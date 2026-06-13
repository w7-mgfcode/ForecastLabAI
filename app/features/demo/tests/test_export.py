"""Tests for the workspace export-bundle writer (E6, issue #412).

Unit tests (no DB, no app) cover the disk primitives -- chunked sha256, the
traversal guard (must raise BEFORE any I/O), deterministic JSON -- and the
manifest assembly via a mocked in-process client. Integration tests run the
real endpoint against docker-compose Postgres with a ``tmp_path`` export root.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import httpx
import pytest

from app.features.demo import export, workspace
from app.features.demo.models import ShowcaseWorkspace
from app.features.demo.schemas import WorkspaceExportResult

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession

# The direct-call unit tests monkeypatch get_workspace + _open_client, so the
# real session / app are never touched -- typed None sentinels keep the strict
# signature satisfied without a DB or app instance.
_NO_DB = cast("AsyncSession", None)
_NO_APP = cast("FastAPI", None)

# =============================================================================
# Unit -- disk primitives (no DB, no app)
# =============================================================================


def test_compute_sha256_matches_whole_file(tmp_path: Path) -> None:
    """The chunked digest equals a whole-file hashlib hash."""
    target = tmp_path / "blob"
    target.write_bytes(b"y" * 25_000)  # > one 8192-byte chunk
    assert export._compute_sha256(target) == hashlib.sha256(target.read_bytes()).hexdigest()


@pytest.mark.parametrize("evil", ["../escape", "../../etc/passwd", "/etc/passwd"])
def test_resolve_bundle_dir_rejects_traversal_before_io(tmp_path: Path, evil: str) -> None:
    """A traversal-shaped id raises ValueError and writes nothing."""
    root = tmp_path.resolve()
    with pytest.raises(ValueError):
        export._resolve_bundle_dir(root, evil)
    # The guard does pure path math -- no directory is created.
    assert list(root.iterdir()) == []


def test_resolve_bundle_dir_accepts_uuid_hex(tmp_path: Path) -> None:
    """A normal uuid-hex id resolves directly under the root."""
    root = tmp_path.resolve()
    workspace_id = "a" * 32
    resolved = export._resolve_bundle_dir(root, workspace_id)
    assert resolved == root / workspace_id


def test_write_json_is_deterministic(tmp_path: Path) -> None:
    """Two dumps of key-shuffled payloads produce identical bytes."""
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    size_a = export._write_json(a, {"z": 1, "a": 2, "m": {"y": 1, "x": 2}})
    size_b = export._write_json(b, {"a": 2, "m": {"x": 2, "y": 1}, "z": 1})
    assert a.read_bytes() == b.read_bytes()
    assert size_a == size_b == len(a.read_bytes())
    assert a.read_text().endswith("\n")


def test_validate_checksums_round_trip(tmp_path: Path) -> None:
    """A hand-built bundle validates; a tampered file flips validated False."""
    bundle = tmp_path / "wsid"
    bundle.mkdir()
    payload = bundle / "manifest.json"
    payload.write_text("hello\n", encoding="utf-8")
    digest = export._compute_sha256(payload)
    (bundle / "checksums.sha256").write_text(f"{digest}  manifest.json\n", encoding="utf-8")
    assert export._validate_checksums(bundle) is True

    payload.write_text("tampered\n", encoding="utf-8")
    assert export._validate_checksums(bundle) is False


# =============================================================================
# Unit -- manifest assembly via a mocked in-process client
# =============================================================================


def _row(**overrides: object) -> SimpleNamespace:
    """An ORM-shaped ShowcaseWorkspace stand-in (mirrors test_routes._orm_like_row)."""
    base: dict[str, object] = {
        "workspace_id": "a" * 32,
        "name": "e6-export",
        "status": "completed",
        "seed": 42,
        "scenario": "showcase_rich",
        "reset": False,
        "skip_seed": True,
        "store_id": 3,
        "product_id": 7,
        "date_start": _dt.date(2026, 1, 1),
        "date_end": _dt.date(2026, 3, 31),
        "created_objects": {},
        "result_summary": {"winner_model_type": "naive"},
        "created_at": _dt.datetime(2026, 6, 1, 12, 0, tzinfo=_dt.UTC),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _mock_client() -> httpx.AsyncClient:
    """In-process client returning canned registry / scenario bodies + one 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/registry/runs/run-win":
            return httpx.Response(
                200,
                json={
                    "run_id": "run-win",
                    "model_type": "naive",
                    "status": "success",
                    "artifact_uri": "demo/naive-model_abc.joblib",
                    "artifact_hash": "deadbeef",
                    "metrics": {"wape": 0.12},
                },
            )
        if path == "/registry/runs/run-win/verify":
            return httpx.Response(200, json={"verified": True})
        if path == "/registry/runs/run-gone":
            return httpx.Response(404, json={"detail": "run not found"})
        if path == "/scenarios/plan-1":
            return httpx.Response(
                200,
                json={
                    "scenario_id": "plan-1",
                    "name": "Price cut 15%",
                    "run_id": "model_xyz",
                    "assumptions": {"price_change_pct": -0.15},
                    "comparison": {},
                    "tags": ["showcase"],
                },
            )
        if path == "/scenarios/dangling":
            return httpx.Response(404, json={"detail": "scenario not found"})
        return httpx.Response(404, json={"detail": f"unmatched {path}"})

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://demo.internal"
    )


