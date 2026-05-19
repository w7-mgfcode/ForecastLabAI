"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import get_session_maker
from app.core.exceptions import register_exception_handlers
from app.core.health import router as health_router
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIdMiddleware
from app.features.agents.routes import router as agents_router
from app.features.agents.websocket import router as agents_ws_router
from app.features.analytics.routes import router as analytics_router
from app.features.backtesting.routes import router as backtesting_router
from app.features.config.routes import router as config_router
from app.features.config.service import apply_overrides_on_startup
from app.features.demo.routes import router as demo_router
from app.features.dimensions.routes import router as dimensions_router
from app.features.featuresets.routes import router as featuresets_router
from app.features.forecasting.routes import router as forecasting_router
from app.features.ingest.routes import router as ingest_router
from app.features.jobs.routes import router as jobs_router
from app.features.ops.routes import router as ops_router
from app.features.rag.routes import router as rag_router
from app.features.registry.routes import router as registry_router
from app.features.seeder.routes import router as seeder_router

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

    # Re-apply persisted runtime config overrides onto the Settings singleton.
    # Warn-and-continue: a missing app_config table must never block startup.
    try:
        session_maker = get_session_maker()
        async with session_maker() as db:
            await apply_overrides_on_startup(db)
    except Exception as exc:  # config must never block startup
        logger.warning(
            "config.overrides_skipped",
            error=str(exc),
            error_type=type(exc).__name__,
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
    # CORS middleware - allow frontend to access API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server (default)
            "http://localhost:5174",  # Vite dev server (alternate port)
            "http://localhost:5175",  # Vite dev server (alternate port)
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:5175",
            "http://10.0.0.121:5173",  # LAN access
            "http://10.0.0.121:5174",
            "http://10.0.0.121:5175",
            "http://192.168.9.73:5173",
        ]
        if settings.is_development
        else [],
        # Allow private LAN IP ranges in development so frontend can run from
        # phones/laptops without hardcoding every host/IP combination.
        allow_origin_regex=(
            r"^https?://("
            r"localhost|127\.0\.0\.1|"
            r"10\.\d+\.\d+\.\d+|"
            r"192\.168\.\d+\.\d+|"
            r"172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+"
            r")(:\d+)?$"
            if settings.is_development
            else None
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)

    # Exception handlers
    register_exception_handlers(app)

    # Routers
    app.include_router(health_router)
    app.include_router(dimensions_router)
    app.include_router(analytics_router)
    app.include_router(ops_router)
    app.include_router(jobs_router)
    app.include_router(ingest_router)
    app.include_router(featuresets_router)
    app.include_router(forecasting_router)
    app.include_router(backtesting_router)
    app.include_router(registry_router)
    app.include_router(rag_router)
    app.include_router(agents_router)
    app.include_router(agents_ws_router)
    app.include_router(seeder_router)
    app.include_router(demo_router)
    app.include_router(config_router)

    return app


app = create_app()
