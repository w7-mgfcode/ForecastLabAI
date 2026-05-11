"""RAG tools for agent interaction with the knowledge base.

Provides PydanticAI-compatible tool functions for:
- Retrieving context from the indexed knowledge base
- Listing indexed sources in the knowledge base
- Formatting citations for evidence-grounded responses

CRITICAL: Returns evidence with stable citations for grounded answers.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.rag.schemas import RetrieveRequest, RetrieveResponse
from app.features.rag.service import RAGService

logger = structlog.get_logger()


async def retrieve_context(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
    similarity_threshold: float = 0.7,
    source_type: str | None = None,
) -> dict[str, Any]:
    """Retrieve relevant context from the knowledge base.

    Use this tool to find documentation, API references, or other indexed
    content that can help answer user questions. Returns chunks with
    relevance scores and source citations.

    CRITICAL: Only use retrieved content as evidence. Do not fabricate
    information not found in the context.

    Args:
        db: Database session (injected via agent context).
        query: Search query text describing what to find.
        top_k: Maximum number of results to return (default 5, max 50).
        similarity_threshold: Minimum similarity score 0.0-1.0 (default 0.7).
        source_type: Filter by source type ('markdown', 'openapi').

    Returns:
        Dictionary with 'results' list containing chunks with citations.
        Each chunk has: chunk_id, source_id, source_path, content,
        relevance_score, and metadata.

    Example:
        # Find documentation about backtesting
        context = await retrieve_context(
            db,
            query='How to run a backtest with time-based CV?',
            top_k=5,
            similarity_threshold=0.7,
        )
    """
    logger.info(
        "agents.rag_tool.retrieve_context_called",
        query_length=len(query),
        top_k=top_k,
        similarity_threshold=similarity_threshold,
        source_type=source_type,
    )

    # Build filters if source_type provided
    filters: dict[str, Any] | None = None
    if source_type:
        filters = {"source_type": source_type}

    # Create retrieve request
    request = RetrieveRequest(
        query=query,
        top_k=min(top_k, 50),  # Cap at 50
        similarity_threshold=similarity_threshold,
        filters=filters,
    )

    # Perform retrieval
    service = RAGService()
    result: RetrieveResponse = await service.retrieve(db=db, request=request)

    # Fallback for terse/ambiguous queries:
    # If strict threshold returns nothing, retry once with lower threshold.
    if not result.results and similarity_threshold > 0.5:
        fallback_threshold = 0.5
        logger.info(
            "agents.rag_tool.retrieve_context_fallback",
            original_threshold=similarity_threshold,
            fallback_threshold=fallback_threshold,
            query_length=len(query),
        )
        fallback_request = RetrieveRequest(
            query=query,
            top_k=min(max(top_k, 8), 50),
            similarity_threshold=fallback_threshold,
            filters=filters,
        )
        result = await service.retrieve(db=db, request=fallback_request)

    logger.info(
        "agents.rag_tool.retrieve_context_completed",
        results_count=len(result.results),
        query_embedding_time_ms=result.query_embedding_time_ms,
        search_time_ms=result.search_time_ms,
        total_chunks_searched=result.total_chunks_searched,
    )

    return result.model_dump()


def format_citations(
    retrieval_result: dict[str, Any],
) -> list[dict[str, str]]:
    """Format retrieval results as stable citations.

    Use this tool to convert retrieval results into a standardized citation
    format for including in evidence-grounded responses.

    Args:
        retrieval_result: Result from retrieve_context.

    Returns:
        List of citation dictionaries with:
        - source_type: Type of source document
        - source_path: Path to the source
        - chunk_id: Unique chunk identifier
        - relevance: Relevance score
        - snippet: First 200 chars of content
    """
    results = _extract_result_items(retrieval_result)
    citations: list[dict[str, str]] = []

    for chunk in results:
        if not isinstance(chunk, dict):
            continue
        content = chunk.get("content", "")
        snippet = content[:200] + "..." if len(content) > 200 else content

        citations.append(
            {
                "source_type": chunk.get("source_type", "unknown"),
                "source_path": chunk.get("source_path", "unknown"),
                "chunk_id": chunk.get("chunk_id", "unknown"),
                "relevance": f"{chunk.get('relevance_score', 0):.2f}",
                "snippet": snippet,
            }
        )

    return citations


def has_sufficient_evidence(
    retrieval_result: dict[str, Any],
    min_results: int = 1,
    min_relevance: float = 0.7,
) -> bool:
    """Check if retrieval results provide sufficient evidence.

    Use this tool to determine if enough relevant context was found
    to provide an evidence-grounded answer. If not, respond with
    "insufficient evidence" rather than fabricating an answer.

    Args:
        retrieval_result: Result from retrieve_context.
        min_results: Minimum number of results required (default 1).
        min_relevance: Minimum average relevance score (default 0.7).

    Returns:
        True if sufficient evidence exists, False otherwise.
    """
    results = _extract_result_items(retrieval_result)

    if len(results) < min_results:
        return False

    # Keep only dict chunks to avoid model/tool argument shape issues.
    dict_results = [r for r in results if isinstance(r, dict)]
    if not dict_results:
        return False

    # Check strongest match relevance (more robust for short queries).
    if dict_results:
        max_relevance = max(r.get("relevance_score", 0) for r in dict_results)
        if max_relevance < min_relevance:
            return False

    return True


def _extract_result_items(retrieval_result: Any) -> list[Any]:
    """Normalize retrieval results into a list of result items.

    PydanticAI tool args can arrive as dicts, JSON strings, or already-parsed lists.
    This helper makes downstream logic resilient to those shapes.
    """
    # Direct dict shape: {"results": [...]}
    if isinstance(retrieval_result, dict):
        results = retrieval_result.get("results", [])
        return results if isinstance(results, list) else []

    # Direct list shape: [...]
    if isinstance(retrieval_result, list):
        return retrieval_result

    # JSON string shape
    if isinstance(retrieval_result, str):
        try:
            parsed = json.loads(retrieval_result)
        except json.JSONDecodeError:
            return []
        return _extract_result_items(parsed)

    return []


async def list_indexed_sources(
    db: AsyncSession,
) -> dict[str, Any]:
    """List indexed sources and chunk statistics from the knowledge base.

    Use this tool when users ask what content exists in the knowledge base.

    Args:
        db: Database session (injected via agent context).

    Returns:
        Dictionary containing sources, total_sources, and total_chunks.
    """
    logger.info("agents.rag_tool.list_sources_called")
    service = RAGService()
    response = await service.list_sources(db=db)
    logger.info(
        "agents.rag_tool.list_sources_completed",
        total_sources=response.total_sources,
        total_chunks=response.total_chunks,
    )
    return response.model_dump()
