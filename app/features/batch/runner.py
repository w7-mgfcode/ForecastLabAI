"""Bounded-concurrency batch runner (PRP-34).

Activates the three forward-compat columns PRP-33 shipped on ``batch_job``
(``max_parallel``, ``running_items``, ``cancelled_items``). The runner is a
single :class:`asyncio.Semaphore` inside an :class:`asyncio.TaskGroup` that
fans out one task per ``batch_job_item``; each child opens its own
``AsyncSession`` and observes a cooperative :class:`asyncio.Event` so
``DELETE /batch/{batch_id}`` cancels what hasn't started and gracefully
drains what has.

The asyncio mechanics (the three working cancel mechanisms, the
``except* asyncio.CancelledError`` PEP-654 catch shape, the ``ContextVar``
inheritance into TaskGroup children) are documented end-to-end in
``PRPs/ai_docs/asyncio-taskgroup-cancellation.md``.

Cross-slice rule: this module imports from ``app.features.batch.models``
(same slice) and ``app.core.*`` only — no cross-slice imports, even lazy.
The per-child execute callable supplied by ``BatchService`` is the seam
that keeps ``app.features.jobs`` reachable without an import here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from app.core.logging import get_logger
from app.features.batch.models import (
    BatchItemStatus,
    BatchJob,
    BatchJobItem,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


logger = get_logger(__name__)


@dataclass
class CancelHandle:
    """Cancel signal + Task refs + completion event for an in-flight batch.

    Created by :func:`run_batch`, looked up by :func:`cancel_batch`, removed
    from :data:`_ACTIVE_BATCHES` and signalled by the runner's caller via
    :func:`mark_completed` *after* the parent's settle has committed — so
    ``DELETE /batch/{batch_id}`` never observes the parent mid-settle.

    Attributes:
        cancel_event: Set to signal cooperative drain.
        completed_event: Set by ``mark_completed`` after parent settle commits.
        tasks: ``asyncio.Task`` refs returned by ``tg.create_task`` — cancel
            target. Never use :func:`asyncio.all_tasks` to find these; that
            mechanism is brittle across concurrent batches (see the ai_doc).
    """

    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    completed_event: asyncio.Event = field(default_factory=asyncio.Event)
    tasks: list[asyncio.Task[None]] = field(default_factory=list)


# Module-level registry — single-process scope (matches the single-host vision
# of ``.claude/rules/product-vision.md``). If a future ADR moves this to a
# shared store (Redis, Postgres advisory locks) that is the entry point.
_ACTIVE_BATCHES: dict[str, CancelHandle] = {}


async def run_batch(
    *,
    batch_id: str,
    item_ids: list[str],
    max_parallel: int,
    global_max_parallel: int,
    session_maker: async_sessionmaker[AsyncSession],
    execute_item: Callable[[str], Awaitable[None]],
) -> int:
    """Execute one batch through a bounded :class:`asyncio.TaskGroup`.

    Args:
        batch_id: ``batch_job.batch_id`` — registry key + log correlator.
        item_ids: pending ``batch_job_item.item_id`` values, in submit order.
        max_parallel: per-batch cap declared in ``batch_job.max_parallel``.
        global_max_parallel: host-wide cap from
            :attr:`app.core.config.Settings.batch_global_max_parallel`.
        session_maker: shared ``async_sessionmaker`` — each child opens
            **one** ``AsyncSession`` from this maker and reuses it for the
            DB writes the runner emits (state transitions + ``running_items``
            counter). The caller-supplied ``execute_item`` opens its own
            session from the same maker (the runner does not pass its
            session in — keeps the contract symmetric with
            ``BatchService._execute_item``).
        execute_item: one-arg coroutine the caller provides. Opens its own
            ``AsyncSession`` from the same ``session_maker`` and runs the
            batch item's work (e.g., delegating to ``JobService``).

    Returns:
        ``effective_max_parallel = min(max_parallel, global_max_parallel)``.

    Notes:
        - Caller MUST call :func:`mark_completed` after the parent's settle
          commits, even on the exception path. The runner deliberately does
          NOT pop the registry entry itself — that would let ``DELETE``'s
          drain race the settle commit.
        - Cancellation does NOT propagate out: ``except* asyncio.CancelledError``
          absorbs the ``ExceptionGroup`` so the caller can settle the parent
          to its observed terminal state.
    """
    effective = min(max_parallel, global_max_parallel)
    sem = asyncio.Semaphore(effective)
    handle = _ACTIVE_BATCHES.setdefault(batch_id, CancelHandle())

    logger.info(
        "batch.runner_start",
        batch_id=batch_id,
        total_items=len(item_ids),
        max_parallel=max_parallel,
        effective_max_parallel=effective,
    )

    async def _child(item_id: str) -> None:
        # One ``AsyncSession`` per child — used for every DB write the runner
        # emits below. Each helper commits its own UPDATE on this session so
        # individual state transitions are visible to concurrent observers
        # (``running_items`` counter is observable to DELETE handlers, etc.).
        async with session_maker() as session:
            # FAST-CANCEL before semaphore acquire — skips not-yet-started
            # work cleanly (the cancel_event check is sync; no await window
            # for a late ``task.cancel()`` to interrupt).
            if handle.cancel_event.is_set():
                await _mark_cancelled_skipped(session, item_id)
                return

            # ``acquired`` tracks whether we entered the semaphore-guarded
            # body. When ``task.cancel()`` fires while we are *waiting* on
            # the semaphore, ``async with sem:`` raises ``CancelledError``
            # before the inner re-check runs; the outer except below routes
            # the item to ``mark_cancelled_skipped`` so the cancel surface
            # is consistent.
            acquired = False
            try:
                async with sem:
                    acquired = True
                    # Re-check after acquire — a sibling may have signalled
                    # cancel while we waited on the semaphore.
                    if handle.cancel_event.is_set():
                        await _mark_cancelled_skipped(session, item_id)
                        return
                    await _bump_running(session, batch_id, +1)
                    try:
                        await execute_item(item_id)
                    except asyncio.CancelledError:
                        # ``execute_item`` catches ``Exception`` but NOT
                        # ``BaseException``; ``CancelledError`` (BaseException
                        # in 3.8+) bubbles up cleanly. Persist the cancelled
                        # terminal state before re-raising so the TaskGroup
                        # absorbs the cancel.
                        await _mark_cancelled_running(session, item_id)
                        raise
                    except Exception:
                        # Defensive: ``execute_item`` should have persisted
                        # its own failure; if it didn't, mark FAILED so the
                        # parent settle aggregates correctly. Do NOT
                        # re-raise — that would tear down sibling children
                        # (test_child_failure_does_not_abort_siblings).
                        logger.exception(
                            "batch.runner_unexpected_child_error",
                            batch_id=batch_id,
                            item_id=item_id,
                        )
                        await _mark_failed_unexpected(session, item_id)
                    finally:
                        await _bump_running(session, batch_id, -1)
            except asyncio.CancelledError:
                if not acquired:
                    # Cancel reached us before we entered the semaphore body
                    # — never started work, never bumped running_items.
                    await _mark_cancelled_skipped(session, item_id)
                raise

    try:
        async with asyncio.TaskGroup() as tg:
            for iid in item_ids:
                # ``name=`` lets the operator inspect tasks in a debugger; we
                # do NOT rely on the name for cancellation (we hold Task refs).
                task = tg.create_task(_child(iid), name=f"batch:{batch_id}:{iid}")
                handle.tasks.append(task)
    except* asyncio.CancelledError:
        # Clean ``task.cancel()`` calls are absorbed by TaskGroup, so this
        # branch is defensive — it fires only if the *parent* coroutine
        # (the POST handler) is cancelled. Either way, the per-child
        # ``finally`` already wrote the terminal state.
        logger.info("batch.runner_cancelled_exception_group", batch_id=batch_id)

    logger.info(
        "batch.runner_complete",
        batch_id=batch_id,
        cancel_requested=handle.cancel_event.is_set(),
    )
    return effective


def cancel_batch(batch_id: str) -> bool:
    """Signal cooperative cancel for an in-flight batch.

    Sets ``cancel_event`` (skips pending children) and calls ``task.cancel()``
    on every tracked child (interrupts running children at the next yield).

    Returns:
        ``True`` if the batch was registered (cancel signal fired);
        ``False`` if no handle exists (race: batch settled before cancel).
    """
    handle = _ACTIVE_BATCHES.get(batch_id)
    if handle is None:
        return False
    handle.cancel_event.set()
    cancelled_count = 0
    for task in handle.tasks:
        if not task.done():
            task.cancel()
            cancelled_count += 1
    logger.info(
        "batch.cancel_requested",
        batch_id=batch_id,
        n_tasks_tracked=len(handle.tasks),
        n_tasks_cancelled=cancelled_count,
    )
    return True


async def await_drain(batch_id: str, timeout_seconds: float) -> bool:
    """Block until the batch's parent settle commits, or timeout elapses.

    Args:
        batch_id: ``batch_job.batch_id``.
        timeout_seconds: max seconds to wait.

    Returns:
        ``True`` on clean drain (or if the batch was never registered);
        ``False`` on timeout.
    """
    handle = _ACTIVE_BATCHES.get(batch_id)
    if handle is None:
        # Already drained (or never registered) — DELETE handler reads as
        # "no need to wait, fetch the settled parent now".
        return True
    try:
        await asyncio.wait_for(
            handle.completed_event.wait(),
            timeout=timeout_seconds,
        )
        return True
    except TimeoutError:
        # ``asyncio.TimeoutError`` is aliased to the built-in ``TimeoutError``
        # since Python 3.11 (PEP 678 / asyncio docs). The project pins
        # Python >= 3.12, so this catch IS the asyncio.wait_for timeout.
        logger.warning(
            "batch.cancel_drain_timeout",
            batch_id=batch_id,
            timeout_seconds=timeout_seconds,
        )
        return False


def mark_completed(batch_id: str) -> None:
    """Signal that the batch's parent settle has committed.

    Must be called by ``BatchService.submit`` after its ``_settle`` commits
    (including on the failure path) so any concurrent ``DELETE`` drain
    unblocks. Idempotent: a missing handle is a no-op.
    """
    handle = _ACTIVE_BATCHES.pop(batch_id, None)
    if handle is None:
        return
    handle.completed_event.set()


# --------------------------------------------------------------------- helpers
# Each helper accepts an already-open ``AsyncSession`` (one per child;
# managed by ``_child``) and commits its single UPDATE on that session. They
# do NOT call ``BatchService`` (would close an import cycle) and they do not
# raise on missing rows (a race where the parent was deleted is survivable
# — log + move on).


async def _bump_running(
    session: AsyncSession,
    batch_id: str,
    delta: int,
) -> None:
    """Atomically bump ``batch_job.running_items`` by ``delta`` (±1)."""
    await session.execute(
        update(BatchJob)
        .where(BatchJob.batch_id == batch_id)
        .values(running_items=BatchJob.running_items + delta)
    )
    await session.commit()


async def _mark_cancelled_skipped(
    session: AsyncSession,
    item_id: str,
) -> None:
    """Mark a not-yet-started item as cancelled (pending → cancelled)."""
    now = datetime.now(UTC)
    await session.execute(
        update(BatchJobItem)
        .where(BatchJobItem.item_id == item_id)
        .values(
            status=BatchItemStatus.CANCELLED.value,
            completed_at=now,
        )
    )
    await session.commit()


async def _mark_cancelled_running(
    session: AsyncSession,
    item_id: str,
) -> None:
    """Mark a running item as cancelled (running → cancelled).

    Runs inside the child's ``except asyncio.CancelledError`` block, so
    ``execute_item`` has already set the item to ``RUNNING`` and bumped the
    parent's ``running_items`` counter. The decrement happens in the
    surrounding ``finally`` block.
    """
    now = datetime.now(UTC)
    row = (
        await session.execute(
            select(BatchJobItem.started_at).where(BatchJobItem.item_id == item_id)
        )
    ).first()
    started_at = row[0] if row is not None else None
    duration_ms = int((now - started_at).total_seconds() * 1000) if started_at is not None else None
    await session.execute(
        update(BatchJobItem)
        .where(BatchJobItem.item_id == item_id)
        .values(
            status=BatchItemStatus.CANCELLED.value,
            completed_at=now,
            duration_ms=duration_ms,
        )
    )
    await session.commit()


async def _mark_failed_unexpected(
    session: AsyncSession,
    item_id: str,
) -> None:
    """Defensive: mark an item ``failed`` when ``execute_item`` raised an
    uncaught exception (its own ``except Exception`` should normally absorb).
    """
    now = datetime.now(UTC)
    await session.execute(
        update(BatchJobItem)
        .where(BatchJobItem.item_id == item_id)
        .values(
            status=BatchItemStatus.FAILED.value,
            completed_at=now,
            error_message="Runner caught unexpected exception (see structlog)",
            error_type="UnexpectedRunnerError",
        )
    )
    await session.commit()


__all__ = [
    "_ACTIVE_BATCHES",
    "CancelHandle",
    "await_drain",
    "cancel_batch",
    "mark_completed",
    "run_batch",
]
