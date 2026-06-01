"""Bounded-concurrency candidate runner for the champion selector (Slice B).

A slice-local mirror of ``app/features/batch/runner.py``: one
:class:`asyncio.Semaphore` inside an :class:`asyncio.TaskGroup` fans out one
task per ``model_selection_candidate``; each child opens its own
``AsyncSession`` and observes a cooperative :class:`asyncio.Event` so
``DELETE /model-selection/{selection_id}`` cancels what hasn't started and
gracefully drains what has.

The asyncio mechanics (the three cancel mechanisms, the
``except* asyncio.CancelledError`` PEP-654 catch shape, the per-task cancel +
cooperative event) are documented in
``PRPs/ai_docs/asyncio-taskgroup-cancellation.md``.

Cross-slice rule: this module imports from ``app.features.model_selection.models``
(same slice) and ``app.core.*`` only — it does NOT import the batch runner
(vertical-slice rule). The per-child ``execute_candidate`` callable supplied by
``ModelSelectionService`` is the seam that keeps the heavy backtest work out of
this module.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from app.core.logging import get_logger
from app.features.model_selection.models import (
    CandidateStatus,
    ModelSelectionCandidate,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


logger = get_logger(__name__)


@dataclass
class CancelHandle:
    """Cancel signal + Task refs + completion event for an in-flight selection.

    Created by :func:`run_selection_candidates`, looked up by
    :func:`cancel_selection`, removed from :data:`_ACTIVE_SELECTIONS` and
    signalled by the runner's caller via :func:`mark_completed` *after* the
    parent's settle has committed — so ``DELETE`` never observes the parent
    mid-settle.
    """

    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    completed_event: asyncio.Event = field(default_factory=asyncio.Event)
    tasks: list[asyncio.Task[None]] = field(default_factory=list)


# Module-level registry — single-process scope (matches the single-host vision).
_ACTIVE_SELECTIONS: dict[str, CancelHandle] = {}


def register_selection(selection_id: str) -> CancelHandle:
    """Eagerly create (or reuse) the cancel handle for a selection.

    Called by the service the moment ``POST /runs`` commits — BEFORE the
    detached worker starts — so a ``DELETE`` arriving in the gap between the 202
    response and the worker's first ``run_selection_candidates`` call still
    finds a handle (and is not misreported as "already settled"). The worker's
    ``setdefault`` reuses this same handle.
    """
    return _ACTIVE_SELECTIONS.setdefault(selection_id, CancelHandle())


async def run_selection_candidates(
    *,
    selection_id: str,
    candidate_ids: list[str],
    max_parallel: int,
    global_max_parallel: int,
    session_maker: async_sessionmaker[AsyncSession],
    execute_candidate: Callable[[str], Awaitable[None]],
) -> int:
    """Execute one selection's candidates through a bounded TaskGroup.

    Args:
        selection_id: ``model_selection_run.selection_id`` — registry key + log
            correlator.
        candidate_ids: ``model_selection_candidate.candidate_id`` values, in
            submit order.
        max_parallel: per-run cap (Slice B passes the global setting — there is
            no per-run field).
        global_max_parallel: host-wide cap from
            :attr:`Settings.model_selection_global_max_parallel`.
        session_maker: shared ``async_sessionmaker``; each child opens one
            ``AsyncSession`` from it for the state-transition writes the runner
            emits. The caller-supplied ``execute_candidate`` opens its OWN
            session from the same maker.
        execute_candidate: one-arg coroutine; runs one candidate's backtest +
            persists its result/failure in its own session.

    Returns:
        ``effective = min(max_parallel, global_max_parallel)``.

    Notes:
        - Caller MUST call :func:`mark_completed` after the parent settle
          commits (even on the exception path).
        - Cancellation does NOT propagate out: ``except* asyncio.CancelledError``
          absorbs the ``ExceptionGroup`` so the caller can settle the parent.
    """
    effective = min(max_parallel, global_max_parallel)
    sem = asyncio.Semaphore(effective)
    handle = _ACTIVE_SELECTIONS.setdefault(selection_id, CancelHandle())

    logger.info(
        "model_selection.runner_start",
        selection_id=selection_id,
        total_candidates=len(candidate_ids),
        max_parallel=max_parallel,
        effective_max_parallel=effective,
    )

    async def _child(candidate_id: str) -> None:
        # One ``AsyncSession`` per child for the runner's own state writes.
        async with session_maker() as session:
            # FAST-CANCEL before the semaphore acquire — skips not-yet-started
            # work cleanly (sync check; no await window).
            if handle.cancel_event.is_set():
                await _mark_cancelled_skipped(session, candidate_id)
                return

            acquired = False
            try:
                async with sem:
                    acquired = True
                    # Re-check after acquire — a sibling may have signalled
                    # cancel while we waited on the semaphore.
                    if handle.cancel_event.is_set():
                        await _mark_cancelled_skipped(session, candidate_id)
                        return
                    try:
                        await execute_candidate(candidate_id)
                    except asyncio.CancelledError:
                        # Persist the cancelled terminal state before re-raising
                        # so the TaskGroup absorbs the cancel.
                        await _mark_cancelled_running(session, candidate_id)
                        raise
                    except Exception:
                        # Defensive: ``execute_candidate`` should persist its own
                        # failure; if it didn't, mark FAILED so settle aggregates
                        # correctly. Do NOT re-raise — that would tear down siblings.
                        logger.exception(
                            "model_selection.runner_unexpected_child_error",
                            selection_id=selection_id,
                            candidate_id=candidate_id,
                        )
                        await _mark_failed_unexpected(session, candidate_id)
            except asyncio.CancelledError:
                if not acquired:
                    await _mark_cancelled_skipped(session, candidate_id)
                raise

    try:
        async with asyncio.TaskGroup() as tg:
            for cid in candidate_ids:
                task = tg.create_task(_child(cid), name=f"model_selection:{selection_id}:{cid}")
                handle.tasks.append(task)
    except* asyncio.CancelledError:
        # Clean ``task.cancel()`` calls are absorbed here; the per-child blocks
        # already wrote the terminal state. The caller settles the parent.
        logger.info(
            "model_selection.runner_cancelled_exception_group",
            selection_id=selection_id,
        )

    logger.info(
        "model_selection.runner_complete",
        selection_id=selection_id,
        cancel_requested=handle.cancel_event.is_set(),
    )
    return effective


def cancel_selection(selection_id: str) -> bool:
    """Signal cooperative cancel for an in-flight selection.

    Sets ``cancel_event`` (skips pending children) and ``task.cancel()`` on
    every tracked child (interrupts running children at the next yield).

    Returns:
        ``True`` if the selection was registered; ``False`` if no handle exists
        (race: the selection settled before cancel).
    """
    handle = _ACTIVE_SELECTIONS.get(selection_id)
    if handle is None:
        return False
    handle.cancel_event.set()
    cancelled_count = 0
    for task in handle.tasks:
        if not task.done():
            task.cancel()
            cancelled_count += 1
    logger.info(
        "model_selection.cancel_requested",
        selection_id=selection_id,
        n_tasks_tracked=len(handle.tasks),
        n_tasks_cancelled=cancelled_count,
    )
    return True


async def await_drain(selection_id: str, timeout_seconds: float) -> bool:
    """Block until the selection's parent settle commits, or timeout elapses.

    Returns:
        ``True`` on clean drain (or if never registered); ``False`` on timeout.
    """
    handle = _ACTIVE_SELECTIONS.get(selection_id)
    if handle is None:
        return True
    try:
        await asyncio.wait_for(handle.completed_event.wait(), timeout=timeout_seconds)
        return True
    except TimeoutError:
        # asyncio.wait_for raises the built-in TimeoutError since Python 3.11.
        logger.warning(
            "model_selection.cancel_drain_timeout",
            selection_id=selection_id,
            timeout_seconds=timeout_seconds,
        )
        return False


def mark_completed(selection_id: str) -> None:
    """Signal that the selection's parent settle has committed.

    Must be called after ``_settle`` commits (including the failure path) so any
    concurrent ``DELETE`` drain unblocks. Idempotent: a missing handle is a no-op.
    """
    handle = _ACTIVE_SELECTIONS.pop(selection_id, None)
    if handle is None:
        return
    handle.completed_event.set()


# --------------------------------------------------------------------- helpers
# Each helper accepts an already-open ``AsyncSession`` (one per child) and
# commits its single UPDATE. They never raise on a missing row (a deleted-parent
# race is survivable — log + move on).


async def _mark_cancelled_skipped(session: AsyncSession, candidate_id: str) -> None:
    """Mark a not-yet-started candidate as cancelled (pending → cancelled)."""
    now = datetime.now(UTC)
    await session.execute(
        update(ModelSelectionCandidate)
        .where(ModelSelectionCandidate.candidate_id == candidate_id)
        .values(status=CandidateStatus.CANCELLED.value, completed_at=now)
    )
    await session.commit()


async def _mark_cancelled_running(session: AsyncSession, candidate_id: str) -> None:
    """Mark a running candidate as cancelled (running → cancelled)."""
    now = datetime.now(UTC)
    row = (
        await session.execute(
            select(ModelSelectionCandidate.started_at).where(
                ModelSelectionCandidate.candidate_id == candidate_id
            )
        )
    ).first()
    started_at = row[0] if row is not None else None
    duration_ms = int((now - started_at).total_seconds() * 1000) if started_at is not None else None
    await session.execute(
        update(ModelSelectionCandidate)
        .where(ModelSelectionCandidate.candidate_id == candidate_id)
        .values(
            status=CandidateStatus.CANCELLED.value,
            completed_at=now,
            duration_ms=duration_ms,
        )
    )
    await session.commit()


async def _mark_failed_unexpected(session: AsyncSession, candidate_id: str) -> None:
    """Defensive: mark a candidate ``failed`` when ``execute_candidate`` raised."""
    now = datetime.now(UTC)
    await session.execute(
        update(ModelSelectionCandidate)
        .where(ModelSelectionCandidate.candidate_id == candidate_id)
        .values(
            status=CandidateStatus.FAILED.value,
            completed_at=now,
            error_message="Runner caught unexpected exception (see structlog)",
            error_type="UnexpectedRunnerError",
        )
    )
    await session.commit()


__all__ = [
    "_ACTIVE_SELECTIONS",
    "CancelHandle",
    "await_drain",
    "cancel_selection",
    "mark_completed",
    "run_selection_candidates",
]
