"""add showcase_workspace metadata and provenance columns

Revision ID: d45cf40dfe47
Revises: 324a2fa37fcc
Create Date: 2026-06-12 12:00:00.000000

E1 of the showcase-completion initiative (umbrella #406, epic #407). Extends
``showcase_workspace`` with the metadata + provenance backbone every parallel
epic consumes: lifecycle columns (``archived`` / ``pinned`` / ``notes`` /
``tags`` / ``config_schema_version``), the replay-provenance soft reference
``replayed_from_workspace_id`` (deliberately NO ForeignKey -- not even
self-referential; ancestor rows stay independently deletable), and six
documented JSONB story slots (``seed_overrides`` / ``user_scope`` /
``approval_events`` / ``rag_events`` / ``job_ids`` / ``phase_summaries``)
that stay NULL until their writer epic lands. NOT NULL columns carry server
defaults so the migration applies on tables with existing rows. Forward-only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d45cf40dfe47"
down_revision: str | None = "324a2fa37fcc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the lifecycle, provenance, and story-slot columns plus indexes."""
    op.add_column(
        "showcase_workspace",
        sa.Column(
            "archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "showcase_workspace",
        sa.Column(
            "pinned",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "showcase_workspace",
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "showcase_workspace",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "showcase_workspace",
        sa.Column(
            "config_schema_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "showcase_workspace",
        sa.Column("replayed_from_workspace_id", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "showcase_workspace",
        sa.Column("seed_overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "showcase_workspace",
        sa.Column("user_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "showcase_workspace",
        sa.Column("approval_events", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "showcase_workspace",
        sa.Column("rag_events", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "showcase_workspace",
        sa.Column("job_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "showcase_workspace",
        sa.Column("phase_summaries", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "ix_showcase_workspace_tags_gin",
        "showcase_workspace",
        ["tags"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_showcase_workspace_replayed_from",
        "showcase_workspace",
        ["replayed_from_workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the two indexes, then the twelve columns (reverse order)."""
    op.drop_index("ix_showcase_workspace_replayed_from", table_name="showcase_workspace")
    op.drop_index(
        "ix_showcase_workspace_tags_gin",
        table_name="showcase_workspace",
        postgresql_using="gin",
    )
    op.drop_column("showcase_workspace", "phase_summaries")
    op.drop_column("showcase_workspace", "job_ids")
    op.drop_column("showcase_workspace", "rag_events")
    op.drop_column("showcase_workspace", "approval_events")
    op.drop_column("showcase_workspace", "user_scope")
    op.drop_column("showcase_workspace", "seed_overrides")
    op.drop_column("showcase_workspace", "replayed_from_workspace_id")
    op.drop_column("showcase_workspace", "config_schema_version")
    op.drop_column("showcase_workspace", "tags")
    op.drop_column("showcase_workspace", "notes")
    op.drop_column("showcase_workspace", "pinned")
    op.drop_column("showcase_workspace", "archived")
