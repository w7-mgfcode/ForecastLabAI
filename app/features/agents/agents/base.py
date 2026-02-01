"""Base agent configuration and utilities.

Provides shared configuration and utility functions for all agents.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.core.config import get_settings

logger = structlog.get_logger()


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


def get_model_settings() -> dict[str, Any]:
    """Get model settings from configuration.

    Returns:
        Dictionary with temperature and max_tokens settings.
    """
    settings = get_settings()
    return {
        "temperature": settings.agent_temperature,
        "max_tokens": settings.agent_max_tokens,
    }


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
