# PRP-5: Forecast Models v0 (Baselines + Global ML Hooks)

## Goal

Implement a model zoo with baseline forecasting algorithms and a unified model interface for the ForecastLabAI forecasting pipeline. The module provides naive, seasonal naive, and moving average models with fit/predict/serialize capabilities, extensible to scikit-learn regression pipelines.

**End State:** A production-ready `forecasting` vertical slice with:
- `BaseForecaster` — Abstract base class defining the model interface
- `NaiveForecaster`, `SeasonalNaiveForecaster`, `MovingAverageForecaster` — Baseline implementations
- `LightGBMForecaster` — Optional ML model with feature engineering integration
- `ModelBundle` — Joblib-based serialization with metadata and feature hash
- `POST /forecasting/train` — Train a model on historical data
- `POST /forecasting/predict` — Generate forecasts for a horizon
- Recursive multi-horizon forecasting support
- All validation gates passing (ruff, mypy, pyright, pytest)

---

## Why

- **Foundation for ForecastOps**: Models are required before backtesting (INITIAL-6) and registry (INITIAL-7)
- **Baseline Benchmarks**: Simple models establish performance baselines for ML comparison
- **Reproducibility**: Unified interface + serialization enables consistent model deployment
- **Integration Ready**: Works with FeatureEngineeringService for automated lag injection

---

## What

### User-Visible Behavior

1. **Train Endpoint**: Accept store/product/date range, return trained model artifact
2. **Predict Endpoint**: Load model, generate multi-step forecasts
3. **Model Types**: naive, seasonal_naive, moving_average, lightgbm (feature-flagged)
4. **Persistence**: Save/load models with full metadata for reproducibility

### Success Criteria

- [ ] All three baseline models implement fit/predict/serialize/load
- [ ] Unified `BaseForecaster` interface with type hints
- [ ] Recursive forecasting for multi-horizon predictions
- [ ] `ModelBundle` includes model + config + feature_hash + metadata
- [ ] Deterministic results with configurable random seed
- [ ] Integration with `FeatureEngineeringService` for ML models
- [ ] 40+ unit tests including determinism and serialization tests
- [ ] Example files demonstrating each model type

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ - Include these in your context window

# Scikit-learn Estimator Interface
- url: https://scikit-learn.org/stable/developers/develop.html
  why: "BaseEstimator patterns, fit/predict contract, get_params/set_params"
  critical: "All __init__ params must be explicit keyword args (no *args/**kwargs)"

# Scikit-learn Model Persistence
- url: https://scikit-learn.org/stable/model_persistence.html
  why: "Joblib dump/load patterns, compression, version compatibility warnings"
  critical: "Models saved with one sklearn version may not load in another"

# Scikit-learn Pipeline Composition
- url: https://scikit-learn.org/stable/modules/compose.html
  why: "Pipeline construction for Scaling -> Encoding -> Regressor"
  critical: "Pipeline requires fit/transform on all but last step"

# Recursive Multi-Step Forecasting
- url: https://skforecast.org/0.9.1/user_guides/autoregresive-forecaster
  why: "Pattern for iterating predictions as input for next step"
  critical: "Error propagation increases with horizon length"

# Naive/Seasonal Forecasting
- url: https://forecastegy.com/posts/naive-time-series-forecasting-in-python/
  why: "Implementation patterns for naive and seasonal naive"

# Multi-Step Forecasting Strategies
- url: https://machinelearningmastery.com/multi-step-time-series-forecasting/
  why: "Recursive vs Direct vs Multi-output strategies"

# Internal Codebase References
- file: app/features/featuresets/schemas.py
  why: "Pattern for frozen Pydantic configs with config_hash()"

- file: app/features/featuresets/service.py
  why: "Pattern for service class with cutoff enforcement"

- file: app/features/featuresets/tests/conftest.py
  why: "Pattern for test fixtures with sequential data"

- file: app/core/config.py
  why: "Pattern for Settings with environment variables"

- file: docs/ARCHITECTURE.md
  why: "Section 7 describes ForecastOps requirements"
