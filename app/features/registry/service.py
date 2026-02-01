"""Registry service for managing model runs and deployments.

Orchestrates:
- Creating and updating model runs
- Managing deployment aliases
- Comparing runs
- Capturing runtime environment info

CRITICAL: All state transitions are validated.
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.registry.models import DeploymentAlias, ModelRun
from app.features.registry.models import RunStatus as RunStatusORM
from app.features.registry.schemas import (
    VALID_TRANSITIONS,
    AliasCreate,
    AliasResponse,
    RunCompareResponse,
    RunCreate,
    RunListResponse,
    RunResponse,
    RunStatus,
    RunUpdate,
)

logger = structlog.get_logger()


class InvalidTransitionError(ValueError):
    """Invalid state transition attempted."""

    pass


class DuplicateRunError(ValueError):
    """Duplicate run detected and policy is 'deny'."""

    pass


class RegistryService:
    """Service for managing model runs and deployment aliases.

    Provides orchestration layer for:
    - Creating and tracking model runs
    - Managing deployment aliases
    - Comparing run configurations and metrics
    - Capturing runtime environment snapshots

    CRITICAL: All state transitions are validated.
    """

    def __init__(self) -> None:
        """Initialize the registry service."""
        self.settings = get_settings()

    def _capture_runtime_info(self) -> dict[str, Any]:
        """Capture current runtime environment information.

        Returns:
            Dictionary with Python and library versions.
        """
        runtime_info: dict[str, Any] = {
            "python_version": sys.version,
        }

        # Try to capture library versions
        try:
            import sklearn  # type: ignore[import-untyped]

            runtime_info["sklearn_version"] = sklearn.__version__
        except ImportError:
            pass

        try:
            import numpy as np

            runtime_info["numpy_version"] = np.__version__
        except ImportError:
            pass

        try:
            import pandas as pd

            runtime_info["pandas_version"] = pd.__version__
        except ImportError:
            pass

        try:
            import joblib  # type: ignore[import-untyped]

            runtime_info["joblib_version"] = joblib.__version__
        except ImportError:
            pass

        return runtime_info

    def _compute_config_hash(self, config: dict[str, Any]) -> str:
        """Compute deterministic hash of model configuration.

        Args:
            config: Model configuration dictionary.

        Returns:
            16-character hex string hash.
        """
        config_json = json.dumps(config, sort_keys=True, default=str)
        return hashlib.sha256(config_json.encode()).hexdigest()[:16]

    def _is_valid_transition(self, current_status: RunStatus, new_status: RunStatus) -> bool:
        """Check if state transition is valid.

        Args:
            current_status: Current run status.
            new_status: Proposed new status.

        Returns:
            True if transition is valid, False otherwise.
        """
        valid_next = VALID_TRANSITIONS.get(current_status, set())
        return new_status in valid_next

    def _validate_transition(self, current_status: RunStatus, new_status: RunStatus) -> None:
        """Validate state transition is allowed.

        Args:
            current_status: Current run status.
            new_status: Proposed new status.

        Raises:
            InvalidTransitionError: If transition is not allowed.
        """
        if not self._is_valid_transition(current_status, new_status):
            valid_next = VALID_TRANSITIONS.get(current_status, set())
            raise InvalidTransitionError(
                f"Invalid transition from {current_status.value} to {new_status.value}. "
                f"Valid transitions: {[s.value for s in valid_next]}"
            )

    async def create_run(
        self,
        db: AsyncSession,
        run_data: RunCreate,
    ) -> RunResponse:
        """Create a new model run.

        Args:
            db: Database session.
            run_data: Run creation data.

        Returns:
            Created run response.

        Raises:
            DuplicateRunError: If duplicate detected and policy is 'deny'.
        """
        run_id = uuid.uuid4().hex
        config_hash = self._compute_config_hash(run_data.model_config_data)

        # Check for duplicates based on policy
        if self.settings.registry_duplicate_policy in ("deny", "detect"):
            existing = await self._find_duplicate(
                db=db,
                config_hash=config_hash,
                store_id=run_data.store_id,
                product_id=run_data.product_id,
                data_window_start=run_data.data_window_start,
                data_window_end=run_data.data_window_end,
            )
            if existing:
                if self.settings.registry_duplicate_policy == "deny":
                    raise DuplicateRunError(f"Duplicate run detected: {existing.run_id}")
                else:  # detect
                    logger.warning(
                        "registry.duplicate_detected",
                        existing_run_id=existing.run_id,
                        config_hash=config_hash,
                    )

        # Capture runtime info
        runtime_info = self._capture_runtime_info()

        # Convert agent context to dict if present
        agent_context_dict = None
        if run_data.agent_context:
            agent_context_dict = run_data.agent_context.model_dump()

        # Create model run
        model_run = ModelRun(
            run_id=run_id,
            status=RunStatusORM.PENDING.value,
            model_type=run_data.model_type,
            model_config=run_data.model_config_data,
            feature_config=run_data.feature_config,
            config_hash=config_hash,
            data_window_start=run_data.data_window_start,
            data_window_end=run_data.data_window_end,
            store_id=run_data.store_id,
            product_id=run_data.product_id,
            runtime_info=runtime_info,
            agent_context=agent_context_dict,
            git_sha=run_data.git_sha,
        )

        db.add(model_run)
        await db.flush()
        await db.refresh(model_run)

        logger.info(
            "registry.run_created",
            run_id=run_id,
            model_type=run_data.model_type,
            config_hash=config_hash,
            store_id=run_data.store_id,
            product_id=run_data.product_id,
        )

        return self._model_to_response(model_run)

    async def get_run(
        self,
        db: AsyncSession,
        run_id: str,
    ) -> RunResponse | None:
        """Get a run by its run_id.

        Args:
            db: Database session.
            run_id: Run identifier.

        Returns:
            Run response or None if not found.
        """
        stmt = select(ModelRun).where(ModelRun.run_id == run_id)
        result = await db.execute(stmt)
        model_run = result.scalar_one_or_none()

        if model_run is None:
            return None

        return self._model_to_response(model_run)

    async def list_runs(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        model_type: str | None = None,
        status: RunStatus | None = None,
        store_id: int | None = None,
        product_id: int | None = None,
    ) -> RunListResponse:
        """List runs with filtering and pagination.

        Args:
            db: Database session.
            page: Page number (1-indexed).
            page_size: Number of runs per page.
            model_type: Filter by model type.
            status: Filter by status.
            store_id: Filter by store ID.
            product_id: Filter by product ID.

        Returns:
            Paginated list of runs.
        """
        # Build query with filters
        stmt = select(ModelRun)

        if model_type is not None:
            stmt = stmt.where(ModelRun.model_type == model_type)
        if status is not None:
            stmt = stmt.where(ModelRun.status == status.value)
        if store_id is not None:
            stmt = stmt.where(ModelRun.store_id == store_id)
        if product_id is not None:
            stmt = stmt.where(ModelRun.product_id == product_id)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await db.execute(count_stmt)
        total = total_result.scalar_one()

        # Apply pagination
        offset = (page - 1) * page_size
        stmt = stmt.order_by(ModelRun.created_at.desc()).offset(offset).limit(page_size)

        result = await db.execute(stmt)
        runs = result.scalars().all()

        return RunListResponse(
            runs=[self._model_to_response(run) for run in runs],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def update_run(
        self,
        db: AsyncSession,
        run_id: str,
        update_data: RunUpdate,
    ) -> RunResponse | None:
        """Update a run.

        Args:
            db: Database session.
            run_id: Run identifier.
            update_data: Fields to update.

        Returns:
            Updated run response or None if not found.

        Raises:
            InvalidTransitionError: If status transition is invalid.
        """
        stmt = select(ModelRun).where(ModelRun.run_id == run_id)
        result = await db.execute(stmt)
        model_run = result.scalar_one_or_none()

        if model_run is None:
            return None

        # Validate status transition if changing status
        if update_data.status is not None:
            current_status = RunStatus(model_run.status)
            self._validate_transition(current_status, update_data.status)
            model_run.status = update_data.status.value

            # Update timing fields based on transition
            now = datetime.now(UTC)
            if update_data.status == RunStatus.RUNNING:
                model_run.started_at = now
            elif update_data.status in (RunStatus.SUCCESS, RunStatus.FAILED):
                model_run.completed_at = now

        # Update other fields
        if update_data.metrics is not None:
            model_run.metrics = update_data.metrics
        if update_data.artifact_uri is not None:
            model_run.artifact_uri = update_data.artifact_uri
        if update_data.artifact_hash is not None:
            model_run.artifact_hash = update_data.artifact_hash
        if update_data.artifact_size_bytes is not None:
            model_run.artifact_size_bytes = update_data.artifact_size_bytes
        if update_data.error_message is not None:
            model_run.error_message = update_data.error_message

        await db.flush()
        await db.refresh(model_run)

        logger.info(
            "registry.run_updated",
            run_id=run_id,
            status=model_run.status,
            has_metrics=model_run.metrics is not None,
            has_artifact=model_run.artifact_uri is not None,
        )

        return self._model_to_response(model_run)

    async def create_alias(
        self,
        db: AsyncSession,
        alias_data: AliasCreate,
    ) -> AliasResponse:
        """Create or update a deployment alias.

        Args:
            db: Database session.
            alias_data: Alias creation data.

        Returns:
            Created/updated alias response.

        Raises:
            ValueError: If run not found or not in SUCCESS status.
        """
        # Find the run
        stmt = select(ModelRun).where(ModelRun.run_id == alias_data.run_id)
        result = await db.execute(stmt)
        model_run = result.scalar_one_or_none()

        if model_run is None:
            raise ValueError(f"Run not found: {alias_data.run_id}")

        # CRITICAL: Only SUCCESS runs can be aliased
        if model_run.status != RunStatusORM.SUCCESS.value:
            raise ValueError(
                f"Only SUCCESS runs can be aliased. "
                f"Run {alias_data.run_id} has status: {model_run.status}"
            )

        # Check if alias exists
        alias_stmt = select(DeploymentAlias).where(
            DeploymentAlias.alias_name == alias_data.alias_name
        )
        alias_result = await db.execute(alias_stmt)
        existing_alias = alias_result.scalar_one_or_none()

        if existing_alias:
            # Update existing alias
            existing_alias.run_id = model_run.id
            existing_alias.description = alias_data.description
            alias = existing_alias
            logger.info(
                "registry.alias_updated",
                alias_name=alias_data.alias_name,
                run_id=alias_data.run_id,
            )
        else:
            # Create new alias
            alias = DeploymentAlias(
                alias_name=alias_data.alias_name,
                run_id=model_run.id,
                description=alias_data.description,
            )
            db.add(alias)
            logger.info(
                "registry.alias_created",
                alias_name=alias_data.alias_name,
                run_id=alias_data.run_id,
            )

        await db.flush()
        await db.refresh(alias)

        return AliasResponse(
            alias_name=alias.alias_name,
            run_id=model_run.run_id,
            run_status=RunStatus(model_run.status),
            model_type=model_run.model_type,
            description=alias.description,
            created_at=alias.created_at,
            updated_at=alias.updated_at,
        )

    async def get_alias(
        self,
        db: AsyncSession,
        alias_name: str,
    ) -> AliasResponse | None:
        """Get an alias by name.

        Args:
            db: Database session.
            alias_name: Alias name.

        Returns:
            Alias response or None if not found.
        """
        stmt = (
            select(DeploymentAlias, ModelRun)
            .join(ModelRun, DeploymentAlias.run_id == ModelRun.id)
            .where(DeploymentAlias.alias_name == alias_name)
        )
        result = await db.execute(stmt)
        row = result.first()

        if row is None:
            return None

        alias, model_run = row

        return AliasResponse(
            alias_name=alias.alias_name,
            run_id=model_run.run_id,
            run_status=RunStatus(model_run.status),
            model_type=model_run.model_type,
            description=alias.description,
            created_at=alias.created_at,
            updated_at=alias.updated_at,
        )

    async def list_aliases(
        self,
        db: AsyncSession,
    ) -> list[AliasResponse]:
        """List all deployment aliases.

        Args:
            db: Database session.

        Returns:
            List of alias responses.
        """
        stmt = (
            select(DeploymentAlias, ModelRun)
            .join(ModelRun, DeploymentAlias.run_id == ModelRun.id)
            .order_by(DeploymentAlias.alias_name)
        )
        result = await db.execute(stmt)
        rows = result.all()

        return [
            AliasResponse(
                alias_name=alias.alias_name,
                run_id=model_run.run_id,
                run_status=RunStatus(model_run.status),
                model_type=model_run.model_type,
                description=alias.description,
                created_at=alias.created_at,
                updated_at=alias.updated_at,
            )
            for alias, model_run in rows
        ]

    async def delete_alias(
        self,
        db: AsyncSession,
        alias_name: str,
    ) -> bool:
        """Delete a deployment alias.

        Args:
            db: Database session.
            alias_name: Alias name.

        Returns:
            True if deleted, False if not found.
        """
        stmt = select(DeploymentAlias).where(DeploymentAlias.alias_name == alias_name)
        result = await db.execute(stmt)
        alias = result.scalar_one_or_none()

        if alias is None:
            return False

        await db.delete(alias)
        await db.flush()

        logger.info("registry.alias_deleted", alias_name=alias_name)
        return True

    async def compare_runs(
        self,
        db: AsyncSession,
        run_id_a: str,
        run_id_b: str,
    ) -> RunCompareResponse | None:
        """Compare two runs.

        Args:
            db: Database session.
            run_id_a: First run ID.
            run_id_b: Second run ID.

        Returns:
            Comparison response or None if either run not found.
        """
        run_a = await self.get_run(db, run_id_a)
        run_b = await self.get_run(db, run_id_b)

        if run_a is None or run_b is None:
            return None

        # Compute config diff
        config_diff = self._compute_config_diff(run_a.model_config_data, run_b.model_config_data)

        # Compute metrics diff
        metrics_diff = self._compute_metrics_diff(run_a.metrics, run_b.metrics)

        return RunCompareResponse(
            run_a=run_a,
            run_b=run_b,
            config_diff=config_diff,
            metrics_diff=metrics_diff,
        )

    async def _find_duplicate(
        self,
        db: AsyncSession,
        config_hash: str,
        store_id: int,
        product_id: int,
        data_window_start: date,
        data_window_end: date,
    ) -> ModelRun | None:
        """Find existing run with same config and data window.

        Args:
            db: Database session.
            config_hash: Configuration hash.
            store_id: Store ID.
            product_id: Product ID.
            data_window_start: Data window start date.
            data_window_end: Data window end date.

        Returns:
            Existing run or None.
        """
        stmt = select(ModelRun).where(
            (ModelRun.config_hash == config_hash)
            & (ModelRun.store_id == store_id)
            & (ModelRun.product_id == product_id)
            & (ModelRun.data_window_start == data_window_start)
            & (ModelRun.data_window_end == data_window_end)
            & (ModelRun.status != RunStatusORM.ARCHIVED.value)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    def _model_to_response(self, model_run: ModelRun) -> RunResponse:
        """Convert ORM model to response schema.

        Args:
            model_run: ORM model.

        Returns:
            Response schema.
        """
        return RunResponse(
            run_id=model_run.run_id,
            status=RunStatus(model_run.status),
            model_type=model_run.model_type,
            model_config=model_run.model_config,
            feature_config=model_run.feature_config,
            config_hash=model_run.config_hash,
            data_window_start=model_run.data_window_start,
            data_window_end=model_run.data_window_end,
            store_id=model_run.store_id,
            product_id=model_run.product_id,
            metrics=model_run.metrics,
            artifact_uri=model_run.artifact_uri,
            artifact_hash=model_run.artifact_hash,
            artifact_size_bytes=model_run.artifact_size_bytes,
            runtime_info=model_run.runtime_info,
            agent_context=model_run.agent_context,
            git_sha=model_run.git_sha,
            error_message=model_run.error_message,
            started_at=model_run.started_at,
            completed_at=model_run.completed_at,
            created_at=model_run.created_at,
            updated_at=model_run.updated_at,
        )

    def _compute_config_diff(
        self, config_a: dict[str, Any], config_b: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute differences between two configurations.

        Args:
            config_a: First configuration.
            config_b: Second configuration.

        Returns:
            Dictionary of differing keys with both values.
        """
        diff: dict[str, Any] = {}
        all_keys = set(config_a.keys()) | set(config_b.keys())

        for key in all_keys:
            val_a = config_a.get(key)
            val_b = config_b.get(key)
            if val_a != val_b:
                diff[key] = {"a": val_a, "b": val_b}

        return diff

    def _compute_metrics_diff(
        self,
        metrics_a: dict[str, Any] | None,
        metrics_b: dict[str, Any] | None,
    ) -> dict[str, dict[str, float | None]]:
        """Compute differences between two metric sets.

        Args:
            metrics_a: First metrics.
            metrics_b: Second metrics.

        Returns:
            Dictionary with metric comparisons.
        """
        metrics_a = metrics_a or {}
        metrics_b = metrics_b or {}

        diff: dict[str, dict[str, float | None]] = {}
        all_keys = set(metrics_a.keys()) | set(metrics_b.keys())

        for key in all_keys:
            val_a = metrics_a.get(key)
            val_b = metrics_b.get(key)

            # Compute difference if both are numeric
            diff_val: float | None = None
            if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                diff_val = float(val_b) - float(val_a)

            diff[key] = {
                "a": float(val_a) if isinstance(val_a, (int, float)) else None,
                "b": float(val_b) if isinstance(val_b, (int, float)) else None,
                "diff": diff_val,
            }

        return diff
