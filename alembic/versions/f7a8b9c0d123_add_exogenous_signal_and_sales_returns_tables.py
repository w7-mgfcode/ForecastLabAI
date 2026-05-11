"""add exogenous_signal and sales_returns tables

Revision ID: f7a8b9c0d123
Revises: d6e0f2g3h456
Create Date: 2026-05-11 12:00:00.000000

Phase 1 of the seeder realism extension. Additive only — creates two new
fact tables to support exogenous demand signals (weather / macro / events)
and synthetic returns volume. No existing rows are touched.

Downgrade drops both tables; any seeded rows are lost. This is acceptable
because the data is synthetic; do not run downgrade against an environment
that holds user-loaded data.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d123"
down_revision: str | None = "d6e0f2g3h456"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply migration: create exogenous_signal and sales_returns."""
    op.create_table(
        "exogenous_signal",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("signal_name", sa.String(length=50), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=True),
        sa.Column("is_global", sa.Boolean(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
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
            "(is_global = true AND store_id IS NULL) OR "
            "(is_global = false AND store_id IS NOT NULL)",
            name="ck_exogenous_signal_global_consistency",
        ),
        sa.ForeignKeyConstraint(["date"], ["calendar.date"]),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_exogenous_signal_date"), "exogenous_signal", ["date"], unique=False
    )
    op.create_index(
        op.f("ix_exogenous_signal_signal_name"),
        "exogenous_signal",
        ["signal_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_exogenous_signal_store_id"),
        "exogenous_signal",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        "ix_exogenous_signal_name_date",
        "exogenous_signal",
        ["signal_name", "date"],
        unique=False,
    )
    op.create_index(
        "uq_exogenous_signal_global",
        "exogenous_signal",
        ["date", "signal_name"],
        unique=True,
        postgresql_where=sa.text("is_global = true"),
    )
    op.create_index(
        "uq_exogenous_signal_per_store",
        "exogenous_signal",
        ["date", "signal_name", "store_id"],
        unique=True,
        postgresql_where=sa.text("is_global = false"),
    )

    op.create_table(
        "sales_returns",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("return_quantity", sa.Integer(), nullable=False),
        sa.Column("return_reason", sa.String(length=50), nullable=False),
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
        sa.CheckConstraint("return_quantity >= 1", name="ck_sales_returns_quantity_positive"),
        sa.ForeignKeyConstraint(["date"], ["calendar.date"]),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sales_returns_product_id"), "sales_returns", ["product_id"], unique=False
    )
    op.create_index(
        op.f("ix_sales_returns_store_id"), "sales_returns", ["store_id"], unique=False
    )
    op.create_index(
        "ix_sales_returns_store_product_date",
        "sales_returns",
        ["store_id", "product_id", "date"],
        unique=False,
    )
    op.create_index("ix_sales_returns_date", "sales_returns", ["date"], unique=False)


def downgrade() -> None:
    """Revert migration: drop sales_returns and exogenous_signal.

    WARNING: Any seeded Phase 1 rows are lost. Acceptable for synthetic data
    only — do not run against an environment with user-loaded signals.
    """
    op.drop_index("ix_sales_returns_date", table_name="sales_returns")
    op.drop_index("ix_sales_returns_store_product_date", table_name="sales_returns")
    op.drop_index(op.f("ix_sales_returns_store_id"), table_name="sales_returns")
    op.drop_index(op.f("ix_sales_returns_product_id"), table_name="sales_returns")
    op.drop_table("sales_returns")

    op.drop_index("uq_exogenous_signal_per_store", table_name="exogenous_signal")
    op.drop_index("uq_exogenous_signal_global", table_name="exogenous_signal")
    op.drop_index("ix_exogenous_signal_name_date", table_name="exogenous_signal")
    op.drop_index(op.f("ix_exogenous_signal_store_id"), table_name="exogenous_signal")
    op.drop_index(op.f("ix_exogenous_signal_signal_name"), table_name="exogenous_signal")
    op.drop_index(op.f("ix_exogenous_signal_date"), table_name="exogenous_signal")
    op.drop_table("exogenous_signal")
