name: "PRP-34 — Batch Parallel Execution (Semaphore + TaskGroup + cooperative cancellation)"
description: |
  Activates the three forward-compat columns PRP-33 shipped on `batch_job`
  (`max_parallel`, `running_items`, `cancelled_items`) by rewiring
  `BatchService.submit` through a new `app/features/batch/runner.py`. The
  runner is a single `asyncio.Semaphore(effective_parallel)` inside an
  `asyncio.TaskGroup`; each child opens its own `AsyncSession`, writes the
  same pinned five-key metrics JSONB the MVP produces, and observes a
  cooperative `asyncio.Event` so `DELETE /batch/{batch_id}` cancels what
  hasn't started and gracefully drains what has. **No new Alembic
  migration** — every column the runner writes already exists on
  `batch_job` per PRP-33 (`app/features/batch/models.py:136-139`).

**Tracking issue:** (to be opened — see "Pre-flight" below)
**Source INITIAL:** `PRPs/INITIAL/INITIAL-batch-parallel-execution.md` (480 lines, refreshed in PR #283)
**Source feature doc:** `docs/optional-features/06-portfolio-forecasting-batch-runner.md` § Full Version → "Parallel execution controls"
**Depends on:** PRP-33 batch-runner MVP (merged in PR #281). All forward-compat schema is in place.
**Blocks:** none — sibling Full-Version PRPs (priority queue, export-and-retry, champion-and-heatmap) are independent.
**Successor PRPs:** none scheduled.

---

## Goal

The new module `app/features/batch/runner.py` becomes the **only** code path
that executes `batch_job_item` rows. `BatchService.submit` stops calling
`_pick_next` + `_execute_item` in a sequential loop and instead hands its
expanded item list to `runner.run_batch(...)`, which:

1. Computes `effective_parallel = min(batch_job.max_parallel, settings.batch_global_max_parallel)`.
2. Wraps an `asyncio.Semaphore(effective_parallel)` inside an
   `asyncio.TaskGroup`, creating one task per item.
3. In each child: skip-if-cancelled, acquire the semaphore, open a fresh
   `AsyncSession`, increment `batch_job.running_items`, delegate to
   `JobService.create_job` (lazy import), write the pinned metrics, decrement
   `running_items` in `finally`.
4. On `DELETE /batch/{batch_id}`: set a per-batch `asyncio.Event`, cancel each
   tracked `Task`, await drain with a bounded `Settings.batch_cancel_drain_timeout_seconds`
   (default 30s), then settle the parent.

A new `DELETE /batch/{batch_id}` endpoint surfaces cancellation; the existing
`POST /batch/forecasting` accepts `max_parallel` (already in the schema) and
returns a `BatchSubmitResponse` whose `running_items` and `cancelled_items`
now reflect real work. The `frontend/src/pages/visualize/batch.tsx` placeholder
gains a max-parallel `Slider` (a new shadcn primitive) on the submit form and
a "Cancel batch" `Button` + `AlertDialog` on the progress card.

## Why

- **Without a cap, the first 50-pair batch wedges the laptop.** The MVP runs
  items serially, so it is safe today but operationally slow. The naive next
  step is `asyncio.gather(*tasks)` over the items — repo precedent in
  `app/features/demo/pipeline.py:419`. At N=500 children that exhausts the
  SQLAlchemy `pool_size=5, max_overflow=10` pool (verified default — see
  `PRPs/ai_docs/asyncio-taskgroup-cancellation.md`), and a per-child sklearn
  fit blows out RAM. The Semaphore + TaskGroup primitive gives bounded
  concurrency + structured cancellation with **zero new dependencies**.
- **Operator needs a stop button.** A 200-item batch that's misconfigured
  (wrong date range, wrong model) currently has to run to completion. A
  cooperative cancel that stops what hasn't started and bounds the drain of
  what has is the difference between "useful tool" and "footgun".
- **Activates schema PRP-33 already shipped.** `batch_job.max_parallel`,
  `running_items`, `cancelled_items` are real columns; the MVP just doesn't
  write the last two. This PRP makes them live. No new migration needed.

## What

### User-visible behaviour

```bash
# Submit with explicit per-batch parallelism (clamped by global cap).
curl -X POST http://localhost:8123/batch/forecasting \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "backtest",
    "scope": {"kind": "manual", "store_ids": [1,2,3,4,5], "product_ids": [1,2,3,4,5]},
    "model_configs": [{"model_type": "naive"}],
    "start_date": "2024-01-01",
    "end_date": "2024-06-30",
    "max_parallel": 8
  }'
# → 202 Accepted with BatchSubmitResponse including running_items, cancelled_items
#    settle to consistent end-state per child outcomes.

# Cancel an in-flight batch.
curl -X DELETE http://localhost:8123/batch/{batch_id}
# → 200 BatchSubmitResponse with status='cancelled' once drain settles.
# → 404 application/problem+json on unknown batch_id.
# → 409 application/problem+json on already-terminal batch.
# → 504 application/problem+json if drain exceeds Settings.batch_cancel_drain_timeout_seconds.

# Frontend: /visualize/batch shows a max_parallel slider on submit, a live
# `running_items` chip on the parent card, and a "Cancel batch" button that
# pops an AlertDialog confirmation.
```

### Success Criteria

- [ ] `grep -rn "asyncio.gather" app/features/batch/` returns no production-code match (allowed in tests for synthetic concurrent-peak checks).
- [ ] `app/features/batch/runner.py` exists and is the only code path that schedules `batch_job_item` execution. `BatchService.submit` calls `runner.run_batch(...)` instead of looping `_pick_next` / `_execute_item`.
- [ ] `Settings.batch_global_max_parallel` defaults to `4`; `Settings.batch_cancel_drain_timeout_seconds` defaults to `30`; `.env.example` lists both placeholders.
- [ ] `POST /batch/forecasting` echoes `max_parallel` and the new `effective_max_parallel` field in `BatchSubmitResponse`; `running_items` and `cancelled_items` are accurate at every observation moment.
- [ ] `DELETE /batch/{batch_id}` returns 200 + cancelled parent on success, 404 on missing, 409 on terminal, 504 on drain timeout — all RFC 7807.
- [ ] The 8 unit tests + 3 integration tests + 2 chaos tests in § Test Plan pass. The semaphore-cap regression test (`test_semaphore_caps_concurrency`) **would have caught an unbounded `gather`** and is the load-bearing spec.
- [ ] `frontend/src/pages/visualize/batch.tsx` renders a max-parallel `Slider` (new shadcn) and a "Cancel batch" `Button` + `AlertDialog`. The submit form sends `max_parallel`; the progress card shows `running_items` live.
- [ ] All five validation gate commands green locally and in CI:
  ```bash
  uv run ruff check . && uv run ruff format --check .
  uv run mypy app/ && uv run pyright app/
  uv run pytest -v -m "not integration"
  docker compose up -d && uv run pytest -v -m integration
  cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run
  ```
- [ ] No Alembic migration added (the three columns are already on the table).
- [ ] No managed-cloud / Celery / Redis dependency introduced.
- [ ] `.claude/rules/commit-format.md` already lists `batch` in the scope allow-list — commits use `feat(batch): ...` / `feat(batch,ui): ...` / `feat(batch,api): ...` referencing the tracking issue.

## All Needed Context

### Documentation & References

```yaml
# MUST READ — load these before implementing
- file: PRPs/INITIAL/INITIAL-batch-parallel-execution.md
  why: 480-line source spec. The Data Model Delta, API Delta, and Risks tables are authoritative. The pseudocode is illustrative — see "Known Gotchas" below for the corrections.

- file: PRPs/ai_docs/asyncio-taskgroup-cancellation.md
  why: Verified asyncio semantics on Python 3.12.13. Captures the three working cancellation mechanisms, the broken `tg.cancel_scope.cancel()` claim in the INITIAL, the ContextVar inheritance into child tasks (so `request_id` propagates automatically), and the SQLAlchemy pool default math. Re-runnable verification commands inline. **Read end-to-end before touching runner.py.**

- file: PRPs/PRP-33-batch-runner-mvp.md
  why: The MVP PRP. Phase 0 § "Cross-Slice Coordination Matrix" pinned every forward-compat column, the partial picker index predicate, the `FOR UPDATE SKIP LOCKED` invariant. PRP-34 must NOT break any of those — the same tests still pass.

- file: app/features/batch/models.py
  why: The three columns this PRP activates live at lines 136-139 (`running_items`, `cancelled_items`, `max_parallel`). The state machines at lines 90-110 already accept the `running → completed/failed/cancelled` and `pending → cancelled` transitions — no model change required.

- file: app/features/batch/service.py
  why: The existing sequential picker loop at lines 152-157 is what this PRP replaces. The lazy `JobService` import pattern at lines 255-257 is what each child reuses. The `_settle` helper at lines 350-391 already aggregates by status — PRP-34 leaves it as-is (it already counts cancelled_items).

- file: app/features/batch/schemas.py
  why: `BatchSubmitRequest.max_parallel` is at line 135 (already validated `ge=1, le=64`). `BatchSubmitResponse` at lines 164-181 already carries `running_items` and `cancelled_items` — PRP-34 adds ONE field, `effective_max_parallel`, to the response.

- file: app/features/batch/routes.py
  why: Three endpoints exist (POST forecasting, GET {id}, GET {id}/items). PRP-34 adds `DELETE /batch/{batch_id}` mirroring the GET shape, 404/409/504 problem+json on the failure paths.

- file: app/features/batch/tests/conftest.py
  why: `db_session` cleans rows where `batch_id.like("test%")` — every new integration test must prefix its batch_id with `test` (use the seed fixtures, they already produce uuid-hex batch_ids; cleanup keys on prefix, so call the helper that overrides batch_id when needed).

- file: app/features/batch/tests/test_routes_integration.py
  why: Reference integration shape — `ASGITransport(app=app)` client fixture, structlog event capture via `structlog.testing.capture_logs`, real Postgres + the `BATCH-` store/product seed fixtures.

- file: app/features/batch/tests/test_service.py
  why: Reference unit-test shape — `_make_job_response` builds a synthetic `JobResponse`; `AsyncMock` proves no DB call lands; the `pytestmark = pytest.mark.integration` is absent here so tests run under `-m "not integration"`.

- file: app/features/demo/service.py
  why: Module-level `asyncio.Lock` + `PipelineBusyError` is the prior art for "one X at a time in the process". The runner's `_ACTIVE_BATCHES` dict + `CancelHandle` follow the same vibe but allow multiple batches; one cancel handle per batch.

- file: app/features/demo/pipeline.py
  why: Lines 418-420 show the `asyncio.gather(...)` pattern this PRP must not import into the batch slice. At N=3 it's fine; at N=500 it's the headline risk.

- file: app/core/database.py
  why: `get_engine()` and `get_session_maker()`. Each child opens its own session via a fresh `async with session_maker() as session:` block. Do NOT use the request's `Depends(get_db)` session inside the runner — that session belongs to the HTTP request lifecycle, not the child task.

- file: app/core/config.py
  why: Where the two new Settings fields land. Mirror the `batch_max_scope_expansion` placement (line 122). `@lru_cache` on `get_settings()` (line 212) — env-var override needs a uvicorn restart, document on the field.

- file: app/core/exceptions.py
  why: `NotFoundError` (404), `ConflictError` (409). 504 needs a new exception or a direct `problem_response(status=504, ...)` call — see Task 6 below. RFC 7807 envelope is automatic via the registered handler.

- file: app/core/problem_details.py
  why: `problem_response(status, title, detail, error_code)` for the 504 path. The `ERROR_TYPES` dict at line 26 catalogues canonical error codes — `GATEWAY_TIMEOUT` may need adding.

- file: app/core/logging.py
  why: `request_id_ctx: ContextVar` is read by the `add_request_id` structlog processor. TaskGroup children inherit the request's contextvars, so child events auto-carry the parent request_id (verified — see ai_doc).

- file: app/core/tests/test_strict_mode_policy.py
  why: AST-walker invariant. PRP-34 does NOT add any new `date | datetime | time | UUID | Decimal` field to a `ConfigDict(strict=True)` model (the existing `start_date`/`end_date` already carry `Field(strict=False, ...)`). Still — running the policy linter is in the validation gates.

- file: app/features/jobs/service.py
  why: `JobService.create_job` at lines 150-191 is the delegation target each runner child invokes. The MVP runner already calls it (lines 285 of batch/service.py); the runner moves the same call into a child coroutine.

- file: app/features/forecasting/service.py
  why: Lines 786-787 — the lazy-import precedent. Every cross-slice import inside the runner stays lazy (in-method) to avoid the alembic cold-boot cycle documented in memory `[[computed-field-cross-slice-cycle]]`.

- file: frontend/src/pages/visualize/batch.tsx
  why: 213-line placeholder ALREADY EXISTS (created by PRP-33). PRP-34 modifies this file to add the slider, the cancel button, and the running_items chip. The page route is already wired in `App.tsx`.

- file: frontend/src/hooks/use-batches.ts
  why: `useSubmitBatch`, `useBatch` (polls 2s while pending/running), `useBatchItems`. PRP-34 adds `useCancelBatch` mutation.

- file: frontend/src/types/api.ts
  why: Lines 336-360 — `BatchSubmitRequest` already has `max_parallel`; `BatchSubmitResponse` already has `running_items`/`cancelled_items`. PRP-34 adds `effective_max_parallel?: number` to the response type.

- file: .claude/rules/shadcn-ui.md
  why: ALL shadcn component work goes through the `shadcn` skill + `mcp__shadcn__*` MCP tools. The slider is added via `pnpm dlx shadcn@latest add slider` from `frontend/`, not by hand-writing the file.

- url: https://docs.python.org/3.12/library/asyncio-task.html#asyncio.TaskGroup
  section: TaskGroup — full signature and exception-group semantics
  critical: TaskGroup's ONLY public surface is `create_task`. No `cancel_scope`, no `cancel()`, no `tasks`. Cancel by holding the Task references `create_task` returns and calling `task.cancel()` on each.

- url: https://docs.python.org/3.12/library/asyncio-sync.html#asyncio.Semaphore
  section: Semaphore — async context manager
  critical: `async with sem:` acquires on entry, releases on exit (including the exception path). Wrap WORK, not task scheduling.

- url: https://peps.python.org/pep-0654/
  section: PEP 654 — except* syntax
  critical: Use `except* asyncio.CancelledError:` to catch the `ExceptionGroup` TaskGroup re-raises when its children were cancelled. Plain `except asyncio.CancelledError:` would not catch the group.

- url: https://docs.sqlalchemy.org/en/20/core/pooling.html#sqlalchemy.pool.QueuePool
  section: QueuePool — pool_size + max_overflow + timeout
  critical: Default `pool_size=5`, `max_overflow=10`, `timeout=30s` on `create_async_engine`. Verified by direct probe (see ai_doc § "SQLAlchemy async pool defaults"). `batch_global_max_parallel ≤ 12` keeps headroom for the HTTP request + cancel endpoint + settle session.
```

### Current Codebase tree (relevant slices only)

```
app/
├── core/
│   ├── config.py                 # Settings model — add two fields here
│   ├── database.py               # get_session_maker() — each runner child opens its own
│   ├── exceptions.py             # NotFoundError, ConflictError, ValidationError
│   ├── logging.py                # request_id_ctx ContextVar — inherited by TaskGroup children
│   ├── middleware.py             # RequestIdMiddleware
│   └── problem_details.py        # problem_response() helper
├── features/
│   ├── batch/
│   │   ├── __init__.py
│   │   ├── models.py             # max_parallel, running_items, cancelled_items ALREADY HERE
│   │   ├── schemas.py            # BatchSubmitRequest.max_parallel ALREADY HERE
│   │   ├── service.py            # sequential picker loop — REPLACE with runner call
│   │   ├── routes.py             # POST/GET endpoints — ADD DELETE here
│   │   └── tests/
│   │       ├── conftest.py       # BATCH-* seed fixtures, ASGITransport client
│   │       ├── test_routes_integration.py
│   │       └── test_service.py
│   ├── demo/
│   │   ├── service.py            # asyncio.Lock single-flight prior art
│   │   └── pipeline.py:418-420   # asyncio.gather anti-pattern (don't copy into batch)
│   └── jobs/
│       └── service.py            # JobService.create_job (delegation target)
└── main.py                       # routers wired here; no change needed for new DELETE
frontend/src/
├── components/ui/
│   ├── slider.tsx                # ABSENT — add via shadcn MCP
│   └── (alert-dialog, button, card, progress, badge, table — ALL present)
├── hooks/
│   └── use-batches.ts            # ADD useCancelBatch here
├── pages/visualize/
│   └── batch.tsx                 # 213-line placeholder — extend with slider+cancel
└── types/
    └── api.ts                    # add effective_max_parallel to BatchSubmitResponse
PRPs/ai_docs/
└── asyncio-taskgroup-cancellation.md   # NEW — captured for this PRP
```

### Desired Codebase tree (delta after PRP-34)

```
app/features/batch/
├── runner.py                     # NEW — Semaphore + TaskGroup + CancelHandle registry
├── service.py                    # MODIFIED — submit() delegates to runner.run_batch()
├── routes.py                     # MODIFIED — add DELETE /batch/{batch_id}
├── schemas.py                    # MODIFIED — add effective_max_parallel to response
└── tests/
    ├── test_runner.py                # NEW — unit + integration (8 cases)
    ├── test_routes_cancel.py         # NEW — DELETE endpoint (3 cases)
    └── test_runner_chaos.py          # NEW — orphan-state regression (2 cases)
app/core/
├── config.py                     # MODIFIED — +batch_global_max_parallel, +batch_cancel_drain_timeout_seconds
├── exceptions.py                 # MODIFIED — +GatewayTimeoutError (504) and ERROR_TYPES key
└── problem_details.py            # MODIFIED — +ERROR_TYPES["GATEWAY_TIMEOUT"]
frontend/src/
├── components/ui/slider.tsx      # NEW — added via shadcn MCP
├── hooks/use-batches.ts          # MODIFIED — +useCancelBatch
├── pages/visualize/batch.tsx     # MODIFIED — slider on submit, cancel button on progress card
└── types/api.ts                  # MODIFIED — +effective_max_parallel?: number on BatchSubmitResponse
.env.example                      # MODIFIED — +BATCH_GLOBAL_MAX_PARALLEL=4, +BATCH_CANCEL_DRAIN_TIMEOUT_SECONDS=30
PRPs/ai_docs/asyncio-taskgroup-cancellation.md  # NEW
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: asyncio.TaskGroup has NO .cancel_scope on stdlib Python 3.12.
# The INITIAL's pseudocode references tg.cancel_scope.cancel() — that's anyio
# API, not stdlib. Cancel by holding Task refs and calling task.cancel() on each.
#
# Verify: uv run python -c "import asyncio; print(dir(asyncio.TaskGroup))"
# Expected: only 'create_task' as a public method.
#
# See PRPs/ai_docs/asyncio-taskgroup-cancellation.md for the verified pattern.

# CRITICAL: catch the ExceptionGroup, not bare CancelledError.
# After a TaskGroup body cancels children, exceptions surface as an
# ExceptionGroup (PEP 654). Use `except* asyncio.CancelledError:` — plain
# `except asyncio.CancelledError:` will NOT catch the group.
#
# Verify: uv run python -c "
# import asyncio
# async def c(): await asyncio.sleep(10)
# async def m():
#     try:
#         async with asyncio.TaskGroup() as tg:
#             t = tg.create_task(c()); await asyncio.sleep(0.01); t.cancel()
#     except* asyncio.CancelledError as eg:
#         print('caught', len(eg.exceptions))
# asyncio.run(m())
# "
# Expected: 'caught 1'

# CRITICAL: each child opens its OWN AsyncSession.
# The HTTP-request session is bound to the request's lifecycle; reusing it
# across N concurrent tasks corrupts identity-map state and serialises work.
# Pattern: `async with session_maker() as session:` inside the child, after
# acquiring the semaphore. Verified default pool: pool_size=5, max_overflow=10.
#
# Verify: uv run python -c "
# from sqlalchemy.ext.asyncio import create_async_engine
# e = create_async_engine('postgresql+asyncpg://x:x@h:5433/x')
# print(e.pool.size(), e.pool._max_overflow, e.pool._timeout)
# "
# Expected: 5 10 30.0

# CRITICAL: Semaphore wraps the work, not the task creation.
# Pattern that DEFEATS the cap:
#     async with sem:           # acquired in the runner, not in the child
#         tg.create_task(child())   # tg.create_task is fast — sem releases instantly
# Correct pattern:
#     async def child(item):
#         async with sem:       # acquired by the child, inside its own body
#             ...               # the actual work
#     for item in items:
#         tg.create_task(child(item))

# CRITICAL: ContextVar inheritance — request_id propagates AUTOMATICALLY.
# Tasks created with asyncio.create_task (and tg.create_task) inherit the
# current contextvars.Context (CPython 3.7+ documented). So
# `app.core.logging.request_id_ctx` flows from the POST handler into every
# TaskGroup child — no explicit `bind_contextvars` needed. The
# `batch.item_started`/`batch.item_completed` log lines auto-correlate to the
# parent request's X-Request-ID.

# CRITICAL: do NOT iterate asyncio.all_tasks() to find children to cancel.
# The INITIAL's cancel_batch sketch scans all_tasks() and matches on
# task.get_name().startswith(f"batch:{batch_id}:"). Brittle: collisions across
# concurrent batches, cancels unrelated request handlers, breaks silently if
# `name=` is dropped in a refactor. Keep the Task references in the
# CancelHandle.tasks list when create_task returns them; cancel via that list.

# GOTCHA: sklearn/LightGBM fits are SYNC C code — uncancellable mid-fit.
# A child that's already inside JobService.create_job's training call will
# NOT observe CancelledError until the fit returns. That's acceptable — the
# runner times out the drain via batch_cancel_drain_timeout_seconds (default
# 30s) and surfaces 504 if the operator wants to bail. Document in the
# DELETE route docstring + a tooltip on the frontend Cancel button.

# GOTCHA: BatchService.submit currently runs the picker LOOP inside the same
# request handler — the response only returns after every item completes.
# Today this is a feature (the response is the settled parent). PRP-34
# preserves it: the runner is awaited inside submit(), the response is still
# the settled parent. The DELETE endpoint is what gives operators a parallel
# control channel — it works because `runner.run_batch` registers a
# CancelHandle that's discoverable from any other request handler.

# GOTCHA: integration-test cleanup keys on batch_id LIKE 'test%'.
# `app/features/batch/tests/conftest.py:db_session` deletes only batches
# whose ID starts with `test`. The MVP submit() generates uuid hex
# batch_ids — the conftest already comments on this. For runner tests that
# explicitly set batch_id, prefix it with `test`. For tests that go through
# the public submit endpoint, the cleanup also wipes data_platform rows
# created by the seed fixtures (`BATCH-%` codes), which transitively
# cascades to batch_job_item via FK ON DELETE CASCADE.

# GOTCHA: shadcn MUST be driven through the MCP, not hand-written.
# `.claude/rules/shadcn-ui.md` is explicit: invoke the `shadcn` skill, use
# `mcp__shadcn__get_add_command_for_items` to get the exact `pnpm dlx`
# command, run it from frontend/, then audit. The slider primitive is one
# of shadcn's standard New York components — it lives at
# @/components/ui/slider after install.
```

## Implementation Blueprint

### Data models and structure

**No new ORM models.** The runner reads and writes existing columns on
`batch_job` (lines 136-139 of `app/features/batch/models.py`). No new schema
migration.

**Two new Settings fields** (`app/core/config.py`):

```python
# Batch Runner Concurrency (PRP-34)
batch_global_max_parallel: int = Field(
    default=4,
    ge=1,
    le=64,
    description=(
        "Hard upper bound on concurrent in-flight batch_job_item executions "
        "across all active batches on this host. Sized for the docker-compose "
        "Postgres pool (pool_size=5, max_overflow=10). Effective per-batch "
        "parallelism is min(batch_job.max_parallel, this). Env override: "
        "BATCH_GLOBAL_MAX_PARALLEL=8 — requires uvicorn restart."
    ),
)
batch_cancel_drain_timeout_seconds: int = Field(
    default=30,
    ge=1,
    le=600,
    description=(
        "Max seconds DELETE /batch/{batch_id} waits for in-flight children "
        "to settle before returning RFC 7807 504. In-flight sklearn/LightGBM "
        "fits are uncancellable mid-call, so a long fit can stall the drain."
    ),
)
```

**One new response field** (`app/features/batch/schemas.py:BatchSubmitResponse`):

```python
effective_max_parallel: int = 0  # min(req.max_parallel, settings.batch_global_max_parallel)
```

(Default `0` for backward compatibility when reading old rows; the runner
always sets it. `from_attributes=True` is already on the model_config, so
`BatchSubmitResponse.model_validate(batch)` needs the field to materialise
from a runtime computation — see Task 4 below.)

### Tasks (dependency-ordered)

```yaml
Task 1 — Capture verified asyncio mechanics
CREATE PRPs/ai_docs/asyncio-taskgroup-cancellation.md:
  - MIRROR pattern from: PRPs/ai_docs/exogenous-regressor-forecasting.md (single-topic deep-dive)
  - CONTENT: TaskGroup API surface (only create_task), the three working cancel
    mechanisms (per-task cancel + raise-inside + cooperative Event), the
    INITIAL's broken cancel_scope claim, ContextVar inheritance proof,
    SQLAlchemy pool default math, sklearn-fit-uncancellable note. Include
    `uv run python -c "..."` verification commands for each claim.
  - STATUS: this file is already authored — verify line count > 100 and that
    each verification command actually runs.

Task 2 — Settings + .env.example
MODIFY app/core/config.py:
  - FIND pattern: "batch_max_scope_expansion: int = 1000"
  - INJECT after line: two new Field(...) entries per § "Data models and structure" above.
  - PRESERVE existing alphabetic-by-section ordering — these go in the "Batch runner" block.
MODIFY .env.example:
  - FIND pattern: "BATCH_MAX_SCOPE_EXPANSION=1000"
  - INJECT after line:
    BATCH_GLOBAL_MAX_PARALLEL=4
    BATCH_CANCEL_DRAIN_TIMEOUT_SECONDS=30
  - PRESERVE block comment style above the new lines.

Task 3 — Exception class for 504 drain timeout
MODIFY app/core/problem_details.py:
  - FIND pattern: "ERROR_TYPES: dict[str, str]" (the canonical-codes dict)
  - INJECT new key: "GATEWAY_TIMEOUT": "https://forecastlabai.dev/problems/gateway-timeout"
MODIFY app/core/exceptions.py:
  - FIND pattern: "class UnprocessableEntityError(ForecastLabError):"
  - INJECT after the full UnprocessableEntityError class:
    class GatewayTimeoutError(ForecastLabError):
        """Raised when a bounded drain (e.g., batch cancellation) exceeds its
        configured budget. Surfaces RFC 7807 504.

        Distinct from a 408 client-timeout: the client didn't time out, the
        server's own internal drain budget did.
        """
        error_type_uri: str = ERROR_TYPES["GATEWAY_TIMEOUT"]
        def __init__(
            self,
            message: str = "Operation drain exceeded budget",
            details: dict[str, Any] | None = None,
        ) -> None:
            super().__init__(
                message=message,
                code="GATEWAY_TIMEOUT",
                status_code=504,
                details=details,
            )

Task 4 — Add effective_max_parallel to BatchSubmitResponse
MODIFY app/features/batch/schemas.py:
  - FIND pattern: "class BatchSubmitResponse(BaseModel):"
  - In the body, INJECT after `cancelled_items: int`:
    effective_max_parallel: int = Field(
        default=0,
        ge=0,
        description=(
            "min(max_parallel, settings.batch_global_max_parallel) actually applied "
            "by the runner. 0 means 'not yet set' for legacy rows; the runner "
            "always populates it on submit."
        ),
    )
  - PRESERVE ConfigDict(from_attributes=True). Add max_parallel mirror if not already present.

Task 5 — Create the runner module
CREATE app/features/batch/runner.py:
  - MIRROR pattern from: app/features/demo/service.py (module-level lock as registry)
  - CONTENT: module-level `_ACTIVE_BATCHES: dict[str, CancelHandle]`, CancelHandle
    dataclass holding the asyncio.Event + list[asyncio.Task], `run_batch()`
    coroutine implementing Semaphore + TaskGroup + per-child fresh AsyncSession
    + cooperative cancel + bounded drain, `cancel_batch()` setter for
    DELETE-side. NO sibling-slice imports at module scope — lazy in-method only.
  - GOTCHA: each child opens its own session via get_session_maker(); never
    reuse the parent runner's session for child work.
  - GOTCHA: keep Task refs in CancelHandle.tasks; never asyncio.all_tasks()
    name-prefix scan.

Task 6 — Rewire BatchService.submit through the runner
MODIFY app/features/batch/service.py:
  - FIND pattern: the `while True: next_item = await self._pick_next(...)` block (lines ~152-157)
  - REPLACE the loop with a single `await runner.run_batch(...)` call passing
    the list of inserted items and the effective_max_parallel value.
  - KEEP _pick_next and _execute_item on the class (test_picker_query_uses_skip_locked
    still asserts the SQL; future PRPs may use the picker for multi-worker mode).
  - GOTCHA: BatchService.submit still computes effective_parallel itself so it
    can write it onto the parent record before the runner starts. The runner
    re-computes it defensively (so a direct caller can't bypass).
  - PRESERVE the existing logger.info("batch.created", ...) and the `_settle` call after the runner returns.

Task 7 — DELETE /batch/{batch_id} endpoint
MODIFY app/features/batch/routes.py:
  - FIND pattern: the last decorated route in the file (`list_batch_items`).
  - APPEND a new route:
      @router.delete("/{batch_id}", response_model=BatchSubmitResponse, ...)
      async def cancel_batch(batch_id: str, db: AsyncSession = Depends(get_db)) -> BatchSubmitResponse: ...
  - LOGIC:
      1. Service.get(batch_id) → None ⇒ raise NotFoundError.
      2. If parent.status in {completed, failed, partial, cancelled} ⇒ ConflictError.
      3. Call runner.cancel_batch(batch_id) — returns True iff registered.
         - Returns False ⇒ Conflict (already settled or never registered).
      4. Await drain with asyncio.wait_for(handle.completed_event.wait(), timeout=settings.batch_cancel_drain_timeout_seconds).
         - TimeoutError ⇒ raise GatewayTimeoutError(message=f"Drain exceeded {timeout}s; parent settle pending.")
      5. Re-load the parent (post-settle) and return BatchSubmitResponse.
  - LOG events: batch.cancel_requested, batch.cancel_drain_timeout, batch.cancelled.

Task 8 — Unit tests
CREATE app/features/batch/tests/test_runner.py:
  - SCAFFOLD per app/features/batch/tests/test_service.py — async def + pytest-asyncio auto-mode.
  - TESTS:
      test_semaphore_caps_concurrency
        - 5 fake child coroutines each await asyncio.sleep(0.05) inside the runner with max_parallel=2
        - Use a shared list to record start/finish events; observed concurrent peak == 2.
        - THIS IS THE LOAD-BEARING REGRESSION TEST FOR UNBOUNDED-FAN-OUT.
      test_settings_global_cap_clamps_max_parallel
        - max_parallel=32, settings.batch_global_max_parallel=4 ⇒ peak ≤ 4.
      test_child_failure_does_not_abort_siblings
        - One of 5 children raises RuntimeError; other 4 reach completion.
        - The runner does NOT propagate the failure to the TaskGroup; each
          child's _execute body catches Exception and writes status=failed.
      test_cancel_pending_child_marks_cancelled_without_running
        - max_parallel=1, 3 items. After first starts, cancel event fires.
        - Assert items 2 and 3 transition pending → cancelled, never opened a session.
      test_cancel_running_child_propagates_cancellederror
        - One child sleeps 1s; cancel after 0.05s. Child observes CancelledError, finally block writes cancelled.

Task 9 — Cancel-endpoint route tests
CREATE app/features/batch/tests/test_routes_cancel.py:
  - SCAFFOLD per app/features/batch/tests/test_routes_integration.py — ASGITransport client.
  - TESTS:
      test_delete_404_unknown_batch — RFC 7807 404; problem+json content-type.
      test_delete_409_terminal_batch — submit + wait for settle, then DELETE → 409.
      test_delete_504_drain_timeout — patch Settings(batch_cancel_drain_timeout_seconds=0), DELETE returns 504 problem+json.

Task 10 — Chaos tests (integration)
CREATE app/features/batch/tests/test_runner_chaos.py:
  - SCAFFOLD per app/features/batch/tests/test_routes_integration.py (pytestmark = pytest.mark.integration).
  - TESTS:
      test_cancel_mid_flight_does_not_orphan_running_items
        - Submit a 4-item batch with max_parallel=2 + fake-slow children, cancel mid-run.
        - SELECT COUNT(*) FROM batch_job_item WHERE batch_id=? AND status='running' → 0.
      test_parent_status_progresses_as_children_complete
        - 6 items, max_parallel=2 — sample batch_job.running_items at intervals; assert running_items ≤ 2 throughout.
        - Final state: status='completed', completed_items=6.

Task 11 — Wire frontend slider + cancel UX
MODIFY frontend (driven by the shadcn skill — invoke `Skill: shadcn-ui`):
  1. Add the slider primitive: `pnpm dlx shadcn@latest add slider` from frontend/.
  2. Verify file exists: frontend/src/components/ui/slider.tsx.
MODIFY frontend/src/types/api.ts:
  - FIND pattern: "export interface BatchSubmitResponse {"
  - INJECT after `cancelled_items: number`:
    effective_max_parallel?: number
MODIFY frontend/src/hooks/use-batches.ts:
  - APPEND a new hook useCancelBatch:
    export function useCancelBatch() {
      const queryClient = useQueryClient()
      return useMutation({
        mutationFn: (batchId: string) =>
          api<BatchSubmitResponse>(`/batch/${batchId}`, { method: 'DELETE' }),
        onSuccess: (data) => {
          queryClient.setQueryData(['batch', data.batch_id], data)
          void queryClient.invalidateQueries({ queryKey: ['batch'] })
        },
      })
    }
MODIFY frontend/src/pages/visualize/batch.tsx:
  - Submit form gains a max_parallel Slider (min=1, max=8 (default) capped by a future server-reported global, step=1, default=4).
  - Tooltip on the slider explains the runtime clamp ("Effective parallelism = min(this, server global cap)").
  - Progress card adds a `running_items` chip via the existing Badge primitive.
  - Add a "Cancel batch" Button that opens AlertDialog (mirror frontend/src/pages/explorer/job-detail.tsx:50 useCancelJob pattern).
  - The cancel button is disabled when `status ∈ {completed, failed, partial, cancelled}`.

Task 12 — Frontend tests
MODIFY frontend (tests live colocated next to source):
  - ADD frontend/src/hooks/use-batches.test.ts (mirror frontend/src/hooks/use-demo-pipeline.test.ts) — assert useCancelBatch issues a DELETE and invalidates the right cache keys.
  - SCOPE: don't add a full Playwright test — visual verification happens via the webapp-testing skill per .claude/rules/ui-design.md.

Task 13 — Validation gates
RUN locally (matches .github/workflows/ci.yml expectations):
  uv run ruff check . && uv run ruff format --check .
  uv run mypy app/ && uv run pyright app/
  uv run pytest -v -m "not integration" app/features/batch/
  docker compose up -d
  uv run alembic upgrade head            # MUST be a no-op (no new migration)
  uv run pytest -v -m integration app/features/batch/
  cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run
```

### Per-task pseudocode (high-information-density)

```python
# ---------------------------------------------------------------- Task 5: runner.py

# NOTE: lazy in-method cross-slice imports break the alembic cold-boot cycle —
# matches the forecasting/service.py:786-787 precedent.

from __future__ import annotations
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.database import get_session_maker
from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level registry — single-process scope (matches single-host vision).
# A future ADR would move this to Redis if multi-process arrives.
_ACTIVE_BATCHES: dict[str, "CancelHandle"] = {}


@dataclass
class CancelHandle:
    """Cancel signal + task refs for an in-flight batch. Created by run_batch,
    looked up by cancel_batch, removed in the run_batch finally."""
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    completed_event: asyncio.Event = field(default_factory=asyncio.Event)
    tasks: list[asyncio.Task[None]] = field(default_factory=list)


async def run_batch(
    batch_id: str,
    item_ids: list[str],                    # item_ids of pending children
    max_parallel: int,
    execute_item: Callable[[str], Awaitable[None]],  # one-arg coroutine: itemize, run, settle row
) -> int:
    """Execute one batch through a bounded TaskGroup. Returns effective_parallel.

    `execute_item` is the per-item closure (passed in from BatchService so the
    runner stays decoupled from JobService). It MUST open its own AsyncSession,
    write final per-row status, and emit lifecycle log events.
    """
    settings = get_settings()
    effective = min(max_parallel, settings.batch_global_max_parallel)
    sem = asyncio.Semaphore(effective)
    handle = CancelHandle()
    _ACTIVE_BATCHES[batch_id] = handle

    logger.info("batch.runner_start", batch_id=batch_id,
                total_items=len(item_ids), max_parallel=max_parallel,
                effective_max_parallel=effective)

    async def _child(item_id: str) -> None:
        # FAST-CANCEL BEFORE acquire — skips not-yet-started work cleanly.
        if handle.cancel_event.is_set():
            await _mark_cancelled_skipped(item_id)
            return
        async with sem:
            if handle.cancel_event.is_set():
                await _mark_cancelled_skipped(item_id)
                return
            await _bump_running(batch_id, +1)
            try:
                await execute_item(item_id)                  # may raise; OK
            except asyncio.CancelledError:
                # Cooperative drain — child observed cancel mid-run.
                await _mark_cancelled_running(item_id)
                raise                                        # let TaskGroup see it
            finally:
                await _bump_running(batch_id, -1)

    try:
        async with asyncio.TaskGroup() as tg:
            for iid in item_ids:
                t = tg.create_task(_child(iid), name=f"batch:{batch_id}:{iid}")
                handle.tasks.append(t)
    except* asyncio.CancelledError:
        # PEP 654 — caught the group of cancelled children. The runner's
        # parent-state settle is the caller's responsibility (BatchService._settle
        # already aggregates by status — works for cancelled the same way).
        pass
    finally:
        handle.completed_event.set()
        _ACTIVE_BATCHES.pop(batch_id, None)

    return effective


def cancel_batch(batch_id: str) -> bool:
    """Signal cancel for an in-flight batch. Returns False if not registered."""
    handle = _ACTIVE_BATCHES.get(batch_id)
    if handle is None:
        return False
    handle.cancel_event.set()
    for t in handle.tasks:
        if not t.done():
            t.cancel()
    logger.info("batch.cancel_requested", batch_id=batch_id, n_tasks=len(handle.tasks))
    return True


async def await_drain(batch_id: str, timeout_seconds: float) -> bool:
    """Block until the runner's completed_event fires or timeout elapses.

    Returns True on clean drain, False on timeout. Returns True immediately
    if the batch is no longer registered (race-free).
    """
    handle = _ACTIVE_BATCHES.get(batch_id)
    if handle is None:
        return True
    try:
        await asyncio.wait_for(handle.completed_event.wait(), timeout=timeout_seconds)
        return True
    except TimeoutError:
        return False


# Helpers _bump_running, _mark_cancelled_skipped, _mark_cancelled_running each
# open a fresh AsyncSession via get_session_maker() and commit a single UPDATE.
# They do NOT call BatchService — that would close a cycle. Implemented inline
# with raw SQLAlchemy update() statements scoped to the relevant batch_job/
# batch_job_item row.


# ---------------------------------------------------------------- Task 6: service.py rewire

# In BatchService.submit, after computing `triples` and inserting parent + N children:

# Build a one-arg closure that BatchService passes to the runner. The closure
# wraps the existing _execute_item logic so the lazy JobService import stays
# on the BatchService side (not the runner), preserving the runner's
# zero-cross-slice-import invariant.
async def _exec_one(item_id: str) -> None:
    async with session_maker() as session:
        item = (await session.execute(
            select(BatchJobItem).where(BatchJobItem.item_id == item_id)
        )).scalar_one()
        await self._execute_item(session, item)

effective = await runner.run_batch(
    batch_id=batch.batch_id,
    item_ids=[i.item_id for i in inserted_items],
    max_parallel=batch.max_parallel,
    execute_item=_exec_one,
)
batch.effective_max_parallel_runtime = effective   # ← if we make this a real attribute
# Alternatively (preferred): write effective into batch.result_summary['effective_max_parallel']
# and resolve it in the Pydantic .model_validate path so we don't need a column.


# ---------------------------------------------------------------- Task 7: DELETE route

@router.delete("/{batch_id}", response_model=BatchSubmitResponse, ...)
async def cancel_batch(batch_id: str, db: AsyncSession = Depends(get_db)) -> BatchSubmitResponse:
    settings = get_settings()
    service = BatchService()
    parent = await service.get(db, batch_id)
    if parent is None:
        raise NotFoundError(message=f"Batch not found: {batch_id}", details={"batch_id": batch_id})
    if parent.status in {BatchStatus.COMPLETED, BatchStatus.FAILED,
                          BatchStatus.PARTIAL, BatchStatus.CANCELLED}:
        raise ConflictError(message=f"Batch already terminal: {parent.status.value}",
                            details={"batch_id": batch_id, "status": parent.status.value})

    if not runner.cancel_batch(batch_id):
        # Race: settled between get() and cancel(). Treat as 409 (already done).
        raise ConflictError(message="Batch settled before cancel could fire",
                            details={"batch_id": batch_id})

    drained = await runner.await_drain(batch_id, settings.batch_cancel_drain_timeout_seconds)
    if not drained:
        raise GatewayTimeoutError(
            message=f"Drain exceeded {settings.batch_cancel_drain_timeout_seconds}s",
            details={"batch_id": batch_id})

    # Re-load post-settle parent and return.
    final = await service.get(db, batch_id)
    assert final is not None  # the parent row never deletes
    return final
```

### Integration Points

```yaml
CONFIG:
  - add to: app/core/config.py (Settings model)
  - pattern: "batch_global_max_parallel: int = Field(default=4, ge=1, le=64, ...)"
  - pattern: "batch_cancel_drain_timeout_seconds: int = Field(default=30, ge=1, le=600, ...)"
  - env file: .env.example gains BATCH_GLOBAL_MAX_PARALLEL=4 and BATCH_CANCEL_DRAIN_TIMEOUT_SECONDS=30

ERROR TAXONOMY:
  - add to: app/core/problem_details.py ERROR_TYPES dict
  - key: "GATEWAY_TIMEOUT" → "https://forecastlabai.dev/problems/gateway-timeout"
  - add to: app/core/exceptions.py
  - pattern: class GatewayTimeoutError(ForecastLabError): status_code=504, code="GATEWAY_TIMEOUT"

ROUTES:
  - add to: app/features/batch/routes.py
  - pattern: '@router.delete("/{batch_id}", response_model=BatchSubmitResponse)'
  - wiring: existing batch_router is already in app/main.py:142 — no main.py change.

FRONTEND TYPES:
  - add to: frontend/src/types/api.ts BatchSubmitResponse
  - field: effective_max_parallel?: number

FRONTEND HOOKS:
  - add to: frontend/src/hooks/use-batches.ts
  - export: useCancelBatch (mutation; on success: setQueryData + invalidateQueries)

FRONTEND UI (driven by shadcn skill — do not hand-write):
  - shadcn add: slider (creates frontend/src/components/ui/slider.tsx)
  - modify: frontend/src/pages/visualize/batch.tsx (slider on submit form, AlertDialog cancel on progress card)

NO DATABASE MIGRATION:
  - The three columns (max_parallel, running_items, cancelled_items) already
    exist per PRP-33's alembic/versions/c1d2e3f40512_create_batch_tables.py.
  - `uv run alembic upgrade head` MUST be a no-op after this PR merges.
  - `uv run alembic check` MUST detect no schema drift.

LOGGING:
  - new structlog events (request_id propagates via ContextVar inheritance):
    batch.runner_start, batch.runner_complete,
    batch.cancel_requested, batch.cancel_drained, batch.cancel_drain_timeout,
    batch.item_cancelled  (in addition to existing batch.item_started/completed/failed)
  - per .claude/rules/security-patterns.md: log IDs + counts, NEVER full payloads.
```

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run FIRST — fix any errors before proceeding.
uv run ruff check . --fix
uv run ruff format .
uv run mypy app/
uv run pyright app/
# Expected: zero errors. The strict-mode policy linter (test_strict_mode_policy.py)
# does NOT need changes — no new date/datetime/UUID/Decimal fields are added.
```

### Level 2: Unit Tests

```bash
uv run pytest -v -m "not integration" app/features/batch/

# Expected new pass list:
#  app/features/batch/tests/test_runner.py::test_semaphore_caps_concurrency PASSED
#  app/features/batch/tests/test_runner.py::test_settings_global_cap_clamps_max_parallel PASSED
#  app/features/batch/tests/test_runner.py::test_child_failure_does_not_abort_siblings PASSED
#  app/features/batch/tests/test_runner.py::test_cancel_pending_child_marks_cancelled_without_running PASSED
#  app/features/batch/tests/test_runner.py::test_cancel_running_child_propagates_cancellederror PASSED
#  app/features/batch/tests/test_routes_cancel.py::test_delete_404_unknown_batch PASSED
#  app/features/batch/tests/test_routes_cancel.py::test_delete_409_terminal_batch PASSED
#  app/features/batch/tests/test_routes_cancel.py::test_delete_504_drain_timeout PASSED
# Plus EVERY existing batch unit test still passes (test_metrics_jsonb_shape_pinned,
# test_picker_query_uses_skip_locked, test_expand_scope_manual_cartesian, ...).
```

### Level 3: Integration Tests

```bash
docker compose up -d
uv run alembic upgrade head           # must be a no-op — verify with:
uv run alembic check                  # expected: "No new upgrade operations detected."

uv run pytest -v -m integration app/features/batch/

# Expected new pass list:
#  test_runner.py::test_parent_status_progresses_as_children_complete PASSED
#  test_runner.py::test_db_connection_pool_not_exhausted PASSED
#  test_routes_cancel.py::test_delete_cancels_in_flight_children_against_real_db PASSED
#  test_runner_chaos.py::test_cancel_mid_flight_does_not_orphan_running_items PASSED
#  test_runner_chaos.py::test_cancel_during_db_commit_keeps_invariants PASSED
# Plus EVERY existing batch integration test still passes (test_submit_batch_happy_path,
# test_submit_batch_partial_failure, test_scope_over_cap_returns_422,
# test_get_items_sort_by_allow_list, test_get_batch_404,
# test_migration_partial_index_present, test_service_emits_lifecycle_events).
```

### Level 4: End-to-end smoke

```bash
# Start the backend + UI.
uv run uvicorn app.main:app --reload --port 8123 &
cd frontend && ./node_modules/.bin/vite --host 0.0.0.0 &

# Submit a small batch with max_parallel=3.
curl -s -X POST http://localhost:8123/batch/forecasting \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "backtest",
    "scope": {"kind": "manual", "store_ids": [1], "product_ids": [1,2,3]},
    "model_configs": [{"model_type": "naive"}],
    "start_date": "2024-01-01",
    "end_date": "2024-04-29",
    "max_parallel": 3
  }' | jq '{batch_id, status, total_items, completed_items, running_items, effective_max_parallel}'
# Expected: status="completed", completed_items=3, effective_max_parallel=3

# Test cancel against a longer-running batch — open a 20-item batch in one
# terminal, DELETE from another; expect 200 with status="cancelled".

# UI dogfood per .claude/rules/ui-design.md:
# Use the webapp-testing skill to drive /visualize/batch in a browser,
# move the slider, submit, watch running_items chip update, click cancel.
```

### Level 5: Frontend gates

```bash
cd frontend
pnpm tsc --noEmit                 # must be clean
pnpm lint                         # must be clean
pnpm test --run                   # vitest — must pass including new use-batches.test.ts
```

## Final Validation Checklist

- [ ] `grep -rn "asyncio.gather" app/features/batch/` returns no production-code line.
- [ ] `grep -rn "tg.cancel_scope" app/features/batch/` returns no match (the INITIAL's broken hint).
- [ ] `grep -rn "asyncio.all_tasks" app/features/batch/runner.py` returns no match (broken cancel mechanism).
- [ ] `grep -rn "from app.features.jobs" app/features/batch/runner.py` returns NO match (cross-slice imports stay lazy and in BatchService, not in the runner).
- [ ] `uv run alembic upgrade head` is a no-op after merge; `uv run alembic check` reports no drift.
- [ ] `Settings.batch_global_max_parallel` and `Settings.batch_cancel_drain_timeout_seconds` are documented in `.env.example`.
- [ ] `BatchSubmitResponse.effective_max_parallel` is non-zero on every freshly-submitted batch.
- [ ] `frontend/src/components/ui/slider.tsx` exists and was added via the shadcn MCP (not hand-written).
- [ ] `frontend/src/pages/visualize/batch.tsx` renders the slider + cancel button — verified visually via the webapp-testing skill.
- [ ] CHANGELOG.md gains a release-please-eligible `feat(batch):` entry (the merge commit subject drives the next pre-1.0 PATCH bump).
- [ ] No new dependency in `pyproject.toml` (single-host vision intact).
- [ ] All five validation-gate commands listed above pass locally.

---

## Anti-Patterns to Avoid

- ❌ `asyncio.gather(*tasks)` for fanning out child work. The point of this PRP is to make it impossible.
- ❌ `tg.cancel_scope.cancel()` — that attribute does not exist on stdlib `asyncio.TaskGroup`; it's an anyio API.
- ❌ Plain `except asyncio.CancelledError:` after `async with asyncio.TaskGroup():` — TaskGroup wraps in an ExceptionGroup; use `except*`.
- ❌ Iterating `asyncio.all_tasks()` to find children to cancel — keep Task refs in `CancelHandle.tasks`.
- ❌ Reusing the request's `AsyncSession` across children — open a fresh session per child via `get_session_maker()`.
- ❌ A new Alembic migration to add `max_parallel`/`running_items`/`cancelled_items` — they already exist (PRP-33).
- ❌ Hand-writing `slider.tsx` — drive it through `pnpm dlx shadcn@latest add slider` per `.claude/rules/shadcn-ui.md`.
- ❌ Importing a sibling slice's service at module scope inside `runner.py` — every cross-slice call stays lazy + in-method.
- ❌ Logging full request/response payloads in `batch.runner_*` events — IDs and counts only, per `.claude/rules/security-patterns.md`.
- ❌ Pushing parallelism above `batch_global_max_parallel + a few headroom slots` without also bumping `app/core/database.py:get_engine()` pool sizing — they go together.
- ❌ Adding a Celery / Redis / Arq queue — `product-vision.md` forbids it ("Not cloud-locked", "single-host deployable").
- ❌ A new "wipe everything" path on batches — `product-vision.md` § "Not a destructive tool".
- ❌ Adding an `AGENT_REQUIRE_APPROVAL` entry for batch cancellation — cancel is not a state-mutating agent tool here; the surface remains operator-driven over HTTP.

---

## Pre-flight

Before kicking off implementation:

1. Open a tracking issue with title `feat(batch): activate max_parallel + cooperative cancellation (PRP-34)` referencing `PRPs/INITIAL/INITIAL-batch-parallel-execution.md` and `PRPs/PRP-34-batch-parallel-execution.md`. Branch will be `feat/batch-parallel-execution` off `dev` (per `.claude/rules/branch-naming.md`).
2. Confirm the verified asyncio behaviour by running the snippets at the top of `PRPs/ai_docs/asyncio-taskgroup-cancellation.md` — if Python or SQLAlchemy has been upgraded since this PRP was written, refresh the doc's claims first.
3. Audit `git log -- app/features/batch/` since PR #281 — verify no subsequent PR moved any of the forward-compat columns or weakened the picker invariant.

---

## Confidence Score

**8 / 10** for one-pass implementation success.

The 2-point deduction:

- (-1) Concurrent integration tests against a single `docker-compose` Postgres can race on the seed-fixture rows; the chaos test in particular is sensitive to scheduler ordering. Likely 1-2 test iterations to stabilise polling timeouts and event-set checkpoints.
- (-1) The frontend Slider integration depends on a clean run of the shadcn MCP install pipeline from the executor's environment. If the MCP isn't authenticated or the registry is mismatched, the fallback is `pnpm dlx shadcn@latest add slider` which works but requires manual `components.json` checks.

The rest is bounded by the precedent in PRP-33 + the verified asyncio doc + the existing batch slice's test patterns.
