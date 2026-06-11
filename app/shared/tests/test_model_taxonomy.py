"""Tests for the shared model-family taxonomy (#268).

Locks the canonical mapping, the back-compat re-export identity across the
legacy forecasting import paths, the JSON-schema contract on
``RunResponse.model_family``, and — the spec for this bug class — fresh-
interpreter cold-boot probes. pytest's in-process import order masks
cross-slice import cycles (forecasting usually loads before registry), so a
subprocess importing registry FIRST (the ``alembic/env.py`` shape) is the
only honest in-suite check.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from app.shared.model_taxonomy import ModelFamily, model_family_for

# ---------------------------------------------------------------------------
# model_family_for — canonical mapping (mirrors the legacy suite in
# app/features/forecasting/tests/test_feature_metadata.py, via the new path)
# ---------------------------------------------------------------------------


def test_model_family_for_maps_baseline_types_to_baseline() -> None:
    for mt in (
        "naive",
        "seasonal_naive",
        "moving_average",
        "weighted_moving_average",
        "seasonal_average",
    ):
        assert model_family_for(mt) == ModelFamily.BASELINE


def test_model_family_for_maps_tree_types_to_tree() -> None:
    for mt in ("regression", "lightgbm", "xgboost", "random_forest"):
        assert model_family_for(mt) == ModelFamily.TREE


def test_model_family_for_maps_additive_types_to_additive() -> None:
    for mt in ("prophet_like", "trend_regression_baseline"):
        assert model_family_for(mt) == ModelFamily.ADDITIVE


def test_model_family_for_unknown_returns_baseline() -> None:
    """An unknown model_type logs a warning and degrades to BASELINE."""
    assert model_family_for("future_arima_v9") == ModelFamily.BASELINE


# ---------------------------------------------------------------------------
# Back-compat re-exports — OBJECT IDENTITY across the legacy paths (#268).
# Enum members are str-valued, so == would pass even across distinct class
# objects; the `is` checks in forecasting/service.py demand identity.
# ---------------------------------------------------------------------------


def test_legacy_import_paths_return_the_same_objects() -> None:
    from app.features.forecasting.feature_metadata import (
        ModelFamily as FMetaMF,
    )
    from app.features.forecasting.feature_metadata import (
        model_family_for as legacy_fn,
    )
    from app.features.forecasting.schemas import ModelFamily as SchemasMF

    assert SchemasMF is ModelFamily
    assert FMetaMF is ModelFamily
    assert legacy_fn is model_family_for


# ---------------------------------------------------------------------------
# JSON-schema lock — the move is contract-invariant (title from the class
# name, members from the values; both unchanged by relocation).
# ---------------------------------------------------------------------------


def test_run_response_model_family_json_schema_unchanged() -> None:
    from app.features.registry.schemas import RunResponse

    schema = RunResponse.model_json_schema(mode="serialization")
    definition = schema["$defs"]["ModelFamily"]
    assert definition["title"] == "ModelFamily"
    assert definition["enum"] == ["baseline", "tree", "additive"]


# ---------------------------------------------------------------------------
# Cold-boot probes — fresh interpreters, worst-case entry orders. The
# alembic-shape probe (registry first) is the one that crashed at PRP-31.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stmt",
    [
        "from app.features.registry import models",  # alembic env.py shape
        "import app.features.forecasting",  # forecasting-first entry
        "import app.main",  # full wiring
    ],
)
def test_cold_boot_import_probe(stmt: str) -> None:
    result = subprocess.run(  # noqa: S603 — internal command, trusted args
        [sys.executable, "-c", stmt],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
