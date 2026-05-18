"""Base agent configuration and utilities.

Provides shared configuration and utility functions for all agents.
"""

from __future__ import annotations

import os
from typing import Any

import structlog
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from app.core.config import get_settings

logger = structlog.get_logger()


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
    return OpenAIChatModel(model_name, provider=OllamaProvider(base_url=base_url))


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
TOOL USAGE:
- Use list_runs to find existing experiments
- Use run_backtest to evaluate model performance
- Use compare_runs to analyze differences between runs
- Use create_alias to deploy successful models (requires approval)
- Use archive_run to clean up old experiments (requires approval)
- Use retrieve_context to find documentation
"""

SAFETY_INSTRUCTIONS = """
SAFETY:
- Actions marked as requiring approval will be paused for human review
- Never bypass safety checks or approval requirements
- Log all significant decisions and their reasoning
"""
