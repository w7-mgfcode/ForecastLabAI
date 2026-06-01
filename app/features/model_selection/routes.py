"""FastAPI routes for the Forecast Champion Selector slice (issue #353).

Endpoints (all under ``/model-selection``):
- GET  /availability            — pair data-availability assessment
- POST /run                     — run candidate comparison + ranking (200)
- GET  /{selection_id}          — fetch a persisted selection run
- GET  /{selection_id}/ranking  — fetch just the ranking block
- POST /{selection_id}/train-winner — train the winning model
- POST /{selection_id}/train-selected — train a user-chosen candidate (override)
- POST /{selection_id}/predict  — forecast with the trained winner + decision
- POST /{selection_id}/promote  — promote the trained champion to a registry alias

Error mapping mirrors ``app/features/backtesting/routes.py``: ``ValueError`` →
``BadRequestError`` (RFC 7807 400), ``SQLAlchemyError`` → ``DatabaseError`` (500).
``NotFoundError`` / ``BadRequestError`` raised inside the service are
``ForecastLabError`` subclasses and bubble straight to the global handler.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import BadRequestError, DatabaseError
from app.core.logging import get_logger
from app.features.model_selection.schemas import (
    ForecastDecisionParams,
    ModelCatalogResponse,
    ModelSelectionRunRequest,
    ModelSelectionRunResponse,
    PairAvailabilityResponse,
    PredictWinnerResponse,
    PromoteRequest,
    PromoteResponse,
    RankingResult,
    SubmitRunResponse,
    TrainSelectedRequest,
    TrainWinnerResponse,
)
from app.features.model_selection.service import ModelSelectionService

logger = get_logger(__name__)

router = APIRouter(prefix="/model-selection", tags=["model-selection"])


@router.get(
    "/availability",
    response_model=PairAvailabilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Assess data availability for a (store, product) pair",
)
async def get_availability(
    store_id: int = Query(..., ge=1, description="Store ID"),
    product_id: int = Query(..., ge=1, description="Product ID"),
    forecast_horizon: int = Query(14, ge=1, le=90, description="Forecast horizon in days"),
    db: AsyncSession = Depends(get_db),
) -> PairAvailabilityResponse:
    """Return coverage, demand, promotion, and a recommended split config."""
    service = ModelSelectionService()
    try:
        return await service.get_availability(db, store_id, product_id, forecast_horizon)
    except ValueError as exc:
        raise BadRequestError(message=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise DatabaseError(
            message="Failed to assess availability", details={"error": str(exc)}
        ) from exc


@router.get(
    "/models",
    response_model=ModelCatalogResponse,
    status_code=status.HTTP_200_OK,
    summary="List the backend-owned candidate-model capability catalog",
)
async def get_model_catalog() -> ModelCatalogResponse:
    """Return the static candidate-model catalog (no DB, no query params).

    Declared BEFORE ``GET /{selection_id}`` so Starlette matches the literal
    ``/models`` path and does not capture it as ``selection_id="models"``.
    """
    service = ModelSelectionService()
    return service.get_model_catalog()


@router.post(
    "/runs",
    response_model=SubmitRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit an async candidate comparison (fire-and-forget LRO)",
)
async def submit_run(
    request: ModelSelectionRunRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> SubmitRunResponse:
    """Submit an async selection run — returns 202 with monitor/cancel pointers.

    The candidate backtests run in a detached task; poll
    ``GET /model-selection/{selection_id}`` for live progress, terminal ranking,
    and the winner.
    """
    logger.info(
        "model_selection.runs_request_received",
        store_id=request.store_id,
        product_id=request.product_id,
        n_candidates=len(request.candidate_models),
    )
    service = ModelSelectionService()
    try:
        result = await service.submit_run(db, request)
        response.headers["Location"] = result.monitor_url
        response.headers["Retry-After"] = "2"
        return result
    except ValueError as exc:
        raise BadRequestError(message=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise DatabaseError(
            message="Failed to submit selection run", details={"error": str(exc)}
        ) from exc


@router.post(
    "/run",
    response_model=ModelSelectionRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Run candidate model comparison and select a champion",
)
async def run_selection(
    request: ModelSelectionRunRequest,
    db: AsyncSession = Depends(get_db),
) -> ModelSelectionRunResponse:
    """Validate availability, backtest candidates, rank, and persist the run."""
    logger.info(
        "model_selection.request_received",
        store_id=request.store_id,
        product_id=request.product_id,
        n_candidates=len(request.candidate_models),
        ranking_metric=request.ranking_metric,
    )
    service = ModelSelectionService()
    try:
        return await service.run_selection(db, request)
    except ValueError as exc:
        raise BadRequestError(message=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise DatabaseError(
            message="Failed to run model selection", details={"error": str(exc)}
        ) from exc


@router.get(
    "/{selection_id}",
    response_model=ModelSelectionRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch a persisted selection run",
)
async def get_selection(
    selection_id: str,
    db: AsyncSession = Depends(get_db),
) -> ModelSelectionRunResponse:
    """Return the full persisted selection run by id (404 when missing)."""
    service = ModelSelectionService()
    try:
        return await service.get_selection(db, selection_id)
    except SQLAlchemyError as exc:
        raise DatabaseError(
            message="Failed to fetch selection run", details={"error": str(exc)}
        ) from exc


@router.delete(
    "/{selection_id}",
    response_model=ModelSelectionRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel an in-flight selection run (cooperative drain)",
    description=(
        "Cooperatively cancel an async selection run (Slice B). Pending "
        "candidates skip; running candidates observe ``asyncio.CancelledError`` "
        "at the next safe yield — sklearn / LightGBM fits are uncancellable "
        "mid-call, so an in-flight fit may finish first. Returns:\n\n"
        "- ``200`` settled run on a clean drain\n"
        "- ``404`` RFC 7807 if the run does not exist\n"
        "- ``409`` RFC 7807 if the run is already terminal\n"
        "- ``504`` RFC 7807 if the drain exceeds "
        "``Settings.model_selection_cancel_drain_timeout_seconds``"
    ),
)
async def cancel_run(
    selection_id: str,
    db: AsyncSession = Depends(get_db),
) -> ModelSelectionRunResponse:
    """Cancel an in-flight selection run and return its settled record.

    ``NotFoundError`` (404) / ``ConflictError`` (409) / ``GatewayTimeoutError``
    (504) raised in-service bubble to the global RFC 7807 handler.
    """
    service = ModelSelectionService()
    try:
        return await service.cancel_run(db, selection_id)
    except SQLAlchemyError as exc:
        raise DatabaseError(
            message="Failed to cancel selection run", details={"error": str(exc)}
        ) from exc


@router.get(
    "/{selection_id}/ranking",
    response_model=RankingResult,
    status_code=status.HTTP_200_OK,
    summary="Fetch the ranking block for a selection run",
)
async def get_ranking(
    selection_id: str,
    db: AsyncSession = Depends(get_db),
) -> RankingResult:
    """Return just the ranking (winner, entries, confidence, reasons)."""
    service = ModelSelectionService()
    try:
        return await service.get_ranking(db, selection_id)
    except SQLAlchemyError as exc:
        raise DatabaseError(message="Failed to fetch ranking", details={"error": str(exc)}) from exc


@router.post(
    "/{selection_id}/train-winner",
    response_model=TrainWinnerResponse,
    status_code=status.HTTP_200_OK,
    summary="Train the winning model for a selection run",
)
async def train_winner(
    selection_id: str,
    db: AsyncSession = Depends(get_db),
) -> TrainWinnerResponse:
    """Train the champion and store its model bundle path."""
    service = ModelSelectionService()
    try:
        return await service.train_winner(db, selection_id)
    except ValueError as exc:
        raise BadRequestError(message=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise DatabaseError(
            message="Failed to train winning model", details={"error": str(exc)}
        ) from exc


@router.post(
    "/{selection_id}/train-selected",
    response_model=TrainWinnerResponse,
    status_code=status.HTTP_200_OK,
    summary="Train a user-chosen candidate (override)",
)
async def train_selected(
    selection_id: str,
    request: TrainSelectedRequest,
    db: AsyncSession = Depends(get_db),
) -> TrainWinnerResponse:
    """Train a chosen candidate (override). A non-candidate ``model_type`` → 400.

    Overriding the recommended winner returns ``is_override=true`` plus an
    ``override_warning`` and records the override reason on the run.
    """
    service = ModelSelectionService()
    try:
        return await service.train_selected(
            db, selection_id, request.model_type, request.override_reason
        )
    except ValueError as exc:
        raise BadRequestError(message=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise DatabaseError(
            message="Failed to train selected model", details={"error": str(exc)}
        ) from exc


@router.post(
    "/{selection_id}/predict",
    response_model=PredictWinnerResponse,
    status_code=status.HTTP_200_OK,
    summary="Forecast with the trained model + inventory decision",
)
async def predict_winner(
    selection_id: str,
    request: ForecastDecisionParams | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
) -> PredictWinnerResponse:
    """Generate a horizon forecast + a labeled safety-stock decision heuristic.

    The body is OPTIONAL — an empty body uses ``ForecastDecisionParams``
    defaults (lead_time_days=7, service_level=0.95). A feature-aware model 400s
    (use the What-If Planner instead).
    """
    params = request or ForecastDecisionParams()
    service = ModelSelectionService()
    try:
        forecast, decision = await service.predict_winner(
            db, selection_id, params.lead_time_days, params.service_level
        )
        return PredictWinnerResponse(
            selection_id=selection_id, forecast=forecast, decision=decision
        )
    except ValueError as exc:
        raise BadRequestError(message=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise DatabaseError(
            message="Failed to forecast with winning model", details={"error": str(exc)}
        ) from exc


@router.post(
    "/{selection_id}/promote",
    response_model=PromoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Promote the trained champion to a registry alias (approval-gated)",
)
async def promote(
    selection_id: str,
    request: PromoteRequest,
    db: AsyncSession = Depends(get_db),
) -> PromoteResponse:
    """Register a SUCCESS model run + alias for the trained champion.

    Approval-gated + audited: requires ``approved_by``; a non-recommended model
    requires ``acknowledge_non_recommended=true`` (else 422); promoting before
    training → 422; a bad ``alias_name`` → 422 at the schema boundary.
    """
    service = ModelSelectionService()
    try:
        return await service.promote(db, selection_id, request)
    except ValueError as exc:
        raise BadRequestError(message=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise DatabaseError(
            message="Failed to promote champion", details={"error": str(exc)}
        ) from exc
