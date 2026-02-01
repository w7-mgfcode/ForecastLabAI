"""Pydantic schemas for job endpoints.

These schemas are optimized for LLM tool-calling with rich descriptions
that help agents understand how to orchestrate jobs.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.features.jobs.models import JobStatus, JobType

# =============================================================================
# Job Create Schema
# =============================================================================


class JobCreate(BaseModel):
    """Request schema for creating a new job.

    Jobs are the primary way to execute ForecastOps operations.
    Each job type has specific required parameters.

    **Job Types and Required Params**:

    - **train**: Train a forecasting model
      - `model_type`: Required - 'naive', 'seasonal_naive', 'linear_regression', etc.
      - `store_id`: Required - Store ID from /dimensions/stores
      - `product_id`: Required - Product ID from /dimensions/products
      - `start_date`: Required - Training data start (YYYY-MM-DD)
      - `end_date`: Required - Training data end (YYYY-MM-DD)
      - Additional model-specific parameters

    - **predict**: Generate predictions
      - `run_id`: Required - Model run ID from previous train job
      - `horizon`: Optional - Number of days to forecast (default 14, max 90)

    - **backtest**: Run cross-validation
      - `model_type`: Required - Model type to evaluate
      - `store_id`: Required - Store ID
      - `product_id`: Required - Product ID
      - `start_date`: Required - Data start date
      - `end_date`: Required - Data end date
      - `n_splits`: Optional - Number of CV folds (default 5, max 20)
      - `test_size`: Optional - Test window size (default 14)
    """

    job_type: JobType = Field(
        ...,
        description="Type of job to execute: 'train', 'predict', or 'backtest'.",
    )
    params: dict[str, Any] = Field(
        ...,
        description="Job-specific parameters. See job type documentation for required fields.",
    )


# =============================================================================
# Job Response Schemas
# =============================================================================


class JobResponse(BaseModel):
    """Response schema for a single job.

    Contains job metadata, status, and results.
    """

    model_config = ConfigDict(from_attributes=True)

    job_id: str = Field(
        ...,
        description="Unique job identifier (32-char hex). Use for polling status.",
    )
    job_type: JobType = Field(
        ...,
        description="Type of job: 'train', 'predict', or 'backtest'.",
    )
    status: JobStatus = Field(
        ...,
        description="Current job status: 'pending', 'running', 'completed', 'failed', or 'cancelled'.",
    )
    params: dict[str, Any] = Field(
        ...,
        description="Job configuration parameters as submitted.",
    )
    result: dict[str, Any] | None = Field(
        None,
        description="Job result (null until completed). "
        "Structure depends on job_type.",
    )
    error_message: str | None = Field(
        None,
        description="Error details if status='failed'. "
        "Use for troubleshooting.",
    )
    error_type: str | None = Field(
        None,
        description="Exception class name if status='failed'. "
        "Helps identify error category.",
    )
    run_id: str | None = Field(
        None,
        description="Model run ID for train/backtest jobs. "
        "Use with /registry/runs endpoint.",
    )
    started_at: datetime | None = Field(
        None,
        description="When job execution started. Null if still pending.",
    )
    completed_at: datetime | None = Field(
        None,
        description="When job finished. Null if still running or pending.",
    )
    created_at: datetime = Field(
        ...,
        description="When job was created.",
    )
    updated_at: datetime = Field(
        ...,
        description="When job was last updated.",
    )


# =============================================================================
# Job List Response
# =============================================================================


class JobListResponse(BaseModel):
    """Paginated list of jobs with filtering metadata.

    Use pagination parameters (page, page_size) to navigate large result sets.
    Filtering by job_type or status reduces the result set before pagination.
    """

    jobs: list[JobResponse] = Field(
        ...,
        description="Array of job records for the current page. "
        "Empty if no jobs match the filters.",
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of jobs matching the applied filters. "
        "Use to calculate total pages: ceil(total / page_size).",
    )
    page: int = Field(
        ...,
        ge=1,
        description="Current page number (1-indexed). First page is 1.",
    )
    page_size: int = Field(
        ...,
        ge=1,
        description="Number of jobs per page. Maximum is 100.",
    )
