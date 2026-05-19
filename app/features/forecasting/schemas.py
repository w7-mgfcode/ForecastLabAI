"""Pydantic schemas for forecasting configuration and API contracts.

Model configs are designed to be:
- Immutable (frozen=True) for reproducibility
- Versioned (schema_version) for registry storage
- Hashable (config_hash) for deduplication
"""

from __future__ import annotations

import hashlib
from datetime import date as date_type
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# =============================================================================
# Model Configuration Schemas
# =============================================================================


class ModelConfigBase(BaseModel):
    """Base configuration for all forecasting models.

    All model configs inherit from this base to ensure:
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

        Returns:
            16-character hex string hash of config JSON.
        """
        config_json = self.model_dump_json()
        return hashlib.sha256(config_json.encode()).hexdigest()[:16]


class NaiveModelConfig(ModelConfigBase):
    """Configuration for naive forecaster (last value).

    The naive forecaster predicts the last observed value for all horizons.
    Formula: y_hat[t+h] = y[t] for all h

    This is the simplest baseline and often performs surprisingly well for
    stable time series.
    """

    model_type: Literal["naive"] = "naive"


class SeasonalNaiveModelConfig(ModelConfigBase):
    """Configuration for seasonal naive forecaster.

    Predicts value from same season in previous cycle.
    Formula: y_hat[t+h] = y[t+h-m] where m is season_length

    For weekly seasonality (m=7), Friday's forecast = last Friday's value.

    Attributes:
        season_length: Seasonality period in days (default: 7 for weekly).
    """

    model_type: Literal["seasonal_naive"] = "seasonal_naive"
    season_length: int = Field(
        default=7,
        ge=1,
        le=365,
        description="Seasonality period in days",
    )


class MovingAverageModelConfig(ModelConfigBase):
    """Configuration for moving average forecaster.

    Predicts the mean of the last N observations for all horizons.
    Formula: y_hat[t+h] = mean(y[t-window+1:t+1])

    CRITICAL: Does NOT update recursively - uses same average for all horizons.

    Attributes:
        window_size: Window size for averaging (default: 7).
    """

    model_type: Literal["moving_average"] = "moving_average"
    window_size: int = Field(
        default=7,
        ge=1,
        le=90,
        description="Window size for averaging",
    )


class LightGBMModelConfig(ModelConfigBase):
    """Configuration for LightGBM regressor (feature-flagged).

    LightGBM is an advanced ML model that uses gradient boosting on
    decision trees. Requires feature engineering integration.

    CRITICAL: Only available when forecast_enable_lightgbm=True in settings.

    Attributes:
        n_estimators: Number of boosting rounds.
        max_depth: Maximum depth of trees.
        learning_rate: Learning rate for gradient boosting.
        feature_config_hash: Hash of FeatureSetConfig used for training.
    """

    model_type: Literal["lightgbm"] = "lightgbm"
    n_estimators: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Number of boosting rounds",
    )
    max_depth: int = Field(
        default=6,
        ge=1,
        le=20,
        description="Maximum depth of trees",
    )
    learning_rate: float = Field(
        default=0.1,
        ge=0.001,
        le=1.0,
        description="Learning rate for gradient boosting",
    )
    feature_config_hash: str | None = Field(
        default=None,
        description="Hash of FeatureSetConfig used for training",
    )


class XGBoostModelConfig(ModelConfigBase):
    """Configuration for the XGBoost regressor (feature-flagged).

    XGBoost is an advanced, feature-aware gradient-boosted-tree model. Like
    ``LightGBMModelConfig`` the field set is deliberately conservative —
    ``n_estimators`` / ``max_depth`` / ``learning_rate`` only — so the schema
    surface stays small and training stays deterministic (no stochastic
    subsampling).

    CRITICAL: Only available when forecast_enable_xgboost=True in settings.

    Attributes:
        n_estimators: Number of boosting rounds.
        max_depth: Maximum depth of trees.
        learning_rate: Learning rate for gradient boosting.
        feature_config_hash: Hash of FeatureSetConfig used for training.
    """

    model_type: Literal["xgboost"] = "xgboost"
    n_estimators: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Number of boosting rounds",
    )
    max_depth: int = Field(
        default=6,
        ge=1,
        le=20,
        description="Maximum depth of trees",
    )
    learning_rate: float = Field(
        default=0.1,
        ge=0.001,
        le=1.0,
        description="Learning rate for gradient boosting",
    )
    feature_config_hash: str | None = Field(
        default=None,
        description="Hash of FeatureSetConfig used for training",
    )


