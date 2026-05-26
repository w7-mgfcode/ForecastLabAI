"""Leakage spec for the V2 feature-frame builders — LOAD-BEARING (PRP-35).

This file IS the spec, mirroring ``app/shared/feature_frames/tests/test_leakage.py``:
it must NEVER be weakened to make a feature pass (AGENTS.md § Safety).

The V2 builders extend V1 with rolling / trend / lifecycle / inventory /
replenishment / returns / exogenous columns. The invariant is the same as V1:

    A future feature value for horizon day ``D`` may use ONLY information
    knowable at the forecast origin ``T``: the observed history up to and
    including ``T``, the calendar (a pure function of the date), launch /
    discontinue dates, or scenario-assumption inputs posited by the caller.
    It NEVER reads an observed target — or any sidecar value — at a horizon
    day ``D`` (which lies after ``T``).

Sequential targets (1.0 … N.0) are used so leakage is mathematically
detectable: a rolling-mean cell at row ``i`` MUST be strictly less than the
current row's target ``i+1`` for the sequential fixture. A disjoint future
target set ({9000.0 … 9999.0}) pins the future-builder side: any future-target
value appearing in any feature cell is a leak.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from app.shared.feature_frames import (
    EXOGENOUS_LAGS_V2,
    ROLLING_WINDOWS_V2,
    SAME_DOW_MEAN_LOOKBACKS_V2,
    TREND_WINDOWS_V2,
    FeatureGroup,
    V2FutureSidecar,
    V2HistoricalSidecar,
    build_future_feature_rows_v2,
    build_historical_feature_rows_v2,
    canonical_feature_columns_v2,
)

# Sequential observed history: 400 days so lag_364 / rolling_90 / trend_90 are
# all resolvable for the future builder's j=1 row.
_N = 400
_ORIGIN = date(2026, 6, 30)
_HISTORY_DATES = [date(2026, 1, 1) + timedelta(days=offset) for offset in range(_N)]
_HISTORY_TAIL = [1000.0 + float(i) for i in range(_N)]  # 1000.0 … 1399.0
# A DISJOINT "future target" set the V2 builders must never read.
_HORIZON = 21
_FUTURE_TARGETS = {9000.0 + float(i) for i in range(_HORIZON)}


# ─── Historical builder — leakage by sequential-target detection ────────────


def _build_historical() -> tuple[list[str], list[list[float]]]:
    """Assemble a V2 historical matrix from sequential targets."""
    columns = canonical_feature_columns_v2()
    sidecar = V2HistoricalSidecar()
    rows = build_historical_feature_rows_v2(
        dates=_HISTORY_DATES,
        quantities=_HISTORY_TAIL,
        prices=[10.0] * _N,
        baseline_price=10.0,
        sidecar=sidecar,
    )
    return columns, rows


def test_v2_lag_columns_read_only_strictly_earlier_observations() -> None:
    """Every V2 ``lag_*`` cell with sequential targets is ``< quantity[i]`` or NaN."""
    columns, rows = _build_historical()
    for lag in EXOGENOUS_LAGS_V2:
        col_index = columns.index(f"lag_{lag}")
        for i in range(_N):
            cell = rows[i][col_index]
            if i < lag:
                assert math.isnan(cell), f"row {i}: lag_{lag} expected NaN, got {cell}"
                continue
            expected = _HISTORY_TAIL[i - lag]
            assert cell == expected, f"LEAKAGE at row {i}: lag_{lag}={cell} != expected={expected}"
            assert cell < _HISTORY_TAIL[i], (
                f"LEAKAGE at row {i}: lag_{lag}={cell} >= current={_HISTORY_TAIL[i]}"
            )


def test_v2_rolling_mean_reads_only_strictly_earlier_rows() -> None:
    """``rolling_mean_W`` at row ``i`` strictly < ``quantity[i]`` (sequential fixture)."""
    columns, rows = _build_historical()
    for window in ROLLING_WINDOWS_V2:
        col_index = columns.index(f"rolling_mean_{window}")
        for i in range(_N):
            cell = rows[i][col_index]
            if i < window:
                assert math.isnan(cell), f"row {i}: rolling_mean_{window} expected NaN"
                continue
            expected = sum(_HISTORY_TAIL[i - window : i]) / window
            assert cell == expected, f"row {i}: rolling_mean_{window}={cell} != expected={expected}"
            assert cell < _HISTORY_TAIL[i], (
                f"LEAKAGE at row {i}: rolling_mean_{window}={cell} >= current={_HISTORY_TAIL[i]}"
            )


def test_v2_rolling_std_first_rows_are_nan() -> None:
    columns, rows = _build_historical()
    col_index = columns.index("rolling_std_28")
    for i in range(28):
        assert math.isnan(rows[i][col_index]), f"rolling_std_28 row {i}: expected NaN"
    # After 28 rows the std becomes computable.
    for i in range(28, _N):
        assert not math.isnan(rows[i][col_index]), (
            f"rolling_std_28 row {i}: expected a value, got NaN"
        )


def test_v2_same_dow_mean_reads_only_strictly_earlier_observations() -> None:
    """Same-DOW means only see earlier same-weekday rows."""
    columns, rows = _build_historical()
    for n_back in SAME_DOW_MEAN_LOOKBACKS_V2:
        col_index = columns.index(f"same_dow_mean_{n_back}")
        for i in range(_N):
            cell = rows[i][col_index]
            if math.isnan(cell):
                continue
            # If non-NaN: cell must be strictly < current quantity (sequential
            # fixture: any earlier index ⇒ smaller value).
            assert cell < _HISTORY_TAIL[i], (
                f"LEAKAGE at row {i}: same_dow_mean_{n_back}={cell} >= current"
            )


def test_v2_trend_columns_first_window_rows_are_nan() -> None:
    columns, rows = _build_historical()
    for window in TREND_WINDOWS_V2:
        col_index = columns.index(f"trend_{window}")
        for i in range(window):
            assert math.isnan(rows[i][col_index]), (
                f"trend_{window} row {i}: expected NaN (insufficient history)"
            )


# ─── Future builder — no future-target value may ever appear ────────────────


def _build_future(gap: int = 0, horizon: int = _HORIZON) -> tuple[list[str], list[list[float]]]:
    test_dates = [_ORIGIN + timedelta(days=gap + offset) for offset in range(1, horizon + 1)]
    history_tail_dates = _HISTORY_DATES
    columns = canonical_feature_columns_v2()
    rows = build_future_feature_rows_v2(
        test_dates=test_dates,
        history_tail=_HISTORY_TAIL,
        history_tail_dates=history_tail_dates,
        gap=gap,
        baseline_price=10.0,
        sidecar=V2FutureSidecar(),
    )
    return columns, rows


def test_future_v2_lag_cells_are_drawn_only_from_history() -> None:
    """Every non-NaN ``lag_*`` cell in the V2 future matrix is from ``history_tail``."""
    columns, rows = _build_future(gap=0)
    history_values = set(_HISTORY_TAIL)
    for lag in EXOGENOUS_LAGS_V2:
        col_index = columns.index(f"lag_{lag}")
        for j in range(_HORIZON):
            cell = rows[j][col_index]
            if math.isnan(cell):
                continue
            assert cell in history_values, (
                f"future lag_{lag} day {j}: leaked non-history value {cell}"
            )
            assert cell not in _FUTURE_TARGETS, (
                f"future lag_{lag} day {j}: leaked FUTURE target {cell}"
            )


@pytest.mark.parametrize("gap", [0, 3, 7])
def test_future_v2_lag_nan_pattern_matches_source_index(gap: int) -> None:
    """A V2 ``lag_k`` cell is NaN exactly when its source day is in the test window.

    For lag ``k`` and test day ``j`` (0-indexed) the source day relative to
    ``T`` is ``gap + j + 1 - k``. The cell MUST be NaN exactly when
    ``gap + j - k >= 0`` (source is a future day).
    """
    columns, rows = _build_future(gap=gap, horizon=_HORIZON)
    for lag in EXOGENOUS_LAGS_V2:
        col_index = columns.index(f"lag_{lag}")
        for j in range(_HORIZON):
            cell = rows[j][col_index]
            if gap + j - lag >= 0:
                assert math.isnan(cell), (
                    f"gap={gap} lag_{lag} day {j}: source future — expected NaN, got {cell}"
                )
            else:
                assert not math.isnan(cell), (
                    f"gap={gap} lag_{lag} day {j}: source in history — expected value"
                )


def test_future_v2_rolling_mean_only_horizon_day_1_is_computable() -> None:
    """``rolling_mean_W`` is computable at horizon ``j=1`` (window entirely ``<= T``);
    NaN for every ``j >= 2`` (window touches future).
    """
    columns, rows = _build_future(gap=0)
    for window in ROLLING_WINDOWS_V2:
        col_index = columns.index(f"rolling_mean_{window}")
        # j=0 (test day 1) — computable
        first = rows[0][col_index]
        expected = sum(_HISTORY_TAIL[-window:]) / window
        assert first == expected, (
            f"future rolling_mean_{window} day 1: expected {expected}, got {first}"
        )
        # j>=1 — NaN
        for j in range(1, _HORIZON):
            assert math.isnan(rows[j][col_index]), (
                f"future rolling_mean_{window} day {j + 1}: expected NaN, got {rows[j][col_index]}"
            )


def test_future_v2_trend_only_horizon_day_1_is_computable() -> None:
    columns, rows = _build_future(gap=0)
    for window in TREND_WINDOWS_V2:
        col_index = columns.index(f"trend_{window}")
        assert not math.isnan(rows[0][col_index]), f"future trend_{window} day 1: expected a value"
        for j in range(1, _HORIZON):
            assert math.isnan(rows[j][col_index]), (
                f"future trend_{window} day {j + 1}: expected NaN"
            )


def test_future_v2_calendar_columns_independent_of_target_series() -> None:
    """Calendar columns read only the dates — they cannot leak the target."""
    columns, rows = _build_future(gap=0)
    history_values = set(_HISTORY_TAIL)
    cal_names = {
        "dow_sin",
        "dow_cos",
        "month_sin",
        "month_cos",
        "is_weekend",
        "is_month_end",
        "week_of_year_sin",
        "week_of_year_cos",
        "day_of_month_sin",
        "day_of_month_cos",
        "is_holiday",
    }
    for name in cal_names:
        col_index = columns.index(name)
        for j in range(_HORIZON):
            cell = rows[j][col_index]
            assert cell not in history_values, (
                f"calendar {name} day {j}: cell {cell} accidentally coincides with history"
            )
            assert cell not in _FUTURE_TARGETS, (
                f"calendar {name} day {j}: cell {cell} accidentally coincides with future target"
            )


def test_future_v2_lag_364_is_dow_aligned() -> None:
    """``lag_364`` at horizon day 1 reads ``history_tail[-364]`` — same weekday as day 1."""
    columns, rows = _build_future(gap=0)
    col_index = columns.index("lag_364")
    expected = _HISTORY_TAIL[-364]
    assert rows[0][col_index] == expected, (
        f"future lag_364 day 1: expected {expected}, got {rows[0][col_index]}"
    )
    # Day 365 → source index (365-1) - 364 = 0 (non-negative) → NaN
    rows365 = build_future_feature_rows_v2(
        test_dates=[_ORIGIN + timedelta(days=offset) for offset in range(1, 366)],
        history_tail=_HISTORY_TAIL,
        history_tail_dates=_HISTORY_DATES,
        gap=0,
        baseline_price=10.0,
        sidecar=V2FutureSidecar(),
    )
    assert math.isnan(rows365[364][col_index]), (
        "future lag_364 at horizon day 365: source is T+1 (future) — expected NaN"
    )


def test_future_v2_inventory_group_off_default_omits_inventory_columns() -> None:
    """Default-V2 manifest does not include INVENTORY columns (off by default)."""
    columns, _ = _build_future(gap=0)
    assert "is_stockout_lag1" not in columns
    assert "stockout_days_7" not in columns
    assert "inventory_available_ratio_28" not in columns


def test_future_v2_inventory_stockout_days_horizon_2_plus_nan() -> None:
    """When INVENTORY enabled but no caller-supplied projection, j>=2 is NaN."""
    test_dates = [_ORIGIN + timedelta(days=offset) for offset in range(1, _HORIZON + 1)]
    rows = build_future_feature_rows_v2(
        test_dates=test_dates,
        history_tail=_HISTORY_TAIL,
        history_tail_dates=_HISTORY_DATES,
        gap=0,
        baseline_price=10.0,
        sidecar=V2FutureSidecar(),
        history_tail_stockouts=tuple([False] * _N),
        groups=(FeatureGroup.INVENTORY,),
    )
    columns = canonical_feature_columns_v2(groups=(FeatureGroup.INVENTORY,))
    for name in ("is_stockout_lag1", "stockout_days_7", "stockout_days_28"):
        col_index = columns.index(name)
        # Day 1 may be a value (computable from history) or NaN; day >= 2 must be NaN
        for j in range(1, _HORIZON):
            assert math.isnan(rows[j][col_index]), (
                f"{name} day {j + 1}: expected NaN (no projected stockouts), got {rows[j][col_index]}"
            )


def test_future_v2_price_promo_is_nan_when_unsupplied() -> None:
    """PRICE_PROMO columns are UNSAFE_UNLESS_SUPPLIED — empty sidecar arrays → NaN."""
    test_dates = [_ORIGIN + timedelta(days=offset) for offset in range(1, _HORIZON + 1)]
    rows = build_future_feature_rows_v2(
        test_dates=test_dates,
        history_tail=_HISTORY_TAIL,
        history_tail_dates=_HISTORY_DATES,
        gap=0,
        baseline_price=10.0,
        sidecar=V2FutureSidecar(),  # no posited price / promo
        groups=(FeatureGroup.PRICE_PROMO,),
    )
    columns = canonical_feature_columns_v2(groups=(FeatureGroup.PRICE_PROMO,))
    for name in (
        "price_factor",
        "promo_active",
        "promo_discount_pct",
        "promo_kind_markdown_active",
        "promo_kind_bundle_active",
    ):
        col_index = columns.index(name)
        for j in range(_HORIZON):
            assert math.isnan(rows[j][col_index]), (
                f"{name} day {j + 1}: expected NaN (sidecar empty), got {rows[j][col_index]}"
            )
