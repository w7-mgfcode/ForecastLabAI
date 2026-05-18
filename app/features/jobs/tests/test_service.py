"""Unit tests for the jobs service result-shaping logic.

These are pure-function tests (no DB) for the helpers that flatten a
``BacktestResponse`` into the job-result contract the dashboard reads.
Regression coverage for issue #148 — the backtest job result used to drop
per-fold metrics, stability and the baseline comparison.
"""

import math
from datetime import date

from app.features.backtesting.schemas import (
    BacktestResponse,
    FoldResult,
    ModelBacktestResult,
    SplitBoundary,
    SplitConfig,
)
from app.features.jobs.service import _finite, _shape_backtest_result


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
