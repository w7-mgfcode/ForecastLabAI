"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.health import router as health_router
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIdMiddleware
from app.features.analytics.routes import router as analytics_router
from app.features.backtesting.routes import router as backtesting_router
from app.features.dimensions.routes import router as dimensions_router
from app.features.featuresets.routes import router as featuresets_router
from app.features.forecasting.routes import router as forecasting_router
from app.features.ingest.routes import router as ingest_router
from app.features.jobs.routes import router as jobs_router
from app.features.registry.routes import router as registry_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup/shutdown.

    Args:
        _app: FastAPI application instance (unused, required by lifespan protocol).

    Yields:
        None after startup, cleans up on shutdown.
    """
    settings = get_settings()

    # Startup
    configure_logging()
    logger.info(
        "app.startup_started",
        app_name=settings.app_name,
        app_env=settings.app_env,
        debug=settings.debug,
    )

    yield

    # Shutdown
    logger.info("app.shutdown_completed")


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Portfolio-grade retail demand forecasting system",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

    # Middleware (order matters - first added = outermost)
    app.add_middleware(RequestIdMiddleware)

    # Exception handlers
    register_exception_handlers(app)

    # Routers
    app.include_router(health_router)
    app.include_router(dimensions_router)
    app.include_router(analytics_router)
    app.include_router(jobs_router)
    app.include_router(ingest_router)
    app.include_router(featuresets_router)
    app.include_router(forecasting_router)
    app.include_router(backtesting_router)
    app.include_router(registry_router)

    return app


app = create_app()
