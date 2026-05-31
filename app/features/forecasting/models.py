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
from sklearn.impute import SimpleImputer  # type: ignore[import-untyped]
from sklearn.linear_model import Ridge  # type: ignore[import-untyped]
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from app.features.forecasting.schemas import ModelConfig


# Canonical 14-column feature frame partitioned into the three Prophet-style
# additive components. Together the three column tuples cover all 14 canonical
# columns exactly — which is what makes the additive invariant hold (the
# component contributions partition the full coef_ · x sum). See
# ``canonical_feature_columns()`` in ``app/shared/feature_frames``.
_PROPHET_LIKE_COMPONENTS: dict[str, tuple[str, ...]] = {
    "trend": ("lag_1", "lag_7", "lag_14", "lag_28", "days_since_launch"),
    "seasonality": (
        "dow_sin",
        "dow_cos",
        "month_sin",
        "month_cos",
        "is_weekend",
        "is_month_end",
    ),
    "holiday_regressor": ("price_factor", "promo_active", "is_holiday"),
}


@dataclass
class ForecastDecomposition:
    """Additive component breakdown of a Prophet-like forecast.

    Invariant: ``intercept + trend + seasonality + holiday_regressor`` equals
    ``predict(...)`` for the same ``X`` (within float tolerance), element-wise.
    Each component array has shape ``[n_rows]`` — one value per forecast row.

    Attributes:
        intercept: The fitted Ridge intercept (a scalar, broadcast over rows).
        trend: Per-row contribution of the trend columns (autoregressive lags
            + ``days_since_launch``).
        seasonality: Per-row contribution of the calendar/seasonal columns.
        holiday_regressor: Per-row contribution of the holiday + extra-regressor
            columns (price, promotion, holiday flag).
    """

    intercept: float
    trend: np.ndarray[Any, np.dtype[np.floating[Any]]]
    seasonality: np.ndarray[Any, np.dtype[np.floating[Any]]]
    holiday_regressor: np.ndarray[Any, np.dtype[np.floating[Any]]]


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


# ---------------------------------------------------------------------------
# Shared PRP-36 helpers (reused by the forecasters AND the explainers).
#
# Centralising these here means the explainer's h=1 math always matches the
# forecaster's predict() math byte-for-byte — no two-place drift when a
# default changes.  These are pure functions: no I/O, no state.
# ---------------------------------------------------------------------------


def compute_weighted_average_weights(
    window_size: int,
    weight_strategy: Literal["linear", "exponential"],
    decay: float,
) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
    """Build the weight vector :class:`WeightedMovingAverageForecaster` applies.

    ``'linear'`` → ``np.arange(1, window_size+1)`` (newest = ``window_size``).
    ``'exponential'`` → ``decay ** np.arange(window_size-1, -1, -1)`` (newest = 1.0).
    """
    if weight_strategy == "linear":
        return np.arange(1, window_size + 1, dtype=np.float64)
    return np.power(decay, np.arange(window_size - 1, -1, -1, dtype=np.float64))


def compute_seasonal_average_for_offset(
    history: np.ndarray[Any, np.dtype[np.floating[Any]]],
    season_length: int,
    lookback_cycles: int,
    target_offset: int,
    trim_outliers: bool,
) -> tuple[float, list[float], np.ndarray[Any, np.dtype[np.floating[Any]]]]:
    """Compute the seasonal-average forecast for one ``target_offset``.

    Mirrors :meth:`SeasonalAverageForecaster.predict` exactly for a single
    horizon step. Returns ``(forecast, samples_used, samples_after_trim)``
    so callers can report whichever array they need:

    - ``forecast`` — the mean reported by the forecaster.
    - ``samples_used`` — the raw samples drawn from ``history``.
    - ``samples_after_trim`` — the array the mean was actually computed
      from (equal to ``samples_used`` when ``trim_outliers`` is off or
      ``len(samples) < 4``).
    """
    samples: list[float] = []
    for k in range(1, lookback_cycles + 1):
        idx_from_end = k * season_length - target_offset
        if 0 <= idx_from_end < history.size:
            samples.append(float(history[history.size - 1 - idx_from_end]))
    if not samples:
        fallback = float(history[-1])
        fallback_arr = np.asarray([fallback], dtype=np.float64)
        return fallback, [fallback], fallback_arr
    arr = np.asarray(samples, dtype=np.float64)
    if trim_outliers and arr.size >= 4:
        arr = np.sort(arr)[1:-1]
    return float(arr.mean()), samples, arr


