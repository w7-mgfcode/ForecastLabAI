"""Unit tests for the V2 feature-frame contract (PRP-35).

Mirrors ``test_contract.py``: pins the V2 pinned constants, the column manifest
+ order, group enablement semantics, the V2 safety taxonomy coverage, and the
leaf-level architectural invariant (``app/shared/**`` never imports
``app/features/**``) — now extended to walk ``contract_v2.py``, ``rows_v2.py``,
and ``sidecar.py``.

The leakage invariants live separately in ``test_leakage_v2.py`` (load-bearing).
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.shared.feature_frames import (
    CALENDAR_COLUMNS,
    DEFAULT_V2_GROUPS,
    EXOGENOUS_LAGS_V2,
    HISTORY_TAIL_DAYS_V2,
    ROLLING_WINDOWS_V2,
    SAME_DOW_MEAN_LOOKBACKS_V2,
    TREND_WINDOWS_V2,
    FeatureGroup,
    FeatureSafety,
    V2ColumnSpec,
    canonical_feature_columns,
    canonical_feature_columns_v2,
    v2_column_manifest,
    v2_feature_groups_dict,
    v2_feature_safety,
    v2_feature_safety_classes,
    v2_pinned_constants,
)

# --- pinned constants ---------------------------------------------------------


def test_pinned_constants_v2() -> None:
    """V2 modelling constants hold their decided values."""
    assert EXOGENOUS_LAGS_V2 == (1, 7, 14, 28, 56, 364)
    assert 364 in EXOGENOUS_LAGS_V2  # DOW-preserving yearly lag
    assert 365 not in EXOGENOUS_LAGS_V2
    assert ROLLING_WINDOWS_V2 == (7, 28, 90)
    assert TREND_WINDOWS_V2 == (30, 90)
    assert SAME_DOW_MEAN_LOOKBACKS_V2 == (4, 8)
    assert HISTORY_TAIL_DAYS_V2 == 400


def test_default_groups_subset() -> None:
    """Default groups exclude the Phase-2 sidecar groups (MVP-green default)."""
    default = set(DEFAULT_V2_GROUPS)
    assert FeatureGroup.TARGET_HISTORY in default
    assert FeatureGroup.CALENDAR in default
    assert FeatureGroup.ROLLING in default
    assert FeatureGroup.TREND in default
    assert FeatureGroup.PRICE_PROMO in default
    assert FeatureGroup.LIFECYCLE in default
    # Off by default
    for group in (
        FeatureGroup.INVENTORY,
        FeatureGroup.REPLENISHMENT,
        FeatureGroup.RETURNS,
        FeatureGroup.EXOGENOUS_WEATHER,
        FeatureGroup.EXOGENOUS_MACRO,
    ):
        assert group not in default


# --- manifest order + group enablement ---------------------------------------


def test_default_v2_manifest_contains_yearly_lag_and_calendar_extensions() -> None:
    columns = canonical_feature_columns_v2()
    assert "lag_364" in columns
    assert "same_dow_mean_4" in columns
    assert "same_dow_mean_8" in columns
    # V2 calendar extensions
    assert "week_of_year_sin" in columns
    assert "day_of_month_cos" in columns
    # V2 rolling + trend columns
    assert "rolling_mean_7" in columns
    assert "rolling_mean_28" in columns
    assert "rolling_mean_90" in columns
    assert "trend_30" in columns
    assert "trend_90" in columns


def test_v2_manifest_subset_when_groups_narrowed() -> None:
    narrow = canonical_feature_columns_v2(
        groups=(FeatureGroup.TARGET_HISTORY, FeatureGroup.CALENDAR)
    )
    # Only target_history + calendar columns appear
    for name in narrow:
        assert (
            name.startswith("lag_")
            or name.startswith("same_dow_mean_")
            or name
            in {
                "dow_sin",
                "dow_cos",
                "month_sin",
                "month_cos",
                "is_weekend",
                "is_month_end",
                "week_of_year_sin",
                "week_of_year_cos",
                "day_of_month_sin",
                "day_of_month_cos",
                "is_holiday",
            }
        )
    # And rolling / trend / price columns must NOT appear
    assert "rolling_mean_7" not in narrow
    assert "price_factor" not in narrow


def test_v2_column_order_is_deterministic() -> None:
    """Two calls with the same groups produce the same column list (byte-stable)."""
    first = canonical_feature_columns_v2()
    second = canonical_feature_columns_v2()
    assert first == second


def test_v2_manifest_respects_canonical_group_order() -> None:
    """Caller's group ordering is normalised to canonical group order."""
    a = canonical_feature_columns_v2(groups=(FeatureGroup.CALENDAR, FeatureGroup.TARGET_HISTORY))
    b = canonical_feature_columns_v2(groups=(FeatureGroup.TARGET_HISTORY, FeatureGroup.CALENDAR))
    assert a == b
    # target_history columns come strictly before calendar columns
    assert a.index("lag_1") < a.index("dow_sin")


def test_v2_includes_v1_calendar_columns_at_same_relative_position() -> None:
    """The V1 CALENDAR_COLUMNS appear in the V2 manifest in their V1 order.

    The V2 manifest may add columns within the V2 CALENDAR group (week_of_year,
    day_of_month) but must preserve the V1 in-group order for back-compat
    consumers.
    """
    v2_calendar = canonical_feature_columns_v2(groups=(FeatureGroup.CALENDAR,))
    v1_present = [c for c in v2_calendar if c in CALENDAR_COLUMNS]
    assert v1_present == list(CALENDAR_COLUMNS)


