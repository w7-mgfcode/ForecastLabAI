# ForecastLabAI — Onboarding Guide

> Generated from the Understand-Anything knowledge graph (`.understand-anything/knowledge-graph.json`).
> Snapshot: commit `1f7fd82` · 860 files · 2,434 graph nodes · 5,011 edges · 8 layers.
> This is a navigational map, not a substitute for `README.md`, `AGENTS.md`, or `docs/_base/*`.

---

## 1. Project Overview

**ForecastLabAI** is a portfolio-grade, **single-host retail demand-forecasting system** that exercises the full ML lifecycle and runs end-to-end with one `docker compose up`. It covers: data platform → ingest → time-safe feature engineering → forecasting → backtesting → model registry → RAG → agentic layer → React dashboard.

| | |
|---|---|
| **Backend** | Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · Pydantic v2 · Alembic · structlog |
| **Database** | PostgreSQL 16 + **pgvector** (vector store lives in the same container — no separate service) |
| **ML / AI** | pandas · NumPy · scikit-learn · LightGBM/XGBoost (opt-in) · PydanticAI · OpenAI · Anthropic · tiktoken |
| **Frontend** | React 19 · TypeScript · Vite · Tailwind CSS · shadcn/ui · TanStack Query/Table · React Router · Recharts |
| **Tooling** | uv (Python) · pnpm (JS) · Docker/Compose · GitHub Actions + release-please · ruff · mypy/pyright `--strict` · pytest/Vitest |

**Defining traits to internalize early:**
- **Vertical-slice architecture** — every domain lives under `app/features/<slice>/{models,schemas,service,routes,tests}.py`. A slice may **not** import another slice; cross-cutting code goes through `app/core/` or `app/shared/`.
- **Time-safety is the load-bearing invariant** — feature engineering must never read past the caller's `cutoff_date`. `app/features/featuresets/tests/test_leakage.py` is the executable spec; it must never be weakened.
- **Single-host by design** — no managed-cloud SDK in the core path; `docker compose up` is the only prerequisite besides Python + Node.
- **Docs-first** — work flows `INITIAL-*.md` → `PRPs/PRP-*.md` → vertical-slice implementation → CI gates.

---

## 2. Architecture Layers

The graph groups all 864 file-level nodes into **8 layers**:

| Layer | Files | What lives here |
|-------|------:|-----------------|
| **Backend Core & Infrastructure** | 67 | `app/core/*` (config, db engine, logging, middleware, problem-details, health) + `app/shared/*` (cross-slice ORM, seeder "The Forge"). The cross-cutting foundation every slice depends on. |
| **Backend Feature Slices** | 261 | The 17+ vertical domain slices under `app/features/` (forecasting, agents, registry, rag, scenarios, backtesting, analytics, batch, demo, …), each self-contained. |
| **Data & Migrations** | 23 | Alembic `versions/*` (forward-only migration chain) + SQL example queries that define/evolve the Postgres+pgvector schema. |
| **Frontend (React SPA)** | 240 | `frontend/src/` — pages, shadcn/ui components, TanStack Query hooks, API client/lib, `types/api.ts`, build config. |
| **Documentation & PRPs** | 202 | `docs/`, ADRs, phase guides, and the `PRPs/` / `INITIAL-*` requirement plans that gate every slice. |
| **CI/CD & Containerization** | 26 | `.github/workflows/*`, Dockerfiles, `docker-compose*.yml`, devcontainer. |
| **Scripts & Demos** | 36 | CLI utilities + demo drivers (`scripts/`, `examples/`) outside the app/frontend trees. |
| **Project Configuration** | 9 | Root tooling/env config (`pyproject.toml`, lockfiles, pre-commit, release-please, `.env.example`). |

---

## 3. Key Concepts & Patterns

