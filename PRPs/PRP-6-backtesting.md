# PRP-6: Backtesting + Metrics (ForecastOps Core)

## Goal

Implement a comprehensive backtesting framework for time-series forecasting models with time-based cross-validation, a full metrics suite, and data lineage for UI visualization. The module provides configurable splitting strategies (expanding/sliding windows with gap support), per-series and aggregated metrics, and mandatory baseline comparisons.

**End State:** A production-ready `backtesting` vertical slice with:
- `TimeSeriesSplitter` — Generates time-based train/test splits (expanding/sliding + gap)
- `BacktestConfig` — Immutable configuration with validation and config_hash()
- `MetricsCalculator` — Computes MAE, sMAPE, WAPE, Forecast Bias, Stability Index
- `BacktestResult` — Per-fold actuals vs predictions with lineage metadata
- `BacktestingService` — Orchestrates split generation, model training, prediction, evaluation
- `POST /backtesting/run` — Execute backtest for a series with configurable strategy
- `GET /backtesting/results/{backtest_id}` — Retrieve backtest results with fold details
- Mandatory baseline comparison (naive/seasonal_naive)
- All validation gates passing (ruff, mypy, pyright, pytest)

---

## Why

- **Model Validation**: Backtesting is the gold standard for evaluating time-series models
- **Leakage Prevention**: Time-based splits ensure no future data contaminates training
- **Metric Transparency**: Per-series distributions expose failures that aggregation masks
- **Baseline Benchmarking**: Every model must beat naive baselines to justify complexity
- **Reproducibility**: Stored split boundaries + config hash enable exact replication
- **UI Integration**: Actual vs Predicted datasets per fold enable rich visualizations

---

## What

### User-Visible Behavior

1. **Run Backtest**: Accept series ID, model config, split strategy, return backtest_id
2. **Retrieve Results**: Get per-fold metrics, aggregated metrics, actual vs predicted data
3. **Split Strategies**: Expanding window (default), sliding window, configurable gap
4. **Metrics Suite**: MAE, sMAPE, WAPE, Forecast Bias, Stability Index
5. **Baseline Comparison**: Automatic benchmarking against naive and seasonal_naive

### Success Criteria

- [ ] TimeSeriesSplitter generates correct expanding/sliding splits with gap
- [ ] All 5 metrics implemented with edge case handling (zeros, empty arrays)
- [ ] BacktestingService orchestrates train → predict → evaluate loop
- [ ] Per-fold actuals vs predictions stored for UI lineage
- [ ] Baseline comparison runs automatically with every backtest
- [ ] Leakage sanity checks verify no future data in training
- [ ] 50+ unit tests covering splits, metrics, service, routes
- [ ] Example files demonstrating each splitting strategy

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ - Include these in your context window

# sklearn TimeSeriesSplit (expanding window only)
- url: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
  why: "Reference implementation for expanding window, gap parameter"
  critical: "sklearn only supports expanding; we need sliding window too"

# Skforecast Backtesting Guide
- url: https://skforecast.org/0.14.0/user_guides/backtesting.html
  why: "backtesting_forecaster() patterns, refit strategies"
  critical: "Supports both expanding and sliding windows with custom metrics"

# Time Series Cross-Validation Best Practices
- url: https://forecastegy.com/posts/time-series-cross-validation-python/
  why: "Visual diagrams of expanding vs sliding windows"
  critical: "Gap parameter simulates operational data latency"

# sMAPE Definition and Edge Cases
- url: https://en.wikipedia.org/wiki/Symmetric_mean_absolute_percentage_error
  why: "Formula: 100/n * sum(2*|F-A|/(|A|+|F|))"
  critical: "Undefined when both actual and forecast are 0; use fallback"

# WAPE vs MAPE Comparison
- url: https://www.baeldung.com/cs/mape-vs-wape-vs-wmape
  why: "WAPE = sum(|A-F|) / sum(|A|) * 100"
  critical: "WAPE handles low/zero values better than MAPE"

# Forecast Bias Definition
- url: https://demandplanning.net/mape-wmape-and-forecast-bias/
  why: "Bias = sum(A-F) / n; negative = over-forecast"
  critical: "Detects systematic over/under forecasting"

# Backtest Machine Learning Models for Time Series
- url: https://machinelearningmastery.com/backtest-machine-learning-models-time-series-forecasting/
  why: "Walk-forward validation patterns"
  critical: "Emphasizes importance of no data leakage"

# Internal Codebase References
- file: app/features/forecasting/models.py
  why: "BaseForecaster interface for fit/predict"

- file: app/features/forecasting/service.py
  why: "Pattern for ForecastingService with async DB operations"

- file: app/features/forecasting/schemas.py
  why: "Pattern for ModelConfig with config_hash()"

