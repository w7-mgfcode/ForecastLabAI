"""Test fixtures + factories for the model_selection slice (issue #353).

Unit helpers build ``CandidateResult`` / fake backtest+predict responses and a
mock ``AsyncSession`` whose ``flush`` stamps ``created_at`` (so the response
mapper, which reads it, works without a real DB). Integration fixtures
(``@pytest.mark.integration``) seed a real ``docker compose`` Postgres and clean
up after themselves with prefix-scoped teardown.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.features.backtesting.schemas import SplitConfig
from app.features.data_platform.models import Calendar, Product, SalesDaily, Store
from app.features.model_selection.models import ModelSelectionRun
from app.features.model_selection.schemas import (
    CandidateResult,
    FoldChart,
    PairAvailabilityResponse,
)
from app.main import app

# Integration test window.
TEST_START = date(2024, 1, 1)
# Largest ``n_days`` any seeding fixture below uses (``ready_pair`` = 120). The
# teardown deletes Calendar over ``[TEST_START, TEST_START + _MAX_SEED_DAYS)``;
# keep this >= the biggest ``_seed_pair`` call so no seeded calendar row leaks.
_MAX_SEED_DAYS = 120


# =============================================================================
# Unit factories
# =============================================================================


def make_candidate_result(
    model_type: str,
    *,
    wape: float = 20.0,
    smape: float = 15.0,
    mae: float = 5.0,
    rmse: float = 6.0,
    bias: float = 0.5,
    sample_size: int = 28,
    n_folds: int = 2,
    points_per_fold: int = 14,
    params: dict[str, Any] | None = None,
    failed: bool = False,
    error: str | None = None,
    aggregated_metrics: dict[str, float] | None = None,
) -> CandidateResult:
    """Build a ``CandidateResult`` for ranking/chart unit tests."""
    if failed:
        return CandidateResult(
            model_type=model_type,
            params=params or {},
            failed=True,
            error=error or "boom",
            aggregated_metrics=None,
            sample_size=0,
            folds=[],
        )
    folds = [
        FoldChart(
            fold_index=i,
            dates=[
                TEST_START + timedelta(days=i * points_per_fold + j) for j in range(points_per_fold)
            ],
            actuals=[10.0 + j for j in range(points_per_fold)],
            predictions=[10.5 + j for j in range(points_per_fold)],
        )
        for i in range(n_folds)
    ]
    metrics = aggregated_metrics or {
        "mae": mae,
        "rmse": rmse,
        "smape": smape,
        "wape": wape,
        "bias": bias,
    }
    return CandidateResult(
        model_type=model_type,
        params=params or {},
        failed=False,
        aggregated_metrics=metrics,
        sample_size=sample_size,
        config_hash="cafef00d",
        folds=folds,
    )


def make_backtest_response(
    *,
    wape: float = 20.0,
    smape: float = 15.0,
    mae: float = 5.0,
    rmse: float = 6.0,
    bias: float = 0.5,
    n_folds: int = 2,
    points_per_fold: int = 14,
) -> SimpleNamespace:
    """A duck-typed stand-in for ``BacktestResponse`` (what _shape_candidate reads)."""
    folds = [
        SimpleNamespace(
            fold_index=i,
            dates=[
                TEST_START + timedelta(days=i * points_per_fold + j) for j in range(points_per_fold)
            ],
            actuals=[10.0 + j for j in range(points_per_fold)],
            predictions=[10.5 + j for j in range(points_per_fold)],
        )
        for i in range(n_folds)
    ]
    main = SimpleNamespace(
        fold_results=folds,
        aggregated_metrics={
            "mae": mae,
            "rmse": rmse,
            "smape": smape,
            "wape": wape,
            "bias": bias,
        },
        metric_std={},
    )
    return SimpleNamespace(main_model_results=main, config_hash="bt00deadbeef", backtest_id="bt")


def make_availability(
    *,
    status: str = "ready",
    store_id: int = 1,
    product_id: int = 1,
    horizon: int = 14,
) -> PairAvailabilityResponse:
    """A ready/limited/unusable availability response for service unit tests."""
    return PairAvailabilityResponse(
        store_id=store_id,
        product_id=product_id,
        first_sales_date=TEST_START,
        last_sales_date=TEST_START + timedelta(days=119),
        observed_days=120,
        expected_calendar_days=120,
        coverage_ratio=1.0,
        missing_days=0,
        zero_sale_days=0,
        promotion_days=0,
        average_daily_demand=12.0,
        status=status,  # type: ignore[arg-type]
        recommended_split_config=SplitConfig(
            strategy="expanding", n_splits=5, min_train_size=30, gap=0, horizon=horizon
        ),
        warnings=[],
    )


def make_mock_db() -> AsyncMock:
    """Mock ``AsyncSession`` whose flush stamps ``created_at`` on added rows."""
    db = AsyncMock()
    added: list[Any] = []

    def _add(obj: Any) -> None:
        added.append(obj)

    async def _flush() -> None:
        for obj in added:
            if isinstance(obj, ModelSelectionRun) and obj.created_at is None:
                obj.created_at = datetime.now(UTC)

    db.add = MagicMock(side_effect=_add)
    db.flush = AsyncMock(side_effect=_flush)
    db.refresh = AsyncMock()
    return db


# =============================================================================
# Integration fixtures — real Postgres
# =============================================================================


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session; wipe model_selection + test data on teardown."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        try:
            yield session
        finally:
            store_ids = _registered_store_ids()
            if store_ids:
                await session.execute(
                    delete(ModelSelectionRun).where(ModelSelectionRun.store_id.in_(store_ids))
                )
            await session.execute(
                delete(SalesDaily).where(SalesDaily.unit_price == Decimal("3.33"))
            )
            await session.execute(delete(Product).where(Product.sku.like("TMSEL-%")))
            await session.execute(delete(Store).where(Store.code.like("TMSEL-%")))
            # Clean up the Calendar rows the fixtures seeded — leaving them
            # orphaned poisons the shared integration DB: the seeder's
            # calendar-seed step skips when the calendar is already non-empty,
            # so downstream phase-2 enrichment (replenishment_event → calendar
            # FK) fails on dates this partial calendar never covered. The
            # seeded sales rows above are already gone, so this delete is
            # FK-safe (scoped to exactly the dates _seed_pair creates).
            await session.execute(
                delete(Calendar).where(
                    Calendar.date >= TEST_START,
                    Calendar.date <= TEST_START + timedelta(days=_MAX_SEED_DAYS - 1),
                )
            )
            await session.commit()

    await engine.dispose()


# Track store ids created by the seeding fixtures so teardown can scope the
# model_selection_run cleanup precisely.
_SEEDED_STORE_IDS: list[int] = []


def _registered_store_ids() -> list[int]:
    return list(_SEEDED_STORE_IDS)


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Test client with the database dependency overridden."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


async def _seed_pair(db: AsyncSession, n_days: int) -> dict[str, Any]:
    """Seed a store/product/calendar + a clean weekly sales series of n_days."""
    suffix = uuid.uuid4().hex[:8]
    store = Store(code=f"TMSEL-{suffix}", name="MSel Store", region="R", store_type="x")
    product = Product(
        sku=f"TMSEL-{suffix}",
        name="MSel Product",
        category="C",
        base_price=Decimal("3.33"),
        launch_date=TEST_START,
    )
    db.add_all([store, product])
    await db.commit()
    await db.refresh(store)
    await db.refresh(product)
    _SEEDED_STORE_IDS.append(store.id)

    weekly = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
    for i in range(n_days):
        d = TEST_START + timedelta(days=i)
        await db.merge(
            Calendar(
                date=d,
                day_of_week=d.weekday(),
                month=d.month,
                quarter=(d.month - 1) // 3 + 1,
                year=d.year,
                is_holiday=False,
            )
        )
    await db.commit()

    for i in range(n_days):
        qty = int(weekly[i % 7])
        db.add(
            SalesDaily(
                date=TEST_START + timedelta(days=i),
                store_id=store.id,
                product_id=product.id,
                quantity=qty,
                unit_price=Decimal("3.33"),
                total_amount=Decimal("3.33") * qty,
            )
        )
    await db.commit()
    return {
        "store_id": store.id,
        "product_id": product.id,
        "start_date": TEST_START.isoformat(),
        "end_date": (TEST_START + timedelta(days=n_days - 1)).isoformat(),
        "n_days": n_days,
    }


@pytest.fixture
async def ready_pair(db_session: AsyncSession) -> dict[str, Any]:
    """A 120-day pair — ``ready`` for horizon=14, n_splits=5 (threshold 100)."""
    return await _seed_pair(db_session, 120)


@pytest.fixture
async def limited_pair(db_session: AsyncSession) -> dict[str, Any]:
    """A 50-day pair — ``limited`` (>= 44, < 100)."""
    return await _seed_pair(db_session, 50)
