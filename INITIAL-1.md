# INITIAL-1.md — Repo Governance + CI/CD + Branching

## FEATURE:
- Branch policy:
  - `main` is protected
  - merges into `main` only from `dev` via PR
  - `phase-*` branches are immutable snapshots (must not be deleted)
- GitHub Actions CI gates:
  - ruff (lint + format check)
  - pytest
  - migrations check (apply on a fresh DB)
  - (optional) mypy/pyright strict gating
- Standard PR template + issue templates + CODEOWNERS (if needed).

## EXAMPLES:
- `examples/ci/local_checks.sh` — runs the same checks locally as CI.
- `.github/workflows/run-tests.yml` — uses a Postgres service container for migrations + tests.
- `.github/pull_request_template.md` — checklist: tests, migrations, docs, no-hardcode.

## DOCUMENTATION:
- GitHub Actions: service containers + caching best practices
- Ruff / Pytest / Alembic workflows
- Branch protection + required checks

## OTHER CONSIDERATIONS:
- CI must be deterministic (locked dependencies / pinned versions).
- Migration checks should enforce both “apply on empty DB” and “no pending revisions”.
- Base CI should not require external secrets (local DB + seed).
