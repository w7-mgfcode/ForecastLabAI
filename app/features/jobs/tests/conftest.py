"""Test fixtures for jobs module."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.features.jobs.models import Job, JobStatus, JobType
from app.features.jobs.schemas import (
    JobCreate,
    JobResponse,
)
from app.main import app

# =============================================================================
# Database Fixtures for Integration Tests
# =============================================================================


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for integration tests.

    Provides a session and cleans up test data (jobs whose job_id starts
    with "test"). Requires PostgreSQL to be running (docker-compose up -d).
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
            # Job has no model_type column for a cleanup key — key on the
            # "test" job_id prefix every fixture/test uses.
            await session.execute(delete(Job).where(Job.job_id.like("test%")))
            await session.commit()

    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database dependency override."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    # Remove only this fixture's override — clear() would also drop overrides
    # installed by other fixtures sharing the app instance.
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def sample_jobs_multi(db_session: AsyncSession) -> list[Job]:
    """Insert three jobs with distinct job_type / status / created_at.

    Drives the list-endpoint sort tests. Every job_id starts with "test"
    so the db_session cleanup removes them. created_at is set explicitly
    (overriding the server_default) so created_at sorting is deterministic.
    """
    jobs = [
        Job(
            job_id=f"test{uuid.uuid4().hex[:28]}",
            job_type=JobType.TRAIN.value,
            status=JobStatus.PENDING.value,
            params={},
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        Job(
            job_id=f"test{uuid.uuid4().hex[:28]}",
            job_type=JobType.PREDICT.value,
            status=JobStatus.RUNNING.value,
            params={},
            created_at=datetime(2024, 1, 2, tzinfo=UTC),
        ),
        Job(
            job_id=f"test{uuid.uuid4().hex[:28]}",
            job_type=JobType.BACKTEST.value,
            status=JobStatus.COMPLETED.value,
            params={},
            created_at=datetime(2024, 1, 3, tzinfo=UTC),
        ),
    ]
    db_session.add_all(jobs)
    await db_session.commit()
    for job in jobs:
        await db_session.refresh(job)
    return jobs


# =============================================================================
# Unit Test Fixtures
# =============================================================================


@pytest.fixture
def sample_train_job_create() -> JobCreate:
    """Create sample train job request."""
    return JobCreate(
        job_type=JobType.TRAIN,
        params={
            "model_type": "naive",
            "store_id": 1,
            "product_id": 1,
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
        },
    )


@pytest.fixture
def sample_predict_job_create() -> JobCreate:
    """Create sample predict job request."""
    return JobCreate(
        job_type=JobType.PREDICT,
        params={
            "run_id": "abc123def4567890123456789012abcd",
            "horizon": 14,
        },
    )


@pytest.fixture
def sample_backtest_job_create() -> JobCreate:
    """Create sample backtest job request."""
    return JobCreate(
        job_type=JobType.BACKTEST,
        params={
            "model_type": "naive",
            "store_id": 1,
            "product_id": 1,
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
            "n_splits": 5,
            "test_size": 14,
        },
    )


@pytest.fixture
def sample_job_response() -> JobResponse:
    """Create sample job response."""
    now = datetime.now(UTC)
    return JobResponse(
        job_id="abc123def4567890123456789012abcd",
        job_type=JobType.TRAIN,
        status=JobStatus.COMPLETED,
        params={
            "model_type": "naive",
            "store_id": 1,
            "product_id": 1,
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
        },
        result={
            "run_id": "xyz789abc123def4567890123456abcd",
            "model_type": "naive",
            "training_samples": 180,
            "training_time_ms": 50.5,
        },
        error_message=None,
        error_type=None,
        run_id="xyz789abc123def4567890123456abcd",
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )
