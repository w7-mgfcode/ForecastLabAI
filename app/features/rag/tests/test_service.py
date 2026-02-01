"""Unit tests for RAG service."""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.rag.schemas import IndexRequest, RetrieveRequest
from app.features.rag.service import RAGService, SourceNotFoundError


class TestRAGServiceUnit:
    """Unit tests for RAGService (no database)."""

    def test_compute_content_hash(self):
        """Test content hash computation."""
        service = RAGService()

        content = "Test content"
        hash1 = service._compute_content_hash(content)

        # Should be SHA-256 hex (64 characters)
        assert len(hash1) == 64
        assert all(c in "0123456789abcdef" for c in hash1)

        # Same content should produce same hash
        hash2 = service._compute_content_hash(content)
        assert hash1 == hash2

        # Different content should produce different hash
        hash3 = service._compute_content_hash("Different content")
        assert hash1 != hash3

    def test_compute_content_hash_deterministic(self):
        """Test hash is deterministic."""
        service = RAGService()

        content = "# Test\n\nWith some content."
        expected = hashlib.sha256(content.encode()).hexdigest()

        result = service._compute_content_hash(content)
        assert result == expected

    def test_read_content_from_path_not_found(self, tmp_path):
        """Test reading from non-existent path raises."""
        service = RAGService()

        with pytest.raises(FileNotFoundError):
            service._read_content_from_path("/nonexistent/path.md")

    def test_read_content_from_path_success(self, tmp_path):
        """Test reading from existing path."""
        service = RAGService()

        # Create test file
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test Content")

        content = service._read_content_from_path(str(test_file))
        assert content == "# Test Content"


class TestRAGServiceIndexDocument:
    """Tests for index_document method."""

    @pytest.mark.asyncio
    async def test_index_with_content_provided(self, mock_embedding_service):
        """Test indexing when content is provided directly."""
        service = RAGService(embedding_service=mock_embedding_service)

        request = IndexRequest(
            source_type="markdown",
            source_path="test-direct-content.md",
            content="# Test\n\nDirect content.",
        )

        # Mock database session
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        mock_db.flush = AsyncMock()
        mock_db.add = MagicMock()

        with patch.object(service, "_find_source_by_path", return_value=None):
            with patch.object(service, "_upsert_source_and_chunks", new_callable=AsyncMock):
                response = await service.index_document(db=mock_db, request=request)

        assert response.status == "indexed"
        assert response.source_path == "test-direct-content.md"
        assert response.chunks_created > 0

    @pytest.mark.asyncio
    async def test_index_unchanged_content(self, mock_embedding_service):
        """Test that unchanged content returns 'unchanged' status."""
        service = RAGService(embedding_service=mock_embedding_service)

        content = "# Test\n\nContent."
        content_hash = service._compute_content_hash(content)

        request = IndexRequest(
            source_type="markdown",
            source_path="test-unchanged.md",
            content=content,
        )

        # Mock existing source with same hash
        mock_source = MagicMock()
        mock_source.source_id = "existing123"
        mock_source.content_hash = content_hash

        mock_db = AsyncMock()

        with patch.object(service, "_find_source_by_path", return_value=mock_source):
            with patch.object(service, "_get_chunk_count", return_value=5):
                response = await service.index_document(db=mock_db, request=request)

        assert response.status == "unchanged"
        assert response.tokens_processed == 0
        assert response.chunks_created == 5

    @pytest.mark.asyncio
    async def test_index_updated_content(self, mock_embedding_service):
        """Test that changed content returns 'updated' status."""
        service = RAGService(embedding_service=mock_embedding_service)

        request = IndexRequest(
            source_type="markdown",
            source_path="test-updated.md",
            content="# Updated\n\nNew content.",
        )

        # Mock existing source with different hash
        mock_source = MagicMock()
        mock_source.source_id = "existing123"
        mock_source.content_hash = "different_hash"

        mock_db = AsyncMock()

        with patch.object(service, "_find_source_by_path", return_value=mock_source):
            with patch.object(service, "_upsert_source_and_chunks", new_callable=AsyncMock):
                response = await service.index_document(db=mock_db, request=request)

        assert response.status == "updated"
        assert response.source_id == "existing123"


class TestRAGServiceRetrieve:
    """Tests for retrieve method."""

    @pytest.mark.asyncio
    async def test_retrieve_calls_embedding_service(self, mock_embedding_service):
        """Test that retrieve calls embedding service for query."""
        service = RAGService(embedding_service=mock_embedding_service)

        request = RetrieveRequest(
            query="Test query",
            top_k=5,
            similarity_threshold=0.7,
        )

        mock_db = AsyncMock()

        with patch.object(service, "_get_total_chunk_count", return_value=100):
            with patch.object(service, "_search_similar_chunks", return_value=[]):
                response = await service.retrieve(db=mock_db, request=request)

        # Verify embedding service was called
        mock_embedding_service.embed_query.assert_called_once_with("Test query")

        assert response.total_chunks_searched == 100
        assert len(response.results) == 0

    @pytest.mark.asyncio
    async def test_retrieve_returns_results(self, mock_embedding_service):
        """Test that retrieve returns search results."""
        from app.features.rag.schemas import ChunkResult

        service = RAGService(embedding_service=mock_embedding_service)

        request = RetrieveRequest(
            query="Test query",
            top_k=5,
        )

        mock_db = AsyncMock()

        mock_results = [
            ChunkResult(
                chunk_id="chunk1",
                source_id="src1",
                source_path="test.md",
                source_type="markdown",
                content="Result content",
                relevance_score=0.95,
            )
        ]

        with patch.object(service, "_get_total_chunk_count", return_value=50):
            with patch.object(service, "_search_similar_chunks", return_value=mock_results):
                response = await service.retrieve(db=mock_db, request=request)

        assert len(response.results) == 1
        assert response.results[0].relevance_score == 0.95


class TestRAGServiceListSources:
    """Tests for list_sources method."""

    @pytest.mark.asyncio
    async def test_list_sources_empty(self):
        """Test listing sources when none exist."""
        service = RAGService()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await service.list_sources(db=mock_db)

        assert response.total_sources == 0
        assert response.total_chunks == 0
        assert len(response.sources) == 0


class TestRAGServiceDeleteSource:
    """Tests for delete_source method."""

    @pytest.mark.asyncio
    async def test_delete_source_not_found(self):
        """Test deleting non-existent source raises."""
        service = RAGService()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(SourceNotFoundError):
            await service.delete_source(db=mock_db, source_id="nonexistent")

    @pytest.mark.asyncio
    async def test_delete_source_success(self):
        """Test successful source deletion."""
        service = RAGService()

        mock_source = MagicMock()
        mock_source.id = 1

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_source
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.delete = AsyncMock()
        mock_db.flush = AsyncMock()

        with patch.object(service, "_get_chunk_count", return_value=10):
            response = await service.delete_source(db=mock_db, source_id="test123")

        assert response.status == "deleted"
        assert response.chunks_deleted == 10
        mock_db.delete.assert_called_once_with(mock_source)
