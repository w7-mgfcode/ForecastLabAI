"""Unit route tests for the two MLZOO-D feature-metadata endpoints.

The matrix mirrors PRP-28's ``/explain/runs/{id}`` + ``/explain/jobs/{id}``
test pair: 200 success for tree + additive runs, 400 for baseline / wrong
job type, 404 for missing run/job, 422 for resource-state issues (no
artifact, missing extra, deleted artifact, HistGBR-no-importance gap).
Every error path asserts the RFC 7807 ``application/problem+json``
envelope so the panel and tests can disambiguate state-prevented operations
from input-validation failures via the ``type`` URI.

Each test monkeypatches the relevant service-layer call (``RegistryService``,
``JobService``, ``load_model_bundle``) so the routes are exercised over the
real HTTP boundary without a real database.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.features.forecasting import service as service_module
from app.features.forecasting.models import (
    LightGBMForecaster,
    ProphetLikeForecaster,
    RegressionForecaster,
)
from app.features.forecasting.persistence import ModelBundle
from app.features.forecasting.schemas import (
    LightGBMModelConfig,
    NaiveModelConfig,
    ProphetLikeModelConfig,
    RegressionModelConfig,
)
from app.features.jobs.models import JobStatus, JobType
from app.features.jobs.schemas import JobResponse
from app.features.jobs.service import JobService
from app.features.registry.schemas import RunResponse, RunStatus
from app.features.registry.service import RegistryService
from app.main import app
from app.shared.feature_frames import canonical_feature_columns

_FEATURE_COLUMNS = list(canonical_feature_columns())
_N_FEATURES = len(_FEATURE_COLUMNS)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _client() -> AsyncGenerator[AsyncClient, None]:
    """Yield an ``AsyncClient`` against the real ``app`` with ``get_db`` stubbed.

    The DB session is never actually used by the feature-metadata service —
    every call goes through ``RegistryService`` / ``JobService`` /
    ``load_model_bundle``, all monkeypatched in each test.
    """
    db = AsyncMock()

    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)


def _assert_problem_detail(body: dict[str, Any], expected_status: int) -> None:
    """Assert RFC 7807 envelope shape and the right status code."""
    for key in ("type", "title", "status", "detail"):
        assert key in body, f"missing RFC 7807 field: {key}"
    assert body["status"] == expected_status


def _now() -> datetime:
    return datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)


def _make_run(
    *,
    run_id: str = "run-abc",
    model_type: str = "lightgbm",
    status: RunStatus = RunStatus.SUCCESS,
    artifact_uri: str | None = "/var/forecast-mock/model.joblib",
) -> RunResponse:
    return RunResponse.model_validate(
        {
            "run_id": run_id,
            "status": status,
            "model_type": model_type,
            "model_config_data": {"model_type": model_type},
            "config_hash": "deadbeefdeadbeef",
            "data_window_start": date(2024, 1, 1),
            "data_window_end": date(2024, 1, 31),
            "store_id": 1,
            "product_id": 1,
            "artifact_uri": artifact_uri,
            "created_at": _now(),
            "updated_at": _now(),
        }
    )


def _make_job(
    *,
    job_id: str = "job-abc",
    job_type: JobType = JobType.TRAIN,
    status: JobStatus = JobStatus.COMPLETED,
    result: dict[str, Any] | None = None,
) -> JobResponse:
    return JobResponse.model_validate(
        {
            "job_id": job_id,
            "job_type": job_type,
            "status": status,
            "params": {"model_type": "lightgbm"},
            "result": result
            if result is not None
            else {"model_path": "/var/forecast-mock/model.joblib"},
            "created_at": _now(),
            "updated_at": _now(),
        }
    )


def _fitted_lightgbm_bundle() -> ModelBundle:
    """Build a real fitted LightGBM bundle for the 200 success path."""
    pytest.importorskip("lightgbm")
    rng = np.random.default_rng(0)
    x = rng.normal(size=(60, _N_FEATURES)).astype(np.float64)
    y = (3.0 * x[:, 0] - 2.0 * x[:, 1] + rng.normal(size=60)).astype(np.float64)
    model = LightGBMForecaster(n_estimators=20).fit(y, x)
    return ModelBundle(
        model=model,
        config=LightGBMModelConfig(model_type="lightgbm"),
        metadata={"feature_columns": list(_FEATURE_COLUMNS)},
    )


def _fitted_prophet_like_bundle() -> ModelBundle:
    rng = np.random.default_rng(1)
    x = rng.normal(size=(60, _N_FEATURES)).astype(np.float64)
    y = (3.0 * x[:, 0] - 2.0 * x[:, 1] + rng.normal(size=60)).astype(np.float64)
    model = ProphetLikeForecaster().fit(y, x)
    return ModelBundle(
        model=model,
        config=ProphetLikeModelConfig(model_type="prophet_like"),
        metadata={"feature_columns": list(_FEATURE_COLUMNS)},
    )


def _fitted_regression_bundle() -> ModelBundle:
    rng = np.random.default_rng(2)
    x = rng.normal(size=(60, _N_FEATURES)).astype(np.float64)
    y = (3.0 * x[:, 0] - 2.0 * x[:, 1] + rng.normal(size=60)).astype(np.float64)
    model = RegressionForecaster().fit(y, x)
    return ModelBundle(
        model=model,
        config=RegressionModelConfig(model_type="regression"),
        metadata={"feature_columns": list(_FEATURE_COLUMNS)},
    )


# ---------------------------------------------------------------------------
# /forecasting/runs/{run_id}/feature-metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_run_metadata_returns_200_for_lightgbm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fitted LightGBM run returns a sorted importance list and 'tree' kind."""
    pytest.importorskip("lightgbm")
    bundle = _fitted_lightgbm_bundle()
    monkeypatch.setattr(
        RegistryService, "get_run", AsyncMock(return_value=_make_run(model_type="lightgbm"))
    )
    monkeypatch.setattr(service_module, "load_model_bundle", lambda *a, **kw: bundle)

    async with _client() as ac:
        response = await ac.get("/forecasting/runs/run-abc/feature-metadata")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "run-abc"
    assert body["model_type"] == "lightgbm"
    assert body["model_family"] == "tree"
    assert body["feature_columns"] == _FEATURE_COLUMNS
    assert len(body["features"]) == _N_FEATURES
    # All tree-kind items are non-negative and sorted by |importance| desc.
    assert all(item["kind"] == "tree" for item in body["features"])
    assert all(item["importance"] >= 0.0 for item in body["features"])
    abs_seq = [abs(item["importance"]) for item in body["features"]]
    assert abs_seq == sorted(abs_seq, reverse=True)
    # importance_type is populated (LightGBM default = "split").
    assert body["importance_type"] == "split"


