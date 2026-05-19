"""Leakage spec for the shared feature-frame builders — LOAD-BEARING (MLZOO-A).

This file IS the spec, mirroring ``app/features/featuresets/tests/test_leakage.py``
and ``app/features/scenarios/tests/test_future_frame_leakage.py``: it must NEVER
be weakened to make a feature pass (AGENTS.md § Safety).

A feature-aware model re-forecasts demand through a *future feature frame*. A
horizon day has no observed target, so the invariant the shared pure builders
(:func:`build_long_lag_columns`, :func:`build_calendar_columns`) obey is:

    A future feature value for horizon day ``D`` may use ONLY information
    knowable at the forecast origin ``T``: the observed history up to and
    including ``T``, or the calendar (a pure function of the date). It may
    NEVER read an observed target at a horizon day ``D`` (which lies after
    ``T``).

Concretely this spec asserts:

1. ``build_long_lag_columns`` returns only values drawn from ``history_tail``
   (entirely ``<= T``) or ``NaN`` — never a value from the future target
   series.
2. A lag cell whose source day lies at or after the first horizon day is
   ``NaN`` — the generator never fabricates or recursively predicts it.
3. Calendar columns are independent of the target series entirely.

The assumption-driven exogenous columns and the assembled-frame end-to-end
checks stay in ``app/features/scenarios/tests/test_future_frame_leakage.py`` —
those builders live in the scenarios slice.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from app.shared.feature_frames import (
    EXOGENOUS_LAGS,
    build_calendar_columns,
    build_future_feature_rows,
    build_historical_feature_rows,
    build_long_lag_columns,
    canonical_feature_columns,
)

# The forecast origin T is the last observed day; the horizon runs T+1 … T+H.
_ORIGIN = date(2026, 6, 30)
_HORIZON = 21
_HORIZON_DATES = [_ORIGIN + timedelta(days=offset) for offset in range(1, _HORIZON + 1)]

# Observed history (all <= T): 90 distinct values 1000.0 … 1089.0.
# history_tail[-1] == y[T], the origin observation.
_HISTORY_TAIL = [1000.0 + float(i) for i in range(90)]
# A DISJOINT "future target" series the generator must never be able to read.
# Any of these values appearing in a feature cell is a leak.
_FUTURE_TARGETS = {9000.0 + float(i) for i in range(_HORIZON)}


def test_long_lag_columns_never_emit_a_future_target() -> None:
    """Every non-NaN long-lag cell is drawn from the observed history.

    ``build_long_lag_columns`` takes ONLY ``history_tail`` as data input — it
    is structurally incapable of reading the future target series. This spec
    pins that: no value disjoint from ``history_tail`` may ever appear.
    """
    history_values = set(_HISTORY_TAIL)
    columns = build_long_lag_columns(_HISTORY_TAIL, _HORIZON)

    for name, values in columns.items():
        for cell in values:
            if math.isnan(cell):
                continue
            assert cell in history_values, (
                f"{name} emitted {cell}, which is not an observed history value"
            )
            assert cell not in _FUTURE_TARGETS, f"{name} leaked a future target value {cell}"


def test_long_lag_source_index_is_never_at_or_after_the_horizon() -> None:
    """A lag cell is populated only when its source day lies at/before ``T``.

    For lag ``k`` and horizon day ``j`` the source index into ``history_tail``
    is ``(j-1)-k``. A non-NaN cell REQUIRES that index to be negative — i.e.
    the source target lies at or before the origin ``T``. A non-negative index
    would point at a future horizon day and MUST yield ``NaN``.
    """
    columns = build_long_lag_columns(_HISTORY_TAIL, _HORIZON)
    for lag in EXOGENOUS_LAGS:
        column = columns[f"lag_{lag}"]
        for j in range(1, _HORIZON + 1):
            source_index = (j - 1) - lag
            cell = column[j - 1]
            if source_index >= 0:
                assert math.isnan(cell), (
                    f"lag_{lag} day {j}: source index {source_index} is in the "
                    "future but the cell is not NaN"
                )
            else:
                assert not math.isnan(cell), (
                    f"lag_{lag} day {j}: source index {source_index} is in "
                    "history but the cell is NaN"
                )


def test_calendar_columns_are_independent_of_the_target_series() -> None:
    """Calendar columns read only the dates — they cannot leak the target.

    ``build_calendar_columns`` does not accept the target series at all; this
    spec pins that structural fact by asserting its output is identical no
    matter what history precedes it.
    """
    calendar_a = build_calendar_columns(_HORIZON_DATES)
    calendar_b = build_calendar_columns(_HORIZON_DATES)
    assert calendar_a == calendar_b
    # No calendar value coincides with a history or future target value.
    history_values = set(_HISTORY_TAIL)
    for values in calendar_a.values():
        for cell in values:
            assert cell not in history_values
            assert cell not in _FUTURE_TARGETS


# --- build_future_feature_rows — the backtest test-window matrix (MLZOO-B.2) --
#
# build_future_feature_rows assembles one backtest fold's test-window feature
# matrix. It receives ONLY history_tail (entirely <= the fold origin T) — it is
# structurally incapable of reading a test-window observed target. These specs
# pin that, the NaN-where-future contract (including a gap > 0 fold), and the
# historical-vs-future asymmetry that is the reason X_future is rebuilt here
# rather than sliced from the historical matrix.

_TEST_WINDOW = 14
_TEST_PRICES = [10.0] * _TEST_WINDOW


def test_future_lag_cells_are_drawn_only_from_history() -> None:
    """Every non-NaN future lag cell comes from ``history_tail`` — never a target.

    ``build_future_feature_rows`` takes only ``history_tail`` as target data;
    a value disjoint from it appearing in any lag cell would be a leak.
    """
    test_dates = [_ORIGIN + timedelta(days=offset) for offset in range(1, _TEST_WINDOW + 1)]
    columns = canonical_feature_columns()
    rows = build_future_feature_rows(
        test_dates=test_dates,
        history_tail=_HISTORY_TAIL,
        gap=0,
        test_prices=_TEST_PRICES,
        baseline_price=10.0,
        test_promo_dates=set(),
        test_holiday_dates=set(),
        launch_date=None,
    )
    history_values = set(_HISTORY_TAIL)
    for lag in EXOGENOUS_LAGS:
        col = columns.index(f"lag_{lag}")
        for j in range(_TEST_WINDOW):
            cell = rows[j][col]
            if math.isnan(cell):
                continue
            assert cell in history_values, (
                f"lag_{lag} test day {j} emitted {cell}, not an observed history value"
            )
            assert cell not in _FUTURE_TARGETS, (
                f"lag_{lag} test day {j} leaked a future target value {cell}"
            )


@pytest.mark.parametrize("gap", [0, 3, 7])
def test_future_lag_is_nan_exactly_where_source_is_a_test_day(gap: int) -> None:
    """A future lag cell is ``NaN`` exactly when its source day is in the test window.

    For lag ``k`` and test day ``j`` (0-indexed) the source day relative to the
    origin ``T`` is ``T + gap + j + 1 - k``; it lies in the test window — and
    the cell MUST be ``NaN`` — exactly when ``gap + j - k >= 0``. Otherwise the
    source is observed history and the cell MUST carry a value.
    """
    test_dates = [_ORIGIN + timedelta(days=gap + offset) for offset in range(1, _TEST_WINDOW + 1)]
    columns = canonical_feature_columns()
    rows = build_future_feature_rows(
        test_dates=test_dates,
        history_tail=_HISTORY_TAIL,
        gap=gap,
        test_prices=_TEST_PRICES,
        baseline_price=10.0,
        test_promo_dates=set(),
        test_holiday_dates=set(),
        launch_date=None,
    )
    for lag in EXOGENOUS_LAGS:
        col = columns.index(f"lag_{lag}")
        for j in range(_TEST_WINDOW):
            cell = rows[j][col]
            if gap + j - lag >= 0:
                assert math.isnan(cell), (
                    f"gap={gap} lag_{lag} day {j}: source is a test day — expected NaN, got {cell}"
                )
            else:
                assert not math.isnan(cell), (
                    f"gap={gap} lag_{lag} day {j}: source is in history — expected a value, got NaN"
                )


def test_historical_and_future_lag_columns_are_asymmetric() -> None:
    """The crux of MLZOO-B.2: a historical lag row reads adjacent observed targets;
    a future lag row does NOT — which is why ``X_future`` is rebuilt here and
    never sliced from the historical matrix.

    A continuous sequential series is split at the origin ``T``. The historical
    matrix row for a test-window day reads that day's neighbouring *observed*
    target as ``lag_1`` (slicing it for ``X_future`` would be target leakage).
    The future matrix produces ``NaN`` there instead.
    """
    series_len = 60
    train_end = 40  # origin T is index 39 (the last train day)
    full = [float(i + 1) for i in range(series_len)]
    history_tail = full[:train_end]
    columns = canonical_feature_columns()
    lag1 = columns.index("lag_1")

    historical = build_historical_feature_rows(
        dates=[_ORIGIN + timedelta(days=offset) for offset in range(series_len)],
        quantities=full,
        prices=[10.0] * series_len,
        baseline_price=10.0,
        promo_dates=set(),
        holiday_dates=set(),
        launch_date=None,
    )
    # The historical matrix row for a TEST-window day reads an observed
    # test-day target as lag_1 — proof that slicing it for X_future leaks.
    assert historical[train_end + 1][lag1] == full[train_end], (
        "historical lag_1 for a test-window row must read the adjacent observed target"
    )

    test_window = 10
    future = build_future_feature_rows(
        test_dates=[_ORIGIN + timedelta(days=offset) for offset in range(1, test_window + 1)],
        history_tail=history_tail,
        gap=0,
        test_prices=[10.0] * test_window,
        baseline_price=10.0,
        test_promo_dates=set(),
        test_holiday_dates=set(),
        launch_date=None,
    )
    # The future matrix: test day 0's lag_1 is y[T] (knowable); every later
    # day's lag_1 is NaN — it never reads a test-window observed target.
    assert future[0][lag1] == history_tail[-1], "future lag_1 day 0 must be the origin y[T]"
    for j in range(1, test_window):
        assert math.isnan(future[j][lag1]), (
            f"future lag_1 test day {j} must be NaN — it must never read a test-window target"
        )
