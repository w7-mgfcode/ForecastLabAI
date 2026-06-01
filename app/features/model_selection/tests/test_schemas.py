"""Unit tests for model_selection request schemas (strict mode + validators)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.features.model_selection.schemas import (
    CandidateProgress,
    ModelSelectionRunRequest,
    ModelSelectionRunResponse,
    SelectionProgress,
    SelectionWindow,
    SubmitRunResponse,
)


def _base_request_dict(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "store_id": 1,
        "product_id": 1,
        "selection_window": {"start_date": "2026-01-01", "end_date": "2026-05-31"},
        "forecast_horizon": 14,
        "split_config": {
            "strategy": "expanding",
            "n_splits": 5,
            "min_train_size": 30,
            "gap": 0,
            "horizon": 14,
        },
        "candidate_models": [{"model_type": "naive", "params": {}}],
    }
    payload.update(overrides)
    return payload


def test_schema_accepts_iso_dates_under_strict_model() -> None:
    """ISO-string dates validate through the strict ``validate_python`` path."""
    window = SelectionWindow.model_validate({"start_date": "2026-01-01", "end_date": "2026-02-01"})
    assert window.start_date.isoformat() == "2026-01-01"

    request = ModelSelectionRunRequest.model_validate(_base_request_dict())
    assert request.selection_window.end_date.isoformat() == "2026-05-31"


def test_schema_rejects_auto_predict_without_train_winner() -> None:
    """LOCKED #7 — auto_predict requires auto_train_winner."""
    with pytest.raises(ValidationError, match="auto_predict requires auto_train_winner"):
        ModelSelectionRunRequest.model_validate(
            _base_request_dict(auto_predict=True, auto_train_winner=False)
        )


def test_schema_rejects_horizon_mismatch_between_split_and_forecast() -> None:
    """LOCKED #5 — split_config.horizon must equal forecast_horizon."""
    bad = _base_request_dict(forecast_horizon=14)
    bad["split_config"] = {
        "strategy": "expanding",
        "n_splits": 5,
        "min_train_size": 30,
        "gap": 0,
        "horizon": 7,
    }
    with pytest.raises(ValidationError, match="must equal"):
        ModelSelectionRunRequest.model_validate(bad)


def test_schema_rejects_feature_groups_with_v1() -> None:
    """V1 must not carry feature_groups (mirrors forecasting TrainRequest)."""
    with pytest.raises(ValidationError, match="feature_groups is only valid"):
        ModelSelectionRunRequest.model_validate(
            _base_request_dict(feature_frame_version=1, feature_groups=["calendar"])
        )


def test_selection_window_rejects_inverted_range() -> None:
    """An end <= start window is rejected."""
    with pytest.raises(ValidationError, match="after start_date"):
        SelectionWindow.model_validate({"start_date": "2026-02-01", "end_date": "2026-01-01"})


def test_candidate_models_min_length_enforced() -> None:
    """At least one candidate is required."""
    with pytest.raises(ValidationError):
        ModelSelectionRunRequest.model_validate(_base_request_dict(candidate_models=[]))


# --------------------------------------------------------------------- Slice B


def _base_response_dict(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "selection_id": "sel1",
        "store_id": 1,
        "product_id": 2,
        "status": "running",
        "selection_window": {"start_date": "2026-01-01", "end_date": "2026-05-31"},
        "forecast_horizon": 14,
        "ranking_metric": "wape",
        "availability": None,
        "ranking": [],
        "winner": None,
        "recommendation_confidence": None,
        "confidence_reasons": [],
        "chart_data": None,
        "final_model": None,
        "forecast": None,
        "business_summary": None,
        "error_message": None,
        "created_at": datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
        "completed_at": None,
    }
    payload.update(overrides)
    return payload


def test_response_progress_fields_default_safely() -> None:
    """Legacy sync-run rows validate without progress fields (additive defaults)."""
    resp = ModelSelectionRunResponse.model_validate(_base_response_dict())
    assert resp.started_at is None
    assert resp.progress is None
    assert resp.candidate_progress == []


def test_status_literal_accepts_cancelled() -> None:
    """The 'cancelled' status (Slice B) is accepted by the response literal."""
    resp = ModelSelectionRunResponse.model_validate(_base_response_dict(status="cancelled"))
    assert resp.status == "cancelled"


