"""Tests for the config service layer.

Unit tests mock the DB session and httpx; integration tests (marked
``integration``) run against a real Postgres via the ``db_session`` fixture.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.features.config import service
from app.features.config.schemas import AIModelConfigUpdate, OllamaModel


def _mock_db(chunk_count: int = 0, override_rows: list[Any] | None = None) -> MagicMock:
    """Build an AsyncSession mock covering execute()/commit() for the service."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = override_rows or []
    result.scalar_one.return_value = chunk_count
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


@contextmanager
def _patch_ollama_get(
    json_payload: dict[str, Any] | None = None,
    side_effect: Exception | None = None,
) -> Iterator[None]:
    """Patch httpx.AsyncClient so /api/tags calls are served from a fixture."""
    mock_response = MagicMock()
    mock_response.json.return_value = json_payload or {}
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    if side_effect is not None:
        mock_client.get = AsyncMock(side_effect=side_effect)
    else:
        mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.features.config.service.httpx.AsyncClient", return_value=mock_client):
        yield


# =============================================================================
# Unit tests — masking
# =============================================================================


class TestMaskSecret:
    """Tests for the secret-masking helper."""

    def test_empty_value_returns_none(self):
        """An unset key masks to None."""
        assert service._mask_secret("") is None

    def test_short_value_masked(self):
        """A short key shows only the trailing characters."""
        assert service._mask_secret("abcd1234") == "…1234"

    def test_long_value_never_leaks_raw(self):
        """A long key is masked and never contains its raw value."""
        raw = "sk-ant-api03-supersecretvalue9999"
        masked = service._mask_secret(raw)
        assert masked is not None
        assert raw not in masked
        assert masked.endswith("9999")


# =============================================================================
# Unit tests — get_effective_config
# =============================================================================


class TestGetEffectiveConfig:
    """Tests for get_effective_config."""

    @pytest.mark.asyncio
    async def test_get_effective_config_masks_secrets(self):
        """API keys appear masked — the raw value never reaches the response."""
        settings = get_settings()
        settings.anthropic_api_key = "sk-ant-supersecretvalue-0001"

        config = await service.get_effective_config(_mock_db())

        anthropic = next(k for k in config.api_keys if k.provider == "anthropic")
        assert anthropic.is_set is True
        assert anthropic.masked is not None
        assert "supersecretvalue" not in config.model_dump_json()

    @pytest.mark.asyncio
    async def test_get_effective_config_maps_agent_limits(self):
        """The agent session-limit fields are sourced from the Settings singleton."""
        settings = get_settings()
        # get_settings() returns a cached singleton — snapshot every field this
        # test mutates and restore it in a finally block so the mutation never
        # leaks into another test.
        fields = (
            "agent_max_tool_calls",
            "agent_timeout_seconds",
            "agent_retry_attempts",
            "agent_session_ttl_minutes",
            "agent_require_approval",
        )
        original = {field: getattr(settings, field) for field in fields}
        try:
            settings.agent_max_tool_calls = 7
            settings.agent_timeout_seconds = 99
            settings.agent_retry_attempts = 2
            settings.agent_session_ttl_minutes = 45
            settings.agent_require_approval = ["create_alias"]

            config = await service.get_effective_config(_mock_db())

            assert config.agent_max_tool_calls == 7
            assert config.agent_timeout_seconds == 99
            assert config.agent_retry_attempts == 2
            assert config.agent_session_ttl_minutes == 45
            assert config.agent_require_approval == ["create_alias"]
        finally:
            for field, value in original.items():
                setattr(settings, field, value)


# =============================================================================
# Unit tests — update_config
# =============================================================================


class TestUpdateConfig:
    """Tests for update_config."""

    @pytest.mark.asyncio
    async def test_update_config_resets_caches(self):
        """A successful update nulls the agent + embedding singletons."""
        from app.features.agents.agents import experiment, rag_assistant
        from app.features.rag import embeddings

        # Seed non-None sentinels so we can prove they were cleared.
        experiment._experiment_agent = MagicMock()
        rag_assistant._rag_assistant_agent = MagicMock()
        embeddings._embedding_provider = MagicMock()

        db = _mock_db()
        result = await service.update_config(db, AIModelConfigUpdate(agent_temperature=0.42))

        assert experiment._experiment_agent is None
        assert rag_assistant._rag_assistant_agent is None
        assert embeddings._embedding_provider is None
        assert result.agent_temperature == 0.42
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_update_config_empty_payload_rejected(self):
        """An update with no fields is a 400."""
        with pytest.raises(HTTPException) as exc:
            await service.update_config(_mock_db(), AIModelConfigUpdate())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_config_dimension_guard(self):
        """Changing the embedding dimension with chunks present is a 409."""
        db = _mock_db(chunk_count=5)
        with pytest.raises(HTTPException) as exc:
            await service.update_config(db, AIModelConfigUpdate(rag_embedding_dimension=768))
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_update_config_dimension_guard_bypassed_by_force(self):
        """force=true allows the embedding-dimension change despite chunks."""
        db = _mock_db(chunk_count=5)
        result = await service.update_config(
            db, AIModelConfigUpdate(rag_embedding_dimension=768, force=True)
        )
        assert result.rag_embedding_dimension == 768

    @pytest.mark.asyncio
    async def test_update_config_secret_mirrored_to_environment(self):
        """Saving an API key mirrors it into os.environ unconditionally."""
        import os

        db = _mock_db()
        await service.update_config(db, AIModelConfigUpdate(openai_api_key="sk-new-openai-key-123"))
        assert os.environ["OPENAI_API_KEY"] == "sk-new-openai-key-123"


