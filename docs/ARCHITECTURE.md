# ARCHITECTURE.md — ForecastLabAI / ForecastOps (Docs-First Bootstrap)

This repository is being built **docs-first** to support AI-assisted development and a portfolio-ready narrative. The goal is an end-to-end retail demand forecasting system (“ForecastOps”) with a typed FastAPI backend, a modern dashboard, a reproducible model registry, and a lightweight RAG knowledge base backed by PostgreSQL + pgvector.

---

## 1) What Exists Today (Current Repo Bootstrap)

At the start, the repo focuses on **governance, standards, and specifications** before code lands.

### 1.1 Current Repository Tree (Key Areas)

- `.github/`  
  CI/CD workflows, PR templates, and repo governance scaffolding.

- `.vscode/settings.json`  
  Editor defaults aligned with strict formatting/linting.

- `docs/ADR/`  
  Architecture Decision Records (ADRs), including:
  - `ADR-INDEX.md`
  - `ADR-0001-template.md`
  - `ADR-0002-frontend-architecture-vite-spa-first.md`
  - `ADR-0003-vector-storage-pgvector-in-postgres.md`

- `docs/github/`  
  Internal references for GitHub workflow patterns and repo setup.

- `docs/validation/`  
  “Definition of Done” standards used as CI gates and review criteria:
  - `ruff-standard.md`
  - `pytest-standard.md`
  - `mypy-standard.md`
  - `pyright-standard.md`
  - `logging-standard.md`

- `PRPs/templates/`  
  PRP templates used to turn INITIAL specs into implementable tasks.

- Root specs:
  - `CLAUDE.md` (AI coding guidance for this repo)
  - `INITIAL-*.md` (feature-level initial specs)

---

## 2) Delivery Process (How Work Flows)

This repo uses a structured “spec-to-code” workflow:

1. **INITIAL-​*.md**  
   Defines scope, outcomes, constraints, examples, and documentation references.

2. **PRP (Product Requirements Prompt)**  
   Converts an INITIAL into a step-by-step, repo-ready implementation plan:
   - DB schema + migrations
   - endpoints + schemas
   - service logic
   - tests (unit + integration)
   - logging events
   - docs/examples updates

3. **Implementation (Vertical Slice)**  
   Code lands as a vertical slice with minimal cross-feature coupling.

4. **Validation Gates**  
   Must be green before merge:
   - Ruff (lint/format), Pytest, Alembic migration checks
   - MyPy + Pyright strict
   - Logging taxonomy compliance

---

## 3) Target System (End-State Architecture)

### 3.1 Logical Component Diagram

```mermaid
flowchart LR
  subgraph UI[Frontend (React + Vite)]
    DASH[Dashboard\nshadcn/ui Data Tables]
    AGENTUI[Agent Chat Interface]
  end

  subgraph API[Backend (FastAPI)]
    ING[Ingest API]
    TRAIN[Train/Backtest API]
    PRED[Predict API]
    RUNS[Runs & Leaderboard API]
    RAGAPI[RAG Query API]
    AGENTS[Agentic Layer\nPydanticAI]
  end

  subgraph DB[PostgreSQL]
    REL[(Relational Tables)]
    VEC[(pgvector Embeddings)]
    SESS[(Agent Sessions)]
  end

  subgraph ART[Artifacts]
    MODEL[(Model Artifacts)]
    REPORTS[(Run Reports)]
    OPENAPI[(OpenAPI Export)]
  end

  DASH --> API
  AGENTUI --> AGENTS

  ING --> REL
  TRAIN --> REL
  PRED --> REL
  RUNS --> REL

  AGENTS --> RAGAPI
  AGENTS --> TRAIN
  AGENTS --> RUNS
  AGENTS --> SESS

  TRAIN --> MODEL
  TRAIN --> REPORTS
  RUNS --> REPORTS

  RAGAPI --> VEC
  RAGAPI --> REL
  RAGAPI --> REPORTS
  RAGAPI --> OPENAPI
```

