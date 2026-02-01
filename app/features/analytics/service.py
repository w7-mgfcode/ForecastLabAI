"""Service layer for analytics operations.

Provides KPI aggregations and drilldown analysis using SQLAlchemy.
"""

from datetime import date
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings
from app.core.logging import get_logger
from app.features.analytics.schemas import (
    DrilldownDimension,
    DrilldownItem,
    DrilldownResponse,
    KPIMetrics,
    KPIResponse,
)
from app.features.data_platform.models import Product, SalesDaily, Store

logger = get_logger(__name__)


class AnalyticsService:
    """Service for computing sales analytics.

    Provides KPI aggregations and drilldown analysis with filtering.
    All methods are async and use SQLAlchemy 2.0 style queries.
    """

    def __init__(self) -> None:
        """Initialize analytics service."""
        self.settings = get_settings()

    async def compute_kpis(
        self,
        db: AsyncSession,
        start_date: date,
        end_date: date,
        store_id: int | None = None,
        product_id: int | None = None,
        category: str | None = None,
    ) -> KPIResponse:
        """Compute aggregated KPIs for a date range.

        Args:
            db: Database session.
            start_date: Start of analysis period (inclusive).
            end_date: End of analysis period (inclusive).
            store_id: Filter by store ID (optional).
            product_id: Filter by product ID (optional).
            category: Filter by category (optional).

        Returns:
            Aggregated KPI metrics.
        """
        # Build base query with aggregations
        stmt = select(
            func.coalesce(func.sum(SalesDaily.total_amount), 0).label("total_revenue"),
            func.coalesce(func.sum(SalesDaily.quantity), 0).label("total_units"),
            func.count().label("total_transactions"),
        ).where((SalesDaily.date >= start_date) & (SalesDaily.date <= end_date))

        # Apply filters
        if store_id is not None:
            stmt = stmt.where(SalesDaily.store_id == store_id)
        if product_id is not None:
            stmt = stmt.where(SalesDaily.product_id == product_id)
        if category is not None:
            stmt = stmt.join(Product, SalesDaily.product_id == Product.id).where(
                Product.category == category
            )

        # Execute query
        result = await db.execute(stmt)
        row = result.one()

        total_revenue = Decimal(str(row.total_revenue))
        total_units = int(row.total_units)
        total_transactions = int(row.total_transactions)

        # Compute derived metrics
        avg_unit_price = total_revenue / total_units if total_units > 0 else None
        avg_basket_value = total_revenue / total_transactions if total_transactions > 0 else None

        metrics = KPIMetrics(
            total_revenue=total_revenue,
            total_units=total_units,
            total_transactions=total_transactions,
            avg_unit_price=avg_unit_price,
            avg_basket_value=avg_basket_value,
        )

        logger.info(
            "analytics.kpis_computed",
            start_date=str(start_date),
            end_date=str(end_date),
            store_id=store_id,
            product_id=product_id,
            category=category,
            total_revenue=float(total_revenue),
            total_transactions=total_transactions,
        )

        return KPIResponse(
            metrics=metrics,
            start_date=start_date,
            end_date=end_date,
            store_id=store_id,
            product_id=product_id,
            category=category,
        )

    async def compute_drilldown(
        self,
        db: AsyncSession,
        dimension: DrilldownDimension,
        start_date: date,
        end_date: date,
        store_id: int | None = None,
        product_id: int | None = None,
        max_items: int = 20,
    ) -> DrilldownResponse:
        """Compute drilldown analysis by a specific dimension.

        Args:
            db: Database session.
            dimension: Dimension to group by.
            start_date: Start of analysis period (inclusive).
            end_date: End of analysis period (inclusive).
            store_id: Filter by store ID (optional).
            product_id: Filter by product ID (optional).
            max_items: Maximum number of items to return.

        Returns:
            Drilldown analysis with ranked items.
        """
        # Build query based on dimension - use cast for type safety
        dimension_col: ColumnElement[Any]
        dimension_id_col: ColumnElement[Any] | None
        join_clause: ColumnElement[bool] | None
        base_entity: type[DeclarativeBase] | None

        if dimension == DrilldownDimension.STORE:
            dimension_col = cast(ColumnElement[Any], Store.code)
            dimension_id_col = cast(ColumnElement[Any], Store.id)
            join_clause = SalesDaily.store_id == Store.id
            base_entity = Store
        elif dimension == DrilldownDimension.PRODUCT:
            dimension_col = cast(ColumnElement[Any], Product.sku)
            dimension_id_col = cast(ColumnElement[Any], Product.id)
            join_clause = SalesDaily.product_id == Product.id
            base_entity = Product
        elif dimension == DrilldownDimension.CATEGORY:
            dimension_col = cast(ColumnElement[Any], Product.category)
            dimension_id_col = None
            join_clause = SalesDaily.product_id == Product.id
            base_entity = Product
        elif dimension == DrilldownDimension.REGION:
            dimension_col = cast(ColumnElement[Any], Store.region)
            dimension_id_col = None
            join_clause = SalesDaily.store_id == Store.id
            base_entity = Store
        else:  # DATE
            dimension_col = cast(ColumnElement[Any], SalesDaily.date)
            dimension_id_col = None
            join_clause = None
            base_entity = None

        # Build aggregation query with explicit columns
        agg_columns: list[ColumnElement[Any]] = [
            dimension_col.label("dimension_value"),
            func.sum(SalesDaily.total_amount).label("total_revenue"),
            func.sum(SalesDaily.quantity).label("total_units"),
            func.count().label("total_transactions"),
        ]

        if dimension_id_col is not None:
            agg_columns.insert(1, dimension_id_col.label("dimension_id"))

        stmt = select(*agg_columns).where(
            (SalesDaily.date >= start_date) & (SalesDaily.date <= end_date)
        )

        # Join dimension table if needed
        if join_clause is not None and base_entity is not None:
            stmt = stmt.join(base_entity, join_clause)

        # Apply filters
        if store_id is not None:
            stmt = stmt.where(SalesDaily.store_id == store_id)
        if product_id is not None:
            stmt = stmt.where(SalesDaily.product_id == product_id)

        # Group by dimension
        if dimension_id_col is not None:
            stmt = stmt.group_by(dimension_col, dimension_id_col)
        else:
            stmt = stmt.group_by(dimension_col)

        # Filter out null dimension values
        stmt = stmt.where(dimension_col.isnot(None))

        # Order by revenue and limit
        stmt = stmt.order_by(func.sum(SalesDaily.total_amount).desc())

        # Count total items and total revenue before limiting
        # Use subquery to get count and sum from full result set
        subq = stmt.subquery()
        count_stmt = select(
            func.count(),
            func.coalesce(func.sum(subq.c.total_revenue), 0),
        ).select_from(subq)
        count_result = await db.execute(count_stmt)
        count_row = count_result.one()
        total_items = int(count_row[0])
        total_revenue_all = Decimal(str(count_row[1]))

        # Apply limit
        stmt = stmt.limit(max_items)

        # Execute query
        result = await db.execute(stmt)
        rows = result.all()

        # Build drilldown items
        items: list[DrilldownItem] = []
        for rank, row in enumerate(rows, 1):
            row_revenue = Decimal(str(row.total_revenue))
            row_units = int(row.total_units)
            row_transactions = int(row.total_transactions)

            # Calculate derived metrics
            avg_unit_price = row_revenue / row_units if row_units > 0 else None
            avg_basket_value = row_revenue / row_transactions if row_transactions > 0 else None

            # Calculate revenue share
            revenue_share = (
                (row_revenue / total_revenue_all * 100) if total_revenue_all > 0 else Decimal("0")
            )

            # Get dimension ID if available
            dim_id = getattr(row, "dimension_id", None)

            items.append(
                DrilldownItem(
                    dimension_value=str(row.dimension_value),
                    dimension_id=dim_id,
                    metrics=KPIMetrics(
                        total_revenue=row_revenue,
                        total_units=row_units,
                        total_transactions=row_transactions,
                        avg_unit_price=avg_unit_price,
                        avg_basket_value=avg_basket_value,
                    ),
                    rank=rank,
                    revenue_share_pct=round(revenue_share, 2),
                )
            )

        logger.info(
            "analytics.drilldown_computed",
            dimension=dimension.value,
            start_date=str(start_date),
            end_date=str(end_date),
            store_id=store_id,
            product_id=product_id,
            items_count=len(items),
            total_items=total_items,
        )

        return DrilldownResponse(
            dimension=dimension,
            items=items,
            total_items=total_items,
            start_date=start_date,
            end_date=end_date,
            store_id=store_id,
            product_id=product_id,
        )
