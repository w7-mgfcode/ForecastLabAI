# AGENTS.md

> Universal agent brief for **ForecastLabAI** — the shared, cross-tool source of truth read by any AI coding agent (Claude Code, Cursor, GitHub Copilot, Gemini CLI, Aider, Zed, …). Claude Code additionally reads `CLAUDE.md`, which imports this file; do not duplicate this content there.

## Project Overview

ForecastLabAI is a portfolio-grade, **single-host retail demand-forecasting** system that exercises the full lifecycle: data platform → ingest → time-safe feature engineering → forecasting → backtesting → model registry → RAG → agentic layer → React dashboard. It is pre-1.0, runs end-to-end on one machine via `docker compose up`, and ships working code in every vertical slice — not specs.

## Tech Stack

- **Backend** — Python 3.12: FastAPI + SQLAlchemy 2.0 async + Pydantic v2; structlog; Alembic migrations.
- **Frontend** — TypeScript 5.9 + React 19: Vite 7, Tailwind 4, shadcn/ui (New York), TanStack Query + Table, React Router 7, Recharts.
- **Database** — PostgreSQL 16 + pgvector (host `:5433` → container `:5432`).
- **ML** — pandas, numpy, scikit-learn, joblib, LightGBM (opt-in).
- **Agents / RAG** — PydanticAI, anthropic, openai, tiktoken; Ollama optional for local embeddings.
- **Package managers** — `uv` (Python), `pnpm` via corepack (JS).
- **CI/CD** — GitHub Actions + release-please (SemVer; pre-1.0 `feat:` → PATCH bumps).

## Setup

```bash
cp .env.example .env                           # set OPENAI_API_KEY / ANTHROPIC_API_KEY
docker compose up -d                           # Postgres+pgvector on :5433
uv sync --extra dev                            # backend deps (Python 3.12)
uv run alembic upgrade head                    # apply migrations
uv run uvicorn app.main:app --reload --port 8123
cd frontend && corepack enable pnpm && pnpm install && pnpm dev   # UI on :5173
```

## Build & Test Commands

Use these exact strings.

```bash
# Backend tests
uv run pytest -v -m "not integration"          # unit, no DB
uv run pytest -v -m integration                # integration, requires docker compose up

# Frontend
cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run

# End-to-end demo (seed → features → train ×3 → backtest → register → alias → agent)
make demo
```

## Validation Gates

Run before every commit. All five gate merge in CI — never skip them.

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/        # both --strict
uv run pytest -v -m "not integration"
```

## Architecture & Conventions

- **Vertical slices** — every domain lives under `app/features/<slice>/{models,schemas,service,routes,tests}.py`. A slice may NOT import from another slice; cross-cutting code goes through `app/core/` or `app/shared/`. Routers are wired in `app/main.py`.
- **Errors** — RFC 7807 `application/problem+json` via `app/core/problem_details.py`. No bare `HTTPException` with raw strings; no ad-hoc error shapes.
- **Validation** — Pydantic v2 at every boundary (HTTP, agent tools, seeder config). ORM uses `Mapped[]` + `mapped_column()` + async sessions.
- **Config** — read settings via `app/core/config.get_settings()`; never touch `os.environ` in feature code. Use `pathlib.Path`, never `os.path`.
- **Time-safety** — feature engineering must prevent leakage (`shift(lag)`, `shift(1).rolling()`, entity-aware `groupby`). `app/features/featuresets/tests/test_leakage.py` is the spec.
- **Migrations** — every schema change ships an Alembic migration; migrations are forward-only once merged.
- **UI** — frontend work goes through the design skills referenced in `.claude/rules/ui-design.md`; never hand-roll UI when a skill applies.

## Testing Requirements

- Every new module, public function, API endpoint, SQLAlchemy model, and Alembic migration ships with a matching test; every bug fix ships a regression test that would have caught it.
- Unit tests mock external services (OpenAI / Anthropic / Ollama). Integration tests are marked `@pytest.mark.integration` and run against the real docker-compose Postgres.
- New endpoints need a route test covering the 2xx happy path plus at least one error path.

## Safety

**Hard rules — never violate:**

- Never commit `.env` or embed secrets in URLs, code, or logs — only `.env.example` is tracked; log key names, never values.
- Never build SQL with string concatenation — only SQLAlchemy 2.0 parameter binding.
- Never use `eval` / `exec` / `pickle.loads` on untrusted input, `subprocess(shell=True, …)` with user input, or `verify=False` on httpx / openai clients.
- Never skip `ruff`, `mypy --strict`, or `pyright --strict` — all gate merge.
- Never edit a merged Alembic migration — migrations are forward-only; add a new one.
- Never weaken `app/features/featuresets/tests/test_leakage.py` — it is the leakage spec.
- Never mock the database in integration tests — they must run against real docker-compose Postgres.
- Never `git push --force` on `dev` or `main`; never add an AI co-author or "Generated with" commit trailer.
- Never add a managed-cloud SDK (AWS/GCP/Azure) to the `app/` core path — it violates the single-host vision.

**Stop and ask before:**

- Cutting `dev` → `main`, or pushing any tag (release-please owns tagging).
- Bumping pydantic-ai / FastAPI / SQLAlchemy major versions.
- Widening an agent's mutation surface without adding the tool name to `agent_require_approval`.

Agent-tool and Pydantic strict-mode specifics: see `docs/_base/SECURITY.md`.

## Git & PR Conventions

- **Branches** — `<type>/<kebab-slug>` off `dev` (`hotfix/*` off `main`). One branch per issue. See `.claude/rules/branch-naming.md`.
- **Commits** — `type(scope): description (#issue)`. Type ∈ {feat, fix, docs, refactor, test, chore, release}; scope from the allow-list in `.claude/rules/commit-format.md`; lowercase description, no trailing period; every commit references an open GitHub issue. No AI co-author / "Generated with" trailer (a hook enforces this).
- **Flow** — branch off `dev` → implement → run the validation gates → PR into `dev` → CI green → merge. Release: PR `dev` → `main`; release-please opens a Release PR; merging it tags `vX.Y.Z`.

## Deep-Dive Docs

Load only what the current task touches.

- Developer guide & stack — `docs/_base/DEV_GUIDE.md`
- Architecture & boundaries — `docs/_base/ARCHITECTURE.md`
- API & WebSocket contracts — `docs/_base/API_CONTRACTS.md`
- Operational runbooks — `docs/_base/RUNBOOKS.md`
- Security & compliance — `docs/_base/SECURITY.md`
- Rules & constraints — `docs/_base/RULES.md`
- Domain model & glossary — `docs/_base/DOMAIN_MODEL.md`
- Service & dependency map — `docs/_base/REPO_MAP_INDEX.md`
- CI/CD pipeline contract — `docs/_base/PIPELINE_CONTRACT.md`
- Project rules — `.claude/rules/*.md`
