# PRP-9: RAG Knowledge Base ("The Memory")

**Feature**: INITIAL-9.md — RAG Knowledge Base
**Status**: Ready for Implementation
**Confidence Score**: 8.5/10

---

## Goal

Build the RAG Knowledge Base layer providing:
1. **Document ingestion** with markdown-aware and OpenAPI-aware chunking
2. **Vector storage** using PostgreSQL + pgvector for embeddings
3. **Semantic retrieval** with configurable top-k and similarity thresholds
4. **Idempotent re-indexing** via content hash comparison

This is the foundational "Memory" layer that INITIAL-10 (Agentic Layer) will consume via the `retrieve_context` tool.

---

## Why

- **Agent-Ready**: Provides `retrieve_context` tool for INITIAL-10 RAG Assistant
- **Evidence-Grounded**: Returns raw chunks with citations (no hallucination)
- **Cost-Effective**: Uses existing PostgreSQL (no new infrastructure)
- **Portfolio Value**: Demonstrates full-stack RAG implementation

---

## What

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/rag/index` | Index document (markdown/openapi) |
| `POST` | `/rag/retrieve` | Semantic search with filters |
| `GET` | `/rag/sources` | List indexed sources |
| `DELETE` | `/rag/sources/{source_id}` | Remove source and chunks |

### Success Criteria

- [ ] pgvector extension enabled via migration
- [ ] Markdown chunker respects heading boundaries
- [ ] OpenAPI chunker produces one chunk per endpoint
- [ ] Async batch embedding with OpenAI API
- [ ] HNSW index for sub-100ms retrieval
- [ ] Idempotent re-indexing (content_hash change detection)
- [ ] 80+ unit tests, 15+ integration tests
- [ ] All validation gates green (ruff, mypy, pyright, pytest)

---

## All Needed Context

### Documentation & References

```yaml
# CRITICAL - pgvector SQLAlchemy Integration
- url: https://github.com/pgvector/pgvector-python
  why: "Official pgvector Python library - Vector column, HNSW index, cosine_distance"

- url: https://github.com/pgvector/pgvector-python/blob/master/README.md
  why: "SQLAlchemy 2.0 patterns, Index creation with postgresql_ops"

# pgvector Indexing
- url: https://neon.com/blog/understanding-vector-search-and-hnsw-index-with-pgvector
  why: "HNSW vs IVFFlat tradeoffs, index tuning parameters"

# OpenAI Embeddings
- url: https://platform.openai.com/docs/api-reference/embeddings
  why: "Embeddings API reference - batch processing, input limits (8192 tokens)"

- url: https://platform.openai.com/docs/guides/embeddings
  why: "Best practices, token counting with tiktoken cl100k_base"

# Markdown Chunking
- url: https://python.langchain.com/docs/how_to/markdown_header_metadata_splitter/
  why: "MarkdownHeaderTextSplitter pattern for heading-aware splitting"

# Codebase Patterns (CRITICAL)
- file: app/features/registry/models.py
  why: "ORM pattern with JSONB, TimestampMixin, Index creation"

- file: app/features/registry/schemas.py
  why: "Pydantic v2 patterns - ConfigDict, field_validator, from_attributes"

- file: app/features/registry/routes.py
  why: "FastAPI patterns - APIRouter, response_model, HTTPException"

- file: app/features/registry/service.py
  why: "Async service pattern - get_settings(), structured logging"

- file: app/features/registry/tests/conftest.py
  why: "Test fixtures - db_session, client, cleanup patterns"

# ADR
- file: docs/ADR/ADR-0003-vector-storage-pgvector-in-postgres.md
  why: "Architectural decision for pgvector over dedicated vector DB"
