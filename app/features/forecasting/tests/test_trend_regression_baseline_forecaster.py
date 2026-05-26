"""Tests for :class:`TrendRegressionBaselineForecaster` (PRP-36)."""

from __future__ import annotations

import numpy as np
import pytest

from app.features.forecasting.models import (
    TrendRegressionBaselineForecaster,
    model_factory,
)
from app.features.forecasting.schemas import TrendRegressionBaselineModelConfig


class TestTrendRegressionBaselineForecaster:
    """Behavioural tests for the Ridge trend baseline."""

    def test_requires_features_false(self) -> None:
        """The trend baseline is target-only (calendar features built internally)."""
        assert TrendRegressionBaselineForecaster.requires_features is False

    def test_fit_raises_on_too_few_observations(self) -> None:
        """fit() needs at least two observations to estimate a trend."""
        model = TrendRegressionBaselineForecaster()
        with pytest.raises(ValueError, match="at least 2 observations"):
            model.fit(np.array([10.0]))

    def test_predict_before_fit_raises(self) -> None:
        """predict() before fit() raises RuntimeError."""
        with pytest.raises(RuntimeError, match="must be fitted"):
            TrendRegressionBaselineForecaster().predict(horizon=5)

    def test_predict_shape(self) -> None:
        """predict() returns the configured horizon length."""
        y = np.linspace(0.0, 30.0, 60)
        model = TrendRegressionBaselineForecaster().fit(y)
        assert model.predict(horizon=14).shape == (14,)

    def test_perfect_linear_series_extrapolated_within_tolerance(self) -> None:
        """A noise-free linear series extrapolates near-perfectly under Ridge."""
        # y = 1 * elapsed_day on a 60-day window. Disable calendar one-hots so
        # the design reduces to a single elapsed-day column and Ridge regresses
        # the slope cleanly.
        n = 60
        y = np.arange(n, dtype=np.float64)
        model = TrendRegressionBaselineForecaster(
            alpha=0.0, include_dow=False, include_month=False
        ).fit(y)
        forecasts = model.predict(horizon=10)
        expected = np.arange(n, n + 10, dtype=np.float64)
        np.testing.assert_allclose(forecasts, expected, atol=1e-6)

    def test_deterministic_with_seed(self) -> None:
        """Ridge is closed-form; two identical fits give identical forecasts."""
        y = np.sin(np.linspace(0.0, 10.0, 90)) + np.linspace(0.0, 5.0, 90)
        a = TrendRegressionBaselineForecaster(random_state=42).fit(y)
        b = TrendRegressionBaselineForecaster(random_state=42).fit(y)
        np.testing.assert_array_equal(a.predict(horizon=14), b.predict(horizon=14))

    def test_dow_toggle_changes_design_matrix_width(self) -> None:
        """include_dow expands the design matrix by 7 one-hot columns."""
        y = np.arange(40, dtype=np.float64)
        with_dow = TrendRegressionBaselineForecaster(include_dow=True, include_month=False)
        without_dow = TrendRegressionBaselineForecaster(include_dow=False, include_month=False)
        # Design matrix is built internally — compare the first row width.
        row_with = with_dow._design_row(elapsed_day=0)
        row_without = without_dow._design_row(elapsed_day=0)
        assert row_with.shape[0] - row_without.shape[0] == 7

        # Both should still fit + predict against the same series.
        with_dow.fit(y)
        without_dow.fit(y)
        assert with_dow.predict(horizon=3).shape == (3,)
        assert without_dow.predict(horizon=3).shape == (3,)

    def test_factory_creates_trend_regression_baseline(self) -> None:
        """model_factory dispatches TrendRegressionBaselineModelConfig."""
        cfg = TrendRegressionBaselineModelConfig(alpha=2.0, include_dow=False, include_month=True)
        model = model_factory(cfg, random_state=7)
        assert isinstance(model, TrendRegressionBaselineForecaster)
        assert model.alpha == 2.0
        assert model.include_dow is False
        assert model.include_month is True
        assert model.random_state == 7
