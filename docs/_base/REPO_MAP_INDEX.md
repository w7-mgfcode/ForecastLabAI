# Repo Map Index
> LLM: Read this index first. Load individual docs ONLY when the current task touches
> that domain. Do NOT pre-load all docs.
>
> Last updated: 2026-05-11 | Generator: w7_generating-claudemd skill (heuristic mode) | Docs: 8

## System at a Glance

ForecastLabAI is a portfolio-grade, single-host retail-demand-forecasting system. One developer maintains it; one `docker-compose up` brings it up. The backend is FastAPI + SQLAlchemy 2.0 async against PostgreSQL 16 + pgvector; the frontend is React 19 + Vite + Tailwind 4 + shadcn/ui. Nineteen vertical slices under `app/features/` cover the full lifecycle (data platform → ingest → features → forecasting → backtesting → registry → RAG → agents → dashboard surfaces). Pre-1.0; release-please drives SemVer; merges flow `dev` → `main`.

## Document Index

> NOTE: `docs/_kB/repo-map/` does NOT exist in this repo. Run the `mapping-repo-context` skill to populate it; once present, this index can be regenerated against the KB. The table below points at the **actual** discovery surface today.

| File | What it answers | Load when... |
|------|-----------------|--------------|
| [`README.md`](../../README.md) | Canonical quick-start, feature list, endpoint reference, frontend stack | Onboarding, demoing, sanity-checking an endpoint shape |
| [`CLAUDE.md`](../../CLAUDE.md) | Operating index, commands, conventions, safety | Start of every Claude session |
| [`CHANGELOG.md`](../../CHANGELOG.md) | release-please-managed release notes | Investigating when behavior changed |
| [`pyproject.toml`](../../pyproject.toml) | Dependencies, ruff/mypy/pyright/pytest config | Tooling questions, version bumps |
| [`docker-compose.yml`](../../docker-compose.yml) | Local Postgres+pgvector definition | Debugging DB connectivity, ports |
| [`Makefile`](../../Makefile) | `make demo` / `demo-quick` / `demo-clean` entry points (PRP-15) | Running the end-to-end demo pipeline |
| [`scripts/run_demo.py`](../../scripts/run_demo.py) | End-to-end pipeline driver — seed → features → train ×3 → backtest → register → alias → agent | First-run demonstrability, integration debugging |
| [`app/features/demo/`](../../app/features/demo/) | In-process e2e demo slice — `POST /demo/run` + `WS /demo/stream` drive the pipeline via `ASGITransport` (no cross-slice imports) | Showcase page, in-product demo |
| [`frontend/src/pages/showcase.tsx`](../../frontend/src/pages/showcase.tsx) | The Showcase page — streams the live pipeline into the dashboard as status cards | Demoing the system in-browser |
| [`frontend/src/pages/knowledge.tsx`](../../frontend/src/pages/knowledge.tsx) | The Knowledge page — indexed RAG corpus, live semantic search, and live system state | Surfacing what the agents can draw on |
| [`frontend/src/pages/guide.tsx`](../../frontend/src/pages/guide.tsx) | The Agent Guide page — agent tools, approval gate, live session limits, example prompts | Explaining how to use the chat agents |
| [`frontend/src/pages/explorer/store-detail.tsx`](../../frontend/src/pages/explorer/store-detail.tsx) | The store detail page — entity profile, date-scoped KPIs, revenue-over-time chart, top-products drilldown | Investigating a single store |
| [`frontend/src/pages/explorer/product-detail.tsx`](../../frontend/src/pages/explorer/product-detail.tsx) | The product detail page — profile, KPIs, revenue + lifecycle-demand curves, top-stores drilldown | Investigating a single product |
| [`frontend/src/pages/explorer/run-detail.tsx`](../../frontend/src/pages/explorer/run-detail.tsx) | The model-run detail page — profile, JSON config/metrics/runtime info, store/product cross-links, artifact integrity verify, compare link | Investigating a single model run |
| [`frontend/src/pages/explorer/job-detail.tsx`](../../frontend/src/pages/explorer/job-detail.tsx) | The job detail page — profile, params/result JSON, error details, linked run, cancel action, live polling | Investigating a single job |
| [`frontend/src/pages/explorer/run-compare.tsx`](../../frontend/src/pages/explorer/run-compare.tsx) | The run-comparison page — two run pickers, side-by-side profile, config_diff, metrics_diff with delta indicators; deep-linkable via `?a=&b=` | Comparing two model runs |
| [`frontend/src/pages/visualize/demand.tsx`](../../frontend/src/pages/visualize/demand.tsx) | The Demand Planner page — completed `predict` jobs rolled into a multi-SKU table (tomorrow/next-week/next-month demand + inventory requirement), lead-time selector, single-SKU drill-in | Answering "how much will this SKU sell, and do I have enough stock?" |
| [`app/features/scenarios/`](../../app/features/scenarios/) | Scenario Simulation slice — `/scenarios/simulate` (stateless what-if) + `scenario_plan` CRUD + `/scenarios/compare`; pure `adjustments.py` heuristic factors and `feature_frame.py` (leakage-safe future X for the `model_exogenous` re-forecast); `agent_tools.py` is the agent-integration seam; never imports a sibling `service.py` | What-If planning, baseline-vs-scenario comparisons, model-driven re-forecasts |
| [`frontend/src/pages/visualize/planner.tsx`](../../frontend/src/pages/visualize/planner.tsx) | The What-If Planner page — pick a baseline predict job, define price/promotion/holiday/inventory/lifecycle assumptions, run a simulation, save / tag / reload / delete named plans, and rank 2-5 saved plans in a multi-scenario comparison | Answering "what if we discount this SKU 15% next week?" |
| [`alembic/versions/`](../../alembic/versions/) | Migrations through `43e35957a248_create_scenario_plan_table.py` | DB-schema questions, migration drift |
| [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) | Phase-by-phase architecture narrative | High-level component reasoning |
| [`docs/PHASE-index.md`](../PHASE-index.md) | Index of all 11 phase docs | Locating per-phase deep-dive |
| [`docs/PHASE/*.md`](../PHASE/) | Per-phase implementation reference | Slice-specific deep dives |
| [`docs/ADR/ADR-INDEX.md`](../ADR/ADR-INDEX.md) | Architectural decision records | Why a tech choice was made |
| [`docs/DAILY-FLOW.md`](../DAILY-FLOW.md) | Developer day-in-the-life loop | Onboarding a contributor |
| [`docs/GIT-GITHUB-GUIDE.md`](../GIT-GITHUB-GUIDE.md) | Branch/PR/release workflow | Anything git/PR-related |
| [`docs/PHASE-FLOW.md`](../PHASE-FLOW.md) | INITIAL → PRP → code pipeline | Authoring new feature requests |
| [`docs/validation/*.md`](../validation/) | Tooling standards (ruff, mypy, pyright, pytest, logging) | Configuring/justifying CI gates |
| [`docs/github/`](../github/) | CI/CD workflow reference + diagrams | Pipeline troubleshooting |
| [`docs/rag-ollama-setup.md`](../rag-ollama-setup.md) | Local-embedding setup | Switching off OpenAI embeddings |
| [`docs/DATA-SEEDER.md`](../DATA-SEEDER.md) | "The Forge" seeder operating guide | Generating / refreshing local data |
| [`PRPs/PRP-*.md`](../../PRPs/) | Per-phase project requirements plans (PRP-0 through PRP-13) | Implementing or extending a phase |
| [`INITIAL-*.md`](../../PRPs/INITIAL/) | Pre-PRP discovery docs | Tracing a feature back to its origin |
| [`.claude/rules/*.md`](../../.claude/rules/) | Project rules (commit-format, branch-naming, security-patterns, product-vision, test-requirements, ui-design, versioning, output-formatting) | Any behavioral decision Claude makes |
| [`.claude/skills/`](../../.claude/skills/) | Slash-command skills (audit-rules-drift, commit-format-check, issue-to-subtasks, repo-visibility-audit, w7_generating-claudemd, …) | Picking the right workflow |
| [`.claude/hooks/check-commit-format.sh`](../../.claude/hooks/check-commit-format.sh) | Pre-commit enforcement of `type(scope): description (#issue)` | Debugging blocked commits |
| [`HANDOFF.md`](../../HANDOFF.md) | Latest session handoff | Resuming context across sessions |
| [`.handoffs/`](../../.handoffs/) | Archived handoffs | Historical session context |
| [`docs/_base/ARCHITECTURE.md`](ARCHITECTURE.md) | System boundaries, components, comm patterns | Architectural changes, blast radius |
| [`docs/_base/API_CONTRACTS.md`](API_CONTRACTS.md) | HTTP + WebSocket endpoint surface | API changes, integration |
| [`docs/_base/RUNBOOKS.md`](RUNBOOKS.md) | Common incidents + resolutions | Debugging, recovery |
| [`docs/_base/SECURITY.md`](SECURITY.md) | Threat model, secrets, scanning | Security review, audit |
| [`docs/_base/RULES.md`](RULES.md) | Change authority + invariants | Any sensitive change |
| [`docs/_base/DOMAIN_MODEL.md`](DOMAIN_MODEL.md) | Aggregates, invariants, ubiquitous language | Naming, modeling, new entity |
| [`docs/_base/DEV_GUIDE.md`](DEV_GUIDE.md) | Human-maintained onboarding (stub) | Onboarding (after a human fills it in) |
| [`docs/_base/PIPELINE_CONTRACT.md`](PIPELINE_CONTRACT.md) | CI/CD stages, merge gates, release flow | CI changes, release planning |

