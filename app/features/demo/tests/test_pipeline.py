"""Unit tests for the demo pipeline orchestrator.

The pipeline drives the app over HTTP via ``pipeline._Client``; these tests
monkeypatch ``_Client`` with a canned-response stand-in so the orchestration
logic (step sequencing, winner selection, fail-fast) is exercised with no
database, no network, and no real models.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

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
    *,
    method: str = "POST",
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
    # PRP-40 — planning + knowledge endpoints (showcase_rich only).
    if path == "/registry/aliases/demo-production":
        return {"alias_name": "demo-production", "run_id": "demo-run-abc123def456"}
    if (
        method == "GET"
        and path.startswith("/registry/runs/")
        and not path.endswith("/verify")
        and not path.endswith("/feature-metadata")
    ):
        # GET /registry/runs/{run_id} returns artifact_uri.
        return {
            "run_id": "demo-run-abc123def456",
            "artifact_uri": "demo/seasonal_naive-model_abc123def456.joblib",
            "status": "success",
        }
    if path == "/scenarios":
        # POST /scenarios runs the simulation and stores the snapshot.
        assert json_body is not None
        name = json_body.get("name", "")
        scenario_id = f"scn-{name}"
        units_delta = -25.0 if "price" in name else 18.5
        revenue_delta = -180.0 if "price" in name else 220.0
        return {
            "scenario_id": scenario_id,
            "name": name,
            "store_id": 7,
            "product_id": 3,
            "run_id": json_body.get("run_id", ""),
            "horizon": json_body.get("horizon", 14),
            "method": "heuristic",
            "created_at": "2026-05-26T10:00:00Z",
            "assumptions": json_body.get("assumptions", {}),
            "comparison": {
                "method": "heuristic",
                "units_delta": units_delta,
                "revenue_delta": revenue_delta,
                "units_delta_pct": 0.0,
            },
            "tags": json_body.get("tags", []),
        }
    if path == "/scenarios/compare":
        assert json_body is not None
        ids = json_body.get("scenario_ids", [])
        # Holiday plan ranks first (higher revenue_delta in the canned data).
        ordered = [
            {
                "scenario_id": ids[1] if len(ids) > 1 else "scn-unknown",
                "name": "showcase-holiday-uplift",
                "units_delta": 18.5,
                "revenue_delta": 220.0,
                "coverage_verdict": "ok",
                "rank": 1,
            },
            {
                "scenario_id": ids[0] if ids else "scn-unknown",
                "name": "showcase-price-cut-10pct",
                "units_delta": -25.0,
                "revenue_delta": -180.0,
                "coverage_verdict": "ok",
                "rank": 2,
            },
        ]
        return {"scenarios": ordered, "chart_data": []}
    if path == "/config/providers/health":
        # _Client wraps top-level JSON arrays as {"_raw": [...]}.
        return {
            "_raw": [
                {"provider": "ollama", "reachable": True, "detail": "ok", "models": []},
                {
                    "provider": "openai",
                    "reachable": True,
                    "detail": "key present",
                    "models": [],
                },
            ]
        }
    if path == "/rag/index/project-docs":
        # Canned 5-file curated index — every test target file present.
        from app.features.demo.pipeline import _USER_GUIDE_CURATED_FILES

        results = [
            {"source_path": p, "status": "indexed", "chunks_created": 4, "error": None}
            for p in sorted(_USER_GUIDE_CURATED_FILES)
        ]
        return {
            "results": results,
            "total_files": 5,
            "indexed": 5,
            "updated": 0,
            "unchanged": 0,
            "failed": 0,
            "total_chunks": 20,
            "duration_ms": 120.0,
        }
    if path == "/rag/retrieve":
        return {
            "results": [
                {
                    "source_path": "docs/user-guide/getting-started.md",
                    "content": "demo content...",
                    "relevance_score": 0.87,
                    "chunk_index": 0,
                }
            ],
            "total_chunks_searched": 20,
        }
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
    if path.startswith("/registry/runs/"):
        # PATCH pending->running->success returns an empty (200) body. The
        # PRP-40 GET /registry/runs/{run_id} branch is handled earlier in
        # this function (returns artifact_uri).
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
            return _canned_response(path, json_body, artifact_path, wapes, method=method)

    return _FakeClient


def _fake_settings(
    registry_root: str,
    *,
    rag_embedding_provider: str = "openai",
    openai_api_key: str = "sk-test",
) -> SimpleNamespace:
    """Fake settings: usable registry root, no agent LLM key (agent skips).

    ``rag_embedding_provider`` defaults to "openai" with a present key so the
    PRP-40 knowledge phase runs to completion in test fixtures; the
    knowledge-skip tests override via ``rag_embedding_provider="openai"`` +
    ``openai_api_key=""`` (or "ollama" with an unreachable canned probe).
    """
    return SimpleNamespace(
        registry_artifact_root=registry_root,
        agent_default_model="anthropic:claude-test",
        anthropic_api_key="",
        openai_api_key=openai_api_key,
        google_api_key="",
        rag_embedding_provider=rag_embedding_provider,
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


def test_phase_table_showcase_rich_adds_v2_decision_portfolio_planning_knowledge_steps():
    """PRP-38 + PRP-39 + PRP-40 — phase_table for SHOWCASE_RICH is the canonical 23 rows.

    PRP-38 shipped 3 (phase2_enrichment, historical_backfill, v2_train).
    PRP-39 added 4 (champion_compat_compare, stale_alias_trigger,
    safer_promote_flow, batch_preset) plus a new ``portfolio`` phase between
    ``decision`` and ``verify``.
    PRP-40 adds 5 (scenario_simulate_and_save, multi_plan_compare,
    embedding_provider_probe, rag_index_subset, rag_retrieve_probe) under two
    new ``planning`` + ``knowledge`` phases, AFTER portfolio and BEFORE verify
    via a relative anchor. Total: 23 rows across 9 phases.
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
        # PRP-39 — portfolio phase between decision and verify.
        ("portfolio", "batch_preset"),
        # PRP-40 — planning + knowledge phases after portfolio, before verify.
        ("planning", "scenario_simulate_and_save"),
        ("planning", "multi_plan_compare"),
        ("knowledge", "embedding_provider_probe"),
        ("knowledge", "rag_index_subset"),
        ("knowledge", "rag_retrieve_probe"),
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


