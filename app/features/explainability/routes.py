"""API routes for the explainability slice.

Three endpoints under a self-owned ``/explain`` namespace produce rule-based
forecast explanations. Service-layer ``ValueError`` (unsupported model type,
too-short series) maps to an RFC 7807 400; a missing run/job maps to a 404;
``SQLAlchemyError`` maps to a 500 — never a bare ``HTTPException``.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import BadRequestError, DatabaseError, NotFoundError
from app.core.logging import get_logger
from app.features.explainability.schemas import (
    ExplainForecastRequest,
    ForecastExplanation,
)
from app.features.explainability.service import ExplainabilityService

logger = get_logger(__name__)

router = APIRouter(prefix="/explain", tags=["explainability"])


@router.post(
    "/forecast",
    response_model=ForecastExplanation,
    status_code=status.HTTP_200_OK,
    summary="Explain an ad-hoc baseline forecast",
    description="""
Compute a rule-based explanation for the h=1 forecast a named baseline model
would produce on the series ending at `as_of_date`.

**Inputs:** `store_id`, `product_id`, `model_type` (`naive` / `seasonal_naive` /
`moving_average`), `as_of_date`, and optional `season_length` / `window_size`.

**Output:** a `ForecastExplanation` — ordered driver contributions, advisory
retail reason codes (correlation, never causation), a confidence band, caveats,
and an agent-readable summary. The series and every reason-code query are
time-safe (`<= as_of_date`).

An unsupported `model_type` (`lightgbm` / `regression`) or a series too short to
forecast returns an RFC 7807 400 — never a 500.
""",
)
async def explain_forecast(
    request: ExplainForecastRequest,
    db: AsyncSession = Depends(get_db),
) -> ForecastExplanation:
    """Explain an ad-hoc baseline forecast.

    Args:
        request: Store/product/model/cutoff parameters.
        db: Async database session from dependency.

    Returns:
        The rule-based forecast explanation.

    Raises:
        BadRequestError: For an unsupported model type or a too-short series.
        DatabaseError: When persistence fails.
    """
    try:
        return await ExplainabilityService().explain_forecast(db, request)
    except ValueError as exc:
        logger.warning("explainability.forecast_invalid", error=str(exc))
        raise BadRequestError(message=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.error("explainability.forecast_db_error", error=str(exc), exc_info=True)
        raise DatabaseError(
            message="Failed to generate forecast explanation",
            details={"error": str(exc)},
        ) from exc


@router.get(
    "/runs/{run_id}",
    response_model=ForecastExplanation,
    summary="Explain a registry model run",
    description="""
Explain a registry `model_run`. The baseline config is reconstructed from
`model_run.model_config`, and `data_window_end` is used as the series cutoff.

A missing `run_id` returns a 404; a non-baseline run (`lightgbm` / `regression`)
returns a 400 — explanations are available for baseline models only.
""",
)
async def explain_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> ForecastExplanation:
    """Explain a registry model run.

    Args:
        run_id: External run identifier.
        db: Async database session from dependency.

    Returns:
        The rule-based forecast explanation.

    Raises:
        NotFoundError: When no run matches ``run_id``.
        BadRequestError: For a non-baseline run or a too-short series.
        DatabaseError: When persistence fails.
    """
    try:
        explanation = await ExplainabilityService().explain_run(db, run_id)
    except ValueError as exc:
        logger.warning("explainability.run_invalid", run_id=run_id, error=str(exc))
        raise BadRequestError(message=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.error("explainability.run_db_error", error=str(exc), exc_info=True)
        raise DatabaseError(
            message="Failed to generate run explanation",
            details={"error": str(exc)},
        ) from exc
    if explanation is None:
        raise NotFoundError(message=f"Model run not found: {run_id}")
    return explanation


@router.get(
    "/jobs/{job_id}",
    response_model=ForecastExplanation,
    summary="Explain a completed predict job",
    description="""
Explain a completed `predict` job. `store_id`, `product_id`, and `model_type`
are read from `job.result`; the series cutoff is the day before the first
forecast date.

A missing `job_id` returns a 404; a job that is not a completed predict job
returns a 400.
""",
)
async def explain_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> ForecastExplanation:
    """Explain a completed predict job.

    Args:
        job_id: External job identifier.
        db: Async database session from dependency.

    Returns:
        The rule-based forecast explanation.

    Raises:
        NotFoundError: When no job matches ``job_id``.
        BadRequestError: When the job is not a completed predict job, or for a
            too-short series.
        DatabaseError: When persistence fails.
    """
    try:
        explanation = await ExplainabilityService().explain_job(db, job_id)
    except ValueError as exc:
        logger.warning("explainability.job_invalid", job_id=job_id, error=str(exc))
        raise BadRequestError(message=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.error("explainability.job_db_error", error=str(exc), exc_info=True)
        raise DatabaseError(
            message="Failed to generate job explanation",
            details={"error": str(exc)},
        ) from exc
    if explanation is None:
        raise NotFoundError(message=f"Job not found: {job_id}")
    return explanation
