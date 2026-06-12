# ForecastLabAI Technical Concepts And Tech Stack

## Overview

ForecastLabAI is a single-host retail demand forecasting platform implemented as a modular monolith with a React SPA frontend. It combines data-platform, ML, RAG, and agentic capabilities in one repository and one local runtime topology.

## Layered technical model

| Layer | Main technology | Responsibility |
|---|---|---|
| UI | React 19, TypeScript 5.9, Vite 7, Tailwind 4, shadcn/ui | Workflow surfaces, charts, controls, streaming UX |
| API | FastAPI, Pydantic v2 | Typed HTTP and WebSocket contracts |
| Services | Python service modules per slice | Business logic and orchestration |
| Persistence | SQLAlchemy 2.0 async, PostgreSQL 16, pgvector | Relational data, JSONB state, vector retrieval |
| ML | pandas, numpy, scikit-learn, joblib, optional LightGBM/XGBoost | Forecast training, prediction, evaluation |
| AI | PydanticAI, OpenAI, Anthropic, optional Gemini and Ollama | RAG embeddings, agent reasoning, tool use |
| Tooling | uv, pnpm, Alembic, Ruff, mypy, pyright, pytest | Development, quality, migration, release |

## Backend stack

### Runtime and framework

- Python 3.12
- FastAPI
- Uvicorn
- Pydantic v2
- Pydantic Settings v2

Key concepts:

- async request handling
- typed request and response models
- RFC 7807 error contracts
- startup lifecycle hooks
- WebSocket streaming for agents and demo pipeline

### Data access

- SQLAlchemy 2.0 async ORM
- `asyncpg` driver
- session creation via `app/core/database.py`
- migration management via Alembic

Key concepts:

- `Mapped[]` ORM typing
- `mapped_column()`
- async session dependency injection
- commit/rollback at request scope

### Persistence patterns

ForecastLabAI uses three persistence patterns:

1. relational dimensions and facts
   - `store`, `product`, `calendar`, `sales_daily`, `price_history`, `promotion`, `inventory_snapshot_daily`
2. operational JSONB-rich entities
   - runs, jobs, sessions, scenarios, config
3. vector-backed retrieval entities
   - RAG sources and chunks with embeddings

### Cross-cutting backend concepts

- centralized settings in `app/core/config.py`
- structured logging via `structlog`
- request correlation via middleware
- problem-details serialization for failures
- strict type-checking as a design constraint, not just a lint step

## Frontend stack

### Core libraries

- React 19
- TypeScript 5.9
- Vite 7
- React Router
- TanStack Query
- TanStack Table
- Recharts
- Tailwind CSS 4
- shadcn/ui and Radix primitives
- Lucide icons

### Frontend concepts

- route-oriented application shell
- lazy-loaded page modules
- React Query hooks for API state
- reusable domain components
- helper libraries for formatting and transform logic
- dedicated WebSocket hook for streaming flows

### Major frontend domains

- dashboard and KPI summaries
- explorer pages for stores, products, jobs, runs, and sales
- visualize pages for forecasting, backtesting, batch, champion selection, demand, and planning
- showcase page for the full demo pipeline
- knowledge page for RAG state and retrieval
- chat page for agent interaction
- admin page for AI provider and model settings

## ML and forecasting stack

### Core packages

- pandas
- numpy
- scikit-learn
- joblib
- optional LightGBM
- optional XGBoost

### Core concepts

- time-safe feature engineering
- train/predict split by service boundary
- backtesting with time-series folds
- model-family and feature metadata
- persisted model bundles
- registry-backed governance and aliases

### ML design choices

- baselines remain first-class
- advanced models are optional extras
- artifact persistence is local filesystem based
- scenario simulation differentiates heuristic and model-driven methods
- model selection is a distinct workflow, not a side effect of training

## RAG and agent stack

### RAG

- pgvector
- OpenAI embeddings or Ollama embeddings
- chunkers by source type
- similarity retrieval with thresholding
- idempotent indexing using content hashes

### Agents

- PydanticAI
- Anthropic and OpenAI as main hosted providers
- optional Gemini identifiers supported in config
- tool-calling with schema validation
- approval gate for mutating actions
- session persistence in Postgres
- streaming token/tool events over WebSocket

### AI control-plane concepts

- live provider switching through config APIs
- fallback model support
- session TTL and tool-call caps
- timeout and retry controls
- explicit allow-lists for model identifier providers

## Database and schema stack

### Database

- PostgreSQL 16
- pgvector extension
- local port `5433` to container `5432`

### Migration management

- Alembic
- forward-only migration policy after merge
- 18 migrations observed in the repo at inspection time

### Data model concepts

- star-schema-like retail data platform
- JSONB for flexible operational entities
- vector embeddings inside Postgres instead of a separate vector store

## Development and quality stack

### Backend package and environment tooling

- `uv`
- `.env` + Pydantic settings

### Frontend package tooling

- `pnpm`
- corepack-enabled workflow

### Quality gates

- Ruff
- mypy `--strict`
- pyright `--strict`
- pytest

### CI/CD

- GitHub Actions
- release-please

Key pipeline concepts:

- blocking lint, typecheck, test, and migration jobs
- Release PR flow from `dev` to `main`
- wheel and sdist build on release creation

## Runtime topology

### Core local services

1. Postgres
2. backend API
3. frontend dev server
4. optional Ollama

### Container strategy

- Docker Compose for local orchestration
- bind mounts for hot reload
- shared named volume for artifacts
- health checks for all main services

## Architectural conventions enforced by the stack

1. Vertical slices own their business logic.
2. `core` and `shared` are the sanctioned cross-cutting surfaces.
3. Schema changes require migrations.
4. API boundaries require Pydantic validation.
5. Time-safe feature engineering is mandatory.
6. AI mutation tools require approval.
7. The product must remain single-host runnable.

## Why this stack fits the repo

The stack fits because the product needs:

- a fast local development loop
- typed API and schema boundaries
- strong data tooling for forecasting
- one database that can handle relational and vector workloads
- a modern dashboard frontend
- enough AI flexibility to compare hosted and local providers

The stack would be a poor fit for a high-scale multi-tenant SaaS, but that is not the repository's goal.
