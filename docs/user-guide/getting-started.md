# Getting Started with ForecastLab

This guide takes you from a fresh clone to a running ForecastLab system with data,
trained models, and a working dashboard — in about ten minutes.

## What ForecastLab Is

ForecastLab is a **retail demand-forecasting system** you run on a single machine. It
covers the whole forecasting lifecycle end to end:

1. **Data platform** — stores, products, calendar, daily sales, prices, promotions, inventory.
2. **Ingest** — load sales data through a batch API.
3. **Feature engineering** — build time-safe features (lags, rolling windows, calendar effects).
4. **Forecasting** — train baseline and machine-learning models.
5. **Backtesting** — measure accuracy with time-series cross-validation.
6. **Model registry** — track every trained model, compare runs, promote a champion.
7. **RAG knowledge base** — semantic search over project documentation.
8. **AI agents** — a chat assistant that can run experiments and answer questions.
9. **Dashboard** — a React web app that surfaces all of the above.

It is built for learning, demos, and portfolio use. It is **not** a multi-tenant SaaS,
not a real-time streaming system, and needs no cloud account — everything runs locally.

## Prerequisites

- **Docker** (for the PostgreSQL database)
- **Python 3.12** with [`uv`](https://docs.astral.sh/uv/) (the Python package manager)
- **Node.js** with `pnpm` (enabled through `corepack`)

## Install and Run

Run these from the repository root.

```bash
# 1. Configure environment — add your OpenAI / Anthropic API keys to .env
cp .env.example .env

# 2. Start PostgreSQL + pgvector (listens on host port 5433)
docker compose up -d

# 3. Install backend dependencies
uv sync --extra dev

# 4. Apply database migrations
uv run alembic upgrade head

# 5. Start the backend API (http://localhost:8123)
uv run uvicorn app.main:app --reload --port 8123
```

In a second terminal, start the web dashboard:

```bash
cd frontend
corepack enable pnpm
pnpm install
pnpm dev          # dashboard at http://localhost:5173
```

Open **http://localhost:5173** in your browser. The interactive API documentation
(Swagger UI) is available at **http://localhost:8123/docs**.

## Load Data and See It Work

A fresh database is empty. The fastest way to see the whole system in action is the
**end-to-end demo**, which seeds data, computes features, trains three models,
backtests them, registers the winner, and exercises the agent:

```bash
make demo
```

You can also watch the same pipeline run live in the browser on the **Showcase** page
(see the Dashboard Guide). To generate data without the full pipeline, use the
**Admin** page or the seeder API directly.

## Key Ports and URLs

| Service        | URL                          |
|----------------|------------------------------|
| Dashboard      | http://localhost:5173        |
| Backend API    | http://localhost:8123        |
| API docs       | http://localhost:8123/docs   |
| PostgreSQL     | localhost:5433               |

## If Something Goes Wrong

- **Dashboard shows "Loading…" everywhere** — the frontend cannot reach the backend.
  Check that the API is running (`curl http://localhost:8123/health`) and that
  `frontend/.env` has `VITE_API_BASE_URL=http://localhost:8123`.
- **Database connection refused** — make sure `docker compose up -d` succeeded and
  migrations are applied (`uv run alembic upgrade head`).
- **API keys** — the AI agent and RAG features need `OPENAI_API_KEY` and/or
  `ANTHROPIC_API_KEY` set in `.env`. Forecasting and the dashboard work without them.
- **Browser dogfood / UI verification** — run `./scripts/dogfood-browser.sh` to
  verify Playwright + snap chromium are ready for headless dashboard exercises;
  pass a Python file path to execute it through the prepared environment.

## Next Steps

- **Dashboard Guide** — a tour of every page in the web app.
- **Feature Reference** — what each part of the system does and its API endpoints.
- **Agents and RAG Guide** — how the chat assistant and knowledge base work.
