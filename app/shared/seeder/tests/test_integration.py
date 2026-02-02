"""Integration tests for seeder (requires PostgreSQL).

Run with: uv run pytest app/shared/seeder/tests/test_integration.py -v -m integration

SAFETY: These tests perform destructive DELETE operations. They require either:
- settings.testing = True, OR
- ALLOW_DESTRUCTIVE_TEST_DB=true environment variable
"""

import os
from collections.abc import AsyncGenerator
from contextlib import suppress
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.features.data_platform.models import (
    Calendar,
    InventorySnapshotDaily,
    PriceHistory,
    Product,
    Promotion,
    SalesDaily,
    Store,
)
from app.shared.seeder import DataSeeder, SeederConfig
from app.shared.seeder.config import DimensionConfig, SparsityConfig

pytestmark = pytest.mark.integration


def _check_destructive_test_guard() -> None:
    """Verify that destructive test operations are explicitly allowed.

    Raises:
        RuntimeError: If destructive operations are not explicitly enabled.
    """
    settings = get_settings()

    # Check for testing flag on settings
    is_testing = getattr(settings, "testing", False)

    # Check for APP_ENV=testing (used in CI)
    app_env_testing = os.environ.get("APP_ENV", "").lower() == "testing"

    # Check for explicit env var override
    allow_destructive = os.environ.get("ALLOW_DESTRUCTIVE_TEST_DB", "").lower() == "true"

    if not is_testing and not app_env_testing and not allow_destructive:
        raise RuntimeError(
            "Destructive test operations require explicit opt-in. "
            "Set ALLOW_DESTRUCTIVE_TEST_DB=true, APP_ENV=testing, or ensure settings.testing=True"
        )


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a database session for testing.

    Cleans up data before and after each test for proper isolation.

    Raises:
        RuntimeError: If destructive operations are not explicitly enabled.
    """
    # Safety guard before any destructive operations
    _check_destructive_test_guard()

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Pre-test cleanup for proper isolation
    async with session_maker() as cleanup_session:
        try:
            # Delete in FK order (facts before dimensions)
            await cleanup_session.execute(delete(SalesDaily))
            await cleanup_session.execute(delete(InventorySnapshotDaily))
            await cleanup_session.execute(delete(PriceHistory))
            await cleanup_session.execute(delete(Promotion))
            await cleanup_session.execute(delete(Calendar))
            await cleanup_session.execute(delete(Product))
            await cleanup_session.execute(delete(Store))
            await cleanup_session.commit()
        except Exception:
            await cleanup_session.rollback()

    async with session_maker() as session:
        try:
            yield session
        finally:
            # Rollback any uncommitted changes
            with suppress(Exception):
                await session.rollback()

    # Safety guard before post-test cleanup
    _check_destructive_test_guard()

    # Post-test cleanup
    async with session_maker() as cleanup_session:
        try:
            # Delete in FK order (facts before dimensions)
            await cleanup_session.execute(delete(SalesDaily))
            await cleanup_session.execute(delete(InventorySnapshotDaily))
            await cleanup_session.execute(delete(PriceHistory))
            await cleanup_session.execute(delete(Promotion))
            await cleanup_session.execute(delete(Calendar))
            await cleanup_session.execute(delete(Product))
            await cleanup_session.execute(delete(Store))
            await cleanup_session.commit()
        except Exception:
            await cleanup_session.rollback()

    await engine.dispose()


class TestGenerateFull:
    """Integration tests for generate_full()."""

    @pytest.mark.asyncio
    async def test_generates_all_tables(self, db_session: AsyncSession) -> None:
        """Test full generation creates data in all tables."""
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),  # 1 week
            dimensions=DimensionConfig(stores=2, products=3),
            batch_size=100,
        )
        seeder = DataSeeder(config)

        result = await seeder.generate_full(db_session)

        assert result.stores_count == 2
        assert result.products_count == 3
        assert result.calendar_days == 7
        assert result.sales_count > 0
        assert result.seed == 42

    @pytest.mark.asyncio
    async def test_respects_unique_constraints(self, db_session: AsyncSession) -> None:
        """Test re-running generate_full with fresh seeder is idempotent.

        Note: The seeder uses ON CONFLICT DO NOTHING, so duplicate inserts
        of the same store codes/SKUs are silently ignored. When using the
        same seed with a fresh seeder instance, the same codes are generated
        and the second insert is effectively a no-op.
        """
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            dimensions=DimensionConfig(stores=2, products=2),
        )

        # First run
        seeder1 = DataSeeder(config)
        await seeder1.generate_full(db_session)
        counts_after_first = await seeder1.get_current_counts(db_session)

        # Second run with fresh seeder (same seed = same codes generated)
        seeder2 = DataSeeder(config)
        await seeder2.generate_full(db_session)
        counts_after_second = await seeder2.get_current_counts(db_session)

        # Store and product counts should remain the same (no duplicates)
        # because same codes are generated and ON CONFLICT DO NOTHING ignores them
        assert counts_after_first["store"] == counts_after_second["store"]
        assert counts_after_first["product"] == counts_after_second["product"]
        assert counts_after_first["calendar"] == counts_after_second["calendar"]

    @pytest.mark.asyncio
    async def test_foreign_keys_valid(self, db_session: AsyncSession) -> None:
        """Test all foreign keys reference valid parents."""
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            dimensions=DimensionConfig(stores=2, products=3),
        )
        seeder = DataSeeder(config)
        await seeder.generate_full(db_session)

        # Verify no integrity errors
        errors = await seeder.verify_data_integrity(db_session)
        assert errors == []

    @pytest.mark.asyncio
    async def test_generates_price_history(self, db_session: AsyncSession) -> None:
        """Test price history is generated."""
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 14),
            dimensions=DimensionConfig(stores=2, products=3),
        )
        seeder = DataSeeder(config)

        result = await seeder.generate_full(db_session)

        assert result.price_history_count > 0

    @pytest.mark.asyncio
    async def test_generates_inventory(self, db_session: AsyncSession) -> None:
        """Test inventory snapshots are generated."""
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),
            dimensions=DimensionConfig(stores=2, products=2),
        )
        seeder = DataSeeder(config)

        result = await seeder.generate_full(db_session)

        assert result.inventory_count > 0


class TestDeleteData:
    """Integration tests for delete_data()."""

    @pytest.mark.asyncio
    async def test_delete_all_clears_tables(self, db_session: AsyncSession) -> None:
        """Test delete with scope='all' clears all tables."""
        # First generate data
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            dimensions=DimensionConfig(stores=2, products=2),
        )
        seeder = DataSeeder(config)
        await seeder.generate_full(db_session)

        # Then delete
        counts = await seeder.delete_data(db_session, scope="all", dry_run=False)

        assert counts["store"] > 0  # Had data before

        # Verify tables are empty
        final_counts = await seeder.get_current_counts(db_session)
        assert all(c == 0 for c in final_counts.values())

    @pytest.mark.asyncio
    async def test_delete_facts_preserves_dimensions(self, db_session: AsyncSession) -> None:
        """Test delete with scope='facts' keeps dimension tables."""
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            dimensions=DimensionConfig(stores=2, products=2),
        )
        seeder = DataSeeder(config)
        await seeder.generate_full(db_session)

        counts_before = await seeder.get_current_counts(db_session)
        await seeder.delete_data(db_session, scope="facts", dry_run=False)
        counts_after = await seeder.get_current_counts(db_session)

        # Dimensions preserved
        assert counts_after["store"] == counts_before["store"]
        assert counts_after["product"] == counts_before["product"]
        # Facts deleted
        assert counts_after["sales_daily"] == 0

    @pytest.mark.asyncio
    async def test_dry_run_doesnt_delete(self, db_session: AsyncSession) -> None:
        """Test dry_run=True doesn't actually delete."""
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            dimensions=DimensionConfig(stores=2, products=2),
        )
        seeder = DataSeeder(config)
        await seeder.generate_full(db_session)

        counts_before = await seeder.get_current_counts(db_session)
        await seeder.delete_data(db_session, scope="all", dry_run=True)
        counts_after = await seeder.get_current_counts(db_session)

        # Counts should be unchanged
        assert counts_before == counts_after


