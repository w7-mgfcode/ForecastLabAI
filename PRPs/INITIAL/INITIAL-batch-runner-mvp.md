# INITIAL-batch-runner-mvp.md — Portfolio Forecasting Batch Runner (MVP)

**Status:** proposed
**Depends on:** none — this slice is the unblocker.
**Blocks:** `INITIAL-batch-parallel-execution`, `INITIAL-batch-priority-queue`,
`INITIAL-batch-export-and-retry`, `INITIAL-batch-champion-and-heatmap` (all four
declare `depends_on: batch-runner-mvp`).
**Source feature doc:** `docs/optional-features/06-portfolio-forecasting-batch-runner.md` § "MVP Scope".
**Successor:** `PRPs/PRP-NN-batch-runner-mvp.md` (to be authored).
**Author:** prompt-architect / claude session, 2026-05-20.

---

## Problem Statement

ForecastLabAI today executes one `(store_id, product_id, model_type)` per
`POST /jobs` call — synchronously, inside the request task
(`app/features/jobs/service.py:150-191`). The shape is fine for single-SKU
demos; it falls over the moment an operator wants to retrain a region after a
master-data refresh, sweep a model across the top-200 revenue SKUs, or ask
"how did model X do across the whole portfolio." 200 round-trips, no
parent-status surface, no per-pair lineage to the registry.

This INITIAL ships the **minimum viable orchestration layer** above forecasting
+ backtesting + registry: one `batch_job` row fans out into many
`batch_job_item` rows, each executed by the same path
`JobService._execute_job` already exercises. The MVP runs items
**sequentially**; parallel execution, priority, champion selection, export,
and retry are deliberately deferred — four follow-up INITIALs are drafted and
all declare `depends_on: batch-runner-mvp`.

**Pain if unsolved:** four scoped Full-Version features sit idle because none
of them can land without the parent/child surface this slice introduces.

---

## Goals

- **Primary:** A new `app/features/batch/` slice exposes `POST /batch/forecasting`
  that (a) inserts one `batch_job` row, (b) expands `scope` into N
  `batch_job_item` rows, (c) executes them sequentially by delegating each item
  to the existing forecasting / backtesting paths, (d) writes per-item `metrics`
  JSONB in a pinned shape, (e) settles parent `status` to
  `completed | failed | partial`.
- **Primary:** `batch_job_item.metrics` JSONB shape is **fixed in this INITIAL**
  to `{wape, smape, mae, bias, sample_size}` so every downstream consumer reads
  from one known contract.
- **Primary:** The MVP migration ships every column the four downstream INITIALs
  declare as MVP-owned (so none needs a retrofit migration), plus the partial
  picker index, and wires `FOR UPDATE SKIP LOCKED` — load-bearing for parallel +
  priority later, no-op while single-threaded today.
- **Secondary:** lineage on every item (`child_job_id` → `job.job_id`;
  `child_run_id` → `model_run.run_id`); structlog events
  (`batch.{created,item_started,item_completed,item_failed,completed}`) with
  `request_id` correlation; MVP UI scaffold at `frontend/src/pages/visualize/
  batch.tsx` (no heatmap, retry, slider, or priority dropdown — those belong to
  downstream PRPs).
- **Non-goals (deferred to a downstream INITIAL):** parallel execution
  (`INITIAL-batch-parallel-execution`); priority bands
  (`INITIAL-batch-priority-queue`); failed-item retry + CSV export
  (`INITIAL-batch-export-and-retry`); champion selection + heatmap
  (`INITIAL-batch-champion-and-heatmap`); cross-batch fairness; multi-host
  scale-out / Celery / Redis (out per `.claude/rules/product-vision.md`); async
  worker process (parent endpoint awaits the full fan-out in MVP).

---

## Cross-Slice Coordination Matrix — the load-bearing section

