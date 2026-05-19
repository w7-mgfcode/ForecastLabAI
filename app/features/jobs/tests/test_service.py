"""Unit tests for the jobs service result-shaping logic.

These are pure-function tests (no DB) for the helpers that flatten a
``BacktestResponse`` into the job-result contract the dashboard reads.
Regression coverage for issue #148 — the backtest job result used to drop
per-fold metrics, stability and the baseline comparison.
"""

import math
from datetime import date
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.backtesting.schemas import (
    BacktestResponse,
    FoldResult,
    ModelBacktestResult,
    SplitBoundary,
    SplitConfig,
)
from app.features.backtesting.service import BacktestingService
from app.features.forecasting.schemas import (
    LightGBMModelConfig,
    ProphetLikeModelConfig,
    RegressionModelConfig,
    TrainResponse,
)
from app.features.forecasting.service import ForecastingService
from app.features.jobs.service import JobService, _finite, _shape_backtest_result


def _fold(idx: int, mae: float, smape: float, wape: float, bias: float) -> FoldResult:
    """Build a FoldResult with the given per-fold metrics."""
    return FoldResult(
        fold_index=idx,
        split=SplitBoundary(
            fold_index=idx,
            train_start=date(2024, 1, 1),
            train_end=date(2024, 2, 1),
            test_start=date(2024, 2, 2),
            test_end=date(2024, 2, 15),
            train_size=32,
            test_size=14,
        ),
        dates=[date(2024, 2, 2)],
        actuals=[10.0],
        predictions=[11.0],
        metrics={"mae": mae, "smape": smape, "wape": wape, "bias": bias},
    )


def _make_response(*, with_baselines: bool = True, nan_stability: bool = False) -> BacktestResponse:
    """Build a minimal BacktestResponse for shaping tests."""
    folds = [
        _fold(0, 10.0, 12.0, 11.0, 1.0),
        _fold(1, 14.0, 11.0, 12.0, 3.0),
    ]
    stability = {
        "wape_stability": math.nan if nan_stability else 8.5,
        "mae_stability": 5.0,
    }
    main = ModelBacktestResult(
        model_type="seasonal_naive",
        config_hash="abc123",
        fold_results=folds,
        aggregated_metrics={"mae": 12.0, "smape": 11.5, "wape": 11.5, "bias": 2.0},
        metric_std=stability,
    )
    baselines: list[ModelBacktestResult] | None = None
    comparison: dict[str, dict[str, float]] | None = None
    if with_baselines:
        baselines = [
            ModelBacktestResult(
                model_type="naive",
                config_hash="n1",
                fold_results=folds,
                aggregated_metrics={"mae": 15.0, "smape": 14.0, "wape": 14.0, "bias": 3.0},
                metric_std={},
            ),
        ]
        comparison = {
            "mae": {
                "main": 12.0,
                "naive": 15.0,
                "vs_naive_pct": 20.0,
                "seasonal_naive": 13.0,
                "vs_seasonal_pct": 7.7,
            },
        }
    return BacktestResponse(
        backtest_id="bt-1",
        store_id=1,
        product_id=1,
        config_hash="cfg",
        split_config=SplitConfig(n_splits=2),
        main_model_results=main,
        baseline_results=baselines,
        comparison_summary=comparison,
        duration_ms=3.5,
        leakage_check_passed=True,
    )


def test_shape_backtest_result_includes_fold_metrics() -> None:
    """fold_metrics is populated, one entry per fold, with 1-based fold numbers."""
    response = _make_response()
    result = _shape_backtest_result(response, "seasonal_naive")

    # top-level fields are passed through unchanged
    assert result["backtest_id"] == response.backtest_id
    assert result["model_type"] == "seasonal_naive"
    assert result["duration_ms"] == response.duration_ms

    # per-fold metrics are present and correctly shaped
    assert result["n_splits"] == 2
    assert [f["fold"] for f in result["fold_metrics"]] == [1, 2]
    assert result["fold_metrics"][0]["mae"] == 10.0
    assert result["fold_metrics"][1]["bias"] == 3.0


def test_shape_backtest_result_aggregated_metrics_use_mean_keys() -> None:
    """aggregated_metrics uses the *_mean keys plus stability_index."""
    result = _shape_backtest_result(_make_response(), "seasonal_naive")
    agg = result["aggregated_metrics"]
    assert set(agg) == {"mae_mean", "smape_mean", "wape_mean", "bias_mean", "stability_index"}
    assert agg["mae_mean"] == 12.0
    assert agg["stability_index"] == 8.5


