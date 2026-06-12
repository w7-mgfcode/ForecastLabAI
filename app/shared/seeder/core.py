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
    ExogenousSignal,
    InventorySnapshotDaily,
    PriceHistory,
    Product,
    Promotion,
    ReplenishmentEvent,
    SalesDaily,
    SalesReturn,
    Store,
)
from app.shared.seeder.generators import (
    BundleGenerator,
    CalendarGenerator,
    ExogenousSignalGenerator,
    InventorySnapshotGenerator,
    LifecycleGenerator,
    MarkdownGenerator,
    PriceHistoryGenerator,
    ProductGenerator,
    PromotionGenerator,
    ReplenishmentGenerator,
    ReturnsGenerator,
    SalesDailyGenerator,
    StoreGenerator,
    build_price_lookup,
)
from app.shared.seeder.generators.exogenous import WEATHER_SIGNAL_NAME

if TYPE_CHECKING:
    from app.shared.seeder.config import SeederConfig

logger = get_logger(__name__)


# Canonical promotion-row shape — every record inserted into the
# ``promotion`` table must carry exactly these keys so the bulk
# ``pg_insert(...).values([...])`` builds a uniform VALUES clause.
# Defaults match the SQL server defaults / CHECK constraint:
# ``kind`` defaults to ``"pct_off"`` (server default) and
# ``bundle_member_product_ids`` is NULL unless ``kind in (bundle, bogo)``.
_PROMOTION_DEFAULTS: dict[str, Any] = {
    "kind": "pct_off",
    "discount_pct": None,
    "discount_amount": None,
    "bundle_member_product_ids": None,
}