The four downstream INITIALs each declare schema additions and read-paths. The
table below captures, per downstream doc, **what the MVP must ship now** and
**what is deferred to that downstream's own forward-only migration**. The
`batch_job_item.metrics` JSONB shape is the most critical row: it is read by
champion-selection (Item 1 of `INITIAL-batch-champion-and-heatmap`) and by every
heatmap cell (Item 2), so it MUST be pinned by the MVP author.

### batch_job_item.metrics JSONB — pinned contract

```jsonc
// batch_job_item.metrics (JSONB, nullable until item completes)
{
  "wape":        0.18,    // Weighted Absolute % Error — champion primary key
  "smape":       0.21,    // Symmetric MAPE — champion first tie-break
  "mae":         12.4,    // Mean Absolute Error — heatmap optional metric
  "bias":       -0.03,    // Mean signed error — heatmap diverging-palette metric
  "sample_size": 60       // # of (date, actual, predicted) rows the metrics aggregate
}
```

Every key is REQUIRED on a successful item; a key MAY be `null` only when the
underlying fold produced NaN (e.g. zero-actuals window). The MVP writes the same
shape regardless of operation: `train`, `predict`, `backtest`, or
`train_backtest_register`. For `predict`-only items the values come from the most
recent backtest of the same `run_id` if one exists; if no metrics exist the item
ships `metrics = null` (champion logic excludes it via `unresolved_pairs`).

**Consumer trace:**

| Key | Consumer | Source doc |
|-----|----------|------------|
| `wape` | Champion lowest-WAPE selection; heatmap `metric=wape` | `INITIAL-batch-champion-and-heatmap` § "Definition of champion" |
| `smape` | Champion first tie-break; heatmap `metric=smape` | same |
| `mae` | Heatmap `metric=mae`; existing dashboards reuse `_BACKTEST_METRICS` | same § "Endpoint shape" |
| `bias` | Heatmap diverging-palette metric (positive vs negative) | same § "Color scale" |
| `sample_size` | Heatmap cell tooltip; champion candidate filtering | same § "HeatmapCell" |

### Column additions the MVP migration MUST ship

| Table · Column | Type / Default | Demanded by |
|----------------|----------------|-------------|
| `batch_job_item.metrics` | `JSONB nullable` | champion-and-heatmap |
| `batch_job.max_parallel` | `INTEGER NOT NULL DEFAULT 4` | parallel-execution |
| `batch_job.running_items` / `cancelled_items` | `INTEGER NOT NULL DEFAULT 0` | parallel-execution |
| `batch_job.default_child_priority` | `SMALLINT NOT NULL DEFAULT 0` | priority-queue |
| `batch_job_item.priority` | `SMALLINT NOT NULL DEFAULT 0` (CHECK BETWEEN -1 AND 2) | priority-queue |
| `batch_job_item` partial index | `(batch_id, status, priority DESC, created_at ASC) WHERE status='pending'` | priority-queue + parallel-execution |

downstream-1's § "Migration policy" demands the four `batch_job` columns be
MVP-owned. The partial picker index needs `priority` on the child to exist
already — hence shipping that one column from downstream-2 too.

### Column additions the MVP MUST NOT ship (each downstream owns its own forward-only migration)

- **export-and-retry:** `batch_job_item.{attempts, last_attempt_at, parent_item_id}`
  + `ix_batch_job_item_parent`; `batch_job.max_attempts`.
- **champion-and-heatmap:** `batch_job_item.is_champion` (indexed);
  `batch_job.champion_summary` (JSONB).
- **priority-queue:** `batch_job_item.{priority_updated_at, priority_history}`
  (the `priority` band column itself ships with the MVP — only the
  history/audit columns defer).

### agent_require_approval additions the MVP MUST NOT add

The MVP exposes **zero mutating agent tools**. The current
`Settings.agent_require_approval` list (`create_alias`, `archive_run`,
`save_scenario`) is unchanged. Future tool names downstream PRPs MUST add:
**`promote_champions`** (champion-and-heatmap); optionally `cancel_batch`
(parallel-execution Q7) and `retry_failed_items` (export-and-retry, currently
deferred).

