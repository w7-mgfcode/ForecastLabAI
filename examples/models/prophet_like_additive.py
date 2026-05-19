"""Example: Training, predicting, and decomposing with the Prophet-like model (MLZOO-C2).

``ProphetLikeForecaster`` is a deterministic, regularized ADDITIVE linear model
— a scikit-learn ``Pipeline`` of a ``SimpleImputer`` + a ``Ridge`` regressor
over the canonical 14-column feature frame. Like the other feature-aware models
it REQUIRES an exogenous feature matrix ``X`` for both ``fit`` and ``predict``.

It is "Prophet-LIKE", not Prophet: it approximates Prophet's additive trend +
seasonality + holiday/regressor decomposition with a linear model over already-
engineered features. It does NOT add the real ``prophet``/Stan dependency and
does NOT model changepoint trend, posterior uncertainty intervals, or automatic
seasonality discovery.

Pure scikit-learn — no optional extra to install, always available:

    uv run python examples/models/prophet_like_additive.py
"""

import numpy as np

from app.features.forecasting.models import ProphetLikeForecaster
from app.shared.feature_frames import canonical_feature_columns


def main() -> None:
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

    # 2. Create the model — deterministic (Ridge solver="cholesky" is closed-form).
    model = ProphetLikeForecaster(alpha=1.0, random_state=42)
    print(f"\nrequires_features: {ProphetLikeForecaster.requires_features}")

    # 3. Fit on the historical feature frame (the SimpleImputer learns its
    #    per-column medians on this training X only — no leakage).
    model.fit(y_train, x_train)
    print(f"Model fitted: {model.is_fitted}")
    print(f"Model params: {model.get_params()}")

    # 4. Predict over a future feature frame of `horizon` rows.
    horizon = 7
    x_future = rng.normal(size=(horizon, n_features))
    forecasts = model.predict(horizon, x_future)
    print(f"\n{horizon}-day forecast:")
    for i, value in enumerate(forecasts):
        print(f"  Day {i + 1}: {value:.2f}")

    # 5. Decompose the forecast into its additive components. The invariant is
    #    intercept + trend + seasonality + holiday_regressor == predict(...).
    decomposition = model.decompose(x_future)
    print(f"\nAdditive decomposition (intercept = {decomposition.intercept:.2f}):")
    print("  Day | trend  | seasonality | holiday_regressor | sum     | predict")
    for i in range(horizon):
        component_sum = (
            decomposition.intercept
            + decomposition.trend[i]
            + decomposition.seasonality[i]
            + decomposition.holiday_regressor[i]
        )
        print(
            f"  {i + 1:>3} | {decomposition.trend[i]:>6.2f} | "
            f"{decomposition.seasonality[i]:>11.2f} | "
            f"{decomposition.holiday_regressor[i]:>17.2f} | "
            f"{component_sum:>7.2f} | {forecasts[i]:>7.2f}"
        )


if __name__ == "__main__":
    main()
