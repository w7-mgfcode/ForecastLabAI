"""Test fixtures for the demo slice."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.features.demo.models import ShowcaseWorkspace
from app.main import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """In-process HTTP client over ASGITransport (no network).

    Unit route tests monkeypatch the demo service, so no database override is
    needed here -- the real pipeline never runs through this client.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://demo-test",
    ) as ac:
        yield ac


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session; wipe every showcase_workspace row on teardown.

    E1 (#390) integration fixture (pattern:
    ``app/features/scenarios/tests/conftest.py``). ``showcase_workspace`` is a
    slice-private table -- no seeder or other slice writes it -- so the
    teardown safely wipes it whole rather than relying on a row marker.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.execute(delete(ShowcaseWorkspace))
            await session.commit()

    await engine.dispose()
