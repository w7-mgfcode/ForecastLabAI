"""FastAPI routes for the demo showcase slice.

Exposes:
- ``POST /demo/run``    -- synchronous; runs the whole pipeline, returns a result.
- ``WS   /demo/stream`` -- streams one StepEvent per step for the live UI.
- ``GET    /demo/workspaces``                 -- E4 (#393): list saved workspaces.
  E2 (#408): ``q`` name search, repeated ``tags`` containment,
  ``include_archived`` (default false), allow-listed ``sort_by``/``sort_order``;
  pinned rows always order first.
- ``GET    /demo/workspaces/{workspace_id}``  -- E4 (#393): one workspace's detail.
- ``GET    /demo/workspaces/{workspace_id}/health`` -- E2 (#408): probe the
  workspace's soft references in-process; per-ref alive/dead/unknown + counts.
- ``PATCH  /demo/workspaces/{workspace_id}``  -- E1 (#407): partial lifecycle
  update (rename / notes / tags / archive / pin); ``status`` is not patchable.
- ``DELETE /demo/workspaces/{workspace_id}``  -- delete the workspace METADATA
  row only; the run's created objects are soft references and stay untouched.
- ``POST   /demo/workspaces/{workspace_id}/export`` -- E6 (#412): write a
  checksum-validated bundle (manifest + scenario-plan snapshots + checksums)
  under ``artifacts/showcase/<workspace_id>/``; soft references resolve
  in-process, model artifacts are referenced (never copied), dangling refs are
  reported, not fatal.

The run/stream handlers obtain the live FastAPI app from ``request.app`` /
``websocket.app`` and pass it into the pipeline -- the slice never imports
``app.main`` (circular). The workspace GETs are the slice's first DB-dependent
routes (``Depends(get_db)``).
"""

from __future__ import annotations

