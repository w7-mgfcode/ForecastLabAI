"""Unit tests for agent base helpers (Ollama-aware model factory)."""

from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel

from app.core.config import get_settings
from app.features.agents.agents.base import build_agent_model, validate_api_key_for_model
from app.features.agents.agents.experiment import create_experiment_agent
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
