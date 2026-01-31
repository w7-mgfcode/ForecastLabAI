# PRP-4: Feature Engineering — Time-Safe Feature Computation

## Goal

Implement a time-safe feature engineering module for the ForecastLabAI forecasting pipeline. The module provides configurable feature computation (lags, rolling windows, calendar features, exogenous signals) with **guaranteed no future data leakage** through explicit cutoff enforcement.

**End State:** A production-ready `featuresets` vertical slice with:
- `FeatureSetConfig` — Pydantic-based configuration schema with versioning
- `FeatureEngineeringService` — Core service computing features with cutoff enforcement
- `POST /featuresets/compute` — API endpoint to compute features for a series
- `POST /featuresets/preview` — Preview feature output for debugging/exploration
- Time-safety enforced at every level (lags, rolling, calendar)
- Comprehensive tests including **leakage-focused validation tests**
- All validation gates passing (ruff, mypy, pyright, pytest)

---

## Why

- **Foundation for ForecastOps**: INITIAL-5 (Forecasting) and INITIAL-6 (Backtesting) require computed features as input
- **Prevent Data Leakage**: Time-series models fail silently when features leak future data; explicit cutoff enforcement prevents this
- **Reproducibility**: Feature configs are versioned and hashable for registry storage (INITIAL-7)
- **Configurability**: Different products/stores may need different feature sets without code changes
- **Agent Tooling Ready**: Exposes feature inspection for PydanticAI agents (INITIAL-9)

---

## What

### Success Criteria

- [ ] `FeatureSetConfig` schema with `lag_config`, `rolling_config`, `calendar_config`, `exogenous_config`, `imputation_config`
- [ ] All configs have `schema_version` field and deterministic `config_hash()` method
- [ ] `FeatureEngineeringService.compute_features(df, cutoff_date)` returns features respecting cutoff
- [ ] Lag features use `shift(lag)` — only past data
- [ ] Rolling features use `shift(1)` before rolling — excludes current observation
- [ ] Calendar features derived from date column (no leakage possible)
- [ ] Exogenous features (price/promo/inventory) lagged appropriately
- [ ] Imputation strategies: zero-fill for sales, forward-fill for prices
- [ ] `POST /featuresets/compute` endpoint accepts config + data window + cutoff
- [ ] `POST /featuresets/preview` endpoint for single-series feature inspection
- [ ] Unit tests for each feature type
- [ ] **Leakage tests** verify no future data used
- [ ] Integration tests with real DB queries
- [ ] Example files: `examples/features/preview_features.py`, `examples/features/config_shape.json`

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ - Critical for implementation
- url: https://www.nixtla.io/blog/automated-time-series-feature-engineering-with-mlforecast
  why: MLForecast patterns for time-safe lag/rolling transforms
  critical: shift(1) before rolling to prevent leakage

- url: https://towardsdatascience.com/avoiding-data-leakage-in-timeseries-101-25ea13fcb15f
  why: Common leakage pitfalls and detection strategies
  critical: Random CV is wrong for time series; always use time-based splits

- url: https://www.sktime.net/en/stable/api_reference/transformations.html
  why: WindowSummarizer patterns if needed
  critical: lag_feature dict syntax for window configurations

- url: https://docs.pydantic.dev/latest/concepts/validators/
  why: Pydantic v2 field validators and model validators
  critical: Use ConfigDict(frozen=True) for immutable configs

- url: https://learn.microsoft.com/en-us/azure/machine-learning/concept-automl-forecasting-calendar-features
  why: Best practices for calendar features in demand forecasting
  critical: Cyclical encoding (sin/cos) for periodic features

- url: https://scikit-learn.org/stable/modules/compose.html
  why: Pipeline composition patterns
  critical: Feature union and column transformer patterns

# Internal codebase files - MUST reference these patterns
- file: app/features/ingest/service.py
  why: Service pattern with Protocol, dataclass results, async DB queries
  pattern: KeyResolverProtocol, UpsertResult dataclass, batch queries

- file: app/features/ingest/schemas.py
  why: Pydantic v2 schema patterns with Field(), validators
  pattern: ConfigDict, field_validator, model_validator

- file: app/features/ingest/routes.py
  why: FastAPI router structure with Depends(get_db)
  pattern: Router tags, response_model, status codes

- file: app/features/ingest/tests/conftest.py
  why: Test fixture patterns with MockKeyResolver
  pattern: Protocol-based mocks, sample data fixtures

- file: app/features/data_platform/models.py
  why: SalesDaily, Calendar, PriceHistory, Promotion, InventorySnapshotDaily models
  pattern: Relationships, grain constraints, Decimal types

- file: app/core/config.py
  why: Pydantic Settings pattern
  pattern: Field() with defaults, ge/le validators

- file: docs/validation/logging-standard.md
  why: Event naming convention
  pattern: featureops.{action}_{state}

- file: CLAUDE.md
  why: Type safety requirements, vertical slice architecture, KISS/YAGNI
  critical: No future leakage, time-based splits only
