"""Unit tests for the feature-importance extractor (MLZOO-D / PRP-31).

These tests fit small, deterministic instances of every feature-aware
forecaster, then assert the extractor returns a sorted, well-shaped
:class:`FeatureImportanceItem` list. The LightGBM and XGBoost tests guard the
optional extras via ``pytest.importorskip`` so the file always runs on a
minimal install — the RegressionForecaster and ProphetLikeForecaster paths
have no optional dependency.

The leakage spec ``app/features/featuresets/tests/test_leakage.py`` is the
hard invariant; nothing here touches it.
"""

from __future__ import annotations

from typing import Any, cast, get_args

import numpy as np
import pytest

from app.features.forecasting.feature_metadata import (
    _MODEL_FAMILY_MAP,
    FeatureImportanceUnavailableError,
    extract_feature_importance,
    importance_type_for,
    model_family_for,
)
from app.features.forecasting.models import (
    BaseForecaster,
    LightGBMForecaster,
    ModelType,
    MovingAverageForecaster,
    NaiveForecaster,
    ProphetLikeForecaster,
    RegressionForecaster,
    SeasonalNaiveForecaster,
    XGBoostForecaster,
)
from app.features.forecasting.schemas import ModelFamily
from app.shared.feature_frames import canonical_feature_columns

FloatArray = np.ndarray[Any, np.dtype[np.floating[Any]]]

_N_FEATURES = len(canonical_feature_columns())  # 14


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


def _synthetic_data(
    n: int = 120, n_features: int = _N_FEATURES, seed: int = 0
) -> tuple[FloatArray, FloatArray]:
    """Build a synthetic (target, feature-matrix) pair with a couple of
    informative columns so the importance vector is not all zero."""
    rng = np.random.default_rng(seed)
    features = rng.normal(size=(n, n_features)).astype(np.float64)
    # Mix signed coefficients so the prophet_like coef_ vector has both signs
    target = (
        50.0
        + 5.0 * features[:, 0]
        - 3.0 * features[:, 1]
        + 2.0 * features[:, 5]
        + rng.normal(scale=0.5, size=n)
    ).astype(np.float64)
    return features, target


def _feature_columns() -> list[str]:
    return list(canonical_feature_columns())


# ---------------------------------------------------------------------------
# model_family_for
# ---------------------------------------------------------------------------


def test_model_family_for_maps_baseline_types_to_baseline() -> None:
    for mt in ("naive", "seasonal_naive", "moving_average"):
        assert model_family_for(mt) == ModelFamily.BASELINE


def test_model_family_for_maps_tree_types_to_tree() -> None:
    for mt in ("regression", "lightgbm", "xgboost"):
        assert model_family_for(mt) == ModelFamily.TREE


def test_model_family_for_maps_prophet_like_to_additive() -> None:
    assert model_family_for("prophet_like") == ModelFamily.ADDITIVE


def test_model_family_for_unknown_returns_baseline() -> None:
    """An unknown model_type logs a warning and degrades to BASELINE."""
    assert model_family_for("future_arima_v9") == ModelFamily.BASELINE


def test_model_family_map_covers_every_known_model_type() -> None:
    """Every Literal in ``ModelType`` is reachable in the family map.

    Catches drift: if a new model type is added to ``forecasting/models.py``
    without updating ``_MODEL_FAMILY_MAP``, this fails immediately and the
    dashboard would otherwise silently classify it as BASELINE.
    """
    declared = set(get_args(ModelType))
    assert declared <= set(_MODEL_FAMILY_MAP.keys()), (
        f"ModelType declares {declared - set(_MODEL_FAMILY_MAP.keys())} "
        "but _MODEL_FAMILY_MAP doesn't"
    )


# ---------------------------------------------------------------------------
# importance_type_for
# ---------------------------------------------------------------------------


def test_importance_type_for_regression_is_permutation() -> None:
    features, target = _synthetic_data()
    model = RegressionForecaster().fit(target, features)
    assert importance_type_for(model) == "permutation"


def test_importance_type_for_prophet_like_is_ridge_coef() -> None:
    features, target = _synthetic_data()
    model = ProphetLikeForecaster().fit(target, features)
    assert importance_type_for(model) == "ridge_coef"


def test_importance_type_for_baseline_is_none() -> None:
    """Baselines are not feature-aware; the function returns None for them."""
    naive = NaiveForecaster()
    seasonal = SeasonalNaiveForecaster()
    ma = MovingAverageForecaster()
    for m in (naive, seasonal, ma):
        assert importance_type_for(cast(BaseForecaster, m)) is None


@pytest.mark.parametrize("extra", ["lightgbm", "xgboost"])
def test_importance_type_for_tree_extras(extra: str) -> None:
    """LGBM / XGBoost expose ``importance_type``; XGB falls back to 'weight'.

    LightGBM's sklearn wrapper sets ``importance_type='split'`` by default.
    XGBoost's wrapper exposes ``importance_type=None`` on a freshly-built
    estimator (the internal default is ``'weight'``), so the helper falls
    back to the documented XGBoost default rather than returning ``None``.
    """
    pytest.importorskip(extra)
    features, target = _synthetic_data()
    model: BaseForecaster
    expected_default: str
    if extra == "lightgbm":
        model = LightGBMForecaster().fit(target, features)
        expected_default = "split"
    else:
        model = XGBoostForecaster().fit(target, features)
        expected_default = "weight"
    kind = importance_type_for(model)
    assert kind == expected_default


