"""FastAPI routes for seeder operations.

Provides REST endpoints for managing synthetic data generation
through the dashboard admin panel.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.features.seeder import schemas, service

router = APIRouter(prefix="/seeder", tags=["seeder"])
logger = get_logger(__name__)


def _check_seeder_enabled() -> None:
    """Check if seeder operations are allowed in current environment.

    Raises:
        HTTPException: If seeder is disabled in production.
    """
    settings = get_settings()
    if not settings.seeder_allow_production and settings.app_env == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seeder operations are not allowed in production environment. "
            "Set SEEDER_ALLOW_PRODUCTION=true to enable (not recommended).",
        )


@router.get(
    "/status",
    response_model=schemas.SeederStatus,
    summary="Get database status",
    description="Returns current row counts for all tables and date range metadata.",
)
async def get_status(
    db: AsyncSession = Depends(get_db),
) -> schemas.SeederStatus:
    """Get current database row counts and metadata.

    Returns counts for all dimension and fact tables, plus date range
    information from sales_daily.
    """
    return await service.get_status(db)


@router.get(
    "/scenarios",
    response_model=list[schemas.ScenarioInfo],
    summary="List scenario presets",
    description="Returns available scenario presets with their default configurations.",
)
async def list_scenarios() -> list[schemas.ScenarioInfo]:
    """List available scenario presets.

    Returns pre-built scenarios like retail_standard, holiday_rush, etc.
    with their default configurations.
    """
    return service.list_scenarios()


@router.get(
    "/channels",
    response_model=schemas.ChannelsResponse,
    summary="List sales channels",
    description=(
        "Return the SQL allow-list for `sales_daily.channel` and "
        "`ChannelConfig.channel_mix` keys (Phase 2). Use these values "
        "to populate UI selectors or validate channel_mix payloads "
        "before POST /seeder/generate."
    ),
)
async def list_channels() -> schemas.ChannelsResponse:
    """List valid sales channel identifiers (Phase 2)."""
    channels = sorted(schemas.VALID_CHANNELS)
    return schemas.ChannelsResponse(channels=channels, total=len(channels))


@router.post(
    "/generate",
    response_model=schemas.GenerateResult,
    status_code=status.HTTP_201_CREATED,
    summary="Generate new dataset",
    description="Generate a complete synthetic dataset. Requires confirmation in non-dev environments.",
)
async def generate_data(
    params: schemas.GenerateParams,
    db: AsyncSession = Depends(get_db),
) -> schemas.GenerateResult:
    """Generate a new synthetic dataset from scratch.

    This will create stores, products, calendar, sales, inventory,
    price history, and promotions based on the selected scenario.

    **Warning:** This operation may take several minutes for large datasets.

    Args:
        params: Generation parameters including scenario and seed.

    Returns:
        GenerateResult with counts of created records.

    Raises:
        HTTPException: If operation fails or is blocked.
    """
    _check_seeder_enabled()

    try:
        return await service.generate_data(db, params)
    except ValueError as e:
        logger.error(
            "seeder.generate.failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(
            "seeder.generate.failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generation failed: {e}",
        ) from e


@router.post(
    "/append",
    response_model=schemas.GenerateResult,
    status_code=status.HTTP_201_CREATED,
    summary="Append data",
    description="Append new data to existing dataset for a specified date range.",
)
async def append_data(
    params: schemas.AppendParams,
    db: AsyncSession = Depends(get_db),
) -> schemas.GenerateResult:
    """Append data to existing dataset.

    Uses existing dimension tables (stores, products) and generates
    new fact records (sales, inventory, etc.) for the specified date range.

    Requires existing dimensions. Run /generate first if database is empty.

    Args:
        params: Append parameters with date range.

    Returns:
        GenerateResult with counts of appended records.

    Raises:
        HTTPException: If no dimensions exist or operation fails.
    """
    _check_seeder_enabled()

    try:
        return await service.append_data(db, params)
    except ValueError as e:
        logger.error(
            "seeder.append.failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(
            "seeder.append.failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Append failed: {e}",
        ) from e


@router.delete(
    "/data",
    response_model=schemas.DeleteResult,
    summary="Delete data",
    description="Delete data with specified scope. Supports dry_run preview.",
)
async def delete_data(
    params: schemas.DeleteParams,
    db: AsyncSession = Depends(get_db),
) -> schemas.DeleteResult:
    """Delete data with specified scope.

    Scopes:
    - `all`: Delete everything (dimensions + facts)
    - `facts`: Delete only fact tables (sales, inventory, prices, promotions)
    - `dimensions`: Delete dimension tables (also deletes facts due to FK constraints)

    Use `dry_run=true` to preview what would be deleted without executing.

    Args:
        params: Delete parameters with scope and dry_run flag.

    Returns:
        DeleteResult with counts of deleted records.

    Raises:
        HTTPException: If operation is blocked or fails.
    """
    _check_seeder_enabled()

    try:
        return await service.delete_data(db, params)
    except ValueError as e:
        logger.error(
            "seeder.delete.failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(
            "seeder.delete.failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Delete failed: {e}",
        ) from e


@router.get(
    "/exogenous",
    response_model=schemas.ExogenousSignalResponse,
    summary="Query exogenous signals",
    description=(
        "Return exogenous signal rows (Phase 1) for a given signal name and date "
        "window. Available signals: `weather_temp_c`, `macro_index`, `event_flag`."
    ),
)
async def query_exogenous(
    signal_name: str = Query(
        ...,
        min_length=1,
        max_length=50,
        description="Signal identifier (e.g. weather_temp_c, macro_index, event_flag)",
    ),
    start_date: date = Query(..., description="Window start (inclusive)"),
    end_date: date = Query(..., description="Window end (inclusive)"),
    store_id: int | None = Query(
        default=None,
        ge=1,
        description="Optional store filter. Omit to include global + per-store rows.",
    ),
    db: AsyncSession = Depends(get_db),
) -> schemas.ExogenousSignalResponse:
    """Query exogenous_signal rows for a signal name and date window.

    Returns rows ordered by date. Subject to row and date-range caps to
    keep the response bounded.

    Raises:
        HTTPException: 400 if the date window is invalid or oversized.
    """
    try:
        return await service.query_exogenous(
            db,
            signal_name=signal_name,
            start_date=start_date,
            end_date=end_date,
            store_id=store_id,
        )
    except ValueError as e:
        logger.error(
            "seeder.exogenous.query_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(
            "seeder.exogenous.query_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Exogenous query failed: {e}",
        ) from e


@router.post(
    "/verify",
    response_model=schemas.VerifyResult,
    summary="Verify data integrity",
    description="Run data integrity checks on current database content.",
)
async def verify_data(
    db: AsyncSession = Depends(get_db),
) -> schemas.VerifyResult:
    """Run data integrity verification.

    Checks performed:
    - Foreign key integrity (sales reference valid stores/products/dates)
    - Non-negative constraints (quantities, prices >= 0)
    - Calendar date coverage (no gaps in date sequence)
    - Data presence (sales data exists)
    - Dimension completeness (stores, products, calendar populated)

    Returns:
        VerifyResult with pass/fail status for each check.
    """
    try:
        return await service.verify_data(db)
    except Exception as e:
        logger.error(
            "seeder.verify.failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failed: {e}",
        ) from e
