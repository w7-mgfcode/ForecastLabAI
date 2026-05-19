"""Leakage spec for the future feature frame — LOAD-BEARING (PRP-27 Phase A).

This file IS the spec, mirroring ``app/features/featuresets/tests/test_leakage.py``
and ``app/features/scenarios/tests/test_leakage.py``: it must NEVER be weakened
to make a feature pass (AGENTS.md § Safety).

The model-driven scenario path re-forecasts demand through a feature-consuming
regressor, which means it builds a *future feature frame*. A horizon day has no
observed target, so the invariant is:

    A future feature value for horizon day ``D`` may use ONLY information
    knowable at the forecast origin ``T``: the observed history up to and
    including ``T``, the calendar (a pure function of the date), or the
    scenario assumptions (the planner's posited future inputs). It may NEVER
    read an observed target at a horizon day ``D`` (which lies after ``T``).

Concretely this spec asserts:

1. ``build_long_lag_columns`` returns only values drawn from ``history_tail``
   (entirely ``<= T``) or ``NaN`` — never a value from the future target
   series.
2. A lag cell whose source day lies at or after the first horizon day is
   ``NaN`` — the generator never fabricates or recursively predicts it.
3. Calendar columns are independent of the target series entirely.
4. An assumption window that falls before the forecast origin contributes
   nothing — every horizon day lies strictly after ``T``.
5. Every non-``NaN`` ``lag_*`` cell in an assembled frame is a member of
   ``history_tail``.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from app.features.scenarios.feature_frame import (
    EXOGENOUS_LAGS,
    assemble_future_frame,
    build_calendar_columns,
    build_exogenous_columns,
    build_long_lag_columns,
    canonical_feature_columns,
)
from app.features.scenarios.schemas import PriceAssumption, ScenarioAssumptions

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


def test_assumption_window_before_origin_has_no_effect() -> None:
    """A price window entirely before the forecast origin contributes nothing.

    Every horizon day lies strictly after ``T``; a window that ends on or
    before ``T`` can never intersect the horizon, so ``price_factor`` stays
    neutral (``1.0``) for every day — the assumption cannot reach into history.
    """
    past_window = ScenarioAssumptions(
        price=PriceAssumption(
            change_pct=-0.40,
            start_date=_ORIGIN - timedelta(days=30),
            end_date=_ORIGIN,
        )
    )
    columns = build_exogenous_columns(_HORIZON_DATES, past_window, set(), launch_date=None)
    assert columns["price_factor"] == [1.0] * _HORIZON, (
        "a price window ending at/before the origin must not move price_factor"
    )


def test_assembled_frame_lag_cells_are_history_or_nan() -> None:
    """Every non-NaN ``lag_*`` cell in an assembled frame is an observed value.

    This is the end-to-end leakage assertion: assemble a full frame and verify
    every target-lag column still only ever shows a history value or ``NaN``.
    """
    columns = canonical_feature_columns()
    frame = assemble_future_frame(
        dates=_HORIZON_DATES,
        feature_columns=columns,
        history_tail=_HISTORY_TAIL,
        assumptions=ScenarioAssumptions(),
        holiday_dates=set(),
        launch_date=None,
    )
    history_values = set(_HISTORY_TAIL)
    lag_indices = {columns.index(f"lag_{k}") for k in EXOGENOUS_LAGS}
    for row in frame.matrix:
        for col_index in lag_indices:
            cell = row[col_index]
            if math.isnan(cell):
                continue
            assert cell in history_values, f"assembled frame leaked non-history value {cell}"
            assert cell not in _FUTURE_TARGETS, f"assembled frame leaked future target {cell}"
