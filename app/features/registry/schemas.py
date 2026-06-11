"""Pydantic schemas for registry API contracts.

Schemas are designed to be:
- Immutable (frozen=True) for reproducibility
- Validated for data integrity
- Compatible with SQLAlchemy models via from_attributes
"""

from __future__ import annotations

import hashlib
import json
from datetime import date as date_type
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

# ``ModelFamily`` / ``model_family_for`` live in ``app/shared/model_taxonomy``
# (#268) so this module never imports from another feature slice. Pydantic v2
# resolves a ``@computed_field``'s return-type annotation at schema-build time,
# so ``ModelFamily`` must be a real runtime import (never TYPE_CHECKING-gated).
from app.shared.model_taxonomy import ModelFamily, model_family_for


class RunStatus(str, Enum):
    """Run lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ARCHIVED = "archived"


# Valid state transitions
VALID_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.PENDING: {RunStatus.RUNNING, RunStatus.ARCHIVED},
    RunStatus.RUNNING: {RunStatus.SUCCESS, RunStatus.FAILED, RunStatus.ARCHIVED},
    RunStatus.SUCCESS: {RunStatus.ARCHIVED},
    RunStatus.FAILED: {RunStatus.ARCHIVED},
    RunStatus.ARCHIVED: set(),  # Terminal state
}


class RuntimeInfo(BaseModel):
    """Runtime environment snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    python_version: str
    sklearn_version: str | None = None
    numpy_version: str | None = None
    pandas_version: str | None = None
    joblib_version: str | None = None


class AgentContext(BaseModel):
    """Agent context for autonomous run traceability."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str | None = None
    session_id: str | None = None


class RunCreate(BaseModel):
    """Request to create a new run."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    model_type: str = Field(..., min_length=1, max_length=50)
    model_config_data: dict[str, Any] = Field(..., alias="model_config")
    feature_config: dict[str, Any] | None = None
    data_window_start: date_type
    data_window_end: date_type
    store_id: int = Field(..., ge=1)
    product_id: int = Field(..., ge=1)
    agent_context: AgentContext | None = None
    git_sha: str | None = Field(None, max_length=40)
    runtime_info_extras: dict[str, Any] | None = Field(
        default=None,
        description=(
            "PRP-36 — optional caller-supplied extras merged INTO the runtime "
            "info captured by the service (Python/sklearn versions). The "
            "intended payload is the V2 metadata the forecasting service "
            "wrote to the model bundle: feature_frame_version, "
            "feature_groups, feature_safety_classes, feature_pinned_constants. "
            "Caller-supplied keys win over service-captured keys."
        ),
    )

    @field_validator("data_window_end")
    @classmethod
    def validate_data_window(cls, v: date_type, info: object) -> date_type:
        """Ensure data_window_end >= data_window_start."""
        data = getattr(info, "data", {})
        if "data_window_start" in data and v < data["data_window_start"]:
            raise ValueError("data_window_end must be >= data_window_start")
        return v

    def compute_config_hash(self) -> str:
        """Compute deterministic hash of model configuration.

        Returns:
            16-character hex string hash of config JSON.
        """
        config_json = json.dumps(self.model_config_data, sort_keys=True, default=str)
        return hashlib.sha256(config_json.encode()).hexdigest()[:16]


class RunUpdate(BaseModel):
    """Request to update a run."""

    model_config = ConfigDict(extra="forbid")

    status: RunStatus | None = None
    metrics: dict[str, Any] | None = None
    artifact_uri: str | None = None
    artifact_hash: str | None = None
    artifact_size_bytes: int | None = Field(None, ge=0)
    error_message: str | None = Field(None, max_length=2000)


class RunResponse(BaseModel):
    """Run details response.

    ``model_family`` is a computed field derived from ``model_type`` at
    serialization time — no DB column, no Alembic migration, no backfill.
    See ``app/shared/model_taxonomy.py`` for the canonical map. Unknown model
    types log a warning and return ``ModelFamily.BASELINE``.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    run_id: str
    status: RunStatus
    model_type: str
    model_config_data: dict[str, Any] = Field(
        ..., alias="model_config", serialization_alias="model_config"
    )
    feature_config: dict[str, Any] | None = None
    config_hash: str
    data_window_start: date_type
    data_window_end: date_type
    store_id: int
    product_id: int
    metrics: dict[str, Any] | None = None
    artifact_uri: str | None = None
    artifact_hash: str | None = None
    artifact_size_bytes: int | None = None
    runtime_info: dict[str, Any] | None = None
    agent_context: dict[str, Any] | None = None
    git_sha: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def model_family(self) -> ModelFamily:
        """Computed family label derived from ``model_type``."""
        return model_family_for(self.model_type)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def feature_frame_version(self) -> int | None:
        """PRP-36 — V1 (1) or V2 (2), read from ``runtime_info`` JSONB.

        ``None`` for runs that pre-date PRP-35 / PRP-36 and never wrote
        the key. Plain Python ``int`` type — no cross-slice import.
        """
        if not self.runtime_info:
            return None
        value = self.runtime_info.get("feature_frame_version")
        if isinstance(value, int):
            return value
        return None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def feature_groups(self) -> dict[str, list[str]] | None:
        """PRP-36 — V2 per-group canonical column manifest, read from ``runtime_info``.

        ``None`` for V1 runs (the key is only populated when training
        with feature_frame_version=2) and for runs that pre-date PRP-35.
        """
        if not self.runtime_info:
            return None
        value = self.runtime_info.get("feature_groups")
        if isinstance(value, dict):
            return value
        return None


class RunListResponse(BaseModel):
    """Paginated list of runs."""

    runs: list[RunResponse]
    total: int
    page: int
    page_size: int


class AliasCreate(BaseModel):
    """Request to create/update an alias."""

    model_config = ConfigDict(extra="forbid")

    alias_name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9\-_]*$")
    run_id: str
    description: str | None = Field(None, max_length=500)


class AliasResponse(BaseModel):
    """Alias details response."""

    model_config = ConfigDict(from_attributes=True)

    alias_name: str
    run_id: str
    run_status: RunStatus
    model_type: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class RunCompareResponse(BaseModel):
    """Comparison of two runs."""

    run_a: RunResponse
    run_b: RunResponse
    config_diff: dict[str, Any]  # Keys that differ
    metrics_diff: dict[str, dict[str, float | None]]  # {metric: {a: val, b: val, diff: val}}
