"""Base agent configuration and utilities.

Provides shared configuration and utility functions for all agents.
"""

from __future__ import annotations

import functools
import inspect
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any, cast

import httpx
import structlog
from pydantic_ai import ModelRetry
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from app.core.config import get_settings

logger = structlog.get_logger()


def recoverable[**P, ToolReturnT](
    func: Callable[P, Awaitable[ToolReturnT]],
) -> Callable[P, Awaitable[ToolReturnT]]:
    """Wrap an async agent tool so an expected ``ValueError`` becomes a ``ModelRetry``.

    Input-driven failures (no data for a store, an unknown run id, a malformed
    date) should let the model correct its arguments on the next turn instead of
    crashing the whole run (issue #176). Other exception types still propagate
    as genuine errors.

    Args:
        func: The async tool function to wrap.

    Returns:
        The wrapped tool function, signature preserved for PydanticAI schema
        extraction.

    Raises:
        TypeError: If ``func`` is not a coroutine function. The wrapper
            ``await``s ``func``, so wrapping a sync callable would only fail
            (with an opaque "not awaitable" error) when the tool is first
            called — this guard surfaces the mistake at decoration time.
    """
    if not inspect.iscoroutinefunction(func):
        raise TypeError(
            f"@recoverable wraps async tool functions only; "
            f"{getattr(func, '__qualname__', func)!r} is not a coroutine function."
        )

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> ToolReturnT:
        try:
            return await func(*args, **kwargs)
        except ValueError as exc:
            raise ModelRetry(str(exc)) from exc

    return wrapper


def _coerce_null_message_content(body: bytes) -> bytes | None:
    """Coerce ``messages[*].content: null`` -> ``""`` in a chat-request body.

    Ollama's OpenAI-compatible ``/v1/chat/completions`` rejects any message
    whose ``content`` is JSON ``null`` and which carries no ``tool_calls`` with
    ``400 invalid message content type: <nil>`` — stricter than the real OpenAI
    API, which tolerates it. A weak local model can emit a degenerate empty
    assistant turn (no text, no tool call); PydanticAI serialises it as
    ``content: null`` and then *replays* that message on its validation-retry,
    so every retry 400s and the whole run dies with a ``FallbackExceptionGroup``.
    Coercing ``null`` -> ``""`` keeps the message OpenAI-spec-valid and lets the
    retry loop proceed.

    Args:
        body: The raw outgoing request body bytes.

    Returns:
        Re-serialised body bytes when a null ``content`` was rewritten, or
        ``None`` when nothing changed (the common case) so the caller can
        forward the original request untouched.
    """
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    payload = cast("dict[str, Any]", parsed)
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return None
    message_list: list[Any] = messages
    changed = False
    for message in message_list:
        if isinstance(message, dict) and "content" in message and message["content"] is None:
            message["content"] = ""
            changed = True
    if not changed:
        return None
    return json.dumps(payload).encode("utf-8")


