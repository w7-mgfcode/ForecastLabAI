"""Tests for :class:`WeightedMovingAverageForecaster` (PRP-36)."""

from __future__ import annotations

import numpy as np
import pytest

from app.features.forecasting.models import (
    WeightedMovingAverageForecaster,
    model_factory,
)
from app.features.forecasting.schemas import WeightedMovingAverageModelConfig


class TestWeightedMovingAverageForecaster:
    """Behavioural tests for the weighted-moving-average baseline."""

    def test_requires_features_false(self) -> None:
        """The weighted moving average is a target-only baseline."""
        assert WeightedMovingAverageForecaster.requires_features is False

    def test_fit_raises_on_too_few_observations(self) -> None:
        """fit() must reject a series shorter than window_size."""
        model = WeightedMovingAverageForecaster(window_size=7)
        with pytest.raises(ValueError, match="at least 7"):
            model.fit(np.array([1.0, 2.0, 3.0]))

    def test_invalid_window_size_raises(self) -> None:
        """window_size below the minimum surfaces a clear error."""
        with pytest.raises(ValueError, match="window_size must be >= 2"):
            WeightedMovingAverageForecaster(window_size=1)

    def test_invalid_weight_strategy_raises(self) -> None:
        """Unknown weight strategy surfaces a clear error."""
        with pytest.raises(ValueError, match="weight_strategy must be"):
            WeightedMovingAverageForecaster(weight_strategy="quadratic")  # type: ignore[arg-type]

    @pytest.mark.parametrize("decay", [-0.1, 0.0, 1.0, 1.5])
    def test_invalid_decay_raises(self, decay: float) -> None:
        """decay outside the open (0, 1) interval surfaces a clear error."""
        with pytest.raises(ValueError, match="decay must lie in"):
            WeightedMovingAverageForecaster(decay=decay)

    def test_fit_then_predict_shape(self) -> None:
        """predict() returns the configured horizon length."""
        y = np.array([10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0])
        model = WeightedMovingAverageForecaster(window_size=7).fit(y)
        forecasts = model.predict(horizon=5)
        assert forecasts.shape == (5,)
        assert np.all(forecasts == forecasts[0])  # constant forecast

    def test_linear_weights_match_np_average(self) -> None:
        """Linear-strategy mean matches np.average(weights=1..W) exactly."""
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        model = WeightedMovingAverageForecaster(window_size=7, weight_strategy="linear").fit(y)
        expected = float(np.average(y, weights=np.arange(1, 8)))
        assert model.predict(horizon=1)[0] == pytest.approx(expected)

    def test_exponential_weights_match_np_average(self) -> None:
        """Exponential-strategy mean matches np.average(weights=decay**...)."""
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        decay = 0.5
        model = WeightedMovingAverageForecaster(
            window_size=5, weight_strategy="exponential", decay=decay
        ).fit(y)
        weights = np.power(decay, np.arange(4, -1, -1))
        expected = float(np.average(y, weights=weights))
        assert model.predict(horizon=1)[0] == pytest.approx(expected)

    def test_deterministic_with_seed(self) -> None:
        """Two identically-configured fits emit byte-identical forecasts."""
        y = np.linspace(1.0, 20.0, 20)
        a = WeightedMovingAverageForecaster(window_size=7, random_state=42).fit(y)
        b = WeightedMovingAverageForecaster(window_size=7, random_state=42).fit(y)
        np.testing.assert_array_equal(a.predict(horizon=10), b.predict(horizon=10))

    def test_predict_before_fit_raises(self) -> None:
        """predict() before fit() raises RuntimeError."""
        with pytest.raises(RuntimeError, match="must be fitted"):
            WeightedMovingAverageForecaster().predict(horizon=5)

    def test_recent_observations_weighted_higher_than_old_under_linear(self) -> None:
        """A trend series biases the linear-weighted mean toward recent values."""
        # Series rising 1..10 — linear weighting should produce a forecast
        # closer to the recent end than to the simple mean (5.5).
        y = np.arange(1.0, 11.0)
        wma = WeightedMovingAverageForecaster(window_size=10, weight_strategy="linear").fit(y)
        simple_mean = float(y.mean())
        wma_value = float(wma.predict(horizon=1)[0])
        assert wma_value > simple_mean, (
            f"linear WMA should overweight recent values, got {wma_value} <= {simple_mean}"
        )

    def test_get_set_params_round_trip(self) -> None:
        """get_params()/set_params() round-trip the constructor surface."""
        model = WeightedMovingAverageForecaster(
            window_size=14, weight_strategy="exponential", decay=0.9
        )
        params = model.get_params()
        assert params == {
            "window_size": 14,
            "weight_strategy": "exponential",
            "decay": 0.9,
            "random_state": 42,
        }
        model.set_params(window_size=7)
        assert model.window_size == 7

    def test_factory_creates_weighted_moving_average(self) -> None:
        """model_factory dispatches WeightedMovingAverageModelConfig."""
        cfg = WeightedMovingAverageModelConfig(
            window_size=10, weight_strategy="exponential", decay=0.6
        )
        model = model_factory(cfg, random_state=123)
        assert isinstance(model, WeightedMovingAverageForecaster)
        assert model.window_size == 10
        assert model.weight_strategy == "exponential"
        assert model.decay == 0.6
        assert model.random_state == 123
