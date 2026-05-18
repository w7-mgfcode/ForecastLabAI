"""Unit tests for analytics time-series schemas.

These tests run without a database (-m "not integration").
"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.features.analytics.schemas import (
    KPIMetrics,
    TimeGranularity,
    TimeSeriesPoint,
    TimeSeriesResponse,
)


def test_time_series_point_construct() -> None:
    """A TimeSeriesPoint carries a period date and nested KPI metrics."""
    point = TimeSeriesPoint(
        period=date(2024, 1, 1),
        metrics=KPIMetrics(
            total_revenue=Decimal("100.00"),
            total_units=10,
            total_transactions=2,
            avg_unit_price=Decimal("10.00"),
            avg_basket_value=Decimal("50.00"),
        ),
    )
    assert point.period == date(2024, 1, 1)
    assert point.metrics.total_units == 10
    assert point.metrics.total_revenue == Decimal("100.00")


def test_time_series_response_construct(sample_kpi_metrics: KPIMetrics) -> None:
    """A TimeSeriesResponse aggregates points with metadata; filters default None."""
    points = [
        TimeSeriesPoint(period=date(2024, 1, day), metrics=sample_kpi_metrics) for day in (1, 2, 3)
    ]
    response = TimeSeriesResponse(
        granularity=TimeGranularity.WEEK,
        points=points,
        total_points=len(points),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 3),
    )
    assert response.total_points == 3
    assert response.granularity == TimeGranularity.WEEK
    assert response.store_id is None
    assert response.product_id is None
    assert response.category is None


def test_time_series_response_granularity_coercion() -> None:
    """A bare string granularity coerces to the TimeGranularity enum."""
    response = TimeSeriesResponse(
        granularity="day",  # type: ignore[arg-type]
        points=[],
        total_points=0,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 1),
    )
    assert response.granularity is TimeGranularity.DAY


def test_time_series_response_rejects_negative_total_points() -> None:
    """total_points has a ge=0 constraint."""
    with pytest.raises(ValidationError):
        TimeSeriesResponse(
            granularity=TimeGranularity.DAY,
            points=[],
            total_points=-1,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
        )
