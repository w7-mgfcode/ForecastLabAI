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


def explainer_factory(
    model_type: str,
    season_length: int | None = None,
    window_size: int | None = None,
) -> BaseExplainer:
    """Build the rule-based explainer for a baseline model type.

    Args:
        model_type: One of ``naive``, ``seasonal_naive``, ``moving_average``.
        season_length: Seasonal period for ``seasonal_naive`` (defaults to 7).
        window_size: Averaging window for ``moving_average`` (defaults to 7).

    Returns:
        The matching explainer instance.

    Raises:
        ValueError: For ``lightgbm``/``regression`` (MVP scope guard) or an
            unknown model type.
    """
    if model_type == "naive":
        return NaiveExplainer()
    if model_type == "seasonal_naive":
        return SeasonalNaiveExplainer(season_length=season_length or 7)
    if model_type == "moving_average":
        return MovingAverageExplainer(window_size=window_size or 7)
    if model_type in ("lightgbm", "regression"):
        raise ValueError(
            f"Explanations are available for baseline models only; "
            f"'{model_type}' is not supported (rule-based MVP)."
        )
    raise ValueError(f"Unknown model type: {model_type}")
