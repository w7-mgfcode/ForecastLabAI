"""Pydantic schemas for the ForecastOps Control Center.

All models here are HTTP **response** models — they are built from aggregated
operational state, never parsed from a request body. They therefore use
``ConfigDict(from_attributes=True)`` and deliberately do NOT set
``strict=True`` (the strict-mode request-body policy does not apply).
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# System & freshness
# =============================================================================


class SystemHealth(BaseModel):
    """Liveness snapshot for the Control Center header."""

    model_config = ConfigDict(from_attributes=True)

    api_ok: bool = Field(
        ...,
        description="True whenever this response was produced (the API served the request).",
    )
    database_connected: bool = Field(
        ...,
        description="True when a 'SELECT 1' probe against PostgreSQL succeeded.",
    )
    latest_successful_job_at: datetime | None = Field(
        None,
        description="Completion timestamp of the most recent completed job. "
        "Null when no job has completed yet.",
    )


class DataFreshness(BaseModel):
    """How current the underlying data and model state are."""

    model_config = ConfigDict(from_attributes=True)

    latest_sales_date: date | None = Field(
        None,
        description="Most recent date present in sales_daily. Null when no sales exist.",
    )
    latest_job_completed_at: datetime | None = Field(
        None,
        description="Completion timestamp of the most recently finished job (any outcome).",
    )
    latest_run_completed_at: datetime | None = Field(
        None,
        description="Completion timestamp of the most recent successful model run.",
    )


# =============================================================================
# Job & run health
# =============================================================================


class StatusCount(BaseModel):
    """One row of a status histogram (e.g. how many jobs are 'failed')."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., description="The lifecycle status value.")
    count: int = Field(..., ge=0, description="Number of entities in that status.")


class JobHealth(BaseModel):
    """Aggregated job-execution health."""

    model_config = ConfigDict(from_attributes=True)

    counts: list[StatusCount] = Field(
        ...,
        description="One entry per JobStatus, zero-filled for statuses with no rows.",
    )
    completed_today: int = Field(
        ...,
        ge=0,
        description="Jobs that completed since 00:00 UTC today.",
    )
    failed_total: int = Field(..., ge=0, description="Total jobs in the 'failed' status.")
    active_total: int = Field(
        ...,
        ge=0,
        description="Jobs currently pending or running.",
    )


class RunHealth(BaseModel):
    """Aggregated model-run health."""

    model_config = ConfigDict(from_attributes=True)

    counts: list[StatusCount] = Field(
        ...,
        description="One entry per RunStatus, zero-filled for statuses with no rows.",
    )
    success_rate: float | None = Field(
        None,
        description="Successful runs divided by non-archived runs. "
        "Null when there are no non-archived runs.",
    )
    failed_total: int = Field(..., ge=0, description="Total runs in the 'failed' status.")


# =============================================================================
# Alias health
# =============================================================================


class AliasHealth(BaseModel):
    """Deployment-alias health, including a staleness verdict."""

    model_config = ConfigDict(from_attributes=True)

    alias_name: str = Field(..., description="The deployment alias name.")
    run_id: str = Field(..., description="External run_id of the aliased model run.")
    run_status: str = Field(..., description="Lifecycle status of the aliased run.")
    model_type: str = Field(..., description="Model type of the aliased run.")
    store_id: int = Field(..., description="Store the aliased run targets.")
    product_id: int = Field(..., description="Product the aliased run targets.")
    is_stale: bool = Field(
        ...,
        description="True when the alias points at a non-successful run, or a newer "
        "successful run exists for the same store/product.",
    )
    stale_reason: str | None = Field(
        None,
        description="Human-readable explanation when is_stale is true; null otherwise.",
    )
    wape: float | None = Field(
        None,
        description="WAPE of the aliased run, when present in its metrics; null otherwise.",
    )


# =============================================================================
# Attention items
# =============================================================================


class AttentionItem(BaseModel):
    """One entry in the 'needs attention' list."""

    model_config = ConfigDict(from_attributes=True)

    item_type: Literal["failed_job", "failed_run", "stale_alias"] = Field(
        ...,
        description="What kind of problem this row represents.",
    )
    entity_id: str = Field(
        ...,
        description="job_id for failed_job; run_id for failed_run and stale_alias. "
        "Used to deep-link to the matching Explorer detail page.",
    )
    label: str = Field(..., description="Short title for the row.")
    detail: str = Field(..., description="Longer explanation (error message or stale reason).")
    occurred_at: datetime | None = Field(
        None,
        description="When the entity was created. Null when unknown.",
    )


# =============================================================================
# Summary response
# =============================================================================


