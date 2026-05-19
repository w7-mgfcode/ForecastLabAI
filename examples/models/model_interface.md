# Model Interface Contract

This document describes the interface contract for ForecastLabAI forecasting models.

## BaseForecaster Interface

All forecasting models implement the `BaseForecaster` abstract base class, which follows
scikit-learn conventions for estimators.

### Required Methods

#### `fit(y, X=None) -> self`

Fit the model on historical data.

**Parameters:**
- `y` (np.ndarray): Target values, 1D array of shape `[n_samples]`
- `X` (np.ndarray | None): Optional exogenous features, 2D array of shape `[n_samples, n_features]`

**Returns:**
- `self`: For method chaining

**Raises:**
- `ValueError`: If `y` is empty or has insufficient observations for the model

**Example:**
```python
model = NaiveForecaster()
model.fit(y=np.array([1, 2, 3, 4, 5]))
```

#### `predict(horizon, X=None) -> np.ndarray`

Generate forecasts for the specified horizon.

**Parameters:**
- `horizon` (int): Number of steps to forecast
- `X` (np.ndarray | None): Optional exogenous features for forecast period

**Returns:**
- `np.ndarray`: Array of forecasts with shape `[horizon]`

**Raises:**
- `RuntimeError`: If model has not been fitted

**Example:**
```python
forecasts = model.predict(horizon=7)
# Returns: array([5., 5., 5., 5., 5., 5., 5.])
```

#### `get_params() -> dict[str, Any]`

Get model parameters (scikit-learn convention).

**Returns:**
- `dict`: Dictionary of parameter names to values

**Example:**
```python
params = model.get_params()
# Returns: {"random_state": 42}
```

#### `set_params(**params) -> self`

Set model parameters (scikit-learn convention).

**Parameters:**
- `**params`: Parameter names and values to set

**Returns:**
- `self`: For method chaining

**Example:**
```python
model.set_params(random_state=99)
```

### Properties

#### `is_fitted: bool`

Check if the model has been fitted.

**Returns:**
- `True` if `fit()` has been called successfully

#### `requires_features: ClassVar[bool]`

Class attribute — `True` when `fit()`/`predict()` REQUIRE a non-`None` `X`
feature frame. Baseline (target-only) models leave it `False`; feature-aware
models (e.g. the regression forecaster) override it to `True`. The forecasting
service branches on this flag instead of an `isinstance` check or a
`model_type` string comparison.

---

## Model Configurations

Each model type has a corresponding configuration schema:

### NaiveModelConfig

```python
{
    "schema_version": "1.0",
    "model_type": "naive"
}
```

### SeasonalNaiveModelConfig

```python
{
    "schema_version": "1.0",
    "model_type": "seasonal_naive",
    "season_length": 7  # 1-365
}
```

### MovingAverageModelConfig

```python
{
    "schema_version": "1.0",
    "model_type": "moving_average",
    "window_size": 7  # 1-90
}
```

### RegressionModelConfig

```python
{
    "schema_version": "1.0",
    "model_type": "regression",
    "max_iter": 200,        # 10-1000  (boosting iterations)
    "learning_rate": 0.05,  # 0.001-1.0
    "max_depth": 6          # 1-20
}
```

A **feature-aware** model (`requires_features = True`): it wraps scikit-learn's
`HistGradientBoostingRegressor` and consumes a per-day exogenous feature frame.
The feature-frame contract — the canonical column set, the historical vs future
frame shapes, and the leakage taxonomy — is documented in
[`feature_frame_contract.md`](feature_frame_contract.md).

### LightGBMModelConfig

```python
{
    "schema_version": "1.0",
    "model_type": "lightgbm",
    "n_estimators": 100,    # 10-1000  (boosting rounds)
    "max_depth": 6,         # 1-20
    "learning_rate": 0.1    # 0.001-1.0
}
```

A **feature-aware** model (`requires_features = True`) wrapping
`lightgbm.LGBMRegressor` — the first *advanced* model in the MLZOO sequence
(PRP-30 / MLZOO-B). LightGBM is an **optional dependency**: install the
`ml-lightgbm` extra (`uv sync --extra dev --extra ml-lightgbm`) and enable
`forecast_enable_lightgbm=true`. It consumes the same canonical feature frame as
`regression` — see [`feature_frame_contract.md`](feature_frame_contract.md).

### XGBoostModelConfig

```python
{
    "schema_version": "1.0",
    "model_type": "xgboost",
    "n_estimators": 100,    # 10-1000  (boosting rounds)
    "max_depth": 6,         # 1-20
    "learning_rate": 0.1    # 0.001-1.0
}
```

A **feature-aware** model (`requires_features = True`) wrapping
`xgboost.XGBRegressor` — the second *advanced* tree model in the MLZOO sequence
(PRP-MLZOO-C1). XGBoost is an **optional dependency**: install the
`ml-xgboost` extra (`uv sync --extra dev --extra ml-xgboost`) and enable
`forecast_enable_xgboost=true`. It consumes the same canonical feature frame as
`regression` and `lightgbm` — see [`feature_frame_contract.md`](feature_frame_contract.md).

### ProphetLikeModelConfig

```python
{
    "schema_version": "1.0",
    "model_type": "prophet_like",
    "alpha": 1.0    # 0.0-10000.0  (Ridge L2 regularization strength)
}
```

A **feature-aware** model (`requires_features = True`) — a deterministic,
regularized **additive linear** model (MLZOO-C2). It is a scikit-learn
`Pipeline` of a `SimpleImputer(median)` + a `Ridge(solver="cholesky")` over the
same canonical 14-column feature frame as `regression`. Unlike the tree models
it ships **always-enabled**: pure scikit-learn, no optional extra, no feature
flag. It exposes a model-specific `decompose()` method that splits any forecast
into its additive trend / seasonality / holiday-regressor contributions.

