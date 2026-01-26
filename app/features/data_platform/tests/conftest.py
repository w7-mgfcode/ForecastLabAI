"""Fixtures for data platform integration tests.

Note: The db_session fixture is duplicated here because pytest fixtures are discovered
based on conftest.py files in the directory path. Tests in app/features/*/tests/ cannot
see fixtures in tests/conftest.py since it's not in their parent path. This is intentional
pytest behavior to allow feature tests to be self-contained.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import Base
from app.features.data_platform.models import Calendar, Product, Store


@pytest.fixture
async def db_session():
    """Create async database session for integration tests.

    This fixture creates all tables, provides a session, and cleans up after.
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
