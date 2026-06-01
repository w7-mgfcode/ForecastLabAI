"""Pydantic v2 schemas for the Forecast Champion Selector slice (issue #353).

Request bodies use ``ConfigDict(strict=True)`` per
``docs/_base/SECURITY.md`` § "Pydantic v2 strict mode on FastAPI request
bodies"; the only JSON-non-native fields (``SelectionWindow.start_date`` /
``end_date``) carry ``Field(strict=False, ...)`` so the strict-mode policy
linter (``app/core/tests/test_strict_mode_policy.py``) stays green and ISO-date
JSON strings are accepted on the ``validate_python`` path.

Enum-like string fields use ``Literal[...]`` (NOT a ``str``-``Enum``) because
strict mode refuses to coerce a JSON string into a str-enum instance — the same
reason ``app/features/batch/schemas.py`` uses literals.

Response/intermediate models are plain ``BaseModel`` (outputs need no strict
coercion). They form the stable backend contract the eventual UI consumes.

``SplitConfig`` is reused directly from the backtesting slice (a schema type
with no import cycle back to this slice) to avoid configuration drift.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.features.backtesting.schemas import SplitConfig

# Valid forecasting model_type values — the full ``ModelConfig`` union
# (``app/features/forecasting/schemas.py``). ``lightgbm``/``xgboost`` are opt-in
# extras and may degrade to a failed candidate at runtime when the extra is
# absent (handled in the service, not rejected here).
ModelType = Literal[
    "naive",
    "seasonal_naive",
    "moving_average",
    "weighted_moving_average",
    "seasonal_average",
    "trend_regression_baseline",
    "random_forest",
    "lightgbm",
    "xgboost",
    "regression",
    "prophet_like",
]

RankingMetric = Literal["wape", "smape", "mae", "bias"]
SelectionStatusLiteral = Literal["pending", "running", "completed", "partial", "failed"]
ConfidenceLevel = Literal["high", "medium", "low"]
AvailabilityStatus = Literal["ready", "limited", "unusable"]


# =============================================================================
# Request models (strict mode)
# =============================================================================


class SelectionWindow(BaseModel):
    """Inclusive date window the candidate backtests run over."""

    model_config = ConfigDict(strict=True)

    start_date: date = Field(strict=False, description="Window start (inclusive), YYYY-MM-DD")
    end_date: date = Field(strict=False, description="Window end (inclusive), YYYY-MM-DD")

    @model_validator(mode="after")
    def _check_order(self) -> SelectionWindow:
        """Reject an inverted/zero-length window (surfaced as RFC 7807 422)."""
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class CandidateModelConfig(BaseModel):
    """One candidate forecasting model to evaluate.

    ``params`` are the FLAT model-specific parameters (e.g.
    ``{"season_length": 7}``). They are flattened into the forecasting
    ``ModelConfig`` union at the service boundary; unknown params surface as a
    failed candidate with a reason rather than a request rejection.
    """

    model_config = ConfigDict(strict=True)

    model_type: ModelType
    params: dict[str, Any] = Field(default_factory=dict)


class RankingPolicy(BaseModel):
    """Tunable thresholds for ranking filters + confidence.

    ``max_acceptable_abs_bias`` is an ABSOLUTE bias bound in demand units and is
    therefore series-scale dependent; it defaults high enough to be effectively
    disabled so confidence is driven primarily by the relative WAPE lead, the
    valid-candidate count, and the sample size. Set a series-appropriate value
    to enable the bias guard.
    """

    model_config = ConfigDict(strict=True)

    minimum_sample_size: int = Field(
        default=0, ge=0, description="Drop candidates whose backtest sample is below this"
    )
    high_confidence_rel_improvement: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Relative WAPE lead over 2nd place required for HIGH confidence",
    )
    max_acceptable_abs_bias: float = Field(
        default=1_000_000_000.0,
        ge=0.0,
        description="Absolute winner-bias bound (demand units); high default = guard disabled",
    )


class ModelSelectionRunRequest(BaseModel):
    """``POST /model-selection/run`` request body."""

    model_config = ConfigDict(strict=True)

    store_id: int = Field(..., ge=1, description="Store ID")
    product_id: int = Field(..., ge=1, description="Product ID")
    selection_window: SelectionWindow
    forecast_horizon: int = Field(..., ge=1, le=90, description="Forecast horizon in days")
    ranking_metric: RankingMetric = "wape"
    split_config: SplitConfig = Field(default_factory=SplitConfig)
    candidate_models: list[CandidateModelConfig] = Field(min_length=1, max_length=10)
    feature_frame_version: int = Field(default=1, ge=1, le=2)
    feature_groups: list[str] | None = Field(default=None)
    ranking_policy: RankingPolicy = Field(default_factory=RankingPolicy)
    auto_train_winner: bool = Field(default=False)
    auto_predict: bool = Field(default=False)

    @model_validator(mode="after")
    def _check_consistency(self) -> ModelSelectionRunRequest:
        """Enforce LOCKED decisions #5 and #7 plus V1/feature-group consistency."""
        if self.split_config.horizon != self.forecast_horizon:
            raise ValueError(
                f"split_config.horizon ({self.split_config.horizon}) must equal "
                f"forecast_horizon ({self.forecast_horizon})"
            )
        if self.auto_predict and not self.auto_train_winner:
            raise ValueError("auto_predict requires auto_train_winner=True")
        if self.feature_frame_version == 1 and self.feature_groups is not None:
            raise ValueError(
                "feature_groups is only valid when feature_frame_version=2; "
                "omit it for V1 selection."
            )
        return self


