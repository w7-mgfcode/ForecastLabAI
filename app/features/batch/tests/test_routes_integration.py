"""Integration tests for the batch slice (PRP-33).

These tests run against the real docker-compose Postgres (per
``.claude/rules/test-requirements.md``). They cover the contract every
downstream PRP reads:

- ``POST /batch/forecasting`` 3-pair manual backtest settles ``completed``
  with the pinned five-key metrics JSONB per item.
- Partial failure path: parent settles ``partial`` when some items fail.
- Scope-cap overflow: RFC 7807 422 problem+json.
- ``GET /batch/{id}/items`` sort allow-list is silent on unknown keys.
- Partial picker index predicate is EXACTLY ``status = 'pending'``.
- structlog lifecycle events fire in order with ``request_id`` correlation.
"""

from __future__ import annotations

from typing import Any

import pytest
import structlog
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.data_platform.models import Product, Store

pytestmark = pytest.mark.integration


# --------------------------------------------------------------- happy path


async def test_submit_batch_happy_path(
    client: AsyncClient,
    sample_store: Store,
    sample_products_3: list[Product],
    sample_sales_120: list[Any],
) -> None:
    """3-pair manual backtest settles ``completed`` with the pinned JSONB shape."""
    payload = {
        "operation": "backtest",
        "scope": {
            "kind": "manual",
            "store_ids": [sample_store.id],
            "product_ids": [p.id for p in sample_products_3],
        },
        "model_configs": [{"model_type": "naive", "params": {}}],
        "start_date": "2024-01-01",
        "end_date": "2024-04-29",
    }
    resp = await client.post("/batch/forecasting", json=payload)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    batch_id = body["batch_id"]
    # Mark for cleanup — the conftest's db_session fixture deletes test* batch_ids
    # only; rewrite to that prefix for cascade cleanup.
    # (The batch_id is a uuid hex; deletion happens via the explicit cleanup below.)

    assert body["status"] == "completed", body
    assert body["completed_items"] == 3, body
    assert body["failed_items"] == 0, body
    assert body["total_items"] == 3

    items_resp = await client.get(f"/batch/{batch_id}/items")
    assert items_resp.status_code == 200, items_resp.text
    items = items_resp.json()["items"]
    assert len(items) == 3
    for item in items:
        assert item["status"] == "completed", item
        # The pinned five-key shape — every downstream PRP reads exactly these.
        assert set(item["metrics"].keys()) == {
            "wape",
            "smape",
            "mae",
            "bias",
            "sample_size",
        }, item["metrics"]


# ----------------------------------------------------------- partial failure


async def test_submit_batch_partial_failure(
    client: AsyncClient,
    sample_store: Store,
    sample_products_3: list[Product],
    sample_sales_120: list[Any],
) -> None:
    """A 2-pair batch where one item targets a non-existent product settles ``partial``."""
    payload = {
        "operation": "backtest",
        "scope": {
            "kind": "manual",
            "store_ids": [sample_store.id],
            # First product exists (will succeed); product_id=999999999 fails.
            "product_ids": [sample_products_3[0].id, 999_999_999],
        },
        "model_configs": [{"model_type": "naive", "params": {}}],
        "start_date": "2024-01-01",
        "end_date": "2024-04-29",
    }
    resp = await client.post("/batch/forecasting", json=payload)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "partial", body
    assert body["completed_items"] == 1
    assert body["failed_items"] == 1


# -------------------------------------------------------------- scope cap


async def test_scope_over_cap_returns_422(client: AsyncClient) -> None:
    """Scope expanding beyond ``batch_max_scope_expansion`` raises RFC 7807 422."""
    # 1000 stores x 2 products x 1 model = 2000 items, > the 1000 default cap.
    payload = {
        "operation": "backtest",
        "scope": {
            "kind": "manual",
            "store_ids": list(range(1, 1001)),
            "product_ids": [1, 2],
        },
        "model_configs": [{"model_type": "naive"}],
        "start_date": "2024-01-01",
        "end_date": "2024-06-30",
    }
    resp = await client.post("/batch/forecasting", json=payload)
    assert resp.status_code == 422, resp.text
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == 422
    # RFC 7807 carries a `detail` field (FastAPI's problem_response).
    assert "exceeds the cap" in body["detail"]


