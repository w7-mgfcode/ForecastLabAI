"""Pydantic schemas for the seeder feature."""

import datetime as _datetime_module
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.shared.seeder.config import default_seed_end_date, default_seed_start_date

VALID_CHANNELS: frozenset[str] = frozenset({"in_store", "online", "click_collect", "wholesale"})
"""Allow-list for ``sales_daily.channel`` — mirrors the SQL CHECK."""


class SeederStatus(BaseModel):
    """Current database state with row counts and metadata."""

    stores: int = Field(description="Number of store records")
    products: int = Field(description="Number of product records")
    calendar: int = Field(description="Number of calendar day records")
    sales: int = Field(description="Number of sales_daily records")
    inventory: int = Field(description="Number of inventory_snapshot_daily records")
    price_history: int = Field(description="Number of price_history records")
    promotions: int = Field(description="Number of promotion records")
    exogenous_signals: int = Field(
        default=0,
        description="Number of exogenous_signal records (Phase 1)",
    )
    sales_returns: int = Field(
        default=0,
        description="Number of sales_returns records (Phase 1)",
    )
    replenishment_events: int = Field(
        default=0,
        description="Number of replenishment_event records (Phase 2)",
    )
    date_range_start: date | None = Field(
        default=None,
        description="Earliest date in sales_daily",
    )
    date_range_end: date | None = Field(
        default=None,
        description="Latest date in sales_daily",
    )
    last_updated: datetime | None = Field(
        default=None,
        description="Timestamp of last data modification",
    )


class ChangepointEventParam(BaseModel):
    """API-facing representation of a demand changepoint (Phase 1)."""

    date: _datetime_module.date = Field(description="Changepoint impulse date")
    demand_multiplier: float = Field(
        ge=0.0,
        description="Peak multiplier on the changepoint date",
    )
    decay_days: int = Field(
        default=30,
        ge=0,
        le=3650,
        description="Exponential decay e-folding time (days). 0 = pure impulse.",
    )


class ScenarioInfo(BaseModel):
    """Information about a scenario preset."""

    name: str = Field(description="Scenario preset name")
    description: str = Field(description="Human-readable description")
    stores: int = Field(description="Default number of stores")
    products: int = Field(description="Default number of products")
    start_date: date = Field(description="Default start date")
    end_date: date = Field(description="Default end date")


