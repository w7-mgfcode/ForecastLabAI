"""Tests for forecasting schemas."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.features.forecasting.schemas import (
    ForecastPoint,
    LightGBMModelConfig,
    MovingAverageModelConfig,
    NaiveModelConfig,
    PredictRequest,
    PredictResponse,
    SeasonalNaiveModelConfig,
    TrainRequest,
    TrainResponse,
)


class TestNaiveModelConfig:
    """Tests for NaiveModelConfig schema."""

    def test_default_values(self):
        """Test default configuration values."""
        config = NaiveModelConfig()
        assert config.model_type == "naive"
        assert config.schema_version == "1.0"

    def test_frozen_immutability(self):
        """Test that config is immutable (frozen=True)."""
        config = NaiveModelConfig()
        with pytest.raises(ValidationError):
            config.model_type = "other"  # type: ignore[assignment]

    def test_config_hash_determinism(self):
        """Test that config_hash is deterministic."""
        config1 = NaiveModelConfig(schema_version="1.0")
        config2 = NaiveModelConfig(schema_version="1.0")
        assert config1.config_hash() == config2.config_hash()

    def test_config_hash_changes_with_params(self):
        """Test that config_hash changes when params differ."""
        config1 = NaiveModelConfig(schema_version="1.0")
        config2 = NaiveModelConfig(schema_version="2.0")
        assert config1.config_hash() != config2.config_hash()


class TestSeasonalNaiveModelConfig:
    """Tests for SeasonalNaiveModelConfig schema."""

    def test_default_season_length(self):
        """Test default season length is 7 (weekly)."""
        config = SeasonalNaiveModelConfig()
        assert config.season_length == 7

    def test_custom_season_length(self):
        """Test custom season length."""
        config = SeasonalNaiveModelConfig(season_length=30)
        assert config.season_length == 30

    def test_season_length_validation_min(self):
        """Test season length minimum validation."""
        with pytest.raises(ValidationError):
            SeasonalNaiveModelConfig(season_length=0)

    def test_season_length_validation_max(self):
        """Test season length maximum validation."""
        with pytest.raises(ValidationError):
            SeasonalNaiveModelConfig(season_length=400)

    def test_config_hash_includes_season_length(self):
        """Test that config_hash includes season_length."""
        config1 = SeasonalNaiveModelConfig(season_length=7)
        config2 = SeasonalNaiveModelConfig(season_length=14)
        assert config1.config_hash() != config2.config_hash()


class TestMovingAverageModelConfig:
    """Tests for MovingAverageModelConfig schema."""

    def test_default_window_size(self):
        """Test default window size is 7."""
        config = MovingAverageModelConfig()
        assert config.window_size == 7

    def test_window_size_validation_min(self):
        """Test window size minimum validation."""
        with pytest.raises(ValidationError):
            MovingAverageModelConfig(window_size=0)

    def test_window_size_validation_max(self):
        """Test window size maximum validation."""
        with pytest.raises(ValidationError):
            MovingAverageModelConfig(window_size=100)

    def test_frozen_immutability(self):
        """Test that config is immutable."""
        config = MovingAverageModelConfig()
        with pytest.raises(ValidationError):
            config.window_size = 14


class TestLightGBMModelConfig:
    """Tests for LightGBMModelConfig schema."""

    def test_default_values(self):
        """Test default configuration values."""
        config = LightGBMModelConfig()
        assert config.model_type == "lightgbm"
        assert config.n_estimators == 100
        assert config.max_depth == 6
        assert config.learning_rate == 0.1
        assert config.feature_config_hash is None

    def test_parameter_validation(self):
        """Test parameter range validation."""
        # n_estimators too low
        with pytest.raises(ValidationError):
            LightGBMModelConfig(n_estimators=5)

        # max_depth too high
        with pytest.raises(ValidationError):
            LightGBMModelConfig(max_depth=25)

        # learning_rate too low
        with pytest.raises(ValidationError):
            LightGBMModelConfig(learning_rate=0.0001)


class TestTrainRequest:
    """Tests for TrainRequest schema."""

    def test_valid_request(self):
        """Test valid training request."""
        request = TrainRequest(
            store_id=1,
            product_id=2,
            train_start_date=date(2024, 1, 1),
            train_end_date=date(2024, 1, 31),
            config=NaiveModelConfig(),
        )
        assert request.store_id == 1
        assert request.product_id == 2

    def test_date_range_validation(self):
        """Test that train_end_date must be after train_start_date."""
        with pytest.raises(ValidationError):
            TrainRequest(
                store_id=1,
                product_id=1,
                train_start_date=date(2024, 1, 31),
                train_end_date=date(2024, 1, 1),
                config=NaiveModelConfig(),
            )

    def test_same_date_validation(self):
        """Test that train_end_date cannot equal train_start_date."""
        with pytest.raises(ValidationError):
            TrainRequest(
                store_id=1,
                product_id=1,
                train_start_date=date(2024, 1, 15),
                train_end_date=date(2024, 1, 15),
                config=NaiveModelConfig(),
            )

    def test_store_id_validation(self):
        """Test store_id must be positive."""
        with pytest.raises(ValidationError):
            TrainRequest(
                store_id=0,
                product_id=1,
                train_start_date=date(2024, 1, 1),
                train_end_date=date(2024, 1, 31),
                config=NaiveModelConfig(),
            )


class TestPredictRequest:
    """Tests for PredictRequest schema."""

    def test_valid_request(self):
        """Test valid prediction request."""
        request = PredictRequest(
            store_id=1,
            product_id=2,
            horizon=14,
            model_path="/path/to/model.joblib",
        )
        assert request.horizon == 14

    def test_horizon_validation_min(self):
        """Test horizon minimum validation."""
        with pytest.raises(ValidationError):
            PredictRequest(
                store_id=1,
                product_id=1,
                horizon=0,
                model_path="/path/to/model.joblib",
            )

    def test_horizon_validation_max(self):
        """Test horizon maximum validation."""
        with pytest.raises(ValidationError):
            PredictRequest(
                store_id=1,
                product_id=1,
                horizon=100,
                model_path="/path/to/model.joblib",
            )


class TestForecastPoint:
    """Tests for ForecastPoint schema."""

    def test_basic_forecast_point(self):
        """Test basic forecast point without bounds."""
        point = ForecastPoint(
            date=date(2024, 2, 1),
            forecast=100.5,
        )
        assert point.date == date(2024, 2, 1)
        assert point.forecast == 100.5
        assert point.lower_bound is None
        assert point.upper_bound is None

    def test_forecast_point_with_bounds(self):
        """Test forecast point with prediction intervals."""
        point = ForecastPoint(
            date=date(2024, 2, 1),
            forecast=100.0,
            lower_bound=80.0,
            upper_bound=120.0,
        )
        assert point.lower_bound == 80.0
        assert point.upper_bound == 120.0


class TestPredictResponse:
    """Tests for PredictResponse schema."""

    def test_valid_response(self):
        """Test valid prediction response."""
        response = PredictResponse(
            store_id=1,
            product_id=2,
            forecasts=[
                ForecastPoint(date=date(2024, 2, 1), forecast=100.0),
                ForecastPoint(date=date(2024, 2, 2), forecast=101.0),
            ],
            model_type="naive",
            config_hash="abc123def456",
            horizon=2,
            duration_ms=10.5,
        )
        assert len(response.forecasts) == 2
        assert response.horizon == 2


class TestTrainResponse:
    """Tests for TrainResponse schema."""

    def test_valid_response(self):
        """Test valid training response."""
        response = TrainResponse(
            store_id=1,
            product_id=2,
            model_type="naive",
            model_path="/artifacts/models/model_abc123.joblib",
            config_hash="abc123def456",
            n_observations=31,
            train_start_date=date(2024, 1, 1),
            train_end_date=date(2024, 1, 31),
            duration_ms=150.5,
        )
        assert response.n_observations == 31
        assert response.model_path.endswith(".joblib")
