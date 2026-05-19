"""Unit tests for the future feature-frame generator (PRP-27 Phase A).

These exercise the pure builders — calendar columns, target long-lag columns,
assumption-driven exogenous columns, and the :func:`assemble_future_frame`
orchestration. The leakage invariants live separately in
``test_future_frame_leakage.py`` (the load-bearing spec).
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from app.features.scenarios.feature_frame import (
    CALENDAR_COLUMNS,
    EXOGENOUS_COLUMNS,
    EXOGENOUS_LAGS,
    HISTORY_TAIL_DAYS,
    MAX_COMPARE_SCENARIOS,
    assemble_future_frame,
    build_calendar_columns,
    build_exogenous_columns,
    build_long_lag_columns,
    canonical_feature_columns,
)
from app.features.scenarios.schemas import (
    HolidayAssumption,
    PriceAssumption,
    PromotionAssumption,
    ScenarioAssumptions,
)

_ORIGIN = date(2026, 6, 30)
_HORIZON = 14
_HORIZON_DATES = [_ORIGIN + timedelta(days=offset) for offset in range(1, _HORIZON + 1)]


# --- pinned constants ---------------------------------------------------------


def test_pinned_constants() -> None:
    """The PRP-27 pinned modelling constants hold their decided values."""
    assert EXOGENOUS_LAGS == (1, 7, 14, 28)
    assert HISTORY_TAIL_DAYS == 90
    assert MAX_COMPARE_SCENARIOS == 5


def test_canonical_feature_columns_order() -> None:
    """The canonical column list is target lags, then calendar, then exogenous."""
    columns = canonical_feature_columns()
    assert columns[:4] == ["lag_1", "lag_7", "lag_14", "lag_28"]
    assert columns[4 : 4 + len(CALENDAR_COLUMNS)] == list(CALENDAR_COLUMNS)
    assert columns[-len(EXOGENOUS_COLUMNS) :] == list(EXOGENOUS_COLUMNS)
    assert len(columns) == len(EXOGENOUS_LAGS) + len(CALENDAR_COLUMNS) + len(EXOGENOUS_COLUMNS)


# --- calendar columns ---------------------------------------------------------


def test_calendar_columns_are_pure_function_of_date() -> None:
    """Calendar columns depend only on the dates — two calls match exactly."""
    first = build_calendar_columns(_HORIZON_DATES)
    second = build_calendar_columns(list(_HORIZON_DATES))
    assert first == second
    assert set(first) == set(CALENDAR_COLUMNS)
    for values in first.values():
        assert len(values) == _HORIZON


def test_calendar_is_weekend_and_month_end() -> None:
    """``is_weekend`` and ``is_month_end`` reflect the date itself."""
    dates = [date(2026, 7, 30), date(2026, 7, 31), date(2026, 8, 1), date(2026, 8, 2)]
    columns = build_calendar_columns(dates)
    # 2026-07-31 is the month end; 2026-08-01 (Sat) and 2026-08-02 (Sun) weekend.
    assert columns["is_month_end"] == [0.0, 1.0, 0.0, 0.0]
    assert columns["is_weekend"] == [1.0 if d.weekday() >= 5 else 0.0 for d in dates]


def test_calendar_cyclical_encoding_bounded() -> None:
    """Cyclical sin/cos encodings stay within [-1, 1]."""
    columns = build_calendar_columns(_HORIZON_DATES)
    for name in ("dow_sin", "dow_cos", "month_sin", "month_cos"):
        assert all(-1.0 <= value <= 1.0 for value in columns[name])


# --- long-lag columns ---------------------------------------------------------


def test_long_lag_indexing_is_correct() -> None:
    """``lag_k`` at horizon day ``j`` equals the observed ``y[T+j-k]``."""
    # history_tail[-1] == y[T], history_tail[-2] == y[T-1], ...
    history_tail = [float(value) for value in range(HISTORY_TAIL_DAYS)]
    columns = build_long_lag_columns(history_tail, _HORIZON)

    assert set(columns) == {f"lag_{k}" for k in EXOGENOUS_LAGS}
    # lag_1 at j=1 reads history_tail[-1] (y[T]); j>=2 needs a future target.
    assert columns["lag_1"][0] == history_tail[-1]
    assert all(math.isnan(value) for value in columns["lag_1"][1:])
    # lag_7 at j=1 reads history_tail[-7]; populated for j in 1..7.
    assert columns["lag_7"][0] == history_tail[-7]
    for j in range(1, _HORIZON + 1):
        cell = columns["lag_7"][j - 1]
        if j <= 7:
            assert cell == history_tail[(j - 1) - 7]
        else:
            assert math.isnan(cell)


def test_long_lag_all_columns_present_for_long_horizon() -> None:
    """Every lag column is emitted even when the horizon exceeds the offset."""
    history_tail = [float(value) for value in range(HISTORY_TAIL_DAYS)]
    columns = build_long_lag_columns(history_tail, horizon=40)
    assert set(columns) == {f"lag_{k}" for k in EXOGENOUS_LAGS}
    # lag_28 over a 40-day horizon: first 28 days populated, last 12 NaN.
    assert all(not math.isnan(v) for v in columns["lag_28"][:28])
    assert all(math.isnan(v) for v in columns["lag_28"][28:])


def test_long_lag_short_history_yields_nan() -> None:
    """A history shorter than the lag offset produces NaN, never an error."""
    columns = build_long_lag_columns([5.0, 6.0, 7.0], horizon=4)
    # lag_28 cannot resolve from a 3-element tail — all NaN.
    assert all(math.isnan(value) for value in columns["lag_28"])
    # lag_1 at j=1 still resolves to the origin observation.
    assert columns["lag_1"][0] == 7.0


# --- exogenous columns --------------------------------------------------------


def test_exogenous_price_window() -> None:
    """``price_factor`` is ``1 + change_pct`` inside the window, ``1.0`` outside."""
    assumptions = ScenarioAssumptions(
        price=PriceAssumption(
            change_pct=-0.15,
            start_date=_HORIZON_DATES[2],
            end_date=_HORIZON_DATES[5],
        )
    )
    columns = build_exogenous_columns(_HORIZON_DATES, assumptions, set(), launch_date=None)
    for index, value in enumerate(columns["price_factor"]):
        if 2 <= index <= 5:
            assert value == 0.85
        else:
            assert value == 1.0


def test_exogenous_promo_and_holiday() -> None:
    """``promo_active`` flags the promotion window; ``is_holiday`` unions sources."""
    calendar_holiday = _HORIZON_DATES[0]
    assumption_holiday = _HORIZON_DATES[9]
    assumptions = ScenarioAssumptions(
        promotion=PromotionAssumption(
            kind="pct_off",
            start_date=_HORIZON_DATES[1],
            end_date=_HORIZON_DATES[3],
        ),
        holiday=HolidayAssumption(dates=[assumption_holiday]),
    )
    columns = build_exogenous_columns(
        _HORIZON_DATES, assumptions, {calendar_holiday}, launch_date=None
    )
    assert [i for i, v in enumerate(columns["promo_active"]) if v == 1.0] == [1, 2, 3]
    # is_holiday unions the calendar holiday and the assumption holiday.
    assert [i for i, v in enumerate(columns["is_holiday"]) if v == 1.0] == [0, 9]


def test_exogenous_days_since_launch() -> None:
    """``days_since_launch`` is a pure date delta, NaN without a launch date."""
    launch = _ORIGIN - timedelta(days=100)
    with_launch = build_exogenous_columns(
        _HORIZON_DATES, ScenarioAssumptions(), set(), launch_date=launch
    )
    assert with_launch["days_since_launch"][0] == float((_HORIZON_DATES[0] - launch).days)
    without_launch = build_exogenous_columns(
        _HORIZON_DATES, ScenarioAssumptions(), set(), launch_date=None
    )
    assert all(math.isnan(value) for value in without_launch["days_since_launch"])


# --- assembly -----------------------------------------------------------------


def test_assemble_future_frame_shape_and_order() -> None:
    """The assembled matrix matches ``feature_columns`` in width and order."""
    columns = canonical_feature_columns()
    history_tail = [float(value) for value in range(HISTORY_TAIL_DAYS)]
    frame = assemble_future_frame(
        dates=_HORIZON_DATES,
        feature_columns=columns,
        history_tail=history_tail,
        assumptions=ScenarioAssumptions(),
        holiday_dates=set(),
        launch_date=None,
    )
    assert frame.feature_columns == columns
    assert frame.dates == _HORIZON_DATES
    assert len(frame.matrix) == _HORIZON
    assert all(len(row) == len(columns) for row in frame.matrix)


def test_assemble_future_frame_unknown_column_is_nan() -> None:
    """A requested column the builders do not produce becomes an all-NaN column."""
    columns = [*canonical_feature_columns(), "mystery_feature"]
    frame = assemble_future_frame(
        dates=_HORIZON_DATES,
        feature_columns=columns,
        history_tail=[float(v) for v in range(HISTORY_TAIL_DAYS)],
        assumptions=ScenarioAssumptions(),
        holiday_dates=set(),
        launch_date=None,
    )
    mystery_index = columns.index("mystery_feature")
    assert all(math.isnan(row[mystery_index]) for row in frame.matrix)
