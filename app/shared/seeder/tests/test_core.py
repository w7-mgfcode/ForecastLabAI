"""Tests for DataSeeder core orchestration."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared.seeder.config import SeederConfig, SparsityConfig
from app.shared.seeder.core import DataSeeder, SeederResult


class TestDataSeederInit:
    """Tests for DataSeeder initialization."""

    def test_creates_rng_from_seed(self):
        """Test RNG is created with config seed."""
        config = SeederConfig(seed=123)
        seeder = DataSeeder(config)

        assert seeder.rng is not None
        # Same seed should produce reproducible first random value
        first_val = seeder.rng.random()
        assert 0 <= first_val <= 1

    def test_same_seed_same_rng_sequence(self):
        """Test same seed produces same RNG sequence."""
        config1 = SeederConfig(seed=123)
        config2 = SeederConfig(seed=123)
        seeder1 = DataSeeder(config1)
        seeder2 = DataSeeder(config2)

        # Same seed should produce same sequence
        assert seeder1.rng.random() == seeder2.rng.random()

    def test_different_seeds_different_sequence(self):
        """Test different seeds produce different RNG sequences."""
        seeder1 = DataSeeder(SeederConfig(seed=123))
        seeder2 = DataSeeder(SeederConfig(seed=456))

        # Different seeds should produce different sequences
        assert seeder1.rng.random() != seeder2.rng.random()

    def test_stores_config(self):
        """Test config is stored on instance."""
        config = SeederConfig(seed=42, batch_size=500)
        seeder = DataSeeder(config)

        assert seeder.config.seed == 42
        assert seeder.config.batch_size == 500


class TestSeederResult:
    """Tests for SeederResult dataclass."""

    def test_default_values(self):
        """Test default values are zero."""
        result = SeederResult()

        assert result.stores_count == 0
        assert result.products_count == 0
        assert result.calendar_days == 0
        assert result.sales_count == 0
        assert result.price_history_count == 0
        assert result.promotions_count == 0
        assert result.inventory_count == 0
        assert result.seed == 42

    def test_custom_values(self):
        """Test custom values are stored."""
        result = SeederResult(
            stores_count=10,
            products_count=50,
            sales_count=1000,
            seed=123,
        )

        assert result.stores_count == 10
        assert result.products_count == 50
        assert result.sales_count == 1000
        assert result.seed == 123


class TestBatchInsert:
    """Tests for _batch_insert method."""

    @pytest.fixture
    def seeder(self):
        """Create seeder with small batch size."""
        config = SeederConfig(seed=42, batch_size=2)
        return DataSeeder(config)

    @pytest.fixture
    def mock_db(self):
        """Create mock async session."""
        db = AsyncMock()
        # Mock execute to return cursor with rowcount
        cursor = MagicMock()
        cursor.rowcount = 2
        db.execute.return_value = cursor
        return db

    @pytest.mark.asyncio
    async def test_empty_records_returns_zero(self, seeder, mock_db):
        """Test empty records list returns 0."""
        count = await seeder._batch_insert(mock_db, MagicMock, [])

        assert count == 0
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_batches_records(self, seeder, mock_db):
        """Test records are batched correctly."""
        records = [{"a": 1}, {"b": 2}, {"c": 3}, {"d": 4}, {"e": 5}]

        with patch("app.shared.seeder.core.pg_insert") as mock_insert:
            mock_stmt = MagicMock()
            mock_stmt.on_conflict_do_nothing.return_value = mock_stmt
            mock_insert.return_value = mock_stmt

            await seeder._batch_insert(mock_db, MagicMock, records)

        # With batch_size=2, 5 records = 3 batches
        assert mock_db.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_returns_total_count(self, seeder, mock_db):
        """Test total inserted count is returned."""
        records = [{"a": 1}, {"b": 2}]

        with patch("app.shared.seeder.core.pg_insert") as mock_insert:
            mock_stmt = MagicMock()
            mock_stmt.on_conflict_do_nothing.return_value = mock_stmt
            mock_insert.return_value = mock_stmt

            count = await seeder._batch_insert(mock_db, MagicMock, records)

        # rowcount=2 per batch, 1 batch for 2 records
        assert count == 2


class TestDeleteData:
    """Tests for delete_data method."""

    @pytest.fixture
    def seeder(self):
        """Create seeder."""
        return DataSeeder(SeederConfig(seed=42))

    @pytest.fixture
    def mock_db(self):
        """Create mock async session with count results."""
        db = AsyncMock()
        # Mock count queries to return different values
        db.execute.return_value.scalar.return_value = 10
        return db

    @pytest.mark.asyncio
    async def test_dry_run_returns_counts_without_delete(self, seeder, mock_db):
        """Test dry run returns counts but doesn't delete."""
        counts = await seeder.delete_data(mock_db, scope="all", dry_run=True)

        assert isinstance(counts, dict)
        assert len(counts) > 0
        # Should have called execute for counts but not commit
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_scope_facts_only(self, seeder, mock_db):
        """Test scope='facts' only processes fact tables."""
        counts = await seeder.delete_data(mock_db, scope="facts", dry_run=True)

        # Should include fact tables
        assert isinstance(counts, dict)
        # Check that fact tables are present
        fact_tables = ["sales_daily", "inventory_snapshot_daily", "price_history", "promotion"]
        for table in fact_tables:
            assert table in counts

    @pytest.mark.asyncio
    async def test_scope_all_includes_dimensions(self, seeder, mock_db):
        """Test scope='all' includes dimension tables."""
        counts = await seeder.delete_data(mock_db, scope="all", dry_run=True)

        # Should include both fact and dimension tables
        dimension_tables = ["store", "product", "calendar"]
        for table in dimension_tables:
            assert table in counts