def build_trend_baseline_design_row(
    elapsed_day: int,
    include_dow: bool,
    include_month: bool,
) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
    """Build one design row matching :class:`TrendRegressionBaselineForecaster`.

    Layout: ``[elapsed_day, (dow_one_hot x7)?, (month_one_hot x12)?]``.

    Synthetic encodings: ``elapsed_day % 7`` for dow, ``(elapsed_day // 30) % 12``
    for month. Calendar-agnostic and deterministic — see the forecaster's
    docstring for the rationale.
    """
    cols: list[float] = [float(elapsed_day)]
    if include_dow:
        dow = elapsed_day % 7
        cols.extend(1.0 if i == dow else 0.0 for i in range(7))
    if include_month:
        month = (elapsed_day // 30) % 12
        cols.extend(1.0 if i == month else 0.0 for i in range(12))
    return np.asarray(cols, dtype=np.float64)


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


class WeightedMovingAverageForecaster(BaseForecaster):
    """Target-only baseline: weighted average of the last ``window_size`` observations.

    Formula (constant for every horizon step):
        ``y_hat[t+h] = np.average(y[-W:], weights=W_strategy)`` for all h.

    Two weight strategies are exposed via ``weight_strategy``:

    - ``'linear'`` → ``weights = np.arange(1, W+1)`` — newest observation
      weighted highest (= ``W``), oldest weighted lowest (= ``1``).
    - ``'exponential'`` → ``weights = decay ** np.arange(W-1, -1, -1)`` —
      geometric decay; newest observation weighted ``decay**0 = 1.0``.

    CRITICAL: like :class:`MovingAverageForecaster`, this baseline does NOT
    update recursively — every horizon step gets the same weighted mean.
    """

    requires_features: ClassVar[bool] = False

    def __init__(
        self,
        *,
        window_size: int = 7,
        weight_strategy: Literal["linear", "exponential"] = "linear",
        decay: float = 0.7,
        random_state: int = 42,
    ) -> None:
        """Initialize the weighted moving average forecaster.

        Args:
            window_size: Number of trailing observations to average (>=2).
            weight_strategy: Either ``'linear'`` or ``'exponential'``.
            decay: Geometric decay factor for ``'exponential'``; must lie in
                ``(0.0, 1.0)``. Ignored for ``'linear'``.
            random_state: Random seed for reproducibility (unused but kept
                for interface consistency).

        Raises:
            ValueError: If ``window_size < 2``, if ``weight_strategy`` is
                unknown, or if ``decay`` is outside ``(0.0, 1.0)``.
        """
        super().__init__(random_state)
        if window_size < 2:
            raise ValueError(
                f"window_size must be >= 2, got {window_size}. "
                "A weighted moving average needs at least two observations."
            )
        if weight_strategy not in ("linear", "exponential"):
            raise ValueError(
                f"weight_strategy must be 'linear' or 'exponential', got {weight_strategy!r}."
            )
        if not 0.0 < decay < 1.0:
            raise ValueError(f"decay must lie in (0.0, 1.0), got {decay}.")
        self.window_size = window_size
        self.weight_strategy: Literal["linear", "exponential"] = weight_strategy
        self.decay = decay
        self._weights: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None
        self._forecast_value: float = 0.0

    def fit(
        self,
        y: np.ndarray[Any, np.dtype[np.floating[Any]]],
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,  # noqa: ARG002
    ) -> WeightedMovingAverageForecaster:
        """Fit by computing the weighted mean of the last ``window_size`` values.

        Args:
            y: Target values (1D array).
            X: Ignored for the weighted moving average baseline.

        Returns:
            self (for method chaining).

        Raises:
            ValueError: If ``len(y) < window_size``.
        """
        y_arr = np.asarray(y, dtype=np.float64)
        if y_arr.size < self.window_size:
            raise ValueError(f"Need at least {self.window_size} observations, got {y_arr.size}")
        tail = y_arr[-self.window_size :]
        # PRP-36 — weight vector built via the shared helper so the
        # explainer reuses the identical formula.
        self._weights = compute_weighted_average_weights(
            window_size=self.window_size,
            weight_strategy=self.weight_strategy,
            decay=self.decay,
        )
        self._last_values = tail
        self._forecast_value = float(np.average(tail, weights=self._weights))
        self._is_fitted = True
        return self

    def predict(
        self,
        horizon: int,
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,  # noqa: ARG002
    ) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
        """Predict the constant weighted mean for every horizon step."""
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before predict")
        return np.full(horizon, self._forecast_value, dtype=np.float64)

    def get_params(self) -> dict[str, Any]:
        """Return constructor parameters (sklearn convention)."""
        return {
            "window_size": self.window_size,
            "weight_strategy": self.weight_strategy,
            "decay": self.decay,
            "random_state": self.random_state,
        }

    def set_params(self, **params: Any) -> WeightedMovingAverageForecaster:  # noqa: ANN401
        """Set constructor parameters (sklearn convention)."""
        for key, value in params.items():
            setattr(self, key, value)
        return self


class SeasonalAverageForecaster(BaseForecaster):
    """Target-only baseline: average of prior matching seasonal positions.

    For horizon day ``j`` (1-based) with season length ``S``, the forecaster
    averages the historical values at offsets ``{j - k*S}`` for ``k`` in
    ``[1..lookback_cycles]`` that fall inside the stored history. With
    ``trim_outliers=True`` and ≥4 samples, the per-bucket sample drops its
    min and max before averaging.

    Compared to :class:`SeasonalNaiveForecaster` (which copies the value
    from a single prior cycle position), this baseline averages across
    multiple prior cycles — more robust on noisy series.
    """

    requires_features: ClassVar[bool] = False

    def __init__(
        self,
        *,
        season_length: int = 7,
        lookback_cycles: int = 4,
        trim_outliers: bool = False,
        random_state: int = 42,
    ) -> None:
        """Initialize the seasonal-average forecaster.

        Args:
            season_length: Seasonality period in days (must be >= 2).
            lookback_cycles: Number of trailing cycles to draw samples from
                (must be >= 2).
            trim_outliers: If True, drop the min + max sample per bucket
                before averaging. Requires ≥4 samples to apply.
            random_state: Random seed (unused, kept for interface parity).

        Raises:
            ValueError: If ``season_length < 2`` or ``lookback_cycles < 2``.
        """
        super().__init__(random_state)
        if season_length < 2:
            raise ValueError(f"season_length must be >= 2, got {season_length}.")
        if lookback_cycles < 2:
            raise ValueError(f"lookback_cycles must be >= 2, got {lookback_cycles}.")
        self.season_length = season_length
        self.lookback_cycles = lookback_cycles
        self.trim_outliers = trim_outliers
        self._history: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None

    def fit(
        self,
        y: np.ndarray[Any, np.dtype[np.floating[Any]]],
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,  # noqa: ARG002
    ) -> SeasonalAverageForecaster:
        """Store the last ``season_length * lookback_cycles`` observations."""
        y_arr = np.asarray(y, dtype=np.float64)
        min_required = self.season_length * 2
        if y_arr.size < min_required:
            raise ValueError(
                f"Need at least {min_required} observations "
                f"(season_length={self.season_length} * 2), got {y_arr.size}"
            )
        window = self.season_length * self.lookback_cycles
        # Keep only the trailing cycles relevant for sampling; if fewer
        # observations exist, retain what's available so predict() still
        # produces a sensible mean.
        self._history = y_arr[-window:] if y_arr.size > window else y_arr.copy()
        self._is_fitted = True
        return self

    def predict(
        self,
        horizon: int,
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,  # noqa: ARG002
    ) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
        """Average matching seasonal positions for every horizon step."""
        if not self._is_fitted or self._history is None:
            raise RuntimeError("Model must be fitted before predict")
        out = np.zeros(horizon, dtype=np.float64)
        for j in range(horizon):
            # PRP-36 — single source of truth for the h=j+1 math. The
            # explainer reuses ``compute_seasonal_average_for_offset`` so
            # the two paths never drift.
            forecast_value, _samples_used, _samples_after_trim = (
                compute_seasonal_average_for_offset(
                    history=self._history,
                    season_length=self.season_length,
                    lookback_cycles=self.lookback_cycles,
                    target_offset=j + 1,  # 1-based horizon day index
                    trim_outliers=self.trim_outliers,
                )
            )
            out[j] = forecast_value
        return out

    def get_params(self) -> dict[str, Any]:
        """Return constructor parameters (sklearn convention)."""
        return {
            "season_length": self.season_length,
            "lookback_cycles": self.lookback_cycles,
            "trim_outliers": self.trim_outliers,
            "random_state": self.random_state,
        }

    def set_params(self, **params: Any) -> SeasonalAverageForecaster:  # noqa: ANN401
        """Set constructor parameters (sklearn convention)."""
        for key, value in params.items():
            setattr(self, key, value)
        return self


class TrendRegressionBaselineForecaster(BaseForecaster):
    """Target-only Ridge baseline: elapsed-day index + optional calendar one-hots.

    Builds its own design matrix from a synthetic elapsed-day index (and,
    optionally, day-of-week / month one-hot columns). Unlike
    :class:`RegressionForecaster`, this forecaster does NOT consume the V1
    or V2 feature frame — its features are purely calendar-derived inside
    ``fit``/``predict``. ``requires_features`` stays ``False``.

    Ridge is deterministic by construction (closed-form solver); a fixed
    ``random_state`` is kept for interface parity but never sampled.
    """

    requires_features: ClassVar[bool] = False

    def __init__(
        self,
        *,
        alpha: float = 1.0,
        include_dow: bool = True,
        include_month: bool = True,
        random_state: int = 42,
    ) -> None:
        """Initialize the trend regression baseline."""
        super().__init__(random_state)
        if alpha < 0.0:
            raise ValueError(f"alpha must be >= 0, got {alpha}.")
        self.alpha = alpha
        self.include_dow = include_dow
        self.include_month = include_month
        self._ridge: Ridge | None = None
        self._n_train: int = 0

    # ---------------------------------------------------------------- design

    def _design_row(self, elapsed_day: int) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
        """Build a single design row.

        Thin wrapper over :func:`build_trend_baseline_design_row` — the
        explainer calls the module-level helper directly so the training
        and explanation paths share one source of truth for the encoding.
        """
        return build_trend_baseline_design_row(
            elapsed_day=elapsed_day,
            include_dow=self.include_dow,
            include_month=self.include_month,
        )

    def _design_matrix(
        self,
        start_day: int,
        n_rows: int,
    ) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
        rows = [self._design_row(start_day + i) for i in range(n_rows)]
        return np.vstack(rows)

    # --------------------------------------------------------------- fit/pred

    def fit(
        self,
        y: np.ndarray[Any, np.dtype[np.floating[Any]]],
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,  # noqa: ARG002
    ) -> TrendRegressionBaselineForecaster:
        """Fit Ridge on a synthetic elapsed-day design matrix."""
        y_arr = np.asarray(y, dtype=np.float64)
        if y_arr.size < 2:
            raise ValueError(f"Need at least 2 observations to fit a trend, got {y_arr.size}.")
        # Synthetic elapsed-day index aligned to the historical positions.
        X_train = self._design_matrix(start_day=0, n_rows=y_arr.size)
        self._ridge = Ridge(alpha=self.alpha, random_state=self.random_state)
        self._ridge.fit(X_train, y_arr)
        self._n_train = int(y_arr.size)
        self._is_fitted = True
        return self

    def predict(
        self,
        horizon: int,
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,  # noqa: ARG002
    ) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
        """Predict horizon steps using the elapsed-day continuation."""
        if not self._is_fitted or self._ridge is None:
            raise RuntimeError("Model must be fitted before predict")
        X_future = self._design_matrix(start_day=self._n_train, n_rows=horizon)
        result = self._ridge.predict(X_future)
        return np.asarray(result, dtype=np.float64)

    def get_params(self) -> dict[str, Any]:
        """Return constructor parameters (sklearn convention)."""
        return {
            "alpha": self.alpha,
            "include_dow": self.include_dow,
            "include_month": self.include_month,
            "random_state": self.random_state,
        }

    def set_params(self, **params: Any) -> TrendRegressionBaselineForecaster:  # noqa: ANN401
        """Set constructor parameters (sklearn convention)."""
        for key, value in params.items():
            setattr(self, key, value)
        return self


class RandomForestForecaster(BaseForecaster):
    """Feature-aware forecaster wrapping ``sklearn.ensemble.RandomForestRegressor``.

    Optional, gated by ``forecast_enable_random_forest`` in settings (the
    factory enforces the gate). Unlike :class:`RegressionForecaster`, the
    wrapped estimator DOES expose ``feature_importances_`` — verified at
    PRP-create time (sklearn 1.8.0) — so the
    :func:`extract_feature_importance` tree branch handles it without a
    new special case.

    Determinism recipe (verified): ``random_state`` is fixed AND ``n_jobs=1``.
    Never set ``n_jobs > 1``; thread-parallel tree fitting introduces
    nondeterminism. ``predict`` accepts the future feature matrix the
    forecasting service builds via the V1 (or, once #299 lands, V2) row
    builders — identical contract to :class:`RegressionForecaster`.
    """

    requires_features: ClassVar[bool] = True

    def __init__(
        self,
        *,
        n_estimators: int = 100,
        max_depth: int | None = 10,
        min_samples_leaf: int = 2,
        random_state: int = 42,
    ) -> None:
        """Initialize the RandomForest forecaster.

        Args:
            n_estimators: Number of trees in the forest.
            max_depth: Maximum depth per tree (``None`` = unlimited).
            min_samples_leaf: Minimum samples required at a leaf.
            random_state: Random seed (REQUIRED for determinism; combined
                with ``n_jobs=1`` it gives byte-identical fits).
        """
        super().__init__(random_state)
        if n_estimators < 1:
            raise ValueError(f"n_estimators must be >= 1, got {n_estimators}.")
        if max_depth is not None and max_depth < 1:
            raise ValueError(f"max_depth must be >= 1 or None, got {max_depth}.")
        if min_samples_leaf < 1:
            raise ValueError(f"min_samples_leaf must be >= 1, got {min_samples_leaf}.")
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        # Lazy import — RandomForestRegressor is a top-level sklearn class but
        # we still mirror the existing pattern of constructing the estimator
        # at ``fit`` time so unit tests can patch the import surface cleanly.
        self._estimator: Any = None
        self._feature_columns: list[str] | None = None
        self._n_features_in: int = 0

    def fit(
        self,
        y: np.ndarray[Any, np.dtype[np.floating[Any]]],
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,
    ) -> RandomForestForecaster:
        """Fit on a feature matrix ``X`` and target vector ``y``."""
        if X is None:
            raise ValueError(
                "RandomForestForecaster requires a non-None X feature matrix; "
                "this is a feature-aware model."
            )
        y_arr = np.asarray(y, dtype=np.float64)
        X_arr = np.asarray(X, dtype=np.float64)
        if X_arr.ndim != 2:
            raise ValueError(f"X must be a 2-D feature matrix, got shape {X_arr.shape}.")
        if X_arr.shape[0] != y_arr.size:
            raise ValueError(
                f"X / y row count mismatch: X has {X_arr.shape[0]}, y has {y_arr.size}."
            )
        # Lazy import keeps the module-load surface stable.
        from sklearn.ensemble import (  # pyright: ignore[reportMissingTypeStubs]
            RandomForestRegressor,
        )

        self._estimator = RandomForestRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            random_state=self.random_state,
            n_jobs=1,  # REQUIRED for determinism; never widen this.
        )
        self._estimator.fit(X_arr, y_arr)
        self._n_features_in = int(X_arr.shape[1])
        self._is_fitted = True
        return self

    def predict(
        self,
        horizon: int,  # noqa: ARG002 — horizon is implied by X.shape[0]
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,
    ) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
        """Predict using the supplied future feature matrix."""
        if not self._is_fitted or self._estimator is None:
            raise RuntimeError("Model must be fitted before predict")
        if X is None:
            raise ValueError("RandomForestForecaster.predict requires a non-None X feature matrix.")
        X_arr = np.asarray(X, dtype=np.float64)
        if X_arr.ndim != 2:
            raise ValueError(f"X must be a 2-D feature matrix, got shape {X_arr.shape}.")
        if X_arr.shape[1] != self._n_features_in:
            raise ValueError(
                f"X column count mismatch: trained on {self._n_features_in} "
                f"columns, predict received {X_arr.shape[1]}."
            )
        result = self._estimator.predict(X_arr)
        return np.asarray(result, dtype=np.float64)

    def get_params(self) -> dict[str, Any]:
        """Return constructor parameters (sklearn convention)."""
        return {
            "n_estimators": self.n_estimators,
            "max_depth": self.max_depth,
            "min_samples_leaf": self.min_samples_leaf,
            "random_state": self.random_state,
        }

    def set_params(self, **params: Any) -> RandomForestForecaster:  # noqa: ANN401
        """Set constructor parameters (sklearn convention)."""
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
        # the first time a LightGBM model is actually fitted. A missing package
        # becomes a ValueError so the route returns a controlled 400, not a 500.
        try:
            import lightgbm as lgb
        except ImportError as exc:
            raise ValueError(
                "LightGBM is not installed. Install the optional 'ml-lightgbm' "
                "extra (e.g. `uv sync --extra ml-lightgbm`)."
            ) from exc

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


