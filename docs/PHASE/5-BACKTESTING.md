# Phase 5: Backtesting

**Date Completed**: 2026-01-31
**PRP**: [PRP-6-backtesting.md](../../PRPs/PRP-6-backtesting.md)
**Release**: PR #32

---

## Executive Summary

Phase 5 implements the Backtesting Framework for ForecastLabAI with CRITICAL time-series cross-validation patterns. The module provides expanding and sliding window strategies with configurable gap parameters to simulate operational data latency, comprehensive accuracy metrics, and mandatory baseline comparisons.

**Key Achievement**: Time-based CV with zero leakage through explicit temporal ordering and built-in leakage validation checks.

---

## Deliverables

### 1. TimeSeriesSplitter

**File**: `app/features/backtesting/splitter.py`

Core splitter for generating train/test splits:

```python
class TimeSeriesSplitter:
    """Generate time-based CV splits with expanding or sliding window.

    CRITICAL: Respects temporal order - no future data in training.

    Expanding Window Example (n_splits=3, min_train=30, horizon=14):
        Fold 0: [0..30] train, [30..44] test
        Fold 1: [0..44] train, [44..58] test  (training grows)
        Fold 2: [0..58] train, [58..72] test

    Sliding Window Example (n_splits=3, min_train=30, horizon=14):
        Fold 0: [0..30] train, [30..44] test
        Fold 1: [14..44] train, [44..58] test  (training slides)
        Fold 2: [28..58] train, [58..72] test
    """
```

**Split Strategies**:

|Strategy|Training Window|Use Case|
|----------|----------------|----------|
|`expanding`|Grows from start with each fold|More training data, detect concept drift|
|`sliding`|Fixed size, slides forward|Consistent training size, recent patterns|

**TimeSeriesSplit Dataclass**:
```python
@dataclass
class TimeSeriesSplit:
    fold_index: int
    train_indices: np.ndarray
    test_indices: np.ndarray
    train_dates: list[date]
    test_dates: list[date]
```

**Key Methods**:
- `split(dates, y)` - Generate train/test splits
- `get_boundaries(dates, y)` - Get split boundaries without full objects
- `validate_no_leakage(dates, y)` - Verify no future data in training

### 2. MetricsCalculator

**File**: `app/features/backtesting/metrics.py`

Comprehensive metrics for forecast evaluation:

```python
class MetricsCalculator:
    """Calculate forecasting accuracy metrics.

    Supported Metrics:
    - MAE: Mean Absolute Error
    - sMAPE: Symmetric Mean Absolute Percentage Error (0-200 scale)
    - WAPE: Weighted Absolute Percentage Error
    - Bias: Forecast Bias (positive = under-forecast)
    - Stability: Coefficient of variation of per-fold metrics
    """
```

**Metrics Formulas**:

|Metric|Formula|Interpretation|
|--------|---------|----------------|
|MAE|`mean(\|actual - predicted\|)`|Average absolute error|
|sMAPE|`100/n * sum(2 * \|A - F\| / (\|A\| + \|F\|))`|Symmetric percentage error (0-200)|
|WAPE|`sum(\|A - F\|) / sum(\|A\|) * 100`|Weighted error for intermittent series|
|Bias|`mean(actual - predicted)`|Positive = under-forecast|
|Stability|`std(metrics) / \|mean(metrics)\| * 100`|Lower = more stable|

**Edge Case Handling**:
- Empty arrays return `NaN`
- Zero denominator handled with warnings
- sMAPE: when both actual and forecast are 0, contributes 0 (perfect forecast)

### 3. Configuration Schemas

**File**: `app/features/backtesting/schemas.py`

Pydantic v2 schemas for backtest configuration:

