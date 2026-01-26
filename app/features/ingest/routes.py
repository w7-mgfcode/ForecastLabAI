"""Ingest API routes for batch upsert operations."""

import time

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import DatabaseError
from app.core.logging import get_logger
from app.features.ingest.schemas import (
    SalesDailyIngestRequest,
    SalesDailyIngestResponse,
)
from app.features.ingest.service import KeyResolver, upsert_sales_daily_batch

logger = get_logger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post(
    "/sales-daily",
    response_model=SalesDailyIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Batch upsert daily sales records",
    description="""
Batch upsert daily sales records using natural keys.

Accepts sales records with store_code and sku (natural keys).
Resolves to internal IDs and performs idempotent upsert using
PostgreSQL ON CONFLICT DO UPDATE.

**Idempotency:** Running the same request twice will update existing
records rather than create duplicates. The grain (date, store_id, product_id)
is enforced by a unique constraint.

**Partial Success:** Invalid rows (unknown store_code, sku, or date) are
rejected while valid rows are processed. Response includes counts and
error details for rejected rows.
""",
)
async def ingest_sales_daily(
    request: SalesDailyIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> SalesDailyIngestResponse:
    """Batch upsert daily sales records.

    Args:
        request: Sales ingest request with list of records.
        db: Async database session from dependency.

    Returns:
        Response with inserted, updated, rejected counts and error details.

    Raises:
        DatabaseError: If database operation fails unexpectedly.
    """
    start_time = time.perf_counter()

    logger.info(
        "ingest.sales_daily.request_received",
        record_count=len(request.records),
    )

    try:
        key_resolver = KeyResolver()
        result = await upsert_sales_daily_batch(db, request.records, key_resolver)

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "ingest.sales_daily.request_completed",
            inserted=result.inserted_count,
            updated=result.updated_count,
            rejected=result.rejected_count,
            duration_ms=round(duration_ms, 2),
        )

        return SalesDailyIngestResponse(
            inserted_count=result.inserted_count,
            updated_count=result.updated_count,
            rejected_count=result.rejected_count,
            total_processed=len(request.records),
            errors=result.errors,
            duration_ms=round(duration_ms, 2),
        )
    except Exception as e:
        logger.error(
            "ingest.sales_daily.request_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise DatabaseError(
            message="Failed to process sales daily ingest",
            details={"error": str(e)},
        ) from e
