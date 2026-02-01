"""Unit tests for RAG chunkers."""

import json

import pytest

from app.features.rag.chunkers import (
    BaseChunker,
    ChunkData,
    MarkdownChunker,
    OpenAPIChunker,
    get_chunker,
)


class TestMarkdownChunker:
    """Tests for MarkdownChunker."""

    def test_chunk_simple_document(self, sample_markdown_content):
        """Test chunking a simple markdown document."""
        chunker = MarkdownChunker()
        chunks = chunker.chunk(sample_markdown_content)

        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk, ChunkData)
            assert chunk.content
            assert chunk.token_count > 0

    def test_chunk_respects_heading_boundaries(self):
        """Test that chunker respects heading boundaries."""
        content = """# Title

Introduction.

## Section One

Content one.

## Section Two

Content two.
"""
        chunker = MarkdownChunker()
        chunker.chunk_size = 1000  # Large enough to not split within sections
        chunks = chunker.chunk(content)

        # Each section should be relatively intact
        contents = [c.content for c in chunks]
        full_content = "\n".join(contents)

        assert "# Title" in full_content or "Title" in full_content
        assert "Section One" in full_content
        assert "Section Two" in full_content

    def test_chunk_extracts_heading_metadata(self):
        """Test that heading metadata is extracted."""
        content = """# Main

## Sub

Content here.
"""
        chunker = MarkdownChunker()
        chunks = chunker.chunk(content)

        # Find chunk with heading metadata
        chunks_with_headings = [c for c in chunks if c.metadata.get("heading")]
        assert len(chunks_with_headings) > 0

        # Check section_path is populated
        for chunk in chunks_with_headings:
            if chunk.metadata.get("section_path"):
                assert isinstance(chunk.metadata["section_path"], list)

    def test_chunk_respects_chunk_size(self, sample_large_markdown_content):
        """Test that chunks respect the configured chunk size."""
        chunker = MarkdownChunker()
        chunker.chunk_size = 200  # Small chunk size
        chunks = chunker.chunk(sample_large_markdown_content)

        # Chunks should not vastly exceed chunk size
        for chunk in chunks:
            # Allow some tolerance for overlap and heading context
            assert chunk.token_count <= chunker.chunk_size * 2

    def test_chunk_handles_empty_content(self):
        """Test handling of empty content."""
        chunker = MarkdownChunker()
        chunks = chunker.chunk("")

        assert len(chunks) == 0

    def test_chunk_handles_content_without_headings(self):
        """Test handling content without headings."""
        content = "This is just plain text without any headings. It has multiple sentences."
        chunker = MarkdownChunker()
        chunks = chunker.chunk(content)

        assert len(chunks) >= 1
        assert chunks[0].content.strip() == content.strip()

    def test_chunk_updates_heading_path_correctly(self):
        """Test heading path updates with nested headings."""
        content = """# Level 1

## Level 2

### Level 3

Back to level 2 content.

## Another Level 2

Content here.
"""
        chunker = MarkdownChunker()
        chunks = chunker.chunk(content)

        # Find chunks with section_path
        paths = [c.metadata.get("section_path") for c in chunks if c.metadata.get("section_path")]

        # Should have various heading depths
        assert len(paths) > 0

    def test_chunk_token_counting(self):
        """Test that token counting is accurate."""
        chunker = MarkdownChunker()

        # Count tokens for known text
        text = "Hello, this is a test."
        token_count = chunker.count_tokens(text)

        assert token_count > 0
        assert token_count < len(text)  # Tokens should be fewer than characters

    def test_chunk_indices_are_sequential(self):
        """Test that chunk indices are sequential."""
        content = """# One

Content one.

# Two

Content two.

# Three

Content three.
"""
        chunker = MarkdownChunker()
        chunks = chunker.chunk(content)

        indices = [c.index for c in chunks]
        expected = list(range(len(chunks)))
        assert indices == expected

    def test_overlap_text_extraction(self):
        """Test overlap text extraction works correctly."""
        chunker = MarkdownChunker()
        chunker.chunk_overlap = 10

        text = "This is a longer piece of text that we want to extract overlap from."
        overlap = chunker._get_overlap_text(text)

        assert len(overlap) > 0
        assert text.endswith(overlap) or overlap in text


