"""Pydantic schemas for data platform validation.

These schemas are used for API input/output validation,
not for ORM operations directly.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# STORE SCHEMAS
# ============================================================================


class StoreBase(BaseModel):
    """Base schema for store data."""

    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=100)
    region: str | None = Field(default=None, max_length=50)
    city: str | None = Field(default=None, max_length=50)
    store_type: str | None = Field(default=None, max_length=30)


class StoreCreate(StoreBase):
    """Schema for creating a new store."""


class StoreRead(StoreBase):
    """Schema for reading store data."""

    id: int

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# PRODUCT SCHEMAS
# ============================================================================


class ProductBase(BaseModel):
    """Base schema for product data."""

    sku: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    brand: str | None = Field(default=None, max_length=100)
    base_price: Decimal | None = Field(default=None, ge=0)
    base_cost: Decimal | None = Field(default=None, ge=0)


class ProductCreate(ProductBase):
    """Schema for creating a new product."""


class ProductRead(ProductBase):
    """Schema for reading product data."""

    id: int

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# CALENDAR SCHEMAS
# ============================================================================


class CalendarBase(BaseModel):
    """Base schema for calendar data."""

    date: date
    day_of_week: int = Field(..., ge=0, le=6)
    month: int = Field(..., ge=1, le=12)
    quarter: int = Field(..., ge=1, le=4)
    year: int
    is_holiday: bool = False
    holiday_name: str | None = Field(default=None, max_length=100)


class CalendarCreate(CalendarBase):
    """Schema for creating a calendar entry."""


class CalendarRead(CalendarBase):
    """Schema for reading calendar data."""

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# SALES DAILY SCHEMAS
# ============================================================================


class SalesDailyBase(BaseModel):
    """Base schema for daily sales data."""

    date: date
    store_id: int = Field(..., gt=0)
    product_id: int = Field(..., gt=0)
    quantity: int = Field(..., ge=0)
    unit_price: Decimal = Field(..., ge=0)
    total_amount: Decimal = Field(..., ge=0)


class SalesDailyCreate(SalesDailyBase):
    """Schema for creating daily sales record."""


class SalesDailyRead(SalesDailyBase):
    """Schema for reading daily sales data."""

    id: int

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# PRICE HISTORY SCHEMAS
# ============================================================================


class PriceHistoryBase(BaseModel):
    """Base schema for price history data."""

    product_id: int = Field(..., gt=0)
    store_id: int | None = Field(default=None, gt=0)
    price: Decimal = Field(..., ge=0)
    valid_from: date
    valid_to: date | None = None


class PriceHistoryCreate(PriceHistoryBase):
    """Schema for creating price history record."""


class PriceHistoryRead(PriceHistoryBase):
    """Schema for reading price history data."""

    id: int

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# PROMOTION SCHEMAS
# ============================================================================


class PromotionBase(BaseModel):
    """Base schema for promotion data."""

    product_id: int = Field(..., gt=0)
    store_id: int | None = Field(default=None, gt=0)
    name: str = Field(..., min_length=1, max_length=200)
    discount_pct: Decimal | None = Field(default=None, ge=0, le=1)
    discount_amount: Decimal | None = Field(default=None, ge=0)
    start_date: date
    end_date: date


class PromotionCreate(PromotionBase):
    """Schema for creating promotion record."""


class PromotionRead(PromotionBase):
    """Schema for reading promotion data."""

    id: int

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# INVENTORY SNAPSHOT DAILY SCHEMAS
# ============================================================================


class InventorySnapshotDailyBase(BaseModel):
    """Base schema for inventory snapshot data."""

    date: date
    store_id: int = Field(..., gt=0)
    product_id: int = Field(..., gt=0)
    on_hand_qty: int = Field(..., ge=0)
    on_order_qty: int = Field(default=0, ge=0)
    is_stockout: bool = False


class InventorySnapshotDailyCreate(InventorySnapshotDailyBase):
    """Schema for creating inventory snapshot record."""


class InventorySnapshotDailyRead(InventorySnapshotDailyBase):
    """Schema for reading inventory snapshot data."""

    id: int

    model_config = ConfigDict(from_attributes=True)
