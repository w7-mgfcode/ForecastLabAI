"""Test fixtures for the demo slice."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

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
