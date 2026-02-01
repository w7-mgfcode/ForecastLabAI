"""API routes for job orchestration.

These endpoints enable LLM agents and users to create and monitor
training, prediction, and backtesting jobs.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.features.jobs.models import JobStatus, JobType
from app.features.jobs.schemas import (
    JobCreate,
    JobListResponse,
    JobResponse,
)
from app.features.jobs.service import JobService

logger = get_logger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


# =============================================================================
# Job Creation
# =============================================================================


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create and execute a job",
    description="""
Create and execute a forecasting job (train, predict, or backtest).

**Important**: Jobs currently execute synchronously but return 202 Accepted
for async-ready API contracts. The response includes the job result.

**Job Types**:

### Train Job
Train a forecasting model on historical data.

Required params:
- `model_type`: Model type (naive, seasonal_naive, linear_regression, etc.)
- `store_id`: Store ID (from /dimensions/stores)
- `product_id`: Product ID (from /dimensions/products)
- `start_date`: Training start date (YYYY-MM-DD)
- `end_date`: Training end date (YYYY-MM-DD)

Example:
```json
{
  "job_type": "train",
  "params": {
    "model_type": "seasonal_naive",
    "store_id": 1,
    "product_id": 1,
    "start_date": "2024-01-01",
    "end_date": "2024-06-30",
    "period": 7
  }
}
```

### Predict Job
Generate predictions from a trained model.

Required params:
- `run_id`: Model run ID from previous train job

Optional params:
- `horizon`: Forecast horizon in days (default 14, max 90)

Example:
```json
{
  "job_type": "predict",
  "params": {
    "run_id": "abc123...",
    "horizon": 30
  }
}
```

### Backtest Job
Run time-based cross-validation to evaluate model performance.

Required params:
- `model_type`: Model type to evaluate
- `store_id`: Store ID
- `product_id`: Product ID
- `start_date`: Data start date
- `end_date`: Data end date

Optional params:
- `n_splits`: Number of CV folds (default 5, max 20)
- `test_size`: Test window size in days (default 14)
- `gap`: Gap between train and test (default 0)

Example:
```json
{
  "job_type": "backtest",
  "params": {
    "model_type": "linear_regression",
    "store_id": 1,
    "product_id": 1,
    "start_date": "2024-01-01",
    "end_date": "2024-06-30",
    "n_splits": 5,
    "test_size": 14
  }
}
```

**Response**:
Returns the job with status and result. For completed jobs, check the `result` field.
For failed jobs, check `error_message` and `error_type`.
""",
)
async def create_job(
    job_create: JobCreate,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """Create and execute a job.

    Args:
        job_create: Job creation request.
        db: Database session.

    Returns:
        Job response with status and result.
    """
    service = JobService()
    return await service.create_job(db=db, job_create=job_create)


# =============================================================================
# Job Listing
# =============================================================================


@router.get(
    "",
    response_model=JobListResponse,
    summary="List jobs",
    description="""
List jobs with pagination and optional filtering.

**Pagination**:
- Results are paginated with 1-indexed pages
- Default: 20 items per page, maximum: 100
- Use `total` in response to calculate total pages

**Filtering**:
- `job_type`: Filter by job type (train, predict, backtest)
- `status`: Filter by status (pending, running, completed, failed, cancelled)

**Example Use Cases**:
1. List all jobs: `GET /jobs`
2. List failed jobs: `GET /jobs?status=failed`
3. List train jobs: `GET /jobs?job_type=train`
4. Paginate: `GET /jobs?page=2&page_size=10`
""",
)
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Jobs per page (max 100)"),
    job_type: JobType | None = Query(None, description="Filter by job type"),
    status: JobStatus | None = Query(None, description="Filter by status"),
) -> JobListResponse:
    """List jobs with pagination and filtering.

    Args:
        db: Database session.
        page: Page number (1-indexed).
        page_size: Number of jobs per page.
        job_type: Filter by job type (optional).
        status: Filter by status (optional).

    Returns:
        Paginated list of jobs.
    """
    service = JobService()
    return await service.list_jobs(
        db=db,
        page=page,
        page_size=page_size,
        job_type=job_type,
        status=status,
    )


# =============================================================================
# Single Job Operations
# =============================================================================


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job by ID",
    description="""
Get details for a specific job by its unique ID.

**Use Case**: Poll job status after creation or retrieve job results.

**Response Fields**:
- `status`: Current status (pending, running, completed, failed, cancelled)
- `result`: Job output (null until completed)
- `error_message`: Error details (if failed)
- `run_id`: Model run ID for train/backtest jobs

**Error Handling**:
- Returns 404 if job_id doesn't exist
""",
)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """Get job details by ID.

    Args:
        job_id: Unique job identifier.
        db: Database session.

    Returns:
        Job details.

    Raises:
        HTTPException: If job not found.
    """
    service = JobService()
    result = await service.get_job(db=db, job_id=job_id)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}. "
            "Use GET /jobs to list available jobs.",
        )

    return result


@router.delete(
    "/{job_id}",
    response_model=JobResponse,
    summary="Cancel a pending job",
    description="""
Cancel a job that is still in 'pending' status.

**Important**: Only pending jobs can be cancelled. Running, completed,
failed, and cancelled jobs cannot be cancelled.

**Error Handling**:
- Returns 404 if job_id doesn't exist
- Returns 400 if job is not in pending status
""",
)
async def cancel_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """Cancel a pending job.

    Args:
        job_id: Unique job identifier.
        db: Database session.

    Returns:
        Updated job with cancelled status.

    Raises:
        HTTPException: If job not found or cannot be cancelled.
    """
    service = JobService()

    try:
        result = await service.cancel_job(db=db, job_id=job_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}. "
            "Use GET /jobs to list available jobs.",
        )

    return result
