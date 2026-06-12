"""Pydantic schemas for the demo showcase slice.

Models for ``POST /demo/run`` and ``WS /demo/stream``. Mirrors the agents
``StreamEvent`` precedent (``app/features/agents/schemas.py``): streamed
event/result models are plain ``BaseModel`` subclasses with NO
``ConfigDict(strict=True)`` -- only the request body uses strict mode.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    # E1 (#407): replay provenance. The frontend Replay handler sends the
    # SOURCE row's workspace_id; create_workspace records it verbatim on the
    # NEW row (soft reference -- no existence check). JSON-native str -> no
    # Field(strict=False) needed.
    replayed_from_workspace_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{32}$",  # uuid4().hex shape of workspace_id
        description="workspace_id this run replays; requires preservation='keep'.",
    )

    @model_validator(mode="after")
    def _workspace_name_requires_keep(self) -> DemoRunRequest:
        """Reject a workspace_name on a run that does not keep a workspace."""
        if self.workspace_name is not None and self.preservation != "keep":
            raise ValueError("workspace_name requires preservation='keep'")
        return self

    @model_validator(mode="after")
    def _replayed_from_requires_keep(self) -> DemoRunRequest:
        """Reject a lineage pointer on a run that writes no workspace row."""
        if self.replayed_from_workspace_id is not None and self.preservation != "keep":
            raise ValueError("replayed_from_workspace_id requires preservation='keep'")
        return self


class WorkspaceUpdateRequest(BaseModel):
    """Partial lifecycle update for ``PATCH /demo/workspaces/{workspace_id}``.

    exclude_unset semantics: only fields present in the body are applied;
    explicit ``null`` clears ``name`` / ``notes``. Explicit ``null`` on
    ``archived`` / ``pinned`` / ``tags`` is rejected (422) -- they back NOT
    NULL columns; send ``[]`` to clear tags. ``extra="forbid"`` so a typo'd
    field 422s instead of silently no-opping (RunUpdate precedent,
    ``app/features/registry/schemas.py``). All fields JSON-native -> the
    model-level ``strict=True`` needs no per-field override. ``status`` is
    deliberately absent -- the pipeline owns the run lifecycle.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str | None = Field(
        default=None,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9\-_]*$",  # same as workspace_name
        description="Rename the workspace; explicit null clears the label.",
    )
    notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Free-text annotation; explicit null clears it.",
    )
    tags: list[str] | None = Field(
        default=None,
        max_length=20,
        description="Replace the full tag list (not a merge).",
    )
    archived: bool | None = Field(default=None, description="Archive flag.")
    pinned: bool | None = Field(default=None, description="Pin flag.")

    @field_validator("archived", "pinned", "tags")
    @classmethod
    def _reject_explicit_null(cls, v: bool | list[str] | None) -> bool | list[str]:
        """Reject an explicit ``null`` on the NOT NULL-backed optional fields.

        Fires only on explicitly provided values (pydantic skips validators
        for defaults unless ``validate_default=True``), so an absent field
        stays unset while an explicit ``{"archived": null}`` / ``{"tags":
        null}`` 422s instead of reaching the NOT NULL column via
        ``exclude_unset`` -> ``setattr`` -> IntegrityError 500. tags: send
        ``[]`` to clear, never ``null``.
        """
        if v is None:
            raise ValueError(
                "archived/pinned accept only true/false and tags accepts a list "
                "(send [] to clear) — explicit null is not allowed"
            )
        return v


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


class WorkspaceListItem(BaseModel):
    """A compact row in the saved-workspaces list (E4, issue #393).

    Response model -- plain ``BaseModel`` with ``from_attributes`` (built from
    ``ShowcaseWorkspace`` ORM rows), NOT ``ConfigDict(strict=True)``: strict
    mode is a request-body policy (see the ``StepEvent`` precedent above).
    """

    model_config = ConfigDict(from_attributes=True)

    workspace_id: str = Field(..., description="Unique external identifier (UUID hex).")
    name: str | None = Field(default=None, description="Optional human label.")
    status: str = Field(..., description="Lifecycle state -- running / completed / failed.")
    seed: int = Field(..., description="Seeder seed the run was started with.")
    scenario: str = Field(..., description="Seeder scenario preset value.")
    reset: bool = Field(..., description="Whether the run wiped the database first.")
    skip_seed: bool = Field(..., description="Whether the run skipped the seed step.")
    result_summary: dict[str, Any] | None = Field(
        default=None, description="Winner / WAPE / wall-clock display payload."
    )
    created_at: datetime = Field(..., description="When the run was recorded (UTC).")
    # E1 (#407) -- additive lifecycle + provenance fields (defaults so
    # pre-E1 ORM-shaped stand-ins keep validating).
    archived: bool = Field(default=False, description="Operator archive flag.")
    pinned: bool = Field(default=False, description="Operator pin flag.")
    tags: list[str] = Field(default_factory=list, description="Operator tags.")
    replayed_from_workspace_id: str | None = Field(
        default=None,
        description="workspace_id this run replayed (soft reference; may dangle).",
    )


class WorkspaceDetailResponse(WorkspaceListItem):
    """Full workspace row incl. created objects (E4, issue #393)."""

    store_id: int | None = Field(default=None, description="Showcase grain store id.")
    product_id: int | None = Field(default=None, description="Showcase grain product id.")
    date_start: date | None = Field(default=None, description="Seeded window start.")
    date_end: date | None = Field(default=None, description="Seeded window end.")
    created_objects: dict[str, Any] = Field(
        default_factory=dict,
        description="Soft-reference ids of everything the run created.",
    )
    # E1 (#407) -- additive lifecycle metadata + the six story slots
    # (NULL until their writer epic lands; defaults keep pre-E1 stand-ins valid).
    notes: str | None = Field(default=None, description="Free-text operator annotation.")
    config_schema_version: int = Field(
        default=1, description="Version of the config + story-slot schema."
    )
    seed_overrides: dict[str, Any] | None = Field(
        default=None, description="Story slot (E3 #409 writes): seeder-override payload."
    )
    user_scope: dict[str, Any] | None = Field(
        default=None, description="Story slot (E3 #409 writes): operator-selected focus."
    )
    approval_events: list[dict[str, Any]] | None = Field(
        default=None, description="Story slot (E5 #411 writes): HITL approval audit."
    )
    rag_events: list[dict[str, Any]] | None = Field(
        default=None, description="Story slot (E5 #411 writes): RAG event audit."
    )
    job_ids: list[str] | None = Field(
        default=None, description="Story slot (later epic): submitted job/batch ids."
    )
    phase_summaries: list[dict[str, Any]] | None = Field(
        default=None, description="Story slot (later epic): per-phase outcome summary."
    )


class WorkspaceListResponse(BaseModel):
    """A page of saved workspaces, newest first (E4, issue #393)."""

    model_config = ConfigDict(from_attributes=True)

    workspaces: list[WorkspaceListItem] = Field(
        ..., description="Saved workspaces for the current page; empty when none."
    )
    total: int = Field(..., ge=0, description="Total saved workspaces.")
