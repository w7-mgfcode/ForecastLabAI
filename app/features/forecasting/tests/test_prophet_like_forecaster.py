"""Unit tests for ``ProphetLikeForecaster`` (PRP-MLZOO-C2).

The Prophet-like forecaster is a deterministic, regularized ADDITIVE linear
model — a ``Ridge`` over the canonical 14-column feature frame, fronted by a
``SimpleImputer`` so the ``NaN`` lag cells the future frame emits do not raise.

These tests cover the shared feature-aware contract (``X`` required, shape
validated, deterministic fits) PLUS the model-specific invariants the tree
models do not have: the additive decomposition invariant, NaN tolerance via
the imputer, and the imputer's leakage-safety (medians learned on train ``X``
only). Pure scikit-learn — no ``importorskip``, this file always runs.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from app.features.forecasting.models import ProphetLikeForecaster, model_factory
from app.features.forecasting.schemas import ProphetLikeModelConfig
from app.shared.feature_frames import canonical_feature_columns

FloatArray = np.ndarray[Any, np.dtype[np.floating[Any]]]

# The canonical contract is exactly 14 wide — the decompose() component
# grouping partitions these 14 columns, so the synthetic frame must match.
_N_FEATURES = len(canonical_feature_columns())  # 14


def _synthetic_data(
    n: int = 120, n_features: int = _N_FEATURES, seed: int = 0
) -> tuple[FloatArray, FloatArray]:
    """Build a synthetic feature matrix and a target that depends on it.

    Defaults to the canonical 14-column width so the decomposition tests line
    up with ``canonical_feature_columns()``.
    """
    rng = np.random.default_rng(seed)
    features = rng.normal(size=(n, n_features))
    target = 50.0 + 5.0 * features[:, 0] - 3.0 * features[:, 1] + rng.normal(scale=0.5, size=n)
    return features.astype(np.float64), target.astype(np.float64)


# ---------------------------------------------------------------------------
# Shared feature-aware contract tests
# ---------------------------------------------------------------------------


def test_fit_predict_roundtrip() -> None:
    """A fitted Prophet-like model produces a finite forecast of horizon length."""
    features, target = _synthetic_data()
    model = ProphetLikeForecaster()
    model.fit(target, features)
    assert model.is_fitted

    horizon = 10
    predictions = model.predict(horizon, features[:horizon])
    assert predictions.shape == (horizon,)
    assert bool(np.all(np.isfinite(predictions)))


def test_fit_rejects_none_features() -> None:
    """``fit`` raises when no exogenous features are supplied."""
    _, target = _synthetic_data()
    with pytest.raises(ValueError, match="requires exogenous features"):
        ProphetLikeForecaster().fit(target, None)


def test_fit_rejects_mismatched_rows() -> None:
    """``fit`` raises when feature and target row counts differ."""
    features, target = _synthetic_data()
    with pytest.raises(ValueError, match="rows must match"):
        ProphetLikeForecaster().fit(target, features[:-5])


def test_predict_rejects_none_features() -> None:
    """``predict`` raises when no exogenous features are supplied."""
    features, target = _synthetic_data()
    model = ProphetLikeForecaster().fit(target, features)
    with pytest.raises(ValueError, match="requires exogenous features"):
        model.predict(5, None)


def test_predict_rejects_wrong_shape_features() -> None:
    """``predict`` raises when the feature row count is not the horizon."""
    features, target = _synthetic_data()
    model = ProphetLikeForecaster().fit(target, features)
    with pytest.raises(ValueError, match="horizon"):
        model.predict(5, features[:8])


def test_predict_before_fit_raises() -> None:
    """``predict`` raises a RuntimeError before the model is fitted."""
    model = ProphetLikeForecaster()
    with pytest.raises(RuntimeError, match="fitted"):
        model.predict(5, np.zeros((5, _N_FEATURES), dtype=np.float64))


def test_determinism_same_data() -> None:
    """Two fits on the same data yield identical forecasts.

    ``Ridge(solver="cholesky")`` is closed-form and ``SimpleImputer(median)``
    is deterministic, so the whole pipeline is bit-reproducible.
    """
    features, target = _synthetic_data()
    future = features[:12]
    first = ProphetLikeForecaster(alpha=1.0).fit(target, features)
    second = ProphetLikeForecaster(alpha=1.0).fit(target, features)
    np.testing.assert_array_equal(first.predict(12, future), second.predict(12, future))


def test_get_and_set_params() -> None:
    """``get_params`` reflects construction; ``set_params`` mutates in place."""
    model = ProphetLikeForecaster(alpha=2.5)
    params = model.get_params()
    assert params["alpha"] == 2.5
    assert params["random_state"] == 42
    model.set_params(alpha=0.1)
    assert model.alpha == 0.1


def test_requires_features_is_true() -> None:
    """The Prophet-like model is feature-aware — the ClassVar is True."""
    assert ProphetLikeForecaster.requires_features is True


def test_model_factory_creates_prophet_like_forecaster() -> None:
    """``model_factory`` dispatches a ProphetLikeModelConfig with NO flag gate."""
    model = model_factory(ProphetLikeModelConfig(alpha=3.0), random_state=42)
    assert isinstance(model, ProphetLikeForecaster)
    assert model.alpha == 3.0


# ---------------------------------------------------------------------------
# Model-specific tests — additive decomposition, NaN tolerance, leakage
# ---------------------------------------------------------------------------


def test_handles_nan_features() -> None:
    """A future frame with NaN lag cells predicts finite values.

    The ``SimpleImputer`` fills the NaN cells — a bare ``Ridge`` would raise
    ``ValueError: Input contains NaN``.
    """
    features, target = _synthetic_data()
    model = ProphetLikeForecaster().fit(target, features)
    future = features[:6].copy()
    future[2, 0] = np.nan  # the future frame emits NaN for un-resolvable lags
    predictions = model.predict(6, future)
    assert bool(np.all(np.isfinite(predictions)))


def test_additive_invariant() -> None:
    """``decompose()``'s four parts sum (rtol 1e-9) to ``predict()``.

    This is what makes the model "Prophet-like": the forecast genuinely IS the
    sum of its trend / seasonality / holiday-regressor components.
    """
    features, target = _synthetic_data()
    model = ProphetLikeForecaster(alpha=1.0).fit(target, features)
    horizon = 12
    future = features[:horizon]
    d = model.decompose(future)
    reconstructed = d.intercept + d.trend + d.seasonality + d.holiday_regressor
    np.testing.assert_allclose(reconstructed, model.predict(horizon, future), rtol=1e-9)


def test_decompose_components_have_horizon_length() -> None:
    """Each decomposition component array has shape (len(X),)."""
    features, target = _synthetic_data()
    model = ProphetLikeForecaster().fit(target, features)
    horizon = 9
    d = model.decompose(features[:horizon])
    assert d.trend.shape == (horizon,)
    assert d.seasonality.shape == (horizon,)
    assert d.holiday_regressor.shape == (horizon,)
    assert isinstance(d.intercept, float)


def test_decompose_uses_trained_imputer_statistics() -> None:
    """``decompose()`` imputes future NaN with the TRAINING-window median.

    The imputed X must equal the trained imputer's ``transform`` of the future
    frame — never a fresh imputer fitted on the future window (which would
    leak future statistics).
    """
    features, target = _synthetic_data()
    model = ProphetLikeForecaster().fit(target, features)
    future = features[:6].copy()
    future[2, 0] = np.nan

    imputer = model._estimator.named_steps["impute"]
    expected_imputed = imputer.transform(future)
    ridge = model._estimator.named_steps["ridge"]
    coef = np.asarray(ridge.coef_, dtype=np.float64)
    columns = canonical_feature_columns()

    # The trend component includes lag_1 (column 0) — the NaN cell. Recompute
    # its contribution from the trained-imputer transform and assert decompose
    # produced exactly that (i.e. it used the trained medians, not new ones).
    trend_idx = [
        columns.index(c) for c in ("lag_1", "lag_7", "lag_14", "lag_28", "days_since_launch")
    ]
    expected_trend = expected_imputed[:, trend_idx] @ coef[trend_idx]

    d = model.decompose(future)
    np.testing.assert_allclose(d.trend, expected_trend, rtol=1e-12)
    # And the imputed lag_1 cell is the training median, not NaN.
    assert np.isfinite(expected_imputed[2, 0])


def test_decompose_before_fit_raises() -> None:
    """``decompose()`` raises a RuntimeError before the model is fitted."""
    model = ProphetLikeForecaster()
    with pytest.raises(RuntimeError, match="fitted"):
        model.decompose(np.zeros((5, _N_FEATURES), dtype=np.float64))
