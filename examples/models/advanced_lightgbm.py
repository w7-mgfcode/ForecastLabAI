"""Example: Training and predicting with the LightGBM forecaster (MLZOO-B).

``LightGBMForecaster`` is the first ADVANCED feature-aware model — it wraps
``lightgbm.LGBMRegressor`` and, unlike the baselines, REQUIRES an exogenous
feature matrix ``X`` for both ``fit`` and ``predict``.

LightGBM is an OPTIONAL dependency. Install the extra first:

    uv sync --extra dev --extra ml-lightgbm

Usage:
    python examples/models/advanced_lightgbm.py
"""

import numpy as np

from app.features.forecasting.models import LightGBMForecaster
from app.shared.feature_frames import canonical_feature_columns


def main():
    # 1. Build a small synthetic feature matrix matching the canonical 14-column
    #    feature-frame contract, plus a target that genuinely depends on it.
    columns = canonical_feature_columns()
    n_features = len(columns)  # 14
    rng = np.random.default_rng(42)
    n_rows = 120
    x_train = rng.normal(size=(n_rows, n_features))
    y_train = (
        50.0 + 5.0 * x_train[:, 0] - 3.0 * x_train[:, 1] + rng.normal(scale=0.5, size=n_rows)
    ).astype(np.float64)
    print(f"Training data: {n_rows} rows x {n_features} features")
    print(f"Feature columns: {columns}")

    # 2. Create the model — deterministic given a fixed random_state.
    model = LightGBMForecaster(n_estimators=100, learning_rate=0.1, max_depth=6, random_state=42)
    print(f"\nrequires_features: {LightGBMForecaster.requires_features}")

    # 3. Fit on the historical feature frame (``lightgbm`` is imported lazily here).
    model.fit(y_train, x_train)
    print(f"Model fitted: {model.is_fitted}")
    print(f"Model params: {model.get_params()}")

    # 4. Predict over a future feature frame of `horizon` rows.
    horizon = 7
    x_future = rng.normal(size=(horizon, n_features))
    forecasts = model.predict(horizon, x_future)
    print(f"\n{horizon}-day forecast:")
    for i, f in enumerate(forecasts):
        print(f"  Day {i + 1}: {f:.2f}")


if __name__ == "__main__":
    main()
