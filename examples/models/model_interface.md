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
