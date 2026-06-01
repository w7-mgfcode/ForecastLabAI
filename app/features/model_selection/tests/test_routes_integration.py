"""Integration tests for the model_selection slice against real Postgres.

Marked ``@pytest.mark.integration`` — require ``docker compose up -d`` + an
applied ``alembic upgrade head``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

_TERMINAL = {"completed", "partial", "failed", "cancelled"}


async def _poll_until_terminal(
    client: AsyncClient, selection_id: str, *, attempts: int = 60, delay: float = 0.5
) -> dict[str, Any]:
    """Poll GET /{id} until the run reaches a terminal status (or attempts run out)."""
    body: dict[str, Any] = {}
    for _ in range(attempts):
        response = await client.get(f"/model-selection/{selection_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in _TERMINAL:
            return body
        await asyncio.sleep(delay)
    raise AssertionError(f"run {selection_id} did not settle: last status {body.get('status')}")


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


# --------------------------------------------------------------------- Slice B


async def test_async_runs_submits_202_and_polls_to_terminal_with_winner(
    client: AsyncClient, ready_pair: dict[str, Any]
) -> None:
    """POST /runs returns 202 running immediately; polling settles with a winner."""
    submit = await client.post("/model-selection/runs", json=_run_body(ready_pair))
    assert submit.status_code == 202
    body = submit.json()
    assert body["status"] == "running"
    selection_id = body["selection_id"]
    assert body["monitor_url"] == f"/model-selection/{selection_id}"
    assert body["cancel_url"] == f"/model-selection/{selection_id}"
    assert body["progress"]["total"] == 3
    assert submit.headers.get("location") == f"/model-selection/{selection_id}"
    assert submit.headers.get("retry-after") == "2"

    terminal = await _poll_until_terminal(client, selection_id)
    assert terminal["status"] in {"completed", "partial"}
    assert terminal["winner"] is not None
    assert terminal["chart_data"] is not None
    assert terminal["ranking"]
    assert terminal["progress"]["total"] == 3
    # Terminal GET output is byte-compatible with the sync /run shape.
    assert terminal["recommendation_confidence"] in {"high", "medium", "low"}


async def test_async_runs_failed_candidate_stays_visible(
    client: AsyncClient, ready_pair: dict[str, Any]
) -> None:
    """An invalid candidate surfaces as a failed/excluded entry, not a 500."""
    body = _run_body(
        ready_pair,
        extra_candidates=[{"model_type": "moving_average", "params": {"window_size": 0}}],
    )
    submit = await client.post("/model-selection/runs", json=body)
    assert submit.status_code == 202
    selection_id = submit.json()["selection_id"]

    terminal = await _poll_until_terminal(client, selection_id)
    assert terminal["status"] == "partial"
    excluded = [e for e in terminal["ranking"] if not e["included"]]
    assert excluded
    assert terminal["winner"] is not None
    # The failed candidate is visible in candidate_progress too.
    failed = [c for c in terminal["candidate_progress"] if c["status"] == "failed"]
    assert failed


async def test_cancel_leaves_no_candidate_running(
    client: AsyncClient, ready_pair: dict[str, Any], db_session: AsyncSession
) -> None:
    """DELETE cooperatively cancels + drains — no candidate left 'running'."""
    submit = await client.post("/model-selection/runs", json=_run_body(ready_pair))
    assert submit.status_code == 202
    selection_id = submit.json()["selection_id"]

    # Cancel almost immediately. Fast baseline fits are uncancellable mid-call
    # and may settle the whole run before the DELETE arrives — an HONEST race:
    #   200 = the cancel fired and drained;
    #   409 = the run had already settled (so nothing was left to cancel).
    # Either way the LOAD-BEARING invariant below must hold.
    cancel = await client.delete(f"/model-selection/{selection_id}")
    assert cancel.status_code in {200, 409}

    # Ensure the run is terminal before asserting the invariant (covers the 200
    # path where the worker just settled, and the 409 already-settled path).
    await _poll_until_terminal(client, selection_id)

    # The load-bearing invariant: after the drain, no candidate row is 'running'.
    rows = await db_session.execute(
        text(
            "SELECT count(*) FROM model_selection_candidate "
            "WHERE selection_id = :sid AND status = 'running'"
        ),
        {"sid": selection_id},
    )
    assert rows.scalar() == 0


async def test_cancel_terminal_run_returns_409(
    client: AsyncClient, ready_pair: dict[str, Any]
) -> None:
    """Cancelling an already-settled run returns 409."""
    submit = await client.post("/model-selection/runs", json=_run_body(ready_pair))
    selection_id = submit.json()["selection_id"]
    await _poll_until_terminal(client, selection_id)

    cancel = await client.delete(f"/model-selection/{selection_id}")
    assert cancel.status_code == 409
    assert cancel.json()["status"] == 409


async def test_candidate_table_has_named_indexes(db_session: AsyncSession) -> None:
    rows = await db_session.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = 'model_selection_candidate'")
    )
    names = {row[0] for row in rows}
    assert "ix_model_selection_candidate_candidate_id" in names
    assert "ix_model_selection_candidate_selection_status" in names


async def test_legacy_sync_run_has_no_progress_children(
    client: AsyncClient, ready_pair: dict[str, Any]
) -> None:
    """A legacy synchronous /run row carries no async progress."""
    run = await client.post("/model-selection/run", json=_run_body(ready_pair))
    assert run.status_code == 200
    selection_id = run.json()["selection_id"]
    fetched = await client.get(f"/model-selection/{selection_id}")
    body = fetched.json()
    assert body["progress"] is None
    assert body["candidate_progress"] == []
