"""End-to-end integration test for Phase 2 features.

Closes the PRP-3.1 umbrella: proves that lifecycle + replenishment +
promotion configs compose cleanly through the HTTP boundary against a
real Postgres, and that the additive contract holds at that boundary.

Requires ``docker-compose`` Postgres+pgvector and ``alembic upgrade head``.
"""

from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.features.data_platform.models import (
    Calendar,
    Product,
    Promotion,
    ReplenishmentEvent,
    SalesDaily,
    Store,
)
from app.main import app

# --- Additive-contract snapshot.
#
# Pinned via the schema-layer twin in
# ``test_schemas.py::test_config_hash_unchanged_when_phase2_omitted``
# (PRP-3.1A §15 Decision E). The HTTP response surfaces
# ``FeatureSetConfig.config_hash()`` verbatim, so the two snapshots MUST
# agree by construction; divergence here would mean ``routes.py``
# introduced a serialization drift between the model hash and the
# response field.
#
# If this constant ever needs to change, update BOTH snapshots in the
# same PR and call out the intentional contract bump in the description.
ADDITIVE_CONTRACT_BASELINE_HASH: str = "6c12b1a783eccdd4"


# --- Phase 2 columns expected end-to-end through ``POST /featuresets/compute``.
#
# Replenishment + promotion columns appear because:
#   * ``compute_features_for_series`` (service.py) eagerly loads
#     replenishment events via ``FeatureDataLoader.load_replenishment_events``.
#   * ``_compute_promotion_features`` falls back to an empty DataFrame when
#     no rows are wired through, and still EMITS its columns (with 0 /
#     NaN values) -- so the column membership assertion holds.
#
# Lifecycle columns (``days_since_launch_lag1`` / ``_discontinue_lag1``) are
# OMITTED from the expected set because the ``FeatureDataLoader`` does not
# join ``product.launch_date`` / ``product.discontinue_date`` onto the
# sales frame; per ``service.py::_compute_lifecycle_features`` (silent
# skip when both source columns are absent), no lifecycle columns reach
# ``feature_columns`` at the HTTP boundary. Extending the loader to plumb
# product attrs is OUT OF SCOPE for this slice (PRP-3.1E ships docs +
# tests only; see PRP-3.1E §16 Open Question 2).
PHASE2_EXPECTED_COLUMNS: set[str] = {
    "days_since_last_replenishment_lag1",
    "replenishment_count_w14_lag1",
    "promo_markdown_active_lag1",
    "promo_markdown_intensity_lag1",
}


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Real async Postgres session with FK-aware cleanup after each test."""
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
            with suppress(Exception):
                await session.rollback()

    # Fresh session for FK-aware cleanup (mirrors
    # ``app/features/ingest/tests/test_routes.py:46-61`` to avoid
    # transaction-state issues from a partially-rolled-back session).
    async with async_session_maker() as cleanup:
        with suppress(Exception):
            await cleanup.execute(
                delete(ReplenishmentEvent).where(
                    ReplenishmentEvent.date.between(date(2024, 1, 1), date(2024, 12, 31))
                )
            )
            await cleanup.execute(delete(Promotion).where(Promotion.start_date >= date(2024, 1, 1)))
            await cleanup.execute(
                delete(SalesDaily).where(
                    SalesDaily.date.between(date(2024, 1, 1), date(2024, 12, 31))
                )
            )
            await cleanup.execute(delete(Product).where(Product.sku.like("P31E-%")))
            await cleanup.execute(delete(Store).where(Store.code.like("P31E-%")))
            await cleanup.execute(
                delete(Calendar).where(Calendar.date.between(date(2024, 1, 1), date(2024, 12, 31)))
            )
            await cleanup.commit()

    await engine.dispose()


@pytest.fixture
async def seed_data(db_session: AsyncSession) -> dict[str, int]:
    """Seed a minimal Phase 2-shaped dataset.

    One store, one product (with launch + discontinue dates set), 60 days
    of sales, three replenishment events, one markdown promotion. Returns
    the resolved ``store_id`` / ``product_id`` so the test request body
    points at real rows (the test DB may already have stale rows from a
    prior ``docker compose`` run with different primary keys).
    """
    # Calendar -- SalesDaily.date is FK to calendar.date, so we must seed
    # every day used by sales rows.
    calendars: list[Calendar] = []
    for i in range(60):
        d = date(2024, 1, 1) + timedelta(days=i)
        calendars.append(
            Calendar(
                date=d,
                day_of_week=d.weekday(),
                month=d.month,
                quarter=((d.month - 1) // 3) + 1,
                year=d.year,
                is_holiday=False,
            )
        )
    db_session.add_all(calendars)

    store = Store(
        code="P31E-S1",
        name="P31E Store 1",
        region="North",
        city="City P31E",
        store_type="supermarket",
    )
    db_session.add(store)
    await db_session.flush()  # populate store.id

    product = Product(
        sku="P31E-SKU-1",
        name="P31E Product 1",
        category="Cat A",
        brand="Brand A",
        base_price=Decimal("19.99"),
        base_cost=Decimal("10.00"),
        launch_date=date(2023, 6, 1),
        discontinue_date=None,
    )
    db_session.add(product)
    await db_session.flush()

    # 60 days of sales (sequential quantities for any leakage detection).
    sales = [
        SalesDaily(
            store_id=store.id,
            product_id=product.id,
            date=date(2024, 1, 1) + timedelta(days=i),
            quantity=i + 1,
            unit_price=Decimal("19.99"),
            total_amount=Decimal(str((i + 1) * 19.99)),
        )
        for i in range(60)
    ]
    db_session.add_all(sales)

    # Three replenishment events.
    db_session.add_all(
        [
            ReplenishmentEvent(
                store_id=store.id,
                product_id=product.id,
                date=d,
                lead_time_days=7,
                ordered_qty=100,
                received_qty=98,
            )
            for d in (date(2024, 1, 5), date(2024, 1, 19), date(2024, 2, 9))
        ]
    )

    # One markdown campaign mid-window.
    db_session.add(
        Promotion(
            product_id=product.id,
            store_id=store.id,
            name="P31E markdown",
            kind="markdown",
            discount_pct=Decimal("0.2000"),
            start_date=date(2024, 1, 20),
            end_date=date(2024, 2, 5),
        )
    )

    await db_session.commit()
    return {"store_id": store.id, "product_id": product.id}


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """ASGITransport client with the shared ``db_session`` override."""
    from app.core.database import get_db

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.integration
class TestPhase2EndToEnd:
    """Integration tests for Phase 2 features at the HTTP boundary."""

    @pytest.mark.asyncio
    async def test_phase2_columns_appear(
        self, client: AsyncClient, seed_data: dict[str, int]
    ) -> None:
        """All wired Phase 2 columns appear when all configs are set.

        Lifecycle columns are not in the expected set; see the module
        docstring on ``PHASE2_EXPECTED_COLUMNS`` for why.
        """
        body = {
            "store_id": seed_data["store_id"],
            "product_id": seed_data["product_id"],
            "cutoff_date": "2024-02-29",
            "lookback_days": 60,
            "config": {
                "name": "phase2-smoke",
                "lifecycle_config": {
                    "include_days_since_launch": True,
                    "include_days_since_discontinue": True,
                    "lag_days": 1,
                },
                "replenishment_config": {
                    "include_days_since_last": True,
                    "include_count_window": True,
                    "lag_days": 1,
                    "count_window_days": 14,
                },
                "promotion_config": {
                    "kinds_to_track": ["markdown"],
                    "include_active": True,
                    "include_intensity": True,
                    "lag_days": 1,
                },
            },
        }
        response = await client.post("/featuresets/compute", json=body)
        assert response.status_code == 200, response.text
        data = response.json()

        cols = set(data["feature_columns"])
        missing = PHASE2_EXPECTED_COLUMNS - cols
        assert not missing, f"Phase 2 columns missing from response: {missing}"

    @pytest.mark.asyncio
    async def test_config_hash_deterministic(
        self, client: AsyncClient, seed_data: dict[str, int]
    ) -> None:
        """Two identical Phase 2 requests return identical ``config_hash``."""
        body = {
            "store_id": seed_data["store_id"],
            "product_id": seed_data["product_id"],
            "cutoff_date": "2024-02-29",
            "lookback_days": 60,
            "config": {
                "name": "phase2-det",
                "lifecycle_config": {"lag_days": 1},
                "replenishment_config": {"lag_days": 1},
                "promotion_config": {
                    "kinds_to_track": ["markdown"],
                    "lag_days": 1,
                },
            },
        }
        r1 = (await client.post("/featuresets/compute", json=body)).json()
        r2 = (await client.post("/featuresets/compute", json=body)).json()
        assert r1["config_hash"] == r2["config_hash"]

    @pytest.mark.asyncio
    async def test_additive_contract_snapshot(
        self, client: AsyncClient, seed_data: dict[str, int]
    ) -> None:
        """A request with NO Phase 2 sub-configs returns the baseline hash.

        Regression guard for PRD §6 / §11 R2 (additive contract). If this
        fails, a pre-PR caller's response shape changed -- STOP and
        root-cause before merging. The schema-layer twin lives in
        ``test_schemas.py::test_config_hash_unchanged_when_phase2_omitted``;
        the two MUST agree by construction.
        """
        body = {
            "store_id": seed_data["store_id"],
            "product_id": seed_data["product_id"],
            "cutoff_date": "2024-02-29",
            "lookback_days": 60,
            "config": {"name": "x"},
        }
        response = await client.post("/featuresets/compute", json=body)
        assert response.status_code == 200, response.text
        assert response.json()["config_hash"] == ADDITIVE_CONTRACT_BASELINE_HASH, (
            "Additive contract broken: a no-Phase-2 request's config_hash "
            "differs from the pre-PRP-3.1A baseline. See "
            "test_schemas.py::test_config_hash_unchanged_when_phase2_omitted."
        )