async def test_export_assembles_manifest_and_reports_dangles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mixed run resolves one run + one plan and reports two dangles."""
    row = _row(
        created_objects={
            "winning_run_id": "run-win",
            "v2_run_id": "run-gone",  # 404 -> unresolved
            "scenario_plan_ids": ["plan-1", "dangling"],
        }
    )

    async def fake_get(_db: object, _workspace_id: str) -> SimpleNamespace:
        return row

    monkeypatch.setattr(workspace, "get_workspace", fake_get)
    monkeypatch.setattr(export, "_open_client", lambda _app: _mock_client())

    result: WorkspaceExportResult = await export.export_workspace(
        db=_NO_DB, app=_NO_APP, workspace_id="a" * 32, export_root=tmp_path
    )

    assert result.validated is True
    assert result.model_runs_referenced == 1
    assert result.scenario_plans_exported == 1
    # Two dangles: the v2 run (404) and the dangling scenario plan (404).
    keys = sorted((ref.key, ref.ref_id) for ref in result.unresolved_references)
    assert keys == [("scenario_plan_ids", "dangling"), ("v2_run_id", "run-gone")]

    bundle = tmp_path / ("a" * 32)
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["bundle_format_version"] == 1
    assert manifest["workspace"]["workspace_id"] == "a" * 32
    assert manifest["model_runs"][0]["run_id"] == "run-win"
    assert manifest["model_runs"][0]["artifact_verified"] is True
    assert manifest["scenario_plans"][0]["scenario_id"] == "plan-1"
    # The plan body is stored verbatim under scenario_plans/.
    plan = json.loads((bundle / "scenario_plans" / "plan-1.json").read_text())
    assert plan["name"] == "Price cut 15%"
    # checksums.sha256 covers every file except itself, two-space separator.
    lines = (bundle / "checksums.sha256").read_text().splitlines()
    covered = {line.split("  ", 1)[1] for line in lines}
    assert "manifest.json" in covered
    assert "scenario_plans/plan-1.json" in covered
    assert "checksums.sha256" not in covered
    # The response inventory DOES include the checksum file itself.
    assert any(entry.path == "checksums.sha256" for entry in result.files)


async def test_export_overwrites_stale_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-existing stale file in the bundle dir is gone after re-export."""
    row = _row(created_objects={"winning_run_id": "run-win"})

    async def fake_get(_db: object, _workspace_id: str) -> SimpleNamespace:
        return row

    monkeypatch.setattr(workspace, "get_workspace", fake_get)
    monkeypatch.setattr(export, "_open_client", lambda _app: _mock_client())

    bundle = tmp_path / ("a" * 32)
    (bundle / "scenario_plans").mkdir(parents=True)
    stale = bundle / "scenario_plans" / "stale.json"
    stale.write_text("{}", encoding="utf-8")

    await export.export_workspace(
        db=_NO_DB, app=_NO_APP, workspace_id="a" * 32, export_root=tmp_path
    )

    assert not stale.exists()
    assert (bundle / "manifest.json").exists()


