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
``GET /demo/workspaces/{workspace_id}`` in ``app/features/demo/routes.py``;
:func:`delete_workspace` backs ``DELETE /demo/workspaces/{workspace_id}``;
:func:`update_workspace` backs ``PATCH /demo/workspaces/{workspace_id}``
(E1, #407). E2 (#408) adds server-side list filters (``q`` name search,
``tags`` containment, ``include_archived``) and an allow-listed sort with
unconditional pinned-first ordering. The request-scoped helpers take a
caller-owned session and raise normally -- the warn-and-continue contract is
pipeline-only.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.database import get_session_maker
from app.core.logging import get_logger
from app.features.demo.models import (
    WORKSPACE_STATUS_COMPLETED,
    WORKSPACE_STATUS_FAILED,
    ShowcaseWorkspace,
)
from app.features.demo.schemas import DemoRunRequest, WorkspaceUpdateRequest

if TYPE_CHECKING:
    # NOTE: pipeline imports this module at runtime; importing DemoContext
    # eagerly here would close an import cycle. The type-only import is safe.
    from app.features.demo.pipeline import DemoContext

logger = get_logger(__name__)

# E2 (#408) -- allow-listed sort columns for GET /demo/workspaces. sort_by is
# user input; unknown values fall back to the default order (created_at desc)
# rather than erroring (dimensions precedent, app/features/dimensions/service.py).
_SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "created_at": ShowcaseWorkspace.created_at,
    "name": ShowcaseWorkspace.name,
    "seed": ShowcaseWorkspace.seed,
    "status": ShowcaseWorkspace.status,
}


def _apply_filters[SelectT: Select[Any]](
    stmt: SelectT,
    *,
    q: str | None = None,
    tags: list[str] | None = None,
    include_archived: bool = False,
) -> SelectT:
    """Apply the E2 list filters to a select statement.

    Shared by :func:`list_workspaces` and :func:`count_workspaces` so the
    page's ``total`` always respects the active filters (scenarios precedent:
    ``app/features/scenarios/service.py`` applies the same ``.where`` chain to
    both the count and rows statements).
    """
    if not include_archived:
        stmt = stmt.where(ShowcaseWorkspace.archived.is_(False))
    if q:
        # Case-insensitive name search (dimensions ILIKE precedent). NAME only
        # -- workspace_id prefixes are copy-paste handles, not search terms.
        stmt = stmt.where(ShowcaseWorkspace.name.ilike(f"%{q}%"))
    if tags:
        # JSONB @> containment -- a workspace matches when it carries every
        # listed tag (scenario_plan.tags precedent; GIN-indexed since E1 #407).
        stmt = stmt.where(ShowcaseWorkspace.tags.contains(tags))
    return stmt


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
                    # E1 (#407): replay provenance, recorded verbatim (soft
                    # reference -- no existence check; dangles are designed).
                    replayed_from_workspace_id=req.replayed_from_workspace_id,
                    # E3 (#409): the two replay-relevant story slots, recorded
                    # at create time (the REQUESTED config -- the effective
                    # grain lands separately on store_id/product_id at
                    # finalize, so a fallen-back scope stays visible). Sparse
                    # JSON: only operator-set knobs appear; never {}.
                    seed_overrides=(
                        req.seed_overrides.model_dump(mode="json", exclude_none=True)
                        if req.seed_overrides is not None
                        else None
                    ),
                    user_scope=(
                        req.user_scope.model_dump(mode="json")
                        if req.user_scope is not None
                        else None
                    ),
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


