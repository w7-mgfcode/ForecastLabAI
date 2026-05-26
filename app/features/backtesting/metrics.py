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
    def rmse(
        actuals: np.ndarray[Any, np.dtype[np.floating[Any]]],
        predictions: np.ndarray[Any, np.dtype[np.floating[Any]]],
    ) -> MetricResult:
        """Root Mean Squared Error.

        Formula: ``sqrt(mean((A - F) ** 2))``

        Penalises large errors more than MAE — useful when a forecast that
        misses a single point badly is operationally worse than one that
        misses many points by a little.

        Args:
            actuals: Ground truth values.
            predictions: Predicted values.

        Returns:
            MetricResult with RMSE value (NaN for empty arrays).

        Raises:
            ValueError: If arrays have different lengths.
        """
        warnings: list[str] = []

        if len(actuals) == 0:
            return MetricResult(name="rmse", value=np.nan, n_samples=0, warnings=["Empty array"])

        if len(actuals) != len(predictions):
            raise ValueError(
                f"Length mismatch: actuals={len(actuals)}, predictions={len(predictions)}"
            )

        rmse_value = float(np.sqrt(np.mean((actuals - predictions) ** 2)))

        return MetricResult(
            name="rmse", value=rmse_value, n_samples=len(actuals), warnings=warnings
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
            "rmse": self.rmse(actuals, predictions).value,
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

    def aggregate_bucket_metrics(
        self,
        fold_bucket_metrics: list[dict[str, dict[str, float]]],
    ) -> dict[str, dict[str, float]]:
        """Aggregate per-horizon-bucket metrics across folds (PRP-36).

        For each bucket id present in any fold, compute the per-metric mean
        across the folds that emitted that bucket. Folds that did NOT emit
        a bucket (because no test point fell inside its horizon range — e.g.
        ``h_29_plus`` on a 14-day forecast) are silently skipped: their
        absence reduces the sample count, not the aggregated value.

        Args:
            fold_bucket_metrics: List of per-fold bucket dicts (the structure
                returned by :func:`compute_bucket_metrics`).

        Returns:
            Per-bucket aggregated mean dict; empty when every fold reported
            an empty bucket dict (degenerate "horizon shorter than the
            shortest bucket" case — shouldn't happen given bucket starts
            at 1).
        """
        if not fold_bucket_metrics:
            return {}

        # Collect every (bucket_id, metric) pair that appeared in any fold.
        bucket_metric_values: dict[str, dict[str, list[float]]] = {}
        for fold in fold_bucket_metrics:
            for bucket_id, metric_dict in fold.items():
                bucket = bucket_metric_values.setdefault(bucket_id, {})
                for metric_name, metric_value in metric_dict.items():
                    if not np.isnan(metric_value):
                        bucket.setdefault(metric_name, []).append(metric_value)

        # Compute mean across folds per (bucket, metric).
        aggregated: dict[str, dict[str, float]] = {}
        for bucket_id, metrics in bucket_metric_values.items():
            bucket_means: dict[str, float] = {}
            for metric_name, values in metrics.items():
                if values:
                    bucket_means[metric_name] = float(np.mean(values))
            if bucket_means:
                aggregated[bucket_id] = bucket_means
        return aggregated


HORIZON_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("h_1_7", 1, 7),
    ("h_8_14", 8, 14),
    ("h_15_28", 15, 28),
    ("h_29_plus", 29, None),
)
"""Per-horizon-bucket boundaries (1-based, inclusive ends; ``None`` = unbounded).

Bucket ids are stable JSON-key-safe strings — keep them in sync with
``app/features/backtesting/schemas.py`` and the Slice C frontend reader.
"""


def compute_bucket_metrics(
    actuals: np.ndarray[Any, np.dtype[np.floating[Any]]],
    predictions: np.ndarray[Any, np.dtype[np.floating[Any]]],
    horizon_offsets: list[int],
) -> dict[str, dict[str, float]]:
    """Compute per-horizon-bucket metrics for a single fold (PRP-36).

    Slices the (actuals, predictions) pair by ``horizon_offsets`` lying in
    each bucket's ``[start, end]`` range, then calls
    :meth:`MetricsCalculator.calculate_all` on the slice. Empty buckets are
    dropped from the output (a 14-day horizon's ``h_29_plus`` bucket simply
    does not appear) — Slice C never has to interpret a NaN slot.

    Args:
        actuals: Ground-truth array, length ``H``.
        predictions: Predicted array, length ``H``.
        horizon_offsets: Per-row horizon position, 1-based. Length ``H``.

    Returns:
        ``dict[bucket_id, dict[metric_name, value]]`` keyed by the bucket
        ids from :data:`HORIZON_BUCKETS`. Empty buckets are omitted.

    Raises:
        ValueError: If the three arrays have different lengths.
    """
    if not (len(actuals) == len(predictions) == len(horizon_offsets)):
        raise ValueError(
            f"array length mismatch: actuals={len(actuals)}, "
            f"predictions={len(predictions)}, horizon_offsets={len(horizon_offsets)}"
        )
    if len(actuals) == 0:
        return {}

    calc = MetricsCalculator()
    out: dict[str, dict[str, float]] = {}
    h = np.asarray(horizon_offsets, dtype=np.int64)
    max_h = int(h.max())
    for bucket_id, start, end in HORIZON_BUCKETS:
        upper = end if end is not None else max_h
        mask = (h >= start) & (h <= upper)
        if not mask.any():
            continue
        bucket_actuals = actuals[mask]
        bucket_predictions = predictions[mask]
        out[bucket_id] = calc.calculate_all(bucket_actuals, bucket_predictions)
    return out