```

### Current Codebase Tree

```bash
app/
├── __init__.py
├── main.py                     # FastAPI entry, router registration
├── core/
│   ├── config.py               # Pydantic Settings
│   ├── database.py             # AsyncSession, get_db()
│   ├── exceptions.py           # ForecastLabError hierarchy
│   ├── health.py               # Router pattern
│   ├── logging.py              # Structured logging
│   └── middleware.py           # RequestIdMiddleware
├── shared/
│   ├── models.py               # TimestampMixin
│   ├── schemas.py              # ErrorResponse
│   └── utils.py                # Utilities
└── features/
    ├── data_platform/
    │   ├── models.py           # Store, Product, Calendar, SalesDaily, PriceHistory, etc.
    │   ├── schemas.py          # Pydantic schemas
    │   └── tests/
    └── ingest/
        ├── routes.py           # POST /ingest/sales-daily
        ├── schemas.py          # Ingest schemas
        ├── service.py          # KeyResolver, upsert logic
        └── tests/
```

### Desired Codebase Tree (files to be added)

```bash
app/
├── core/
│   └── config.py               # MODIFY: Add feature engineering settings
└── features/
    └── featuresets/            # NEW: Feature engineering vertical slice
        ├── __init__.py         # Module exports
        ├── schemas.py          # FeatureSetConfig, LagConfig, RollingConfig, etc.
        ├── service.py          # FeatureEngineeringService
        ├── routes.py           # POST /featuresets/compute, POST /featuresets/preview
        └── tests/
            ├── __init__.py
            ├── conftest.py     # Feature-specific fixtures, sample time series
            ├── test_schemas.py # Config validation tests
            ├── test_service.py # Service logic tests
            ├── test_leakage.py # CRITICAL: Leakage prevention tests
            └── test_routes.py  # Integration tests

examples/
└── features/
    ├── preview_features.py     # NEW: Feature preview script
    ├── config_shape.json       # NEW: Example config JSON
    └── leakage_tests.py        # NEW: Leakage test templates
```

### Known Gotchas & Library Quirks

```python
# CRITICAL: Lag features must use positive shift values
# ❌ WRONG: df["lag_1"] = df["quantity"].shift(-1)  # LEAKS FUTURE!
# ✅ CORRECT: df["lag_1"] = df["quantity"].shift(1)  # Uses past data

# CRITICAL: Rolling features must exclude current observation
# ❌ WRONG: df["rolling_mean_7"] = df["quantity"].rolling(7).mean()  # Includes current!
# ✅ CORRECT: df["rolling_mean_7"] = df["quantity"].shift(1).rolling(7).mean()  # Excludes current

# CRITICAL: Group-aware operations for multi-series data
# ❌ WRONG: df["lag_1"] = df["quantity"].shift(1)  # Leaks across series!
# ✅ CORRECT: df["lag_1"] = df.groupby(["store_id", "product_id"])["quantity"].shift(1)

# CRITICAL: Cutoff must be explicit parameter, not inferred
# ❌ WRONG: def compute_features(df):  # No cutoff = risk of leakage
# ✅ CORRECT: def compute_features(df, cutoff_date: date):  # Explicit cutoff

# CRITICAL: Decimal for monetary values
# ❌ WRONG: price: float
# ✅ CORRECT: price: Decimal = Field(..., decimal_places=2)

# CRITICAL: Pydantic v2 frozen configs for immutability
# ❌ WRONG: class Config: pass
# ✅ CORRECT: model_config = ConfigDict(frozen=True, extra="forbid")

# CRITICAL: Cyclical encoding for periodic features
# ❌ WRONG: day_of_week as integer 0-6 (ML sees 0 and 6 as far apart)
# ✅ CORRECT: sin/cos encoding preserves cyclical continuity

# CRITICAL: Forward-fill for prices, zero-fill for sales
# - Missing sales = no sales = 0
# - Missing price = price unchanged = forward-fill
# - Missing inventory = last known state = forward-fill

