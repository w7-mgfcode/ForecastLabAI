# Phase 8: RAG Knowledge Base

**Date Completed**: 2026-02-01
**PRP**: PRP-9
**Status**: ✅ Completed

---

## Executive Summary

Phase 8 implements the RAG (Retrieval-Augmented Generation) Knowledge Base for ForecastLabAI with PostgreSQL pgvector for semantic similarity search, multiple embedding providers (OpenAI and Ollama), and evidence-grounded retrieval with citations.

### Objectives Achieved

1. **pgvector Integration** - HNSW index for fast cosine similarity search
2. **Embedding Provider Pattern** - Abstract base class with OpenAI and Ollama implementations
3. **Document Indexing** - Markdown and OpenAPI-aware chunking with content hash for idempotency
4. **Semantic Retrieval** - Configurable top-k retrieval with similarity threshold
5. **Source Management** - List, index, and delete document sources

---

## Deliverables

### 1. Embedding Provider Pattern

**File**: `app/features/rag/embeddings.py`

Implements abstract `EmbeddingProvider` base class with two concrete implementations:

```python
class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def embed_query(self, query: str) -> list[float]: ...

    @property
    @abstractmethod
    def dimension(self) -> int: ...
```

**Providers**:

| Provider | Endpoint | Features |
|----------|----------|----------|
| `OpenAIEmbeddingProvider` | OpenAI API | Batch processing, rate limit handling, token validation |
| `OllamaEmbeddingProvider` | `/v1/embeddings` | OpenAI-compatible, configurable dimensions, local/LAN |

**Factory Function**:

```python
def get_embedding_service() -> EmbeddingProvider:
    """Returns provider based on RAG_EMBEDDING_PROVIDER config."""
    settings = get_settings()
    if settings.rag_embedding_provider == "ollama":
        return OllamaEmbeddingProvider()
    return OpenAIEmbeddingProvider()
```

### 2. Document Chunking

**File**: `app/features/rag/chunkers.py`

| Chunker | Source Type | Strategy |
|---------|-------------|----------|
| `MarkdownChunker` | `markdown` | Respects heading boundaries, extracts heading hierarchy metadata |
| `OpenAPIChunker` | `openapi` | Chunks by endpoint, extracts method/path/parameters metadata |

**ChunkData Structure**:

```python
@dataclass
class ChunkData:
    content: str              # Chunk text
    token_count: int          # Token count for the chunk
    chunk_index: int          # Position in source document
    metadata: dict | None     # Heading path, endpoint info, etc.
```

### 3. RAG Service

**File**: `app/features/rag/service.py`

| Method | Description |
|--------|-------------|
| `index_document()` | Index document with chunking and embedding |
| `retrieve()` | Semantic search with similarity scoring |
| `list_sources()` | List indexed sources with statistics |
| `delete_source()` | Delete source and its chunks |

**Idempotent Indexing**:
- SHA-256 content hash for change detection
- Returns `"unchanged"` status if content matches existing source
- Re-indexes only when content changes

### 4. ORM Models

**File**: `app/features/rag/models.py`

```python
class DocumentSource(TimestampMixin, Base):
    """Registry of indexed document sources."""
    __tablename__ = "document_source"

    id: Mapped[int]
    source_id: Mapped[str]      # UUID hex (32 chars)
    source_type: Mapped[str]    # markdown, openapi
    source_path: Mapped[str]    # File path or identifier
    content_hash: Mapped[str]   # SHA-256 for change detection
    metadata_: Mapped[dict]     # JSONB custom metadata
    indexed_at: Mapped[datetime]


class DocumentChunk(TimestampMixin, Base):
    """Indexed document chunk with embedding."""
    __tablename__ = "document_chunk"

    id: Mapped[int]
    chunk_id: Mapped[str]       # UUID hex (32 chars)
    source_id: Mapped[int]      # FK to document_source
    chunk_index: Mapped[int]    # Position in document
    content: Mapped[str]        # Chunk text
    embedding: Mapped[list[float]]  # Vector(dimension)
    token_count: Mapped[int]
    metadata_: Mapped[dict]     # Heading hierarchy, etc.
```

### 5. API Endpoints

**File**: `app/features/rag/routes.py`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/rag/index` | Index a document into the knowledge base |
| POST | `/rag/retrieve` | Semantic search across indexed documents |
| GET | `/rag/sources` | List all indexed sources |
| DELETE | `/rag/sources/{source_id}` | Delete source and its chunks |

---

## Configuration

### New Settings in `app/core/config.py`

```python
# Embedding Provider
rag_embedding_provider: Literal["openai", "ollama"] = "openai"

# OpenAI Configuration
openai_api_key: str = ""
rag_embedding_model: str = "text-embedding-3-small"

# Ollama Configuration
ollama_base_url: str = "http://localhost:11434"
ollama_embedding_model: str = "nomic-embed-text"

# Common Embedding Settings
rag_embedding_dimension: int = 1536
rag_embedding_batch_size: int = 100

# Chunking Configuration
rag_chunk_size: int = 512         # tokens
rag_chunk_overlap: int = 50       # tokens
rag_min_chunk_size: int = 100     # minimum tokens per chunk

# Retrieval Configuration
rag_top_k: int = 5
rag_similarity_threshold: float = 0.7
rag_max_context_tokens: int = 4000

