"""V2 historical + future row assemblers (PRP-35).

Sibling of ``rows.py`` (V1). The two row assemblers below build the V2 feature
matrix in canonical column order (see :func:`canonical_feature_columns_v2`),
emitting only the columns whose owning :class:`FeatureGroup` is enabled.

LEAF-LEVEL: like ``rows.py`` and ``contract_v2.py`` this module imports nothing
from ``app/features/**``. Every helper is pure (stdlib + numpy for ``polyfit``
on the trend columns). ``tests/test_contract.py`` and ``test_contract_v2.py``
extend the AST-walk invariant over this module too.

Leakage rule the V2 builders obey (mirrors V1):

    A future feature value for horizon day ``D`` may use ONLY information
    knowable at the forecast origin ``T``: the observed history up to and
    including ``T``, the calendar (a pure function of the date), launch /
    discontinue dates, or scenario-assumption inputs posited by the caller.
    It NEVER reads an observed target — or any sidecar value — at a
    horizon day ``D``.

Group-gated emission: the column manifest is derived from the ``groups``
parameter. A disabled group's columns do NOT appear (silent omission, NOT a
NaN-fill placeholder). When a group IS enabled but a specific day lacks
source data, that cell is NaN.

LOUD failure (ValueError) — programmer / contract errors only:

* ``groups`` is empty (zero-column matrix is a misuse).
* ``groups`` contains an unknown :class:`FeatureGroup` name.
* A sidecar per-day array's length disagrees with ``dates`` / ``test_dates``
  for an enabled group whose columns read that array.

NEVER raise ValueError because a single day's source is missing within an
enabled group — that's the NaN case.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np

from app.shared.feature_frames.contract import (
    CALENDAR_COLUMNS,
    build_calendar_columns,
    build_long_lag_columns,
)
from app.shared.feature_frames.contract_v2 import (
    EXOGENOUS_LAGS_V2,
    INVENTORY_AVAILABILITY_WINDOW_V2,
    LIFECYCLE_MATURE_THRESHOLD_DAYS,
    LIFECYCLE_NEW_THRESHOLD_DAYS,
    MACRO_SIGNAL_NAMES_V2,
    REPLENISHMENT_QTY_WINDOW_V2,
    REPLENISHMENT_WINDOW_V2,
    RETURNS_RATE_WINDOW_V2,
    RETURNS_WINDOWS_V2,
    ROLLING_WINDOWS_V2,
    SAME_DOW_MEAN_LOOKBACKS_V2,
    STOCKOUT_WINDOWS_V2,
    TREND_WINDOWS_V2,
    WEATHER_SIGNAL_NAMES_V2,
    FeatureGroup,
    canonical_feature_columns_v2,
    resolve_v2_groups,
)
from app.shared.feature_frames.sidecar import V2FutureSidecar, V2HistoricalSidecar

# ── Pure column helpers (historical) ────────────────────────────────────────


def _rolling_mean_column(quantities: list[float], window: int) -> list[float]:
    """Leakage-safe rolling mean: row ``i`` reads ``quantities[i-window..i-1]`` only.

    First ``window`` rows are NaN. NEVER includes ``quantities[i]``.
    """
    out: list[float] = []
    for i in range(len(quantities)):
        if i < window:
            out.append(math.nan)
        else:
            out.append(sum(quantities[i - window : i]) / window)
    return out


def _rolling_median_column(quantities: list[float], window: int) -> list[float]:
    out: list[float] = []
    for i in range(len(quantities)):
        if i < window:
            out.append(math.nan)
            continue
        window_slice = sorted(quantities[i - window : i])
        mid = window // 2
        if window % 2 == 1:
            out.append(window_slice[mid])
        else:
            out.append((window_slice[mid - 1] + window_slice[mid]) / 2.0)
    return out


def _rolling_std_column(quantities: list[float], window: int) -> list[float]:
    """Sample standard deviation over the trailing ``window`` strictly-earlier rows."""
    out: list[float] = []
    for i in range(len(quantities)):
        if i < window:
            out.append(math.nan)
            continue
        slice_ = quantities[i - window : i]
        mean = sum(slice_) / window
        variance = sum((v - mean) ** 2 for v in slice_) / (window - 1) if window > 1 else 0.0
        out.append(math.sqrt(variance))
    return out


def _same_dow_mean_column(dates: list[date], quantities: list[float], n_back: int) -> list[float]:
    """Mean of the ``n_back`` most recent EARLIER observations with the same weekday.

    NaN when fewer than ``n_back`` same-weekday earlier observations exist.
    """
    out: list[float] = []
    for i, day in enumerate(dates):
        same_dow = [quantities[j] for j in range(i) if dates[j].weekday() == day.weekday()]
        if len(same_dow) >= n_back:
            out.append(sum(same_dow[-n_back:]) / n_back)
        else:
            out.append(math.nan)
    return out


def _trend_column(quantities: list[float], window: int) -> list[float]:
    """Linear slope (numpy.polyfit, deg=1) over the trailing ``window`` rows.

    NaN when fewer than ``window`` earlier rows exist.
    """
    out: list[float] = []
    for i in range(len(quantities)):
        if i < window:
            out.append(math.nan)
            continue
        y = np.asarray(quantities[i - window : i], dtype=np.float64)
        x = np.arange(window, dtype=np.float64)
        # polyfit returns [slope, intercept] for deg=1
        slope = float(np.polyfit(x, y, 1)[0])
        out.append(slope)
    return out


def _ratio_two_means_column(
    quantities: list[float], num_window: int, den_window: int
) -> list[float]:
    """Ratio of two trailing-window means (both strictly earlier than row ``i``).

    NaN when either window has insufficient history. ``den == 0`` → NaN.
    """
    out: list[float] = []
    for i in range(len(quantities)):
        if i < num_window or i < den_window:
            out.append(math.nan)
            continue
        num = sum(quantities[i - num_window : i]) / num_window
        den = sum(quantities[i - den_window : i]) / den_window
        out.append(num / den if den != 0.0 else math.nan)
    return out


def _ratio_window_vs_prev_window_column(quantities: list[float], window: int) -> list[float]:
    """Ratio of trailing window mean to the window before it.

    For row ``i``: num = mean(quantities[i-window..i-1]),
    den = mean(quantities[i-2*window..i-window-1]). NaN until 2*window
    earlier rows exist. ``den == 0`` → NaN.
    """
    out: list[float] = []
    for i in range(len(quantities)):
        if i < 2 * window:
            out.append(math.nan)
            continue
        num = sum(quantities[i - window : i]) / window
        den = sum(quantities[i - 2 * window : i - window]) / window
        out.append(num / den if den != 0.0 else math.nan)
    return out


def _v2_calendar_columns(dates: list[date]) -> dict[str, list[float]]:
    """V1 calendar columns + V2 extensions (week_of_year, day_of_month).

    Pure function of each date — zero leakage risk.
    """
    base = build_calendar_columns(dates)
    week_sin: list[float] = []
    week_cos: list[float] = []
    dom_sin: list[float] = []
    dom_cos: list[float] = []
    for day in dates:
        # ISO week number — 1..53
        iso_week = day.isocalendar().week
        week_sin.append(math.sin(2.0 * math.pi * iso_week / 53.0))
        week_cos.append(math.cos(2.0 * math.pi * iso_week / 53.0))
        # Day of month — 1..31 (use 31 for cyclical encoding)
        dom_sin.append(math.sin(2.0 * math.pi * day.day / 31.0))
        dom_cos.append(math.cos(2.0 * math.pi * day.day / 31.0))
    return {
        **base,
        "week_of_year_sin": week_sin,
        "week_of_year_cos": week_cos,
        "day_of_month_sin": dom_sin,
        "day_of_month_cos": dom_cos,
    }


def _lifecycle_columns(
    dates: list[date],
    launch_date: date | None,
    discontinue_date: date | None,
) -> dict[str, list[float]]:
    """V1 days_since_launch + V2 lifecycle flags. Pure function of dates + attrs."""
    days_since: list[float] = []
    is_new: list[float] = []
    is_mature: list[float] = []
    is_disc: list[float] = []
    days_until_disc: list[float] = []
    for day in dates:
        if launch_date is None:
            days_since.append(math.nan)
            is_new.append(math.nan)
            is_mature.append(math.nan)
        else:
            since = (day - launch_date).days
            days_since.append(float(since))
            is_new.append(1.0 if 0 <= since < LIFECYCLE_NEW_THRESHOLD_DAYS else 0.0)
            is_mature.append(1.0 if since >= LIFECYCLE_MATURE_THRESHOLD_DAYS else 0.0)
        if discontinue_date is None:
            is_disc.append(0.0)
            days_until_disc.append(math.nan)
        else:
            is_disc.append(1.0 if day >= discontinue_date else 0.0)
            days_until_disc.append(float((discontinue_date - day).days))
    return {
        "days_since_launch": days_since,
        "is_new_product": is_new,
        "is_mature_product": is_mature,
        "is_discontinued": is_disc,
        "days_until_discontinue": days_until_disc,
    }


def _stockout_columns(
    is_stockout_per_day: tuple[bool, ...],
    on_hand_qty: tuple[float | None, ...],
    n_rows: int,
) -> dict[str, list[float]]:
    """Inventory-derived columns; every cell reads only strictly-earlier days.

    Caller must pass per-day arrays of length ``n_rows`` (validated by caller).
    """
    stockout_flags = [1.0 if flag else 0.0 for flag in is_stockout_per_day]
    is_stockout_lag1: list[float] = []
    for i in range(n_rows):
        is_stockout_lag1.append(stockout_flags[i - 1] if i >= 1 else math.nan)
    stockout_per_window: dict[int, list[float]] = {}
    for window in STOCKOUT_WINDOWS_V2:
        col: list[float] = []
        for i in range(n_rows):
            if i < window:
                col.append(math.nan)
            else:
                col.append(float(sum(stockout_flags[i - window : i])))
        stockout_per_window[window] = col
    # inventory_available_ratio_28: trailing-28-day mean(on_hand_qty / max_on_hand_in_window)
    avail_ratio: list[float] = []
    window = INVENTORY_AVAILABILITY_WINDOW_V2
    for i in range(n_rows):
        if i < window:
            avail_ratio.append(math.nan)
            continue
        slice_ = on_hand_qty[i - window : i]
        observed = [v for v in slice_ if v is not None]
        if not observed:
            avail_ratio.append(math.nan)
            continue
        max_on_hand = max(observed)
        if max_on_hand <= 0.0:
            avail_ratio.append(math.nan)
            continue
        mean_observed = sum(observed) / len(observed)
        avail_ratio.append(mean_observed / max_on_hand)
    return {
        "is_stockout_lag1": is_stockout_lag1,
        "stockout_days_7": stockout_per_window[7],
        "stockout_days_28": stockout_per_window[28],
        "inventory_available_ratio_28": avail_ratio,
    }


def _replenishment_columns(
    dates: list[date],
    event_dates: tuple[date, ...],
    event_qty: tuple[int, ...],
) -> dict[str, list[float]]:
    """Replenishment cadence columns; every cell reads only events strictly before the row."""
    n_rows = len(dates)
    days_since: list[float] = []
    count_14: list[float] = []
    qty_28: list[float] = []
    for i, day in enumerate(dates):
        # Strictly-earlier events: event date < day
        prior = [(d, q) for d, q in zip(event_dates, event_qty, strict=True) if d < day]
        if prior:
            last_event_date = max(d for d, _ in prior)
            days_since.append(float((day - last_event_date).days))
        else:
            days_since.append(math.nan)
        # Counts / qty inside the [day - W, day) windows
        win14_start = day.toordinal() - REPLENISHMENT_WINDOW_V2
        win28_start = day.toordinal() - REPLENISHMENT_QTY_WINDOW_V2
        count_14.append(float(sum(1 for d, _ in prior if d.toordinal() >= win14_start)))
        qty_28.append(float(sum(q for d, q in prior if d.toordinal() >= win28_start)))
        # Suppress unused-loop-variable warning
        _ = i
    if n_rows == 0:  # defensive; never hit in practice
        return {
            "days_since_last_replenishment": [],
            "replenishment_count_14": [],
            "replenishment_qty_28": [],
        }
    return {
        "days_since_last_replenishment": days_since,
        "replenishment_count_14": count_14,
        "replenishment_qty_28": qty_28,
    }


def _returns_columns(
    quantities: list[float],
    returns_qty_per_day: tuple[int, ...],
    n_rows: int,
) -> dict[str, list[float]]:
    """Returns-window columns; every cell reads only strictly-earlier days."""
    returns_floats = [float(v) for v in returns_qty_per_day]
    out: dict[str, list[float]] = {}
    for window in RETURNS_WINDOWS_V2:
        col: list[float] = []
        for i in range(n_rows):
            if i < window:
                col.append(math.nan)
            else:
                col.append(float(sum(returns_floats[i - window : i])))
        out[f"returns_qty_{window}"] = col
    # returns_rate_28: sum(returns) / max(1, sum(sales)) over the trailing window
    rate: list[float] = []
    window = RETURNS_RATE_WINDOW_V2
    for i in range(n_rows):
        if i < window:
            rate.append(math.nan)
            continue
        ret_sum = sum(returns_floats[i - window : i])
        sales_sum = sum(quantities[i - window : i])
        rate.append(ret_sum / sales_sum if sales_sum > 0.0 else 0.0)
    out["returns_rate_28"] = rate
    return out


def _price_promo_columns_historical(
    *,
    dates: list[date],
    prices: list[float],
    baseline_price: float,
    promo_dates: frozenset[date],
    promo_kinds_per_day: tuple[frozenset[str], ...],
    promo_discount_pct_per_day: tuple[float, ...],
    n_rows: int,
) -> dict[str, list[float]]:
    """V2 PRICE_PROMO columns for the historical builder.

    ``promo_kinds_per_day`` / ``promo_discount_pct_per_day`` MAY be empty
    tuples (then ``promo_discount_pct`` and the kind flags are all 0.0); when
    non-empty they MUST have length ``n_rows`` (caller validates).
    """
    price_factor = [prices[i] / baseline_price for i in range(n_rows)]
    promo_active = [1.0 if day in promo_dates else 0.0 for day in dates]
    if promo_discount_pct_per_day:
        promo_discount = [float(v) for v in promo_discount_pct_per_day]
    else:
        promo_discount = [0.0] * n_rows
    if promo_kinds_per_day:
        markdown = [1.0 if "markdown" in promo_kinds_per_day[i] else 0.0 for i in range(n_rows)]
        bundle = [1.0 if "bundle" in promo_kinds_per_day[i] else 0.0 for i in range(n_rows)]
    else:
        markdown = [0.0] * n_rows
        bundle = [0.0] * n_rows
    return {
        "price_factor": price_factor,
        "promo_active": promo_active,
        "promo_discount_pct": promo_discount,
        "promo_kind_markdown_active": markdown,
        "promo_kind_bundle_active": bundle,
    }


def _exogenous_columns(
    dates: list[date],
    signal_names: tuple[str, ...],
    per_day: dict[date, dict[str, float]],
) -> dict[str, list[float]]:
    """Per-day exogenous-signal columns; NaN where the date has no entry."""
    out: dict[str, list[float]] = {}
    for name in signal_names:
        col: list[float] = []
        for day in dates:
            entry = per_day.get(day)
            if entry is None or name not in entry:
                col.append(math.nan)
            else:
                col.append(float(entry[name]))
        out[f"exo_{name}"] = col
    return out


# ── Public builders ─────────────────────────────────────────────────────────


def _validate_per_day_length(
    *,
    name: str,
    actual: int,
    expected: int,
    group: FeatureGroup,
) -> None:
    """Raise ValueError when a sidecar per-day array's length disagrees with ``dates``."""
    if actual != expected:
        raise ValueError(
            f"v2 builder: sidecar field {name!r} has length {actual}, but the "
            f"{group.value} group requires length {expected} (must align with `dates`)."
        )


