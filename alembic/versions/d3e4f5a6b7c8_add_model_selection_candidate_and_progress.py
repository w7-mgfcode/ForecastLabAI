"""add model_selection_candidate and async progress columns

Revision ID: d3e4f5a6b7c8
Revises: b667d321603c
Create Date: 2026-06-01 09:30:00.000000

Slice B of the Forecast Champion Selector (issue #360). Converts the selection
run into a DB-backed async LRO:

- creates ``model_selection_candidate`` (one row per candidate, FK CASCADE to
  ``model_selection_run.selection_id``) carrying per-candidate status, result
  JSONB, error, and timing — the live-progress + audit surface;
- adds ``started_at`` + the four final count columns to ``model_selection_run``;
- widens the run status CheckConstraint to include ``'cancelled'`` (forward-only
  drop + recreate of the named constraint).

Mirrors ``c1d2e3f40512_create_batch_tables`` for JSONB / index / FK style.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "b667d321603c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_RUN_STATUS = "status IN ('pending', 'running', 'completed', 'partial', 'failed')"
_NEW_RUN_STATUS = (
    "status IN ('pending', 'running', 'completed', 'partial', 'failed', 'cancelled')"
)


def upgrade() -> None:
    """Apply migration."""
    # ------------------------------------------------------------------
    # 1. Widen the run status CheckConstraint to include 'cancelled'.
    # ------------------------------------------------------------------
    op.drop_constraint(
        "ck_model_selection_run_valid_status",
        "model_selection_run",
        type_="check",
    )
    op.create_check_constraint(
        "ck_model_selection_run_valid_status",
        "model_selection_run",
        _NEW_RUN_STATUS,
    )

    # ------------------------------------------------------------------
    # 2. Additive progress columns on the parent run.
    # ------------------------------------------------------------------
    op.add_column(
        "model_selection_run",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "model_selection_run",
        sa.Column("total_candidates", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "model_selection_run",
        sa.Column(
            "completed_candidates", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "model_selection_run",
        sa.Column("failed_candidates", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "model_selection_run",
        sa.Column(
            "cancelled_candidates", sa.Integer(), nullable=False, server_default="0"
        ),
    )

    # ------------------------------------------------------------------
    # 3. Per-candidate execution child table (FK CASCADE on selection_id).
    # ------------------------------------------------------------------
    op.create_table(
        "model_selection_candidate",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.String(length=32), nullable=False),
        sa.Column("selection_id", sa.String(length=32), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("model_type", sa.String(length=40), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_model_selection_candidate_valid_status",
        ),
        sa.ForeignKeyConstraint(
            ["selection_id"],
            ["model_selection_run.selection_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_model_selection_candidate_candidate_id"),
        "model_selection_candidate",
        ["candidate_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_model_selection_candidate_selection_id"),
        "model_selection_candidate",
        ["selection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_selection_candidate_status"),
        "model_selection_candidate",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_model_selection_candidate_selection_status",
        "model_selection_candidate",
        ["selection_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Revert migration."""
    op.drop_index(
        "ix_model_selection_candidate_selection_status",
        table_name="model_selection_candidate",
    )
    op.drop_index(
        op.f("ix_model_selection_candidate_status"),
        table_name="model_selection_candidate",
    )
    op.drop_index(
        op.f("ix_model_selection_candidate_selection_id"),
        table_name="model_selection_candidate",
    )
    op.drop_index(
        op.f("ix_model_selection_candidate_candidate_id"),
        table_name="model_selection_candidate",
    )
    op.drop_table("model_selection_candidate")

    op.drop_column("model_selection_run", "cancelled_candidates")
    op.drop_column("model_selection_run", "failed_candidates")
    op.drop_column("model_selection_run", "completed_candidates")
    op.drop_column("model_selection_run", "total_candidates")
    op.drop_column("model_selection_run", "started_at")

    op.drop_constraint(
        "ck_model_selection_run_valid_status",
        "model_selection_run",
        type_="check",
    )
    op.create_check_constraint(
        "ck_model_selection_run_valid_status",
        "model_selection_run",
        _OLD_RUN_STATUS,
    )
