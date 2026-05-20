# INITIAL-batch-export-and-retry.md — Batch Result Export + Failed-Item Retry

```yaml
status: proposed
depends_on: batch-runner-mvp
slice: batch (NEW — `app/features/batch/`)
estimated_size: small-to-medium (one slice extension + one frontend page extension)
```

## FEATURE

Ship two coordinated enhancements on top of the (not-yet-built) `batch` MVP:

1. **Exportable results** — operator downloads the full result table of a finished
   batch as a CSV from the batch-detail page.
2. **Retry failed items** — operator re-runs the failed children of a batch,
   either one row at a time or all failed at once, without disturbing successful
   children or the registry artifacts they already produced.

They are planned together because they share:

- the same result-table on the batch-detail page (the only place this UX exists),
- the same `batch_job_item` row shape,
- the same triage workflow — finish a batch, inspect the failures, retry the
  ones that look fixable, export the rest for offline review.

## PROBLEM STATEMENT

After the `batch` MVP lands, an operator who runs a 200-item portfolio backtest
and ends up with 14 failures has no way to:

- get the result table out of the browser for sharing or offline triage,
- selectively retry a subset of failed items without re-running the whole batch
  (which would re-do 186 already-successful items and pollute the registry with
  duplicate runs).

These two gaps are blocking the batch slice from being usable for portfolio work
even though the MVP itself ships. Both are additive, both reuse existing
primitives, both score +16 in the gap analysis (E=1+2, V=3+4, F=5+5, R=1+2) and
they share the same surface — there is no reason to split them across two PRPs.

## OUT OF SCOPE

- The MVP itself (parent `batch_job`, child `batch_job_item`, `POST /batch/forecasting`)
  — that is `INITIAL-batch-runner-mvp.md` (NEW; pre-requisite, not this doc).
- Parallel execution controls, priority queue, batch-level champion selection,
  portfolio heatmaps — separate Full-Version enhancements.
- Server-side asynchronous task queue (Celery / RQ / arq). Job execution remains
  the synchronous-with-async-shaped-API pattern from `app/features/jobs/service.py`.
- Background scheduled re-runs of failed items. Retry is operator-triggered only.

---

## ITEM 1 — Exportable results

### User story

> As an operator who just finished a 200-item batch backtest, I want one click to
> download the full result table as a CSV so I can paste it into a spreadsheet,
> share it with a teammate, or feed it into a notebook for follow-up analysis.

### Recommendation: client-side CSV (reuse `csv-export.ts`)

The repo already has a battle-tested client-side CSV path:

- `frontend/src/lib/csv-export.ts` — RFC 4180-compliant `toCsv(rows, columns)`
  with CRLF, header row, formula-injection escaping (`=`, `+`, `-`, `@`, `\t`,
  `\r` prefixed with `'`), UTF-8 download blob (`text/csv;charset=utf-8;`).
- `frontend/src/lib/csv-export.test.ts` — covers the escaping + download path.
- Existing usages: `frontend/src/pages/explorer/jobs.tsx:204`,
  `frontend/src/pages/visualize/planner.tsx:206`, `frontend/src/pages/explorer/runs.tsx`,
  `frontend/src/pages/visualize/backtest.tsx`, `frontend/src/pages/visualize/demand.tsx`,
  `frontend/src/pages/visualize/forecast.tsx`.

Going client-side wins on:

- **Zero backend work** — no new endpoint, no new schema, no new test scaffolding.
- **Single source of truth** — the CSV columns are the same TypeScript fields the
  table already binds; no parallel server-side column mapping to drift.
- **Consistency** — every other table in the app exports the same way; an
  operator-facing UX inconsistency on this one page would be surprising.

Server-side `GET /batch/{id}/items.csv` is rejected at this scope because the
expected batch sizes are bounded by the MVP's "single host, single operator"
constraint — even a 5,000-item batch is ~500 KB of CSV which is trivial to ship
through the existing JSON list endpoint that the table already calls.

### Trigger point

`POST /batch/{id}/retry-failed` (item 2) and the existing `GET /batch/{id}/items`
list endpoint already drive the table. The export button reads `data?.items ?? []`
from the same TanStack Query cache the table renders — no extra fetch.

### Column set

