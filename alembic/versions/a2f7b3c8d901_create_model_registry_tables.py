"""create_model_registry_tables

Revision ID: a2f7b3c8d901
Revises: e1165ebcef61
Create Date: 2026-02-01 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a2f7b3c8d901"
down_revision: Union[str, None] = "e1165ebcef61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration - create model_run and deployment_alias tables."""
    # Create model_run table
    op.create_table(
        "model_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        # Model configuration
        sa.Column("model_type", sa.String(length=50), nullable=False),
        sa.Column("model_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("feature_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("config_hash", sa.String(length=16), nullable=False),
        # Data window
        sa.Column("data_window_start", sa.Date(), nullable=False),
        sa.Column("data_window_end", sa.Date(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        # Metrics
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Artifact info
        sa.Column("artifact_uri", sa.String(length=500), nullable=True),
        sa.Column("artifact_hash", sa.String(length=64), nullable=True),
        sa.Column("artifact_size_bytes", sa.Integer(), nullable=True),
        # Environment & lineage
        sa.Column("runtime_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("agent_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("git_sha", sa.String(length=40), nullable=True),
        # Error tracking
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        # Timing
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('pending', 'running', 'success', 'failed', 'archived')",
            name="ck_model_run_valid_status",
        ),
        sa.CheckConstraint(
            "data_window_end >= data_window_start",
            name="ck_model_run_valid_data_window",
        ),
    )

    # Create indexes for model_run
    op.create_index(op.f("ix_model_run_run_id"), "model_run", ["run_id"], unique=True)
    op.create_index(op.f("ix_model_run_status"), "model_run", ["status"], unique=False)
    op.create_index(op.f("ix_model_run_model_type"), "model_run", ["model_type"], unique=False)
    op.create_index(op.f("ix_model_run_config_hash"), "model_run", ["config_hash"], unique=False)
    op.create_index(op.f("ix_model_run_store_id"), "model_run", ["store_id"], unique=False)
    op.create_index(op.f("ix_model_run_product_id"), "model_run", ["product_id"], unique=False)

    # Composite indexes
    op.create_index(
        "ix_model_run_store_product", "model_run", ["store_id", "product_id"], unique=False
    )
    op.create_index(
        "ix_model_run_data_window",
        "model_run",
        ["data_window_start", "data_window_end"],
        unique=False,
    )

    # GIN indexes for JSONB containment queries
    op.create_index(
        "ix_model_run_model_config_gin",
        "model_run",
        ["model_config"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_model_run_metrics_gin",
        "model_run",
        ["metrics"],
        unique=False,
        postgresql_using="gin",
    )

    # Create deployment_alias table
    op.create_table(
        "deployment_alias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alias_name", sa.String(length=100), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
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
        sa.ForeignKeyConstraint(["run_id"], ["model_run.id"]),
        sa.UniqueConstraint("alias_name", name="uq_deployment_alias_name"),
    )

    # Create indexes for deployment_alias
    op.create_index(
        op.f("ix_deployment_alias_alias_name"),
        "deployment_alias",
        ["alias_name"],
        unique=True,
    )
    op.create_index(
        op.f("ix_deployment_alias_run_id"), "deployment_alias", ["run_id"], unique=False
    )


def downgrade() -> None:
    """Revert migration - drop model_run and deployment_alias tables."""
    # Drop deployment_alias table and indexes
    op.drop_index(op.f("ix_deployment_alias_run_id"), table_name="deployment_alias")
    op.drop_index(op.f("ix_deployment_alias_alias_name"), table_name="deployment_alias")
    op.drop_table("deployment_alias")

    # Drop model_run indexes
    op.drop_index("ix_model_run_metrics_gin", table_name="model_run")
    op.drop_index("ix_model_run_model_config_gin", table_name="model_run")
    op.drop_index("ix_model_run_data_window", table_name="model_run")
    op.drop_index("ix_model_run_store_product", table_name="model_run")
    op.drop_index(op.f("ix_model_run_product_id"), table_name="model_run")
    op.drop_index(op.f("ix_model_run_store_id"), table_name="model_run")
    op.drop_index(op.f("ix_model_run_config_hash"), table_name="model_run")
    op.drop_index(op.f("ix_model_run_model_type"), table_name="model_run")
    op.drop_index(op.f("ix_model_run_status"), table_name="model_run")
    op.drop_index(op.f("ix_model_run_run_id"), table_name="model_run")

    # Drop model_run table
    op.drop_table("model_run")
