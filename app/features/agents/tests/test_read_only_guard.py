"""Deterministic tests for the experiment-agent read-only intent guard (#347).

The guard stops a read-only question ("list the runs and tell me the lowest
WAPE", "top products", "current deployment alias") from derailing into a
scenario / write / experiment tool — especially on an output-format validation
retry, where a weak local model tends to start a brand-new action instead of
reformatting the data it already fetched.

These tests are deterministic and require **no live model call**: they assert
that the guard text exists, names the right tools, and governs each named
read-only intent, and that the guard is actually delivered to the model in the
system prompt.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.core.config import get_settings
from app.features.agents.agents.base import READ_ONLY_INTENT_GUARD
from app.features.agents.agents.experiment import (
    EXPERIMENT_SYSTEM_PROMPT,
    create_experiment_agent,
)
from app.features.agents.deps import AgentDeps

# Tools that must NEVER be called for a read-only intent.
PROHIBITED_TOOLS = (
    "tool_propose_scenario",
    "tool_save_scenario",
    "tool_create_alias",
    "tool_archive_run",
    "tool_run_backtest",
)

# Read-only tools the guard steers the model toward.
ALLOWED_READ_TOOLS = (
    "tool_list_runs",
    "tool_get_run",
    "tool_compare_runs",
)


@pytest.fixture(autouse=True)
def _reset_settings() -> Iterator[None]:
    """Reset the settings cache so model mutations do not leak across tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_guard_is_embedded_in_experiment_prompt() -> None:
    """The experiment system prompt embeds the read-only intent guard."""
    assert READ_ONLY_INTENT_GUARD.strip() in EXPERIMENT_SYSTEM_PROMPT
    assert "READ-ONLY INTENT GUARD" in EXPERIMENT_SYSTEM_PROMPT


@pytest.mark.parametrize("tool_name", PROHIBITED_TOOLS)
def test_guard_names_prohibited_tools(tool_name: str) -> None:
    """The guard explicitly forbids each scenario/write/experiment tool."""
    assert tool_name in READ_ONLY_INTENT_GUARD
    # And the prohibition is unambiguous.
    assert "NEVER call" in READ_ONLY_INTENT_GUARD


@pytest.mark.parametrize("tool_name", ALLOWED_READ_TOOLS)
def test_guard_names_allowed_read_tools(tool_name: str) -> None:
    """The guard points the model at the read-only tools to use instead."""
    assert tool_name in READ_ONLY_INTENT_GUARD
    assert "Use ONLY read-only tools" in READ_ONLY_INTENT_GUARD


def test_guard_forbids_new_tools_on_validation_retry() -> None:
    """On an output-format retry the model must reformat, not call new tools."""
    guard = READ_ONLY_INTENT_GUARD
    assert "OUTPUT-FORMAT RETRIES" in guard
    assert "DO NOT call any new tool" in guard
    assert "reformat" in guard
    # The exact validation-error string that triggered the original derail.
    assert "summary: Field required" in guard


def test_guard_requires_clarification_for_ambiguous_top_products() -> None:
    """An ambiguous "top products" ranking gets a clarifying question, not a guess."""
    guard = READ_ONLY_INTENT_GUARD
    assert "top products" in guard
    assert "Top by revenue, units sold, forecasted demand, or model error?" in guard


def test_guard_prohibits_invented_ids() -> None:
    """The guard forbids inventing store_id / product_id / run_id values."""
    guard = READ_ONLY_INTENT_GUARD
    assert "NEVER invent" in guard
    for token in ("store_id", "product_id", "run_id"):
        assert token in guard


def test_guard_states_limitation_when_no_tool_exists() -> None:
    """The guard tells the model to state a missing-tool limitation, not fabricate."""
    guard = READ_ONLY_INTENT_GUARD
    assert "does not have a tool for that metric" in guard
    assert "Do NOT invent data" in guard


# Each example read-only prompt and the guard substring that proves the guard
# governs that intent (so the named query class can never silently lose
# coverage). Deterministic — no model is invoked.
@pytest.mark.parametrize(
    ("prompt", "covered_intent"),
    [
        (
            "List the most recent model runs and tell me which has the lowest WAPE.",
            "WAPE",
        ),
        ("List the top products.", "top products"),
        (
            "Which products have the highest forecasted demand?",
            "highest forecasted demand",
        ),
        ("Show the current deployment alias.", "registry aliases and deployment status"),
        ("Summarize total revenue and units sold.", "units-sold summaries"),
        ("Show the backtest metrics for this grain.", "backtest metrics"),
    ],
)
def test_read_only_intents_are_covered_by_guard(prompt: str, covered_intent: str) -> None:
    """Every named read-only intent is enumerated in the guard's read-only list.

    This is the routing contract: each of these prompts is a read-only request,
    and the guard's read-only example list names its intent — so the model is
    told to answer it with read tools only and never with a scenario/write tool.
    """
    assert covered_intent in READ_ONLY_INTENT_GUARD


def test_guard_is_delivered_in_system_prompt_to_model() -> None:
    """The guard actually reaches the model in the delivered system prompt.

    Builds the real experiment agent against a stub FunctionModel (no live
    call), captures the system prompt the framework sends, and asserts the guard
    is present. Regression for #347 — a guard that never reaches the model is
    worthless.
    """
    settings = get_settings()
    settings.agent_default_model = "ollama:llama3.1"
    agent = create_experiment_agent()

    captured: dict[str, str] = {}

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        for message in messages:
            for part in getattr(message, "parts", []):
                if getattr(part, "part_kind", None) == "system-prompt":
                    captured["system_prompt"] = part.content
        # End the run with a PromptedOutput-parseable text reply.
        return ModelResponse(parts=[TextPart(content='{"summary": "noop"}')])

    agent.run_sync(
        "List the most recent model runs and tell me which has the lowest WAPE.",
        model=FunctionModel(respond),
        deps=AgentDeps(db=AsyncMock(), session_id="test-read-only-guard"),
    )

    system_prompt = captured.get("system_prompt", "")
    assert "READ-ONLY INTENT GUARD" in system_prompt
    assert "DO NOT call any new tool" in system_prompt
    for tool_name in PROHIBITED_TOOLS:
        assert tool_name in system_prompt
