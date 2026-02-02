"""Core seeder orchestration module."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.shared.seeder.generators import (
    CalendarGenerator,
    InventorySnapshotGenerator,
    PriceHistoryGenerator,
    ProductGenerator,
    PromotionGenerator,
    SalesDailyGenerator,
    StoreGenerator,
)

if TYPE_CHECKING:
    from app.shared.seeder.config import SeederConfig

logger = get_logger(__name__)


@dataclass
class SeederResult:
    """Result of a seeder operation.

    Attributes:
        stores_count: Number of stores generated/affected.
        products_count: Number of products generated/affected.
        calendar_days: Number of calendar days generated/affected.
        sales_count: Number of sales records generated/affected.
        price_history_count: Number of price history records.
        promotions_count: Number of promotions generated.
        inventory_count: Number of inventory snapshots.
        seed: Random seed used.
    """

    stores_count: int = 0
    products_count: int = 0
    calendar_days: int = 0
    sales_count: int = 0
    price_history_count: int = 0
    promotions_count: int = 0
    inventory_count: int = 0
    seed: int = 42


class DataSeeder:
    """Orchestrates synthetic data generation for the ForecastLabAI system.

    This class coordinates dimension and fact table generation with proper
    foreign key relationships and time-series patterns.
    """

    def __init__(self, config: SeederConfig) -> None:
        """Initialize the data seeder.

        Args:
            config: Seeder configuration.
        """
        self.config = config
        self.rng = random.Random(config.seed)

    async def _batch_insert(
        self,
        db: AsyncSession,
        table: type,
        records: list[dict[str, Any]],
        batch_size: int | None = None,
    ) -> int:
        """Insert records in batches.

        Args:
            db: Async database session.
            table: SQLAlchemy model class.
            records: List of record dictionaries.
            batch_size: Override batch size.

        Returns:
            Number of records inserted.
        """
        if not records:
            return 0

        size = batch_size or self.config.batch_size
        total_inserted = 0

        for i in range(0, len(records), size):
            batch = records[i : i + size]
            stmt = pg_insert(table).values(batch)
            # Use ON CONFLICT DO NOTHING for idempotent inserts
            stmt = stmt.on_conflict_do_nothing()
            cursor_result = await db.execute(stmt)
            # rowcount is available on CursorResult but not in Result type stubs
            row_count = getattr(cursor_result, "rowcount", None)
            # Use explicit None check to avoid treating 0 as falsy
            total_inserted += row_count if row_count is not None else len(batch)

        return total_inserted

    async def _generate_dimensions(
        self,
        db: AsyncSession,
    ) -> tuple[list[int], list[tuple[int, Decimal]], list[date]]:
        """Generate and insert dimension tables.

        Args:
            db: Async database session.

        Returns:
            Tuple of (store_ids, product_data, dates).
        """
        # Generate stores
        store_gen = StoreGenerator(self.rng, self.config.dimensions)
        store_records = store_gen.generate()

        logger.info(
            "seeder.stores.generating",
            count=len(store_records),
        )

        await self._batch_insert(db, Store, store_records)

        # Fetch store IDs
        result = await db.execute(select(Store.id))
        store_ids = [row[0] for row in result.fetchall()]

        # Generate products
        product_gen = ProductGenerator(self.rng, self.config.dimensions)
        product_records = product_gen.generate()

        logger.info(
            "seeder.products.generating",
            count=len(product_records),
        )

        await self._batch_insert(db, Product, product_records)

        # Fetch product IDs with base prices
        result = await db.execute(select(Product.id, Product.base_price))
        product_data = [(row[0], row[1] or Decimal("9.99")) for row in result.fetchall()]

        # Generate calendar
        calendar_gen = CalendarGenerator(
            self.config.start_date,
            self.config.end_date,
            self.config.holidays,
        )
        calendar_records = calendar_gen.generate()

        logger.info(
            "seeder.calendar.generating",
            count=len(calendar_records),
        )

        await self._batch_insert(db, Calendar, calendar_records)

        # Generate dates list
        dates: list[date] = []
        current = self.config.start_date
        while current <= self.config.end_date:
            dates.append(current)
            current += timedelta(days=1)

        return store_ids, product_data, dates

    async def _generate_facts(
        self,
        db: AsyncSession,
        store_ids: list[int],
        product_data: list[tuple[int, Decimal]],
        dates: list[date],
    ) -> tuple[int, int, int, int]:
        """Generate and insert fact tables.

        Args:
            db: Async database session.
            store_ids: List of store IDs.
            product_data: List of (product_id, base_price) tuples.
            dates: List of dates.

        Returns:
            Tuple of (sales_count, price_history_count, promotions_count, inventory_count).
        """
        product_ids = [pid for pid, _ in product_data]

        # Generate price history
        price_gen = PriceHistoryGenerator(self.rng)
        price_records = price_gen.generate(
            product_data,
            store_ids,
            self.config.start_date,
            self.config.end_date,
        )

        logger.info(
            "seeder.price_history.generating",
            count=len(price_records),
        )

        await self._batch_insert(db, PriceHistory, price_records)

        # Generate promotions
        promo_gen = PromotionGenerator(
            self.rng,
            promotion_probability=self.config.retail.promotion_probability,
        )
        promo_records, promo_dates = promo_gen.generate(
            product_ids,
            store_ids,
            self.config.start_date,
            self.config.end_date,
        )

        logger.info(
            "seeder.promotions.generating",
            count=len(promo_records),
        )

        await self._batch_insert(db, Promotion, promo_records)

        # Generate inventory snapshots
        inventory_gen = InventorySnapshotGenerator(
            self.rng,
            stockout_probability=self.config.retail.stockout_probability,
        )
        inventory_records, stockout_dates = inventory_gen.generate(
            store_ids,
            product_ids,
            dates,
        )

        logger.info(
            "seeder.inventory.generating",
            count=len(inventory_records),
        )

        await self._batch_insert(db, InventorySnapshotDaily, inventory_records)

        # Generate sales (depends on promotions and stockouts)
        sales_gen = SalesDailyGenerator(
            self.rng,
            self.config.time_series,
            self.config.retail,
            self.config.sparsity,
            self.config.holidays,
        )
        sales_records = sales_gen.generate(
            store_ids,
            product_data,
            dates,
            promo_dates,
            stockout_dates,
        )

        logger.info(
            "seeder.sales.generating",
            count=len(sales_records),
        )

        await self._batch_insert(db, SalesDaily, sales_records)

        return (
            len(sales_records),
            len(price_records),
            len(promo_records),
            len(inventory_records),
        )

    async def generate_full(self, db: AsyncSession) -> SeederResult:
        """Generate complete synthetic dataset from scratch.

        This generates all dimension and fact tables with the configured
        patterns and relationships.

        Args:
            db: Async database session.

        Returns:
            SeederResult with counts of generated records.
        """
        logger.info(
            "seeder.full_generation.started",
            seed=self.config.seed,
            stores=self.config.dimensions.stores,
            products=self.config.dimensions.products,
            start_date=str(self.config.start_date),
            end_date=str(self.config.end_date),
        )

        # Generate dimensions first
        store_ids, product_data, dates = await self._generate_dimensions(db)

        # Generate facts
        sales_count, price_count, promo_count, inventory_count = await self._generate_facts(
            db, store_ids, product_data, dates
        )

        # Commit all changes
        await db.commit()

        result = SeederResult(
            stores_count=len(store_ids),
            products_count=len(product_data),
            calendar_days=len(dates),
            sales_count=sales_count,
            price_history_count=price_count,
            promotions_count=promo_count,
            inventory_count=inventory_count,
            seed=self.config.seed,
        )

        logger.info(
            "seeder.full_generation.completed",
            stores=result.stores_count,
            products=result.products_count,
            calendar_days=result.calendar_days,
            sales=result.sales_count,
            seed=self.config.seed,
        )

        return result

    async def append_data(
        self,
        db: AsyncSession,
        start_date: date,
        end_date: date,
    ) -> SeederResult:
        """Append data to existing dataset without corrupting existing records.

        Uses existing dimension tables and generates new fact records for
        the specified date range.

        Args:
            db: Async database session.
            start_date: Start of new date range.
            end_date: End of new date range.

        Returns:
            SeederResult with counts of appended records.
        """
        logger.info(
            "seeder.append.started",
            seed=self.config.seed,
            start_date=str(start_date),
            end_date=str(end_date),
        )

        # Fetch existing store IDs
        result = await db.execute(select(Store.id))
        store_ids = [row[0] for row in result.fetchall()]

        if not store_ids:
            raise ValueError("No stores found. Run --full-new first to create dimensions.")

        # Fetch existing product data
        result = await db.execute(select(Product.id, Product.base_price))
        product_data = [(row[0], row[1] or Decimal("9.99")) for row in result.fetchall()]

        if not product_data:
            raise ValueError("No products found. Run --full-new first to create dimensions.")

        # Generate calendar for new date range
        calendar_gen = CalendarGenerator(start_date, end_date, self.config.holidays)
        calendar_records = calendar_gen.generate()

        logger.info(
            "seeder.calendar.appending",
            count=len(calendar_records),
        )

        await self._batch_insert(db, Calendar, calendar_records)

        # Generate dates list
        dates: list[date] = []
        current = start_date
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=1)

        # Generate facts for new date range
        sales_count, price_count, promo_count, inventory_count = await self._generate_facts(
            db, store_ids, product_data, dates
        )

        await db.commit()

        result_data = SeederResult(
            stores_count=0,  # No new stores
            products_count=0,  # No new products
            calendar_days=len(dates),
            sales_count=sales_count,
            price_history_count=price_count,
            promotions_count=promo_count,
            inventory_count=inventory_count,
            seed=self.config.seed,
        )

        logger.info(
            "seeder.append.completed",
            calendar_days=result_data.calendar_days,
            sales=result_data.sales_count,
        )

        return result_data

    async def delete_data(
        self,
        db: AsyncSession,
        scope: Literal["all", "facts", "dimensions"] = "all",
        dry_run: bool = False,
    ) -> dict[str, int]:
        """Delete generated data with safety guards.

        Args:
            db: Async database session.
            scope: What to delete (all, facts, dimensions).
            dry_run: If True, only preview what would be deleted.

        Returns:
            Dictionary of table names to row counts (deleted or would be deleted).
        """
        counts: dict[str, int] = {}

        # Get current counts
        fact_tables = [
            ("sales_daily", SalesDaily),
            ("inventory_snapshot_daily", InventorySnapshotDaily),
            ("price_history", PriceHistory),
            ("promotion", Promotion),
        ]
        dimension_tables = [
            ("store", Store),
            ("product", Product),
            ("calendar", Calendar),
        ]

        tables_to_delete: list[tuple[str, type]] = []

        if scope in ("all", "facts"):
            tables_to_delete.extend(fact_tables)
        if scope in ("all", "dimensions"):
            tables_to_delete.extend(dimension_tables)

        # Get counts
        for name, model in tables_to_delete:
            result = await db.execute(select(func.count()).select_from(model))
            count = result.scalar() or 0
            counts[name] = count

        if dry_run:
            logger.info(
                "seeder.delete.dry_run",
                scope=scope,
                counts=counts,
            )
            return counts

        # Delete in correct order (facts before dimensions due to FKs)
        if scope in ("all", "facts"):
            for name, model in fact_tables:
                logger.info(f"seeder.delete.{name}", count=counts.get(name, 0))
                await db.execute(delete(model))

        if scope in ("all", "dimensions"):
            # Must delete facts first if deleting dimensions
            if scope == "dimensions":
                # Get and log fact table counts before implicit deletion
                for fact_name, fact_model in fact_tables:
                    fact_result = await db.execute(select(func.count()).select_from(fact_model))
                    fact_count = fact_result.scalar() or 0
                    counts[fact_name] = fact_count
                    logger.info(
                        f"seeder.delete.{fact_name}",
                        count=fact_count,
                        reason="implicit_fk_cleanup",
                    )
                    await db.execute(delete(fact_model))

            for name, model in dimension_tables:
                logger.info(f"seeder.delete.{name}", count=counts.get(name, 0))
                await db.execute(delete(model))

        await db.commit()

        logger.info(
            "seeder.delete.completed",
            scope=scope,
            total_deleted=sum(counts.values()),
        )

        return counts

    async def get_current_counts(self, db: AsyncSession) -> dict[str, int]:
        """Get current row counts for all seeder-relevant tables.

        Args:
            db: Async database session.

        Returns:
            Dictionary of table names to row counts.
        """
        tables = [
            ("store", Store),
            ("product", Product),
            ("calendar", Calendar),
            ("sales_daily", SalesDaily),
            ("price_history", PriceHistory),
            ("promotion", Promotion),
            ("inventory_snapshot_daily", InventorySnapshotDaily),
        ]

        counts: dict[str, int] = {}
        for name, model in tables:
            result = await db.execute(select(func.count()).select_from(model))
            counts[name] = result.scalar() or 0

        return counts

    async def verify_data_integrity(self, db: AsyncSession) -> list[str]:
        """Verify data integrity after generation.

        Checks:
        - All sales have valid store/product/date references
        - Constraint compliance (positive quantities, valid dates)
        - No orphaned records

        Args:
            db: Async database session.

        Returns:
            List of error messages (empty if all checks pass).
        """
        errors: list[str] = []

        # Check for orphaned sales (should not exist due to FK constraints)
        orphan_check = text("""
            SELECT COUNT(*) FROM sales_daily s
            LEFT JOIN store st ON s.store_id = st.id
            LEFT JOIN product p ON s.product_id = p.id
            LEFT JOIN calendar c ON s.date = c.date
            WHERE st.id IS NULL OR p.id IS NULL OR c.date IS NULL
        """)
        result = await db.execute(orphan_check)
        orphan_count = result.scalar() or 0
        if orphan_count > 0:
            errors.append(f"Found {orphan_count} sales with invalid foreign keys")

        # Check for negative quantities
        neg_qty_check = text("SELECT COUNT(*) FROM sales_daily WHERE quantity < 0")
        result = await db.execute(neg_qty_check)
        neg_count = result.scalar() or 0
        if neg_count > 0:
            errors.append(f"Found {neg_count} sales with negative quantity")

        # Check calendar date coverage
        result = await db.execute(select(func.min(Calendar.date), func.max(Calendar.date)))
        row = result.fetchone()
        if row and row[0] and row[1]:
            min_date, max_date = row
            expected_days = (max_date - min_date).days + 1
            result = await db.execute(select(func.count()).select_from(Calendar))
            actual_days = result.scalar() or 0
            if actual_days != expected_days:
                errors.append(
                    f"Calendar gap detected: expected {expected_days} days, found {actual_days}"
                )

        return errors
