name: "PRP-32 — Dockerize ForecastLabAI Full Stack (Backend + Frontend + Postgres + opt-in Ollama)"
description: |
  Extend the existing single-container `docker-compose.yml` (Postgres+pgvector only) into a
  four-service Compose stack — `postgres` (unchanged), `backend` (FastAPI), `frontend`
  (React/Vite), `ollama` (opt-in `gpu` profile) — so the full system comes up with
  `make docker-up` on a dev laptop or a GPU host. Adds two Dockerfiles, a `.dockerignore`,
  a GPU override file, three `make` targets, an integration test that locks in the
  "no `localhost` for cross-container hops" invariant, runbook + README + ollama-setup
  doc updates. Source plan: `.agents/plans/dockerize-full-stack-rev2.md`.

## Purpose

Close the onboarding gap: today the quick-start needs four host-side toolchains
(`uv`, `pnpm`, Python 3.12, Node) and two terminals; only Postgres is in Compose.
Reviewers, CI matrix runners, and the maintainer-after-context-loss all pay that
tax. After this PRP lands, `make docker-up` brings up the whole system, and the
existing host-mode flow keeps working unchanged.

## Core Principles

1. **Additive only** — no schema changes, no migrations, no breaking API edits, no
   slice boundary changes. Existing `docker compose up -d` semantics (Postgres-only)
   stay valid; new services are extensions.
2. **Honors the single-host vision** (`.claude/rules/product-vision.md`) — pgvector
   stays the vector store per ADR-0003; no Qdrant, no managed-cloud SDK added.
3. **Ollama opt-in** — gated by a `gpu` Compose profile so non-GPU laptops are
   unaffected; the cloud-OpenAI default in `RAG_EMBEDDING_PROVIDER=openai` is unchanged.
4. **Strict gates honored** — `ruff` + `mypy --strict` + `pyright --strict` + `pytest`
   all green; new test file follows `tests/test_e2e_demo.py` precedent.
5. **Runtime-verified library claims** — every Docker / uv / Compose / asyncpg /
   pnpm claim in this PRP was validated on the dev host before the PRP was written;
   verification commands are inlined in "Known Gotchas" so a future reader can
   re-verify on a version bump. (Motivated by issue #258 — `[[histgbr-no-feature-importances]]`
   + `[[simpleimputer-drops-empty-columns]]` precedents.)

---

## Goal

A single command, `make docker-up`, builds two new images (`forecastlab-backend:dev`,
`forecastlab-frontend:dev`) and brings up four healthy services on one Compose
network with stable DNS aliases (`postgres`, `backend`, `frontend`, `ollama`):

- `http://localhost:8123/health` → `{"status":"ok"}` within 60 s of cold start.
- `http://localhost:5173` → SPA loads with no "Loading…" regression.
- `docker compose exec backend python -c "import socket; socket.create_connection(('postgres', 5432), timeout=2)"` exits 0.
- `docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile gpu up -d ollama --wait` succeeds on a GPU host; the existing `RAG_EMBEDDING_PROVIDER=ollama` path then talks to `http://ollama:11434` from inside the backend container.

The host-mode flow (`uv run uvicorn`, `pnpm dev`) keeps working unchanged.

## Why

- **Onboarding cost.** Today's quick-start sets up four host toolchains and two
  terminals; portfolio reviewers and matrix CI consumers pay that tax once each.
- **Cross-container networking is currently unspecified.** The existing
  `OLLAMA_BASE_URL=http://localhost:11434` works from the host but breaks the
  moment the backend moves into a container — there is no in-cluster URL documented.
- **The `pre-existing Postgres-only Compose file` is a half-step.** It looks like
  "compose support" but isn't — the rest of the stack is invisible. This PRP closes
  the gap.
- **Reusable for portfolio demo on a GPU host.** Once Ollama is in the GPU profile,
  the local-only RAG path (`docs/rag-ollama-setup.md`) becomes a one-command demo
  rather than a manual `ollama serve` + env edit.

## What

A four-service Compose stack with the additions/edits below. The deliverable is
**packaging**, not application logic — no `app/features/**` source files are
touched (with one allow-listed exception: an OPTIONAL CORS comment, see Integration
Points).

### Success Criteria

- [ ] `make docker-up` returns 0 on a clean host within 60 s; `postgres`, `backend`,
      `frontend` all report `Health: healthy` via `docker compose ps --format json`.
