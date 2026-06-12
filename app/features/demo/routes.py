"""FastAPI routes for the demo showcase slice.

Exposes:
- ``POST /demo/run``    -- synchronous; runs the whole pipeline, returns a result.
- ``WS   /demo/stream`` -- streams one StepEvent per step for the live UI.
- ``GET    /demo/workspaces``                 -- E4 (#393): list saved workspaces.
- ``GET    /demo/workspaces/{workspace_id}``  -- E4 (#393): one workspace's detail.
- ``PATCH  /demo/workspaces/{workspace_id}``  -- E1 (#407): partial lifecycle
  update (rename / notes / tags / archive / pin); ``status`` is not patchable.
- ``DELETE /demo/workspaces/{workspace_id}``  -- delete the workspace METADATA
  row only; the run's created objects are soft references and stay untouched.

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
from app.features.demo import service, workspace
from app.features.demo.schemas import (
    DemoRunRequest,
    DemoRunResult,
    StepEvent,
    WorkspaceDetailResponse,
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


@router.get(
    "/workspaces",
    response_model=WorkspaceListResponse,
    summary="List saved showcase workspaces",
    description="List saved showcase workspaces, newest first. Returns 200 + "
    "an empty list when no workspaces exist.",
)
async def list_showcase_workspaces(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum workspaces to return."),
    offset: int = Query(default=0, ge=0, description="Number of workspaces to skip."),
) -> WorkspaceListResponse:
    """List saved showcase workspaces (E4, issue #393).

    Args:
        db: Async database session from dependency.
        limit: Maximum workspaces to return (1-100).
        offset: Number of workspaces to skip.

    Returns:
        A page of saved workspaces plus the total count.
    """
    rows = await workspace.list_workspaces(db, limit=limit, offset=offset)
    total = await workspace.count_workspaces(db)
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
