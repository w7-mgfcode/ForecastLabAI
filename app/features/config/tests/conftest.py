"""Test fixtures for the config feature."""

from collections.abc import AsyncGenerator, Iterator

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.features.config.models import AppConfig


@pytest.fixture(autouse=True)
def reset_caches() -> Iterator[None]:
    """Reset the settings cache + agent/embedding singletons between tests.

    Config tests mutate the cached ``Settings`` singleton and the agent /
    embedding module globals; isolating them keeps tests order-independent.
    """
    from app.features.agents.agents import experiment, rag_assistant
    from app.features.rag import embeddings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    experiment._experiment_agent = None
    rag_assistant._rag_assistant_agent = None
    embeddings._embedding_provider = None


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async DB session for integration tests; wipes app_config on teardown.

    Requires PostgreSQL to be running (docker-compose up -d) and migrations
    applied.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.execute(delete(AppConfig))
            await session.commit()

    await engine.dispose()