class _OllamaNullContentTransport(httpx.AsyncHTTPTransport):
    """httpx transport that null-content-sanitises outgoing Ollama requests.

    See :func:`_coerce_null_message_content` for the Ollama-compat defect this
    works around. Applied to the ``OllamaProvider``'s HTTP client so the fix
    covers both the streaming and non-streaming agent paths.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        sanitized = _coerce_null_message_content(request.content)
        if sanitized is not None:
            headers = dict(request.headers)
            headers.pop("content-length", None)  # httpx recomputes from the new body
            request = httpx.Request(
                request.method,
                request.url,
                headers=headers,
                content=sanitized,
                extensions=request.extensions,
            )
        return await super().handle_async_request(request)


def build_agent_model(identifier: str) -> str | Model:
    """Build the PydanticAI ``model`` argument for an agent identifier.

    Cloud providers accept a plain ``provider:model-name`` string. Ollama does
    not — it needs an :class:`OpenAIChatModel` bound to an :class:`OllamaProvider`
    pointed at the host's OpenAI-compatible ``/v1`` endpoint.

    Args:
        identifier: Model identifier (e.g. ``anthropic:claude-sonnet-4-5``,
            ``ollama:llama3.1``).

    Returns:
        The identifier string unchanged for cloud providers, or a configured
        :class:`OpenAIChatModel` for the ``ollama`` provider.
    """
    provider = identifier.split(":", 1)[0]
    if provider != "ollama":
        return identifier

    settings = get_settings()
    model_name = identifier.split(":", 1)[1]
    # CRITICAL: Ollama's OpenAI-compatible base ends in /v1.
    base_url = settings.ollama_base_url.rstrip("/") + "/v1"
    # The null-content sanitiser lives on the HTTP client (see
    # _OllamaNullContentTransport). A generous read timeout is required because
    # local generation on an 8B model routinely exceeds httpx's 5s default.
    http_client = httpx.AsyncClient(
        transport=_OllamaNullContentTransport(),
        timeout=httpx.Timeout(600.0, connect=10.0),
    )
    return OpenAIChatModel(
        model_name,
        provider=OllamaProvider(base_url=base_url, http_client=http_client),
    )


def reset_agent_caches() -> None:
    """Drop the cached agent singletons so the next build picks up new config.

    Called by the config service after a successful model/key change. Imports
    are local to avoid an import cycle (the agent modules import from here).
    """
    from app.features.agents.agents.experiment import reset_experiment_agent
    from app.features.agents.agents.rag_assistant import reset_rag_assistant_agent

    reset_experiment_agent()
    reset_rag_assistant_agent()


def get_model_identifier() -> str:
    """Get the configured model identifier for agents.

    Returns:
        Model identifier string (e.g., 'anthropic:claude-sonnet-4-5').
    """
    settings = get_settings()
    return settings.agent_default_model


def get_fallback_model() -> str:
    """Get the fallback model identifier.

    Returns:
        Fallback model identifier string.
    """
    settings = get_settings()
    return settings.agent_fallback_model


def build_agent_model_with_fallback() -> Model | str:
    """Build the PydanticAI ``model`` argument, wrapping primary + fallback.

    When the primary model raises a provider error — HTTP 5xx, rate limit,
    timeout, i.e. any ``pydantic_ai.exceptions.ModelAPIError`` — PydanticAI's
    :class:`FallbackModel` transparently retries the request against
    ``agent_fallback_model``. This keeps an agent run alive through a transient
    provider outage (e.g. a Gemini ``503 UNAVAILABLE``) instead of surfacing a
    hard error. ``FallbackModel``'s default ``fallback_on=(ModelAPIError,)``
    already covers that case.

    The primary model is returned alone (no fallback wrapper) when:

    - no fallback is configured, or it equals the primary identifier; or
    - the fallback provider has no API key — wrapping it would only move the
      failure, so the agent runs primary-only and logs a warning.

    Returns:
        A :class:`FallbackModel` (primary then fallback) when a usable fallback
        is configured, otherwise the primary model argument from
        :func:`build_agent_model`.

    Raises:
        ValueError: If the primary provider's API key is not configured
            (fail-fast — an agent with no usable primary cannot run).
    """
    primary_id = get_model_identifier()
    validate_api_key_for_model(primary_id)  # fail-fast on the primary
    primary = build_agent_model(primary_id)

    fallback_id = get_fallback_model()
    if not fallback_id or fallback_id == primary_id:
        return primary

    try:
        validate_api_key_for_model(fallback_id)
    except ValueError:
        logger.warning(
            "agents.fallback_disabled",
            reason="missing_api_key",
            primary=primary_id,
            fallback=fallback_id,
        )
        return primary

    fallback = build_agent_model(fallback_id)
    logger.info("agents.fallback_enabled", primary=primary_id, fallback=fallback_id)
    return FallbackModel(primary, fallback)


def get_agent_retries() -> int:
    """Get the configured retry budget for agent tool calls and output validation.

    PydanticAI defaults to 1 retry; without this the configured
    ``agent_retry_attempts`` setting is silently ignored.

    Returns:
        Number of retry attempts for tool calls and structured-output validation.
    """
    settings = get_settings()
    return settings.agent_retry_attempts


def get_model_settings() -> dict[str, Any]:
    """Get model settings from configuration for PydanticAI Agent.

    Returns:
        Dictionary with model_settings wrapped for Agent constructor.
    """
    settings = get_settings()
    inner_settings: dict[str, Any] = {
        "temperature": settings.agent_temperature,
        "max_tokens": settings.agent_max_tokens,
    }

    # Add thinking budget if configured (Gemini 2.5+ extended reasoning)
    if settings.agent_thinking_budget:
        inner_settings["thinking"] = {"budget": settings.agent_thinking_budget}

    return {"model_settings": inner_settings}


def validate_api_key_for_model(model: str) -> None:
    """Validate that required API key is configured for model.

    Also exports the API key to environment for PydanticAI compatibility.

    Args:
        model: Model identifier (provider:model-name).

    Raises:
        ValueError: If required API key is not configured.
    """
    settings = get_settings()
    provider = model.split(":")[0]

    if provider == "ollama":
        # Local Ollama runs without an API key — nothing to validate or export.
        logger.debug("agents.api_key_validated", provider=provider, model=model)
        return

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "Anthropic API key not configured. Set ANTHROPIC_API_KEY environment variable."
            )
        # Only set env var if not already present to avoid repeated mutations
        if "ANTHROPIC_API_KEY" not in os.environ:
            os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
    elif provider == "openai":
        if not settings.openai_api_key:
            raise ValueError(
                "OpenAI API key not configured. Set OPENAI_API_KEY environment variable."
            )
        if "OPENAI_API_KEY" not in os.environ:
            os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    elif provider in ["google-gla", "google-vertex"]:
        if not settings.google_api_key:
            raise ValueError(
                "Google API key not configured. Set GOOGLE_API_KEY environment variable."
            )
        if "GOOGLE_API_KEY" not in os.environ:
            os.environ["GOOGLE_API_KEY"] = settings.google_api_key

    logger.debug(
        "agents.api_key_validated",
        provider=provider,
        model=model,
    )


def requires_approval(action_name: str) -> bool:
    """Check if an action requires human approval.

    Args:
        action_name: Name of the action to check.

    Returns:
        True if the action requires approval.
    """
    settings = get_settings()
    return action_name in settings.agent_require_approval


# System prompt components that can be reused across agents
SYSTEM_PROMPT_HEADER = """You are an AI assistant for ForecastLabAI, a retail demand forecasting system.
You help users run experiments, analyze results, and manage model deployments.

