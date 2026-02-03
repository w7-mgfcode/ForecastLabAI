"""Service layer for seeder operations."""

from __future__ import annotations

import time
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.features.data_platform.models import (
    Calendar,
    InventorySnapshotDaily,
    PriceHistory,
    Product,
    Promotion,
    SalesDaily,
    Store,
)
from app.features.seeder import schemas
from app.shared.seeder import DataSeeder, ScenarioPreset, SeederConfig
from app.shared.seeder.config import DimensionConfig, SparsityConfig

logger = get_logger(__name__)


def _get_scenario_preset(name: str) -> ScenarioPreset | None:
    """Convert scenario name string to ScenarioPreset enum.

    Args:
        name: Scenario name (e.g., "retail_standard").

    Returns:
        ScenarioPreset enum value or None if not found.
    """
    try:
        return ScenarioPreset(name)
    except ValueError:
        return None


def _build_config_from_params(params: schemas.GenerateParams) -> SeederConfig:
    """Build SeederConfig from API parameters.

    Args:
        params: Generation parameters from API request.

    Returns:
        Configured SeederConfig instance.
    """
    preset = _get_scenario_preset(params.scenario)

    if preset:
        # Start from scenario preset and override with explicit params
        config = SeederConfig.from_scenario(preset, seed=params.seed)
        # Override dimensions if explicitly set (different from defaults)
        config.dimensions = DimensionConfig(
            stores=params.stores,
            products=params.products,
        )
        config.start_date = params.start_date
        config.end_date = params.end_date
        if params.sparsity > 0:
            config.sparsity = SparsityConfig(missing_combinations_pct=params.sparsity)
    else:
        # Use default config with provided params
        config = SeederConfig(
            seed=params.seed,
            start_date=params.start_date,
            end_date=params.end_date,
            dimensions=DimensionConfig(
                stores=params.stores,
                products=params.products,
            ),
            sparsity=SparsityConfig(missing_combinations_pct=params.sparsity),
        )

    settings = get_settings()
    config.batch_size = settings.seeder_batch_size
    config.enable_progress = settings.seeder_enable_progress

    return config


async def get_status(db: AsyncSession) -> schemas.SeederStatus:
    """Get current database status with row counts.

    Args:
        db: Async database session.

    Returns:
        SeederStatus with current counts and metadata.
    """
    logger.info("seeder.status.fetching")

    # Fetch counts for all tables
    tables = [
        ("stores", Store),
        ("products", Product),
        ("calendar", Calendar),
        ("sales", SalesDaily),
        ("inventory", InventorySnapshotDaily),
        ("price_history", PriceHistory),
        ("promotions", Promotion),
    ]

    counts: dict[str, int] = {}
    for name, model in tables:
        result = await db.execute(select(func.count()).select_from(model))
        counts[name] = result.scalar() or 0

    # Get date range from sales_daily
    date_range_start: date | None = None
    date_range_end: date | None = None

    if counts["sales"] > 0:
        result = await db.execute(select(func.min(SalesDaily.date), func.max(SalesDaily.date)))
        row = result.fetchone()
        if row:
            date_range_start = row[0]
            date_range_end = row[1]

    # Get last update time from most recent sale
    last_updated: datetime | None = None
    if counts["sales"] > 0:
        result = await db.execute(select(func.max(SalesDaily.updated_at)))
        scalar_result = result.scalar()
        if isinstance(scalar_result, datetime):
            last_updated = scalar_result

    status = schemas.SeederStatus(
        stores=counts["stores"],
        products=counts["products"],
        calendar=counts["calendar"],
        sales=counts["sales"],
        inventory=counts["inventory"],
        price_history=counts["price_history"],
        promotions=counts["promotions"],
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        last_updated=last_updated,
    )

    logger.info(
        "seeder.status.fetched",
        total_records=sum(counts.values()),
        has_data=counts["sales"] > 0,
    )

    return status


def list_scenarios() -> list[schemas.ScenarioInfo]:
    """List available scenario presets.

    Returns:
        List of ScenarioInfo with preset details.
    """
    scenarios = [
        schemas.ScenarioInfo(
            name="retail_standard",
            description="Normal retail patterns with mild seasonality and linear trend",
            stores=10,
            products=50,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        ),
        schemas.ScenarioInfo(
            name="holiday_rush",
            description="Q4 surge with Black Friday/Christmas peaks and high stockout risk",
            stores=10,
            products=50,
            start_date=date(2024, 10, 1),
            end_date=date(2024, 12, 31),
        ),
        schemas.ScenarioInfo(
            name="high_variance",
            description="Noisy, unpredictable data with frequent anomalies for robustness testing",
            stores=10,
            products=50,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        ),
        schemas.ScenarioInfo(
            name="stockout_heavy",
            description="Frequent stockouts (25% probability) for inventory modeling",
            stores=10,
            products=50,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        ),
        schemas.ScenarioInfo(
            name="new_launches",
            description="100 products with gradual launch ramp patterns",
            stores=10,
            products=100,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        ),
        schemas.ScenarioInfo(
            name="sparse",
            description="50% missing combinations and random date gaps for gap handling",
            stores=10,
            products=50,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        ),
    ]

    logger.info("seeder.scenarios.listed", count=len(scenarios))
    return scenarios


