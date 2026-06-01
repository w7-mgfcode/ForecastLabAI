"""Unit tests for the Slice B bounded-concurrency candidate runner.

The runner's DB helpers are monkeypatched to awaitable no-ops so the asyncio
orchestration is exercised without docker-compose. The DB invariants (no
candidate left ``running`` after a cancel drain) are covered in the integration
suite. Mirrors ``app/features/batch/tests/test_runner.py``.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.features.model_selection import runner


@pytest.fixture(autouse=True)
def _clear_registry() -> Any:
    runner._ACTIVE_SELECTIONS.clear()
    yield
    runner._ACTIVE_SELECTIONS.clear()


@pytest.fixture
def patch_db_helpers(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Replace runner DB helpers with awaitable no-ops + a call tracker."""
    calls: dict[str, list[Any]] = {
        "mark_cancelled_skipped": [],
        "mark_cancelled_running": [],
        "mark_failed_unexpected": [],
    }

    async def _mark_cancelled_skipped(_session: Any, candidate_id: str) -> None:
        calls["mark_cancelled_skipped"].append(candidate_id)

    async def _mark_cancelled_running(_session: Any, candidate_id: str) -> None:
        calls["mark_cancelled_running"].append(candidate_id)

    async def _mark_failed_unexpected(_session: Any, candidate_id: str) -> None:
        calls["mark_failed_unexpected"].append(candidate_id)

    monkeypatch.setattr(runner, "_mark_cancelled_skipped", _mark_cancelled_skipped)
    monkeypatch.setattr(runner, "_mark_cancelled_running", _mark_cancelled_running)
    monkeypatch.setattr(runner, "_mark_failed_unexpected", _mark_failed_unexpected)
    return calls


def _fake_session_maker() -> Any:
    @asynccontextmanager
    async def _ctx() -> Any:
        yield AsyncMock()

    def _maker() -> Any:
        return _ctx()

    return cast(Any, _maker)


# ---------------------------------------------------------------- semaphore


async def test_runner_semaphore_caps_concurrency(
    patch_db_helpers: dict[str, list[Any]],
) -> None:
    """5 candidates with max_parallel=2 — observed concurrent peak == 2."""
    in_flight = 0
    peak = 0

    async def child(_cid: str) -> None:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        try:
            await asyncio.sleep(0.02)
        finally:
            in_flight -= 1

    effective = await runner.run_selection_candidates(
        selection_id="s_sem",
        candidate_ids=[f"c{i}" for i in range(5)],
        max_parallel=2,
        global_max_parallel=10,
        session_maker=_fake_session_maker(),
        execute_candidate=child,
    )
    runner.mark_completed("s_sem")
    assert effective == 2
    assert peak == 2, f"observed peak {peak}, expected exactly 2"


async def test_runner_global_cap_clamps_max_parallel(
    patch_db_helpers: dict[str, list[Any]],
) -> None:
    """max_parallel=32 clamped by global_max_parallel=1 → sequential (peak 1)."""
    in_flight = 0
    peak = 0

    async def child(_cid: str) -> None:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        try:
            await asyncio.sleep(0.01)
        finally:
            in_flight -= 1

    effective = await runner.run_selection_candidates(
        selection_id="s_seq",
        candidate_ids=[f"c{i}" for i in range(4)],
        max_parallel=32,
        global_max_parallel=1,
        session_maker=_fake_session_maker(),
        execute_candidate=child,
    )
    runner.mark_completed("s_seq")
    assert effective == 1
    assert peak == 1, f"global cap of 1 must serialize; observed peak {peak}"


# ---------------------------------------------------- per-child failure isolation


async def test_runner_child_failure_does_not_abort_siblings(
    patch_db_helpers: dict[str, list[Any]],
) -> None:
    completed: list[str] = []

    async def child(cid: str) -> None:
        if cid == "c2":
            raise RuntimeError("synthetic failure")
        await asyncio.sleep(0.01)
        completed.append(cid)

    await runner.run_selection_candidates(
        selection_id="s_fail",
        candidate_ids=[f"c{i}" for i in range(5)],
        max_parallel=5,
        global_max_parallel=10,
        session_maker=_fake_session_maker(),
        execute_candidate=child,
    )
    runner.mark_completed("s_fail")
    assert sorted(completed) == ["c0", "c1", "c3", "c4"]
    assert patch_db_helpers["mark_failed_unexpected"] == ["c2"]


# --------------------------------------------------------------- cancel paths


async def test_runner_cancel_before_start_skips(
    patch_db_helpers: dict[str, list[Any]],
) -> None:
    """max_parallel=1, 3 candidates. Cancel after c0 starts → c1/c2 skip."""
    started: list[str] = []

    async def child(cid: str) -> None:
        started.append(cid)
        await asyncio.sleep(0.5)

    task = asyncio.create_task(
        runner.run_selection_candidates(
            selection_id="s_pending",
            candidate_ids=["c0", "c1", "c2"],
            max_parallel=1,
            global_max_parallel=10,
            session_maker=_fake_session_maker(),
            execute_candidate=child,
        )
    )
    await asyncio.sleep(0.05)
    fired = runner.cancel_selection("s_pending")
    await task
    runner.mark_completed("s_pending")

    assert fired is True
    assert patch_db_helpers["mark_cancelled_running"] == ["c0"]
    assert set(patch_db_helpers["mark_cancelled_skipped"]) == {"c1", "c2"}
    assert started == ["c0"]


async def test_runner_cancel_mid_flight_marks_cancelled(
    patch_db_helpers: dict[str, list[Any]],
) -> None:
    cancelled_in_child: list[str] = []

    async def child(cid: str) -> None:
        try:
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            cancelled_in_child.append(cid)
            raise

    task = asyncio.create_task(
        runner.run_selection_candidates(
            selection_id="s_running",
            candidate_ids=["c0"],
            max_parallel=1,
            global_max_parallel=10,
            session_maker=_fake_session_maker(),
            execute_candidate=child,
        )
    )
    await asyncio.sleep(0.05)
    runner.cancel_selection("s_running")
    await task
    runner.mark_completed("s_running")
    assert cancelled_in_child == ["c0"]
    assert patch_db_helpers["mark_cancelled_running"] == ["c0"]


# ------------------------------------------------------------- registry hygiene


async def test_mark_completed_unblocks_await_drain() -> None:
    runner._ACTIVE_SELECTIONS["sx"] = runner.CancelHandle()
    drain_task = asyncio.create_task(runner.await_drain("sx", timeout_seconds=1.0))
    await asyncio.sleep(0.01)
    runner.mark_completed("sx")
    drained = await drain_task
    assert drained is True
    assert "sx" not in runner._ACTIVE_SELECTIONS


async def test_cancel_selection_returns_false_when_unregistered() -> None:
    assert runner.cancel_selection("nope") is False


async def test_await_drain_returns_true_when_unregistered() -> None:
    assert await runner.await_drain("nope", timeout_seconds=0.0) is True


async def test_await_drain_times_out_on_stuck_handle() -> None:
    runner._ACTIVE_SELECTIONS["s_stuck"] = runner.CancelHandle()
    assert await runner.await_drain("s_stuck", timeout_seconds=0.05) is False
