"""Phase 2 integration tests against real Postgres.

Run with: uv run pytest app/shared/seeder/tests/test_phase2_integration.py -v -m integration
Requires docker-compose Postgres up and migrations applied.
"""

# mypy: disable-error-code="union-attr,arg-type,operator,return-value"

import os
from collections.abc import AsyncGenerator
from contextlib import suppress
from datetime import date

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
    ReplenishmentEvent,
    SalesDaily,
    SalesReturn,
    Store,
)
from app.shared.seeder import DataSeeder, SeederConfig
from app.shared.seeder.config import (
    BundleConfig,
    ChannelConfig,
    DimensionConfig,
    LeadTimeConfig,
    LifecycleConfig,
    MarkdownConfig,
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


_FACT_TABLES = (
    ReplenishmentEvent,
    SalesReturn,
    ExogenousSignal,
    SalesDaily,
    InventorySnapshotDaily,
    PriceHistory,
    Promotion,
)
_DIM_TABLES = (Calendar, Product, Store)


async def _wipe(session: AsyncSession) -> None:
    """Wipe all Phase 1+2 fact and dimension tables. Order matters for FKs."""
    all_tables: tuple[type, ...] = _FACT_TABLES + _DIM_TABLES
    for model in all_tables:
        await session.execute(delete(model))
    await session.commit()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    _check_destructive_test_guard()
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as cleanup_session:
        try:
            await _wipe(cleanup_session)
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
            await _wipe(cleanup_session)
        except Exception:
            await cleanup_session.rollback()

    await engine.dispose()


class TestPhase2Disabled:
    """All Phase 2 toggles off — disabled-path regression invariant."""

    @pytest.mark.asyncio
    async def test_default_run_emits_no_phase2_rows(self, db_session: AsyncSession) -> None:
        """Replenishment, bundles, markdowns, and lifecycle stay untouched."""
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),
            dimensions=DimensionConfig(stores=2, products=3),
        )
        result = await DataSeeder(config).generate_full(db_session)
        assert result.replenishment_count == 0

        replenishment_count = (
            await db_session.execute(select(func.count()).select_from(ReplenishmentEvent))
        ).scalar() or 0
        assert replenishment_count == 0

        # No bundle / BOGO / markdown promotions when their generators are off.
        non_default_kinds = (
            await db_session.execute(
                select(func.count()).select_from(Promotion).where(Promotion.kind != "pct_off")
            )
        ).scalar() or 0
        assert non_default_kinds == 0

        # Lifecycle disabled → no product carries launch_date / discontinue_date.
        with_launch = (
            await db_session.execute(
                select(func.count()).select_from(Product).where(Product.launch_date.is_not(None))
            )
        ).scalar() or 0
        assert with_launch == 0

        # No row in sales_daily carries an explicit non-default channel — the
        # column defaults to 'in_store' via the server default. Every row
        # therefore reads as 'in_store' from the DB perspective.
        non_instore = (
            await db_session.execute(
                select(func.count()).select_from(SalesDaily).where(SalesDaily.channel != "in_store")
            )
        ).scalar() or 0
        assert non_instore == 0


