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
    RAGUI[RAG Assistant Panel]
  end

  subgraph API[Backend (FastAPI)]
    ING[Ingest API]
    TRAIN[Train/Backtest API]
    PRED[Predict API]
    RUNS[Runs & Leaderboard API]
    RAGAPI[RAG Query API]
  end

  subgraph DB[PostgreSQL]
    REL[(Relational Tables)]
    VEC[(pgvector Embeddings)]
  end

  subgraph ART[Artifacts]
    MODEL[(Model Artifacts)]
    REPORTS[(Run Reports)]
    OPENAPI[(OpenAPI Export)]
  end

  DASH --> API
  RAGUI --> RAGAPI

  ING --> REL
  TRAIN --> REL
  PRED --> REL
  RUNS --> REL

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
    ├── ingest/         # idempotent ingest endpoints (sales_daily / sales_txn)
    ├── featuresets/    # time-safe feature engineering (lags/rolling/exog)
    ├── forecasting/    # model zoo + fit/predict + serialization
    ├── backtesting/    # rolling/expanding CV + metrics
    ├── registry/       # run registry + artifact metadata
    ├── rag/            # indexing + retrieval + citations (pgvector)
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
```
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

## 8) Typed FastAPI Contracts (Serving Layer)

**Implemented Endpoints:**
- `GET /health` - Health check
- `POST /ingest/sales-daily` - Batch upsert daily sales records
- `POST /featuresets/compute` - Compute time-safe features
- `POST /featuresets/preview` - Preview features with sample rows
- `POST /forecasting/train` - Train forecasting model (returns model_path)
- `POST /forecasting/predict` - Generate forecasts using saved model
- `POST /backtesting/run` - Run time-series CV backtest with baseline comparisons
- `POST /registry/runs` - Create model run
- `GET /registry/runs` - List runs with filters
- `GET /registry/runs/{run_id}` - Get run details
- `PATCH /registry/runs/{run_id}` - Update run status/metrics/artifacts
- `GET /registry/runs/{run_id}/verify` - Verify artifact integrity
- `POST /registry/aliases` - Create deployment alias
- `GET /registry/aliases` - List aliases
- `GET /registry/aliases/{alias_name}` - Get alias details
- `DELETE /registry/aliases/{alias_name}` - Delete alias
- `GET /registry/compare/{run_id_a}/{run_id_b}` - Compare two runs

**Planned Endpoints:**
- `GET /data/kpis`, `GET /data/drilldowns` - Data exploration
- `POST /rag/query` - RAG knowledge base queries (optional `/rag/index` in dev)

Contracts are Pydantic v2 validated and use `response_model` for explicit output typing.

---

## 9) Dashboard (React + Vite)

The UI is intentionally **table-first**:
- Data Explorer
- Model Runs (leaderboard + compare)
- Train & Predict (forms + status)
- Predictions (tabular forecasts)
- RAG assistant panel with citations

Decision reference: `docs/ADR/ADR-0002-frontend-architecture-vite-spa-first.md`

---

## 10) RAG Knowledge Base (Postgres + pgvector)

### 10.1 Indexed Sources (Planned)
- `README.md`
- `docs/*` (Architecture, ADRs, guides)
- OpenAPI export
- Run reports generated per training run

### 10.2 Evidence-Grounded Answers
RAG must return citations for non-trivial claims; if evidence is insufficient, it must respond “not found / insufficient evidence”.

Decision reference: `docs/ADR/ADR-0003-vector-storage-pgvector-in-postgres.md`

---

## 11) Quality, CI, and Review Rules

The repo standards live in `docs/validation/` and are treated as merge gates:
- Ruff lint/format
- Pytest (unit + integration)
- Alembic migration checks
- MyPy + Pyright strict
- Logging taxonomy (`docs/validation/logging-standard.md`)

---

## 12) Roadmap (Phased Delivery)

- **Phase-0**: vertical-slice demo (seed → ingest → baseline train → predict → UI tables) ✅
- **Phase-1**: ForecastOps core (backtesting + registry + leaderboard) ✅
  - Backtesting: ✅ IMPLEMENTED (PRP-6)
  - Registry: ✅ IMPLEMENTED (PRP-7)
  - Leaderboard UI: Planned
- **Phase-2**: ML models + richer exogenous features
- **Phase-3**: RAG + agentic workflows (PydanticAI), run report generation/indexing