```

### Current Codebase Tree (Relevant Parts)

```text
app/
├── core/
│   ├── config.py           # Settings singleton
│   ├── database.py         # AsyncSession, get_db
│   ├── exceptions.py       # ForecastLabError base
│   └── logging.py          # Structured logging
├── shared/
│   └── models.py           # TimestampMixin
├── features/
│   ├── data_platform/
│   │   └── models.py       # SalesDaily, Store, Product, Calendar
│   ├── featuresets/
│   │   ├── schemas.py      # FeatureSetConfig, config_hash()
│   │   ├── service.py      # FeatureEngineeringService
│   │   └── routes.py       # POST /featuresets/compute
│   └── ingest/
│       └── ...
└── main.py                 # FastAPI app with router registration
```

### Desired Codebase Tree

```text
app/features/forecasting/           # NEW: Forecasting vertical slice
├── __init__.py                     # Module exports
├── schemas.py                      # ModelConfig, TrainRequest, PredictRequest, PredictResponse
├── models.py                       # BaseForecaster, NaiveForecaster, SeasonalNaiveForecaster, etc.
├── service.py                      # ForecastingService (orchestration)
├── persistence.py                  # ModelBundle, save/load functions
├── routes.py                       # POST /forecasting/train, POST /forecasting/predict
└── tests/
    ├── __init__.py
    ├── conftest.py                 # Fixtures: sample configs, time series data
    ├── test_schemas.py             # Config validation, immutability
    ├── test_models.py              # Model fit/predict, determinism
    ├── test_persistence.py         # Serialization round-trip
    ├── test_service.py             # Orchestration logic
    └── test_routes.py              # Integration tests

examples/models/                    # NEW: Example scripts
├── baseline_naive.py               # Train and predict with naive model
├── baseline_seasonal.py            # Train and predict with seasonal naive
├── baseline_mavg.py                # Train and predict with moving average
└── model_interface.md              # Contract documentation

app/core/config.py                  # MODIFY: Add forecasting settings
app/main.py                         # MODIFY: Register forecasting router
```

### Known Gotchas

#### CRITICAL: Pydantic v2 uses model_config = ConfigDict(...), not class Config

Example: `frozen=True` for immutability, `extra="forbid"` for strict validation.

#### CRITICAL: Use field_validator (not @validator) with @classmethod decorator

Example: `@field_validator("horizon") @classmethod def validate_horizon(...)`

#### CRITICAL: Joblib serialization includes Python version

Models may not load if trained on different Python/sklearn version. Document this.

#### CRITICAL: Recursive forecasting propagates errors

Warn users for long horizons.

#### CRITICAL: All forecasters must be deterministic with fixed random_state

Use `Settings().forecast_random_seed` consistently.

#### CRITICAL: Multi-horizon forecasting updates lags recursively

Prediction at t+1 becomes lag_1 for prediction at t+2.

#### CRITICAL: Feature engineering must use cutoff_date = last training date

Never use future data when computing features for prediction.

---

## Implementation Blueprint

### Data Models and Schemas

```python
# app/features/forecasting/schemas.py

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal
from datetime import date
import hashlib

