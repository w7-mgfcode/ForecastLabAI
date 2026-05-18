"""API routes for analytics endpoints.

These endpoints provide KPI aggregations and drilldown analysis
with filtering by store, product, and date range.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import BadRequestError
from app.core.logging import get_logger
from app.features.analytics.schemas import (
    DrilldownDimension,
    DrilldownResponse,
    InventoryStatusResponse,
    KPIResponse,
    TimeGranularity,
    TimeSeriesResponse,
)
from app.features.analytics.service import AnalyticsService

logger = get_logger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


# =============================================================================
# Date Range Validation Helper
# =============================================================================


def validate_date_range(start_date: date, end_date: date) -> None:
    """Validate that date range is valid.

    Args:
        start_date: Start of analysis period.
        end_date: End of analysis period.

    Raises:
        BadRequestError: If date range is invalid. Surfaces as an RFC 7807
            ``application/problem+json`` 400 via the registered handler — a
            raw ``HTTPException`` would bypass the problem-details envelope.
    """
    settings = get_settings()

    if end_date < start_date:
        raise BadRequestError(
            message=f"end_date ({end_date}) must be >= start_date ({start_date})",
        )

    days_diff = (end_date - start_date).days
    max_days = settings.analytics_max_date_range_days

    if days_diff > max_days:
        raise BadRequestError(
            message=f"Date range ({days_diff} days) exceeds maximum allowed ({max_days} days)",
        )


# =============================================================================
# KPI Endpoints
# =============================================================================


@router.get(
    "/kpis",
    response_model=KPIResponse,
    summary="Compute aggregated KPIs",
    description="""
Compute aggregated sales KPIs for a specified date range.

**Purpose**: Get high-level sales metrics (revenue, units, transactions)
with optional filtering by store, product, or category.

**Metrics Computed**:
- `total_revenue`: Sum of total_amount across all transactions
- `total_units`: Sum of quantity sold
- `total_transactions`: Count of unique (date, store, product) records
- `avg_unit_price`: total_revenue / total_units
- `avg_basket_value`: total_revenue / total_transactions

**Filtering Options**:
- `store_id`: Filter to specific store (use GET /dimensions/stores to find IDs)
- `product_id`: Filter to specific product (use GET /dimensions/products to find IDs)
- `category`: Filter by product category name (exact match)

**Date Range**:
- Both start_date and end_date are inclusive
- Maximum range: 730 days (2 years)

**Example Use Cases**:
1. Total sales this month: `GET /analytics/kpis?start_date=2024-01-01&end_date=2024-01-31`
2. Store performance: `GET /analytics/kpis?store_id=5&start_date=2024-01-01&end_date=2024-12-31`
3. Category revenue: `GET /analytics/kpis?category=Beverage&start_date=2024-01-01&end_date=2024-01-31`
""",
)
async def get_kpis(
    start_date: date = Query(
        ...,
        description="Start of analysis period (inclusive). Format: YYYY-MM-DD.",
    ),
    end_date: date = Query(
        ...,
        description="End of analysis period (inclusive). Format: YYYY-MM-DD.",
    ),
    store_id: int | None = Query(
        None,
        ge=1,
        description="Filter by store ID. Use GET /dimensions/stores to find valid IDs.",
    ),
    product_id: int | None = Query(
        None,
        ge=1,
        description="Filter by product ID. Use GET /dimensions/products to find valid IDs.",
    ),
    category: str | None = Query(
        None,
        description="Filter by product category name (exact match).",
    ),
    db: AsyncSession = Depends(get_db),
) -> KPIResponse:
    """Compute KPIs for a date range with optional filters.

    Args:
        start_date: Start of analysis period (inclusive).
        end_date: End of analysis period (inclusive).
        store_id: Filter by store ID (optional).
        product_id: Filter by product ID (optional).
        category: Filter by category (optional).
        db: Database session.

    Returns:
        Aggregated KPI metrics.

    Raises:
        BadRequestError: If date range is invalid (RFC 7807 400).
    """
    # Validate date range before processing
    validate_date_range(start_date, end_date)

    service = AnalyticsService()
    return await service.compute_kpis(
        db=db,
        start_date=start_date,
        end_date=end_date,
        store_id=store_id,
        product_id=product_id,
        category=category,
    )


# =============================================================================
# Drilldown Endpoints
# =============================================================================


@router.get(
    "/drilldowns",
    response_model=DrilldownResponse,
    summary="Compute drilldown analysis",
    description="""
