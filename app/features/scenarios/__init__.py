"""Scenario Simulation / What-If Planning slice.

A vertical slice that turns a baseline forecast into a *plan*: it loads an
already-trained baseline model, runs its forecast, applies deterministic,
transparent uplift / drag factors for future assumptions (price change,
promotion, holiday, inventory, lifecycle), and returns a baseline-vs-scenario
comparison. Comparisons can be persisted as named ``scenario_plan`` rows.

DECISIONS LOCKED (PRP-26): the baseline forecasters ignore exogenous
regressors, so a "what-if" is applied as a deterministic post-forecast
multiplier — never a leakage-prone re-training. Every result is explicitly
labelled ``method = "heuristic"`` with a fixed disclaimer.
"""

from app.features.scenarios.models import ScenarioPlan
from app.features.scenarios.routes import router
from app.features.scenarios.schemas import (
    ScenarioComparison,
    ScenarioListResponse,
    ScenarioPlanResponse,
)
from app.features.scenarios.service import ScenarioService

__all__ = [
    "ScenarioComparison",
    "ScenarioListResponse",
    "ScenarioPlan",
    "ScenarioPlanResponse",
    "ScenarioService",
    "router",
]
