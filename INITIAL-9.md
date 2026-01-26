# INITIAL-9.md — Dashboard + RAG + Agentic Layer (PydanticAI)

## FEATURE:
- Dashboard (React + Vite + shadcn/ui Data Table):
  - Data Explorer (tables, filters, export)
  - Model Runs (leaderboard, compare)
  - Train & Predict (forms, status)
  - Predictions (tabular view)
- RAG assistant (pgvector):
  - indexed sources: README.md, /docs/*, OpenAPI export, run reports
  - retrieve top-k → answer with citations
- Optional PydanticAI:
  - agent with tools:
    - experiment orchestrator (generate configs → backtest → select best → report)
    - rag assistant (query → retrieve → structured answer)
  - enforced structured outputs

## EXAMPLES:
- `examples/ui/README.md` — page map + API mapping (no hardcoded base URL).
- `examples/rag/index_docs.py` — chunk+embed+store (Settings-driven).
- `examples/rag/query.http` — Q&A returning a citations schema.
- `examples/agent/` — best-practice agent setup (providers, tools, dependencies).

## DOCUMENTATION:
- shadcn/ui Data Table pattern + TanStack Table
- pgvector similarity search + indexing strategies
- PydanticAI docs (include link in README as a code block)

## OTHER CONSIDERATIONS:
- Required: `.env.example` for frontend (`VITE_API_BASE_URL`).
- RAG must be evidence-grounded: if no support, return “not found” (no hallucinations).
- Stable citation schema: source_type, source_id/path, chunk_id, snippet/span.
- Embedding model + dimension must come from Settings (never hardcoded).
