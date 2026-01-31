"""Feature engineering API routes for feature computation and preview."""

import math
import time
from datetime import date as date_type

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import DatabaseError, NotFoundError
from app.core.logging import get_logger
from app.features.featuresets.schemas import (
    ComputeFeaturesRequest,
    ComputeFeaturesResponse,
    FeatureRow,
    PreviewFeaturesRequest,
)
from app.features.featuresets.service import compute_features_for_series

logger = get_logger(__name__)

router = APIRouter(prefix="/featuresets", tags=["featuresets"])


@router.post(
    "/compute",
    response_model=ComputeFeaturesResponse,
    status_code=status.HTTP_200_OK,
    summary="Compute features for a series",
    description="""
Compute time-safe features for a single store/product series.

**Time Safety:** All features are computed using only data up to and including
the cutoff_date. This prevents future data leakage in training pipelines.

**Feature Types:**
- **Lag features:** Past values at specified lag periods
- **Rolling features:** Rolling statistics (mean, std, etc.) over windows
- **Calendar features:** Day of week, month, quarter with cyclical encoding
- **Exogenous features:** Price lags, price changes, stockout flags

**Configuration:** Pass a FeatureSetConfig to enable/disable specific feature types.
Each sub-config (lag_config, rolling_config, etc.) can be null to disable.
""",
)
async def compute_features(
    request: ComputeFeaturesRequest,
    db: AsyncSession = Depends(get_db),
) -> ComputeFeaturesResponse:
    """Compute features for a single series.

    Args:
        request: Feature computation request with config.
        db: Async database session from dependency.

    Returns:
        Response with computed features and metadata.

    Raises:
        NotFoundError: If no data found for the series.
        DatabaseError: If database operation fails.
    """
    start_time = time.perf_counter()

    logger.info(
        "featureops.compute_request_received",
        store_id=request.store_id,
        product_id=request.product_id,
        cutoff_date=str(request.cutoff_date),
        lookback_days=request.lookback_days,
        config_hash=request.config.config_hash(),
    )

    try:
        result = await compute_features_for_series(
            db=db,
            store_id=request.store_id,
            product_id=request.product_id,
            cutoff_date=request.cutoff_date,
            lookback_days=request.lookback_days,
            config=request.config,
        )

        duration_ms = (time.perf_counter() - start_time) * 1000

        # Check if any data was found
        if result.df.empty:
            logger.warning(
                "featureops.compute_no_data",
                store_id=request.store_id,
                product_id=request.product_id,
            )
            raise NotFoundError(
                message=f"No data found for store_id={request.store_id}, product_id={request.product_id}",
                details={
                    "store_id": request.store_id,
                    "product_id": request.product_id,
                    "cutoff_date": str(request.cutoff_date),
                },
            )

        # Convert dataframe to response rows using records for type safety
        rows: list[FeatureRow] = []
        records = result.df.to_dict("records")
        for record in records:
            # Extract features, handling NaN/None
            features: dict[str, float | int | None] = {}
            for col in result.feature_columns:
                val = record.get(col)
                if val is None or (isinstance(val, float) and math.isnan(val)):
                    features[col] = None
                elif isinstance(val, (int, float)):
                    features[col] = float(val) if isinstance(val, float) else int(val)
                else:
                    features[col] = None

            # Extract date, handling Timestamp
            date_val = record.get(request.config.date_column)
            row_date: date_type
            if isinstance(date_val, pd.Timestamp):
                row_date = date_val.date()
            elif isinstance(date_val, date_type):
                row_date = date_val
            elif date_val is not None and hasattr(date_val, "date"):
                row_date = date_val.date()
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot extract date from unsupported type: {type(date_val).__name__}",
                )

            # Validate store_id/product_id presence
            store_id_val = record.get("store_id")
            product_id_val = record.get("product_id")
            if store_id_val is None or int(store_id_val) < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing or invalid store_id in data record",
                )
            if product_id_val is None or int(product_id_val) < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing or invalid product_id in data record",
                )

            rows.append(
                FeatureRow(
                    date=row_date,
                    store_id=int(store_id_val),
                    product_id=int(product_id_val),
                    features=features,
                )
            )

        # Convert null_counts values to int
        null_counts = {k: int(v) for k, v in result.stats.get("null_counts", {}).items()}

        logger.info(
            "featureops.compute_request_completed",
            store_id=request.store_id,
            product_id=request.product_id,
            row_count=len(rows),
            feature_count=len(result.feature_columns),
            duration_ms=round(duration_ms, 2),
        )

        return ComputeFeaturesResponse(
            rows=rows,
            feature_columns=result.feature_columns,
            config_hash=result.config_hash,
            cutoff_date=request.cutoff_date,
            row_count=len(rows),
            null_counts=null_counts,
            duration_ms=round(duration_ms, 2),
        )

    except NotFoundError:
        raise
    except SQLAlchemyError as e:
        logger.error(
            "featureops.compute_request_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise DatabaseError(
            message="Failed to compute features",
            details={"error": str(e)},
        ) from e


