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

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import ConflictError, GatewayTimeoutError, NotFoundError
from app.core.logging import get_logger
from app.features.batch import runner
from app.features.batch.models import TERMINAL_BATCH_STATES
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


@router.delete(
    "/{batch_id}",
    response_model=BatchSubmitResponse,
    summary="Cancel an in-flight batch (cooperative drain)",
    description=(
        "Cancel an in-flight batch (PRP-34). Pending children skip execution; "
        "running children observe ``asyncio.CancelledError`` at the next safe "
        "yield point — sklearn / LightGBM fits are uncancellable mid-call, so "
        "an in-flight fit may stall the drain (504 surfaces that). Returns:\n\n"
        "- ``200`` settled parent on clean drain\n"
        "- ``404`` RFC 7807 if the batch does not exist\n"
        "- ``409`` RFC 7807 if the batch is already terminal\n"
        "- ``504`` RFC 7807 if the drain exceeds "
        "``Settings.batch_cancel_drain_timeout_seconds``"
    ),
)
async def cancel_batch_route(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
) -> BatchSubmitResponse:
    """Cancel an in-flight batch and return its settled parent record."""
    service = BatchService()
    parent = await service.get(db=db, batch_id=batch_id)
    if parent is None:
        raise NotFoundError(
            message=f"Batch not found: {batch_id}",
            details={"batch_id": batch_id},
        )
    if parent.status in TERMINAL_BATCH_STATES:
        raise ConflictError(
            message=f"Batch already terminal: {parent.status.value}",
            details={"batch_id": batch_id, "status": parent.status.value},
        )

    fired = runner.cancel_batch(batch_id)
    if not fired:
        # Race: the submit handler's ``_settle`` committed and
        # ``mark_completed`` removed the registry handle between our
        # ``service.get`` above and ``cancel_batch`` here. The parent is now
        # terminal in DB but we still raise 409 so the operator's intent
        # ("I want this stopped") gets a truthful answer.
        raise ConflictError(
            message="Batch settled before cancel could fire",
            details={"batch_id": batch_id},
        )

    settings = get_settings()
    drained = await runner.await_drain(
        batch_id=batch_id,
        timeout_seconds=float(settings.batch_cancel_drain_timeout_seconds),
    )
    if not drained:
        raise GatewayTimeoutError(
            message=(
                f"Drain exceeded {settings.batch_cancel_drain_timeout_seconds}s; "
                "parent settle still pending. In-flight sklearn / LightGBM fits "
                "are uncancellable mid-call — retry once the fit completes."
            ),
            details={
                "batch_id": batch_id,
                "drain_timeout_seconds": settings.batch_cancel_drain_timeout_seconds,
            },
        )

    final = await service.get(db=db, batch_id=batch_id)
    if final is None:
        # Defensive — ``batch_job`` rows are never deleted, so this branch
        # should be unreachable. Surface as 404 if it ever happens.
        raise NotFoundError(
            message=f"Batch not found after drain: {batch_id}",
            details={"batch_id": batch_id},
        )
    logger.info("batch.cancelled", batch_id=batch_id, status=final.status.value)
    return final


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
