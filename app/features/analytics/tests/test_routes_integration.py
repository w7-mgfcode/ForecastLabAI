"""Integration tests for analytics routes.

Runs against a real PostgreSQL database to verify the full flow from API
request through SQL aggregation to response.

Requires PostgreSQL to be running: docker-compose up -d
"""

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.data_platform.models import (
    InventorySnapshotDaily,
    Product,
    SalesDaily,
    Store,
)

# Sum of quantities 1..120 = 7260; revenue = 9.99 * 7260.
_EXPECTED_UNITS = 7260
_EXPECTED_REVENUE = Decimal("9.99") * _EXPECTED_UNITS


@pytest.mark.integration
@pytest.mark.asyncio
class TestAnalyticsTimeseriesIntegration:
    """Integration tests for GET /analytics/timeseries."""

    async def test_timeseries_day_granularity(
        self,
        client: AsyncClient,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Day granularity returns one ascending point per sales day."""
        response = await client.get(
            "/analytics/timeseries",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-04-29",
                "granularity": "day",
                "store_id": sample_store.id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["granularity"] == "day"

        points = data["points"]
        assert len(points) == 120
        assert len(points) == data["total_points"]

        periods = [p["period"] for p in points]
        assert periods == sorted(periods), "Points must be ascending by period"

        # quantity == day number: first day sold 1 unit.
        assert points[0]["period"] == "2024-01-01"
        assert points[0]["metrics"]["total_units"] == 1

    async def test_timeseries_week_granularity(
        self,
        client: AsyncClient,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Week granularity buckets days into ascending weekly periods."""
        response = await client.get(
            "/analytics/timeseries",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-04-29",
                "granularity": "week",
                "store_id": sample_store.id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["granularity"] == "week"

        points = data["points"]
        assert 0 < len(points) < 120, "Weekly buckets collapse the 120 days"
        assert len(points) == data["total_points"]

        periods = [p["period"] for p in points]
        assert periods == sorted(periods), "Points must be ascending by period"

    async def test_timeseries_store_filter_isolates_revenue(
        self,
        client: AsyncClient,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """The store_id filter scopes the series and is echoed in the response."""
        response = await client.get(
            "/analytics/timeseries",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-04-29",
                "granularity": "day",
                "store_id": sample_store.id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["store_id"] == sample_store.id

        total = sum(Decimal(p["metrics"]["total_revenue"]) for p in data["points"])
        assert total == _EXPECTED_REVENUE

    async def test_timeseries_inverted_range_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """end_date before start_date is rejected with a 400."""
        response = await client.get(
            "/analytics/timeseries",
            params={
                "start_date": "2024-04-29",
                "end_date": "2024-01-01",
                "granularity": "day",
            },
        )

        assert response.status_code == 400
        assert "detail" in response.json()


@pytest.mark.integration
@pytest.mark.asyncio
class TestAnalyticsSmokeIntegration:
    """Smoke tests for the pre-existing analytics endpoints (no slice tests today)."""

    async def test_kpis_smoke(
        self,
        client: AsyncClient,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """GET /analytics/kpis aggregates the seeded sales for the test store."""
        response = await client.get(
            "/analytics/kpis",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-04-29",
                "store_id": sample_store.id,
            },
        )

        assert response.status_code == 200
        metrics = response.json()["metrics"]
        assert metrics["total_units"] == _EXPECTED_UNITS
        assert metrics["total_transactions"] == 120
        assert Decimal(metrics["total_revenue"]) == _EXPECTED_REVENUE

    async def test_drilldowns_smoke(
        self,
        client: AsyncClient,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """GET /analytics/drilldowns by date returns ranked items."""
        response = await client.get(
            "/analytics/drilldowns",
            params={
                "dimension": "date",
                "start_date": "2024-01-01",
                "end_date": "2024-04-29",
                "store_id": sample_store.id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["dimension"] == "date"
        assert len(data["items"]) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
class TestAnalyticsInventoryStatusIntegration:
    """Integration tests for GET /analytics/inventory-status."""

    async def test_inventory_status_returns_latest_per_grain(
        self,
        client: AsyncClient,
        sample_store: Store,
        sample_product: Product,
        sample_inventory: list[InventorySnapshotDaily],
    ) -> None:
        """One item per grain, each carrying the latest snapshot for the grain."""
        response = await client.get(
            "/analytics/inventory-status",
            params={"store_id": sample_store.id},
        )

        assert response.status_code == 200
        data = response.json()
        # sample_inventory creates two grains under this store.
        assert data["total_items"] == 2
        assert len(data["items"]) == 2
        assert data["store_id"] == sample_store.id

        # Grain 1 must return the newer (2024-01-20) snapshot, not the older one.
        grain1 = next(i for i in data["items"] if i["product_id"] == sample_product.id)
        assert grain1["date"] == "2024-01-20"
        assert grain1["on_hand_qty"] == 12
        assert grain1["on_order_qty"] == 30
        assert grain1["is_stockout"] is False

        # Grain 2 is the stockout snapshot.
        stockout = next(i for i in data["items"] if i["product_id"] != sample_product.id)
        assert stockout["on_hand_qty"] == 0
        assert stockout["is_stockout"] is True

    async def test_inventory_status_product_filter_narrows(
        self,
        client: AsyncClient,
        sample_store: Store,
        sample_product: Product,
        sample_inventory: list[InventorySnapshotDaily],
    ) -> None:
        """The product_id filter narrows the result to a single grain."""
        response = await client.get(
            "/analytics/inventory-status",
            params={"store_id": sample_store.id, "product_id": sample_product.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_items"] == 1
        assert data["product_id"] == sample_product.id
        assert data["items"][0]["product_id"] == sample_product.id
        assert data["items"][0]["on_hand_qty"] == 12

    async def test_inventory_status_empty_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """An empty inventory table yields HTTP 200 with an empty list, not a 404."""
        await db_session.execute(delete(InventorySnapshotDaily))
        await db_session.commit()

        response = await client.get("/analytics/inventory-status")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total_items"] == 0
