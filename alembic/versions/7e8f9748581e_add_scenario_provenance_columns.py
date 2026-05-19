"""add scenario provenance columns

Revision ID: 7e8f9748581e
Revises: bb8c4587ef1d
Create Date: 2026-05-19 10:47:09.829097

PRP-27 Phase D — adds provenance + approval-audit columns to ``scenario_plan``
so an agent-proposed plan records who/what created it and the human approval
decision that released it. ``source`` server-defaults to ``'user'`` so every
pre-existing row stays valid. Forward-only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7e8f9748581e'
down_revision: Union[str, None] = 'bb8c4587ef1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the source + approval-audit columns, their CHECKs and an index."""
    op.add_column(
        'scenario_plan',
        sa.Column(
            'source',
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
    )
    op.add_column(
        'scenario_plan',
        sa.Column('agent_session_id', sa.String(length=32), nullable=True),
    )
    op.add_column(
        'scenario_plan',
        sa.Column('approved_by', sa.String(length=120), nullable=True),
    )
    op.add_column(
        'scenario_plan',
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'scenario_plan',
        sa.Column('approval_decision', sa.String(length=16), nullable=True),
    )
    op.create_check_constraint(
        'ck_scenario_plan_source',
        'scenario_plan',
        "source IN ('user', 'agent')",
    )
    op.create_check_constraint(
        'ck_scenario_plan_approval_decision',
        'scenario_plan',
        "approval_decision IS NULL OR approval_decision IN ('approved', 'rejected')",
    )
    op.create_index('ix_scenario_plan_source', 'scenario_plan', ['source'], unique=False)


def downgrade() -> None:
    """Drop the index, the two CHECKs and the provenance columns."""
    op.drop_index('ix_scenario_plan_source', table_name='scenario_plan')
    op.drop_constraint('ck_scenario_plan_approval_decision', 'scenario_plan', type_='check')
    op.drop_constraint('ck_scenario_plan_source', 'scenario_plan', type_='check')
    op.drop_column('scenario_plan', 'approval_decision')
    op.drop_column('scenario_plan', 'approved_at')
    op.drop_column('scenario_plan', 'approved_by')
    op.drop_column('scenario_plan', 'agent_session_id')
    op.drop_column('scenario_plan', 'source')
