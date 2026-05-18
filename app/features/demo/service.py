"""Service layer for the demo showcase slice.

A module-level ``asyncio.Lock`` enforces single-flight: only one demo pipeline
runs at a time. Concurrent attempts raise :class:`PipelineBusyError`, which the
route layer surfaces as an RFC 7807 ``409``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.features.demo.pipeline import run_pipeline
from app.features.demo.schemas import DemoRunRequest, DemoRunResult, StepEvent

# Single-flight guard -- one demo pipeline at a time across the whole process.
_pipeline_lock = asyncio.Lock()


class PipelineBusyError(Exception):
    """Raised when a demo pipeline run is already in progress."""


async def stream_pipeline(app: FastAPI, req: DemoRunRequest) -> AsyncIterator[StepEvent]:
    """Lock-guarded wrapper around :func:`run_pipeline`.

    Args:
        app: The live FastAPI application.
        req: Run parameters.

    Yields:
        StepEvent instances, in execution order.

    Raises:
        PipelineBusyError: If another pipeline run is already in progress.
    """
    if _pipeline_lock.locked():
        raise PipelineBusyError("A demo pipeline run is already in progress.")
    async with _pipeline_lock:
        async for event in run_pipeline(app, req):
            yield event


async def run_pipeline_sync(app: FastAPI, req: DemoRunRequest) -> DemoRunResult:
    """Drain :func:`stream_pipeline` into an aggregate :class:`DemoRunResult`.

    Args:
        app: The live FastAPI application.
        req: Run parameters.

    Returns:
        The aggregate result of the whole pipeline run.

    Raises:
        PipelineBusyError: If another pipeline run is already in progress.
    """
    steps: list[StepEvent] = []
    final: StepEvent | None = None
    async for event in stream_pipeline(app, req):
        if event.event_type == "step_complete":
            steps.append(event)
        elif event.event_type == "pipeline_complete":
            final = event

    if final is None:  # defensive -- run_pipeline always emits pipeline_complete
        return DemoRunResult(overall_status="fail", steps=steps)

    winner_wape = final.data.get("winner_wape")
    wall_clock = final.data.get("wall_clock_s", 0.0)
    return DemoRunResult(
        overall_status="fail" if final.status == "fail" else "pass",
        steps=steps,
        winner_model_type=final.data.get("winner_model_type"),
        winner_wape=float(winner_wape) if isinstance(winner_wape, (int, float)) else None,
        winning_run_id=final.data.get("winning_run_id"),
        alias=final.data.get("alias"),
        wall_clock_s=float(wall_clock) if isinstance(wall_clock, (int, float)) else 0.0,
    )
