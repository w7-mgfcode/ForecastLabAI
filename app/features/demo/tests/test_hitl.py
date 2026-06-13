"""Unit tests for the HITL decision relay (E5, issue #411).

pytest-asyncio runs in auto mode (``pyproject.toml``), so ``async def`` tests
need no marker. Each test clears the module slot first so the global state never
leaks between cases.
"""

from __future__ import annotations

import asyncio

import pytest

from app.features.demo import hitl


@pytest.fixture(autouse=True)
def _clear_slot() -> None:
    """Reset the module-level slot before every test (global-state hygiene)."""
    hitl.clear()


def test_resolve_without_register_is_not_found() -> None:
    assert hitl.resolve("action-1", "approved") == "not_found"


def test_resolve_wrong_action_is_not_found() -> None:
    hitl.register("action-1")
    assert hitl.resolve("other", "approved") == "not_found"


def test_double_resolve_is_already_decided() -> None:
    hitl.register("action-1")
    assert hitl.resolve("action-1", "approved") == "applied"
    assert hitl.resolve("action-1", "rejected") == "already_decided"


def test_register_overwrites_stale_slot() -> None:
    hitl.register("stale")
    assert hitl.resolve("stale", "approved") == "applied"
    # A new run registers a fresh slot; the stale decision must not bleed in.
    hitl.register("fresh")
    assert hitl.resolve("fresh", "rejected") == "applied"


def test_clear_closes_the_window() -> None:
    hitl.register("action-1")
    hitl.clear()
    assert hitl.resolve("action-1", "approved") == "not_found"


async def test_resolve_before_wait_returns_decision() -> None:
    hitl.register("action-1")
    assert hitl.resolve("action-1", "rejected", reason="too risky") == "applied"
    result = await hitl.wait_for_decision("action-1", timeout=1.0)
    assert result == ("rejected", "too risky")


async def test_wait_then_resolve_concurrently() -> None:
    hitl.register("action-1")

    async def _decide() -> None:
        await asyncio.sleep(0.02)
        hitl.resolve("action-1", "approved")

    decider = asyncio.ensure_future(_decide())
    result = await hitl.wait_for_decision("action-1", timeout=1.0)
    await decider
    assert result == ("approved", None)


async def test_wait_times_out_to_none() -> None:
    hitl.register("action-1")
    result = await hitl.wait_for_decision("action-1", timeout=0.02)
    assert result is None


async def test_wait_unknown_action_returns_none() -> None:
    result = await hitl.wait_for_decision("never-registered", timeout=0.02)
    assert result is None