- [ ] `curl -fsS http://localhost:8123/health` from the host → `{"status":"ok"}`.
- [ ] `curl -fsS http://localhost:5173/` from the host → SPA index HTML.
- [ ] `docker compose exec -T backend python -c "import socket; socket.create_connection(('postgres', 5432), timeout=2)"` exits 0.
- [ ] `make docker-up-gpu` brings Ollama up on a GPU host; `docker exec forecastlab-ollama nvidia-smi` shows the GPU. (SKIP target on non-GPU CI.)
- [ ] `DOCKER_STACK_TEST=1 uv run pytest -v -m integration tests/test_docker_stack.py` — three tests pass.
- [ ] `uv run pytest -m "not integration"` — unchanged (no host-mode regression).
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/` — all green.
- [ ] No file under `app/features/**/*.py` or `app/core/**/*.py` (excluding the
      `app/core/config.py` host-mode defaults) hardcodes `localhost:5433` or
      `localhost:11434` — locked in by `test_no_hardcoded_localhost_for_internal_services`.
- [ ] `docs/_base/RUNBOOKS.md` gains "Multi-container stack failed at step X"
      section; `README.md` gains "Run everything in containers" subsection;
      `docs/rag-ollama-setup.md` gains the in-cluster URL paragraph.
- [ ] **No new ADR-violating dependency** — pgvector remains the vector store; no
      Qdrant; no managed-cloud SDK on the core path.
- [ ] Commits follow `type(scope): description (#issue)` — likely `feat(repo): …`
      and `docs(repo): …`; one GitHub issue tracks the whole PRP; no AI co-author
      trailer.

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ before implementing
- url: https://docs.docker.com/reference/compose-file/services/#healthcheck
  why: every service needs a healthcheck so `depends_on: condition: service_healthy` blocks correctly
  critical: |
    Use `["CMD", "curl", "-fsS", "http://localhost:8123/health"]` (CMD-list form, NOT shell form).
    `start_period: 30s` is mandatory for backend — uvicorn + alembic upgrade take ~5-15 s cold.

- url: https://docs.docker.com/reference/compose-file/services/#depends_on
  why: long-form `depends_on: {svc: {condition: service_healthy}}` blocks until the dependency reports healthy
  critical: |
    The short form (`depends_on: [postgres]`) only waits for container start, NOT readiness.
    Backend MUST use the long form to wait for Postgres health, or alembic upgrade races.

- url: https://docs.docker.com/reference/compose-file/services/#profiles
  why: gates Ollama behind `--profile gpu` so non-GPU hosts get a clean default
  critical: |
    Services without `profiles:` always start; services WITH a profile only start when
    `--profile <name>` is passed OR when an active service has a `depends_on` on them.

- url: https://docs.docker.com/reference/cli/docker/compose/up/#options
  why: `--wait` blocks `docker compose up` until all services report healthy
  critical: |
    Returns non-zero exit on any unhealthy service. `--wait-timeout 60` caps the wait.
    Verified present on this host (Docker Compose v5.1.3).

- url: https://docs.docker.com/reference/cli/docker/compose/ps/#format
  why: `docker compose ps --format json` outputs JSON-LINES (one object per line) in Compose v2.27+ and v5.x
  critical: |
    Verified on this host: each row is its own JSON object separated by newlines —
    NOT a single JSON array. Parse with `[json.loads(l) for l in stdout.splitlines() if l.strip()]`.

- url: https://docs.astral.sh/uv/guides/integration/docker/
  why: official uv Docker integration pattern — `--frozen` + `--no-install-project` for bootstrap
  critical: |
    `uv sync --frozen --extra dev` errors if the project source isn't present yet (no `app/`),
    because uv tries to install the project itself. Use `--no-install-project` in the deps
    stage (verified flag exists in uv 0.11.8 via `uv sync --help`), then a second
    `uv sync --frozen --extra dev` after copying `app/` if needed.

- url: https://pnpm.io/docker
  why: corepack-based pnpm install pattern matching the host-side `AGENTS.md` § Setup
  critical: |
    `RUN corepack enable pnpm && pnpm install --frozen-lockfile` — the `--frozen-lockfile`
    flag refuses to write to `pnpm-lock.yaml`, mirroring the CI invariant.

- url: https://vitejs.dev/config/server-options.html#server-host
  why: `vite --host 0.0.0.0` makes the dev server reachable from outside the container
  critical: |
    Default bind is `127.0.0.1` — that's loopback INSIDE the container only, so the host
    browser sees ECONNREFUSED. Setting `--host 0.0.0.0` is required for the dev target.

- url: https://hub.docker.com/r/ollama/ollama
  why: Ollama image defaults to `0.0.0.0:11434` inside container; no extra config needed
  critical: |
    Healthcheck endpoint is `GET /api/tags` (returns 200 even with no models pulled).
    Models are stored in `/root/.ollama` — name the named volume `forecastlab_ollama_models`.

- url: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html#docker-compose
  why: the only supported Compose v2 way to expose NVIDIA GPUs
  critical: |
    `deploy.resources.reservations.devices: [{driver: nvidia, count: all, capabilities: [gpu]}]`
    is silently ignored if `nvidia-container-runtime` isn't the configured Docker runtime.
    Verify with `docker info | grep -i runtime` BEFORE invoking the gpu profile.

- url: https://hub.docker.com/r/pgvector/pgvector
  why: image tag `pg16` is the pinned variant — already in use; no change to the postgres service
  critical: matches ADR-0003 — the vector store stays in Postgres.

# Codebase reference files — READ BEFORE WRITING ANY CODE

- file: docker-compose.yml
  why: the existing 22-line file is the canonical pattern to extend; `postgres` block stays untouched
  critical: |
    The `postgres` service keeps `image: pgvector/pgvector:pg16`, `ports: ["5433:5432"]`,
    `forecastlab_pgdata` named volume, and the existing healthcheck (`pg_isready -U
    forecastlab -d forecastlab`). DO NOT edit those — just add `networks: [forecastlab]`
    to attach it to the new explicit network.

- file: app/main.py (CORS allow-list, search for "CORSMiddleware")
  why: ALREADY covers `http://localhost:5173/5174/5175` and 127.0.0.1 variants in dev
  critical: |
    No CORS edit is required for the containerized frontend — the existing allow-list
    handles it. (Plan's note about "must add http://frontend:5173" was wrong: the browser
    is the consumer, not the container; the browser always sees `http://localhost:5173`.)

- file: app/core/config.py (lines 1-80)
  why: `Settings` reads `DATABASE_URL` and (later) `OLLAMA_BASE_URL` via pydantic-settings
  critical: |
    `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`. Container
    `environment:` block OVERRIDES `.env` because OS env wins. For compose-mode, set
    `DATABASE_URL=postgresql+asyncpg://forecastlab:forecastlab@postgres:5432/forecastlab`
    (port 5432, hostname `postgres` — NOT `localhost:5433`).

- file: .env.example
  why: canonical env schema — every new key MUST be added here first (security-patterns.md two-file model)
  critical: |
    Append, don't replace. Add `OLLAMA_BASE_URL=http://ollama:11434` as a documented
    compose-mode default; KEEP the existing `DATABASE_URL=…@localhost:5433/…` default
    uncommented so host-mode still works.

- file: frontend/.env.example
  why: has TWO browser-consumed vars (VITE_API_BASE_URL and VITE_WS_URL); both stay on localhost:8123
  critical: |
    The browser is always the consumer — both vars must keep `http://localhost:8123` /
    `ws://localhost:8123/agents/stream` even when the frontend runs in a container.

- file: frontend/package.json (lines 65-67)
  why: `pnpm.onlyBuiltDependencies: ["esbuild"]` is ALREADY landed
  critical: |
    The pnpm 11 `depsStatusCheck` trap documented in RUNBOOKS.md is already mitigated.
    The dev-target Dockerfile still bypasses `pnpm dev` and calls Vite directly — but
    the rationale is "explicit + no surprise stalls", NOT the depsStatusCheck workaround.

- file: pyproject.toml (requires-python)
  why: Python pin is `>=3.12` — Dockerfile base must be `python:3.12-slim-bookworm`
  critical: |
    Do NOT use `python:3-slim` (floating major) or `python:3.13-slim` — strict pin
    matches the host setup and prevents wheel-resolution surprises.

- file: Makefile
  why: existing `demo` / `demo-quick` / `demo-clean` target style (.PHONY, ## help-text comments, tab indented)
  critical: |
    Mirror the help-text comment convention (`## ...`); the `help` target auto-formats those.
    All new targets MUST be `.PHONY`. Tab (not space) indentation on recipe lines.

- file: .github/workflows/ci.yml (services: postgres block, search "services:" + "postgres:")
  why: CI uses GitHub Actions `services:` containers — NOT `docker compose`
  critical: |
    This PRP does NOT change CI gating. `tests/test_docker_stack.py` is skipped unless
    `DOCKER_STACK_TEST=1` is exported; CI does not export it, so the existing test job
    stays unchanged. A follow-up PRP can wire a nightly compose-stack workflow.

- file: tests/test_e2e_demo.py
  why: precedent for repo-level integration tests that orchestrate processes (subprocess + docker compose)
  critical: |
    Uses `@pytest.mark.integration`, env-var gates, and `subprocess.run(..., capture_output=True, text=True, timeout=240)`.
    Mirror that shape in `tests/test_docker_stack.py`.

- file: app/core/health.py
  why: `GET /health` already returns `{"status":"ok"}` and is wired in app/main.py
  critical: container healthcheck reuses it — no new endpoint required.

- file: docs/_base/RUNBOOKS.md (sections "Database connection refused" + "Frontend shows Loading…")
  why: precedent format for new "Multi-container stack failed at step X" entry
  critical: mirror the Symptoms / Diagnosis / Resolution H3 structure.

- file: docs/ADR/ADR-0003-vector-storage-pgvector-in-postgres.md
  why: the load-bearing decision that BLOCKS adding Qdrant to this stack
  critical: |
    INITIAL-docker-rev2 mentions Qdrant; this PRP explicitly rejects that. If a future
    revision wants Qdrant, open a new ADR superseding ADR-0003 + a new PRP for the
    embedding-provider abstraction. Do NOT silently land Qdrant here.

- file: .claude/rules/product-vision.md (§ "Out of Scope (Hard No)")
  why: "no managed-cloud SDK in app/ core path" — Compose itself is fine; SDKs aren't
  critical: this PRP adds zero core-path dependencies; only build/run packaging.

- docfile: .agents/plans/dockerize-full-stack-rev2.md
  why: the full source plan with NOTES § "Vision-tension call-outs" justifying every
       deviation from INITIAL-docker-rev2 (Qdrant rejection, opt-in Ollama, missing
       example-file substitutions)
```

### Current Codebase tree (relevant slice)

```bash
ForecastLabAI/
├── docker-compose.yml                       # 22 lines, postgres-only — KEEP postgres block as-is
├── .env.example                             # canonical env schema — APPEND, don't replace
├── pyproject.toml                           # requires-python = ">=3.12"; asyncpg>=0.31.0
├── uv.lock                                  # required by `uv sync --frozen`
├── Makefile                                 # demo / demo-quick / demo-clean — add docker-* targets
├── app/
│   ├── main.py                              # FastAPI wiring + CORS allow-list (already covers localhost:5173+)
│   ├── core/
│   │   ├── config.py                        # Settings + DATABASE_URL default (host-mode)
│   │   └── health.py                        # GET /health → {"status":"ok"} — reused by container healthcheck
│   └── features/                            # 18 slices — NOT TOUCHED by this PRP
├── frontend/
│   ├── package.json                         # pnpm.onlyBuiltDependencies: ["esbuild"] already present
│   ├── pnpm-lock.yaml                       # required by `pnpm install --frozen-lockfile`
│   └── .env.example                         # VITE_API_BASE_URL + VITE_WS_URL — stay on localhost:8123
├── tests/
│   ├── conftest.py                          # repo-level pytest config
│   └── test_e2e_demo.py                     # precedent for subprocess-driven integration test
├── docs/_base/
│   └── RUNBOOKS.md                          # ADD "Multi-container stack failed at step X" entry
├── docs/
│   └── rag-ollama-setup.md                  # ADD in-cluster URL paragraph
└── README.md                                # ADD "Run everything in containers" subsection
```

### Desired Codebase tree (additions / edits)

```bash
ForecastLabAI/
├── docker-compose.yml                       # EXTEND: add backend, frontend, ollama services + networks: + volumes:
├── docker-compose.gpu.yml                   # NEW: GPU override (nvidia device reservations) for ollama
├── Dockerfile.backend                       # NEW: multi-stage Python 3.12 + uv, targets dev + prod
├── Dockerfile.frontend                      # NEW: multi-stage Node 22 + pnpm, targets dev (vite) + prod (nginx)
├── .dockerignore                            # NEW: exclude .venv, node_modules, .env, .claude, .agents, …
├── .env.example                             # EDIT: add OLLAMA_BASE_URL + Compose-mode DATABASE_URL comment
├── frontend/.env.example                    # EDIT: add comment "browser is always the consumer — keep localhost:8123"
├── Makefile                                 # EDIT: append docker-up / docker-up-gpu / docker-down targets
├── tests/test_docker_stack.py               # NEW: 3 tests (services healthy + DNS reach + localhost-purity grep)
├── docs/_base/RUNBOOKS.md                   # EDIT: add "Multi-container stack failed at step X" section
├── docs/rag-ollama-setup.md                 # EDIT: add in-cluster URL paragraph
└── README.md                                # EDIT: add "Run everything in containers" subsection
```

### Known Gotchas of our codebase & Library Quirks

```python
# === RUNTIME-VERIFIED (verification commands inline) ===

# CRITICAL [verified 2026-05-20]: asyncpg does NOT depend on libpq.
# It talks the Postgres wire protocol directly.
# Verify:   grep -E '^libpq|libpq-dev' uv.lock  → no hits
# Action:   Dockerfile.backend MUST NOT `apt-get install libpq5`. Slim image is enough.
#           Plan's GOTCHA "libpq5 needed for asyncpg" was WRONG and is corrected here.

# CRITICAL [verified 2026-05-20]: uv 0.11.8 supports `--no-install-project` and `--no-install-workspace`.
# Verify:   uv sync --help | grep -E "(no-install-project|no-install-workspace|frozen)"
# Action:   In Dockerfile.backend `deps` stage, before `app/` is copied:
#               uv sync --frozen --extra dev --no-install-project
#           After copying `app/`, a second `uv sync --frozen --extra dev` registers
#           the project. Or use `--no-install-workspace` if a workspace error fires.

# CRITICAL [verified 2026-05-20]: docker compose ps --format json returns JSON-LINES, NOT array.
# Verify:   docker compose ps --format json | head -1 | python3 -c "import sys,json; json.loads(sys.stdin.read())"
#           (the JSON.loads() succeeds per-line; multi-line stdin would error)
# Action:   In tests/test_docker_stack.py:
#               rows = [json.loads(line) for line in stdout.splitlines() if line.strip()]
#           Do NOT call `json.loads(stdout)` — that errors on multi-row output.

# CRITICAL [verified 2026-05-20]: docker compose up --wait flag EXISTS in this Compose version.
# Verify:   docker compose up --help | grep -E "(--wait|--wait-timeout)"
# Action:   `make docker-up` uses `docker compose up -d --wait` — surfaces healthcheck
#           failures synchronously instead of returning success on "running but unhealthy".

# CRITICAL: app/main.py CORS allow-list ALREADY covers localhost:5173, 5174, 5175 + 127.0.0.1 variants.
# Verify:   grep -A 12 'CORSMiddleware' app/main.py | grep -c 'localhost:5173'
# Action:   DO NOT widen the CORS list. The containerized frontend is reached BY THE BROWSER
#           via the host-published port 5173, so the origin the browser sends is identical
#           to the host-mode origin.

# CRITICAL: pnpm.onlyBuiltDependencies: ["esbuild"] is ALREADY in frontend/package.json.
# Verify:   grep -A 2 '"pnpm":' frontend/package.json
# Action:   The pnpm 11 depsStatusCheck trap is already mitigated at the source.
#           Dockerfile.frontend still calls vite directly in the dev target ONLY because
#           explicit > implicit in a containerized hot-reload path — NOT to dodge depsStatusCheck.

# CRITICAL: Vite default --host is 127.0.0.1 (container-loopback only).
# Verify:   grep -E 'server\..*host|host' frontend/vite.config.ts (no override in repo)
# Action:   Dev target CMD MUST pass --host 0.0.0.0 or the host browser sees ECONNREFUSED.

# CRITICAL: pydantic-settings reads OS env BEFORE .env (env wins).
# Verify:   grep -E 'env_file|SettingsConfigDict' app/core/config.py
# Action:   In docker-compose.yml backend service, the `environment:` block overrides the
#           bind-mounted `.env`. Use it to inject `DATABASE_URL=...@postgres:5432/...` so
#           the in-cluster URL trumps the host-mode default without editing `.env`.

# CRITICAL: bind-mounting `./app:/app/app` SHADOWS the image's baked-in COPY.
# Verify:   docker run --rm forecastlab-backend:dev ls /app/app (must list slice dirs)
# Action:   The image MUST be self-sufficient (no bind-mount). The dev compose adds the
#           bind-mount on top for hot-reload. A standalone `docker run` smoke test catches
#           a missing COPY before the compose stack masks it.

# CRITICAL: gpu profile silently no-ops without nvidia-container-runtime.
# Verify:   docker info | grep -i runtime  (must show "nvidia" if GPU host)
# Action:   make docker-up-gpu MUST fail-fast on non-GPU hosts. Runbook entry documents
#           the diagnosis. Test `test_docker_stack_services_healthy` skips Ollama unless
#           DOCKER_STACK_GPU=1 is also set.

# CRITICAL: Repo files have mixed CRLF/LF line endings (memory [[repo-line-endings-crlf]]).
# Verify:   file Dockerfile.backend Dockerfile.frontend docker-compose.yml after writing
# Action:   The Write tool emits LF — that's the desired state. Run
#           `git diff --stat` before committing; if a CRLF whole-file flip appears on a
#           file you didn't intend to touch, revert it and only commit the targeted change.

# CRITICAL: .env is gitignored (`.env`, `.env.cloud`, `.env.local`). NEVER commit it.
# Verify:   grep -E '^\.env' .gitignore
# Action:   Only `.env.example` is committed. The container `env_file: .env` directive
#           reads the developer's local file; missing keys must fail-fast via `${VAR:?…}`
#           syntax in the compose env-var block.

# CRITICAL: `frontend/.env.example` has TWO browser-consumed vars (VITE_API_BASE_URL, VITE_WS_URL).
# Verify:   cat frontend/.env.example
# Action:   Both must stay on `localhost:8123` even in compose mode — the browser, not
#           any container, is the consumer. Update the comment for BOTH, not just the HTTP one.

# CRITICAL: GitHub Actions ci.yml uses `services: postgres:` containers, NOT docker compose.
# Verify:   grep -A 5 'services:' .github/workflows/ci.yml | head -15
# Action:   This PRP does NOT change ci.yml. `tests/test_docker_stack.py` gates on
#           DOCKER_STACK_TEST=1 (unset in CI) so the existing CI flow is untouched.
#           A nightly compose-stack workflow can be a follow-up PRP.

# CRITICAL: PRP-31 precedent (issue #258) — runtime-verify every library claim.
# Memories: [[histgbr-no-feature-importances]] + [[simpleimputer-drops-empty-columns]].
# Action:   Every CRITICAL above has an explicit `Verify:` line. Re-run them on any
#           Docker / Compose / uv upgrade before assuming the claim still holds.
```

---

## Implementation Blueprint

### Data models and structure

No new Python data models, no new SQLAlchemy ORM, no Alembic migration. The single
typed structure introduced is implicit in `tests/test_docker_stack.py`:

```python
# tests/test_docker_stack.py — TypedDict for clarity in the JSON-lines parser
from typing import TypedDict

class ComposePsRow(TypedDict):
    Service: str           # e.g. "postgres" | "backend" | "frontend" | "ollama"
    State:   str           # e.g. "running" | "exited"
    Health:  str           # e.g. "healthy" | "unhealthy" | "starting" | "" (no healthcheck)
    Name:    str           # container name (e.g. "forecastlab-backend")
```

### List of tasks (execute in order)

```yaml
Task 1:
CREATE .dockerignore:
  - Exclude .venv/, frontend/node_modules/, frontend/dist/, artifacts/, .git/, .env,
    .env.cloud, .env.local, *.pyc, __pycache__/, .handoffs/, HANDOFF.md, .claude/,
    .agents/, *.log, .pytest_cache/, .ruff_cache/, .mypy_cache/, .DS_Store
  - VALIDATE: `du -sh $(git ls-files -o --directory --exclude-standard | head) 2>/dev/null`
    confirms .venv + node_modules are absent from the would-be build context.

Task 2:
CREATE Dockerfile.backend:
  - MIRROR pattern from: https://docs.astral.sh/uv/guides/integration/docker/
  - Multi-stage: `base` (python:3.12-slim-bookworm + curl), `deps`
    (copy pyproject.toml + uv.lock, `uv sync --frozen --extra dev --no-install-project`),
    `dev` (copy /opt/venv, copy app/ alembic/ alembic.ini scripts/, EXPOSE 8123,
    ENTRYPOINT script that runs `uv run alembic upgrade head && exec uv run uvicorn
    app.main:app --host 0.0.0.0 --port 8123 --reload`).
  - PROD target: identical but without `--reload` and without `--extra dev`.
  - GOTCHA: do NOT apt-install libpq5 — asyncpg doesn't need it (verified above).
  - GOTCHA: use `--mount=type=cache,target=/root/.cache/uv` for fast rebuilds (BuildKit).
  - VALIDATE: `docker build -t forecastlab-backend:dev --target dev -f Dockerfile.backend .`
    exits 0; `docker run --rm -e DATABASE_URL=postgresql+asyncpg://forecastlab:forecastlab@host.docker.internal:5433/forecastlab
    -p 8123:8123 forecastlab-backend:dev`; `curl http://localhost:8123/health` → `{"status":"ok"}`.

Task 3:
CREATE Dockerfile.frontend:
  - MIRROR pattern from: https://pnpm.io/docker
  - Multi-stage: `builder` (node:22-bookworm-slim, corepack enable pnpm, copy
    frontend/package.json + frontend/pnpm-lock.yaml, `pnpm install --frozen-lockfile`,
    copy frontend/, `pnpm build`), `prod` (nginx:1.27-alpine + try_files SPA conf),
    `dev` (separate target — node:22-bookworm-slim, EXPOSE 5173, CMD
    `["./node_modules/.bin/vite", "--host", "0.0.0.0"]`).
  - GOTCHA: dev CMD MUST pass `--host 0.0.0.0` or host browser sees ECONNREFUSED.
  - VALIDATE: `docker build -t forecastlab-frontend:dev --target dev -f Dockerfile.frontend .`
    exits 0; `docker run --rm -p 5173:5173 -e VITE_API_BASE_URL=http://localhost:8123
    forecastlab-frontend:dev`; `curl -fsS http://localhost:5173/` returns SPA HTML.

Task 4:
EXTEND docker-compose.yml:
  - PRESERVE the existing `postgres` service exactly (image, healthcheck, port, volume).
  - ADD top-level `networks: {forecastlab: {driver: bridge}}` and attach all four services.
  - ADD `backend` service: build: {context: ., dockerfile: Dockerfile.backend, target: dev},
    container_name: forecastlab-backend, env_file: .env,
    environment: {DATABASE_URL: "postgresql+asyncpg://forecastlab:forecastlab@postgres:5432/forecastlab",
                  OLLAMA_BASE_URL: "http://ollama:11434", APP_ENV: "development"},
    ports: ["8123:8123"], depends_on: {postgres: {condition: service_healthy}},
    healthcheck: ["CMD", "curl", "-fsS", "http://localhost:8123/health"]
      with interval: 10s timeout: 5s retries: 5 start_period: 30s,
    volumes: [./app:/app/app, ./alembic:/app/alembic, forecastlab_artifacts:/app/artifacts],
    restart: unless-stopped.
  - ADD `frontend` service: build: {context: ., dockerfile: Dockerfile.frontend, target: dev},
    container_name: forecastlab-frontend,
    environment: {VITE_API_BASE_URL: "http://localhost:8123",
                  VITE_WS_URL: "ws://localhost:8123/agents/stream"},
    ports: ["5173:5173"], depends_on: {backend: {condition: service_healthy}},
    volumes: [./frontend/src:/app/src, ./frontend/public:/app/public,
              ./frontend/index.html:/app/index.html, ./frontend/vite.config.ts:/app/vite.config.ts],
    restart: unless-stopped.
  - ADD `ollama` service: image: ollama/ollama:latest, container_name: forecastlab-ollama,
    profiles: ["gpu"], ports: ["11434:11434"],
    volumes: [forecastlab_ollama_models:/root/.ollama],
    healthcheck: ["CMD", "curl", "-fsS", "http://localhost:11434/api/tags"]
      with interval: 30s timeout: 10s retries: 3 start_period: 20s,
    restart: unless-stopped.
  - ADD to top-level `volumes:` — `forecastlab_ollama_models:` and `forecastlab_artifacts:`.
  - GOTCHA 1: Inside the network, Postgres is `postgres:5432` (container port),
    NOT `localhost:5433` (host-mapped). Runbook entry documents this.
  - GOTCHA 2: `./app:/app/app` bind-mount shadows the image COPY — keep it,
    enables uvicorn --reload to pick up edits, image still works standalone.
  - VALIDATE: `docker compose config` parses cleanly (exit 0). `docker compose up -d --wait`
    brings the three default services (no Ollama) to healthy within 60 s.
    `docker compose ps --format json | head -1 | jq -r '.Service + ": " + .Health'`
    shows `postgres: healthy`, then re-run for the other two.

Task 5:
CREATE docker-compose.gpu.yml:
  - Single service block: `ollama: {deploy: {resources: {reservations:
    {devices: [{driver: nvidia, count: all, capabilities: [gpu]}]}}}}`.
  - GOTCHA: silently ignored if `nvidia-container-runtime` not configured.
    The runbook entry MUST instruct verification via `docker info | grep -i runtime`.
  - VALIDATE: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile gpu config`
    parses cleanly. On a GPU host: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml
    --profile gpu up -d ollama --wait` reports healthy; `docker exec forecastlab-ollama nvidia-smi`
    shows the GPU.

Task 6:
EDIT .env.example:
  - INSERT a fenced comment block immediately above the existing `DATABASE_URL=` line:
        # Host-mode (uv run uvicorn): use the line below.
        # Compose-mode (docker compose up): the backend container overrides this with
        #   DATABASE_URL=postgresql+asyncpg://forecastlab:forecastlab@postgres:5432/forecastlab
        # via its `environment:` block, so the .env value below stays the host-mode default.
  - APPEND under the Ollama section:
        # OLLAMA_BASE_URL=http://localhost:11434  # host-mode
        # In compose-mode, the backend container injects http://ollama:11434.
  - KEEP every existing line untouched.
  - VALIDATE: `grep -E '^# (Host|Compose)-mode' .env.example` matches.
    `git diff .env.example | grep -E '^\+[^#]'` shows only documentation-comment additions.

Task 7:
EDIT frontend/.env.example:
  - Replace `VITE_API_BASE_URL=http://localhost:8123` with:
        # The browser, not the container, calls the backend — keep this on localhost:8123
        # even when running via docker compose.
        VITE_API_BASE_URL=http://localhost:8123
  - Replace `VITE_WS_URL=ws://localhost:8123/agents/stream` with:
        # Same browser-is-consumer rule — keep this on localhost:8123 in compose mode.
        VITE_WS_URL=ws://localhost:8123/agents/stream
  - PRESERVE every other line untouched.
  - VALIDATE: `grep -c 'browser, not the container' frontend/.env.example` returns 1
    (only the first occurrence; second comment uses different wording).

Task 8:
EDIT Makefile:
  - APPEND (matching the existing .PHONY convention and ## help-text style):
        .PHONY: docker-up docker-up-gpu docker-down

        docker-up:  ## bring full stack up (no GPU)
        	docker compose up -d --wait --wait-timeout 90

        docker-up-gpu:  ## bring full stack up with Ollama on GPU
        	docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile gpu up -d --wait --wait-timeout 120

        docker-down:  ## stop and remove containers (keep volumes)
        	docker compose down
  - UPDATE the `.PHONY:` line at the top of the Makefile to add the three new targets.
  - UPDATE the `help:` target's echoed list to mention the new targets.
  - GOTCHA: tab indentation on recipe lines (not spaces).
  - VALIDATE: `make -n docker-up` echoes `docker compose up -d --wait --wait-timeout 90`.
    `make help | grep docker-up` lists all three new targets.

Task 9:
CREATE tests/test_docker_stack.py:
  - PATTERN: mirror tests/test_e2e_demo.py for subprocess + integration-marker shape.
  - Module skip: `pytestmark = pytest.mark.skipif(os.environ.get("DOCKER_STACK_TEST") != "1",
                              reason="set DOCKER_STACK_TEST=1 to run after `make docker-up`")`.
  - Test 1 `test_docker_stack_services_healthy`:
        proc = subprocess.run(["docker", "compose", "ps", "--format", "json"],
                              capture_output=True, text=True, check=True, timeout=30)
        rows = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
        by_svc = {r["Service"]: r for r in rows}
        for svc in ("postgres", "backend", "frontend"):
            assert by_svc[svc]["Health"] == "healthy", f"{svc}: {by_svc[svc]}"
        if os.environ.get("DOCKER_STACK_GPU") == "1":
            assert by_svc["ollama"]["Health"] == "healthy"
  - Test 2 `test_backend_can_reach_postgres_via_internal_dns`:
        proc = subprocess.run(
            ["docker", "compose", "exec", "-T", "backend",
             "python", "-c", "import socket; socket.create_connection(('postgres', 5432), timeout=2)"],
            capture_output=True, text=True, timeout=10)
        assert proc.returncode == 0, proc.stderr
  - Test 3 `test_no_hardcoded_localhost_for_internal_services`:
        ROOT = pathlib.Path(__file__).resolve().parents[1]
        ALLOWED = {ROOT / "app" / "core" / "config.py"}  # host-mode defaults legitimately live here
        pat = re.compile(r"localhost:(5433|11434)")
        offenders = []
        for p in (ROOT / "app").rglob("*.py"):
            if p in ALLOWED or "/tests/" in p.as_posix() or p.name.startswith("test_"):
                continue
            text = p.read_text(encoding="utf-8")
            for n, line in enumerate(text.splitlines(), 1):
                if pat.search(line):
                    offenders.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()}")
        assert not offenders, "\n".join(offenders)
  - IMPORTS: subprocess, json, os, re, pathlib, pytest.
  - GOTCHA: `docker compose exec -T` (the `-T` disables TTY) is required from pytest
    or stdin allocation errors fire. (Reproduced: omitting -T fails on this host.)
  - VALIDATE: `DOCKER_STACK_TEST=1 uv run pytest -v -m integration tests/test_docker_stack.py`
    runs all three tests; first two pass after `make docker-up`; third passes regardless.

Task 10:
EDIT docs/_base/RUNBOOKS.md:
  - APPEND a new H3 section "### Multi-container stack failed at step X" after the
    existing "### Frontend shows "Loading..." everywhere" section.
  - Cover: (a) `make docker-up` non-zero — `docker compose ps` to find the unhealthy
    service, `docker compose logs <svc> --tail 50` for the cause; (b) backend logs
    `getaddrinfo failed` on `postgres` — Postgres not healthy yet (cold-start race);
    (c) frontend reachable from host but not from backend curl — expected, browser is
    the consumer; (d) Ollama profile up without GPU — diagnosis via `docker info |
    grep -i runtime` and `nvidia-smi`; (e) "Loading…" on /dashboard after compose up —
    `VITE_API_BASE_URL` got overridden to a container hostname; reset to `localhost:8123`.
  - PATTERN: mirror the Symptoms / Diagnosis / Resolution structure used in the
    existing "Database connection refused" entry.
  - VALIDATE: `grep -c 'Multi-container stack failed' docs/_base/RUNBOOKS.md` → 1.

Task 11:
EDIT docs/rag-ollama-setup.md:
  - APPEND a paragraph after the existing host-mode section:
        "When ForecastLabAI runs via `docker compose --profile gpu up`, the backend
        container reaches Ollama through the in-cluster DNS name `http://ollama:11434`
        — the backend service's `environment:` block sets `OLLAMA_BASE_URL=http://ollama:11434`
        automatically. To run host-mode against the containerized Ollama, set
        `OLLAMA_BASE_URL=http://localhost:11434` in your `.env` (Ollama publishes
        port 11434 on the host)."
  - VALIDATE: `grep -c 'ollama:11434' docs/rag-ollama-setup.md` ≥ 1.

Task 12:
EDIT README.md:
  - APPEND a "### Run everything in containers" subsection under Quick Start that lists:
        make docker-up           # → http://localhost:8123 + http://localhost:5173, ~60 s
        make docker-down         # stop containers, keep volumes
  - APPEND a sub-subsection "### GPU host (optional Ollama)":
        make docker-up-gpu       # adds Ollama with NVIDIA passthrough
  - Cross-link to `docs/_base/RUNBOOKS.md` "Multi-container stack failed at step X"
    for diagnosis.
  - PATTERN: use fenced bash blocks matching the rest of the Quick Start.
  - VALIDATE: `grep -A 2 'Run everything in containers' README.md | grep -F 'make docker-up'`.
```

### Per-task pseudocode (critical details only)

```dockerfile
# Task 2 — Dockerfile.backend (multi-stage, target dev by default)
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm AS base
# curl is needed by the healthcheck; ca-certificates for HTTPS uv installer
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# Pin uv via the official installer; matches uv 0.11.8 on this host
ENV UV_INSTALL_DIR=/usr/local/bin UV_PYTHON_INSTALL_DIR=/root/.local/share/uv/python
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

FROM base AS deps
WORKDIR /app
COPY pyproject.toml uv.lock ./
# --no-install-project: don't try to install the workspace before `app/` is copied
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra dev --no-install-project

FROM deps AS dev
WORKDIR /app
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/
# Now install the project itself (cheap, deps already cached above)
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --extra dev
EXPOSE 8123
# Inline entrypoint: migrations then uvicorn with reload (dev only)
ENTRYPOINT ["sh", "-c", "uv run alembic upgrade head && exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8123 --reload"]

FROM dev AS prod
# Re-sync without dev extras for the smaller prod image
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen
ENTRYPOINT ["sh", "-c", "uv run alembic upgrade head && exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8123"]
```

```dockerfile
# Task 3 — Dockerfile.frontend (multi-stage; default target dev)
# syntax=docker/dockerfile:1.7
FROM node:22-bookworm-slim AS builder
WORKDIR /app
RUN corepack enable pnpm
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ .
RUN pnpm build

FROM nginx:1.27-alpine AS prod
COPY --from=builder /app/dist/ /usr/share/nginx/html/
# Minimal SPA conf — try_files for client-side routing
RUN printf 'server { listen 80; root /usr/share/nginx/html; try_files $uri /index.html; }\n' > /etc/nginx/conf.d/default.conf
EXPOSE 80

FROM node:22-bookworm-slim AS dev
WORKDIR /app
RUN corepack enable pnpm
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ .
EXPOSE 5173
# GOTCHA: --host 0.0.0.0 required, or host browser sees ECONNREFUSED
CMD ["./node_modules/.bin/vite", "--host", "0.0.0.0"]
```

```yaml
# Task 4 — docker-compose.yml (additions; existing postgres block kept verbatim)
services:
  postgres:
    # ...existing block UNCHANGED — just add `networks: [forecastlab]`
    networks: [forecastlab]

  backend:
    build: {context: ., dockerfile: Dockerfile.backend, target: dev}
    container_name: forecastlab-backend
    env_file: .env
    environment:
      DATABASE_URL: "postgresql+asyncpg://forecastlab:forecastlab@postgres:5432/forecastlab"
      OLLAMA_BASE_URL: "http://ollama:11434"
      APP_ENV: "development"
    ports: ["8123:8123"]
    depends_on: {postgres: {condition: service_healthy}}
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8123/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    volumes:
      - ./app:/app/app
      - ./alembic:/app/alembic
      - forecastlab_artifacts:/app/artifacts
    networks: [forecastlab]
    restart: unless-stopped

  frontend:
    build: {context: ., dockerfile: Dockerfile.frontend, target: dev}
    container_name: forecastlab-frontend
    environment:
      VITE_API_BASE_URL: "http://localhost:8123"
      VITE_WS_URL: "ws://localhost:8123/agents/stream"
    ports: ["5173:5173"]
    depends_on: {backend: {condition: service_healthy}}
    volumes:
      - ./frontend/src:/app/src
      - ./frontend/public:/app/public
      - ./frontend/index.html:/app/index.html
      - ./frontend/vite.config.ts:/app/vite.config.ts
    networks: [forecastlab]
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    container_name: forecastlab-ollama
    profiles: ["gpu"]
    ports: ["11434:11434"]
    volumes: [forecastlab_ollama_models:/root/.ollama]
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:11434/api/tags"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s
    networks: [forecastlab]
    restart: unless-stopped

networks:
  forecastlab: {driver: bridge}

volumes:
  forecastlab_pgdata: {}            # existing
  forecastlab_ollama_models: {}     # new
  forecastlab_artifacts: {}         # new
```

### Integration Points

```yaml
DATABASE:
  - No migration. No model change. `alembic upgrade head` runs in the backend
    container entrypoint — same forward-only invariant.

CONFIG:
  - Add to: .env.example (DOC-ONLY comments — no new required env var).
  - Pattern: a fenced comment block above the existing DATABASE_URL line + a
    commented OLLAMA_BASE_URL example. The container's `environment:` block in
    docker-compose.yml is the actual source of compose-mode values.

ROUTES:
  - No new routes. CORS allow-list in app/main.py already covers localhost:5173+.

OPTIONAL CORS NOTE (defer — do NOT change in this PRP):
  - If a future PRP adds inter-container HTTP calls from another container to
    the backend, the CORS list will need an explicit container-DNS origin
    (e.g., http://other-svc:1234). Today only the browser hits the backend,
    so the list is correct as-is.

CI:
  - No change to .github/workflows/ci.yml. `tests/test_docker_stack.py` gates
    on DOCKER_STACK_TEST=1 (unset in CI). A follow-up PRP can wire a nightly
    compose-stack workflow that mirrors e2e-nightly.yml.

DOCUMENTATION:
  - Three docs updated (see Tasks 10-12). No new docs created.
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Compose YAML parses (base + GPU override)
docker compose config --quiet && echo "compose base OK"
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile gpu config --quiet && echo "compose gpu OK"

# Dockerfile lint (optional — skip if hadolint not installed)
command -v hadolint && hadolint Dockerfile.backend Dockerfile.frontend || echo "hadolint not present — skipping"

# Python file gates (only the new test file in this PRP)
uv run ruff check tests/test_docker_stack.py
uv run ruff format --check tests/test_docker_stack.py
uv run mypy tests/test_docker_stack.py    # type-only assertions, must be clean
```

### Level 2: Unit / no-DB checks

```bash
# Full unit suite — NO REGRESSION expected (this PRP doesn't touch app/ logic)
uv run pytest -v -m "not integration"

# Strict-type gates against existing app/
uv run mypy app/
uv run pyright app/
```

### Level 3: Integration Test (this stack)

```bash
# Bring stack up
make docker-up                                       # must exit 0 within 60s

# Inspect — every service must be healthy
docker compose ps --format json \
  | python3 -c "import sys,json; [print(json.loads(l)['Service'], '=>', json.loads(l)['Health']) for l in sys.stdin if l.strip()]"
# Expected:
#   postgres => healthy
#   backend => healthy
#   frontend => healthy

# New repo-level integration tests
DOCKER_STACK_TEST=1 uv run pytest -v -m integration tests/test_docker_stack.py

# Re-run the EXISTING integration suite from INSIDE the backend container
docker compose exec -T backend uv run pytest -v -m integration

# Tear down (keeps volumes; data persists)
make docker-down
```

### Level 4: Manual Validation (host browser)

```bash
make docker-up

# Health
curl -fsS http://localhost:8123/health                 # {"status":"ok"}
curl -fsS http://localhost:8123/docs | head -5         # Swagger HTML

# Browser
#   open http://localhost:5173 — Dashboard fetches KPIs/jobs (no "Loading..." regression)
#   open http://localhost:8123/docs — interactive Swagger

# E2E demo from inside the backend container (reuses scripts/run_demo.py)
docker compose exec -T backend uv run python scripts/run_demo.py --seed 42

make docker-down
```

### Level 5: GPU-host validation (skip on non-GPU)

```bash
nvidia-smi                                              # gate
make docker-up-gpu
docker exec forecastlab-ollama ollama pull nomic-embed-text

# Switch backend to Ollama embeddings (transient — edit .env locally)
#   RAG_EMBEDDING_PROVIDER=ollama
#   OLLAMA_BASE_URL=http://ollama:11434     # in-cluster from backend
#   RAG_EMBEDDING_DIMENSION=768             # nomic-embed-text dimension
# (then) docker compose restart backend

curl -X POST http://localhost:8123/rag/index/project-docs    # exercises Ollama embeddings
DOCKER_STACK_TEST=1 DOCKER_STACK_GPU=1 uv run pytest -v -m integration tests/test_docker_stack.py
make docker-down
```

---

## Final Validation Checklist

- [ ] `docker compose config` and `docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile gpu config` both parse cleanly.
- [ ] `make docker-up` exits 0 within 60 s on a clean host; `docker compose ps` reports postgres/backend/frontend `healthy`.
- [ ] `curl -fsS http://localhost:8123/health` → `{"status":"ok"}`; `curl -fsS http://localhost:5173/` → SPA HTML.
- [ ] `docker compose exec -T backend python -c "import socket; socket.create_connection(('postgres', 5432), timeout=2)"` exits 0.
- [ ] `DOCKER_STACK_TEST=1 uv run pytest -v -m integration tests/test_docker_stack.py` — all 3 tests pass.
- [ ] `uv run pytest -v -m "not integration"` — no regressions (this PRP touches packaging only).
- [ ] `uv run ruff check .` / `ruff format --check .` / `mypy app/` / `pyright app/` — all green.
- [ ] No file under `app/features/**/*.py` or `app/core/**/*.py` (excluding `app/core/config.py`) hardcodes `localhost:5433` or `localhost:11434`.
- [ ] `docs/_base/RUNBOOKS.md` has the "Multi-container stack failed at step X" section; `README.md` has the "Run everything in containers" subsection; `docs/rag-ollama-setup.md` has the `http://ollama:11434` in-cluster paragraph.
- [ ] **No new ADR-violating dependency** — pgvector remains the vector store per ADR-0003; no Qdrant; no managed-cloud SDK on the core path.
- [ ] `.env` is NOT committed; only `.env.example` and `frontend/.env.example` carry diffs; no secret-shaped values in any new file.
- [ ] GPU validation (Level 5) attempted on a GPU host OR explicitly deferred in the PR description.
- [ ] All commits follow `type(scope): description (#issue)` with scope ∈ {`repo`, `docs`}; no AI co-author trailer; every commit references the tracking issue this PRP gets opened against.
- [ ] One PR into `dev` (branch `feat/repo-dockerize-full-stack`), CI green, reviewer approved, merged with the standard merge commit (not squash for back-merges; this is a feature PR so squash or merge — maintainer's choice).
- [ ] HANDOFF.md updated with: the new compose commands, the GPU profile invocation, the localhost-purity invariant, the asyncpg-no-libpq runtime finding.

---

## Anti-Patterns to Avoid

- ❌ Don't apt-install `libpq5` / `libpq-dev` in `Dockerfile.backend` — asyncpg doesn't need it (runtime-verified; the plan's original gotcha was wrong).
- ❌ Don't widen the CORS allow-list in `app/main.py` — it already covers the containerized frontend's browser origin.
- ❌ Don't replace the existing `postgres` service block — extend the file, don't rewrite it.
- ❌ Don't add Qdrant, Weaviate, Milvus, or any other vector store — ADR-0003 + product-vision.md hard-block it. (See plan NOTES § "Vision-tension call-outs" #1.)
- ❌ Don't add an AWS/GCP/Azure SDK to the core path — product-vision.md hard-no.
- ❌ Don't set `pnpm dev` as the dev-target CMD — call `vite --host 0.0.0.0` directly. (Explicit > implicit in a container; depsStatusCheck is already mitigated at the package.json level.)
- ❌ Don't omit `--host 0.0.0.0` from the Vite dev CMD — without it the host browser can't reach the container.
- ❌ Don't commit `.env` (or any `.env.cloud` / `.env.local`) — gitignored; only `.env.example` is tracked.
- ❌ Don't change `ci.yml` to use `docker compose` — the existing GitHub Actions `services:` pattern is faster, well-isolated, and not in this PRP's scope.
- ❌ Don't make `tests/test_docker_stack.py` run unconditionally in CI — it requires a live Docker daemon and `make docker-up`; gate it on `DOCKER_STACK_TEST=1` so existing CI is unchanged.
- ❌ Don't edit `app/core/config.py` host-mode defaults — they're correct as the host-mode source of truth; the compose path overrides via container env.
- ❌ Don't add an AI co-author trailer to any commit (`Co-Authored-By: Claude …` / `🤖 Generated with …`) — `.claude/rules/commit-format.md` forbids it; the pre-commit hook will fail the commit.
- ❌ Don't `--force` push on `dev` or `main` — `.claude/rules/security-patterns.md` hard-forbids it.

---

## Confidence Score

**8/10** for one-pass implementation success.

Up from 7/10 in the source plan after:
- runtime-verified the four critical Docker / uv / Compose claims (`--no-install-project`, `--wait`, JSON-lines `ps`, `-T` exec);
- corrected the wrong `libpq5` gotcha (asyncpg doesn't need it);
- caught that the CORS allow-list is already correct (no `app/main.py` edit needed);
- noticed `frontend/.env.example` has TWO browser-consumed vars (both must keep `localhost`);
- pinned `python:3.12-slim-bookworm` (matches `requires-python = ">=3.12"`);
- noticed `pnpm.onlyBuiltDependencies: ["esbuild"]` is already in `frontend/package.json`.

Remaining 2 points of uncertainty:
- The two-stage `uv sync --no-install-project` → `uv sync` pattern is documented but can hit edge cases on uv version skew (this host runs uv 0.11.8; CI may have a different pin) — Level 1 validation catches a build failure synchronously.
- The bind-mount-vs-COPY shadow in the dev target requires the image to remain self-sufficient; the standalone `docker run` smoke test in Task 2's VALIDATE catches drift, but a developer who skips it would only see the failure on a CI run against the prod image.

If a future revision re-introduces Qdrant or a managed-cloud SDK, this PRP DOES NOT cover that — open a new INITIAL + PRP under `PRPs/INITIAL/`.
