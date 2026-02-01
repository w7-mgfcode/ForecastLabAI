"""Test fixtures for jobs module."""

from datetime import UTC, datetime

import pytest

from app.features.jobs.models import JobStatus, JobType
from app.features.jobs.schemas import (
    JobCreate,
    JobResponse,
)


@pytest.fixture
def sample_train_job_create() -> JobCreate:
    """Create sample train job request."""
    return JobCreate(
        job_type=JobType.TRAIN,
        params={
            "model_type": "naive",
            "store_id": 1,
            "product_id": 1,
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
        },
    )


@pytest.fixture
def sample_predict_job_create() -> JobCreate:
    """Create sample predict job request."""
    return JobCreate(
        job_type=JobType.PREDICT,
        params={
            "run_id": "abc123def4567890123456789012abcd",
            "horizon": 14,
        },
    )


@pytest.fixture
def sample_backtest_job_create() -> JobCreate:
    """Create sample backtest job request."""
    return JobCreate(
        job_type=JobType.BACKTEST,
        params={
            "model_type": "naive",
            "store_id": 1,
            "product_id": 1,
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
            "n_splits": 5,
            "test_size": 14,
        },
    )


@pytest.fixture
def sample_job_response() -> JobResponse:
    """Create sample job response."""
    now = datetime.now(UTC)
    return JobResponse(
        job_id="abc123def4567890123456789012abcd",
        job_type=JobType.TRAIN,
        status=JobStatus.COMPLETED,
        params={
            "model_type": "naive",
            "store_id": 1,
            "product_id": 1,
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
        },
        result={
            "run_id": "xyz789abc123def4567890123456abcd",
            "model_type": "naive",
            "training_samples": 180,
            "training_time_ms": 50.5,
        },
        error_message=None,
        error_type=None,
        run_id="xyz789abc123def4567890123456abcd",
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )
