"""create forecast explanation table

Revision ID: f84258c4cb44
Revises: 7e8f9748581e
Create Date: 2026-05-19 11:46:00.062839

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f84258c4cb44'
down_revision: Union[str, None] = '7e8f9748581e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration — create the forecast_explanation table."""
    op.create_table(
        'forecast_explanation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('explanation_id', sa.String(length=32), nullable=False),
        sa.Column('run_id', sa.String(length=32), nullable=True),
        sa.Column('job_id', sa.String(length=32), nullable=True),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('model_type', sa.String(length=50), nullable=False),
        sa.Column('method', sa.String(length=20), nullable=False),
        sa.Column('as_of_date', sa.Date(), nullable=False),
        sa.Column('forecast_value', sa.Float(), nullable=False),
        sa.Column('confidence', sa.String(length=10), nullable=False),
        sa.Column('drivers', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('reason_codes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('caveats', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('agent_summary', sa.String(length=2000), nullable=False),
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
        sa.CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name='ck_forecast_explanation_confidence',
        ),
        sa.CheckConstraint(
            "method IN ('rule_based', 'shap', 'component')",
            name='ck_forecast_explanation_method',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_forecast_explanation_explanation_id'),
        'forecast_explanation',
        ['explanation_id'],
        unique=True,
    )
    op.create_index(
        op.f('ix_forecast_explanation_run_id'),
        'forecast_explanation',
        ['run_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_forecast_explanation_job_id'),
        'forecast_explanation',
        ['job_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_forecast_explanation_store_id'),
        'forecast_explanation',
        ['store_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_forecast_explanation_product_id'),
        'forecast_explanation',
        ['product_id'],
        unique=False,
    )
    op.create_index(
        'ix_forecast_explanation_drivers_gin',
        'forecast_explanation',
        ['drivers'],
        unique=False,
        postgresql_using='gin',
    )
    op.create_index(
        'ix_forecast_explanation_store_product',
        'forecast_explanation',
        ['store_id', 'product_id'],
        unique=False,
    )


def downgrade() -> None:
    """Revert migration — drop the forecast_explanation table."""
    op.drop_index(
        'ix_forecast_explanation_store_product', table_name='forecast_explanation'
    )
    op.drop_index(
        'ix_forecast_explanation_drivers_gin',
        table_name='forecast_explanation',
        postgresql_using='gin',
    )
    op.drop_index(
        op.f('ix_forecast_explanation_product_id'), table_name='forecast_explanation'
    )
    op.drop_index(
        op.f('ix_forecast_explanation_store_id'), table_name='forecast_explanation'
    )
    op.drop_index(
        op.f('ix_forecast_explanation_job_id'), table_name='forecast_explanation'
    )
    op.drop_index(
        op.f('ix_forecast_explanation_run_id'), table_name='forecast_explanation'
    )
    op.drop_index(
        op.f('ix_forecast_explanation_explanation_id'),
        table_name='forecast_explanation',
    )
    op.drop_table('forecast_explanation')
