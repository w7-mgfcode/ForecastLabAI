# Phase 3: Feature Engineering

**Date Completed**: 2026-01-31
**PRP**: [PRP-4-feature-engineering.md](../../PRPs/PRP-4-feature-engineering.md)
**Release**: PR #25

---

## Executive Summary

Phase 3 implements the Feature Engineering Layer for ForecastLabAI with CRITICAL leakage prevention patterns. The module provides time-safe feature computation for retail demand forecasting, ensuring that features computed at any cutoff date only use data available at that point in time.

**Key Achievement**: Zero future data leakage through architectural constraints enforced at the service layer.

---

## Deliverables

### 1. Feature Configuration Schemas

**File**: `app/features/featuresets/schemas.py`

Pydantic v2 schemas with frozen configs for reproducibility:

| Schema | Purpose |
|--------|---------|
| `LagConfig` | Lag feature configuration (lags, target_column, fill_value) |
| `RollingConfig` | Rolling window configuration (windows, aggregations, min_periods) |
| `CalendarConfig` | Calendar feature configuration (day_of_week, month, cyclical encoding) |
| `ExogenousConfig` | Exogenous feature configuration (price_lags, stockout flags) |
| `ImputationConfig` | Imputation strategies (zero, ffill, bfill, mean, drop) |
| `FeatureSetConfig` | Complete feature configuration with config_hash() |
| `ComputeFeaturesRequest` | API request schema with validation |
| `ComputeFeaturesResponse` | API response with features and metadata |

**Key Features**:
- Frozen models (`frozen=True`) for immutability
- Schema versioning for registry storage
- Deterministic `config_hash()` for deduplication
- Validation: positive lags, non-empty configs, valid aggregations

### 2. FeatureEngineeringService

**File**: `app/features/featuresets/service.py`

Core service with CRITICAL leakage prevention:

```python
class FeatureEngineeringService:
    """Time-safe feature engineering service.

    CRITICAL: All feature computation respects cutoff_date to prevent leakage.
    """

    def compute_features(self, df, cutoff_date=None) -> FeatureComputationResult:
        # 1. Filter to cutoff BEFORE any computation
        # 2. Sort by entity + date
        # 3. Compute features with group isolation
```

**Leakage Prevention Patterns**:

| Pattern | Implementation | Why |
|---------|---------------|-----|
| Lag features | `shift(lag)` with positive lag only | Ensures only past data accessed |
| Rolling features | `shift(1)` BEFORE `.rolling()` | Excludes current observation from window |
| Group isolation | `groupby(entity_cols, observed=True)` | Prevents cross-series contamination |
| Cutoff enforcement | Filter data before feature computation | No future data in pipeline |

### 3. API Endpoints

