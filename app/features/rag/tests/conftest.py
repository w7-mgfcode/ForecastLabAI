"""Test fixtures for RAG module."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.features.rag.embeddings import EmbeddingService
from app.features.rag.models import DocumentChunk, DocumentSource
from app.features.rag.schemas import IndexRequest, RetrieveRequest
from app.main import app

# =============================================================================
# Database Fixtures for Integration Tests
# =============================================================================


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for integration tests.

    Creates tables if needed, provides a session, and cleans up test data.
    Requires PostgreSQL to be running (docker-compose up -d).
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        try:
            yield session
        finally:
            # Clean up test data (delete sources with test- prefix)
            test_source_ids = delete(DocumentSource).where(
                DocumentSource.source_path.like("test-%")
            )
            await session.execute(test_source_ids)
            await session.commit()

    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database dependency override."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# =============================================================================
# Mock Embedding Service
# =============================================================================


@pytest.fixture
def mock_embedding_service() -> EmbeddingService:
    """Create a mocked EmbeddingService for unit tests.

    Returns embeddings of correct dimension (1536) without calling OpenAI API.
    """
    service = MagicMock(spec=EmbeddingService)

    # Mock embed_texts to return deterministic embeddings
    async def mock_embed_texts(texts, **kwargs):
        # Return embedding vector of correct dimension for each text
        return [[0.1] * 1536 for _ in texts]

    # Mock embed_query to return single embedding
    async def mock_embed_query(query):
        return [0.1] * 1536

    service.embed_texts = AsyncMock(side_effect=mock_embed_texts)
    service.embed_query = AsyncMock(side_effect=mock_embed_query)
    service.count_tokens = MagicMock(side_effect=lambda text: len(text.split()))
    service.truncate_to_tokens = MagicMock(side_effect=lambda text, max_tokens: text)

    return service


# =============================================================================
# Sample Content Fixtures
# =============================================================================


@pytest.fixture
def sample_markdown_content() -> str:
    """Sample markdown content with headings for testing."""
    return """# Main Title

This is the introduction paragraph with some content.

## Section One

First section content goes here. It has multiple sentences.
This is the second sentence. And a third one.

### Subsection 1.1

Subsection content with details about the topic.

### Subsection 1.2

More subsection content here.

## Section Two

Second section with different content.

### Subsection 2.1

Final subsection content.
"""


@pytest.fixture
def sample_openapi_content() -> str:
    """Sample OpenAPI JSON content for testing."""
    return """{
  "openapi": "3.0.0",
  "info": {
    "title": "Test API",
    "version": "1.0.0",
    "description": "A test API for unit testing"
  },
  "servers": [
    {"url": "https://api.example.com", "description": "Production"}
  ],
  "paths": {
    "/users": {
      "get": {
        "operationId": "listUsers",
        "summary": "List all users",
        "description": "Returns a paginated list of users",
        "tags": ["users"],
        "parameters": [
          {
            "name": "page",
            "in": "query",
            "description": "Page number",
            "required": false
          }
        ],
        "responses": {
          "200": {"description": "Success"}
        }
      },
      "post": {
        "operationId": "createUser",
        "summary": "Create a user",
        "tags": ["users"],
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {"type": "object", "properties": {"name": {"type": "string"}}}
            }
          }
        },
        "responses": {
          "201": {"description": "Created"}
        }
      }
    }
  }
}"""


@pytest.fixture
def sample_large_markdown_content() -> str:
    """Large markdown content that exceeds chunk size for testing."""
    # Generate content that will need multiple chunks
    paragraphs = []
    for i in range(50):
        paragraphs.append(
            f"## Section {i}\n\n"
            f"This is paragraph {i} with enough content to make it substantial. "
            f"It contains multiple sentences to ensure proper chunking behavior. "
            f"The content is designed to test the chunker's ability to handle large documents. "
            f"Each section has similar structure but different section numbers.\n"
        )
    return "\n".join(paragraphs)


# =============================================================================
# Schema Fixtures
# =============================================================================


@pytest.fixture
def sample_index_request() -> IndexRequest:
    """Sample index request for testing."""
    return IndexRequest(
        source_type="markdown",
        source_path="test-document.md",
        content="# Test\n\nThis is test content.",
        metadata={"category": "testing"},
    )


@pytest.fixture
def sample_retrieve_request() -> RetrieveRequest:
    """Sample retrieve request for testing."""
    return RetrieveRequest(
        query="What is the test about?",
        top_k=5,
        similarity_threshold=0.7,
    )


# =============================================================================
# Model Fixtures
# =============================================================================


@pytest.fixture
def sample_document_source() -> DocumentSource:
    """Sample DocumentSource ORM object for testing."""
    return DocumentSource(
        source_id="test123456789012345678901234",
        source_type="markdown",
        source_path="test-sample.md",
        content_hash="a" * 64,
        metadata_={"category": "testing"},
        indexed_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_document_chunk() -> DocumentChunk:
    """Sample DocumentChunk ORM object for testing."""
    return DocumentChunk(
        chunk_id="chunk12345678901234567890123",
        source_id=1,
        chunk_index=0,
        content="Test chunk content",
        embedding=[0.1] * 1536,
        token_count=3,
        metadata_={"heading": "Test"},
    )
