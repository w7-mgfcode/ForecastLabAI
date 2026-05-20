name: "PRP-33 — Batch Runner MVP (portfolio forecasting orchestration layer)"
description: |
  Ships the minimum viable orchestration layer above forecasting + backtesting +
  registry. One `batch_job` row fans out into N `batch_job_item` rows; each item
  is executed sequentially by delegating to the existing `JobService.create_job`
  path; per-item metrics land in a pinned JSONB shape; parent status settles to
  `completed | failed | partial`. The MVP is the unblocker for four downstream
  Full-Version INITIALs (parallel-execution, priority-queue, export-and-retry,
  champion-and-heatmap) — every column those downstreams claim as MVP-owned is
  shipped in this PRP, plus the partial picker index and `FOR UPDATE SKIP
  LOCKED` so no downstream needs a code-level picker retrofit.

**Tracking issue:** #277
**Source INITIAL:** `PRPs/INITIAL/INITIAL-batch-runner-mvp.md` (493 lines, merged on `dev` via PR #278)
**Source feature doc:** `docs/optional-features/06-portfolio-forecasting-batch-runner.md` § "MVP Scope"
**Depends on:** none — this slice is the unblocker.
**Blocks:** `INITIAL-batch-parallel-execution`, `INITIAL-batch-priority-queue`, `INITIAL-batch-export-and-retry`, `INITIAL-batch-champion-and-heatmap` (all four declare `depends_on: batch-runner-mvp`).
**Successor PRPs:** PRP-34/35/36/37 (the four downstream INITIALs, authored only after this PRP merges).

---

## Goal

A new vertical slice at `app/features/batch/` exposes three endpoints (`POST /batch/forecasting`, `GET /batch/{batch_id}`, `GET /batch/{batch_id}/items`) that submit, observe, and list a portfolio batch. The runner expands a `BatchScope` into N `batch_job_item` rows, executes them sequentially via lazy-import delegation to `JobService.create_job`, writes a pinned five-key metrics JSONB per successful item, and settles the parent to `completed | failed | partial`. The migration ships every column the four downstream INITIALs need MVP-owned plus a partial picker index. A placeholder page at `frontend/src/pages/visualize/batch.tsx` polls the parent status and renders an items table — **no slider, no cancel button, no retry, no heatmap, no promotion panel** (each downstream PRP owns one of those surfaces).

## Why

- **Unblocks four downstream Full-Version features** that sit idle without a parent/child orchestration surface — the Cross-Slice Coordination Matrix in the INITIAL traces every column and every JSONB key per consumer.
- **Removes the "200 round-trips for a regional retrain" pain** without pre-judging the parallel-execution, priority-queue, retry, or champion-selection designs.
- **Stays single-host and pre-1.0 compliant.** No managed queue, no Redis, no Celery; the runner is a thin orchestrator over the existing `JobService` contract. Vertical-slice boundaries stay intact via the lazy-import precedent.
- **Preserves vertical-slice purity.** The new slice does not import another `app/features/<other>/*` at module scope; every cross-slice call goes through a lazy in-method import (precedent: `app/features/forecasting/service.py:786-787`).

## What

Submit a batch:

```bash
curl -X POST http://localhost:8123/batch/forecasting \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "backtest",
    "scope": {"kind": "manual", "store_ids": [1, 2], "product_ids": [1, 2, 3]},
    "model_configs": [{"model_type": "naive", "params": {}}],
    "start_date": "2025-01-01",
    "end_date": "2025-06-30"
  }'
# 202 Accepted, ProblemDetail on 4xx
```

The runner expands manual scope to `2 × 3 = 6` pairs × 1 model = 6 items; each item runs sequentially in-process; the response carries the parent record after settlement. Items are independently observable via `GET /batch/{batch_id}/items` (allow-listed `sort_by ∈ {created_at, completed_at, status, priority}`).

### Success Criteria

- [ ] `alembic upgrade head` on a fresh `docker-compose` Postgres creates `batch_job` + `batch_job_item` with every column, CHECK constraint, and index in the matrix below. The partial picker index predicate matches **exactly** `WHERE (status = 'pending')`.
- [ ] `POST /batch/forecasting` with a 3-pair manual `operation=backtest` scope returns 202 and settles `completed` with `completed_items=3`. Every item's `metrics` JSONB carries exactly `{wape, smape, mae, bias, sample_size}` — no extras, no missing.
- [ ] `grep -rn "for_update" app/features/batch/service.py` returns at least one line with `skip_locked=True`.
- [ ] `Settings.agent_require_approval` gains zero entries; `.claude/rules/commit-format.md` lists `batch` in the scope allow-list.
- [ ] `app/features/jobs/`, `app/features/forecasting/`, and `tests/test_e2e_demo.py` files are unmodified.
- [ ] All five validation gate commands run green: `ruff check`, `ruff format --check`, `mypy app/`, `pyright app/`, `pytest -v -m "not integration"`, `pytest -v -m integration`, frontend `pnpm tsc --noEmit && pnpm lint && pnpm test --run`.

## All Needed Context

### Documentation & References

```yaml
# MUST READ - load these before implementing
- file: PRPs/INITIAL/INITIAL-batch-runner-mvp.md
  why: 493-line source spec; the Cross-Slice Coordination Matrix (§ "the load-bearing section") pins every column shipped vs. deferred and the JSONB metrics shape; the Test Plan enumerates the exact tests this PRP demands. Read end-to-end.

- file: PRPs/INITIAL/INITIAL-batch-champion-and-heatmap.md
  why: Downstream-4. Reads the pinned `metrics` JSONB shape. Confirms which keys (`wape` primary, `smape` tie-break, `mae`/`bias` heatmap, `sample_size` tooltip+filter) drive what.

- file: PRPs/INITIAL/INITIAL-batch-parallel-execution.md
  why: Downstream-1. Demands `batch_job.{max_parallel, running_items, cancelled_items}` ship MVP-owned (so the parallel runner needs no retrofit migration on a populated table). Also demands `FOR UPDATE SKIP LOCKED` wired now.

- file: PRPs/INITIAL/INITIAL-batch-priority-queue.md
  why: Downstream-2. Demands `batch_job_item.priority` and the partial picker index `ix_batch_job_item_picker (batch_id, status, priority, created_at) WHERE status = 'pending'` ship MVP-owned.

- file: PRPs/INITIAL/INITIAL-batch-export-and-retry.md
  why: Downstream-3. Confirms `attempts`/`last_attempt_at`/`parent_item_id` are NOT in the MVP — they ship with the retry PRP's own forward-only migration.

- file: app/features/jobs/models.py
  why: Direct precedent for `Job` ORM model (`String(32)` job_id, `JSONB` params/result, `String(2000)` error_message, `String(100)` error_type, `CheckConstraint` on status). `batch_job_item` mirrors this 1:1 for the per-pair fields.

- file: app/features/jobs/schemas.py
  why: Direct precedent for `JobCreate`/`JobResponse`. `BatchSubmitRequest` / `BatchSubmitResponse` mirror the 202-Accepted convention.

- file: app/features/jobs/routes.py
  why: Router pattern — `APIRouter(prefix="/jobs", tags=["jobs"])`, `status_code=status.HTTP_202_ACCEPTED`, per-request `JobService()` instantiation, sort_by allow-list documented in the OpenAPI description.

- file: app/features/jobs/service.py
  why: `JobService.create_job` (lines 150-191) is the delegation target; `_execute_job` (lines 330-407) is the dispatch pattern this PRP copies; `_JOB_SORT_COLUMNS` (lines 54-59) is the sort-allow-list pattern.

- file: app/features/forecasting/service.py
  why: Lazy cross-slice import precedent. Lines 700-701 lazy-import `RegistryService`; lines 786-787 lazy-import `JobService`. **The batch runner MUST follow this pattern verbatim** — module-scope cross-slice imports close an alembic cold-boot cycle (memory `[[computed-field-cross-slice-cycle]]`).

- file: alembic/versions/a2f7b3c8d901_create_model_registry_tables.py
  why: Direct precedent for a two-table migration with JSONB columns, CHECK constraints, and GIN indexes. Mirror the `op.create_table` + `sa.PrimaryKeyConstraint` + `sa.CheckConstraint` shape verbatim.

- file: alembic/versions/f7a8b9c0d123_add_exogenous_signal_and_sales_returns_tables.py
  why: Partial-index precedent. Lines 80-93 show `op.create_index(..., postgresql_where=sa.text("..."))`. The batch migration MUST use this exact shape for `ix_batch_job_item_picker`.

- file: app/core/problem_details.py
  why: RFC 7807 helpers. Use `problem_response(status, title, detail, error_code)` (line 161) for all 4xx returns. Error codes lookup table at line 26 — `VALIDATION_ERROR` (422), `BAD_REQUEST` (400), `NOT_FOUND` (404), `UNPROCESSABLE_ENTITY` (422).

- file: app/core/config.py
  why: `Settings` class via pydantic-settings. Append `batch_max_scope_expansion: int = Field(default=1000, ge=1, le=10000)` to the body; mirror the `jobs_retention_days` placement (line 119).

- file: app/main.py
  why: Router wiring location. The `batch_router` import goes between `agents_ws_router` and `seeder_router` (line 32); `app.include_router(batch_router)` goes between `jobs_router` (line 140) and `ingest_router` (line 141).

- file: app/core/tests/test_strict_mode_policy.py
  why: **Load-bearing AST-walker invariant.** Scans `app/features/**/schemas.py` for any `ConfigDict(strict=True)` model whose fields are typed `date | datetime | time | UUID | Decimal` without a matching `Field(strict=False, ...)` override. `BatchSubmitRequest.{start_date, end_date}` and any nested `date` field MUST add the override or CI fails.

- file: app/features/featuresets/tests/test_leakage.py
  why: Load-bearing leakage spec the linter pattern above mirrors. Never weaken either to make a feature pass.

- file: frontend/src/hooks/use-jobs.ts
  why: TanStack Query mutation precedent. `use-batches.ts` mirrors the `useSubmitBatch`/`useBatch`/`useBatchItems` triad.

- file: frontend/src/pages/explorer/job-detail.tsx
  why: Polling-while-pending precedent. The new `visualize/batch.tsx` polls `GET /batch/{id}` every 2 s while parent `status ∈ {pending, running}`, mirroring this file's `useQuery({ refetchInterval })` pattern.

- file: frontend/src/pages/visualize/forecast.tsx
  why: Sibling page in `visualize/`. Mirror the shell layout — no new shadcn primitives the existing pages don't use (`.claude/rules/shadcn-ui.md`).

- url: https://docs.sqlalchemy.org/en/20/orm/queryguide/query.html#sqlalchemy.orm.Query.with_for_update
  section: "skip_locked=True"
  why: Pessimistic-lock semantics with skip-locked. Verified at runtime: SQLAlchemy 2.0.46 `select(...).with_for_update(skip_locked=True)` signature `(*, nowait, read, of, skip_locked, key_share)`.

- url: https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.create_index
  section: "postgresql_where"
  why: Partial index creation via dialect-specific kwarg. Verified by existing usage in alembic/versions/f7a8b9c0d123_*.py.

- url: https://docs.pydantic.dev/latest/concepts/strict_mode/#field-level-strict
  section: "Per-field strict override"
  why: `Field(strict=False)` overrides `ConfigDict(strict=True)` for a single field, letting Pydantic coerce JSON-native strings (ISO dates, UUIDs) into Python types. Verified at runtime — `BaseModel(model_config=ConfigDict(strict=True)).model_validate({"d": "2026-01-01"})` parses the date correctly with `Field(strict=False)`.

- docfile: docs/_base/SECURITY.md
  section: "Pydantic v2 strict mode on FastAPI request bodies"
  why: The policy the strict-mode linter codifies; the batch slice MUST follow it.

- docfile: docs/_base/ARCHITECTURE.md
  section: "Cross-slice read-only import pattern"
  why: Authoritative on lazy in-method imports for cross-slice calls.

- docfile: docs/_base/API_CONTRACTS.md
  section: "HTTP Endpoints"
  why: 202 Accepted convention + RFC 7807 4xx body shape.

- docfile: docs/_base/RULES.md
  section: "Hard Rules"
  why: Forward-only migrations; never weaken the leakage / strict-mode specs; no managed-cloud SDK; no AI co-author trailer; the merge gates.

- docfile: .claude/rules/commit-format.md
  why: The PR MUST add `batch` to the scope allow-list table (between `jobs` and `db`).
```

### Current Codebase Tree (relevant slices)

```bash
app/
├── core/
│   ├── config.py            # Settings: append batch_max_scope_expansion here
│   ├── database.py          # AsyncSession via get_db
│   ├── problem_details.py   # problem_response() helper for RFC 7807
│   └── tests/test_strict_mode_policy.py   # AST-walker invariant — must stay green
├── features/
│   ├── jobs/                # Precedent slice — JobService.create_job is the delegation target
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── service.py       # _execute_job dispatch (lines 330-407), _JOB_SORT_COLUMNS
│   │   └── routes.py
│   ├── forecasting/
│   │   └── service.py       # Lazy-import precedent (lines 700-701, 786-787)
│   └── registry/
│       └── service.py       # Status state machine precedent
└── main.py                  # Router wiring — add batch_router here

alembic/versions/
├── a2f7b3c8d901_create_model_registry_tables.py   # Two-table migration precedent
└── f7a8b9c0d123_add_exogenous_signal_and_sales_returns_tables.py   # Partial-index precedent

frontend/src/
├── hooks/use-jobs.ts                      # TanStack Query mutation precedent
└── pages/explorer/job-detail.tsx          # Polling-while-pending precedent
```

### Desired Codebase Tree (files to add/extend)

```bash
# NEW (this PRP)
alembic/versions/<rev>_create_batch_tables.py             # ONE migration, creates both tables + all indexes

app/features/batch/
├── __init__.py
├── models.py                  # BatchJob, BatchJobItem, BatchStatus, BatchItemStatus, BatchOperation enums
├── schemas.py                 # BatchScope, BatchModelConfig, BatchSubmitRequest, BatchSubmitResponse, BatchItemResponse, BatchListResponse
├── service.py                 # BatchService: submit, get, list_items, expand_scope, _pick_next, _execute_item, _settle
├── routes.py                  # /batch/forecasting, /batch/{id}, /batch/{id}/items
└── tests/
    ├── __init__.py
    ├── conftest.py            # Fixtures: db_session, sample_batch_payload
    ├── test_models.py         # Enum + CHECK-constraint coverage
    ├── test_schemas.py        # Strict-mode JSON path; top_revenue requires top_n
    ├── test_service.py        # Scope expansion; metrics shape pinned; settlement matrix; SKIP LOCKED in compiled SQL
    └── test_routes_integration.py  # Real-Postgres: happy 3-pair; partial-failure; over-cap 422; sort allow-list; partial index present

frontend/src/
├── pages/visualize/batch.tsx           # Placeholder page (submit + poll + items table only)
├── pages/visualize/batch.test.tsx      # Submit form validates >=1 model_config; polls then stops on terminal
├── hooks/use-batches.ts                # useSubmitBatch, useBatch, useBatchItems
└── hooks/use-batches.test.ts           # Mutation body shape

# EXTENDED (one or two lines each)
app/main.py                                   # import + include_router for batch_router
app/core/config.py                            # batch_max_scope_expansion Setting
.env.example                                  # BATCH_MAX_SCOPE_EXPANSION=1000
frontend/src/types/api.ts                     # BatchJob, BatchJobItem, BatchSubmitRequest, BatchSubmitResponse types
frontend/src/pages/ops.tsx                    # 1-line nav entry (or wherever the visualize nav lives)
.claude/rules/commit-format.md                # Add | `batch` | `app/features/batch/**` | row between `jobs` and `db`
```

### Known Gotchas — runtime-verified library quirks + repo invariants

```python
# ── 1. SQLAlchemy 2.0 `with_for_update(skip_locked=True)` — VERIFIED ──
# Verification command (run before locking the PRP):
#   uv run python -c "from sqlalchemy import select; import inspect; print(inspect.signature(select(None).with_for_update))"
# Output (SQLAlchemy 2.0.46):
#   (*, nowait: 'bool' = False, read: 'bool' = False, of: 'Optional[_ForUpdateOfArgument]' = None,
#    skip_locked: 'bool' = False, key_share: 'bool' = False) -> 'Self'
# CRITICAL: `skip_locked=True` is a no-op when only one worker is running (the MVP), but compiles to
# `FOR UPDATE SKIP LOCKED` SQL — load-bearing for downstream-1 (parallel) and downstream-2 (priority).
# DO NOT remove the kwarg "because it does nothing yet" — the integration test asserts on it.

# ── 2. Alembic partial-index syntax — VERIFIED ──
# Existing precedent: alembic/versions/f7a8b9c0d123_*.py:80-93 uses
#   op.create_index("uq_exogenous_signal_global", "exogenous_signal", [...],
#                   unique=True, postgresql_where=sa.text("is_global = true"))
# For ix_batch_job_item_picker, the predicate MUST be EXACTLY:
#   postgresql_where=sa.text("status = 'pending'")
# (note the single-quoted string literal — Postgres stores the WHERE clause as plain text in
# pg_indexes.indexdef as `WHERE (status = 'pending'::text)` after parse; the integration test
# matches the un-cast form via substring containment, not regex equality.)

# ── 3. Pydantic v2 ConfigDict(strict=True) + JSON-native types — POLICY LINTED ──
# app/core/tests/test_strict_mode_policy.py is an AST walker that scans every
# app/features/**/schemas.py model with `ConfigDict(strict=True)` for any field typed
# `date | datetime | time | UUID | Decimal` without a `Field(strict=False, ...)` override.
# FAILING THE LINTER FAILS CI. For BatchSubmitRequest:
#   class BatchSubmitRequest(BaseModel):
#       model_config = ConfigDict(strict=True)
#       start_date: date = Field(strict=False, description="...")
#       end_date: date = Field(strict=False, description="...")
# The baseline guard inside the linter test enforces 4 known-good models — touching the linter
# to "fix it" is forbidden by docs/_base/RULES.md.
# Verification command:
#   uv run python -c "from pydantic import BaseModel, Field, ConfigDict; from datetime import date
#   class M(BaseModel):
#       model_config = ConfigDict(strict=True)
#       d: date = Field(strict=False)
#   print(M.model_validate({'d': '2026-01-01'}))"

# ── 4. Cross-slice import cycle at alembic cold-boot — REQUIRES LAZY IMPORT ──
# Precedent: app/features/forecasting/service.py:786-787 inside
#   `get_feature_metadata_for_job` — `from app.features.jobs.service import JobService` is
# imported INSIDE the method, NOT at module scope. The batch slice MUST follow this pattern
# for every call into JobService / ForecastingService / RegistryService / AnalyticsService.
# Memory `[[computed-field-cross-slice-cycle]]` documents the cycle this avoids.
# Read-only data-contract imports (ORM model classes) MAY be at module scope IFF they carry the
# explicit `# read-only data contract — see module docstring` comment, per the
# explainability/service.py:56-57 precedent.

# ── 5. `test_e2e_demo.py` non-regression — DEMO PIPELINE MUST STAY GREEN ──
# The batch slice MUST NOT touch app/features/jobs/, app/features/forecasting/, or perturb the
# demo pipeline in any way. The validation gates re-run tests/test_e2e_demo.py.

# ── 6. JSONB metrics shape is PINNED across this PRP + four downstream PRPs ──
# Adding a sixth key (or renaming a key) is a breaking change that requires a new INITIAL doc
# + a Pydantic schema bump BEFORE any downstream consumer ships. The keys are: wape (champion
# primary), smape (champion tie-break), mae (heatmap optional), bias (heatmap diverging
# palette), sample_size (heatmap tooltip + champion filter). A key MAY be null only when the
# underlying fold produces NaN (zero-actuals window).

# ── 7. commit-format scope `batch` is NOT YET in the allow-list ──
# .claude/hooks/check-commit-format.sh rejects unknown scopes. This PR MUST add the row
#     | `batch`      | `app/features/batch/**` |
# to .claude/rules/commit-format.md (between `jobs` and `db` — the boundary between feature
# scopes and infra scopes). Without it, every commit on this PRP's branch fails the hook.

# ── 8. Settings.agent_require_approval is FROZEN in MVP ──
# Current value: ["create_alias", "archive_run", "save_scenario"]. The batch slice MUST NOT
# add a mutating agent tool. Future downstream PRPs add: `promote_champions` (downstream-4
# REQUIRED), optionally `cancel_batch` (downstream-1), optionally `retry_failed_items`
# (downstream-3, currently deferred).

# ── 9. `op.f()` index wrapper is required for default-named indexes ──
# Precedent: a2f7b3c8d901_*.py uses `op.create_index(op.f("ix_model_run_run_id"), ...)` for
# simple single-column indexes. Custom-named indexes (the partial one, the GIN one) skip op.f.
# Mirror this convention.

# ── 10. The `params` JSONB on batch_job_item is PER-ITEM, frozen at expansion time ──
# Do NOT mutate `params` after the item is inserted; the runner reads from it on every
# `_execute_item` call. If you need a different shape per JobType, build it at expansion and
# freeze it.
```

## Implementation Blueprint

### Data Models — ORM (`app/features/batch/models.py`)

```python
# Mirror app/features/jobs/models.py shape: TimestampMixin + Base, str Enums,
# CHECK constraints in __table_args__, Index() for composites + GIN.

class BatchStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"          # >=1 success + >=1 failure
    CANCELLED = "cancelled"       # Reserved for downstream-1; MVP never writes

class BatchOperation(str, Enum):
    TRAIN = "train"
    PREDICT = "predict"
    BACKTEST = "backtest"
    TRAIN_BACKTEST_REGISTER = "train_backtest_register"

class BatchItemStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"       # Reserved for downstream-1

# Transition map mirrors VALID_JOB_TRANSITIONS in jobs/models.py:59-65.

class BatchJob(TimestampMixin, Base):
    __tablename__ = "batch_job"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)   # uuid hex
    operation: Mapped[str] = mapped_column(String(30), index=True)
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    model_configs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=BatchStatus.PENDING.value, index=True)
    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    running_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)        # downstream-1
    cancelled_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)      # downstream-1
    max_parallel: Mapped[int] = mapped_column(Integer, default=4, nullable=False)         # downstream-1 (MVP ignores)
    default_child_priority: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)  # downstream-2 (MVP NORMAL only)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'partial', 'cancelled')",
            name="ck_batch_job_valid_status",
        ),
        CheckConstraint(
            "operation IN ('train', 'predict', 'backtest', 'train_backtest_register')",
            name="ck_batch_job_valid_operation",
        ),
        CheckConstraint(
            "default_child_priority BETWEEN -1 AND 2",
            name="ck_batch_job_priority_band",
        ),
        Index("ix_batch_job_status_created", "status", "created_at"),
    )

