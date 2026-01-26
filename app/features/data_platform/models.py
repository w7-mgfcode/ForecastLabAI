"""Data platform ORM models for retail forecasting mini-warehouse.

This module defines dimension and fact tables following star schema patterns:
- Dimensions: Store, Product, Calendar
- Facts: SalesDaily, PriceHistory, Promotion, InventorySnapshotDaily

Grain: SalesDaily uniquely keyed by (date, store_id, product_id).
"""

import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
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
    sales: Mapped[list["SalesDaily"]] = relationship(back_populates="store")
    price_history: Mapped[list["PriceHistory"]] = relationship(back_populates="store")
    promotions: Mapped[list["Promotion"]] = relationship(back_populates="store")
    inventory_snapshots: Mapped[list["InventorySnapshotDaily"]] = relationship(
        back_populates="store"
    )


class Product(TimestampMixin, Base):
    """Product dimension table.

    Attributes:
        id: Primary key.
        sku: Stock keeping unit (unique product identifier).
        name: Product display name.
        category: Product category.
        brand: Product brand.
        base_price: Standard retail price.
        base_cost: Standard cost/COGS.
    """

    __tablename__ = "product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    base_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    base_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Relationships (one-to-many)
    sales: Mapped[list["SalesDaily"]] = relationship(back_populates="product")
    price_history: Mapped[list["PriceHistory"]] = relationship(back_populates="product")
    promotions: Mapped[list["Promotion"]] = relationship(back_populates="product")
    inventory_snapshots: Mapped[list["InventorySnapshotDaily"]] = relationship(
        back_populates="product"
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
    sales: Mapped[list["SalesDaily"]] = relationship(back_populates="calendar")
    inventory_snapshots: Mapped[list["InventorySnapshotDaily"]] = relationship(
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
    Enforced by unique constraint for idempotent upserts.

    Attributes:
        id: Surrogate primary key.
        date: Sales date (FK to calendar).
        store_id: Store (FK to store).
        product_id: Product (FK to product).
        quantity: Units sold.
        unit_price: Price per unit at time of sale.
        total_amount: Total sales amount (quantity * unit_price).
    """

    __tablename__ = "sales_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, ForeignKey("calendar.date"), index=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("store.id"), index=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("product.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    # Relationships
    store: Mapped["Store"] = relationship(back_populates="sales")
    product: Mapped["Product"] = relationship(back_populates="sales")
    calendar: Mapped["Calendar"] = relationship(back_populates="sales")

    __table_args__ = (
        # GRAIN PROTECTION: Unique constraint prevents duplicate rows
        UniqueConstraint("date", "store_id", "product_id", name="uq_sales_daily_grain"),
        # Composite index for common query pattern: date range + store
        Index("ix_sales_daily_date_store", "date", "store_id"),
        # Composite index for date range + product
        Index("ix_sales_daily_date_product", "date", "product_id"),
        # Check constraint for data quality
        CheckConstraint("quantity >= 0", name="ck_sales_daily_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_sales_daily_price_positive"),
        CheckConstraint("total_amount >= 0", name="ck_sales_daily_amount_positive"),
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
    product: Mapped["Product"] = relationship(back_populates="price_history")
    store: Mapped["Store | None"] = relationship(back_populates="price_history")

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

    Tracks promotional campaigns with discount mechanics.

    Attributes:
        id: Primary key.
        product_id: Product (FK).
        store_id: Store (FK) - NULL for chain-wide promos.
        name: Promotion name/description.
        discount_pct: Discount percentage (e.g., 0.15 for 15% off).
        discount_amount: Fixed discount amount (alternative to %).
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
    discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    start_date: Mapped[datetime.date] = mapped_column(Date, index=True)
    end_date: Mapped[datetime.date] = mapped_column(Date)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="promotions")
    store: Mapped["Store | None"] = relationship(back_populates="promotions")

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
    date: Mapped[datetime.date] = mapped_column(Date, ForeignKey("calendar.date"), index=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("store.id"), index=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("product.id"), index=True)
    on_hand_qty: Mapped[int] = mapped_column(Integer)
    on_order_qty: Mapped[int] = mapped_column(Integer, default=0)
    is_stockout: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    calendar: Mapped["Calendar"] = relationship(back_populates="inventory_snapshots")
    store: Mapped["Store"] = relationship(back_populates="inventory_snapshots")
    product: Mapped["Product"] = relationship(back_populates="inventory_snapshots")

    __table_args__ = (
        UniqueConstraint(
            "date", "store_id", "product_id", name="uq_inventory_snapshot_daily_grain"
        ),
        Index("ix_inventory_snapshot_date_store", "date", "store_id"),
        CheckConstraint("on_hand_qty >= 0", name="ck_inventory_on_hand_positive"),
        CheckConstraint("on_order_qty >= 0", name="ck_inventory_on_order_positive"),
    )
