"""Forecasting API routes for model training and prediction."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import BadRequestError, DatabaseError
from app.core.logging import get_logger
from app.features.forecasting.schemas import (
    FeatureMetadataResponse,
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
- `regression`: HistGradientBoostingRegressor over the canonical 14-column
  feature frame (always available; no optional extra)
- `lightgbm`: LightGBM regressor (feature-aware; requires the `ml-lightgbm`
  extra at install time AND `forecast_enable_lightgbm=True` at runtime)
- `xgboost`: XGBoost regressor (feature-aware; requires the `ml-xgboost`
  extra at install time AND `forecast_enable_xgboost=True` at runtime)
- `prophet_like`: Ridge-based additive forecaster — trend + seasonality +
  holiday-regressor decomposition (always available; pure scikit-learn)

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
        raise BadRequestError(
            message="LightGBM is disabled. Set forecast_enable_lightgbm=True in settings.",
        )

    # Check if XGBoost is enabled
    if request.config.model_type == "xgboost" and not settings.forecast_enable_xgboost:
        raise BadRequestError(
            message="XGBoost is disabled. Set forecast_enable_xgboost=True in settings.",
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


# ─── MLZOO-D / PRP-31 — feature-metadata endpoints ───────────────────────────
#
# Two sibling routes (run-keyed + job-keyed) that mirror PRP-28's
# /explain/runs/{run_id} + /explain/jobs/{job_id} shape exactly. Each returns
# the canonical 14-column feature frame the model consumed and its native
# feature_importances_ (tree) or coef_ (additive prophet_like). All error
# paths flow through ForecastLabError subclasses (NotFoundError 404,
# BadRequestError 400, UnprocessableEntityError 422) into
# forecastlab_exception_handler which serializes RFC 7807 problem+json — no
# bare HTTPException, no raw 500.


@router.get(
    "/runs/{run_id}/feature-metadata",
    response_model=FeatureMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract feature columns + learned importance for an advanced-model run",
    description="""
Returns the canonical 14-column feature frame the model consumed and the
fitted estimator's `feature_importances_` (tree models) or `coef_` (additive
prophet_like). Loads the saved joblib artifact lazily — the
`/registry/runs/{run_id}/verify` precedent for "load and inspect".

**Error semantics (RFC 7807 application/problem+json):**
- 400 BAD_REQUEST — model_family is `baseline` (no learned importance to extract)
- 404 NOT_FOUND — run_id not found
- 422 UNPROCESSABLE_ENTITY — run has no artifact_uri yet, status is
  pending/running/failed, the artifact file has been deleted from disk
  (`FileNotFoundError`), `joblib.load` raised `ModuleNotFoundError` because
  an optional `ml-*` extra is not installed, or the underlying estimator
  does not expose `feature_importances_` (`HistGradientBoostingRegressor`).
- 500 — DB layer surprise (`SQLAlchemyError`) — mapped to `DatabaseError`.

Archived runs whose artifact files are intact still return 200.
""",
)
async def get_run_feature_metadata(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> FeatureMetadataResponse:
    """Extract feature metadata for a registry-tracked run.

    Args:
        run_id: Registry ``model_run.run_id`` (full UUID).
        db: Async database session from dependency.

    Returns:
        :class:`FeatureMetadataResponse` for a non-baseline run.

    Raises:
        NotFoundError: When no run matches ``run_id``.
        BadRequestError: For a baseline-family run.
        UnprocessableEntityError: For a run with no usable artifact / missing
            ``ml-*`` extra / deleted artifact / HistGBR-no-importance gap.
        DatabaseError: For DB-layer surprises.
    """
    try:
        return await ForecastingService().get_feature_metadata_for_run(db, run_id)
    except SQLAlchemyError as exc:
        logger.error(
            "forecasting.feature_metadata_db_error",
            run_id=run_id,
            error=str(exc),
            exc_info=True,
        )
        raise DatabaseError(
            message="Failed to load feature metadata",
            details={"error": str(exc)},
        ) from exc


@router.get(
    "/jobs/{job_id}/feature-metadata",
    response_model=FeatureMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract feature columns + learned importance for a completed train job",
    description="""
The job-keyed sibling of `/forecasting/runs/{run_id}/feature-metadata`,
exactly mirroring the shape of `/explain/jobs/{job_id}` (PRP-28). Use this
endpoint when the caller has only a `job_id` — for example, the dashboard's
forecast viz page (`frontend/src/pages/visualize/forecast.tsx`), whose
`trainJob.result.run_id` is the **forecast-artifact key**
(`uuid.uuid4().hex[:12]`, see `forecasting/service.py:270`), NOT a registry
UUID.

The route reads `job.result["model_path"]` (the full `.joblib` path written
by `_execute_train` at `jobs/service.py:517`) and loads the bundle directly.

**Error semantics (RFC 7807 application/problem+json):**
- 400 BAD_REQUEST — the job is not a completed train job, or the trained
  model is baseline-family.
- 404 NOT_FOUND — job_id not found.
- 422 UNPROCESSABLE_ENTITY — `model_path` missing from the train-job result,
  the artifact file is missing from disk (`FileNotFoundError`), an `ml-*`
  extra is not installed at unpickle time (`ModuleNotFoundError`), or the
  underlying estimator does not expose `feature_importances_`
  (`HistGradientBoostingRegressor`).
- 500 — DB layer surprise (`SQLAlchemyError`) — mapped to `DatabaseError`.
""",
)
async def get_job_feature_metadata(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> FeatureMetadataResponse:
    """Extract feature metadata for a completed train job.

    Args:
        job_id: Job identifier returned by ``POST /jobs``.
        db: Async database session from dependency.

    Returns:
        :class:`FeatureMetadataResponse` whose ``run_id`` field is the
        forecast-artifact key (12-char hex), NOT a registry UUID.

    Raises:
        NotFoundError: When no job matches ``job_id``.
        BadRequestError: For a non-completed-train job, or a baseline-trained
            job.
        UnprocessableEntityError: For a missing ``model_path``, deleted
            artifact, missing ``ml-*`` extra, or HistGBR-no-importance gap.
        DatabaseError: For DB-layer surprises.
    """
    try:
        return await ForecastingService().get_feature_metadata_for_job(db, job_id)
    except SQLAlchemyError as exc:
        logger.error(
            "forecasting.feature_metadata_db_error",
            job_id=job_id,
            error=str(exc),
            exc_info=True,
        )
        raise DatabaseError(
            message="Failed to load feature metadata",
            details={"error": str(exc)},
        ) from exc