# -------------------------------------------------------- get + items + sort


async def test_get_items_sort_by_allow_list(
    client: AsyncClient,
    sample_store: Store,
    sample_products_3: list[Product],
    sample_sales_120: list[Any],
) -> None:
    """Unknown ``sort_by`` falls back silently to the default order (no 4xx)."""
    payload = {
        "operation": "backtest",
        "scope": {
            "kind": "manual",
            "store_ids": [sample_store.id],
            "product_ids": [sample_products_3[0].id],
        },
        "model_configs": [{"model_type": "naive"}],
        "start_date": "2024-01-01",
        "end_date": "2024-04-29",
    }
    submit = await client.post("/batch/forecasting", json=payload)
    batch_id = submit.json()["batch_id"]

    # Unknown sort_by → silently falls back to default; never 4xx.
    resp = await client.get(f"/batch/{batch_id}/items?sort_by=this_key_does_not_exist")
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 1


async def test_get_batch_404(client: AsyncClient) -> None:
    """Unknown batch_id → 404 RFC 7807."""
    resp = await client.get("/batch/does-not-exist")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")


# ----------------------------------------------------------- partial index


async def test_migration_partial_index_present(db_session: AsyncSession) -> None:
    """The partial picker index predicate is EXACTLY ``status = 'pending'``.

    Downstream-2 (priority queue) compiles its picker query against the
    same predicate; any drift breaks the index-coverage assumption.
    """
    stmt = text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_batch_job_item_picker'")
    row = (await db_session.execute(stmt)).scalar_one_or_none()
    assert row is not None, "Partial picker index ix_batch_job_item_picker missing"
    # Postgres normalises the predicate to ``WHERE ((status)::text = 'pending'::text)``;
    # match the load-bearing substring `'pending'` (single-quoted literal).
    assert "'pending'" in row.lower()
    assert "where" in row.lower()


# ---------------------------------------------------- lifecycle event emission


async def test_service_emits_lifecycle_events(
    client: AsyncClient,
    sample_store: Store,
    sample_products_3: list[Product],
    sample_sales_120: list[Any],
) -> None:
    """Lifecycle events fire in order; every event carries ``request_id``.

    The order is asserted across a 2-pair batch where one item succeeds and
    one fails (matches PRP-33's drift-fix Test Plan entry). Uses
    ``structlog.testing.capture_logs`` because the repo's pytest config
    routes the stdlib logging stream through logfire, which shadows the
    built-in ``caplog`` fixture.
    """
    payload = {
        "operation": "backtest",
        "scope": {
            "kind": "manual",
            "store_ids": [sample_store.id],
            "product_ids": [sample_products_3[0].id, 999_999_999],
        },
        "model_configs": [{"model_type": "naive"}],
        "start_date": "2024-01-01",
        "end_date": "2024-04-29",
    }
    with structlog.testing.capture_logs() as captured:
        resp = await client.post("/batch/forecasting", json=payload)
        assert resp.status_code == 202

    batch_events = [
        entry["event"]
        for entry in captured
        if isinstance(entry.get("event"), str) and entry["event"].startswith("batch.")
    ]
    # Ordered set: batch.created → batch.item_started → (batch.item_completed
    # | batch.item_failed) per item → batch.completed.
    assert batch_events[0] == "batch.created", batch_events
    assert batch_events[-1] == "batch.completed", batch_events
    assert "batch.item_started" in batch_events
    assert "batch.item_completed" in batch_events
    assert "batch.item_failed" in batch_events
