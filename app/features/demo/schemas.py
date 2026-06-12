"""Pydantic schemas for the demo showcase slice.

Models for ``POST /demo/run`` and ``WS /demo/stream``. Mirrors the agents
``StreamEvent`` precedent (``app/features/agents/schemas.py``): streamed
event/result models are plain ``BaseModel`` subclasses with NO
``ConfigDict(strict=True)`` -- only the request body uses strict mode.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.seeder.config import ScenarioPreset

# One pipeline step's outcome.
StepStatus = Literal["running", "pass", "fail", "skip", "warn"]
# Kind of streamed event.
EventType = Literal["step_start", "step_complete", "pipeline_complete", "error"]


def _utc_now() -> datetime:
    """Return the current UTC timestamp (default factory for event timestamps)."""
    return datetime.now(UTC)


class DemoRunRequest(BaseModel):
    """Request body for ``POST /demo/run`` and the ``WS /demo/stream`` start frame.

    Every field is JSON-native (``int`` / ``bool`` / ``str`` / ``Literal``), so
    ``ConfigDict(strict=True)`` is safe with no ``Field(strict=False)``
    override -- there is no ``date`` / ``datetime`` / ``UUID`` / ``Decimal``
    field (see ``.claude/rules/security-patterns.md`` and
    ``test_strict_mode_policy.py``). The sole exception is ``scenario``, whose
    enum-on-the-wire form carries its own override (PRP-38).
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
    # PRP-38: optional scenario picker. Default keeps existing demo_minimal
    # behaviour wire-compatible with prior clients that omit the field.
    # ``strict=False`` overrides the model-level ``strict=True`` so FastAPI's
    # ``validate_python`` (called on the JSON-parsed dict) accepts the enum's
    # string value form (e.g. ``"showcase_rich"``) on the wire — the same
    # pattern used for ``date`` fields elsewhere in the repo (see
    # ``docs/_base/SECURITY.md`` -> "Pydantic v2 strict mode on FastAPI
    # request bodies").
    scenario: ScenarioPreset = Field(
        default=ScenarioPreset.DEMO_MINIMAL,
        strict=False,
        description="Seeder scenario preset that drives the pipeline shape.",
    )
    # E1 (#390): preservation policy. Default "ephemeral" keeps legacy
    # behaviour byte-identical (no workspace row). Both new fields are
    # JSON-native (Literal[str] / str), so the model-level ``strict=True``
    # needs no per-field override.
    preservation: Literal["ephemeral", "keep"] = Field(
        default="ephemeral",
        description="'keep' records this run as a showcase_workspace row.",
    )
    workspace_name: str | None = Field(
        default=None,
        max_length=100,
        # Same pattern as the registry alias_name (registry/schemas.py).
        pattern=r"^[a-z0-9][a-z0-9\-_]*$",
        description="Optional workspace label; requires preservation='keep'.",
    )

    @model_validator(mode="after")
    def _workspace_name_requires_keep(self) -> DemoRunRequest:
        """Reject a workspace_name on a run that does not keep a workspace."""
        if self.workspace_name is not None and self.preservation != "keep":
            raise ValueError("workspace_name requires preservation='keep'")
        return self


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
    # PRP-38: additive phase grouping. Optional + Nullable so legacy clients
    # that don't render phases keep working. Phase indices are 1-based.
    phase_name: str | None = Field(
        default=None,
        description="Phase id (e.g. 'data', 'modeling'). None on summary events.",
    )
    phase_index: int | None = Field(
        default=None,
        ge=1,
        description="1-based phase position across all phases of this run.",
    )
    phase_total: int | None = Field(
        default=None,
        ge=1,
        description="Total number of distinct phases in this run.",
    )


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
    # E1 (#390): additive Optional field mirroring ``winning_run_id`` --
    # ``None`` on ephemeral runs, the workspace_id on preservation='keep' runs.
    workspace_id: str | None = Field(
        default=None,
        description="showcase_workspace id recorded for this run, if kept.",
    )
