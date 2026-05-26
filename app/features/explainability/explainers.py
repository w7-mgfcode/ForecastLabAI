"""Rule-based, deterministic explainers for the three baseline forecasters.

Each explainer MIRRORS the exact h=1 math of the matching forecaster in
``app/features/forecasting/models.py`` — a rule-based explainer is *exact*, not
an approximation. ``test_explainers.py`` asserts each explainer's forecast value
equals the real forecaster's ``.fit(y).predict(1)[0]`` on the same series.

A driver with ``contribution == 0.0`` is informational context only — the
baseline model does not consume it. The sum of all driver contributions equals
the forecast value.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np

from app.features.explainability.schemas import (
    ConfidenceLevel,
    Direction,
    DriverContribution,
)
from app.features.forecasting.models import (
    build_trend_baseline_design_row,
    compute_seasonal_average_for_offset,
    compute_weighted_average_weights,
)

# A 1-D float series, matching the forecasters' target-array type.
FloatArray = np.ndarray[Any, np.dtype[np.floating[Any]]]

# Below this many observations a naive explanation is treated as low-confidence.
_NAIVE_MIN_COMFORTABLE = 14


def _direction(value: float) -> Direction:
    """Map a signed value to a driver direction literal."""
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


class BaseExplainer(ABC):
    """Abstract base for a rule-based forecast explainer."""

    @abstractmethod
    def explain(self, y: FloatArray) -> tuple[float, list[DriverContribution]]:
        """Decompose the h=1 forecast into named driver contributions.

        Args:
            y: The historical target series (time-ordered, ``<= as_of_date``).

        Returns:
            The h=1 forecast value and its ordered driver contributions.

        Raises:
            ValueError: If the series is too short to produce the forecast.
        """

    @abstractmethod
    def confidence(self, y: FloatArray) -> ConfidenceLevel:
        """Return a qualitative confidence band for the explanation.

        Args:
            y: The historical target series.

        Returns:
            The confidence band.
        """


class NaiveExplainer(BaseExplainer):
    """Explainer for the naive forecaster — the forecast IS the last value."""

    def explain(self, y: FloatArray) -> tuple[float, list[DriverContribution]]:
        """Decompose the naive h=1 forecast.

        Args:
            y: The historical target series.

        Returns:
            The h=1 forecast (``y[-1]``) and its driver contributions.

        Raises:
            ValueError: If ``y`` is empty.
        """
        if len(y) == 0:
            raise ValueError("Cannot explain an empty series")
        forecast = float(y[-1])
        drivers = [
            DriverContribution(
                name="last_observation",
                feature_value=forecast,
                contribution=forecast,
                direction="positive",
                description="The naive forecast is exactly the last observed value.",
            )
        ]
        if len(y) >= _NAIVE_MIN_COMFORTABLE:
            trend = float(np.mean(y[-7:]) - np.mean(y[-14:-7]))
            drivers.append(
                DriverContribution(
                    name="recent_trend",
                    feature_value=trend,
                    contribution=0.0,
                    direction=_direction(trend),
                    description=(
                        "Context only — week-over-week change in mean demand; "
                        "the naive model does not use trend."
                    ),
                )
            )
        return forecast, drivers

    def confidence(self, y: FloatArray) -> ConfidenceLevel:
        """Return ``LOW`` for a short series, otherwise ``MEDIUM``."""
        if len(y) < _NAIVE_MIN_COMFORTABLE:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.MEDIUM


class SeasonalNaiveExplainer(BaseExplainer):
    """Explainer for the seasonal-naive forecaster — last season's value."""

    def __init__(self, season_length: int = 7) -> None:
        """Initialise the explainer.

        Args:
            season_length: Seasonal period in days (must be >= 1).

        Raises:
            ValueError: If ``season_length`` < 1.
        """
        if season_length < 1:
            raise ValueError(f"season_length must be >= 1, got {season_length}")
        self.season_length = season_length

    def explain(self, y: FloatArray) -> tuple[float, list[DriverContribution]]:
        """Decompose the seasonal-naive h=1 forecast.

        Args:
            y: The historical target series.

        Returns:
            The h=1 forecast (``y[-season_length]``) and its driver contributions.

        Raises:
            ValueError: If ``y`` has fewer observations than ``season_length``.
        """
        if len(y) < self.season_length:
            raise ValueError(f"Need at least {self.season_length} observations")
        forecast = float(y[-self.season_length])
        drivers = [
            DriverContribution(
                name="season_match",
                feature_value=forecast,
                contribution=forecast,
                direction="positive",
                description=(
                    f"The forecast repeats the value observed {self.season_length} "
                    "days ago (one seasonal cycle back)."
                ),
            )
        ]
        return forecast, drivers

    def confidence(self, y: FloatArray) -> ConfidenceLevel:
        """Return ``LOW`` for under two seasonal cycles, otherwise ``MEDIUM``."""
        if len(y) < 2 * self.season_length:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.MEDIUM


