"""Route tests for the demo slice (POST /demo/run + WS /demo/stream + GETs).

The demo service is monkeypatched so these tests exercise the route wiring
without a database or a real pipeline run. The E4 (#393) workspace GET unit
tests monkeypatch the workspace helpers the same way; their integration
counterparts run against the real Postgres via the ``db_session`` fixture.
"""

import datetime as _dt
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.demo import service, workspace
from app.features.demo.schemas import DemoRunRequest, DemoRunResult, StepEvent
from app.main import app


@pytest.fixture
def canned_result() -> DemoRunResult:
    """A successful DemoRunResult used to stub the service."""
    return DemoRunResult(
        overall_status="pass",
        steps=[
            StepEvent(
                event_type="step_complete",
                step_name="precheck",
                step_index=1,
                total_steps=11,
                status="pass",
                detail="/health -> ok",
            )
        ],
        winner_model_type="seasonal_naive",
        winner_wape=0.15,
        winning_run_id="demo-run-abc",
        alias="demo-production",
        wall_clock_s=12.0,
    )


async def test_run_demo_pipeline_success(client, monkeypatch, canned_result: DemoRunResult):
    async def fake_run_sync(_app, _params: DemoRunRequest) -> DemoRunResult:
        return canned_result

    monkeypatch.setattr(service, "run_pipeline_sync", fake_run_sync)

    resp = await client.post("/demo/run", json={"skip_seed": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_status"] == "pass"
    assert body["winner_model_type"] == "seasonal_naive"
    assert body["winning_run_id"] == "demo-run-abc"
    assert len(body["steps"]) == 1


async def test_run_demo_pipeline_busy_returns_409(client, monkeypatch):
    async def fake_run_sync(_app, _params: DemoRunRequest) -> DemoRunResult:
        raise service.PipelineBusyError("A demo pipeline run is already in progress.")

    monkeypatch.setattr(service, "run_pipeline_sync", fake_run_sync)

    resp = await client.post("/demo/run", json={})
    assert resp.status_code == 409
    # RFC 7807 problem+json (ConflictError -> forecastlab_exception_handler)
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert "in progress" in body["detail"]


async def test_run_demo_pipeline_rejects_negative_seed(client):
    resp = await client.post("/demo/run", json={"seed": -5})
    assert resp.status_code == 422


def test_demo_stream_websocket_streams_events(monkeypatch):
    async def fake_stream(_app, _params: DemoRunRequest) -> AsyncIterator[StepEvent]:
        yield StepEvent(
            event_type="step_start",
            step_name="precheck",
            step_index=1,
            total_steps=11,
        )
        yield StepEvent(
            event_type="pipeline_complete",
            step_name="summary",
            step_index=11,
            total_steps=11,
            status="pass",
            detail="runs=3 winner=seasonal_naive wall_clock=12s",
        )

    monkeypatch.setattr(service, "stream_pipeline", fake_stream)

    with TestClient(app).websocket_connect("/demo/stream") as ws:
        ws.send_json({"skip_seed": True})
        first = ws.receive_json()
        assert first["event_type"] == "step_start"
        assert first["step_name"] == "precheck"
        second = ws.receive_json()
        assert second["event_type"] == "pipeline_complete"
        assert second["status"] == "pass"


def test_demo_stream_websocket_busy_sends_error(monkeypatch):
    async def fake_stream(_app, _params: DemoRunRequest) -> AsyncIterator[StepEvent]:
        raise service.PipelineBusyError("A demo pipeline run is already in progress.")
        yield  # pragma: no cover -- makes this an async generator

    monkeypatch.setattr(service, "stream_pipeline", fake_stream)

    with TestClient(app).websocket_connect("/demo/stream") as ws:
        ws.send_json({})
        event = ws.receive_json()
        assert event["event_type"] == "error"
        assert "in progress" in event["detail"]


# =============================================================================
# E1 (#390) -- preservation / workspace_name passthrough
# =============================================================================


async def test_run_demo_accepts_preservation_fields(
    client, monkeypatch, canned_result: DemoRunResult
):
    """E1 (#390) -- the new optional fields validate and reach the service."""
    seen: dict[str, DemoRunRequest] = {}

    async def fake_run_sync(_app, params: DemoRunRequest) -> DemoRunResult:
        seen["params"] = params
        return canned_result

    monkeypatch.setattr(service, "run_pipeline_sync", fake_run_sync)

    resp = await client.post(
        "/demo/run",
        json={"skip_seed": True, "preservation": "keep", "workspace_name": "e1-route"},
    )
    assert resp.status_code == 200
    assert seen["params"].preservation == "keep"
    assert seen["params"].workspace_name == "e1-route"
    # The additive DemoRunResult field rides on the response (None here --
    # the canned result doesn't set it).
    assert resp.json()["workspace_id"] is None


async def test_run_demo_rejects_name_without_keep_422(client):
    """E1 (#390) -- workspace_name without preservation='keep' is a 422."""
    resp = await client.post("/demo/run", json={"workspace_name": "bad"})
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")


def test_demo_stream_websocket_accepts_preservation_fields(monkeypatch):
    """E1 (#390) -- the WS start frame accepts the new fields end-to-end."""
    seen: dict[str, DemoRunRequest] = {}

    async def fake_stream(_app, params: DemoRunRequest) -> AsyncIterator[StepEvent]:
        seen["params"] = params
        yield StepEvent(
            event_type="pipeline_complete",
            step_name="summary",
            step_index=11,
            total_steps=11,
            status="pass",
            data={"workspace_id": "ws-route-test"},
        )

    monkeypatch.setattr(service, "stream_pipeline", fake_stream)

    with TestClient(app).websocket_connect("/demo/stream") as ws:
        ws.send_json({"preservation": "keep", "workspace_name": "ws-frame"})
        event = ws.receive_json()
        assert event["event_type"] == "pipeline_complete"
        assert event["data"]["workspace_id"] == "ws-route-test"
    assert seen["params"].preservation == "keep"
    assert seen["params"].workspace_name == "ws-frame"


def test_demo_stream_websocket_legacy_frame_ignores_unknown_keys(monkeypatch):
    """E1 (#390) -- unknown start-frame keys stay ignored (the WS forward/
    backward compatibility contract; no extra='forbid')."""
    seen: dict[str, DemoRunRequest] = {}

    async def fake_stream(_app, params: DemoRunRequest) -> AsyncIterator[StepEvent]:
        seen["params"] = params
        yield StepEvent(
            event_type="pipeline_complete",
            step_name="summary",
            step_index=11,
            total_steps=11,
            status="pass",
        )

    monkeypatch.setattr(service, "stream_pipeline", fake_stream)

    with TestClient(app).websocket_connect("/demo/stream") as ws:
        ws.send_json({"seed": 7, "future_key_from_a_newer_client": True})
        event = ws.receive_json()
        assert event["event_type"] == "pipeline_complete"
    assert seen["params"].seed == 7
    assert seen["params"].preservation == "ephemeral"


# =============================================================================
# E4 (#393) -- GET /demo/workspaces + GET /demo/workspaces/{id} (unit)
# =============================================================================


def _orm_like_row(workspace_id: str = "a" * 32, **overrides: object) -> SimpleNamespace:
    """An ORM-shaped stand-in for a ShowcaseWorkspace row."""
    base: dict[str, object] = {
        "workspace_id": workspace_id,
        "name": "e4-route",
        "status": "completed",
        "seed": 42,
        "scenario": "demo_minimal",
        "reset": False,
        "skip_seed": True,
        "store_id": 3,
        "product_id": 7,
        "date_start": _dt.date(2026, 1, 1),
        "date_end": _dt.date(2026, 3, 31),
        "created_objects": {"winning_run_id": "run-abc"},
        "result_summary": {"winner_model_type": "naive"},
        "created_at": _dt.datetime(2026, 6, 1, 12, 0, tzinfo=_dt.UTC),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


async def test_list_workspaces_empty(client, monkeypatch):
    """E4 (#393) -- empty table yields 200 + an empty page (no 404)."""

    async def fake_list(_db, *, limit: int, offset: int) -> list[SimpleNamespace]:
        return []

    async def fake_count(_db) -> int:
        return 0

    monkeypatch.setattr(workspace, "list_workspaces", fake_list)
    monkeypatch.setattr(workspace, "count_workspaces", fake_count)

    resp = await client.get("/demo/workspaces")
    assert resp.status_code == 200
    assert resp.json() == {"workspaces": [], "total": 0}


async def test_list_workspaces_passes_pagination(client, monkeypatch):
    """E4 (#393) -- limit/offset query params reach the helper."""
    seen: dict[str, int] = {}

    async def fake_list(_db, *, limit: int, offset: int) -> list[SimpleNamespace]:
        seen["limit"] = limit
        seen["offset"] = offset
        return [_orm_like_row()]

    async def fake_count(_db) -> int:
        return 5

    monkeypatch.setattr(workspace, "list_workspaces", fake_list)
    monkeypatch.setattr(workspace, "count_workspaces", fake_count)

    resp = await client.get("/demo/workspaces", params={"limit": 2, "offset": 3})
    assert resp.status_code == 200
    assert seen == {"limit": 2, "offset": 3}
    body = resp.json()
    assert body["total"] == 5
    assert body["workspaces"][0]["workspace_id"] == "a" * 32
    # List items are compact -- no created_objects on the page payload.
    assert "created_objects" not in body["workspaces"][0]


async def test_list_workspaces_rejects_bad_pagination(client):
    """E4 (#393) -- out-of-range limit/offset are 422 problem+json."""
    resp = await client.get("/demo/workspaces", params={"limit": 0})
    assert resp.status_code == 422
    resp = await client.get("/demo/workspaces", params={"offset": -1})
    assert resp.status_code == 422


async def test_get_workspace_404(client, monkeypatch):
    """E4 (#393) -- unknown workspace_id is a 404 problem+json."""

    async def fake_get(_db, _workspace_id: str) -> None:
        return None

    monkeypatch.setattr(workspace, "get_workspace", fake_get)

    resp = await client.get("/demo/workspaces/" + "0" * 32)
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert "Workspace not found" in resp.json()["detail"]


async def test_get_workspace_success(client, monkeypatch):
    """E4 (#393) -- detail fields round-trip incl. created_objects + grain."""

    async def fake_get(_db, workspace_id: str) -> SimpleNamespace:
        return _orm_like_row(workspace_id=workspace_id)

    monkeypatch.setattr(workspace, "get_workspace", fake_get)

    resp = await client.get("/demo/workspaces/" + "b" * 32)
    assert resp.status_code == 200
    body = resp.json()
    assert body["workspace_id"] == "b" * 32
    assert body["created_objects"] == {"winning_run_id": "run-abc"}
    assert body["store_id"] == 3
    assert body["product_id"] == 7
    assert body["date_start"] == "2026-01-01"
    assert body["date_end"] == "2026-03-31"


# =============================================================================
# E4 (#393) -- workspace GET routes against real Postgres (integration)
# =============================================================================


@pytest.mark.integration
async def test_list_workspaces_integration_newest_first(client, db_session: AsyncSession):
    """Seeded rows list newest-first with the right total."""
    ids: list[str] = []
    for index in range(3):
        workspace_id = await workspace.create_workspace(
            DemoRunRequest.model_validate(
                {"preservation": "keep", "workspace_name": f"e4-it-{index}"}
            )
        )
        assert workspace_id is not None
        ids.append(workspace_id)

    resp = await client.get("/demo/workspaces")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert [w["workspace_id"] for w in body["workspaces"]] == list(reversed(ids))
    assert body["workspaces"][0]["name"] == "e4-it-2"

    paged = await client.get("/demo/workspaces", params={"limit": 1, "offset": 1})
    assert paged.status_code == 200
    paged_body = paged.json()
    assert paged_body["total"] == 3
    assert [w["workspace_id"] for w in paged_body["workspaces"]] == [ids[1]]


@pytest.mark.integration
async def test_get_workspace_integration_round_trip(client, db_session: AsyncSession):
    """created_objects JSONB round-trips through the detail endpoint."""
    workspace_id = await workspace.create_workspace(
        DemoRunRequest.model_validate({"preservation": "keep", "workspace_name": "e4-it-detail"})
    )
    assert workspace_id is not None

    resp = await client.get(f"/demo/workspaces/{workspace_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["workspace_id"] == workspace_id
    assert body["name"] == "e4-it-detail"
    assert body["status"] == "running"
    assert body["created_objects"] == {}
    assert body["result_summary"] is None

    missing = await client.get("/demo/workspaces/" + "f" * 32)
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/problem+json")
