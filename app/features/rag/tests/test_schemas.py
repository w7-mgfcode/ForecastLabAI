"""Unit tests for RAG schemas."""

import pytest
from pydantic import ValidationError

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


class TestIndexRequest:
    """Tests for IndexRequest schema."""

    def test_valid_markdown_request(self):
        """Test valid markdown index request."""
        request = IndexRequest(
            source_type="markdown",
            source_path="docs/README.md",
            content="# Hello\n\nWorld",
            metadata={"category": "docs"},
        )
        assert request.source_type == "markdown"
        assert request.source_path == "docs/README.md"
        assert request.content == "# Hello\n\nWorld"
        assert request.metadata == {"category": "docs"}

    def test_valid_openapi_request(self):
        """Test valid openapi index request."""
        request = IndexRequest(
            source_type="openapi",
            source_path="api/openapi.json",
        )
        assert request.source_type == "openapi"
        assert request.content is None
        assert request.metadata is None

    def test_invalid_source_type(self):
        """Test invalid source type is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IndexRequest(
                source_type="invalid",  # type: ignore[arg-type]
                source_path="test.txt",
            )
        assert "source_type" in str(exc_info.value)

    def test_empty_source_path_rejected(self):
        """Test empty source path is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IndexRequest(
                source_type="markdown",
                source_path="",
            )
        assert "source_path" in str(exc_info.value)

    def test_source_path_max_length(self):
        """Test source path max length is enforced."""
        with pytest.raises(ValidationError) as exc_info:
            IndexRequest(
                source_type="markdown",
                source_path="x" * 501,
            )
        assert "source_path" in str(exc_info.value)

    def test_extra_fields_rejected(self):
        """Test extra fields are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IndexRequest(
                source_type="markdown",
                source_path="test.md",
                extra_field="not allowed",  # type: ignore[call-arg]
            )
        assert "extra_field" in str(exc_info.value)


class TestRetrieveRequest:
    """Tests for RetrieveRequest schema."""

    def test_valid_request_defaults(self):
        """Test valid request with defaults."""
        request = RetrieveRequest(query="What is forecasting?")
        assert request.query == "What is forecasting?"
        assert request.top_k == 5
        # similarity_threshold defaults to None (service uses settings fallback)
        assert request.similarity_threshold is None
        assert request.filters is None

    def test_valid_request_custom_params(self):
        """Test valid request with custom parameters."""
        request = RetrieveRequest(
            query="How does backtesting work?",
            top_k=10,
            similarity_threshold=0.8,
            filters={"source_type": ["markdown"]},
        )
        assert request.top_k == 10
        assert request.similarity_threshold == 0.8
        assert request.filters == {"source_type": ["markdown"]}

    def test_empty_query_rejected(self):
        """Test empty query is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RetrieveRequest(query="")
        assert "query" in str(exc_info.value)

    def test_query_max_length(self):
        """Test query max length is enforced."""
        with pytest.raises(ValidationError) as exc_info:
            RetrieveRequest(query="x" * 2001)
        assert "query" in str(exc_info.value)

    def test_top_k_bounds(self):
        """Test top_k bounds are enforced."""
        # Below minimum
        with pytest.raises(ValidationError):
            RetrieveRequest(query="test", top_k=0)

        # Above maximum
        with pytest.raises(ValidationError):
            RetrieveRequest(query="test", top_k=51)

        # Valid bounds
        request_min = RetrieveRequest(query="test", top_k=1)
        assert request_min.top_k == 1

        request_max = RetrieveRequest(query="test", top_k=50)
        assert request_max.top_k == 50

    def test_similarity_threshold_bounds(self):
        """Test similarity threshold bounds are enforced."""
        # Below minimum
        with pytest.raises(ValidationError):
            RetrieveRequest(query="test", similarity_threshold=-0.1)

        # Above maximum
        with pytest.raises(ValidationError):
            RetrieveRequest(query="test", similarity_threshold=1.1)

        # Valid bounds
        request_min = RetrieveRequest(query="test", similarity_threshold=0.0)
        assert request_min.similarity_threshold == 0.0

        request_max = RetrieveRequest(query="test", similarity_threshold=1.0)
        assert request_max.similarity_threshold == 1.0


