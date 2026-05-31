"""Tests for backtesting metrics calculator."""

import math

import numpy as np
import pytest

from app.features.backtesting.metrics import (
    HORIZON_BUCKETS,
    MetricsCalculator,
    compute_bucket_metrics,
)


class TestMAE:
    """Tests for Mean Absolute Error calculation."""

    def test_mae_perfect_predictions(self) -> None:
        """Test MAE is 0 for perfect predictions."""
        calc = MetricsCalculator()
        actuals = np.array([10.0, 20.0, 30.0])
        predictions = np.array([10.0, 20.0, 30.0])

        result = calc.mae(actuals, predictions)
        assert result.value == 0.0

    def test_mae_known_values(self) -> None:
        """Test MAE with known values."""
        calc = MetricsCalculator()
        actuals = np.array([10.0, 20.0, 30.0])
        predictions = np.array([12.0, 18.0, 33.0])

        # |10-12| + |20-18| + |30-33| = 2 + 2 + 3 = 7
        # MAE = 7/3 = 2.333...
        result = calc.mae(actuals, predictions)
        assert result.value == pytest.approx(7 / 3)

    def test_mae_negative_errors(self) -> None:
        """Test MAE handles negative errors correctly."""
        calc = MetricsCalculator()
        actuals = np.array([10.0, 20.0])
        predictions = np.array([15.0, 15.0])  # Over and under

        # |10-15| + |20-15| = 5 + 5 = 10
        # MAE = 10/2 = 5
        result = calc.mae(actuals, predictions)
        assert result.value == 5.0

    def test_mae_n_samples(self) -> None:
        """Test MAE returns correct n_samples."""
        calc = MetricsCalculator()
        actuals = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        predictions = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        result = calc.mae(actuals, predictions)
        assert result.n_samples == 5


class TestSMAPE:
    """Tests for Symmetric Mean Absolute Percentage Error calculation."""

    def test_smape_perfect_predictions(self) -> None:
        """Test sMAPE is 0 for perfect predictions."""
        calc = MetricsCalculator()
        actuals = np.array([10.0, 20.0, 30.0])
        predictions = np.array([10.0, 20.0, 30.0])

        result = calc.smape(actuals, predictions)
        assert result.value == 0.0

    def test_smape_known_values(self) -> None:
        """Test sMAPE with known values."""
        calc = MetricsCalculator()
        actuals = np.array([100.0])
        predictions = np.array([80.0])

        # |100-80| / (|100|+|80|) * 200 = 20/180 * 200 = 22.22...
        result = calc.smape(actuals, predictions)
        expected = (20 / 180) * 200
        assert result.value == pytest.approx(expected)

    def test_smape_range_0_to_200(self) -> None:
        """Test sMAPE is in range 0-200."""
        calc = MetricsCalculator()
        actuals = np.array([100.0, 50.0, 25.0])
        predictions = np.array([0.0, 100.0, 0.0])  # Extreme predictions

        result = calc.smape(actuals, predictions)
        assert 0 <= result.value <= 200

    def test_smape_both_zero_returns_zero(self) -> None:
        """Test sMAPE returns 0 when both actual and prediction are 0."""
        calc = MetricsCalculator()
        actuals = np.array([0.0, 10.0, 0.0])
        predictions = np.array([0.0, 10.0, 0.0])

        result = calc.smape(actuals, predictions)
        assert result.value == 0.0

    def test_smape_actual_zero_pred_nonzero(self) -> None:
        """Test sMAPE when actual is 0 but prediction is not."""
        calc = MetricsCalculator()
        actuals = np.array([0.0])
        predictions = np.array([10.0])

        # |0-10| / (|0|+|10|) * 200 = 10/10 * 200 = 200
        result = calc.smape(actuals, predictions)
        assert result.value == 200.0

    def test_smape_symmetric(self) -> None:
        """Test sMAPE is symmetric (actual/pred interchangeable)."""
        calc = MetricsCalculator()
        actuals1 = np.array([100.0])
        predictions1 = np.array([80.0])

        actuals2 = np.array([80.0])
        predictions2 = np.array([100.0])

        result1 = calc.smape(actuals1, predictions1)
        result2 = calc.smape(actuals2, predictions2)

        assert result1.value == pytest.approx(result2.value)


