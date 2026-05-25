# asyncio.TaskGroup + Semaphore + Cooperative Cancellation (Python 3.12)

> Captured for PRP-34. Verified against Python 3.12.13 (the project's pinned
> interpreter, per `pyproject.toml requires-python = ">=3.12"`).

## What the stdlib actually offers

`asyncio.TaskGroup` is the Python 3.11+ structured-concurrency primitive
([docs](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.TaskGroup)).
The **only** public surface is `create_task(coro, *, name=None, context=None)`.
There is no `cancel_scope`, no `cancel()`, no `tasks` property — verified:

```bash
uv run python -c "import asyncio; print([m for m in dir(asyncio.TaskGroup) if not m.startswith('_')])"
# → ['create_task']
```

The INITIAL's pseudocode calls `tg.cancel_scope.cancel()`. **That attribute does
not exist** — that's anyio API, not stdlib asyncio. Don't import anyio for
this; instead, retain the tasks `create_task` returns and cancel them.

## How to cancel TaskGroup-managed children

Three mutually compatible mechanisms work on stdlib `TaskGroup`:

1. **Per-task cancel.** `tg.create_task(coro)` returns a `Task`; keep a list
   and call `task.cancel()` on each. The TaskGroup awaits the `CancelledError`s
   and re-raises them inside an `ExceptionGroup`, caught with `except*`.

2. **Raise inside the `async with`.** Any exception raised from the body of
   `async with asyncio.TaskGroup() as tg:` cancels all currently running
   children, then re-raises as an `ExceptionGroup`. Use this when the
   *runner itself* needs to abort (e.g., total drain timeout).

3. **Cooperative event check.** Each child polls an `asyncio.Event` at safe
   yield points (before semaphore acquire, after acquire, in a `finally`
   block) and returns early. Use this to skip work that hasn't started.

Combine #1 (cancel running children) + #3 (skip not-yet-started children).
Verified working pattern:

```python
import asyncio

async def child(i: int, sem: asyncio.Semaphore, cancel: asyncio.Event) -> None:
    if cancel.is_set():
        return                                  # fast-skip BEFORE semaphore
    async with sem:
        if cancel.is_set():
            return                              # fast-skip AFTER semaphore
        try:
            await asyncio.sleep(10)             # the actual work
        except asyncio.CancelledError:
            # finalise child state here (write 'cancelled' to DB), then re-raise
            raise

async def main() -> None:
    sem = asyncio.Semaphore(2)
    cancel = asyncio.Event()
    try:
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(child(i, sem, cancel), name=f"batch:b1:item{i}")
                for i in range(4)
            ]
            await asyncio.sleep(0.05)
            cancel.set()
            for t in tasks:
                t.cancel()
    except* asyncio.CancelledError:             # PEP 654 except*
        pass                                    # observed — drain complete
```

**Verification command** (re-runnable on library upgrade):

```bash
uv run python -c "
import asyncio
async def child(i, sem, cancel):
    if cancel.is_set(): return
    async with sem:
        if cancel.is_set(): return
        try: await asyncio.sleep(10)
        except asyncio.CancelledError:
            print(f'child {i} cancelled cleanly'); raise
async def main():
    sem, cancel = asyncio.Semaphore(2), asyncio.Event()
    try:
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(child(i, sem, cancel), name=f'item{i}') for i in range(4)]
            await asyncio.sleep(0.05)
            cancel.set()
            for t in tasks: t.cancel()
    except* asyncio.CancelledError: print('drained')
asyncio.run(main())
"
# → 'child 0 cancelled cleanly', 'child 1 cancelled cleanly', 'drained'
# Children 2 & 3 never acquired the semaphore so they never printed.
```

## Why NOT `asyncio.all_tasks()` + name-prefix scan

The INITIAL's `cancel_batch` sketch iterates `asyncio.all_tasks()` and matches
on `task.get_name().startswith(f"batch:{batch_id}:")`. This is brittle:

- `get_name()` defaults to `Task-N` when `name=` is not passed; any
  refactor that drops `name=` silently breaks the cancel path.
