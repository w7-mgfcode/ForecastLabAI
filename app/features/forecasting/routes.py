"""Forecasting API routes for model training and prediction."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import DatabaseError
from app.core.logging import get_logger
from app.features.forecasting.schemas import (
    PredictRequest,
    PredictResponse,
    TrainRequest,
    TrainResponse,
)
from app.features.forecasting.service import ForecastingService

logger = get_logger(__name__)

router = APIRouter(prefix="/forecasting", tags=["forecasting"])


@router.post(
    "/train",
    response_model=TrainResponse,
    status_code=status.HTTP_200_OK,
    summary="Train a forecasting model",
    description="""
Train a forecasting model for a single store/product series.

**Model Types:**
- `naive`: Predicts last observed value for all horizons
- `seasonal_naive`: Predicts value from same season in previous cycle
- `moving_average`: Predicts mean of last N observations
- `lightgbm`: LightGBM regressor (feature-flagged, disabled by default)

**Persistence:** Trained models are saved as ModelBundle files containing:
- The fitted model
- Configuration used for training
- Metadata (store_id, product_id, dates, n_observations)
- Version information for compatibility checking

**Response:** Returns the path to the saved model bundle for use in prediction.
""",
)
async def train_model(
    request: TrainRequest,
    db: AsyncSession = Depends(get_db),
) -> TrainResponse:
    """Train a forecasting model for a single series.

    Args:
        request: Training request with config.
        db: Async database session from dependency.

    Returns:
        Response with training results and model path.

    Raises:
        HTTPException: If model type is disabled or training fails.
        NotFoundError: If no training data found.
        DatabaseError: If database operation fails.
    """
    settings = get_settings()

    # Check if LightGBM is enabled
    if request.config.model_type == "lightgbm" and not settings.forecast_enable_lightgbm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LightGBM is disabled. Set forecast_enable_lightgbm=True in settings.",
        )

    logger.info(
        "forecasting.train_request_received",
        store_id=request.store_id,
        product_id=request.product_id,
        train_start_date=str(request.train_start_date),
        train_end_date=str(request.train_end_date),
        model_type=request.config.model_type,
    )

    service = ForecastingService()

    try:
        response = await service.train_model(
            db=db,
            store_id=request.store_id,
            product_id=request.product_id,
            train_start_date=request.train_start_date,
            train_end_date=request.train_end_date,
            config=request.config,
        )

        logger.info(
            "forecasting.train_request_completed",
            store_id=request.store_id,
            product_id=request.product_id,
            model_type=request.config.model_type,
            model_path=response.model_path,
            n_observations=response.n_observations,
            duration_ms=response.duration_ms,
        )

        return response

    except ValueError as e:
        logger.warning(
            "forecasting.train_request_failed",
            store_id=request.store_id,
            product_id=request.product_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except SQLAlchemyError as e:
        logger.error(
            "forecasting.train_request_failed",
            store_id=request.store_id,
            product_id=request.product_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise DatabaseError(
            message="Failed to train model",
            details={"error": str(e)},
        ) from e


@router.post(
    "/predict",
    response_model=PredictResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate forecasts using a trained model",
    description="""
Generate forecasts using a previously trained model.

**Inputs:**
- `store_id`, `product_id`: Must match the model's training data
- `horizon`: Number of days to forecast (1-90)
- `model_path`: Path to saved model bundle

**Forecast Points:** Each point includes:
- `date`: Forecast date
- `forecast`: Point forecast value
- `lower_bound`, `upper_bound`: Prediction intervals (optional, model-dependent)

**Validation:** The service validates that the model was trained for the
requested store/product combination.
""",
)
async def predict(
    request: PredictRequest,
    db: AsyncSession = Depends(get_db),  # noqa: ARG001
) -> PredictResponse:
    """Generate forecasts using a saved model.

    Args:
        request: Prediction request with model path and horizon.
        db: Async database session from dependency (unused but kept for consistency).

    Returns:
        Response with forecast points.

    Raises:
        HTTPException: If model not found or validation fails.
    """
    logger.info(
        "forecasting.predict_request_received",
        store_id=request.store_id,
        product_id=request.product_id,
        horizon=request.horizon,
        model_path=request.model_path,
    )

    service = ForecastingService()

    try:
        response = await service.predict(
            store_id=request.store_id,
            product_id=request.product_id,
            horizon=request.horizon,
            model_path=request.model_path,
        )

        logger.info(
            "forecasting.predict_request_completed",
            store_id=request.store_id,
            product_id=request.product_id,
            horizon=request.horizon,
            model_type=response.model_type,
            duration_ms=response.duration_ms,
        )

        return response

    except FileNotFoundError as e:
        logger.warning(
            "forecasting.predict_request_failed",
            store_id=request.store_id,
            product_id=request.product_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except ValueError as e:
        logger.warning(
            "forecasting.predict_request_failed",
            store_id=request.store_id,
            product_id=request.product_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
