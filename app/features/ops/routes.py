"""API routes for the ForecastOps Control Center.

Three read-only aggregation endpoints backing the ``/ops`` Control Center page:
operational summary, the ranked retraining-candidate queue, and per-grain
forecast-error health with a drift verdict.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.features.ops.schemas import (
    ModelHealthResponse,
    OpsSummaryResponse,
    RetrainingCandidatesResponse,
)
from app.features.ops.service import OpsService

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get(
    "/summary",
    response_model=OpsSummaryResponse,
    summary="Operational summary for the Control Center",
    description="""
Aggregate the system's operational state into one response.

**Sections**:
- `system`: API liveness, database connectivity, latest completed job.
- `jobs`: per-status job histogram plus active / failed / completed-today counts.
- `runs`: per-status model-run histogram plus success rate and failed count.
- `aliases`: every deployment alias with a staleness verdict.
- `freshness`: latest sales date, latest completed job, latest successful run.
- `attention_items`: recent failed jobs, failed runs, and stale aliases.

Returns HTTP 200 even on an empty database — every section degrades to
zeros / nulls / empty lists rather than erroring.
""",
)
async def get_ops_summary(
    db: AsyncSession = Depends(get_db),
) -> OpsSummaryResponse:
    """Return the aggregated operational summary.

    Args:
        db: Database session.

    Returns:
        The full operational summary.
    """
    return await OpsService().get_summary(db)


@router.get(
    "/retraining-candidates",
    response_model=RetrainingCandidatesResponse,
    summary="Ranked retraining-candidate queue",
    description="""
Rank `(store, product)` grains by a deterministic retraining-priority score.

Each grain is evaluated from its latest successful model run. The score blends
a time-based signal (staleness since the training-data window ended) with a
performance-based signal (WAPE), so the highest-scoring rows are the most
overdue and/or least accurate.

Candidates are sorted by `priority_score` descending and capped at `limit`.
""",
)
async def get_retraining_candidates(
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of candidates to return (1-100, default 20).",
    ),
    db: AsyncSession = Depends(get_db),
) -> RetrainingCandidatesResponse:
    """Return the ranked retraining-candidate queue.

    Args:
        limit: Maximum number of candidates to return.
        db: Database session.

    Returns:
        Candidates sorted by priority score (highest first).
    """
    return await OpsService().get_retraining_candidates(db, limit)


@router.get(
    "/model-health",
    response_model=ModelHealthResponse,
    summary="Per-(store, product) forecast-error health and drift",
    description="""
Classify forecast-error **performance drift** for every `(store, product)` grain.

For each grain the endpoint reads the **full** successful-run history, extracts
each run's WAPE, and compares the latest WAPE against the mean of the prior
WAPEs within a ±10% relative band — yielding a drift verdict
(`improving` / `stable` / `degrading` / `unknown`).

Entries are sorted **degrading-first**, then by the magnitude of the WAPE
change, and capped at `limit`. Returns HTTP 200 even on an empty database.

This is a performance-drift signal, not data drift — it needs no feature
snapshots and adds no new table or migration.
""",
)
async def get_model_health(
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of grains to return (1-100, default 20).",
    ),
    db: AsyncSession = Depends(get_db),
) -> ModelHealthResponse:
    """Return per-grain forecast-error health and drift.

    Args:
        limit: Maximum number of grains to return.
        db: Database session.

    Returns:
        Grains sorted degrading-first, then by absolute WAPE change.
    """
    return await OpsService().get_model_health(db, limit)
