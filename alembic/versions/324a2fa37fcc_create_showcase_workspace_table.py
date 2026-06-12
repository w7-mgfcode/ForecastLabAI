"""create showcase_workspace table

Revision ID: 324a2fa37fcc
Revises: e4f5a6b7c8d9
Create Date: 2026-06-12 10:00:00.000000

E1 of the showcase-workspace initiative (umbrella #389, epic #390). First
table owned by the demo slice: one row per preserved showcase run -- its
configuration (replay inputs) plus the soft-reference ids of every object the
pipeline created. Deliberately NO ForeignKey to ``model_run`` /
``scenario_plan`` / ``batch_job`` / ``agent_session`` -- recorded ids are
opaque soft references so cross-slice schema coupling stays zero and the
referenced rows remain independently deletable.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "324a2fa37fcc"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply migration -- create the showcase_workspace table."""
    op.create_table(
        "showcase_workspace",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("scenario", sa.String(length=40), nullable=False),
        sa.Column("reset", sa.Boolean(), nullable=False),
        sa.Column("skip_seed", sa.Boolean(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("date_start", sa.Date(), nullable=True),
        sa.Column("date_end", sa.Date(), nullable=True),
        sa.Column(
            "created_objects",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("result_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            "status IN ('running', 'completed', 'failed')",
            name="ck_showcase_workspace_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_showcase_workspace_workspace_id"),
        "showcase_workspace",
        ["workspace_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_showcase_workspace_name"),
        "showcase_workspace",
        ["name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_showcase_workspace_status"),
        "showcase_workspace",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_showcase_workspace_status_created",
        "showcase_workspace",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Revert migration -- drop the showcase_workspace table."""
    op.drop_index("ix_showcase_workspace_status_created", table_name="showcase_workspace")
    op.drop_index(op.f("ix_showcase_workspace_status"), table_name="showcase_workspace")
    op.drop_index(op.f("ix_showcase_workspace_name"), table_name="showcase_workspace")
    op.drop_index(op.f("ix_showcase_workspace_workspace_id"), table_name="showcase_workspace")
    op.drop_table("showcase_workspace")
