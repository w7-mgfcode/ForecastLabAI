"""V2 leakage spec at the forecasting-slice layer — LOAD-BEARING (PRP-35).

Mirrors ``test_regression_features_leakage.py``: must NEVER be weakened to
make a feature pass (AGENTS.md § Safety).

The slice-layer counterpart to ``app/shared/feature_frames/tests/test_leakage_v2.py``.
Pins the time-safety invariants of the V2 historical row assembler as used
through the public ``build_historical_feature_rows_v2`` (driven by sequential
targets so leakage is mathematically detectable).
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from app.shared.feature_frames import (
    EXOGENOUS_LAGS_V2,
    ROLLING_WINDOWS_V2,
    TREND_WINDOWS_V2,
    FeatureGroup,
    V2HistoricalSidecar,
    build_historical_feature_rows_v2,
    canonical_feature_columns_v2,
)

_N = 200
_DATES = [date(2026, 1, 1) + timedelta(days=offset) for offset in range(_N)]
_QUANTITIES = [float(offset + 1) for offset in range(_N)]
_PRICES = [10.0] * _N
_BASELINE_PRICE = 10.0


def _build_rows(
    groups: tuple[FeatureGroup, ...] | None = None,
) -> tuple[list[str], list[list[float]]]:
    """Assemble the V2 feature matrix from sequential targets."""
    columns = canonical_feature_columns_v2(groups=groups)
    sidecar = V2HistoricalSidecar()
    rows = build_historical_feature_rows_v2(
        dates=_DATES,
        quantities=_QUANTITIES,
        prices=_PRICES,
        baseline_price=_BASELINE_PRICE,
        sidecar=sidecar,
        groups=groups,
    )
    return columns, rows


def test_v2_lag_columns_read_only_strictly_earlier_observations() -> None:
    """CRITICAL: every V2 lag cell reads a strictly-earlier observation, or NaN."""
    columns, rows = _build_rows()
    for lag in EXOGENOUS_LAGS_V2:
        col_index = columns.index(f"lag_{lag}")
        for i in range(_N):
            cell = rows[i][col_index]
            if i < lag:
                assert math.isnan(cell), (
                    f"row {i}: lag_{lag} has no source day yet — expected NaN, got {cell}"
                )
                continue
            expected = _QUANTITIES[i - lag]
            assert cell == expected, f"LEAKAGE at row {i}: lag_{lag}={cell} != expected={expected}"
            assert cell < _QUANTITIES[i], (
                f"LEAKAGE at row {i}: lag_{lag}={cell} >= current={_QUANTITIES[i]}"
            )


def test_v2_rolling_mean_strictly_less_than_current_target() -> None:
    """Rolling-mean values built from sequential prior rows are always < current."""
    columns, rows = _build_rows()
    for window in ROLLING_WINDOWS_V2:
        col_index = columns.index(f"rolling_mean_{window}")
        for i in range(_N):
            cell = rows[i][col_index]
            if i < window:
                assert math.isnan(cell), f"row {i}: rolling_mean_{window} should be NaN"
                continue
            expected = sum(_QUANTITIES[i - window : i]) / window
            assert cell == expected, (
                f"row {i}: rolling_mean_{window} expected {expected}, got {cell}"
            )
            assert cell < _QUANTITIES[i], (
                f"LEAKAGE at row {i}: rolling_mean_{window}={cell} >= current"
            )


def test_v2_trend_strictly_positive_with_sequential_targets() -> None:
    """For a monotonic-up sequential series the trend slope is ~1.0 everywhere computable."""
    columns, rows = _build_rows()
    for window in TREND_WINDOWS_V2:
        col_index = columns.index(f"trend_{window}")
        for i in range(window, _N):
            cell = rows[i][col_index]
            # Sequential 1..N with window points: slope == 1.0 (approximately)
            assert abs(cell - 1.0) < 1e-6, (
                f"row {i}: trend_{window} expected ≈1.0 (sequential), got {cell}"
            )


def test_v2_matrix_shape_matches_canonical_columns() -> None:
    columns, rows = _build_rows()
    assert len(rows) == _N
    assert all(len(row) == len(columns) for row in rows)


def test_v2_assemble_is_deterministic() -> None:
    """Identical inputs produce an identical V2 matrix — no hidden state."""
    _, a = _build_rows()
    _, b = _build_rows()
    assert a == b


def test_v2_disabled_groups_omit_their_columns_entirely() -> None:
    """A disabled group's columns do NOT appear (NOT NaN-fill placeholders)."""
    columns_narrow, rows_narrow = _build_rows(
        groups=(FeatureGroup.TARGET_HISTORY, FeatureGroup.CALENDAR)
    )
    # No rolling / trend columns should be in the manifest.
    assert "rolling_mean_7" not in columns_narrow
    assert "trend_30" not in columns_narrow
    # Width is exactly len(columns_narrow), not the full default.
    assert all(len(row) == len(columns_narrow) for row in rows_narrow)