```ts
const csvColumns: CsvColumn<BatchJobItem>[] = [
  { key: 'item_id',        header: 'Item ID' },
  { key: 'store_id',       header: 'Store ID' },
  { key: 'product_id',     header: 'Product ID' },
  { key: 'model_type',     header: 'Model' },
  { key: 'status',         header: 'Status' },
  { key: 'attempts',       header: 'Attempts' },
  { key: 'child_job_id',   header: 'Child Job ID' },
  { key: 'child_run_id',   header: 'Child Run ID' },
  { key: 'error_message',  header: 'Error' },
  { key: 'started_at',     header: 'Started' },
  { key: 'completed_at',   header: 'Completed' },
  { key: 'duration_ms',    header: 'Duration (ms)' },
]
```

All columns ship by default; column visibility on the table itself (already
supported by `frontend/src/components/data-table/data-table.tsx:50,75` via
`enableColumnVisibility`) lets the operator hide noisy columns visually but the
CSV always exports the full canonical set so an offline file is self-contained.

### Encoding + date format

- UTF-8 output via the existing `text/csv;charset=utf-8;` Blob in `downloadCsv`.
  No BOM — Excel on Windows occasionally needs one, but the repo's other CSV
  exports (`jobs.csv`, `scenario-deltas.csv`) do not emit one, so this stays
  consistent. If a follow-up issue requests Excel compatibility, prepend
  `﻿` once in `downloadCsv` and every page benefits.
- Dates as ISO-8601 (`2026-05-20T14:30:00Z`) — matches the JSON the API already
  returns. The table cell formats with `date-fns` for display, but the CSV
  exports the raw ISO string so spreadsheets can parse it.

### File naming

```
batch-{batch_id}-items-{YYYYMMDD}.csv
```

Example: `batch-7f3a2c-items-20260520.csv`. Same shape as the demo / planner
exports — short, parseable, sortable.

### Frontend touchpoint

- **Component** — extend `frontend/src/pages/batch/batch-detail.tsx` (**NEW** in
  MVP). Add a header-action `<Button variant="outline" size="sm">` next to the
  existing "Retry all failed" button.
- **Implementation** — exactly the same shape as `planner.tsx:204` and
  `jobs.tsx:203`:

  ```ts
  function handleExport() {
    if (!data?.items?.length) return
    const today = format(new Date(), 'yyyyMMdd')
    downloadCsv(
      `batch-${batchId}-items-${today}.csv`,
      toCsv(data.items, csvColumns),
    )
  }
  ```

- **Reuse** — no new lib files, no new shadcn components. Use the existing
  `Download` icon from `lucide-react` (already in `jobs.tsx:4`).

### Test plan (export)

`frontend/src/pages/batch/batch-detail.test.tsx` (**NEW**) — vitest:

1. **Header row snapshot** — render `toCsv([], csvColumns)` and assert the first
   line equals the canonical 12-column header. This is a regression gate; any
   future column rename or reorder shows up here.
2. **Sample row** — render `toCsv([sampleItem], csvColumns)` with one fixture
   row covering each column type (string, int, status enum, ISO date, ms int,
   nullable `error_message`); assert the formula-injection escape fires on a
   crafted `error_message` like `=cmd|" /C calc"!A0`. (The escape itself is
   already covered by `csv-export.test.ts`; this test proves the column shape
   feeds it correctly.)
3. **Button disabled when empty** — assert the export button is disabled and
   the click is a no-op when `data.items` is empty.

No backend tests for export (no backend code added).

---

## ITEM 2 — Retry failed items

### User story

> As an operator looking at a finished batch with 14 failures, I want to retry
> the specific failures that look transient (DB timeout, missing data window)
> without re-running the 186 successful items, and I want each retry to produce
> a fresh registry run so the history is auditable.

### Endpoint shape

```
POST /batch/{batch_id}/retry-failed
  body: BatchRetryRequest { item_ids: list[str] | None }   # None = all failed
  → 202 Accepted, BatchRetryResponse
                  { batch_id, retried_item_ids, new_item_ids,
                    counts: { total, completed, failed, pending, running } }

POST /batch/{batch_id}/items/{item_id}/retry
  body: (empty)
  → 202 Accepted, BatchRetryResponse  # single-item convenience wrapper
```

The bulk endpoint with an optional `item_ids` filter is the primary surface;
the single-item endpoint exists purely so the row-level "Retry" button has a
clean target. Behavior is identical: each retried item produces a new
`batch_job_item` row (see "Reuse vs new rows" below) and the response carries
the refreshed counts so the frontend can update its table without a separate
`GET /batch/{id}` round-trip.

