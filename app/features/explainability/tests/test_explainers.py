"""Unit tests for the rule-based explainers.

The load-bearing assertion: each explainer's h=1 forecast value EQUALS the real
forecaster's ``.fit(y).predict(1)[0]`` on the same series. A rule-based
explainer is exact — if it diverges from the forecaster, it is wrong.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.features.explainability.explainers import (
    MovingAverageExplainer,
    NaiveExplainer,
    SeasonalNaiveExplainer,
    explainer_factory,
)
from app.features.explainability.schemas import ConfidenceLevel
from app.features.forecasting.models import (
    MovingAverageForecaster,
    NaiveForecaster,
    SeasonalNaiveForecaster,
)


class TestNaiveExplainer:
    """Tests for NaiveExplainer."""

    def test_forecast_matches_real_forecaster(self, sample_series: np.ndarray) -> None:
        """h=1 value equals NaiveForecaster's prediction on the same series."""
        forecast, _ = NaiveExplainer().explain(sample_series)
        expected = float(NaiveForecaster().fit(sample_series).predict(1)[0])
        assert forecast == pytest.approx(expected)

    def test_main_driver_contribution_sums_to_forecast(self, sample_series: np.ndarray) -> None:
        """Driver contributions sum to the forecast value."""
        forecast, drivers = NaiveExplainer().explain(sample_series)
        assert sum(d.contribution for d in drivers) == pytest.approx(forecast)

    def test_recent_trend_driver_present_for_long_series(self, sample_series: np.ndarray) -> None:
        """A long series gets an informational recent_trend driver."""
        _, drivers = NaiveExplainer().explain(sample_series)
        names = {d.name for d in drivers}
        assert "last_observation" in names
        assert "recent_trend" in names
        trend = next(d for d in drivers if d.name == "recent_trend")
        assert trend.contribution == 0.0

    def test_no_trend_driver_for_short_series(self, short_series: np.ndarray) -> None:
        """A short series gets only the last_observation driver."""
        _, drivers = NaiveExplainer().explain(short_series)
        assert [d.name for d in drivers] == ["last_observation"]

    def test_empty_series_raises(self) -> None:
        """An empty series raises ValueError (mirrors NaiveForecaster.fit)."""
        with pytest.raises(ValueError, match="empty"):
            NaiveExplainer().explain(np.array([], dtype=np.float64))

    def test_confidence_downgrades_on_short_series(
        self, sample_series: np.ndarray, short_series: np.ndarray
    ) -> None:
        """Confidence is LOW for a short series, MEDIUM otherwise."""
        assert NaiveExplainer().confidence(short_series) == ConfidenceLevel.LOW
        assert NaiveExplainer().confidence(sample_series) == ConfidenceLevel.MEDIUM


class TestSeasonalNaiveExplainer:
    """Tests for SeasonalNaiveExplainer."""

    def test_forecast_matches_real_forecaster(self, sample_series: np.ndarray) -> None:
        """h=1 value equals SeasonalNaiveForecaster's prediction."""
        forecast, _ = SeasonalNaiveExplainer(season_length=7).explain(sample_series)
        expected = float(SeasonalNaiveForecaster(season_length=7).fit(sample_series).predict(1)[0])
        assert forecast == pytest.approx(expected)

    def test_main_driver_contribution_sums_to_forecast(self, sample_series: np.ndarray) -> None:
        """Driver contributions sum to the forecast value."""
        forecast, drivers = SeasonalNaiveExplainer(season_length=7).explain(sample_series)
        assert sum(d.contribution for d in drivers) == pytest.approx(forecast)
        assert drivers[0].direction == "positive"

    def test_too_short_series_raises(self, short_series: np.ndarray) -> None:
        """A series shorter than season_length raises ValueError."""
        with pytest.raises(ValueError, match="at least"):
            SeasonalNaiveExplainer(season_length=7).explain(short_series)

    def test_invalid_season_length_raises(self) -> None:
        """season_length < 1 raises ValueError."""
        with pytest.raises(ValueError, match="season_length"):
            SeasonalNaiveExplainer(season_length=0)

    def test_confidence_downgrades_under_two_cycles(self) -> None:
        """Confidence is LOW under two seasonal cycles, MEDIUM otherwise."""
        short = np.arange(10.0, dtype=np.float64)  # 10 < 2*7
        long = np.arange(40.0, dtype=np.float64)  # 40 >= 2*7
        assert SeasonalNaiveExplainer(7).confidence(short) == ConfidenceLevel.LOW
        assert SeasonalNaiveExplainer(7).confidence(long) == ConfidenceLevel.MEDIUM


