"""Integration tests for the model_selection slice against real Postgres.

Marked ``@pytest.mark.integration`` — require ``docker compose up -d`` + an
applied ``alembic upgrade head``.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


def _run_body(
    pair: dict[str, Any], extra_candidates: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    candidates = [
        {"model_type": "naive", "params": {}},
        {"model_type": "seasonal_naive", "params": {"season_length": 7}},
        {"model_type": "moving_average", "params": {"window_size": 7}},
    ]
    if extra_candidates:
        candidates.extend(extra_candidates)
    return {
        "store_id": pair["store_id"],
        "product_id": pair["product_id"],
        "selection_window": {"start_date": pair["start_date"], "end_date": pair["end_date"]},
        "forecast_horizon": 14,
        "ranking_metric": "wape",
        "split_config": {
            "strategy": "expanding",
            "n_splits": 5,
            "min_train_size": 30,
            "gap": 0,
            "horizon": 14,
        },
        "candidate_models": candidates,
        "auto_train_winner": False,
        "auto_predict": False,
    }


async def test_table_has_named_indexes(db_session: AsyncSession) -> None:
    rows = await db_session.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = 'model_selection_run'")
    )
    names = {row[0] for row in rows}
    assert "ix_model_selection_run_selection_id" in names
    assert "ix_model_selection_run_store_product_created" in names
    assert "ix_model_selection_run_status_created" in names


async def test_availability_ready_pair(client: AsyncClient, ready_pair: dict[str, Any]) -> None:
    response = await client.get(
        "/model-selection/availability",
        params={
            "store_id": ready_pair["store_id"],
            "product_id": ready_pair["product_id"],
            "forecast_horizon": 14,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["observed_days"] == ready_pair["n_days"]
    assert body["recommended_split_config"]["horizon"] == 14


async def test_availability_limited_pair(client: AsyncClient, limited_pair: dict[str, Any]) -> None:
    response = await client.get(
        "/model-selection/availability",
        params={
            "store_id": limited_pair["store_id"],
            "product_id": limited_pair["product_id"],
            "forecast_horizon": 14,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "limited"


async def test_availability_unknown_pair_returns_404(client: AsyncClient) -> None:
    response = await client.get(
        "/model-selection/availability",
        params={"store_id": 999999, "product_id": 999999, "forecast_horizon": 14},
    )
    assert response.status_code == 404
    assert response.json()["status"] == 404


async def test_run_persists_and_get_returns_same(
    client: AsyncClient, ready_pair: dict[str, Any]
) -> None:
    run = await client.post("/model-selection/run", json=_run_body(ready_pair))
    assert run.status_code == 200
    body = run.json()
    assert body["status"] in {"completed", "partial"}
    assert body["winner"] is not None
    assert body["recommendation_confidence"] in {"high", "medium", "low"}
    assert body["chart_data"] is not None
    assert body["ranking"]
    selection_id = body["selection_id"]

    fetched = await client.get(f"/model-selection/{selection_id}")
    assert fetched.status_code == 200
    assert fetched.json()["selection_id"] == selection_id

    ranking = await client.get(f"/model-selection/{selection_id}/ranking")
    assert ranking.status_code == 200
    assert ranking.json()["winner"] is not None


async def test_run_partial_with_bad_candidate(
    client: AsyncClient, ready_pair: dict[str, Any]
) -> None:
    """An invalid candidate param surfaces as a failed entry, not a 500."""
    body = _run_body(
        ready_pair,
        extra_candidates=[{"model_type": "moving_average", "params": {"window_size": 0}}],
    )
    response = await client.post("/model-selection/run", json=body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    excluded = [e for e in payload["ranking"] if not e["included"]]
    assert excluded
    assert payload["winner"] is not None


async def test_get_missing_selection_returns_404(client: AsyncClient) -> None:
    response = await client.get("/model-selection/does-not-exist")
    assert response.status_code == 404
    assert response.json()["status"] == 404
