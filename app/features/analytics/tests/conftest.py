"""Test fixtures for analytics module."""

from datetime import date
from decimal import Decimal

import pytest

from app.features.analytics.schemas import (
    DrilldownDimension,
    DrilldownItem,
    DrilldownResponse,
    KPIMetrics,
    KPIResponse,
)


@pytest.fixture
def sample_kpi_metrics() -> KPIMetrics:
    """Create sample KPI metrics for testing."""
    return KPIMetrics(
        total_revenue=Decimal("10000.00"),
        total_units=500,
        total_transactions=100,
        avg_unit_price=Decimal("20.00"),
        avg_basket_value=Decimal("100.00"),
    )


@pytest.fixture
def sample_kpi_response(sample_kpi_metrics: KPIMetrics) -> KPIResponse:
    """Create sample KPI response for testing."""
    return KPIResponse(
        metrics=sample_kpi_metrics,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        store_id=None,
        product_id=None,
        category=None,
    )


@pytest.fixture
def sample_drilldown_items(sample_kpi_metrics: KPIMetrics) -> list[DrilldownItem]:
    """Create sample drilldown items for testing."""
    return [
        DrilldownItem(
            dimension_value="S001",
            dimension_id=1,
            metrics=sample_kpi_metrics,
            rank=1,
            revenue_share_pct=Decimal("60.00"),
        ),
        DrilldownItem(
            dimension_value="S002",
            dimension_id=2,
            metrics=KPIMetrics(
                total_revenue=Decimal("5000.00"),
                total_units=250,
                total_transactions=50,
                avg_unit_price=Decimal("20.00"),
                avg_basket_value=Decimal("100.00"),
            ),
            rank=2,
            revenue_share_pct=Decimal("40.00"),
        ),
    ]


@pytest.fixture
def sample_drilldown_response(
    sample_drilldown_items: list[DrilldownItem],
) -> DrilldownResponse:
    """Create sample drilldown response for testing."""
    return DrilldownResponse(
        dimension=DrilldownDimension.STORE,
        items=sample_drilldown_items,
        total_items=2,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        store_id=None,
        product_id=None,
    )
