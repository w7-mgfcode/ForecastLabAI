# Running the stack

The two ways to run ForecastLabAI — host mode and container mode — how they differ, and when the difference bites.

**Purpose:** choose a mode deliberately and know what changes when you switch.
**Intended reader:** operators running the system beyond a first install.

## What you'll accomplish

A running stack in whichever mode suits you, and a clear model of which hostname reaches which service from where.

## The two modes

**Host mode** — Postgres in Docker; backend and frontend run directly on your machine. Best for development: `--reload` works, breakpoints work, edits are instant.

**Container mode** — everything in Docker, including backend and frontend. Best for demos and for "does this work on a clean machine" checks.

They differ in exactly one thing that matters: **network identity**.

## The hostname rule

| From | Reaches Postgres at | Reaches Ollama at |
|---|---|---|
| Your machine (host mode) | `localhost:5433` | `localhost:11434` |
| Inside a container | `postgres:5432` | `ollama:11434` |

The Compose file publishes Postgres as `5433:5432` — host port 5433, container port 5432. Host port 5433 avoids colliding with a Postgres you may already run.

The backend container sets `DATABASE_URL` and `OLLAMA_BASE_URL` in its own `environment:` block, which **overrides whatever `.env` holds**. This is why `.env` can keep the host-mode defaults: container mode does not read them.

Nearly every "works from my terminal but not in the container" problem is this table.

## Host mode

```bash
docker compose up -d postgres                           # database only — name the service
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8123        # terminal 1
cd frontend && pnpm dev                                 # terminal 2
```

**Name the service.** Plain `docker compose up -d` starts `postgres`, `backend`, **and** `frontend` — only `ollama` is profile-gated. In host mode you are running the backend and frontend yourself, so starting their containers too is redundant, and the backend container will fail its healthcheck until migrations are applied.

## Container mode

```bash
make docker-up      # docker compose up -d --wait --wait-timeout 90
```

`--wait` blocks until the healthchecks pass, so the command returning means the stack is genuinely ready — not merely started. All three services (postgres, backend, frontend) declare healthchecks.

Stop with:

```bash
make docker-down    # stops and removes containers, KEEPS named volumes
```

Your data survives `docker-down` because it lives in named volumes: `forecastlab_pgdata` (the database), `forecastlab_artifacts` (model artifacts), and `forecastlab_ollama_models` (pulled Ollama models). Removing those volumes — `docker compose down -v` — is what actually destroys data.

## The GPU profile

Ollama is behind a Compose **profile**, so it does not start unless you ask for it:

```bash
make docker-up-gpu
# docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile gpu up -d --wait --wait-timeout 120
```

This adds an `ollama` service on `:11434` with GPU device reservations from the overlay file. Two things to understand:

- **The GPU is for the LLM only.** It accelerates local embeddings and local agent models. The forecasting models are scikit-learn, LightGBM, and XGBoost — **CPU only**, unaffected by this profile. Turning on GPU will not make training faster.
- **Verify host GPU support before invoking it.** The overlay requires a working NVIDIA container runtime; without it, the service fails to start rather than silently falling back to CPU.

The longer wait timeout (120s vs 90s) exists because Ollama's first start is slower.

## Ports

| Service | Host port | Container port | Notes |
|---|---|---|---|
| PostgreSQL + pgvector | 5433 | 5432 | `pgvector/pgvector:pg16` |
| Backend API | 8123 | 8123 | |
| Dashboard | 5173 | 5173 | |
| Ollama | 11434 | 11434 | `gpu` profile only |

## Checking health

```bash
docker compose ps                        # container health
curl http://localhost:8123/health        # {"status":"ok"}
uv run python scripts/check_db.py        # app can reach AND authenticate
uv run alembic current                   # migrations applied
```

`/health` is a liveness probe. It answering `ok` means the backend is up and its database connection works — so a failure above that line is infrastructure, and a failure below it is application logic or your request.

## Which settings need a restart

Almost all of them: `get_settings()` is `@lru_cache`d, so the settings object is built once per process.

The deliberate exception is the AI-model configuration — agent model, embedding provider/model/dimension, and provider API keys — which `/admin` → AI Models persists to the `app_config` table and applies live. Those overrides are re-applied at startup too, so they survive restarts. Everything else in the [configuration reference](../configuration.md) requires bouncing the backend.

Settings that specifically call out a restart requirement: `batch_global_max_parallel`, `model_selection_global_max_parallel`, and the three `forecast_enable_*` model flags.

## Next

- [Operations](operations.md) — jobs, batches, artifacts, and routine upkeep.
- [Troubleshooting](../troubleshooting.md) — when a mode switch breaks something.
