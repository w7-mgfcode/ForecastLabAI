"""Leakage spec for the scenarios future frame — LOAD-BEARING (PRP-27 Phase A).

This file IS the spec, mirroring ``app/features/featuresets/tests/test_leakage.py``
and ``app/features/scenarios/tests/test_leakage.py``: it must NEVER be weakened
to make a feature pass (AGENTS.md § Safety).

Its scope is the parts of the future frame the **scenarios slice** owns: the
assumption-driven exogenous columns (``build_exogenous_columns``) and the
end-to-end assembled frame (``assemble_future_frame``). The shared pure builders
(``build_calendar_columns``, ``build_long_lag_columns``) moved to
``app/shared/feature_frames`` in MLZOO-A and are spec'd by the load-bearing
``app/shared/feature_frames/tests/test_leakage.py``.

The model-driven scenario path re-forecasts demand through a feature-consuming
regressor, which means it builds a *future feature frame*. A horizon day has no
observed target, so the invariant is:

    A future feature value for horizon day ``D`` may use ONLY information
    knowable at the forecast origin ``T``: the observed history up to and
    including ``T``, the calendar (a pure function of the date), or the
    scenario assumptions (the planner's posited future inputs). It may NEVER
    read an observed target at a horizon day ``D`` (which lies after ``T``).

Concretely this spec asserts:

1. An assumption window that falls before the forecast origin contributes
   nothing — every horizon day lies strictly after ``T``.
2. Every non-``NaN`` ``lag_*`` cell in an assembled frame is a member of
   ``history_tail``.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from app.features.scenarios.feature_frame import (
    assemble_future_frame,
    build_exogenous_columns,
)
from app.features.scenarios.schemas import PriceAssumption, ScenarioAssumptions
from app.shared.feature_frames import EXOGENOUS_LAGS, canonical_feature_columns

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
