"""Pydantic schemas for analytics endpoints.

These schemas define KPI aggregations and drilldown responses
with rich descriptions for LLM tool-calling.
"""

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

# =============================================================================
# Enums
# =============================================================================


class TimeGranularity(str, Enum):
    """Time granularity for aggregations.

    Controls how time-based KPIs are grouped.
    """

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"


class DrilldownDimension(str, Enum):
    """Dimensions available for drilldown analysis.

    Each dimension groups KPIs by a different attribute.
    """

    STORE = "store"
    PRODUCT = "product"
    CATEGORY = "category"
    REGION = "region"
    DATE = "date"


# =============================================================================
# KPI Response Schemas
# =============================================================================


class KPIMetrics(BaseModel):
    """Core KPI metrics for sales analysis.

    All monetary values are in the local currency.
    """

    model_config = ConfigDict(from_attributes=True)

    total_revenue: Decimal = Field(
        ...,
        description="Total sales revenue (sum of total_amount). "
        "Represents the gross sales value before discounts.",
    )
    total_units: int = Field(
        ...,
        ge=0,
        description="Total units sold (sum of quantity). Represents the physical volume of sales.",
    )
    total_transactions: int = Field(
        ...,
        ge=0,
        description="Number of unique (date, store, product) combinations. "
        "Approximates the number of sales transactions.",
    )
    avg_unit_price: Decimal | None = Field(
        None,
        description="Average price per unit (total_revenue / total_units). Null if no units sold.",
    )
    avg_basket_value: Decimal | None = Field(
        None,
        description="Average transaction value (total_revenue / total_transactions). "
        "Null if no transactions.",
    )


class KPIResponse(BaseModel):
    """Aggregated KPI response for a date range.

    Use this to get high-level sales metrics for the specified period.
    """

    metrics: KPIMetrics = Field(
        ...,
        description="Aggregated KPI values for the date range.",
    )
    start_date: date = Field(
        ...,
        description="Start of the analysis period (inclusive).",
    )
    end_date: date = Field(
        ...,
        description="End of the analysis period (inclusive).",
    )
    store_id: int | None = Field(
        None,
        description="Store filter applied (if any). Null means all stores included.",
    )
    product_id: int | None = Field(
        None,
        description="Product filter applied (if any). Null means all products included.",
    )
    category: str | None = Field(
        None,
        description="Category filter applied (if any). Null means all categories included.",
    )


# =============================================================================
# Drilldown Response Schemas
# =============================================================================


class DrilldownItem(BaseModel):
    """A single item in a drilldown result.

    Contains the dimension value and associated metrics.
    """

    model_config = ConfigDict(from_attributes=True)

    dimension_value: str = Field(
        ...,
        description="Value of the drilldown dimension (e.g., store code, category name).",
    )
    dimension_id: int | None = Field(
        None,
        description="ID of the dimension entity (if applicable). "
        "Null for dimensions without IDs (like category).",
    )
    metrics: KPIMetrics = Field(
        ...,
        description="KPI metrics for this dimension value.",
    )
    rank: int = Field(
        ...,
        ge=1,
        description="Rank by revenue (1 = highest revenue).",
    )
    revenue_share_pct: Decimal = Field(
        ...,
        ge=0,
        le=100,
        description="Percentage of total revenue for this dimension value. "
        "Sum of all shares equals 100.",
    )


class DrilldownResponse(BaseModel):
    """Drilldown analysis response.

    Breaks down KPIs by a specific dimension with ranking and share percentages.
    """

    dimension: DrilldownDimension = Field(
        ...,
        description="Dimension used for grouping (store, product, category, etc.).",
    )
    items: list[DrilldownItem] = Field(
        ...,
        description="Drilldown items ordered by revenue (highest first). "
        "Limited to top N items based on max_items parameter.",
    )
    total_items: int = Field(
        ...,
        ge=0,
        description="Total number of unique dimension values in the data. "
        "May be larger than len(items) if results are limited.",
    )
    start_date: date = Field(
        ...,
        description="Start of the analysis period (inclusive).",
    )
    end_date: date = Field(
        ...,
        description="End of the analysis period (inclusive).",
    )
    store_id: int | None = Field(
        None,
        description="Store filter applied (if any).",
    )
    product_id: int | None = Field(
        None,
        description="Product filter applied (if any).",
    )


# =============================================================================
# Date Range Validation
# =============================================================================


class DateRangeParams(BaseModel):
    """Parameters for date range validation.

    Used internally to validate date range constraints.
    """

    start_date: date = Field(
        ...,
        description="Start date of the analysis period (inclusive).",
    )
    end_date: date = Field(
        ...,
        description="End date of the analysis period (inclusive).",
    )

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v: date, info: object) -> date:
        """Ensure end_date >= start_date."""
        data = getattr(info, "data", {})
        if "start_date" in data and v < data["start_date"]:
            msg = "end_date must be >= start_date"
            raise ValueError(msg)
        return v
