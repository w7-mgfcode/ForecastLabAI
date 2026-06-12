"""Showcase workspace persistence helpers (E1, issue #390).

Create/finalize the ``showcase_workspace`` row a ``preservation="keep"`` demo
run records itself into. The write helpers open their OWN sessions via
``app.core.database.get_session_maker()`` -- ``run_pipeline`` is not
request-scoped, so no FastAPI dependency is available (precedent: the lifespan
config-override load in ``app/main.py`` and the agents websocket per-message
sessions).

CONTRACT -- warn-and-continue: a workspace DB failure must NEVER break the
demo pipeline. :func:`create_workspace` returns ``None`` on any error;
:func:`finalize_workspace` swallows any error. Both log a structured warning
(pattern: the ``app/main.py`` lifespan config-override load).

:func:`get_workspace` / :func:`list_workspaces` / :func:`count_workspaces` are
routed since E4 (epic #393) by ``GET /demo/workspaces`` and
``GET /demo/workspaces/{workspace_id}`` in ``app/features/demo/routes.py``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_maker
from app.core.logging import get_logger
from app.features.demo.models import (
    WORKSPACE_STATUS_COMPLETED,
    WORKSPACE_STATUS_FAILED,
    ShowcaseWorkspace,
)
from app.features.demo.schemas import DemoRunRequest

if TYPE_CHECKING:
    # NOTE: pipeline imports this module at runtime; importing DemoContext
    # eagerly here would close an import cycle. The type-only import is safe.
    from app.features.demo.pipeline import DemoContext

logger = get_logger(__name__)


async def create_workspace(req: DemoRunRequest) -> str | None:
    """Insert a ``running`` workspace row for a ``preservation="keep"`` run.

    Args:
        req: The validated demo run request (config recorded verbatim).

    Returns:
        The new row's ``workspace_id``, or ``None`` when the insert failed
        (warn-and-continue -- the pipeline proceeds without a workspace).
    """
    workspace_id = uuid.uuid4().hex
    try:
        session_maker = get_session_maker()
        async with session_maker() as db:
            db.add(
                ShowcaseWorkspace(
                    workspace_id=workspace_id,
                    name=req.workspace_name,
                    seed=req.seed,
                    scenario=req.scenario.value,
                    reset=req.reset,
                    skip_seed=req.skip_seed,
                )
            )
            await db.commit()
    except Exception as exc:  # workspace must never break the demo
        logger.warning(
            "demo.workspace_create_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None
    logger.info("demo.workspace_created", workspace_id=workspace_id, name=req.workspace_name)
    return workspace_id


def _collect_created_objects(ctx: DemoContext) -> dict[str, Any]:
    """Map ``DemoContext`` accumulator fields to the ``created_objects`` JSONB.

    Every value is already a plain ``str`` / ``None`` on ``ctx`` (HTTP response
    payloads). ``None`` and empty values are dropped so the JSONB stays sparse
    and greppable.
    """
    raw: dict[str, Any] = {
        "winning_run_id": ctx.winning_run_id,
        "v2_run_id": ctx.v2_run_id,
        "v2_model_path": ctx.v2_model_path,
        # Literal mirrors ``pipeline.DEMO_ALIAS`` -- importing pipeline here
        # would close an import cycle (pipeline imports this module).
        "alias": "demo-production" if ctx.winning_run_id else None,
        "agent_session_id": ctx.session_id,
        "batch_id": ctx.batch_id,
        "scenario_plan_ids": [s for s in (ctx.price_cut_scenario_id, ctx.holiday_scenario_id) if s],
        "scenario_artifact_key": ctx.scenario_artifact_key,
        "train_model_types": sorted(ctx.train_results),
        "stale_alias_run_id": ctx.stale_alias_run_id,
    }
    return {key: value for key, value in raw.items() if value not in (None, [])}


async def finalize_workspace(
    workspace_id: str,
    ctx: DemoContext,
    *,
    failed: bool,
    wall_clock_s: float | None = None,
) -> None:
    """Settle a workspace row to ``completed`` / ``failed`` with collected ids.

    Called by ``run_pipeline`` BEFORE the final ``pipeline_complete`` yield --
    including the mid-run-failure path, so a partial run still records what it
    created. Finalizing a missing ``workspace_id`` (its create failed earlier)
    is a silent no-op.

    Args:
        workspace_id: The row to finalize (from :func:`create_workspace`).
        ctx: The pipeline's cross-step accumulator.
        failed: Whether any step failed.
        wall_clock_s: Total pipeline wall-clock, recorded in ``result_summary``.
    """
    try:
        session_maker = get_session_maker()
        async with session_maker() as db:
            result = await db.execute(
                select(ShowcaseWorkspace).where(ShowcaseWorkspace.workspace_id == workspace_id)
            )
            row = result.scalar_one_or_none()
            if row is None:  # create failed earlier -- nothing to finalize
                return
            row.status = WORKSPACE_STATUS_FAILED if failed else WORKSPACE_STATUS_COMPLETED
            row.store_id = ctx.store_id
            row.product_id = ctx.product_id
            row.date_start = ctx.date_start
            row.date_end = ctx.date_end
            row.created_objects = _collect_created_objects(ctx)
            row.result_summary = {
                "winner_model_type": ctx.winner_model_type,
                "winner_wape": ctx.winner_wape,
                "wall_clock_s": wall_clock_s,
            }
            await db.commit()
    except Exception as exc:  # workspace must never break the demo
        logger.warning(
            "demo.workspace_finalize_failed",
            workspace_id=workspace_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return
    logger.info("demo.workspace_finalized", workspace_id=workspace_id, failed=failed)


async def get_workspace(db: AsyncSession, workspace_id: str) -> ShowcaseWorkspace | None:
    """Load a workspace row by its external id.

    Args:
        db: An open async session (caller-owned).
        workspace_id: The external id to look up.

    Returns:
        The row, or ``None`` when missing.
    """
    result = await db.execute(
        select(ShowcaseWorkspace).where(ShowcaseWorkspace.workspace_id == workspace_id)
    )
    return result.scalar_one_or_none()


async def list_workspaces(
    db: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[ShowcaseWorkspace]:
    """List workspace rows, newest first (tie-broken by id, descending).

    Args:
        db: An open async session (caller-owned).
        limit: Maximum rows to return.
        offset: Rows to skip from the newest end.

    Returns:
        The matching rows, newest first.
    """
    result = await db.execute(
        select(ShowcaseWorkspace)
        .order_by(ShowcaseWorkspace.created_at.desc(), ShowcaseWorkspace.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def count_workspaces(db: AsyncSession) -> int:
    """Count all workspace rows (E4, issue #393).

    Args:
        db: An open async session (caller-owned).

    Returns:
        The total number of saved workspaces.
    """
    count_stmt = select(func.count()).select_from(ShowcaseWorkspace)
    return int(await db.scalar(count_stmt) or 0)