### 3.2 Key Flows
- **Ingest**: replay-safe upserts into relational tables (idempotent).
- **Train/Backtest**: build time-safe features, fit models, evaluate via time-based splits, persist run registry + artifacts.
- **Predict**: load a run’s model artifact, generate forecasts for requested series/horizon.
- **Dashboard**: explore data, browse runs/leaderboards, trigger train/predict, view predictions.
- **RAG**: index docs/OpenAPI/run reports into pgvector; retrieve top-k; answer with citations.

---

## 4) Planned Code Layout (When Implementation Starts)

When code is added, the repo will expand to include:

```
app/                    # FastAPI backend (vertical slices)
frontend/               # Vite + React dashboard
examples/               # runnable examples (seed/ingest/train/backtest/rag)
scripts/                # utilities (seed, exports, smoke tests)
alembic/                # migrations
docker-compose.yml      # local Postgres + pgvector
pyproject.toml          # tooling + strict typing + test config
```

Backend follows **vertical slice architecture**:

```
app/
├── core/               # config, database, logging, middleware, health, exceptions
├── shared/             # pagination, timestamps, error schemas
└── features/
    ├── data_platform/  # core tables (store, product, calendar, sales)
    ├── ingest/         # idempotent ingest endpoints (sales_daily / sales_txn)
    ├── featuresets/    # time-safe feature engineering (lags/rolling/exog)
    ├── forecasting/    # model zoo + fit/predict + serialization
    ├── backtesting/    # rolling/expanding CV + metrics
    ├── registry/       # run registry + artifact metadata
    ├── rag/            # indexing + retrieval + citations (pgvector) ✅
    ├── agents/         # PydanticAI agents (experiment, RAG assistant) ✅
    ├── dimensions/     # store/product discovery for LLM tool-calling
    ├── analytics/      # KPI aggregations and drilldowns
    └── jobs/           # optional orchestration (sync now; async-ready contracts)
```

---

## 5) Data Platform (Mini Warehouse) — ✅ IMPLEMENTED

### 5.1 Core Tables (Implemented via PRP-2)

**Dimensions**
- `store` — id, code (unique), name, region, city, store_type
- `product` — id, sku (unique), name, category, brand, base_price, base_cost
- `calendar` — date (PK), day_of_week, month, quarter, year, is_holiday, holiday_name

**Facts**
- `sales_daily` (required) — grain: `UNIQUE(date, store_id, product_id)` with FK to all dimensions
- `price_history` — valid_from/valid_to windows, nullable store_id for chain-wide prices
- `promotion` — discount_pct, discount_amount, start_date/end_date windows
- `inventory_snapshot_daily` — on_hand_qty, on_order_qty, is_stockout flag, grain-protected

**Stub-Ready (Optional)**
- `sales_txn`, `traffic_daily`, `weather_daily`

### 5.2 Key Features

- **SQLAlchemy 2.0**: All models use `Mapped[]` type annotations and `mapped_column()`
- **Grain Protection**: Unique constraints on `(date, store_id, product_id)` for `sales_daily` and `inventory_snapshot_daily`
- **Data Quality**: Check constraints enforce positive quantities, valid date ranges, valid calendar values
- **Query Performance**: Composite indexes for time-range + store/product filtering
- **Type Safety**: All monetary values use `Numeric(10, 2)`, dates use proper `Date` type

### 5.3 Grain & Idempotency (Critical)
- Uniqueness enforced at DB-level via `UniqueConstraint` (not just index)
- Enables `ON CONFLICT` upserts for replay-safe ingestion
- Migration: `alembic/versions/e1165ebcef61_create_data_platform_tables.py`

### 5.4 Location
- Models: `app/features/data_platform/models.py`
- Schemas: `app/features/data_platform/schemas.py`
- Tests: `app/features/data_platform/tests/` (32 unit + 11 integration tests)
- Documentation: `examples/schema/README.md`, `examples/queries/`

