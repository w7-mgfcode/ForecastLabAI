name: "PRP-24 — ForecastOps Control Center"
description: |
  Context-rich PRP for a new read-only `ops` backend slice + an `/ops` frontend
  Control Center page that aggregates operational state (jobs, runs, aliases,
  data freshness) and ranks retraining candidates. One-pass implementation target.

## Purpose

Add an operator-facing dashboard that connects ForecastLabAI's isolated Explorer/Visualize
pages into one workflow. A new read-only vertical slice `app/features/ops/` exposes two
server-side aggregation endpoints; a new `frontend/src/pages/ops.tsx` page consumes them.

---

## Goal

Ship a fully working ForecastOps Control Center:

- **Backend** — a new read-only slice `app/features/ops/` with two endpoints:
  - `GET /ops/summary` — system health, job-status counts, run/alias health, data
    freshness, and a "needs attention" list (failed jobs/runs + stale aliases).
  - `GET /ops/retraining-candidates?limit=` — a `(store, product)` queue ranked by a
    deterministic retraining-priority score.
- **Frontend** — a new `/ops` page wired into the top nav, consuming both endpoints,
  reusing existing `KPICard` / `StatusBadge` / `Card` / `Table` / loading-error-empty
  components, with attention items linking to existing Explorer detail pages.

End state: `docker compose up` → seed → open `/ops` → operator sees, at a glance, what
needs attention. No new tables, no Alembic migration, no new external dependency.

## Why

- **User value** — operators can answer "which forecasts need attention?" without
  cross-referencing four CRUD pages. Failed jobs and stale models become visible before
  they affect decisions. Retraining candidates are ranked by recency + error.
- **Demo value** — reviewers see a mature ForecastOps story instead of isolated CRUD pages.
- **Integration** — this is the natural layer above the existing `jobs`, `registry`,
  `backtesting`, and `analytics` slices and the Explorer pages. It reads their state; it
  does not duplicate it.
- **Source docs** — `docs/optional-features/02-forecastops-control-center.md` (feature
  brief) and `.agents/plans/forecastops-control-center.md` (the 17-task implementation
  plan this PRP is derived from).

## What

### User-visible behavior

A new **Control Center** nav item opens `/ops`, a dense single page with:

1. **System Health** card — API up, database connected, embedding-provider reachability,
   timestamp of the latest successful job.
2. **KPI row** — Active Jobs, Failed Jobs, Run Success Rate, Stale Aliases.
3. **Data Freshness** card — latest sales date, latest completed job, latest successful run.
4. **Needs Attention** table — recent failed jobs, failed runs, and stale aliases; each row
   links to the matching Explorer detail page.
5. **Retraining Queue** table — `(store, product)` pairs ranked by priority score, showing
   staleness, WAPE, and a human-readable reason.

The page polls every 15 s, shows loading/error/empty states, and degrades gracefully when
fields are null (no sales yet, metrics missing, etc.).

### Technical requirements

- New vertical slice `app/features/ops/` with `__init__.py`, `schemas.py`, `service.py`,
  `routes.py`, `tests/`. **No `models.py`, no migration** (read-only — mirrors `analytics`).
- Server-side SQL aggregation (`COUNT … GROUP BY`, `DISTINCT ON`) — never fetch lists and
  count in Python.
- RFC 7807 errors, Pydantic v2 response models, SQLAlchemy 2.0 async, `mypy --strict` +
  `pyright --strict` clean.
- Frontend: new page + hook module + pure util module (+ vitest tests) + route + nav item +
  API response types.

### Success Criteria

- [ ] `GET /ops/summary` → 200 with `system`, `jobs`, `runs`, `aliases`, `freshness`,
      `attention_items`, `generated_at`.
- [ ] `GET /ops/retraining-candidates` → 200, candidates sorted by `priority_score` desc,
      honoring `limit`; 422 when `limit` is outside `[1, 100]`.
- [ ] `GET /ops/summary` → 200 (never 500) when the database has no jobs/runs/aliases.
- [ ] `/ops` page renders all five sections, appears in the top nav, and attention items
      link to the correct Explorer detail routes.
- [ ] Backend reads sibling slices via **ORM models only** (no `service.py`/`schemas.py`
      cross-slice imports); the vertical-slice tension is called out in the PR description.
- [ ] All validation gates pass: `ruff`, `mypy --strict`, `pyright --strict`, `pytest`
      (unit + integration), frontend `tsc` + `lint` + `test`.
- [ ] No new external dependency, no new table, no Alembic migration.

---

## All Needed Context

### DECISIONS LOCKED (resolved during planning — do NOT re-litigate)