---

## Data Model

### batch_job (NEW)

`StrEnum`s: `BatchStatus ∈ {pending, running, completed, failed, partial, cancelled}`
(`partial` = ≥1 success + ≥1 failure; `cancelled` reserved for downstream-1, MVP
never writes it); `BatchOperation ∈ {train, predict, backtest, train_backtest_register}`.

Columns (all `NOT NULL` unless noted; `TimestampMixin` adds `created_at`/`updated_at`):

| Column | Type | Default | Note |
|--------|------|---------|------|
| `id` | `Integer` PK | — | — |
| `batch_id` | `String(32)` UNIQUE INDEX | uuid hex | external id |
| `operation` | `String(30)` INDEX | — | `BatchOperation` |
| `scope` | `JSONB` | — | request `BatchScope` |
| `model_configs` | `JSONB` | — | list of `BatchModelConfig` |
| `status` | `String(20)` INDEX | `pending` | `BatchStatus` |
| `total_items` / `completed_items` / `failed_items` | `Integer` | `0` | MVP-owned counters |
| `running_items` / `cancelled_items` | `Integer` | `0` | downstream-1 (MVP keeps `0`) |
| `max_parallel` | `Integer` | `4` | downstream-1 (MVP ignores) |
| `default_child_priority` | `SmallInteger` | `0` | downstream-2 (MVP NORMAL only) |
| `params` | `JSONB` | — | request echo |
| `result_summary` | `JSONB nullable` | `NULL` | shape in Q4 |
| `started_at` / `completed_at` | `DateTime(timezone=True) nullable` | `NULL` | — |

CHECK constraints: valid `status`, valid `operation`, `default_child_priority BETWEEN -1 AND 2`.
Extra index: `ix_batch_job_status_created (status, created_at)`.

### batch_job_item (NEW)

`StrEnum BatchItemStatus ∈ {pending, running, completed, failed, cancelled}`
(`cancelled` reserved for downstream-1).

Columns:

| Column | Type | Default | Note |
|--------|------|---------|------|
| `id` | `Integer` PK | — | — |
| `item_id` | `String(32)` UNIQUE INDEX | uuid hex | external id |
| `batch_id` | `String(32)` FK → `batch_job.batch_id` `ON DELETE CASCADE`, INDEX | — | — |
| `store_id` / `product_id` | `Integer` INDEX | — | — |
| `model_type` | `String(30)` | — | `BatchModelConfig.model_type` |
| `status` | `String(20)` INDEX | `pending` | — |
| `priority` | `SmallInteger` | `0` | downstream-2 (MVP NORMAL only) |
| `params` | `JSONB` | — | frozen per-item args |
| `metrics` | `JSONB nullable` | `NULL` | pinned five-key shape above |
| `child_job_id` / `child_run_id` | `String(32) nullable` INDEX | `NULL` | lineage to `job` + `model_run` |
| `error_message` (2000) / `error_type` (100) | `String nullable` | `NULL` | mirrors `Job` |
| `started_at` / `completed_at` | `DateTime(timezone=True) nullable` | `NULL` | — |
| `duration_ms` | `Integer nullable` | `NULL` | — |

CHECK: valid `status`, `priority BETWEEN -1 AND 2`.

Indexes:

- `ix_batch_job_item_batch_status (batch_id, status)`.
- **`ix_batch_job_item_picker (batch_id, status, priority, created_at)
  WHERE status = 'pending'`** — partial index, load-bearing for downstream-1
  (parallel) and downstream-2 (priority); MVP picker uses it too.
- `ix_batch_job_item_metrics_gin (metrics)` — GIN, for heatmap aggregation
  (downstream-4) and ad-hoc JSONB containment queries.

