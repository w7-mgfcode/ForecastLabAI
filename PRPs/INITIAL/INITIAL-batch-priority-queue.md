# INITIAL-batch-priority-queue.md — Priority Queue for Batch Forecasting Children

**Status:** proposed
**Depends on:** `batch-runner-mvp` (the MVP parent/child surface from `docs/optional-features/06-portfolio-forecasting-batch-runner.md`) — **NEW**, not yet implemented.
**Related (independent):** `batch-parallel-execution` (semaphore-bounded fan-out) — **NEW**, separate INITIAL. This doc assumes both eventually coexist; ordering decisions are the input the parallel runner consumes.
**Author:** plan-feature session, 2026-05-20
**Successor:** `PRPs/PRP-N-batch-priority-queue.md` (to be authored)

---

## Problem Statement

A portfolio operator typically fans out a single batch into hundreds of `(store_id, product_id, model_type)` tuples — e.g. "retrain everything for region EU after a master-data refresh". The MVP `batch_job` + `batch_job_item` surface processes children in insertion order (FIFO), which is fine when every series matters equally. It breaks down in three concrete scenarios:

1. **Revenue-weighted recovery.** Overnight pipeline failed for region EU. The operator restarts the batch at 08:30 with a 30-minute window before the morning revenue dashboard refreshes. The top-20 SKUs by trailing-90-day revenue must finish before the long tail; FIFO blindly retrains low-volume SKUs first because the upstream scope expansion happened to emit them in `product_id ASC` order.
2. **High-error catch-up.** A backtest sweep flagged 50 series with WAPE > 0.40. The operator wants those 50 retrained ahead of the routine nightly batch already queued; today's only knob is to manually cancel + resubmit, losing audit lineage.
3. **Ad-hoc executive ask.** A merchandiser asks for an updated forecast for one specific SKU while a 2000-item batch is mid-run. FIFO forces them to wait behind 1500 routine items.

The MVP ships a working surface; **this slice adds an ordering knob without altering FIFO as the default**. Setting no priority must remain a strict FIFO experience (zero behavior drift for existing callers and tests).

