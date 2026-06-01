"""ORM models for the Forecast Champion Selector slice (issue #353).

One table — ``model_selection_run`` — records one ``POST /model-selection/run``
invocation as an auditable artifact. Mirrors ``app/features/batch/models.py``
for shape: ``TimestampMixin`` + ``Base``, a string status column with an
allow-list ``CheckConstraint`` in ``__table_args__``, and JSONB columns for the
flexible audit snapshots (candidate configs, policy, availability, ranking,
per-candidate results, chart data, winner metrics, forecast summary, business
summary).
"""

from __future__ import annotations

import datetime as _dt
from enum import Enum
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import TimestampMixin


class ModelSelectionStatus(str, Enum):
    """Lifecycle states of a selection run.

    Transitions:
    - PENDING -> RUNNING -> {COMPLETED, PARTIAL, FAILED, CANCELLED}
    - PARTIAL fires when >=1 candidate succeeded AND >=1 candidate failed/cancelled.
    - FAILED fires when availability is unusable (fail-fast) OR every
      candidate's backtest errored (no valid winner).
    - CANCELLED (Slice B) fires when a cancel drained before any candidate
      reached a non-cancelled terminal state.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Statuses a selection run cannot transition out of — the DELETE-route 409 set
# (Slice B). Mirrors ``batch.models.TERMINAL_BATCH_STATES``.
TERMINAL_SELECTION_STATES: frozenset[str] = frozenset(
    {
        ModelSelectionStatus.COMPLETED.value,
        ModelSelectionStatus.PARTIAL.value,
        ModelSelectionStatus.FAILED.value,
        ModelSelectionStatus.CANCELLED.value,
    }
)


class CandidateStatus(str, Enum):
    """Per-candidate execution states inside an async selection run (Slice B)."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelSelectionRun(TimestampMixin, Base):
    """A single champion-selection run over one (store, product) pair.

    ``candidate_results`` carries the full per-candidate detail (incl. fold
    actuals/predictions) so a ``GET`` rebuilds the same ``chart_data`` payload
    the originating ``/run`` returned. ``chart_data`` caches the computed
    chart-ready payload so the read path needs no recomputation.
    """

    __tablename__ = "model_selection_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    selection_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    store_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    start_date: Mapped[_dt.date] = mapped_column(Date)
    end_date: Mapped[_dt.date] = mapped_column(Date)
    forecast_horizon: Mapped[int] = mapped_column(Integer)
    ranking_metric: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(
        String(20), default=ModelSelectionStatus.PENDING.value, index=True
    )
    candidate_models: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    availability_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ranking_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    candidate_results: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    chart_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    winner_model_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    winner_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    final_model_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    forecast_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    business_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Slice B (async) — set when the run starts executing; the four count
    # columns cache the FINAL per-status candidate tally written once at settle
    # (live progress is derived from a GROUP BY over the child rows).
    started_at: Mapped[_dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_candidates: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed_candidates: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_candidates: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cancelled_candidates: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed_at: Mapped[_dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'partial', 'failed', 'cancelled')",
            name="ck_model_selection_run_valid_status",
        ),
        Index(
            "ix_model_selection_run_store_product_created",
            "store_id",
            "product_id",
            "created_at",
        ),
        Index("ix_model_selection_run_status_created", "status", "created_at"),
    )


class ModelSelectionCandidate(TimestampMixin, Base):
    """One candidate's async execution record inside a selection run (Slice B).

    Concurrent candidate tasks each write their OWN row in their OWN session —
    no shared-row write race. ``result`` carries the full ``CandidateResult``
    JSONB (incl. folds) on success; failed/cancelled candidates keep their row
    so they stay visible in the results UI. Mirrors ``batch.BatchJobItem``.
    """

    __tablename__ = "model_selection_candidate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    selection_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("model_selection_run.selection_id", ondelete="CASCADE"),
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer)  # submit order — stable display
    model_type: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=CandidateStatus.PENDING.value, index=True
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[_dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[_dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_model_selection_candidate_valid_status",
        ),
        Index(
            "ix_model_selection_candidate_selection_status",
            "selection_id",
            "status",
        ),
    )
