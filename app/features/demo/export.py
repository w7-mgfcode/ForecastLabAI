"""Workspace export-bundle writer (E6, issue #412).

Write a self-describing, checksum-validated bundle for a saved showcase
workspace under ``<showcase_export_root>/<workspace_id>/``::

    manifest.json              versioned snapshot + references
    scenario_plans/<id>.json   one per resolvable scenario plan
    checksums.sha256           sha256sum-compatible; covers every other file

Frozen decisions (see ``PRPs/PRP-showcase-completion-E6-export-bundle.md``):

1. One directory per ``workspace_id`` (unique uuid4 hex), keyed off the DB row.
2. Re-export is a deterministic overwrite -- the existing guarded bundle
   directory is removed and rewritten; ``exported_at`` records the moment.
3. Soft references resolve over the public HTTP surface IN-PROCESS
   (``httpx.ASGITransport``) -- the demo slice may not import the registry /
   scenarios slices (vertical-slice rule). Any non-2xx -> an
   ``unresolved_references`` entry (or ``artifact_verified=None``), never a
   failed export.
4. Model artifacts are REFERENCED (uri + registry hash + live verify result),
   never copied.
5. Stateless -- export writes NOTHING to the database (no row, no story slot).
6. ``failed`` workspaces are exportable; ``running`` ones are a 409.
7. ``checksums.sha256`` excludes itself (a self-referencing checksum file is a
   bootstrap hole) and uses the two-space ``sha256sum`` separator.

The traversal guard (:func:`_resolve_bundle_dir`) and chunked SHA-256
(:func:`_compute_sha256`) MIRROR ``app/features/registry/storage.py``
(``LocalFSProvider._resolve_path`` / ``AbstractStorageProvider.compute_hash``)
-- the vertical-slice rule forbids importing that module, so the ~10-line
pattern is reimplemented here. Reference resolution uses the same in-process
``httpx`` client ``app/features/demo/link_health.py`` uses.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, ForecastLabError, NotFoundError
from app.core.logging import get_logger
from app.features.demo import workspace
from app.features.demo.models import WORKSPACE_STATUS_RUNNING
from app.features.demo.schemas import (
    BUNDLE_FORMAT_VERSION,
    ExportFileEntry,
    UnresolvedReference,
    WorkspaceDetailResponse,
    WorkspaceExportResult,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)

_MANIFEST = "manifest.json"
_CHECKSUMS = "checksums.sha256"
_PLANS_DIR = "scenario_plans"
# created_objects run-id keys whose registry runs the manifest references.
_RUN_KEYS = ("winning_run_id", "v2_run_id", "stale_alias_run_id")
# Generous in-process budget (no real network); a hung driven endpoint surfaces
# as a response under raise_app_exceptions=False, not a hang.
_EXPORT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


def _compute_sha256(path: Path) -> str:
    """Chunked SHA-256 of a file (mirror ``registry/storage.py:compute_hash``)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_bundle_dir(root: Path, workspace_id: str) -> Path:
    """Resolve ``<root>/<workspace_id>``, guarding against path traversal.

    Mirrors ``registry/storage.py:LocalFSProvider._resolve_path`` -- ``resolve()``
    then ``relative_to(root)``. A ``workspace_id`` that escapes the root raises
    ``ValueError`` BEFORE any disk I/O. ``root`` must already be resolved. The
    id always comes from the DB row (uuid4 hex), never raw from the URL path, so
    this is defense in depth.
    """
    bundle_dir = (root / workspace_id).resolve()
    try:
        bundle_dir.relative_to(root)
    except ValueError:
        logger.warning(
            "demo.export_path_traversal_attempt",
            workspace_id=workspace_id,
            root=str(root),
        )
        raise
    return bundle_dir


def _write_json(path: Path, payload: dict[str, Any]) -> int:
    """Write deterministic JSON (sorted keys, 2-space indent, trailing newline).

    ``sort_keys`` makes the bytes order-independent so unchanged state
    re-exports to identical bytes (stable checksums). Returns the byte size.
    """
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(data)
    return len(data)


def _root_relative(root: Path) -> str:
    """Repo-root-relative POSIX string for display (no absolute-path leak)."""
    try:
        return root.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return root.as_posix()


def _open_client(app: FastAPI) -> httpx.AsyncClient:
    """In-process client over ``ASGITransport`` (pattern: ``link_health.py``).

    ``raise_app_exceptions=False`` is load-bearing: a driven endpoint's failure
    becomes a 5xx *response* (-> ``unresolved_references`` / ``artifact_verified
    =None``), never a re-raised exception inside the export. ``base_url`` is
    cosmetic but required by httpx.
    """
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://demo.internal",
        timeout=_EXPORT_TIMEOUT,
    )