def build_historical_feature_rows_v2(
    *,
    dates: list[date],
    quantities: list[float],
    prices: list[float],
    baseline_price: float,
    sidecar: V2HistoricalSidecar,
    groups: tuple[FeatureGroup, ...] | None = None,
) -> list[list[float]]:
    """Assemble the V2 historical regression feature matrix — pure, leakage-safe.

    Every row reads only data strictly earlier than that row (target lags,
    rolling, trend, stockout, replenishment, returns) or same-day attributes
    that carry no leakage (calendar, lifecycle, observed price / promotion /
    exogenous signal). NO column reads a future observation.

    Group-gated emission: ``groups`` decides which columns appear. ``None``
    resolves to :data:`DEFAULT_V2_GROUPS`. The output column order follows
    :func:`canonical_feature_columns_v2`.

    Args:
        dates: Observed days in chronological order.
        quantities: Observed target values aligned with ``dates``.
        prices: Observed unit prices aligned with ``dates``.
        baseline_price: Typical price; ``price_factor`` is the ratio to it.
        sidecar: All V2 inputs beyond the V1 surface.
        groups: Enabled :class:`FeatureGroup` subset.

    Returns:
        Row-major matrix ``[n_observations][n_features]``; NaN where a cell's
        source data is missing for that day.

    Raises:
        ValueError: When ``dates`` / ``quantities`` / ``prices`` lengths
            disagree, when ``baseline_price`` is not finite and > 0, when
            ``groups`` is empty or names an unknown group, or when an enabled
            group's sidecar per-day array length disagrees with ``len(dates)``.
    """
    n_rows = len(dates)
    if len(quantities) != n_rows or len(prices) != n_rows:
        raise ValueError(
            f"build_historical_feature_rows_v2: dates ({n_rows}), quantities "
            f"({len(quantities)}), prices ({len(prices)}) must all share length."
        )
    if not math.isfinite(baseline_price) or baseline_price <= 0.0:
        raise ValueError(
            f"build_historical_feature_rows_v2: baseline_price must be finite and > 0, got {baseline_price!r}"
        )
    resolved_groups = resolve_v2_groups(groups)
    resolved_set = set(resolved_groups)
    columns = canonical_feature_columns_v2(groups)
    column_data: dict[str, list[float]] = {}

    # TARGET_HISTORY
    if FeatureGroup.TARGET_HISTORY in resolved_set:
        for lag in EXOGENOUS_LAGS_V2:
            col: list[float] = []
            for i in range(n_rows):
                col.append(quantities[i - lag] if i >= lag else math.nan)
            column_data[f"lag_{lag}"] = col
        for n_back in SAME_DOW_MEAN_LOOKBACKS_V2:
            column_data[f"same_dow_mean_{n_back}"] = _same_dow_mean_column(
                dates, quantities, n_back
            )

    # CALENDAR
    if FeatureGroup.CALENDAR in resolved_set:
        cal = _v2_calendar_columns(dates)
        column_data.update(cal)
        column_data["is_holiday"] = [1.0 if day in sidecar.holiday_dates else 0.0 for day in dates]

    # ROLLING
    if FeatureGroup.ROLLING in resolved_set:
        for window in ROLLING_WINDOWS_V2:
            column_data[f"rolling_mean_{window}"] = _rolling_mean_column(quantities, window)
        column_data["rolling_median_28"] = _rolling_median_column(quantities, 28)
        column_data["rolling_std_28"] = _rolling_std_column(quantities, 28)

    # TREND
    if FeatureGroup.TREND in resolved_set:
        for window in TREND_WINDOWS_V2:
            column_data[f"trend_{window}"] = _trend_column(quantities, window)
        column_data["rolling_mean_7_vs_28"] = _ratio_two_means_column(quantities, 7, 28)
        column_data["rolling_mean_28_vs_prev_28"] = _ratio_window_vs_prev_window_column(
            quantities, 28
        )

    # PRICE_PROMO
    if FeatureGroup.PRICE_PROMO in resolved_set:
        if sidecar.promo_kinds_per_day:
            _validate_per_day_length(
                name="promo_kinds_per_day",
                actual=len(sidecar.promo_kinds_per_day),
                expected=n_rows,
                group=FeatureGroup.PRICE_PROMO,
            )
        if sidecar.promo_discount_pct_per_day:
            _validate_per_day_length(
                name="promo_discount_pct_per_day",
                actual=len(sidecar.promo_discount_pct_per_day),
                expected=n_rows,
                group=FeatureGroup.PRICE_PROMO,
            )
        column_data.update(
            _price_promo_columns_historical(
                dates=dates,
                prices=prices,
                baseline_price=baseline_price,
                promo_dates=sidecar.promo_dates,
                promo_kinds_per_day=sidecar.promo_kinds_per_day,
                promo_discount_pct_per_day=sidecar.promo_discount_pct_per_day,
                n_rows=n_rows,
            )
        )

    # INVENTORY
    if FeatureGroup.INVENTORY in resolved_set:
        _validate_per_day_length(
            name="is_stockout_per_day",
            actual=len(sidecar.is_stockout_per_day),
            expected=n_rows,
            group=FeatureGroup.INVENTORY,
        )
        _validate_per_day_length(
            name="on_hand_qty",
            actual=len(sidecar.on_hand_qty),
            expected=n_rows,
            group=FeatureGroup.INVENTORY,
        )
        column_data.update(
            _stockout_columns(
                is_stockout_per_day=sidecar.is_stockout_per_day,
                on_hand_qty=sidecar.on_hand_qty,
                n_rows=n_rows,
            )
        )

    # LIFECYCLE
    if FeatureGroup.LIFECYCLE in resolved_set:
        column_data.update(
            _lifecycle_columns(
                dates,
                launch_date=sidecar.launch_date,
                discontinue_date=sidecar.discontinue_date,
            )
        )

    # REPLENISHMENT
    if FeatureGroup.REPLENISHMENT in resolved_set:
        if len(sidecar.replenishment_event_dates) != len(sidecar.replenishment_event_qty):
            raise ValueError(
                "build_historical_feature_rows_v2: replenishment_event_dates and "
                "replenishment_event_qty must have equal length"
            )
        column_data.update(
            _replenishment_columns(
                dates=dates,
                event_dates=sidecar.replenishment_event_dates,
                event_qty=sidecar.replenishment_event_qty,
            )
        )

    # RETURNS
    if FeatureGroup.RETURNS in resolved_set:
        _validate_per_day_length(
            name="returns_qty_per_day",
            actual=len(sidecar.returns_qty_per_day),
            expected=n_rows,
            group=FeatureGroup.RETURNS,
        )
        column_data.update(
            _returns_columns(
                quantities=quantities,
                returns_qty_per_day=sidecar.returns_qty_per_day,
                n_rows=n_rows,
            )
        )

    # EXOGENOUS_WEATHER
    if FeatureGroup.EXOGENOUS_WEATHER in resolved_set:
        column_data.update(
            _exogenous_columns(dates, WEATHER_SIGNAL_NAMES_V2, sidecar.weather_per_day)
        )

    # EXOGENOUS_MACRO
    if FeatureGroup.EXOGENOUS_MACRO in resolved_set:
        column_data.update(_exogenous_columns(dates, MACRO_SIGNAL_NAMES_V2, sidecar.macro_per_day))

    rows: list[list[float]] = [[column_data[name][i] for name in columns] for i in range(n_rows)]
    return rows


