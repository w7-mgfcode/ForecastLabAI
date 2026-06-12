"""Soft-reference liveness probes for showcase workspaces (E2, issue #408).

A workspace row records everything its run created as OPAQUE SOFT REFERENCES
(no ForeignKeys -- see ``app/features/demo/models.py``), so referenced objects
can be deleted out from under it by design. This module turns that silent
staleness into a per-workspace health signal.

The demo slice may NOT import another feature slice (vertical-slice rule), so
liveness is checked through the public HTTP API **in-process** via
``httpx.ASGITransport`` -- the exact mechanism ``pipeline._Client`` already
uses (``app/features/demo/pipeline.py``). ``raise_app_exceptions=False`` is
load-bearing: an unhandled error inside a probed endpoint must surface as a
500 *response* (classified ``unknown``), never as a re-raised exception.

Classification table:

    2xx              -> "alive"    (the referenced object still exists)
    404              -> "dead"     (deleted after the run -- expected, designed)
    anything else    -> "unknown"  (5xx, timeout, transport error -- no false alarms)

A probe NEVER raises -- a flaky slice must not 500 the health route.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

from app.features.demo.models import WORKSPACE_STATUS_COMPLETED, ShowcaseWorkspace
from app.features.demo.schemas import (
    RefHealthStatus,
    RefType,
    WorkspaceHealthResponse,
    WorkspaceRefHealth,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

# Probe budget -- generous for an in-process call; a hung dependency inside a
# probed endpoint classifies as "unknown" instead of hanging the health route.
_PROBE_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


@dataclass(frozen=True)
class _ProbeTarget:
    """One probeable soft reference resolved from a workspace row."""

    key: str  # created_objects key (list keys carry an index, e.g. "scenario_plan_ids[0]")
    ref_type: RefType
    ref_id: str
    probe_path: str  # public API path whose status code decides liveness


def build_probe_targets(ws: ShowcaseWorkspace) -> list[_ProbeTarget]:
    """Map a workspace's soft references to probeable public API paths.

    Non-probeable ``created_objects`` keys (``v2_model_path``,
    ``scenario_artifact_key``, ``train_model_types``) are skipped -- they have
    no HTTP identity to check. The E1 ``job_ids`` story slot (CONTRACT(E1)-6)
    probes through ``GET /jobs/{job_id}`` when present; pre-backfill rows
    where the slot is NULL are silently skipped.
    """
    targets: list[_ProbeTarget] = []
    objects = ws.created_objects or {}

    def _str_value(key: str) -> str | None:
        value = objects.get(key)
        return value if isinstance(value, str) and value else None

    for key in ("winning_run_id", "v2_run_id", "stale_alias_run_id"):
        run_id = _str_value(key)
        if run_id:
            targets.append(_ProbeTarget(key, "model_run", run_id, f"/registry/runs/{run_id}"))

    plan_ids = objects.get("scenario_plan_ids")
    if isinstance(plan_ids, list):
        for index, plan_id in enumerate(plan_ids):
            if isinstance(plan_id, str) and plan_id:
                targets.append(
                    _ProbeTarget(
                        f"scenario_plan_ids[{index}]",
                        "scenario_plan",
                        plan_id,
                        f"/scenarios/{plan_id}",
                    )
                )

    alias = _str_value("alias")
    if alias:
        targets.append(_ProbeTarget("alias", "alias", alias, f"/registry/aliases/{alias}"))

    batch_id = _str_value("batch_id")
    if batch_id:
        targets.append(_ProbeTarget("batch_id", "batch", batch_id, f"/batch/{batch_id}"))

    session_id = _str_value("agent_session_id")
    if session_id:
        targets.append(
            _ProbeTarget(
                "agent_session_id",
                "agent_session",
                session_id,
                f"/agents/sessions/{session_id}",
            )
        )

    # The ORM types job_ids as list[str], but JSONB enforces nothing at
    # runtime -- treat entries as untrusted (mirrors the created_objects guards).
    job_ids: list[Any] = list(ws.job_ids or [])
    for index, job_id in enumerate(job_ids):
        if isinstance(job_id, str) and job_id:
            targets.append(_ProbeTarget(f"job_ids[{index}]", "job", job_id, f"/jobs/{job_id}"))

    return targets


async def _probe_one(client: httpx.AsyncClient, target: _ProbeTarget) -> WorkspaceRefHealth:
    """Probe one reference; classify the status code. NEVER raises."""
    status: RefHealthStatus
    try:
        response = await client.get(target.probe_path)
    except (httpx.HTTPError, OSError):
        status = "unknown"
    else:
        if 200 <= response.status_code < 300:
            status = "alive"
        elif response.status_code == 404:
            status = "dead"
        else:
            status = "unknown"
    return WorkspaceRefHealth(
        key=target.key,
        ref_type=target.ref_type,
        ref_id=target.ref_id,
        status=status,
        probe_path=target.probe_path,
    )


async def probe_workspace_links(app: FastAPI, ws: ShowcaseWorkspace) -> WorkspaceHealthResponse:
    """Probe every soft reference a workspace recorded; aggregate the counts.

    Probes run concurrently. ``partial_run`` flags a row whose pipeline never
    settled to ``completed`` -- its artifacts may be missing regardless of
    what the probes find.

    Args:
        app: The live FastAPI app (``request.app`` -- the slice never imports
            ``app.main``).
        ws: The workspace row whose references are probed.

    Returns:
        The per-reference results plus alive/dead/unknown counts.
    """
    targets = build_probe_targets(ws)
    references: list[WorkspaceRefHealth] = []
    if targets:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://demo.internal",
            timeout=_PROBE_TIMEOUT,
        ) as client:
            references = list(
                await asyncio.gather(*(_probe_one(client, target) for target in targets))
            )
    return WorkspaceHealthResponse(
        workspace_id=ws.workspace_id,
        workspace_status=ws.status,
        partial_run=ws.status != WORKSPACE_STATUS_COMPLETED,
        references=references,
        alive=sum(1 for ref in references if ref.status == "alive"),
        dead=sum(1 for ref in references if ref.status == "dead"),
        unknown=sum(1 for ref in references if ref.status == "unknown"),
    )