# ---------------------------------------------------------------------------
# extract_feature_importance — happy paths
# ---------------------------------------------------------------------------


def test_extract_regression_raises_unavailable() -> None:
    """HistGradientBoostingRegressor does not expose ``feature_importances_``.

    Unlike the older ``GradientBoostingRegressor``, the histogram-based booster
    sklearn 1.x ships does not implement the attribute. The extractor surfaces
    this as :class:`FeatureImportanceUnavailableError` (a ``ValueError``
    subclass) so the service layer can map it to a 422 with a clear
    remediation hint, rather than letting an opaque AttributeError reach the
    handler.
    """
    features, target = _synthetic_data()
    model = RegressionForecaster().fit(target, features)
    with pytest.raises(
        FeatureImportanceUnavailableError,
        match="HistGradientBoostingRegressor",
    ):
        extract_feature_importance(model, _feature_columns())


def test_extract_prophet_like_preserves_sign() -> None:
    """Ridge coefficients can be negative; the extractor must preserve sign."""
    features, target = _synthetic_data()
    model = ProphetLikeForecaster().fit(target, features)
    items = extract_feature_importance(model, _feature_columns())

    assert len(items) == _N_FEATURES
    assert all(item.kind == "linear_coef" for item in items)
    # At least one negative coefficient must exist for a target with negative
    # weight on feature index 1; if not, the extractor probably called abs().
    assert any(item.importance < 0.0 for item in items), (
        "Expected at least one negative coefficient; sign was probably stripped"
    )
    # Sorted by |importance| desc.
    abs_seq = [abs(item.importance) for item in items]
    assert abs_seq == sorted(abs_seq, reverse=True)
    # Ranks are 1-indexed and monotonic.
    assert [item.rank for item in items] == list(range(1, _N_FEATURES + 1))


@pytest.mark.parametrize("extra", ["lightgbm", "xgboost"])
def test_extract_tree_models_match_feature_columns(extra: str) -> None:
    """LightGBM / XGBoost extractors are guarded by ``importorskip``."""
    pytest.importorskip(extra)
    features, target = _synthetic_data()
    model: BaseForecaster
    if extra == "lightgbm":
        model = LightGBMForecaster().fit(target, features)
    else:
        model = XGBoostForecaster().fit(target, features)

    items = extract_feature_importance(model, _feature_columns())
    assert len(items) == _N_FEATURES
    assert all(item.kind == "tree" for item in items)
    assert all(item.importance >= 0.0 for item in items)
    abs_seq = [abs(item.importance) for item in items]
    assert abs_seq == sorted(abs_seq, reverse=True)


# ---------------------------------------------------------------------------
# extract_feature_importance — error paths
# ---------------------------------------------------------------------------


def test_extract_raises_on_non_feature_aware_model() -> None:
    """Baseline forecasters are explicitly rejected with a clear message."""
    naive = NaiveForecaster()
    with pytest.raises(ValueError, match="not feature-aware"):
        extract_feature_importance(cast(BaseForecaster, naive), _feature_columns())


def test_extract_raises_on_feature_column_length_mismatch() -> None:
    """The length-mismatch guard fires for an estimator that DOES expose
    ``feature_importances_`` (ProphetLike here — RegressionForecaster fails
    earlier with FeatureImportanceUnavailableError)."""
    features, target = _synthetic_data()
    model = ProphetLikeForecaster().fit(target, features)
    short_cols = _feature_columns()[:-3]
    with pytest.raises(ValueError, match="length mismatch"):
        extract_feature_importance(model, short_cols)


def test_extract_prophet_like_pads_dropped_imputer_columns() -> None:
    """Regression test for the SimpleImputer-drops-empty-column edge case.

    sklearn 1.2+'s ``SimpleImputer`` (default ``keep_empty_features=False``)
    drops columns whose training values are all NaN. In production this
    fires whenever ``days_since_launch`` has no launch date — the imputer
    silently strips column index 13 and Ridge learns a shape-(13,) coef.
    The extractor must realign the coef vector to the full 14-column
    input contract by padding the dropped column with 0.0; otherwise the
    response 400s with a misleading "length mismatch" message.
    """
    features, target = _synthetic_data()
    features[:, 13] = np.nan  # mark the last column as all-NaN
    model = ProphetLikeForecaster().fit(target, features)
    items = extract_feature_importance(model, _feature_columns())
    # The padded result preserves the full input contract.
    assert len(items) == _N_FEATURES
    # The dropped column appears with importance == 0 (model assigned no
    # weight because it had no observed values).
    dropped = next(item for item in items if item.name == _feature_columns()[13])
    assert dropped.importance == 0.0