async def test_export_empty_created_objects_minimal_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty-references run still exports a valid manifest + checksums."""
    row = _row(created_objects={})

    async def fake_get(_db: object, _workspace_id: str) -> SimpleNamespace:
        return row

    monkeypatch.setattr(workspace, "get_workspace", fake_get)
    monkeypatch.setattr(export, "_open_client", lambda _app: _mock_client())

    result = await export.export_workspace(
        db=_NO_DB, app=_NO_APP, workspace_id="a" * 32, export_root=tmp_path
    )
    assert result.validated is True
    assert result.model_runs_referenced == 0
    assert result.scenario_plans_exported == 0
    assert result.unresolved_references == []
    paths = {entry.path for entry in result.files}
    assert paths == {"manifest.json", "checksums.sha256"}


async def test_export_404_on_missing_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing row raises NotFoundError before any disk work."""
    from app.core.exceptions import NotFoundError

    async def fake_get(_db: object, _workspace_id: str) -> None:
        return None

    monkeypatch.setattr(workspace, "get_workspace", fake_get)
    with pytest.raises(NotFoundError):
        await export.export_workspace(db=_NO_DB, app=_NO_APP, workspace_id="z" * 32)


async def test_export_409_on_running_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    """A running row raises ConflictError (references not yet settled)."""
    from app.core.exceptions import ConflictError

    async def fake_get(_db: object, _workspace_id: str) -> SimpleNamespace:
        return _row(status="running")

    monkeypatch.setattr(workspace, "get_workspace", fake_get)
    with pytest.raises(ConflictError):
        await export.export_workspace(db=_NO_DB, app=_NO_APP, workspace_id="a" * 32)


# =============================================================================
# Integration -- real endpoint, real Postgres, tmp_path export root
# =============================================================================


@pytest.mark.integration
async def test_export_endpoint_round_trip(
    client: httpx.AsyncClient,
    db_session: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed row exports; checksums verify; a dangling plan is reported."""
    from app.core.config import get_settings

    workspace_id = "e6" + "0" * 30
    db_session.add(
        ShowcaseWorkspace(
            workspace_id=workspace_id,
            name="e6-integration",
            seed=42,
            scenario="showcase_rich",
            reset=False,
            skip_seed=True,
            status="completed",
            created_objects={"scenario_plan_ids": ["dangling-plan-1"]},
        )
    )
    await db_session.commit()

    # Point the export root at tmp_path without disturbing the cached settings.
    patched = get_settings().model_copy(update={"showcase_export_root": str(tmp_path)})
    monkeypatch.setattr(export, "get_settings", lambda: patched)

    resp = await client.post(f"/demo/workspaces/{workspace_id}/export")
    assert resp.status_code == 200
    body = resp.json()
    assert body["validated"] is True
    assert body["bundle_path"].endswith(workspace_id)
    # The dangling scenario plan is reported, not fatal.
    assert any(ref["ref_id"] == "dangling-plan-1" for ref in body["unresolved_references"])

    bundle = tmp_path / workspace_id
    assert (bundle / "manifest.json").exists()
    # Independently re-verify every checksum line (don't trust validated alone).
    for line in (bundle / "checksums.sha256").read_text().splitlines():
        if not line.strip():
            continue
        expected, _, rel = line.partition("  ")
        actual = hashlib.sha256((bundle / rel).read_bytes()).hexdigest()
        assert actual == expected, rel

    # Re-export overwrites: plant a stale file, re-export, assert it's gone.
    stale = bundle / "scenario_plans" / "stale.json"
    stale.write_text("{}", encoding="utf-8")
    resp2 = await client.post(f"/demo/workspaces/{workspace_id}/export")
    assert resp2.status_code == 200
    assert not stale.exists()


@pytest.mark.integration
async def test_export_endpoint_409_on_running(
    client: httpx.AsyncClient,
    db_session: Any,
) -> None:
    """The endpoint rejects a still-running workspace with 409 problem+json."""
    workspace_id = "e6run" + "0" * 27
    db_session.add(
        ShowcaseWorkspace(
            workspace_id=workspace_id,
            name="e6-running",
            seed=1,
            scenario="demo_minimal",
            reset=False,
            skip_seed=True,
            status="running",
        )
    )
    await db_session.commit()

    resp = await client.post(f"/demo/workspaces/{workspace_id}/export")
    assert resp.status_code == 409
    assert resp.headers["content-type"].startswith("application/problem+json")
