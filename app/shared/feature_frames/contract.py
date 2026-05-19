"""Shared feature-frame contract for feature-aware forecasting (MLZOO-A).

This module is the **single source of truth** for the regression feature-frame
contract: the pinned modelling constants, the canonical feature-column set and
its order, the :class:`FutureFeatureFrame` carrier, the leakage-safe pure
column builders, and the :class:`FeatureSafety` leakage taxonomy.

Before MLZOO-A the contract was duplicated across two vertical slices — the
``forecasting`` slice (the historical training frame) and the ``scenarios``
slice (the future prediction frame) — because a cross-slice import is forbidden
(AGENTS.md § Architecture). A cross-cutting package under ``app/shared/`` is the
sanctioned home: both slices now *import* this one definition rather than
re-typing it, so a silent column-order mismatch is structurally impossible.

LEAF-LEVEL: ``app/shared/**`` may NEVER import from ``app/features/**``. Every
builder here is pure (stdlib ``math`` / ``datetime`` / ``dataclasses`` only) so
that invariant holds; ``tests/test_contract.py`` enforces it with an AST walk.

The leakage rule the future-frame builders obey (mirrors PRP-27 and the
load-bearing ``tests/test_leakage.py`` alongside this module):

    A future feature value for horizon day ``D`` may use ONLY information
    knowable at the forecast origin ``T``: the observed history up to and
    including ``T``, or the calendar (a pure function of the date). It may
    NEVER read an observed target at a horizon day.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

# ── PINNED modelling constants (PRP-27 DECISIONS LOCKED #10/#11) ──
# Lag offsets (days) for the target long-lag columns: daily, weekly,
# fortnightly, and a four-week lag covering the dominant retail seasonality.
EXOGENOUS_LAGS: tuple[int, ...] = (1, 7, 14, 28)
# Observed-target tail (days, ending at the forecast origin T) fed to the
# generator — 90 comfortably exceeds the largest lag offset (28).
HISTORY_TAIL_DAYS: int = 90

# Fixed calendar columns — each a pure function of the date, never a leak.
CALENDAR_COLUMNS: tuple[str, ...] = (
    "dow_sin",
    "dow_cos",
    "month_sin",
    "month_cos",
    "is_weekend",
    "is_month_end",
)
# Fixed current-day exogenous columns — driven by the scenario assumptions
# (the planner's posited future inputs) and by timeless attributes (the
# calendar, the product launch date). Every value is knowable at origin T.
EXOGENOUS_COLUMNS: tuple[str, ...] = (
    "price_factor",
    "promo_active",
    "is_holiday",
    "days_since_launch",
)


@dataclass
class FutureFeatureFrame:
    """A horizon-length feature matrix for one ``(store, product)`` series.

    Attributes:
        dates: The horizon days ``T+1 … T+horizon`` (chronological).
        feature_columns: Column order — matches the trained bundle exactly.
        matrix: Row-major ``[horizon][n_features]``; ``NaN`` is allowed and
            expected (a long-lag cell whose source target lies in the future,
            or ``days_since_launch`` when the product has no launch date).
    """

    dates: list[date]
    feature_columns: list[str]
    matrix: list[list[float]]


def canonical_feature_columns(lags: tuple[int, ...] = EXOGENOUS_LAGS) -> list[str]:
    """Return the fixed, ordered regression feature-column list.

    This is the single source of truth for the regression feature set. The
    Phase B training path persists exactly this list in the model bundle's
    metadata; the future frame reproduces it column-for-column. The column
    set is deliberately *fixed* (not horizon-dependent): for a long horizon
    some target-lag columns are mostly ``NaN``, which the NaN-tolerant
    estimator handles — far safer than a horizon-varying column set.

    Args:
        lags: Target long-lag offsets (defaults to the pinned ``EXOGENOUS_LAGS``).

    Returns:
        Ordered column names: target lags, then calendar, then exogenous.
    """
    target_lags = [f"lag_{k}" for k in lags]
    return [*target_lags, *CALENDAR_COLUMNS, *EXOGENOUS_COLUMNS]


def _is_month_end(point_date: date) -> bool:
    """True when ``point_date`` is the last day of its month."""
    return (point_date + timedelta(days=1)).month != point_date.month


def build_calendar_columns(dates: list[date]) -> dict[str, list[float]]:
    """Build the calendar feature columns — a pure function of each date.

    Calendar features carry zero leakage risk: they read only the date
    itself, never the target series. Day-of-week and month use cyclical
    (sin/cos) encoding so the estimator sees their periodic structure.

    Args:
        dates: The horizon days.

    Returns:
        A mapping of every name in :data:`CALENDAR_COLUMNS` to its per-day
        values.
    """
    columns: dict[str, list[float]] = {name: [] for name in CALENDAR_COLUMNS}
    for point_date in dates:
        dow = point_date.weekday()  # 0 = Monday … 6 = Sunday
        month = point_date.month
        columns["dow_sin"].append(math.sin(2.0 * math.pi * dow / 7.0))
        columns["dow_cos"].append(math.cos(2.0 * math.pi * dow / 7.0))
        columns["month_sin"].append(math.sin(2.0 * math.pi * month / 12.0))
        columns["month_cos"].append(math.cos(2.0 * math.pi * month / 12.0))
        columns["is_weekend"].append(1.0 if dow >= 5 else 0.0)
        columns["is_month_end"].append(1.0 if _is_month_end(point_date) else 0.0)
    return columns


def build_long_lag_columns(
    history_tail: list[float],
    horizon: int,
    lags: tuple[int, ...] = EXOGENOUS_LAGS,
) -> dict[str, list[float]]:
    """Build the target long-lag columns — the leakage-critical helper.

    ``history_tail`` is the observed target series ending at the forecast
    origin ``T``: ``history_tail[-1] == y[T]``, ``history_tail[-2] == y[T-1]``,
    and so on. The lag-``k`` column at horizon day ``T+j`` (``j`` in
    ``1 … horizon``) is the observed target ``y[T+j-k]``.

    SAFETY (PRP-27 DECISIONS LOCKED #4): the source index into
    ``history_tail`` is ``idx = (j - 1) - k``. The cell is populated **only
    when ``idx < 0``** — i.e. the source day ``T+j-k`` lies at or before the
    origin ``T`` and therefore inside ``history_tail``. When ``idx >= 0`` the
    source day is a *future* horizon day with no observed target, so the cell
    is ``NaN`` — never a recursive prediction, never a fabricated value. This
    function structurally **cannot** read a future target: its only data
    input is ``history_tail`` (entirely ``<= T``).

    Args:
        history_tail: Observed target values ending at the origin ``T``.
        horizon: Number of horizon days.
        lags: Lag offsets (defaults to the pinned ``EXOGENOUS_LAGS``).

    Returns:
        A mapping ``"lag_{k}" -> [horizon values]``; out-of-range cells are
        ``NaN``.
    """
    tail_len = len(history_tail)
    columns: dict[str, list[float]] = {}
    for lag in lags:
        column: list[float] = []
        for j in range(1, horizon + 1):
            # Negative index from the end of history_tail. idx < 0 means the
            # source day T+j-k is at/before the origin T — safe to read.
            idx = (j - 1) - lag
            if idx < 0 and -tail_len <= idx:
                column.append(float(history_tail[idx]))
            else:
                column.append(math.nan)
        columns[f"lag_{lag}"] = column
    return columns


class FeatureSafety(Enum):
    """Leakage classification of a feature column in a FUTURE prediction frame.

    Every canonical feature column falls into exactly one class. The
    classification governs how a future-frame builder may populate the column
    for a horizon day ``D`` (which has no observed target):

    * ``SAFE`` — a pure function of the date (calendar features); reading it
      can never leak a future target.
    * ``CONDITIONALLY_SAFE`` — a target long-lag; safe only when its source
      day lies at or before the forecast origin ``T``, otherwise the cell is
      ``NaN``.
    * ``UNSAFE_UNLESS_SUPPLIED`` — a future price / promotion input; knowable
      at ``T`` ONLY because the caller posits it (a scenario assumption). It
      is never inferred from observed data.
    """

    SAFE = "safe"
    CONDITIONALLY_SAFE = "conditionally_safe"
    UNSAFE_UNLESS_SUPPLIED = "unsafe_unless_supplied"


# The executable taxonomy: every canonical column → its FeatureSafety class.
# ``is_holiday`` and ``days_since_launch`` are SAFE — a calendar holiday row is
# a timeless attribute and ``days_since_launch`` is a pure function of the date
# once the launch date is known. ``price_factor`` / ``promo_active`` are
# UNSAFE_UNLESS_SUPPLIED — only a posited scenario assumption makes them
# knowable for a future day.
FEATURE_CLASS: dict[str, FeatureSafety] = {
    **{f"lag_{k}": FeatureSafety.CONDITIONALLY_SAFE for k in EXOGENOUS_LAGS},
    "dow_sin": FeatureSafety.SAFE,
    "dow_cos": FeatureSafety.SAFE,
    "month_sin": FeatureSafety.SAFE,
    "month_cos": FeatureSafety.SAFE,
    "is_weekend": FeatureSafety.SAFE,
    "is_month_end": FeatureSafety.SAFE,
    "price_factor": FeatureSafety.UNSAFE_UNLESS_SUPPLIED,
    "promo_active": FeatureSafety.UNSAFE_UNLESS_SUPPLIED,
    "is_holiday": FeatureSafety.SAFE,
    "days_since_launch": FeatureSafety.SAFE,
}


def feature_safety(column: str) -> FeatureSafety:
    """Return the leakage classification of a feature column.

    Args:
        column: A feature-column name (e.g. ``"lag_7"``, ``"dow_sin"``).

    Returns:
        The column's :class:`FeatureSafety` class. A ``lag_*`` column with a
        custom offset not literally in :data:`FEATURE_CLASS` resolves to
        ``CONDITIONALLY_SAFE`` — every target lag is conditionally safe.

    Raises:
        KeyError: When ``column`` is neither a known column nor a ``lag_*``
            column — callers must classify every column they emit.
    """
    if column in FEATURE_CLASS:
        return FEATURE_CLASS[column]
    if column.startswith("lag_"):
        return FeatureSafety.CONDITIONALLY_SAFE
    raise KeyError(f"Unclassified feature column: {column!r}")