# ── Future builder ──────────────────────────────────────────────────────────


def _future_rolling_mean_column(
    history_tail: list[float], horizon: int, window: int
) -> list[float]:
    """Future rolling mean — only horizon day j=1 is computable; j>=2 → NaN.

    For horizon day ``j`` (1..horizon) the source window is
    ``T+j-window .. T+j-1``. The window touches only history (``<= T``) iff
    ``j == 1``. For ``j >= 2`` the window includes at least one future day
    whose target is unobserved → NaN.
    """
    out: list[float] = []
    for j in range(1, horizon + 1):
        if j == 1 and len(history_tail) >= window:
            out.append(sum(history_tail[-window:]) / window)
        else:
            out.append(math.nan)
    return out


def _future_rolling_median_column(
    history_tail: list[float], horizon: int, window: int
) -> list[float]:
    out: list[float] = []
    for j in range(1, horizon + 1):
        if j == 1 and len(history_tail) >= window:
            window_slice = sorted(history_tail[-window:])
            mid = window // 2
            if window % 2 == 1:
                out.append(window_slice[mid])
            else:
                out.append((window_slice[mid - 1] + window_slice[mid]) / 2.0)
        else:
            out.append(math.nan)
    return out


def _future_rolling_std_column(history_tail: list[float], horizon: int, window: int) -> list[float]:
    out: list[float] = []
    for j in range(1, horizon + 1):
        if j == 1 and len(history_tail) >= window:
            slice_ = history_tail[-window:]
            mean = sum(slice_) / window
            variance = sum((v - mean) ** 2 for v in slice_) / (window - 1) if window > 1 else 0.0
            out.append(math.sqrt(variance))
        else:
            out.append(math.nan)
    return out


