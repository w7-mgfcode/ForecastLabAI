"""FastAPI routes for backtesting endpoints.

Endpoints:
- POST /backtesting/run - Execute backtest for a series
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import DatabaseError
from app.core.logging import get_logger
from app.features.backtesting.schemas import BacktestRequest, BacktestResponse
from app.features.backtesting.service import BacktestingService

logger = get_logger(__name__)

router = APIRouter(prefix="/backtesting", tags=["backtesting"])


@router.post(
    "/run",
    response_model=BacktestResponse,
    status_code=status.HTTP_200_OK,
    summary="Run a backtest",
    description="""
Run a time-series backtest for a store/product series.

**Split Strategies:**
- `expanding`: Training window grows with each fold (sklearn-like)
- `sliding`: Training window slides forward with fixed size

**Gap Parameter:**
- Simulates operational data latency
- gap=1 means 1 day between training end and test start

**Metrics Calculated:**
- MAE: Mean Absolute Error
- sMAPE: Symmetric Mean Absolute Percentage Error (0-200)
- WAPE: Weighted Absolute Percentage Error
- Bias: Forecast bias (positive = under-forecast)

**Baseline Comparison:**
When `include_baselines=true`, automatically compares against:
- Naive (last value)
- Seasonal Naive (same day previous week)

**Response includes:**
- Per-fold metrics and predictions (if `store_fold_details=true`)
- Aggregated metrics across all folds
- Comparison summary vs baselines
- Leakage validation status
""",
)
async def run_backtest(
    request: BacktestRequest,
    db: AsyncSession = Depends(get_db),
) -> BacktestResponse:
    """Run a backtest for a single series.

    Args:
        request: Backtest request with configuration.
        db: Async database session from dependency.

    Returns:
        BacktestResponse with all results.

    Raises:
        HTTPException: If validation fails or insufficient data.
        DatabaseError: If database operation fails.
    """
    start_time = time.perf_counter()

    logger.info(
        "backtesting.request_received",
        store_id=request.store_id,
        product_id=request.product_id,
        model_type=request.config.model_config_main.model_type,
        strategy=request.config.split_config.strategy,
        n_splits=request.config.split_config.n_splits,
    )

    service = BacktestingService()

    try:
        response = await service.run_backtest(
            db=db,
            store_id=request.store_id,
            product_id=request.product_id,
            start_date=request.start_date,
            end_date=request.end_date,
            config=request.config,
        )

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "backtesting.request_completed",
            store_id=request.store_id,
            product_id=request.product_id,
            backtest_id=response.backtest_id,
            n_folds=len(response.main_model_results.fold_results),
            duration_ms=duration_ms,
        )

        return response

    except ValueError as e:
        logger.warning(
            "backtesting.request_failed",
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
            "backtesting.request_failed",
            store_id=request.store_id,
            product_id=request.product_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise DatabaseError(
            message="Failed to run backtest",
            details={"error": str(e)},
        ) from e
