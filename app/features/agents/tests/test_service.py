"""Unit tests for agent service."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import (
    FallbackExceptionGroup,
    ModelHTTPError,
    UnexpectedModelBehavior,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)

from app.core.exceptions import AgentFallbackExhaustedError
from app.features.agents.deps import AgentDeps
from app.features.agents.models import AgentSession, AgentType, SessionStatus
from app.features.agents.schemas import ExperimentReport
from app.features.agents.service import (
    AgentService,
    NoApprovalPendingError,
    SessionExpiredError,
    SessionNotFoundError,
)


class TestAgentServiceInit:
    """Tests for AgentService initialization."""

    def test_service_init(self) -> None:
        """Service should initialize successfully."""
        service = AgentService()
        assert service.settings is not None

    def test_get_agent_experiment(self) -> None:
        """Should return experiment agent."""
        service = AgentService()
        # This will fail without API key, but we're testing the path validation
        with patch("app.features.agents.agents.experiment.get_experiment_agent") as mock_get:
            mock_agent = MagicMock()
            mock_get.return_value = mock_agent

            agent = service._get_agent(AgentType.EXPERIMENT.value)
            assert agent is mock_agent
            mock_get.assert_called_once()

    def test_get_agent_rag_assistant(self) -> None:
        """Should return RAG assistant agent."""
        service = AgentService()
        with patch("app.features.agents.agents.rag_assistant.get_rag_assistant_agent") as mock_get:
            mock_agent = MagicMock()
            mock_get.return_value = mock_agent

            agent = service._get_agent(AgentType.RAG_ASSISTANT.value)
            assert agent is mock_agent
            mock_get.assert_called_once()

    def test_get_agent_unknown_type_raises(self) -> None:
        """Should raise ValueError for unknown agent type."""
        service = AgentService()
        with pytest.raises(ValueError, match="Unknown agent type"):
            service._get_agent("unknown_agent")


class TestAgentServiceCreateSession:
    """Tests for session creation."""

    @pytest.mark.asyncio
    async def test_create_session_experiment(self) -> None:
        """Should create experiment session."""
        service = AgentService()
        now = datetime.now(UTC)
        # Create mock with sync add() and async flush()/refresh()
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        # Make refresh set created_at on the session
        async def mock_refresh(session: Any) -> None:
            session.created_at = now
            session.updated_at = now

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        # Patch _get_agent to avoid API key requirement
        with patch.object(service, "_get_agent", return_value=MagicMock()):
            response = await service.create_session(
                db=mock_db,
                agent_type=AgentType.EXPERIMENT.value,
            )

        assert response.agent_type == AgentType.EXPERIMENT.value
        assert response.status == SessionStatus.ACTIVE.value
        assert len(response.session_id) == 32  # UUID hex
        assert response.total_tokens_used == 0
        assert response.tool_calls_count == 0
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_session_rag(self) -> None:
        """Should create RAG assistant session."""
        service = AgentService()
        now = datetime.now(UTC)
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        async def mock_refresh(session: Any) -> None:
            session.created_at = now
            session.updated_at = now

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        with patch.object(service, "_get_agent", return_value=MagicMock()):
            response = await service.create_session(
                db=mock_db,
                agent_type=AgentType.RAG_ASSISTANT.value,
            )

        assert response.agent_type == AgentType.RAG_ASSISTANT.value
        assert response.status == SessionStatus.ACTIVE.value

    @pytest.mark.asyncio
    async def test_create_session_with_context(self) -> None:
        """Should create session with initial context."""
        service = AgentService()
        now = datetime.now(UTC)
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        async def mock_refresh(session: Any) -> None:
            session.created_at = now
            session.updated_at = now

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)
        initial_context = {"objective": "test"}

        with patch.object(service, "_get_agent", return_value=MagicMock()):
            response = await service.create_session(
                db=mock_db,
                agent_type=AgentType.EXPERIMENT.value,
                initial_context=initial_context,
            )

        assert response.session_id is not None

    @pytest.mark.asyncio
    async def test_create_session_invalid_type_raises(self) -> None:
        """Should raise for invalid agent type."""
        service = AgentService()
        mock_db = AsyncMock()

        with pytest.raises(ValueError, match="Unknown agent type"):
            await service.create_session(
                db=mock_db,
                agent_type="invalid_type",
            )


class TestAgentServiceGetSession:
    """Tests for session retrieval."""

    @pytest.mark.asyncio
    async def test_get_session_found(self, sample_active_session: AgentSession) -> None:
        """Should return session when found."""
        service = AgentService()
        mock_db = AsyncMock()

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        response = await service.get_session(
            db=mock_db,
            session_id=sample_active_session.session_id,
        )

        assert response is not None
        assert response.session_id == sample_active_session.session_id
        assert response.agent_type == sample_active_session.agent_type

    @pytest.mark.asyncio
    async def test_get_session_not_found(self) -> None:
        """Should return None when session not found."""
        service = AgentService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        response = await service.get_session(
            db=mock_db,
            session_id="nonexistent",
        )

        assert response is None


class TestAgentServiceChat:
    """Tests for chat functionality."""

    @pytest.mark.asyncio
    async def test_chat_session_not_found_raises(self) -> None:
        """Should raise SessionNotFoundError."""
        service = AgentService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(SessionNotFoundError):
            await service.chat(
                db=mock_db,
                session_id="nonexistent",
                message="Hello",
            )

    @pytest.mark.asyncio
    async def test_chat_session_expired_raises(self, sample_expired_session: AgentSession) -> None:
        """Should raise SessionExpiredError for expired session."""
        service = AgentService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_expired_session
        mock_db.execute.return_value = mock_result

        with pytest.raises(SessionExpiredError):
            await service.chat(
                db=mock_db,
                session_id=sample_expired_session.session_id,
                message="Hello",
            )

    @pytest.mark.asyncio
    async def test_chat_awaiting_approval_returns_pending(
        self, sample_awaiting_approval_session: AgentSession
    ) -> None:
        """Should return pending message when awaiting approval."""
        service = AgentService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_awaiting_approval_session
        mock_db.execute.return_value = mock_result

        response = await service.chat(
            db=mock_db,
            session_id=sample_awaiting_approval_session.session_id,
            message="Hello",
        )

        assert response.pending_approval is True
        assert response.pending_action is not None
        assert "awaiting approval" in response.message.lower()

    @pytest.mark.asyncio
    async def test_chat_success(
        self,
        sample_active_session: AgentSession,
        sample_experiment_report: ExperimentReport,
    ) -> None:
        """Should process chat and return response."""
        service = AgentService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        # Mock agent
        mock_agent = MagicMock()
        mock_agent_result = MagicMock()
        mock_agent_result.output = sample_experiment_report
        mock_usage = MagicMock()
        mock_usage.total_tokens = 100
        mock_agent_result.usage.return_value = mock_usage
        mock_agent_result.all_messages.return_value = []
        mock_agent.run = AsyncMock(return_value=mock_agent_result)

        with patch.object(service, "_get_agent", return_value=mock_agent):
            response = await service.chat(
                db=mock_db,
                session_id=sample_active_session.session_id,
                message="Run experiment",
            )

        assert response.session_id == sample_active_session.session_id
        assert response.tokens_used == 100
        mock_agent.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_model_misbehavior_returns_friendly_message(
        self,
        sample_active_session: AgentSession,
    ) -> None:
        """A misbehaving model should yield a clean message, not crash.

        Regression for issue #164: a tool call exceeding its retry budget
        raised PydanticAI's `UnexpectedModelBehavior`, whose raw string
        ("Tool '...' exceeded max retries count of 1") leaked to the user.
        """
        service = AgentService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(
            side_effect=UnexpectedModelBehavior(
                "Tool 'tool_compare_backtest_results' exceeded max retries count of 1"
            )
        )

        with patch.object(service, "_get_agent", return_value=mock_agent):
            response = await service.chat(
                db=mock_db,
                session_id=sample_active_session.session_id,
                message="Hello",
            )

        assert response.session_id == sample_active_session.session_id
        assert response.pending_approval is False
        assert "invalid tool call" in response.message
        assert "exceeded max retries" not in response.message

    @pytest.mark.asyncio
    async def test_chat_finalizer_salvages_answer_on_misbehavior(
        self,
        sample_active_session: AgentSession,
    ) -> None:
        """When tools fetched data but structured output failed, salvage a reply (#351).

        A weak local model calls the read tool and gets the data, then can't wrap
        it in the ExperimentReport schema and exhausts the output-retry budget.
        The service then asks a tool-less finalizer to answer in plain text — the
        user gets the answer instead of the generic "invalid tool call" error.
        """
        service = AgentService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(
            side_effect=UnexpectedModelBehavior("Exceeded maximum output retries (3)")
        )

        salvaged_answer = "The lowest WAPE is the naive run 2fad611b (18.93)."
        with (
            patch.object(service, "_get_agent", return_value=mock_agent),
            patch.object(
                service,
                "_salvage_plaintext_answer",
                AsyncMock(return_value=salvaged_answer),
            ),
        ):
            response = await service.chat(
                db=mock_db,
                session_id=sample_active_session.session_id,
                message="List the most recent model runs and tell me which has the lowest WAPE.",
            )

        assert response.message == salvaged_answer
        assert response.pending_approval is False
        assert "invalid tool call" not in response.message

    @pytest.mark.asyncio
    async def test_chat_runs_tools_sequentially(
        self,
        sample_active_session: AgentSession,
        sample_experiment_report: ExperimentReport,
    ) -> None:
        """chat() must run the agent under sequential tool execution.

        Regression for issue #172: every tool shares the single AgentDeps.db
        AsyncSession, so concurrent tool calls raised SQLAlchemy's
        InvalidRequestError. The service must enter PydanticAI's public
        ``Agent.parallel_tool_call_execution_mode("sequential")`` context
        around the agent run.
        """
        service = AgentService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        run_result = MagicMock()
        run_result.output = sample_experiment_report
        usage = MagicMock()
        usage.total_tokens = 1
        run_result.usage.return_value = usage
        run_result.all_messages.return_value = []

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=run_result)

        with (
            patch.object(service, "_get_agent", return_value=mock_agent),
            patch.object(Agent, "parallel_tool_call_execution_mode") as mock_mode,
        ):
            await service.chat(
                db=mock_db,
                session_id=sample_active_session.session_id,
                message="Run a backtest",
            )

        mock_mode.assert_called_once_with("sequential")

    @pytest.mark.asyncio
    async def test_chat_fallback_exhausted_raises_classified_error(
        self,
        sample_active_session: AgentSession,
    ) -> None:
        """A FallbackExceptionGroup from agent.run must raise the classified
        502 AgentFallbackExhaustedError, not bubble the raw group (#335)."""
        service = AgentService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        group = FallbackExceptionGroup(
            "All models from FallbackModel failed",
            [
                ModelHTTPError(
                    404,
                    "google-gla:gemini-3-flash-preview",
                    body={"error": {"message": "models/gemini-3-flash-preview is not found"}},
                ),
                ModelHTTPError(
                    429,
                    "google-gla:gemini-2.5-flash",
                    body={"error": {"message": "RESOURCE_EXHAUSTED key AIzaFakeKey123456789"}},
                ),
            ],
        )
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=group)

        with patch.object(service, "_get_agent", return_value=mock_agent):
            with pytest.raises(AgentFallbackExhaustedError) as exc_info:
                await service.chat(
                    db=mock_db,
                    session_id=sample_active_session.session_id,
                    message="Hello",
                )

        exc = exc_info.value
        assert exc.status_code == 502
        assert exc.code == "AGENT_FALLBACK_EXHAUSTED"
        failures = exc.extensions["failures"]
        assert len(failures) == 2
        assert failures[0]["reason"] == "model_not_found"
        assert failures[1]["reason"] == "quota_exhausted"
        assert "sub-exceptions" not in exc.message
        # Issue #335 hard constraint: no secret-like material anywhere.
        serialized = json.dumps({"message": exc.message, "extensions": exc.extensions})
        assert "AIza" not in serialized


class TestAgentServiceStreamChat:
    """Tests for streaming chat functionality."""

    @pytest.mark.asyncio
    async def test_stream_chat_model_misbehavior_yields_error_event(
        self,
        sample_active_session: AgentSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A misbehaving model should yield a recoverable `error` event, not crash.

        Regression for issue #164: `UnexpectedModelBehavior` raised inside
        `agent.run_stream` bubbled to the WebSocket handler, which echoed the
        raw exception string to the client.
        """
        service = AgentService()
        # Pin a streaming-capable (cloud) provider so this exercises the
        # run_stream path regardless of the local .env (#342).
        monkeypatch.setattr(service.settings, "agent_default_model", "anthropic:claude-test")
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        class _RaisingStream:
            """Async context manager that fails on entry like a misbehaving run."""

            async def __aenter__(self) -> Any:
                raise UnexpectedModelBehavior(
                    "Tool 'tool_compare_backtest_results' exceeded max retries count of 1"
                )

            async def __aexit__(self, *exc: object) -> bool:
                return False

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_RaisingStream())

        with patch.object(service, "_get_agent", return_value=mock_agent):
            events = [
                event
                async for event in service.stream_chat(
                    db=mock_db,
                    session_id=sample_active_session.session_id,
                    message="Hello",
                )
            ]

        assert len(events) == 1
        assert events[0].event_type == "error"
        assert events[0].data["recoverable"] is True
        assert events[0].data["error_type"] == "model_behavior_error"
        assert "exceeded max retries" not in events[0].data["error"]
        # failures is exclusive to fallback_exhausted events (#335).
        assert "failures" not in events[0].data

    @pytest.mark.asyncio
    async def test_stream_chat_fallback_exhausted_yields_classified_error(
        self,
        sample_active_session: AgentSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """All fallback legs failing must yield ONE classified `error` event
        with per-model failures — never the raw group string (#335)."""
        service = AgentService()
        # Pin a streaming-capable (cloud) provider so this exercises the
        # run_stream path regardless of the local .env (#342).
        monkeypatch.setattr(service.settings, "agent_default_model", "anthropic:claude-test")
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        class _RaisingStream:
            """Async context manager that fails on entry like an exhausted chain."""

            async def __aenter__(self) -> Any:
                raise FallbackExceptionGroup(
                    "All models from FallbackModel failed",
                    [
                        ModelHTTPError(
                            404,
                            "google-gla:gemini-3-flash-preview",
                            body={
                                "error": {"message": "models/gemini-3-flash-preview is not found"}
                            },
                        ),
                        ModelHTTPError(
                            429,
                            "google-gla:gemini-2.5-flash",
                            body={
                                "error": {"message": "RESOURCE_EXHAUSTED key AIzaFakeKey123456789"}
                            },
                        ),
                    ],
                )

            async def __aexit__(self, *exc: object) -> bool:
                return False

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_RaisingStream())

        with patch.object(service, "_get_agent", return_value=mock_agent):
            events = [
                event
                async for event in service.stream_chat(
                    db=mock_db,
                    session_id=sample_active_session.session_id,
                    message="Hello",
                )
            ]

        assert len(events) == 1
        assert events[0].event_type == "error"
        assert events[0].data["error_type"] == "fallback_exhausted"
        assert events[0].data["recoverable"] is True
        failures = events[0].data["failures"]
        assert len(failures) == 2
        assert failures[0]["reason"] == "model_not_found"
        assert failures[1]["reason"] == "quota_exhausted"
        assert "google-gla:gemini-3-flash-preview" in events[0].data["error"]
        assert "google-gla:gemini-2.5-flash" in events[0].data["error"]
        # The opaque group string must never reach the client.
        assert "sub-exceptions" not in events[0].data["error"]
        # Issue #335 hard constraint: no secret-like material anywhere.
        assert "AIza" not in json.dumps(events[0].model_dump(mode="json"))

    @pytest.mark.asyncio
    async def test_stream_chat_bare_model_api_error_classified(
        self,
        sample_active_session: AgentSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A bare ModelAPIError (single-model config, no fallback wired) gets
        the same classified treatment as a 1-element failures list (#335)."""
        service = AgentService()
        monkeypatch.setattr(service.settings, "agent_default_model", "anthropic:claude-test")
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        class _RaisingStream:
            """Async context manager that fails on entry like a provider 401."""

            async def __aenter__(self) -> Any:
                raise ModelHTTPError(401, "anthropic:claude-test")

            async def __aexit__(self, *exc: object) -> bool:
                return False

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_RaisingStream())

        with patch.object(service, "_get_agent", return_value=mock_agent):
            events = [
                event
                async for event in service.stream_chat(
                    db=mock_db,
                    session_id=sample_active_session.session_id,
                    message="Hello",
                )
            ]

        assert len(events) == 1
        assert events[0].event_type == "error"
        assert events[0].data["error_type"] == "fallback_exhausted"
        failures = events[0].data["failures"]
        assert len(failures) == 1
        assert failures[0]["reason"] == "auth_error"
        assert failures[0]["model_name"] == "anthropic:claude-test"

    @pytest.mark.asyncio
    async def test_chat_surfaces_pending_action_on_model_misbehavior(
        self,
        sample_active_session: AgentSession,
    ) -> None:
        """A gated tool that fired before the model misbehaved must surface the
        Approve card, not the generic error (#344).

        A gated tool records ``deps.pending_action`` the moment it fires, but a
        weak model can ramble past the gate and exhaust its retry budget, so
        ``agent.run`` raises ``UnexpectedModelBehavior`` before returning. The
        captured approval is valid and must not be discarded.
        """
        service = AgentService()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        def _fire_gate_then_misbehave(*_args: Any, **kwargs: Any) -> None:
            deps: AgentDeps = kwargs["deps"]
            deps.set_pending_action(
                "create_alias",
                {"alias_name": "champion", "run_id": "1" * 32},
                "Create alias champion",
            )
            raise UnexpectedModelBehavior("Exceeded maximum output retries (3)")

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=_fire_gate_then_misbehave)

        with patch.object(service, "_get_agent", return_value=mock_agent):
            response = await service.chat(
                db=mock_db,
                session_id=sample_active_session.session_id,
                message="Create alias champion. Call tool_create_alias now.",
            )

        assert response.pending_approval is True
        assert response.pending_action is not None
        assert response.pending_action.action_type == "create_alias"
        assert response.pending_action.arguments["alias_name"] == "champion"
        assert "invalid tool call" not in response.message
        # Session flipped so POST /approve can find the action.
        assert sample_active_session.status == SessionStatus.AWAITING_APPROVAL.value
        assert sample_active_session.pending_action is not None

    @pytest.mark.asyncio
    async def test_stream_chat_surfaces_approval_on_model_misbehavior(
        self,
        sample_active_session: AgentSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The streaming path must emit ``approval_required`` (not ``error``)
        when a gated tool fired before the model misbehaved (#344)."""
        service = AgentService()
        # Pin ollama so stream_chat uses the non-streaming run() path (#342) —
        # the real-world scenario where this surfaced.
        monkeypatch.setattr(service.settings, "agent_default_model", "ollama:qwen3:8b")
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        def _fire_gate_then_misbehave(*_args: Any, **kwargs: Any) -> None:
            deps: AgentDeps = kwargs["deps"]
            deps.set_pending_action(
                "create_alias",
                {"alias_name": "champion", "run_id": "1" * 32},
                "Create alias champion",
            )
            raise UnexpectedModelBehavior("Exceeded maximum output retries (3)")

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=_fire_gate_then_misbehave)

        with patch.object(service, "_get_agent", return_value=mock_agent):
            events = [
                event
                async for event in service.stream_chat(
                    db=mock_db,
                    session_id=sample_active_session.session_id,
                    message="Create alias champion. Call tool_create_alias now.",
                )
            ]

        event_types = [event.event_type for event in events]
        assert "approval_required" in event_types
        assert "error" not in event_types
        approval = next(e for e in events if e.event_type == "approval_required")
        assert approval.data["action"].action_type == "create_alias"
        assert sample_active_session.status == SessionStatus.AWAITING_APPROVAL.value

    @pytest.mark.asyncio
    async def test_stream_chat_runs_tools_sequentially(
        self,
        sample_active_session: AgentSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """stream_chat() must also run the agent under sequential tool execution.

        Mirrors test_chat_runs_tools_sequentially for the streaming path so a
        future change to only one code path cannot silently reintroduce the
        concurrent-session bug from issue #172.
        """
        service = AgentService()
        # Pin a streaming-capable (cloud) provider so this exercises the
        # run_stream path regardless of the local .env (#342).
        monkeypatch.setattr(service.settings, "agent_default_model", "anthropic:claude-test")
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        class _StubStream:
            """Minimal async-context-manager stand-in for agent.run_stream(...)."""

            async def __aenter__(self) -> MagicMock:
                stream = MagicMock()

                async def _stream_text() -> AsyncIterator[str]:
                    yield "hello"

                stream.stream_text = _stream_text
                stream.get_output = AsyncMock(return_value=None)
                usage = MagicMock()
                usage.total_tokens = 1
                stream.usage.return_value = usage
                stream.all_messages.return_value = []
                return stream

            async def __aexit__(self, *exc: object) -> bool:
                return False

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_StubStream())

        with (
            patch.object(service, "_get_agent", return_value=mock_agent),
            patch.object(Agent, "parallel_tool_call_execution_mode") as mock_mode,
        ):
            async for _event in service.stream_chat(
                db=mock_db,
                session_id=sample_active_session.session_id,
                message="Run a backtest",
            ):
                pass

        mock_mode.assert_called_once_with("sequential")

    @pytest.mark.asyncio
    async def test_stream_chat_ollama_uses_nonstreaming_path(
        self,
        sample_active_session: AgentSession,
        sample_experiment_report: ExperimentReport,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """#342 — an ollama agent uses agent.run() (not run_stream).

        Ollama's OpenAI-compat endpoint rejects PydanticAI's streamed request
        with 400 "invalid message content type: <nil>". The service must fall
        back to the non-streaming run() path and still emit text_delta +
        approval_required (from deps.pending_action, #336) + complete.
        """
        service = AgentService()
        monkeypatch.setattr(service.settings, "agent_default_model", "ollama:qwen3:8b")
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        def _run(message: str, *, deps: AgentDeps, message_history: Any) -> MagicMock:
            # A gated tool fired during the run and recorded an approval request.
            deps.set_pending_action(
                "save_scenario",
                {"name": "p", "run_id": "r", "store_id": 1, "product_id": 2},
                "Save scenario plan 'p'",
            )
            res = MagicMock()
            res.output = sample_experiment_report  # has a non-empty summary
            usage = MagicMock()
            usage.total_tokens = 11
            res.usage.return_value = usage
            res.all_messages.return_value = []
            return res

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=_run)
        mock_agent.run_stream = MagicMock(
            side_effect=AssertionError("run_stream must not be called for the ollama provider")
        )

        with patch.object(service, "_get_agent", return_value=mock_agent):
            events = [
                event
                async for event in service.stream_chat(
                    db=mock_db,
                    session_id=sample_active_session.session_id,
                    message="Save a what-if scenario plan",
                )
            ]

        types = [e.event_type for e in events]
        assert "text_delta" in types  # full reply emitted as one delta
        assert "approval_required" in types
        assert types[-1] == "complete"
        approval = next(e for e in events if e.event_type == "approval_required")
        assert approval.data["action"].action_type == "save_scenario"
        mock_agent.run.assert_awaited_once()
        mock_agent.run_stream.assert_not_called()
        assert sample_active_session.status == SessionStatus.AWAITING_APPROVAL.value

    @pytest.mark.asyncio
    async def test_stream_chat_cloud_keeps_streaming_path(
        self,
        sample_active_session: AgentSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Regression guard for #342 — a cloud provider keeps the run_stream path."""
        service = AgentService()
        monkeypatch.setattr(service.settings, "agent_default_model", "anthropic:claude-test")
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        class _StubStream:
            async def __aenter__(self) -> MagicMock:
                stream = MagicMock()

                async def _stream_text() -> AsyncIterator[str]:
                    yield "hello"

                stream.stream_text = _stream_text
                stream.get_output = AsyncMock(return_value=None)
                usage = MagicMock()
                usage.total_tokens = 1
                stream.usage.return_value = usage
                stream.all_messages.return_value = []
                return stream

            async def __aexit__(self, *exc: object) -> bool:
                return False

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=_StubStream())
        mock_agent.run = AsyncMock(
            side_effect=AssertionError("run must not be called for a cloud provider")
        )

        with patch.object(service, "_get_agent", return_value=mock_agent):
            events = [
                event
                async for event in service.stream_chat(
                    db=mock_db,
                    session_id=sample_active_session.session_id,
                    message="hello",
                )
            ]

        mock_agent.run_stream.assert_called_once()
        mock_agent.run.assert_not_called()
        assert any(e.event_type == "complete" for e in events)


class TestAgentServiceApproval:
    """Tests for approval workflow."""

    @pytest.mark.asyncio
    async def test_approve_session_not_found_raises(self) -> None:
        """Should raise SessionNotFoundError."""
        service = AgentService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(SessionNotFoundError):
            await service.approve_action(
                db=mock_db,
                session_id="nonexistent",
                action_id="action123",
                approved=True,
            )

    @pytest.mark.asyncio
    async def test_approve_no_pending_action_raises(
        self, sample_active_session: AgentSession
    ) -> None:
        """Should raise NoApprovalPendingError when no action pending."""
        service = AgentService()
        mock_db = AsyncMock()

        sample_active_session.pending_action = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        with pytest.raises(NoApprovalPendingError):
            await service.approve_action(
                db=mock_db,
                session_id=sample_active_session.session_id,
                action_id="action123",
                approved=True,
            )

    @pytest.mark.asyncio
    async def test_approve_wrong_action_id_raises(
        self, sample_awaiting_approval_session: AgentSession
    ) -> None:
        """Should raise NoApprovalPendingError for wrong action ID."""
        service = AgentService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_awaiting_approval_session
        mock_db.execute.return_value = mock_result

        with pytest.raises(NoApprovalPendingError, match="Action not found"):
            await service.approve_action(
                db=mock_db,
                session_id=sample_awaiting_approval_session.session_id,
                action_id="wrong_action_id",
                approved=True,
            )

    @pytest.mark.asyncio
    async def test_approve_action_approved(
        self, sample_awaiting_approval_session: AgentSession
    ) -> None:
        """Should approve action and return executed status."""
        service = AgentService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_awaiting_approval_session
        mock_db.execute.return_value = mock_result

        # Mock the _execute_pending_action method to return success
        service._execute_pending_action = AsyncMock(  # type: ignore[method-assign]
            return_value={"message": "Alias created successfully", "alias_name": "production"}
        )

        pending = sample_awaiting_approval_session.pending_action
        assert pending is not None
        action_id = pending["action_id"]
        response = await service.approve_action(
            db=mock_db,
            session_id=sample_awaiting_approval_session.session_id,
            action_id=action_id,
            approved=True,
        )

        assert response.approved is True
        assert response.status == "executed"
        assert sample_awaiting_approval_session.pending_action is None
        assert sample_awaiting_approval_session.status == SessionStatus.ACTIVE.value
        # Verify _execute_pending_action was called with correct arguments
        service._execute_pending_action.assert_called_once_with(
            db=mock_db,
            action_type="create_alias",
            arguments={"alias_name": "production", "run_id": "abc123"},
        )

    @pytest.mark.asyncio
    async def test_approve_action_rejected(
        self, sample_awaiting_approval_session: AgentSession
    ) -> None:
        """Should reject action and return rejected status."""
        service = AgentService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_awaiting_approval_session
        mock_db.execute.return_value = mock_result

        pending = sample_awaiting_approval_session.pending_action
        assert pending is not None
        action_id = pending["action_id"]
        response = await service.approve_action(
            db=mock_db,
            session_id=sample_awaiting_approval_session.session_id,
            action_id=action_id,
            approved=False,
            reason="Not ready for production",
        )

        assert response.approved is False
        assert response.status == "rejected"


class TestAgentServiceCloseSession:
    """Tests for session closing."""

    @pytest.mark.asyncio
    async def test_close_session_found(self, sample_active_session: AgentSession) -> None:
        """Should close session and return True."""
        service = AgentService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        result = await service.close_session(
            db=mock_db,
            session_id=sample_active_session.session_id,
        )

        assert result is True
        assert sample_active_session.status == SessionStatus.CLOSED.value
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_session_not_found(self) -> None:
        """Should return False for nonexistent session."""
        service = AgentService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.close_session(
            db=mock_db,
            session_id="nonexistent",
        )

        assert result is False


class TestAgentServiceMessageSerialization:
    """Tests for message serialization/deserialization."""

    def test_serialize_empty_messages(self) -> None:
        """Should handle empty message list."""
        service = AgentService()
        result = service._serialize_messages([])
        assert result == []

    def test_deserialize_empty_messages(self) -> None:
        """Should handle empty message data."""
        service = AgentService()
        result = service._deserialize_messages([], "test-session")
        assert result == []

    def test_serialize_deserialize_roundtrip(self) -> None:
        """Messages should round-trip back into real ModelMessage objects.

        Regression for issue #166: _deserialize_messages used to return raw
        dicts, which crashed PydanticAI 1.96 when it accessed `conversation_id`
        on the history items.
        """
        service = AgentService()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="run a backtest")]),
            ModelResponse(parts=[TextPart(content="done")]),
        ]

        serialized = service._serialize_messages(messages)
        # Serialized form must survive a JSONB write (pure JSON types only).
        json.dumps(serialized)

        restored = service._deserialize_messages(serialized, "test-session")

        assert [type(m).__name__ for m in restored] == ["ModelRequest", "ModelResponse"]
        # The attribute whose absence on a dict caused the original crash.
        assert restored[0].conversation_id is None

    def test_deserialize_legacy_format_returns_empty(self) -> None:
        """Unparseable (pre-#166) stored history degrades to empty, not a crash."""
        service = AgentService()
        legacy: list[dict[str, Any]] = [{"type": "ModelRequest", "data": "<str dump>"}]
        result = service._deserialize_messages(legacy, "test-session")
        assert result == []

    def test_deserialize_non_validation_error_returns_empty(self) -> None:
        """Any deserialization failure degrades to empty, not only ValidationError."""
        service = AgentService()
        data: list[dict[str, Any]] = [{"kind": "request", "parts": []}]
        with patch(
            "app.features.agents.service.ModelMessagesTypeAdapter.validate_python",
            side_effect=TypeError("unexpected adapter failure"),
        ):
            result = service._deserialize_messages(data, "test-session")
        assert result == []


