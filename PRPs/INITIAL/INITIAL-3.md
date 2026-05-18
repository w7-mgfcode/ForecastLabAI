# INITIAL-3.md — Ingest Layer (Idempotent Upserts)

## FEATURE:
- Typed ingest endpoints:
  - batch upsert `/ingest/sales-daily`
  - optional `/ingest/transactions`
- Idempotency:
  - natural keys + ON CONFLICT upserts
  - replay-safe (no duplicates)
- Validation:
  - qty >= 0, date parsing, required fields
  - max batch size / chunking driven by Settings

## EXAMPLES:
- `examples/api/ingest_sales_daily.http` — uses variables (API_BASE_URL), no hardcoded URLs.
- `examples/api/ingest_sales_txn.http` — optional high-volume payload example.
- `examples/seed/payload_export.py` — exports seed data into API-compatible JSON payloads.

## DOCUMENTATION:
- FastAPI request models + validation patterns
- Postgres upsert (ON CONFLICT) + uniqueness constraints

## OTHER CONSIDERATIONS:
- Logging: inserted/updated counts + dedupe stats.
- Batch sizing/timeouts must be configurable.
- Provide a consistent error schema (problem+details).
