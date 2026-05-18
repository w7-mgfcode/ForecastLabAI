# ForecastLabAI

Deep-dive references (Claude loads only when needed):
- Developer guide & tech stack:  @docs/_base/DEV_GUIDE.md
- Architecture & boundaries:     @docs/_base/ARCHITECTURE.md
- API contracts & interfaces:    @docs/_base/API_CONTRACTS.md
- Operational runbooks:          @docs/_base/RUNBOOKS.md
- Security & compliance:         @docs/_base/SECURITY.md
- Rules & constraints:           @docs/_base/RULES.md
- Domain model & glossary:       @docs/_base/DOMAIN_MODEL.md
- Service & dependency map:      @docs/_base/REPO_MAP_INDEX.md
- Pipeline contract (CI/CD):     @docs/_base/PIPELINE_CONTRACT.md

> Project rules already enforced via `.claude/rules/` (commit-format, branch-naming, security-patterns, product-vision, test-requirements, ui-design, versioning, output-formatting). Read those first; this file is the operating index.

## Stack

- Language: Python 3.12 (backend), TypeScript 5.9 + React 19 (frontend)
- Framework: FastAPI + SQLAlchemy 2.0 async + Pydantic v2; Vite 7 + Tailwind 4 + shadcn/ui
- Infrastructure: Single-host `docker-compose` (no K8s, no cloud SDK in core path)
- Database: PostgreSQL 16 + pgvector (port `5433` host → `5432` container)
- CI/CD: GitHub Actions + release-please (SemVer, pre-1.0 patch bumps)

## Architecture

**Owns:** Full vertical-slice retail-demand-forecasting demo — data platform, ingest, feature engineering (time-safe), forecasting, backtesting, model registry, RAG (pgvector), agentic layer (PydanticAI), React dashboard.

**Depends on:** PostgreSQL+pgvector (required), OpenAI/Anthropic/Google API (agent + RAG embeddings), Ollama (optional local embeddings).

**Depended on by:** Nothing internal — single deployment, no consumers. Frontend ↔ backend over HTTP + WebSocket (`/agents/stream`).

**Vertical-slice layout:** Every domain lives under `app/features/<slice>/{models,schemas,service,routes,tests}.py`. Cross-slice code goes through `app/core/` or `app/shared/`. Wire-up in `app/main.py`.

**Core data flow:** Seeder/Ingest → `sales_daily` + dimensions → Featuresets (lag/rolling/calendar, leakage-safe) → Forecasting (naive/seasonal/MA/LightGBM) → Backtesting (rolling/expanding splits) → Registry (runs + aliases) → Serving via `/forecasting`, `/backtesting`, `/analytics`. RAG indexes docs → pgvector → Agents (experiment / rag_assistant) call tools with human-in-loop approval for mutating ops.

## Commands

### Local Development
```bash
docker-compose up -d                          # Postgres+pgvector on :5433
uv sync --extra dev                            # install backend deps (Python 3.12)
uv run alembic upgrade head                    # apply migrations
uv run uvicorn app.main:app --reload --port 8123
cd frontend && pnpm install && pnpm dev       # UI on :5173
```

### Testing
```bash
uv run pytest -v -m "not integration"          # unit, no DB
uv run pytest -v -m integration                # integration, requires docker-compose up
cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run
```

### Validation gates (run before commit)
```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/        # both --strict, both block merge
```

### Database & seeder
```bash
uv run alembic revision --autogenerate -m "<desc>"
uv run python scripts/seed_random.py --full-new --seed 42 --confirm
uv run python scripts/seed_random.py --status
```

## Conventions

- Branches: `<type>/<kebab-slug>` off `dev` (off `main` for hotfix). See `.claude/rules/branch-naming.md`.
- Commits: `type(scope): description (#issue)` — scope from allow-list, no AI co-author trailer, every commit references an open GitHub issue. Hook `.claude/hooks/check-commit-format.sh` enforces it.
- All errors via `app/core/problem_details.py` (RFC 7807 `application/problem+json`).
- Pydantic v2 at every boundary (HTTP, agent tools, seeder config). SQLAlchemy with `Mapped[]` + async sessions.
- Time-safe features only — `app/features/featuresets/tests/test_leakage.py` is the spec; never weaken to make a feature pass.
- UI work goes through the skills in `.claude/rules/ui-design.md` (stitch-design, frontend-design, webapp-testing) — never hand-roll.

## Safety

> Load `docs/_base/RULES.md` for the full constraint matrix.

**STOP and ask before:**
- Cutting `dev` → `main` (release-please will tag) or any tag push
- Editing a merged Alembic migration (migrations are forward-only; create a new one)
- `git push --force` on `dev` or `main` (forbidden)
- Adding a managed-cloud SDK to `app/` core path (violates single-host vision)
- Bumping pydantic-ai / FastAPI / SQLAlchemy major versions

**NEVER:**
- Commit `.env` (only `.env.example` is tracked) or embed secrets in URLs/code/logs
- Use raw SQL string concat — always SQLAlchemy parameter binding
- Disable `verify=False` on httpx / openai clients
- Skip `mypy --strict` or `pyright --strict` — both gate merge
- Add AI co-author trailers to commits (`commit-format.md` forbids it)
- Mock external services in integration tests (use real Postgres via docker-compose)

## Verification

```bash
uv run ruff check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"
gh issue view <N> --json state                # confirm referenced issue exists
wc -l CLAUDE.md                                # must stay ≤ 150
```

## Workflow

1. Open or pick a GitHub issue (`gh issue list`); branch off `dev` per `branch-naming.md`.
2. Implement inside the matching `app/features/<slice>/` (or new slice with PRP).
3. Run `ruff` → `mypy` → `pyright` → `pytest -m "not integration"` locally.
4. (DB/UI touched) Run integration tests + frontend type-check + dogfood via webapp-testing skill.
5. Commit with `type(scope): description (#issue)`; push.
6. Open PR into `dev`; CI must be green; merge.
7. When ready to release: PR `dev` → `main`. release-please opens a Release PR; merge to tag.

## Learnings

<!-- Session-specific discoveries Claude should remember. Update sparingly. -->
- HEURISTIC_MODE generated this doc (no `docs/_kB/repo-map/` KB). Run `mapping-repo-context` to upgrade fidelity; sections marked `[ASSUMPTION]` in `docs/_base/` need verification.
