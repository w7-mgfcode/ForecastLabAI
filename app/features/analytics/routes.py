"""API routes for analytics endpoints.

These endpoints provide KPI aggregations and drilldown analysis
with filtering by store, product, and date range.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.features.analytics.schemas import (
    DrilldownDimension,
    DrilldownResponse,
    KPIResponse,
)
from app.features.analytics.service import AnalyticsService

logger = get_logger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


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
        description="Filter by store ID. Use GET /dimensions/stores to find valid IDs.",
    ),
    product_id: int | None = Query(
        None,
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
    """
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
        description="Filter by store ID. Use GET /dimensions/stores to find valid IDs.",
    ),
    product_id: int | None = Query(
        None,
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
    """
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