# CRITICAL: Calendar dates must exist in Calendar table
# Features referencing calendar (is_holiday, etc.) require FK lookup
```

---

## Implementation Blueprint

### Data Models and Structure

#### Feature Configuration Schemas (app/features/featuresets/schemas.py)

```python
"""Pydantic schemas for feature engineering configuration."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
import hashlib

from pydantic import BaseModel, Field, ConfigDict, field_validator


class FeatureConfigBase(BaseModel):
    """Base configuration with versioning support."""

    model_config = ConfigDict(
        frozen=True,  # Immutable after creation
        extra="forbid",  # No extra fields allowed
        strict=True,
    )

    schema_version: str = Field(
        ...,
        description="Semantic version of this config schema",
        pattern=r"^\d+\.\d+(\.\d+)?$",
    )

    def config_hash(self) -> str:
        """Generate deterministic hash of configuration."""
        # Exclude timestamps from hash for reproducibility
        config_json = self.model_dump_json()
        return hashlib.sha256(config_json.encode()).hexdigest()[:16]


class LagConfig(FeatureConfigBase):
    """Configuration for lag-based features."""

    schema_version: str = "1.0"
    lags: tuple[int, ...] = Field(
        default=(1, 7, 14, 28),
        description="Lag periods in days",
    )
    target_column: str = Field(default="quantity")
    fill_value: float | None = Field(
        default=None,
        description="Value to fill NaN (None = keep NaN)",
    )

    @field_validator("lags")
    @classmethod
    def validate_lags_positive(cls, v: tuple[int, ...]) -> tuple[int, ...]:
        """Ensure all lags are positive (no future leakage)."""
        if any(lag <= 0 for lag in v):
            raise ValueError("All lags must be positive integers")
        return v


class RollingConfig(FeatureConfigBase):
    """Configuration for rolling window features."""

    schema_version: str = "1.0"
    windows: tuple[int, ...] = Field(
        default=(7, 14, 28),
        description="Window sizes in days",
    )
    aggregations: tuple[Literal["mean", "std", "min", "max", "sum"], ...] = Field(
        default=("mean", "std"),
    )
    target_column: str = Field(default="quantity")
    min_periods: int | None = Field(
        default=None,
        description="Minimum observations required (None = window size)",
    )


class CalendarConfig(FeatureConfigBase):
    """Configuration for calendar features."""

    schema_version: str = "1.0"
    include_day_of_week: bool = True
    include_month: bool = True
    include_quarter: bool = True
    include_year: bool = False
    include_is_weekend: bool = True
    include_is_month_end: bool = True
    include_is_holiday: bool = True
    use_cyclical_encoding: bool = Field(
        default=True,
        description="Use sin/cos encoding for periodic features",
    )


class ExogenousConfig(FeatureConfigBase):
    """Configuration for exogenous variable features."""

    schema_version: str = "1.0"
    # Price features
    include_price: bool = True
    price_lags: tuple[int, ...] = (7, 28)
    include_price_change: bool = True
    # Promotion features
    include_promo: bool = True
    # Inventory features
    include_inventory: bool = False
    include_stockout_flag: bool = True


class ImputationConfig(FeatureConfigBase):
    """Configuration for missing value imputation."""

    schema_version: str = "1.0"
    strategies: dict[str, Literal["zero", "ffill", "bfill", "mean", "drop"]] = Field(
        default_factory=lambda: {
            "quantity": "zero",
            "unit_price": "ffill",
            "total_amount": "zero",
        }
    )


class FeatureSetConfig(FeatureConfigBase):
    """Complete feature engineering configuration."""

    schema_version: str = "1.0"

    # Feature sub-configurations (None = disabled)
    lag_config: LagConfig | None = None
    rolling_config: RollingConfig | None = None
    calendar_config: CalendarConfig | None = None
    exogenous_config: ExogenousConfig | None = None
    imputation_config: ImputationConfig | None = None

    # Data grain
    entity_columns: tuple[str, ...] = ("store_id", "product_id")
    date_column: str = "date"
    target_column: str = "quantity"

    # Metadata
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None

    def get_enabled_features(self) -> list[str]:
        """Return list of enabled feature types."""
        enabled = []
        if self.lag_config:
            enabled.append("lag")
        if self.rolling_config:
            enabled.append("rolling")
        if self.calendar_config:
            enabled.append("calendar")
        if self.exogenous_config:
            enabled.append("exogenous")
        return enabled


# Request/Response schemas for API
class ComputeFeaturesRequest(BaseModel):
    """Request body for POST /featuresets/compute."""

    model_config = ConfigDict(strict=True)

    store_id: int = Field(..., ge=1)
    product_id: int = Field(..., ge=1)
    cutoff_date: date = Field(..., description="Compute features up to this date (inclusive)")
    lookback_days: int = Field(default=365, ge=1, le=1095, description="Days of history to use")
    config: FeatureSetConfig


class FeatureRow(BaseModel):
    """Single row of computed features."""

    date: date
    store_id: int
    product_id: int
    features: dict[str, float | int | None]


class ComputeFeaturesResponse(BaseModel):
    """Response body for POST /featuresets/compute."""

    rows: list[FeatureRow]
    feature_columns: list[str]
    config_hash: str
    cutoff_date: date
    row_count: int
    null_counts: dict[str, int]
    duration_ms: float


class PreviewFeaturesRequest(BaseModel):
    """Request for POST /featuresets/preview."""

    store_id: int = Field(..., ge=1)
    product_id: int = Field(..., ge=1)
    cutoff_date: date
    sample_rows: int = Field(default=10, ge=1, le=100)
    config: FeatureSetConfig
```

#### Settings Extension (app/core/config.py)

```python
# Add to Settings class:
# Feature Engineering configuration
feature_max_lookback_days: int = Field(
    default=1095,  # 3 years
    ge=30,
    le=1825,  # 5 years
    description="Maximum lookback window for feature computation",
)
feature_max_lag: int = Field(
    default=365,
    ge=1,
    le=730,
    description="Maximum allowed lag value",
)
feature_max_window: int = Field(
    default=90,
    ge=1,
    le=365,
    description="Maximum rolling window size",
)
```

### Tasks (Ordered Implementation)

```yaml
Task 1: Create featuresets feature directory structure
  FILES:
    - app/features/featuresets/__init__.py
    - app/features/featuresets/schemas.py
    - app/features/featuresets/service.py
    - app/features/featuresets/routes.py
    - app/features/featuresets/tests/__init__.py
    - app/features/featuresets/tests/conftest.py
  VALIDATION:
    - ls -la app/features/featuresets/

Task 2: Add feature engineering configuration to Settings
  MODIFY: app/core/config.py
  ADD:
    - feature_max_lookback_days: int = 1095
    - feature_max_lag: int = 365
    - feature_max_window: int = 90
  VALIDATION:
    - uv run python -c "from app.core.config import get_settings; s = get_settings(); print(f'max_lag={s.feature_max_lag}')"

Task 3: Implement feature configuration schemas
  FILE: app/features/featuresets/schemas.py
  IMPLEMENT:
    - FeatureConfigBase with config_hash()
    - LagConfig with lag validation (positive only)
    - RollingConfig with window/aggregation options
    - CalendarConfig with cyclical encoding flag
    - ExogenousConfig for price/promo/inventory
    - ImputationConfig with strategy mapping
    - FeatureSetConfig combining all configs
    - ComputeFeaturesRequest/Response for API
  VALIDATION:
    - uv run mypy app/features/featuresets/schemas.py
    - uv run pyright app/features/featuresets/schemas.py

Task 4: Implement FeatureEngineeringService core
  FILE: app/features/featuresets/service.py
  IMPLEMENT:
    - FeatureComputationResult dataclass
    - FeatureEngineeringService class
    - compute_features(df, cutoff_date) main method
    - _compute_lag_features() with groupby + shift
    - _compute_rolling_features() with shift(1) + rolling
    - _compute_calendar_features() with cyclical encoding
    - _apply_imputation() with strategy dispatch
  PSEUDOCODE: See "Service Implementation Pseudocode" section below
  VALIDATION:
    - uv run mypy app/features/featuresets/service.py
    - uv run pyright app/features/featuresets/service.py

Task 5: Implement data loading service
  FILE: app/features/featuresets/service.py (append)
  IMPLEMENT:
    - FeatureDataLoader class
    - load_sales_data(db, store_id, product_id, start_date, end_date)
    - load_calendar_data(db, start_date, end_date)
    - load_price_data(db, store_id, product_id, start_date, end_date)
    - Efficient async queries with proper date filtering
  VALIDATION:
    - uv run mypy app/features/featuresets/service.py

Task 6: Implement exogenous feature computation
  FILE: app/features/featuresets/service.py (append)
  IMPLEMENT:
    - _compute_exogenous_features() method
    - Price lag features
    - Price change percentage
    - Promotion active flag
    - Stockout flag from inventory
  VALIDATION:
    - uv run mypy app/features/featuresets/service.py

Task 7: Implement featuresets routes
  FILE: app/features/featuresets/routes.py
  IMPLEMENT:
    - Router with tag "featuresets"
    - POST /featuresets/compute endpoint
    - POST /featuresets/preview endpoint
    - Error handling with ForecastLabError
  VALIDATION:
    - uv run mypy app/features/featuresets/routes.py
    - uv run pyright app/features/featuresets/routes.py

Task 8: Register featuresets router in main.py
  MODIFY: app/main.py
  ADD:
    - from app.features.featuresets.routes import router as featuresets_router
    - app.include_router(featuresets_router)
  VALIDATION:
    - uv run python -c "from app.main import app; print([r.path for r in app.routes])"

Task 9: Create test fixtures with sample time series
  FILE: app/features/featuresets/tests/conftest.py
  IMPLEMENT:
    - sample_time_series fixture (30 days of data)
    - sample_feature_config fixture
    - sample_lag_config, sample_rolling_config fixtures
    - mock_db_session fixture for unit tests
  VALIDATION:
    - uv run pytest app/features/featuresets/tests/ --collect-only

Task 10: Create unit tests for schemas
  FILE: app/features/featuresets/tests/test_schemas.py
  IMPLEMENT:
    - Test LagConfig rejects negative lags
    - Test FeatureSetConfig config_hash() determinism
    - Test ComputeFeaturesRequest validation
    - Test frozen config immutability
  VALIDATION:
    - uv run pytest app/features/featuresets/tests/test_schemas.py -v

Task 11: Create unit tests for service
  FILE: app/features/featuresets/tests/test_service.py
  IMPLEMENT:
    - Test lag feature computation
    - Test rolling feature computation
    - Test calendar feature computation
    - Test imputation strategies
    - Test compute_features() integration
  VALIDATION:
    - uv run pytest app/features/featuresets/tests/test_service.py -v

Task 12: Create CRITICAL leakage prevention tests
  FILE: app/features/featuresets/tests/test_leakage.py
  IMPLEMENT:
    - test_lag_features_no_future_data()
    - test_rolling_features_exclude_current()
    - test_cutoff_strictly_enforced()
    - test_group_isolation_no_cross_series_leakage()
  PATTERN:
    - Use sequential values (1,2,3...) so leakage is mathematically detectable
    - Assert feature at row i never uses data from rows > i
  VALIDATION:
    - uv run pytest app/features/featuresets/tests/test_leakage.py -v

Task 13: Create integration tests for routes
  FILE: app/features/featuresets/tests/test_routes.py
  IMPLEMENT:
    - Test POST /featuresets/compute with valid payload
    - Test POST /featuresets/preview returns sample rows
    - Test error handling for missing data
    - Test config_hash consistency
  REQUIRES:
    - Running PostgreSQL with seeded data
  VALIDATION:
    - uv run pytest app/features/featuresets/tests/test_routes.py -v -m integration

Task 14: Create example files
  FILES:
    - examples/features/preview_features.py
    - examples/features/config_shape.json
    - examples/features/leakage_tests.py
  CONTENT: See "Example Files" section below
  VALIDATION:
    - ls -la examples/features/

Task 15: Final validation - Run all quality gates
  COMMANDS:
    - uv run ruff check app/features/featuresets/ --fix
    - uv run ruff format app/features/featuresets/
    - uv run mypy app/features/featuresets/
    - uv run pyright app/features/featuresets/
    - uv run pytest app/features/featuresets/tests/ -v
    - uv run pytest app/features/featuresets/tests/test_leakage.py -v  # CRITICAL
```

### Service Implementation Pseudocode

```python
"""Feature engineering service - CRITICAL implementation details."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.features.data_platform.models import SalesDaily, Calendar, PriceHistory
from app.features.featuresets.schemas import FeatureSetConfig

