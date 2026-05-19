"""Unit tests for the shared feature-frame contract (MLZOO-A).

Covers the canonical column set + order, the pinned constants, the
:class:`FeatureSafety` taxonomy coverage, the :class:`FutureFeatureFrame`
shape, builder determinism, and the leaf-level architectural invariant
(``app/shared/**`` never imports ``app/features/**``).

The leakage invariants live separately in ``test_leakage.py`` (load-bearing).
"""

from __future__ import annotations

import ast
from datetime import date, timedelta
from pathlib import Path

from app.shared.feature_frames import (
    CALENDAR_COLUMNS,
    EXOGENOUS_COLUMNS,
    EXOGENOUS_LAGS,
    HISTORY_TAIL_DAYS,
    FeatureSafety,
    FutureFeatureFrame,
    build_calendar_columns,
    canonical_feature_columns,
    feature_safety,
)

_ORIGIN = date(2026, 6, 30)
_HORIZON = 14
_HORIZON_DATES = [_ORIGIN + timedelta(days=offset) for offset in range(1, _HORIZON + 1)]


# --- pinned constants ---------------------------------------------------------


def test_pinned_constants() -> None:
    """The pinned modelling constants hold their decided values."""
    assert EXOGENOUS_LAGS == (1, 7, 14, 28)
    assert HISTORY_TAIL_DAYS == 90


def test_canonical_feature_columns_order() -> None:
    """The canonical column list is target lags, then calendar, then exogenous."""
    columns = canonical_feature_columns()
    assert columns[:4] == ["lag_1", "lag_7", "lag_14", "lag_28"]
    assert columns[4 : 4 + len(CALENDAR_COLUMNS)] == list(CALENDAR_COLUMNS)
    assert columns[-len(EXOGENOUS_COLUMNS) :] == list(EXOGENOUS_COLUMNS)
    assert len(columns) == len(EXOGENOUS_LAGS) + len(CALENDAR_COLUMNS) + len(EXOGENOUS_COLUMNS)


# --- FeatureSafety taxonomy ---------------------------------------------------


def test_feature_class_covers_every_canonical_column() -> None:
    """Every canonical column resolves to a FeatureSafety class — no KeyError."""
    for column in canonical_feature_columns():
        assert isinstance(feature_safety(column), FeatureSafety)


def test_calendar_columns_are_all_SAFE() -> None:
    """Calendar columns are pure functions of the date — always SAFE."""
    for column in CALENDAR_COLUMNS:
        assert feature_safety(column) is FeatureSafety.SAFE


def test_lag_columns_are_CONDITIONALLY_SAFE() -> None:
    """Target long-lag columns — including custom offsets — are conditionally safe."""
    for lag in EXOGENOUS_LAGS:
        assert feature_safety(f"lag_{lag}") is FeatureSafety.CONDITIONALLY_SAFE
    # A custom lag offset not literally in FEATURE_CLASS still classifies.
    assert feature_safety("lag_3") is FeatureSafety.CONDITIONALLY_SAFE


def test_exogenous_price_and_promo_are_unsafe_unless_supplied() -> None:
    """Future price / promotion inputs are knowable only when posited."""
    assert feature_safety("price_factor") is FeatureSafety.UNSAFE_UNLESS_SUPPLIED
    assert feature_safety("promo_active") is FeatureSafety.UNSAFE_UNLESS_SUPPLIED


def test_feature_safety_rejects_an_unclassified_column() -> None:
    """A genuinely unknown column raises — callers must classify every column."""
    try:
        feature_safety("mystery_feature")
    except KeyError:
        pass
    else:
        raise AssertionError("feature_safety must raise KeyError for an unknown column")


# --- FutureFeatureFrame dataclass ---------------------------------------------


def test_future_feature_frame_dataclass_shape() -> None:
    """FutureFeatureFrame carries dates, feature_columns, and a row-major matrix."""
    columns = canonical_feature_columns()
    frame = FutureFeatureFrame(
        dates=list(_HORIZON_DATES),
        feature_columns=columns,
        matrix=[[0.0] * len(columns) for _ in _HORIZON_DATES],
    )
    assert frame.dates == _HORIZON_DATES
    assert frame.feature_columns == columns
    assert len(frame.matrix) == _HORIZON
    assert all(len(row) == len(columns) for row in frame.matrix)


# --- builder determinism ------------------------------------------------------


def test_build_calendar_columns_is_deterministic() -> None:
    """Calendar columns depend only on the dates — two calls match exactly."""
    first = build_calendar_columns(_HORIZON_DATES)
    second = build_calendar_columns(list(_HORIZON_DATES))
    assert first == second
    assert set(first) == set(CALENDAR_COLUMNS)
    for values in first.values():
        assert len(values) == _HORIZON


# --- architectural invariant --------------------------------------------------


def test_shared_package_imports_nothing_from_features() -> None:
    """``app/shared/**`` is leaf-level — it may never import a vertical slice.

    Walks every ``.py`` file in the package and asserts no module imports a
    name under ``app.features`` (AGENTS.md § Architecture).
    """
    pkg_dir = Path(__file__).resolve().parents[1]  # app/shared/feature_frames/
    for py_file in pkg_dir.rglob("*.py"):
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