class OpsSummaryResponse(BaseModel):
    """Aggregated operational summary for the Control Center page."""

    model_config = ConfigDict(from_attributes=True)

    system: SystemHealth = Field(..., description="Liveness and connectivity.")
    jobs: JobHealth = Field(..., description="Job-execution health.")
    runs: RunHealth = Field(..., description="Model-run health.")
    aliases: list[AliasHealth] = Field(
        ...,
        description="Every deployment alias with its staleness verdict.",
    )
    freshness: DataFreshness = Field(..., description="How current data and models are.")
    attention_items: list[AttentionItem] = Field(
        ...,
        description="Recent failed jobs, failed runs, and stale aliases.",
    )
    generated_at: datetime = Field(..., description="When this summary was computed (UTC).")


# =============================================================================
# Retraining-candidate queue
# =============================================================================


class RetrainingCandidate(BaseModel):
    """One (store, product) pair ranked for retraining."""

    model_config = ConfigDict(from_attributes=True)

    store_id: int = Field(..., description="Store the candidate covers.")
    product_id: int = Field(..., description="Product the candidate covers.")
    priority_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Retraining-priority score in [0, 1]; higher means more urgent.",
    )
    staleness_days: int = Field(
        ...,
        ge=0,
        description="Days since the latest successful run's training-data window ended.",
    )
    wape: float | None = Field(
        None,
        description="WAPE of the latest successful run, when known; null otherwise.",
    )
    latest_run_id: str | None = Field(
        None,
        description="External run_id of the latest successful run for this grain.",
    )
    latest_run_status: str | None = Field(
        None,
        description="Status of that run (always 'success' for evaluated candidates).",
    )
    reason: str = Field(..., description="Human-readable rationale for the score.")


class RetrainingCandidatesResponse(BaseModel):
    """Ranked retraining-candidate queue."""

    model_config = ConfigDict(from_attributes=True)

    candidates: list[RetrainingCandidate] = Field(
        ...,
        description="Candidates sorted by priority_score (descending), capped at the limit.",
    )
    total_evaluated: int = Field(
        ...,
        ge=0,
        description="Total (store, product) grains evaluated before applying the limit.",
    )
    generated_at: datetime = Field(..., description="When this queue was computed (UTC).")


# =============================================================================
# Model health & drift
# =============================================================================


# Forecast-error trend verdict for a (store, product) grain.
DriftDirection = Literal["improving", "stable", "degrading", "unknown"]


class WapePoint(BaseModel):
    """One run's WAPE observation in a grain's chronological history."""

    model_config = ConfigDict(from_attributes=True)

    run_id: str = Field(..., description="External run_id of the observed run.")
    created_at: datetime = Field(..., description="When the run was created (UTC).")
    wape: float | None = Field(
        None,
        description="WAPE of the run, when present in its metrics; null otherwise.",
    )


class ModelHealthEntry(BaseModel):
    """Forecast-error health and drift verdict for one (store, product) grain."""

    model_config = ConfigDict(from_attributes=True)

    store_id: int = Field(..., description="Store the grain covers.")
    product_id: int = Field(..., description="Product the grain covers.")
    run_count: int = Field(
        ...,
        ge=0,
        description="Number of successful runs evaluated for this grain.",
    )
    latest_run_id: str | None = Field(
        None,
        description="External run_id of the most recent successful run.",
    )
    latest_run_status: str | None = Field(
        None,
        description="Status of that run (always 'success' for evaluated grains).",
    )
    latest_wape: float | None = Field(
        None,
        description="Most recent numeric WAPE in the grain's history; null when none.",
    )
    previous_wape: float | None = Field(
        None,
        description="The prior numeric WAPE, used as the drift baseline; null when none.",
    )
    wape_delta: float | None = Field(
        None,
        description="latest_wape minus previous_wape; null when fewer than two numeric WAPEs.",
    )
    drift_direction: DriftDirection = Field(
        ...,
        description="Forecast-error trend: improving / stable / degrading / unknown.",
    )
    last_trained_at: datetime | None = Field(
        None,
        description="created_at of the latest successful run; null when none.",
    )
    staleness_days: int = Field(
        ...,
        ge=0,
        description="Days since the latest run's training-data window ended.",
    )
    wape_history: list[WapePoint] = Field(
        ...,
        description="Chronological WAPE observations; may carry null gaps.",
    )


class ModelHealthResponse(BaseModel):
    """Per-grain forecast-error health, degrading grains first."""

    model_config = ConfigDict(from_attributes=True)

    entries: list[ModelHealthEntry] = Field(
        ...,
        description="Grains sorted degrading-first, then by |wape_delta| descending.",
    )
    total_evaluated: int = Field(
        ...,
        ge=0,
        description="Total grains evaluated before applying the limit.",
    )
    generated_at: datetime = Field(..., description="When this report was computed (UTC).")
