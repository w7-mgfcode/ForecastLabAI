"""Pydantic schemas for forecasting configuration and API contracts.

Model configs are designed to be:
- Immutable (frozen=True) for reproducibility
- Versioned (schema_version) for registry storage
- Hashable (config_hash) for deduplication
"""

from __future__ import annotations

import hashlib
from datetime import date as date_type
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.shared.feature_frames import FeatureGroup

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


class WeightedMovingAverageModelConfig(ModelConfigBase):
    """Configuration for the weighted moving average baseline (PRP-36).

    Always-on target-only baseline. The fitted forecaster computes a
    weighted mean of the last ``window_size`` observations and emits it
    for every horizon step (no recursive update).

    Two weight strategies are supported:

    - ``'linear'`` → ``weights = np.arange(1, window_size+1)`` — most recent
      observation weighted highest, oldest weighted lowest.
    - ``'exponential'`` → ``weights = np.power(decay, np.arange(window_size-1, -1, -1))``
      — geometric decay from the most recent observation.

    Attributes:
        window_size: Number of trailing observations included in the average.
        weight_strategy: Either ``'linear'`` or ``'exponential'``.
        decay: Geometric decay factor for the ``'exponential'`` strategy
            (ignored when ``weight_strategy='linear'``).
    """

    model_type: Literal["weighted_moving_average"] = "weighted_moving_average"
    window_size: int = Field(
        default=7,
        ge=2,
        le=90,
        description="Number of trailing observations to average",
    )
    weight_strategy: Literal["linear", "exponential"] = Field(
        default="linear",
        description="Weighting scheme: 'linear' or 'exponential'",
    )
    decay: float = Field(
        default=0.7,
        gt=0.0,
        lt=1.0,
        description="Geometric decay factor (used only for weight_strategy='exponential')",
    )


class SeasonalAverageModelConfig(ModelConfigBase):
    """Configuration for the seasonal-average baseline (PRP-36).

    Always-on target-only baseline. For horizon day ``j`` with season
    length ``S``, the fitted forecaster averages the values at offsets
    ``{j - k*S}`` for ``k`` in ``[1..lookback_cycles]`` that fall inside
    the stored history. With ``trim_outliers=True`` the per-bucket sample
    drops its min and max before averaging (requires ≥4 samples to apply).

    Attributes:
        season_length: Seasonality period in days (default 7 = weekly).
        lookback_cycles: Number of trailing cycles to draw samples from.
        trim_outliers: If True, drop the min + max sample before averaging.
    """

    model_type: Literal["seasonal_average"] = "seasonal_average"
    season_length: int = Field(
        default=7,
        ge=2,
        le=365,
        description="Seasonality period in days",
    )
    lookback_cycles: int = Field(
        default=4,
        ge=2,
        le=12,
        description="Number of trailing cycles to draw samples from",
    )
    trim_outliers: bool = Field(
        default=False,
        description="If True, drop the min + max sample before averaging (requires ≥4 samples)",
    )


class TrendRegressionBaselineModelConfig(ModelConfigBase):
    """Configuration for the Ridge trend baseline (PRP-36).

    Target-only Ridge regressor over an elapsed-day index plus optional
    calendar one-hots (day-of-week, month). Does NOT consume the V1 or
    V2 feature frame — its features are purely calendar-derived inside
    the forecaster. ``requires_features`` stays ``False``.

    Attributes:
        alpha: Ridge L2 regularization strength.
        include_dow: If True, include a 7-column day-of-week one-hot.
        include_month: If True, include a 12-column month-of-year one-hot.
    """

    model_type: Literal["trend_regression_baseline"] = "trend_regression_baseline"
    alpha: float = Field(
        default=1.0,
        ge=0.0,
        le=1000.0,
        description="Ridge L2 regularization strength",
    )
    include_dow: bool = Field(
        default=True,
        description="If True, include a day-of-week one-hot in the design matrix",
    )
    include_month: bool = Field(
        default=True,
        description="If True, include a month-of-year one-hot in the design matrix",
    )


