"""Unit tests for the demo pipeline orchestrator.

The pipeline drives the app over HTTP via ``pipeline._Client``; these tests
monkeypatch ``_Client`` with a canned-response stand-in so the orchestration
logic (step sequencing, winner selection, fail-fast) is exercised with no
database, no network, and no real models.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
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
        # PRP-41 — step_ops_snapshot also consumes this; the additive runs.counts
        # block + extra is_stale flag on the alias drive the KPI tiles.
        return {
            "aliases": [
                {
                    "alias_name": "demo-production",
                    "is_stale": True,
                    "stale_reason": "feature_frame_version_mismatch",
                    "alias_feature_frame_version": 2,
                    "comparable_run_feature_frame_version": 3,
                }
            ],
            "runs": {
                "counts": [
                    {"status": "success", "count": 5},
                    {"status": "failed", "count": 1},
                ],
            },
        }
    if path.startswith("/ops/retraining-candidates"):
        # PRP-41 — canned 2 retraining candidates so step_ops_snapshot's
        # retraining KPI tile renders > 0.
        return {
            "candidates": [
                {"store_id": 7, "product_id": 3, "priority_score": 0.8},
                {"store_id": 7, "product_id": 4, "priority_score": 0.6},
            ],
            "total_evaluated": 2,
            "generated_at": "2026-05-26T10:00:00Z",
        }
    if path.startswith("/ops/model-health"):
        # PRP-41 — 3 health entries; 1 degrading so degrading_count == 1.
        return {
            "entries": [
                {"store_id": 7, "product_id": 3, "drift_direction": "stable"},
                {"store_id": 7, "product_id": 4, "drift_direction": "degrading"},
                {"store_id": 8, "product_id": 3, "drift_direction": "improving"},
            ],
            "total_evaluated": 3,
            "generated_at": "2026-05-26T10:00:00Z",
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
        def __init__(
            self,
            _app: Any,
            *,
            event_sink: list[Any] | None = None,
        ) -> None:
            # PRP-41 — accept the optional event_sink the orchestrator passes
            # in; remember it so ``yield_event`` can feed intermediate frames.
            self.calls: list[tuple[str, str]] = []
            self._event_sink = event_sink

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        def yield_event(self, event: Any) -> None:
            # PRP-41 — mirror pipeline._Client.yield_event semantics.
            if self._event_sink is None:
                return
            self._event_sink.append(event)

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
        def __init__(self, _app: Any, *, event_sink: list[Any] | None = None) -> None:
            self._event_sink = event_sink

        async def __aenter__(self) -> _FailingClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        def yield_event(self, event: Any) -> None:
            if self._event_sink is None:
                return
            self._event_sink.append(event)

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
        def __init__(self, _app: Any, *, event_sink: list[Any] | None = None) -> None:
            self._event_sink = event_sink

        async def __aenter__(self) -> _BrokenClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        def yield_event(self, event: Any) -> None:
            if self._event_sink is None:
                return
            self._event_sink.append(event)

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


def test_phase_table_demo_minimal_matches_legacy_11_steps_under_agents_phase():
    """PRP-38 / PRP-41 — DEMO_MINIMAL keeps the legacy 11-step flow.

    PRP-41 — design Z: the legacy ``step_agent`` row now lives under the
    unified ``agents`` phase id (was ``agent``). The step name stays
    ``agent`` so the wire payload + the frontend's legacy step rendering
    keep working. Step count unchanged.
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
        ("agents", "agent"),
        ("cleanup", "cleanup"),
    ]


