"""Unit tests for feature-aware backtesting (MLZOO-B.2).

Pure, DB-free tests of the per-fold feature-aware path wired into
``BacktestingService._run_model_backtest``: the historical matrix build, the
per-fold ``X_train`` slice / ``X_future`` rebuild, the ``feature_aware`` /
``exogenous_policy`` result fields, the gap > 0 fold, and the loud failure when
a feature-aware model reaches the fold loop with no ``ExogenousFrame`` loaded.

The leakage invariants of the row builders themselves live in the load-bearing
``app/shared/feature_frames/tests/test_leakage.py``; this file pins the
backtesting *integration* of those builders.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from app.features.backtesting.schemas import SplitConfig
from app.features.backtesting.service import (
    BacktestingService,
    ExogenousFrame,
    SeriesData,
)
from app.features.backtesting.splitter import TimeSeriesSplitter
from app.features.forecasting.schemas import NaiveModelConfig, RegressionModelConfig
from app.shared.feature_frames import canonical_feature_columns

_N_FEATURES = len(canonical_feature_columns())  # 14 — 4 lags + 6 calendar + 4 exogenous


def _exogenous(n: int) -> ExogenousFrame:
    """A flat, no-promo, no-holiday ExogenousFrame aligned with an n-day series."""
    return ExogenousFrame(
        prices=[9.99] * n,
        baseline_price=9.99,
        promo_dates=set(),
        holiday_dates=set(),
        launch_date=None,
    )


def _series(dates: list[date], values: np.ndarray, *, with_exogenous: bool) -> SeriesData:
    """Build SeriesData, optionally carrying a loaded ExogenousFrame."""
    return SeriesData(
        dates=dates,
        values=values,
        store_id=1,
        product_id=1,
        exogenous=_exogenous(len(dates)) if with_exogenous else None,
    )


def test_canonical_feature_set_is_fourteen_columns() -> None:
    """The feature-aware matrices use exactly the 14-column canonical set."""
    assert _N_FEATURES == 14


def test_build_historical_matrix_shape_matches_series_and_columns(
    sample_dates_120: list[date],
    sample_values_120: np.ndarray,
) -> None:
    """The historical matrix has one row per series day, canonical column width."""
    service = BacktestingService()
    series = _series(sample_dates_120, sample_values_120, with_exogenous=True)

    matrix = service._build_historical_matrix(series)

    assert matrix.shape == (120, _N_FEATURES)


def test_build_historical_matrix_without_exogenous_fails_loud(
    sample_dates_120: list[date],
    sample_values_120: np.ndarray,
) -> None:
    """No ExogenousFrame -> loud ValueError, never a silent all-NaN matrix."""
    service = BacktestingService()
    series = _series(sample_dates_120, sample_values_120, with_exogenous=False)

    with pytest.raises(ValueError, match="ExogenousFrame"):
        service._build_historical_matrix(series)


def test_feature_aware_fold_predicts_one_value_per_test_day(
    sample_dates_120: list[date],
    sample_values_120: np.ndarray,
    sample_split_config_expanding: SplitConfig,
) -> None:
    """A single feature-aware fold yields exactly horizon predictions."""
    service = BacktestingService()
    series = _series(sample_dates_120, sample_values_120, with_exogenous=True)
    splitter = TimeSeriesSplitter(sample_split_config_expanding)
    historical_matrix = service._build_historical_matrix(series)
    split = next(splitter.split(series.dates, series.values))

    predictions = service._run_feature_aware_fold(
        series_data=series,
        split=split,
        model_config=RegressionModelConfig(),
        historical_matrix=historical_matrix,
        gap=sample_split_config_expanding.gap,
    )

    assert predictions.shape == (len(split.test_indices),)
    assert np.all(np.isfinite(predictions))


def test_feature_aware_backtest_produces_per_fold_metrics(
    sample_dates_120: list[date],
    sample_values_120: np.ndarray,
    sample_split_config_expanding: SplitConfig,
) -> None:
    """A regression backtest runs end-to-end and yields per-fold metrics.

    Repurposed positive assertion — feature-aware models are backtestable now
    (supersedes the PRP-29 interim loud-fail contract).
    """
    service = BacktestingService()
    series = _series(sample_dates_120, sample_values_120, with_exogenous=True)
    splitter = TimeSeriesSplitter(sample_split_config_expanding)

    result = service._run_model_backtest(
        series_data=series,
        splitter=splitter,
        model_config=RegressionModelConfig(),
        store_fold_details=True,
    )

    assert result.model_type == "regression"
    assert len(result.fold_results) > 0
    assert "mae" in result.aggregated_metrics
    for fold in result.fold_results:
        assert "mae" in fold.metrics


def test_feature_aware_result_records_observed_policy(
    sample_dates_120: list[date],
    sample_values_120: np.ndarray,
    sample_split_config_expanding: SplitConfig,
) -> None:
    """A feature-aware result is flagged and records the v1 exogenous policy."""
    service = BacktestingService()
    series = _series(sample_dates_120, sample_values_120, with_exogenous=True)
    splitter = TimeSeriesSplitter(sample_split_config_expanding)

    result = service._run_model_backtest(
        series_data=series,
        splitter=splitter,
        model_config=RegressionModelConfig(),
        store_fold_details=True,
    )

    assert result.feature_aware is True
    assert result.exogenous_policy == "observed"


def test_target_only_result_is_not_flagged_feature_aware(
    sample_dates_120: list[date],
    sample_values_120: np.ndarray,
    sample_split_config_expanding: SplitConfig,
) -> None:
    """A target-only baseline keeps feature_aware False and no exogenous policy."""
    service = BacktestingService()
    series = _series(sample_dates_120, sample_values_120, with_exogenous=False)
    splitter = TimeSeriesSplitter(sample_split_config_expanding)

    result = service._run_model_backtest(
        series_data=series,
        splitter=splitter,
        model_config=NaiveModelConfig(),
        store_fold_details=True,
    )

    assert result.feature_aware is False
    assert result.exogenous_policy is None


def test_feature_aware_backtest_without_exogenous_fails_loud(
    sample_dates_120: list[date],
    sample_values_120: np.ndarray,
    sample_split_config_expanding: SplitConfig,
) -> None:
    """A feature-aware model reaching the fold loop with no ExogenousFrame
    must fail LOUD — the genuinely-unsupported path (DECISIONS LOCKED #8)."""
    service = BacktestingService()
    series = _series(sample_dates_120, sample_values_120, with_exogenous=False)
    splitter = TimeSeriesSplitter(sample_split_config_expanding)

    with pytest.raises(ValueError, match="ExogenousFrame"):
        service._run_model_backtest(
            series_data=series,
            splitter=splitter,
            model_config=RegressionModelConfig(),
            store_fold_details=True,
        )


def test_feature_aware_backtest_runs_with_a_gap_fold(
    sample_dates_120: list[date],
    sample_values_120: np.ndarray,
    sample_split_config_with_gap: SplitConfig,
) -> None:
    """A gap > 0 fold runs — the lag columns drop the gap lead-in correctly."""
    assert sample_split_config_with_gap.gap > 0
    service = BacktestingService()
    series = _series(sample_dates_120, sample_values_120, with_exogenous=True)
    splitter = TimeSeriesSplitter(sample_split_config_with_gap)

    result = service._run_model_backtest(
        series_data=series,
        splitter=splitter,
        model_config=RegressionModelConfig(),
        store_fold_details=True,
    )

    assert result.feature_aware is True
    assert len(result.fold_results) > 0
    for fold in result.fold_results:
        assert np.isfinite(fold.metrics["mae"])
