"""Agent service for orchestrating agent sessions and interactions.

Orchestrates:
- Session creation and management
- Agent invocation with dependency injection
- Human-in-the-loop approval workflow
- Message history persistence
- Token usage tracking

CRITICAL: Sessions expire after configured TTL.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import structlog
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.agents.deps import AgentDeps
from app.features.agents.models import AgentSession, AgentType, SessionStatus
from app.features.agents.schemas import (
    ApprovalResponse,
    ChatResponse,
    PendingAction,
    SessionResponse,
    StreamEvent,
    ToolCallResult,
)

logger = structlog.get_logger()


class SessionNotFoundError(ValueError):
    """Session not found in the database."""

    pass


class SessionExpiredError(ValueError):
    """Session has expired."""

    pass


class NoApprovalPendingError(ValueError):
    """No approval action pending for this session."""

    pass


class AgentService:
    """Service for managing agent sessions and interactions.

    Provides orchestration layer for:
    - Creating and retrieving sessions
    - Running agent interactions
    - Managing human-in-the-loop approval
    - Tracking token usage and tool calls

    CRITICAL: All sessions have a TTL and expire automatically.
    """

    def __init__(self) -> None:
        """Initialize the agent service."""
        self.settings = get_settings()

    def _get_agent(self, agent_type: str) -> Agent[AgentDeps, Any]:
        """Get agent instance by type (lazy loading).

        Agents are created on first access to avoid requiring API keys at import time.

        Args:
            agent_type: Type of agent to retrieve.

        Returns:
            Agent instance.

        Raises:
            ValueError: If agent type is not recognized.
        """
        if agent_type == AgentType.EXPERIMENT.value:
            from app.features.agents.agents.experiment import get_experiment_agent

            return get_experiment_agent()
        elif agent_type == AgentType.RAG_ASSISTANT.value:
            from app.features.agents.agents.rag_assistant import get_rag_assistant_agent

            return get_rag_assistant_agent()
        else:
            available = [AgentType.EXPERIMENT.value, AgentType.RAG_ASSISTANT.value]
            raise ValueError(f"Unknown agent type: {agent_type}. Available: {available}")

    async def create_session(
        self,
        db: AsyncSession,
        agent_type: str,
        initial_context: dict[str, Any] | None = None,  # noqa: ARG002 - reserved for future use
    ) -> SessionResponse:
        """Create a new agent session.

        Args:
            db: Database session.
            agent_type: Type of agent for this session.
            initial_context: Optional context to prime the conversation.

        Returns:
            Created session details.
        """
        # Validate agent type
        self._get_agent(agent_type)

        session_id = uuid.uuid4().hex
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self.settings.agent_session_ttl_minutes)

        # Create session
        session = AgentSession(
            session_id=session_id,
            agent_type=agent_type,
            status=SessionStatus.ACTIVE.value,
            message_history=[],
            pending_action=None,
            total_tokens_used=0,
            tool_calls_count=0,
            last_activity=now,
            expires_at=expires_at,
        )

        db.add(session)
        await db.flush()
        await db.refresh(session)

        logger.info(
            "agents.session_created",
            session_id=session_id,
            agent_type=agent_type,
            expires_at=expires_at.isoformat(),
        )

        return SessionResponse(
            session_id=session.session_id,
            agent_type=session.agent_type,
            status=session.status,
            total_tokens_used=session.total_tokens_used,
            tool_calls_count=session.tool_calls_count,
            last_activity=session.last_activity,
            expires_at=session.expires_at,
            created_at=session.created_at,
        )

    async def get_session(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> SessionResponse | None:
        """Get session by ID.

        Args:
            db: Database session.
            session_id: Session identifier.

        Returns:
            Session response or None if not found.
        """
        session = await self._get_session_model(db, session_id)
        if session is None:
            return None

        return SessionResponse(
            session_id=session.session_id,
            agent_type=session.agent_type,
            status=session.status,
            total_tokens_used=session.total_tokens_used,
            tool_calls_count=session.tool_calls_count,
            last_activity=session.last_activity,
            expires_at=session.expires_at,
            created_at=session.created_at,
        )

    async def chat(
        self,
        db: AsyncSession,
        session_id: str,
        message: str,
        request_id: str | None = None,
    ) -> ChatResponse:
        """Send a message and get agent response.

        Args:
            db: Database session.
            session_id: Session identifier.
            message: User message.
            request_id: Optional request correlation ID.

        Returns:
            Agent response with tool calls and token usage.

        Raises:
            SessionNotFoundError: If session not found.
            SessionExpiredError: If session has expired.
        """
        session = await self._get_session_model(db, session_id)
        if session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        # Check expiration
        now = datetime.now(UTC)
        if session.expires_at < now:
            session.status = SessionStatus.EXPIRED.value
            await db.flush()
            raise SessionExpiredError(f"Session expired: {session_id}")

        # Check if awaiting approval
        if session.status == SessionStatus.AWAITING_APPROVAL.value:
            return ChatResponse(
                session_id=session_id,
                message="Session is awaiting approval for a pending action. "
                "Please approve or reject before continuing.",
                pending_approval=True,
                pending_action=self._format_pending_action(session.pending_action),
            )

        # Get agent and create deps
        agent = self._get_agent(session.agent_type)
        deps = AgentDeps(
            db=db,
            session_id=session_id,
            request_id=request_id,
        )

        # Run agent with message history
        message_history = self._deserialize_messages(session.message_history)

        logger.info(
            "agents.chat_started",
            session_id=session_id,
            agent_type=session.agent_type,
            message_length=len(message),
            history_length=len(message_history),
        )

        result = await agent.run(
            message,
            deps=deps,
            message_history=message_history,
        )

        # Extract tool calls from result
        tool_calls: list[ToolCallResult] = []
        # Note: PydanticAI doesn't expose tool call details in the result object
        # directly, so we track them via the deps counter

        # Check for pending approval actions
        pending_action = None
        pending_approval = False

        # The structured output might indicate approval is needed
        # NOTE: PydanticAI's result.data type is generic, cast to Any for attribute access
        result_data: Any = result.data  # type: ignore[attr-defined]
        if hasattr(result_data, "approval_required") and result_data.approval_required:
            pending_approval = True
            if hasattr(result_data, "pending_action"):
                pending_action_name: str | None = result_data.pending_action
                session.pending_action = {
                    "action_id": uuid.uuid4().hex[:16],
                    "action_type": pending_action_name or "unknown",
                    "description": "Agent requested approval for an action",
                    "arguments": {},
                    "created_at": now.isoformat(),
                    "expires_at": (
                        now + timedelta(minutes=self.settings.agent_approval_timeout_minutes)
                    ).isoformat(),
                }
                session.status = SessionStatus.AWAITING_APPROVAL.value
                pending_action = self._format_pending_action(session.pending_action)

        # Update session
        usage = result.usage()
        session.message_history = self._serialize_messages(result.all_messages())
        session.total_tokens_used += usage.total_tokens or 0
        session.tool_calls_count += deps.tool_call_count
        session.last_activity = now

        # Extend expiration
        session.expires_at = now + timedelta(minutes=self.settings.agent_session_ttl_minutes)

        await db.flush()

        logger.info(
            "agents.chat_completed",
            session_id=session_id,
            tokens_used=usage.total_tokens,
            tool_calls=deps.tool_call_count,
            pending_approval=pending_approval,
        )

        # Format response message
        response_message: str = str(result_data) if result_data else "No response generated."
        if hasattr(result_data, "answer"):
            response_message = result_data.answer
        elif hasattr(result_data, "recommendation"):
            response_message = result_data.recommendation

        return ChatResponse(
            session_id=session_id,
            message=response_message,
            tool_calls=tool_calls,
            pending_approval=pending_approval,
            pending_action=pending_action,
            tokens_used=usage.total_tokens or 0,
        )

    async def stream_chat(
        self,
        db: AsyncSession,
        session_id: str,
        message: str,
        request_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream agent response for WebSocket delivery.

        Args:
            db: Database session.
            session_id: Session identifier.
            message: User message.
            request_id: Optional request correlation ID.

        Yields:
            StreamEvent objects for each chunk.

        Raises:
            SessionNotFoundError: If session not found.
            SessionExpiredError: If session has expired.
        """
        session = await self._get_session_model(db, session_id)
        if session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        now = datetime.now(UTC)
        if session.expires_at < now:
            session.status = SessionStatus.EXPIRED.value
            await db.flush()
            raise SessionExpiredError(f"Session expired: {session_id}")

        # Get agent and create deps
        agent = self._get_agent(session.agent_type)
        deps = AgentDeps(
            db=db,
            session_id=session_id,
            request_id=request_id,
        )

        message_history = self._deserialize_messages(session.message_history)

        logger.info(
            "agents.stream_chat_started",
            session_id=session_id,
            agent_type=session.agent_type,
        )

        # Stream the response
        async with agent.run_stream(
            message,
            deps=deps,
            message_history=message_history,
        ) as result:
            async for text in result.stream_text():
                yield StreamEvent(
                    event_type="text_delta",
                    data={"delta": text},
                    timestamp=datetime.now(UTC),
                )

            # Get final result and update session
            # NOTE: PydanticAI's result type is generic, cast to Any for attribute access
            final_result: Any = await result.get_data()  # type: ignore[attr-defined]
            usage = result.usage()

            session.message_history = self._serialize_messages(result.all_messages())
            session.total_tokens_used += usage.total_tokens or 0
            session.tool_calls_count += deps.tool_call_count
            session.last_activity = datetime.now(UTC)
            session.expires_at = session.last_activity + timedelta(
                minutes=self.settings.agent_session_ttl_minutes
            )

            await db.flush()

            # Yield completion event
            response_message: str = str(final_result) if final_result else ""
            if hasattr(final_result, "answer"):
                response_message = final_result.answer
            elif hasattr(final_result, "recommendation"):
                response_message = final_result.recommendation

            yield StreamEvent(
                event_type="complete",
                data={
                    "message": response_message,
                    "tokens_used": usage.total_tokens or 0,
                    "tool_calls_count": deps.tool_call_count,
                },
                timestamp=datetime.now(UTC),
            )

        logger.info(
            "agents.stream_chat_completed",
            session_id=session_id,
            tokens_used=usage.total_tokens,
        )

    async def approve_action(
        self,
        db: AsyncSession,
        session_id: str,
        action_id: str,
        approved: bool,
        reason: str | None = None,
    ) -> ApprovalResponse:
        """Approve or reject a pending action.

        Args:
            db: Database session.
            session_id: Session identifier.
            action_id: Action identifier to approve/reject.
            approved: Whether to approve.
            reason: Optional reason for the decision.

        Returns:
            Approval response with result.

        Raises:
            SessionNotFoundError: If session not found.
            NoApprovalPendingError: If no action pending.
        """
        session = await self._get_session_model(db, session_id)
        if session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        if session.pending_action is None:
            raise NoApprovalPendingError(f"No pending action for session: {session_id}")

        pending = session.pending_action
        if pending.get("action_id") != action_id:
            raise NoApprovalPendingError(f"Action not found: {action_id}")

        logger.info(
            "agents.approval_processed",
            session_id=session_id,
            action_id=action_id,
            approved=approved,
            reason=reason,
        )

        # Clear pending action and restore active status
        session.pending_action = None
        session.status = SessionStatus.ACTIVE.value
        session.last_activity = datetime.now(UTC)

        result: Any = None
        status: Literal["executed", "rejected", "expired"] = "rejected"

        if approved:
            # Execute the pending action
            try:
                result = await self._execute_pending_action(
                    db=db,
                    action_type=pending.get("action_type", "unknown"),
                    arguments=pending.get("arguments", {}),
                )
                status = "executed"
                logger.info(
                    "agents.action_executed",
                    session_id=session_id,
                    action_id=action_id,
                    action_type=pending.get("action_type"),
                )
            except Exception as e:
                logger.exception(
                    "agents.action_execution_failed",
                    session_id=session_id,
                    action_id=action_id,
                    action_type=pending.get("action_type"),
                    error=str(e),
                    error_type=type(e).__name__,
                )
                result = {"error": str(e), "error_type": type(e).__name__}
                status = "rejected"  # Mark as rejected on failure

        await db.flush()

        return ApprovalResponse(
            action_id=action_id,
            approved=approved,
            result=result,
            status=status,
        )

    async def close_session(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> bool:
        """Close a session.

        Args:
            db: Database session.
            session_id: Session identifier.

        Returns:
            True if closed, False if not found.
        """
        session = await self._get_session_model(db, session_id)
        if session is None:
            return False

        session.status = SessionStatus.CLOSED.value
        await db.flush()

        logger.info("agents.session_closed", session_id=session_id)
        return True

    async def _get_session_model(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> AgentSession | None:
        """Get session ORM model by ID.

        Args:
            db: Database session.
            session_id: Session identifier.

        Returns:
            AgentSession or None.
        """
        stmt = select(AgentSession).where(AgentSession.session_id == session_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    def _serialize_messages(
        self,
        messages: list[ModelMessage],
    ) -> list[dict[str, Any]]:
        """Serialize PydanticAI messages for storage.

        PydanticAI messages (ModelRequest, ModelResponse) are dataclasses,
        so we use dataclasses.asdict() for serialization.

        Args:
            messages: List of ModelMessage objects.

        Returns:
            List of serializable dictionaries.
        """
        import dataclasses

        serialized: list[dict[str, Any]] = []
        for msg in messages:
            if dataclasses.is_dataclass(msg) and not isinstance(msg, type):
                # Convert dataclass to dict, handling nested types
                try:
                    msg_dict = dataclasses.asdict(msg)
                    # Add kind discriminator for deserialization
                    if hasattr(msg, "kind"):
                        msg_dict["kind"] = msg.kind
                    serialized.append(msg_dict)
                except (TypeError, ValueError):
                    # Fallback for types that can't be converted
                    serialized.append({"type": type(msg).__name__, "data": str(msg)})
            else:
                # Fallback for non-dataclass types
                serialized.append({"type": type(msg).__name__, "data": str(msg)})
        return serialized

    def _deserialize_messages(
        self,
        data: list[dict[str, Any]],
    ) -> list[ModelMessage]:
        """Deserialize messages from storage.

        Args:
            data: List of serialized message dictionaries.

        Returns:
            List of ModelMessage objects.

        Note:
            PydanticAI handles message reconstruction internally.
            We return the raw data for now - the agent.run() method
            accepts message history in various formats.
        """
        # PydanticAI's run() method can accept message history as dicts
        # Cast to list[ModelMessage] for type checking
        return data  # type: ignore[return-value]

    def _format_pending_action(
        self,
        pending: dict[str, Any] | None,
    ) -> PendingAction | None:
        """Format pending action for response.

        Args:
            pending: Pending action dict from session.

        Returns:
            PendingAction schema or None.
        """
        if pending is None:
            return None

        return PendingAction(
            action_id=pending.get("action_id", ""),
            action_type=pending.get("action_type", ""),
            description=pending.get("description", ""),
            arguments=pending.get("arguments", {}),
            created_at=datetime.fromisoformat(pending.get("created_at", "")),
            expires_at=datetime.fromisoformat(pending.get("expires_at", "")),
        )

    async def _execute_pending_action(
        self,
        db: AsyncSession,
        action_type: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a pending action that was approved.

        Args:
            db: Database session.
            action_type: Type of action to execute (e.g., 'create_alias', 'archive_run').
            arguments: Arguments for the action.

        Returns:
            Result dictionary from the executed action.

        Raises:
            ValueError: If action_type is not recognized.
        """
        from app.features.agents.tools.registry_tools import archive_run, create_alias

        if action_type == "create_alias":
            alias_name = arguments.get("alias_name", "")
            run_id = arguments.get("run_id", "")
            description = arguments.get("description")
            return await create_alias(
                db=db,
                alias_name=alias_name,
                run_id=run_id,
                description=description,
            )
        elif action_type == "archive_run":
            run_id = arguments.get("run_id", "")
            result = await archive_run(db=db, run_id=run_id)
            if result is None:
                raise ValueError(f"Run not found: {run_id}")
            return result
        else:
            raise ValueError(
                f"Unknown action type: {action_type}. Supported actions: create_alias, archive_run"
            )