def test_phase_table_showcase_rich_emits_24_steps_with_agents_hitl_and_ops_snapshot():
    """PRP-38 + PRP-39 + PRP-40 + PRP-41 — SHOWCASE_RICH is the canonical 24 rows.

    PRP-38 shipped 3 (phase2_enrichment, historical_backfill, v2_train).
    PRP-39 added 4 (champion_compat_compare, stale_alias_trigger,
    safer_promote_flow, batch_preset) plus a new ``portfolio`` phase between
    ``decision`` and ``verify``.
    PRP-40 added 5 (scenario_simulate_and_save, multi_plan_compare,
    embedding_provider_probe, rag_index_subset, rag_retrieve_probe) under two
    new ``planning`` + ``knowledge`` phases, AFTER portfolio and BEFORE verify
    via a relative anchor.
    PRP-41 — design Z: SHOWCASE_RICH swaps the legacy ``agent`` step for
    ``agent_hitl_flow`` (HITL approval round-trip) under the unified
    ``agents`` phase id, AND appends a new ``ops`` phase carrying
    ``ops_snapshot`` IMMEDIATELY AFTER ``agents``, BEFORE ``cleanup``.
    Total: 24 rows across 10 phases.
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
        # PRP-41 — agents (HITL) + ops snapshot, both under new phase ids.
        ("agents", "agent_hitl_flow"),
        ("ops", "ops_snapshot"),
        ("cleanup", "cleanup"),
    ]


@pytest.mark.parametrize(
    "preset",
    [
        ScenarioPreset.RETAIL_STANDARD,
        ScenarioPreset.HOLIDAY_RUSH,
        ScenarioPreset.HIGH_VARIANCE,
        ScenarioPreset.STOCKOUT_HEAVY,
        ScenarioPreset.NEW_LAUNCHES,
        ScenarioPreset.SPARSE,
    ],
)
def test_phase_table_non_showcase_presets_match_demo_minimal_shape(preset: ScenarioPreset):
    """PRP-38 / E2 (#391) — only SHOWCASE_RICH extends the pipeline.

    Every other preset (incl. the 5 newly exposed by E2) runs the legacy
    11-step flow; the picker offers them as data-shape variations only.
    """
    rows = pipeline._phase_table(preset)
    minimal_rows = pipeline._phase_table(ScenarioPreset.DEMO_MINIMAL)
    assert [(p, s) for p, s, _ in rows] == [(p, s) for p, s, _ in minimal_rows]


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
    # PRP-41 — design Z renames the legacy "agent" phase to "agents" for ALL
    # scenarios. Demo_minimal still emits 6 phases (data/modeling/decision/
    # verify/agents/cleanup); ops is showcase_rich-only.
    for ev in step_events:
        assert ev.phase_name in {"data", "modeling", "decision", "verify", "agents", "cleanup"}
        assert ev.phase_index is not None and ev.phase_index >= 1
        assert ev.phase_total == 6
    # Verify phases appear in canonical order.
    phases_seen = []
    for ev in step_events:
        if ev.phase_name and ev.phase_name not in phases_seen:
            phases_seen.append(ev.phase_name)
    assert phases_seen == ["data", "modeling", "decision", "verify", "agents", "cleanup"]


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


async def test_run_pipeline_showcase_rich_emits_24_steps(monkeypatch, tmp_path):
    """PRP-38 + PRP-39 + PRP-40 + PRP-41 — SHOWCASE_RICH = 24 total steps.

    11 base + 3 PRP-38 + 4 PRP-39 + 5 PRP-40 + 1 PRP-41 (ops_snapshot — the
    legacy `agent` step is swapped for `agent_hitl_flow` not added, hence
    +1 net for PRP-41).
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
    assert len(completes) == 24
    # Every event reports total_steps=24
    for ev in completes:
        assert ev.total_steps == 24


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


def test__showcase_plan_tags_ephemeral():
    """E3 (#392) — no workspace row -> base triple only, no workspace tag."""
    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False)
    assert pipeline._showcase_plan_tags(ctx, "price") == [
        "showcase",
        "price",
        "source:showcase",
    ]


def test__showcase_plan_tags_keep_named():
    """E3 (#392) — keep run with a name -> workspace:<name> appended."""
    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False)
    ctx.workspace_id = "a" * 32
    ctx.workspace_name = "bf-demo"
    assert pipeline._showcase_plan_tags(ctx, "holiday") == [
        "showcase",
        "holiday",
        "source:showcase",
        "workspace:bf-demo",
    ]


def test__showcase_plan_tags_keep_unnamed_falls_back_to_workspace_id():
    """E3 (#392) — keep run without a name -> workspace:<workspace_id>."""
    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False)
    ctx.workspace_id = "f" * 32
    assert pipeline._showcase_plan_tags(ctx, "price") == [
        "showcase",
        "price",
        "source:showcase",
        f"workspace:{'f' * 32}",
    ]


