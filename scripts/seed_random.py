#!/usr/bin/env python
"""Randomized database seeder CLI - The Forge.

Generate synthetic test data for ForecastLabAI with realistic time-series patterns.

Usage:
    # Generate complete dataset
    uv run python scripts/seed_random.py --full-new --seed 42 --confirm

    # Delete all data
    uv run python scripts/seed_random.py --delete --confirm

    # Append data for new date range
    uv run python scripts/seed_random.py --append --start-date 2025-01-01 --end-date 2025-03-31

    # Run pre-built scenario
    uv run python scripts/seed_random.py --full-new --scenario holiday_rush --confirm

    # Preview deletion
    uv run python scripts/seed_random.py --delete --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.shared.seeder import DataSeeder, ScenarioPreset, SeederConfig
from app.shared.seeder.config import (
    DimensionConfig,
    HolidayConfig,
    RetailPatternConfig,
    SparsityConfig,
    TimeSeriesConfig,
)
from app.shared.seeder.rag_scenario import run_rag_scenario


def parse_date(date_str: str) -> date:
    """Parse date string in YYYY-MM-DD format.

    Args:
        date_str: Date string.

    Returns:
        Parsed date object.

    Raises:
        argparse.ArgumentTypeError: If date format is invalid.
    """
    try:
        parts = date_str.split("-")
        if len(parts) != 3:
            raise ValueError("Invalid format")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError) as e:
        raise argparse.ArgumentTypeError(f"Invalid date format: {date_str}. Use YYYY-MM-DD") from e


def load_config_from_yaml(path: Path) -> SeederConfig:
    """Load seeder configuration from YAML file.

    Args:
        path: Path to YAML config file.

    Returns:
        SeederConfig loaded from file.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValueError: If config file is invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open() as f:
        data = yaml.safe_load(f)

    # Parse dimensions
    dimensions_data = data.get("dimensions", {})
    dimensions = DimensionConfig(
        stores=dimensions_data.get("stores", {}).get("count", 10),
        products=dimensions_data.get("products", {}).get("count", 50),
        store_regions=dimensions_data.get("stores", {}).get(
            "regions", ["North", "South", "East", "West"]
        ),
        store_types=dimensions_data.get("stores", {}).get(
            "types", ["supermarket", "express", "warehouse"]
        ),
        product_categories=dimensions_data.get("products", {}).get(
            "categories", ["Beverage", "Snack", "Dairy", "Frozen"]
        ),
        product_brands=dimensions_data.get("products", {}).get(
            "brands", ["BrandA", "BrandB", "Generic"]
        ),
    )

    # Parse date range
    date_range = data.get("date_range", {})
    start_date = parse_date(date_range["start"]) if "start" in date_range else date(2024, 1, 1)
    end_date = parse_date(date_range["end"]) if "end" in date_range else date(2024, 12, 31)

    # Parse time series config
    ts_data = data.get("time_series", {})
    time_series = TimeSeriesConfig(
        base_demand=ts_data.get("base_demand", 100),
        trend=ts_data.get("trend", "none"),
        trend_slope=ts_data.get("trend_slope", 0.001),
        noise_sigma=ts_data.get("noise_sigma", 0.1),
        monthly_seasonality=ts_data.get("monthly_seasonality", {}),
    )

    # Parse retail config
    retail_data = data.get("retail", {})
    retail = RetailPatternConfig(
        promotion_probability=retail_data.get("promotion_probability", 0.1),
        stockout_probability=retail_data.get("stockout_probability", 0.02),
        promotion_lift=retail_data.get("promotion_lift", 1.3),
    )

    # Parse sparsity config
    sparsity_data = data.get("sparsity", {})
    sparsity = SparsityConfig(
        missing_combinations_pct=sparsity_data.get("missing_combinations_pct", 0.0),
        random_gaps_per_series=sparsity_data.get("random_gaps_per_series", 0),
    )

    # Parse holidays
    holidays: list[HolidayConfig] = []
    for h in data.get("holidays", []):
        holidays.append(
            HolidayConfig(
                date=parse_date(h["date"]),
                name=h["name"],
                multiplier=h.get("multiplier", 1.5),
            )
        )

    return SeederConfig(
        seed=data.get("seed", 42),
        start_date=start_date,
        end_date=end_date,
        dimensions=dimensions,
        time_series=time_series,
        retail=retail,
        sparsity=sparsity,
        holidays=holidays,
        batch_size=data.get("batch_size", 1000),
    )


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for CLI."""
    parser = argparse.ArgumentParser(
        description="ForecastLabAI Randomized Database Seeder (The Forge)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate standard dataset
  seed_random.py --full-new --seed 42 --confirm

  # Holiday scenario with 20 stores
  seed_random.py --full-new --scenario holiday_rush --stores 20 --confirm

  # Preview deletion
  seed_random.py --delete --dry-run

  # Append 3 months
  seed_random.py --append --start-date 2025-01-01 --end-date 2025-03-31

  # Load config from YAML
  seed_random.py --full-new --config examples/seed/config_holiday.yaml --confirm
        """,
    )

    # Operation modes (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--full-new",
        action="store_true",
        help="Generate complete dataset from scratch",
    )
    mode_group.add_argument(
        "--delete",
        action="store_true",
        help="Delete generated data",
    )
    mode_group.add_argument(
        "--append",
        action="store_true",
        help="Append data to existing dataset",
    )
    mode_group.add_argument(
        "--status",
        action="store_true",
        help="Show current data counts",
    )
    mode_group.add_argument(
        "--verify",
        action="store_true",
        help="Verify data integrity",
    )
    mode_group.add_argument(
        "--run-scenario",
        action="store_true",
        help="Run a standalone scenario (use with --scenario)",
    )

    # Data generation options
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--stores",
        type=int,
        default=10,
        help="Number of stores to generate (default: 10)",
    )
    parser.add_argument(
        "--products",
        type=int,
        default=50,
        help="Number of products to generate (default: 50)",
    )
    parser.add_argument(
        "--start-date",
        type=parse_date,
        default=date(2024, 1, 1),
        help="Start of date range (default: 2024-01-01)",
    )
    parser.add_argument(
        "--end-date",
        type=parse_date,
        default=date(2024, 12, 31),
        help="End of date range (default: 2024-12-31)",
    )
    parser.add_argument(
        "--sparsity",
        type=float,
        default=0.0,
        help="Fraction of missing store/product combinations (default: 0.0)",
    )

    # Scenario and config
    parser.add_argument(
        "--scenario",
        choices=[s.value for s in ScenarioPreset] + ["rag-agent"],
        help="Run pre-built scenario (rag-agent is special E2E test)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Load configuration from YAML file",
    )

    # Delete options
    parser.add_argument(
        "--scope",
        choices=["all", "facts", "dimensions"],
        default="all",
        help="Deletion scope (default: all)",
    )

    # Safety options
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm destructive operations",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without executing",
    )

    # Other options
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed logging",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Batch insert size (default: 1000)",
    )

    return parser


