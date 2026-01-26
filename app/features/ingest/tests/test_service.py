"""Unit tests for ingest service."""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.ingest.schemas import SalesDailyIngestRow
from app.features.ingest.service import KeyResolver, UpsertResult, upsert_sales_daily_batch


class TestKeyResolver:
    """Tests for KeyResolver class."""

    @pytest.mark.asyncio
    async def test_resolve_store_codes_returns_mapping(self):
        """Test that resolve_store_codes returns correct mapping."""
        # Setup mock session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(
            [
                MagicMock(code="S001", id=1),
                MagicMock(code="S002", id=2),
            ]
        )
        mock_session.execute.return_value = mock_result

        resolver = KeyResolver()
        result = await resolver.resolve_store_codes(mock_session, {"S001", "S002"})

        assert result == {"S001": 1, "S002": 2}
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_store_codes_empty_set(self):
        """Test that resolve_store_codes handles empty set."""
        mock_session = AsyncMock()
        resolver = KeyResolver()
        result = await resolver.resolve_store_codes(mock_session, set())

        assert result == {}
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_skus_returns_mapping(self):
        """Test that resolve_skus returns correct mapping."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(
            [
                MagicMock(sku="SKU-001", id=101),
                MagicMock(sku="SKU-002", id=102),
            ]
        )
        mock_session.execute.return_value = mock_result

        resolver = KeyResolver()
        result = await resolver.resolve_skus(mock_session, {"SKU-001", "SKU-002"})

        assert result == {"SKU-001": 101, "SKU-002": 102}

    @pytest.mark.asyncio
    async def test_resolve_skus_empty_set(self):
        """Test that resolve_skus handles empty set."""
        mock_session = AsyncMock()
        resolver = KeyResolver()
        result = await resolver.resolve_skus(mock_session, set())

        assert result == {}
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_dates_returns_set(self):
        """Test that resolve_dates returns set of valid dates."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(
            [
                MagicMock(date=date(2024, 1, 15)),
                MagicMock(date=date(2024, 1, 16)),
            ]
        )
        mock_session.execute.return_value = mock_result

        resolver = KeyResolver()
        result = await resolver.resolve_dates(mock_session, {date(2024, 1, 15), date(2024, 1, 16)})

        assert result == {date(2024, 1, 15), date(2024, 1, 16)}

    @pytest.mark.asyncio
    async def test_resolve_dates_empty_set(self):
        """Test that resolve_dates handles empty set."""
        mock_session = AsyncMock()
        resolver = KeyResolver()
        result = await resolver.resolve_dates(mock_session, set())

        assert result == set()
        mock_session.execute.assert_not_called()


class TestUpsertResult:
    """Tests for UpsertResult dataclass."""

    def test_default_values(self):
        """Test UpsertResult default values."""
        result = UpsertResult()
        assert result.processed_count == 0
        assert result.rejected_count == 0
        assert result.errors == []

    def test_with_values(self):
        """Test UpsertResult with values."""
        result = UpsertResult(
            processed_count=5,
            rejected_count=1,
            errors=[],
        )
        assert result.processed_count == 5
        assert result.rejected_count == 1