async def test_scenario_simulate_and_save_happy_path():
    """PRP-40 + #324 — resolves the champion via ctx.winning_run_id -> run ->
    artifact_key, saves the plan. Must NOT read the demo-production alias
    (safer_promote_flow deliberately corrupts it)."""
    ctx = _make_showcase_ctx()  # winning_run_id = "demo-run-abc123def456"
    client = _RecordingClient(
        None,
        responses={
            ("GET", "/registry/runs/demo-run-abc123def456"): {
                "run_id": "demo-run-abc123def456",
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
    assert body["tags"] == ["showcase", "price", "source:showcase"]
    # E3 (#392) — the step data echoes the tags it sent.
    assert data["tags"] == ["showcase", "price", "source:showcase"]
    # #324 — the safer-promote-corrupted demo-production alias must NOT be read.
    assert all(path != "/registry/aliases/demo-production" for _m, path, _b in client.calls)


async def test_scenario_simulate_and_save_keep_run_carries_workspace_tag():
    """E3 (#392) — a keep run (workspace_id set) stamps workspace:<name>."""
    ctx = _make_showcase_ctx()
    ctx.workspace_id = "a" * 32
    ctx.workspace_name = "bf-demo"
    client = _RecordingClient(
        None,
        responses={
            ("GET", "/registry/runs/demo-run-abc123def456"): {
                "run_id": "demo-run-abc123def456",
                "artifact_uri": "demo/seasonal_naive-model_abc123def456.joblib",
            },
            ("POST", "/scenarios"): {
                "scenario_id": "scn-001",
                "comparison": {"method": "heuristic"},
            },
        },
    )
    status, _detail, data = await pipeline.step_scenario_simulate_and_save(ctx, _as_client(client))
    assert status == "pass"
    save_call = next(c for c in client.calls if c[0] == "POST" and c[1] == "/scenarios")
    body = save_call[2]
    assert body is not None
    assert body["tags"] == ["showcase", "price", "source:showcase", "workspace:bf-demo"]
    assert data["tags"] == ["showcase", "price", "source:showcase", "workspace:bf-demo"]


async def test_scenario_simulate_and_save_missing_champion_falls_back_to_alias():
    """PRP-40 + #324 — with no champion recorded, fall back to the alias; an
    alias missing run_id -> FAIL with clear detail."""
    ctx = _make_showcase_ctx()
    ctx.winning_run_id = None  # force the defensive alias fallback
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
    """PRP-40 — the champion run's artifact_uri the regex can't parse -> FAIL."""
    ctx = _make_showcase_ctx()  # winning_run_id = "demo-run-abc123def456"
    client = _RecordingClient(
        None,
        responses={
            ("GET", "/registry/runs/demo-run-abc123def456"): {"artifact_uri": "garbage-path.bin"},
        },
    )
    status, detail, _ = await pipeline.step_scenario_simulate_and_save(ctx, _as_client(client))
    assert status == "fail"
    assert "artifact-key" in detail


async def test_scenario_simulate_and_save_ignores_corrupted_demo_alias():
    """#324 regression — the step resolves the champion via ctx.winning_run_id
    and never consults the safer-promote-corrupted demo-production alias."""
    ctx = _make_showcase_ctx()  # winning_run_id = "demo-run-abc123def456"
    client = _RecordingClient(
        None,
        responses={
            ("GET", "/registry/runs/demo-run-abc123def456"): {
                "artifact_uri": "demo/seasonal_naive-model_abc123def456.joblib",
            },
            ("POST", "/scenarios"): {
                "scenario_id": "scn-001",
                "comparison": {"method": "heuristic", "units_delta": 1.0, "revenue_delta": 2.0},
            },
        },
    )
    status, _detail, _data = await pipeline.step_scenario_simulate_and_save(ctx, _as_client(client))
    assert status == "pass"
    assert ctx.scenario_artifact_key == "abc123def456"
    assert all(path != "/registry/aliases/demo-production" for _m, path, _b in client.calls)


def test_parse_artifact_key_rejects_safer_promote_placeholder():
    """#324 regression — the OLD PRP-39 placeholder artifact_uri is unparseable
    (the exact failure the cascade surfaced); the NEW real-shape safer-promote
    URI parses cleanly."""
    import pytest

    with pytest.raises(ValueError, match="Cannot parse artifact-key"):
        pipeline._parse_artifact_key("demo/safer-promote-placeholder.joblib")
    assert (
        pipeline._parse_artifact_key("demo/seasonal_naive-model_abcdef012345.joblib")
        == "abcdef012345"
    )


def test_format_demo_artifact_key_round_trips_through_parser():
    """#324 — _format_demo_artifact_key strips dashes + truncates to a hex-only
    key that round-trips through _parse_artifact_key (producer/parser in sync)."""
    key = pipeline._format_demo_artifact_key("1234abcd-5678-90ef-dead-beef00112233")
    assert key == "1234abcd5678"
    assert len(key) == pipeline._DEMO_ARTIFACT_KEY_LEN
    uri = f"demo/seasonal_naive-model_{key}.joblib"
    assert pipeline._parse_artifact_key(uri) == key


class _AliasRestoreSpyClient:
    """Minimal _Client stand-in recording alias-restore POSTs (#324 safeguard)."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self._fail = fail

    async def request(
        self,
        step: str,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((method, path, json_body))
        if self._fail:
            raise OSError("simulated transport failure")
        return {}


async def test_restore_demo_alias_after_failure_repoints_to_original():
    """#324 — a mid-run failure must restore demo-production to the champion."""
    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False)
    ctx.original_demo_alias_run_id = "champion-run-123"
    spy = _AliasRestoreSpyClient()
    await pipeline._restore_demo_alias_after_failure(ctx, cast("pipeline._Client", spy))
    assert len(spy.calls) == 1
    method, path, body = spy.calls[0]
    assert method == "POST"
    assert path == "/registry/aliases"
    assert body is not None
    assert body["alias_name"] == pipeline.DEMO_ALIAS
    assert body["run_id"] == "champion-run-123"


async def test_restore_demo_alias_after_failure_noop_without_swap():
    """#324 — no original alias captured (no swap happened) -> no restore call."""
    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False)
    ctx.original_demo_alias_run_id = None
    spy = _AliasRestoreSpyClient()
    await pipeline._restore_demo_alias_after_failure(ctx, cast("pipeline._Client", spy))
    assert spy.calls == []


async def test_restore_demo_alias_after_failure_swallows_errors():
    """#324 — the safeguard must never raise (must not mask the original fail)."""
    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False)
    ctx.original_demo_alias_run_id = "champion-run-123"
    spy = _AliasRestoreSpyClient(fail=True)
    await pipeline._restore_demo_alias_after_failure(ctx, cast("pipeline._Client", spy))  # no raise
    assert len(spy.calls) == 1


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
    # E3 (#392) — the holiday-plan save carries the ephemeral tag triple.
    save_call = next(c for c in client.calls if c[0] == "POST" and c[1] == "/scenarios")
    body = save_call[2]
    assert body is not None
    assert body["tags"] == ["showcase", "holiday", "source:showcase"]


