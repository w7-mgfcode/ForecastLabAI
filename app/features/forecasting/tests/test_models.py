"""Tests for forecasting models."""

import numpy as np
import pytest

from app.features.forecasting.models import (
    MovingAverageForecaster,
    NaiveForecaster,
    SeasonalNaiveForecaster,
    model_factory,
)


class TestNaiveForecaster:
    """Tests for NaiveForecaster."""

    def test_fit_stores_last_value(self, sample_time_series):
        """Test that fit stores the last value correctly."""
        model = NaiveForecaster()
        model.fit(sample_time_series)

        assert model.is_fitted
        assert model._last_value == 60.0  # Last value in 1-60 sequence

    def test_predict_repeats_last_value(self, sample_time_series):
        """Test that predict repeats the last value for all horizons."""
        model = NaiveForecaster()
        model.fit(sample_time_series)

        forecasts = model.predict(horizon=7)

        assert len(forecasts) == 7
        assert all(f == 60.0 for f in forecasts)

    def test_predict_before_fit_raises(self):
        """Test that predict before fit raises RuntimeError."""
        model = NaiveForecaster()

        with pytest.raises(RuntimeError, match="must be fitted"):
            model.predict(horizon=5)

    def test_fit_empty_array_raises(self):
        """Test that fitting on empty array raises ValueError."""
        model = NaiveForecaster()
        empty = np.array([], dtype=np.float64)

        with pytest.raises(ValueError, match="empty"):
            model.fit(empty)

    def test_determinism(self, sample_time_series):
        """Test that model is deterministic."""
        model1 = NaiveForecaster(random_state=42)
        model2 = NaiveForecaster(random_state=42)

        model1.fit(sample_time_series)
        model2.fit(sample_time_series)

        forecasts1 = model1.predict(horizon=10)
        forecasts2 = model2.predict(horizon=10)

        np.testing.assert_array_equal(forecasts1, forecasts2)

    def test_get_params(self):
        """Test get_params returns expected values."""
        model = NaiveForecaster(random_state=123)
        params = model.get_params()

        assert params == {"random_state": 123}

    def test_set_params(self):
        """Test set_params modifies model."""
        model = NaiveForecaster(random_state=42)
        model.set_params(random_state=99)

        assert model.random_state == 99


class TestSeasonalNaiveForecaster:
    """Tests for SeasonalNaiveForecaster."""

    def test_fit_stores_seasonal_values(self, sample_seasonal_series):
        """Test that fit stores the last season_length values."""
        model = SeasonalNaiveForecaster(season_length=7)
        model.fit(sample_seasonal_series)

        assert model.is_fitted
        # Last 7 values of the pattern
        expected = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0])
        np.testing.assert_array_equal(model._last_values, expected)

    def test_predict_cycles_seasonal_pattern(self, sample_seasonal_series):
        """Test that predict cycles through seasonal values."""
        model = SeasonalNaiveForecaster(season_length=7)
        model.fit(sample_seasonal_series)

        # Predict 14 days (2 full cycles)
        forecasts = model.predict(horizon=14)

        expected = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0] * 2)
        np.testing.assert_array_equal(forecasts, expected)

    def test_predict_partial_cycle(self, sample_seasonal_series):
        """Test prediction for partial seasonal cycle."""
        model = SeasonalNaiveForecaster(season_length=7)
        model.fit(sample_seasonal_series)

        forecasts = model.predict(horizon=3)

        expected = np.array([10.0, 20.0, 30.0])
        np.testing.assert_array_equal(forecasts, expected)

    def test_insufficient_data_raises(self):
        """Test that insufficient data raises ValueError."""
        model = SeasonalNaiveForecaster(season_length=7)
        short_data = np.array([1.0, 2.0, 3.0])  # Only 3 observations

        with pytest.raises(ValueError, match="at least 7"):
            model.fit(short_data)

    def test_invalid_season_length_raises(self):
        """Test that season_length < 1 raises ValueError on construction."""
        with pytest.raises(ValueError, match="season_length must be >= 1"):
            SeasonalNaiveForecaster(season_length=0)

        with pytest.raises(ValueError, match="season_length must be >= 1"):
            SeasonalNaiveForecaster(season_length=-5)

    def test_get_params(self):
        """Test get_params returns expected values."""
        model = SeasonalNaiveForecaster(season_length=14, random_state=42)
        params = model.get_params()

        assert params == {"season_length": 14, "random_state": 42}

    def test_set_params(self):
        """Test set_params modifies model."""
        model = SeasonalNaiveForecaster(season_length=7)
        model.set_params(season_length=30)

        assert model.season_length == 30