class MovingAverageExplainer(BaseExplainer):
    """Explainer for the moving-average forecaster — mean of the last window."""

    def __init__(self, window_size: int = 7) -> None:
        """Initialise the explainer.

        Args:
            window_size: Averaging window in days (must be >= 1).

        Raises:
            ValueError: If ``window_size`` < 1.
        """
        if window_size < 1:
            raise ValueError(f"window_size must be >= 1, got {window_size}")
        self.window_size = window_size

    def explain(self, y: FloatArray) -> tuple[float, list[DriverContribution]]:
        """Decompose the moving-average h=1 forecast.

        Args:
            y: The historical target series.

        Returns:
            The h=1 forecast (``mean(y[-window_size:])``) and driver contributions.

        Raises:
            ValueError: If ``y`` has fewer observations than ``window_size``.
        """
        if len(y) < self.window_size:
            raise ValueError(f"Need at least {self.window_size} observations")
        window = y[-self.window_size :]
        forecast = float(np.mean(window))
        dispersion = float(np.std(window))
        drivers = [
            DriverContribution(
                name="window_mean",
                feature_value=forecast,
                contribution=forecast,
                direction="positive",
                description=(
                    f"The forecast is the mean of the last {self.window_size} observed values."
                ),
            ),
            DriverContribution(
                name="window_dispersion",
                feature_value=dispersion,
                contribution=0.0,
                direction="neutral",
                description=(
                    "Context only — standard deviation within the averaging "
                    "window; higher values mean a noisier, less reliable mean."
                ),
            ),
        ]
        return forecast, drivers

    def confidence(self, y: FloatArray) -> ConfidenceLevel:
        """Return ``HIGH`` for a stable full window, ``MEDIUM``/``LOW`` otherwise."""
        if len(y) < self.window_size:
            return ConfidenceLevel.LOW
        window = y[-self.window_size :]
        mean = float(np.mean(window))
        std = float(np.std(window))
        cv = std / mean if mean > 0 else 0.0
        if cv < 0.5:
            return ConfidenceLevel.HIGH
        return ConfidenceLevel.MEDIUM


class WeightedMovingAverageExplainer(BaseExplainer):
    """Explainer for the weighted-moving-average baseline (PRP-36).

    Mirrors :class:`MovingAverageExplainer` but reports the weight strategy
    in the driver description. The h=1 forecast is
    ``np.average(y[-window_size:], weights=...)`` exactly.
    """

    def __init__(
        self,
        window_size: int = 7,
        weight_strategy: str = "linear",
        decay: float = 0.7,
    ) -> None:
        if window_size < 2:
            raise ValueError(f"window_size must be >= 2, got {window_size}")
        if weight_strategy not in ("linear", "exponential"):
            raise ValueError(
                f"weight_strategy must be 'linear' or 'exponential', got {weight_strategy!r}"
            )
        if not 0.0 < decay < 1.0:
            raise ValueError(f"decay must lie in (0.0, 1.0), got {decay}")
        self.window_size = window_size
        self.weight_strategy = weight_strategy
        self.decay = decay

    def _weights(self) -> FloatArray:
        # Reuses the forecaster's weight-construction helper so the
        # explainer and the forecaster never drift.
        return compute_weighted_average_weights(
            window_size=self.window_size,
            weight_strategy=self.weight_strategy,  # type: ignore[arg-type]
            decay=self.decay,
        )

    def explain(self, y: FloatArray) -> tuple[float, list[DriverContribution]]:
        if len(y) < self.window_size:
            raise ValueError(f"Need at least {self.window_size} observations")
        window = y[-self.window_size :]
        weights = self._weights()
        forecast = float(np.average(window, weights=weights))
        dispersion = float(np.std(window))
        drivers = [
            DriverContribution(
                name="weighted_window_mean",
                feature_value=forecast,
                contribution=forecast,
                direction="positive",
                description=(
                    f"The forecast is the {self.weight_strategy}-weighted mean of the "
                    f"last {self.window_size} observed values"
                    + (f" (decay={self.decay})." if self.weight_strategy == "exponential" else ".")
                ),
            ),
            DriverContribution(
                name="window_dispersion",
                feature_value=dispersion,
                contribution=0.0,
                direction="neutral",
                description=(
                    "Context only — standard deviation within the averaging "
                    "window; higher values mean a noisier, less reliable mean."
                ),
            ),
        ]
        return forecast, drivers

    def confidence(self, y: FloatArray) -> ConfidenceLevel:
        if len(y) < self.window_size:
            return ConfidenceLevel.LOW
        window = y[-self.window_size :]
        mean = float(np.mean(window))
        std = float(np.std(window))
        cv = std / mean if mean > 0 else 0.0
        if cv < 0.5:
            return ConfidenceLevel.HIGH
        return ConfidenceLevel.MEDIUM