async def test_multi_plan_compare_keep_run_carries_workspace_tag():
    """E3 (#392) — the workspace tag flows to plan #2 on keep runs."""
    ctx = _make_showcase_ctx()
    ctx.price_cut_scenario_id = "scn-price"
    ctx.scenario_artifact_key = "abc123def456"
    ctx.workspace_id = "b" * 32
    ctx.workspace_name = "bf-demo"
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
                ],
            },
        },
    )
    status, _detail, _data = await pipeline.step_multi_plan_compare(ctx, _as_client(client))
    assert status == "pass"
    save_call = next(c for c in client.calls if c[0] == "POST" and c[1] == "/scenarios")
    body = save_call[2]
    assert body is not None
    assert body["tags"] == ["showcase", "holiday", "source:showcase", "workspace:bf-demo"]


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


async def test_rag_index_subset_skips_on_embedding_auth_502():
    """#329 — an EMBEDDING_AUTH 502 (invalid/placeholder key) SKIPs, not FAILs.

    The probe only checks key presence, so a bad key reaches the index call and
    502s with the machine-readable EMBEDDING_AUTH marker. The step classifies it
    and skips, and marks the context so the retrieve probe skips too.
    """
    ctx = _make_showcase_ctx()
    assert ctx.embedding_unreachable is False
    client = _RecordingClient(
        None,
        errors={
            ("POST", "/rag/index/project-docs"): pipeline._StepError(
                "rag_index_subset",
                502,
                {
                    "type": "/errors/embedding-auth",
                    "title": "Embedding Auth",
                    "status": 502,
                    "code": "EMBEDDING_AUTH",
                    "detail": "Embedding provider rejected the credentials",
                },
            ),
        },
    )
    status, detail, _ = await pipeline.step_rag_index_subset(ctx, _as_client(client))
    assert status == "skip"
    assert "rejected credentials" in detail
    # The call WAS attempted (unlike the unreachable case)...
    assert len(client.calls) == 1
    # ...and the context is now marked so the retrieve probe skips too.
    assert ctx.embedding_unreachable is True


async def test_rag_index_subset_skips_on_embedding_auth_type_only():
    """#329 — classification by `type` alone (no `code`) still SKIPs gracefully.

    The classifier accepts a problem whose `type` URI's final path segment is
    `embedding-auth` even when there is no `code` field — and even when the
    `type` is a fully-qualified absolute URI rather than the canonical relative
    one. The step must still skip and flag the context.
    """
    ctx = _make_showcase_ctx()
    assert ctx.embedding_unreachable is False
    client = _RecordingClient(
        None,
        errors={
            ("POST", "/rag/index/project-docs"): pipeline._StepError(
                "rag_index_subset",
                502,
                {
                    # No "code" key — only an absolute "type" ending in the slug.
                    "type": "https://errors.example.com/rag/embedding-auth",
                    "title": "Embedding Auth",
                    "status": 502,
                    "detail": "Embedding provider rejected the credentials",
                },
            ),
        },
    )
    status, detail, _ = await pipeline.step_rag_index_subset(ctx, _as_client(client))
    assert status == "skip"
    assert "rejected credentials" in detail
    assert len(client.calls) == 1
    assert ctx.embedding_unreachable is True


async def test_rag_index_subset_reraises_non_auth_502():
    """#329 — a non-auth 502 (e.g. connection failure) still propagates as FAIL."""
    import pytest

    ctx = _make_showcase_ctx()
    client = _RecordingClient(
        None,
        errors={
            ("POST", "/rag/index/project-docs"): pipeline._StepError(
                "rag_index_subset",
                502,
                {"title": "Bad Gateway", "detail": "Embedding generation failed: timeout"},
            ),
        },
    )
    with pytest.raises(pipeline._StepError):
        await pipeline.step_rag_index_subset(ctx, _as_client(client))
    assert ctx.embedding_unreachable is False


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


async def test_rag_retrieve_probe_skips_on_embedding_auth_502():
    """#329 — retrieve also classifies an EMBEDDING_AUTH 502 as SKIP, not FAIL."""
    ctx = _make_showcase_ctx()
    client = _RecordingClient(
        None,
        errors={
            ("POST", "/rag/retrieve"): pipeline._StepError(
                "rag_retrieve_probe",
                502,
                {
                    "type": "/errors/embedding-auth",
                    "title": "Embedding Auth",
                    "status": 502,
                    "code": "EMBEDDING_AUTH",
                    "detail": "Embedding provider rejected the credentials",
                },
            ),
        },
    )
    status, detail, _ = await pipeline.step_rag_retrieve_probe(ctx, _as_client(client))
    assert status == "skip"
    assert "rejected credentials" in detail
    assert ctx.embedding_unreachable is True


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


# =============================================================================
# PRP-41 — agents (HITL) + ops snapshot per-step unit tests
# =============================================================================