class BatchJobItem(TimestampMixin, Base):
    __tablename__ = "batch_job_item"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    batch_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("batch_job.batch_id", ondelete="CASCADE"), index=True
    )
    store_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    model_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default=BatchItemStatus.PENDING.value, index=True)
    priority: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)        # downstream-2 (MVP NORMAL only)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    child_job_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    child_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_batch_job_item_valid_status",
        ),
        CheckConstraint(
            "priority BETWEEN -1 AND 2",
            name="ck_batch_job_item_priority_band",
        ),
        Index("ix_batch_job_item_batch_status", "batch_id", "status"),
        Index("ix_batch_job_item_metrics_gin", "metrics", postgresql_using="gin"),
        # partial picker index created in the migration (postgresql_where) — NOT here, because
        # SQLAlchemy Index() lacks a portable partial-predicate kwarg. The migration owns it.
    )
```

### Pydantic schemas (`app/features/batch/schemas.py`)

```python
# Every request body: ConfigDict(strict=True) + Field(strict=False) on date/datetime/UUID.
# Mirror app/features/jobs/schemas.py response shape.

class BatchScopeKind(str, Enum):
    MANUAL = "manual"
    REGION = "region"
    CATEGORY = "category"
    TOP_REVENUE = "top_revenue"
    ALL = "all"