- It scans the entire event loop's task set, which on a uvicorn process
  includes other request handlers, WebSocket pumps, and background tasks.
- Two concurrent batches with name collisions would cancel each other.

**Correct pattern:** store the `Task` references in the `CancelHandle` when
they're created, cancel via that list. Never reach into `asyncio.all_tasks()`.

## Semaphore composition with AsyncSession

`asyncio.Semaphore` is a context manager — `async with sem:` acquires on
entry, releases on exit (including the exception path). The Semaphore must
wrap the **work** (everything that opens a DB session and runs the model),
not the `tg.create_task(...)` call:

```python
# WRONG — semaphore around scheduling, not work. Defeats the cap.
async with sem:
    tg.create_task(child())

# RIGHT — child acquires the semaphore inside its own body.
async def child():
    async with sem:
        async with session_maker() as session:
            await do_work(session)

for item in items:
    tg.create_task(child())
```

Each child opens its OWN `AsyncSession` via `get_session_maker()` inside the
semaphore-acquired block — never shares the runner's session. This is the
only way the SQLAlchemy connection pool survives `max_parallel > 1`.

## ContextVar inheritance into TaskGroup children

The project binds the per-request `X-Request-ID` to a `ContextVar`
(`app/core/logging.py:13` — `request_id_ctx: ContextVar[str | None]`). This
is consumed by structlog via the `add_request_id` processor.

**`asyncio.Task` created with `create_task()` inherits the current
`contextvars.Context`** (CPython implementation detail since 3.7; documented
behaviour). That means every `batch.item_*` log line emitted from a TaskGroup
child gets the same `request_id` as the parent `POST /batch/forecasting`
request automatically. No explicit `structlog.contextvars.bind_contextvars`
plumbing needed inside the runner.

Verification:

```bash
uv run python -c "
import asyncio, contextvars
v = contextvars.ContextVar('v', default=None)
async def child(): print('child sees:', v.get())
async def main():
    v.set('outer')
    async with asyncio.TaskGroup() as tg:
        tg.create_task(child())
asyncio.run(main())
"
# → child sees: outer
```

## SQLAlchemy async pool defaults that bound the design

```bash
uv run python -c "
from sqlalchemy.ext.asyncio import create_async_engine
e = create_async_engine('postgresql+asyncpg://x:x@h:5433/x')
print('size:', e.pool.size(), 'overflow:', e.pool._max_overflow, 'timeout:', e.pool._timeout)
"
# → size: 5  overflow: 10  timeout: 30.0
```

So the upper bound on parallel children that won't trigger
`sqlalchemy.exc.TimeoutError` (the QueuePool exhaustion symptom) is
`pool_size + max_overflow - reserved_for_other_requests`. With one
in-flight `POST /batch/forecasting` request (1 session) + one `cancel`
endpoint (potentially 1 session) + the runner's settle-parent session (1),
`batch_global_max_parallel ≤ 12` is the safe headroom. The PRP's
`Settings.batch_global_max_parallel = 4` default is well inside this.

If a future iteration raises the global cap above 12, bump the engine's
`pool_size`/`max_overflow` in `app/core/database.py:get_engine()` in the
same PR — these go together.

## sklearn / LightGBM ignore CancelledError mid-fit

The model-training call inside `JobService.create_job` lands in a sync C
extension (`sklearn.ensemble`/`lightgbm.Booster.update`). `asyncio` cannot
preempt sync C code. Cancellation semantics:

- **Pending children** (haven't reached `sem.acquire()`): observe the
  cancel event, transition to `cancelled`, no work executed.
- **In-flight children** (mid-fit): the cancel signal is **deferred** until
  the C call returns. The `try/finally` block then writes `cancelled` if
  the task observed `CancelledError`, or `completed`/`failed` if the work
  finished first. **Either is acceptable** — the parent's status reflects
  the actual per-child outcomes; the invariant is "no row left in
  `running` state after settle".

This is why the PRP needs `Settings.batch_cancel_drain_timeout_seconds`
(default 30s) and a 504 surface — an in-flight fit can stall the drain.