Both endpoints are **idempotent at the operator level** (a second click while a
retry is mid-flight returns 409 with the in-flight item ids) and **status-aware**
(only `failed` items are eligible; a 400 lists any non-failed item ids the
operator tried to retry).

### State machine

The MVP's `batch_job_item.status` mirrors `JobStatus` (`pending`, `running`,
`completed`, `failed`, `cancelled` — see `app/features/jobs/models.py:43-65`,
`VALID_JOB_TRANSITIONS`). Retry does **NOT** add a `failed → pending` edge.
Instead it creates a **new** `batch_job_item` row with status `pending` and
the failed row stays terminal. This keeps the existing terminal-state invariant
unchanged ("`failed` is a sink") and means no Alembic migration touches the
status check constraint.

```
failed row R   ──(retry)──►   R stays failed (terminal, kept for audit)
                              R'   (new row)   pending → running → completed | failed
                                                with R'.parent_item_id = R.item_id
                                                with R'.attempts      = R.attempts + 1
```

Pseudocode for `BatchService.retry_failed`:

```python
async def retry_failed(
    self, db: AsyncSession, batch_id: str,
    item_ids: list[str] | None,
) -> BatchRetryResponse:
    batch = await self._get_batch_or_404(db, batch_id)

    # 409 if the parent is still mid-flight — retry is only for finished batches.
    if batch.status in {BatchStatus.PENDING, BatchStatus.RUNNING}:
        raise BatchConflictError(
            f"Cannot retry while batch is {batch.status}; wait for completion."
        )

    # Resolve the candidate set.
    candidates = await self._failed_items(db, batch.id, item_ids)
    if not candidates:
        raise BatchValidationError(
            "No failed items match the request (already retried or never failed)."
        )

    # 400 if the operator asked to retry a non-failed id.
    if item_ids is not None:
        unmatched = set(item_ids) - {c.item_id for c in candidates}
        if unmatched:
            raise BatchValidationError(
                f"Items not in failed state: {sorted(unmatched)}"
            )

    # Cap attempts. batch.max_attempts default 3.
    over_cap = [c for c in candidates if c.attempts >= batch.max_attempts]
    if over_cap:
        raise BatchValidationError(
            f"Items exceed max_attempts={batch.max_attempts}: "
            f"{sorted(c.item_id for c in over_cap)}"
        )

    new_items: list[BatchJobItem] = []
    for failed in candidates:
        new_item = BatchJobItem(
            item_id=uuid.uuid4().hex,
            batch_id=batch.id,
            store_id=failed.store_id,
            product_id=failed.product_id,
            model_type=failed.model_type,
            params=failed.params,            # JSONB copy of the original args
            status=BatchItemStatus.PENDING.value,
            attempts=failed.attempts + 1,
            parent_item_id=failed.item_id,   # row-history linkage
            last_attempt_at=datetime.now(UTC),
        )
        db.add(new_item)
        new_items.append(new_item)

    # Flip parent batch back to RUNNING and reset its result_summary aggregate.
    batch.status = BatchStatus.RUNNING.value
    await db.commit()

    # Synchronous execution (same shape as JobService._execute_job).
    for item in new_items:
        await self._execute_item(db, item)

    # Recompute the aggregate from scratch over the full item set
    # (parents + retries) — this is the only safe way to keep
    # completed/failed/pending counts coherent across multiple retry waves.
    await self._refresh_result_summary(db, batch)

    return BatchRetryResponse(...)
```

### Reuse vs. new rows: **new rows, with `parent_item_id` for history**

The decision is auditability and registry-artifact integrity:

- **Each retry produces a fresh `child_run_id`** — same as a fresh train job
  through `JobService._execute_train` (`app/features/jobs/service.py:493-512`).
  The registry stores a new `model_run` row; the artifact on disk is a new
  `model_{run_id}.joblib`. The original failed item's `child_run_id` (if any)
  stays attached to it as the historical record. No `model_run` row is ever
  mutated post-success.
- **`parent_item_id` lets the table render a small "retried from R" link** on
  the new row so the chain is browsable, but downstream consumers (registry,
  the run-detail page) see independent runs.
- **`attempts` on the row** is the chain depth so a UI badge ("attempt 2 of 3")
  is one column read away.

The mutate-in-place alternative (bump `attempts`, reset `status` back to
`pending`, overwrite `child_run_id`) was considered and rejected because:

1. It would require a `failed → pending` transition that violates the existing
   "failed is terminal" invariant carried over from `VALID_JOB_TRANSITIONS`.