class TestWAPE:
    """Tests for Weighted Absolute Percentage Error calculation."""

    def test_wape_perfect_predictions(self) -> None:
        """Test WAPE is 0 for perfect predictions."""
        calc = MetricsCalculator()
        actuals = np.array([10.0, 20.0, 30.0])
        predictions = np.array([10.0, 20.0, 30.0])

        result = calc.wape(actuals, predictions)
        assert result.value == 0.0

    def test_wape_known_values(self) -> None:
        """Test WAPE with known values."""
        calc = MetricsCalculator()
        actuals = np.array([100.0, 200.0])
        predictions = np.array([90.0, 220.0])

        # sum(|errors|) / sum(|actuals|) * 100
        # (10 + 20) / 300 * 100 = 10%
        result = calc.wape(actuals, predictions)
        assert result.value == pytest.approx(10.0)

    def test_wape_zero_actuals_returns_inf(self) -> None:
        """Test WAPE returns inf when sum of actuals is zero."""
        calc = MetricsCalculator()
        actuals = np.array([0.0, 0.0, 0.0])
        predictions = np.array([1.0, 2.0, 3.0])

        result = calc.wape(actuals, predictions)
        assert math.isinf(result.value)
        assert len(result.warnings) > 0

    def test_wape_weighted_properly(self) -> None:
        """Test WAPE weights larger actuals more heavily."""
        calc = MetricsCalculator()
        # Same absolute error (10) but different actuals
        actuals = np.array([10.0, 100.0])
        predictions = np.array([0.0, 90.0])

        # sum(|errors|) / sum(|actuals|) * 100
        # (10 + 10) / 110 * 100 = 18.18%
        result = calc.wape(actuals, predictions)
        assert result.value == pytest.approx(20 / 110 * 100)


class TestBias:
    """Tests for Forecast Bias calculation."""

    def test_bias_no_bias(self) -> None:
        """Test bias is 0 when over/under predictions cancel out."""
        calc = MetricsCalculator()
        actuals = np.array([10.0, 20.0])
        predictions = np.array([15.0, 15.0])  # +5 and -5 cancel

        result = calc.bias(actuals, predictions)
        assert result.value == pytest.approx(0.0)

    def test_bias_positive_under_forecast(self) -> None:
        """Test positive bias indicates under-forecasting."""
        calc = MetricsCalculator()
        actuals = np.array([100.0, 100.0])
        predictions = np.array([80.0, 80.0])

        # Bias = mean(actuals - predictions) = mean(20, 20) = 20
        result = calc.bias(actuals, predictions)
        assert result.value == 20.0

    def test_bias_negative_over_forecast(self) -> None:
        """Test negative bias indicates over-forecasting."""
        calc = MetricsCalculator()
        actuals = np.array([100.0, 100.0])
        predictions = np.array([120.0, 120.0])

        # Bias = mean(actuals - predictions) = mean(-20, -20) = -20
        result = calc.bias(actuals, predictions)
        assert result.value == -20.0


class TestCalculateAll:
    """Tests for calculate_all method."""

    def test_calculate_all_returns_all_metrics(self) -> None:
        """Test calculate_all returns all expected metrics."""
        calc = MetricsCalculator()
        actuals = np.array([10.0, 20.0, 30.0])
        predictions = np.array([12.0, 18.0, 33.0])

        result = calc.calculate_all(actuals, predictions)

        assert "mae" in result
        assert "rmse" in result  # PRP-36 — RMSE added alongside MAE/sMAPE/WAPE/bias.
        assert "smape" in result
        assert "wape" in result
        assert "bias" in result

    def test_calculate_all_values_consistent(self) -> None:
        """Test calculate_all values match individual calculations."""
        calc = MetricsCalculator()
        actuals = np.array([10.0, 20.0, 30.0])
        predictions = np.array([12.0, 18.0, 33.0])

        all_metrics = calc.calculate_all(actuals, predictions)

        assert all_metrics["mae"] == calc.mae(actuals, predictions).value
        assert all_metrics["rmse"] == calc.rmse(actuals, predictions).value
        assert all_metrics["smape"] == calc.smape(actuals, predictions).value
        assert all_metrics["wape"] == calc.wape(actuals, predictions).value
        assert all_metrics["bias"] == calc.bias(actuals, predictions).value


