name: "PRP-17 — In-Product Demo Showcase Page (live e2e pipeline in the dashboard)"
description: |
  Turn the CLI-only end-to-end demo (PRP-15 / `scripts/run_demo.py` / `make demo`) into a
  visible, in-product experience. Add a new backend `demo` vertical slice that drives the
  published API surface in-process and streams per-step progress, plus a React **Showcase**
  page that renders the pipeline running live — seed → features → train ×3 → backtest ×3 →
  register → verify → agent — as status cards a portfolio reviewer can watch in the browser.

## Purpose
Close the demonstrability gap that PRP-15 left half-open. PRP-15 made the e2e pipeline
*runnable* (`make demo`) — but only from a terminal. A portfolio reviewer (or the
maintainer after an absence) who opens the dashboard sees no live pipeline narrative; the
multi-week Phase-1/Phase-2 investment is invisible unless someone runs a shell command.
After this PRP, the dashboard has a **Showcase** page: click "Run pipeline", watch the
11-step e2e flow stream to completion, and land on the registered winning model — no CLI.

> **PRP numbering note:** `PRP-16` is reserved by PRP-15 for Phase-2-aware LightGBM. This
> PRP takes `PRP-17` to avoid the collision.

## Core Principles
1. **Context is King** — every endpoint shape, schema field, and orchestration decision is
   linked to a real source file + line below. The orchestration logic is a *proven* copy of
   `scripts/run_demo.py` (PR #129) — that file is the reference implementation.
2. **Vertical-slice rule respected** — new code lives under `app/features/demo/`; it does
   NOT import from any other `app/features/*` slice. It drives the app through its own HTTP
   surface via `httpx.ASGITransport` (the in-process transport the test suite already uses,
   `tests/conftest.py:4`), so there is zero cross-slice Python import.
3. **Reuse existing patterns** — WebSocket streaming mirrors `/agents/stream`
   (`app/features/agents/websocket.py`); the frontend reuses `useWebSocket`
   (`frontend/src/hooks/use-websocket.ts`); no new streaming primitive is invented.
4. **Additive only** — no schema changes, no Alembic migration, no breaking API edits, no
   new env var. One new backend slice, one new frontend page.
5. **Strict gates honored** — `ruff` + `mypy --strict` + `pyright --strict` + `pytest` +
   `pnpm tsc --noEmit` + `pnpm lint` + `pnpm test` all green.
6. **UI through skills** — the page is built via `frontend-design` + `shadcn-ui` and
   dogfooded via `webapp-testing` / `agent-browser` per `.claude/rules/ui-design.md`.

---

## Goal
A new **Showcase** nav item routes to `/showcase`. The page shows the 11 pipeline steps as
a vertical list of status cards. Clicking **Run pipeline** opens a WebSocket to
`/demo/stream`; the backend `demo` slice drives `precheck → (reset) → (seed) → status →
features → train ×3 → backtest ×3 → register → verify → agent → cleanup` against the app's
own HTTP surface in-process, emitting one `StepEvent` per step. Each card updates live
(🔄 → ✅/❌/⏭️/⚠️) with a one-line detail and a duration. The backtest step surfaces
per-model WAPE and highlights the winner; the register step surfaces the `run_id` and the
`demo-production` alias. A final summary banner shows `runs=3 winner=<model> wall_clock=<t>s`.

## Why
- **Portfolio identity.** `.claude/rules/product-vision.md` principle 1 — "portfolio-grade,
  end-to-end … every phase ships working code". The e2e proof currently lives only in
  `scripts/run_demo.py` + `Makefile` (`make demo`). A dashboard visitor can't see it.
- **Momentum.** PR #129 (`feat(api,docs): e2e demo pipeline + showcase script (#128)`) just
  landed the pipeline backend. This PRP turns that investment into the visible payoff.
- **Empty backlog.** `gh issue list --state open` is effectively empty (only #128/#130,
  both already merged) — a clean inflection point to invest in the demo surface.
- **Reviewer UX.** `frontend/src/pages/` has `dashboard, chat, admin, explorer/*,
  visualize/*` — none run or visualize the pipeline. The gap is real and unfilled.

## What
A new `app/features/demo/` backend slice exposing:
- `POST /demo/run` — synchronous; runs the whole pipeline and returns a `DemoRunResult`
  (all step outcomes). Simple consumer + the integration-test target.
- `WS /demo/stream` — streams one `StepEvent` per step for the live UI.

Both share a single orchestrator, `app/features/demo/pipeline.py:run_pipeline()`, an async
generator yielding `StepEvent`. A module-level `asyncio.Lock` ensures only one pipeline
runs at a time (concurrent attempts get RFC 7807 `409`).

A new React **Showcase** page (`frontend/src/pages/showcase.tsx`) consumes `/demo/stream`
via a thin `use-demo-pipeline.ts` hook (wrapping `useWebSocket`) and renders the live step
cards + summary.

### Success Criteria
- [ ] `GET /showcase` in the running SPA renders 11 idle step cards + a **Run pipeline** button.
- [ ] Clicking **Run pipeline** streams live updates; every step ends `✅` or `⏭️` on a
      seeded DB (agent step `⏭️` when no LLM key is configured).
- [ ] `POST /demo/run` returns `200` with a `DemoRunResult` whose `overall_status` is
      `"pass"` on a seeded DB; a second concurrent call returns `409 application/problem+json`.
- [ ] The backtest step's event `data` carries per-model WAPE; the page highlights the winner.
- [ ] The register step's event `data` carries `run_id`; `GET /registry/aliases/demo-production`
      returns that `run_id` after a run.
- [ ] `tests/test_demo_showcase_integration.py` (`@pytest.mark.integration`) passes against
      real Postgres.
- [ ] `app/features/demo/tests/test_pipeline.py` + `test_routes.py` pass (unit, mocked HTTP).
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ &&
      uv run pyright app/` all clean.
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` all clean.
- [ ] No Alembic migration; no new `.env` var; `scripts/run_demo.py` untouched.

---

## All Needed Context

### Documentation & References
```yaml
- url: https://www.python-httpx.org/advanced/transports/#asgi-transport
  why: httpx ASGITransport — call a FastAPI app in-process with no network/port
  critical: |
    `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://demo")`.
    This is how the demo slice drives /seeder, /forecasting, /backtesting, /registry,
    /agents WITHOUT importing those slices' Python modules — satisfying the vertical-slice
    rule. The test suite already uses this exact pattern (tests/conftest.py:4,15).

- url: https://fastapi.tiangolo.com/advanced/websockets/
  why: FastAPI @router.websocket() — accept(), receive_json(), send_json(), close()
  critical: |
    A prefixed APIRouter applies its prefix to websocket routes too:
    `APIRouter(prefix="/demo")` + `@router.websocket("/stream")` → `/demo/stream`.

- url: https://www.python-httpx.org/async/
  why: AsyncClient lifecycle + timeout
  critical: |
    Always `async with httpx.AsyncClient(...) as client:`. Pass an explicit timeout —
    the seed step is slow. Use httpx.Timeout(120.0, connect=5.0).

- url: https://docs.pydantic.dev/latest/concepts/models/
  why: Pydantic v2 models for StepEvent / DemoRunRequest / DemoRunResult
  critical: |
    REQUEST bodies under app/features/**/schemas.py with ConfigDict(strict=True) and a
    field typed date/datetime/UUID/Decimal MUST add Field(strict=False, ...) — enforced by
    app/core/tests/test_strict_mode_policy.py (AST walker). DemoRunRequest's fields are all
    JSON-native (int/bool) so it is safe with strict=True. EVENT/RESPONSE models
    (StepEvent, DemoRunResult) follow the StreamEvent precedent: a PLAIN BaseModel, NO
    strict=True — see app/features/agents/schemas.py:229 StreamEvent.

- file: scripts/run_demo.py
  why: THE reference implementation. The pipeline.py orchestration is a faithful in-process
    port of this file's 11 steps. Every step's request payload is proven here.
  critical: |
    - Step list + order: _step_table() at lines 935-953.
    - DemoContext accumulator: lines 119-148. Reuse the field set.
    - Per-step request bodies — copy verbatim:
        seed     → lines 414-428   (POST /seeder/generate)
        status   → lines 457-507   (GET /seeder/status + /dimensions/* for real IDs)
        features → lines 535-554   (POST /featuresets/compute)
        train    → lines 581-597   (POST /forecasting/train ×3 via asyncio.gather)
        backtest → lines 620-651   (POST /backtesting/run ×3 sequential)
        register → lines 673-793   (registry 2-step create→running→success + alias)
        verify   → lines 813-818   (GET /registry/runs/{id}/verify)
        agent    → lines 827-892   (POST /agents/sessions + /chat, skip if no key)
    - Winner selection: _select_winner() lines 338-356 (lowest non-NaN WAPE).
    - Model config payloads: _model_config_payload() lines 301-314.
    - LLM-key presence check: _llm_key_present() lines 317-335.
    - Artifact copy/hash dance (train dir vs registry root): lines 715-731 — MUST replicate.
    - StepError / RFC 7807 surfacing: lines 155-225.

- file: app/features/agents/websocket.py
  why: The WebSocket handler pattern to mirror for WS /demo/stream
  critical: |
    accept() → receive a start frame → stream events with send_json(event.model_dump(
    mode="json")) → handle WebSocketDisconnect. The demo stream is one-directional after
    the start frame (no per-message loop needed — run once, then close).

- file: app/features/agents/schemas.py
  why: StreamEvent (line ~229) is the event-model precedent — plain BaseModel,
    `data: dict[str, Any]`, `timestamp: datetime = Field(default_factory=_utc_now)`
  critical: Do NOT put ConfigDict(strict=True) on StepEvent. Mirror StreamEvent exactly.

- file: app/features/seeder/routes.py
  why: Router/slice conventions; the production guard `_check_seeder_enabled()` (lines 20-33)
  critical: |
    `router = APIRouter(prefix="/seeder", tags=["seeder"])`. The demo's seed step calls
    POST /seeder/generate which already enforces the prod guard — the demo slice needs NO
    separate env guard.

- file: app/features/analytics/  (whole dir)
  why: Precedent for a slice with NO models.py (read-only / stateless slice)
  critical: demo slice has no DB table → no models.py, no migration. analytics + dimensions
    both omit models.py. This is allowed.

- file: app/main.py
  why: Router wiring — lines 114-126. Add `app.include_router(demo_router)` after seeder.
  critical: |
    Import circularity: the WS/HTTP handlers must NOT import `app.main`. Get the live app
    via `request.app` / `websocket.app` and pass it into run_pipeline(app=...).

- file: tests/conftest.py
  why: ASGITransport AsyncClient fixture (`client`) + async `db_session` fixture
  critical: The integration test reuses the `client` fixture to POST /demo/run in-process.

- file: app/core/problem_details.py
  why: RFC 7807 error shape — the 409 "pipeline already running" response uses it
  critical: Raise via the slice's normal HTTPException path; register_exception_handlers
    in app/main.py serializes it to application/problem+json.

- file: frontend/src/hooks/use-websocket.ts
  why: Generic reconnecting WebSocket hook — use-demo-pipeline.ts wraps it
  critical: |
    `useWebSocket(url, { onMessage, autoConnect })`. Returns { status, send, disconnect,
    reconnect }. For the demo, set autoConnect:false and call reconnect()+send() on the
    "Run pipeline" click; disconnect() on pipeline_complete.

- file: frontend/src/pages/chat.tsx
  why: Reference for a page that consumes useWebSocket + renders streamed events
  critical: Mirror its event-accumulation-into-state shape.

- file: frontend/src/pages/admin.tsx
  why: Reference for a page that triggers a backend pipeline (the seeder) + renders Cards
  critical: Mirror Card/Button/Badge usage + loading/error states.

- file: frontend/src/lib/constants.ts
  why: ROUTES + NAV_ITEMS + WS_URL — add SHOWCASE route, nav entry, DEMO_WS_URL
  critical: WS_URL pattern at line 47. Derive DEMO_WS_URL the same way.

- file: frontend/src/App.tsx
  why: Lazy-route registration — add a <Route path={ROUTES.SHOWCASE}> like the others
  critical: Pages are lazy(() => import(...)); wrap in <Suspense fallback={<PageLoader/>}>.

- file: frontend/src/lib/api.ts
  why: The `api<T>()` fetch wrapper + ApiError — used by the POST /demo/run fallback path
  critical: ApiError carries the RFC 7807 ProblemDetail; surface detail.detail in the UI.

- file: frontend/src/types/api.ts
  why: TS type surface — add StepEvent, DemoRunRequest, DemoRunResult
  critical: Keep field names identical to the Pydantic models (snake_case on the wire).

- file: .claude/rules/output-formatting.md
  why: Glyphs ✅/❌/⚠️/⏭️/🔄 — reuse the same status vocabulary in the UI
- file: .claude/rules/security-patterns.md
  why: Never log secret VALUES; agent step logs key PRESENCE only (bool)
- file: .claude/rules/test-requirements.md
  why: New endpoint → route test (2xx + ≥1 error path); new stateful hook → vitest
- file: .claude/rules/ui-design.md
  why: UI built/dogfooded via frontend-design + shadcn-ui + webapp-testing skills
- file: .claude/rules/commit-format.md
  why: `type(scope): description (#issue)`; open the tracking issue FIRST
- file: .claude/rules/branch-naming.md
  why: `<type>/<kebab-slug>` off dev → `feat/demo-showcase-page`
```

### Current Codebase tree (relevant)
```bash
app/
├── main.py                              # MOD — wire demo_router
├── core/{config,problem_details}.py     # reuse (get_settings, RFC 7807)
└── features/
    ├── demo/                            # NEW SLICE — entire directory
    ├── seeder/{routes,schemas,service}.py    # demo calls POST /seeder/generate, GET /status
    ├── featuresets/{routes,schemas}.py       # demo calls POST /featuresets/compute
    ├── forecasting/{routes,schemas}.py       # demo calls POST /forecasting/train
    ├── backtesting/{routes,schemas}.py       # demo calls POST /backtesting/run
    ├── registry/{routes,schemas,storage}.py  # demo calls /registry/runs + /aliases + /verify
    ├── agents/{routes,websocket,schemas}.py  # demo calls /agents/sessions; WS pattern source
    ├── dimensions/                           # demo calls GET /dimensions/{stores,products}
    └── analytics/                            # precedent: slice with no models.py
scripts/run_demo.py                      # UNTOUCHED — the reference orchestration
tests/conftest.py                        # ASGITransport client fixture (reused)
frontend/src/
├── App.tsx                              # MOD — add /showcase route
├── lib/{constants,api}.ts               # MOD constants; reuse api
├── types/api.ts                         # MOD — add demo types
├── hooks/{use-websocket,index}.ts       # reuse use-websocket; MOD index
├── pages/{chat,admin}.tsx               # reference pages
└── components/{ui,layout,charts}/       # reuse Card/Button/Badge/StatusBadge
```

### Desired Codebase tree (files added / changed)
```bash
NEW  app/features/demo/__init__.py                   # slice exports
NEW  app/features/demo/schemas.py                    # StepEvent, DemoRunRequest, DemoRunResult
NEW  app/features/demo/pipeline.py                   # run_pipeline() async generator (~300 LOC)
NEW  app/features/demo/service.py                    # asyncio.Lock guard + run wrappers
NEW  app/features/demo/routes.py                     # POST /demo/run + WS /demo/stream
NEW  app/features/demo/tests/__init__.py
NEW  app/features/demo/tests/conftest.py             # ASGITransport client fixture
NEW  app/features/demo/tests/test_schemas.py         # event/request model validation
NEW  app/features/demo/tests/test_pipeline.py        # unit — mocked HTTP, step sequence + winner
NEW  app/features/demo/tests/test_routes.py          # route test: 200 + 409 + WS connect
NEW  tests/test_demo_showcase_integration.py         # @pytest.mark.integration — real DB
MOD  app/main.py                                     # +import + include_router(demo_router)
NEW  frontend/src/pages/showcase.tsx                 # the Showcase page
NEW  frontend/src/hooks/use-demo-pipeline.ts         # wraps useWebSocket, owns step state
NEW  frontend/src/hooks/use-demo-pipeline.test.ts    # vitest — hook state machine
NEW  frontend/src/components/demo/demo-step-card.tsx # one step card
NEW  frontend/src/components/demo/index.ts           # barrel export
MOD  frontend/src/App.tsx                            # +lazy import + <Route path=/showcase>
MOD  frontend/src/lib/constants.ts                   # +SHOWCASE route, NAV_ITEMS entry, DEMO_WS_URL
MOD  frontend/src/hooks/index.ts                     # +export use-demo-pipeline
MOD  frontend/src/types/api.ts                       # +StepEvent, DemoRunRequest, DemoRunResult
MOD  README.md                                       # "Try it in the browser" line
MOD  docs/_base/API_CONTRACTS.md                     # +demo slice rows + WS event section
MOD  docs/_base/RUNBOOKS.md                          # "Showcase pipeline fails" incident
MOD  docs/_base/REPO_MAP_INDEX.md                    # +rows for the demo slice + showcase page
KEEP scripts/run_demo.py                             # UNCHANGED (see Known Tradeoffs)
```

### Known Gotchas & Library Quirks
```python
# CRITICAL: VERTICAL-SLICE RULE. app/features/demo/ may NOT `import` from any other
#   app/features/* slice. It drives them over HTTP via httpx.ASGITransport(app=app).
#   Importing app.core.* (get_settings, problem_details) IS allowed.

# CRITICAL: NO `import app.main` inside the demo slice — app/main.py imports the demo
#   router, so importing main back creates a circular import. Obtain the live FastAPI
#   instance from `request.app` (HTTP handler) / `websocket.app` (WS handler) and pass it
#   into run_pipeline(app=...).

# CRITICAL: pipeline.py runs in `app/` → mypy --strict + pyright --strict apply, and
#   ruff does NOT exempt prints/annotations there (per-file-ignores only covers
#   scripts/** + examples/** + tests/**, pyproject.toml:92-101). Fully annotate; no print().

# CRITICAL: in-process httpx call — base_url is cosmetic, e.g. "http://demo.internal".
#   ASGITransport routes straight to the app; CORS does not apply (server-side).

# CRITICAL: the seed step is slow + CPU-heavy (pandas generation). Over ASGITransport it
#   runs in the SAME event loop as the WS handler, so it briefly stalls heartbeats.
#   MITIGATION: the Showcase page defaults skip_seed=true (assumes a seeded DB). Re-seed
#   is an explicit opt-in checkbox that warns it is slow. If skip_seed=true and the DB is
#   empty, the `status` step fails fast with a clear "seed the DB first" detail.

# CRITICAL: Postgres auto-increment does NOT reset across delete/seed. The freshly-seeded
#   store/product IDs are NOT 1. The `status` step MUST discover real IDs from
#   GET /dimensions/stores?page=1&page_size=1 and /dimensions/products?... — copy
#   run_demo.py:470-506 verbatim.

# CRITICAL: registry transitions are pending → running → success. You MUST PATCH the
#   intermediate `running` step. pending → success is rejected. (run_demo.py:761-781)

# CRITICAL: RunCreate uses Field(alias="model_config") — the on-the-wire JSON key is
#   "model_config", not "model_config_data". (run_demo.py:739)

# CRITICAL: aliases can ONLY point to runs in SUCCESS status — alias AFTER patch-to-success.
#   (run_demo.py:784-793)

# CRITICAL: artifact verify needs a copy. /forecasting/train writes to
#   settings.forecast_model_artifacts_dir; /registry verify resolves against
#   settings.registry_artifact_root. Copy the file + record a registry-relative URI.
#   Replicate run_demo.py:715-731 exactly.

# CRITICAL: agent step — skip gracefully (⏭️) when no API key matches the configured
#   agent_default_model provider. Reuse the run_demo.py:317-335 _llm_key_present() logic.
#   Log key PRESENCE (bool) only — NEVER the value (security-patterns.md).

# CRITICAL: backtest expanding + n_splits=3 + horizon=14 + min_train_size=30 needs the
#   seeded range ≥ 30 + 3*14 = 72 days. demo_minimal covers 2024-10-01..2024-12-31 (92d).
#   demo_minimal ALREADY EXISTS (app/shared/seeder/config.py:20,608 — landed in PR #129).
#   This PRP adds NO scenario.

# CRITICAL: StepEvent / DemoRunResult are EVENT models — plain BaseModel, NO strict=True
#   (mirror agents StreamEvent). Only DemoRunRequest (request body) gets
#   ConfigDict(strict=True); its int/bool fields need no Field(strict=False).

# GOTCHA: WS prefix — APIRouter(prefix="/demo") makes @router.websocket("/stream") serve
#   at /demo/stream. One router file handles both POST /run and WS /stream.

# GOTCHA: concurrency — two Showcase tabs => two pipelines => duplicate training + alias
#   thrash. Guard with a module-level asyncio.Lock in service.py: if locked, POST returns
#   409 RFC 7807; WS sends one error event then closes.

# GOTCHA: frontend WS URL — derive from VITE_API_BASE_URL:
#   const DEMO_WS_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8123')
#       .replace(/^http/, 'ws') + '/demo/stream'

# GOTCHA: useWebSocket auto-reconnects. For a one-shot pipeline, call disconnect() on the
#   pipeline_complete event so it does not reconnect and re-trigger.

# GOTCHA: every commit needs an open issue (commit-format.md). Open the tracking issue
#   BEFORE the first commit. No AI co-author trailer, ever.
```

### Known Tradeoffs (decided — do not re-litigate)
```yaml
duplication:
  decision: scripts/run_demo.py is left UNTOUCHED; pipeline.py is a fresh in-process port.
  why: run_demo.py just landed (PR #129) and is covered by e2e-nightly.yml. Refactoring it
       to share code risks regressing a nightly-CI surface and balloons scope. The ~200
       lines of orchestration are well-understood (the whole file is the reference). Both
       hit the same documented API contract + the same demo_minimal constants, so drift is
       low-risk and mechanically detectable.
  followup: a future PRP may converge run_demo.py onto app.features.demo.pipeline. Out of
            scope here. (See Open Questions.)
transport:
  decision: drive the app in-process via httpx.ASGITransport, NOT real-network localhost.
  why: keeps the slice import-free of other slices (vertical-slice rule) AND validates the
       real deployed contract, with no port/CORS concerns.
streaming:
  decision: WebSocket (mirrors /agents/stream + reuses useWebSocket), not SSE.
  why: the repo has a WS precedent + a generic WS hook; no SSE precedent. "Don't create new
       patterns when existing ones work."
```

---

## Implementation Blueprint

### Data models (`app/features/demo/schemas.py`)
```python
from __future__ import annotations
from datetime import UTC, datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

StepStatus = Literal["running", "pass", "fail", "skip", "warn"]
EventType = Literal["step_start", "step_complete", "pipeline_complete", "error"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DemoRunRequest(BaseModel):
    """Request body for POST /demo/run and the WS /demo/stream start frame."""
    model_config = ConfigDict(strict=True)  # all fields JSON-native → no Field(strict=False)
    seed: int = Field(default=42, ge=0)
    reset: bool = False        # wipe DB before seeding (destructive)
    skip_seed: bool = True     # default: assume a seeded DB (fast path; see Gotchas)


class StepEvent(BaseModel):
    """One streamed pipeline event. Plain BaseModel — mirror agents StreamEvent. NO strict."""
    event_type: EventType
    step_name: str
    step_index: int            # 1-based
    total_steps: int
    status: StepStatus | None = None      # None on step_start
    detail: str = ""
    duration_ms: float = 0.0
    data: dict[str, Any] = Field(default_factory=dict)   # winner metrics, run_id, etc.
    timestamp: datetime = Field(default_factory=_utc_now)


class DemoRunResult(BaseModel):
    """Aggregate result returned by the synchronous POST /demo/run."""
    overall_status: Literal["pass", "fail"]
    steps: list[StepEvent]                  # the step_complete events, in order
    winner_model_type: str | None = None
    winner_wape: float | None = None
    winning_run_id: str | None = None
    alias: str | None = None
    wall_clock_s: float = 0.0
```

### Orchestration (`app/features/demo/pipeline.py`)
```python
# Pseudocode — full step bodies are a faithful port of scripts/run_demo.py.

# Constants — copy from run_demo.py:66-81 (DEMO_ALIAS, DEMO_HORIZON, DEMO_MODEL_TYPES, ...)

class _StepError(Exception):
    """RFC 7807-aware typed failure — port of run_demo.py StepError (lines 155-173)."""

class _Client:
    """Thin httpx wrapper over ASGITransport — port of run_demo.py HttpClient (176-225)."""
    def __init__(self, app: FastAPI) -> None:
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://demo.internal",
            timeout=httpx.Timeout(120.0, connect=5.0),
        )
    # async __aenter__/__aexit__ + request(step, method, path, json_body) -> dict
    # non-2xx → raise _StepError with parsed problem+json title/detail/request_id

# DemoContext — port run_demo.py:119-148 (store_id, product_id, date_start/end,
#   train_results, backtest_results, winner_*, winning_run_id, session_id, ...)

# Each step is `async def step_x(ctx, client) -> tuple[StepStatus, str, dict]`
#   returning (status, human_detail, structured_data). Step bodies are verbatim ports:
#     step_precheck   ← run_demo.py:364-375
#     step_reset      ← run_demo.py:378-401   (gated on req.reset)
#     step_seed       ← run_demo.py:404-443   (gated on req.skip_seed)
#     step_status     ← run_demo.py:446-517   (discovers REAL store/product ids)
#     step_features   ← run_demo.py:520-563
#     step_train      ← run_demo.py:566-606   (asyncio.gather of 3 trains)
#     step_backtest   ← run_demo.py:609-670   (3 sequential; _select_winner :338-356)
#                       data={"per_model": {mt: metrics}, "winner": mt, "winner_wape": w}
#     step_register   ← run_demo.py:673-800   (2-step + alias + artifact copy/hash :715-731)
#                       data={"run_id": run_id, "alias": DEMO_ALIAS}
#     step_verify     ← run_demo.py:803-824
#     step_agent      ← run_demo.py:827-892   (_llm_key_present :317-335 → skip if no key)
#     step_cleanup    ← run_demo.py:895-924

async def run_pipeline(
    app: FastAPI, req: DemoRunRequest
) -> AsyncIterator[StepEvent]:
    """Drive the 11-step pipeline; yield a step_start + step_complete per step,
    then a final pipeline_complete event. Never raises — failures become fail events."""
    steps = _step_table()              # [(name, fn), ...] — gate reset/seed on req flags
    ctx = DemoContext(...)
    wall_start = time.monotonic()
    any_fail = False
    async with _Client(app) as client:
        for index, (name, fn) in enumerate(steps, start=1):
            yield StepEvent(event_type="step_start", step_name=name,
                            step_index=index, total_steps=len(steps))
            t0 = time.monotonic()
            try:
                status, detail, data = await fn(ctx, client)
            except _StepError as exc:
                status, detail, data = "fail", str(exc), {}
            except (httpx.HTTPError, OSError) as exc:
                status, detail, data = "fail", f"transport: {exc}", {}
            dur = (time.monotonic() - t0) * 1000
            yield StepEvent(event_type="step_complete", step_name=name,
                            step_index=index, total_steps=len(steps),
                            status=status, detail=detail, data=data, duration_ms=dur)
            if status == "fail":
                any_fail = True
                break                  # stop on first failure (like run_demo.py:1005)
    yield StepEvent(
        event_type="pipeline_complete", step_name="summary",
        step_index=len(steps), total_steps=len(steps),
        status="fail" if any_fail else "pass",
        detail=f"runs={len(ctx.backtest_results)} winner={ctx.winner_model_type} "
               f"wall_clock={time.monotonic() - wall_start:.0f}s",
        data={"winner_model_type": ctx.winner_model_type,
              "winner_wape": ctx.winner_wape,
              "winning_run_id": ctx.winning_run_id,
              "alias": DEMO_ALIAS if ctx.winning_run_id else None,
              "wall_clock_s": time.monotonic() - wall_start},
    )
```

### Service (`app/features/demo/service.py`)
```python
import asyncio
_pipeline_lock = asyncio.Lock()         # module-level — one pipeline at a time

class PipelineBusyError(Exception):
    """Raised when a pipeline run is already in progress."""

async def stream_pipeline(app, req) -> AsyncIterator[StepEvent]:
    if _pipeline_lock.locked():
        raise PipelineBusyError("A demo pipeline run is already in progress.")
    async with _pipeline_lock:
        async for event in run_pipeline(app, req):
            yield event

async def run_pipeline_sync(app, req) -> DemoRunResult:
    steps: list[StepEvent] = []
    final: StepEvent | None = None
    async for event in stream_pipeline(app, req):     # reuses the lock guard
        if event.event_type == "step_complete":
            steps.append(event)
        elif event.event_type == "pipeline_complete":
            final = event
    # assemble DemoRunResult from steps + final.data
```

### Routes (`app/features/demo/routes.py`)
```python
router = APIRouter(prefix="/demo", tags=["demo"])

@router.post("/run", response_model=DemoRunResult, summary="Run the e2e demo pipeline")
async def run_demo(request: Request, params: DemoRunRequest) -> DemoRunResult:
    try:
        return await service.run_pipeline_sync(request.app, params)
    except service.PipelineBusyError as exc:
        # RFC 7807 409 — register_exception_handlers serializes HTTPException
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.websocket("/stream")
async def stream_demo(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        raw = await websocket.receive_json()         # start frame: {seed, reset, skip_seed}
        params = DemoRunRequest.model_validate(raw)
        async for event in service.stream_pipeline(websocket.app, params):
            await websocket.send_json(event.model_dump(mode="json"))
    except service.PipelineBusyError as exc:
        await websocket.send_json({"event_type": "error", "step_name": "pipeline",
                                   "step_index": 0, "total_steps": 0, "status": "fail",
                                   "detail": str(exc)})
    except WebSocketDisconnect:
        logger.info("demo.websocket_disconnected")
    finally:
        await websocket.close()
```

### Frontend (`frontend/src/hooks/use-demo-pipeline.ts`)
```typescript
// Wraps useWebSocket. Owns: steps[] (11 entries, status-tracked), phase, summary.
// start(req): reset steps to "idle", reconnect(), send(JSON.stringify(req)).
// onMessage(StepEvent): step_start → mark step "running"; step_complete → set status +
//   detail + data; pipeline_complete → store summary, set phase "done", disconnect().
// Returns { steps, phase: 'idle'|'running'|'done'|'error', summary, start, isRunning }.
```

### Frontend page (`frontend/src/pages/showcase.tsx`)
```text
- Header: "End-to-End Showcase" + a short sentence on what the pipeline does.
- Controls Card: "Run pipeline" button (disabled while isRunning), a "Re-seed first"
  checkbox (warns: slow; sets skip_seed=false) and a "Reset DB" checkbox (destructive).
- Steps: vertical list of <DemoStepCard> — glyph (🔄/✅/❌/⏭️/⚠️), name, detail, duration.
- Backtest card: when data.per_model present, render per-model WAPE (kpi-card or a small
  bar) and highlight the winner.
- Summary banner on pipeline_complete: runs / winner / wall_clock; link to /explorer/runs.
- Error/empty states via ErrorDisplay + LoadingState (mirror admin.tsx).
```

### list of tasks (in execution order)
```yaml
Task 1 — Open the tracking GitHub issue (REQUIRED before any commit):
  RUN: gh issue create \
        --title "feat(api,ui): in-product demo showcase page" \
        --label enhancement \
        --body "Implements PRP-17. Adds an app/features/demo slice (POST /demo/run + WS
                /demo/stream) that drives the e2e pipeline in-process, and a React
                Showcase page that streams the run live. Builds on PRP-15 (#128)."
  CAPTURE: the issue number → use in EVERY commit below.

Task 2 — Backend slice scaffold + schemas:
  CREATE app/features/demo/__init__.py        — export router, run_pipeline, schemas
  CREATE app/features/demo/schemas.py         — DemoRunRequest, StepEvent, DemoRunResult
                                                (see "Data models" above; NO strict on
                                                 StepEvent/DemoRunResult)
  CREATE app/features/demo/tests/__init__.py

Task 3 — Orchestration pipeline:
  CREATE app/features/demo/pipeline.py
    - PORT constants + StepError + DemoContext + every step from scripts/run_demo.py
      (line refs in "All Needed Context"). Replace the network HttpClient with the
      ASGITransport _Client.
    - IMPLEMENT run_pipeline(app, req) -> AsyncIterator[StepEvent] (see pseudocode).
    - Gate `reset` on req.reset and `seed` on `not req.skip_seed`.
    - backtest step → data={"per_model":..., "winner":..., "winner_wape":...}.
    - register step → data={"run_id":..., "alias": DEMO_ALIAS}.
    - DO NOT import from any app/features/* slice. DO NOT import app.main.

Task 4 — Service guard:
  CREATE app/features/demo/service.py
    - module-level asyncio.Lock; PipelineBusyError.
    - stream_pipeline(app, req) — lock-guarded async generator.
    - run_pipeline_sync(app, req) -> DemoRunResult — drains stream_pipeline.

Task 5 — Routes:
  CREATE app/features/demo/routes.py
    - APIRouter(prefix="/demo", tags=["demo"]).
    - POST /run → run_pipeline_sync; PipelineBusyError → HTTPException(409).
    - WS /stream → accept, receive start frame, validate DemoRunRequest, stream events.
    - Mirror app/features/agents/websocket.py for the WS handler shape.

Task 6 — Wire into the app:
  MODIFY app/main.py:
    - ADD `from app.features.demo.routes import router as demo_router` with the other
      feature-router imports (alphabetical block, lines 16-24).
    - ADD `app.include_router(demo_router)` after `app.include_router(seeder_router)`
      (line 126).

Task 7 — Backend unit tests:
  CREATE app/features/demo/tests/conftest.py   — ASGITransport AsyncClient fixture
                                                 (mirror app/features/registry/tests/conftest.py)
  CREATE app/features/demo/tests/test_schemas.py
    - DemoRunRequest defaults (seed=42, skip_seed=True, reset=False); seed=-1 → ValidationError.
    - StepEvent round-trips model_dump(mode="json") with an ISO timestamp string.
  CREATE app/features/demo/tests/test_pipeline.py
    - Mock _Client (unittest.mock.AsyncMock) with canned 2xx bodies for every endpoint.
    - Assert run_pipeline yields step_start+step_complete for all 11 steps then
      pipeline_complete; assert winner = argmin WAPE; assert a failed step stops the run.
    - Assert agent step → "skip" when _llm_key_present() is False (monkeypatch get_settings).
  CREATE app/features/demo/tests/test_routes.py
    - POST /demo/run happy path (mock service.run_pipeline_sync) → 200 + DemoRunResult.
    - Concurrent run → 409 application/problem+json (acquire the lock, then POST).
    - WS /demo/stream connect → receives a step_start event (use the Starlette test
      client's websocket_connect; mirror however agents WS is exercised, else assert via
      the integration test only).

Task 8 — Integration test:
  CREATE tests/test_demo_showcase_integration.py
    - @pytest.mark.integration.
    - Reuse the `client` fixture from tests/conftest.py (ASGITransport).
    - Precondition: seed demo_minimal once (POST /seeder/generate) OR assert the test DB
      already has data; then POST /demo/run with {skip_seed:true, reset:false}.
    - Assert: 200; overall_status == "pass"; every step status in {pass, skip};
      winner_model_type is set; GET /registry/aliases/demo-production → winning_run_id.
    - Teardown: DELETE /registry/aliases/demo-production (best-effort).

Task 9 — Frontend types + constants + routing:
  MODIFY frontend/src/types/api.ts — add StepEvent, DemoRunRequest, DemoRunResult
    (snake_case fields matching the Pydantic models).
  MODIFY frontend/src/lib/constants.ts:
    - ROUTES.SHOWCASE = '/showcase'.
    - NAV_ITEMS — add { label: 'Showcase', href: ROUTES.SHOWCASE } (after Dashboard).
    - DEMO_WS_URL — derived from VITE_API_BASE_URL (see Gotchas).
  MODIFY frontend/src/App.tsx:
    - const ShowcasePage = lazy(() => import('@/pages/showcase')).
    - <Route path={ROUTES.SHOWCASE} element={<Suspense ...><ShowcasePage/></Suspense>}/>.

Task 10 — Frontend hook:
  CREATE frontend/src/hooks/use-demo-pipeline.ts (see pseudocode — wraps useWebSocket).
  MODIFY frontend/src/hooks/index.ts — export the hook.

Task 11 — Frontend components + page:
  CREATE frontend/src/components/demo/demo-step-card.tsx — one step card (glyph + name +
    detail + duration); reuse Card + Badge + status vocab from .claude/rules/output-formatting.md.
  CREATE frontend/src/components/demo/index.ts — barrel export.
  CREATE frontend/src/pages/showcase.tsx — the page (see "Frontend page" layout).
    Build with the frontend-design + shadcn-ui skills per .claude/rules/ui-design.md.

Task 12 — Frontend test:
  CREATE frontend/src/hooks/use-demo-pipeline.test.ts
    - vitest: feed synthetic StepEvent messages, assert steps[] transitions
      idle → running → pass and phase reaches 'done' on pipeline_complete.

Task 13 — Docs:
  MODIFY README.md — add a "Try it in the browser: open /showcase, click Run pipeline" line
    near the existing demo / make demo section.
  MODIFY docs/_base/API_CONTRACTS.md — add the demo slice rows (POST /demo/run, WS
    /demo/stream) + a short "WebSocket Events (/demo/stream)" subsection listing the
    StepEvent event_type values.
  MODIFY docs/_base/RUNBOOKS.md — add a "Showcase pipeline fails at step X" incident
    (skip_seed=true on an empty DB → seed first; 409 → another run in progress;
    agent ⏭️ → no LLM key).
  MODIFY docs/_base/REPO_MAP_INDEX.md — add rows for app/features/demo/ + the Showcase page.

Task 14 — Dogfood the running UI (mandatory per ui-design.md):
  - docker compose up -d ; uv run alembic upgrade head ; seed demo_minimal once.
  - uv run uvicorn app.main:app --port 8123 & ; cd frontend && pnpm dev.
  - Use the webapp-testing / agent-browser skill: open /showcase, click Run pipeline,
    confirm steps stream to ✅/⏭️, confirm the summary banner + winner highlight render,
    capture a screenshot. A green type-check is NOT proof the UI works.

Task 15 — Commit + PR:
  Branch: feat/demo-showcase-page (off dev, per branch-naming.md).
  Commits (each referencing the Task-1 issue; no AI co-author trailer):
    1. feat(api): demo slice — pipeline + service + routes for /demo/run + /demo/stream (#N)
    2. test(api): unit + integration coverage for the demo slice (#N)
    3. feat(ui): showcase page streaming the live e2e pipeline (#N)
    4. test(ui): use-demo-pipeline hook coverage (#N)
    5. docs(docs): document the demo slice + showcase page (#N)
  Open PR into dev; CI must be green; merge.
```

### Integration Points
```yaml
DATABASE:
  - migration: NONE. The demo slice persists nothing of its own; it reads/writes only
    through the existing slices' endpoints. No models.py (precedent: analytics, dimensions).
CONFIG:
  - No new env var. The agent step reads existing settings (openai/anthropic/google keys)
    via get_settings(); the seed step's prod-guard is enforced by /seeder/generate itself.
ROUTES (app/main.py):
  - import: `from app.features.demo.routes import router as demo_router`
  - wire:   `app.include_router(demo_router)`  (after seeder_router, main.py:126)
FRONTEND ROUTING:
  - ROUTES.SHOWCASE + NAV_ITEMS entry (constants.ts); lazy <Route> in App.tsx.
CI:
  - No new workflow. Existing ci.yml (lint/typecheck/test/migration-check) covers it.
    The integration test runs in ci.yml's `test` job (Postgres service already present).
```

---

## Validation Loop

### Level 1: Syntax & Style
```bash
uv run ruff check . --fix
uv run ruff format .
uv run mypy app/                 # strict — pipeline.py/service.py/routes.py must pass
uv run pyright app/              # strict
# Expected: zero errors. pipeline.py is under app/ → no print(), full annotations.
```

### Level 2: Backend unit tests (no DB)
```bash
uv run pytest -v -m "not integration" app/features/demo/ app/core/tests/test_strict_mode_policy.py
# Expected: all green. test_strict_mode_policy MUST still pass — it proves StepEvent did
# not accidentally get ConfigDict(strict=True) with a bare datetime field.
```

### Level 3: Backend integration test (real DB + in-process app)
```bash
docker compose up -d
uv run alembic upgrade head
uv run python scripts/seed_random.py --full-new --seed 42 --confirm   # seed once
uv run pytest -v -m integration tests/test_demo_showcase_integration.py
# Expected: PASS — overall_status == "pass", winner set, demo-production alias points to it.
```

### Level 4: Frontend gates
```bash
cd frontend
pnpm install
pnpm tsc --noEmit
pnpm lint
pnpm test --run
# Expected: clean. use-demo-pipeline.test.ts green.
```

### Level 5: Manual end-to-end (the maintainer's actual UX)
```bash
docker compose up -d && uv run alembic upgrade head
uv run uvicorn app.main:app --port 8123 &
until curl -fs http://127.0.0.1:8123/health; do sleep 2; done
cd frontend && pnpm dev          # http://localhost:5173
# Browser: open /showcase → click "Run pipeline".
# Expected: 11 step cards stream 🔄 → ✅ (agent ⏭️ if no LLM key); a summary banner
# shows "runs=3 winner=<model> wall_clock=<t>s"; the backtest card highlights the winner.
# Cross-check: GET http://localhost:8123/registry/aliases/demo-production returns the run_id.
```

---

## Final Validation Checklist
- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run mypy app/` clean (strict) — including `app/features/demo/`
- [ ] `uv run pyright app/` clean (strict)
- [ ] `uv run pytest -v -m "not integration"` all green (incl. test_strict_mode_policy)
- [ ] `uv run pytest -v -m integration tests/test_demo_showcase_integration.py` green
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` all clean
- [ ] `POST /demo/run` returns 200 + `DemoRunResult` on a seeded DB; concurrent call → 409
- [ ] WS `/demo/stream` streams `StepEvent`s; the page renders them live
- [ ] Manual `/showcase` run dogfooded in a real browser (webapp-testing / agent-browser);
      screenshot captured
- [ ] `GET /registry/aliases/demo-production` returns the winning `run_id` after a run
- [ ] No Alembic migration added; no new `.env`/`.env.example` var
- [ ] `scripts/run_demo.py` and `examples/e2e_smoke.sh` untouched (regression check)
- [ ] `app/features/demo/` contains no `import app.features.<other>` and no `import app.main`
- [ ] README + API_CONTRACTS + RUNBOOKS + REPO_MAP_INDEX updated
- [ ] Branch `feat/demo-showcase-page`; every commit references the Task-1 issue; no AI
      co-author trailer

---

## Anti-Patterns to Avoid
- ❌ Don't import other `app/features/*` slices into `app/features/demo/` — drive them over
  HTTP via ASGITransport. This is the load-bearing architectural rule.
- ❌ Don't `import app.main` in the demo slice — circular import. Use `request.app` /
  `websocket.app`.
- ❌ Don't put `ConfigDict(strict=True)` on `StepEvent` / `DemoRunResult` — they are event
  models; mirror agents `StreamEvent`. (A bare `datetime` under a `strict=True` model fails
  `test_strict_mode_policy.py`.)
- ❌ Don't refactor `scripts/run_demo.py` — it is a nightly-CI surface; pipeline.py is a
  separate in-process port (see Known Tradeoffs).
- ❌ Don't skip the `pending → running → success` registry transition.
- ❌ Don't default the Showcase to re-seeding — the seed step blocks the event loop in-process;
  default `skip_seed=true`, make re-seed an explicit opt-in.
- ❌ Don't log LLM API key values — log presence (bool) only.
- ❌ Don't add LightGBM to the demo — it's feature-flagged off; Phase-2 LightGBM is PRP-16.
- ❌ Don't hand-roll the page UI — use the `frontend-design` + `shadcn-ui` skills, dogfood
  with `webapp-testing` (per `.claude/rules/ui-design.md`).
- ❌ Don't claim the UI works on a green type-check alone — exercise it in a real browser.
- ❌ Don't `git push --force` on dev/main; don't add AI co-author trailers.

---

## Open Questions for the Maintainer (max 3)
1. **Run history** — should `/demo/run` persist a row per run (a `demo_run` table) so the
   Showcase page can show "last run: 3m ago, green"? This PRP keeps it stateless (no
   migration). Persisting it is a clean follow-up if you want run history.
2. **Convergence** — do you want a follow-up PRP to converge `scripts/run_demo.py` onto
   `app.features.demo.pipeline` (single-source the orchestration)? This PRP deliberately
   leaves them separate to de-risk.
3. **Re-seed default** — confirm the Showcase should default to `skip_seed=true` (fast,
   assumes a seeded DB). The alternative — always re-seed — is slower and briefly stalls
   the event loop in-process.

---

## Confidence Score

**8 / 10** for one-pass implementation success.

**Why high:**
- The orchestration is not novel — it is a line-referenced port of `scripts/run_demo.py`
  (the entire file is reproduced in this PRP's context). Every endpoint payload is proven.
- `demo_minimal` already exists; no scenario/seeder work, no migration, no new env var.
- The streaming pattern, the WS hook, the slice layout, and the ASGITransport client all
  have direct in-repo precedents cited with file+line.
- Validation gates are concrete and executable; the strict-mode invariant test guards the
  one subtle Pydantic gotcha.

**Why not 10:**
- The in-process WS handler running a CPU-heavy seed step is a real (if accepted) wrinkle;
  the `skip_seed=true` default mitigates it but the re-seed path may need a tuned timeout.
- WebSocket route-testing with the Starlette test client can be fiddly; the integration
  test is the firmer net and the unit WS test may need a light touch.
- The frontend page is genuine UI work — the live-streaming step list + winner highlight
  needs a browser dogfooding pass (Task 14) to be truly done; type-check alone won't catch
  a layout or event-wiring bug.

All three failure modes are caught deterministically by the validation loop and the fixes
are local (timeout tuning, test-client shape, UI iteration via webapp-testing).
