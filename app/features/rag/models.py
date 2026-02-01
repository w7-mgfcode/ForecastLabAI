"""RAG knowledge base ORM models.

This module defines:
- DocumentSource: Registry of indexed document sources
- DocumentChunk: Indexed document chunks with embeddings

CRITICAL: Uses PostgreSQL pgvector for embedding storage and similarity search.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.models import TimestampMixin

if TYPE_CHECKING:
    pass


class DocumentSource(TimestampMixin, Base):
    """Registered document source for indexing.

    CRITICAL: Tracks indexed sources with content hash for idempotent re-indexing.

    Attributes:
        id: Primary key.
        source_id: Unique external identifier (UUID hex, 32 chars).
        source_type: Type of source (markdown, openapi, run_report).
        source_path: Path or identifier for the source.
        content_hash: SHA-256 hash for change detection.
        metadata_: Custom metadata as JSONB.
        indexed_at: When the source was last indexed.
        chunks: Related document chunks.
    """

    __tablename__ = "document_source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationship to chunks
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("source_type", "source_path", name="uq_source_type_path"),)


class DocumentChunk(TimestampMixin, Base):
    """Indexed document chunk with embedding.

    CRITICAL: Stores vector embeddings for semantic similarity search.

    Attributes:
        id: Primary key.
        chunk_id: Unique external identifier (UUID hex, 32 chars).
        source_id: Foreign key to parent source.
        chunk_index: Position within the source document.
        content: Chunk text content.
        embedding: Vector embedding (1536 dimensions for text-embedding-3-small).
        token_count: Number of tokens in the chunk.
        metadata_: Heading hierarchy, section path, etc.
        source: Related document source.
    """

    __tablename__ = "document_chunk"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("document_source.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Vector column for embeddings - dimension configurable via settings
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationship to source
    source: Mapped[DocumentSource] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("source_id", "chunk_index", name="uq_source_chunk_index"),
        # HNSW index for cosine similarity search
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # GIN index for metadata filtering
        Index("ix_chunk_metadata_gin", "metadata", postgresql_using="gin"),
    )