def test_v2_includes_every_v1_canonical_column() -> None:
    """Every V1 canonical column (V1 default lags + calendar + exogenous) is
    reachable via the V2 manifest when the appropriate V2 groups are enabled."""
    v1_columns = set(canonical_feature_columns())
    v2_full = set(
        canonical_feature_columns_v2(
            groups=(
                FeatureGroup.TARGET_HISTORY,
                FeatureGroup.CALENDAR,
                FeatureGroup.PRICE_PROMO,
                FeatureGroup.LIFECYCLE,
            )
        )
    )
    # All V1 columns must be in V2's full set (modulo the column home — V1's
    # `is_holiday` is in V2's CALENDAR group, not PRICE_PROMO).
    missing = v1_columns - v2_full
    assert not missing, f"V2 manifest missing V1 columns: {sorted(missing)}"


# --- V2 safety taxonomy -------------------------------------------------------


def test_every_default_v2_column_is_classifiable() -> None:
    """Every default-V2 column resolves to a FeatureSafety class via v2_feature_safety."""
    for column in canonical_feature_columns_v2():
        assert isinstance(v2_feature_safety(column), FeatureSafety)


def test_v2_calendar_and_lifecycle_columns_are_SAFE() -> None:
    """Calendar + lifecycle columns are pure functions of the date — SAFE."""
    for column in canonical_feature_columns_v2(groups=(FeatureGroup.CALENDAR,)):
        assert v2_feature_safety(column) is FeatureSafety.SAFE
    for column in canonical_feature_columns_v2(groups=(FeatureGroup.LIFECYCLE,)):
        assert v2_feature_safety(column) is FeatureSafety.SAFE


def test_v2_target_history_columns_are_CONDITIONALLY_SAFE() -> None:
    for column in canonical_feature_columns_v2(groups=(FeatureGroup.TARGET_HISTORY,)):
        assert v2_feature_safety(column) is FeatureSafety.CONDITIONALLY_SAFE


def test_v2_price_promo_columns_are_UNSAFE_UNLESS_SUPPLIED() -> None:
    for column in canonical_feature_columns_v2(groups=(FeatureGroup.PRICE_PROMO,)):
        assert v2_feature_safety(column) is FeatureSafety.UNSAFE_UNLESS_SUPPLIED


def test_v2_feature_safety_rejects_an_unclassified_column() -> None:
    try:
        v2_feature_safety("mystery_feature_v2")
    except KeyError:
        pass
    else:
        raise AssertionError("v2_feature_safety must raise KeyError for an unknown column")


# --- v2_feature_groups_dict + v2_feature_safety_classes -----------------------


def test_v2_feature_groups_dict_maps_columns_to_group_names() -> None:
    columns = canonical_feature_columns_v2()
    mapping = v2_feature_groups_dict(columns)
    # Every default group is represented
    for group in DEFAULT_V2_GROUPS:
        assert group.value in mapping
        assert mapping[group.value], f"group {group.value} has no columns"
    # The combined columns reconstruct the full default manifest
    all_columns_back = [c for group_cols in mapping.values() for c in group_cols]
    assert set(all_columns_back) == set(columns)


def test_v2_feature_safety_classes_returns_full_map() -> None:
    columns = canonical_feature_columns_v2()
    classes = v2_feature_safety_classes(columns)
    assert set(classes.keys()) == set(columns)
    assert set(classes.values()) <= {"safe", "conditionally_safe", "unsafe_unless_supplied"}


# --- v2_pinned_constants ------------------------------------------------------


def test_v2_pinned_constants_snapshot_matches_constants() -> None:
    snap = v2_pinned_constants()
    assert tuple(snap["exogenous_lags"]) == EXOGENOUS_LAGS_V2
    assert tuple(snap["rolling_windows"]) == ROLLING_WINDOWS_V2
    assert tuple(snap["trend_windows"]) == TREND_WINDOWS_V2


# --- v2_column_manifest dataclass shape ---------------------------------------


def test_v2_column_manifest_carries_spec_objects() -> None:
    manifest = v2_column_manifest()
    assert manifest  # non-empty
    for spec in manifest:
        assert isinstance(spec, V2ColumnSpec)
        assert isinstance(spec.name, str)
        assert isinstance(spec.group, FeatureGroup)
        assert isinstance(spec.safety, FeatureSafety)


# --- LOUD failure modes --------------------------------------------------------


def test_empty_groups_raises() -> None:
    """An empty groups tuple is a misuse — zero-column matrix is forbidden."""
    try:
        canonical_feature_columns_v2(groups=())
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for empty groups")


# --- architectural invariant (extended to V2 modules) ------------------------


def test_v2_modules_are_leaf_level() -> None:
    """``app/shared/feature_frames/**`` is leaf-level — never imports vertical slices.

    Extended over contract_v2.py, rows_v2.py, sidecar.py so the AST-walk
    invariant catches a V2 regression.
    """
    pkg_dir = Path(__file__).resolve().parents[1]
    walked: set[str] = set()
    for py_file in pkg_dir.rglob("*.py"):
        walked.add(py_file.name)
        source = py_file.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.features"), (
                    f"ARCHITECTURE BREACH: {py_file} imports from {node.module}"
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("app.features"), (
                        f"ARCHITECTURE BREACH: {py_file} imports {alias.name}"
                    )
    # The V2 modules must exist and be covered by the walk above.
    assert {"contract_v2.py", "rows_v2.py", "sidecar.py"} <= walked, (
        f"expected contract_v2.py + rows_v2.py + sidecar.py in the walk, got {sorted(walked)}"
    )
