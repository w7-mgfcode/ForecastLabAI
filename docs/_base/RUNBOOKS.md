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

### Multi-container stack failed at step X
**Symptoms:** `make docker-up` exits non-zero, or `docker compose ps` shows one of `postgres` / `backend` / `frontend` as `Health: unhealthy` (or `starting` past the `start_period`).
**Diagnosis:**
```bash
docker compose ps --format json | python3 -c "import sys,json; [print(json.loads(l)['Service'],'=>',json.loads(l)['Health']) for l in sys.stdin if l.strip()]"
docker compose logs <unhealthy-svc> --tail 50
```
**Resolution:** one of the following, by failure mode.

1. **Backend logs show `getaddrinfo failed` on `postgres`.** Postgres wasn't healthy when the backend started despite the `depends_on: service_healthy` gate (rare — usually a cold-start race after a `docker system prune`). Restart: `docker compose restart backend`. If it persists, `docker compose down && make docker-up` from a clean state.
2. **`curl http://localhost:8123/health` from the host returns ECONNREFUSED, but `docker compose ps` says `backend healthy`.** Port 8123 is held by a host-side process (a stale `uv run uvicorn` from an earlier session). Resolve: `lsof -iTCP:8123 -sTCP:LISTEN` to find the PID and kill it, or stop the container's port publish and try again.
3. **Frontend reachable from the host but a backend `curl http://frontend:5173` fails.** This is **expected** — the browser is the consumer of the frontend, never the backend. No backend → frontend hop exists; if you have a feature that needs one, it belongs in a follow-up PRP (CORS + a container-DNS origin).
4. **Frontend page shows `Loading...` after `make docker-up`.** A stale `frontend/.env` is overriding the container's `environment:` block with a LAN IP. Remove or reset the bind-mounted `frontend/.env`; the container ships `VITE_API_BASE_URL=http://localhost:8123` which is the browser-correct value.
5. **`make docker-up-gpu` brought everything up but Ollama is `unhealthy` or `nvidia-smi` inside the container errors.** The host is missing `nvidia-container-runtime`. Verify with `docker info | grep -i runtime` (must show `nvidia`) and `nvidia-smi` on the host. If it isn't installed, install the NVIDIA Container Toolkit per <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>, then `sudo systemctl restart docker` and try again.
6. **`make docker-up` returns 0 but a service is still `starting` 60 s later.** Inspect via `docker compose logs <svc> --tail 100`. The most common culprit is alembic taking longer than `start_period: 30s` to apply migrations on a slower host — bump the healthcheck `start_period` in `docker-compose.yml` if this is reproducible.
7. **Migration error inside backend logs after the schema changed.** The backend container ran `alembic upgrade head` at entrypoint. If the migration is failing, check `docker compose logs backend --tail 80` for the SQLAlchemy / alembic stack trace, fix the migration on a branch, rebuild the backend image (`docker compose build backend`), and bring the stack back up.

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

### `make demo` fails at step X
**Symptoms:** `scripts/run_demo.py` prints `❌ Step N/11: <name> -- ...` and exits 1 (step failure) or 2 (precondition).
**Diagnosis flow:**
1. **Precheck failed (exit 2)** — backend isn't reachable on the URL the script is hitting.
   ```bash
   curl -s http://localhost:8123/health   # should print {"status":"ok"}
   docker compose ps                       # confirm Postgres is up on :5433
   ```
   Fix: start uvicorn (`uv run uvicorn app.main:app --port 8123`) and/or `docker compose up -d`. The Makefile targets `demo` and `demo-clean` invoke `docker compose up -d` for you; `demo-quick` does not.