async def test_run_pipeline_showcase_rich_emits_23_steps(monkeypatch, tmp_path):
    """PRP-38 + PRP-39 + PRP-40 — SHOWCASE_RICH = 11 base + 3 PRP-38 + 4 PRP-39 + 5 PRP-40 = 23 total steps.

    PRP-38 shipped 3 (phase2_enrichment + historical_backfill + v2_train).
    PRP-39 added 4 (champion_compat_compare + stale_alias_trigger +
    safer_promote_flow + batch_preset).
    PRP-40 adds 5 (scenario_simulate_and_save + multi_plan_compare +
    embedding_provider_probe + rag_index_subset + rag_retrieve_probe).
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
    assert len(completes) == 23
    # Every event reports total_steps=23
    for ev in completes:
        assert ev.total_steps == 23


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


# =============================================================================
# PRP-40 — Helpers + planning/knowledge step unit tests
# =============================================================================


def test_parse_artifact_key_v1_demo_path():
    """PRP-40 — V1 demo path: 'demo/{model_type}-model_{KEY}.joblib'."""
    key = pipeline._parse_artifact_key("demo/seasonal_naive-model_abc123def456.joblib")
    assert key == "abc123def456"


def test_parse_artifact_key_v2_artifacts_models_path():
    """PRP-40 — V2 path: 'artifacts/models/model_{KEY}.joblib'."""
    key = pipeline._parse_artifact_key("artifacts/models/model_deadbeef0042.joblib")
    assert key == "deadbeef0042"


def test_parse_artifact_key_rejects_unparseable():
    """PRP-40 — a malformed artifact_uri raises ValueError (not a silent miss)."""
    import pytest

    with pytest.raises(ValueError, match="Cannot parse artifact-key"):
        pipeline._parse_artifact_key("not-a-model-uri.bin")


class _RecordingClient:
    """A minimal stand-in for pipeline._Client recording every call.

    Tests pass a dict of (method, path) -> response body; missing entries
    raise AssertionError so unexpected requests show up loudly.
    """

    def __init__(
        self,
        _app: Any,
        responses: dict[tuple[str, str], Any] | None = None,
        errors: dict[tuple[str, str], pipeline._StepError] | None = None,
    ) -> None:
        self._responses = responses or {}
        self._errors = errors or {}
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    async def __aenter__(self) -> _RecordingClient:
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
        self.calls.append((method, path, json_body))
        key = (method, path)
        if key in self._errors:
            raise self._errors[key]
        if key in self._responses:
            response = self._responses[key]
            if not isinstance(response, dict):
                raise AssertionError(
                    f"canned response for {key!r} must be a dict, got {type(response)}"
                )
            return cast("dict[str, Any]", response)
        raise AssertionError(f"unexpected request: method={method!r} path={path!r}")


def _as_client(rec: _RecordingClient) -> pipeline._Client:
    """Cast a _RecordingClient stand-in to the real _Client type for typecheckers.

    The stand-in is structurally compatible with pipeline._Client (same async
    ``request`` signature) but mypy can't see that since the real _Client is
    not declared as a Protocol. ``cast`` is the load-bearing escape hatch.
    """
    return cast("pipeline._Client", rec)


def _make_showcase_ctx(scenario: ScenarioPreset = ScenarioPreset.SHOWCASE_RICH) -> Any:
    """Build a DemoContext positioned at the start of the planning phase."""
    from datetime import date as date_type

    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False, scenario=scenario)
    ctx.store_id = 7
    ctx.product_id = 3
    ctx.date_start = date_type(2024, 1, 1)
    ctx.date_end = date_type(2024, 12, 31)
    ctx.winner_model_type = "seasonal_naive"
    ctx.winning_run_id = "demo-run-abc123def456"
    return ctx


async def test_scenario_simulate_and_save_happy_path():
    """PRP-40 — happy path: resolves alias -> run -> artifact_key, saves plan."""
    ctx = _make_showcase_ctx()
    client = _RecordingClient(
        None,
        responses={
            (
                "GET",
                "/registry/aliases/demo-production",
            ): {"alias_name": "demo-production", "run_id": "uuid-32-char"},
            ("GET", "/registry/runs/uuid-32-char"): {
                "run_id": "uuid-32-char",
                "artifact_uri": "demo/seasonal_naive-model_abc123def456.joblib",
            },
            ("POST", "/scenarios"): {
                "scenario_id": "scn-001",
                "comparison": {
                    "method": "heuristic",
                    "units_delta": -25.5,
                    "revenue_delta": -180.0,
                },
            },
        },
    )
    status, detail, data = await pipeline.step_scenario_simulate_and_save(ctx, _as_client(client))
    assert status == "pass"
    assert ctx.scenario_artifact_key == "abc123def456"
    assert ctx.price_cut_scenario_id == "scn-001"
    assert data["method"] == "heuristic"
    assert data["units_delta"] == -25.5
    assert data["revenue_delta"] == -180.0
    assert data["artifact_key"] == "abc123def456"
    assert "showcase-price-cut-10pct" in detail
    assert "heuristic" in detail
    # The POST /scenarios body carried the additive price assumption.
    save_call = next(c for c in client.calls if c[0] == "POST" and c[1] == "/scenarios")
    body = save_call[2]
    assert body is not None
    assert body["name"] == "showcase-price-cut-10pct"
    assert body["run_id"] == "abc123def456"
    assert body["assumptions"]["price"]["change_pct"] == -0.10
    assert body["tags"] == ["showcase", "price"]


async def test_scenario_simulate_and_save_missing_alias_fails():
    """PRP-40 — alias missing run_id -> FAIL with clear detail."""
    ctx = _make_showcase_ctx()
    client = _RecordingClient(
        None,
        responses={
            ("GET", "/registry/aliases/demo-production"): {"alias_name": "demo-production"},
        },
    )
    status, detail, _ = await pipeline.step_scenario_simulate_and_save(ctx, _as_client(client))
    assert status == "fail"
    assert "no run_id" in detail


async def test_scenario_simulate_and_save_unparseable_artifact_uri_fails():
    """PRP-40 — artifact_uri the regex can't parse -> FAIL."""
    ctx = _make_showcase_ctx()
    client = _RecordingClient(
        None,
        responses={
            ("GET", "/registry/aliases/demo-production"): {"run_id": "uuid"},
            ("GET", "/registry/runs/uuid"): {"artifact_uri": "garbage-path.bin"},
        },
    )
    status, detail, _ = await pipeline.step_scenario_simulate_and_save(ctx, _as_client(client))
    assert status == "fail"
    assert "artifact-key" in detail


