"""Unit tests for agent ORM models."""

import uuid
from datetime import UTC, datetime, timedelta

from app.features.agents.models import AgentSession, AgentType, SessionStatus


class TestAgentTypeEnum:
    """Tests for AgentType enum."""

    def test_experiment_value(self) -> None:
        """Should have experiment value."""
        assert AgentType.EXPERIMENT.value == "experiment"

    def test_rag_assistant_value(self) -> None:
        """Should have rag_assistant value."""
        assert AgentType.RAG_ASSISTANT.value == "rag_assistant"

    def test_enum_membership(self) -> None:
        """Should have expected members."""
        assert len(AgentType) == 2
        assert AgentType.EXPERIMENT in AgentType
        assert AgentType.RAG_ASSISTANT in AgentType


class TestSessionStatusEnum:
    """Tests for SessionStatus enum."""

    def test_active_value(self) -> None:
        """Should have active value."""
        assert SessionStatus.ACTIVE.value == "active"

    def test_awaiting_approval_value(self) -> None:
        """Should have awaiting_approval value."""
        assert SessionStatus.AWAITING_APPROVAL.value == "awaiting_approval"

    def test_closed_value(self) -> None:
        """Should have closed value."""
        assert SessionStatus.CLOSED.value == "closed"

    def test_expired_value(self) -> None:
        """Should have expired value."""
        assert SessionStatus.EXPIRED.value == "expired"

    def test_enum_membership(self) -> None:
        """Should have expected members."""
        assert len(SessionStatus) == 4


class TestAgentSessionModel:
    """Tests for AgentSession ORM model."""

    def test_create_session(self) -> None:
        """Should create session with required fields."""
        session_id = uuid.uuid4().hex
        now = datetime.now(UTC)

        session = AgentSession(
            session_id=session_id,
            agent_type=AgentType.EXPERIMENT.value,
            status=SessionStatus.ACTIVE.value,
            message_history=[],
            total_tokens_used=0,
            tool_calls_count=0,
            last_activity=now,
            expires_at=now + timedelta(minutes=30),
        )

        assert session.session_id == session_id
        assert session.agent_type == "experiment"
        assert session.status == "active"
        assert session.message_history == []
        assert session.pending_action is None

    def test_create_session_with_history(self) -> None:
        """Should create session with message history."""
        now = datetime.now(UTC)
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        session = AgentSession(
            session_id=uuid.uuid4().hex,
            agent_type=AgentType.RAG_ASSISTANT.value,
            status=SessionStatus.ACTIVE.value,
            message_history=history,
            total_tokens_used=50,
            tool_calls_count=0,
            last_activity=now,
            expires_at=now + timedelta(minutes=30),
        )

        assert len(session.message_history) == 2
        assert session.message_history[0]["role"] == "user"

    def test_create_session_with_pending_action(self) -> None:
        """Should create session with pending action."""
        now = datetime.now(UTC)
        pending = {
            "action_id": "act123",
            "action_type": "create_alias",
            "description": "Create alias",
            "arguments": {"name": "prod"},
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        }

        session = AgentSession(
            session_id=uuid.uuid4().hex,
            agent_type=AgentType.EXPERIMENT.value,
            status=SessionStatus.AWAITING_APPROVAL.value,
            message_history=[],
            pending_action=pending,
            total_tokens_used=100,
            tool_calls_count=3,
            last_activity=now,
            expires_at=now + timedelta(minutes=30),
        )

        assert session.pending_action is not None
        assert session.pending_action["action_id"] == "act123"
        assert session.status == "awaiting_approval"

    def test_session_tracking_fields(self) -> None:
        """Should track tokens and tool calls."""
        now = datetime.now(UTC)

        session = AgentSession(
            session_id=uuid.uuid4().hex,
            agent_type=AgentType.EXPERIMENT.value,
            status=SessionStatus.ACTIVE.value,
            message_history=[],
            total_tokens_used=1500,
            tool_calls_count=12,
            last_activity=now,
            expires_at=now + timedelta(minutes=30),
        )

        assert session.total_tokens_used == 1500
        assert session.tool_calls_count == 12

    def test_session_expiration(self) -> None:
        """Should track expiration time."""
        now = datetime.now(UTC)
        expires = now + timedelta(minutes=30)

        session = AgentSession(
            session_id=uuid.uuid4().hex,
            agent_type=AgentType.EXPERIMENT.value,
            status=SessionStatus.ACTIVE.value,
            message_history=[],
            total_tokens_used=0,
            tool_calls_count=0,
            last_activity=now,
            expires_at=expires,
        )

        assert session.expires_at == expires
        assert session.last_activity == now

    def test_session_id_format(self) -> None:
        """Session ID should be 32-char hex string."""
        session_id = uuid.uuid4().hex

        assert len(session_id) == 32
        assert all(c in "0123456789abcdef" for c in session_id)

    def test_update_session_status(self) -> None:
        """Should update session status."""
        now = datetime.now(UTC)

        session = AgentSession(
            session_id=uuid.uuid4().hex,
            agent_type=AgentType.EXPERIMENT.value,
            status=SessionStatus.ACTIVE.value,
            message_history=[],
            total_tokens_used=0,
            tool_calls_count=0,
            last_activity=now,
            expires_at=now + timedelta(minutes=30),
        )

        # Simulate status update
        session.status = SessionStatus.CLOSED.value
        assert session.status == "closed"

    def test_update_message_history(self) -> None:
        """Should update message history."""
        now = datetime.now(UTC)

        session = AgentSession(
            session_id=uuid.uuid4().hex,
            agent_type=AgentType.RAG_ASSISTANT.value,
            status=SessionStatus.ACTIVE.value,
            message_history=[],
            total_tokens_used=0,
            tool_calls_count=0,
            last_activity=now,
            expires_at=now + timedelta(minutes=30),
        )

        # Add messages
        session.message_history = [
            {"role": "user", "content": "Question?"},
            {"role": "assistant", "content": "Answer!"},
        ]
        session.total_tokens_used = 100

        assert len(session.message_history) == 2
        assert session.total_tokens_used == 100

    def test_clear_pending_action(self) -> None:
        """Should clear pending action after approval."""
        now = datetime.now(UTC)
        pending = {
            "action_id": "act123",
            "action_type": "create_alias",
        }

        session = AgentSession(
            session_id=uuid.uuid4().hex,
            agent_type=AgentType.EXPERIMENT.value,
            status=SessionStatus.AWAITING_APPROVAL.value,
            message_history=[],
            pending_action=pending,
            total_tokens_used=0,
            tool_calls_count=0,
            last_activity=now,
            expires_at=now + timedelta(minutes=30),
        )

        # Clear after approval
        session.pending_action = None
        session.status = SessionStatus.ACTIVE.value

        assert session.pending_action is None
        assert session.status == "active"