**Who is affected:** portfolio operators, the agent layer (an `experiment` agent's `submit_batch` tool will inherit a priority arg), and `app/features/jobs/` consumers indirectly (see §Scoping decision).
**Pain if unsolved:** the batch runner stays a research toy; operator value plateaus at MVP.

---

## Goals

- **Primary:** A `batch_job_item` can carry a priority value; the runner picks the next pending child by `(priority DESC, created_at ASC)` instead of strict `created_at ASC`. Default priority is `NORMAL`, which preserves today's FIFO behavior for any caller that never opts in.
- **Secondary:**
  - Mutate priority on a pending child or whole batch via REST (operator UX).
  - Log every priority change as a structured event (`batch.priority_changed`) for auditability.
  - Keep starvation bounded — document the trade-off and ship an aging knob as a config-gated, off-by-default feature.
  - Expose a single dropdown control on the batch-submit form (shadcn `Select`).
- **Non-goals (explicit):**
  - Preemption (a higher-priority child does **not** pause a lower-priority one mid-run).
  - Cross-batch fairness / quotas (single-tenant; `.claude/rules/product-vision.md`).
  - Reordering the `app/features/jobs/job` table — see §Scoping decision.
  - A new `priority` MCP/agent tool surface beyond extending `submit_batch` (see §Security).
  - Per-user or per-role priority limits (no auth model exists; `docs/_base/SECURITY.md`).
  - Pluggable scheduling algorithms (weighted-fair-queue, deadline-aware, etc. — explicit no per product-vision §"Not a generic ML platform").

---

## Scoping decision — children-only, not the global jobs slice

**Decision:** Priority lives on `batch_job_item` (and `batch_job` as a default for newly-inserted children). It does **not** touch `app/features/jobs/job`.

**Why:**

- The `job` table is consumed by `/jobs`, `/forecasting/train`, `/backtesting/run`, the agent tools, the demo pipeline, and the frontend Ops page (`frontend/src/pages/ops.tsx`, `frontend/src/pages/explorer/jobs.tsx`, `frontend/src/pages/explorer/job-detail.tsx`). Changing FIFO semantics there would silently re-order:
  - `scripts/run_demo.py` step 6 (parallel-train, asserts deterministic completion order from `created_at` ASC).
  - `tests/test_e2e_demo.py` integration assertions on job ordering.
  - The dashboard's "recent jobs" list (`list_jobs` ordered by `created_at` desc).
- Jobs today **execute synchronously inside `JobService.create_job`** (`app/features/jobs/service.py:150-191`) — there is no real queue to reorder. A `job.priority` column would be a behavioral lie until the slice is rewritten as an async worker (a separate, much larger effort).
- Batch children are a **new** consumer of a **new** queue introduced by the MVP — no installed base to disrupt. Priority is opt-in by construction.
- If a future PRP introduces an async `jobs` worker, the priority pattern landed here is the precedent it can copy.

**Trade-off accepted:** an operator who wants to prioritize a single ad-hoc forecast outside a batch must still submit it as a one-item batch. Documented in §Open Questions Q3.

---

## Out of scope (deferred)

- **Preemption.** A higher-priority child arriving mid-run does not kill a running lower-priority child. Each child runs to completion (or failure) once picked; the next pick honors the new priority. Preemption breaks idempotency, complicates artifact cleanup, and conflicts with `.claude/rules/product-vision.md` §"Not a destructive tool".
- **Cross-batch global ordering.** Each batch is its own queue. A `URGENT` child in batch B does **not** jump ahead of a `NORMAL` child in batch A that's already in flight. Two batches running concurrently share the parallel-runner semaphore but their internal orderings are independent.
- **Dynamic priority based on real-time error.** An item's WAPE is unknown until backtest completes; we do not auto-bump priority mid-batch.
- **Priority on the `job` table.** See §Scoping decision.
- **Fair-share scheduling, deadline-earliest-first, weighted-round-robin.** Out per product-vision.
- **Per-tenant or per-user quotas.** No auth model.

---

## Data model delta

### New columns on `batch_job_item` (**NEW** table from MVP)

| Column | Type | Default | Index | Notes |
|--------|------|---------|-------|-------|
| `priority` | `SMALLINT` (CHECK constraint, see below) | `0` (NORMAL) | covered by composite below | Higher value runs sooner. |
| `priority_updated_at` | `TIMESTAMPTZ` | NULL | none | Set when priority is mutated post-insert; NULL when it equals the value at insert. Used by §Starvation handling. |
| `priority_history` | `JSONB` | `'[]'::jsonb` | GIN if queried | Append-only array of `{from, to, at, source}` records. Source ∈ `{user, agent, aging}`. |

### New column on `batch_job` (**NEW** table from MVP)

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `default_child_priority` | `SMALLINT` | `0` (NORMAL) | Stamped onto every child at scope-expansion time. A later per-child override wins. |

### Enum / band design

Use a small integer band rather than a free integer, exposed as a Python `IntEnum` in `app/features/batch/models.py`:

```python
class BatchPriority(IntEnum):
    LOW = -1
    NORMAL = 0
    HIGH = 1
    URGENT = 2
```

**Why bands:** four discrete values map to a four-option UI dropdown and a Pydantic `Literal[...]` field, eliminate operator second-guessing ("is 7 higher than 5?"), and stay compact in the JSONB history. A future widening to six bands is a backward-compatible `IntEnum` extension; widening to free integers is not. Higher value = runs sooner (matches user mental model "urgent is bigger").

**CHECK constraint:**

```sql
CHECK (priority BETWEEN -1 AND 2)
```

### Composite index — the load-bearing one

```sql
CREATE INDEX ix_batch_job_item_picker
  ON batch_job_item (batch_id, status, priority DESC, created_at ASC)
  WHERE status = 'pending';
```

A **partial** index on `status = 'pending'` keeps it tiny (children leave it the moment they start running). The leading column is `batch_id` so the planner can scope each batch's picker query to its own slice; `status` is included so the partial-index predicate matches. The tail `(priority DESC, created_at ASC)` is the picker's sort key.

### Migration impact

- **Risk: LOW.** Both columns land on **new** tables introduced by the MVP migration. Adding the columns + index in the same Alembic revision as the MVP — or in a small follow-up revision against an unused table — is a forward-only, zero-data-rewrite change.
- **NEVER edit** the MVP migration once merged (`.claude/rules/security-patterns.md`). If the MVP has already landed, ship a new revision: `alembic/versions/<rev>_add_batch_priority.py` — **NEW**.
- Backfill: `batch_job_item.priority` defaults to `0` (NORMAL), preserving FIFO for any rows the MVP created.

---

## API delta

All schemas Pydantic v2; request bodies use `model_config = ConfigDict(strict=True)` per `.claude/rules/security-patterns.md` §"Pydantic v2 strict mode on FastAPI request bodies". No `date`/`UUID`/`Decimal` fields in this slice → no per-field `Field(strict=False, ...)` needed.

### Extended request — `POST /batch/forecasting` (**NEW** in MVP; extended here)

```python
class BatchPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

class BatchSubmitRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    # ... fields owned by the MVP (scope, model_configs, operation) ...
    default_child_priority: BatchPriority = Field(
        default=BatchPriority.NORMAL,
        description="Default priority stamped onto every child item. "
                    "Per-child overrides via PATCH /batch/{batch_id}/items/{item_id}.",
    )
```

The string-enum at the API boundary maps to the `IntEnum` inside the ORM via a single converter — operators get a readable surface, the DB gets a sortable scalar.

### New endpoints (**NEW**)

| Method | Path | Purpose | Status codes |
|--------|------|---------|--------------|
| `PATCH` | `/batch/{batch_id}` | Reprioritize **all pending** children in one shot. Body: `{"default_child_priority": "high"}`. Already-running and completed children unaffected. | 200, 404, 400 (no pending children), 409 (batch terminal) |
| `PATCH` | `/batch/{batch_id}/items/{item_id}` | Reprioritize a single pending child. Body: `{"priority": "urgent"}`. | 200, 404, 400 (child not pending), 409 (child terminal) |
| `GET`   | `/batch/{batch_id}/items` | (MVP-owned) — `priority` is added to the response row + `?sort_by=priority` allow-listed. | 200 |

Errors use the existing RFC 7807 envelope (`app/core/problem_details.py`). Mutating endpoints emit `batch.priority_changed` structlog events with `batch_id`, `item_id`, `from`, `to`, `source`, and the `request_id` from `RequestIdMiddleware`.

### Response delta — `BatchItemResponse` (**NEW** in MVP; extended here)

```python
class BatchItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    # ... fields owned by the MVP (item_id, store_id, product_id, model_type, status, job_id, ...)
    priority: BatchPriority
    priority_updated_at: datetime | None
    # priority_history intentionally NOT in the default response — fetch via ?include=history
```

---

## Backend service shape

### Picker query (the load-bearing one)

The MVP's "pick next pending child for batch X" query becomes:

```python
# app/features/batch/service.py (**NEW** in MVP)
stmt = (
    select(BatchJobItem)
    .where(
        BatchJobItem.batch_id == batch_id,
        BatchJobItem.status == BatchItemStatus.PENDING.value,
    )
    .order_by(
        BatchJobItem.priority.desc(),
        BatchJobItem.created_at.asc(),
        BatchJobItem.id.asc(),  # tie-breaker on identical created_at (bulk insert)
    )
    .limit(1)
    .with_for_update(skip_locked=True)
)
```

Notes:

- `priority DESC, created_at ASC` is the explicit sort. Tie-breaker on `id` because bulk-insert of 1000 children can produce identical `created_at` timestamps at PostgreSQL's microsecond resolution.
- `with_for_update(skip_locked=True)` translates to `FOR UPDATE SKIP LOCKED` — required once the parallel runner (separate INITIAL) runs more than one picker concurrently. With a single worker today, `SKIP LOCKED` is a no-op but the wiring lands now to avoid retrofitting later.
- The partial index `ix_batch_job_item_picker` (above) covers this exact predicate + sort.
- Run inside a transaction; the same transaction transitions the row to `RUNNING` before commit, so a concurrent picker skips it.

### Mutation helper

```python
async def set_priority(
    db: AsyncSession,
    item: BatchJobItem,
    new_priority: BatchPriority,
    *,
    source: Literal["user", "agent", "aging"],
) -> None:
    if item.status != BatchItemStatus.PENDING.value:
        raise BatchItemNotPendingError(item.item_id, item.status)
    old = BatchPriority(item.priority)
    if old == new_priority:
        return  # no-op, no audit event
    item.priority_history = [
        *item.priority_history,
        {"from": old.name, "to": new_priority.name,
         "at": datetime.now(UTC).isoformat(), "source": source},
    ]
    item.priority = new_priority.value
    item.priority_updated_at = datetime.now(UTC)
    logger.info(
        "batch.priority_changed",
        batch_id=item.batch_id, item_id=item.item_id,
        old=old.name, new=new_priority.name, source=source,
    )
```

A bulk variant (`PATCH /batch/{batch_id}`) applies the same mutation to every pending child in a single transaction, emitting one structlog event per affected row (not one aggregate event — auditability requires per-row records).

---

## Starvation handling

A pure priority queue can starve `LOW`-priority items forever if `URGENT` children keep arriving. Two mitigation paths:

### Recommendation: ship aging behind a config flag, default OFF

```python
# app/core/config.py — **NEW** settings
batch_priority_aging_enabled: bool = False
batch_priority_aging_minutes: int = 30  # bump one band per N minutes pending
```

When enabled, a background tick (re-using the parallel runner's loop, **NOT** a new scheduler) bumps any pending child whose `created_at` is older than `aging_minutes` and whose priority is below `URGENT`:

```sql
UPDATE batch_job_item
   SET priority = priority + 1,
       priority_updated_at = now(),
       priority_history = priority_history || jsonb_build_object(
         'from', priority::text, 'to', (priority + 1)::text,
         'at', now()::text, 'source', 'aging'
       )
 WHERE status = 'pending'
   AND priority < 2
   AND created_at < now() - make_interval(mins => :aging_minutes);
```

**Why default-OFF:** matches `.claude/rules/product-vision.md` §"single-host, single-tenant" — the operator running a single batch at a time on their laptop rarely hits starvation. Flag exists so the moment the parallel runner lets two batches coexist, the knob is one env var away.

### Explicit non-goal alternative (rejected)

Hard time-bounded fairness (`SCHED_RR`-style round-robin within priority bands) — out per product-vision §"Not a generic ML platform".

---

## Frontend touchpoints

All UI work goes through `.claude/rules/ui-design.md` + `.claude/rules/shadcn-ui.md`. No hand-rolled components.

| Surface | Component | Action |
|---------|-----------|--------|
| **NEW** batch submit form (`frontend/src/pages/visualize/batch.tsx` — **NEW**, owned by MVP) | shadcn `Select` (already used in `frontend/src/pages/visualize/planner.tsx`) | Four-option `Default child priority` dropdown: Low / Normal / High / Urgent. Default = Normal. |
| **NEW** batch detail page (`frontend/src/pages/explorer/batch-detail.tsx` — **NEW**, owned by MVP) | shadcn `DropdownMenu` per row + `Button` "Reprioritize all pending" | Row dropdown calls `PATCH /batch/{id}/items/{item_id}`; the bulk button calls `PATCH /batch/{id}`. Disabled when the row is no longer pending. |
| Children table | TanStack Table | Add `priority` column with a sortable header (sort param maps to `?sort_by=priority`). Column renders a `Badge` per priority band (existing `frontend/src/components/ui/badge.tsx`). |
| Audit drawer | shadcn `Sheet` | "View priority history" opens a side panel listing `priority_history` entries. Fetches with `?include=history`. |
| Color tokens | Tailwind semantic tokens only | `URGENT` → `bg-destructive`, `HIGH` → `bg-primary`, `NORMAL` → `bg-muted`, `LOW` → `bg-secondary`. **No raw colors** (per `.claude/rules/shadcn-ui.md`). |

**Verification:** every frontend touchpoint MUST be exercised in a real browser via the `webapp-testing` or `agent-browser` skill before the PRP is merged (per `.claude/rules/ui-design.md` §"Hard Requirements").

---

## Test plan

All per `.claude/rules/test-requirements.md`. New tests live in `app/features/batch/tests/` (**NEW** directory, owned by MVP) + `frontend/src/pages/explorer/batch-detail.test.tsx` (**NEW**).

### Unit (mocked, fast, no DB)

- `test_priority_enum_ordering` — assert `URGENT > HIGH > NORMAL > LOW` as integers (round-trip via the picker's comparator).
- `test_set_priority_no_op` — same-value mutation emits no event and does not append to `priority_history`.
- `test_set_priority_non_pending_rejected` — calling on `running` / `completed` / `failed` / `cancelled` raises `BatchItemNotPendingError`.
- `test_priority_history_append_only` — three mutations produce three entries in insertion order.
- `test_default_child_priority_applied` — children inserted by scope expansion inherit `BatchJob.default_child_priority`.

### Integration (real Postgres, `@pytest.mark.integration`)

- `test_picker_fifo_baseline` — 5 children all at `NORMAL`; picker returns them in `created_at` ASC order. **Proves zero behavior drift when priority is unset.**
- `test_picker_priority_override` — 3 `NORMAL` + 2 `URGENT` (inserted later). Picker returns the two `URGENT` first, then the three `NORMAL` in insertion order.
- `test_picker_tie_break_on_created_at` — 5 children at identical priority, identical `created_at` (bulk insert in one statement); picker order is stable across runs via the `id` tie-breaker.
- `test_picker_skip_locked` — open a transaction holding a `FOR UPDATE` lock on the highest-priority child; a second session's picker returns the next-highest-priority unlocked child (proves `SKIP LOCKED` wiring).
- `test_patch_batch_reprioritize_all_pending` — `PATCH /batch/{id}` with `default_child_priority=HIGH` bumps only pending children; running and completed rows untouched.
- `test_patch_item_terminal_rejected` — `PATCH /batch/{id}/items/{item_id}` on a completed child → 409.
- `test_aging_disabled_by_default` — `batch_priority_aging_enabled=False` → no priority changes after `aging_minutes` elapse (covered by frozen-clock helper).
- `test_aging_enabled_bumps_old_pending` — flag on, fast-forward clock; `LOW` → `NORMAL` after the threshold, `URGENT` does not overflow.

### Regression (covers the §Scoping decision blast-radius assertion)

- `test_jobs_list_unchanged_when_priority_unset` — runs `scripts/run_demo.py`'s `train` step three times; asserts `GET /jobs` order is identical before and after this slice's migration (this is a meta-assertion that we did not accidentally touch the `job` table).
- `test_e2e_demo_unchanged` — the existing `tests/test_e2e_demo.py` passes with no modifications.

### Pydantic v2 strict-mode regression

- `test_batch_submit_request_json_roundtrip` — `BatchSubmitRequest.model_validate({"default_child_priority": "high", ...})` (the `validate_python` path FastAPI uses on parsed JSON). Catches the strict-mode trap documented in `docs/_base/SECURITY.md`.

### Frontend (vitest)

- `batch-detail.test.tsx` — renders five priority-banded rows, clicks "Reprioritize all pending", asserts the mutation hook was called with the right body.
- Type-check (`pnpm tsc --noEmit`) MUST stay clean.

---

## Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **FIFO semantic drift leaks into the `job` table by accident** (the headline risk) | Low | High | The §Scoping decision is enforced by `test_jobs_list_unchanged_when_priority_unset` — any commit that touches `app/features/jobs/models.py` while this PRP is in flight requires explicit reviewer sign-off. |
| Starvation of `LOW` items in long-running multi-batch scenarios | Med (only post-parallel runner) | Med | Aging knob shipped off-by-default; documented in `docs/_base/RUNBOOKS.md` (Common Incidents). |
| Operator sets `URGENT` for everything → effectively FIFO again | High | Low | Educational only — show priority distribution badge counts on the batch detail header so the operator sees the regression themselves. |
| Bulk PATCH on a 5000-item batch is slow / locks too much | Low | Med | Bulk mutation runs in a single transaction with the partial index; benchmark in the PRP. If > 200 ms, paginate via `LIMIT/OFFSET` and emit one event per row anyway. |
| Operator changes priority mid-pick (race between `PATCH` and the picker) | Low | Low | `with_for_update(skip_locked=True)` on the picker; `PATCH` selects pending rows only — a row that started running between `PATCH`'s select and its update is no longer pending, so the update WHERE clause filters it out. Add an integration test. |
| Priority becomes a covert sort-tiebreaker for non-priority callers | Low | Med | The picker query is gated to `batch_job_item`; `app/features/jobs/service.py:list_jobs` is untouched. The regression test above pins this. |
| `priority_history` JSONB grows unboundedly on long-lived batches | Low | Low | Realistic upper bound: 4 bands × few changes per item = small. If it ever matters, cap to last 20 entries — defer until evidence. |
| Frontend confuses operators (4 bands feel arbitrary) | Med | Low | Match the dropdown labels to the band semantics: "Low — runs last", "Normal — FIFO default", "High — jump current queue", "Urgent — top of queue". One-line tooltip per band. |
| **Migration risk on a populated `batch_job_item` table** (post-MVP merge) | Low | Med | Default value `0` + non-NULL constraint added in the same migration; the partial index is `CREATE INDEX CONCURRENTLY`-safe but standard `CREATE INDEX` is fine on this scale (single-host, low row count). Alembic op uses `op.create_index(..., postgresql_concurrently=False)`. |
| Agent layer accidentally widens the mutation surface | Low | Med | The `submit_batch` agent tool inherits `default_child_priority` (already a request field, no new tool). A `set_batch_priority` tool would be a separate change; if introduced, **must** be added to `agent_require_approval` per `.claude/rules/security-patterns.md`. Explicitly tracked as Open Question Q4. |

---

## Security

- **Mutation surface.** `PATCH /batch/...` is a state mutation. There is no auth model (`docs/_base/SECURITY.md`), so the protection is the same as every other mutating endpoint today: single-tenant trust + structured audit logs. No new attack surface vs. the MVP.
- **Agent integration.** Today's MVP plan covers `submit_batch`; **this slice does not introduce a `set_batch_priority` tool**. If a future PRP does, the tool name MUST be added to `agent_require_approval` (currently `["create_alias", "archive_run", "save_scenario"]`) before merge. This is non-negotiable per `.claude/rules/security-patterns.md` §"LLM / Agent layer".
- **Audit log content.** `batch.priority_changed` records contain no user-supplied freeform text — only enum values, ids, and timestamps. No PII redaction required.
- **Input validation.** Pydantic v2 `StrEnum` on the API boundary makes "priority = 999" impossible; the DB `CHECK (priority BETWEEN -1 AND 2)` is the belt to the Pydantic suspenders.

---

## Open questions (for the PRP author)

- [ ] **Q1 — Aging default.** Ship aging on or off by default? Recommendation here is **off**; revisit once the parallel-execution runner is in and we have real evidence of multi-batch contention.
- [ ] **Q2 — Bulk PATCH cap.** Cap the number of rows a single `PATCH /batch/{id}` can touch (e.g. 1000), or rely on the partial index + single transaction? Recommendation: no cap until benchmark says otherwise; document the practical upper bound.
- [ ] **Q3 — Should "ad-hoc one-item batch" become a sanctioned UX?** The §Scoping decision punts single-job priority to "submit as a 1-item batch". Is that good enough, or do we want a `POST /batch/forecasting/quick` thin wrapper? Recommendation: defer; revisit after operator feedback.
- [ ] **Q4 — Agent `set_priority` tool.** Worth shipping in the same PRP as the REST endpoints, or defer until an operator asks? Recommendation: defer. Adds approval-gate surface area without proven value. If shipped, MUST land in `agent_require_approval`.
- [ ] **Q5 — Number of bands.** Four feels right for a portfolio operator; some shops prefer three (Normal / High / Urgent). The Pydantic `StrEnum` + DB `CHECK` make adding/dropping a band a single forward-only migration.
- [ ] **Q6 — Surface `priority` on `BatchJobItem` GET responses by default?** Currently yes; consider whether the history (`?include=history`) is the right gate or whether it should be on by default once row counts settle.

---

## References

Files relied on (all present in repo unless marked **NEW**):

- `docs/optional-features/06-portfolio-forecasting-batch-runner.md` — source feature doc.
- `app/features/jobs/models.py` — today's `Job` model + `JobStatus` transitions; the surface this PRP deliberately does **not** touch.
- `app/features/jobs/service.py:150-191` — proves jobs execute synchronously inside `create_job` (no real queue today).
- `app/features/jobs/schemas.py`, `app/features/jobs/routes.py` — the API surface this PRP must not regress.
- `app/core/problem_details.py` — RFC 7807 envelope reused by new endpoints.
- `app/core/config.py` — pattern for the two new `batch_priority_aging_*` settings.
- `app/core/database.py` — `Base`, async session helper.
- `app/shared/models.py` — `TimestampMixin` (matched by all ORM models).
- `frontend/src/pages/visualize/planner.tsx` — precedent for shadcn `Select` usage in a submit form.
- `frontend/src/pages/explorer/jobs.tsx`, `frontend/src/pages/explorer/job-detail.tsx` — pattern for TanStack-Table + detail-drawer pages.
- `.claude/rules/security-patterns.md` — strict-mode policy, Pydantic v2 JSON path, agent-approval rules.
- `.claude/rules/product-vision.md` — single-host, single-tenant, not-a-streaming-system constraints.
- `.claude/rules/test-requirements.md` — unit + integration policy; integration tests hit real Postgres.
- `.claude/rules/ui-design.md`, `.claude/rules/shadcn-ui.md` — UI sourcing, no hand-rolled components.
- `.claude/rules/output-formatting.md` — formatting matched here.
- `docs/_base/API_CONTRACTS.md` — endpoint-listing format mirrored.
- `docs/_base/DOMAIN_MODEL.md` — aggregate + invariant conventions.
- `docs/_base/RUNBOOKS.md` — where the starvation diagnosis runbook will land.
- `PRPs/INITIAL/INITIAL-MLZOO-B-lightgbm-first-model.md`, `PRPs/INITIAL/INITIAL-14.md` — INITIAL format references.

**NEW** files this slice introduces (named here for the PRP author to confirm):

- `alembic/versions/<rev>_add_batch_priority.py`
- `app/features/batch/models.py` — `BatchPriority` IntEnum + ORM columns (or amended MVP file)
- `app/features/batch/schemas.py` — `BatchPriority` StrEnum + extended request/response models
- `app/features/batch/service.py` — picker query + `set_priority` helper
- `app/features/batch/routes.py` — `PATCH` endpoints
- `app/features/batch/tests/test_priority.py`, `test_priority_picker.py`, `test_priority_aging.py`
- `frontend/src/pages/visualize/batch.tsx` (extended), `frontend/src/pages/explorer/batch-detail.tsx`
- `docs/_base/API_CONTRACTS.md` rows for the new PATCH endpoints

External references (PRP-time only, not consumed in this doc):

- PostgreSQL row locks (`FOR UPDATE SKIP LOCKED`): https://www.postgresql.org/docs/16/sql-select.html#SQL-FOR-UPDATE-SHARE
- SQLAlchemy `with_for_update`: https://docs.sqlalchemy.org/en/21/orm/queryguide/query.html#sqlalchemy.orm.Query.with_for_update
- shadcn `Select` and `DropdownMenu` registry items (via the `shadcn` MCP per `.claude/rules/shadcn-ui.md`).
