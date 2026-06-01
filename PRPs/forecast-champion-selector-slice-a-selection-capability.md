name: "Forecast Champion Selector — Slice A: Selection & Capability Foundation"
description: |
  First usable frontend/backend surface for the Forecast Champion Selector. Adds
  one backend-owned model-capability catalog endpoint to the existing
  `model_selection` slice, then builds the React selection shell — searchable
  store/product selectors, pair validation, live data-availability assessment,
  a simple/advanced backtest-settings form, and a candidate-model picker — under
  a new `/visualize/champion` page. Slice A deliberately STOPS before running the
  comparison: it does NOT call `POST /model-selection/run`, render ranking/chart
  results, train, predict, or promote. Those are Slice B (async run + results)
  and Slice C (train/predict/business summary/override/promotion).

**Created:** 2026-06-01 · **Slice:** A of 3 (A → B → C)
**Current repo base observed:** `dev` @ `6c3f8d4` (Merge PR #354 — model_selection backend merged)
**Backend foundation (source of truth):** `PRPs/forecast-champion-selector-backend.md` (issue #353, MERGED) +
the live slice `app/features/model_selection/` (schemas/service/routes/ranking/explanations verified 2026-06-01).
**Working-tree caveat:** `docker-compose.lan.yml` is an untracked local dogfood override; do NOT commit it.
**Tracking issue:** create before implementation, suggested title `feat(api,ui): forecast champion selector slice A — selection & capability`.
**Suggested branch:** `feat/champion-selector-slice-a` (off `dev`, per `.claude/rules/branch-naming.md`).
**Commit scope:** `api` (new catalog endpoint + slice schemas/service/routes) and `ui` (frontend page/components/hooks/types).
No migration in Slice A — no schema change. Every commit references the tracking issue.

---

## Goal

**Feature Goal:** Ship the first interactive Forecast Champion Selector surface — a `/visualize/champion`
React page that lets a user choose a **Store → Product → Time Period → Forecast Horizon → Model Types →
Backtest Settings**, see whether the chosen pair has enough history to model (live availability assessment),
and pick candidate models from a **backend-owned** capability catalog — backed by exactly one new backend
endpoint (`GET /model-selection/models`). The page is genuinely usable for *configuration + availability
triage* even though the comparison **run** itself lands in Slice B.

**Deliverable:**
- **Backend:** `GET /model-selection/models` → `ModelCatalogResponse` (capability catalog), implemented via a new
  pure module `app/features/model_selection/capabilities.py`, response schemas added to the slice's
  `schemas.py`, a thin `ModelSelectionService.get_model_catalog()` delegate, and the route wired in the slice's
  existing `routes.py`. No migration, no new mutation surface, no agent tool.
- **Frontend:** a lazy-loaded `pages/visualize/champion.tsx` page (route `ROUTES.VISUALIZE.CHAMPION`,
  nav entry under **Visualize**), a `components/champion-selector/` component family (searchable store/product
  selects, availability panel, backtest-settings form, candidate-model picker), a `hooks/use-model-selection.ts`
  query-hook module (catalog + availability reads), and a `types/api.ts` "Model Selection" section that declares
  the FULL workflow contract (so Slices B/C inherit, not redefine, the types).

**Success Definition:**
1. `GET /model-selection/models` returns HTTP 200 with a non-empty `models` array — each entry carrying
   `model_type`, `label`, `family ∈ {baseline,tree,additive}`, `feature_aware`, `requires_extra`,
   `default_params`, `supports_auto_predict`, `description` — plus a `default_candidate_model_types` list.
2. The `/visualize/champion` page renders: a searchable store select, a searchable product select (each with a
   secondary line — store `code · name`, product `sku · category`), a date-range picker, a horizon input, a
   candidate-model picker fed by `GET /model-selection/models`, and a simple/advanced backtest-settings form.
3. Selecting a valid `(store, product, horizon)` triggers `GET /model-selection/availability` and renders a
   `ready | limited | unusable` status block with coverage/observed-days/zero-sale/promotion/avg-demand and the
   recommended split config; an unusable/empty pair shows a clear not-enough-data state.
4. The "Run comparison" primary CTA is present but **disabled** with explanatory copy (Slice B turns it on).
5. All Slice A validation gates pass (backend Level-1..4 + frontend `tsc`/`lint`/`test`).

## Why

- Business users want to ask "which model should I use for this store/product?" through a UI, not curl. Slice A
  gives them the **configuration + triage** half of that workflow immediately, and a stable shell Slice B/C bolt
  onto with minimal churn.
- The capability catalog must be **backend-owned** (coordination contract): the model union, families, opt-in
  extras, and feature-aware flags live in Python (`app/features/forecasting/`), and shipping them over an API
  prevents the TypeScript `MODEL_FAMILY_MAP`/`MODEL_TYPE_LABELS` from drifting out of sync as new models land.
- Declaring the full TS contract now (consumed read-only in A) means Slices B and C add behavior, not type
  definitions — cleaner slice boundaries, fewer merge conflicts.
- Preserves the single-host architecture: one new read-only GET, no queue, no new dependency, no cloud SDK.

## What

### New backend endpoint (added to the existing slice router `APIRouter(prefix="/model-selection")`)

```http
GET /model-selection/models
```

Response `ModelCatalogResponse`:

```json
{
  "models": [
    {
      "model_type": "naive",
      "label": "Naive",
      "family": "baseline",
      "feature_aware": false,
      "requires_extra": false,
      "default_params": {},
      "supports_auto_predict": true,
      "description": "Repeats the last observed value."
    },
    {
      "model_type": "seasonal_naive",
      "label": "Seasonal Naive",
      "family": "baseline",
      "feature_aware": false,
      "requires_extra": false,
      "default_params": { "season_length": 7 },
      "supports_auto_predict": true,
      "description": "Repeats the value from one season ago."
    }
    // ... one entry per forecasting ModelConfig member (11 total)
  ],
  "default_candidate_model_types": ["naive", "seasonal_naive", "moving_average", "regression", "prophet_like"]
}
```

### LOCKED Slice-A decisions (remove every "choose-one" ambiguity)

1. **Exactly one new backend endpoint:** `GET /model-selection/models`. It is **declared in `routes.py`
   BEFORE the `GET /{selection_id}` route** (literal path must precede the path-param route, mirroring the
   existing `/availability` route at `routes.py:41` which sits before `/{selection_id}` at `:94`). Status 200.
   No request body, no query params.
2. **Catalog is backend-owned and derived, not hand-duplicated.** `family` comes from the forecasting
   authority `app.features.forecasting.feature_metadata.model_family_for(model_type)` (imported LAZILY inside
   the builder, per the slice's cross-slice discipline) mapped to the lowercase literal
   (`ModelFamily.BASELINE → "baseline"`, etc.). `model_type` iteration order + `default_params` + `label` +
   `description` come from a slice-local ordered map in `capabilities.py` whose keys are asserted (in a test) to
   exactly equal the `ModelType` Literal in `app/features/model_selection/schemas.py`.
3. **`requires_extra`** = `model_type in {"lightgbm", "xgboost"}` (opt-in extras that may `ImportError`).
   **`feature_aware`** = `model_type in {"regression", "prophet_like", "lightgbm", "xgboost", "random_forest"}`
   (the set the forecasting `predict()` rejects — see Known Gotchas to verify against `forecasting/service.py`).
   **`supports_auto_predict`** = `not feature_aware` (feature-aware winners cannot auto-predict — backend
   `predict()` rejects them; this flag lets Slice C grey-out the auto-predict toggle).
4. **`default_candidate_model_types`** = `["naive", "seasonal_naive", "moving_average", "regression", "prophet_like"]`
   — the exact default five from the backend PRP's `POST /run` example, so the UI pre-selects the same set the
   contract documents.
5. **No `model_selection_run` write in Slice A.** The page consumes `GET /models` and `GET /availability` only.
   It assembles a typed `ModelSelectionRunRequest` in component state and exposes it through a **disabled**
   "Run comparison" CTA; Slice B wires the `POST /run` mutation + results. Slice A MUST NOT call `POST /run`,
   `/{id}`, `/{id}/ranking`, `/{id}/train-winner`, or `/{id}/predict`.
6. **Searchable selects use existing primitives only** (no new npm dependency). Stores/products are fetched at
   `pageSize: 100` (the dimensions cap) and filtered **client-side** inside a `Popover` + text `Input` +
   scrollable button list. (If the catalog ever exceeds 100, swap to the server-side `search` param the
   `useStores`/`useProducts` hooks already support — out of scope here.)
7. **Bias-explanation copy (locked, reused by B/C):** wherever bias is explained in help text/tooltips, use
   exactly — *"Positive bias means the model under-forecasts (risk of stockouts); negative bias means it
   over-forecasts (risk of overstock)."* Export it as a shared constant so B/C reuse the same wording.
8. **WAPE is the default ranking metric**; the advanced form's ranking-metric select offers `wape` (default),
   `smape`, `mae`, `bias`, with help text stating the tie-break chain *WAPE → sMAPE → |bias| → MAE* and the
   bias copy from #7.

### Success Criteria

- [ ] `GET /model-selection/models` returns 200 with `models` (11 entries) + `default_candidate_model_types`.
- [ ] `capabilities.build_model_catalog()` is pure (no DB/IO) and its `model_type` set equals the slice
      `ModelType` Literal (asserted by a test).
- [ ] `/model-selection/models` is matched correctly (NOT captured by `/{selection_id}`) — route-order test green.
- [ ] `/visualize/champion` route + Visualize nav entry render the page; lazy-loaded like its siblings.
- [ ] Searchable store + product selects filter client-side and show the secondary descriptor line.
- [ ] Pair validation: the form's primary CTA stays disabled until a store, product, valid date window, and
      horizon are all chosen; the date window + horizon respect backend bounds.
- [ ] Availability auto-fetches for a valid pair and renders `ready/limited/unusable` + metrics + recommended
      split config; an empty/unusable pair renders a not-enough-data `EmptyState`.
- [ ] The candidate-model picker is fed by `GET /model-selection/models`; opt-in-extra models are visibly
      flagged; the default five are pre-selected.
- [ ] The simple/advanced settings form mirrors `SplitConfig` bounds and keeps `split_config.horizon ===
      forecast_horizon` (matching the backend request validator).
- [ ] The "Run comparison" CTA is present but disabled with copy indicating it arrives next.
- [ ] No `POST /model-selection/run` (or any mutation) is called; no chart/ranking results UI; no train/predict/
      promotion UI; no agent tool; no migration; no new npm dependency.
- [ ] `app/core/tests/test_strict_mode_policy.py` stays green (no new strict request model with date fields).
- [ ] All backend Level-1..4 gates + frontend `pnpm tsc --noEmit && pnpm lint && pnpm test --run` pass.

## All Needed Context

### Documentation & References

```yaml
# Slice / contract source of truth
- file: PRPs/forecast-champion-selector-backend.md
  why: The merged backend foundation. LOCKED decisions #1-#7, the full /run + /{id} contract, the
       availability semantics (ready/limited/unusable thresholds), and the default-five candidate list.
       Slice A consumes this contract read-only; do not re-derive ranking/confidence in TS.
- file: PRPs/ai_docs/forecast-champion-selector-backend-research.md
  why: External-lib + runtime facts (FastAPI APIRouter, Pydantic strict mode, sklearn TimeSeriesSplit).
- file: PRPs/templates/prp_base.md
  why: Base PRP template structure. NOTE — the referenced "PRPs/prp-readme.md.md" does NOT exist
       (`find PRPs -iname '*readme*'` empty on 2026-06-01); the backend PRP records the same finding.

# Live backend slice to read (the contract the UI consumes)
- file: app/features/model_selection/schemas.py
  why: ModelType Literal (:34, the 11 model_types), RankingMetric (:48), AvailabilityStatus (:51),
       ConfidenceLevel (:50), PairAvailabilityResponse (:239), ModelSelectionRunRequest (:118),
       ModelSelectionRunResponse (:267), ModelRankEntry (:195), WinnerSummary (:216), ChartData (:225).
       ADD the new ModelCatalogResponse + CandidateModelInfo here (plain BaseModel — outputs need no strict).
- file: app/features/model_selection/routes.py
  why: APIRouter(prefix="/model-selection") (:38); the literal `/availability` (:41) precedes `/{selection_id}`
       (:94) — MIRROR that ordering for the new `/models` route. Error mapping: ValueError→BadRequestError,
       SQLAlchemyError→DatabaseError.
- file: app/features/model_selection/service.py
  why: Stateless service pattern; lazy cross-slice imports inside methods (:215-219). ADD
       get_model_catalog() delegating to capabilities.build_model_catalog() (no DB needed; keep signature
       db-free or accept db and ignore — prefer db-free since the catalog is static).
- file: app/features/model_selection/ranking.py
  why: PURE-module precedent (no DB/IO, unit-tested directly). MIRROR this style for capabilities.py.
- file: app/features/model_selection/explanations.py
  why: Second pure-module precedent (deterministic text). Same import/style conventions.
- file: app/features/model_selection/tests/test_routes.py
  why: Route-test pattern (ASGITransport + AsyncClient + dependency_overrides[get_db]); ADD a /models 200
       test + a route-ordering test (GET /model-selection/models is NOT treated as selection_id="models").
- file: app/features/model_selection/tests/test_ranking.py
  why: Pure-unit test pattern to MIRROR for tests/test_capabilities.py.

# Backend authority for model family / union (catalog source)
- file: app/features/forecasting/feature_metadata.py
  why: model_family_for(model_type) -> ModelFamily (:57) and _MODEL_FAMILY_MAP (:42). The catalog `family`
       field derives from here. ModelFamily enum is BASELINE/TREE/ADDITIVE (lowercase .value).
- file: app/features/forecasting/schemas.py
  why: ModelConfig union (the 11 flat members + their default params). Use to VERIFY default_params per model
       (see Known Gotchas verification one-liner). ModelFamily enum lives here too (imported by feature_metadata).
- file: app/features/backtesting/schemas.py
  why: SplitConfig (:24) — strategy Literal["expanding","sliding"] (def "expanding"), n_splits 2-20 (def 5),
       min_train_size >=7 (def 30), gap 0-30 (def 0), horizon 1-90 (def 14), field_validator horizon>gap (:65).
       The TS SplitConfig type + advanced form bounds mirror this exactly.

# Frontend examples to MIRROR (verified 2026-06-01)
- file: frontend/src/pages/visualize/backtest.tsx
  why: Canonical analytical page: Card sections, store/product Select fed by useStores/useProducts
       ({page:1,pageSize:100}), DateRangePicker, numeric Inputs, a `formReady` gate, EmptyState/LoadingState,
       getErrorMessage. Slice A's champion page mirrors this density (minus the results/charts).
- file: frontend/src/components/forecast-intelligence/model-type-select.tsx
  why: shadcn Select-based model picker convention + data-testid pattern. The Slice-A candidate picker mirrors
       the labelling style but sources options from GET /model-selection/models (NOT the hardcoded util).
- file: frontend/src/components/forecast-intelligence/model-type-utils.ts
  why: The EXISTING hardcoded MODEL_FAMILY_MAP / MODEL_TYPE_LABELS used by OTHER pages. DO NOT refactor or
       delete it in Slice A — other pages depend on it; the champion page just doesn't use it.
- file: frontend/src/components/forecast-intelligence/batch-matrix-picker.tsx
  why: Multi-select-of-models pattern (checkbox list, max-rows cap, data-testid scheme, Badge for state).
       The candidate-model picker mirrors this (checkbox per model, opt-in-extra Badge), but rows = model_types
       from the catalog, no feature-frame matrix (that's B/C).
- file: frontend/src/components/forecast-intelligence/batch-matrix-picker.test.tsx
  why: Component test convention — render + fireEvent + expect(onChange).toHaveBeenCalledWith; afterEach(cleanup).
- file: frontend/src/hooks/use-stores.ts
  why: useStores({page,pageSize,...,search,enabled}) query-hook shape + keyed query + keepPreviousData.
- file: frontend/src/hooks/use-products.ts
  why: useProducts(...) — identical shape; the searchable selects fetch at pageSize:100.
- file: frontend/src/hooks/use-batches.test.ts
  why: Hook test convention — vi.fn() fetch mock via vi.stubGlobal('fetch',...), QueryClient wrapper,
       renderHook + waitFor, afterEach(vi.unstubAllGlobals()). MIRROR for use-model-selection.test.ts.
- file: frontend/src/hooks/index.ts
  why: Star-export barrel; ADD `export * from './use-model-selection'`.
- file: frontend/src/lib/api.ts
  why: `api<T>(endpoint,{params})` typed fetch helper; getErrorMessage(); ApiError. All hooks call `api`.
- file: frontend/src/lib/constants.ts
  why: ROUTES (VISUALIZE.* block) + NAV_ITEMS (Visualize group). ADD ROUTES.VISUALIZE.CHAMPION +
       a { label:'Champion Selector', href: ROUTES.VISUALIZE.CHAMPION } nav entry under Visualize.
- file: frontend/src/App.tsx
  why: Lazy-page + <Route path={ROUTES.VISUALIZE.X} element={<Suspense><Page/></Suspense>}> pattern. ADD the
       champion route mirroring the BATCH/PLANNER entries.
- file: frontend/src/types/api.ts
  why: Section-commented type file. ModelFamily (:177 = 'baseline'|'tree'|'additive'), ProblemDetail (:652),
       Store/StoreListResponse (:10/:21), Product/ProductListResponse (:25/:37). ADD a new
       "// === Model Selection (Champion Selector) ===" section near the Registry block.
- file: frontend/src/components/common/error-display.tsx
  why: EmptyState({title,description,action?,icon?}) — used for the not-enough-data state.
- file: frontend/src/components/common/loading-state.tsx
  why: LoadingState({message}) — used while availability/catalog load.
- file: frontend/src/components/common/date-range-picker.tsx
  why: DateRangePicker({value:DateRange|undefined,onChange}) — the time-period selector.
- file: frontend/src/components/ui/{select,popover,input,card,button,badge,checkbox,table}.tsx
  why: Available shadcn primitives. NOTE: there is NO command/combobox/cmdk primitive — build the searchable
       select from Popover + Input + a filtered button list (LOCKED #6).
- file: frontend/src/components/layout/top-nav.tsx
  why: Renders NAV_ITEMS (grouped via NavigationMenu). No edit needed beyond the constants.ts NAV_ITEMS entry.
- file: frontend/vitest.config.ts
  why: jsdom env; include 'src/**/*.test.{ts,tsx}'; `@`→./src alias. No setup file. `pnpm test --run` runs once.

# External official docs (with reasoning)
- url: https://fastapi.tiangolo.com/tutorial/bigger-applications/#include-an-apirouter-with-a-custom-prefix-tags-responses-and-dependencies
  why: APIRouter route-registration + the literal-before-path-param ordering rule that LOCKED #1 depends on.
- url: https://www.ibm.com/design/language/  # (progressive disclosure principle)
  why: Simple/advanced settings split — show the recommended split config by default, reveal n_splits/min_train/
       gap/strategy under an "Advanced" toggle so novice users aren't overwhelmed. NOTE: the originally-cited
       IBM technical-content URL 404s; use the IBM Design language site / Nielsen Norman
       (https://www.nngroup.com/articles/progressive-disclosure/) as the canonical reference instead.
- url: https://help.tableau.com/current/pro/desktop/en-us/dashboards_best_practices.htm
  why: Analytical dashboard layout — lead with the question (which model?), group related controls, keep the
       availability triage adjacent to the selection. Informs the Card grouping of the champion page.
- url: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
  why: The split semantics behind SplitConfig (expanding window, n_splits, gap, horizon) — so the advanced
       form's help text describes folds correctly.
- url: https://tanstack.com/query/latest/docs/framework/react/guides/queries
  why: useQuery enabled-gating (only fetch availability once a valid pair exists) + queryKey conventions.
```

### Current Codebase Tree (relevant)

```bash
app/features/model_selection/        # MERGED backend slice (issue #353)
├── __init__.py
├── models.py            # ModelSelectionRun ORM (NOT touched in Slice A)
├── schemas.py           # request/response contract  ← ADD catalog response models
├── ranking.py           # pure ranking (precedent for capabilities.py)
├── explanations.py      # pure explanations (precedent)
├── service.py           # ModelSelectionService     ← ADD get_model_catalog()
├── routes.py            # APIRouter(/model-selection) ← ADD GET /models (before /{selection_id})
└── tests/               # ← ADD test_capabilities.py; extend test_routes.py
app/features/forecasting/feature_metadata.py   # model_family_for() — catalog family authority
frontend/src/
├── App.tsx                              # ← ADD lazy champion route
├── lib/{api,constants}.ts               # ← constants: ROUTES.VISUALIZE.CHAMPION + NAV_ITEMS entry
├── types/api.ts                         # ← ADD "Model Selection" section
├── hooks/{use-stores,use-products,index}.ts  # ← index: export use-model-selection
├── pages/visualize/{backtest,batch,...}.tsx  # page-density precedent
└── components/
    ├── common/{error-display,loading-state,date-range-picker}.tsx
    ├── ui/{select,popover,input,card,button,badge,checkbox,table}.tsx
    └── forecast-intelligence/{model-type-select,batch-matrix-picker}.tsx  # picker precedents
```

### Desired Codebase Tree (Slice A additions)

```bash
# Backend
app/features/model_selection/capabilities.py          # NEW: pure build_model_catalog()
app/features/model_selection/schemas.py               # MODIFIED: + CandidateModelInfo, ModelCatalogResponse
app/features/model_selection/service.py               # MODIFIED: + get_model_catalog()
app/features/model_selection/routes.py                # MODIFIED: + GET /models (before /{selection_id})
app/features/model_selection/tests/test_capabilities.py   # NEW: pure catalog unit tests
app/features/model_selection/tests/test_routes.py     # MODIFIED: + /models route + ordering tests

# Frontend
frontend/src/lib/constants.ts                         # MODIFIED: ROUTES.VISUALIZE.CHAMPION + NAV_ITEMS entry
frontend/src/App.tsx                                  # MODIFIED: lazy ChampionSelectorPage route
frontend/src/types/api.ts                             # MODIFIED: Model Selection section (full contract)
frontend/src/hooks/use-model-selection.ts             # NEW: useModelCatalog + usePairAvailability
frontend/src/hooks/use-model-selection.test.ts        # NEW
frontend/src/hooks/index.ts                           # MODIFIED: + export
frontend/src/pages/visualize/champion.tsx             # NEW: the page shell
frontend/src/components/champion-selector/searchable-entity-select.tsx        # NEW (generic combobox)
frontend/src/components/champion-selector/searchable-entity-select.test.tsx   # NEW
frontend/src/components/champion-selector/availability-panel.tsx              # NEW
frontend/src/components/champion-selector/availability-panel.test.tsx         # NEW
frontend/src/components/champion-selector/backtest-settings-form.tsx          # NEW
frontend/src/components/champion-selector/backtest-settings-form.test.tsx     # NEW
frontend/src/components/champion-selector/candidate-model-picker.tsx          # NEW
frontend/src/components/champion-selector/candidate-model-picker.test.tsx     # NEW
frontend/src/components/champion-selector/copy.ts                             # NEW: BIAS_EXPLANATION const (LOCKED #7)
```

### Known Gotchas & VERIFIED Contracts

```python
# ── ROUTE ORDERING (LOCKED #1) ────────────────────────────────────────────────
# Starlette matches routes in DECLARATION ORDER. The literal `GET /models` MUST be declared BEFORE
# `GET /{selection_id}` or a request to /model-selection/models is captured as selection_id="models"
# and 404s in the service. The existing `/availability` route (routes.py:41) already sits before
# `/{selection_id}` (:94) — place `/models` immediately after `/availability`.

# ── CATALOG default_params — VERIFY before hardcoding ─────────────────────────
# default_params per model must match the forecasting ModelConfig member defaults. Verify with:
#   uv run python -c "
#   from pydantic import TypeAdapter
#   from app.features.forecasting.schemas import ModelConfig
#   a=TypeAdapter(ModelConfig)
#   for mt in ['naive','seasonal_naive','moving_average','weighted_moving_average','seasonal_average',
#              'trend_regression_baseline','regression','prophet_like','random_forest','lightgbm','xgboost']:
#       try:
#           m=a.validate_python({'model_type':mt}); d=m.model_dump(); d.pop('model_type',None)
#           print(mt, d)
#       except Exception as e:
#           print(mt, 'NEEDS-PARAMS:', e)"
# Use the printed defaults as `default_params` in capabilities.py. If a member REQUIRES a param (validation
# error with only model_type), supply the contract default (seasonal_naive→{'season_length':7},
# moving_average→{'window_size':7}) — match the backend PRP /run example. Pin these in test_capabilities.py.

# ── feature_aware / requires_extra — VERIFY against forecasting predict() reject ──
# LOCKED #3 sets feature_aware = {regression, prophet_like, lightgbm, xgboost, random_forest}. Confirm this
# equals the set ForecastingService.predict() rejects (the backend PRP cites forecasting/service.py:491
# "rejects feature-aware models"). If the live reject-set differs, the live code wins — update the
# capabilities set and the test to match, and note the discrepancy in the PR description.

# ── family literal mapping ────────────────────────────────────────────────────
# model_family_for(mt) returns a ModelFamily enum; serialize via `.value` → "baseline"|"tree"|"additive"
# which already matches the frontend ModelFamily TS union (types/api.ts:177). Import model_family_for
# LAZILY inside build_model_catalog() (mirror service.py lazy cross-slice imports).

# ── NO new strict request model ───────────────────────────────────────────────
# GET /models has no body and no query params → no ConfigDict(strict=True) model, no date fields → the
# strict-mode policy linter is unaffected. Do NOT add an AvailabilityQuery-style model for /models.

# ── catalog is static/pure ─────────────────────────────────────────────────────
# build_model_catalog() takes no args and does no I/O — it is unit-testable like ranking.py. get_model_catalog()
# on the service is a thin pass-through (no db round-trip needed); keep it sync-pure or trivially async.
```

```typescript
// ── FRONTEND ────────────────────────────────────────────────────────────────
// NO combobox/cmdk primitive exists (only select/popover/input/dialog under components/ui). Build the
// searchable select from <Popover> + <Input> (filter box) + a scrollable list of <button> rows. Filter the
// already-fetched ≤100 rows CLIENT-SIDE (LOCKED #6). Do NOT add cmdk / a new npm dependency.
//
// Stores/products: useStores({page:1,pageSize:100}) / useProducts({page:1,pageSize:100}) (the dimensions
// endpoints cap page_size at 100 — see backtest.tsx:97-98).
//
// IDs are NOT 1-based (memory: seeder-does-not-reset-id-sequences) — never hardcode store_id=1/product_id=1
// in tests or examples; read real IDs from the dimensions list. selection_id is BACKEND-generated — do NOT
// call crypto.randomUUID() client-side (memory: showcase-crypto-randomuuid-lan-crash; undefined over LAN HTTP).
//
// SplitConfig has NO existing TS type — add it. Mirror backend bounds EXACTLY:
//   strategy: 'expanding'|'sliding' (def 'expanding'); n_splits 2..20 (def 5); min_train_size >=7 (def 30);
//   gap 0..30 (def 0); horizon 1..90 (def 14); horizon must be > gap; AND split_config.horizon === forecast_horizon
//   (the backend ModelSelectionRunRequest validator enforces both — mirror client-side so the assembled
//   request is always valid for Slice B).
//
// Availability fetch is gated: usePairAvailability(storeId, productId, horizon, { enabled: !!storeId && !!productId })
// — only fire once a pair is chosen (TanStack `enabled`). Mirror useStore(storeId, enabled) gating style.
//
// Mixed CRLF/LF line endings exist repo-wide (memory: repo-line-endings-crlf) — run `git diff --stat` before
// committing to avoid whole-file noise diffs; keep new files LF.
//
// VITE_API_BASE_URL must be http://localhost:8123 for local dogfood (memory/CLAUDE.local.md).
```

## Implementation Blueprint

### Backend data models (added to `app/features/model_selection/schemas.py`)

```python
# Response-only (plain BaseModel — no strict needed). Place after the existing response models.
class CandidateModelInfo(BaseModel):
    """One selectable forecasting model in the capability catalog."""
    model_type: str
    label: str
    family: Literal["baseline", "tree", "additive"]
    feature_aware: bool
    requires_extra: bool          # lightgbm/xgboost — opt-in extra may be absent at runtime
    default_params: dict[str, Any]
    supports_auto_predict: bool   # False for feature-aware models (predict() rejects them)
    description: str

class ModelCatalogResponse(BaseModel):
    """GET /model-selection/models — backend-owned candidate catalog."""
    models: list[CandidateModelInfo]
    default_candidate_model_types: list[str]
```

`app/features/model_selection/capabilities.py` (pure):

```python
# CRITICAL details only — not full code.
# _CATALOG: an ORDERED dict/list keyed by model_type with (label, default_params, description) — keys MUST
#   equal the ModelType Literal members (asserted in test_capabilities.py).
# _FEATURE_AWARE = frozenset({"regression","prophet_like","lightgbm","xgboost","random_forest"})  # LOCKED #3
# _REQUIRES_EXTRA = frozenset({"lightgbm","xgboost"})
# DEFAULT_CANDIDATE_MODEL_TYPES = ["naive","seasonal_naive","moving_average","regression","prophet_like"]
#
# def build_model_catalog() -> ModelCatalogResponse:
#     from app.features.forecasting.feature_metadata import model_family_for   # lazy cross-slice
#     models = []
#     for model_type, meta in _CATALOG.items():
#         family = model_family_for(model_type).value          # "baseline"|"tree"|"additive"
#         feature_aware = model_type in _FEATURE_AWARE
#         models.append(CandidateModelInfo(
#             model_type=model_type, label=meta.label, family=family,
#             feature_aware=feature_aware, requires_extra=model_type in _REQUIRES_EXTRA,
#             default_params=meta.default_params, supports_auto_predict=not feature_aware,
#             description=meta.description))
#     return ModelCatalogResponse(models=models, default_candidate_model_types=DEFAULT_CANDIDATE_MODEL_TYPES)
```

### Implementation Tasks (dependency-ordered)

```yaml
# ───────────────────────── BACKEND ─────────────────────────
Task 1 — Catalog schemas:
  MODIFY app/features/model_selection/schemas.py:
    - ADD CandidateModelInfo + ModelCatalogResponse (plain BaseModel; reuse existing Literal/Any imports).

Task 2 — Pure catalog builder:
  CREATE app/features/model_selection/capabilities.py:
    - MIRROR ranking.py module style (pure, no DB/IO, `from __future__ import annotations`).
    - _CATALOG ordered map (label/default_params/description per model_type) — RUN the verification one-liner
      (Known Gotchas) and pin default_params to the printed forecasting defaults.
    - build_model_catalog() per blueprint; lazy-import model_family_for.

Task 3 — Service delegate:
  MODIFY app/features/model_selection/service.py:
    - ADD get_model_catalog(self) -> ModelCatalogResponse  (thin: `return build_model_catalog()`).
      (Keep it on the service for symmetry with availability/run; no db arg needed.)
    - Import build_model_catalog + ModelCatalogResponse (module scope is fine — same slice, no cycle).

Task 4 — Route (ORDER MATTERS):
  MODIFY app/features/model_selection/routes.py:
    - ADD `@router.get("/models", response_model=ModelCatalogResponse, status_code=200)` IMMEDIATELY AFTER the
      `/availability` handler and BEFORE `GET /{selection_id}` (LOCKED #1).
    - Handler: `service = ModelSelectionService(); return service.get_model_catalog()`  (wrap in the same
      try/except SQLAlchemyError→DatabaseError shell only if it touches db; catalog is static so a bare return
      is fine — but keep the import of the response model).

Task 5 — Backend tests:
  CREATE app/features/model_selection/tests/test_capabilities.py:
    - test_catalog_model_types_match_literal  (keys == ModelType.__args__)
    - test_catalog_families_are_valid_literals (each family in {baseline,tree,additive})
    - test_requires_extra_flags_lightgbm_xgboost_only
    - test_feature_aware_models_do_not_support_auto_predict
    - test_default_candidate_model_types_are_the_default_five
    - test_default_params_match_forecasting_defaults  (seasonal_naive season_length=7, moving_average window_size=7)
  MODIFY app/features/model_selection/tests/test_routes.py:
    - test_get_models_returns_catalog_200  (ASGITransport; assert models non-empty + default list)
    - test_models_route_not_captured_by_selection_id  (GET /model-selection/models ≠ a 404 "selection run models
      not found"; assert it returns the catalog shape, proving literal-before-param ordering)

# ───────────────────────── FRONTEND ─────────────────────────
Task 6 — TS contract:
  MODIFY frontend/src/types/api.ts:
    - ADD a "// === Model Selection (Champion Selector) ===" section. Declare the FULL workflow contract so
      Slices B/C inherit it:
      SplitConfig, CandidateModelConfig, RankingPolicy, ModelSelectionRunRequest, SelectionWindow,
      CandidateModelInfo, ModelCatalogResponse, PairAvailability (mirror PairAvailabilityResponse),
      ModelRankEntry, WinnerSummary, ChartData, ForecastSummary, ModelSelectionRunResponse.
    - family field reuses the existing ModelFamily union; status uses 'pending'|'running'|'completed'|'partial'|'failed'.
    - Mark with a comment which types Slice A CONSUMES (ModelCatalogResponse, PairAvailability, SplitConfig)
      vs which are DECLARED-FOR-LATER (run request/response, ranking, chart).

Task 7 — Query hooks:
  CREATE frontend/src/hooks/use-model-selection.ts:
    - useModelCatalog(): useQuery(['model-selection','models'], () => api<ModelCatalogResponse>('/model-selection/models'))
      with staleTime long (catalog is static).
    - usePairAvailability(storeId, productId, forecastHorizon, enabled): useQuery keyed on the triple, calling
      api<PairAvailability>('/model-selection/availability', { params: { store_id, product_id, forecast_horizon } }),
      enabled: enabled && storeId>0 && productId>0  (MIRROR useStore gating).
  MODIFY frontend/src/hooks/index.ts: ADD `export * from './use-model-selection'` (alpha order).
  CREATE frontend/src/hooks/use-model-selection.test.ts:
    - MIRROR use-batches.test.ts (vi.stubGlobal('fetch',...), QueryClient wrapper, renderHook+waitFor).
    - assert /model-selection/models URL + parsed catalog; assert availability URL carries the 3 query params;
      assert availability query is DISABLED when storeId/productId absent (fetch not called).

Task 8 — Shared copy + searchable select:
  CREATE frontend/src/components/champion-selector/copy.ts:
    - export const BIAS_EXPLANATION = "Positive bias means the model under-forecasts (risk of stockouts); "
      + "negative bias means it over-forecasts (risk of overstock)."   # LOCKED #7
    - export const RANKING_TIE_BREAK = "Ranked by WAPE, then sMAPE, then |bias|, then MAE."   # LOCKED #8
  CREATE frontend/src/components/champion-selector/searchable-entity-select.tsx:
    - Generic: props { items: {id:number; primary:string; secondary?:string}[]; value:number|null;
      onChange:(id:number)=>void; placeholder; loading?; emptyLabel? }.
    - Popover + trigger Button (shows selected primary/secondary) + Input filter (client-side, case-insensitive
      over primary+secondary) + scrollable list of <button> rows. data-testid="searchable-entity-select".
  CREATE searchable-entity-select.test.tsx: render, type a filter, assert filtered rows; click selects + calls onChange.

Task 9 — Availability panel:
  CREATE frontend/src/components/champion-selector/availability-panel.tsx:
    - props { availability?: PairAvailability; isLoading; isError }.
    - LoadingState while loading; EmptyState ("Not enough data to model this pair") when status==='unusable' OR
      observed_days===0; otherwise a Card with a status Badge (ready=default, limited=secondary/amber,
      unusable=destructive) + metric tiles (observed_days, coverage_ratio %, zero_sale_days, promotion_days
      [or "—" when null], average_daily_demand) + a "Recommended split" summary (strategy, n_splits, min_train,
      gap, horizon). Render warnings[] as muted lines.
  CREATE availability-panel.test.tsx: ready→tiles render; unusable→EmptyState; null promotion_days→"—".

Task 10 — Backtest settings form (simple/advanced):
  CREATE frontend/src/components/champion-selector/backtest-settings-form.tsx:
    - props { value: SplitConfig; rankingMetric: RankingMetric; forecastHorizon:number;
      onChange:(next:SplitConfig)=>void; onRankingMetricChange:(m)=>void; recommended?:SplitConfig }.
    - "Simple" view shows recommended split read-only + a "Use recommended" button; an "Advanced" toggle reveals
      n_splits / min_train_size / gap / strategy inputs (bounds per SplitConfig). horizon is DERIVED from
      forecastHorizon (kept equal — LOCKED Gotcha) and shown read-only with a note.
    - ranking-metric Select (wape default / smape / mae / bias) with help text = RANKING_TIE_BREAK + BIAS_EXPLANATION.
    - client-side validation surfaces inline errors (n_splits 2-20, min_train>=7, gap 0-30, gap<horizon).
  CREATE backtest-settings-form.test.tsx: advanced toggle reveals inputs; invalid n_splits shows error; "Use
    recommended" calls onChange with the recommended config.

Task 11 — Candidate-model picker:
  CREATE frontend/src/components/champion-selector/candidate-model-picker.tsx:
    - props { catalog?: ModelCatalogResponse; selected:string[]; onChange:(types:string[])=>void; isLoading }.
    - MIRROR batch-matrix-picker: checkbox per catalog model (grouped by family), opt-in-extra models show a
      "extra" Badge, feature-aware models show a small "feature-aware" hint; cap selection at 10 (backend
      candidate_models max_length=10) with a "max reached" Badge. Pre-select default_candidate_model_types on
      first catalog load (controlled by the page). data-testid per model.
  CREATE candidate-model-picker.test.tsx: toggling a model calls onChange; cap at 10 disables further adds;
    extra Badge present for lightgbm/xgboost.

Task 12 — Page shell:
  CREATE frontend/src/pages/visualize/champion.tsx (default export):
    - MIRROR backtest.tsx layout density. State: storeId, productId, dateRange, forecastHorizon, splitConfig,
      rankingMetric, selectedModels.
    - useStores/useProducts ({page:1,pageSize:100}) → feed two SearchableEntitySelect (store primary=`code · name`,
      product primary=`sku · name`, secondary=category). useModelCatalog() → CandidateModelPicker (pre-select
      defaults on load). usePairAvailability(storeId,productId,forecastHorizon, enabled=valid pair) → AvailabilityPanel.
    - Keep splitConfig.horizon === forecastHorizon (sync on horizon change); seed splitConfig from
      availability.recommended_split_config when it arrives (only if the user hasn't edited — simplest: a
      "Use recommended" button rather than auto-overwrite).
    - Assemble a typed `ModelSelectionRunRequest` (store_id, product_id, selection_window from dateRange,
      forecast_horizon, ranking_metric, split_config, candidate_models=[{model_type, params:{}}...], V1 defaults).
      Set `auto_train_winner: false` and `auto_predict: false` explicitly: the async run path (Slice B `POST /runs`)
      treats both as NO-OPS, and training/prediction happen later via Slice C's explicit `train-winner`/`train-selected`/
      `predict` actions — so these two request fields are effectively dead in the UI flow (set false, never surfaced).
      Render a DISABLED "Run comparison" Button with help text "Model comparison runs in the next update"
      (LOCKED #5). Gate en/disable purely on form validity; never call POST.
    - EmptyState when no pair chosen; LoadingState while catalog loads; getErrorMessage on query errors.
  MODIFY frontend/src/lib/constants.ts:
    - ROUTES.VISUALIZE.CHAMPION = '/visualize/champion'
    - NAV_ITEMS Visualize group: add { label: 'Champion Selector', href: ROUTES.VISUALIZE.CHAMPION }
  MODIFY frontend/src/App.tsx:
    - const ChampionSelectorPage = lazy(() => import('@/pages/visualize/champion'))
    - <Route path={ROUTES.VISUALIZE.CHAMPION} element={<Suspense fallback={<PageLoader/>}><ChampionSelectorPage/></Suspense>} />
```

### Integration Points

```yaml
ROUTES (backend):
  - app/features/model_selection/routes.py: GET /models added BEFORE /{selection_id} (no app/main.py change —
    the router is already wired).
ROUTES (frontend):
  - constants.ts ROUTES.VISUALIZE.CHAMPION + NAV_ITEMS entry; App.tsx lazy <Route>.
CONFIG: none (no settings, no .env var, no migration).
OBSERVABILITY: catalog endpoint may log `model_selection.catalog_served` (optional; mirror existing logger.info
  events) — not required.
```

## Validation Loop

### Level 1 — Backend syntax & policy

```bash
uv run ruff check app/features/model_selection
uv run ruff format --check app/features/model_selection
uv run mypy app/features/model_selection
uv run pyright app/features/model_selection
uv run pytest app/core/tests/test_strict_mode_policy.py -v   # must stay green (no new strict date model)
```

### Level 2 — Backend unit tests

```bash
uv run pytest app/features/model_selection/tests/test_capabilities.py app/features/model_selection/tests/test_routes.py -v -m "not integration"
```

### Level 3 — Frontend gates

```bash
cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run
```

Expected: type-check clean; lint clean (react-refresh only-export-components — keep non-component exports like
`copy.ts` constants in `.ts` files, not `.tsx`); new component + hook tests pass.

### Level 4 — Full gates (must be green before PR)

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
uv run pytest -v -m "not integration"
cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run
```

> Known-local-noise: mypy/pyright report pre-existing `lightgbm`/`xgboost` optional-dep import errors in
> `forecasting/`+`registry/` (CI installs the extras). Do NOT "fix" them — and remember a green LOCAL mypy can
> MASK errors that only surface once the extras resolve types (memory: the #355 finalizer cast).

### Manual dogfood probe (discover REAL ids first — IDs are NOT 1-based)

```bash
uv run uvicorn app.main:app --port 8123 &
# 0) catalog
curl -s http://localhost:8123/model-selection/models | python3 -m json.tool | head -40
# 1) confirm /models is NOT captured by /{selection_id} (should be the catalog, not a 404)
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8123/model-selection/models   # 200
# 2) discover real ids, then availability
curl -s "http://localhost:8123/dimensions/stores?page=1&page_size=5" | python3 -m json.tool | grep '"id"'
curl -s "http://localhost:8123/dimensions/products?page=1&page_size=5" | python3 -m json.tool | grep '"id"'
curl -s "http://localhost:8123/model-selection/availability?store_id=<ID>&product_id=<ID>&forecast_horizon=14" | python3 -m json.tool
# 3) frontend: VITE_API_BASE_URL=http://localhost:8123; pnpm dev (or ./node_modules/.bin/vite --host 0.0.0.0);
#    dogfood /visualize/champion over http://localhost:5173 (NOT a LAN IP — crypto/secure-context memory).
```

Expected: catalog 200 with 11 models + default-five list; availability renders ready/limited/unusable on the
page; the "Run comparison" CTA is visibly disabled; no console call to `POST /model-selection/run`.

## Final Validation Checklist

- [ ] `GET /model-selection/models` returns 200 with 11 models + default-five list; declared BEFORE `/{selection_id}`.
- [ ] `capabilities.build_model_catalog()` is pure; its model_type set == the slice `ModelType` Literal (tested).
- [ ] `family` derives from `forecasting.feature_metadata.model_family_for` (lazy import); values lowercase.
- [ ] `requires_extra`/`feature_aware`/`supports_auto_predict` flags verified against forecasting's predict-reject set.
- [ ] No new strict request model; strict-mode policy test green; no migration; no new mutation/agent surface.
- [ ] `/visualize/champion` route + Visualize nav entry render; page lazy-loaded like its siblings.
- [ ] Searchable store/product selects filter client-side (no new npm dep); secondary descriptor line shown.
- [ ] Availability auto-fetches for a valid pair; ready/limited/unusable + metrics + recommended split; empty
      state for unusable/empty; null promotion_days renders "—".
- [ ] Settings form mirrors SplitConfig bounds and keeps split_config.horizon === forecast_horizon.
- [ ] Candidate picker sourced from the catalog; default five pre-selected; opt-in extras flagged; cap 10.
- [ ] "Run comparison" CTA present but disabled; Slice A makes NO `POST /run` (or any mutation) call.
- [ ] All Level-4 gates pass; `gh issue view <N>` confirms the tracking issue is open.
- [ ] `git diff --stat` shows no whole-file CRLF noise; `docker-compose.lan.yml` NOT staged.

## Anti-Patterns to Avoid

- ❌ Don't implement Slice B (the comparison run, progress/cancel, ranking table, charts) or Slice C
  (train/predict/business summary/manual override/promotion) — Slice A is selection + capability + availability ONLY.
- ❌ Don't call `POST /model-selection/run` or any `/{selection_id}*` endpoint from Slice A.
- ❌ Don't add a backend endpoint outside the `/model-selection` namespace, and don't put the catalog in the
  forecasting slice (it stays slice-local — Option 1).
- ❌ Don't re-derive the model catalog in TypeScript or refactor/delete the existing `model-type-utils.ts`
  (other pages still use it). The champion page consumes the backend catalog.
- ❌ Don't add `cmdk`/a combobox dependency — build the searchable select from existing Popover+Input+list.
- ❌ Don't declare `GET /models` after `GET /{selection_id}` (it would be captured as a selection_id).
- ❌ Don't hardcode store_id=1/product_id=1 in tests or probes (IDs aren't 1-based).
- ❌ Don't call `crypto.randomUUID()` client-side (LAN secure-context crash); selection_id is backend-owned.
- ❌ Don't add a new strict request model with date fields without `Field(strict=False)` (none is needed here).
- ❌ Don't auto-overwrite a user-edited split config with the recommended one — offer a "Use recommended" button.

## Confidence Score

**8.5/10** for one-pass implementation success. The backend foundation is merged and its contract is read
verbatim; every frontend convention (routing, nav, lazy page, query hooks, hook/component test harness, common
components, available shadcn primitives) is verified against live files; the one new backend endpoint is a small
pure-catalog read with a precise route-ordering rule and verification one-liners for the only data-shape risks
(`default_params`, the `feature_aware` set). Residual risk (the 1.5): (a) the searchable-select UX is hand-built
from primitives (no combobox to mirror), so its tests need care; (b) the Slice-A/Slice-B boundary on the disabled
"Run comparison" CTA must be respected to avoid scope bleed; (c) this is the first frontend slice in this
workflow, so the `react-refresh/only-export-components` lint rule (keep constants in `copy.ts`, components in
`.tsx`) and CRLF noise are the most likely friction points — both are called out explicitly above.
