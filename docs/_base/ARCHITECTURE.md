# ForecastLabAI Architecture
> Source: heuristic discovery of `README.md`, `app/main.py`, `app/core/config.py`, `docker-compose.yml`, `.github/workflows/`, `.claude/rules/`. Spot-verified against code on 2026-05-12.
> Last generated: 2026-05-11 · Last verified: 2026-05-12

## System Boundaries

### What This Repo Owns
- The entire stack: FastAPI backend (`app/`), React 19 SPA (`frontend/`), Alembic migrations (`alembic/`), data seeder (`app/shared/seeder/` + `scripts/seed_random.py`), `.claude/` policy + skills + hooks, docs (`docs/`, `PRPs/` incl. `PRPs/INITIAL/`).
- 7-table retail data platform (`store`, `product`, `calendar`, `sales_daily`, `price_history`, `promotion`, `inventory_snapshot_daily`) + registry, jobs, RAG sources/chunks, agent sessions.
- 11 backend vertical slices under `app/features/` + cross-cutting `app/core/` + `app/shared/`.

### What This Repo Depends On
| Dependency | Interface | Owner | Change Process |
|------------|-----------|-------|----------------|
| PostgreSQL 16 + pgvector | `asyncpg` URL `DATABASE_URL` | self (docker-compose) | New extension → migration |
| OpenAI API | `openai>=1.40` via `app/features/rag` + `app/features/agents` | external | Pin model name in config |
| Anthropic API | `anthropic>=0.50` via PydanticAI | external | Pin model name in config |
| Google Gemini (optional) | `google-gla:*` / `google-vertex:*` model IDs | external | Set `GOOGLE_API_KEY` |
| Ollama (optional) | HTTP at `OLLAMA_BASE_URL` | self/LAN | Set `RAG_EMBEDDING_PROVIDER=ollama` |

### What Depends On This Repo
| Consumer | Depends On | Break Risk |
|----------|-----------|------------|
| `frontend/` React SPA | Backend HTTP API + `/agents/stream` WebSocket | HIGH — same repo, both released together |
| External demos / portfolio reviewers | `/docs` (Swagger), `/redoc` | LOW |

No other internal repos consume this one — single-deployment system per `.claude/rules/product-vision.md`.

## Resource Hierarchy

```
ForecastLabAI repo
├── docker-compose.yml          # single Postgres+pgvector container
├── app/                        # FastAPI process (uvicorn :8123)
│   ├── core/                   # config, db engine, logging, middleware, problem-details, health
│   ├── shared/                 # cross-slice models + seeder ("The Forge")
│   └── features/<slice>/       # vertical slices (11 of them)
└── frontend/                   # Vite dev server :5173 (proxies → :8123)
```

## Component Overview

| Component | Language | Type | Path | Wired in |
|-----------|----------|------|------|----------|
| Health | Python | HTTP | `app/core/health.py` | `app/main.py` |
| Dimensions | Python | HTTP read | `app/features/dimensions/` | `app/main.py` |
| Analytics | Python | HTTP read | `app/features/analytics/` | `app/main.py` |
| Jobs | Python | HTTP CRUD | `app/features/jobs/` | `app/main.py` |
| Ingest | Python | HTTP upsert | `app/features/ingest/` | `app/main.py` |
| Featuresets | Python | HTTP compute | `app/features/featuresets/` | `app/main.py` |
| Forecasting | Python | HTTP train/predict | `app/features/forecasting/` | `app/main.py` |
| Backtesting | Python | HTTP run | `app/features/backtesting/` | `app/main.py` |
| Registry | Python | HTTP CRUD + JSONB | `app/features/registry/` | `app/main.py` |
| RAG | Python | HTTP index/retrieve + pgvector | `app/features/rag/` | `app/main.py` |
| Agents | Python | HTTP + WebSocket | `app/features/agents/` | `app/main.py` |
| Seeder | Python | HTTP control | `app/features/seeder/` | `app/main.py` |
| Data platform | Python | ORM only (no router) | `app/features/data_platform/` | imported by services |
| Frontend | TypeScript | SPA | `frontend/src/` | served by Vite |

## Communication Patterns

| Pattern | Used By | Protocol | Auth |
|---------|---------|----------|------|
| Sync HTTP (REST) | Frontend → Backend, demo curl | HTTP/JSON | None (single-tenant; CORS allow-list dev-only) |
| WebSocket streaming | Frontend chat ↔ `/agents/stream` | WS frames | None |
| Process → DB | All services → Postgres | `postgresql+asyncpg` | `DATABASE_URL` user/pass |
| Agent tool calls | PydanticAI → backend services | In-process Python | Pydantic-validated arg schemas |
| RAG embeddings | RAG service → OpenAI / Ollama | HTTPS | `OPENAI_API_KEY` env or Ollama LAN URL |
| Agent LLM calls | Agents → Anthropic/OpenAI/Gemini | HTTPS | provider API key env |

### Cross-slice read-only import pattern

When a feature slice needs to call a service method or read a schema from a
**different** feature slice (e.g., `forecasting/service.py` → `RegistryService`):

- Import at the **call site** (inside the method), not at module scope, IF
  any of these are true:
  - The upstream slice's `schemas.py` imports a type from this slice
  - The downstream slice is loaded by `alembic/env.py` at migration time
  - The import would close an SQLAlchemy registry cycle

- Prefer importing the **service class** over the ORM model — calls go through
  the public surface, not the persistence layer.

- Document the lazy import with a single-line NOTE comment at the top of the
  file naming the cycle it breaks.

Existing precedents:
- `app/features/explainability/service.py:57` — read-only `ModelRun` import
- `app/features/forecasting/service.py` — lazy `RegistryService` / `JobService` /
  `RunStatus` imports inside `get_feature_metadata_for_*` methods (added by
  PRP-31; required because `RunResponse.model_family` computed_field closes
  the cycle at alembic cold-boot)

## Deployment Flow (Causal Chain)

```
PR opened on dev  →  ci.yml (lint + typecheck + test + migration-check)  →  reviewer approve  →  merge to dev
dev → main PR     →  release-please opens Release PR  →  merge Release PR  →  tag vX.Y.Z  →  cd-release.yml (build wheel + upload artifacts to GitHub Release)
Local install     →  docker-compose up -d  →  alembic upgrade head  →  uvicorn  →  vite
```

No staging/prod environments configured. Deployment target is the developer laptop or a single host — there is no managed cloud target and no hosted demo URL. `app_env="production"` exists in config (`app/core/config.py:21`) only to select JSON logging and strict CORS; it does not imply a deployed environment.

## Observability Stack

| Signal | Tool | Retention | Surface |
|--------|------|-----------|---------|
| Logs | `structlog` (JSON in prod, console in dev) | stdout only — process-local | `app/core/logging.py` |
| Request ID | `RequestIdMiddleware` (`app/core/middleware.py`) | per-request | echoed in problem-details `request_id` |
| Errors | RFC 7807 problem+json | per-response | `app/core/problem_details.py` |
| Metrics | none (verified: no Prometheus / OpenTelemetry / Sentry imports in `app/` or `pyproject.toml`) | — | — |
| Traces | none (same verification) | — | — |
| Dashboards | The React app itself surfaces operational state via Jobs/Runs/Health pages | live | `frontend/src/pages/` |
