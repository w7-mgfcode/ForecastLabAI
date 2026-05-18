name: "PRP-21 — Explorer Interactivity: Model Runs & Jobs (detail views, comparison, verify, sorting)"
description: |
  Extend the **Model Runs** and **Jobs** pages of the ForecastLabAI dashboard
  Explorer menu from flat, read-only tables into an interactive investigation
  surface — the direct sibling of PRP-20 (`#187`/`#188`, which did this for
  Sales / Stores / Products), applied to the `registry` and `jobs` slices:

  1. **Click-through detail views** — three new deep-linkable routes:
     - `/explorer/runs/:runId` — model-run profile, JSON config/metrics/runtime
       info, store/product cross-links, an artifact section with a "Verify
       integrity" button, and a "Compare with…" link.
     - `/explorer/jobs/:jobId` — job profile, `params`/`result` JSON, error
       details, a linked `run_id`, and a cancel action; live-polls while running.
     - `/explorer/runs/compare?a=<id>&b=<id>` — run-vs-run comparison: side-by-side
       profile table, `config_diff`, and `metrics_diff` with delta indicators.
  2. **Artifact verify action** — a button on the run detail page calling the
     existing `GET /registry/runs/{run_id}/verify` (SHA-256 integrity check).
  3. **Richer tables** — server-side column sorting + row-click navigation on both
     tables; the Jobs table additionally gains CSV export + column-visibility
     toggles (the Runs table already has both from PRP-20).
  4. **URL state** — filter / sort / page state on both tables persisted in the
     URL query string (`useSearchParams`), so a pasted URL reproduces the view.

  Backend-touching but **additive**: the only server change is two optional
  `sort_by` / `sort_order` query params on `GET /registry/runs` and `GET /jobs`
  (allow-listed columns; unknown → default order, never an error). **No Alembic
  migration**, **no new slice**, **no new env var**, **no `app/main.py` change**
  (both routers are already wired). Every detail/compare/verify endpoint the
  frontend needs **already exists**; three of four hooks (`useRun`, `useJob`,
  `useCompareRuns`) already exist and are currently unused.

> **PRP numbering:** `PRP-16` is reserved (Phase-2 LightGBM). `PRP-17`–`PRP-20`
> are used. This is `PRP-21`. Source plan:
> `.agents/plans/explorer-runs-jobs-interactivity.md`.

## Purpose
Close the "Model Runs / Jobs Explorer pages are terminal" gap. Today a row shows a
truncated `run_id`/`job_id`, a status badge, and a few columns — there is no way to
see a run's `model_config`, `metrics`, `runtime_info`, the artifact hash, or a job's
`params`/`result`/`error_message` from the UI. Two runs cannot be compared. Artifact
integrity cannot be checked. Neither table sorts, the Jobs table cannot export, and
filter state is lost on every refresh. Every one of those answers already exists in
the backend; the dashboard simply does not surface them. PRP-20 solved the identical
gap for Stores/Products — this PRP applies the same pattern to the remaining two
Explorer pages.

## Core Principles
1. **Context is King** — every endpoint shape, hook name, schema field, service
   method, and pattern below is linked to a real source file + verified line numbers.
2. **Reuse existing patterns** — the backend change is a verbatim copy of the
   `dimensions` allow-listed-sort pattern; the new pages mirror `store-detail.tsx`;
   the table upgrades mirror `stores.tsx`; the routes register exactly like the
   existing Explorer detail routes in `App.tsx`.
3. **Additive only** — no new slice, no migration, no new `.env` var, no
   `app/main.py` edit. The backend delta is two optional query params on two
   already-wired list endpoints.
4. **Strict gates honored** — because `.py` files in the `registry` and `jobs`
   slices change, the repo-wide `ruff` / `mypy --strict` / `pyright --strict` /
   `pytest` CI jobs genuinely apply and must stay green; each backend change ships
   with slice tests.
5. **UI through skills** — pages built via `frontend-design` + `shadcn-ui` and
   dogfooded via `webapp-testing` / `agent-browser` per `.claude/rules/ui-design.md`.
   A green `tsc` is NOT proof the UI works.

---

## Goal

**Backend (additive, no migration):**
- `GET /registry/runs` gains optional `sort_by` + `sort_order` params (allow-listed
  columns; unknown `sort_by` → default `created_at desc`, never an error).
- `GET /jobs` gains the identical `sort_by` + `sort_order` params.

**Frontend:**
- Three new routes — `/explorer/runs/:runId`, `/explorer/jobs/:jobId`,
  `/explorer/runs/compare` — composed entirely from already-shipped endpoints.
- Row-click navigation from the Runs / Jobs tables into the detail pages.
- Server-side column sorting on both tables; CSV export + column-visibility on the
  Jobs table (Runs already has them).
- Filter / sort / page state on both tables persisted in the URL query string.
- One new hook (`useVerifyArtifact`), one new shared component (`JsonBlock`), one new
  TS type (`ArtifactVerifyResponse`); `sortBy`/`sortOrder` added to `useRuns`/`useJobs`.

## Why
- **Portfolio identity.** `.claude/rules/product-vision.md` principle 1 —
  "portfolio-grade, end-to-end … every phase ships working code". The registry and
  jobs slices are fully built (`GET /registry/runs/{id}`, `/registry/compare/{a}/{b}`,
  `/registry/runs/{id}/verify`, `GET /jobs/{id}`) but the dashboard exposes them only
  as flat tables — a reviewer cannot inspect a single run or compare two without
  leaving the UI for Swagger.
- **Analyst workflow.** "Why did this run perform worse" and "what did this job
  return" are core questions; today they are unanswerable in-product.
- **Consistency.** Stores/Products already have detail pages, sorting, export and URL
  state (PRP-20). Runs/Jobs being flat is a visible, jarring inconsistency.
- **High value per line.** Almost everything is composition of shipped endpoints and
  shipped components; the only new server code is two query params.

## What
Backend-touching but additive. Two `sort_by`/`sort_order` query params + allow-listed
ordering on the `registry` and `jobs` list endpoints, with tests for both (the `jobs`
slice has **no DB test fixtures and no route tests today** — this PRP also closes that
gap). Frontend: 3 new pages, 3 new routes, 1 new hook, 1 new component, 1 new TS type,
2 existing table pages upgraded to interactive. No migration, no new env var, no new
slice, no `app/main.py` change.

### Success Criteria
- [ ] `GET /registry/runs` and `GET /jobs` accept `sort_by` + `sort_order`; omitting
      them preserves the current `created_at desc` default; an unknown `sort_by`
      falls back to the default order without erroring; `sort_order` outside
      `{asc,desc}` is rejected (422 via the `Query` regex).
- [ ] Clicking a Model Runs row navigates to a working `/explorer/runs/:runId` page
      with status, model type, store/product links, data window, hashes,
      timestamps, and the `model_config`/`feature_config`/`metrics`/`runtime_info`/
      `agent_context` JSON.
- [ ] Clicking a Jobs row navigates to a working `/explorer/jobs/:jobId` page with
      status, type, timestamps, linked `run_id`, `params`/`result` JSON, error
      details, and a cancel action for pending jobs; the page live-polls until terminal.