class TestUpsertSalesDailyBatch:
    """Tests for upsert_sales_daily_batch function."""

    @pytest.mark.asyncio
    async def test_all_valid_rows_processed(self, mock_key_resolver):
        """Test that all valid rows are processed."""
        mock_session = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.rowcount = 2
        mock_session.execute.return_value = mock_execute_result

        records = [
            SalesDailyIngestRow(
                date=date(2024, 1, 15),
                store_code="S001",
                sku="SKU-001",
                quantity=10,
                unit_price=Decimal("9.99"),
                total_amount=Decimal("99.90"),
            ),
            SalesDailyIngestRow(
                date=date(2024, 1, 15),
                store_code="S002",
                sku="SKU-002",
                quantity=5,
                unit_price=Decimal("19.99"),
                total_amount=Decimal("99.95"),
            ),
        ]

        result = await upsert_sales_daily_batch(mock_session, records, mock_key_resolver)

        assert result.processed_count == 2
        assert result.rejected_count == 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_unknown_store_rejected(self, mock_key_resolver):
        """Test that rows with unknown store codes are rejected."""
        mock_session = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.rowcount = 1
        mock_session.execute.return_value = mock_execute_result

        records = [
            SalesDailyIngestRow(
                date=date(2024, 1, 15),
                store_code="S001",
                sku="SKU-001",
                quantity=10,
                unit_price=Decimal("9.99"),
                total_amount=Decimal("99.90"),
            ),
            SalesDailyIngestRow(
                date=date(2024, 1, 15),
                store_code="UNKNOWN_STORE",  # Not in mock resolver
                sku="SKU-001",
                quantity=5,
                unit_price=Decimal("9.99"),
                total_amount=Decimal("49.95"),
            ),
        ]

        result = await upsert_sales_daily_batch(mock_session, records, mock_key_resolver)

        assert result.processed_count == 1
        assert result.rejected_count == 1
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "UNKNOWN_STORE"
        assert result.errors[0].row_index == 1

    @pytest.mark.asyncio
    async def test_unknown_product_rejected(self, mock_key_resolver):
        """Test that rows with unknown SKUs are rejected."""
        mock_session = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.rowcount = 1
        mock_session.execute.return_value = mock_execute_result

        records = [
            SalesDailyIngestRow(
                date=date(2024, 1, 15),
                store_code="S001",
                sku="SKU-001",
                quantity=10,
                unit_price=Decimal("9.99"),
                total_amount=Decimal("99.90"),
            ),
            SalesDailyIngestRow(
                date=date(2024, 1, 15),
                store_code="S001",
                sku="UNKNOWN_SKU",  # Not in mock resolver
                quantity=5,
                unit_price=Decimal("9.99"),
                total_amount=Decimal("49.95"),
            ),
        ]

        result = await upsert_sales_daily_batch(mock_session, records, mock_key_resolver)

        assert result.processed_count == 1
        assert result.rejected_count == 1
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "UNKNOWN_PRODUCT"
        assert result.errors[0].row_index == 1

    @pytest.mark.asyncio
    async def test_unknown_date_rejected(self, mock_key_resolver):
        """Test that rows with unknown dates are rejected."""
        mock_session = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.rowcount = 1
        mock_session.execute.return_value = mock_execute_result

        records = [
            SalesDailyIngestRow(
                date=date(2024, 1, 15),  # In mock resolver
                store_code="S001",
                sku="SKU-001",
                quantity=10,
                unit_price=Decimal("9.99"),
                total_amount=Decimal("99.90"),
            ),
            SalesDailyIngestRow(
                date=date(2024, 12, 31),  # Not in mock resolver
                store_code="S001",
                sku="SKU-001",
                quantity=5,
                unit_price=Decimal("9.99"),
                total_amount=Decimal("49.95"),
            ),
        ]

        result = await upsert_sales_daily_batch(mock_session, records, mock_key_resolver)

        assert result.processed_count == 1
        assert result.rejected_count == 1
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "UNKNOWN_DATE"
        assert result.errors[0].row_index == 1

    @pytest.mark.asyncio
    async def test_partial_success_mixed_rows(self, sample_ingest_rows_mixed, mock_key_resolver):
        """Test partial success with mixed valid/invalid rows."""
        mock_session = AsyncMock()
        mock_execute_result = MagicMock()
        # 2 valid rows will be processed
        mock_execute_result.rowcount = 2
        mock_session.execute.return_value = mock_execute_result

        result = await upsert_sales_daily_batch(
            mock_session, sample_ingest_rows_mixed, mock_key_resolver
        )

        # 2 valid rows (S001/SKU-001 and S002/SKU-002)
        # 2 invalid rows (UNKNOWN store, UNKNOWN-SKU product)
        assert result.processed_count == 2
        assert result.rejected_count == 2
        assert len(result.errors) == 2

        # Verify error codes
        error_codes = {e.error_code for e in result.errors}
        assert "UNKNOWN_STORE" in error_codes
        assert "UNKNOWN_PRODUCT" in error_codes

    @pytest.mark.asyncio
    async def test_all_rows_rejected(self, mock_key_resolver):
        """Test that all rows can be rejected."""
        mock_session = AsyncMock()

        records = [
            SalesDailyIngestRow(
                date=date(2024, 1, 15),
                store_code="INVALID_STORE",
                sku="SKU-001",
                quantity=10,
                unit_price=Decimal("9.99"),
                total_amount=Decimal("99.90"),
            ),
        ]

        result = await upsert_sales_daily_batch(mock_session, records, mock_key_resolver)

        assert result.processed_count == 0
        assert result.rejected_count == 1
        # DB execute should not be called since no valid rows
        # (only key resolution queries, no insert)

    @pytest.mark.asyncio
    async def test_empty_records_handled(self, mock_key_resolver):
        """Test that empty records list is handled."""
        mock_session = AsyncMock()

        result = await upsert_sales_daily_batch(mock_session, [], mock_key_resolver)

        assert result.processed_count == 0
        assert result.rejected_count == 0
        assert result.errors == []
