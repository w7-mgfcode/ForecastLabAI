"""Unit route tests for the explainability endpoints.

Each test overrides ``get_db`` with a scripted-mock session, so the routes are
exercised over the HTTP boundary without a real database. Error paths assert the
RFC 7807 problem-detail shape.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.features.explainability.tests.conftest import (
    forecast_result_db,
    make_mock_db,
    mock_result,
)
from app.main import app


@asynccontextmanager
async def _client(db: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    """Yield a test client whose get_db dependency yields ``db``."""

    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)


def _assert_problem_detail(body: dict[str, Any], expected_status: int) -> None:
    """Assert an RFC 7807 problem-detail body shape."""
    for key in ("type", "title", "status", "detail"):
        assert key in body, f"missing RFC 7807 field: {key}"
    assert body["status"] == expected_status


@pytest.mark.asyncio
async def test_explain_forecast_returns_200() -> None:
    """POST /explain/forecast returns 200 with a well-formed explanation."""
    db = forecast_result_db([10.0, 12.0, 11.0, 9.0, 14.0])
    async with _client(db) as ac:
        response = await ac.post(
            "/explain/forecast",
            json={
                "store_id": 1,
                "product_id": 2,
                "model_type": "naive",
                "as_of_date": "2024-03-01",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["forecast_value"] == 14.0
    assert body["method"] == "rule_based"
    assert body["drivers"][0]["name"] == "last_observation"


@pytest.mark.asyncio
async def test_explain_forecast_rejects_iso_string_path() -> None:
    """An ISO-string as_of_date is accepted (strict-mode JSON path)."""
    db = forecast_result_db([10.0, 12.0, 11.0])
    async with _client(db) as ac:
        response = await ac.post(
            "/explain/forecast",
            json={
                "store_id": 1,
                "product_id": 2,
                "model_type": "naive",
                "as_of_date": "2024-03-01",
            },
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_explain_forecast_empty_series_returns_400() -> None:
    """An empty series yields an RFC 7807 400."""
    db = forecast_result_db([])
    async with _client(db) as ac:
        response = await ac.post(
            "/explain/forecast",
            json={
                "store_id": 1,
                "product_id": 2,
                "model_type": "naive",
                "as_of_date": "2024-03-01",
            },
        )
    assert response.status_code == 400
    _assert_problem_detail(response.json(), 400)


@pytest.mark.asyncio
async def test_explain_run_missing_returns_404() -> None:
    """GET /explain/runs/{missing} yields an RFC 7807 404."""
    db = make_mock_db([mock_result(one=None)])
    async with _client(db) as ac:
        response = await ac.get("/explain/runs/does-not-exist")
    assert response.status_code == 404
    _assert_problem_detail(response.json(), 404)


@pytest.mark.asyncio
async def test_explain_run_lightgbm_returns_400() -> None:
    """GET /explain/runs/{lightgbm-run} yields an RFC 7807 400."""
    run = SimpleNamespace(
        run_id="run-lgbm",
        model_type="lightgbm",
        model_config={"model_type": "lightgbm"},
        store_id=1,
        product_id=2,
        data_window_end=date(2024, 3, 1),
    )
    db = make_mock_db([mock_result(one=run)])
    async with _client(db) as ac:
        response = await ac.get("/explain/runs/run-lgbm")
    assert response.status_code == 400
    _assert_problem_detail(response.json(), 400)


@pytest.mark.asyncio
async def test_explain_job_missing_returns_404() -> None:
    """GET /explain/jobs/{missing} yields an RFC 7807 404."""
    db = make_mock_db([mock_result(one=None)])
    async with _client(db) as ac:
        response = await ac.get("/explain/jobs/does-not-exist")
    assert response.status_code == 404
    _assert_problem_detail(response.json(), 404)


@pytest.mark.asyncio
async def test_explain_job_non_predict_returns_400() -> None:
    """GET /explain/jobs/{train-job} yields an RFC 7807 400."""
    job = SimpleNamespace(job_id="job-train", job_type="train", status="completed", result={})
    db = make_mock_db([mock_result(one=job)])
    async with _client(db) as ac:
        response = await ac.get("/explain/jobs/job-train")
    assert response.status_code == 400
    _assert_problem_detail(response.json(), 400)
