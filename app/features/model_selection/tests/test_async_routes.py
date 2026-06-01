"""Unit route tests for the Slice B async endpoints (service mocked).

Mirrors ``test_routes.py``: ``get_db`` overridden with a mock session, the
service patched at the class level. Asserts the 202 shape + headers and the
DELETE 404/409 mapping over the HTTP boundary.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.exceptions import ConflictError, NotFoundError
from app.features.model_selection.schemas import (
    CandidateProgress,
    ModelSelectionRunResponse,
    SelectionProgress,
    SelectionWindow,
    SubmitRunResponse,
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


def _valid_run_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "store_id": 5,
        "product_id": 8,
        "selection_window": {"start_date": "2026-01-01", "end_date": "2026-05-31"},
        "forecast_horizon": 14,
        "split_config": {
            "strategy": "expanding",
            "n_splits": 5,
            "min_train_size": 30,
            "gap": 0,
            "horizon": 14,
        },
        "candidate_models": [
            {"model_type": "naive", "params": {}},
            {"model_type": "seasonal_naive", "params": {"season_length": 7}},
        ],
    }
    body.update(overrides)
    return body


def _running_submit_response(selection_id: str = "sel_async") -> SubmitRunResponse:
    return SubmitRunResponse(
        selection_id=selection_id,
        store_id=5,
        product_id=8,
        status="running",
        selection_window=SelectionWindow(start_date="2026-01-01", end_date="2026-05-31"),  # type: ignore[arg-type]
        forecast_horizon=14,
        ranking_metric="wape",
        availability=None,
        ranking=[],
        winner=None,
        recommendation_confidence=None,
        confidence_reasons=[],
        chart_data=None,
        final_model=None,
        forecast=None,
        business_summary=None,
        error_message=None,
        created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
        completed_at=None,
        progress=SelectionProgress(
            total=2, pending=2, running=0, completed=0, failed=0, cancelled=0
        ),
        candidate_progress=[
            CandidateProgress(candidate_id="c0", ordinal=0, model_type="naive", status="pending"),
            CandidateProgress(
                candidate_id="c1", ordinal=1, model_type="seasonal_naive", status="pending"
            ),
        ],
        monitor_url=f"/model-selection/{selection_id}",
        cancel_url=f"/model-selection/{selection_id}",
    )


async def test_submit_runs_returns_202_with_headers_and_running_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ModelSelectionService,
        "submit_run",
        AsyncMock(return_value=_running_submit_response()),
    )
    async with _client() as ac:
        response = await ac.post("/model-selection/runs", json=_valid_run_body())
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "running"
    assert body["monitor_url"] == "/model-selection/sel_async"
    assert body["cancel_url"] == "/model-selection/sel_async"
    assert body["progress"]["pending"] == 2
    assert len(body["candidate_progress"]) == 2
    # LRO status-monitor headers.
    assert response.headers.get("location") == "/model-selection/sel_async"
    assert response.headers.get("retry-after") == "2"


async def test_submit_runs_validation_error_returns_problem_json() -> None:
    """A horizon mismatch is rejected by the request validator (422)."""
    bad = _valid_run_body(forecast_horizon=14)
    bad["split_config"] = {
        "strategy": "expanding",
        "n_splits": 5,
        "min_train_size": 30,
        "gap": 0,
        "horizon": 7,
    }
    async with _client() as ac:
        response = await ac.post("/model-selection/runs", json=bad)
    assert response.status_code == 422
    _assert_problem_detail(response.json(), 422)


async def test_delete_run_404_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ModelSelectionService,
        "cancel_run",
        AsyncMock(side_effect=NotFoundError(message="Selection run missing not found")),
    )
    async with _client() as ac:
        response = await ac.delete("/model-selection/missing")
    assert response.status_code == 404
    _assert_problem_detail(response.json(), 404)


async def test_delete_run_409_when_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ModelSelectionService,
        "cancel_run",
        AsyncMock(side_effect=ConflictError(message="Selection run already terminal: completed")),
    )
    async with _client() as ac:
        response = await ac.delete("/model-selection/sel_done")
    assert response.status_code == 409
    _assert_problem_detail(response.json(), 409)


async def test_delete_run_returns_settled_200(monkeypatch: pytest.MonkeyPatch) -> None:
    settled = _running_submit_response("sel_cancel")
    settled_resp = ModelSelectionRunResponse.model_validate(
        {**settled.model_dump(), "status": "cancelled"}
    )
    monkeypatch.setattr(ModelSelectionService, "cancel_run", AsyncMock(return_value=settled_resp))
    async with _client() as ac:
        response = await ac.delete("/model-selection/sel_cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
