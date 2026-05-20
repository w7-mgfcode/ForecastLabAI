"""Test fixtures for the batch slice (PRP-33)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.features.batch.models import BatchJob, BatchJobItem
from app.features.data_platform.models import Calendar, Product, SalesDaily, Store
from app.main import app


@pytest.fixture
def sample_manual_payload() -> dict[str, Any]:
    """A canonical 3-pair manual backtest submit payload."""
    return {
        "operation": "backtest",
        "scope": {"kind": "manual", "store_ids": [1], "product_ids": [1, 2, 3]},
        "model_configs": [{"model_type": "naive", "params": {}}],
        "start_date": "2025-01-01",
        "end_date": "2025-06-30",
    }


@pytest.fixture
def sample_top_revenue_payload() -> dict[str, Any]:
    """A top_revenue scope payload — top_n=2, one model."""
    return {
        "operation": "backtest",
        "scope": {"kind": "top_revenue", "top_n": 2},
        "model_configs": [{"model_type": "naive", "params": {}}],
        "start_date": "2025-01-01",
        "end_date": "2025-06-30",
    }


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async database session for integration tests.

    Cleans up rows whose ``batch_id`` starts with ``test`` after each test —
    cascade FK removes their child items automatically.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        try:
            yield session
        finally:
            # FK CASCADE removes batch_job_item rows when the parent goes;
            # explicit batch_job_item DELETE handles orphans from prior failed runs.
            await session.execute(delete(BatchJobItem).where(BatchJobItem.batch_id.like("test%")))
            await session.execute(delete(BatchJob).where(BatchJob.batch_id.like("test%")))
            await session.commit()
    await engine.dispose()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """HTTP client bound to the FastAPI app via ASGI transport (no real port)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ============================================================================
# Seed fixtures for integration tests — mirror the backtesting conftest.
# Each test gets unique store/product codes so concurrent runs don't collide.
# ============================================================================


@pytest.fixture
async def sample_store(db_session: AsyncSession) -> Store:
    """One isolated store for integration tests."""
    unique_id = uuid.uuid4().hex[:8]
    store = Store(
        code=f"BATCH-{unique_id}",
        name="Batch Test Store",
        region="Batch Test Region",
        city="Batch Test City",
        store_type="supermarket",
    )
    db_session.add(store)
    await db_session.commit()
    await db_session.refresh(store)
    return store


@pytest.fixture
async def sample_products_3(db_session: AsyncSession) -> list[Product]:
    """Three isolated products for the 3-pair happy-path test."""
    products: list[Product] = []
    for _ in range(3):
        unique_id = uuid.uuid4().hex[:8]
        product = Product(
            sku=f"BATCH-{unique_id}",
            name=f"Batch Test Product {unique_id}",
            category="Batch Test Category",
            brand="Batch Test Brand",
            base_price=Decimal("19.99"),
            base_cost=Decimal("9.99"),
        )
        db_session.add(product)
        products.append(product)
    await db_session.commit()
    for p in products:
        await db_session.refresh(p)
    return products


@pytest.fixture
async def sample_calendar_120(db_session: AsyncSession) -> list[Calendar]:
    """120 calendar rows starting 2024-01-01 (idempotent via merge)."""
    start = date(2024, 1, 1)
    rows: list[Calendar] = []
    for i in range(120):
        d = start + timedelta(days=i)
        c = Calendar(
            date=d,
            day_of_week=d.weekday(),
            month=d.month,
            quarter=(d.month - 1) // 3 + 1,
            year=d.year,
            is_holiday=False,
        )
        merged = await db_session.merge(c)
        rows.append(merged)
    await db_session.commit()
    return rows


@pytest.fixture
async def sample_sales_120(
    db_session: AsyncSession,
    sample_store: Store,
    sample_products_3: list[Product],
    sample_calendar_120: list[Calendar],
) -> list[SalesDaily]:
    """120 days of sequential sales for the 3 products at the one store.

    Quantity = day number (1..120) so the naive backtest produces stable,
    non-NaN metrics.
    """
    sales: list[SalesDaily] = []
    for product in sample_products_3:
        for i, cal in enumerate(sample_calendar_120):
            qty = i + 1
            unit_price = Decimal("9.99")
            row = SalesDaily(
                date=cal.date,
                store_id=sample_store.id,
                product_id=product.id,
                quantity=qty,
                unit_price=unit_price,
                total_amount=unit_price * qty,
            )
            db_session.add(row)
            sales.append(row)
    await db_session.commit()
    return sales