import json

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.features.demo import export, hitl, link_health, service, workspace
from app.features.demo.models import WORKSPACE_STATUS_RUNNING
from app.features.demo.schemas import (
    ApprovalEventItem,
    ApprovalEventsResponse,
    DemoRunRequest,
    DemoRunResult,
    HitlDecisionRequest,
    StepEvent,
    WorkspaceDetailResponse,
    WorkspaceExportResult,
    WorkspaceHealthResponse,
    WorkspaceListItem,
    WorkspaceListResponse,
    WorkspaceUpdateRequest,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post(
    "/run",
    response_model=DemoRunResult,
    summary="Run the end-to-end demo pipeline",
    description=(
        "Drives the full e2e pipeline (seed -> features -> train x3 -> "
        "backtest x3 -> register -> verify -> agent) in-process and returns "
        "every step outcome. Returns 409 if a pipeline run is already active."
    ),
)
async def run_demo_pipeline(request: Request, params: DemoRunRequest) -> DemoRunResult:
    """Run the demo pipeline synchronously and return the aggregate result.

    Args:
        request: The incoming request (used to obtain the live FastAPI app).
        params: Run parameters (seed, reset, skip_seed).

    Returns:
        The aggregate :class:`DemoRunResult`.

    Raises:
        ConflictError: If another pipeline run is already in progress (409).
    """
    try:
        return await service.run_pipeline_sync(request.app, params)
    except service.PipelineBusyError as exc:
        raise ConflictError(str(exc)) from exc


@router.post(
    "/hitl-decision",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Relay an operator decision to the in-flight HITL step",
    description=(
        "Relay the Showcase HITL step card's Approve / Reject to the running "
        "pipeline (E5, #411). The pipeline forwards the real decision to the "
        "agents HITL gate. 404 when no matching action is pending; 409 when the "
        "action was already decided; 422 on a malformed body."
    ),
)
async def submit_hitl_decision(body: HitlDecisionRequest) -> None:
    """Relay an operator Approve/Reject to the in-flight HITL step (E5, #411).

    Args:
        body: The operator decision (action_id, approved/rejected, optional reason).

    Raises:
        NotFoundError: When no HITL action is pending under ``action_id`` (404).
        ConflictError: When the action was already decided (409).
    """
    outcome = hitl.resolve(body.action_id, body.decision, body.reason)
    if outcome == "not_found":
        raise NotFoundError(message=f"No pending HITL action: {body.action_id}")
    if outcome == "already_decided":
        raise ConflictError(f"Action already decided: {body.action_id}")


@router.get(
    "/approval-events",
    response_model=ApprovalEventsResponse,
    summary="Recent HITL approval events across saved workspaces",
    description=(
        "Flatten ``approval_events`` across the newest saved workspaces that "
        "carry the slot, newest-workspace-first (E5, #411). An audit-glance "
        "surface -- no pagination. Returns 200 + an empty list when none."
    ),
)
async def list_hitl_approval_events(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum flattened entries."),
) -> ApprovalEventsResponse:
    """List recent HITL approval events flattened across workspaces (E5, #411).

    Args:
        db: Async database session from dependency.
        limit: Maximum flattened entries to return (1-200).

    Returns:
        The flattened approval events plus the returned count.
    """
    events = await workspace.list_approval_events(db, limit=limit)
    return ApprovalEventsResponse(
        events=[ApprovalEventItem.model_validate(event) for event in events],
        total=len(events),
    )


@router.get(
    "/workspaces",
    response_model=WorkspaceListResponse,
    summary="List saved showcase workspaces",
    description=(
        "List saved showcase workspaces, newest first (pinned rows always "
        "order first). E2 (#408): `q` searches names case-insensitively, "
        "repeated `tags` params filter by containment, archived rows are "
        "hidden unless `include_archived=true`, and `sort_by`/`sort_order` "
        "are allow-listed (unknown values use the default order). Returns "
        "200 + an empty list when nothing matches."
    ),
)
async def list_showcase_workspaces(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum workspaces to return."),
    offset: int = Query(default=0, ge=0, description="Number of workspaces to skip."),
    q: str | None = Query(
        default=None,
        min_length=2,
        description="Search in workspace name (case-insensitive).",
    ),
    tags: list[str] | None = Query(
        default=None,
        description="Repeatable tag filter -- a workspace matches when it "
        "carries every listed tag.",
    ),
    include_archived: bool = Query(
        default=False,
        description="Include archived workspaces (hidden by default).",
    ),
    sort_by: str | None = Query(
        default=None,
        description="Sort column: created_at, name, seed, or status. "
        "Unknown values fall back to the default order (created_at desc).",
    ),
    sort_order: str = Query(
        default="desc",
        pattern="^(asc|desc)$",
        description="Sort direction: asc or desc.",
    ),
) -> WorkspaceListResponse:
    """List saved showcase workspaces (E4 #393; filters/sort E2 #408).

    Args:
        db: Async database session from dependency.
        limit: Maximum workspaces to return (1-100).
        offset: Number of workspaces to skip.
        q: Case-insensitive name search.
        tags: Repeatable tag containment filter.
        include_archived: Include archived workspaces.
        sort_by: Allow-listed sort column (unknown values use default order).
        sort_order: Sort direction (asc or desc).

    Returns:
        A page of saved workspaces plus the filtered total count.
    """
    rows = await workspace.list_workspaces(
        db,
        limit=limit,
        offset=offset,
        q=q,
        tags=tags,
        include_archived=include_archived,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total = await workspace.count_workspaces(db, q=q, tags=tags, include_archived=include_archived)
    return WorkspaceListResponse(
        workspaces=[WorkspaceListItem.model_validate(row) for row in rows],
        total=total,
    )


@router.get(
    "/workspaces/{workspace_id}",
    response_model=WorkspaceDetailResponse,
    summary="Get a saved showcase workspace",
    description="Fetch one saved workspace, including its created-object soft references.",
)
async def get_showcase_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
) -> WorkspaceDetailResponse:
    """Get a saved showcase workspace by id (E4, issue #393).

    Args:
        workspace_id: External identifier of the workspace.
        db: Async database session from dependency.

    Returns:
        The full workspace row including ``created_objects``.

    Raises:
        NotFoundError: When no workspace matches ``workspace_id``.
    """
    row = await workspace.get_workspace(db, workspace_id)
    if row is None:
        raise NotFoundError(message=f"Workspace not found: {workspace_id}")
    return WorkspaceDetailResponse.model_validate(row)


@router.get(
    "/workspaces/{workspace_id}/health",
    response_model=WorkspaceHealthResponse,
    summary="Probe a workspace's soft-reference link health",
    description=(
        "Probe every soft reference the workspace recorded (model runs, "
        "scenario plans, alias, batch, agent session, job ids) through the "
        "public API in-process. Each reference classifies as alive (2xx), "
        "dead (404 -- deleted after the run), or unknown (anything else). "
        "`partial_run` flags a row whose pipeline never completed."
    ),
)
async def get_workspace_health(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WorkspaceHealthResponse:
    """Probe a saved workspace's soft references (E2, issue #408).

    Args:
        workspace_id: External identifier of the workspace.
        request: The incoming request (used to obtain the live FastAPI app
            for the in-process probes).
        db: Async database session from dependency.

    Returns:
        Per-reference liveness plus aggregate counts.

    Raises:
        NotFoundError: When no workspace matches ``workspace_id``.
    """
    row = await workspace.get_workspace(db, workspace_id)
    if row is None:
        raise NotFoundError(message=f"Workspace not found: {workspace_id}")
    return await link_health.probe_workspace_links(request.app, row)


@router.patch(
    "/workspaces/{workspace_id}",
    response_model=WorkspaceDetailResponse,
    summary="Update a saved showcase workspace's lifecycle metadata",
    description=(
        "Partial update: rename / notes / tags / archive / pin. Only fields "
        "present in the body change; explicit null clears name/notes. The run "
        "lifecycle status is not patchable."
    ),
)
async def update_showcase_workspace(
    workspace_id: str,
    update: WorkspaceUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> WorkspaceDetailResponse:
    """Update a saved showcase workspace's lifecycle metadata (E1, #407).

    Args:
        workspace_id: External identifier of the workspace.
        update: Partial-update body; only provided fields are applied.
        db: Async database session from dependency.

    Returns:
        The full updated workspace row.

    Raises:
        NotFoundError: When no workspace matches ``workspace_id``.
    """
    row = await workspace.update_workspace(db, workspace_id, update)
    if row is None:
        raise NotFoundError(message=f"Workspace not found: {workspace_id}")
    return WorkspaceDetailResponse.model_validate(row)


@router.delete(
    "/workspaces/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a saved showcase workspace",
    description=(
        "Delete one saved workspace METADATA row. Everything the run created "
        "(model runs, scenario plans, aliases, jobs, artifacts) is a soft "
        "reference and is NOT deleted."
    ),
)
async def delete_showcase_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a saved showcase workspace metadata row.

    Args:
        workspace_id: External identifier of the workspace.
        db: Async database session from dependency.

    Raises:
        NotFoundError: When no workspace matches ``workspace_id``.
    """
    deleted = await workspace.delete_workspace(db, workspace_id)
    if not deleted:
        raise NotFoundError(message=f"Workspace not found: {workspace_id}")


@router.post(
    "/workspaces/{workspace_id}/export",
    response_model=WorkspaceExportResult,
    summary="Export a saved showcase workspace as a checksum-validated bundle",
    description=(
        "Write artifacts/showcase/<workspace_id>/ -- a versioned manifest.json, "
        "one JSON per resolvable scenario plan, and a sha256sum-compatible "
        "checksums.sha256 -- then re-verify every checksum before returning. "
        "Model artifacts are referenced (uri + registry hash + live verify), "
        "never copied. Dangling soft references are reported in "
        "`unresolved_references` (the export still returns 200). 404 when the "
        "workspace is missing; 409 while its run is still in progress; "
        "re-export overwrites the bundle."
    ),
)
async def export_showcase_workspace(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WorkspaceExportResult:
    """Export a saved showcase workspace to a checksum-validated bundle (E6, #412).

    Args:
        workspace_id: External identifier of the workspace.
        request: The incoming request (used to obtain the live FastAPI app for
            the in-process soft-reference resolution GETs).
        db: Async database session from dependency.

    Returns:
        The export result -- bundle path, file inventory with hashes, counts,
        unresolved references, and the checksum-validation flag.

    Raises:
        NotFoundError: When no workspace matches ``workspace_id`` (404).
        ConflictError: When the workspace run is still in progress (409).
    """
    row = await workspace.get_workspace(db, workspace_id)
    if row is None:
        raise NotFoundError(message=f"Workspace not found: {workspace_id}")
    if row.status == WORKSPACE_STATUS_RUNNING:
        raise ConflictError(
            "Cannot export while the run is still in progress; retry after the run settles."
        )
    return await export.export_workspace(db, request.app, workspace_id)


@router.websocket("/stream")
async def stream_demo_pipeline(websocket: WebSocket) -> None:
    """Stream one StepEvent per pipeline step over a WebSocket.

    Protocol:
    1. Client connects and sends one start frame: ``{"seed", "reset", "skip_seed"}``
       (all fields optional -- the request model supplies defaults).
    2. Server streams ``step_start`` / ``step_complete`` events, then a final
       ``pipeline_complete`` event, and closes.
    3. On a bad start frame or a busy pipeline, the server sends one ``error``
       event and closes.
    """
    await websocket.accept()
    logger.info("demo.websocket_connected")
    try:
        raw = await websocket.receive_json()
        params = DemoRunRequest.model_validate(raw)
        async for event in service.stream_pipeline(websocket.app, params):
            await websocket.send_json(event.model_dump(mode="json"))
    except WebSocketDisconnect:
        logger.info("demo.websocket_disconnected")
        return
    except (ValidationError, json.JSONDecodeError) as exc:
        await websocket.send_json(
            _error_event(f"invalid start frame: {exc}").model_dump(mode="json")
        )
    except service.PipelineBusyError as exc:
        await websocket.send_json(_error_event(str(exc)).model_dump(mode="json"))
    await websocket.close()


def _error_event(detail: str) -> StepEvent:
    """Build a one-off ``error`` StepEvent for the WebSocket failure path."""
    return StepEvent(
        event_type="error",
        step_name="pipeline",
        step_index=0,
        total_steps=0,
        status="fail",
        detail=detail,
    )