class BatchScope(BaseModel):
    model_config = ConfigDict(strict=True)
    kind: BatchScopeKind
    store_ids: list[int] | None = Field(default=None, description="Required if kind=manual")
    product_ids: list[int] | None = Field(default=None, description="Required if kind=manual")
    region: str | None = Field(default=None, description="Required if kind=region")
    category: str | None = Field(default=None, description="Required if kind=category")
    top_n: int | None = Field(default=None, ge=1, le=1000, description="Required if kind=top_revenue")

    @model_validator(mode="after")
    def _check_kind_consistency(self) -> "BatchScope":
        # MANUAL requires both store_ids and product_ids
        # REGION requires region; CATEGORY requires category; TOP_REVENUE requires top_n.
        # ALL requires none. Reject mismatched payloads with ValueError -> 422 RFC 7807.
        ...

VALID_MODEL_TYPES = {
    "naive", "seasonal_naive", "moving_average", "regression",
    "lightgbm", "xgboost", "prophet_like",
}

class BatchModelConfig(BaseModel):
    model_config = ConfigDict(strict=True)
    model_type: Literal["naive", "seasonal_naive", "moving_average",
                         "regression", "lightgbm", "xgboost", "prophet_like"]
    params: dict[str, Any] = Field(default_factory=dict)

class BatchSubmitRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    operation: BatchOperation
    scope: BatchScope
    model_configs: list[BatchModelConfig] = Field(min_length=1, max_length=10)
    start_date: date = Field(strict=False, description="YYYY-MM-DD")
    end_date: date = Field(strict=False, description="YYYY-MM-DD")
    # Forward-compat — accepted, validated, persisted, ignored by MVP runner.
    max_parallel: int = Field(default=4, ge=1, le=64)
    default_child_priority: int = Field(default=0, ge=-1, le=2)

class BatchItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    item_id: str
    batch_id: str
    store_id: int
    product_id: int
    model_type: str
    status: BatchItemStatus
    priority: int
    metrics: dict[str, Any] | None
    child_job_id: str | None
    child_run_id: str | None
    error_message: str | None
    error_type: str | None
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    created_at: datetime
    updated_at: datetime

class BatchSubmitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    batch_id: str
    operation: BatchOperation
    status: BatchStatus
    total_items: int
    completed_items: int
    failed_items: int
    running_items: int
    cancelled_items: int
    started_at: datetime | None
    completed_at: datetime | None
    result_summary: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

class BatchItemListResponse(BaseModel):
    items: list[BatchItemResponse]
    total: int
    page: int
    page_size: int
```

### Service layer (`app/features/batch/service.py`)

Picker query, single-threaded MVP, `FOR UPDATE SKIP LOCKED` wired:

```python
# Pseudocode — full impl mirrors app/features/jobs/service.py:JobService shape.

_BATCH_ITEM_SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "created_at":   BatchJobItem.created_at,
    "completed_at": BatchJobItem.completed_at,
    "status":       BatchJobItem.status,
    "priority":     BatchJobItem.priority,
}

# Pinned metrics keys — the test_metrics_jsonb_shape_pinned regression locks this exact list.
_METRICS_KEYS: tuple[str, ...] = ("wape", "smape", "mae", "bias", "sample_size")

