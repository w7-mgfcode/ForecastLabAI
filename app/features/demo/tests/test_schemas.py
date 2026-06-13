"""Unit tests for demo slice schemas."""

import datetime as _dt
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.features.demo.schemas import (
    DemoRunRequest,
    DemoRunResult,
    StepEvent,
    UserScope,
    WorkspaceDetailResponse,
    WorkspaceListItem,
    WorkspaceListResponse,
    WorkspaceUpdateRequest,
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


# =============================================================================
# E1 (#407) -- replayed_from_workspace_id (replay provenance)
# =============================================================================


def test_demo_run_request_replayed_from_default_none():
    """E1 (#407) -- default None; a legacy frame without the key validates."""
    assert DemoRunRequest().replayed_from_workspace_id is None
    legacy = DemoRunRequest.model_validate({"seed": 7})
    assert legacy.replayed_from_workspace_id is None


def test_demo_run_request_replayed_from_json_path():
    """E1 (#407) -- the JSON wire form (validate_python on a parsed dict, the
    path FastAPI uses) accepts keep + a 32-hex lineage pointer."""
    req = DemoRunRequest.model_validate(
        {"preservation": "keep", "replayed_from_workspace_id": "a" * 32}
    )
    assert req.replayed_from_workspace_id == "a" * 32


def test_demo_run_request_replayed_from_requires_keep():
    """E1 (#407) -- a lineage pointer without preservation='keep' is rejected."""
    with pytest.raises(ValidationError):
        DemoRunRequest.model_validate({"replayed_from_workspace_id": "a" * 32})
    with pytest.raises(ValidationError):
        DemoRunRequest.model_validate(
            {"preservation": "ephemeral", "replayed_from_workspace_id": "a" * 32}
        )


def test_demo_run_request_replayed_from_pattern_rejected():
    """E1 (#407) -- values off the uuid4().hex shape are rejected."""
    for bad in ("not-hex!" + "0" * 24, "A" * 32, "a" * 31, "a" * 33):
        with pytest.raises(ValidationError):
            DemoRunRequest.model_validate(
                {"preservation": "keep", "replayed_from_workspace_id": bad}
            )


# =============================================================================
# E3 (#409) -- seed_overrides + user_scope (advanced seed config + focus pair)
# =============================================================================


def test_demo_run_request_e3_field_defaults():
    """E3 (#409) -- defaults None; a legacy 4-field frame stays byte-identical."""
    req = DemoRunRequest.model_validate(
        {"seed": 7, "reset": False, "skip_seed": True, "scenario": "demo_minimal"}
    )
    assert req.seed_overrides is None
    assert req.user_scope is None


def test_demo_run_request_seed_overrides_json_path():
    """E3 (#409) -- the JSON wire form (validate_python on a parsed dict, the
    path FastAPI uses) accepts a nested overrides object on a re-seed run."""
    req = DemoRunRequest.model_validate(
        {"skip_seed": False, "seed_overrides": {"stores": 8, "promotion_intensity": 0.3}}
    )
    assert req.seed_overrides is not None
    assert req.seed_overrides.stores == 8
    assert req.seed_overrides.promotion_intensity == 0.3


def test_demo_run_request_seed_overrides_require_reseed():
    """E3 (#409) -- overrides on a skip_seed run would be a silent no-op."""
    with pytest.raises(ValidationError):
        DemoRunRequest.model_validate({"skip_seed": True, "seed_overrides": {"stores": 8}})
    # skip_seed defaults to True -- omitting it must also reject.
    with pytest.raises(ValidationError):
        DemoRunRequest.model_validate({"seed_overrides": {"stores": 8}})


def test_demo_run_request_empty_seed_overrides_normalizes_to_none():
    """E3 (#409) -- {} on the wire collapses to None (single no-overrides form),
    and is therefore legal even on a skip_seed run."""
    req = DemoRunRequest.model_validate({"skip_seed": True, "seed_overrides": {}})
    assert req.seed_overrides is None


def test_demo_run_request_window_days_rejected_on_holiday_rush():
    """E3 (#409) -- holiday_rush is calendar-pinned; window_days fails loudly."""
    with pytest.raises(ValidationError):
        DemoRunRequest.model_validate(
            {
                "skip_seed": False,
                "scenario": "holiday_rush",
                "seed_overrides": {"window_days": 120},
            }
        )
    # The same knob is fine on a today-anchored preset.
    req = DemoRunRequest.model_validate(
        {
            "skip_seed": False,
            "scenario": "retail_standard",
            "seed_overrides": {"window_days": 120},
        }
    )
    assert req.seed_overrides is not None
    assert req.seed_overrides.window_days == 120


def test_demo_run_request_seed_overrides_unknown_knob_rejected():
    """E3 (#409) -- the nested extra='forbid' allow-list holds on the demo path."""
    with pytest.raises(ValidationError):
        DemoRunRequest.model_validate({"skip_seed": False, "seed_overrides": {"bogus_knob": 1}})


def test_demo_run_request_user_scope_json_path():
    """E3 (#409) -- user_scope accepts a real id pair; works with skip_seed."""
    req = DemoRunRequest.model_validate({"user_scope": {"store_id": 12, "product_id": 47}})
    assert req.user_scope is not None
    assert req.user_scope.store_id == 12
    assert req.user_scope.product_id == 47


def test_user_scope_rejects_extra_keys_and_bad_ids():
    """E3 (#409) -- closed schema; ids are ge=1; strict rejects string ints."""
    with pytest.raises(ValidationError):
        UserScope.model_validate({"store_id": 1, "product_id": 1, "extra": True})
    with pytest.raises(ValidationError):
        UserScope.model_validate({"store_id": 0, "product_id": 1})
    with pytest.raises(ValidationError):
        UserScope.model_validate({"store_id": 1})  # product_id required
    with pytest.raises(ValidationError):
        UserScope.model_validate({"store_id": "1", "product_id": 1})


# =============================================================================
# E1 (#407) -- WorkspaceUpdateRequest (PATCH body)
# =============================================================================


def test_workspace_update_request_partial_fields_set():
    """E1 (#407) -- exclude_unset distinguishes absent from explicit null."""
    cleared = WorkspaceUpdateRequest.model_validate({"notes": None})
    assert cleared.model_dump(exclude_unset=True) == {"notes": None}
    empty = WorkspaceUpdateRequest.model_validate({})
    assert empty.model_dump(exclude_unset=True) == {}


def test_workspace_update_request_rejects_unknown_key():
    """E1 (#407) -- extra='forbid': status (and any typo) is not patchable."""
    with pytest.raises(ValidationError):
        WorkspaceUpdateRequest.model_validate({"status": "archived"})
    with pytest.raises(ValidationError):
        WorkspaceUpdateRequest.model_validate({"archvied": True})


def test_workspace_update_request_name_pattern_and_tags_cap():
    """E1 (#407) -- name pattern + the 20-item tag cap are enforced."""
    with pytest.raises(ValidationError):
        WorkspaceUpdateRequest.model_validate({"name": "Bad Name!"})
    with pytest.raises(ValidationError):
        WorkspaceUpdateRequest.model_validate({"tags": [f"t{i}" for i in range(21)]})
    ok = WorkspaceUpdateRequest.model_validate({"tags": ["workspace:x", "demo"]})
    assert ok.tags == ["workspace:x", "demo"]


def test_workspace_update_request_rejects_explicit_null_flags():
    """E1 (#407) -- explicit null on the NOT NULL-backed fields is a 422."""
    with pytest.raises(ValidationError):
        WorkspaceUpdateRequest.model_validate({"archived": None})
    with pytest.raises(ValidationError):
        WorkspaceUpdateRequest.model_validate({"pinned": None})
    with pytest.raises(ValidationError):
        WorkspaceUpdateRequest.model_validate({"tags": None})
    # The sanctioned clear path: an empty list, never null.
    assert WorkspaceUpdateRequest.model_validate({"tags": []}).tags == []


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


def test_workspace_responses_default_e1_fields_for_pre_e1_rows():
    """E1 (#407) -- pre-E1 ORM-shaped rows (no new attrs) still validate;
    the additive fields fall back to their defaults."""
    item = WorkspaceListItem.model_validate(_orm_like_workspace_row())
    assert item.archived is False
    assert item.pinned is False
    assert item.tags == []
    assert item.replayed_from_workspace_id is None

    detail = WorkspaceDetailResponse.model_validate(_orm_like_workspace_row())
    assert detail.notes is None
    assert detail.config_schema_version == 1
    assert detail.seed_overrides is None
    assert detail.user_scope is None
    assert detail.approval_events is None
    assert detail.rag_events is None
    assert detail.job_ids is None
    assert detail.phase_summaries is None


def test_workspace_detail_passes_e1_fields_through():
    """E1 (#407) -- populated lifecycle + slot values ride through verbatim."""
    detail = WorkspaceDetailResponse.model_validate(
        _orm_like_workspace_row(
            archived=True,
            pinned=True,
            tags=["demo", "workspace:x"],
            replayed_from_workspace_id="b" * 32,
            notes="kept for the quarterly review",
            config_schema_version=1,
            seed_overrides={"noise_sigma": 0.2},
            job_ids=["job-1", "job-2"],
        )
    )
    assert detail.archived is True
    assert detail.pinned is True
    assert detail.tags == ["demo", "workspace:x"]
    assert detail.replayed_from_workspace_id == "b" * 32
    assert detail.notes == "kept for the quarterly review"
    assert detail.seed_overrides == {"noise_sigma": 0.2}
    assert detail.job_ids == ["job-1", "job-2"]


def test_workspace_list_item_exposes_e3_slots():
    """E3 (#409) -- seed_overrides/user_scope live on the LIST item (replay
    reads list rows), defaulting to None on rows without them."""
    bare = WorkspaceListItem.model_validate(_orm_like_workspace_row())
    assert bare.seed_overrides is None
    assert bare.user_scope is None

    slotted = WorkspaceListItem.model_validate(
        _orm_like_workspace_row(
            seed_overrides={"stores": 8, "noise_sigma": 0.25},
            user_scope={"store_id": 12, "product_id": 47},
        )
    )
    assert slotted.seed_overrides == {"stores": 8, "noise_sigma": 0.25}
    assert slotted.user_scope == {"store_id": 12, "product_id": 47}
    # Detail inherits the same exposure.
    detail = WorkspaceDetailResponse.model_validate(
        _orm_like_workspace_row(seed_overrides={"sparsity": 0.3})
    )
    assert detail.seed_overrides == {"sparsity": 0.3}


def test_workspace_list_response_shape():
    """E4 (#393) -- page shape mirrors the scenarios list (items + total)."""
    item = WorkspaceListItem.model_validate(_orm_like_workspace_row())
    page = WorkspaceListResponse(workspaces=[item], total=1)
    dumped = page.model_dump(mode="json")
    assert dumped["total"] == 1
    assert dumped["workspaces"][0]["workspace_id"] == "a" * 32
    # ISO serialization on the wire.
    assert isinstance(dumped["workspaces"][0]["created_at"], str)