class TestIndexResponse:
    """Tests for IndexResponse schema."""

    def test_indexed_status(self):
        """Test indexed status response."""
        response = IndexResponse(
            source_id="abc123",
            source_path="test.md",
            chunks_created=5,
            tokens_processed=1000,
            duration_ms=123.45,
            status="indexed",
        )
        assert response.status == "indexed"
        assert response.chunks_created == 5

    def test_updated_status(self):
        """Test updated status response."""
        response = IndexResponse(
            source_id="abc123",
            source_path="test.md",
            chunks_created=3,
            tokens_processed=500,
            duration_ms=50.0,
            status="updated",
        )
        assert response.status == "updated"

    def test_unchanged_status(self):
        """Test unchanged status response."""
        response = IndexResponse(
            source_id="abc123",
            source_path="test.md",
            chunks_created=5,
            tokens_processed=0,
            duration_ms=10.0,
            status="unchanged",
        )
        assert response.status == "unchanged"
        assert response.tokens_processed == 0


class TestChunkResult:
    """Tests for ChunkResult schema."""

    def test_valid_chunk_result(self):
        """Test valid chunk result."""
        result = ChunkResult(
            chunk_id="chunk123",
            source_id="src123",
            source_path="docs/test.md",
            source_type="markdown",
            content="This is chunk content",
            relevance_score=0.95,
            metadata={"heading": "Introduction"},
        )
        assert result.relevance_score == 0.95
        assert result.metadata == {"heading": "Introduction"}

    def test_relevance_score_bounds(self):
        """Test relevance score bounds."""
        # Valid bounds
        result_zero = ChunkResult(
            chunk_id="c1",
            source_id="s1",
            source_path="test.md",
            source_type="markdown",
            content="test",
            relevance_score=0.0,
        )
        assert result_zero.relevance_score == 0.0

        result_one = ChunkResult(
            chunk_id="c1",
            source_id="s1",
            source_path="test.md",
            source_type="markdown",
            content="test",
            relevance_score=1.0,
        )
        assert result_one.relevance_score == 1.0

        # Out of bounds
        with pytest.raises(ValidationError):
            ChunkResult(
                chunk_id="c1",
                source_id="s1",
                source_path="test.md",
                source_type="markdown",
                content="test",
                relevance_score=1.5,
            )


class TestRetrieveResponse:
    """Tests for RetrieveResponse schema."""

    def test_valid_response(self):
        """Test valid retrieve response."""
        response = RetrieveResponse(
            results=[
                ChunkResult(
                    chunk_id="c1",
                    source_id="s1",
                    source_path="test.md",
                    source_type="markdown",
                    content="test content",
                    relevance_score=0.9,
                )
            ],
            query_embedding_time_ms=45.5,
            search_time_ms=12.3,
            total_chunks_searched=100,
        )
        assert len(response.results) == 1
        assert response.total_chunks_searched == 100

    def test_empty_results(self):
        """Test response with no results."""
        response = RetrieveResponse(
            results=[],
            query_embedding_time_ms=50.0,
            search_time_ms=10.0,
            total_chunks_searched=0,
        )
        assert len(response.results) == 0


class TestSourceResponse:
    """Tests for SourceResponse schema."""

    def test_valid_source_response(self):
        """Test valid source response."""
        from datetime import UTC, datetime

        response = SourceResponse(
            source_id="src123",
            source_type="markdown",
            source_path="docs/README.md",
            chunk_count=10,
            content_hash="a" * 64,
            indexed_at=datetime.now(UTC),
            metadata={"category": "docs"},
        )
        assert response.chunk_count == 10
        assert response.source_type == "markdown"


class TestSourceListResponse:
    """Tests for SourceListResponse schema."""

    def test_valid_list_response(self):
        """Test valid source list response."""
        from datetime import UTC, datetime

        response = SourceListResponse(
            sources=[
                SourceResponse(
                    source_id="src1",
                    source_type="markdown",
                    source_path="doc1.md",
                    chunk_count=5,
                    content_hash="a" * 64,
                    indexed_at=datetime.now(UTC),
                )
            ],
            total_sources=1,
            total_chunks=5,
        )
        assert response.total_sources == 1
        assert response.total_chunks == 5

    def test_empty_list_response(self):
        """Test empty source list response."""
        response = SourceListResponse(
            sources=[],
            total_sources=0,
            total_chunks=0,
        )
        assert len(response.sources) == 0


class TestDeleteResponse:
    """Tests for DeleteResponse schema."""

    def test_valid_delete_response(self):
        """Test valid delete response."""
        response = DeleteResponse(
            source_id="src123",
            chunks_deleted=10,
            status="deleted",
        )
        assert response.status == "deleted"
        assert response.chunks_deleted == 10
