"""Leakage-safe future feature-frame generator (PRP-27 Phase A).

The scenario MVP (PRP-26) never builds a future feature matrix — it multiplies
a baseline forecast by a deterministic factor, so it is *immune* to leakage.
The Full Version introduces a model-driven path (``method="model_exogenous"``)
that re-forecasts demand through a feature-consuming regressor, and that needs
a **future feature frame**: the same feature columns the model was trained on,
produced for each horizon day ``T+1 … T+horizon``.

That is a new and dangerous surface — a horizon day ``D`` has *no observed
target* — so this module is governed by one rule:

    A future feature value for day ``D`` may only use information knowable at
    the forecast origin ``T`` (the last training day): the observed history
    up to and including ``T``, the calendar (a pure function of the date), or
    the scenario assumptions (the planner's *posited* future inputs).
    It may NEVER read an observed target at a horizon day.

``app/features/scenarios/tests/test_future_frame_leakage.py`` is the
load-bearing spec for the assumption-driven columns and the assembled frame; the
shared pure builders are spec'd by
``app/shared/feature_frames/tests/test_leakage.py``. Neither may be weakened
(AGENTS.md § Safety), mirroring ``app/features/featuresets/tests/test_leakage.py``.

DECISIONS LOCKED (PRP-27):
* #3 — no cross-slice ``service.py`` import. This module imports only the
  ``data_platform`` ORM (a sanctioned read-only ORM import), the shared
  feature-frame contract (``app/shared/feature_frames`` — a leaf-level
  package, the allowed ``app/features -> app/shared`` direction), and
  same-slice schema value-objects.
* #4 — long-lag + calendar + assumption-driven columns ONLY; no recursion.
  A target lag value for horizon day ``T+j`` is the observed ``y[T+j-k]``;
  when ``T+j-k > T`` (a future target) the cell is ``NaN`` — the model
  (``HistGradientBoostingRegressor``) handles ``NaN`` natively. No recursion
  ever fills those gaps in v1.
* #12 — ``MAX_COMPARE_SCENARIOS`` (the Phase-C comparison cap) lives here.

Feature-column contract: ``app/shared/feature_frames`` is the single source of
truth for the regression feature set, its column order, the pinned constants
(``EXOGENOUS_LAGS``, ``HISTORY_TAIL_DAYS``), and the leakage-safe pure builders
(``build_calendar_columns``, ``build_long_lag_columns``). This module imports —
and re-exports, for back-compat — those names; it owns only the
assumption-driven, DB-touching parts of the future frame.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.features.data_platform.models import Calendar
from app.shared.feature_frames import (
    CALENDAR_COLUMNS,
    EXOGENOUS_COLUMNS,
    EXOGENOUS_LAGS,
    HISTORY_TAIL_DAYS,
    FutureFeatureFrame,
    build_calendar_columns,
    build_long_lag_columns,
    canonical_feature_columns,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.features.scenarios.schemas import ScenarioAssumptions

logger = get_logger(__name__)

# Public surface of this module. The first block is the future-frame contract
# re-exported from ``app/shared/feature_frames`` so existing importers of this
# module keep resolving (back-compat); listing them in ``__all__`` marks the
# re-export as intentional for both ruff (F401) and pyright (reportUnusedImport).
__all__ = [
    "CALENDAR_COLUMNS",
    "EXOGENOUS_COLUMNS",
    "EXOGENOUS_LAGS",
    "HISTORY_TAIL_DAYS",
    "MAX_COMPARE_SCENARIOS",
    "FutureFeatureFrame",
    "assemble_future_frame",
    "build_calendar_columns",
    "build_exogenous_columns",
    "build_future_frame",
    "build_long_lag_columns",
    "canonical_feature_columns",
]

# Upper bound on the multi-scenario comparison (Phase C) so the chart stays
# legible; defined here as the scenarios slice's single modelling-constants
# home (PRP-27 DECISIONS LOCKED #12). NOT a feature-frame concept, so it stays
# in this slice rather than moving to ``app/shared/feature_frames``.
MAX_COMPARE_SCENARIOS: int = 5


def _in_window(point_date: date, start: date, end: date) -> bool:
    """True when ``point_date`` is inside the inclusive ``[start, end]`` window.

    A reversed window (``start`` after ``end``) is normalised rather than
    treated as empty — junk input must never raise (mirrors
    ``adjustments._in_window``).
    """
    lo, hi = (start, end) if start <= end else (end, start)
    return lo <= point_date <= hi


def build_exogenous_columns(
    dates: list[date],
    assumptions: ScenarioAssumptions,
    holiday_dates: set[date],
    launch_date: date | None,
) -> dict[str, list[float]]:
    """Build the current-day exogenous columns from the scenario assumptions.

    These columns are the *intended* what-if input — the planner is positing a
    future price / promotion / holiday — so reading them is not leakage. Each
    is knowable at origin ``T``:

    * ``price_factor`` — ``1.0`` (the typical price) outside any price window,
      ``1.0 + change_pct`` inside it.
    * ``promo_active`` — ``1.0`` when a promotion assumption covers the day.
    * ``is_holiday`` — ``1.0`` when the day is in the holiday assumption OR a
      ``calendar`` holiday (a calendar row is a timeless attribute).
    * ``days_since_launch`` — ``(date - launch_date).days``, a pure function of
      the date; ``NaN`` when the product has no launch date.

    Args:
        dates: The horizon days.
        assumptions: The scenario assumptions.
        holiday_dates: Calendar holiday dates inside the horizon.
        launch_date: The product's launch date, or ``None``.

    Returns:
        A mapping of every name in :data:`EXOGENOUS_COLUMNS` to its per-day
        values.
    """
    price = assumptions.price
    promotion = assumptions.promotion
    holiday = assumptions.holiday
    assumption_holidays: set[date] = set(holiday.dates) if holiday is not None else set()

    price_factor: list[float] = []
    promo_active: list[float] = []
    is_holiday: list[float] = []
    days_since_launch: list[float] = []

    for point_date in dates:
        if price is not None and _in_window(point_date, price.start_date, price.end_date):
            price_factor.append(1.0 + price.change_pct)
        else:
            price_factor.append(1.0)

        if promotion is not None and _in_window(
            point_date, promotion.start_date, promotion.end_date
        ):
            promo_active.append(1.0)
        else:
            promo_active.append(0.0)

        is_holiday.append(
            1.0 if point_date in assumption_holidays or point_date in holiday_dates else 0.0
        )

        if launch_date is not None:
            days_since_launch.append(float((point_date - launch_date).days))
        else:
            days_since_launch.append(math.nan)

    return {
        "price_factor": price_factor,
        "promo_active": promo_active,
        "is_holiday": is_holiday,
        "days_since_launch": days_since_launch,
    }


def assemble_future_frame(
    *,
    dates: list[date],
    feature_columns: list[str],
    history_tail: list[float],
    assumptions: ScenarioAssumptions,
    holiday_dates: set[date],
    launch_date: date | None,
) -> FutureFeatureFrame:
    """Assemble a :class:`FutureFeatureFrame` from already-resolved inputs.

    Pure (no DB, no I/O) so it is fully unit-testable; :func:`build_future_frame`
    is the thin async wrapper that resolves ``holiday_dates`` from the
    ``calendar`` table first.

    Any requested column not produced by the builders is filled with ``NaN``
    so the matrix always matches ``feature_columns`` in width and order.

    Args:
        dates: The horizon days ``T+1 … T+horizon``.
        feature_columns: The exact column order to emit.
        history_tail: Observed target values ending at the origin ``T``.
        assumptions: The scenario assumptions.
        holiday_dates: Calendar holiday dates inside the horizon.
        launch_date: The product's launch date, or ``None``.

    Returns:
        The assembled future feature frame.
    """
    horizon = len(dates)
    column_data: dict[str, list[float]] = {}
    column_data.update(build_long_lag_columns(history_tail, horizon))
    column_data.update(build_calendar_columns(dates))
    column_data.update(build_exogenous_columns(dates, assumptions, holiday_dates, launch_date))

    # Defensive: any column the trained bundle expects but this generator does
    # not produce becomes an all-NaN column (the estimator tolerates NaN).
    for column in feature_columns:
        if column not in column_data:
            column_data[column] = [math.nan] * horizon

    matrix: list[list[float]] = [
        [column_data[column][j] for column in feature_columns] for j in range(horizon)
    ]
    return FutureFeatureFrame(
        dates=list(dates),
        feature_columns=list(feature_columns),
        matrix=matrix,
    )


async def build_future_frame(
    db: AsyncSession,
    *,
    store_id: int,
    product_id: int,
    forecast_origin: date,
    horizon: int,
    feature_columns: list[str],
    history_tail: list[float],
    assumptions: ScenarioAssumptions,
    launch_date: date | None = None,
) -> FutureFeatureFrame:
    """Build the future feature frame for one ``(store, product)`` series.

    The only database read is the ``calendar`` holiday lookup for the horizon
    window — a ``calendar`` row is a timeless attribute, so reading it is not
    leakage. Everything else is derived from ``history_tail`` (observed,
    ``<= T``), the dates, or the assumptions.

    Args:
        db: Async database session (used only for the calendar lookup).
        store_id: Store the baseline model targets (logged).
        product_id: Product the baseline model targets (logged).
        forecast_origin: The origin ``T`` — the last training day. The horizon
            runs ``T+1 … T+horizon``.
        horizon: Number of horizon days (``>= 1``).
        feature_columns: The trained bundle's feature-column order.
        history_tail: Observed target values ending at ``T``.
        assumptions: The scenario assumptions.
        launch_date: The product's launch date, or ``None``.

    Returns:
        The assembled future feature frame.

    Raises:
        ValueError: When ``horizon`` is below 1.
    """
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")

    dates = [forecast_origin + timedelta(days=offset) for offset in range(1, horizon + 1)]

    result = await db.execute(
        select(Calendar.date).where(
            Calendar.date >= dates[0],
            Calendar.date <= dates[-1],
            Calendar.is_holiday.is_(True),
        )
    )
    holiday_dates: set[date] = set(result.scalars().all())

    frame = assemble_future_frame(
        dates=dates,
        feature_columns=feature_columns,
        history_tail=history_tail,
        assumptions=assumptions,
        holiday_dates=holiday_dates,
        launch_date=launch_date,
    )
    logger.info(
        "scenarios.future_frame_built",
        store_id=store_id,
        product_id=product_id,
        horizon=horizon,
        n_features=len(feature_columns),
        n_calendar_holidays=len(holiday_dates),
    )
    return frame