---

## 6) Feature Engineering (Time-Safe) — ✅ IMPLEMENTED

### 6.1 Core Service (Implemented via PRP-4)

The `FeatureEngineeringService` provides time-safe feature computation with CRITICAL leakage prevention:

**Leakage Prevention Patterns**:
- **Lag features**: `shift(lag)` with positive lag only — ensures only past data accessed
- **Rolling features**: `shift(1)` BEFORE `.rolling()` — excludes current observation from window
- **Group isolation**: `groupby(entity_cols, observed=True)` — prevents cross-series contamination
- **Cutoff enforcement**: Data filtered before feature computation — no future data in pipeline

### 6.2 Feature Types

| Type | Description | Output Example |
|------|-------------|----------------|
| Lag | Past values at specified periods | `lag_1`, `lag_7`, `lag_14` |
| Rolling | Rolling statistics (mean, std, min, max) | `rolling_mean_7`, `rolling_std_7` |
| Calendar | Date features with cyclical encoding | `dow_sin`, `dow_cos`, `month_sin` |
| Imputation | Zero-fill for sales, forward-fill for prices | N/A (modifies source columns) |

### 6.3 API Endpoints

- `POST /featuresets/compute` — Compute features for a single series
- `POST /featuresets/preview` — Preview features with sample rows

### 6.4 Location

- Schemas: `app/features/featuresets/schemas.py`
- Service: `app/features/featuresets/service.py`
- Routes: `app/features/featuresets/routes.py`
- Tests: `app/features/featuresets/tests/` (55 tests including leakage prevention)
- Demo: `examples/compute_features_demo.py`

---

## 7) ForecastOps (Training + Backtesting + Registry)

### 7.1 Model Zoo — ✅ IMPLEMENTED (Baseline Models)

**Implemented via PRP-5** - Forecasting module provides:

| Model | Description | Config Parameters |
|-------|-------------|-------------------|
| `naive` | Last observed value | None |
| `seasonal_naive` | Previous season value | `season_length` (e.g., 7 for weekly) |
| `moving_average` | Mean of last N observations | `window_size` (default: 7) |
| `lightgbm` | LightGBM regressor | Feature-flagged, disabled by default |

**Model Interface:** All models inherit from `BaseForecaster` with typed `fit()` and `predict()` methods.

**Persistence:** Models saved as `ModelBundle` (joblib) containing fitted model, config, metadata, and version info.

### 7.2 API Endpoints

- `POST /forecasting/train` - Train model for a single series (returns model_path)
- `POST /forecasting/predict` - Generate forecasts using saved model

### 7.3 Location

- Models: `app/features/forecasting/models.py`
- Persistence: `app/features/forecasting/persistence.py`
- Schemas: `app/features/forecasting/schemas.py`
- Service: `app/features/forecasting/service.py`
- Routes: `app/features/forecasting/routes.py`
- Tests: `app/features/forecasting/tests/` (comprehensive test coverage)
- Examples: `examples/models/` (baseline_naive.py, baseline_seasonal.py, baseline_mavg.py)

### 7.4 Configuration (Settings)

```python
forecast_random_seed: int = 42
forecast_default_horizon: int = 14
forecast_max_horizon: int = 90
forecast_model_artifacts_dir: str = "./artifacts/models"
forecast_enable_lightgbm: bool = False
```

### 7.5 Backtesting Protocol — ✅ IMPLEMENTED

**Implemented via PRP-6** - Time-series backtesting module provides:

**Split Strategies:**
| Strategy | Description | Train Size Behavior |
|----------|-------------|---------------------|
| `expanding` | Train window grows each fold | Increases per fold |
| `sliding` | Fixed-size train window slides | Constant |

