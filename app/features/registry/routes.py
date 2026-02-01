"""Registry API routes for model runs and deployment aliases."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import DatabaseError
from app.core.logging import get_logger
from app.features.registry.schemas import (
    AliasCreate,
    AliasResponse,
    RunCompareResponse,
    RunCreate,
    RunListResponse,
    RunResponse,
    RunStatus,
    RunUpdate,
)
from app.features.registry.service import (
    DuplicateRunError,
    InvalidTransitionError,
    RegistryService,
)
from app.features.registry.storage import (
    ArtifactNotFoundError,
    ChecksumMismatchError,
    LocalFSProvider,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/registry", tags=["registry"])


# =============================================================================
# Run Endpoints
# =============================================================================


@router.post(
    "/runs",
    response_model=RunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new model run",
    description="""
Create a new model run with PENDING status.

**Required Fields:**
- `model_type`: Type of model (e.g., 'naive', 'seasonal_naive')
- `model_config`: Full model configuration as JSON
- `data_window_start`: Start date of training data
- `data_window_end`: End date of training data
- `store_id`: Store ID for this run
- `product_id`: Product ID for this run

**Optional Fields:**
- `feature_config`: Feature engineering configuration
- `agent_context`: Agent ID and session ID for traceability
- `git_sha`: Git commit hash

**Duplicate Detection:**
Based on `registry_duplicate_policy` setting:
- `allow`: Always create new runs
- `deny`: Reject if duplicate config+window exists
- `detect`: Log warning but allow creation
""",
)
async def create_run(
    request: RunCreate,
    db: AsyncSession = Depends(get_db),
) -> RunResponse:
    """Create a new model run.

    Args:
        request: Run creation request.
        db: Async database session from dependency.

    Returns:
        Created run details.

    Raises:
        HTTPException: If duplicate detected with 'deny' policy.
        DatabaseError: If database operation fails.
    """
    logger.info(
        "registry.create_run_request_received",
        model_type=request.model_type,
        store_id=request.store_id,
        product_id=request.product_id,
    )

    service = RegistryService()

    try:
        response = await service.create_run(db=db, run_data=request)

        logger.info(
            "registry.create_run_request_completed",
            run_id=response.run_id,
            config_hash=response.config_hash,
        )

        return response

    except DuplicateRunError as e:
        logger.warning(
            "registry.create_run_request_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e
    except SQLAlchemyError as e:
        logger.error(
            "registry.create_run_request_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise DatabaseError(
            message="Failed to create run",
            details={"error": str(e)},
        ) from e


@router.get(
    "/runs",
    response_model=RunListResponse,
    summary="List model runs",
    description="""
List model runs with optional filtering and pagination.

**Filters:**
- `model_type`: Filter by model type
- `status`: Filter by run status
- `store_id`: Filter by store ID
- `product_id`: Filter by product ID

**Pagination:**
- `page`: Page number (1-indexed, default: 1)
- `page_size`: Runs per page (default: 20, max: 100)
""",
)
async def list_runs(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Runs per page"),
    model_type: str | None = Query(None, description="Filter by model type"),
    run_status: RunStatus | None = Query(None, alias="status", description="Filter by status"),
    store_id: int | None = Query(None, ge=1, description="Filter by store ID"),
    product_id: int | None = Query(None, ge=1, description="Filter by product ID"),
) -> RunListResponse:
    """List model runs with filtering and pagination.

    Args:
        db: Async database session from dependency.
        page: Page number (1-indexed).
        page_size: Number of runs per page.
        model_type: Filter by model type.
        run_status: Filter by status.
        store_id: Filter by store ID.
        product_id: Filter by product ID.

    Returns:
        Paginated list of runs.
    """
    service = RegistryService()

    response = await service.list_runs(
        db=db,
        page=page,
        page_size=page_size,
        model_type=model_type,
        status=run_status,
        store_id=store_id,
        product_id=product_id,
    )

    return response


@router.get(
    "/runs/{run_id}",
    response_model=RunResponse,
    summary="Get run details",
    description="Get full details for a specific model run by its run_id.",
)
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> RunResponse:
    """Get run details by run_id.

    Args:
        run_id: Run identifier.
        db: Async database session from dependency.

    Returns:
        Run details.

    Raises:
        HTTPException: If run not found.
    """
    service = RegistryService()

    response = await service.get_run(db=db, run_id=run_id)

    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    return response


@router.patch(
    "/runs/{run_id}",
    response_model=RunResponse,
    summary="Update a run",
    description="""
Update a model run's status, metrics, or artifact information.

**Status Transitions:**
- `pending` → `running` | `archived`
- `running` → `success` | `failed` | `archived`
- `success` → `archived`
- `failed` → `archived`
- `archived` → (terminal, no transitions)

**Updatable Fields:**
- `status`: New status (must be valid transition)
- `metrics`: Performance metrics (JSON)
- `artifact_uri`: Relative path to artifact
- `artifact_hash`: SHA-256 checksum
- `artifact_size_bytes`: Artifact file size
- `error_message`: Error details (for FAILED runs)
""",
)
async def update_run(
    run_id: str,
    request: RunUpdate,
    db: AsyncSession = Depends(get_db),
) -> RunResponse:
    """Update a model run.

    Args:
        run_id: Run identifier.
        request: Update request with fields to change.
        db: Async database session from dependency.

    Returns:
        Updated run details.

    Raises:
        HTTPException: If run not found or invalid status transition.
    """
    logger.info(
        "registry.update_run_request_received",
        run_id=run_id,
        new_status=request.status.value if request.status else None,
    )

    service = RegistryService()

    try:
        response = await service.update_run(db=db, run_id=run_id, update_data=request)

        if response is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run not found: {run_id}",
            )

        logger.info(
            "registry.update_run_request_completed",
            run_id=run_id,
            status=response.status.value,
        )

        return response

    except InvalidTransitionError as e:
        logger.warning(
            "registry.update_run_request_failed",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except SQLAlchemyError as e:
        logger.error(
            "registry.update_run_request_failed",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise DatabaseError(
            message="Failed to update run",
            details={"error": str(e)},
        ) from e


@router.get(
    "/runs/{run_id}/verify",
    response_model=dict[str, bool | str],
    summary="Verify artifact integrity",
    description="""