It is "Prophet-**like**", not Prophet: it approximates Prophet's additive shape
with a linear model over engineered features. It does **not** add the real
`prophet`/Stan dependency and does **not** model changepoint trend, posterior
uncertainty intervals, or automatic seasonality discovery.

---

## Model Formulas

### Naive Forecaster

```
ŷ[t+h] = y[t]  for all h ∈ [1, horizon]
```

Predicts the last observed value for all future horizons.

### Seasonal Naive Forecaster

```
ŷ[t+h] = y[t + h - m]  where m = season_length
```

Predicts the value from the same position in the previous seasonal cycle.

### Moving Average Forecaster

```
ŷ[t+h] = mean(y[t-window+1:t+1])  for all h ∈ [1, horizon]
```

Predicts the average of the last `window_size` observations.

### Regression Forecaster

```
ŷ[t+h] = HistGradientBoostingRegressor.predict(X[t+h])
```

Predicts each horizon day from its exogenous feature row `X[t+h]` (target
long-lags, calendar, and posited price/promotion inputs). Unlike the baselines
it REQUIRES a feature frame — see [`feature_frame_contract.md`](feature_frame_contract.md).

### LightGBM Forecaster

```
ŷ[t+h] = LGBMRegressor.predict(X[t+h])
```

Same exogenous-feature contract as the regression forecaster, but the estimator
is `lightgbm.LGBMRegressor` — gradient-boosted leaf-wise trees. Feature-aware
(`requires_features = True`), deterministic (`n_jobs=1`, `deterministic=True`,
`force_col_wise=True`, fixed `random_state`), and NaN-tolerant. Optional —
behind the `ml-lightgbm` extra and the `forecast_enable_lightgbm` flag.

### XGBoost Forecaster

```
ŷ[t+h] = XGBRegressor.predict(X[t+h])
```

Same exogenous-feature contract as the regression and LightGBM forecasters, but
the estimator is `xgboost.XGBRegressor` — gradient-boosted trees. Feature-aware
(`requires_features = True`), deterministic (`n_jobs=1`, `tree_method="hist"`,
fixed `random_state`, no stochastic subsampling), and NaN-tolerant
(`missing=np.nan`). Optional — behind the `ml-xgboost` extra and the
`forecast_enable_xgboost` flag.

### Prophet-like Forecaster

```
ŷ[t+h] = intercept + trend[t+h] + seasonality[t+h] + holiday_regressor[t+h]
```

An **additive** linear forecast: a `Ridge` fit gives `ŷ = intercept + Σ coefᵢ·xᵢ`,
and that sum is grouped into three Prophet-style components, each the partial
sum over its columns of the canonical 14-column frame:

| Component | Canonical columns |
|-----------|-------------------|
| `trend` | `lag_1`, `lag_7`, `lag_14`, `lag_28`, `days_since_launch` |
| `seasonality` | `dow_sin`, `dow_cos`, `month_sin`, `month_cos`, `is_weekend`, `is_month_end` |
| `holiday_regressor` | `price_factor`, `promo_active`, `is_holiday` |

The three column sets partition all 14 columns exactly, so the **additive
invariant** holds: `decompose(X)`'s four parts sum (within float tolerance) to
`predict(...)`. Feature-aware (`requires_features = True`), deterministic
(`Ridge(solver="cholesky")` closed-form, `SimpleImputer(median)`), and
NaN-tolerant via the imputer. Pure scikit-learn — always available, no extra,
no flag. The `decompose()` method (model-specific, not on `BaseForecaster`)
returns the four-way breakdown.

---

## Persistence (ModelBundle)

Models are persisted using `ModelBundle` which includes:

```python
@dataclass
class ModelBundle:
    model: BaseForecaster      # Fitted model
    config: ModelConfig        # Configuration used
    metadata: dict[str, Any]   # Custom metadata (store_id, dates, etc.)
    created_at: datetime       # Save timestamp
    python_version: str        # Python version
    sklearn_version: str       # Scikit-learn version
    lightgbm_version: str | None  # LightGBM version (None if extra not installed)
    xgboost_version: str | None   # XGBoost version (None if extra not installed)
    bundle_hash: str           # Deterministic hash
```

### Save/Load

```python
from app.features.forecasting.persistence import save_model_bundle, load_model_bundle

# Save
path = save_model_bundle(bundle, "./artifacts/models/my_model")

# Load
bundle = load_model_bundle(path)
forecasts = bundle.model.predict(horizon=7)
```

---

## Determinism

All models must be deterministic given the same:
1. Input data (`y`, `X`)
2. Configuration parameters
3. `random_state`

This ensures reproducibility in experiments and backtesting.

---

## Input/Output Shapes

| Method | Input Shape | Output Shape |
|--------|-------------|--------------|
| `fit(y)` | `[n_samples]` | `self` |
| `fit(y, X)` | `y: [n_samples]`, `X: [n_samples, n_features]` | `self` |
| `predict(horizon)` | `int` | `[horizon]` |
| `predict(horizon, X)` | `int`, `X: [horizon, n_features]` | `[horizon]` |

---

## Error Handling

| Scenario | Exception | Message |
|----------|-----------|---------|
| Empty training data | `ValueError` | "Cannot fit on empty array" |
| Insufficient data for seasonal | `ValueError` | "Need at least {season_length} observations" |
| Insufficient data for MA | `ValueError` | "Need at least {window_size} observations" |
| Predict before fit | `RuntimeError` | "Model must be fitted before predict" |
| Unknown model type | `ValueError` | "Unknown model type: {type}" |