class TestOpenAPIChunker:
    """Tests for OpenAPIChunker."""

    def test_chunk_openapi_json(self, sample_openapi_content):
        """Test chunking OpenAPI JSON content."""
        chunker = OpenAPIChunker()
        chunks = chunker.chunk(sample_openapi_content)

        assert len(chunks) >= 2  # At least info + endpoints

        # Check for endpoint metadata
        endpoint_chunks = [c for c in chunks if c.metadata.get("type") == "endpoint"]
        assert len(endpoint_chunks) >= 2  # GET and POST /users

    def test_chunk_creates_info_chunk(self, sample_openapi_content):
        """Test that an info chunk is created."""
        chunker = OpenAPIChunker()
        chunks = chunker.chunk(sample_openapi_content)

        info_chunks = [c for c in chunks if c.metadata.get("type") == "api_info"]
        assert len(info_chunks) == 1
        assert "Test API" in info_chunks[0].content

    def test_chunk_extracts_endpoint_metadata(self, sample_openapi_content):
        """Test endpoint metadata extraction."""
        chunker = OpenAPIChunker()
        chunks = chunker.chunk(sample_openapi_content)

        endpoint_chunks = [c for c in chunks if c.metadata.get("type") == "endpoint"]

        # Check GET /users endpoint
        get_users = [
            c
            for c in endpoint_chunks
            if c.metadata.get("path") == "/users" and c.metadata.get("method") == "GET"
        ]
        assert len(get_users) == 1
        assert get_users[0].metadata.get("operation_id") == "listUsers"

    def test_chunk_includes_parameters(self, sample_openapi_content):
        """Test that parameters are included in chunk content."""
        chunker = OpenAPIChunker()
        chunks = chunker.chunk(sample_openapi_content)

        endpoint_chunks = [c for c in chunks if c.metadata.get("type") == "endpoint"]
        get_users = next(c for c in endpoint_chunks if c.metadata.get("method") == "GET")

        assert "Parameters" in get_users.content
        assert "page" in get_users.content

    def test_chunk_handles_invalid_json(self):
        """Test handling of invalid JSON content."""
        chunker = OpenAPIChunker()
        chunks = chunker.chunk("not valid json")

        # Should fall back to markdown chunking
        assert len(chunks) >= 1

    def test_chunk_handles_minimal_spec(self):
        """Test handling minimal OpenAPI spec."""
        minimal_spec = json.dumps(
            {
                "openapi": "3.0.0",
                "info": {"title": "Minimal", "version": "1.0"},
                "paths": {},
            }
        )
        chunker = OpenAPIChunker()
        chunks = chunker.chunk(minimal_spec)

        # Should at least have info chunk
        assert len(chunks) >= 1

    def test_chunk_respects_token_limit(self, sample_openapi_content):
        """Test that chunks don't exceed token limit."""
        chunker = OpenAPIChunker()
        chunks = chunker.chunk(sample_openapi_content)

        for chunk in chunks:
            assert chunk.token_count <= BaseChunker.MAX_TOKENS_PER_CHUNK


class TestGetChunker:
    """Tests for get_chunker factory function."""

    def test_get_markdown_chunker(self):
        """Test getting markdown chunker."""
        chunker = get_chunker("markdown")
        assert isinstance(chunker, MarkdownChunker)

    def test_get_openapi_chunker(self):
        """Test getting openapi chunker."""
        chunker = get_chunker("openapi")
        assert isinstance(chunker, OpenAPIChunker)

    def test_invalid_source_type_raises(self):
        """Test that invalid source type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_chunker("invalid_type")
        assert "Unsupported source type" in str(exc_info.value)


class TestChunkData:
    """Tests for ChunkData dataclass."""

    def test_chunk_data_creation(self):
        """Test creating ChunkData."""
        chunk = ChunkData(
            content="Test content",
            index=0,
            token_count=2,
            metadata={"heading": "Test"},
        )
        assert chunk.content == "Test content"
        assert chunk.index == 0
        assert chunk.token_count == 2
        assert chunk.metadata == {"heading": "Test"}

    def test_chunk_data_default_metadata(self):
        """Test default metadata is empty dict."""
        chunk = ChunkData(
            content="Test",
            index=0,
            token_count=1,
        )
        assert chunk.metadata == {}
