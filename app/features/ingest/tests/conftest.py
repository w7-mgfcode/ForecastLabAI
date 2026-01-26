"""Feature-specific test fixtures for ingest module."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.features.ingest.schemas import SalesDailyIngestRequest, SalesDailyIngestRow


class MockKeyResolver:
    """Mock KeyResolver for testing with predefined mappings."""

    def __init__(
        self,
        store_map: dict[str, int] | None = None,
        product_map: dict[str, int] | None = None,
        valid_dates: set[date] | None = None,
    ) -> None:
        self._store_map = store_map or {"S001": 1, "S002": 2}
        self._product_map = product_map or {"SKU-001": 101, "SKU-002": 102, "SKU-003": 103}
        self._valid_dates = valid_dates or {date(2024, 1, 15), date(2024, 1, 16)}

    async def resolve_store_codes(self, db: Any, codes: set[str]) -> dict[str, int]:
        return {code: self._store_map[code] for code in codes if code in self._store_map}

    async def resolve_skus(self, db: Any, skus: set[str]) -> dict[str, int]:
        return {sku: self._product_map[sku] for sku in skus if sku in self._product_map}

    async def resolve_dates(self, db: Any, dates: set[date]) -> set[date]:
        return {d for d in dates if d in self._valid_dates}


@pytest.fixture
def sample_ingest_row() -> SalesDailyIngestRow:
    """Create a sample valid ingest row."""
    return SalesDailyIngestRow(
        date=date(2024, 1, 15),
        store_code="S001",
        sku="SKU-001",
        quantity=10,
        unit_price=Decimal("9.99"),
        total_amount=Decimal("99.90"),
    )


@pytest.fixture
def sample_ingest_request(sample_ingest_row) -> SalesDailyIngestRequest:
    """Create a sample valid ingest request."""
    return SalesDailyIngestRequest(
        records=[
            sample_ingest_row,
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


@pytest.fixture
def mock_key_resolver() -> MockKeyResolver:
    """Create a mock KeyResolver with predefined mappings."""
    return MockKeyResolver()


@pytest.fixture
def sample_ingest_rows_mixed() -> list[SalesDailyIngestRow]:
    """Create a list of ingest rows with mixed valid/invalid data."""
    return [
        # Valid row
        SalesDailyIngestRow(
            date=date(2024, 1, 15),
            store_code="S001",
            sku="SKU-001",
            quantity=10,
            unit_price=Decimal("9.99"),
            total_amount=Decimal("99.90"),
        ),
        # Unknown store
        SalesDailyIngestRow(
            date=date(2024, 1, 15),
            store_code="UNKNOWN",
            sku="SKU-001",
            quantity=5,
            unit_price=Decimal("9.99"),
            total_amount=Decimal("49.95"),
        ),
        # Unknown product
        SalesDailyIngestRow(
            date=date(2024, 1, 15),
            store_code="S001",
            sku="UNKNOWN-SKU",
            quantity=3,
            unit_price=Decimal("5.00"),
            total_amount=Decimal("15.00"),
        ),
        # Another valid row
        SalesDailyIngestRow(
            date=date(2024, 1, 15),
            store_code="S002",
            sku="SKU-002",
            quantity=7,
            unit_price=Decimal("15.00"),
            total_amount=Decimal("105.00"),
        ),
    ]
