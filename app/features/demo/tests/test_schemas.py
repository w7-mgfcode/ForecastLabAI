"""Unit tests for demo slice schemas."""

import datetime as _dt
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.features.demo.schemas import (
    DemoRunRequest,
    DemoRunResult,
    StepEvent,
    WorkspaceDetailResponse,
    WorkspaceListItem,
    WorkspaceListResponse,
)
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


def test_demo_run_request_new_field_defaults():
    """E1 (#390) -- defaults preserve legacy behaviour (ephemeral, unnamed)."""
    req = DemoRunRequest()
    assert req.preservation == "ephemeral"
    assert req.workspace_name is None


def test_demo_run_request_json_path_keep_with_name():
    """E1 (#390) -- the JSON wire form (validate_python on a parsed dict, the
    path FastAPI uses) accepts keep + a named workspace."""
    req = DemoRunRequest.model_validate({"preservation": "keep", "workspace_name": "bf-demo"})
    assert req.preservation == "keep"
    assert req.workspace_name == "bf-demo"


def test_demo_run_request_legacy_frame_still_validates():
    """E1 (#390) -- a legacy start frame without the new keys still validates."""
    req = DemoRunRequest.model_validate({"seed": 7})
    assert req.seed == 7
    assert req.preservation == "ephemeral"
    assert req.workspace_name is None


def test_demo_run_request_workspace_name_requires_keep():
    """E1 (#390) -- workspace_name without preservation='keep' is rejected."""
    with pytest.raises(ValidationError):
        DemoRunRequest.model_validate({"workspace_name": "x"})
    with pytest.raises(ValidationError):
        DemoRunRequest.model_validate({"preservation": "ephemeral", "workspace_name": "x"})


def test_demo_run_request_workspace_name_pattern_rejected():
    """E1 (#390) -- names violating the alias-style pattern are rejected."""
    with pytest.raises(ValidationError):
        DemoRunRequest.model_validate({"preservation": "keep", "workspace_name": "Black Friday!"})
    with pytest.raises(ValidationError):
        DemoRunRequest.model_validate({"preservation": "keep", "workspace_name": "-leading-dash"})


def test_demo_run_request_rejects_unknown_preservation():
    """E1 (#390) -- preservation is a closed Literal; unknown values 422."""
    with pytest.raises(ValidationError):
        DemoRunRequest.model_validate({"preservation": "archive"})


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
    # E1 (#390) -- additive Optional field defaults to None (ephemeral runs).
    assert result.workspace_id is None


# =============================================================================
# E4 (#393) -- workspace response models
# =============================================================================


def _orm_like_workspace_row(**overrides: object) -> SimpleNamespace:
    """An ORM-shaped stand-in for a ShowcaseWorkspace row (from_attributes)."""
    base: dict[str, object] = {
        "workspace_id": "a" * 32,
        "name": "e4-demo",
        "status": "completed",
        "seed": 42,
        "scenario": "demo_minimal",
        "reset": False,
        "skip_seed": True,
        "store_id": 3,
        "product_id": 7,
        "date_start": _dt.date(2026, 1, 1),
        "date_end": _dt.date(2026, 3, 31),
        "created_objects": {"winning_run_id": "run-abc", "scenario_plan_ids": ["sp-1"]},
        "result_summary": {"winner_model_type": "naive", "winner_wape": 0.2},
        "created_at": _dt.datetime(2026, 6, 1, 12, 0, tzinfo=_dt.UTC),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_workspace_list_item_from_attributes_round_trip():
    """E4 (#393) -- list item builds from an ORM-shaped row."""
    item = WorkspaceListItem.model_validate(_orm_like_workspace_row())
    assert item.workspace_id == "a" * 32
    assert item.name == "e4-demo"
    assert item.status == "completed"
    assert item.seed == 42
    assert item.scenario == "demo_minimal"
    assert item.reset is False
    assert item.skip_seed is True
    assert item.result_summary == {"winner_model_type": "naive", "winner_wape": 0.2}


def test_workspace_detail_carries_created_objects_verbatim():
    """E4 (#393) -- detail model passes created_objects + grain through untouched."""
    detail = WorkspaceDetailResponse.model_validate(_orm_like_workspace_row())
    assert detail.created_objects == {
        "winning_run_id": "run-abc",
        "scenario_plan_ids": ["sp-1"],
    }
    assert detail.store_id == 3
    assert detail.product_id == 7
    assert detail.date_start == _dt.date(2026, 1, 1)
    assert detail.date_end == _dt.date(2026, 3, 31)


def test_workspace_detail_tolerates_running_row_nulls():
    """E4 (#393) -- a still-running row (NULL grain/summary) validates."""
    detail = WorkspaceDetailResponse.model_validate(
        _orm_like_workspace_row(
            status="running",
            name=None,
            store_id=None,
            product_id=None,
            date_start=None,
            date_end=None,
            created_objects={},
            result_summary=None,
        )
    )
    assert detail.status == "running"
    assert detail.name is None
    assert detail.created_objects == {}
    assert detail.result_summary is None


def test_workspace_list_response_shape():
    """E4 (#393) -- page shape mirrors the scenarios list (items + total)."""
    item = WorkspaceListItem.model_validate(_orm_like_workspace_row())
    page = WorkspaceListResponse(workspaces=[item], total=1)
    dumped = page.model_dump(mode="json")
    assert dumped["total"] == 1
    assert dumped["workspaces"][0]["workspace_id"] == "a" * 32
    # ISO serialization on the wire.
    assert isinstance(dumped["workspaces"][0]["created_at"], str)