**Gap Parameter:** Simulates operational data latency (e.g., `gap=7` = 7 days between train end and test start).

**Metrics Suite:**
| Metric | Description | Scale |
|--------|-------------|-------|
| MAE | Mean Absolute Error | Same as target |
| sMAPE | Symmetric MAPE | 0-200 |
| WAPE | Weighted Absolute Percentage Error | 0-100+ |
| Bias | Forecast bias (positive = under-forecast) | Same as target |
| Stability Index | CV of metrics across folds | 0-100+ |

**Baseline Comparisons:** Automatic comparison against naive and seasonal_naive models with improvement percentages.

**Leakage Validation:** Built-in validation ensures no data leakage in splits.

**API Endpoint:** `POST /backtesting/run`

**Location:**
- Schemas: `app/features/backtesting/schemas.py`
- Splitter: `app/features/backtesting/splitter.py`
- Metrics: `app/features/backtesting/metrics.py`
- Service: `app/features/backtesting/service.py`
- Routes: `app/features/backtesting/routes.py`
- Tests: `app/features/backtesting/tests/` (95 tests)
- Examples: `examples/backtest/` (run_backtest.py, inspect_splits.py, metrics_demo.py)

### 7.6 Model Registry — ✅ IMPLEMENTED

**Implemented via PRP-7** - Full run tracking and deployment alias management:

**ORM Models:**
- `ModelRun` - JSONB columns for model_config, feature_config, metrics, runtime_info, agent_context
- `DeploymentAlias` - Mutable pointers to successful runs for deployment

**Run Lifecycle (State Machine):**
```text
PENDING → RUNNING → SUCCESS/FAILED → ARCHIVED
```
- Validated transitions prevent invalid state changes
- Aliases can only point to SUCCESS runs

**Storage Provider:**
- `LocalFSProvider` with abstract interface for future S3/GCS support
- SHA-256 integrity verification on load
- Path traversal prevention (security)

**Each Run Stores:**
- run_id (UUID hex, 32 chars), timestamps (created_at, updated_at, started_at, completed_at)
- model_type + model_config (JSONB with GIN index)
- feature_config (JSONB, optional)
- data_window_start, data_window_end, store_id, product_id
- config_hash (16-char SHA-256 prefix for deduplication)
- metrics (JSONB with GIN index)
- artifact_uri, artifact_hash (SHA-256), artifact_size_bytes
- runtime_info (Python, numpy, pandas, sklearn, joblib versions)
- agent_context (agent_id, session_id for autonomous workflows)
- git_sha (optional)
- error_message (for FAILED runs)

**Duplicate Detection:**
- Configurable via `registry_duplicate_policy`: allow, deny, detect
- Based on config_hash + store_id + product_id + data_window

**API Endpoints:**
- `POST /registry/runs` - Create run
- `GET /registry/runs` - List with filters and pagination
- `GET /registry/runs/{run_id}` - Get run details
- `PATCH /registry/runs/{run_id}` - Update status/metrics/artifacts
- `GET /registry/runs/{run_id}/verify` - Verify artifact integrity
- `POST /registry/aliases` - Create/update deployment alias
- `GET /registry/aliases` - List aliases
- `GET /registry/aliases/{alias_name}` - Get alias
- `DELETE /registry/aliases/{alias_name}` - Delete alias
- `GET /registry/compare/{run_id_a}/{run_id_b}` - Compare runs

**Location:**
- Models: `app/features/registry/models.py`
- Schemas: `app/features/registry/schemas.py`
- Storage: `app/features/registry/storage.py`
- Service: `app/features/registry/service.py`
- Routes: `app/features/registry/routes.py`
- Tests: `app/features/registry/tests/` (103 unit + 24 integration tests)
- Example: `examples/registry_demo.py`

**Configuration (Settings):**
```python
registry_artifact_root: str = "./artifacts/registry"
registry_duplicate_policy: Literal["allow", "deny", "detect"] = "detect"
```

