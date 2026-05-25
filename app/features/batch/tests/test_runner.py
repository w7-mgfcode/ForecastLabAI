"""Unit tests for the PRP-34 bounded-concurrency batch runner.

The runner's DB helpers (``_bump_running``, ``_mark_cancelled_skipped``,
``_mark_cancelled_running``, ``_mark_failed_unexpected``) are monkeypatched
to awaitable no-ops so the asyncio orchestration can be exercised without
docker-compose. The DB invariants those helpers guard (no orphaned
``running`` rows, ``running_items`` counter bounded by
``effective_max_parallel``) are covered in the integration chaos suite
(``test_runner_chaos.py``).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.features.batch import runner


@pytest.fixture(autouse=True)
def _clear_registry() -> Any:
    """Each test starts with a clean ``_ACTIVE_BATCHES`` registry."""
    runner._ACTIVE_BATCHES.clear()
    yield
    runner._ACTIVE_BATCHES.clear()


@pytest.fixture
def patch_db_helpers(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Replace runner DB helpers with awaitable no-ops.

    Returns a call-tracker dict the test can read to assert which helper
    fired for which item — the only contract this fixture cares about.
    The helpers now accept an ``AsyncSession`` (refactor per code review)
    but the unit tests don't exercise SQL — the session arg is ignored.
    """
    calls: dict[str, list[Any]] = {
        "bump_running": [],
        "mark_cancelled_skipped": [],
        "mark_cancelled_running": [],
        "mark_failed_unexpected": [],
    }

    async def _bump_running(_session: Any, batch_id: str, delta: int) -> None:
        calls["bump_running"].append((batch_id, delta))

    async def _mark_cancelled_skipped(_session: Any, item_id: str) -> None:
        calls["mark_cancelled_skipped"].append(item_id)

    async def _mark_cancelled_running(_session: Any, item_id: str) -> None:
        calls["mark_cancelled_running"].append(item_id)

    async def _mark_failed_unexpected(_session: Any, item_id: str) -> None:
        calls["mark_failed_unexpected"].append(item_id)

    monkeypatch.setattr(runner, "_bump_running", _bump_running)
    monkeypatch.setattr(runner, "_mark_cancelled_skipped", _mark_cancelled_skipped)
    monkeypatch.setattr(runner, "_mark_cancelled_running", _mark_cancelled_running)
    monkeypatch.setattr(runner, "_mark_failed_unexpected", _mark_failed_unexpected)
    return calls


def _fake_session_maker() -> Any:
    """An ``async_sessionmaker``-shaped callable that yields a Mock session.

    ``runner.run_batch`` calls ``session_maker()`` and uses the result as an
    async context manager (``async with session_maker() as session:``). The
    Mock session is never touched because the patched helpers ignore it.
    """

    @asynccontextmanager
    async def _ctx() -> Any:
        yield AsyncMock()

    def _maker() -> Any:
        return _ctx()

    return cast(Any, _maker)


# ---------------------------------------------------------------- semaphore


async def test_semaphore_caps_concurrency(patch_db_helpers: dict[str, list[Any]]) -> None:
    """5 children with max_parallel=2 — observed concurrent peak == 2.

    LOAD-BEARING regression for the unbounded-fan-out failure mode. If a
    future refactor replaces the Semaphore with ``asyncio.gather`` or
    pushes the ``async with sem:`` outside the child, this test fires.
    """
    in_flight = 0
    peak = 0

    async def child(_item_id: str) -> None:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        try:
            await asyncio.sleep(0.02)
        finally:
            in_flight -= 1

    effective = await runner.run_batch(
        batch_id="b_sem",
        item_ids=[f"i{i}" for i in range(5)],
        max_parallel=2,
        global_max_parallel=10,
        session_maker=_fake_session_maker(),
        execute_item=child,
    )
    runner.mark_completed("b_sem")

    assert effective == 2
    assert peak == 2, f"observed peak {peak}, expected exactly 2"
    # Every child bumped running ±1 — net zero.
    bump_deltas = [delta for (_, delta) in patch_db_helpers["bump_running"]]
    assert sum(bump_deltas) == 0
    assert len(bump_deltas) == 10  # 5 children x (start + finish)


async def test_settings_global_cap_clamps_max_parallel(
    patch_db_helpers: dict[str, list[Any]],
) -> None:
    """max_parallel=32 clamped by global_max_parallel=4 → effective=4, peak ≤ 4."""
    in_flight = 0
    peak = 0

    async def child(_item_id: str) -> None:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        try:
            await asyncio.sleep(0.02)
        finally:
            in_flight -= 1

    effective = await runner.run_batch(
        batch_id="b_cap",
        item_ids=[f"i{i}" for i in range(8)],
        max_parallel=32,
        global_max_parallel=4,
        session_maker=_fake_session_maker(),
        execute_item=child,
    )
    runner.mark_completed("b_cap")

    assert effective == 4
    assert peak <= 4, f"observed peak {peak} exceeded global cap of 4"


