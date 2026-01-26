"""Ingest service with key resolution and batch upsert logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.features.data_platform.models import Calendar, Product, SalesDaily, Store
from app.features.ingest.schemas import IngestRowError, SalesDailyIngestRow

logger = get_logger(__name__)


@runtime_checkable
class KeyResolverProtocol(Protocol):
    """Protocol for key resolution services."""

    async def resolve_store_codes(self, db: AsyncSession, codes: set[str]) -> dict[str, int]:
        """Resolve store codes to store IDs."""
        ...

    async def resolve_skus(self, db: AsyncSession, skus: set[str]) -> dict[str, int]:
        """Resolve SKUs to product IDs."""
        ...

    async def resolve_dates(self, db: AsyncSession, dates: set[date_type]) -> set[date_type]:
        """Check which dates exist in the calendar table."""
        ...


class KeyResolver:
    """Resolves natural keys (store_code, sku) to internal database IDs."""

    async def resolve_store_codes(self, db: AsyncSession, codes: set[str]) -> dict[str, int]:
        """Resolve store codes to store IDs.

        Args:
            db: Async database session.
            codes: Set of store codes to resolve.

        Returns:
            Dictionary mapping store_code -> store_id for found stores.
        """
        if not codes:
            return {}

        stmt = select(Store.code, Store.id).where(Store.code.in_(codes))
        result = await db.execute(stmt)
        return {row.code: row.id for row in result}

    async def resolve_skus(self, db: AsyncSession, skus: set[str]) -> dict[str, int]:
        """Resolve SKUs to product IDs.

        Args:
            db: Async database session.
            skus: Set of SKUs to resolve.

        Returns:
            Dictionary mapping sku -> product_id for found products.
        """
        if not skus:
            return {}

        stmt = select(Product.sku, Product.id).where(Product.sku.in_(skus))
        result = await db.execute(stmt)
        return {row.sku: row.id for row in result}

    async def resolve_dates(self, db: AsyncSession, dates: set[date_type]) -> set[date_type]:
        """Check which dates exist in the calendar table.

        Args:
            db: Async database session.
            dates: Set of dates to check.

        Returns:
            Set of dates that exist in the calendar table.
        """
        if not dates:
            return set()

        stmt = select(Calendar.date).where(Calendar.date.in_(dates))
        result = await db.execute(stmt)
        return {row.date for row in result}


@dataclass
class UpsertResult:
    """Result of batch upsert operation."""

    inserted_count: int = 0
    updated_count: int = 0
    rejected_count: int = 0
    errors: list[IngestRowError] = field(  # pyright: ignore[reportUnknownVariableType]
        default_factory=list
    )


async def upsert_sales_daily_batch(
    db: AsyncSession,
    records: list[SalesDailyIngestRow],
    key_resolver: KeyResolverProtocol,
) -> UpsertResult:
    """Upsert sales daily records with key resolution and partial success.

    Resolves natural keys (store_code, sku) to internal IDs, validates
    calendar dates exist, then performs idempotent upsert using
    PostgreSQL's ON CONFLICT DO UPDATE.

    Args:
        db: Async database session.
        records: List of sales records with natural keys.
        key_resolver: KeyResolver instance for ID lookups.

    Returns:
        UpsertResult with counts and error details.
    """
    logger.info("ingest.sales_daily.upsert_started", batch_size=len(records))

    # Extract unique codes, SKUs, and dates
    store_codes = {r.store_code for r in records}
    skus = {r.sku for r in records}
    dates = {r.date for r in records}

    # Resolve all keys in batch
    store_map = await key_resolver.resolve_store_codes(db, store_codes)
    product_map = await key_resolver.resolve_skus(db, skus)
    valid_dates = await key_resolver.resolve_dates(db, dates)

    # Validate and prepare rows
    valid_rows: list[dict[str, Any]] = []
    errors: list[IngestRowError] = []

    for idx, record in enumerate(records):
        store_id = store_map.get(record.store_code)
        product_id = product_map.get(record.sku)
        date_exists = record.date in valid_dates

        # Check for unknown store
        if store_id is None:
            errors.append(
                IngestRowError(
                    row_index=idx,
                    store_code=record.store_code,
                    sku=record.sku,
                    date=record.date,
                    error_code="UNKNOWN_STORE",
                    error_message=f"Store code '{record.store_code}' not found",
                )
            )
            continue

        # Check for unknown product
        if product_id is None:
            errors.append(
                IngestRowError(
                    row_index=idx,
                    store_code=record.store_code,
                    sku=record.sku,
                    date=record.date,
                    error_code="UNKNOWN_PRODUCT",
                    error_message=f"SKU '{record.sku}' not found",
                )
            )
            continue

        # Check for missing calendar date
        if not date_exists:
            errors.append(
                IngestRowError(
                    row_index=idx,
                    store_code=record.store_code,
                    sku=record.sku,
                    date=record.date,
                    error_code="UNKNOWN_DATE",
                    error_message=f"Date '{record.date}' not found in calendar",
                )
            )
            continue

        valid_rows.append(
            {
                "date": record.date,
                "store_id": store_id,
                "product_id": product_id,
                "quantity": record.quantity,
                "unit_price": record.unit_price,
                "total_amount": record.total_amount,
            }
        )

    # Perform upsert for valid rows
    inserted = 0
    updated = 0

    if valid_rows:
        # Use PostgreSQL INSERT...ON CONFLICT DO UPDATE
        insert_stmt = pg_insert(SalesDaily).values(valid_rows)
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["date", "store_id", "product_id"],
            set_={
                "quantity": insert_stmt.excluded.quantity,
                "unit_price": insert_stmt.excluded.unit_price,
                "total_amount": insert_stmt.excluded.total_amount,
                "updated_at": func.now(),
            },
        ).returning(SalesDaily.id)

        # Execute and get results
        result = await db.execute(upsert_stmt)
        rows_affected = len(result.fetchall())

        # Note: Distinguishing inserted vs updated accurately requires xmax check
        # For simplicity, count all as processed (could enhance later)
        # A row is "inserted" if xmax = 0, "updated" if xmax > 0
        # For now, we report total as "inserted" for new batches
        inserted = rows_affected
        updated = 0

    logger.info(
        "ingest.sales_daily.upsert_completed",
        inserted=inserted,
        updated=updated,
        rejected=len(errors),
        total_valid=len(valid_rows),
    )

    return UpsertResult(
        inserted_count=inserted,
        updated_count=updated,
        rejected_count=len(errors),
        errors=errors,
    )