Break down KPIs by a specific dimension to identify top performers.

**Purpose**: Drill into sales data by store, product, category, region, or date
to understand what's driving overall performance.

**Available Dimensions**:
- `store`: Group by store (returns store code and ID)
- `product`: Group by product (returns SKU and ID)
- `category`: Group by product category
- `region`: Group by store region
- `date`: Group by date (daily breakdown)

**Response Structure**:
Each item includes:
- Dimension value and ID (where applicable)
- Full KPI metrics (revenue, units, transactions, averages)
- Rank by revenue (1 = highest)
- Revenue share percentage

**Filtering Options**:
- `store_id`: Limit analysis to specific store
- `product_id`: Limit analysis to specific product
- `max_items`: Maximum items to return (default 20, max 100)

**Example Use Cases**:
1. Top stores by revenue: `GET /analytics/drilldowns?dimension=store&start_date=2024-01-01&end_date=2024-01-31`
2. Product mix analysis: `GET /analytics/drilldowns?dimension=product&store_id=5&start_date=2024-01-01&end_date=2024-01-31`
3. Regional performance: `GET /analytics/drilldowns?dimension=region&start_date=2024-01-01&end_date=2024-12-31`
4. Daily trend: `GET /analytics/drilldowns?dimension=date&store_id=5&product_id=10&start_date=2024-01-01&end_date=2024-01-31`
""",
)
async def get_drilldowns(
    dimension: DrilldownDimension = Query(
        ...,
        description="Dimension to group by: store, product, category, region, or date.",
    ),
    start_date: date = Query(
        ...,
        description="Start of analysis period (inclusive). Format: YYYY-MM-DD.",
    ),
    end_date: date = Query(
        ...,
        description="End of analysis period (inclusive). Format: YYYY-MM-DD.",
    ),
    store_id: int | None = Query(
        None,
        ge=1,
        description="Filter by store ID. Use GET /dimensions/stores to find valid IDs.",
    ),
    product_id: int | None = Query(
        None,
        ge=1,
        description="Filter by product ID. Use GET /dimensions/products to find valid IDs.",
    ),
    max_items: int = Query(
        20,
        ge=1,
        le=100,
        description="Maximum number of items to return (1-100, default 20).",
    ),
    db: AsyncSession = Depends(get_db),
) -> DrilldownResponse:
    """Compute drilldown analysis by dimension.

    Args:
        dimension: Dimension to group by.
        start_date: Start of analysis period (inclusive).
        end_date: End of analysis period (inclusive).
        store_id: Filter by store ID (optional).
        product_id: Filter by product ID (optional).
        max_items: Maximum items to return.
        db: Database session.

    Returns:
        Drilldown analysis with ranked items.

    Raises:
        BadRequestError: If date range is invalid (RFC 7807 400).
    """
    # Validate date range before processing
    validate_date_range(start_date, end_date)

    service = AnalyticsService()
    return await service.compute_drilldown(
        db=db,
        dimension=dimension,
        start_date=start_date,
        end_date=end_date,
        store_id=store_id,
        product_id=product_id,
        max_items=max_items,
    )


# =============================================================================
# Time Series Endpoints
# =============================================================================


@router.get(
    "/timeseries",
    response_model=TimeSeriesResponse,
    summary="Compute a period-bucketed sales time series",
    description="""
Aggregate sales into a time series bucketed by day, week, month, or quarter.

**Purpose**: Drive revenue-over-time charts. Unlike `/drilldowns?dimension=date`,
this endpoint orders points by period (not revenue), supports week/month/quarter
bucketing, and is not capped at 100 items.

**Metrics per period**: same `KPIMetrics` shape as `/analytics/kpis` —
`total_revenue`, `total_units`, `total_transactions`, `avg_unit_price`,
`avg_basket_value`.