async def _resolve_model_runs(
    client: httpx.AsyncClient,
    created: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[UnresolvedReference]]:
    """Resolve the run-id soft references to manifest model-run references.

    A run that resolves (2xx) is referenced (uri + registry hash + a live
    ``artifact_verified`` from the verify endpoint when both uri and hash are
    present). A non-2xx run is an ``unresolved_references`` entry. A failed
    artifact *verify* on a resolved run is NOT unresolved -- the run resolved;
    only its artifact check did not (``artifact_verified=None``).
    """
    model_runs: list[dict[str, Any]] = []
    unresolved: list[UnresolvedReference] = []
    for key in _RUN_KEYS:
        run_id = created.get(key)
        if not isinstance(run_id, str) or not run_id:
            continue
        resp = await client.get(f"/registry/runs/{run_id}")
        if resp.status_code != 200:
            reason = f"HTTP {resp.status_code}"
            unresolved.append(UnresolvedReference(key=key, ref_id=run_id, reason=reason))
            logger.warning(
                "demo.export_unresolved_reference", key=key, ref_id=run_id, reason=reason
            )
            continue
        body = resp.json()
        artifact_uri = body.get("artifact_uri")
        artifact_hash = body.get("artifact_hash")
        verified: bool | None = None
        if artifact_uri and artifact_hash:
            vresp = await client.get(f"/registry/runs/{run_id}/verify")
            if vresp.status_code == 200:
                raw = vresp.json().get("verified")
                verified = raw if isinstance(raw, bool) else None
        model_runs.append(
            {
                "key": key,
                "run_id": run_id,
                "model_type": body.get("model_type"),
                "status": body.get("status"),
                "artifact_uri": artifact_uri,
                "artifact_hash": artifact_hash,
                "artifact_verified": verified,
                "metrics": body.get("metrics"),
            }
        )
    return model_runs, unresolved


async def _resolve_scenario_plans(
    client: httpx.AsyncClient,
    created: dict[str, Any],
    plans_dir: Path,
) -> tuple[list[dict[str, Any]], list[tuple[str, int]], list[UnresolvedReference]]:
    """Write a JSON snapshot per resolvable scenario plan; report dangles.

    Returns ``(manifest plan entries, written (relpath, size) pairs,
    unresolved)``. The plan body is stored verbatim -- its ``run_id`` is the
    forecast ARTIFACT key, not a registry ``model_run.run_id`` (different id
    spaces; memory anchor ``scenario-run-id-vs-registry-run-id``), so it is
    never joined against the registry.
    """
    plan_entries: list[dict[str, Any]] = []
    file_entries: list[tuple[str, int]] = []
    unresolved: list[UnresolvedReference] = []
    # JSONB types this list[str], but nothing enforces it at runtime -- treat
    # entries as untrusted (mirrors link_health's created_objects guards).
    raw_plan_ids = created.get("scenario_plan_ids")
    plan_ids: list[Any] = raw_plan_ids if isinstance(raw_plan_ids, list) else []
    for scenario_id in plan_ids:
        if not isinstance(scenario_id, str) or not scenario_id:
            continue
        resp = await client.get(f"/scenarios/{scenario_id}")
        if resp.status_code != 200:
            reason = f"HTTP {resp.status_code}"
            unresolved.append(
                UnresolvedReference(key="scenario_plan_ids", ref_id=scenario_id, reason=reason)
            )
            logger.warning(
                "demo.export_unresolved_reference",
                key="scenario_plan_ids",
                ref_id=scenario_id,
                reason=reason,
            )
            continue
        body = resp.json()
        rel = f"{_PLANS_DIR}/{scenario_id}.json"
        size = _write_json(plans_dir / f"{scenario_id}.json", body)
        plan_entries.append(
            {
                "scenario_id": scenario_id,
                "file": rel,
                "name": body.get("name") if isinstance(body, dict) else None,
            }
        )
        file_entries.append((rel, size))
    return plan_entries, file_entries, unresolved


def _validate_checksums(bundle_dir: Path) -> bool:
    """Re-read ``checksums.sha256``, recompute every listed hash, compare.

    Returns ``False`` (the caller logs it) rather than raising on any mismatch
    or parse issue -- a failed validation is reported honestly in the response.
    """
    checksums_path = bundle_dir / _CHECKSUMS
    try:
        content = checksums_path.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in content.splitlines():
        if not line.strip():
            continue
        # sha256sum format: "<hex>  <relpath>" (two-space separator).
        expected, _, rel = line.partition("  ")
        if not rel:
            return False
        target = bundle_dir / rel
        try:
            actual = _compute_sha256(target)
        except OSError:
            return False
        if actual != expected:
            return False
    return True


