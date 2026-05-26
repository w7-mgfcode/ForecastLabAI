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
from app.shared.seeder.config import ScenarioPreset

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
        # page_size=5 is the PRP-39 batch_preset discovery call; return 3 stores
        # so the step doesn't skip. Other callers ask for page_size=1; either
        # way the first item is the showcase grain (id=7).
        if "page_size=5" in path:
            return {"stores": [{"id": 7}, {"id": 8}, {"id": 9}]}
        return {"stores": [{"id": 7}]}
    if path.startswith("/dimensions/products"):
        if "page_size=5" in path:
            return {"products": [{"id": 3}, {"id": 4}]}
        return {"products": [{"id": 3}]}
    if path == "/featuresets/compute":
        return {"row_count": 80, "feature_columns": ["lag_1", "roll_7", "dow"]}
    if path == "/forecasting/train":
        return {"model_path": artifact_path}
    if path == "/backtesting/run":
        assert json_body is not None
        model_type = json_body["config"]["model_config_main"]["model_type"]
        wape = wapes.get(model_type, 0.5)
        # PRP-38 — include_baselines=True adds a baseline_results block;
        # bucketed_aggregated_metrics populated for the showcase-rich flow.
        include_baselines = bool(json_body["config"].get("include_baselines"))
        response: dict[str, Any] = {
            "main_model_results": {
                "aggregated_metrics": {
                    "wape": wape,
                    "mae": 1.0,
                    "rmse": 1.5,
                    "smape": 12.0,
                },
                "bucketed_aggregated_metrics": {
                    "h_1_7": {"wape": wape * 0.9, "mae": 0.9, "rmse": 1.3, "smape": 11.0},
                    "h_8_14": {"wape": wape * 1.1, "mae": 1.1, "rmse": 1.7, "smape": 13.0},
                },
            }
        }
        if include_baselines:
            response["baseline_results"] = [
                {
                    "model_type": "naive",
                    "aggregated_metrics": {"wape": wapes.get("naive", 0.3)},
                },
                {
                    "model_type": "seasonal_naive",
                    "aggregated_metrics": {"wape": wapes.get("seasonal_naive", 0.2)},
                },
            ]
        return response
    if path == "/registry/runs":
        return {"run_id": "demo-run-abc123def456"}
    if path == "/seeder/phase2-enrichment":
        return {
            "success": True,
            "records_created": {
                "product": 15,
                "replenishment_event": 1300,
                "exogenous_signal": 360,
                "sales_returns": 42,
            },
            "duration_ms": 234.5,
        }
    if path.endswith("/verify"):
        return {"verified": True}
    if path.endswith("/feature-metadata"):
        return {
            "run_id": "demo-run-abc123def456",
            "model_type": "prophet_like",
            "model_family": "additive",
            "feature_columns": ["lag_1", "lag_7", "dow", "month"],
            "features": [],
            "importance_type": "ridge_coef",
            "feature_frame_version": 2,
            "feature_groups": {"target_history": ["lag_1", "lag_7"], "calendar": ["dow", "month"]},
            "feature_safety_classes": {"lag_1": "leak_safe"},
        }
    if path.startswith("/registry/runs?"):
        # PRP-39 — champion_compat_compare lists SUCCESS runs on the grain.
        return {
            "runs": [
                {"run_id": "v1-baseline-run-id-aaaa", "feature_frame_version": None},
                {"run_id": "demo-run-abc123def456", "feature_frame_version": 2},
            ],
        }
    if path.startswith("/registry/compare/"):
        # PRP-39 — champion_compat_compare GETs the compare envelope.
        return {
            "run_a": {
                "run_id": "v1-baseline-run-id-aaaa",
                "feature_frame_version": None,
            },
            "run_b": {
                "run_id": "demo-run-abc123def456",
                "feature_frame_version": 2,
            },
            "config_diff": {},
            "metrics_diff": {},
        }
    if path.startswith("/registry/runs/"):  # PATCH pending->running->success
        return {}
    if path == "/registry/aliases":
        return {}
    if path.startswith("/registry/aliases/"):
        # PRP-39 — safer_promote_flow GETs the current alias target before swap.
        return {
            "alias_name": "demo-production",
            "run_id": "demo-run-abc123def456",
            "description": "current target",
        }
    if path == "/ops/summary":
        # PRP-39 — stale_alias_trigger GETs after registering a V=3 run.
        return {
            "aliases": [
                {
                    "alias_name": "demo-production",
                    "stale_reason": "feature_frame_version_mismatch",
                    "alias_feature_frame_version": 2,
                    "comparable_run_feature_frame_version": 3,
                }
            ]
        }
    if path == "/batch/forecasting":
        # PRP-39 — batch_preset POSTs the preset expansion. Return terminal
        # COMPLETED status (per D3, settles synchronously in most cases).
        return {
            "batch_id": "batch-demo-abcdef0123",
            "status": "completed",
            "total_items": 18,
            "completed_items": 18,
            "failed_items": 0,
        }
    if path.startswith("/batch/"):
        # Safety-net poll path (rare in canned fast tests).
        return {
            "batch_id": path.split("/")[-1],
            "status": "completed",
            "total_items": 18,
            "completed_items": 18,
            "failed_items": 0,
        }
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


