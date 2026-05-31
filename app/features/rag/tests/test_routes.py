"""Integration tests for RAG API routes.

These tests require:
- PostgreSQL running with pgvector extension (docker-compose up -d)
- Migrations applied (uv run alembic upgrade head)

Note: These tests mock the OpenAI embedding service to avoid API calls.
"""

from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.features.rag.embeddings import EmbeddingAuthError, EmbeddingError, EmbeddingService
from app.features.rag.service import RAGService

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

    @pytest.mark.asyncio
    async def test_index_embedding_auth_failure_returns_502_with_marker(self, client: AsyncClient):
        """#329 — /rag/index maps an embedding auth failure to the marked 502.

        Mirrors the /rag/index/project-docs assertion so all three RAG routes
        stay aligned on the same RFC 7807 type/code.
        """
        mock_service = create_mock_embedding_service()
        mock_service.embed_texts = AsyncMock(
            side_effect=EmbeddingAuthError("OpenAI rejected the embedding credentials")
        )

        with patch(
            "app.features.rag.service.get_embedding_service",
            return_value=mock_service,
        ):
            response = await client.post(
                "/rag/index",
                json={
                    "source_type": "markdown",
                    "source_path": "test-index-auth-001",
                    "content": "# Auth\n\nContent that needs embedding.",
                },
            )

        assert response.status_code == 502
        body = response.json()
        assert body["code"] == "EMBEDDING_AUTH"
        assert body["type"].endswith("/embedding-auth")
        assert body["status"] == 502


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

    @pytest.mark.asyncio
    async def test_retrieve_embedding_auth_failure_returns_502_with_marker(
        self, client: AsyncClient
    ):
        """#329 — /rag/retrieve maps an embedding auth failure to the marked 502.

        Keeps the retrieve handler aligned with the two index handlers on the
        same RFC 7807 type/code.
        """
        mock_service = create_mock_embedding_service()
        auth_error = EmbeddingAuthError("OpenAI rejected the embedding credentials")
        mock_service.embed_query = AsyncMock(side_effect=auth_error)
        mock_service.embed_texts = AsyncMock(side_effect=auth_error)

        with patch(
            "app.features.rag.service.get_embedding_service",
            return_value=mock_service,
        ):
            response = await client.post(
                "/rag/retrieve",
                json={"query": "anything", "top_k": 5, "similarity_threshold": 0.0},
            )

        assert response.status_code == 502
        body = response.json()
        assert body["code"] == "EMBEDDING_AUTH"
        assert body["type"].endswith("/embedding-auth")
        assert body["status"] == 502


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


# =============================================================================
# Index Project Docs Endpoint Tests
# =============================================================================


