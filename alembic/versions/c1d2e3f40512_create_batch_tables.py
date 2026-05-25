"""create_batch_tables

Revision ID: c1d2e3f40512
Revises: f84258c4cb44
Create Date: 2026-05-20 10:30:00.000000

Creates the batch_job + batch_job_item tables for PRP-33 batch-runner MVP.
The forward-compat columns on batch_job (running_items, cancelled_items,
max_parallel, default_child_priority) and batch_job_item (priority) are
MVP-owned per the PRP's Cross-Slice Coordination Matrix — the four
downstream INITIALs (parallel-execution, priority-queue, export-and-retry,
champion-and-heatmap) consume them without further schema changes.

The partial picker index predicate is EXACTLY ``WHERE (status = 'pending')``
— downstream-2 (priority queue) compiles against the same predicate so the
picker SELECT remains index-covered when CANCELLED rows enter the table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f40512"
down_revision: str | None = "f84258c4cb44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply migration."""
    # ------------------------------------------------------------------
    # batch_job — parent record, one row per submission.
    # ------------------------------------------------------------------
    op.create_table(
        "batch_job",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=30), nullable=False),
        sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_configs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("running_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancelled_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_parallel", sa.Integer(), nullable=False, server_default="4"),
        sa.Column(
            "default_child_priority",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('pending', 'running', 'completed', 'failed', 'partial', 'cancelled')",
            name="ck_batch_job_valid_status",
        ),
        sa.CheckConstraint(
            "operation IN ('train', 'predict', 'backtest', 'train_backtest_register')",
            name="ck_batch_job_valid_operation",
        ),
        sa.CheckConstraint(
            "default_child_priority BETWEEN -1 AND 2",
            name="ck_batch_job_priority_band",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_batch_job_batch_id"), "batch_job", ["batch_id"], unique=True)
    op.create_index(op.f("ix_batch_job_status"), "batch_job", ["status"], unique=False)
    op.create_index(op.f("ix_batch_job_operation"), "batch_job", ["operation"], unique=False)
    op.create_index(
        "ix_batch_job_status_created",
        "batch_job",
        ["status", "created_at"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # batch_job_item — child record, one row per (store, product, model) triple.
    # FK CASCADE on batch_id so deleting a parent removes its items.
    # ------------------------------------------------------------------
    op.create_table(
        "batch_job_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.String(length=32), nullable=False),
        sa.Column("batch_id", sa.String(length=32), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("model_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("child_job_id", sa.String(length=32), nullable=True),
        sa.Column("child_run_id", sa.String(length=32), nullable=True),
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
            name="ck_batch_job_item_valid_status",
        ),
        sa.CheckConstraint(
            "priority BETWEEN -1 AND 2",
            name="ck_batch_job_item_priority_band",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["batch_job.batch_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_batch_job_item_item_id"),
        "batch_job_item",
        ["item_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_batch_job_item_batch_id"),
        "batch_job_item",
        ["batch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_batch_job_item_store_id"),
        "batch_job_item",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_batch_job_item_product_id"),
        "batch_job_item",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_batch_job_item_status"),
        "batch_job_item",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_batch_job_item_child_job_id"),
        "batch_job_item",
        ["child_job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_batch_job_item_child_run_id"),
        "batch_job_item",
        ["child_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_batch_job_item_batch_status",
        "batch_job_item",
        ["batch_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_batch_job_item_metrics_gin",
        "batch_job_item",
        ["metrics"],
        unique=False,
        postgresql_using="gin",
    )
    # Partial picker index — load-bearing for downstream-1 (parallel) and
    # downstream-2 (priority). Predicate is EXACTLY ``status = 'pending'`` —
    # the integration test asserts the substring on pg_indexes.indexdef.
    op.create_index(
        "ix_batch_job_item_picker",
        "batch_job_item",
        ["batch_id", "status", "priority", "created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    """Revert migration."""
    op.drop_index("ix_batch_job_item_picker", table_name="batch_job_item")
    op.drop_index(
        "ix_batch_job_item_metrics_gin",
        table_name="batch_job_item",
        postgresql_using="gin",
    )
    op.drop_index("ix_batch_job_item_batch_status", table_name="batch_job_item")
    op.drop_index(op.f("ix_batch_job_item_child_run_id"), table_name="batch_job_item")
    op.drop_index(op.f("ix_batch_job_item_child_job_id"), table_name="batch_job_item")
    op.drop_index(op.f("ix_batch_job_item_status"), table_name="batch_job_item")
    op.drop_index(op.f("ix_batch_job_item_product_id"), table_name="batch_job_item")
    op.drop_index(op.f("ix_batch_job_item_store_id"), table_name="batch_job_item")
    op.drop_index(op.f("ix_batch_job_item_batch_id"), table_name="batch_job_item")
    op.drop_index(op.f("ix_batch_job_item_item_id"), table_name="batch_job_item")
    op.drop_table("batch_job_item")
    op.drop_index("ix_batch_job_status_created", table_name="batch_job")
    op.drop_index(op.f("ix_batch_job_operation"), table_name="batch_job")
    op.drop_index(op.f("ix_batch_job_status"), table_name="batch_job")
    op.drop_index(op.f("ix_batch_job_batch_id"), table_name="batch_job")
    op.drop_table("batch_job")
