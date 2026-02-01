"""Example: Training and predicting with the Seasonal Naive forecaster.

The Seasonal Naive forecaster predicts values from the same season in
the previous cycle. For weekly seasonality (season_length=7), Friday's
forecast equals last Friday's value.

Usage:
    python examples/models/baseline_seasonal.py
"""

import numpy as np

from app.features.forecasting.models import SeasonalNaiveForecaster
from app.features.forecasting.persistence import ModelBundle, load_model_bundle, save_model_bundle
from app.features.forecasting.schemas import SeasonalNaiveModelConfig


def main():
    # 1. Create sample data with weekly pattern
    # Pattern: Mon=10, Tue=20, Wed=30, Thu=40, Fri=50, Sat=60, Sun=70
    weekly_pattern = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0])
    y = np.tile(weekly_pattern, 4)  # 4 weeks = 28 days
    print(f"Training data: {len(y)} observations (4 weeks)")
    print(f"Weekly pattern: {weekly_pattern}")
    print(f"Last week: {y[-7:]}")

    # 2. Create and configure the model
    config = SeasonalNaiveModelConfig(
        schema_version="1.0",
        season_length=7,  # Weekly seasonality
    )
    model = SeasonalNaiveForecaster(season_length=7, random_state=42)

    # 3. Fit the model
    model.fit(y)
    print(f"\nModel fitted: {model.is_fitted}")
    print(f"Model params: {model.get_params()}")
    print(f"Stored seasonal values: {model._last_values}")

    # 4. Generate predictions for 2 weeks
    horizon = 14
    forecasts = model.predict(horizon=horizon)
    print(f"\n{horizon}-day forecast (2 weeks):")
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for i, f in enumerate(forecasts):
        day_name = days[i % 7]
        print(f"  Day {i + 1} ({day_name}): {f:.2f}")

    # 5. Verify seasonality is preserved
    print("\nVerifying seasonal cycling:")
    print(f"  Week 1: {forecasts[:7]}")
    print(f"  Week 2: {forecasts[7:]}")
    assert np.array_equal(forecasts[:7], forecasts[7:]), "Seasonal pattern should repeat!"
    print("  ✓ Pattern repeats correctly")

    # 6. Save the model bundle
    bundle = ModelBundle(
        model=model,
        config=config,
        metadata={
            "store_id": 1,
            "product_id": 1,
            "train_start_date": "2024-01-01",
            "train_end_date": "2024-01-28",
            "n_observations": len(y),
            "seasonality": "weekly",
        },
    )

    model_path = save_model_bundle(bundle, "./artifacts/models/seasonal_example")
    print(f"\nModel saved to: {model_path}")

    # 7. Load and verify
    loaded_bundle = load_model_bundle(model_path)
    loaded_forecasts = loaded_bundle.model.predict(horizon=7)
    print(f"\nLoaded model forecast (1 week): {loaded_forecasts}")
    print(f"Config: season_length={loaded_bundle.config.season_length}")


if __name__ == "__main__":
    main()
