"""Test fixtures for analytics module."""

import uuid
from collections.abc import AsyncGenerator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.features.analytics.schemas import (
    DrilldownDimension,
    DrilldownItem,
    DrilldownResponse,
    KPIMetrics,
    KPIResponse,
)
from app.features.data_platform.models import (
    Calendar,
    InventorySnapshotDaily,
    Product,
    SalesDaily,
    Store,
)
from app.main import app


@pytest.fixture
def sample_kpi_metrics() -> KPIMetrics:
    """Create sample KPI metrics for testing."""
    return KPIMetrics(
        total_revenue=Decimal("10000.00"),
        total_units=500,
        total_transactions=100,
        avg_unit_price=Decimal("20.00"),
        avg_basket_value=Decimal("100.00"),
    )


@pytest.fixture
def sample_kpi_response(sample_kpi_metrics: KPIMetrics) -> KPIResponse:
    """Create sample KPI response for testing."""
    return KPIResponse(
        metrics=sample_kpi_metrics,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        store_id=None,
        product_id=None,
        category=None,
    )


@pytest.fixture
def sample_drilldown_items(sample_kpi_metrics: KPIMetrics) -> list[DrilldownItem]:
    """Create sample drilldown items for testing."""
    return [
        DrilldownItem(
            dimension_value="S001",
            dimension_id=1,
            metrics=sample_kpi_metrics,
            rank=1,
            revenue_share_pct=Decimal("60.00"),
        ),
        DrilldownItem(
            dimension_value="S002",
            dimension_id=2,
            metrics=KPIMetrics(
                total_revenue=Decimal("5000.00"),
                total_units=250,
                total_transactions=50,
                avg_unit_price=Decimal("20.00"),
                avg_basket_value=Decimal("100.00"),
            ),
            rank=2,
            revenue_share_pct=Decimal("40.00"),
        ),
    ]


@pytest.fixture
def sample_drilldown_response(
    sample_drilldown_items: list[DrilldownItem],
) -> DrilldownResponse:
    """Create sample drilldown response for testing."""
    return DrilldownResponse(
        dimension=DrilldownDimension.STORE,
        items=sample_drilldown_items,
        total_items=2,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        store_id=None,
        product_id=None,
    )


# =============================================================================
# Database Fixtures for Integration Tests
# =============================================================================


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create an async database session for integration tests.

    Yields a session, then cleans up TEST-prefixed data and the test
    calendar range. Requires PostgreSQL (docker-compose up -d).
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
            # Clean up test data (delete in FK-safe order). InventorySnapshotDaily
            # FK-references store/product/calendar, so it must be cleared before
            # the Store/Product/Calendar deletes below.
            await session.execute(delete(InventorySnapshotDaily))
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
async def sample_store(db_session: AsyncSession) -> Store:
    """Create a sample store with a unique TEST- code."""
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
    """Create a sample product with a unique TEST- SKU."""
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
    """Create 120 calendar records starting from 2024-01-01 (idempotent)."""
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
    """Create 120 days of sequential sales (quantity = day number 1..120)."""
    sales_records = []

    for i, calendar in enumerate(sample_calendar_120):
        quantity = i + 1
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


@pytest.fixture
async def sample_inventory(
    db_session: AsyncSession,
    sample_store: Store,
    sample_product: Product,
    sample_calendar_120: list[Calendar],
) -> list[InventorySnapshotDaily]:
    """Create inventory snapshots for two grains.

    Grain 1 (sample_store, sample_product): two snapshots on different dates,
    so a test can prove the latest (2024-01-20) wins over the older one
    (2024-01-10). Grain 2 (sample_store, a second TEST- product): a single
    stockout snapshot. The second product is TEST-prefixed so the db_session
    cleanup removes it.
    """
    unique_id = uuid.uuid4().hex[:8]
    product2 = Product(
        sku=f"TEST-{unique_id}",
        name="Test Product 2",
        category="Test Category",
        brand="Test Brand",
        base_price=Decimal("29.99"),
        base_cost=Decimal("14.99"),
    )
    db_session.add(product2)
    await db_session.commit()
    await db_session.refresh(product2)

    snapshots = [
        # Grain 1 — older snapshot (must be superseded by the newer one).
        InventorySnapshotDaily(
            date=date(2024, 1, 10),
            store_id=sample_store.id,
            product_id=sample_product.id,
            on_hand_qty=50,
            on_order_qty=10,
            is_stockout=False,
        ),
        # Grain 1 — newer snapshot (latest-per-grain must return this one).
        InventorySnapshotDaily(
            date=date(2024, 1, 20),
            store_id=sample_store.id,
            product_id=sample_product.id,
            on_hand_qty=12,
            on_order_qty=30,
            is_stockout=False,
        ),
        # Grain 2 — single stockout snapshot.
        InventorySnapshotDaily(
            date=date(2024, 1, 15),
            store_id=sample_store.id,
            product_id=product2.id,
            on_hand_qty=0,
            on_order_qty=0,
            is_stockout=True,
        ),
    ]
    for snapshot in snapshots:
        db_session.add(snapshot)

    await db_session.commit()
    for snapshot in snapshots:
        await db_session.refresh(snapshot)
    return snapshots
