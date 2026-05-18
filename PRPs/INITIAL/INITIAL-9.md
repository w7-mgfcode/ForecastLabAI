# INITIAL-9.md — RAG Knowledge Base (The Memory)

## Architectural Role

**"The Memory"** - Vector storage, document ingestion, and semantic retrieval infrastructure.

This phase provides the foundational knowledge layer that enables:
- Indexed documentation and run reports for AI-assisted search
- Semantic retrieval with relevance scoring
- Evidence-grounded context for the Agentic Layer (INITIAL-10)

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Vector Store | PostgreSQL 16 + [pgvector](https://github.com/pgvector/pgvector) | Similarity search |
| Embeddings | [OpenAI text-embedding-3-small](https://platform.openai.com/docs/models/text-embedding-3-small) | 1536-dim vectors (configurable) |
| Chunking | Markdown-aware, OpenAPI endpoint-aware | Semantic boundaries |
| Index Type | HNSW (default) or IVFFlat | Approximate nearest neighbor |

---

## FEATURE

### Database Layer
- `document_chunk` table with vector column (`embedding VECTOR(1536)`)
- HNSW index for cosine similarity search
- Unique constraint `(source_id, chunk_index)` for idempotent re-indexing
- Metadata JSONB for source type, heading hierarchy, timestamps

### Ingestion Pipeline
- **Markdown Chunker**: Heading-aware splitting (configurable size/overlap)
- **OpenAPI Chunker**: Endpoint-based granularity (one chunk per operation)
- **Embedding Service**: Async batch processing with rate limiting
- **Source Registry**: Track indexed sources with version/hash for change detection

### Retrieval Engine
- Top-k semantic search with configurable similarity threshold
- Metadata filtering (source_type, date_range, tags)
- Relevance score normalization (0.0 - 1.0)
- Context window assembly for downstream consumption

---

## ENDPOINTS

### POST /rag/index
Index documents from various sources.

**Request**:
```json
{
  "source_type": "markdown",
  "source_path": "docs/ARCHITECTURE.md",
  "metadata": {
    "category": "documentation",
    "version": "1.0.0"
  }
}
```

**Response**:
```json
{
  "source_id": "src_abc123",
  "chunks_created": 15,
  "tokens_processed": 4250,
  "duration_ms": 1234.56,
  "status": "indexed"
}
```

### POST /rag/retrieve
Semantic search across indexed documents.

**Request**:
```json
{
  "query": "How does backtesting prevent data leakage?",
  "top_k": 5,
  "similarity_threshold": 0.7,
  "filters": {
    "source_type": ["markdown", "openapi"],
    "category": "documentation"
  }
}
```

**Response**:
```json
{
  "results": [
    {
      "chunk_id": "chunk_xyz789",
      "source_id": "src_abc123",
      "source_path": "docs/PHASE/5-BACKTESTING.md",
      "content": "TimeSeriesSplitter uses time-based splits (expanding/sliding window) to prevent leakage...",
      "relevance_score": 0.92,
      "metadata": {
        "heading": "Leakage Prevention",
        "section_path": ["Phase 5: Backtesting", "Implementation", "Leakage Prevention"]
      }
    }
  ],
  "query_embedding_time_ms": 45.2,
  "search_time_ms": 12.8,
  "total_chunks_searched": 1250
}
```

### GET /rag/sources
List all indexed sources with metadata.

**Response**:
```json
{
  "sources": [
    {
      "source_id": "src_abc123",
      "source_type": "markdown",
      "source_path": "docs/ARCHITECTURE.md",
      "chunk_count": 15,
      "indexed_at": "2026-02-01T10:30:00Z",
      "content_hash": "sha256:abc123..."
    }
  ],
  "total_sources": 12,
  "total_chunks": 450
}
```

### DELETE /rag/sources/{source_id}
Remove an indexed source and all its chunks.

**Response**:
```json
{
  "source_id": "src_abc123",
  "chunks_deleted": 15,
  "status": "deleted"
}
```

---

## DATABASE SCHEMA

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Document source registry
CREATE TABLE document_source (
    source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type VARCHAR(50) NOT NULL,  -- 'markdown', 'openapi', 'run_report'
    source_path TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,  -- SHA-256 for change detection
    metadata JSONB DEFAULT '{}',
    indexed_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (source_type, source_path)
);

-- Document chunks with embeddings
CREATE TABLE document_chunk (
    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES document_source(source_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1536),  -- Configurable dimension
    token_count INTEGER NOT NULL,
    metadata JSONB DEFAULT '{}',  -- heading, section_path, etc.
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (source_id, chunk_index)
);

-- HNSW index for cosine similarity
CREATE INDEX idx_chunk_embedding_hnsw
ON document_chunk
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Metadata filtering index
CREATE INDEX idx_chunk_metadata ON document_chunk USING gin (metadata);
```

---

## EXAMPLES

### examples/rag/index_docs.py
```python
"""Index documentation into RAG knowledge base."""
import asyncio
from pathlib import Path
import httpx

async def index_markdown_docs():
    """Index all markdown docs from docs/ directory."""
    async with httpx.AsyncClient(base_url="http://localhost:8123") as client:
        docs_dir = Path("docs")
        for md_file in docs_dir.rglob("*.md"):
            response = await client.post(
                "/rag/index",
                json={
                    "source_type": "markdown",
                    "source_path": str(md_file),
                    "metadata": {"category": "documentation"}
                }
            )
            result = response.json()
            print(f"Indexed {md_file}: {result['chunks_created']} chunks")

if __name__ == "__main__":
    asyncio.run(index_markdown_docs())
```

### examples/rag/query.http
```http
### Semantic search query
POST http://localhost:8123/rag/retrieve
Content-Type: application/json

{
  "query": "How do I configure backtesting splits?",
  "top_k": 5,
  "similarity_threshold": 0.7
}

### List all indexed sources
GET http://localhost:8123/rag/sources

### Re-index after documentation update
POST http://localhost:8123/rag/index
Content-Type: application/json

{
  "source_type": "markdown",
  "source_path": "README.md",
  "metadata": {"category": "overview"}
}
```

---

## CONFIGURATION (Settings)

```python
# app/core/config.py additions

# RAG Embedding Configuration
rag_embedding_model: str = "text-embedding-3-small"
rag_embedding_dimension: int = 1536
rag_embedding_batch_size: int = 100

# RAG Chunking Configuration
rag_chunk_size: int = 512  # tokens
rag_chunk_overlap: int = 50  # tokens
rag_min_chunk_size: int = 100  # minimum tokens per chunk

# RAG Retrieval Configuration
rag_top_k: int = 5
rag_similarity_threshold: float = 0.7
rag_max_context_tokens: int = 4000

# RAG Index Configuration
rag_index_type: Literal["hnsw", "ivfflat"] = "hnsw"
rag_hnsw_m: int = 16
rag_hnsw_ef_construction: int = 64
```

---

## SUCCESS CRITERIA

- [ ] pgvector extension enabled and tested in docker-compose
- [ ] Markdown chunker respects heading boundaries
- [ ] OpenAPI chunker produces one chunk per endpoint
- [ ] Embeddings generated via async batch processing
- [ ] Retrieval returns top-k with normalized relevance scores
- [ ] Re-indexing is idempotent (content_hash change detection)
- [ ] Unique constraint prevents duplicate chunks
- [ ] HNSW index provides sub-100ms search latency
- [ ] Integration tests with real embeddings (mocked in unit tests)
- [ ] Structured logging for all index/retrieve operations

---

## CROSS-MODULE INTEGRATION

| Direction | Module | Integration Point |
|-----------|--------|-------------------|
| **→ Agentic Layer** | INITIAL-10 | Provides `retrieve_context` tool for RAG Assistant agent |
| **→ Dashboard** | INITIAL-11 | Sources list displayed in Admin panel |
| **← Registry** | Phase 6 | Run reports indexed as knowledge sources |
| **← Jobs** | Phase 7 | Indexing operations tracked as jobs |

---

## DOCUMENTATION LINKS

- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [pgvector Tutorial (DataCamp)](https://www.datacamp.com/tutorial/pgvector-tutorial)
- [OpenAI Embeddings Guide](https://platform.openai.com/docs/guides/embeddings)
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference/embeddings)
- [Neon pgvector Docs](https://neon.com/docs/extensions/pgvector)
- [HNSW Algorithm Paper](https://arxiv.org/abs/1603.09320)

---

## OTHER CONSIDERATIONS

- **Evidence-Grounded**: Retrieval returns raw chunks only; no answer generation in this layer
- **Idempotency**: Content hash comparison prevents unnecessary re-embedding
- **Rate Limiting**: Respect OpenAI API rate limits during batch embedding
- **Cost Tracking**: Log token counts for embedding cost monitoring
- **Dimension Flexibility**: Support for other embedding models (e.g., 3072-dim text-embedding-3-large)