class TestMovingAverageExplainer:
    """Tests for MovingAverageExplainer."""

    def test_forecast_matches_real_forecaster(self, sample_series: np.ndarray) -> None:
        """h=1 value equals MovingAverageForecaster's prediction."""
        forecast, _ = MovingAverageExplainer(window_size=7).explain(sample_series)
        expected = float(MovingAverageForecaster(window_size=7).fit(sample_series).predict(1)[0])
        assert forecast == pytest.approx(expected)

    def test_main_driver_contribution_sums_to_forecast(self, sample_series: np.ndarray) -> None:
        """Driver contributions sum to the forecast (dispersion contributes 0)."""
        forecast, drivers = MovingAverageExplainer(window_size=7).explain(sample_series)
        assert sum(d.contribution for d in drivers) == pytest.approx(forecast)
        dispersion = next(d for d in drivers if d.name == "window_dispersion")
        assert dispersion.contribution == 0.0
        assert dispersion.direction == "neutral"

    def test_too_short_series_raises(self, short_series: np.ndarray) -> None:
        """A series shorter than window_size raises ValueError."""
        with pytest.raises(ValueError, match="at least"):
            MovingAverageExplainer(window_size=7).explain(short_series)

    def test_confidence_high_for_stable_window(self, flat_series: np.ndarray) -> None:
        """A flat (zero-dispersion) window yields HIGH confidence."""
        assert MovingAverageExplainer(7).confidence(flat_series) == ConfidenceLevel.HIGH

    def test_confidence_medium_for_noisy_window(self) -> None:
        """A high-variance window yields MEDIUM confidence."""
        noisy = np.array([1.0, 100.0, 2.0, 99.0, 3.0, 98.0, 4.0], dtype=np.float64)
        assert MovingAverageExplainer(7).confidence(noisy) == ConfidenceLevel.MEDIUM


