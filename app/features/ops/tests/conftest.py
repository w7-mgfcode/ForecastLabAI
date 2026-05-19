"""Test fixtures for the ops slice.

Mirrors ``app/features/analytics/tests/conftest.py``: a real PostgreSQL session
(integration tests need ``docker-compose up -d``) with FK-safe, scoped cleanup.

All seeded rows carry a ``test-`` / ``TEST-`` marker so the teardown never
touches a shared dev or CI dataset.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.features.data_platform.models import Calendar, Product, SalesDaily, Store
from app.features.jobs.models import Job, JobStatus, JobType
from app.features.registry.models import DeploymentAlias, ModelRun, RunStatus
from app.main import app

# Calendar dates the ops sales fixture occupies — deleted on teardown.
_SALES_DATES = [date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)]


def _short_id() -> str:
    """Return a short unique hex token for test natural keys."""
    return uuid.uuid4().hex[:12]


# =============================================================================
# Database + client fixtures
# =============================================================================


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session, then clean up every ``test-``/``TEST-`` row.

    Cleanup runs in FK-safe order: DeploymentAlias before ModelRun (alias FKs
    the run), and Sales before its Store/Product parents. Jobs are independent.
    Calendar rows are intentionally left in place — the sales fixture's dates
    fall inside the seeder's window, so a seeded dataset may already reference
    them; deleting them would hit a foreign-key violation.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        try:
            yield session
        finally:
            test_store_ids = select(Store.id).where(Store.code.like("TEST-%"))
            test_product_ids = select(Product.id).where(Product.sku.like("TEST-%"))
            # Aliases first — they FK-reference model_run.
            await session.execute(
                delete(DeploymentAlias).where(DeploymentAlias.alias_name.like("test-%"))
            )
            await session.execute(delete(ModelRun).where(ModelRun.run_id.like("test-%")))
            await session.execute(delete(Job).where(Job.job_id.like("test-%")))
            await session.execute(
                delete(SalesDaily).where(
                    SalesDaily.store_id.in_(test_store_ids)
                    | SalesDaily.product_id.in_(test_product_ids)
                )
            )
            await session.execute(delete(Product).where(Product.sku.like("TEST-%")))
            await session.execute(delete(Store).where(Store.code.like("TEST-%")))
            await session.commit()

    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with the database dependency overridden."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.pop(get_db, None)


# =============================================================================
# Sample-data fixtures
# =============================================================================


@pytest.fixture
async def sample_jobs(db_session: AsyncSession) -> list[Job]:
    """Create one job per lifecycle status; the failed job carries an error."""
    jobs = [
        Job(
            job_id=f"test-{_short_id()}",
            job_type=JobType.TRAIN.value,
            status=JobStatus.PENDING.value,
            params={"_test": True},
        ),
        Job(
            job_id=f"test-{_short_id()}",
            job_type=JobType.PREDICT.value,
            status=JobStatus.RUNNING.value,
            params={"_test": True},
        ),
        Job(
            job_id=f"test-{_short_id()}",
            job_type=JobType.BACKTEST.value,
            status=JobStatus.COMPLETED.value,
            params={"_test": True},
            result={"ok": True},
        ),
        Job(
            job_id=f"test-{_short_id()}",
            job_type=JobType.TRAIN.value,
            status=JobStatus.FAILED.value,
            params={"_test": True},
            error_message="seeded failure",
            error_type="ValueError",
        ),
    ]
    for job in jobs:
        db_session.add(job)
    await db_session.commit()
    for job in jobs:
        await db_session.refresh(job)
    return jobs


@pytest.fixture
async def sample_runs(db_session: AsyncSession) -> dict[str, ModelRun]:
    """Create model runs across grains and statuses.

    ``success_old`` and ``success_new`` share grain (9001, 8001) so an alias to
    ``success_old`` is provably stale (a newer successful run exists).
    """

    def _run(
        status: str,
        store_id: int,
        product_id: int,
        window_end: date,
        metrics: dict[str, float] | None,
        error_message: str | None = None,
    ) -> ModelRun:
        return ModelRun(
            run_id=f"test-{_short_id()}",
            status=status,
            model_type="naive",
            model_config={"_test": True},
            config_hash=_short_id()[:16],
            data_window_start=date(2025, 1, 1),
            data_window_end=window_end,
            store_id=store_id,
            product_id=product_id,
            metrics=metrics,
            error_message=error_message,
        )

    runs = {
        "success_old": _run(RunStatus.SUCCESS.value, 9001, 8001, date(2026, 1, 1), {"wape": 31.0}),
        "failed": _run(
            RunStatus.FAILED.value,
            9002,
            8002,
            date(2026, 2, 1),
            None,
            error_message="seeded run failure",
        ),
        "success_other": _run(RunStatus.SUCCESS.value, 9003, 8003, date(2026, 2, 15), None),
    }
    for run in runs.values():
        db_session.add(run)
    await db_session.commit()
    for run in runs.values():
        await db_session.refresh(run)

    # success_new is committed after success_old so its created_at is strictly
    # later — making success_old the stale one for grain (9001, 8001).
    success_new = _run(RunStatus.SUCCESS.value, 9001, 8001, date(2026, 4, 1), {"wape": 12.0})
    db_session.add(success_new)
    await db_session.commit()
    await db_session.refresh(success_new)
    runs["success_new"] = success_new
    return runs


@pytest.fixture
async def sample_alias(
    db_session: AsyncSession, sample_runs: dict[str, ModelRun]
) -> DeploymentAlias:
    """Alias pointing at the OLDER successful run — provably stale."""
    alias = DeploymentAlias(
        alias_name=f"test-{_short_id()}",
        run_id=sample_runs["success_old"].id,
        description="ops slice test alias",
    )
    db_session.add(alias)
    await db_session.commit()
    await db_session.refresh(alias)
    return alias


@pytest.fixture
async def sample_sales(db_session: AsyncSession) -> list[SalesDaily]:
    """Create a TEST- store/product, calendar rows, and a few sales days."""
    store = Store(
        code=f"TEST-{_short_id()}",
        name="Ops Test Store",
        region="Test Region",
        city="Test City",
        store_type="supermarket",
    )
    product = Product(
        sku=f"TEST-{_short_id()}",
        name="Ops Test Product",
        category="Test Category",
        brand="Test Brand",
        base_price=10,
        base_cost=5,
    )
    db_session.add_all([store, product])
    await db_session.commit()
    await db_session.refresh(store)
    await db_session.refresh(product)

    for day in _SALES_DATES:
        await db_session.merge(
            Calendar(
                date=day,
                day_of_week=day.weekday(),
                month=day.month,
                quarter=(day.month - 1) // 3 + 1,
                year=day.year,
                is_holiday=False,
            )
        )
    await db_session.commit()

    sales = [
        SalesDaily(
            date=day,
            store_id=store.id,
            product_id=product.id,
            quantity=5,
            unit_price=10,
            total_amount=50,
        )
        for day in _SALES_DATES
    ]
    for row in sales:
        db_session.add(row)
    await db_session.commit()
    for row in sales:
        await db_session.refresh(row)
    return sales
