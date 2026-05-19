"""create scenario plan table

Revision ID: 43e35957a248
Revises: 378c112e4b32
Create Date: 2026-05-19 07:34:30.545495

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '43e35957a248'
down_revision: Union[str, None] = '378c112e4b32'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration — create the scenario_plan table."""
    op.create_table(
        'scenario_plan',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scenario_id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(length=32), nullable=False),
        sa.Column('horizon', sa.Integer(), nullable=False),
        sa.Column('assumptions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('comparison', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('method', sa.String(length=20), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint("method IN ('heuristic')", name='ck_scenario_plan_method'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_scenario_plan_scenario_id'), 'scenario_plan', ['scenario_id'], unique=True
    )
    op.create_index(
        op.f('ix_scenario_plan_store_id'), 'scenario_plan', ['store_id'], unique=False
    )
    op.create_index(
        op.f('ix_scenario_plan_product_id'), 'scenario_plan', ['product_id'], unique=False
    )
    op.create_index(
        op.f('ix_scenario_plan_run_id'), 'scenario_plan', ['run_id'], unique=False
    )
    op.create_index(
        'ix_scenario_plan_assumptions_gin',
        'scenario_plan',
        ['assumptions'],
        unique=False,
        postgresql_using='gin',
    )
    op.create_index(
        'ix_scenario_plan_comparison_gin',
        'scenario_plan',
        ['comparison'],
        unique=False,
        postgresql_using='gin',
    )
    op.create_index(
        'ix_scenario_plan_store_product',
        'scenario_plan',
        ['store_id', 'product_id'],
        unique=False,
    )


def downgrade() -> None:
    """Revert migration — drop the scenario_plan table."""
    op.drop_index('ix_scenario_plan_store_product', table_name='scenario_plan')
    op.drop_index(
        'ix_scenario_plan_comparison_gin', table_name='scenario_plan', postgresql_using='gin'
    )
    op.drop_index(
        'ix_scenario_plan_assumptions_gin', table_name='scenario_plan', postgresql_using='gin'
    )
    op.drop_index(op.f('ix_scenario_plan_run_id'), table_name='scenario_plan')
    op.drop_index(op.f('ix_scenario_plan_product_id'), table_name='scenario_plan')
    op.drop_index(op.f('ix_scenario_plan_store_id'), table_name='scenario_plan')
    op.drop_index(op.f('ix_scenario_plan_scenario_id'), table_name='scenario_plan')
    op.drop_table('scenario_plan')