2. It loses the prior `child_run_id`, which means the registry has an orphan
   `model_run` with no `batch_job_item` pointing at it.
3. It makes the result-table snapshot misleading — a row that "failed at
   12:04" silently changing to "completed at 12:11" hides the retry from
   anyone who already screenshotted or exported the table.

### Retry-count cap

- `batch_job.max_attempts: int` — column on the parent, default 3, configurable
  per-batch at create time via the MVP's `POST /batch/forecasting` body.
- `batch_job_item.attempts: int` — column on each child, starts at 1 on initial
  creation and increments on each retry-child.
- A retry request that would create an item with `attempts > max_attempts`
  rejects with 400 listing the over-cap items. The operator can either raise
  the cap (a future "edit batch" affordance, out of scope here) or accept the
  failure.

### Selective vs. retry-all

- **Single-item retry** — table row has a small `<Button variant="ghost" size="sm">`
  with a retry icon (`RefreshCw` from `lucide-react`). Disabled if
  `row.status != 'failed'` or `row.attempts >= batch.max_attempts`. Clicks
  `POST /batch/{id}/items/{item_id}/retry`.
- **Retry-all-failed** — table header has a `<Button variant="outline">Retry all
  failed</Button>` next to the Export CSV button. Clicks
  `POST /batch/{id}/retry-failed` with `item_ids: null`. Disabled if there
  are no failed items.
- **Multi-select retry** — out of scope for this PRP; the bulk endpoint
  already accepts an arbitrary `item_ids` list so a future row-checkbox UI is
  one click away.

### `result_summary` aggregation

After every retry wave, `BatchService._refresh_result_summary` recomputes:

```python
{
  "total":     count(all items where parent_item_id IS NULL),    # original cohort size
  "completed": count(items where status == 'completed'           # current best status
                     and item_id IN latest_chain_member(...)),
  "failed":    count(items where status == 'failed'
                     and item_id IN latest_chain_member(...)),
  "pending":   count(items where status == 'pending'),
  "running":   count(items where status == 'running'),
  "attempts_used": sum(attempts) over latest_chain_member(...),
}
```

`latest_chain_member(item)` is "the youngest row sharing the same root ancestor"
— resolved by walking `parent_item_id` to the root and picking the row in that
tree with the largest `attempts`. In practice the parent batch is small enough
that a single SQL CTE handles it; pseudocode lives in the future PRP.

The MVP's `result_summary` already has `total / completed / failed`. The retry
work adds `pending`, `running`, and `attempts_used`, all additive — no breaking
change to consumers that pre-date this PRP.

### Concurrency

- Parent `batch_job.status ∈ {pending, running}` → `409 application/problem+json`
  with `detail="Cannot retry while batch is running; wait for completion"`. The
  operator-facing button is also disabled in that state so 409 is a defensive
  net, not the primary UX.
- Two retry requests for the same batch racing → second one sees the first
  retry's `pending` / `running` children and 409s with the in-flight item ids
  echoed back. The MVP's `BatchService` already needs a per-batch advisory
  lock to serialize parent-status writes; the retry path reuses it.
- Retry for a `cancelled` batch → 400 (`Cannot retry a cancelled batch; create
  a new batch`).

---

## SHARED UX — the batch-detail page

```
─────────────────────────────────────────────────────────────────────────────
  Batch 7f3a2c · backtest · created 2026-05-20 14:02   [ status: completed ]
─────────────────────────────────────────────────────────────────────────────

  ┌── KPIs ──────────────────────────────────────────────────────────────┐
  │ total       completed   failed    pending    attempts used / cap     │
  │   200          186         14        0           214 / 600           │
  └──────────────────────────────────────────────────────────────────────┘

  ┌── Filters ───────────────────────────────────────────────────────────┐
  │  [ status ▾ ]  [ model ▾ ]  [ store ▾ ]   sort: completed_at desc    │
  │  [✓] show retries                                                    │
  └──────────────────────────────────────────────────────────────────────┘

  ┌── Result table ──────────────────────────────────────────────────────┐
  │  [ Retry all failed (14) ]                          [ ↓ Export CSV ] │
  │ ────────────────────────────────────────────────────────────────────│
  │  Item    Store  Product  Model   Status      Attempts   Action      │
  │  7f3…01  S-001  P-101    naive   completed       1        —         │
  │  7f3…02  S-001  P-102    naive   failed          2        [ ↻ ]    │
  │  7f3…02b S-001  P-102    naive   completed       3        —  ◂ retry │
  │  …                                                                   │
  │  [ < 1 2 3 … 10 > ]                                                  │
  └──────────────────────────────────────────────────────────────────────┘
```

