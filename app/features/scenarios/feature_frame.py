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
from app.features.data_platform.models import Calendar, Product
from app.shared.feature_frames import (
    CALENDAR_COLUMNS,
    EXOGENOUS_COLUMNS,
    EXOGENOUS_LAGS,
    HISTORY_TAIL_DAYS,
    FeatureGroup,
    FutureFeatureFrame,
    V2FutureSidecar,
    build_calendar_columns,
    build_future_feature_rows_v2,
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
    feature_frame_version: int = 1,
    history_tail_dates: list[date] | None = None,
    feature_groups: dict[str, list[str]] | None = None,
) -> FutureFeatureFrame:
    """Build the future feature frame for one ``(store, product)`` series.

    Dispatches on ``feature_frame_version``:

    * V1 (default) — unchanged byte-for-byte. Reads calendar holidays for
      the horizon window and delegates to :func:`assemble_future_frame`.
    * V2 (PRP-35) — when the bundle was trained with the richer V2 contract.
      Reads holidays + product discontinue date, assembles a
      :class:`~app.shared.feature_frames.V2FutureSidecar` from the
      assumptions, and delegates to ``build_future_feature_rows_v2``.

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
        feature_frame_version: 1 (default) or 2. V1 bundles MAY omit this and
            the legacy path is preserved.
        history_tail_dates: V2 only — observed dates aligned with
            ``history_tail``. Required for V2 same-DOW lookups and exogenous
            sidecar lookups (omit → empty list / NaN cells).
        feature_groups: V2 only — bundle's ``feature_groups`` metadata. When
            provided, drives which V2 columns the future builder emits.

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

    if feature_frame_version == 2:
        frame = await _build_future_frame_v2(
            db,
            store_id=store_id,
            product_id=product_id,
            dates=dates,
            feature_columns=feature_columns,
            history_tail=history_tail,
            history_tail_dates=history_tail_dates or [],
            assumptions=assumptions,
            holiday_dates=holiday_dates,
            launch_date=launch_date,
            feature_groups=feature_groups,
        )
        logger.info(
            "scenarios.future_frame_built",
            store_id=store_id,
            product_id=product_id,
            horizon=horizon,
            n_features=len(feature_columns),
            n_calendar_holidays=len(holiday_dates),
            feature_frame_version=2,
        )
        return frame

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


async def _build_future_frame_v2(
    db: AsyncSession,
    *,
    store_id: int,
    product_id: int,
    dates: list[date],
    feature_columns: list[str],
    history_tail: list[float],
    history_tail_dates: list[date],
    assumptions: ScenarioAssumptions,
    holiday_dates: set[date],
    launch_date: date | None,
    feature_groups: dict[str, list[str]] | None,
) -> FutureFeatureFrame:
    """V2 future-frame assembly.

    Loads discontinue_date (a timeless attribute) inline — same-slice
    data_platform.models read, mirroring the ``Calendar`` import already used
    in the V1 path. Then builds a :class:`V2FutureSidecar` from the
    assumptions and delegates to ``build_future_feature_rows_v2``.

    Note: ``store_id`` is unused by V2 sidecar assembly (the future frame is
    driven by the assumptions); kept on the signature for parity with V1.
    """
    _ = store_id  # parameter parity with V1; not read by the V2 assembly
    horizon = len(dates)
    # Load discontinue_date inline (same-slice data_platform.models read, like
    # the V1 path's Calendar lookup).
    discontinue_date: date | None = await db.scalar(
        select(Product.discontinue_date).where(Product.id == product_id)
    )

    # Build per-day assumption-driven inputs.
    price = assumptions.price
    promotion = assumptions.promotion
    assumption_holidays: set[date] = (
        set(assumptions.holiday.dates) if assumptions.holiday is not None else set()
    )
    horizon_holidays = holiday_dates | assumption_holidays

    price_factor_per_day: list[float | None] = []
    promo_active_per_day: list[bool] = []
    promo_kinds_per_day: list[frozenset[str]] = []
    promo_discount_per_day: list[float] = []
    for point in dates:
        # price_factor — 1.0 baseline, (1 + change_pct) inside an assumption window
        if price is not None and _in_window(point, price.start_date, price.end_date):
            price_factor_per_day.append(1.0 + float(price.change_pct))
        else:
            price_factor_per_day.append(1.0)
        in_promo = promotion is not None and _in_window(
            point, promotion.start_date, promotion.end_date
        )
        promo_active_per_day.append(bool(in_promo))
        # Default V2 MVP: scenario PromotionAssumption has no kind / discount
        # plumbing yet — assume an empty kind set and 0.0 discount when active.
        # A future PRP can widen ScenarioAssumptions.promotion to carry these.
        promo_kinds_per_day.append(frozenset())
        promo_discount_per_day.append(0.0)

    sidecar = V2FutureSidecar(
        holiday_dates=frozenset(horizon_holidays),
        launch_date=launch_date,
        discontinue_date=discontinue_date,
        price_factor_per_day=tuple(price_factor_per_day),
        promo_active_per_day=tuple(promo_active_per_day),
        promo_kinds_per_day=tuple(promo_kinds_per_day),
        promo_discount_pct_per_day=tuple(promo_discount_per_day),
    )

    # Resolve groups from the bundle's persisted feature_groups dict; default
    # to all groups present in feature_columns (best-effort) when the bundle
    # didn't record one.
    if feature_groups:
        group_names = list(feature_groups.keys())
        valid: dict[str, FeatureGroup] = {g.value: g for g in FeatureGroup}
        resolved_groups: tuple[FeatureGroup, ...] = tuple(
            valid[name] for name in group_names if name in valid
        )
    else:
        resolved_groups = ()
    if not resolved_groups:
        # Fallback: infer from columns present in feature_columns. The future
        # builder will silently NaN-fill any column not produced (defensive,
        # mirrors V1 assemble_future_frame).
        from app.shared.feature_frames import canonical_feature_columns_v2

        # Try all groups; the builder will emit ALL columns the manifest
        # contains for those groups, which may differ from ``feature_columns``.
        # We let the caller's ``feature_columns`` be the authoritative output
        # column order — any extras are dropped below.
        try:
            _ = canonical_feature_columns_v2()
            resolved_groups = tuple(g for g in FeatureGroup)
        except ValueError:  # pragma: no cover — defensive
            resolved_groups = ()

    # Build the V2 future matrix (full groups), then project to the bundle's
    # ``feature_columns`` order — any column the bundle didn't expect is
    # dropped; any column the bundle expected but the V2 builder doesn't
    # produce is NaN-filled (defensive shape, mirrors V1).
    import math

    full_rows = build_future_feature_rows_v2(
        test_dates=dates,
        history_tail=history_tail,
        history_tail_dates=history_tail_dates,
        gap=0,
        baseline_price=1.0,  # price_factor is already the ratio; baseline is unitary
        sidecar=sidecar,
        groups=resolved_groups,
    )
    full_columns = list(_columns_for_resolved_groups(resolved_groups))
    full_index = {name: i for i, name in enumerate(full_columns)}
    matrix: list[list[float]] = []
    for j in range(horizon):
        row: list[float] = []
        for column in feature_columns:
            if column in full_index:
                row.append(full_rows[j][full_index[column]])
            else:
                row.append(math.nan)
        matrix.append(row)
    return FutureFeatureFrame(
        dates=list(dates),
        feature_columns=list(feature_columns),
        matrix=matrix,
    )


def _columns_for_resolved_groups(
    groups: tuple[FeatureGroup, ...],
) -> list[str]:
    """Resolve the full V2 column list for the supplied groups (best-effort)."""
    from app.shared.feature_frames import canonical_feature_columns_v2

    if not groups:
        return []
    return canonical_feature_columns_v2(groups=groups)
