"""Unit tests for config slice schemas."""

import pytest
from pydantic import ValidationError

from app.core.config import validate_model_identifier
from app.features.config.schemas import (
    AIModelConfig,
    AIModelConfigUpdate,
    ApiKeyStatus,
    OllamaModel,
    ProviderHealth,
)


class TestValidateModelIdentifier:
    """Tests for the shared validate_model_identifier helper."""

    def test_validate_model_identifier_accepts_ollama(self):
        """An 'ollama:<model>' identifier is accepted."""
        assert validate_model_identifier("ollama:llama3.1") == "ollama:llama3.1"

    def test_validate_model_identifier_accepts_cloud(self):
        """Cloud-provider identifiers keep working unchanged."""
        assert (
            validate_model_identifier("anthropic:claude-sonnet-4-5")
            == "anthropic:claude-sonnet-4-5"
        )

    def test_validate_model_identifier_rejects_blank_ollama(self):
        """'ollama:' with no model name is rejected."""
        with pytest.raises(ValueError, match="empty or blank"):
            validate_model_identifier("ollama:")

    def test_validate_model_identifier_rejects_missing_colon(self):
        """An identifier without a provider prefix is rejected."""
        with pytest.raises(ValueError, match="provider:model-name"):
            validate_model_identifier("llama3.1")

    def test_validate_model_identifier_rejects_unknown_provider(self):
        """An unknown provider is rejected."""
        with pytest.raises(ValueError, match="Unknown provider"):
            validate_model_identifier("pinecone:model")


class TestAIModelConfigUpdate:
    """Tests for the PATCH /config/ai request body."""

    def test_accepts_ollama_model(self):
        """The update body accepts an ollama agent model."""
        upd = AIModelConfigUpdate(agent_default_model="ollama:llama3.1")
        assert upd.agent_default_model == "ollama:llama3.1"

    def test_rejects_blank_ollama_model(self):
        """A blank ollama model identifier fails validation."""
        with pytest.raises(ValidationError):
            AIModelConfigUpdate(agent_default_model="ollama:")

    def test_rejects_unknown_provider(self):
        """An unknown provider on the fallback model fails validation."""
        with pytest.raises(ValidationError):
            AIModelConfigUpdate(agent_fallback_model="bad:model")

    def test_force_defaults_false(self):
        """The dimension-guard bypass flag defaults to False."""
        assert AIModelConfigUpdate().force is False

    def test_temperature_range_enforced(self):
        """Temperature above the allowed range fails validation."""
        with pytest.raises(ValidationError):
            AIModelConfigUpdate(agent_temperature=3.0)

    def test_embedding_provider_literal_enforced(self):
        """Only 'openai' and 'ollama' are valid embedding providers."""
        with pytest.raises(ValidationError):
            AIModelConfigUpdate.model_validate({"rag_embedding_provider": "pinecone"})

    def test_all_fields_optional(self):
        """An empty update body is structurally valid (rejected later in service)."""
        upd = AIModelConfigUpdate()
        assert upd.agent_default_model is None
        assert upd.rag_embedding_dimension is None

    def test_model_validate_json_path(self):
        """Exercise FastAPI's validate_python path on the strict request body.

        Mirrors the strict-mode policy requirement: every strict request body
        gets at least one model_validate({...}) case.
        """
        upd = AIModelConfigUpdate.model_validate(
            {"agent_temperature": 0.5, "agent_default_model": "ollama:llama3.1"}
        )
        assert upd.agent_temperature == 0.5
        assert upd.agent_default_model == "ollama:llama3.1"


class TestResponseSchemas:
    """Tests for the response-only schemas."""

    def test_ai_model_config_constructs(self):
        """AIModelConfig accepts a full effective-config payload."""
        cfg = AIModelConfig(
            agent_default_model="anthropic:claude-sonnet-4-5",
            agent_fallback_model="openai:gpt-4o",
            agent_temperature=0.1,
            agent_max_tokens=4096,
            agent_thinking_budget=None,
            rag_embedding_provider="openai",
            rag_embedding_model="text-embedding-3-small",
            rag_embedding_dimension=1536,
            ollama_base_url="http://localhost:11434",
            ollama_embedding_model="nomic-embed-text",
            api_keys=[],
            overridden_keys=[],
        )
        assert cfg.agent_thinking_budget is None

    def test_api_key_status(self):
        """ApiKeyStatus carries presence + a masked preview."""
        status = ApiKeyStatus(provider="anthropic", is_set=True, masked="sk-ant-…3f9a")
        assert status.is_set is True
        assert status.masked == "sk-ant-…3f9a"

    def test_ollama_model_optional_fields(self):
        """OllamaModel size/family default to None."""
        model = OllamaModel(name="llama3.1:latest")
        assert model.size_bytes is None
        assert model.family is None

    def test_provider_health_defaults_models_empty(self):
        """ProviderHealth.models defaults to an empty list."""
        health = ProviderHealth(provider="openai", reachable=True, detail="ok")
        assert health.models == []