|Schema|Purpose|
|--------|---------|
|`SplitConfig`|Strategy, n_splits, min_train_size, gap, horizon|
|`BacktestConfig`|Complete config with model_config and options|
|`SplitBoundary`|Fold boundary dates and sizes|
|`FoldResult`|Per-fold actuals, predictions, metrics|
|`ModelBacktestResult`|All folds + aggregated metrics|
|`BacktestRequest`|API request schema|
|`BacktestResponse`|API response with all results|

**SplitConfig Example**:
```python
SplitConfig(
    strategy="expanding",  # or "sliding"
    n_splits=5,           # 2-20 folds
    min_train_size=30,    # Minimum training samples
    gap=0,                # Gap between train end and test start
    horizon=14,           # Forecast horizon per fold
)
```

**Gap Parameter**:
- Simulates operational data latency
- `gap=1` means 1 day between train_end and test_start
- Valid range: 0-30 days
- Validation: `horizon > gap` (must be meaningful test period)

### 4. BacktestingService

**File**: `app/features/backtesting/service.py`

Core service for running backtests:

```python
class BacktestingService:
    """Service for running time-series backtests."""

    async def run_backtest(
        self,
        db: AsyncSession,
        store_id: int,
        product_id: int,
        start_date: date,
        end_date: date,
        config: BacktestConfig,
    ) -> BacktestResponse:
        """Run backtest for a single series."""
```

**Backtest Flow**:
1. Fetch data from `sales_daily` table
2. Validate sufficient data for requested splits
3. Generate splits using TimeSeriesSplitter
4. For each fold:
   - Instantiate model via `model_factory()`
   - Fit on training data
   - Predict for test period
   - Calculate metrics
5. Aggregate metrics across folds
6. Run baseline comparisons (naive, seasonal_naive)
7. Generate comparison summary with improvement percentages

### 5. API Endpoint

**File**: `app/features/backtesting/routes.py`

|Endpoint|Method|Description|
|----------|--------|-------------|
|`/backtesting/run`|POST|Execute backtest for a series|

**Request Example**:
```json
{
  "store_id": 1,
  "product_id": 101,
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "config": {
    "schema_version": "1.0",
    "split_config": {
      "strategy": "expanding",
      "n_splits": 5,
      "min_train_size": 30,
      "gap": 0,
      "horizon": 14
    },
    "model_config_main": {
      "model_type": "seasonal_naive",
      "season_length": 7
    },
    "include_baselines": true,
    "store_fold_details": true
  }
}
```

**Response Structure**:
```json
{
  "backtest_id": "abc123def456",
  "store_id": 1,
  "product_id": 101,
  "config_hash": "a1b2c3d4e5f6g7h8",
  "split_config": { ... },
  "main_model_results": {
    "model_type": "seasonal_naive",
    "config_hash": "x1y2z3...",
    "fold_results": [ ... ],
    "aggregated_metrics": {
      "mae": 3.45,
      "smape": 12.34,
      "wape": 8.76,
      "bias": -0.23
    },
    "metric_std": {
      "mae": 0.45,
      "smape": 1.23
    }
  },
  "baseline_results": [ ... ],
  "comparison_summary": {
    "vs_naive": {
      "mae_improvement_pct": 15.2,
      "smape_improvement_pct": 8.7
    },
    "vs_seasonal_naive": {
      "mae_improvement_pct": 3.1,
      "smape_improvement_pct": 2.4
    }
  },
  "duration_ms": 245.67,
  "leakage_check_passed": true
}
```

### 6. Test Suite

**Directory**: `app/features/backtesting/tests/`

|File|Tests|Coverage|
|------|-------|----------|
|`test_schemas.py`|18|Schema validation, frozen models, config hash|
|`test_splitter.py`|32|Expanding/sliding strategies, gap, leakage validation|
|`test_metrics.py`|24|All metrics, edge cases, aggregation|
|`test_service.py`|25|Service logic, mocked DB|
|`test_routes_integration.py`|8|Route integration with real DB|
|`test_service_integration.py`|8|Service integration with real DB|