async def test_multi_plan_compare_happy_path():
    """PRP-40 — happy path: second-plan save + compare returns ranked list."""
    ctx = _make_showcase_ctx()
    ctx.price_cut_scenario_id = "scn-price"
    ctx.scenario_artifact_key = "abc123def456"
    client = _RecordingClient(
        None,
        responses={
            ("POST", "/scenarios"): {
                "scenario_id": "scn-holiday",
                "comparison": {"method": "heuristic"},
            },
            ("POST", "/scenarios/compare"): {
                "scenarios": [
                    {
                        "scenario_id": "scn-holiday",
                        "name": "showcase-holiday-uplift",
                        "units_delta": 18.5,
                        "revenue_delta": 220.0,
                        "coverage_verdict": "ok",
                        "rank": 1,
                    },
                    {
                        "scenario_id": "scn-price",
                        "name": "showcase-price-cut-10pct",
                        "units_delta": -25.5,
                        "revenue_delta": -180.0,
                        "coverage_verdict": "ok",
                        "rank": 2,
                    },
                ],
            },
        },
    )
    status, detail, data = await pipeline.step_multi_plan_compare(ctx, _as_client(client))
    assert status == "pass"
    assert ctx.holiday_scenario_id == "scn-holiday"
    assert data["winner_scenario_id"] == "scn-holiday"
    assert data["winner_name"] == "showcase-holiday-uplift"
    assert data["ranked_by"] == "revenue_delta"
    assert len(data["ranked"]) == 2
    assert "winner=showcase-holiday-uplift" in detail


