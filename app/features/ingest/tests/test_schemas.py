"""Unit tests for ingest schemas."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.features.ingest.schemas import (
    IngestRowError,
    SalesDailyIngestRequest,
    SalesDailyIngestResponse,
    SalesDailyIngestRow,
)


class TestSalesDailyIngestRow:
    """Tests for SalesDailyIngestRow schema."""

    def test_valid_row(self):
        """Test valid row creation."""
        row = SalesDailyIngestRow(
            date=date(2024, 1, 15),
            store_code="S001",
            sku="SKU-001",
            quantity=10,
            unit_price=Decimal("9.99"),
            total_amount=Decimal("99.90"),
        )
        assert row.date == date(2024, 1, 15)
        assert row.store_code == "S001"
        assert row.sku == "SKU-001"
        assert row.quantity == 10
        assert row.unit_price == Decimal("9.99")
        assert row.total_amount == Decimal("99.90")

    def test_negative_quantity_rejected(self):
        """Test that negative quantity is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SalesDailyIngestRow(
                date=date(2024, 1, 15),
                store_code="S001",
                sku="SKU-001",
                quantity=-5,
                unit_price=Decimal("9.99"),
                total_amount=Decimal("99.90"),
            )
        assert "quantity" in str(exc_info.value)

    def test_negative_unit_price_rejected(self):
        """Test that negative unit price is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SalesDailyIngestRow(
                date=date(2024, 1, 15),
                store_code="S001",
                sku="SKU-001",
                quantity=10,
                unit_price=Decimal("-9.99"),
                total_amount=Decimal("99.90"),
            )
        assert "unit_price" in str(exc_info.value)

    def test_negative_total_amount_rejected(self):
        """Test that negative total amount is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SalesDailyIngestRow(
                date=date(2024, 1, 15),
                store_code="S001",
                sku="SKU-001",
                quantity=10,
                unit_price=Decimal("9.99"),
                total_amount=Decimal("-99.90"),
            )
        assert "total_amount" in str(exc_info.value)

    def test_empty_store_code_rejected(self):
        """Test that empty store code is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SalesDailyIngestRow(
                date=date(2024, 1, 15),
                store_code="",
                sku="SKU-001",
                quantity=10,
                unit_price=Decimal("9.99"),
                total_amount=Decimal("99.90"),
            )
        assert "store_code" in str(exc_info.value)

    def test_empty_sku_rejected(self):
        """Test that empty SKU is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SalesDailyIngestRow(
                date=date(2024, 1, 15),
                store_code="S001",
                sku="",
                quantity=10,
                unit_price=Decimal("9.99"),
                total_amount=Decimal("99.90"),
            )
        assert "sku" in str(exc_info.value)

    def test_store_code_max_length(self):
        """Test that store code exceeding max length is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SalesDailyIngestRow(
                date=date(2024, 1, 15),
                store_code="S" * 21,  # max is 20
                sku="SKU-001",
                quantity=10,
                unit_price=Decimal("9.99"),
                total_amount=Decimal("99.90"),
            )
        assert "store_code" in str(exc_info.value)

    def test_sku_max_length(self):
        """Test that SKU exceeding max length is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SalesDailyIngestRow(
                date=date(2024, 1, 15),
                store_code="S001",
                sku="SKU" * 20,  # max is 50
                quantity=10,
                unit_price=Decimal("9.99"),
                total_amount=Decimal("99.90"),
            )
        assert "sku" in str(exc_info.value)

    def test_zero_quantity_allowed(self):
        """Test that zero quantity is allowed."""
        row = SalesDailyIngestRow(
            date=date(2024, 1, 15),
            store_code="S001",
            sku="SKU-001",
            quantity=0,
            unit_price=Decimal("9.99"),
            total_amount=Decimal("0.00"),
        )
        assert row.quantity == 0

    def test_total_amount_consistency_validation_passes(self):
        """Test that total amount consistency validation passes for matching values."""
        row = SalesDailyIngestRow(
            date=date(2024, 1, 15),
            store_code="S001",
            sku="SKU-001",
            quantity=10,
            unit_price=Decimal("9.99"),
            total_amount=Decimal("99.90"),
        )
        # Should pass even with slight mismatch
        assert row.total_amount == Decimal("99.90")

    def test_total_amount_allows_mismatch_within_tolerance(self):
        """Test that small mismatches in total amount are allowed."""
        # Expected: 10 * 9.99 = 99.90, actual: 99.91 (within 0.01 tolerance)
        row = SalesDailyIngestRow(
            date=date(2024, 1, 15),
            store_code="S001",
            sku="SKU-001",
            quantity=10,
            unit_price=Decimal("9.99"),
            total_amount=Decimal("99.91"),
        )
        assert row.total_amount == Decimal("99.91")


