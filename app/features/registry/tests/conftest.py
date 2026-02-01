"""Test fixtures for registry module."""

import tempfile
import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import date
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.features.registry.models import DeploymentAlias, ModelRun
from app.features.registry.schemas import AgentContext, RunCreate, RunStatus
from app.features.registry.storage import LocalFSProvider
from app.main import app

# =============================================================================
# Database Fixtures for Integration Tests
# =============================================================================


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for integration tests.

    Creates tables if needed, provides a session, and cleans up test data.
    Requires PostgreSQL to be running (docker-compose up -d).
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    # Create session
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        try:
            yield session
        finally:
            # Clean up test data (delete in correct order due to FK constraints)
            await session.execute(delete(DeploymentAlias))
            await session.execute(delete(ModelRun).where(ModelRun.model_type.like("test-%")))
            await session.commit()

    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database dependency override."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# =============================================================================
# Unit Test Fixtures
# =============================================================================


@pytest.fixture
def sample_run_create() -> RunCreate:
    """Create a sample RunCreate for testing."""
    return RunCreate(
        model_type="test-naive",
        model_config_data={"strategy": "last_value"},
        feature_config={"lags": [1, 7]},
        data_window_start=date(2024, 1, 1),
        data_window_end=date(2024, 3, 31),
        store_id=1,
        product_id=1,
        agent_context=AgentContext(agent_id="test-agent", session_id="test-session"),
        git_sha="abc1234567890",
    )


@pytest.fixture
def sample_run_create_minimal() -> RunCreate:
    """Create a minimal RunCreate for testing."""
    return RunCreate(
        model_type="test-minimal",
        model_config_data={"type": "baseline"},
        data_window_start=date(2024, 1, 1),
        data_window_end=date(2024, 1, 31),
        store_id=1,
        product_id=1,
    )


@pytest.fixture
def sample_run_create_duplicate(sample_run_create: RunCreate) -> RunCreate:
    """Create a duplicate RunCreate (same config hash and data window)."""
    return RunCreate(
        model_type=sample_run_create.model_type,
        model_config_data=sample_run_create.model_config_data,
        data_window_start=sample_run_create.data_window_start,
        data_window_end=sample_run_create.data_window_end,
        store_id=sample_run_create.store_id,
        product_id=sample_run_create.product_id,
    )


@pytest.fixture
def sample_model_run() -> ModelRun:
    """Create a sample ModelRun ORM object for testing."""
    return ModelRun(
        run_id=uuid.uuid4().hex,
        status=RunStatus.PENDING.value,
        model_type="test-naive",
        model_config={"strategy": "last_value"},
        feature_config={"lags": [1, 7]},
        config_hash="abc123def456",
        data_window_start=date(2024, 1, 1),
        data_window_end=date(2024, 3, 31),
        store_id=1,
        product_id=1,
    )


@pytest.fixture
def temp_artifact_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for artifact storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def storage_provider(temp_artifact_dir: Path) -> LocalFSProvider:
    """Create a LocalFSProvider with temporary root directory."""
    return LocalFSProvider(root_dir=temp_artifact_dir)


@pytest.fixture
def sample_artifact_content() -> bytes:
    """Create sample artifact content for testing."""
    return b"test artifact content for sha256 verification"


@pytest.fixture
def sample_artifact_file(temp_artifact_dir: Path, sample_artifact_content: bytes) -> Path:
    """Create a sample artifact file for testing."""
    artifact_path = temp_artifact_dir / "source_artifact.pkl"
    artifact_path.write_bytes(sample_artifact_content)
    return artifact_path


# =============================================================================
# Status Transition Test Fixtures
# =============================================================================


@pytest.fixture
def sample_pending_run() -> ModelRun:
    """Create a pending model run."""
    return ModelRun(
        run_id=uuid.uuid4().hex,
        status=RunStatus.PENDING.value,
        model_type="test-status",
        model_config={"test": True},
        config_hash="status12345678",
        data_window_start=date(2024, 1, 1),
        data_window_end=date(2024, 1, 31),
        store_id=1,
        product_id=1,
    )


@pytest.fixture
def sample_running_run() -> ModelRun:
    """Create a running model run."""
    return ModelRun(
        run_id=uuid.uuid4().hex,
        status=RunStatus.RUNNING.value,
        model_type="test-status",
        model_config={"test": True},
        config_hash="status12345678",
        data_window_start=date(2024, 1, 1),
        data_window_end=date(2024, 1, 31),
        store_id=1,
        product_id=1,
    )


@pytest.fixture
def sample_success_run() -> ModelRun:
    """Create a successful model run."""
    return ModelRun(
        run_id=uuid.uuid4().hex,
        status=RunStatus.SUCCESS.value,
        model_type="test-status",
        model_config={"test": True},
        config_hash="status12345678",
        data_window_start=date(2024, 1, 1),
        data_window_end=date(2024, 1, 31),
        store_id=1,
        product_id=1,
        metrics={"mae": 1.5, "smape": 10.2},
        artifact_uri="models/test.pkl",
        artifact_hash="abc123",
    )


@pytest.fixture
def sample_failed_run() -> ModelRun:
    """Create a failed model run."""
    return ModelRun(
        run_id=uuid.uuid4().hex,
        status=RunStatus.FAILED.value,
        model_type="test-status",
        model_config={"test": True},
        config_hash="status12345678",
        data_window_start=date(2024, 1, 1),
        data_window_end=date(2024, 1, 31),
        store_id=1,
        product_id=1,
        error_message="Training failed due to insufficient data",
    )
