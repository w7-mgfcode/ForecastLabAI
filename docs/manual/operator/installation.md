# Installation

From an empty checkout to a backend that answers `/health` and a dashboard that loads.

**Purpose:** get the stack running, with each step's pass condition stated.
**Intended reader:** operators installing for the first time.

## What you'll accomplish

A migrated PostgreSQL database, a backend serving on `:8123`, and a dashboard on `:5173`. The database will still be **empty** — filling it is [Seeding data](seeding-data.md), and the fastest route to a working system is [Quickstart](quickstart.md).

## Prerequisites

| Requirement | Why |
|---|---|
| **Docker + Docker Compose v2** | PostgreSQL 16 with the pgvector extension. |
| **Python 3.12+** with [`uv`](https://docs.astral.sh/uv/) | Backend runtime and dependency management. |
| **Node.js 20+** with `pnpm` (via `corepack`) | The dashboard. Skip if you only want the API. |

An LLM API key is **optional** — see [Optional: AI features](#optional-ai-features).

## 1 · Configure the environment

```bash
cp .env.example .env
```

`.env` is never committed; only `.env.example` is tracked. The defaults work as-is for a local install — you only need to edit it for the optional AI features.

Every variable is documented in the [configuration reference](../configuration.md). Note that `.env.example` ships the commonly-changed subset, not the full surface.

## 2 · Start PostgreSQL + pgvector

```bash
docker compose up -d
```

**Pass condition:** `docker compose ps` shows the Postgres service healthy, publishing host port **5433**.

Port 5433 is deliberate — it avoids colliding with a Postgres you may already run on 5432. The container still listens on 5432 internally; 5433 is only the host-side publication.

## 3 · Install backend dependencies

```bash
uv sync --extra dev
```

Two forecasting models are opt-in extras. Add them now if you want them:

```bash
uv sync --extra dev --extra ml-lightgbm     # then set FORECAST_ENABLE_LIGHTGBM=true
uv sync --extra dev --extra ml-xgboost      # then set FORECAST_ENABLE_XGBOOST=true
```

Installing the extra is only half — each model also needs its `forecast_enable_*` flag set to `true`. The flags are permission gates, not installation checks, so setting one without the library fails later at fit or unpickle time rather than at startup. `random_forest` is the exception: set `FORECAST_ENABLE_RANDOM_FOREST=true` and nothing else, since it is pure scikit-learn.

## 4 · Apply database migrations

```bash
uv run alembic upgrade head
```

**Pass condition:** `uv run alembic current` reports a revision. Migrations are forward-only once merged — after any `git pull`, run this again.

## 5 · Verify database connectivity

```bash
uv run python scripts/check_db.py
```

This confirms the application can reach *and authenticate to* the database — a stricter check than the container being healthy.

## 6 · Start the backend

```bash
uv run uvicorn app.main:app --reload --port 8123
```

**Pass condition:**

```bash
curl http://localhost:8123/health
# {"status":"ok"}
```

The interactive OpenAPI contract is now at **http://localhost:8123/docs**. That schema is generated from the code and is the authoritative API reference; this manual explains it rather than restating it.

## 7 · Start the dashboard

In a second terminal:

```bash
cd frontend
corepack enable pnpm
pnpm install
pnpm dev
```

**Pass condition:** http://localhost:5173 loads. With an empty database the KPI cards read zero — that is correct, not a failure.

The dashboard reads one variable of its own, `VITE_API_BASE_URL` (default `http://localhost:8123`), from `frontend/.env`. It is a **build-time** variable: changing it requires restarting `pnpm dev`, not just a hot reload.

## Ports

| Service | URL |
|---|---|
| Dashboard | http://localhost:5173 |
| Backend API | http://localhost:8123 |
| API docs (OpenAPI) | http://localhost:8123/docs |
| PostgreSQL | localhost:5433 |

## Optional: AI features

The chat agents and OpenAI-backed embeddings need a key in `.env`:

```bash
OPENAI_API_KEY=sk-…
# and/or
ANTHROPIC_API_KEY=sk-ant-…
```

Without a key, **forecasting, backtesting, the registry, the Explorer, and every analytical page still work.** Only `/chat` and OpenAI embeddings are unavailable.

To avoid external services entirely, run embeddings and the agent locally through Ollama — set `RAG_EMBEDDING_PROVIDER=ollama` and an `ollama:` agent model. Mind `rag_embedding_dimension`: it must match the model's output width (1536 for OpenAI `text-embedding-3-small`, 768 for `nomic-embed-text`). It is a fixed-width column, so changing it is a migration, not a settings edit.

These settings are also editable at runtime with no restart from **`/admin` → AI Models** — see [Runtime-editable settings](../configuration.md#runtime-editable-settings-no-restart).

## Everything in containers instead

If you would rather not install Python and Node locally:

```bash
make docker-up          # full stack in containers
make docker-up-gpu      # same, plus Ollama on GPU
```

Container mode changes how the backend reaches the database (`postgres:5432`, not `localhost:5433`). See [Running the stack](running-the-stack.md).

## Verifying the whole install

The honest end-to-end check is the demo pipeline, which exercises seed → features → train → backtest → register → alias → agent:

```bash
make demo
```

`make demo` requires the backend to **already be serving** on `:8123` — it drives the running API rather than starting one. See [Quickstart](quickstart.md).

## Next

- [Quickstart](quickstart.md) — get to a working system with trained models.
- [Troubleshooting](../troubleshooting.md) — if a pass condition above did not hold.
