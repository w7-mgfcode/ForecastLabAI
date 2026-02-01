"""Model registry ORM models for tracking runs and deployments.

This module defines:
- ModelRun: Registry entry for each model training run
- DeploymentAlias: Mutable pointers to successful runs

CRITICAL: Uses PostgreSQL JSONB for flexible metadata storage.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.models import TimestampMixin

if TYPE_CHECKING:
    pass


class RunStatus(str, Enum):
    """Valid states for a model run.

    State transitions:
    - PENDING -> RUNNING -> SUCCESS | FAILED
    - Any state except ARCHIVED -> ARCHIVED
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ARCHIVED = "archived"


class ModelRun(TimestampMixin, Base):
    """Model run registry entry.

    CRITICAL: Captures full experiment lineage for reproducibility.

    Attributes:
        id: Primary key.
        run_id: Unique external identifier (UUID hex, 32 chars).
        status: Current lifecycle state.
        model_type: Type of model (naive, seasonal_naive, etc.).
        model_config: Full model configuration as JSONB.
        feature_config: Feature engineering config as JSONB (nullable).
        data_window_start: Training data start date.
        data_window_end: Training data end date.
        store_id: Store ID for this run.
        product_id: Product ID for this run.
        metrics: Performance metrics as JSONB.
        artifact_uri: Relative path to artifact (from ARTIFACT_ROOT).
        artifact_hash: SHA-256 checksum of artifact.
        artifact_size_bytes: Size of artifact file.
        runtime_info: Python/library versions as JSONB.
        agent_context: Agent ID and session ID for traceability.
        git_sha: Optional git commit hash.
        config_hash: Hash of model_config for deduplication.
        error_message: Error details if status=FAILED.
        started_at: When run started.
        completed_at: When run completed (success or failed).
    """

    __tablename__ = "model_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default=RunStatus.PENDING.value, index=True)

    # Model configuration
    model_type: Mapped[str] = mapped_column(String(50), index=True)
    model_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    feature_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    config_hash: Mapped[str] = mapped_column(String(16), index=True)

    # Data window
    data_window_start: Mapped[datetime.date] = mapped_column(Date)
    data_window_end: Mapped[datetime.date] = mapped_column(Date)
    store_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)

    # Metrics
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Artifact info
    artifact_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    artifact_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # SHA-256
    artifact_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Environment & lineage
    runtime_info: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    agent_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    git_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # Timing
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationship to aliases
    aliases: Mapped[list[DeploymentAlias]] = relationship(back_populates="run")

    __table_args__ = (
        # GIN index for JSONB containment queries
        Index("ix_model_run_model_config_gin", "model_config", postgresql_using="gin"),
        Index("ix_model_run_metrics_gin", "metrics", postgresql_using="gin"),
        # Composite index for common query pattern
        Index("ix_model_run_store_product", "store_id", "product_id"),
        Index("ix_model_run_data_window", "data_window_start", "data_window_end"),
        # Constraint: valid status values
        CheckConstraint(
            "status IN ('pending', 'running', 'success', 'failed', 'archived')",
            name="ck_model_run_valid_status",
        ),
        # Constraint: data window validity
        CheckConstraint(
            "data_window_end >= data_window_start",
            name="ck_model_run_valid_data_window",
        ),
    )


class DeploymentAlias(TimestampMixin, Base):
    """Mutable pointer to a specific successful run.

    CRITICAL: Aliases provide stable references for deployment.

    Attributes:
        id: Primary key.
        alias_name: Unique alias name (e.g., 'production', 'staging-v2').
        run_id: Foreign key to the aliased run (internal ID).
        description: Optional description of this alias.
    """

    __tablename__ = "deployment_alias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alias_name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("model_run.id"), index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationship
    run: Mapped[ModelRun] = relationship(back_populates="aliases")

    __table_args__ = (UniqueConstraint("alias_name", name="uq_deployment_alias_name"),)
