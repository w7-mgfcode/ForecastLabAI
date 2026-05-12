# ForecastLabAI Developer Guide
> HUMAN-MAINTAINED — do not overwrite via the generating-claudemd skill.
> Fill in all {FILL IN} sections; remove this stub marker line when content is complete.

## What This Project Is

{FILL IN: 2 sentences. Suggested seed — "A portfolio-grade, single-host retail demand forecasting system that exercises the full lifecycle: data platform → ingest → time-safe features → forecasting → backtesting → registry → RAG → agents → React dashboard. Pre-1.0; release-please-driven SemVer."}

## Tech Stack

See `CLAUDE.md` Stack section and `pyproject.toml` for authoritative dependency list. {FILL IN: any narrative on why each choice — point to ADRs in `docs/ADR/`.}

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

{FILL IN: any host-specific notes (e.g., WSL caveats from `HANDOFF.md` on corrupt `.venv` / `node_modules` binaries).}

## Running Tests

```bash
uv run pytest -v -m "not integration"          # unit (fast, no DB)
docker compose up -d
uv run pytest -v -m integration                # integration (real Postgres)
cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run
```

{FILL IN: coverage targets if any; how to add a new vertical slice's `tests/`.}

## Project Conventions

Authoritative rules live in `.claude/rules/` and are surfaced in `docs/_base/RULES.md`. The non-obvious gotchas worth highlighting here:

- Vertical-slice imports: `app/features/X` may NOT import from `app/features/Y`. Cross-cutting code goes to `app/shared/` or `app/core/`.
- The seeder is the only sanctioned bulk-mutation path on the DB.
- {FILL IN: any other conventions discovered in practice.}

## Why We Chose These Technologies

- ADRs live in `docs/ADR/` — see `docs/ADR/ADR-INDEX.md`.
- {FILL IN: short narrative for newcomers — e.g., "pgvector chosen over a managed vector DB to keep the system single-host; see ADR-0003."}

## Common Troubleshooting

See `docs/_base/RUNBOOKS.md` — "Common Incidents" section covers the recurring traps (frontend `Loading...` from misconfigured `VITE_API_BASE_URL`, pnpm 11 `depsStatusCheck`, WSL `.venv` corruption, `.env`-bleed in Settings tests).

## Contacts & Resources

- Maintainer: Gabor Szabo
- Issue tracker: GitHub Issues on this repo
- Release tracker: `CHANGELOG.md` (release-please-managed)
- {FILL IN: any out-of-repo links — Slack, Notion, demo URL.}