---

## 8) Typed FastAPI Contracts (Serving Layer) — ✅ IMPLEMENTED

**Implemented via PRP-8** - Agent-first API design with RFC 7807 error responses:

### 8.1 RFC 7807 Problem Details

All error responses use RFC 7807 format with `Content-Type: application/problem+json`:
- Type URIs: `/errors/validation`, `/errors/not-found`, `/errors/conflict`, `/errors/database`
- Includes `request_id` for correlation
- Field-level validation errors for 422 responses

### 8.2 Implemented Endpoints

**Health & Core:**
- `GET /health` - Health check

**Dimensions (Discovery):**
- `GET /dimensions/stores` - List stores with pagination, filtering, search
- `GET /dimensions/stores/{store_id}` - Get store by ID
- `GET /dimensions/products` - List products with pagination, filtering, search
- `GET /dimensions/products/{product_id}` - Get product by ID

**Analytics:**
- `GET /analytics/kpis` - Compute KPIs for date range with filters
- `GET /analytics/drilldowns` - Drill into dimension (store, product, category, region, date)

**Jobs (Task Orchestration):**
- `POST /jobs` - Create and execute job (train, predict, backtest)
- `GET /jobs` - List jobs with filtering and pagination
- `GET /jobs/{job_id}` - Get job status and result
- `DELETE /jobs/{job_id}` - Cancel pending job

**Ingest:**
- `POST /ingest/sales-daily` - Batch upsert daily sales records

**Feature Engineering:**
- `POST /featuresets/compute` - Compute time-safe features
- `POST /featuresets/preview` - Preview features with sample rows

**Forecasting:**
- `POST /forecasting/train` - Train forecasting model
- `POST /forecasting/predict` - Generate forecasts

**Backtesting:**
- `POST /backtesting/run` - Run time-series CV backtest

**Model Registry:**
- `POST /registry/runs` - Create model run
- `GET /registry/runs` - List runs with filters
- `GET /registry/runs/{run_id}` - Get run details
- `PATCH /registry/runs/{run_id}` - Update status/metrics/artifacts
- `GET /registry/runs/{run_id}/verify` - Verify artifact integrity
- `POST /registry/aliases` - Create deployment alias
- `GET /registry/aliases` - List aliases
- `GET /registry/aliases/{alias_name}` - Get alias details
- `DELETE /registry/aliases/{alias_name}` - Delete alias
- `GET /registry/compare/{run_id_a}/{run_id_b}` - Compare two runs

### 8.3 Location

- Problem Details: `app/core/problem_details.py`
- Dimensions: `app/features/dimensions/` (schemas, service, routes)
- Analytics: `app/features/analytics/` (schemas, service, routes)
- Jobs: `app/features/jobs/` (models, schemas, service, routes)
- Migration: `alembic/versions/37e16ecef223_create_jobs_table.py`

### 8.4 Configuration (Settings)

```python
analytics_max_rows: int = 10000
analytics_max_date_range_days: int = 730
jobs_retention_days: int = 30
```

**RAG:**
- `POST /rag/index` - Index document into knowledge base
- `POST /rag/retrieve` - Semantic search across indexed documents
- `GET /rag/sources` - List indexed sources
- `DELETE /rag/sources/{source_id}` - Delete source and chunks

**Agents:**
- `POST /agents/sessions` - Create new agent session
- `GET /agents/sessions/{session_id}` - Get session status
- `POST /agents/sessions/{session_id}/chat` - Send message to agent
- `POST /agents/sessions/{session_id}/approve` - Approve/reject pending action
- `DELETE /agents/sessions/{session_id}` - Close session
- `WS /agents/stream` - WebSocket streaming endpoint

Contracts are Pydantic v2 validated and use `response_model` for explicit output typing.

---

## 9) RAG Knowledge Base (Postgres + pgvector) — ✅ IMPLEMENTED

