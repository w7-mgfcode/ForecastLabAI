"""API routes for the Scenario Simulation slice.

Five endpoints back the ``Visualize → What-If Planner`` page: a stateless
``POST /scenarios/simulate`` plus CRUD over saved ``scenario_plan`` rows.

Service-layer ``FileNotFoundError`` / ``ValueError`` map to RFC 7807 problem
responses via the ``app.core.exceptions`` ``ForecastLabError`` hierarchy
(``application/problem+json``) — a bogus ``run_id`` never surfaces as a 500.
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import BadRequestError, DatabaseError, NotFoundError
from app.core.logging import get_logger
from app.features.scenarios.schemas import (
    CreateScenarioRequest,
    ScenarioComparison,
    ScenarioListResponse,
    ScenarioPlanResponse,
    SimulateScenarioRequest,
)
from app.features.scenarios.service import ScenarioService

logger = get_logger(__name__)

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.post(
    "/simulate",
    response_model=ScenarioComparison,
    status_code=status.HTTP_200_OK,
    summary="Run a stateless what-if simulation",
    description="""
Run a baseline forecast for an existing trained model and apply deterministic
what-if adjustment factors.

**Inputs:**
- `run_id`: artifact key of a baseline model (the `run_id` on a completed
  predict/train job — `model_{run_id}.joblib`).
- `horizon`: number of days to simulate (1-90).
- `assumptions`: optional price / promotion / holiday / inventory / lifecycle
  assumptions. Omit them all for a no-change baseline.

**Output:** a `ScenarioComparison` — per-day baseline vs. scenario demand,
aggregate unit and revenue deltas, a coverage verdict, and a `method`
(`heuristic`) plus a `disclaimer`. The result is a deterministic post-forecast
multiplier, NOT a re-trained causal model.

A bogus `run_id` returns a 404 problem response; an invalid artifact path
returns 400 — never a 500.
""",
)
async def simulate_scenario(
    request: SimulateScenarioRequest,
    db: AsyncSession = Depends(get_db),
) -> ScenarioComparison:
    """Run a stateless scenario simulation.

    Args:
        request: Baseline run_id, horizon, and what-if assumptions.
        db: Async database session from dependency.

    Returns:
        A baseline-vs-scenario comparison.

    Raises:
        NotFoundError: When the model artifact is missing.
        BadRequestError: When the request is otherwise invalid.
    """
    try:
        return await ScenarioService().simulate(db, request)
    except FileNotFoundError as exc:
        logger.warning("scenarios.simulate_not_found", run_id=request.run_id, error=str(exc))
        raise NotFoundError(message=str(exc)) from exc
    except ValueError as exc:
        logger.warning("scenarios.simulate_invalid", run_id=request.run_id, error=str(exc))
        raise BadRequestError(message=str(exc)) from exc


@router.post(
    "",
    response_model=ScenarioPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a scenario plan",
    description="""
Run a simulation and persist it as a named plan.

The saved plan stores both the raw assumptions and the full comparison
snapshot, so a reloaded plan re-renders without recomputation.
""",
)
async def create_scenario(
    request: CreateScenarioRequest,
    db: AsyncSession = Depends(get_db),
) -> ScenarioPlanResponse:
    """Persist a scenario plan.

    Args:
        request: Plan name plus baseline run_id, horizon, and assumptions.
        db: Async database session from dependency.

    Returns:
        The saved plan with its embedded comparison snapshot.

    Raises:
        NotFoundError: When the model artifact is missing.
        BadRequestError: When the request is otherwise invalid.
        DatabaseError: When the persistence operation fails.
    """
    try:
        return await ScenarioService().create_plan(db, request)
    except FileNotFoundError as exc:
        logger.warning("scenarios.create_not_found", run_id=request.run_id, error=str(exc))
        raise NotFoundError(message=str(exc)) from exc
    except ValueError as exc:
        logger.warning("scenarios.create_invalid", run_id=request.run_id, error=str(exc))
        raise BadRequestError(message=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.error("scenarios.create_db_error", error=str(exc), exc_info=True)
        raise DatabaseError(
            message="Failed to save scenario plan",
            details={"error": str(exc)},
        ) from exc


@router.get(
    "",
    response_model=ScenarioListResponse,
    summary="List saved scenario plans",
    description="List saved scenario plans, newest first. Returns 200 + an "
    "empty list when no plans exist.",
)
async def list_scenarios(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum plans to return."),
    offset: int = Query(default=0, ge=0, description="Number of plans to skip."),
) -> ScenarioListResponse:
    """List saved scenario plans.

    Args:
        db: Async database session from dependency.
        limit: Maximum plans to return (1-100).
        offset: Number of plans to skip.

    Returns:
        A page of saved plans plus the total count.
    """
    return await ScenarioService().list_plans(db, limit=limit, offset=offset)


@router.get(
    "/{scenario_id}",
    response_model=ScenarioPlanResponse,
    summary="Get a saved scenario plan",
    description="Fetch one saved plan, including its embedded comparison snapshot.",
)
async def get_scenario(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
) -> ScenarioPlanResponse:
    """Get a saved scenario plan by id.

    Args:
        scenario_id: External identifier of the plan.
        db: Async database session from dependency.

    Returns:
        The saved plan with its embedded comparison snapshot.

    Raises:
        NotFoundError: When no plan matches ``scenario_id``.
    """
    plan = await ScenarioService().get_plan(db, scenario_id)
    if plan is None:
        raise NotFoundError(message=f"Scenario plan not found: {scenario_id}")
    return plan


@router.delete(
    "/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a saved scenario plan",
    description="Delete a saved scenario plan by id.",
)
async def delete_scenario(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a saved scenario plan.

    Args:
        scenario_id: External identifier of the plan.
        db: Async database session from dependency.

    Raises:
        NotFoundError: When no plan matches ``scenario_id``.
    """
    deleted = await ScenarioService().delete_plan(db, scenario_id)
    if not deleted:
        raise NotFoundError(message=f"Scenario plan not found: {scenario_id}")
