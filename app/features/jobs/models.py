"""Job ORM model for async-ready task tracking.

This module defines the Job model for tracking background jobs
such as training, prediction, and backtesting operations.

CRITICAL: Uses PostgreSQL JSONB for flexible params and results.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import TimestampMixin


class JobType(str, Enum):
    """Types of jobs that can be executed.

    Each type corresponds to a specific ForecastOps operation:
    - TRAIN: Train a forecasting model
    - PREDICT: Generate predictions from a trained model
    - BACKTEST: Run time-based cross-validation
    """

    TRAIN = "train"
    PREDICT = "predict"
    BACKTEST = "backtest"


class JobStatus(str, Enum):
    """Job lifecycle states.

    State transitions:
    - PENDING -> RUNNING -> COMPLETED | FAILED
    - PENDING -> CANCELLED (via DELETE endpoint)
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Valid state transitions for job status
VALID_JOB_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.PENDING: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING: {JobStatus.COMPLETED, JobStatus.FAILED},
    JobStatus.COMPLETED: set(),  # Terminal state
    JobStatus.FAILED: set(),  # Terminal state
    JobStatus.CANCELLED: set(),  # Terminal state
}


class Job(TimestampMixin, Base):
    """Background job tracking model.

    CRITICAL: Stores job configuration and results as JSONB for flexibility.
    Jobs execute synchronously but API contracts are async-ready.

    Attributes:
        id: Primary key.
        job_id: Unique external identifier (UUID hex, 32 chars).
        job_type: Type of job (train, predict, backtest).
        status: Current lifecycle state.
        params: Job configuration as JSONB.
        result: Job result as JSONB (null until completed).
        error_message: Error details if status=FAILED.
        error_type: Exception class name if status=FAILED.
        started_at: When job execution started.
        completed_at: When job finished (success or failure).
        run_id: Link to model_run for train/backtest jobs.
    """

    __tablename__ = "job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    job_type: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.PENDING.value, index=True)

    # Job configuration (stored as JSONB for flexibility)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Result/error storage
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Timing
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Linkage to model run (for train/backtest jobs)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    __table_args__ = (
        # GIN index for JSONB containment queries
        Index("ix_job_params_gin", "params", postgresql_using="gin"),
        Index("ix_job_result_gin", "result", postgresql_using="gin"),
        # Composite index for common query patterns
        Index("ix_job_type_status", "job_type", "status"),
        # Constraint: valid status values
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_job_valid_status",
        ),
        # Constraint: valid job type values
        CheckConstraint(
            "job_type IN ('train', 'predict', 'backtest')",
            name="ck_job_valid_type",
        ),
    )