def _make_hitl_client(
    *,
    chat_pending: bool = True,
    chat_action_id: str = "action-abc-123",
    approve_status: int = 200,
    approve_body: dict[str, Any] | None = None,
    session_id: str = "sess-test-0001",
    capture_intermediate: bool = True,
) -> tuple[Any, list[Any]]:
    """Build a fake client that replays the HITL chat+approve round-trip.

    Returns ``(client, intermediate_events)`` so a test can assert what the
    HITL step buffered into the event sink.
    """
    intermediate: list[Any] = []

    class _HitlClient:
        def __init__(
            self,
            _app: Any = None,
            *,
            event_sink: list[Any] | None = None,
        ) -> None:
            self.calls: list[tuple[str, str]] = []
            self._event_sink = event_sink if event_sink is not None else intermediate

        async def __aenter__(self) -> _HitlClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        def yield_event(self, event: Any) -> None:
            if not capture_intermediate or self._event_sink is None:
                return
            self._event_sink.append(event)

        async def request(
            self,
            step: str,
            method: str,
            path: str,
            *,
            json_body: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            self.calls.append((method, path))
            if path == "/agents/sessions":
                return {"session_id": session_id, "agent_type": "experiment"}
            if path.endswith("/chat"):
                if chat_pending:
                    return {
                        "session_id": session_id,
                        "message": "I'll save that scenario.",
                        "tool_calls": [{"tool_name": "tool_save_scenario", "tool_call_id": "tc-1"}],
                        "pending_approval": True,
                        "pending_action": {
                            "action_id": chat_action_id,
                            "action_type": "save_scenario",
                        },
                        "tokens_used": 240,
                    }
                return {
                    "session_id": session_id,
                    "message": "Done.",
                    "tool_calls": [],
                    "pending_approval": False,
                    "pending_action": None,
                    "tokens_used": 80,
                }
            if path.endswith("/approve"):
                if approve_status >= 400:
                    raise pipeline._StepError(
                        step,
                        approve_status,
                        {"title": "Bad Request", "detail": "No pending action"},
                    )
                return approve_body or {
                    "action_id": chat_action_id,
                    "approved": True,
                    "status": "executed",
                }
            raise AssertionError(f"unexpected request: {method} {path}")

    return _HitlClient(event_sink=intermediate), intermediate


def test_llm_key_present_ollama_needs_no_key(monkeypatch):
    """#340 — the local ollama provider needs no API key, so the gate is True.

    Without this, a local-Ollama stack (agent_default_model=ollama:*) makes the
    showcase agent_hitl_flow / agent steps skip with "no API key matching
    agent_default_model provider" even though Ollama is reachable.
    """
    monkeypatch.setattr(
        pipeline,
        "get_settings",
        lambda: SimpleNamespace(
            agent_default_model="ollama:qwen3:8b",
            anthropic_api_key="",
            openai_api_key="",
            google_api_key="",
        ),
    )
    assert pipeline._llm_key_present() is True


def test_llm_key_present_cloud_still_requires_key(monkeypatch):
    """Regression guard for #340 — a cloud provider still requires its key."""
    monkeypatch.setattr(
        pipeline,
        "get_settings",
        lambda: SimpleNamespace(
            agent_default_model="openai:gpt-4.1-mini",
            anthropic_api_key="",
            openai_api_key="",
            google_api_key="",
        ),
    )
    assert pipeline._llm_key_present() is False


async def test_agent_hitl_flow_happy_path(monkeypatch, tmp_path):
    """PRP-41 — full HITL round-trip: chat -> intermediate -> approve -> pass."""
    monkeypatch.setattr(
        pipeline,
        "get_settings",
        lambda: _fake_settings(str(tmp_path / "reg"), openai_api_key="sk-test"),
    )
    # Pick a provider whose key the fake settings sets.
    monkeypatch.setattr(
        pipeline,
        "_llm_key_present",
        lambda: True,
    )
    # Short-circuit the 3s display delay so the test stays fast.
    monkeypatch.setattr(pipeline, "_APPROVAL_DISPLAY_DELAY_S", 0.0)

    client, intermediate = _make_hitl_client()
    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False)
    status, detail, data = await pipeline.step_agent_hitl_flow(ctx, client)

    assert status == "pass"
    assert "approved=executed" in detail
    assert data["approval_decision"] == "executed"
    assert data["action_id"] == "action-abc-123"
    assert data["session_id"] == "sess-test-0001"
    assert data["tokens_used"] == 240
    # The HITL step buffered exactly one intermediate event for the FE.
    assert len(intermediate) == 1
    inter = intermediate[0]
    assert inter.status == "running"
    assert inter.data["awaiting_approval"] is True
    assert inter.data["action_id"] == "action-abc-123"
    assert inter.phase_name == pipeline.PHASE_AGENTS
    # Ctx threaded for downstream cleanup + KPI consumers.
    assert ctx.approval_action_id == "action-abc-123"
    assert ctx.agent_approval_decision == "executed"
    assert ctx.session_id == "sess-test-0001"


async def test_agent_hitl_flow_skips_without_key(monkeypatch, tmp_path):
    """PRP-41 — no LLM key -> skip-gracefully; no session created."""
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    monkeypatch.setattr(pipeline, "_llm_key_present", lambda: False)

    client, intermediate = _make_hitl_client()
    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False)
    status, detail, data = await pipeline.step_agent_hitl_flow(ctx, client)

    assert status == "skip"
    assert "no API key" in detail
    assert data == {}
    assert intermediate == []
    assert ctx.session_id is None