class XGBoostForecaster(BaseForecaster):
    """Feature-aware forecaster wrapping ``xgboost.XGBRegressor``.

    The second ADVANCED feature-aware tree model (MLZOO-C1). Structurally a
    twin of ``LightGBMForecaster``: it REQUIRES a non-``None`` exogenous ``X``
    for both ``fit`` and ``predict``; the estimator is gradient-boosted trees
    from the optional ``xgboost`` package.

    ``xgboost`` is imported LAZILY inside ``fit`` — never at module scope and
    never in ``__init__`` — so importing this module (which every forecasting
    code path does, baseline models included) never requires the optional
    ``ml-xgboost`` dependency.

    Determinism: ``XGBRegressor`` has no ``deterministic`` switch (unlike
    LightGBM). Bit-reproducibility comes from ``n_jobs=1`` + ``tree_method="hist"``
    + a fixed ``random_state`` + the conservative config leaving ``subsample`` /
    ``colsample_bytree`` at their ``1.0`` defaults (no stochastic sampling) —
    all pinned in ``fit``. XGBoost tolerates ``NaN`` natively (``missing=np.nan``),
    which matters because the future feature frame leaves lag cells ``NaN``
    when their source target lies in the un-observed horizon.

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
        """Initialize the XGBoost forecaster.

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
    ) -> XGBoostForecaster:
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
            raise ValueError("XGBoostForecaster requires exogenous features X for fit()")
        if len(y) == 0:
            raise ValueError("Cannot fit on empty array")
        if X.shape[0] != len(y):
            raise ValueError(
                f"X has {X.shape[0]} rows but y has {len(y)} — feature/target rows must match"
            )
        # LAZY import — the optional ``ml-xgboost`` dependency is only needed
        # the first time an XGBoost model is actually fitted. A missing package
        # becomes a ValueError so the route returns a controlled 400, not a 500.
        try:
            import xgboost as xgb
        except ImportError as exc:
            raise ValueError(
                "XGBoost is not installed. Install the optional 'ml-xgboost' "
                "extra (e.g. `uv sync --extra ml-xgboost`)."
            ) from exc

        estimator: Any = xgb.XGBRegressor(
            n_estimators=self.n_estimators,
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            random_state=self.random_state,
            n_jobs=1,  # single-threaded — removes float-summation non-determinism
            tree_method="hist",  # explicit; the default, and the reproducible path
            verbosity=0,  # silence XGBoost's training chatter
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
            raise ValueError("XGBoostForecaster requires exogenous features X for predict()")
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

    def set_params(self, **params: Any) -> XGBoostForecaster:  # noqa: ANN401
        """Set model parameters.

        Args:
            **params: Parameter names and values to set.

        Returns:
            self (for method chaining).
        """
        for key, value in params.items():
            setattr(self, key, value)
        return self


class ProphetLikeForecaster(BaseForecaster):
    """Feature-aware ADDITIVE forecaster — Ridge over the canonical frame.

    Prophet-LIKE, not Prophet: it approximates Prophet's additive trend +
    seasonality + holiday/regressor decomposition with a regularized linear
    model over the already-engineered 14-column feature frame. It REQUIRES a
    non-``None`` exogenous ``X`` for both ``fit`` and ``predict``.

    The fitted estimator is a scikit-learn ``Pipeline`` of two deterministic
    steps: a ``SimpleImputer(strategy="median")`` that fills the ``NaN`` lag
    cells the future feature frame emits (a bare ``Ridge`` raises
    ``ValueError: Input contains NaN``), followed by a
    ``Ridge(solver="cholesky")`` whose closed-form L2-regularized fit is
    robust to the collinear engineered columns. Folding the imputer INSIDE the
    pipeline keeps the no-leakage invariant: it learns its medians on the
    training ``X`` only and re-applies them at predict time.

    ``decompose()`` returns the per-component additive contributions of a
    forecast — the literal ``y_hat = intercept + trend + seasonality +
    holiday_regressor`` split, computed on the IMPUTED ``X``.

    NOT modelled (deliberately — see PRP-MLZOO-C2 Risks): changepoint trend,
    posterior uncertainty intervals, automatic seasonality discovery,
    multiplicative seasonality. This is an additive linear approximation, not
    the real ``prophet`` package.

    Attributes:
        alpha: Ridge L2 regularization strength (0.0 degenerates to OLS).
    """

    requires_features: ClassVar[bool] = True
    """A feature-aware model — ``fit``/``predict`` REQUIRE a non-None ``X``."""

    def __init__(self, *, alpha: float = 1.0, random_state: int = 42) -> None:
        """Initialize the Prophet-like additive forecaster.

        Args:
            alpha: Ridge L2 regularization strength. The default 1.0 keeps
                coefficients robust to the collinear engineered-feature frame.
            random_state: Kept for interface parity with the other forecasters;
                ``Ridge(solver="cholesky")`` is closed-form and needs no seed.
        """
        super().__init__(random_state)
        self.alpha = alpha
        self._estimator: Any = None

    def fit(
        self,
        y: np.ndarray[Any, np.dtype[np.floating[Any]]],
        X: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None,
    ) -> ProphetLikeForecaster:
        """Fit the additive Ridge pipeline on historical features.

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
            raise ValueError("ProphetLikeForecaster requires exogenous features X for fit()")
        if len(y) == 0:
            raise ValueError("Cannot fit on empty array")
        if X.shape[0] != len(y):
            raise ValueError(
                f"X has {X.shape[0]} rows but y has {len(y)} — feature/target rows must match"
            )
        # The imputer learns its per-column medians on THIS training X only;
        # the Ridge solver is deterministic and closed-form.
        estimator: Any = Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("ridge", Ridge(alpha=self.alpha, solver="cholesky")),
            ]
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
            raise ValueError("ProphetLikeForecaster requires exogenous features X for predict()")
        if X.shape[0] != horizon:
            raise ValueError(f"X has {X.shape[0]} rows but horizon is {horizon} — they must match")
        # The Pipeline imputes the NaN lag cells, then the Ridge predicts.
        predictions = self._estimator.predict(X)
        result: np.ndarray[Any, np.dtype[np.floating[Any]]] = np.asarray(
            predictions, dtype=np.float64
        )
        return result

    def decompose(self, X: np.ndarray[Any, np.dtype[np.floating[Any]]]) -> ForecastDecomposition:
        """Split a forecast into its additive trend / seasonality / regressor parts.

        Operates on the IMPUTED ``X`` — the trained imputer's ``transform`` —
        so the per-component contributions sum EXACTLY to ``predict(...)``: any
        ``NaN`` cell is filled with the TRAINING-window median, never a
        predict-time median (no leakage). Each component contribution is the
        partial sum ``Σ_{i ∈ component} coef_i · x_i``; together the three
        component column-sets partition all 14 canonical columns, so
        ``intercept + trend + seasonality + holiday_regressor == predict()``.

        Args:
            X: Feature matrix of shape ``[n_rows, n_features]`` (the same frame
                a ``predict`` call would consume). May contain ``NaN`` cells.

        Returns:
            A :class:`ForecastDecomposition` with the four-way breakdown.

        Raises:
            RuntimeError: If the model has not been fitted.
        """
        from app.shared.feature_frames import canonical_feature_columns

        if not self._is_fitted or self._estimator is None:
            raise RuntimeError("Model must be fitted before decompose")
        imputer = self._estimator.named_steps["impute"]
        ridge = self._estimator.named_steps["ridge"]
        x_imputed = imputer.transform(X)
        columns = canonical_feature_columns()
        coef = np.asarray(ridge.coef_, dtype=np.float64)
        contributions: dict[str, np.ndarray[Any, np.dtype[np.floating[Any]]]] = {}
        for component, comp_cols in _PROPHET_LIKE_COMPONENTS.items():
            idx = [columns.index(c) for c in comp_cols]
            contributions[component] = np.asarray(x_imputed[:, idx] @ coef[idx], dtype=np.float64)
        return ForecastDecomposition(
            intercept=float(ridge.intercept_),
            trend=contributions["trend"],
            seasonality=contributions["seasonality"],
            holiday_regressor=contributions["holiday_regressor"],
        )

    def get_params(self) -> dict[str, Any]:
        """Get model parameters.

        Returns:
            Dictionary with alpha and random_state.
        """
        return {"alpha": self.alpha, "random_state": self.random_state}

    def set_params(self, **params: Any) -> ProphetLikeForecaster:  # noqa: ANN401
        """Set model parameters.

        Args:
            **params: Parameter names and values to set.

        Returns:
            self (for method chaining).
        """
        for key, value in params.items():
            setattr(self, key, value)
        return self


# Type alias for model type literals — keep in sync with ``_MODEL_FAMILY_MAP``
# and the ``ModelConfig`` discriminated union. The
# ``test_model_family_map_covers_every_known_model_type`` test walks
# ``get_args(ModelType)`` to catch drift.
ModelType = Literal[
    "naive",
    "seasonal_naive",
    "moving_average",
    "weighted_moving_average",  # PRP-36
    "seasonal_average",  # PRP-36
    "trend_regression_baseline",  # PRP-36
    "random_forest",  # PRP-36 (optional)
    "xgboost",
    "lightgbm",
    "regression",
    "prophet_like",
]


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
    elif model_type == "weighted_moving_average":
        from app.features.forecasting.schemas import WeightedMovingAverageModelConfig

        if isinstance(config, WeightedMovingAverageModelConfig):
            return WeightedMovingAverageForecaster(
                window_size=config.window_size,
                weight_strategy=config.weight_strategy,
                decay=config.decay,
                random_state=random_state,
            )
        raise ValueError("Invalid config type for weighted_moving_average")
    elif model_type == "seasonal_average":
        from app.features.forecasting.schemas import SeasonalAverageModelConfig

        if isinstance(config, SeasonalAverageModelConfig):
            return SeasonalAverageForecaster(
                season_length=config.season_length,
                lookback_cycles=config.lookback_cycles,
                trim_outliers=config.trim_outliers,
                random_state=random_state,
            )
        raise ValueError("Invalid config type for seasonal_average")
    elif model_type == "trend_regression_baseline":
        from app.features.forecasting.schemas import TrendRegressionBaselineModelConfig

        if isinstance(config, TrendRegressionBaselineModelConfig):
            return TrendRegressionBaselineForecaster(
                alpha=config.alpha,
                include_dow=config.include_dow,
                include_month=config.include_month,
                random_state=random_state,
            )
        raise ValueError("Invalid config type for trend_regression_baseline")
    elif model_type == "random_forest":
        if not settings.forecast_enable_random_forest:
            raise ValueError(
                "random_forest is not enabled. Set forecast_enable_random_forest=True "
                "in settings (PRP-36 — optional feature-aware model)."
            )
        from app.features.forecasting.schemas import RandomForestModelConfig

        if isinstance(config, RandomForestModelConfig):
            return RandomForestForecaster(
                n_estimators=config.n_estimators,
                max_depth=config.max_depth,
                min_samples_leaf=config.min_samples_leaf,
                random_state=random_state,
            )
        raise ValueError("Invalid config type for random_forest")
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
    elif model_type == "xgboost":
        if not settings.forecast_enable_xgboost:
            raise ValueError(
                "XGBoost is not enabled. Set forecast_enable_xgboost=True in settings."
            )
        from app.features.forecasting.schemas import XGBoostModelConfig

        if isinstance(config, XGBoostModelConfig):
            return XGBoostForecaster(
                n_estimators=config.n_estimators,
                learning_rate=config.learning_rate,
                max_depth=config.max_depth,
                random_state=random_state,
            )
        raise ValueError("Invalid config type for xgboost")
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
    elif model_type == "prophet_like":
        # No flag gate — the Prophet-like model is pure scikit-learn and ships
        # always-enabled, exactly like ``regression``.
        from app.features.forecasting.schemas import ProphetLikeModelConfig

        if isinstance(config, ProphetLikeModelConfig):
            return ProphetLikeForecaster(alpha=config.alpha, random_state=random_state)
        raise ValueError("Invalid config type for prophet_like")
    else:
        raise ValueError(f"Unknown model type: {model_type}")
