"""Shared feature-frame contract for feature-aware forecasting (MLZOO-A).

The single, cross-cutting home for the regression feature-frame contract — the
pinned constants, the canonical column set, the :class:`FutureFeatureFrame`
carrier, the leakage-safe pure builders, and the :class:`FeatureSafety`
taxonomy. Both the ``forecasting`` slice (historical training frame) and the
``scenarios`` slice (future prediction frame) import from here, so the contract
is defined exactly once.

This package is leaf-level: it imports nothing from ``app/features/**``.
"""

from app.shared.feature_frames.contract import (
    CALENDAR_COLUMNS,
    EXOGENOUS_COLUMNS,
    EXOGENOUS_LAGS,
    FEATURE_CLASS,
    HISTORY_TAIL_DAYS,
    FeatureSafety,
    FutureFeatureFrame,
    build_calendar_columns,
    build_long_lag_columns,
    canonical_feature_columns,
    feature_safety,
)
from app.shared.feature_frames.rows import (
    build_future_feature_rows,
    build_historical_feature_rows,
)

__all__ = [
    "CALENDAR_COLUMNS",
    "EXOGENOUS_COLUMNS",
    "EXOGENOUS_LAGS",
    "FEATURE_CLASS",
    "HISTORY_TAIL_DAYS",
    "FeatureSafety",
    "FutureFeatureFrame",
    "build_calendar_columns",
    "build_future_feature_rows",
    "build_historical_feature_rows",
    "build_long_lag_columns",
    "canonical_feature_columns",
    "feature_safety",
]
