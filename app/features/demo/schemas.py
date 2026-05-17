"""Pydantic schemas for the demo showcase slice.

Models for ``POST /demo/run`` and ``WS /demo/stream``. Mirrors the agents
``StreamEvent`` precedent (``app/features/agents/schemas.py``): streamed
event/result models are plain ``BaseModel`` subclasses with NO
``ConfigDict(strict=True)`` -- only the request body uses strict mode.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# One pipeline step's outcome.
StepStatus = Literal["running", "pass", "fail", "skip", "warn"]
# Kind of streamed event.
EventType = Literal["step_start", "step_complete", "pipeline_complete", "error"]


def _utc_now() -> datetime:
    """Return the current UTC timestamp (default factory for event timestamps)."""
    return datetime.now(UTC)


class DemoRunRequest(BaseModel):
    """Request body for ``POST /demo/run`` and the ``WS /demo/stream`` start frame.

    Every field is JSON-native (``int`` / ``bool``), so ``ConfigDict(strict=True)``
    is safe with no ``Field(strict=False)`` override -- there is no
    ``date`` / ``datetime`` / ``UUID`` / ``Decimal`` field (see
    ``.claude/rules/security-patterns.md`` and ``test_strict_mode_policy.py``).
    """

    model_config = ConfigDict(strict=True)

    seed: int = Field(default=42, ge=0, description="Deterministic seeder seed.")
    reset: bool = Field(
        default=False,
        description="Wipe the database before seeding (destructive).",
    )
    skip_seed: bool = Field(
        default=True,
        description="Assume an already-seeded database and skip the slow seed step.",
    )


class StepEvent(BaseModel):
    """One streamed pipeline event.

    Plain ``BaseModel`` -- mirrors agents ``StreamEvent``. NO
    ``ConfigDict(strict=True)``: ``timestamp`` is a bare ``datetime`` and event
    models are not request bodies, so the strict-mode JSON-date policy does
    not apply to them.
    """

    event_type: EventType = Field(..., description="Kind of pipeline event.")
    step_name: str = Field(..., description="Step identifier (e.g. 'train').")
    step_index: int = Field(..., description="1-based position in the step table.")
    total_steps: int = Field(..., description="Total number of steps in the run.")
    status: StepStatus | None = Field(
        default=None,
        description="Step outcome -- None on a step_start event.",
    )
    detail: str = Field(default="", description="One-line human-readable detail.")
    duration_ms: float = Field(default=0.0, description="Step wall-clock in milliseconds.")
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured payload (per-model metrics, run_id, ...).",
    )
    timestamp: datetime = Field(default_factory=_utc_now)


class DemoRunResult(BaseModel):
    """Aggregate result returned by the synchronous ``POST /demo/run``."""

    overall_status: Literal["pass", "fail"] = Field(
        ...,
        description="'pass' if no step failed, otherwise 'fail'.",
    )
    steps: list[StepEvent] = Field(
        default_factory=list,
        description="The step_complete events, in execution order.",
    )
    winner_model_type: str | None = Field(
        default=None,
        description="Lowest-WAPE model_type, if the backtest step ran.",
    )
    winner_wape: float | None = Field(
        default=None,
        description="The winning model's aggregated WAPE.",
    )
    winning_run_id: str | None = Field(
        default=None,
        description="Registry run_id of the registered winner.",
    )
    alias: str | None = Field(
        default=None,
        description="Deployment alias pointing at the winning run.",
    )
    wall_clock_s: float = Field(
        default=0.0,
        description="Total pipeline wall-clock in seconds.",
    )
