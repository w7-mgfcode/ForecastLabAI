# INITIAL-8.md — FastAPI Serving Layer (Typed Contracts)

## FEATURE:
- Typed endpoints (minimum):
  - POST /ingest/sales-daily
  - POST /train
  - POST /predict
  - GET /runs (leaderboard)
  - GET /runs/{run_id}
  - GET /data/kpis + /data/drilldowns
- Pydantic v2 schemas:
  - request validation
  - response_model-enforced outputs
- OpenAPI export generation (also used as a RAG source).
- Job-Driven Orchestration:  - Asynchronous task pattern (POST returns job_id, GET polls status).
  - Standardized Job statuses: PENDING | RUNNING | COMPLETED | FAILED.
- Dimension Discovery:
  - Metadata endpoints for Store and Product catalogs (names, categories, IDs).
- Standardized API Protocols:
  - Unified filtering, sorting, and pagination schemas (Mixin pattern).
  - Semantic Error responses with domain-specific error codes (RFC 7807).
- AI-Enhanced Documentation:
  - Rich OpenAPI metadata optimized for LLM tool-calling and RAG indexing.
- Agent-First API Design:
  - Rich OpenAPI metadata (Pydantic Field descriptions) for RAG indexing.
  - Discovery endpoints for Store/Product metadata resolution.
- Asynchronous Task Protocol:
  - Unified Job Status API (job_id tracking) for long-running ForecastOps.
- Robust Error Handling:
  - Semantic error codes (RFC 7807) to enable Agent-led troubleshooting.
- Scalable Data Access:
  - Standardized Pagination and Filtering mixins for consistent tool-calling.

## EXAMPLES:
- `examples/api/train.http`
- `examples/api/predict.http`
- `examples/api/runs.http`
- `examples/api/kpis.http`
- `examples/api/openapi_export.sh` — produces an OpenAPI export artifact.

## DOCUMENTATION:
- FastAPI response_model filtering + error handling
- Pagination/filtering conventions

## OTHER CONSIDERATIONS:
- Job orchestration can be synchronous in Phase-0, but contracts should be async-ready (job_id + status endpoint).
- Provide a consistent error schema + request_id logging.
