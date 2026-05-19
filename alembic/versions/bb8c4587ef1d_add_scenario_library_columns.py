"""add scenario library columns

Revision ID: bb8c4587ef1d
Revises: e47f5739d7d0
Create Date: 2026-05-19 10:26:58.473203

PRP-27 Phase C — adds the scenario-library columns to ``scenario_plan``:
``tags`` (a JSONB string array, queryable via a GIN index) and ``cloned_from``
(the ``scenario_id`` a plan was cloned from, nullable). Forward-only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'bb8c4587ef1d'
down_revision: Union[str, None] = 'e47f5739d7d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the tags and cloned_from columns plus a GIN index on tags."""
    op.add_column(
        'scenario_plan',
        sa.Column(
            'tags',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        'scenario_plan',
        sa.Column('cloned_from', sa.String(length=32), nullable=True),
    )
    op.create_index(
        'ix_scenario_plan_tags_gin',
        'scenario_plan',
        ['tags'],
        unique=False,
        postgresql_using='gin',
    )


def downgrade() -> None:
    """Drop the GIN index and the scenario-library columns."""
    op.drop_index('ix_scenario_plan_tags_gin', table_name='scenario_plan', postgresql_using='gin')
    op.drop_column('scenario_plan', 'cloned_from')
    op.drop_column('scenario_plan', 'tags')
