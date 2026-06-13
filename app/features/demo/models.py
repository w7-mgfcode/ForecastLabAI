"""Showcase workspace ORM model.

First table owned by the demo slice (precedent: ``app/features/batch/models.py``).
A row = one preserved showcase run: its configuration (replay inputs) plus the
ids of every object the pipeline created. All recorded ids are OPAQUE SOFT
REFERENCES -- deliberately NO ForeignKey to ``model_run`` / ``scenario_plan`` /
``batch_job`` / ``agent_session``: a cross-slice FK would couple the demo
slice's schema to four other slices and break independent deletion (e.g.
``DELETE /registry/runs/{id}`` must keep working while a workspace row still
references the run). E1 of the showcase-workspace initiative (umbrella #389,
epic #390).

E1 of the showcase-completion initiative (umbrella #406, epic #407) adds the
metadata + provenance backbone: lifecycle columns (``archived`` / ``pinned`` /
``notes`` / ``tags`` / ``config_schema_version``), the replay-provenance
column ``replayed_from_workspace_id`` -- ALSO a soft reference, deliberately
no ForeignKey, not even self-referential: ancestor rows must stay
independently deletable (metadata-only delete) without cascading to or
blocking descendants, so dangling lineage pointers are expected -- and six
documented JSONB story slots (``seed_overrides`` / ``user_scope`` /
``approval_events`` / ``rag_events`` / ``job_ids`` / ``phase_summaries``)
that stay NULL until their writer epic lands (#408-#412).

GOTCHA: SQLAlchemy reserves the declarative attribute name ``metadata``; the
JSONB columns are therefore named ``created_objects`` and ``result_summary``.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from sqlalchemy import CheckConstraint, Date, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import TimestampMixin

# Workspace lifecycle states -- guarded by a CHECK constraint. ``running`` is
# written at creation (before the first pipeline step executes); the finalize
# hook settles the row to ``completed`` or ``failed``.
WORKSPACE_STATUS_RUNNING = "running"
WORKSPACE_STATUS_COMPLETED = "completed"
WORKSPACE_STATUS_FAILED = "failed"


class ShowcaseWorkspace(TimestampMixin, Base):
    """A preserved showcase run.

    Attributes:
        id: Surrogate primary key.
        workspace_id: Unique external identifier (UUID hex, 32 chars).
        name: Optional human label from ``DemoRunRequest.workspace_name``.
        status: Lifecycle state -- running / completed / failed (CHECK-constrained).
        seed: Seeder seed the run was started with (replay input).
        scenario: Seeder scenario preset value (replay input).
        reset: Whether the run wiped the database before seeding (replay input).
        skip_seed: Whether the run skipped the seed step (replay input).
        store_id: Showcase grain store id; NULL when the run failed early.
        product_id: Showcase grain product id; NULL when the run failed early.
        date_start: Seeded data window start; NULL when unknown.
        date_end: Seeded data window end; NULL when unknown.
        created_objects: Soft-reference ids of everything the run created (JSONB).
        result_summary: Winner / WAPE / wall-clock display payload (JSONB).
        run_config: Replay-input run config -- model set + backtest knobs (E4 #410); NULL on defaults.
        archived: Operator curation flag -- archived rows still list in E1.
        pinned: Operator curation flag -- no behavioral semantics in E1.
        notes: Free-text operator annotation (capped at the Pydantic boundary).
        tags: Queryable JSONB string array, GIN-indexed (scenario_plan pattern).
        config_schema_version: Version of the config + story-slot schema (starts at 1).
        replayed_from_workspace_id: Soft reference to the replayed source row.
        seed_overrides: Story slot (E3 #409 writes) -- NULL until written.
        user_scope: Story slot (E3 #409 writes) -- NULL until written.
        approval_events: Story slot (E5 #411 writes) -- NULL until written.
        rag_events: Story slot (E5 #411 writes) -- NULL until written.
        job_ids: Story slot (later parallel epic writes) -- NULL until written.
        phase_summaries: Story slot (later parallel epic writes) -- NULL until written.
    """

    __tablename__ = "showcase_workspace"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=WORKSPACE_STATUS_RUNNING, nullable=False, index=True
    )
    # Run configuration -- replay inputs (E4 restore/replay reads these verbatim).
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    scenario: Mapped[str] = mapped_column(String(40), nullable=False)
    reset: Mapped[bool] = mapped_column(nullable=False, default=False)
    skip_seed: Mapped[bool] = mapped_column(nullable=False, default=True)
    # Grain + window discovered by the status/seed steps (NULL on early failure).
    store_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_start: Mapped[_dt.date | None] = mapped_column(Date, nullable=True)
    date_end: Mapped[_dt.date | None] = mapped_column(Date, nullable=True)
    # Everything the run created -- flexible JSONB of soft references (see the
    # module docstring for the deliberate no-FK decision).
    created_objects: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # winner_model_type / winner_wape / wall_clock_s -- display payload.
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # E4 (#410) -- replay-input run config (NOT an E1 story slot; see
    # DOMAIN_MODEL.md D1). Shape: {"train_model_types": [...], "backtest": {...}}
    # via model_dump(mode="json"); NULL when the run used default config.
    # Written by create_workspace at insert time (a replay input known before
    # step 1, like seed/scenario); consumed by Load/Replay. config_schema_version
    # is deliberately NOT bumped -- it versions the STORY-SLOT schema; run_config
    # presence is NULL-detectable and carries its own documented shape.
    run_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # ── E1 (#407) — lifecycle metadata ────────────────────────────────────
    # Orthogonal to ``status`` (which the pipeline owns): archive/pin are
    # operator curation flags, PATCH-mutable, default false.
    archived: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    pinned: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    # Free-text operator annotation; length capped at the Pydantic boundary (2000).
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Queryable JSONB string array -- EXACT scenario_plan.tags pattern
    # (app/features/scenarios/models.py); GIN-indexed below.
    tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # Version of the workspace config + story-slot schema (umbrella #406
    # junk-drawer mitigation). Bump the ORM default when a slot shape changes.
    # E5 (#411) bumped 1 -> 2: it widened the approval_events.decision enum
    # (+timed_out), added "probe" to rag_events.event, and added the additive
    # entry keys documented below. server_default stays text("1") -- no
    # migration; old rows legitimately read 1.
    config_schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, server_default=text("1")
    )

    # ── E1 (#407) — replay provenance ─────────────────────────────────────
    # SOFT reference to the workspace this run replayed (uuid4().hex of the
    # source row). Deliberately NO ForeignKey -- not even self-referential:
    # ancestor rows must stay independently deletable (metadata-only delete),
    # and dangling lineage pointers are expected, like every created_objects id.
    replayed_from_workspace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # ── E1 (#407) — documented JSONB story slots ──────────────────────────
    # Six dedicated nullable JSONB columns (precedent: created_objects /
    # result_summary). NULL = "slot never written" (distinct from empty).
    # E1 writes NONE of them; documented schema per slot (authoritative copy
    # in docs/_base/DOMAIN_MODEL.md):
    #   seed_overrides   (E3 #409 writes) — dict: the curated seeder-override
    #                    payload from the start frame, stored verbatim
    #                    (model_dump(mode="json")); replay echoes it.
    #   user_scope       (E3 #409 writes) — dict: operator-selected focus,
    #                    {"store_id": int, "product_id": int} (additive keys
    #                    allowed later).
    #   approval_events  (E5 #411 writes — schema v2) — list[dict], append-only:
    #                    {"action_id": str, "tool_name": str,
    #                     "decision": "approved"|"rejected"|"timed_out",
    #                     "decided_at": iso8601-str, "session_id": str,
    #                     # v2 additive (config_schema_version >= 2):
    #                     "auto_approved": bool, "reason": str|None,
    #                     "execution_status": str|None,
    #                     "tool_call_summary": {"description": str,
    #                         "arguments_keys": list[str]},
    #                     "transcript_summary": str, "tokens_used": int,
    #                     "tool_calls_count": int}.
    #   rag_events       (E5 #411 writes — schema v2) — list[dict], append-only:
    #                    {"event": "probe"|"index"|"retrieve"|"skip",
    #                     "status": "pass"|"warn"|"skip", "detail": str,
    #                     "count": int, "occurred_at": iso8601-str,
    #                     "provider": str|None, "reachable": bool|None}.
    #   job_ids          (later parallel epic) — list[str]: job / batch
    #                    sub-job ids the run submitted (soft references).
    #   phase_summaries  (later parallel epic) — list[dict], one per phase:
    #                    {"phase_name": str, "status": "pass"|"fail"|"warn"|"skip",
    #                     "steps": int, "duration_ms": float}.
    seed_overrides: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    user_scope: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    approval_events: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    rag_events: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    job_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    phase_summaries: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_showcase_workspace_status",
        ),
        Index("ix_showcase_workspace_status_created", "status", "created_at"),
        # E1 (#407) — tag containment queries (scenario_plan GIN precedent).
        Index("ix_showcase_workspace_tags_gin", "tags", postgresql_using="gin"),
        # E1 (#407) — lineage lookups ("which runs replayed this workspace?").
        Index("ix_showcase_workspace_replayed_from", "replayed_from_workspace_id"),
    )
