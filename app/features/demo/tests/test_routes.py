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

    async def fake_list(_db, **_kwargs: object) -> list[SimpleNamespace]:
        return []

    async def fake_count(_db, **_kwargs: object) -> int:
        return 0

    monkeypatch.setattr(workspace, "list_workspaces", fake_list)
    monkeypatch.setattr(workspace, "count_workspaces", fake_count)

    resp = await client.get("/demo/workspaces")
    assert resp.status_code == 200
    assert resp.json() == {"workspaces": [], "total": 0}


async def test_list_workspaces_passes_pagination(client, monkeypatch):
    """E4 (#393) -- limit/offset query params reach the helper."""
    seen: dict[str, object] = {}

    async def fake_list(_db, **kwargs: object) -> list[SimpleNamespace]:
        seen.update(kwargs)
        return [_orm_like_row()]

    async def fake_count(_db, **_kwargs: object) -> int:
        return 5

    monkeypatch.setattr(workspace, "list_workspaces", fake_list)
    monkeypatch.setattr(workspace, "count_workspaces", fake_count)

    resp = await client.get("/demo/workspaces", params={"limit": 2, "offset": 3})
    assert resp.status_code == 200
    assert seen["limit"] == 2
    assert seen["offset"] == 3
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


# =============================================================================
# E2 (#408) -- list filters / sort + GET /demo/workspaces/{id}/health (unit)
# =============================================================================


async def test_list_workspaces_passes_filters_and_sort(client, monkeypatch):
    """E2 (#408) -- q/tags/include_archived/sort params reach BOTH helpers."""
    seen_list: dict[str, object] = {}
    seen_count: dict[str, object] = {}

    async def fake_list(_db, **kwargs: object) -> list[SimpleNamespace]:
        seen_list.update(kwargs)
        return []

    async def fake_count(_db, **kwargs: object) -> int:
        seen_count.update(kwargs)
        return 0

    monkeypatch.setattr(workspace, "list_workspaces", fake_list)
    monkeypatch.setattr(workspace, "count_workspaces", fake_count)

    resp = await client.get(
        "/demo/workspaces",
        params=[
            ("q", "demo"),
            ("tags", "smoke"),
            ("tags", "e2"),
            ("include_archived", "true"),
            ("sort_by", "name"),
            ("sort_order", "asc"),
        ],
    )
    assert resp.status_code == 200
    assert seen_list["q"] == "demo"
    assert seen_list["tags"] == ["smoke", "e2"]
    assert seen_list["include_archived"] is True
    assert seen_list["sort_by"] == "name"
    assert seen_list["sort_order"] == "asc"
    # The count helper gets the SAME filters -- total respects them.
    assert seen_count["q"] == "demo"
    assert seen_count["tags"] == ["smoke", "e2"]
    assert seen_count["include_archived"] is True


async def test_list_workspaces_defaults_hide_archived(client, monkeypatch):
    """E2 (#408) -- a legacy no-param call defaults to include_archived=False."""
    seen: dict[str, object] = {}

    async def fake_list(_db, **kwargs: object) -> list[SimpleNamespace]:
        seen.update(kwargs)
        return []

    async def fake_count(_db, **_kwargs: object) -> int:
        return 0

    monkeypatch.setattr(workspace, "list_workspaces", fake_list)
    monkeypatch.setattr(workspace, "count_workspaces", fake_count)

    resp = await client.get("/demo/workspaces")
    assert resp.status_code == 200
    assert seen["include_archived"] is False
    assert seen["q"] is None
    assert seen["tags"] is None
    assert seen["sort_by"] is None


async def test_list_workspaces_rejects_bad_sort_order(client):
    """E2 (#408) -- sort_order is pattern-constrained (asc|desc only)."""
    resp = await client.get("/demo/workspaces", params={"sort_order": "sideways"})
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_workspace_health_404(client, monkeypatch):
    """E2 (#408) -- health on a missing workspace is a 404 problem+json."""

    async def fake_get(_db, _workspace_id: str) -> None:
        return None

    monkeypatch.setattr(workspace, "get_workspace", fake_get)

    resp = await client.get("/demo/workspaces/" + "0" * 32 + "/health")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert "Workspace not found" in resp.json()["detail"]