- file: app/features/featuresets/service.py
  why: "Pattern for cutoff_date enforcement (leakage prevention)"

- file: app/core/config.py
  why: "Pattern for Settings with environment variables"

- file: PRPs/PRP-5-forecasting.md
  why: "Reference PRP structure and task breakdown"
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
│   │   └── service.py      # FeatureEngineeringService
│   └── forecasting/
│       ├── models.py       # BaseForecaster, NaiveForecaster, etc.
│       ├── schemas.py      # ModelConfig, TrainRequest
│       ├── service.py      # ForecastingService
│       └── persistence.py  # ModelBundle, save/load
└── main.py                 # FastAPI app with router registration
```

### Desired Codebase Tree

```text
app/features/backtesting/              # NEW: Backtesting vertical slice
├── __init__.py                        # Module exports
├── schemas.py                         # BacktestConfig, BacktestRequest, BacktestResponse, etc.
├── splitter.py                        # TimeSeriesSplitter (expanding/sliding + gap)
├── metrics.py                         # MetricsCalculator (MAE, sMAPE, WAPE, Bias, Stability)
├── service.py                         # BacktestingService (orchestration)
├── routes.py                          # POST /backtesting/run, GET /backtesting/results/{id}
└── tests/
    ├── __init__.py
    ├── conftest.py                    # Fixtures: sample series, configs
    ├── test_schemas.py                # Config validation, immutability
    ├── test_splitter.py               # Split generation, gap handling
    ├── test_metrics.py                # Metric calculations, edge cases
    ├── test_service.py                # Orchestration logic
    └── test_routes.py                 # Integration tests

examples/backtest/                     # NEW: Example scripts
├── run_backtest.py                    # Execute backtest with different strategies
├── inspect_splits.py                  # Visualize split boundaries
└── metrics_demo.py                    # Metric edge cases (zeros in sMAPE)

app/core/config.py                     # MODIFY: Add backtesting settings
app/main.py                            # MODIFY: Register backtesting router
```

### Known Gotchas

```python
# CRITICAL: sMAPE is undefined when both actual and forecast are 0
# Use epsilon fallback: denominator = max(|A| + |F|, epsilon)
# Return 0.0 when both are exactly 0 (perfect forecast of zero)

# CRITICAL: WAPE divides by sum(|actual|) - handle zero denominator
# When all actuals are 0, return np.inf or raise ValueError

# CRITICAL: Sliding window requires enough data for min_train_size + gap + horizon
# Validate data length before attempting split generation

# CRITICAL: Gap parameter simulates operational latency
# gap=1 means 1 day between last training date and first forecast date
# This is common in production where data has reporting delays

# CRITICAL: Stability Index measures forecast consistency across folds
# Formula: std(fold_metrics) / mean(fold_metrics) * 100
# Lower is better; high values indicate unstable model

# CRITICAL: Baseline comparison is MANDATORY
# Every backtest must include naive and seasonal_naive benchmarks
# If custom model doesn't beat baselines, warn user

# CRITICAL: Per-fold actuals vs predictions must be stored
# This enables UI visualization of forecast errors over time
# Store as list of FoldResult with dates, actuals, predictions

# CRITICAL: Use cutoff_date = train_end_date for feature computation
# This is inherited from forecasting module - no future data
```

---

## Implementation Blueprint

### Data Models and Schemas

```python
# app/features/backtesting/schemas.py

from __future__ import annotations
from datetime import date as date_type
from typing import Literal
import hashlib

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SplitConfig(BaseModel):
    """Configuration for time-series splitting."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy: Literal["expanding", "sliding"] = Field(
        default="expanding",
        description="Expanding grows training window; sliding keeps fixed size"
    )
    n_splits: int = Field(default=5, ge=2, le=20, description="Number of CV folds")
    min_train_size: int = Field(default=30, ge=7, description="Minimum training samples")
    gap: int = Field(default=0, ge=0, le=30, description="Gap between train end and test start")
    horizon: int = Field(default=14, ge=1, le=90, description="Forecast horizon per fold")

    @field_validator("horizon")
    @classmethod
    def validate_horizon_vs_gap(cls, v: int, info) -> int:
        """Ensure horizon is reasonable relative to gap."""
        data = getattr(info, "data", {})
        gap = data.get("gap", 0)
        if v <= gap:
            raise ValueError(f"horizon ({v}) must be greater than gap ({gap})")
        return v


class BacktestConfig(BaseModel):
    """Complete backtest configuration."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(default="1.0", pattern=r"^\d+\.\d+(\.\d+)?$")
    split_config: SplitConfig = Field(default_factory=SplitConfig)
    model_config_main: ModelConfig  # The model to evaluate (from forecasting.schemas)
    include_baselines: bool = Field(default=True, description="Include naive/seasonal benchmarks")
    store_fold_details: bool = Field(default=True, description="Store per-fold actuals/predictions")

    def config_hash(self) -> str:
        """Deterministic hash for reproducibility."""
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:16]