async def export_workspace(
    db: AsyncSession,
    app: FastAPI,
    workspace_id: str,
    *,
    export_root: str | Path | None = None,
) -> WorkspaceExportResult:
    """Export a saved workspace to a checksum-validated bundle on disk.

    Re-queries the row via :func:`workspace.get_workspace` so the function is
    independently callable/testable; the route's 404/409 pre-guard fires before
    any export work begins.

    Args:
        db: Caller-owned async session (used only to load the row).
        app: The live FastAPI app for in-process soft-reference resolution.
        workspace_id: External id of the workspace to export.
        export_root: Override the configured ``showcase_export_root`` (tests).

    Returns:
        The export result (bundle path, file inventory, counts, unresolved
        references, checksum-validation flag).

    Raises:
        NotFoundError: When no workspace matches ``workspace_id`` (404).
        ConflictError: When the workspace run is still ``running`` (409).
        ForecastLabError: When the bundle cannot be written to disk (500).
    """
    row = await workspace.get_workspace(db, workspace_id)
    if row is None:
        raise NotFoundError(message=f"Workspace not found: {workspace_id}")
    if row.status == WORKSPACE_STATUS_RUNNING:
        raise ConflictError(
            "Cannot export while the run is still in progress; retry after the run settles."
        )

    snapshot = WorkspaceDetailResponse.model_validate(row).model_dump(mode="json")
    created = row.created_objects or {}

    root = Path(export_root or get_settings().showcase_export_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    # GUARD before any rmtree / mkdir / write -- the rmtree target is the
    # guarded resolution only, never a raw request value.
    bundle_dir = _resolve_bundle_dir(root, row.workspace_id)

    exported_at = datetime.now(UTC)
    try:
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)  # Decision 2 -- deterministic overwrite.
        plans_dir = bundle_dir / _PLANS_DIR
        plans_dir.mkdir(parents=True)

        async with _open_client(app) as client:
            model_runs, run_unresolved = await _resolve_model_runs(client, created)
            plan_entries, plan_files, plan_unresolved = await _resolve_scenario_plans(
                client, created, plans_dir
            )
        unresolved = [*run_unresolved, *plan_unresolved]

        manifest = {
            "bundle_format_version": BUNDLE_FORMAT_VERSION,
            "exported_at": exported_at.isoformat(),
            "workspace": snapshot,
            "model_runs": model_runs,
            "scenario_plans": plan_entries,
            "unresolved_references": [ref.model_dump() for ref in unresolved],
            # Paths + sizes so a consumer can sanity-check without parsing the
            # hash file; hashes live ONLY in checksums.sha256 (Decision 7).
            "files": [{"path": rel, "size_bytes": size} for rel, size in plan_files],
        }
        _write_json(bundle_dir / _MANIFEST, manifest)

        # checksums.sha256 -- every bundle file except itself, sorted, two-space
        # sha256sum format, bundle-relative POSIX paths.
        checksum_lines = [
            f"{_compute_sha256(path)}  {path.relative_to(bundle_dir).as_posix()}"
            for path in sorted(bundle_dir.rglob("*"))
            if path.is_file() and path.name != _CHECKSUMS
        ]
        (bundle_dir / _CHECKSUMS).write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "demo.workspace_export_failed",
            workspace_id=row.workspace_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise ForecastLabError(
            message=f"Export bundle write failed: {exc}", status_code=500
        ) from exc

    validated = _validate_checksums(bundle_dir)
    files = [
        ExportFileEntry(
            path=path.relative_to(bundle_dir).as_posix(),
            sha256=_compute_sha256(path),
            size_bytes=path.stat().st_size,
        )
        for path in sorted(bundle_dir.rglob("*"))
        if path.is_file()
    ]

    logger.info(
        "demo.workspace_exported",
        workspace_id=row.workspace_id,
        files=len(files),
        unresolved=len(unresolved),
        validated=validated,
    )
    return WorkspaceExportResult(
        workspace_id=row.workspace_id,
        bundle_path=f"{_root_relative(root)}/{row.workspace_id}",
        bundle_format_version=BUNDLE_FORMAT_VERSION,
        exported_at=exported_at,
        files=files,
        scenario_plans_exported=len(plan_entries),
        model_runs_referenced=len(model_runs),
        unresolved_references=unresolved,
        validated=validated,
    )