@pytest.mark.asyncio
async def test_get_run_metadata_returns_200_for_prophet_like(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fitted prophet_like run preserves negative coefficients."""
    bundle = _fitted_prophet_like_bundle()
    monkeypatch.setattr(
        RegistryService, "get_run", AsyncMock(return_value=_make_run(model_type="prophet_like"))
    )
    monkeypatch.setattr(service_module, "load_model_bundle", lambda *a, **kw: bundle)

    async with _client() as ac:
        response = await ac.get("/forecasting/runs/run-abc/feature-metadata")

    assert response.status_code == 200
    body = response.json()
    assert body["model_family"] == "additive"
    assert body["importance_type"] == "ridge_coef"
    assert all(item["kind"] == "linear_coef" for item in body["features"])
    # The synthetic target weights feature index 1 negatively — at least one
    # coefficient must be negative if sign was preserved.
    assert any(item["importance"] < 0 for item in body["features"])


@pytest.mark.asyncio
async def test_get_run_metadata_returns_404_for_missing_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(RegistryService, "get_run", AsyncMock(return_value=None))
    async with _client() as ac:
        response = await ac.get("/forecasting/runs/does-not-exist/feature-metadata")
    assert response.status_code == 404
    body = response.json()
    _assert_problem_detail(body, 404)
    assert body["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_run_metadata_returns_400_for_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        RegistryService, "get_run", AsyncMock(return_value=_make_run(model_type="naive"))
    )
    async with _client() as ac:
        response = await ac.get("/forecasting/runs/run-naive/feature-metadata")
    assert response.status_code == 400
    body = response.json()
    _assert_problem_detail(body, 400)
    assert body["code"] == "BAD_REQUEST"
    assert "baseline" in body["detail"]


@pytest.mark.asyncio
async def test_get_run_metadata_returns_422_when_artifact_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        RegistryService,
        "get_run",
        AsyncMock(
            return_value=_make_run(
                model_type="lightgbm",
                status=RunStatus.SUCCESS,
                artifact_uri=None,
            )
        ),
    )
    async with _client() as ac:
        response = await ac.get("/forecasting/runs/run-noart/feature-metadata")
    assert response.status_code == 422
    body = response.json()
    _assert_problem_detail(body, 422)
    assert body["code"] == "UNPROCESSABLE_ENTITY"
    # MUST NOT collide with the Pydantic-input VALIDATION_ERROR 422.
    assert body["code"] != "VALIDATION_ERROR"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [RunStatus.PENDING, RunStatus.RUNNING, RunStatus.FAILED])
async def test_get_run_metadata_returns_422_for_non_success_status(
    monkeypatch: pytest.MonkeyPatch, status: RunStatus
) -> None:
    monkeypatch.setattr(
        RegistryService,
        "get_run",
        AsyncMock(return_value=_make_run(model_type="lightgbm", status=status)),
    )
    async with _client() as ac:
        response = await ac.get("/forecasting/runs/run-pending/feature-metadata")
    assert response.status_code == 422
    body = response.json()
    _assert_problem_detail(body, 422)
    assert body["code"] == "UNPROCESSABLE_ENTITY"


@pytest.mark.asyncio
async def test_get_run_metadata_returns_422_for_missing_ml_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``joblib.load`` raises ModuleNotFoundError when an ml-* extra is missing."""
    monkeypatch.setattr(
        RegistryService,
        "get_run",
        AsyncMock(return_value=_make_run(model_type="lightgbm")),
    )

    def _raise(*a: Any, **kw: Any) -> None:
        raise ModuleNotFoundError("No module named 'lightgbm'", name="lightgbm")

    monkeypatch.setattr(service_module, "load_model_bundle", _raise)

    async with _client() as ac:
        response = await ac.get("/forecasting/runs/run-noextra/feature-metadata")
    assert response.status_code == 422
    body = response.json()
    _assert_problem_detail(body, 422)
    assert body["code"] == "UNPROCESSABLE_ENTITY"
    assert "ml-lightgbm" in body["detail"]


@pytest.mark.asyncio
async def test_get_run_metadata_returns_422_for_deleted_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``load_model_bundle`` raises FileNotFoundError when the file is gone."""
    monkeypatch.setattr(
        RegistryService,
        "get_run",
        AsyncMock(return_value=_make_run(model_type="lightgbm")),
    )

    def _raise(*a: Any, **kw: Any) -> None:
        raise FileNotFoundError("/var/forecast-mock/model.joblib")

    monkeypatch.setattr(service_module, "load_model_bundle", _raise)

    async with _client() as ac:
        response = await ac.get("/forecasting/runs/run-deleted/feature-metadata")
    assert response.status_code == 422
    body = response.json()
    _assert_problem_detail(body, 422)
    assert body["code"] == "UNPROCESSABLE_ENTITY"
    assert "missing from disk" in body["detail"]


@pytest.mark.asyncio
async def test_get_run_metadata_returns_422_for_regression_no_importance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RegressionForecaster's HistGBR doesn't expose feature_importances_."""
    bundle = _fitted_regression_bundle()
    monkeypatch.setattr(
        RegistryService,
        "get_run",
        AsyncMock(return_value=_make_run(model_type="regression")),
    )
    monkeypatch.setattr(service_module, "load_model_bundle", lambda *a, **kw: bundle)

    async with _client() as ac:
        response = await ac.get("/forecasting/runs/run-reg/feature-metadata")
    assert response.status_code == 422
    body = response.json()
    _assert_problem_detail(body, 422)
    assert body["code"] == "UNPROCESSABLE_ENTITY"
    assert "HistGradientBoostingRegressor" in body["detail"]


# ---------------------------------------------------------------------------
# /forecasting/jobs/{job_id}/feature-metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_job_metadata_returns_200_for_completed_train(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed train job returns the importance list keyed by the artifact key."""
    bundle = _fitted_prophet_like_bundle()
    monkeypatch.setattr(
        JobService,
        "get_job",
        AsyncMock(
            return_value=_make_job(
                result={"model_path": "/var/forecast-mock/forecast/model_abc123def456.joblib"}
            )
        ),
    )
    monkeypatch.setattr(service_module, "load_model_bundle", lambda *a, **kw: bundle)

    async with _client() as ac:
        response = await ac.get("/forecasting/jobs/job-abc/feature-metadata")

    assert response.status_code == 200
    body = response.json()
    # The artifact key is parsed from the bundle file stem (NOT a registry UUID).
    assert body["run_id"] == "abc123def456"
    assert body["model_family"] == "additive"


@pytest.mark.asyncio
async def test_get_job_metadata_returns_404_for_missing_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(JobService, "get_job", AsyncMock(return_value=None))
    async with _client() as ac:
        response = await ac.get("/forecasting/jobs/missing/feature-metadata")
    assert response.status_code == 404
    body = response.json()
    _assert_problem_detail(body, 404)
    assert body["code"] == "NOT_FOUND"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("job_type", "status_value", "detail_substring"),
    [
        (JobType.PREDICT, JobStatus.COMPLETED, "completed"),
        (JobType.TRAIN, JobStatus.PENDING, "completed"),
        (JobType.TRAIN, JobStatus.FAILED, "completed"),
    ],
)
async def test_get_job_metadata_returns_400_for_wrong_job_state(
    monkeypatch: pytest.MonkeyPatch,
    job_type: JobType,
    status_value: JobStatus,
    detail_substring: str,
) -> None:
    monkeypatch.setattr(
        JobService,
        "get_job",
        AsyncMock(return_value=_make_job(job_type=job_type, status=status_value, result=None)),
    )
    async with _client() as ac:
        response = await ac.get("/forecasting/jobs/job-x/feature-metadata")
    assert response.status_code == 400
    body = response.json()
    _assert_problem_detail(body, 400)
    assert body["code"] == "BAD_REQUEST"
    assert detail_substring in body["detail"]


