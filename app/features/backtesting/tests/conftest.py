"""Test fixtures for backtesting module."""

import uuid
from collections.abc import AsyncGenerator
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.features.backtesting.schemas import BacktestConfig, SplitConfig
from app.features.data_platform.models import Calendar, Product, SalesDaily, Store
from app.features.forecasting.schemas import NaiveModelConfig, SeasonalNaiveModelConfig
from app.main import app

# =============================================================================
# Database Fixtures for Integration Tests
# =============================================================================


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for integration tests.

    Creates tables if needed, provides a session, and cleans up test data.
    Requires PostgreSQL to be running (docker-compose up -d).
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
            # Clean up test data (delete in correct order due to FK constraints)
            await session.execute(delete(SalesDaily))
            await session.execute(delete(Product).where(Product.sku.like("TEST-%")))
            await session.execute(delete(Store).where(Store.code.like("TEST-%")))
            # Clean up calendar entries in our test date range (2024-01-01 to 2024-04-29)
            await session.execute(
                delete(Calendar).where(
                    (Calendar.date >= date(2024, 1, 1)) & (Calendar.date <= date(2024, 4, 29))
                )
            )
            await session.commit()

    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database dependency override."""

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
async def sample_store(db_session: AsyncSession) -> Store:
    """Create a sample store for testing with unique ID."""
    unique_id = uuid.uuid4().hex[:8]
    store = Store(
        code=f"TEST-{unique_id}",
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
    """Create a sample product for testing with unique ID."""
    unique_id = uuid.uuid4().hex[:8]
    product = Product(
        sku=f"TEST-{unique_id}",
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
async def sample_calendar_120(db_session: AsyncSession) -> list[Calendar]:
    """Create 120 calendar records starting from 2024-01-01.

    Uses merge to handle existing records gracefully (idempotent).
    """
    start = date(2024, 1, 1)
    calendars = []

    for i in range(120):
        d = start + timedelta(days=i)
        calendar = Calendar(
            date=d,
            day_of_week=d.weekday(),
            month=d.month,
            quarter=(d.month - 1) // 3 + 1,
            year=d.year,
            is_holiday=False,
        )
        # Use merge to handle existing records (upsert behavior)
        merged = await db_session.merge(calendar)
        calendars.append(merged)

    await db_session.commit()
    return calendars


@pytest.fixture
async def sample_sales_120(
    db_session: AsyncSession,
    sample_store: Store,
    sample_product: Product,
    sample_calendar_120: list[Calendar],
) -> list[SalesDaily]:
    """Create 120 days of sequential sales data.

    Sales quantity = day number (1, 2, 3, ..., 120) for predictable verification.
    """
    sales_records = []

    for i, calendar in enumerate(sample_calendar_120):
        quantity = i + 1  # 1, 2, 3, ..., 120
        unit_price = Decimal("9.99")
        sales = SalesDaily(
            date=calendar.date,
            store_id=sample_store.id,
            product_id=sample_product.id,
            quantity=quantity,
            unit_price=unit_price,
            total_amount=unit_price * quantity,
        )
        sales_records.append(sales)
        db_session.add(sales)

    await db_session.commit()
    for sale in sales_records:
        await db_session.refresh(sale)
    return sales_records


# =============================================================================
# Unit Test Fixtures (original)
# =============================================================================


@pytest.fixture
def sample_dates_120() -> list[date]:
    """Create 120 consecutive dates starting from 2024-01-01."""
    start = date(2024, 1, 1)
    return [start + timedelta(days=i) for i in range(120)]


@pytest.fixture
def sample_values_120() -> np.ndarray:
    """Create 120 sequential values (1, 2, 3, ..., 120)."""
    return np.array(range(1, 121), dtype=np.float64)


@pytest.fixture
def sample_dates_84() -> list[date]:
    """Create 84 consecutive dates (12 weeks) starting from 2024-01-01."""
    start = date(2024, 1, 1)
    return [start + timedelta(days=i) for i in range(84)]


@pytest.fixture
def sample_seasonal_values_84() -> np.ndarray:
    """Create 84 values with weekly pattern (12 weeks).

    Pattern: [10, 20, 30, 40, 50, 60, 70] repeated 12 times.
    """
    weekly_pattern = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0])
    return np.tile(weekly_pattern, 12)


@pytest.fixture
def sample_split_config_expanding() -> SplitConfig:
    """Create a SplitConfig with expanding window strategy."""
    return SplitConfig(
        strategy="expanding",
        n_splits=5,
        min_train_size=30,
        gap=0,
        horizon=14,
    )


@pytest.fixture
def sample_split_config_sliding() -> SplitConfig:
    """Create a SplitConfig with sliding window strategy."""
    return SplitConfig(
        strategy="sliding",
        n_splits=5,
        min_train_size=30,
        gap=0,
        horizon=14,
    )


@pytest.fixture
def sample_split_config_with_gap() -> SplitConfig:
    """Create a SplitConfig with gap between train and test."""
    return SplitConfig(
        strategy="expanding",
        n_splits=3,
        min_train_size=30,
        gap=7,
        horizon=14,
    )


@pytest.fixture
def sample_naive_config() -> NaiveModelConfig:
    """Create a naive model configuration."""
    return NaiveModelConfig()


@pytest.fixture
def sample_seasonal_config() -> SeasonalNaiveModelConfig:
    """Create a seasonal naive model configuration."""
    return SeasonalNaiveModelConfig(season_length=7)


@pytest.fixture
def sample_backtest_config_naive(sample_split_config_expanding: SplitConfig) -> BacktestConfig:
    """Create a BacktestConfig with naive model."""
    return BacktestConfig(
        split_config=sample_split_config_expanding,
        model_config_main=NaiveModelConfig(),
        include_baselines=True,
        store_fold_details=True,
    )


@pytest.fixture
def sample_backtest_config_no_baselines(
    sample_split_config_expanding: SplitConfig,
) -> BacktestConfig:
    """Create a BacktestConfig without baselines."""
    return BacktestConfig(
        split_config=sample_split_config_expanding,
        model_config_main=NaiveModelConfig(),
        include_baselines=False,
        store_fold_details=True,
    )
