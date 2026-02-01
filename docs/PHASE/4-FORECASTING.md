# Phase 4: Forecasting

**Date Completed**: 2026-01-31
**PRP**: [PRP-5-forecasting.md](../../PRPs/PRP-5-forecasting.md)
**Release**: PR #28

---

## Executive Summary

Phase 4 implements the Forecasting Layer for ForecastLabAI with a unified model zoo following scikit-learn conventions. The module provides a `BaseForecaster` abstract class that all models implement, ensuring consistent `fit`/`predict` interfaces and seamless integration with the backtesting framework.

**Key Achievement**: Extensible model zoo with deterministic training via fixed `random_state` and joblib-based persistence for reproducibility.

---

## Deliverables

### 1. BaseForecaster Abstract Class

**File**: `app/features/forecasting/models.py`

Unified interface for all forecasting models:

```python
class BaseForecaster(ABC):
    """Abstract base class for all forecasting models.

    CRITICAL: All implementations must be deterministic with fixed random_state.

    Interface follows scikit-learn conventions:
    - fit(y, X=None) -> self
    - predict(horizon, X=None) -> np.ndarray
    - get_params() -> dict
    - set_params(**params) -> self
    """
```

**Model Types Implemented**:

|Model|Class|Description|Key Parameter|
|-------|-------|-------------|---------------|
|`naive`|`NaiveForecaster`|Predicts last observed value for all horizons|None|
|`seasonal_naive`|`SeasonalNaiveForecaster`|Predicts value from same season in previous cycle|`season_length` (default: 7)|
|`moving_average`|`MovingAverageForecaster`|Predicts mean of last N observations|`window_size` (default: 7)|
|`lightgbm`|(Placeholder)|LightGBM regressor (feature-flagged)|`n_estimators`, `max_depth`, `learning_rate`|

**FitResult Dataclass**:
```python
@dataclass
class FitResult:
    fitted: bool
    n_observations: int
    train_start: date_type
    train_end: date_type
    metrics: dict[str, float]
```

### 2. Model Configuration Schemas

**File**: `app/features/forecasting/schemas.py`

Pydantic v2 schemas with frozen configs for reproducibility:

|Schema|Purpose|
|--------|---------|
|`ModelConfigBase`|Base with `schema_version` and `config_hash()`|
|`NaiveModelConfig`|Config for naive forecaster|
|`SeasonalNaiveModelConfig`|Config with `season_length` (1-365)|
|`MovingAverageModelConfig`|Config with `window_size` (1-90)|
|`LightGBMModelConfig`|Config for LightGBM (n_estimators, max_depth, learning_rate)|
|`TrainRequest`|API request with store_id, product_id, date range, config|
|`TrainResponse`|Response with model_path, n_observations, duration_ms|
|`PredictRequest`|Request with horizon (1-90), model_path|
|`PredictResponse`|Response with forecast points|
|`ForecastPoint`|Single forecast with date, value, optional bounds|

**Key Features**:
- Frozen models (`frozen=True`) for immutability
- Schema versioning for registry storage
- Deterministic `config_hash()` for deduplication
- Strict validation (positive lags, valid ranges)

### 3. Model Persistence

**File**: `app/features/forecasting/persistence.py`

Joblib-based persistence with versioned bundles:

```python
@dataclass
class ModelBundle:
    """Bundled model with metadata for serialization."""
    model: BaseForecaster
    config: ModelConfig
    metadata: ModelMetadata
    version: str = "1.0"

def save_model_bundle(bundle: ModelBundle, path: Path) -> None:
    """Save model bundle to disk using joblib."""

def load_model_bundle(path: Path) -> ModelBundle:
    """Load model bundle from disk."""
```

**Bundle Contents**:
- Fitted model instance
- Configuration used for training
- Metadata (store_id, product_id, dates, n_observations)
- Version string for compatibility checking

### 4. ForecastingService

**File**: `app/features/forecasting/service.py`

Core service for model training and prediction:

```python
class ForecastingService:
    """Service for model training and prediction."""

    async def train_model(
        self,
        db: AsyncSession,
        store_id: int,
        product_id: int,
        train_start_date: date,
        train_end_date: date,
        config: ModelConfig,
    ) -> TrainResponse:
        """Train model on historical data."""

    async def predict(
        self,
        store_id: int,
        product_id: int,
        horizon: int,
        model_path: str,
    ) -> PredictResponse:
        """Generate forecasts using saved model."""
```

**Key Features**:
- Fetches training data from `sales_daily` table
- Uses `model_factory()` to instantiate correct model type
- Validates store/product match on prediction
- Structured logging for all operations

### 5. API Endpoints

**File**: `app/features/forecasting/routes.py`

|Endpoint|Method|Description|
|----------|--------|-------------|
|`/forecasting/train`|POST|Train a forecasting model|
|`/forecasting/predict`|POST|Generate forecasts using trained model|