CRITICAL INSTRUCTIONS:
- Only use information from tool calls or retrieved context
- Never fabricate metrics, run IDs, or other data
- If asked about something not in your context, say so clearly
- Explain your reasoning before taking actions
"""

TOOL_USAGE_INSTRUCTIONS = """
TOOL USAGE (call tools by these EXACT names):
- Use tool_list_runs to find existing experiments
- Use tool_run_backtest to evaluate model performance
- Use tool_compare_backtest_results to compare two backtest results
- Use tool_compare_runs to analyze differences between registered runs
- Use tool_create_alias to deploy successful models (requires approval)
- Use tool_archive_run to clean up old experiments (requires approval)
- Use tool_propose_scenario to draft a candidate what-if scenario (read-only)
- Use tool_save_scenario to persist an approved scenario plan (requires approval)
"""

SAFETY_INSTRUCTIONS = """
SAFETY:
- Actions marked as requiring approval will be paused for human review
- Never bypass safety checks or approval requirements
- Log all significant decisions and their reasoning
"""

# Generalized read-only intent guard. Embedded in the experiment-agent prompt to
# stop a read-only question (list/rank/summarize/compare/report) from derailing
# into a scenario / write / experiment tool — especially on an output-format
# validation retry, where a weak local model tends to start a brand-new action
# instead of just reformatting the data it already fetched (issue #347). Every
# `tool_*` name referenced here is registered on the experiment agent, so the
# `test_prompts_only_reference_registered_tool_names` invariant still holds.
READ_ONLY_INTENT_GUARD = """
READ-ONLY INTENT GUARD (apply this before every turn):
Many requests are READ-ONLY — the user wants you to look something up and report
it, not to change anything. Treat a request as READ-ONLY when it asks you to list,
show, rank, summarize, compare, or report. Examples that are ALWAYS read-only
unless the user explicitly asks to change something:
- listing or ranking stores or products (e.g. "top products")
- sales, revenue, or units-sold summaries
- forecast summaries, or which products have the highest forecasted demand
- model runs and metric comparisons, including WAPE, MAE, or RMSE
- registry aliases and deployment status
- backtest metrics
- RAG / document / knowledge questions

For a READ-ONLY request you MUST:
- Use ONLY read-only tools: tool_list_runs, tool_get_run, tool_compare_runs,
  tool_compare_backtest_results.
- NEVER call tool_propose_scenario, tool_save_scenario, tool_create_alias,
  tool_archive_run, or tool_run_backtest. Those create, save, promote, archive,
  run, or plan something — they are NOT allowed for a read-only question.
- Call a mutating / planning / experiment tool ONLY when the user EXPLICITLY asks
  to create, save, promote, archive, run a backtest, or run an experiment.
- Answer directly in the ExperimentReport `summary` field, grounded in tool output.

FINISH IN ONE PASS — do not loop:
- Call each read-only tool AT MOST ONCE per question.
- The MOMENT a read tool returns, STOP calling tools and write your
  ExperimentReport `summary` from what it returned — you already have the answer.
- NEVER call a tool again that has already returned. Re-running the same tool
  (e.g. tool_list_runs twice) is the most common failure: it burns the retry
  budget until the run is killed. Use the data you already received.
- If a read tool returns an EMPTY result, say so in the `summary` (e.g. "No model
  runs found.") — do NOT retry the tool hoping for different data.

OUTPUT-FORMAT RETRIES:
- If your previous reply failed schema validation (e.g. "summary: Field required"),
  DO NOT call any new tool. Only reformat the data you already obtained into a
  valid ExperimentReport with a concise `summary`. A validation retry is a
  formatting fix, never a reason to start a new action.

WHEN A TOOL IS MISSING OR THE REQUEST IS AMBIGUOUS:
- If a ranking is ambiguous (e.g. "top products"), ask a clarifying question such
  as: "Top by revenue, units sold, forecasted demand, or model error?" — do not guess.
- If no read-only tool exists for the requested metric, say plainly that this agent
  does not have a tool for that metric. Do NOT invent data.
- NEVER invent or guess a store_id, product_id, or run_id. Use only IDs returned by
  a tool or explicitly supplied by the user.
"""