class TestExplainerFactory:
    """Tests for explainer_factory."""

    def test_builds_each_baseline(self) -> None:
        """The factory builds the matching explainer per baseline model type."""
        assert isinstance(explainer_factory("naive"), NaiveExplainer)
        assert isinstance(
            explainer_factory("seasonal_naive", season_length=14), SeasonalNaiveExplainer
        )
        assert isinstance(
            explainer_factory("moving_average", window_size=21), MovingAverageExplainer
        )

    def test_seasonal_defaults_to_seven(self) -> None:
        """A None season_length defaults to 7."""
        explainer = explainer_factory("seasonal_naive")
        assert isinstance(explainer, SeasonalNaiveExplainer)
        assert explainer.season_length == 7

    @pytest.mark.parametrize("model_type", ["lightgbm", "regression"])
    def test_rejects_non_baseline_models(self, model_type: str) -> None:
        """lightgbm/regression are rejected (MVP scope guard)."""
        with pytest.raises(ValueError, match="baseline models only"):
            explainer_factory(model_type)

    def test_rejects_unknown_model(self) -> None:
        """An unknown model type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown model type"):
            explainer_factory("transformer")

    # PRP-36 — new baseline explainers
    def test_builds_weighted_moving_average(self) -> None:
        """The factory dispatches the weighted MA explainer with correct params."""
        from app.features.explainability.explainers import WeightedMovingAverageExplainer

        explainer = explainer_factory(
            "weighted_moving_average",
            window_size=14,
            weight_strategy="exponential",
            decay=0.5,
        )
        assert isinstance(explainer, WeightedMovingAverageExplainer)
        assert explainer.window_size == 14
        assert explainer.weight_strategy == "exponential"
        assert explainer.decay == 0.5

    def test_builds_seasonal_average(self) -> None:
        """The factory dispatches the seasonal-average explainer with correct params."""
        from app.features.explainability.explainers import SeasonalAverageExplainer

        explainer = explainer_factory(
            "seasonal_average",
            season_length=7,
            lookback_cycles=3,
            trim_outliers=True,
        )
        assert isinstance(explainer, SeasonalAverageExplainer)
        assert explainer.season_length == 7
        assert explainer.lookback_cycles == 3
        assert explainer.trim_outliers is True

    def test_builds_trend_regression_baseline_with_bundle(self) -> None:
        """The trend baseline factory requires a fitted Ridge bundle."""
        from app.features.explainability.explainers import (
            TrendRegressionBaselineExplainer,
        )

        explainer = explainer_factory(
            "trend_regression_baseline",
            trend_baseline_bundle=(0.5, [1.0] * 20, True, True),
        )
        assert isinstance(explainer, TrendRegressionBaselineExplainer)
        assert explainer.intercept == 0.5

    def test_trend_regression_baseline_without_bundle_raises(self) -> None:
        """Trend baseline without a fitted Ridge bundle fails with a clear message."""
        with pytest.raises(ValueError, match="trend_baseline_bundle"):
            explainer_factory("trend_regression_baseline")

    @pytest.mark.parametrize(
        "model_type",
        ["lightgbm", "regression", "xgboost", "random_forest", "prophet_like"],
    )
    def test_feature_aware_models_routed_to_scope_guard(self, model_type: str) -> None:
        """PRP-36 — every feature-aware model surfaces the scope guard 422 message."""
        with pytest.raises(ValueError, match="baseline models only"):
            explainer_factory(model_type)


class TestWeightedMovingAverageExplainer:
    """PRP-36 — h=1 forecast equals the matching forecaster's prediction."""

    def test_explanation_matches_forecaster_linear(self) -> None:
        from app.features.explainability.explainers import (
            WeightedMovingAverageExplainer,
        )
        from app.features.forecasting.models import WeightedMovingAverageForecaster

        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        forecaster = WeightedMovingAverageForecaster(window_size=7).fit(y)
        explainer = WeightedMovingAverageExplainer(window_size=7)
        forecast, drivers = explainer.explain(y)
        assert forecast == pytest.approx(float(forecaster.predict(1)[0]))
        names = [d.name for d in drivers]
        assert "weighted_window_mean" in names

    def test_explanation_matches_forecaster_exponential(self) -> None:
        from app.features.explainability.explainers import (
            WeightedMovingAverageExplainer,
        )
        from app.features.forecasting.models import WeightedMovingAverageForecaster

        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        forecaster = WeightedMovingAverageForecaster(
            window_size=5, weight_strategy="exponential", decay=0.5
        ).fit(y)
        explainer = WeightedMovingAverageExplainer(
            window_size=5, weight_strategy="exponential", decay=0.5
        )
        forecast, _ = explainer.explain(y)
        assert forecast == pytest.approx(float(forecaster.predict(1)[0]))


class TestSeasonalAverageExplainer:
    """PRP-36 — h=1 forecast equals the matching forecaster's prediction."""

    def test_explanation_matches_forecaster_on_weekly_cycle(self) -> None:
        from app.features.explainability.explainers import SeasonalAverageExplainer
        from app.features.forecasting.models import SeasonalAverageForecaster

        weekly = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0])
        y = np.tile(weekly, 4)
        forecaster = SeasonalAverageForecaster(season_length=7, lookback_cycles=4).fit(y)
        explainer = SeasonalAverageExplainer(season_length=7, lookback_cycles=4)
        forecast, _ = explainer.explain(y)
        assert forecast == pytest.approx(float(forecaster.predict(1)[0]))
