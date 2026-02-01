"""REST API routes for agent interactions.

Provides endpoints for:
- Session management (create, get, close)
- Chat interactions (sync and stream)
- Human-in-the-loop approval workflow
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.features.agents.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    ChatRequest,
    ChatResponse,
    SessionCreateRequest,
    SessionResponse,
)
from app.features.agents.service import (
    AgentService,
    NoApprovalPendingError,
    SessionExpiredError,
    SessionNotFoundError,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/agents", tags=["agents"])


def get_agent_service() -> AgentService:
    """Get agent service instance."""
    return AgentService()


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new agent session",
)
async def create_session(
    request: SessionCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> SessionResponse:
    """Create a new agent session.

    Creates a session for the specified agent type. Sessions expire after
    the configured TTL if not used.

    Args:
        request: Session creation request with agent_type.
        db: Database session.
        service: Agent service.

    Returns:
        Created session details including session_id.
    """
    try:
        return await service.create_session(
            db=db,
            agent_type=request.agent_type,
            initial_context=request.initial_context,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    summary="Get session status",
)
async def get_session(
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> SessionResponse:
    """Get session status and details.

    Args:
        session_id: Session identifier.
        db: Database session.
        service: Agent service.

    Returns:
        Session details including status and usage metrics.
    """
    result = await service.get_session(db=db, session_id=session_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
    return result


@router.post(
    "/sessions/{session_id}/chat",
    response_model=ChatResponse,
    summary="Send a message to the agent",
)
async def chat(
    session_id: str,
    request: ChatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> ChatResponse:
    """Send a message and get agent response.

    This is a synchronous endpoint that returns the complete response.
    For streaming responses, use the WebSocket endpoint.

    Args:
        session_id: Session identifier.
        request: Chat request with message.
        db: Database session.
        service: Agent service.

    Returns:
        Agent response with tool calls and token usage.
    """
    try:
        return await service.chat(
            db=db,
            session_id=session_id,
            message=request.message,
        )
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except SessionExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e),
        ) from e


@router.post(
    "/sessions/{session_id}/approve",
    response_model=ApprovalResponse,
    summary="Approve or reject a pending action",
)
async def approve_action(
    session_id: str,
    request: ApprovalRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> ApprovalResponse:
    """Approve or reject a pending action.

    When an agent requests a sensitive action (like creating an alias),
    the session enters awaiting_approval state. Use this endpoint to
    approve or reject the pending action.

    Args:
        session_id: Session identifier.
        request: Approval request with decision.
        db: Database session.
        service: Agent service.

    Returns:
        Approval response with execution result.
    """
    try:
        return await service.approve_action(
            db=db,
            session_id=session_id,
            action_id=request.action_id,
            approved=request.approved,
            reason=request.reason,
        )
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except NoApprovalPendingError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Close a session",
)
async def close_session(
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> None:
    """Close a session.

    Marks the session as closed. Closed sessions cannot be resumed.

    Args:
        session_id: Session identifier.
        db: Database session.
        service: Agent service.
    """
    closed = await service.close_session(db=db, session_id=session_id)
    if not closed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
