# CI and quality gates

What must pass before code merges, what runs in GitHub Actions, and how a release happens.

**Purpose:** get a change through the pipeline without surprises.
**Intended reader:** integrators contributing code.

## What you'll accomplish

A local check sequence that matches CI, and an understanding of the branch, commit, and release conventions.

## The local gates

Run these before every commit. They mirror what CI enforces, so a green local run is a strong predictor of a green pipeline.

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/        # both --strict
uv run pytest -v -m "not integration"
```

Frontend work adds:

```bash
cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run
```

**Two type checkers, both strict, both gating.** That is deliberate rather than redundant: mypy and pyright disagree about enough real cases that passing both is a meaningfully stronger guarantee than passing either.

Integration tests need a live database and are excluded from the fast loop:

```bash
docker compose up -d
uv run pytest -v -m integration
```

They run against **real** Compose Postgres. Mocking the database in an integration test is forbidden — a mocked integration test proves nothing about the thing it names.

## The CI workflow

`.github/workflows/ci.yml` runs on push, pull request, and manual dispatch, with in-progress runs cancelled when a newer commit lands on the same ref.

| Job | Runs |
|---|---|
| **Lint & Format** | `ruff check` and `ruff format --check`. |
| **Type Check** | `mypy app/` then `pyright app/`. |
| **Test** | Migrations against a service Postgres, then the suite. |
| **Migration Check** | Applies migrations to a **fresh** database, then verifies no pending migrations remain. |

Dependencies install with `uv sync --frozen --all-extras --dev` — `--frozen` means the lockfile is authoritative, so a `uv.lock` that drifted from `pyproject.toml` fails CI rather than silently resolving something new.

### Migration Check is the subtle one

It does two things a normal test run does not: it proves migrations apply cleanly **from empty**, and it proves the ORM models and the migration history agree — that autogenerate would produce nothing new.

That second check catches the common mistake of changing a `models.py` and forgetting the migration. Locally everything works, because your database already has the column from a previous manual step. On a fresh database it does not exist.

## Other workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `cd-release.yml` | push to `main` | Release automation. |
| `e2e-nightly.yml` | nightly cron (07:00 UTC) + dispatch | Full end-to-end run. |
| `schema-validation.yml` | changes to `alembic/**`, `**/models.py`, `core/database.py` | Path-scoped schema checks. |
| `dependency-check.yml` | weekly cron (Sun 00:00 UTC) + dispatch | Dependency review. |
| `phase-snapshot.yml` | push to `phase-*` branches | Phase snapshots. |

The nightly e2e is what exercises the full pipeline against a real stack — the same ground `make demo` covers locally.

## Branches and commits

**Branches** — `<type>/<kebab-slug>` off `dev`; `hotfix/*` off `main`. One branch per issue.

**Commits** — `type(scope): description (#issue)`:

- `type` ∈ `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `release`
- `scope` from the allow-list in `.claude/rules/commit-format.md`
- lowercase description, no trailing period
- **every commit references an open GitHub issue**

**No AI co-author or "Generated with" trailer.** A hook enforces this — a commit carrying one is rejected.

## The flow

```
branch off dev  →  implement  →  run the gates  →  PR into dev  →  CI green  →  merge
```

Releasing:

```
PR dev → main  →  release-please opens a Release PR  →  merging it tags vX.Y.Z
```

**release-please owns tagging.** Do not push tags by hand. Versioning is SemVer, and the project is pre-1.0 — which means `feat:` commits produce **PATCH** bumps, not MINOR. That surprises people who expect standard SemVer behavior; it is correct for a 0.x line.

Never `git push --force` on `dev` or `main`.

## Stop and ask before

- Cutting `dev` → `main`, or pushing any tag.
- Bumping pydantic-ai, FastAPI, or SQLAlchemy major versions.
- Widening an agent's mutation surface without adding the tool to `agent_require_approval`.

## When CI fails and local passed

**`uv sync --frozen` failed** — `uv.lock` is out of step with `pyproject.toml`. Re-lock and commit the lockfile.

**Migration Check failed but tests passed** — you changed a model without a migration. Your local database already had the column.

**pyright failed where mypy passed** — the checkers disagree; both must pass. Usually a narrowing or overload case.

**An integration test failed only in CI** — it depends on state a previous local run left behind. Reproduce with a clean database: `docker compose down -v && docker compose up -d`.

## Next

- [Extending ForecastLabAI](extending.md) — what to build, and what not to touch.
- [AGENTS.md](../../../AGENTS.md) — the full rule set these gates enforce.
