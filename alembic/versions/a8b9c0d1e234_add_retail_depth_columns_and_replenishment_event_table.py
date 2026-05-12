"""add retail-depth columns and replenishment_event table

Revision ID: a8b9c0d1e234
Revises: f7a8b9c0d123
Create Date: 2026-05-11 13:00:00.000000

Phase 2 of the seeder realism extension. Additive only:

- ``sales_daily.channel`` (VARCHAR(20), NOT NULL, server default ``"in_store"``)
  with a CHECK constraint pinning the allow-list and a composite
  ``(date, channel)`` index for downstream analytics.
- ``product`` gains lifecycle fields (``lifecycle_stage``, ``launch_date``,
  ``discontinue_date``) plus ``pack_size`` and ``subcategory``. All NULL by
  default so existing rows keep working.
- ``promotion.kind`` (VARCHAR(20), NOT NULL, server default ``"pct_off"``)
  and ``promotion.bundle_member_product_ids`` (JSONB, NULL) — bundle/BOGO
  mechanics.
- New table ``replenishment_event`` drives lead-time-aware stockout
  clustering. Columns: ``date``, ``store_id``, ``product_id``,
  ``lead_time_days``, ``ordered_qty``, ``received_qty``.

The server defaults on ``sales_daily.channel`` and ``promotion.kind`` are
intentional: scenarios that do not enable Phase 2 multichannel/bundle
toggles will populate rows without those columns, and the database picks
the historical default automatically. This keeps the regression invariant
(``retail_standard`` produces byte-identical row counts).

Downgrade drops all of the above. Any seeded Phase 2 rows are lost;
acceptable for synthetic data only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8b9c0d1e234"
down_revision: str | None = "f7a8b9c0d123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHANNEL_ALLOWLIST = "('in_store', 'online', 'click_collect', 'wholesale')"
_PROMOTION_KIND_ALLOWLIST = "('pct_off', 'bogo', 'bundle', 'markdown')"
_LIFECYCLE_STAGE_ALLOWLIST = "('intro', 'growth', 'maturity', 'decline', 'discontinued')"


def upgrade() -> None:
    """Apply migration: add retail-depth columns and replenishment_event."""
    # ------------------------------------------------------------------ #
    # 1. sales_daily.channel (NOT NULL with server default 'in_store')
    # ------------------------------------------------------------------ #
    op.add_column(
        "sales_daily",
        sa.Column(
            "channel",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'in_store'"),
        ),
    )
    op.create_index(
        "ix_sales_daily_date_channel",
        "sales_daily",
        ["date", "channel"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_sales_daily_channel_allowlist",
        "sales_daily",
        f"channel IN {_CHANNEL_ALLOWLIST}",
    )

    # ------------------------------------------------------------------ #
    # 2. product lifecycle / pack_size / subcategory (all NULL by default)
    # ------------------------------------------------------------------ #
    op.add_column(
        "product",
        sa.Column("lifecycle_stage", sa.String(length=20), nullable=True),
    )
    op.add_column("product", sa.Column("launch_date", sa.Date(), nullable=True))
    op.add_column("product", sa.Column("discontinue_date", sa.Date(), nullable=True))
    op.add_column("product", sa.Column("pack_size", sa.Integer(), nullable=True))
    op.add_column(
        "product",
        sa.Column("subcategory", sa.String(length=100), nullable=True),
    )
    op.create_index(
        op.f("ix_product_subcategory"),
        "product",
        ["subcategory"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_product_lifecycle_stage_allowlist",
        "product",
        f"lifecycle_stage IS NULL OR lifecycle_stage IN {_LIFECYCLE_STAGE_ALLOWLIST}",
    )
    op.create_check_constraint(
        "ck_product_pack_size_positive",
        "product",
        "pack_size IS NULL OR pack_size > 0",
    )
    op.create_check_constraint(
        "ck_product_lifecycle_dates_order",
        "product",
        "discontinue_date IS NULL "
        "OR launch_date IS NULL "
        "OR discontinue_date >= launch_date",
    )

    # ------------------------------------------------------------------ #
    # 3. promotion.kind + promotion.bundle_member_product_ids
    # ------------------------------------------------------------------ #
    op.add_column(
        "promotion",
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'pct_off'"),
        ),
    )
    op.add_column(
        "promotion",
        sa.Column(
            "bundle_member_product_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_promotion_kind_allowlist",
        "promotion",
        f"kind IN {_PROMOTION_KIND_ALLOWLIST}",
    )
    # A bundle/BOGO promotion MUST carry at least one member; non-bundle
    # promotions MUST NOT. Enforced at the SQL layer so Pydantic & ORM stay
    # additive.
    op.create_check_constraint(
        "ck_promotion_bundle_members_consistency",
        "promotion",
        "(kind IN ('bundle', 'bogo') AND bundle_member_product_ids IS NOT NULL)"
        " OR (kind NOT IN ('bundle', 'bogo') AND bundle_member_product_ids IS NULL)",
    )

    # ------------------------------------------------------------------ #
    # 4. replenishment_event table
    # ------------------------------------------------------------------ #
    op.create_table(
        "replenishment_event",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("lead_time_days", sa.Integer(), nullable=False),
        sa.Column("ordered_qty", sa.Integer(), nullable=False),
        sa.Column("received_qty", sa.Integer(), nullable=False),
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
            "lead_time_days >= 0", name="ck_replenishment_event_lead_time_positive"
        ),
        sa.CheckConstraint(
            "ordered_qty >= 0", name="ck_replenishment_event_ordered_qty_positive"
        ),
        sa.CheckConstraint(
            "received_qty >= 0", name="ck_replenishment_event_received_qty_positive"
        ),
        sa.CheckConstraint(
            "received_qty <= ordered_qty",
            name="ck_replenishment_event_received_le_ordered",
        ),
        sa.ForeignKeyConstraint(["date"], ["calendar.date"]),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_replenishment_event_date"),
        "replenishment_event",
        ["date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_replenishment_event_product_id"),
        "replenishment_event",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_replenishment_event_store_id"),
        "replenishment_event",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        "ix_replenishment_event_store_product_date",
        "replenishment_event",
        ["store_id", "product_id", "date"],
        unique=False,
    )


def downgrade() -> None:
    """Revert migration: drop everything Phase 2 added.

    WARNING: Any seeded Phase 2 rows are lost. Acceptable for synthetic data
    only — do not run against an environment with user-loaded retail data.
    """
    # 4. replenishment_event
    op.drop_index(
        "ix_replenishment_event_store_product_date",
        table_name="replenishment_event",
    )
    op.drop_index(
        op.f("ix_replenishment_event_store_id"), table_name="replenishment_event"
    )
    op.drop_index(
        op.f("ix_replenishment_event_product_id"), table_name="replenishment_event"
    )
    op.drop_index(
        op.f("ix_replenishment_event_date"), table_name="replenishment_event"
    )
    op.drop_table("replenishment_event")

    # 3. promotion.kind + bundle_member_product_ids
    op.drop_constraint(
        "ck_promotion_bundle_members_consistency", "promotion", type_="check"
    )
    op.drop_constraint("ck_promotion_kind_allowlist", "promotion", type_="check")
    op.drop_column("promotion", "bundle_member_product_ids")
    op.drop_column("promotion", "kind")

    # 2. product lifecycle fields
    op.drop_constraint(
        "ck_product_lifecycle_dates_order", "product", type_="check"
    )
    op.drop_constraint("ck_product_pack_size_positive", "product", type_="check")
    op.drop_constraint(
        "ck_product_lifecycle_stage_allowlist", "product", type_="check"
    )
    op.drop_index(op.f("ix_product_subcategory"), table_name="product")
    op.drop_column("product", "subcategory")
    op.drop_column("product", "pack_size")
    op.drop_column("product", "discontinue_date")
    op.drop_column("product", "launch_date")
    op.drop_column("product", "lifecycle_stage")

    # 1. sales_daily.channel
    op.drop_constraint(
        "ck_sales_daily_channel_allowlist", "sales_daily", type_="check"
    )
    op.drop_index("ix_sales_daily_date_channel", table_name="sales_daily")
    op.drop_column("sales_daily", "channel")