# =============================================================================
# PRP-38 — phase grouping + new scenarios
# =============================================================================


def test_phase_table_demo_minimal_matches_legacy_11_steps():
    """PRP-38 — phase_table for DEMO_MINIMAL drops to the legacy 11-step flow.

    Test gates the (phase_name, step_name) lockstep contract with the frontend
    PHASE_DEFS.ts. If a phase or step is added in either tier without the
    matching change here, this test fails.
    """
    rows = pipeline._phase_table(ScenarioPreset.DEMO_MINIMAL)
    by_phase_step = [(p, s) for p, s, _fn in rows]
    assert by_phase_step == [
        ("data", "precheck"),
        ("data", "reset"),
        ("data", "seed"),
        ("data", "status"),
        ("data", "features"),
        ("modeling", "train"),
        ("decision", "backtest"),
        ("decision", "register"),
        ("verify", "verify"),
        ("agent", "agent"),
        ("cleanup", "cleanup"),
    ]


def test_phase_table_showcase_rich_adds_v2_steps():
    """PRP-38/39 — phase_table for SHOWCASE_RICH adds 3+4 steps; phase order stable.

    PRP-38 shipped 3 (phase2_enrichment, historical_backfill, v2_train).
    PRP-39 adds 4 more (champion_compat_compare, stale_alias_trigger,
    safer_promote_flow, batch_preset) AND a new ``portfolio`` phase between
    ``decision`` and ``verify``. Total: 18 rows across 7 phases.
    """
    rows = pipeline._phase_table(ScenarioPreset.SHOWCASE_RICH)
    by_phase_step = [(p, s) for p, s, _fn in rows]
    assert by_phase_step == [
        ("data", "precheck"),
        ("data", "reset"),
        ("data", "seed"),
        ("data", "status"),
        ("data", "features"),
        ("data", "phase2_enrichment"),
        ("data", "historical_backfill"),
        ("modeling", "train"),
        ("modeling", "v2_train"),
        ("decision", "backtest"),
        ("decision", "register"),
        # PRP-39 — three decision-phase extensions after register.
        ("decision", "champion_compat_compare"),
        ("decision", "stale_alias_trigger"),
        ("decision", "safer_promote_flow"),
        # PRP-39 — new portfolio phase between decision and verify.
        ("portfolio", "batch_preset"),
        ("verify", "verify"),
        ("agent", "agent"),
        ("cleanup", "cleanup"),
    ]


def test_phase_table_sparse_matches_demo_minimal_shape():
    """PRP-38 — SPARSE is offered in the picker but does not extend the pipeline."""
    sparse_rows = pipeline._phase_table(ScenarioPreset.SPARSE)
    minimal_rows = pipeline._phase_table(ScenarioPreset.DEMO_MINIMAL)
    assert [(p, s) for p, s, _ in sparse_rows] == [(p, s) for p, s, _ in minimal_rows]


