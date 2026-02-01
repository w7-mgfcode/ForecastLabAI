"""Example: Training and predicting with the Moving Average forecaster.

The Moving Average forecaster predicts the mean of the last N observations
for all horizons. This is a simple baseline that smooths out short-term
fluctuations.

Usage:
    python examples/models/baseline_mavg.py
"""

import numpy as np

from app.features.forecasting.models import MovingAverageForecaster
from app.features.forecasting.persistence import ModelBundle, load_model_bundle, save_model_bundle
from app.features.forecasting.schemas import MovingAverageModelConfig


def main():
    # 1. Create sample data with some variation
    # Sequential values with noise
    np.random.seed(42)
    base = np.arange(1, 31, dtype=np.float64)
    noise = np.random.normal(0, 2, 30)
    y = base + noise
    print(f"Training data: {len(y)} observations")
    print(f"Last 7 values: {y[-7:].round(2)}")
    print(f"Mean of last 7: {np.mean(y[-7:]):.2f}")

    # 2. Create and configure the model
    config = MovingAverageModelConfig(
        schema_version="1.0",
        window_size=7,
    )
    model = MovingAverageForecaster(window_size=7, random_state=42)

    # 3. Fit the model
    model.fit(y)
    print(f"\nModel fitted: {model.is_fitted}")
    print(f"Model params: {model.get_params()}")
    print(f"Computed forecast value: {model._forecast_value:.2f}")

    # 4. Generate predictions
    horizon = 7
    forecasts = model.predict(horizon=horizon)
    print(f"\n{horizon}-day forecast:")
    for i, f in enumerate(forecasts):
        print(f"  Day {i + 1}: {f:.2f}")

    # 5. Verify all forecasts are the same (constant prediction)
    print("\nVerifying constant forecast:")
    assert all(f == forecasts[0] for f in forecasts), "All forecasts should be equal!"
    print(f"  ✓ All {horizon} forecasts equal: {forecasts[0]:.2f}")

    # 6. Compare different window sizes
    print("\nComparing window sizes:")
    for window in [3, 7, 14, 21]:
        if window <= len(y):
            temp_model = MovingAverageForecaster(window_size=window)
            temp_model.fit(y)
            pred = temp_model.predict(horizon=1)[0]
            actual_mean = np.mean(y[-window:])
            print(f"  Window {window:2d}: forecast={pred:.2f}, actual_mean={actual_mean:.2f}")

    # 7. Save the model bundle
    bundle = ModelBundle(
        model=model,
        config=config,
        metadata={
            "store_id": 1,
            "product_id": 1,
            "train_start_date": "2024-01-01",
            "train_end_date": "2024-01-30",
            "n_observations": len(y),
            "window_size": 7,
        },
    )

    model_path = save_model_bundle(bundle, "./artifacts/models/mavg_example")
    print(f"\nModel saved to: {model_path}")

    # 8. Load and verify
    loaded_bundle = load_model_bundle(model_path)
    loaded_forecasts = loaded_bundle.model.predict(horizon=3)
    print(f"\nLoaded model forecast: {loaded_forecasts}")
    print(f"Config: window_size={loaded_bundle.config.window_size}")


if __name__ == "__main__":
    main()