class SeasonalAverageExplainer(BaseExplainer):
    """Explainer for the seasonal-average baseline (PRP-36).

    Mirrors :class:`SeasonalAverageForecaster.predict` for ``horizon=1``:
    horizon day 1 maps to offsets ``{1*S - 1, 2*S - 1, ...}`` from the end
    of the stored history. The h=1 forecast is the mean (or trimmed mean
    when ``trim_outliers=True`` AND ≥4 samples are present) of those
    sampled values.
    """

    def __init__(
        self,
        season_length: int = 7,
        lookback_cycles: int = 4,
        trim_outliers: bool = False,
    ) -> None:
        if season_length < 2:
            raise ValueError(f"season_length must be >= 2, got {season_length}")
        if lookback_cycles < 2:
            raise ValueError(f"lookback_cycles must be >= 2, got {lookback_cycles}")
        self.season_length = season_length
        self.lookback_cycles = lookback_cycles
        self.trim_outliers = trim_outliers

    def explain(self, y: FloatArray) -> tuple[float, list[DriverContribution]]:
        min_required = self.season_length * 2
        if len(y) < min_required:
            raise ValueError(f"Need at least {min_required} observations")
        # PRP-36 — single source of truth shared with the forecaster.
        forecast, samples_used, samples_after_trim = compute_seasonal_average_for_offset(
            history=y,
            season_length=self.season_length,
            lookback_cycles=self.lookback_cycles,
            target_offset=1,  # h=1 — the only horizon the explainer reports.
            trim_outliers=self.trim_outliers,
        )
        used_trim = self.trim_outliers and len(samples_used) >= 4
        trim_note = " after trimming the min + max samples" if used_trim else ""
        # Dispersion is reported on the SAME array the forecast was
        # averaged from — trimmed when trimming applied, raw otherwise —
        # so the value matches the "what we averaged" semantic.
        drivers = [
            DriverContribution(
                name="seasonal_window_mean",
                feature_value=float(forecast),
                contribution=float(forecast),
                direction="positive",
                description=(
                    f"The forecast averages the values from the last {len(samples_used)} "
                    f"matching seasonal positions (every {self.season_length} days){trim_note}."
                ),
            ),
            DriverContribution(
                name="sample_dispersion",
                feature_value=float(np.std(samples_after_trim)),
                contribution=0.0,
                direction="neutral",
                description=(
                    "Context only — standard deviation across the sampled "
                    "seasonal positions actually averaged (post-trim when "
                    "trim_outliers is on)."
                ),
            ),
        ]
        return forecast, drivers

    def confidence(self, y: FloatArray) -> ConfidenceLevel:
        if len(y) < self.season_length * self.lookback_cycles:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.MEDIUM