class TestAppendData:
    """Integration tests for append_data()."""

    @pytest.mark.asyncio
    async def test_append_extends_date_range(self, db_session: AsyncSession) -> None:
        """Test append adds data for new date range."""
        # First generate initial data
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),
            dimensions=DimensionConfig(stores=2, products=2),
        )
        seeder = DataSeeder(config)
        await seeder.generate_full(db_session)

        # Append second week
        append_result = await seeder.append_data(
            db_session,
            start_date=date(2024, 1, 8),
            end_date=date(2024, 1, 14),
        )

        assert append_result.calendar_days == 7
        assert append_result.sales_count > 0

        # Total calendar days should be 14
        counts = await seeder.get_current_counts(db_session)
        assert counts["calendar"] == 14

    @pytest.mark.asyncio
    async def test_append_fails_without_dimensions(self, db_session: AsyncSession) -> None:
        """Test append fails if no dimensions exist."""
        config = SeederConfig(seed=42)
        seeder = DataSeeder(config)

        with pytest.raises(ValueError, match="No stores found"):
            await seeder.append_data(
                db_session,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 7),
            )

    @pytest.mark.asyncio
    async def test_append_uses_existing_dimensions(self, db_session: AsyncSession) -> None:
        """Test append uses existing store/product dimensions."""
        # Generate initial data
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            dimensions=DimensionConfig(stores=3, products=4),
        )
        seeder = DataSeeder(config)
        await seeder.generate_full(db_session)

        # Append more data
        append_result = await seeder.append_data(
            db_session,
            start_date=date(2024, 1, 4),
            end_date=date(2024, 1, 6),
        )

        # No new stores or products
        assert append_result.stores_count == 0
        assert append_result.products_count == 0
        # But calendar and facts added
        assert append_result.calendar_days == 3
        assert append_result.sales_count > 0


