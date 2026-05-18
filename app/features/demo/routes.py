"""FastAPI routes for the demo showcase slice.

Exposes:
- ``POST /demo/run``    -- synchronous; runs the whole pipeline, returns a result.
- ``WS   /demo/stream`` -- streams one StepEvent per step for the live UI.

Both obtain the live FastAPI app from ``request.app`` / ``websocket.app`` and
pass it into the pipeline -- the slice never imports ``app.main`` (circular).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.exceptions import ConflictError
from app.core.logging import get_logger
from app.features.demo import service
from app.features.demo.schemas import DemoRunRequest, DemoRunResult, StepEvent

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
