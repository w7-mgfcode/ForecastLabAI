"""Pydantic schemas for the runtime configuration slice.

Request bodies keep ``ConfigDict(strict=True)`` per repo policy
(``.claude/rules/security-patterns.md``). Every field here is a JSON-native
scalar (str/int/float/bool), so no ``Field(strict=False)`` override is needed
and ``app/core/tests/test_strict_mode_policy.py`` stays green.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import validate_model_identifier

# ``Settings`` fields the operator may override at runtime via PATCH /config/ai.
ALLOWED_OVERRIDE_KEYS: frozenset[str] = frozenset(
    {
        "agent_default_model",
        "agent_fallback_model",
        "agent_temperature",
        "agent_max_tokens",
        "agent_thinking_budget",
        "rag_embedding_provider",
        "rag_embedding_model",
        "rag_embedding_dimension",
        "ollama_base_url",
        "ollama_embedding_model",
        "openai_api_key",
        "anthropic_api_key",
        "google_api_key",
    }
)

# Subset of ALLOWED_OVERRIDE_KEYS holding secrets: masked in responses,
# mirrored into os.environ on save, and NEVER logged or returned raw.
SECRET_KEYS: frozenset[str] = frozenset(
    {
        "openai_api_key",
        "anthropic_api_key",
        "google_api_key",
    }
)

# Maps a secret Settings field to its environment-variable name.
SECRET_ENV_NAMES: dict[str, str] = {
    "openai_api_key": "OPENAI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "google_api_key": "GOOGLE_API_KEY",
}


class ApiKeyStatus(BaseModel):
    """Presence + masked preview of one provider API key (response only)."""

    provider: str = Field(description="Provider name: 'openai' | 'anthropic' | 'google'")
    is_set: bool = Field(description="True when a non-empty key is configured")
    masked: str | None = Field(
        default=None,
        description="Masked preview (e.g. 'sk-ant…3f9a'); None when no key is set",
    )


class AIModelConfig(BaseModel):
    """Effective AI-model configuration — GET /config/ai response."""

    agent_default_model: str = Field(description="Active agent LLM identifier")
    agent_fallback_model: str = Field(description="Fallback agent LLM identifier")
    agent_temperature: float = Field(description="Agent sampling temperature")
    agent_max_tokens: int = Field(description="Agent response token cap")
    agent_thinking_budget: int | None = Field(
        description="Extended-reasoning token budget (Gemini 2.5+); None disables it"
    )
    rag_embedding_provider: str = Field(description="RAG embedding provider: 'openai' | 'ollama'")
    rag_embedding_model: str = Field(description="OpenAI embedding model name")
    rag_embedding_dimension: int = Field(description="Embedding vector dimension")
    ollama_base_url: str = Field(description="Ollama server base URL")
    ollama_embedding_model: str = Field(description="Ollama embedding model name")
    api_keys: list[ApiKeyStatus] = Field(description="Per-provider key presence (masked)")
    overridden_keys: list[str] = Field(
        description="Keys currently sourced from app_config rather than the environment"
    )


class AIModelConfigUpdate(BaseModel):
    """Partial update for the AI-model configuration — PATCH /config/ai body.

    All fields are optional; only the non-null ones are persisted and applied.
    """

    model_config = ConfigDict(strict=True)

    agent_default_model: str | None = None
    agent_fallback_model: str | None = None
    agent_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    agent_max_tokens: int | None = Field(default=None, ge=1)
    agent_thinking_budget: int | None = Field(default=None, ge=1)
    rag_embedding_provider: Literal["openai", "ollama"] | None = None
    rag_embedding_model: str | None = None
    rag_embedding_dimension: int | None = Field(default=None, ge=1)
    ollama_base_url: str | None = None
    ollama_embedding_model: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    force: bool = Field(
        default=False,
        description="Bypass the embedding-dimension-change guard (re-index required)",
    )

    @field_validator("agent_default_model", "agent_fallback_model")
    @classmethod
    def _check_model_identifier(cls, v: str | None) -> str | None:
        """Validate agent model identifiers (incl. the ``ollama:`` provider)."""
        if v is None:
            return None
        return validate_model_identifier(v)


class OllamaModel(BaseModel):
    """One model pulled on the Ollama host (from GET /api/tags)."""

    name: str = Field(description="Model name, e.g. 'llama3.1:latest'")
    size_bytes: int | None = Field(default=None, description="On-disk size in bytes")
    family: str | None = Field(default=None, description="Model family, e.g. 'llama'")


class ProviderHealth(BaseModel):
    """Connectivity status for one AI provider — GET /config/providers/health."""

    provider: str = Field(description="'ollama' | 'openai' | 'anthropic' | 'google'")
    reachable: bool = Field(description="True when the provider is usable")
    detail: str = Field(description="Human-readable status detail")
    models: list[str] = Field(
        default_factory=list,
        description="Local model names (populated for the 'ollama' provider)",
    )
