"""Unit tests for agent base helpers (Ollama-aware model factory)."""

from collections.abc import Iterator

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.models.openai import OpenAIChatModel

from app.core.config import get_settings
from app.features.agents.agents.base import (
    TOOL_USAGE_INSTRUCTIONS,
    build_agent_model,
    recoverable,
    validate_api_key_for_model,
)


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


def test_tool_usage_instructions_use_registered_tool_names():
    """The prompt must name tools by their registered `tool_*` names (#175)."""
    for name in (
        "tool_list_runs",
        "tool_run_backtest",
        "tool_compare_backtest_results",
        "tool_compare_runs",
        "tool_create_alias",
        "tool_archive_run",
    ):
        assert name in TOOL_USAGE_INSTRUCTIONS


async def test_recoverable_converts_valueerror_to_model_retry():
    """A ValueError from a tool becomes a ModelRetry the model can recover from (#176)."""

    @recoverable
    async def tool() -> str:
        raise ValueError("No data found for store=1")

    with pytest.raises(ModelRetry, match="No data found for store=1"):
        await tool()


async def test_recoverable_passes_through_other_exceptions():
    """Non-ValueError exceptions are genuine bugs — they must still propagate."""

    @recoverable
    async def tool() -> str:
        raise RuntimeError("a real bug")

    with pytest.raises(RuntimeError, match="a real bug"):
        await tool()


async def test_recoverable_returns_value_on_success():
    """The decorator is transparent when the tool succeeds."""

    @recoverable
    async def tool() -> str:
        return "ok"

    assert await tool() == "ok"
