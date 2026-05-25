"""Integration tests for ``DELETE /batch/{batch_id}`` (PRP-34).

ASGITransport-backed — same pattern as ``test_routes_integration.py``.
Marked ``integration`` because they query the real docker-compose Postgres
via the FastAPI ``get_db`` dependency.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.batch import runner
from app.features.batch.models import BatchJob, BatchStatus
from app.features.data_platform.models import Product, Store

pytestmark = pytest.mark.integration


async def test_delete_404_unknown_batch(client: AsyncClient) -> None:
    """Unknown batch_id → RFC 7807 404 problem+json."""
    resp = await client.delete("/batch/does-not-exist-prp34")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == 404
    assert body["code"] == "NOT_FOUND"


async def test_delete_409_terminal_batch(
    client: AsyncClient,
    sample_store: Store,
    sample_products_3: list[Product],
    sample_sales_120: list[Any],
) -> None:
    """A successfully-completed batch is terminal — DELETE returns RFC 7807 409.

    Submits a 3-pair naive backtest; the run completes synchronously inside
    ``POST /batch/forecasting``. The subsequent DELETE finds the parent in
    ``completed`` (terminal) and the runner registry empty.
    """
    payload = {
        "operation": "backtest",
        "scope": {
            "kind": "manual",
            "store_ids": [sample_store.id],
            "product_ids": [p.id for p in sample_products_3],
        },
        "model_configs": [{"model_type": "naive"}],
        "start_date": "2024-01-01",
        "end_date": "2024-04-29",
    }
    submit = await client.post("/batch/forecasting", json=payload)
    assert submit.status_code == 202, submit.text
    batch_id = submit.json()["batch_id"]
    assert submit.json()["status"] == "completed"

    resp = await client.delete(f"/batch/{batch_id}")
    assert resp.status_code == 409
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == 409
    assert body["code"] == "CONFLICT"


async def test_delete_200_clean_drain(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Happy-path DELETE: registered handle, drain succeeds immediately, 200.

    Seeds a ``running`` parent row and pre-fires the registry handle's
    ``completed_event`` so the route's ``runner.await_drain`` returns
    ``True`` without waiting — the same observable shape as
    ``BatchService.submit`` finishing settle and calling ``mark_completed``
    a microsecond before the DELETE handler's drain check. Verifies the
    route then reloads the parent and serialises a 200 ``BatchSubmitResponse``.

    The genuine *mid-flight* cancel-and-drain path is covered end-to-end
    by ``test_runner_chaos.test_cancel_mid_flight_does_not_orphan_running_items``.
    """
    batch = BatchJob(
        batch_id="test_200_drain",
        operation="backtest",
        scope={"kind": "manual"},
        model_configs=[],
        status=BatchStatus.RUNNING.value,
        total_items=0,
        params={},
        max_parallel=4,
    )
    db_session.add(batch)
    await db_session.commit()

    handle = runner.CancelHandle()
    handle.completed_event.set()  # drain returns True immediately
    runner._ACTIVE_BATCHES["test_200_drain"] = handle

    try:
        resp = await client.delete("/batch/test_200_drain")
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("application/json")
        body = resp.json()
        assert body["batch_id"] == "test_200_drain"
        assert body["max_parallel"] == 4
        # The parent was never run through _settle, so it stays ``running``
        # — the route's contract is "return the current parent record after
        # drain", not "force settle"; settle is the submit handler's job.
        assert body["status"] == "running"
    finally:
        runner._ACTIVE_BATCHES.pop("test_200_drain", None)


async def test_delete_504_drain_timeout(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stuck registry handle + 0-second drain timeout → RFC 7807 504.

    Sets up an in-DB ``running`` parent row + a registry handle whose
    ``completed_event`` never fires. With ``batch_cancel_drain_timeout_seconds=0``,
    ``runner.await_drain`` raises ``TimeoutError`` and the route surfaces
    :class:`app.core.exceptions.GatewayTimeoutError` as a 504.
    """
    batch = BatchJob(
        batch_id="test_504_drain",
        operation="backtest",
        scope={"kind": "manual"},
        model_configs=[],
        status=BatchStatus.RUNNING.value,
        total_items=0,
        params={},
        max_parallel=4,
    )
    db_session.add(batch)
    await db_session.commit()

    handle = runner.CancelHandle()
    runner._ACTIVE_BATCHES["test_504_drain"] = handle

    settings = get_settings()
    monkeypatch.setattr(settings, "batch_cancel_drain_timeout_seconds", 0)

    try:
        resp = await client.delete("/batch/test_504_drain")
        assert resp.status_code == 504, resp.text
        assert resp.headers["content-type"].startswith("application/problem+json")
        body = resp.json()
        assert body["status"] == 504
        assert body["code"] == "GATEWAY_TIMEOUT"
        assert "Drain exceeded" in body["detail"]
    finally:
        runner._ACTIVE_BATCHES.pop("test_504_drain", None)