def test_shape_backtest_result_includes_baseline_comparison() -> None:
    """baseline_comparison carries naive/seasonal MAE and improvement percentages."""
    result = _shape_backtest_result(_make_response(with_baselines=True), "seasonal_naive")
    comparison = result["baseline_comparison"]
    assert comparison["naive"] == {"mae": 15.0, "improvement_pct": 20.0}
    assert comparison["seasonal_naive"] == {"mae": 13.0, "improvement_pct": 7.7}


def test_shape_backtest_result_omits_baseline_when_absent() -> None:
    """With no comparison summary, baseline_comparison is left out entirely."""
    result = _shape_backtest_result(_make_response(with_baselines=False), "seasonal_naive")
    assert "baseline_comparison" not in result


def test_shape_backtest_result_coerces_nan_stability() -> None:
    """NaN metrics are coerced to 0.0 — Postgres jsonb rejects non-finite floats."""
    result = _shape_backtest_result(_make_response(nan_stability=True), "seasonal_naive")
    assert result["aggregated_metrics"]["stability_index"] == 0.0


def test_shape_backtest_result_defaults_missing_metric_to_zero() -> None:
    """A metric absent from the response defaults to 0.0 instead of being dropped.

    Guards against silent drift if the backtesting service stops emitting one of
    the _BACKTEST_METRICS keys.
    """
    response = _make_response()
    del response.main_model_results.aggregated_metrics["bias"]
    result = _shape_backtest_result(response, "seasonal_naive")
    # the *_mean key is still present in the contract, just zeroed
    assert result["aggregated_metrics"]["bias_mean"] == 0.0
    assert "bias_mean" in result["aggregated_metrics"]


def test_finite_coerces_non_finite_values() -> None:
    """_finite passes finite values through and maps NaN/inf to 0.0."""
    assert _finite(3.5) == 3.5
    assert _finite(0.0) == 0.0
    assert _finite(math.nan) == 0.0
    assert _finite(math.inf) == 0.0
    assert _finite(-math.inf) == 0.0


# =============================================================================
# _execute_train regression-model support (#229)
# =============================================================================


def _fake_train_response(model_type: str) -> TrainResponse:
    """Build a TrainResponse stub for mocking ForecastingService.train_model."""
    return TrainResponse(
        store_id=1,
        product_id=1,
        model_type=model_type,
        model_path="/data/artifacts/model_abc123def456.joblib",
        config_hash="cfg-hash",
        n_observations=400,
        train_start_date=date(2024, 1, 1),
        train_end_date=date(2024, 12, 31),
        duration_ms=12.0,
    )


_REGRESSION_PARAMS: dict[str, Any] = {
    "model_type": "regression",
    "store_id": 1,
    "product_id": 1,
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
}


async def test_execute_train_builds_regression_config() -> None:
    """A train job with model_type='regression' builds a RegressionModelConfig (#229)."""
    fake = _fake_train_response("regression")
    with patch.object(
        ForecastingService, "train_model", new=AsyncMock(return_value=fake)
    ) as mock_train:
        result = await JobService()._execute_train(
            db=cast(AsyncSession, AsyncMock()),
            params=_REGRESSION_PARAMS,
        )
    assert mock_train.call_args is not None
    config = mock_train.call_args.kwargs["config"]
    assert isinstance(config, RegressionModelConfig)
    assert result["model_type"] == "regression"
    # run_id is parsed from the model_abc123def456.joblib artifact path.
    assert result["run_id"] == "abc123def456"


async def test_execute_train_builds_lightgbm_config() -> None:
    """A train job with model_type='lightgbm' builds a LightGBMModelConfig (#242).

    ``train_model`` is mocked, so ``model_factory`` (and its feature-flag gate)
    is never reached and ``LightGBMModelConfig`` is a pure Pydantic schema —
    this test needs neither the flag nor the optional lightgbm dependency.
    """
    fake = _fake_train_response("lightgbm")
    with patch.object(
        ForecastingService, "train_model", new=AsyncMock(return_value=fake)
    ) as mock_train:
        result = await JobService()._execute_train(
            db=cast(AsyncSession, AsyncMock()),
            params={**_REGRESSION_PARAMS, "model_type": "lightgbm"},
        )
    assert mock_train.call_args is not None
    config = mock_train.call_args.kwargs["config"]
    assert isinstance(config, LightGBMModelConfig)
    assert result["model_type"] == "lightgbm"