- [ ] `/explorer/runs/compare?a=&b=` shows two run pickers, a side-by-side profile
      table, `config_diff`, and `metrics_diff` with delta indicators; the comparison
      is deep-linkable via the URL.
- [ ] The run detail "Verify integrity" button calls `GET /registry/runs/{id}/verify`
      and surfaces pass/fail (incl. the `verified:false` checksum-mismatch branch).
- [ ] Both tables support server-side column sorting + row-click; the Jobs table
      also supports CSV export + column-visibility; the Jobs table's in-row cancel
      button cancels WITHOUT navigating.
- [ ] Filter / sort / page state on both tables round-trips through the URL (paste a
      filtered URL into a fresh tab → identical view).
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ &&
      uv run pyright app/` clean; `uv run pytest -v -m "not integration"` and the
      `registry` + `jobs` integration tests green.
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` clean.
- [ ] No Alembic migration; no new slice; no `app/main.py` change; no `.env` var.
- [ ] All three new pages dogfooded in a real browser (screenshots captured).

---

## All Needed Context

### Documentation & References
```yaml
# ---- External docs ----
- url: https://tanstack.com/query/latest/docs/framework/react/guides/queries
  why: useQuery shape for the new useVerifyArtifact hook.
  critical: GET data → useQuery({ queryKey, queryFn, enabled }). The repo hooks
    (use-runs.ts, use-jobs.ts) follow this exactly — copy that shape.

- url: https://tanstack.com/query/latest/docs/framework/react/guides/disabling-queries
  why: useVerifyArtifact is a button-gated GET — `enabled` toggled by component
    state, then refetch(). This is exactly how useCompareRuns (use-runs.ts:50-56)
    is already built — mirror it.

- url: https://tanstack.com/table/v8/docs/guide/sorting#manual-server-side-sorting
  why: DataTable already sets `manualSorting: true`; SortingState (`[{id,desc}]`)
    MUST round-trip through the backend sort_by/sort_order params.
  critical: A client-only sort reorders ONLY the visible page. Server-side is
    mandatory — thread SortingState → sort_by/sort_order → useRuns/useJobs.

- url: https://tanstack.com/table/v8/docs/guide/column-visibility
  why: column-visibility dropdown — already implemented in DataTable via
    `enableColumnVisibility`; the Jobs table just needs to pass the prop.

- url: https://reactrouter.com/6.30.1/hooks/use-params
  why: `:runId` / `:jobId` dynamic-segment extraction.
  critical: useParams() returns `Record<string,string|undefined>`. Run/Job IDs
    are UUID-hex STRINGS — guard truthiness only, do NOT Number()-parse them
    (unlike store-detail.tsx / product-detail.tsx which parse numeric ids).

- url: https://reactrouter.com/6.30.1/hooks/use-search-params
  why: URL filter/sort/page persistence + reading ?a=&b= on the compare page.
  critical: useSearchParams() → [params, setParams]; params.get('x') is
    `string | null`. Treat it as controlled state initialised from the URL.

- url: https://reactrouter.com/6.30.1/route/route
  why: route ranking. v6 ranks routes by specificity — the static
    `/explorer/runs/compare` outranks the dynamic `/explorer/runs/:runId`, so
    `compare` is never captured as a `:runId`. Registration order does not matter;
    register `compare` first anyway for readability.

# ---- THE sibling PRP to mirror ----
- file: PRPs/PRP-20-explorer-interactivity.md
  why: this PRP's direct precedent. Read its "Known Gotchas", "list of tasks",
    "Validation Loop", and "Anti-Patterns" — this PRP applies the same shape to
    the registry/jobs slices. PRP-20 added DataTable's onRowClick / sorting /
    enableColumnVisibility, csv-export.ts, DataTableColumnHeader, and the
    store-detail/product-detail pages — all REUSED here, not rebuilt.

# ---- Backend: the sort pattern to copy verbatim ----
- file: app/features/dimensions/service.py
  why: lines 29-45 — `_STORE_SORT_COLUMNS` / `_PRODUCT_SORT_COLUMNS` allow-list
    dicts typed `dict[str, InstrumentedAttribute[Any]]`; import on line 12
    (`from sqlalchemy.orm import InstrumentedAttribute`). Lines 105-113 — the
    resolve-or-default ordering logic. COPY this dict + logic exactly.

- file: app/features/dimensions/routes.py
  why: lines 70-91 / 195-216 — the `sort_by` / `sort_order` `Query(...)`
    declarations + docstrings. `sort_order` uses
    `Query("asc", pattern="^(asc|desc)$", description=...)`.

# ---- Backend: registry slice (gets sort params) ----
- file: app/features/registry/routes.py
  why: `list_runs` handler lines 147-182 — add sort_by/sort_order Query params
    here (after `product_id`), pass into service.list_runs(). get_run (185-217),
    verify_artifact (311-383), compare_runs (566-606) ALREADY EXIST — do NOT
    modify, the frontend just consumes them.
  critical: verify_artifact returns HTTP 200 with `{"verified": false, ...}` on a
    checksum mismatch (lines 377-383) — it does NOT raise. Only a missing
    run/artifact 404s. The frontend must handle both the 200-false branch and
    the error branch.

- file: app/features/registry/service.py
  why: `list_runs` lines 257-310 — default order is
    `stmt.order_by(ModelRun.created_at.desc())` (line 300). Imports already have
    `from typing import Any` (line 19) and `from sqlalchemy import func, select`
    (line 22). Add `InstrumentedAttribute` import + `_RUN_SORT_COLUMNS` here.

- file: app/features/registry/tests/conftest.py
  why: ALREADY has integration DB fixtures — `db_session` (lines 26-56), `client`
    (lines 59-79) — plus sample run fixtures. REUSE these.
  critical: the `db_session` cleanup deletes runs via
    `ModelRun.model_type.like("test-%")` (lines 49,53). Every run a sort test
    creates MUST use a `model_type` starting with `test-` or it will not be
    cleaned up. Aliases for those runs are cleaned too.

- file: app/features/registry/tests/test_routes.py
  why: already has `@pytest.mark.integration` route tests using the `client`
    fixture. Add the sort-param test cases here in that same style.

# ---- Backend: jobs slice (gets sort params; needs DB test fixtures) ----
- file: app/features/jobs/routes.py
  why: `list_jobs` handler lines 169-195 — add sort_by/sort_order Query params
    (after `status`). get_job (222-247), cancel_job (265-297) ALREADY EXIST.

- file: app/features/jobs/service.py
  why: `list_jobs` lines 204-251 — default order is
    `stmt.order_by(Job.created_at.desc())` (line 240). Imports: `from typing
    import TYPE_CHECKING, Any` (line 14), `from sqlalchemy import func, select`
    (line 16). Add `InstrumentedAttribute` import + `_JOB_SORT_COLUMNS` here.

- file: app/features/jobs/models.py
  why: the `Job` ORM model. Columns for the sort allow-list: `created_at`,
    `completed_at` (both `DateTime`, `completed_at` nullable), `job_type`,
    `status` (both `String`). `params`/`result` are JSONB — NOT sortable.
    `job_id` is `String(32)` (exactly a uuid4 hex).

- file: app/features/jobs/tests/conftest.py
  why: currently UNIT-ONLY (`sample_train_job_create` etc.). It has NO
    `db_session` / `client` fixture; the `jobs` slice has NO `test_routes.py`.
  critical: Task 4 must COPY `db_session` + `client` from
    app/features/registry/tests/conftest.py:26-79, swapping the cleanup to delete
    `Job` rows. Job has no `model_type` — use a `job_id` prefix for the cleanup
    key (see Gotchas).

# ---- Frontend: hooks (3 of 4 already exist) ----
- file: frontend/src/hooks/use-runs.ts
  why: `useRuns` (list, lines 15-40), `useRun(runId, enabled)` (42-48),
    `useCompareRuns(a, b, enabled)` (50-56). Add sortBy/sortOrder to UseRunsParams;
    add a new `useVerifyArtifact` hook here.

- file: frontend/src/hooks/use-jobs.ts
  why: `useJobs` (list, 13-35), `useJob(jobId, enabled)` (37-47 — ALREADY polls
    every 2s while pending/running, stops otherwise), `useCancelJob` (60-69). Add
    sortBy/sortOrder to UseJobsParams.

- file: frontend/src/hooks/use-stores.ts
  why: the PRP-20 precedent for adding optional sortBy/sortOrder to a list hook —
    threaded into both the queryKey array and the api params. Mirror it.

# ---- Frontend: components (all already exist — REUSED, not built) ----
- file: frontend/src/components/data-table/data-table.tsx
  why: ALREADY supports `sorting`, `onSortingChange`, `onRowClick`,
    `enableColumnVisibility` (PRP-20, props at lines 31-36). NO change needed —
    just pass the props from runs.tsx / jobs.tsx.

- file: frontend/src/components/data-table/data-table-column-header.tsx
  why: `<DataTableColumnHeader column title />` — a sortable header button. Use it
    in the runs/jobs column defs for sortable columns. A column is sortable unless
    its def sets `enableSorting: false`.

- file: frontend/src/components/common/status-badge.tsx + frontend/src/lib/status-utils.ts
  why: `StatusBadge` + `getStatusVariant(status)`. status-utils ALREADY maps every
    RunStatus (pending/running/success/failed/archived) and JobStatus
    (pending/running/completed/failed/cancelled) value — no change needed.

- file: frontend/src/components/common/error-display.tsx
  why: `ErrorDisplay` (error + optional onRetry/title) — used on every detail
    page for the invalid-id and query-error states.

- file: frontend/src/components/common/job-picker.tsx
  why: an existing entity-picker component — read it as the pattern for the
    run-picker `<select>` on the compare page (or use shadcn Select directly).

- file: frontend/src/components/common/index.ts
  why: barrel — add `export * from './json-block'` for the new JsonBlock component.

- file: frontend/src/components/ui/select.tsx
  why: shadcn Select — read for exact exports (Select, SelectTrigger, SelectValue,
    SelectContent, SelectItem) for the compare-page run pickers.

- file: frontend/src/components/charts/kpi-card.tsx
  why: OPTIONAL — `KPICard` (title, value, icon?, isLoading?) could surface a
    run's headline metrics; JsonBlock is the minimum.

- file: frontend/src/lib/csv-export.ts
  why: `toCsv(rows, columns)` + `downloadCsv(filename, csv)` + `CsvColumn<T>`
    (`key: keyof T & string`, `header`). Already used by runs.tsx — the Jobs table
    needs the same `csvColumns` + export button.

- file: frontend/src/lib/api.ts
  why: `api<T>(endpoint, {params, method, body})` client (drops undefined/null/''
    params), `formatNumber`, `ApiError`, `getErrorMessage`.

# ---- Frontend: routing + pages ----
- file: frontend/src/lib/constants.ts
  why: `ROUTES.EXPLORER` (lines 5-15). STORE_DETAIL/PRODUCT_DETAIL are already
    there as dynamic routes (13-14). Add RUN_DETAIL, JOB_DETAIL, RUN_COMPARE.
    NAV_ITEMS (27-51) is UNCHANGED — detail pages are click-through, not nav items.

- file: frontend/src/App.tsx
  why: lazy imports (10-25), `<Route>`s inside `<AppShell/>` (37-158).
    StoreDetailPage / ProductDetailPage are already registered (lines 15, 17,
    70-93) — add the 3 new pages identically.

- file: frontend/src/pages/explorer/store-detail.tsx
  why: THE detail-page template — useParams + guard (22-24), ErrorDisplay states
    (56-75), "Back to …" Button-asChild-Link (86-91), profile Card `<dl>` grid
    (108-133), section cards with empty-state fallbacks (162-197).

- file: frontend/src/pages/explorer/stores.tsx
  why: THE interactive-table-page template — useSearchParams URL state (57-95),
    handleSortingChange (102-110), handlePaginationChange (97-100), CSV export
    (125-127), onRowClick → navigate() (191), DataTableColumnHeader in column defs
    (22-45). runs.tsx + jobs.tsx must converge on this exact shape.

- file: frontend/src/pages/explorer/runs.tsx
  why: current Model Runs page (176 lines). ALREADY has CSV export +
    enableColumnVisibility. Gets URL state, row-click, server sort, a "Compare" link.

- file: frontend/src/pages/explorer/jobs.tsx
  why: current Jobs page (192 lines). Has NEITHER export NOR column visibility NOR
    URL state. The `columns` array is built INSIDE the component (closes over
    handleCancelJob); the `actions` column (91-122) renders an AlertDialog cancel
    button inside the row.

- file: frontend/src/types/api.ts
  why: `ModelRun` (122-145), `RunListResponse` (147-149), `RunCompareResponse`
    (161-166: run_a, run_b, config_diff, metrics_diff:Record<string,{a,b,diff}>),
    `RunStatus` (120), `Job` (172-185), `JobListResponse` (187-189),
    `JobStatus`/`JobType` (169-170). Add one new `ArtifactVerifyResponse` type.

# ---- Rules ----
- file: .claude/rules/ui-design.md
  why: UI built/dogfooded via frontend-design + shadcn-ui + webapp-testing.
- file: .claude/rules/security-patterns.md
  why: "Allow-lists over deny-lists" — sort_by MUST resolve through an allow-list
    dict to a real mapped column, never interpolate the raw string into SQL.
- file: .claude/rules/test-requirements.md
  why: new endpoint param → test; new SQLAlchemy-touching path → integration test
    against real Postgres, never mocked.
- file: .claude/rules/commit-format.md & branch-naming.md
  why: `type(scope): description (#issue)`; scopes `registry`/`jobs`/`ui`/`api`/
    `docs` (comma-pairs allowed); branch `feat/explorer-runs-jobs-interactivity`
    off `dev`; open the tracking issue FIRST.
```

### Current Codebase tree (relevant)
```bash
app/features/
├── registry/
│   ├── routes.py            # MOD — +sort_by/sort_order on list_runs
│   ├── service.py           # MOD — +_RUN_SORT_COLUMNS, allow-listed ordering
│   └── tests/
│       ├── conftest.py      # REUSE — db_session/client already exist
│       └── test_routes.py   # MOD — +sort-param integration tests
└── jobs/
    ├── routes.py            # MOD — +sort_by/sort_order on list_jobs
    ├── service.py           # MOD — +_JOB_SORT_COLUMNS, allow-listed ordering
    └── tests/
        ├── conftest.py      # MOD — +db_session/client (copied from registry) + sample_jobs_multi
        └── test_routes.py   # NEW — integration tests (closes the jobs route-test gap)

frontend/src/
├── App.tsx                  # MOD — +3 lazy detail/compare routes
├── lib/constants.ts         # MOD — +ROUTES.EXPLORER.RUN_DETAIL/JOB_DETAIL/RUN_COMPARE
├── types/api.ts             # MOD — +ArtifactVerifyResponse
├── hooks/
│   ├── use-runs.ts          # MOD — +sortBy/sortOrder on useRuns, +useVerifyArtifact
│   └── use-jobs.ts          # MOD — +sortBy/sortOrder on useJobs
├── components/common/
│   ├── json-block.tsx       # NEW — formatted-JSON viewer
│   └── index.ts             # MOD — +1 barrel line
└── pages/explorer/
    ├── runs.tsx             # MOD — +row-click, +sorting, +url state, +compare link
    ├── jobs.tsx             # MOD — +row-click, +sorting, +export, +visibility, +url state
    ├── run-detail.tsx       # NEW
    ├── job-detail.tsx       # NEW
    └── run-compare.tsx      # NEW
```

### Desired Codebase tree (files added / changed)
```bash
NEW  app/features/jobs/tests/test_routes.py            # integration — /jobs list + sort + /jobs/{id}
NEW  frontend/src/components/common/json-block.tsx     # JSON viewer component
NEW  frontend/src/pages/explorer/run-detail.tsx        # /explorer/runs/:runId
NEW  frontend/src/pages/explorer/job-detail.tsx        # /explorer/jobs/:jobId
NEW  frontend/src/pages/explorer/run-compare.tsx       # /explorer/runs/compare
MOD  app/features/registry/{routes,service}.py         # +sort_by/sort_order
MOD  app/features/registry/tests/test_routes.py        # +sort integration tests
MOD  app/features/jobs/{routes,service}.py             # +sort_by/sort_order
MOD  app/features/jobs/tests/conftest.py               # +db_session/client + sample_jobs_multi
MOD  frontend/src/types/api.ts                         # +ArtifactVerifyResponse
MOD  frontend/src/hooks/{use-runs,use-jobs}.ts         # +sort params, +useVerifyArtifact
MOD  frontend/src/components/common/index.ts           # +json-block barrel line
MOD  frontend/src/lib/constants.ts                     # +3 routes
MOD  frontend/src/App.tsx                              # +3 lazy routes
MOD  frontend/src/pages/explorer/{runs,jobs}.tsx       # interactive upgrades
MOD  README.md                                         # feature list
MOD  docs/_base/API_CONTRACTS.md                       # +sort params on /registry/runs & /jobs
MOD  docs/_base/REPO_MAP_INDEX.md                      # +run-detail/job-detail/run-compare rows
KEEP app/main.py                                       # UNCHANGED — both routers already wired
KEEP alembic/**                                        # UNCHANGED — NO migration (sort is read-only)
```

### Known Gotchas & Library Quirks
```python
# CRITICAL: NO Alembic migration. Sorting is a read-only ORDER BY change; the
#   schema does not change. `.claude/rules` require a migration only when the
#   SCHEMA changes. Adding one would be wrong.

# CRITICAL: sort_by is user input. Resolve it through an explicit allow-list dict
#   {str: InstrumentedAttribute} → a real SQLAlchemy mapped column. NEVER
#   interpolate the raw string into the query (security-patterns.md). Unknown
#   sort_by → fall back to the default order; do NOT 400 (keeps it
#   backward-compatible and avoids 500s from stale frontend state).

# CRITICAL: ModelRun.metrics / ModelRun.runtime_info and Job.params / Job.result
#   are JSONB columns — they are NOT in the sort allow-list (cannot ORDER BY a
#   JSONB blob meaningfully). Allow-list runs by created_at|model_type|status|
#   store_id|product_id; jobs by created_at|completed_at|job_type|status.

# CRITICAL: registry verify_artifact (routes.py:377-383) returns HTTP 200 with
#   {"verified": false, ...} on a checksum MISMATCH — it does NOT raise. Only a
#   missing run (404) or missing artifact (400) is an error. useVerifyArtifact
#   must handle the 200-false success branch AND the ApiError branch.

# CRITICAL: jobs slice has NO DB test infrastructure. jobs/tests/conftest.py has
#   only unit fixtures; there is no test_routes.py. Task 4 copies db_session +
#   client from registry/tests/conftest.py:26-79. Budget time — this is the
#   least-mechanical task (mirrors PRP-20's analytics test gap).

# CRITICAL: registry's db_session cleanup deletes runs via
#   ModelRun.model_type.like("test-%"). A sort test that creates runs MUST set
#   model_type to a value starting with "test-" (e.g. "test-aaa", "test-bbb")
#   or the rows leak. Sorting by model_type still works on those values.

# CRITICAL: Job has no model_type column for a cleanup key. The jobs db_session
#   cleanup must key on job_id. Job.job_id is String(32) (exactly a uuid4 hex).
#   Create test jobs with job_id = "test" + uuid.uuid4().hex[:28] (32 chars,
#   starts "test"); cleanup: delete(Job).where(Job.job_id.like("test%")).

# GOTCHA: run_id / job_id are UUID-hex STRINGS, not integers. The detail pages
#   guard useParams() values by truthiness only — do NOT Number()-parse them
#   (store-detail.tsx / product-detail.tsx parse numeric ids; this is different).

# GOTCHA: React Router v6 ranks `/explorer/runs/compare` (static) ABOVE
#   `/explorer/runs/:runId` (dynamic) — `compare` is never captured as a runId.
#   Registration order in <Routes> does not matter; register compare first anyway.

# GOTCHA: jobs.tsx renders an AlertDialog cancel button inside each row
#   (lines 91-122). Once onRowClick makes the row clickable, the cancel cell
#   MUST stopPropagation — wrap the AlertDialogTrigger/cell with
#   onClick={(e) => e.stopPropagation()} so cancelling does not also navigate.

# GOTCHA: DataTable has `manualSorting: true`. Server-side sort is mandatory —
#   thread SortingState → sort_by/sort_order → useRuns/useJobs → URL. A
#   client-only sort would silently reorder only the current page.

# GOTCHA: a DataTableColumnHeader column's `column.id` (= accessorKey) must equal
#   the backend allow-list key. runs.tsx accessorKeys status|model_type|store_id|
#   product_id|created_at already match _RUN_SORT_COLUMNS; jobs.tsx status|
#   job_type|created_at|completed_at match _JOB_SORT_COLUMNS.

# GOTCHA: data-table-pagination.tsx ALREADY has a page-size selector. Do NOT add
#   another one.

# GOTCHA: keep useRuns/useJobs sortBy/sortOrder params OPTIONAL — nothing else
#   calls these hooks, but optionality keeps the diff minimal and safe.

# GOTCHA: new .tsx/.ts files are LF. Editing existing .py files preserves their
#   CRLF (repo .py files are CRLF, no .gitattributes — project memory). After
#   writing the NEW .py test file run `git diff --stat` and confirm no whole-file
#   EOL churn slipped in.

# GOTCHA: both routers are already in app/main.py. Do NOT edit main.py — the sort
#   params attach to the existing list handlers in routes.py.

# GOTCHA: every commit references the open tracking issue (commit-format.md);
#   NO AI co-author trailer, ever. Branch off `dev`.
```

### Resolved Decisions (user-confirmed 2026-05-18)
```yaml
interactivity-scope:
  decision: all four directions ship — detail pages + row-click, run-vs-run
    comparison, artifact verify action, and server-side table sorting.
  status: confirmed (AskUserQuestion, multi-select all four).
compare-ux:
  decision: run-vs-run comparison is a dedicated deep-linkable route
    (/explorer/runs/compare?a=<id>&b=<id>), NOT a modal/inline panel — shareable
    via URL, consistent with the deep-linkable detail-page pattern.
  status: confirmed (user chose "Dedicated deep-linkable route").
metrics-diff-rendering:
  decision: metrics_diff is rendered as a table with delta indicators (▲/▼ on the
    sign of `diff`), NOT a chart. The PRP does not colour-code "better/worse" —
    the backend does not classify metric direction.
  status: confirmed (matches the user-approved AskUserQuestion preview).
```

---

## Implementation Blueprint

### Backend — registry sort (`app/features/registry/service.py`)
```python
# IMPORTS to add: `from sqlalchemy.orm import InstrumentedAttribute`
# `Any` and `func, select` are already imported (lines 19, 22).

# Module level, after `logger = ...`. Mirror dimensions/service.py:32-45.
_RUN_SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "created_at": ModelRun.created_at,
    "model_type": ModelRun.model_type,
    "status": ModelRun.status,
    "store_id": ModelRun.store_id,
    "product_id": ModelRun.product_id,
}

# In list_runs: add params `sort_by: str | None = None`, `sort_order: str = "asc"`.
# Replace the line-300 order_by with the resolve-or-default block:
sort_column = _RUN_SORT_COLUMNS.get(sort_by) if sort_by else None
if sort_column is not None:
    order_by = sort_column.desc() if sort_order == "desc" else sort_column.asc()
else:
    order_by = ModelRun.created_at.desc()  # UNCHANGED default — keeps existing tests green
stmt = stmt.order_by(order_by).offset(offset).limit(page_size)
```

### Backend — registry route (`app/features/registry/routes.py`, in `list_runs`)
```python
# Add after the product_id Query param (mirror dimensions/routes.py:70-91):
sort_by: str | None = Query(
    None,
    description="Sort column: created_at|model_type|status|store_id|product_id. "
    "Unknown values use the default order.",
),
sort_order: str = Query("asc", pattern="^(asc|desc)$", description="Sort direction."),
# ...then thread sort_by=sort_by, sort_order=sort_order into service.list_runs(...).
```

### Backend — jobs sort (`app/features/jobs/service.py` + `routes.py`)
```python
# service.py — add `from sqlalchemy.orm import InstrumentedAttribute`; module-level:
_JOB_SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "created_at": Job.created_at,
    "completed_at": Job.completed_at,
    "job_type": Job.job_type,
    "status": Job.status,
}
# list_jobs: +sort_by/sort_order params; replace line-240 order_by with the same
# resolve-or-default block; default Job.created_at.desc().
# routes.py — list_jobs: +sort_by/sort_order Query params (after `status`),
# thread into service.list_jobs(...). completed_at is nullable — Postgres default
# NULLS LAST on .asc() is acceptable; do NOT add special null handling.
```

### Frontend — type (`frontend/src/types/api.ts`, after `RunCompareResponse`)
```typescript
// Response from GET /registry/runs/{run_id}/verify (SHA-256 integrity check).
// On a checksum mismatch the endpoint returns HTTP 200 with verified:false + error.
export interface ArtifactVerifyResponse {
  verified: boolean
  run_id: string
  artifact_uri: string
  stored_hash?: string
  computed_hash?: string
  error?: string
}
```

### Frontend — hooks (`use-runs.ts` / `use-jobs.ts`)
```typescript
// use-runs.ts — add to UseRunsParams: sortBy?: string; sortOrder?: 'asc' | 'desc'
// thread into useRuns queryKey + api params as sort_by / sort_order.
// New hook (mirror useCompareRuns at use-runs.ts:50-56):
export function useVerifyArtifact(runId: string, enabled = false) {
  return useQuery({
    queryKey: ['runs', runId, 'verify'],
    queryFn: () => api<ArtifactVerifyResponse>(`/registry/runs/${runId}/verify`),
    enabled: enabled && !!runId,
    retry: false,   // surface a 404 / mismatch immediately
  })
}
// use-jobs.ts — add sortBy/sortOrder to UseJobsParams, thread into useJobs the
// same way. Leave useJob's refetchInterval polling (lines 42-46) untouched.
```

### Frontend — JsonBlock (`frontend/src/components/common/json-block.tsx`)
```typescript
// Pure presentational. value: unknown; className?: string.
// null/undefined → a muted "—". Otherwise:
//   <pre class="max-h-96 overflow-auto rounded-md border bg-muted/40 p-3
//               text-xs font-mono whitespace-pre-wrap break-all">
//     {JSON.stringify(value, null, 2)}
//   </pre>
// No syntax-highlighter dependency. Add `export * from './json-block'` to
// components/common/index.ts.
```

### Frontend — run-detail page (`frontend/src/pages/explorer/run-detail.tsx`)
```text
export default function RunDetailPage()
- const { runId } = useParams(); guard !runId → ErrorDisplay "Invalid run".
- const runQuery = useRun(runId ?? '', !!runId); runQuery.error → ErrorDisplay + retry.
- const [verifyOn, setVerifyOn] = useState(false)
  const verifyQuery = useVerifyArtifact(runId ?? '', verifyOn)
- Header: "Back to Model Runs" Button-asChild-Link → ROUTES.EXPLORER.RUNS;
  <h1> mono run_id; StatusBadge variant={getStatusVariant(run.status)}.
- Profile Card (<dl> grid, mirror store-detail.tsx:108-133): model_type;
  store_id → Link `/explorer/stores/${store_id}`; product_id → Link
  `/explorer/products/${product_id}`; data window; config_hash (mono); git_sha;
  created_at / started_at / completed_at (format via date-fns).
- if status==='failed' && error_message → destructive-styled Card.
- Metrics Card: <JsonBlock value={run.metrics} />.
- Config Card: <JsonBlock value={run.model_config} /> + feature_config.
- Runtime Card: <JsonBlock value={run.runtime_info} />.
- Agent context Card: <JsonBlock value={run.agent_context} /> (render only if non-null).
- Artifact Card: artifact_uri, artifact_hash (mono), artifact_size_bytes;
  a "Verify integrity" Button — onClick: verifyOn ? verifyQuery.refetch() :
  setVerifyOn(true). disabled={!run.artifact_uri}. While verifyQuery.isFetching →
  spinner; verifyQuery.data?.verified===true → green check + computed_hash;
  verified===false OR verifyQuery.error → destructive alert.
- "Compare with…" Button-asChild-Link → `${ROUTES.EXPLORER.RUN_COMPARE}?a=${runId}`.
- Build with frontend-design + shadcn-ui; reuse LoadingState/ErrorDisplay.
```

### Frontend — job-detail page (`frontend/src/pages/explorer/job-detail.tsx`)
```text
export default function JobDetailPage()
- const { jobId } = useParams(); guard !jobId → ErrorDisplay.
- const jobQuery = useJob(jobId ?? '', !!jobId)  // already polls while pending/running
- Header: "Back to Jobs" Link → ROUTES.EXPLORER.JOBS; mono job_id; StatusBadge.
- Profile Card: job_type (capitalize); created_at/started_at/completed_at;
  run_id → if non-null, Link `/explorer/runs/${run_id}` (cross-link to run detail).
- Params Card: <JsonBlock value={job.params} />.
- Result Card: <JsonBlock value={job.result} /> — muted "No result yet" when
  result==null and status is pending/running.
- if status==='failed' → destructive Card with error_message + error_type.
- if status==='pending' → "Cancel job" Button wrapped in the AlertDialog
  confirmation copied from jobs.tsx:99-119, wired to useCancelJob.mutateAsync.
- GOTCHA: after cancel, also invalidate ['jobs', jobId] so this page reflects the
  cancelled status (useCancelJob.onSuccess currently invalidates only ['jobs']).
```

### Frontend — run-compare page (`frontend/src/pages/explorer/run-compare.tsx`)
```text
export default function RunComparePage()
- const [params, setParams] = useSearchParams()
  const a = params.get('a') ?? ''; const b = params.get('b') ?? ''
- Two run pickers: shadcn Select populated by useRuns({ page:1, pageSize:100 });
  each option label `${run_id.slice(0,8)} · ${model_type} · ${status}`.
  Selecting updates the URL via setParams → comparison is deep-linkable.
- const cmp = useCompareRuns(a, b, !!a && !!b)  // RunCompareResponse
- Empty state when !a || !b → Card prompting the user to pick two runs.
- Profile table: rows model_type / status / data window / config_hash / created_at
  from cmp.data.run_a vs run_b (side-by-side, Table component).
- config_diff Card: <JsonBlock value={cmp.data.config_diff} />.
- metrics_diff table: Object.entries(cmp.data.metrics_diff) → one row each:
  Metric | Run A (m.a) | Run B (m.b) | Δ (m.diff with ▲ if diff>0 / ▼ if diff<0 /
  "—" if diff==null). Guard nullable numbers. Do NOT colour-code better/worse.
- "Back to Model Runs" Link.
```

### list of tasks (in execution order)
```yaml
Task 1 — Tracking GitHub issue + branch:
  - Open ONE issue: "Explorer interactivity: Model Runs & Jobs detail views, run
    comparison, artifact verify, table sorting". Note scopes registry/jobs/ui/api/docs.
  - Confirm: `gh issue view <N> --json state` → OPEN. Every commit references (#N).
  - Branch: `git fetch origin && git switch -c
    feat/explorer-runs-jobs-interactivity origin/dev`.
  - GOTCHA: do NOT reuse the current local `feat/explorer-interactivity` branch
    (that is merged PRP-20). Branch fresh off `dev`.

Task 2 — Backend: registry sort params:
  MODIFY app/features/registry/service.py
    - Add `from sqlalchemy.orm import InstrumentedAttribute`.
    - Add module-level `_RUN_SORT_COLUMNS` (see Blueprint).
    - Add `sort_by`/`sort_order` params to `list_runs`; replace the line-300
      order_by with the resolve-or-default block.
  MODIFY app/features/registry/routes.py
    - Add `sort_by`/`sort_order` Query params to `list_runs` (after product_id);
      thread into `service.list_runs(...)`.
  VALIDATE: uv run ruff check app/features/registry/ &&
    uv run mypy app/features/registry/ && uv run pyright app/features/registry/ &&
    uv run python -c "from app.main import app"

Task 3 — Backend: jobs sort params:
  MODIFY app/features/jobs/service.py
    - Add `from sqlalchemy.orm import InstrumentedAttribute`.
    - Add module-level `_JOB_SORT_COLUMNS` (see Blueprint).
    - Add `sort_by`/`sort_order` params to `list_jobs`; replace the line-240
      order_by with the resolve-or-default block.
  MODIFY app/features/jobs/routes.py
    - Add `sort_by`/`sort_order` Query params to `list_jobs` (after status);
      thread into `service.list_jobs(...)`.
  VALIDATE: uv run ruff check app/features/jobs/ &&
    uv run mypy app/features/jobs/ && uv run pyright app/features/jobs/

Task 4 — Backend tests (registry sort + jobs DB infra & route tests):
  MODIFY app/features/registry/tests/test_routes.py
    - Add @pytest.mark.integration test(s): POST 3 runs with model_type
      "test-aaa"/"test-bbb"/"test-ccc"; GET /registry/runs?sort_by=model_type&
      sort_order=desc asserts descending; sort_by=metrics (unknown) falls back to
      default order, HTTP 200; omitted params == created_at desc.
  MODIFY app/features/jobs/tests/conftest.py
    - Copy `db_session` + `client` from registry/tests/conftest.py:26-79 VERBATIM,
      swapping the cleanup to `delete(Job).where(Job.job_id.like("test%"))`
      (import `Job` from app.features.jobs.models, `delete` from sqlalchemy).
    - Add a `sample_jobs_multi` fixture inserting 3 Job ORM rows directly:
      job_id=f"test{uuid.uuid4().hex[:28]}", distinct job_type + status, staggered
      created_at, params={} (JSONB non-null).
  CREATE app/features/jobs/tests/test_routes.py
    - @pytest.mark.integration class (mirror registry/tests/test_routes.py style):
      GET /jobs 200 happy path; GET /jobs?sort_by=job_type&sort_order=asc ordered;
      unknown sort_by → default order, 200; GET /jobs/{id} 200 + 404.
  GOTCHA: new .py file (test_routes.py) — run `git diff --stat` after, confirm no
    EOL churn. Integration tests need `docker compose up -d` + alembic upgrade head.
  VALIDATE:
    docker compose up -d && uv run alembic upgrade head &&
    uv run pytest -v -m integration app/features/registry/tests/test_routes.py
      app/features/jobs/tests/

Task 5 — Frontend: type + hooks:
  MODIFY frontend/src/types/api.ts — add `ArtifactVerifyResponse` (see Blueprint).
  MODIFY frontend/src/hooks/use-runs.ts — add sortBy/sortOrder to UseRunsParams +
    useRuns; add `useVerifyArtifact` hook; import ArtifactVerifyResponse.
  MODIFY frontend/src/hooks/use-jobs.ts — add sortBy/sortOrder to UseJobsParams +
    useJobs.
  VALIDATE: cd frontend && pnpm tsc --noEmit

Task 6 — Frontend: JsonBlock component:
  CREATE frontend/src/components/common/json-block.tsx (see Blueprint).
  MODIFY frontend/src/components/common/index.ts — add the barrel line.
  VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 7 — Frontend: routing:
  MODIFY frontend/src/lib/constants.ts — ROUTES.EXPLORER +=
    RUN_DETAIL:'/explorer/runs/:runId', JOB_DETAIL:'/explorer/jobs/:jobId',
    RUN_COMPARE:'/explorer/runs/compare'. Do NOT touch NAV_ITEMS.
  MODIFY frontend/src/App.tsx — 3 lazy imports (RunDetailPage, JobDetailPage,
    RunComparePage) + 3 <Route>s in <Suspense> inside <AppShell/>; register
    RUN_COMPARE before RUN_DETAIL.
  NOTE: pnpm tsc will fail here until Tasks 8-10 exist — re-run after Task 10.

Task 8 — Frontend: run-detail page:
  CREATE frontend/src/pages/explorer/run-detail.tsx (see Blueprint).
    Build with frontend-design + shadcn-ui.
  VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 9 — Frontend: job-detail page:
  CREATE frontend/src/pages/explorer/job-detail.tsx (see Blueprint).
  VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 10 — Frontend: run-compare page:
  CREATE frontend/src/pages/explorer/run-compare.tsx (see Blueprint).
  VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 11 — Frontend: interactive Runs table:
  MODIFY frontend/src/pages/explorer/runs.tsx
    - Convert useState filters/pagination → useSearchParams URL state (copy
      stores.tsx:57-127 — updateParams/handlePaginationChange/handleSortingChange/
      handleFilterChange/handleReset). URL keys: model_type, status, page,
      sort_by, sort_order.
    - Wrap sortable headers (status, model_type, store_id, product_id, created_at)
      in <DataTableColumnHeader>; set enableSorting:false on run_id, data_window,
      metrics.
    - Derive sortBy/sortOrder from sorting[0]; pass to useRuns; pass
      sorting/onSortingChange to DataTable.
    - useNavigate(); onRowClick={(run)=>navigate(`/explorer/runs/${run.run_id}`)}.
    - Add a "Compare runs" Button-asChild-Link → ROUTES.EXPLORER.RUN_COMPARE.
    - Keep the existing CSV export + enableColumnVisibility.
  VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 12 — Frontend: interactive Jobs table:
  MODIFY frontend/src/pages/explorer/jobs.tsx
    - Same URL-state conversion (keys: job_type, status, page, sort_by, sort_order).
    - Add `csvColumns: CsvColumn<Job>[]` (job_id, job_type, status, run_id,
      created_at, completed_at — exclude JSONB params/result) + "Export CSV"
      Button (mirror runs.tsx:71-80,106-108,157-162).
    - Add `enableColumnVisibility` to DataTable.
    - Sortable headers via DataTableColumnHeader (status, job_type, created_at,
      completed_at); job_id/params/actions non-sortable.
    - useNavigate(); onRowClick={(job)=>navigate(`/explorer/jobs/${job.job_id}`)}.
    - CRITICAL: wrap the `actions` cell content with
      onClick={(e)=>e.stopPropagation()} so the cancel AlertDialog does not also
      navigate to the job detail page.
  VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint &&
    cd frontend && pnpm test --run

Task 13 — Docs:
  MODIFY README.md — mention run/job detail pages, run comparison, artifact verify,
    table sorting in the feature list.
  MODIFY docs/_base/API_CONTRACTS.md — note the new sort_by/sort_order params on the
    GET /registry/runs and GET /jobs rows (mirror the /dimensions sort note from PRP-20).
  MODIFY docs/_base/REPO_MAP_INDEX.md — add rows for run-detail.tsx / job-detail.tsx /
    run-compare.tsx.

Task 14 — Dogfood the running UI (mandatory per ui-design.md):
  - docker compose up -d ; uv run alembic upgrade head ;
    uv run python scripts/seed_random.py --full-new --seed 42 --confirm.
  - Run `make demo` (or POST a few /jobs) so the registry + jobs tables have rows.
  - uv run uvicorn app.main:app --port 8123 & ; cd frontend &&
    ./node_modules/.bin/vite --host 0.0.0.0.
  - Via webapp-testing / agent-browser, exercise the 10 scenarios in Validation
    Level 4. Capture screenshots of all three new pages.

Task 15 — Commit + PR:
  Branch feat/explorer-runs-jobs-interactivity. Commits, each (#issue), no AI trailer:
    1. feat(registry): add sort_by/sort_order to model-run listing (#N)
    2. feat(jobs): add sort_by/sort_order to job listing (#N)
    3. test(registry,jobs): cover list-endpoint sorting (#N)
    4. feat(ui): add model-run and job detail pages (#N)
    5. feat(ui): add run-vs-run comparison page (#N)
    6. feat(ui): interactive Runs/Jobs tables — sorting, row-click, export, url state (#N)
    7. docs(docs): document explorer runs/jobs interactivity (#N)
  Open PR into dev; CI green; merge.
```

### Per-task pseudocode (highest-risk tasks)
```python
# Task 2/3 — the backend resolve-or-default ordering (registry shown; jobs identical)
async def list_runs(self, db, page=1, page_size=20, model_type=None, status=None,
                     store_id=None, product_id=None,
                     sort_by=None, sort_order="asc"):
    stmt = select(ModelRun)
    # ... existing filter .where() clauses UNCHANGED ...
    # ... existing count_stmt UNCHANGED ...
    offset = (page - 1) * page_size
    # PATTERN: allow-list resolve (dimensions/service.py:105-113). NEVER raw string.
    sort_column = _RUN_SORT_COLUMNS.get(sort_by) if sort_by else None
    if sort_column is not None:
        order_by = sort_column.desc() if sort_order == "desc" else sort_column.asc()
    else:
        order_by = ModelRun.created_at.desc()  # UNCHANGED default
    stmt = stmt.order_by(order_by).offset(offset).limit(page_size)
    # ... rest UNCHANGED ...
```
```typescript
// Task 8 — the verify button (the one piece of genuinely new UI logic)
const [verifyOn, setVerifyOn] = useState(false)
const verify = useVerifyArtifact(runId ?? '', verifyOn)
function onVerify() {
  if (!verifyOn) setVerifyOn(true)   // first click → enable the query
  else void verify.refetch()         // subsequent clicks → re-run
}
// render: verify.isFetching → spinner; verify.error → destructive alert (404/400);
//   verify.data?.verified === true → green check + verify.data.computed_hash;
//   verify.data?.verified === false → destructive alert + verify.data.error
```

### Integration Points
```yaml
DATABASE:  NONE — no migration, no schema change. ORDER BY only.
BACKEND:   registry slice — +2 query params, allow-listed ordering on list_runs.
           jobs slice — +2 query params, allow-listed ordering on list_jobs.
           app/main.py UNCHANGED (both routers already wired).
CONFIG:    NONE — no new env var.
FRONTEND ROUTING:
  - ROUTES.EXPLORER.RUN_DETAIL + JOB_DETAIL + RUN_COMPARE (constants.ts).
  - Three lazy <Route>s in App.tsx (:runId / :jobId / static compare).
  - NAV_ITEMS unchanged (detail/compare pages are click-through, not nav items).
CI:
  - No new workflow. ci.yml covers it. Because registry + jobs .py files change,
    the ruff/mypy/pyright/pytest jobs are load-bearing — keep green.
```

---

## Validation Loop

### Level 1: Syntax & Style
```bash
uv run ruff check . && uv run ruff format --check .
cd frontend && pnpm lint
# Expected: zero errors. Fix before proceeding.
```

### Level 2: Type Checks
```bash
uv run mypy app/ && uv run pyright app/        # both --strict, both gate merge
cd frontend && pnpm tsc --noEmit
# Watch: the InstrumentedAttribute import + _RUN_SORT_COLUMNS / _JOB_SORT_COLUMNS
# dict typing are the most likely strict-mode failures.
```

### Level 3: Unit + Integration Tests
```bash
uv run pytest -v -m "not integration"
docker compose up -d && uv run alembic upgrade head
uv run pytest -v -m integration app/features/registry/tests app/features/jobs/tests
cd frontend && pnpm test --run
# If integration tests fail on a stale local Postgres:
#   docker compose down -v && docker compose up -d && uv run alembic upgrade head
```

### Level 4: Manual end-to-end (dogfood — REQUIRED, ui-design.md)
```bash
docker compose up -d && uv run alembic upgrade head
uv run python scripts/seed_random.py --full-new --seed 42 --confirm
make demo                                       # populate registry + jobs tables
uv run uvicorn app.main:app --port 8123 &
until curl -fs http://127.0.0.1:8123/health; do sleep 2; done
cd frontend && ./node_modules/.bin/vite --host 0.0.0.0     # http://localhost:5173

# Browser checks via webapp-testing / agent-browser:
#  1. /explorer/runs → click a row → /explorer/runs/:id with profile, JSON
#     config, metrics, runtime info.
#  2. On a run detail page click "Verify integrity" → pass (or fail) result renders.
#  3. Click "Compare with…" → /explorer/runs/compare?a=<id>; pick a second run →
#     side-by-side + config_diff + metrics_diff render; URL carries ?a=&b=.
#  4. Sort the Runs table by Model Type desc → order changes ACROSS pages.
#  5. /explorer/jobs → click a row → /explorer/jobs/:id with params + result JSON.
#  6. On a pending job detail page click "Cancel job" → status → cancelled.
#  7. In the Jobs table, click a row's cancel ✕ → it cancels WITHOUT navigating.
#  8. Export the Jobs table to CSV; toggle a column off via "View".
#  9. Apply a filter + a sort on Runs, copy the URL, open in a new tab → identical.
# 10. curl "http://localhost:8123/jobs?sort_by=status&sort_order=desc" → 200, ordered.
```

---

## Final validation Checklist
- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run mypy app/ && uv run pyright app/` clean (both --strict)
- [ ] `uv run pytest -v -m "not integration"` green
- [ ] `uv run pytest -v -m integration app/features/registry/tests app/features/jobs/tests` green
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` clean
- [ ] `GET /registry/runs` & `GET /jobs` accept sort_by/sort_order; omitted == prior
      `created_at desc`; unknown sort_by → default order, no error
- [ ] Row-click on Runs/Jobs → working detail pages with JSON config/metrics/result
- [ ] Run comparison page renders config_diff + metrics_diff; deep-linkable via ?a=&b=
- [ ] "Verify integrity" button surfaces pass/fail incl. the verified:false branch
- [ ] Jobs table: CSV export + column visibility; in-row cancel does NOT navigate
- [ ] Filter/sort/page state round-trips through the URL on both tables
- [ ] No Alembic migration; no app/main.py change; no new slice; no .env var
- [ ] README + API_CONTRACTS.md + REPO_MAP_INDEX.md updated
- [ ] Branch `feat/explorer-runs-jobs-interactivity`; every commit references the
      Task-1 issue; no AI co-author trailer
- [ ] All three new pages dogfooded in a real browser (screenshots captured)

---

## Anti-Patterns to Avoid
- ❌ Don't add an Alembic migration — sorting is a read-only ORDER BY; the schema
  does not change.
- ❌ Don't interpolate `sort_by` into the query — resolve it through the allow-list
  dict to a real mapped column; unknown → default order, never 400.
- ❌ Don't put `metrics`/`runtime_info`/`params`/`result` (JSONB) in the sort
  allow-list — they cannot be ordered meaningfully.
- ❌ Don't do client-only table sorting — DataTable is `manualSorting:true`; sort
  MUST round-trip to the backend.
- ❌ Don't `Number()`-parse `:runId` / `:jobId` — they are UUID-hex strings, not
  integers (this differs from store-detail.tsx / product-detail.tsx).
- ❌ Don't forget `e.stopPropagation()` on the Jobs table's in-row cancel button —
  the row is now clickable.
- ❌ Don't re-implement a page-size selector — `data-table-pagination.tsx` has one.
- ❌ Don't edit `app/main.py` — both routers are already wired.
- ❌ Don't rebuild DataTable / DataTableColumnHeader / csv-export / store-detail —
  PRP-20 already shipped them; this PRP reuses them.
- ❌ Don't mock the database in integration tests; don't create test runs without a
  `test-` model_type prefix (registry cleanup) or test jobs without a `test`
  job_id prefix (jobs cleanup).
- ❌ Don't hand-roll the pages without `frontend-design` / `shadcn-ui`, and don't
  claim "done" on a green `tsc` — dogfood in a real browser.
- ❌ Don't `git push --force` on dev/main; no AI co-author trailers; every commit
  references the open issue.

---

## Confidence Score

**8 / 10** for one-pass implementation success.

**Why solid:**
- Almost entirely additive and mechanically patterned by PRP-20 — the backend
  change is a verbatim copy of the `dimensions` allow-listed-sort pattern; the
  three pages mirror `store-detail.tsx`; the table upgrades mirror `stores.tsx`;
  the routes register exactly like the existing Explorer detail routes.
- Every detail/compare/verify endpoint already exists and is tested — no new
  backend route, no new service method, no new schema. Three of four hooks
  (`useRun`/`useJob`/`useCompareRuns`) already exist; `DataTable` already supports
  `onRowClick`/`sorting`/`enableColumnVisibility`. Only `useVerifyArtifact`,
  `JsonBlock`, and `ArtifactVerifyResponse` are genuinely new.
- Every cited file carries verified line numbers; the real traps (UUID-vs-numeric
  id parsing, `stopPropagation` on the in-row cancel, the two test-cleanup prefix
  conventions, verify returning 200-on-mismatch) are called out with the exact fix.
- Validation gates are concrete, layered, and fast; the dogfood checklist has 10
  explicit scenarios.

**Why not higher:**
- The `jobs` slice has **no DB test infrastructure** — Task 4 must stand up
  `db_session`/`client` from scratch (copied from `registry`) plus a new
  `test_routes.py`. This is the least-mechanical task and the most likely to need
  a second pass (the same risk PRP-20 flagged for the `analytics` slice).
- The three new pages are genuine UI composition — layout, hierarchy, the
  verify-button state machine, and the URL-state sync need the real-browser
  dogfood (Task 14); a green `tsc` will not catch a cramped detail page or a
  dropped `useSearchParams` round-trip.
- ≈22 files across two layers is a wide surface; the per-task `VALIDATE` keeps it
  recoverable but a single clean pass is ambitious.

All identified risks are caught by the validation loop (strict type-check +
integration tests + browser dogfood) and the fixes are local. Executing the tasks
in order and running each `VALIDATE` before moving on is what carries it.