@pytest.mark.integration
class TestIndexProjectDocsEndpoint:
    """Integration tests for POST /rag/index/project-docs endpoint."""

    @pytest.mark.asyncio
    async def test_indexes_discovered_docs(self, client: AsyncClient, tmp_path):
        """Test that discovered docs are indexed and re-runs are idempotent."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "PRPs").mkdir()
        # Non-empty content; `test-` token so conftest cleanup catches the rows.
        (tmp_path / "docs" / "test-proj-1.md").write_text(
            "# Alpha\n\nAlpha content.", encoding="utf-8"
        )
        (tmp_path / "PRPs" / "test-proj-2.md").write_text(
            "# Beta\n\nBeta content.", encoding="utf-8"
        )
        mock_service = create_mock_embedding_service()

        with (
            patch(
                "app.features.rag.routes.RAGService",
                partial(RAGService, base_dir=str(tmp_path)),
            ),
            patch(
                "app.features.rag.service.get_embedding_service",
                return_value=mock_service,
            ),
        ):
            response1 = await client.post("/rag/index/project-docs", json={})
            assert response1.status_code == 200
            data1 = response1.json()
            assert data1["total_files"] == 2
            assert data1["indexed"] == 2
            assert data1["failed"] == 0
            assert data1["total_chunks"] >= 2

            # Idempotent re-run — every file unchanged, no new chunks.
            response2 = await client.post("/rag/index/project-docs", json={})
            assert response2.status_code == 200
            assert response2.json()["unchanged"] == 2

    @pytest.mark.asyncio
    async def test_empty_roots_returns_zero(self, client: AsyncClient, tmp_path):
        """Test that an empty doc tree returns zero files without error."""
        mock_service = create_mock_embedding_service()

        with (
            patch(
                "app.features.rag.routes.RAGService",
                partial(RAGService, base_dir=str(tmp_path)),
            ),
            patch(
                "app.features.rag.service.get_embedding_service",
                return_value=mock_service,
            ),
        ):
            response = await client.post("/rag/index/project-docs", json={})

        assert response.status_code == 200
        assert response.json()["total_files"] == 0

    @pytest.mark.asyncio
    async def test_toggles_select_roots(self, client: AsyncClient, tmp_path):
        """Test that include_* toggles restrict discovery."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "PRPs").mkdir()
        (tmp_path / "docs" / "test-toggle-1.md").write_text(
            "# Docs\n\nDocs content.", encoding="utf-8"
        )
        (tmp_path / "PRPs" / "test-toggle-2.md").write_text(
            "# Prp\n\nPrp content.", encoding="utf-8"
        )
        mock_service = create_mock_embedding_service()

        with (
            patch(
                "app.features.rag.routes.RAGService",
                partial(RAGService, base_dir=str(tmp_path)),
            ),
            patch(
                "app.features.rag.service.get_embedding_service",
                return_value=mock_service,
            ),
        ):
            response = await client.post(
                "/rag/index/project-docs",
                json={"include_prps": False, "include_root": False},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total_files"] == 1
        assert data["results"][0]["source_path"] == "docs/test-toggle-1.md"

    @pytest.mark.asyncio
    async def test_unknown_field_rejected(self, client: AsyncClient):
        """Test that an unknown body field is rejected (extra='forbid')."""
        response = await client.post("/rag/index/project-docs", json={"bogus": True})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_embedding_failure_returns_502(self, client: AsyncClient, tmp_path):
        """Test that an embedding-provider failure is batch-fatal (502)."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "test-proj-3.md").write_text(
            "# Gamma\n\nGamma content.", encoding="utf-8"
        )
        # Build a mock whose embed_texts raises — a MagicMock var (not the
        # EmbeddingService-typed factory return) so mypy permits the assignment.
        mock_service = MagicMock(spec=EmbeddingService)
        mock_service.embed_texts = AsyncMock(side_effect=EmbeddingError("no key"))

        with (
            patch(
                "app.features.rag.routes.RAGService",
                partial(RAGService, base_dir=str(tmp_path)),
            ),
            patch(
                "app.features.rag.service.get_embedding_service",
                return_value=mock_service,
            ),
        ):
            response = await client.post("/rag/index/project-docs", json={})

        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_embedding_auth_failure_returns_502_with_marker(
        self, client: AsyncClient, tmp_path
    ):
        """#329 — an embedding auth failure stays 502 but carries the

        machine-readable EMBEDDING_AUTH problem marker so the demo pipeline can
        classify it (vs a generic embedding 502) without brittle text matching.
        """
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "auth-doc.md").write_text(
            "# Delta\n\nDelta content.", encoding="utf-8"
        )
        mock_service = MagicMock(spec=EmbeddingService)
        mock_service.embed_texts = AsyncMock(
            side_effect=EmbeddingAuthError("OpenAI rejected the embedding credentials")
        )

        with (
            patch(
                "app.features.rag.routes.RAGService",
                partial(RAGService, base_dir=str(tmp_path)),
            ),
            patch(
                "app.features.rag.service.get_embedding_service",
                return_value=mock_service,
            ),
        ):
            response = await client.post("/rag/index/project-docs", json={})

        # Status stays 502 (public contract stable); body is RFC 7807 with a
        # stable type/code an automated consumer can branch on.
        assert response.status_code == 502
        body = response.json()
        assert body["code"] == "EMBEDDING_AUTH"
        assert body["type"].endswith("/embedding-auth")
        assert body["status"] == 502