class AvailabilityQuery(BaseModel):
    """Validated query params for ``GET /model-selection/availability``."""

    model_config = ConfigDict(strict=True)

    store_id: int = Field(..., ge=1)
    product_id: int = Field(..., ge=1)
    forecast_horizon: int = Field(default=14, ge=1, le=90)


# =============================================================================
# Intermediate models (service-internal; embedded in JSONB snapshots)
# =============================================================================


class FoldChart(BaseModel):
    """Per-fold chart points for one candidate."""

    fold_index: int
    dates: list[date]
    actuals: list[float]
    predictions: list[float]


class CandidateResult(BaseModel):
    """One candidate's full backtest outcome (success or failure).

    ``params`` are carried through unchanged so the winning model can be rebuilt
    from the persisted record without re-deriving them.
    """

    model_type: str
    params: dict[str, Any]
    failed: bool
    error: str | None = None
    aggregated_metrics: dict[str, float] | None = None
    sample_size: int = 0
    config_hash: str | None = None
    folds: list[FoldChart] = Field(default_factory=list)


class ModelRankEntry(BaseModel):
    """One row in the ranking table — a ranked winner/runner-up or an excluded
    (failed/filtered) candidate. Excluded entries keep ``rank=None``."""

    rank: int | None
    model_type: str
    params: dict[str, Any]
    included: bool
    exclusion_reason: str | None = None
    metrics: dict[str, float] | None = None


class RankingResult(BaseModel):
    """Deterministic ranking outcome — persisted into ``ranking_result``."""

    winner: ModelRankEntry | None
    entries: list[ModelRankEntry]
    confidence: ConfidenceLevel
    reasons: list[str]


class WinnerSummary(BaseModel):
    """The champion — flattened for the response top level."""

    model_type: str
    params: dict[str, Any]
    metrics: dict[str, float]
    rank: int


class ChartData(BaseModel):
    """Chart-ready comparison payload (a Success-Criteria deliverable)."""

    wape_by_model: dict[str, float]
    bias_by_model: dict[str, float]
    fold_stability: dict[str, list[float]]
    winner_actual_vs_predicted: list[FoldChart]


# =============================================================================
# Response models
# =============================================================================


class PairAvailabilityResponse(BaseModel):
    """``GET /model-selection/availability`` response."""

    store_id: int
    product_id: int
    first_sales_date: date | None
    last_sales_date: date | None
    observed_days: int
    expected_calendar_days: int
    coverage_ratio: float
    missing_days: int
    zero_sale_days: int
    promotion_days: int | None
    average_daily_demand: float
    status: AvailabilityStatus
    recommended_split_config: SplitConfig
    warnings: list[str] = Field(default_factory=list)


class ForecastSummary(BaseModel):
    """Forecast output rolled up for the response."""

    points: list[dict[str, Any]]
    total_demand: float
    average_demand: float
    horizon: int


class ModelSelectionRunResponse(BaseModel):
    """``POST /model-selection/run`` and ``GET /model-selection/{id}`` contract."""

    selection_id: str
    store_id: int
    product_id: int
    status: SelectionStatusLiteral
    selection_window: SelectionWindow
    forecast_horizon: int
    ranking_metric: str
    availability: PairAvailabilityResponse | None
    ranking: list[ModelRankEntry]
    winner: WinnerSummary | None
    recommendation_confidence: ConfidenceLevel | None
    confidence_reasons: list[str]
    chart_data: ChartData | None
    final_model: dict[str, Any] | None
    forecast: ForecastSummary | None
    business_summary: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class CandidateModelInfo(BaseModel):
    """One selectable forecasting model in the capability catalog.

    Output-only (plain ``BaseModel`` — no strict coercion needed). The
    capability flags are BACKEND-OWNED: they derive from the forecasting
    authority (``model_family_for`` + each forecaster's ``requires_features``)
    so the frontend never re-derives families/feature-awareness in TypeScript.
    """

    model_type: str
    label: str
    family: Literal["baseline", "tree", "additive"]
    feature_aware: bool
    requires_extra: bool  # lightgbm/xgboost — opt-in extra may be absent at runtime
    default_params: dict[str, Any]
    supports_auto_predict: bool  # False for feature-aware models (predict() rejects them)
    description: str


class ModelCatalogResponse(BaseModel):
    """``GET /model-selection/models`` — backend-owned candidate catalog."""

    models: list[CandidateModelInfo]
    default_candidate_model_types: list[str]


class TrainWinnerResponse(BaseModel):
    """``POST /model-selection/{id}/train-winner`` response."""

    selection_id: str
    model_type: str
    model_path: str


class PredictWinnerResponse(BaseModel):
    """``POST /model-selection/{id}/predict`` response."""

    selection_id: str
    forecast: ForecastSummary
