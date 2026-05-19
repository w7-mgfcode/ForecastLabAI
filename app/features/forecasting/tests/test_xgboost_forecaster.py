"""Unit tests for ``XGBoostForecaster`` (PRP-MLZOO-C1).

The XGBoost forecaster is the second ADVANCED feature-aware tree model and a
structural twin of ``LightGBMForecaster``. Like ``RegressionForecaster`` it
*consumes* the exogenous ``X`` argument, so these tests mirror that contract:
``X`` is required, its shape is validated, fits are deterministic, and ``NaN``
features are tolerated (XGBoost handles missing values natively via
``missing=np.nan``).

The whole module SKIPs (never ERRORs) when the optional ``ml-xgboost``
dependency is absent — ``pytest.importorskip``. Importing ``XGBoostForecaster``
itself is leak-free (``xgboost`` is imported lazily inside ``fit``), so the
class import sits with the other module imports; the ``importorskip`` guard
fires only because every test below actually fits a model.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.features.forecasting.models import XGBoostForecaster, model_factory
from app.features.forecasting.schemas import XGBoostModelConfig

pytest.importorskip("xgboost")

FloatArray = np.ndarray[Any, np.dtype[np.floating[Any]]]


def _synthetic_data(
    n: int = 120, n_features: int = 6, seed: int = 0
) -> tuple[FloatArray, FloatArray]:
    """Build a synthetic feature matrix and a target that depends on it."""
    rng = np.random.default_rng(seed)
    features = rng.normal(size=(n, n_features))
    target = 50.0 + 5.0 * features[:, 0] - 3.0 * features[:, 1] + rng.normal(scale=0.5, size=n)
    return features.astype(np.float64), target.astype(np.float64)


def test_fit_predict_roundtrip() -> None:
    """A fitted XGBoost model produces a finite forecast of horizon length."""
    features, target = _synthetic_data()
    model = XGBoostForecaster()
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
        XGBoostForecaster().fit(target, None)


def test_fit_rejects_mismatched_rows() -> None:
    """``fit`` raises when feature and target row counts differ."""
    features, target = _synthetic_data()
    with pytest.raises(ValueError, match="rows must match"):
        XGBoostForecaster().fit(target, features[:-5])


def test_predict_rejects_none_features() -> None:
    """``predict`` raises when no exogenous features are supplied."""
    features, target = _synthetic_data()
    model = XGBoostForecaster().fit(target, features)
    with pytest.raises(ValueError, match="requires exogenous features"):
        model.predict(5, None)


def test_predict_rejects_wrong_shape_features() -> None:
    """``predict`` raises when the feature row count is not the horizon."""
    features, target = _synthetic_data()
    model = XGBoostForecaster().fit(target, features)
    with pytest.raises(ValueError, match="horizon"):
        model.predict(5, features[:8])


def test_predict_before_fit_raises() -> None:
    """``predict`` raises a RuntimeError before the model is fitted."""
    model = XGBoostForecaster()
    with pytest.raises(RuntimeError, match="fitted"):
        model.predict(5, np.zeros((5, 3), dtype=np.float64))


def test_determinism_same_random_state() -> None:
    """Two fits with the same random_state yield identical forecasts.

    XGBoost has no ``deterministic`` switch (unlike LightGBM). Bit-
    reproducibility comes from ``n_jobs=1`` + ``tree_method="hist"`` + a fixed
    ``random_state`` + the conservative config leaving ``subsample`` /
    ``colsample_bytree`` at their ``1.0`` defaults — all pinned in ``fit`` — so
    an EXACT ``assert_array_equal`` within one environment is the correct gate.
    """
    features, target = _synthetic_data()
    future = features[:12]
    first = XGBoostForecaster(random_state=7).fit(target, features)
    second = XGBoostForecaster(random_state=7).fit(target, features)
    np.testing.assert_array_equal(first.predict(12, future), second.predict(12, future))


def test_handles_nan_features() -> None:
    """``XGBRegressor`` tolerates NaN feature cells natively."""
    features, target = _synthetic_data()
    model = XGBoostForecaster().fit(target, features)
    future = features[:6].copy()
    future[2, 0] = np.nan  # the future frame emits NaN for un-resolvable lags
    predictions = model.predict(6, future)
    assert bool(np.all(np.isfinite(predictions)))


def test_get_and_set_params() -> None:
    """``get_params`` reflects construction; ``set_params`` mutates in place."""
    model = XGBoostForecaster(n_estimators=150, learning_rate=0.03, max_depth=4)
    params = model.get_params()
    assert params["n_estimators"] == 150
    assert params["learning_rate"] == 0.03
    assert params["max_depth"] == 4
    model.set_params(max_depth=9)
    assert model.max_depth == 9


def test_requires_features_is_true() -> None:
    """XGBoost is a feature-aware model — the ClassVar is True."""
    assert XGBoostForecaster.requires_features is True


def test_model_factory_creates_xgboost_forecaster() -> None:
    """``model_factory`` dispatches an XGBoostModelConfig when the flag is on."""
    enabled = MagicMock()
    enabled.forecast_enable_xgboost = True
    with patch("app.core.config.get_settings", return_value=enabled):
        model = model_factory(XGBoostModelConfig(n_estimators=120), random_state=42)
    assert isinstance(model, XGBoostForecaster)
    assert model.n_estimators == 120
    assert model.random_state == 42