class TestAggregateFoldMetrics:
    """Tests for aggregate_fold_metrics method."""

    def test_aggregate_computes_mean(self) -> None:
        """Test aggregation computes mean across folds."""
        calc = MetricsCalculator()
        fold_metrics = [
            {"mae": 10.0, "smape": 20.0},
            {"mae": 20.0, "smape": 40.0},
            {"mae": 30.0, "smape": 60.0},
        ]

        aggregated, _ = calc.aggregate_fold_metrics(fold_metrics)

        assert aggregated["mae"] == pytest.approx(20.0)  # mean of 10, 20, 30
        assert aggregated["smape"] == pytest.approx(40.0)  # mean of 20, 40, 60

    def test_aggregate_computes_stability(self) -> None:
        """Test aggregation computes stability index (coefficient of variation)."""
        calc = MetricsCalculator()
        fold_metrics = [
            {"mae": 10.0},
            {"mae": 20.0},
            {"mae": 30.0},
        ]

        _, stability = calc.aggregate_fold_metrics(fold_metrics)

        # Stability = std/mean * 100 = sqrt(200/3)/20 * 100 ≈ 40.82%
        expected_std = np.std([10.0, 20.0, 30.0])
        expected_mean = np.mean([10.0, 20.0, 30.0])
        expected_stability = (expected_std / expected_mean) * 100
        assert stability["mae_stability"] == pytest.approx(expected_stability)

    def test_aggregate_empty_folds(self) -> None:
        """Test aggregation handles empty fold list."""
        calc = MetricsCalculator()
        fold_metrics: list[dict[str, float]] = []

        aggregated, std = calc.aggregate_fold_metrics(fold_metrics)

        assert aggregated == {}
        assert std == {}

    def test_aggregate_single_fold(self) -> None:
        """Test aggregation with single fold."""
        calc = MetricsCalculator()
        fold_metrics = [{"mae": 15.0, "smape": 25.0}]

        aggregated, stability = calc.aggregate_fold_metrics(fold_metrics)

        assert aggregated["mae"] == 15.0
        assert aggregated["smape"] == 25.0
        # Single fold: stability_index returns nan (need at least 2 folds)
        assert np.isnan(stability["mae_stability"])
        assert np.isnan(stability["smape_stability"])


class TestStabilityIndex:
    """Tests for stability index calculation."""

    def test_stability_index_perfect_stability(self) -> None:
        """Test stability index is 0 for identical values."""
        calc = MetricsCalculator()
        values = [10.0, 10.0, 10.0, 10.0]

        result = calc.stability_index(values)
        assert result.value == 0.0

    def test_stability_index_known_cv(self) -> None:
        """Test stability index with known coefficient of variation."""
        calc = MetricsCalculator()
        # Values with known std and mean
        values = [10.0, 20.0, 30.0]
        # std ≈ 8.165, mean = 20
        # CV = 8.165 / 20 * 100 ≈ 40.82%

        result = calc.stability_index(values)
        expected_cv = (np.std(values) / np.mean(values)) * 100
        assert result.value == pytest.approx(expected_cv)

    def test_stability_index_zero_mean(self) -> None:
        """Test stability index handles zero mean."""
        calc = MetricsCalculator()
        values = [-10.0, 0.0, 10.0]  # mean = 0

        result = calc.stability_index(values)
        assert math.isinf(result.value)
        assert len(result.warnings) > 0

    def test_stability_higher_for_variable_data(self) -> None:
        """Test higher stability index for more variable data."""
        calc = MetricsCalculator()
        stable = [100.0, 101.0, 99.0, 100.0]
        variable = [50.0, 100.0, 150.0, 200.0]

        stable_result = calc.stability_index(stable)
        variable_result = calc.stability_index(variable)

        assert variable_result.value > stable_result.value


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_single_sample(self) -> None:
        """Test metrics work with single sample."""
        calc = MetricsCalculator()
        actuals = np.array([100.0])
        predictions = np.array([90.0])

        result = calc.calculate_all(actuals, predictions)

        assert result["mae"] == 10.0
        assert result["bias"] == 10.0

    def test_large_values(self) -> None:
        """Test metrics handle large values correctly."""
        calc = MetricsCalculator()
        actuals = np.array([1e9, 2e9, 3e9])
        predictions = np.array([1.1e9, 1.9e9, 3.1e9])

        result = calc.calculate_all(actuals, predictions)

        # Should compute without overflow
        assert not math.isnan(result["mae"])
        assert not math.isnan(result["smape"])

    def test_small_values(self) -> None:
        """Test metrics handle small values correctly."""
        calc = MetricsCalculator()
        actuals = np.array([0.001, 0.002, 0.003])
        predictions = np.array([0.0011, 0.0019, 0.0031])

        result = calc.calculate_all(actuals, predictions)

        # Should compute without underflow issues
        assert not math.isnan(result["mae"])
        assert not math.isnan(result["smape"])

    def test_mixed_positive_negative_actuals(self) -> None:
        """Test metrics handle mixed positive/negative actuals."""
        calc = MetricsCalculator()
        actuals = np.array([-10.0, 0.0, 10.0])
        predictions = np.array([-8.0, 2.0, 8.0])

        # MAE should still work
        mae_result = calc.mae(actuals, predictions)
        assert mae_result.value == pytest.approx(2.0)  # mean of |2|, |2|, |2|