class SplitBoundary(BaseModel):
    """Boundary dates for a single CV split."""
    fold_index: int
    train_start: date_type
    train_end: date_type
    test_start: date_type
    test_end: date_type
    train_size: int
    test_size: int


class FoldResult(BaseModel):
    """Results for a single backtest fold."""
    fold_index: int
    split: SplitBoundary
    dates: list[date_type]
    actuals: list[float]
    predictions: list[float]
    metrics: dict[str, float]  # {"mae": 1.23, "smape": 5.67, ...}


class ModelBacktestResult(BaseModel):
    """Backtest results for a single model."""
    model_type: str
    config_hash: str
    fold_results: list[FoldResult]
    aggregated_metrics: dict[str, float]  # Mean across folds
    metric_std: dict[str, float]  # Std across folds for stability


class BacktestResponse(BaseModel):
    """Complete backtest response."""
    backtest_id: str
    store_id: int
    product_id: int
    config_hash: str
    split_config: SplitConfig
    main_model_results: ModelBacktestResult
    baseline_results: list[ModelBacktestResult] | None = None  # naive, seasonal_naive
    comparison_summary: dict[str, dict[str, float]] | None = None  # Model vs baselines
    duration_ms: float
    leakage_check_passed: bool
```

### Time Series Splitter

```python
# app/features/backtesting/splitter.py

from __future__ import annotations
from dataclasses import dataclass
from datetime import date as date_type, timedelta
from typing import Iterator

import numpy as np

from app.features.backtesting.schemas import SplitBoundary, SplitConfig


@dataclass
class TimeSeriesSplit:
    """A single train/test split with indices and dates."""
    fold_index: int
    train_indices: np.ndarray
    test_indices: np.ndarray
    train_dates: list[date_type]
    test_dates: list[date_type]


