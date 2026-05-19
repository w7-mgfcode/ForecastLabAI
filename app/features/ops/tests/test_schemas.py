"""Unit tests for the ops slice's Pydantic response schemas.

These run without a database (-m "not integration").
"""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.features.ops.schemas import (
    AliasHealth,
    AttentionItem,
    DataFreshness,
    JobHealth,
    ModelHealthEntry,
    ModelHealthResponse,
    OpsSummaryResponse,
    RetrainingCandidate,
    RetrainingCandidatesResponse,
    RunHealth,
    StatusCount,
    SystemHealth,
    WapePoint,
)

_NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


def test_system_health_construct() -> None:
    """SystemHealth carries liveness flags and an optional job timestamp."""
    system = SystemHealth(api_ok=True, database_connected=True, latest_successful_job_at=_NOW)
    assert system.api_ok is True
    assert system.latest_successful_job_at == _NOW


def test_system_health_allows_null_job_timestamp() -> None:
    """latest_successful_job_at defaults to None when no job has completed."""
    system = SystemHealth(api_ok=True, database_connected=False)
    assert system.latest_successful_job_at is None


def test_status_count_rejects_negative_count() -> None:
    """A negative count violates the ge=0 constraint."""
    with pytest.raises(ValidationError):
        StatusCount(status="failed", count=-1)


def test_job_health_construct_and_reject_negative() -> None:
    """JobHealth aggregates counts; negative totals are rejected."""
    health = JobHealth(
        counts=[StatusCount(status="completed", count=3)],
        completed_today=2,
        failed_total=1,
        active_total=0,
    )
    assert health.completed_today == 2
    with pytest.raises(ValidationError):
        JobHealth(counts=[], completed_today=-1, failed_total=0, active_total=0)


def test_run_health_allows_null_success_rate() -> None:
    """success_rate is None when there are no eligible runs."""
    health = RunHealth(counts=[], success_rate=None, failed_total=0)
    assert health.success_rate is None


def test_alias_health_construct() -> None:
    """AliasHealth carries the staleness verdict and an optional WAPE."""
    alias = AliasHealth(
        alias_name="production",
        run_id="abc123",
        run_status="success",
        model_type="naive",
        store_id=1,
        product_id=2,
        is_stale=True,
        stale_reason="a newer successful run exists for this store/product",
        wape=18.4,
    )
    assert alias.is_stale is True
    assert alias.wape == 18.4


def test_data_freshness_defaults_to_null() -> None:
    """Every freshness field is optional and defaults to None."""
    freshness = DataFreshness()
    assert freshness.latest_sales_date is None
    assert freshness.latest_job_completed_at is None
    assert freshness.latest_run_completed_at is None


def test_attention_item_rejects_unknown_type() -> None:
    """item_type is constrained to the three known literals."""
    with pytest.raises(ValidationError):
        AttentionItem(
            item_type="something_else",  # type: ignore[arg-type]
            entity_id="x",
            label="x",
            detail="x",
        )


def test_attention_item_construct() -> None:
    """A valid AttentionItem accepts the known literals."""
    item = AttentionItem(
        item_type="failed_job",
        entity_id="job-1",
        label="train job failed",
        detail="boom",
        occurred_at=_NOW,
    )
    assert item.item_type == "failed_job"


def test_ops_summary_response_construct() -> None:
    """OpsSummaryResponse nests every section."""
    summary = OpsSummaryResponse(
        system=SystemHealth(api_ok=True, database_connected=True),
        jobs=JobHealth(counts=[], completed_today=0, failed_total=0, active_total=0),
        runs=RunHealth(counts=[], success_rate=None, failed_total=0),
        aliases=[],
        freshness=DataFreshness(),
        attention_items=[],
        generated_at=_NOW,
    )
    assert summary.generated_at == _NOW
    assert summary.aliases == []


def test_retraining_candidate_rejects_out_of_range_score() -> None:
    """priority_score is bounded to [0.0, 1.0]."""
    with pytest.raises(ValidationError):
        RetrainingCandidate(
            store_id=1,
            product_id=2,
            priority_score=1.5,
            staleness_days=10,
            wape=None,
            latest_run_id="r1",
            latest_run_status="success",
            reason="x",
        )


