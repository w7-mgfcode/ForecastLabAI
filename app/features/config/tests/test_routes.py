"""Unit tests for config slice routes.

The DB dependency is overridden with a stub session; the service layer is
patched so routes are exercised in isolation.
"""

from collections.abc import AsyncGenerator, Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.features.config import schemas
from app.main import app


def _sample_config(
    agent_default_model: str = "anthropic:claude-sonnet-4-5",
    agent_temperature: float = 0.1,
) -> schemas.AIModelConfig:
    """Build a representative AIModelConfig response."""
    return schemas.AIModelConfig(
        agent_default_model=agent_default_model,
        agent_fallback_model="openai:gpt-4o",
        agent_temperature=agent_temperature,
        agent_max_tokens=4096,
        agent_thinking_budget=None,
        rag_embedding_provider="openai",
        rag_embedding_model="text-embedding-3-small",
        rag_embedding_dimension=1536,
        ollama_base_url="http://localhost:11434",
        ollama_embedding_model="nomic-embed-text",
        api_keys=[schemas.ApiKeyStatus(provider="anthropic", is_set=True, masked="sk-ant-…1234")],
        overridden_keys=[],
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Test client with the DB dependency stubbed (no lifespan, no real DB)."""

    async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestGetAIConfig:
    """Tests for GET /config/ai."""

    def test_returns_effective_config(self, client):
        """The endpoint returns the effective config with masked keys."""
        with patch(
            "app.features.config.routes.service.get_effective_config",
            new=AsyncMock(return_value=_sample_config()),
        ):
            response = client.get("/config/ai")

        assert response.status_code == 200
        data = response.json()
        assert data["agent_default_model"] == "anthropic:claude-sonnet-4-5"
        assert data["api_keys"][0]["masked"] == "sk-ant-…1234"


class TestUpdateAIConfig:
    """Tests for PATCH /config/ai."""

    def test_patch_applies_change(self, client):
        """A valid update returns the new effective config."""
        with patch(
            "app.features.config.routes.service.update_config",
            new=AsyncMock(return_value=_sample_config(agent_temperature=0.3)),
        ):
            response = client.patch("/config/ai", json={"agent_temperature": 0.3})

        assert response.status_code == 200
        assert response.json()["agent_temperature"] == 0.3

    def test_patch_accepts_ollama_model(self, client):
        """An ollama agent model passes schema validation and reaches the service."""
        with patch(
            "app.features.config.routes.service.update_config",
            new=AsyncMock(return_value=_sample_config(agent_default_model="ollama:llama3.1")),
        ):
            response = client.patch("/config/ai", json={"agent_default_model": "ollama:llama3.1"})

        assert response.status_code == 200
        assert response.json()["agent_default_model"] == "ollama:llama3.1"

    def test_patch_rejects_invalid_model(self, client):
        """An invalid model identifier is rejected at the schema boundary (422)."""
        response = client.patch("/config/ai", json={"agent_default_model": "nope"})
        assert response.status_code == 422

    def test_patch_surfaces_dimension_conflict(self, client):
        """A 409 from the dimension guard propagates to the caller."""
        with patch(
            "app.features.config.routes.service.update_config",
            new=AsyncMock(side_effect=HTTPException(status_code=409, detail="dimension change")),
        ):
            response = client.patch("/config/ai", json={"rag_embedding_dimension": 768})

        assert response.status_code == 409


class TestProviderHealthRoute:
    """Tests for GET /config/providers/health."""

    def test_returns_health(self, client):
        """The endpoint returns one entry per provider."""
        with patch(
            "app.features.config.routes.service.get_provider_health",
            new=AsyncMock(
                return_value=[
                    schemas.ProviderHealth(
                        provider="ollama",
                        reachable=True,
                        detail="ok",
                        models=["llama3.1"],
                    ),
                ]
            ),
        ):
            response = client.get("/config/providers/health")

        assert response.status_code == 200
        assert response.json()[0]["provider"] == "ollama"


class TestOllamaModelsRoute:
    """Tests for GET /config/ollama/models."""

    def test_returns_models(self, client):
        """The endpoint returns the host's pulled models."""
        with patch(
            "app.features.config.routes.service.list_ollama_models",
            new=AsyncMock(return_value=[schemas.OllamaModel(name="llama3.1:latest")]),
        ):
            response = client.get("/config/ollama/models")

        assert response.status_code == 200
        assert response.json()[0]["name"] == "llama3.1:latest"

    def test_unreachable_returns_502(self, client):
        """An unreachable Ollama host surfaces as a 502."""
        with patch(
            "app.features.config.routes.service.list_ollama_models",
            new=AsyncMock(side_effect=HTTPException(status_code=502, detail="unreachable")),
        ):
            response = client.get("/config/ollama/models")

        assert response.status_code == 502
