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

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import TimestampMixin


class ModelSelectionStatus(str, Enum):
    """Lifecycle states of a selection run.

    Transitions:
    - PENDING -> RUNNING -> {COMPLETED, PARTIAL, FAILED}
    - PARTIAL fires when >=1 candidate succeeded AND >=1 candidate failed.
    - FAILED fires when availability is unusable (fail-fast) OR every
      candidate's backtest errored (no valid winner).
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


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
    completed_at: Mapped[_dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'partial', 'failed')",
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
