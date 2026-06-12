"""Unit tests for the link-health probe module (E2, issue #408).

Probes run against a THROWAWAY FastAPI stub app -- no database, no real
slices. The stub returns 200 / 404 / 500 (and one raising endpoint) at the
probed paths so every classification branch is exercised. Workspace rows are
constructed in memory (never persisted) -- Python-side column defaults apply
at INSERT time, so every consumed field is passed explicitly.
"""

from typing import Any

from fastapi import FastAPI, Response

from app.features.demo import link_health
from app.features.demo.link_health import _ProbeTarget, build_probe_targets
from app.features.demo.models import ShowcaseWorkspace


def _make_workspace(**overrides: Any) -> ShowcaseWorkspace:
    """An in-memory (unpersisted) ShowcaseWorkspace with explicit fields."""
    base: dict[str, Any] = {
        "workspace_id": "a" * 32,
        "name": "e2-health",
        "status": "completed",
        "seed": 42,
        "scenario": "demo_minimal",
        "reset": False,
        "skip_seed": True,
        "created_objects": {},
        "job_ids": None,
    }
    base.update(overrides)
    return ShowcaseWorkspace(**base)


def _stub_app() -> FastAPI:
    """A throwaway ASGI app standing in for the probed public surface."""
    app = FastAPI()

    @app.get("/registry/runs/{run_id}")
    def get_run(run_id: str) -> Response:
        if run_id == "run-alive":
            return Response(status_code=200, content="{}", media_type="application/json")
        return Response(status_code=404)

    @app.get("/scenarios/{scenario_id}")
    def get_scenario(scenario_id: str) -> Response:
        return Response(status_code=404)

    @app.get("/registry/aliases/{alias_name}")
    def get_alias(alias_name: str) -> Response:
        return Response(status_code=200, content="{}", media_type="application/json")

    @app.get("/batch/{batch_id}")
    def get_batch(batch_id: str) -> Response:
        return Response(status_code=500)

    @app.get("/agents/sessions/{session_id}")
    def get_session(session_id: str) -> Response:
        raise RuntimeError("probed endpoint blew up")  # -> 500 response, never re-raised

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> Response:
        if job_id == "job-alive":
            return Response(status_code=200, content="{}", media_type="application/json")
        return Response(status_code=404)

    return app


# =============================================================================
# build_probe_targets
# =============================================================================


def test_build_probe_targets_covers_every_probeable_key() -> None:
    """Every probeable created_objects key + the job_ids slot map to a path."""
    ws = _make_workspace(
        created_objects={
            "winning_run_id": "run-1",
            "v2_run_id": "run-2",
            "stale_alias_run_id": "run-3",
            "scenario_plan_ids": ["sp-1", "sp-2"],
            "alias": "demo-production",
            "batch_id": "batch-1",
            "agent_session_id": "sess-1",
            # Non-probeable keys -- no HTTP identity; must be skipped.
            "v2_model_path": "artifacts/models/model_x.joblib",
            "scenario_artifact_key": "abc123",
            "train_model_types": ["naive", "seasonal_naive"],
        },
        job_ids=["job-1", "job-2"],
    )
    targets = build_probe_targets(ws)
    by_key = {t.key: t for t in targets}

    assert by_key["winning_run_id"].probe_path == "/registry/runs/run-1"
    assert by_key["winning_run_id"].ref_type == "model_run"
    assert by_key["v2_run_id"].probe_path == "/registry/runs/run-2"
    assert by_key["stale_alias_run_id"].probe_path == "/registry/runs/run-3"
    assert by_key["scenario_plan_ids[0]"].probe_path == "/scenarios/sp-1"
    assert by_key["scenario_plan_ids[1]"].probe_path == "/scenarios/sp-2"
    assert by_key["scenario_plan_ids[0]"].ref_type == "scenario_plan"
    assert by_key["alias"].probe_path == "/registry/aliases/demo-production"
    assert by_key["batch_id"].probe_path == "/batch/batch-1"
    assert by_key["agent_session_id"].probe_path == "/agents/sessions/sess-1"
    assert by_key["job_ids[0]"].probe_path == "/jobs/job-1"
    assert by_key["job_ids[1]"].probe_path == "/jobs/job-2"
    assert by_key["job_ids[0]"].ref_type == "job"
    # 3 run ids + 2 plans + alias + batch + session + 2 jobs -- and nothing
    # for the non-probeable keys.
    assert len(targets) == 10
    assert not any("model_path" in t.key or "artifact" in t.key for t in targets)


