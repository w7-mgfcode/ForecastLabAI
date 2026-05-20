"""FastAPI routes for the batch runner slice (PRP-33).

Three endpoints mirroring ``app/features/jobs/routes.py``:

- ``POST /batch/forecasting`` — submit a batch, run it sequentially, return parent.
- ``GET  /batch/{batch_id}`` — fetch parent state.
- ``GET  /batch/{batch_id}/items`` — list items with pagination + allow-listed sort.

All 4xx responses route through ``app.core.exceptions`` to RFC 7807
``application/problem+json``.
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.features.batch.schemas import (
    BatchItemListResponse,
    BatchSubmitRequest,
    BatchSubmitResponse,
)
from app.features.batch.service import BatchService

logger = get_logger(__name__)

router = APIRouter(prefix="/batch", tags=["batch"])


@router.post(
    "/forecasting",
    response_model=BatchSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit and run a portfolio batch",
    description=(
        "Submit a portfolio batch that expands a `BatchScope` to N "
        "(store, product, model) triples, runs them sequentially via the "
        "internal job runner, and settles the parent to "
        "`completed | failed | partial`."
    ),
)
async def submit_batch(
    req: BatchSubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchSubmitResponse:
    """Submit and run a batch — returns the settled parent record."""
    service = BatchService()
    return await service.submit(db=db, req=req)


@router.get(
    "/{batch_id}",
    response_model=BatchSubmitResponse,
    summary="Get batch parent record",
)
async def get_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
) -> BatchSubmitResponse:
    """Get the parent batch record."""
    service = BatchService()
    result = await service.get(db=db, batch_id=batch_id)
    if result is None:
        raise NotFoundError(
            message=f"Batch not found: {batch_id}",
            details={"batch_id": batch_id},
        )
    return result


@router.get(
    "/{batch_id}/items",
    response_model=BatchItemListResponse,
    summary="List batch items",
    description=(
        "List items belonging to a batch with pagination and an allow-listed "
        "`sort_by`. Unknown sort keys fall back silently to the default order "
        "(`created_at desc`) — never raises 4xx."
    ),
)
async def list_batch_items(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page (max 200)"),
    sort_by: str | None = Query(
        None,
        description=(
            "Allow-listed sort column: created_at | completed_at | status | "
            "priority. Unknown values fall back to created_at desc."
        ),
    ),
    sort_order: str = Query("asc", pattern="^(asc|desc)$", description="Sort direction."),
) -> BatchItemListResponse:
    """List items belonging to a batch."""
    service = BatchService()
    result = await service.list_items(
        db=db,
        batch_id=batch_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    if result is None:
        raise NotFoundError(
            message=f"Batch not found: {batch_id}",
            details={"batch_id": batch_id},
        )
    return result