- **The vertical slice (read one to learn all).** `models.py` (SQLAlchemy ORM) → `schemas.py` (Pydantic v2 boundary) → `service.py` (business logic) → `routes.py` (HTTP) → `tests/`. The **registry** slice is the cleanest exemplar.
- **RFC 7807 errors everywhere.** All errors return `application/problem+json` via `app/core/problem_details.py` / `app/core/exceptions.py` — never a bare 500, never an ad-hoc error shape.
- **Config through one door.** Feature code reads `app/core/config.get_settings()` (cached singleton) — never `os.environ` directly. Use `pathlib.Path`, never `os.path`.
- **Async ORM.** `app/core/database.py` owns the async engine, session-maker, `get_db` dependency, and declarative `Base`. Every model inherits `Base`; every service opens a session through `get_db`.
- **Time-safe features.** Lags via `shift(k)`, rolling via `shift(1).rolling(...)`, entity-aware `groupby` — enforced by `test_leakage.py`.
- **Forward-only migrations.** Once an Alembic migration merges, never edit it — add a new one. CI's `migration-check` replays the chain on a fresh DB every PR.
- **HITL agent gate.** Mutating PydanticAI tools (`create_alias`, `archive_run`, `save_scenario`) block on human approval via `agent_require_approval`. Never widen the agent's mutation surface without adding the tool there.
- **Registry trust model.** A run moves `pending → running → success/failed → archived`; an alias may point only to a `success` run; artifacts are SHA-256-verified with path-traversal prevention.

---

## 4. Guided Tour (recommended reading order)

A 14-step path from entry point to single-host deploy. Each step names the files to open.

1. **Project Overview** — `README.md` + `AGENTS.md`. The roadmap, stack, validation gates, and vertical-slice brief every later step assumes.
2. **Application Entry Point** — `app/main.py`. FastAPI factory: wires every slice's router, CORS, request-ID middleware, RFC 7807 handlers, lifespan. The bird's-eye map of the backend surface.
3. **Core: Config, DB, Errors** — `app/core/config.py` (cached `get_settings()`), `app/core/database.py` (async engine, `get_db`, `Base`), `app/core/problem_details.py`. Highest-fan-in backend files — breakage cascades.
4. **The Data Platform (Domain Model)** — `app/features/data_platform/models.py`. The 7-table retail core (store/product/calendar/sales_daily/price_history/promotion/inventory) + Phase-2 tables. The vocabulary the whole system speaks; grain = one `sales_daily` row per store × product × date.
5. **Time-Safe Feature Engineering** — `app/features/featuresets/service.py` + `tests/test_leakage.py`. Leakage-prevented lag/rolling/calendar/exogenous/lifecycle features; the test is the spec.
6. **Forecasting & Backtesting** — `forecasting/service.py` + `models.py` (model zoo), `backtesting/splitter.py` (expanding/sliding folds), `backtesting/metrics.py` (MAE/sMAPE/WAPE/bias/RMSE + per-bucket).
7. **A Slice End-to-End: the Model Registry** — `registry/{models,schemas,service,routes}.py` + `storage.py`. Run state machine, comparable-run/feature-frame invariants, aliases, SHA-256 artifact integrity.
8. **Database Migrations** — `alembic/versions/`. Forward-only chain applied via `alembic upgrade head` at container start; CI replays it every PR.
9. **RAG Knowledge Base (pgvector)** — `rag/service.py`. Idempotent (content-hash) indexing + HNSW retrieval inside the same Postgres container; embedding dim is fixed per provider.
10. **The Agentic Layer with HITL** — `agents/service.py`, `deps.py`, `websocket.py`. PydanticAI sessions, streaming, and the human-in-the-loop approval gate for mutating tools.
11. **Frontend Contract & Data Layer** — `frontend/src/types/api.ts` (mirrors backend schemas; most-depended-on file in the repo), `lib/api.ts` (fetch + RFC 7807 → typed `ApiError`), `hooks/use-demo-pipeline.ts`.
12. **A Key Page: the Showcase** — `frontend/src/pages/showcase.tsx` (drives the live demo pipeline in-browser) + `knowledge.tsx` (RAG corpus + semantic search).
13. **The End-to-End Demo Pipeline** — `app/features/demo/pipeline.py`. Capstone: seed → features → train → backtest → register → alias → RAG → agent in-process; mirrors `scripts/run_demo.py`.
14. **Containerization, CI, Config** — `docker-compose.yml`, `Dockerfile.backend`, `.github/workflows/ci.yml` (4 blocking gates), `pyproject.toml`.

---

## 5. File Map — the highest-leverage files

**Most-depended-on (fan-in) — change these carefully:**