async def generate_data(
    db: AsyncSession,
    params: schemas.GenerateParams,
) -> schemas.GenerateResult:
    """Generate a new synthetic dataset.

    Args:
        db: Async database session.
        params: Generation parameters.

    Returns:
        GenerateResult with counts and timing.

    Raises:
        ValueError: If production guard is enabled.
    """
    settings = get_settings()

    # Production guard
    if not settings.seeder_allow_production and settings.app_env == "production":
        logger.warning("seeder.generate.blocked", reason="production_guard")
        raise ValueError("Seeder operations are not allowed in production environment")

    if params.dry_run:
        logger.info(
            "seeder.generate.dry_run",
            scenario=params.scenario,
            seed=params.seed,
            stores=params.stores,
            products=params.products,
        )
        return schemas.GenerateResult(
            success=True,
            records_created={
                "stores": params.stores,
                "products": params.products,
                "calendar": (params.end_date - params.start_date).days + 1,
                "sales": 0,  # Would be calculated
                "price_history": 0,
                "promotions": 0,
                "inventory": 0,
            },
            duration_seconds=0.0,
            message=f"Dry run: would generate data with scenario '{params.scenario}'",
            seed=params.seed,
        )

    logger.info(
        "seeder.generate.started",
        scenario=params.scenario,
        seed=params.seed,
        stores=params.stores,
        products=params.products,
        start_date=str(params.start_date),
        end_date=str(params.end_date),
    )

    start_time = time.perf_counter()

    config = _build_config_from_params(params)
    seeder = DataSeeder(config)

    result = await seeder.generate_full(db)

    duration = time.perf_counter() - start_time

    logger.info(
        "seeder.generate.completed",
        seed=params.seed,
        duration_seconds=round(duration, 2),
        total_records=result.sales_count + result.inventory_count,
    )

    return schemas.GenerateResult(
        success=True,
        records_created={
            "stores": result.stores_count,
            "products": result.products_count,
            "calendar": result.calendar_days,
            "sales": result.sales_count,
            "price_history": result.price_history_count,
            "promotions": result.promotions_count,
            "inventory": result.inventory_count,
        },
        duration_seconds=round(duration, 2),
        message=f"Successfully generated {result.sales_count:,} sales records with seed {params.seed}",
        seed=params.seed,
    )


async def append_data(
    db: AsyncSession,
    params: schemas.AppendParams,
) -> schemas.GenerateResult:
    """Append data to existing dataset.

    Args:
        db: Async database session.
        params: Append parameters.

    Returns:
        GenerateResult with counts and timing.

    Raises:
        ValueError: If no existing dimensions found.
    """
    settings = get_settings()

    # Production guard
    if not settings.seeder_allow_production and settings.app_env == "production":
        logger.warning("seeder.append.blocked", reason="production_guard")
        raise ValueError("Seeder operations are not allowed in production environment")

    logger.info(
        "seeder.append.started",
        seed=params.seed,
        start_date=str(params.start_date),
        end_date=str(params.end_date),
    )

    start_time = time.perf_counter()

    config = SeederConfig(
        seed=params.seed,
        start_date=params.start_date,
        end_date=params.end_date,
        batch_size=settings.seeder_batch_size,
    )
    seeder = DataSeeder(config)

    result = await seeder.append_data(db, params.start_date, params.end_date)

    duration = time.perf_counter() - start_time

    logger.info(
        "seeder.append.completed",
        seed=params.seed,
        duration_seconds=round(duration, 2),
        sales_appended=result.sales_count,
    )

    return schemas.GenerateResult(
        success=True,
        records_created={
            "stores": result.stores_count,
            "products": result.products_count,
            "calendar": result.calendar_days,
            "sales": result.sales_count,
            "price_history": result.price_history_count,
            "promotions": result.promotions_count,
            "inventory": result.inventory_count,
        },
        duration_seconds=round(duration, 2),
        message=f"Appended {result.sales_count:,} sales records for date range {params.start_date} to {params.end_date}",
        seed=params.seed,
    )


