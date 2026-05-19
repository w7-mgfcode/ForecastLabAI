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

from app.shared.feature_frames import (
    EXOGENOUS_LAGS,
    build_calendar_columns,
    build_long_lag_columns,
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