class TestRMSE:
    """Tests for Root Mean Squared Error (PRP-36)."""

    def test_rmse_perfect_predictions(self) -> None:
        """Perfect predictions yield RMSE == 0."""
        calc = MetricsCalculator()
        actuals = np.array([10.0, 20.0, 30.0])
        predictions = np.array([10.0, 20.0, 30.0])
        assert calc.rmse(actuals, predictions).value == 0.0

    def test_rmse_known_values(self) -> None:
        """RMSE matches the closed-form formula."""
        calc = MetricsCalculator()
        actuals = np.array([10.0, 20.0, 30.0])
        predictions = np.array([12.0, 18.0, 33.0])
        # errors: [-2, 2, -3] → sq: [4, 4, 9] → mean=17/3 → sqrt≈2.380
        assert calc.rmse(actuals, predictions).value == pytest.approx(np.sqrt(17.0 / 3.0))

    def test_rmse_penalises_large_errors_more_than_mae(self) -> None:
        """A single big miss surfaces in RMSE more strongly than in MAE."""
        calc = MetricsCalculator()
        actuals = np.array([10.0, 10.0, 10.0])
        even = np.array([8.0, 8.0, 8.0])  # MAE=2, RMSE=2 (uniform error)
        spiky = np.array([10.0, 10.0, 4.0])  # MAE=2, RMSE=sqrt(12)≈3.46
        assert calc.rmse(actuals, even).value == pytest.approx(calc.mae(actuals, even).value)
        assert calc.rmse(actuals, spiky).value > calc.mae(actuals, spiky).value

    def test_rmse_empty_array_returns_nan(self) -> None:
        """Empty inputs return NaN with a warning."""
        calc = MetricsCalculator()
        result = calc.rmse(np.array([]), np.array([]))
        assert math.isnan(result.value)
        assert result.n_samples == 0
        assert "Empty array" in result.warnings

    def test_rmse_length_mismatch_raises(self) -> None:
        """Different-length arrays surface as ValueError."""
        calc = MetricsCalculator()
        with pytest.raises(ValueError, match="Length mismatch"):
            calc.rmse(np.array([1.0, 2.0]), np.array([1.0]))


