"""Service layer for job operations.

Provides job creation, execution, and tracking.
Jobs execute synchronously but API contracts are async-ready.

CRITICAL: All job operations are logged for auditability.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.features.jobs.models import (
    VALID_JOB_TRANSITIONS,
    Job,
    JobStatus,
    JobType,
)
from app.features.jobs.schemas import (
    JobCreate,
    JobListResponse,
    JobResponse,
)

logger = get_logger(__name__)


class JobService:
    """Service for managing background jobs.

    Provides job creation, execution, and status tracking.
    Jobs execute synchronously but contracts are async-ready.
    """

    def __init__(self) -> None:
        """Initialize job service."""
        self.settings = get_settings()

    async def create_job(
        self,
        db: AsyncSession,
        job_create: JobCreate,
    ) -> JobResponse:
        """Create and execute a new job.

        CRITICAL: Jobs execute synchronously. Future versions may
        support async execution via task queue.

        Args:
            db: Database session.
            job_create: Job creation request.

        Returns:
            Job response with status and result.
        """
        # Generate unique job ID
        job_id = uuid.uuid4().hex

        # Create job record
        job = Job(
            job_id=job_id,
            job_type=job_create.job_type.value,
            status=JobStatus.PENDING.value,
            params=job_create.params,
        )

        db.add(job)
        await db.commit()
        await db.refresh(job)

        logger.info(
            "jobs.job_created",
            job_id=job_id,
            job_type=job_create.job_type.value,
        )

        # Execute job synchronously
        job = await self._execute_job(db, job)

        return self._to_response(job)

    async def get_job(
        self,
        db: AsyncSession,
        job_id: str,
    ) -> JobResponse | None:
        """Get job by ID.

        Args:
            db: Database session.
            job_id: Unique job identifier.

        Returns:
            Job response or None if not found.
        """
        stmt = select(Job).where(Job.job_id == job_id)
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            return None

        return self._to_response(job)

    async def list_jobs(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        job_type: JobType | None = None,
        status: JobStatus | None = None,
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
        # Build base query
        stmt = select(Job)

        # Apply filters
        if job_type is not None:
            stmt = stmt.where(Job.job_type == job_type.value)
        if status is not None:
            stmt = stmt.where(Job.status == status.value)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await db.execute(count_stmt)
        total = count_result.scalar_one()

        # Apply pagination
        offset = (page - 1) * page_size
        stmt = stmt.order_by(Job.created_at.desc()).offset(offset).limit(page_size)

        # Execute query
        result = await db.execute(stmt)
        jobs = result.scalars().all()

        return JobListResponse(
            jobs=[self._to_response(job) for job in jobs],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def cancel_job(
        self,
        db: AsyncSession,
        job_id: str,
    ) -> JobResponse | None:
        """Cancel a pending job.

        Args:
            db: Database session.
            job_id: Unique job identifier.

        Returns:
            Updated job response or None if not found.

        Raises:
            ValueError: If job cannot be cancelled (not pending).
        """
        stmt = select(Job).where(Job.job_id == job_id)
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            return None

        current_status = JobStatus(job.status)

        # Validate transition
        if JobStatus.CANCELLED not in VALID_JOB_TRANSITIONS[current_status]:
            msg = f"Cannot cancel job in status '{current_status.value}'"
            raise ValueError(msg)

        job.status = JobStatus.CANCELLED.value
        job.completed_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(job)

        logger.info(
            "jobs.job_cancelled",
            job_id=job_id,
        )

        return self._to_response(job)

    async def _execute_job(
        self,
        db: AsyncSession,
        job: Job,
    ) -> Job:
        """Execute a job synchronously.

        CRITICAL: This is where job execution happens.
        Future versions may delegate to a task queue.

        Args:
            db: Database session.
            job: Job to execute.

        Returns:
            Updated job with results.
        """
        # Update status to RUNNING
        job.status = JobStatus.RUNNING.value
        job.started_at = datetime.now(UTC)
        await db.commit()

        logger.info(
            "jobs.job_started",
            job_id=job.job_id,
            job_type=job.job_type,
        )

        try:
            # Execute based on job type
            job_type = JobType(job.job_type)
            result: dict[str, Any]

            if job_type == JobType.TRAIN:
                result = await self._execute_train(db, job.params)
            elif job_type == JobType.PREDICT:
                result = await self._execute_predict(db, job.params)
            elif job_type == JobType.BACKTEST:
                result = await self._execute_backtest(db, job.params)
            else:
                msg = f"Unknown job type: {job_type}"
                raise ValueError(msg)

            # Update job with result
            job.status = JobStatus.COMPLETED.value
            job.result = result
            job.completed_at = datetime.now(UTC)

            # Capture run_id if available
            if "run_id" in result:
                job.run_id = result["run_id"]

            logger.info(
                "jobs.job_completed",
                job_id=job.job_id,
                job_type=job.job_type,
            )

        except Exception as e:
            # Update job with error
            job.status = JobStatus.FAILED.value
            job.error_message = str(e)[:2000]  # Truncate to fit column
            job.error_type = type(e).__name__
            job.completed_at = datetime.now(UTC)

            logger.error(
                "jobs.job_failed",
                job_id=job.job_id,
                job_type=job.job_type,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )

        await db.commit()
        await db.refresh(job)

        return job

    async def _execute_train(
        self,
        db: AsyncSession,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a train job.

        Args:
            db: Database session.
            params: Training parameters.

        Returns:
            Result dict with training info.
        """
        # Import here to avoid circular imports
        from datetime import date as date_type

        from app.features.forecasting.schemas import (
            MovingAverageModelConfig,
            NaiveModelConfig,
            SeasonalNaiveModelConfig,
        )
        from app.features.forecasting.service import ForecastingService

        service = ForecastingService()

        # Extract parameters
        model_type = params.get("model_type", "naive")
        store_id = params["store_id"]
        product_id = params["product_id"]
        start_date = params["start_date"]
        end_date = params["end_date"]

        # Parse dates if strings
        if isinstance(start_date, str):
            start_date = date_type.fromisoformat(start_date)
        if isinstance(end_date, str):
            end_date = date_type.fromisoformat(end_date)

        # Build model config based on model_type
        from app.features.forecasting.schemas import ModelConfig as ModelConfigType

        config: ModelConfigType
        if model_type == "naive":
            config = NaiveModelConfig()
        elif model_type == "seasonal_naive":
            season_length = params.get("season_length", 7)
            config = SeasonalNaiveModelConfig(season_length=season_length)
        elif model_type == "moving_average":
            window_size = params.get("window_size", 7)
            config = MovingAverageModelConfig(window_size=window_size)
        else:
            msg = f"Unsupported model_type: {model_type}"
            raise ValueError(msg)

        # Train model
        response = await service.train_model(
            db=db,
            store_id=store_id,
            product_id=product_id,
            train_start_date=start_date,
            train_end_date=end_date,
            config=config,
        )

        # Extract run_id from model_path (model_{run_id}.joblib format)
        # The model_path looks like: /path/to/model_{uuid}.joblib
        from pathlib import Path as PathLib

        model_basename = PathLib(response.model_path).stem  # Remove .joblib extension
        run_id = model_basename.replace("model_", "") if model_basename.startswith("model_") else model_basename

        return {
            "run_id": run_id,
            "model_type": response.model_type,
            "model_path": response.model_path,
            "config_hash": response.config_hash,
            "n_observations": response.n_observations,
            "train_start_date": str(response.train_start_date),
            "train_end_date": str(response.train_end_date),
            "store_id": response.store_id,
            "product_id": response.product_id,
            "duration_ms": response.duration_ms,
        }

    async def _execute_predict(
        self,
        db: AsyncSession,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a predict job.

        Args:
            db: Database session (unused for predict, but consistent interface).
            params: Prediction parameters.

        Returns:
            Result dict with predictions.
        """
        # Import here to avoid circular imports
        from pathlib import Path

        from app.features.forecasting.persistence import load_model_bundle
        from app.features.forecasting.service import ForecastingService

        # Note: db is unused here but kept for consistent interface
        _ = db

        service = ForecastingService()

        # Extract run_id from params (as documented in schema)
        run_id = params["run_id"]
        horizon = params.get("horizon", 14)

        # Resolve run_id to model_path and metadata
        # Model path follows pattern: {artifacts_dir}/model_{run_id}.joblib
        artifacts_dir = Path(self.settings.forecast_model_artifacts_dir)
        model_path = artifacts_dir / f"model_{run_id}.joblib"

        if not model_path.exists():
            # Try without .joblib extension (older format)
            model_path = artifacts_dir / f"model_{run_id}"
            if not model_path.exists():
                msg = f"Model not found for run_id: {run_id}"
                raise FileNotFoundError(msg)

        # Load bundle to get store_id and product_id from metadata
        bundle = load_model_bundle(model_path, base_dir=artifacts_dir)
        store_id_raw = bundle.metadata.get("store_id")
        product_id_raw = bundle.metadata.get("product_id")
        # Cast to int - metadata values are stored as int but typed as object
        store_id = int(str(store_id_raw)) if store_id_raw is not None else 0
        product_id = int(str(product_id_raw)) if product_id_raw is not None else 0

        if store_id == 0 or product_id == 0:
            msg = f"Model bundle missing store_id or product_id in metadata for run_id: {run_id}"
            raise ValueError(msg)

        # Generate predictions
        response = await service.predict(
            store_id=store_id,
            product_id=product_id,
            horizon=horizon,
            model_path=str(model_path),
        )

        return {
            "store_id": response.store_id,
            "product_id": response.product_id,
            "model_type": response.model_type,
            "horizon": response.horizon,
            "forecasts": [
                {
                    "date": f.date.isoformat(),
                    "forecast": float(f.forecast),
                    "lower_bound": float(f.lower_bound) if f.lower_bound else None,
                    "upper_bound": float(f.upper_bound) if f.upper_bound else None,
                }
                for f in response.forecasts
            ],
            "duration_ms": response.duration_ms,
        }

    async def _execute_backtest(
        self,
        db: AsyncSession,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a backtest job.

        Args:
            db: Database session.
            params: Backtest parameters.

        Returns:
            Result dict with backtest metrics.
        """
        # Import here to avoid circular imports
        from datetime import date as date_type

        from app.features.backtesting.schemas import BacktestConfig, SplitConfig
        from app.features.backtesting.service import BacktestingService
        from app.features.forecasting.schemas import (
            MovingAverageModelConfig,
            NaiveModelConfig,
            SeasonalNaiveModelConfig,
        )

        service = BacktestingService()

        # Extract parameters
        model_type = params.get("model_type", "naive")
        store_id = params["store_id"]
        product_id = params["product_id"]
        start_date = params["start_date"]
        end_date = params["end_date"]
        n_splits = params.get("n_splits", 5)
        test_size = params.get("test_size", 14)
        gap = params.get("gap", 0)

        # Parse dates if strings
        if isinstance(start_date, str):
            start_date = date_type.fromisoformat(start_date)
        if isinstance(end_date, str):
            end_date = date_type.fromisoformat(end_date)

        # Build model config based on model_type
        from app.features.forecasting.schemas import ModelConfig as ModelConfigType

        model_config: ModelConfigType
        if model_type == "naive":
            model_config = NaiveModelConfig()
        elif model_type == "seasonal_naive":
            season_length = params.get("season_length", 7)
            model_config = SeasonalNaiveModelConfig(season_length=season_length)
        elif model_type == "moving_average":
            window_size = params.get("window_size", 7)
            model_config = MovingAverageModelConfig(window_size=window_size)
        else:
            msg = f"Unsupported model_type: {model_type}"
            raise ValueError(msg)

        # Build split config
        split_config = SplitConfig(
            n_splits=n_splits,
            horizon=test_size,
            gap=gap,
        )

        # Build backtest config
        backtest_config = BacktestConfig(
            split_config=split_config,
            model_config_main=model_config,
        )

        # Run backtest
        response = await service.run_backtest(
            db=db,
            store_id=store_id,
            product_id=product_id,
            start_date=start_date,
            end_date=end_date,
            config=backtest_config,
        )

        # Extract metrics from main_model_results
        main_metrics = response.main_model_results.aggregated_metrics

        return {
            "backtest_id": response.backtest_id,
            "model_type": model_type,
            "n_splits": len(response.main_model_results.fold_results),
            "aggregated_metrics": {
                "mae": main_metrics.get("mae", 0.0),
                "smape": main_metrics.get("smape", 0.0),
                "wape": main_metrics.get("wape", 0.0),
                "bias": main_metrics.get("bias", 0.0),
            },
            "duration_ms": response.duration_ms,
        }

    def _to_response(self, job: Job) -> JobResponse:
        """Convert Job model to response schema.

        Args:
            job: Job ORM model.

        Returns:
            Job response schema.
        """
        return JobResponse(
            job_id=job.job_id,
            job_type=JobType(job.job_type),
            status=JobStatus(job.status),
            params=job.params,
            result=job.result,
            error_message=job.error_message,
            error_type=job.error_type,
            run_id=job.run_id,
            started_at=job.started_at,
            completed_at=job.completed_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