def _future_trend_column(history_tail: list[float], horizon: int, window: int) -> list[float]:
    out: list[float] = []
    for j in range(1, horizon + 1):
        if j == 1 and len(history_tail) >= window:
            y = np.asarray(history_tail[-window:], dtype=np.float64)
            x = np.arange(window, dtype=np.float64)
            slope = float(np.polyfit(x, y, 1)[0])
            out.append(slope)
        else:
            out.append(math.nan)
    return out


def _future_ratio_two_means_column(
    history_tail: list[float], horizon: int, num_window: int, den_window: int
) -> list[float]:
    out: list[float] = []
    for j in range(1, horizon + 1):
        if j == 1 and len(history_tail) >= max(num_window, den_window):
            num = sum(history_tail[-num_window:]) / num_window
            den = sum(history_tail[-den_window:]) / den_window
            out.append(num / den if den != 0.0 else math.nan)
        else:
            out.append(math.nan)
    return out


def _future_ratio_window_vs_prev_window_column(
    history_tail: list[float], horizon: int, window: int
) -> list[float]:
    out: list[float] = []
    for j in range(1, horizon + 1):
        if j == 1 and len(history_tail) >= 2 * window:
            num = sum(history_tail[-window:]) / window
            den = sum(history_tail[-2 * window : -window]) / window
            out.append(num / den if den != 0.0 else math.nan)
        else:
            out.append(math.nan)
    return out


