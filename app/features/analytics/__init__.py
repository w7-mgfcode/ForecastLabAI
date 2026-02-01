"""Analytics module for KPI aggregations and drilldowns.

This module provides endpoints for computing sales KPIs and drilling
into data by dimension (store, product, time period).
"""

from app.features.analytics.routes import router
from app.features.analytics.schemas import (
    DrilldownDimension,
    DrilldownResponse,
    KPIResponse,
    TimeGranularity,
)
from app.features.analytics.service import AnalyticsService

__all__ = [
    "AnalyticsService",
    "DrilldownDimension",
    "DrilldownResponse",
    "KPIResponse",
    "TimeGranularity",
    "router",
]
