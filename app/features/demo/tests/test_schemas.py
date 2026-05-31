"""Unit tests for demo slice schemas."""

import pytest
from pydantic import ValidationError

from app.features.demo.schemas import DemoRunRequest, DemoRunResult, StepEvent
from app.shared.seeder.config import ScenarioPreset


def test_demo_run_request_defaults():
    req = DemoRunRequest()
    assert req.seed == 42
    assert req.reset is False
    assert req.skip_seed is True
    # PRP-38 — default scenario preserves legacy demo_minimal behaviour.
    assert req.scenario is ScenarioPreset.DEMO_MINIMAL


def test_demo_run_request_negative_seed_rejected():
    with pytest.raises(ValidationError):
        DemoRunRequest(seed=-1)


def test_demo_run_request_strict_rejects_string_seed():
    # ConfigDict(strict=True): a JSON string is not coerced to int (the
    # validate_python path FastAPI uses). Catches subtle coercion bugs.
    with pytest.raises(ValidationError):
        DemoRunRequest.model_validate({"seed": "5"})


def test_demo_run_request_accepts_overrides():
    req = DemoRunRequest.model_validate({"seed": 7, "reset": True, "skip_seed": False})
    assert req.seed == 7
    assert req.reset is True
    assert req.skip_seed is False


def test_demo_run_request_scenario_showcase_rich():
    """PRP-38 — the JSON wire form accepts the new SHOWCASE_RICH preset."""
    req = DemoRunRequest.model_validate({"scenario": "showcase_rich"})
    assert req.scenario is ScenarioPreset.SHOWCASE_RICH


def test_demo_run_request_scenario_rejects_unknown():
    """PRP-38 — unknown scenarios are rejected by Pydantic (strict + enum)."""
    with pytest.raises(ValidationError):
        DemoRunRequest.model_validate({"scenario": "not_a_preset"})


def test_step_event_json_round_trip():
    event = StepEvent(
        event_type="step_complete",
        step_name="train",
        step_index=6,
        total_steps=11,
        status="pass",
        detail="trained 3 models",
        duration_ms=123.4,
        data={"trained": ["naive", "seasonal_naive"]},
    )
    dumped = event.model_dump(mode="json")
    # timestamp must serialize to an ISO string on the wire (matches send_json).
    assert isinstance(dumped["timestamp"], str)
    assert dumped["event_type"] == "step_complete"
    assert dumped["status"] == "pass"

    restored = StepEvent.model_validate(dumped)
    assert restored.step_name == "train"
    assert restored.data == {"trained": ["naive", "seasonal_naive"]}


def test_step_event_status_optional_on_start():
    event = StepEvent(
        event_type="step_start",
        step_name="seed",
        step_index=3,
        total_steps=11,
    )
    assert event.status is None
    assert event.detail == ""
    assert event.data == {}
    # PRP-38 — new Optional phase fields default to None (legacy back-compat).
    assert event.phase_name is None
    assert event.phase_index is None
    assert event.phase_total is None


def test_step_event_phase_fields_round_trip():
    """PRP-38 — phase fields ride alongside existing event fields on the wire."""
    event = StepEvent(
        event_type="step_complete",
        step_name="v2_train",
        step_index=9,
        total_steps=14,
        status="pass",
        phase_name="modeling",
        phase_index=2,
        phase_total=6,
    )
    dumped = event.model_dump(mode="json")
    assert dumped["phase_name"] == "modeling"
    assert dumped["phase_index"] == 2
    assert dumped["phase_total"] == 6

    restored = StepEvent.model_validate(dumped)
    assert restored.phase_name == "modeling"
    assert restored.phase_index == 2
    assert restored.phase_total == 6


def test_step_event_legacy_payload_validates_without_phase_fields():
    """PRP-38 — a legacy wire payload without phase_* still validates (back-compat)."""
    restored = StepEvent.model_validate(
        {
            "event_type": "step_complete",
            "step_name": "train",
            "step_index": 6,
            "total_steps": 11,
            "status": "pass",
            "detail": "",
            "duration_ms": 0.0,
            "data": {},
            "timestamp": "2026-05-26T12:00:00+00:00",
        }
    )
    assert restored.phase_name is None
    assert restored.phase_index is None
    assert restored.phase_total is None


def test_demo_run_result_defaults():
    result = DemoRunResult(overall_status="pass")
    assert result.steps == []
    assert result.winner_model_type is None
    assert result.winner_wape is None
    assert result.wall_clock_s == 0.0