async def test_agent_hitl_flow_skips_on_session_failure(monkeypatch, tmp_path):
    """PRP-41 — session-create error -> skip, never raise."""
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    monkeypatch.setattr(pipeline, "_llm_key_present", lambda: True)

    class _NoSessionClient:
        def __init__(self, _app: Any = None, *, event_sink: list[Any] | None = None) -> None:
            self._event_sink = event_sink

        async def __aenter__(self) -> _NoSessionClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        def yield_event(self, event: Any) -> None:
            pass

        async def request(self, step: str, method: str, path: str, **_kw: Any) -> dict[str, Any]:
            raise pipeline._StepError(step, 500, {"title": "boom", "detail": "agents down"})

    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False)
    status, detail, _ = await pipeline.step_agent_hitl_flow(
        ctx, cast(pipeline._Client, _NoSessionClient())
    )
    assert status == "skip"
    assert "session-create failed" in detail


async def test_agent_hitl_flow_skips_when_agent_did_not_trigger_tool(monkeypatch, tmp_path):
    """PRP-41 — agent answered directly (no pending_action) -> skip with detail."""
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    monkeypatch.setattr(pipeline, "_llm_key_present", lambda: True)
    monkeypatch.setattr(pipeline, "_APPROVAL_DISPLAY_DELAY_S", 0.0)

    client, intermediate = _make_hitl_client(chat_pending=False)
    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False)
    status, detail, data = await pipeline.step_agent_hitl_flow(ctx, client)
    assert status == "skip"
    assert "did not trigger save_scenario" in detail
    assert data["session_id"] == "sess-test-0001"
    # No intermediate event because no pending action surfaced.
    assert intermediate == []


async def test_agent_hitl_flow_absorbs_double_approve_400(monkeypatch, tmp_path):
    """PRP-41 — FE pre-empted Approve -> backend approve returns 400; absorb."""
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    monkeypatch.setattr(pipeline, "_llm_key_present", lambda: True)
    monkeypatch.setattr(pipeline, "_APPROVAL_DISPLAY_DELAY_S", 0.0)

    client, intermediate = _make_hitl_client(approve_status=400)
    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False)
    status, detail, data = await pipeline.step_agent_hitl_flow(ctx, client)

    # 4xx absorbed: step still passes with optimistic "executed" decision.
    assert status == "pass"
    assert data["approval_decision"] == "executed"
    assert "approved=executed" in detail
    # The intermediate event was still buffered before the absorb branch.
    assert len(intermediate) == 1


async def test_agent_hitl_flow_skips_on_hard_timeout(monkeypatch, tmp_path):
    """PRP-41 — elapsed > _APPROVAL_HARD_TIMEOUT_S -> skip with timed_out."""
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    monkeypatch.setattr(pipeline, "_llm_key_present", lambda: True)
    monkeypatch.setattr(pipeline, "_APPROVAL_DISPLAY_DELAY_S", 0.0)
    # Force the elapsed-time check to fire: set the hard cap below the
    # display delay so any positive elapsed exceeds it.
    monkeypatch.setattr(pipeline, "_APPROVAL_HARD_TIMEOUT_S", -1.0)

    client, intermediate = _make_hitl_client()
    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False)
    status, detail, data = await pipeline.step_agent_hitl_flow(ctx, client)

    assert status == "skip"
    assert "approval timed out" in detail
    assert data["timed_out"] is True
    assert data["approval_decision"] == "timed_out"
    assert ctx.agent_approval_decision == "timed_out"
    # Intermediate event was emitted; approve POST never fired.
    assert len(intermediate) == 1
    assert all(call[1] != f"/agents/sessions/{data['session_id']}/approve" for call in client.calls)


async def test_ops_snapshot_happy_path(tmp_path):
    """PRP-41 — three /ops/* GETs feed the 5-key KPI payload."""

    class _OpsClient:
        def __init__(self, _app: Any = None, *, event_sink: list[Any] | None = None) -> None:
            self._event_sink = event_sink
            self.calls: list[str] = []

        async def __aenter__(self) -> _OpsClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        def yield_event(self, event: Any) -> None:
            pass

        async def request(self, step: str, method: str, path: str, **_kw: Any) -> dict[str, Any]:
            self.calls.append(path)
            if path == "/ops/summary":
                return {
                    "aliases": [
                        {"alias_name": "demo-production", "is_stale": True},
                        {"alias_name": "challenger", "is_stale": False},
                    ],
                    "runs": {
                        "counts": [
                            {"status": "success", "count": 4},
                            {"status": "failed", "count": 1},
                        ]
                    },
                }
            if path.startswith("/ops/retraining-candidates"):
                return {"candidates": [{"store_id": 1}, {"store_id": 2}], "total_evaluated": 2}
            if path.startswith("/ops/model-health"):
                return {
                    "entries": [
                        {"drift_direction": "degrading"},
                        {"drift_direction": "stable"},
                    ],
                    "total_evaluated": 2,
                }
            raise AssertionError(f"unexpected: {path}")

    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False)
    status, detail, data = await pipeline.step_ops_snapshot(
        ctx, cast(pipeline._Client, _OpsClient())
    )

    assert status == "pass"
    assert data == {
        "stale_aliases_count": 1,
        "retraining_candidates_count": 2,
        "total_runs": 5,
        "total_aliases": 2,
        "degrading_health_count": 1,
    }
    assert "stale_aliases=1" in detail
    assert "degrading=1" in detail


