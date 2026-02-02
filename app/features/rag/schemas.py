"""Pydantic schemas for RAG API contracts.

Schemas are designed to be:
- Validated for data integrity
- Compatible with SQLAlchemy models via from_attributes
- Evidence-grounded (citations include source metadata)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class IndexRequest(BaseModel):
    """Request to index a document into the knowledge base.

    Args:
        source_type: Type of document to index (markdown or openapi).
        source_path: Path to the document or identifier.
        content: Optional content override (if not reading from path).
        metadata: Custom metadata to attach to the source.
    """

    model_config = ConfigDict(extra="forbid")

    source_type: Literal["markdown", "openapi"] = Field(
        ..., description="Type of document to index"
    )
    source_path: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Path to the document or unique identifier",
    )
    content: str | None = Field(
        None, description="Optional content override (if not reading from path)"
    )
    metadata: dict[str, Any] | None = Field(
        None, description="Custom metadata to attach to the source"
    )


class IndexResponse(BaseModel):
    """Response from document indexing operation.

    Args:
        source_id: Unique identifier for the indexed source.
        source_path: Path of the indexed document.
        chunks_created: Number of chunks created from the document.
        tokens_processed: Total tokens processed across all chunks.
        duration_ms: Time taken to index the document.
        status: Indexing status (indexed, updated, unchanged).
    """

    model_config = ConfigDict(from_attributes=True)

    source_id: str
    source_path: str
    chunks_created: int
    tokens_processed: int
    duration_ms: float
    status: Literal["indexed", "updated", "unchanged"]


class RetrieveRequest(BaseModel):
    """Request for semantic search across indexed documents.

    Args:
        query: Search query text.
        top_k: Number of results to return (1-50).
        similarity_threshold: Minimum similarity score (0.0-1.0).
        filters: Metadata filters to apply.
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=2000, description="Search query text")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of results to return")
    similarity_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Minimum similarity score (default from settings)"
    )
    filters: dict[str, Any] | None = Field(
        None, description="Metadata filters (source_type, category, etc.)"
    )


class ChunkResult(BaseModel):
    """Single chunk in retrieval results with citation metadata.

    CRITICAL: Provides evidence-grounded context with stable citations.

    Args:
        chunk_id: Unique identifier for the chunk.
        source_id: Identifier of the parent source.
        source_path: Path of the source document.
        source_type: Type of source document.
        content: Chunk text content.
        relevance_score: Similarity score (0.0-1.0).
        metadata: Heading hierarchy, section path, etc.
    """

    model_config = ConfigDict(from_attributes=True)

    chunk_id: str
    source_id: str
    source_path: str
    source_type: str
    content: str
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    metadata: dict[str, Any] | None = None


class RetrieveResponse(BaseModel):
    """Response from semantic search operation.

    Args:
        results: List of matching chunks with relevance scores.
        query_embedding_time_ms: Time to generate query embedding.
        search_time_ms: Time to execute similarity search.
        total_chunks_searched: Total chunks in the search space.
    """

    results: list[ChunkResult]
    query_embedding_time_ms: float
    search_time_ms: float
    total_chunks_searched: int


class SourceResponse(BaseModel):
    """Details of an indexed document source.

    Args:
        source_id: Unique identifier for the source.
        source_type: Type of document (markdown, openapi).
        source_path: Path to the document.
        chunk_count: Number of chunks from this source.
        content_hash: SHA-256 hash for change detection.
        indexed_at: When the source was last indexed.
        metadata: Custom metadata attached to the source.
    """

    model_config = ConfigDict(from_attributes=True)

    source_id: str
    source_type: str
    source_path: str
    chunk_count: int
    content_hash: str
    indexed_at: datetime
    metadata: dict[str, Any] | None = None


class SourceListResponse(BaseModel):
    """List of all indexed sources with summary statistics.

    Args:
        sources: List of indexed sources.
        total_sources: Total number of sources.
        total_chunks: Total number of chunks across all sources.
    """

    sources: list[SourceResponse]
    total_sources: int
    total_chunks: int


class DeleteResponse(BaseModel):
    """Response from source deletion operation.

    Args:
        source_id: Identifier of the deleted source.
        chunks_deleted: Number of chunks that were deleted.
        status: Always "deleted".
    """

    source_id: str
    chunks_deleted: int
    status: Literal["deleted"]
