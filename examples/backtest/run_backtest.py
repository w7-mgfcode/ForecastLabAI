"""Example: Running a backtest via the API.

Demonstrates how to call the backtesting endpoint to evaluate a model
on historical data using time-series cross-validation.

Prerequisites:
    - API server running: uv run uvicorn app.main:app --reload --port 8123
    - Database with sales data (run seed_demo_data.py first)

Usage:
    python examples/backtest/run_backtest.py
"""

import httpx

API_BASE = "http://localhost:8123"


def main():
    # 1. Prepare backtest request
    request_payload = {
        "store_id": 1,
        "product_id": 1,
        "start_date": "2024-01-01",
        "end_date": "2024-06-30",
        "config": {
            "split_config": {
                "strategy": "expanding",
                "n_splits": 5,
                "min_train_size": 30,
                "gap": 0,
                "horizon": 14,
            },
            "model_config_main": {
                "model_type": "naive",
            },
            "include_baselines": True,
            "store_fold_details": True,
        },
    }

    print("=" * 60)
    print("BACKTEST REQUEST")
    print("=" * 60)
    print(f"Store ID: {request_payload['store_id']}")
    print(f"Product ID: {request_payload['product_id']}")
    print(f"Date Range: {request_payload['start_date']} to {request_payload['end_date']}")
    print(f"Strategy: {request_payload['config']['split_config']['strategy']}")
    print(f"N Splits: {request_payload['config']['split_config']['n_splits']}")
    print(f"Horizon: {request_payload['config']['split_config']['horizon']} days")
    print()

    # 2. Send request to API
    print("Sending request to API...")
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{API_BASE}/backtesting/run",
            json=request_payload,
        )

    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        print(response.text)
        return

    result = response.json()

    # 3. Display results
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    print(f"Backtest ID: {result['backtest_id']}")
    print(f"Config Hash: {result['config_hash']}")
    print(f"Duration: {result['duration_ms']:.1f} ms")
    print(f"Leakage Check: {'PASSED' if result['leakage_check_passed'] else 'FAILED'}")

    # 4. Main model results
    main_results = result["main_model_results"]
    print(f"\n--- Main Model: {main_results['model_type']} ---")
    print("Aggregated Metrics:")
    for metric, value in main_results["aggregated_metrics"].items():
        stability = main_results["metric_std"].get(f"{metric}_stability", "N/A")
        if isinstance(stability, float):
            print(f"  {metric}: {value:.4f} (stability: {stability:.2f}%)")
        else:
            print(f"  {metric}: {value:.4f}")

    # 5. Per-fold details
    if main_results["fold_results"]:
        print("\nPer-Fold Results:")
        for fold in main_results["fold_results"]:
            split = fold["split"]
            print(
                f"  Fold {fold['fold_index']}: "
                f"train={split['train_start']} to {split['train_end']} ({split['train_size']} days), "
                f"test={split['test_start']} to {split['test_end']} ({split['test_size']} days)"
            )
            print(f"    MAE: {fold['metrics']['mae']:.4f}, sMAPE: {fold['metrics']['smape']:.2f}")

    # 6. Baseline comparisons
    if result.get("baseline_results"):
        print("\n--- Baseline Comparisons ---")
        for baseline in result["baseline_results"]:
            print(f"\n{baseline['model_type']}:")
            for metric, value in baseline["aggregated_metrics"].items():
                print(f"  {metric}: {value:.4f}")

    # 7. Comparison summary
    if result.get("comparison_summary"):
        print("\n--- Comparison Summary (vs Baselines) ---")
        for metric, comparison in result["comparison_summary"].items():
            print(f"\n{metric}:")
            print(f"  Main model: {comparison['main']:.4f}")
            if "naive" in comparison:
                print(f"  Naive: {comparison['naive']:.4f}")
            if "vs_naive_pct" in comparison:
                imp = comparison["vs_naive_pct"]
                direction = "better" if imp > 0 else "worse"
                print(f"  vs Naive: {abs(imp):.1f}% {direction}")
            if "seasonal_naive" in comparison:
                print(f"  Seasonal Naive: {comparison['seasonal_naive']:.4f}")
            if "vs_seasonal_pct" in comparison:
                imp = comparison["vs_seasonal_pct"]
                direction = "better" if imp > 0 else "worse"
                print(f"  vs Seasonal: {abs(imp):.1f}% {direction}")


if __name__ == "__main__":
    main()
