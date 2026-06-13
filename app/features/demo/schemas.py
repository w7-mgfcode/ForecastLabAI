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

from app.shared.model_taxonomy import KNOWN_MODEL_TYPES
from app.shared.seeder.config import ScenarioPreset
from app.shared.seeder.overrides import SeederOverrides

# One pipeline step's outcome.
StepStatus = Literal["running", "pass", "fail", "skip", "warn"]
# Kind of streamed event.
EventType = Literal["step_start", "step_complete", "pipeline_complete", "error"]


def _utc_now() -> datetime:
    """Return the current UTC timestamp (default factory for event timestamps)."""
    return datetime.now(UTC)


class UserScope(BaseModel):
    """Operator-selected (store, product) focus pair (E3, issue #409).

    Ids are REAL discovered ids (Postgres sequences never reset -- ids are not
    1-based); ``step_status`` validates them against ``/dimensions/*/{id}``
    and warn-falls-back to discovery when the pair dangles (e.g. after a
    reset+reseed re-issued ids). ``extra="forbid"`` keeps the slot schema
    closed; additive keys need a documented schema change.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    store_id: int = Field(..., ge=1, description="Real store id from /dimensions/stores.")
    product_id: int = Field(..., ge=1, description="Real product id from /dimensions/products.")


class DemoBacktestConfig(BaseModel):
    """Backtest knobs for the showcase pipeline (E4, issue #410).

    Bounds MIRROR ``app/features/backtesting/schemas.py:SplitConfig`` exactly --
    the pipeline forwards them verbatim into ``POST /backtesting/run``. The only
    intentional divergence is ``n_splits``'s default (3, the demo default, vs
    SplitConfig's 5) and the addition of ``metric``, the winner-ranking choice
    (D5: WAPE / MAE / RMSE, all lower-is-better; smape/bias deliberately
    excluded -- issue #410 names exactly these three). Every field is
    JSON-native so the parent's ``strict=True`` needs no per-field override.
    """

    model_config = ConfigDict(strict=True)

    horizon: int = Field(default=14, ge=1, le=90, description="Forecast horizon per fold.")
    strategy: Literal["expanding", "sliding"] = Field(
        default="expanding",
        description="Expanding grows the training window; sliding keeps it fixed.",
    )
    n_splits: int = Field(default=3, ge=2, le=20, description="Number of CV folds.")
    min_train_size: int = Field(default=30, ge=7, description="Minimum training samples.")
    gap: int = Field(default=0, ge=0, le=30, description="Gap days between train end and test.")
    metric: Literal["wape", "mae", "rmse"] = Field(
        default="wape", description="Winner-ranking metric (lower is better)."
    )

    @model_validator(mode="after")
    def _gap_lt_horizon(self) -> DemoBacktestConfig:
        """Mirror SplitConfig's horizon > gap invariant (avoids a 422 deeper in)."""
        if self.gap >= self.horizon:
            raise ValueError(f"horizon ({self.horizon}) must be greater than gap ({self.gap})")
        return self


class DemoRunRequest(BaseModel):
    """Request body for ``POST /demo/run`` and the ``WS /demo/stream`` start frame.

    Every field is JSON-native (``int`` / ``bool`` / ``str`` / ``Literal``), so
    ``ConfigDict(strict=True)`` is safe with no ``Field(strict=False)``
    override -- there is no ``date`` / ``datetime`` / ``UUID`` / ``Decimal``
    field (see ``.claude/rules/security-patterns.md`` and
    ``test_strict_mode_policy.py``). The sole exception is ``scenario``, whose
    enum-on-the-wire form carries its own override (PRP-38). The nested
    ``seed_overrides`` / ``user_scope`` models are themselves all-JSON-native
    and validate from the JSON-parsed dict under the parent's strict mode
    (runtime-verified on pydantic 2.12.5 -- E3 #409).
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
    # E3 (#409): curated seed overrides + operator-selected focus pair. Both
    # additive Optional with None defaults so legacy frames stay byte-identical.
    # The nested models carry their own ConfigDict(strict=True, extra="forbid").
    seed_overrides: SeederOverrides | None = Field(
        default=None,
        description=(
            "Curated seeder overrides (allow-listed knobs); requires "
            "skip_seed=false (Re-seed first). Forwarded verbatim to "
            "POST /seeder/generate and recorded on a kept workspace row."
        ),
    )
    user_scope: UserScope | None = Field(
        default=None,
        description=(
            "Operator-selected (store, product) focus pair the pipeline models "
            "instead of the auto-discovered first pair; validated by the status "
            "step (warn + fallback to discovery on a dangling pair)."
        ),
    )
    # E4 (#410): additive run-config. None -> the legacy DEMO_MODEL_TYPES trio +
    # legacy split constants, byte-identical behaviour. The model allow-list
    # comes from app.shared.model_taxonomy (vertical-slice rule: the demo slice
    # never imports model_selection / forecasting). Flag enforcement is NOT
    # here -- a disabled opt-in model fails fast in step_train (D6) to avoid the
    # documented ".env-bleed" class from reading settings inside a schema.
    train_model_types: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=10,
        description="Models the pipeline trains/backtests; None = the legacy baseline trio.",
    )
    backtest: DemoBacktestConfig | None = Field(
        default=None,
        description="Backtest split + ranking-metric config; None = the legacy demo split.",
    )

    @field_validator("train_model_types")
    @classmethod
    def _known_unique_models(cls, v: list[str] | None) -> list[str] | None:
        """Allow-list + de-dup the model selection against KNOWN_MODEL_TYPES."""
        if v is None:
            return v
        unknown = [m for m in v if m not in KNOWN_MODEL_TYPES]
        if unknown:
            raise ValueError(
                f"Unknown model type(s): {unknown!r}. Valid: {sorted(KNOWN_MODEL_TYPES)}"
            )
        if len(set(v)) != len(v):
            raise ValueError("train_model_types contains duplicates")
        return v

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

    @model_validator(mode="after")
    def _seed_overrides_require_reseed(self) -> DemoRunRequest:
        """Reject overrides on a run that skips the seed step (silent no-op trap).

        An empty overrides object (``{}`` on the wire) normalizes to ``None``
        so downstream code has a single "no overrides" representation.
        """
        if self.seed_overrides is not None and self.seed_overrides.is_empty():
            self.seed_overrides = None
        if self.seed_overrides is not None and self.skip_seed:
            raise ValueError("seed_overrides requires skip_seed=false (Re-seed first)")
        return self

    @model_validator(mode="after")
    def _window_days_forbidden_on_holiday_rush(self) -> DemoRunRequest:
        """Reject window_days on the calendar-pinned holiday_rush preset.

        The preset's HolidayConfig spikes are fixed 2024 dates -- a shifted
        window would silently drop every holiday spike, so this fails loudly.
        """
        if (
            self.seed_overrides is not None
            and self.seed_overrides.window_days is not None
            and self.scenario is ScenarioPreset.HOLIDAY_RUSH
        ):
            raise ValueError("window_days cannot override the calendar-pinned holiday_rush window")
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
    # E3 (#409) -- the two replay-relevant story slots live on the LIST item
    # (not detail-only): the frontend Replay reads list rows, and the
    # replay-verbatim contract includes both slots.
    seed_overrides: dict[str, Any] | None = Field(
        default=None, description="Story slot (E3 #409): seeder-override payload."
    )
    user_scope: dict[str, Any] | None = Field(
        default=None, description="Story slot (E3 #409): operator-selected focus."
    )
    # E4 (#410) -- replay-input echo (NOT a story slot; a dedicated nullable
    # JSONB column, see DOMAIN_MODEL.md D1). None on default-config / pre-E4
    # rows. On the LIST item because the frontend Replay reads list rows and
    # rebuilds the start frame's train_model_types + backtest from it.
    run_config: dict[str, Any] | None = Field(
        default=None,
        description="Replay-input run config (model set + backtest); None on defaults.",
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
    # E3 (#409) -- seed_overrides / user_scope moved UP to WorkspaceListItem
    # (replay reads list rows); the four remaining story slots stay detail-only.
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


# E2 (#408) -- link-health classification of one probed soft reference.
RefHealthStatus = Literal["alive", "dead", "unknown"]
# E2 (#408) -- kind of soft-referenced object a workspace can record.
RefType = Literal["model_run", "scenario_plan", "alias", "batch", "agent_session", "job"]


class WorkspaceRefHealth(BaseModel):
    """Liveness of one soft reference recorded on a workspace (E2, #408).

    Response model -- plain ``BaseModel``, NOT strict (``StepEvent``
    precedent above; strict mode is request-body-only policy).
    """

    key: str = Field(
        ...,
        description="created_objects key, e.g. 'winning_run_id' or 'scenario_plan_ids[0]'.",
    )
    ref_type: RefType = Field(..., description="Kind of referenced object.")
    ref_id: str = Field(..., description="The recorded soft-reference id.")
    status: RefHealthStatus = Field(
        ..., description="alive (2xx) / dead (404) / unknown (anything else)."
    )
    probe_path: str = Field(..., description="The public API path probed.")


class WorkspaceHealthResponse(BaseModel):
    """Per-workspace link-health summary (E2, #408).

    Response model -- plain ``BaseModel``, NOT strict.
    """

    workspace_id: str = Field(..., description="The probed workspace's external id.")
    workspace_status: str = Field(..., description="running / completed / failed.")
    partial_run: bool = Field(
        ..., description="True when workspace_status != 'completed' (the run never settled)."
    )
    references: list[WorkspaceRefHealth] = Field(
        default_factory=list,
        description="Per-reference probe results; empty when nothing was recorded.",
    )
    alive: int = Field(..., ge=0, description="Count of references that probed alive.")
    dead: int = Field(..., ge=0, description="Count of references that probed dead (404).")
    unknown: int = Field(..., ge=0, description="Count of references whose probe was inconclusive.")
    checked_at: datetime = Field(default_factory=_utc_now, description="When the probes ran (UTC).")


class HitlDecisionRequest(BaseModel):
    """Operator decision relay for the showcase HITL step (E5, issue #411).

    POSTed by the Showcase step card's Approve / Reject buttons to
    ``POST /demo/hitl-decision``; the in-flight pipeline waits on the in-memory
    relay and forwards the real decision to the agents HITL gate. HTTP-only
    body -- every field is JSON-native (``str`` / ``Literal``), so the
    model-level ``strict=True`` needs no ``Field(strict=False)`` override (the
    AST policy walker fires only on date/datetime/time/UUID/Decimal).
    ``extra="forbid"`` so a typo'd field 422s instead of silently no-opping.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    action_id: str = Field(..., min_length=1, description="Pending action to decide.")
    decision: Literal["approved", "rejected"] = Field(..., description="Operator decision.")
    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reason (mirrors agents ApprovalRequest.reason).",
    )


class ApprovalEventItem(BaseModel):
    """One flattened approval event for ``GET /demo/approval-events`` (E5, #411).

    Built from JSONB story-slot dicts (NOT ORM rows) -- tolerant typing with
    defaults so a v1 entry (pre-E5 base keys only) still validates. Response
    model: plain ``BaseModel``, NOT strict (strict mode is request-body policy).
    """

    workspace_id: str = Field(..., description="The workspace whose run recorded this event.")
    workspace_name: str | None = Field(default=None, description="The workspace's optional label.")
    action_id: str | None = Field(default=None, description="The decided action's id.")
    tool_name: str | None = Field(default=None, description="The gated tool (e.g. save_scenario).")
    decision: str | None = Field(default=None, description="approved / rejected / timed_out.")
    decided_at: str | None = Field(default=None, description="ISO8601 UTC decision timestamp.")
    session_id: str | None = Field(
        default=None, description="Agent session the action belonged to."
    )
    auto_approved: bool | None = Field(
        default=None, description="True when the decision window lapsed."
    )
    reason: str | None = Field(default=None, description="Operator-supplied reason (reject).")
    execution_status: str | None = Field(
        default=None, description="Agents-API status: executed / rejected / external_4xx."
    )
    transcript_summary: str | None = Field(
        default=None, description="Agent chat message (<=200 chars)."
    )


class ApprovalEventsResponse(BaseModel):
    """Recent HITL approval events flattened across workspaces (E5, #411)."""

    events: list[ApprovalEventItem] = Field(
        ..., description="Flattened approval events, newest workspace first; empty when none."
    )
    total: int = Field(..., ge=0, description="Number of flattened entries returned (capped).")


# =============================================================================
# E6 (#412) -- workspace export bundle (POST /demo/workspaces/{id}/export)
# =============================================================================

# Bumped on any manifest-shape change so bundle consumers can branch on it.
BUNDLE_FORMAT_VERSION = 1


class ExportFileEntry(BaseModel):
    """One file inside an exported workspace bundle (E6, issue #412).

    Response model -- plain ``BaseModel``, NOT ``ConfigDict(strict=True)``:
    strict mode is a request-body policy and this endpoint has no body.
    """

    path: str = Field(..., description="Bundle-relative POSIX path.")
    sha256: str = Field(..., description="Hex SHA-256 of the file contents.")
    size_bytes: int = Field(..., ge=0, description="File size in bytes.")


class UnresolvedReference(BaseModel):
    """A soft reference that could not be resolved during export (E6, #412)."""

    key: str = Field(..., description="created_objects key (e.g. 'scenario_plan_ids').")
    ref_id: str = Field(..., description="The id that failed to resolve.")
    reason: str = Field(..., description="Short cause, e.g. 'HTTP 404'.")


class WorkspaceExportResult(BaseModel):
    """Result of ``POST /demo/workspaces/{workspace_id}/export`` (E6, #412)."""

    workspace_id: str = Field(..., description="The exported workspace's id.")
    bundle_path: str = Field(
        ..., description="Repo-root-relative bundle dir, e.g. 'artifacts/showcase/<id>'."
    )
    bundle_format_version: int = Field(..., description="Manifest schema version.")
    exported_at: datetime = Field(..., description="When the export ran (UTC).")
    # The COMPLETE on-disk inventory, INCLUDING checksums.sha256 itself (with
    # its own computed hash) -- it just never lists itself inside the checksum
    # file; the response is where that hash lives.
    files: list[ExportFileEntry] = Field(
        ..., description="Every file in the bundle with its hash and size."
    )
    scenario_plans_exported: int = Field(
        ..., ge=0, description="Scenario plans written to scenario_plans/."
    )
    model_runs_referenced: int = Field(
        ..., ge=0, description="Model runs referenced in the manifest (not copied)."
    )
    unresolved_references: list[UnresolvedReference] = Field(
        ..., description="Soft references that could not be resolved (export still succeeded)."
    )
    validated: bool = Field(
        ..., description="True when checksums.sha256 re-read + recomputed clean."
    )