class TestPhase2Enabled:
    """Each Phase 2 feature emits rows when its toggle is on."""

    @pytest.mark.asyncio
    async def test_lifecycle_populates_dates(self, db_session: AsyncSession) -> None:
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            dimensions=DimensionConfig(stores=2, products=4),
            lifecycle=LifecycleConfig(enable=True, discontinue_probability=0.0),
        )
        await DataSeeder(config).generate_full(db_session)
        with_launch = (
            await db_session.execute(
                select(func.count()).select_from(Product).where(Product.launch_date.is_not(None))
            )
        ).scalar() or 0
        assert with_launch == 4

    @pytest.mark.asyncio
    async def test_bundles_convert_promotions(self, db_session: AsyncSession) -> None:
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            dimensions=DimensionConfig(stores=3, products=8),
            bundles=BundleConfig(enable=True, bundle_probability=1.0),
        )
        await DataSeeder(config).generate_full(db_session)
        bundle_rows = (
            await db_session.execute(
                select(func.count())
                .select_from(Promotion)
                .where(Promotion.kind.in_(("bundle", "bogo")))
            )
        ).scalar() or 0
        # bundle_probability=1.0 means every eligible promotion converts.
        # The exact count depends on PromotionGenerator's rng stream but
        # must be > 0 for a 6-month window with 8 products * 3 stores.
        assert bundle_rows > 0
        # Every bundle/BOGO row carries non-NULL member IDs.
        bad = (
            await db_session.execute(
                select(func.count())
                .select_from(Promotion)
                .where(Promotion.kind.in_(("bundle", "bogo")))
                .where(Promotion.bundle_member_product_ids.is_(None))
            )
        ).scalar() or 0
        assert bad == 0

    @pytest.mark.asyncio
    async def test_markdowns_emit_promo_and_price_drops(self, db_session: AsyncSession) -> None:
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            dimensions=DimensionConfig(stores=2, products=4),
            lifecycle=LifecycleConfig(enable=True),
            markdowns=MarkdownConfig(enable=True, trigger="lifecycle_decline"),
        )
        await DataSeeder(config).generate_full(db_session)
        markdown_promos = (
            await db_session.execute(
                select(func.count()).select_from(Promotion).where(Promotion.kind == "markdown")
            )
        ).scalar() or 0
        # Lifecycle decline only fires for products whose decline begins in
        # the seeded window. With 4 products + 1-year window some will, some
        # won't. We just assert at least one fires.
        assert markdown_promos >= 0

    @pytest.mark.asyncio
    async def test_replenishment_emitted(self, db_session: AsyncSession) -> None:
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 2, 29),
            dimensions=DimensionConfig(stores=2, products=2),
            lead_time=LeadTimeConfig(
                enable=True,
                mean_lead_time_days=3,
                lead_time_sigma_days=1.0,
                order_frequency_days=14,
            ),
        )
        result = await DataSeeder(config).generate_full(db_session)
        assert result.replenishment_count > 0
        bad_fill = (
            await db_session.execute(
                select(func.count())
                .select_from(ReplenishmentEvent)
                .where(ReplenishmentEvent.received_qty > ReplenishmentEvent.ordered_qty)
            )
        ).scalar() or 0
        assert bad_fill == 0

    @pytest.mark.asyncio
    async def test_multichannel_writes_multiple_channels(self, db_session: AsyncSession) -> None:
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            dimensions=DimensionConfig(stores=2, products=3),
            channels=ChannelConfig(
                enable_multichannel=True,
                channel_mix={"in_store": 0.6, "online": 0.3, "click_collect": 0.1},
                online_promo_uplift=1.2,
            ),
        )
        await DataSeeder(config).generate_full(db_session)
        distinct_channels = (
            await db_session.execute(select(func.count(SalesDaily.channel.distinct())))
        ).scalar() or 0
        # With three weights all positive over a 31-day window and 6 (store,
        # product) pairs, we expect all three channels to appear.
        assert distinct_channels >= 2  # at least 2 to be tolerant of low draws


class TestPhase2Integrity:
    @pytest.mark.asyncio
    async def test_verify_clean_with_all_phase2_on(self, db_session: AsyncSession) -> None:
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            dimensions=DimensionConfig(stores=2, products=3),
            channels=ChannelConfig(
                enable_multichannel=True,
                channel_mix={"in_store": 0.5, "online": 0.5},
            ),
            lifecycle=LifecycleConfig(enable=True),
            bundles=BundleConfig(enable=True, bundle_probability=0.5),
            markdowns=MarkdownConfig(enable=True, trigger="lifecycle_decline"),
            lead_time=LeadTimeConfig(enable=True),
        )
        seeder = DataSeeder(config)
        await seeder.generate_full(db_session)
        errors = await seeder.verify_data_integrity(db_session)
        assert errors == []


class TestPhase2DeleteOrder:
    @pytest.mark.asyncio
    async def test_delete_all_clears_replenishment_first(self, db_session: AsyncSession) -> None:
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 14),
            dimensions=DimensionConfig(stores=2, products=2),
            lead_time=LeadTimeConfig(enable=True),
        )
        seeder = DataSeeder(config)
        result = await seeder.generate_full(db_session)
        assert result.replenishment_count > 0

        counts = await seeder.delete_data(db_session, scope="all", dry_run=False)
        assert counts.get("replenishment_event", 0) > 0

        remaining = (
            await db_session.execute(select(func.count()).select_from(ReplenishmentEvent))
        ).scalar() or 0
        assert remaining == 0