| File | Importers | Role |
|------|----------:|------|
| `frontend/src/types/api.ts` | 116 | Single source of truth for backend schema types |
| `app/core/config.py` | 68 | Cached settings singleton |
| `app/core/database.py` | 51 | Async engine / session / `Base` |
| `frontend/src/components/ui/button.tsx` | 47 | shadcn primitive |
| `frontend/src/components/ui/card.tsx` | 46 | shadcn primitive |
| `frontend/src/lib/utils.ts` | 44 | FE utility helpers (`cn`, etc.) |
| `app/features/data_platform/models.py` | 43 | De-facto shared ORM layer (all fact-table FKs) |
| `frontend/src/lib/api.ts` | 42 | Fetch wrapper + RFC 7807 parsing |
| `app/core/logging.py` | 41 | structlog setup |
| `app/features/forecasting/schemas.py` | 34 | Forecast train/predict contracts |
| `app/shared/seeder/config.py` | 33 | Seeder scenario presets ("The Forge") |
| `app/main.py` | 28 | Router/middleware wiring hub |

**By layer (entry points to start reading):**
- **Backend Core** → `app/main.py`, `app/core/{config,database,problem_details,exceptions,logging,middleware,health}.py`
- **Feature Slices** → pick one and read M→S→S→R→T; `registry/` is the model slice, `forecasting/` and `agents/` are the richest
- **Data & Migrations** → `alembic/versions/*` (newest = current schema), `examples/*.sql`
- **Frontend** → `types/api.ts` → `lib/api.ts` → `hooks/*` → `pages/showcase.tsx`
- **Scripts & Demos** → `scripts/run_demo.py`, `scripts/seed_random.py`

---

## 6. Complexity Hotspots — approach carefully

Files the analyzer rated **complex**. Concentrated in **batch**, **forecasting**, **analytics**, **agents/tools**, and **backtesting**:

- **Batch slice** — `batch/runner.py` (bounded-concurrency async runner w/ cancel/drain), `batch/service.py`, `batch/models.py`, `batch/tests/test_runner.py`. Concurrency + cancellation semantics; read the tests alongside the code.
- **Forecasting** — `forecasting/models.py` (baseline→regression→LightGBM/XGBoost/prophet-like factory), `forecasting/service.py` (leakage-safe regression matrices), `forecasting/schemas.py` (config union), plus its test suite (`test_service`, `test_models`, `test_feature_metadata`, `test_persistence`, `test_schemas`).
- **Analytics** — `analytics/{service,routes,schemas}.py` + integration tests (SQL GROUP-BY aggregation; date-range validation).
- **Agents / tools** — `agents/tools/registry_tools.py` & `backtesting_tools.py` (HITL-gated mutations), `agents/tests/test_tools.py`.
- **Backtesting** — `backtesting/metrics.py` (metric math + per-bucket aggregation), `backtesting/schemas.py`.
- **Core** — `app/core/exceptions.py` (domain exception hierarchy → RFC 7807 handlers).

> Gotcha worth flagging: Pydantic v2 **strict mode** on request bodies 422s ISO-string values for `date`/`datetime`/`UUID`/`Decimal` unless the field has `Field(strict=False, ...)` — see `forecasting/tests/test_schemas.py` and `app/core/tests/test_strict_mode_policy.py`.

---

## 7. Getting Started (validation gates)

```bash
cp .env.example .env                      # set OPENAI_API_KEY / ANTHROPIC_API_KEY
docker compose up -d                      # Postgres+pgvector on :5433
uv sync --extra dev                       # backend deps (Python 3.12)
uv run alembic upgrade head               # migrations
uv run uvicorn app.main:app --reload --port 8123
cd frontend && corepack enable pnpm && pnpm install && pnpm dev   # UI on :5173
```

Run before every commit (all five gate merge in CI):

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/   # both --strict
uv run pytest -v -m "not integration"
```

`make demo` runs the full end-to-end pipeline; the **Showcase** page (`/showcase`) drives it live in-browser.

---

*Explore interactively:* `/understand-anything:understand-dashboard` · *Ask questions:* `/understand-anything:understand-chat` · *Deep-dive a file:* `/understand-anything:understand-explain`.
