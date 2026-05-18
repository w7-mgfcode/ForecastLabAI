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
