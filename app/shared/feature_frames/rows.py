"""Shared row-matrix assemblers for feature-aware forecasting (MLZOO-B.2).

This module joins :mod:`app.shared.feature_frames.contract` under the
cross-cutting ``app/shared/feature_frames`` package. ``contract.py`` owns the
pinned constants, the canonical column set, the leakage-safe *column* builders
and the :class:`~app.shared.feature_frames.contract.FeatureSafety` taxonomy;
this module owns the two *row-matrix* assemblers built on top of them:

* :func:`build_historical_feature_rows` — the historical (training) feature
  matrix. Promoted verbatim from ``ForecastingService._assemble_regression_rows``
  so the ``backtesting`` slice can reuse it without a forbidden cross-slice
  import (``backtesting -> forecasting`` is not allowed; ``-> app/shared`` is).
* :func:`build_future_feature_rows` — the test-window (future) feature matrix
  for a backtest fold. Leakage-safe by construction (see below).

LEAF-LEVEL: like ``contract.py`` this module may NEVER import from
``app/features/**``. Every function is pure — stdlib ``math`` / ``datetime``
plus the contract builders only. ``tests/test_contract.py`` enforces it with
an AST walk; ``tests/test_leakage.py`` pins the leakage invariants.

The leakage rule the future builder obeys (mirrors ``contract.py`` and the
load-bearing ``tests/test_leakage.py``):

    A future feature value for a test-window day may use ONLY information
    knowable at the forecast origin ``T`` — the observed history up to and
    including ``T``, the calendar (a pure function of the date), or an
    exogenous input recorded for the test window (price / promotion). It may
    NEVER read an observed *target* at a test-window day.
"""

from __future__ import annotations

import math
from datetime import date

from app.shared.feature_frames.contract import (
    CALENDAR_COLUMNS,
    EXOGENOUS_LAGS,
    build_calendar_columns,
    build_long_lag_columns,
    canonical_feature_columns,
)


def build_historical_feature_rows(
    *,
    dates: list[date],
    quantities: list[float],
    prices: list[float],
    baseline_price: float,
    promo_dates: set[date],
    holiday_dates: set[date],
    launch_date: date | None,
) -> list[list[float]]:
    """Assemble the historical regression feature matrix — pure, leakage-safe.

    Time-safe by construction: every lag column at row ``i`` reads only the
    observed target at ``i - lag`` (a strictly earlier day); calendar columns
    are pure functions of the date; ``price_factor`` / ``promo_active`` /
    ``is_holiday`` / ``days_since_launch`` read the same-day exogenous
    attributes. No row reads a future observation.

    Column order is :func:`canonical_feature_columns` exactly: the target
    lags, then the calendar columns, then ``price_factor``, ``promo_active``,
    ``is_holiday``, ``days_since_launch``.

    Promoted verbatim from ``ForecastingService._assemble_regression_rows``
    (which now delegates here) so the leakage invariant is unit-tested without
    a database (``app/features/forecasting/tests/test_regression_features_leakage.py``)
    and the ``backtesting`` slice can reuse it without a cross-slice import.

    Args:
        dates: Observed days in chronological order.
        quantities: Observed target values aligned with ``dates``.
        prices: Observed unit prices aligned with ``dates``.
        baseline_price: The typical price; ``price_factor`` is the ratio to it.
        promo_dates: Days a promotion covered.
        holiday_dates: Calendar holiday days.
        launch_date: The product's launch date, or ``None``.

    Returns:
        Row-major feature matrix ``[n_observations][n_features]``; ``NaN`` marks
        a lag whose source day precedes the series, and ``days_since_launch``
        when the product has no launch date.
    """
    calendar_columns = build_calendar_columns(dates)
    rows: list[list[float]] = []
    for index, day in enumerate(dates):
        row: list[float] = []
        # Target long-lag columns — read only strictly-earlier observations.
        for lag in EXOGENOUS_LAGS:
            row.append(quantities[index - lag] if index >= lag else math.nan)
        # Calendar columns — pure functions of the date (shared builder).
        for name in CALENDAR_COLUMNS:
            row.append(calendar_columns[name][index])
        # Exogenous columns — same-day observed attributes.
        row.append(prices[index] / baseline_price)
        row.append(1.0 if day in promo_dates else 0.0)
        row.append(1.0 if day in holiday_dates else 0.0)
        row.append(float((day - launch_date).days) if launch_date is not None else math.nan)
        rows.append(row)
    return rows