@router.post(
    "/preview",
    response_model=ComputeFeaturesResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview features for a series",
    description="""
Preview computed features for a single store/product series.

Returns a limited number of sample rows for debugging and exploration.
Uses the same computation logic as /compute but limits output rows.
""",
)
async def preview_features(
    request: PreviewFeaturesRequest,
    db: AsyncSession = Depends(get_db),
) -> ComputeFeaturesResponse:
    """Preview features for a single series.

    Args:
        request: Preview request with config and sample size.
        db: Async database session from dependency.

    Returns:
        Response with sample feature rows.

    Raises:
        NotFoundError: If no data found for the series.
        DatabaseError: If database operation fails.
    """
    start_time = time.perf_counter()

    logger.info(
        "featureops.preview_request_received",
        store_id=request.store_id,
        product_id=request.product_id,
        cutoff_date=str(request.cutoff_date),
        sample_rows=request.sample_rows,
    )

    try:
        # Use default lookback for preview
        result = await compute_features_for_series(
            db=db,
            store_id=request.store_id,
            product_id=request.product_id,
            cutoff_date=request.cutoff_date,
            lookback_days=365,
            config=request.config,
        )

        duration_ms = (time.perf_counter() - start_time) * 1000

        if result.df.empty:
            raise NotFoundError(
                message=f"No data found for store_id={request.store_id}, product_id={request.product_id}",
                details={
                    "store_id": request.store_id,
                    "product_id": request.product_id,
                },
            )

        # Limit to sample_rows (take last N rows)
        sample_df = result.df.tail(request.sample_rows)

        # Convert to response rows using records for type safety
        rows: list[FeatureRow] = []
        records = sample_df.to_dict("records")
        for record in records:
            # Extract features, handling NaN/None
            features: dict[str, float | int | None] = {}
            for col in result.feature_columns:
                val = record.get(col)
                if val is None or (isinstance(val, float) and math.isnan(val)):
                    features[col] = None
                elif isinstance(val, (int, float)):
                    features[col] = float(val) if isinstance(val, float) else int(val)
                else:
                    features[col] = None

            # Extract date, handling Timestamp
            date_val = record.get(request.config.date_column)
            row_date: date_type
            if isinstance(date_val, pd.Timestamp):
                row_date = date_val.date()
            elif isinstance(date_val, date_type):
                row_date = date_val
            elif date_val is not None and hasattr(date_val, "date"):
                row_date = date_val.date()
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot extract date from unsupported type: {type(date_val).__name__}",
                )

            # Validate store_id/product_id presence
            store_id_val = record.get("store_id")
            product_id_val = record.get("product_id")
            if store_id_val is None or int(store_id_val) < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing or invalid store_id in data record",
                )
            if product_id_val is None or int(product_id_val) < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing or invalid product_id in data record",
                )

            rows.append(
                FeatureRow(
                    date=row_date,
                    store_id=int(store_id_val),
                    product_id=int(product_id_val),
                    features=features,
                )
            )

        null_counts = {k: int(v) for k, v in result.stats.get("null_counts", {}).items()}

        logger.info(
            "featureops.preview_request_completed",
            row_count=len(rows),
            duration_ms=round(duration_ms, 2),
        )

        return ComputeFeaturesResponse(
            rows=rows,
            feature_columns=result.feature_columns,
            config_hash=result.config_hash,
            cutoff_date=request.cutoff_date,
            row_count=len(rows),
            null_counts=null_counts,
            duration_ms=round(duration_ms, 2),
        )

    except NotFoundError:
        raise
    except SQLAlchemyError as e:
        logger.error(
            "featureops.preview_request_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise DatabaseError(
            message="Failed to preview features",
            details={"error": str(e)},
        ) from e
