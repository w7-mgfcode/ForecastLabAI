"""Feature-frame contract V2 — richer, opt-in feature manifest (PRP-35).

V2 extends :mod:`app.shared.feature_frames.contract` with a richer set of
columns (yearly seasonality, rolling demand level, trend, lifecycle, optional
phase-2 sidecar signals) WITHOUT changing V1 byte-for-byte. V1 callers continue
to see V1 columns at the same positions; V2 callers opt in via
``TrainRequest.feature_frame_version=2`` + an optional ``feature_groups`` list.

LEAF-LEVEL: like ``contract.py`` this module may NEVER import from
``app/features/**``. Every symbol is pure stdlib (``math``, ``dataclasses``,
``enum``, ``datetime``).

The leakage rule the V2 builders obey mirrors V1 exactly:

    A future feature value for horizon day ``D`` may use ONLY information
    knowable at the forecast origin ``T``: the observed history up to and
    including ``T``, the calendar (a pure function of the date), launch /
    discontinue dates (timeless attributes), or scenario-assumption inputs
    posited by the caller. It may NEVER read an observed target — or any
    sidecar value — at a horizon day ``D``.

Every V2 column has a :class:`~app.shared.feature_frames.contract.FeatureSafety`
classification (resolved via :func:`v2_feature_safety_classes`) so a downstream
consumer can tell at a glance which cells may be NaN at a future horizon row.

The V2 column manifest is a function of the enabled :class:`FeatureGroup`
subset. Group enablement decides which columns appear in the output matrix
(disabled group = silent omission, NOT a NaN-filled placeholder). Per-cell
NaN signals "source data unknown for this day"; HGBR tolerates NaN natively.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.shared.feature_frames.contract import (
    CALENDAR_COLUMNS,
    FeatureSafety,
)

# ── Versions ────────────────────────────────────────────────────────────────
FEATURE_FRAME_VERSION_V1: int = 1
FEATURE_FRAME_VERSION_V2: int = 2

# ── Pinned V2 modelling constants (PRP-35 DECISIONS LOCKED) ─────────────────
# Lag offsets — daily, weekly, fortnightly, four-week, eight-week, yearly.
# ``lag_364`` (not ``lag_365``) preserves day-of-week (52 * 7 = 364).
EXOGENOUS_LAGS_V2: tuple[int, ...] = (1, 7, 14, 28, 56, 364)
# Same-day-of-week mean lookbacks: average of the N most recent same-weekday
# observations strictly before each row.
SAME_DOW_MEAN_LOOKBACKS_V2: tuple[int, ...] = (4, 8)
# Rolling-mean windows (also feed median / std).
ROLLING_WINDOWS_V2: tuple[int, ...] = (7, 28, 90)
# Trend windows — linear slope (numpy.polyfit) over the trailing N days.
TREND_WINDOWS_V2: tuple[int, ...] = (30, 90)
# Stockout / replenishment / returns aggregate windows.
STOCKOUT_WINDOWS_V2: tuple[int, ...] = (7, 28)
REPLENISHMENT_WINDOW_V2: int = 14
REPLENISHMENT_QTY_WINDOW_V2: int = 28
RETURNS_WINDOWS_V2: tuple[int, ...] = (7, 28)
RETURNS_RATE_WINDOW_V2: int = 28
INVENTORY_AVAILABILITY_WINDOW_V2: int = 28
# Lifecycle thresholds (days from launch).
LIFECYCLE_NEW_THRESHOLD_DAYS: int = 30
LIFECYCLE_MATURE_THRESHOLD_DAYS: int = 180
# Observed-target tail length fed to the future builder. Must comfortably
# exceed ``max(EXOGENOUS_LAGS_V2)`` and the largest rolling/trend window.
HISTORY_TAIL_DAYS_V2: int = 400  # 364 + 28 buffer + 8 safety margin

# Canonical signal names emitted by the EXOGENOUS_* groups in V2. The MVP
# pins a small, stable set; future PRPs can extend the manifest.
WEATHER_SIGNAL_NAMES_V2: tuple[str, ...] = ("weather_temp_c", "weather_precip_mm")
MACRO_SIGNAL_NAMES_V2: tuple[str, ...] = ("macro_index",)


# ── Feature groups ──────────────────────────────────────────────────────────


class FeatureGroup(str, Enum):
    """Coarse grouping of V2 feature columns — drives opt-in enablement.

    Enabling a group emits its columns into the manifest in the order the
    group is listed below. Disabling a group omits its columns entirely (NOT a
    NaN-fill placeholder). Per-day NaN inside an enabled group signals
    "source data unknown for this day"; the model (HGBR) handles NaN natively.
    """

    TARGET_HISTORY = "target_history"
    CALENDAR = "calendar"
    ROLLING = "rolling"
    TREND = "trend"
    PRICE_PROMO = "price_promo"
    INVENTORY = "inventory"
    LIFECYCLE = "lifecycle"
    REPLENISHMENT = "replenishment"
    RETURNS = "returns"
    EXOGENOUS_WEATHER = "exogenous_weather"
    EXOGENOUS_MACRO = "exogenous_macro"


# Canonical group order — the V2 manifest emits columns in exactly this order.
_GROUP_ORDER: tuple[FeatureGroup, ...] = (
    FeatureGroup.TARGET_HISTORY,
    FeatureGroup.CALENDAR,
    FeatureGroup.ROLLING,
    FeatureGroup.TREND,
    FeatureGroup.PRICE_PROMO,
    FeatureGroup.INVENTORY,
    FeatureGroup.LIFECYCLE,
    FeatureGroup.REPLENISHMENT,
    FeatureGroup.RETURNS,
    FeatureGroup.EXOGENOUS_WEATHER,
    FeatureGroup.EXOGENOUS_MACRO,
)

# Default groups when ``feature_groups`` is None on the request. Phase-2
# sidecar groups (INVENTORY / REPLENISHMENT / RETURNS / EXOGENOUS_*) are off
# by default so the MVP stays green on smaller seeded DBs.
DEFAULT_V2_GROUPS: tuple[FeatureGroup, ...] = (
    FeatureGroup.TARGET_HISTORY,
    FeatureGroup.CALENDAR,
    FeatureGroup.ROLLING,
    FeatureGroup.TREND,
    FeatureGroup.PRICE_PROMO,
    FeatureGroup.LIFECYCLE,
)


# ── Column manifests per group ──────────────────────────────────────────────
# Each tuple is the in-group column order. Tests pin both the per-group
# membership and the overall canonical order built from these blocks.

_TARGET_HISTORY_COLUMNS: tuple[str, ...] = (
    *(f"lag_{k}" for k in EXOGENOUS_LAGS_V2),
    *(f"same_dow_mean_{n}" for n in SAME_DOW_MEAN_LOOKBACKS_V2),
)

# V1 calendar columns first (V1 ordering preserved within the V1 subset), then
# V2 extensions. ``is_holiday`` (V1 EXOGENOUS_COLUMNS) is calendar-derived and
# placed last in the V2 CALENDAR group — see PRP-35 § Open Design Decisions.
_CALENDAR_COLUMNS_V2: tuple[str, ...] = (
    *CALENDAR_COLUMNS,  # dow_sin, dow_cos, month_sin, month_cos, is_weekend, is_month_end
    "week_of_year_sin",
    "week_of_year_cos",
    "day_of_month_sin",
    "day_of_month_cos",
    "is_holiday",
)

_ROLLING_COLUMNS: tuple[str, ...] = (
    "rolling_mean_7",
    "rolling_mean_28",
    "rolling_mean_90",
    "rolling_median_28",
    "rolling_std_28",
)

_TREND_COLUMNS: tuple[str, ...] = (
    "trend_30",
    "trend_90",
    "rolling_mean_7_vs_28",
    "rolling_mean_28_vs_prev_28",
)

# V1 price_factor + promo_active first, then V2 extensions.
_PRICE_PROMO_COLUMNS: tuple[str, ...] = (
    "price_factor",
    "promo_active",
    "promo_discount_pct",
    "promo_kind_markdown_active",
    "promo_kind_bundle_active",
)

_INVENTORY_COLUMNS: tuple[str, ...] = (
    "is_stockout_lag1",
    "stockout_days_7",
    "stockout_days_28",
    "inventory_available_ratio_28",
)

# V1 days_since_launch first, then V2 extensions.
_LIFECYCLE_COLUMNS: tuple[str, ...] = (
    "days_since_launch",
    "is_new_product",
    "is_mature_product",
    "is_discontinued",
    "days_until_discontinue",
)

_REPLENISHMENT_COLUMNS: tuple[str, ...] = (
    "days_since_last_replenishment",
    "replenishment_count_14",
    "replenishment_qty_28",
)

_RETURNS_COLUMNS: tuple[str, ...] = (
    "returns_qty_7",
    "returns_qty_28",
    "returns_rate_28",
)

_EXOGENOUS_WEATHER_COLUMNS: tuple[str, ...] = tuple(
    f"exo_{name}" for name in WEATHER_SIGNAL_NAMES_V2
)
_EXOGENOUS_MACRO_COLUMNS: tuple[str, ...] = tuple(f"exo_{name}" for name in MACRO_SIGNAL_NAMES_V2)


_GROUP_COLUMNS: dict[FeatureGroup, tuple[str, ...]] = {
    FeatureGroup.TARGET_HISTORY: _TARGET_HISTORY_COLUMNS,
    FeatureGroup.CALENDAR: _CALENDAR_COLUMNS_V2,
    FeatureGroup.ROLLING: _ROLLING_COLUMNS,
    FeatureGroup.TREND: _TREND_COLUMNS,
    FeatureGroup.PRICE_PROMO: _PRICE_PROMO_COLUMNS,
    FeatureGroup.INVENTORY: _INVENTORY_COLUMNS,
    FeatureGroup.LIFECYCLE: _LIFECYCLE_COLUMNS,
    FeatureGroup.REPLENISHMENT: _REPLENISHMENT_COLUMNS,
    FeatureGroup.RETURNS: _RETURNS_COLUMNS,
    FeatureGroup.EXOGENOUS_WEATHER: _EXOGENOUS_WEATHER_COLUMNS,
    FeatureGroup.EXOGENOUS_MACRO: _EXOGENOUS_MACRO_COLUMNS,
}


# Per-column safety class. Group enablement decides emission; this map decides
# leakage class. Every column V2 ever emits is classified here.
_COLUMN_SAFETY: dict[str, FeatureSafety] = {
    # TARGET_HISTORY — all conditionally safe (target-derived)
    **dict.fromkeys(_TARGET_HISTORY_COLUMNS, FeatureSafety.CONDITIONALLY_SAFE),
    # CALENDAR — pure functions of the date; SAFE
    **dict.fromkeys(_CALENDAR_COLUMNS_V2, FeatureSafety.SAFE),
    # ROLLING — target-derived rolling statistics
    **dict.fromkeys(_ROLLING_COLUMNS, FeatureSafety.CONDITIONALLY_SAFE),
    # TREND — target-derived
    **dict.fromkeys(_TREND_COLUMNS, FeatureSafety.CONDITIONALLY_SAFE),
    # PRICE_PROMO — UNSAFE unless caller supplies the future inputs
    **dict.fromkeys(_PRICE_PROMO_COLUMNS, FeatureSafety.UNSAFE_UNLESS_SUPPLIED),
    # INVENTORY — observed inventory series; future unknowable unless supplied
    **dict.fromkeys(_INVENTORY_COLUMNS, FeatureSafety.CONDITIONALLY_SAFE),
    # LIFECYCLE — pure function of date + launch/discontinue dates (timeless)
    **dict.fromkeys(_LIFECYCLE_COLUMNS, FeatureSafety.SAFE),
    # REPLENISHMENT — observed event series; future unknowable
    **dict.fromkeys(_REPLENISHMENT_COLUMNS, FeatureSafety.CONDITIONALLY_SAFE),
    # RETURNS — observed returns series; future unknowable
    **dict.fromkeys(_RETURNS_COLUMNS, FeatureSafety.CONDITIONALLY_SAFE),
    # EXOGENOUS_* — observed signals; future unknowable unless supplied
    **dict.fromkeys(_EXOGENOUS_WEATHER_COLUMNS, FeatureSafety.CONDITIONALLY_SAFE),
    **dict.fromkeys(_EXOGENOUS_MACRO_COLUMNS, FeatureSafety.CONDITIONALLY_SAFE),
}


# ── Public surface ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class V2ColumnSpec:
    """One V2 feature column — name, group, safety class."""

    name: str
    group: FeatureGroup
    safety: FeatureSafety


def resolve_v2_groups(groups: tuple[FeatureGroup, ...] | None) -> tuple[FeatureGroup, ...]:
    """Return groups in canonical order. ``None`` → ``DEFAULT_V2_GROUPS``."""
    requested = DEFAULT_V2_GROUPS if groups is None else groups
    if not requested:
        raise ValueError(
            "v2 feature manifest: at least one FeatureGroup must be enabled "
            "(empty groups would produce a zero-column matrix)."
        )
    requested_set = set(requested)
    unknown = requested_set - set(_GROUP_ORDER)
    if unknown:
        raise ValueError(f"v2 feature manifest: unknown FeatureGroup(s): {sorted(unknown)!r}")
    # Emit in canonical group order regardless of input order.
    return tuple(g for g in _GROUP_ORDER if g in requested_set)


def v2_column_manifest(
    groups: tuple[FeatureGroup, ...] | None = None,
) -> list[V2ColumnSpec]:
    """The ordered, canonical V2 column manifest for the enabled groups.

    Args:
        groups: The enabled :class:`FeatureGroup` subset. ``None`` resolves to
            :data:`DEFAULT_V2_GROUPS`. Group ordering in the output follows the
            canonical group order; the caller's input order is ignored.

    Returns:
        Ordered list of :class:`V2ColumnSpec` — one per emitted column.

    Raises:
        ValueError: When ``groups`` is empty or names an unknown group.
    """
    resolved = resolve_v2_groups(groups)
    manifest: list[V2ColumnSpec] = []
    for group in resolved:
        for column in _GROUP_COLUMNS[group]:
            manifest.append(V2ColumnSpec(name=column, group=group, safety=_COLUMN_SAFETY[column]))
    return manifest


def canonical_feature_columns_v2(
    groups: tuple[FeatureGroup, ...] | None = None,
) -> list[str]:
    """Equivalent of ``canonical_feature_columns`` for V2."""
    return [spec.name for spec in v2_column_manifest(groups)]


def v2_feature_groups_dict(columns: list[str]) -> dict[str, list[str]]:
    """Return a ``{group_name: [columns]}`` mapping for the supplied columns.

    Persisted into bundle metadata so the dashboard (Slice C) can render the
    grouped column list. Columns not classifiable to a V2 group are silently
    skipped (defensive — every column V2 emits is classified by construction).
    """
    # Reverse map: column name → group
    col_to_group: dict[str, FeatureGroup] = {}
    for group_key, group_cols in _GROUP_COLUMNS.items():
        for column in group_cols:
            col_to_group[column] = group_key

    grouped: dict[str, list[str]] = {}
    for column in columns:
        owning_group = col_to_group.get(column)
        if owning_group is None:
            continue
        grouped.setdefault(owning_group.value, []).append(column)
    return grouped


def v2_feature_safety_classes(columns: list[str]) -> dict[str, str]:
    """Return ``{column: safety_class.value}`` for every supplied column.

    Persisted into bundle metadata. Unknown columns (defensive case) classify
    as :data:`FeatureSafety.CONDITIONALLY_SAFE` to mirror V1's lag_* fallback.
    """
    out: dict[str, str] = {}
    for column in columns:
        safety = _COLUMN_SAFETY.get(column)
        if safety is None:
            # Mirror V1 contract: any unclassified column conservatively
            # routes to CONDITIONALLY_SAFE so downstream consumers don't fail.
            safety = FeatureSafety.CONDITIONALLY_SAFE
        out[column] = safety.value
    return out


def v2_feature_safety(column: str) -> FeatureSafety:
    """Return the V2 leakage classification of a single column."""
    if column in _COLUMN_SAFETY:
        return _COLUMN_SAFETY[column]
    raise KeyError(f"Unclassified V2 feature column: {column!r}")


def v2_pinned_constants() -> dict[str, list[int]]:
    """Snapshot of the pinned V2 modelling constants — persisted to bundle metadata."""
    return {
        "exogenous_lags": list(EXOGENOUS_LAGS_V2),
        "same_dow_mean_lookbacks": list(SAME_DOW_MEAN_LOOKBACKS_V2),
        "rolling_windows": list(ROLLING_WINDOWS_V2),
        "trend_windows": list(TREND_WINDOWS_V2),
        "stockout_windows": list(STOCKOUT_WINDOWS_V2),
        "replenishment_window": [REPLENISHMENT_WINDOW_V2],
        "replenishment_qty_window": [REPLENISHMENT_QTY_WINDOW_V2],
        "returns_windows": list(RETURNS_WINDOWS_V2),
        "returns_rate_window": [RETURNS_RATE_WINDOW_V2],
        "inventory_availability_window": [INVENTORY_AVAILABILITY_WINDOW_V2],
        "history_tail_days": [HISTORY_TAIL_DAYS_V2],
    }
