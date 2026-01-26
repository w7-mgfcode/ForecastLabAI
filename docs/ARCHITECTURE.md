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

## 5) Data Platform (Mini Warehouse)

### 5.1 Core Tables (Planned)
**Dimensions**
- `store` (region/city/type)
- `product` (SKU/category/brand/base_price/base_cost)
- `calendar` (date, weekday/month, holiday flags)

**Facts**
- `sales_daily` (required) — grain: `(date, store_id, product_id)`
- `price_history` — valid_from/to windows
- `promotion` — promo windows + mechanics
- `inventory_snapshot_daily` — on_hand, on_order, stockout signals

**Optional**
- `sales_txn`, `traffic_daily`, `weather_daily`

### 5.2 Grain & Idempotency (Critical)
- Enforce uniqueness at DB-level for `sales_daily`: `(date, store_id, product_id)`.
- Ingest must use `ON CONFLICT` upserts (replay-safe).

---

## 6) ForecastOps (Training + Backtesting + Registry)

### 6.1 Model Zoo (Minimum)
- naive
- seasonal naive
- moving average (configurable window)

### 6.2 Feature Engineering (Time-Safe)
- Compute features with an explicit **cutoff**.
- Lags/rolling windows must use history `<= cutoff` only.

### 6.3 Backtesting Protocol
- Time-based CV only: rolling or expanding splits (no random split).
- Metrics: MAE, sMAPE (pinball loss later if needed).

### 6.4 Model Registry
Each run stores:
- run_id, timestamps
- model_type + model_config (JSON)
- feature_config + schema_version
- data window boundaries
- metrics (JSON)
- artifact URI/path + artifact hash
- optional git_sha

---

## 7) Typed FastAPI Contracts (Serving Layer)

Minimum endpoint categories (planned):
- `POST /ingest/sales-daily` (optional `/ingest/transactions`)
- `POST /train` (returns `run_id`, optional `job_id`)
- `POST /predict`
- `GET /runs`, `GET /runs/{run_id}`
- `GET /data/kpis`, `GET /data/drilldowns`
- `POST /rag/query` (optional `/rag/index` in dev)

Contracts are Pydantic v2 validated and use `response_model` for explicit output typing.

---

## 8) Dashboard (React + Vite)

The UI is intentionally **table-first**:
- Data Explorer
- Model Runs (leaderboard + compare)
- Train & Predict (forms + status)
- Predictions (tabular forecasts)
- RAG assistant panel with citations

Decision reference: `docs/ADR/ADR-0002-frontend-architecture-vite-spa-first.md`

---

## 9) RAG Knowledge Base (Postgres + pgvector)

### 9.1 Indexed Sources (Planned)
- `README.md`
- `docs/*` (Architecture, ADRs, guides)
- OpenAPI export
- Run reports generated per training run

### 9.2 Evidence-Grounded Answers
RAG must return citations for non-trivial claims; if evidence is insufficient, it must respond “not found / insufficient evidence”.

Decision reference: `docs/ADR/ADR-0003-vector-storage-pgvector-in-postgres.md`

---

## 10) Quality, CI, and Review Rules

The repo standards live in `docs/validation/` and are treated as merge gates:
- Ruff lint/format
- Pytest (unit + integration)
- Alembic migration checks
- MyPy + Pyright strict
- Logging taxonomy (`docs/validation/logging-standard.md`)

---

## 11) Roadmap (Phased Delivery)

- **Phase-0**: vertical-slice demo (seed → ingest → baseline train → predict → UI tables)
- **Phase-1**: ForecastOps core (backtesting + registry + leaderboard)
- **Phase-2**: ML models + richer exogenous features
- **Phase-3**: RAG + agentic workflows (PydanticAI), run report generation/indexing
