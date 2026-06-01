"""Unit tests for the deterministic business-explanation layer."""

from __future__ import annotations

from app.features.model_selection.explanations import explain_winner
from app.features.model_selection.ranking import rank_candidates
from app.features.model_selection.schemas import RankingPolicy
from app.features.model_selection.tests.conftest import make_availability, make_candidate_result


def test_explain_winner_produces_deterministic_summary() -> None:
    results = [
        make_candidate_result("winner", wape=10.0),
        make_candidate_result("second", wape=20.0),
    ]
    ranking = rank_candidates(results, RankingPolicy(), "wape", availability_status="ready")
    summary = explain_winner(ranking, make_availability(status="ready"))

    assert "winner" in summary["headline"]
    assert summary["winner"]["model_type"] == "winner"
    assert summary["recommendation_confidence"] == ranking.confidence
    assert summary["confidence_reasons"] == ranking.reasons
    assert summary["comparison"]["runner_up_model_type"] == "second"
    assert any("coverage" in note.lower() for note in summary["data_notes"])
    assert summary["caveats"]


def test_explain_winner_is_deterministic() -> None:
    """Same input → byte-identical output (no LLM, no randomness)."""
    results = [
        make_candidate_result("winner", wape=10.0),
        make_candidate_result("second", wape=20.0),
    ]
    ranking = rank_candidates(results, RankingPolicy(), "wape", availability_status="ready")
    availability = make_availability(status="ready")
    assert explain_winner(ranking, availability) == explain_winner(ranking, availability)


def test_explain_winner_handles_no_winner() -> None:
    results = [make_candidate_result("x", failed=True, error="boom")]
    ranking = rank_candidates(results, RankingPolicy(), "wape")
    summary = explain_winner(ranking, make_availability(status="limited"))
    assert summary["winner"] is None
    assert "No model" in summary["headline"]
