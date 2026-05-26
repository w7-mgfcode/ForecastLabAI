"""Shared feature-frame contract for feature-aware forecasting (MLZOO-A + PRP-35).

The single, cross-cutting home for the regression feature-frame contract — the
pinned constants, the canonical column sets (V1 and V2), the
:class:`FutureFeatureFrame` carrier, the leakage-safe pure builders, and the
:class:`FeatureSafety` taxonomy. Both the ``forecasting`` slice (historical
training frame) and the ``scenarios`` slice (future prediction frame) import
from here, so the contract is defined exactly once.

V2 (PRP-35) adds a richer, opt-in surface alongside V1: every V1 export below
remains at the same position and behaviour; V2 callers reach the V2 manifest /
sidecars / row builders through the same package.

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
from app.shared.feature_frames.contract_v2 import (
    DEFAULT_V2_GROUPS,
    EXOGENOUS_LAGS_V2,
    FEATURE_FRAME_VERSION_V1,
    FEATURE_FRAME_VERSION_V2,
    HISTORY_TAIL_DAYS_V2,
    INVENTORY_AVAILABILITY_WINDOW_V2,
    LIFECYCLE_MATURE_THRESHOLD_DAYS,
    LIFECYCLE_NEW_THRESHOLD_DAYS,
    MACRO_SIGNAL_NAMES_V2,
    REPLENISHMENT_QTY_WINDOW_V2,
    REPLENISHMENT_WINDOW_V2,
    RETURNS_RATE_WINDOW_V2,
    RETURNS_WINDOWS_V2,
    ROLLING_WINDOWS_V2,
    SAME_DOW_MEAN_LOOKBACKS_V2,
    STOCKOUT_WINDOWS_V2,
    TREND_WINDOWS_V2,
    WEATHER_SIGNAL_NAMES_V2,
    FeatureGroup,
    V2ColumnSpec,
    canonical_feature_columns_v2,
    v2_column_manifest,
    v2_feature_groups_dict,
    v2_feature_safety,
    v2_feature_safety_classes,
    v2_pinned_constants,
)
from app.shared.feature_frames.rows import (
    build_future_feature_rows,
    build_historical_feature_rows,
)
from app.shared.feature_frames.rows_v2 import (
    build_future_feature_rows_v2,
    build_historical_feature_rows_v2,
)
from app.shared.feature_frames.sidecar import V2FutureSidecar, V2HistoricalSidecar

__all__ = [
    "CALENDAR_COLUMNS",
    "DEFAULT_V2_GROUPS",
    "EXOGENOUS_COLUMNS",
    "EXOGENOUS_LAGS",
    "EXOGENOUS_LAGS_V2",
    "FEATURE_CLASS",
    "FEATURE_FRAME_VERSION_V1",
    "FEATURE_FRAME_VERSION_V2",
    "HISTORY_TAIL_DAYS",
    "HISTORY_TAIL_DAYS_V2",
    "INVENTORY_AVAILABILITY_WINDOW_V2",
    "LIFECYCLE_MATURE_THRESHOLD_DAYS",
    "LIFECYCLE_NEW_THRESHOLD_DAYS",
    "MACRO_SIGNAL_NAMES_V2",
    "REPLENISHMENT_QTY_WINDOW_V2",
    "REPLENISHMENT_WINDOW_V2",
    "RETURNS_RATE_WINDOW_V2",
    "RETURNS_WINDOWS_V2",
    "ROLLING_WINDOWS_V2",
    "SAME_DOW_MEAN_LOOKBACKS_V2",
    "STOCKOUT_WINDOWS_V2",
    "TREND_WINDOWS_V2",
    "WEATHER_SIGNAL_NAMES_V2",
    "FeatureGroup",
    "FeatureSafety",
    "FutureFeatureFrame",
    "V2ColumnSpec",
    "V2FutureSidecar",
    "V2HistoricalSidecar",
    "build_calendar_columns",
    "build_future_feature_rows",
    "build_future_feature_rows_v2",
    "build_historical_feature_rows",
    "build_historical_feature_rows_v2",
    "build_long_lag_columns",
    "canonical_feature_columns",
    "canonical_feature_columns_v2",
    "feature_safety",
    "v2_column_manifest",
    "v2_feature_groups_dict",
    "v2_feature_safety",
    "v2_feature_safety_classes",
    "v2_pinned_constants",
]