class TestMovingAverageForecaster:
    """Tests for MovingAverageForecaster."""

    def test_fit_computes_window_mean(self, sample_constant_series):
        """Test that fit computes mean of last window_size values."""
        model = MovingAverageForecaster(window_size=7)
        model.fit(sample_constant_series)

        assert model.is_fitted
        assert model._forecast_value == 100.0  # Mean of constant series

    def test_predict_returns_constant(self, sample_constant_series):
        """Test that predict returns same value for all horizons."""
        model = MovingAverageForecaster(window_size=7)
        model.fit(sample_constant_series)

        forecasts = model.predict(horizon=14)

        assert len(forecasts) == 14
        assert all(f == 100.0 for f in forecasts)

    def test_moving_average_calculation(self, sample_time_series):
        """Test moving average is calculated correctly."""
        model = MovingAverageForecaster(window_size=7)
        model.fit(sample_time_series)

        # Last 7 values: 54, 55, 56, 57, 58, 59, 60
        # Mean: (54 + 55 + 56 + 57 + 58 + 59 + 60) / 7 = 57.0
        expected_mean = 57.0

        forecasts = model.predict(horizon=3)
        assert all(f == expected_mean for f in forecasts)

    def test_insufficient_data_raises(self):
        """Test that insufficient data raises ValueError."""
        model = MovingAverageForecaster(window_size=7)
        short_data = np.array([1.0, 2.0, 3.0])

        with pytest.raises(ValueError, match="at least 7"):
            model.fit(short_data)

    def test_invalid_window_size_raises(self):
        """Test that window_size < 1 raises ValueError on construction."""
        with pytest.raises(ValueError, match="window_size must be >= 1"):
            MovingAverageForecaster(window_size=0)

        with pytest.raises(ValueError, match="window_size must be >= 1"):
            MovingAverageForecaster(window_size=-3)

    def test_get_params(self):
        """Test get_params returns expected values."""
        model = MovingAverageForecaster(window_size=14, random_state=42)
        params = model.get_params()

        assert params == {"window_size": 14, "random_state": 42}


class TestModelFactory:
    """Tests for model_factory function."""

    def test_factory_creates_naive(self, sample_naive_config):
        """Test factory creates NaiveForecaster for naive config."""
        model = model_factory(sample_naive_config, random_state=42)

        assert isinstance(model, NaiveForecaster)
        assert model.random_state == 42

    def test_factory_creates_seasonal_naive(self, sample_seasonal_config):
        """Test factory creates SeasonalNaiveForecaster for seasonal_naive config."""
        model = model_factory(sample_seasonal_config, random_state=42)

        assert isinstance(model, SeasonalNaiveForecaster)
        assert model.season_length == 7

    def test_factory_creates_moving_average(self, sample_mavg_config):
        """Test factory creates MovingAverageForecaster for moving_average config."""
        model = model_factory(sample_mavg_config, random_state=42)

        assert isinstance(model, MovingAverageForecaster)
        assert model.window_size == 7


class TestBaseForecasterInterface:
    """Tests for BaseForecaster interface compliance."""

    @pytest.mark.parametrize(
        "model_class",
        [NaiveForecaster, SeasonalNaiveForecaster, MovingAverageForecaster],
    )
    def test_is_fitted_property(self, model_class):
        """Test is_fitted property for all models."""
        if model_class == SeasonalNaiveForecaster:
            model = model_class(season_length=7)
        elif model_class == MovingAverageForecaster:
            model = model_class(window_size=7)
        else:
            model = model_class()

        assert not model.is_fitted

        data = np.arange(1, 31, dtype=np.float64)
        model.fit(data)

        assert model.is_fitted

    @pytest.mark.parametrize(
        "model_class",
        [NaiveForecaster, SeasonalNaiveForecaster, MovingAverageForecaster],
    )
    def test_fit_returns_self(self, model_class):
        """Test that fit returns self for method chaining."""
        if model_class == SeasonalNaiveForecaster:
            model = model_class(season_length=7)
        elif model_class == MovingAverageForecaster:
            model = model_class(window_size=7)
        else:
            model = model_class()

        data = np.arange(1, 31, dtype=np.float64)
        result = model.fit(data)

        assert result is model

    @pytest.mark.parametrize(
        "model_class",
        [NaiveForecaster, SeasonalNaiveForecaster, MovingAverageForecaster],
    )
    def test_predict_returns_correct_shape(self, model_class):
        """Test that predict returns array of correct shape."""
        if model_class == SeasonalNaiveForecaster:
            model = model_class(season_length=7)
        elif model_class == MovingAverageForecaster:
            model = model_class(window_size=7)
        else:
            model = model_class()

        data = np.arange(1, 31, dtype=np.float64)
        model.fit(data)

        for horizon in [1, 7, 14, 30]:
            forecasts = model.predict(horizon)
            assert forecasts.shape == (horizon,)
