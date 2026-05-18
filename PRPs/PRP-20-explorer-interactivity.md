name: "PRP-20 — Explorer Interactivity Extension (Sales / Stores / Products)"
description: |
  Turn the three primary Explorer pages of the ForecastLabAI dashboard —
  **Sales**, **Stores**, **Products** — from flat, read-only list/drilldown
  views into an interactive analysis surface:

  1. **Click-through detail views** — two new deep-linkable routes
     (`/explorer/stores/:storeId`, `/explorer/products/:productId`) reached by
     clicking a table row. Each shows the entity's profile, date-scoped KPIs, a
     revenue-over-time chart, and a top-contributors drilldown.
  2. **Richer tables** — server-side column sorting, CSV export, and
     column-visibility toggles on the Stores / Products / Runs DataTables.
  3. **Charts on the Sales page** — a revenue-by-dimension bar chart and a
     revenue-over-time line chart alongside the existing ranked drilldown list.
  4. **Cross-filtering** — filter / date / dimension state persisted in the URL
     query string, and a "View in Sales" link from detail pages that carries
     `store_id` / `product_id` into the Sales analytics page.

  Backend-touching but additive: one new read-only endpoint
  (`GET /analytics/timeseries`) supplies the aggregated series the charts need,
  and the two `/dimensions` list endpoints gain additive `sort_by` / `sort_order`
  query params. **No Alembic migration** (every query is a read aggregate over
  existing tables), **no new slice**, **no new env var**, **no `app/main.py`
  change** (the `analytics` router is already wired).

> **PRP numbering:** `PRP-16` is reserved (Phase-2 LightGBM, per PRP-15).
> `PRP-17` (Showcase), `PRP-18` (AI Model console), `PRP-19` (Knowledge + Agent
> Guide) are used. This is `PRP-20`. Source plan:
> `.agents/plans/explorer-interactivity-extension.md`.

## Purpose
Close the "the Explorer pages are terminal" gap. Today Stores and Products are
static paginated tables with no row interaction, no sorting, no export; Sales is
a ranked text list with no visual trend; filter state is lost on every refresh;
and there is no way to scope analytics to a single entity from the UI — an
analyst must drop to Swagger (`/docs`) or `curl`. This PRP makes the Explorer a
place you can actually *investigate* in.

## Core Principles
1. **Context is King** — every endpoint shape, hook name, schema field, service
   method, and pattern below is linked to a real source file + line.
2. **Reuse existing patterns** — the new endpoint mirrors `compute_kpis`; the
   new pages mirror `sales.tsx` / `dashboard.tsx`; charts reuse `TimeSeriesChart`
   and the `backtest-folds-chart.tsx` Recharts pattern; detail routes register
   exactly like the existing Explorer routes in `App.tsx`.
3. **Additive only** — no new slice, no migration, no new `.env` var, no
   `app/main.py` edit. The backend deltas are one new route on the existing
   `analytics` router + two optional query params on `/dimensions`.
4. **Strict gates honored** — because `.py` files in the `analytics` and
   `dimensions` slices change, the repo-wide `ruff` / `mypy --strict` /
   `pyright --strict` / `pytest` CI jobs genuinely apply and must stay green —
   each backend change ships with slice tests.
5. **UI through skills** — pages built via `frontend-design` + `shadcn-ui` and
   dogfooded via `webapp-testing` / `agent-browser` per `.claude/rules/ui-design.md`.
   A green `tsc` is NOT proof the UI works.

---

## Goal

**Backend (additive, no migration):**
- `GET /analytics/timeseries` — daily / weekly / monthly / quarterly aggregated
  sales (`total_revenue`, `total_units`, `total_transactions` + derived
  averages), filterable by `store_id` / `product_id` / `category`, ordered by
  period ascending.
- `GET /dimensions/stores` and `GET /dimensions/products` gain optional
  `sort_by` + `sort_order` params (allow-listed columns; unknown → default
  order, never an error).

**Frontend:**
- Two new routes — `/explorer/stores/:storeId` and `/explorer/products/:productId`
  — reached by clicking a Stores/Products row. Each: entity profile card, a
  `DateRangePicker`, four `KPICard`s, a revenue-over-time `TimeSeriesChart`, a
  top-contributors drilldown, and a "View in Sales" link. Product detail also
  shows the existing `/dimensions/products/{id}/lifecycle-curve`.
- Stores / Products / Runs tables gain CSV export + column-visibility toggles;
  Stores / Products additionally gain server-side column sorting and row-click
  navigation.
- The Sales page gains a revenue-by-dimension bar chart + a revenue-over-time
  line chart, and reads `store_id` / `product_id` from the URL for cross-filtering.
- Filter / date / dimension state on Sales / Stores / Products persists in the
  URL query string (`useSearchParams`).

## Why
- **Portfolio identity.** `.claude/rules/product-vision.md` principle 1 —
  "portfolio-grade, end-to-end … every phase ships working code". The analytics
  layer (`/analytics/kpis`, `/analytics/drilldowns`) and the dimension catalog
  are fully built but the dashboard exposes them as flat tables — a reviewer
  cannot *explore* a single store or product without leaving the UI.
- **Analyst workflow.** "Why is revenue moving" is the core question; today it
  is unanswerable in-product. Detail views + charts + cross-filtering make the
  Explorer a genuine investigation surface.
- **High value per line.** Almost everything is composition of shipped endpoints
  and shipped components; the only new server code is one read-only aggregate
  query and two query params.

## What
Backend-touching but additive. One new route + service method + two schemas on
the `analytics` slice; two query params + allow-listed ordering on the
`dimensions` slice; integration tests for both (the `analytics` slice has **no
test files today** — this PRP also closes that gap). Frontend: 2 new pages, 2
new routes, ~6 new hooks/components/utils, 4 existing pages upgraded, new TS
types. No migration, no new env var, no new slice.

### Success Criteria
- [ ] `GET /analytics/timeseries?start_date=…&end_date=…&granularity=day|week|month|quarter`
      returns period-ascending aggregated points; honors `store_id` /
      `product_id` / `category` filters; reuses `validate_date_range` so an
      inverted range and an over-730-day range both 400 with RFC 7807.
- [ ] `GET /dimensions/stores` and `/dimensions/products` accept `sort_by` +
      `sort_order`; omitting them preserves the current default order
      (`Store.code` / `Product.sku`); an unknown `sort_by` falls back to the
      default order without erroring.
- [ ] Clicking a Stores/Products row navigates to a working
      `/explorer/stores/:id` / `/explorer/products/:id` page with profile,
      date-scoped KPIs, a revenue-over-time chart, and a top-contributors list.
- [ ] Stores & Products tables support server-side column sorting, CSV export,
      and column-visibility toggles; Runs supports export + column visibility.
- [ ] The Sales page shows a revenue-by-dimension bar chart + a revenue-over-time
      line chart in addition to the ranked list, and applies `?store_id` /
      `?product_id` from the URL.