def test_legacy_step_table_adapter_returns_11_pairs():
    """PRP-38 — ``_step_table()`` legacy adapter preserves the back-compat path."""
    flat = pipeline._step_table()
    assert len(flat) == 11
    assert [name for name, _fn in flat] == [
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


async def test_run_pipeline_emits_phase_fields(monkeypatch, tmp_path):
    """PRP-38 — every step_start / step_complete event carries phase_* fields."""
    artifact = tmp_path / "artifacts" / "models" / "model_x.joblib"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    wapes = {"naive": 0.3, "seasonal_naive": 0.1, "moving_average": 0.2, "prophet_like": 0.08}
    monkeypatch.setattr(pipeline, "_Client", _build_fake_client(str(artifact), wapes))

    events = [e async for e in pipeline.run_pipeline(app=_FAKE_APP, req=DemoRunRequest())]
    step_events = [e for e in events if e.event_type in {"step_start", "step_complete"}]
    assert step_events
    for ev in step_events:
        assert ev.phase_name in {"data", "modeling", "decision", "verify", "agent", "cleanup"}
        assert ev.phase_index is not None and ev.phase_index >= 1
        assert ev.phase_total == 6
    # Verify phases appear in canonical order.
    phases_seen = []
    for ev in step_events:
        if ev.phase_name and ev.phase_name not in phases_seen:
            phases_seen.append(ev.phase_name)
    assert phases_seen == ["data", "modeling", "decision", "verify", "agent", "cleanup"]


async def test_run_pipeline_showcase_rich_runs_v2_and_buckets(monkeypatch, tmp_path):
    """PRP-38 — SHOWCASE_RICH run reaches v2_train + bucket-visible backtest."""
    # The fake artifact must live under a path that contains 'artifacts/models/'
    # so step_v2_train's R1 check passes.
    artifact = tmp_path / "artifacts" / "models" / "model_v2abc.joblib"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"v2 bundle bytes")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    wapes = {
        "naive": 0.30,
        "seasonal_naive": 0.18,
        "moving_average": 0.25,
        "prophet_like": 0.10,
    }
    monkeypatch.setattr(pipeline, "_Client", _build_fake_client(str(artifact), wapes))

    req = DemoRunRequest(scenario=ScenarioPreset.SHOWCASE_RICH)
    events = [e async for e in pipeline.run_pipeline(app=_FAKE_APP, req=req)]
    by_name = {e.step_name: e for e in events if e.event_type == "step_complete"}

    # Phase-2 enrichment step records counts
    assert by_name["phase2_enrichment"].status == "pass"
    assert by_name["phase2_enrichment"].data["records_created"]["product"] == 15

    # V2 train step: artifact_uri = train_response["model_path"] (R1).
    v2 = by_name["v2_train"]
    assert v2.status == "pass"
    assert v2.data["feature_frame_version"] == 2
    assert v2.data["model_type"] == "prophet_like"
    assert v2.data["v2_run_id"] == "demo-run-abc123def456"
    assert v2.data["artifact_uri_full"] == str(artifact)
    assert v2.data["feature_columns_count"] == 4
    assert "target_history" in v2.data["feature_groups"]

    # Backtest step emits buckets when SHOWCASE_RICH is active.
    bt = by_name["backtest"]
    assert bt.status == "pass"
    buckets = bt.data["bucketed_aggregated_metrics"]
    assert "h_1_7" in buckets
    assert "h_8_14" in buckets
    # Subset against HORIZON_BUCKETS ids.
    from app.features.backtesting.metrics import HORIZON_BUCKETS

    bucket_ids = {b[0] for b in HORIZON_BUCKETS}
    assert set(buckets.keys()).issubset(bucket_ids)

    # Pipeline summary surfaces the v2_run_id for the Inspect deep link.
    final = events[-1]
    assert final.event_type == "pipeline_complete"
    assert final.data["v2_run_id"] == "demo-run-abc123def456"


