"""Unit tests for agent service."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
        with patch(
            "app.features.agents.agents.experiment.get_experiment_agent"
        ) as mock_get:
            mock_agent = MagicMock()
            mock_get.return_value = mock_agent

            agent = service._get_agent(AgentType.EXPERIMENT.value)
            assert agent is mock_agent
            mock_get.assert_called_once()

    def test_get_agent_rag_assistant(self) -> None:
        """Should return RAG assistant agent."""
        service = AgentService()
        with patch(
            "app.features.agents.agents.rag_assistant.get_rag_assistant_agent"
        ) as mock_get:
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
    async def test_get_session_found(
        self, sample_active_session: AgentSession
    ) -> None:
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
    async def test_chat_session_expired_raises(
        self, sample_expired_session: AgentSession
    ) -> None:
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
        mock_agent_result.data = sample_experiment_report
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
    async def test_close_session_found(
        self, sample_active_session: AgentSession
    ) -> None:
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
        result = service._deserialize_messages([])
        assert result == []

    def test_deserialize_returns_raw_data(self) -> None:
        """Should return raw data for PydanticAI compatibility."""
        service = AgentService()
        data: list[dict[str, Any]] = [{"kind": "request", "parts": []}]
        result = service._deserialize_messages(data)
        # _deserialize_messages returns raw dicts for PydanticAI
        assert len(result) == 1


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