@pytest.mark.asyncio
async def test_get_job_metadata_returns_400_for_baseline_trained_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defence-in-depth: a completed train job whose underlying model is
    baseline returns 400, not a 200 with no importance."""
    rng = np.random.default_rng(3)
    from app.features.forecasting.models import NaiveForecaster

    y = rng.normal(size=30).astype(np.float64)
    baseline_model = NaiveForecaster()
    baseline_model.fit(y)
    baseline_bundle = ModelBundle(
        model=baseline_model,
        config=NaiveModelConfig(model_type="naive"),
        metadata={"feature_columns": list(_FEATURE_COLUMNS)},
    )
    monkeypatch.setattr(
        JobService,
        "get_job",
        AsyncMock(
            return_value=_make_job(
                result={"model_path": "/var/forecast-mock/forecast/model_baseline.joblib"}
            )
        ),
    )
    monkeypatch.setattr(service_module, "load_model_bundle", lambda *a, **kw: baseline_bundle)

    async with _client() as ac:
        response = await ac.get("/forecasting/jobs/job-baseline/feature-metadata")
    assert response.status_code == 400
    body = response.json()
    _assert_problem_detail(body, 400)
    assert body["code"] == "BAD_REQUEST"
    assert "baseline" in body["detail"]


@pytest.mark.asyncio
async def test_get_job_metadata_returns_422_for_missing_model_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        JobService,
        "get_job",
        AsyncMock(return_value=_make_job(result={})),  # no model_path key
    )
    async with _client() as ac:
        response = await ac.get("/forecasting/jobs/job-bad/feature-metadata")
    assert response.status_code == 422
    body = response.json()
    _assert_problem_detail(body, 422)
    assert body["code"] == "UNPROCESSABLE_ENTITY"
    assert "model_path" in body["detail"]


@pytest.mark.asyncio
async def test_get_job_metadata_returns_422_for_deleted_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        JobService,
        "get_job",
        AsyncMock(
            return_value=_make_job(
                result={"model_path": "/var/forecast-mock/forecast/model_gone.joblib"}
            )
        ),
    )

    def _raise(*a: Any, **kw: Any) -> None:
        raise FileNotFoundError("/var/forecast-mock/forecast/model_gone.joblib")

    monkeypatch.setattr(service_module, "load_model_bundle", _raise)

    async with _client() as ac:
        response = await ac.get("/forecasting/jobs/job-gone/feature-metadata")
    assert response.status_code == 422
    body = response.json()
    _assert_problem_detail(body, 422)
    assert body["code"] == "UNPROCESSABLE_ENTITY"
    assert "missing from disk" in body["detail"]


@pytest.mark.asyncio
async def test_get_job_metadata_returns_422_for_missing_ml_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        JobService,
        "get_job",
        AsyncMock(
            return_value=_make_job(
                result={"model_path": "/var/forecast-mock/forecast/model_x.joblib"}
            )
        ),
    )

    def _raise(*a: Any, **kw: Any) -> None:
        raise ModuleNotFoundError("No module named 'xgboost'", name="xgboost")

    monkeypatch.setattr(service_module, "load_model_bundle", _raise)

    async with _client() as ac:
        response = await ac.get("/forecasting/jobs/job-noext/feature-metadata")
    assert response.status_code == 422
    body = response.json()
    _assert_problem_detail(body, 422)
    assert body["code"] == "UNPROCESSABLE_ENTITY"
    assert "ml-xgboost" in body["detail"]