logger = get_logger(__name__)


@dataclass
class FeatureComputationResult:
    """Result of feature computation."""

    df: pd.DataFrame
    feature_columns: list[str]
    config_hash: str
    stats: dict[str, Any] = field(default_factory=dict)


class FeatureEngineeringService:
    """
    Time-safe feature engineering service.

    CRITICAL: All feature computation respects cutoff_date to prevent leakage.
    """

    def __init__(self, config: FeatureSetConfig) -> None:
        self.config = config
        self.entity_cols = list(config.entity_columns)
        self.date_col = config.date_column
        self.target_col = config.target_column

    def compute_features(
        self,
        df: pd.DataFrame,
        cutoff_date: date | None = None,
    ) -> FeatureComputationResult:
        """
        Compute all configured features.

        Args:
            df: Input dataframe with entity columns, date, and target
            cutoff_date: Maximum date to include (CRITICAL for time-safety)

        Returns:
            FeatureComputationResult with computed features
        """
        logger.info(
            "featureops.compute_started",
            config_hash=self.config.config_hash(),
            row_count=len(df),
            cutoff_date=str(cutoff_date) if cutoff_date else None,
        )

        result = df.copy()

        # CRITICAL: Sort by entity + date for correct lag/rolling computation
        result = result.sort_values(self.entity_cols + [self.date_col])

        # CRITICAL: Filter to cutoff BEFORE any feature computation
        if cutoff_date:
            result = result[result[self.date_col] <= cutoff_date]

        feature_columns: list[str] = []

        # 1. Apply imputation FIRST (fills gaps before lag/rolling)
        if self.config.imputation_config:
            result = self._apply_imputation(result)

        # 2. Lag features
        if self.config.lag_config:
            result, cols = self._compute_lag_features(result)
            feature_columns.extend(cols)

        # 3. Rolling features (uses shifted data)
        if self.config.rolling_config:
            result, cols = self._compute_rolling_features(result)
            feature_columns.extend(cols)

        # 4. Calendar features (no leakage risk)
        if self.config.calendar_config:
            result, cols = self._compute_calendar_features(result)
            feature_columns.extend(cols)

        # 5. Exogenous features
        if self.config.exogenous_config:
            result, cols = self._compute_exogenous_features(result)
            feature_columns.extend(cols)

        stats = {
            "input_rows": len(df),
            "output_rows": len(result),
            "feature_count": len(feature_columns),
            "null_counts": result[feature_columns].isnull().sum().to_dict(),
        }

        logger.info(
            "featureops.compute_completed",
            config_hash=self.config.config_hash(),
            feature_count=len(feature_columns),
        )

        return FeatureComputationResult(
            df=result,
            feature_columns=feature_columns,
            config_hash=self.config.config_hash(),
            stats=stats,
        )

    def _compute_lag_features(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[str]]:
        """
        Compute lag features with proper grouping.

        CRITICAL: shift(lag) uses PAST data only (positive lag = look back)
        """
        config = self.config.lag_config
        assert config is not None

        result = df.copy()
        columns: list[str] = []

        for lag in config.lags:
            col_name = f"lag_{lag}"
            # CRITICAL: Group by entity to prevent cross-series leakage
            result[col_name] = (
                df.groupby(self.entity_cols)[config.target_column]
                .shift(lag)  # Positive shift = look back in time
            )
            if config.fill_value is not None:
                result[col_name] = result[col_name].fillna(config.fill_value)
            columns.append(col_name)

        return result, columns

    def _compute_rolling_features(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[str]]:
        """
        Compute rolling window features.

        CRITICAL: shift(1) BEFORE rolling to exclude current observation.
        Without shift(1), rolling(7).mean() at row i uses data from [i-6, i] inclusive.
        With shift(1), it uses data from [i-7, i-1] — truly past data only.
        """
        config = self.config.rolling_config
        assert config is not None

        result = df.copy()
        columns: list[str] = []

        for window in config.windows:
            min_per = config.min_periods if config.min_periods else window

            for agg in config.aggregations:
                col_name = f"rolling_{agg}_{window}"

                # CRITICAL: shift(1) prevents using current row in rolling calculation
                result[col_name] = (
                    df.groupby(self.entity_cols)[config.target_column]
                    .transform(
                        lambda x: x.shift(1)
                        .rolling(window=window, min_periods=min_per)
                        .agg(agg)
                    )
                )
                columns.append(col_name)

        return result, columns

    def _compute_calendar_features(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[str]]:
        """
        Compute calendar-based features.

        Calendar features are derived from the date column itself,
        so there's no risk of future leakage.
        """
        config = self.config.calendar_config
        assert config is not None

        result = df.copy()
        columns: list[str] = []
        dates = pd.to_datetime(result[self.date_col])

        if config.include_day_of_week:
            dow = dates.dt.dayofweek  # 0=Monday, 6=Sunday
            if config.use_cyclical_encoding:
                result["dow_sin"] = np.sin(2 * np.pi * dow / 7)
                result["dow_cos"] = np.cos(2 * np.pi * dow / 7)
                columns.extend(["dow_sin", "dow_cos"])
            else:
                result["day_of_week"] = dow
                columns.append("day_of_week")

        if config.include_month:
            month = dates.dt.month
            if config.use_cyclical_encoding:
                result["month_sin"] = np.sin(2 * np.pi * month / 12)
                result["month_cos"] = np.cos(2 * np.pi * month / 12)
                columns.extend(["month_sin", "month_cos"])
            else:
                result["month"] = month
                columns.append("month")

        if config.include_quarter:
            result["quarter"] = dates.dt.quarter
            columns.append("quarter")

        if config.include_is_weekend:
            result["is_weekend"] = dates.dt.dayofweek.isin([5, 6]).astype(int)
            columns.append("is_weekend")

        if config.include_is_month_end:
            result["is_month_end"] = dates.dt.is_month_end.astype(int)
            columns.append("is_month_end")

        # is_holiday requires calendar table lookup (handled separately)

        return result, columns

    def _apply_imputation(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply configured imputation strategies."""
        config = self.config.imputation_config
        assert config is not None

        result = df.copy()

        for col, strategy in config.strategies.items():
            if col not in result.columns:
                continue

            if strategy == "zero":
                result[col] = result[col].fillna(0)
            elif strategy == "ffill":
                # CRITICAL: Group-aware forward fill
                result[col] = result.groupby(self.entity_cols)[col].ffill()
            elif strategy == "bfill":
                result[col] = result.groupby(self.entity_cols)[col].bfill()
            elif strategy == "mean":
                result[col] = result.groupby(self.entity_cols)[col].transform(
                    lambda x: x.fillna(x.mean())
                )
            elif strategy == "drop":
                result = result.dropna(subset=[col])

        return result

    def _compute_exogenous_features(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[str]]:
        """Compute exogenous features (price, promo, inventory)."""
        config = self.config.exogenous_config
        assert config is not None

        result = df.copy()
        columns: list[str] = []

        # Price features (if price column exists)
        if config.include_price and "unit_price" in df.columns:
            for lag in config.price_lags:
                col_name = f"price_lag_{lag}"
                result[col_name] = (
                    df.groupby(self.entity_cols)["unit_price"]
                    .shift(lag)
                )
                columns.append(col_name)

            if config.include_price_change:
                # Price change vs 7 days ago
                result["price_pct_change_7d"] = (
                    df.groupby(self.entity_cols)["unit_price"]
                    .pct_change(periods=7)
                )
                columns.append("price_pct_change_7d")

        return result, columns
```

### Integration Points

```yaml
DATABASE:
  - No new migrations required (uses existing SalesDaily, Calendar, PriceHistory)
  - Queries use existing grain constraint for efficient lookups
  - Calendar table provides is_holiday flag

CONFIG:
  - MODIFY: app/core/config.py
  - ADD: feature_max_lookback_days, feature_max_lag, feature_max_window

ROUTES:
  - MODIFY: app/main.py
  - ADD: app.include_router(featuresets_router)
  - ENDPOINTS:
    - POST /featuresets/compute
    - POST /featuresets/preview

DEPENDENCIES:
  - pandas (add to pyproject.toml if not present)
  - numpy (add to pyproject.toml if not present)
  - SalesDaily table must have data for the requested series/date range
  - Calendar table should have entries for dates in range

REGISTRY INTEGRATION (Future - INITIAL-7):
  - FeatureSetConfig.config_hash() enables registry lookups
  - FeatureSetConfig.model_dump_json() for registry storage
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run FIRST - fix any errors before proceeding
uv run ruff check app/features/featuresets/ --fix
uv run ruff format app/features/featuresets/

# Expected: No errors
```

### Level 2: Type Checking

```bash
# Run SECOND - type safety is non-negotiable
uv run mypy app/features/featuresets/
uv run pyright app/features/featuresets/

# Expected: 0 errors
```

### Level 3: Unit Tests

```bash
# Run THIRD - verify schemas and service logic
uv run pytest app/features/featuresets/tests/test_schemas.py -v
uv run pytest app/features/featuresets/tests/test_service.py -v

# Expected: All tests pass
```

### Level 4: CRITICAL Leakage Tests

```bash
# Run FOURTH - these tests are NON-NEGOTIABLE
uv run pytest app/features/featuresets/tests/test_leakage.py -v

# Expected: ALL leakage tests pass
# If any fail: STOP and fix immediately - leakage is a critical bug
```

### Level 5: Integration Tests

```bash
# Run FIFTH - verify API and database behavior
docker-compose up -d
sleep 5
uv run alembic upgrade head
uv run python examples/seed_demo_data.py

uv run pytest app/features/featuresets/tests/test_routes.py -v -m integration

docker-compose down

# Expected: All tests pass
```

### Level 6: Manual API Test

```bash
# Start API server
uv run uvicorn app.main:app --reload --port 8123

# Test compute endpoint
curl -X POST http://localhost:8123/featuresets/compute \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": 1,
    "product_id": 1,
    "cutoff_date": "2024-01-31",
    "lookback_days": 60,
    "config": {
      "schema_version": "1.0",
      "name": "test_config",
      "lag_config": {"schema_version": "1.0", "lags": [1, 7, 14]},
      "rolling_config": {"schema_version": "1.0", "windows": [7, 14], "aggregations": ["mean", "std"]},
      "calendar_config": {"schema_version": "1.0"}
    }
  }'

# Expected: {"rows": [...], "feature_columns": [...], "config_hash": "...", ...}
```

---

## Final Validation Checklist

- [ ] `uv run ruff check app/features/featuresets/` passes with no errors
- [ ] `uv run ruff format --check app/features/featuresets/` passes
- [ ] `uv run mypy app/features/featuresets/` passes with 0 errors
- [ ] `uv run pyright app/features/featuresets/` passes with 0 errors
- [ ] `uv run pytest app/features/featuresets/tests/test_schemas.py -v` all tests pass
- [ ] `uv run pytest app/features/featuresets/tests/test_service.py -v` all tests pass
- [ ] `uv run pytest app/features/featuresets/tests/test_leakage.py -v` **ALL leakage tests pass**
- [ ] `uv run pytest app/features/featuresets/tests/test_routes.py -v -m integration` all tests pass
- [ ] POST /featuresets/compute returns correct response structure
- [ ] Lag features only use past data (shift with positive values)
- [ ] Rolling features exclude current observation (shift(1) before rolling)
- [ ] Calendar features use cyclical encoding
- [ ] Config hash is deterministic (same config = same hash)
- [ ] Imputation respects group boundaries
- [ ] Logs follow `featureops.{action}_{state}` naming convention
- [ ] `examples/features/` contains working examples

---

## Anti-Patterns to Avoid

- ❌ **Don't** use negative shift values — causes future leakage
- ❌ **Don't** apply rolling without shift(1) — includes current observation
- ❌ **Don't** compute features without explicit cutoff_date parameter
- ❌ **Don't** use global statistics (mean/std of entire dataset)
- ❌ **Don't** forget groupby for multi-series data — causes cross-series leakage
- ❌ **Don't** use random train/test splits — use time-based splits only
- ❌ **Don't** use integer encoding for cyclical features (day of week, month)
- ❌ **Don't** hardcode feature configurations — use FeatureSetConfig
- ❌ **Don't** skip leakage tests — they are the most important tests
- ❌ **Don't** use float for monetary values — use Decimal

---

## Example Files

### examples/features/config_shape.json

```json
{
  "schema_version": "1.0",
  "name": "retail_demand_v1",
  "description": "Standard feature set for retail demand forecasting",
  "entity_columns": ["store_id", "product_id"],
  "date_column": "date",
  "target_column": "quantity",
  "lag_config": {
    "schema_version": "1.0",
    "lags": [1, 7, 14, 28, 364],
    "target_column": "quantity",
    "fill_value": null
  },
  "rolling_config": {
    "schema_version": "1.0",
    "windows": [7, 14, 28],
    "aggregations": ["mean", "std"],
    "target_column": "quantity",
    "min_periods": null
  },
  "calendar_config": {
    "schema_version": "1.0",
    "include_day_of_week": true,
    "include_month": true,
    "include_quarter": true,
    "include_year": false,
    "include_is_weekend": true,
    "include_is_month_end": true,
    "include_is_holiday": true,
    "use_cyclical_encoding": true
  },
  "exogenous_config": {
    "schema_version": "1.0",
    "include_price": true,
    "price_lags": [7, 28],
    "include_price_change": true,
    "include_promo": true,
    "include_inventory": false,
    "include_stockout_flag": true
  },
  "imputation_config": {
    "schema_version": "1.0",
    "strategies": {
      "quantity": "zero",
      "unit_price": "ffill",
      "total_amount": "zero"
    }
  }
}
```

### examples/features/preview_features.py

```python
"""Preview feature computation for a single series."""

import asyncio
from datetime import date

import httpx


async def preview_features() -> None:
    """Preview features for store 1, product 1."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8123/featuresets/compute",
            json={
                "store_id": 1,
                "product_id": 1,
                "cutoff_date": "2024-01-31",
                "lookback_days": 60,
                "config": {
                    "schema_version": "1.0",
                    "name": "preview_test",
                    "lag_config": {
                        "schema_version": "1.0",
                        "lags": [1, 7, 14],
                    },
                    "rolling_config": {
                        "schema_version": "1.0",
                        "windows": [7, 14],
                        "aggregations": ["mean", "std"],
                    },
                    "calendar_config": {
                        "schema_version": "1.0",
                    },
                },
            },
        )

        result = response.json()
        print(f"Config Hash: {result['config_hash']}")
        print(f"Feature Columns: {result['feature_columns']}")
        print(f"Row Count: {result['row_count']}")
        print(f"Null Counts: {result['null_counts']}")
        print(f"\nSample Rows:")
        for row in result["rows"][:5]:
            print(f"  {row['date']}: {row['features']}")


