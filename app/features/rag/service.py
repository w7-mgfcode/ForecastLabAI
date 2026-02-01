"""RAG service for document indexing and semantic retrieval.

Orchestrates:
- Document indexing with chunking and embedding
- Semantic retrieval with similarity search
- Source management (list, delete)
- Idempotent re-indexing via content hash comparison

CRITICAL: Uses pgvector cosine_distance for similarity search.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.rag.chunkers import ChunkData, get_chunker
from app.features.rag.embeddings import EmbeddingProvider, get_embedding_service
from app.features.rag.models import DocumentChunk, DocumentSource
from app.features.rag.schemas import (
    ChunkResult,
    DeleteResponse,
    IndexRequest,
    IndexResponse,
    RetrieveRequest,
    RetrieveResponse,
    SourceListResponse,
    SourceResponse,
)

logger = structlog.get_logger()


class SourceNotFoundError(ValueError):
    """Source not found in the knowledge base."""

    pass


class RAGService:
    """Service for RAG knowledge base operations.

    Provides:
    - Document indexing with automatic chunking and embedding
    - Semantic retrieval with configurable similarity threshold
    - Source management and statistics
    - Idempotent re-indexing based on content hash

    CRITICAL: Uses cosine_distance for similarity (not l2_distance).
    """

    def __init__(
        self,
        embedding_service: EmbeddingProvider | None = None,
    ) -> None:
        """Initialize RAG service.

        Args:
            embedding_service: Optional embedding provider override (for testing).
        """
        self.settings = get_settings()
        self._embedding_service = embedding_service or get_embedding_service()

    def _compute_content_hash(self, content: str) -> str:
        """Compute SHA-256 hash of content for change detection.

        Args:
            content: Document content.

        Returns:
            64-character hex string hash.
        """
        return hashlib.sha256(content.encode()).hexdigest()

    def _read_content_from_path(self, source_path: str) -> str:
        """Read content from a file path.

        Args:
            source_path: Path to the file.

        Returns:
            File content.

        Raises:
            FileNotFoundError: If file doesn't exist.
        """
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        return path.read_text(encoding="utf-8")

    async def index_document(
        self,
        db: AsyncSession,
        request: IndexRequest,
    ) -> IndexResponse:
        """Index a document into the knowledge base.

        Handles:
        - Content reading (from path or request)
        - Content hash comparison for idempotent updates
        - Chunking based on source type
        - Embedding generation for all chunks
        - Database upsert (source + chunks)

        Args:
            db: Database session.
            request: Index request with source info.

        Returns:
            Indexing result with statistics.
        """
        start_time = time.time()

        logger.info(
            "rag.index_document_started",
            source_type=request.source_type,
            source_path=request.source_path,
        )

        # Get content (from request or file)
        if request.content:
            content = request.content
        else:
            content = self._read_content_from_path(request.source_path)

        # Compute content hash
        content_hash = self._compute_content_hash(content)

        # Check if source already exists
        existing_source = await self._find_source_by_path(
            db, request.source_type, request.source_path
        )

        if existing_source and existing_source.content_hash == content_hash:
            # Content unchanged - skip re-indexing
            chunk_count = await self._get_chunk_count(db, existing_source.id)
            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                "rag.index_document_unchanged",
                source_id=existing_source.source_id,
                source_path=request.source_path,
            )

            return IndexResponse(
                source_id=existing_source.source_id,
                source_path=request.source_path,
                chunks_created=chunk_count,
                tokens_processed=0,
                duration_ms=duration_ms,
                status="unchanged",
            )

        # Chunk the content
        chunker = get_chunker(request.source_type)
        chunks = chunker.chunk(content)

        if not chunks:
            logger.warning(
                "rag.index_document_no_chunks",
                source_path=request.source_path,
            )
            chunks = []

        # Generate embeddings for all chunks
        chunk_texts = [chunk.content for chunk in chunks]
        embeddings: list[list[float]] = []

        if chunk_texts:
            embeddings = await self._embedding_service.embed_texts(chunk_texts)

        # Calculate total tokens
        total_tokens = sum(chunk.token_count for chunk in chunks)

        # Upsert source and chunks
        source_id = existing_source.source_id if existing_source else uuid.uuid4().hex
        status: Literal["indexed", "updated", "unchanged"] = (
            "updated" if existing_source else "indexed"
        )

        await self._upsert_source_and_chunks(
            db=db,
            source_id=source_id,
            source_type=request.source_type,
            source_path=request.source_path,
            content_hash=content_hash,
            metadata=request.metadata,
            chunks=chunks,
            embeddings=embeddings,
            existing_source=existing_source,
        )

        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "rag.index_document_completed",
            source_id=source_id,
            source_path=request.source_path,
            chunks_created=len(chunks),
            tokens_processed=total_tokens,
            duration_ms=duration_ms,
            status=status,
        )

        return IndexResponse(
            source_id=source_id,
            source_path=request.source_path,
            chunks_created=len(chunks),
            tokens_processed=total_tokens,
            duration_ms=duration_ms,
            status=status,
        )

    async def retrieve(
        self,
        db: AsyncSession,
        request: RetrieveRequest,
    ) -> RetrieveResponse:
        """Perform semantic search across indexed documents.

        Uses pgvector cosine_distance for similarity ranking:
        - relevance_score = 1 - cosine_distance (normalized to 0-1)
        - Filters by similarity threshold
        - Supports metadata filtering

        Args:
            db: Database session.
            request: Retrieval request with query and filters.

        Returns:
            Search results with relevance scores.
        """
        embed_start = time.time()

        logger.info(
            "rag.retrieve_started",
            query_length=len(request.query),
            top_k=request.top_k,
            threshold=request.similarity_threshold,
        )

        # Generate query embedding
        query_embedding = await self._embedding_service.embed_query(request.query)
        embed_time_ms = (time.time() - embed_start) * 1000

        search_start = time.time()

        # Get total chunk count for statistics
        total_chunks = await self._get_total_chunk_count(db)

        # Build similarity search query
        # CRITICAL: cosine_distance returns values 0-2, so relevance = 1 - distance/2
        # But for cosine similarity on normalized vectors, distance is 0-1
        results = await self._search_similar_chunks(
            db=db,
            query_embedding=query_embedding,
            top_k=request.top_k,
            threshold=request.similarity_threshold,
            filters=request.filters,
        )

        search_time_ms = (time.time() - search_start) * 1000

        logger.info(
            "rag.retrieve_completed",
            results_count=len(results),
            query_embedding_time_ms=embed_time_ms,
            search_time_ms=search_time_ms,
        )

        return RetrieveResponse(
            results=results,
            query_embedding_time_ms=embed_time_ms,
            search_time_ms=search_time_ms,
            total_chunks_searched=total_chunks,
        )

    async def list_sources(
        self,
        db: AsyncSession,
    ) -> SourceListResponse:
        """List all indexed sources with statistics.

        Args:
            db: Database session.

        Returns:
            List of sources with chunk counts.
        """
        # Get sources with chunk counts
        stmt = (
            select(
                DocumentSource,
                func.count(DocumentChunk.id).label("chunk_count"),
            )
            .outerjoin(DocumentChunk, DocumentSource.id == DocumentChunk.source_id)
            .group_by(DocumentSource.id)
            .order_by(DocumentSource.indexed_at.desc())
        )

        result = await db.execute(stmt)
        rows = result.all()

        sources: list[SourceResponse] = []
        total_chunks = 0

        for source, chunk_count in rows:
            sources.append(
                SourceResponse(
                    source_id=source.source_id,
                    source_type=source.source_type,
                    source_path=source.source_path,
                    chunk_count=chunk_count,
                    content_hash=source.content_hash,
                    indexed_at=source.indexed_at,
                    metadata=source.metadata_,
                )
            )
            total_chunks += chunk_count

        return SourceListResponse(
            sources=sources,
            total_sources=len(sources),
            total_chunks=total_chunks,
        )

    async def delete_source(
        self,
        db: AsyncSession,
        source_id: str,
    ) -> DeleteResponse:
        """Delete a source and all its chunks.

        Args:
            db: Database session.
            source_id: Source identifier.

        Returns:
            Deletion result with chunk count.

        Raises:
            SourceNotFoundError: If source not found.
        """
        logger.info("rag.delete_source_started", source_id=source_id)

        # Find source
        stmt = select(DocumentSource).where(DocumentSource.source_id == source_id)
        result = await db.execute(stmt)
        source = result.scalar_one_or_none()

        if source is None:
            raise SourceNotFoundError(f"Source not found: {source_id}")

        # Count chunks before deletion
        chunk_count = await self._get_chunk_count(db, source.id)

        # Delete source (cascades to chunks)
        await db.delete(source)
        await db.flush()

        logger.info(
            "rag.delete_source_completed",
            source_id=source_id,
            chunks_deleted=chunk_count,
        )

        return DeleteResponse(
            source_id=source_id,
            chunks_deleted=chunk_count,
            status="deleted",
        )

    async def _find_source_by_path(
        self,
        db: AsyncSession,
        source_type: str,
        source_path: str,
    ) -> DocumentSource | None:
        """Find source by type and path.

        Args:
            db: Database session.
            source_type: Source type.
            source_path: Source path.

        Returns:
            Source or None.
        """
        stmt = select(DocumentSource).where(
            (DocumentSource.source_type == source_type)
            & (DocumentSource.source_path == source_path)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_chunk_count(self, db: AsyncSession, source_id: int) -> int:
        """Get number of chunks for a source.

        Args:
            db: Database session.
            source_id: Source internal ID.

        Returns:
            Chunk count.
        """
        stmt = (
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.source_id == source_id)
        )
        result = await db.execute(stmt)
        return result.scalar_one()

    async def _get_total_chunk_count(self, db: AsyncSession) -> int:
        """Get total number of chunks across all sources.

        Args:
            db: Database session.

        Returns:
            Total chunk count.
        """
        stmt = select(func.count()).select_from(DocumentChunk)
        result = await db.execute(stmt)
        return result.scalar_one()

    async def _upsert_source_and_chunks(
        self,
        db: AsyncSession,
        source_id: str,
        source_type: str,
        source_path: str,
        content_hash: str,
        metadata: dict[str, Any] | None,
        chunks: list[ChunkData],
        embeddings: list[list[float]],
        existing_source: DocumentSource | None,
    ) -> None:
        """Upsert source and chunks in database.

        Args:
            db: Database session.
            source_id: External source identifier.
            source_type: Type of source.
            source_path: Path to source.
            content_hash: SHA-256 hash of content.
            metadata: Custom metadata.
            chunks: Chunked content.
            embeddings: Embeddings for each chunk.
            existing_source: Existing source if updating.
        """
        now = datetime.now(UTC)

        if existing_source:
            # Update existing source
            existing_source.content_hash = content_hash
            existing_source.metadata_ = metadata
            existing_source.indexed_at = now

            # Delete old chunks
            await db.execute(
                delete(DocumentChunk).where(DocumentChunk.source_id == existing_source.id)
            )
            source_internal_id = existing_source.id
        else:
            # Create new source
            source = DocumentSource(
                source_id=source_id,
                source_type=source_type,
                source_path=source_path,
                content_hash=content_hash,
                metadata_=metadata,
                indexed_at=now,
            )
            db.add(source)
            await db.flush()
            source_internal_id = source.id

        # Create new chunks
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
            chunk_obj = DocumentChunk(
                chunk_id=uuid.uuid4().hex,
                source_id=source_internal_id,
                chunk_index=i,
                content=chunk.content,
                embedding=embedding,
                token_count=chunk.token_count,
                metadata_=chunk.metadata if chunk.metadata else None,
            )
            db.add(chunk_obj)

        await db.flush()

    async def _search_similar_chunks(
        self,
        db: AsyncSession,
        query_embedding: list[float],
        top_k: int,
        threshold: float,
        filters: dict[str, Any] | None,
    ) -> list[ChunkResult]:
        """Search for similar chunks using cosine distance.

        Args:
            db: Database session.
            query_embedding: Query embedding vector.
            top_k: Maximum results to return.
            threshold: Minimum similarity threshold.
            filters: Optional metadata filters.

        Returns:
            List of chunk results with relevance scores.
        """
        # CRITICAL: Use cosine_distance method from pgvector
        # cosine_distance returns 1 - cosine_similarity for normalized vectors
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)

        # Build query with distance calculation
        stmt = (
            select(
                DocumentChunk,
                DocumentSource,
                distance.label("distance"),
            )
            .join(DocumentSource, DocumentChunk.source_id == DocumentSource.id)
            .where(DocumentChunk.embedding.isnot(None))
            .order_by(distance)
            .limit(top_k * 2)  # Fetch extra to filter by threshold
        )

        # Apply metadata filters if provided
        if filters:
            if "source_type" in filters:
                source_types = filters["source_type"]
                if isinstance(source_types, str):
                    source_types = [source_types]
                stmt = stmt.where(DocumentSource.source_type.in_(source_types))

            if "category" in filters:
                # Filter by metadata category
                stmt = stmt.where(
                    DocumentSource.metadata_.op("->>")("category") == filters["category"]
                )

        result = await db.execute(stmt)
        rows = result.all()

        results: list[ChunkResult] = []
        for chunk, source, dist in rows:
            # Convert distance to similarity score
            # For cosine distance: similarity = 1 - distance
            relevance_score = 1.0 - float(dist)

            # Apply threshold filter
            if relevance_score < threshold:
                continue

            results.append(
                ChunkResult(
                    chunk_id=chunk.chunk_id,
                    source_id=source.source_id,
                    source_path=source.source_path,
                    source_type=source.source_type,
                    content=chunk.content,
                    relevance_score=round(relevance_score, 4),
                    metadata=chunk.metadata_,
                )
            )

            # Stop if we have enough results
            if len(results) >= top_k:
                break

        return results
