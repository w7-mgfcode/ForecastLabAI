"""Pydantic schemas for feature engineering configuration.

Feature configs are designed to be:
- Immutable (frozen=True) for reproducibility
- Versioned (schema_version) for registry storage
- Hashable (config_hash) for deduplication
"""

from __future__ import annotations

import hashlib
from datetime import date as date_type
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FeatureConfigBase(BaseModel):
    """Base configuration with versioning support.

    All feature configs inherit from this base to ensure:
    - Immutability after creation (frozen=True)
    - No extra fields allowed (extra="forbid")
    - Schema versioning for reproducibility
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    schema_version: str = Field(
        default="1.0",
        description="Semantic version of this config schema",
        pattern=r"^\d+\.\d+(\.\d+)?$",
    )

    def config_hash(self) -> str:
        """Generate deterministic hash of configuration.

        Excludes ``None``-valued fields so that adding new optional sub-config
        slots is hash-invariant for callers that don't set them (additive
        contract — see PRP-3.1A §15 Decision E).

        Returns:
            16-character hex string hash of config JSON.
        """
        config_json = self.model_dump_json(exclude_none=True)
        return hashlib.sha256(config_json.encode()).hexdigest()[:16]


class LagConfig(FeatureConfigBase):
    """Configuration for lag-based features.

    Lag features capture autoregressive patterns where past values
    predict future values. All lags must be positive to prevent
    future data leakage.

    Attributes:
        lags: Tuple of positive lag periods in days.
        target_column: Column to compute lags from.
        fill_value: Value to fill NaN (None = keep NaN).
    """

    lags: tuple[int, ...] = Field(
        default=(1, 7, 14, 28),
        description="Lag periods in days (must be positive)",
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
        if not v:
            raise ValueError("At least one lag must be specified")
        if any(lag <= 0 for lag in v):
            raise ValueError("All lags must be positive integers (no future leakage)")
        return v


class RollingConfig(FeatureConfigBase):
    """Configuration for rolling window features.

    Rolling features capture trends and volatility over fixed windows.
    Uses shift(1) before rolling to exclude current observation.

    Attributes:
        windows: Tuple of window sizes in days.
        aggregations: Tuple of aggregation functions to apply.
        target_column: Column to compute rolling features from.
        min_periods: Minimum observations required (None = window size).
    """

    windows: tuple[int, ...] = Field(
        default=(7, 14, 28),
        description="Window sizes in days",
    )
    aggregations: tuple[Literal["mean", "std", "min", "max", "sum"], ...] = Field(
        default=("mean", "std"),
        description="Aggregation functions to apply",
    )
    target_column: str = Field(default="quantity")
    min_periods: int | None = Field(
        default=None,
        description="Minimum observations required (None = window size)",
    )

    @field_validator("windows")
    @classmethod
    def validate_windows_positive(cls, v: tuple[int, ...]) -> tuple[int, ...]:
        """Ensure all windows are positive."""
        if not v:
            raise ValueError("At least one window must be specified")
        if any(w <= 0 for w in v):
            raise ValueError("All windows must be positive integers")
        return v


class CalendarConfig(FeatureConfigBase):
    """Configuration for calendar features.

    Calendar features capture cyclical patterns (day of week, month)
    and special events (holidays). No leakage risk as features are
    derived from the date column itself.

    Attributes:
        include_day_of_week: Include day of week features.
        include_month: Include month features.
        include_quarter: Include quarter features.
        include_year: Include year feature.
        include_is_weekend: Include weekend flag.
        include_is_month_end: Include month-end flag.
        include_is_holiday: Include holiday flag (requires Calendar table).
        use_cyclical_encoding: Use sin/cos encoding for periodic features.
    """

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
    """Configuration for exogenous variable features.

    Exogenous features capture external factors (price, promotions,
    inventory) that affect demand. All features are lagged appropriately
    to prevent leakage.

    Attributes:
        include_price: Include price features.
        price_lags: Lag periods for price features.
        include_price_change: Include price change percentage.
        include_promo: Include promotion flags.
        include_inventory: Include inventory levels.
        include_stockout_flag: Include stockout flag.
    """

    include_price: bool = True
    price_lags: tuple[int, ...] = Field(
        default=(7, 28),
        description="Lag periods for price features",
    )
    include_price_change: bool = True
    include_promo: bool = True
    include_inventory: bool = False
    include_stockout_flag: bool = True

    @field_validator("price_lags")
    @classmethod
    def validate_price_lags_positive(cls, v: tuple[int, ...]) -> tuple[int, ...]:
        """Ensure all price lags are positive."""
        if any(lag <= 0 for lag in v):
            raise ValueError("All price lags must be positive integers")
        return v


class LifecycleConfig(FeatureConfigBase):
    """Configuration for product-lifecycle features.

    Lifecycle features capture time-since-launch and time-since-discontinue
    as continuous integer date-deltas (NOT categorical stage). LightGBM splits
    discover stage boundaries from the continuous variable naturally — see
    PRP-3.1 decisions log §1.

    All features are derived from product.launch_date and
    product.discontinue_date (both nullable on Phase 2 products).

    Attributes:
        include_days_since_launch: Emit days_since_launch_lag{N} columns.
        include_days_since_discontinue: Emit days_since_discontinue_lag{N}.
        lag_days: Lag offset in days (>= 1 to prevent leakage).
    """

    include_days_since_launch: bool = True
    include_days_since_discontinue: bool = True
    lag_days: int = Field(default=1, ge=1, le=30, description="Lag offset in days")


class ReplenishmentConfig(FeatureConfigBase):
    """Configuration for replenishment-event features.

    Replenishment features capture inbound-stock cadence via:
      * ``days_since_last_replenishment_lag{N}`` -- gap to previous event
      * ``replenishment_count_w{W}_lag{N}`` -- rolling count over window W

    Source: ``replenishment_event`` table (separate from sales_daily).
    The JOIN happens in service.py (PRP-3.1C) -- this slice only declares
    the contract.

    Attributes:
        include_days_since_last: Emit days_since_last_replenishment_lag{N}.
        include_count_window: Emit replenishment_count_w{W}_lag{N}.
        lag_days: Lag offset (>= 1).
        count_window_days: Rolling-window size for count features (7-60).
    """

    include_days_since_last: bool = True
    include_count_window: bool = True
    lag_days: int = Field(default=1, ge=1, le=30, description="Lag offset in days")
    count_window_days: int = Field(
        default=14,
        ge=7,
        le=60,
        description="Rolling-window size for replenishment count features",
    )


class PromotionConfig(FeatureConfigBase):
    """Configuration for generic promotion-family features.

    GENERALIZED from the original MarkdownConfig design (PRP-3.1 decisions
    log §3) to cover all four ``promotion.kind`` values via one JOIN:
    pct_off | bogo | bundle | markdown. Default ``kinds_to_track=("markdown",)``
    preserves the original PRD intent; caller opts in to others.

    Produced columns (per kind in kinds_to_track):
      * ``promo_<kind>_active_lag{N}`` -- int 0/1
      * ``promo_<kind>_intensity_lag{N}`` -- float (when include_intensity)

    Intensity source: ``promotion.discount_pct`` (Numeric(5,4), 0..1 range)
    per data_platform/models.py. NULL discounts produce NaN columns.

    Attributes:
        kinds_to_track: Allow-listed promotion kinds (tuple required for
            frozen-model hashability).
        include_active: Emit promo_<kind>_active_lag{N}.
        include_intensity: Emit promo_<kind>_intensity_lag{N}.
        lag_days: Lag offset (>= 1).
    """

    kinds_to_track: tuple[Literal["pct_off", "bogo", "bundle", "markdown"], ...] = Field(
        default=("markdown",),
        description="Promotion kinds to track (subset of promotion.kind allow-list)",
    )
    include_active: bool = True
    include_intensity: bool = True
    lag_days: int = Field(default=1, ge=1, le=30, description="Lag offset in days")

    @field_validator("kinds_to_track")
    @classmethod
    def validate_kinds_non_empty_unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        """Reject empty tuple and duplicates."""
        if not v:
            raise ValueError("At least one promotion kind must be specified")
        if len(set(v)) != len(v):
            raise ValueError("Duplicate promotion kinds are not allowed")
        return v


class ImputationConfig(FeatureConfigBase):
    """Configuration for missing value imputation.

    Imputation strategies:
    - zero: Fill with 0 (for sales/quantity) — TIME-SAFE
    - ffill: Forward fill (for prices) — TIME-SAFE
    - bfill: Backward fill — WARNING: uses future data, avoid in production
    - mean: Fill with group mean — WARNING: uses future data, avoid in production
    - expanding_mean: Fill with expanding mean — TIME-SAFE (uses only past data)
    - drop: Drop rows with missing values — TIME-SAFE

    Attributes:
        strategies: Mapping of column name to imputation strategy.
    """

    strategies: dict[str, Literal["zero", "ffill", "bfill", "mean", "expanding_mean", "drop"]] = (
        Field(
            default={
                "quantity": "zero",
                "unit_price": "ffill",
                "total_amount": "zero",
            }
        )
    )


class FeatureSetConfig(FeatureConfigBase):
    """Complete feature engineering configuration.

    Combines all feature sub-configurations into a single config.
    Each sub-config can be None to disable that feature type.

    Attributes:
        name: Human-readable name for this feature set.
        description: Optional description.
        entity_columns: Columns defining the entity (e.g., store_id, product_id).
        date_column: Column containing the date.
        target_column: Column containing the target variable.
        lag_config: Configuration for lag features (None = disabled).
        rolling_config: Configuration for rolling features (None = disabled).
        calendar_config: Configuration for calendar features (None = disabled).
        exogenous_config: Configuration for exogenous features (None = disabled).
        lifecycle_config: Configuration for lifecycle features (None = disabled).
        replenishment_config: Configuration for replenishment features (None = disabled).
        promotion_config: Configuration for promotion features (None = disabled).
        imputation_config: Configuration for imputation (None = disabled).
    """

    name: str = Field(..., min_length=1, max_length=100, description="Feature set name")
    description: str | None = Field(default=None, description="Optional description")

    # Data grain
    entity_columns: tuple[str, ...] = Field(
        default=("store_id", "product_id"),
        description="Columns defining the entity grain",
    )
    date_column: str = Field(default="date")
    target_column: str = Field(default="quantity")

    # Feature sub-configurations (None = disabled)
    lag_config: LagConfig | None = None
    rolling_config: RollingConfig | None = None
    calendar_config: CalendarConfig | None = None
    exogenous_config: ExogenousConfig | None = None
    # --- Phase 2 additions (PRP-3.1A) ---
    lifecycle_config: LifecycleConfig | None = None
    replenishment_config: ReplenishmentConfig | None = None
    promotion_config: PromotionConfig | None = None
    # --- end Phase 2 additions ---
    imputation_config: ImputationConfig | None = None

    def get_enabled_features(self) -> list[str]:
        """Return list of enabled feature types.

        Returns:
            List of enabled feature type names.
        """
        enabled: list[str] = []
        if self.lag_config:
            enabled.append("lag")
        if self.rolling_config:
            enabled.append("rolling")
        if self.calendar_config:
            enabled.append("calendar")
        if self.exogenous_config:
            enabled.append("exogenous")
        # --- Phase 2 additions (PRP-3.1A) ---
        if self.lifecycle_config:
            enabled.append("lifecycle")
        if self.replenishment_config:
            enabled.append("replenishment")
        if self.promotion_config:
            enabled.append("promotion")
        # --- end Phase 2 additions ---
        return enabled


# =============================================================================
# API Request/Response Schemas
# =============================================================================


class ComputeFeaturesRequest(BaseModel):
    """Request body for POST /featuresets/compute.

    Attributes:
        store_id: Store ID to compute features for.
        product_id: Product ID to compute features for.
        cutoff_date: Maximum date to include (CRITICAL for time-safety).
        lookback_days: Days of history to use.
        config: Feature set configuration.
    """

    model_config = ConfigDict(strict=True)

    store_id: int = Field(..., ge=1, description="Store ID")
    product_id: int = Field(..., ge=1, description="Product ID")
    # NOTE: ``strict=False`` overrides the model-level ``strict=True`` for this
    # field so FastAPI's ``validate_python`` (called on the JSON-parsed dict
    # by ``fastapi._compat.v2:175``) accepts ISO date strings from JSON
    # request bodies. Without this override, ``strict=True`` requires an
    # actual ``datetime.date`` instance -- which JSON cannot carry --
    # and every HTTP caller would 422.
    cutoff_date: date_type = Field(
        ...,
        strict=False,
        description="Compute features up to this date (inclusive)",
    )
    lookback_days: int = Field(
        default=365,
        ge=1,
        le=1095,
        description="Days of history to use",
    )
    config: FeatureSetConfig


class FeatureRow(BaseModel):
    """Single row of computed features.

    Attributes:
        date: Date for this row.
        store_id: Store ID.
        product_id: Product ID.
        features: Dictionary of feature name to value.
    """

    date: date_type
    store_id: int
    product_id: int
    features: dict[str, float | int | None]


class ComputeFeaturesResponse(BaseModel):
    """Response body for POST /featuresets/compute.

    Attributes:
        rows: List of feature rows.
        feature_columns: List of computed feature column names.
        config_hash: Hash of the configuration used.
        cutoff_date: Cutoff date used.
        row_count: Number of rows returned.
        null_counts: Count of null values per feature.
        duration_ms: Processing duration in milliseconds.
    """

    rows: list[FeatureRow]
    feature_columns: list[str]
    config_hash: str
    cutoff_date: date_type
    row_count: int
    null_counts: dict[str, int]
    duration_ms: float


class PreviewFeaturesRequest(BaseModel):
    """Request for POST /featuresets/preview.

    Attributes:
        store_id: Store ID to preview features for.
        product_id: Product ID to preview features for.
        cutoff_date: Cutoff date for features.
        sample_rows: Number of sample rows to return.
        config: Feature set configuration.
    """

    model_config = ConfigDict(strict=True)

    store_id: int = Field(..., ge=1)
    product_id: int = Field(..., ge=1)
    # See ``ComputeFeaturesRequest.cutoff_date`` for the rationale on
    # ``strict=False`` (FastAPI ``validate_python`` + JSON dates).
    cutoff_date: date_type = Field(..., strict=False)
    sample_rows: int = Field(default=10, ge=1, le=100)
    config: FeatureSetConfig
