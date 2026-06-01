"""Unit route tests — service methods mocked, exercised over the HTTP boundary.

``get_db`` is overridden with a mock session; the service is patched at the
class level so the routes are tested in isolation. Error paths assert the
RFC 7807 problem-detail shape.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.exceptions import BadRequestError, NotFoundError
from app.features.model_selection.schemas import (
    ModelRankEntry,
    ModelSelectionRunResponse,
    SelectionWindow,
    WinnerSummary,
)
from app.features.model_selection.service import ModelSelectionService
from app.main import app


@asynccontextmanager
async def _client() -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)


def _assert_problem_detail(body: dict[str, Any], expected_status: int) -> None:
    for key in ("type", "title", "status", "detail"):
        assert key in body, f"missing RFC 7807 field: {key}"
    assert body["status"] == expected_status


def _run_response() -> ModelSelectionRunResponse:
    metrics = {
        "wape": 10.0,
        "smape": 8.0,
        "mae": 4.0,
        "rmse": 5.0,
        "bias": 0.1,
        "sample_size": 28.0,
    }
    return ModelSelectionRunResponse(
        selection_id="sel123",
        store_id=1,
        product_id=1,
        status="completed",
        selection_window=SelectionWindow(start_date=date(2026, 1, 1), end_date=date(2026, 5, 31)),
        forecast_horizon=14,
        ranking_metric="wape",
        availability=None,
        ranking=[
            ModelRankEntry(rank=1, model_type="naive", params={}, included=True, metrics=metrics)
        ],
        winner=WinnerSummary(model_type="naive", params={}, metrics=metrics, rank=1),
        recommendation_confidence="high",
        confidence_reasons=["clear lead"],
        chart_data=None,
        final_model=None,
        forecast=None,
        business_summary=None,
        error_message=None,
        created_at=datetime.now(UTC),
        completed_at=None,
    )


def _valid_run_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "store_id": 1,
        "product_id": 1,
        "selection_window": {"start_date": "2026-01-01", "end_date": "2026-05-31"},
        "forecast_horizon": 14,
        "split_config": {
            "strategy": "expanding",
            "n_splits": 5,
            "min_train_size": 30,
            "gap": 0,
            "horizon": 14,
        },
        "candidate_models": [{"model_type": "naive", "params": {}}],
    }
    body.update(overrides)
    return body


async def test_run_returns_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ModelSelectionService, "run_selection", AsyncMock(return_value=_run_response())
    )
    async with _client() as ac:
        response = await ac.post("/model-selection/run", json=_valid_run_body())
    assert response.status_code == 200
    body = response.json()
    assert body["selection_id"] == "sel123"
    assert body["recommendation_confidence"] == "high"
    assert "confidence" not in body


async def test_run_validation_error_returns_problem_json() -> None:
    """auto_predict without auto_train_winner is rejected by the validator (422)."""
    async with _client() as ac:
        response = await ac.post(
            "/model-selection/run",
            json=_valid_run_body(auto_predict=True, auto_train_winner=False),
        )
    assert response.status_code == 422
    _assert_problem_detail(response.json(), 422)


async def test_routes_return_problem_json_on_bad_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ModelSelectionService,
        "run_selection",
        AsyncMock(side_effect=BadRequestError(message="availability unusable")),
    )
    async with _client() as ac:
        response = await ac.post("/model-selection/run", json=_valid_run_body())
    assert response.status_code == 400
    _assert_problem_detail(response.json(), 400)


async def test_get_selection_not_found_returns_problem_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ModelSelectionService,
        "get_selection",
        AsyncMock(side_effect=NotFoundError(message="Selection run missing not found")),
    )
    async with _client() as ac:
        response = await ac.get("/model-selection/missing")
    assert response.status_code == 404
    _assert_problem_detail(response.json(), 404)


async def test_availability_returns_200(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.features.model_selection.tests.conftest import make_availability

    monkeypatch.setattr(
        ModelSelectionService,
        "get_availability",
        AsyncMock(return_value=make_availability(status="ready")),
    )
    async with _client() as ac:
        response = await ac.get(
            "/model-selection/availability",
            params={"store_id": 1, "product_id": 1, "forecast_horizon": 14},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


async def test_availability_rejects_bad_query() -> None:
    """store_id < 1 fails Query validation → 422 problem+json."""
    async with _client() as ac:
        response = await ac.get(
            "/model-selection/availability",
            params={"store_id": 0, "product_id": 1},
        )
    assert response.status_code == 422
    _assert_problem_detail(response.json(), 422)


async def test_get_models_returns_catalog_200() -> None:
    """GET /model-selection/models returns the static catalog (no mock needed)."""
    async with _client() as ac:
        response = await ac.get("/model-selection/models")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["models"], list)
    assert len(body["models"]) == 11
    # Each entry carries the backend-owned capability contract.
    first = body["models"][0]
    for key in (
        "model_type",
        "label",
        "family",
        "feature_aware",
        "requires_extra",
        "default_params",
        "supports_auto_predict",
        "description",
    ):
        assert key in first, f"missing catalog field: {key}"
    assert body["default_candidate_model_types"] == [
        "naive",
        "seasonal_naive",
        "moving_average",
        "regression",
        "prophet_like",
    ]


async def test_models_route_not_captured_by_selection_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Literal /models must NOT be matched as GET /{selection_id}.

    If route ordering regressed, the request would hit ``get_selection`` (here
    forced to 404) instead of the catalog handler. We assert the catalog shape
    comes back, proving the literal-before-path-param ordering holds.
    """
    monkeypatch.setattr(
        ModelSelectionService,
        "get_selection",
        AsyncMock(side_effect=NotFoundError(message="selection run models not found")),
    )
    async with _client() as ac:
        response = await ac.get("/model-selection/models")
    assert response.status_code == 200
    assert "models" in response.json()
