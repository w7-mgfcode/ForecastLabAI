"""Batch runner ORM models.

Two tables — ``batch_job`` (parent) and ``batch_job_item`` (child) — track a
portfolio batch and its expanded (store, product, model) work items. Mirrors
``app/features/jobs/models.py`` for shape: ``TimestampMixin`` + ``Base``,
string ``Enum``s, ``CheckConstraint`` in ``__table_args__``, JSONB columns
for flexible per-item config and per-fold metrics.

Forward-compat columns owned by the MVP (per PRP-33 § "Cross-Slice
Coordination Matrix") so the four downstream PRPs ship without a schema
migration:

- ``batch_job.running_items`` / ``cancelled_items`` — downstream-1 (parallel)
- ``batch_job.max_parallel`` — downstream-1 (MVP runner ignores)
- ``batch_job.default_child_priority`` — downstream-2 (priority queue)
- ``batch_job_item.priority`` — downstream-2 (MVP NORMAL only)

The partial picker index ``ix_batch_job_item_picker`` (``WHERE status =
'pending'``) is created in the Alembic migration, not here — SQLAlchemy's
``Index()`` cannot express a portable partial predicate.
"""

from __future__ import annotations

import datetime as _dt
from enum import Enum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import TimestampMixin


class BatchStatus(str, Enum):
    """Parent batch lifecycle states.

    Transitions:
    - PENDING -> RUNNING -> {COMPLETED, FAILED, PARTIAL}
    - PARTIAL fires when >=1 item succeeded AND >=1 item failed.
    - CANCELLED is reserved for downstream-1 (parallel) — MVP never writes it.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


class BatchOperation(str, Enum):
    """Batch operation kinds.

    TRAIN_BACKTEST_REGISTER chains three child JobService.create_job calls
    per item; the other three map 1:1 to a single JobType.
    """

    TRAIN = "train"
    PREDICT = "predict"
    BACKTEST = "backtest"
    TRAIN_BACKTEST_REGISTER = "train_backtest_register"


class BatchItemStatus(str, Enum):
    """Per-item lifecycle states.

    Transitions mirror ``JobStatus`` minus PARTIAL (only the parent settles
    to PARTIAL). CANCELLED is reserved for downstream-1.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


VALID_BATCH_TRANSITIONS: dict[BatchStatus, set[BatchStatus]] = {
    BatchStatus.PENDING: {BatchStatus.RUNNING, BatchStatus.CANCELLED},
    BatchStatus.RUNNING: {
        BatchStatus.COMPLETED,
        BatchStatus.FAILED,
        BatchStatus.PARTIAL,
        BatchStatus.CANCELLED,
    },
    BatchStatus.COMPLETED: set(),
    BatchStatus.FAILED: set(),
    BatchStatus.PARTIAL: set(),
    BatchStatus.CANCELLED: set(),
}

VALID_BATCH_ITEM_TRANSITIONS: dict[BatchItemStatus, set[BatchItemStatus]] = {
    BatchItemStatus.PENDING: {BatchItemStatus.RUNNING, BatchItemStatus.CANCELLED},
    BatchItemStatus.RUNNING: {BatchItemStatus.COMPLETED, BatchItemStatus.FAILED},
    BatchItemStatus.COMPLETED: set(),
    BatchItemStatus.FAILED: set(),
    BatchItemStatus.CANCELLED: set(),
}


class BatchJob(TimestampMixin, Base):
    """Parent batch record — one row per submission.

    ``scope``, ``model_configs``, ``params``, and ``result_summary`` are all
    JSONB so the four downstream PRPs can add keys without a schema
    migration. ``params`` carries the original submit request verbatim;
    ``scope`` and ``model_configs`` are split out so they remain
    independently queryable from SQL without a JSONB path expression.
    """

    __tablename__ = "batch_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    operation: Mapped[str] = mapped_column(String(30), index=True)
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    model_configs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=BatchStatus.PENDING.value, index=True)
    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Forward-compat — downstream-1 (parallel) maintains these counters; MVP
    # leaves them at 0 except via the settle aggregate.
    running_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancelled_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Forward-compat — downstream-1 reads max_parallel; MVP runner ignores it.
    max_parallel: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    # Forward-compat — downstream-2 reads default_child_priority; MVP only writes NORMAL (0).
    default_child_priority: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[_dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[_dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'partial', 'cancelled')",
            name="ck_batch_job_valid_status",
        ),
        CheckConstraint(
            "operation IN ('train', 'predict', 'backtest', 'train_backtest_register')",
            name="ck_batch_job_valid_operation",
        ),
        CheckConstraint(
            "default_child_priority BETWEEN -1 AND 2",
            name="ck_batch_job_priority_band",
        ),
        Index("ix_batch_job_status_created", "status", "created_at"),
    )


class BatchJobItem(TimestampMixin, Base):
    """Child batch item — one row per (store, product, model_type) triple.

    ``params`` is frozen at expansion time; the runner reads from it on every
    ``_execute_item`` call, never mutates it. ``metrics`` carries the pinned
    five-key JSONB ``{wape, smape, mae, bias, sample_size}`` for backtest
    items; nullable for predict-only items and for fold runs that produced
    NaN on a zero-actuals window.
    """

    __tablename__ = "batch_job_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    batch_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("batch_job.batch_id", ondelete="CASCADE"),
        index=True,
    )
    store_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    model_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(
        String(20), default=BatchItemStatus.PENDING.value, index=True
    )
    # Forward-compat — downstream-2 reads priority; MVP only writes NORMAL (0).
    priority: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    child_job_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    child_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
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
            name="ck_batch_job_item_valid_status",
        ),
        CheckConstraint(
            "priority BETWEEN -1 AND 2",
            name="ck_batch_job_item_priority_band",
        ),
        Index("ix_batch_job_item_batch_status", "batch_id", "status"),
        Index("ix_batch_job_item_metrics_gin", "metrics", postgresql_using="gin"),
        # Partial picker index (postgresql_where) lives in the Alembic migration —
        # SQLAlchemy's Index() lacks a portable partial-predicate kwarg.
    )