- [ ] Filter / date / dimension state round-trips through the URL (paste a
      filtered URL into a fresh tab → identical view); "View in Sales" carries
      the entity filter.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ &&
      uv run pyright app/` clean; `uv run pytest -v -m "not integration"` and
      `-m integration` for the `analytics` + `dimensions` slices green.
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` clean
      (incl. the new `csv-export.test.ts`).
- [ ] No Alembic migration; no new slice; no `app/main.py` change; no `.env` var.
- [ ] Both detail pages + the upgraded Sales page dogfooded in a real browser
      (screenshots captured).

---

## All Needed Context

### Documentation & References
```yaml
# ---- External docs ----
- url: https://tanstack.com/query/latest/docs/framework/react/guides/queries
  why: useQuery shape for the new GET hooks (timeseries, lifecycle-curve)
  critical: GET data → useQuery({ queryKey, queryFn, enabled }). The repo's
    hooks (use-drilldowns.ts, use-kpis.ts) follow this exactly — copy that shape.

- url: https://tanstack.com/table/v8/docs/guide/sorting#manual-server-side-sorting
  why: DataTable already sets `manualSorting: true` — this section shows how
    SortingState (`[{id, desc}]`) maps to server-side sort params.
  critical: With manualSorting, sorting MUST round-trip through the backend
    `sort_by`/`sort_order`; a client-only sort would only reorder the visible page.

- url: https://tanstack.com/table/v8/docs/guide/column-visibility
  why: column-visibility dropdown — `columnVisibility` state,
    `onColumnVisibilityChange`, `column.getCanHide()`, `column.toggleVisibility()`.

- url: https://reactrouter.com/6.30.1/hooks/use-params
  why: `/explorer/stores/:storeId` dynamic-segment extraction.
  critical: `useParams()` returns `Record<string,string|undefined>` — the id is
    a STRING and may be undefined; parse with Number() and guard Number.isNaN.

- url: https://reactrouter.com/6.30.1/hooks/use-search-params
  why: URL filter persistence + cross-filtering (Sales reads ?store_id).
  critical: `useSearchParams()` → `[params, setParams]`; `params.get('x')` is
    `string | null`. Treat it like controlled state initialised from the URL.

- url: https://recharts.org/en-US/api/BarChart
  why: the new RevenueBarChart. Prefer mirroring backtest-folds-chart.tsx
    (already in the repo) over raw Recharts.

- url: https://www.postgresql.org/docs/16/functions-datetime.html#FUNCTIONS-DATETIME-TRUNC
  why: Postgres `date_trunc(field, source)` — `field` ∈ {day,week,month,quarter};
    all four TimeGranularity values are valid field strings.

- url: https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.cast
  why: `cast(expr, Date)` to coerce the date_trunc timestamp back to a DATE so
    TimeSeriesPoint.period (a `date`) validates.

# ---- Backend: the pattern to mirror ----
- file: app/features/analytics/routes.py
  why: THE route pattern. `validate_date_range` (lines 32-57) — reuse verbatim,
    it also enforces the 730-day cap via settings.analytics_max_date_range_days.
    `get_kpis` (lines 65-147) is the route shape to copy for `get_timeseries`.
  critical: The `analytics` router is already included in app/main.py — the new
    route attaches to the existing `router` object; do NOT touch app/main.py.

- file: app/features/analytics/service.py
  why: `compute_kpis` (lines 39-116) is the closest aggregation: coalesced sums,
    inclusive date `where`, optional store/product filters, the `category`
    `.join(Product, …)`. `compute_drilldown` (lines 199-209) shows group_by/order_by.
  critical: |
    NAME COLLISION — service.py already does `from typing import Any, cast`
    (line 8) and uses `cast(ColumnElement[Any], Store.code)`. SQLAlchemy ALSO
    exports `cast`. You MUST import the SQLAlchemy one aliased:
    `from sqlalchemy import Date` and `from sqlalchemy import cast as sa_cast`.
    Then `sa_cast(func.date_trunc(granularity.value, SalesDaily.date), Date)`.
    Importing plain `cast` from sqlalchemy would shadow typing.cast and break
    the existing drilldown code + the strict type-check.

- file: app/features/analytics/schemas.py
  why: `KPIMetrics` (lines 48-80) — REUSE for per-period metrics. `TimeGranularity`
    enum (lines 18-28: day/week/month/quarter, str-Enum) ALREADY EXISTS — REUSE
    it for the `granularity` param. `KPIResponse` (lines 83-112) is the
    response-envelope pattern; `DrilldownItem` (lines 120-152) shows `from_attributes`.

- file: app/features/analytics/tests/conftest.py
  why: currently holds ONLY unit fixtures (Pydantic objects, no DB). The slice
    has NO test_*.py at all — see "Testing gap" gotcha.

- file: app/features/dimensions/routes.py
  why: stores-list handler (lines 33-92) + products-list handler (lines 144-203)
    — add `sort_by`/`sort_order` `Query` params here, mirroring the existing
    `region`/`store_type`/`category` params.

- file: app/features/dimensions/service.py
  why: `list_stores` (lines 35-100) + `list_products` (lines 148-213) — current
    default order is `stmt.order_by(Store.code)` (line 81) and
    `stmt.order_by(Product.sku)` (line 194). Add allow-listed sorting here.
    `get_product_lifecycle_curve` (lines 261-343) backs the product detail page.

- file: app/features/dimensions/schemas.py
  why: `StoreResponse`/`ProductResponse` field names (the sort allow-list keys);
    `LifecycleCurveResponse` (lines 208-234): product_id, sku, launch_date,
    discontinue_date, start_date, end_date, points:[{date,stage,multiplier}],
    total — mirror field-for-field into types/api.ts.

- file: app/features/backtesting/tests/conftest.py
  why: THE integration-test DB fixture set to COPY. `db_session`, `client`
    (with `app.dependency_overrides[get_db]`), `sample_store`, `sample_product`,
    `sample_calendar_120`, `sample_sales_120` (2024-01-01..2024-04-29, qty 1..120).
  critical: test rows use `TEST-<uuid8>` code/sku prefixes; the conftest cleanup
    deletes `SalesDaily` + `Product/Store LIKE 'TEST-%'` + the test calendar range.

- file: app/features/backtesting/tests/test_routes_integration.py
  why: the `@pytest.mark.integration` + `@pytest.mark.asyncio` class style,
    `AsyncClient` POST/GET, `response.json()` assertions (lines 1-67).

- file: app/core/config.py
  why: `analytics_max_date_range_days: int = 730` (line 115) — `validate_date_range`
    already enforces it; reusing that helper means the new endpoint inherits the cap.

# ---- Frontend: the pattern to mirror ----
- file: frontend/src/pages/explorer/sales.tsx
  why: current Sales page (DateRangePicker + Tabs + useDrilldowns + error/loading
    scaffold). Charts + URL state are added here.

- file: frontend/src/pages/explorer/stores.tsx  &  products.tsx
  why: current table pages — pagination + DataTableToolbar + DataTable. Row-click,
    sorting, export, column visibility, URL state are added here.

- file: frontend/src/pages/explorer/runs.tsx
  why: a third DataTable page — gets export + column visibility (no detail page,
    no server sort in scope).

- file: frontend/src/pages/dashboard.tsx
  why: reference for the KPICard grid layout used on the new detail pages.

- file: frontend/src/components/data-table/data-table.tsx
  why: `manualSorting: true` is already set; `sorting`/`onSortingChange` props
    exist but are unused by pages. Add an optional `onRowClick` + an optional
    `enableColumnVisibility` (internal columnVisibility state). KEEP every change
    additive so runs.tsx and other callers still compile.

- file: frontend/src/components/data-table/data-table-pagination.tsx
  why: a page-size selector ALREADY EXISTS here (`pageSizeOptions=[10,25,50,100]`).
    Do NOT re-implement page size.

- file: frontend/src/components/data-table/data-table-toolbar.tsx
  why: search + select filters + reset. Export/view-options buttons sit alongside it.

- file: frontend/src/components/charts/time-series-chart.tsx
  why: REUSE for revenue-over-time. Props: `data:{date,actual?,predicted?}[]`,
    `actualKey`, `showPredicted`. Feed revenue as `actual`, pass `showPredicted={false}`.
  critical: the Line's legend label is hardcoded "Actual" — acceptable here
    (the series IS actual historical revenue). The `--chart-N` CSS vars are full
    oklch() — reference them directly, never wrap in hsl() (see file comment l.42-43).

- file: frontend/src/components/charts/backtest-folds-chart.tsx
  why: the Recharts `BarChart` + `ChartContainer` pattern to mirror for RevenueBarChart.

- file: frontend/src/components/charts/kpi-card.tsx
  why: REUSE on the detail pages. Props: title, value, description?, icon?, isLoading?.

- file: frontend/src/components/ui/dropdown-menu.tsx
  why: exports `DropdownMenu`, `DropdownMenuTrigger`, `DropdownMenuContent`,
    `DropdownMenuCheckboxItem`, `DropdownMenuLabel`, `DropdownMenuSeparator` —
    everything DataTableViewOptions needs.

- file: frontend/src/lib/api.ts
  why: `api<T>(endpoint,{params})` client (drops undefined/null/'' params),
    `formatCurrency`/`formatNumber`/`formatPercent`, `ApiError`, `getErrorMessage`.

- file: frontend/src/lib/date-utils.ts
  why: `dateRangeToStrings` / `stringsToDateRange` for DateRange ↔ API string.

- file: frontend/src/lib/constants.ts
  why: `ROUTES` (EXPLORER block lines 5-11) + `NAV_ITEMS`. Add 2 detail routes to
    ROUTES.EXPLORER. Do NOT add them to NAV_ITEMS (reached by click-through).

- file: frontend/src/App.tsx
  why: lazy-route registration (lines 13-19 imports, 52-91 Explorer routes).
    Add 2 lazy imports + 2 `<Route>`s with dynamic `:storeId`/`:productId`.

- file: frontend/src/hooks/use-drilldowns.ts
  why: THE hook template — useQuery + queryKey array + keepPreviousData + enabled.

- file: frontend/src/hooks/use-stores.ts  &  use-products.ts
  why: paginated list hooks + the existing `useStore(id)` / `useProduct(id)`
    detail hooks (reused by the detail pages). Extend the list hooks with
    `sortBy`/`sortOrder`.

- file: frontend/src/hooks/use-kpis.ts
  why: `useKPIs({startDate,endDate,storeId,productId,category})` — reused on the
    detail pages as-is.

- file: frontend/src/hooks/index.ts
  why: barrel re-export — add `use-timeseries` and `use-lifecycle-curve` lines.

- file: frontend/src/components/data-table/index.ts  &  components/charts/index.ts
  why: barrels — add the new view-options/column-header + revenue-bar-chart exports.

- file: frontend/src/types/api.ts
  why: `Store`, `Product`, `KPIMetrics`, `KPIResponse`, `DrilldownResponse`,
    `DrilldownDimension`, `PaginatedResponse<T>` (lines 1-76). Add the new
    time-series + lifecycle types here.

- file: frontend/src/lib/knowledge-utils.ts  &  knowledge-utils.test.ts
  why: precedent for a pure `lib/*.ts` helper + its colocated vitest — the model
    for `csv-export.ts` + `csv-export.test.ts`.

- file: frontend/src/hooks/use-demo-pipeline.test.ts
  why: vitest structure (describe/it/expect) for the csv-export test.

- file: PRPs/PRP-19-knowledge-and-agent-guide-pages.md
  why: the most recent "add pages + small additive backend change" PRP — the
    frontend registration pattern (constants + App.tsx + lazy route) is identical.

# ---- Rules ----
- file: .claude/rules/ui-design.md
  why: UI built/dogfooded via frontend-design + shadcn-ui + webapp-testing.
- file: .claude/rules/security-patterns.md
  why: "Allow-lists over deny-lists" — the sort_by param MUST resolve through an
    allow-list dict to a real mapped column, never interpolate the raw string.
- file: .claude/rules/test-requirements.md
  why: new endpoint → route test (2xx + 1 error path); new param → test;
    new pure util → vitest. Integration tests use real Postgres, never mocked.
- file: .claude/rules/commit-format.md  &  branch-naming.md
  why: `type(scope): description (#issue)`; scopes `analytics`/`dimensions`/`ui`/
    `api`/`docs`; branch `feat/explorer-interactivity` off `dev`; open the issue FIRST.
```

### Current Codebase tree (relevant)
```bash
app/features/
├── analytics/
│   ├── routes.py            # MOD — +GET /analytics/timeseries
│   ├── service.py           # MOD — +compute_timeseries
│   ├── schemas.py           # MOD — +TimeSeriesPoint/TimeSeriesResponse
│   └── tests/
│       ├── conftest.py      # MOD — +DB fixtures (copied from backtesting)
│       ├── test_schemas.py            # NEW
│       └── test_routes_integration.py # NEW
└── dimensions/
    ├── routes.py            # MOD — +sort_by/sort_order on stores+products lists
    ├── service.py           # MOD — allow-listed ordering in list_stores/list_products
    └── tests/
        ├── conftest.py      # MOD — +DB fixtures + multi-row fixtures
        └── test_sort.py     # NEW

frontend/src/
├── App.tsx                  # MOD — +2 lazy detail routes
├── lib/
│   ├── constants.ts         # MOD — +ROUTES.EXPLORER.STORE_DETAIL/PRODUCT_DETAIL
│   ├── csv-export.ts        # NEW — pure CSV util + downloadCsv
│   └── csv-export.test.ts   # NEW — vitest
├── types/api.ts             # MOD — +TimeGranularity/TimeSeries*/LifecycleCurveResponse
├── hooks/
│   ├── index.ts             # MOD — +2 barrel lines
│   ├── use-stores.ts        # MOD — +sortBy/sortOrder
│   ├── use-products.ts      # MOD — +sortBy/sortOrder
│   ├── use-timeseries.ts    # NEW
│   └── use-lifecycle-curve.ts # NEW
├── components/
│   ├── data-table/
│   │   ├── data-table.tsx              # MOD — +onRowClick, +enableColumnVisibility
│   │   ├── data-table-view-options.tsx # NEW — column-visibility dropdown
│   │   ├── data-table-column-header.tsx# NEW — sortable header button
│   │   └── index.ts                    # MOD — +2 barrel lines
│   └── charts/
│       ├── revenue-bar-chart.tsx       # NEW
│       └── index.ts                    # MOD — +1 barrel line
└── pages/explorer/
    ├── sales.tsx            # MOD — +charts, +URL state, +cross-filter
    ├── stores.tsx           # MOD — +row-click, +sorting, +export, +view-options, +URL state
    ├── products.tsx         # MOD — same as stores
    ├── runs.tsx             # MOD — +export, +view-options
    ├── store-detail.tsx     # NEW
    └── product-detail.tsx   # NEW