if __name__ == "__main__":
    asyncio.run(preview_features())
```

---

## Confidence Score: 8/10

**Rationale:**

- (+) Clear time-safety patterns with explicit cutoff enforcement
- (+) Comprehensive leakage prevention with dedicated tests
- (+) Follows existing codebase patterns (vertical slice, schemas, logging)
- (+) Pydantic v2 config with versioning and hashing for reproducibility
- (+) Type-safe throughout with strict mypy/pyright
- (+) Well-documented gotchas and anti-patterns
- (+) Calendar cyclical encoding is best practice for ML
- (-) Exogenous features require data from PriceHistory/Promotion tables (more complex queries)
- (-) Large datasets may need chunked processing (YAGNI for now)
- (-) Holiday features require Calendar table is_holiday flag to be populated

**Recommended Approach:**

1. Execute tasks 1-3 (directory structure, config, schemas)
2. Run type checkers after each file
3. Execute tasks 4-6 (service implementation)
4. Run unit tests after service
5. Execute tasks 7-8 (routes, main registration)
6. Execute tasks 9-12 (test fixtures, all tests)
7. **CRITICAL: Ensure all leakage tests pass before proceeding**
8. Execute tasks 13-14 (examples, integration tests)
9. Run full validation loop

---

## Version

- **PRP Version:** 1.0
- **Target INITIAL:** INITIAL-4.md (Feature Engineering)
- **Created:** 2026-01-31
- **Author:** Claude Code

---

## References

### Time-Series Feature Engineering
- [MLForecast Feature Engineering](https://www.nixtla.io/blog/automated-time-series-feature-engineering-with-mlforecast)
- [sktime Transformations API](https://www.sktime.net/en/stable/api_reference/transformations.html)
- [Avoiding Data Leakage in Time Series](https://towardsdatascience.com/avoiding-data-leakage-in-timeseries-101-25ea13fcb15f)

### Best Practices
- [Azure AutoML Calendar Features](https://learn.microsoft.com/en-us/azure/machine-learning/concept-automl-forecasting-calendar-features)
- [scikit-learn Pipeline Composition](https://scikit-learn.org/stable/modules/compose.html)
- [Cyclical Feature Encoding](https://developer.nvidia.com/blog/three-approaches-to-encoding-time-information-as-features-for-ml-models/)

### Pydantic v2
- [Field Validators](https://docs.pydantic.dev/latest/concepts/validators/)
- [Model Configuration](https://docs.pydantic.dev/latest/concepts/config/)

### Project Internal
- [CLAUDE.md](../CLAUDE.md) - Type safety, vertical slice architecture
- [Logging Standard](../docs/validation/logging-standard.md) - Event naming convention
- [Ingest Service Pattern](../app/features/ingest/service.py) - Async service patterns
