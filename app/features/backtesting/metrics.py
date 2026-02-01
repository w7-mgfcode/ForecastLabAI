"""Metrics calculator for forecast evaluation.

Supported Metrics:
- MAE: Mean Absolute Error
- sMAPE: Symmetric Mean Absolute Percentage Error
- WAPE: Weighted Absolute Percentage Error
- Bias: Forecast Bias (positive = under-forecast)
- Stability: Coefficient of variation of per-fold metrics

CRITICAL: All metrics handle edge cases (zeros, empty arrays).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class MetricResult:
    """Result of a single metric calculation.

    Attributes:
        name: Name of the metric.
        value: Calculated value (may be nan for edge cases).
        n_samples: Number of samples used in calculation.
        warnings: List of warnings generated during calculation.
    """

    name: str
    value: float
    n_samples: int
    warnings: list[str] = field(default_factory=lambda: [])


class MetricsCalculator:
    """Calculate forecasting accuracy metrics.

    Provides methods for computing various forecast accuracy metrics
    with proper edge case handling.

    Supported Metrics:
    - MAE: Mean Absolute Error
    - sMAPE: Symmetric Mean Absolute Percentage Error (0-200 scale)
    - WAPE: Weighted Absolute Percentage Error
    - Bias: Forecast Bias (positive = under-forecast)
    - Stability: Coefficient of variation of per-fold metrics

    CRITICAL: All metrics handle edge cases (zeros, empty arrays).
    """

    EPSILON = 1e-10  # Fallback for division by zero

    @staticmethod
    def mae(
        actuals: np.ndarray[Any, np.dtype[np.floating[Any]]],
        predictions: np.ndarray[Any, np.dtype[np.floating[Any]]],
    ) -> MetricResult:
        """Mean Absolute Error.

        Formula: mean(|actual - predicted|)

        Args:
            actuals: Ground truth values.
            predictions: Predicted values.

        Returns:
            MetricResult with MAE value.

        Raises:
            ValueError: If arrays have different lengths.
        """
        warnings: list[str] = []

        if len(actuals) == 0:
            return MetricResult(name="mae", value=np.nan, n_samples=0, warnings=["Empty array"])

        if len(actuals) != len(predictions):
            raise ValueError(
                f"Length mismatch: actuals={len(actuals)}, predictions={len(predictions)}"
            )

        mae_value = float(np.mean(np.abs(actuals - predictions)))

        return MetricResult(name="mae", value=mae_value, n_samples=len(actuals), warnings=warnings)

    @staticmethod
    def smape(
        actuals: np.ndarray[Any, np.dtype[np.floating[Any]]],
        predictions: np.ndarray[Any, np.dtype[np.floating[Any]]],
    ) -> MetricResult:
        """Symmetric Mean Absolute Percentage Error.

        Formula: 100/n * sum(2 * |A - F| / (|A| + |F|))

        CRITICAL: When both A and F are 0, contributes 0 to sum (perfect forecast).
        Uses epsilon fallback to avoid division by zero.

        Args:
            actuals: Ground truth values.
            predictions: Predicted values.

        Returns:
            MetricResult with sMAPE value (0-200 scale).

        Raises:
            ValueError: If arrays have different lengths.
        """
        warnings: list[str] = []

        if len(actuals) == 0:
            return MetricResult(name="smape", value=np.nan, n_samples=0, warnings=["Empty array"])

        if len(actuals) != len(predictions):
            raise ValueError(
                f"Length mismatch: actuals={len(actuals)}, predictions={len(predictions)}"
            )

        numerator = 2.0 * np.abs(actuals - predictions)
        denominator = np.abs(actuals) + np.abs(predictions)

        # Handle zeros: when both are 0, result is 0 (perfect forecast of zero)
        # When denominator is 0 but numerator isn't, use epsilon
        with np.errstate(divide="ignore", invalid="ignore"):
            ratios = np.where(
                (actuals == 0) & (predictions == 0),
                0.0,  # Perfect forecast of zero
                np.where(
                    denominator == 0,
                    2.0,  # Maximum error (shouldn't happen if above handles 0/0)
                    numerator / denominator,
                ),
            )

        smape_value = float(100.0 * np.mean(ratios))

        n_zeros = int(np.sum((actuals == 0) | (predictions == 0)))
        if n_zeros > 0:
            warnings.append(f"{n_zeros} samples with zero values")

        return MetricResult(
            name="smape", value=smape_value, n_samples=len(actuals), warnings=warnings
        )

    @staticmethod
    def wape(
        actuals: np.ndarray[Any, np.dtype[np.floating[Any]]],
        predictions: np.ndarray[Any, np.dtype[np.floating[Any]]],
    ) -> MetricResult:
        """Weighted Absolute Percentage Error.

        Formula: sum(|A - F|) / sum(|A|) * 100

        CRITICAL: Better than MAPE for intermittent/low-volume series.
        Returns inf if sum of actuals is zero.

        Args:
            actuals: Ground truth values.
            predictions: Predicted values.

        Returns:
            MetricResult with WAPE value.

        Raises:
            ValueError: If arrays have different lengths.
        """
        warnings: list[str] = []

        if len(actuals) == 0:
            return MetricResult(name="wape", value=np.nan, n_samples=0, warnings=["Empty array"])

        if len(actuals) != len(predictions):
            raise ValueError(
                f"Length mismatch: actuals={len(actuals)}, predictions={len(predictions)}"
            )

        sum_abs_error = float(np.sum(np.abs(actuals - predictions)))
        sum_abs_actual = float(np.sum(np.abs(actuals)))

        if sum_abs_actual == 0:
            warnings.append("Sum of actuals is zero; WAPE undefined")
            return MetricResult(
                name="wape", value=float("inf"), n_samples=len(actuals), warnings=warnings
            )

        wape_value = (sum_abs_error / sum_abs_actual) * 100.0

        return MetricResult(
            name="wape", value=wape_value, n_samples=len(actuals), warnings=warnings
        )

    @staticmethod
    def bias(
        actuals: np.ndarray[Any, np.dtype[np.floating[Any]]],
        predictions: np.ndarray[Any, np.dtype[np.floating[Any]]],
    ) -> MetricResult:
        """Forecast Bias.

        Formula: mean(actual - predicted)

        Interpretation:
        - Positive: Model under-forecasts (actuals > predictions)
        - Negative: Model over-forecasts (actuals < predictions)
        - Zero: No systematic bias

        Args:
            actuals: Ground truth values.
            predictions: Predicted values.

        Returns:
            MetricResult with Bias value.

        Raises:
            ValueError: If arrays have different lengths.
        """
        warnings: list[str] = []

        if len(actuals) == 0:
            return MetricResult(name="bias", value=np.nan, n_samples=0, warnings=["Empty array"])

        if len(actuals) != len(predictions):
            raise ValueError(
                f"Length mismatch: actuals={len(actuals)}, predictions={len(predictions)}"
            )

        errors = actuals - predictions
        bias_value = float(np.mean(errors))
        error_std = float(np.std(errors))

        if error_std > 0 and abs(bias_value) > error_std:
            warnings.append(
                "Bias exceeds error standard deviation; systematic over/under-forecasting detected"
            )

        return MetricResult(
            name="bias", value=bias_value, n_samples=len(actuals), warnings=warnings
        )

    @staticmethod
    def stability_index(fold_metric_values: list[float]) -> MetricResult:
        """Stability Index (coefficient of variation across folds).

        Formula: std(metrics) / |mean(metrics)| * 100

        Interpretation:
        - Lower is better (more stable model)
        - High values indicate inconsistent performance across time periods

        Args:
            fold_metric_values: List of metric values from each fold.

        Returns:
            MetricResult with Stability Index value.
        """
        warnings: list[str] = []

        # Filter out nan values
        valid_values = [v for v in fold_metric_values if not np.isnan(v)]

        if len(valid_values) < 2:
            return MetricResult(
                name="stability_index",
                value=np.nan,
                n_samples=len(valid_values),
                warnings=["Need at least 2 valid folds for stability calculation"],
            )

        values = np.array(valid_values)
        mean_val = float(np.mean(values))
        std_val = float(np.std(values))

        if mean_val == 0:
            warnings.append("Mean is zero; stability index undefined")
            return MetricResult(
                name="stability_index",
                value=float("inf"),
                n_samples=len(valid_values),
                warnings=warnings,
            )

        stability = (std_val / abs(mean_val)) * 100.0

        if stability > 50:
            warnings.append(
                "High instability (>50%); model performance varies significantly across folds"
            )

        return MetricResult(
            name="stability_index", value=stability, n_samples=len(valid_values), warnings=warnings
        )

    def calculate_all(
        self,
        actuals: np.ndarray[Any, np.dtype[np.floating[Any]]],
        predictions: np.ndarray[Any, np.dtype[np.floating[Any]]],
    ) -> dict[str, float]:
        """Calculate all point metrics for a single fold.

        Args:
            actuals: Ground truth values.
            predictions: Predicted values.

        Returns:
            Dictionary of metric name to value.
        """
        return {
            "mae": self.mae(actuals, predictions).value,
            "smape": self.smape(actuals, predictions).value,
            "wape": self.wape(actuals, predictions).value,
            "bias": self.bias(actuals, predictions).value,
        }

    def aggregate_fold_metrics(
        self,
        fold_metrics: list[dict[str, float]],
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Aggregate metrics across folds.

        Args:
            fold_metrics: List of per-fold metric dictionaries.

        Returns:
            Tuple of (aggregated_means, stability_indices).
        """
        if not fold_metrics:
            return {}, {}

        metric_names = list(fold_metrics[0].keys())
        aggregated: dict[str, float] = {}
        stability: dict[str, float] = {}

        for name in metric_names:
            values = [fm[name] for fm in fold_metrics if not np.isnan(fm[name])]
            if values:
                aggregated[name] = float(np.mean(values))
                stability_result = self.stability_index(values)
                stability[f"{name}_stability"] = stability_result.value
            else:
                aggregated[name] = np.nan
                stability[f"{name}_stability"] = np.nan

        return aggregated, stability
