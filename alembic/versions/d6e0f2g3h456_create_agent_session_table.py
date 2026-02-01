"""create_agent_session_table

Revision ID: d6e0f2g3h456
Revises: c5d9e1f2g345
Create Date: 2026-02-01 14:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d6e0f2g3h456"
down_revision: str | None = "c5d9e1f2g345"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply migration - create agent_session table."""
    op.create_table(
        "agent_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=32), nullable=False),
        sa.Column("agent_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        # Conversation state
        sa.Column(
            "message_history",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        # Human-in-the-loop pending action
        sa.Column(
            "pending_action",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        # Usage metrics
        sa.Column("total_tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_calls_count", sa.Integer(), nullable=False, server_default="0"),
        # Session timing
        sa.Column("last_activity", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        # Timestamps (from TimestampMixin)
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('active', 'awaiting_approval', 'expired', 'closed')",
            name="ck_agent_session_valid_status",
        ),
    )

    # Create indexes for agent_session
    op.create_index(
        op.f("ix_agent_session_session_id"),
        "agent_session",
        ["session_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_agent_session_agent_type"),
        "agent_session",
        ["agent_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_session_status"),
        "agent_session",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_session_expires_at"),
        "agent_session",
        ["expires_at"],
        unique=False,
    )

    # GIN index for JSONB message_history queries
    op.create_index(
        "ix_agent_session_message_history_gin",
        "agent_session",
        ["message_history"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Revert migration - drop agent_session table."""
    # Drop indexes
    op.drop_index("ix_agent_session_message_history_gin", table_name="agent_session")
    op.drop_index(op.f("ix_agent_session_expires_at"), table_name="agent_session")
    op.drop_index(op.f("ix_agent_session_status"), table_name="agent_session")
    op.drop_index(op.f("ix_agent_session_agent_type"), table_name="agent_session")
    op.drop_index(op.f("ix_agent_session_session_id"), table_name="agent_session")

    # Drop table
    op.drop_table("agent_session")