class TestAgentServicePendingActionFormat:
    """Tests for pending action formatting."""

    def test_format_pending_action_none(self) -> None:
        """Should return None for None input."""
        service = AgentService()
        result = service._format_pending_action(None)
        assert result is None

    def test_format_pending_action_valid(self) -> None:
        """Should format valid pending action."""
        service = AgentService()
        now = datetime.now(UTC)
        pending = {
            "action_id": "act123",
            "action_type": "create_alias",
            "description": "Create alias",
            "arguments": {"name": "prod"},
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        }

        result = service._format_pending_action(pending)

        assert result is not None
        assert result.action_id == "act123"
        assert result.action_type == "create_alias"
        assert result.description == "Create alias"
        assert result.arguments == {"name": "prod"}


class TestAgentDeps:
    """Tests for AgentDeps dataclass."""

    def test_agent_deps_creation(self, mock_db_session: AsyncMock) -> None:
        """Should create AgentDeps with defaults."""
        deps = AgentDeps(
            db=mock_db_session,
            session_id="test-123",
        )

        assert deps.db is mock_db_session
        assert deps.session_id == "test-123"
        assert deps.request_id is None
        assert deps.tool_call_count == 0

    def test_agent_deps_with_request_id(self, mock_db_session: AsyncMock) -> None:
        """Should create AgentDeps with request_id."""
        deps = AgentDeps(
            db=mock_db_session,
            session_id="test-123",
            request_id="req-456",
        )

        assert deps.request_id == "req-456"

    def test_increment_tool_calls(self, mock_db_session: AsyncMock) -> None:
        """Should increment tool call count."""
        deps = AgentDeps(
            db=mock_db_session,
            session_id="test-123",
        )

        assert deps.tool_call_count == 0
        deps.increment_tool_calls()
        assert deps.tool_call_count == 1
        deps.increment_tool_calls()
        assert deps.tool_call_count == 2

    def test_set_pending_action_records_request(self, mock_db_session: AsyncMock) -> None:
        """set_pending_action should record a machine-readable HITL request (#336)."""
        deps = AgentDeps(db=mock_db_session, session_id="test-123")
        assert deps.pending_action is None

        deps.set_pending_action(
            "save_scenario",
            {"name": "p", "run_id": "r", "store_id": 1, "product_id": 2},
            "Save scenario plan 'p'",
        )

        assert deps.pending_action is not None
        assert deps.pending_action["action_type"] == "save_scenario"
        assert deps.pending_action["arguments"]["run_id"] == "r"
        assert deps.pending_action["description"] == "Save scenario plan 'p'"


