name: "PRP-22 — Visualize: Demand Planner page + interactive Forecast/Backtest pages"
description: |
  Extend the **Visualize** menu of the ForecastLabAI dashboard from two flat,
  read-only job viewers into a business-facing demand surface — the direct
  successor to PRP-20/PRP-21 (Explorer interactivity), applied to the
  `analytics` slice and `frontend/src/pages/visualize/`:

  1. **New backend endpoint** — `GET /analytics/inventory-status` exposes the
     latest `inventory_snapshot_daily` row per `(store, product)` grain
     (`on_hand_qty`, `on_order_qty`, `is_stockout`). The inventory fact table
     has no HTTP surface today; the Demand Planner needs it to compute an
     inventory requirement. Additive — no migration, no new slice, no
     `app/main.py` change (the `analytics` router is already wired).

  2. **New page** — `Visualize → Demand Planner` (`/visualize/demand`). It reads
     every completed `predict` job, joins each to its product (SKU/name) and to
     the latest inventory snapshot, and shows a multi-SKU table:
     **tomorrow's sales** · **next week** · **next month** · **inventory
     requirement (`készletigény`)**. A row click opens a single-SKU drill-in
     with the daily demand curve and the reorder breakdown.

  3. **Interactivity** for the existing **Forecast** and **Backtest Results**
     pages — in-page job submission, a prediction-interval band toggle on the
     forecast chart, CSV export, and run/job cross-links.

  Hungarian terms in the source request map to: *holnapi eladás* → tomorrow's
  sales, *következő hét* → next week, *következő hónap* → next month,
  *SKU demand* → per-SKU demand, *készletigény* → inventory requirement. **All
  UI copy is English** — every existing page in this repo is English.

> **PRP numbering:** `PRP-16` is reserved (Phase-2 LightGBM). `PRP-17`–`PRP-21`
> are used. This is `PRP-22`. Source plan:
> `.agents/plans/visualize-demand-planner-and-interactivity.md`.

## Purpose
Close the "Visualize pages are terminal viewers" gap. Today `forecast.tsx` loads
one `predict` job and draws a line; `backtest.tsx` loads one `backtest` job and
shows metrics. Neither rolls a forecast up into business numbers, surfaces stock
context, exports, links to the originating run, or lets the user launch a job.
There is **no view that answers "how much will this SKU sell tomorrow / next week
/ next month, and do I have enough stock?"** — and `inventory_snapshot_daily`,
though populated by the seeder, is invisible to the API. PRP-20/PRP-21 made the
Explorer pages interactive; this PRP does the equivalent for the Visualize area
and adds the one missing read endpoint that a demand view requires.

## Core Principles
1. **Context is King** — every endpoint shape, hook name, schema field, service
   method, and pattern below is linked to a real source file + verified line
   numbers.
2. **Reuse existing patterns** — the endpoint mirrors `analytics`'s
   `get_timeseries`; the hook mirrors `use-timeseries.ts`; the page skeleton
   mirrors `forecast.tsx`; the drill-in mirrors `run-detail.tsx`; CSV reuses
   `csv-export.ts`.
3. **Additive only** — no Alembic migration (the inventory table already
   exists; the endpoint is read-only), no new slice, no new `.env` var, no
   `app/main.py` change (the `analytics` router is already wired).
4. **Strict gates honored** — `.py` files in the `analytics` slice change, so
   the repo-wide `ruff` / `mypy --strict` / `pyright --strict` / `pytest` CI
   jobs genuinely apply; the new endpoint ships with slice tests.
5. **UI through skills** — pages built via `frontend-design` + `shadcn-ui`,
   dogfooded via `webapp-testing` / `agent-browser` per
   `.claude/rules/ui-design.md`. A green `tsc` is NOT proof the UI works.

---

## Goal

**Backend (additive, no migration):**
- `GET /analytics/inventory-status` — optional `store_id` / `product_id` filters;
  returns the latest snapshot per `(store, product)` grain via Postgres
  `DISTINCT ON`; `200` + empty list on an empty table (never `404`).

**Frontend:**
- New route `/visualize/demand` + `Visualize → Demand Planner` nav entry.
- `demand.tsx` — a multi-SKU demand table built client-side from completed
  `predict` jobs, with a lead-time selector and a single-SKU drill-in panel.
- One new hook (`useInventoryStatus`), one new pure module (`demand-utils.ts` +
  tests), three new TS types (`InventoryStatusItem`, `InventoryStatusResponse`,
  `DemandRow`).
- `TimeSeriesChart` extended with an optional prediction-interval band
  (backward-compatible — new props default off).
- `forecast.tsx` / `backtest.tsx` upgraded: in-page job submission, CSV export,
  interval-band toggle (forecast), run/job cross-links.

## Why
- **Portfolio identity.** `.claude/rules/product-vision.md` principle 1 —
  "portfolio-grade, end-to-end … every phase ships working code". The system
  trains, backtests and registers models, but a reviewer cannot see what a
  forecast *means for the business* — only a raw daily array.
- **Demand-planner workflow.** "What do I sell tomorrow / this week / this
  month, and do I need to reorder?" is the core retail question; today it is
  unanswerable in-product.
- **Consistency.** Explorer pages have detail views, sorting, export and
  cross-links (PRP-20/21). The Visualize pages being read-only single-job
  viewers is a visible inconsistency.
- **Unlocks the inventory fact table.** `inventory_snapshot_daily` is seeded but
  has no API surface — this PRP gives it one, reusably.

## What
One new read-only `analytics` endpoint (+ tests), one new page, two page
refactors, one shared-chart change. No migration, no new slice, no `.env` var,
no `app/main.py` change.

### Success Criteria
- [ ] `GET /analytics/inventory-status` returns the latest snapshot per
      `(store, product)`; honours `store_id` / `product_id`; returns `200` with
      `items: []`, `total_items: 0` on an empty table.
- [ ] `Visualize → Demand Planner` lists every completed `predict` job as a SKU
      row with tomorrow / next-week / next-month demand + inventory requirement;
      a lead-time selector (7/14/30 d) recomputes the requirement live.
- [ ] A demand row click opens a drill-in with the SKU's daily demand curve, the
      reorder breakdown, and cross-links to the source job + (when present) the
      model run.
- [ ] The Forecast page can launch a `predict` job in-page (pick a completed
      `train` job + horizon); the interval-band toggle and CSV export work.
- [ ] The Backtest page can launch a `backtest` job in-page; CSV export of fold
      metrics works; the loaded job links to its job detail page.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy app/
      && uv run pyright app/` clean; `uv run pytest -v -m "not integration"` and
      the `analytics` integration tests green.
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` clean.
- [ ] No Alembic migration; no new slice; no `app/main.py` change; no `.env` var.
- [ ] The Demand Planner + both upgraded pages dogfooded in a real browser
      (screenshots captured).

