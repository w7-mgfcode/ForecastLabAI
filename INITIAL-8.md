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
