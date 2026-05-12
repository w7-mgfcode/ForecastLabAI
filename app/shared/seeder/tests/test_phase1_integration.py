"""Phase 1 integration tests against real Postgres.

Run with: uv run pytest app/shared/seeder/tests/test_phase1_integration.py -v -m integration
Requires docker-compose Postgres up and migrations applied.
"""

# mypy: disable-error-code="union-attr,arg-type,operator,return-value"

import os
from collections.abc import AsyncGenerator
from contextlib import suppress
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.features.data_platform.models import (
    Calendar,
    ExogenousSignal,
    InventorySnapshotDaily,
    PriceHistory,
    Product,
    Promotion,
    SalesDaily,
    SalesReturn,
    Store,
)
from app.features.seeder import schemas, service
from app.shared.seeder import DataSeeder, SeederConfig
from app.shared.seeder.config import (
    ChangepointConfig,
    ChangepointEvent,
    DimensionConfig,
    ExogenousSignalConfig,
    MultiSeasonalityConfig,
    ReturnsConfig,
)

pytestmark = pytest.mark.integration


def _check_destructive_test_guard() -> None:
    settings = get_settings()
    is_testing = getattr(settings, "testing", False)
    app_env_testing = os.environ.get("APP_ENV", "").lower() == "testing"
    allow_destructive = os.environ.get("ALLOW_DESTRUCTIVE_TEST_DB", "").lower() == "true"
    if not is_testing and not app_env_testing and not allow_destructive:
        raise RuntimeError(
            "Destructive test operations require explicit opt-in. "
            "Set ALLOW_DESTRUCTIVE_TEST_DB=true, APP_ENV=testing, or settings.testing=True"
        )


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    _check_destructive_test_guard()
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as cleanup_session:
        try:
            await cleanup_session.execute(delete(SalesReturn))
            await cleanup_session.execute(delete(ExogenousSignal))
            await cleanup_session.execute(delete(SalesDaily))
            await cleanup_session.execute(delete(InventorySnapshotDaily))
            await cleanup_session.execute(delete(PriceHistory))
            await cleanup_session.execute(delete(Promotion))
            await cleanup_session.execute(delete(Calendar))
            await cleanup_session.execute(delete(Product))
            await cleanup_session.execute(delete(Store))
            await cleanup_session.commit()
        except Exception:
            await cleanup_session.rollback()

    async with session_maker() as session:
        try:
            yield session
        finally:
            with suppress(Exception):
                await session.rollback()

    _check_destructive_test_guard()

    async with session_maker() as cleanup_session:
        try:
            await cleanup_session.execute(delete(SalesReturn))
            await cleanup_session.execute(delete(ExogenousSignal))
            await cleanup_session.execute(delete(SalesDaily))
            await cleanup_session.execute(delete(InventorySnapshotDaily))
            await cleanup_session.execute(delete(PriceHistory))
            await cleanup_session.execute(delete(Promotion))
            await cleanup_session.execute(delete(Calendar))
            await cleanup_session.execute(delete(Product))
            await cleanup_session.execute(delete(Store))
            await cleanup_session.commit()
        except Exception:
            await cleanup_session.rollback()

    await engine.dispose()


class TestPhase1Disabled:
    @pytest.mark.asyncio
    async def test_default_run_creates_no_phase1_rows(self, db_session: AsyncSession) -> None:
        """With Phase 1 fully off, exogenous_signal and sales_returns stay empty."""
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),
            dimensions=DimensionConfig(stores=2, products=3),
        )
        result = await DataSeeder(config).generate_full(db_session)
        assert result.exogenous_count == 0
        assert result.returns_count == 0

        exo_count = (
            await db_session.execute(select(func.count()).select_from(ExogenousSignal))
        ).scalar() or 0
        ret_count = (
            await db_session.execute(select(func.count()).select_from(SalesReturn))
        ).scalar() or 0
        assert exo_count == 0
        assert ret_count == 0


