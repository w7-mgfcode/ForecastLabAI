"""Integration tests for ingest API routes.

These tests require a running PostgreSQL database (docker-compose up -d).
"""

from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import Base
from app.features.data_platform.models import Calendar, Product, SalesDaily, Store
from app.main import app


@pytest.fixture
async def db_session():
    """Create async database session for integration tests.

    Creates all tables, provides a session, and cleans up after.
    Requires PostgreSQL to be running (docker-compose up -d).
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.rollback()

    # Cleanup: drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def seed_data(db_session: AsyncSession):
    """Seed test data for ingest integration tests."""
    # Create stores
    stores = [
        Store(code="S001", name="Store 1", region="North", city="City A", store_type="supermarket"),
        Store(code="S002", name="Store 2", region="South", city="City B", store_type="express"),
    ]
    db_session.add_all(stores)

    # Create products
    products = [
        Product(
            sku="SKU-001",
            name="Product 1",
            category="Category A",
            brand="Brand A",
            base_price=Decimal("9.99"),
            base_cost=Decimal("5.00"),
        ),
        Product(
            sku="SKU-002",
            name="Product 2",
            category="Category A",
            brand="Brand B",
            base_price=Decimal("19.99"),
            base_cost=Decimal("10.00"),
        ),
    ]
    db_session.add_all(products)

    # Create calendar entries
    calendars = [
        Calendar(
            date=date(2024, 1, 15),
            day_of_week=0,
            month=1,
            quarter=1,
            year=2024,
            is_holiday=False,
        ),
        Calendar(
            date=date(2024, 1, 16),
            day_of_week=1,
            month=1,
            quarter=1,
            year=2024,
            is_holiday=False,
        ),
    ]
    db_session.add_all(calendars)

    await db_session.commit()

    return {"stores": stores, "products": products, "calendars": calendars}


@pytest.fixture
async def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.integration
class TestIngestSalesDaily:
    """Integration tests for POST /ingest/sales-daily endpoint."""

    @pytest.mark.asyncio
    async def test_ingest_valid_records(self, client, db_session, seed_data):
        """Test ingesting valid sales records."""
        payload = {
            "records": [
                {
                    "date": "2024-01-15",
                    "store_code": "S001",
                    "sku": "SKU-001",
                    "quantity": 10,
                    "unit_price": "9.99",
                    "total_amount": "99.90",
                },
                {
                    "date": "2024-01-15",
                    "store_code": "S001",
                    "sku": "SKU-002",
                    "quantity": 5,
                    "unit_price": "19.99",
                    "total_amount": "99.95",
                },
            ]
        }

        response = await client.post("/ingest/sales-daily", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["inserted_count"] == 2
        assert data["rejected_count"] == 0
        assert data["total_processed"] == 2
        assert data["errors"] == []
        assert data["duration_ms"] >= 0

        # Verify data in database
        result = await db_session.execute(select(SalesDaily))
        sales_records = result.scalars().all()
        assert len(sales_records) == 2

    @pytest.mark.asyncio
    async def test_ingest_idempotency(self, client, db_session, seed_data):
        """Test that running same ingest twice updates rather than duplicates."""
        payload = {
            "records": [
                {
                    "date": "2024-01-15",
                    "store_code": "S001",
                    "sku": "SKU-001",
                    "quantity": 10,
                    "unit_price": "9.99",
                    "total_amount": "99.90",
                },
            ]
        }

        # First ingest
        response1 = await client.post("/ingest/sales-daily", json=payload)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["inserted_count"] == 1

        # Verify one record exists
        result = await db_session.execute(select(SalesDaily))
        records_after_first = result.scalars().all()
        assert len(records_after_first) == 1
        assert records_after_first[0].quantity == 10

        # Second ingest with updated quantity
        payload["records"][0]["quantity"] = 15
        payload["records"][0]["total_amount"] = "149.85"

        response2 = await client.post("/ingest/sales-daily", json=payload)
        assert response2.status_code == 200

        # Verify still only one record (updated, not duplicated)
        db_session.expire_all()  # Synchronous method
        result = await db_session.execute(select(SalesDaily))
        records_after_second = result.scalars().all()
        assert len(records_after_second) == 1
        assert records_after_second[0].quantity == 15

    @pytest.mark.asyncio
    async def test_ingest_partial_success(self, client, db_session, seed_data):
        """Test partial success with mixed valid/invalid rows."""
        payload = {
            "records": [
                {
                    "date": "2024-01-15",
                    "store_code": "S001",
                    "sku": "SKU-001",
                    "quantity": 10,
                    "unit_price": "9.99",
                    "total_amount": "99.90",
                },
                {
                    "date": "2024-01-15",
                    "store_code": "UNKNOWN",  # Invalid store
                    "sku": "SKU-001",
                    "quantity": 5,
                    "unit_price": "9.99",
                    "total_amount": "49.95",
                },
            ]
        }

        response = await client.post("/ingest/sales-daily", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["inserted_count"] == 1
        assert data["rejected_count"] == 1
        assert data["total_processed"] == 2
        assert len(data["errors"]) == 1
        assert data["errors"][0]["error_code"] == "UNKNOWN_STORE"
        assert data["errors"][0]["row_index"] == 1

    @pytest.mark.asyncio
    async def test_ingest_unknown_store(self, client, db_session, seed_data):
        """Test that unknown store code returns error."""
        payload = {
            "records": [
                {
                    "date": "2024-01-15",
                    "store_code": "NONEXISTENT",
                    "sku": "SKU-001",
                    "quantity": 10,
                    "unit_price": "9.99",
                    "total_amount": "99.90",
                },
            ]
        }

        response = await client.post("/ingest/sales-daily", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["inserted_count"] == 0
        assert data["rejected_count"] == 1
        assert data["errors"][0]["error_code"] == "UNKNOWN_STORE"

    @pytest.mark.asyncio
    async def test_ingest_unknown_product(self, client, db_session, seed_data):
        """Test that unknown SKU returns error."""
        payload = {
            "records": [
                {
                    "date": "2024-01-15",
                    "store_code": "S001",
                    "sku": "NONEXISTENT-SKU",
                    "quantity": 10,
                    "unit_price": "9.99",
                    "total_amount": "99.90",
                },
            ]
        }

        response = await client.post("/ingest/sales-daily", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["inserted_count"] == 0
        assert data["rejected_count"] == 1
        assert data["errors"][0]["error_code"] == "UNKNOWN_PRODUCT"

    @pytest.mark.asyncio
    async def test_ingest_unknown_date(self, client, db_session, seed_data):
        """Test that date not in calendar returns error."""
        payload = {
            "records": [
                {
                    "date": "2024-12-31",  # Not in seeded calendar
                    "store_code": "S001",
                    "sku": "SKU-001",
                    "quantity": 10,
                    "unit_price": "9.99",
                    "total_amount": "99.90",
                },
            ]
        }

        response = await client.post("/ingest/sales-daily", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["inserted_count"] == 0
        assert data["rejected_count"] == 1
        assert data["errors"][0]["error_code"] == "UNKNOWN_DATE"

    @pytest.mark.asyncio
    async def test_ingest_empty_records_rejected(self, client):
        """Test that empty records list returns 422."""
        payload: dict[str, list[dict[str, str]]] = {"records": []}

        response = await client.post("/ingest/sales-daily", json=payload)

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_ingest_negative_quantity_rejected(self, client):
        """Test that negative quantity returns 422."""
        payload = {
            "records": [
                {
                    "date": "2024-01-15",
                    "store_code": "S001",
                    "sku": "SKU-001",
                    "quantity": -5,
                    "unit_price": "9.99",
                    "total_amount": "99.90",
                },
            ]
        }

        response = await client.post("/ingest/sales-daily", json=payload)

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_ingest_response_has_request_id(self, client, db_session, seed_data):
        """Test that response has X-Request-ID header."""
        payload = {
            "records": [
                {
                    "date": "2024-01-15",
                    "store_code": "S001",
                    "sku": "SKU-001",
                    "quantity": 10,
                    "unit_price": "9.99",
                    "total_amount": "99.90",
                },
            ]
        }

        response = await client.post("/ingest/sales-daily", json=payload)

        assert response.status_code == 200
        assert "x-request-id" in response.headers