```

### Current Codebase Tree (Relevant Parts)

```
app/
├── core/
│   ├── config.py          # Settings singleton - ADD RAG settings here
│   ├── database.py         # Base, get_db, get_engine
│   ├── logging.py          # get_logger, structured logging
│   └── exceptions.py       # ForecastLabError base class
├── shared/
│   └── models.py           # TimestampMixin
├── features/
│   ├── registry/           # REFERENCE: Follow this pattern exactly
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── routes.py
│   │   ├── service.py
│   │   ├── storage.py
│   │   └── tests/
│   └── rag/                # NEW: Create this vertical slice
├── main.py                  # Include rag router here
docker-compose.yml           # Already uses pgvector/pgvector:pg16
alembic/versions/            # Add migration for pgvector extension + tables
```

### Desired Codebase Tree (Files to Create)

```
app/features/rag/
├── __init__.py              # Export router
├── models.py                # DocumentSource, DocumentChunk ORM models
├── schemas.py               # IndexRequest/Response, RetrieveRequest/Response, etc.
├── routes.py                # FastAPI router with /rag/* endpoints
├── service.py               # RAGService - indexing and retrieval logic
├── chunkers.py              # MarkdownChunker, OpenAPIChunker classes
├── embeddings.py            # EmbeddingService - async OpenAI API calls
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # db_session, client fixtures
│   ├── test_schemas.py      # Schema validation tests
│   ├── test_chunkers.py     # Chunking logic tests (unit, no DB)
│   ├── test_embeddings.py   # Embedding tests with mocked API
│   ├── test_service.py      # Service tests (unit + integration)
│   └── test_routes.py       # Route integration tests

alembic/versions/
└── xxxx_create_rag_tables.py  # Migration with CREATE EXTENSION vector

examples/rag/
├── index_docs.py            # Example: index docs/ directory
└── query.http               # HTTP client examples
```

### Known Gotchas & Library Quirks

```python
# CRITICAL: pgvector SQLAlchemy requires explicit import
from pgvector.sqlalchemy import Vector  # NOT from sqlalchemy

# CRITICAL: HNSW index requires vector_cosine_ops for cosine distance
Index(
    "ix_embedding_hnsw",
    DocumentChunk.embedding,
    postgresql_using="hnsw",
    postgresql_with={"m": 16, "ef_construction": 64},
    postgresql_ops={"embedding": "vector_cosine_ops"},  # MUST match query distance
)

# CRITICAL: Cosine distance query uses cosine_distance method
from pgvector.sqlalchemy import Vector
stmt = select(DocumentChunk).order_by(
    DocumentChunk.embedding.cosine_distance(query_embedding)  # NOT <=> operator
).limit(top_k)

# CRITICAL: OpenAI embeddings input limit is 8192 tokens per text
# Use tiktoken to count tokens before sending to API
import tiktoken
enc = tiktoken.get_encoding("cl100k_base")
tokens = enc.encode(text)
if len(tokens) > 8191:
    # Truncate or split

# CRITICAL: OpenAI API returns embeddings in same order as input
# But batch requests should be <= 2048 inputs per call

# CRITICAL: Pydantic v2 uses ConfigDict, not class Config
from pydantic import BaseModel, ConfigDict
class MySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

# CRITICAL: SQLAlchemy 2.0 uses Mapped[] and mapped_column()
from sqlalchemy.orm import Mapped, mapped_column
embedding = mapped_column(Vector(1536))  # Vector column

