# PRP-31 — MLZOO-D — Frontend, Registry, and Explainability Polish

> **Sequence position:** Final MLZOO PRP. A (PRP-29) → B (PRP-30) → B.2 (PRP-MLZOO-B.2)
> → C1 (PRP-MLZOO-C1) → C2 (PRP-MLZOO-C2) all merged in v0.2.16. This PRP is the
> surfacing layer: it exposes the advanced-model metadata the backend already
> captures (and a small slice it does not yet) in the React dashboard, plus a
> minimal "feature importance" hook for the three feature-aware model families.

## Purpose

Make Advanced ML Model Zoo capabilities **discoverable in the product**. Today, a
user who trains a LightGBM, XGBoost, regression, or prophet_like model sees the
same flat `model_type` string in the runs explorer that a `naive` baseline
produces — even though the registry already stores richer config, dependency
versions, and (inside the joblib bundle) the canonical 14-column feature frame
and the fitted estimator's learned importances. This PRP closes that gap with
the smallest possible surface: two new backend endpoints
(`/forecasting/runs/{run_id}/feature-metadata` and
`/forecasting/jobs/{job_id}/feature-metadata`), one computed registry field,
one new React panel, and additive in-place edits to four existing pages.

This PRP follows the staging contract in `PRPs/INITIAL/INITIAL-MLZOO-index.md`
("D. Frontend / registry / explainability") and the original brief at
`PRPs/INITIAL/INITIAL-MLZOO-D-frontend-registry-explainability.md`.

## What this PRP already inherits (DO NOT re-build)

The backend mechanics this PRP surfaces are **already shipped in v0.2.16**.
Do not re-implement any of:

- **The canonical feature frame** (`app/shared/feature_frames/contract.py:80-98`)
  — 14 columns: 4 target lags (`lag_1`, `lag_7`, `lag_14`, `lag_28`), 6 calendar
  signals (`dow_sin`, `dow_cos`, `month_sin`, `month_cos`, `is_weekend`,
  `is_month_end`), 4 exogenous (`price_factor`, `promo_active`, `is_holiday`,
  `days_since_launch`). Use as-is; do not propose adding or removing columns
  in MLZOO-D.
- **The four feature-aware forecasters** with `requires_features: ClassVar[bool] = True`:
  `RegressionForecaster` (`app/features/forecasting/models.py:483`),
  `LightGBMForecaster` (`models.py:625`), `XGBoostForecaster` (`models.py:787`),
  `ProphetLikeForecaster` (`models.py:950`). All four already persist
  `feature_columns` into `bundle.metadata` at train time
  (`app/features/forecasting/service.py:233-238`).
- **Runtime info capture** (`app/features/registry/service.py:84-139`) — Python,
  sklearn, numpy, pandas, joblib, plus conditional `lightgbm_version` /
  `xgboost_version` already in the `runtime_info` JSONB.
- **Bundle deserialization** (`app/features/forecasting/persistence.py:136-176`)
  — `load_model_bundle(path)` is the proven entry point for any "load the
  fitted model, inspect it" workflow. Mirror the `/registry/runs/{run_id}/verify`
  precedent (`app/features/registry/routes.py:327`) for the new endpoint.
- **RFC 7807 error envelope** via `app/core/exceptions.py:BadRequestError` /
  `DatabaseError` — the existing `forecastlab_exception_handler` serializes
  these to `application/problem+json`. Never raise bare `HTTPException(400, "...")`
  (PR #253 review fix; v0.2.16 closed the last holes).
- **Explanation panel** (`frontend/src/components/explainability/explanation-panel.tsx`)
  + hooks (`frontend/src/hooks/use-explanations.ts`) — baseline-only by design
  per `PRPs/PRP-28-forecast-explainability-driver-attribution.md`. **Do not
  extend the existing panel** to advanced models; build a sibling panel.
- **Run-detail, run-compare, runs explorer, forecast viz, backtest viz** —
  existing structure (`frontend/src/pages/explorer/{runs,run-detail,run-compare}.tsx`,
  `frontend/src/pages/visualize/{forecast,backtest}.tsx`). Insertions only,
  never rewrites.

## DEPENDS ON — read before starting

```yaml
# Prerequisite PRPs (all merged; read for context, not action)
- PRPs/PRP-29-feature-aware-forecasting-foundation.md   # FeatureFrameContract; ClassVar requires_features
- PRPs/PRP-30-lightgbm-first-advanced-model.md          # LightGBM contract; runtime_info shape
- PRPs/PRP-MLZOO-B.2-feature-aware-backtesting.md       # Per-fold X_train/X_future leakage-safe split
- PRPs/PRP-MLZOO-C1-xgboost-model.md                    # XGBoost mirror of LightGBM
- PRPs/PRP-MLZOO-C2-prophet-like-additive-model.md      # Additive Ridge pipeline; decompose()
- PRPs/PRP-28-forecast-explainability-driver-attribution.md  # Existing baseline ExplanationPanel
# Foundation INITIAL
- PRPs/INITIAL/INITIAL-MLZOO-index.md                   # Sequencing rule: keep D additive, no model families
- PRPs/INITIAL/INITIAL-MLZOO-D-frontend-registry-explainability.md  # The brief this PRP implements

# Files that anchor every implementation decision below
- app/features/forecasting/models.py                    # feature_importances_ / coef_ extraction
- app/features/forecasting/persistence.py               # load_model_bundle() entry point
- app/features/forecasting/service.py                   # extra_metadata population at line 233
- app/features/registry/routes.py                       # /verify precedent at line 327
- app/features/registry/schemas.py                      # RunResponse + alias="model_config"
- frontend/src/components/explainability/explanation-panel.tsx  # the layout pattern to mirror
- frontend/src/components/explainability/explanation-panel.test.tsx  # the test scaffolding to mirror
- frontend/src/pages/explorer/run-detail.tsx            # insertion target (line 156-189 region)
- frontend/src/pages/explorer/runs.tsx                  # MODEL_TYPES allow-list at line 21
```

## Goal

Surface advanced-model metadata in five places — runs explorer, run detail,
run compare, forecast viz, backtest viz — without changing the data model,
the migration set, the agent surface, or the model contracts.

Deliverables (each is independently verifiable):

1. **Two backend endpoints** — both forecasting-scoped, mirroring PRP-28's
   `/explain/runs/{run_id}` + `/explain/jobs/{job_id}` shape exactly:
   - `GET /forecasting/runs/{run_id}/feature-metadata` — registry-UUID-keyed
     (consumed by run-detail / run-compare pages).
   - `GET /forecasting/jobs/{job_id}/feature-metadata` — job-keyed sibling
     (consumed by `forecast.tsx`, which only has the `job_id` and whose
     `job.result.run_id` is the **artifact key**, NOT a registry UUID —
     see Critical-fix note below and memory `scenario-run-id-vs-registry-run-id`).
   Both return canonical feature columns + learned feature importance
   (tree models) or signed coefficients (prophet_like additive). RFC 7807
   errors throughout: 400 for baseline-family runs, 404 for missing run/job,
   422 for runs in `pending`/`running`/`failed` status or missing artifacts
   (a successful `archived` run with an intact artifact still returns 200).
2. **One computed registry field** — `model_family: Literal["baseline","tree","additive"]`
   on `RunResponse`, derived from `model_type` (no DB column, no migration).
3. **One frontend panel** — `<FeatureImportancePanel>` mirroring the structure
   of the existing `<ExplanationPanel>` but rendering ranked importance bars
   plus the model-family caveat ("model-derived, not causal").
4. **In-place additions** to the five pages (column, badge, card insertion,
   hook wiring). No layout rewrites.
5. **Docs touch-up** — one new subsection in `docs/user-guide/feature-reference.md`
   explaining what advanced-model metadata the dashboard exposes and the
   correlation-vs-causation caveat.

## Why

- INITIAL-MLZOO-D is the last unshipped piece of the MLZOO sequence. Backend
  contracts have been frozen across A/B/B.2/C1/C2; the dashboard hasn't moved.
- Operators currently have no way to see WHICH features drove a trained advanced
  model. Two LightGBM runs against the same store/product/window with different
  hyperparameters look identical in the runs table.
- The existing `<ExplanationPanel>` (PRP-28) is rule-based and baseline-only —
  it correctly returns 400 for `lightgbm` / `xgboost` / `regression` /
  `prophet_like`. Until MLZOO-D ships, there is **no advanced-model
  introspection** in the UI at all.
- The "model_family" categorisation is implicit today (the agent reports note
  no enum exists). Surfacing it once, deterministically, lets every page show
  a consistent Baseline / Tree / Additive badge without 5 ad-hoc string maps.

## What

### Backend additions

1. New module `app/features/forecasting/feature_metadata.py`:
   - `extract_feature_importance(model: BaseForecaster, feature_columns: list[str])
     -> list[FeatureImportanceItem]` — branches on instance type:
     - `LightGBMForecaster` / `XGBoostForecaster` / `RegressionForecaster` →
       `estimator.feature_importances_` (always non-negative, tree-based)
     - `ProphetLikeForecaster` → `pipeline.named_steps["ridge"].coef_` (signed)
     - Any other type → raise `ValueError` (used by the route to emit 400)
   - Returns items sorted by `|importance|` descending; each item carries
     `name: str`, `importance: float`, `kind: Literal["tree","linear_coef"]`,
     `rank: int` (1-indexed).

2. New endpoint `GET /forecasting/runs/{run_id}/feature-metadata` in
   `app/features/forecasting/routes.py`:
   - Looks up the run via the registry service (cross-slice: forecasting
     already imports registry via the train flow).
   - 404 if the run doesn't exist; 400 (RFC 7807 via `BadRequestError`) if the
     run is for a baseline model; 422 if `artifact_uri is None` or the run is
     `pending` / `running` / `failed`.
   - On success: `load_model_bundle(artifact_uri)`, then call
     `extract_feature_importance(bundle.model, bundle.metadata["feature_columns"])`.
   - Returns `FeatureMetadataResponse` (Pydantic schema, see Data Models).

3. Computed field `model_family` on `RunResponse`
   (`app/features/registry/schemas.py`):
   - `model_family: ModelFamily` populated via a Pydantic `@computed_field` or
     `model_validator(mode="after")`, derived from `model_type`.
   - Map: `{naive, seasonal_naive, moving_average} → baseline`;
     `{regression, lightgbm, xgboost} → tree`; `{prophet_like} → additive`.
   - Unknown types return `baseline` and emit a `logger.warning` (forward-compat
     for future model families before this map is updated).

4. Docstring drift fix in `app/features/forecasting/routes.py:33-37` —
   list `xgboost`, `regression`, `prophet_like` alongside `lightgbm` in the
   `/forecasting/train` description (currently only `lightgbm` is named).
   Bundle into the same commit as the new endpoint.

### Frontend additions

1. **Types** (`frontend/src/types/api.ts`):
   - Add `ModelFamily = 'baseline' | 'tree' | 'additive'`.
   - Add `model_family: ModelFamily` to `ModelRun` and `RunResponse`-shaped
     types.
   - Add `FeatureImportanceItem`, `FeatureMetadataResponse` matching the
     backend schemas exactly.

2. **Hooks** (`frontend/src/hooks/use-feature-metadata.ts` — new file, two sibling exports):
   - `useRunFeatureMetadata(runId: string, enabled: boolean)` →
     queryKey `['feature-metadata', 'run', runId]`, URL
     `/forecasting/runs/${runId}/feature-metadata`.
   - `useJobFeatureMetadata(jobId: string, enabled: boolean)` →
     queryKey `['feature-metadata', 'job', jobId]`, URL
     `/forecasting/jobs/${jobId}/feature-metadata`. **Required** for
     `forecast.tsx`, which holds only a `job_id` (not a registry UUID).
   - Both use `retry: false` because a 400 (baseline family) / 404 / 422 is
     a final answer, not a transient. Mirror `useRunExplanation` +
     `useJobExplanation` (PRP-28) exactly.

3. **Panel** (`frontend/src/components/explainability/feature-importance-panel.tsx` — new):
   - Card shell with title "Feature Importance" + description that names the
     model family.
   - Body: horizontal bar list (top N by importance, default 14 — exactly the
     canonical feature count). For `kind === "linear_coef"`, show the sign
     (red/green) and label the column as "Coefficient" instead of "Importance".
   - Caveat footer: "Importance is model-derived. It reflects how much each
     feature reduced the model's training error — not real-world causation."
   - Same error-handling shape as `ExplanationPanel`: neutral muted card for
     `ApiError.status === 400` (non-feature-aware) or 422 (no artifact),
     destructive card for unexpected.

4. **Test** (`feature-importance-panel.test.tsx` — new):
   - Mirror the fixture pattern from `explanation-panel.test.tsx:7-30`.
   - Cases: renders ranked tree-model items; renders signed coefficients with
     direction icons; loading state; 400 neutral message; 422 "artifact not
     available" message; empty `features` list message.

5. **Badge helper** (`frontend/src/components/common/model-family-badge.tsx` — new):
   - `<ModelFamilyBadge family={model_family} />` → shadcn `<Badge>` with a
     deterministic `variant` mapping: `baseline` → `secondary`, `tree` →
     `default`, `additive` → `outline`. Pure derivation, no API call.

6. **Pages — in-place additive edits only:**

   a. `frontend/src/pages/explorer/runs.tsx`:
      - Extend the `MODEL_TYPES` allow-list (line 21) to
        `['naive', 'seasonal_naive', 'moving_average', 'regression', 'lightgbm', 'xgboost', 'prophet_like']`.
      - Insert a new column after `model_type` (line 47) that renders
        `<ModelFamilyBadge family={row.original.model_family} />`.
      - Add `model_family` to `csvColumns` (line 83-92).

   b. `frontend/src/pages/explorer/run-detail.tsx`:
      - Add `<ModelFamilyBadge>` next to the model-type field in the profile
        card (around line 95-143).
      - New `<Card>` titled "Feature Metadata" between the existing "Metrics"
        card (line 156-164) and the "Forecast Explanation" panel (line 166-170)
        — but render it ONLY when `run.model_family !== 'baseline'`. Inside:
        a small list of `bundle.metadata.feature_columns` (the 14 canonical
        names, fetched from the new endpoint).
      - Render `<FeatureImportancePanel>` immediately below the existing
        `<ExplanationPanel>` (around line 170), fed by
        `useRunFeatureMetadata(runId, run.model_family !== 'baseline')`.

   c. `frontend/src/pages/explorer/run-compare.tsx`:
      - Add a "Family" row to the Profile table (lines 145-213): two
        `<ModelFamilyBadge>` cells side by side.
      - Add a new collapsible Card after the "Metrics diff" card (line 231-266)
        titled "Feature Importance (Run A vs Run B)" rendering two
        `<FeatureImportancePanel>`s side by side in a `grid-cols-2` (mobile:
        stacked). Both fed by `useRunFeatureMetadata(_, enabled)` — pass
        `enabled: false` for both when families differ so no fetch fires.

   d. `frontend/src/pages/visualize/forecast.tsx`:
      - **CRITICAL:** `trainJob.result.run_id` is the forecast-artifact key,
        NOT a registry UUID — see Task 17 and memory
        `scenario-run-id-vs-registry-run-id`. Use `useJobFeatureMetadata(trainJobId, ...)`
        keyed by the **job_id**, not by the artifact key.
      - Render a compact `<ModelFamilyBadge>` + `<FeatureImportancePanel>` in
        a `<Collapsible>` near the existing `<ExplanationPanel>` (line 256-263)
        — collapsed by default to preserve scan flow.

   e. `frontend/src/pages/visualize/backtest.tsx`:
      - Extend `MODEL_OPTIONS` (line 52) to add `lightgbm`, `xgboost`,
        `regression`, `prophet_like`. The B.2 backtest path is fully
        feature-aware on the backend; this is the last gating that prevented
        operators from running an advanced-model backtest from the UI.
      - No other change in this PRP (no per-model importance comparison;
        deferred — see "Anti-Patterns to Avoid").

### Docs additions

1. New "Advanced Model Metadata" subsection in
   `docs/user-guide/feature-reference.md`:
   - One paragraph naming the four feature-aware families and what the
     dashboard exposes (family badge, feature columns, importance / coefs).
   - One paragraph stating the correlation-vs-causation caveat verbatim:
     "Feature importance is model-derived. It reflects how much each feature
     reduced the model's training error — not real-world causation."

2. One-line mention in `docs/user-guide/dashboard-guide.md` linking to the
   new subsection from wherever it discusses the runs explorer / run detail.

3. **No new ADR.** No new external dependency. No new core path. SHAP / LIME
   remain out of scope (PRP-28 § "Adding SHAP later needs its own PRP + ADR";
   honour that).

### Success Criteria

- [ ] `GET /forecasting/runs/{run_id}/feature-metadata` returns 200 with a
      sorted `features: list[FeatureImportanceItem]` for a successful
      LightGBM / XGBoost / regression / prophet_like run.
- [ ] `GET /forecasting/jobs/{job_id}/feature-metadata` returns 200 with the
      same payload shape for a completed `train` job whose underlying model
      is non-baseline; 400 for a `predict` / non-completed / baseline-trained
      job; 404 for an unknown `job_id`.
- [ ] Both endpoints return RFC 7807 `application/problem+json` 400 for
      baseline runs, 404 for missing run/job, 422 for runs whose
      `artifact_uri is None`, runs in `pending`/`running`/`failed` status,
      `ModuleNotFoundError` raised by `joblib.load` (missing ml-* extra),
      and `FileNotFoundError` raised by `load_model_bundle` (artifact file
      deleted or moved on disk while the registry/job row lives on).
      Archived runs with intact artifacts still return 200.
- [ ] The 422 type URI is `UNPROCESSABLE_ENTITY` (not `VALIDATION_ERROR`) so
      consumers can disambiguate state-prevented operations from input
      validation failures.
- [ ] `RunResponse.model_family` is populated for every run returned by
      `/registry/runs` and `/registry/runs/{run_id}` without a second DB query
      and without an Alembic migration.
- [ ] The runs explorer table shows a `Family` Badge column; filtering by
      `?model_type=lightgbm|xgboost|prophet_like|regression` works
      end-to-end (no 422 from the URL-param allow-list).
- [ ] The run detail page renders `<ModelFamilyBadge>`, a "Feature Metadata"
      card listing the 14 canonical columns, and `<FeatureImportancePanel>`
      for a successful LightGBM run; renders nothing extra (no error,
      no empty card) for a successful baseline run.
- [ ] The run compare page renders two `<FeatureImportancePanel>`s side by
      side when both selected runs share `model_family`; renders a single
      explanatory message ("cross-family comparison not supported") when
      they differ.
- [ ] The forecast viz page renders a collapsible `<FeatureImportancePanel>`
      tied to the train run, when the train run's family is not baseline.
- [ ] The backtest viz page lets the user pick `lightgbm`, `xgboost`,
      `regression`, or `prophet_like` and runs the backtest successfully.
- [ ] `<FeatureImportancePanel>` renders signed direction (`+` green / `-` red)
      for prophet_like coefficients and positive-only bars for tree-model
      importances.
- [ ] Validation gates pass: `ruff check`, `ruff format --check`, `mypy --strict`,
      `pyright --strict`, `pytest -v -m "not integration"`,
      `pytest -v -m integration`, `pnpm tsc --noEmit`, `pnpm lint`,
      `pnpm test --run`.
- [ ] Browser dogfood via `webapp-testing` skill: dashboard renders all five
      pages cleanly against a database containing at least one trained run
      per family (use `make demo` plus a manual LightGBM train; the v0.2.16
      contract makes this reachable with a single curl).

## All Needed Context

### Documentation & References

```yaml
# ─── Library docs (sections, not just domains) ─────────────────────────────
- url: https://lightgbm.readthedocs.io/en/v4.5.0/pythonapi/lightgbm.LGBMRegressor.html
  why: feature_importances_ attribute semantics ("gain" by default; non-negative ndarray)
  critical: |
    LGBMRegressor.feature_importances_ is shape (n_features,), integer "split"
    by default but exposed as float when importance_type="gain" is set.
    The model_factory does NOT override importance_type — confirm what
    ships and document the kind explicitly in the response JSON.

- url: https://xgboost.readthedocs.io/en/stable/python/python_api.html#xgboost.XGBRegressor.feature_importances_
  why: XGBoost mirrors LightGBM's API for feature_importances_; same shape, default importance_type='weight'
  critical: |
    Like LightGBM, document the importance_type in the response so consumers
    know whether they're seeing "gain", "weight", or "cover".

- url: https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html#sklearn.linear_model.Ridge
  why: Ridge.coef_ is a signed ndarray. The prophet_like pipeline's coef_ lives at pipeline.named_steps["ridge"].coef_
  critical: |
    Sign carries directional information that Importance does NOT — the panel
    MUST surface it (green/+ vs red/−). Do NOT take abs() before display.

- url: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html#sklearn.ensemble.HistGradientBoostingRegressor.feature_importances_
  why: RegressionForecaster wraps HistGradientBoostingRegressor; same .feature_importances_ pattern as LightGBM
  critical: |
    HistGBR's feature_importances_ is "permutation-based on training data"
    by default — slower than LightGBM/XGBoost's tree-split impurity but
    still non-negative.

- url: https://tanstack.com/query/v5/docs/framework/react/guides/queries
  why: retry: false pattern for endpoints where 4xx is a final answer
  critical: Mirror frontend/src/hooks/use-explanations.ts:10-17 verbatim

- url: https://ui.shadcn.com/docs/components/badge
  why: Badge variants (default | secondary | destructive | outline) — used by ModelFamilyBadge

- url: https://ui.shadcn.com/docs/components/collapsible
  why: Used on forecast.tsx to keep the importance panel collapsed by default

- url: https://recharts.org/en-US/api/BarChart
  why: Used by frontend/src/components/charts/revenue-bar-chart.tsx — template for the horizontal importance bars

# ─── In-repo files (the actual patterns to mirror) ─────────────────────────
- file: app/features/registry/routes.py
  lines: 327-410
  why: /verify endpoint — exact precedent for "load the artifact, return JSON" pattern, including 404 + integrity error handling

- file: app/features/forecasting/persistence.py
  lines: 136-176
  why: load_model_bundle() — the only sanctioned bundle-deserialization entry point; do not re-implement

- file: app/features/forecasting/models.py
  lines: 1094-1100
  why: prophet_like's pipeline.named_steps["ridge"].coef_ is the ONLY signed-coefficient extraction path; ridge.coef_ is shape (n_features,)

- file: app/features/forecasting/service.py
  lines: 222-238
  why: shows that bundle.metadata["feature_columns"] is already populated for every feature-aware train; the new endpoint reads this back

- file: app/features/registry/schemas.py
  lines: 65-92, 109-138
  why: RunResponse Pydantic v2 alias pattern (model_config_data aliased to "model_config"); ConfigDict(populate_by_name=True)
  critical: |
    Pydantic v2 strict mode applies on FastAPI request bodies; date/datetime
    fields need Field(strict=False, ...) overrides — but RunResponse is a
    RESPONSE, not a request, so this gotcha does NOT apply to the new types
    here. (Confirm with .claude/rules/security-patterns.md § Pydantic v2 strict mode.)

- file: app/features/registry/tests/test_routes.py
  why: existing route-test pattern; use as the spec for test_routes_feature_metadata.py

- file: app/core/exceptions.py
  why: BadRequestError, DatabaseError — the only RFC 7807-handled exception classes; v0.2.16 PR #253 closed the last holes that used bare HTTPException

- file: frontend/src/components/explainability/explanation-panel.tsx
  lines: 22-26, 78-92, 104-125, 136-216
  why: exact layout pattern to mirror — PanelShell, ApiError 400 → neutral; everything else → destructive

- file: frontend/src/components/explainability/explanation-panel.test.tsx
  why: vitest scaffolding (fixture shape, render assertions); copy structure verbatim

- file: frontend/src/hooks/use-explanations.ts
  lines: 10-17
  why: useRunExplanation pattern — retry: false; queryKey shape; enabled gating

- file: frontend/src/types/api.ts
  lines: 170-217, 873-903
  why: where to add ModelFamily / FeatureImportanceItem / FeatureMetadataResponse

- file: frontend/src/pages/explorer/runs.tsx
  lines: 21, 24-81, 83-92, 101
  why: MODEL_TYPES allow-list extension point; ColumnDef pattern; csvColumns extension point

- file: frontend/src/pages/explorer/run-detail.tsx
  lines: 88-211
  why: insertion zones (profile card, metrics, explanation; the new card slots in between)

- file: frontend/src/pages/explorer/run-compare.tsx
  lines: 28-50, 82-85, 143-267
  why: DeltaCell pattern (sign-only coloring), URL-param ?a=&b=, side-by-side table layout

- file: frontend/src/pages/visualize/forecast.tsx
  lines: 36-79, 256-263
  why: train→predict job flow; where ExplanationPanel currently renders

- file: frontend/src/pages/visualize/backtest.tsx
  lines: 52-56
  why: MODEL_OPTIONS allow-list — the only file to touch for the backtest extension

- file: frontend/src/components/charts/revenue-bar-chart.tsx
  why: closest existing horizontal-bar precedent (single Bar series; deterministic palette via --chart-N)

# ─── Project rules (read once before starting) ─────────────────────────────
- file: .claude/rules/security-patterns.md
  why: RFC 7807 envelope; Pydantic v2 strict mode policy (applies to request bodies only)

- file: .claude/rules/test-requirements.md
  why: every new module/endpoint/component needs a matching test

- file: .claude/rules/ui-design.md
  why: webapp-testing skill required for browser dogfood; do not hand-roll UI when a skill applies

- file: .claude/rules/shadcn-ui.md
  why: use the shadcn MCP for new components; the Badge / Collapsible / Card primitives needed here are already installed

- file: docs/_base/SECURITY.md
  section: "Pydantic v2 strict mode on FastAPI request bodies"
  why: confirms the response-only types in this PRP do not need Field(strict=False, ...)

- file: docs/_base/DOMAIN_MODEL.md
  why: confirms "the registry's RunResponse is the surface MLZOO-D extends"; ubiquitous-language match for "model family", "feature importance"
```

### Current Codebase tree (relevant slice)

```text
app/features/forecasting/
├── models.py            # BaseForecaster, the four feature-aware models
├── persistence.py       # ModelBundle, load_model_bundle, save_model_bundle
├── routes.py            # /forecasting/train, /forecasting/predict
├── schemas.py           # TrainRequest, PredictRequest, ModelConfigBase + subtypes
├── service.py           # ForecastingService (train pulls feature_columns into bundle.metadata)
└── tests/
    ├── test_lightgbm_forecaster.py
    ├── test_xgboost_forecaster.py
    ├── test_prophet_like_forecaster.py
    ├── test_regression_forecaster.py
    ├── test_routes.py
    └── test_service.py

app/features/registry/
├── models.py            # ModelRun, DeploymentAlias ORM
├── routes.py            # /registry/runs CRUD, /verify, /aliases
├── schemas.py           # RunCreate, RunResponse (alias="model_config"), RunCompareResponse
├── service.py           # RegistryService, runtime_info capture
└── tests/
    ├── test_routes.py
    └── test_service.py

frontend/src/
├── components/
│   ├── common/
│   │   ├── json-block.tsx
│   │   └── status-badge.tsx
│   ├── charts/
│   │   ├── revenue-bar-chart.tsx
│   │   └── ... (kpi-card, multi-series-chart, time-series-chart)
│   └── explainability/
│       ├── explanation-panel.tsx
│       └── explanation-panel.test.tsx
├── hooks/
│   ├── use-explanations.ts
│   └── use-runs.ts
├── pages/
│   ├── explorer/
│   │   ├── runs.tsx
│   │   ├── run-detail.tsx
│   │   └── run-compare.tsx
│   └── visualize/
│       ├── forecast.tsx
│       └── backtest.tsx
└── types/api.ts
```

### Desired Codebase tree (additions)

```text
app/core/
└── exceptions.py         # MODIFIED — adds UnprocessableEntityError(ForecastLabError) for 422 resource-state path

app/features/forecasting/
├── feature_metadata.py   # NEW — extract_feature_importance(); ModelFamily classifier; importance_type_for()
├── routes.py             # MODIFIED — adds GET /forecasting/runs/{run_id}/feature-metadata + GET /forecasting/jobs/{job_id}/feature-metadata
├── schemas.py            # MODIFIED — adds FeatureImportanceItem, FeatureMetadataResponse, ModelFamily
└── tests/
    ├── test_feature_metadata.py            # NEW — unit tests for extract_feature_importance
    └── test_routes_feature_metadata.py     # NEW — route tests for BOTH endpoints (200, 400, 404, 422 paths)

app/features/registry/
└── schemas.py            # MODIFIED — adds model_family computed field to RunResponse

frontend/src/
├── components/
│   ├── common/
│   │   ├── model-family-badge.tsx          # NEW
│   │   └── model-family-badge.test.tsx     # NEW — closes test-requirements.md gap (M3)
│   └── explainability/
│       ├── feature-importance-panel.tsx    # NEW
│       └── feature-importance-panel.test.tsx  # NEW
├── hooks/
│   └── use-feature-metadata.ts             # NEW — exports useRunFeatureMetadata + useJobFeatureMetadata
├── pages/
│   ├── explorer/
│   │   ├── runs.tsx                        # MODIFIED — column + allow-list
│   │   ├── run-detail.tsx                  # MODIFIED — badge + cards
│   │   └── run-compare.tsx                 # MODIFIED — family row + side-by-side
│   └── visualize/
│       ├── forecast.tsx                    # MODIFIED — collapsible panel
│       └── backtest.tsx                    # MODIFIED — MODEL_OPTIONS allow-list
└── types/api.ts                            # MODIFIED — new types

docs/user-guide/
├── dashboard-guide.md    # MODIFIED — one-line cross-link
└── feature-reference.md  # MODIFIED — new "Advanced Model Metadata" subsection
```

### Files to MODIFY

| Path | What changes |
|------|--------------|
| `app/core/exceptions.py` | + `UnprocessableEntityError(ForecastLabError)` class (status_code=422, code="UNPROCESSABLE_ENTITY") |
| `app/features/forecasting/feature_metadata.py` | NEW — `extract_feature_importance`, `model_family_for(model_type)`, `importance_type_for` |
| `app/features/forecasting/routes.py` | + `GET /forecasting/runs/{run_id}/feature-metadata` AND + `GET /forecasting/jobs/{job_id}/feature-metadata`; doc-string drift fix (lines 33-37) |
| `app/features/forecasting/schemas.py` | + `ModelFamily` enum, `FeatureImportanceItem`, `FeatureMetadataResponse` |
| `app/features/forecasting/service.py` | + `get_feature_metadata_for_run` AND `get_feature_metadata_for_job` methods |
| `app/features/forecasting/tests/test_feature_metadata.py` | NEW — unit tests for the extractor |
| `app/features/forecasting/tests/test_routes_feature_metadata.py` | NEW — route tests |
| `app/features/registry/schemas.py` | + `model_family` computed field on `RunResponse` |
| `app/features/registry/tests/test_schemas.py` | + tests for the computed field |
| `frontend/src/types/api.ts` | + types: `ModelFamily`, `FeatureImportanceItem`, `FeatureMetadataResponse`; extend `ModelRun` |
| `frontend/src/lib/api.ts` | (no change — generic `api<T>()` already handles the new endpoint) |
| `frontend/src/hooks/use-feature-metadata.ts` | NEW |
| `frontend/src/components/common/model-family-badge.tsx` | NEW |
| `frontend/src/components/common/model-family-badge.test.tsx` | NEW — closes test-requirements gap flagged by prp-quality-agent |
| `frontend/src/components/explainability/feature-importance-panel.tsx` | NEW |
| `frontend/src/components/explainability/feature-importance-panel.test.tsx` | NEW |
| `frontend/src/pages/explorer/runs.tsx` | + `model_family` column, MODEL_TYPES allow-list extension, csvColumns update |
| `frontend/src/pages/explorer/run-detail.tsx` | + `<ModelFamilyBadge>` in profile, "Feature Metadata" card, `<FeatureImportancePanel>` |
| `frontend/src/pages/explorer/run-compare.tsx` | + "Family" row in profile; new collapsible side-by-side panel card |
| `frontend/src/pages/visualize/forecast.tsx` | + collapsible importance panel tied to train run |
| `frontend/src/pages/visualize/backtest.tsx` | + MODEL_OPTIONS allow-list extension |
| `docs/user-guide/feature-reference.md` | + "Advanced Model Metadata" subsection |
| `docs/user-guide/dashboard-guide.md` | + one-line cross-link |

### DECISIONS LOCKED

1. **[DECISION LOCKED] No new column on `model_run`; no Alembic migration.**
   The MLZOO-D surface is read-only and additive. Feature columns live in
   `bundle.metadata` already (`service.py:233-238`); feature importance lives
   on the fitted estimator object. Lazy extraction via a new endpoint that
   `load_model_bundle()`s the artifact is exactly the pattern `/verify`
   already uses. A migration would add a backfill story we do not need.

2. **[DECISION LOCKED] Endpoint lives in the forecasting slice, not registry.**
   `GET /forecasting/runs/{run_id}/feature-metadata` — not `/registry/runs/...`.
   The forecasting slice OWNS the bundle format (it knows about `ModelBundle`,
   the four feature-aware classes, and the `coef_` vs `feature_importances_`
   branch). Putting the endpoint in registry would require either a cross-slice
   import of `forecasting.persistence` or duplicate bundle-deserialization
   code. The new forecasting → registry import (calling `RegistryService.get_run`
   from within forecasting) is itself NEW — `app/features/forecasting/` does
   not import from `app/features/registry/` today. The precedent for this
   read-only direction lives in `app/features/explainability/service.py:57`
   (`from app.features.registry.models import ModelRun` — read-only data
   contract; see the module docstring for the rationale). Mirror that
   pattern: import `RegistryService` (or `ModelRun` directly) read-only
   and never call mutating registry methods from forecasting. The reverse
   direction (registry → forecasting) does not exist and we are not
   introducing it, so the import graph stays one-way.

3. **[DECISION LOCKED] `model_family` is computed, not persisted.**
   A Pydantic `@computed_field` (or `model_validator(mode="after")`) on
   `RunResponse` derives `model_family` from `model_type` at serialization
   time. No DB column, no migration, no backfill. Future model families
   require updating one map in `feature_metadata.py` and one enum in
   `forecasting/schemas.py`; existing rows pick up the new value
   automatically on next read.

4. **[DECISION LOCKED] One panel, two display modes.**
   `<FeatureImportancePanel>` renders BOTH tree-model positive-only bars AND
   prophet_like signed coefficients. The mode is selected by the
   `kind: "tree" | "linear_coef"` field on each `FeatureImportanceItem`.
   Two separate components would force every consumer page to know the
   family up-front before rendering — duplicating the family map and
   coupling the panel to the model taxonomy. One component reads `kind`
   and labels axes / colors accordingly.

5. **[DECISION LOCKED] No SHAP, no LIME, no permutation-importance recompute.**
   PRP-28 explicitly defers SHAP to its own future PRP + ADR (PRP-28 §
   "Adding SHAP later needs its own PRP + ADR"). MLZOO-D surfaces only
   what the trained estimator already exposes as a first-class attribute
   (`.feature_importances_`, `.coef_`). Permutation importance on hold-out
   would require a feature frame and a leakage-safe split — a substantially
   larger surface that belongs in a follow-on PRP.

6. **[DECISION LOCKED] No agent-tool exposure of feature importance in MLZOO-D.**
   The chat agent's tool surface (`app/features/agents/tools/*`) is OUT OF
   SCOPE. Exposing feature importance to the experiment agent is its own
   decision: it changes the surface the human-in-the-loop approval gate
   guards, and the conversational ergonomics need their own design. Defer
   to a separate PRP (`agents`-scoped).

7. **[DECISION LOCKED] Backtest viz extension is allow-list-only.**
   Extending `MODEL_OPTIONS` in `backtest.tsx` is the bare minimum to let
   operators run feature-aware backtests from the UI (B.2 made the backend
   ready). Per-model side-by-side fold comparison, multi-family ranking,
   and per-fold feature-importance heatmaps are explicitly OUT OF SCOPE —
   they are full features in their own right, not a polish PRP's surface.

8. **[DECISION LOCKED] Cross-slice run-compare is read-only.**
   When two compared runs have different `model_family`, the compare page
   shows a single "cross-family comparison not supported" message in the
   feature-importance card — it does NOT render two panels with a "doesn't
   make sense" warning, and it does NOT auto-rank features by some shared
   abstract measure. Cross-family metric comparison (MAE, sMAPE) still works
   in the existing metrics-diff card because those metrics are absolute.

### Known Gotchas

```python
# CRITICAL: LightGBM and XGBoost extras are OPTIONAL.
# pyproject.toml's [project.optional-dependencies] gates lightgbm / xgboost
# behind ml-lightgbm and ml-xgboost extras. The ForecastLabAI wrapper class
# (LightGBMForecaster / XGBoostForecaster) is unconditionally importable —
# the lazy `import lightgbm as lgb` / `import xgboost as xgb` lives inside
# fit() at models.py:704, 861, wrapped in try/except since v0.2.16 PR #253.
#
# BUT the joblib bundle for a lightgbm/xgboost run contains the
# scikit-learn-compatible *estimator* (LGBMRegressor / XGBRegressor)
# pickled. `joblib.load(bundle_path)` deserializes that estimator and
# CAN raise `ModuleNotFoundError: No module named 'lightgbm'` (or xgboost)
# at unpickle time, BEFORE control returns to extract_feature_importance.
#
# Handle this at the route boundary: wrap `load_model_bundle(...)` in
# `try/except ModuleNotFoundError as exc → raise
# UnprocessableEntityError(f"Model artifact requires the {pkg} extra; reinstall with --extra ml-{pkg}") from exc`.
# The 422 surfaces a clear remediation hint to the operator; do NOT 500.
#
# extract_feature_importance itself MUST not import lightgbm / xgboost at
# module scope. It branches on `isinstance(model, LightGBMForecaster)` etc.
# — those forecaster wrapper classes are always importable. Reading
# `.feature_importances_` off the (already-unpickled) estimator instance
# does NOT require re-importing the library.

# CRITICAL: ProphetLikeForecaster.coef_ lives at `pipeline.named_steps["ridge"].coef_`,
# NOT at `model.coef_`. The model attribute is the wrapper class; `.coef_`
# requires drilling into the sklearn Pipeline. The forecaster already does
# this for its decompose() method (models.py:1094-1098) — mirror that code
# path; do not re-implement.

# CRITICAL: LGBMRegressor.feature_importances_ default importance_type is
# "split" (integer counts of splits per feature). For dashboarding "what
# drove the model", "gain" is more useful — but changing the default would
# alter the persisted contract. MLZOO-D documents whatever the trained
# estimator exposes by reading model.booster_.params.get("importance_type")
# when present and falling back to "split" in the response JSON. We do NOT
# override the default at training time in this PRP.

# CRITICAL: RunResponse uses Pydantic v2 aliases.
# model_config_data is the internal attribute name; alias="model_config" is
# the wire field name (registry/schemas.py:117-118). A new computed_field
# named "model_family" must NOT collide with an existing alias and MUST
# include `ConfigDict(populate_by_name=True)` propagation. Test by JSON-
# serializing a RunResponse and asserting both "model_config" and
# "model_family" appear as top-level keys.

# CRITICAL: FastAPI strict-mode policy applies to REQUEST bodies, not responses.
# `FeatureMetadataResponse` is a response model; its date/datetime fields (if
# any are added later) do not need Field(strict=False, ...). See
# docs/_base/SECURITY.md § "Pydantic v2 strict mode on FastAPI request bodies".

# GOTCHA: load_model_bundle resolves paths against `forecast_model_artifacts_dir`.
# persistence.py:136 accepts `path: str | Path, base_dir: str | Path | None = None`.
# Pass `base_dir=settings.forecast_model_artifacts_dir` explicitly so the
# resolver's path-traversal guard applies (security-patterns.md §
# "File operations" requires canonicalization at boundaries). The existing
# /forecasting/predict call site at service.py:365 canonicalizes upstream
# instead — that pattern is NOT the one to mirror here; this endpoint
# receives only the run_id (or job_id) and never trusts an arbitrary path
# from the user, so the base_dir form is both safer and shorter.

# GOTCHA: model_run.status state machine is pending → running → success | failed → archived.
# A run with status=archived but a still-existing artifact CAN have its
# feature-metadata extracted. Return 200 for archived; return 422 only for
# pending / running / failed (which have no usable artifact). Document this
# in the route docstring so it's clear the gate is "is there a usable
# artifact", not "is this the current alias".

# GOTCHA: TanStack Query keys must include runId so cache doesn't leak between runs.
# Mirror `['explanations', 'run', runId]` (use-explanations.ts:11) with
# `['feature-metadata', runId]`. retry: false because 400 / 422 are final answers.

# GOTCHA: ApiError 400 vs 422 surfacing in the panel.
# 400 = "this run's family doesn't support feature importance" — render
# neutral muted message ("Feature importance is available for tree and
# additive models only.").
# 422 = "this run has no usable artifact yet" — render the same neutral
# style but a different message ("Feature importance is available once
# training completes and the model artifact is saved.").
# 404 / 5xx = render destructive (red) ErrorDisplay.
# Mirror the if-branch shape from explanation-panel.tsx:104-125.

# GOTCHA: Run-compare cross-family — DO render the card, DO NOT fetch.
# When run_a.model_family !== run_b.model_family, render the new collapsible
# card with a single-line muted message inside ("Feature-importance
# comparison is only meaningful when both runs share a model family.").
# Call useRunFeatureMetadata with `enabled: false` for both to avoid the
# requests altogether. This keeps the page deterministic and avoids
# triggering a 400 burst that would clutter the network tab.

# GOTCHA: pnpm test --run is the right CI invocation (vitest run).
# `pnpm test` (no --run) starts watch mode and hangs CI. package.json:11
# defines `"test": "vitest run"` so plain `pnpm test` works locally, but
# the validation gate must use `pnpm test --run` to be unambiguous.
```

## Implementation Blueprint

### Data models

```python
# app/features/forecasting/schemas.py — additions

from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ModelFamily(str, Enum):
    """Classifier for advanced-model UI surfacing.

    Derived from model_type; not persisted in the DB. Surfaced on RunResponse
    via a computed field and consumed by the dashboard for the family Badge
    and the feature-importance panel routing.
    """

    BASELINE = "baseline"   # naive, seasonal_naive, moving_average
    TREE = "tree"           # regression (HistGBR), lightgbm, xgboost
    ADDITIVE = "additive"   # prophet_like (Ridge pipeline)


class FeatureImportanceItem(BaseModel):
    """One row of model-derived feature importance, ready for the dashboard."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Canonical feature column name (e.g. 'lag_7').")
    importance: float = Field(
        ...,
        description=(
            "For tree models: estimator.feature_importances_ value "
            "(non-negative). For additive models: pipeline.named_steps['ridge'].coef_ "
            "value (signed; the sign carries directional information)."
        ),
    )
    kind: Literal["tree", "linear_coef"] = Field(
        ...,
        description="Determines display semantics: 'tree' → magnitude bar; "
                    "'linear_coef' → signed bar with direction icon.",
    )
    rank: int = Field(..., ge=1, description="1-indexed rank by |importance| desc.")


class FeatureMetadataResponse(BaseModel):
    """The /forecasting/runs/{run_id}/feature-metadata response."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    model_type: str
    model_family: ModelFamily
    feature_columns: list[str] = Field(
        ...,
        description="The canonical feature frame the model consumed at training time. "
                    "Always 14 columns for v0.2.16 feature-aware models (see "
                    "app/shared/feature_frames/contract.py:80).",
    )
    features: list[FeatureImportanceItem] = Field(
        ...,
        description="Sorted by |importance| descending; len == len(feature_columns).",
    )
    importance_type: str | None = Field(
        default=None,
        description="For LightGBM/XGBoost: the booster's importance_type "
                    "('split' / 'gain' / 'weight' / 'cover' depending on the lib's "
                    "default). For HistGBR: 'permutation'. For prophet_like: 'ridge_coef'. "
                    "Always populated so consumers know what the numbers mean.",
    )
```

```python
# app/features/registry/schemas.py — addition (around line 109-138)

from app.features.forecasting.schemas import ModelFamily

class RunResponse(BaseModel):
    # ... existing fields unchanged ...

    @computed_field  # type: ignore[prop-decorator]
    @property
    def model_family(self) -> ModelFamily:
        """Derived from model_type. See app/features/forecasting/feature_metadata.py
        for the canonical map. Unknown types log a warning and return BASELINE."""
        from app.features.forecasting.feature_metadata import model_family_for
        return model_family_for(self.model_type)
```

### Tasks (dependency-ordered)

```yaml
# ════════ STEP 1 — Backend foundation: extractor + family classifier ════════

Task 1 — CREATE app/features/forecasting/feature_metadata.py:
  - PURPOSE: pure-function extraction; no I/O; no FastAPI; no DB.
  - DEFINE model_family_for(model_type: str) -> ModelFamily  (the map; unknown → BASELINE + logger.warning)
  - DEFINE extract_feature_importance(model, feature_columns) -> list[FeatureImportanceItem]
      - isinstance check on the four feature-aware classes (import them locally)
      - branch on (LightGBM | XGBoost | Regression) → .feature_importances_, kind="tree"
      - branch on ProphetLike → pipeline.named_steps["ridge"].coef_, kind="linear_coef"
      - else → raise ValueError("model_type 'X' is not feature-aware")
      - sort by abs(importance) desc; assign rank 1..N
  - DEFINE importance_type_for(model) -> str | None  (LightGBM booster.params['importance_type'] or default; HistGBR → "permutation"; ProphetLike → "ridge_coef")
  - VALIDATE: uv run ruff check app/features/forecasting/feature_metadata.py
  - VALIDATE: uv run mypy app/features/forecasting/feature_metadata.py
  - VALIDATE: uv run pyright app/features/forecasting/feature_metadata.py

Task 2 — CREATE app/features/forecasting/tests/test_feature_metadata.py:
  - PURPOSE: unit-test the extractor with concrete fitted instances of each class.
  - MIRROR pattern from: app/features/forecasting/tests/test_lightgbm_forecaster.py
  - FIXTURES: small synthetic (y, X) frames; fit each forecaster; assert:
      - LightGBM/XGBoost/Regression: every importance >= 0; sum > 0; len == len(feature_columns); rank monotonically increasing
      - ProphetLike: at least one negative coefficient possible; sign is preserved; |coef| sort still produces correct ranks
      - Unknown model class → ValueError with substring "not feature-aware"
      - model_family_for: every Literal in ModelType maps to exactly one family
  - VALIDATE: uv run pytest -v app/features/forecasting/tests/test_feature_metadata.py

# ════════ STEP 2 — Backend schemas + route ════════

Task 3 — MODIFY app/features/forecasting/schemas.py:
  - ADD ModelFamily enum (str, Enum)
  - ADD FeatureImportanceItem, FeatureMetadataResponse (definitions in Data Models above)
  - PRESERVE all existing exports
  - VALIDATE: uv run mypy app/features/forecasting/schemas.py

Task 4 — MODIFY app/features/registry/schemas.py:
  - IMPORT ModelFamily from app.features.forecasting.schemas
  - ADD model_family computed_field on RunResponse (definition in Data Models above)
  - GOTCHA: ConfigDict already has populate_by_name=True (line 112); no change needed
  - ADD model_family to RunListResponse items via the same computed field (auto-propagates)
  - VALIDATE: uv run mypy app/features/registry/schemas.py
  - VALIDATE: uv run pyright app/features/registry/schemas.py

Task 5 — MODIFY app/features/registry/tests/test_schemas.py:
  - ADD test asserting RunResponse(...).model_dump()["model_family"] == ModelFamily.TREE for model_type="lightgbm"
  - ADD parametrized test covering all 7 model_types and the unknown case
  - VALIDATE: uv run pytest -v app/features/registry/tests/test_schemas.py

Task 6 — MODIFY app/features/forecasting/service.py:
  - ADD method ForecastingService.get_feature_metadata_for_run(run_id: str, db: AsyncSession) -> FeatureMetadataResponse
      - Look up the registry run via RegistryService.get_run(db, run_id)
      - If None → raise NotFoundError(f"Model run not found: {run_id}")  (NotFoundError already exists in app/core/exceptions.py and emits RFC 7807 404 via forecastlab_exception_handler)
      - If model_family_for(run.model_type) == ModelFamily.BASELINE → raise BadRequestError("Feature metadata is available for tree and additive families only; this run is a baseline model.")
      - If run.artifact_uri is None or run.status not in ('success', 'archived') → raise UnprocessableEntityError("Run has no usable artifact yet; status={status}, artifact_uri={present|absent}")
      - Wrap `load_model_bundle(run.artifact_uri, base_dir=settings.forecast_model_artifacts_dir)` in try/except (ModuleNotFoundError, FileNotFoundError) → raise UnprocessableEntityError:
          - ModuleNotFoundError → "Model artifact requires the ml-{pkg} extra; reinstall the backend with the extra enabled." (See "Optional ML extras" gotcha)
          - FileNotFoundError → "Model artifact file is missing from disk: {path}. The registry row references an artifact that has been deleted or moved." (Same 422 type URI; the registry row is stale but the request shape is valid.)
      - feature_columns = bundle.metadata["feature_columns"]  (always populated for feature-aware bundles per service.py:233-238)
      - features = extract_feature_importance(bundle.model, feature_columns)
      - importance_type = importance_type_for(bundle.model)
      - return FeatureMetadataResponse(run_id=run.run_id, model_type=run.model_type, model_family=model_family_for(run.model_type), feature_columns=feature_columns, features=features, importance_type=importance_type)
  - ADD method ForecastingService.get_feature_metadata_for_job(job_id: str, db: AsyncSession) -> FeatureMetadataResponse
      - PURPOSE: mirror PRP-28's /explain/jobs/{job_id} shape — forecast.tsx only has the job_id; trainJob.result.run_id is the **artifact key** (uuid.uuid4().hex[:12], see service.py:270), NOT the registry UUID
      - Look up the job via JobsService.get_job(db, job_id)
      - If None → raise NotFoundError(f"Job not found: {job_id}")
      - If job.job_type != 'train' or job.status != 'completed' → raise BadRequestError("Feature metadata can only be derived from a completed train job; got job_type={...}, status={...}")
      - bundle_path_str = job.result.get("model_path")  (CRITICAL: use the `model_path` field, NOT `run_id`. `_execute_train` in jobs/service.py:517 already populates `model_path` with the full path including `.joblib` suffix. Reconstructing the path from `run_id` would fail because `load_model_bundle` (persistence.py:154,173) calls `path.exists()` verbatim — it does NOT auto-inject `.joblib` like `save_model_bundle` does (persistence.py:88-89))
      - If not bundle_path_str → raise UnprocessableEntityError("Train job result missing model_path; job may have failed mid-write")
      - bundle_path = Path(bundle_path_str)
      - Wrap `load_model_bundle(bundle_path, base_dir=settings.forecast_model_artifacts_dir)` in the same try/except (ModuleNotFoundError, FileNotFoundError) → UnprocessableEntityError pair as above (same messages, FileNotFoundError especially likely on the job-keyed path because predict-job cleanup or manual `rm` of stale artifacts is common while the job row lives on)
      - Derive model_type from bundle.config.model_type
      - If model_family_for(bundle.config.model_type) == ModelFamily.BASELINE → raise BadRequestError(...)  (same message as above)
      - Same extraction path; the response's `run_id` field is populated with the **artifact key** parsed from the bundle path stem (documented in the FeatureMetadataResponse field description; consumers MUST NOT treat this as a registry UUID when the source is a job)
  - PRESERVE: every existing public method on ForecastingService
  - VALIDATE: uv run mypy app/features/forecasting/service.py
  - VALIDATE: uv run pyright app/features/forecasting/service.py

Task 6.5 — MODIFY app/core/exceptions.py:
  - PURPOSE: the v0.2.16 PR #253 hygiene fix forbids `HTTPException(422, "raw string")`; the existing ForecastLabError subclasses cover 400/404/409/422-Pydantic/500 but NOT 422-resource-state. Add one.
  - ADD: class UnprocessableEntityError(ForecastLabError) with status_code=422, code="UNPROCESSABLE_ENTITY", error_type_uri matching the ERROR_TYPES["UNPROCESSABLE_ENTITY"] convention (add the constant if not present)
  - VERIFY: forecastlab_exception_handler already serializes ForecastLabError subclasses to application/problem+json (it does — that's the whole pattern); no handler wiring needed
  - NB: do NOT collide semantics with the existing ValidationError (status_code=422, code="VALIDATION_ERROR") — that one is for Pydantic input failures. UnprocessableEntityError is for "request is well-formed but the resource is in a state where the operation can't proceed" (no artifact, missing optional extra, etc.). Different `code` → different `type` URI → consumers can disambiguate.
  - VALIDATE: uv run mypy app/core/exceptions.py
  - VALIDATE: uv run pytest -v app/core/tests/  (existing exception tests must still pass)

Task 7 — MODIFY app/features/forecasting/routes.py:
  - ADD GET /forecasting/runs/{run_id}/feature-metadata
      - response_model=FeatureMetadataResponse
      - dependency: db = Depends(get_db)
      - body: `return await service.get_feature_metadata_for_run(run_id, db)`
      - Do NOT wrap with try/except in the route — let the ForecastLabError subclasses (NotFoundError 404, BadRequestError 400, UnprocessableEntityError 422) flow straight through to forecastlab_exception_handler which serializes them as application/problem+json. Mirror the shape of `/explain/runs/{run_id}` (app/features/explainability/routes.py:108-121) — that endpoint does the same thing (catches only ValueError → BadRequestError and SQLAlchemyError → DatabaseError).
      - DO catch SQLAlchemyError → DatabaseError for DB-level surprise paths (mirror explainability/routes.py:113-118).
  - FIX doc-string drift at lines 33-37: list xgboost, regression, prophet_like alongside lightgbm in the /forecasting/train description
  - VALIDATE: uv run mypy app/features/forecasting/routes.py
  - VALIDATE: uv run pyright app/features/forecasting/routes.py

Task 7.5 — ADD sibling endpoint in app/features/forecasting/routes.py:
  - PURPOSE: forecast.tsx has only the job_id, not a registry run_id. The Critical-fix flagged by prp-quality-agent.
  - ADD GET /forecasting/jobs/{job_id}/feature-metadata
      - response_model=FeatureMetadataResponse
      - body: `return await service.get_feature_metadata_for_job(job_id, db)`
      - Same exception-flow contract as Task 7 (no try/except in the route except SQLAlchemyError → DatabaseError; the ForecastLabError subclasses flow through to the RFC 7807 handler).
      - Docstring: cite PRP-28's `/explain/jobs/{job_id}` (app/features/explainability/routes.py:124) as the structural twin so future maintainers see the pair.
  - VALIDATE: uv run mypy app/features/forecasting/routes.py

Task 8 — CREATE app/features/forecasting/tests/test_routes_feature_metadata.py:
  - MIRROR pattern from: app/features/explainability/tests/test_routes.py (PRP-28 already shipped the /explain/runs/{id} + /explain/jobs/{id} test pair — copy the structure)
  - CASES (cover BOTH endpoints — same matrix for each):
      - 200 success for a fitted LightGBM run (assert content-type, sorted importances, kind='tree', importance_type populated)
      - 200 success for a fitted ProphetLike run (assert at least one negative coefficient renders intact, kind='linear_coef', importance_type='ridge_coef')
      - 400 application/problem+json for a baseline run / a non-train job (assert content-type = application/problem+json, type URI is BAD_REQUEST, detail contains "baseline" or "train job")
      - 404 application/problem+json for unknown run_id / job_id (type URI is NOT_FOUND)
      - 422 application/problem+json for pending / running / failed run; for an artifact_uri = None on a success-status run; for a ModuleNotFoundError during load_model_bundle (mock joblib.load to raise); for a FileNotFoundError during load_model_bundle (point artifact_uri at a non-existent path, or set job.result["model_path"] to a path the artifacts dir doesn't contain) — type URI is UNPROCESSABLE_ENTITY (NOT the existing VALIDATION_ERROR)
      - 422 specifically for the job endpoint: a train job in `pending` / `failed` status returns 400 (not a completed train), and a `predict` job returns 400 (wrong job_type)
  - VALIDATE: uv run pytest -v app/features/forecasting/tests/test_routes_feature_metadata.py
  - VALIDATE: uv run pytest -v -m integration app/features/forecasting/tests/test_routes_feature_metadata.py

# ════════ STEP 3 — Frontend types + hook + panel ════════

Task 9 — MODIFY frontend/src/types/api.ts:
  - ADD around line 170:
      export type ModelFamily = 'baseline' | 'tree' | 'additive'
  - EXTEND ModelRun interface to include `model_family: ModelFamily`
  - ADD after the ModelRun group:
      export interface FeatureImportanceItem {
        name: string
        importance: number
        kind: 'tree' | 'linear_coef'
        rank: number
      }
      export interface FeatureMetadataResponse {
        run_id: string
        model_type: string
        model_family: ModelFamily
        feature_columns: string[]
        features: FeatureImportanceItem[]
        importance_type: string | null
      }
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task 10 — CREATE frontend/src/hooks/use-feature-metadata.ts:
  - MIRROR verbatim from: frontend/src/hooks/use-explanations.ts:10-17 (useRunExplanation pattern)
  - Export TWO sibling hooks (mirroring useRunExplanation + useJobExplanation from PRP-28):
      1. useRunFeatureMetadata(runId: string, enabled = true)
         - Query key: ['feature-metadata', 'run', runId]
         - URL: `/forecasting/runs/${runId}/feature-metadata`
         - retry: false (400/404/422 are all final answers)
      2. useJobFeatureMetadata(jobId: string, enabled = true)
         - Query key: ['feature-metadata', 'job', jobId]
         - URL: `/forecasting/jobs/${jobId}/feature-metadata`
         - retry: false
  - Both return useQuery<FeatureMetadataResponse>; both gated by `enabled && !!{id}` exactly like useRunExplanation
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task 11 — CREATE frontend/src/components/common/model-family-badge.tsx:
  - PURPOSE: pure derivation; no hooks
  - export function ModelFamilyBadge({ family }: { family: ModelFamily }) — returns shadcn <Badge variant={...}> with:
      baseline → 'secondary'; tree → 'default'; additive → 'outline'
  - Use Lucide icons (TreePine for tree, LineChart for additive, Activity for baseline) at h-3 w-3 with the existing flex-gap pattern from StatusBadge
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task 11.5 — CREATE frontend/src/components/common/model-family-badge.test.tsx:
  - PURPOSE: closes the test-requirements.md gap flagged by prp-quality-agent (M3).
  - MIRROR scaffolding from: frontend/src/components/explainability/explanation-panel.test.tsx
  - CASES (3 trivial):
      - renders 'tree' family with the expected variant text + TreePine icon
      - renders 'additive' family with the LineChart icon
      - renders 'baseline' family with the Activity icon + 'secondary' variant
  - VALIDATE: cd frontend && pnpm test --run src/components/common/model-family-badge.test.tsx

Task 12 — CREATE frontend/src/components/explainability/feature-importance-panel.tsx:
  - MIRROR layout from: frontend/src/components/explainability/explanation-panel.tsx
  - PanelShell variant: title "Feature Importance", description tied to family ("Tree-based gain importance (model-derived)." | "Ridge regression coefficients (signed; sign indicates direction).")
  - Body: ordered list of features (use Card + a flex list, OR re-use recharts via a thin wrapper — KEEP IT SIMPLE: a CSS-grid table is acceptable; do not introduce a new chart dependency)
      - For kind='tree': horizontal bar with width = (importance / max) × 100%, neutral color
      - For kind='linear_coef': horizontal bar with width = (|coef| / max) × 100%, color by sign (text-success for positive, text-destructive for negative), TrendingUp/TrendingDown icon
      - Show feature name (mono font, w-40 left-aligned), bar, numeric value (right-aligned, w-20)
  - Caveat footer (border-top, text-muted-foreground): "Importance is model-derived. It reflects how much each feature reduced training error — not real-world causation."
  - Error handling:
      - 400 → neutral muted Info card with "Feature importance is available for tree and additive model families only."
      - 422 → neutral muted Info card with "Feature importance is available once training completes and the artifact is saved."
      - 404 / 5xx → destructive AlertTriangle ErrorDisplay
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task 13 — CREATE frontend/src/components/explainability/feature-importance-panel.test.tsx:
  - MIRROR scaffolding from: frontend/src/components/explainability/explanation-panel.test.tsx:1-66
  - FIXTURES: sampleTreeImportance (kind='tree', 14 items), sampleLinearCoef (kind='linear_coef', 14 items including 2 negative)
  - CASES:
      - renders tree items with positive bars
      - renders linear items with signed colors and direction icons
      - loading state
      - 400 → neutral baseline message
      - 422 → neutral artifact-missing message
      - empty features list message
  - VALIDATE: cd frontend && pnpm test --run frontend/src/components/explainability/feature-importance-panel.test.tsx

# ════════ STEP 4 — Page wiring (additive, in-place) ════════

Task 14 — MODIFY frontend/src/pages/explorer/runs.tsx:
  - EXTEND line 21 MODEL_TYPES → ['naive', 'seasonal_naive', 'moving_average', 'regression', 'lightgbm', 'xgboost', 'prophet_like']
  - INSERT new ColumnDef after the model_type column (after line 47):
      {
        accessorKey: 'model_family',
        header: 'Family',
        enableSorting: false,
        cell: ({ row }) => <ModelFamilyBadge family={row.original.model_family} />,
      }
  - EXTEND csvColumns (line 83-92) with { key: 'model_family', header: 'Family' }
  - PRESERVE: all existing URL-param logic; the existing useRuns hook already returns model_family via the backend computed field
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task 15 — MODIFY frontend/src/pages/explorer/run-detail.tsx:
  - IMPORT ModelFamilyBadge, FeatureImportancePanel, useRunFeatureMetadata
  - In the profile card (lines 88-143), add a <ModelFamilyBadge family={run.model_family} /> immediately after the model_type Field cell
  - After the existing "Metrics" card (line 156-164), INSERT a new <Card> titled "Feature Metadata":
      - Only render when run.model_family !== 'baseline'
      - Feed by featureMetadata = useRunFeatureMetadata(runId, run.model_family !== 'baseline')
      - Body: list the 14 feature columns from featureMetadata.data?.feature_columns (use the existing list pattern; one-line per column, monospace, comma-separated chips OK)
      - Show featureMetadata.data?.importance_type at the bottom as a small muted tag
  - INSERT <FeatureImportancePanel data={featureMetadata.data} isLoading={featureMetadata.isLoading} error={featureMetadata.error} /> immediately below the existing <ExplanationPanel> (around line 170), gated by run.model_family !== 'baseline'
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task 16 — MODIFY frontend/src/pages/explorer/run-compare.tsx:
  - IMPORT ModelFamilyBadge, FeatureImportancePanel, useRunFeatureMetadata
  - In the Profile table (lines 145-213), add a new row labeled "Family" with two <ModelFamilyBadge> cells (run.run_a.model_family / run.run_b.model_family)
  - After the "Metrics diff" card (line 231-266), INSERT a new <Card> titled "Feature Importance" wrapping a <Collapsible> (default open):
      - sameFamily = run_a.model_family === run_b.model_family && run_a.model_family !== 'baseline'
      - When !sameFamily: render a single muted line ("Feature-importance comparison is only meaningful when both runs share a non-baseline family."); call useRunFeatureMetadata(_, enabled: false) for both
      - When sameFamily: render two <FeatureImportancePanel>s in a grid-cols-2 (md:grid-cols-2, base: grid-cols-1)
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task 17 — MODIFY frontend/src/pages/visualize/forecast.tsx:
  - CRITICAL: forecast.tsx has NO access to a registry run_id. `trainJob.result.run_id`
    (line 48-49) is the **forecast-artifact key** (uuid.uuid4().hex[:12], see
    forecasting/service.py:270) saved as `model_{id}.joblib`. It is NOT the
    registry model_run.run_id (full UUID). Calling
    `useRunFeatureMetadata(trainJob.result.run_id, …)` would 404 because the
    backend treats `{run_id}` as a registry UUID. This is the bug prp-quality-agent
    flagged (Critical #1) and the trap recorded in memory `scenario-run-id-vs-registry-run-id`.
  - CORRECT WIRING: use the job-based sibling hook + endpoint (Tasks 7.5 + 10).
  - IMPORT useJobFeatureMetadata, FeatureImportancePanel, ModelFamilyBadge from their respective new files. (Do NOT import useRun — it is not used in forecast.tsx today and is not needed: the job-based endpoint reads model_type / family from the bundle directly.)
  - Wire the panel keyed on the loaded predict job's source train job:
      const trainJobMetadata = useJobFeatureMetadata(trainJobId, !!trainJobId)
      const trainFamily = trainJobMetadata.data?.model_family ?? null
  - Below the existing <ExplanationPanel> for the predict job (lines 256-263), INSERT a <Collapsible defaultOpen={false}> containing:
      - Trigger: "Model details" + <ModelFamilyBadge family={trainFamily ?? 'baseline'} /> (the badge renders only when trainJobMetadata.data is populated, to avoid flashing 'baseline' before the fetch resolves)
      - Content: <FeatureImportancePanel data={trainJobMetadata.data} isLoading={trainJobMetadata.isLoading} error={trainJobMetadata.error} />
  - The panel's 400-handler will render the neutral message when the train job is a baseline model, so we do not gate the Collapsible's existence on family — TanStack Query handles the empty/error states.
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task 18 — MODIFY frontend/src/pages/visualize/backtest.tsx:
  - EXTEND MODEL_OPTIONS at line 52:
      [
        { value: 'naive', label: 'Naive' },
        { value: 'seasonal_naive', label: 'Seasonal Naive' },
        { value: 'moving_average', label: 'Moving Average' },
        { value: 'regression', label: 'Regression (HistGBR)' },
        { value: 'lightgbm', label: 'LightGBM' },
        { value: 'xgboost', label: 'XGBoost' },
        { value: 'prophet_like', label: 'Prophet-like (additive)' },
      ]
  - NO OTHER CHANGE in MLZOO-D (per DECISIONS LOCKED #7)
  - VALIDATE: cd frontend && pnpm tsc --noEmit

# ════════ STEP 5 — Docs ════════

Task 19 — MODIFY docs/user-guide/feature-reference.md:
  - ADD new ## section titled "Advanced Model Metadata"
  - One paragraph naming the families (baseline / tree / additive) and what the dashboard shows (badge, feature columns, importance / coefs)
  - One paragraph stating the correlation-vs-causation caveat VERBATIM (so support replies can quote it):
      "Feature importance is model-derived. It reflects how much each feature reduced the model's training error — not real-world causation. Two products with similar importance profiles are not necessarily driven by the same business factors."
  - Cross-link the relevant page sections (run detail, run compare, forecast viz)
  - VALIDATE: markdownlint-cli2 if installed; otherwise eyeball the rendered doc

Task 20 — MODIFY docs/user-guide/dashboard-guide.md:
  - ADD one-line cross-link to the new feature-reference section from the runs-explorer / run-detail discussion (find the appropriate H2)
  - VALIDATE: visual inspection

# ════════ STEP 6 — Browser dogfood (per .claude/rules/ui-design.md) ════════

Task 21 — DOGFOOD via the webapp-testing skill:
  - PRECONDITION: docker compose up -d && uv run alembic upgrade head && make demo (gives one each of naive / seasonal_naive / moving_average); then curl /forecasting/train with model_type=lightgbm (and optionally xgboost / prophet_like) against the same store/product to fill the four advanced families.
  - SCENARIO 1 — Runs explorer: filter by model_type=lightgbm; assert the Family column renders with the "tree" badge.
  - SCENARIO 2 — Run detail (lightgbm run): assert the Feature Metadata card lists the 14 columns; the importance panel renders 14 bars, sorted.
  - SCENARIO 3 — Run detail (baseline run): assert neither the Feature Metadata card nor the FeatureImportancePanel renders.
  - SCENARIO 4 — Run compare (two lightgbm runs): assert two panels render side by side.
  - SCENARIO 5 — Run compare (lightgbm vs naive): assert the cross-family muted message renders; assert no /feature-metadata requests fire (check network tab).
  - SCENARIO 6 — Forecast viz: select a completed train job whose model_type is lightgbm; expand the "Model details" collapsible; assert the FeatureImportancePanel renders importance bars from the new /forecasting/jobs/{job_id}/feature-metadata endpoint (NOT from /runs/.../). Check the Network tab to confirm the job-keyed URL is hit, not a 404-ing run-keyed URL.
  - SCENARIO 6b — Forecast viz, baseline train job: select a completed train job whose model_type is naive; expand the collapsible; assert the panel renders the neutral 400 message ("Feature importance is available for tree and additive model families only").
  - SCENARIO 7 — Backtest viz: pick "Prophet-like (additive)"; submit; assert the backtest completes and fold metrics render.
  - VALIDATE: capture screenshots for the PR review
```

### Per-task pseudocode (only where the task needs more than the YAML above)

```python
# Task 1 — extract_feature_importance (pure function)

from app.features.forecasting.models import (
    LightGBMForecaster, XGBoostForecaster,
    RegressionForecaster, ProphetLikeForecaster,
)

def extract_feature_importance(
    model: BaseForecaster,
    feature_columns: list[str],
) -> list[FeatureImportanceItem]:
    """Pure: no I/O, no FastAPI, no DB. Raises ValueError for non-feature-aware classes."""
    if isinstance(model, (LightGBMForecaster, XGBoostForecaster, RegressionForecaster)):
        raw = np.asarray(model._estimator.feature_importances_, dtype=np.float64)  # private attr by convention
        kind: Literal["tree", "linear_coef"] = "tree"
    elif isinstance(model, ProphetLikeForecaster):
        # MIRROR models.py:1094-1098 — drill into the Pipeline
        ridge = model._estimator.named_steps["ridge"]
        raw = np.asarray(ridge.coef_, dtype=np.float64)
        kind = "linear_coef"
    else:
        raise ValueError(f"model_type '{type(model).__name__}' is not feature-aware")

    if len(raw) != len(feature_columns):
        raise ValueError(
            f"feature_columns length mismatch: importance vector has {len(raw)} elements, "
            f"feature_columns has {len(feature_columns)}"
        )

    # Sort by absolute magnitude desc; preserve sign in the value for linear_coef.
    indices_by_magnitude = np.argsort(-np.abs(raw))
    items = [
        FeatureImportanceItem(
            name=feature_columns[i],
            importance=float(raw[i]),
            kind=kind,
            rank=rank,
        )
        for rank, i in enumerate(indices_by_magnitude, start=1)
    ]
    return items
```

```python
# Task 7 — /forecasting/runs/{run_id}/feature-metadata route

@router.get(
    "/runs/{run_id}/feature-metadata",
    response_model=FeatureMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract feature columns + learned importance for an advanced-model run",
    description="""
Returns the canonical 14-column feature frame the model consumed and the
fitted estimator's `feature_importances_` (tree models) or `coef_` (additive
prophet_like). Loads the saved joblib artifact lazily.

**Error semantics (RFC 7807 application/problem+json):**
- 400 — model_family is 'baseline' (no learned importance to extract)
- 404 — run_id not found
- 422 — run has no artifact_uri yet, status is pending/running/failed,
  or the bundle file is missing on disk (storage corruption)
""",
)
async def get_run_feature_metadata(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> FeatureMetadataResponse:
    # Mirror app/features/explainability/routes.py:108-121 — the service
    # raises ForecastLabError subclasses (NotFoundError / BadRequestError /
    # UnprocessableEntityError) directly; forecastlab_exception_handler
    # serializes each to application/problem+json with the right status.
    # Catch only the DB-layer surprise path; everything else flows through.
    service = ForecastingService(get_settings(), db)
    try:
        return await service.get_feature_metadata_for_run(run_id, db)
    except SQLAlchemyError as exc:
        logger.error("forecasting.feature_metadata_db_error", run_id=run_id, error=str(exc), exc_info=True)
        raise DatabaseError(
            message="Failed to load feature metadata",
            details={"error": str(exc)},
        ) from exc


@router.get(
    "/jobs/{job_id}/feature-metadata",
    response_model=FeatureMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract feature columns + learned importance for a completed train job",
    description="""
The job-keyed sibling of `/forecasting/runs/{run_id}/feature-metadata`,
exactly matching the shape of `/explain/jobs/{job_id}` (PRP-28). Use this
endpoint when the caller has only a `job_id` — for example, the dashboard's
forecast viz page (`frontend/src/pages/visualize/forecast.tsx`).

The route reads `job.result.run_id` (the **forecast-artifact key**, not a
registry UUID) and loads the bundle directly from
`{forecast_model_artifacts_dir}/model_{artifact_id}`.

**Error semantics (RFC 7807 application/problem+json):**
- 400 — the job is not a completed train job, or the trained model is baseline
- 404 — job_id not found
- 422 — bundle missing or ML extra not installed at unpickle time
""",
)
async def get_job_feature_metadata(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> FeatureMetadataResponse:
    service = ForecastingService(get_settings(), db)
    try:
        return await service.get_feature_metadata_for_job(job_id, db)
    except SQLAlchemyError as exc:
        logger.error("forecasting.feature_metadata_db_error", job_id=job_id, error=str(exc), exc_info=True)
        raise DatabaseError(
            message="Failed to load feature metadata",
            details={"error": str(exc)},
        ) from exc
```

```tsx
// Task 12 — FeatureImportancePanel (sketch; mirror explanation-panel.tsx layout)

export function FeatureImportancePanel({
  data,
  isLoading,
  error,
}: FeatureImportancePanelProps) {
  if (isLoading) return <PanelShell><LoadingState /></PanelShell>
  if (error) {
    const apiError = error instanceof ApiError ? error : null
    if (apiError?.status === 400) {
      return <NeutralMessage icon={Info} text="Feature importance is available for tree and additive model families only." />
    }
    if (apiError?.status === 422) {
      return <NeutralMessage icon={Info} text="Feature importance is available once training completes and the artifact is saved." />
    }
    return <ErrorDisplay error={error} />
  }
  if (!data) return null

  const maxAbs = Math.max(...data.features.map((f) => Math.abs(f.importance)))
  return (
    <PanelShell family={data.model_family}>
      <ol className="space-y-1">
        {data.features.map((f) => (
          <FeatureRow key={f.name} item={f} maxAbs={maxAbs} />
        ))}
      </ol>
      <CaveatFooter />
    </PanelShell>
  )
}
```

### Integration Points

```yaml
ROUTES:
  - add to: app/main.py
  - pattern: (no change — forecasting_router already registered at line 143; the new GET is a sub-route)

CONFIG:
  - no new env var
  - no change to .env.example

DATABASE:
  - no migration

PYDANTIC IMPORTS:
  - app/features/registry/schemas.py imports ModelFamily from app/features/forecasting/schemas.py
  - this is a downstream→upstream import: registry → forecasting
  - app/features/forecasting NEVER imports app/features/registry/schemas.py for ModelFamily
  - (NEW cross-slice import: app/features/forecasting/service.py imports RegistryService from app/features/registry/service.py for the new get_feature_metadata_for_run method. This direction is new to forecasting; it mirrors the read-only pattern already established in app/features/explainability/service.py:57 — see DECISIONS LOCKED #2.)

FRONTEND ROUTES:
  - no new React Router route — all changes are in-place page edits
```

## Validation Loop

### Level 0 — Environment

```bash
docker compose up -d
uv sync --extra dev --extra ml-lightgbm --extra ml-xgboost
uv run alembic upgrade head
cd frontend && corepack enable pnpm && pnpm install && cd ..
```

### Level 1 — Syntax & Style

```bash
uv run ruff check app/features/forecasting/feature_metadata.py \
                  app/features/forecasting/routes.py \
                  app/features/forecasting/schemas.py \
                  app/features/forecasting/service.py \
                  app/features/registry/schemas.py
uv run ruff format --check app/

cd frontend && pnpm lint && cd ..
```

### Level 2 — Type Checks

```bash
uv run mypy app/
uv run pyright app/

cd frontend && pnpm tsc --noEmit && cd ..
```

### Level 3 — Unit Tests

```bash
uv run pytest -v app/features/forecasting/tests/test_feature_metadata.py
uv run pytest -v app/features/forecasting/tests/test_routes_feature_metadata.py
uv run pytest -v app/features/registry/tests/test_schemas.py
uv run pytest -v -m "not integration"

cd frontend && pnpm test --run \
    frontend/src/components/explainability/feature-importance-panel.test.tsx \
  && cd ..
cd frontend && pnpm test --run && cd ..    # whole frontend suite
```

### Level 4 — Integration Tests

```bash
docker compose up -d
uv run pytest -v -m integration app/features/forecasting/tests/test_routes_feature_metadata.py
uv run pytest -v -m integration
```

### Level 5 — Manual Dogfood (per .claude/rules/ui-design.md)

```bash
# 1. Seed and train across all four feature-aware families
make demo                                         # naive / seasonal_naive / moving_average
curl -s -X POST localhost:8123/forecasting/train \
  -H 'content-type: application/json' \
  -d '{"store_id":1,"product_id":1,"train_start_date":"2024-01-01","train_end_date":"2024-06-30","model_config":{"model_type":"lightgbm"}}' | jq
# repeat with model_type in {"xgboost","regression","prophet_like"} (lightgbm/xgboost require the extras enabled in pyproject.toml)

# 2. Drive the dashboard with the webapp-testing skill
# (see Task 21 SCENARIOS 1-7 above)

# 3. Verify the new endpoint by hand
RUN_ID=$(curl -s 'localhost:8123/registry/runs?model_type=lightgbm&page_size=1' | jq -r '.runs[0].run_id')
curl -s "localhost:8123/forecasting/runs/${RUN_ID}/feature-metadata" | jq

JOB_ID=$(curl -s 'localhost:8123/jobs?job_type=train&status=completed&page_size=1' | jq -r '.jobs[0].job_id')
curl -s "localhost:8123/forecasting/jobs/${JOB_ID}/feature-metadata" | jq
```

## Final Validation Checklist

- [ ] `uv run ruff check .` clean
- [ ] `uv run ruff format --check .` clean
- [ ] `uv run mypy app/` clean
- [ ] `uv run pyright app/` clean
- [ ] `uv run pytest -v -m "not integration"` green
- [ ] `uv run pytest -v -m integration` green
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` green
- [ ] `GET /forecasting/runs/{run_id}/feature-metadata` returns 200 for one fitted run per family (LightGBM, XGBoost, regression, prophet_like)
- [ ] `GET /forecasting/jobs/{job_id}/feature-metadata` returns 200 for the same set of runs reached via their training job_id
- [ ] Both endpoints return RFC 7807 problem+json for 400 (baseline / wrong job_type), 404 (missing run/job), 422 (no artifact / missing ml-* extra)
- [ ] `GET /registry/runs/{run_id}` and `GET /registry/runs` both serialize `model_family` on every item (verify with `curl … | jq '.runs[0].model_family'`)
- [ ] Runs explorer Family column renders with the expected Badge variant for every model_type
- [ ] Run detail renders ModelFamilyBadge + Feature Metadata card + FeatureImportancePanel only when family != baseline
- [ ] Run compare renders side-by-side panels for same-family pairs and a muted single-line message for cross-family pairs (without firing requests)
- [ ] Forecast viz Collapsible expands to show the FeatureImportancePanel tied to the train run; collapses by default
- [ ] Backtest viz lets the user pick any of the seven model types and runs successfully on each (B.2's feature-aware split handles tree/additive correctly)
- [ ] No new Alembic migration in `alembic/versions/`
- [ ] No new dependency in `pyproject.toml` (LightGBM / XGBoost extras unchanged; no SHAP, no LIME)
- [ ] `docs/user-guide/feature-reference.md` contains the "Advanced Model Metadata" section with the verbatim correlation-vs-causation caveat
- [ ] `wc -l CLAUDE.md` ≤ 150 (no change expected in MLZOO-D)
- [ ] CHANGELOG entry will be auto-generated by release-please from the `feat(forecast,ui): …` commit on merge

## Anti-Patterns to Avoid

- ❌ **Do NOT add `model_family` as a real column on `model_run`.** Computed
  field on `RunResponse` is the locked design — see DECISIONS LOCKED #3. A
  column would force a migration and a backfill story we do not need.
- ❌ **Do NOT extend the existing `<ExplanationPanel>` to feature importance.**
  PRP-28 named it "rule-based driver attribution" deliberately. Build a
  sibling panel; tests stay isolated and the baseline-only 400 path stays
  meaningful — see DECISIONS LOCKED #4.
- ❌ **Do NOT introduce SHAP, LIME, or a permutation-importance recompute.**
  SHAP is explicitly deferred (PRP-28). Permutation-importance is a full
  feature (needs holdout splits, leakage proofs) — out of scope.
- ❌ **Do NOT add an agent tool that exposes feature importance** to the chat
  agent — that's a HITL approval-surface widening (`agent_require_approval`)
  and a separate PRP — see DECISIONS LOCKED #6.
- ❌ **Do NOT extend `backtest.tsx` beyond the MODEL_OPTIONS allow-list.**
  Per-fold per-model importance heatmaps, multi-family ranking — those are
  full features — DECISIONS LOCKED #7.
- ❌ **Do NOT use `verify=False`** on any HTTP client added here; no new
  external integration is needed (security-patterns.md hard rule).
- ❌ **Do NOT raise `HTTPException(400, "raw string")`** — every error path
  must flow through `BadRequestError` / `DatabaseError` / a 422 dedicated
  exception so the registered handler emits RFC 7807. PR #253 closed the
  last holes; do not reopen them.
- ❌ **Do NOT include a Co-Authored-By or "Generated with" trailer.**
  Hook `.claude/hooks/check-commit-format.sh` enforces this; do not bypass.
- ❌ **Do NOT touch `app/features/featuresets/tests/test_leakage.py`** to
  make any new test pass. It is the leakage spec.
- ❌ **Do NOT import `lightgbm` or `xgboost` at module scope** in
  `feature_metadata.py`. The extras are optional; importing at module load
  would break installs that don't have them, even though the
  `feature_metadata` module is loaded on every API startup. Read
  `.feature_importances_` off the unpickled object — no import required.
- ❌ **Do NOT pre-load `bundle.model` in `useRunFeatureMetadata` even when
  the family is baseline.** Pass `enabled: run.model_family !== 'baseline'`
  to TanStack Query so the request never fires; the panel renders nothing.
- ❌ **Do NOT raise `HTTPException(404, ...)` from the new route** — use
  `NotFoundError(message=...)` from `app/core/exceptions.py` (line 75
  precedent: `class NotFoundError(ForecastLabError): status_code = 404`).
  The handler at `forecastlab_exception_handler` emits the RFC 7807
  envelope. Plain `HTTPException` does NOT.
- ❌ **Do NOT reuse `ValidationError` for the 422 path.** The existing
  `ValidationError` (status_code=422, code="VALIDATION_ERROR") is for
  Pydantic input failures. The new `UnprocessableEntityError`
  (code="UNPROCESSABLE_ENTITY") signals "resource state prevents the
  operation" — a different semantic. Consumers and tests disambiguate via
  the `type` URI in the problem+json body.
- ❌ **Do NOT call `useRunFeatureMetadata(trainJob.result.run_id, ...)` from
  `forecast.tsx`.** That field is the **artifact key** (12-char hex), not a
  registry UUID. Use `useJobFeatureMetadata(trainJobId, ...)` instead. The
  job-based endpoint resolves the artifact path internally. Recorded in
  memory `[[scenario-run-id-vs-registry-run-id]]`.
- ❌ **Do NOT use `dangerouslySetInnerHTML`** anywhere — render
  `feature_columns` as plain text or chips.

## Open Questions — ALL RESOLVED

1. **Where does the endpoint live — registry or forecasting?**
   → forecasting (DECISIONS LOCKED #2). Forecasting owns the bundle format.
2. **Is `model_family` a DB column or a computed field?**
   → computed field (DECISIONS LOCKED #3). No migration, no backfill.
3. **One panel or two?**
   → one panel, branching on `kind` (DECISIONS LOCKED #4).
4. **Does MLZOO-D add SHAP / LIME?**
   → no, deferred (DECISIONS LOCKED #5; PRP-28 already deferred SHAP).
5. **Does MLZOO-D widen the agent's tool surface?**
   → no, deferred to a separate agents-scoped PRP (DECISIONS LOCKED #6).
6. **How far does backtest.tsx change?**
   → MODEL_OPTIONS allow-list only (DECISIONS LOCKED #7).
7. **What happens when run-compare's two runs differ in family?**
   → render a single muted message; no fetch (DECISIONS LOCKED #8).
8. **Does the panel show signed coefficients for prophet_like?**
   → yes; sign is preserved end-to-end (data model: `importance: float`
   signed; panel: green/red + direction icon when `kind === 'linear_coef'`).

## Confidence Score

**8 / 10** for one-pass implementation success (post-revision; prp-quality-agent
flagged two Critical issues in v1 — ID-namespace mismatch on `forecast.tsx` and
a `HTTPException(422)` anti-pattern that would have re-opened v0.2.16 PR #253's
hygiene fix. Both are now resolved by Tasks 6.5, 7.5, 10's two sibling hooks,
and the rewritten Task 17 + Anti-Patterns block).

Rationale: every backend mechanic this PRP surfaces is already shipped and
verified in v0.2.16 — the four feature-aware classes, the bundle metadata
write at train time, the `runtime_info` capture, the `load_model_bundle`
deserialization, and the `/verify` endpoint that this new endpoint mirrors.
The two-endpoint pair (`/runs/{id}` + `/jobs/{id}`) is a verbatim mirror of
PRP-28's `/explain/runs/{id}` + `/explain/jobs/{id}` split, which already
ships and is test-covered. Every error path flows through a `ForecastLabError`
subclass into `forecastlab_exception_handler` — no `HTTPException` in the
new code. The frontend insertion points are precisely located (file:line
cited throughout) and use only shadcn primitives that are already installed
and test-covered. No migration, no new external dependency, no new agent
tool, no change to leakage tests.

The −2 risk is concentrated in two places: **(a) the prophet_like signed-
coefficient display** — the panel must preserve sign through extraction
(NumPy ndarray), Pydantic response serialization (float, not abs), TanStack
Query (untouched), and React render (don't `Math.abs` in the bar-width
calc when computing `widthPercent = abs(value)/maxAbs * 100`, but DO keep
the original sign for the color/icon branch); the mitigation is the `kind`
discriminator on the wire and the matching test case in
`feature-importance-panel.test.tsx`. **(b) browser dogfood** (Task 21) —
the new collapsible on `forecast.tsx`, the conditional render gates on
`run-detail.tsx`, the cross-family branch on `run-compare.tsx`, and now
the additional `SCENARIO 6b` (baseline-train-job 400 path) each have a
state-machine flavor that catches up only in a real browser; the eight
dogfood SCENARIOS are designed to exercise every branch. Both risks are
gate-caught (vitest + webapp-testing skill); neither requires a redesign
to recover.
