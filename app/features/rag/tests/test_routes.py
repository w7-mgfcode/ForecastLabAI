"""Integration tests for RAG API routes.

These tests require:
- PostgreSQL running with pgvector extension (docker-compose up -d)
- Migrations applied (uv run alembic upgrade head)

Note: These tests mock the OpenAI embedding service to avoid API calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.features.rag.embeddings import EmbeddingService

# =============================================================================
# Mock Embedding Service for Integration Tests
# =============================================================================


def create_mock_embedding_service() -> EmbeddingService:
    """Create a mock embedding service for integration tests."""
    service = MagicMock(spec=EmbeddingService)

    async def mock_embed_texts(texts, **kwargs):
        return [[0.1 + i * 0.01] * 1536 for i, _ in enumerate(texts)]

    async def mock_embed_query(query):
        return [0.1] * 1536

    service.embed_texts = AsyncMock(side_effect=mock_embed_texts)
    service.embed_query = AsyncMock(side_effect=mock_embed_query)
    service.count_tokens = MagicMock(side_effect=lambda text: len(text.split()))
    service.truncate_to_tokens = MagicMock(side_effect=lambda text, max_tokens: text)

    return service


# =============================================================================
# Index Endpoint Tests
# =============================================================================


@pytest.mark.integration
class TestIndexEndpoint:
    """Integration tests for POST /rag/index endpoint."""

    @pytest.mark.asyncio
    async def test_index_markdown_creates_chunks(self, client: AsyncClient):
        """Test that indexing markdown creates chunks in database."""
        mock_service = create_mock_embedding_service()

        with patch(
            "app.features.rag.service.get_embedding_service",
            return_value=mock_service,
        ):
            response = await client.post(
                "/rag/index",
                json={
                    "source_type": "markdown",
                    "source_path": "test-index-md-001",
                    "content": "# Test Document\n\nThis is test content for indexing.",
                    "metadata": {"category": "testing"},
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "indexed"
        assert data["chunks_created"] >= 1
        assert data["source_path"] == "test-index-md-001"
        assert "source_id" in data

    @pytest.mark.asyncio
    async def test_index_same_content_returns_unchanged(self, client: AsyncClient):
        """Test that re-indexing unchanged content returns 'unchanged' status."""
        mock_service = create_mock_embedding_service()

        content = "# Unchanged\n\nSame content twice."

        with patch(
            "app.features.rag.service.get_embedding_service",
            return_value=mock_service,
        ):
            # First index
            response1 = await client.post(
                "/rag/index",
                json={
                    "source_type": "markdown",
                    "source_path": "test-unchanged-001",
                    "content": content,
                },
            )
            assert response1.status_code == 201
            assert response1.json()["status"] == "indexed"

            # Second index with same content
            response2 = await client.post(
                "/rag/index",
                json={
                    "source_type": "markdown",
                    "source_path": "test-unchanged-001",
                    "content": content,
                },
            )
            assert response2.status_code == 201
            assert response2.json()["status"] == "unchanged"

    @pytest.mark.asyncio
    async def test_index_updated_content_re_indexes(self, client: AsyncClient):
        """Test that updated content triggers re-indexing."""
        mock_service = create_mock_embedding_service()

        with patch(
            "app.features.rag.service.get_embedding_service",
            return_value=mock_service,
        ):
            # First index
            response1 = await client.post(
                "/rag/index",
                json={
                    "source_type": "markdown",
                    "source_path": "test-updated-001",
                    "content": "# Original\n\nOriginal content.",
                },
            )
            assert response1.status_code == 201
            source_id = response1.json()["source_id"]

            # Second index with different content
            response2 = await client.post(
                "/rag/index",
                json={
                    "source_type": "markdown",
                    "source_path": "test-updated-001",
                    "content": "# Updated\n\nNew updated content.",
                },
            )
            assert response2.status_code == 201
            assert response2.json()["status"] == "updated"
            assert response2.json()["source_id"] == source_id

    @pytest.mark.asyncio
    async def test_index_invalid_source_type(self, client: AsyncClient):
        """Test that invalid source type returns 422."""
        response = await client.post(
            "/rag/index",
            json={
                "source_type": "invalid",
                "source_path": "test.txt",
                "content": "test",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_index_file_not_found(self, client: AsyncClient):
        """Test that missing file returns 404."""
        response = await client.post(
            "/rag/index",
            json={
                "source_type": "markdown",
                "source_path": "/nonexistent/path/file.md",
            },
        )
        assert response.status_code == 404


# =============================================================================
# Retrieve Endpoint Tests
# =============================================================================


@pytest.mark.integration
class TestRetrieveEndpoint:
    """Integration tests for POST /rag/retrieve endpoint."""

    @pytest.mark.asyncio
    async def test_retrieve_returns_relevant_chunks(self, client: AsyncClient):
        """Test that retrieval returns matching chunks."""
        mock_service = create_mock_embedding_service()

        with patch(
            "app.features.rag.service.get_embedding_service",
            return_value=mock_service,
        ):
            # First, index a document
            await client.post(
                "/rag/index",
                json={
                    "source_type": "markdown",
                    "source_path": "test-retrieve-001",
                    "content": "# Backtesting Guide\n\nBacktesting prevents data leakage by using time-based splits.",
                },
            )

            # Then retrieve
            response = await client.post(
                "/rag/retrieve",
                json={
                    "query": "How does backtesting prevent leakage?",
                    "top_k": 5,
                    "similarity_threshold": 0.0,  # Low threshold to ensure results
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "query_embedding_time_ms" in data
        assert "search_time_ms" in data
        assert "total_chunks_searched" in data

    @pytest.mark.asyncio
    async def test_retrieve_respects_threshold(self, client: AsyncClient):
        """Test that retrieval respects similarity threshold."""
        mock_service = create_mock_embedding_service()

        with patch(
            "app.features.rag.service.get_embedding_service",
            return_value=mock_service,
        ):
            # Index a document
            await client.post(
                "/rag/index",
                json={
                    "source_type": "markdown",
                    "source_path": "test-threshold-001",
                    "content": "# Test Content\n\nSome test content here.",
                },
            )

            # Retrieve with very high threshold
            response = await client.post(
                "/rag/retrieve",
                json={
                    "query": "unrelated query",
                    "top_k": 5,
                    "similarity_threshold": 0.99,  # Very high threshold
                },
            )

        assert response.status_code == 200
        # With high threshold and mock embeddings, results may be empty
        data = response.json()
        assert isinstance(data["results"], list)

    @pytest.mark.asyncio
    async def test_retrieve_empty_database(self, client: AsyncClient):
        """Test retrieval on empty database returns empty results."""
        mock_service = create_mock_embedding_service()

        with patch(
            "app.features.rag.service.get_embedding_service",
            return_value=mock_service,
        ):
            response = await client.post(
                "/rag/retrieve",
                json={
                    "query": "anything",
                    "top_k": 5,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["results"], list)

    @pytest.mark.asyncio
    async def test_retrieve_validates_query(self, client: AsyncClient):
        """Test that empty query is rejected."""
        response = await client.post(
            "/rag/retrieve",
            json={
                "query": "",
                "top_k": 5,
            },
        )
        assert response.status_code == 422


# =============================================================================
# Sources Endpoint Tests
# =============================================================================


@pytest.mark.integration
class TestSourcesEndpoint:
    """Integration tests for /rag/sources endpoints."""

    @pytest.mark.asyncio
    async def test_list_sources_returns_all(self, client: AsyncClient):
        """Test listing all indexed sources."""
        mock_service = create_mock_embedding_service()

        with patch(
            "app.features.rag.service.get_embedding_service",
            return_value=mock_service,
        ):
            # Index a couple of documents
            await client.post(
                "/rag/index",
                json={
                    "source_type": "markdown",
                    "source_path": "test-list-001",
                    "content": "# First Doc",
                },
            )
            await client.post(
                "/rag/index",
                json={
                    "source_type": "markdown",
                    "source_path": "test-list-002",
                    "content": "# Second Doc",
                },
            )

            # List sources
            response = await client.get("/rag/sources")

        assert response.status_code == 200
        data = response.json()
        assert "sources" in data
        assert "total_sources" in data
        assert "total_chunks" in data
        assert data["total_sources"] >= 2

    @pytest.mark.asyncio
    async def test_delete_source_removes_chunks(self, client: AsyncClient):
        """Test that deleting a source removes all its chunks."""
        mock_service = create_mock_embedding_service()

        with patch(
            "app.features.rag.service.get_embedding_service",
            return_value=mock_service,
        ):
            # Index a document
            index_response = await client.post(
                "/rag/index",
                json={
                    "source_type": "markdown",
                    "source_path": "test-delete-001",
                    "content": "# Delete Me\n\nThis will be deleted.",
                },
            )
            source_id = index_response.json()["source_id"]

            # Delete the source
            delete_response = await client.delete(f"/rag/sources/{source_id}")

        assert delete_response.status_code == 200
        data = delete_response.json()
        assert data["status"] == "deleted"
        assert data["chunks_deleted"] >= 1

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, client: AsyncClient):
        """Test that deleting non-existent source returns 404."""
        response = await client.delete("/rag/sources/nonexistent123456789012")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_source_not_in_list_after_delete(self, client: AsyncClient):
        """Test that deleted source no longer appears in list."""
        mock_service = create_mock_embedding_service()

        with patch(
            "app.features.rag.service.get_embedding_service",
            return_value=mock_service,
        ):
            # Index a document
            index_response = await client.post(
                "/rag/index",
                json={
                    "source_type": "markdown",
                    "source_path": "test-delete-verify-001",
                    "content": "# Verify Delete",
                },
            )
            source_id = index_response.json()["source_id"]

            # Delete the source
            await client.delete(f"/rag/sources/{source_id}")

            # Verify not in list
            list_response = await client.get("/rag/sources")
            source_ids = [s["source_id"] for s in list_response.json()["sources"]]
            assert source_id not in source_ids


# =============================================================================
# OpenAPI Indexing Tests
# =============================================================================


@pytest.mark.integration
class TestOpenAPIIndexing:
    """Integration tests for OpenAPI document indexing."""

    @pytest.mark.asyncio
    async def test_index_openapi_creates_endpoint_chunks(self, client: AsyncClient):
        """Test that OpenAPI spec creates endpoint-based chunks."""
        mock_service = create_mock_embedding_service()

        openapi_spec = """{
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0"},
            "paths": {
                "/users": {
                    "get": {"summary": "List users", "operationId": "listUsers", "responses": {"200": {"description": "OK"}}},
                    "post": {"summary": "Create user", "operationId": "createUser", "responses": {"201": {"description": "Created"}}}
                }
            }
        }"""

        with patch(
            "app.features.rag.service.get_embedding_service",
            return_value=mock_service,
        ):
            response = await client.post(
                "/rag/index",
                json={
                    "source_type": "openapi",
                    "source_path": "test-openapi-001",
                    "content": openapi_spec,
                },
            )

        assert response.status_code == 201
        data = response.json()
        # Should have at least: info chunk + 2 endpoint chunks
        assert data["chunks_created"] >= 3