class TestSparsity:
    """Integration tests for sparsity configuration."""

    @pytest.mark.asyncio
    async def test_sparsity_reduces_sales_count(self, db_session: AsyncSession) -> None:
        """Test sparsity config reduces number of sales records."""
        # Full density
        config_full = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),
            dimensions=DimensionConfig(stores=3, products=4),
            sparsity=SparsityConfig(missing_combinations_pct=0.0),
        )

        seeder_full = DataSeeder(config_full)
        result_full = await seeder_full.generate_full(db_session)

        # Cleanup and regenerate with sparse config
        await seeder_full.delete_data(db_session, scope="all", dry_run=False)

        # 50% sparse
        config_sparse = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),
            dimensions=DimensionConfig(stores=3, products=4),
            sparsity=SparsityConfig(missing_combinations_pct=0.5),
        )

        seeder_sparse = DataSeeder(config_sparse)
        result_sparse = await seeder_sparse.generate_full(db_session)

        # Sparse should have fewer sales
        assert result_sparse.sales_count < result_full.sales_count


class TestReproducibility:
    """Integration tests for seed reproducibility."""

    @pytest.mark.asyncio
    async def test_same_seed_same_data(self, db_session: AsyncSession) -> None:
        """Test same seed produces same store/product codes."""
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            dimensions=DimensionConfig(stores=2, products=2),
        )

        # First run
        seeder1 = DataSeeder(config)
        await seeder1.generate_full(db_session)

        result = await db_session.execute(select(Store.code).order_by(Store.code))
        codes1 = [row[0] for row in result.fetchall()]

        # Cleanup
        await seeder1.delete_data(db_session, scope="all", dry_run=False)

        # Second run with same seed
        seeder2 = DataSeeder(config)
        await seeder2.generate_full(db_session)

        result = await db_session.execute(select(Store.code).order_by(Store.code))
        codes2 = [row[0] for row in result.fetchall()]

        assert codes1 == codes2

    @pytest.mark.asyncio
    async def test_different_seed_different_data(self, db_session: AsyncSession) -> None:
        """Test different seeds produce different store codes."""
        config1 = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            dimensions=DimensionConfig(stores=2, products=2),
        )

        # First run
        seeder1 = DataSeeder(config1)
        await seeder1.generate_full(db_session)

        result = await db_session.execute(select(Store.code).order_by(Store.code))
        codes1 = [row[0] for row in result.fetchall()]

        # Cleanup
        await seeder1.delete_data(db_session, scope="all", dry_run=False)

        # Second run with different seed
        config2 = SeederConfig(
            seed=123,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            dimensions=DimensionConfig(stores=2, products=2),
        )
        seeder2 = DataSeeder(config2)
        await seeder2.generate_full(db_session)

        result = await db_session.execute(select(Store.code).order_by(Store.code))
        codes2 = [row[0] for row in result.fetchall()]

        assert codes1 != codes2


class TestVerifyIntegrity:
    """Integration tests for verify_data_integrity."""

    @pytest.mark.asyncio
    async def test_verify_passes_on_valid_data(self, db_session: AsyncSession) -> None:
        """Test verification passes on properly generated data."""
        config = SeederConfig(
            seed=42,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),
            dimensions=DimensionConfig(stores=2, products=3),
        )
        seeder = DataSeeder(config)
        await seeder.generate_full(db_session)

        errors = await seeder.verify_data_integrity(db_session)

        assert errors == []

    @pytest.mark.asyncio
    async def test_verify_on_empty_database(self, db_session: AsyncSession) -> None:
        """Test verification on empty database doesn't crash."""
        config = SeederConfig(seed=42)
        seeder = DataSeeder(config)

        # Should not raise, just return empty errors list
        errors = await seeder.verify_data_integrity(db_session)

        # No data means no integrity errors
        assert errors == []
