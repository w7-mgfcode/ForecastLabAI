"""Tests for :class:`SeasonalAverageForecaster` (PRP-36)."""

from __future__ import annotations

import numpy as np
import pytest

from app.features.forecasting.models import (
    SeasonalAverageForecaster,
    model_factory,
)
from app.features.forecasting.schemas import SeasonalAverageModelConfig


def _weekly_pattern(n_weeks: int) -> np.ndarray:
    """Build ``n_weeks`` weeks of a 7-day pattern [10, 20, ..., 70]."""
    pattern = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0])
    return np.tile(pattern, n_weeks)


class TestSeasonalAverageForecaster:
    """Behavioural tests for the seasonal-average baseline."""

    def test_requires_features_false(self) -> None:
        """The seasonal-average baseline is target-only."""
        assert SeasonalAverageForecaster.requires_features is False

    def test_invalid_season_length_raises(self) -> None:
        """season_length < 2 surfaces a clear error."""
        with pytest.raises(ValueError, match="season_length must be >= 2"):
            SeasonalAverageForecaster(season_length=1)

    def test_invalid_lookback_cycles_raises(self) -> None:
        """lookback_cycles < 2 surfaces a clear error."""
        with pytest.raises(ValueError, match="lookback_cycles must be >= 2"):
            SeasonalAverageForecaster(lookback_cycles=1)

    def test_fit_raises_on_too_few_observations(self) -> None:
        """fit() requires at least 2 * season_length observations."""
        model = SeasonalAverageForecaster(season_length=7)
        with pytest.raises(ValueError, match="at least 14"):
            model.fit(np.array([1.0] * 10))

    def test_predict_picks_matching_dow_positions(self) -> None:
        """A perfectly-cyclical series forecasts the matching DOW pattern exactly."""
        y = _weekly_pattern(n_weeks=4)
        model = SeasonalAverageForecaster(season_length=7, lookback_cycles=4).fit(y)
        # Horizon day 1 corresponds to the same DOW as positions
        # {y[-7], y[-14], y[-21], y[-28]} — all equal to 10.0 in this pattern.
        forecasts = model.predict(horizon=7)
        np.testing.assert_array_almost_equal(
            forecasts,
            [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0],
        )

    def test_predict_shape(self) -> None:
        """predict() returns the configured horizon length."""
        y = _weekly_pattern(n_weeks=4)
        model = SeasonalAverageForecaster(season_length=7, lookback_cycles=4).fit(y)
        assert model.predict(horizon=10).shape == (10,)

    def test_lookback_cycles_smaller_than_history_works(self) -> None:
        """The forecaster trims history to ``lookback_cycles * season_length``."""
        y = _weekly_pattern(n_weeks=6)  # 42 days
        model = SeasonalAverageForecaster(season_length=7, lookback_cycles=2).fit(y)
        # Only the last 14 days are sampled, but the cyclical pattern is
        # identical so the forecast still matches the canonical week.
        forecasts = model.predict(horizon=7)
        np.testing.assert_array_almost_equal(
            forecasts,
            [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0],
        )

    def test_trim_outliers_drops_min_and_max(self) -> None:
        """With ``trim_outliers=True``, each per-bucket sample drops min + max."""
        # Build a series where day-1 of each week takes values 5, 10, 100, 50
        # (4 lookback samples → after trim drops 5 and 100, leaves [10, 50]
        # → mean = 30.0). Other days repeat a fixed value.
        weeks = []
        for w_value in (5.0, 10.0, 100.0, 50.0):
            weeks.append([w_value, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
        y = np.array(weeks, dtype=np.float64).flatten()

        trimmed = SeasonalAverageForecaster(
            season_length=7, lookback_cycles=4, trim_outliers=True
        ).fit(y)
        plain = SeasonalAverageForecaster(
            season_length=7, lookback_cycles=4, trim_outliers=False
        ).fit(y)

        # Trimmed mean over day-1 samples: drop {5.0, 100.0}, keep {10.0, 50.0} → 30.0
        assert trimmed.predict(horizon=1)[0] == pytest.approx(30.0)
        # Plain mean: (5 + 10 + 100 + 50) / 4 = 41.25
        assert plain.predict(horizon=1)[0] == pytest.approx(41.25)

    def test_deterministic_with_seed(self) -> None:
        """Two identically-configured fits emit byte-identical forecasts."""
        y = _weekly_pattern(n_weeks=4)
        a = SeasonalAverageForecaster(random_state=42).fit(y)
        b = SeasonalAverageForecaster(random_state=42).fit(y)
        np.testing.assert_array_equal(a.predict(horizon=14), b.predict(horizon=14))

    def test_predict_before_fit_raises(self) -> None:
        """predict() before fit() raises RuntimeError."""
        with pytest.raises(RuntimeError, match="must be fitted"):
            SeasonalAverageForecaster().predict(horizon=5)

    def test_factory_creates_seasonal_average(self) -> None:
        """model_factory dispatches SeasonalAverageModelConfig."""
        cfg = SeasonalAverageModelConfig(season_length=7, lookback_cycles=3, trim_outliers=True)
        model = model_factory(cfg, random_state=99)
        assert isinstance(model, SeasonalAverageForecaster)
        assert model.season_length == 7
        assert model.lookback_cycles == 3
        assert model.trim_outliers is True
        assert model.random_state == 99
