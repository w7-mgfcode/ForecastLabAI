# INITIAL-batch-parallel-execution.md — Parallel Execution Controls for the Portfolio Forecasting Batch Runner

**Status:** proposed
**Depends on:** `batch-runner-mvp` (parent `batch_job` + child `batch_job_item` + `POST /batch/forecasting` — **NEW**, not yet scaffolded)
**Source feature doc:** `docs/optional-features/06-portfolio-forecasting-batch-runner.md` § Full Version → "Parallel execution controls"
**Scope:** one Full-Version enhancement on top of the (unbuilt) batch-runner MVP — DB delta, backend service shape, API surface, frontend control, tests.

---

## Problem Statement

Today the `jobs` slice (`app/features/jobs/service.py:_execute_job`) executes one job per HTTP request, synchronously, inside the request task. A "batch" of forecasting work (train / backtest / predict across many `(store_id, product_id, model_type)` tuples) does not exist yet — the source feature doc proposes it as `batch_job` → many `batch_job_item` rows driven by `POST /batch/forecasting`.

Once the MVP lands, the next failure mode is obvious and severe: **the runner will be tempted to fan out N child items via a single `asyncio.gather(*tasks)`**. There is prior art for that pattern in this repo (`app/features/demo/pipeline.py:419`, `scripts/run_demo.py:604`), and it is fine at N=3 model types — but it is not safe at N=500 store-product pairs.

Quantified risk profile on the single-host vision target (developer laptop, `docker-compose` Postgres):

| Resource | Default ceiling on this host | What `gather` of N=500 children does |
|----------|------------------------------|--------------------------------------|
| asyncpg connection pool | SQLAlchemy `create_async_engine` default `pool_size=5`, `max_overflow=10` → ~15 concurrent sessions (`app/core/database.py:25`) | 500 children all open a session → `TimeoutError: QueuePool limit exceeded` on the 16th onward |
| Process memory | A single LightGBM / regression train holds the training frame + model bundle | 500 trains in flight ≈ memory blow-up; OOM-kill is the soft outcome |
| sklearn/LightGBM CPU usage | Each fit will use multiple cores unless capped | N concurrent fits with thread oversubscription thrash the scheduler |
| Postgres `max_connections` | Postgres 16 default 100 | Sustained breach destabilises the whole stack, including the dashboard |

**Pain if unsolved:** the MVP ships and the first 50-pair batch wedges the laptop, the demo, and the dashboard. The batch runner becomes unusable for the portfolio-scale operations the source doc was written to enable.

**Operator pain:** an operator that kicks off a batch needs (a) a knob to tune parallelism per batch and (b) a cancellation surface (`DELETE /batch/{batch_id}`) that actually stops in-flight children — not just flags them.

---

## Goals

- **Primary:** All batch child execution flows through a single **bounded concurrency primitive** — an `asyncio.Semaphore` sized by the smaller of `batch_job.max_parallel` and a global `Settings.batch_global_max_parallel`. Unbounded fan-out is not reachable from any code path.
- **Secondary:**
  - `batch_job` carries a `max_parallel` column persisted at create time (default `min(4, os.cpu_count() or 1)`); request schema validates `1 ≤ max_parallel ≤ Settings.batch_global_max_parallel`.
  - `DELETE /batch/{batch_id}` cancels in-flight children: signals the runner task group, awaits `CancelledError` propagation per child, then transitions still-`pending` items to `cancelled` and in-flight items to `cancelled` once the cooperating asyncio task observes the cancel.
  - Operators see live parent-status progression (`total_items` / `completed_items` / `failed_items` / `cancelled_items` / `running_items`) update as each semaphore slot frees.
  - structlog event per child start, per child finish (with `duration_ms`, `request_id` correlation), and per cancellation — `.claude/rules/security-patterns.md` § "Never log full prompts/responses" applies; we log IDs and metrics, not payloads.
- **Non-goals (out of scope, defer to follow-up INITIALs):**
  - MVP scaffolding itself — the `batch_job` / `batch_job_item` tables, the `POST /batch/forecasting` endpoint, the scope-expansion service. Those land in `INITIAL-batch-runner-mvp` (NEW). This plan **extends** that MVP migration with one column (`max_parallel`) rather than adding a second migration.
  - Retry of failed items (separate Full-Version item).
  - Priority queue (separate Full-Version item).
  - Champion selection per batch (separate Full-Version item).
  - **Celery / Redis / RabbitMQ / managed-cloud workers** — explicitly forbidden by `.claude/rules/product-vision.md` ("Not cloud-locked", "single-host deployable"). The plan stays in-process.
  - Multi-host scale-out, process pool across machines.
  - Cross-batch global queue / fairness scheduling — one batch at a time has its own semaphore; a second batch competes via the global cap, no cross-batch arbitration logic.

