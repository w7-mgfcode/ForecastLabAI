"""Leakage spec for the historical regression feature builder — LOAD-BEARING.

This file IS the spec, mirroring ``app/features/featuresets/tests/test_leakage.py``
and ``app/shared/feature_frames/tests/test_leakage.py``: it must NEVER be
weakened to make a feature pass (AGENTS.md § Safety).

It pins the time-safety of :func:`_assemble_regression_rows` — the pure row
assembler behind ``ForecastingService._build_regression_features``. Sequential
target values (1, 2, 3, …) are used so any leakage is mathematically
detectable: with that input the lag-``k`` cell at row ``i`` MUST equal
``quantity[i-k]`` and MUST be strictly less than ``quantity[i]``. A lag cell
equal to or greater than the current row's target proves the builder read
current-or-future data.

The cutoff itself (``date <= end_date``) is enforced upstream by the SQL window
in ``_build_regression_features``; the row assembler only ever sees the
already-bounded ``dates`` list, and emits exactly one row per supplied date.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from app.features.forecasting.service import _assemble_regression_rows
from app.shared.feature_frames import EXOGENOUS_LAGS, canonical_feature_columns

_N = 60
_DATES = [date(2026, 1, 1) + timedelta(days=offset) for offset in range(_N)]
# Sequential targets 1.0 … 60.0 — quantity[i] == i + 1, so leakage is detectable.
_QUANTITIES = [float(offset + 1) for offset in range(_N)]
_PRICES = [10.0] * _N
_BASELINE_PRICE = 10.0


def _build_rows() -> list[list[float]]:
    """Assemble the regression feature matrix from the sequential fixture."""
    return _assemble_regression_rows(
        dates=_DATES,
        quantities=_QUANTITIES,
        prices=_PRICES,
        baseline_price=_BASELINE_PRICE,
        promo_dates=set(),
        holiday_dates=set(),
        launch_date=None,
    )


def test_lag_columns_read_only_strictly_earlier_observations() -> None:
    """CRITICAL: every lag cell reads a strictly-earlier observation, or NaN.

    With sequential targets the lag-``k`` cell at row ``i`` (for ``i >= k``)
    must equal ``quantity[i-k]`` exactly and be strictly below the current
    row's target ``quantity[i]``. Any cell ``>= quantity[i]`` is future
    leakage. Rows before the lag offset have no source day → ``NaN``.
    """
    columns = canonical_feature_columns()
    rows = _build_rows()

    for lag in EXOGENOUS_LAGS:
        col_index = columns.index(f"lag_{lag}")
        for i in range(_N):
            cell = rows[i][col_index]
            if i < lag:
                assert math.isnan(cell), (
                    f"row {i}: lag_{lag} has no source day yet — expected NaN, got {cell}"
                )
                continue
            expected = _QUANTITIES[i - lag]
            assert cell == expected, (
                f"LEAKAGE DETECTED at row {i}: lag_{lag}={cell} != expected={expected}. "
                "Lag feature is not correctly shifted."
            )
            assert cell < _QUANTITIES[i], (
                f"LEAKAGE DETECTED at row {i}: lag_{lag}={cell} >= current="
                f"{_QUANTITIES[i]}. Lag feature is using current or future data!"
            )


def test_assembled_matrix_shape_matches_canonical_columns() -> None:
    """One row per supplied date; every row matches the canonical column width.

    The assembler emits exactly ``len(dates)`` rows and never invents a row
    beyond the (cutoff-bounded) ``dates`` it was given.
    """
    columns = canonical_feature_columns()
    rows = _build_rows()
    assert len(rows) == _N
    assert all(len(row) == len(columns) for row in rows)


def test_assemble_regression_rows_is_deterministic() -> None:
    """Identical inputs produce an identical feature matrix — no hidden state."""
    assert _build_rows() == _build_rows()