class TestSalesDailyIngestRequest:
    """Tests for SalesDailyIngestRequest schema."""

    def test_valid_request_single_record(self):
        """Test valid request with single record."""
        request = SalesDailyIngestRequest(
            records=[
                SalesDailyIngestRow(
                    date=date(2024, 1, 15),
                    store_code="S001",
                    sku="SKU-001",
                    quantity=10,
                    unit_price=Decimal("9.99"),
                    total_amount=Decimal("99.90"),
                )
            ]
        )
        assert len(request.records) == 1

    def test_valid_request_multiple_records(self):
        """Test valid request with multiple records."""
        request = SalesDailyIngestRequest(
            records=[
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
                    sku="SKU-002",
                    quantity=5,
                    unit_price=Decimal("19.99"),
                    total_amount=Decimal("99.95"),
                ),
            ]
        )
        assert len(request.records) == 2

    def test_empty_records_rejected(self):
        """Test that empty records list is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SalesDailyIngestRequest(records=[])
        assert "records" in str(exc_info.value)


class TestIngestRowError:
    """Tests for IngestRowError schema."""

    def test_error_serialization(self):
        """Test that error can be serialized."""
        error = IngestRowError(
            row_index=1,
            store_code="UNKNOWN",
            sku="SKU-001",
            date=date(2024, 1, 15),
            error_code="UNKNOWN_STORE",
            error_message="Store code 'UNKNOWN' not found",
        )
        data = error.model_dump()
        assert data["row_index"] == 1
        assert data["error_code"] == "UNKNOWN_STORE"
        assert "UNKNOWN" in data["error_message"]


class TestSalesDailyIngestResponse:
    """Tests for SalesDailyIngestResponse schema."""

    def test_response_serialization(self):
        """Test that response can be serialized."""
        response = SalesDailyIngestResponse(
            processed_count=7,
            rejected_count=1,
            total_received=8,
            errors=[
                IngestRowError(
                    row_index=7,
                    store_code="BAD",
                    sku="SKU-001",
                    date=date(2024, 1, 15),
                    error_code="UNKNOWN_STORE",
                    error_message="Store code 'BAD' not found",
                )
            ],
            duration_ms=45.23,
        )
        data = response.model_dump()
        assert data["processed_count"] == 7
        assert data["rejected_count"] == 1
        assert data["total_received"] == 8
        assert len(data["errors"]) == 1
        assert data["duration_ms"] == 45.23

    def test_response_with_no_errors(self):
        """Test response with no errors."""
        response = SalesDailyIngestResponse(
            processed_count=10,
            rejected_count=0,
            total_received=10,
            errors=[],
            duration_ms=30.0,
        )
        assert response.rejected_count == 0
        assert len(response.errors) == 0

    def test_response_counts_non_negative(self):
        """Test that negative counts are rejected."""
        with pytest.raises(ValidationError):
            SalesDailyIngestResponse(
                processed_count=-1,
                rejected_count=0,
                total_received=0,
                errors=[],
                duration_ms=0.0,
            )