class RegressionModelConfig(ModelConfigBase):
    """Configuration for the exogenous-regressor forecaster (PRP-27).

    Wraps scikit-learn's ``HistGradientBoostingRegressor`` — a deterministic,
    NaN-tolerant gradient-boosted tree model. Unlike the baseline forecasters,
    a ``regression`` model *consumes* a per-day exogenous feature frame, so a
    scenario what-if can be answered by genuinely re-forecasting demand
    (``method="model_exogenous"``) rather than by a post-forecast multiplier.

    No feature flag and no new dependency: ``HistGradientBoostingRegressor``
    ships with the already-pinned ``scikit-learn`` (see
    ``PRPs/ai_docs/exogenous-regressor-forecasting.md`` § 5).

    Attributes:
        max_iter: Number of boosting iterations.
        learning_rate: Gradient-boosting learning rate.
        max_depth: Maximum depth of each tree.
        feature_config_hash: Optional hash of the feature contract used.
    """

    model_type: Literal["regression"] = "regression"
    max_iter: int = Field(
        default=200,
        ge=10,
        le=1000,
        description="Number of boosting iterations",
    )
    learning_rate: float = Field(
        default=0.05,
        ge=0.001,
        le=1.0,
        description="Gradient-boosting learning rate",
    )
    max_depth: int = Field(
        default=6,
        ge=1,
        le=20,
        description="Maximum depth of each tree",
    )
    feature_config_hash: str | None = Field(
        default=None,
        description="Hash of the feature contract used for training",
    )


# Union type for all model configs
ModelConfig = (
    NaiveModelConfig
    | SeasonalNaiveModelConfig
    | MovingAverageModelConfig
    | LightGBMModelConfig
    | XGBoostModelConfig
    | RegressionModelConfig
)


# =============================================================================
# API Request/Response Schemas
# =============================================================================


class TrainRequest(BaseModel):
    """Request body for POST /forecasting/train.

    Attributes:
        store_id: Store ID to train model for.
        product_id: Product ID to train model for.
        train_start_date: Start date of training period.
        train_end_date: End date of training period (inclusive).
        config: Model configuration.
    """

    model_config = ConfigDict(strict=True)

    store_id: int = Field(..., ge=1, description="Store ID")
    product_id: int = Field(..., ge=1, description="Product ID")
    # ``strict=False`` overrides the model-level ``strict=True`` so FastAPI's
    # ``validate_python`` (called on the JSON-parsed dict at
    # ``fastapi._compat.v2:175``) accepts ISO date strings from JSON request
    # bodies. See ``docs/_base/SECURITY.md`` -> "Pydantic v2 strict mode on
    # FastAPI request bodies" for the repo-wide policy (issue #117).
    train_start_date: date_type = Field(
        ...,
        strict=False,
        description="Start date of training period",
    )
    train_end_date: date_type = Field(
        ...,
        strict=False,
        description="End date of training period (inclusive)",
    )
    config: ModelConfig

    @field_validator("train_end_date")
    @classmethod
    def validate_date_range(cls, v: date_type, info: object) -> date_type:
        """Ensure train_end_date is after train_start_date."""
        # Type narrow info to ValidationInfo-like object
        data = getattr(info, "data", {})
        if "train_start_date" in data and v <= data["train_start_date"]:
            raise ValueError("train_end_date must be after train_start_date")
        return v


class TrainResponse(BaseModel):
    """Response body for POST /forecasting/train.

    Attributes:
        store_id: Store ID model was trained for.
        product_id: Product ID model was trained for.
        model_type: Type of model trained.
        model_path: Path to saved model bundle.
        config_hash: Hash of the configuration used.
        n_observations: Number of observations used for training.
        train_start_date: Start date of training period.
        train_end_date: End date of training period.
        duration_ms: Training duration in milliseconds.
    """

    store_id: int
    product_id: int
    model_type: str
    model_path: str
    config_hash: str
    n_observations: int
    train_start_date: date_type
    train_end_date: date_type
    duration_ms: float


class PredictRequest(BaseModel):
    """Request body for POST /forecasting/predict.

    Attributes:
        store_id: Store ID to predict for.
        product_id: Product ID to predict for.
        horizon: Number of days to forecast.
        model_path: Path to saved model bundle.
    """

    model_config = ConfigDict(strict=True)

    store_id: int = Field(..., ge=1, description="Store ID")
    product_id: int = Field(..., ge=1, description="Product ID")
    horizon: int = Field(
        ...,
        ge=1,
        le=90,
        description="Number of days to forecast",
    )
    model_path: str = Field(
        ...,
        description="Path to saved model bundle",
    )


class ForecastPoint(BaseModel):
    """Single forecast point.

    Attributes:
        date: Date of the forecast.
        forecast: Point forecast value.
        lower_bound: Lower bound of prediction interval (optional).
        upper_bound: Upper bound of prediction interval (optional).
    """

    date: date_type
    forecast: float
    lower_bound: float | None = None
    upper_bound: float | None = None


class PredictResponse(BaseModel):
    """Response body for POST /forecasting/predict.

    Attributes:
        store_id: Store ID predictions are for.
        product_id: Product ID predictions are for.
        forecasts: List of forecast points.
        model_type: Type of model used.
        config_hash: Hash of the configuration used.
        horizon: Number of days forecasted.
        duration_ms: Prediction duration in milliseconds.
    """

    store_id: int
    product_id: int
    forecasts: list[ForecastPoint]
    model_type: str
    config_hash: str
    horizon: int
    duration_ms: float
