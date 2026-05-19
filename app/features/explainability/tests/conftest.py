"""Test fixtures for the explainability slice.

Unit fixtures supply numpy series and a ``make_mock_db`` factory that builds an
``AsyncMock`` session whose ``execute`` calls are scripted in order. Integration
fixtures (``@pytest.mark.integration``) seed a real ``docker compose`` Postgres
and clean up after themselves; ``forecast_explanation`` is a slice-private table
so its teardown wipes it whole.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import AsyncGenerator
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.features.data_platform.models import Calendar, Product, SalesDaily, Store
from app.features.explainability.models import ForecastExplanation
from app.features.registry.models import ModelRun, RunStatus
from app.main import app

# Test date range — kept narrow so the calendar teardown is precise.
TEST_START = date(2024, 1, 1)
TEST_DAYS = 90
TEST_END = TEST_START + timedelta(days=TEST_DAYS - 1)


# =============================================================================
# Unit fixtures — numpy series + scripted-mock DB factory
# =============================================================================


@pytest.fixture
def sample_series() -> np.ndarray:
    """A 60-observation float series with mild variation."""
    return np.array([float(10 + (i % 7)) for i in range(60)], dtype=np.float64)


@pytest.fixture
def flat_series() -> np.ndarray:
    """A 30-observation constant series."""
    return np.full(30, 25.0, dtype=np.float64)


@pytest.fixture
def short_series() -> np.ndarray:
    """A 3-observation series (shorter than every comfortable threshold)."""
    return np.array([5.0, 7.0, 6.0], dtype=np.float64)


def mock_result(*, scalars: list[Any] | None = None, one: Any | None = None) -> MagicMock:
    """Build a mock SQLAlchemy ``Result`` for one ``execute`` call."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = scalars or []
    result.scalar_one_or_none.return_value = one
    return result


def make_mock_db(results: list[MagicMock]) -> AsyncMock:
    """Build an ``AsyncMock`` session whose ``execute`` returns ``results`` in order.

    Args:
        results: Mock ``Result`` objects (see ``mock_result``), one per expected
            ``execute`` call, in call order.

    Returns:
        A mock session ready to pass to ``ExplainabilityService``.
    """
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=results)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


def sales_rows(values: list[float], start: date = TEST_START) -> list[SimpleNamespace]:
    """Build sales-row stand-ins (``.quantity`` / ``.date``) for the mock DB."""
    return [
        SimpleNamespace(quantity=int(v), date=start + timedelta(days=i))
        for i, v in enumerate(values)
    ]


def forecast_result_db(values: list[float]) -> AsyncMock:
    """Mock DB for one ``explain_forecast`` call (series + 4 reason-code queries)."""
    return make_mock_db(
        [
            mock_result(scalars=sales_rows(values)),  # _load_series
            mock_result(scalars=[]),  # inventory
            mock_result(scalars=[]),  # promotion
            mock_result(one=None),  # product
            mock_result(one=None),  # calendar
        ]
    )


# =============================================================================
# Integration fixtures — real Postgres
# =============================================================================


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session; wipe explainability + test data on teardown."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        try:
            yield session
        finally:
            await session.execute(delete(ForecastExplanation))
            await session.execute(delete(SalesDaily))
            await session.execute(delete(ModelRun).where(ModelRun.run_id.like("texpl%")))
            await session.execute(delete(Product).where(Product.sku.like("TEXPL-%")))
            await session.execute(delete(Store).where(Store.code.like("TEXPL-%")))
            await session.execute(
                delete(Calendar).where((Calendar.date >= TEST_START) & (Calendar.date <= TEST_END))
            )
            await session.commit()

    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Test client with the database dependency overridden."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def seeded_series(db_session: AsyncSession) -> dict[str, int]:
    """Seed a store, product, calendar, and a sales series; return ids.

    The series is a clean weekly pattern so the seasonal-naive h=1 forecast is
    deterministic.
    """
    suffix = uuid.uuid4().hex[:8]
    store = Store(code=f"TEXPL-{suffix}", name="Explain Store", region="R", store_type="x")
    product = Product(
        sku=f"TEXPL-{suffix}",
        name="Explain Product",
        category="C",
        base_price=Decimal("9.99"),
        launch_date=TEST_START,
    )
    db_session.add_all([store, product])
    await db_session.commit()
    await db_session.refresh(store)
    await db_session.refresh(product)

    weekly = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
    for i in range(TEST_DAYS):
        d = TEST_START + timedelta(days=i)
        await db_session.merge(
            Calendar(
                date=d,
                day_of_week=d.weekday(),
                month=d.month,
                quarter=(d.month - 1) // 3 + 1,
                year=d.year,
                is_holiday=False,
            )
        )
    await db_session.commit()

    for i in range(TEST_DAYS):
        qty = weekly[i % 7]
        db_session.add(
            SalesDaily(
                date=TEST_START + timedelta(days=i),
                store_id=store.id,
                product_id=product.id,
                quantity=int(qty),
                unit_price=Decimal("9.99"),
                total_amount=Decimal("9.99") * int(qty),
            )
        )
    await db_session.commit()

    return {"store_id": store.id, "product_id": product.id}


@pytest.fixture
async def seeded_run(db_session: AsyncSession, seeded_series: dict[str, int]) -> str:
    """Seed a successful baseline ModelRun over the seeded series; return run_id."""
    run_id = f"texpl{uuid.uuid4().hex[:11]}"
    run = ModelRun(
        run_id=run_id,
        status=RunStatus.SUCCESS.value,
        model_type="naive",
        model_config={"model_type": "naive", "schema_version": "1.0"},
        config_hash="deadbeefdeadbeef",
        data_window_start=TEST_START,
        data_window_end=TEST_END,
        store_id=seeded_series["store_id"],
        product_id=seeded_series["product_id"],
    )
    db_session.add(run)
    await db_session.commit()
    return run_id


@pytest.fixture
def explanation_row_kwargs() -> dict[str, Any]:
    """Valid keyword args for constructing a ForecastExplanation ORM row."""
    return {
        "explanation_id": uuid.uuid4().hex,
        "store_id": 1,
        "product_id": 2,
        "model_type": "naive",
        "method": "rule_based",
        "as_of_date": datetime.date(2024, 3, 1),
        "forecast_value": 42.0,
        "confidence": "medium",
        "drivers": [{"name": "last_observation", "contribution": 42.0}],
        "reason_codes": [],
        "caveats": ["correlation not causation"],
        "agent_summary": "A test explanation.",
    }
