"""widen scenario method check

Revision ID: e47f5739d7d0
Revises: 43e35957a248
Create Date: 2026-05-19 10:06:15.179816

PRP-27 Phase B — widens the ``scenario_plan.method`` CHECK constraint so a
model-driven simulation can persist ``method='model_exogenous'`` alongside the
MVP's ``'heuristic'``. Forward-only: never edits the merged migration that
created the table.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e47f5739d7d0'
down_revision: Union[str, None] = '43e35957a248'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT = "ck_scenario_plan_method"
_TABLE = "scenario_plan"


def upgrade() -> None:
    """Allow method IN ('heuristic', 'model_exogenous')."""
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "method IN ('heuristic', 'model_exogenous')",
    )


def downgrade() -> None:
    """Revert to method IN ('heuristic') only."""
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "method IN ('heuristic')",
    )