Verify that the artifact for a run matches its stored checksum.

Returns verification status and computed hash.
""",
)
async def verify_artifact(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool | str]:
    """Verify artifact integrity for a run.

    Args:
        run_id: Run identifier.
        db: Async database session from dependency.

    Returns:
        Verification result with computed hash.

    Raises:
        HTTPException: If run not found or artifact missing.
    """
    service = RegistryService()
    run = await service.get_run(db=db, run_id=run_id)

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    if run.artifact_uri is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Run has no associated artifact",
        )

    storage = LocalFSProvider()

    try:
        path = storage.load(run.artifact_uri, expected_hash=run.artifact_hash)
        actual_hash = storage.compute_hash(path)

        return {
            "verified": True,
            "run_id": run_id,
            "artifact_uri": run.artifact_uri,
            "stored_hash": run.artifact_hash or "",
            "computed_hash": actual_hash,
        }

    except ArtifactNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except ChecksumMismatchError as e:
        return {
            "verified": False,
            "run_id": run_id,
            "artifact_uri": run.artifact_uri,
            "error": str(e),
        }


# =============================================================================
# Alias Endpoints
# =============================================================================


@router.post(
    "/aliases",
    response_model=AliasResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update an alias",
    description="""
Create or update a deployment alias pointing to a successful run.

**Alias Names:**
- Must start with lowercase letter or number
- Can contain lowercase letters, numbers, hyphens, and underscores
- Maximum 100 characters

**IMPORTANT:** Aliases can only point to runs with SUCCESS status.
""",
)
async def create_alias(
    request: AliasCreate,
    db: AsyncSession = Depends(get_db),
) -> AliasResponse:
    """Create or update a deployment alias.

    Args:
        request: Alias creation request.
        db: Async database session from dependency.

    Returns:
        Created/updated alias details.

    Raises:
        HTTPException: If run not found or not in SUCCESS status.
    """
    logger.info(
        "registry.create_alias_request_received",
        alias_name=request.alias_name,
        run_id=request.run_id,
    )

    service = RegistryService()

    try:
        response = await service.create_alias(db=db, alias_data=request)

        logger.info(
            "registry.create_alias_request_completed",
            alias_name=request.alias_name,
            run_id=response.run_id,
        )

        return response

    except ValueError as e:
        logger.warning(
            "registry.create_alias_request_failed",
            alias_name=request.alias_name,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except SQLAlchemyError as e:
        logger.error(
            "registry.create_alias_request_failed",
            alias_name=request.alias_name,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise DatabaseError(
            message="Failed to create alias",
            details={"error": str(e)},
        ) from e


@router.get(
    "/aliases",
    response_model=list[AliasResponse],
    summary="List all aliases",
    description="List all deployment aliases sorted by name.",
)
async def list_aliases(
    db: AsyncSession = Depends(get_db),
) -> list[AliasResponse]:
    """List all deployment aliases.

    Args:
        db: Async database session from dependency.

    Returns:
        List of aliases.
    """
    service = RegistryService()
    return await service.list_aliases(db=db)


@router.get(
    "/aliases/{alias_name}",
    response_model=AliasResponse,
    summary="Get alias details",
    description="Get details for a specific deployment alias.",
)
async def get_alias(
    alias_name: str,
    db: AsyncSession = Depends(get_db),
) -> AliasResponse:
    """Get alias details by name.

    Args:
        alias_name: Alias name.
        db: Async database session from dependency.

    Returns:
        Alias details.

    Raises:
        HTTPException: If alias not found.
    """
    service = RegistryService()
    response = await service.get_alias(db=db, alias_name=alias_name)

    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alias not found: {alias_name}",
        )

    return response


@router.delete(
    "/aliases/{alias_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an alias",
    description="Delete a deployment alias.",
)
async def delete_alias(
    alias_name: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a deployment alias.

    Args:
        alias_name: Alias name.
        db: Async database session from dependency.

    Raises:
        HTTPException: If alias not found.
    """
    logger.info(
        "registry.delete_alias_request_received",
        alias_name=alias_name,
    )

    service = RegistryService()
    deleted = await service.delete_alias(db=db, alias_name=alias_name)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alias not found: {alias_name}",
        )

    logger.info(
        "registry.delete_alias_request_completed",
        alias_name=alias_name,
    )


# =============================================================================
# Compare Endpoint
# =============================================================================


@router.get(
    "/compare/{run_id_a}/{run_id_b}",
    response_model=RunCompareResponse,
    summary="Compare two runs",
    description="""
Compare two model runs side-by-side.

Returns:
- Full details of both runs
- Configuration differences
- Metrics differences with computed deltas
""",
)
async def compare_runs(
    run_id_a: str,
    run_id_b: str,
    db: AsyncSession = Depends(get_db),
) -> RunCompareResponse:
    """Compare two runs.

    Args:
        run_id_a: First run ID.
        run_id_b: Second run ID.
        db: Async database session from dependency.

    Returns:
        Comparison of both runs.

    Raises:
        HTTPException: If either run not found.
    """
    service = RegistryService()
    response = await service.compare_runs(db=db, run_id_a=run_id_a, run_id_b=run_id_b)

    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"One or both runs not found: {run_id_a}, {run_id_b}",
        )

    return response
