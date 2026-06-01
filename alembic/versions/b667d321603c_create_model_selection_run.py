"""create_model_selection_run

Revision ID: b667d321603c
Revises: c1d2e3f40512
Create Date: 2026-06-01 05:58:51.986105

Creates the ``model_selection_run`` table for the Forecast Champion Selector
backend (issue #353). One row per ``POST /model-selection/run`` — an auditable
record of which candidate models competed for a (store, product) pair, over
which window/policy, and which model won.

JSONB snapshot columns mirror the ``batch_job`` precedent
(``c1d2e3f40512_create_batch_tables``): every flexible payload (candidate
configs, policy, availability, ranking, per-candidate results incl. fold chart
data, winner metrics, forecast summary, business summary) is JSONB so the
eventual UI PRP can add keys without a schema migration. ``candidate_results``
holds the full per-candidate detail (incl. fold actuals/predictions) so a
``GET`` rebuilds the same ``chart_data`` payload the originating ``/run``
returned — without it the chart's fold-stability and actual-vs-predicted
overlays could not be reconstructed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b667d321603c"
down_revision: str | None = "c1d2e3f40512"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply migration."""
    op.create_table(
        "model_selection_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("selection_id", sa.String(length=32), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("forecast_horizon", sa.Integer(), nullable=False),
        sa.Column("ranking_metric", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("candidate_models", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("policy_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("availability_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ranking_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("candidate_results", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("chart_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("winner_model_type", sa.String(length=40), nullable=True),
        sa.Column("winner_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("final_model_path", sa.String(length=512), nullable=True),
        sa.Column("forecast_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("business_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
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
            "status IN ('pending', 'running', 'completed', 'partial', 'failed')",
            name="ck_model_selection_run_valid_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_model_selection_run_selection_id"),
        "model_selection_run",
        ["selection_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_model_selection_run_store_id"),
        "model_selection_run",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_selection_run_product_id"),
        "model_selection_run",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_selection_run_status"),
        "model_selection_run",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_model_selection_run_store_product_created",
        "model_selection_run",
        ["store_id", "product_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_model_selection_run_status_created",
        "model_selection_run",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Revert migration."""
    op.drop_index("ix_model_selection_run_status_created", table_name="model_selection_run")
    op.drop_index(
        "ix_model_selection_run_store_product_created", table_name="model_selection_run"
    )
    op.drop_index(op.f("ix_model_selection_run_status"), table_name="model_selection_run")
    op.drop_index(op.f("ix_model_selection_run_product_id"), table_name="model_selection_run")
    op.drop_index(op.f("ix_model_selection_run_store_id"), table_name="model_selection_run")
    op.drop_index(op.f("ix_model_selection_run_selection_id"), table_name="model_selection_run")
    op.drop_table("model_selection_run")
