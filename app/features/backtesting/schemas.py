"""Pydantic schemas for backtesting configuration and API contracts.

Schemas are designed to be:
- Immutable (frozen=True) for reproducibility
- Versioned (schema_version) for registry storage
- Hashable (config_hash) for deduplication
"""

from __future__ import annotations

import hashlib
from datetime import date as date_type
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.features.forecasting.schemas import ModelConfig

# =============================================================================
# Split Configuration
# =============================================================================


class SplitConfig(BaseModel):
    """Configuration for time-series splitting.

    Attributes:
        strategy: 'expanding' grows training window; 'sliding' keeps fixed size.
        n_splits: Number of CV folds (2-20).
        min_train_size: Minimum training samples required.
        gap: Gap days between train end and test start (simulates data latency).
        horizon: Forecast horizon per fold.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy: Literal["expanding", "sliding"] = Field(
        default="expanding",
        description="Expanding grows training window; sliding keeps fixed size",
    )
    n_splits: int = Field(
        default=5,
        ge=2,
        le=20,
        description="Number of CV folds",
    )
    min_train_size: int = Field(
        default=30,
        ge=7,
        description="Minimum training samples",
    )
    gap: int = Field(
        default=0,
        ge=0,
        le=30,
        description="Gap between train end and test start",
    )
    horizon: int = Field(
        default=14,
        ge=1,
        le=90,
        description="Forecast horizon per fold",
    )

    @field_validator("horizon")
    @classmethod
    def validate_horizon_vs_gap(cls, v: int, info: object) -> int:
        """Ensure horizon is reasonable relative to gap."""
        data = getattr(info, "data", {})
        gap = data.get("gap", 0)
        if gap is not None and v <= gap:
            raise ValueError(f"horizon ({v}) must be greater than gap ({gap})")
        return v


# =============================================================================
# Backtest Configuration
# =============================================================================


class BacktestConfig(BaseModel):
    """Complete backtest configuration.

    Attributes:
        schema_version: Semantic version of this config schema.
        split_config: Configuration for time-series splitting.
        model_config_main: The model configuration to evaluate.
        include_baselines: Whether to include naive/seasonal_naive benchmarks.
        store_fold_details: Whether to store per-fold actuals/predictions.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(
        default="1.0",
        description="Semantic version of this config schema",
        pattern=r"^\d+\.\d+(\.\d+)?$",
    )
    split_config: SplitConfig = Field(default_factory=SplitConfig)
    model_config_main: Annotated[ModelConfig, Field(discriminator="model_type")]
    include_baselines: bool = Field(
        default=True,
        description="Include naive/seasonal benchmarks",
    )
    store_fold_details: bool = Field(
        default=True,
        description="Store per-fold actuals/predictions",
    )

    def config_hash(self) -> str:
        """Generate deterministic hash of configuration.

        Returns:
            16-character hex string hash of config JSON.
        """
        config_json = self.model_dump_json()
        return hashlib.sha256(config_json.encode()).hexdigest()[:16]


# =============================================================================
# Split Boundary and Fold Results
# =============================================================================


class SplitBoundary(BaseModel):
    """Boundary dates for a single CV split.

    Attributes:
        fold_index: Index of the fold (0-based).
        train_start: Start date of training period.
        train_end: End date of training period.
        test_start: Start date of test period.
        test_end: End date of test period.
        train_size: Number of training samples.
        test_size: Number of test samples.
    """

    fold_index: int
    train_start: date_type
    train_end: date_type
    test_start: date_type
    test_end: date_type
    train_size: int
    test_size: int


class FoldResult(BaseModel):
    """Results for a single backtest fold.

    Attributes:
        fold_index: Index of the fold (0-based).
        split: Split boundary information.
        dates: List of dates in the test period.
        actuals: Actual values for the test period.
        predictions: Predicted values for the test period.
        metrics: Dictionary of metric names to values.
    """

    fold_index: int
    split: SplitBoundary
    dates: list[date_type]
    actuals: list[float]
    predictions: list[float]
    metrics: dict[str, float]


class ModelBacktestResult(BaseModel):
    """Backtest results for a single model.

    Attributes:
        model_type: Type of the model.
        config_hash: Hash of the model configuration.
        fold_results: Results for each fold.
        aggregated_metrics: Mean metrics across folds.
        metric_std: Standard deviation of metrics across folds.
    """

    model_type: str
    config_hash: str
    fold_results: list[FoldResult]
    aggregated_metrics: dict[str, float]
    metric_std: dict[str, float]


# =============================================================================
# API Request/Response Schemas
# =============================================================================


class BacktestRequest(BaseModel):
    """Request body for POST /backtesting/run.

    Attributes:
        store_id: Store ID to run backtest for.
        product_id: Product ID to run backtest for.
        start_date: Start date of the data range.
        end_date: End date of the data range.
        config: Backtest configuration.
    """

    model_config = ConfigDict(strict=True)

    store_id: int = Field(..., ge=1, description="Store ID")
    product_id: int = Field(..., ge=1, description="Product ID")
    start_date: date_type = Field(
        ...,
        description="Start date of data range",
    )
    end_date: date_type = Field(
        ...,
        description="End date of data range",
    )
    config: BacktestConfig

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v: date_type, info: object) -> date_type:
        """Ensure end_date is after start_date."""
        data = getattr(info, "data", {})
        if "start_date" in data and v <= data["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v


class BacktestResponse(BaseModel):
    """Response body for POST /backtesting/run.

    Attributes:
        backtest_id: Unique identifier for this backtest run.
        store_id: Store ID the backtest was run for.
        product_id: Product ID the backtest was run for.
        config_hash: Hash of the backtest configuration.
        split_config: Split configuration used.
        main_model_results: Results for the main model.
        baseline_results: Results for baseline models (if included).
        comparison_summary: Summary comparing main model to baselines.
        duration_ms: Total duration in milliseconds.
        leakage_check_passed: Whether leakage sanity checks passed.
    """

    backtest_id: str
    store_id: int
    product_id: int
    config_hash: str
    split_config: SplitConfig
    main_model_results: ModelBacktestResult
    baseline_results: list[ModelBacktestResult] | None = None
    comparison_summary: dict[str, dict[str, float]] | None = None
    duration_ms: float
    leakage_check_passed: bool
