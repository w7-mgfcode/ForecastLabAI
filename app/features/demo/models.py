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

GOTCHA: SQLAlchemy reserves the declarative attribute name ``metadata``; the
JSONB columns are therefore named ``created_objects`` and ``result_summary``.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from sqlalchemy import CheckConstraint, Date, Index, Integer, String, text
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

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_showcase_workspace_status",
        ),
        Index("ix_showcase_workspace_status_created", "status", "created_at"),
    )
