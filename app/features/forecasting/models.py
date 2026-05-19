"""Forecasting models with unified scikit-learn-style interface.

All forecasters implement a common interface:
- fit(y, X=None) -> self
- predict(horizon, X=None) -> np.ndarray
- get_params() -> dict
- set_params(**params) -> self

CRITICAL: All implementations must be deterministic with fixed random_state.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import TYPE_CHECKING, Any, ClassVar, Literal

import numpy as np
from sklearn.ensemble import (  # type: ignore[import-untyped]
    HistGradientBoostingRegressor,
)

if TYPE_CHECKING:
    from app.features.forecasting.schemas import ModelConfig


@dataclass
class FitResult:
    """Result of model fitting.

    Attributes:
        fitted: Whether the model was successfully fitted.
        n_observations: Number of observations used for fitting.
        train_start: Start date of training period.
        train_end: End date of training period.
        metrics: Dictionary of training metrics (e.g., {"train_mae": 1.23}).
    """

    fitted: bool
    n_observations: int
    train_start: date_type
    train_end: date_type
    metrics: dict[str, float] = field(default_factory=lambda: {})


class BaseForecaster(ABC):
    """Abstract base class for all forecasting models.

    CRITICAL: All implementations must be deterministic with fixed random_state.

    Interface follows scikit-learn conventions:
    - fit(y, X=None) -> self
    - predict(horizon, X=None) -> np.ndarray
    - get_params() -> dict
    - set_params(**params) -> self

    Attributes:
        random_state: Random seed for reproducibility.
        requires_features: True when ``fit``/``predict`` require a non-None
            ``X`` feature frame; baseline (target-only) models leave it False.
    """

    requires_features: ClassVar[bool] = False
    """True when ``fit()``/``predict()`` REQUIRE a non-None ``X`` feature frame.

    Baseline (target-only) models leave this ``False``; feature-aware models
    override it to ``True``. ``ForecastingService`` branches on this flag
    rather than an ``isinstance`` check or a ``model_type`` string comparison.
    """

    def __init__(self, random_state: int = 42) -> None:
        """Initialize the forecaster.

        Args:
            random_state: Random seed for reproducibility.
        """
        self.random_state = random_state
        self._is_fitted = False
        self._last_values: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None
        self._fit_result: FitResult | None = None

    @abstractmethod
    def fit(
        self,
        y: np.ndarray[Any, np.dtype[np.floating[Any]]],
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,
    ) -> BaseForecaster:
        """Fit the model on historical data.

        Args:
            y: Target values (1D array of shape [n_samples]).
            X: Optional exogenous features (2D array of shape [n_samples, n_features]).

        Returns:
            self (for method chaining).

        Raises:
            ValueError: If y is empty or has insufficient observations.
        """

    @abstractmethod
    def predict(
        self, horizon: int, X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None
    ) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
        """Generate forecasts for the specified horizon.

        CRITICAL: For recursive forecasting, predictions at t+k become
        inputs for predictions at t+k+1.

        Args:
            horizon: Number of steps to forecast.
            X: Optional exogenous features for forecast period.

        Returns:
            Array of forecasts with shape [horizon].

        Raises:
            RuntimeError: If model has not been fitted.
        """

    @abstractmethod
    def get_params(self) -> dict[str, Any]:
        """Get model parameters (scikit-learn convention).

        Returns:
            Dictionary of parameter names to values.
        """

    @abstractmethod
    def set_params(self, **params: Any) -> BaseForecaster:  # noqa: ANN401
        """Set model parameters (scikit-learn convention).

        Args:
            **params: Parameter names and values to set.

        Returns:
            self (for method chaining).
        """

    @property
    def is_fitted(self) -> bool:
        """Check if the model has been fitted.

        Returns:
            True if fit() has been called successfully.
        """
        return self._is_fitted


class NaiveForecaster(BaseForecaster):
    """Naive forecaster: predicts last observed value for all horizons.

    Formula: y_hat[t+h] = y[t] for all h

    This is the simplest baseline model. It assumes the time series will
    remain constant at its last observed value.
    """

    def __init__(self, random_state: int = 42) -> None:
        """Initialize the naive forecaster.

        Args:
            random_state: Random seed for reproducibility (unused but kept for interface).
        """
        super().__init__(random_state)
        self._last_value: float = 0.0

    def fit(
        self,
        y: np.ndarray[Any, np.dtype[np.floating[Any]]],
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,  # noqa: ARG002
    ) -> NaiveForecaster:
        """Fit by storing the last observed value.

        Args:
            y: Target values (1D array).
            X: Ignored for naive model.

        Returns:
            self (for method chaining).

        Raises:
            ValueError: If y is empty.
        """
        if len(y) == 0:
            raise ValueError("Cannot fit on empty array")
        self._last_value = float(y[-1])
        self._last_values = np.array([self._last_value])
        self._is_fitted = True
        return self

    def predict(
        self,
        horizon: int,
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,  # noqa: ARG002
    ) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
        """Predict last value for all horizons.

        Args:
            horizon: Number of steps to forecast.
            X: Ignored for naive model.

        Returns:
            Array of forecasts with shape [horizon].

        Raises:
            RuntimeError: If model has not been fitted.
        """
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before predict")
        return np.full(horizon, self._last_value, dtype=np.float64)

    def get_params(self) -> dict[str, Any]:
        """Get model parameters.

        Returns:
            Dictionary with random_state.
        """
        return {"random_state": self.random_state}

    def set_params(self, **params: Any) -> NaiveForecaster:  # noqa: ANN401
        """Set model parameters.

        Args:
            **params: Parameter names and values to set.

        Returns:
            self (for method chaining).
        """
        for key, value in params.items():
            setattr(self, key, value)
        return self


class SeasonalNaiveForecaster(BaseForecaster):
    """Seasonal naive forecaster: predicts value from same season in previous cycle.

    Formula: y_hat[t+h] = y[t+h-m] where m is season_length

    For weekly seasonality (m=7), Friday's forecast = last Friday's value.

    Attributes:
        season_length: Seasonality period in days (default: 7 for weekly).
    """

    def __init__(self, season_length: int = 7, random_state: int = 42) -> None:
        """Initialize the seasonal naive forecaster.

        Args:
            season_length: Seasonality period in days (must be >= 1).
            random_state: Random seed for reproducibility (unused but kept for interface).

        Raises:
            ValueError: If season_length < 1.
        """
        super().__init__(random_state)
        if season_length < 1:
            raise ValueError(
                f"season_length must be >= 1, got {season_length}. "
                "A valid seasonality period is required for seasonal forecasting."
            )
        self.season_length = season_length

    def fit(
        self,
        y: np.ndarray[Any, np.dtype[np.floating[Any]]],
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,  # noqa: ARG002
    ) -> SeasonalNaiveForecaster:
        """Fit by storing the last season_length values.

        Args:
            y: Target values (1D array).
            X: Ignored for seasonal naive model.

        Returns:
            self (for method chaining).

        Raises:
            ValueError: If y has fewer observations than season_length.
        """
        if len(y) < self.season_length:
            raise ValueError(f"Need at least {self.season_length} observations")
        # Store last season_length values for cycling
        self._last_values = np.array(y[-self.season_length :], dtype=np.float64)
        self._is_fitted = True
        return self

    def predict(
        self,
        horizon: int,
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,  # noqa: ARG002
    ) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
        """Predict by cycling through seasonal values.

        Args:
            horizon: Number of steps to forecast.
            X: Ignored for seasonal naive model.

        Returns:
            Array of forecasts with shape [horizon].

        Raises:
            RuntimeError: If model has not been fitted.
        """
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before predict")
        if self._last_values is None:
            raise RuntimeError("Model was not properly fitted")
        # Cycle through seasonal values
        forecasts = np.zeros(horizon, dtype=np.float64)
        for h in range(horizon):
            idx = h % self.season_length
            forecasts[h] = self._last_values[idx]
        return forecasts

    def get_params(self) -> dict[str, Any]:
        """Get model parameters.

        Returns:
            Dictionary with season_length and random_state.
        """
        return {"season_length": self.season_length, "random_state": self.random_state}

    def set_params(self, **params: Any) -> SeasonalNaiveForecaster:  # noqa: ANN401
        """Set model parameters.

        Args:
            **params: Parameter names and values to set.

        Returns:
            self (for method chaining).
        """
        for key, value in params.items():
            setattr(self, key, value)
        return self


class MovingAverageForecaster(BaseForecaster):
    """Moving average forecaster: predicts mean of last N observations.

    Formula: y_hat[t+h] = mean(y[t-window+1:t+1])

    CRITICAL: Does NOT update recursively - uses same average for all horizons.

    Attributes:
        window_size: Window size for averaging (default: 7).
    """

    def __init__(self, window_size: int = 7, random_state: int = 42) -> None:
        """Initialize the moving average forecaster.

        Args:
            window_size: Window size for averaging (must be >= 1).
            random_state: Random seed for reproducibility (unused but kept for interface).

        Raises:
            ValueError: If window_size < 1.
        """
        super().__init__(random_state)
        if window_size < 1:
            raise ValueError(
                f"window_size must be >= 1, got {window_size}. "
                "A valid window size is required for moving average computation."
            )
        self.window_size = window_size
        self._forecast_value: float = 0.0

    def fit(
        self,
        y: np.ndarray[Any, np.dtype[np.floating[Any]]],
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,  # noqa: ARG002
    ) -> MovingAverageForecaster:
        """Fit by computing mean of last window_size values.

        Args:
            y: Target values (1D array).
            X: Ignored for moving average model.

        Returns:
            self (for method chaining).

        Raises:
            ValueError: If y has fewer observations than window_size.
        """
        if len(y) < self.window_size:
            raise ValueError(f"Need at least {self.window_size} observations")
        # Compute mean of last window_size values
        self._last_values = np.array(y[-self.window_size :], dtype=np.float64)
        self._forecast_value = float(np.mean(self._last_values))
        self._is_fitted = True
        return self

    def predict(
        self,
        horizon: int,
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,  # noqa: ARG002
    ) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
        """Predict constant value (mean) for all horizons.

        Args:
            horizon: Number of steps to forecast.
            X: Ignored for moving average model.

        Returns:
            Array of forecasts with shape [horizon].

        Raises:
            RuntimeError: If model has not been fitted.
        """
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before predict")
        # Constant forecast for all horizons
        return np.full(horizon, self._forecast_value, dtype=np.float64)

    def get_params(self) -> dict[str, Any]:
        """Get model parameters.

        Returns:
            Dictionary with window_size and random_state.
        """
        return {"window_size": self.window_size, "random_state": self.random_state}

    def set_params(self, **params: Any) -> MovingAverageForecaster:  # noqa: ANN401
        """Set model parameters.

        Args:
            **params: Parameter names and values to set.

        Returns:
            self (for method chaining).
        """
        for key, value in params.items():
            setattr(self, key, value)
        return self


class RegressionForecaster(BaseForecaster):
    """Feature-driven forecaster wrapping ``HistGradientBoostingRegressor``.

    CRITICAL: this is the FIRST forecaster that *consumes* the exogenous ``X``
    argument — the baseline forecasters all ignore it (each ``fit``/``predict``
    carries ``# noqa: ARG002``). Both ``fit`` and ``predict`` therefore REQUIRE
    a non-``None`` ``X`` whose row count matches, and raise ``ValueError``
    otherwise — a regression model cannot forecast without its feature frame.

    ``HistGradientBoostingRegressor`` is deterministic given a fixed
    ``random_state`` and tolerates ``NaN`` natively, which matters because the
    future feature frame leaves lag cells ``NaN`` when their source target
    lies in the (un-observed) horizon.

    Attributes:
        max_iter: Number of boosting iterations.
        learning_rate: Gradient-boosting learning rate.
        max_depth: Maximum depth of each tree.
    """

    requires_features: ClassVar[bool] = True
    """A feature-aware model — ``fit``/``predict`` REQUIRE a non-None ``X``."""

    def __init__(
        self,
        *,
        max_iter: int = 200,
        learning_rate: float = 0.05,
        max_depth: int = 6,
        random_state: int = 42,
    ) -> None:
        """Initialize the regression forecaster.

        Args:
            max_iter: Number of boosting iterations.
            learning_rate: Gradient-boosting learning rate.
            max_depth: Maximum depth of each tree.
            random_state: Random seed for reproducibility (determinism).
        """
        super().__init__(random_state)
        self.max_iter = max_iter
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self._estimator: Any = None

    def fit(
        self,
        y: np.ndarray[Any, np.dtype[np.floating[Any]]],
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,
    ) -> RegressionForecaster:
        """Fit the gradient-boosted regressor on historical features.

        Args:
            y: Target values (1D array of shape ``[n_samples]``).
            X: Exogenous features (2D array of shape ``[n_samples, n_features]``).
                REQUIRED — unlike the baseline forecasters.

        Returns:
            self (for method chaining).

        Raises:
            ValueError: If ``X`` is ``None``, ``y`` is empty, or the row counts
                of ``X`` and ``y`` do not match.
        """
        if X is None:
            raise ValueError("RegressionForecaster requires exogenous features X for fit()")
        if len(y) == 0:
            raise ValueError("Cannot fit on empty array")
        if X.shape[0] != len(y):
            raise ValueError(
                f"X has {X.shape[0]} rows but y has {len(y)} — feature/target rows must match"
            )
        estimator: Any = HistGradientBoostingRegressor(
            max_iter=self.max_iter,
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            random_state=self.random_state,
        )
        estimator.fit(X, y)
        self._estimator = estimator
        self._last_values = np.asarray(y[-1:], dtype=np.float64)
        self._is_fitted = True
        return self

    def predict(
        self,
        horizon: int,
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,
    ) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
        """Generate forecasts from a future feature frame.

        Args:
            horizon: Number of steps to forecast.
            X: Exogenous features for the forecast period, shape
                ``[horizon, n_features]``. REQUIRED.

        Returns:
            Array of forecasts with shape ``[horizon]``.

        Raises:
            RuntimeError: If the model has not been fitted.
            ValueError: If ``X`` is ``None`` or its row count is not ``horizon``.
        """
        if not self._is_fitted or self._estimator is None:
            raise RuntimeError("Model must be fitted before predict")
        if X is None:
            raise ValueError("RegressionForecaster requires exogenous features X for predict()")
        if X.shape[0] != horizon:
            raise ValueError(f"X has {X.shape[0]} rows but horizon is {horizon} — they must match")
        predictions = self._estimator.predict(X)
        result: np.ndarray[Any, np.dtype[np.floating[Any]]] = np.asarray(
            predictions, dtype=np.float64
        )
        return result

    def get_params(self) -> dict[str, Any]:
        """Get model parameters.

        Returns:
            Dictionary with max_iter, learning_rate, max_depth, random_state.
        """
        return {
            "max_iter": self.max_iter,
            "learning_rate": self.learning_rate,
            "max_depth": self.max_depth,
            "random_state": self.random_state,
        }

    def set_params(self, **params: Any) -> RegressionForecaster:  # noqa: ANN401
        """Set model parameters.

        Args:
            **params: Parameter names and values to set.

        Returns:
            self (for method chaining).
        """
        for key, value in params.items():
            setattr(self, key, value)
        return self


class LightGBMForecaster(BaseForecaster):
    """Feature-aware forecaster wrapping ``lightgbm.LGBMRegressor``.

    The first ADVANCED feature-aware model (MLZOO-B). Like
    ``RegressionForecaster`` it REQUIRES a non-``None`` exogenous ``X`` for both
    ``fit`` and ``predict``; unlike it, the estimator is gradient-boosted
    leaf-wise trees from the optional ``lightgbm`` package.

    ``lightgbm`` is imported LAZILY inside ``fit`` — never at module scope and
    never in ``__init__`` — so importing this module (which every forecasting
    code path does, baseline models included) never requires the optional
    ``ml-lightgbm`` dependency.

    Determinism: ``LGBMRegressor`` is bit-reproducible only with ``n_jobs=1``
    AND ``deterministic=True`` AND ``force_col_wise=True`` AND a fixed
    ``random_state`` — all four are pinned in ``fit``. LightGBM also tolerates
    ``NaN`` natively, which matters because the future feature frame leaves lag
    cells ``NaN`` when their source target lies in the un-observed horizon.

    Attributes:
        n_estimators: Number of boosting rounds.
        learning_rate: Gradient-boosting learning rate.
        max_depth: Maximum depth of each tree.
    """

    requires_features: ClassVar[bool] = True
    """A feature-aware model — ``fit``/``predict`` REQUIRE a non-None ``X``."""

    def __init__(
        self,
        *,
        n_estimators: int = 100,
        learning_rate: float = 0.1,
        max_depth: int = 6,
        random_state: int = 42,
    ) -> None:
        """Initialize the LightGBM forecaster.

        Args:
            n_estimators: Number of boosting rounds.
            learning_rate: Gradient-boosting learning rate.
            max_depth: Maximum depth of each tree.
            random_state: Random seed for reproducibility (determinism).
        """
        super().__init__(random_state)
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self._estimator: Any = None

    def fit(
        self,
        y: np.ndarray[Any, np.dtype[np.floating[Any]]],
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,
    ) -> LightGBMForecaster:
        """Fit the gradient-boosted regressor on historical features.

        Args:
            y: Target values (1D array of shape ``[n_samples]``).
            X: Exogenous features (2D array of shape ``[n_samples, n_features]``).
                REQUIRED — unlike the baseline forecasters.

        Returns:
            self (for method chaining).

        Raises:
            ValueError: If ``X`` is ``None``, ``y`` is empty, or the row counts
                of ``X`` and ``y`` do not match.
        """
        if X is None:
            raise ValueError("LightGBMForecaster requires exogenous features X for fit()")
        if len(y) == 0:
            raise ValueError("Cannot fit on empty array")
        if X.shape[0] != len(y):
            raise ValueError(
                f"X has {X.shape[0]} rows but y has {len(y)} — feature/target rows must match"
            )
        # LAZY import — the optional ``ml-lightgbm`` dependency is only needed
        # the first time a LightGBM model is actually fitted.
        import lightgbm as lgb

        estimator: Any = lgb.LGBMRegressor(
            n_estimators=self.n_estimators,
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            random_state=self.random_state,
            n_jobs=1,  # \
            deterministic=True,  #  } all four required for a bit-reproducible fit
            force_col_wise=True,  # /
            verbosity=-1,  # silence LightGBM's training chatter
        )
        estimator.fit(X, y)
        self._estimator = estimator
        self._last_values = np.asarray(y[-1:], dtype=np.float64)
        self._is_fitted = True
        return self

    def predict(
        self,
        horizon: int,
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,
    ) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
        """Generate forecasts from a future feature frame.

        Args:
            horizon: Number of steps to forecast.
            X: Exogenous features for the forecast period, shape
                ``[horizon, n_features]``. REQUIRED.

        Returns:
            Array of forecasts with shape ``[horizon]``.

        Raises:
            RuntimeError: If the model has not been fitted.
            ValueError: If ``X`` is ``None`` or its row count is not ``horizon``.
        """
        if not self._is_fitted or self._estimator is None:
            raise RuntimeError("Model must be fitted before predict")
        if X is None:
            raise ValueError("LightGBMForecaster requires exogenous features X for predict()")
        if X.shape[0] != horizon:
            raise ValueError(f"X has {X.shape[0]} rows but horizon is {horizon} — they must match")
        predictions = self._estimator.predict(X)
        result: np.ndarray[Any, np.dtype[np.floating[Any]]] = np.asarray(
            predictions, dtype=np.float64
        )
        return result

    def get_params(self) -> dict[str, Any]:
        """Get model parameters.

        Returns:
            Dictionary with n_estimators, learning_rate, max_depth, random_state.
        """
        return {
            "n_estimators": self.n_estimators,
            "learning_rate": self.learning_rate,
            "max_depth": self.max_depth,
            "random_state": self.random_state,
        }

    def set_params(self, **params: Any) -> LightGBMForecaster:  # noqa: ANN401
        """Set model parameters.

        Args:
            **params: Parameter names and values to set.

        Returns:
            self (for method chaining).
        """
        for key, value in params.items():
            setattr(self, key, value)
        return self


# Type alias for model type literals
ModelType = Literal["naive", "seasonal_naive", "moving_average", "lightgbm", "regression"]


def model_factory(config: ModelConfig, random_state: int = 42) -> BaseForecaster:
    """Create a forecaster instance from a configuration.

    Args:
        config: Model configuration.
        random_state: Random seed for reproducibility.

    Returns:
        Instantiated forecaster.

    Raises:
        ValueError: If model_type is unknown or LightGBM is not enabled.
    """
    from app.core.config import get_settings

    settings = get_settings()

    model_type: str = config.model_type

    if model_type == "naive":
        return NaiveForecaster(random_state=random_state)
    elif model_type == "seasonal_naive":
        from app.features.forecasting.schemas import SeasonalNaiveModelConfig

        if isinstance(config, SeasonalNaiveModelConfig):
            return SeasonalNaiveForecaster(
                season_length=config.season_length,
                random_state=random_state,
            )
        raise ValueError("Invalid config type for seasonal_naive")
    elif model_type == "moving_average":
        from app.features.forecasting.schemas import MovingAverageModelConfig

        if isinstance(config, MovingAverageModelConfig):
            return MovingAverageForecaster(
                window_size=config.window_size,
                random_state=random_state,
            )
        raise ValueError("Invalid config type for moving_average")
    elif model_type == "lightgbm":
        if not settings.forecast_enable_lightgbm:
            raise ValueError(
                "LightGBM is not enabled. Set forecast_enable_lightgbm=True in settings."
            )
        from app.features.forecasting.schemas import LightGBMModelConfig

        if isinstance(config, LightGBMModelConfig):
            return LightGBMForecaster(
                n_estimators=config.n_estimators,
                learning_rate=config.learning_rate,
                max_depth=config.max_depth,
                random_state=random_state,
            )
        raise ValueError("Invalid config type for lightgbm")
    elif model_type == "regression":
        from app.features.forecasting.schemas import RegressionModelConfig

        if isinstance(config, RegressionModelConfig):
            return RegressionForecaster(
                max_iter=config.max_iter,
                learning_rate=config.learning_rate,
                max_depth=config.max_depth,
                random_state=random_state,
            )
        raise ValueError("Invalid config type for regression")
    else:
        raise ValueError(f"Unknown model type: {model_type}")