2. **Seed step failed** — production-guard or scenario mismatch. The script POSTs `demo_minimal` to `/seeder/generate`; check `app_env != "production"` (or set `seeder_allow_production=true` if you really mean it). The scenario must exist in `app/shared/seeder/config.py:ScenarioPreset` (added by PRP-15 / issue #128).
3. **Features step failed** — schema drift on `ComputeFeaturesRequest`. The script sends a minimal `FeatureSetConfig` with `name="demo_featureset"` + lag/rolling/calendar configs; if a recent change tightened a `Field(strict=...)` constraint, the failure surfaces here.
4. **Train step failed (one of three)** — the script trains naive / seasonal_naive / moving_average in parallel via `asyncio.gather`. Check the failing model's RFC 7807 body (echoed in the script output); the `request_id` correlates with the uvicorn logs.
5. **Backtest produced NaN WAPE** — `demo_minimal` is tuned to avoid the SPARSE-style NaN trap (moderate `noise_sigma=0.10`, no sparsity). If you customized the scenario and now hit NaN, follow the `app/shared/seeder/tests/test_phase1_regression.py` pattern.
6. **Register step failed** — most likely `pending → success` instead of the mandatory `pending → running → success` transition, or `alias_name` doesn't match the registry pattern (`^[a-z0-9][a-z0-9\-_]*$`). The script uses `demo-production` which is compliant; only worry if you forked the script.
7. **Agent step showed ⏭️ but you expected ✅** — `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` not set in the environment the backend reads. Verify with `grep -E '^(OPENAI|ANTHROPIC)_API_KEY=' .env` (name only — never paste the value).

**Wall-clock soft-warn:**
- `⚠️ Result: GREEN (over budget ...)` — the run succeeded but exceeded the 180 s budget. Not a failure; expected on slower hardware. The integration test (`tests/test_e2e_demo.py`) follows the same soft-warn semantics.

**Capture artifacts for a postmortem:**
```bash
# Nightly CI uploads .ci-logs/uvicorn.log on failure (e2e-nightly.yml).
# Locally, capture both streams:
uv run python scripts/run_demo.py --seed 42 --quiet 2>&1 | tee demo.log
```

### Showcase page (`/showcase`) pipeline fails at step X
**Symptoms:** The dashboard Showcase page (`/showcase`) — or `POST /demo/run` — shows a step card flip to ❌, the run stops, and the summary banner is red.
**Diagnosis flow (matches `app/features/demo/pipeline.py` step names):**
1. **`status` step fails** — `skip_seed=true` (the default) ran against an empty database. Seed first: tick **Re-seed first** on the page, or `POST /seeder/generate` the `demo_minimal` scenario, or run `make demo` once.
2. **`register` step fails with `HTTP 500 -- Database Error`** — the registry's `_find_duplicate` hit multiple pre-existing `model_run` rows with the same config hash (accumulated by prior `make demo` / `run_demo.py` runs). Not a demo-slice bug — the demo correctly surfaces the registry's 500. Fix by clearing stale runs or running against a fresh database.
3. **`agent` step shows ⏭️** — no API key matches the configured `agent_default_model` provider, or the provider rejected the key. Expected; not a failure. The pipeline still goes green.
4. **Page shows an `error` banner ("Pipeline could not start")** — either the start frame was malformed, or another run is already in progress (`409`). Only one demo pipeline runs at a time (module-level `asyncio.Lock`). Wait for the active run to finish.
5. **`phase2_enrichment` step fails (PRP-38, `showcase_rich` only)** — `POST /seeder/phase2-enrichment` returned RFC 7807 with `title="Unprocessable Entity"` and a `detail` mentioning "Empty dimensions or calendar". Cause: the scenario picker is on `showcase_rich` but **Re-seed first** wasn't ticked AND the DB doesn't have a seeded dataset yet. Fix: tick **Re-seed first** OR call `POST /seeder/generate` with `scenario=showcase_rich` once before running the showcase.
6. **`historical_backfill` step shows ⏭️ (PRP-38, `showcase_rich` only)** — date window is shorter than `3 * (horizon + 1) + min_train_size = 75 days`. Cause: the `showcase_rich` scenario should produce a 180-day window, so a skip here means the dataset was previously seeded with a smaller scenario (e.g. `demo_minimal`'s 92-day window) and the showcase ran with `skip_seed=true`. Fix: tick **Re-seed first** so the scenario picker's preset takes over the existing data; the next run will have 180 days.
7. **`v2_train` step fails with `model_path does not contain 'artifacts/models/'` (PRP-38, `showcase_rich` only)** — `POST /forecasting/train` returned a relative path that doesn't match the R1 contract. Cause: someone changed `forecast_model_artifacts_dir` and the path no longer lives under `artifacts/models/`. Fix: revert the config change OR update step_v2_train's assertion to match the new convention.
8. **V2 Feature Frame panel on `/explorer/runs/{id}` is empty after a green `showcase_rich` run (PRP-38)** — happens when the `v2_run_id` was registered with `runtime_info_extras={"feature_frame_version": 2}` but the bundle on disk doesn't carry the V2 manifest (e.g. an older bundle copied over). Cause: the `/forecasting/runs/{id}/feature-metadata` endpoint loads the bundle and the bundle's `feature_groups` / `feature_safety_classes` are None for V1 bundles. Fix: rebuild the bundle (re-run the showcase with `Re-seed first` ticked so a fresh V2 bundle lands).
9. **`verify` step shows ⏭️ on a `prophet_like` winner (PRP-38, `showcase_rich` only)** — expected. The V2 winner's `artifact_uri` is the full `artifacts/models/...` path so `/forecasting/runs/{id}/feature-metadata` can resolve it. The `/registry/runs/{id}/verify` endpoint resolves under `registry_artifact_root`; the two roots differ, so verify is skipped gracefully for V2 winners.
**Notes:** the `POST /demo/run` body and `WS /demo/stream` events are documented in `docs/_base/API_CONTRACTS.md`. The pipeline mirrors `scripts/run_demo.py`; the per-step diagnosis for `make demo` above applies to the same steps. PRP-38 added the `scenario` field on `DemoRunRequest` (defaults to `demo_minimal`) and the additive `phase_name` / `phase_index` / `phase_total` fields on every `StepEvent`.

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
