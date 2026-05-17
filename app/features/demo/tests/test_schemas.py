"""Unit tests for demo slice schemas."""

import pytest
from pydantic import ValidationError

from app.features.demo.schemas import DemoRunRequest, DemoRunResult, StepEvent


def test_demo_run_request_defaults():
    req = DemoRunRequest()
    assert req.seed == 42
    assert req.reset is False
    assert req.skip_seed is True


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


def test_demo_run_result_defaults():
    result = DemoRunResult(overall_status="pass")
    assert result.steps == []
    assert result.winner_model_type is None
    assert result.winner_wape is None
    assert result.wall_clock_s == 0.0