class TrendRegressionBaselineExplainer(BaseExplainer):
    """Explainer for the Ridge trend baseline (PRP-36).

    Surfaces the Ridge coefficients learned on the synthetic elapsed-day
    + optional dow/month design. Unlike the target-only baselines, this
    explainer requires a fitted Ridge — the service passes ``coef_`` +
    ``intercept_`` in via :class:`_FittedRidgeBundle` rather than re-fitting
    inside ``explain`` (re-fitting would re-engineer the design matrix,
    losing the ``include_dow`` / ``include_month`` toggles).
    """

    def __init__(
        self,
        intercept: float,
        coefficients: list[float],
        include_dow: bool = True,
        include_month: bool = True,
    ) -> None:
        self.intercept = intercept
        self.coefficients = list(coefficients)
        self.include_dow = include_dow
        self.include_month = include_month

    def explain(self, y: FloatArray) -> tuple[float, list[DriverContribution]]:
        if len(y) < 2:
            raise ValueError("Need at least 2 observations")
        elapsed_day = len(y)
        # h=1 elapsed-day continuation: the next index after training. The
        # design row is built via the SAME helper the forecaster's
        # ``_design_row`` wraps — single source of truth for the encoding.
        cols_arr = build_trend_baseline_design_row(
            elapsed_day=elapsed_day,
            include_dow=self.include_dow,
            include_month=self.include_month,
        )
        cols: list[float] = [float(v) for v in cols_arr]
        if len(cols) != len(self.coefficients):
            raise ValueError(
                f"design row width ({len(cols)}) != coefficient count ({len(self.coefficients)})"
            )
        contributions = [c * coef for c, coef in zip(cols, self.coefficients, strict=True)]
        forecast = float(self.intercept + sum(contributions))
        drivers: list[DriverContribution] = [
            DriverContribution(
                name="trend_intercept",
                feature_value=1.0,
                contribution=float(self.intercept),
                direction=_direction(self.intercept),
                description="Ridge intercept (baseline level before any covariates).",
            ),
            DriverContribution(
                name="elapsed_day",
                feature_value=float(elapsed_day),
                contribution=float(contributions[0]),
                direction=_direction(contributions[0]),
                description=(
                    "Linear trend term — the slope Ridge fitted on the "
                    "elapsed-day index times the next-day value."
                ),
            ),
        ]
        if self.include_dow:
            dow_contribution = sum(contributions[1:8])
            drivers.append(
                DriverContribution(
                    name="day_of_week",
                    feature_value=float(elapsed_day % 7),
                    contribution=float(dow_contribution),
                    direction=_direction(dow_contribution),
                    description=("Calendar-cycle DOW one-hot effect for the forecasted day."),
                )
            )
        if self.include_month:
            offset = 8 if self.include_dow else 1
            month_contribution = sum(contributions[offset : offset + 12])
            drivers.append(
                DriverContribution(
                    name="month_of_year",
                    feature_value=float((elapsed_day // 30) % 12),
                    contribution=float(month_contribution),
                    direction=_direction(month_contribution),
                    description=("Calendar-cycle month one-hot effect for the forecasted day."),
                )
            )
        return forecast, drivers

    def confidence(self, y: FloatArray) -> ConfidenceLevel:
        if len(y) < 30:
            return ConfidenceLevel.LOW
        if len(y) < 90:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.HIGH


def explainer_factory(
    model_type: str,
    season_length: int | None = None,
    window_size: int | None = None,
    weight_strategy: str | None = None,
    decay: float | None = None,
    lookback_cycles: int | None = None,
    trim_outliers: bool | None = None,
    trend_baseline_bundle: tuple[float, list[float], bool, bool] | None = None,
) -> BaseExplainer:
    """Build the rule-based explainer for a baseline model type.

    Args:
        model_type: One of ``naive``, ``seasonal_naive``, ``moving_average``,
            ``weighted_moving_average``, ``seasonal_average``, or
            ``trend_regression_baseline``.
        season_length: Seasonal period for ``seasonal_naive`` / ``seasonal_average``.
        window_size: Window for ``moving_average`` / ``weighted_moving_average``.
        weight_strategy: ``'linear'`` or ``'exponential'`` (weighted MA).
        decay: Geometric decay for exponential WMA.
        lookback_cycles: Cycles to average over (seasonal_average).
        trim_outliers: Drop min + max per bucket (seasonal_average).
        trend_baseline_bundle: ``(intercept, coefficients, include_dow,
            include_month)`` for ``trend_regression_baseline`` — caller
            supplies the fitted Ridge state.

    Returns:
        The matching explainer instance.

    Raises:
        ValueError: For ``lightgbm``/``regression``/``xgboost``/``random_forest``
            /``prophet_like`` (MVP scope guard — feature-aware models route
            through a different code path) or an unknown model type.
    """
    if model_type == "naive":
        return NaiveExplainer()
    if model_type == "seasonal_naive":
        return SeasonalNaiveExplainer(season_length=season_length or 7)
    if model_type == "moving_average":
        return MovingAverageExplainer(window_size=window_size or 7)
    if model_type == "weighted_moving_average":
        return WeightedMovingAverageExplainer(
            window_size=window_size or 7,
            weight_strategy=weight_strategy or "linear",
            decay=decay if decay is not None else 0.7,
        )
    if model_type == "seasonal_average":
        return SeasonalAverageExplainer(
            season_length=season_length or 7,
            lookback_cycles=lookback_cycles or 4,
            trim_outliers=bool(trim_outliers) if trim_outliers is not None else False,
        )
    if model_type == "trend_regression_baseline":
        if trend_baseline_bundle is None:
            raise ValueError(
                "trend_regression_baseline explainer requires trend_baseline_bundle "
                "(intercept, coefficients, include_dow, include_month) from the fitted Ridge."
            )
        intercept, coefficients, include_dow, include_month = trend_baseline_bundle
        return TrendRegressionBaselineExplainer(
            intercept=intercept,
            coefficients=coefficients,
            include_dow=include_dow,
            include_month=include_month,
        )
    if model_type in ("lightgbm", "regression", "xgboost", "random_forest", "prophet_like"):
        raise ValueError(
            f"Explanations are available for baseline models only; "
            f"'{model_type}' is not supported (rule-based MVP)."
        )
    raise ValueError(f"Unknown model type: {model_type}")
