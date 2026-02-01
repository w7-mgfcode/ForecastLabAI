"""Fixtures for data platform integration tests.

Note: The db_session fixture is duplicated here because pytest fixtures are discovered
based on conftest.py files in the directory path. Tests in app/features/*/tests/ cannot
see fixtures in tests/conftest.py since it's not in their parent path. This is intentional
pytest behavior to allow feature tests to be self-contained.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.features.data_platform.models import (
    Calendar,
    InventorySnapshotDaily,
    PriceHistory,
    Product,
    Promotion,
    SalesDaily,
    Store,
)


@pytest.fixture
async def db_session():
    """Create async database session for integration tests.

    Uses existing tables from migrations. Cleans up test data after each test.
    Requires PostgreSQL to be running (docker-compose up -d) and migrations applied.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

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
            # Rollback any pending transaction first (required if test caused an error)
            try:
                await session.rollback()
            except Exception:
                pass

    # Use a fresh session for cleanup to avoid transaction state issues
    async with async_session_maker() as cleanup_session:
        try:
            # Clean up test data (delete in correct order due to FK constraints)
            await cleanup_session.execute(delete(SalesDaily))
            await cleanup_session.execute(delete(InventorySnapshotDaily))
            await cleanup_session.execute(delete(PriceHistory))
            await cleanup_session.execute(delete(Promotion))
            await cleanup_session.execute(delete(Product).where(Product.sku.like("SKU-TEST%")))
            await cleanup_session.execute(delete(Product).where(Product.sku.like("TEST-%")))
            await cleanup_session.execute(delete(Store).where(Store.code.like("TEST%")))
            await cleanup_session.execute(
                delete(Calendar).where(
                    (Calendar.date >= date(2024, 1, 1)) & (Calendar.date <= date(2024, 12, 31))
                )
            )
            await cleanup_session.commit()
        except Exception:
            # If cleanup fails, continue anyway - next test run will try again
            pass

    await engine.dispose()


@pytest.fixture
async def sample_store(db_session: AsyncSession) -> Store:
    """Create a sample store for testing."""
    store = Store(
        code="TEST001",
        name="Test Store",
        region="Test Region",
        city="Test City",
        store_type="supermarket",
    )
    db_session.add(store)
    await db_session.commit()
    await db_session.refresh(store)
    return store


@pytest.fixture
async def sample_product(db_session: AsyncSession) -> Product:
    """Create a sample product for testing."""
    product = Product(
        sku="SKU-TEST-001",
        name="Test Product",
        category="Test Category",
        brand="Test Brand",
        base_price=Decimal("19.99"),
        base_cost=Decimal("9.99"),
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


@pytest.fixture
async def sample_calendar(db_session: AsyncSession) -> Calendar:
    """Create a sample calendar entry for testing."""
    calendar = Calendar(
        date=date(2024, 1, 15),
        day_of_week=0,  # Monday
        month=1,
        quarter=1,
        year=2024,
        is_holiday=False,
    )
    db_session.add(calendar)
    await db_session.commit()
    await db_session.refresh(calendar)
    return calendar
