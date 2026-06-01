"""Deterministic business-explanation layer for the champion selector (#353).

Pure functions — NO LLM, NO external call. Translates the numeric ranking +
availability into short, deterministic English a business user can read. The
output dict is persisted into ``model_selection_run.business_summary`` and
echoed on the response.
"""

from __future__ import annotations

from typing import Any

from app.features.model_selection.schemas import PairAvailabilityResponse, RankingResult


def _metric_phrase(metrics: dict[str, float] | None) -> str:
    """One-line plain-English metric summary for a ranked model."""
    if not metrics:
        return "no metrics available"
    return (
        f"WAPE {metrics['wape']:.1f}%, sMAPE {metrics['smape']:.1f}, "
        f"MAE {metrics['mae']:.2f}, bias {metrics['bias']:.2f}"
    )


def explain_winner(
    ranking: RankingResult,
    availability: PairAvailabilityResponse | None,
) -> dict[str, Any]:
    """Build the deterministic ``business_summary`` payload.

    Always returns a dict; when there is no winner the summary explains why no
    model could be recommended.
    """
    caveats = [
        "Backtest accuracy reflects historical fit, not a guarantee of future performance.",
        "Metrics measure correlation with past demand, not causation.",
    ]

    if availability is not None:
        data_notes = [
            f"Observed {availability.observed_days} of "
            f"{availability.expected_calendar_days} calendar days "
            f"({availability.coverage_ratio:.0%} coverage).",
            f"Average daily demand {availability.average_daily_demand:.2f}.",
        ]
        data_notes.extend(availability.warnings)
    else:
        data_notes = ["No availability snapshot was computed."]

    if ranking.winner is None:
        return {
            "headline": "No model could be recommended for this pair.",
            "winner": None,
            "recommendation_confidence": ranking.confidence,
            "confidence_reasons": ranking.reasons,
            "comparison": None,
            "data_notes": data_notes,
            "caveats": caveats,
        }

    winner = ranking.winner
    headline = f"Recommended model: {winner.model_type} ({ranking.confidence} confidence)."

    included = [e for e in ranking.entries if e.included]
    runner_up = included[1] if len(included) > 1 else None
    if runner_up is not None and runner_up.metrics and winner.metrics:
        runner_wape = runner_up.metrics["wape"]
        if runner_wape > 0:
            lead = (runner_wape - winner.metrics["wape"]) / runner_wape
            lead_text = f"{lead:.1%} lower WAPE than the runner-up ({runner_up.model_type})"
        else:
            lead_text = f"a comparable WAPE to the runner-up ({runner_up.model_type})"
        comparison: dict[str, Any] = {
            "runner_up_model_type": runner_up.model_type,
            "runner_up_summary": _metric_phrase(runner_up.metrics),
            "lead_text": lead_text,
        }
    else:
        comparison = {
            "runner_up_model_type": None,
            "runner_up_summary": None,
            "lead_text": "no runner-up was available for comparison",
        }

    return {
        "headline": headline,
        "winner": {
            "model_type": winner.model_type,
            "summary": _metric_phrase(winner.metrics),
        },
        "recommendation_confidence": ranking.confidence,
        "confidence_reasons": ranking.reasons,
        "comparison": comparison,
        "data_notes": data_notes,
        "caveats": caveats,
    }