def _normalize_promotion_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure every promotion record carries the canonical key set.

    ``PromotionGenerator`` emits records without ``kind`` /
    ``bundle_member_product_ids``; ``BundleGenerator`` mutates a subset
    of those into ``bogo`` / ``bundle`` rows; ``MarkdownGenerator``
    appends ``kind='markdown'`` rows. PostgreSQL multi-row INSERT
    requires uniform keys across the batch, so we patch missing keys
    with their schema defaults in place.

    Existing values are preserved — ``setdefault`` only fills gaps.
    """
    for record in records:
        for key, default in _PROMOTION_DEFAULTS.items():
            record.setdefault(key, default)
    return records


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
        exogenous_count: Number of exogenous signal records (Phase 1).
        returns_count: Number of sales return records (Phase 1).
        replenishment_count: Number of replenishment_event records (Phase 2).
        seed: Random seed used.
    """

    stores_count: int = 0
    products_count: int = 0
    calendar_days: int = 0
    sales_count: int = 0
    price_history_count: int = 0
    promotions_count: int = 0
    inventory_count: int = 0
    exogenous_count: int = 0
    returns_count: int = 0
    replenishment_count: int = 0
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
    ) -> tuple[
        list[int],
        list[tuple[int, Decimal]],
        list[date],
        dict[int, tuple[date | None, date | None]],
    ]:
        """Generate and insert dimension tables.

        Args:
            db: Async database session.

        Returns:
            Tuple of ``(store_ids, product_data, dates,
            product_lifecycle_data)``. ``product_lifecycle_data`` maps
            ``product_id -> (launch_date, discontinue_date)``. When
            lifecycle is disabled the dict is still returned but every
            value is ``(None, None)`` so the downstream multiplier
            short-circuits to 1.0.
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

        # Generate products. Phase 2: pass lifecycle config + date_range
        # when lifecycle is enabled so product rows pick up launch /
        # discontinue / stage attributes. Disabled path is byte-identical.
        product_gen = ProductGenerator(
            self.rng,
            self.config.dimensions,
            lifecycle_config=self.config.lifecycle,
            date_range=(self.config.start_date, self.config.end_date),
        )
        product_records = product_gen.generate()

        logger.info(
            "seeder.products.generating",
            count=len(product_records),
        )

        await self._batch_insert(db, Product, product_records)

        # Fetch product IDs with base prices + lifecycle dates. Single
        # query keeps the row-set consistent (re-querying could race
        # with concurrent writers, though seeder is single-tenant).
        rows = (
            await db.execute(
                select(
                    Product.id,
                    Product.base_price,
                    Product.launch_date,
                    Product.discontinue_date,
                )
            )
        ).fetchall()
        product_data = [(row[0], row[1] or Decimal("9.99")) for row in rows]
        product_lifecycle_data: dict[int, tuple[date | None, date | None]] = {
            row[0]: (row[2], row[3]) for row in rows
        }

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

        return store_ids, product_data, dates, product_lifecycle_data

    async def _generate_exogenous(
        self,
        db: AsyncSession,
        store_ids: list[int],
        dates: list[date],
    ) -> tuple[int, dict[tuple[int, date], float]]:
        """Generate exogenous signals (Phase 1).

        Returns:
            Tuple of (rows_inserted, weather_lookup) where ``weather_lookup``
            is ``{(store_id, date): temp_c}`` for downstream demand math.
            Empty dict if weather is disabled.
        """
        exo_gen = ExogenousSignalGenerator(self.rng, self.config.exogenous)
        records = exo_gen.generate(dates, store_ids)

        if not records:
            return 0, {}

        logger.info("seeder.exogenous.generating", count=len(records))
        inserted = await self._batch_insert(db, ExogenousSignal, records)

        weather_lookup: dict[tuple[int, date], float] = {}
        if self.config.exogenous.enable_weather:
            for r in records:
                if r["signal_name"] != WEATHER_SIGNAL_NAME:
                    continue
                store_id = r["store_id"]
                signal_date = r["date"]
                value = r["value"]
                if (
                    isinstance(store_id, int)
                    and isinstance(signal_date, date)
                    and isinstance(value, float)
                ):
                    weather_lookup[(store_id, signal_date)] = value

        return inserted, weather_lookup

    async def _generate_facts(
        self,
        db: AsyncSession,
        store_ids: list[int],
        product_data: list[tuple[int, Decimal]],
        dates: list[date],
        weather_lookup: dict[tuple[int, date], float] | None = None,
        product_lifecycle_data: dict[int, tuple[date | None, date | None]] | None = None,
    ) -> tuple[int, int, int, int, int, int]:
        """Generate and insert fact tables.

        Args:
            db: Async database session.
            store_ids: List of store IDs.
            product_data: List of (product_id, base_price) tuples.
            dates: List of dates.
            weather_lookup: Optional ``{(store_id, date): temp_c}`` from the
                exogenous generator. Demand picks up weather sensitivity only
                when this dict is non-empty AND
                ``config.exogenous.weather_temperature_sensitivity`` is non-zero.
            product_lifecycle_data: Optional Phase 2 mapping
                ``product_id -> (launch_date, discontinue_date)``. Consumed
                by ``SalesDailyGenerator``'s lifecycle multiplier and by
                ``MarkdownGenerator`` for the ``lifecycle_decline`` trigger.

        Returns:
            Tuple of (sales_count, price_history_count, promotions_count,
            inventory_count, returns_count, replenishment_count).
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

        # Phase 2: convert a slice of promotions to bundle/BOGO in place.
        # Disabled path is a no-op (zero rng draws, no mutation).
        bundle_gen = BundleGenerator(self.rng, self.config.bundles)
        bundle_gen.apply(promo_records, product_ids)

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

        # Phase 2: emit markdown promo rows + price drops. Disabled path
        # returns empty containers and consumes zero rng. Built BEFORE
        # promotion insert so markdown rows ship in the same batch.
        lifecycle_gen = LifecycleGenerator(self.config.lifecycle)
        product_specs: list[dict[str, Any]] = [
            {
                "product_id": pid,
                "base_price": price,
                "launch_date": (product_lifecycle_data or {}).get(pid, (None, None))[0],
                "discontinue_date": (product_lifecycle_data or {}).get(pid, (None, None))[1],
            }
            for pid, price in product_data
        ]
        markdown_gen = MarkdownGenerator(self.rng, self.config.markdowns)
        (
            markdown_promo_records,
            markdown_price_records,
            _markdown_dates,
        ) = markdown_gen.generate(
            product_specs=product_specs,
            store_ids=store_ids,
            stockout_dates=stockout_dates,
            dates=dates,
            lifecycle=lifecycle_gen,
            inventory_records=inventory_records,
        )

        # Merge markdown outputs into the main lists, then normalize so
        # every promotion row carries the same key set (required for
        # pg_insert multi-row INSERT). The disabled-path lists are empty
        # so the merge is a no-op.
        promo_records.extend(markdown_promo_records)
        price_records.extend(markdown_price_records)
        _normalize_promotion_records(promo_records)

        logger.info(
            "seeder.price_history.generating",
            count=len(price_records),
        )
        await self._batch_insert(db, PriceHistory, price_records)

        logger.info(
            "seeder.promotions.generating",
            count=len(promo_records),
        )
        await self._batch_insert(db, Promotion, promo_records)

        logger.info(
            "seeder.inventory.generating",
            count=len(inventory_records),
        )
        await self._batch_insert(db, InventorySnapshotDaily, inventory_records)

        # Generate sales (depends on promotions and stockouts). Phase 1
        # extensions stay as None / 0 when their config flags are off so the
        # disabled-path is byte-identical with pre-Phase-1. Phase 2
        # lifecycle / channels are gated by their own enable flags inside
        # the generator.
        weather_lookup_for_sales = (
            weather_lookup
            if weather_lookup and self.config.exogenous.weather_temperature_sensitivity != 0.0
            else None
        )
        # Price/sales coupling (issue #237): thread the generated price
        # windows (incl. Phase 2 markdowns merged above) into the sales
        # generator so unit_price follows price_history and demand responds
        # via retail.price_elasticity. None preserves the legacy path
        # byte-for-byte — same gating convention as weather_lookup_for_sales.
        price_lookup_for_sales = (
            build_price_lookup(price_records) if self.config.retail.price_sales_coupling else None
        )
        sales_gen = SalesDailyGenerator(
            self.rng,
            self.config.time_series,
            self.config.retail,
            self.config.sparsity,
            self.config.holidays,
            multi_seasonality=self.config.multi_seasonality,
            changepoints=self.config.changepoints,
            substitution=self.config.substitution,
            exogenous_weather=weather_lookup_for_sales,
            weather_temperature_sensitivity=(self.config.exogenous.weather_temperature_sensitivity),
            weather_climatology_mean_c=self.config.exogenous.weather_climatology_mean_c,
            lifecycle=lifecycle_gen,
            channels=self.config.channels,
        )
        sales_records = sales_gen.generate(
            store_ids,
            product_data,
            dates,
            promo_dates,
            stockout_dates,
            product_lifecycle_data=product_lifecycle_data,
            price_lookup=price_lookup_for_sales,
        )

        logger.info(
            "seeder.sales.generating",
            count=len(sales_records),
        )

        await self._batch_insert(db, SalesDaily, sales_records)

        # Generate returns (Phase 1) — depends on sales. Returns config is
        # disabled by default; generator short-circuits to an empty list.
        returns_gen = ReturnsGenerator(self.rng, self.config.returns)
        returns_records = returns_gen.generate(sales_records, self.config.end_date)
        if returns_records:
            logger.info("seeder.returns.generating", count=len(returns_records))
            await self._batch_insert(db, SalesReturn, returns_records)

        # Phase 2: emit replenishment_event rows. Disabled path returns
        # an empty list and consumes zero rng.
        replenishment_gen = ReplenishmentGenerator(self.rng, self.config.lead_time)
        replenishment_records = replenishment_gen.generate(
            store_ids,
            product_ids,
            dates,
            base_demand=self.config.time_series.base_demand,
        )
        if replenishment_records:
            logger.info("seeder.replenishment.generating", count=len(replenishment_records))
            await self._batch_insert(db, ReplenishmentEvent, replenishment_records)

        return (
            len(sales_records),
            len(price_records),
            len(promo_records),
            len(inventory_records),
            len(returns_records),
            len(replenishment_records),
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
        (
            store_ids,
            product_data,
            dates,
            product_lifecycle_data,
        ) = await self._generate_dimensions(db)

        # Phase 1: generate exogenous signals (no-op when no signal is enabled).
        exogenous_count, weather_lookup = await self._generate_exogenous(db, store_ids, dates)

        # Generate facts
        (
            sales_count,
            price_count,
            promo_count,
            inventory_count,
            returns_count,
            replenishment_count,
        ) = await self._generate_facts(
            db,
            store_ids,
            product_data,
            dates,
            weather_lookup,
            product_lifecycle_data=product_lifecycle_data,
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
            exogenous_count=exogenous_count,
            returns_count=returns_count,
            replenishment_count=replenishment_count,
            seed=self.config.seed,
        )

        logger.info(
            "seeder.full_generation.completed",
            stores=result.stores_count,
            products=result.products_count,
            calendar_days=result.calendar_days,
            sales=result.sales_count,
            exogenous=result.exogenous_count,
            returns=result.returns_count,
            replenishment=result.replenishment_count,
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

        # Fetch existing product data (with lifecycle dates for Phase 2).
        # Lifecycle multiplier short-circuits to 1.0 for products with
        # NULL launch_date so the disabled path is byte-identical.
        rows = (
            await db.execute(
                select(
                    Product.id,
                    Product.base_price,
                    Product.launch_date,
                    Product.discontinue_date,
                )
            )
        ).fetchall()
        product_data = [(row[0], row[1] or Decimal("9.99")) for row in rows]
        product_lifecycle_data: dict[int, tuple[date | None, date | None]] = {
            row[0]: (row[2], row[3]) for row in rows
        }

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

        # Phase 1: append exogenous signals for the new range (no-op when off).
        exogenous_count, weather_lookup = await self._generate_exogenous(db, store_ids, dates)

        # Generate facts for new date range
        (
            sales_count,
            price_count,
            promo_count,
            inventory_count,
            returns_count,
            replenishment_count,
        ) = await self._generate_facts(
            db,
            store_ids,
            product_data,
            dates,
            weather_lookup,
            product_lifecycle_data=product_lifecycle_data,
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
            exogenous_count=exogenous_count,
            returns_count=returns_count,
            replenishment_count=replenishment_count,
            seed=self.config.seed,
        )

        logger.info(
            "seeder.append.completed",
            calendar_days=result_data.calendar_days,
            sales=result_data.sales_count,
            exogenous=result_data.exogenous_count,
            returns=result_data.returns_count,
            replenishment=result_data.replenishment_count,
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

        # Get current counts. Phase 2 ``replenishment_event`` leads — it
        # FKs to store/product/calendar but no other table FKs into it,
        # so dropping first removes the leaf safely. Phase 1 tables come
        # next (sales_returns FKs to product/store, exogenous_signal FKs
        # to store/calendar), then the older fact tables. The order keeps
        # the dimension/calendar wipe free of FK violations.
        fact_tables = [
            ("replenishment_event", ReplenishmentEvent),
            ("sales_returns", SalesReturn),
            ("exogenous_signal", ExogenousSignal),
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
            ("exogenous_signal", ExogenousSignal),
            ("sales_returns", SalesReturn),
            ("replenishment_event", ReplenishmentEvent),
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

        # Phase 1: sales_returns must never carry quantity <= 0 (CHECK
        # constraint guards this at the DB layer, but a defensive count
        # catches drift if a future generator drops the invariant).
        neg_return_check = text("SELECT COUNT(*) FROM sales_returns WHERE return_quantity < 1")
        result = await db.execute(neg_return_check)
        neg_returns = result.scalar() or 0
        if neg_returns > 0:
            errors.append(f"Found {neg_returns} sales_returns with non-positive quantity")

        # Phase 1: exogenous_signal global/per-store consistency.
        bad_global_check = text(
            "SELECT COUNT(*) FROM exogenous_signal "
            "WHERE (is_global = true AND store_id IS NOT NULL) "
            "   OR (is_global = false AND store_id IS NULL)"
        )
        result = await db.execute(bad_global_check)
        bad_global = result.scalar() or 0
        if bad_global > 0:
            errors.append(
                f"Found {bad_global} exogenous_signal rows violating "
                "is_global / store_id consistency"
            )

        # Phase 2: bundle / BOGO promotions must declare their member
        # product IDs. The CHECK constraint enforces this at the DB
        # layer; the count below catches generator drift early.
        bundle_consistency_check = text(
            "SELECT COUNT(*) FROM promotion "
            "WHERE kind IN ('bundle', 'bogo') AND bundle_member_product_ids IS NULL"
        )
        result = await db.execute(bundle_consistency_check)
        bad_bundles = result.scalar() or 0
        if bad_bundles > 0:
            errors.append(
                f"Found {bad_bundles} bundle/BOGO promotions with NULL bundle_member_product_ids"
            )

        # Phase 2: lifecycle date ordering — discontinue_date must be
        # on or after launch_date when both are set. Also caught by the
        # ``ck_product_lifecycle_date_order`` CHECK; defensive count for
        # generator drift.
        bad_lifecycle_check = text(
            "SELECT COUNT(*) FROM product "
            "WHERE discontinue_date IS NOT NULL AND launch_date IS NOT NULL "
            "  AND discontinue_date < launch_date"
        )
        result = await db.execute(bad_lifecycle_check)
        bad_lifecycle = result.scalar() or 0
        if bad_lifecycle > 0:
            errors.append(f"Found {bad_lifecycle} products with discontinue_date < launch_date")

        # Phase 2: replenishment fill rate — received_qty must never
        # exceed ordered_qty. DB-enforced; defensive count.
        bad_fill_check = text(
            "SELECT COUNT(*) FROM replenishment_event WHERE received_qty > ordered_qty"
        )
        result = await db.execute(bad_fill_check)
        bad_fill = result.scalar() or 0
        if bad_fill > 0:
            errors.append(
                f"Found {bad_fill} replenishment_event rows with received_qty > ordered_qty"
            )

        return errors