**Total**: 115 tests (99 unit + 16 integration)

**Test Data Strategy**:
- Use 120 days of sequential sales data (quantity = day number 1-120)
- Sequential values make leakage mathematically detectable
- Integration tests require PostgreSQL via `docker-compose up -d`

### 7. Example Scripts

**Directory**: `examples/backtest/`

|File|Description|
|------|-------------|
|`run_backtest.py`|Full backtest API call example|
|`inspect_splits.py`|Visualize split boundaries|
|`metrics_demo.py`|Metrics calculation examples|

---

## Configuration

**File**: `app/core/config.py`

New settings added:

```python
# Backtesting
backtest_max_splits: int = 20
backtest_default_min_train_size: int = 30
backtest_max_gap: int = 30
backtest_results_dir: str = "./artifacts/backtests"
```

|Setting|Default|Description|
|---------|---------|-------------|
|`backtest_max_splits`|20|Maximum allowed CV folds|
|`backtest_default_min_train_size`|30|Default minimum training observations|
|`backtest_max_gap`|30|Maximum allowed gap in days|
|`backtest_results_dir`|`./artifacts/backtests`|Directory for saved results|

---

## Directory Structure

```text
app/features/backtesting/
├── __init__.py          # Module exports
├── schemas.py           # Pydantic configuration schemas
├── splitter.py          # TimeSeriesSplitter
├── metrics.py           # MetricsCalculator
├── service.py           # BacktestingService
├── routes.py            # FastAPI endpoints
└── tests/
    ├── __init__.py
    ├── conftest.py              # Test fixtures
    ├── test_schemas.py          # Schema validation tests
    ├── test_splitter.py         # Splitter unit tests
    ├── test_metrics.py          # Metrics unit tests
    ├── test_service.py          # Service unit tests
    ├── test_routes_integration.py   # Route integration tests
    └── test_service_integration.py  # Service integration tests

examples/backtest/
├── run_backtest.py      # Full backtest example
├── inspect_splits.py    # Split visualization
└── metrics_demo.py      # Metrics demo
```

---

## Validation Results

```bash
$ uv run ruff check app/features/backtesting/
All checks passed!

$ uv run mypy app/features/backtesting/
Success: no issues found in 12 source files

$ uv run pyright app/features/backtesting/
0 errors, 0 warnings, 0 informations

$ uv run pytest app/features/backtesting/tests/ -v
115 passed in 2.34s

$ uv run pytest app/features/backtesting/tests/ -v -m integration
16 passed in 4.56s
```

---

## Logging Events

|Event|Description|
|-------|-------------|
|`backtesting.request_received`|Backtest request received|
|`backtesting.request_completed`|Backtest completed successfully|
|`backtesting.request_failed`|Backtest failed|
|`backtesting.fold_started`|CV fold started|
|`backtesting.fold_completed`|CV fold completed|
|`backtesting.leakage_check_passed`|Leakage validation passed|
|`backtesting.leakage_check_failed`|Leakage validation failed|

---

## Leakage Prevention

**Built-in Checks**:
1. `TimeSeriesSplitter.validate_no_leakage()` verifies:
   - `train_end < test_start` for all folds
   - Gap is respected
   - No overlap between train and test indices

2. Response includes `leakage_check_passed: bool`

**Test Strategy**:
- Sequential values (1, 2, 3...) so leakage is detectable
- Assert feature at row i never uses data from rows > i
- Test gap enforcement across folds

---

## Next Phase Preparation

Phase 6 (Model Registry) will use the backtesting module to:
1. Store backtest configuration and results per run
2. Track model performance over time
3. Compare runs with different configurations
4. Maintain lineage from data → features → model → backtest

**Integration Points**:
- `BacktestConfig.config_hash()` for registry deduplication
- `ModelBacktestResult.aggregated_metrics` for run comparison
- `FoldResult` for detailed audit trail
