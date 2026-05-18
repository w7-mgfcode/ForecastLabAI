"""Unit tests for the demo pipeline orchestrator.

The pipeline drives the app over HTTP via ``pipeline._Client``; these tests
monkeypatch ``_Client`` with a canned-response stand-in so the orchestration
logic (step sequencing, winner selection, fail-fast) is exercised with no
database, no network, and no real models.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI

from app.features.demo import pipeline
from app.features.demo.schemas import DemoRunRequest

# A bare app instance -- the fake clients ignore it; it only satisfies the
# run_pipeline(app: FastAPI, ...) signature.
_FAKE_APP = FastAPI()

# =============================================================================
# Canned HTTP responses
# =============================================================================


def _canned_response(
    path: str,
    json_body: dict[str, Any] | None,
    artifact_path: str,
    wapes: dict[str, float],
) -> dict[str, Any]:
    """Return a canned 2xx body for a given endpoint path."""
    if path == "/health":
        return {"status": "ok"}
    if path == "/seeder/data":
        return {"records_deleted": {"sales": 120, "store": 3}}
    if path == "/seeder/generate":
        return {"records_created": {"sales": 500, "store": 3, "product": 10}}
    if path == "/seeder/status":
        return {
            "date_range_start": "2024-10-01",
            "date_range_end": "2024-12-31",
            "sales": 500,
        }
    if path.startswith("/dimensions/stores"):
        return {"stores": [{"id": 7}]}
    if path.startswith("/dimensions/products"):
        return {"products": [{"id": 3}]}
    if path == "/featuresets/compute":
        return {"row_count": 80, "feature_columns": ["lag_1", "roll_7", "dow"]}
    if path == "/forecasting/train":
        return {"model_path": artifact_path}
    if path == "/backtesting/run":
        assert json_body is not None
        model_type = json_body["config"]["model_config_main"]["model_type"]
        return {
            "main_model_results": {
                "aggregated_metrics": {"wape": wapes[model_type], "mae": 1.0, "smape": 12.0}
            }
        }
    if path == "/registry/runs":
        return {"run_id": "demo-run-abc123def456"}
    if path.endswith("/verify"):
        return {"verified": True}
    if path.startswith("/registry/runs/"):  # PATCH pending->running->success
        return {}
    if path == "/registry/aliases":
        return {}
    raise AssertionError(f"unexpected request path: {path}")


def _build_fake_client(artifact_path: str, wapes: dict[str, float]) -> type:
    """Build a canned-response stand-in class for ``pipeline._Client``."""

    class _FakeClient:
        def __init__(self, _app: Any) -> None:
            self.calls: list[tuple[str, str]] = []

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def request(
            self,
            step: str,
            method: str,
            path: str,
            *,
            json_body: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            self.calls.append((method, path))
            return _canned_response(path, json_body, artifact_path, wapes)

    return _FakeClient


def _fake_settings(registry_root: str) -> SimpleNamespace:
    """Fake settings: usable registry root, no LLM keys (agent step skips)."""
    return SimpleNamespace(
        registry_artifact_root=registry_root,
        agent_default_model="anthropic:claude-test",
        anthropic_api_key="",
        openai_api_key="",
        google_api_key="",
    )


# =============================================================================
# _select_winner
# =============================================================================


def test_select_winner_picks_lowest_wape():
    results = {"naive": {"wape": 0.30}, "seasonal_naive": {"wape": 0.12}, "ma": {"wape": 0.25}}
    assert pipeline._select_winner(results) == ("seasonal_naive", 0.12)


def test_select_winner_skips_nan():
    results = {"naive": {"wape": float("nan")}, "seasonal_naive": {"wape": 0.5}}
    assert pipeline._select_winner(results) == ("seasonal_naive", 0.5)


def test_select_winner_none_when_no_usable_wape():
    assert pipeline._select_winner({}) is None
    assert pipeline._select_winner({"naive": {"wape": float("nan")}}) is None


# =============================================================================
# run_pipeline -- full green run
# =============================================================================


async def test_run_pipeline_full_green(monkeypatch, tmp_path):
    artifact = tmp_path / "naive-model.joblib"
    artifact.write_bytes(b"fake joblib artifact bytes")
    registry_root = tmp_path / "registry"

    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(registry_root)))
    wapes = {"naive": 0.30, "seasonal_naive": 0.15, "moving_average": 0.25}
    monkeypatch.setattr(pipeline, "_Client", _build_fake_client(str(artifact), wapes))

    events = [e async for e in pipeline.run_pipeline(app=_FAKE_APP, req=DemoRunRequest())]

    starts = [e for e in events if e.event_type == "step_start"]
    completes = [e for e in events if e.event_type == "step_complete"]
    finals = [e for e in events if e.event_type == "pipeline_complete"]

    # 11 step_start + 11 step_complete + 1 pipeline_complete
    assert len(starts) == 11
    assert len(completes) == 11
    assert len(finals) == 1

    assert [e.step_name for e in completes] == [
        "precheck",
        "reset",
        "seed",
        "status",
        "features",
        "train",
        "backtest",
        "register",
        "verify",
        "agent",
        "cleanup",
    ]

    by_name = {e.step_name: e for e in completes}
    assert by_name["precheck"].status == "pass"
    assert by_name["reset"].status == "skip"  # reset=False
    assert by_name["seed"].status == "skip"  # skip_seed=True (default)
    assert by_name["status"].status == "pass"
    assert by_name["features"].status == "pass"
    assert by_name["train"].status == "pass"
    assert by_name["backtest"].status == "pass"
    assert by_name["register"].status == "pass"
    assert by_name["verify"].status == "pass"
    assert by_name["agent"].status == "skip"  # no LLM key
    assert by_name["cleanup"].status == "skip"

    # winner = lowest WAPE = seasonal_naive
    assert by_name["backtest"].data["winner"] == "seasonal_naive"
    assert by_name["register"].data["run_id"] == "demo-run-abc123def456"
    assert by_name["register"].data["alias"] == "demo-production"

    final = finals[0]
    assert final.status == "pass"
    assert final.data["winner_model_type"] == "seasonal_naive"
    assert final.data["winning_run_id"] == "demo-run-abc123def456"

    # the registry artifact was copied + is hashable
    copied = list((registry_root / "demo").glob("*.joblib"))
    assert len(copied) == 1


async def test_run_pipeline_emits_step_start_before_complete(monkeypatch, tmp_path):
    artifact = tmp_path / "m.joblib"
    artifact.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    wapes = {"naive": 0.3, "seasonal_naive": 0.1, "moving_average": 0.2}
    monkeypatch.setattr(pipeline, "_Client", _build_fake_client(str(artifact), wapes))

    events = [e async for e in pipeline.run_pipeline(app=_FAKE_APP, req=DemoRunRequest())]
    # for each step, step_start must precede its step_complete
    seen_start: set[str] = set()
    for event in events:
        if event.event_type == "step_start":
            seen_start.add(event.step_name)
        elif event.event_type == "step_complete":
            assert event.step_name in seen_start


async def test_run_pipeline_with_reset_and_seed(monkeypatch, tmp_path):
    artifact = tmp_path / "m.joblib"
    artifact.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    wapes = {"naive": 0.3, "seasonal_naive": 0.1, "moving_average": 0.2}
    monkeypatch.setattr(pipeline, "_Client", _build_fake_client(str(artifact), wapes))

    req = DemoRunRequest(reset=True, skip_seed=False)
    events = [e async for e in pipeline.run_pipeline(app=_FAKE_APP, req=req)]
    by_name = {e.step_name: e for e in events if e.event_type == "step_complete"}
    assert by_name["reset"].status == "pass"
    assert by_name["seed"].status == "pass"
    assert events[-1].status == "pass"


# =============================================================================
# run_pipeline -- fail-fast
# =============================================================================


async def test_run_pipeline_stops_on_failed_step(monkeypatch):
    class _FailingClient:
        def __init__(self, _app: Any) -> None:
            pass

        async def __aenter__(self) -> _FailingClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def request(
            self,
            step: str,
            method: str,
            path: str,
            *,
            json_body: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            if path == "/health":
                return {"status": "ok"}
            if path == "/seeder/status":
                raise pipeline._StepError(
                    "status", 500, {"title": "Database Error", "detail": "db down"}
                )
            raise AssertionError(f"unexpected request after failure: {path}")

    monkeypatch.setattr(pipeline, "_Client", _FailingClient)

    events = [e async for e in pipeline.run_pipeline(app=_FAKE_APP, req=DemoRunRequest())]
    completes = [e for e in events if e.event_type == "step_complete"]

    # precheck pass, reset skip, seed skip, status FAIL -> run stops
    assert [e.step_name for e in completes] == ["precheck", "reset", "seed", "status"]
    assert completes[-1].status == "fail"
    assert "db down" in completes[-1].detail

    final = events[-1]
    assert final.event_type == "pipeline_complete"
    assert final.status == "fail"


async def test_run_pipeline_transport_error_becomes_fail(monkeypatch):
    import httpx

    class _BrokenClient:
        def __init__(self, _app: Any) -> None:
            pass

        async def __aenter__(self) -> _BrokenClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def request(self, *_a: object, **_k: object) -> dict[str, Any]:
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(pipeline, "_Client", _BrokenClient)
    events = [e async for e in pipeline.run_pipeline(app=_FAKE_APP, req=DemoRunRequest())]
    completes = [e for e in events if e.event_type == "step_complete"]
    assert completes[0].step_name == "precheck"
    assert completes[0].status == "fail"
    assert "transport error" in completes[0].detail
    assert events[-1].status == "fail"