1. **Backend approach** — a real `app/features/ops/` slice that **imports the ORM models**
   of sibling slices (`Job`, `ModelRun`, `DeploymentAlias`, `SalesDaily`) for server-side
   SQL aggregation. This is a deliberate, accepted tension with the *"a slice may NOT import
   from another slice"* rule (`AGENTS.md` § Architecture). `data_platform` ORM is already a
   sanctioned cross-slice import (`analytics` uses it); importing `jobs`/`registry` ORM is
   the new tension. **Restrict imports to ORM models + read-only `select()` — NEVER import a
   sibling `service.py` or `schemas.py`.** The chosen alternative over an `ASGITransport`
   in-process-HTTP approach (the `demo` slice's pattern). **MUST be called out in the PR
   description** per `.claude/rules/product-vision.md` § "When Ideas Don't Align".
2. **Scope** — feature-doc MVP **plus** the retraining-candidate queue: two endpoints total.
   `/ops/model-health` and `/ops/job-health` from the feature brief are **folded into
   `/ops/summary`** (model-health → the alias section; job-health → the jobs section).
   **Deferred — do NOT build:** drift indicators, bulk-action queue, action drawer,
   WebSocket live updates, exportable incident report.
3. **Provider health** — `config.service.get_provider_health()` is a *service function*, so
   the `ops` backend does NOT import it. The frontend reuses the **existing**
   `useProviderHealth()` hook from `frontend/src/hooks/use-config.ts` (it already calls
   `GET /config/providers/health`).

### Documentation & References

```yaml
# MUST READ — backend slice pattern to mirror exactly
- file: app/features/analytics/routes.py
  why: Canonical read-only aggregation router. Router decl: `router = APIRouter(prefix="/analytics", tags=["analytics"])`. Endpoint signatures, Query() validation, `db: AsyncSession = Depends(get_db)`, `response_model=`. Imports header lines 1-23.
- file: app/features/analytics/service.py
  why: `AnalyticsService` class; SQLAlchemy 2.0 `select()` + `func.sum/count`; `.where()` before `.group_by()`; `DISTINCT ON` latest-per-grain in `compute_inventory_status`; `result.one()/.all()`; `logger.info("analytics.<event>", ...)`.
- file: app/features/analytics/schemas.py
  why: Pydantic v2 response models — `model_config = ConfigDict(from_attributes=True)`, `Field(..., description=...)`, str-Enum pattern.
- file: app/features/analytics/__init__.py
  why: EXACT slice `__init__.py` shape to mirror (docstring + imports + `__all__`).
- file: app/features/analytics/tests/conftest.py
  why: `db_session` + `client` fixtures; `app.dependency_overrides[get_db]`; `AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`; `TEST-`-prefixed sample data; FK-safe cleanup.
- file: app/features/analytics/tests/test_routes_integration.py
  why: `@pytest.mark.integration` + `@pytest.mark.asyncio`, `client.get(path, params=...)`, status + JSON assertions.
- file: app/features/analytics/tests/test_schemas.py
  why: Unmarked unit tests for Pydantic construction/validation.

# MUST READ — data-source ORM models (the `ops` service queries these)
- file: app/features/jobs/models.py
  why: `Job` table `job`; `JobStatus`/`JobType` enums; columns incl. `job_id`, `status`, `completed_at`, `created_at`, `error_message`, `error_type`, `run_id`.
- file: app/features/registry/models.py
  why: `ModelRun` table `model_run` (status, model_type, metrics JSONB, data_window_end, store_id, product_id, completed_at, created_at); `RunStatus` enum; `DeploymentAlias` table `deployment_alias` (alias_name, run_id FK→model_run.id, relationship `.run`).
- file: app/features/data_platform/models.py
  why: `SalesDaily` (table `sales_daily`, column `date: Mapped[datetime.date]`) — for the latest-sales-date freshness query.
- file: app/core/database.py
  why: `get_db` async dependency (auto-commit/rollback) and `Base`. Import: `from app.core.database import get_db`.
- file: app/core/exceptions.py
  why: `BadRequestError` etc.; RFC 7807 handler already registered in `app/main.py`.
- file: app/core/health.py
  why: DB-connectivity check pattern — `await db.execute(text("SELECT 1"))` in try/except.
- file: app/main.py
  why: router import + `app.include_router(...)` wiring (analytics: import line 17, include line 133).

# MUST READ — frontend patterns
- file: frontend/src/pages/visualize/demand.tsx
  why: Closest dense data page — header, error→loading→empty early returns, hooks, useMemo, Card/Table, inline helper subcomponents, `@/` imports.
- file: frontend/src/hooks/use-runs.ts
  why: TanStack Query hook module pattern to mirror for `use-ops.ts`.
- file: frontend/src/hooks/use-jobs.ts
  why: `refetchInterval` polling pattern.
- file: frontend/src/hooks/use-config.ts
  why: ALREADY EXPORTS `useProviderHealth()` — reuse it, do NOT duplicate.
- file: frontend/src/lib/api.ts
  why: `api<T>(endpoint, config)` generic client; `ApiError`; `formatNumber`/`formatPercent`.
- file: frontend/src/types/api.ts
  why: response-type conventions; `ProviderHealth` already at line ~575; reuse `JobStatus`/`RunStatus` unions.
- file: frontend/src/lib/constants.ts
  why: `ROUTES` object + `NAV_ITEMS` array — add `ROUTES.OPS` + a single-link nav entry.
- file: frontend/src/lib/status-utils.ts
  why: ALREADY EXPORTS `getStatusVariant(status)` → StatusBadge variant — reuse for job/run status badges.
- file: frontend/src/App.tsx
  why: lazy-load + `<Suspense>` + `<Route>` inside `<Route element={<AppShell/>}>`.
- file: frontend/src/components/charts/kpi-card.tsx
  why: `KPICard` props — `title`, `value:string|number`, `description?`, `icon?:LucideIcon`, `trend?`, `isLoading?`.
- file: frontend/src/components/common/status-badge.tsx
  why: `StatusBadge` variants — `default|success|warning|error|info|pending`.
- file: frontend/src/components/common/error-display.tsx
  why: `ErrorDisplay({error,title?,onRetry?})` + `EmptyState({title,description?,action?,icon?})`.
- file: frontend/src/lib/knowledge-utils.ts
  why: pattern for a PURE util module + colocated `*.test.ts` vitest file.

# External docs
- url: https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#aggregate-functions-with-group-by-having
  why: `select(Job.status, func.count()).group_by(Job.status)` aggregation.
- url: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#postgresql-distinct-on
  why: `.distinct(col, col)` DISTINCT ON — order_by MUST lead with the same columns.
- url: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
  why: `await db.execute(select(...))`, `.scalar()`, `.scalars()`, `.all()`.
- url: https://fastapi.tiangolo.com/tutorial/query-params-str-validations/
  why: `Query(default=20, ge=1, le=100)` bounded validation.
- url: https://tanstack.com/query/latest/docs/framework/react/reference/useQuery
  why: `refetchInterval`, `enabled`, `queryKey` for polling hooks.
- url: https://docs.pydantic.dev/latest/concepts/config/
  why: `ConfigDict(from_attributes=True)` for ORM-row → Pydantic response models.

- docfile: .agents/plans/forecastops-control-center.md
  why: The full 17-task implementation plan with per-task IMPLEMENT/PATTERN/GOTCHA/VALIDATE.
- docfile: docs/optional-features/02-forecastops-control-center.md
  why: Original feature brief — UX sections, risk model, validation plan.
```

### Current Codebase tree (relevant subset)

```bash
app/
├── main.py                              # router wiring — UPDATE
├── core/
│   ├── database.py                      # get_db, Base
│   ├── exceptions.py                    # BadRequestError, RFC 7807
│   └── health.py                        # SELECT 1 connectivity pattern
├── features/
│   ├── analytics/                       # ← MIRROR THIS SLICE (read-only aggregation)
│   │   ├── __init__.py  routes.py  schemas.py  service.py
│   │   └── tests/ (conftest.py, test_routes_integration.py, test_schemas.py)
│   ├── jobs/models.py                   # Job, JobStatus, JobType
│   ├── registry/models.py               # ModelRun, RunStatus, DeploymentAlias
│   └── data_platform/models.py          # SalesDaily
frontend/src/
├── App.tsx                              # route registration — UPDATE
├── hooks/ (use-runs.ts, use-jobs.ts, use-config.ts, index.ts)
├── lib/ (api.ts, constants.ts, status-utils.ts, knowledge-utils.ts)
├── types/api.ts                         # response types — UPDATE
├── pages/visualize/demand.tsx           # ← MIRROR for the dense page layout
└── components/ (charts/kpi-card.tsx, common/status-badge.tsx, common/error-display.tsx)
```

### Desired Codebase tree (files to add / touch)

```bash
app/features/ops/                        # NEW SLICE — read-only, no models.py, no migration
├── __init__.py                          # NEW — slice exports (mirror analytics/__init__.py)
├── schemas.py                           # NEW — Pydantic v2 response models
├── service.py                           # NEW — OpsService + pure score/extract helpers
├── routes.py                            # NEW — APIRouter(prefix="/ops") + 2 endpoints
└── tests/
    ├── __init__.py                      # NEW — empty package marker
    ├── conftest.py                      # NEW — db_session, client, sample-data fixtures
    ├── test_schemas.py                  # NEW — unit (unmarked)
    ├── test_service.py                  # NEW — unit for score_retraining_candidate/extract_wape
    └── test_routes_integration.py       # NEW — @pytest.mark.integration

app/main.py                              # UPDATE — import + include_router(ops_router)

frontend/src/
├── hooks/use-ops.ts                     # NEW — useOpsSummary, useRetrainingCandidates
├── hooks/index.ts                       # UPDATE — export * from './use-ops'
├── lib/ops-utils.ts                     # NEW — pure helpers
├── lib/ops-utils.test.ts                # NEW — vitest unit tests
├── pages/ops.tsx                        # NEW — the Control Center page
├── types/api.ts                         # UPDATE — Ops* response interfaces
├── lib/constants.ts                     # UPDATE — ROUTES.OPS + NAV_ITEMS entry
└── App.tsx                              # UPDATE — lazy import + <Route>
```

### Known Gotchas & Library Quirks

```python
# CRITICAL: ORM status columns are String, NOT enum-typed. Compare against the
#   `.value`, never the enum object — mirror registry/service.py & jobs/service.py:
#     select(Job.status, func.count()).where(Job.status == JobStatus.COMPLETED.value)
#
# CRITICAL: ruff DTZ rules — do NOT use `date.today()` or naive `datetime.now()`.
#   Use timezone-aware forms:
#     now = datetime.now(UTC)              # from `datetime import UTC`
#     today = datetime.now(UTC).date()     # for staleness math
#
# CRITICAL: PostgreSQL DISTINCT ON — `.distinct(a, b)` REQUIRES `order_by` to lead
#   with the SAME columns. Order the "latest" tiebreaker by `created_at.desc()`
#   (TimestampMixin, always non-null) — NOT `completed_at` (nullable; DESC puts
#   NULLs first in Postgres and would pick a NULL-completed row):
#     select(ModelRun).where(ModelRun.status == RunStatus.SUCCESS.value)
#       .distinct(ModelRun.store_id, ModelRun.product_id)
#       .order_by(ModelRun.store_id, ModelRun.product_id, ModelRun.created_at.desc())
#
# CRITICAL: `func.count()` with no arg = COUNT(*) — valid, used by analytics.
#   `select(Col, func.count()).group_by(Col)` returns only EXISTING statuses;
#   zero-fill the missing enum members in Python.
#
# CRITICAL: AsyncSession FORBIDS implicit IO / lazy-loading (SQLAlchemy async
#   docs). The alias query MUST select BOTH entities —
#   `select(DeploymentAlias, ModelRun).join(ModelRun, DeploymentAlias.run_id == ModelRun.id)`
#   — rows come back as (alias, run) tuples; use the joined `ModelRun` row
#   DIRECTLY. NEVER touch the `DeploymentAlias.run` relationship attribute — it
#   triggers a lazy load → `MissingGreenlet` error. Same rule for every
#   relationship: eager-select it or `selectinload()` it; never access it lazily.
#
# CRITICAL: model_run.metrics JSONB is frequently None or lacks WAPE — backtest
#   metrics persist to job.result, NOT model_run.metrics (only an explicit
#   update_run writes run metrics). `extract_wape()` MUST tolerate None / unrelated
#   dicts / non-numeric values. Scoring MUST NEVER raise on missing data.
#
# CRITICAL: DeploymentAlias.run_id is the INTEGER model_run.id (FK), NOT the
#   32-char run_id string. In fixtures set it from the persisted run's `.id`.
#   Insert ModelRun before DeploymentAlias; clean up DeploymentAlias first.
#
# CRITICAL: Pydantic strict-mode linter (app/core/tests/test_strict_mode_policy.py)
#   only inspects request models with ConfigDict(strict=True). Ops schemas are
#   RESPONSE models with ConfigDict(from_attributes=True) — date/datetime fields
#   need NO Field(strict=False). Do NOT add strict=True.
#
# CRITICAL: Cross-slice ORM import is the ACCEPTED design (decision #1). No CI
#   import-linter enforces slice boundaries, so this will not fail the build —
#   but it MUST be flagged in the PR description.
#
# GOTCHA: commit-format scope allow-list has NO `ops` scope. Use feat(api): for
#   backend commits, feat(ui): for frontend, feat(api,ui): for the wiring commit.
#
# GOTCHA: the /ops page renders inside AppShell (<Outlet/>) — do NOT add nav,
#   container, or Toaster. Never hardcode raw colors — use shadcn variants /
#   semantic tokens (.claude/rules/shadcn-ui.md).
```

---

## External Research Findings

Verified May 2026 against the docs the feature brief cited. Each finding ends with a
**verdict** — what it changes (or confirms) for this PRP.

### 1. SQLAlchemy async ORM — `https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html`

The repo pins `sqlalchemy[asyncio]>=2.0.36`; the doc page is the 2.1 line — the async
contract below is identical across 2.0/2.1.

- Execution idioms confirmed: `await session.execute(stmt)` → `.scalars()` / `.all()` /
  `.one()`; single aggregate value via `await session.scalar(select(func.max(col)))`.
- **CRITICAL — implicit IO is forbidden.** *"the application needs to avoid any points at
  which IO-on-attribute access may occur."* Accessing an un-loaded relationship under
  `AsyncSession` raises `MissingGreenlet`. Two safe patterns: eager-select the related
  entity in the same `select(...)`, or `selectinload()` it.
- A single `AsyncSession` is not safe across concurrent tasks — irrelevant here (one
  request = one `get_db` session), but do not `asyncio.gather` queries on the same session.
- **Verdict — applied.** The alias query already selects both entities
  (`select(DeploymentAlias, ModelRun).join(...)`). Added a CRITICAL gotcha: iterate the
  `(alias, run)` tuples and use the joined `ModelRun` directly; **never touch
  `DeploymentAlias.run`**. No other relationship is accessed, so no `selectinload()` is
  needed. No code-shape change beyond the explicit warning.

### 2. FastAPI query-param validation — `https://fastapi.tiangolo.com/tutorial/query-params-str-validations/`

- Bounded numeric query params: `Query(ge=…, le=…)`; a violation returns **HTTP 422**
  (`Unprocessable Entity`) automatically — confirms the `?limit=0` / `?limit=200` → 422
  test cases.
- Current docs favour the `Annotated[int, Query(ge=1, le=100)] = 20` form over the
  legacy `limit: int = Query(default=20, ge=1, le=100)` form.
- **Verdict — mirror the repo, not the docs.** `analytics/routes.py` uses the non-`Annotated`
  `Query(...)` form. Consistency with the existing slice wins (`.claude/rules` § "don't
  create new patterns when existing ones work"). Keep the PRP's `Query(default=20, ge=1,
  le=100, …)` signature; if `analytics/routes.py` is found to use `Annotated`, match that
  instead.

### 3. TanStack Query v5 — `https://tanstack.com/query/.../guides/important-defaults`

- v4→v5 renames: `cacheTime` → `gcTime`; `isLoading` → `isPending` (`isLoading` still
  exists = `isPending && isFetching`); `keepPreviousData` is now
  `placeholderData: keepPreviousData`. `use-runs.ts` already uses the v5 form — mirror it.
- Polling: pair `refetchInterval` with `refetchOnWindowFocus: false` to avoid focus-storms.
  The repo's `query-client.ts` already sets `refetchOnWindowFocus: false` and
  `staleTime: 5min` globally.
- **Verdict — applied.** `useOpsSummary` keeps `refetchInterval: 15000` (operational state
  worth polling); `useRetrainingCandidates` gets **no** `refetchInterval` (slow-moving —
  refetch-on-mount suffices). Task 12 updated accordingly.

### 4. MLflow Model Registry — `https://www.mlflow.org/docs/latest/ml/model-registry/`

- MLflow defines an **alias** as *"a mutable, named reference to a particular version of a
  registered model"*; the `champion`/production-alias promotion pattern decouples
  deployment from a specific version.
- ForecastLabAI's `DeploymentAlias` is the same concept. MLflow frames alias governance as
  managing **staleness** — an alias is "stale" when it still points at an old version
  after a better one exists.
- **Verdict — confirms the design.** The PRP's `is_stale` detection (alias → non-`success`
  run, or a newer `success` run exists for the same store/product) is the industry-standard
  alias-staleness check. No change; cite MLflow as the conceptual basis in the PR.