---

## All Needed Context

### Documentation & References
```yaml
# ---- External docs ----
- url: https://docs.sqlalchemy.org/en/20/core/selectable.html#sqlalchemy.sql.expression.Select.distinct
  why: select(Model).distinct(col_a, col_b) renders Postgres DISTINCT ON.
  critical: The DISTINCT ON columns MUST be the leftmost ORDER BY columns —
    order_by(store_id, product_id, date.desc()) then .distinct(store_id,
    product_id) gives the latest row per grain. Wrong order → SQL error.

- url: https://www.postgresql.org/docs/16/sql-select.html#SQL-DISTINCT
  why: DISTINCT ON semantics — keeps the first row of each distinct group as
    defined by ORDER BY. This is how "latest snapshot per grain" is expressed.

- url: https://tanstack.com/query/latest/docs/framework/react/guides/queries
  why: useQuery shape for the new useInventoryStatus hook. The repo hooks
    (use-timeseries.ts, use-jobs.ts) follow this exactly — copy that shape.

- url: https://tanstack.com/query/latest/docs/framework/react/guides/mutations
  why: useCreateJob (use-jobs.ts:55-64) is a useMutation; the in-page "Run new…"
    buttons call .mutateAsync then point the page at the returned job_id.

- url: https://recharts.org/en-US/api/Area
  why: the prediction-interval band. An <Area> whose dataKey returns a tuple
    [lower, upper] renders a range band. Forecast line + band needs a
    <ComposedChart> (Area + Line together), not a plain <LineChart>.
  critical: recharts is pinned at 2.15.4 (frontend/package.json) — ComposedChart
    and range-Area both exist in 2.15.x. If the range-dataKey form is uncertain,
    confirm via the contex7 MCP (resolve-library-id "recharts" → query-docs
    "ComposedChart Area range band").

- url: https://reactrouter.com/en/main/hooks/use-params
  why: react-router-dom is v7.13.0 — useParams() for an optional drill-in id if
    the drill-in is ever promoted to its own route (not required for the MVP;
    the drill-in is an in-page panel).

# ---- THE sibling PRPs to mirror ----
- file: PRPs/PRP-21-explorer-runs-jobs-interactivity.md
  why: the immediate precedent. Read its "Known Gotchas", "list of tasks",
    "Validation Loop" and "Anti-Patterns" — this PRP applies the same shape to
    the analytics slice + visualize pages. PRP-21 added csv-export.ts usage,
    cross-links, and detail-page patterns — all REUSED here, not rebuilt.
- file: PRPs/PRP-20-explorer-interactivity.md
  why: PRP-20 introduced revenue-bar-chart.tsx, json-block.tsx, csv-export.ts,
    use-timeseries.ts, use-lifecycle-curve.ts and the store/product detail
    pages — the exact patterns this PRP composes.

# ---- Backend: the analytics slice (gets the new endpoint) ----
- file: app/features/analytics/routes.py
  why: get_timeseries (lines 259-345) is the EXACT template — APIRouter,
    Query(...) params, rich docstring, `service = AnalyticsService()` call.
    The router is `APIRouter(prefix="/analytics", tags=["analytics"])` (line 26).
  critical: inventory-status has NO date params, so do NOT call
    validate_date_range (lines 34-59) — that helper is for date-range endpoints.

- file: app/features/analytics/service.py
  why: AnalyticsService.compute_kpis (lines 43-90) — the SQLAlchemy 2.0 async
    `select(...).where(...)`, `await db.execute(stmt)`, settings + logger style
    to mirror for compute_inventory_status. Imports at lines 10-27.

- file: app/features/analytics/schemas.py
  why: TimeSeriesPoint / TimeSeriesResponse (lines 199-255) — the response-schema
    shape to mirror: `model_config = ConfigDict(from_attributes=True)`, rich
    `Field(..., description=...)`, echoed filter fields, a `total_*` count.

- file: app/features/data_platform/models.py
  why: InventorySnapshotDaily (lines 345-381) — the table queried. Columns:
    `id`, `date` (FK calendar.date), `store_id` (FK store.id), `product_id`
    (FK product.id), `on_hand_qty:int`, `on_order_qty:int default 0`,
    `is_stockout:bool default False`. Unique grain (date, store_id, product_id).

- file: app/features/analytics/tests/test_routes_integration.py
  why: integration-test layout — `@pytest.mark.integration`, `@pytest.mark.asyncio`,
    class-grouped, uses the `client` fixture + seeded fixtures. Add a
    `TestAnalyticsInventoryStatusIntegration` class here (lines 21-58 style).

- file: app/features/analytics/tests/conftest.py
  why: fixtures — `db_session` (lines 99-130), `client` (133-148), `sample_store`
    (151-165), `sample_product` (168-183), `sample_calendar_120` (186-206).
  critical: the db_session cleanup (lines 119-128) deletes ALL SalesDaily, then
    `Product`/`Store` rows with a `TEST-` code/sku, then Calendar in
    2024-01-01..2024-04-29 — it does NOT delete InventorySnapshotDaily. A new
    `sample_inventory` fixture MUST add `delete(InventorySnapshotDaily)` to that
    cleanup BEFORE the Store/Product/Calendar deletes (FK order), or rows leak /
    FK-block. See Gotchas.

- file: app/features/analytics/tests/test_schemas.py
  why: schema unit-test pattern for the new InventoryStatus* schemas.

- file: app/main.py
  why: the analytics router is ALREADY wired (`analytics_router` import line 17,
    `app.include_router(analytics_router)` line 133). NO main.py change needed.

# ---- Backend: job-result + job-param contracts (read-only — do NOT change) ----
- file: app/features/jobs/service.py
  why:
    - _execute_predict (lines 493-560): a completed `predict` job stores
      `result = {store_id, product_id, model_type, horizon,
      forecasts:[{date:isostr, forecast:float, lower_bound?, upper_bound?}]}`.
      The Demand Planner + Forecast page consume exactly this.
    - _execute_train (lines ~400-491): a completed `train` job stores
      `result = {run_id, model_type, model_path, config_hash, n_observations,
      train_start_date, train_end_date, store_id, product_id, duration_ms}`.
      `run_id` is the ARTIFACT key (model_{run_id}.joblib), NOT a registry run.
    - _execute_predict params contract: `{run_id:str, horizon:int}` — `run_id`
      MUST be a train job's `result.run_id`.
    - _execute_backtest (lines 569-655) params contract: `{model_type, store_id,
      product_id, start_date, end_date, n_splits?(=5), test_size?(=14),
      gap?(=0), season_length?(=7), window_size?(=7)}`; dates accepted as ISO
      strings. Result shaped by _shape_backtest_result (lines 71-136).
  critical: forecasting/service.py does NOT touch the registry — training does
    not create a `model_run` row. The in-page "Run new forecast" MUST pick a
    completed `train` job and submit its `result.run_id`; a registry run_id from
    `useRuns` would NOT resolve to a model artifact. See Gotchas.

- file: app/features/forecasting/schemas.py
  why: PredictRequest / ForecastPoint / PredictResponse (lines 227-289) —
    `horizon` bounded 1..90; ForecastPoint has optional `lower_bound`/
    `upper_bound`.

# ---- Frontend: pages being upgraded / mirrored ----
- file: frontend/src/pages/visualize/forecast.tsx
  why: the page upgraded in Tasks 11-12. Current: JobPicker (jobType="predict")
    + useJob + TimeSeriesChart. The forecast array is read defensively as
    `job?.result?.forecasts as Array<{date,forecast}> | undefined` (line 17).
- file: frontend/src/pages/visualize/backtest.tsx
  why: the page upgraded in Task 13. Current: JobPicker (jobType="backtest") +
    BacktestResult interface (11-30) + MetricsSummary + BacktestFoldsChart.
- file: frontend/src/pages/explorer/run-detail.tsx
  why: THE detail/drill-in template — header with back-Link, `Field` helper
    (lines 27-34), Card sections, cross-`Link` to `/explorer/stores|products`,
    LoadingState/ErrorDisplay. Mirror for the Demand Planner drill-in panel.
- file: frontend/src/pages/explorer/runs.tsx
  why: a working interactive table page (for the demand table layout reference).

# ---- Frontend: components (REUSED, not built) ----
- file: frontend/src/components/charts/time-series-chart.tsx
  why: the chart extended in Task 10. Props actualKey/predictedKey/showActual/
    showPredicted/height. Note the oklch `var(--color-*)` comment (lines 42-43)
    — wrapping in hsl() renders black.
- file: frontend/src/components/common/job-picker.tsx
  why: JobPicker — a `useJobs`-backed Select + manual-id entry. Its prop type is
    `jobType: Extract<JobType,'predict'|'backtest'>` (line 18) — WIDEN it to
    include `'train'` for the in-page-forecast train-job picker.
- file: frontend/src/components/ui/table.tsx
  why: the plain shadcn Table (Table/TableHeader/TableBody/TableRow/TableCell/
    TableHead). Use THIS for the demand table — see Gotchas (DataTable is
    server-paginated; the demand rows are client-derived).
- file: frontend/src/components/ui/select.tsx
  why: shadcn Select for the lead-time selector + the in-page-run model/store/
    product pickers.
- file: frontend/src/components/ui/checkbox.tsx
  why: the interval-band toggle on the Forecast page.
- file: frontend/src/components/common/date-range-picker.tsx
  why: DateRangePicker (value: DateRange from react-day-picker, onChange) — for
    the in-page backtest date window.
- file: frontend/src/components/common/error-display.tsx
  why: ErrorDisplay + EmptyState — used for the three page states.
- file: frontend/src/components/common/loading-state.tsx
  why: LoadingState.
- file: frontend/src/components/common/status-badge.tsx
  why: StatusBadge for the stockout / partial-horizon badges.
- file: frontend/src/components/charts/kpi-card.tsx
  why: KPICard (title, value, icon?) — OPTIONAL, for the tomorrow/week/month
    headline tiles in the drill-in.

# ---- Frontend: hooks / libs ----
- file: frontend/src/hooks/use-timeseries.ts
  why: THE hook shape to copy verbatim for use-inventory.ts — useQuery,
    `queryKey` array, `api<T>('/path',{params})`, keepPreviousData, enabled.
- file: frontend/src/hooks/use-jobs.ts
  why: useJob (polls 2s while pending/running), useJobs, useCreateJob (mutation).
- file: frontend/src/hooks/use-products.ts
  why: useProducts({page,pageSize,...}) → ProductListResponse{products:Product[]}.
- file: frontend/src/hooks/use-stores.ts
  why: useStores — for the in-page backtest store picker (mirror use-products).
- file: frontend/src/lib/api.ts
  why: `api<T>(endpoint,{params,method,body})` (drops undefined/null/'' params),
    formatNumber/formatCurrency/formatPercent, getErrorMessage, ApiError.
- file: frontend/src/lib/csv-export.ts
  why: toCsv(rows, columns) + downloadCsv(filename, csv) + CsvColumn<T>
    (`key: keyof T & string`, `header`) — reused for both export buttons.
- file: frontend/src/lib/csv-export.test.ts
  why: vitest pattern for the new demand-utils.test.ts.
- file: frontend/src/lib/constants.ts
  why: ROUTES.VISUALIZE (lines 21-24) + the `Visualize` NAV_ITEMS submenu
    (lines 45-51) — add DEMAND here.
- file: frontend/src/App.tsx
  why: lazy imports (23-24) + the ROUTES.VISUALIZE.FORECAST <Route> block
    (137-144) — add the demand page identically.
- file: frontend/src/types/api.ts
  why: existing Job (183-196), JobCreate (202-205), JobType (180), Product
    (25-35), ProductListResponse (37-39). Add InventoryStatusItem,
    InventoryStatusResponse, DemandRow.

# ---- Rules ----
- file: .claude/rules/ui-design.md
  why: UI built via frontend-design + shadcn-ui; dogfooded via webapp-testing /
    agent-browser. A green tsc is NOT proof the UI works.
- file: .claude/rules/security-patterns.md
  why: GET endpoint, Pydantic-validated Query params, SQLAlchemy parameter
    binding (no raw SQL). No request body ⇒ the strict-mode date rule does not
    apply.
- file: .claude/rules/test-requirements.md
  why: new endpoint → route test (2xx + 1 error/edge path); new pure utils →
    unit tests; new stateful component → a vitest test; integration tests run
    against real Postgres, never mocked.
- file: .claude/rules/commit-format.md & branch-naming.md
  why: `type(scope): description (#issue)`; scopes `analytics`/`ui`/`docs`;
    branch `feat/ui-visualize-demand-planner` off `dev`; open the issue FIRST.
```

### Current Codebase tree (relevant)
```bash
app/features/analytics/
├── routes.py                    # MOD — +GET /inventory-status
├── service.py                   # MOD — +compute_inventory_status
├── schemas.py                   # MOD — +InventoryStatusItem/Response
└── tests/
    ├── conftest.py              # MOD — +sample_inventory, +inventory cleanup
    ├── test_routes_integration.py  # MOD — +TestAnalyticsInventoryStatusIntegration
    └── test_schemas.py          # MOD — +inventory schema unit tests

frontend/src/
├── App.tsx                      # MOD — +1 lazy route (demand)
├── lib/
│   ├── constants.ts             # MOD — +ROUTES.VISUALIZE.DEMAND + nav entry
│   ├── demand-utils.ts          # NEW — pure rollup/inventory math
│   └── demand-utils.test.ts     # NEW — vitest unit tests
├── types/api.ts                 # MOD — +InventoryStatusItem/Response, DemandRow
├── hooks/use-inventory.ts       # NEW — useInventoryStatus
├── components/
│   ├── charts/time-series-chart.tsx   # MOD — +optional interval band
│   └── common/job-picker.tsx          # MOD — widen jobType to include 'train'
└── pages/visualize/
    ├── demand.tsx               # NEW — Demand Planner page
    ├── forecast.tsx             # MOD — in-page run, interval toggle, CSV, links
    └── backtest.tsx             # MOD — in-page run, CSV, links
```

### Desired Codebase tree (files added / changed)
```bash
NEW  frontend/src/lib/demand-utils.ts            # sumWindow/rollups/inventoryRequirement/joinDemandRows
NEW  frontend/src/lib/demand-utils.test.ts       # vitest unit tests
NEW  frontend/src/hooks/use-inventory.ts         # useInventoryStatus query hook
NEW  frontend/src/pages/visualize/demand.tsx     # /visualize/demand page
MOD  app/features/analytics/schemas.py           # +InventoryStatusItem/Response
MOD  app/features/analytics/service.py           # +compute_inventory_status
MOD  app/features/analytics/routes.py            # +GET /inventory-status
MOD  app/features/analytics/tests/conftest.py    # +sample_inventory + cleanup
MOD  app/features/analytics/tests/test_routes_integration.py  # +inventory tests
MOD  app/features/analytics/tests/test_schemas.py             # +schema tests
MOD  frontend/src/types/api.ts                   # +3 types
MOD  frontend/src/lib/constants.ts               # +route + nav entry
MOD  frontend/src/App.tsx                        # +1 lazy route
MOD  frontend/src/components/charts/time-series-chart.tsx  # +interval band
MOD  frontend/src/components/common/job-picker.tsx         # widen jobType
MOD  frontend/src/pages/visualize/forecast.tsx   # interactivity
MOD  frontend/src/pages/visualize/backtest.tsx   # interactivity
MOD  README.md                                   # feature list
MOD  docs/_base/API_CONTRACTS.md                 # +/analytics/inventory-status row
MOD  docs/_base/REPO_MAP_INDEX.md                # +demand.tsx row
KEEP app/main.py                                 # UNCHANGED — analytics router wired
KEEP alembic/**                                  # UNCHANGED — NO migration (read-only endpoint)
```

### Known Gotchas & Library Quirks
```python
# CRITICAL: NO Alembic migration. inventory_snapshot_daily already exists; the
#   endpoint is a read-only SELECT. `.claude/rules` require a migration only when
#   the SCHEMA changes. Adding one would be wrong.

# CRITICAL: NO app/main.py change. The analytics router is already wired
#   (main.py:17, 133). The new endpoint attaches to the existing analytics
#   APIRouter in routes.py.

# CRITICAL: Postgres DISTINCT ON. select(InventorySnapshotDaily)
#   .order_by(store_id, product_id, date.desc()).distinct(store_id, product_id)
#   → "SELECT DISTINCT ON (store_id, product_id) ... ORDER BY store_id,
#   product_id, date DESC". The DISTINCT ON columns MUST lead the ORDER BY or
#   Postgres errors. This yields the latest snapshot per grain.

# CRITICAL: a `train` job's result.run_id is the ARTIFACT key
#   (model_{run_id}.joblib), NOT a registry model_run id. forecasting/service.py
#   never writes to the registry. So the in-page "Run new forecast" picks a
#   completed `train` JOB and submits `{run_id: trainJob.result.run_id,
#   horizon}` as a `predict` job. Do NOT use useRuns / a registry RunPicker —
#   those ids will FileNotFoundError in _execute_predict.

# CRITICAL: the analytics db_session cleanup (conftest.py:119-128) deletes
#   SalesDaily, TEST- Store/Product, and Calendar 2024-01-01..2024-04-29 — it
#   does NOT touch InventorySnapshotDaily. The sample_inventory fixture's rows
#   FK-reference calendar.date / store.id / product.id, so the cleanup MUST gain
#   `await session.execute(delete(InventorySnapshotDaily))` as the FIRST delete
#   (before Store/Product/Calendar) or the run leaks rows / hits an FK error.
#   Import InventorySnapshotDaily in conftest.py.

# CRITICAL: a predict job defaults to horizon=14. "Next month" (30 d) is
#   therefore usually a PARTIAL sum. demand-utils must return a
#   `nextMonthPartial: boolean` and the table must badge it — never report a
#   misleadingly low absolute number as if it were a full month.

# GOTCHA: use the plain shadcn <Table> (components/ui/table.tsx) for the demand
#   table, NOT the Explorer <DataTable>. DataTable is built for server-paginated
#   data with `manualSorting:true`; the demand rows are derived client-side from
#   completed predict jobs (≤50). A plain Table + a small useMemo client-side
#   sort is correct and lower-risk.

# GOTCHA: Job.result is typed `Record<string,unknown> | null` (types/api.ts:188).
#   Narrow defensively — `job.result?.forecasts as ForecastPoint[] | undefined`
#   — exactly as forecast.tsx:17 already does. A SKU whose predict job has no
#   inventory row must still render (requirement = "unknown", not a crash).

# GOTCHA: the prediction-interval band needs recharts <ComposedChart> (Area +
#   Line together). A plain <LineChart> cannot host an <Area>. Keep TimeSeriesChart
#   backward-compatible: ComposedChart renders Lines identically; the band is
#   gated behind `showInterval` (default false) so existing callers are unaffected.

# GOTCHA: JobPicker's prop type is Extract<JobType,'predict'|'backtest'> — widen
#   to Extract<JobType,'train'|'predict'|'backtest'> so the in-page-forecast
#   train-job picker compiles. jobLabel() already handles any job.

# GOTCHA: useCreateJob (use-jobs.ts:55-64) is a mutation returning the new Job;
#   after .mutateAsync, set the page's searchJobId to job.job_id — useJob then
#   auto-polls while pending/running (use-jobs.ts:48-52).

# GOTCHA: new .ts/.tsx files are LF. Editing existing .py files must PRESERVE
#   their CRLF (repo .py files are CRLF, no .gitattributes — project memory).
#   After editing run `git diff --stat` and confirm no whole-file EOL churn.

# GOTCHA: every commit references the open tracking issue (commit-format.md);
#   NO AI co-author trailer, ever. Branch off `dev`.
```

### Resolved Decisions (user-confirmed 2026-05-18)
```yaml
keszletigeny-calculation:
  decision: add the read-only GET /analytics/inventory-status endpoint;
    inventory requirement = max(0, leadTimeDemand - on_hand_qty - on_order_qty).
  status: confirmed (AskUserQuestion — "Add inventory endpoint").
demand-page-scope:
  decision: multi-SKU table aggregating ALL recent completed predict jobs, with
    a single-SKU drill-in panel — not a single-SKU-only view.
  status: confirmed (AskUserQuestion — "Multi-SKU table + drill-in").
interactivity-scope:
  decision: all four upgrades ship on the Forecast/Backtest pages — in-page
    job submission, prediction-interval band, CSV export, run/job cross-links.
  status: confirmed (AskUserQuestion — multi-select, all four).
ui-language:
  decision: all UI copy is English. The Hungarian request terms map to
    Tomorrow / Next week / Next month / SKU demand / Inventory requirement.
  status: derived — every existing page in the repo is English.
```

---

## Implementation Blueprint

### Data models — backend schemas (`app/features/analytics/schemas.py`)
```python
# Append after TimeSeriesResponse. Mirror TimeSeriesPoint/TimeSeriesResponse.
class InventoryStatusItem(BaseModel):
    """Latest inventory snapshot for one (store, product) grain."""
    model_config = ConfigDict(from_attributes=True)

    store_id: int = Field(..., description="Store ID.")
    product_id: int = Field(..., description="Product ID.")
    date: date = Field(..., description="Snapshot date (latest available).")
    on_hand_qty: int = Field(..., ge=0, description="Units on hand end-of-day.")
    on_order_qty: int = Field(..., ge=0, description="Units inbound / on order.")
    is_stockout: bool = Field(..., description="True when on_hand_qty is 0.")


class InventoryStatusResponse(BaseModel):
    """Latest inventory snapshot per (store, product) grain."""
    items: list[InventoryStatusItem] = Field(..., description="One item per grain.")
    total_items: int = Field(..., ge=0, description="Number of items returned.")
    store_id: int | None = Field(None, description="Store filter applied, if any.")
    product_id: int | None = Field(None, description="Product filter applied, if any.")
```

### Data models — frontend types (`frontend/src/types/api.ts`, after TimeSeriesResponse)
```typescript
// GET /analytics/inventory-status — latest snapshot per (store, product).
export interface InventoryStatusItem {
  store_id: number
  product_id: number
  date: string            // ISO date
  on_hand_qty: number
  on_order_qty: number
  is_stockout: boolean
}
export interface InventoryStatusResponse {
  items: InventoryStatusItem[]
  total_items: number
  store_id: number | null
  product_id: number | null
}
// Client-derived view-model row for the Demand Planner table (camelCase — not a
// wire contract). One per completed predict job.
export interface DemandRow {
  jobId: string
  runId: string | null
  storeId: number
  productId: number
  sku: string
  productName: string
  modelType: string
  horizon: number
  tomorrow: number
  nextWeek: number
  nextMonth: number
  nextMonthPartial: boolean
  onHand: number | null     // null when no inventory snapshot exists
  onOrder: number | null
  isStockout: boolean
  inventoryRequirement: number | null  // null when stock is unknown
  forecasts: { date: string; forecast: number; lower_bound?: number; upper_bound?: number }[]
}
```

### Backend service (`app/features/analytics/service.py`)
```python
# IMPORTS: add InventorySnapshotDaily to the data_platform import; add the two
#   new schema names. `select` is already imported.

async def compute_inventory_status(
    self, db: AsyncSession, store_id: int | None = None, product_id: int | None = None,
) -> InventoryStatusResponse:
    # PATTERN: compute_kpis (service.py:43-90) — async select + filter chaining.
    stmt = (
        select(InventorySnapshotDaily)
        .order_by(
            InventorySnapshotDaily.store_id,
            InventorySnapshotDaily.product_id,
            InventorySnapshotDaily.date.desc(),
        )
        .distinct(InventorySnapshotDaily.store_id, InventorySnapshotDaily.product_id)
    )
    if store_id is not None:
        stmt = stmt.where(InventorySnapshotDaily.store_id == store_id)
    if product_id is not None:
        stmt = stmt.where(InventorySnapshotDaily.product_id == product_id)

    rows = (await db.execute(stmt)).scalars().all()
    items = [InventoryStatusItem.model_validate(r) for r in rows]
    logger.info("analytics.inventory_status_computed", count=len(items), store_id=store_id)
    return InventoryStatusResponse(
        items=items, total_items=len(items), store_id=store_id, product_id=product_id,
    )
```

### Backend route (`app/features/analytics/routes.py`)
```python
# Add InventoryStatusResponse to the schema import block, then append:
@router.get(
    "/inventory-status",
    response_model=InventoryStatusResponse,
    summary="Latest inventory snapshot per store/product",
    description="""Return the most recent inventory_snapshot_daily row for each
(store, product) grain — on-hand units, on-order units, stockout flag. Optional
store_id / product_id filters. Returns an empty list (HTTP 200) when no
snapshots exist.""",
)
async def get_inventory_status(
    store_id: int | None = Query(None, description="Filter by store ID."),
    product_id: int | None = Query(None, description="Filter by product ID."),
    db: AsyncSession = Depends(get_db),
) -> InventoryStatusResponse:
    service = AnalyticsService()
    return await service.compute_inventory_status(
        db=db, store_id=store_id, product_id=product_id,
    )
```

### Frontend hook (`frontend/src/hooks/use-inventory.ts`) — mirror use-timeseries.ts
```typescript
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { InventoryStatusResponse } from '@/types/api'

interface UseInventoryParams { storeId?: number; productId?: number; enabled?: boolean }

export function useInventoryStatus({ storeId, productId, enabled = true }: UseInventoryParams) {
  return useQuery({
    queryKey: ['inventory-status', { storeId, productId }],
    queryFn: () => api<InventoryStatusResponse>('/analytics/inventory-status', {
      params: { store_id: storeId, product_id: productId },
    }),
    placeholderData: keepPreviousData,
    enabled,
  })
}
```

### Frontend pure utils (`frontend/src/lib/demand-utils.ts`)
```typescript
// All pure, no React. ForecastPoint = {date, forecast, lower_bound?, upper_bound?}.
export function sumWindow(forecasts: { forecast: number }[], days: number): number {
  return forecasts.slice(0, days).reduce((s, p) => s + p.forecast, 0)
}
export function rollups(forecasts: { forecast: number }[]) {
  return {
    tomorrow: forecasts[0]?.forecast ?? 0,
    nextWeek: sumWindow(forecasts, 7),
    nextMonth: sumWindow(forecasts, 30),
    nextMonthPartial: forecasts.length < 30,
  }
}
// units to reorder; 0 when covered; null when stock is unknown.
export function inventoryRequirement(
  leadTimeDemand: number, onHand: number | null, onOrder: number | null,
): number | null {
  if (onHand === null) return null
  return Math.max(0, Math.round(leadTimeDemand - onHand - (onOrder ?? 0)))
}
// joinDemandRows(predictJobs, products, inventoryItems, leadTimeDays) -> DemandRow[]
//   - key inventory + product by (store_id, product_id) / product id into Maps
//   - leadTimeDemand = sumWindow(forecasts, leadTimeDays)
//   - skip predict jobs whose result has no forecasts array
```

### Demand Planner page (`frontend/src/pages/visualize/demand.tsx`)
```text
export default function DemandPlannerPage()
- const [leadTime, setLeadTime] = useState(14)            // 7 | 14 | 30
- const [selectedJobId, setSelectedJobId] = useState('')   // drill-in target
- const jobsQuery = useJobs({ jobType:'predict', status:'completed', page:1, pageSize:50 })
- const productsQuery = useProducts({ page:1, pageSize:500 })
- const invQuery = useInventoryStatus({})
- const rows: DemandRow[] = useMemo(() => joinDemandRows(
    jobsQuery.data?.jobs ?? [], productsQuery.data?.products ?? [],
    invQuery.data?.items ?? [], leadTime), [deps])
- States: LoadingState while any query loads; ErrorDisplay on error;
  EmptyState when rows.length === 0 ("No completed forecasts — run one on the
  Forecast page", link to ROUTES.VISUALIZE.FORECAST).
- Header card: <h1>Demand Planner</h1> + a lead-time <Select> (7/14/30 days).
- Multi-SKU <Table> (components/ui/table.tsx): columns SKU · Product · Tomorrow
  · Next week · Next month · On hand · Inventory need. Numbers via formatNumber.
  Badge is_stockout (destructive) and nextMonthPartial ("partial"). Clickable
  rows set selectedJobId. An "Export CSV" Button → downloadCsv('demand.csv',
  toCsv(rows, [...CsvColumn<DemandRow>])).
- Client-side sort: a useState sort key + a useMemo sorted copy; clickable
  <TableHead> cells.
- Drill-in panel (Card, shown when selectedJobId set): the selected row's
  TimeSeriesChart (data=forecasts, predictedKey="forecast", showActual=false),
  a reorder breakdown (leadTimeDemand - onHand - onOrder = need, via the `Field`
  helper pattern from run-detail.tsx), and cross-Links to
  `/explorer/jobs/${jobId}` and (when runId) `/explorer/runs/${runId}`.
- Build with frontend-design + shadcn-ui.
```

### TimeSeriesChart interval band (`frontend/src/components/charts/time-series-chart.tsx`)
```text
- Add optional props: lowerKey?: string, upperKey?: string, showInterval = false.
- Swap <LineChart> → <ComposedChart> (recharts) — Lines render identically.
- When showInterval && lowerKey && upperKey: render an <Area> whose dataKey is a
  function returning [row[lowerKey], row[upperKey]] (recharts range area), low
  fillOpacity, drawn BEFORE the forecast <Line> so the line sits on top.
- All current props/behaviour unchanged; existing callers omit the new props.
```

### Forecast page interactivity (`frontend/src/pages/visualize/forecast.tsx`)
```text
- "Run new forecast" Card: a JobPicker(jobType="train") to choose a completed
  train job + a horizon <Select>/input (1..90) + a "Run forecast" Button →
  useCreateJob().mutateAsync({ job_type:'predict',
  params:{ run_id: trainJob.result.run_id, horizon } }); on success
  setSearchJobId(newJob.job_id). EmptyState/disabled when no train jobs exist.
- Interval toggle: a <Checkbox> "Show prediction interval" → TimeSeriesChart
  showInterval/lowerKey="lower_bound"/upperKey="upper_bound"; disable the toggle
  when the loaded forecast points carry no bounds.
- "Export CSV" Button → downloadCsv(`forecast-${jobId}.csv`, toCsv(forecastData,
  [{key:'date',header:'Date'},{key:'forecast',header:'Forecast'},
   {key:'lower_bound',header:'Lower'},{key:'upper_bound',header:'Upper'}])).
- Cross-links in the Job Details card: Link to `/explorer/jobs/${job.job_id}`
  and, when job.result.run_id exists, `/explorer/runs/${run_id}`.
```

### Backtest page interactivity (`frontend/src/pages/visualize/backtest.tsx`)
```text
- "Run new backtest" Card: store <Select> (useStores), product <Select>
  (useProducts), model_type <Select> (naive|seasonal_naive|moving_average),
  <DateRangePicker>, n_splits + test_size inputs (defaults 5 / 14) → useCreateJob()
  .mutateAsync({ job_type:'backtest', params:{ model_type, store_id, product_id,
  start_date, end_date, n_splits, test_size } }); on success point searchJobId
  at the new job. (Re-verify the params keys against _execute_backtest first.)
- "Export CSV" Button → downloadCsv(`backtest-${jobId}.csv`,
  toCsv(backtestResult.fold_metrics, [{key:'fold',header:'Fold'},
  {key:'mae',...},{key:'smape',...},{key:'wape',...},{key:'bias',...}])).
- Cross-link: Link the loaded job to `/explorer/jobs/${job.job_id}`.
```

### list of tasks (in execution order)
```yaml
Task 1 — Tracking GitHub issue + branch:
  - Open ONE issue: "Visualize: Demand Planner page + interactive Forecast/
    Backtest pages". Scopes: analytics / ui / docs.
  - Confirm `gh issue view <N> --json state` → OPEN. Every commit references (#N).
  - Branch: `git fetch origin && git switch -c feat/ui-visualize-demand-planner
    origin/dev`.

Task 2 — Backend: inventory schemas:
  MODIFY app/features/analytics/schemas.py
    - Append InventoryStatusItem + InventoryStatusResponse (see Blueprint).
  VALIDATE: uv run ruff check app/features/analytics/schemas.py &&
    uv run mypy app/features/analytics/schemas.py

Task 3 — Backend: service method:
  MODIFY app/features/analytics/service.py
    - Add `InventorySnapshotDaily` to the data_platform import; add the two
      schema imports; add `compute_inventory_status` (see Blueprint).
  VALIDATE: uv run mypy app/features/analytics/service.py &&
    uv run pyright app/features/analytics/service.py

Task 4 — Backend: route:
  MODIFY app/features/analytics/routes.py
    - Add InventoryStatusResponse to the schema imports; add the
      GET /inventory-status handler (see Blueprint). No validate_date_range.
  VALIDATE: uv run ruff check app/features/analytics/ && uv run mypy app/ &&
    uv run pyright app/ && uv run python -c "from app.main import app"

Task 5 — Backend tests:
  MODIFY app/features/analytics/tests/conftest.py
    - Import InventorySnapshotDaily. Add `delete(InventorySnapshotDaily)` as the
      FIRST statement in the db_session cleanup (before SalesDaily/Store/
      Product/Calendar — FK order). Add a `sample_inventory` fixture inserting
      >=2 snapshots for one grain on different dates (proves latest-wins) + a
      second grain — depends on sample_store/sample_product/sample_calendar_120.
  MODIFY app/features/analytics/tests/test_routes_integration.py
    - Add TestAnalyticsInventoryStatusIntegration: latest-per-grain returned;
      store_id filter narrows; empty DB → items:[]/total_items:0/HTTP 200.
  MODIFY app/features/analytics/tests/test_schemas.py
    - Unit tests for InventoryStatusItem/Response (valid + rejects negative qty).
  GOTCHA: integration tests need `docker compose up -d` + `alembic upgrade head`.
  VALIDATE:
    docker compose up -d && uv run alembic upgrade head &&
    uv run pytest -v app/features/analytics/tests/ &&
    uv run pytest -v -m integration app/features/analytics/tests/

Task 6 — Frontend: types:
  MODIFY frontend/src/types/api.ts — add InventoryStatusItem,
    InventoryStatusResponse, DemandRow (see Blueprint).
  VALIDATE: cd frontend && pnpm tsc --noEmit

Task 7 — Frontend: hook:
  CREATE frontend/src/hooks/use-inventory.ts (see Blueprint).
  VALIDATE: cd frontend && pnpm tsc --noEmit

Task 8 — Frontend: pure utils + tests:
  CREATE frontend/src/lib/demand-utils.ts (see Blueprint).
  CREATE frontend/src/lib/demand-utils.test.ts — cover empty forecasts,
    horizon<30 (nextMonthPartial true), covered vs reorder inventory, the join
    with a missing inventory row (onHand null → requirement null).
  VALIDATE: cd frontend && pnpm test --run src/lib/demand-utils.test.ts

Task 9 — Frontend: routing:
  MODIFY frontend/src/lib/constants.ts — ROUTES.VISUALIZE +=
    DEMAND:'/visualize/demand'; add { label:'Demand Planner',
    href:ROUTES.VISUALIZE.DEMAND } to the Visualize NAV_ITEMS submenu.
  MODIFY frontend/src/App.tsx — lazy import DemandPlannerPage + a <Route> in
    <Suspense> (mirror the FORECAST route block).
  NOTE: pnpm tsc fails here until Task 10 — re-run after Task 10.

Task 10 — Frontend: Demand Planner page:
  CREATE frontend/src/pages/visualize/demand.tsx (see Blueprint).
    Build with frontend-design + shadcn-ui; use the plain <Table>, not DataTable.
  VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 11 — Frontend: TimeSeriesChart interval band:
  MODIFY frontend/src/components/charts/time-series-chart.tsx (see Blueprint).
  GOTCHA: keep backward-compatible — existing callers omit the new props. If the
    recharts range-Area API is uncertain, confirm via the contex7 MCP.
  VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm test --run

Task 12 — Frontend: widen JobPicker + upgrade Forecast page:
  MODIFY frontend/src/components/common/job-picker.tsx — widen `jobType` to
    Extract<JobType,'train'|'predict'|'backtest'>.
  MODIFY frontend/src/pages/visualize/forecast.tsx — in-page run (train-job
    picker + horizon → predict job), interval toggle, CSV export, cross-links
    (see Blueprint).
  VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 13 — Frontend: upgrade Backtest page:
  MODIFY frontend/src/pages/visualize/backtest.tsx — in-page backtest run, CSV
    export of fold_metrics, job cross-link (see Blueprint). Re-read
    _execute_backtest for the exact params keys before wiring the form.
  VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run

Task 14 — Docs:
  MODIFY README.md — mention the Demand Planner + interactive Visualize pages.
  MODIFY docs/_base/API_CONTRACTS.md — add the GET /analytics/inventory-status
    row to the analytics section.
  MODIFY docs/_base/REPO_MAP_INDEX.md — add a demand.tsx frontend-page row.

Task 15 — Dogfood the running UI (mandatory per ui-design.md):
  - docker compose up -d ; uv run alembic upgrade head ;
    uv run python scripts/seed_random.py --full-new --seed 42 --confirm.
  - `make demo` (or POST a few train + predict + backtest /jobs) so the pages
    have data.
  - uv run uvicorn app.main:app --port 8123 & ; cd frontend &&
    ./node_modules/.bin/vite --host 0.0.0.0.
  - Via webapp-testing / agent-browser exercise the 9 scenarios in Validation
    Level 4. Capture screenshots of the Demand Planner + both upgraded pages.

Task 16 — Commit + PR:
  Branch feat/ui-visualize-demand-planner. Commits, each (#issue), no AI trailer:
    1. feat(analytics): add inventory-status endpoint (#N)
    2. test(analytics): cover inventory-status endpoint (#N)
    3. feat(ui): add demand-planner data layer — types, hook, demand-utils (#N)
    4. feat(ui): add Visualize Demand Planner page (#N)
    5. feat(ui): add prediction-interval band to TimeSeriesChart (#N)
    6. feat(ui): make Forecast and Backtest pages interactive (#N)
    7. docs(docs): document Visualize demand planner + interactivity (#N)
  Open PR into dev; CI green; merge.
```

### Per-task pseudocode (highest-risk tasks)
```python
# Task 3 — the DISTINCT ON query (the one piece of non-trivial backend SQL)
stmt = (
    select(InventorySnapshotDaily)
    .order_by(                                    # DISTINCT ON cols MUST lead
        InventorySnapshotDaily.store_id,
        InventorySnapshotDaily.product_id,
        InventorySnapshotDaily.date.desc(),       # ...then date desc → latest
    )
    .distinct(
        InventorySnapshotDaily.store_id,
        InventorySnapshotDaily.product_id,
    )
)
# filters compose after; .scalars().all() → list[InventorySnapshotDaily]
```
```typescript
// Task 12 — the in-page forecast run (the genuinely new UI logic)
const createJob = useCreateJob()
async function runForecast(trainJob: Job, horizon: number) {
  const runId = trainJob.result?.run_id           // ARTIFACT key, not a registry id
  if (typeof runId !== 'string') return            // guard a malformed result
  const job = await createJob.mutateAsync({
    job_type: 'predict', params: { run_id: runId, horizon },
  })
  setSearchJobId(job.job_id)                        // useJob then polls to completion
}
```

### Integration Points
```yaml
DATABASE:  NONE — no migration. Read-only SELECT on inventory_snapshot_daily.
BACKEND:   analytics slice — +1 GET endpoint, +1 service method, +2 schemas.
           app/main.py UNCHANGED (analytics router already wired).
CONFIG:    NONE — no new env var.
FRONTEND ROUTING:
  - ROUTES.VISUALIZE.DEMAND (constants.ts) + a Visualize NAV_ITEMS entry.
  - One lazy <Route> in App.tsx.
CI:
  - No new workflow. ci.yml covers it. Because analytics .py files change, the
    ruff/mypy/pyright/pytest jobs are load-bearing — keep green.
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
# Watch: the .distinct()/.scalars() typing and the InventoryStatusItem
# model_validate(orm_row) call are the most likely strict-mode snags.
```

### Level 3: Unit + Integration Tests
```bash
uv run pytest -v -m "not integration"
docker compose up -d && uv run alembic upgrade head
uv run pytest -v -m integration app/features/analytics/tests/
cd frontend && pnpm test --run
# If integration tests fail on a stale local Postgres:
#   docker compose down -v && docker compose up -d && uv run alembic upgrade head
```

### Level 4: Manual end-to-end (dogfood — REQUIRED, ui-design.md)
```bash
docker compose up -d && uv run alembic upgrade head
uv run python scripts/seed_random.py --full-new --seed 42 --confirm
make demo                                       # populate jobs (train/predict/backtest)
uv run uvicorn app.main:app --port 8123 &
until curl -fs http://127.0.0.1:8123/health; do sleep 2; done
cd frontend && ./node_modules/.bin/vite --host 0.0.0.0     # http://localhost:5173

# Browser checks via webapp-testing / agent-browser:
#  1. curl "http://localhost:8123/analytics/inventory-status?store_id=1" → 200,
#     one item per product, each carrying the LATEST date.
#  2. Visualize → Demand Planner lists SKU rows with tomorrow/next-week/
#     next-month + inventory need; a horizon-14 forecast badges "partial" month.
#  3. Change the lead-time selector 7→14→30 → the inventory-need column updates.
#  4. Click a demand row → drill-in shows the demand curve + reorder breakdown
#     + working cross-links to the job and (if present) the run.
#  5. Export the demand table to CSV → file downloads with all rows.
#  6. Forecast page → "Run new forecast": pick a train job + horizon 30 → a new
#     predict job runs and the chart renders a 30-day forecast.
#  7. Toggle "Show prediction interval" → a shaded band renders (or the toggle
#     is disabled when the model has no bounds).
#  8. Backtest page → "Run new backtest": pick store/product/model/dates → a new
#     backtest job runs and metrics render; export fold metrics to CSV.
#  9. Forecast/Backtest job cross-links navigate to /explorer/jobs/:id.
```

---

## Final validation Checklist
- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run mypy app/ && uv run pyright app/` clean (both --strict)
- [ ] `uv run pytest -v -m "not integration"` green
- [ ] `uv run pytest -v -m integration app/features/analytics/tests/` green
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` clean
- [ ] `GET /analytics/inventory-status` returns latest-per-grain; honours
      store_id/product_id; empty table → 200 + items:[]
- [ ] Demand Planner table renders SKU rows with tomorrow/next-week/next-month +
      inventory requirement; lead-time selector recomputes the requirement
- [ ] Demand row drill-in shows the demand curve + reorder breakdown + cross-links
- [ ] Forecast page launches a predict job in-page; interval band + CSV work
- [ ] Backtest page launches a backtest job in-page; fold-metric CSV works
- [ ] No Alembic migration; no app/main.py change; no new slice; no .env var
- [ ] README + API_CONTRACTS.md + REPO_MAP_INDEX.md updated
- [ ] Branch `feat/ui-visualize-demand-planner`; every commit references the
      Task-1 issue; no AI co-author trailer
- [ ] Demand Planner + both upgraded pages dogfooded in a real browser
      (screenshots captured)

---

## Anti-Patterns to Avoid
- ❌ Don't add an Alembic migration — the endpoint is a read-only SELECT;
  `inventory_snapshot_daily` already exists.
- ❌ Don't edit `app/main.py` — the analytics router is already wired.
- ❌ Don't put `date.desc()` before `store_id`/`product_id` in the ORDER BY —
  Postgres requires the DISTINCT ON columns to lead.
- ❌ Don't use a registry `useRuns` RunPicker for the in-page forecast — train
  jobs do not create registry runs; submit the `train` job's `result.run_id`.
- ❌ Don't use the Explorer `DataTable` for the demand table — it is
  server-paginated (`manualSorting:true`); use the plain `<Table>` + a small
  client-side sort.
- ❌ Don't report "next month" as a full-month number when `horizon < 30` —
  return and badge `nextMonthPartial`.
- ❌ Don't forget the `delete(InventorySnapshotDaily)` cleanup line in the
  analytics `db_session` fixture, before the Store/Product/Calendar deletes.
- ❌ Don't break `TimeSeriesChart`'s existing callers — the interval band is
  opt-in (`showInterval` defaults false).
- ❌ Don't mock the database in integration tests; don't create test rows
  without the `TEST-` store/product prefix the cleanup keys on.
- ❌ Don't hand-roll the page without `frontend-design` / `shadcn-ui`, and don't
  claim "done" on a green `tsc` — dogfood in a real browser.
- ❌ Don't `git push --force` on dev/main; no AI co-author trailers; every
  commit references the open issue.

---

## Confidence Score

**8 / 10** for one-pass implementation success.

**Why solid:**
- The backend change is one read-only endpoint that mirrors `get_timeseries`
  almost verbatim — one service method, one route, two schemas, no migration,
  no `main.py` change, no new slice.
- The frontend reuses shipped infrastructure end-to-end: `use-timeseries.ts` is
  the exact hook template, `csv-export.ts` / `TimeSeriesChart` / `JobPicker` /
  `Table` / `DateRangePicker` / `useCreateJob` all already exist; the page
  skeleton mirrors `forecast.tsx` and the drill-in mirrors `run-detail.tsx`.
- The demand math lives in a pure, fully unit-tested `demand-utils.ts` module —
  the highest-logic part is the most testable.
- Every cited file carries verified line numbers; the real traps (DISTINCT ON
  column order, train-job vs registry-run id for predict, the missing inventory
  cleanup line, partial-month horizons, `ComposedChart` for the band) are each
  called out with the exact fix.

**Why not higher:**
- The in-page **backtest** form is the largest sub-task — store/product/model/
  date controls plus the `_execute_backtest` params contract; a key mismatch
  there is the most likely second-pass fix (the PRP prescribes re-reading the
  contract first).
- The `TimeSeriesChart` `LineChart`→`ComposedChart` migration plus a recharts
  range-`Area` band is genuine shared-component surgery — backward-compatible by
  design, but it needs the real-browser dogfood (Task 15) and possibly a
  contex7 doc check to land cleanly.
- The Demand Planner is real UI composition — table + sort + drill-in + states;
  a green `tsc` will not catch a cramped layout or a broken join.

All identified risks are caught by the layered validation loop (strict
type-check → integration tests → browser dogfood) and the fixes are local.
Executing the 16 tasks in order and running each `VALIDATE` before moving on is
what carries it.