## Dependency Hotspots (high blast-radius targets)

| Component | Why it's hot | Risk |
|-----------|--------------|------|
| `app/core/database.py` | Every slice's `service.py` opens a session through it | CRITICAL — breakage cascades |
| `app/core/problem_details.py` | Every error path serializes through it | HIGH — affects all error responses |
| `app/main.py` | Wires every router; central CORS + middleware | HIGH — wiring regression blocks the API |
| `app/features/data_platform/models.py` | Every fact table FK lands here | HIGH — migration drift breaks many tests |
| `app/features/featuresets/tests/test_leakage.py` | Load-bearing spec | HIGH — weakening it lets leakage land |
| `app/features/agents/service.py` + `tools/*` | HITL gates + tool wiring | HIGH — security boundary |
| `alembic/versions/` | Forward-only; CI `migration-check` enforces | HIGH — edit-after-merge corrupts deploys |

## Tech Stack Snapshot

| Category | Technology | Status |
|----------|------------|--------|
| Backend language | Python 3.12 | Pinned |
| Backend framework | FastAPI ≥ 0.115 + Pydantic v2 + SQLAlchemy 2.0 async | Pinned |
| ML / data | pandas ≥ 3, numpy ≥ 2.4, scikit-learn ≥ 1.6, joblib, LightGBM (opt-in) | Pinned |
| Agents | PydanticAI ≥ 1.80, anthropic ≥ 0.50, openai ≥ 1.40 | Pinned |
| RAG | pgvector ≥ 0.3, tiktoken ≥ 0.7, Ollama (optional) | Pinned |
| Frontend | React 19, Vite 7, TypeScript 5.9, Tailwind 4, shadcn/ui (New York) | Pinned |
| Primary DB | PostgreSQL 16 + pgvector (`pgvector/pgvector:pg16`) | Pinned |
| Package manager | uv (Python), pnpm via corepack (JS) | Pinned |
| IaC | none — `docker-compose` single-host | By design (`product-vision.md`) |
| Orchestration | none — single uvicorn process | By design |
| CI/CD | GitHub Actions + release-please | Pinned |

## Index Update History (last 5 generations)

| Date | Change | Who |
|------|--------|-----|
| 2026-05-11 | Initial generation (heuristic mode — `docs/_kB/repo-map/` absent) | w7_generating-claudemd skill |
