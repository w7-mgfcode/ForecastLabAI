"""Shared pytest fixtures for ForecastLabAI tests."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.main import app


@pytest.fixture
async def client():
    """Create async HTTP client for testing FastAPI endpoints."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
async def db_session():
    """Create async database session for integration tests.

    Uses existing tables from migrations. Rolls back changes after each test.
    Requires PostgreSQL to be running (docker-compose up -d) and migrations applied.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    # Create session
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        try:
            yield session
        finally:
            # Clean up test data by rolling back any uncommitted changes
            await session.rollback()

    await engine.dispose()