async def test_execute_train_builds_prophet_like_config() -> None:
    """A train job with model_type='prophet_like' builds a ProphetLikeModelConfig (#248).

    ``train_model`` is mocked, so the test is pure (no DB). The Prophet-like
    model is pure scikit-learn — no feature flag, no optional dependency.
    """
    fake = _fake_train_response("prophet_like")
    with patch.object(
        ForecastingService, "train_model", new=AsyncMock(return_value=fake)
    ) as mock_train:
        result = await JobService()._execute_train(
            db=cast(AsyncSession, AsyncMock()),
            params={**_REGRESSION_PARAMS, "model_type": "prophet_like"},
        )
    assert mock_train.call_args is not None
    config = mock_train.call_args.kwargs["config"]
    assert isinstance(config, ProphetLikeModelConfig)
    assert result["model_type"] == "prophet_like"


async def test_execute_train_rejects_unsupported_model_type() -> None:
    """_execute_train still rejects a genuinely unsupported model_type."""
    with pytest.raises(ValueError, match="Unsupported model_type"):
        await JobService()._execute_train(
            db=cast(AsyncSession, AsyncMock()),
            params={**_REGRESSION_PARAMS, "model_type": "arima"},
        )


# Parameters for a backtest job — _execute_backtest reads these keys.
_BACKTEST_PARAMS: dict[str, Any] = {
    "model_type": "regression",
    "store_id": 1,
    "product_id": 1,
    "start_date": "2024-01-01",
    "end_date": "2024-12-01",
    "n_splits": 3,
}


async def test_execute_backtest_builds_regression_config() -> None:
    """A backtest job with model_type='regression' builds a RegressionModelConfig.

    ``run_backtest`` is mocked, so the test is pure (no DB): it pins that
    ``_execute_backtest`` widened its allow-list and shaped the result.
    """
    response = _make_response()
    with patch.object(
        BacktestingService, "run_backtest", new=AsyncMock(return_value=response)
    ) as mock_run:
        result = await JobService()._execute_backtest(
            db=cast(AsyncSession, AsyncMock()),
            params=_BACKTEST_PARAMS,
        )
    assert mock_run.call_args is not None
    config = mock_run.call_args.kwargs["config"]
    assert isinstance(config.model_config_main, RegressionModelConfig)
    assert result["model_type"] == "regression"
    # The frontend job-result contract is still shaped (byte-stable keys).
    assert "fold_metrics" in result
    assert "aggregated_metrics" in result


async def test_execute_backtest_builds_lightgbm_config() -> None:
    """A backtest job with model_type='lightgbm' builds a LightGBMModelConfig.

    ``run_backtest`` is mocked, so ``model_factory``'s feature-flag gate is
    never reached and the optional lightgbm dependency is not required.
    """
    response = _make_response()
    with patch.object(
        BacktestingService, "run_backtest", new=AsyncMock(return_value=response)
    ) as mock_run:
        result = await JobService()._execute_backtest(
            db=cast(AsyncSession, AsyncMock()),
            params={**_BACKTEST_PARAMS, "model_type": "lightgbm"},
        )
    assert mock_run.call_args is not None
    config = mock_run.call_args.kwargs["config"]
    assert isinstance(config.model_config_main, LightGBMModelConfig)
    assert result["model_type"] == "lightgbm"


async def test_execute_backtest_builds_prophet_like_config() -> None:
    """A backtest job with model_type='prophet_like' builds a ProphetLikeModelConfig.

    ``run_backtest`` is mocked, so the test is pure (no DB): it pins that
    ``_execute_backtest`` widened its allow-list to the pure-sklearn additive
    model and shaped the result.
    """
    response = _make_response()
    with patch.object(
        BacktestingService, "run_backtest", new=AsyncMock(return_value=response)
    ) as mock_run:
        result = await JobService()._execute_backtest(
            db=cast(AsyncSession, AsyncMock()),
            params={**_BACKTEST_PARAMS, "model_type": "prophet_like"},
        )
    assert mock_run.call_args is not None
    config = mock_run.call_args.kwargs["config"]
    assert isinstance(config.model_config_main, ProphetLikeModelConfig)
    assert result["model_type"] == "prophet_like"


async def test_execute_backtest_rejects_unsupported_model_type() -> None:
    """_execute_backtest still rejects a genuinely unsupported model_type."""
    with pytest.raises(ValueError, match="Unsupported model_type"):
        await JobService()._execute_backtest(
            db=cast(AsyncSession, AsyncMock()),
            params={**_BACKTEST_PARAMS, "model_type": "arima"},
        )
