"""PydanticAI agent definitions.

Provides:
- ExperimentAgent: Autonomous experiment orchestration
- RAGAssistantAgent: Evidence-grounded Q&A

Agents are lazily initialized to avoid requiring API keys at import time.
Use the getter functions to retrieve agent instances.
"""

from app.features.agents.agents.experiment import get_experiment_agent
from app.features.agents.agents.rag_assistant import get_rag_assistant_agent

__all__ = [
    "get_experiment_agent",
    "get_rag_assistant_agent",
]
