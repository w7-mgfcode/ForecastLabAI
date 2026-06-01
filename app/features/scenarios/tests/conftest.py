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
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.features.forecasting.models import (
    LightGBMForecaster,
    NaiveForecaster,
    ProphetLikeForecaster,
    RegressionForecaster,
    XGBoostForecaster,
)
from app.features.forecasting.persistence import ModelBundle, save_model_bundle
from app.features.forecasting.schemas import (
    LightGBMModelConfig,
    NaiveModelConfig,
    ProphetLikeModelConfig,
    RegressionModelConfig,
    XGBoostModelConfig,
)
from app.features.scenarios.models import ScenarioPlan
from app.main import app
from app.shared.feature_frames import canonical_feature_columns

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
async def existing_grain(db_session: AsyncSession) -> AsyncGenerator[tuple[int, int], None]:
    """Insert the Store + Product dimension rows for the test grain; clean up after.

    ``propose_scenario`` now rejects a grain whose store/product do not exist
    (#347). ``TEST_STORE_ID`` / ``TEST_PRODUCT_ID`` are deliberately high IDs no
    seeder uses, so a read-only proposal for them needs the dimension rows seeded
    explicitly. Removed on teardown so the grain stays absent for the
    rejection-path tests.
    """
    from app.features.data_platform.models import Product, Store

    db_session.add(Store(id=TEST_STORE_ID, code=f"S{TEST_STORE_ID}", name="Test Store"))
    db_session.add(Product(id=TEST_PRODUCT_ID, sku=f"SKU{TEST_PRODUCT_ID}", name="Test Product"))
    await db_session.commit()
    try:
        yield (TEST_STORE_ID, TEST_PRODUCT_ID)
    finally:
        await db_session.execute(delete(Product).where(Product.id == TEST_PRODUCT_ID))
        await db_session.execute(delete(Store).where(Store.id == TEST_STORE_ID))
        await db_session.commit()


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


@pytest.fixture
def trained_lightgbm_model() -> Generator[str, None, None]:
    """Save a real fitted ``LightGBMForecaster`` bundle on disk; yield run_id.

    SKIPs when the optional ``ml-lightgbm`` dependency is absent. The bundle
    carries the full PRP-27 feature metadata so the model-exogenous simulate
    path can build a future feature frame and genuinely re-forecast — exactly
    as it does for a regression bundle (PRP-30 / MLZOO-B).
    """
    pytest.importorskip("lightgbm")

    settings = get_settings()
    artifacts_dir = Path(settings.forecast_model_artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:12]
    columns = canonical_feature_columns()
    rng = np.random.default_rng(7)
    n_rows = 200
    features = rng.normal(size=(n_rows, len(columns)))
    price_index = columns.index("price_factor")
    target = 40.0 - 20.0 * features[:, price_index] + rng.normal(scale=0.5, size=n_rows)

    model = LightGBMForecaster(random_state=7)
    model.fit(target.astype(np.float64), features.astype(np.float64))

    history_start = date(2026, 4, 1)
    bundle = ModelBundle(
        model=model,
        config=LightGBMModelConfig(),
        metadata={
            "store_id": TEST_STORE_ID,
            "product_id": TEST_PRODUCT_ID,
            "train_end_date": TEST_TRAIN_END_DATE,
            "n_observations": n_rows,
            "feature_columns": columns,
            "history_tail": [12.0] * 90,
            "history_tail_dates": [
                (history_start + timedelta(days=offset)).isoformat() for offset in range(90)
            ],
            "launch_date": "2025-01-01",
        },
    )
    save_model_bundle(bundle, artifacts_dir / f"model_{run_id}")

    yield run_id

    (artifacts_dir / f"model_{run_id}.joblib").unlink(missing_ok=True)


@pytest.fixture
def trained_xgboost_model() -> Generator[str, None, None]:
    """Save a real fitted ``XGBoostForecaster`` bundle on disk; yield run_id.

    SKIPs when the optional ``ml-xgboost`` dependency is absent. The bundle
    carries the full PRP-27 feature metadata so the model-exogenous simulate
    path can build a future feature frame and genuinely re-forecast — exactly
    as it does for a regression bundle (PRP-MLZOO-C1).
    """
    pytest.importorskip("xgboost")

    settings = get_settings()
    artifacts_dir = Path(settings.forecast_model_artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:12]
    columns = canonical_feature_columns()
    rng = np.random.default_rng(7)
    n_rows = 200
    features = rng.normal(size=(n_rows, len(columns)))
    price_index = columns.index("price_factor")
    target = 40.0 - 20.0 * features[:, price_index] + rng.normal(scale=0.5, size=n_rows)

    model = XGBoostForecaster(random_state=7)
    model.fit(target.astype(np.float64), features.astype(np.float64))

    history_start = date(2026, 4, 1)
    bundle = ModelBundle(
        model=model,
        config=XGBoostModelConfig(),
        metadata={
            "store_id": TEST_STORE_ID,
            "product_id": TEST_PRODUCT_ID,
            "train_end_date": TEST_TRAIN_END_DATE,
            "n_observations": n_rows,
            "feature_columns": columns,
            "history_tail": [12.0] * 90,
            "history_tail_dates": [
                (history_start + timedelta(days=offset)).isoformat() for offset in range(90)
            ],
            "launch_date": "2025-01-01",
        },
    )
    save_model_bundle(bundle, artifacts_dir / f"model_{run_id}")

    yield run_id

    (artifacts_dir / f"model_{run_id}.joblib").unlink(missing_ok=True)