# =============================================================================
# Unit tests — provider health + ollama models
# =============================================================================


class TestProviderHealth:
    """Tests for get_provider_health."""

    @pytest.mark.asyncio
    async def test_health_reports_ollama_reachable(self):
        """A reachable Ollama host reports its pulled models."""
        with patch(
            "app.features.config.service._fetch_ollama_models",
            new=AsyncMock(return_value=[OllamaModel(name="llama3.1:latest")]),
        ):
            health = await service.get_provider_health()
        ollama = next(h for h in health if h.provider == "ollama")
        assert ollama.reachable is True
        assert "llama3.1:latest" in ollama.models

    @pytest.mark.asyncio
    async def test_health_reports_ollama_unreachable(self):
        """An unreachable Ollama host reports reachable=False."""
        with patch(
            "app.features.config.service._fetch_ollama_models",
            new=AsyncMock(side_effect=httpx.ConnectError("refused")),
        ):
            health = await service.get_provider_health()
        ollama = next(h for h in health if h.provider == "ollama")
        assert ollama.reachable is False

    @pytest.mark.asyncio
    async def test_health_reports_cloud_key_presence(self):
        """Cloud providers report reachable iff a key is configured."""
        settings = get_settings()
        settings.openai_api_key = "sk-test-openai"
        settings.anthropic_api_key = ""

        with patch(
            "app.features.config.service._fetch_ollama_models",
            new=AsyncMock(side_effect=httpx.ConnectError("x")),
        ):
            health = await service.get_provider_health()

        openai = next(h for h in health if h.provider == "openai")
        anthropic = next(h for h in health if h.provider == "anthropic")
        assert openai.reachable is True
        assert anthropic.reachable is False


class TestListOllamaModels:
    """Tests for list_ollama_models."""

    @pytest.mark.asyncio
    async def test_list_ollama_models_parses_tags(self):
        """A /api/tags response is parsed into OllamaModel objects."""
        payload = {
            "models": [
                {
                    "name": "llama3.1:latest",
                    "model": "llama3.1",
                    "size": 4661224676,
                    "details": {"family": "llama"},
                },
                {"name": "nomic-embed-text:latest", "size": 274302450, "details": {}},
            ]
        }
        with _patch_ollama_get(json_payload=payload):
            models = await service.list_ollama_models()

        assert [m.name for m in models] == [
            "llama3.1:latest",
            "nomic-embed-text:latest",
        ]
        assert models[0].family == "llama"
        assert models[0].size_bytes == 4661224676

    @pytest.mark.asyncio
    async def test_list_ollama_models_unreachable_raises_502(self):
        """An unreachable Ollama host surfaces as a 502."""
        with _patch_ollama_get(side_effect=httpx.ConnectError("refused")):
            with pytest.raises(HTTPException) as exc:
                await service.list_ollama_models()
        assert exc.value.status_code == 502


# =============================================================================
# Integration tests — real Postgres round-trips
# =============================================================================


@pytest.mark.integration
class TestConfigServiceIntegration:
    """Integration tests requiring a real database."""

    @pytest.mark.asyncio
    async def test_update_and_read_round_trip(self, db_session):
        """An override persists and is reported by get_effective_config."""
        await service.update_config(db_session, AIModelConfigUpdate(agent_temperature=0.77))
        config = await service.get_effective_config(db_session)
        assert config.agent_temperature == 0.77
        assert "agent_temperature" in config.overridden_keys

    @pytest.mark.asyncio
    async def test_apply_overrides_on_startup_reapplies(self, db_session):
        """Persisted overrides are re-applied onto a fresh Settings singleton."""
        await service.update_config(db_session, AIModelConfigUpdate(agent_max_tokens=2048))
        # Simulate a process restart.
        get_settings.cache_clear()
        await service.apply_overrides_on_startup(db_session)
        assert get_settings().agent_max_tokens == 2048

    @pytest.mark.asyncio
    async def test_apply_overrides_on_startup_empty_is_noop(self, db_session):
        """With no persisted overrides, startup application is a clean no-op."""
        await service.apply_overrides_on_startup(db_session)
        config = await service.get_effective_config(db_session)
        assert config.overridden_keys == []