class TestPhase1Enabled:
    @pytest.mark.asyncio
    async def test_exogenous_weather_and_macro_persisted(self, db_session: AsyncSession) -> None:
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),  # 7 days
            dimensions=DimensionConfig(stores=2, products=2),
            exogenous=ExogenousSignalConfig(
                enable_weather=True,
                enable_macro=True,
            ),
        )
        result = await DataSeeder(config).generate_full(db_session)
        # 2 stores x 7 dates weather + 7 dates macro = 21 rows.
        assert result.exogenous_count == 21

        weather_rows = (
            await db_session.execute(
                select(func.count())
                .select_from(ExogenousSignal)
                .where(ExogenousSignal.signal_name == "weather_temp_c")
            )
        ).scalar() or 0
        macro_rows = (
            await db_session.execute(
                select(func.count())
                .select_from(ExogenousSignal)
                .where(ExogenousSignal.signal_name == "macro_index")
            )
        ).scalar() or 0
        assert weather_rows == 14
        assert macro_rows == 7

    @pytest.mark.asyncio
    async def test_returns_table_populated(self, db_session: AsyncSession) -> None:
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            dimensions=DimensionConfig(stores=2, products=3),
            returns=ReturnsConfig(enable=True, return_probability=0.2),
        )
        result = await DataSeeder(config).generate_full(db_session)
        assert result.returns_count > 0
        # Quantity invariant
        bad = (
            await db_session.execute(
                select(func.count()).select_from(SalesReturn).where(SalesReturn.return_quantity < 1)
            )
        ).scalar() or 0
        assert bad == 0

    @pytest.mark.asyncio
    async def test_changepoint_lifts_demand_at_date(self, db_session: AsyncSession) -> None:
        """A 5x changepoint on day 0 with no decay should produce strictly
        higher total demand than the baseline run."""
        # Baseline (no changepoint).
        base_config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 14),
            dimensions=DimensionConfig(stores=2, products=2),
        )
        await DataSeeder(base_config).generate_full(db_session)
        baseline_total = (
            await db_session.execute(
                select(func.sum(SalesDaily.quantity)).where(SalesDaily.date == date(2024, 1, 1))
            )
        ).scalar() or 0

        # Reset and re-run with a changepoint.
        await db_session.execute(delete(SalesReturn))
        await db_session.execute(delete(ExogenousSignal))
        await db_session.execute(delete(SalesDaily))
        await db_session.execute(delete(InventorySnapshotDaily))
        await db_session.execute(delete(PriceHistory))
        await db_session.execute(delete(Promotion))
        await db_session.execute(delete(Calendar))
        await db_session.execute(delete(Product))
        await db_session.execute(delete(Store))
        await db_session.commit()

        cp_config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 14),
            dimensions=DimensionConfig(stores=2, products=2),
            changepoints=ChangepointConfig(
                changepoints=[
                    ChangepointEvent(
                        date=date(2024, 1, 1),
                        demand_multiplier=5.0,
                        decay_days=0,
                    )
                ]
            ),
        )
        await DataSeeder(cp_config).generate_full(db_session)
        cp_total = (
            await db_session.execute(
                select(func.sum(SalesDaily.quantity)).where(SalesDaily.date == date(2024, 1, 1))
            )
        ).scalar() or 0
        assert cp_total > baseline_total * 2  # well above the 5x lift floor

    @pytest.mark.asyncio
    async def test_verify_integrity_clean_with_phase1(self, db_session: AsyncSession) -> None:
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),
            dimensions=DimensionConfig(stores=2, products=2),
            exogenous=ExogenousSignalConfig(enable_weather=True),
            returns=ReturnsConfig(enable=True, return_probability=0.5),
            multi_seasonality=MultiSeasonalityConfig(yearly_seasonality_amplitude=0.1),
        )
        seeder = DataSeeder(config)
        await seeder.generate_full(db_session)
        errors = await seeder.verify_data_integrity(db_session)
        assert errors == []


class TestQueryExogenousService:
    @pytest.mark.asyncio
    async def test_query_returns_persisted_weather(self, db_session: AsyncSession) -> None:
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),
            dimensions=DimensionConfig(stores=2, products=2),
            exogenous=ExogenousSignalConfig(enable_weather=True),
        )
        await DataSeeder(config).generate_full(db_session)

        # Need to commit DataSeeder's writes? DataSeeder.generate_full already
        # commits. The fixture's expire_on_commit=False keeps objects valid.

        resp = await service.query_exogenous(
            db_session,
            signal_name="weather_temp_c",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
            store_id=None,
        )
        assert isinstance(resp, schemas.ExogenousSignalResponse)
        # 2 stores x 2 dates = 4 weather rows in this window.
        assert resp.total == 4
        for r in resp.records:
            assert r.signal_name == "weather_temp_c"
            assert r.is_global is False

    @pytest.mark.asyncio
    async def test_query_filter_by_store(self, db_session: AsyncSession) -> None:
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            dimensions=DimensionConfig(stores=3, products=2),
            exogenous=ExogenousSignalConfig(enable_weather=True, enable_macro=True),
        )
        await DataSeeder(config).generate_full(db_session)

        # Pick the first store id present.
        store_id_row = (await db_session.execute(select(Store.id).limit(1))).scalar()
        assert store_id_row is not None

        resp = await service.query_exogenous(
            db_session,
            signal_name="weather_temp_c",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            store_id=store_id_row,
        )
        # Only the rows for this store_id over 3 dates.
        assert resp.total == 3
        for r in resp.records:
            assert r.store_id == store_id_row

    @pytest.mark.asyncio
    async def test_query_empty_signal_returns_no_rows(self, db_session: AsyncSession) -> None:
        # No data seeded → query should return empty list, not error.
        # First seed something to make sure tables exist with FK targets,
        # then query a signal we never emitted.
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            dimensions=DimensionConfig(stores=1, products=1),
        )
        await DataSeeder(config).generate_full(db_session)

        resp = await service.query_exogenous(
            db_session,
            signal_name="weather_temp_c",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            store_id=None,
        )
        assert resp.total == 0
        assert resp.records == []


# Suppress unused-import warning for timedelta — kept for future use.
_ = timedelta
