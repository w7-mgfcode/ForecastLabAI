name: "PRP-MLZOO-C1 — XGBoost Feature-Aware Forecasting Model"
description: |

## Purpose

The first half of MLZOO-C (`PRPs/INITIAL/INITIAL-MLZOO-C-xgboost-prophet-extensions.md`).
It adds **one** advanced, feature-aware forecasting model — `XGBoostForecaster`, wrapping
`xgboost.XGBRegressor` — as a low-risk follow-up that **mirrors the merged
`LightGBMForecaster` design byte-for-byte** (PRP-30 / MLZOO-B, commit `2f1b8a5`).

This PRP implements **XGBoost only**: its `XGBoostModelConfig` schema, the
`XGBoostForecaster` class, its `model_factory` wiring, the `forecast_enable_xgboost`
runtime flag, the `ml-xgboost` optional dependency group, the jobs train/backtest
branches, the reproducibility metadata, and tests. It adds **no** Prophet-like model
(that is PRP-MLZOO-C2, a separate branch and review unit — see DECISIONS LOCKED #1),
**no** hyperparameter search, **no** portfolio/global models, **no** frontend, and
**no** explainability change.

> **Sibling PRP:** `PRPs/PRP-MLZOO-C2-prophet-like-additive-model.md` ships the
> Prophet-like additive model. C1 and C2 are intentionally **separate branches and
> separate review units** — never combine them. They are additive and order-independent;
> whichever merges second rebases cleanly (see "Sibling-PRP integration" below).

## What this PRP already inherits (DO NOT re-build)

PRP-29 (MLZOO-A), PRP-30 (MLZOO-B), and PRP-MLZOO-B.2 (feature-aware backtesting,
PR #244) already shipped the entire structural foundation a new feature-aware model
stands on. Re-use it; do not re-derive it:

- **The feature-aware model contract.** `BaseForecaster.requires_features: ClassVar[bool]`
  (`app/features/forecasting/models.py:64`). `RegressionForecaster` (`models.py:438`) and
  `LightGBMForecaster` (`models.py:580`) are the *existing* feature-aware models —
  `requires_features = True`, `fit(y, X)` / `predict(horizon, X)` both require a
  non-`None` `X`. `XGBoostForecaster` is their structural twin.
- **The shared feature-frame contract.** `app/shared/feature_frames/` owns the pinned
  constants, `canonical_feature_columns()` (the 14-column set), the leakage-safe pure
  builders, and the `FeatureSafety` taxonomy. A new feature-aware model writes **zero**
  new contract code.
- **The training-frame branch.** `ForecastingService.train_model`
  (`app/features/forecasting/service.py:180-297`) branches on `model.requires_features`
  (`service.py:219`) — **model-type-agnostic**, no string compare. If true it builds the
  historical frame via `_build_regression_features` and calls `model.fit(features.y,
  features.X)`, persisting `feature_columns` / `history_tail` / `launch_date` into the
  bundle metadata. **An XGBoost model trains with zero changes to `train_model`.**
- **The predict rejection.** `ForecastingService.predict` (`service.py:383-393`) rejects
  any `bundle.model.requires_features` model — capability-based, not `model_type`-string.
  An XGBoost model is rejected there automatically; it forecasts through
  `POST /scenarios/simulate`.
- **The scenario `model_exogenous` dispatch.** `app/features/scenarios/service.py:114`
  already branches on `bundle.model.requires_features` — no `model_type` strings remain
  in `app/features/scenarios/`. An XGBoost bundle takes the genuine re-forecast path
  with **zero scenarios changes**.
- **Feature-aware backtesting.** `app/features/backtesting/service.py:384-409` probes
  `model_factory(...).requires_features` and, when true, builds per-fold leakage-safe
  `X_train` (sliced) / `X_future` (rebuilt) via `build_historical_feature_rows` /
  `build_future_feature_rows`. **Model-agnostic** — never checks a `model_type` string.
  An XGBoost model backtests with **zero backtesting-service changes**. (This is the key
  difference from PRP-30, which had to defer backtesting to B.2 — B.2 is now merged.)
- **The historical-frame leakage spec.** `app/features/forecasting/tests/test_regression_features_leakage.py`
  and `app/shared/feature_frames/tests/test_leakage.py` pin the historical and future
  builders. XGBoost consumes the **same** builders → these specs already cover its
  training and future feature matrices. **No new leakage test is required** (DECISIONS
  LOCKED #6).

The **problem this PRP fixes**: XGBoost — named in `INITIAL-MLZOO-C` and
`docs/optional-features/05-advanced-ml-model-zoo.md` as the second tree-based model and
the robust-regularization benchmark against LightGBM — does not exist. There is no
`xgboost` dependency, no `XGBoostModelConfig`, no `xgboost` in the `ModelType` literal,
no `model_factory` branch, and `JobService._execute_train` / `_execute_backtest` reject
`model_type="xgboost"` as unsupported.

## DEPENDS ON — read before starting

- `PRPs/INITIAL/INITIAL-MLZOO-C-xgboost-prophet-extensions.md` — the shared C brief.
- `PRPs/INITIAL/INITIAL-MLZOO-index.md` — the MLZOO roadmap (A ✅ → B ✅ → B.2 ✅ →
  **C1 (this) ∥ C2** → D).
- `PRPs/PRP-30-lightgbm-first-advanced-model.md` — **the byte-for-byte template for this
  PRP.** Every DECISIONS LOCKED entry and Anti-Pattern there applies here with `lightgbm`
  → `xgboost`. Read it in full first.
- `PRPs/PRP-MLZOO-B.2-feature-aware-backtesting.md` — explains why backtesting now works
  for any `requires_features` model with no per-model wiring.
- `examples/models/feature_frame_contract.md` — the historical/future frame shapes a
  feature-aware model consumes, and the canonical 14-column set.

---

## Goal

Implement `XGBoostForecaster` — a deterministic, feature-aware forecasting model wrapping
`xgboost.XGBRegressor` — and wire it end-to-end: `model_factory` instantiates it (behind a
new `forecast_enable_xgboost` flag), `ForecastingService.train_model` trains it through the
existing `requires_features` branch, `POST /scenarios/simulate` re-forecasts it through
`method="model_exogenous"`, the backtesting fold loop backtests it through the existing
`requires_features` probe, `JobService._execute_train` and `_execute_backtest` accept
`model_type="xgboost"`, and the XGBoost library version is captured in the model bundle and
the registry's `runtime_info`. XGBoost ships as an **optional dependency group**
(`ml-xgboost`); the model code lazy-imports it so a single-host install without the extra
still works for every other model.

**End state:** a user with `forecast_enable_xgboost=True` and the `ml-xgboost` extra
installed can train an `xgboost` model (HTTP or job), re-forecast it in a what-if scenario,
and backtest it, exactly as they can a `lightgbm` model today. Every existing model behaves
**identically** before and after.

## Why

- **The model zoo needs a second tree benchmark.** `docs/optional-features/05-advanced-ml-model-zoo.md`
  frames XGBoost as the "strong tabular benchmark … robust regularization … useful
  comparison against LightGBM". A credible model-*comparison* platform needs more than one
  advanced model; XGBoost is the industry-standard second.
- **The foundation is fully paid for.** PRP-29/30/B.2 made train, predict, scenarios, and
  backtesting all branch on `requires_features`. Adding a second tree model is now a
  *small, contained* change — one class (a near-clone of the proven `LightGBMForecaster`),
  one config, one factory branch, two jobs branches, metadata, and tests.
- **De-risks the dependency one step at a time.** `INITIAL-MLZOO-index.md` mandates "Add
  XGBoost as a second tree model" only after the first advanced model path is stable. It is.
- **Low blast radius.** No migration, no API-contract change, no existing-model change, no
  new vertical slice.

## What

A backend-only feature PRP. User-visible behaviour gains exactly one thing: `model_type:
"xgboost"` becomes a real, trainable, scenario-re-forecastable, backtestable model when the
feature flag and the optional dependency are both present. Everything else is identical.

### Technical requirements

1. **Optional dependency group.** `pyproject.toml` gains `[project.optional-dependencies]
   ml-xgboost = ["xgboost>=2.1.0"]`. CI already runs `uv sync --frozen --all-extras --dev`
   (`.github/workflows/ci.yml:48,74,116,163`) so the extra is installed and tested in CI
   with **no workflow change**. `uv.lock` is regenerated (`uv lock`) because CI uses
   `--frozen`.
2. **Runtime flag.** `app/core/config.py` gains `forecast_enable_xgboost: bool = False`
   (after `forecast_enable_lightgbm`, `config.py:101`) — mirrors the LightGBM gate exactly.
3. **`XGBoostModelConfig`** in `app/features/forecasting/schemas.py` — a `ModelConfigBase`
   subclass, **conservative field set matching `LightGBMModelConfig`** (DECISIONS LOCKED
   #4): `n_estimators` (10-1000, default 100), `max_depth` (1-20, default 6),
   `learning_rate` (0.001-1.0, default 0.1), `feature_config_hash: str | None`. Added to
   the `ModelConfig` union.
4. **`XGBoostForecaster`** in `app/features/forecasting/models.py` — a `BaseForecaster`
   subclass with `requires_features: ClassVar[bool] = True`, structurally mirroring
   `LightGBMForecaster` (`models.py:580-732`). It lazy-imports `xgboost` inside `fit()` so
   importing `models.py` never requires the optional dependency. It is deterministic
   (`n_jobs=1`, `tree_method="hist"`, fixed `random_state`) and NaN-tolerant (XGBoost
   handles `NaN` natively via `missing=np.nan`).
5. **`model_factory`** — a new `xgboost` branch mirroring the `lightgbm` branch
   (`models.py:778-792`), gated on `forecast_enable_xgboost`. The `ModelType` literal
   (`models.py:736`) gains `"xgboost"`.
6. **Jobs integration.** `JobService._execute_train` (`jobs/service.py:454-478`) and
   `_execute_backtest` (`jobs/service.py:641-658`) each gain an `xgboost` branch building
   `XGBoostModelConfig` — mirroring the existing `lightgbm` branches.
7. **Route gate.** `POST /forecasting/train` (`forecasting/routes.py:67-72`) gains an
   `xgboost` flag gate mirroring the `lightgbm` one.
8. **Reproducibility metadata.** `ModelBundle` gains an `xgboost_version: str | None`
   field (best-effort captured on save, mismatch-warned on load — mirroring
   `lightgbm_version`, `persistence.py:56,104-108,185-199`);
   `RegistryService._capture_runtime_info` (`registry/service.py:124-129`) gains an
   `xgboost` version block.
9. **Tests** mirroring the `LightGBMForecaster` suite, gated with
   `pytest.importorskip("xgboost")`; an `examples/models/advanced_xgboost.py` example;
   additive docs.

### Success Criteria

- [ ] `model_factory(XGBoostModelConfig(), random_state=42)` returns an `XGBoostForecaster`
      when `forecast_enable_xgboost=True`; raises a clear `ValueError` when the flag is off.
- [ ] `XGBoostForecaster.requires_features is True`; `fit`/`predict` require a non-`None`
      `X` and raise the same error-message substrings as `LightGBMForecaster`
      (`"requires exogenous features"`, `"rows must match"`, `"horizon"`, `"fitted"`).
- [ ] Two fits with the same `random_state` produce **identical** forecasts
      (`np.testing.assert_array_equal`) — single-threaded `hist` is reproducible within one
      environment (see Gotchas).
- [ ] `ForecastingService.train_model` trains an `xgboost` model with **no edit to
      `train_model`** (routes through the existing `requires_features` branch).
- [ ] `POST /scenarios/simulate` against a trained `xgboost` run returns
      `method="model_exogenous"` (not `"heuristic"`) — **no edit to scenarios code**.
- [ ] A backtest of an `xgboost` model produces per-fold metrics — **no edit to
      backtesting-service code** (the B.2 `requires_features` probe handles it).
- [ ] `JobService._execute_train` and `_execute_backtest` accept `model_type="xgboost"`.
- [ ] `ModelBundle.xgboost_version` and registry `runtime_info["xgboost_version"]` are
      captured when `xgboost` is installed.
- [ ] Every baseline model, `regression`, `lightgbm`, and every existing test pass **with
      no behaviour change**.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"` all green.
- [ ] No Alembic migration; no route/schema/WebSocket *contract* change; XGBoost stays an
      *optional* dependency (the core `dependencies` list is unchanged).

---

## All Needed Context

### Documentation & References

```yaml
- file: PRPs/PRP-30-lightgbm-first-advanced-model.md
  why: THE template. This PRP is a near-clone with lightgbm -> xgboost. Every DECISIONS
       LOCKED entry, every Anti-Pattern, every Validation Level there applies here. Read
       it fully before touching code.

- file: app/features/forecasting/models.py
  why: LightGBMForecaster (lines 580-732) is the BYTE-FOR-BYTE structural template for
       XGBoostForecaster — same __init__ shape, same fit/predict guards, same error
       strings, same lazy-import-inside-fit pattern, same get_params/set_params. The
       model_factory lightgbm branch (lines 778-792) is the template for the xgboost
       branch. The ModelType literal is at line 736.
  critical: The estimator is typed `Any` (`estimator: Any = lgb.LGBMRegressor(...)` at
       models.py:661) — mirror that for XGBRegressor so pyright --strict stays quiet.

- file: app/features/forecasting/schemas.py
  why: LightGBMModelConfig (lines 107-144) is the template for XGBoostModelConfig — same
       four fields, same Field(ge=, le=, default=) bounds. The ModelConfig union is at
       lines 192-199. DECISIONS LOCKED #4: keep XGBoostModelConfig conservative — DO NOT
       add subsample/colsample_bytree/reg_alpha/reg_lambda.

- file: app/features/forecasting/service.py
  why: train_model (lines 180-297) branches `if model.requires_features:` (line 219) —
       MODEL-AGNOSTIC. predict (lines 299-437) rejects feature-aware models at
       lines 383-393 — also capability-based. _build_regression_features and
       _assemble_regression_rows are REUSED unchanged by XGBoost.
  critical: DO NOT EDIT service.py. An XGBoost model trains and is predict-rejected purely
       because requires_features=True. Verify by reading, then leave it alone.

- file: app/features/forecasting/persistence.py
  why: ModelBundle dataclass (lines 48-57) has python_version + sklearn_version +
       lightgbm_version. save_model_bundle captures lightgbm_version best-effort at
       lines 102-108; load_model_bundle mismatch-warns at lines 185-199. ADD
       `xgboost_version` mirroring `lightgbm_version` EXACTLY. compute_hash (lines 59-72)
       reads only config_hash/model_params/metadata — adding xgboost_version does NOT
       change any bundle hash.

- file: app/features/forecasting/routes.py
  why: POST /forecasting/train has the lightgbm feature-flag gate at lines 67-72
       (`request.config.model_type == "lightgbm" and not settings.forecast_enable_lightgbm`
       -> 400). ADD a parallel xgboost gate. ValueError -> 400 (lines 115-118).

- file: app/features/jobs/service.py
  why: _execute_train has the model_type if/elif chain at lines 454-478 (lightgbm branch
       at the elif; final `else: raise ValueError("Unsupported model_type: ...")`).
       _execute_backtest has an IDENTICAL chain at lines 641-658. The forecasting-schemas
       import block is at lines 426-433. ADD an xgboost branch to BOTH chains and
       XGBoostModelConfig to the import.

- file: app/features/registry/service.py
  why: _capture_runtime_info (lines 84-131) best-effort-imports sklearn/numpy/pandas/
       joblib/lightgbm into a runtime_info dict. The lightgbm block is at lines 124-129.
       ADD an identical `try: import xgboost` block. runtime_info is JSONB — NO migration.

- file: app/features/backtesting/service.py
  why: lines 384-409 probe `model_factory(...).requires_features` and branch to
       _run_feature_aware_fold for any feature-aware model. MODEL-AGNOSTIC — DO NOT EDIT.
       Read to confirm an xgboost model backtests for free.

- file: app/features/forecasting/tests/test_lightgbm_forecaster.py
  why: THE test template for test_xgboost_forecaster.py. Clone every test 1:1 swapping
       LightGBMForecaster -> XGBoostForecaster, LightGBMModelConfig -> XGBoostModelConfig,
       forecast_enable_lightgbm -> forecast_enable_xgboost, and the importorskip target.
       Copy the `_synthetic_data` helper verbatim.

- file: app/features/forecasting/tests/test_regression_forecaster.py
  why: The fuller 10-test template the LightGBM file itself was cloned from — same test
       names. Either file works as the clone source.

- file: app/features/forecasting/tests/test_service.py
  why: TestFeatureAwareContract (lines 349-412) — test_requires_features_flag and
       test_lightgbm_factory_respects_flag. Extend the first with XGBoost; add an
       xgboost-flag mirror of the second.

- file: app/features/jobs/tests/test_service.py
  why: test_execute_train_rejects_unsupported_model_type (lines 243-249, already uses
       "arima" — NO fix needed). test_execute_train_builds_lightgbm_config (lines 222-241)
       and test_execute_backtest_builds_lightgbm_config (lines 286-304) are the templates
       for the xgboost job tests.

- url: https://xgboost.readthedocs.io/en/stable/python/python_api.html#xgboost.XGBRegressor
  why: XGBRegressor sklearn-API constructor — n_estimators, learning_rate, max_depth,
       random_state, n_jobs, tree_method, verbosity. fit(X, y) / predict(X) are
       sklearn-compatible. `missing` defaults to np.nan (native NaN handling).

- url: https://xgboost.readthedocs.io/en/stable/faq.html
  section: "Slightly different result between runs"
  critical: XGBoost has NO `deterministic=True` switch (unlike LightGBM). Single-machine
       bit-reproducibility comes from `n_jobs=1` + a fixed `random_state` + no stochastic
       sampling (conservative config has no subsample/colsample, so this holds) +
       `tree_method="hist"` (the default; pin it explicitly). Multi-threaded fits differ
       by float-summation order. Reproducibility is promised only within the SAME
       hardware+build — fine for CI and the determinism unit test.

- url: https://xgboost.readthedocs.io/en/stable/parameter.html
  section: Parameters for Tree Booster / Global Configuration
  why: max_depth, eta(=learning_rate), tree_method, verbosity semantics and ranges.
```

### Current Codebase tree (relevant — all already exist)

```bash
app/features/forecasting/
├── models.py            # BaseForecaster, RegressionForecaster, LightGBMForecaster,
│                        #   model_factory (lightgbm branch is the template), ModelType
├── schemas.py           # LightGBMModelConfig (the template), ModelConfig union
├── service.py           # train_model + predict branch on requires_features (untouched)
├── persistence.py       # ModelBundle (python/sklearn/lightgbm_version)
├── routes.py            # /forecasting/train has the lightgbm flag gate (lines 67-72)
└── tests/
    ├── test_lightgbm_forecaster.py          # the test template to clone
    ├── test_regression_forecaster.py        # the fuller 10-test template
    ├── test_service.py                      # TestFeatureAwareContract
    ├── test_routes.py
    ├── test_persistence.py
    └── test_regression_features_leakage.py  # load-bearing — already covers XGBoost's frame
app/core/config.py                           # forecast_enable_lightgbm at line 101
app/features/scenarios/service.py            # model_exogenous dispatch on requires_features (untouched)
app/features/backtesting/service.py          # feature-aware fold loop, requires_features probe (untouched)
app/features/jobs/service.py                 # _execute_train + _execute_backtest model_type chains
app/features/registry/service.py             # _capture_runtime_info (lightgbm block at 124-129)
app/shared/feature_frames/                   # the shared contract — reused, untouched
examples/models/advanced_lightgbm.py         # the example template
pyproject.toml                               # ml-lightgbm extra + lightgbm.* mypy override
.github/workflows/ci.yml                     # uv sync --frozen --all-extras --dev (no change)
```

### Desired Codebase tree — files to ADD

```bash
app/features/forecasting/tests/
└── test_xgboost_forecaster.py     # cloned from test_lightgbm_forecaster.py, importorskip
examples/models/
└── advanced_xgboost.py            # minimal XGBoost train/predict example
```

### Files to MODIFY (all additive or behaviour-preserving)

```bash
pyproject.toml                                  # + [project.optional-dependencies] ml-xgboost
                                                #   + (only if mypy --strict complains) xgboost.* override
uv.lock                                         # regenerated by `uv lock`
app/core/config.py                              # + forecast_enable_xgboost: bool = False
app/features/forecasting/schemas.py             # + XGBoostModelConfig; + to ModelConfig union
app/features/forecasting/models.py              # + XGBoostForecaster; + "xgboost" in ModelType;
                                                #   + model_factory xgboost branch
app/features/forecasting/persistence.py         # + ModelBundle.xgboost_version (save + load)
app/features/forecasting/routes.py              # + xgboost flag gate
app/features/jobs/service.py                    # _execute_train + _execute_backtest: + xgboost branch
app/features/registry/service.py                # _capture_runtime_info: + xgboost block
app/features/forecasting/tests/test_service.py  # extend TestFeatureAwareContract
app/features/forecasting/tests/test_routes.py   # + xgboost 400-when-disabled route test
app/features/forecasting/tests/test_persistence.py  # + xgboost_version captured assertion
app/features/jobs/tests/test_service.py         # + xgboost train + backtest job tests
app/features/scenarios/tests/test_routes_integration.py  # + xgboost model_exogenous test
app/features/backtesting/tests/test_feature_aware_backtest.py  # + light xgboost backtest test
app/features/registry/tests/test_service.py     # + runtime_info has xgboost_version
examples/models/model_interface.md              # additive: xgboost row
examples/models/feature_frame_contract.md       # additive: xgboost is a feature-aware model
README.md                                       # additive: the ml-xgboost optional extra
```

### DECISIONS LOCKED (resolved during planning — do NOT re-litigate)

1. **C1 (XGBoost) and C2 (Prophet-like) are separate PRPs, branches, and review units.**
   `INITIAL-MLZOO-C` describes both; the MLZOO index now lists them as two rows. This PRP
   touches **only** XGBoost. If you find yourself adding a Prophet-like model, stop — that
   is `PRPs/PRP-MLZOO-C2-prophet-like-additive-model.md`. (User-confirmed.)

2. **XGBoost ships as an optional dependency group, not a core dependency.** A new
   `[project.optional-dependencies] ml-xgboost = ["xgboost>=2.1.0"]`. Rationale: mirrors
   the merged `ml-lightgbm` decision (PRP-30 DECISIONS LOCKED #1); the single-host vision
   keeps the core install dependency-light; `INITIAL-MLZOO-index.md` mandates dependency
   groups (`ml-xgboost` is named there). CI's `--all-extras` installs and tests it. (User-
   confirmed.)

3. **The `xgboost` import is LAZY — inside `fit()`, never at module scope.** `models.py`
   is imported by every forecasting code path (baseline models included); a module-level
   `import xgboost` would make every forecast path require the optional extra. Mirror
   `LightGBMForecaster` exactly: `model_factory` and `XGBoostForecaster.__init__` only
   store parameters; `import xgboost` happens the first time `fit()` runs.
   `requires_features` is a `ClassVar` → readable with no import.

4. **`XGBoostModelConfig` is CONSERVATIVE — `n_estimators` / `max_depth` /
   `learning_rate` / `feature_config_hash` only.** It mirrors `LightGBMModelConfig`
   (PRP-30 DECISIONS LOCKED #3). `subsample` / `colsample_bytree` / `reg_alpha` /
   `reg_lambda` (named in `docs/optional-features/05-advanced-ml-model-zoo.md`) are a
   deliberate future-PRP extension — adding them now widens the schema surface for no MVP
   value, AND `subsample`/`colsample_bytree` < 1.0 introduce stochastic row/column
   sampling that complicates the determinism guarantee. The forecaster uses XGBoost
   defaults for every parameter not in the config (so `subsample`/`colsample_bytree` stay
   at 1.0 → no stochastic sampling). (User-confirmed: "Conservative (match LightGBM)".)

5. **Backtesting needs NO backtesting-service change.** Unlike PRP-30 (which deferred
   backtesting to B.2), B.2 is merged: `backtesting/service.py` probes
   `requires_features` and is fully model-agnostic. An XGBoost model backtests for free.
   This PRP only adds the `xgboost` branch to `JobService._execute_backtest` (the job
   layer still maps a `model_type` string → a config object).

6. **No new leakage test.** XGBoost reuses `_build_regression_features` /
   `_assemble_regression_rows` (historical frame) and the shared `app/shared/feature_frames`
   builders (future + per-fold frames) byte-for-byte. Those are pinned by the load-bearing
   `test_regression_features_leakage.py` and `app/shared/feature_frames/tests/test_leakage.py`.
   XGBoost is leakage-covered by construction; a duplicate XGBoost-flavoured leakage test
   would test the same code twice. State the reuse explicitly in the PR description.

7. **Determinism: `n_jobs=1` + `tree_method="hist"` + fixed `random_state` + conservative
   config (no subsample/colsample).** XGBoost has no `deterministic`/`force_col_wise`
   switch (LightGBM does). Single-threaded `hist` with a fixed seed and no stochastic
   sampling is bit-reproducible within one hardware+build environment — which is exactly
   the determinism unit test's scope. Keep `np.testing.assert_array_equal` (the repo
   idiom). See Gotchas for the residual-risk note.

8. **`POST /forecasting/predict` is NOT changed.** An XGBoost model is feature-aware
   (`requires_features=True`) and is rejected by the existing capability-based predict
   branch — identical to `regression`/`lightgbm`. It forecasts through
   `POST /scenarios/simulate`.

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: lazy import. `import xgboost` goes INSIDE XGBoostForecaster.fit(), not at the
#   top of models.py and not in __init__. models.py is imported for naive/seasonal/mavg/
#   regression/lightgbm too; a module-level xgboost import would make every forecast path
#   require the optional extra. Mirror LightGBMForecaster.fit (models.py:657-659).

# CRITICAL: determinism. XGBoost has NO `deterministic=True` flag. Pin n_jobs=1 +
#   tree_method="hist" + a fixed random_state, and rely on the conservative config leaving
#   subsample/colsample_bytree at their 1.0 defaults (no stochastic sampling). Single-
#   threaded `hist` is bit-reproducible within one environment — which is the
#   test_determinism_same_random_state scope. Keep np.testing.assert_array_equal.
#   IF (and only if) that test proves genuinely flaky in CI across runs on the SAME
#   environment, that is a real signal — investigate the XGBoost build, do NOT paper over
#   it by switching to assert_allclose. (Cross-environment bit-equality is never promised
#   and is not what the test checks.)

# GOTCHA: mypy --strict + warn_unused_ignores=true. xgboost ships a py.typed marker, so
#   `import xgboost` resolves WITHOUT an override in most cases. Start WITHOUT a
#   [[tool.mypy.overrides]] xgboost.* block. ONLY if `uv run mypy app/` flags xgboost.*
#   internals, add `module = ["xgboost.*"]  ignore_missing_imports = true` (mirroring the
#   lightgbm.* override at pyproject.toml:150-152). Do NOT add both an override AND an
#   inline `# type: ignore` — warn_unused_ignores would flag the redundant one. Type the
#   estimator `Any` (mirror `estimator: Any = lgb.LGBMRegressor(...)` at models.py:661).

# GOTCHA: pyright --strict excludes tests/ but scans app/. With ml-xgboost installed
#   (CI: --all-extras; locally: Validation Level 0) pyright resolves `import xgboost`.
#   reportUnknownMemberType is already "warning" (pyproject:177) so dynamic XGBRegressor
#   attribute access does not fail the gate.

# GOTCHA: uv.lock + --frozen. CI installs with `uv sync --frozen` — `--frozen` REFUSES to
#   update the lockfile. After editing pyproject.toml you MUST run `uv lock` and commit the
#   refreshed uv.lock, or every CI job fails at the install step.

# GOTCHA: tests must not hard-require the optional dep. test_xgboost_forecaster.py starts
#   with `pytest.importorskip("xgboost")` so a dev who ran `uv sync --extra dev` (no
#   ml-xgboost) sees the suite SKIP, not ERROR. CI installs --all-extras so it RUNS there.

# GOTCHA: loading an XGBoost bundle requires the ml-xgboost extra. joblib.load unpickles
#   the embedded XGBRegressor, which needs `xgboost` importable. Inherent to an optional
#   ML dependency — document it; do not engineer around it.

# GOTCHA: silence training output with `verbosity=0` in the XGBRegressor constructor
#   (default is 1 = warnings). `verbose` is a fit() arg for eval-set printing, not a
#   constructor param — not needed here (no eval_set).

# GOTCHA: line endings — repo has mixed CRLF/LF, no .gitattributes. Run `git diff --stat`
#   before committing; if a modified file shows a whole-file diff, re-normalise to its
#   original ending so the review shows only the real change.

# SIBLING-PRP integration: PRP-MLZOO-C2 also edits the ModelType Literal (models.py:736)
#   and the ModelConfig union (schemas.py:192-199). Both edits are purely additive (one
#   new literal entry, one new union member). If C2 merged first you will see its
#   "prophet_like" entry already present — just add "xgboost" alongside. A trivial
#   one-line rebase, never a semantic conflict.
```

---

## Implementation Blueprint

### Data models and structure

No ORM model, no migration. One new Pydantic schema and one new forecaster class:

```python
# app/features/forecasting/schemas.py — mirrors LightGBMModelConfig (schemas.py:107-144)

class XGBoostModelConfig(ModelConfigBase):
    """Configuration for the XGBoost regressor (feature-flagged).

    XGBoost is an advanced, feature-aware gradient-boosted-tree model. Like
    ``LightGBMModelConfig`` the field set is deliberately conservative —
    ``n_estimators`` / ``max_depth`` / ``learning_rate`` only — so the schema
    surface stays small and training stays deterministic (no stochastic
    subsampling). Only available when ``forecast_enable_xgboost=True``.
    """

    model_type: Literal["xgboost"] = "xgboost"
    n_estimators: int = Field(default=100, ge=10, le=1000, description="Number of boosting rounds")
    max_depth: int = Field(default=6, ge=1, le=20, description="Maximum depth of trees")
    learning_rate: float = Field(
        default=0.1, ge=0.001, le=1.0, description="Learning rate for gradient boosting"
    )
    feature_config_hash: str | None = Field(
        default=None, description="Hash of FeatureSetConfig used for training"
    )


# app/features/forecasting/models.py — mirrors LightGBMForecaster (models.py:580-732)

class XGBoostForecaster(BaseForecaster):
    """Feature-aware forecaster wrapping ``xgboost.XGBRegressor``.

    The second ADVANCED feature-aware tree model (MLZOO-C1). Structurally a
    twin of ``LightGBMForecaster``: REQUIRES a non-``None`` exogenous ``X`` for
    both ``fit`` and ``predict``; ``xgboost`` is imported LAZILY inside ``fit``.

    Determinism: ``XGBRegressor`` has no ``deterministic`` switch — bit-
    reproducibility comes from ``n_jobs=1`` + ``tree_method="hist"`` + a fixed
    ``random_state`` + the conservative config leaving ``subsample`` /
    ``colsample_bytree`` at 1.0 (no stochastic sampling). XGBoost tolerates
    ``NaN`` natively (``missing=np.nan``).
    """

    requires_features: ClassVar[bool] = True

    def __init__(
        self, *, n_estimators: int = 100, learning_rate: float = 0.1,
        max_depth: int = 6, random_state: int = 42,
    ) -> None:
        super().__init__(random_state)
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self._estimator: Any = None
```

### list of tasks (dependency-ordered)

```yaml
# ════════ STEP 1 — Optional dependency + runtime flag ════════

Task 1 — MODIFY pyproject.toml + regenerate uv.lock:
  - ADD under [project.optional-dependencies], after the `ml-lightgbm` line (pyproject:47):
        # Opt-in advanced forecasting model (MLZOO-C1). Same optional-extra
        # pattern as ml-lightgbm; CI installs it via --all-extras.
        ml-xgboost = ["xgboost>=2.1.0"]
  - DO NOT add a [[tool.mypy.overrides]] xgboost.* block yet — xgboost ships py.typed.
        Add it ONLY if Validation Level 2 (mypy --strict) complains about xgboost.*.
  - RUN `uv lock` to refresh uv.lock (CI uses `uv sync --frozen`).
  - RUN `uv sync --extra dev --extra ml-lightgbm --extra ml-xgboost` locally.
  - VALIDATE: uv run python -c "import xgboost; print(xgboost.__version__)"

Task 2 — MODIFY app/core/config.py — add the runtime flag:
  - ADD after `forecast_enable_lightgbm: bool = False` (config.py:101):
        forecast_enable_xgboost: bool = False
  - Mirror the surrounding comment style of the Forecasting settings block.
  - VALIDATE: uv run python -c "from app.core.config import get_settings; \
        print(get_settings().forecast_enable_xgboost)"

# ════════ STEP 2 — Schema ════════

Task 3 — MODIFY app/features/forecasting/schemas.py — ADD XGBoostModelConfig:
  - PLACE the new class immediately AFTER LightGBMModelConfig (after schemas.py:144),
        BEFORE RegressionModelConfig.
  - MIRROR LightGBMModelConfig field-for-field (see Data models above).
  - ADD `XGBoostModelConfig` to the ModelConfig union (schemas.py:192-199), e.g. between
        LightGBMModelConfig and RegressionModelConfig.
  - VALIDATE: uv run mypy app/features/forecasting/schemas.py

# ════════ STEP 3 — The forecaster + factory ════════

Task 4 — MODIFY app/features/forecasting/models.py — ADD XGBoostForecaster:
  - PLACE the new class immediately AFTER LightGBMForecaster (after models.py:732),
        BEFORE the `ModelType` alias (models.py:736).
  - MIRROR LightGBMForecaster byte-for-byte: __init__ shape, fit guards (X is None ->
        ValueError "XGBoostForecaster requires exogenous features X for fit()"; empty y ->
        "Cannot fit on empty array"; row mismatch -> f"X has {X.shape[0]} rows but y has
        {len(y)} — feature/target rows must match"), predict guards (not fitted ->
        RuntimeError "Model must be fitted before predict"; X is None -> ValueError
        "XGBoostForecaster requires exogenous features X for predict()"; shape mismatch ->
        f"X has {X.shape[0]} rows but horizon is {horizon} — they must match"),
        get_params, set_params.
  - INSIDE fit(): `import xgboost as xgb` (LAZY), then
        `estimator: Any = xgb.XGBRegressor(n_estimators=self.n_estimators,
        learning_rate=self.learning_rate, max_depth=self.max_depth,
        random_state=self.random_state, n_jobs=1, tree_method="hist", verbosity=0)`;
        `estimator.fit(X, y)`.
  - set requires_features: ClassVar[bool] = True.
  - get_params returns {n_estimators, learning_rate, max_depth, random_state}.
  - PRESERVE the error-message substrings EXACTLY — the cloned tests `match=` on them.
  - VALIDATE: uv run mypy app/features/forecasting/models.py && uv run pyright app/features/forecasting/

Task 5 — MODIFY app/features/forecasting/models.py — ModelType literal + model_factory:
  - ADD "xgboost" to the ModelType Literal (models.py:736):
        ModelType = Literal["naive", "seasonal_naive", "moving_average", "xgboost",
                            "lightgbm", "regression"]
  - ADD an `elif model_type == "xgboost":` branch to model_factory, mirroring the
        lightgbm branch (models.py:778-792) — gate FIRST on forecast_enable_xgboost:
            elif model_type == "xgboost":
                if not settings.forecast_enable_xgboost:
                    raise ValueError(
                        "XGBoost is not enabled. Set forecast_enable_xgboost=True in settings."
                    )
                from app.features.forecasting.schemas import XGBoostModelConfig
                if isinstance(config, XGBoostModelConfig):
                    return XGBoostForecaster(
                        n_estimators=config.n_estimators,
                        learning_rate=config.learning_rate,
                        max_depth=config.max_depth,
                        random_state=random_state,
                    )
                raise ValueError("Invalid config type for xgboost")
  - VALIDATE: uv run mypy app/ && uv run pyright app/

# ════════ STEP 4 — Route gate ════════

Task 6 — MODIFY app/features/forecasting/routes.py — add the xgboost flag gate:
  - ADD, immediately after the lightgbm gate (routes.py:67-72), a parallel gate:
        if request.config.model_type == "xgboost" and not settings.forecast_enable_xgboost:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="XGBoost is disabled. Set forecast_enable_xgboost=True in settings.",
            )
  - VALIDATE: uv run mypy app/features/forecasting/ && uv run pyright app/features/forecasting/

# ════════ STEP 5 — Jobs integration ════════

Task 7 — MODIFY app/features/jobs/service.py — _execute_train + _execute_backtest:
  - ADD `XGBoostModelConfig` to the forecasting-schemas import block (jobs/service.py:426-433).
  - ADD an xgboost branch to the _execute_train if/elif chain (jobs/service.py:454-478),
        BEFORE the final `else`, mirroring the lightgbm branch:
            elif model_type == "xgboost":
                # forecast_enable_xgboost gate lives in model_factory — a disabled
                # flag surfaces as a loud failed job.
                config = XGBoostModelConfig(
                    n_estimators=params.get("n_estimators", 100),
                    learning_rate=params.get("learning_rate", 0.1),
                    max_depth=params.get("max_depth", 6),
                )
  - ADD an xgboost branch to the _execute_backtest if/elif chain (jobs/service.py:641-658),
        mirroring its lightgbm branch:
            elif model_type == "xgboost":
                # Feature-aware — the backtest builds per-fold leakage-safe X.
                model_config = XGBoostModelConfig()
  - VALIDATE: uv run mypy app/features/jobs/ && uv run pyright app/features/jobs/

# ════════ STEP 6 — Reproducibility metadata ════════

Task 8 — MODIFY app/features/forecasting/persistence.py — ModelBundle.xgboost_version:
  - ADD field to ModelBundle (after `lightgbm_version: str | None = None`, persistence.py:56):
        xgboost_version: str | None = None
  - UPDATE the ModelBundle docstring Attributes block to mention xgboost_version (mirror
        the lightgbm_version wording at persistence.py:43-44).
  - In save_model_bundle, AFTER the lightgbm best-effort capture (persistence.py:102-108),
        ADD an identical block:
            try:
                import xgboost
                bundle.xgboost_version = str(xgboost.__version__)
            except ImportError:
                bundle.xgboost_version = None
  - In load_model_bundle, AFTER the lightgbm mismatch-warning block (persistence.py:185-199),
        ADD an identical block logging `forecasting.xgboost_version_mismatch` (saved vs
        current) only when both are non-None and differ; guard the current-version lookup
        in try/except ImportError.
  - compute_hash (persistence.py:59-72) is unchanged — confirm no bundle hash shifts.
  - VALIDATE: uv run mypy app/features/forecasting/ && uv run pyright app/features/forecasting/

Task 9 — MODIFY app/features/registry/service.py — _capture_runtime_info:
  - ADD, after the lightgbm block (registry/service.py:124-129):
        # XGBoost is an optional dependency — only recorded when installed.
        try:
            import xgboost
            runtime_info["xgboost_version"] = xgboost.__version__
        except ImportError:
            pass
  - VALIDATE: uv run mypy app/features/registry/ && uv run pyright app/features/registry/

# ════════ STEP 7 — Tests ════════

Task 10 — CREATE app/features/forecasting/tests/test_xgboost_forecaster.py:
  - CLONE test_lightgbm_forecaster.py 1:1. Module-scope `pytest.importorskip("xgboost")`.
  - Swap LightGBMForecaster -> XGBoostForecaster, LightGBMModelConfig -> XGBoostModelConfig,
        forecast_enable_lightgbm -> forecast_enable_xgboost throughout.
  - COPY the `_synthetic_data` helper verbatim.
  - Keep test_determinism_same_random_state with np.testing.assert_array_equal.
  - VALIDATE: uv run pytest -v app/features/forecasting/tests/test_xgboost_forecaster.py

Task 11 — MODIFY app/features/forecasting/tests/test_service.py:
  - In TestFeatureAwareContract.test_requires_features_flag, ADD:
        from app.features.forecasting.models import XGBoostForecaster
        assert XGBoostForecaster.requires_features is True
  - ADD test_xgboost_factory_respects_flag mirroring test_lightgbm_factory_respects_flag
        (flag off -> ValueError "not enabled"; flag on -> isinstance XGBoostForecaster).
  - VALIDATE: uv run pytest -v -m "not integration" app/features/forecasting/tests/test_service.py

Task 12 — MODIFY app/features/forecasting/tests/test_routes.py:
  - ADD test_train_xgboost_rejected_when_disabled: POST /forecasting/train with
        config={"model_type":"xgboost"} and forecast_enable_xgboost at its default (False)
        -> 400, problem+json detail mentioning XGBoost disabled. Mirror the lightgbm route
        test if one exists; otherwise follow the file's ASGITransport client fixture idiom.
  - VALIDATE: uv run pytest -v app/features/forecasting/tests/test_routes.py

Task 13 — MODIFY app/features/jobs/tests/test_service.py:
  - ADD test_execute_train_builds_xgboost_config mirroring
        test_execute_train_builds_lightgbm_config (lines 222-241).
  - ADD test_execute_backtest_builds_xgboost_config mirroring
        test_execute_backtest_builds_lightgbm_config (lines 286-304).
  - The rejects-unsupported test (lines 243-249) already uses "arima" — DO NOT touch it.
  - VALIDATE: uv run pytest -v app/features/jobs/tests/test_service.py

Task 14 — MODIFY app/features/forecasting/tests/test_persistence.py:
  - ADD test_xgboost_version_recorded: after `pytest.importorskip("xgboost")`, save a
        ModelBundle and assert `bundle.xgboost_version` is a non-empty str.
  - VALIDATE: uv run pytest -v -m "not integration" app/features/forecasting/tests/test_persistence.py

Task 15 — MODIFY app/features/scenarios/tests/test_routes_integration.py:
  - ADD an integration test that trains an `xgboost` model then POSTs /scenarios/simulate
        with its run_id and asserts the response `method == "model_exogenous"`. Mirror the
        existing lightgbm/regression model_exogenous test; gate with
        `pytest.importorskip("xgboost")` and enable forecast_enable_xgboost.
  - VALIDATE: uv run pytest -v -m integration app/features/scenarios/tests/test_routes_integration.py

Task 16 — MODIFY app/features/backtesting/tests/test_feature_aware_backtest.py:
  - ADD a light test that runs the feature-aware backtest with an XGBoostModelConfig and
        asserts per-fold metrics + `feature_aware=True` — mirroring
        test_feature_aware_backtest_produces_per_fold_metrics. Gate with
        `pytest.importorskip("xgboost")` and enable forecast_enable_xgboost. This satisfies
        INITIAL-MLZOO-B's "backtesting integration test comparing baseline and advanced
        model path" for the XGBoost model.
  - VALIDATE: uv run pytest -v app/features/backtesting/tests/test_feature_aware_backtest.py

Task 17 — MODIFY app/features/registry/tests/test_service.py:
  - ADD/extend a runtime_info test: with `pytest.importorskip("xgboost")` a created run's
        runtime_info contains the `xgboost_version` key. Mirror the lightgbm assertion.
  - VALIDATE: uv run pytest -v app/features/registry/tests/test_service.py

# ════════ STEP 8 — Docs & example ════════

Task 18 — CREATE examples/models/advanced_xgboost.py:
  - CLONE examples/models/advanced_lightgbm.py, swapping LightGBMForecaster ->
        XGBoostForecaster and the docstring/install line (`--extra ml-xgboost`).
  - VALIDATE: uv run python examples/models/advanced_xgboost.py  (requires ml-xgboost)

Task 19 — MODIFY examples/models/model_interface.md + feature_frame_contract.md:
  - model_interface.md: ADDITIVE — add an XGBoostModelConfig entry under "## Model
        Configurations" and an "### XGBoost Forecaster" entry under "## Model Formulas";
        note requires_features=True and the ml-xgboost optional extra.
  - feature_frame_contract.md: ADDITIVE — record XGBoost as an IMPLEMENTED feature-aware
        model in the relevant sentence/list. Do NOT rewrite the file.
  - VALIDATE: uv run ruff check . && uv run ruff format --check .

Task 20 — MODIFY README.md:
  - ADDITIVE: extend the install-section opt-in note and the Supported Model Types list
        (README.md:344 area) — `xgboost` is an opt-in model installed via
        `uv sync --extra dev --extra ml-xgboost` and enabled with
        `forecast_enable_xgboost=true`. Mirror the existing ml-lightgbm wording.
  - VALIDATE: uv run ruff format --check .   (README is markdown — visual check only)
```

### Per-task pseudocode (critical details only)

```python
# ── Task 4 — XGBoostForecaster.fit (lazy import + determinism is the crux) ──
def fit(self, y, X=None):
    if X is None:
        raise ValueError("XGBoostForecaster requires exogenous features X for fit()")
    if len(y) == 0:
        raise ValueError("Cannot fit on empty array")
    if X.shape[0] != len(y):
        raise ValueError(
            f"X has {X.shape[0]} rows but y has {len(y)} — feature/target rows must match"
        )
    import xgboost as xgb               # LAZY — optional dependency; never module-scope
    estimator: Any = xgb.XGBRegressor(
        n_estimators=self.n_estimators,
        learning_rate=self.learning_rate,
        max_depth=self.max_depth,
        random_state=self.random_state,
        n_jobs=1,                       # single-threaded — removes float-summation
                                        #   non-determinism (XGBoost has no `deterministic`)
        tree_method="hist",             # explicit; the default, and the reproducible path
        verbosity=0,                    # silence XGBoost training chatter
    )
    estimator.fit(X, y)                 # NaN in X is fine — missing=np.nan is the default
    self._estimator = estimator
    self._last_values = np.asarray(y[-1:], dtype=np.float64)
    self._is_fitted = True
    return self

# predict() is byte-identical to LightGBMForecaster.predict (models.py:677-706),
# only the error-string prefix changes: "XGBoostForecaster requires exogenous features ...".
```

### Integration Points

```yaml
DEPENDENCY:
  - pyproject.toml: + [project.optional-dependencies] ml-xgboost = ["xgboost>=2.1.0"].
  - uv.lock: regenerated by `uv lock` (CI installs with --frozen).
  - CI: NO workflow change — ci.yml already runs `uv sync --frozen --all-extras --dev`.

CONFIG:
  - app/core/config.py: + forecast_enable_xgboost: bool = False (the runtime gate).
  - forecast_random_seed (config.py:97) is the determinism source threaded through
    model_factory — UNCHANGED.

TRAIN / PREDICT / SCENARIOS / BACKTESTING:
  - ForecastingService.train_model, ForecastingService.predict,
    scenarios/service.py, backtesting/service.py — ALL UNCHANGED. Each branches on
    `requires_features`; an XGBoost model (requires_features=True) routes through every
    path automatically.

JOBS:
  - jobs/service.py: + xgboost branch in _execute_train AND _execute_backtest (the job
    layer maps a model_type string -> a config object — the one place a string compare
    still lives by design).

PERSISTENCE / REGISTRY:
  - ModelBundle: + xgboost_version field (best-effort on save, mismatch-warn on load).
    compute_hash unchanged -> no bundle hash shifts.
  - runtime_info JSONB: + "xgboost_version" key when xgboost is importable. NO migration.

NO MIGRATION: this PRP touches no SQLAlchemy model and no Alembic version.
NO API CONTRACT CHANGE: no route path, response schema, or WebSocket frame changes
  (a new request-body `model_type` value is an additive, pre-1.0-permitted change).
```

---

## Validation Loop

### Level 0: Environment

```bash
uv lock                                                  # refresh lock after pyproject edit
uv sync --extra dev --extra ml-lightgbm --extra ml-xgboost
uv run python -c "import xgboost; print('xgboost', xgboost.__version__)"
# Expected: prints a 2.x/3.x version. Without this, mypy/pyright on the lazy import and
# the XGBoost tests cannot run locally (CI installs --all-extras automatically).
```

### Level 1: Syntax & Style

```bash
uv run ruff check . --fix && uv run ruff format --check .
# Expected: no errors. Fix everything before Level 2.
```

### Level 2: Type Checks

```bash
uv run mypy app/        # --strict; gates merge
uv run pyright app/     # --strict; gates merge
# If mypy flags xgboost.* internals, add the [[tool.mypy.overrides]] xgboost.* block
# (see Task 1). Do NOT add both an override and an inline `# type: ignore`.
```

### Level 3: Unit Tests

```bash
uv run pytest -v app/features/forecasting/tests/test_xgboost_forecaster.py
uv run pytest -v -m "not integration" app/features/forecasting/tests/test_service.py
uv run pytest -v app/features/jobs/tests/test_service.py
uv run pytest -v app/features/backtesting/tests/test_feature_aware_backtest.py

# Regression — these must stay green with NO behaviour change
uv run pytest -v -m "not integration" app/features/forecasting/tests/
uv run pytest -v -m "not integration" app/features/backtesting/tests/
uv run pytest -v -m "not integration"          # whole fast suite
# Expected: all green. Every baseline / regression / lightgbm test passes UNEDITED.
# If xgboost is somehow absent, test_xgboost_forecaster.py SKIPS — never ERRORs.
```

### Level 4: Integration Tests

```bash
docker compose up -d && uv run alembic upgrade head
uv run pytest -v -m integration app/features/forecasting/ app/features/scenarios/ \
  app/features/jobs/ app/features/registry/
# CRITICAL: the scenarios xgboost model_exogenous test (Task 15) must report
# method="model_exogenous". No migration in this PRP.
```

### Level 5: Manual Validation (dogfood — REQUIRED)

```bash
# 1. Determinism
uv run python -c "
import numpy as np
from app.features.forecasting.models import XGBoostForecaster
rng = np.random.default_rng(0)
X = rng.normal(size=(80, 14)); y = (3.0 * X[:, 0] + rng.normal(size=80)).astype(np.float64)
a = XGBoostForecaster(random_state=7).fit(y, X).predict(12, X[:12])
b = XGBoostForecaster(random_state=7).fit(y, X).predict(12, X[:12])
np.testing.assert_array_equal(a, b); print('xgboost deterministic OK', a[:3])"

# 2. requires_features
uv run python -c "
from app.features.forecasting.models import XGBoostForecaster
assert XGBoostForecaster.requires_features is True; print('requires_features OK')"

# 3. End-to-end: set FORECAST_ENABLE_XGBOOST=true in .env, restart uvicorn, then
#    POST /forecasting/train with config {"model_type":"xgboost"} -> 200; take the run_id
#    and POST /scenarios/simulate -> ScenarioComparison "method" == "model_exogenous";
#    submit an xgboost backtest job -> completes with per-fold metrics.

# 4. The optional dep stays optional — in a venv WITHOUT ml-xgboost, training a naive
#    model still succeeds and `import app.features.forecasting.models` does not raise.
```

---

## Final Validation Checklist

- [ ] `uv run ruff check .` and `uv run ruff format --check .` clean.
- [ ] `uv run mypy app/` and `uv run pyright app/` clean (both --strict).
- [ ] `uv run pytest -v -m "not integration"` fully green; `test_xgboost_forecaster.py`
      runs (xgboost installed) and passes — never ERRORs.
- [ ] `uv run pytest -v -m integration app/features/{forecasting,scenarios,jobs,registry}/`
      green, including the scenarios `xgboost` `model_exogenous` test.
- [ ] `model_factory(XGBoostModelConfig())` returns an `XGBoostForecaster` with the flag
      on, raises a clear `ValueError` with the flag off.
- [ ] An `xgboost` backtest produces per-fold metrics with **no edit to
      `backtesting/service.py`**.
- [ ] Every baseline / `regression` / `lightgbm` test passes with **no edit**.
- [ ] `uv.lock` is regenerated and committed; the core `[project] dependencies` list is
      UNCHANGED (XGBoost is only in `[project.optional-dependencies]`).
- [ ] No Alembic migration; no route-path/response-schema/WebSocket change.
- [ ] `git diff --stat` shows only intended files — no whole-file CRLF/LF noise diffs.
- [ ] An OPEN GitHub issue exists (`gh issue view <N> --json state` → `OPEN`); commit
      `feat(forecast): add XGBoost feature-aware forecasting model (#<issue>)`; branch
      `feat/forecasting-xgboost-model` off `dev`.
- [ ] The PR description states C1 is one of two MLZOO-C review units and links the
      sibling `PRP-MLZOO-C2`.

---

## Anti-Patterns to Avoid

- ❌ Don't implement the Prophet-like model — that is `PRP-MLZOO-C2`, a separate branch.
- ❌ Don't combine C1 and C2 into one branch or one PR (DECISIONS LOCKED #1).
- ❌ Don't add hyperparameter search, portfolio/global models, or an explainability change.
- ❌ Don't add `xgboost` to the core `[project] dependencies` — it is an OPTIONAL extra.
  Don't `import xgboost` at module scope — lazy-import inside `fit()`.
- ❌ Don't add `subsample` / `colsample_bytree` / `reg_alpha` / `reg_lambda` to
  `XGBoostModelConfig` — DECISIONS LOCKED #4 keeps it conservative (and stochastic
  subsampling would complicate determinism).
- ❌ Don't edit `ForecastingService.train_model` / `predict`, `scenarios/service.py`, or
  `backtesting/service.py` — they already branch on `requires_features`.
- ❌ Don't write a new leakage test — XGBoost reuses the already-pinned shared builders.
- ❌ Don't "fix" a determinism-test flake with `assert_allclose` — pin `n_jobs=1` +
  `tree_method="hist"` + a fixed `random_state` and keep `assert_array_equal`. A genuine
  flake on the same environment is a real signal to investigate, not to silence.
- ❌ Don't forget `uv lock` — CI's `uv sync --frozen` fails on a stale lockfile.
- ❌ Don't make `test_xgboost_forecaster.py` hard-require the extra — `pytest.importorskip`.

## Open Questions — RESOLVED

`INITIAL-MLZOO-C`'s open points are resolved for the XGBoost half:
- **Scope** → XGBoost only; Prophet-like is the sibling PRP-MLZOO-C2 (DECISIONS LOCKED #1).
- **Dependency strategy** → optional `ml-xgboost` extra (#2), mirroring `ml-lightgbm`.
- **Config fields** → conservative, matching `LightGBMModelConfig` (#4).
- **Determinism** → `n_jobs=1` + `tree_method="hist"` + fixed seed + no stochastic
  sampling (#7); residual cross-environment non-determinism is documented, not tested.
- **Holiday/regressor features** → already carried as columns in the canonical 14-column
  frame (`is_holiday`, `price_factor`, `promo_active`); no XGBoost-specific handling.

Nothing is left to litigate at implementation time.

## Confidence Score

**9 / 10** for one-pass implementation success.

Rationale: this is the lowest-risk PRP in the MLZOO sequence. The merged `LightGBMForecaster`
(PRP-30) is a *proven, tested* template — `XGBoostForecaster` is a near-mechanical clone
with two library swaps (`lgb.LGBMRegressor` → `xgb.XGBRegressor`, and
`deterministic/force_col_wise` → `tree_method="hist"`). Every consuming path —
train, predict, scenarios, **backtesting** — already branches on `requires_features`, so the
only genuinely new wiring is two `model_factory`/jobs branches and the metadata field. The
−1 risk is XGBoost determinism: unlike LightGBM there is no `deterministic` flag, so
`assert_array_equal` rests on single-threaded `hist` + fixed seed + no stochastic sampling
being reproducible within one environment — which the research confirms it is, and the
conservative config guarantees no subsampling. The risk is caught immediately by the Level 3
determinism test, and the "every existing test passes unedited" gate makes any accidental
regression impossible to miss.
