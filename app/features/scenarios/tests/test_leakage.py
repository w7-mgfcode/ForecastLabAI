"""Leakage spec for scenario simulation — LOAD-BEARING.

This file IS the spec, mirroring the precedent of
``app/features/featuresets/tests/test_leakage.py``: it must NEVER be weakened
to make a feature pass (AGENTS.md § Safety).

The invariant: a scenario adjustment touches ONLY horizon (future) points. It
applies a deterministic post-forecast multiplier to the baseline forecast and
can never reach back into, read, or mutate the historical target series.

Concretely this spec asserts:

1. ``apply_adjustment`` returns a NEW list and never mutates its ``baseline``
   input, and the adjusted series has exactly ``horizon`` points.
2. An assumption window that falls entirely BEFORE the forecast start
   contributes factor ``1.0`` to every horizon day — it cannot affect history,
   and it cannot affect the future either.
3. A day outside any assumption window contributes factor ``1.0``.
4. An empty ``ScenarioAssumptions`` leaves the baseline exactly unchanged.
"""

from datetime import date, timedelta

from app.features.scenarios import adjustments
from app.features.scenarios.schemas import PriceAssumption, ScenarioAssumptions

# A deterministic forecast horizon used throughout this spec.
_FORECAST_START = date(2026, 7, 1)
_HORIZON = 14
_HORIZON_DATES = [_FORECAST_START + timedelta(days=offset) for offset in range(_HORIZON)]


def test_apply_adjustment_does_not_mutate_baseline() -> None:
    """``apply_adjustment`` returns a new list; the input baseline is untouched."""
    baseline = [10.0] * _HORIZON
    baseline_snapshot = list(baseline)
    factors = [1.5] * _HORIZON

    adjusted = adjustments.apply_adjustment(baseline, factors)

    assert adjusted is not baseline, "apply_adjustment must return a NEW list"
    assert baseline == baseline_snapshot, "the input baseline must never be mutated"
    assert len(adjusted) == _HORIZON, "the adjusted series must keep the horizon length"


def test_assumption_window_before_forecast_start_has_no_effect() -> None:
    """A price window entirely before the forecast start contributes no factor.

    The window 2026-06-01 .. 2026-06-15 ends before the forecast starts on
    2026-07-01. Every horizon day must therefore receive factor 1.0 — the
    adjustment can never reach a date outside the future horizon.
    """
    past_window = ScenarioAssumptions(
        price=PriceAssumption(
            change_pct=-0.30,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 15),
        )
    )
    factors = [
        adjustments.combined_daily_factor(point_date, past_window) for point_date in _HORIZON_DATES
    ]
    assert factors == [1.0] * _HORIZON, "a pre-forecast window must not affect the horizon"


def test_out_of_window_days_contribute_unit_factor() -> None:
    """Only days inside the assumption window are adjusted; the rest stay 1.0.

    The window covers exactly the first three horizon days; days 4..14 must be
    untouched (factor 1.0).
    """
    windowed = ScenarioAssumptions(
        price=PriceAssumption(
            change_pct=-0.25,
            start_date=_HORIZON_DATES[0],
            end_date=_HORIZON_DATES[2],
        )
    )
    factors = [
        adjustments.combined_daily_factor(point_date, windowed) for point_date in _HORIZON_DATES
    ]
    assert all(factor > 1.0 for factor in factors[:3]), "in-window days must be adjusted"
    assert factors[3:] == [1.0] * (_HORIZON - 3), "out-of-window days must stay neutral"


def test_empty_assumptions_leave_baseline_unchanged() -> None:
    """With no assumptions the scenario series equals the baseline exactly."""
    baseline = [float(value) for value in range(1, _HORIZON + 1)]
    factors = [
        adjustments.combined_daily_factor(point_date, ScenarioAssumptions())
        for point_date in _HORIZON_DATES
    ]
    scenario = adjustments.apply_adjustment(baseline, factors)
    assert scenario == baseline, "an empty scenario must not move the baseline"