**Filtering Options**:
- `store_id`: scope the series to a single store
- `product_id`: scope the series to a single product
- `category`: scope the series to a product category (exact match)

**Date Range**:
- Both `start_date` and `end_date` are inclusive
- Maximum range: 730 days (2 years)

**Example Use Cases**:
1. Daily revenue trend: `GET /analytics/timeseries?start_date=2024-01-01&end_date=2024-03-31&granularity=day`
2. Weekly trend for a store: `GET /analytics/timeseries?store_id=5&start_date=2024-01-01&end_date=2024-12-31&granularity=week`
""",
)
async def get_timeseries(
    start_date: date = Query(
        ...,
        description="Start of analysis period (inclusive). Format: YYYY-MM-DD.",
    ),
    end_date: date = Query(
        ...,
        description="End of analysis period (inclusive). Format: YYYY-MM-DD.",
    ),
    granularity: TimeGranularity = Query(
        TimeGranularity.DAY,
        description="Bucket size: day, week, month, or quarter.",
    ),
    store_id: int | None = Query(
        None,
        ge=1,
        description="Filter by store ID. Use GET /dimensions/stores to find valid IDs.",
    ),
    product_id: int | None = Query(
        None,
        ge=1,
        description="Filter by product ID. Use GET /dimensions/products to find valid IDs.",
    ),
    category: str | None = Query(
        None,
        description="Filter by product category name (exact match).",
    ),
    db: AsyncSession = Depends(get_db),
) -> TimeSeriesResponse:
    """Compute a period-bucketed sales time series with optional filters.

    Args:
        start_date: Start of analysis period (inclusive).
        end_date: End of analysis period (inclusive).
        granularity: Bucket size (day, week, month, quarter).
        store_id: Filter by store ID (optional).
        product_id: Filter by product ID (optional).
        category: Filter by category (optional).
        db: Database session.

    Returns:
        Time series response with points in ascending period order.

    Raises:
        BadRequestError: If date range is invalid (RFC 7807 400).
    """
    # Validate date range before processing
    validate_date_range(start_date, end_date)

    service = AnalyticsService()
    return await service.compute_timeseries(
        db=db,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        store_id=store_id,
        product_id=product_id,
        category=category,
    )


# =============================================================================
# Inventory Status Endpoint
# =============================================================================


@router.get(
    "/inventory-status",
    response_model=InventoryStatusResponse,
    summary="Latest inventory snapshot per store/product",
    description="""
Return the most recent `inventory_snapshot_daily` row for each
(store, product) grain.

**Purpose**: Surface current stock context — on-hand units, on-order units,
and the stockout flag — so a demand view can compute an inventory requirement.

**Per grain**: the latest snapshot by date (`on_hand_qty`, `on_order_qty`,
`is_stockout`).

**Filtering Options**:
- `store_id`: scope to a single store
- `product_id`: scope to a single product

**Empty data**: returns HTTP 200 with `items: []` and `total_items: 0` when no
snapshots exist — never a 404.

**Example Use Cases**:
1. All grains: `GET /analytics/inventory-status`
2. One store: `GET /analytics/inventory-status?store_id=5`
3. One grain: `GET /analytics/inventory-status?store_id=5&product_id=10`
""",
)
async def get_inventory_status(
    store_id: int | None = Query(
        None,
        ge=1,
        description="Filter by store ID. Use GET /dimensions/stores to find valid IDs.",
    ),
    product_id: int | None = Query(
        None,
        ge=1,
        description="Filter by product ID. Use GET /dimensions/products to find valid IDs.",
    ),
    db: AsyncSession = Depends(get_db),
) -> InventoryStatusResponse:
    """Return the latest inventory snapshot per (store, product) grain.

    Args:
        store_id: Filter by store ID (optional).
        product_id: Filter by product ID (optional).
        db: Database session.

    Returns:
        Latest snapshot per grain. Empty list when no snapshots exist.
    """
    service = AnalyticsService()
    return await service.compute_inventory_status(
        db=db,
        store_id=store_id,
        product_id=product_id,
    )
