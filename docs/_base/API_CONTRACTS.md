# ForecastLabAI API Contracts
> Source: heuristic discovery from `app/main.py` router wiring and per-feature `routes.py`. Full request/response schemas live in the Pydantic models at `app/features/<slice>/schemas.py`. Swagger UI at `http://localhost:8123/docs` is the authoritative live contract.

## HTTP Endpoints

All endpoints serve JSON; error responses use `application/problem+json` (RFC 7807) via `app/core/problem_details.py`. Schemas are Pydantic v2 (`app/features/<slice>/schemas.py`).

| Slice | Method | Path | Purpose |
|-------|--------|------|---------|
| health | GET | `/health` | Liveness probe — `{"status":"ok"}` |
| ingest | POST | `/ingest/sales-daily` | Batch upsert with natural-key resolution, idempotent `ON CONFLICT DO UPDATE` |
| dimensions | GET | `/dimensions/stores` | List stores (1-indexed pagination, region/store_type filter, case-insensitive search, optional allow-listed `sort_by`/`sort_order`) |
| dimensions | GET | `/dimensions/stores/{store_id}` | Get store by ID |
| dimensions | GET | `/dimensions/products` | List products (category/brand filter, sku/name search, optional allow-listed `sort_by`/`sort_order`) |
| dimensions | GET | `/dimensions/products/{product_id}` | Get product by ID |
| analytics | GET | `/analytics/kpis` | Aggregated KPIs (revenue, units, transactions, avg unit price, avg basket) |
| analytics | GET | `/analytics/drilldowns` | Group-by dimension: store / product / category / region / date |
| analytics | GET | `/analytics/timeseries` | Period-bucketed sales series (`granularity` = day/week/month/quarter) for revenue-over-time charts; reuses `validate_date_range` (inverted/over-730-day ranges 400) |
| analytics | GET | `/analytics/inventory-status` | Latest `inventory_snapshot_daily` row per `(store, product)` grain (Postgres `DISTINCT ON`); optional `store_id`/`product_id` filters; `200` + empty list on an empty table (never `404`) |
| featuresets | POST | `/featuresets/compute` | Compute time-safe features (lag/rolling/calendar, leakage-prevented) |
| featuresets | POST | `/featuresets/preview` | Preview features with sample rows |
| forecasting | POST | `/forecasting/train` | Train a model (naive / seasonal_naive / moving_average / lightgbm / regression). `regression` wraps `HistGradientBoostingRegressor` on lag + calendar + exogenous features — the baseline a `model_exogenous` scenario re-forecasts through |
| forecasting | POST | `/forecasting/predict` | Generate horizon predictions from a trained model |
| backtesting | POST | `/backtesting/run` | Time-series CV (rolling/expanding splits, MAE/sMAPE/WAPE/bias/stability) |
| explainability | POST | `/explain/forecast` | Rule-based explanation of the h=1 forecast a named baseline model (`naive`/`seasonal_naive`/`moving_average`) produces on the series ending at `as_of_date`; returns a `ForecastExplanation` — driver contributions, advisory retail reason codes (correlation, not causation), confidence band, caveats, agent summary. Time-safe (`<= as_of_date`); a non-baseline `model_type` or a too-short series → RFC 7807 400 |
| explainability | GET | `/explain/runs/{run_id}` | Explain a registry `model_run` — config reconstructed from `model_run.model_config`, cutoff `data_window_end`. Missing run → 404; a non-baseline (`lightgbm`/`regression`) run → 400 |
| explainability | GET | `/explain/jobs/{job_id}` | Explain a completed `predict` job — store/product/model read from `job.result`, cutoff = day before the first forecast date. Missing job → 404; a job that is not a completed predict job → 400 |
| scenarios | POST | `/scenarios/simulate` | Stateless what-if: load a baseline model, forecast, apply price/promotion/holiday/inventory/lifecycle assumptions, return a `ScenarioComparison`. A `regression` baseline genuinely re-forecasts through a leakage-safe future feature frame (`method="model_exogenous"`); any other baseline applies a deterministic post-forecast multiplier (`method="heuristic"`). Bogus `run_id` → RFC 7807 404 |
| scenarios | POST | `/scenarios` | Run a simulation and persist it as a named `scenario_plan` (raw assumptions + full comparison snapshot); optional `tags` + `cloned_from` |
| scenarios | GET | `/scenarios` | List saved scenario plans, newest first (`limit`/`offset`, optional repeated `tags` filter — JSONB containment); `200` + empty list on an empty table |
| scenarios | GET | `/scenarios/{scenario_id}` | Saved plan + embedded comparison snapshot; `404` when missing |
| scenarios | POST | `/scenarios/compare` | Rank 2-5 saved plans (`scenario_ids`, `rank_by`) against a shared baseline; returns a `MultiScenarioComparison` with ranked rows + merged multi-series chart data. Unknown `scenario_id` → 404 |
| scenarios | DELETE | `/scenarios/{scenario_id}` | Delete a saved plan; `404` when missing |
| registry | POST | `/registry/runs` | Create model run (pending) |
| registry | GET | `/registry/runs` | List with filters + pagination + optional allow-listed `sort_by`/`sort_order` (created_at/model_type/status/store_id/product_id; unknown → default `created_at desc`) |
| registry | GET | `/registry/runs/{run_id}` | Run details + JSONB metrics + runtime_info |
| registry | PATCH | `/registry/runs/{run_id}` | Update status / metrics / artifact_uri |
| registry | GET | `/registry/runs/{run_id}/verify` | SHA-256 artifact integrity check |
| registry | POST | `/registry/aliases` | Create/update alias (only on `success` runs) |
| registry | GET | `/registry/aliases` | List aliases |
| registry | GET | `/registry/aliases/{alias_name}` | Get alias |
| registry | DELETE | `/registry/aliases/{alias_name}` | Delete alias |
| registry | GET | `/registry/compare/{run_id_a}/{run_id_b}` | Diff two runs |
| jobs | POST | `/jobs` | Submit `train` / `predict` / `backtest` (returns 202-style job_id) |
| jobs | GET | `/jobs` | List with filters + optional allow-listed `sort_by`/`sort_order` (created_at/completed_at/job_type/status; unknown → default `created_at desc`) |
| jobs | GET | `/jobs/{job_id}` | Status + result JSON |
| jobs | DELETE | `/jobs/{job_id}` | Cancel pending |
| rag | POST | `/rag/index` | Index a markdown/openapi document; idempotent via content hash |
| rag | POST | `/rag/index/project-docs` | Bulk-index bundled `docs/`, `PRPs/`, and root markdown; per-file + aggregate summary; idempotent via content hash; `502` if the embedding provider fails |
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
| demo | POST | `/demo/run` | Run the end-to-end demo pipeline in-process; returns a `DemoRunResult`. `409 application/problem+json` if a run is already active |
| demo | WS | `/demo/stream` | Stream one `StepEvent` per pipeline step for the live Showcase page |
| config | GET | `/config/ai` | Effective AI-model config (agent LLM + RAG embeddings); API keys masked, never raw |
| config | PATCH | `/config/ai` | Persist + apply AI-model changes live (no restart). `409` if an embedding-dimension change would orphan indexed RAG chunks (resend with `force=true`) |
| config | GET | `/config/providers/health` | Per-provider connectivity — Ollama probed live, cloud providers by API-key presence |
| config | GET | `/config/ollama/models` | Models pulled on the configured Ollama host. `502` if the host is unreachable |