---

## Architectural Choice

**Recommended primitive: a single `asyncio.Semaphore(max_parallel)` inside an `asyncio.TaskGroup` owned by the runner coroutine.**

```python
# Conceptual sketch (NOT final code — placement / cancellation handling lives in
# the BatchRunnerService below).
sem = asyncio.Semaphore(effective_parallel)
async with asyncio.TaskGroup() as tg:
    for item in batch.items:
        tg.create_task(_run_one(item, sem))
```

Rationale (2-3 sentences as required by the prompt): `asyncio.Semaphore` is the standard-library primitive for "at most N concurrent async tasks", composes natively with `AsyncSession` (each child opens its own session inside the `acquire` block, freeing the connection on release), and needs zero new dependencies. `asyncio.TaskGroup` (Python 3.11+, available on 3.12 per `AGENTS.md`) gives structured concurrency — cancellation of the runner deterministically cancels every child task — which `asyncio.gather(..., return_exceptions=True)` does NOT cleanly provide. Together they satisfy the cancellation goal without a custom supervisor.

**Alternatives considered and rejected:**

| Alternative | Reject reason |
|-------------|---------------|
| `asyncio.gather(*tasks)` (current `app/features/demo/pipeline.py:419` pattern) | No bound on concurrency, no clean cancellation of in-flight children when the parent batch is deleted. Acceptable for N=3 model types; unacceptable for N=500 store-product pairs. |
| `concurrent.futures.ProcessPoolExecutor` | sklearn / LightGBM training is CPU-bound, so a process pool would actually parallelise it — but it forces a new IPC surface (parent ↔ workers), a new lifecycle (pool startup/teardown), and breaks the AsyncSession-per-request shape. Defer to a follow-up if profiling shows the GIL is the bottleneck. |
| Celery / Redis / Arq / RQ | Violates `.claude/rules/product-vision.md` (no managed-cloud SDK, no streaming broker, `docker-compose up` must remain the only prereq). Hard NO. |
| A FastAPI `BackgroundTasks` per item (per the source doc's "Documentation" link) | `BackgroundTasks` runs in the request's thread/loop after the response — it has no concurrency cap, no cancellation surface, and dies with the request. Not fit for purpose. |
| Custom `Queue` + N worker coroutines (the producer/consumer shape) | Equivalent semantics to `Semaphore + TaskGroup` but more code to maintain. Pick it only if scope expansion is itself slow (the source doc's scope-expansion service is fast — it's just a SQL filter — so the simpler primitive wins). |

---

## Data Model Delta

The MVP INITIAL will create the table; this INITIAL specifies the column it MUST include so the parallel-execution layer never needs a second migration to add it. Both the column and the MVP migration land together — this is not a follow-up migration (matches the source doc's "Full Version" framing).

**`batch_job` columns this feature touches (column-level deltas only, MVP owns the rest of the schema):**

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `max_parallel` | `Integer NOT NULL` | `4` (server-side default) | Per-batch concurrency cap. Bounded by `Settings.batch_global_max_parallel` at create-time validation. **NEW** — added by the MVP migration on the explicit instruction of this INITIAL. |
| `running_items` | `Integer NOT NULL DEFAULT 0` | `0` | Live count, incremented when a child task enters the semaphore-acquired body, decremented on exit. Lets the UI show "X of Y in flight" without a `COUNT(*) WHERE status='running'` poll. **NEW** — added by the MVP migration. |
| `cancelled_items` | `Integer NOT NULL DEFAULT 0` | `0` | Live count of items the operator cancelled. Mirrors `failed_items` / `completed_items` from the source doc § Data Model. **NEW** — MVP must include it (cancellation is a first-class lifecycle state in this plan). |
| (existing MVP) `status` | `String(20)` | `'pending'` | This INITIAL adds two transitions to the MVP state machine — see § API Delta. |

**Migration policy:** per `.claude/rules/security-patterns.md` ("Migrations are forward-only after merge") and `docs/_base/RULES.md`, the migration that ships the MVP table MUST already include these three columns. If the MVP migration lands without them, this INITIAL becomes infeasible without adding a forward-only migration; the MVP author MUST coordinate.

**No schema changes to `batch_job_item`** beyond what the MVP defines. Child cancellation is a status transition, not a schema change.

---

## API Delta

All requests/responses follow `.claude/rules/security-patterns.md` § "Pydantic v2 strict mode on FastAPI request bodies" — `ConfigDict(strict=True)` plus `Field(strict=False, ...)` on dates/UUIDs/Decimals. RFC 7807 errors via `app/core/problem_details.py` (NEW — same as every other slice).

### Request schema delta (MVP owns the rest)

```python
# app/features/batch/schemas.py  (NEW — created by MVP)
class BatchCreateRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    # ... MVP fields: operation, scope, model_configs ...

    max_parallel: int = Field(
        default=4,
        ge=1,
        le=64,  # hard ceiling; the runtime cap is min(this, settings.batch_global_max_parallel)
        description=(
            "Maximum concurrent child items in flight for this batch. "
            "Effective value at runtime is min(max_parallel, settings.batch_global_max_parallel)."
        ),
    )
```

A request with `max_parallel > settings.batch_global_max_parallel` is **accepted** (the runner clamps); the response echoes the clamped `effective_max_parallel` (see below) so the operator can see what actually applied. Rejecting would force operators to know a server-side value to send a valid request — bad UX.

### Response schema delta

```python
class BatchResponse(BaseModel):
    # ... MVP fields: batch_id, operation, status, total_items, completed_items, failed_items, ... ...

    max_parallel: int           # requested value, echoed
    effective_max_parallel: int # min(max_parallel, settings.batch_global_max_parallel) — NEW
    running_items: int          # live count — NEW
    cancelled_items: int        # live count — NEW
```

### Parent / child status transitions under parallelism

Parent state machine (extends what the MVP will define):

```
pending  →  running  →  completed       (all children completed)
                    →  partial          (≥1 child failed/cancelled, ≥1 succeeded)
                    →  failed           (every child failed; no successes)
                    →  cancelled        (operator hit DELETE; ≥1 child in-flight got CancelledError)
```

Child state machine (mirrors MVP's `batch_job_item.status`):

```
pending   →  running  →  completed
                     →  failed
          →  cancelled                  (operator cancel BEFORE the child entered the semaphore)
running   →  cancelled                  (operator cancel DURING execution, child observed CancelledError)
```

**Important invariant:** a `cancelled` parent does NOT imply every child is `cancelled`. Children that completed before the cancel signal stay `completed`. This matches `app/features/registry/models.py` `RunStatus` convention — terminal states are sticky.

### `DELETE /batch/{batch_id}` — cancellation contract

- 200: `BatchResponse` with parent `status='cancelled'` and per-child statuses settled.
- 404: unknown batch_id.
- 409: parent already in a terminal state (`completed`, `failed`, `partial`, `cancelled`) — nothing to cancel.

Cancellation flow (precise sequence, matches `asyncio.TaskGroup` semantics):

1. Resolve `batch_id` → in-memory runner handle (an `asyncio.Event` per active batch, registered when the runner starts).
2. Set the cancel event. The runner observes it on its next semaphore-release boundary AND propagates `tg.cancel_scope.cancel()` (or `task.cancel()` per task on Python without `cancel_scope`) to every in-flight child.
3. Each child child-task awaits a `try / finally`: `finally` writes the child's final status (`cancelled` if it observed `CancelledError`, `completed`/`failed` if it raced past).
4. The runner writes the parent's final status, then returns.
5. The endpoint awaits the runner's completion (with a bounded wait, default 30s — surface a 504-shaped problem-details body on overrun rather than orphaning state).

---

## Backend Service Shape

NEW slice: `app/features/batch/` per `.claude/rules/product-vision.md` § "Vertical slice architecture". Cross-slice calls into forecasting/backtesting/jobs go through the call-site lazy-import pattern documented in `docs/_base/ARCHITECTURE.md` § "Cross-slice read-only import pattern" (precedent: `app/features/forecasting/service.py` lazy imports of `RegistryService` / `JobService`).

### Module layout (additive to MVP)

```
app/features/batch/
├── models.py           # batch_job, batch_job_item (NEW — owned by MVP)
├── schemas.py          # BatchCreateRequest / BatchResponse (NEW — owned by MVP)
├── service.py          # BatchRunnerService (NEW — this INITIAL fills in the runner)
├── runner.py           # NEW — semaphore + TaskGroup + registry of active batches
├── routes.py           # POST /batch/forecasting, GET /batch/{id}, DELETE /batch/{id} (NEW — MVP)
└── tests/
    ├── conftest.py
    ├── test_runner.py          # NEW (this INITIAL)
    ├── test_routes_cancel.py   # NEW (this INITIAL)
    └── test_runner_chaos.py    # NEW (this INITIAL)
```

### `runner.py` — pseudocode

```python
# NEW — illustrative, not final.
# All actual code lands in the PRP-derived implementation.

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from app.core.config import get_settings
from app.core.database import get_session_maker
from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level registry: batch_id -> CancelHandle. Lets DELETE /batch/{id}
# signal an in-flight runner. Wiped when the runner returns. Single-process
# only — matches the single-host vision; no Redis / cross-host registry.
_ACTIVE_BATCHES: dict[str, "CancelHandle"] = {}


class CancelHandle:
    def __init__(self) -> None:
        self.cancel_event = asyncio.Event()
        self.task_group_ref: asyncio.TaskGroup | None = None


async def run_batch(
    batch_id: str,
    items: list["BatchItemSpec"],   # MVP-owned spec
    max_parallel: int,
    run_one: Callable[["BatchItemSpec"], Awaitable[None]],
) -> None:
    settings = get_settings()
    effective_parallel = min(max_parallel, settings.batch_global_max_parallel)
    sem = asyncio.Semaphore(effective_parallel)
    handle = CancelHandle()
    _ACTIVE_BATCHES[batch_id] = handle

    logger.info(
        "batch.runner_start",
        batch_id=batch_id,
        total_items=len(items),
        max_parallel=max_parallel,
        effective_max_parallel=effective_parallel,
    )

    async def _child(item: "BatchItemSpec") -> None:
        # Fast-cancel BEFORE acquiring the slot: keeps work that hasn't started
        # from ever opening a DB session.
        if handle.cancel_event.is_set():
            await _mark_child_cancelled(item)
            return

        async with sem:
            if handle.cancel_event.is_set():
                await _mark_child_cancelled(item)
                return
            try:
                await _increment_running(item.batch_id)
                await run_one(item)             # opens its own AsyncSession
            except asyncio.CancelledError:
                await _mark_child_cancelled(item)
                raise                            # propagate so TaskGroup sees it
            except Exception as exc:             # noqa: BLE001 — runner is a boundary
                await _mark_child_failed(item, exc)
            else:
                await _mark_child_completed(item)
            finally:
                await _decrement_running(item.batch_id)

    try:
        async with asyncio.TaskGroup() as tg:
            handle.task_group_ref = tg
            for item in items:
                tg.create_task(_child(item))
    except* asyncio.CancelledError:
        # Operator cancelled — final parent status set below.
        pass
    finally:
        _ACTIVE_BATCHES.pop(batch_id, None)
        await _settle_parent_status(batch_id, cancelled=handle.cancel_event.is_set())


async def cancel_batch(batch_id: str) -> bool:
    handle = _ACTIVE_BATCHES.get(batch_id)
    if handle is None:
        return False
    handle.cancel_event.set()
    if handle.task_group_ref is not None:
        # Best-effort task cancellation; the TaskGroup will await CancelledError.
        for task in list(asyncio.all_tasks()):
            if task.get_name().startswith(f"batch:{batch_id}:"):
                task.cancel()
    return True
```

Key invariants the implementation MUST preserve:

- **Every child opens its own `AsyncSession`** via `get_session_maker()` — never share the parent runner's session. This is the only way `pool_size=5, max_overflow=10` (default) survives `max_parallel > 1`.
- **Semaphore wraps the work, not the task creation**: `tg.create_task(_child(item))` is unbounded in scheduling cost (cheap), but `_child` itself acquires the semaphore before doing any heavy work.
- **Cancellation is cooperative**: sklearn/LightGBM fit calls are sync and don't observe `CancelledError` mid-fit. That is acceptable — the runner cancels what hasn't started and lets in-flight fits finish; the operator sees `running_items` drain to zero, then the parent settles. Document this in the route docstring.
- **No `time.sleep`** anywhere in `_child` (would block the loop and starve siblings). Anything sleep-shaped uses `asyncio.sleep`.

---

## Settings Additions

Append to `app/core/config.py:Settings` (single block, near the existing `# Jobs` section):

```python
# Batch Runner Configuration
batch_global_max_parallel: int = Field(
    default=4,
    ge=1,
    le=64,
    description=(
        "Hard upper bound on concurrent in-flight batch_job_item executions across "
        "all active batches on this host. Sized for the docker-compose Postgres "
        "pool (pool_size=5, max_overflow=10). Override via BATCH_GLOBAL_MAX_PARALLEL."
    ),
)
batch_cancel_drain_timeout_seconds: int = Field(
    default=30,
    ge=1,
    le=600,
    description="Max time DELETE /batch/{id} waits for in-flight children to settle before returning 504.",
)
```

**Default rationale:** `4` is the largest value that keeps the SQLAlchemy connection pool comfortably above its high-water mark in steady state (`pool_size=5` + per-child session checkout) on the default docker-compose Postgres, AND matches a reasonable `os.cpu_count()` floor on a typical developer laptop. The ceiling `64` exists so a user with a beefier host can opt in without code change.

**Env-var override:** `BATCH_GLOBAL_MAX_PARALLEL=8 uvicorn ...` — must land in `.env.example` per `.claude/rules/security-patterns.md` § "Secrets handling" (the two-file model applies to all env vars, not just secrets).

**Validation:** field-level `ge=1, le=64`. Settings is read once per process (`@lru_cache` on `get_settings()` — `app/core/config.py:209`); changing the env var requires a uvicorn restart, matching every other tunable in this Settings model.

---

## Frontend Touchpoints

Per `.claude/rules/ui-design.md` and `.claude/rules/shadcn-ui.md`: drive UI work through the `shadcn` skill + `mcp__shadcn__*` MCP tools. No hand-rolled components.

### Pages

1. **`frontend/src/pages/ops.tsx`** (exists) — add a "Batch run" card panel that includes:
   - Scope picker (owned by MVP).
   - Operation picker (owned by MVP).
   - **`max_parallel` control** — a shadcn `Slider` (`@/components/ui/slider`, **NEW component** to be added via `pnpm dlx shadcn@latest add slider` from `frontend/` per `.claude/rules/shadcn-ui.md`). Min `1`, max `min(64, server-reported global cap)`, step `1`, default `4`. Disable + show a helper-text caption if the user is offline from the backend (TanStack Query failure).
   - A `Tooltip` (`@/components/ui/tooltip`, already installed per `frontend/src/components/ui/tooltip.tsx`) explaining the runtime clamp.

2. **`frontend/src/pages/visualize/batch.tsx`** (**NEW**, conventional position next to `demand.tsx` / `planner.tsx` / `forecast.tsx` / `backtest.tsx`) — the per-batch progress / drilldown page:
   - Header card with `total / completed / failed / cancelled / running` (uses shadcn `Card` + shadcn `Progress`, both already installed).
   - "Cancel batch" `Button` (shadcn) that surfaces an `AlertDialog` (already installed) confirmation, then hits `DELETE /batch/{batch_id}`.
   - Items `Table` (shadcn `Table` + TanStack Table) for the children — same shape as existing `frontend/src/pages/ops.tsx` job list.
   - Live updates via TanStack Query polling at 2s while parent `status ∈ {pending, running}`; stop polling once terminal (mirrors existing job-detail polling in `frontend/src/pages/explorer/job-detail.tsx`).

### Reuse / no new primitives

- Status badges → existing `frontend/src/components/ui/badge.tsx`.
- Form layout / labels → existing pattern in `frontend/src/pages/ops.tsx`.
- Toast on cancel success/failure → existing `sonner` toast already wired (`frontend/src/components/ui/sonner.tsx`).

### Type-safety gate

The `src/types/api.ts` augmentation for `BatchResponse.max_parallel` / `effective_max_parallel` / `running_items` / `cancelled_items` MUST keep `pnpm tsc --noEmit` green (per `.claude/rules/test-requirements.md`).

---

## Test Plan

Per `.claude/rules/test-requirements.md`: every NEW module gets a matching `tests/` file; every public function gets a happy-path test; the bug class "unbounded parallelism" gets a regression test that would have caught it.

### Unit tests (`-m "not integration"`) — no DB

| Test | What it asserts |
|------|-----------------|
| `test_runner.py::test_semaphore_caps_concurrency` | With `max_parallel=2` and 5 fake child coroutines that each `asyncio.sleep(0.05)` while bumping a shared counter, the observed concurrent peak is exactly 2. **This is the regression test for the runaway-parallelism risk.** |
| `test_runner.py::test_settings_global_cap_clamps_max_parallel` | A request with `max_parallel=32` and `settings.batch_global_max_parallel=4` runs with effective parallelism 4 (counter peak ≤ 4). |
| `test_runner.py::test_child_failure_does_not_abort_siblings` | One of 5 children raises; the other 4 still reach `completed`; parent ends `partial`. |
| `test_runner.py::test_cancel_pending_child_marks_cancelled_without_running` | A child cancelled before semaphore acquire transitions `pending → cancelled` and never opens a session. |
| `test_runner.py::test_cancel_running_child_propagates_cancellederror` | A child blocked on `asyncio.sleep` receives `CancelledError`, writes `cancelled` in `finally`. |
| `test_routes_cancel.py::test_delete_404_unknown_batch` | RFC 7807 404. |
| `test_routes_cancel.py::test_delete_409_terminal_batch` | RFC 7807 409 on already-`completed` batch. |
| `test_routes_cancel.py::test_delete_504_drain_timeout` | When `batch_cancel_drain_timeout_seconds=0` and a fake child sleeps past it, the endpoint returns RFC 7807 504. |

External calls (forecasting/backtesting services) are mocked per `.claude/rules/test-requirements.md` § "Mock external services (OpenAI, Anthropic, Ollama) in unit tests" — applied here to in-repo service boundaries the runner orchestrates.

### Integration tests (`-m integration`) — real Postgres via `docker-compose`

| Test | What it asserts |
|------|-----------------|
| `test_runner.py::test_parent_status_progresses_as_children_complete` | A batch of 6 real (fast / mocked-model) children with `max_parallel=2` shows `running_items` ≤ 2 throughout, `completed_items` monotonically increases, parent ends `completed`. |
| `test_runner.py::test_db_connection_pool_not_exhausted` | A batch with `max_parallel=settings.batch_global_max_parallel` runs to completion without raising `sqlalchemy.exc.TimeoutError` (the QueuePool exhaustion symptom). |
| `test_routes_cancel.py::test_delete_cancels_in_flight_children_against_real_db` | An operator cancel mid-run produces a parent in `cancelled`, ≥1 child in `cancelled`, and any already-`completed` children stay `completed`. |

### "Chaos" tests (still `-m integration`, marked clearly)

| Test | What it asserts |
|------|-----------------|
| `test_runner_chaos.py::test_cancel_mid_flight_does_not_orphan_running_items` | After cancel + drain, `SELECT COUNT(*) FROM batch_job_item WHERE status='running' AND batch_id=...` returns 0. No half-state rows. |
| `test_runner_chaos.py::test_cancel_during_db_commit_keeps_invariants` | A child whose final-status commit is cancelled mid-flight either (a) commits cleanly OR (b) leaves the row in `running` AND the runner's `_settle_parent_status` reconciles to `cancelled`. Either is acceptable; neither leaves the parent inconsistent with the sum of its children. |

### Validation gate run

Mirror `CLAUDE.md` § Verification — these MUST pass locally before commit:

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
uv run pytest -v -m "not integration"
docker compose up -d && uv run pytest -v -m integration
cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run
```

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| **Runaway parallelism wedges the host** (the headline risk) | HIGH if no cap | CATASTROPHIC (host OOM, dashboard down) | `Semaphore(min(per_batch, global))` is the ONLY path to execution; no `gather` of children; field-level `le=64`; integration test `test_db_connection_pool_not_exhausted` is the regression. |
| **DB connection-pool exhaustion at `max_parallel > 10`** | MEDIUM (pool default 5+10) | HIGH (cascading 500s system-wide) | Default `batch_global_max_parallel=4`; the migration that ships the column also bumps `pool_size`/`max_overflow` if needed (deferred — start conservative). The integration test catches regressions. |
| **Cancelled-but-still-running children orphan DB state** | MEDIUM | MEDIUM | Each `_child` writes its final status in a `finally` block. The chaos test `test_cancel_mid_flight_does_not_orphan_running_items` is the regression. |
| **sklearn / LightGBM fit ignores `CancelledError`** | HIGH (sync C extension call) | LOW (just slower drain) | Document in the route docstring + tooltip: "Cancel stops what hasn't started; in-flight fits finish." The `batch_cancel_drain_timeout_seconds` cap + 504 surface is the escape hatch. |
| **Operator sets `max_parallel=64` on a 4-core laptop and the system thrashes** | MEDIUM | HIGH | The global cap is the safety net; the per-batch value clamps. Frontend slider visually caps at the server-reported global. |
| **Two batches submitted back-to-back each take `global_max_parallel` slots → 2× concurrency in the same pool** | LOW (operator behaviour) | HIGH | Phase 2 follow-up: a process-wide `Semaphore(batch_global_max_parallel)` shared across batches (`runner.py:_GLOBAL_SEMAPHORE`). Marked as an open question below — the simple per-batch cap is the first cut. |
| **Module-level `_ACTIVE_BATCHES` dict is process-local** | LOW (single-host vision) | LOW | Acceptable — `.claude/rules/product-vision.md` § "Not multi-tenant SaaS" rules out clustering. Document the assumption; if a future ADR moves to multi-process, this becomes a Redis / DB-row registry. |
| **`asyncio.TaskGroup` semantics on Python 3.11 vs 3.12** | LOW (3.12 pinned per `AGENTS.md`) | LOW | The `pyproject.toml` Python pin enforces it; reject any PR that loosens `requires-python`. |

---

## Open Questions (for the PRP author)

1. **Process-wide global semaphore vs per-batch only?** Should a second `Semaphore(batch_global_max_parallel)` sit outside any batch so two concurrent batches still respect a single host-wide ceiling? The plan above includes ONLY the per-batch cap as the simple first cut; the global Settings value caps the per-batch value at create time but does NOT enforce host-wide concurrency across simultaneous batches. Recommend: ship the per-batch cap in v1, add the process-wide semaphore in a follow-up only if multi-batch overlap shows up in practice.
2. **Should the SQLAlchemy engine's `pool_size` / `max_overflow` be bumped in `app/core/database.py:get_engine()` as part of this work?** Not strictly required if `batch_global_max_parallel ≤ pool_size + max_overflow = 15`, but a comment near the engine creation would defend the invariant.
3. **WebSocket vs polling for the parent-progress UI?** The dashboard uses polling for `frontend/src/pages/explorer/job-detail.tsx` and a WebSocket for `/agents/stream` and `/demo/stream`. The simpler choice for v1 is TanStack Query polling at 2s; a follow-up `WS /batch/{id}/stream` mirroring `/demo/stream` (`app/features/demo/routes.py`) is a low-cost iteration.
4. **How does the runner survive a uvicorn restart mid-batch?** Out of scope here — the source doc's "Failed child jobs need resumability" risk row maps to a separate Full-Version item ("Retry failed items"). For v1, in-flight items become `failed` on next boot (a startup-reconcile sweep marks them). Documented for the MVP author.
5. **Should `batch_cancel_drain_timeout_seconds` be per-batch?** v1 keeps it global. If a long-running backtest batch routinely overruns the global default, the PRP can promote it to a per-batch `cancel_drain_timeout_seconds` column.
6. **CPU pinning / `joblib.parallel_backend('threading', n_jobs=1)` inside child training to prevent thread oversubscription?** Not enforced here — defer to the model-training service. Flag for the PRP if profiling shows GIL contention.

---

## References

Files this plan relies on (paths inside this repo). Items marked **NEW** do not exist today and are created by either the MVP INITIAL or this one.

- `docs/optional-features/06-portfolio-forecasting-batch-runner.md` — source feature doc; this INITIAL implements one row of its § Full Version table.
- `app/features/jobs/models.py` — `Job` / `JobStatus` / `VALID_JOB_TRANSITIONS`; the child-item state machine borrows the shape.
- `app/features/jobs/service.py` — current synchronous executor pattern this plan moves past; `_execute_job` is the per-item analogue of `_child`.
- `app/features/jobs/schemas.py` — `JobCreate` / `JobResponse` strict-mode example.
- `app/features/jobs/routes.py` — endpoint shape, 202-Accepted convention, error contract.
- `app/features/demo/pipeline.py:419` — existing `asyncio.gather` pattern (current ceiling: 3 model types); the unbounded-fan-out anti-pattern this INITIAL displaces for batch runs.
- `scripts/run_demo.py:604` — same anti-pattern, scripted side.
- `app/core/config.py:62` — `Settings` model; `batch_global_max_parallel` / `batch_cancel_drain_timeout_seconds` are added here.
- `app/core/config.py:209` — `@lru_cache` on `get_settings()` — config is read once per process.
- `app/core/database.py:25` — `create_async_engine`; pool sizing is the load-bearing default behind the parallelism math.
- `app/core/problem_details.py` — RFC 7807 envelope all new endpoints use (referenced by `docs/_base/SECURITY.md` and `.claude/rules/security-patterns.md`).
- `app/core/logging.py` — structlog instance used for all `batch.runner_*` events.
- `app/features/forecasting/service.py` — lazy-import precedent the runner reuses to call into forecasting/backtesting without closing an import cycle.
- `app/features/registry/models.py` — `RunStatus` terminal-state convention (`completed`/`failed`/`cancelled` are sticky) — the runner mirrors it.
- `frontend/src/pages/ops.tsx` — existing scope of "ForecastOps" page; the batch-create form lives here.
- `frontend/src/pages/explorer/job-detail.tsx` — polling pattern reused for batch-progress polling.
- `frontend/src/components/ui/tooltip.tsx`, `frontend/src/components/ui/progress.tsx`, `frontend/src/components/ui/card.tsx`, `frontend/src/components/ui/badge.tsx`, `frontend/src/components/ui/alert-dialog.tsx`, `frontend/src/components/ui/table.tsx`, `frontend/src/components/ui/button.tsx`, `frontend/src/components/ui/sonner.tsx` — existing shadcn primitives reused.
- `frontend/src/components/ui/slider.tsx` — **NEW** shadcn component, added via `pnpm dlx shadcn@latest add slider` from `frontend/` per `.claude/rules/shadcn-ui.md`.
- `frontend/src/pages/visualize/batch.tsx` — **NEW** page for per-batch progress / cancel.
- `app/features/batch/` — **NEW** slice (its skeleton is owned by `INITIAL-batch-runner-mvp`; this INITIAL adds `runner.py`, the `max_parallel` / `running_items` / `cancelled_items` columns, the `DELETE` cancel semantics, and the tests above).
- `app/features/batch/runner.py` — **NEW** module (created by this INITIAL).
- `app/features/batch/tests/test_runner.py`, `tests/test_routes_cancel.py`, `tests/test_runner_chaos.py` — **NEW** test files.
- `alembic/versions/<batch-mvp-revision>_create_batch_job.py` — **NEW** migration (owned by MVP, but ships the three columns this INITIAL requires; not a follow-up migration).
- `.env.example` — **MUST** gain `BATCH_GLOBAL_MAX_PARALLEL=4` and `BATCH_CANCEL_DRAIN_TIMEOUT_SECONDS=30` placeholders (`.claude/rules/security-patterns.md` § "two-file model is mandatory").
- `docs/_base/API_CONTRACTS.md`, `docs/_base/ARCHITECTURE.md`, `docs/_base/RULES.md`, `docs/_base/SECURITY.md`, `docs/_base/DOMAIN_MODEL.md` — touched by the PRP to register the new slice + endpoint surface + invariants.
- `.claude/rules/product-vision.md`, `.claude/rules/security-patterns.md`, `.claude/rules/test-requirements.md`, `.claude/rules/ui-design.md`, `.claude/rules/shadcn-ui.md`, `.claude/rules/commit-format.md` — authoritative on the rules this plan obeys.

---

## Acceptance Summary

A reviewer looking at the merged PRP-output for this INITIAL should be able to confirm, in order:

1. The MVP migration shipped `max_parallel`, `running_items`, and `cancelled_items` on `batch_job` (forward-only, no follow-up migration).
2. `app/features/batch/runner.py` exists and is the ONLY path that executes children — `grep -rn "asyncio.gather" app/features/batch/` returns no production-code match.
3. `Settings.batch_global_max_parallel` defaults to `4`; `.env.example` includes the override placeholder.
4. `POST /batch/forecasting` accepts `max_parallel`; the response echoes `effective_max_parallel`.
5. `DELETE /batch/{batch_id}` cancels in-flight children; the parent settles to `cancelled` or `partial` per the state machine above.
6. The five "what asserts this" rows in § Test Plan are realised as passing tests.
7. The frontend slider on `ops.tsx` clamps to the server-reported global cap; the batch-progress page polls and renders `running_items` / `completed_items` / `failed_items` / `cancelled_items` live.
8. All five validation-gate commands in § Test Plan pass on a fresh laptop.