def test_retraining_candidate_rejects_negative_staleness() -> None:
    """staleness_days violates ge=0 when negative."""
    with pytest.raises(ValidationError):
        RetrainingCandidate(
            store_id=1,
            product_id=2,
            priority_score=0.5,
            staleness_days=-1,
            wape=None,
            latest_run_id="r1",
            latest_run_status="success",
            reason="x",
        )


def test_retraining_candidates_response_construct() -> None:
    """RetrainingCandidatesResponse wraps candidates with a total and timestamp."""
    candidate = RetrainingCandidate(
        store_id=1,
        product_id=2,
        priority_score=0.75,
        staleness_days=30,
        wape=12.0,
        latest_run_id="r1",
        latest_run_status="success",
        reason="30d since last training window; WAPE 12.0",
    )
    response = RetrainingCandidatesResponse(
        candidates=[candidate],
        total_evaluated=1,
        generated_at=_NOW,
    )
    assert response.total_evaluated == 1
    assert response.candidates[0].priority_score == 0.75


def test_data_freshness_accepts_date() -> None:
    """latest_sales_date accepts a date value."""
    freshness = DataFreshness(latest_sales_date=date(2026, 5, 1))
    assert freshness.latest_sales_date == date(2026, 5, 1)


# =============================================================================
# Model health & drift
# =============================================================================


def test_wape_point_construct() -> None:
    """WapePoint carries a run_id, timestamp, and an optional WAPE."""
    point = WapePoint(run_id="r1", created_at=_NOW, wape=14.0)
    assert point.wape == 14.0
    null_point = WapePoint(run_id="r2", created_at=_NOW)
    assert null_point.wape is None


def test_model_health_entry_construct() -> None:
    """A valid ModelHealthEntry accepts a known drift direction and history."""
    entry = ModelHealthEntry(
        store_id=1,
        product_id=2,
        run_count=3,
        latest_run_id="r3",
        latest_run_status="success",
        latest_wape=25.0,
        previous_wape=11.0,
        wape_delta=14.0,
        drift_direction="degrading",
        last_trained_at=_NOW,
        staleness_days=30,
        wape_history=[WapePoint(run_id="r3", created_at=_NOW, wape=25.0)],
    )
    assert entry.drift_direction == "degrading"
    assert entry.wape_delta == 14.0


def test_model_health_entry_rejects_negative_run_count() -> None:
    """run_count violates the ge=0 constraint when negative."""
    with pytest.raises(ValidationError):
        ModelHealthEntry(
            store_id=1,
            product_id=2,
            run_count=-1,
            drift_direction="unknown",
            staleness_days=0,
            wape_history=[],
        )


def test_model_health_entry_rejects_negative_staleness() -> None:
    """staleness_days violates the ge=0 constraint when negative."""
    with pytest.raises(ValidationError):
        ModelHealthEntry(
            store_id=1,
            product_id=2,
            run_count=0,
            drift_direction="unknown",
            staleness_days=-1,
            wape_history=[],
        )


def test_model_health_entry_rejects_unknown_drift_direction() -> None:
    """drift_direction is constrained to the four known literals."""
    with pytest.raises(ValidationError):
        ModelHealthEntry(
            store_id=1,
            product_id=2,
            run_count=0,
            drift_direction="exploding",  # type: ignore[arg-type]
            staleness_days=0,
            wape_history=[],
        )


def test_model_health_response_construct() -> None:
    """ModelHealthResponse wraps entries with a total and timestamp."""
    entry = ModelHealthEntry(
        store_id=1,
        product_id=2,
        run_count=2,
        drift_direction="stable",
        staleness_days=5,
        wape_history=[],
    )
    response = ModelHealthResponse(entries=[entry], total_evaluated=1, generated_at=_NOW)
    assert response.total_evaluated == 1
    assert response.entries[0].drift_direction == "stable"
