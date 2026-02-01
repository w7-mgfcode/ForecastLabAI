"""RAG API routes for document indexing and semantic retrieval."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import DatabaseError
from app.core.logging import get_logger
from app.features.rag.embeddings import EmbeddingError
from app.features.rag.schemas import (
    DeleteResponse,
    IndexRequest,
    IndexResponse,
    RetrieveRequest,
    RetrieveResponse,
    SourceListResponse,
)
from app.features.rag.service import RAGService, SourceNotFoundError

logger = get_logger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])


# =============================================================================
# Index Endpoint
# =============================================================================


@router.post(
    "/index",
    response_model=IndexResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Index a document",
    description="""
Index a document into the RAG knowledge base.

**Source Types:**
- `markdown`: Markdown documents (split by headings)
- `openapi`: OpenAPI specifications (split by endpoint)

**Content Source:**
- Provide `content` directly in the request, OR
- Provide `source_path` to read from file system

**Idempotent Updates:**
- Documents are identified by `source_type` + `source_path`
- Content hash is compared to detect changes
- If unchanged, returns `status: "unchanged"` without re-indexing
- If changed, old chunks are deleted and new ones created

**Returns:**
- `source_id`: Unique identifier for the indexed source
- `chunks_created`: Number of chunks created
- `tokens_processed`: Total tokens processed
- `status`: "indexed", "updated", or "unchanged"
""",
)
async def index_document(
    request: IndexRequest,
    db: AsyncSession = Depends(get_db),
) -> IndexResponse:
    """Index a document into the knowledge base.

    Args:
        request: Index request with source type, path, and optional content.
        db: Async database session from dependency.

    Returns:
        Indexing result with statistics.

    Raises:
        HTTPException: If file not found or embedding generation fails.
        DatabaseError: If database operation fails.
    """
    logger.info(
        "rag.index_request_received",
        source_type=request.source_type,
        source_path=request.source_path,
        has_content=request.content is not None,
    )

    service = RAGService()

    try:
        response = await service.index_document(db=db, request=request)

        logger.info(
            "rag.index_request_completed",
            source_id=response.source_id,
            chunks_created=response.chunks_created,
            status=response.status,
        )

        return response

    except FileNotFoundError as e:
        logger.warning(
            "rag.index_request_failed",
            error=str(e),
            error_type=type(e).__name__,
            source_path=request.source_path,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    except EmbeddingError as e:
        logger.error(
            "rag.index_request_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Embedding generation failed: {e}",
        ) from e

    except SQLAlchemyError as e:
        logger.error(
            "rag.index_request_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise DatabaseError(
            message="Failed to index document",
            details={"error": str(e)},
        ) from e


# =============================================================================
# Retrieve Endpoint
# =============================================================================


@router.post(
    "/retrieve",
    response_model=RetrieveResponse,
    summary="Semantic search",
    description="""
Perform semantic search across indexed documents.

**Query:**
- Natural language query (1-2000 characters)
- Converted to embedding for similarity search

**Parameters:**
- `top_k`: Number of results (1-50, default: 5)
- `similarity_threshold`: Minimum similarity (0.0-1.0, default: 0.7)
- `filters`: Optional metadata filters

**Filters:**
- `source_type`: List of source types to search
- `category`: Category from source metadata

**Returns:**
- List of matching chunks with relevance scores
- Performance metrics (embedding time, search time)
- Total chunks searched

**Evidence-Grounded:**
Returns raw chunks with citations - no answer generation.
""",
)
async def retrieve(
    request: RetrieveRequest,
    db: AsyncSession = Depends(get_db),
) -> RetrieveResponse:
    """Perform semantic search across indexed documents.

    Args:
        request: Retrieval request with query and filters.
        db: Async database session from dependency.

    Returns:
        Search results with relevance scores.

    Raises:
        HTTPException: If embedding generation fails.
        DatabaseError: If database operation fails.
    """
    logger.info(
        "rag.retrieve_request_received",
        query_length=len(request.query),
        top_k=request.top_k,
        threshold=request.similarity_threshold,
        has_filters=request.filters is not None,
    )

    service = RAGService()

    try:
        response = await service.retrieve(db=db, request=request)

        logger.info(
            "rag.retrieve_request_completed",
            results_count=len(response.results),
            query_embedding_time_ms=response.query_embedding_time_ms,
            search_time_ms=response.search_time_ms,
        )

        return response

    except EmbeddingError as e:
        logger.error(
            "rag.retrieve_request_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Embedding generation failed: {e}",
        ) from e

    except SQLAlchemyError as e:
        logger.error(
            "rag.retrieve_request_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise DatabaseError(
            message="Failed to retrieve documents",
            details={"error": str(e)},
        ) from e


# =============================================================================
# Sources Endpoints
# =============================================================================


@router.get(
    "/sources",
    response_model=SourceListResponse,
    summary="List indexed sources",
    description="""
List all indexed document sources with statistics.

Returns:
- List of sources with chunk counts
- Total source count
- Total chunk count across all sources
""",
)
async def list_sources(
    db: AsyncSession = Depends(get_db),
) -> SourceListResponse:
    """List all indexed sources.

    Args:
        db: Async database session from dependency.

    Returns:
        List of sources with statistics.
    """
    service = RAGService()
    response = await service.list_sources(db=db)

    logger.info(
        "rag.list_sources_completed",
        total_sources=response.total_sources,
        total_chunks=response.total_chunks,
    )

    return response


@router.delete(
    "/sources/{source_id}",
    response_model=DeleteResponse,
    summary="Delete a source",
    description="""
Delete an indexed source and all its chunks.

**Cascade Delete:**
All chunks belonging to the source are automatically deleted.

**Returns:**
- `source_id`: Deleted source identifier
- `chunks_deleted`: Number of chunks removed
- `status`: Always "deleted"
""",
)
async def delete_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
) -> DeleteResponse:
    """Delete a source and all its chunks.

    Args:
        source_id: Source identifier.
        db: Async database session from dependency.

    Returns:
        Deletion result.

    Raises:
        HTTPException: If source not found.
        DatabaseError: If database operation fails.
    """
    logger.info("rag.delete_source_request_received", source_id=source_id)

    service = RAGService()

    try:
        response = await service.delete_source(db=db, source_id=source_id)

        logger.info(
            "rag.delete_source_request_completed",
            source_id=source_id,
            chunks_deleted=response.chunks_deleted,
        )

        return response

    except SourceNotFoundError as e:
        logger.warning(
            "rag.delete_source_request_failed",
            source_id=source_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    except SQLAlchemyError as e:
        logger.error(
            "rag.delete_source_request_failed",
            source_id=source_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise DatabaseError(
            message="Failed to delete source",
            details={"error": str(e)},
        ) from e
