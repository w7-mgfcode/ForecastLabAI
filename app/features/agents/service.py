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

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

import structlog
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
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


def _sequential_tool_execution() -> AbstractContextManager[None]:
    """Run an agent turn's tool calls one at a time, never concurrently.

    Every tool in a run shares the single ``AgentDeps.db`` ``AsyncSession``,
    and SQLAlchemy forbids concurrent operations on one session. PydanticAI's
    default parallel tool execution therefore raises ``InvalidRequestError``
    whenever a model emits more than one DB-touching tool call in a turn
    (issue #172).

    Both :meth:`AgentService.chat` and :meth:`AgentService.stream_chat` wrap
    their agent run in this context, so the execution-mode policy lives in
    exactly one place.
    """
    return Agent.parallel_tool_call_execution_mode("sequential")


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
        message_history = self._deserialize_messages(session.message_history, session_id)

        logger.info(
            "agents.chat_started",
            session_id=session_id,
            agent_type=session.agent_type,
            message_length=len(message),
            history_length=len(message_history),
        )

        try:
            with _sequential_tool_execution():
                result = await asyncio.wait_for(
                    agent.run(
                        message,
                        deps=deps,
                        message_history=message_history,
                    ),
                    timeout=self.settings.agent_timeout_seconds,
                )
        except TimeoutError as e:
            raise TimeoutError(
                f"Agent response timed out after {self.settings.agent_timeout_seconds} seconds"
            ) from e
        except UnexpectedModelBehavior as e:
            # The model misbehaved (e.g. a tool call exceeded its retry budget).
            # This is recoverable from the user's perspective — surface a clean
            # message instead of leaking the raw PydanticAI exception string.
            logger.warning(
                "agents.chat_model_misbehavior",
                session_id=session_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            session.last_activity = datetime.now(UTC)
            await db.flush()
            return ChatResponse(
                session_id=session_id,
                message=(
                    "I couldn't complete that request — the model produced an "
                    "invalid tool call. Please try rephrasing, or give me a "
                    "specific forecasting objective to work on."
                ),
            )

        # Extract tool calls from result
        tool_calls: list[ToolCallResult] = []
        # Note: PydanticAI doesn't expose tool call details in the result object
        # directly, so we track them via the deps counter

        # Check for pending approval actions
        pending_action = None
        pending_approval = False

        # The structured output might indicate approval is needed
        # NOTE: PydanticAI v1.48.0 uses result.output (not result.data)
        result_data: Any = result.output

        # Check for pending_action in result data (primary trigger)
        # The agent tools should return a pending_action dict with action_type and arguments
        if hasattr(result_data, "pending_action") and result_data.pending_action:
            pending_approval = True
            pending_action_data = result_data.pending_action
            # Extract action details - support both dict and object with attributes
            if isinstance(pending_action_data, dict):
                action_type = pending_action_data.get("action_type", "unknown")
                arguments = pending_action_data.get("arguments", {})
                description = pending_action_data.get(
                    "description", f"Agent requested approval for {action_type}"
                )
            else:
                action_type = getattr(pending_action_data, "action_type", "unknown")
                arguments = getattr(pending_action_data, "arguments", {})
                description = getattr(
                    pending_action_data,
                    "description",
                    f"Agent requested approval for {action_type}",
                )

            session.pending_action = {
                "action_id": uuid.uuid4().hex[:16],
                "action_type": action_type,
                "description": description,
                "arguments": arguments,
                "created_at": now.isoformat(),
                "expires_at": (
                    now + timedelta(minutes=self.settings.agent_approval_timeout_minutes)
                ).isoformat(),
            }
            session.status = SessionStatus.AWAITING_APPROVAL.value
            pending_action = self._format_pending_action(session.pending_action)
        # Fallback: check approval_required flag (legacy trigger)
        elif hasattr(result_data, "approval_required") and result_data.approval_required:
            pending_approval = True
            session.pending_action = {
                "action_id": uuid.uuid4().hex[:16],
                "action_type": "unknown",
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
        response_message: str = "No response generated."
        if result_data:
            if hasattr(result_data, "answer") and result_data.answer:
                response_message = str(result_data.answer)
            elif hasattr(result_data, "summary") and result_data.summary:
                response_message = str(result_data.summary)
            elif hasattr(result_data, "recommendations") and result_data.recommendations:
                recommendations = result_data.recommendations
                if isinstance(recommendations, list) and recommendations:
                    response_message = "\n".join(str(item) for item in recommendations)
                else:
                    response_message = str(result_data)
            else:
                response_message = str(result_data)

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

        message_history = self._deserialize_messages(session.message_history, session_id)

        logger.info(
            "agents.stream_chat_started",
            session_id=session_id,
            agent_type=session.agent_type,
        )

        # Stream the response
        try:
            with _sequential_tool_execution():
                async with asyncio.timeout(self.settings.agent_timeout_seconds):
                    async with agent.run_stream(
                        message,
                        deps=deps,
                        message_history=message_history,
                    ) as result:
                        try:
                            async for text in result.stream_text():
                                yield StreamEvent(
                                    event_type="text_delta",
                                    data={"delta": text},
                                    timestamp=datetime.now(UTC),
                                )
                        except Exception as e:
                            # Structured output agents (output_type=...) cannot stream raw text deltas.
                            # In that case we skip delta streaming and only emit the final complete event.
                            logger.info(
                                "agents.stream_chat_text_delta_unavailable",
                                session_id=session_id,
                                error=str(e),
                                error_type=type(e).__name__,
                            )

                        # Get final result and update session
                        # NOTE: PydanticAI v1.48 exposes get_output() on StreamedRunResult.
                        final_result: Any = await result.get_output()
                        usage = result.usage()

                        session.message_history = self._serialize_messages(result.all_messages())
                        session.total_tokens_used += usage.total_tokens or 0
                        session.tool_calls_count += deps.tool_call_count
                        session.last_activity = datetime.now(UTC)
                        session.expires_at = session.last_activity + timedelta(
                            minutes=self.settings.agent_session_ttl_minutes
                        )

                        await db.flush()

                        # Check for pending approval actions (mirror chat() logic)
                        pending_action = None
                        pending_approval = False
                        stream_now = datetime.now(UTC)

                        # Check for pending_action in result data (primary trigger)
                        if hasattr(final_result, "pending_action") and final_result.pending_action:
                            pending_approval = True
                            pending_action_data = final_result.pending_action
                            # Extract action details - support both dict and object with attributes
                            if isinstance(pending_action_data, dict):
                                action_type = pending_action_data.get("action_type", "unknown")
                                arguments = pending_action_data.get("arguments", {})
                                description = pending_action_data.get(
                                    "description", f"Agent requested approval for {action_type}"
                                )
                            else:
                                action_type = getattr(pending_action_data, "action_type", "unknown")
                                arguments = getattr(pending_action_data, "arguments", {})
                                description = getattr(
                                    pending_action_data,
                                    "description",
                                    f"Agent requested approval for {action_type}",
                                )

                            session.pending_action = {
                                "action_id": uuid.uuid4().hex[:16],
                                "action_type": action_type,
                                "description": description,
                                "arguments": arguments,
                                "created_at": stream_now.isoformat(),
                                "expires_at": (
                                    stream_now
                                    + timedelta(
                                        minutes=self.settings.agent_approval_timeout_minutes
                                    )
                                ).isoformat(),
                            }
                            session.status = SessionStatus.AWAITING_APPROVAL.value
                            pending_action = self._format_pending_action(session.pending_action)
                        # Fallback: check approval_required flag (legacy trigger)
                        elif (
                            hasattr(final_result, "approval_required")
                            and final_result.approval_required
                        ):
                            pending_approval = True
                            session.pending_action = {
                                "action_id": uuid.uuid4().hex[:16],
                                "action_type": "unknown",
                                "description": "Agent requested approval for an action",
                                "arguments": {},
                                "created_at": stream_now.isoformat(),
                                "expires_at": (
                                    stream_now
                                    + timedelta(
                                        minutes=self.settings.agent_approval_timeout_minutes
                                    )
                                ).isoformat(),
                            }
                            session.status = SessionStatus.AWAITING_APPROVAL.value
                            pending_action = self._format_pending_action(session.pending_action)

                        await db.flush()

                        # If approval is required, emit approval_required event
                        if pending_approval and pending_action:
                            yield StreamEvent(
                                event_type="approval_required",
                                data={
                                    "action": pending_action,
                                    "message": "Human approval required before proceeding.",
                                },
                                timestamp=stream_now,
                            )

                        # Yield completion event
                        response_message: str = "No response generated."
                        if final_result:
                            if hasattr(final_result, "answer") and final_result.answer:
                                response_message = str(final_result.answer)
                            elif hasattr(final_result, "summary") and final_result.summary:
                                response_message = str(final_result.summary)
                            elif (
                                hasattr(final_result, "recommendations")
                                and final_result.recommendations
                            ):
                                recommendations = final_result.recommendations
                                if isinstance(recommendations, list) and recommendations:
                                    response_message = "\n".join(
                                        str(item) for item in recommendations
                                    )
                                else:
                                    response_message = str(final_result)
                            else:
                                response_message = str(final_result)

                        yield StreamEvent(
                            event_type="complete",
                            data={
                                "message": response_message,
                                "tokens_used": usage.total_tokens or 0,
                                "tool_calls_count": deps.tool_call_count,
                                "pending_approval": pending_approval,
                            },
                            timestamp=datetime.now(UTC),
                        )
        except TimeoutError as e:
            raise TimeoutError(
                f"Agent response timed out after {self.settings.agent_timeout_seconds} seconds"
            ) from e
        except UnexpectedModelBehavior as e:
            # The model misbehaved (e.g. a tool call exceeded its retry budget).
            # Emit a clean, recoverable `error` event rather than letting the raw
            # PydanticAI exception bubble to the WebSocket handler.
            logger.warning(
                "agents.stream_chat_model_misbehavior",
                session_id=session_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            yield StreamEvent(
                event_type="error",
                data={
                    "error": (
                        "The assistant produced an invalid tool call and couldn't "
                        "complete the request. Please try rephrasing your message."
                    ),
                    "error_type": "model_behavior_error",
                    "recoverable": True,
                },
                timestamp=datetime.now(UTC),
            )
            return

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
        """Serialize PydanticAI messages to JSON-safe dicts for JSONB storage.

        Uses PydanticAI's own ``ModelMessagesTypeAdapter`` so the output can be
        round-tripped back into real ``ModelMessage`` objects by
        :meth:`_deserialize_messages`.

        Args:
            messages: List of ModelMessage objects (e.g. ``result.all_messages()``).

        Returns:
            List of JSON-serializable dictionaries.
        """
        return cast(
            list[dict[str, Any]],
            ModelMessagesTypeAdapter.dump_python(messages, mode="json"),
        )

    def _deserialize_messages(
        self,
        data: list[dict[str, Any]],
        session_id: str,
    ) -> list[ModelMessage]:
        """Reconstruct PydanticAI ModelMessage objects from stored dicts.

        PydanticAI's ``run()`` / ``run_stream()`` require ``message_history`` to
        be real ``ModelMessage`` instances — passing raw dicts fails when the
        framework accesses fields such as ``conversation_id``.

        Args:
            data: List of serialized message dictionaries.
            session_id: Owning session, logged so a failure can be correlated
                with the specific stored record.

        Returns:
            List of ModelMessage objects. Returns an empty list if the stored
            data cannot be validated (e.g. it predates this serialization
            format) — a lost history is recoverable; a crash is not.
        """
        if not data:
            return []
        try:
            return ModelMessagesTypeAdapter.validate_python(data)
        except Exception:
            # Degrade to an empty history on ANY deserialization failure, not
            # just ValidationError: a malformed stored record (wrong shape,
            # type errors) must never crash an otherwise-valid agent run.
            # exc_info preserves the full exception type, message, and traceback.
            logger.warning(
                "agents.message_history_deserialize_failed",
                session_id=session_id,
                message_count=len(data),
                exc_info=True,
            )
            return []

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
        from app.features.scenarios.agent_tools import save_scenario
        from app.features.scenarios.schemas import SaveScenarioRequest

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
        elif action_type == "save_scenario":
            # The HITL gate has released the agent's save_scenario call — persist
            # the scenario_plan row now, stamped with the approved audit trail.
            request = SaveScenarioRequest.model_validate(arguments)
            return await save_scenario(
                db=db,
                request=request,
                agent_session_id=arguments.get("agent_session_id"),
            )
        else:
            raise ValueError(
                f"Unknown action type: {action_type}. Supported actions: "
                "create_alias, archive_run, save_scenario"
            )
