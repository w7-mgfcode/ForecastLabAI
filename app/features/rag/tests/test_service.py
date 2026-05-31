"""Unit tests for RAG service."""

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.rag.schemas import (
    IndexProjectDocsRequest,
    IndexRequest,
    RetrieveRequest,
)
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
        # Pass tmp_path as base_dir to allow test files in tmp directory
        service = RAGService(base_dir=tmp_path)

        # Create test file
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test Content")

        content = service._read_content_from_path(str(test_file))
        assert content == "# Test Content"

    def test_read_content_from_path_traversal_blocked(self, tmp_path):
        """Test that path traversal attempts are blocked."""
        # Set base_dir to tmp_path
        service = RAGService(base_dir=tmp_path)

        # Try to read file outside base_dir (should fail)
        with pytest.raises(FileNotFoundError, match="not found or access denied"):
            service._read_content_from_path("/etc/passwd")


class TestRAGServiceDiscoverProjectDocFiles:
    """Unit tests for RAGService._discover_project_doc_files (pure, no DB)."""

    @staticmethod
    def _build_tree(tmp_path: Path) -> None:
        """Create a fixture doc tree under tmp_path."""
        (tmp_path / "docs" / "sub").mkdir(parents=True)
        (tmp_path / "PRPs").mkdir()
        (tmp_path / "docs" / "test-a.md").write_text("# A", encoding="utf-8")
        (tmp_path / "docs" / "sub" / "test-b.md").write_text("# B", encoding="utf-8")
        (tmp_path / "docs" / "notes.txt").write_text("not markdown", encoding="utf-8")
        (tmp_path / "PRPs" / "test-c.md").write_text("# C", encoding="utf-8")
        (tmp_path / "README.md").write_text("# Readme", encoding="utf-8")

    def test_discovers_all_roots(self, tmp_path):
        """Test discovery across docs/, PRPs/, and the root allow-list."""
        self._build_tree(tmp_path)
        service = RAGService(base_dir=str(tmp_path))

        found = service._discover_project_doc_files(IndexProjectDocsRequest())

        rel = {p.relative_to(tmp_path).as_posix(): cat for p, cat in found}
        assert rel == {
            "docs/test-a.md": "docs",
            "docs/sub/test-b.md": "docs",
            "PRPs/test-c.md": "prp",
            "README.md": "root",
        }

    def test_filters_non_markdown(self, tmp_path):
        """Test that non-.md files (notes.txt) are excluded."""
        self._build_tree(tmp_path)
        service = RAGService(base_dir=str(tmp_path))

        found = service._discover_project_doc_files(IndexProjectDocsRequest())

        assert all(p.suffix == ".md" for p, _ in found)

    def test_result_is_sorted(self, tmp_path):
        """Test that discovery returns a deterministically sorted list."""
        self._build_tree(tmp_path)
        service = RAGService(base_dir=str(tmp_path))

        found = service._discover_project_doc_files(IndexProjectDocsRequest())

        paths = [str(p) for p, _ in found]
        assert paths == sorted(paths)

    def test_toggles_select_roots(self, tmp_path):
        """Test that include_* toggles select roots independently."""
        self._build_tree(tmp_path)
        service = RAGService(base_dir=str(tmp_path))

        docs_only = service._discover_project_doc_files(
            IndexProjectDocsRequest(include_prps=False, include_root=False)
        )
        assert {cat for _, cat in docs_only} == {"docs"}

        no_root = service._discover_project_doc_files(IndexProjectDocsRequest(include_root=False))
        assert "root" not in {cat for _, cat in no_root}

    def test_missing_root_directory_yields_nothing(self, tmp_path):
        """Test that an absent docs/ or PRPs/ root contributes 0 files."""
        # tmp_path is empty — no docs/, no PRPs/, no root markdown.
        service = RAGService(base_dir=str(tmp_path))

        found = service._discover_project_doc_files(IndexProjectDocsRequest())

        assert found == []

    def test_root_allow_list_only(self, tmp_path):
        """Test that only allow-listed root files are discovered."""
        (tmp_path / "README.md").write_text("# Readme", encoding="utf-8")
        (tmp_path / "NOTES.md").write_text("# Notes", encoding="utf-8")
        service = RAGService(base_dir=str(tmp_path))

        found = service._discover_project_doc_files(IndexProjectDocsRequest())

        names = {p.name for p, _ in found}
        assert names == {"README.md"}

    # --- PRP-40 — additive path_prefix sub-path filter ---

    def test_path_prefix_scopes_docs_discovery(self, tmp_path):
        """PRP-40 — path_prefix='docs/user-guide' restricts docs scan to that subtree."""
        (tmp_path / "docs" / "user-guide").mkdir(parents=True)
        (tmp_path / "docs" / "other").mkdir()
        (tmp_path / "docs" / "user-guide" / "intro.md").write_text("# A", encoding="utf-8")
        (tmp_path / "docs" / "other" / "internal.md").write_text("# B", encoding="utf-8")
        service = RAGService(base_dir=str(tmp_path))

        found = service._discover_project_doc_files(
            IndexProjectDocsRequest(
                include_docs=True,
                include_prps=False,
                include_root=False,
                path_prefix="docs/user-guide",
            )
        )

        rels = {p.relative_to(tmp_path).as_posix() for p, _ in found}
        assert rels == {"docs/user-guide/intro.md"}

    def test_path_prefix_none_preserves_wholesale_scan(self, tmp_path):
        """PRP-40 — path_prefix=None (default) keeps the existing wholesale rglob behaviour."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "a.md").write_text("# A", encoding="utf-8")
        (tmp_path / "docs" / "deep").mkdir()
        (tmp_path / "docs" / "deep" / "b.md").write_text("# B", encoding="utf-8")
        service = RAGService(base_dir=str(tmp_path))

        found = service._discover_project_doc_files(
            IndexProjectDocsRequest(include_docs=True, include_prps=False, include_root=False)
        )

        rels = {p.relative_to(tmp_path).as_posix() for p, _ in found}
        assert rels == {"docs/a.md", "docs/deep/b.md"}

    def test_index_project_docs_rejects_path_traversal(self, tmp_path):
        """PRP-40 — path_prefix that escapes base_dir raises ValueError.

        Load-bearing security surface — `path_prefix` lands in an `rglob` call,
        so a traversal-prefix MUST be rejected at the discovery layer
        (security-patterns.md path-traversal rule).
        """
        service = RAGService(base_dir=str(tmp_path))

        with pytest.raises(ValueError, match="escapes the project root"):
            service._discover_project_doc_files(
                IndexProjectDocsRequest(
                    include_docs=True,
                    include_prps=False,
                    include_root=False,
                    path_prefix="../../etc",
                )
            )


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
