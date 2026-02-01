"""RAG Assistant Agent for evidence-grounded Q&A.

This agent:
- Retrieves relevant context from the knowledge base
- Provides answers grounded in retrieved evidence
- Includes citations for all claims
- Clearly states when information is not available
"""

from __future__ import annotations

from typing import Any

import structlog
from pydantic_ai import Agent, RunContext

from app.features.agents.agents.base import (
    SAFETY_INSTRUCTIONS,
    SYSTEM_PROMPT_HEADER,
    get_model_identifier,
    get_model_settings,
)
from app.features.agents.deps import AgentDeps
from app.features.agents.schemas import RAGAnswer
from app.features.agents.tools.rag_tools import (
    format_citations,
    has_sufficient_evidence,
    retrieve_context,
)

logger = structlog.get_logger()

# RAG-specific system prompt
RAG_SYSTEM_PROMPT = f"""{SYSTEM_PROMPT_HEADER}

You are the RAG Assistant Agent. Your role is to:
1. Understand the user's question
2. Retrieve relevant context from the knowledge base
3. Formulate an answer ONLY based on retrieved evidence
4. Include citations for all claims
5. Clearly state when information is not found

CRITICAL EVIDENCE RULES:
- NEVER make claims not supported by retrieved context
- If context is insufficient, say "I don't have enough information"
- Always cite the source_path and chunk_id for claims
- Prefer multiple sources over single source when available
- State confidence level based on evidence quality

RESPONSE FORMAT:
- Start with a direct answer to the question
- Support with specific evidence from context
- Include citations in [source_path:chunk_id] format
- End with confidence assessment

{SAFETY_INSTRUCTIONS}
"""

# Lazily created agent instance
_rag_assistant_agent: Agent[AgentDeps, RAGAnswer] | None = None


def create_rag_assistant_agent() -> Agent[AgentDeps, RAGAnswer]:
    """Create and configure the RAG assistant agent with all tools.

    Returns:
        Configured Agent instance with tools registered.
    """
    agent: Agent[AgentDeps, RAGAnswer] = Agent(
        model=get_model_identifier(),
        deps_type=AgentDeps,
        output_type=RAGAnswer,
        system_prompt=RAG_SYSTEM_PROMPT,
        **get_model_settings(),
    )

    # Register tools with the agent
    @agent.tool
    async def tool_retrieve_context(
        ctx: RunContext[AgentDeps],
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.7,
        source_type: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve relevant context from the knowledge base.

        Use this to find documentation, API references, or other indexed content.

        CRITICAL: Only use retrieved content as evidence. Do not fabricate
        information not found in the context.

        Args:
            query: Search query describing what to find.
            top_k: Maximum results to return (default 5).
            similarity_threshold: Minimum similarity score (default 0.7).
            source_type: Filter by source type ('markdown', 'openapi').

        Returns:
            Dictionary with 'results' list containing chunks with citations.
        """
        ctx.deps.increment_tool_calls()
        logger.info(
            "agents.rag_assistant.tool_retrieve_context",
            session_id=ctx.deps.session_id,
            query_length=len(query),
            top_k=top_k,
        )
        return await retrieve_context(
            db=ctx.deps.db,
            query=query,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            source_type=source_type,
        )

    @agent.tool_plain
    def tool_format_citations(
        retrieval_result: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Format retrieval results as stable citations.

        Use this to convert retrieval results into citation format.

        Args:
            retrieval_result: Result from retrieve_context.

        Returns:
            List of formatted citations.
        """
        return format_citations(retrieval_result)

    @agent.tool_plain
    def tool_check_evidence(
        retrieval_result: dict[str, Any],
        min_results: int = 1,
        min_relevance: float = 0.7,
    ) -> bool:
        """Check if retrieval results provide sufficient evidence.

        Use this to determine if enough context was found to answer.
        If False, respond with "insufficient evidence" message.

        Args:
            retrieval_result: Result from retrieve_context.
            min_results: Minimum number of results required.
            min_relevance: Minimum average relevance score.

        Returns:
            True if sufficient evidence exists.
        """
        return has_sufficient_evidence(
            retrieval_result,
            min_results=min_results,
            min_relevance=min_relevance,
        )

    return agent


def get_rag_assistant_agent() -> Agent[AgentDeps, RAGAnswer]:
    """Get or create the RAG assistant agent singleton.

    Returns:
        Configured RAG assistant agent instance.
    """
    global _rag_assistant_agent
    if _rag_assistant_agent is None:
        _rag_assistant_agent = create_rag_assistant_agent()
    return _rag_assistant_agent