async def test_multi_plan_compare_second_save_failure_emits_warn():
    """PRP-40 R19 — second-plan POST 4xx -> WARN, NOT FAIL (partial success)."""
    ctx = _make_showcase_ctx()
    ctx.price_cut_scenario_id = "scn-price"
    ctx.scenario_artifact_key = "abc123def456"
    client = _RecordingClient(
        None,
        errors={
            ("POST", "/scenarios"): pipeline._StepError(
                "multi_plan_compare[save]",
                422,
                {"title": "Unprocessable Entity", "detail": "horizon out of range"},
            ),
        },
    )
    status, detail, data = await pipeline.step_multi_plan_compare(ctx, _as_client(client))
    assert status == "warn"
    assert "holiday-plan save failed" in detail
    assert data["price_cut_scenario_id"] == "scn-price"


async def test_multi_plan_compare_fails_without_price_cut_plan():
    """PRP-40 — missing prior-step state -> FAIL with clear detail."""
    ctx = _make_showcase_ctx()  # price_cut_scenario_id stays None
    client = _RecordingClient(None)
    status, detail, _ = await pipeline.step_multi_plan_compare(ctx, _as_client(client))
    assert status == "fail"
    assert "price_cut plan not saved" in detail


async def test_embedding_provider_probe_reachable_openai(monkeypatch, tmp_path):
    """PRP-40 — openai key present -> PASS + ctx.embedding_unreachable=False."""
    monkeypatch.setattr(
        pipeline,
        "get_settings",
        lambda: _fake_settings(
            str(tmp_path / "reg"),
            rag_embedding_provider="openai",
            openai_api_key="sk-test",
        ),
    )
    ctx = _make_showcase_ctx()
    client = _RecordingClient(None)
    status, detail, data = await pipeline.step_embedding_provider_probe(ctx, _as_client(client))
    assert status == "pass"
    assert ctx.embedding_unreachable is False
    assert data["provider"] == "openai"
    assert data["reachable"] is True
    assert "reachable=True" in detail