### 5. NIST AI RMF — `https://www.nist.gov/itl/ai-risk-management-framework`

- Four core functions: **Govern, Map, Measure, Manage**. *Measure* = continuously track
  trustworthiness/performance of deployed AI; *Manage* = act on what monitoring surfaces.
  (Operational depth lives in the AI RMF 1.0 PDF + Playbook, not the overview page.)
- **Verdict — framing only.** The Control Center operationalises *Measure* (model-health
  metrics, freshness) and *Manage* (the "needs attention" + retraining queue). Useful
  one-line justification for the PR description; no implementation impact.

### 6. Model-retraining triggers (MLOps best practice — web search, May 2026)

- Established taxonomy: **time-based** (simple, predictable, but "may lead to unnecessary
  retraining"), **performance-based** (retrain on metric degradation — needs monitoring),
  **drift-based** (data/concept drift — needs drift detection). Sources recommend combining
  signals over a pure time-based trigger.
- **Verdict — confirms the heuristic.** The PRP's score blends a **time-based** signal
  (staleness) with a **performance-based** signal (WAPE) — exactly the recommended hybrid.
  Drift-based is correctly deferred (needs infra the repo doesn't have). When WAPE is
  unknown the score degrades to time-based only — an acceptable, documented fallback. The
  60/40 staleness/error weighting is a defensible, deterministic heuristic; keep it.
- Sources: [When to Retrain Your ML Models](https://tech.flowblog.io/blog/when-to-retrain-your-ml-models-for-success),
  [Model Retraining 2026 (AIMultiple)](https://research.aimultiple.com/model-retraining/),
  [CMU SEI — Automated Retraining](https://www.sei.cmu.edu/blog/improving-automated-retraining-of-machine-learning-models/).

### 7. WAPE as the error signal (web search, May 2026)

- WAPE/WMAPE is volume-weighted — a miss on a high-volume SKU counts more — and is not
  destabilised by low-demand items; it is the recommended single accuracy metric for
  demand forecasting. sMAPE is widely considered broken (unstable near zero, can go
  negative). MAE is interpretable but scale-blind.
- **Verdict — confirms the choice.** Using WAPE as the score's error component is correct.
  There is no universal "bad WAPE" threshold; the score's cap at WAPE 100 (total error =
  total demand) is a reasonable normalisation ceiling. Keep it.
- Sources: [Forecast Accuracy Metrics 2026](https://prospeo.io/s/forecast-accuracy-metrics),
  [MAPE vs WMAPE vs SMAPE](https://medium.com/@vinitkothari.24/time-series-evaluation-metrics-mape-vs-wmape-vs-smape-which-one-to-use-why-and-when-part1-32d3852b4779).

### 8. Cited docs assessed as out-of-scope (do NOT pull these in)

- **OpenTelemetry** (`opentelemetry.io`, `opentelemetry-python-contrib…fastapi`) — the repo
  deliberately ships **no metrics/traces** (`docs/_base/SECURITY.md`: "Metrics — none …
  Traces — none"). The `/ops` Control Center **is** the observability surface. Adding OTel
  would be a new dependency and a scope violation — **do not add it.**
- **scikit-learn model persistence / `TimeSeriesSplit`** — the `ops` slice does no training
  or cross-validation; those belong to `forecasting`/`backtesting`. Not relevant here.
- **Recharts** — MVP is cards + tables (no charts). Recharts is already available
  (`frontend/src/components/ui/chart.tsx`) if a sparkline is wanted in a later iteration;
  deferred, not part of this PRP.

---

## Implementation Blueprint

### Data models and structure — `app/features/ops/schemas.py`

All response models. Every model: `model_config = ConfigDict(from_attributes=True)`.
Every field: `Field(..., description="...")`. Counts: `Field(..., ge=0, ...)`.

```python
# Pydantic v2 response models (NOT request bodies — no strict=True)
class SystemHealth(BaseModel):
    api_ok: bool
    database_connected: bool
    latest_successful_job_at: datetime | None

class StatusCount(BaseModel):
    status: str
    count: int = Field(..., ge=0)

class JobHealth(BaseModel):
    counts: list[StatusCount]          # one per JobStatus, zero-filled
    completed_today: int = Field(..., ge=0)
    failed_total: int = Field(..., ge=0)
    active_total: int = Field(..., ge=0)   # pending + running

class RunHealth(BaseModel):
    counts: list[StatusCount]          # one per RunStatus, zero-filled
    success_rate: float | None         # success / (total - archived); None if denom 0
    failed_total: int = Field(..., ge=0)

class AliasHealth(BaseModel):
    alias_name: str
    run_id: str
    run_status: str
    model_type: str
    store_id: int
    product_id: int
    is_stale: bool
    stale_reason: str | None
    wape: float | None

class DataFreshness(BaseModel):
    latest_sales_date: date | None
    latest_job_completed_at: datetime | None
    latest_run_completed_at: datetime | None

class AttentionItem(BaseModel):
    item_type: Literal["failed_job", "failed_run", "stale_alias"]
    entity_id: str          # job_id for failed_job; run_id for failed_run AND stale_alias
    label: str
    detail: str
    occurred_at: datetime | None

class OpsSummaryResponse(BaseModel):
    system: SystemHealth
    jobs: JobHealth
    runs: RunHealth
    aliases: list[AliasHealth]
    freshness: DataFreshness
    attention_items: list[AttentionItem]
    generated_at: datetime

class RetrainingCandidate(BaseModel):
    store_id: int
    product_id: int
    priority_score: float = Field(..., ge=0.0, le=1.0)
    staleness_days: int = Field(..., ge=0)
    wape: float | None
    latest_run_id: str | None
    latest_run_status: str | None
    reason: str

class RetrainingCandidatesResponse(BaseModel):
    candidates: list[RetrainingCandidate]
    total_evaluated: int = Field(..., ge=0)
    generated_at: datetime
```

### Per-task pseudocode (critical details — not full code)

```python
# ── app/features/ops/service.py — pure helpers (module scope, above OpsService) ──

def extract_wape(metrics: dict[str, Any] | None) -> float | None:
    # GOTCHA: match the param type to ModelRun.metrics' Mapped[...] annotation.
    # Try "wape", "wape_mean", "WAPE"; return first numeric (int|float, not bool); else None.
    if not metrics:
        return None
    for key in ("wape", "wape_mean", "WAPE"):
        v = metrics.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return None

def score_retraining_candidate(staleness_days: int, wape: float | None) -> float:
    """Retraining priority in [0.0, 1.0]; higher = more urgent.
    60% staleness (cap 90 days) + 40% error (cap WAPE 100)."""
    staleness_norm = min(max(staleness_days, 0), 90) / 90.0
    error_norm = min(max(wape, 0.0), 100.0) / 100.0 if wape is not None else 0.0
    return round(0.6 * staleness_norm + 0.4 * error_norm, 4)


# ── OpsService — no custom __init__; just two async methods ──

class OpsService:
    async def get_summary(self, db: AsyncSession) -> OpsSummaryResponse:
        now = datetime.now(UTC)

        # SYSTEM
        try:
            await db.execute(text("SELECT 1"))
            db_ok = True
        except Exception:                       # noqa: BLE001 — connectivity probe
            db_ok = False
        latest_job = await db.scalar(
            select(func.max(Job.completed_at)).where(Job.status == JobStatus.COMPLETED.value)
        )

        # JOBS — server-side GROUP BY, zero-fill the enum
        job_rows = (await db.execute(
            select(Job.status, func.count()).group_by(Job.status))).all()
        job_map = {s: c for s, c in job_rows}
        job_counts = [StatusCount(status=s.value, count=job_map.get(s.value, 0))
                      for s in JobStatus]
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        completed_today = await db.scalar(select(func.count()).select_from(Job).where(
            Job.status == JobStatus.COMPLETED.value, Job.completed_at >= start_of_day)) or 0
        # active_total = pending + running ; failed_total = failed  (from job_map)

        # RUNS — same GROUP BY pattern over RunStatus; success_rate = success/(total-archived)

        # ALIASES — join, compute staleness
        alias_rows = (await db.execute(
            select(DeploymentAlias, ModelRun)
            .join(ModelRun, DeploymentAlias.run_id == ModelRun.id))).all()
        # For each (alias, run): is_stale via _is_alias_stale(run, db-derived newer-success),
        # wape = extract_wape(run.metrics).

        # FRESHNESS
        latest_sales_date = await db.scalar(select(func.max(SalesDaily.date)))
        # latest_job_completed_at, latest_run_completed_at (status==SUCCESS) likewise.

        # ATTENTION ITEMS — 10 most-recent failed jobs + 10 failed runs + every stale alias
        failed_jobs = (await db.execute(
            select(Job).where(Job.status == JobStatus.FAILED.value)
            .order_by(Job.created_at.desc()).limit(10))).scalars().all()
        # failed_job  → AttentionItem(entity_id=job.job_id, occurred_at=job.created_at, ...)
        # failed_run  → AttentionItem(entity_id=run.run_id, ...)
        # stale_alias → AttentionItem(entity_id=<aliased run.run_id>, label="alias '<name>'", ...)

        logger.info("ops.summary_computed", db_ok=db_ok, failed_jobs=..., stale_aliases=...)
        return OpsSummaryResponse(...)

    async def get_retraining_candidates(self, db: AsyncSession, limit: int
                                        ) -> RetrainingCandidatesResponse:
        today = datetime.now(UTC).date()
        # latest SUCCESS run per (store, product) — DISTINCT ON, order_by created_at.desc()
        runs = (await db.execute(
            select(ModelRun).where(ModelRun.status == RunStatus.SUCCESS.value)
            .distinct(ModelRun.store_id, ModelRun.product_id)
            .order_by(ModelRun.store_id, ModelRun.product_id, ModelRun.created_at.desc())
        )).scalars().all()
        candidates = []
        for run in runs:
            staleness = (today - run.data_window_end).days
            wape = extract_wape(run.metrics)
            score = score_retraining_candidate(staleness, wape)
            reason = f"{staleness}d since last train window" + (
                f"; WAPE {wape:.1f}" if wape is not None else "; WAPE unknown")
            candidates.append(RetrainingCandidate(
                store_id=run.store_id, product_id=run.product_id, priority_score=score,
                staleness_days=max(staleness, 0), wape=wape, latest_run_id=run.run_id,
                latest_run_status=run.status, reason=reason))
        candidates.sort(key=lambda c: c.priority_score, reverse=True)
        return RetrainingCandidatesResponse(
            candidates=candidates[:limit], total_evaluated=len(candidates),
            generated_at=datetime.now(UTC))
```

```python
# ── app/features/ops/routes.py ──
router = APIRouter(prefix="/ops", tags=["ops"])

@router.get("/summary", response_model=OpsSummaryResponse,
            summary="Operational summary for the Control Center")
async def get_ops_summary(db: AsyncSession = Depends(get_db)) -> OpsSummaryResponse:
    return await OpsService().get_summary(db)

@router.get("/retraining-candidates", response_model=RetrainingCandidatesResponse,
            summary="Ranked retraining-candidate queue")
async def get_retraining_candidates(
    limit: int = Query(default=20, ge=1, le=100, description="Max candidates to return"),
    db: AsyncSession = Depends(get_db),
) -> RetrainingCandidatesResponse:
    return await OpsService().get_retraining_candidates(db, limit)
```

```typescript
// ── frontend/src/lib/ops-utils.ts — PURE (no React, no fetch) ──
import { ROUTES } from '@/lib/constants'
import type { AttentionItem, RetrainingCandidate, SystemHealth } from '@/types/api'

export function summaryHealthVariant(s: SystemHealth): 'success' | 'error' {
  return s.api_ok && s.database_connected ? 'success' : 'error'
}
export function attentionItemLink(item: AttentionItem): string {
  // failed_job → /explorer/jobs/:id ; failed_run + stale_alias → /explorer/runs/:id
  if (item.item_type === 'failed_job') return `/explorer/jobs/${item.entity_id}`
  return `/explorer/runs/${item.entity_id}`
}
export function attentionBadgeVariant(t: AttentionItem['item_type']): 'error' | 'warning' {
  return t === 'stale_alias' ? 'warning' : 'error'
}
export function formatStaleness(days: number): string {
  return days <= 0 ? 'today' : `${days}d`
}
export function sortRetrainingCandidates(rows: RetrainingCandidate[]): RetrainingCandidate[] {
  return [...rows].sort((a, b) => b.priority_score - a.priority_score)
}
```

### list of tasks to be completed (in order)

```yaml
Task 1 — CREATE app/features/ops/schemas.py:
  - MIRROR pattern from: app/features/analytics/schemas.py
  - DEFINE the 11 response models above; every model ConfigDict(from_attributes=True)
  - IMPORTS: from datetime import date, datetime; from typing import Literal;
             from pydantic import BaseModel, ConfigDict, Field
  - GOTCHA: response models — NO ConfigDict(strict=True), NO Field(strict=False)
  - VALIDATE: uv run python -c "from app.features.ops.schemas import OpsSummaryResponse, RetrainingCandidatesResponse; print('ok')"

Task 2 — CREATE app/features/ops/service.py (pure helpers first):
  - ADD module-scope `extract_wape` and `score_retraining_candidate` (pseudocode above)
  - IMPORTS: from typing import Any
  - GOTCHA: never raise on None/missing metrics
  - VALIDATE: uv run python -c "from app.features.ops.service import score_retraining_candidate as s; assert s(90,100.0)==1.0 and s(0,None)==0.0; print('ok')"

Task 3 — CREATE app/features/ops/tests/__init__.py + test_schemas.py + test_service.py:
  - __init__.py empty
  - test_schemas.py: construct each model; assert ge=0 rejects negatives (pytest.raises(ValidationError))
  - test_service.py: score boundaries (0,None)->0.0, (90,100.0)->1.0, mid, negative clamp,
                     wape>100 clamp; extract_wape each key / None / {} / non-numeric / bool
  - MIRROR: app/features/analytics/tests/test_schemas.py — plain def test_*(), UNMARKED
  - VALIDATE: uv run pytest -v -m "not integration" app/features/ops/tests/test_schemas.py app/features/ops/tests/test_service.py

Task 4 — UPDATE app/features/ops/service.py — implement OpsService:
  - ADD class OpsService (no custom __init__) with get_summary + get_retraining_candidates
  - MIRROR: AnalyticsService.compute_inventory_status (DISTINCT ON), compute_kpis (func + scalar)
  - IMPORTS: from datetime import UTC, datetime;
             from sqlalchemy import func, select, text;
             from sqlalchemy.ext.asyncio import AsyncSession;
             from app.core.logging import get_logger;
             from app.features.jobs.models import Job, JobStatus;
             from app.features.registry.models import DeploymentAlias, ModelRun, RunStatus;
             from app.features.data_platform.models import SalesDaily;
             from app.features.ops.schemas import (... all ...)
  - GOTCHA: compare status == Enum.X.value; use datetime.now(UTC); created_at.desc() for DISTINCT ON
  - VALIDATE: uv run mypy app/features/ops/ && uv run pyright app/features/ops/

Task 5 — CREATE app/features/ops/routes.py:
  - MIRROR: app/features/analytics/routes.py header + endpoint signatures
  - router = APIRouter(prefix="/ops", tags=["ops"]); 2 endpoints (pseudocode above)
  - VALIDATE: uv run python -c "from app.features.ops.routes import router; print(sorted(r.path for r in router.routes))"

Task 6 — CREATE app/features/ops/__init__.py:
  - MIRROR: app/features/analytics/__init__.py — docstring + imports + __all__
  - VALIDATE: uv run python -c "from app.features.ops import router, OpsService; print('ok')"

Task 7 — UPDATE app/main.py:
  - FIND the block of `from app.features.<x>.routes import router as <x>_router` imports
  - INJECT: from app.features.ops.routes import router as ops_router
  - FIND in create_app(): the run of `app.include_router(...)` calls
  - INJECT: app.include_router(ops_router)   (e.g. after analytics_router)
  - PRESERVE ruff import sorting (keep grouped with app.features.* imports)
  - VALIDATE: uv run python -c "from app.main import app; p={r.path for r in app.routes}; assert '/ops/summary' in p and '/ops/retraining-candidates' in p; print('wired')"

Task 8 — CREATE app/features/ops/tests/conftest.py:
  - MIRROR: app/features/analytics/tests/conftest.py (db_session, client fixtures verbatim;
    extend TEST- cleanup to Job/ModelRun/DeploymentAlias — DeploymentAlias before ModelRun)
  - ADD fixtures: sample_jobs (statuses incl. failed+error_message),
    sample_runs (statuses incl. success with metrics={"wape":31.0} + failed; varied
    store_id/product_id/data_window_end), sample_alias (DeploymentAlias→success run),
    sample_sales (a couple SalesDaily rows)
  - GOTCHA: DeploymentAlias.run_id = persisted run.id (int); insert ModelRun first
  - VALIDATE: uv run pytest -m integration app/features/ops/tests/ --collect-only

Task 9 — CREATE app/features/ops/tests/test_routes_integration.py:
  - @pytest.mark.integration + @pytest.mark.asyncio
  - tests: /ops/summary 200 happy (seeded) ; /ops/summary 200 resilient (no fixtures →
    counts >= 0, status keys all present) ; /ops/retraining-candidates 200 sorted desc,
    len <= limit ; ?limit=0 → 422 ; ?limit=200 → 422
  - MIRROR: app/features/analytics/tests/test_routes_integration.py
  - GOTCHA: idempotent — assert structural invariants, not exact global totals
  - VALIDATE: docker compose up -d && uv run pytest -v -m integration app/features/ops/

Task 10 — UPDATE frontend/src/types/api.ts:
  - ADD interfaces: SystemHealth, StatusCount, JobHealth, RunHealth, AliasHealth,
    DataFreshness, AttentionItem, OpsSummaryResponse, RetrainingCandidate,
    RetrainingCandidatesResponse (dates as string; nullable → `| null`)
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task 11 — CREATE frontend/src/lib/ops-utils.ts + ops-utils.test.ts:
  - IMPLEMENT pure functions (pseudocode above)
  - MIRROR: frontend/src/lib/knowledge-utils.ts + knowledge-utils.test.ts
  - VALIDATE: cd frontend && pnpm test --run src/lib/ops-utils.test.ts

Task 12 — CREATE frontend/src/hooks/use-ops.ts + UPDATE hooks/index.ts:
  - useOpsSummary(enabled=true): queryKey ['ops','summary'], api<OpsSummaryResponse>('/ops/summary'),
    refetchInterval: 15000   (operational state — poll. Global query-client already
    sets refetchOnWindowFocus:false, so this won't double-fire on tab focus.)
  - useRetrainingCandidates(limit=20, enabled=true): queryKey ['ops','retraining',limit],
    api<RetrainingCandidatesResponse>('/ops/retraining-candidates', {params:{limit}})
    — NO refetchInterval: the queue moves slowly (changes only on a new run);
    refetch-on-mount + manual invalidation is sufficient. Avoids needless load.
  - DO NOT add useProviderHealth — it already exists in use-config.ts; reuse that.
  - index.ts: add `export * from './use-ops'`
  - MIRROR: frontend/src/hooks/use-runs.ts, use-jobs.ts
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task 13 — UPDATE frontend/src/lib/constants.ts:
  - ADD `OPS: '/ops'` to ROUTES (after SHOWCASE)
  - ADD `{ label: 'Control Center', href: ROUTES.OPS }` to NAV_ITEMS (after Showcase)
  - PRESERVE the `as const` literal types
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task 14 — UPDATE frontend/src/App.tsx:
  - ADD `const OpsPage = lazy(() => import('@/pages/ops'))`
  - ADD `<Route path={ROUTES.OPS} element={<Suspense fallback={<PageLoader />}><OpsPage /></Suspense>} />`
    inside the <Route element={<AppShell />}> block
  - VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 15 — CREATE frontend/src/pages/ops.tsx:
  - export default function OpsPage()
  - hooks: useOpsSummary(), useRetrainingCandidates(), useProviderHealth() [from use-config]
  - early returns: ErrorDisplay(onRetry) → LoadingState → EmptyState (zero jobs AND runs)
  - sections: System Health card, KPI row (KPICard ×4), Data Freshness card,
    Needs Attention table (Link to attentionItemLink(item)), Retraining Queue table
  - reuse getStatusVariant from @/lib/status-utils for job/run status badges
  - MIRROR: frontend/src/pages/visualize/demand.tsx
  - GOTCHA: renders inside AppShell — no nav/container; no raw colors
  - VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 16 — FULL validation sweep (all gates — see Validation Loop)

Task 17 — Browser dogfood per .claude/rules/ui-design.md (webapp-testing / agent-browser)
```

### Integration Points

```yaml
DATABASE:
  - migration: NONE — read-only slice, no schema change.
  - tables read (existing): job, model_run, deployment_alias, sales_daily.

ROUTES (backend):
  - add to: app/main.py
  - import: from app.features.ops.routes import router as ops_router
  - wire:   app.include_router(ops_router)

ROUTES (frontend):
  - add to: frontend/src/lib/constants.ts  → ROUTES.OPS = '/ops' ; NAV_ITEMS entry
  - add to: frontend/src/App.tsx           → lazy import + <Route path={ROUTES.OPS}>

HOOKS:
  - new:   frontend/src/hooks/use-ops.ts
  - update: frontend/src/hooks/index.ts → export * from './use-ops'
  - reuse: useProviderHealth from frontend/src/hooks/use-config.ts (do NOT duplicate)

CONFIG: none — no new settings, no new env var.
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . --fix
uv run ruff format --check .
cd frontend && pnpm lint
# Expected: no errors. Common trap: date.today() → ruff DTZ — use datetime.now(UTC).date().
```

### Level 2: Type Checks

```bash
uv run mypy app/ && uv run pyright app/      # both --strict
cd frontend && pnpm tsc --noEmit
# Expected: no errors.
```

### Level 3: Unit Tests

```bash
uv run pytest -v -m "not integration" app/features/ops/
cd frontend && pnpm test --run src/lib/ops-utils.test.ts
```

Backend unit cases (`test_service.py`, pure — no DB, no mocks):
```python
def test_score_zero_when_fresh_and_no_error():
    assert score_retraining_candidate(0, None) == 0.0

def test_score_max_when_fully_stale_and_max_error():
    assert score_retraining_candidate(90, 100.0) == 1.0

def test_score_clamps_negative_staleness_and_high_wape():
    assert score_retraining_candidate(-5, 250.0) == 0.4   # staleness→0, error→1.0, *0.4

def test_extract_wape_prefers_wape_then_wape_mean():
    assert extract_wape({"wape": 12.0}) == 12.0
    assert extract_wape({"wape_mean": 8.5}) == 8.5
    assert extract_wape(None) is None
    assert extract_wape({}) is None
    assert extract_wape({"wape": "bad"}) is None
    assert extract_wape({"wape": True}) is None          # bool is not a metric
```

### Level 4: Integration Tests

```bash
docker compose up -d
uv run alembic upgrade head
uv run pytest -v -m integration app/features/ops/
```

`test_routes_integration.py` (`@pytest.mark.integration` + `@pytest.mark.asyncio`):
- `/ops/summary` → 200; `system.database_connected is True`; job & run `counts` cover
  every status key; seeded failed job appears in `attention_items`; `freshness.latest_sales_date` set.
- `/ops/summary` with no fixtures → 200 (never 500); all counts `>= 0`; `attention_items` is a list.
- `/ops/retraining-candidates` → 200; `candidates` sorted by `priority_score` desc; `len <= limit`.
- `/ops/retraining-candidates?limit=0` → 422.
- `/ops/retraining-candidates?limit=200` → 422.

### Level 5: Manual Validation

```bash
uv run uvicorn app.main:app --reload --port 8123 &
curl -s http://localhost:8123/ops/summary | head -c 400
curl -s "http://localhost:8123/ops/retraining-candidates?limit=5" | head -c 400
curl -s -o /dev/null -w '%{http_code}\n' "http://localhost:8123/ops/retraining-candidates?limit=0"  # 422
# Frontend: seed first (make demo), then open http://localhost:5173/ops via
# the webapp-testing skill / agent-browser — verify all 5 sections, nav item,
# attention-item links route to Explorer detail pages, retraining table sorted,
# empty-state on a fresh DB. Type-check passing ≠ UI works.
```

---

## Final Validation Checklist

- [ ] `uv run ruff check . && uv run ruff format --check .` — clean
- [ ] `uv run mypy app/ && uv run pyright app/` — clean (`--strict`)
- [ ] `uv run pytest -v -m "not integration"` — green
- [ ] `docker compose up -d && uv run pytest -v -m integration` — green
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` — green
- [ ] `GET /ops/summary` and `GET /ops/retraining-candidates` behave per Success Criteria
- [ ] `/ops` page renders all 5 sections in a real browser; nav item present; links work
- [ ] No new dependency, no new table, no migration
- [ ] Backend cross-slice imports are ORM-models-only; PR description flags the tension
- [ ] Commits use `feat(api)` / `feat(ui)` scopes (no `ops` scope exists) and reference an open issue

---

## Anti-Patterns to Avoid

- ❌ Don't import a sibling slice's `service.py` or `schemas.py` — ORM models only.
- ❌ Don't fetch full lists and count in Python — use `func.count()` + `GROUP BY`.
- ❌ Don't use `date.today()` / naive `datetime.now()` — ruff DTZ; use `datetime.now(UTC)`.
- ❌ Don't add `ConfigDict(strict=True)` to response models.
- ❌ Don't duplicate `useProviderHealth` — reuse the one in `use-config.ts`.
- ❌ Don't re-implement a status→badge mapper — reuse `getStatusVariant` from `status-utils.ts`.
- ❌ Don't create `app/features/ops/models.py` or an Alembic migration.
- ❌ Don't let scoring raise on `None`/missing `metrics` — degrade to staleness-only.
- ❌ Don't claim the UI works on a green type-check — dogfood it in a browser.
- ❌ Don't catch-all silently except for the deliberate DB-connectivity probe.

---

## Workflow Notes

- Open a GitHub issue first (`gh issue list` / `gh issue create`); branch
  `feat/ops-control-center` off `dev` (`.claude/rules/branch-naming.md`); every commit
  references the issue and uses `feat(api)` / `feat(ui)` / `feat(api,ai)` scopes; PR into `dev`.
- The cross-slice ORM import (`jobs`, `registry`) is a deliberate, accepted tension with the
  vertical-slice rule — **state it explicitly in the PR description** per
  `.claude/rules/product-vision.md`.

## Confidence Score

**9 / 10** for one-pass implementation success.

Rationale: the `analytics` slice is a near-exact backend template; every data source, ORM
column, enum, and frontend pattern is verified against the live codebase; all three open
items the plan flagged (`SalesDaily`, `useProviderHealth`, `getStatusVariant`) are resolved
inline. The external-research pass (§ External Research Findings) validated the retraining
heuristic (hybrid time+performance trigger, WAPE error signal) and the alias-staleness
design against MLOps/MLflow guidance, and caught one latent bug — the `AsyncSession`
lazy-load trap on `DeploymentAlias.run` — now fixed with an explicit CRITICAL gotcha.
Residual risk: (1) integration-test fixture FK ordering for `DeploymentAlias`→`ModelRun`;
(2) `model_run.metrics` shape variability — both mitigated by defensive `extract_wape` and
structural (not exact-total) test assertions; (3) minor SQLAlchemy `DISTINCT ON` / typing
friction under `--strict`, mitigated by the explicit gotcha and `created_at`-ordering
guidance.
