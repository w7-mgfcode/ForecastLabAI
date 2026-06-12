"""Route tests for the demo slice (POST /demo/run + WS /demo/stream).

The demo service is monkeypatched so these tests exercise the route wiring
without a database or a real pipeline run.
"""

from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from app.features.demo import service
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
