"""Chaos / orphan-state regression tests for the PRP-34 runner.

These tests bypass the HTTP layer and drive ``runner.run_batch`` directly
with a synthetic ``execute_item`` callable, so they can exercise mid-flight
cancellation without depending on the timing of a real backtest. They run
against the real docker-compose Postgres so the DB invariants the runner
guards (no orphaned ``running`` rows, parent ``running_items=0`` after
drain) are verified end-to-end.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.features.batch import runner
from app.features.batch.models import (
    BatchItemStatus,
    BatchJob,
    BatchJobItem,
    BatchStatus,
)
from app.features.data_platform.models import Product, Store

pytestmark = pytest.mark.integration


async def _seed_synthetic_batch(
    db_session: AsyncSession,
    *,
    n_items: int,
    max_parallel: int,
    batch_id_prefix: str = "test_chaos",
) -> tuple[str, list[str]]:
    """Insert a parent + N pending items directly (bypass scope expansion)."""
    bid = f"{batch_id_prefix}_{uuid.uuid4().hex[:8]}"
    batch = BatchJob(
        batch_id=bid,
        operation="backtest",
        scope={"kind": "manual"},
        model_configs=[],
        status=BatchStatus.RUNNING.value,
        total_items=n_items,
        params={},
        max_parallel=max_parallel,
    )
    db_session.add(batch)
    item_ids: list[str] = []
    for i in range(n_items):
        iid = f"{bid}_i{i}"
        item_ids.append(iid)
        db_session.add(
            BatchJobItem(
                item_id=iid,
                batch_id=bid,
                store_id=1,
                product_id=1,
                model_type="naive",
                status=BatchItemStatus.PENDING.value,
                params={},
            )
        )
    await db_session.commit()
    return bid, item_ids


async def test_cancel_mid_flight_does_not_orphan_running_items(
    db_session: AsyncSession,
) -> None:
    """A cancel mid-flight leaves no ``batch_job_item`` in RUNNING state.

    4-item batch, max_parallel=2, slow synthetic children. After cancel:
    - no items in ``running`` status
    - ``batch_job.running_items`` is 0
    """
    bid, item_ids = await _seed_synthetic_batch(db_session, n_items=4, max_parallel=2)
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def slow_exec(item_id: str) -> None:
        async with session_maker() as s:
            await s.execute(
                update(BatchJobItem)
                .where(BatchJobItem.item_id == item_id)
                .values(
                    status=BatchItemStatus.RUNNING.value,
                    started_at=datetime.now(UTC),
                )
            )
            await s.commit()
        try:
            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            raise
        async with session_maker() as s:
            await s.execute(
                update(BatchJobItem)
                .where(BatchJobItem.item_id == item_id)
                .values(
                    status=BatchItemStatus.COMPLETED.value,
                    completed_at=datetime.now(UTC),
                )
            )
            await s.commit()

    task = asyncio.create_task(
        runner.run_batch(
            batch_id=bid,
            item_ids=item_ids,
            max_parallel=2,
            global_max_parallel=10,
            session_maker=session_maker,
            execute_item=slow_exec,
        )
    )
    # Let the 2 max_parallel children acquire the semaphore + start work.
    await asyncio.sleep(0.15)
    fired = runner.cancel_batch(bid)
    assert fired is True
    await task
    runner.mark_completed(bid)
    await engine.dispose()

    # Verify no item left in RUNNING state.
    rows = (
        (await db_session.execute(select(BatchJobItem).where(BatchJobItem.batch_id == bid)))
        .scalars()
        .all()
    )
    statuses = [r.status for r in rows]
    assert BatchItemStatus.RUNNING.value not in statuses, (
        f"orphaned RUNNING item(s) after cancel: {statuses}"
    )
    # Every item should now be either cancelled or (rarely, if the cancel
    # raced the completion update) completed; nothing else.
    allowed = {
        BatchItemStatus.CANCELLED.value,
        BatchItemStatus.COMPLETED.value,
    }
    assert set(statuses) <= allowed, f"unexpected statuses: {statuses}"

    # Parent's running_items must be 0 post-drain.
    parent = (
        await db_session.execute(select(BatchJob).where(BatchJob.batch_id == bid))
    ).scalar_one()
    assert parent.running_items == 0
    # Cleanup for the conftest LIKE 'test%' DELETE.
    await db_session.execute(delete(BatchJobItem).where(BatchJobItem.batch_id == bid))
    await db_session.execute(delete(BatchJob).where(BatchJob.batch_id == bid))
    await db_session.commit()


async def test_parent_status_progresses_as_children_complete(
    client: AsyncClient,
    sample_store: Store,
    sample_products_3: list[Product],
    sample_sales_120: list[Any],
) -> None:
    """A 3-pair max_parallel=2 batch settles with running_items=0 + effective_max_parallel=2.

    Verifies the BatchService → runner → settle integration writes the
    expected JSONB key the PRP-34 ``BatchSubmitResponse.effective_max_parallel``
    computed field resolves at response time.
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
        "max_parallel": 2,
    }
    resp = await client.post("/batch/forecasting", json=payload)
    assert resp.status_code == 202, resp.text
    body = resp.json()

    assert body["status"] == "completed"
    assert body["completed_items"] == 3
    assert body["running_items"] == 0
    assert body["effective_max_parallel"] == 2
    # The JSONB summary itself should carry the key too.
    assert body["result_summary"]["effective_max_parallel"] == 2