async def test_ops_snapshot_warns_when_all_three_endpoints_fail(tmp_path):
    """PRP-41 — every /ops/* returns 5xx -> warn (not fail), zero-filled payload."""

    class _OpsBrokenClient:
        def __init__(self, _app: Any = None, *, event_sink: list[Any] | None = None) -> None:
            pass

        async def __aenter__(self) -> _OpsBrokenClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        def yield_event(self, event: Any) -> None:
            pass

        async def request(self, step: str, method: str, path: str, **_kw: Any) -> dict[str, Any]:
            raise pipeline._StepError(step, 500, {"title": "DB down", "detail": "unreachable"})

    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False)
    status, detail, data = await pipeline.step_ops_snapshot(
        ctx, cast(pipeline._Client, _OpsBrokenClient())
    )

    assert status == "warn"
    assert "/ops/*" in detail and "unavailable" in detail
    assert data == {
        "stale_aliases_count": 0,
        "retraining_candidates_count": 0,
        "total_runs": 0,
        "total_aliases": 0,
        "degrading_health_count": 0,
    }


async def test_ops_snapshot_passes_on_empty_db(tmp_path):
    """PRP-41 — 200 + empty bodies -> pass with zero-filled payload."""

    class _OpsEmptyClient:
        def __init__(self, _app: Any = None, *, event_sink: list[Any] | None = None) -> None:
            pass

        async def __aenter__(self) -> _OpsEmptyClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        def yield_event(self, event: Any) -> None:
            pass

        async def request(self, step: str, method: str, path: str, **_kw: Any) -> dict[str, Any]:
            if path == "/ops/summary":
                return {"aliases": [], "runs": {"counts": []}}
            if path.startswith("/ops/retraining-candidates"):
                return {"candidates": [], "total_evaluated": 0}
            if path.startswith("/ops/model-health"):
                return {"entries": [], "total_evaluated": 0}
            raise AssertionError(path)

    ctx = pipeline.DemoContext(seed=42, skip_seed=True, reset=False)
    status, _, data = await pipeline.step_ops_snapshot(
        ctx, cast(pipeline._Client, _OpsEmptyClient())
    )
    assert status == "pass"
    assert data == {
        "stale_aliases_count": 0,
        "retraining_candidates_count": 0,
        "total_runs": 0,
        "total_aliases": 0,
        "degrading_health_count": 0,
    }


# =============================================================================
# E1 (#390) -- workspace persistence hooks
# =============================================================================


class _WorkspaceSpy:
    """Recording stand-in for the workspace module's create/finalize hooks."""

    def __init__(self, create_returns: str | None = "ws-e1-test") -> None:
        self.create_calls: list[Any] = []
        self.finalize_calls: list[dict[str, Any]] = []
        self._create_returns = create_returns

    async def create_workspace(self, req: Any) -> str | None:
        self.create_calls.append(req)
        return self._create_returns

    async def finalize_workspace(
        self,
        workspace_id: str,
        ctx: Any,
        *,
        failed: bool,
        wall_clock_s: float | None = None,
    ) -> None:
        self.finalize_calls.append(
            {"workspace_id": workspace_id, "failed": failed, "wall_clock_s": wall_clock_s}
        )


async def test_run_pipeline_keep_creates_and_finalizes_workspace(monkeypatch, tmp_path):
    """E1 (#390) -- keep run: create before steps, finalize before the yield."""
    artifact = tmp_path / "m.joblib"
    artifact.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    wapes = {"naive": 0.3, "seasonal_naive": 0.1, "moving_average": 0.2}
    monkeypatch.setattr(pipeline, "_Client", _build_fake_client(str(artifact), wapes))
    spy = _WorkspaceSpy()
    monkeypatch.setattr(pipeline, "workspace", spy)

    req = DemoRunRequest.model_validate({"preservation": "keep", "workspace_name": "e1-test"})
    events = [e async for e in pipeline.run_pipeline(app=_FAKE_APP, req=req)]

    assert len(spy.create_calls) == 1
    assert spy.create_calls[0] is req
    assert len(spy.finalize_calls) == 1
    assert spy.finalize_calls[0]["workspace_id"] == "ws-e1-test"
    assert spy.finalize_calls[0]["failed"] is False
    assert spy.finalize_calls[0]["wall_clock_s"] is not None

    final = events[-1]
    assert final.event_type == "pipeline_complete"
    assert final.status == "pass"
    assert final.data["workspace_id"] == "ws-e1-test"


async def test_run_pipeline_ephemeral_touches_no_workspace(monkeypatch, tmp_path):
    """E1 (#390) -- default (ephemeral) run issues zero workspace calls."""
    artifact = tmp_path / "m.joblib"
    artifact.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    wapes = {"naive": 0.3, "seasonal_naive": 0.1, "moving_average": 0.2}
    monkeypatch.setattr(pipeline, "_Client", _build_fake_client(str(artifact), wapes))
    spy = _WorkspaceSpy()
    monkeypatch.setattr(pipeline, "workspace", spy)

    events = [e async for e in pipeline.run_pipeline(app=_FAKE_APP, req=DemoRunRequest())]

    assert spy.create_calls == []
    assert spy.finalize_calls == []
    final = events[-1]
    assert final.event_type == "pipeline_complete"
    # The key is additive and present, with a null value on ephemeral runs.
    assert "workspace_id" in final.data
    assert final.data["workspace_id"] is None