# ---------------------------------------------------- per-child failure isolation


async def test_child_failure_does_not_abort_siblings(
    patch_db_helpers: dict[str, list[Any]],
) -> None:
    """One of 5 children raises RuntimeError; other 4 reach completion.

    The runner's child-level ``except Exception`` (defensive) catches the
    error and marks the item failed; the TaskGroup never sees the exception
    so siblings continue. Without this guard, TaskGroup cancels siblings
    on the first failure.
    """
    completed: list[str] = []

    async def child(item_id: str) -> None:
        if item_id == "i2":
            raise RuntimeError("synthetic failure")
        await asyncio.sleep(0.01)
        completed.append(item_id)

    effective = await runner.run_batch(
        batch_id="b_fail",
        item_ids=[f"i{i}" for i in range(5)],
        max_parallel=5,
        global_max_parallel=10,
        session_maker=_fake_session_maker(),
        execute_item=child,
    )
    runner.mark_completed("b_fail")

    assert effective == 5
    assert sorted(completed) == ["i0", "i1", "i3", "i4"]
    assert patch_db_helpers["mark_failed_unexpected"] == ["i2"]


# --------------------------------------------------------------- cancel paths


async def test_cancel_pending_child_marks_cancelled_without_running(
    patch_db_helpers: dict[str, list[Any]],
) -> None:
    """max_parallel=1, 3 items. After i0 starts, cancel — i1/i2 skip the work."""
    started: list[str] = []

    async def child(item_id: str) -> None:
        started.append(item_id)
        try:
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise

    task = asyncio.create_task(
        runner.run_batch(
            batch_id="b_pending",
            item_ids=["i0", "i1", "i2"],
            max_parallel=1,
            global_max_parallel=10,
            session_maker=_fake_session_maker(),
            execute_item=child,
        )
    )
    await asyncio.sleep(0.05)  # let i0 acquire the semaphore + start work
    fired = runner.cancel_batch("b_pending")
    await task
    runner.mark_completed("b_pending")

    assert fired is True
    # i0 was running when cancelled → mark_cancelled_running path.
    assert patch_db_helpers["mark_cancelled_running"] == ["i0"]
    # i1, i2 never acquired the semaphore → mark_cancelled_skipped path.
    assert set(patch_db_helpers["mark_cancelled_skipped"]) == {"i1", "i2"}
    # i0 was the only one that even entered child.
    assert started == ["i0"]


async def test_cancel_running_child_propagates_cancelled_error(
    patch_db_helpers: dict[str, list[Any]],
) -> None:
    """A running child observes CancelledError; finally block writes cancelled."""
    cancelled_in_child: list[str] = []

    async def child(item_id: str) -> None:
        try:
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            cancelled_in_child.append(item_id)
            raise

    task = asyncio.create_task(
        runner.run_batch(
            batch_id="b_running",
            item_ids=["i0"],
            max_parallel=1,
            global_max_parallel=10,
            session_maker=_fake_session_maker(),
            execute_item=child,
        )
    )
    await asyncio.sleep(0.05)
    runner.cancel_batch("b_running")
    await task
    runner.mark_completed("b_running")

    assert cancelled_in_child == ["i0"]
    assert patch_db_helpers["mark_cancelled_running"] == ["i0"]


# ------------------------------------------------------------- registry hygiene


async def test_mark_completed_unblocks_await_drain(
    patch_db_helpers: dict[str, list[Any]],
) -> None:
    """``mark_completed`` removes the registry entry and fires the event."""
    runner._ACTIVE_BATCHES["bx"] = runner.CancelHandle()

    # Start a drain waiter
    drain_task = asyncio.create_task(runner.await_drain("bx", timeout_seconds=1.0))
    await asyncio.sleep(0.01)
    runner.mark_completed("bx")
    drained = await drain_task

    assert drained is True
    assert "bx" not in runner._ACTIVE_BATCHES


async def test_cancel_batch_returns_false_when_unregistered() -> None:
    """``cancel_batch`` on an unregistered batch returns False (race-safe)."""
    fired = runner.cancel_batch("does-not-exist")
    assert fired is False


async def test_await_drain_returns_true_when_unregistered() -> None:
    """``await_drain`` on an unregistered batch returns True immediately."""
    drained = await runner.await_drain("does-not-exist", timeout_seconds=0.0)
    assert drained is True


async def test_await_drain_times_out_on_stuck_handle() -> None:
    """``await_drain`` returns False when ``completed_event`` never fires."""
    runner._ACTIVE_BATCHES["b_stuck"] = runner.CancelHandle()
    drained = await runner.await_drain("b_stuck", timeout_seconds=0.05)
    assert drained is False