**Implemented via PRP-9** - RAG Knowledge Base with pgvector and multiple embedding providers:

### 9.1 Core Features

**Embedding Providers:**
- **OpenAI** (default): `text-embedding-3-small` (1536 dimensions)
- **Ollama** (local/LAN): `nomic-embed-text` (768 dimensions) via OpenAI-compatible `/v1/embeddings` endpoint

**Indexing & Retrieval:**
- PostgreSQL pgvector with HNSW similarity search
- Idempotent indexing via SHA-256 content hash
- Configurable embedding dimensions (must match model)
- Markdown-aware and OpenAPI endpoint-aware chunking strategies

**Evidence-Grounded Answers:**
- RAG returns citations for all claims
- If evidence is insufficient, responds with "not found / insufficient evidence"
- Citations include: source_type, source_path, chunk_id, snippet, relevance_score

### 9.2 Database Schema

**Tables:**
- `document_source` - Indexed sources (markdown, openapi, etc.)
- `document_chunk` - Text chunks with pgvector embeddings (dynamic dimension support)

**Indexes:**
- HNSW index on embedding vector for fast similarity search
- GIN indexes on metadata JSONB for filtering

### 9.3 API Endpoints

- `POST /rag/index` - Index document into knowledge base
- `POST /rag/retrieve` - Semantic search with similarity threshold
- `GET /rag/sources` - List indexed sources
- `DELETE /rag/sources/{source_id}` - Delete source and chunks

### 9.4 Indexed Sources

Currently supported:
- Markdown documents (`README.md`, `docs/`)
- OpenAPI specifications (endpoint documentation)
- Run reports (planned: generated per training run)

### 9.5 Configuration (Settings)

```python
rag_embedding_provider: Literal["openai", "ollama"] = "openai"
rag_embedding_dimension: int = 1536  # Must match model
rag_embedding_batch_size: int = 100

# OpenAI Configuration
openai_api_key: str = ""
rag_embedding_model: str = "text-embedding-3-small"

# Ollama Configuration (when provider="ollama")
ollama_base_url: str = "http://localhost:11434"
ollama_embedding_model: str = "nomic-embed-text"

# Chunking
rag_chunk_size: int = 512  # tokens
rag_chunk_overlap: int = 50  # tokens

# Retrieval
rag_top_k: int = 5
rag_similarity_threshold: float = 0.7
```

### 9.6 Location

- Models: `app/features/rag/models.py`
- Schemas: `app/features/rag/schemas.py`
- Embeddings: `app/features/rag/embeddings.py` (provider pattern)
- Chunkers: `app/features/rag/chunkers.py` (markdown, OpenAPI)
- Service: `app/features/rag/service.py`
- Routes: `app/features/rag/routes.py`
- Tests: `app/features/rag/tests/` (82 unit + 14 integration tests)
- Migrations: `alembic/versions/b4c8d9e0f123_create_rag_tables.py`, `c5d9e1f2g345_rag_dynamic_embedding_dimension.py`

Decision reference: `docs/ADR/ADR-0003-vector-storage-pgvector-in-postgres.md`

---

## 10) Agentic Layer ("The Brain") — ✅ IMPLEMENTED

**Implemented via PRP-10** - PydanticAI-based agents for autonomous decision-making and tool orchestration:

### 10.1 Core Features

**Agent Types:**
1. **Experiment Orchestrator Agent** (`agent_type: "experiment"`)
   - Autonomous model experimentation workflow
   - Systematic backtest execution and comparison
   - Deployment recommendation with human-in-the-loop approval
   - Tools: `list_models`, `run_backtest`, `compare_runs`, `create_alias`, `archive_run`

2. **RAG Assistant Agent** (`agent_type: "rag_assistant"`)
   - Evidence-grounded question answering
   - Citation-backed responses with confidence scoring
   - "Insufficient evidence" detection to prevent hallucination
   - Tools: `retrieve_context`, `format_citation`

