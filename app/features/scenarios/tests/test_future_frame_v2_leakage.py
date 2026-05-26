"""V2 leakage spec for the scenarios future frame — LOAD-BEARING (PRP-35).

Mirrors ``test_future_frame_leakage.py`` for the V2 builder. Pure (no DB):
exercises ``build_future_feature_rows_v2`` directly with the
:class:`V2FutureSidecar` shape the scenarios slice assembles when re-forecasting
a V2 bundle.

Must NEVER be weakened to make a feature pass (AGENTS.md § Safety).
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from app.shared.feature_frames import (
    EXOGENOUS_LAGS_V2,
    FeatureGroup,
    V2FutureSidecar,
    build_future_feature_rows_v2,
    canonical_feature_columns_v2,
    v2_feature_safety,
)
from app.shared.feature_frames.contract import FeatureSafety

_ORIGIN = date(2026, 6, 30)
_HORIZON = 14
_HISTORY_TAIL = [1000.0 + float(i) for i in range(400)]
_HISTORY_TAIL_DATES = [_ORIGIN - timedelta(days=399 - i) for i in range(400)]


def test_v2_future_assumption_driven_price_factor_reflects_input() -> None:
    """When the caller supplies ``price_factor_per_day`` it appears in the cell."""
    test_dates = [_ORIGIN + timedelta(days=offset) for offset in range(1, _HORIZON + 1)]
    posited = [0.85] * _HORIZON  # 15% price cut every day
    sidecar = V2FutureSidecar(
        price_factor_per_day=tuple(posited),
        promo_active_per_day=tuple([False] * _HORIZON),
        promo_kinds_per_day=tuple([frozenset() for _ in range(_HORIZON)]),
        promo_discount_pct_per_day=tuple([0.0] * _HORIZON),
    )
    columns = canonical_feature_columns_v2(groups=(FeatureGroup.PRICE_PROMO,))
    rows = build_future_feature_rows_v2(
        test_dates=test_dates,
        history_tail=_HISTORY_TAIL,
        history_tail_dates=_HISTORY_TAIL_DATES,
        gap=0,
        baseline_price=1.0,
        sidecar=sidecar,
        groups=(FeatureGroup.PRICE_PROMO,),
    )
    col_index = columns.index("price_factor")
    for j in range(_HORIZON):
        assert rows[j][col_index] == 0.85, (
            f"day {j + 1}: price_factor expected 0.85, got {rows[j][col_index]}"
        )


def test_v2_future_unsupplied_price_promo_yields_nan() -> None:
    """When the sidecar omits the assumption arrays, PRICE_PROMO cells are NaN."""
    test_dates = [_ORIGIN + timedelta(days=offset) for offset in range(1, _HORIZON + 1)]
    sidecar = V2FutureSidecar()  # nothing posited
    columns = canonical_feature_columns_v2(groups=(FeatureGroup.PRICE_PROMO,))
    rows = build_future_feature_rows_v2(
        test_dates=test_dates,
        history_tail=_HISTORY_TAIL,
        history_tail_dates=_HISTORY_TAIL_DATES,
        gap=0,
        baseline_price=1.0,
        sidecar=sidecar,
        groups=(FeatureGroup.PRICE_PROMO,),
    )
    for column in columns:
        assert v2_feature_safety(column) is FeatureSafety.UNSAFE_UNLESS_SUPPLIED
    for j in range(_HORIZON):
        for column in columns:
            cell = rows[j][columns.index(column)]
            assert math.isnan(cell), (
                f"day {j + 1}: PRICE_PROMO column {column!r} expected NaN, got {cell}"
            )


def test_v2_future_lag_cells_drawn_only_from_history() -> None:
    """Every non-NaN ``lag_*`` cell in the V2 future frame is from history_tail."""
    test_dates = [_ORIGIN + timedelta(days=offset) for offset in range(1, _HORIZON + 1)]
    sidecar = V2FutureSidecar()
    columns = canonical_feature_columns_v2(groups=(FeatureGroup.TARGET_HISTORY,))
    rows = build_future_feature_rows_v2(
        test_dates=test_dates,
        history_tail=_HISTORY_TAIL,
        history_tail_dates=_HISTORY_TAIL_DATES,
        gap=0,
        baseline_price=1.0,
        sidecar=sidecar,
        groups=(FeatureGroup.TARGET_HISTORY,),
    )
    history_values = set(_HISTORY_TAIL)
    future_targets = {9000.0 + float(i) for i in range(_HORIZON)}
    for lag in EXOGENOUS_LAGS_V2:
        col_index = columns.index(f"lag_{lag}")
        for j in range(_HORIZON):
            cell = rows[j][col_index]
            if math.isnan(cell):
                continue
            assert cell in history_values, f"lag_{lag} day {j + 1}: leaked non-history value {cell}"
            assert cell not in future_targets, f"lag_{lag} day {j + 1}: leaked future target {cell}"


def test_v2_future_weather_macro_nan_when_sidecar_empty() -> None:
    """EXOGENOUS_WEATHER / MACRO columns are NaN when sidecar dicts are empty."""
    test_dates = [_ORIGIN + timedelta(days=offset) for offset in range(1, _HORIZON + 1)]
    sidecar = V2FutureSidecar()
    columns = canonical_feature_columns_v2(
        groups=(FeatureGroup.EXOGENOUS_WEATHER, FeatureGroup.EXOGENOUS_MACRO)
    )
    rows = build_future_feature_rows_v2(
        test_dates=test_dates,
        history_tail=_HISTORY_TAIL,
        history_tail_dates=_HISTORY_TAIL_DATES,
        gap=0,
        baseline_price=1.0,
        sidecar=sidecar,
        groups=(FeatureGroup.EXOGENOUS_WEATHER, FeatureGroup.EXOGENOUS_MACRO),
    )
    for j in range(_HORIZON):
        for column in columns:
            cell = rows[j][columns.index(column)]
            assert math.isnan(cell), (
                f"day {j + 1}: {column!r} expected NaN (empty sidecar), got {cell}"
            )


def test_v2_future_lifecycle_safe_when_launch_date_supplied() -> None:
    """LIFECYCLE columns are SAFE (pure function of dates + launch/discontinue)."""
    test_dates = [_ORIGIN + timedelta(days=offset) for offset in range(1, _HORIZON + 1)]
    launch = _ORIGIN - timedelta(days=100)  # 100 days before T
    sidecar = V2FutureSidecar(launch_date=launch)
    columns = canonical_feature_columns_v2(groups=(FeatureGroup.LIFECYCLE,))
    rows = build_future_feature_rows_v2(
        test_dates=test_dates,
        history_tail=_HISTORY_TAIL,
        history_tail_dates=_HISTORY_TAIL_DATES,
        gap=0,
        baseline_price=1.0,
        sidecar=sidecar,
        groups=(FeatureGroup.LIFECYCLE,),
    )
    days_since_idx = columns.index("days_since_launch")
    # Test day 1 → days_since_launch = 101
    assert rows[0][days_since_idx] == 101.0
    # Test day 14 → 114
    assert rows[13][days_since_idx] == 114.0
    # is_mature_product = 1.0 (>= 180 days threshold? no — 101 days < 180), so 0.0
    is_mature_idx = columns.index("is_mature_product")
    assert rows[0][is_mature_idx] == 0.0
    # is_new_product = 0.0 (>= 30 days)
    is_new_idx = columns.index("is_new_product")
    assert rows[0][is_new_idx] == 0.0