async def get_session() -> AsyncSession:
    """Create database session."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return session_maker()


def print_banner() -> None:
    """Print the Forge banner."""
    print()
    print("=" * 60)
    print("  ForecastLabAI - The Forge")
    print("  Randomized Database Seeder")
    print("=" * 60)
    print()


def print_counts(counts: dict[str, int], title: str = "Current Data Counts") -> None:
    """Print table counts in a formatted way."""
    print(f"\n{title}:")
    print("-" * 40)
    for table, count in counts.items():
        print(f"  {table:<30} {count:>8,}")
    print("-" * 40)
    print(f"  {'Total':<30} {sum(counts.values()):>8,}")
    print()


async def run_full_new(
    args: argparse.Namespace,
    session: AsyncSession,
) -> int:
    """Run full new generation."""
    settings = get_settings()

    # Safety check for production
    if settings.is_production and not settings.seeder_allow_production:
        print("ERROR: Cannot run seeder in production environment.")
        print("Set SEEDER_ALLOW_PRODUCTION=true to override (not recommended).")
        return 1

    # Confirmation check
    if settings.seeder_require_confirm and not args.confirm:
        print("ERROR: --confirm flag required for data generation.")
        print("This will create new data. Use --confirm to proceed.")
        return 1

    # Build configuration
    if args.config:
        print(f"Loading configuration from: {args.config}")
        config = load_config_from_yaml(args.config)
    elif args.scenario:
        # Validate scenario is a valid ScenarioPreset (not "rag-agent" which is standalone)
        valid_presets = {s.value for s in ScenarioPreset}
        if args.scenario not in valid_presets:
            print(f"ERROR: '{args.scenario}' is not a valid scenario for --full-new.")
            print(f"Valid scenarios: {', '.join(sorted(valid_presets))}")
            print("Note: 'rag-agent' is a standalone scenario. Use --run-scenario instead.")
            return 1
        print(f"Using scenario: {args.scenario}")
        config = SeederConfig.from_scenario(ScenarioPreset(args.scenario), seed=args.seed)
    else:
        config = SeederConfig(
            seed=args.seed,
            start_date=args.start_date,
            end_date=args.end_date,
            dimensions=DimensionConfig(
                stores=args.stores,
                products=args.products,
            ),
            sparsity=SparsityConfig(missing_combinations_pct=args.sparsity),
            batch_size=args.batch_size,
        )

    print("Configuration:")
    print(f"  Seed: {config.seed}")
    print(f"  Stores: {config.dimensions.stores}")
    print(f"  Products: {config.dimensions.products}")
    print(f"  Date range: {config.start_date} to {config.end_date}")
    print()

    seeder = DataSeeder(config)
    result = await seeder.generate_full(session)

    print("\nGeneration Complete!")
    print("-" * 40)
    print(f"  Stores:           {result.stores_count:>8,}")
    print(f"  Products:         {result.products_count:>8,}")
    print(f"  Calendar days:    {result.calendar_days:>8,}")
    print(f"  Sales records:    {result.sales_count:>8,}")
    print(f"  Price history:    {result.price_history_count:>8,}")
    print(f"  Promotions:       {result.promotions_count:>8,}")
    print(f"  Inventory snaps:  {result.inventory_count:>8,}")
    print("-" * 40)
    print(f"  Seed used:        {result.seed}")
    print()

    return 0


async def run_delete(
    args: argparse.Namespace,
    session: AsyncSession,
) -> int:
    """Run delete operation."""
    settings = get_settings()

    # Safety check for production
    if settings.is_production and not settings.seeder_allow_production:
        print("ERROR: Cannot run seeder in production environment.")
        return 1

    # Dry run mode
    if args.dry_run:
        print("DRY RUN - No data will be deleted")
        print()

    # Confirmation check
    if not args.dry_run and settings.seeder_require_confirm and not args.confirm:
        print("ERROR: --confirm flag required for data deletion.")
        print("Use --dry-run to preview or --confirm to proceed.")
        return 1

    config = SeederConfig(seed=args.seed)
    seeder = DataSeeder(config)

    scope: Literal["all", "facts", "dimensions"] = args.scope
    counts = await seeder.delete_data(session, scope=scope, dry_run=args.dry_run)

    action = "Would delete" if args.dry_run else "Deleted"
    print_counts(counts, title=f"{action} ({scope})")

    return 0


async def run_append(
    args: argparse.Namespace,
    session: AsyncSession,
) -> int:
    """Run append operation."""
    settings = get_settings()

    # Safety check for production
    if settings.is_production and not settings.seeder_allow_production:
        print("ERROR: Cannot run seeder in production environment.")
        return 1

    print(f"Appending data for date range: {args.start_date} to {args.end_date}")
    print()

    config = SeederConfig(
        seed=args.seed,
        start_date=args.start_date,
        end_date=args.end_date,
        batch_size=args.batch_size,
    )
    seeder = DataSeeder(config)

    try:
        result = await seeder.append_data(session, args.start_date, args.end_date)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1

    print("\nAppend Complete!")
    print("-" * 40)
    print(f"  Calendar days added:  {result.calendar_days:>8,}")
    print(f"  Sales records added:  {result.sales_count:>8,}")
    print(f"  Price history added:  {result.price_history_count:>8,}")
    print(f"  Promotions added:     {result.promotions_count:>8,}")
    print(f"  Inventory added:      {result.inventory_count:>8,}")
    print("-" * 40)
    print()

    return 0


async def run_status(session: AsyncSession) -> int:
    """Show current data status."""
    config = SeederConfig()
    seeder = DataSeeder(config)
    counts = await seeder.get_current_counts(session)
    print_counts(counts)
    return 0


async def run_verify(session: AsyncSession) -> int:
    """Verify data integrity."""
    print("Verifying data integrity...")
    print()

    config = SeederConfig()
    seeder = DataSeeder(config)
    errors = await seeder.verify_data_integrity(session)

    if errors:
        print("ERRORS FOUND:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("All integrity checks passed!")
    return 0


async def run_rag_agent_scenario(args: argparse.Namespace) -> int:
    """Run RAG + Agent E2E validation scenario."""
    settings = get_settings()

    # Safety check for production
    if settings.is_production and not settings.seeder_allow_production:
        print("ERROR: Cannot run seeder scenarios in production environment.")
        return 1

    print("Running RAG + Agent E2E Scenario")
    print("-" * 40)
    print()

    api_base = f"http://{settings.api_host}:{settings.api_port}"
    if settings.api_host == "0.0.0.0":  # noqa: S104
        api_base = f"http://localhost:{settings.api_port}"

    result = await run_rag_scenario(
        api_base_url=api_base,
        seed=args.seed,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        print("DRY RUN - No actions taken")
        print(f"  Documents to index: {result.documents_indexed}")
        print("  Steps: index_docs -> create_session -> query -> verify -> cleanup")
        return 0

    print("Results:")
    print(f"  Documents indexed:   {result.documents_indexed}")
    print(f"  Session created:     {'Y' if result.session_created else 'N'}")
    print(f"  Query sent:          {'Y' if result.query_sent else 'N'}")
    print(f"  Response received:   {'Y' if result.response_received else 'N'}")
    print(f"  Citations found:     {'Y' if result.citations_found else 'N'}")
    print(f"  Cleanup completed:   {'Y' if result.cleanup_completed else 'N'}")
    print()

    if result.errors:
        print("Errors:")
        for error in result.errors:
            print(f"  - {error}")
        return 1

    print("RAG + Agent scenario completed successfully!")
    return 0


async def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    print_banner()

    # Handle --run-scenario mode (for standalone scenarios like rag-agent)
    if args.run_scenario:
        if not args.scenario:
            print("ERROR: --run-scenario requires --scenario to specify which scenario to run.")
            return 1
        if args.scenario == "rag-agent":
            return await run_rag_agent_scenario(args)
        else:
            print(f"ERROR: Scenario '{args.scenario}' is not a standalone scenario.")
            print("Use --full-new with --scenario for data generation scenarios.")
            return 1

    session = await get_session()

    try:
        if args.full_new:
            return await run_full_new(args, session)
        elif args.delete:
            return await run_delete(args, session)
        elif args.append:
            return await run_append(args, session)
        elif args.status:
            return await run_status(session)
        elif args.verify:
            return await run_verify(session)
        else:
            parser.print_help()
            return 1
    finally:
        await session.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
