# Deep Dive: Software Architect

## Scope

This document studies ForecastLabAI as a systems architect would: platform boundaries, component ownership, runtime topology, persistence model, coupling, scaling limits, and evolution paths. It is grounded in `app/main.py`, `app/core/*`, `app/features/*`, `frontend/src/*`, `docker-compose.yml`, `pyproject.toml`, `frontend/package.json`, `alembic/versions/*`, `Makefile`, and the base docs under `docs/_base/`.

## 1. Research

### System identity

ForecastLabAI is a single-host, end-to-end retail demand forecasting product. The repository intentionally owns the full loop:

1. Data platform
2. Batch ingest
3. Leakage-safe feature engineering
4. Forecast training and prediction
5. Backtesting
6. Registry and aliases
7. Scenario planning
8. RAG knowledge base
9. Agentic workflows with approval gates
10. React dashboard surfaces

That identity is enforced both socially and structurally:

- `app/features/<slice>/` defines vertical slices.
- `docker-compose.yml` keeps runtime local and single-host.
- `.claude/rules/product-vision.md` rejects multi-tenant SaaS, streaming infra, and managed-cloud-first expansion.

### Architecture style

The backend is a modular monolith with vertical-slice boundaries. Each slice usually exposes:

- `models.py`
- `schemas.py`
- `service.py`
- `routes.py`
- `tests/`

Cross-cutting concerns live in:

- `app/core/` for config, database, middleware, exceptions, health, problem-details, logging
- `app/shared/` for reusable data-model and feature-frame logic

The frontend is a route-driven SPA with:

- page composition in `frontend/src/pages/*`
- reusable domain components in `frontend/src/components/*`
- server-state access in `frontend/src/hooks/*`
- a thin fetch wrapper in `frontend/src/lib/api.ts`

### Runtime topology

The production-like local topology is small by design:

- Postgres 16 + pgvector
- one FastAPI process
- one Vite/React UI
- optional Ollama container for local embeddings

This yields strong demo portability and a low operational surface, but it also centralizes all CPU-bound training, backtesting, and agent orchestration onto one host.

### Entrypoints and wiring

`app/main.py` is the composition root. It wires:

- middleware
- exception handling
- router registration for all slices
- startup config override replay

This makes `app/main.py` a high-blast-radius file. Any architectural shift that changes router composition, middleware order, or startup behavior lands here.

### Persistence model

The data plane mixes three persistence styles:

1. relational warehouse-like retail data in `app/features/data_platform/models.py`
2. JSONB-heavy operational metadata in registry, jobs, sessions, scenarios
3. pgvector-backed chunk storage in RAG tables

That is a pragmatic design for a portfolio system:

- relational where grain and joins matter
- JSONB where flexibility matters
- vector columns where retrieval matters

The tradeoff is schema readability: business-critical semantics live partly in migrations and partly in JSON payload conventions.

### API surface

The API is broad and coherent. Key groups are:

- exploratory read APIs: `/dimensions`, `/analytics`, `/ops`
- operational execution APIs: `/forecasting`, `/backtesting`, `/jobs`, `/batch`, `/model-selection`
- model governance APIs: `/registry`, `/config`
- AI APIs: `/rag`, `/agents`
- demo and seeding APIs: `/seeder`, `/demo`
- planning APIs: `/scenarios`

Error handling is normalized through RFC 7807 problem details, which is a strong contract decision for a system with many slices.

### Frontend information architecture

The frontend is organized around user intent rather than backend slices:

- Dashboard
- Showcase
- Ops
- Explorer
- Visualize
- Knowledge
- Chat
- Guide
- Admin

This is the right abstraction. The backend is phase-oriented; the UI is workflow-oriented.

### Testing and governance

The repository is heavy on validation:

- `ruff`
- `mypy --strict`
- `pyright --strict`
- unit tests
- integration tests
- migration checks

Observed footprint from the repo:

- 328 Python files under `app/`
- 176 backend test files
- 229 frontend TS/TSX files
- 57 frontend test files
- 18 Alembic migrations

That is a meaningful sign of architecture discipline for a pre-1.0 system.

## 2. Compose A Role-Based Plan

### Architectural reading plan

For an architect onboarding to this codebase, the minimum effective reading order is:

1. `AGENTS.md`
2. `docs/_base/ARCHITECTURE.md`
3. `docs/_base/API_CONTRACTS.md`
4. `docs/_base/DOMAIN_MODEL.md`
5. `app/main.py`
6. `app/core/config.py`
7. `app/core/database.py`
8. `app/features/data_platform/models.py`
9. `app/features/forecasting/service.py`
10. `app/features/rag/service.py`
11. `app/features/agents/service.py`
12. `frontend/src/App.tsx`

