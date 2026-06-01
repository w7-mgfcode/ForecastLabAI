"""Unit tests for model_selection request schemas (strict mode + validators)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.features.model_selection.schemas import (
    ModelSelectionRunRequest,
    SelectionWindow,
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