**Train Request Example**:
```json
{
  "store_id": 1,
  "product_id": 101,
  "train_start_date": "2024-01-01",
  "train_end_date": "2024-12-31",
  "config": {
    "model_type": "seasonal_naive",
    "season_length": 7
  }
}
```

**Train Response Example**:
```json
{
  "store_id": 1,
  "product_id": 101,
  "model_type": "seasonal_naive",
  "model_path": "./artifacts/models/store_1_product_101_seasonal_naive_20240131_abc123.joblib",
  "config_hash": "a1b2c3d4e5f6g7h8",
  "n_observations": 365,
  "train_start_date": "2024-01-01",
  "train_end_date": "2024-12-31",
  "duration_ms": 45.23
}
```

**Predict Response Example**:
```json
{
  "store_id": 1,
  "product_id": 101,
  "forecasts": [
    {"date": "2025-01-01", "forecast": 42.5, "lower_bound": null, "upper_bound": null},
    {"date": "2025-01-02", "forecast": 38.2, "lower_bound": null, "upper_bound": null}
  ],
  "model_type": "seasonal_naive",
  "config_hash": "a1b2c3d4e5f6g7h8",
  "horizon": 14,
  "duration_ms": 2.15
}
```

### 6. Test Suite

**Directory**: `app/features/forecasting/tests/`

|File|Tests|Coverage|
|------|-------|----------|
|`test_schemas.py`|20|Schema validation, config hash, frozen models|
|`test_models.py`|24|Model fit/predict, edge cases, params|
|`test_persistence.py`|15|Save/load bundles, version compatibility|
|`test_service.py`|20|Service integration, validation, logging|

**Total**: 79 tests

**Test Strategy**:
- Unit tests for each model type with edge cases
- Determinism tests (same input → same output)
- Bundle round-trip serialization tests
- Service tests with mocked database

### 7. Example Scripts

**Directory**: `examples/models/`

|File|Description|
|------|-------------|
|`baseline_naive.py`|Naive forecaster demo|
|`baseline_seasonal.py`|Seasonal naive with weekly seasonality|
|`baseline_mavg.py`|Moving average with configurable window|

---

## Configuration

**File**: `app/core/config.py`

New settings added:

```python
# Forecasting
forecast_random_seed: int = 42
forecast_default_horizon: int = 14
forecast_max_horizon: int = 90
forecast_model_artifacts_dir: str = "./artifacts/models"
forecast_enable_lightgbm: bool = False
```

|Setting|Default|Description|
|---------|---------|-------------|
|`forecast_random_seed`|42|Random seed for reproducibility|
|`forecast_default_horizon`|14|Default forecast horizon in days|
|`forecast_max_horizon`|90|Maximum allowed horizon|
|`forecast_model_artifacts_dir`|`./artifacts/models`|Directory for saved models|
|`forecast_enable_lightgbm`|False|Feature flag for LightGBM models|

---

## Directory Structure

```text
app/features/forecasting/
├── __init__.py          # Module exports
├── models.py            # BaseForecaster + implementations
├── schemas.py           # Pydantic configuration schemas
├── persistence.py       # Joblib save/load utilities
├── service.py           # ForecastingService
├── routes.py            # FastAPI endpoints
└── tests/
    ├── __init__.py
    ├── conftest.py      # Test fixtures
    ├── test_models.py   # Model unit tests
    ├── test_schemas.py  # Schema validation tests
    ├── test_persistence.py  # Persistence tests
    └── test_service.py  # Service integration tests

examples/models/
├── baseline_naive.py    # Naive forecaster demo
├── baseline_seasonal.py # Seasonal naive demo
└── baseline_mavg.py     # Moving average demo
```

---

## Validation Results

```bash
$ uv run ruff check app/features/forecasting/
All checks passed!

$ uv run mypy app/features/forecasting/
Success: no issues found in 10 source files

$ uv run pyright app/features/forecasting/
0 errors, 0 warnings, 0 informations

$ uv run pytest app/features/forecasting/tests/ -v
79 passed in 1.23s
```

---

## Logging Events

|Event|Description|
|-------|-------------|
|`forecasting.train_request_received`|Train request received|
|`forecasting.train_request_completed`|Training completed successfully|
|`forecasting.train_request_failed`|Training failed|
|`forecasting.predict_request_received`|Prediction request received|
|`forecasting.predict_request_completed`|Prediction completed|
|`forecasting.predict_request_failed`|Prediction failed|
|`forecasting.model_saved`|Model bundle saved to disk|
|`forecasting.model_loaded`|Model bundle loaded from disk|

---

## Next Phase Preparation

Phase 5 (Backtesting) will use the forecasting module to:
1. Train models on rolling/expanding training windows
2. Generate predictions for held-out test periods
3. Calculate accuracy metrics across folds
4. Compare against naive/seasonal baselines

**Integration Points**:
- `BaseForecaster.fit()` and `predict()` for CV folds
- `model_factory()` for instantiating models per fold
- `ModelConfig.config_hash()` for result deduplication
