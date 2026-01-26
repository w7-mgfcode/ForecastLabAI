"""Tests for request middleware."""

import pytest


@pytest.mark.asyncio
async def test_request_id_middleware_generates_id(client):
    """Middleware should generate request ID if not provided."""
    response = await client.get("/health")

    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert len(request_id) == 36  # UUID format


@pytest.mark.asyncio
async def test_request_id_middleware_preserves_provided_id(client):
    """Middleware should preserve client-provided request ID."""
    custom_id = "my-custom-request-id"
    response = await client.get("/health", headers={"X-Request-ID": custom_id})

    assert response.headers["X-Request-ID"] == custom_id


@pytest.mark.asyncio
async def test_request_id_middleware_different_ids_per_request(client):
    """Each request should get a unique ID if not provided."""
    response1 = await client.get("/health")
    response2 = await client.get("/health")

    id1 = response1.headers["X-Request-ID"]
    id2 = response2.headers["X-Request-ID"]

    assert id1 != id2