- KPIs at the top come from the parent `result_summary`.
- The filter row uses the existing `DataTableToolbar` (`frontend/src/components/data-table/data-table-toolbar.tsx`).
- The result table is a single `DataTable<BatchJobItem>` instance — same as
  `frontend/src/pages/explorer/jobs.tsx` — with a row-level Retry button in the
  rightmost `Action` column and two header actions ("Retry all failed",
  "Export CSV") next to each other.
- "show retries" filter is a client-side toggle that hides any row with
  `parent_item_id != null` so the table can show "original cohort only" or
  "full history" — the export always emits whatever the table currently shows.

---

## DATA MODEL DELTA

### Net-new columns on `batch_job_item` (NEW table, owned by the MVP)

The MVP introduces the table; this PRP adds:

| Column            | Type                       | Nullable | Default      | Purpose                                                  |
|-------------------|----------------------------|----------|--------------|----------------------------------------------------------|
| `attempts`        | `INTEGER`                  | NO       | `1`          | Chain depth; original row is 1, first retry is 2, etc.    |
| `last_attempt_at` | `TIMESTAMP WITH TIME ZONE` | YES      | `NULL`       | When this row most recently started running.              |
| `parent_item_id`  | `VARCHAR(32)`              | YES      | `NULL`       | `item_id` of the row this one was retried from. `NULL` for original rows. |

Plus an index for the row-history walk:

```sql
CREATE INDEX ix_batch_job_item_parent ON batch_job_item (parent_item_id);
```

### Net-new column on `batch_job`

| Column         | Type      | Nullable | Default | Purpose                                                |
|----------------|-----------|----------|---------|--------------------------------------------------------|
| `max_attempts` | `INTEGER` | NO       | `3`     | Per-batch cap; over-cap retries are rejected with 400. |

### Migration

**NEW** Alembic migration: `alembic/versions/<rev>_add_batch_retry_columns.py`
adds the four columns + the index. Forward-only. No data backfill needed — the
MVP migration ships with the table empty.

---

## API DELTA — Pydantic v2 sketches

All schemas live in `app/features/batch/schemas.py` (**NEW** in MVP).

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

# Strict request body — per `.claude/rules/security-patterns.md` §
# "Pydantic v2 strict mode on FastAPI request bodies". No date/uuid/decimal
# fields here, so no per-field `strict=False` override needed.

class BatchRetryRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    item_ids: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of `batch_job_item.item_id` values to retry. "
            "When omitted or `null`, every failed item in the batch is retried."
        ),
        max_length=500,
    )


