"""Tests for :class:`RandomForestForecaster` (PRP-36 — optional feature-aware model)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.features.forecasting.models import (
    RandomForestForecaster,
    model_factory,
)
from app.features.forecasting.schemas import RandomForestModelConfig


def _enabled_settings() -> MagicMock:
    """Return a settings mock with the random_forest flag flipped on."""
    s = MagicMock()
    s.forecast_enable_random_forest = True
    s.forecast_enable_lightgbm = False
    s.forecast_enable_xgboost = False
    return s


@pytest.fixture
def small_feature_matrix() -> tuple[np.ndarray, np.ndarray]:
    """Build a deterministic 30-row by 3-column feature matrix + target."""
    rng = np.random.default_rng(seed=42)
    X = rng.standard_normal(size=(30, 3))
    # y is a near-linear function of the features plus a small noise term so
    # the forest has something to fit.
    y = X[:, 0] * 2.0 + X[:, 1] * 0.5 - X[:, 2] + rng.standard_normal(size=30) * 0.1
    return X.astype(np.float64), y.astype(np.float64)


class TestRandomForestForecaster:
    """Behavioural tests for the sklearn-RandomForest feature-aware model."""

    def test_requires_features_true(self) -> None:
        """RandomForestForecaster is the second feature-aware baseline."""
        assert RandomForestForecaster.requires_features is True

    def test_fit_requires_non_none_X(self) -> None:
        """fit() raises when X is None (matches RegressionForecaster contract)."""
        model = RandomForestForecaster(n_estimators=10)
        with pytest.raises(ValueError, match="requires a non-None X"):
            model.fit(np.array([1.0, 2.0, 3.0]), X=None)

    def test_fit_raises_on_row_mismatch(
        self, small_feature_matrix: tuple[np.ndarray, np.ndarray]
    ) -> None:
        """fit() validates X.shape[0] == y.size."""
        X, y = small_feature_matrix
        model = RandomForestForecaster(n_estimators=10)
        with pytest.raises(ValueError, match="row count mismatch"):
            model.fit(y[:-1], X=X)

    def test_predict_requires_non_none_X(
        self, small_feature_matrix: tuple[np.ndarray, np.ndarray]
    ) -> None:
        """predict() raises when X is None (no recursive fallback)."""
        X, y = small_feature_matrix
        model = RandomForestForecaster(n_estimators=10).fit(y, X=X)
        with pytest.raises(ValueError, match="requires a non-None X"):
            model.predict(horizon=5, X=None)

    def test_predict_validates_column_count(
        self, small_feature_matrix: tuple[np.ndarray, np.ndarray]
    ) -> None:
        """predict() validates X.shape[1] against the trained column count."""
        X, y = small_feature_matrix
        model = RandomForestForecaster(n_estimators=10).fit(y, X=X)
        with pytest.raises(ValueError, match="column count mismatch"):
            model.predict(horizon=2, X=X[:2, :-1])

    def test_predict_before_fit_raises(self) -> None:
        """predict() before fit() raises RuntimeError."""
        with pytest.raises(RuntimeError, match="must be fitted"):
            RandomForestForecaster().predict(horizon=5, X=np.array([[1.0, 2.0]]))

    def test_predict_shape(self, small_feature_matrix: tuple[np.ndarray, np.ndarray]) -> None:
        """predict() returns one forecast per row of the future X."""
        X, y = small_feature_matrix
        model = RandomForestForecaster(n_estimators=10).fit(y, X=X)
        future_X = X[:5]
        forecasts = model.predict(horizon=5, X=future_X)
        assert forecasts.shape == (5,)

    def test_deterministic_with_seed(
        self, small_feature_matrix: tuple[np.ndarray, np.ndarray]
    ) -> None:
        """random_state + n_jobs=1 give byte-identical predictions."""
        X, y = small_feature_matrix
        a = RandomForestForecaster(n_estimators=10, random_state=42).fit(y, X=X)
        b = RandomForestForecaster(n_estimators=10, random_state=42).fit(y, X=X)
        np.testing.assert_array_equal(a.predict(horizon=5, X=X[:5]), b.predict(horizon=5, X=X[:5]))

    def test_feature_importances_shape_matches_feature_columns(
        self, small_feature_matrix: tuple[np.ndarray, np.ndarray]
    ) -> None:
        """The wrapped estimator exposes a 1-D importance vector of width n_features."""
        X, y = small_feature_matrix
        model = RandomForestForecaster(n_estimators=10).fit(y, X=X)
        importances = model._estimator.feature_importances_
        assert importances.ndim == 1
        assert importances.shape == (X.shape[1],)

    def test_factory_gate_blocks_when_flag_off(self) -> None:
        """model_factory refuses to dispatch random_forest when the flag is off."""
        disabled = MagicMock()
        disabled.forecast_enable_random_forest = False
        with patch("app.core.config.get_settings", return_value=disabled):
            with pytest.raises(ValueError, match="random_forest is not enabled"):
                model_factory(RandomForestModelConfig(n_estimators=10), random_state=42)

    def test_factory_creates_random_forest_when_enabled(self) -> None:
        """model_factory dispatches the forecaster when the flag is on."""
        with patch("app.core.config.get_settings", return_value=_enabled_settings()):
            model = model_factory(
                RandomForestModelConfig(n_estimators=50, max_depth=8, min_samples_leaf=3),
                random_state=42,
            )
        assert isinstance(model, RandomForestForecaster)
        assert model.n_estimators == 50
        assert model.max_depth == 8
        assert model.min_samples_leaf == 3
        assert model.random_state == 42

    def test_invalid_n_estimators_raises(self) -> None:
        """n_estimators < 1 surfaces a clear error."""
        with pytest.raises(ValueError, match="n_estimators"):
            RandomForestForecaster(n_estimators=0)

    def test_invalid_max_depth_raises(self) -> None:
        """max_depth below the minimum surfaces a clear error."""
        with pytest.raises(ValueError, match="max_depth"):
            RandomForestForecaster(max_depth=0)

    def test_invalid_min_samples_leaf_raises(self) -> None:
        """min_samples_leaf < 1 surfaces a clear error (rounds out the validation branches)."""
        with pytest.raises(ValueError, match="min_samples_leaf"):
            RandomForestForecaster(min_samples_leaf=0)
