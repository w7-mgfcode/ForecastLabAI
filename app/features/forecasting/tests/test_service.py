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
    def saved_model_context(self, sample_naive_config, sample_time_series):
        """Create a saved model for prediction tests with patched settings."""
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
            yield {"model_path": str(saved), "tmpdir": tmpdir}

    @pytest.mark.asyncio
    async def test_predict_returns_correct_horizon(self, saved_model_context):
        """Test that predict returns correct number of forecast points."""
        with patch("app.features.forecasting.service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.forecast_model_artifacts_dir = saved_model_context["tmpdir"]
            mock_settings.return_value = settings

            service = ForecastingService()

            response = await service.predict(
                store_id=1,
                product_id=2,
                horizon=7,
                model_path=saved_model_context["model_path"],
            )

            assert len(response.forecasts) == 7
            assert response.horizon == 7

    @pytest.mark.asyncio
    async def test_predict_validates_store_id(self, saved_model_context):
        """Test that predict validates store_id matches model."""
        with patch("app.features.forecasting.service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.forecast_model_artifacts_dir = saved_model_context["tmpdir"]
            mock_settings.return_value = settings

            service = ForecastingService()

            with pytest.raises(ValueError, match="store=1"):
                await service.predict(
                    store_id=999,  # Wrong store
                    product_id=2,
                    horizon=7,
                    model_path=saved_model_context["model_path"],
                )

    @pytest.mark.asyncio
    async def test_predict_validates_product_id(self, saved_model_context):
        """Test that predict validates product_id matches model."""
        with patch("app.features.forecasting.service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.forecast_model_artifacts_dir = saved_model_context["tmpdir"]
            mock_settings.return_value = settings

            service = ForecastingService()

            with pytest.raises(ValueError, match="product=2"):
                await service.predict(
                    store_id=1,
                    product_id=999,  # Wrong product
                    horizon=7,
                    model_path=saved_model_context["model_path"],
                )

    @pytest.mark.asyncio
    async def test_predict_file_not_found(self):
        """Test that predict raises for missing model file."""
        with TemporaryDirectory() as tmpdir:
            with patch("app.features.forecasting.service.get_settings") as mock_settings:
                settings = MagicMock()
                settings.forecast_model_artifacts_dir = tmpdir
                mock_settings.return_value = settings

                service = ForecastingService()

                # Path must be inside artifacts dir and have .joblib extension
                with pytest.raises(FileNotFoundError):
                    await service.predict(
                        store_id=1,
                        product_id=1,
                        horizon=7,
                        model_path=f"{tmpdir}/nonexistent/model.joblib",
                    )

    @pytest.mark.asyncio
    async def test_predict_forecast_dates(self, saved_model_context):
        """Test that predict generates correct forecast dates."""
        with patch("app.features.forecasting.service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.forecast_model_artifacts_dir = saved_model_context["tmpdir"]
            mock_settings.return_value = settings

            service = ForecastingService()

            response = await service.predict(
                store_id=1,
                product_id=2,
                horizon=3,
                model_path=saved_model_context["model_path"],
            )

            # Train end date was 2024-01-31, so forecasts start 2024-02-01
            assert response.forecasts[0].date == date(2024, 2, 1)
            assert response.forecasts[1].date == date(2024, 2, 2)
            assert response.forecasts[2].date == date(2024, 2, 3)

    @pytest.mark.asyncio
    async def test_predict_includes_model_type(self, saved_model_context):
        """Test that predict response includes model type."""
        with patch("app.features.forecasting.service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.forecast_model_artifacts_dir = saved_model_context["tmpdir"]
            mock_settings.return_value = settings

            service = ForecastingService()

            response = await service.predict(
                store_id=1,
                product_id=2,
                horizon=7,
                model_path=saved_model_context["model_path"],
            )

            assert response.model_type == "naive"

    @pytest.mark.asyncio
    async def test_predict_includes_config_hash(self, saved_model_context):
        """Test that predict response includes config hash."""
        with patch("app.features.forecasting.service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.forecast_model_artifacts_dir = saved_model_context["tmpdir"]
            mock_settings.return_value = settings

            service = ForecastingService()

            response = await service.predict(
                store_id=1,
                product_id=2,
                horizon=7,
                model_path=saved_model_context["model_path"],
            )

            assert response.config_hash is not None
            assert len(response.config_hash) == 16

    @pytest.mark.asyncio
    async def test_predict_rejects_path_traversal(self):
        """Test that predict rejects paths outside artifacts directory."""
        with TemporaryDirectory() as tmpdir:
            with patch("app.features.forecasting.service.get_settings") as mock_settings:
                settings = MagicMock()
                settings.forecast_model_artifacts_dir = tmpdir
                mock_settings.return_value = settings

                service = ForecastingService()

                # Try to load from outside the artifacts directory (with valid extension)
                with pytest.raises(ValueError, match="must be within the configured"):
                    await service.predict(
                        store_id=1,
                        product_id=1,
                        horizon=7,
                        model_path="/etc/malicious.joblib",
                    )

    @pytest.mark.asyncio
    async def test_predict_rejects_invalid_extension(self):
        """Test that predict rejects non-.joblib files."""
        with TemporaryDirectory() as tmpdir:
            with patch("app.features.forecasting.service.get_settings") as mock_settings:
                settings = MagicMock()
                settings.forecast_model_artifacts_dir = tmpdir
                mock_settings.return_value = settings

                service = ForecastingService()

                # Try to load a file without .joblib extension
                with pytest.raises(ValueError, match=r"\.joblib extension"):
                    await service.predict(
                        store_id=1,
                        product_id=1,
                        horizon=7,
                        model_path=f"{tmpdir}/model.pkl",
                    )


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
            # Patch get_settings BEFORE constructing ForecastingService
            with patch("app.features.forecasting.service.get_settings") as mock_settings:
                settings = MagicMock()
                settings.forecast_random_seed = 42
                settings.forecast_model_artifacts_dir = tmpdir
                mock_settings.return_value = settings

                # Now construct service with patched settings
                service = ForecastingService()

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


class TestFeatureAwareContract:
    """Tests for the feature-aware model contract (MLZOO-A / PRP-29)."""

    def test_requires_features_flag(self):
        """Baseline forecasters require no features; feature-aware ones do."""
        from app.features.forecasting.models import LightGBMForecaster, XGBoostForecaster
        from app.features.forecasting.schemas import RegressionModelConfig

        assert model_factory(NaiveModelConfig()).requires_features is False
        assert model_factory(SeasonalNaiveModelConfig()).requires_features is False
        assert model_factory(MovingAverageModelConfig()).requires_features is False
        assert model_factory(RegressionModelConfig()).requires_features is True
        # LightGBM is feature-aware too — assert the ClassVar directly so this
        # needs neither the factory flag nor the optional lightgbm dependency.
        assert LightGBMForecaster.requires_features is True
        # XGBoost is feature-aware too — same import-free ClassVar assertion.
        assert XGBoostForecaster.requires_features is True

    def test_lightgbm_factory_respects_flag(self):
        """model_factory gates LightGBM behind forecast_enable_lightgbm.

        Construction is flag-gated but import-free (``lightgbm`` is imported
        lazily inside ``fit``), so neither branch needs the optional extra.
        """
        from app.features.forecasting.models import LightGBMForecaster
        from app.features.forecasting.schemas import LightGBMModelConfig

        disabled = MagicMock()
        disabled.forecast_enable_lightgbm = False
        with (
            patch("app.core.config.get_settings", return_value=disabled),
            pytest.raises(ValueError, match="not enabled"),
        ):
            model_factory(LightGBMModelConfig())

        enabled = MagicMock()
        enabled.forecast_enable_lightgbm = True
        with patch("app.core.config.get_settings", return_value=enabled):
            model = model_factory(LightGBMModelConfig())
        assert isinstance(model, LightGBMForecaster)

    def test_xgboost_factory_respects_flag(self):
        """model_factory gates XGBoost behind forecast_enable_xgboost.

        Construction is flag-gated but import-free (``xgboost`` is imported
        lazily inside ``fit``), so neither branch needs the optional extra.
        """
        from app.features.forecasting.models import XGBoostForecaster
        from app.features.forecasting.schemas import XGBoostModelConfig

        disabled = MagicMock()
        disabled.forecast_enable_xgboost = False
        with (
            patch("app.core.config.get_settings", return_value=disabled),
            pytest.raises(ValueError, match="not enabled"),
        ):
            model_factory(XGBoostModelConfig())

        enabled = MagicMock()
        enabled.forecast_enable_xgboost = True
        with patch("app.core.config.get_settings", return_value=enabled):
            model = model_factory(XGBoostModelConfig())
        assert isinstance(model, XGBoostForecaster)

    def test_canonical_columns_match_regression_contract(self):
        """The canonical column set is the exact 14-name regression contract.

        Pins the contract after the local duplicated column-list constant
        was deleted in favour of the shared single source of truth.
        """
        from app.shared.feature_frames import canonical_feature_columns

        assert canonical_feature_columns() == [
            "lag_1",
            "lag_7",
            "lag_14",
            "lag_28",
            "dow_sin",
            "dow_cos",
            "month_sin",
            "month_cos",
            "is_weekend",
            "is_month_end",
            "price_factor",
            "promo_active",
            "is_holiday",
            "days_since_launch",
        ]