# CRITICAL: Alembic migration needs op.execute for CREATE EXTENSION
op.execute("CREATE EXTENSION IF NOT EXISTS vector")
```

---

## Implementation Blueprint

### Data Models

#### ORM Models (models.py)

```python
"""RAG knowledge base ORM models."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import (
    DateTime, Index, Integer, String, Text, UniqueConstraint, ForeignKey,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from app.core.database import Base
from app.shared.models import TimestampMixin


class DocumentSource(TimestampMixin, Base):
    """Registered document source for indexing."""
    __tablename__ = "document_source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)  # markdown, openapi
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationship
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("source_type", "source_path", name="uq_source_type_path"),
    )


class DocumentChunk(TimestampMixin, Base):
    """Indexed document chunk with embedding."""
    __tablename__ = "document_chunk"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("document_source.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(1536), nullable=True)  # Dimension from settings
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationship
    source: Mapped[DocumentSource] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("source_id", "chunk_index", name="uq_source_chunk_index"),
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunk_metadata_gin", "metadata", postgresql_using="gin"),
    )
```

#### Pydantic Schemas (schemas.py)

```python
"""Pydantic schemas for RAG API contracts."""
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class IndexRequest(BaseModel):
    """Request to index a document."""
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["markdown", "openapi"] = Field(
        ..., description="Type of document to index"
    )
    source_path: str = Field(..., min_length=1, max_length=500)
    content: str | None = Field(None, description="Optional content override")
    metadata: dict[str, Any] | None = Field(None, description="Custom metadata")


class IndexResponse(BaseModel):
    """Response from indexing operation."""
    model_config = ConfigDict(from_attributes=True)

    source_id: str
    source_path: str
    chunks_created: int
    tokens_processed: int
    duration_ms: float
    status: Literal["indexed", "updated", "unchanged"]


class RetrieveRequest(BaseModel):
    """Request for semantic search."""
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    filters: dict[str, Any] | None = Field(None, description="Metadata filters")


class ChunkResult(BaseModel):
    """Single chunk in retrieval results."""
    model_config = ConfigDict(from_attributes=True)

    chunk_id: str
    source_id: str
    source_path: str
    source_type: str
    content: str
    relevance_score: float
    metadata: dict[str, Any] | None = None


class RetrieveResponse(BaseModel):
    """Response from retrieval operation."""
    results: list[ChunkResult]
    query_embedding_time_ms: float
    search_time_ms: float
    total_chunks_searched: int


class SourceResponse(BaseModel):
    """Source details response."""
    model_config = ConfigDict(from_attributes=True)

    source_id: str
    source_type: str
    source_path: str
    chunk_count: int
    content_hash: str
    indexed_at: datetime
    metadata: dict[str, Any] | None = None


class SourceListResponse(BaseModel):
    """List of indexed sources."""
    sources: list[SourceResponse]
    total_sources: int
    total_chunks: int


class DeleteResponse(BaseModel):
    """Response from delete operation."""
    source_id: str
    chunks_deleted: int
    status: Literal["deleted"]
```

---

## Task List

### Task 1: Add Dependencies to pyproject.toml

```yaml
MODIFY: pyproject.toml
ADD to dependencies:
  - "pgvector>=0.3.0"      # pgvector SQLAlchemy support
  - "openai>=1.40.0"       # OpenAI API client (async)
  - "tiktoken>=0.7.0"      # Token counting for chunk size
  - "httpx>=0.28.0"        # Already in dev, may need in main for async HTTP
```

### Task 2: Add RAG Settings to config.py

```yaml
MODIFY: app/core/config.py
ADD after "jobs_retention_days" (~line 65):
  # RAG Embedding Configuration
  rag_embedding_model: str = "text-embedding-3-small"
  rag_embedding_dimension: int = 1536
  rag_embedding_batch_size: int = 100
  openai_api_key: str = ""  # Required for embeddings

  # RAG Chunking Configuration
  rag_chunk_size: int = 512  # tokens
  rag_chunk_overlap: int = 50  # tokens
  rag_min_chunk_size: int = 100

  # RAG Retrieval Configuration
  rag_top_k: int = 5
  rag_similarity_threshold: float = 0.7
  rag_max_context_tokens: int = 4000

  # RAG Index Configuration
  rag_index_type: Literal["hnsw", "ivfflat"] = "hnsw"
  rag_hnsw_m: int = 16
  rag_hnsw_ef_construction: int = 64
```

### Task 3: Create Alembic Migration

```yaml
CREATE: alembic/versions/xxxx_create_rag_tables.py
PATTERN: Follow app/features/registry migration pattern

Pseudocode:
def upgrade():
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create document_source table
    op.create_table("document_source", ...)

    # Create document_chunk table with Vector column
    op.create_table("document_chunk",
        sa.Column("embedding", Vector(1536), nullable=True),
        ...
    )

    # Create HNSW index
    op.create_index(
        "ix_chunk_embedding_hnsw",
        "document_chunk",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
```

### Task 4: Create ORM Models

```yaml
CREATE: app/features/rag/models.py
MIRROR: app/features/registry/models.py pattern
CRITICAL:
  - Use pgvector.sqlalchemy.Vector for embedding column
  - Add HNSW index in __table_args__
  - Use TimestampMixin
  - Cascade delete from source to chunks
```

### Task 5: Create Pydantic Schemas

```yaml
CREATE: app/features/rag/schemas.py
MIRROR: app/features/registry/schemas.py pattern
INCLUDE:
  - IndexRequest, IndexResponse
  - RetrieveRequest, RetrieveResponse, ChunkResult
  - SourceResponse, SourceListResponse
  - DeleteResponse
```

### Task 6: Create Chunker Classes

```yaml
CREATE: app/features/rag/chunkers.py

Classes:
  BaseChunker (ABC):
    - chunk(content: str) -> list[ChunkData]

  MarkdownChunker(BaseChunker):
    - Split on heading boundaries (# ## ###)
    - Respect chunk_size and chunk_overlap from settings
    - Extract heading hierarchy for metadata
    - Use tiktoken cl100k_base for token counting

  OpenAPIChunker(BaseChunker):
    - Parse OpenAPI JSON/YAML
    - One chunk per endpoint (path + method)
    - Include operation summary, description, parameters

CRITICAL:
  - Use tiktoken for token counting (cl100k_base encoding)
  - Never exceed 8191 tokens per chunk (OpenAI limit)
```

### Task 7: Create Embedding Service

```yaml
CREATE: app/features/rag/embeddings.py

Class EmbeddingService:
  __init__(self):
    - Load settings (api_key, model, dimension, batch_size)
    - Initialize AsyncOpenAI client

  async def embed_texts(self, texts: list[str]) -> list[list[float]]:
    - Batch texts into groups of batch_size
    - Call OpenAI embeddings API for each batch
    - Handle rate limits with exponential backoff
    - Return embeddings in same order as input

  async def embed_query(self, query: str) -> list[float]:
    - Single text embedding for retrieval queries

CRITICAL:
  - Use openai.AsyncOpenAI for async calls
  - Validate token count before API call
  - Log token usage for cost tracking
```

### Task 8: Create RAG Service

```yaml
CREATE: app/features/rag/service.py
MIRROR: app/features/registry/service.py pattern

Class RAGService:
  async def index_document(self, db, request: IndexRequest) -> IndexResponse:
    - Read content from source_path (or use provided content)
    - Compute SHA-256 content hash
    - Check if source exists with same hash (skip if unchanged)
    - Chunk content using appropriate chunker
    - Generate embeddings for all chunks
    - Upsert source record
    - Delete old chunks, insert new chunks
    - Return IndexResponse with stats

  async def retrieve(self, db, request: RetrieveRequest) -> RetrieveResponse:
    - Generate query embedding
    - Build pgvector similarity query with cosine_distance
    - Apply metadata filters if provided
    - Execute query, compute relevance scores
    - Return top-k results above threshold

  async def list_sources(self, db) -> SourceListResponse:
    - Query all sources with chunk counts
    - Return paginated list

  async def delete_source(self, db, source_id: str) -> DeleteResponse:
    - Find source by source_id
    - Delete (cascades to chunks)
    - Return delete count

CRITICAL:
  - Use cosine_distance for similarity (NOT l2_distance)
  - Relevance score = 1 - cosine_distance (normalized to 0-1)
  - Handle source not found with 404
```

### Task 9: Create FastAPI Routes

```yaml
CREATE: app/features/rag/routes.py
MIRROR: app/features/registry/routes.py pattern

Routes:
  POST /rag/index -> IndexResponse (201 CREATED)
  POST /rag/retrieve -> RetrieveResponse (200 OK)
  GET /rag/sources -> SourceListResponse (200 OK)
  DELETE /rag/sources/{source_id} -> DeleteResponse (200 OK)

CRITICAL:
  - Use structured logging with rag.* event prefix
  - Handle OpenAI API errors gracefully
  - Validate source_id format
```

### Task 10: Register Router in main.py

```yaml
MODIFY: app/main.py
ADD import: from app.features.rag.routes import router as rag_router
ADD router: app.include_router(rag_router)
```

### Task 11: Create Test Fixtures

```yaml
CREATE: app/features/rag/tests/conftest.py
MIRROR: app/features/registry/tests/conftest.py

Fixtures:
  - db_session: Async session with cleanup (delete test-* sources)
  - client: AsyncClient with db override
  - sample_markdown_content: Test markdown with headings
  - sample_openapi_content: Test OpenAPI spec
  - mock_embedding_service: Mocked EmbeddingService for unit tests
```

### Task 12: Create Unit Tests

```yaml
CREATE: app/features/rag/tests/test_schemas.py
  - Test IndexRequest validation
  - Test RetrieveRequest validation (query length, threshold bounds)

CREATE: app/features/rag/tests/test_chunkers.py
  - Test MarkdownChunker respects heading boundaries
  - Test MarkdownChunker respects chunk_size
  - Test MarkdownChunker extracts heading metadata
  - Test OpenAPIChunker creates one chunk per endpoint
  - Test chunk token counts are within limits

CREATE: app/features/rag/tests/test_embeddings.py
  - Test embed_texts batching logic
  - Test embed_query returns correct dimension
  - Mock OpenAI API responses

CREATE: app/features/rag/tests/test_service.py (unit)
  - Test content hash computation
  - Test idempotent re-indexing logic
  - Test relevance score normalization
```

### Task 13: Create Integration Tests

```yaml
CREATE: app/features/rag/tests/test_routes.py
@pytest.mark.integration tests:
  - test_index_markdown_creates_chunks
  - test_index_same_content_returns_unchanged
  - test_index_updated_content_re_indexes
  - test_retrieve_returns_relevant_chunks
  - test_retrieve_respects_threshold
  - test_list_sources_returns_all
  - test_delete_source_removes_chunks
  - test_delete_nonexistent_returns_404
```

### Task 14: Create Examples

```yaml
CREATE: examples/rag/index_docs.py
  - Script to index docs/ directory

CREATE: examples/rag/query.http
  - HTTP client examples for all endpoints
```

### Task 15: Update .env.example

```yaml
MODIFY: .env.example
ADD:
  # RAG Configuration
  OPENAI_API_KEY=sk-...
  RAG_EMBEDDING_MODEL=text-embedding-3-small
  RAG_CHUNK_SIZE=512
  RAG_TOP_K=5
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run FIRST - fix any errors before proceeding
uv run ruff check app/features/rag/ --fix
uv run ruff format app/features/rag/

# Expected: No errors
```

### Level 2: Type Checking

```bash
# MUST be green
uv run mypy app/features/rag/
uv run pyright app/features/rag/

# Expected: 0 errors on both
```

### Level 3: Unit Tests

```bash
# No database required
uv run pytest app/features/rag/tests/ -v -m "not integration"

# Expected: All pass
# If failing: Read error, fix code, re-run
```

### Level 4: Integration Tests

```bash
# Requires PostgreSQL running
docker-compose up -d

# Run migrations
uv run alembic upgrade head

# Run integration tests
uv run pytest app/features/rag/tests/ -v -m integration

# Expected: All pass
```

### Level 5: Manual Smoke Test

```bash
# Start API
uv run uvicorn app.main:app --reload --port 8123

# Index a document
curl -X POST http://localhost:8123/rag/index \
  -H "Content-Type: application/json" \
  -d '{"source_type": "markdown", "source_path": "README.md"}'

# Expected: {"source_id": "...", "chunks_created": N, ...}

# Retrieve
curl -X POST http://localhost:8123/rag/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "What is ForecastLabAI?", "top_k": 3}'

# Expected: {"results": [...], ...}

# List sources
curl http://localhost:8123/rag/sources

# Delete source
curl -X DELETE http://localhost:8123/rag/sources/{source_id}
```

---

## Final Validation Checklist

- [ ] All tests pass: `uv run pytest app/features/rag/tests/ -v`
- [ ] No linting errors: `uv run ruff check app/features/rag/`
- [ ] No type errors: `uv run mypy app/features/rag/ && uv run pyright app/features/rag/`
- [ ] Migration applies cleanly: `uv run alembic upgrade head`
- [ ] Manual smoke test successful
- [ ] Structured logging events follow `rag.*` prefix
- [ ] Content hash prevents duplicate embeddings
- [ ] HNSW index used for similarity queries

---

## Anti-Patterns to Avoid

- ❌ Don't use `l2_distance` when you want cosine similarity
- ❌ Don't forget to enable pgvector extension in migration
- ❌ Don't exceed 8191 tokens per embedding input
- ❌ Don't use sync OpenAI client - use AsyncOpenAI
- ❌ Don't hardcode embedding dimensions - use settings
- ❌ Don't catch all exceptions - be specific
- ❌ Don't skip content hash comparison (wastes API calls)
- ❌ Don't create new patterns when registry patterns work

---

## Confidence Score: 8.5/10

**Strengths:**
- Docker already has pgvector image
- Clear patterns from registry module to follow
- Comprehensive documentation available
- ADR decision already made

**Risks:**
- OpenAI API rate limits during bulk indexing
- HNSW index creation on large datasets may be slow
- tiktoken token counting edge cases

**Mitigations:**
- Implement exponential backoff for API calls
- Create index after initial data load
- Extensive unit tests for chunking edge cases
