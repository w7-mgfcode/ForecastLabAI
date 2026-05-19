"""ForecastOps Control Center slice.

A read-only vertical slice that aggregates operational state across the
``jobs``, ``registry``, and ``data_platform`` slices: system health, job / run /
alias health, data freshness, a needs-attention list, and a ranked
retraining-candidate queue. Has no models and no migration — it only reads.
"""

from app.features.ops.routes import router
from app.features.ops.schemas import OpsSummaryResponse, RetrainingCandidatesResponse
from app.features.ops.service import OpsService

__all__ = [
    "OpsService",
    "OpsSummaryResponse",
    "RetrainingCandidatesResponse",
    "router",
]