class TestComputeBucketMetrics:
    """Tests for the per-horizon-bucket helper (PRP-36)."""

    def test_horizon_buckets_constant_shape(self) -> None:
        """HORIZON_BUCKETS exposes four buckets with the documented boundaries."""
        ids = [b[0] for b in HORIZON_BUCKETS]
        assert ids == ["h_1_7", "h_8_14", "h_15_28", "h_29_plus"]
        assert HORIZON_BUCKETS[-1][2] is None  # h_29_plus is unbounded.

    def test_compute_buckets_full_horizon_emits_all_present(self) -> None:
        """A 30-day horizon spans all four buckets — they should all appear."""
        actuals = np.arange(1.0, 31.0)  # 30 days
        predictions = actuals + 1.0  # uniform +1 error
        horizon_offsets = list(range(1, 31))
        result = compute_bucket_metrics(actuals, predictions, horizon_offsets)
        assert set(result.keys()) == {"h_1_7", "h_8_14", "h_15_28", "h_29_plus"}
        # Each bucket carries the same metric names as calculate_all.
        for bucket in result.values():
            assert {"mae", "rmse", "smape", "wape", "bias"} <= set(bucket.keys())
            assert bucket["mae"] == pytest.approx(1.0)

    def test_compute_buckets_drops_empty_h29_for_14day_horizon(self) -> None:
        """A 14-day horizon must NOT emit ``h_29_plus`` — empty buckets drop."""
        actuals = np.arange(1.0, 15.0)
        predictions = actuals.copy()
        horizon_offsets = list(range(1, 15))
        result = compute_bucket_metrics(actuals, predictions, horizon_offsets)
        assert "h_1_7" in result
        assert "h_8_14" in result
        assert "h_15_28" not in result
        assert "h_29_plus" not in result

    def test_compute_buckets_handles_unaligned_offsets(self) -> None:
        """A non-contiguous offset list still slices into the right buckets."""
        actuals = np.array([1.0, 2.0, 3.0, 4.0])
        predictions = np.array([1.5, 2.5, 3.5, 4.5])
        horizon_offsets = [1, 14, 15, 50]  # h_1_7, h_8_14, h_15_28, h_29_plus
        result = compute_bucket_metrics(actuals, predictions, horizon_offsets)
        assert set(result.keys()) == {"h_1_7", "h_8_14", "h_15_28", "h_29_plus"}

    def test_compute_buckets_length_mismatch_raises(self) -> None:
        """Mismatched array lengths surface as ValueError."""
        with pytest.raises(ValueError, match="length mismatch"):
            compute_bucket_metrics(
                np.array([1.0, 2.0]),
                np.array([1.0, 2.0, 3.0]),
                [1, 2, 3],
            )

    def test_compute_buckets_empty_arrays_returns_empty_dict(self) -> None:
        """Empty inputs return an empty dict (no buckets to emit)."""
        result = compute_bucket_metrics(np.array([]), np.array([]), [])
        assert result == {}


class TestAggregateBucketMetrics:
    """Tests for cross-fold aggregation of per-horizon-bucket metrics."""

    def test_aggregate_means_per_bucket(self) -> None:
        """aggregate_bucket_metrics returns per-bucket means across folds."""
        calc = MetricsCalculator()
        fold_buckets = [
            {"h_1_7": {"mae": 2.0, "rmse": 3.0}, "h_8_14": {"mae": 4.0}},
            {"h_1_7": {"mae": 6.0, "rmse": 7.0}, "h_8_14": {"mae": 8.0}},
        ]
        aggregated = calc.aggregate_bucket_metrics(fold_buckets)
        assert aggregated["h_1_7"]["mae"] == pytest.approx(4.0)
        assert aggregated["h_1_7"]["rmse"] == pytest.approx(5.0)
        assert aggregated["h_8_14"]["mae"] == pytest.approx(6.0)

    def test_aggregate_skips_buckets_absent_in_some_folds(self) -> None:
        """A bucket present in only some folds aggregates over the present folds only."""
        calc = MetricsCalculator()
        fold_buckets = [
            {"h_1_7": {"mae": 10.0}},
            {"h_1_7": {"mae": 20.0}, "h_29_plus": {"mae": 5.0}},
        ]
        aggregated = calc.aggregate_bucket_metrics(fold_buckets)
        assert aggregated["h_1_7"]["mae"] == pytest.approx(15.0)
        assert aggregated["h_29_plus"]["mae"] == pytest.approx(5.0)

    def test_aggregate_empty_input_returns_empty_dict(self) -> None:
        """No folds → no buckets."""
        calc = MetricsCalculator()
        assert calc.aggregate_bucket_metrics([]) == {}

    def test_aggregate_skips_nan_values(self) -> None:
        """NaN per-fold values do not contribute to the mean."""
        calc = MetricsCalculator()
        fold_buckets = [
            {"h_1_7": {"mae": 2.0}},
            {"h_1_7": {"mae": float("nan")}},
            {"h_1_7": {"mae": 4.0}},
        ]
        aggregated = calc.aggregate_bucket_metrics(fold_buckets)
        assert aggregated["h_1_7"]["mae"] == pytest.approx(3.0)