def test_build_probe_targets_empty_objects() -> None:
    """No recorded references (and a NULL job_ids slot) -> no targets."""
    assert build_probe_targets(_make_workspace()) == []


def test_build_probe_targets_skips_non_string_values() -> None:
    """Malformed JSONB values (non-strings, empties) are skipped, not raised."""
    ws = _make_workspace(
        created_objects={
            "winning_run_id": 123,  # not a str
            "alias": "",  # empty
            "scenario_plan_ids": ["sp-1", 7, None, ""],
            "batch_id": None,
        },
        job_ids=["job-1", 42],
    )
    targets = build_probe_targets(ws)
    assert [t.key for t in targets] == ["scenario_plan_ids[0]", "job_ids[0]"]


# =============================================================================
# probe_workspace_links (against the stub app)
# =============================================================================


async def test_probe_classification_alive_dead_unknown() -> None:
    """2xx -> alive, 404 -> dead, 5xx/exception -> unknown; counts add up."""
    ws = _make_workspace(
        created_objects={
            "winning_run_id": "run-alive",  # 200 -> alive
            "v2_run_id": "run-gone",  # 404 -> dead
            "scenario_plan_ids": ["sp-gone"],  # 404 -> dead
            "alias": "demo-production",  # 200 -> alive
            "batch_id": "batch-1",  # 500 -> unknown
            "agent_session_id": "sess-1",  # raises -> 500 response -> unknown
        },
        job_ids=["job-alive", "job-gone"],  # 200 + 404
    )
    health = await link_health.probe_workspace_links(_stub_app(), ws)

    by_key = {r.key: r.status for r in health.references}
    assert by_key["winning_run_id"] == "alive"
    assert by_key["v2_run_id"] == "dead"
    assert by_key["scenario_plan_ids[0]"] == "dead"
    assert by_key["alias"] == "alive"
    assert by_key["batch_id"] == "unknown"
    assert by_key["agent_session_id"] == "unknown"
    assert by_key["job_ids[0]"] == "alive"
    assert by_key["job_ids[1]"] == "dead"

    assert health.alive == 3
    assert health.dead == 3
    assert health.unknown == 2
    assert health.workspace_id == ws.workspace_id
    assert health.partial_run is False


async def test_probe_empty_workspace_short_circuits() -> None:
    """No references -> empty result, zero counts, no client construction."""
    health = await link_health.probe_workspace_links(_stub_app(), _make_workspace())
    assert health.references == []
    assert (health.alive, health.dead, health.unknown) == (0, 0, 0)


async def test_partial_run_flag_tracks_status() -> None:
    """partial_run is True exactly when the row never reached 'completed'."""
    app = _stub_app()
    for status, expected in (("completed", False), ("failed", True), ("running", True)):
        health = await link_health.probe_workspace_links(app, _make_workspace(status=status))
        assert health.partial_run is expected
        assert health.workspace_status == status


async def test_probe_transport_error_classifies_unknown() -> None:
    """A transport-level failure classifies as unknown -- never raises."""

    class _ExplodingClient:
        async def get(self, _path: str) -> Response:
            raise OSError("transport down")

    target = _ProbeTarget(
        key="winning_run_id",
        ref_type="model_run",
        ref_id="run-1",
        probe_path="/registry/runs/run-1",
    )
    result = await link_health._probe_one(_ExplodingClient(), target)  # type: ignore[arg-type]
    assert result.status == "unknown"
    assert result.ref_id == "run-1"