def build_future_feature_rows(
    *,
    test_dates: list[date],
    history_tail: list[float],
    gap: int,
    test_prices: list[float],
    baseline_price: float,
    test_promo_dates: set[date],
    test_holiday_dates: set[date],
    launch_date: date | None,
) -> list[list[float]]:
    """Assemble a backtest fold's test-window feature matrix — leakage-safe.

    This is the leakage-critical builder. A test-window day has no observed
    target, so the matrix MUST be rebuilt here rather than sliced from the
    historical matrix — a sliced historical row would read an adjacent
    test-day observed target as its ``lag_1`` cell (target leakage).

    Column population by class (matches the canonical column order exactly):

    * **Target lags** (``lag_*``) — from :func:`build_long_lag_columns` over
      ``history_tail``, which ends at the fold origin ``T``. A lag cell whose
      source day lies in the test window is ``NaN`` — structurally enforced,
      never a recursive prediction.
    * **Calendar columns** — pure functions of the test-window date.
    * **Exogenous columns** (``price_factor`` / ``promo_active``) — the
      *observed* recorded price / promotion for the test window. This reads
      no target ``y`` (not target leakage); it is exogenous foresight under
      the ``observed`` policy and assumes the future price/promo plan was
      known at ``T``.
    * ``is_holiday`` / ``days_since_launch`` — calendar / launch-date
      attributes, knowable at ``T``.

    Gap handling: with ``gap > 0`` the first test day is ``T + gap + 1`` but
    :func:`build_long_lag_columns` indexes its day ``m`` as ``T + m``. The lag
    columns are therefore built for ``gap + len(test_dates)`` days and the
    first ``gap`` rows dropped. With ``gap == 0`` the slice is a no-op.

    Args:
        test_dates: The fold's test-window days (chronological).
        history_tail: Observed targets ending at the fold origin ``T``
            (``history_tail[-1] == y[T]``); excludes the gap days.
        gap: Gap days between train end and test start (simulated latency).
        test_prices: Recorded unit prices aligned with ``test_dates``.
        baseline_price: The typical price; ``price_factor`` is the ratio to it.
        test_promo_dates: Test-window days a promotion covered.
        test_holiday_dates: Test-window calendar holiday days.
        launch_date: The product's launch date, or ``None``.

    Returns:
        Row-major feature matrix ``[len(test_dates)][n_features]`` in canonical
        column order; ``NaN`` marks a future-sourced lag cell and
        ``days_since_launch`` when the product has no launch date.

    Raises:
        ValueError: When ``gap`` is negative, ``test_prices`` does not align
            with ``test_dates``, or a canonical column cannot be sourced.
    """
    horizon = len(test_dates)
    if gap < 0:
        raise ValueError(f"build_future_feature_rows: gap must be >= 0, got {gap}")
    if len(test_prices) != horizon:
        raise ValueError(
            f"build_future_feature_rows: test_prices has {len(test_prices)} entries "
            f"but test_dates has {horizon} — they must align"
        )

    # Lags: build for gap + horizon days, then drop the gap lead-in so row j
    # corresponds to test day j. NaN-where-future is enforced by the builder.
    lag_columns = build_long_lag_columns(history_tail, gap + horizon)
    lag_columns = {name: values[gap:] for name, values in lag_columns.items()}
    calendar_columns = build_calendar_columns(test_dates)
    calendar_names = set(CALENDAR_COLUMNS)
    columns = canonical_feature_columns()

    rows: list[list[float]] = []
    for j, day in enumerate(test_dates):
        row: list[float] = []
        for column in columns:
            if column.startswith("lag_"):  # target lag — NaN where future
                row.append(lag_columns[column][j])
            elif column in calendar_names:  # pure function of the date
                row.append(calendar_columns[column][j])
            elif column == "price_factor":  # observed exogenous foresight
                row.append(test_prices[j] / baseline_price)
            elif column == "promo_active":  # observed exogenous foresight
                row.append(1.0 if day in test_promo_dates else 0.0)
            elif column == "is_holiday":  # calendar attribute
                row.append(1.0 if day in test_holiday_dates else 0.0)
            elif column == "days_since_launch":  # pure function of the date
                row.append(float((day - launch_date).days) if launch_date is not None else math.nan)
            else:  # loud failure — never a silent 0.0 / NaN fill
                raise ValueError(
                    f"build_future_feature_rows: cannot source future column {column!r}"
                )
        rows.append(row)
    return rows