### Architecture review plan

Review the system in these lenses:

1. Boundary integrity
   - verify slices depend on `core` and `shared`, not freely on each other
   - pay attention to lazy-import seams already used to break cycles
2. Runtime concentration
   - identify CPU-heavy paths that still run inline on the API host
   - compare jobs, batch, model selection, demo pipeline, and agent activity
3. Data durability
   - map what is canonical in tables versus in JSONB versus on disk artifacts
4. Contract stability
   - inspect how frontend hooks depend on backend shapes and polling behavior
5. AI safety posture
   - inspect where retrieval, tool calling, approval gates, and provider switches can fail

### Architecture decisions already present

The codebase has already made these strategic decisions:

- modular monolith over microservices
- async FastAPI over sync API server
- Postgres as both OLTP-ish store and vector store
- file-based model artifacts instead of external artifact services
- local-first provider switching rather than cloud orchestration
- workflow visibility in-product rather than in external ops tooling

### Near-term architecture planning topics

An architect would likely focus next on:

1. formalizing cross-slice dependency rules with automated checks
2. isolating CPU-heavy training/backtesting from request latency
3. making artifact and JSONB conventions easier to inspect and evolve
4. strengthening app-level observability beyond logs and request IDs
5. reducing hidden coupling between demo orchestration and slice APIs

## 3. Validate

### Evidence that the current architecture is coherent

- The slice map in `app/main.py` matches the product lifecycle.
- `app/core/config.py` centralizes runtime control instead of scattering env reads.
- `app/core/database.py` keeps session creation standardized.
- Multiple services use documented lazy imports to avoid import-cycle collapse.
- `frontend/src/App.tsx` is route-structured and uses lazy loading, which fits the breadth of the UI.
- `docker-compose.yml` keeps the full stack reproducible on one machine.
- `docs/_base/API_CONTRACTS.md` and `docs/_base/DOMAIN_MODEL.md` already track core system invariants.

### Architectural strengths

1. Strong vertical-slice organization
2. Clear local deploy story
3. Typed boundaries everywhere
4. Explicit anti-leakage posture in forecasting/featuresets
5. Practical AI safety guardrails with approval-required mutating tools
6. Good UX-to-backend alignment through workflow-based frontend pages

### Architectural tensions

1. Single-host simplicity versus CPU-heavy ML workflows
2. Slice purity versus necessary cross-slice orchestration
3. JSONB flexibility versus discoverability and query clarity
4. Broad product scope versus maintainability for one repo and one host
5. Local-first AI flexibility versus provider-specific runtime drift

### Main risks

1. `app/main.py` as central blast radius
2. long-running work inside the application process
3. file artifact lifecycle complexity
4. limited observability for concurrency and performance debugging
5. increasing product breadth without a stronger architecture map of ownership and dependency budgets

## 4. Generate

## Generated Architectural Findings

### High-level assessment

ForecastLabAI is a well-shaped modular monolith. It has enough structure to feel like a real platform, but it still preserves a single-machine demo story. That balance is the repository's main architectural achievement.

### What the architecture optimizes for

It optimizes for:

- demonstrability
- local reproducibility
- architectural breadth
- typed boundaries
- explainable workflows

It does not optimize for:

- horizontal scale
- high-throughput asynchronous execution
- multi-tenant isolation
- cloud-native elasticity

Those are intentional non-goals, not omissions.

### Primary architectural seams

The most important seams in the system are:

1. `core` vs feature slices
2. relational facts/dimensions vs JSONB operational state
3. artifact-on-disk vs metadata-in-registry
4. backend phase APIs vs frontend workflow pages
5. deterministic ML pipeline logic vs probabilistic LLM/agent flows

### Best-fit mental model

Treat the repo as four systems sharing one host:

1. a retail analytics API
2. an ML execution engine
3. an AI retrieval-and-agent layer
4. an operator-facing product shell

The design works because those systems are colocated but not completely blended.

### Recommended architectural priorities

1. Add dependency-graph enforcement for slice boundaries.
2. Make long-running model work more explicitly job-owned and easier to isolate.
3. Introduce richer observability around durations, failures, queue-like backlogs, and artifact usage.
4. Publish a canonical artifact contract covering model bundle versions, registry metadata, and scenario compatibility.
5. Continue treating time-safety, RFC 7807, and approval-gated mutation as non-negotiable architectural invariants.

### Final architect view

This repository is already beyond a toy demo. Its value is not just that it has many features, but that those features are connected through consistent contracts. The next architectural challenge is no longer "can it do the whole flow?" but "can the whole flow keep growing without hidden coupling and host saturation?"
