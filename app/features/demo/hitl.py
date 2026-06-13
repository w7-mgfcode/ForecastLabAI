"""HITL decision relay for the showcase pipeline (E5, issue #411).

A single-slot, in-memory store that lets the Showcase HITL step card relay an
operator's Approve/Reject decision back to the in-flight pipeline. The browser
POSTs ``/demo/hitl-decision`` (demo slice); :func:`resolve` records the decision
and wakes the waiting step, which then forwards the real decision to the agents
HITL gate (``POST /agents/sessions/{id}/approve`` with ``approved=true|false``).

This is module-level mutable state. It is SAFE because
``app.features.demo.service._pipeline_lock`` enforces exactly one pipeline per
process, and ``step_agent_hitl_flow`` registers at most one pending action per
run (precedent for module-level demo state: the lock itself, ``service.py:19``).
Defensive anyway: :func:`register` overwrites any stale slot from a crashed run
so the next run can never wedge, and the step clears the slot in a ``finally``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Literal

from app.core.logging import get_logger

logger = get_logger(__name__)

Decision = Literal["approved", "rejected"]
ResolveOutcome = Literal["applied", "already_decided", "not_found"]


@dataclass
class _PendingDecision:
    """The one open decision window, or ``None`` when no step is awaiting."""

    action_id: str
    event: asyncio.Event = field(default_factory=asyncio.Event)
    decision: Decision | None = None
    reason: str | None = None


_slot: _PendingDecision | None = None  # module-level; one pipeline at a time


def register(action_id: str) -> None:
    """Open the decision window for ``action_id``.

    Overwrites any stale slot left by a crashed run so a wedged slot can never
    block the next run. Called by ``step_agent_hitl_flow`` immediately before it
    yields the intermediate ``awaiting_approval`` event.
    """
    global _slot
    _slot = _PendingDecision(action_id=action_id)


def resolve(action_id: str, decision: Decision, reason: str | None = None) -> ResolveOutcome:
    """Record the operator's decision; called by ``POST /demo/hitl-decision``.

    Returns ``"not_found"`` when no window is open for ``action_id`` (nothing
    pending under that id), ``"already_decided"`` when a decision already
    landed, and ``"applied"`` on success.
    """
    if _slot is None or _slot.action_id != action_id:
        return "not_found"
    if _slot.decision is not None:
        return "already_decided"
    _slot.decision = decision
    _slot.reason = reason
    _slot.event.set()
    logger.info("demo.hitl_decision_resolved", action_id=action_id, decision=decision)
    return "applied"


async def wait_for_decision(action_id: str, timeout: float) -> tuple[Decision, str | None] | None:
    """Block up to ``timeout`` seconds for an operator decision.

    Returns the ``(decision, reason)`` pair when the operator decided in time,
    or ``None`` when the window lapsed (the caller then auto-approves) or when
    no slot is open for ``action_id`` (defensive -- the step always registers
    first).
    """
    if _slot is None or _slot.action_id != action_id:
        return None
    try:
        await asyncio.wait_for(_slot.event.wait(), timeout=timeout)
    except TimeoutError:
        return None
    if _slot.decision is None:  # defensive: event set without a decision
        return None
    return (_slot.decision, _slot.reason)


def clear() -> None:
    """Close the decision window (called from the step's ``finally``)."""
    global _slot
    _slot = None
