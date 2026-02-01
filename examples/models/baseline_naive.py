"""Example: Training and predicting with the Naive forecaster.

The Naive forecaster predicts the last observed value for all horizons.
This is the simplest baseline model and often works well for stable series.

Usage:
    python examples/models/baseline_naive.py
"""

import numpy as np

from app.features.forecasting.models import NaiveForecaster
from app.features.forecasting.persistence import ModelBundle, load_model_bundle, save_model_bundle
from app.features.forecasting.schemas import NaiveModelConfig


def main():
    # 1. Create sample data (30 days of sequential values)
    y = np.array(range(1, 31), dtype=np.float64)
    print(f"Training data: {len(y)} observations")
    print(f"Last value: {y[-1]}")

    # 2. Create and configure the model
    config = NaiveModelConfig(schema_version="1.0")
    model = NaiveForecaster(random_state=42)

    # 3. Fit the model
    model.fit(y)
    print(f"\nModel fitted: {model.is_fitted}")
    print(f"Model params: {model.get_params()}")

    # 4. Generate predictions
    horizon = 7
    forecasts = model.predict(horizon=horizon)
    print(f"\n{horizon}-day forecast:")
    for i, f in enumerate(forecasts):
        print(f"  Day {i + 1}: {f:.2f}")

    # 5. Save the model bundle
    bundle = ModelBundle(
        model=model,
        config=config,
        metadata={
            "store_id": 1,
            "product_id": 1,
            "train_start_date": "2024-01-01",
            "train_end_date": "2024-01-30",
            "n_observations": len(y),
        },
    )

    model_path = save_model_bundle(bundle, "./artifacts/models/naive_example")
    print(f"\nModel saved to: {model_path}")

    # 6. Load and verify
    loaded_bundle = load_model_bundle(model_path)
    loaded_forecasts = loaded_bundle.model.predict(horizon=horizon)
    print(f"\nLoaded model forecast: {loaded_forecasts}")
    print(f"Config hash: {loaded_bundle.config.config_hash()}")
    print(f"Bundle hash: {loaded_bundle.bundle_hash}")


if __name__ == "__main__":
    main()