async def test_embedding_provider_probe_unreachable_openai(monkeypatch, tmp_path):
    """PRP-40 — openai with empty key -> PASS + ctx.embedding_unreachable=True."""
    monkeypatch.setattr(
        pipeline,
        "get_settings",
        lambda: _fake_settings(
            str(tmp_path / "reg"),
            rag_embedding_provider="openai",
            openai_api_key="",
        ),
    )
    ctx = _make_showcase_ctx()
    client = _RecordingClient(None)
    status, detail, data = await pipeline.step_embedding_provider_probe(ctx, _as_client(client))
    assert status == "pass"
    assert ctx.embedding_unreachable is True
    assert data["reachable"] is False
    assert "knowledge phase will skip" in detail


async def test_embedding_provider_probe_ollama_reachable(monkeypatch, tmp_path):
    """PRP-40 — ollama provider live-probed via /config/providers/health."""
    monkeypatch.setattr(
        pipeline,
        "get_settings",
        lambda: _fake_settings(
            str(tmp_path / "reg"),
            rag_embedding_provider="ollama",
        ),
    )
    ctx = _make_showcase_ctx()
    # _Client wraps a list response as {"_raw": [...]}.
    client = _RecordingClient(
        None,
        responses={
            ("GET", "/config/providers/health"): {
                "_raw": [
                    {"provider": "ollama", "reachable": True, "detail": "ok", "models": []},
                ]
            },
        },
    )
    status, _detail, data = await pipeline.step_embedding_provider_probe(ctx, _as_client(client))
    assert status == "pass"
    assert ctx.embedding_unreachable is False
    assert data["provider"] == "ollama"
    assert data["reachable"] is True


async def test_embedding_provider_probe_ollama_unreachable(monkeypatch, tmp_path):
    """PRP-40 — ollama probe returns reachable=False -> ctx.embedding_unreachable."""
    monkeypatch.setattr(
        pipeline,
        "get_settings",
        lambda: _fake_settings(
            str(tmp_path / "reg"),
            rag_embedding_provider="ollama",
        ),
    )
    ctx = _make_showcase_ctx()
    client = _RecordingClient(
        None,
        responses={
            ("GET", "/config/providers/health"): {
                "_raw": [
                    {"provider": "ollama", "reachable": False, "detail": "down", "models": []},
                ]
            },
        },
    )
    status, _, data = await pipeline.step_embedding_provider_probe(ctx, _as_client(client))
    assert status == "pass"
    assert ctx.embedding_unreachable is True
    assert data["reachable"] is False


async def test_rag_index_subset_happy_path():
    """PRP-40 — index subset returns curated_hits + total_chunks counters."""
    ctx = _make_showcase_ctx()
    results = [
        {"source_path": p, "status": "indexed", "chunks_created": 4, "error": None}
        for p in sorted(pipeline._USER_GUIDE_CURATED_FILES)
    ]
    client = _RecordingClient(
        None,
        responses={
            ("POST", "/rag/index/project-docs"): {
                "results": results,
                "total_files": 5,
                "indexed": 5,
                "updated": 0,
                "unchanged": 0,
                "failed": 0,
                "total_chunks": 20,
                "duration_ms": 120.0,
            },
        },
    )
    status, detail, data = await pipeline.step_rag_index_subset(ctx, _as_client(client))
    assert status == "pass"
    assert data["curated_hits"] == 5
    assert data["total_chunks"] == 20
    assert "files_indexed=5/5" in detail
    # The POST body carried path_prefix="docs/user-guide".
    body = client.calls[0][2]
    assert body is not None
    assert body["path_prefix"] == "docs/user-guide"
    assert body["include_docs"] is True
    assert body["include_prps"] is False
    assert body["include_root"] is False


async def test_rag_index_subset_skips_when_provider_unreachable():
    """PRP-40 — skip with detail 'embedding provider unreachable'; no HTTP call."""
    ctx = _make_showcase_ctx()
    ctx.embedding_unreachable = True
    client = _RecordingClient(None)  # any call would AssertionError
    status, detail, _ = await pipeline.step_rag_index_subset(ctx, _as_client(client))
    assert status == "skip"
    assert "unreachable" in detail
    assert client.calls == []


