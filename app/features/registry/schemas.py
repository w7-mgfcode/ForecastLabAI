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

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    """Run details response."""

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
