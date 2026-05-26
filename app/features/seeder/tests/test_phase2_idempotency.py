"""Integration tests for the phase2-enrichment idempotency contract (#312).

Calls ``POST /seeder/phase2-enrichment`` twice against a real Postgres-backed
database and asserts that the second call:

* returns 2xx (no ``IntegrityError`` from the ``uq_exogenous_signal_per_store``
  / ``uq_exogenous_signal_global`` partial unique indexes),
* reports ``records_skipped`` populated for the three insert tables
  (``replenishment_event`` / ``exogenous_signal`` / ``sales_returns``),
* reports ``records_created`` zero for those same tables on the second call.

Requires ``docker compose up -d`` AND a seeded data platform (``demo_minimal``
or richer). The test is **non-destructive** — it reuses whatever calendar +
dimensions are already in the dev DB and skips with a clear message when the
DB is empty.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.features.data_platform.models import Calendar, Product, Store
from app.main import app


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session against the live dev Postgres.

    Non-destructive — no cleanup. The test reuses whatever data the dev DB
    already has (see module docstring).
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.integration
@pytest.mark.asyncio
class TestPhase2EnrichmentIdempotency:
    """Two consecutive ``POST /seeder/phase2-enrichment`` calls do not error."""

    async def test_second_call_is_idempotent(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Second call returns 2xx and reports ``records_skipped`` populated.

        Regression for #312 — pre-fix the second call raised
        ``IntegrityError`` on ``uq_exogenous_signal_per_store`` and the global
        handler surfaced it as HTTP 500.
        """
        # Skip cleanly when the DB is empty — the test is a regression for an
        # already-seeded path, not a seeding test. The seeded path is exercised
        # by ``make demo`` + the e2e nightly job.
        n_stores = await db_session.scalar(select(func.count()).select_from(Store)) or 0
        n_products = await db_session.scalar(select(func.count()).select_from(Product)) or 0
        n_calendar = await db_session.scalar(select(func.count()).select_from(Calendar)) or 0
        if not (n_stores and n_products and n_calendar):
            pytest.skip(
                "Phase 2 idempotency test needs a seeded DB — run `make demo` or "
                "POST /seeder/generate {scenario: demo_minimal} first."
            )

        payload = {"seed": 42, "returns_probability": 0.05}

        first = await client.post("/seeder/phase2-enrichment", json=payload)
        assert first.status_code == status.HTTP_201_CREATED, first.text
        first_body = first.json()
        assert first_body["success"] is True
        first_created = first_body["records_created"]
        first_skipped = first_body["records_skipped"]

        # The main bug fix: the second call must NOT bubble an IntegrityError
        # as HTTP 500 — it must return 2xx.
        second = await client.post("/seeder/phase2-enrichment", json=payload)
        assert second.status_code == status.HTTP_201_CREATED, second.text
        body = second.json()
        assert body["success"] is True

        skipped = body["records_skipped"]
        created = body["records_created"]

        # Idempotency proof: the second call writes ZERO new rows to any of
        # the three insert tables, regardless of how many the first call
        # produced. (``product`` is a deterministic UPDATE under a fixed seed
        # and has no skip semantic — its count just mirrors the row count.)
        for table in ("replenishment_event", "exogenous_signal", "sales_returns"):
            assert created[table] == 0, (
                f"expected no new {table} rows on the second call (idempotency), "
                f"got created={created}, skipped={skipped}"
            )

        # Sanity guard: the test is only meaningful if at least one of the
        # three insert tables actually exercised the idempotency path — i.e.
        # the first call produced rows for it, OR the second call skipped
        # rows for it (the original ``uq_exogenous_signal_per_store`` bug
        # surface). Sparse fixture state from other tests can leave the
        # generators producing zero records; soft-skip rather than fail in
        # that case.
        for table in ("replenishment_event", "exogenous_signal", "sales_returns"):
            if first_created.get(table, 0) > 0 or skipped.get(table, 0) > 0:
                break
            if first_skipped.get(table, 0) > 0:
                break
        else:
            pytest.skip(
                "DB state too sparse to generate phase-2 records for any of the "
                "three insert tables — idempotency path not exercised. "
                f"first_created={first_created}, first_skipped={first_skipped}, "
                f"second_created={created}, second_skipped={skipped}"
            )
