"""Demo showcase slice.

Drives the end-to-end forecasting pipeline in-process (via ``httpx.ASGITransport``)
and streams per-step progress, powering the dashboard's Showcase page. This slice
has no database table of its own -- it reads and writes only through the other
slices' HTTP endpoints (precedent: ``analytics``, ``dimensions``).
"""

from app.features.demo.pipeline import run_pipeline
from app.features.demo.routes import router
from app.features.demo.schemas import DemoRunRequest, DemoRunResult, StepEvent

__all__ = [
    "DemoRunRequest",
    "DemoRunResult",
    "StepEvent",
    "router",
    "run_pipeline",
]
