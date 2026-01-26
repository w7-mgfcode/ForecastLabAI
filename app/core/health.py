"""Health check endpoints."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: Literal["ok", "degraded", "unhealthy"]
    database: Literal["connected", "disconnected"] | None = None


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Basic health check endpoint.

    Returns:
        Health status response.
    """
    logger.debug("health.check_started")
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
async def readiness_check(
    db: AsyncSession = Depends(get_db),
) -> HealthResponse:
    """Readiness check including database connectivity.

    Args:
        db: Database session dependency.

    Returns:
        Health status with database state.
    """
    logger.debug("health.readiness_check_started")

    try:
        await db.execute(text("SELECT 1"))
        logger.info("health.database_connected")
        return HealthResponse(status="ok", database="connected")
    except Exception as e:
        logger.error(
            "health.database_disconnected",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        return HealthResponse(status="unhealthy", database="disconnected")