class TestGetCurrentCounts:
    """Tests for get_current_counts method."""

    @pytest.fixture
    def seeder(self):
        """Create seeder."""
        return DataSeeder(SeederConfig(seed=42))

    @pytest.mark.asyncio
    async def test_returns_all_table_counts(self, seeder):
        """Test all tables are included in counts."""
        mock_db = AsyncMock()
        # Return a MagicMock for the result (not AsyncMock) since
        # scalar() is synchronous after await execute()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 100
        mock_db.execute.return_value = mock_result

        counts = await seeder.get_current_counts(mock_db)

        expected_tables = [
            "store",
            "product",
            "calendar",
            "sales_daily",
            "price_history",
            "promotion",
            "inventory_snapshot_daily",
        ]
        for table in expected_tables:
            assert table in counts
            assert counts[table] == 100


class TestVerifyDataIntegrity:
    """Tests for verify_data_integrity method."""

    @pytest.fixture
    def seeder(self):
        """Create seeder."""
        return DataSeeder(SeederConfig(seed=42))

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_valid(self, seeder):
        """Test empty list returned when data is valid."""
        mock_db = AsyncMock()
        # Create separate mock results for each execute call
        # verify_data_integrity makes 4 calls:
        # 1. orphan check
        # 2. negative qty check
        # 3. min/max date check
        # 4. calendar count
        mock_result1 = MagicMock()
        mock_result1.scalar.return_value = 0  # no orphans
        mock_result2 = MagicMock()
        mock_result2.scalar.return_value = 0  # no negative qty
        mock_result3 = MagicMock()
        mock_result3.fetchone.return_value = (date(2024, 1, 1), date(2024, 1, 31))
        mock_result4 = MagicMock()
        mock_result4.scalar.return_value = 31  # 31 days matches Jan 1-31

        mock_db.execute.side_effect = [mock_result1, mock_result2, mock_result3, mock_result4]

        errors = await seeder.verify_data_integrity(mock_db)

        assert errors == []

    @pytest.mark.asyncio
    async def test_detects_orphaned_sales(self, seeder):
        """Test orphaned sales are detected."""
        mock_db = AsyncMock()
        # Create separate mock results for each execute call
        mock_result1 = MagicMock()
        mock_result1.scalar.return_value = 5  # orphan check returns 5 errors
        mock_result2 = MagicMock()
        mock_result2.scalar.return_value = 0  # negative qty check
        mock_result3 = MagicMock()
        mock_result3.fetchone.return_value = (date(2024, 1, 1), date(2024, 1, 31))
        mock_result4 = MagicMock()
        mock_result4.scalar.return_value = 31  # calendar count

        mock_db.execute.side_effect = [mock_result1, mock_result2, mock_result3, mock_result4]

        errors = await seeder.verify_data_integrity(mock_db)

        assert any("invalid foreign keys" in e for e in errors)

    @pytest.mark.asyncio
    async def test_detects_negative_quantities(self, seeder):
        """Test negative quantities are detected."""
        mock_db = AsyncMock()
        # Create separate mock results for each execute call
        mock_result1 = MagicMock()
        mock_result1.scalar.return_value = 0  # orphan check
        mock_result2 = MagicMock()
        mock_result2.scalar.return_value = 3  # negative qty check returns 3 errors
        mock_result3 = MagicMock()
        mock_result3.fetchone.return_value = (date(2024, 1, 1), date(2024, 1, 31))
        mock_result4 = MagicMock()
        mock_result4.scalar.return_value = 31  # calendar count

        mock_db.execute.side_effect = [mock_result1, mock_result2, mock_result3, mock_result4]

        errors = await seeder.verify_data_integrity(mock_db)

        assert any("negative quantity" in e for e in errors)


class TestAppendDataValidation:
    """Tests for append_data method validation."""

    @pytest.fixture
    def seeder(self):
        """Create seeder."""
        return DataSeeder(SeederConfig(seed=42))

    @pytest.mark.asyncio
    async def test_raises_when_no_stores(self, seeder):
        """Test ValueError raised when no stores exist."""
        mock_db = AsyncMock()
        # Return a MagicMock for the result (not AsyncMock) since
        # fetchall() is synchronous after await execute()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="No stores found"):
            await seeder.append_data(
                mock_db,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 7),
            )


class TestSeederConfigDefaults:
    """Tests for SeederConfig defaults used in DataSeeder."""

    def test_default_batch_size(self):
        """Test default batch size is 1000."""
        config = SeederConfig()
        seeder = DataSeeder(config)

        assert seeder.config.batch_size == 1000

    def test_default_dimensions(self):
        """Test default dimension config."""
        config = SeederConfig()
        seeder = DataSeeder(config)

        assert seeder.config.dimensions.stores == 10
        assert seeder.config.dimensions.products == 50

    def test_default_date_range(self):
        """Test default date range is full year 2024."""
        config = SeederConfig()
        seeder = DataSeeder(config)

        assert seeder.config.start_date == date(2024, 1, 1)
        assert seeder.config.end_date == date(2024, 12, 31)

    def test_custom_sparsity(self):
        """Test custom sparsity configuration."""
        config = SeederConfig(
            sparsity=SparsityConfig(
                missing_combinations_pct=0.3,
                random_gaps_per_series=2,
            )
        )
        seeder = DataSeeder(config)

        assert seeder.config.sparsity.missing_combinations_pct == 0.3
        assert seeder.config.sparsity.random_gaps_per_series == 2