async def delete_data(
    db: AsyncSession,
    params: schemas.DeleteParams,
) -> schemas.DeleteResult:
    """Delete data with specified scope.

    Args:
        db: Async database session.
        params: Delete parameters.

    Returns:
        DeleteResult with counts and status.

    Raises:
        ValueError: If production guard is enabled.
    """
    settings = get_settings()

    # Production guard
    if not settings.seeder_allow_production and settings.app_env == "production":
        logger.warning("seeder.delete.blocked", reason="production_guard")
        raise ValueError("Seeder operations are not allowed in production environment")

    logger.info(
        "seeder.delete.started",
        scope=params.scope,
        dry_run=params.dry_run,
    )

    config = SeederConfig(batch_size=settings.seeder_batch_size)
    seeder = DataSeeder(config)

    counts = await seeder.delete_data(db, scope=params.scope, dry_run=params.dry_run)

    total_deleted = sum(counts.values())

    if params.dry_run:
        message = f"Dry run: would delete {total_deleted:,} records (scope: {params.scope})"
    else:
        message = f"Deleted {total_deleted:,} records (scope: {params.scope})"

    logger.info(
        "seeder.delete.completed",
        scope=params.scope,
        dry_run=params.dry_run,
        total_deleted=total_deleted,
    )

    return schemas.DeleteResult(
        success=True,
        records_deleted=counts,
        message=message,
        dry_run=params.dry_run,
    )


async def verify_data(db: AsyncSession) -> schemas.VerifyResult:
    """Run data integrity verification.

    Args:
        db: Async database session.

    Returns:
        VerifyResult with check results.
    """
    logger.info("seeder.verify.started")

    checks: list[schemas.VerifyCheck] = []
    settings = get_settings()

    config = SeederConfig(batch_size=settings.seeder_batch_size)
    seeder = DataSeeder(config)

    # Run basic integrity checks
    errors = await seeder.verify_data_integrity(db)

    # Check 1: Foreign key integrity
    fk_errors = [e for e in errors if "foreign key" in e.lower()]
    checks.append(
        schemas.VerifyCheck(
            name="Foreign Key Integrity",
            status="failed" if fk_errors else "passed",
            message="All foreign key references are valid" if not fk_errors else fk_errors[0],
            details=fk_errors if fk_errors else None,
        )
    )

    # Check 2: Non-negative constraints
    neg_errors = [e for e in errors if "negative" in e.lower()]
    checks.append(
        schemas.VerifyCheck(
            name="Non-Negative Constraints",
            status="failed" if neg_errors else "passed",
            message="All quantities and prices are non-negative"
            if not neg_errors
            else neg_errors[0],
            details=neg_errors if neg_errors else None,
        )
    )

    # Check 3: Calendar coverage
    calendar_errors = [e for e in errors if "calendar" in e.lower() or "gap" in e.lower()]
    checks.append(
        schemas.VerifyCheck(
            name="Calendar Date Coverage",
            status="warning" if calendar_errors else "passed",
            message="Calendar has gaps in date sequence"
            if calendar_errors
            else "Calendar dates are contiguous",
            details=calendar_errors if calendar_errors else None,
        )
    )

    # Check 4: Data presence
    status = await get_status(db)
    has_data = status.sales > 0
    checks.append(
        schemas.VerifyCheck(
            name="Data Presence",
            status="passed" if has_data else "warning",
            message=f"{status.sales:,} sales records found" if has_data else "No sales data found",
        )
    )

    # Check 5: Dimension completeness
    has_dimensions = status.stores > 0 and status.products > 0 and status.calendar > 0
    checks.append(
        schemas.VerifyCheck(
            name="Dimension Completeness",
            status="passed" if has_dimensions else "warning",
            message="All dimension tables populated"
            if has_dimensions
            else "Missing dimension data",
            details=[
                f"Stores: {status.stores}",
                f"Products: {status.products}",
                f"Calendar: {status.calendar}",
            ],
        )
    )

    # Calculate summary
    passed_count = sum(1 for c in checks if c.status == "passed")
    warning_count = sum(1 for c in checks if c.status == "warning")
    failed_count = sum(1 for c in checks if c.status == "failed")

    # Overall pass if no failures
    passed = failed_count == 0

    logger.info(
        "seeder.verify.completed",
        passed=passed,
        total_checks=len(checks),
        passed_count=passed_count,
        warning_count=warning_count,
        failed_count=failed_count,
    )

    return schemas.VerifyResult(
        passed=passed,
        checks=checks,
        total_checks=len(checks),
        passed_count=passed_count,
        warning_count=warning_count,
        failed_count=failed_count,
    )