**Session Management:**
- PostgreSQL JSONB storage for multi-turn message history
- Configurable session TTL and expiration (default: 120 minutes)
- Token usage tracking and tool call auditing
- Session state: active, awaiting_approval, expired, closed

**Human-in-the-Loop Approval:**
- Blocks sensitive actions (create_alias, archive_run)
- Configurable approval timeout (default: 60 minutes)
- Approval workflow: pending_action → approve/reject → execute/cancel
- Full audit trail for all decisions

**WebSocket Streaming:**
- Real-time token delivery for responsive UX
- Tool call progress events (tool_call_start, tool_call_end)
- Event types: text_delta, approval_required, complete, error
- Error handling with session recovery

### 10.2 Architecture Highlights

**Lazy Agent Initialization:**
- Agents instantiated on first use (no API key required at import)
- Prevents import-time failures in development

**Structured Outputs:**
- All responses are Pydantic models (ExperimentReport, RAGAnswer)
- Type-safe agent orchestration with PydanticAI v1.48.0
- Full MyPy + Pyright compliance

**Tool Integration:**
- Seamless binding to Registry, Backtesting, Forecasting, and RAG modules
- Tool docstrings optimized for LLM function-calling
- Comprehensive error handling with retry logic

### 10.3 Database Schema

**AgentSession Table:**
```sql
CREATE TABLE agent_session (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(32) UNIQUE NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    message_history JSONB NOT NULL DEFAULT '[]',
    pending_action JSONB NULL,
    total_tokens_used INTEGER NOT NULL DEFAULT 0,
    tool_calls_count INTEGER NOT NULL DEFAULT 0,
    last_activity TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

**Indexes:**
- Unique index on session_id
- Indexes on agent_type, status, expires_at
- GIN index on message_history for JSONB queries

### 10.4 API Endpoints

**REST API:**
- `POST /agents/sessions` - Create new agent session
- `GET /agents/sessions/{session_id}` - Get session status
- `POST /agents/sessions/{session_id}/chat` - Send message to agent
- `POST /agents/sessions/{session_id}/approve` - Approve/reject pending action
- `DELETE /agents/sessions/{session_id}` - Close session

**WebSocket:**
- `WS /agents/stream` - Real-time streaming endpoint

### 10.5 Configuration (Settings)

```python
# Agent LLM Configuration
agent_default_model: str = "anthropic:claude-sonnet-4-5"
agent_fallback_model: str = "openai:gpt-4o"
agent_temperature: float = 0.1
agent_max_tokens: int = 4096
anthropic_api_key: str = ""

# Agent Execution Configuration
agent_max_tool_calls: int = 10
agent_timeout_seconds: int = 120
agent_retry_attempts: int = 3
agent_retry_delay_seconds: float = 1.0

# Human-in-the-Loop Configuration
agent_require_approval: list[str] = ["create_alias", "archive_run"]
agent_approval_timeout_minutes: int = 60

# Session Configuration
agent_session_ttl_minutes: int = 120
agent_max_sessions_per_user: int = 5