## WebSocket Events (`/agents/stream`)

Verified against `app/features/agents/websocket.py` and `app/features/agents/schemas.py:229` (`StreamEvent`):

- **Client → server (per message):** `{"session_id": str, "message": str}` — both fields required; missing fields return a recoverable `error` event. The connection stays open for multiple messages within one session; each message gets a fresh DB session.
- **Server → client (every frame):** `{"event_type": <one of below>, "data": {...}, "timestamp": <iso8601 UTC>}` (Pydantic-serialized `StreamEvent`).
- **`event_type` values (Literal in `StreamEvent`):**
  - `text_delta` — `data: {"delta": str}` (`TextDeltaEvent`)
  - `tool_call_start` — `data: {"tool_name": str, "tool_call_id": str, "arguments": dict}` (`ToolCallStartEvent`)
  - `tool_call_end` — `data: {"tool_name": str, "tool_call_id": str, "result": Any, "duration_ms": float}` (`ToolCallEndEvent`)
  - `approval_required` — emitted when a tool in `agent_require_approval` is pending; the chat REST `/agents/sessions/{id}/approve` endpoint releases it
  - `complete` — `data: {"message": str, "tokens_used": int, "tool_calls_count": int}` (`CompleteEvent`)
  - `error` — `data: {"error": str, "error_type": str, "recoverable": bool}` (`ErrorEvent`). On `recoverable: false` (e.g., `session_not_found`, `session_expired`), the client should close.

## WebSocket Events (`/demo/stream`)

Drives the end-to-end demo pipeline for the dashboard Showcase page. Verified against `app/features/demo/routes.py` and `app/features/demo/schemas.py` (`StepEvent`).

- **Client → server (one start frame):** `{"seed": int, "reset": bool, "skip_seed": bool}` — all fields optional (`DemoRunRequest` supplies defaults `seed=42`, `reset=false`, `skip_seed=true`). The pipeline runs once, then the server closes.
- **Server → client (every frame):** Pydantic-serialized `StepEvent` — `{"event_type", "step_name", "step_index", "total_steps", "status", "detail", "duration_ms", "data", "timestamp"}`.
- **`event_type` values (Literal in `StepEvent`):**
  - `step_start` — a step began; `status` is `null`.
  - `step_complete` — a step finished; `status ∈ {pass, fail, skip, warn}`, `data` carries structured payload (backtest `per_model` WAPE + `winner`; register `run_id` + `alias`).
  - `pipeline_complete` — final event; `data` carries `winner_model_type`, `winner_wape`, `winning_run_id`, `alias`, `wall_clock_s`.
  - `error` — bad start frame or a concurrent run already in progress; one event, then the server closes.
- Concurrency: a module-level `asyncio.Lock` allows one pipeline at a time. A second `POST /demo/run` returns `409`; a second `WS /demo/stream` receives one `error` event.

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
