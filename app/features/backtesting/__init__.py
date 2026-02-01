"""Backtesting module for time-series forecasting evaluation.

Provides time-based cross-validation, metrics calculation, and baseline comparisons.
"""

from app.features.backtesting.metrics import MetricResult, MetricsCalculator
from app.features.backtesting.schemas import (
    BacktestConfig,
    BacktestRequest,
    BacktestResponse,
    FoldResult,
    ModelBacktestResult,
    SplitBoundary,
    SplitConfig,
)
from app.features.backtesting.splitter import TimeSeriesSplit, TimeSeriesSplitter

__all__ = [
    "BacktestConfig",
    "BacktestRequest",
    "BacktestResponse",
    "FoldResult",
    "MetricResult",
    "MetricsCalculator",
    "ModelBacktestResult",
    "SplitBoundary",
    "SplitConfig",
    "TimeSeriesSplit",
    "TimeSeriesSplitter",
]
