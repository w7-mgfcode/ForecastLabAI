"""Data platform ORM models for retail forecasting mini-warehouse.

This module defines dimension and fact tables following star schema patterns:
- Dimensions: Store, Product, Calendar
- Facts: SalesDaily, PriceHistory, Promotion, InventorySnapshotDaily

Grain: SalesDaily uniquely keyed by (date, store_id, product_id).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.models import TimestampMixin

# ============================================================================
# DIMENSION TABLES
# ============================================================================


class Store(TimestampMixin, Base):
    """Store dimension table.

    Attributes:
        id: Primary key.
        code: Unique store code (e.g., "S001").
        name: Store display name.
        region: Geographic region.
        city: City location.
        store_type: Store format (e.g., "supermarket", "express", "warehouse").
    """

    __tablename__ = "store"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    city: Mapped[str | None] = mapped_column(String(50), nullable=True)
    store_type: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Relationships (one-to-many)
    sales: Mapped[list[SalesDaily]] = relationship(back_populates="store")
    price_history: Mapped[list[PriceHistory]] = relationship(back_populates="store")
    promotions: Mapped[list[Promotion]] = relationship(back_populates="store")
    inventory_snapshots: Mapped[list[InventorySnapshotDaily]] = relationship(back_populates="store")


class Product(TimestampMixin, Base):
    """Product dimension table.

    Attributes:
        id: Primary key.
        sku: Stock keeping unit (unique product identifier).
        name: Product display name.
        category: Product category.
        subcategory: Optional finer-grain category (Phase 2 retail-depth).
        brand: Product brand.
        base_price: Standard retail price.
        base_cost: Standard cost/COGS.
        pack_size: Optional units-per-pack (Phase 2). NULL means single-unit.
        lifecycle_stage: One of ``intro|growth|maturity|decline|discontinued``
            (Phase 2). NULL when the lifecycle generator is disabled.
        launch_date: Date the product became sellable (Phase 2). NULL when
            lifecycle is disabled.
        discontinue_date: Date the product was retired (Phase 2). NULL when
            still active or lifecycle is disabled.
    """

    __tablename__ = "product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    base_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    base_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    pack_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lifecycle_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    launch_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    discontinue_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    # Relationships (one-to-many)
    sales: Mapped[list[SalesDaily]] = relationship(back_populates="product")
    price_history: Mapped[list[PriceHistory]] = relationship(back_populates="product")
    promotions: Mapped[list[Promotion]] = relationship(back_populates="product")
    inventory_snapshots: Mapped[list[InventorySnapshotDaily]] = relationship(
        back_populates="product"
    )

    __table_args__ = (
        CheckConstraint(
            "lifecycle_stage IS NULL OR lifecycle_stage IN "
            "('intro', 'growth', 'maturity', 'decline', 'discontinued')",
            name="ck_product_lifecycle_stage_allowlist",
        ),
        CheckConstraint(
            "pack_size IS NULL OR pack_size > 0",
            name="ck_product_pack_size_positive",
        ),
        CheckConstraint(
            "discontinue_date IS NULL OR launch_date IS NULL OR discontinue_date >= launch_date",
            name="ck_product_lifecycle_dates_order",
        ),
    )


class Calendar(TimestampMixin, Base):
    """Calendar dimension table for time-based analysis.

    Uses date as primary key (no surrogate key needed).

    Attributes:
        date: Calendar date (primary key).
        day_of_week: 0=Monday, 6=Sunday.
        month: Month number (1-12).
        quarter: Quarter number (1-4).
        year: Year (e.g., 2024).
        is_holiday: Whether this date is a holiday.
        holiday_name: Name of the holiday (if applicable).
    """

    __tablename__ = "calendar"

    date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0=Monday, 6=Sunday
    month: Mapped[int] = mapped_column(Integer)
    quarter: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer, index=True)
    is_holiday: Mapped[bool] = mapped_column(Boolean, default=False)
    holiday_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    sales: Mapped[list[SalesDaily]] = relationship(back_populates="calendar")
    inventory_snapshots: Mapped[list[InventorySnapshotDaily]] = relationship(
        back_populates="calendar"
    )

    __table_args__ = (
        CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name="ck_calendar_day_of_week"),
        CheckConstraint("month >= 1 AND month <= 12", name="ck_calendar_month"),
        CheckConstraint("quarter >= 1 AND quarter <= 4", name="ck_calendar_quarter"),
    )


# ============================================================================
# FACT TABLES
# ============================================================================


class SalesDaily(TimestampMixin, Base):
    """Daily sales fact table.

    CRITICAL: Grain is (date, store_id, product_id) - one row per store/product/day.
    Enforced by unique constraint for idempotent upserts. The Phase 2
    ``channel`` column is intentionally **outside** the grain — pre-Phase-2
    rows default to ``in_store``; multi-channel scenarios are emitted as a
    single row per (date, store, product) with a channel mix encoded in
    downstream aggregates rather than splitting the grain.

    Attributes:
        id: Surrogate primary key.
        date: Sales date (FK to calendar).
        store_id: Store (FK to store).
        product_id: Product (FK to product).
        quantity: Units sold.
        unit_price: Price per unit at time of sale.
        total_amount: Total sales amount (quantity * unit_price).
        channel: Sales channel — one of ``in_store|online|click_collect|wholesale``.
            Defaults to ``in_store`` server-side so existing scenarios stay
            byte-identical.
    """

    __tablename__ = "sales_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Note: date column is covered by composite indexes (ix_sales_daily_date_store, ix_sales_daily_date_product)
    date: Mapped[datetime.date] = mapped_column(Date, ForeignKey("calendar.date"))
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("store.id"), index=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("product.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    channel: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'in_store'")
    )

    # Relationships
    store: Mapped[Store] = relationship(back_populates="sales")
    product: Mapped[Product] = relationship(back_populates="sales")
    calendar: Mapped[Calendar] = relationship(back_populates="sales")

    __table_args__ = (
        # GRAIN PROTECTION: Unique constraint prevents duplicate rows
        UniqueConstraint("date", "store_id", "product_id", name="uq_sales_daily_grain"),
        # Composite index for common query pattern: date range + store
        Index("ix_sales_daily_date_store", "date", "store_id"),
        # Composite index for date range + product
        Index("ix_sales_daily_date_product", "date", "product_id"),
        # Composite index for date range + channel (Phase 2)
        Index("ix_sales_daily_date_channel", "date", "channel"),
        # Check constraint for data quality
        CheckConstraint("quantity >= 0", name="ck_sales_daily_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_sales_daily_price_positive"),
        CheckConstraint("total_amount >= 0", name="ck_sales_daily_amount_positive"),
        CheckConstraint(
            "channel IN ('in_store', 'online', 'click_collect', 'wholesale')",
            name="ck_sales_daily_channel_allowlist",
        ),
    )


class PriceHistory(TimestampMixin, Base):
    """Price history fact table with validity windows.

    Tracks price changes over time with valid_from/valid_to windows.
    valid_to = NULL means currently active price.

    Attributes:
        id: Primary key.
        product_id: Product (FK).
        store_id: Store (FK) - NULL for chain-wide prices.
        price: Price during validity window.
        valid_from: Start of validity period.
        valid_to: End of validity period (NULL = current).
    """

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("product.id"), index=True)
    store_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("store.id"), index=True, nullable=True
    )
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    valid_from: Mapped[datetime.date] = mapped_column(Date, index=True)
    valid_to: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    # Relationships
    product: Mapped[Product] = relationship(back_populates="price_history")
    store: Mapped[Store | None] = relationship(back_populates="price_history")

    __table_args__ = (
        Index("ix_price_history_product_validity", "product_id", "valid_from", "valid_to"),
        CheckConstraint("price >= 0", name="ck_price_history_price_positive"),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_price_history_valid_dates",
        ),
    )


class Promotion(TimestampMixin, Base):
    """Promotion fact table.

    Tracks promotional campaigns with discount mechanics. Phase 2 adds the
    ``kind`` discriminator (with server default ``pct_off`` preserving the
    pre-Phase-2 behaviour) and a JSONB ``bundle_member_product_ids`` for
    BOGO/bundle mechanics.

    Attributes:
        id: Primary key.
        product_id: Product (FK).
        store_id: Store (FK) - NULL for chain-wide promos.
        name: Promotion name/description.
        kind: ``pct_off | bogo | bundle | markdown`` (Phase 2). Server-default
            ``pct_off``.
        discount_pct: Discount percentage (e.g., 0.15 for 15% off).
        discount_amount: Fixed discount amount (alternative to %).
        bundle_member_product_ids: JSONB list of related product IDs when
            ``kind in (bundle, bogo)``; NULL otherwise.
        start_date: Promotion start date.
        end_date: Promotion end date.
    """

    __tablename__ = "promotion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("product.id"), index=True)
    store_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("store.id"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pct_off'"))
    discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    # ``none_as_null=True`` is load-bearing: Python ``None`` must serialize
    # to SQL ``NULL`` (not JSON ``null``) so the
    # ``ck_promotion_bundle_members_consistency`` CHECK constraint correctly
    # rejects bundle/BOGO rows that omit member IDs.
    bundle_member_product_ids: Mapped[list[int] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    start_date: Mapped[datetime.date] = mapped_column(Date, index=True)
    end_date: Mapped[datetime.date] = mapped_column(Date)

    # Relationships
    product: Mapped[Product] = relationship(back_populates="promotions")
    store: Mapped[Store | None] = relationship(back_populates="promotions")

    __table_args__ = (
        Index("ix_promotion_product_dates", "product_id", "start_date", "end_date"),
        CheckConstraint("end_date >= start_date", name="ck_promotion_valid_dates"),
        CheckConstraint(
            "discount_pct IS NULL OR (discount_pct >= 0 AND discount_pct <= 1)",
            name="ck_promotion_discount_pct_range",
        ),
        CheckConstraint(
            "discount_amount IS NULL OR discount_amount >= 0",
            name="ck_promotion_discount_amount_positive",
        ),
        CheckConstraint(
            "kind IN ('pct_off', 'bogo', 'bundle', 'markdown')",
            name="ck_promotion_kind_allowlist",
        ),
        CheckConstraint(
            "(kind IN ('bundle', 'bogo') AND bundle_member_product_ids IS NOT NULL)"
            " OR (kind NOT IN ('bundle', 'bogo') AND bundle_member_product_ids IS NULL)",
            name="ck_promotion_bundle_members_consistency",
        ),
    )


class InventorySnapshotDaily(TimestampMixin, Base):
    """Daily inventory snapshot fact table.

    Daily end-of-day inventory levels for stockout detection.

    Attributes:
        id: Primary key.
        date: Snapshot date (FK to calendar).
        store_id: Store (FK).
        product_id: Product (FK).
        on_hand_qty: Units on hand at end of day.
        on_order_qty: Units on order (incoming).
        is_stockout: True if on_hand_qty = 0.
    """

    __tablename__ = "inventory_snapshot_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Note: date column is covered by composite index (ix_inventory_snapshot_date_store)
    date: Mapped[datetime.date] = mapped_column(Date, ForeignKey("calendar.date"))
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("store.id"), index=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("product.id"), index=True)
    on_hand_qty: Mapped[int] = mapped_column(Integer)
    on_order_qty: Mapped[int] = mapped_column(Integer, default=0)
    is_stockout: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    calendar: Mapped[Calendar] = relationship(back_populates="inventory_snapshots")
    store: Mapped[Store] = relationship(back_populates="inventory_snapshots")
    product: Mapped[Product] = relationship(back_populates="inventory_snapshots")

    __table_args__ = (
        UniqueConstraint(
            "date", "store_id", "product_id", name="uq_inventory_snapshot_daily_grain"
        ),
        Index("ix_inventory_snapshot_date_store", "date", "store_id"),
        CheckConstraint("on_hand_qty >= 0", name="ck_inventory_on_hand_positive"),
        CheckConstraint("on_order_qty >= 0", name="ck_inventory_on_order_positive"),
    )


class ExogenousSignal(TimestampMixin, Base):
    """Exogenous demand-relevant signals (weather, macro index, events).

    A signal is either chain-wide (``is_global=True``, ``store_id IS NULL``)
    or per-store (``is_global=False``, ``store_id IS NOT NULL``). The two
    cases are enforced by ``ck_exogenous_signal_global_consistency`` and made
    unique by two partial indexes so re-runs of the seeder are idempotent.

    Attributes:
        id: Surrogate primary key.
        date: Signal date (FK to calendar).
        signal_name: Short identifier (e.g. ``"weather_temp_c"``, ``"macro_index"``).
        store_id: Store (FK) — NULL when ``is_global=True``.
        is_global: True for chain-wide signals; mirrors ``store_id IS NULL``.
        value: Numeric value of the signal on the given date.
    """

    __tablename__ = "exogenous_signal"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, ForeignKey("calendar.date"), index=True)
    signal_name: Mapped[str] = mapped_column(String(50), index=True)
    store_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("store.id"), nullable=True, index=True
    )
    is_global: Mapped[bool] = mapped_column(Boolean, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        Index("ix_exogenous_signal_name_date", "signal_name", "date"),
        Index(
            "uq_exogenous_signal_global",
            "date",
            "signal_name",
            unique=True,
            postgresql_where=("is_global = true"),
        ),
        Index(
            "uq_exogenous_signal_per_store",
            "date",
            "signal_name",
            "store_id",
            unique=True,
            postgresql_where=("is_global = false"),
        ),
        CheckConstraint(
            "(is_global = true AND store_id IS NULL) OR "
            "(is_global = false AND store_id IS NOT NULL)",
            name="ck_exogenous_signal_global_consistency",
        ),
    )


class SalesReturn(TimestampMixin, Base):
    """Synthetic sales return event.

    Returns are not subtracted from ``sales_daily.quantity``; they live in a
    separate table so featuresets/forecasting can opt into them as a signal.

    Attributes:
        id: Surrogate primary key.
        date: Return date (FK to calendar).
        store_id: Store (FK).
        product_id: Product (FK).
        return_quantity: Units returned (>= 1).
        return_reason: Free-form short reason (e.g. ``"defective"``,
            ``"changed_mind"``).
    """

    __tablename__ = "sales_returns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, ForeignKey("calendar.date"))
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("store.id"), index=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("product.id"), index=True)
    return_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    return_reason: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        Index("ix_sales_returns_store_product_date", "store_id", "product_id", "date"),
        Index("ix_sales_returns_date", "date"),
        CheckConstraint("return_quantity >= 1", name="ck_sales_returns_quantity_positive"),
    )


class ReplenishmentEvent(TimestampMixin, Base):
    """Synthetic replenishment / inbound stock event (Phase 2).

    Drives lead-time-aware stockout clustering. A row marks the date a
    purchase order was *received* at a store for a given product, along
    with how many days the order was in transit and the ordered vs.
    received quantities. The inventory generator consumes these to
    schedule realistic stockout windows.

    Attributes:
        id: Surrogate primary key.
        date: Date of receipt at the store (FK to calendar).
        store_id: Store (FK).
        product_id: Product (FK).
        lead_time_days: Days between order placement and receipt.
        ordered_qty: Units ordered.
        received_qty: Units actually received (``<= ordered_qty``).
    """

    __tablename__ = "replenishment_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, ForeignKey("calendar.date"), index=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("store.id"), index=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("product.id"), index=True)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    ordered_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    received_qty: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index(
            "ix_replenishment_event_store_product_date",
            "store_id",
            "product_id",
            "date",
        ),
        CheckConstraint("lead_time_days >= 0", name="ck_replenishment_event_lead_time_positive"),
        CheckConstraint("ordered_qty >= 0", name="ck_replenishment_event_ordered_qty_positive"),
        CheckConstraint("received_qty >= 0", name="ck_replenishment_event_received_qty_positive"),
        CheckConstraint(
            "received_qty <= ordered_qty",
            name="ck_replenishment_event_received_le_ordered",
        ),
    )