async def test_run_pipeline_showcase_rich_emits_18_steps(monkeypatch, tmp_path):
    """PRP-38/39 — SHOWCASE_RICH adds 3+4 new steps (11 -> 18 total).

    PRP-38 shipped 14 (11 + phase2_enrichment + historical_backfill + v2_train).
    PRP-39 adds 4 more (champion_compat_compare + stale_alias_trigger +
    safer_promote_flow + batch_preset).
    """
    artifact = tmp_path / "artifacts" / "models" / "model_x.joblib"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    wapes = {"naive": 0.3, "seasonal_naive": 0.1, "moving_average": 0.2, "prophet_like": 0.08}
    monkeypatch.setattr(pipeline, "_Client", _build_fake_client(str(artifact), wapes))

    req = DemoRunRequest(scenario=ScenarioPreset.SHOWCASE_RICH)
    events = [e async for e in pipeline.run_pipeline(app=_FAKE_APP, req=req)]
    completes = [e for e in events if e.event_type == "step_complete"]
    assert len(completes) == 18
    # Every event reports total_steps=18
    for ev in completes:
        assert ev.total_steps == 18


# =============================================================================
# PRP-39 — per-step unit tests (canned ASGI HTTP)
# =============================================================================


def _make_ctx_showcase_ready() -> pipeline.DemoContext:
    """Build a DemoContext with the fields PRP-39 steps consume already set."""
    from datetime import date

    ctx = pipeline.DemoContext(
        seed=42,
        skip_seed=True,
        reset=False,
        scenario=ScenarioPreset.SHOWCASE_RICH,
    )
    ctx.store_id = 7
    ctx.product_id = 3
    ctx.date_start = date(2024, 10, 1)
    ctx.date_end = date(2024, 12, 31)
    ctx.winner_model_type = "prophet_like"
    ctx.winner_wape = 0.08
    ctx.winning_run_id = "demo-run-abc123def456"
    ctx.v2_run_id = "demo-run-abc123def456"
    return ctx


def _bind_fake_client(artifact_path: str, wapes: dict[str, float]) -> Any:
    """Construct a fake-client instance for direct step-function invocation."""
    fake_class = _build_fake_client(artifact_path, wapes)
    return fake_class(_FAKE_APP)


async def test_champion_compat_compare_step_marks_v_mismatch_incompatible(monkeypatch, tmp_path):
    """PRP-39 — champion_compat_compare derives compatible=False on V mismatch."""
    artifact = tmp_path / "m.joblib"
    artifact.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    client = _bind_fake_client(str(artifact), {"prophet_like": 0.08})

    ctx = _make_ctx_showcase_ready()
    status, detail, data = await pipeline.step_champion_compat_compare(ctx, client)

    assert status == "pass"
    assert data["compatible"] is False
    assert data["comparable_reason"] == "feature_frame_version_mismatch"
    assert data["v1_run_id"] == "v1-baseline-run-id-aaaa"
    assert data["v2_run_id"] == "demo-run-abc123def456"
    assert data["feature_frame_version_a"] is None
    assert data["feature_frame_version_b"] == 2
    assert "V_a=1" in detail and "V_b=2" in detail


async def test_champion_compat_compare_step_skips_without_v2_run(monkeypatch, tmp_path):
    """PRP-39 — champion_compat_compare skips when no V2 run exists (R14)."""
    artifact = tmp_path / "m.joblib"
    artifact.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    client = _bind_fake_client(str(artifact), {})

    ctx = _make_ctx_showcase_ready()
    ctx.v2_run_id = None
    status, detail, _ = await pipeline.step_champion_compat_compare(ctx, client)

    assert status == "skip"
    assert "showcase_rich" in detail


