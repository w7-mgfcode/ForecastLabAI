"""Forecasting tools for agent interaction with the forecasting service.

Provides PydanticAI-compatible tool functions for:
- Training forecasting models
- Generating predictions with trained models

CRITICAL: Respects time-safety constraints and Settings limits.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.forecasting.schemas import (
    ModelConfig,
    MovingAverageModelConfig,
    NaiveModelConfig,
    PredictResponse,
    SeasonalNaiveModelConfig,
    TrainResponse,
)
from app.features.forecasting.service import ForecastingService

logger = structlog.get_logger()


def _create_model_config(
    model_type: str,
    season_length: int | None = None,
) -> ModelConfig:
    """Create model configuration from type string.

    Args:
        model_type: Type of model ('naive', 'seasonal_naive', 'linear_regression').
        season_length: Season length for seasonal models (default 7 for weekly).

    Returns:
        Configured ModelConfig instance.

    Raises:
        ValueError: If model_type is not supported.
    """
    if model_type == "naive":
        return NaiveModelConfig()
    elif model_type == "seasonal_naive":
        return SeasonalNaiveModelConfig(season_length=season_length or 7)
    elif model_type == "moving_average":
        return MovingAverageModelConfig()
    else:
        raise ValueError(
            f"Unsupported model type: {model_type}. "
            f"Supported: naive, seasonal_naive, moving_average"
        )


async def train_model(
    db: AsyncSession,
    store_id: int,
    product_id: int,
    train_start_date: date,
    train_end_date: date,
    model_type: str = "naive",
    season_length: int | None = None,
) -> dict[str, Any]:
    """Train a forecasting model and save it to disk.

    Use this tool to train a new model on historical data. The trained model
    is saved as a bundle and can be used for predictions.

    Args:
        db: Database session (injected via agent context).
        store_id: Store ID to train for.
        product_id: Product ID to train for.
        train_start_date: Start date of training data (YYYY-MM-DD).
        train_end_date: End date of training data (YYYY-MM-DD).
        model_type: Model to train ('naive', 'seasonal_naive', 'moving_average').
        season_length: Season length for seasonal models (default 7 for weekly).

    Returns:
        TrainResponse with model path and training statistics.

    Example:
        # Train a seasonal naive model
        result = await train_model(
            db,
            store_id=1,
            product_id=101,
            train_start_date=date(2024, 1, 1),
            train_end_date=date(2024, 6, 30),
            model_type='seasonal_naive',
            season_length=7,
        )
    """
    logger.info(
        "agents.forecasting_tool.train_model_called",
        store_id=store_id,
        product_id=product_id,
        train_start_date=str(train_start_date),
        train_end_date=str(train_end_date),
        model_type=model_type,
    )

    # Create model configuration
    model_config = _create_model_config(model_type, season_length)

    # Train model
    service = ForecastingService()
    result: TrainResponse = await service.train_model(
        db=db,
        store_id=store_id,
        product_id=product_id,
        train_start_date=train_start_date,
        train_end_date=train_end_date,
        config=model_config,
    )

    logger.info(
        "agents.forecasting_tool.train_model_completed",
        store_id=store_id,
        product_id=product_id,
        model_type=model_type,
        model_path=result.model_path,
        n_observations=result.n_observations,
        duration_ms=result.duration_ms,
    )

    return result.model_dump()


async def predict(
    store_id: int,
    product_id: int,
    horizon: int,
    model_path: str,
) -> dict[str, Any]:
    """Generate forecasts using a trained model.

    Use this tool to generate predictions for future dates using a previously
    trained model. The model must have been trained for the same store/product.

    Args:
        store_id: Store ID to predict for.
        product_id: Product ID to predict for.
        horizon: Number of days to forecast (default max from settings).
        model_path: Path to the saved model bundle (.joblib file).

    Returns:
        PredictResponse with forecast points.

    Example:
        # Generate 14-day forecast
        result = await predict(
            store_id=1,
            product_id=101,
            horizon=14,
            model_path='./artifacts/models/model_abc123.joblib',
        )
    """
    logger.info(
        "agents.forecasting_tool.predict_called",
        store_id=store_id,
        product_id=product_id,
        horizon=horizon,
        model_path=model_path,
    )

    # Generate predictions
    service = ForecastingService()
    result: PredictResponse = await service.predict(
        store_id=store_id,
        product_id=product_id,
        horizon=horizon,
        model_path=model_path,
    )

    logger.info(
        "agents.forecasting_tool.predict_completed",
        store_id=store_id,
        product_id=product_id,
        horizon=horizon,
        model_type=result.model_type,
        duration_ms=result.duration_ms,
    )

    return result.model_dump()
