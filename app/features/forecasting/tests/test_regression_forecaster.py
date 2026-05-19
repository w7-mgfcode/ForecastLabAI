"""Unit tests for ``RegressionForecaster`` (PRP-27 Phase B).

The regression forecaster is the first model that *consumes* the exogenous
``X`` argument, so these tests focus on the new contract: ``X`` is required,
its shape is validated, fits are deterministic, and ``NaN`` features are
tolerated (the future feature frame deliberately emits ``NaN`` cells).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from app.features.forecasting.models import RegressionForecaster, model_factory
from app.features.forecasting.schemas import RegressionModelConfig

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
    """A fitted regression model produces a finite forecast of horizon length."""
    features, target = _synthetic_data()
    model = RegressionForecaster()
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
        RegressionForecaster().fit(target, None)


def test_fit_rejects_mismatched_rows() -> None:
    """``fit`` raises when feature and target row counts differ."""
    features, target = _synthetic_data()
    with pytest.raises(ValueError, match="rows must match"):
        RegressionForecaster().fit(target, features[:-5])


def test_predict_rejects_none_features() -> None:
    """``predict`` raises when no exogenous features are supplied."""
    features, target = _synthetic_data()
    model = RegressionForecaster().fit(target, features)
    with pytest.raises(ValueError, match="requires exogenous features"):
        model.predict(5, None)


def test_predict_rejects_wrong_shape_features() -> None:
    """``predict`` raises when the feature row count is not the horizon."""
    features, target = _synthetic_data()
    model = RegressionForecaster().fit(target, features)
    with pytest.raises(ValueError, match="horizon"):
        model.predict(5, features[:8])


def test_predict_before_fit_raises() -> None:
    """``predict`` raises a RuntimeError before the model is fitted."""
    model = RegressionForecaster()
    with pytest.raises(RuntimeError, match="fitted"):
        model.predict(5, np.zeros((5, 3), dtype=np.float64))


def test_determinism_same_random_state() -> None:
    """Two fits with the same random_state yield identical forecasts."""
    features, target = _synthetic_data()
    future = features[:12]
    first = RegressionForecaster(random_state=7).fit(target, features)
    second = RegressionForecaster(random_state=7).fit(target, features)
    np.testing.assert_array_equal(first.predict(12, future), second.predict(12, future))


def test_handles_nan_features() -> None:
    """``HistGradientBoostingRegressor`` tolerates NaN feature cells natively."""
    features, target = _synthetic_data()
    model = RegressionForecaster().fit(target, features)
    future = features[:6].copy()
    future[2, 0] = np.nan  # the future frame emits NaN for un-resolvable lags
    predictions = model.predict(6, future)
    assert bool(np.all(np.isfinite(predictions)))


def test_get_and_set_params() -> None:
    """``get_params`` reflects construction; ``set_params`` mutates in place."""
    model = RegressionForecaster(max_iter=150, learning_rate=0.03, max_depth=4)
    params = model.get_params()
    assert params["max_iter"] == 150
    assert params["learning_rate"] == 0.03
    assert params["max_depth"] == 4
    model.set_params(max_depth=9)
    assert model.max_depth == 9


def test_model_factory_creates_regression_forecaster() -> None:
    """``model_factory`` dispatches a RegressionModelConfig to the right class."""
    model = model_factory(RegressionModelConfig(max_iter=120), random_state=42)
    assert isinstance(model, RegressionForecaster)
    assert model.max_iter == 120
