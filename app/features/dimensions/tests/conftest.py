"""Test fixtures for dimensions module."""

import uuid
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.features.data_platform.models import Calendar, Product, SalesDaily, Store
from app.main import app


@pytest.fixture
def sample_store_data():
    """Sample store data for testing."""
    return {
        "code": "S001",
        "name": "Main Street Store",
        "region": "North",
        "city": "Springfield",
        "store_type": "supermarket",
    }


@pytest.fixture
def sample_product_data():
    """Sample product data for testing."""
    return {
        "sku": "SKU-001",
        "name": "Cola Classic",
        "category": "Beverage",
        "brand": "CocaCola",
        "base_price": "2.99",
        "base_cost": "1.50",
    }


# =============================================================================
# Database Fixtures for Integration Tests
# =============================================================================


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create an async database session for integration tests.

    Yields a session, then cleans up TEST-prefixed data. Requires
    PostgreSQL (docker-compose up -d).
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        try:
            yield session
        finally:
            # Clean up test data (delete in FK-safe order).
            await session.execute(delete(SalesDaily))
            await session.execute(delete(Product).where(Product.sku.like("TEST-%")))
            await session.execute(delete(Store).where(Store.code.like("TEST-%")))
            await session.execute(
                delete(Calendar).where(
                    (Calendar.date >= date(2024, 1, 1)) & (Calendar.date <= date(2024, 4, 29))
                )
            )
            await session.commit()

    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with the database dependency overridden."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def sample_stores_multi(db_session: AsyncSession) -> list[Store]:
    """Create 3 stores sharing a unique TEST- prefix.

    Codes and names are deliberately non-aligned so that an ascending
    sort by ``code`` differs from an ascending sort by ``name``.
    """
    prefix = f"TEST-{uuid.uuid4().hex[:6]}"
    stores = [
        Store(
            code=f"{prefix}-A",
            name="Zulu Store",
            region="North",
            city="Alpha City",
            store_type="express",
        ),
        Store(
            code=f"{prefix}-B",
            name="Alpha Store",
            region="South",
            city="Zeta City",
            store_type="warehouse",
        ),
        Store(
            code=f"{prefix}-C",
            name="Mike Store",
            region="East",
            city="Mid City",
            store_type="supermarket",
        ),
    ]
    for store in stores:
        db_session.add(store)
    await db_session.commit()
    for store in stores:
        await db_session.refresh(store)
    return stores


@pytest.fixture
async def sample_products_multi(db_session: AsyncSession) -> list[Product]:
    """Create 3 products sharing a unique TEST- prefix.

    SKUs and names are deliberately non-aligned so that an ascending
    sort by ``sku`` differs from an ascending sort by ``name``.
    """
    prefix = f"TEST-{uuid.uuid4().hex[:6]}"
    products = [
        Product(
            sku=f"{prefix}-A",
            name="Zulu Widget",
            category="Cat-Z",
            brand="Brand-M",
            base_price=Decimal("9.99"),
            base_cost=Decimal("5.00"),
        ),
        Product(
            sku=f"{prefix}-B",
            name="Alpha Widget",
            category="Cat-A",
            brand="Brand-Z",
            base_price=Decimal("1.99"),
            base_cost=Decimal("1.00"),
        ),
        Product(
            sku=f"{prefix}-C",
            name="Mike Widget",
            category="Cat-M",
            brand="Brand-A",
            base_price=Decimal("5.99"),
            base_cost=Decimal("3.00"),
        ),
    ]
    for product in products:
        db_session.add(product)
    await db_session.commit()
    for product in products:
        await db_session.refresh(product)
    return products