def test_selection_and_candidate_progress_models() -> None:
    progress = SelectionProgress(total=5, pending=3, running=1, completed=1, failed=0, cancelled=0)
    assert progress.total == 5
    cand = CandidateProgress(candidate_id="c1", ordinal=0, model_type="naive", status="running")
    assert cand.status == "running"
    assert cand.error is None


def test_submit_run_response_carries_monitor_and_cancel_urls() -> None:
    submit = SubmitRunResponse.model_validate(
        _base_response_dict(
            monitor_url="/model-selection/sel1",
            cancel_url="/model-selection/sel1",
            progress={
                "total": 1,
                "pending": 1,
                "running": 0,
                "completed": 0,
                "failed": 0,
                "cancelled": 0,
            },
            candidate_progress=[
                {"candidate_id": "c1", "ordinal": 0, "model_type": "naive", "status": "pending"}
            ],
        )
    )
    assert submit.monitor_url == "/model-selection/sel1"
    assert submit.cancel_url == "/model-selection/sel1"
    assert submit.progress is not None
    assert submit.progress.pending == 1
    assert submit.candidate_progress[0].model_type == "naive"


# =============================================================================
# Slice C — decision + promotion schemas
# =============================================================================

from app.features.model_selection.schemas import (  # noqa: E402
    ForecastDecisionParams,
    ForecastSummary,
    PredictWinnerResponse,
    PromoteRequest,
    TrainSelectedRequest,
    TrainWinnerResponse,
)


def test_train_selected_request_accepts_model_type() -> None:
    req = TrainSelectedRequest.model_validate(
        {"model_type": "seasonal_naive", "override_reason": "domain"}
    )
    assert req.model_type == "seasonal_naive"
    assert req.override_reason == "domain"


def test_train_selected_request_rejects_unknown_model_type() -> None:
    with pytest.raises(ValidationError):
        TrainSelectedRequest.model_validate({"model_type": "not_a_model"})


def test_forecast_decision_params_defaults() -> None:
    params = ForecastDecisionParams()
    assert params.lead_time_days == 7
    assert params.service_level == 0.95


@pytest.mark.parametrize("service_level", [0.49, 1.0, 1.5])
def test_forecast_decision_params_rejects_out_of_bound_service_level(service_level: float) -> None:
    with pytest.raises(ValidationError):
        ForecastDecisionParams.model_validate({"service_level": service_level})


def test_forecast_decision_params_validate_python_path() -> None:
    """Exercise the validate_python path (matches FastAPI's body coercion)."""
    params = ForecastDecisionParams.model_validate({"lead_time_days": 14, "service_level": 0.99})
    assert params.lead_time_days == 14


@pytest.mark.parametrize("alias", ["Bad Alias", "UPPER", "-leading", "has space"])
def test_promote_request_rejects_bad_alias_name(alias: str) -> None:
    with pytest.raises(ValidationError):
        PromoteRequest.model_validate({"alias_name": alias, "approved_by": "gabor"})


def test_promote_request_accepts_valid_alias_and_defaults() -> None:
    req = PromoteRequest.model_validate({"alias_name": "champion-store5", "approved_by": "gabor"})
    assert req.alias_name == "champion-store5"
    assert req.acknowledge_non_recommended is False
    assert req.description is None


def test_promote_request_requires_approved_by() -> None:
    with pytest.raises(ValidationError):
        PromoteRequest.model_validate({"alias_name": "champion-x"})


def test_train_winner_response_back_compat_defaults() -> None:
    """train-winner callers that omit the Slice C fields still validate."""
    resp = TrainWinnerResponse.model_validate(
        {"selection_id": "s", "model_type": "naive", "model_path": "p"}
    )
    assert resp.is_override is False
    assert resp.override_warning is None


def test_forecast_summary_peak_low_optional() -> None:
    """Legacy ForecastSummary (no peak/low) still validates."""
    summary = ForecastSummary.model_validate(
        {"points": [], "total_demand": 0.0, "average_demand": 0.0, "horizon": 14}
    )
    assert summary.peak_date is None
    assert summary.peak_demand is None


def test_predict_winner_response_decision_optional() -> None:
    resp = PredictWinnerResponse.model_validate(
        {
            "selection_id": "s",
            "forecast": {"points": [], "total_demand": 0.0, "average_demand": 0.0, "horizon": 14},
        }
    )
    assert resp.decision is None