### Migration

**ONE** Alembic revision (`alembic/versions/<rev>_create_batch_tables.py` — NEW)
creates both tables, all columns in the matrix above, all CHECK constraints, and
all indexes including the partial picker index. Forward-only after merge. Must
upgrade cleanly on an empty `docker-compose` Postgres so the CI `migration-check`
job stays green (`docs/_base/PIPELINE_CONTRACT.md`).

---

## API Surface (MVP)

All schemas Pydantic v2 with `model_config = ConfigDict(strict=True)` on request
bodies (per `docs/_base/SECURITY.md` § "Pydantic v2 strict mode on FastAPI request
bodies"). Errors use `application/problem+json` via `app/core/problem_details.py`
(`docs/_base/API_CONTRACTS.md`).

| Method | Path | Purpose | Codes |
|--------|------|---------|-------|
| POST | `/batch/forecasting` | Submit a batch (expands scope, runs sequentially, returns 202-shaped). | 202, 400, 422 |
| GET  | `/batch/{batch_id}` | Parent record + rolled-up counts. | 200, 404 |
| GET  | `/batch/{batch_id}/items` | Paginated child rows (allow-listed `sort_by ∈ {created_at, completed_at, status, priority}`). | 200, 404 |

**Out of scope for MVP** (each owned by exactly one downstream INITIAL):

- `DELETE /batch/{batch_id}` (cancellation contract) — `INITIAL-batch-parallel-execution`.
- `PATCH /batch/{batch_id}` and `PATCH /batch/{batch_id}/items/{item_id}` (priority
  mutation) — `INITIAL-batch-priority-queue`.
- `POST /batch/{batch_id}/retry-failed` and `POST /batch/{batch_id}/items/{item_id}/retry`
  — `INITIAL-batch-export-and-retry`.
- `GET /batch/{batch_id}/champions`, `POST /batch/{batch_id}/promote-champions`,
  `GET /batch/{batch_id}/heatmap` — `INITIAL-batch-champion-and-heatmap`.

### BatchSubmitRequest (sketch)

Pydantic v2 `ConfigDict(strict=True)` on every nested model; `Field(strict=False, …)`
on every `date`/`datetime`/`UUID`/`Decimal` per the strict-mode policy.

- `BatchScope`: `kind ∈ {manual, region, category, top_revenue, all}` + the
  matching selector fields (`store_ids` / `product_ids` / `region` / `category` /
  `top_n: int Field(ge=1, le=1000)`).
- `BatchModelConfig`: `model_type ∈ {naive, seasonal_naive, moving_average,
  regression, lightgbm, xgboost, prophet_like}` + free-form `params: dict`.
- `BatchSubmitRequest`: `operation`, `scope`, `model_configs (min_length=1,
  max_length=10)`, `start_date` / `end_date` (`Field(strict=False)`), and
  forward-compat **`max_parallel`** + **`default_child_priority`** — accepted,
  validated, persisted, but ignored by the MVP runner.

---

## Backend Service Shape

### Slice layout (new)

Standard vertical slice — `app/features/batch/{__init__,models,schemas,service,
routes}.py` plus `tests/{conftest,test_models,test_schemas,test_service,test_routes,
test_routes_integration}.py`. The integration tests carry `@pytest.mark.integration`.

### Picker query (single-threaded MVP; SKIP LOCKED wired now)

The MVP picks one pending item per loop iteration:

```python
select(BatchJobItem)
  .where(BatchJobItem.batch_id == batch.batch_id,
         BatchJobItem.status == BatchItemStatus.PENDING.value)
  .order_by(BatchJobItem.priority.desc(),
            BatchJobItem.created_at.asc(),
            BatchJobItem.id.asc())   # bulk-insert tie-break
  .limit(1)
  .with_for_update(skip_locked=True)
```

`FOR UPDATE SKIP LOCKED` is a no-op with a single worker but means downstream-1
(parallel) and downstream-2 (priority) need no code-level retrofit. The partial
index `ix_batch_job_item_picker` covers this exact predicate + sort. With
`priority=0` on every MVP item the order collapses to pure `created_at` ASC —
identical to FIFO; the priority arm activates the moment downstream-2 lets
operators set non-zero values.

### Cross-slice integration

The runner does NOT import from another `app/features/<other>/` slice at module
scope. Any call into forecasting / backtesting / registry happens via lazy
in-method import per `docs/_base/ARCHITECTURE.md` § "Cross-slice read-only
import pattern" — precedent: `app/features/forecasting/service.py`.

`_execute_item` routes by `operation`:

- `train` / `predict` / `backtest` → build a `JobCreate`, call
  `JobService.create_job` (unchanged path), write `job.job_id` →
  `batch_job_item.child_job_id` and `job.run_id` → `child_run_id`. Metrics are
  read from `job.result` when `job_type=='backtest'` and shaped into the
  pinned JSONB.
- `train_backtest_register` → chained `train → backtest → register run`.
  Backtest metrics populate the JSONB; alias creation is **omitted** in MVP
  (champion promotion lives in downstream-4).

The runner is a thin orchestrator over the existing `JobService` contract — per-
item happy- and error-path test coverage already lives in `app/features/jobs/`.

### Settings

Append one field to `app/core/config.py:Settings`:
`batch_max_scope_expansion: int = Field(default=1000, ge=1, le=10000)` — hard
ceiling on the row count a single scope can resolve to; over-cap returns RFC 7807
422. Add `BATCH_MAX_SCOPE_EXPANSION=1000` to `.env.example`. Downstream-1 adds
its own `batch_global_max_parallel` + `batch_cancel_drain_timeout_seconds`.

---

## Frontend Touchpoints (MVP only)

Per `.claude/rules/ui-design.md` + `.claude/rules/shadcn-ui.md` — no hand-rolled
components, no new shadcn primitives the existing pages don't already use.

- `frontend/src/pages/visualize/batch.tsx` (**NEW**) — submit form
  (operation + scope + model_configs) + parent-status card + items table.
  Polls `GET /batch/{id}` every 2 s while parent `status ∈ {pending, running}`
  (mirrors `frontend/src/pages/explorer/job-detail.tsx`).
- `frontend/src/hooks/use-batches.ts` (**NEW**) — TanStack Query wrappers
  `useSubmitBatch`, `useBatch`, `useBatchItems`.
- `frontend/src/types/api.ts` — extend with `BatchJob`, `BatchJobItem`,
  `BatchSubmitRequest`, `BatchSubmitResponse`.
- `frontend/src/pages/ops.tsx` — 1-line nav entry.

Hold-points downstream PRPs claim — explicitly NOT in MVP: heatmap + promotion
panel (champion-and-heatmap); export CSV + retry buttons (export-and-retry);
max_parallel slider + cancel button (parallel-execution); priority dropdown +
history sheet (priority-queue).

---

## Test Plan

Per `.claude/rules/test-requirements.md`: every new module, public function, API
endpoint, ORM model, and migration ships with a test.

### Unit (no DB, `pytest -m "not integration"`)

- `test_models.py` — enum / CHECK-constraint coverage (committing `priority=7`
  raises `IntegrityError`).
- `test_schemas.py::test_submit_request_strict_mode_json_path` — calls
  `BatchSubmitRequest.model_validate({"start_date": "2026-01-01", ...})`, the
  JSON path FastAPI exercises (regression for `docs/_base/SECURITY.md` §
  "Pydantic v2 strict mode").
- `test_schemas.py::test_scope_top_revenue_requires_top_n` — `kind=top_revenue`
  with `top_n=None` rejects.
- `test_service.py` — scope expansion for each `BatchScope.kind`;
  `metrics_jsonb_shape_pinned` (writes exactly `{wape, smape, mae, bias,
  sample_size}`, no extras);  status-settlement matrix (`partial` on mixed,
  `failed` on all-fail, `completed` on all-pass);  `picker_query_uses_skip_locked`
  (compiled SQL contains `FOR UPDATE SKIP LOCKED` — regression for downstream-1/2).

### Integration (`pytest -m integration`, real Postgres)

- `test_routes_integration.py::test_submit_batch_happy_path` — 3-pair manual
  batch + `operation=backtest`; assert parent `completed_items=3` and every
  item's `metrics` JSONB carries the pinned five keys.
- `test_routes_integration.py::test_submit_batch_partial_failure` — one pair
  with no sales window → that item `failed` with `error_message`, parent
  settles `partial`.
- `test_routes_integration.py::test_scope_over_cap_returns_422` — RFC 7807 422
  body.
- `test_routes_integration.py::test_get_items_sort_by_allow_list` — unknown
  `sort_by` falls back silently to the default; never raises.
- `test_routes_integration.py::test_migration_partial_index_present` —
  `pg_indexes.indexdef` for `ix_batch_job_item_picker` contains
  `WHERE (status = 'pending')`. The downstream-2 picker depends on this exact
  predicate.

### Regression (the MVP must not touch other slices)

- `test_e2e_demo.py` — re-run unchanged. The batch slice MUST NOT register a
  router or migration touch that perturbs the demo pipeline.
- `app/features/jobs/tests/test_service.py` — re-run unchanged.
  `JobService.create_job` is consumed via lazy import; no edit to that file.
- `tests/test_docker_stack.py` — re-run unchanged. The new slice MUST NOT add a
  Compose-level dependency.

### Frontend (vitest)

- `frontend/src/pages/visualize/batch.test.tsx` — submit form validates
  `model_configs.length >= 1`, polls on `pending`/`running`, stops on terminal.
- `frontend/src/hooks/use-batches.test.ts` — TanStack Query mutation wires up
  with the right body shape.

### Validation gates

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
|------|------------|--------|------------|
| Pinned `metrics` shape misses a key a downstream consumer later needs. | Med | High | The four-doc consumer trace above is the audit; a sixth key MUST land via a new INITIAL + Pydantic schema change before the consumer ships. |
| Sequential execution on a 500-pair batch hangs the request task for minutes. | High | Med | `batch_max_scope_expansion` (default 1000, env-overridable) bounds the MVP worst case. The parallel-execution INITIAL is the structural fix. |
| Forward-compat columns (priority, max_parallel) drift from the downstream INITIALs that consume them. | Low | Med | The Coordination Matrix is the contract; any downstream PRP that changes a column type / default MUST update this INITIAL's matrix first. |
| Cross-slice import cycle (forecasting ↔ batch) at alembic cold-boot. | Med | High | Lazy in-method import per `docs/_base/ARCHITECTURE.md` § "Cross-slice read-only import pattern"; precedent: `app/features/forecasting/service.py`. |
| `batch` is not in `.claude/rules/commit-format.md` scope allow-list. | Confirmed | Low | The PRP MUST add it in the same PR. Until then commits use the cross-cutting `feat(api,ui): ...` form. |
| `_execute_item` calls `JobService.create_job` synchronously; one slow item blocks the whole batch. | High | Med | Accepted in MVP. `batch_max_scope_expansion` caps the blast radius; the parallel-execution INITIAL removes the bottleneck. |

---

## Open Questions (for the PRP author)

- [ ] **Q1 — `train_backtest_register` alias side-effect.** The operation name
  implies an alias write, but alias-naming policy is owned by
  `INITIAL-batch-champion-and-heatmap`. Recommendation: MVP registers the
  run (`model_run.status=success`) but does NOT create an alias — that is
  the HITL-gated `promote_champions` tool's job.
- [ ] **Q2 — `scope.kind=top_revenue` resolution.** Reuse `AnalyticsService`
  via lazy import (it owns the SQL) vs. inline the aggregate in the batch
  slice. Recommendation: lazy-import — preserves the vertical-slice
  invariant.
- [ ] **Q3 — Per-item `params` validation at submit time.** Recommendation:
  yes — validate against the same Pydantic models `JobService` already uses
  (`TrainRequest` etc.) so a 500-pair batch fails fast on a typo, not an
  hour into execution.
- [ ] **Q4 — `result_summary` JSONB shape.** Recommendation:
  `{total, completed, failed, pending, running, cancelled, attempts_used: 0,
  by_model_type: { ... }}`. The `attempts_used` key is `0` in MVP;
  downstream-3 populates it.

---

## References

**Source / precedents (verified):**
`docs/optional-features/06-portfolio-forecasting-batch-runner.md`;
`app/features/jobs/{models,schemas,service,routes}.py` (the executor pattern,
the 202-Accepted convention, the `_JOB_SORT_COLUMNS` allow-list);
`app/features/forecasting/service.py` (lazy-import precedent for the cross-slice
cycle); `app/features/registry/service.py:421-495` (`create_alias`, consumed
indirectly via Q1); `app/features/backtesting/metrics.py` (WAPE/sMAPE/MAE/bias
definitions that populate the pinned `metrics` JSONB);
`app/core/{problem_details,database,config,logging}.py`; `app/shared/models.py`
(`TimestampMixin`); `frontend/src/pages/explorer/job-detail.tsx` (polling);
`frontend/src/hooks/use-jobs.ts` (TanStack Query mutation pattern).
Rules: `.claude/rules/{product-vision,commit-format,security-patterns,
test-requirements,ui-design,shadcn-ui}.md`. Base docs: `docs/_base/{ARCHITECTURE,
API_CONTRACTS,SECURITY,PIPELINE_CONTRACT,DOMAIN_MODEL,RULES}.md`. Downstream
INITIALs read for the Cross-Slice Coordination Matrix:
`PRPs/INITIAL/INITIAL-batch-{parallel-execution,priority-queue,export-and-retry,
champion-and-heatmap}.md`.

**NEW files this plan introduces:**

- `alembic/versions/<rev>_create_batch_tables.py`
- `app/features/batch/{__init__,models,schemas,service,routes}.py` + matching `tests/`
- `frontend/src/pages/visualize/batch.tsx` (+ `.test.tsx`)
- `frontend/src/hooks/use-batches.ts` (+ `.test.ts`)

**EXTEND (one or two lines each):**

`app/main.py` (register router); `frontend/src/types/api.ts` (Batch* types);
`frontend/src/pages/ops.tsx` (nav entry); `app/core/config.py`
(`batch_max_scope_expansion` Setting); `.env.example`
(`BATCH_MAX_SCOPE_EXPANSION=1000`); `.claude/rules/commit-format.md` (add
`batch` to scope allow-list).

---

## Acceptance Summary

A reviewer landing the PRP should be able to confirm, in order:

1. `alembic upgrade head` on a fresh Postgres creates both tables + every column,
   CHECK constraint, and index in the Coordination Matrix — and the partial
   index predicate is exactly `WHERE (status = 'pending')`.
2. `POST /batch/forecasting` with a 3-pair manual backtest scope returns 202 and
   settles `completed` with `completed_items=3`; every item's `metrics` JSONB
   carries exactly `{wape, smape, mae, bias, sample_size}`.
3. `grep -rn "for_update" app/features/batch/service.py` returns at least one
   line with `skip_locked=True`.
4. `Settings.agent_require_approval` gains no entries (MVP exposes no mutating
   agent tools); `.claude/rules/commit-format.md` lists `batch` in the scope
   allow-list.
5. `app/features/jobs/`, `app/features/forecasting/`, and the demo e2e tests are
   untouched; all five validation-gate commands run green.
