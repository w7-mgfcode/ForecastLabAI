# ForecastLabAI Runbooks
> Source: heuristic discovery from `docker-compose.yml`, `app/main.py`, `app/core/config.py`, `HANDOFF.md`, `.claude/rules/`. Operational scope is intentionally small — this is a single-host portfolio system.

## Common Incidents

### Frontend shows "Loading..." everywhere
**Symptoms:** Pages mount but every TanStack Query hook stays in pending state.
**Likely causes:**
1. `frontend/.env` `VITE_API_BASE_URL` points at a LAN host the browser can't reach.
2. Backend not running on `:8123`.
3. CORS rejected the origin.
**Diagnosis:**
```bash
curl -s http://localhost:8123/health         # backend reachable?
grep VITE_API_BASE_URL frontend/.env         # what URL is the SPA calling?
```
**Resolution:**
1. Edit `frontend/.env` → `VITE_API_BASE_URL=http://localhost:8123`.
2. Restart Vite: `cd frontend && ./node_modules/.bin/vite --host 0.0.0.0`.
3. If CORS error in browser console, add the origin to `app/main.py` `allow_origins` (dev-only LAN regex already covers `10.x` / `192.168.x` / `172.16-31.x`).

### Database connection refused
**Symptoms:** `asyncpg.exceptions.CannotConnectNowError` or `ConnectionRefusedError` on first request.
**Diagnosis:**
```bash
docker compose ps                            # postgres container running?
docker compose logs postgres | tail -50
```
**Resolution:**
```bash
docker compose up -d                         # bring it up
uv run alembic upgrade head                  # apply migrations
uv run python scripts/check_db.py            # confirm connectivity
```

### Tests pass locally but fail in CI on a fresh DB
**Symptoms:** Integration tests pass on the dev host (which has stale seeded data) and fail in CI.
**Diagnosis:** Integration tests must be idempotent — they may not assume pre-existing rows.
**Resolution:**
```bash
docker compose down -v && docker compose up -d
uv run alembic upgrade head
uv run pytest -v -m integration
```

### `pnpm dev` re-runs install and errors on esbuild
**Symptoms:** pnpm 11 `depsStatusCheck` reinstalls and blocks the esbuild postinstall script.
**Workaround:** `./node_modules/.bin/vite --host 0.0.0.0` directly. Permanent fix: add `pnpm.onlyBuiltDependencies: ["esbuild"]` to `frontend/package.json`.

### Settings tests fail because they pick up the local `.env`
**Symptoms:** `app/core/tests/test_config.py::test_settings_has_defaults` and a few `agents/tests/test_config_validation.py` cases fail when `.env` exists.
**Root cause:** `Settings()` reads `.env` via `SettingsConfigDict(env_file=".env")`.
**Fix:** Use `Settings(_env_file=None)` in those tests to bypass `.env`.

### `.venv` or `frontend/node_modules` binaries become corrupt (WSL only)
**Symptoms:** `python` / `tsc` are reported as `IntxLNK` data blobs; `uv run` / `tsc --noEmit` fails with `cannot execute binary file`.
**Resolution:**
```bash
rm -rf .venv && uv sync --extra dev
rm -rf frontend/node_modules && corepack enable pnpm && cd frontend && pnpm install && pnpm rebuild esbuild
```

### release-please skipped the bump after a dev → main merge
**Symptoms:** `dev → main` PR is merged, `CD Release` workflow on `main` completes in ~10s, **no Release PR** is opened. release-please log shows `No user facing commits found since <sha> - skipping`.
**Root cause:** `gh pr merge --merge` uses the **PR title** as the merge-commit subject. If that subject is a valid conventional commit of a non-bumping type (`chore`, `docs`, `refactor`, `test`, `ci`), release-please reads it at face value, classifies the whole merge as non-bumping, and stops. Prior dev→main merges done via the GitHub web UI used the default `Merge pull request #N from <branch>` subject — non-conventional — so release-please traversed to the underlying commits and bumped correctly.
**Diagnosis:**
```bash
git log origin/main -1 --format='%s'         # if this matches type(scope): ..., that's the trap
gh run view <cd-release-run-id> --log | grep -E "(Considering|No user facing)"
```
**Prevention (any one of):**
- Merge dev → main via the **GitHub web UI** (uses default non-conventional subject).
- Force a non-conventional subject from the CLI: `gh pr merge <N> --merge --subject "Merge pull request #<N> from w7-mgfcode/dev"`.
- Title the dev → main PR with a `feat:` or `fix:` type so the subject bumps regardless.
**Recovery (after the trap fires):**
1. Open an issue tracking the release (`release: cut vX.Y.Z for ...`).
2. Branch off `dev`: `git switch -c feat/release-trigger-X-Y-Z`.
3. `git commit --allow-empty -m "feat(release): trigger vX.Y.Z release for <slice> (#<issue>)"`.
4. PR to `main`, **wait for all four `main` status checks to go green** (Lint & Format, Type Check, Test, Migration Check — enforced at the branch-protection layer since #108), then admin-merge — the empty `feat:` becomes the merge subject and release-please bumps PATCH (pre-1.0 config). Reference example: PRs #99 → #100 → #101 for v0.2.8. Plan ~3-5 min between push and the merge button becoming available.

## Break-Glass Procedures

There is no "production" — break-glass is N/A. The closest equivalent is the seeder:

### Reset to a known-good seeded state
```bash
uv run python scripts/seed_random.py --delete --confirm
uv run python scripts/seed_random.py --full-new --seed 42 --confirm
uv run python scripts/seed_random.py --verify
```

## Secret Rotation

There are no managed secrets — keys live in the developer's `.env`. Rotation = edit `.env`, restart `uvicorn`. Never commit `.env`. `.env.example` is the canonical schema; new env vars must land there first.

## Release / Rollback

### Cut a release
```bash
# from dev, ensure CI green
gh pr create --base main --head dev --title "release: ..."
# merge PR via the GitHub web UI (or with an explicit non-conventional --subject)
#   → release-please opens "chore(main): release X.Y.Z" PR on main
# merge that PR → release-please tags vX.Y.Z and cd-release.yml uploads wheel
```

> ⚠️ **Do NOT** merge with `gh pr merge --merge` if the PR title is a non-bumping conventional commit (`chore(...)`, `docs(...)`, etc.) — the merge-commit subject becomes the PR title verbatim and release-please will skip the bump. See the "release-please skipped the bump after a dev → main merge" incident above.

### Rollback a release
```bash
# undo a tag is destructive; prefer cutting a new patch release with the fix
git revert <bad-commit-sha>
gh pr create --base dev --head fix/<slug>
# proceed through normal release flow → vX.Y.(Z+1)
```

Never `git push --force` on `dev` or `main` (see `.claude/rules/security-patterns.md`).

## Logs & Debugging

- Backend logs: stdout from `uvicorn` (JSON in `production`, console in `development`). Each request carries an `X-Request-ID` header echoed in error bodies (`request_id` field) — grep logs by that ID.
- Frontend network errors: open browser devtools → Network tab → check `/health`, then the failing endpoint's status + RFC 7807 body.
- Agent issues: check `app/features/agents/models.py` `agent_session` table — `message_history` JSONB has the full transcript, including tool calls and pending approvals.
