"""add showcase_workspace run_config column

Revision ID: b7c1d9e3f204
Revises: d45cf40dfe47
Create Date: 2026-06-13 12:00:00.000000

E4 of the showcase-completion initiative (umbrella #406, epic #410). Adds a
single nullable JSONB ``run_config`` column to ``showcase_workspace`` -- a
REPLAY-INPUT column in the same class as ``seed`` / ``scenario`` / ``reset`` /
``skip_seed`` (NOT an E1 story slot; see docs/_base/DOMAIN_MODEL.md D1). It
records the start-frame model set + backtest config a ``preservation="keep"``
run was launched with, so Load/Replay can reproduce it verbatim. NULL when the
run used default config. No index (the read path is by ``workspace_id``; the
column is a display/replay payload). Forward-only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c1d9e3f204"
down_revision: str | None = "d45cf40dfe47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``run_config`` JSONB column."""
    op.add_column(
        "showcase_workspace",
        sa.Column("run_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Drop the ``run_config`` column."""
    op.drop_column("showcase_workspace", "run_config")
