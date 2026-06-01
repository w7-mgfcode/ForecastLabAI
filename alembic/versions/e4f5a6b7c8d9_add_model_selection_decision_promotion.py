"""add model_selection decision + promotion columns

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-01 11:00:00.000000

Slice C of the Forecast Champion Selector (issue #362). Adds the decision +
operationalization columns to ``model_selection_run`` — all ADDITIVE:

- ``trained_model_type`` / ``is_override`` / ``override_reason`` — which model
  the final bundle holds and whether it was a non-recommended override;
- ``champion_run_id`` / ``promoted_alias`` / ``promotion_decision`` — the
  approval-gated registry handoff (registry ``model_run.run_id``, alias name,
  and the audited decision record);
- ``feature_frame_version`` — M1, the request's V (1 or 2) persisted at
  run-creation so train/promote carry the REAL version end-to-end. The
  server_default ``'1'`` backfills legacy rows ONLY (not a code hardcode).

No CheckConstraint change. ``downgrade`` drops all seven columns.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply migration — seven additive columns on model_selection_run."""
    op.add_column(
        "model_selection_run",
        sa.Column("trained_model_type", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "model_selection_run",
        sa.Column(
            "is_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "model_selection_run",
        sa.Column("override_reason", sa.String(length=2000), nullable=True),
    )
    op.add_column(
        "model_selection_run",
        sa.Column("champion_run_id", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "model_selection_run",
        sa.Column("promoted_alias", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "model_selection_run",
        sa.Column(
            "promotion_decision",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "model_selection_run",
        sa.Column(
            "feature_frame_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    """Revert migration — drop the seven Slice C columns."""
    op.drop_column("model_selection_run", "feature_frame_version")
    op.drop_column("model_selection_run", "promotion_decision")
    op.drop_column("model_selection_run", "promoted_alias")
    op.drop_column("model_selection_run", "champion_run_id")
    op.drop_column("model_selection_run", "override_reason")
    op.drop_column("model_selection_run", "is_override")
    op.drop_column("model_selection_run", "trained_model_type")