class BatchService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def submit(self, db: AsyncSession, req: BatchSubmitRequest) -> BatchSubmitResponse:
        # 1. Lazy import — break the alembic cold-boot cycle.
        # 2. Expand scope to (store_id, product_id, model_type) triples.
        pairs = await self._expand_scope(db, req.scope)
        triples = [(s, p, mc) for (s, p) in pairs for mc in req.model_configs]
        if len(triples) > self.settings.batch_max_scope_expansion:
            # RFC 7807 422 via problem_response. Bubble as HTTPException(422, detail=...)
            # mapped to RFC 7807 by app/core/exceptions.py.
            raise UnprocessableEntityError(...)

        # 3. Insert parent + N children in one transaction.
        batch = BatchJob(
            batch_id=uuid.uuid4().hex,
            operation=req.operation.value,
            scope=req.scope.model_dump(mode="json"),
            model_configs=[mc.model_dump(mode="json") for mc in req.model_configs],
            status=BatchStatus.PENDING.value,
            total_items=len(triples),
            params=req.model_dump(mode="json"),
            default_child_priority=req.default_child_priority,
            max_parallel=req.max_parallel,
        )
        db.add(batch)
        for store_id, product_id, mc in triples:
            item = BatchJobItem(
                item_id=uuid.uuid4().hex,
                batch_id=batch.batch_id,
                store_id=store_id,
                product_id=product_id,
                model_type=mc.model_type,
                priority=req.default_child_priority,
                params=self._frozen_item_params(req, store_id, product_id, mc),
            )
            db.add(item)
        await db.commit()

        # 4. Settle parent to running, loop the picker, settle.
        batch.status = BatchStatus.RUNNING.value
        batch.started_at = datetime.now(UTC)
        await db.commit()

        while True:
            item = await self._pick_next(db, batch.batch_id)
            if item is None:
                break
            await self._execute_item(db, item)

        await self._settle(db, batch)
        await db.refresh(batch)
        return BatchSubmitResponse.model_validate(batch)

    async def _pick_next(self, db: AsyncSession, batch_id: str) -> BatchJobItem | None:
        """Single-threaded MVP picker. SKIP LOCKED wired now — no-op for one worker but
        load-bearing for downstream-1/-2 (no code retrofit needed when those land)."""
        stmt = (
            select(BatchJobItem)
            .where(
                BatchJobItem.batch_id == batch_id,
                BatchJobItem.status == BatchItemStatus.PENDING.value,
            )
            .order_by(
                BatchJobItem.priority.desc(),
                BatchJobItem.created_at.asc(),
                BatchJobItem.id.asc(),                  # bulk-insert tie-break
            )
            .limit(1)
            .with_for_update(skip_locked=True)          # ← VERIFIED via SQLAlchemy 2.0.46
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    async def _execute_item(self, db: AsyncSession, item: BatchJobItem) -> None:
        # Lazy cross-slice import — precedent forecasting/service.py:786-787.
        from app.features.jobs.schemas import JobCreate
        from app.features.jobs.service import JobService

        item.status = BatchItemStatus.RUNNING.value
        item.started_at = datetime.now(UTC)
        await db.commit()
        try:
            if item.params["operation"] in ("train", "predict", "backtest"):
                # Single-step ops -> one JobCreate call.
                job = await JobService().create_job(
                    db=db,
                    job_create=JobCreate(job_type=item.params["operation"], params=item.params["job_params"]),
                )
                item.child_job_id = job.job_id
                item.child_run_id = job.run_id
                if job.status == JobStatus.FAILED:
                    raise RuntimeError(job.error_message or "child job failed")
                item.metrics = self._shape_metrics(job)
            else:
                # train_backtest_register -> chained 3-step (alias creation OMITTED per Q1).
                ...

            item.status = BatchItemStatus.COMPLETED.value
        except Exception as exc:
            item.status = BatchItemStatus.FAILED.value
            item.error_message = str(exc)[:2000]
            item.error_type = type(exc).__name__
        item.completed_at = datetime.now(UTC)
        item.duration_ms = int((item.completed_at - item.started_at).total_seconds() * 1000)
        await db.commit()
        # structlog: batch.item_started / batch.item_completed / batch.item_failed at each step.

    def _shape_metrics(self, job: JobResponse) -> dict[str, Any] | None:
        """Coerce JobResponse.result into the pinned five-key JSONB.

        CRITICAL: returns EXACTLY {wape, smape, mae, bias, sample_size} or None.
        Any value MAY be None if the underlying fold produced NaN (zero-actuals window)."""
        if job.job_type != JobType.BACKTEST or not job.result:
            # For predict-only items the values come from the most recent backtest of the same
            # run_id if one exists; if no metrics exist the item ships metrics=null (champion
            # logic excludes it via unresolved_pairs).
            return None
        agg = job.result.get("aggregated_metrics", {})
        return {
            "wape": agg.get("wape_mean"),
            "smape": agg.get("smape_mean"),
            "mae": agg.get("mae_mean"),
            "bias": agg.get("bias_mean"),
            "sample_size": sum(f.get("sample_size", 0) for f in job.result.get("fold_metrics", []))
            or job.result.get("n_observations"),
        }

    async def _settle(self, db: AsyncSession, batch: BatchJob) -> None:
        # Aggregate per-status counts via a single GROUP BY on batch_job_item.
        # status -> {completed, failed, partial (>=1 success + >=1 failure)}
        # MVP never writes cancelled here (downstream-1 owns it).
        ...

    async def _expand_scope(self, db: AsyncSession, scope: BatchScope) -> list[tuple[int, int]]:
        # MANUAL: cartesian product of store_ids x product_ids
        # REGION: lazy-import dimensions/service to query stores filtered by region; cross all products
        # CATEGORY: lazy-import dimensions/service to query products filtered by category; cross all stores
        # TOP_REVENUE: lazy-import analytics/service (preserves vertical-slice invariant) to rank by revenue
        # ALL: cartesian product of all dimensions.
        ...

    def _frozen_item_params(self, req: BatchSubmitRequest, store_id: int, product_id: int, mc: BatchModelConfig) -> dict[str, Any]:
        """Build the per-item JSONB args frozen at expansion time. Maps operation -> JobCreate.params shape."""
        return {
            "operation": req.operation.value,
            "job_params": {
                "model_type": mc.model_type,
                "store_id": store_id,
                "product_id": product_id,
                "start_date": req.start_date.isoformat(),
                "end_date": req.end_date.isoformat(),
                **mc.params,
            },
        }
```

### Routes (`app/features/batch/routes.py`)

Three endpoints mirroring `app/features/jobs/routes.py`:

| Method | Path                       | Status   | Returns                |
|--------|----------------------------|----------|------------------------|
| POST   | `/batch/forecasting`       | 202      | `BatchSubmitResponse`  |
| GET    | `/batch/{batch_id}`        | 200, 404 | `BatchSubmitResponse`  |
| GET    | `/batch/{batch_id}/items`  | 200, 404 | `BatchItemListResponse`|

`sort_by` is `Query(None, pattern=...)` and resolves via `_BATCH_ITEM_SORT_COLUMNS.get(sort_by) or BatchJobItem.created_at` (allow-list, never raw input). All 4xx returns route through `app.core.problem_details.problem_response`.

### Integration Points

```yaml
DATABASE:
  - migration: "alembic/versions/<rev>_create_batch_tables.py"
  - tables: batch_job, batch_job_item
  - indexes (regular):
    - op.f("ix_batch_job_batch_id") UNIQUE
    - op.f("ix_batch_job_status")
    - op.f("ix_batch_job_operation")
    - op.f("ix_batch_job_item_item_id") UNIQUE
    - op.f("ix_batch_job_item_batch_id")
    - op.f("ix_batch_job_item_store_id")
    - op.f("ix_batch_job_item_product_id")
    - op.f("ix_batch_job_item_status")
    - op.f("ix_batch_job_item_child_job_id")
    - op.f("ix_batch_job_item_child_run_id")
    - ix_batch_job_status_created (status, created_at)
    - ix_batch_job_item_batch_status (batch_id, status)
  - indexes (special):
    - ix_batch_job_item_metrics_gin: postgresql_using="gin"
    - ix_batch_job_item_picker (batch_id, status, priority, created_at) postgresql_where=sa.text("status = 'pending'")
  - check constraints:
    - ck_batch_job_valid_status, ck_batch_job_valid_operation, ck_batch_job_priority_band
    - ck_batch_job_item_valid_status, ck_batch_job_item_priority_band
  - foreign key: batch_job_item.batch_id -> batch_job.batch_id ON DELETE CASCADE

CONFIG:
  - add to app/core/config.py (after jobs_retention_days on line 119):
      batch_max_scope_expansion: int = Field(default=1000, ge=1, le=10000)
  - add to .env.example:
      BATCH_MAX_SCOPE_EXPANSION=1000

ROUTES:
  - add to app/main.py imports (between agents_ws_router and seeder_router):
      from app.features.batch.routes import router as batch_router
  - add to app/main.py create_app() (between jobs_router and ingest_router):
      app.include_router(batch_router)

SCOPE ALLOW-LIST:
  - add to .claude/rules/commit-format.md table (between `jobs` and `db`):
      | `batch`      | `app/features/batch/**` |
  - this enables `feat(batch): ...` / `test(batch): ...` for future PRP work.

AGENT TOOLS:
  - Settings.agent_require_approval: UNCHANGED. MVP exposes zero mutating agent tools.
```

## Implementation Tasks (dependency-ordered)

Each task lists target file(s), the precedent to mirror, and the validation gate that confirms it.

```yaml
Task 1 — Pre-add `batch` to commit-format scope allow-list (UNBLOCKS commits on this branch):
  MODIFY .claude/rules/commit-format.md:
    - FIND the row `| \`jobs\`       | \`app/features/jobs/**\` |`
    - INSERT immediately after it: `| \`batch\`      | \`app/features/batch/**\` |`
    - PRESERVE all other rows in their existing order (table is domain-grouped, not alphabetical)
  VALIDATE:
    - grep -n '^| \`batch\`' .claude/rules/commit-format.md  # exactly one match

Task 2 — Create batch_tables migration (FORWARD-ONLY after merge):
  CREATE alembic/versions/<auto>_create_batch_tables.py:
    - MIRROR pattern from alembic/versions/a2f7b3c8d901_create_model_registry_tables.py (two-table create + indexes + checks)
    - INHERIT partial-index syntax from alembic/versions/f7a8b9c0d123_add_exogenous_signal_and_sales_returns_tables.py:80-93 (postgresql_where=sa.text("..."))
    - down_revision: read with `uv run alembic heads --resolve-dependencies` and use the head SHA
    - PRESERVE the exact partial-index predicate: postgresql_where=sa.text("status = 'pending'")
    - PRESERVE on-delete-cascade on batch_job_item.batch_id FK
  VALIDATE:
    - docker compose up -d && uv run alembic upgrade head     # idempotent on fresh DB
    - docker compose exec postgres psql -U forecastlab -d forecastlab -c "\\d batch_job_item"  # confirm columns
    - SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_batch_job_item_picker'  # contains "WHERE (status = 'pending')"

Task 3 — Create slice skeleton:
  CREATE app/features/batch/__init__.py:
    - empty file (slice marker)
  CREATE app/features/batch/models.py:
    - MIRROR pattern from app/features/jobs/models.py (Job ORM + JobType/JobStatus enums + VALID_*_TRANSITIONS)
    - ADD BatchStatus, BatchOperation, BatchItemStatus str Enums per blueprint above
    - ADD VALID_BATCH_TRANSITIONS, VALID_BATCH_ITEM_TRANSITIONS dicts mirroring VALID_JOB_TRANSITIONS
    - ADD BatchJob, BatchJobItem ORM classes per blueprint above (use Mapped[] + mapped_column())
    - PRESERVE __table_args__ shape from jobs/models.py:114-130 (Index + CheckConstraint tuple)
  VALIDATE:
    - uv run python -c "from app.features.batch.models import BatchJob, BatchJobItem, BatchStatus, BatchItemStatus, BatchOperation; print('ok')"
    - uv run mypy app/features/batch/models.py
    - uv run pyright app/features/batch/models.py

Task 4 — Pydantic schemas:
  CREATE app/features/batch/schemas.py:
    - MIRROR pattern from app/features/jobs/schemas.py (JobCreate + JobResponse + JobListResponse + ConfigDict pattern)
    - ADD BatchScope, BatchScopeKind, BatchModelConfig, BatchSubmitRequest, BatchSubmitResponse, BatchItemResponse, BatchItemListResponse per blueprint
    - CRITICAL: every request body uses `model_config = ConfigDict(strict=True)`
    - CRITICAL: every date field uses `Field(strict=False, description="...")` (compliance: docs/_base/SECURITY.md § "Pydantic v2 strict mode on FastAPI request bodies")
    - ADD BatchScope.model_validator(mode="after") to reject kind/selector mismatches (e.g. kind=top_revenue without top_n)
  VALIDATE:
    - uv run pytest app/core/tests/test_strict_mode_policy.py -v   # MUST stay green — covers app/features/**/schemas.py
    - uv run python -c "from app.features.batch.schemas import BatchSubmitRequest; print(BatchSubmitRequest.model_validate({'operation':'backtest','scope':{'kind':'manual','store_ids':[1],'product_ids':[1]},'model_configs':[{'model_type':'naive','params':{}}],'start_date':'2025-01-01','end_date':'2025-06-30'}))"

Task 5 — Service layer:
  CREATE app/features/batch/service.py:
    - MIRROR pattern from app/features/jobs/service.py (JobService class, settings via get_settings, structured logger)
    - ADD _BATCH_ITEM_SORT_COLUMNS allow-list dict (mirror _JOB_SORT_COLUMNS:54-59)
    - ADD _METRICS_KEYS tuple = ("wape", "smape", "mae", "bias", "sample_size")
    - ADD BatchService.submit, _expand_scope, _pick_next, _execute_item, _shape_metrics, _settle, get, list_items
    - CRITICAL: _pick_next uses `.with_for_update(skip_locked=True)` (regression test asserts this)
    - CRITICAL: all cross-slice imports (JobService, ForecastingService, AnalyticsService, DimensionsService) are LAZY inside the methods that need them — see app/features/forecasting/service.py:786-787 for the precedent
    - PRESERVE structlog event names: batch.{created,item_started,item_completed,item_failed,completed,settled}
  VALIDATE:
    - uv run mypy app/features/batch/service.py
    - uv run pyright app/features/batch/service.py
    - grep -n "for_update.*skip_locked" app/features/batch/service.py   # must match the picker query

Task 6 — Routes + wiring:
  CREATE app/features/batch/routes.py:
    - MIRROR pattern from app/features/jobs/routes.py (APIRouter prefix + tags, 202 Accepted, async def, service instance per request)
    - ADD POST /batch/forecasting (202 + BatchSubmitResponse)
    - ADD GET /batch/{batch_id} (200 / 404)
    - ADD GET /batch/{batch_id}/items (200 with paginated allow-listed sort_by)
    - CRITICAL: all 4xx error returns go through app.core.problem_details.problem_response (NEVER raise HTTPException with raw string)
  MODIFY app/main.py:
    - FIND the line `from app.features.agents.websocket import router as agents_ws_router`
    - INJECT after it (preserving alpha order in the existing block): `from app.features.batch.routes import router as batch_router`
    - FIND `app.include_router(jobs_router)`
    - INJECT immediately after it: `app.include_router(batch_router)`
  VALIDATE:
    - uv run uvicorn app.main:app --reload --port 8123 &  # start backend
    - curl -s http://localhost:8123/openapi.json | jq '.paths | keys[] | select(. | startswith("/batch"))'  # 3 paths

Task 7 — Settings + .env.example:
  MODIFY app/core/config.py:
    - FIND the comment `# Jobs`
    - INSERT after `jobs_retention_days: int = 30`:
        # Batch (portfolio orchestration)
        batch_max_scope_expansion: int = Field(default=1000, ge=1, le=10000)
    - IMPORT pydantic.Field at the top of the file if not already imported (it is — line 6)
  MODIFY .env.example:
    - ADD `BATCH_MAX_SCOPE_EXPANSION=1000`
  VALIDATE:
    - uv run python -c "from app.core.config import get_settings; print(get_settings().batch_max_scope_expansion)"   # 1000

Task 8 — Unit tests (no DB):
  CREATE app/features/batch/tests/__init__.py: empty
  CREATE app/features/batch/tests/conftest.py:
    - MIRROR pattern from app/features/jobs/tests/conftest.py
    - ADD fixtures: sample_manual_payload, sample_top_revenue_payload
  CREATE app/features/batch/tests/test_models.py:
    - test_batch_job_status_enum_round_trip
    - test_batch_job_item_priority_band_check (committing priority=7 raises IntegrityError; integration only)
    - test_valid_transitions_dict
  CREATE app/features/batch/tests/test_schemas.py:
    - test_submit_request_strict_mode_json_path (regression for SECURITY.md § "Pydantic v2 strict mode"):
        BatchSubmitRequest.model_validate({"start_date": "2026-01-01", ...})
        # JSON path; mirrors FastAPI's validate_python — failure mode prevented: PR #115, #119
    - test_scope_top_revenue_requires_top_n (kind=top_revenue with top_n=None → ValidationError)
    - test_scope_manual_requires_both_id_lists
    - test_model_configs_min_max_length (length 0 → ValidationError; length 11 → ValidationError)
  CREATE app/features/batch/tests/test_service.py:
    - test_expand_scope_manual_cartesian
    - test_expand_scope_top_revenue_uses_lazy_analytics_import (assert AnalyticsService imported inside method)
    - test_expand_scope_region_uses_lazy_dimensions_import:
        # kind=region with region="EU"; assert DimensionsService imported inside method (not at module scope)
        # pairs cover every store in region × all products
    - test_expand_scope_category_uses_lazy_dimensions_import:
        # kind=category with category="footwear"; assert DimensionsService imported inside method
        # pairs cover all stores × every product in category
    - test_expand_scope_all_cartesian_full_dimensions:
        # kind=all; pairs cover the full store × product cartesian from the dimensions slice
    - test_metrics_jsonb_shape_pinned:
        # Build a JobResponse with aggregated_metrics, call BatchService._shape_metrics,
        # assert set(result.keys()) == {"wape", "smape", "mae", "bias", "sample_size"}
    - test_status_settlement_matrix (partial on mixed, failed on all-fail, completed on all-pass)
    - test_picker_query_uses_skip_locked:
        # Compile the picker SELECT, str(stmt) contains "FOR UPDATE SKIP LOCKED"
    - test_service_emits_lifecycle_events:
        # Patch structlog; submit a 2-pair batch where one item succeeds and one fails.
        # Assert event names emitted in order: batch.created, batch.item_started, batch.item_completed,
        # batch.item_started, batch.item_failed, batch.completed.
        # Assert each event payload carries a `request_id` field for log correlation
        # (per .claude/rules/security-patterns.md § "API surface" — request-ID propagation).
  VALIDATE:
    - uv run pytest app/features/batch/tests/ -v -m "not integration"   # all pass

Task 9 — Integration tests (real Postgres):
  CREATE app/features/batch/tests/test_routes_integration.py:
    - mark every test with @pytest.mark.integration
    - test_submit_batch_happy_path:
        # POST 3-pair manual backtest scope; await response; assert status=completed, completed_items=3
        # for each item: set(item.metrics.keys()) == {"wape", "smape", "mae", "bias", "sample_size"}
    - test_submit_batch_partial_failure:
        # One pair with start_date / end_date producing no sales window → that item failed with error_message
        # parent settles to partial
    - test_scope_over_cap_returns_422:
        # scope expands to > batch_max_scope_expansion; response is RFC 7807 422 (problem+json)
    - test_get_items_sort_by_allow_list:
        # unknown sort_by falls back silently to default; never raises 4xx
    - test_migration_partial_index_present:
        # SELECT indexdef FROM pg_indexes WHERE indexname='ix_batch_job_item_picker'
        # assert "WHERE (status = 'pending'" in indexdef.lower()   # downstream-2's picker depends on this exact predicate
  VALIDATE:
    - docker compose up -d && uv run pytest app/features/batch/tests/ -v -m integration   # all pass

Task 10 — Frontend:
  EXTEND frontend/src/types/api.ts:
    - ADD BatchScope, BatchScopeKind, BatchOperation, BatchModelConfig, BatchSubmitRequest, BatchSubmitResponse, BatchItemResponse, BatchItemListResponse types matching the Pydantic shapes
  CREATE frontend/src/hooks/use-batches.ts:
    - MIRROR pattern from frontend/src/hooks/use-jobs.ts (TanStack Query mutation + query)
    - ADD useSubmitBatch (POST /batch/forecasting), useBatch (GET /batch/{id}), useBatchItems (GET /batch/{id}/items)
    - useBatch polls every 2_000 ms while status in ('pending','running'); stops on terminal
  CREATE frontend/src/hooks/use-batches.test.ts:
    - test useSubmitBatch request body shape (model_configs.length >= 1)
  CREATE frontend/src/pages/visualize/batch.tsx:
    - MIRROR pattern from frontend/src/pages/visualize/forecast.tsx for the page shell
    - MIRROR pattern from frontend/src/pages/explorer/job-detail.tsx for the polling pattern
    - Form: operation + scope (kind + selectors) + model_configs (table with add/remove) + start_date + end_date
    - Submit → display parent status card + items table (item_id, store_id, product_id, model_type, status, duration_ms)
    - NO heatmap, NO max_parallel slider, NO cancel button, NO retry button, NO priority dropdown, NO promotion panel
  CREATE frontend/src/pages/visualize/batch.test.tsx:
    - test form validates model_configs.length >= 1
    - test polling stops on terminal status (mock useBatch returning completed → no further refetch)
  EXTEND frontend/src/pages/ops.tsx (or wherever the /visualize nav lives):
    - 1-line nav entry pointing at /visualize/batch
  VALIDATE:
    - cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run

Task 11 — Run all validation gates:
  Run, in order:
    uv run ruff check . && uv run ruff format --check .
    uv run mypy app/ && uv run pyright app/
    uv run pytest -v -m "not integration"
    docker compose up -d && uv run pytest -v -m integration
    cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run
  ALL must be green before pushing.

Task 12 — Smoke test the demo pipeline (non-regression):
  Run:
    make demo
  Confirm: green run, no perturbation. (The batch slice MUST NOT touch the demo step list.)
```

### Per-task pseudocode (only the parts that need it)

```python
# ── Task 5 picker (compiled SQL containment is the regression test) ──
async def _pick_next(self, db: AsyncSession, batch_id: str) -> BatchJobItem | None:
    stmt = (
        select(BatchJobItem)
        .where(
            BatchJobItem.batch_id == batch_id,
            BatchJobItem.status == BatchItemStatus.PENDING.value,
        )
        .order_by(
            BatchJobItem.priority.desc(),
            BatchJobItem.created_at.asc(),
            BatchJobItem.id.asc(),
        )
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return (await db.execute(stmt)).scalar_one_or_none()

# Regression test (test_service.py::test_picker_query_uses_skip_locked):
def test_picker_query_uses_skip_locked() -> None:
    from sqlalchemy.dialects import postgresql
    stmt = (
        select(BatchJobItem)
        .where(BatchJobItem.batch_id == "x", BatchJobItem.status == "pending")
        .order_by(BatchJobItem.priority.desc(), BatchJobItem.created_at.asc(), BatchJobItem.id.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert "FOR UPDATE SKIP LOCKED" in str(compiled).upper()

# ── Task 2 migration body (the ONLY non-obvious parts) ──
def upgrade() -> None:
    op.create_table(
        "batch_job",
        # ... columns ...
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'partial', 'cancelled')",
            name="ck_batch_job_valid_status",
        ),
        sa.CheckConstraint(
            "operation IN ('train', 'predict', 'backtest', 'train_backtest_register')",
            name="ck_batch_job_valid_operation",
        ),
        sa.CheckConstraint(
            "default_child_priority BETWEEN -1 AND 2",
            name="ck_batch_job_priority_band",
        ),
    )
    op.create_index(op.f("ix_batch_job_batch_id"), "batch_job", ["batch_id"], unique=True)
    # ... simple indexes ...
    op.create_index("ix_batch_job_status_created", "batch_job", ["status", "created_at"], unique=False)

    op.create_table(
        "batch_job_item",
        # ... columns ...
        sa.ForeignKeyConstraint(["batch_id"], ["batch_job.batch_id"], ondelete="CASCADE"),
        # ... check constraints ...
    )
    op.create_index(op.f("ix_batch_job_item_item_id"), "batch_job_item", ["item_id"], unique=True)
    # ... simple indexes ...
    op.create_index("ix_batch_job_item_batch_status", "batch_job_item", ["batch_id", "status"], unique=False)
    op.create_index(
        "ix_batch_job_item_metrics_gin", "batch_job_item", ["metrics"],
        unique=False, postgresql_using="gin",
    )
    op.create_index(
        "ix_batch_job_item_picker",
        "batch_job_item",
        ["batch_id", "status", "priority", "created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),       # ← VERIFIED via existing precedent
    )

def downgrade() -> None:
    # Drop indexes (reverse order), then tables.
    op.drop_index("ix_batch_job_item_picker", table_name="batch_job_item")
    op.drop_index("ix_batch_job_item_metrics_gin", table_name="batch_job_item")
    op.drop_index("ix_batch_job_item_batch_status", table_name="batch_job_item")
    # ... etc
    op.drop_table("batch_job_item")
    op.drop_table("batch_job")
```

## Validation Loop

### Level 1 — Syntax & Style

```bash
uv run ruff check . --fix
uv run ruff format --check .
# Expected: clean. If anything fails, READ the error and fix; never disable a rule.
```

### Level 2 — Type Check

```bash
uv run mypy app/
uv run pyright app/
# Both --strict (already configured in pyproject.toml). Expected: 0 errors.
```

### Level 3 — Unit Tests

```bash
uv run pytest -v -m "not integration"
# Expected: every Task-8 test passes; the load-bearing test_strict_mode_policy.py is green.
# If failing: read error, fix code, re-run — NEVER weaken the linter or mock the DB to pass.
```

### Level 4 — Integration (real Postgres + alembic)

```bash
docker compose up -d
uv run alembic upgrade head        # the new migration applies cleanly
uv run pytest -v -m integration
# Expected: every Task-9 test passes; test_migration_partial_index_present catches predicate drift.
```

### Level 5 — Frontend

```bash
cd frontend
pnpm tsc --noEmit
pnpm lint
pnpm test --run
# Expected: 0 type errors, 0 lint errors, all vitest cases pass.
```

### Level 6 — End-to-end smoke (non-regression)

```bash
make demo
# Expected: green run, identical step list as before. The batch slice MUST NOT touch the demo.
```

### Level 7 — Manual smoke

```bash
# Start the stack
docker compose up -d
uv run uvicorn app.main:app --reload --port 8123 &

# Submit a small batch
curl -X POST http://localhost:8123/batch/forecasting \
  -H "Content-Type: application/json" \
  -d '{"operation":"backtest","scope":{"kind":"manual","store_ids":[1,2,3],"product_ids":[1]},"model_configs":[{"model_type":"naive","params":{}}],"start_date":"2025-01-01","end_date":"2025-06-30"}' \
  | jq

# Expected: 202, status=completed, total_items=3, completed_items=3.
# Every item.metrics has the pinned five keys.

# Confirm partial index landed:
docker compose exec postgres psql -U forecastlab -d forecastlab \
  -c "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_batch_job_item_picker';"
# Expected: includes "WHERE (status = 'pending'::text)" — predicate intact.

# Confirm SKIP LOCKED wired:
grep -n "for_update.*skip_locked" app/features/batch/service.py
# Expected: at least one match in _pick_next.
```

## Final Validation Checklist

A reviewer landing the PRP confirms, in order:

- [ ] `uv run alembic upgrade head` on a fresh Postgres creates both tables + every column, CHECK constraint, and index in the Coordination Matrix.
- [ ] `SELECT indexdef FROM pg_indexes WHERE indexname='ix_batch_job_item_picker'` returns a string containing exactly `WHERE (status = 'pending'` (Postgres may suffix `::text` after parse — substring match, not regex equality).
- [ ] `POST /batch/forecasting` with a 3-pair manual `operation=backtest` scope returns 202 and settles to `completed` with `completed_items=3`. Every item's `metrics` JSONB carries exactly `{wape, smape, mae, bias, sample_size}` — no extras, no missing.
- [ ] `grep -rn "for_update" app/features/batch/service.py` returns at least one line with `skip_locked=True`.
- [ ] `Settings.agent_require_approval` is unchanged from `["create_alias", "archive_run", "save_scenario"]`.
- [ ] `.claude/rules/commit-format.md` lists `batch` in the scope allow-list (between `jobs` and `db`).
- [ ] `app/features/jobs/`, `app/features/forecasting/`, and `tests/test_e2e_demo.py` files are unmodified (`git diff --stat origin/dev...HEAD -- 'app/features/jobs/**' 'app/features/forecasting/**' 'tests/test_e2e_demo.py'` is empty).
- [ ] All five validation gate commands run green: ruff, ruff format, mypy, pyright, pytest -m "not integration", pytest -m integration, frontend tsc + lint + test.
- [ ] `make demo` still completes green (non-regression).
- [ ] `test_strict_mode_policy.py` stays green and DISCOVERS the new BatchSubmitRequest model (the linter's baseline guard auto-extends).
- [ ] PR title is `feat(batch): ship batch-runner MVP (#277)` (lowercase, no trailing period, references the umbrella issue).
- [ ] No AI co-author trailer in any commit (`git log --grep='Co-Authored-By: Claude' origin/dev..HEAD` returns nothing).

## Anti-Patterns to Avoid

- ❌ Don't import another `app/features/<other>/` module at module scope from `app/features/batch/service.py` — closes the alembic cold-boot cycle. Use lazy in-method imports per `app/features/forecasting/service.py:786-787`.
- ❌ Don't add new entries to `Settings.agent_require_approval` in this PRP. MVP exposes zero mutating agent tools. The downstream PRPs add them when they ship their tool surfaces.
- ❌ Don't weaken `app/core/tests/test_strict_mode_policy.py` to make a date field pass — add `Field(strict=False)` instead.
- ❌ Don't ship `metrics` with extra keys or different key names. The shape is pinned across this PRP + four downstream PRPs.
- ❌ Don't remove `skip_locked=True` from the picker query "because the MVP is single-threaded" — the integration test asserts on it; downstream-1/-2 depend on it being wired now.
- ❌ Don't admin-merge the PR with red CI. The four required `dev` status checks (Lint & Format, Type Check, Test, Migration Check) are mandatory.
- ❌ Don't `git push --force` on `dev` or `main`. `--force-with-lease` on the feature branch only, and only if absolutely necessary.
- ❌ Don't add `Co-Authored-By: Claude` or `🤖 Generated with` lines to any commit. The pre-commit hook rejects them — fix the message, never bypass.
- ❌ Don't ship the heatmap, max_parallel slider, cancel button, retry button, priority dropdown, or promotion panel in this PRP. Each is owned by exactly one downstream PRP.
- ❌ Don't add a managed-cloud SDK (Celery/Redis/SQS) to make the runner async — single-host vision per `.claude/rules/product-vision.md`.

## Open Questions Resolved (lifted from INITIAL § "Open Questions")

- **Q1 — `train_backtest_register` alias side-effect.** RESOLVED: MVP registers the run (`model_run.status=success`) but does NOT create an alias. Alias-naming policy is owned by `INITIAL-batch-champion-and-heatmap` (downstream-4). Alias creation is the HITL-gated `promote_champions` tool's job and is deferred.
- **Q2 — `scope.kind=top_revenue` resolution.** RESOLVED: lazy-import `AnalyticsService` inside `_expand_scope` — preserves the vertical-slice invariant. AnalyticsService already owns the revenue-ranking SQL.
- **Q3 — Per-item `params` validation at submit time.** RESOLVED: yes — validate against the same Pydantic models `JobService` already uses (`TrainRequest`/`PredictRequest`/`BacktestRequest`) so a 500-pair batch fails fast on a typo, not an hour into execution. Implementation: inside `_expand_scope`, validate one frozen-params dict per (operation, model_type) tuple before any DB insert.
- **Q4 — `result_summary` JSONB shape.** RESOLVED: `{total, completed, failed, pending, running, cancelled, attempts_used: 0, by_model_type: { <model_type>: {completed, failed} }}`. The `attempts_used` key is `0` in MVP; downstream-3 populates it.

## References

**Source / precedents (verified in this PRP):**
- `PRPs/INITIAL/INITIAL-batch-runner-mvp.md` (source spec, 493 lines)
- `PRPs/INITIAL/INITIAL-batch-{champion-and-heatmap,export-and-retry,parallel-execution,priority-queue}.md` (the four downstream INITIALs)
- `docs/optional-features/06-portfolio-forecasting-batch-runner.md` § "MVP Scope"
- `app/features/jobs/{models,schemas,service,routes}.py` (executor pattern, 202 convention, sort allow-list at jobs/service.py:54-59)
- `app/features/forecasting/service.py:700-701, 786-787` (lazy cross-slice import precedent)
- `app/features/registry/service.py` (status state machine precedent)
- `app/features/backtesting/metrics.py` (WAPE/sMAPE/MAE/bias definitions populating the pinned `metrics` JSONB)
- `app/core/{problem_details,config,database,logging,middleware}.py`
- `app/shared/models.py` (`TimestampMixin`)
- `app/core/tests/test_strict_mode_policy.py` (the AST linter that gates strict-mode policy compliance)
- `alembic/versions/a2f7b3c8d901_create_model_registry_tables.py` (two-table migration precedent)
- `alembic/versions/f7a8b9c0d123_add_exogenous_signal_and_sales_returns_tables.py:80-93` (partial-index precedent)
- `frontend/src/pages/explorer/job-detail.tsx` (polling precedent)
- `frontend/src/hooks/use-jobs.ts` (TanStack Query mutation precedent)
- `frontend/src/pages/visualize/forecast.tsx` (visualize page shell precedent)

**Rules + base docs:**
- `.claude/rules/{product-vision,commit-format,branch-naming,security-patterns,test-requirements,ui-design,shadcn-ui,versioning,output-formatting}.md`
- `docs/_base/{ARCHITECTURE,API_CONTRACTS,SECURITY,PIPELINE_CONTRACT,DOMAIN_MODEL,RULES,RUNBOOKS}.md`

**Runtime-verification commands (re-run on any library upgrade):**
- `uv run python -c "from sqlalchemy import select; import inspect; print(inspect.signature(select(None).with_for_update))"` → must include `skip_locked: bool = False`
- `uv run python -c "from pydantic import BaseModel, Field, ConfigDict; from datetime import date; \nclass M(BaseModel):\n  model_config = ConfigDict(strict=True)\n  d: date = Field(strict=False)\nprint(M.model_validate({'d': '2026-01-01'}))"` → must print `d=datetime.date(2026, 1, 1)`
- `grep -rn "postgresql_where" alembic/versions/` → must show the precedent migrations (`f7a8b9c0d123_*.py`)

---

## Confidence Score

**Confidence: 9/10** for one-pass implementation success.

**What gives me confidence:**
- The source INITIAL is unusually complete (493 lines of pinned design, no open architectural questions left).
- Every library claim is runtime-verified in this PRP (SQLAlchemy `with_for_update(skip_locked=True)`, Alembic `postgresql_where`, Pydantic `Field(strict=False)`).
- Every cross-slice integration point has a named, line-anchored precedent (lazy import: `forecasting/service.py:786-787`; partial index: `f7a8b9c0d123_*.py:80-93`; two-table migration: `a2f7b3c8d901_*.py`).
- The four downstream INITIALs are merged on `dev` — the Cross-Slice Coordination Matrix is now historic and immutable, not speculative.
- The non-regression boundary is explicit: `app/features/jobs/`, `app/features/forecasting/`, `tests/test_e2e_demo.py` are off-limits, and the integration test set asserts on the partial-index predicate + the pinned JSONB shape.

**Why not 10:**
- `_shape_metrics` depends on the shape of `JobResponse.result` for backtest jobs. The current job result shape (`aggregated_metrics: {wape_mean, smape_mean, mae_mean, bias_mean}`) does not include a `sample_size` aggregate. **Resolved: compute `sample_size` inside the batch slice from `fold_metrics`.** `_shape_metrics` derives the aggregate as `sum(f.get("sample_size", 0) for f in job.result.get("fold_metrics", []))` with `job.result.get("n_observations")` as the fallback when `fold_metrics` is empty (matches the blueprint at the `_shape_metrics` body in § "Service blueprint"). The implementing agent verifies on first read that `FoldResult` exposes `sample_size` per fold: `uv run python -c "from app.features.backtesting.schemas import FoldResult; print(FoldResult.model_fields.keys())"`. **Option (b) — extending `_shape_backtest_result` (`jobs/service.py:71-136`) to emit a new aggregate — is REJECTED** because it touches `app/features/jobs/`, violating the vertical-slice no-cross-import rule and the explicit non-regression boundary declared in § "What → Success Criteria" of this PRP. All `sample_size` derivation MUST stay inside `app/features/batch/`.
