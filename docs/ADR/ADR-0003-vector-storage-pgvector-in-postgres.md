# ADR-0003: Vector Storage — pgvector in PostgreSQL

- Status: Accepted
- Date: 2026-01-26

## Context
The project includes a lightweight RAG assistant to answer questions about:
- repository documentation (README, docs)
- OpenAPI export
- model run reports (generated per training run)

We want the RAG layer to be:
- simple to operate locally (Docker Compose)
- easy to explain in a portfolio setting
- sufficiently performant for demo-scale corpora
- consistent with the primary datastore (PostgreSQL)

## Decision
Use **PostgreSQL + pgvector** as the only vector store for embeddings and similarity search.

- Store chunks and embeddings in Postgres.
- Perform top-k retrieval via vector similarity queries.
- Keep citation metadata (source_type, source_id/path, chunk_id, snippet/span) alongside chunks.

## Alternatives Considered
1) **Dedicated vector DB (e.g., Pinecone/Weaviate/Milvus)**
   - Pros: built for vector retrieval at scale, rich indexing options, managed operations.
   - Cons: extra infrastructure and operational complexity; less “one-command local dev”; not necessary for demo-scale scope.

2) **Postgres pgvector (selected)**
   - Pros: single datastore; easy local setup; strong portfolio story (“no extra DB”); good enough performance for moderate corpora.
   - Cons: retrieval tuning and indexing options are more limited than specialized systems at very large scale.

## Consequences
- Positive:
  - Reduced operational footprint: one DB for relational + vector workloads.
  - Simpler CI and local dev (service container + docker-compose).
- Negative / Risks:
  - At large scale, vector indexing/query performance may require careful tuning and/or a migration.
- Mitigations:
  - Design a clean retrieval interface so we can swap backends later if needed.
  - Version chunking strategy and keep embeddings metadata explicit.

## Links
- INITIAL: `INITIAL-9.md` (RAG + Agentic)
- PRP: (to be created) `docs/PRP/PRP-rag-pgvector.md`
