"""Unit tests for agent base helpers (Ollama-aware model factory)."""

from collections.abc import Iterator

import pytest
from pydantic_ai.models.openai import OpenAIChatModel

from app.core.config import get_settings
from app.features.agents.agents.base import (
    build_agent_model,
    get_agent_retries,
    validate_api_key_for_model,
)
from app.features.agents.agents.experiment import create_experiment_agent
from app.features.agents.agents.rag_assistant import create_rag_assistant_agent


@pytest.fixture(autouse=True)
def _reset_settings() -> Iterator[None]:
    """Reset the settings cache so key mutations do not leak across tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_build_agent_model_cloud_returns_string():
    """A cloud identifier is returned unchanged (plain-string Agent path)."""
    assert build_agent_model("anthropic:claude-sonnet-4-5") == "anthropic:claude-sonnet-4-5"


def test_build_agent_model_openai_returns_string():
    """An openai identifier is also returned unchanged."""
    assert build_agent_model("openai:gpt-4o") == "openai:gpt-4o"


def test_build_agent_model_ollama_returns_model_object():
    """An ollama identifier becomes a configured OpenAIChatModel object."""
    model = build_agent_model("ollama:llama3.1")
    assert isinstance(model, OpenAIChatModel)


def test_validate_api_key_for_model_ollama_skips_key_check():
    """The ollama provider needs no API key — validation must not raise."""
    settings = get_settings()
    settings.anthropic_api_key = ""
    settings.openai_api_key = ""
    settings.google_api_key = ""
    # Should return without raising even though no cloud key is configured.
    validate_api_key_for_model("ollama:llama3.1")


def test_get_agent_retries_returns_configured_value():
    """get_agent_retries reflects the agent_retry_attempts setting."""
    settings = get_settings()
    settings.agent_retry_attempts = 5
    assert get_agent_retries() == 5


def test_experiment_agent_applies_retry_attempts():
    """The experiment agent is built with the configured retry budget.

    Regression for issue #170: agent_retry_attempts was never passed to
    Agent(), so PydanticAI silently used its default of 1.
    """
    settings = get_settings()
    settings.agent_default_model = "ollama:llama3.1"
    settings.agent_retry_attempts = 4

    agent = create_experiment_agent()

    assert agent._max_output_retries == 4
    assert agent._max_tool_retries == 4


def test_rag_assistant_agent_applies_retry_attempts():
    """The RAG assistant agent is built with the configured retry budget."""
    settings = get_settings()
    settings.agent_default_model = "ollama:llama3.1"
    settings.agent_retry_attempts = 4

    agent = create_rag_assistant_agent()

    assert agent._max_output_retries == 4
    assert agent._max_tool_retries == 4