**File**: `app/features/featuresets/routes.py`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/featuresets/compute` | POST | Compute features for a single series |
| `/featuresets/preview` | POST | Preview features with limited sample rows |

**Response Schema**:
```json
{
  "rows": [
    {
      "date": "2024-01-31",
      "store_id": 1,
      "product_id": 1,
      "features": {
        "lag_1": 10.0,
        "lag_7": 8.0,
        "rolling_mean_7": 9.5,
        "dow_sin": 0.433,
        "dow_cos": 0.901
      }
    }
  ],
  "feature_columns": ["lag_1", "lag_7", "rolling_mean_7", "dow_sin", "dow_cos"],
  "config_hash": "a1b2c3d4e5f6g7h8",
  "cutoff_date": "2024-01-31",
  "row_count": 365,
  "null_counts": {"lag_1": 1, "lag_7": 7},
  "duration_ms": 45.23
}
```

### 4. Test Suite

**Directory**: `app/features/featuresets/tests/`

| File | Tests | Coverage |
|------|-------|----------|
| `test_schemas.py` | 16 | Schema validation, config hash, frozen models |
| `test_service.py` | 19 | Lag, rolling, calendar, imputation, cutoff |
| `test_leakage.py` | 10 | CRITICAL leakage prevention tests |
| `conftest.py` | - | Test fixtures with sequential values for leakage detection |

**Total**: 55 tests

**Leakage Test Strategy**:
- Use sequential values (1, 2, 3...) so leakage is mathematically detectable
- Assert feature at row i never uses data from rows > i
- Test group isolation with multi-series fixtures

### 5. Example Script

**File**: `examples/compute_features_demo.py`

Runnable demo showing:
- Feature configuration
- API calls to /compute and /preview
- Response handling

---

## Configuration

**File**: `app/core/config.py`

New settings added:

```python
# Feature Engineering
feature_max_lookback_days: int = 1095  # 3 years
feature_max_lag: int = 365
feature_max_window: int = 90
```

---

## Feature Types

### Lag Features

Past values at specified lag periods.

```python
LagConfig(
    lags=(1, 7, 14, 28),  # Days to look back
    target_column="quantity",
    fill_value=None,  # Optional: fill NaN with this value
)
```

**Output columns**: `lag_1`, `lag_7`, `lag_14`, `lag_28`

### Rolling Features

Rolling statistics over configurable windows.

```python
RollingConfig(
    windows=(7, 14, 28),
    aggregations=("mean", "std", "min", "max"),
    min_periods=7,
)
```

**Output columns**: `rolling_mean_7`, `rolling_std_7`, `rolling_min_7`, ...

**CRITICAL**: Uses `shift(1)` before rolling to exclude current observation.

### Calendar Features

Date-derived features with optional cyclical encoding.

```python
CalendarConfig(
    include_day_of_week=True,
    include_month=True,
    include_quarter=True,
    include_is_weekend=True,
    use_cyclical_encoding=True,  # sin/cos encoding
)
```

**Output columns**:
- Cyclical: `dow_sin`, `dow_cos`, `month_sin`, `month_cos`
- Non-cyclical: `day_of_week`, `month`, `quarter`, `is_weekend`

### Imputation

```python
ImputationConfig(
    strategies={
        "quantity": "zero",      # Zero-fill for sales
        "unit_price": "ffill",   # Forward-fill for prices
    }
)
```

**Strategies**: `zero`, `ffill`, `bfill`, `mean`, `drop`

---

## Phase 2 Features (Retail-Depth)

Phase 2 (PRP-3.1, landed in PRs covering INITIALs 1–5) extends the feature
matrix with three retail-depth families derived from the seeder's Phase 2
emission. All three families are **opt-in** (default `None`) and **additive** —
a `/featuresets/compute` call without any Phase 2 sub-config returns a response
byte-identical in `config_hash` to the pre-Phase-2 baseline (regression-guarded
by both `test_schemas.py::test_config_hash_unchanged_when_phase2_omitted` at
the model layer and `test_phase2_integration.py::TestPhase2EndToEnd::test_additive_contract_snapshot`
at the HTTP boundary).

### Lifecycle features

Continuous date-deltas derived from `product.launch_date` and
`product.discontinue_date` (both nullable on Phase 2 products). See
PRP-3.1B for the compute method; the categorical `lifecycle_stage` was
explicitly **dropped** in favor of continuous deltas (decision log §1) —
LightGBM splits discover stage boundaries from the integer delta naturally.

```python
from app.features.featuresets.schemas import LifecycleConfig

LifecycleConfig(
    include_days_since_launch=True,        # default True
    include_days_since_discontinue=True,   # default True
    lag_days=1,                             # 1..30
)
```

| Column | Type | Time-safety |
|--------|------|-------------|
| `days_since_launch_lag{N}` | int (NaN if `launch_date` is NULL) | `shift(N)` per `(store_id, product_id)` |
| `days_since_discontinue_lag{N}` | int (NaN if `discontinue_date` is NULL; signed pre-/post-retire) | `shift(N)` per `(store_id, product_id)` |

End-to-end at the HTTP boundary, `FeatureDataLoader.load_product_attrs`
joins `product.launch_date` / `product.discontinue_date` onto the sales
frame when `lifecycle_config` is set (#116). The attributes are timeless
(no cutoff filter), so the merge is constant per product and
`_compute_lifecycle_features` derives the per-row delta + `shift(N)`
downstream.

### Replenishment features

Inbound-stock cadence from the `replenishment_event` table (separate from
`sales_daily`). See PRP-3.1C for the compute method + SQL helper. The
loader (`FeatureDataLoader.load_replenishment_events`) applies an SQL-side
`date <= cutoff_date` predicate to enforce time-safety before pandas sees
the rows.

```python
from app.features.featuresets.schemas import ReplenishmentConfig

