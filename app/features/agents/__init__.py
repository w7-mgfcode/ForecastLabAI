"""Agentic layer for intelligent experiment orchestration.

This module provides:
- PydanticAI agents for experiment orchestration and RAG assistance
- Tool wrappers for registry, backtesting, forecasting, and RAG
- Session management with human-in-the-loop approval
- WebSocket streaming for real-time agent responses
"""

# Import models to register with SQLAlchemy metadata
from app.features.agents import models  # noqa: F401

__all__ = ["models"]
