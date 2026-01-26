"""Tests for health check endpoints."""

import pytest


@pytest.mark.asyncio
async def test_health_check_returns_ok(client):
    """Health endpoint should return status ok."""
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_check_includes_request_id_header(client):
    """Health endpoint should include X-Request-ID in response."""
    response = await client.get("/health")

    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0


@pytest.mark.asyncio
async def test_health_check_uses_provided_request_id(client):
    """Health endpoint should echo back provided X-Request-ID."""
    custom_id = "test-request-id-12345"
    response = await client.get("/health", headers={"X-Request-ID": custom_id})

    assert response.headers["X-Request-ID"] == custom_id