class ModelConfigBase(BaseModel):
    """Base configuration for all forecasting models."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(default="1.0", pattern=r"^\d+\.\d+(\.\d+)?$")

    def config_hash(self) -> str:
        """Deterministic hash for reproducibility."""
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:16]


class NaiveModelConfig(ModelConfigBase):
    """Config for naive forecaster (last value)."""
    model_type: Literal["naive"] = "naive"


class SeasonalNaiveModelConfig(ModelConfigBase):
    """Config for seasonal naive forecaster."""
    model_type: Literal["seasonal_naive"] = "seasonal_naive"
    season_length: int = Field(default=7, ge=1, le=365, description="Seasonality period in days")


class MovingAverageModelConfig(ModelConfigBase):
    """Config for moving average forecaster."""
    model_type: Literal["moving_average"] = "moving_average"
    window_size: int = Field(default=7, ge=1, le=90, description="Window size for averaging")


class LightGBMModelConfig(ModelConfigBase):
    """Config for LightGBM regressor (feature-flagged)."""
    model_type: Literal["lightgbm"] = "lightgbm"
    n_estimators: int = Field(default=100, ge=10, le=1000)
    max_depth: int = Field(default=6, ge=1, le=20)
    learning_rate: float = Field(default=0.1, ge=0.001, le=1.0)
    feature_config_hash: str | None = Field(default=None, description="Hash of FeatureSetConfig used")


# Union type for all configs
ModelConfig = NaiveModelConfig | SeasonalNaiveModelConfig | MovingAverageModelConfig | LightGBMModelConfig


class TrainRequest(BaseModel):
    """Request body for POST /forecasting/train."""
    model_config = ConfigDict(strict=True)

    store_id: int = Field(..., ge=1)
    product_id: int = Field(..., ge=1)
    train_start_date: date
    train_end_date: date
    config: ModelConfig

    @field_validator("train_end_date")
    @classmethod
    def validate_date_range(cls, v: date, info) -> date:
        if "train_start_date" in info.data and v <= info.data["train_start_date"]:
            raise ValueError("train_end_date must be after train_start_date")
        return v


class PredictRequest(BaseModel):
    """Request body for POST /forecasting/predict."""
    model_config = ConfigDict(strict=True)

    store_id: int = Field(..., ge=1)
    product_id: int = Field(..., ge=1)
    horizon: int = Field(..., ge=1, le=90, description="Number of days to forecast")
    model_path: str = Field(..., description="Path to saved model bundle")


class ForecastPoint(BaseModel):
    """Single forecast point."""
    date: date
    forecast: float
    lower_bound: float | None = None
    upper_bound: float | None = None


class PredictResponse(BaseModel):
    """Response body for POST /forecasting/predict."""
    store_id: int
    product_id: int
    forecasts: list[ForecastPoint]
    model_type: str
    config_hash: str
    horizon: int
    duration_ms: float
```

### Model Interface (Abstract Base)

```python
# app/features/forecasting/models.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np
import pandas as pd
from typing import Any

@dataclass
class FitResult:
    """Result of model fitting."""
    fitted: bool
    n_observations: int
    train_start: date
    train_end: date
    metrics: dict[str, float]  # e.g., {"train_mae": 1.23}


class BaseForecaster(ABC):
    """Abstract base class for all forecasting models.

    CRITICAL: All implementations must be deterministic with fixed random_state.

    Interface follows scikit-learn conventions:
    - fit(y, X=None) -> self
    - predict(horizon, X=None) -> np.ndarray
    - get_params() -> dict
    - set_params(**params) -> self
    """

    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self._is_fitted = False
        self._last_values: np.ndarray | None = None
        self._fit_result: FitResult | None = None

    @abstractmethod
    def fit(self, y: np.ndarray, X: np.ndarray | None = None) -> "BaseForecaster":
        """Fit the model on historical data.

        Args:
            y: Target values (1D array of shape [n_samples])
            X: Optional exogenous features (2D array of shape [n_samples, n_features])

        Returns:
            self (for method chaining)
        """
        pass

    @abstractmethod
    def predict(self, horizon: int, X: np.ndarray | None = None) -> np.ndarray:
        """Generate forecasts for the specified horizon.

        CRITICAL: For recursive forecasting, predictions at t+k become
        inputs for predictions at t+k+1.

        Args:
            horizon: Number of steps to forecast
            X: Optional exogenous features for forecast period

        Returns:
            Array of forecasts with shape [horizon]
        """
        pass

    @abstractmethod
    def get_params(self) -> dict[str, Any]:
        """Get model parameters (scikit-learn convention)."""
        pass

    @abstractmethod
    def set_params(self, **params: Any) -> "BaseForecaster":
        """Set model parameters (scikit-learn convention)."""
        pass

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted


class NaiveForecaster(BaseForecaster):
    """Naive forecaster: predicts last observed value for all horizons.

    Formula: y_hat[t+h] = y[t] for all h
    """

    def __init__(self, random_state: int = 42):
        super().__init__(random_state)

    def fit(self, y: np.ndarray, X: np.ndarray | None = None) -> "NaiveForecaster":
        if len(y) == 0:
            raise ValueError("Cannot fit on empty array")
        self._last_values = np.array([y[-1]])
        self._is_fitted = True
        return self

    def predict(self, horizon: int, X: np.ndarray | None = None) -> np.ndarray:
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before predict")
        # Repeat last value for all horizons
        return np.full(horizon, self._last_values[0])

    def get_params(self) -> dict[str, Any]:
        return {"random_state": self.random_state}

    def set_params(self, **params: Any) -> "NaiveForecaster":
        for key, value in params.items():
            setattr(self, key, value)
        return self


class SeasonalNaiveForecaster(BaseForecaster):
    """Seasonal naive forecaster: predicts value from same season in previous cycle.

    Formula: y_hat[t+h] = y[t+h-m] where m is season_length

    For weekly seasonality (m=7), Friday's forecast = last Friday's value.
    """

    def __init__(self, season_length: int = 7, random_state: int = 42):
        super().__init__(random_state)
        self.season_length = season_length

    def fit(self, y: np.ndarray, X: np.ndarray | None = None) -> "SeasonalNaiveForecaster":
        if len(y) < self.season_length:
            raise ValueError(f"Need at least {self.season_length} observations")
        # Store last season_length values for cycling
        self._last_values = y[-self.season_length:]
        self._is_fitted = True
        return self

    def predict(self, horizon: int, X: np.ndarray | None = None) -> np.ndarray:
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before predict")
        # Cycle through seasonal values
        forecasts = np.zeros(horizon)
        for h in range(horizon):
            idx = h % self.season_length
            forecasts[h] = self._last_values[idx]
        return forecasts

    def get_params(self) -> dict[str, Any]:
        return {"season_length": self.season_length, "random_state": self.random_state}

    def set_params(self, **params: Any) -> "SeasonalNaiveForecaster":
        for key, value in params.items():
            setattr(self, key, value)
        return self


class MovingAverageForecaster(BaseForecaster):
    """Moving average forecaster: predicts mean of last N observations.

    Formula: y_hat[t+h] = mean(y[t-window+1:t+1])

    CRITICAL: Does NOT update recursively - uses same average for all horizons.
    """

    def __init__(self, window_size: int = 7, random_state: int = 42):
        super().__init__(random_state)
        self.window_size = window_size

    def fit(self, y: np.ndarray, X: np.ndarray | None = None) -> "MovingAverageForecaster":
        if len(y) < self.window_size:
            raise ValueError(f"Need at least {self.window_size} observations")
        # Compute mean of last window_size values
        self._last_values = y[-self.window_size:]
        self._forecast_value = float(np.mean(self._last_values))
        self._is_fitted = True
        return self

    def predict(self, horizon: int, X: np.ndarray | None = None) -> np.ndarray:
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before predict")
        # Constant forecast for all horizons
        return np.full(horizon, self._forecast_value)

    def get_params(self) -> dict[str, Any]:
        return {"window_size": self.window_size, "random_state": self.random_state}

    def set_params(self, **params: Any) -> "MovingAverageForecaster":
        for key, value in params.items():
            setattr(self, key, value)
        return self
```

### Persistence Layer

```python
# app/features/forecasting/persistence.py

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import hashlib
import json

import joblib

from app.features.forecasting.models import BaseForecaster
from app.features.forecasting.schemas import ModelConfig


@dataclass
class ModelBundle:
    """Bundle containing model, config, and metadata for persistence.

    CRITICAL: Includes version info for compatibility checking.
    """
    model: BaseForecaster
    config: ModelConfig
    metadata: dict[str, Any] = field(default_factory=dict)

    # Auto-populated on save
    created_at: datetime | None = None
    python_version: str | None = None
    sklearn_version: str | None = None
    bundle_hash: str | None = None

    def compute_hash(self) -> str:
        """Compute deterministic hash of bundle contents."""
        content = {
            "config_hash": self.config.config_hash(),
            "model_params": self.model.get_params(),
            "metadata": self.metadata,
        }
        return hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()[:16]


def save_model_bundle(bundle: ModelBundle, path: str | Path) -> Path:
    """Save model bundle to disk using joblib.

    CRITICAL: Records Python and sklearn versions for compatibility warnings.

    Args:
        bundle: ModelBundle to save
        path: File path (will add .joblib extension if missing)

    Returns:
        Path to saved file
    """
    import sys
    import sklearn

    path = Path(path)
    if not path.suffix:
        path = path.with_suffix(".joblib")

    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Populate metadata
    bundle.created_at = datetime.utcnow()
    bundle.python_version = sys.version
    bundle.sklearn_version = sklearn.__version__
    bundle.bundle_hash = bundle.compute_hash()

    # Save with compression
    joblib.dump(bundle, path, compress=3)

    return path


def load_model_bundle(path: str | Path) -> ModelBundle:
    """Load model bundle from disk.

    CRITICAL: Logs warning if versions don't match.

    Args:
        path: Path to saved bundle

    Returns:
        Loaded ModelBundle

    Raises:
        FileNotFoundError: If path doesn't exist
    """
    import sys
    import sklearn
    import structlog

    logger = structlog.get_logger()
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Model bundle not found: {path}")

    bundle: ModelBundle = joblib.load(path)

    # Version compatibility warnings
    if bundle.python_version and not sys.version.startswith(bundle.python_version.split()[0]):
        logger.warning(
            "forecasting.model_version_mismatch",
            saved_python=bundle.python_version,
            current_python=sys.version,
        )

    if bundle.sklearn_version and bundle.sklearn_version != sklearn.__version__:
        logger.warning(
            "forecasting.sklearn_version_mismatch",
            saved_sklearn=bundle.sklearn_version,
            current_sklearn=sklearn.__version__,
        )

    return bundle
```

---

## Task List

### Task 1: Add forecasting settings to config

```yaml
FILE: app/core/config.py
ACTION: MODIFY
FIND: "feature_max_window: int = 90"
INJECT AFTER:
  - forecast_random_seed: int = 42
  - forecast_default_horizon: int = 14
  - forecast_max_horizon: int = 90
  - forecast_model_artifacts_dir: str = "./artifacts/models"
  - forecast_enable_lightgbm: bool = False  # Feature flag
VALIDATION:
  - uv run mypy app/core/config.py
  - uv run pyright app/core/config.py
```

### Task 2: Create forecasting module structure

```yaml
ACTION: CREATE directories and __init__.py
FILES:
  - app/features/forecasting/__init__.py
  - app/features/forecasting/tests/__init__.py
PATTERN: Mirror featuresets module exports
```

### Task 3: Implement schemas.py

```yaml
FILE: app/features/forecasting/schemas.py
ACTION: CREATE
IMPLEMENT:
  - ModelConfigBase with frozen=True, config_hash()
  - NaiveModelConfig, SeasonalNaiveModelConfig, MovingAverageModelConfig
  - LightGBMModelConfig (for feature-flagged ML)
  - TrainRequest, PredictRequest schemas
  - ForecastPoint, PredictResponse schemas
  - TrainResponse schema
PATTERN: Mirror app/features/featuresets/schemas.py
VALIDATION:
  - uv run mypy app/features/forecasting/schemas.py
  - uv run pyright app/features/forecasting/schemas.py
```

### Task 4: Implement models.py (BaseForecaster + baselines)

```yaml
FILE: app/features/forecasting/models.py
ACTION: CREATE
IMPLEMENT:
  - FitResult dataclass
  - BaseForecaster ABC with fit/predict/get_params/set_params
  - NaiveForecaster implementation
  - SeasonalNaiveForecaster implementation
  - MovingAverageForecaster implementation
  - model_factory() function to instantiate by type
CRITICAL:
  - All models must be deterministic with random_state
  - Store last N values for prediction
  - Raise RuntimeError if predict called before fit
VALIDATION:
  - uv run mypy app/features/forecasting/models.py
  - uv run pyright app/features/forecasting/models.py
```

### Task 5: Implement persistence.py

```yaml
FILE: app/features/forecasting/persistence.py
ACTION: CREATE
IMPLEMENT:
  - ModelBundle dataclass
  - save_model_bundle() with joblib compression
  - load_model_bundle() with version warnings
CRITICAL:
  - Record Python/sklearn versions
  - Compute deterministic bundle hash
  - Log warnings on version mismatch
VALIDATION:
  - uv run mypy app/features/forecasting/persistence.py
  - uv run pyright app/features/forecasting/persistence.py
```

### Task 6: Implement service.py

```yaml
FILE: app/features/forecasting/service.py
ACTION: CREATE
IMPLEMENT:
  - ForecastingService class
  - train_model() method: load data, fit model, save bundle
  - predict() method: load bundle, generate forecasts
  - _load_training_data() helper: query SalesDaily
  - _prepare_features() helper: call FeatureEngineeringService if ML model
CRITICAL:
  - Use cutoff_date = train_end_date for feature computation
  - Validate grain (store_id, product_id)
  - Log forecasting.train_started, forecasting.train_completed
VALIDATION:
  - uv run mypy app/features/forecasting/service.py
  - uv run pyright app/features/forecasting/service.py
```

### Task 7: Implement routes.py

```yaml
FILE: app/features/forecasting/routes.py
ACTION: CREATE
IMPLEMENT:
  - APIRouter(prefix="/forecasting", tags=["forecasting"])
  - POST /train endpoint
  - POST /predict endpoint
  - Error handling with ForecastLabError
PATTERN: Mirror app/features/featuresets/routes.py
CRITICAL:
  - time.perf_counter() for duration_ms
  - Depends(get_db) for database session
  - Structured logging on entry/exit/error
VALIDATION:
  - uv run mypy app/features/forecasting/routes.py
  - uv run pyright app/features/forecasting/routes.py
```

### Task 8: Register router in main.py

```yaml
FILE: app/main.py
ACTION: MODIFY
FIND: "app.include_router(featuresets_router)"
INJECT AFTER:
  - from app.features.forecasting.routes import router as forecasting_router
  - app.include_router(forecasting_router)
VALIDATION:
  - uv run python -c "from app.main import app; print('OK')"
```

### Task 9: Create test fixtures (conftest.py)

```yaml
FILE: app/features/forecasting/tests/conftest.py
ACTION: CREATE
IMPLEMENT:
  - sample_time_series: 60 days of sequential values
  - sample_seasonal_series: data with weekly pattern
  - sample_naive_config, sample_seasonal_config, sample_mavg_config
  - tmp_model_path: temporary path for serialization tests
PATTERN: Mirror app/features/featuresets/tests/conftest.py
```

### Task 10: Create test_schemas.py

```yaml
FILE: app/features/forecasting/tests/test_schemas.py
ACTION: CREATE
IMPLEMENT:
  - Test config validation (positive values, ranges)
  - Test config immutability (frozen=True)
  - Test config_hash() determinism
  - Test TrainRequest date validation
  - Test PredictRequest horizon validation
VALIDATION:
  - uv run pytest app/features/forecasting/tests/test_schemas.py -v
```

### Task 11: Create test_models.py

```yaml
FILE: app/features/forecasting/tests/test_models.py
ACTION: CREATE
IMPLEMENT:
  - TestNaiveForecaster: fit, predict, determinism
  - TestSeasonalNaiveForecaster: fit, predict, seasonal cycling
  - TestMovingAverageForecaster: fit, predict, window averaging
  - Test error on predict before fit
  - Test error on insufficient data
  - Test get_params/set_params
CRITICAL:
  - Use sequential data for determinism verification
  - Assert exact expected values
VALIDATION:
  - uv run pytest app/features/forecasting/tests/test_models.py -v
```

### Task 12: Create test_persistence.py

```yaml
FILE: app/features/forecasting/tests/test_persistence.py
ACTION: CREATE
IMPLEMENT:
  - Test save/load round-trip
  - Test bundle_hash consistency
  - Test version metadata recorded
  - Test FileNotFoundError on missing path
  - Test compression reduces file size
VALIDATION:
  - uv run pytest app/features/forecasting/tests/test_persistence.py -v
```

### Task 13: Create test_service.py

```yaml
FILE: app/features/forecasting/tests/test_service.py
ACTION: CREATE
IMPLEMENT:
  - Test train_model happy path (mock DB)
  - Test predict happy path (mock loaded bundle)
  - Test error handling for missing data
  - Test model_factory returns correct type
VALIDATION:
  - uv run pytest app/features/forecasting/tests/test_service.py -v
```

### Task 14: Create example files

```yaml
FILES:
  - examples/models/baseline_naive.py
  - examples/models/baseline_seasonal.py
  - examples/models/baseline_mavg.py
  - examples/models/model_interface.md
ACTION: CREATE
IMPLEMENT:
  - Runnable demos showing train -> save -> load -> predict
  - Documentation of model interface contract
```

### Task 15: Update module __init__.py exports

```yaml
FILE: app/features/forecasting/__init__.py
ACTION: MODIFY
IMPLEMENT:
  - Export all public classes
  - __all__ list (sorted alphabetically)
VALIDATION:
  - uv run python -c "from app.features.forecasting import *; print('OK')"
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run after EACH file creation
uv run ruff check app/features/forecasting/ --fix
uv run ruff format app/features/forecasting/

# Expected: All checks passed!
```

### Level 2: Type Checking

```bash
# Run after completing schemas, models, persistence, service
uv run mypy app/features/forecasting/
uv run pyright app/features/forecasting/

# Expected: Success: no issues found
```

### Level 3: Unit Tests

```bash
# Run incrementally as tests are created
uv run pytest app/features/forecasting/tests/test_schemas.py -v
uv run pytest app/features/forecasting/tests/test_models.py -v
uv run pytest app/features/forecasting/tests/test_persistence.py -v
uv run pytest app/features/forecasting/tests/test_service.py -v

# Run all
uv run pytest app/features/forecasting/tests/ -v

# Expected: 40+ tests passed
```

### Level 4: Integration Test

```bash
# Start API
uv run uvicorn app.main:app --reload --port 8123

# Test train endpoint (requires seeded DB)
curl -X POST http://localhost:8123/forecasting/train \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": 1,
    "product_id": 1,
    "train_start_date": "2024-01-01",
    "train_end_date": "2024-01-31",
    "config": {"model_type": "naive"}
  }'

# Test predict endpoint
curl -X POST http://localhost:8123/forecasting/predict \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": 1,
    "product_id": 1,
    "horizon": 7,
    "model_path": "./artifacts/models/model_xxx.joblib"
  }'
```

### Level 5: Full Validation

```bash
# Complete validation suite
uv run ruff check app/features/forecasting/ && \
uv run mypy app/features/forecasting/ && \
uv run pyright app/features/forecasting/ && \
uv run pytest app/features/forecasting/tests/ -v

# Expected: All green
```

---

## Final Checklist

- [ ] All 15 tasks completed
- [ ] `uv run ruff check .` — no errors
- [ ] `uv run mypy app/features/forecasting/` — no errors
- [ ] `uv run pyright app/features/forecasting/` — no errors
- [ ] `uv run pytest app/features/forecasting/tests/ -v` — 40+ tests passed
- [ ] Example scripts run successfully
- [ ] Router registered in main.py
- [ ] Settings added to config.py
- [ ] Logging events follow standard format

---

## Anti-Patterns to Avoid

- **DON'T** hardcode horizons or window sizes — use config
- **DON'T** use random operations without `random_state`
- **DON'T** call predict() before fit() — raise RuntimeError
- **DON'T** use pickle directly — use joblib for sklearn compatibility
- **DON'T** ignore version mismatches — log warnings
- **DON'T** store entire training data in model — only store what's needed for prediction
- **DON'T** use future data in feature computation — enforce cutoff_date
- **DON'T** catch generic Exception — be specific

---

## Confidence Score: 8/10

**Strengths:**
- Clear patterns from featuresets module to follow
- Well-documented scikit-learn interface standards
- Comprehensive task breakdown
- Executable validation gates

**Risks:**
- LightGBM integration deferred (feature-flagged)
- Integration tests require seeded database
- Recursive ML forecasting complexity (deferred to backtesting phase)

**Mitigation:**
- Focus on baseline models first (naive, seasonal, moving average)
- LightGBM is optional and feature-flagged
- Recursive forecasting for ML models will be addressed in INITIAL-6

---

## Sources

- [Developing scikit-learn estimators](https://scikit-learn.org/stable/developers/develop.html)
- [scikit-learn Model Persistence](https://scikit-learn.org/stable/model_persistence.html)
- [scikit-learn Pipeline Composition](https://scikit-learn.org/stable/modules/compose.html)
- [Skforecast Recursive Multi-step Forecasting](https://skforecast.org/0.9.1/user_guides/autoregresive-forecaster)
- [Naive Time Series Forecasting in Python](https://forecastegy.com/posts/naive-time-series-forecasting-in-python/)
- [Multi-Step Time Series Forecasting Strategies](https://machinelearningmastery.com/multi-step-time-series-forecasting/)
- [Seasonal Persistence Forecasting](https://machinelearningmastery.com/seasonal-persistence-forecasting-python/)