class GenerateParams(BaseModel):
    """Parameters for generating a new dataset."""

    scenario: str = Field(
        default="retail_standard",
        description="Scenario preset name",
    )
    seed: int = Field(
        default=42,
        ge=0,
        description="Random seed for reproducibility",
    )
    stores: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of stores to generate",
    )
    products: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Number of products to generate",
    )
    start_date: date = Field(
        default_factory=default_seed_start_date,
        description="Start of date range (defaults to one year before today)",
    )
    end_date: date = Field(
        default_factory=default_seed_end_date,
        description="End of date range (defaults to today)",
    )
    sparsity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of missing store/product combinations",
    )
    dry_run: bool = Field(
        default=False,
        description="Preview only, do not execute",
    )

    # Phase 1 — realism extension. All flags default off so existing
    # scenarios remain byte-identical when this endpoint is called without
    # the new fields.
    enable_exogenous: bool = Field(
        default=False,
        description="Seed weather/macro/event exogenous signals (Phase 1)",
    )
    enable_returns: bool = Field(
        default=False,
        description="Seed sales_returns rows derived from sales (Phase 1)",
    )
    enable_substitution: bool = Field(
        default=False,
        description="Apply cross-product substitution lift on stockouts (Phase 1)",
    )
    yearly_seasonality_amplitude: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Yearly sin-wave demand amplitude (fraction). None or 0 = disabled. (Phase 1)"
        ),
    )
    weather_temperature_sensitivity: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
        description=(
            "Demand delta per °C above the climatology mean. "
            "Only applied when enable_exogenous=true. (Phase 1)"
        ),
    )
    changepoints: list[ChangepointEventParam] | None = Field(
        default=None,
        description="Optional list of demand changepoints (Phase 1)",
    )
    substitute_groups: list[list[int]] | None = Field(
        default=None,
        description=(
            "Optional list of product-ID groups whose members substitute for "
            "each other on stockout. Only applied when enable_substitution=true. "
            "(Phase 1)"
        ),
    )
    substitution_lift_on_stockout: float | None = Field(
        default=None,
        ge=0.0,
        le=10.0,
        description=(
            "Demand lift distributed across in-stock group-mates when a member "
            "is stocked out. Only applied when enable_substitution=true. (Phase 1)"
        ),
    )

    # Phase 2 — retail-depth extension. All flags default off so existing
    # scenarios stay byte-identical when the endpoint is called without
    # the new fields.
    enable_multichannel: bool = Field(
        default=False,
        description="Split sales across channels (in_store/online/...) (Phase 2)",
    )
    channel_mix: dict[str, float] | None = Field(
        default=None,
        description=(
            "Probability weights per channel. Keys must be a subset of "
            "{in_store, online, click_collect, wholesale}. Weights "
            "normalize at use time; at least one weight must be > 0. "
            "Only applied when enable_multichannel=true. (Phase 2)"
        ),
    )
    online_promo_uplift: float | None = Field(
        default=None,
        ge=0.0,
        le=10.0,
        description=(
            "Multiplier on online-channel quantity during promotions "
            "(e.g. 1.2 = +20%). Only applied when enable_multichannel=true. (Phase 2)"
        ),
    )
    online_substitution_to_instore: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of in-store demand that shifts to online during "
            "promotions (0.0 = independent; 1.0 = pure substitution). "
            "Only applied when enable_multichannel=true. (Phase 2)"
        ),
    )
    enable_lifecycle: bool = Field(
        default=False,
        description="Assign product lifecycle stage + launch/discontinue dates (Phase 2)",
    )
    lifecycle_discontinue_probability: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Probability a product gets a discontinue_date within the "
            "seeded range. Only applied when enable_lifecycle=true. (Phase 2)"
        ),
    )
    enable_bundles: bool = Field(
        default=False,
        description="Convert a fraction of promotions to bundle/BOGO (Phase 2)",
    )
    bundle_probability: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Per-promotion conversion probability. Only applied when enable_bundles=true. (Phase 2)"
        ),
    )
    enable_markdowns: bool = Field(
        default=False,
        description="Emit clearance markdown promos + price drops (Phase 2)",
    )
    markdown_trigger: Literal["lifecycle_decline", "stockout_risk"] | None = Field(
        default=None,
        description=(
            "Markdown firing rule. 'age_days' is deferred — see issue #94. "
            "Only applied when enable_markdowns=true. (Phase 2)"
        ),
    )
    enable_lead_time: bool = Field(
        default=False,
        description="Emit replenishment_event rows with stochastic lead times (Phase 2)",
    )
    mean_lead_time_days: int | None = Field(
        default=None,
        ge=0,
        le=365,
        description=(
            "Mean Normal-distributed lead time (days). Only applied when "
            "enable_lead_time=true. (Phase 2)"
        ),
    )

    @model_validator(mode="after")
    def _validate_date_range(self) -> "GenerateParams":
        """Reject inverted date ranges with a clear message."""
        if self.end_date < self.start_date:
            raise ValueError(
                f"end_date ({self.end_date}) must be on or after start_date ({self.start_date})"
            )
        return self

    @field_validator("channel_mix")
    @classmethod
    def _validate_channel_mix(
        cls,
        value: dict[str, float] | None,
    ) -> dict[str, float] | None:
        """Validate channel_mix keys, non-negativity, and positive total.

        Empty dict is rejected so callers must either pass None or a
        meaningful split. The full set of channels need not appear —
        unspecified channels get zero weight.
        """
        if value is None:
            return None
        if not value:
            raise ValueError(
                "channel_mix must not be empty when supplied; pass null to use defaults"
            )
        invalid = set(value.keys()) - VALID_CHANNELS
        if invalid:
            raise ValueError(
                f"channel_mix contains invalid channels {sorted(invalid)}; "
                f"allow-list is {sorted(VALID_CHANNELS)}"
            )
        for name, weight in value.items():
            if weight < 0:
                raise ValueError(f"channel_mix['{name}']={weight} must be non-negative")
        if sum(value.values()) <= 0:
            raise ValueError("channel_mix must have at least one positive weight")
        return value


class AppendParams(BaseModel):
    """Parameters for appending data to existing dataset."""

    start_date: date = Field(description="Start of new date range")
    end_date: date = Field(description="End of new date range")
    seed: int = Field(
        default=43,
        ge=0,
        description="Random seed for reproducibility",
    )


class DeleteParams(BaseModel):
    """Parameters for deleting data."""

    scope: Literal["all", "facts", "dimensions"] = Field(
        default="all",
        description="What to delete: all, facts (sales/inventory/etc), or dimensions (store/product/calendar)",
    )
    dry_run: bool = Field(
        default=False,
        description="Preview what would be deleted without executing",
    )