```

### Desired Codebase tree (files added / changed)
```bash
NEW  app/features/analytics/tests/test_schemas.py            # unit — new schemas
NEW  app/features/analytics/tests/test_routes_integration.py # integration — /timeseries (+ kpis/drilldowns smoke)
NEW  app/features/dimensions/tests/test_sort.py              # integration — sort params
NEW  frontend/src/hooks/use-timeseries.ts                    # GET /analytics/timeseries
NEW  frontend/src/hooks/use-lifecycle-curve.ts               # GET /dimensions/products/{id}/lifecycle-curve
NEW  frontend/src/components/charts/revenue-bar-chart.tsx    # revenue-by-dimension bar chart
NEW  frontend/src/components/data-table/data-table-view-options.tsx   # column-visibility dropdown
NEW  frontend/src/components/data-table/data-table-column-header.tsx  # sortable header button
NEW  frontend/src/lib/csv-export.ts                          # pure toCsv + downloadCsv
NEW  frontend/src/lib/csv-export.test.ts                     # vitest — toCsv coverage
NEW  frontend/src/pages/explorer/store-detail.tsx            # store detail route page
NEW  frontend/src/pages/explorer/product-detail.tsx          # product detail route page
MOD  app/features/analytics/{routes,service,schemas}.py      # +timeseries endpoint
MOD  app/features/analytics/tests/conftest.py                # +DB fixtures
MOD  app/features/dimensions/{routes,service}.py             # +sort_by/sort_order
MOD  app/features/dimensions/tests/conftest.py               # +DB + multi-row fixtures
MOD  frontend/src/types/api.ts                               # +TimeGranularity/TimeSeries*/LifecycleCurveResponse
MOD  frontend/src/hooks/{use-stores,use-products,index}.ts   # +sort params, +barrel
MOD  frontend/src/components/data-table/{data-table,index}.ts(x)  # +onRowClick/+visibility
MOD  frontend/src/components/charts/index.ts                 # +revenue-bar-chart export
MOD  frontend/src/lib/constants.ts                           # +2 detail routes
MOD  frontend/src/App.tsx                                    # +2 lazy routes
MOD  frontend/src/pages/explorer/{sales,stores,products,runs}.tsx  # interactive upgrades
MOD  README.md                                               # feature list
MOD  docs/_base/API_CONTRACTS.md                             # +/analytics/timeseries row, +sort params
MOD  docs/_base/REPO_MAP_INDEX.md                            # +store-detail/product-detail rows
KEEP app/main.py                                             # UNCHANGED — analytics router already wired
KEEP alembic/**                                              # UNCHANGED — NO migration (read-only queries)
```

### Known Gotchas & Library Quirks
```python
# CRITICAL: `cast` NAME COLLISION in analytics/service.py. The file already does
#   `from typing import Any, cast` and uses typing.cast for drilldown columns.
#   SQLAlchemy also exports `cast`. Import the SQLAlchemy one ALIASED:
#       from sqlalchemy import Date
#       from sqlalchemy import cast as sa_cast
#   Use `sa_cast(func.date_trunc(granularity.value, SalesDaily.date), Date)`.
#   A plain `from sqlalchemy import cast` would shadow typing.cast and break the
#   existing code AND the strict type-check.

# CRITICAL: `func.date_trunc` is untyped. Under mypy --strict / pyright --strict
#   annotate the bucket column explicitly — `bucket: ColumnElement[Any]` (mirror
#   `dimension_col: ColumnElement[Any]` at service.py:143). For granularity=DAY
#   use the raw `SalesDaily.date` column (no date_trunc needed); only week/month/
#   quarter need date_trunc + sa_cast.

# CRITICAL: NO Alembic migration. Every new query is a read aggregate over
#   existing tables (sales_daily, store, product). Adding a migration would be
#   wrong. `.claude/rules` only require a migration when the SCHEMA changes.

# CRITICAL: TESTING GAP — the `analytics` slice has NO test files (only
#   tests/conftest.py with unit fixtures). The `dimensions` tests/conftest.py
#   has only dict fixtures. Neither has a DB session/client fixture. Task 4 must
#   COPY db_session/client/sample_store/sample_product/sample_calendar_120/
#   sample_sales_120 from app/features/backtesting/tests/conftest.py. Budget time.

# CRITICAL: sort_by is user input. Resolve it through an explicit allow-list
#   dict {str: mapped_column} → a real SQLAlchemy column. NEVER interpolate the
#   raw string into the query (security-patterns.md). Unknown sort_by → fall
#   back to the current default order; do NOT 400 (keeps it backward-compatible
#   and avoids 500s from stale frontend state).

# CRITICAL: DataTable has `manualSorting: true`. Server-side sort is mandatory —
#   thread SortingState → sort_by/sort_order → useStores/useProducts. A
#   client-only sort would silently reorder only the current page.

# GOTCHA: money fields serialize to JSON STRINGS (Decimal). `KPIMetrics.total_revenue`
#   is `string` in types/api.ts. ALWAYS `Number(x)` before feeding Recharts.

# GOTCHA: data-table-pagination.tsx ALREADY has a page-size selector
#   (pageSizeOptions=[10,25,50,100]). Do NOT add another one.

# GOTCHA: every change to DataTableProps must be ADDITIVE & optional — runs.tsx
#   and any other DataTable caller must compile unchanged.

# GOTCHA: useParams() returns string|undefined. Parse the :storeId/:productId
#   with Number() and guard Number.isNaN → render a not-found ErrorDisplay state.

# GOTCHA: the lifecycle-curve endpoint is NEVER empty — for a product with no
#   launch_date it returns a flat curve at multiplier 1.0 (service.py:300-301),
#   `points` always has ≥1 entry. Handle the "flat" curve gracefully; there is
#   no "empty points" case to special-case.

# GOTCHA: TimeSeriesChart hardcodes the Line name "Actual" and `--chart-N` are
#   full oklch() vars — reference directly, never hsl() (file comment l.42-43).

# GOTCHA: new .tsx/.ts files are LF. Editing existing .py files preserves their
#   CRLF (repo .py files are CRLF, no .gitattributes — see project memory).
#   For the 3 NEW .py test files, after writing run `git diff --stat` and
#   confirm no whole-file EOL churn slipped into the diff.

# GOTCHA: the `analytics` router is already in app/main.py. Do NOT edit main.py —
#   the new route attaches to the existing `router` object in analytics/routes.py.

# GOTCHA: every commit references the open tracking issue (commit-format.md);
#   NO AI co-author trailer, ever. Branch off `dev`.
```

### Resolved Decisions (user-confirmed 2026-05-18)
```yaml
interactivity-scope:
  decision: all four directions ship — click-through detail views, richer
    tables, charts on Sales, and cross-filtering.
  status: confirmed (AskUserQuestion, multi-select all four).
timeseries-data-source:
  decision: add a backend endpoint `GET /analytics/timeseries` for the
    per-store/per-product daily series rather than reusing
    /analytics/drilldowns?dimension=date.
  why: drilldowns caps at max_items=100, orders by revenue (not date), and has
    no week/month bucketing. A dedicated endpoint is cleaner, cheap (read-only,
    indexed on ix_sales_daily_date_store / ix_sales_daily_date_product), and
    reuses KPIMetrics + TimeGranularity.
  status: confirmed (user chose "Add a backend endpoint (Recommended)").
detail-ux:
  decision: entity detail views are dedicated React Router route pages
    (/explorer/stores/:storeId, /explorer/products/:productId), NOT a Sheet or
    Dialog — they are deep-linkable and enable the cross-filtering "View in
    Sales" link.
  status: confirmed (user chose "Dedicated route page").
```

---

## Implementation Blueprint

### Backend data models (`app/features/analytics/schemas.py`, append after `DrilldownResponse`)
```python
# REUSE the existing KPIMetrics + TimeGranularity from this file — do NOT redefine.
# These are RESPONSE models — do NOT add ConfigDict(strict=True) (the strict-mode
# policy / AST linter only governs request bodies). Every Field needs a description.

class TimeSeriesPoint(BaseModel):
    """One aggregated period of the sales time series."""
    model_config = ConfigDict(from_attributes=True)
    period: date = Field(..., description="Bucket start date (day, or first day of week/month/quarter).")
    metrics: KPIMetrics = Field(..., description="Aggregated KPI metrics for this period.")

class TimeSeriesResponse(BaseModel):
    """Period-bucketed sales time series for charting."""
    granularity: TimeGranularity = Field(..., description="Bucket size used for aggregation.")
    points: list[TimeSeriesPoint] = Field(..., description="Points in ascending period order.")
    total_points: int = Field(..., ge=0, description="Number of points returned.")
    start_date: date = Field(..., description="Start of the analysis period (inclusive).")
    end_date: date = Field(..., description="End of the analysis period (inclusive).")
    store_id: int | None = Field(None, description="Store filter applied (if any).")
    product_id: int | None = Field(None, description="Product filter applied (if any).")
    category: str | None = Field(None, description="Category filter applied (if any).")
```

### Backend service (`app/features/analytics/service.py`, new method on `AnalyticsService`)
```python
# IMPORTS to add: `from sqlalchemy import Date` ; `from sqlalchemy import cast as sa_cast`
# and TimeGranularity/TimeSeriesPoint/TimeSeriesResponse to the schemas import block.

async def compute_timeseries(self, db, start_date, end_date,
                              granularity=TimeGranularity.DAY,
                              store_id=None, product_id=None, category=None) -> TimeSeriesResponse:
    # PATTERN: bucket expression. DAY → raw date column; coarser → date_trunc.
    bucket: ColumnElement[Any]
    if granularity == TimeGranularity.DAY:
        bucket = SalesDaily.date
    else:
        bucket = sa_cast(func.date_trunc(granularity.value, SalesDaily.date), Date)

    # PATTERN: identical aggregation/filters to compute_kpis (service.py:62-76)
    stmt = select(
        bucket.label("period"),
        func.coalesce(func.sum(SalesDaily.total_amount), 0).label("total_revenue"),
        func.coalesce(func.sum(SalesDaily.quantity), 0).label("total_units"),
        func.count().label("total_transactions"),
    ).where((SalesDaily.date >= start_date) & (SalesDaily.date <= end_date))
    if store_id is not None:   stmt = stmt.where(SalesDaily.store_id == store_id)
    if product_id is not None: stmt = stmt.where(SalesDaily.product_id == product_id)
    if category is not None:
        stmt = stmt.join(Product, SalesDaily.product_id == Product.id).where(Product.category == category)
    stmt = stmt.group_by(bucket).order_by(bucket)

    rows = (await db.execute(stmt)).all()
    points: list[TimeSeriesPoint] = []
    for row in rows:
        revenue = Decimal(str(row.total_revenue)); units = int(row.total_units)
        txns = int(row.total_transactions)
        points.append(TimeSeriesPoint(period=row.period, metrics=KPIMetrics(
            total_revenue=revenue, total_units=units, total_transactions=txns,
            avg_unit_price=(revenue / units if units > 0 else None),
            avg_basket_value=(revenue / txns if txns > 0 else None))))
    logger.info("analytics.timeseries_computed", granularity=granularity.value,
                start_date=str(start_date), end_date=str(end_date),
                store_id=store_id, product_id=product_id, points=len(points))
    return TimeSeriesResponse(granularity=granularity, points=points,
                              total_points=len(points), start_date=start_date,
                              end_date=end_date, store_id=store_id,
                              product_id=product_id, category=category)
```

### Backend route (`app/features/analytics/routes.py`, new `@router.get("/timeseries")`)
```python
# Mirror get_kpis (lines 65-147): rich description=, Query(...) params, reuse
# validate_date_range(start_date, end_date), then AnalyticsService().compute_timeseries(...).
# granularity: TimeGranularity = Query(TimeGranularity.DAY, description="Bucket size: day|week|month|quarter.")
```

### Backend sort params (`app/features/dimensions/`)
```python
# routes.py — add to BOTH list handlers:
#   sort_by:  str | None = Query(None, description="Sort column. Stores: code|name|region|city|store_type.")
#   sort_order: str = Query("asc", pattern="^(asc|desc)$", description="Sort direction.")
# service.py — list_stores / list_products:
_STORE_SORT = {"code": Store.code, "name": Store.name, "region": Store.region,
               "city": Store.city, "store_type": Store.store_type}
column = _STORE_SORT.get(sort_by) if sort_by else None
if column is not None:
    stmt = stmt.order_by(column.desc() if sort_order == "desc" else column.asc())
else:
    stmt = stmt.order_by(Store.code)   # UNCHANGED default — keeps existing tests green
# Products allow-list: sku|name|category|brand|base_price ; default order Product.sku.
```

### Frontend types (`frontend/src/types/api.ts`, append near the `// === Analytics ===` block)
```typescript
export type TimeGranularity = 'day' | 'week' | 'month' | 'quarter'
export interface TimeSeriesPoint { period: string; metrics: KPIMetrics }
export interface TimeSeriesResponse {
  granularity: TimeGranularity
  points: TimeSeriesPoint[]
  total_points: number
  start_date: string; end_date: string
  store_id: number | null; product_id: number | null; category: string | null
}
// Mirror app/features/dimensions/schemas.py LifecycleCurveResponse (lines 208-234):
export interface LifecyclePoint { date: string; stage: string; multiplier: number }
export interface LifecycleCurveResponse {
  product_id: number; sku: string
  launch_date: string | null; discontinue_date: string | null
  start_date: string; end_date: string
  points: LifecyclePoint[]; total: number
}
```

### Frontend hooks (`use-timeseries.ts`, `use-lifecycle-curve.ts` — mirror use-drilldowns.ts)
```typescript
// use-timeseries.ts
export function useTimeseries({ startDate, endDate, granularity = 'day',
  storeId, productId, category, enabled = true }: UseTimeseriesParams) {
  return useQuery({
    queryKey: ['timeseries', { startDate, endDate, granularity, storeId, productId, category }],
    queryFn: () => api<TimeSeriesResponse>('/analytics/timeseries', { params: {
      start_date: startDate, end_date: endDate, granularity,
      store_id: storeId, product_id: productId, category } }),
    placeholderData: keepPreviousData,
    enabled: enabled && !!startDate && !!endDate,
  })
}
// use-lifecycle-curve.ts
export function useLifecycleCurve(productId: number,
  { startDate, endDate, enabled = true }: UseLifecycleCurveParams = {}) {
  return useQuery({
    queryKey: ['lifecycle-curve', productId, { startDate, endDate }],
    queryFn: () => api<LifecycleCurveResponse>(
      `/dimensions/products/${productId}/lifecycle-curve`,
      { params: { start_date: startDate, end_date: endDate } }),
    enabled: enabled && productId > 0,
  })
}
```

### Detail page layout (`store-detail.tsx`; `product-detail.tsx` is the symmetric twin)
```text
export default function StoreDetailPage()
- const { storeId } = useParams(); const id = Number(storeId); guard Number.isNaN → ErrorDisplay.
- Header: "Back to Stores" Link + <h1>{store.name}</h1>; profile Card (code/region/city/type) from useStore(id).
- <DateRangePicker> — default last 30 days (subDays(new Date(),30)..new Date()).
- 4 <KPICard>s from useKPIs({ storeId:id, startDate, endDate }) — revenue/units/transactions/avg basket.
- <TimeSeriesChart title="Revenue over time" data={points.map(p => ({date:p.period, actual:Number(p.metrics.total_revenue)}))} showPredicted={false}/>
  from useTimeseries({ storeId:id, startDate, endDate, granularity:'day' }).
- "Top products" — useDrilldowns({ dimension:'product', storeId:id, startDate, endDate }) → list or <RevenueBarChart>.
- "View in Sales" <Link to={`/explorer/sales?store_id=${id}`}>.
- Reuse LoadingState / ErrorDisplay; build with frontend-design + shadcn-ui.

product-detail.tsx delta: useProduct(id); useKPIs/useTimeseries with productId;
useDrilldowns({ dimension:'store', productId:id }) for "Top stores"; PLUS
useLifecycleCurve(id) → <TimeSeriesChart title="Lifecycle demand curve"
data={points.map(p=>({date:p.date, actual:p.multiplier}))} showPredicted={false}/>.
"View in Sales" → /explorer/sales?product_id=${id}.
```

### list of tasks (in execution order)
```yaml
Task 1 — Tracking GitHub issue:
  - Open ONE issue: "Explorer interactivity: detail views, richer tables, Sales
    charts, cross-filtering". Note it spans analytics + dimensions + ui scopes.
  - Confirm: `gh issue view <N> --json state`. Every commit below references (#N).
  - Branch: `git switch -c feat/explorer-interactivity` off an up-to-date dev.

Task 2 — Backend: /analytics/timeseries endpoint:
  MODIFY app/features/analytics/schemas.py
    - Append TimeSeriesPoint + TimeSeriesResponse (see "Backend data models").
      Reuse KPIMetrics + TimeGranularity; do NOT add strict=True.
  MODIFY app/features/analytics/service.py
    - Add `from sqlalchemy import Date` and `from sqlalchemy import cast as sa_cast`.
    - Add TimeGranularity/TimeSeriesPoint/TimeSeriesResponse to the schemas import.
    - Add `compute_timeseries` (see "Backend service" pseudocode).
  MODIFY app/features/analytics/routes.py
    - Add TimeGranularity/TimeSeriesResponse to the schemas import.
    - Add `@router.get("/timeseries", response_model=TimeSeriesResponse, ...)`
      mirroring get_kpis; reuse validate_date_range.
  VALIDATE: uv run ruff check app/features/analytics/ && uv run mypy app/features/analytics/ &&
    uv run pyright app/features/analytics/ &&
    uv run python -c "from app.main import app; assert any('timeseries' in r.path for r in app.routes)"

Task 3 — Backend: dimensions sort params:
  MODIFY app/features/dimensions/routes.py — add sort_by/sort_order Query params
    to the stores-list (lines 33-92) and products-list (lines 144-203) handlers;
    pass them into the service calls.
  MODIFY app/features/dimensions/service.py — add sort_by/sort_order params to
    list_stores/list_products; allow-list dict → mapped column; apply .order_by();
    UNKNOWN/None sort_by keeps the existing default (Store.code / Product.sku).
  VALIDATE: uv run ruff check app/features/dimensions/ && uv run mypy app/features/dimensions/ &&
    uv run pyright app/features/dimensions/

Task 4 — Backend: tests (closes the analytics test gap):
  MODIFY app/features/analytics/tests/conftest.py
    - Append DB fixtures copied verbatim from app/features/backtesting/tests/
      conftest.py: db_session, client, sample_store, sample_product,
      sample_calendar_120, sample_sales_120. Keep the existing unit fixtures.
  CREATE app/features/analytics/tests/test_schemas.py
    - Unit: construct TimeSeriesPoint/TimeSeriesResponse; assert total_points>=0,
      granularity enum coercion. Runs under -m "not integration".
  CREATE app/features/analytics/tests/test_routes_integration.py
    - @pytest.mark.integration class: GET /analytics/timeseries 200 for
      granularity=day and granularity=week against sample_sales_120; assert
      points ascending by period and len(points)==total_points; test store_id
      filter; test end_date<start_date → 400. Smoke-test /analytics/kpis +
      /analytics/drilldowns (slice had none).
  MODIFY app/features/dimensions/tests/conftest.py
    - Append the same DB fixtures + a multi-row fixture (e.g. sample_stores_multi
      / sample_products_multi: 3 rows with TEST-* codes/skus and deliberately
      non-aligned names so asc-by-code != asc-by-name).
  CREATE app/features/dimensions/tests/test_sort.py
    - @pytest.mark.integration: sort_by=name asc/desc correctness on stores +
      products; unknown sort_by → default order, no error; omitted params ==
      prior behavior.
  GOTCHA: new .py files — run `git diff --stat` afterwards, confirm no EOL churn.
  VALIDATE: uv run pytest -v -m "not integration" app/features/analytics/tests/test_schemas.py
    then: docker compose up -d && uv run alembic upgrade head &&
    uv run pytest -v -m integration app/features/analytics/tests app/features/dimensions/tests

Task 5 — Frontend: types + hooks:
  MODIFY frontend/src/types/api.ts — add TimeGranularity, TimeSeriesPoint,
    TimeSeriesResponse, LifecyclePoint, LifecycleCurveResponse (see "Frontend types").
  CREATE frontend/src/hooks/use-timeseries.ts + use-lifecycle-curve.ts (see pseudocode).
  MODIFY frontend/src/hooks/use-stores.ts + use-products.ts — add optional
    sortBy?:string / sortOrder?:'asc'|'desc'; thread into queryKey + api params
    as sort_by/sort_order. Keep optional so existing call sites compile.
  MODIFY frontend/src/hooks/index.ts — add `export * from './use-timeseries'`
    and `export * from './use-lifecycle-curve'`.
  VALIDATE: cd frontend && pnpm tsc --noEmit

Task 6 — Frontend: shared interactive components:
  MODIFY frontend/src/components/data-table/data-table.tsx
    - Add optional `onRowClick?: (row: TData) => void`; when set, add
      onClick + `cursor-pointer` to each data <TableRow> (NOT skeleton/empty rows).
    - Add optional `enableColumnVisibility?: boolean`; add internal
      useState<VisibilityState> + onColumnVisibilityChange + state.columnVisibility;
      when enabled render <DataTableViewOptions table={table}/> above the table.
    - All additive — runs.tsx and every caller must still compile.
  CREATE frontend/src/components/data-table/data-table-view-options.tsx
    - DropdownMenu of DropdownMenuCheckboxItem per table.getAllColumns()
      .filter(c=>c.getCanHide()), bound to getIsVisible()/toggleVisibility().
  CREATE frontend/src/components/data-table/data-table-column-header.tsx
    - <DataTableColumnHeader column title> — a Button that calls
      column.toggleSorting(); shows an up/down/none chevron from lucide-react.
  MODIFY frontend/src/components/data-table/index.ts — barrel +2 lines.
  CREATE frontend/src/components/charts/revenue-bar-chart.tsx
    - RevenueBarChart({title,description?,data:{label,revenue}[],height?,className?})
      — Recharts BarChart in ChartContainer/Card; mirror backtest-folds-chart.tsx.
  MODIFY frontend/src/components/charts/index.ts — barrel +1 line.
  CREATE frontend/src/lib/csv-export.ts
    - toCsv<T>(rows, columns:{key,header}[]) : string — RFC-4180 quoting, CRLF rows.
    - downloadCsv(filename, csv) — Blob + createObjectURL + <a download> + revoke.
  VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 7 — Frontend: routing:
  MODIFY frontend/src/lib/constants.ts — ROUTES.EXPLORER += STORE_DETAIL:
    '/explorer/stores/:storeId', PRODUCT_DETAIL: '/explorer/products/:productId'.
    Do NOT add to NAV_ITEMS.
  MODIFY frontend/src/App.tsx — 2 lazy imports (StoreDetailPage, ProductDetailPage)
    + 2 <Route>s wrapped in <Suspense fallback={<PageLoader/>}>, inside <AppShell/>.

Task 8 — Frontend: detail pages:
  CREATE frontend/src/pages/explorer/store-detail.tsx (see "Detail page layout").
  CREATE frontend/src/pages/explorer/product-detail.tsx (symmetric twin +
    useLifecycleCurve). Build with frontend-design + shadcn-ui.
  VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 9 — Frontend: richer Stores + Products tables:
  MODIFY frontend/src/pages/explorer/stores.tsx
    - useNavigate(); onRowClick → `/explorer/stores/${s.id}`.
    - SortingState; pass sorting/onSortingChange to DataTable; derive sortBy/
      sortOrder from sorting[0] → useStores. Sortable columns use DataTableColumnHeader.
    - useSearchParams: persist search/region/store_type/page/sort; init state from URL.
    - "Export CSV" Button (toCsv+downloadCsv on data.stores); enableColumnVisibility.
    - Reset pageIndex to 0 on sort/filter/search change.
  MODIFY frontend/src/pages/explorer/products.tsx — same treatment
    (search/category/brand/page/sort in URL; row-click → /explorer/products/:id).
  VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 10 — Frontend: Runs table (export + view-options only):
  MODIFY frontend/src/pages/explorer/runs.tsx — add CSV export + enableColumnVisibility.
    NO server sort, NO detail route (out of scope for Runs).
  VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 11 — Frontend: Sales page charts + cross-filtering:
  MODIFY frontend/src/pages/explorer/sales.tsx
    - useSearchParams: read store_id/product_id (cross-filter) → pass to
      useDrilldowns; show a dismissible Badge "Filtered to store/product #N".
    - Persist dimension + date range in the URL.
    - <RevenueBarChart> fed by drilldown items ({label:dimension_value,
      revenue:Number(metrics.total_revenue)}).
    - <TimeSeriesChart> fed by useTimeseries({startDate,endDate,granularity:'day',
      storeId,productId}); guard behind data?.points?.length.
    - Keep the existing ranked list below the charts.
  VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 12 — Frontend test:
  CREATE frontend/src/lib/csv-export.test.ts — vitest (mirror use-demo-pipeline.test.ts):
    toCsv empty rows → header-only; quoting/escaping of , " \n; header order.
    Do NOT test downloadCsv (DOM side-effect).
  VALIDATE: cd frontend && pnpm lint && pnpm tsc --noEmit && pnpm test --run

Task 13 — Docs:
  MODIFY README.md — mention store/product detail pages + Sales charts in the
    feature list.
  MODIFY docs/_base/API_CONTRACTS.md — add the `GET /analytics/timeseries` row
    to the HTTP Endpoints table; note the new `/dimensions` sort params.
  MODIFY docs/_base/REPO_MAP_INDEX.md — add rows for store-detail.tsx /
    product-detail.tsx.

Task 14 — Dogfood the running UI (mandatory per ui-design.md):
  - docker compose up -d ; uv run alembic upgrade head ;
    uv run python scripts/seed_random.py --full-new --seed 42 --confirm.
  - uv run uvicorn app.main:app --port 8123 & ; cd frontend && pnpm dev.
  - Via webapp-testing / agent-browser, exercise the 9 scenarios in
    Validation Level 4 below. Capture screenshots of both detail pages + Sales.

Task 15 — Commit + PR:
  Branch feat/explorer-interactivity (Task 1). Commits, each (#issue), no AI trailer:
    1. feat(analytics): add GET /analytics/timeseries aggregated sales endpoint (#N)
    2. feat(dimensions): add sort_by/sort_order to store + product listings (#N)
    3. feat(ui): explorer store + product detail pages (#N)
    4. feat(ui): richer explorer tables — sorting, csv export, column visibility (#N)
    5. feat(ui): sales charts + url-state cross-filtering (#N)
    6. test(ui): csv-export pure-helper coverage (#N)
    7. docs(docs): document the explorer interactivity extension (#N)
  Open PR into dev; CI green; merge.
```

### Integration Points
```yaml
DATABASE:  NONE — no migration, no schema change. Read aggregates only.
BACKEND:   analytics slice — +1 route, +1 service method, +2 schemas.
           dimensions slice — +2 query params, allow-listed ordering.
           app/main.py UNCHANGED (analytics router already wired).
CONFIG:    NONE — no new env var. The 730-day cap reuses
           settings.analytics_max_date_range_days via validate_date_range.
FRONTEND ROUTING:
  - ROUTES.EXPLORER.STORE_DETAIL + PRODUCT_DETAIL (constants.ts).
  - Two lazy dynamic <Route>s in App.tsx (:storeId / :productId).
  - NAV_ITEMS unchanged (detail pages are click-through, not nav items).
CI:
  - No new workflow. ci.yml covers it. Because analytics + dimensions .py files
    change, the ruff/mypy/pyright/pytest jobs are load-bearing — keep green.
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
# Watch: the sa_cast alias + the ColumnElement[Any] bucket annotation in
# compute_timeseries are the most likely failures here.
```

### Level 3: Unit + Integration Tests
```bash
uv run pytest -v -m "not integration"          # incl. analytics test_schemas.py
docker compose up -d && uv run alembic upgrade head
uv run pytest -v -m integration app/features/analytics/tests app/features/dimensions/tests
cd frontend && pnpm test --run                 # incl. csv-export.test.ts
# If integration tests fail on stale local Postgres:
#   docker compose down -v && docker compose up -d && uv run alembic upgrade head
```

### Level 4: Manual end-to-end (dogfood — REQUIRED, ui-design.md)
```bash
docker compose up -d && uv run alembic upgrade head
uv run python scripts/seed_random.py --full-new --seed 42 --confirm
uv run uvicorn app.main:app --port 8123 &
until curl -fs http://127.0.0.1:8123/health; do sleep 2; done
cd frontend && ./node_modules/.bin/vite --host 0.0.0.0     # http://localhost:5173

# Browser checks via webapp-testing / agent-browser:
#  1. /explorer/stores → click a row → /explorer/stores/:id with KPIs + revenue chart + top products.
#  2. Sort the Stores table by Name desc → order changes ACROSS pages (server-side).
#  3. Export CSV → file downloads with the visible columns.
#  4. Toggle a column off via "View" → column hides.
#  5. /explorer/products/:id → lifecycle curve renders (flat at 1.0 if no launch_date).
#  6. /explorer/sales → bar chart + line chart render; switch dimension tab → charts update.
#  7. From a store detail page click "View in Sales" → Sales scoped to that store (badge shown).
#  8. Apply filters on Stores, copy the URL, open in a new tab → identical filtered view.
#  9. curl "http://localhost:8123/analytics/timeseries?start_date=2026-04-01&end_date=2026-05-01&granularity=week"
#     → 200 with ascending points.
```

---

## Final Validation Checklist
- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run mypy app/ && uv run pyright app/` clean (both --strict)
- [ ] `uv run pytest -v -m "not integration"` green (incl. analytics test_schemas.py)
- [ ] `uv run pytest -v -m integration app/features/analytics/tests app/features/dimensions/tests` green
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` clean
- [ ] `GET /analytics/timeseries` returns ascending points for day/week/month/quarter,
      honors store/product/category filters, 400s on inverted/over-cap range
- [ ] `GET /dimensions/stores|products` accept sort_by/sort_order; omitted == prior
      behavior; unknown sort_by → default order, no error
- [ ] Row-click on Stores/Products → working detail pages with KPIs + chart + drilldown
- [ ] Stores/Products tables: server sorting + CSV export + column visibility; Runs: export + visibility
- [ ] Sales page shows bar chart + line chart; applies ?store_id/?product_id; URL state round-trips
- [ ] "View in Sales" carries the entity filter; detail pages dogfooded in a real browser (screenshots)
- [ ] No Alembic migration; no app/main.py change; no new slice; no .env var
- [ ] README + API_CONTRACTS.md + REPO_MAP_INDEX.md updated
- [ ] Branch `feat/explorer-interactivity`; every commit references the Task-1 issue; no AI co-author trailer

---

## Anti-Patterns to Avoid
- ❌ Don't import `cast` plain from sqlalchemy in analytics/service.py — it
  shadows the existing `typing.cast`. Alias it: `cast as sa_cast`.
- ❌ Don't add an Alembic migration — every new query is a read aggregate; the
  schema does not change.
- ❌ Don't interpolate `sort_by` into the query — resolve it through an
  allow-list dict to a real mapped column; unknown → default order, never 400.
- ❌ Don't reuse `/analytics/drilldowns?dimension=date` for the charts — it caps
  at 100 items, orders by revenue, and has no week/month bucketing.
- ❌ Don't do client-only table sorting — DataTable is `manualSorting:true`;
  sort MUST round-trip to the backend.
- ❌ Don't re-implement a page-size selector — `data-table-pagination.tsx`
  already has one.
- ❌ Don't make `DataTableProps` changes non-optional — every existing caller
  (runs.tsx etc.) must compile unchanged.
- ❌ Don't feed string Decimals into Recharts — `Number(x)` first.
- ❌ Don't edit `app/main.py` — the analytics router is already wired.
- ❌ Don't hand-roll the pages without `frontend-design` / `shadcn-ui`, and
  don't claim "done" on a green `tsc` — dogfood in a real browser.
- ❌ Don't `git push --force` on dev/main; no AI co-author trailers; every
  commit references the open issue.

---

## Confidence Score

**7 / 10** for one-pass implementation success.

**Why solid:**
- Almost entirely additive and well-patterned. The new endpoint is a near-clone
  of `compute_kpis`; the detail pages mirror `sales.tsx` + `dashboard.tsx`; the
  charts reuse `TimeSeriesChart` and the `backtest-folds-chart.tsx` pattern; the
  routes register exactly like the existing Explorer routes. No migration, no
  new slice, no `main.py` change.
- Every cited file carries verified line numbers; the two highest-risk backend
  traps (`cast` name collision, `date_trunc` strict typing) are called out with
  the exact fix.
- Validation gates are concrete, layered, and fast; the dogfood checklist has 9
  explicit scenarios.

**Why not higher:**
- Genuinely large — 15 tasks across two layers, ~25 files. More surface = more
  room for a small mistake; the per-task `VALIDATE` keeps it recoverable but a
  single pass is ambitious.
- The `analytics` slice has **no test infrastructure** — Task 4 must stand up DB
  fixtures from scratch (copied from `backtesting`). This is the least
  mechanical task and the most likely to need a second pass.
- The four upgraded pages are real UI composition — layout/hierarchy/URL-state
  need the real-browser dogfood (Task 14); a green `tsc` will not catch a
  cramped detail page or a dropped `useSearchParams` sync.

All identified risks are caught by the validation loop (strict type-check +
integration tests + browser dogfood) and the fixes are local. Executing the
tasks in order and running each `VALIDATE` before moving on is what carries it.