class RandomForestModelConfig(ModelConfigBase):
    """Configuration for the sklearn RandomForest feature-aware forecaster (PRP-36).

    Optional, gated by ``forecast_enable_random_forest`` in settings. Wraps
    ``sklearn.ensemble.RandomForestRegressor`` with ``n_jobs=1`` (required
    for determinism) and a fixed ``random_state``. Unlike
    ``HistGradientBoostingRegressor``, ``RandomForestRegressor`` DOES expose
    ``feature_importances_`` — so ``extract_feature_importance`` returns a
    1-D importance vector matching ``feature_columns``.

    Attributes:
        n_estimators: Number of trees in the forest.
        max_depth: Maximum depth per tree (``None`` = unlimited).
        min_samples_leaf: Minimum samples required to be at a leaf node.
        feature_config_hash: Optional hash of the feature contract used.
    """

    model_type: Literal["random_forest"] = "random_forest"
    n_estimators: int = Field(
        default=100,
        ge=10,
        le=500,
        description="Number of trees in the forest",
    )
    max_depth: int | None = Field(
        default=10,
        ge=2,
        le=64,
        description="Maximum depth per tree (None = unlimited)",
    )
    min_samples_leaf: int = Field(
        default=2,
        ge=1,
        le=50,
        description="Minimum samples required to be at a leaf node",
    )
    feature_config_hash: str | None = Field(
        default=None,
        description="Hash of the feature contract used for training",
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


class ProphetLikeModelConfig(ModelConfigBase):
    """Configuration for the Prophet-like additive forecaster (MLZOO-C2).

    A deterministic, regularized ADDITIVE linear model — a ``Ridge`` regressor
    over the canonical 14-column feature frame — that decomposes demand into
    trend / seasonality / holiday-regressor components. It approximates
    Prophet's additive shape WITHOUT the real ``prophet``/Stan dependency: it
    does not model changepoint trend, posterior uncertainty, or automatic
    seasonality discovery. Pure scikit-learn — no optional dependency, no
    feature flag, always available (like ``RegressionModelConfig``).

    Attributes:
        alpha: Ridge L2 regularization strength. 0.0 degenerates to ordinary
            least squares; the default 1.0 keeps coefficients robust to the
            collinear engineered-feature frame.
        feature_config_hash: Optional hash of the feature contract used.
    """

    model_type: Literal["prophet_like"] = "prophet_like"
    alpha: float = Field(
        default=1.0,
        ge=0.0,
        le=10000.0,
        description="Ridge L2 regularization strength",
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
    | WeightedMovingAverageModelConfig
    | SeasonalAverageModelConfig
    | TrendRegressionBaselineModelConfig
    | RandomForestModelConfig
    | LightGBMModelConfig
    | XGBoostModelConfig
    | RegressionModelConfig
    | ProphetLikeModelConfig
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
    # PRP-35: opt-in to the V2 feature contract (richer, leakage-safe). V1
    # remains the default and the back-compat path; V2 callers also set
    # ``feature_groups`` to pick the enabled :class:`FeatureGroup` subset.
    # NOTE: these fields live on ``TrainRequest``, NOT on ``ModelConfigBase`` —
    # adding them to the config would mutate every existing ``config_hash()``
    # value, orphaning every registry row and alias. The resolved version is
    # persisted into bundle metadata instead.
    feature_frame_version: int = Field(
        default=1,
        ge=1,
        le=2,
        description=(
            "Feature contract version. 1 = V1 (default, 14 columns, back-compat); "
            "2 = V2 (richer manifest, opt-in)."
        ),
    )
    feature_groups: list[str] | None = Field(
        default=None,
        description=(
            "V2 only: optional list of FeatureGroup names to enable "
            "(None → DEFAULT_V2_GROUPS). MUST be None / omitted when "
            "feature_frame_version=1 (422 otherwise)."
        ),
    )

    @field_validator("train_end_date")
    @classmethod
    def validate_date_range(cls, v: date_type, info: object) -> date_type:
        """Ensure train_end_date is after train_start_date."""
        # Type narrow info to ValidationInfo-like object
        data = getattr(info, "data", {})
        if "train_start_date" in data and v <= data["train_start_date"]:
            raise ValueError("train_end_date must be after train_start_date")
        return v

    @model_validator(mode="after")
    def validate_feature_frame_version_and_groups(self) -> TrainRequest:
        """Reject ``feature_groups`` when V1 and unknown group names when V2."""
        if self.feature_frame_version == 1 and self.feature_groups is not None:
            raise ValueError(
                "feature_groups is only valid when feature_frame_version=2; "
                "omit it for V1 training."
            )
        if self.feature_frame_version == 2 and self.feature_groups is not None:
            valid_names = {g.value for g in FeatureGroup}
            unknown = [name for name in self.feature_groups if name not in valid_names]
            if unknown:
                raise ValueError(
                    f"Unknown FeatureGroup name(s): {unknown!r}. "
                    f"Valid names: {sorted(valid_names)}."
                )
        return self


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


# =============================================================================
# Model Family + Feature Metadata Schemas (MLZOO-D / PRP-31)
# =============================================================================


class ModelFamily(str, Enum):
    """Classifier for advanced-model UI surfacing.

    Derived from ``model_type``; not persisted in the DB. Surfaced on
    ``RunResponse`` via a computed field and consumed by the dashboard for the
    family Badge and the feature-importance panel routing. Unknown model types
    classify as ``BASELINE`` (forward-compatible for new families before the
    map in ``feature_metadata.py`` is updated).
    """

    BASELINE = "baseline"  # naive, seasonal_naive, moving_average
    TREE = "tree"  # regression (HistGBR), lightgbm, xgboost
    ADDITIVE = "additive"  # prophet_like (Ridge pipeline)


class FeatureImportanceItem(BaseModel):
    """One row of model-derived feature importance, ready for the dashboard."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Canonical feature column name (e.g. 'lag_7').")
    importance: float = Field(
        ...,
        description=(
            "For tree models: estimator.feature_importances_ value "
            "(non-negative). For additive models: "
            "pipeline.named_steps['ridge'].coef_ value (signed; the sign "
            "carries directional information and MUST be preserved)."
        ),
    )
    kind: Literal["tree", "linear_coef"] = Field(
        ...,
        description=(
            "Display semantics: 'tree' → magnitude bar; "
            "'linear_coef' → signed bar with direction icon."
        ),
    )
    rank: int = Field(..., ge=1, description="1-indexed rank by |importance| desc.")


class FeatureMetadataResponse(BaseModel):
    """The /forecasting/runs/{run_id}/feature-metadata response.

    Also the /forecasting/jobs/{job_id}/feature-metadata response. When sourced
    from a job, ``run_id`` is the **artifact key** parsed from the bundle file
    name (12-char hex), NOT a registry ``model_run.run_id``. Consumers MUST NOT
    join this back to the registry by that field when the source was a job.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(
        ...,
        description=(
            "Source identifier. For the runs-keyed endpoint: the registry "
            "run_id. For the jobs-keyed endpoint: the forecast-artifact key "
            "(``uuid.uuid4().hex[:12]``) parsed from the bundle path stem."
        ),
    )
    model_type: str
    model_family: ModelFamily
    feature_columns: list[str] = Field(
        ...,
        description=(
            "The canonical feature frame the model consumed at training time. "
            "Always 14 columns for v0.2.16 feature-aware models (see "
            "app/shared/feature_frames/contract.py:80)."
        ),
    )
    features: list[FeatureImportanceItem] = Field(
        ...,
        description="Sorted by |importance| descending; len == len(feature_columns).",
    )
    importance_type: str | None = Field(
        default=None,
        description=(
            "For LightGBM / XGBoost: the booster's ``importance_type`` "
            "('split' / 'gain' / 'weight' / 'cover' depending on the library "
            "default; ForecastLabAI does not override at training time). "
            "For HistGBR-based RegressionForecaster: 'permutation'. "
            "For prophet_like: 'ridge_coef'. Always populated so consumers "
            "know what the numbers mean."
        ),
    )
    # PRP-35 — purely additive V2 metadata. ``feature_frame_version`` defaults
    # to 1 for legacy bundles (``bundle.metadata.get("feature_frame_version", 1)``).
    # ``feature_groups`` / ``feature_safety_classes`` are populated for V2
    # bundles only and absent (None) for V1.
    feature_frame_version: int = Field(
        default=1,
        ge=1,
        le=2,
        description="Feature contract version recorded in the bundle metadata.",
    )
    feature_groups: dict[str, list[str]] | None = Field(
        default=None,
        description=(
            "V2 only: ``{group_name: [columns]}`` mapping from "
            "``v2_feature_groups_dict``. None for V1 bundles."
        ),
    )
    feature_safety_classes: dict[str, str] | None = Field(
        default=None,
        description=(
            "V2 only: ``{column: safety.value}`` mapping from "
            "``v2_feature_safety_classes``. None for V1 bundles."
        ),
    )
