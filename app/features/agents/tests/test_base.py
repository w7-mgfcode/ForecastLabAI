"""Unit tests for agent base helpers (Ollama-aware model factory)."""

import re
from collections.abc import Iterator
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel

from app.core.config import get_settings
from app.features.agents.agents.base import (
    TOOL_USAGE_INSTRUCTIONS,
    build_agent_model,
    get_agent_retries,
    recoverable,
    validate_api_key_for_model,
)
from app.features.agents.agents.experiment import (
    EXPERIMENT_SYSTEM_PROMPT,
    create_experiment_agent,
)
from app.features.agents.agents.rag_assistant import create_rag_assistant_agent
from app.features.agents.deps import AgentDeps
from app.features.agents.schemas import ExperimentReport, RAGAnswer


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


def test_prompts_only_reference_registered_tool_names() -> None:
    """Every `tool_*` name in the agent prompts must be an actually-registered tool.

    Regression for issue #175: the prompts named tools as `run_backtest`,
    `list_runs`, … but the registered tools are `tool_`-prefixed, so weaker
    models called unknown tool names. This test is the single source of truth
    for that invariant — the registered set is read off the built agent (not a
    hardcoded list), so drift in either direction (a renamed tool or an edited
    prompt) fails CI.
    """
    settings = get_settings()
    settings.agent_default_model = "ollama:llama3.1"
    agent = create_experiment_agent()

    captured: dict[str, set[str]] = {}

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captured["registered"] = {tool.name for tool in info.function_tools}
        # End the run immediately with a PromptedOutput-parseable text reply.
        return ModelResponse(parts=[TextPart(content='{"summary": "noop"}')])

    agent.run_sync(
        "noop",
        model=FunctionModel(respond),
        deps=AgentDeps(db=AsyncMock(), session_id="test-tool-names"),
    )
    registered = captured["registered"]

    # Tool names the prompts instruct the model to call. EXPERIMENT_SYSTEM_PROMPT
    # already embeds TOOL_USAGE_INSTRUCTIONS; both are scanned to stay correct
    # even if that embedding changes.
    prompt_text = TOOL_USAGE_INSTRUCTIONS + EXPERIMENT_SYSTEM_PROMPT
    referenced = set(re.findall(r"\btool_[a-z_]+\b", prompt_text))

    assert referenced, "expected the prompts to name at least one tool"
    unknown = referenced - registered
    assert not unknown, f"prompts reference unregistered tools: {sorted(unknown)}"


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


def test_recoverable_rejects_sync_function() -> None:
    """@recoverable is async-only — applying it to a sync function fails fast.

    Without the guard a sync function would be wrapped and then ``await``ed,
    surfacing a confusing ``TypeError: ... is not awaitable`` only at call
    time. The decorator rejects it at decoration time instead.
    """

    def sync_tool() -> str:
        return "nope"

    # recoverable is async-only by type; cast bypasses the static check so the
    # runtime guard itself can be exercised.
    with pytest.raises(TypeError, match="async tool functions only"):
        recoverable(cast(Any, sync_tool))


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


def test_experiment_agent_uses_prompted_output() -> None:
    """The experiment agent runs in PromptedOutput mode, not default ToolOutput.

    Regression for issue #173: weaker/local models answer in prose and cannot
    satisfy the tool-call output contract that the default ToolOutput mode
    requires. PromptedOutput puts the JSON schema in the prompt and parses the
    model's text reply instead.

    This is asserted behaviorally via the public ``FunctionModel`` test double:
    PromptedOutput mode registers no ``final_result`` output tool, and a
    plain-text JSON reply is still parsed into a valid ``ExperimentReport``.
    """
    settings = get_settings()
    settings.agent_default_model = "ollama:llama3.1"
    agent = create_experiment_agent()

    report_json = ExperimentReport(
        run_id="run-1",
        status="success",
        summary="seasonal_naive wins",
        metrics={"mae": 8.9},
        recommendations=["deploy seasonal_naive"],
    ).model_dump_json()

    captured: dict[str, list[str]] = {}

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captured["output_tools"] = [tool.name for tool in info.output_tools]
        return ModelResponse(parts=[TextPart(content=report_json)])

    result = agent.run_sync(
        "Run an experiment",
        model=FunctionModel(respond),
        deps=AgentDeps(db=AsyncMock(), session_id="test-prompted-output"),
    )

    # PromptedOutput mode registers no structured-output tool...
    assert captured["output_tools"] == []
    # ...and the plain-text JSON reply is parsed into the structured type.
    assert isinstance(result.output, ExperimentReport)
    assert result.output.summary == "seasonal_naive wins"


def test_rag_assistant_agent_uses_prompted_output() -> None:
    """The RAG assistant agent runs in PromptedOutput mode (issue #173).

    Mirrors test_experiment_agent_uses_prompted_output: no ``final_result``
    output tool is registered, and a plain-text JSON reply is parsed into a
    valid ``RAGAnswer``.
    """
    settings = get_settings()
    settings.agent_default_model = "ollama:llama3.1"
    agent = create_rag_assistant_agent()

    answer_json = RAGAnswer(
        answer="The forecast API supports naive and seasonal_naive models.",
        confidence="high",
        sources=[{"source_path": "docs/api.md", "relevance": 0.9}],
    ).model_dump_json()

    captured: dict[str, list[str]] = {}

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captured["output_tools"] = [tool.name for tool in info.output_tools]
        return ModelResponse(parts=[TextPart(content=answer_json)])

    result = agent.run_sync(
        "What models does the forecast API support?",
        model=FunctionModel(respond),
        deps=AgentDeps(db=AsyncMock(), session_id="test-prompted-output"),
    )

    assert captured["output_tools"] == []
    assert isinstance(result.output, RAGAnswer)
    assert result.output.confidence == "high"