class TimeSeriesSplitter:
    """Generate time-based CV splits with expanding or sliding window.

    CRITICAL: Respects temporal order - no future data in training.

    Expanding Window:
        Fold 1: [0..30] train, [31..44] test
        Fold 2: [0..44] train, [45..58] test  (training grows)
        Fold 3: [0..58] train, [59..72] test

    Sliding Window:
        Fold 1: [0..30] train, [31..44] test
        Fold 2: [14..44] train, [45..58] test  (training slides)
        Fold 3: [28..58] train, [59..72] test

    Gap Parameter:
        gap=1 inserts 1 day between train_end and test_start
        This simulates operational data latency
    """

    def __init__(self, config: SplitConfig) -> None:
        self.config = config

    def split(
        self,
        dates: list[date_type],
        y: np.ndarray,
    ) -> Iterator[TimeSeriesSplit]:
        """Generate train/test splits.

        Args:
            dates: Sorted list of dates (must match y length)
            y: Target values array

        Yields:
            TimeSeriesSplit objects for each fold

        Raises:
            ValueError: If data is insufficient for requested splits
        """
        n_samples = len(dates)
        min_required = self.config.min_train_size + self.config.gap + self.config.horizon

        if n_samples < min_required:
            raise ValueError(
                f"Need at least {min_required} samples, got {n_samples}. "
                f"(min_train={self.config.min_train_size}, gap={self.config.gap}, "
                f"horizon={self.config.horizon})"
            )

        # Calculate test set positions
        test_size = self.config.horizon
        n_splits = self.config.n_splits

        # Work backwards from end of data
        # Last test set ends at n_samples
        # Each fold's test set is `test_size` samples
        # We need n_splits * test_size for test sets
        total_test_samples = n_splits * test_size

        # First fold's train_end position
        if self.config.strategy == "expanding":
            # Expanding: first train ends at min_train_size
            first_train_end = self.config.min_train_size
        else:
            # Sliding: calculate so last fold uses all data
            # Last fold: train_end + gap + test_size = n_samples
            # Working backwards...
            first_train_end = self.config.min_train_size

        # Calculate step size between folds
        available_for_folds = n_samples - first_train_end - self.config.gap - test_size
        step = max(1, available_for_folds // (n_splits - 1)) if n_splits > 1 else 0

        for fold_idx in range(n_splits):
            if self.config.strategy == "expanding":
                # Training starts at 0, ends grow with each fold
                train_start_idx = 0
                train_end_idx = first_train_end + (fold_idx * step)
            else:
                # Sliding: both start and end move forward
                train_start_idx = fold_idx * step
                train_end_idx = train_start_idx + self.config.min_train_size + (fold_idx * step // (n_splits or 1))
                # Ensure minimum train size
                train_end_idx = max(train_end_idx, train_start_idx + self.config.min_train_size)

            # Test starts after gap
            test_start_idx = train_end_idx + self.config.gap
            test_end_idx = min(test_start_idx + test_size, n_samples)

            # Bounds check
            if test_end_idx > n_samples or train_end_idx >= n_samples:
                break

            yield TimeSeriesSplit(
                fold_index=fold_idx,
                train_indices=np.arange(train_start_idx, train_end_idx),
                test_indices=np.arange(test_start_idx, test_end_idx),
                train_dates=dates[train_start_idx:train_end_idx],
                test_dates=dates[test_start_idx:test_end_idx],
            )

    def get_boundaries(self, dates: list[date_type], y: np.ndarray) -> list[SplitBoundary]:
        """Get split boundaries without full split objects."""
        boundaries = []
        for split in self.split(dates, y):
            boundaries.append(SplitBoundary(
                fold_index=split.fold_index,
                train_start=split.train_dates[0],
                train_end=split.train_dates[-1],
                test_start=split.test_dates[0],
                test_end=split.test_dates[-1],
                train_size=len(split.train_indices),
                test_size=len(split.test_indices),
            ))
        return boundaries
```

### Metrics Calculator

```python
# app/features/backtesting/metrics.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class MetricResult:
    """Result of a single metric calculation."""
    name: str
    value: float
    n_samples: int
    warnings: list[str]


class MetricsCalculator:
    """Calculate forecasting accuracy metrics.

    Supported Metrics:
    - MAE: Mean Absolute Error
    - sMAPE: Symmetric Mean Absolute Percentage Error
    - WAPE: Weighted Absolute Percentage Error
    - Bias: Forecast Bias (positive = under-forecast)
    - Stability: Coefficient of variation of per-fold metrics

    CRITICAL: All metrics handle edge cases (zeros, empty arrays).
    """

    EPSILON = 1e-10  # Fallback for division by zero

    @staticmethod
    def mae(actuals: np.ndarray, predictions: np.ndarray) -> MetricResult:
        """Mean Absolute Error.

        Formula: mean(|actual - predicted|)

        Args:
            actuals: Ground truth values
            predictions: Predicted values

        Returns:
            MetricResult with MAE value
        """
        warnings: list[str] = []

        if len(actuals) == 0:
            return MetricResult(name="mae", value=np.nan, n_samples=0, warnings=["Empty array"])

        if len(actuals) != len(predictions):
            raise ValueError(f"Length mismatch: actuals={len(actuals)}, predictions={len(predictions)}")

        mae_value = float(np.mean(np.abs(actuals - predictions)))

        return MetricResult(name="mae", value=mae_value, n_samples=len(actuals), warnings=warnings)

    @staticmethod
    def smape(actuals: np.ndarray, predictions: np.ndarray) -> MetricResult:
        """Symmetric Mean Absolute Percentage Error.

        Formula: 100/n * sum(2 * |A - F| / (|A| + |F|))

        CRITICAL: When both A and F are 0, contributes 0 to sum (perfect forecast).
        Uses epsilon fallback to avoid division by zero.

        Args:
            actuals: Ground truth values
            predictions: Predicted values

        Returns:
            MetricResult with sMAPE value (0-200 scale)
        """
        warnings: list[str] = []

        if len(actuals) == 0:
            return MetricResult(name="smape", value=np.nan, n_samples=0, warnings=["Empty array"])

        if len(actuals) != len(predictions):
            raise ValueError(f"Length mismatch: actuals={len(actuals)}, predictions={len(predictions)}")

        numerator = 2 * np.abs(actuals - predictions)
        denominator = np.abs(actuals) + np.abs(predictions)

        # Handle zeros: when both are 0, result is 0 (perfect forecast of zero)
        # When denominator is 0 but numerator isn't, use epsilon
        with np.errstate(divide='ignore', invalid='ignore'):
            ratios = np.where(
                (actuals == 0) & (predictions == 0),
                0.0,  # Perfect forecast of zero
                np.where(
                    denominator == 0,
                    2.0,  # Maximum error (shouldn't happen if above handles 0/0)
                    numerator / denominator
                )
            )

        smape_value = float(100.0 * np.mean(ratios))

        n_zeros = int(np.sum((actuals == 0) | (predictions == 0)))
        if n_zeros > 0:
            warnings.append(f"{n_zeros} samples with zero values")

        return MetricResult(name="smape", value=smape_value, n_samples=len(actuals), warnings=warnings)

    @staticmethod
    def wape(actuals: np.ndarray, predictions: np.ndarray) -> MetricResult:
        """Weighted Absolute Percentage Error.

        Formula: sum(|A - F|) / sum(|A|) * 100

        CRITICAL: Better than MAPE for intermittent/low-volume series.
        Returns inf if sum of actuals is zero.

        Args:
            actuals: Ground truth values
            predictions: Predicted values

        Returns:
            MetricResult with WAPE value
        """
        warnings: list[str] = []

        if len(actuals) == 0:
            return MetricResult(name="wape", value=np.nan, n_samples=0, warnings=["Empty array"])

        if len(actuals) != len(predictions):
            raise ValueError(f"Length mismatch: actuals={len(actuals)}, predictions={len(predictions)}")

        sum_abs_error = float(np.sum(np.abs(actuals - predictions)))
        sum_abs_actual = float(np.sum(np.abs(actuals)))

        if sum_abs_actual == 0:
            warnings.append("Sum of actuals is zero; WAPE undefined")
            return MetricResult(name="wape", value=np.inf, n_samples=len(actuals), warnings=warnings)

        wape_value = (sum_abs_error / sum_abs_actual) * 100.0

        return MetricResult(name="wape", value=wape_value, n_samples=len(actuals), warnings=warnings)

    @staticmethod
    def bias(actuals: np.ndarray, predictions: np.ndarray) -> MetricResult:
        """Forecast Bias.

        Formula: mean(actual - predicted)

        Interpretation:
        - Positive: Model under-forecasts (actuals > predictions)
        - Negative: Model over-forecasts (actuals < predictions)
        - Zero: No systematic bias

        Args:
            actuals: Ground truth values
            predictions: Predicted values

        Returns:
            MetricResult with Bias value
        """
        warnings: list[str] = []

        if len(actuals) == 0:
            return MetricResult(name="bias", value=np.nan, n_samples=0, warnings=["Empty array"])

        if len(actuals) != len(predictions):
            raise ValueError(f"Length mismatch: actuals={len(actuals)}, predictions={len(predictions)}")

        bias_value = float(np.mean(actuals - predictions))

        if abs(bias_value) > np.std(actuals - predictions):
            warnings.append("Bias exceeds error standard deviation; systematic over/under-forecasting detected")

        return MetricResult(name="bias", value=bias_value, n_samples=len(actuals), warnings=warnings)

    @staticmethod
    def stability_index(fold_metric_values: list[float]) -> MetricResult:
        """Stability Index (coefficient of variation across folds).

        Formula: std(metrics) / mean(metrics) * 100

        Interpretation:
        - Lower is better (more stable model)
        - High values indicate inconsistent performance across time periods

        Args:
            fold_metric_values: List of metric values from each fold

        Returns:
            MetricResult with Stability Index value
        """
        warnings: list[str] = []

        if len(fold_metric_values) < 2:
            return MetricResult(
                name="stability_index",
                value=np.nan,
                n_samples=len(fold_metric_values),
                warnings=["Need at least 2 folds for stability calculation"]
            )

        values = np.array(fold_metric_values)
        mean_val = float(np.mean(values))
        std_val = float(np.std(values))

        if mean_val == 0:
            warnings.append("Mean is zero; stability index undefined")
            return MetricResult(name="stability_index", value=np.inf, n_samples=len(fold_metric_values), warnings=warnings)

        stability = (std_val / abs(mean_val)) * 100.0

        if stability > 50:
            warnings.append("High instability (>50%); model performance varies significantly across folds")

        return MetricResult(name="stability_index", value=stability, n_samples=len(fold_metric_values), warnings=warnings)

    def calculate_all(
        self,
        actuals: np.ndarray,
        predictions: np.ndarray
    ) -> dict[str, float]:
        """Calculate all point metrics for a single fold.

        Args:
            actuals: Ground truth values
            predictions: Predicted values

        Returns:
            Dictionary of metric name to value
        """
        return {
            "mae": self.mae(actuals, predictions).value,
            "smape": self.smape(actuals, predictions).value,
            "wape": self.wape(actuals, predictions).value,
            "bias": self.bias(actuals, predictions).value,
        }

    def aggregate_fold_metrics(
        self,
        fold_metrics: list[dict[str, float]],
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Aggregate metrics across folds.

        Args:
            fold_metrics: List of per-fold metric dictionaries

        Returns:
            Tuple of (aggregated_means, stability_std)
        """
        if not fold_metrics:
            return {}, {}

        metric_names = fold_metrics[0].keys()
        aggregated: dict[str, float] = {}
        stability: dict[str, float] = {}

        for name in metric_names:
            values = [fm[name] for fm in fold_metrics if not np.isnan(fm[name])]
            if values:
                aggregated[name] = float(np.mean(values))
                stability[f"{name}_stability"] = self.stability_index(values).value
            else:
                aggregated[name] = np.nan
                stability[f"{name}_stability"] = np.nan

        return aggregated, stability
```

---

## Task List

### Task 1: Add backtesting settings to config

```yaml
FILE: app/core/config.py
ACTION: MODIFY
FIND: "forecast_enable_lightgbm: bool = False"
INJECT AFTER:
  - "# Backtesting"
  - "backtest_max_splits: int = 20"
  - "backtest_default_min_train_size: int = 30"
  - "backtest_max_gap: int = 30"
  - "backtest_results_dir: str = './artifacts/backtests'"
VALIDATION:
  - uv run mypy app/core/config.py
  - uv run pyright app/core/config.py
```

### Task 2: Create backtesting module structure

```yaml
ACTION: CREATE directories and __init__.py
FILES:
  - app/features/backtesting/__init__.py
  - app/features/backtesting/tests/__init__.py
PATTERN: Mirror forecasting module exports
```

### Task 3: Implement schemas.py

```yaml
FILE: app/features/backtesting/schemas.py
ACTION: CREATE
IMPLEMENT:
  - SplitConfig with frozen=True, strategy validation
  - BacktestConfig with config_hash()
  - SplitBoundary for fold boundaries
  - FoldResult for per-fold actuals/predictions
  - ModelBacktestResult for single model results
  - BacktestRequest, BacktestResponse schemas
PATTERN: Mirror app/features/forecasting/schemas.py
CRITICAL:
  - Import ModelConfig from forecasting.schemas
  - Validate horizon > gap
  - Use Literal["expanding", "sliding"] for strategy
VALIDATION:
  - uv run mypy app/features/backtesting/schemas.py
  - uv run pyright app/features/backtesting/schemas.py
```

### Task 4: Implement splitter.py

```yaml
FILE: app/features/backtesting/splitter.py
ACTION: CREATE
IMPLEMENT:
  - TimeSeriesSplit dataclass (indices + dates)
  - TimeSeriesSplitter class with split() generator
  - get_boundaries() for boundary inspection
  - Support expanding and sliding strategies
  - Gap parameter between train end and test start
CRITICAL:
  - Validate sufficient data for requested splits
  - Expanding: train grows, start stays at 0
  - Sliding: both start and end move forward
  - Yield splits in chronological order
VALIDATION:
  - uv run mypy app/features/backtesting/splitter.py
  - uv run pyright app/features/backtesting/splitter.py
```

### Task 5: Implement metrics.py

```yaml
FILE: app/features/backtesting/metrics.py
ACTION: CREATE
IMPLEMENT:
  - MetricResult dataclass with warnings
  - MetricsCalculator class
  - mae() - Mean Absolute Error
  - smape() - Symmetric Mean Absolute Percentage Error
  - wape() - Weighted Absolute Percentage Error
  - bias() - Forecast Bias
  - stability_index() - Coefficient of variation
  - calculate_all() - Compute all metrics for a fold
  - aggregate_fold_metrics() - Mean + stability across folds
CRITICAL:
  - Handle zeros in sMAPE denominator
  - Handle zero sum of actuals in WAPE
  - Return np.nan for empty arrays
  - Log warnings for edge cases
VALIDATION:
  - uv run mypy app/features/backtesting/metrics.py
  - uv run pyright app/features/backtesting/metrics.py
```

### Task 6: Implement service.py

```yaml
FILE: app/features/backtesting/service.py
ACTION: CREATE
IMPLEMENT:
  - BacktestingService class
  - run_backtest() - Main orchestration method
  - _load_series_data() - Query SalesDaily for series
  - _run_single_model_backtest() - Train/predict/evaluate per fold
  - _run_baseline_comparison() - Run naive + seasonal_naive
  - _check_leakage() - Verify no future data in training
  - _generate_comparison_summary() - Model vs baselines
CRITICAL:
  - Use ForecastingService for model training/prediction
  - Cutoff date = train_end for each fold
  - Store per-fold actuals/predictions if config.store_fold_details
  - Return BacktestResponse with all results
PATTERN: Mirror app/features/forecasting/service.py
VALIDATION:
  - uv run mypy app/features/backtesting/service.py
  - uv run pyright app/features/backtesting/service.py
```

### Task 7: Implement routes.py

```yaml
FILE: app/features/backtesting/routes.py
ACTION: CREATE
IMPLEMENT:
  - APIRouter(prefix="/backtesting", tags=["backtesting"])
  - POST /run - Execute backtest, return results
  - GET /results/{backtest_id} - (Optional) Retrieve stored results
PATTERN: Mirror app/features/forecasting/routes.py
CRITICAL:
  - time.perf_counter() for duration_ms
  - Depends(get_db) for database session
  - Structured logging: backtesting.run_started, backtesting.run_completed
  - Return 400 for insufficient data
VALIDATION:
  - uv run mypy app/features/backtesting/routes.py
  - uv run pyright app/features/backtesting/routes.py
```

### Task 8: Register router in main.py

```yaml
FILE: app/main.py
ACTION: MODIFY
FIND: "app.include_router(forecasting_router)"
INJECT AFTER:
  - "from app.features.backtesting.routes import router as backtesting_router"
  - "app.include_router(backtesting_router)"
VALIDATION:
  - uv run python -c "from app.main import app; print('OK')"
```

### Task 9: Create test fixtures (conftest.py)

```yaml
FILE: app/features/backtesting/tests/conftest.py
ACTION: CREATE
IMPLEMENT:
  - sample_daily_series: 120 days of sequential dates + values
  - sample_seasonal_series: 84 days (12 weeks) with weekly pattern
  - sample_split_config_expanding: SplitConfig with strategy="expanding"
  - sample_split_config_sliding: SplitConfig with strategy="sliding"
  - sample_backtest_config: Full BacktestConfig with naive model
PATTERN: Mirror app/features/forecasting/tests/conftest.py
```

### Task 10: Create test_schemas.py

```yaml
FILE: app/features/backtesting/tests/test_schemas.py
ACTION: CREATE
IMPLEMENT:
  - Test SplitConfig validation (positive values, ranges)
  - Test SplitConfig strategy validation ("expanding", "sliding")
  - Test SplitConfig horizon > gap validation
  - Test BacktestConfig immutability (frozen=True)
  - Test config_hash() determinism
VALIDATION:
  - uv run pytest app/features/backtesting/tests/test_schemas.py -v
```

### Task 11: Create test_splitter.py

```yaml
FILE: app/features/backtesting/tests/test_splitter.py
ACTION: CREATE
IMPLEMENT:
  - TestTimeSeriesSplitter class
  - test_expanding_window_splits: Train grows, start stays at 0
  - test_sliding_window_splits: Both start and end move
  - test_gap_between_train_test: Verify gap days between train_end and test_start
  - test_insufficient_data_raises: ValueError for too little data
  - test_boundaries_match_split_indices: get_boundaries() consistency
  - test_no_overlap_between_folds: Verify non-overlapping test sets
  - test_chronological_order: Folds are in time order
CRITICAL:
  - Assert exact indices for deterministic splits
  - Verify train/test don't overlap
  - Verify gap is respected
VALIDATION:
  - uv run pytest app/features/backtesting/tests/test_splitter.py -v
```

### Task 12: Create test_metrics.py

```yaml
FILE: app/features/backtesting/tests/test_metrics.py
ACTION: CREATE
IMPLEMENT:
  - TestMAE: Basic calculation, empty array, length mismatch
  - TestSMAPE: Basic calculation, zeros handling, both-zero case
  - TestWAPE: Basic calculation, zero actuals
  - TestBias: Positive bias (under-forecast), negative bias (over-forecast)
  - TestStabilityIndex: Low stability (good), high stability (bad)
  - TestCalculateAll: All metrics at once
  - TestAggregateFoldMetrics: Mean and stability across folds
CRITICAL:
  - Test edge case: actuals = [0, 0, 0], predictions = [0, 0, 0]
  - Test edge case: actuals = [0, 1, 2], predictions = [0.5, 0.5, 0.5]
  - Assert exact expected values for known inputs
VALIDATION:
  - uv run pytest app/features/backtesting/tests/test_metrics.py -v
```

### Task 13: Create test_service.py

```yaml
FILE: app/features/backtesting/tests/test_service.py
ACTION: CREATE
IMPLEMENT:
  - Test run_backtest happy path (mock DB, mock ForecastingService)
  - Test baseline comparison included when config.include_baselines=True
  - Test fold_details stored when config.store_fold_details=True
  - Test leakage check passes for valid splits
  - Test insufficient data returns appropriate error
  - Test comparison_summary shows model vs baselines
VALIDATION:
  - uv run pytest app/features/backtesting/tests/test_service.py -v
```

### Task 14: Create test_routes.py (optional integration)

```yaml
FILE: app/features/backtesting/tests/test_routes.py
ACTION: CREATE
IMPLEMENT:
  - Test POST /backtesting/run with valid request
  - Test 400 response for insufficient data
  - Test 422 response for invalid config
PATTERN: Mirror app/features/forecasting/tests/ patterns
VALIDATION:
  - uv run pytest app/features/backtesting/tests/test_routes.py -v
```

### Task 15: Create example files

```yaml
FILES:
  - examples/backtest/run_backtest.py
  - examples/backtest/inspect_splits.py
  - examples/backtest/metrics_demo.py
ACTION: CREATE
IMPLEMENT:
  - run_backtest.py: Execute backtest with expanding and sliding configs
  - inspect_splits.py: Visualize split boundaries with print output
  - metrics_demo.py: Show metric calculations with edge cases
```

### Task 16: Update module __init__.py exports

```yaml
FILE: app/features/backtesting/__init__.py
ACTION: MODIFY
IMPLEMENT:
  - Export all public classes
  - __all__ list (sorted alphabetically)
VALIDATION:
  - uv run python -c "from app.features.backtesting import *; print('OK')"
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run after EACH file creation
uv run ruff check app/features/backtesting/ --fix
uv run ruff format app/features/backtesting/

# Expected: All checks passed!
```

### Level 2: Type Checking

```bash
# Run after completing schemas, splitter, metrics, service
uv run mypy app/features/backtesting/
uv run pyright app/features/backtesting/

# Expected: Success: no issues found
```

### Level 3: Unit Tests

```bash
# Run incrementally as tests are created
uv run pytest app/features/backtesting/tests/test_schemas.py -v
uv run pytest app/features/backtesting/tests/test_splitter.py -v
uv run pytest app/features/backtesting/tests/test_metrics.py -v
uv run pytest app/features/backtesting/tests/test_service.py -v

# Run all
uv run pytest app/features/backtesting/tests/ -v

# Expected: 50+ tests passed
```

### Level 4: Integration Test

```bash
# Start API
uv run uvicorn app.main:app --reload --port 8123

# Test backtest endpoint (requires seeded DB with 120+ days of data)
curl -X POST http://localhost:8123/backtesting/run \
  -H "Content-Type: application/json" \
  -d '{
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
        "horizon": 14
      },
      "model_config_main": {
        "model_type": "naive"
      },
      "include_baselines": true,
      "store_fold_details": true
    }
  }'

# Expected: JSON with main_model_results, baseline_results, comparison_summary
```

### Level 5: Full Validation

```bash
# Complete validation suite
uv run ruff check app/features/backtesting/ && \
uv run mypy app/features/backtesting/ && \
uv run pyright app/features/backtesting/ && \
uv run pytest app/features/backtesting/tests/ -v

# Expected: All green
```

---

## Final Checklist

- [ ] All 16 tasks completed
- [ ] `uv run ruff check .` — no errors
- [ ] `uv run mypy app/features/backtesting/` — no errors
- [ ] `uv run pyright app/features/backtesting/` — no errors
- [ ] `uv run pytest app/features/backtesting/tests/ -v` — 50+ tests passed
- [ ] Example scripts run successfully
- [ ] Router registered in main.py
- [ ] Settings added to config.py
- [ ] Logging events follow standard format
- [ ] Baseline comparison works automatically
- [ ] Per-fold actuals/predictions stored for UI

---

## Anti-Patterns to Avoid

- **DON'T** use random splits — time-series requires temporal ordering
- **DON'T** ignore the gap parameter — it simulates real operational latency
- **DON'T** aggregate metrics without exposing per-fold distributions
- **DON'T** skip baseline comparison — it's mandatory for model validation
- **DON'T** use future data in training — enforce cutoff_date strictly
- **DON'T** catch generic Exception — be specific about error types
- **DON'T** hardcode metric thresholds — make them configurable
- **DON'T** silently handle zero division — return np.nan with warnings

---

## Confidence Score: 8/10

**Strengths:**
- Clear patterns from forecasting module to follow
- Well-documented time-series CV patterns (sklearn, skforecast)
- Comprehensive metrics suite with edge case handling
- Strong task breakdown with validation gates
- Baseline comparison ensures practical model evaluation

**Risks:**
- Service orchestration complexity (train/predict loop per fold)
- Database queries for large series may need optimization
- Integration tests require seeded database with sufficient data
- Sliding window logic is more complex than expanding

**Mitigation:**
- Focus on expanding window first (simpler, matches sklearn)
- Add pagination/batching for large series if needed
- Provide seed script with 120+ days of data
- Thoroughly test sliding window edge cases

---

## Sources

- [sklearn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)
- [Skforecast Backtesting Guide](https://skforecast.org/0.14.0/user_guides/backtesting.html)
- [Time Series Cross-Validation Best Practices](https://forecastegy.com/posts/time-series-cross-validation-python/)
- [sMAPE Definition (Wikipedia)](https://en.wikipedia.org/wiki/Symmetric_mean_absolute_percentage_error)
- [MAPE vs WAPE vs WMAPE (Baeldung)](https://www.baeldung.com/cs/mape-vs-wape-vs-wmape)
- [Forecast Bias Definition](https://demandplanning.net/mape-wmape-and-forecast-bias/)
- [Backtest ML Models for Time Series](https://machinelearningmastery.com/backtest-machine-learning-models-time-series-forecasting/)