ReplenishmentConfig(
    include_days_since_last=True,   # default True
    include_count_window=True,      # default True
    lag_days=1,                      # 1..30
    count_window_days=14,            # 7..60
)
```

| Column | Type | Time-safety |
|--------|------|-------------|
| `days_since_last_replenishment_lag{N}` | float64 (NaN before first event) | `merge_asof` backward + `shift(N)` per series |
| `replenishment_count_w{W}_lag{N}` | int64 | `shift(1).rolling(W).sum()` per series |

### Promotion features (generic — any `promotion.kind`)

Generalized from the original markdown-only design (decision log §3) — one
JOIN to the `promotion` table, with one-hot per kind on the configured
subset. Default `kinds_to_track=("markdown",)` preserves the original PRD
intent; callers can opt into `pct_off | bogo | bundle` by passing additional
kinds. See PRP-3.1D for the compute method.

```python
from app.features.featuresets.schemas import PromotionConfig

PromotionConfig(
    kinds_to_track=("markdown",),   # subset of pct_off|bogo|bundle|markdown
    include_active=True,             # default True
    include_intensity=True,          # default True
    lag_days=1,                       # 1..30
)
```

| Column | Type | Time-safety |
|--------|------|-------------|
| `promo_<kind>_active_lag{N}` | Int64 (nullable 0/1) | `shift(N)` per `(store_id, product_id)` of daily active indicator |
| `promo_<kind>_intensity_lag{N}` | float64 (NaN if `discount_pct` NULL) | `shift(N)` of `promotion.discount_pct` (Numeric(5,4)) |

### Time-safety guarantee (cross-cutting)

All Phase 2 features obey the same invariants as Phase 1
(`app/features/featuresets/tests/test_leakage.py`):

- Every numeric column is `shift(N)` (positive `N`) per `(store_id, product_id)` group.
- Every rolling/count column is `shift(1).rolling(W)`, never `rolling(W).shift(1)`.
- Auxiliary tables (`replenishment_event`, `promotion`) are SQL-filtered to
  `event_date <= cutoff_date` / `start_date <= cutoff_date` BEFORE pandas
  sees them.
- A dedicated `TestPhase2CrossConfigLeakage` class composes all three
  families with `lag_config` and asserts no future-data references at the
  union of feature rows.

### End-to-end integration

`app/features/featuresets/tests/test_phase2_integration.py` (marked
`@pytest.mark.integration`) exercises `POST /featuresets/compute` against
a real Postgres with all three Phase 2 sub-configs set, and pins the
additive-contract snapshot at the HTTP boundary. Run after
`docker compose up -d && uv run alembic upgrade head`.

---

## Dependencies

Added to `pyproject.toml`:

```toml
dependencies = [
    # ... existing
    "pandas>=2.0.0",
    "numpy>=1.24.0",
]

[dependency-groups]
dev = [
    # ... existing
    "pandas-stubs>=2.0.0",
]
```

---

## Directory Structure

```
app/features/featuresets/
├── __init__.py          # Module exports
├── schemas.py           # Pydantic configuration schemas
├── service.py           # FeatureEngineeringService
├── routes.py            # FastAPI endpoints
└── tests/
    ├── __init__.py
    ├── conftest.py      # Test fixtures
    ├── test_schemas.py  # Schema validation tests
    ├── test_service.py  # Service unit tests
    └── test_leakage.py  # CRITICAL leakage tests

examples/
└── compute_features_demo.py  # Demo script
```

---

## Validation Results

```
$ uv run ruff check app/features/featuresets/
All checks passed!

$ uv run mypy app/features/featuresets/
Success: no issues found in 9 source files

$ uv run pyright app/features/featuresets/
0 errors, 0 warnings, 0 informations

$ uv run pytest app/features/featuresets/tests/ -v
55 passed in 0.45s
```

---

## Next Phase Preparation

Phase 4 (Forecasting) will use the feature engineering module to:
1. Generate features for training data using cutoff-based computation
2. Store feature configuration in model registry
3. Ensure reproducible feature computation during prediction

**Integration Points**:
- `FeatureSetConfig.config_hash()` for registry storage
- `compute_features_for_series()` for model training pipelines
- Schema versioning for backward compatibility
