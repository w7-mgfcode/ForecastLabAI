"""Agent session ORM models for conversation state management.

This module defines:
- SessionStatus: Valid states for an agent session
- AgentSession: Persistent conversation state with message history

CRITICAL: Uses PostgreSQL JSONB for flexible message history storage.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import TimestampMixin


class SessionStatus(str, Enum):
    """Valid states for an agent session.

    State transitions:
    - ACTIVE -> AWAITING_APPROVAL (when sensitive action pending)
    - AWAITING_APPROVAL -> ACTIVE (on approval/rejection)
    - ACTIVE -> EXPIRED (on timeout)
    - ACTIVE -> CLOSED (on explicit close)
    """

    ACTIVE = "active"
    AWAITING_APPROVAL = "awaiting_approval"
    EXPIRED = "expired"
    CLOSED = "closed"


class AgentType(str, Enum):
    """Available agent types.

    Each type has specific tool access and system prompts.
    """

    EXPERIMENT = "experiment"
    RAG_ASSISTANT = "rag_assistant"


class AgentSession(TimestampMixin, Base):
    """Agent session for tracking conversation state.

    CRITICAL: Persists full message history for session resumption.

    Attributes:
        id: Primary key.
        session_id: Unique external identifier (UUID hex, 32 chars).
        agent_type: Type of agent for this session.
        status: Current session state.
        message_history: Full conversation history as JSONB.
        pending_action: Pending approval action details as JSONB (nullable).
        total_tokens_used: Cumulative token usage.
        tool_calls_count: Number of tool invocations.
        last_activity: Last interaction timestamp.
        expires_at: Session expiration timestamp.
    """

    __tablename__ = "agent_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    agent_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(30), default=SessionStatus.ACTIVE.value, index=True)

    # Conversation state
    message_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    # Human-in-the-loop pending action
    pending_action: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Usage metrics
    total_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls_count: Mapped[int] = mapped_column(Integer, default=0)

    # Session timing
    last_activity: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    __table_args__ = (
        # GIN index for JSONB message history queries
        Index("ix_agent_session_message_history_gin", "message_history", postgresql_using="gin"),
        # Constraint: valid status values
        CheckConstraint(
            "status IN ('active', 'awaiting_approval', 'expired', 'closed')",
            name="ck_agent_session_valid_status",
        ),
    )