class GenerateResult(BaseModel):
    """Result of a generation or append operation."""

    success: bool = Field(description="Whether the operation succeeded")
    records_created: dict[str, int] = Field(
        description="Count of records created per table",
    )
    duration_seconds: float = Field(description="Time taken in seconds")
    message: str = Field(description="Human-readable result message")
    seed: int = Field(description="Random seed used")


class DeleteResult(BaseModel):
    """Result of a delete operation."""

    success: bool = Field(description="Whether the operation succeeded")
    records_deleted: dict[str, int] = Field(
        description="Count of records deleted per table",
    )
    message: str = Field(description="Human-readable result message")
    dry_run: bool = Field(description="Whether this was a preview only")


class VerifyCheck(BaseModel):
    """Single verification check result."""

    name: str = Field(description="Check name")
    status: Literal["passed", "warning", "failed"] = Field(
        description="Check status",
    )
    message: str = Field(description="Human-readable result")
    details: list[str] | None = Field(
        default=None,
        description="Additional details if applicable",
    )


class VerifyResult(BaseModel):
    """Result of data verification."""

    passed: bool = Field(description="Whether all critical checks passed")
    checks: list[VerifyCheck] = Field(description="Individual check results")
    total_checks: int = Field(description="Number of checks performed")
    passed_count: int = Field(description="Number of passed checks")
    warning_count: int = Field(description="Number of warnings")
    failed_count: int = Field(description="Number of failures")


# ============================================================================
# PHASE 1 — Exogenous signal read API
# ============================================================================


class ExogenousSignalRecord(BaseModel):
    """One row of the exogenous_signal table."""

    date: _datetime_module.date = Field(description="Signal date")
    signal_name: str = Field(description="Signal identifier")
    store_id: int | None = Field(
        default=None,
        description="Store ID. None for chain-wide (global) signals.",
    )
    is_global: bool = Field(description="True for chain-wide signals")
    value: float = Field(description="Numeric signal value")


class ExogenousSignalResponse(BaseModel):
    """Response payload for GET /seeder/exogenous."""

    signal_name: str = Field(description="Signal identifier queried")
    start_date: date = Field(description="Start of the query window")
    end_date: date = Field(description="End of the query window")
    store_id: int | None = Field(
        default=None,
        description="Specific store filter, if applied",
    )
    records: list[ExogenousSignalRecord] = Field(
        description="Signal rows in ascending date order",
    )
    total: int = Field(description="Row count in the response")


# ============================================================================
# PHASE 2 — Channels enumeration
# ============================================================================


class ChannelsResponse(BaseModel):
    """Response payload for GET /seeder/channels.

    Returns the SQL allow-list for ``sales_daily.channel`` so callers
    (admin UI, agent tools, integration tests) can populate selectors
    without duplicating the constant. Mirrors the SQL CHECK constraint.
    """

    channels: list[str] = Field(
        description=(
            "Sorted list of valid channel identifiers for sales_daily.channel "
            "and for ChannelConfig.channel_mix keys."
        ),
    )
    total: int = Field(description="Number of valid channels")


# ============================================================================
# PRP-38 — Phase 2 additive enrichment endpoint
# ============================================================================


class Phase2EnrichmentRequest(BaseModel):
    """Request body for POST /seeder/phase2-enrichment (PRP-38).

    Runs Phase 2 generators (lifecycle, replenishment, exogenous, returns)
    against the existing seeded dimensions + calendar. Every field is
    JSON-native, so ``ConfigDict(strict=True)`` is safe without
    ``Field(strict=False)`` overrides.
    """

    model_config = ConfigDict(strict=True)

    seed: int = Field(
        default=42,
        ge=0,
        description="Random seed for reproducible enrichment.",
    )
    returns_probability: float = Field(
        default=0.02,
        ge=0.0,
        le=1.0,
        description="Per-sale return probability (default ~2% of sales).",
    )
    discontinue_probability: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description=(
            "Probability a product gets a discontinue_date within the seeded "
            "range (lifecycle generator)."
        ),
    )


class Phase2EnrichmentResponse(BaseModel):
    """Response body for POST /seeder/phase2-enrichment (PRP-38)."""

    success: bool = Field(description="Whether the operation succeeded.")
    records_created: dict[str, int] = Field(
        description=(
            "Count of rows written/updated per table "
            "(product, replenishment_event, exogenous_signal, sales_returns)."
        ),
    )
    duration_ms: float = Field(description="Wall-clock duration in milliseconds.")
