name: "PRP-30 — LightGBM First Advanced Model (MLZOO-B)"
description: |

## Purpose

The second PRP of the **Advanced ML Model Zoo** sequence (`PRPs/INITIAL/INITIAL-MLZOO-index.md`).
It adds the **first advanced, feature-aware forecasting model** — `LightGBMForecaster`,
wrapping `lightgbm.LGBMRegressor` — on top of the leakage-safe shared feature-frame contract
delivered by PRP-29 (MLZOO-A).

This PRP implements **one model**: the LightGBM forecaster, its `model_factory` wiring, its
training path, its scenario `model_exogenous` re-forecast path, and its reproducibility
metadata. It adds **no** new model beyond LightGBM, **no** hyperparameter search, **no**
portfolio/global models, **no** frontend, **no** explainability change, and — by an explicit
scoping decision (see DECISIONS LOCKED #6) — **no** feature-aware backtesting wiring. If you
find yourself touching the backtesting fold loop, stop — that is PRP-MLZOO-B.2.

## What this PRP already inherits (DO NOT re-build)

PRP-29 (MLZOO-A, merged commit `b116489`) already shipped the foundation a feature-aware model
stands on. Re-use it; do not re-derive it:

- **The feature-aware model contract.** `BaseForecaster.requires_features: ClassVar[bool]`
  (`app/features/forecasting/models.py:64`). `RegressionForecaster` (`models.py:438`) is the
  *existing* feature-aware model — `requires_features = True`, `fit(y, X)` / `predict(horizon, X)`
  both require a non-`None` `X`. `LightGBMForecaster` is its structural twin.
- **The shared feature-frame contract.** `app/shared/feature_frames/` owns the pinned
  constants, `canonical_feature_columns()` (the 14-column set), `FutureFeatureFrame`, the
  leakage-safe pure builders, and the `FeatureSafety` taxonomy. A feature-aware model writes
  **zero** new contract code.
- **The training-frame branch.** `ForecastingService.train_model`
  (`app/features/forecasting/service.py:~226`) already branches on `model.requires_features`:
  if true it builds the historical frame via `_build_regression_features` and calls
  `model.fit(features.y, features.X)`, persisting `feature_columns` / `history_tail` /
  `launch_date` into the bundle metadata. **A new feature-aware model trains with zero
  changes to `train_model`.**
- **The predict rejection.** `ForecastingService.predict` (`service.py:~392`) already rejects
  any `requires_features` model — `POST /forecasting/predict` cannot supply an exogenous frame.
  A LightGBM model is rejected there automatically (DECISIONS LOCKED #4 — no predict change).
- **The historical-frame leakage spec.** `app/features/forecasting/tests/test_regression_features_leakage.py`
  pins `_assemble_regression_rows`; `app/shared/feature_frames/tests/test_leakage.py` pins the
  shared builders. LightGBM consumes the **same** builders → these specs already cover its
  training feature matrix and its future feature matrix. **No new leakage test is required**
  (see DECISIONS LOCKED #5).

The **problem this PRP fixes**: `lightgbm` is a dead placeholder. `LightGBMModelConfig`
exists (`schemas.py:107`), `forecast_enable_lightgbm` exists (`config.py:101`), `lightgbm` is
in the `ModelType` literal (`models.py:581`) and the `ModelConfig` union — but `model_factory`
raises `NotImplementedError("LightGBM forecaster not yet implemented")` (`models.py:623-629`),
`lightgbm` is absent from `pyproject.toml`, and `jobs._execute_train` rejects it as an
unsupported `model_type`. There is no advanced model to compare baselines against.

## DEPENDS ON — read before starting

- `PRPs/INITIAL/INITIAL-MLZOO-B-lightgbm-first-model.md` — this PRP's brief.
- `PRPs/INITIAL/INITIAL-MLZOO-index.md` — the MLZOO roadmap (A ✅ → **B (this)** → C → D).
- `PRPs/PRP-29-feature-aware-forecasting-foundation.md` — the merged foundation. Its
  DECISIONS LOCKED #2 (`requires_features` attribute, not a `FeatureAwareForecaster` class)
  and #6 (NaN-as-unknown) are binding here too.
- `PRPs/ai_docs/exogenous-regressor-forecasting.md` — §1 has the `LGBMRegressor` snippet; §2 is
  the leakage rule the shared builders already obey; §5 explains why `regression` shipped on
  scikit-learn first.
- `examples/models/feature_frame_contract.md` — the historical/future frame shapes a
  feature-aware model consumes, and the canonical 14-column set.
- `docs/optional-features/05-advanced-ml-model-zoo.md` — the full model-zoo vision and risks.

---

## Goal

Implement `LightGBMForecaster` — a deterministic, feature-aware forecasting model wrapping
`lightgbm.LGBMRegressor` — and wire it end-to-end: `model_factory` instantiates it (behind the
existing `forecast_enable_lightgbm` flag), `ForecastingService.train_model` trains it through
the existing `requires_features` branch, `POST /scenarios/simulate` re-forecasts it through
`method="model_exogenous"`, `JobService._execute_train` accepts `model_type="lightgbm"`, and
the LightGBM library version is captured in the model bundle and the registry's `runtime_info`.
LightGBM ships as an **optional dependency group** (`ml-lightgbm`); the model code lazy-imports
it so a single-host install without the extra still works for every baseline model.

**End state:** a user with `forecast_enable_lightgbm=True` and the `ml-lightgbm` extra
installed can train a `lightgbm` model (HTTP or job), and re-forecast it in a what-if
scenario, exactly as they can a `regression` model today. Every baseline model and the
`regression` model behave **identically** before and after. Backtesting a feature-aware model
still fails loud (unchanged) — feature-aware backtesting is PRP-MLZOO-B.2.

## Why

- **The model zoo needs a credible advanced model.** `docs/optional-features/05-advanced-ml-model-zoo.md`
  frames the goal as "upgrade ForecastLabAI from baseline forecasting to a credible model
  *comparison* platform". The `regression` model (scikit-learn `HistGradientBoostingRegressor`)
  shipped as the *foundation-prover*; LightGBM is the first model whose presence makes a
  comparison meaningful — it is the industry-standard gradient-boosted tree for tabular retail
  demand on engineered lag/calendar features.
- **The foundation is already paid for.** PRP-29 made the feature-frame contract single-source
  and the train/predict path branch on `requires_features`. Adding a second feature-aware model
  is now a *small, contained* change — the expensive structural work is done.
- **It de-risks the dependency one step at a time.** `INITIAL-MLZOO-index.md` mandates "Add
  LightGBM support behind optional dependency group" before XGBoost/Prophet. This PRP does
  exactly that and no more.
- **Low blast radius.** No migration, no API-contract change, no baseline-model change, no
  new vertical slice. The risk surface is one new class + three small wiring edits + metadata
  + tests.

## What

A backend-only feature PRP. User-visible behaviour gains exactly one thing: `model_type:
"lightgbm"` becomes a real, trainable, scenario-re-forecastable model when the feature flag
and the optional dependency are both present. Everything else is identical.

### Technical requirements

1. **Optional dependency group.** `pyproject.toml` gains `[project.optional-dependencies]
   ml-lightgbm = ["lightgbm>=4.5.0"]`. CI already runs `uv sync --frozen --all-extras --dev`
   (`.github/workflows/ci.yml:48,74,116,163`) so the extra is installed and tested in CI with
   **no workflow change**. `uv.lock` is regenerated (`uv lock`) because CI uses `--frozen`.
2. **`LightGBMForecaster`** in `app/features/forecasting/models.py` — a `BaseForecaster`
   subclass with `requires_features: ClassVar[bool] = True`, structurally mirroring
   `RegressionForecaster`. It lazy-imports `lightgbm` inside `fit()` (not at module load, not
   in `__init__`) so importing `models.py` never requires the optional dependency. It is
   deterministic (`n_jobs=1`, `deterministic=True`, `force_col_wise=True`, fixed
   `random_state`) and NaN-tolerant (LightGBM handles `NaN` natively).
3. **`model_factory`** — the `lightgbm` branch (`models.py:623-629`) replaces its
   `NotImplementedError` with a real `LightGBMForecaster(...)` instantiation, keeping the
   `forecast_enable_lightgbm` gate.
4. **Scenario re-forecast.** `app/features/scenarios/service.py` dispatches the
   `model_exogenous` re-forecast on `bundle.model.requires_features` instead of the hard-coded
   `bundle.config.model_type == "regression"` — so a LightGBM bundle takes the genuine
   re-forecast path, not the heuristic-multiplier fallback.
5. **Jobs integration.** `JobService._execute_train` (`jobs/service.py:453-469`) gains a
   `lightgbm` branch building `LightGBMModelConfig`. `_execute_backtest` is **not** changed —
   it keeps rejecting feature-aware models (backtesting deferred).
6. **Reproducibility metadata.** `ModelBundle` gains a `lightgbm_version: str | None` field
   (best-effort captured on save, mismatch-warned on load — mirroring `sklearn_version`);
   `RegistryService._capture_runtime_info` gains a `lightgbm` version block.
7. **Tests** mirroring the `RegressionForecaster` test suite, gated with
   `pytest.importorskip("lightgbm")`; an `examples/models/advanced_lightgbm.py` minimal
   train/predict example; additive docs.

### Success Criteria

- [ ] `model_factory(LightGBMModelConfig(), random_state=42)` returns a `LightGBMForecaster`
      when `forecast_enable_lightgbm=True`; raises a clear `ValueError` when the flag is off.
- [ ] `LightGBMForecaster.requires_features is True`; `fit`/`predict` require a non-`None` `X`
      and raise the same error-message substrings as `RegressionForecaster`
      (`"requires exogenous features"`, `"rows must match"`, `"horizon"`, `"fitted"`).
- [ ] Two fits with the same `random_state` produce **identical** forecasts
      (`np.testing.assert_array_equal`).
- [ ] `ForecastingService.train_model` trains a `lightgbm` model with **no edit to
      `train_model`** (it routes through the existing `requires_features` branch).
- [ ] `POST /scenarios/simulate` against a trained `lightgbm` run returns
      `method="model_exogenous"` (not `"heuristic"`).
- [ ] `JobService._execute_train` accepts `model_type="lightgbm"`; `_execute_backtest` still
      rejects it with `Unsupported model_type`.
- [ ] `ModelBundle.lightgbm_version` and registry `runtime_info["lightgbm_version"]` are
      captured when `lightgbm` is installed.
- [ ] Every baseline model, the `regression` model, and the backtesting loud-fail guard test
      (`test_feature_aware_model_fails_loud_in_backtest`) pass **with no behaviour change**.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"` all green.
- [ ] No Alembic migration; no route/schema/WebSocket contract change; LightGBM stays an
      *optional* dependency (the core `dependencies` list is unchanged).

---

## All Needed Context

### Documentation & References

```yaml
- file: app/features/forecasting/models.py
  why: RegressionForecaster (lines 438-577) is the BYTE-FOR-BYTE structural template for
       LightGBMForecaster — same __init__ shape, same fit/predict guards, same error strings,
       same get_params/set_params. requires_features ClassVar is at line 64 (base) / 458
       (RegressionForecaster override). model_factory lightgbm branch to replace: lines 623-629.
  critical: The estimator is typed `Any` (see `estimator: Any = HistGradientBoostingRegressor(...)`
       at models.py:510) — mirror that for LGBMRegressor so pyright --strict stays quiet.

- file: app/features/forecasting/schemas.py
  why: LightGBMModelConfig (lines 107-144) ALREADY EXISTS — model_type Literal["lightgbm"],
       n_estimators (10-1000, default 100), max_depth (1-20, default 6), learning_rate
       (0.001-1.0, default 0.1), feature_config_hash. It is already in the ModelConfig union
       (lines 193-199). DO NOT add fields — DECISIONS LOCKED #3 keeps it conservative.

- file: app/features/forecasting/service.py
  why: train_model (~line 226) already branches `if model.requires_features:` → builds the
       historical frame and persists feature metadata. predict (~line 392) already rejects
       feature-aware models. _build_regression_features (lines 503-635) and the pure
       _assemble_regression_rows (lines 114-170) are REUSED unchanged by LightGBM.
  critical: DO NOT EDIT service.py. A LightGBM model trains and is predict-rejected purely
       because requires_features=True. Verify by reading, then leave it alone.

- file: app/features/forecasting/persistence.py
  why: ModelBundle dataclass (lines 30-69) has python_version + sklearn_version (no
       extensible version dict). save_model_bundle captures them at lines 94-98;
       load_model_bundle mismatch-warns at lines 156-172. Add `lightgbm_version` mirroring
       `sklearn_version` exactly. compute_hash (lines ~52-66) does NOT include version fields
       → adding lightgbm_version does not change any bundle hash.

- file: app/features/forecasting/routes.py
  why: POST /forecasting/train (lines 47-131) ALREADY has the lightgbm feature-flag gate at
       lines 67-72 (`model_type == "lightgbm" and not settings.forecast_enable_lightgbm` →
       400). ValueError → 400, FileNotFoundError → 404. No route-code change needed; only a
       new route test.

- file: app/features/scenarios/service.py
  why: The model_exogenous dispatch is hard-coded `if bundle.config.model_type == "regression":`
       (~line 112). CHANGE it to `if bundle.model.requires_features:`. _simulate_model_exogenous
       reads bundle.metadata["feature_columns"]/["history_tail"] and calls
       `bundle.model.predict(horizon, X)` — model-agnostic, no other change.
  critical: grep `app/features/scenarios/` for every `"regression"` / `model_type` check and
       generalise each model-capability check to requires_features. Do not miss agent_tools.py.

- file: app/features/scenarios/feature_frame.py
  why: build_future_frame (lines 232-299) / assemble_future_frame (lines 181-229) produce a
       FutureFeatureFrame for ANY feature_columns list — model-agnostic. LightGBM model_exogenous
       needs ZERO feature-frame code. Read to confirm; do not edit.

- file: app/features/jobs/service.py
  why: _execute_train (lines 409-503) has a model_type if/elif chain (lines 453-469) that
       rejects anything but naive/seasonal_naive/moving_average/regression with
       `ValueError("Unsupported model_type: ...")`. ADD a `lightgbm` branch. _execute_backtest
       (lines 583-668, branch 630-640) keeps rejecting lightgbm — backtesting is deferred.

- file: app/features/registry/service.py
  why: _capture_runtime_info (lines 84-123) best-effort-imports sklearn/numpy/pandas/joblib
       into a runtime_info dict. ADD an identical `try: import lightgbm` block. runtime_info
       is JSONB (registry/models.py) — a new key needs NO migration.

- file: app/features/forecasting/tests/test_regression_forecaster.py
  why: The FULL test template for test_lightgbm_forecaster.py. Clone every test: fit/predict
       roundtrip, rejects-None-X, rejects-mismatched-rows, predict-before-fit, NaN tolerance,
       get/set params, factory creation, and especially test_determinism_same_random_state
       (np.testing.assert_array_equal of two same-seed fits). Copy its `_synthetic_data` helper.

- file: app/features/forecasting/tests/test_service.py
  why: TestFeatureAwareContract (lines 349-385) — test_requires_features_flag and
       test_canonical_columns_match_regression_contract. Extend the first; the second is
       UNCHANGED (LightGBM reuses the same 14-column contract).

- file: app/features/backtesting/tests/test_service.py
  why: test_feature_aware_model_fails_loud_in_backtest (lines 120-152) STAYS — it is the
       interim contract until PRP-MLZOO-B.2 wires feature-aware backtesting. It uses
       RegressionModelConfig and is unaffected by this PRP. Do not touch it.

- file: app/features/jobs/tests/test_service.py
  why: A test around line 218 (`test_..._rejects_unsupported_model_type`) currently uses
       `"lightgbm"` as the genuinely-unsupported type. Once _execute_train accepts lightgbm
       this test is WRONG — swap its payload to a still-unsupported string ("arima").

- url: https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMRegressor.html
  why: LGBMRegressor sklearn-API constructor — n_estimators, learning_rate, max_depth,
       random_state, n_jobs, verbosity. fit(X, y) / predict(X) are sklearn-compatible.

- url: https://lightgbm.readthedocs.io/en/stable/Parameters.html#deterministic
  section: deterministic, force_col_wise, num_threads
  critical: For bit-reproducible trees set deterministic=true AND force_col_wise=true (or
       force_row_wise=true) AND num_threads=1 (LGBMRegressor: n_jobs=1). Without all three a
       multi-threaded fit can differ by ULPs and the determinism test (assert_array_equal)
       flakes. verbosity=-1 silences LightGBM's training chatter.

- docfile: PRPs/ai_docs/exogenous-regressor-forecasting.md
  why: §1 has the exact LGBMRegressor snippet; §5 records why `regression` shipped on
       scikit-learn first — LightGBM was deferred precisely to a later PRP (this one).
```

### Current Codebase tree (relevant — all already exist)

```bash
app/features/forecasting/
├── models.py            # BaseForecaster, RegressionForecaster, model_factory (lightgbm stub)
├── schemas.py           # LightGBMModelConfig (already exists), ModelConfig union
├── service.py           # train_model + predict already branch on requires_features
├── persistence.py       # ModelBundle (python_version + sklearn_version only)
├── routes.py            # /forecasting/train already has the lightgbm flag gate
└── tests/
    ├── conftest.py
    ├── test_regression_forecaster.py        # the test template to clone
    ├── test_service.py                      # TestFeatureAwareContract
    ├── test_routes.py
    ├── test_persistence.py
    └── test_regression_features_leakage.py  # load-bearing — already covers LightGBM's frame
app/features/scenarios/service.py            # model_exogenous dispatch (model_type=="regression")
app/features/jobs/service.py                 # _execute_train rejects lightgbm
app/features/registry/service.py             # _capture_runtime_info (no lightgbm)
app/features/backtesting/tests/test_service.py  # loud-fail guard (stays)
app/shared/feature_frames/                   # the shared contract (PRP-29) — reused, untouched
examples/models/
├── baseline_naive.py / baseline_seasonal.py / baseline_mavg.py
├── model_interface.md
└── feature_frame_contract.md
pyproject.toml                               # lightgbm absent
.github/workflows/ci.yml                     # uv sync --frozen --all-extras --dev (no change)
```

### Desired Codebase tree — files to ADD

```bash
app/features/forecasting/tests/
└── test_lightgbm_forecaster.py     # cloned from test_regression_forecaster.py, importorskip

examples/models/
└── advanced_lightgbm.py            # minimal LightGBM train/predict example (INITIAL-B asks)
```

### Files to MODIFY (all additive or behaviour-preserving)

```bash
pyproject.toml                                  # + [project.optional-dependencies] ml-lightgbm
                                                #   + [[tool.mypy.overrides]] lightgbm.* ignore_missing_imports
uv.lock                                         # regenerated by `uv lock`
app/features/forecasting/models.py              # + LightGBMForecaster; model_factory lightgbm branch
app/features/forecasting/persistence.py         # + ModelBundle.lightgbm_version (save + load)
app/features/scenarios/service.py               # model_type=="regression" -> requires_features
app/features/jobs/service.py                    # _execute_train: + lightgbm branch
app/features/registry/service.py                # _capture_runtime_info: + lightgbm block
app/features/forecasting/__init__.py            # export LightGBMForecaster if RegressionForecaster is exported
app/features/forecasting/tests/test_service.py  # extend test_requires_features_flag
app/features/forecasting/tests/test_routes.py   # + lightgbm 400-when-disabled route test
app/features/forecasting/tests/test_persistence.py  # + lightgbm_version captured assertion
app/features/jobs/tests/test_service.py         # fix rejects-unsupported test; + lightgbm job test
app/features/scenarios/tests/test_routes_integration.py  # + lightgbm model_exogenous test
app/features/registry/tests/test_service.py     # + runtime_info has lightgbm_version
examples/models/model_interface.md              # additive: lightgbm row
examples/models/feature_frame_contract.md       # additive: lightgbm is now a feature-aware model
README.md                                       # additive: the ml-lightgbm optional extra
```

### DECISIONS LOCKED (resolved during planning — do NOT re-litigate)

1. **LightGBM ships as an optional dependency group, not a core/hard dependency.** A new
   `[project.optional-dependencies] ml-lightgbm = ["lightgbm>=4.5.0"]`. Rationale: AGENTS.md
   lists LightGBM as "(opt-in)"; `INITIAL-MLZOO-index.md` mandates "behind optional dependency
   group"; the single-host vision keeps the core install dependency-light. CI runs
   `uv sync --frozen --all-extras --dev` so the extra **is** installed and tested in CI — no
   workflow edit needed. (User-confirmed during PRP planning.)

2. **The sklearn fallback is rejected — it would be a no-op.** `INITIAL-B` offered
   `HistGradientBoostingRegressor` as a fallback, but the `regression` model **already is**
   exactly that (PRP-27). Implementing the fallback would duplicate an existing model and add
   nothing. LightGBM is genuinely implemented. (User-confirmed.)

3. **`LightGBMModelConfig` is used UNCHANGED — conservative config.** It already exists with
   `n_estimators` / `max_depth` / `learning_rate` / `feature_config_hash`. `INITIAL-B` says
   "Keep the first config conservative". `num_leaves` / `min_child_samples` / `subsample` /
   `colsample_bytree` (named in `INITIAL-MLZOO-index.md`) are a deliberate future-PRP
   extension — adding them now widens the schema surface for no MVP value. The forecaster uses
   LightGBM defaults for every parameter not in the config.

4. **`POST /forecasting/predict` is NOT changed.** A LightGBM model is feature-aware
   (`requires_features=True`) and is rejected by the existing predict branch — identical to
   `regression`. It forecasts through `POST /scenarios/simulate`. This answers INITIAL-B's
   "How prediction rejects missing future feature frames": the rejection already exists and is
   capability-based (`requires_features`), not `model_type`-string-based.

5. **No new leakage test.** LightGBM reuses `_build_regression_features` /
   `_assemble_regression_rows` (historical frame) and the shared `app/shared/feature_frames`
   builders (future frame) **byte-for-byte**. Those are already pinned by the load-bearing
   `app/features/forecasting/tests/test_regression_features_leakage.py` and
   `app/shared/feature_frames/tests/test_leakage.py`. The model is leakage-covered by
   construction; a duplicate LightGBM-flavoured leakage test would test the same code twice.
   The PRP MUST state this reuse explicitly so the reviewer sees the coverage is intact.

6. **Feature-aware backtesting is OUT OF SCOPE — deferred to PRP-MLZOO-B.2.** The backtest
   fold loop (`backtesting/service.py::_run_model_backtest`) is synchronous, DB-free, and
   loads target quantities only; wiring per-fold leakage-safe `X_train`/`X_future` builders is
   itself PRP-sized. `test_feature_aware_model_fails_loud_in_backtest` stays as the interim
   loud-fail contract. `JobService._execute_backtest` keeps rejecting `lightgbm`.
   (User-confirmed: "Defer to a follow-up PRP".)

7. **The `lightgbm` import is LAZY — inside `fit()`, never at module scope.** Importing
   `app/features/forecasting/models.py` must never require the optional dependency (the module
   is imported by every forecasting code path, baseline models included). `model_factory` and
   `LightGBMForecaster.__init__` only store parameters; `import lightgbm` happens the first
   time `fit()` runs. `requires_features` is a `ClassVar` → readable with no import.

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: lazy import. `import lightgbm` goes INSIDE LightGBMForecaster.fit(), not at the
#   top of models.py and not in __init__. models.py is imported for naive/seasonal/mavg too;
#   a module-level lightgbm import would make every forecast path require the optional extra.

# CRITICAL: determinism. LGBMRegressor is reproducible ONLY with n_jobs=1 AND
#   deterministic=True AND force_col_wise=True AND a fixed random_state. Omit any one and a
#   multi-threaded fit differs by ULPs → test_determinism_same_random_state (which uses
#   np.testing.assert_array_equal — EXACT equality, the repo idiom) flakes in CI. Do not
#   "fix" a flake by switching to assert_allclose — fix the LGBMRegressor params.

# GOTCHA: mypy --strict + warn_unused_ignores=true. lightgbm has incomplete type information.
#   Add a `[[tool.mypy.overrides]] module=["lightgbm.*"] ignore_missing_imports=true` block to
#   pyproject.toml. With that, do NOT also add an inline `# type: ignore[import-untyped]` — the
#   override handles it and an unused inline ignore is itself a mypy error. Type the estimator
#   `Any` (mirror `estimator: Any = HistGradientBoostingRegressor(...)` at models.py:510).

# GOTCHA: pyright --strict excludes tests/ (pyproject [tool.pyright] exclude) but scans app/.
#   With the ml-lightgbm extra installed (CI: --all-extras; locally: see Validation Level 0)
#   pyright resolves `import lightgbm`. reportUnknownMemberType is already "warning" not
#   "error" (pyproject:169) so dynamic LGBMRegressor attribute access does not fail the gate.

# GOTCHA: uv.lock + --frozen. CI installs with `uv sync --frozen` — `--frozen` REFUSES to
#   update the lockfile. After editing pyproject.toml you MUST run `uv lock` and commit the
#   refreshed uv.lock, or every CI job fails at the install step.

# GOTCHA: tests must not hard-require the optional dep. test_lightgbm_forecaster.py starts with
#   `pytest.importorskip("lightgbm")` so a dev who ran `uv sync --extra dev` (no ml-lightgbm)
#   sees the suite SKIP, not ERROR. CI installs --all-extras so the tests RUN there.

# GOTCHA: jobs/tests/test_service.py ~line 218 — a test asserts `model_type="lightgbm"` is
#   rejected as unsupported. After _execute_train gains a lightgbm branch that assertion is
#   false. Swap the test payload to a string that is genuinely unsupported, e.g. "arima".

# GOTCHA: loading a LightGBM bundle requires the ml-lightgbm extra. joblib.load unpickles the
#   embedded LGBMRegressor, which needs `lightgbm` importable. This is inherent to an optional
#   ML dependency — document it; do not try to engineer around it.

# GOTCHA: scenarios dispatch. The model_exogenous re-forecast is gated `if
#   bundle.config.model_type == "regression":`. A LightGBM bundle would silently fall through
#   to the heuristic multiplier. Change it to `if bundle.model.requires_features:` — the
#   repo's own forecasting/service.py already branches on exactly that flag.

# GOTCHA: line endings — repo has mixed CRLF/LF, no .gitattributes. Run `git diff --stat`
#   before committing; if a modified file shows a whole-file diff, re-normalise to its
#   original ending so the review shows only the real change.
```

---

## Implementation Blueprint

### Data models and structure

No ORM model, no Pydantic schema change, no migration. `LightGBMModelConfig` already exists
and is used as-is (DECISIONS LOCKED #3). The only new structured type is the forecaster class:

```python
# app/features/forecasting/models.py — mirrors RegressionForecaster (models.py:438-577)

class LightGBMForecaster(BaseForecaster):
    """Feature-aware forecaster wrapping ``lightgbm.LGBMRegressor``.

    The first ADVANCED feature-aware model (MLZOO-B). Like RegressionForecaster
    it REQUIRES a non-None exogenous X for both fit and predict; unlike it, the
    estimator is gradient-boosted leaf-wise trees from the optional ``lightgbm``
    package. ``lightgbm`` is imported lazily inside ``fit`` so importing this
    module never requires the optional dependency.
    """

    requires_features: ClassVar[bool] = True

    def __init__(self, *, n_estimators: int = 100, learning_rate: float = 0.1,
                 max_depth: int = 6, random_state: int = 42) -> None:
        super().__init__(random_state)
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self._estimator: Any = None
```

### list of tasks (dependency-ordered)

```yaml
# ════════ STEP 1 — Optional dependency ════════

Task 1 — MODIFY pyproject.toml + regenerate uv.lock:
  - ADD under [project.optional-dependencies], after the `dev` group:
        ml-lightgbm = ["lightgbm>=4.5.0"]
  - ADD a new mypy override block (after the existing alembic override, ~line 145):
        [[tool.mypy.overrides]]
        module = ["lightgbm.*"]
        ignore_missing_imports = true
  - RUN `uv lock` to refresh uv.lock (CI uses `uv sync --frozen` — a stale lock fails CI).
  - RUN `uv sync --extra dev --extra ml-lightgbm` locally so the gates can see lightgbm.
  - VALIDATE: uv run python -c "import lightgbm; print(lightgbm.__version__)"

# ════════ STEP 2 — The forecaster + factory ════════

Task 2 — MODIFY app/features/forecasting/models.py — ADD LightGBMForecaster:
  - PLACE the new class immediately AFTER RegressionForecaster (after models.py:577),
      BEFORE the `ModelType` alias.
  - MIRROR RegressionForecaster byte-for-byte for: __init__ shape (keyword-only params +
      random_state, `self._estimator: Any = None`), the fit guards (X is None → ValueError
      "LightGBMForecaster requires exogenous features X for fit()"; empty y → ValueError
      "Cannot fit on empty array"; row mismatch → ValueError f"X has {X.shape[0]} rows but y
      has {len(y)} — feature/target rows must match"), the predict guards (not fitted →
      RuntimeError "Model must be fitted before predict"; X is None → ValueError
      "LightGBMForecaster requires exogenous features X for predict()"; shape mismatch →
      ValueError f"X has {X.shape[0]} rows but horizon is {horizon} — they must match"),
      get_params, set_params.
  - INSIDE fit(): `import lightgbm as lgb` (lazy), then
      `estimator: Any = lgb.LGBMRegressor(n_estimators=self.n_estimators,
      learning_rate=self.learning_rate, max_depth=self.max_depth,
      random_state=self.random_state, n_jobs=1, deterministic=True,
      force_col_wise=True, verbosity=-1)`; `estimator.fit(X, y)`.
  - set requires_features: ClassVar[bool] = True (with the one-line docstring).
  - get_params returns {n_estimators, learning_rate, max_depth, random_state}.
  - PRESERVE the error-message substrings EXACTLY — the cloned tests `match=` on them.
  - VALIDATE: uv run mypy app/features/forecasting/models.py && uv run pyright app/features/forecasting/

Task 3 — MODIFY app/features/forecasting/models.py — model_factory lightgbm branch:
  - REPLACE the body of `elif model_type == "lightgbm":` (currently models.py:623-629,
      the `NotImplementedError`) with:
        if not settings.forecast_enable_lightgbm:
            raise ValueError("LightGBM is not enabled. Set forecast_enable_lightgbm=True in settings.")
        from app.features.forecasting.schemas import LightGBMModelConfig
        if isinstance(config, LightGBMModelConfig):
            return LightGBMForecaster(
                n_estimators=config.n_estimators,
                learning_rate=config.learning_rate,
                max_depth=config.max_depth,
                random_state=random_state,
            )
        raise ValueError("Invalid config type for lightgbm")
  - KEEP the forecast_enable_lightgbm gate FIRST (the route relies on it; tests rely on it).
  - VALIDATE: uv run mypy app/ && uv run pyright app/

Task 4 — MODIFY app/features/forecasting/__init__.py:
  - IF `RegressionForecaster` is imported/__all__-listed there, ADD `LightGBMForecaster`
      alongside it (same import line + __all__). IF RegressionForecaster is NOT exported,
      make NO change (match the existing convention exactly).
  - VALIDATE: uv run ruff check app/features/forecasting/__init__.py

# ════════ STEP 3 — Scenario re-forecast path ════════

Task 5 — MODIFY app/features/scenarios/service.py — generalise the model_exogenous dispatch:
  - FIND `if bundle.config.model_type == "regression":` (~service.py:112) and CHANGE the
      condition to `if bundle.model.requires_features:`.
  - GREP `app/features/scenarios/` for every other `"regression"` / `model_type ==` check
      (service.py, agent_tools.py, schemas.py): any check that means "is this model
      feature-aware / re-forecastable" becomes `requires_features`; a check that is genuinely
      regression-specific (none expected) stays. Report what you found in the PR description.
  - DO NOT change feature_frame.py — build_future_frame is already model-agnostic.
  - VALIDATE: uv run mypy app/features/scenarios/ && uv run pyright app/features/scenarios/

# ════════ STEP 4 — Jobs integration ════════

Task 6 — MODIFY app/features/jobs/service.py — _execute_train:
  - ADD `LightGBMModelConfig` to the forecasting-schemas import block (jobs/service.py:426-431).
  - ADD a branch in the model_type if/elif chain (jobs/service.py:453-469), BEFORE the
      final `else: raise ValueError("Unsupported model_type: ...")`:
        elif model_type == "lightgbm":
            config = LightGBMModelConfig(
                n_estimators=params.get("n_estimators", 100),
                learning_rate=params.get("learning_rate", 0.1),
                max_depth=params.get("max_depth", 6),
            )
  - DO NOT touch _execute_backtest (jobs/service.py:583-668) — it keeps rejecting lightgbm;
      feature-aware backtesting is PRP-MLZOO-B.2 (DECISIONS LOCKED #6).
  - NOTE: _execute_train does not check forecast_enable_lightgbm — model_factory does. A
      lightgbm job with the flag off fails LOUD ("LightGBM is not enabled"). That is correct.
  - VALIDATE: uv run mypy app/features/jobs/ && uv run pyright app/features/jobs/

# ════════ STEP 5 — Reproducibility metadata ════════

Task 7 — MODIFY app/features/forecasting/persistence.py — ModelBundle.lightgbm_version:
  - ADD field to ModelBundle (after `sklearn_version: str | None = None`):
        lightgbm_version: str | None = None
  - In save_model_bundle (near persistence.py:94-98), AFTER `bundle.sklearn_version = ...`,
      ADD a best-effort capture (mirror RegistryService._capture_runtime_info's idiom):
        try:
            import lightgbm
            bundle.lightgbm_version = str(lightgbm.__version__)
        except ImportError:
            bundle.lightgbm_version = None
  - In load_model_bundle (near persistence.py:156-172), ADD a mismatch-warning block
      mirroring the sklearn_version one — log `lightgbm_version_mismatch` (saved vs current)
      only when both are non-None and differ. Guard the current-version lookup in a
      try/except ImportError so loading a non-LightGBM bundle without the extra never warns.
  - compute_hash is unchanged (it never read version fields) — confirm no bundle hash shifts.
  - VALIDATE: uv run mypy app/features/forecasting/ && uv run pyright app/features/forecasting/

Task 8 — MODIFY app/features/registry/service.py — _capture_runtime_info:
  - ADD, alongside the sklearn/numpy/pandas/joblib blocks (registry/service.py:84-123):
        try:
            import lightgbm
            runtime_info["lightgbm_version"] = lightgbm.__version__
        except ImportError:
            pass
  - VALIDATE: uv run mypy app/features/registry/ && uv run pyright app/features/registry/

# ════════ STEP 6 — Tests ════════

Task 9 — CREATE app/features/forecasting/tests/test_lightgbm_forecaster.py:
  - START the module with `import pytest` then `pytest.importorskip("lightgbm")` at module
      scope (skips the whole file when the optional extra is absent).
  - CLONE every test from test_regression_forecaster.py, swapping RegressionForecaster →
      LightGBMForecaster and RegressionModelConfig → LightGBMModelConfig: fit/predict
      roundtrip, fit-rejects-None-features, fit-rejects-mismatched-rows,
      predict-rejects-None-features, predict-rejects-wrong-shape, predict-before-fit-raises,
      test_determinism_same_random_state (np.testing.assert_array_equal), handles-NaN-features,
      get/set params, and model_factory creation.
  - COPY the `_synthetic_data` helper verbatim.
  - For the factory test: `model_factory` needs forecast_enable_lightgbm=True — patch it via
      `unittest.mock.patch("app.features.forecasting.models.get_settings")` returning a
      settings stub with forecast_enable_lightgbm=True (note: model_factory imports
      get_settings INSIDE the function — patch that path), OR construct LightGBMForecaster
      directly for the non-factory tests.
  - VALIDATE: uv run pytest -v -m "not integration" app/features/forecasting/tests/test_lightgbm_forecaster.py

Task 10 — MODIFY app/features/forecasting/tests/test_service.py:
  - In TestFeatureAwareContract.test_requires_features_flag (~line 351), ADD a class-level
      assertion that needs neither the factory flag nor lightgbm installed:
        from app.features.forecasting.models import LightGBMForecaster
        assert LightGBMForecaster.requires_features is True
  - ADD test_lightgbm_factory_respects_flag: with forecast_enable_lightgbm=False (patched)
      model_factory(LightGBMModelConfig()) raises ValueError matching "not enabled"; with
      True it returns a LightGBMForecaster. Guard the True-branch with
      `pytest.importorskip("lightgbm")` only if it constructs+fits — construction alone needs
      no import (lazy), so the isinstance check needs no importorskip.
  - test_canonical_columns_match_regression_contract is UNCHANGED (LightGBM reuses it).
  - VALIDATE: uv run pytest -v -m "not integration" app/features/forecasting/tests/test_service.py

Task 11 — MODIFY app/features/forecasting/tests/test_routes.py:
  - ADD test_train_lightgbm_rejected_when_disabled: POST /forecasting/train with
      `config={"model_type":"lightgbm"}` and forecast_enable_lightgbm at its default (False)
      → 400, problem+json detail mentioning LightGBM disabled (route gate routes.py:67-72).
  - Follow the file's existing ASGITransport client fixture + @pytest.mark.integration idiom.
  - VALIDATE: uv run pytest -v app/features/forecasting/tests/test_routes.py

Task 12 — MODIFY app/features/jobs/tests/test_service.py:
  - FIX the rejects-unsupported-model-type test (~line 218): change the params payload
      `model_type` from `"lightgbm"` to a genuinely unsupported value `"arima"`; keep the
      `ValueError`/`Unsupported model_type` expectation.
  - ADD test_execute_train_accepts_lightgbm: build a JobCreate train job with
      model_type="lightgbm"; with forecast_enable_lightgbm enabled + `pytest.importorskip
      ("lightgbm")` assert it runs (or, mirroring the existing regression job test, assert
      _execute_train builds a LightGBMModelConfig — match the file's existing depth of mock).
  - VALIDATE: uv run pytest -v app/features/jobs/tests/test_service.py

Task 13 — MODIFY app/features/scenarios/tests/test_routes_integration.py:
  - ADD an integration test that trains a `lightgbm` model then POSTs /scenarios/simulate
      with its run_id and asserts the response `method == "model_exogenous"` (NOT "heuristic")
      — pins the Task 5 dispatch change. Mirror the existing regression model_exogenous test
      in this file; gate with `pytest.importorskip("lightgbm")` and enable
      forecast_enable_lightgbm.
  - VALIDATE: uv run pytest -v -m integration app/features/scenarios/tests/test_routes_integration.py

Task 14 — MODIFY app/features/forecasting/tests/test_persistence.py:
  - ADD test_lightgbm_version_recorded: after `pytest.importorskip("lightgbm")`, save a
      ModelBundle and assert `bundle.lightgbm_version` is a non-empty str; and assert a
      non-LightGBM bundle still saves/loads with lightgbm_version possibly set (str) — the
      field is populated best-effort regardless of model type.
  - VALIDATE: uv run pytest -v -m "not integration" app/features/forecasting/tests/test_persistence.py

Task 15 — MODIFY app/features/registry/tests/test_service.py:
  - ADD/extend a runtime_info test: when `lightgbm` is importable
      (`pytest.importorskip("lightgbm")`) a created run's runtime_info contains the
      `lightgbm_version` key. Mirror the existing sklearn/numpy runtime_info assertions.
  - VALIDATE: uv run pytest -v app/features/registry/tests/test_service.py

# ════════ STEP 7 — Docs & example ════════

Task 16 — CREATE examples/models/advanced_lightgbm.py:
  - A minimal, runnable script: build a small synthetic [n, 14] feature matrix + target,
      `LightGBMForecaster(random_state=42).fit(y, X)`, `predict(horizon, X_future)`, print
      the forecasts. Mirror the structure/header of examples/models/baseline_naive.py.
  - `examples/**` ignores T201/ANN/S101 (pyproject ruff per-file-ignores) — `print` is fine.
  - VALIDATE: uv run python examples/models/advanced_lightgbm.py  (requires the ml-lightgbm extra)

Task 17 — MODIFY examples/models/model_interface.md + feature_frame_contract.md:
  - model_interface.md: ADDITIVE — add a `lightgbm` row to the Model Configurations / Model
      Formulas sections; note requires_features=True; note it is optional (ml-lightgbm extra).
  - feature_frame_contract.md: ADDITIVE — update the opening line ("the regression forecaster
      today; LightGBM ... in the MLZOO sequence") to record LightGBM as an IMPLEMENTED
      feature-aware model. Do NOT rewrite the file. The backtesting loud-fail limitation
      paragraph stays accurate (B.2 still pending).
  - VALIDATE: uv run ruff check . && uv run ruff format --check .

Task 18 — MODIFY README.md:
  - ADDITIVE: one line in the install/setup section that `LightGBM` is an opt-in model
      installed via `uv sync --extra dev --extra ml-lightgbm` and enabled with
      `forecast_enable_lightgbm=true`. Mirror the README's existing tone; do not restructure.
  - VALIDATE: uv run ruff format --check .   (README is markdown — visual check only)
```

### Per-task pseudocode (critical details only)

```python
# ── Task 2 — LightGBMForecaster.fit/predict (the lazy import + determinism is the crux) ──
def fit(self, y, X=None):
    if X is None:
        raise ValueError("LightGBMForecaster requires exogenous features X for fit()")
    if len(y) == 0:
        raise ValueError("Cannot fit on empty array")
    if X.shape[0] != len(y):
        raise ValueError(
            f"X has {X.shape[0]} rows but y has {len(y)} — feature/target rows must match"
        )
    import lightgbm as lgb            # LAZY — optional dependency; never module-scope
    estimator: Any = lgb.LGBMRegressor(
        n_estimators=self.n_estimators,
        learning_rate=self.learning_rate,
        max_depth=self.max_depth,
        random_state=self.random_state,
        n_jobs=1,                     # \
        deterministic=True,           #  } all three required for bit-reproducible fit
        force_col_wise=True,          # /
        verbosity=-1,                 # silence LightGBM training chatter
    )
    estimator.fit(X, y)               # NaN in X is fine — LightGBM handles missing natively
    self._estimator = estimator
    self._last_values = np.asarray(y[-1:], dtype=np.float64)
    self._is_fitted = True
    return self

def predict(self, horizon, X=None):
    if not self._is_fitted or self._estimator is None:
        raise RuntimeError("Model must be fitted before predict")
    if X is None:
        raise ValueError("LightGBMForecaster requires exogenous features X for predict()")
    if X.shape[0] != horizon:
        raise ValueError(f"X has {X.shape[0]} rows but horizon is {horizon} — they must match")
    predictions = self._estimator.predict(X)
    return np.asarray(predictions, dtype=np.float64)

# ── Task 5 — scenarios dispatch: branch on capability, not a string ──
# app/features/scenarios/service.py ~line 112
#   BEFORE:  if bundle.config.model_type == "regression":
#   AFTER:   if bundle.model.requires_features:
#       return await self._simulate_model_exogenous(db, request, bundle, store_id, product_id)
#   This mirrors forecasting/service.py, which already branches on
#   `model.requires_features` / `bundle.model.requires_features`. A LightGBM bundle now
#   takes the genuine re-forecast path; a baseline bundle still takes the heuristic path.

# ── Task 3 — model_factory: gate first, then construct ──
elif model_type == "lightgbm":
    if not settings.forecast_enable_lightgbm:
        raise ValueError("LightGBM is not enabled. Set forecast_enable_lightgbm=True in settings.")
    from app.features.forecasting.schemas import LightGBMModelConfig
    if isinstance(config, LightGBMModelConfig):
        return LightGBMForecaster(
            n_estimators=config.n_estimators,
            learning_rate=config.learning_rate,
            max_depth=config.max_depth,
            random_state=random_state,        # threaded from settings.forecast_random_seed
        )
    raise ValueError("Invalid config type for lightgbm")
```

### Integration Points

```yaml
DEPENDENCY:
  - pyproject.toml: + [project.optional-dependencies] ml-lightgbm = ["lightgbm>=4.5.0"].
  - uv.lock: regenerated by `uv lock` (CI installs with --frozen).
  - CI: NO workflow change — ci.yml already runs `uv sync --frozen --all-extras --dev`
    (lines 48, 74, 116, 163), so --all-extras installs ml-lightgbm and CI tests the path.

CONFIG:
  - No new setting. forecast_enable_lightgbm (config.py:101, default False) is the runtime
    gate — UNCHANGED. forecast_random_seed (config.py:97, default 42) is the determinism
    source threaded through model_factory — UNCHANGED.

TRAIN PATH:
  - ForecastingService.train_model — UNCHANGED. It already branches on
    `model.requires_features`; a LightGBM model (requires_features=True) routes through
    `_build_regression_features` automatically and persists feature_columns/history_tail.

PREDICT PATH:
  - POST /forecasting/predict — UNCHANGED. Rejects all requires_features models, LightGBM
    included. LightGBM forecasts through POST /scenarios/simulate (model_exogenous).

PERSISTENCE:
  - ModelBundle: + lightgbm_version field (best-effort on save, mismatch-warn on load).
    compute_hash unchanged → no bundle hash shifts. Old bundles load fine (dataclass default).

REGISTRY:
  - runtime_info JSONB: + "lightgbm_version" key when lightgbm is importable. JSONB → NO
    Alembic migration.

NO MIGRATION: this PRP touches no SQLAlchemy model and no Alembic version.
NO API CONTRACT CHANGE: no route, request/response schema, or WebSocket frame changes.
```

---

## Validation Loop

### Level 0: Environment

```bash
uv lock                                    # refresh the lockfile after the pyproject edit
uv sync --extra dev --extra ml-lightgbm     # install the optional extra locally
uv run python -c "import lightgbm; print('lightgbm', lightgbm.__version__)"
# Expected: prints a 4.x version. Without this, mypy/pyright on the lazy import + the
# LightGBM tests cannot run locally (CI installs --all-extras automatically).
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
# Watch for: the [[tool.mypy.overrides]] lightgbm.* block must exist; do NOT add an inline
# `# type: ignore[import-untyped]` on `import lightgbm` (warn_unused_ignores would flag it).
```

### Level 3: Unit Tests

```bash
# New + extended tests
uv run pytest -v -m "not integration" app/features/forecasting/tests/test_lightgbm_forecaster.py
uv run pytest -v -m "not integration" app/features/forecasting/tests/test_service.py
uv run pytest -v -m "not integration" app/features/jobs/tests/test_service.py

# Regression — these slices must stay green with NO behaviour change
uv run pytest -v -m "not integration" app/features/forecasting/tests/
uv run pytest -v -m "not integration" app/features/backtesting/tests/    # loud-fail guard MUST still pass
uv run pytest -v -m "not integration" app/features/scenarios/tests/

# Whole fast suite
uv run pytest -v -m "not integration"
# Expected: all green. The baseline-forecaster tests and test_regression_forecaster.py must
# pass with ZERO edits. If lightgbm is somehow absent, test_lightgbm_forecaster.py SKIPS
# (importorskip) — it must never ERROR.
```

### Level 4: Integration Tests

```bash
docker compose up -d && uv run alembic upgrade head
uv run pytest -v -m integration app/features/forecasting/ app/features/scenarios/ \
  app/features/jobs/ app/features/registry/
# CRITICAL: the scenarios lightgbm model_exogenous test (Task 13) must report
# method="model_exogenous". No migration in this PRP → no `alembic downgrade` round-trip.
```

### Level 5: Manual Validation (dogfood — REQUIRED)

```bash
# 1. The forecaster wires up and is deterministic
uv run python -c "
import numpy as np
from app.features.forecasting.models import LightGBMForecaster
rng = np.random.default_rng(0)
X = rng.normal(size=(80, 14)); y = (3.0 * X[:, 0] + rng.normal(size=80)).astype(np.float64)
a = LightGBMForecaster(random_state=7).fit(y, X).predict(12, X[:12])
b = LightGBMForecaster(random_state=7).fit(y, X).predict(12, X[:12])
np.testing.assert_array_equal(a, b); print('lightgbm deterministic OK', a[:3])"

# 2. requires_features is correct
uv run python -c "
from app.features.forecasting.models import LightGBMForecaster
assert LightGBMForecaster.requires_features is True; print('requires_features OK')"

# 3. End-to-end: train a lightgbm model and re-forecast it in a scenario.
#    Set FORECAST_ENABLE_LIGHTGBM=true in .env, restart uvicorn, then:
#    curl -sX POST localhost:8123/forecasting/train -H 'Content-Type: application/json' \
#      -d '{"store_id":1,"product_id":1,"train_start_date":"2024-01-01",
#           "train_end_date":"2024-06-01","config":{"model_type":"lightgbm"}}'
#    -> 200; take the run_id from the model_path, then POST /scenarios/simulate with it
#    -> the ScenarioComparison "method" field is "model_exogenous".

# 4. The optional dep stays optional — a baseline still works without it
#    (in a venv WITHOUT ml-lightgbm): training a naive model must still succeed, and
#    `import app.features.forecasting.models` must not raise ImportError.
```

---

## Final Validation Checklist

- [ ] `uv run ruff check .` and `uv run ruff format --check .` clean.
- [ ] `uv run mypy app/` and `uv run pyright app/` clean (both --strict).
- [ ] `uv run pytest -v -m "not integration"` fully green; `test_lightgbm_forecaster.py` runs
      (lightgbm installed) and passes — never ERRORs.
- [ ] `uv run pytest -v -m integration app/features/{forecasting,scenarios,jobs,registry}/` green,
      including the scenarios `lightgbm` `model_exogenous` test.
- [ ] `model_factory(LightGBMModelConfig())` returns a `LightGBMForecaster` with the flag on,
      raises a clear `ValueError` with the flag off.
- [ ] `test_feature_aware_model_fails_loud_in_backtest` and every baseline / `regression`
      test pass with **no edit**.
- [ ] `git grep -n 'NotImplementedError' app/features/forecasting/models.py` no longer matches
      the LightGBM line.
- [ ] `uv.lock` is regenerated and committed; the core `[project] dependencies` list is
      UNCHANGED (LightGBM is only in `[project.optional-dependencies]`).
- [ ] No Alembic migration; no route/schema/WebSocket contract change.
- [ ] `git diff --stat` shows only intended files — no whole-file CRLF/LF noise diffs.
- [ ] An OPEN GitHub issue exists for this work (`gh issue view <N> --json state` → `OPEN`);
      commit `feat(forecast): add LightGBM feature-aware forecasting model (#<issue>)`;
      branch `feat/forecasting-lightgbm-first-model` off `dev`.

---

## Anti-Patterns to Avoid

- ❌ Don't implement XGBoost, Prophet, or any second model — that is PRP-MLZOO-C
  (`INITIAL-MLZOO-index.md`). This PRP is LightGBM only.
- ❌ Don't add hyperparameter search, portfolio/global models, or an explainability change —
  all explicitly out of scope in `INITIAL-MLZOO-B`.
- ❌ Don't wire feature-aware backtesting — DECISIONS LOCKED #6 defers it to PRP-MLZOO-B.2.
  Keep `test_feature_aware_model_fails_loud_in_backtest`; do not touch `_run_model_backtest`
  or `_execute_backtest`.
- ❌ Don't add `lightgbm` to the core `[project] dependencies` — it is an OPTIONAL extra
  (DECISIONS LOCKED #1). Don't `import lightgbm` at module scope (DECISIONS LOCKED #7).
- ❌ Don't add fields to `LightGBMModelConfig` — DECISIONS LOCKED #3 keeps it conservative.
- ❌ Don't edit `ForecastingService.train_model` / `predict` — they already branch on
  `requires_features`; a LightGBM model trains and is predict-rejected with zero service edits.
- ❌ Don't write a new leakage test for LightGBM — it reuses the already-pinned shared and
  historical builders (DECISIONS LOCKED #5). Re-testing the same code is noise.
- ❌ Don't "fix" a determinism-test flake with `assert_allclose` — pin `n_jobs=1` +
  `deterministic=True` + `force_col_wise=True` on `LGBMRegressor` and keep `assert_array_equal`.
- ❌ Don't forget `uv lock` — CI's `uv sync --frozen` fails on a stale lockfile.
- ❌ Don't make `test_lightgbm_forecaster.py` hard-require the extra — `pytest.importorskip`
  so it SKIPS (never ERRORs) when `ml-lightgbm` is not installed.

## Open Questions — ALL RESOLVED

`INITIAL-MLZOO-B`'s "Required decisions" were resolved during PRP planning:
- **Dependency strategy** → optional dependency group `ml-lightgbm` (DECISIONS LOCKED #1;
  user-confirmed). The sklearn fallback is rejected as a no-op (#2).
- **Advanced model config fields** → `LightGBMModelConfig` used unchanged, conservative (#3).
- **Dependency versions in registry/runtime metadata** → `ModelBundle.lightgbm_version` +
  `runtime_info["lightgbm_version"]` (Tasks 7-8).
- **How prediction rejects missing future feature frames** → the existing capability-based
  (`requires_features`) rejection in `POST /forecasting/predict` (#4).
- **Backtesting scope** → deferred to PRP-MLZOO-B.2 (#6; user-confirmed "Defer to a
  follow-up PRP").

Nothing is left to litigate at implementation time.

## Confidence Score

**8 / 10** for one-pass implementation success.

Rationale: the feature-aware foundation (PRP-29) did the hard structural work — the train
path, the predict rejection, and the shared frame contract already branch on
`requires_features`, so adding a second feature-aware model is a *contained* change:
one new class (a near-clone of the proven `RegressionForecaster`), one `model_factory`
branch, one scenarios-dispatch line, one jobs branch, and metadata + tests. There is no
migration, no API change, no baseline-model change, and no new algorithm to invent.
The −2 risk is concentrated in two places: (a) **LightGBM determinism** — `assert_array_equal`
requires `n_jobs=1` + `deterministic=True` + `force_col_wise=True`, and a miss flakes only in
CI; the pseudocode pins all three explicitly. (b) **the optional-dependency mechanics** — the
`uv lock` refresh, the mypy `ignore_missing_imports` override, and `pytest.importorskip` must
all land together or the gates fail; each is called out as a discrete task with its own
validation step. Both risks are caught fast — by Level 0/2 (env + types) and Level 3 (the
determinism test). The "baselines + regression + backtest guard must pass unedited" gate makes
any accidental regression impossible to miss.
