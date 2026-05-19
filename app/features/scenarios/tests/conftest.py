"""Test fixtures for the scenarios slice.

Integration tests run against a real PostgreSQL database (``docker compose up
-d`` required). The ``trained_model`` fixture writes a real model bundle into
the configured artifacts directory so ``POST /scenarios/simulate`` can resolve
it, exactly as a completed predict job would.

``scenario_plan`` is a slice-private table — no seeder or demo writes it — so
the teardown safely wipes it whole rather than relying on a row marker.
"""

import uuid
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.features.forecasting.models import NaiveForecaster
from app.features.forecasting.persistence import ModelBundle, save_model_bundle
from app.features.forecasting.schemas import NaiveModelConfig
from app.features.scenarios.models import ScenarioPlan
from app.main import app

# Store / product the test bundle is trained for. High IDs that no seeder uses,
# so the revenue calc deterministically hits the unit-price fallback.
TEST_STORE_ID = 990001
TEST_PRODUCT_ID = 990002
# train_end_date baked into the bundle metadata — the forecast starts the next day.
TEST_TRAIN_END_DATE = "2026-06-30"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session, then wipe every scenario_plan row on teardown."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.execute(delete(ScenarioPlan))
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


@pytest.fixture
def trained_model() -> Generator[str, None, None]:
    """Save a real fitted naive-model bundle on disk; yield its run_id.

    The bundle lands in ``settings.forecast_model_artifacts_dir`` as
    ``model_{run_id}.joblib`` — the exact artifact key ``ScenarioService``
    resolves. The file is removed on teardown.
    """
    settings = get_settings()
    artifacts_dir = Path(settings.forecast_model_artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:12]
    model = NaiveForecaster()
    model.fit(np.array([10.0, 12.0, 11.0, 13.0, 9.0, 14.0, 10.0], dtype=np.float64))
    bundle = ModelBundle(
        model=model,
        config=NaiveModelConfig(),
        metadata={
            "store_id": TEST_STORE_ID,
            "product_id": TEST_PRODUCT_ID,
            "train_end_date": TEST_TRAIN_END_DATE,
            "n_observations": 7,
        },
    )
    save_model_bundle(bundle, artifacts_dir / f"model_{run_id}")

    yield run_id

    (artifacts_dir / f"model_{run_id}.joblib").unlink(missing_ok=True)
