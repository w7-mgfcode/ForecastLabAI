"""Tests for the ModelSelectionRun ORM model + status enum.

The status CHECK-constraint enforcement is exercised in the integration suite
(it requires the real Postgres CHECK); here we cover the enum values and the
in-Python ORM construction.
"""

from __future__ import annotations

from datetime import date

from app.features.model_selection.models import (
    TERMINAL_SELECTION_STATES,
    CandidateStatus,
    ModelSelectionCandidate,
    ModelSelectionRun,
    ModelSelectionStatus,
)


def test_status_enum_values() -> None:
    assert {s.value for s in ModelSelectionStatus} == {
        "pending",
        "running",
        "completed",
        "partial",
        "failed",
        "cancelled",
    }


def test_candidate_status_enum_values() -> None:
    assert {s.value for s in CandidateStatus} == {
        "pending",
        "running",
        "completed",
        "failed",
        "cancelled",
    }


def test_terminal_selection_states() -> None:
    assert TERMINAL_SELECTION_STATES == {"completed", "partial", "failed", "cancelled"}
    assert "running" not in TERMINAL_SELECTION_STATES
    assert "pending" not in TERMINAL_SELECTION_STATES


def test_model_selection_run_construction_defaults() -> None:
    row = ModelSelectionRun(
        selection_id="abc123",
        store_id=1,
        product_id=2,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 5, 31),
        forecast_horizon=14,
        ranking_metric="wape",
        status=ModelSelectionStatus.RUNNING.value,
        candidate_models=[{"model_type": "naive", "params": {}}],
        policy_snapshot={"minimum_sample_size": 0},
    )
    assert row.selection_id == "abc123"
    assert row.status == "running"
    assert row.winner_model_type is None
    assert row.final_model_path is None


def test_model_selection_candidate_construction() -> None:
    cand = ModelSelectionCandidate(
        candidate_id="cand1",
        selection_id="abc123",
        ordinal=0,
        model_type="naive",
        params={},
        status=CandidateStatus.PENDING.value,
    )
    assert cand.candidate_id == "cand1"
    assert cand.selection_id == "abc123"
    assert cand.status == "pending"
    assert cand.result is None
    assert cand.error_message is None
