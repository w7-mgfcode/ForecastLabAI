"""Registry tools for agent interaction with the model registry.

Provides PydanticAI-compatible tool functions for:
- Listing and retrieving model runs
- Comparing run configurations and metrics
- Creating deployment aliases
- Archiving runs

CRITICAL: create_alias and archive_run require human approval.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.registry.schemas import (
    AliasCreate,
    AliasResponse,
    RunCompareResponse,
    RunListResponse,
    RunResponse,
    RunStatus,
    RunUpdate,
)
from app.features.registry.service import RegistryService

logger = structlog.get_logger()


async def list_runs(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    model_type: str | None = None,
    status: str | None = None,
    store_id: int | None = None,
    product_id: int | None = None,
) -> dict[str, Any]:
    """List model runs from the registry with filtering.

    Use this tool to browse existing experiment runs and find runs to compare
    or analyze. Supports filtering by model type, status, store, and product.

    Args:
        db: Database session (injected via agent context).
        page: Page number (1-indexed, default 1).
        page_size: Results per page (default 20, max 100).
        model_type: Filter by model type (e.g., 'naive', 'seasonal_naive').
        status: Filter by status ('pending', 'running', 'success', 'failed', 'archived').
        store_id: Filter by store ID.
        product_id: Filter by product ID.

    Returns:
        Dictionary with 'runs' list and pagination info.

    Example:
        # List all successful runs for store 1
        result = await list_runs(db, status='success', store_id=1)
    """
    logger.info(
        "agents.registry_tool.list_runs_called",
        page=page,
        page_size=page_size,
        model_type=model_type,
        status=status,
        store_id=store_id,
        product_id=product_id,
    )

    service = RegistryService()

    # Convert status string to enum if provided
    status_enum = RunStatus(status) if status else None

    result: RunListResponse = await service.list_runs(
        db=db,
        page=page,
        page_size=min(page_size, 100),  # Cap at 100
        model_type=model_type,
        status=status_enum,
        store_id=store_id,
        product_id=product_id,
    )

    return result.model_dump()


async def get_run(
    db: AsyncSession,
    run_id: str,
) -> dict[str, Any] | None:
    """Get detailed information about a specific model run.

    Use this tool to retrieve full details of a run including its configuration,
    metrics, artifact location, and timing information.

    Args:
        db: Database session (injected via agent context).
        run_id: The unique run identifier (32-char hex string).

    Returns:
        Run details dictionary or None if not found.

    Example:
        # Get details of a specific run
        run = await get_run(db, run_id='abc123def456...')
    """
    logger.info("agents.registry_tool.get_run_called", run_id=run_id)

    service = RegistryService()
    result: RunResponse | None = await service.get_run(db=db, run_id=run_id)

    if result is None:
        return None

    return result.model_dump()


async def compare_runs(
    db: AsyncSession,
    run_id_a: str,
    run_id_b: str,
) -> dict[str, Any] | None:
    """Compare two model runs to analyze configuration and metric differences.

    Use this tool to understand how two experiments differ in their setup
    and results. Helps identify which configuration changes led to better
    or worse performance.

    Args:
        db: Database session (injected via agent context).
        run_id_a: First run ID to compare.
        run_id_b: Second run ID to compare.

    Returns:
        Comparison with config_diff and metrics_diff, or None if either run not found.

    Example:
        # Compare two runs to see what changed
        comparison = await compare_runs(db, run_id_a='abc123...', run_id_b='def456...')
    """
    logger.info(
        "agents.registry_tool.compare_runs_called",
        run_id_a=run_id_a,
        run_id_b=run_id_b,
    )

    service = RegistryService()
    result: RunCompareResponse | None = await service.compare_runs(
        db=db,
        run_id_a=run_id_a,
        run_id_b=run_id_b,
    )

    if result is None:
        return None

    return result.model_dump()


async def create_alias(
    db: AsyncSession,
    alias_name: str,
    run_id: str,
    description: str | None = None,
) -> dict[str, Any]:
    """Create or update a deployment alias pointing to a successful run.

    REQUIRES HUMAN APPROVAL: This action modifies deployment configuration.

    Use this tool to promote a successful run to a named deployment stage
    (e.g., 'production', 'staging', 'champion'). Aliases provide stable
    references for serving models.

    Args:
        db: Database session (injected via agent context).
        alias_name: Name for the alias (e.g., 'production', 'staging').
        run_id: Run ID to alias (must be in SUCCESS status).
        description: Optional description for the alias.

    Returns:
        Created/updated alias details.

    Raises:
        ValueError: If run not found or not in SUCCESS status.

    Example:
        # Promote a successful run to production
        alias = await create_alias(db, alias_name='production', run_id='abc123...')
    """
    logger.info(
        "agents.registry_tool.create_alias_called",
        alias_name=alias_name,
        run_id=run_id,
    )

    service = RegistryService()
    alias_data = AliasCreate(
        alias_name=alias_name,
        run_id=run_id,
        description=description,
    )

    result: AliasResponse = await service.create_alias(db=db, alias_data=alias_data)

    logger.info(
        "agents.registry_tool.create_alias_completed",
        alias_name=alias_name,
        run_id=run_id,
    )

    return result.model_dump()


async def archive_run(
    db: AsyncSession,
    run_id: str,
) -> dict[str, Any] | None:
    """Archive a model run to mark it as no longer active.

    REQUIRES HUMAN APPROVAL: This action modifies run state permanently.

    Use this tool to archive runs that are no longer needed for active
    experimentation. Archived runs remain in the registry but are excluded
    from default queries.

    Args:
        db: Database session (injected via agent context).
        run_id: Run ID to archive.

    Returns:
        Updated run details or None if not found.

    Example:
        # Archive an old run
        result = await archive_run(db, run_id='abc123...')
    """
    logger.info("agents.registry_tool.archive_run_called", run_id=run_id)

    service = RegistryService()

    # Use update_run with ARCHIVED status
    update_data = RunUpdate(status=RunStatus.ARCHIVED)  # pyright: ignore[reportCallIssue]
    result: RunResponse | None = await service.update_run(
        db=db,
        run_id=run_id,
        update_data=update_data,
    )

    if result is None:
        return None

    logger.info("agents.registry_tool.archive_run_completed", run_id=run_id)

    return result.model_dump()