def _future_same_dow_mean_column(
    history_tail_dates: list[date],
    history_tail: list[float],
    test_dates: list[date],
    n_back: int,
) -> list[float]:
    """For each test day with weekday w, average the n_back most recent same-DOW history values.

    Reads only ``history_tail`` (entirely ``<= T``); a test day's same-DOW
    history slice never moves with horizon offset (no recursion).
    """
    out: list[float] = []
    for test_day in test_dates:
        same_dow = [
            history_tail[k]
            for k in range(len(history_tail_dates))
            if history_tail_dates[k].weekday() == test_day.weekday()
        ]
        if len(same_dow) >= n_back:
            out.append(sum(same_dow[-n_back:]) / n_back)
        else:
            out.append(math.nan)
    return out


def build_future_feature_rows_v2(
    *,
    test_dates: list[date],
    history_tail: list[float],
    history_tail_dates: list[date],
    gap: int,
    baseline_price: float,
    sidecar: V2FutureSidecar,
    history_tail_stockouts: tuple[bool, ...] = (),
    history_tail_on_hand: tuple[float | None, ...] = (),
    history_tail_replenishment_dates: tuple[date, ...] = (),
    history_tail_replenishment_qty: tuple[int, ...] = (),
    history_tail_returns_qty: tuple[int, ...] = (),
    groups: tuple[FeatureGroup, ...] | None = None,
) -> list[list[float]]:
    """Assemble the V2 future feature matrix — leakage-safe.

    A horizon day has no observed target — so the future builder NEVER reads a
    target value at a horizon row. Window-aggregate columns (rolling, trend,
    stockout/replenishment/returns windows) emit NaN for any horizon day whose
    window would touch ``T+1 …``; only horizon day ``j == 1`` is computable
    (its window slice is entirely ``<= T``).

    Args:
        test_dates: The horizon days ``T+gap+1 … T+gap+horizon`` (chronological).
        history_tail: Observed targets ending at the origin ``T`` (entirely
            ``<= T``); ``history_tail[-1] == y[T]``.
        history_tail_dates: ISO dates aligned with ``history_tail``.
        gap: Latency between train end and test start (days).
        baseline_price: Median positive training-window price.
        sidecar: Future inputs (calendar / lifecycle / assumed price-promo).
        history_tail_stockouts: V2 INVENTORY group — per-day stockout flags
            aligned with ``history_tail_dates``.
        history_tail_on_hand: Per-day on-hand inventory aligned with
            ``history_tail_dates``.
        history_tail_replenishment_dates: Event-time dates of replenishment
            receipts in the data window, sorted ascending.
        history_tail_replenishment_qty: Event-time received quantities aligned
            with ``history_tail_replenishment_dates``.
        history_tail_returns_qty: Per-day returns quantities aligned with
            ``history_tail_dates``.
        groups: Enabled :class:`FeatureGroup` subset (matches the bundle).

    Returns:
        Row-major matrix ``[len(test_dates)][n_features]`` in canonical V2
        column order; NaN-where-future for every CONDITIONALLY_SAFE cell.

    Raises:
        ValueError: When ``gap`` is negative, ``baseline_price`` is invalid,
            ``groups`` is empty / unknown, or per-day sidecar arrays have
            length mismatching ``test_dates`` for an enabled group.
    """
    horizon = len(test_dates)
    if gap < 0:
        raise ValueError(f"build_future_feature_rows_v2: gap must be >= 0, got {gap}")
    if not math.isfinite(baseline_price) or baseline_price <= 0.0:
        raise ValueError(
            f"build_future_feature_rows_v2: baseline_price must be finite and > 0, got {baseline_price!r}"
        )
    if len(history_tail) != len(history_tail_dates):
        raise ValueError(
            "build_future_feature_rows_v2: history_tail and history_tail_dates must have equal length"
        )
    resolved_groups = resolve_v2_groups(groups)
    resolved_set = set(resolved_groups)
    columns = canonical_feature_columns_v2(groups)
    column_data: dict[str, list[float]] = {}

    # TARGET_HISTORY — V1 long-lag helper extended over EXOGENOUS_LAGS_V2,
    # then gap-trimmed.
    if FeatureGroup.TARGET_HISTORY in resolved_set:
        lag_cols = build_long_lag_columns(history_tail, gap + horizon, EXOGENOUS_LAGS_V2)
        for lag in EXOGENOUS_LAGS_V2:
            column_data[f"lag_{lag}"] = lag_cols[f"lag_{lag}"][gap:]
        for n_back in SAME_DOW_MEAN_LOOKBACKS_V2:
            column_data[f"same_dow_mean_{n_back}"] = _future_same_dow_mean_column(
                history_tail_dates, history_tail, test_dates, n_back
            )

    # CALENDAR
    if FeatureGroup.CALENDAR in resolved_set:
        cal = _v2_calendar_columns(test_dates)
        column_data.update(cal)
        column_data["is_holiday"] = [
            1.0 if day in sidecar.holiday_dates else 0.0 for day in test_dates
        ]

    # ROLLING — j=1 computable, j>=2 NaN.
    if FeatureGroup.ROLLING in resolved_set:
        for window in ROLLING_WINDOWS_V2:
            column_data[f"rolling_mean_{window}"] = _future_rolling_mean_column(
                history_tail, horizon, window
            )
        column_data["rolling_median_28"] = _future_rolling_median_column(history_tail, horizon, 28)
        column_data["rolling_std_28"] = _future_rolling_std_column(history_tail, horizon, 28)

    # TREND — j=1 computable, j>=2 NaN.
    if FeatureGroup.TREND in resolved_set:
        for window in TREND_WINDOWS_V2:
            column_data[f"trend_{window}"] = _future_trend_column(history_tail, horizon, window)
        column_data["rolling_mean_7_vs_28"] = _future_ratio_two_means_column(
            history_tail, horizon, 7, 28
        )
        column_data["rolling_mean_28_vs_prev_28"] = _future_ratio_window_vs_prev_window_column(
            history_tail, horizon, 28
        )

    # PRICE_PROMO — driven entirely by the future sidecar (UNSAFE_UNLESS_SUPPLIED).
    if FeatureGroup.PRICE_PROMO in resolved_set:
        for name, arr in (
            ("price_factor_per_day", sidecar.price_factor_per_day),
            ("promo_active_per_day", sidecar.promo_active_per_day),
            ("promo_kinds_per_day", sidecar.promo_kinds_per_day),
            ("promo_discount_pct_per_day", sidecar.promo_discount_pct_per_day),
        ):
            if arr and len(arr) != horizon:
                _validate_per_day_length(
                    name=name,
                    actual=len(arr),
                    expected=horizon,
                    group=FeatureGroup.PRICE_PROMO,
                )
        price_factor = (
            [math.nan if v is None else float(v) for v in sidecar.price_factor_per_day]
            if sidecar.price_factor_per_day
            else [math.nan] * horizon
        )
        promo_active = (
            [1.0 if v else 0.0 for v in sidecar.promo_active_per_day]
            if sidecar.promo_active_per_day
            else [math.nan] * horizon
        )
        promo_discount = (
            [float(v) for v in sidecar.promo_discount_pct_per_day]
            if sidecar.promo_discount_pct_per_day
            else [math.nan] * horizon
        )
        if sidecar.promo_kinds_per_day:
            markdown = [
                1.0 if "markdown" in sidecar.promo_kinds_per_day[i] else 0.0 for i in range(horizon)
            ]
            bundle = [
                1.0 if "bundle" in sidecar.promo_kinds_per_day[i] else 0.0 for i in range(horizon)
            ]
        else:
            markdown = [math.nan] * horizon
            bundle = [math.nan] * horizon
        column_data["price_factor"] = price_factor
        column_data["promo_active"] = promo_active
        column_data["promo_discount_pct"] = promo_discount
        column_data["promo_kind_markdown_active"] = markdown
        column_data["promo_kind_bundle_active"] = bundle

    # INVENTORY — j=1 may be computable from history_tail; j>=2 NaN unless
    # caller supplies projected stockouts (V2 MVP does NOT support
    # caller-supplied projections, so j>=2 is always NaN).
    if FeatureGroup.INVENTORY in resolved_set:
        is_stockout_lag1 = (
            [float(1.0 if history_tail_stockouts[-1] else 0.0)] + [math.nan] * (horizon - 1)
            if history_tail_stockouts
            else [math.nan] * horizon
        )
        stockout_7 = (
            [float(sum(1 if flag else 0 for flag in history_tail_stockouts[-7:]))]
            + [math.nan] * (horizon - 1)
            if len(history_tail_stockouts) >= 7
            else [math.nan] * horizon
        )
        stockout_28 = (
            [float(sum(1 if flag else 0 for flag in history_tail_stockouts[-28:]))]
            + [math.nan] * (horizon - 1)
            if len(history_tail_stockouts) >= 28
            else [math.nan] * horizon
        )
        # inventory_available_ratio_28 — j=1: mean(observed)/max(observed)
        window = INVENTORY_AVAILABILITY_WINDOW_V2
        if len(history_tail_on_hand) >= window:
            slice_ = history_tail_on_hand[-window:]
            observed = [v for v in slice_ if v is not None]
            if observed and max(observed) > 0.0:
                avail = sum(observed) / len(observed) / max(observed)
            else:
                avail = math.nan
            avail_ratio = [avail] + [math.nan] * (horizon - 1)
        else:
            avail_ratio = [math.nan] * horizon
        column_data["is_stockout_lag1"] = is_stockout_lag1
        column_data["stockout_days_7"] = stockout_7
        column_data["stockout_days_28"] = stockout_28
        column_data["inventory_available_ratio_28"] = avail_ratio

    # LIFECYCLE — pure function of test dates + launch/discontinue (knowable at T).
    if FeatureGroup.LIFECYCLE in resolved_set:
        column_data.update(
            _lifecycle_columns(
                test_dates,
                launch_date=sidecar.launch_date,
                discontinue_date=sidecar.discontinue_date,
            )
        )

    # REPLENISHMENT — events strictly before each test day. With V2 MVP we
    # only consider events from history (the caller does not posit future
    # replenishments), so j>=2 uses the same prior-event set as j=1.
    if FeatureGroup.REPLENISHMENT in resolved_set:
        if len(history_tail_replenishment_dates) != len(history_tail_replenishment_qty):
            raise ValueError("build_future_feature_rows_v2: replenishment dates and qty must align")
        days_since: list[float] = []
        count_14: list[float] = []
        qty_28: list[float] = []
        for j, day in enumerate(test_dates):
            prior = [
                (d, q)
                for d, q in zip(
                    history_tail_replenishment_dates,
                    history_tail_replenishment_qty,
                    strict=True,
                )
                if d < day
            ]
            if prior:
                last = max(d for d, _ in prior)
                days_since.append(float((day - last).days))
            else:
                days_since.append(math.nan)
            # Counts / qty only on j=1 to mirror the historical builder's
            # strictly-earlier rule; further horizon days have no new events
            # in the supplied sidecar.
            if j == 0:
                win14_start = day.toordinal() - REPLENISHMENT_WINDOW_V2
                win28_start = day.toordinal() - REPLENISHMENT_QTY_WINDOW_V2
                count_14.append(float(sum(1 for d, _ in prior if d.toordinal() >= win14_start)))
                qty_28.append(float(sum(q for d, q in prior if d.toordinal() >= win28_start)))
            else:
                count_14.append(math.nan)
                qty_28.append(math.nan)
        column_data["days_since_last_replenishment"] = days_since
        column_data["replenishment_count_14"] = count_14
        column_data["replenishment_qty_28"] = qty_28

    # RETURNS — j=1 computable from history_tail_returns_qty; j>=2 NaN.
    if FeatureGroup.RETURNS in resolved_set:
        returns_floats = [float(v) for v in history_tail_returns_qty]
        for window in RETURNS_WINDOWS_V2:
            if len(returns_floats) >= window:
                first = float(sum(returns_floats[-window:]))
            else:
                first = math.nan
            column_data[f"returns_qty_{window}"] = [first] + [math.nan] * (horizon - 1)
        rate_window = RETURNS_RATE_WINDOW_V2
        if len(returns_floats) >= rate_window and len(history_tail) >= rate_window:
            ret_sum = sum(returns_floats[-rate_window:])
            sales_sum = sum(history_tail[-rate_window:])
            first = ret_sum / sales_sum if sales_sum > 0.0 else 0.0
        else:
            first = math.nan
        column_data["returns_rate_28"] = [first] + [math.nan] * (horizon - 1)

    # EXOGENOUS_WEATHER / MACRO — NaN when the date has no entry in the sidecar.
    if FeatureGroup.EXOGENOUS_WEATHER in resolved_set:
        column_data.update(
            _exogenous_columns(test_dates, WEATHER_SIGNAL_NAMES_V2, sidecar.weather_per_day)
        )
    if FeatureGroup.EXOGENOUS_MACRO in resolved_set:
        column_data.update(
            _exogenous_columns(test_dates, MACRO_SIGNAL_NAMES_V2, sidecar.macro_per_day)
        )

    # Defensive: any column the manifest expects but the dispatcher above did
    # not produce becomes an all-NaN column (cannot happen in practice — every
    # enabled group fills every one of its columns — but mirrors the V1
    # ``assemble_future_frame`` defensive shape).
    for column in columns:
        if column not in column_data:
            column_data[column] = [math.nan] * horizon

    rows: list[list[float]] = [[column_data[name][j] for name in columns] for j in range(horizon)]
    return rows


__all__ = [
    "build_future_feature_rows_v2",
    "build_historical_feature_rows_v2",
]

# Cross-reference the V1 calendar columns set so static analysers see it used.
_ = CALENDAR_COLUMNS