async def update_workspace(
    db: AsyncSession,
    workspace_id: str,
    update: WorkspaceUpdateRequest,
) -> ShowcaseWorkspace | None:
    """Apply a partial lifecycle update; return the row or ``None`` when missing.

    ``exclude_unset`` distinguishes absent fields from explicit ``null`` --
    only fields present in the request body are applied (explicit ``null``
    clears ``name`` / ``notes``; the schema rejects ``null`` on the NOT NULL
    columns). JSONB values are assigned WHOLE (never mutated in place) so
    SQLAlchemy change detection fires. An empty request is a no-op that still
    returns the row.

    Args:
        db: An open async session (caller-owned; this backs an HTTP route,
            NOT the pipeline -- it raises normally, no warn-and-continue).
        workspace_id: The external id of the row to update.
        update: The validated partial-update request.

    Returns:
        The updated row, or ``None`` when no row matched (route maps to 404).
    """
    row = await get_workspace(db, workspace_id)
    if row is None:
        return None
    changes = update.model_dump(exclude_unset=True)  # absent != explicit null
    for field, value in changes.items():
        setattr(row, field, value)  # whole-value assignment (JSONB gotcha)
    await db.commit()
    await db.refresh(row)
    logger.info("demo.workspace_updated", workspace_id=workspace_id, fields=sorted(changes))
    return row


async def list_workspaces(
    db: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    tags: list[str] | None = None,
    include_archived: bool = False,
    sort_by: str | None = None,
    sort_order: str = "desc",
) -> list[ShowcaseWorkspace]:
    """List workspace rows with E2 (#408) filters; pinned rows always first.

    Default order is newest first (tie-broken by id, descending). ``sort_by``
    is allow-listed (created_at / name / seed / status); unknown values fall
    back to the default order. ``name`` sorts NULLS LAST so unnamed rows sink.
    Pinned rows order first regardless of the active sort.

    Args:
        db: An open async session (caller-owned).
        limit: Maximum rows to return.
        offset: Rows to skip from the sorted front.
        q: Case-insensitive name search (ILIKE substring).
        tags: Tag containment filter -- a row must carry every listed tag.
        include_archived: Include archived rows (hidden by default).
        sort_by: Allow-listed sort column; unknown values use the default order.
        sort_order: Sort direction ("asc" or "desc").

    Returns:
        The matching rows in the requested order.
    """
    sort_column = _SORT_COLUMNS.get(sort_by) if sort_by else None
    if sort_column is not None:
        order_expr = sort_column.desc() if sort_order == "desc" else sort_column.asc()
        if sort_by == "name":
            order_expr = order_expr.nulls_last()
    else:
        order_expr = ShowcaseWorkspace.created_at.desc()
    stmt = _apply_filters(
        select(ShowcaseWorkspace), q=q, tags=tags, include_archived=include_archived
    )
    result = await db.execute(
        stmt.order_by(ShowcaseWorkspace.pinned.desc(), order_expr, ShowcaseWorkspace.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def delete_workspace(db: AsyncSession, workspace_id: str) -> bool:
    """Delete a workspace METADATA row; return ``True`` when a row was removed.

    Deletes ONLY the ``showcase_workspace`` row. Everything the run created --
    model runs, scenario plans, aliases, jobs, agent sessions, artifacts -- is
    carried as OPAQUE SOFT REFERENCES in ``created_objects`` (no ForeignKeys
    by design, see ``app/features/demo/models.py``) and is deliberately left
    untouched: the workspace is an audit record, never an ownership root.

    Args:
        db: An open async session (caller-owned).
        workspace_id: The external id of the row to delete.

    Returns:
        ``True`` when a row was deleted, ``False`` when none matched.
    """
    row = await get_workspace(db, workspace_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    logger.info("demo.workspace_deleted", workspace_id=workspace_id)
    return True


async def count_workspaces(
    db: AsyncSession,
    *,
    q: str | None = None,
    tags: list[str] | None = None,
    include_archived: bool = False,
) -> int:
    """Count workspace rows matching the active filters (E4 #393, E2 #408).

    Applies the SAME filter chain as :func:`list_workspaces` (via
    :func:`_apply_filters`) so a filtered page's ``total`` stays honest.

    Args:
        db: An open async session (caller-owned).
        q: Case-insensitive name search (ILIKE substring).
        tags: Tag containment filter -- a row must carry every listed tag.
        include_archived: Include archived rows (hidden by default).

    Returns:
        The number of saved workspaces matching the filters.
    """
    count_stmt = _apply_filters(
        select(func.count()).select_from(ShowcaseWorkspace),
        q=q,
        tags=tags,
        include_archived=include_archived,
    )
    return int(await db.scalar(count_stmt) or 0)