class TestAgentServiceDepsApproval:
    """Regression tests for #336 — gated tools propagate approval via deps.

    The experiment agent's structured output (ExperimentReport) carries no
    pending_action/approval_required field, so a gated tool call (e.g.
    save_scenario) used to leave the session ``active`` with no pending action
    and no ``approval_required`` event. These assert the deterministic
    deps-based path: tool -> deps.pending_action -> awaiting_approval ->
    approval_required.
    """

    @staticmethod
    def _save_scenario_pending(deps: AgentDeps) -> None:
        """Simulate the gated save_scenario tool short-circuiting for approval."""
        deps.set_pending_action(
            "save_scenario",
            {
                "name": "plan-a",
                "run_id": "702c7ce74e9848d3b11f124a71bf7b50",
                "store_id": 111,
                "product_id": 339,
                "horizon": 14,
                "assumptions": {},
                "source": "agent",
                "agent_session_id": deps.session_id,
            },
            "Save scenario plan 'plan-a' for store 111 / product 339",
        )

    @pytest.mark.asyncio
    async def test_chat_persists_pending_action_from_deps(
        self,
        sample_active_session: AgentSession,
        sample_experiment_report: ExperimentReport,
    ) -> None:
        """chat() must persist deps.pending_action even when the output lacks one."""
        service = AgentService()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        def _run(message: str, *, deps: AgentDeps, message_history: Any) -> MagicMock:
            # A gated tool fired during the run and recorded the approval request.
            self._save_scenario_pending(deps)
            res = MagicMock()
            res.output = sample_experiment_report  # no pending_action field
            usage = MagicMock()
            usage.total_tokens = 7
            res.usage.return_value = usage
            res.all_messages.return_value = []
            return res

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=_run)

        with patch.object(service, "_get_agent", return_value=mock_agent):
            response = await service.chat(
                db=mock_db,
                session_id=sample_active_session.session_id,
                message="Save a what-if scenario plan for run 702c...",
            )

        assert response.pending_approval is True
        assert response.pending_action is not None
        assert response.pending_action.action_type == "save_scenario"
        assert response.pending_action.arguments["run_id"] == "702c7ce74e9848d3b11f124a71bf7b50"
        assert sample_active_session.status == SessionStatus.AWAITING_APPROVAL.value
        assert sample_active_session.pending_action is not None
        assert sample_active_session.pending_action["action_type"] == "save_scenario"

    @pytest.mark.asyncio
    async def test_stream_chat_emits_approval_required_from_deps(
        self,
        sample_active_session: AgentSession,
        sample_experiment_report: ExperimentReport,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """stream_chat() must emit approval_required from deps.pending_action."""
        service = AgentService()
        # Pin a streaming-capable (cloud) provider so this exercises the
        # run_stream path regardless of the local .env (#342).
        monkeypatch.setattr(service.settings, "agent_default_model", "anthropic:claude-test")
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_active_session
        mock_db.execute.return_value = mock_result

        report = sample_experiment_report

        class _StubStream:
            async def __aenter__(self) -> MagicMock:
                stream = MagicMock()

                async def _stream_text() -> AsyncIterator[str]:
                    # Structured-output agents cannot stream text deltas; mirror
                    # that by yielding nothing.
                    return
                    yield  # pragma: no cover

                stream.stream_text = _stream_text
                stream.get_output = AsyncMock(return_value=report)
                usage = MagicMock()
                usage.total_tokens = 9
                stream.usage.return_value = usage
                stream.all_messages.return_value = []
                return stream

            async def __aexit__(self, *exc: object) -> bool:
                return False

        def _run_stream(message: str, *, deps: AgentDeps, message_history: Any) -> _StubStream:
            self._save_scenario_pending(deps)
            return _StubStream()

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(side_effect=_run_stream)

        with patch.object(service, "_get_agent", return_value=mock_agent):
            events = [
                event
                async for event in service.stream_chat(
                    db=mock_db,
                    session_id=sample_active_session.session_id,
                    message="Save a what-if scenario plan for run 702c...",
                )
            ]

        approval_events = [e for e in events if e.event_type == "approval_required"]
        assert len(approval_events) == 1
        assert approval_events[0].data["action"].action_type == "save_scenario"
        assert sample_active_session.status == SessionStatus.AWAITING_APPROVAL.value
        assert sample_active_session.pending_action is not None


class TestFinalizerSalvage:
    """The plain-text finalizer fallback used on structured-output failure (#351)."""

    def test_extract_tool_payloads_pulls_tool_returns(self) -> None:
        """Tool returns are extracted from a captured run trace, in order."""
        captured: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="List runs")]),
            ModelResponse(parts=[TextPart(content="{}")]),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="tool_list_runs",
                        content={"runs": [{"run_id": "abc", "wape": 18.93}]},
                        tool_call_id="call-1",
                    )
                ]
            ),
        ]

        payloads = AgentService._extract_tool_payloads(captured)

        assert payloads == [
            {"tool": "tool_list_runs", "result": {"runs": [{"run_id": "abc", "wape": 18.93}]}}
        ]

    def test_extract_tool_payloads_empty_when_no_tool_returns(self) -> None:
        """No tool returns (model failed before any tool ran) yields an empty list."""
        captured: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="List runs")]),
            ModelResponse(parts=[TextPart(content='{"runs": []}')]),
        ]

        assert AgentService._extract_tool_payloads(captured) == []

    @pytest.mark.asyncio
    async def test_salvage_returns_none_without_tool_data(self) -> None:
        """With no captured tool data, salvage returns None (caller emits the error)."""
        service = AgentService()
        result = await service._salvage_plaintext_answer("any question", [])
        assert result is None

    def test_compact_for_finalizer_strips_verbose_keys_keeps_metrics(self) -> None:
        """Compaction drops bulky config/runtime blobs but keeps identity + metrics (#351).

        Regression for the finalizer reporting 99.0 as "lowest WAPE" when the
        true minimum (18.93) had been truncated out of the oversized payload.
        """
        raw = [
            {
                "tool": "tool_list_runs",
                "result": {
                    "runs": [
                        {
                            "run_id": "a",
                            "model_type": "seasonal_naive",
                            "metrics": {"wape": 99.0},
                            "model_config_data": {"x": "y" * 500},
                            "runtime_info": {"python": "3.12"},
                            "artifact_uri": "demo/seasonal-model_a.joblib",
                        },
                        {
                            "run_id": "b",
                            "model_type": "naive",
                            "metrics": {"wape": 18.93},
                            "feature_config": {"lots": "of stuff"},
                        },
                    ]
                },
            }
        ]

        compact = cast(list[dict[str, Any]], AgentService._compact_for_finalizer(raw))
        runs = compact[0]["result"]["runs"]

        # Identity + metrics survive for BOTH runs (so a ranking sees 18.93).
        assert runs[0]["run_id"] == "a"
        assert runs[0]["metrics"] == {"wape": 99.0}
        assert runs[1]["run_id"] == "b"
        assert runs[1]["metrics"] == {"wape": 18.93}
        # Verbose blobs are gone.
        assert "model_config_data" not in runs[0]
        assert "runtime_info" not in runs[0]
        assert "artifact_uri" not in runs[0]
        assert "feature_config" not in runs[1]