class BatchRetryCounts(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    total:     int
    completed: int
    failed:    int
    pending:   int
    running:   int


class BatchRetryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id:           str = Field(..., description="Parent batch identifier.")
    retried_item_ids:   list[str] = Field(..., description="Failed item ids that were retried.")
    new_item_ids:       list[str] = Field(..., description="Fresh child item ids created by this retry.")
    counts:             BatchRetryCounts
    started_at:         datetime
```

Errors use the existing RFC 7807 envelope via `app/core/problem_details.py`:

| Status | Class                  | When                                              |
|--------|------------------------|---------------------------------------------------|
| 400    | `BatchValidationError` | Non-failed `item_ids`, over-cap items, empty set. |
| 404    | `BatchNotFoundError`   | Unknown `batch_id` or `item_id`.                  |
| 409    | `BatchConflictError`   | Parent still `pending` / `running`, or retry race. |

### Export endpoint

**None.** Export is client-side per the recommendation above. No new HTTP
surface; the existing `GET /batch/{id}/items` paginated list feeds it.

---

## BACKEND SERVICE SHAPE

`app/features/batch/service.py` (**NEW** in MVP — this PRP adds methods):

```python
class BatchService:
    # ... MVP methods ...

    async def retry_failed(
        self,
        db: AsyncSession,
        batch_id: str,
        item_ids: list[str] | None,
    ) -> BatchRetryResponse:
        """Retry failed children. Creates new batch_job_item rows; does NOT mutate failures."""

    async def retry_single(
        self,
        db: AsyncSession,
        batch_id: str,
        item_id: str,
    ) -> BatchRetryResponse:
        """Convenience wrapper around retry_failed for one item."""

    async def _execute_item(
        self,
        db: AsyncSession,
        item: BatchJobItem,
    ) -> BatchJobItem:
        """Mirror of JobService._execute_job — single item runs synchronously,
        produces a child Job (and thus a model_run via the existing forecasting
        pipeline), writes child_job_id and child_run_id back, updates status."""

    async def _refresh_result_summary(
        self,
        db: AsyncSession,
        batch: BatchJob,
    ) -> None:
        """Recompute the parent's `result_summary` JSONB aggregate over the
        full item set, using `latest_chain_member` semantics."""
```

The pattern matches `JobService._execute_job` (`app/features/jobs/service.py:330-407`):
status → RUNNING, try/except, status → COMPLETED on success or FAILED on
exception, `completed_at = datetime.now(UTC)`, structured log on every
transition.

---

## FRONTEND TOUCHPOINTS

| Path                                                | Status      | Purpose                                         |
|-----------------------------------------------------|-------------|-------------------------------------------------|
| `frontend/src/pages/batch/batch-detail.tsx`         | **NEW** (MVP) | Adds Export CSV + Retry header buttons + row Retry action |
| `frontend/src/pages/batch/batch-detail.test.tsx`    | **NEW**     | vitest — CSV header snapshot + retry button states |
| `frontend/src/hooks/use-batches.ts`                 | **NEW** (MVP) | Add `useRetryBatchFailed` + `useRetryBatchItem` mutations |
| `frontend/src/lib/csv-export.ts`                    | reuse       | No changes — call site only                     |
| `frontend/src/components/data-table/data-table.tsx` | reuse       | No changes — wire row Retry via column `cell`   |
| `frontend/src/types/api.ts`                         | extend (NEW) | `BatchJobItem`, `BatchRetryRequest`, `BatchRetryResponse` |

No hand-rolled UI per `.claude/rules/ui-design.md`. No new shadcn components
beyond what `jobs.tsx` already uses (`AlertDialog`, `Button`, `StatusBadge`) —
nothing to install via the `shadcn` MCP per `.claude/rules/shadcn-ui.md`.

---

## TEST PLAN

Per `.claude/rules/test-requirements.md` — every new module, public function,
API endpoint, ORM column, and migration ships with a test.

### Backend — `app/features/batch/tests/`

Layout mirrors `app/features/jobs/tests/`:

- `conftest.py` — fixture `batch_with_one_success_two_failed` that seeds a
  parent `batch_job` with three `batch_job_item` children (1 completed, 2
  failed); reused by every retry test.
- `test_models.py` (NEW or extend MVP) — constraint test for `attempts >= 1`,
  CRUD test for `parent_item_id` self-FK behaviour, index existence.
- `test_service_retry.py` (NEW) — unit tests:
  - `test_retry_failed_creates_new_rows_does_not_mutate_failed` — the failed
    rows remain `status == failed`; two new rows appear with
    `attempts == 2`, `parent_item_id` set, status terminal after `_execute_item`.
  - `test_retry_failed_idempotent_under_409_when_running` — set parent
    `status == running`; the call raises `BatchConflictError`.
  - `test_retry_failed_rejects_non_failed_item_ids` — passing a completed
    item id raises `BatchValidationError`; the message lists the offending ids.
  - `test_retry_failed_rejects_over_cap_items` — `attempts >= max_attempts`
    items raise `BatchValidationError`.
  - `test_retry_single_wraps_retry_failed` — equivalence with `item_ids=[x]`.
  - `test_result_summary_refresh_after_retry_wave` — counts move from
    `(3, 1, 2, 0, 0)` to `(3, 2, 1, 0, 0)` when one retry succeeds and the
    other still fails; `attempts_used` reflects the chain depth.
- `test_routes_retry.py` (NEW) — route integration:
  - 202 happy path for `POST /batch/{id}/retry-failed`.
  - 202 happy path for `POST /batch/{id}/items/{item_id}/retry`.
  - 409 when parent is `running` — body is `application/problem+json`.
  - 400 when `item_ids` contains a non-failed id — body is RFC 7807.
  - 404 when `batch_id` or `item_id` is unknown.
- `test_migration_retry_columns.py` (NEW, marked `@pytest.mark.integration`) —
  alembic upgrade head on a fresh `docker-compose` Postgres, then a stamp +
  downgrade to confirm the migration is reversible while it is still the
  newest head. (After merge it becomes forward-only.)

### Backend — regression

- `app/features/jobs/tests/test_service.py` — re-run unchanged. `JobStatus`
  transitions are not touched; the retry path produces new `Job` rows the same
  way `_execute_train` already does. This is the explicit regression: existing
  job behavior is undisturbed.
- `app/features/registry/tests/test_service.py` — re-run unchanged. Each retry
  produces a new `model_run` via the existing `RegistryService.create_run`
  path; no `model_run` row is mutated post-`success`. The artifact-SHA-256
  verify invariant (`GET /registry/runs/{id}/verify`) continues to hold.

### Frontend — `frontend/src/pages/batch/batch-detail.test.tsx`

- **CSV header snapshot** — `toCsv([], csvColumns)` equals the canonical 12-
  column header string. Any column add/rename breaks this gate.
- **CSV sample row** — `toCsv([fixture], csvColumns)` matches a known string
  exercising every field type including a nullable `error_message`.
- **Formula-injection** — fixture with `error_message: '=cmd|" /C calc"!A0'`
  comes out CSV-escaped (leading `'`).
- **Export button disabled when empty** — `data.items === []` ⇒ button is
  `disabled`.
- **Retry-all-failed button visibility** — visible only when
  `result_summary.failed > 0` and parent status is terminal; disabled while
  the mutation is in-flight.
- **Row Retry button gates** — visible only when `row.status === 'failed'`;
  disabled when `row.attempts >= batch.max_attempts`.

### Frontend — regression

- `frontend/src/lib/csv-export.test.ts` — unchanged. The library itself is not
  touched.

All tests pass under `uv run pytest -v -m "not integration"` (unit) and the
integration migration test under `uv run pytest -v -m integration`. Frontend
runs `pnpm tsc --noEmit && pnpm lint && pnpm test --run` clean.

---

## RISKS AND MITIGATIONS

| Risk                                                                                          | Likelihood | Mitigation                                                                                                                          |
|-----------------------------------------------------------------------------------------------|------------|-------------------------------------------------------------------------------------------------------------------------------------|
| Retry creates orphan `model_run` rows in the registry when `_execute_item` raises mid-flight. | Medium     | Reuse `JobService._execute_job`'s exception path — the registry row only finalizes on `success`, so a crash leaves a `failed` model_run with valid `runtime_info`. No orphan artifact ever lands on disk; `RegistryService.create_run` rolls back on commit failure. |
| Large CSV (>10 MB) exhausts browser memory.                                                   | Low        | MVP-bounded batch size; even 5,000 items × 12 columns ~600 KB. If we hit this in practice, add server-side `GET /batch/{id}/items.csv` later — the schema is set up for it. |
| Retry wave deadlocks against a concurrent batch run.                                          | Low        | Per-batch advisory lock (MVP scope); retry reuses it. The 409 path is the user-visible safety valve.                                |
| `result_summary` recomputation drifts as more retry waves land.                               | Medium     | `_refresh_result_summary` recomputes from scratch over the full item set on every retry wave — no incremental aggregation, no drift. |
| Operator clicks "Retry all" twice quickly, double-creating retry rows.                        | Medium     | Frontend disables the button while `useRetryBatchFailed.isPending`; backend 409s on the second call via the advisory lock.          |
| A retried item's params drifted because the MVP serialized them differently from `Job.params`.| Low        | The retry copies the **stored** `batch_job_item.params` JSONB verbatim — no re-derivation from the parent's `batch_job.params`. Schema drift between MVP versions is therefore retry-safe. |

---

## OPEN QUESTIONS

These are for the follow-up PRP author to decide:

1. **Excel BOM** — should `downloadCsv` prepend `﻿` once and benefit every
   page, or stay BOM-less? Current repo convention is BOM-less; this PRP
   inherits that. A follow-up issue could flip it globally.
2. **Single-item retry vs. multi-select retry** — this PRP ships single-row
   and retry-all-failed. A row-checkbox multi-select UI is one TanStack Table
   feature flag away; defer until a real operator asks for it.
3. **Should `max_attempts` be editable post-create?** This PRP says no (lock
   it at create time); a "PATCH /batch/{id}" affordance is a separate
   enhancement.
4. **Retry observability** — emit a structured-log line per retry wave
   (`batch.retry_wave`, `n_items`, `batch_id`) and let the operator scrape it,
   or also surface it on the batch-detail page as a small "Retry history"
   panel? This PRP recommends the log line only; the UI panel can land later
   when there is enough retry data to make it useful.
5. **Agent integration** — should the batch agent be able to call
   `retry_failed` as a tool? If yes, the tool must be added to
   `agent_require_approval` per `docs/_base/SECURITY.md` § "LLM / Agent
   Security". This PRP says **no** for now — keep the human-in-the-loop
   approval surface narrow until the export+retry UX is dogfooded.
6. **Pagination boundary for the result table** — `DataTable` uses
   `manualPagination` (server-side). For a 5k-item batch should the export
   pull `data.items` from the current page only (matches what's visible),
   or fetch the full list via a separate paginated walk? Recommendation:
   current page only with a small "Export current page" label; a "Export
   all" path can land as a follow-up that paginates through `GET /batch/{id}/items`.

---

## REFERENCES

### Existing files this plan relies on (all verified to exist)

- `docs/optional-features/06-portfolio-forecasting-batch-runner.md` — source vision.
- `frontend/src/lib/csv-export.ts` — reused verbatim.
- `frontend/src/lib/csv-export.test.ts` — coverage of the lib.
- `frontend/src/pages/explorer/jobs.tsx:25,30-37,203-205` — closest pattern (same
  table + same Export CSV header action shape).
- `frontend/src/pages/visualize/planner.tsx:35,204-207` — second pattern reference.
- `frontend/src/components/data-table/data-table.tsx` — reused unchanged.
- `frontend/src/components/data-table/data-table-toolbar.tsx` — filter row reused.
- `app/features/jobs/models.py:43-65` — `JobStatus` + `VALID_JOB_TRANSITIONS`
  invariant this PRP preserves.
- `app/features/jobs/service.py:330-407` — `_execute_job` pattern that
  `_execute_item` mirrors.
- `app/features/jobs/service.py:493-525` — the train sub-job pattern that a
  retried batch item follows.
- `app/core/problem_details.py` — RFC 7807 envelope used by the 400/404/409 paths.
- `app/shared/models.py` — `TimestampMixin` for the new columns' `created_at` /
  `updated_at`.
- `docs/_base/ARCHITECTURE.md` — vertical-slice constraint enforced.
- `docs/_base/API_CONTRACTS.md` — endpoint listing this PRP extends.
- `docs/_base/SECURITY.md` § "Pydantic v2 strict mode" — followed on all new request bodies.
- `docs/_base/RULES.md` — forward-only migration and HITL invariants.
- `.claude/rules/test-requirements.md` — test layout this PRP commits to.
- `.claude/rules/ui-design.md` and `.claude/rules/shadcn-ui.md` — UI tooling rules
  (no hand-rolled UI; no new shadcn components needed here).

### NEW files this plan introduces

- `app/features/batch/` — entire vertical slice (most of it owned by the MVP).
- `app/features/batch/models.py` — `BatchJob`, `BatchJobItem`, `BatchStatus`,
  `BatchItemStatus`, `VALID_BATCH_TRANSITIONS` (MVP); + `attempts`,
  `last_attempt_at`, `parent_item_id`, `max_attempts` columns (this PRP).
- `app/features/batch/schemas.py` — `BatchRetryRequest`, `BatchRetryResponse`,
  `BatchRetryCounts`, `BatchValidationError`, `BatchConflictError`,
  `BatchNotFoundError` (this PRP).
- `app/features/batch/service.py` — `BatchService.retry_failed`,
  `retry_single`, `_execute_item`, `_refresh_result_summary` (this PRP).
- `app/features/batch/routes.py` — `POST /batch/{id}/retry-failed`,
  `POST /batch/{id}/items/{item_id}/retry` (this PRP).
- `app/features/batch/tests/test_service_retry.py`,
  `app/features/batch/tests/test_routes_retry.py`,
  `app/features/batch/tests/test_migration_retry_columns.py` (this PRP).
- `alembic/versions/<rev>_add_batch_retry_columns.py` (this PRP).
- `frontend/src/pages/batch/batch-detail.tsx` (MVP) — extended for Export +
  Retry actions here.
- `frontend/src/pages/batch/batch-detail.test.tsx` (this PRP).
- `frontend/src/hooks/use-batches.ts` — `useRetryBatchFailed`,
  `useRetryBatchItem` (this PRP); base `useBatch`, `useBatches` (MVP).
- `frontend/src/types/api.ts` — extended with `BatchJobItem`,
  `BatchRetryRequest`, `BatchRetryResponse` types (this PRP).
