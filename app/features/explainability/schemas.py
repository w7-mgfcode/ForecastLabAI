"""Pydantic v2 schemas for the explainability slice.

The response schemas (``DriverContribution``, ``ReasonCode``,
``ForecastExplanation``) are plain ``BaseModel`` — NOT ``strict=True`` — so they
serialise cleanly. The single request body (``ExplainForecastRequest``) IS
``strict=True``; its ``as_of_date`` field therefore carries ``Field(strict=False)``
because ``date`` has no native JSON representation (see ``docs/_base/SECURITY.md``
-> "Pydantic v2 strict mode on FastAPI request bodies"; enforced by
``app/core/tests/test_strict_mode_policy.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_type
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Direction of a driver's influence on the forecast.
Direction = Literal["positive", "negative", "neutral"]

# Advisory retail reason-code identifiers — correlation signals, never causal claims.
ReasonCodeId = Literal[
    "stockout_constrained",
    "promotion_overlap",
    "holiday_effect",
    "lifecycle_decay",
    "trend_shift",
    "insufficient_history",
]

# Baseline model types this slice can explain. ``lightgbm``/``regression`` are
# rejected with a clean 400 (MVP scope guard).
ExplainableModelType = Literal[
    "naive",
    "seasonal_naive",
    "moving_average",
    # PRP-36 — new target-only baselines (always-on).
    "weighted_moving_average",
    "seasonal_average",
]


class ConfidenceLevel(str, Enum):
    """Qualitative confidence band for an explanation."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DriverContribution(BaseModel):
    """One named, interpretable demand driver behind a forecast.

    Attributes:
        name: Stable machine identifier for the driver.
        feature_value: The observed value of the underlying feature.
        contribution: Amount (in model units) this driver adds to the forecast.
            Informational/context drivers carry ``0.0``.
        direction: Sign of the driver's influence.
        description: Human-readable explanation of the driver.
    """

    name: str
    feature_value: float
    contribution: float
    direction: Direction
    description: str


class ReasonCode(BaseModel):
    """An advisory retail signal correlated with the forecast.

    CRITICAL: reason codes describe correlation, never business causality.

    Attributes:
        code: Machine-readable reason-code identifier.
        severity: ``info`` for context, ``warn`` for a quality caveat.
        detail: Human-readable detail for the signal.
    """

    code: ReasonCodeId
    severity: Literal["info", "warn"]
    detail: str


class ForecastExplanation(BaseModel):
    """Structured, rule-based explanation of a baseline h=1 forecast.

    Attributes:
        store_id: Store the forecast targets.
        product_id: Product the forecast targets.
        model_type: Baseline model type explained.
        method: Always ``rule_based`` for the MVP (``shap``/``component`` reserved).
        forecast_value: The h=1 forecast the baseline model produces.
        drivers: Ordered, named driver contributions.
        reason_codes: Advisory retail reason codes (correlation only).
        confidence: Qualitative confidence band.
        caveats: Plain-language caveats, always including the correlation-vs-
            causation disclaimer.
        agent_summary: One-paragraph natural-language summary for chat agents.
        as_of_date: Series cutoff — no data past this date informs the explanation.
        generated_at: UTC timestamp the explanation was produced.
    """

    model_config = ConfigDict(from_attributes=True)

    store_id: int
    product_id: int
    model_type: str
    method: Literal["rule_based"] = "rule_based"
    forecast_value: float
    drivers: list[DriverContribution]
    reason_codes: list[ReasonCode]
    confidence: ConfidenceLevel
    caveats: list[str]
    agent_summary: str
    as_of_date: date_type
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExplainForecastRequest(BaseModel):
    """Request body for ``POST /explain/forecast``.

    Attributes:
        store_id: Store ID to explain.
        product_id: Product ID to explain.
        model_type: Baseline model type to reproduce and explain.
        as_of_date: Series cutoff date — the explainer reads only ``<= as_of_date``.
        season_length: Seasonal period (``seasonal_naive`` only; defaults to 7).
        window_size: Averaging window (``moving_average`` only; defaults to 7).
    """

    model_config = ConfigDict(strict=True)

    store_id: int = Field(..., ge=1, description="Store ID")
    product_id: int = Field(..., ge=1, description="Product ID")
    model_type: ExplainableModelType = Field(..., description="Baseline model type")
    # ``date`` has no native JSON representation — ``strict=False`` lets FastAPI's
    # ``validate_python`` accept an ISO-string body. Repo-wide policy; see module
    # docstring.
    as_of_date: date_type = Field(
        ...,
        strict=False,
        description="Series cutoff date (the explainer reads only <= this date)",
    )
    season_length: int | None = Field(
        None, ge=1, le=365, description="Seasonal period for seasonal_naive / seasonal_average"
    )
    window_size: int | None = Field(
        None,
        ge=1,
        le=90,
        description="Averaging window for moving_average / weighted_moving_average",
    )
    # PRP-36 — weighted_moving_average + seasonal_average extras.
    weight_strategy: Literal["linear", "exponential"] | None = Field(
        None, description="Weighting scheme for weighted_moving_average (default 'linear')"
    )
    decay: float | None = Field(
        None,
        gt=0.0,
        lt=1.0,
        description="Geometric decay for weighted_moving_average exponential (default 0.7)",
    )
    lookback_cycles: int | None = Field(
        None,
        ge=2,
        le=12,
        description="Cycles to draw from for seasonal_average (default 4)",
    )
    trim_outliers: bool | None = Field(
        None,
        description="Drop min + max samples before averaging (seasonal_average only)",
    )
