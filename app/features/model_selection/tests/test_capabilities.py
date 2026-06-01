"""Unit tests for the pure model-capability catalog (issue #356, Slice A).

No DB, no I/O — exercises ``build_model_catalog`` directly, mirroring
``test_ranking.py``. These pin the BACKEND-OWNED capability contract the
frontend consumes read-only.
"""

from __future__ import annotations

import typing

from app.features.model_selection.capabilities import (
    DEFAULT_CANDIDATE_MODEL_TYPES,
    build_model_catalog,
)
from app.features.model_selection.schemas import ModelType

_EXPECTED_MODEL_TYPES = set(typing.get_args(ModelType))


def test_catalog_model_types_match_literal() -> None:
    """The catalog covers EXACTLY the ``ModelType`` Literal — no drift."""
    catalog = build_model_catalog()
    catalog_types = {m.model_type for m in catalog.models}
    assert catalog_types == _EXPECTED_MODEL_TYPES
    # 11 models, no duplicates.
    assert len(catalog.models) == len(_EXPECTED_MODEL_TYPES) == 11


def test_catalog_families_are_valid_literals() -> None:
    """Every family is one of the three lowercase literals from forecasting."""
    catalog = build_model_catalog()
    for model in catalog.models:
        assert model.family in {"baseline", "tree", "additive"}


def test_requires_extra_flags_lightgbm_xgboost_only() -> None:
    """Only the opt-in extras (lightgbm/xgboost) carry requires_extra=True."""
    catalog = build_model_catalog()
    extras = {m.model_type for m in catalog.models if m.requires_extra}
    assert extras == {"lightgbm", "xgboost"}


def test_feature_aware_set_matches_predict_reject_set() -> None:
    """feature_aware == the forecasters with requires_features=True."""
    catalog = build_model_catalog()
    feature_aware = {m.model_type for m in catalog.models if m.feature_aware}
    assert feature_aware == {
        "regression",
        "prophet_like",
        "lightgbm",
        "xgboost",
        "random_forest",
    }


def test_feature_aware_models_do_not_support_auto_predict() -> None:
    """supports_auto_predict is the strict negation of feature_aware."""
    catalog = build_model_catalog()
    for model in catalog.models:
        assert model.supports_auto_predict == (not model.feature_aware)


def test_default_candidate_model_types_are_the_default_five() -> None:
    """The pre-selected defaults match the backend /run contract example."""
    catalog = build_model_catalog()
    assert catalog.default_candidate_model_types == [
        "naive",
        "seasonal_naive",
        "moving_average",
        "regression",
        "prophet_like",
    ]
    # The exported constant and the response agree.
    assert DEFAULT_CANDIDATE_MODEL_TYPES == catalog.default_candidate_model_types
    # Every default is a real catalog entry.
    catalog_types = {m.model_type for m in catalog.models}
    assert set(catalog.default_candidate_model_types) <= catalog_types


def test_default_params_match_forecasting_defaults() -> None:
    """default_params are pinned to the live forecasting ModelConfig defaults."""
    by_type = {m.model_type: m.default_params for m in build_model_catalog().models}
    assert by_type["naive"] == {}
    assert by_type["seasonal_naive"] == {"season_length": 7}
    assert by_type["moving_average"] == {"window_size": 7}
    assert by_type["regression"] == {
        "max_iter": 200,
        "learning_rate": 0.05,
        "max_depth": 6,
    }
    # No internal/meta fields leak into the catalog.
    for params in by_type.values():
        assert "schema_version" not in params
        assert "feature_config_hash" not in params


def test_labels_and_descriptions_are_non_empty() -> None:
    """Each entry carries human-facing label + description copy."""
    for model in build_model_catalog().models:
        assert model.label.strip()
        assert model.description.strip()
