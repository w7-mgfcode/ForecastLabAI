"""Unit tests for agent base helpers (Ollama-aware model factory)."""

from collections.abc import Iterator

import pytest
from pydantic_ai.models.openai import OpenAIChatModel

from app.core.config import get_settings
from app.features.agents.agents.base import build_agent_model, validate_api_key_for_model
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


def test_experiment_agent_uses_prompted_output():
    """The experiment agent uses PromptedOutput, not the default ToolOutput.

    Regression for issue #173: weaker/local models cannot satisfy the
    default tool-based structured-output mode and fail output validation.
    """
    settings = get_settings()
    settings.agent_default_model = "ollama:llama3.1"
    agent = create_experiment_agent()
    assert type(agent._output_schema).__name__ == "PromptedOutputSchema"


def test_rag_assistant_agent_uses_prompted_output():
    """The RAG assistant agent uses PromptedOutput (issue #173)."""
    settings = get_settings()
    settings.agent_default_model = "ollama:llama3.1"
    agent = create_rag_assistant_agent()
    assert type(agent._output_schema).__name__ == "PromptedOutputSchema"