async def test_workspace_health_happy_path(client, monkeypatch):
    """E2 (#408) -- the route resolves the row and returns the probe result."""
    from app.features.demo import link_health
    from app.features.demo.schemas import WorkspaceHealthResponse, WorkspaceRefHealth

    row = _orm_like_row(status="failed")

    async def fake_get(_db, workspace_id: str) -> SimpleNamespace:
        return row

    async def fake_probe(_app, ws) -> WorkspaceHealthResponse:
        assert ws is row  # the route passes the resolved ORM row through
        return WorkspaceHealthResponse(
            workspace_id="a" * 32,
            workspace_status="failed",
            partial_run=True,
            references=[
                WorkspaceRefHealth(
                    key="winning_run_id",
                    ref_type="model_run",
                    ref_id="run-abc",
                    status="dead",
                    probe_path="/registry/runs/run-abc",
                )
            ],
            alive=0,
            dead=1,
            unknown=0,
        )

    monkeypatch.setattr(workspace, "get_workspace", fake_get)
    monkeypatch.setattr(link_health, "probe_workspace_links", fake_probe)

    resp = await client.get("/demo/workspaces/" + "a" * 32 + "/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["workspace_id"] == "a" * 32
    assert body["partial_run"] is True
    assert body["dead"] == 1
    assert body["references"][0]["status"] == "dead"
    assert body["references"][0]["probe_path"] == "/registry/runs/run-abc"


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
# DELETE /demo/workspaces/{workspace_id} (unit)
# =============================================================================


async def test_delete_workspace_204(client, monkeypatch):
    """A deleted workspace row yields 204 with an empty body."""
    seen: dict[str, str] = {}

    async def fake_delete(_db, workspace_id: str) -> bool:
        seen["workspace_id"] = workspace_id
        return True

    monkeypatch.setattr(workspace, "delete_workspace", fake_delete)

    resp = await client.delete("/demo/workspaces/" + "c" * 32)
    assert resp.status_code == 204
    assert resp.content == b""
    assert seen["workspace_id"] == "c" * 32


async def test_delete_workspace_404(client, monkeypatch):
    """An unknown workspace_id is a 404 problem+json."""

    async def fake_delete(_db, _workspace_id: str) -> bool:
        return False

    monkeypatch.setattr(workspace, "delete_workspace", fake_delete)

    resp = await client.delete("/demo/workspaces/" + "0" * 32)
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert "Workspace not found" in resp.json()["detail"]


# =============================================================================
# E1 (#407) -- PATCH /demo/workspaces/{workspace_id} (unit)
# =============================================================================


async def test_patch_workspace_happy_path(client, monkeypatch):
    """E1 (#407) -- provided fields update; response echoes the full detail."""
    seen: dict[str, object] = {}

    async def fake_update(_db, workspace_id: str, update) -> SimpleNamespace:
        seen["workspace_id"] = workspace_id
        seen["changes"] = update.model_dump(exclude_unset=True)
        return _orm_like_row(
            workspace_id=workspace_id,
            name="renamed",
            pinned=True,
            tags=["t1"],
        )

    monkeypatch.setattr(workspace, "update_workspace", fake_update)

    resp = await client.patch(
        "/demo/workspaces/" + "a" * 32,
        json={"name": "renamed", "pinned": True, "tags": ["t1"]},
    )
    assert resp.status_code == 200
    assert seen["workspace_id"] == "a" * 32
    assert seen["changes"] == {"name": "renamed", "pinned": True, "tags": ["t1"]}
    body = resp.json()
    assert body["name"] == "renamed"
    assert body["pinned"] is True
    assert body["tags"] == ["t1"]
    # Untouched fields ride through from the row.
    assert body["status"] == "completed"
    assert body["seed"] == 42


async def test_patch_workspace_missing_404_problem_json(client, monkeypatch):
    """E1 (#407) -- an unknown workspace_id is a 404 problem+json."""

    async def fake_update(_db, _workspace_id: str, _update) -> None:
        return None

    monkeypatch.setattr(workspace, "update_workspace", fake_update)

    resp = await client.patch("/demo/workspaces/" + "0" * 32, json={"pinned": True})
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert "Workspace not found" in resp.json()["detail"]


async def test_patch_workspace_unknown_field_422(client):
    """E1 (#407) -- extra='forbid': a typo'd field is a 422 problem+json."""
    resp = await client.patch("/demo/workspaces/" + "a" * 32, json={"bogus": 1})
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_patch_workspace_explicit_null_archived_422(client):
    """E1 (#407) -- explicit null on a NOT NULL-backed field is a 422."""
    resp = await client.patch("/demo/workspaces/" + "a" * 32, json={"archived": None})
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_patch_workspace_empty_body_noop_200(client, monkeypatch):
    """E1 (#407) -- an empty body is a 200 no-op returning the current row."""

    async def fake_update(_db, workspace_id: str, update) -> SimpleNamespace:
        assert update.model_dump(exclude_unset=True) == {}
        return _orm_like_row(workspace_id=workspace_id)

    monkeypatch.setattr(workspace, "update_workspace", fake_update)

    resp = await client.patch("/demo/workspaces/" + "a" * 32, json={})
    assert resp.status_code == 200
    assert resp.json()["workspace_id"] == "a" * 32


async def test_run_demo_rejects_replayed_from_without_keep_422(client):
    """E1 (#407) -- a lineage pointer without preservation='keep' is a 422."""
    resp = await client.post("/demo/run", json={"replayed_from_workspace_id": "a" * 32})
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")


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


@pytest.mark.integration
async def test_patch_workspace_integration_round_trip(client, db_session: AsyncSession):
    """E1 (#407) -- PATCH round-trips rename/notes/tags/archive/pin on a real row."""
    workspace_id = await workspace.create_workspace(
        DemoRunRequest.model_validate({"preservation": "keep", "workspace_name": "e1-patch"})
    )
    assert workspace_id is not None

    resp = await client.patch(
        f"/demo/workspaces/{workspace_id}",
        json={
            "name": "e1-renamed",
            "notes": "kept for review",
            "tags": ["smoke", "workspace:e1"],
            "archived": True,
            "pinned": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "e1-renamed"
    assert body["notes"] == "kept for review"
    assert body["tags"] == ["smoke", "workspace:e1"]
    assert body["archived"] is True
    assert body["pinned"] is True
    # The pipeline-owned lifecycle status is untouched.
    assert body["status"] == "running"

    # The change persisted -- the detail endpoint reads it back.
    detail = await client.get(f"/demo/workspaces/{workspace_id}")
    assert detail.status_code == 200
    assert detail.json()["name"] == "e1-renamed"
    assert detail.json()["archived"] is True


@pytest.mark.integration
async def test_delete_workspace_integration_round_trip(client, db_session: AsyncSession):
    """DELETE removes exactly the target metadata row; a re-delete is 404."""
    kept = await workspace.create_workspace(
        DemoRunRequest.model_validate({"preservation": "keep", "workspace_name": "del-kept"})
    )
    target = await workspace.create_workspace(
        DemoRunRequest.model_validate({"preservation": "keep", "workspace_name": "del-target"})
    )
    assert kept is not None and target is not None

    resp = await client.delete(f"/demo/workspaces/{target}")
    assert resp.status_code == 204

    # The deleted row is gone; the sibling row is untouched.
    assert (await client.get(f"/demo/workspaces/{target}")).status_code == 404
    survivors = await client.get("/demo/workspaces")
    assert [w["workspace_id"] for w in survivors.json()["workspaces"]] == [kept]

    # Deleting again is a 404 problem+json (no idempotent 204).
    again = await client.delete(f"/demo/workspaces/{target}")
    assert again.status_code == 404
    assert again.headers["content-type"].startswith("application/problem+json")


@pytest.mark.integration
async def test_delete_workspace_integration_keeps_created_objects(client, db_session: AsyncSession):
    """Deleting a workspace never deletes (or resolves) its soft references.

    The workspace references one REAL cross-slice object (an agent session)
    plus one dangling run id -- the delete must succeed without touching the
    former or resolving the latter (no-FK soft-reference contract).
    """
    session_resp = await client.post("/agents/sessions", json={"agent_type": "experiment"})
    assert session_resp.status_code == 201
    agent_session_id = session_resp.json()["session_id"]
    try:
        workspace_id = await workspace.create_workspace(
            DemoRunRequest.model_validate({"preservation": "keep", "workspace_name": "del-softref"})
        )
        assert workspace_id is not None
        row = await workspace.get_workspace(db_session, workspace_id)
        assert row is not None
        row.created_objects = {
            "agent_session_id": agent_session_id,
            "winning_run_id": "run-dangling-never-created",
        }
        await db_session.commit()

        resp = await client.delete(f"/demo/workspaces/{workspace_id}")
        assert resp.status_code == 204

        # The metadata row is gone...
        assert (await client.get(f"/demo/workspaces/{workspace_id}")).status_code == 404
        # ...but the soft-referenced agent session still exists.
        still_there = await client.get(f"/agents/sessions/{agent_session_id}")
        assert still_there.status_code == 200
    finally:
        await client.delete(f"/agents/sessions/{agent_session_id}")


# =============================================================================
# E2 (#408) -- list filters / sort + health against real Postgres (integration)
# =============================================================================


@pytest.mark.integration
async def test_list_workspaces_integration_filters_and_sort(client, db_session: AsyncSession):
    """Filters, sort, pinned-first ordering, and filtered totals on real rows."""
    ids: dict[str, str] = {}
    # Creation order matters for the default created_at sort assertions.
    for name in ("alpha-match", "beta", "zeta-pinned"):
        workspace_id = await workspace.create_workspace(
            DemoRunRequest.model_validate({"preservation": "keep", "workspace_name": name})
        )
        assert workspace_id is not None
        ids[name] = workspace_id
    unnamed = await workspace.create_workspace(
        DemoRunRequest.model_validate({"preservation": "keep"})
    )
    assert unnamed is not None

    # Curate via the PATCH surface (E1): pin zeta, archive beta, tag alpha.
    assert (
        await client.patch(f"/demo/workspaces/{ids['zeta-pinned']}", json={"pinned": True})
    ).status_code == 200
    assert (
        await client.patch(f"/demo/workspaces/{ids['beta']}", json={"archived": True})
    ).status_code == 200
    assert (
        await client.patch(f"/demo/workspaces/{ids['alpha-match']}", json={"tags": ["smoke", "e2"]})
    ).status_code == 200

    # Default list: archived hidden, pinned first, then newest-first.
    resp = await client.get("/demo/workspaces")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3  # beta (archived) excluded from the total too
    listed = [w["workspace_id"] for w in body["workspaces"]]
    assert ids["beta"] not in listed
    assert listed == [ids["zeta-pinned"], unnamed, ids["alpha-match"]]

    # include_archived=true surfaces the archived row again.
    resp = await client.get("/demo/workspaces", params={"include_archived": "true"})
    assert resp.json()["total"] == 4
    assert ids["beta"] in [w["workspace_id"] for w in resp.json()["workspaces"]]

    # q: case-insensitive name substring; total respects the filter.
    resp = await client.get("/demo/workspaces", params={"q": "ALPHA"})
    body = resp.json()
    assert body["total"] == 1
    assert [w["workspace_id"] for w in body["workspaces"]] == [ids["alpha-match"]]

    # tags: containment -- ALL listed tags must match.
    resp = await client.get("/demo/workspaces", params=[("tags", "smoke"), ("tags", "e2")])
    assert [w["workspace_id"] for w in resp.json()["workspaces"]] == [ids["alpha-match"]]
    resp = await client.get("/demo/workspaces", params=[("tags", "smoke"), ("tags", "nope")])
    assert resp.json()["total"] == 0

    # sort_by=name asc: pinned row STILL first, unnamed row sinks (NULLS LAST).
    resp = await client.get("/demo/workspaces", params={"sort_by": "name", "sort_order": "asc"})
    names = [w["name"] for w in resp.json()["workspaces"]]
    assert names == ["zeta-pinned", "alpha-match", None]

    # Unknown sort_by silently falls back to the default order (no 422).
    resp = await client.get("/demo/workspaces", params={"sort_by": "bogus"})
    assert resp.status_code == 200
    assert [w["workspace_id"] for w in resp.json()["workspaces"]] == [
        ids["zeta-pinned"],
        unnamed,
        ids["alpha-match"],
    ]


@pytest.mark.integration
async def test_workspace_health_integration_alive_and_dead(client, db_session: AsyncSession):
    """A real reference probes alive; a bogus one probes dead (E2, #408)."""
    session_resp = await client.post("/agents/sessions", json={"agent_type": "experiment"})
    assert session_resp.status_code == 201
    agent_session_id = session_resp.json()["session_id"]
    try:
        workspace_id = await workspace.create_workspace(
            DemoRunRequest.model_validate({"preservation": "keep", "workspace_name": "e2-health"})
        )
        assert workspace_id is not None
        row = await workspace.get_workspace(db_session, workspace_id)
        assert row is not None
        row.created_objects = {
            "agent_session_id": agent_session_id,
            "winning_run_id": "run-dangling-never-created",
        }
        await db_session.commit()

        resp = await client.get(f"/demo/workspaces/{workspace_id}/health")
        assert resp.status_code == 200
        body = resp.json()
        by_key = {r["key"]: r["status"] for r in body["references"]}
        assert by_key["agent_session_id"] == "alive"
        assert by_key["winning_run_id"] == "dead"
        assert body["alive"] == 1
        assert body["dead"] == 1
        assert body["unknown"] == 0
        # The row was inserted as 'running' (never finalized) -> partial run.
        assert body["partial_run"] is True
    finally:
        await client.delete(f"/agents/sessions/{agent_session_id}")


# =============================================================================
# E5 (#411) — POST /demo/hitl-decision + GET /demo/approval-events
# =============================================================================


@pytest.fixture(autouse=True)
def _clear_hitl_slot():
    """Reset the module-level HITL relay slot around every test in this file."""
    from app.features.demo import hitl

    hitl.clear()
    yield
    hitl.clear()


async def test_hitl_decision_204_on_pending(client):
    """A decision for the registered pending action returns 204."""
    from app.features.demo import hitl

    hitl.register("act-204")
    resp = await client.post(
        "/demo/hitl-decision",
        json={"action_id": "act-204", "decision": "rejected", "reason": "too risky"},
    )
    assert resp.status_code == 204
    # The relay recorded the operator's decision for the waiting step (use a
    # positive timeout: wait_for(timeout=0) raises before stepping the
    # freshly-scheduled task, even when the event is already set).
    assert await hitl.wait_for_decision("act-204", timeout=1.0) == ("rejected", "too risky")


async def test_hitl_decision_404_when_nothing_pending(client):
    """No registered action -> 404 problem+json."""
    resp = await client.post(
        "/demo/hitl-decision",
        json={"action_id": "ghost", "decision": "approved"},
    )
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert "No pending HITL action" in resp.json()["detail"]


async def test_hitl_decision_409_when_already_decided(client):
    """A second decision for the same action -> 409 problem+json."""
    from app.features.demo import hitl

    hitl.register("act-409")
    first = await client.post(
        "/demo/hitl-decision", json={"action_id": "act-409", "decision": "approved"}
    )
    assert first.status_code == 204
    second = await client.post(
        "/demo/hitl-decision", json={"action_id": "act-409", "decision": "rejected"}
    )
    assert second.status_code == 409
    assert second.headers["content-type"].startswith("application/problem+json")
    assert "already decided" in second.json()["detail"]


async def test_hitl_decision_422_bad_body(client):
    """A bad decision literal / extra key -> 422 problem+json."""
    bad_literal = await client.post(
        "/demo/hitl-decision", json={"action_id": "a", "decision": "maybe"}
    )
    assert bad_literal.status_code == 422
    assert bad_literal.headers["content-type"].startswith("application/problem+json")
    extra_key = await client.post(
        "/demo/hitl-decision",
        json={"action_id": "a", "decision": "approved", "bogus": 1},
    )
    assert extra_key.status_code == 422


async def test_approval_events_empty(client, monkeypatch):
    """200 + empty list when no workspace carries approval events."""

    async def fake_list(_db, *, limit: int = 50) -> list[dict[str, object]]:
        return []

    monkeypatch.setattr(workspace, "list_approval_events", fake_list)
    resp = await client.get("/demo/approval-events")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"events": [], "total": 0}


async def test_approval_events_populated(client, monkeypatch):
    """Flattened entries carry workspace_id / workspace_name + decision."""

    async def fake_list(_db, *, limit: int = 50) -> list[dict[str, object]]:
        return [
            {
                "workspace_id": "a" * 32,
                "workspace_name": "demo-1",
                "action_id": "act-1",
                "tool_name": "save_scenario",
                "decision": "rejected",
                "decided_at": "2026-06-13T00:00:00+00:00",
                "session_id": "sess-1",
                "auto_approved": False,
                "reason": "too risky",
                "execution_status": "rejected",
                "transcript_summary": "I'll save that scenario.",
            }
        ]

    monkeypatch.setattr(workspace, "list_approval_events", fake_list)
    resp = await client.get("/demo/approval-events", params={"limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["events"][0]["workspace_id"] == "a" * 32
    assert body["events"][0]["workspace_name"] == "demo-1"
    assert body["events"][0]["decision"] == "rejected"


async def test_approval_events_rejects_bad_limit(client):
    """limit is bounded 1-200 -> 422 problem+json out of range."""
    resp = await client.get("/demo/approval-events", params={"limit": 0})
    assert resp.status_code == 422
    resp = await client.get("/demo/approval-events", params={"limit": 999})
    assert resp.status_code == 422
