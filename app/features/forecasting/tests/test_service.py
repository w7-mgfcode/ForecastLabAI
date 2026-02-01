"""Tests for forecasting service."""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.features.forecasting.models import NaiveForecaster, model_factory
from app.features.forecasting.persistence import ModelBundle, save_model_bundle
from app.features.forecasting.schemas import (
    MovingAverageModelConfig,
    NaiveModelConfig,
    SeasonalNaiveModelConfig,
)
from app.features.forecasting.service import ForecastingService, TrainingData


class TestTrainingData:
    """Tests for TrainingData dataclass."""

    def test_n_observations_computed(self):
        """Test that n_observations is computed from y."""
        data = TrainingData(
            y=np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
            dates=[date(2024, 1, i) for i in range(1, 6)],
            store_id=1,
            product_id=2,
        )

        assert data.n_observations == 5

    def test_empty_data(self):
        """Test empty training data."""
        data = TrainingData(
            y=np.array([], dtype=np.float64),
            dates=[],
            store_id=1,
            product_id=1,
        )

        assert data.n_observations == 0


class TestModelFactory:
    """Tests for model_factory function."""

    def test_naive_config_creates_naive_forecaster(self):
        """Test that naive config creates NaiveForecaster."""
        config = NaiveModelConfig()
        model = model_factory(config, random_state=42)

        assert isinstance(model, NaiveForecaster)
        assert model.random_state == 42

    def test_seasonal_config_creates_seasonal_forecaster(self):
        """Test that seasonal_naive config creates SeasonalNaiveForecaster."""
        config = SeasonalNaiveModelConfig(season_length=14)
        model = model_factory(config, random_state=42)

        from app.features.forecasting.models import SeasonalNaiveForecaster

        assert isinstance(model, SeasonalNaiveForecaster)
        assert model.season_length == 14

    def test_mavg_config_creates_mavg_forecaster(self):
        """Test that moving_average config creates MovingAverageForecaster."""
        config = MovingAverageModelConfig(window_size=21)
        model = model_factory(config, random_state=42)

        from app.features.forecasting.models import MovingAverageForecaster

        assert isinstance(model, MovingAverageForecaster)
        assert model.window_size == 21


class TestForecastingServicePredict:
    """Tests for ForecastingService.predict method."""

    @pytest.fixture
    def saved_model_path(self, sample_naive_config, sample_time_series):
        """Create a saved model for prediction tests."""
        with TemporaryDirectory() as tmpdir:
            model = NaiveForecaster()
            model.fit(sample_time_series)

            bundle = ModelBundle(
                model=model,
                config=sample_naive_config,
                metadata={
                    "store_id": 1,
                    "product_id": 2,
                    "train_end_date": "2024-01-31",
                },
            )

            path = Path(tmpdir) / "test_model"
            saved = save_model_bundle(bundle, path)
            yield str(saved)

    @pytest.mark.asyncio
    async def test_predict_returns_correct_horizon(self, saved_model_path):
        """Test that predict returns correct number of forecast points."""
        service = ForecastingService()

        response = await service.predict(
            store_id=1,
            product_id=2,
            horizon=7,
            model_path=saved_model_path,
        )

        assert len(response.forecasts) == 7
        assert response.horizon == 7

    @pytest.mark.asyncio
    async def test_predict_validates_store_id(self, saved_model_path):
        """Test that predict validates store_id matches model."""
        service = ForecastingService()

        with pytest.raises(ValueError, match="store=1"):
            await service.predict(
                store_id=999,  # Wrong store
                product_id=2,
                horizon=7,
                model_path=saved_model_path,
            )

    @pytest.mark.asyncio
    async def test_predict_validates_product_id(self, saved_model_path):
        """Test that predict validates product_id matches model."""
        service = ForecastingService()

        with pytest.raises(ValueError, match="product=2"):
            await service.predict(
                store_id=1,
                product_id=999,  # Wrong product
                horizon=7,
                model_path=saved_model_path,
            )

    @pytest.mark.asyncio
    async def test_predict_file_not_found(self):
        """Test that predict raises for missing model file."""
        service = ForecastingService()

        with pytest.raises(FileNotFoundError):
            await service.predict(
                store_id=1,
                product_id=1,
                horizon=7,
                model_path="/nonexistent/model.joblib",
            )

    @pytest.mark.asyncio
    async def test_predict_forecast_dates(self, saved_model_path):
        """Test that predict generates correct forecast dates."""
        service = ForecastingService()

        response = await service.predict(
            store_id=1,
            product_id=2,
            horizon=3,
            model_path=saved_model_path,
        )

        # Train end date was 2024-01-31, so forecasts start 2024-02-01
        assert response.forecasts[0].date == date(2024, 2, 1)
        assert response.forecasts[1].date == date(2024, 2, 2)
        assert response.forecasts[2].date == date(2024, 2, 3)

    @pytest.mark.asyncio
    async def test_predict_includes_model_type(self, saved_model_path):
        """Test that predict response includes model type."""
        service = ForecastingService()

        response = await service.predict(
            store_id=1,
            product_id=2,
            horizon=7,
            model_path=saved_model_path,
        )

        assert response.model_type == "naive"

    @pytest.mark.asyncio
    async def test_predict_includes_config_hash(self, saved_model_path):
        """Test that predict response includes config hash."""
        service = ForecastingService()

        response = await service.predict(
            store_id=1,
            product_id=2,
            horizon=7,
            model_path=saved_model_path,
        )

        assert response.config_hash is not None
        assert len(response.config_hash) == 16


class TestForecastingServiceTrain:
    """Tests for ForecastingService.train_model method."""

    @pytest.mark.asyncio
    async def test_train_empty_data_raises(self):
        """Test that training with no data raises ValueError."""
        service = ForecastingService()

        # Mock database session that returns empty result
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="No training data"):
            await service.train_model(
                db=mock_db,
                store_id=1,
                product_id=1,
                train_start_date=date(2024, 1, 1),
                train_end_date=date(2024, 1, 31),
                config=NaiveModelConfig(),
            )

    @pytest.mark.asyncio
    async def test_train_returns_model_path(self):
        """Test that training returns a valid model path."""
        service = ForecastingService()

        # Mock database session with sample data
        mock_db = AsyncMock()
        mock_result = MagicMock()

        # Create mock rows
        mock_rows = []
        for i in range(30):
            row = MagicMock()
            row.date = date(2024, 1, i + 1)
            row.quantity = float(i + 1)
            mock_rows.append(row)

        mock_result.all.return_value = mock_rows
        mock_db.execute.return_value = mock_result

        with TemporaryDirectory() as tmpdir:
            with patch("app.features.forecasting.service.get_settings") as mock_settings:
                settings = MagicMock()
                settings.forecast_random_seed = 42
                settings.forecast_model_artifacts_dir = tmpdir
                mock_settings.return_value = settings

                response = await service.train_model(
                    db=mock_db,
                    store_id=1,
                    product_id=2,
                    train_start_date=date(2024, 1, 1),
                    train_end_date=date(2024, 1, 30),
                    config=NaiveModelConfig(),
                )

                assert response.model_path.endswith(".joblib")
                assert Path(response.model_path).exists()
                assert response.n_observations == 30
                assert response.model_type == "naive"