# Index Configuration
rag_index_type: Literal["hnsw", "ivfflat"] = "hnsw"
rag_hnsw_m: int = 16
rag_hnsw_ef_construction: int = 64
```

### Environment Variables

**OpenAI Provider (default)**:
```bash
RAG_EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-your-key
RAG_EMBEDDING_MODEL=text-embedding-3-small
RAG_EMBEDDING_DIMENSION=1536
```

**Ollama Provider (local/LAN)**:
```bash
RAG_EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
RAG_EMBEDDING_DIMENSION=768
```

---

## Database Changes

### Migration: `b4c8d9e0f123_create_rag_tables.py`

Creates base RAG tables with pgvector:

**Tables**:
- `document_source` - Source registry with content hash
- `document_chunk` - Chunks with vector embeddings

**Indexes**:
- `ix_document_source_source_id` (unique)
- `ix_document_source_source_type`
- `ix_document_chunk_chunk_id` (unique)
- `ix_document_chunk_source_id`
- `ix_chunk_embedding_hnsw` - HNSW index for cosine similarity
- `ix_chunk_metadata_gin` - GIN index for metadata filtering

### Migration: `c5d9e1f2g345_rag_dynamic_embedding_dimension.py`

Enables configurable embedding dimension:

```python
def upgrade() -> None:
    dimension = int(os.environ.get("RAG_EMBEDDING_DIMENSION", "1536"))
    op.drop_index("ix_chunk_embedding_hnsw")
    op.execute(f"ALTER TABLE document_chunk ALTER COLUMN embedding TYPE vector({dimension})")
    op.create_index("ix_chunk_embedding_hnsw", ...)
```

**Note**: Changing dimension requires re-indexing all documents.

---

## Integration

### Router Registration in `app/main.py`

```python
from app.features.rag.routes import router as rag_router

# In create_app():
app.include_router(rag_router)
```

### Alembic Model Import in `alembic/env.py`

```python
from app.features.rag import models as rag_models  # noqa: F401
```

---

## Test Coverage

### Test Files

| File | Tests | Description |
|------|-------|-------------|
| `test_embeddings.py` | 25 | Provider pattern, OpenAI, Ollama, factory |
| `test_chunkers.py` | 22 | Markdown and OpenAPI chunking |
| `test_schemas.py` | 22 | Request/response validation |
| `test_service.py` | 12 | Service unit tests |
| `test_routes.py` | 14 | Integration tests (require DB) |

### Validation Results

```
Ruff:    All checks passed
MyPy:    0 errors (117 source files)
Pyright: 0 errors
Pytest:  82 unit tests passed + 14 integration tests
```

---

## Directory Structure

```
app/
├── core/
│   └── config.py              # MODIFIED: Added RAG and Ollama settings
├── features/
│   └── rag/                   # NEW: RAG Knowledge Base
│       ├── __init__.py
│       ├── models.py          # DocumentSource, DocumentChunk ORM
│       ├── schemas.py         # Request/response Pydantic schemas
│       ├── embeddings.py      # EmbeddingProvider, OpenAI, Ollama
│       ├── chunkers.py        # MarkdownChunker, OpenAPIChunker
│       ├── service.py         # RAGService
│       ├── routes.py          # API endpoints
│       └── tests/
│           ├── __init__.py
│           ├── conftest.py
│           ├── test_embeddings.py
│           ├── test_chunkers.py
│           ├── test_schemas.py
│           ├── test_service.py
│           └── test_routes.py
└── main.py                    # MODIFIED: Router registration

alembic/
├── env.py                     # MODIFIED: RAG model import
└── versions/
    ├── b4c8d9e0f123_create_rag_tables.py         # NEW
    └── c5d9e1f2g345_rag_dynamic_embedding_dimension.py  # NEW
```

---

## API Usage Examples

### Index Documents

```bash
# Index a markdown file
curl -X POST http://localhost:8123/rag/index \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "markdown",
    "source_path": "docs/ARCHITECTURE.md"
  }'

# Index with inline content
curl -X POST http://localhost:8123/rag/index \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "markdown",
    "source_path": "inline/readme",
    "content": "# Project Overview\n\nThis is the project readme...",
    "metadata": {"category": "documentation"}
  }'

# Index OpenAPI spec
curl -X POST http://localhost:8123/rag/index \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "openapi",
    "source_path": "openapi.json"
  }'
```

### Semantic Retrieval

```bash
# Basic query
curl -X POST http://localhost:8123/rag/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How does backtesting work?"
  }'

# Query with filters
curl -X POST http://localhost:8123/rag/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "API endpoints for forecasting",
    "top_k": 10,
    "similarity_threshold": 0.8,
    "filters": {
      "source_type": "openapi"
    }
  }'
```

### Source Management

```bash
# List all sources
curl http://localhost:8123/rag/sources

# Delete a source
curl -X DELETE http://localhost:8123/rag/sources/abc123def456...
```

---

## Embedding Provider Comparison

| Feature | OpenAI | Ollama |
|---------|--------|--------|
| Endpoint | OpenAI API | `/v1/embeddings` |
| Authentication | API key required | None |
| Rate Limiting | Yes, with backoff | No |
| Token Validation | Yes (8191 max) | No |
| Batch Size | Configurable (2048 max) | Native batch support |
| Dimensions | 1536 (text-embedding-3-small) | Model-dependent |
| Network | Internet required | Local/LAN |

---

## Next Phase Preparation

Phase 9 (Agentic Layer) will build on this RAG infrastructure to:
- Create RAG Assistant Agent for evidence-grounded Q&A
- Implement citation formatting with source references
- Add WebSocket streaming for real-time responses
- Integrate with Experiment Orchestrator Agent
