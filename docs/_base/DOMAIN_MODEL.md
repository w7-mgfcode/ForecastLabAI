# ForecastLabAI Domain Model
> Source: heuristic discovery from `app/features/data_platform/models.py`, `app/features/registry/models.py`, `app/features/rag/models.py`, `app/features/agents/models.py`, `app/features/forecasting/models.py`, `app/features/jobs/models.py`, `app/shared/seeder/`. Body spot-verified against the SQLAlchemy models on 2026-05-12.

## Bounded Contexts

| Context | Owns | Anti-Corruption Layer |
|---------|------|-----------------------|
| Data Platform | `store`, `product`, `calendar`, `sales_daily`, `price_history`, `promotion`, `inventory_snapshot_daily` | Ingest layer's natural-key resolution (`store_code` → `store_id`, `sku` → `product_id`) |
| Featuresets | Computed feature matrices (in-memory; not persisted) | Time-cutoff parameter — never reads beyond `cutoff_date` |
| Forecasting | Trained model artifacts on disk (joblib `.pkl`) | Model interface in `examples/models/model_interface.md`; artifact_uri returned to caller |
| Backtesting | Fold results, metrics (returned in response; persisted via Registry) | `SplitConfig` (expanding/sliding, gap, horizon) — `app/features/backtesting/splitter.py` |
| Registry | `model_run`, `run_alias`, `model_artifact` | SHA-256 hash on artifact_uri; status state machine |
| RAG | `rag_source`, `rag_chunk` (with pgvector embedding column) | Content hash for idempotent indexing; embedding dimension fixed per provider |
| Agents | `agent_session` (JSONB message_history) | Pydantic-validated tool args; HITL approval queue |
| Jobs | `job` (JSONB params + result) | Discriminated-union `job_type` (`train`/`predict`/`backtest`) |
| Analytics | None persisted — pure read-aggregates | SQL GROUP BY over `sales_daily` joined to dimensions |
| Seeder ("The Forge") | Generates synthetic rows in Data Platform tables | `Scenario` preset + `DimensionConfig`/`FactsConfig` dataclasses; `dataclasses.replace` for field-precise overrides |

## Core Aggregates

### `model_run` (Registry)
- **Root:** `ModelRun(run_id: UUID, status: RunStatus)`
- **Status state machine:** `pending` → `running` → `success` | `failed` → `archived`
- **JSONB fields:** `model_config`, `metrics`, `runtime_info` (Python/numpy/pandas versions captured at training)
- **Invariants:**
  - An alias may point only to a `success` run.
  - Artifact_uri SHA-256 hash must verify before any consumer trusts it (`GET /registry/runs/{id}/verify`).
  - `runtime_info` is immutable after `success`.

### `agent_session` (Agents)
- **Root:** `AgentSession(session_id: UUID, status: SessionStatus)`
- **Status:** `active` / `awaiting_approval` / `expired` / `closed` (`SessionStatus` enum, `app/features/agents/models.py:24`). Transitions: `ACTIVE → AWAITING_APPROVAL` (sensitive action pending), `AWAITING_APPROVAL → ACTIVE` (on approval/rejection), `ACTIVE → EXPIRED` (on timeout), `ACTIVE → CLOSED` (on explicit close).
- **Invariants:**
  - `message_history` JSONB is append-only within a session.
  - Tools in `agent_require_approval` block until `POST /agents/sessions/{id}/approve` returns.
  - Token budget cap (`agent_max_tokens`) and tool-call cap (`agent_max_tool_calls`) per session.

### `sales_daily` (Data Platform)
- **Root:** composite `(store_id, product_id, date)`
- **Invariants:**
  - `quantity >= 0`, `unit_price >= 0`, `total_amount = quantity * unit_price` (approx; rounding tolerated).
  - `store_id`, `product_id`, `date` must reference existing dimension rows.
  - Idempotent upsert via `ON CONFLICT (store_id, product_id, date) DO UPDATE` (`app/features/ingest/service.py`).

## Key Invariants — NEVER violate

1. **Time safety in features.** `app/features/featuresets/` uses only data at or before `cutoff_date`. Lags via `shift(positive)`, rolling via `shift(1).rolling(...)`, all `groupby` entity-aware. The test `app/features/featuresets/tests/test_leakage.py` is the spec — it MUST keep passing.
2. **Forward-only migrations.** Once an Alembic migration is merged, never edit it. Add a new migration to fix or evolve.
3. **HITL approval gates the agent's mutation surface.** Every tool that writes to the registry (`create_alias`, `archive_run`, …) must be in `agent_require_approval`. Widening the surface without updating that list is a security regression.
4. **Single-host deployable.** No managed cloud service in the core path. `docker-compose up` must continue to be the only prerequisite besides Python + Node.
5. **Pre-1.0 contracts may move.** Pin the version you build against. After `v1.0.0`, full SemVer applies.
6. **Seeder is idempotent + scoped.** Never introduce a "wipe everything" path that isn't behind `--confirm` + scope flag.

## Ubiquitous Language — use exactly these terms

| Term | Means | NOT |
|------|-------|-----|
| `store` | Retail location (dimension); composite-key parent of sales | branch, outlet |
| `product` | SKU (dimension); composite-key parent of sales | item, article |
| `sales_daily` | One row per `(store_id, product_id, date)` | order, transaction (those would be finer-grain) |
| `run` | A model training instance tracked in the registry | experiment, job |
| `alias` | A pointer to a `success` run (e.g., `production`, `champion`) | tag, label |
| `session` (agent) | One conversation between user and PydanticAI agent | thread, chat |
| `fold` | One train+test split inside a backtest | iteration |
| `baseline` | A naive / seasonal_naive / moving_average model included for comparison | benchmark, control |
| `lag` | Past value at offset `k` (`shift(k)`) | window |
| `rolling` | Statistic over a trailing window with `shift(1)` to avoid leakage | moving average (only for the MA model name) |
| `chunk` (RAG) | A windowed segment of a source document with its own embedding | section, paragraph |
| `scenario` (seeder) | A YAML or in-code preset (`retail_standard`, `holiday_rush`, …) that wires `DimensionConfig` + `FactsConfig` | template, profile |

## Event Taxonomy

None. There is no async event bus by design (`product-vision.md`: not a streaming system). All workflows are request/response or in-process tool-call.

## Entity Relationship Summary

```
store ─────┐
           ├──► sales_daily ◄──── price_history
product ───┤                 ◄──── promotion
           ├──► inventory_snapshot_daily
calendar ──┘

model_run ──owns──► artifact (on disk; SHA-256 verified)
model_run ◄─points-to── run_alias

rag_source ──owns──► rag_chunk (with pgvector embedding)

agent_session ──owns──► message_history (JSONB) ──may-contain──► tool_call (pending approval)

job ──may-reference──► model_run (for train/backtest jobs)
```

## Glossary (cross-cutting)

| Term | Definition | Context |
|------|------------|---------|
| HITL | Human-in-the-loop — agent pauses for `/approve` call | Agents |
| RFC 7807 | `application/problem+json` error envelope | API |
| HNSW | Hierarchical Navigable Small World — pgvector index type | RAG |
| SMAPE | Symmetric Mean Absolute Percentage Error (0–200 scale) | Backtesting metrics |
| WAPE | Weighted Absolute Percentage Error | Backtesting metrics |
| PRP | Project Requirements Plan — the doc that gates a vertical-slice implementation | Workflow |
| INITIAL-N | Discovery-phase doc that precedes a PRP | Workflow |
| "The Forge" | Internal name for the seeder (`app/shared/seeder/`) | Seeder |
