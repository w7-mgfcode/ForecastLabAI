# RAG Corpus Manager

## Summary

Build an Admin and Knowledge workflow for indexing, inspecting, refreshing, and deleting RAG sources. The current Knowledge page handles an empty corpus well, but the running system reported `0 sources` and `0 chunks`, which means the RAG Assistant has no evidence base despite the app having extensive `docs/`, `PRPs/`, and architecture references.

## Why It Fits ForecastLabAI

ForecastLabAI already has:

- RAG API routes in `app/features/rag/routes.py`.
- RAG service, embeddings, schemas, and tests in `app/features/rag/`.
- Knowledge page in `frontend/src/pages/knowledge.tsx`.
- Admin tabs in `frontend/src/pages/admin.tsx`.
- Runtime AI model configuration in `app/features/config/`.

This feature turns the existing RAG layer from an invisible backend capability into an operator-facing system.

## User Value

- Users can see what the assistant can cite before asking questions.
- Demo reviewers can index project docs without CLI setup.
- Failed embedding-provider health becomes visible before users attempt semantic search.
- The Knowledge page becomes a real corpus browser instead of mostly an empty-state page.

## Proposed UX

### Admin: RAG Sources Tab

Add:

- Source list with path, type, chunk count, embedding dimension, indexed timestamp, and status.
- "Index Project Docs" action for `docs/`, `PRPs/`, and selected root markdown files.
- "Index Single Document" dialog for a local path or pasted markdown.
- "Re-index stale" action when file modified time is newer than indexed time.
- "Delete source" action with confirmation.
- Provider health panel showing embedding provider, dimension, and reachability.

### Knowledge Page

Add:

- Source filters by type: docs, PRP, API, code, markdown.
- Chunk preview drawer.
- Relevance examples for semantic search.
- Empty-state action that links directly to the Admin indexing flow.

## Backend Design

Use the existing RAG slice and add only missing orchestration endpoints if needed:

- `POST /rag/index/project-docs`
- `POST /rag/index/document`
- `GET /rag/sources`
- `GET /rag/sources/{source_id}/chunks`
- `DELETE /rag/sources/{source_id}`
- `POST /rag/sources/{source_id}/reindex`

Request/response schemas should live in `app/features/rag/schemas.py`.

## Frontend Design

Likely files:

- `frontend/src/pages/admin.tsx`
- `frontend/src/pages/knowledge.tsx`
- `frontend/src/hooks/use-rag-sources.ts`
- New admin components under `frontend/src/components/admin/`

Use existing shadcn/ui components and avoid adding new UI libraries.

## Data Model Considerations

The existing RAG tables should remain the source of truth. If stale-source detection is added, store:

- `source_path`
- `source_type`
- `content_hash`
- `indexed_at`
- `embedding_provider`
- `embedding_model`
- `embedding_dimension`

If these fields already exist, reuse them instead of creating parallel metadata.

## MVP Scope

- Index bundled markdown docs from `docs/` and `PRPs/`.
- List sources and chunk counts.
- Delete a source.
- Show provider health.
- Update Knowledge empty state.

## Full Version

- Stale detection and one-click re-index.
- Chunk preview.
- Search result explainability.
- Batch indexing progress.
- Failed chunk retry.
- Corpus coverage metrics.

## Risks

- Embedding provider mismatch can break vector search if dimensions differ.
- Indexing large files may block requests unless moved to the jobs layer.
- Path handling must prevent arbitrary file reads outside approved repo paths.

## Validation Plan

- Unit tests for chunking and source metadata.
- API tests for index/list/delete/retrieve.
- Frontend tests for hooks and empty/non-empty states.
- Browser QA:
  - Admin shows empty corpus.
  - Index project docs.
  - Knowledge source list updates.
  - Semantic search returns cited chunks.
  - Delete source updates counts.

## Documentation

- FastAPI documentation: https://fastapi.tiangolo.com/
- Pydantic documentation: https://docs.pydantic.dev/latest/
- SQLAlchemy asyncio documentation: https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html
- pgvector Python documentation: https://github.com/pgvector/pgvector-python
- OpenAI embeddings guide: https://platform.openai.com/docs/guides/embeddings
- Ollama API documentation: https://github.com/ollama/ollama/blob/main/docs/api.md
- TanStack Query React documentation: https://tanstack.com/query/latest/docs/framework/react/overview
- shadcn/ui documentation: https://ui.shadcn.com/docs
- Radix UI primitives documentation: https://www.radix-ui.com/primitives/docs
- OWASP Top 10 for LLM Applications: https://owasp.org/www-project-top-10-for-large-language-model-applications/
