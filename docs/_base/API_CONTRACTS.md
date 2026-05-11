# ForecastLabAI API Contracts
> Source: heuristic discovery from `app/main.py` router wiring and per-feature `routes.py`. Full request/response schemas live in the Pydantic models at `app/features/<slice>/schemas.py`. Swagger UI at `http://localhost:8123/docs` is the authoritative live contract.

## HTTP Endpoints

All endpoints serve JSON; error responses use `application/problem+json` (RFC 7807) via `app/core/problem_details.py`. Schemas are Pydantic v2 (`app/features/<slice>/schemas.py`).

| Slice | Method | Path | Purpose |
|-------|--------|------|---------|
| health | GET | `/health` | Liveness probe — `{"status":"ok"}` |
| ingest | POST | `/ingest/sales-daily` | Batch upsert with natural-key resolution, idempotent `ON CONFLICT DO UPDATE` |
| dimensions | GET | `/dimensions/stores` | List stores (1-indexed pagination, region/store_type filter, case-insensitive search) |
| dimensions | GET | `/dimensions/stores/{store_id}` | Get store by ID |
| dimensions | GET | `/dimensions/products` | List products (category/brand filter, sku/name search) |
| dimensions | GET | `/dimensions/products/{product_id}` | Get product by ID |
| analytics | GET | `/analytics/kpis` | Aggregated KPIs (revenue, units, transactions, avg unit price, avg basket) |
| analytics | GET | `/analytics/drilldowns` | Group-by dimension: store / product / category / region / date |
| featuresets | POST | `/featuresets/compute` | Compute time-safe features (lag/rolling/calendar, leakage-prevented) |
| featuresets | POST | `/featuresets/preview` | Preview features with sample rows |
| forecasting | POST | `/forecasting/train` | Train a model (naive / seasonal_naive / moving_average / lightgbm) |
| forecasting | POST | `/forecasting/predict` | Generate horizon predictions from a trained model |
| backtesting | POST | `/backtesting/run` | Time-series CV (rolling/expanding splits, MAE/sMAPE/WAPE/bias/stability) |
| registry | POST | `/registry/runs` | Create model run (pending) |
| registry | GET | `/registry/runs` | List with filters + pagination |
| registry | GET | `/registry/runs/{run_id}` | Run details + JSONB metrics + runtime_info |
| registry | PATCH | `/registry/runs/{run_id}` | Update status / metrics / artifact_uri |
| registry | GET | `/registry/runs/{run_id}/verify` | SHA-256 artifact integrity check |
| registry | POST | `/registry/aliases` | Create/update alias (only on `success` runs) |
| registry | GET | `/registry/aliases` | List aliases |
| registry | GET | `/registry/aliases/{alias_name}` | Get alias |
| registry | DELETE | `/registry/aliases/{alias_name}` | Delete alias |
| registry | GET | `/registry/compare/{run_id_a}/{run_id_b}` | Diff two runs |
| jobs | POST | `/jobs` | Submit `train` / `predict` / `backtest` (returns 202-style job_id) |
| jobs | GET | `/jobs` | List with filters |
| jobs | GET | `/jobs/{job_id}` | Status + result JSON |
| jobs | DELETE | `/jobs/{job_id}` | Cancel pending |
| rag | POST | `/rag/index` | Index a markdown/openapi document; idempotent via content hash |
| rag | POST | `/rag/retrieve` | Semantic search (HNSW), top-k with similarity threshold |
| rag | GET | `/rag/sources` | List indexed sources |
| rag | DELETE | `/rag/sources/{source_id}` | Delete source + cascaded chunks |
| agents | POST | `/agents/sessions` | Create session (`agent_type`: `experiment` or `rag_assistant`) |
| agents | GET | `/agents/sessions/{session_id}` | Status + message history (Postgres JSONB) |
| agents | POST | `/agents/sessions/{session_id}/chat` | Send user message; returns full response |
| agents | POST | `/agents/sessions/{session_id}/approve` | Approve/reject a pending tool call (HITL gate) |
| agents | DELETE | `/agents/sessions/{session_id}` | Close session |
| agents | WS | `/agents/stream` | Token-by-token streaming + tool-call events |
| seeder | (see `app/features/seeder/routes.py`) | `/seeder/*` | Trigger scenarios, status, customization |

## WebSocket Events (`/agents/stream`)

[UNVERIFIED — verify against `app/features/agents/websocket.py`]
- Client → server: `{"session_id": str, "message": str}`
- Server → client (streamed): token deltas, tool-call announcements, tool-call results, completion event, error frames.

## Async Events / Queues

None. Job execution is synchronous-with-async-shaped-API (per `app/features/jobs/`). No Kafka / SQS / pub-sub. Per `.claude/rules/product-vision.md`, **not a streaming system**.

## External Integrations

| Integration | Direction | Auth | Rate Limit | Fallback |
|-------------|-----------|------|------------|----------|
| OpenAI (embeddings + agent LLM) | egress HTTPS | `OPENAI_API_KEY` | provider-side | switch `RAG_EMBEDDING_PROVIDER=ollama`; switch agent model |
| Anthropic (agent LLM) | egress HTTPS | `ANTHROPIC_API_KEY` | provider-side | `AGENT_FALLBACK_MODEL` |
| Google Gemini (agent LLM, optional) | egress HTTPS | `GOOGLE_API_KEY` | provider-side | switch model |
| Ollama (local embeddings, optional) | egress HTTP LAN | none | local | switch back to OpenAI |

## Schema Change Policy

- Pre-1.0: API contracts under `/dimensions`, `/analytics`, `/ingest`, `/forecasting`, `/backtesting`, `/registry`, `/rag`, `/agents`, `/jobs` MAY change in MINOR releases. Pin the version. (See `.claude/rules/versioning.md`.)
- Every DB-touching change ships with an Alembic migration. Forward-only after merge.
- Pydantic v2 schema additions: prefer additive; breaking field renames go behind a `feat!:` or call out in PR description.
- New endpoints must register in `app/main.py` and have a route test in the slice's `tests/test_routes.py` (per `.claude/rules/test-requirements.md`).
