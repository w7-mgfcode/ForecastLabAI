# ForecastLabAI Developer Guide
> HUMAN-MAINTAINED — do not overwrite via the generating-claudemd skill.

## What This Project Is

ForecastLabAI is a portfolio-grade, single-host retail demand forecasting system that exercises the full lifecycle: data platform → ingest → time-safe features → forecasting → backtesting → model registry → RAG → agentic layer → React dashboard. It is pre-1.0, released on a release-please-driven SemVer train, and runs end-to-end on a developer laptop with nothing but `docker-compose up`, Python 3.12, and Node.

## Tech Stack

See `CLAUDE.md` Stack section and `pyproject.toml` for the authoritative dependency list. The stack favours a single-host, dependency-light footprint: FastAPI + SQLAlchemy 2.0 async + Pydantic v2 for a strictly-typed backend, PostgreSQL 16 with pgvector so the vector store needs no separate service (`docs/ADR/ADR-0003`), and a Vite SPA rather than a server-rendered frontend (`docs/ADR/ADR-0002`). No managed-cloud SDK sits in the core path — that is a deliberate constraint from `.claude/rules/product-vision.md`.

## Local Development Setup

Authoritative quick-start lives in `README.md`. The short version:

```bash
cp .env.example .env                          # set your OPENAI_API_KEY / ANTHROPIC_API_KEY
docker compose up -d                          # Postgres+pgvector on :5433
uv sync --extra dev                            # Python 3.12 deps
uv run alembic upgrade head                    # migrations
uv run uvicorn app.main:app --reload --port 8123
cd frontend && corepack enable pnpm && pnpm install && pnpm dev
```

Host-specific notes:

- **WSL:** `.venv/bin/*` and `frontend/node_modules/.bin/*` binaries can become corrupt `IntxLNK` blobs after a Windows file-server bridge event — the symptom is `cannot execute binary file`. Rebuild with `rm -rf .venv && uv sync --extra dev` and `rm -rf frontend/node_modules && cd frontend && pnpm install && pnpm rebuild esbuild`.
- **pnpm 11:** `pnpm dev` can stall on the `depsStatusCheck` preflight reinstalling esbuild. Bypass it with `./node_modules/.bin/vite --host 0.0.0.0`, or add `pnpm.onlyBuiltDependencies: ["esbuild"]` to `frontend/package.json`.
- **Frontend API base:** `frontend/.env` `VITE_API_BASE_URL` must resolve from the browser's host — point it at `http://localhost:8123` for local work.

See `docs/_base/RUNBOOKS.md` → "Common Incidents" for the full list.

## Running Tests

```bash
uv run pytest -v -m "not integration"          # unit (fast, no DB)
docker compose up -d
uv run pytest -v -m integration                # integration (real Postgres)
cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run
```

There is no enforced coverage percentage; the gate is `.claude/rules/test-requirements.md`. Every new module, public function, API endpoint, SQLAlchemy model, and Alembic migration ships with a matching test, and every bug fix ships a regression test that would have caught it. A new vertical slice gets its own `app/features/<slice>/tests/` directory with a `conftest.py` for fixtures and `test_<module>.py` files — unit tests mock external services (OpenAI, Anthropic, Ollama), integration tests are marked `@pytest.mark.integration` and run against the real `docker-compose` Postgres. Never mock the database in an integration test.

## Project Conventions

Authoritative rules live in `.claude/rules/` and are surfaced in `docs/_base/RULES.md`. The non-obvious gotchas worth highlighting here:

- Vertical-slice imports: `app/features/X` may NOT import from `app/features/Y`. Cross-cutting code goes to `app/shared/` or `app/core/`.
- The seeder is the only sanctioned bulk-mutation path on the DB.
- All API errors use the RFC 7807 `application/problem+json` envelope via `app/core/problem_details.py` — never raise a bare `HTTPException` with a raw string.
- Time-safety is load-bearing: `app/features/featuresets/tests/test_leakage.py` is the spec and must never be weakened to make a feature pass.
- Alembic migrations are forward-only once merged — fix forward with a new migration, never edit a merged one.
- Read settings via `app/core/config.get_settings()`; never touch `os.environ` directly in feature code.
- Agent tools that mutate state must be listed in `agent_require_approval` so the human-in-the-loop gate fires.
- Commits follow `type(scope): description (#issue)` and reference an open issue; branches are `<type>/<kebab-slug>` off `dev`.

## Why We Chose These Technologies

- ADRs live in `docs/ADR/` — see `docs/ADR/ADR-INDEX.md`.
- **pgvector over a managed vector DB** — keeps the system single-host; one `docker-compose up` brings up Postgres and the vector store together (`docs/ADR/ADR-0003`).
- **Vite SPA over server-side rendering** — keeps the backend a pure JSON + WebSocket API with no rendering concerns, so the frontend can be developed and deployed independently (`docs/ADR/ADR-0002`).
- **PydanticAI for the agent layer** — its typed tool-call contracts fit the repo's strict-typing invariant, so LLM tool inputs are validated the same way HTTP request bodies are.

## Common Troubleshooting

See `docs/_base/RUNBOOKS.md` — "Common Incidents" section covers the recurring traps (frontend `Loading...` from misconfigured `VITE_API_BASE_URL`, pnpm 11 `depsStatusCheck`, WSL `.venv` corruption, `.env`-bleed in Settings tests).

## Contacts & Resources

- Maintainer: Gabor Szabo (`@w7-mgfcode`)
- Issue tracker: GitHub Issues on this repo
- Release tracker: `CHANGELOG.md` (release-please-managed)
- Out-of-repo links: none — this is a single-maintainer portfolio repo with no Slack/Notion workspace and no hosted demo URL (the system runs locally only). All coordination happens through GitHub Issues and PRs.