async def test_run_pipeline_workspace_create_failure_does_not_break_run(monkeypatch, tmp_path):
    """E1 (#390) -- create_workspace's warn path (None) leaves the run green."""
    artifact = tmp_path / "m.joblib"
    artifact.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "get_settings", lambda: _fake_settings(str(tmp_path / "reg")))
    wapes = {"naive": 0.3, "seasonal_naive": 0.1, "moving_average": 0.2}
    monkeypatch.setattr(pipeline, "_Client", _build_fake_client(str(artifact), wapes))
    spy = _WorkspaceSpy(create_returns=None)
    monkeypatch.setattr(pipeline, "workspace", spy)

    req = DemoRunRequest.model_validate({"preservation": "keep"})
    events = [e async for e in pipeline.run_pipeline(app=_FAKE_APP, req=req)]

    assert len(spy.create_calls) == 1
    # No row was created, so there is nothing to finalize.
    assert spy.finalize_calls == []
    final = events[-1]
    assert final.event_type == "pipeline_complete"
    assert final.status == "pass"
    assert final.data["workspace_id"] is None


async def test_run_pipeline_keep_finalizes_failed_on_step_failure(monkeypatch):
    """E1 (#390) -- a mid-run step failure still finalizes, with failed=True."""

    class _FailingClient:
        def __init__(self, _app: Any, *, event_sink: list[Any] | None = None) -> None:
            self._event_sink = event_sink

        async def __aenter__(self) -> _FailingClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        def yield_event(self, event: Any) -> None:
            if self._event_sink is None:
                return
            self._event_sink.append(event)

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
    spy = _WorkspaceSpy()
    monkeypatch.setattr(pipeline, "workspace", spy)

    req = DemoRunRequest.model_validate({"preservation": "keep"})
    events = [e async for e in pipeline.run_pipeline(app=_FAKE_APP, req=req)]

    assert len(spy.finalize_calls) == 1
    assert spy.finalize_calls[0]["workspace_id"] == "ws-e1-test"
    assert spy.finalize_calls[0]["failed"] is True
    final = events[-1]
    assert final.event_type == "pipeline_complete"
    assert final.status == "fail"
    assert final.data["workspace_id"] == "ws-e1-test"


# =============================================================================
# E2 (#391) — per-preset demo seed profiles
# =============================================================================


def test_scenario_seed_profile_covers_every_preset():
    """E2 (#391) — every ScenarioPreset member has an explicit seed profile.

    The ``.get`` fallback in step_seed stays (a future 9th member must not
    crash), but no CURRENT member may silently fall back to demo_minimal —
    the picker cards promise per-preset seed shapes.
    """
    assert set(pipeline._SCENARIO_SEED_PROFILE) == set(ScenarioPreset)


def test_scenario_seed_profile_windows_clear_backfill_gate():
    """E2 (#391) — every profile window is >= 75 days so a later
    showcase_rich run with skip_seed=true clears the historical_backfill gate."""
    for preset, profile in pipeline._SCENARIO_SEED_PROFILE.items():
        if profile.window is not None:
            span = (profile.window[1] - profile.window[0]).days
        else:
            span = profile.span_days
        assert span >= 75, f"{preset.value} window spans only {span} days"


async def test_step_seed_holiday_rush_posts_pinned_window():
    """E2 (#391) — holiday_rush MUST seed the calendar-pinned 2024 window.

    The preset's HolidayConfig spikes are fixed 2024 dates; a today-anchored
    window would never contain them and the preset silently degrades.
    """
    ctx = pipeline.DemoContext(
        seed=42, skip_seed=False, reset=False, scenario=ScenarioPreset.HOLIDAY_RUSH
    )
    client = _RecordingClient(
        None,
        responses={("POST", "/seeder/generate"): {"records_created": {"sales": 1}}},
    )
    status, detail, _data = await pipeline.step_seed(ctx, _as_client(client))
    assert status == "pass"
    body = client.calls[0][2]
    assert body is not None
    assert body["scenario"] == "holiday_rush"
    assert body["start_date"] == "2024-10-01"
    assert body["end_date"] == "2024-12-31"
    assert body["stores"] == 5
    assert body["products"] == 15
    assert "holiday_rush: 5 stores x 15 products" in detail


async def test_step_seed_retail_standard_posts_demo_scaled_profile():
    """E2 (#391) — retail_standard seeds 5x15 over a 180-day today-anchored window."""
    ctx = pipeline.DemoContext(
        seed=42, skip_seed=False, reset=False, scenario=ScenarioPreset.RETAIL_STANDARD
    )
    client = _RecordingClient(
        None,
        responses={("POST", "/seeder/generate"): {"records_created": {"sales": 1}}},
    )
    status, _detail, _data = await pipeline.step_seed(ctx, _as_client(client))
    assert status == "pass"
    body = client.calls[0][2]
    assert body is not None
    assert body["scenario"] == "retail_standard"
    assert body["stores"] == 5
    assert body["products"] == 15
    start = date.fromisoformat(body["start_date"])
    end = date.fromisoformat(body["end_date"])
    assert end - start == timedelta(days=180)
    # sparsity stays 0.0 — the seeder override fires only when > 0, which is
    # what preserves the sparse preset's 50%-missing character.
    assert body["sparsity"] == 0.0
