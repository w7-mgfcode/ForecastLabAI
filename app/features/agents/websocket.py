"""WebSocket handler for streaming agent responses.

Provides real-time streaming of agent responses for responsive UX.

CRITICAL: Uses session-per-message pattern to avoid stale data and memory growth.
Each incoming message gets a fresh database session that is closed after processing.
"""

from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.database import get_session_maker
from app.features.agents.service import (
    AgentService,
    SessionExpiredError,
    SessionNotFoundError,
)

logger = structlog.get_logger()

router = APIRouter(tags=["agents-websocket"])


@router.websocket("/agents/stream")
async def websocket_stream(
    websocket: WebSocket,
) -> None:
    """WebSocket endpoint for streaming agent responses.

    Protocol:
    1. Client connects and sends: {"session_id": "...", "message": "..."}
    2. Server streams: {"event_type": "text_delta", "data": {"delta": "..."}}
    3. Server completes: {"event_type": "complete", "data": {...}}
    4. On error: {"event_type": "error", "data": {"error": "...", "recoverable": bool}}

    The connection stays open for multiple messages within the same session.

    CRITICAL: Uses session-per-message pattern - each message gets a fresh database
    session to avoid stale data and memory growth from long-lived connections.
    """
    await websocket.accept()

    service = AgentService()
    session_maker = get_session_maker()
    current_session_id: str | None = None

    logger.info("agents.websocket_connected")

    try:
        while True:
            # Receive message from client
            try:
                data = await websocket.receive_json()
            except json.JSONDecodeError as e:
                await _send_error(websocket, f"Invalid JSON: {e}", recoverable=True)
                continue

            # Validate message format
            session_id = data.get("session_id")
            message = data.get("message")

            if not session_id or not message:
                await _send_error(
                    websocket,
                    "Missing required fields: session_id and message",
                    recoverable=True,
                )
                continue

            current_session_id = session_id

            logger.info(
                "agents.websocket_message_received",
                session_id=session_id,
                message_length=len(message),
            )

            # Stream response with fresh database session per message
            # This prevents stale data and memory growth from accumulated ORM objects
            async with session_maker() as db:
                try:
                    async for event in service.stream_chat(
                        db=db,
                        session_id=session_id,
                        message=message,
                    ):
                        await websocket.send_json(event.model_dump(mode="json"))

                    # Commit any changes made during streaming
                    await db.commit()

                except SessionNotFoundError as e:
                    await _send_error(
                        websocket,
                        str(e),
                        error_type="session_not_found",
                        recoverable=False,
                    )
                except SessionExpiredError as e:
                    await _send_error(
                        websocket,
                        str(e),
                        error_type="session_expired",
                        recoverable=False,
                    )
                except Exception as e:
                    logger.exception(
                        "agents.websocket_stream_error",
                        session_id=session_id,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    await db.rollback()
                    await _send_error(
                        websocket,
                        f"Stream error: {e}",
                        error_type=type(e).__name__,
                        recoverable=True,
                    )

    except WebSocketDisconnect:
        logger.info(
            "agents.websocket_disconnected",
            session_id=current_session_id,
        )


async def _send_error(
    websocket: WebSocket,
    error: str,
    error_type: str = "unknown",
    recoverable: bool = True,
) -> None:
    """Send error event to WebSocket client.

    Args:
        websocket: WebSocket connection.
        error: Error message.
        error_type: Type of error.
        recoverable: Whether the client can continue using this connection.
    """
    from datetime import UTC, datetime

    await websocket.send_json(
        {
            "event_type": "error",
            "data": {
                "error": error,
                "error_type": error_type,
                "recoverable": recoverable,
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )
