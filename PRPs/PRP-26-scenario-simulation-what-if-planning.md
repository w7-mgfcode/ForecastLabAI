name: "PRP-26 — Scenario Simulation / What-If Planning (MVP)"
description: |
  Context-rich PRP that promotes the **MVP scope** of
  `docs/optional-features/03-scenario-simulation-what-if-planning.md` into code: a
  new `app/features/scenarios/` vertical slice that turns ForecastLabAI from
  "predict the future" into "plan possible futures". It runs a baseline forecast
  from an existing trained model, applies **deterministic, transparent uplift /
  drag factors** for future assumptions (price change, promotion, holiday,
  inventory, lifecycle), and returns a baseline-vs-scenario comparison. Scenarios
  can be saved as named JSON plans. A new `Visualize → What-If Planner` page drives
  the slice. Phased so each phase is independently shippable and one-pass
  implementable.

## Purpose

ForecastLabAI can train, predict, backtest, register and visualise demand — but
every forecast answers exactly one question: *"what happens if nothing changes?"*
There is **no surface that answers "what if we discount this SKU 15% next week?"**
This PRP delivers the **MVP** of the Scenario Simulation feature brief:

- **Phase A — Stateless Simulation Engine (backend)**: a pure deterministic
  adjustment engine (`adjustments.py`) and a stateless `POST /scenarios/simulate`
  endpoint that resolves a baseline model, runs a baseline forecast, applies
  per-day adjustment factors, and returns a `ScenarioComparison`. No table yet.
- **Phase B — Saved Scenario Plans (persistence)**: a new `scenario_plan` table +
  Alembic migration, and `POST /scenarios` / `GET /scenarios` /
  `GET /scenarios/{id}` / `DELETE /scenarios/{id}` CRUD over saved plans.
- **Phase C — What-If Planner Page (frontend)**: a `/visualize/planner` page —
  baseline picker → assumption form → run → baseline-vs-scenario chart + delta
  table → save / reload / delete named plans.

The **"Full Version"** (a future-feature-frame generator, exogenous-regressor
model support, agent-generated scenarios, multi-scenario comparison) is explicitly
**out of scope** — see DECISIONS LOCKED #1.

> Source plan: `.agents/plans/scenario-simulation-what-if-planning.md` (validated
> against the repo as of 2026-05-19). Feature brief:
> `docs/optional-features/03-scenario-simulation-what-if-planning.md`.

---

## DEPENDS ON — read before starting

This PRP has **no new dependency** on an unmerged PRP. It builds on already-merged
slices: `forecasting` (PRP-5), `registry` (PRP-7), `jobs` (PRP-8),
`data_platform` (PRP-2), and the frontend dashboard (PRP-11). Sanity-check before
starting: if `app/features/forecasting/service.py` does not define
`ForecastingService.predict` and `app/features/forecasting/persistence.py` does
not expose `load_model_bundle`, stop — a dependency moved and the artifact-resolution
plan needs revisiting.

---

## Goal

**Feature Goal**: Ship the MVP of Scenario Simulation as a new
`app/features/scenarios/` vertical slice — the first slice since `rag` to ship
both a persisted table **and** a non-trivial compute path — plus a `Visualize →
What-If Planner` page, delivered as three independently-shippable phases.

**Deliverable**:
- **Backend** — a new `scenarios` slice (`models.py`, `schemas.py`,
  `adjustments.py`, `service.py`, `routes.py`, `tests/`), one Alembic migration
  creating `scenario_plan`, and five endpoints (`POST /scenarios/simulate`,
  `POST /scenarios`, `GET /scenarios`, `GET /scenarios/{scenario_id}`,
  `DELETE /scenarios/{scenario_id}`).
- **Frontend** — a `/visualize/planner` page, `use-scenarios.ts` hooks, a pure
  `scenario-utils.ts` module (+ vitest), new `Scenario*` TS types, a route + nav
  entry.

**Success Definition**: `docker compose up` → seed → `make demo` (so completed
`predict` jobs + trained models exist) → open `/visualize/planner` → a planner
picks a baseline `predict` job, defines assumptions (e.g. −15% price + a `pct_off`
promotion), runs a simulation, sees a baseline-vs-scenario chart + delta table +
a visible **heuristic disclaimer**, exports the delta CSV, and saves / reloads /
deletes a named plan — with every gate (`ruff`, `mypy --strict`,
`pyright --strict`, `pytest` unit + integration, frontend `tsc`/`lint`/`test`)
green.

## Why

- **User value** — business users can quantify the demand + revenue impact of a
  decision (a discount, a promotion, a holiday) *before* committing to it, and
  save the analysis as a reusable plan. Inventory users get a coverage / stockout
  verdict under demand spikes.
- **Demo value** — a demo reviewer currently sees a *forecasting* system; this
  feature makes it a *planning* system — a recognisably high-value retail
  workflow.
- **Integration** — the data platform already models the relevant drivers (price
  history, promotions, inventory snapshots, calendar/holiday flags) and Phase-2
  feature engineering already supports promotion / lifecycle / exogenous features;
  none of that was reachable as a planning workflow. This slice surfaces it.

## What

### User-visible behavior

A new `Visualize → What-If Planner` page (`/visualize/planner`) lets a planner:

1. **Pick a baseline** — choose a completed `predict` job (its `run_id` is the
   baseline model artifact key) and a horizon (7 / 14 / 30 / 60 / 90 days).
2. **Define assumptions** — all optional: a price `change_pct` over a date window,
   a promotion `kind` + window, holiday/event dates, an inventory `on_hand_units`
   cap, a lifecycle `stage` override.
3. **Run the simulation** — `POST /scenarios/simulate` returns a baseline series,
   a scenario series, per-day + aggregate deltas, a revenue delta, and a coverage
   verdict.
4. **Review** — a baseline-vs-scenario two-series chart, KPI tiles
   (units/revenue delta, coverage verdict), a per-day delta table with CSV export,
   and a **prominent heuristic-disclaimer banner**.
5. **Save / reload / delete** — persist the scenario as a named plan (inputs +
   the comparison snapshot), list saved plans, reload one, delete one.

### Technical requirements

- Phase A: a new `scenarios` slice — pure `adjustments.py`, Pydantic v2 request +
  response models, `ScenarioService.simulate`, an `APIRouter`, RFC 7807 errors,
  `mypy --strict` + `pyright --strict` clean. **Stateless** — no table.
- Phase B: a `scenario_plan` ORM model (JSONB inputs + JSONB comparison snapshot),
  an Alembic migration (upgrade **and** downgrade), CRUD service methods + routes.
- Phase C: **frontend only** — a pure `scenario-utils.ts` (+ vitest), TanStack
  Query hooks, the planner page, routing + nav wiring. No backend changes.
- No new external dependency, no managed-cloud SDK, no WebSocket. Reuses FastAPI,
  SQLAlchemy 2.0 async, Pydantic v2, numpy, structlog, Recharts, TanStack Query —
  all already present.

### Success Criteria

- [ ] `POST /scenarios/simulate` returns a `ScenarioComparison` with `points`
      length == `horizon`, baseline + scenario series, per-day + aggregate deltas,
      a revenue delta, a `coverage_verdict`, and `method == "heuristic"` plus a
      non-empty `disclaimer`.
- [ ] An empty `ScenarioAssumptions` yields scenario == baseline, all deltas 0.0.
- [ ] A bogus `run_id` → RFC 7807 problem response (404/400), never a 500.
- [ ] `adjustments.py` helpers are pure, never raise on junk input, and are
      unit-tested directly.
- [ ] `test_leakage.py` proves the scenario adjustment touches only horizon
      (future) points and never mutates / reads the historical series — treated as
      a load-bearing spec (never weakened to make a feature pass).
- [ ] `POST /scenarios` persists a plan; `GET /scenarios` lists; `GET
      /scenarios/{id}` returns the embedded comparison snapshot; `DELETE` removes
      it; `GET /scenarios` on an empty table → 200 + empty list (never 404).
- [ ] The Alembic migration creates `scenario_plan` and upgrades **and**
      downgrades cleanly on a fresh DB.
- [ ] `Visualize → What-If Planner` lets a user pick a baseline `predict` job,
      define assumptions, run a simulation, see a baseline-vs-scenario chart +
      delta table + a visible heuristic disclaimer, export the delta CSV, and
      save / reload / delete a named plan.
- [ ] All gates pass: `ruff`, `mypy --strict`, `pyright --strict`, `pytest`
      (unit + integration), frontend `tsc` + `lint` + `test`.
- [ ] No new external dependency; no managed-cloud SDK; no WebSocket; the slice
      respects the no-cross-slice-service-import rule (DECISIONS LOCKED #2).
- [ ] README + `docs/_base/{API_CONTRACTS,REPO_MAP_INDEX,DOMAIN_MODEL}.md` updated.

---

## All Needed Context

### DECISIONS LOCKED (resolved during planning — do NOT re-litigate)

1. **MVP scope only — the heuristic adjustment is a post-forecast multiplier.**
   The baseline models (`naive`, `seasonal_naive`, `moving_average`) forecast from
   the historical target series only and **ignore the exogenous `X` argument**
   (verified: `# noqa: ARG002` on every `fit`/`predict` in
   `forecasting/models.py`). The MVP therefore applies assumptions as a
   **deterministic post-forecast multiplier** on the baseline forecast — never a
   leakage-prone re-training. Every result is explicitly labelled
   `method = "heuristic"` with a fixed `disclaimer` string. The "Full Version"
   (future-feature-frame generator, exogenous-regressor model support,
   agent-generated scenarios, multi-scenario comparison) is **out of scope** — it
   needs models that consume future feature frames, which the MVP does not add.

2. **The scenario service does NOT import a sibling slice's `service.py`.**
   `AGENTS.md` § Architecture: "a slice may NOT import from another slice;
   cross-cutting code goes through `app/core/` or `app/shared/`." The sanctioned
   narrow exception (used by `ops`) is importing a sibling's **ORM `models.py`**
   read-only — NOT its `service.py`. Calling `ForecastingService` from `scenarios`
   would be a genuine cross-slice *service* import and **violates the rule**.
   RESOLUTION: the scenario service imports only the **stable, lower-level
   building blocks** — `load_model_bundle` from `forecasting/persistence.py` — and
   produces the baseline forecast by calling `bundle.model.predict(horizon)`
   directly (the `BaseForecaster` interface), replicating the ~30-line
   `ForecastPoint`-construction block from `ForecastingService.predict`
   (`forecasting/service.py`, the predict body). Read-only ORM imports of sibling
   `models.py` (`data_platform`, `registry`) are allowed. Alternative considered +
   rejected: promoting the predict logic to `app/shared/` — larger blast radius,
   deferred to the Full Version. **This decision MUST be cited in the PR
   description** per `product-vision.md` § "When Ideas Don't Align".

3. **`scenario_plan` stores the comparison SNAPSHOT, not just the inputs.** A
   saved plan persists both the raw `ScenarioAssumptions` **and** the full
   `ScenarioComparison` as JSONB, so a reloaded plan re-renders without
   recomputation (and without needing the original model artifact to still exist).
   Persist via `model_dump(mode="json")` so `date`/`datetime` serialise to strings
   (JSONB rejects Python `date`).

4. **There is no `scenarios` commit scope.** The `.claude/rules/commit-format.md`
   allow-list has **no `scenarios` scope**. Use `feat(api)` for the backend slice,
   `feat(api,db)` for the slice + migration, `feat(ui)` for the frontend,
   `test(api)` for backend tests, `docs(docs)` for docs. Do **not** invent a
   scope.

5. **The current Alembic head is `378c112e4b32`, NOT `d6e0f2g3h456`.** The source
   plan guessed `d6e0f2g3h456`; the verified head (via `uv run alembic heads`) is
   `378c112e4b32_create_app_config_table.py`. Set the new migration's
   `down_revision = "378c112e4b32"` — but **re-verify with `uv run alembic heads`
   immediately before writing the migration** (a PRP merging first would move it).

6. **No WebSocket.** Simulation is request/response — `POST /scenarios/simulate`
   computes synchronously and returns. No streaming surface — consistent with
   `product-vision.md` "not a real-time streaming system".

### Documentation & References

```yaml
# ── MUST READ — repo files (read BEFORE implementing) ──

- file: PRPs/PRP-25-forecastops-control-center-full.md
  why: The most recent, highest-quality PRP. Mirror its DECISIONS LOCKED section,
       its Known Gotchas table, its phased task list, its Anti-Patterns, and its
       Confidence Score rationale.

- file: PRPs/PRP-22-visualize-demand-planner.md
  why: The immediate sibling — it added a new Visualize page (demand.tsx), a new
       hook, a new pure util module, new TS types, a route + nav entry. The EXACT
       frontend shape this feature reuses. Its Resolved Decisions + Known Gotchas
       apply.

- file: PRPs/PRP-9-rag-knowledge-base.md
  why: The precedent for a slice that ships a new table + Alembic migration +
       service compute path. Read its migration + model + service layering.

- file: app/features/forecasting/service.py
  why: ForecastingService.predict() is the baseline-forecast engine — loads a
       .joblib bundle, validates store/product, calls bundle.model.predict(horizon),
       builds ForecastPoints. The scenario service REPLICATES the ~30-line predict
       body (per DECISIONS LOCKED #2) rather than importing this class.
  critical: Path-traversal validation in predict() is load-bearing — mirror it.

- file: app/features/forecasting/persistence.py
  why: load_model_bundle — the SANCTIONED lower-level building block the scenario
       service imports (NOT ForecastingService). Read what the bundle carries
       (model, metadata with store_id/product_id/train_end_date).

- file: app/features/forecasting/schemas.py
  why: ForecastPoint (date, forecast, lower_bound?, upper_bound?) + PredictResponse
       — the baseline series shape. TrainRequest is the request-body strict-mode
       pattern (ConfigDict(strict=True) + Field(strict=False) on date fields).

- file: app/features/forecasting/models.py
  why: Confirms the baseline forecasters IGNORE the exogenous X argument
       (# noqa: ARG002) — the reason the MVP is a post-forecast multiplier.

- file: app/features/jobs/service.py
  why: _execute_predict shows how a run_id resolves to a model artifact —
       {artifacts_dir}/model_{run_id}.joblib, then load_model_bundle to read
       store_id/product_id from bundle.metadata. The scenario service resolves the
       baseline artifact the SAME way.
  critical: A predict/train job's run_id is the ARTIFACT KEY (model_{run_id}.joblib),
            NOT a registry model_run.run_id — see Known Gotchas.

- file: app/features/jobs/schemas.py
  why: JobCreate / JobResponse — the scenario page picks a completed predict job
       whose result carries run_id, store_id, product_id, forecasts.

- file: app/features/jobs/models.py
  why: Job — JSONB columns for params/result, CheckConstraint, Index,
       TimestampMixin. The scenario_plan table mirrors this.

- file: app/features/registry/models.py
  why: ModelRun (JSONB model_config/metrics; data_window_end; store_id/product_id;
       run_id 32-char string; RunStatus). Read-only context lookup only.

- file: app/features/data_platform/models.py
  why: SalesDaily (store_id, product_id, date, quantity, unit_price) — used to
       estimate a baseline unit price for the revenue-delta calc. PriceHistory /
       Promotion (kind in {pct_off,bogo,bundle,markdown}, discount_pct) document
       the real driver semantics the heuristic factors approximate.

- file: app/features/ops/service.py
  why: The pure module-scope helper pattern (extract_wape, score_retraining_candidate)
       — exactly how adjustments.py helpers should be written (pure, never raise,
       unit-tested directly). OpsService class shape mirrors ScenarioService.

- file: app/features/ops/schemas.py
  why: Response-model conventions — ConfigDict(from_attributes=True), every field
       a Field(..., description=), counts ge=0, NO strict=True on response models.

- file: app/features/ops/routes.py
  why: APIRouter(prefix=, tags=), Query(default=, ge=, le=, description=),
       Depends(get_db), rich docstrings.

- file: app/features/rag/models.py
  why: DocumentSource — the model-with-JSONB + TimestampMixin + String(32)
       external-id + GIN-index pattern for the new scenario_plan table.

- file: alembic/versions/37e16ecef223_create_jobs_table.py
  why: The EXACT migration shape for a new JSONB-bearing table — op.create_table,
       postgresql.JSONB(astext_type=sa.Text()), GIN index, CheckConstraint,
       server_default=sa.text('now()') on timestamps, a real downgrade().

- file: app/features/ops/tests/conftest.py
  why: Real-Postgres integration fixtures — ASGITransport client, FK-safe scoped
       cleanup, TEST-/test- marker on every seeded natural key. The scenario
       conftest MUST add delete(ScenarioPlan) to its cleanup.

- file: app/features/ops/tests/test_service.py
  why: The pattern for unit-testing pure helpers — adjustments.py gets the same.

- file: app/features/ops/tests/test_routes_integration.py
  why: The @pytest.mark.integration route-test pattern (happy + empty-DB + 422).

- file: app/features/forecasting/tests/test_service.py
  why: How ForecastingService is tested with a real model bundle on disk — needed
       for the /scenarios/simulate integration test (it needs a trained model).

- file: app/features/featuresets/tests/test_leakage.py
  why: The leakage-spec precedent — a test that IS the spec, never weakened to
       make a feature pass. The scenario test_leakage.py follows this philosophy.

- file: app/core/problem_details.py
  why: RFC 7807 application/problem+json envelope. The route layer maps
       FileNotFoundError/ValueError from the service to structured problems.

- file: frontend/src/pages/visualize/demand.tsx
  why: The closest page — header, loading/error/empty early returns, Card/Table
       sections, Select controls, useMemo derivations, a drill-in Card, CSV
       export, formatNumber, @/ imports, keyboard-operable rows. The planner page
       mirrors its skeleton.

- file: frontend/src/pages/visualize/forecast.tsx
  why: The in-page job-launch pattern — useCreateJob().mutateAsync(...), JobPicker,
       a horizon Select, runError state, getErrorMessage. The planner reuses this
       to pick a baseline predict job.

- file: frontend/src/hooks/use-jobs.ts
  why: useCreateJob (a useMutation) is the pattern for useSimulateScenario /
       useCreateScenario / useDeleteScenario; useJobs({jobType:'predict',
       status:'completed'}) lists baseline-candidate jobs.

- file: frontend/src/hooks/use-ops.ts
  why: The query-hook pattern (useQuery, queryKey array, api<T>(path, {params})).
       Mirror for useScenario / useScenarios.

- file: frontend/src/lib/demand-utils.ts
  why: The pure-util module pattern — typed, no React, no I/O, @/types/api
       imports, fully unit-tested. scenario-utils.ts follows this exactly.

- file: frontend/src/lib/csv-export.ts
  why: toCsv/downloadCsv/CsvColumn<T> — reuse for the delta-table export.
       CSV-injection-safe; do NOT re-implement.

- file: frontend/src/components/charts/time-series-chart.tsx
  why: The Recharts wrapper — data, actualKey/predictedKey, showActual/showPredicted,
       optional lowerKey/upperKey/showInterval band. The baseline-vs-scenario chart
       renders TWO series here (baseline as actualKey, scenario as predictedKey).
  critical: Verify the exact prop names in the file before wiring.

- file: frontend/src/components/common/job-picker.tsx
  why: JobPicker — reused verbatim to pick a baseline predict job. Also reuse
       ErrorDisplay/EmptyState, LoadingState, StatusBadge from components/common/.

- file: frontend/src/lib/constants.ts
  why: ROUTES.VISUALIZE (FORECAST/BACKTEST/DEMAND) + the Visualize NAV_ITEMS
       submenu — add PLANNER here.

- file: frontend/src/App.tsx
  why: The lazy(() => import()) block + the ROUTES.VISUALIZE.* <Route> block —
       add the planner identically (copy the DEMAND route).

- file: frontend/src/types/api.ts
  why: Job, JobCreate, ForecastPoint, Product already defined — add Scenario*
       interfaces here, mirroring the Ops* / InventoryStatus* additions.

# ── Rules — read before writing any code ──

- file: .claude/rules/product-vision.md
  why: Principle 5 (time-safety), principle 8 (single-host), the "not a streaming
       system" guardrail. Answer all 6 Litmus-Test questions in the PR description.

- file: .claude/rules/security-patterns.md
  why: Pydantic v2 at every boundary, SQLAlchemy parameter binding,
       pathlib.Path.resolve() for the model-artifact path, the strict-mode
       request-body policy.

- file: .claude/rules/test-requirements.md
  why: New module -> test file; new endpoint -> route test (2xx + 1 error path);
       new model -> constraint test; new migration -> upgrade/downgrade clean.

- file: .claude/rules/commit-format.md
  why: type(scope): description (#issue). GOTCHA: no `scenarios` scope — see
       DECISIONS LOCKED #4.

- file: .claude/rules/branch-naming.md
  why: branch feat/scenario-what-if-planner off dev.

- file: .claude/rules/ui-design.md
- file: .claude/rules/shadcn-ui.md
  why: Build the page via frontend-design + shadcn-ui skills; dogfood in a real
       browser via webapp-testing / agent-browser. A green tsc is NOT proof the
       UI works.

# ── External documentation ──

- url: https://fastapi.tiangolo.com/tutorial/body/
  why: The new slice's request-body endpoints follow this.

- url: https://fastapi.tiangolo.com/tutorial/bigger-applications/#apirouter
  why: Confirms APIRouter(prefix=...) + include_router registration.

- url: https://docs.pydantic.dev/latest/concepts/strict_mode/
  why: Request bodies use ConfigDict(strict=True) + per-field Field(strict=False)
       on JSON-non-native types (date); response models do NOT. This is the repo's
       docs/_base/SECURITY.md policy — get it right or every HTTP caller 422s on
       date fields.

- url: https://docs.pydantic.dev/latest/concepts/models/
  why: model_dump(mode="json") for JSONB persistence of date/datetime fields.

- url: https://recharts.org/en-US/api/LineChart
  why: The baseline-vs-scenario two-series chart; TimeSeriesChart already wraps
       Recharts — pass two series, do not hand-roll a chart.

- url: https://tanstack.com/query/latest/docs/framework/react/guides/mutations
  why: useSimulateScenario/useCreateScenario/useDeleteScenario are mutations;
       useScenarios/useScenario are queries. Mirror use-jobs.ts.

- url: https://www.nist.gov/itl/ai-risk-management-framework
  why: The "Risks" section of the brief — over-trust of heuristic numbers. Drives
       the MANDATORY method: "heuristic" label + a disclaimer string on every
       ScenarioComparison (a transparency / explainability control).
```

> Note: LightGBM / XGBoost / Prophet / scikit-learn `TimeSeriesSplit` (cited in
> the feature brief) are **context for the Full Version only**. The MVP does NOT
> add an exogenous-regressor model — do not pull these in for MVP implementation.

### Current Codebase tree (relevant slices)

```bash
app/
├── main.py                          # router wiring — add scenarios_router
├── core/
│   ├── config.py                    # get_settings() — forecast_model_artifacts_dir (str)
│   ├── database.py                  # get_db dependency
│   └── problem_details.py           # RFC 7807 envelope
└── features/
    ├── data_platform/models.py      # SalesDaily, PriceHistory, Promotion, Calendar
    ├── forecasting/
    │   ├── persistence.py           # load_model_bundle  <- IMPORT THIS
    │   ├── service.py               # ForecastingService.predict  <- replicate body
    │   ├── models.py                # baseline forecasters (ignore exogenous X)
    │   └── schemas.py               # ForecastPoint, PredictResponse, TrainRequest
    ├── jobs/                        # Job model, _execute_predict (artifact resolution)
    ├── registry/models.py           # ModelRun
    └── ops/                         # the pattern-mirror slice (pure helpers, schemas)
alembic/versions/
└── 378c112e4b32_create_app_config_table.py   # <- current head (VERIFY)
frontend/src/
├── pages/visualize/{demand,forecast,backtest}.tsx
├── hooks/{use-jobs,use-ops}.ts
├── lib/{demand-utils,csv-export,constants}.ts
├── components/charts/time-series-chart.tsx
├── components/common/{job-picker,error-display,loading-state,status-badge}.tsx
├── types/api.ts
└── App.tsx
```

### Desired Codebase tree — files to ADD

```bash
# ── Backend: the new `scenarios` vertical slice ──
app/features/scenarios/__init__.py            # slice package + __all__
app/features/scenarios/models.py              # ScenarioPlan ORM model (JSONB)
app/features/scenarios/schemas.py             # request + response Pydantic models
app/features/scenarios/adjustments.py         # PURE deterministic factor math
app/features/scenarios/service.py             # ScenarioService (simulate + CRUD)
app/features/scenarios/routes.py              # APIRouter — 5 endpoints
app/features/scenarios/tests/__init__.py
app/features/scenarios/tests/conftest.py      # real-Postgres fixtures + cleanup
app/features/scenarios/tests/test_adjustments.py        # PURE-function unit tests
app/features/scenarios/tests/test_schemas.py            # schema unit tests
app/features/scenarios/tests/test_leakage.py            # leakage spec (load-bearing)
app/features/scenarios/tests/test_routes_integration.py # @pytest.mark.integration

# ── Backend: migration ──
alembic/versions/<rev>_create_scenario_plan_table.py    # new table

# ── Frontend ──
frontend/src/hooks/use-scenarios.ts           # query + mutation hooks
frontend/src/lib/scenario-utils.ts            # PURE chart-merge + delta utils
frontend/src/lib/scenario-utils.test.ts       # vitest
frontend/src/pages/visualize/planner.tsx      # the /visualize/planner What-If page
```

### Files to MODIFY (all additive)

```bash
app/main.py                       # +1 import, +1 include_router(scenarios_router)
frontend/src/types/api.ts         # +Scenario* interfaces
frontend/src/lib/constants.ts     # +ROUTES.VISUALIZE.PLANNER + nav entry
frontend/src/App.tsx              # +1 lazy import + 1 <Route>
README.md                         # feature-list mention
docs/_base/API_CONTRACTS.md       # +/scenarios/* rows
docs/_base/REPO_MAP_INDEX.md      # +scenarios slice + planner.tsx rows
docs/_base/DOMAIN_MODEL.md        # +scenario_plan aggregate + ubiquitous-language rows
```

### Known Gotchas of our codebase & Library Quirks

| # | Gotcha | Mitigation |
|---|--------|-----------|
| 1 | A predict/train job's `run_id` is the **artifact key** (`model_{run_id}.joblib`), NOT a registry `model_run.run_id`. Passing the wrong one yields a missing artifact. | Resolve the artifact exactly as `jobs/service.py:_execute_predict` does. The page picks a *completed predict job* whose `result.run_id` is the artifact key. A bogus `run_id` must surface as a 404/400 problem, never a 500. |
| 2 | A slice may **NOT** import another slice's `service.py`. Importing `ForecastingService` from `scenarios` violates `AGENTS.md` § Architecture. | Import only `load_model_bundle` from `forecasting/persistence.py`; produce the baseline by calling `bundle.model.predict(horizon)` and replicating the ~30-line `ForecastPoint`-construction block. Cite in the PR (DECISIONS LOCKED #2). |
| 3 | FastAPI calls `TypeAdapter.validate_python` on request bodies. With `ConfigDict(strict=True)`, Pydantic refuses to coerce ISO-string dates → every HTTP caller 422s on `date` fields. | Request bodies: `ConfigDict(strict=True)` + `Field(strict=False, ...)` on **every** `date`/`datetime` field. Response models: `from_attributes=True`, **NO** `strict=True`. (`docs/_base/SECURITY.md`.) |
| 4 | JSONB rejects Python `date`/`datetime` objects. | Persist `assumptions` / `comparison` via `model_dump(mode="json")` so dates serialise to ISO strings. |
| 5 | SQLAlchemy reserves the attribute name `metadata` on declarative models (`rag` works around it with `metadata_`/`"metadata"`). | Name the `scenario_plan` JSONB columns `assumptions` and `comparison` — never `metadata`. |
| 6 | The current Alembic head is **`378c112e4b32`**, not the `d6e0f2g3h456` the source plan guessed. | Set `down_revision = "378c112e4b32"`, but re-verify with `uv run alembic heads` immediately before writing the migration. Migrations are forward-only after merge. |
| 7 | There is **no `scenarios` commit scope** in the allow-list. | Use `feat(api)` / `feat(api,db)` / `feat(ui)` / `test(api)` / `docs(docs)` (DECISIONS LOCKED #4). |
| 8 | The baseline forecasters ignore exogenous regressors — a "what-if" cannot be done by re-prediction. | The MVP applies a **post-forecast deterministic multiplier**; label every result `method = "heuristic"` + a `disclaimer`. |
| 9 | A green `pnpm tsc` is NOT proof the UI works. | Dogfood the running page in a real browser via `webapp-testing` / `agent-browser` (Task C7) — mandatory per `.claude/rules/ui-design.md`. |
| 10 | `units_delta_pct` divide-by-zero when baseline demand is 0. | Guard: return `0.0` when `baseline_total_units == 0`. |
| 11 | An assumption window can fall entirely **before** the forecast start. | The adjustment touches **only** horizon (future) days; out-of-window days contribute factor `1.0`. The leakage test asserts this. |
| 12 | The repo uses **CRLF line endings** on `.py` files (no `.gitattributes`); scripted text-mode writes can silently flip them to LF. | Edit `app/main.py` minimally; preserve existing line endings. |

---

## Implementation Blueprint

### Data models and structure

**Backend — `adjustments.py` (PURE, no DB, no I/O, never raises):**

```python
# Module constants — documented deterministic heuristic factors.
# Final values are a planning DECISION — lock them before coding (see NOTES).
PRICE_ELASTICITY = -1.2          # demand_factor = (1 + change_pct) ** PRICE_ELASTICITY
PROMOTION_UPLIFT_BY_KIND = {"pct_off": 1.25, "bogo": 1.40, "bundle": 1.15, "markdown": 1.30}
HOLIDAY_UPLIFT = 1.30
LIFECYCLE_FACTOR = {"launch": 1.2, "growth": 1.1, "maturity": 1.0, "decline": 0.85}
FACTOR_BAND = (0.1, 5.0)         # clamp band — no negative / explosive forecast

def clamp(value, lo, hi) -> float: ...
def price_factor(price_change_pct: float) -> float: ...           # constant-elasticity
def promotion_factor(kind: str, active: bool) -> float: ...        # 1.0 if not active / unknown kind
def holiday_factor(is_holiday: bool) -> float: ...
def lifecycle_factor(stage: str | None) -> float: ...              # 1.0 for None / unknown
def combined_daily_factor(*, day_index, horizon, assumptions) -> float: ...  # multiply applicable, clamp
def apply_adjustment(baseline: list[float], factors: list[float]) -> list[float]:
    # element-wise multiply; len asserted equal; every output max(0.0, ...)
```

**Backend — `schemas.py` (Pydantic v2):**

```python
# Request models — ConfigDict(strict=True) + Field(strict=False) on every date:
class PriceAssumption:        change_pct: float (ge=-0.9, le=5.0); start_date/end_date: date
class PromotionAssumption:    kind: Literal["pct_off","bogo","bundle","markdown"]; start_date/end_date: date
class HolidayAssumption:      dates: list[date]
class InventoryAssumption:    on_hand_units: int (ge=0)                 # caps coverage, not demand
class LifecycleAssumption:    stage: Literal["launch","growth","maturity","decline"]
class ScenarioAssumptions:    price/promotion/holiday/inventory/lifecycle: ... | None = None
class SimulateScenarioRequest: run_id: str; horizon: int (ge=1, le=90); assumptions; name: str | None
class CreateScenarioRequest:  name: str; run_id: str; horizon: int; assumptions: ScenarioAssumptions

# Response models — ConfigDict(from_attributes=True), NO strict=True, Field(..., description=):
class ScenarioPoint:        date; baseline; scenario; delta; applied_factor: float
class ScenarioComparison:   store_id; product_id; model_type; horizon; points: list[ScenarioPoint];
                            baseline_total_units; scenario_total_units; units_delta; units_delta_pct;
                            baseline_revenue; scenario_revenue; revenue_delta; unit_price_used;
                            coverage_verdict: Literal["covered","at_risk","stockout","unknown"];
                            method: Literal["heuristic"]; disclaimer: str; generated_at: datetime
class ScenarioPlanResponse: scenario_id; name; store_id; product_id; run_id; horizon; method;
                            created_at; comparison: ScenarioComparison; assumptions: ScenarioAssumptions
class ScenarioListItem:     scenario_id; name; store_id; product_id; units_delta; revenue_delta; created_at
class ScenarioListResponse: scenarios: list[ScenarioListItem]; total: int (ge=0)
```

**Backend — `models.py` (`ScenarioPlan(TimestampMixin, Base)`):**

```python
id: int (PK); scenario_id: str String(32) unique index; name: str String(200)
store_id: int (index); product_id: int (index); run_id: str String(32) (index)
horizon: int
assumptions: dict[str, Any]  -> JSONB        # raw ScenarioAssumptions dump
comparison:  dict[str, Any]  -> JSONB        # full ScenarioComparison snapshot
method: str String(20) -> CheckConstraint("method IN ('heuristic')")
__table_args__: GIN index on assumptions + comparison; composite (store_id, product_id)
```

### list of tasks to be completed (dependency-ordered)

The work is **three independently-shippable phases**. Prefer one PR per phase (or
one phased PR). **Phase A must merge before Phase C can be dogfooded** (the page
needs the endpoint).

```yaml
Task 0 — SETUP: tracking issue + branch:
  - Open ONE GitHub issue "Scenario Simulation / What-If Planning (MVP)"; confirm OPEN.
  - git fetch origin && git switch -c feat/scenario-what-if-planner origin/dev
  - GOTCHA: no `scenarios` commit scope — use feat(api)/feat(api,db)/feat(ui)/docs(docs).
  - VALIDATE: gh issue view <N> --json state  -> OPEN

# ════════ PHASE A — Stateless Simulation Engine (backend) ════════

Task A1 — CREATE app/features/scenarios/__init__.py + tests/__init__.py:
  - Docstring + empty __all__ (extend as schemas land); empty tests/__init__.py.
  - PATTERN: app/features/ops/__init__.py
  - VALIDATE: uv run python -c "import app.features.scenarios"

Task A2 — CREATE app/features/scenarios/adjustments.py:
  - The PURE deterministic adjustment engine (see Data models above). stdlib only,
    `from __future__ import annotations`, no numpy. Every helper tolerates junk
    input (negative pct, unknown kind, None stage) and returns a sane factor —
    NEVER raises.
  - PATTERN: app/features/ops/service.py pure module-scope helpers.
  - VALIDATE: uv run python -c "from app.features.scenarios.adjustments import combined_daily_factor; print('ok')"

Task A3 — CREATE app/features/scenarios/schemas.py (Phase A subset):
  - The simulate request models + ScenarioComparison + ScenarioPoint (see above).
  - PATTERN: forecasting/schemas.py:TrainRequest (request, strict); ops/schemas.py
    (response, from_attributes).
  - GOTCHA: strict=True ONLY on request bodies; Field(strict=False) on every date.
  - VALIDATE: uv run python -c "from app.features.scenarios.schemas import SimulateScenarioRequest, ScenarioComparison; print('ok')"

Task A4 — CREATE app/features/scenarios/service.py (Phase A subset):
  - ScenarioService.simulate(db, request) -> ScenarioComparison:
    1. Resolve artifact: artifacts_dir = Path(settings.forecast_model_artifacts_dir);
       model_path = (artifacts_dir / f"model_{run_id}.joblib").resolve()
       (mirror jobs/service.py:_execute_predict — the setting is a str, wrap in Path).
       Then mirror the LOAD-BEARING path-traversal guard from
       forecasting/service.py:218-248 — reject a non-`.joblib` suffix and any path
       that escapes artifacts_dir (`resolved_path.relative_to(artifacts_dir)`) with
       ValueError. FileNotFoundError if the validated path is absent.
    2. load_model_bundle -> read store_id/product_id from bundle.metadata.
    3. Produce the baseline series by calling bundle.model.predict(horizon) and
       replicating the ForecastPoint-construction block from
       ForecastingService.predict (DECISIONS LOCKED #2 — do NOT import the
       sibling service).
    4. Estimate unit_price_used: most-recent non-null SalesDaily.unit_price for
       (store, product); fall back to a documented default + log a warning.
    5. Per horizon day: applied_factor = adjustments.combined_daily_factor(...);
       scenario = max(0.0, baseline * applied_factor).
    6. Aggregate totals, units_delta, units_delta_pct (guard /0), revenue, deltas.
    7. coverage_verdict from the inventory assumption (covered / at_risk / stockout
       / unknown).
    8. Return ScenarioComparison(method="heuristic", disclaimer=<fixed>).
       logger.info("scenarios.simulated", ...).
  - PATTERN: ops/service.py (class shape, logging); jobs/service.py:_execute_predict
    (artifact resolution).
  - VALIDATE: uv run mypy app/features/scenarios/ && uv run pyright app/features/scenarios/

Task A5 — CREATE app/features/scenarios/routes.py (Phase A subset):
  - router = APIRouter(prefix="/scenarios", tags=["scenarios"]);
    POST /scenarios/simulate -> response_model=ScenarioComparison, rich docstring.
    Map FileNotFoundError/ValueError -> RFC 7807 problem (read forecasting/routes.py
    + app/core/problem_details.py first).
  - PATTERN: ops/routes.py; forecasting/routes.py.
  - VALIDATE: uv run ruff check app/features/scenarios/ && uv run mypy app/

Task A6 — UPDATE app/main.py:
  - +1 import (alphabetical) + app.include_router(scenarios_router).
  - GOTCHA: preserve line endings; edit minimally (Gotcha #12).
  - VALIDATE: uv run python -c "from app.main import app; assert '/scenarios/simulate' in {r.path for r in app.routes}; print('wired')"

Task A7 — CREATE tests/test_adjustments.py + test_schemas.py:
  - test_adjustments.py: every pure helper — factor math, clamp bounds,
    kind/stage fallthrough, junk-input tolerance, apply_adjustment element-wise +
    non-negative.
  - test_schemas.py: SimulateScenarioRequest from ISO-string dates via
    model_validate({...}) (the FastAPI validate_python path); change_pct bounds.
  - PATTERN: ops/tests/test_service.py + test_schemas.py.
  - VALIDATE: uv run pytest -v -m "not integration" app/features/scenarios/tests/test_adjustments.py app/features/scenarios/tests/test_schemas.py

Task A8 — CREATE tests/test_leakage.py (LOAD-BEARING):
  - Assert the adjustment touches ONLY horizon points: apply_adjustment returns a
    new list and leaves the input baseline unchanged; out-of-window days
    contribute factor 1.0; len(points) == horizon; an assumption window before
    the forecast start contributes no factor.
  - PATTERN: app/features/featuresets/tests/test_leakage.py.
  - GOTCHA: never weaken this test to make a feature pass (AGENTS.md § Safety).
  - VALIDATE: uv run pytest -v -m "not integration" app/features/scenarios/tests/test_leakage.py

# ════════ PHASE B — Saved Scenario Plans (persistence) ════════

Task B1 — CREATE app/features/scenarios/models.py:
  - ScenarioPlan(TimestampMixin, Base) — see Data models above.
  - PATTERN: jobs/models.py + rag/models.py:DocumentSource.
  - GOTCHA: do NOT name a column `metadata` (Gotcha #5).
  - VALIDATE: uv run python -c "from app.features.scenarios.models import ScenarioPlan; print(ScenarioPlan.__tablename__)"

Task B2 — CREATE the Alembic migration:
  - uv run alembic revision -m "create scenario plan table", then hand-write
    upgrade() (op.create_table with all columns, postgresql.JSONB(astext_type=
    sa.Text()), GIN indexes, the CheckConstraint, created_at/updated_at with
    server_default=sa.text('now()')) and a real downgrade().
  - PATTERN: alembic/versions/37e16ecef223_create_jobs_table.py.
  - GOTCHA: confirm head with `uv run alembic heads` and set down_revision to it
    (currently 378c112e4b32 — VERIFY, do not assume; Gotcha #6).
  - VALIDATE: docker compose up -d && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head

Task B3 — EXTEND app/features/scenarios/schemas.py:
  - Add CreateScenarioRequest (request), ScenarioPlanResponse, ScenarioListItem,
    ScenarioListResponse (responses — from_attributes).
  - PATTERN: ops/schemas.py; jobs/schemas.py:JobListResponse.
  - VALIDATE: uv run mypy app/features/scenarios/schemas.py

Task B4 — EXTEND app/features/scenarios/service.py:
  - create_plan (runs simulate, persists ScenarioPlan, scenario_id=uuid4().hex),
    list_plans, get_plan, delete_plan.
  - GOTCHA: persist comparison + assumptions via model_dump(mode="json")
    (Gotcha #4).
  - PATTERN: jobs/service.py (create/list/get); registry/service.py.
  - VALIDATE: uv run mypy app/ && uv run pyright app/

Task B5 — EXTEND app/features/scenarios/routes.py:
  - POST /scenarios (201); GET /scenarios (limit/offset Query params, bounded);
    GET /scenarios/{scenario_id} (404 problem when missing);
    DELETE /scenarios/{scenario_id} (204, 404 when missing).
  - PATTERN: registry/routes.py (alias CRUD with 404 mapping).
  - VALIDATE: uv run python -c "from app.main import app; paths={r.path for r in app.routes}; assert {'/scenarios','/scenarios/{scenario_id}'} <= paths; print('wired')"

Task B6 — CREATE tests/conftest.py + test_routes_integration.py:
  - conftest.py: real-Postgres fixtures (ASGITransport client; scoped cleanup that
    INCLUDES delete(ScenarioPlan) + FK-safe deletes of seeded TEST-/test- rows; a
    trained_model fixture that puts a real bundle on disk for simulate).
  - test_routes_integration.py (@pytest.mark.integration): simulate happy path
    (200, points length == horizon, method == "heuristic"); bogus run_id -> RFC
    7807 problem (not 500); full CRUD round-trip; GET /scenarios on empty table ->
    200 + []. Plus a constraint test for the method CheckConstraint.
  - PATTERN: ops/tests/conftest.py + test_routes_integration.py;
    forecasting/tests/conftest.py.
  - GOTCHA: never mock the DB; integration tests need docker compose up + alembic
    upgrade head.
  - VALIDATE: docker compose up -d && uv run alembic upgrade head && uv run pytest -v -m integration app/features/scenarios/

# ════════ PHASE C — What-If Planner Page (frontend) ════════

Task C1 — UPDATE frontend/src/types/api.ts:
  - Add Scenario* TS interfaces (dates as string) mirroring the backend schemas.
  - PATTERN: the Ops* / InventoryStatus* blocks already in types/api.ts.
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task C2 — CREATE frontend/src/hooks/use-scenarios.ts:
  - useSimulateScenario (mutation), useCreateScenario (mutation, invalidates list),
    useScenarios (query), useScenario(scenarioId) (query), useDeleteScenario
    (mutation).
  - PATTERN: use-jobs.ts (useCreateJob mutation + useJobs query); use-ops.ts.
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task C3 — CREATE frontend/src/lib/scenario-utils.ts + scenario-utils.test.ts:
  - PURE utils: mergeComparisonSeries (ScenarioPoint[] -> chart rows),
    formatDelta (signed), deltaCsvColumns (CsvColumn<ScenarioPoint>[]),
    summariseAssumptions (human-readable bullets).
  - PATTERN: demand-utils.ts.
  - VALIDATE: cd frontend && pnpm test --run src/lib/scenario-utils.test.ts

Task C4 — UPDATE frontend/src/lib/constants.ts + frontend/src/App.tsx:
  - ROUTES.VISUALIZE.PLANNER = '/visualize/planner'; a Visualize NAV_ITEMS entry;
    a lazy import + <Route> in App.tsx (copy the DEMAND route).
  - GOTCHA: pnpm tsc fails until Task C5 creates the page — re-run after C5.
  - VALIDATE: (after C5) cd frontend && pnpm tsc --noEmit

Task C5 — CREATE frontend/src/pages/visualize/planner.tsx:
  - Build via frontend-design + shadcn-ui skills. Header Card with a prominent
    heuristic-disclaimer banner; baseline picker (JobPicker jobType="predict" +
    horizon Select); assumptions form (price slider, promotion kind + window,
    holiday dates, inventory units, lifecycle stage — all optional); a "Run
    simulation" Button; results (TimeSeriesChart two-series, KPI tiles, per-day
    delta Table + Export CSV, "Save as plan"); a saved-plans Card (list, reload,
    delete). Standard LoadingState / ErrorDisplay / EmptyState early returns.
  - PATTERN: demand.tsx (skeleton, states, drill-in, CSV); forecast.tsx (in-page
    job launch).
  - GOTCHA: renders inside AppShell; shadcn semantic tokens only; a green tsc is
    NOT proof the UI works (Gotcha #9).
  - VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task C6 — UPDATE docs:
  - README.md (feature list); docs/_base/API_CONTRACTS.md (5 /scenarios/* rows);
    docs/_base/REPO_MAP_INDEX.md (scenarios slice + planner.tsx);
    docs/_base/DOMAIN_MODEL.md (scenario_plan aggregate + ubiquitous-language rows).
  - VALIDATE: git diff --stat docs/ README.md

Task C7 — Dogfood the running UI (MANDATORY per .claude/rules/ui-design.md):
  - docker compose up -d && alembic upgrade head && seed_random --full-new, then
    `make demo` (so completed predict jobs + trained models exist), start uvicorn
    + vite, exercise via webapp-testing / agent-browser: pick a baseline job,
    define a -15% price + a pct_off promotion, run, confirm the two-series chart +
    non-zero deltas + the disclaimer banner, export the delta CSV, save the plan,
    reload it, delete it. Capture screenshots.
  - VALIDATE: screenshots captured; all 8 manual-check scenarios pass.

Task C8 — Commit + PR:
  - Commits (each (#issue), no AI co-author trailer):
    feat(api): add scenario simulation engine and simulate endpoint (#N)
    test(api): cover scenario adjustments, schemas, and leakage spec (#N)
    feat(api,db): add scenario_plan table and CRUD endpoints (#N)
    test(api): cover scenario plan persistence and CRUD (#N)
    feat(ui): add scenario data layer — types, hooks, scenario-utils (#N)
    feat(ui): add Visualize What-If Planner page (#N)
    docs(docs): document scenario simulation slice and planner page (#N)
  - GOTCHA: the PR description MUST flag (a) results are heuristic, deliberately
    labelled, not model-causal — the Full-Version exogenous-model path is out of
    scope; (b) the scenario service deliberately does NOT import sibling
    ForecastingService (DECISIONS LOCKED #2). Answer the 6 product-vision Litmus
    questions.
  - VALIDATE: open PR into dev; CI green; merge.
```

### Per-task pseudocode (critical details only)

```python
# Task A4 — ScenarioService.simulate (the heart of Phase A)
async def simulate(self, db: AsyncSession, request: SimulateScenarioRequest) -> ScenarioComparison:
    settings = get_settings()
    # GOTCHA #1/#2: resolve the ARTIFACT, mirror jobs/service.py:_execute_predict.
    # forecast_model_artifacts_dir is a str — wrap in Path (NOT settings.artifacts_dir).
    artifacts_dir = Path(settings.forecast_model_artifacts_dir).resolve()
    model_path = (artifacts_dir / f"model_{request.run_id}.joblib").resolve()
    # LOAD-BEARING path-traversal guard — mirror forecasting/service.py:218-248
    if model_path.suffix != ".joblib":
        raise ValueError(f"Invalid model path for run_id={request.run_id}")
    try:
        model_path.relative_to(artifacts_dir)                    # rejects ../ escape
    except ValueError:
        raise ValueError(f"Invalid model path for run_id={request.run_id}") from None
    if not model_path.exists():
        raise FileNotFoundError(f"No model artifact for run_id={request.run_id}")
    bundle = load_model_bundle(model_path)                       # forecasting/persistence.py
    # bundle.metadata is dict[str, object] — int(str(...)) keeps mypy --strict happy
    store_id  = int(str(bundle.metadata["store_id"]))
    product_id = int(str(bundle.metadata["product_id"]))
    # DECISIONS LOCKED #2: replicate the ForecastingService.predict body — do NOT import it
    raw = bundle.model.predict(request.horizon)                  # BaseForecaster interface
    # train_end_date is stored as an ISO STRING — parse it; fall back to today if absent
    train_end_raw = bundle.metadata.get("train_end_date")
    train_end_date = (date.fromisoformat(train_end_raw)
                      if isinstance(train_end_raw, str)
                      else datetime.now(UTC).date())
    start = train_end_date + timedelta(days=1)
    baseline_pts = [ForecastPoint(date=start + timedelta(days=i), forecast=float(v))
                    for i, v in enumerate(raw)]
    # estimate unit price (revenue delta)
    unit_price = await self._latest_unit_price(db, store_id, product_id)   # default + warn if none
    # apply per-day deterministic factors — adjustments.py is PURE
    factors = [adjustments.combined_daily_factor(day_index=i, horizon=request.horizon,
               assumptions=request.assumptions) for i in range(request.horizon)]
    baseline = [p.forecast for p in baseline_pts]
    scenario = adjustments.apply_adjustment(baseline, factors)   # element-wise, max(0.0,...)
    # aggregate — guard divide-by-zero (Gotcha #10)
    ...
    return ScenarioComparison(method="heuristic", disclaimer=HEURISTIC_DISCLAIMER, ...)
```

### Integration Points

```yaml
DATABASE:
  - migration: "create scenario_plan table (id, scenario_id, name, store_id,
                product_id, run_id, horizon, assumptions JSONB, comparison JSONB,
                method, created_at, updated_at)"
  - index: "GIN on assumptions + comparison; composite (store_id, product_id);
            unique on scenario_id"
  - constraint: "CheckConstraint method IN ('heuristic')"
  - down_revision: "378c112e4b32  (VERIFY with `uv run alembic heads`)"

ROUTES:
  - add to: app/main.py
  - pattern: "from app.features.scenarios.routes import router as scenarios_router
              ... app.include_router(scenarios_router)"

FRONTEND ROUTING:
  - add to: frontend/src/lib/constants.ts
  - pattern: "ROUTES.VISUALIZE.PLANNER = '/visualize/planner' + a Visualize
              NAV_ITEMS entry"
  - add to: frontend/src/App.tsx
  - pattern: "lazy(() => import('@/pages/visualize/planner')) + a <Route>"

CONFIG:
  - no new config — reuses settings.forecast_model_artifacts_dir (a str;
    wrap with Path(...) before use, app/core/config.py)
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . --fix && uv run ruff format --check .
cd frontend && pnpm lint
# Traps: date.today() / naive datetime -> ruff DTZ (use datetime.now(UTC));
#        os.path -> ruff PTH (use pathlib.Path); a stray # noqa -> RUF100.
```

### Level 2: Type Checks

```bash
uv run mypy app/ && uv run pyright app/        # both --strict, both gate merge
cd frontend && pnpm tsc --noEmit
```

### Level 3: Unit Tests

```bash
uv run pytest -v -m "not integration" app/features/scenarios/
cd frontend && pnpm test --run src/lib/scenario-utils.test.ts
```

### Level 4: Integration Tests

```bash
docker compose up -d && uv run alembic upgrade head
uv run pytest -v -m integration app/features/scenarios/
# Migration up/down check:
uv run alembic downgrade -1 && uv run alembic upgrade head
```

### Level 5: Manual Validation (dogfood — REQUIRED)

```bash
docker compose up -d && uv run alembic upgrade head
uv run python scripts/seed_random.py --full-new --seed 42 --confirm
make demo                                       # populates predict jobs + models
uv run uvicorn app.main:app --port 8123 &
until curl -fs http://127.0.0.1:8123/health; do sleep 2; done
# stateless simulate:
curl -s -X POST http://localhost:8123/scenarios/simulate \
  -H 'content-type: application/json' \
  -d '{"run_id":"<artifact-run-id>","horizon":14,
       "assumptions":{"price":{"change_pct":-0.15,
       "start_date":"2026-06-01","end_date":"2026-06-14"}}}' | head -c 600
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  http://localhost:8123/scenarios/simulate -H 'content-type: application/json' \
  -d '{"run_id":"does-not-exist","horizon":14,"assumptions":{}}'   # expect 404, not 500
# Frontend: cd frontend && ./node_modules/.bin/vite --host 0.0.0.0
#   -> open http://localhost:5173/visualize/planner via webapp-testing/agent-browser:
#     pick a baseline job, set a price + promotion assumption, run, verify the
#     two-series chart + non-zero deltas + the heuristic disclaimer, export the
#     delta CSV, save the plan, reload it from the saved list, delete it.
```

### Level 6: Additional Validation (optional)

```bash
# Confirm Recharts / TanStack Query usage against current docs via the contex7 MCP
# if the TimeSeriesChart two-series wiring or a mutation pattern is uncertain.
```

---

## Final Validation Checklist

- [ ] `uv run ruff check . && uv run ruff format --check .` — clean
- [ ] `uv run mypy app/ && uv run pyright app/` — clean (`--strict`)
- [ ] `uv run pytest -v -m "not integration"` — green (incl. the leakage spec)
- [ ] `docker compose up -d && uv run pytest -v -m integration` — green
- [ ] `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` — clean
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` — green
- [ ] `POST /scenarios/simulate` behaves per Success Criteria (points length ==
      horizon, method == "heuristic", bogus run_id -> RFC 7807, not 500)
- [ ] CRUD round-trip works; `GET /scenarios` on an empty table -> 200 + []
- [ ] `/visualize/planner` runs a simulation, shows a two-series chart + delta
      table + heuristic disclaimer, exports CSV, saves/reloads/deletes a plan —
      dogfooded in a browser (screenshots captured)
- [ ] No new external dependency; no managed-cloud SDK; no WebSocket
- [ ] `scenario_plan` table created via migration; columns named `assumptions` /
      `comparison` (never `metadata`)
- [ ] README + `docs/_base/{API_CONTRACTS,REPO_MAP_INDEX,DOMAIN_MODEL}.md` updated
- [ ] Branch `feat/scenario-what-if-planner`; every commit references the tracking
      issue; commit scopes are `api`/`api,db`/`ui`/`docs` (no `scenarios` scope);
      no AI co-author trailer
- [ ] PR description flags: (a) heuristic, not model-causal — Full Version out of
      scope; (b) the scenario service deliberately does NOT import sibling
      `ForecastingService` (DECISIONS LOCKED #2); and answers the 6 Litmus-Test
      questions

---

## Anti-Patterns to Avoid

- ❌ Don't import `ForecastingService` (or any sibling slice's `service.py`) into
  `scenarios` — import only `load_model_bundle` from `forecasting/persistence.py`
  and replicate the predict body (DECISIONS LOCKED #2).
- ❌ Don't add an exogenous-regressor model or a future-feature-frame generator —
  that is the Full Version, out of scope (DECISIONS LOCKED #1).
- ❌ Don't re-train a model to produce the scenario — the MVP applies a
  post-forecast deterministic multiplier.
- ❌ Don't drop the `method: "heuristic"` label or the `disclaimer` — they are the
  NIST-AI-RMF transparency control against over-trust.
- ❌ Don't put `ConfigDict(strict=True)` on response models; don't omit
  `Field(strict=False)` on `date` fields of request bodies (Gotcha #3).
- ❌ Don't name a `scenario_plan` column `metadata` — SQLAlchemy reserves it
  (Gotcha #5).
- ❌ Don't persist Python `date`/`datetime` into JSONB — use
  `model_dump(mode="json")` (Gotcha #4).
- ❌ Don't guess the migration `down_revision` — verify with `uv run alembic heads`
  (Gotcha #6).
- ❌ Don't weaken `test_leakage.py` to make a feature pass — it is the spec.
- ❌ Don't `raise HTTPException(500, "raw string")` — use the RFC 7807 envelope.
- ❌ Don't add a WebSocket — simulation is request/response (DECISIONS LOCKED #6).
- ❌ Don't `pnpm add` anything — Recharts / TanStack Query / shadcn primitives are
  installed.
- ❌ Don't hand-roll a chart — pass two series to the existing `TimeSeriesChart`.
- ❌ Don't claim the UI works on a green type-check — dogfood it in a browser.
- ❌ Don't invent a `scenarios` commit scope — use `api`/`api,db`/`ui`/`docs`.

## NOTES — open questions / planning decisions to lock before coding

- **Heuristic factor values are not yet final.** `PRICE_ELASTICITY = -1.2`,
  `PROMOTION_UPLIFT_BY_KIND`, `HOLIDAY_UPLIFT = 1.30`, `LIFECYCLE_FACTOR`, and the
  `FACTOR_BAND` clamp `[0.1, 5.0]` are *suggested starting values*. They are a
  planning decision — confirm them (or adjust) before coding `adjustments.py`.
  They are deliberately conservative and documented as constants so a reviewer can
  see and tune them. The tests assert *direction and bounds* (a price cut → uplift
  > 1, a clamp keeps the factor in band), not exact magnitudes — so reasonable
  re-tuning does not break tests.
- **`coverage_verdict` band**: `at_risk` is suggested as "scenario total within
  10% of `on_hand_units`". Confirm the band before coding.
- **`unit_price_used` fallback**: when no `SalesDaily` row exists for the
  `(store, product)`, the service falls back to a documented default (suggested
  `1.0`) and logs a warning. Confirm the default.
- **Lifecycle stage source**: the MVP takes `lifecycle.stage` as a direct user
  override on the assumption form — it does not derive the current stage from
  `product.launch_date`. Deriving it is a Full-Version concern.

## Confidence Score

**9 / 10** for one-pass implementation success.

Rationale: the source plan (`.agents/plans/scenario-simulation-what-if-planning.md`)
is unusually thorough and was validated against the repo as of 2026-05-19 — every
file path, class name, and pattern reference here was cross-checked. The two
highest-risk areas are both de-risked: (1) the cross-slice-import constraint is
resolved by a locked decision (import `load_model_bundle`, replicate the predict
body) rather than left for the implementer to discover; (2) the artifact-resolution
gotcha (`run_id` is the artifact key, not a registry id) is called out explicitly
with the exact reference (`jobs/service.py:_execute_predict`). `adjustments.py` is
pure, dependency-free, and trivially unit-testable. Phase C is a near-exact mirror
of PRP-22's `demand.tsx` shape over a deterministic backend. The residual 1-point
risk is the heuristic factor *values* (NOTES) — a planning decision that does not
affect the structure, and the tests assert direction/bounds rather than exact
magnitudes, so re-tuning is safe. The biggest scope risks of the feature brief —
an exogenous-regressor model and a WebSocket — are removed by DECISIONS LOCKED #1
and #6, keeping every phase aligned with the single-host, non-streaming, time-safe
product vision.
