"""Pydantic schemas for the Scenario Simulation slice.

Two families of model live here:

* **Request bodies** — ``SimulateScenarioRequest``, ``CreateScenarioRequest`` and
  the ``*Assumption`` inputs. They carry ``ConfigDict(strict=True)`` to catch
  silent coercion bugs on JSON-native types, and every ``date`` field carries a
  ``Field(strict=False, ...)`` override so FastAPI's ``validate_python`` path
  still accepts ISO-string dates (see ``docs/_base/SECURITY.md`` — "Pydantic v2
  strict mode on FastAPI request bodies").
* **Responses** — ``ScenarioComparison``, ``ScenarioPlanResponse`` and the list
  models. They use ``ConfigDict(from_attributes=True)`` and deliberately do NOT
  set ``strict=True``.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# Promotion mechanics mirror data_platform.models.Promotion.kind.
PromotionKind = Literal["pct_off", "bogo", "bundle", "markdown"]
# Lifecycle stages a planner can force on the assumption form.
LifecycleStage = Literal["launch", "growth", "maturity", "decline"]
# Whether projected demand is covered by on-hand stock.
CoverageVerdict = Literal["covered", "at_risk", "stockout", "unknown"]


# =============================================================================
# Assumption inputs (request fragments)
# =============================================================================


class PriceAssumption(BaseModel):
    """A relative price change applied over a future date window."""

    model_config = ConfigDict(strict=True)

    change_pct: float = Field(
        ...,
        ge=-0.9,
        le=5.0,
        description="Relative price change as a fraction (-0.15 == 15% cheaper, "
        "0.10 == 10% dearer).",
    )
    start_date: date_type = Field(
        ...,
        strict=False,
        description="First day the price change is in effect (inclusive).",
    )
    end_date: date_type = Field(
        ...,
        strict=False,
        description="Last day the price change is in effect (inclusive).",
    )


class PromotionAssumption(BaseModel):
    """A promotion of a given kind running over a future date window."""

    model_config = ConfigDict(strict=True)

    kind: PromotionKind = Field(
        ...,
        description="Promotion mechanic: pct_off, bogo, bundle, or markdown.",
    )
    start_date: date_type = Field(
        ...,
        strict=False,
        description="First day the promotion runs (inclusive).",
    )
    end_date: date_type = Field(
        ...,
        strict=False,
        description="Last day the promotion runs (inclusive).",
    )


class HolidayAssumption(BaseModel):
    """Explicit holiday / event days that lift demand."""

    model_config = ConfigDict(strict=True)

    # ``strict=False`` on the outer Field satisfies the strict-mode policy
    # linter; the per-element ``Annotated[..., Field(strict=False)]`` is what
    # actually lets each ISO-string date coerce — field-level strict does NOT
    # propagate into list members.
    dates: list[Annotated[date_type, Field(strict=False)]] = Field(
        ...,
        strict=False,
        min_length=1,
        description="Calendar dates treated as holiday / event days.",
    )


class InventoryAssumption(BaseModel):
    """On-hand stock used only to derive a coverage verdict — never demand."""

    model_config = ConfigDict(strict=True)

    on_hand_units: int = Field(
        ...,
        ge=0,
        description="Units of stock on hand for the horizon. Caps coverage, not demand.",
    )


class LifecycleAssumption(BaseModel):
    """A forced product lifecycle stage for the whole horizon."""

    model_config = ConfigDict(strict=True)

    stage: LifecycleStage = Field(
        ...,
        description="Lifecycle stage override: launch, growth, maturity, or decline.",
    )


class ScenarioAssumptions(BaseModel):
    """The full set of optional what-if assumptions.

    Every field is optional — an empty ``ScenarioAssumptions`` is the "nothing
    changes" case and yields a scenario identical to the baseline.
    """

    model_config = ConfigDict(strict=True)

    price: PriceAssumption | None = Field(default=None, description="Price-change assumption.")
    promotion: PromotionAssumption | None = Field(default=None, description="Promotion assumption.")
    holiday: HolidayAssumption | None = Field(default=None, description="Holiday / event days.")
    inventory: InventoryAssumption | None = Field(
        default=None, description="On-hand stock for the coverage verdict."
    )
    lifecycle: LifecycleAssumption | None = Field(
        default=None, description="Lifecycle-stage override."
    )


# =============================================================================
# Request bodies
# =============================================================================


class SimulateScenarioRequest(BaseModel):
    """Request body for ``POST /scenarios/simulate`` (stateless)."""

    model_config = ConfigDict(strict=True)

    run_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Artifact key of a baseline model — the run_id stored on a "
        "completed predict/train job (model_{run_id}.joblib).",
    )
    horizon: int = Field(
        ...,
        ge=1,
        le=90,
        description="Number of days to simulate.",
    )
    assumptions: ScenarioAssumptions = Field(
        default_factory=ScenarioAssumptions,
        description="Optional what-if assumptions. Omit for a no-change baseline.",
    )
    name: str | None = Field(
        default=None,
        max_length=200,
        description="Optional label echoed back; suggested name when saving a plan.",
    )


class CreateScenarioRequest(BaseModel):
    """Request body for ``POST /scenarios`` — runs a simulation and persists it."""

    model_config = ConfigDict(strict=True)

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Human-readable name for the saved plan.",
    )
    run_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Artifact key of the baseline model.",
    )
    horizon: int = Field(
        ...,
        ge=1,
        le=90,
        description="Number of days to simulate.",
    )
    assumptions: ScenarioAssumptions = Field(
        default_factory=ScenarioAssumptions,
        description="What-if assumptions for this plan.",
    )


# =============================================================================
# Response models
# =============================================================================


class ScenarioPoint(BaseModel):
    """One horizon day: baseline vs. scenario demand and the factor applied."""

    model_config = ConfigDict(from_attributes=True)

    date: date_type = Field(..., description="Forecast date.")
    baseline: float = Field(..., description="Baseline forecast demand for the day.")
    scenario: float = Field(..., description="Scenario-adjusted demand for the day.")
    delta: float = Field(..., description="scenario minus baseline for the day.")
    applied_factor: float = Field(
        ...,
        description="Combined deterministic multiplier applied on the day (1.0 == no change).",
    )


class ScenarioComparison(BaseModel):
    """A full baseline-vs-scenario comparison for one (store, product) series."""

    model_config = ConfigDict(from_attributes=True)

    store_id: int = Field(..., description="Store the baseline model targets.")
    product_id: int = Field(..., description="Product the baseline model targets.")
    model_type: str = Field(..., description="Model type of the baseline artifact.")
    horizon: int = Field(..., ge=1, description="Number of days simulated.")
    points: list[ScenarioPoint] = Field(
        ...,
        description="Per-day baseline / scenario series; length equals horizon.",
    )
    baseline_total_units: float = Field(..., description="Summed baseline demand.")
    scenario_total_units: float = Field(..., description="Summed scenario demand.")
    units_delta: float = Field(..., description="scenario_total_units minus baseline_total_units.")
    units_delta_pct: float = Field(
        ...,
        description="units_delta as a percentage of baseline; 0.0 when baseline is 0.",
    )
    unit_price_used: float = Field(
        ...,
        description="Unit price used for the revenue estimate (most recent sale, "
        "or a documented fallback).",
    )
    baseline_revenue: float = Field(..., description="baseline_total_units * unit_price_used.")
    scenario_revenue: float = Field(..., description="scenario_total_units * unit_price_used.")
    revenue_delta: float = Field(..., description="scenario_revenue minus baseline_revenue.")
    coverage_verdict: CoverageVerdict = Field(
        ...,
        description="covered / at_risk / stockout, or unknown when no inventory "
        "assumption was supplied.",
    )
    method: Literal["heuristic"] = Field(
        ...,
        description="Always 'heuristic' — the result is a deterministic post-forecast "
        "multiplier, not a re-trained causal model.",
    )
    disclaimer: str = Field(
        ...,
        description="Plain-language caveat that the numbers are heuristic estimates.",
    )
    generated_at: datetime = Field(..., description="When the comparison was computed (UTC).")


class ScenarioPlanResponse(BaseModel):
    """A persisted scenario plan, including the embedded comparison snapshot."""

    model_config = ConfigDict(from_attributes=True)

    scenario_id: str = Field(..., description="Unique external identifier of the plan.")
    name: str = Field(..., description="Human-readable plan name.")
    store_id: int = Field(..., description="Store the plan targets.")
    product_id: int = Field(..., description="Product the plan targets.")
    run_id: str = Field(..., description="Artifact key of the baseline model.")
    horizon: int = Field(..., ge=1, description="Number of days simulated.")
    method: str = Field(..., description="Adjustment method — always 'heuristic'.")
    created_at: datetime = Field(..., description="When the plan was saved (UTC).")
    assumptions: ScenarioAssumptions = Field(
        ..., description="The raw what-if assumptions the plan was built from."
    )
    comparison: ScenarioComparison = Field(
        ..., description="The full baseline-vs-scenario snapshot, re-rendered without recompute."
    )


class ScenarioListItem(BaseModel):
    """A compact row in the saved-plans list."""

    model_config = ConfigDict(from_attributes=True)

    scenario_id: str = Field(..., description="Unique external identifier of the plan.")
    name: str = Field(..., description="Human-readable plan name.")
    store_id: int = Field(..., description="Store the plan targets.")
    product_id: int = Field(..., description="Product the plan targets.")
    horizon: int = Field(..., ge=1, description="Number of days simulated.")
    units_delta: float = Field(..., description="Summed scenario-minus-baseline demand.")
    revenue_delta: float = Field(..., description="Scenario-minus-baseline revenue.")
    created_at: datetime = Field(..., description="When the plan was saved (UTC).")


class ScenarioListResponse(BaseModel):
    """A page of saved scenario plans, newest first."""

    model_config = ConfigDict(from_attributes=True)

    scenarios: list[ScenarioListItem] = Field(
        ..., description="Saved plans for the current page; empty when none exist."
    )
    total: int = Field(..., ge=0, description="Total saved plans matching the query.")
