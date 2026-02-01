"""Forecasting service for model training and prediction.

Orchestrates:
- Loading training data from database
- Model instantiation via factory
- Training and prediction
- Model persistence via ModelBundle

CRITICAL: All operations respect time-safety constraints.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.data_platform.models import SalesDaily
from app.features.forecasting.models import model_factory
from app.features.forecasting.persistence import (
    ModelBundle,
    load_model_bundle,
    save_model_bundle,
)
from app.features.forecasting.schemas import (
    ForecastPoint,
    ModelConfig,
    PredictResponse,
    TrainResponse,
)

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


@dataclass
class TrainingData:
    """Container for loaded training data.

    Attributes:
        y: Target values as numpy array.
        dates: Corresponding dates.
        store_id: Store ID.
        product_id: Product ID.
        n_observations: Number of observations.
    """

    y: np.ndarray[Any, np.dtype[np.floating[Any]]]
    dates: list[date_type]
    store_id: int
    product_id: int
    n_observations: int = field(init=False)

    def __post_init__(self) -> None:
        """Compute derived fields."""
        self.n_observations = len(self.y)


class ForecastingService:
    """Service for training and predicting with forecasting models.

    Provides orchestration layer for:
    - Loading training data from database
    - Training models with configured parameters
    - Saving trained models as bundles
    - Loading models and generating predictions

    CRITICAL: All operations use Settings for reproducibility.
    """

    def __init__(self) -> None:
        """Initialize the forecasting service."""
        self.settings = get_settings()

    async def train_model(
        self,
        db: AsyncSession,
        store_id: int,
        product_id: int,
        train_start_date: date_type,
        train_end_date: date_type,
        config: ModelConfig,
    ) -> TrainResponse:
        """Train a forecasting model and save to disk.

        Args:
            db: Database session.
            store_id: Store ID to train for.
            product_id: Product ID to train for.
            train_start_date: Start date of training period.
            train_end_date: End date of training period (inclusive).
            config: Model configuration.

        Returns:
            TrainResponse with training results.

        Raises:
            ValueError: If insufficient training data.
        """
        start_time = time.perf_counter()

        logger.info(
            "forecasting.train_started",
            store_id=store_id,
            product_id=product_id,
            train_start_date=str(train_start_date),
            train_end_date=str(train_end_date),
            model_type=config.model_type,
            config_hash=config.config_hash(),
        )

        # Load training data
        training_data = await self._load_training_data(
            db=db,
            store_id=store_id,
            product_id=product_id,
            start_date=train_start_date,
            end_date=train_end_date,
        )

        if training_data.n_observations == 0:
            raise ValueError(
                f"No training data found for store={store_id}, product={product_id} "
                f"between {train_start_date} and {train_end_date}"
            )

        # Create and fit model
        model = model_factory(config, random_state=self.settings.forecast_random_seed)
        model.fit(training_data.y)

        # Create bundle with metadata
        bundle = ModelBundle(
            model=model,
            config=config,
            metadata={
                "store_id": store_id,
                "product_id": product_id,
                "train_start_date": str(train_start_date),
                "train_end_date": str(train_end_date),
                "n_observations": training_data.n_observations,
            },
        )

        # Save bundle
        model_id = uuid.uuid4().hex[:12]
        model_path = Path(self.settings.forecast_model_artifacts_dir) / f"model_{model_id}"
        saved_path = save_model_bundle(bundle, model_path)

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "forecasting.train_completed",
            store_id=store_id,
            product_id=product_id,
            model_type=config.model_type,
            config_hash=config.config_hash(),
            n_observations=training_data.n_observations,
            model_path=str(saved_path),
            duration_ms=duration_ms,
        )

        return TrainResponse(
            store_id=store_id,
            product_id=product_id,
            model_type=config.model_type,
            model_path=str(saved_path),
            config_hash=config.config_hash(),
            n_observations=training_data.n_observations,
            train_start_date=train_start_date,
            train_end_date=train_end_date,
            duration_ms=duration_ms,
        )

    async def predict(
        self,
        store_id: int,
        product_id: int,
        horizon: int,
        model_path: str,
    ) -> PredictResponse:
        """Generate forecasts using a saved model.

        Args:
            store_id: Store ID to predict for.
            product_id: Product ID to predict for.
            horizon: Number of days to forecast.
            model_path: Path to saved model bundle.

        Returns:
            PredictResponse with forecasts.

        Raises:
            FileNotFoundError: If model bundle not found.
            ValueError: If model was trained for different store/product.
        """
        start_time = time.perf_counter()

        logger.info(
            "forecasting.predict_started",
            store_id=store_id,
            product_id=product_id,
            horizon=horizon,
            model_path=model_path,
        )

        # Security: Validate model_path before loading
        # Resolve to absolute path and validate extension and location
        resolved_path = Path(model_path).resolve()
        artifacts_dir = Path(self.settings.forecast_model_artifacts_dir).resolve()

        # Check for .joblib extension
        if resolved_path.suffix != ".joblib":
            logger.warning(
                "forecasting.predict_rejected",
                model_path=model_path,
                resolved_path=str(resolved_path),
                reason="invalid_extension",
            )
            raise ValueError(
                f"Invalid model path: '{model_path}'. Model files must have .joblib extension."
            )

        # Check path is within artifacts directory
        try:
            resolved_path.relative_to(artifacts_dir)
        except ValueError:
            logger.warning(
                "forecasting.predict_rejected",
                model_path=model_path,
                resolved_path=str(resolved_path),
                artifacts_dir=str(artifacts_dir),
                reason="path_traversal_attempt",
            )
            raise ValueError(
                f"Invalid model path: '{model_path}'. "
                f"Model path must be within the configured artifacts directory: '{artifacts_dir}'."
            ) from None

        # Load model bundle (path already validated)
        bundle = load_model_bundle(resolved_path)

        # Validate store/product match
        bundle_store_id = bundle.metadata.get("store_id")
        bundle_product_id = bundle.metadata.get("product_id")

        if bundle_store_id != store_id:
            raise ValueError(
                f"Model was trained for store={bundle_store_id}, "
                f"but prediction requested for store={store_id}"
            )

        if bundle_product_id != product_id:
            raise ValueError(
                f"Model was trained for product={bundle_product_id}, "
                f"but prediction requested for product={product_id}"
            )

        # Generate forecasts
        forecasts_array = bundle.model.predict(horizon)

        # Get the training end date to compute forecast dates
        train_end_date_str = bundle.metadata.get("train_end_date")
        if isinstance(train_end_date_str, str):
            train_end_date = date_type.fromisoformat(train_end_date_str)
        else:
            # Default to today if not stored
            train_end_date = datetime.now(UTC).date()

        # Create forecast points
        forecasts: list[ForecastPoint] = []
        for h in range(horizon):
            forecast_date = train_end_date + timedelta(days=h + 1)
            forecasts.append(
                ForecastPoint(
                    date=forecast_date,
                    forecast=float(forecasts_array[h]),
                )
            )

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "forecasting.predict_completed",
            store_id=store_id,
            product_id=product_id,
            horizon=horizon,
            model_type=bundle.config.model_type,
            config_hash=bundle.config.config_hash(),
            duration_ms=duration_ms,
        )

        return PredictResponse(
            store_id=store_id,
            product_id=product_id,
            forecasts=forecasts,
            model_type=bundle.config.model_type,
            config_hash=bundle.config.config_hash(),
            horizon=horizon,
            duration_ms=duration_ms,
        )

    async def _load_training_data(
        self,
        db: AsyncSession,
        store_id: int,
        product_id: int,
        start_date: date_type,
        end_date: date_type,
    ) -> TrainingData:
        """Load training data from database.

        Args:
            db: Database session.
            store_id: Store ID.
            product_id: Product ID.
            start_date: Start date (inclusive).
            end_date: End date (inclusive).

        Returns:
            TrainingData container with loaded data.
        """
        stmt = (
            select(
                SalesDaily.date,
                SalesDaily.quantity,
            )
            .where(
                (SalesDaily.store_id == store_id)
                & (SalesDaily.product_id == product_id)
                & (SalesDaily.date >= start_date)
                & (SalesDaily.date <= end_date)
            )
            .order_by(SalesDaily.date)
        )

        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            return TrainingData(
                y=np.array([], dtype=np.float64),
                dates=[],
                store_id=store_id,
                product_id=product_id,
            )

        dates = [row.date for row in rows]
        y = np.array([float(row.quantity) for row in rows], dtype=np.float64)

        return TrainingData(
            y=y,
            dates=dates,
            store_id=store_id,
            product_id=product_id,
        )