@pytest.fixture
def trained_regression_model() -> Generator[str, None, None]:
    """Save a real fitted ``RegressionForecaster`` bundle on disk; yield run_id.

    The bundle carries the full PRP-27 metadata contract — ``feature_columns``,
    ``history_tail``, ``launch_date`` — so the model-exogenous simulate path can
    build a future feature frame and genuinely re-forecast. Demand is wired to
    respond negatively to ``price_factor`` so a price cut lifts the forecast.
    """
    settings = get_settings()
    artifacts_dir = Path(settings.forecast_model_artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:12]
    columns = canonical_feature_columns()
    rng = np.random.default_rng(7)
    n_rows = 200
    features = rng.normal(size=(n_rows, len(columns)))
    # Strong, negative price_factor coefficient: price_factor < 1.0 (a cut)
    # lifts demand. The signal dwarfs the 0.5-scale noise, so the model learns
    # a clean, deterministic price response.
    price_index = columns.index("price_factor")
    target = 40.0 - 20.0 * features[:, price_index] + rng.normal(scale=0.5, size=n_rows)

    model = RegressionForecaster(random_state=7)
    model.fit(target.astype(np.float64), features.astype(np.float64))

    history_start = date(2026, 4, 1)
    bundle = ModelBundle(
        model=model,
        config=RegressionModelConfig(),
        metadata={
            "store_id": TEST_STORE_ID,
            "product_id": TEST_PRODUCT_ID,
            "train_end_date": TEST_TRAIN_END_DATE,
            "n_observations": n_rows,
            "feature_columns": columns,
            "history_tail": [12.0] * 90,
            "history_tail_dates": [
                (history_start + timedelta(days=offset)).isoformat() for offset in range(90)
            ],
            "launch_date": "2025-01-01",
        },
    )
    save_model_bundle(bundle, artifacts_dir / f"model_{run_id}")

    yield run_id

    (artifacts_dir / f"model_{run_id}.joblib").unlink(missing_ok=True)


@pytest.fixture
def trained_prophet_like_model() -> Generator[str, None, None]:
    """Save a real fitted ``ProphetLikeForecaster`` bundle on disk; yield run_id.

    The Prophet-like additive model is feature-aware (pure scikit-learn — no
    flag, no optional dependency), so the bundle carries the full PRP-27
    feature metadata and the model-exogenous simulate path can build a future
    feature frame and genuinely re-forecast — exactly as it does for a
    regression or LightGBM bundle. Demand is wired to respond negatively to
    ``price_factor`` so a price cut lifts the forecast.
    """
    settings = get_settings()
    artifacts_dir = Path(settings.forecast_model_artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:12]
    columns = canonical_feature_columns()
    rng = np.random.default_rng(7)
    n_rows = 200
    features = rng.normal(size=(n_rows, len(columns)))
    price_index = columns.index("price_factor")
    target = 40.0 - 20.0 * features[:, price_index] + rng.normal(scale=0.5, size=n_rows)

    model = ProphetLikeForecaster(random_state=7)
    model.fit(target.astype(np.float64), features.astype(np.float64))

    history_start = date(2026, 4, 1)
    bundle = ModelBundle(
        model=model,
        config=ProphetLikeModelConfig(),
        metadata={
            "store_id": TEST_STORE_ID,
            "product_id": TEST_PRODUCT_ID,
            "train_end_date": TEST_TRAIN_END_DATE,
            "n_observations": n_rows,
            "feature_columns": columns,
            "history_tail": [12.0] * 90,
            "history_tail_dates": [
                (history_start + timedelta(days=offset)).isoformat() for offset in range(90)
            ],
            "launch_date": "2025-01-01",
        },
    )
    save_model_bundle(bundle, artifacts_dir / f"model_{run_id}")

    yield run_id

    (artifacts_dir / f"model_{run_id}.joblib").unlink(missing_ok=True)
