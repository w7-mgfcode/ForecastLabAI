"""Example: Metrics calculation and interpretation.

Demonstrates the forecasting metrics suite and their interpretation
for model evaluation.

Usage:
    python examples/backtest/metrics_demo.py
"""

import numpy as np

from app.features.backtesting.metrics import MetricsCalculator


def print_metric_result(result):
    """Pretty print a MetricResult."""
    print(f"  {result.name.upper()}: {result.value:.4f}")
    if result.warnings:
        for warning in result.warnings:
            print(f"    ⚠ {warning}")


def main():
    calc = MetricsCalculator()

    print("=" * 70)
    print("FORECASTING METRICS DEMONSTRATION")
    print("=" * 70)

    # Scenario 1: Perfect Predictions
    print("\n--- Scenario 1: Perfect Predictions ---")
    actuals = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
    predictions = np.array([100.0, 200.0, 300.0, 400.0, 500.0])

    print(f"Actuals:     {actuals}")
    print(f"Predictions: {predictions}")
    print("\nMetrics:")
    print_metric_result(calc.mae(actuals, predictions))
    print_metric_result(calc.smape(actuals, predictions))
    print_metric_result(calc.wape(actuals, predictions))
    print_metric_result(calc.bias(actuals, predictions))

    # Scenario 2: Over-Forecasting
    print("\n--- Scenario 2: Consistent Over-Forecasting ---")
    actuals = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
    predictions = np.array([120.0, 120.0, 120.0, 120.0, 120.0])

    print(f"Actuals:     {actuals}")
    print(f"Predictions: {predictions}")
    print("\nMetrics:")
    print_metric_result(calc.mae(actuals, predictions))
    print_metric_result(calc.smape(actuals, predictions))
    print_metric_result(calc.wape(actuals, predictions))
    print_metric_result(calc.bias(actuals, predictions))
    print("  → Negative bias indicates over-forecasting")

    # Scenario 3: Under-Forecasting
    print("\n--- Scenario 3: Consistent Under-Forecasting ---")
    actuals = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
    predictions = np.array([80.0, 80.0, 80.0, 80.0, 80.0])

    print(f"Actuals:     {actuals}")
    print(f"Predictions: {predictions}")
    print("\nMetrics:")
    print_metric_result(calc.mae(actuals, predictions))
    print_metric_result(calc.smape(actuals, predictions))
    print_metric_result(calc.wape(actuals, predictions))
    print_metric_result(calc.bias(actuals, predictions))
    print("  → Positive bias indicates under-forecasting")

    # Scenario 4: Mixed Errors (no bias)
    print("\n--- Scenario 4: Mixed Errors (No Systematic Bias) ---")
    actuals = np.array([100.0, 100.0, 100.0, 100.0])
    predictions = np.array([110.0, 90.0, 110.0, 90.0])  # +10, -10, +10, -10

    print(f"Actuals:     {actuals}")
    print(f"Predictions: {predictions}")
    print("\nMetrics:")
    print_metric_result(calc.mae(actuals, predictions))
    print_metric_result(calc.smape(actuals, predictions))
    print_metric_result(calc.wape(actuals, predictions))
    print_metric_result(calc.bias(actuals, predictions))
    print("  → Bias ≈ 0 despite non-zero MAE")

    # Scenario 5: Intermittent Series (zeros)
    print("\n--- Scenario 5: Intermittent Series (With Zeros) ---")
    actuals = np.array([0.0, 50.0, 0.0, 100.0, 0.0])
    predictions = np.array([10.0, 40.0, 5.0, 90.0, 0.0])

    print(f"Actuals:     {actuals}")
    print(f"Predictions: {predictions}")
    print("\nMetrics:")
    print_metric_result(calc.mae(actuals, predictions))
    print_metric_result(calc.smape(actuals, predictions))
    print_metric_result(calc.wape(actuals, predictions))
    print_metric_result(calc.bias(actuals, predictions))
    print("  → WAPE is robust for intermittent series")

    # Scenario 6: Stability Index
    print("\n--- Scenario 6: Fold Stability Comparison ---")

    stable_folds = [10.0, 11.0, 9.5, 10.5, 10.0]
    unstable_folds = [5.0, 20.0, 8.0, 25.0, 12.0]

    print(f"Stable fold MAEs:   {stable_folds}")
    stable_result = calc.stability_index(stable_folds)
    print_metric_result(stable_result)

    print(f"\nUnstable fold MAEs: {unstable_folds}")
    unstable_result = calc.stability_index(unstable_folds)
    print_metric_result(unstable_result)
    print("  → Lower stability index = more consistent performance")

    # Aggregation example
    print("\n--- Scenario 7: Fold Aggregation ---")
    fold_metrics = [
        {"mae": 10.0, "smape": 15.0, "wape": 12.0, "bias": 2.0},
        {"mae": 12.0, "smape": 18.0, "wape": 14.0, "bias": 3.0},
        {"mae": 8.0, "smape": 12.0, "wape": 10.0, "bias": 1.0},
        {"mae": 11.0, "smape": 16.0, "wape": 13.0, "bias": 2.5},
    ]

    print("Fold metrics:")
    for i, fm in enumerate(fold_metrics):
        print(
            f"  Fold {i}: MAE={fm['mae']}, sMAPE={fm['smape']}, WAPE={fm['wape']}, Bias={fm['bias']}"
        )

    aggregated, stability = calc.aggregate_fold_metrics(fold_metrics)

    print("\nAggregated (mean across folds):")
    for metric, value in aggregated.items():
        stab_key = f"{metric}_stability"
        stab_val = stability.get(stab_key, float("nan"))
        print(f"  {metric}: {value:.4f} (stability: {stab_val:.2f}%)")

    # Metric interpretation guide
    print("\n" + "=" * 70)
    print("METRIC INTERPRETATION GUIDE")
    print("=" * 70)
    print("""
MAE (Mean Absolute Error):
  - Unit: Same as target variable (e.g., units sold)
  - Lower is better
  - Easy to interpret: "On average, we're off by X units"

sMAPE (Symmetric Mean Absolute Percentage Error):
  - Unit: Percentage (0-200 scale)
  - Lower is better
  - Symmetric: treats over/under-forecasting equally
  - 0 = perfect, 200 = maximum error

WAPE (Weighted Absolute Percentage Error):
  - Unit: Percentage
  - Lower is better
  - Better than MAPE for intermittent/low-volume series
  - Weights errors by actual values

Bias (Forecast Bias):
  - Unit: Same as target variable
  - Closer to 0 is better
  - Positive = under-forecasting (actuals > predictions)
  - Negative = over-forecasting (actuals < predictions)

Stability Index (Coefficient of Variation):
  - Unit: Percentage
  - Lower is better
  - Measures consistency across folds
  - High values indicate unreliable model performance
""")


if __name__ == "__main__":
    main()