# Streaming Configuration
agent_enable_streaming: bool = True
```

### 10.6 Location

- Agents: `app/features/agents/agents/` (experiment.py, rag_assistant.py, base.py)
- Tools: `app/features/agents/tools/` (registry, backtesting, forecasting, RAG)
- Models: `app/features/agents/models.py`
- Schemas: `app/features/agents/schemas.py`
- Service: `app/features/agents/service.py`
- Routes: `app/features/agents/routes.py`
- WebSocket: `app/features/agents/websocket.py`
- Dependencies: `app/features/agents/deps.py`
- Tests: `app/features/agents/tests/` (92 unit tests)
- Migration: `alembic/versions/d6e0f2g3h456_create_agent_session_table.py`

### 10.7 Dependencies

```python
# Added to pyproject.toml
"pydantic-ai>=1.48.0"      # PydanticAI agent framework (v1 stable)
"anthropic>=0.50.0"        # Anthropic SDK for Claude
```

---

## 11) Dashboard (React + Vite) — Pending

The UI is intentionally **table-first**:
- Data Explorer
- Model Runs (leaderboard + compare)
- Train & Predict (forms + status)
- Predictions (tabular forecasts)
- **Agent Chat Interface** with streaming and citations

Decision reference: `docs/ADR/ADR-0002-frontend-architecture-vite-spa-first.md`

---

## 12) Quality, CI, and Review Rules

The repo standards live in `docs/validation/` and are treated as merge gates:
- Ruff lint/format
- Pytest (unit + integration)
- Alembic migration checks
- MyPy + Pyright strict
- Logging taxonomy (`docs/validation/logging-standard.md`)

---

## 13) Roadmap (Phased Delivery)

### Completed Phases

- **Phase 0**: Project Foundation ✅
  - Repository setup, CI/CD workflows, validation standards
  - PRP-0, PRP-1

- **Phase 1**: Data Platform ✅
  - 7-table mini warehouse (dimensions + facts)
  - Grain protection, check constraints, composite indexes
  - PRP-2

- **Phase 2**: Ingest Layer ✅
  - Idempotent batch upsert endpoints
  - Natural key resolution, partial success handling
  - PRP-3

- **Phase 3**: Feature Engineering ✅
  - Time-safe lags, rolling windows, calendar features
  - Leakage prevention (shift-before-rolling pattern)
  - PRP-4

- **Phase 4**: Forecasting ✅
  - Model zoo (naive, seasonal_naive, moving_average, LightGBM)
  - BaseForecaster interface, ModelBundle persistence
  - PRP-5

- **Phase 5**: Backtesting ✅
  - Time-series CV (expanding/sliding strategies)
  - Metrics (MAE, sMAPE, WAPE, Bias, Stability Index)
  - Baseline comparisons with improvement percentages
  - PRP-6

- **Phase 6**: Model Registry ✅
  - Run tracking with JSONB config/metrics/runtime_info
  - Deployment aliases, SHA-256 artifact integrity
  - Duplicate detection, state machine (PENDING → RUNNING → SUCCESS/FAILED → ARCHIVED)
  - PRP-7

- **Phase 7**: Serving Layer ✅
  - RFC 7807 Problem Details error format
  - Dimensions discovery (stores, products)
  - Analytics KPIs and drilldowns
  - Jobs orchestration (sync execution, async-ready contracts)
  - PRP-8

- **Phase 8**: RAG Knowledge Base ✅
  - PostgreSQL pgvector with HNSW indexing
  - OpenAI and Ollama embedding providers
  - Markdown and OpenAPI chunking strategies
  - Evidence-grounded answers with citations
  - PRP-9

- **Phase 9**: Agentic Layer ✅
  - PydanticAI agents (Experiment Orchestrator, RAG Assistant)
  - Session management with JSONB message history
  - Human-in-the-loop approval workflow
  - WebSocket streaming for real-time responses
  - Tool integration with Registry, Backtesting, Forecasting, and RAG
  - PRP-10

### Pending Phases

- **Phase 10**: ForecastLab Dashboard (Pending)
  - React 19 + Vite + shadcn/ui + Tailwind CSS 4
  - TanStack Table for server-side data grids
  - TanStack Query for data fetching and caching
  - Recharts for time series visualization
  - Agent chat interface with streaming and citations
  - PRP-11

- **Phase 11**: ML Models (Future)
  - Advanced models (XGBoost, Prophet, etc.)
  - Richer exogenous features
  - Hyperparameter optimization

- **Phase 12**: Production Hardening (Future)
  - Async job execution (Celery/ARQ)
  - S3/GCS artifact storage
  - Distributed caching (Redis)
  - Observability (OpenTelemetry)