async def test_rag_retrieve_probe_happy_path():
    """PRP-40 — top hit + similarity score surface on PASS."""
    ctx = _make_showcase_ctx()
    client = _RecordingClient(
        None,
        responses={
            ("POST", "/rag/retrieve"): {
                "results": [
                    {
                        "source_path": "docs/user-guide/getting-started.md",
                        "content": "...",
                        "relevance_score": 0.87,
                        "chunk_index": 0,
                    }
                ],
                "total_chunks_searched": 20,
            },
        },
    )
    status, detail, data = await pipeline.step_rag_retrieve_probe(ctx, _as_client(client))
    assert status == "pass"
    assert data["results_count"] == 1
    assert data["top_source_path"] == "docs/user-guide/getting-started.md"
    assert data["top_relevance_score"] == 0.87
    assert "score=0.870" in detail


async def test_rag_retrieve_probe_zero_hits_emits_warn():
    """PRP-40 — empty results list -> WARN (not FAIL); pipeline still green."""
    ctx = _make_showcase_ctx()
    client = _RecordingClient(
        None,
        responses={
            ("POST", "/rag/retrieve"): {"results": [], "total_chunks_searched": 0},
        },
    )
    status, detail, data = await pipeline.step_rag_retrieve_probe(ctx, _as_client(client))
    assert status == "warn"
    assert "no hits" in detail
    assert data["results_count"] == 0


async def test_rag_retrieve_probe_skips_when_provider_unreachable():
    """PRP-40 — skip when ctx.embedding_unreachable; no HTTP call."""
    ctx = _make_showcase_ctx()
    ctx.embedding_unreachable = True
    client = _RecordingClient(None)
    status, detail, _ = await pipeline.step_rag_retrieve_probe(ctx, _as_client(client))
    assert status == "skip"
    assert "unreachable" in detail
    assert client.calls == []


async def test_run_pipeline_showcase_rich_runs_planning_and_knowledge(monkeypatch, tmp_path):
    """PRP-40 — end-to-end SHOWCASE_RICH reaches the 5 new steps + greens."""
    artifact = tmp_path / "artifacts" / "models" / "model_abc123def456.joblib"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"v2 bundle bytes")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    # prophet_like wins so v2 path is exercised end-to-end.
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

    # The 5 new step cards all emitted terminal statuses.
    assert by_name["scenario_simulate_and_save"].status == "pass"
    assert by_name["scenario_simulate_and_save"].data["method"] == "heuristic"
    assert by_name["multi_plan_compare"].status == "pass"
    assert by_name["multi_plan_compare"].data["ranked_by"] == "revenue_delta"
    assert by_name["embedding_provider_probe"].status == "pass"
    assert by_name["embedding_provider_probe"].data["reachable"] is True
    assert by_name["rag_index_subset"].status == "pass"
    assert by_name["rag_index_subset"].data["curated_hits"] == 5
    assert by_name["rag_retrieve_probe"].status == "pass"
    assert "docs/user-guide" in by_name["rag_retrieve_probe"].data["top_source_path"]

    # Pipeline still greens.
    final = events[-1]
    assert final.event_type == "pipeline_complete"
    assert final.status == "pass"


async def test_run_pipeline_showcase_rich_skips_knowledge_when_provider_unreachable(
    monkeypatch, tmp_path
):
    """PRP-40 C3 — every embedding provider unreachable -> 3x skip; pipeline green."""
    artifact = tmp_path / "artifacts" / "models" / "model_abc123def456.joblib"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"v2 bundle bytes")
    monkeypatch.setattr(
        pipeline,
        "get_settings",
        lambda: _fake_settings(
            str(tmp_path / "reg"),
            rag_embedding_provider="openai",
            openai_api_key="",  # the embedding provider key is absent.
        ),
    )
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

    # Probe still PASSES (always emits pass; just flags downstream to skip).
    assert by_name["embedding_provider_probe"].status == "pass"
    assert by_name["embedding_provider_probe"].data["reachable"] is False
    # Downstream knowledge steps skip.
    assert by_name["rag_index_subset"].status == "skip"
    assert by_name["rag_retrieve_probe"].status == "skip"
    # Pipeline still greens.
    final = events[-1]
    assert final.event_type == "pipeline_complete"
    assert final.status == "pass"