async def test_stale_alias_trigger_step_surfaces_v_mismatch(monkeypatch, tmp_path):
    """PRP-39 — stale_alias_trigger registers V=3 run and confirms ops verdict."""
    artifact = tmp_path / "m.joblib"
    artifact.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    client = _bind_fake_client(str(artifact), {"prophet_like": 0.08})

    ctx = _make_ctx_showcase_ready()
    status, _detail, data = await pipeline.step_stale_alias_trigger(ctx, client)

    assert status == "pass"
    assert data["alias_name"] == "demo-production"
    assert data["stale_reason"] == "feature_frame_version_mismatch"
    assert data["alias_feature_frame_version"] == 2
    assert data["comparable_run_feature_frame_version"] == 3
    assert ctx.stale_alias_run_id == "demo-run-abc123def456"


async def test_safer_promote_flow_step_captures_original_alias(monkeypatch, tmp_path):
    """PRP-39 — safer_promote_flow records original alias for R15 restore."""
    artifact = tmp_path / "m.joblib"
    artifact.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    client = _bind_fake_client(str(artifact), {"seasonal_naive": 99.0})

    ctx = _make_ctx_showcase_ready()
    status, _detail, data = await pipeline.step_safer_promote_flow(ctx, client)

    assert status == "pass"
    assert data["alias_name"] == "demo-production"
    assert data["before_run_id"] == "demo-run-abc123def456"  # canned GET response
    assert data["after_run_id"] == "demo-run-abc123def456"  # canned POST returns same id
    assert data["swap_intent"] == "demo_safer_promote_walkthrough"
    # R15 — original alias captured before swap.
    assert ctx.original_demo_alias_run_id == "demo-run-abc123def456"


async def test_batch_preset_step_emits_terminal_completed(monkeypatch, tmp_path):
    """PRP-39 — batch_preset returns pass on terminal completed status (D2/D3)."""
    artifact = tmp_path / "m.joblib"
    artifact.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    client = _bind_fake_client(str(artifact), {})

    ctx = _make_ctx_showcase_ready()
    status, detail, data = await pipeline.step_batch_preset(ctx, client)

    assert status == "pass"
    assert data["batch_id"] == "batch-demo-abcdef0123"
    assert data["kind"] == "manual"
    assert data["preset_source"] == "quick_baseline_sweep"
    assert data["total_items"] == 18
    assert data["completed_items"] == 18
    assert data["status"] == "completed"
    assert "preset=quick_baseline_sweep" in detail
    assert ctx.batch_id == "batch-demo-abcdef0123"


async def test_batch_preset_step_skips_without_date_range(monkeypatch, tmp_path):
    """PRP-39 — batch_preset skips gracefully when no date range present."""
    artifact = tmp_path / "m.joblib"
    artifact.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    client = _bind_fake_client(str(artifact), {})

    ctx = _make_ctx_showcase_ready()
    ctx.date_start = None
    ctx.date_end = None
    status, detail, _ = await pipeline.step_batch_preset(ctx, client)

    assert status == "skip"
    assert "showcase_rich" in detail


async def test_cleanup_restores_alias_when_promote_swapped_it(monkeypatch, tmp_path):
    """PRP-39 R15 — cleanup restores demo-production alias post-swap."""
    artifact = tmp_path / "m.joblib"
    artifact.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    client = _bind_fake_client(str(artifact), {})

    ctx = _make_ctx_showcase_ready()
    ctx.original_demo_alias_run_id = "original-v2-winner-run-id"
    # No agent session opened
    ctx.session_id = None

    status, detail, data = await pipeline.step_cleanup(ctx, client)

    assert status == "pass"
    assert data["alias_restored"] is True
    assert data["restored_run_id"] == "original-v2-winner-run-id"
    assert "alias restored" in detail


async def test_cleanup_skips_when_nothing_to_restore_or_close(monkeypatch, tmp_path):
    """PRP-39 — cleanup is a no-op skip when no agent + no alias swap occurred."""
    artifact = tmp_path / "m.joblib"
    artifact.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    client = _bind_fake_client(str(artifact), {})

    ctx = _make_ctx_showcase_ready()
    ctx.session_id = None
    ctx.original_demo_alias_run_id = None  # PRP-39 — no swap to restore

    status, _detail, data = await pipeline.step_cleanup(ctx, client)

    assert status == "skip"
    assert data["alias_restored"] is False
    assert data["agent_session_closed"] is False
