name: "PRP-MLZOO-C2 — Prophet-like Additive Forecasting Model"
description: |

## Purpose

The second half of MLZOO-C (`PRPs/INITIAL/INITIAL-MLZOO-C-xgboost-prophet-extensions.md`).
It adds a **Prophet-like additive forecasting model** — `ProphetLikeForecaster` — a
*deterministic, regularized, additive linear* model that decomposes demand into **trend**,
**seasonality**, and **holiday/regressor** components.

This is **not** a clone of the LightGBM/XGBoost tree models. It is a distinct model-family
design task. The two tree models are gradient-boosted, non-additive, and opaque; the
Prophet-like model is a transparent additive linear model whose fitted coefficients *are*
the component decomposition. Concretely it is a scikit-learn `Pipeline` of a
`SimpleImputer` + a `Ridge` regressor over the canonical 14-column feature frame, plus a
`decompose()` method that splits any forecast into its additive trend / seasonality /
regressor contributions.

> **Sibling PRP:** `PRPs/PRP-MLZOO-C1-xgboost-model.md` ships the XGBoost model. C1 and C2
> are intentionally **separate branches and separate review units** — never combine them.
> They are additive and order-independent; whichever merges second rebases cleanly (see
> "Sibling-PRP integration" below).

> **Naming honesty.** The model is "Prophet-**like**", never "Prophet". It deliberately
> approximates Prophet's *additive decomposition* shape using a linear model over
> already-engineered features. It does **not** add the real `prophet`/Stan dependency and
> does **not** replicate Prophet's changepoint trend, posterior uncertainty intervals, or
> automatic seasonality discovery. `docs/optional-features/05-advanced-ml-model-zoo.md`
> explicitly endorses "Prophet-like" as the intentional term for exactly this. Every
> docstring and doc section MUST set this expectation plainly (see Risks).

## What this PRP already inherits (DO NOT re-build)

PRP-29 (MLZOO-A), PRP-30 (MLZOO-B), PRP-27 (the `regression` model), and PRP-MLZOO-B.2
(feature-aware backtesting) already shipped the structural foundation. Re-use it:

- **The feature-aware model contract.** `BaseForecaster.requires_features: ClassVar[bool]`
  (`app/features/forecasting/models.py:64`). `RegressionForecaster` (`models.py:438`) is the
  **closest structural template** — like the Prophet-like model it wraps a pure-scikit-learn
  estimator, needs **no optional dependency**, and needs **no feature flag**. (The LightGBM/
  XGBoost forecasters are *less* relevant here — they carry optional-dependency machinery
  this model does not need.)
- **The shared feature-frame contract.** `app/shared/feature_frames/` owns
  `canonical_feature_columns()` — the fixed, ordered 14-column set:
  `["lag_1","lag_7","lag_14","lag_28","dow_sin","dow_cos","month_sin","month_cos",
  "is_weekend","is_month_end","price_factor","promo_active","is_holiday",
  "days_since_launch"]`. The Prophet-like model consumes this frame **unchanged** and
  writes **zero** new contract code (DECISIONS LOCKED #3).
- **Train / predict / scenarios / backtesting** — all branch on
  `model.requires_features`, capability-based, never on a `model_type` string
  (`forecasting/service.py:219,383`, `scenarios/service.py:114`,
  `backtesting/service.py:384-409`). A new feature-aware model trains, is predict-rejected,
  re-forecasts in scenarios (`method="model_exogenous"`), and backtests with **zero
  changes to those four service layers**.
- **The leakage spec.** `app/features/forecasting/tests/test_regression_features_leakage.py`
  and `app/shared/feature_frames/tests/test_leakage.py` pin the historical and future
  builders. Because the Prophet-like model consumes the **same** builders, its training and
  future feature matrices are leakage-covered by construction (DECISIONS LOCKED #6).

The **problem this PRP fixes**: `docs/optional-features/05-advanced-ml-model-zoo.md` calls
for "Prophet-like models with trend, seasonality, holiday, and regressor components" as the
third model family — to make ForecastLabAI a credible model-*comparison* platform with more
than tree models. No additive/decomposable model exists today (`regression` is a tree;
`naive`/`seasonal_naive`/`moving_average` are target-only).

## DEPENDS ON — read before starting

- `PRPs/INITIAL/INITIAL-MLZOO-C-xgboost-prophet-extensions.md` — the shared C brief.
- `PRPs/INITIAL/INITIAL-MLZOO-index.md` — the MLZOO roadmap.
- `docs/optional-features/05-advanced-ml-model-zoo.md` — § "Prophet-like Models" is the
  vision: trend, weekly/yearly seasonality, holiday/event regressors, optional changepoints,
  optional external regressors; and the explicit option "Implement a lightweight additive
  model using sklearn regression over generated trend/seasonal features."
- `PRPs/PRP-27-scenario-simulation-full-version.md` & `PRPs/ai_docs/exogenous-regressor-forecasting.md`
  — how the `regression` model (the structural template) consumes a future feature frame.
- `examples/models/feature_frame_contract.md` — the historical/future frame shapes.

---

## Goal

Implement `ProphetLikeForecaster` — a deterministic, feature-aware, **additive** forecasting
model — and wire it end-to-end. It is a scikit-learn `Pipeline([SimpleImputer, Ridge])` over
the canonical 14-column feature frame. It exposes the standard `BaseForecaster` interface
(`fit`/`predict`/`get_params`/`set_params`, `requires_features = True`) **plus** a model-
specific `decompose()` method that returns the additive trend / seasonality / holiday-
regressor contribution breakdown of a forecast. Because it is pure scikit-learn (already a
core dependency), it ships **always-enabled** — no optional dependency group, no feature
flag, no lazy import — exactly like the `regression` model.

**End state:** a user can train a `prophet_like` model (HTTP or job), re-forecast it in a
what-if scenario (`method="model_exogenous"`), and backtest it, with no extra install and no
flag — exactly as they can a `regression` model today. Every existing model behaves
**identically** before and after.

## Why

- **The model zoo needs a non-tree, transparent model.** The comparison platform currently
  has three target-only baselines and two opaque gradient-boosted trees (`regression`,
  `lightgbm` — and `xgboost` from sibling C1). An *additive linear* model is a genuinely
  different model family: interpretable, fast, and the natural seam for explainability
  (MLZOO-D). It answers "how much of this forecast is trend vs seasonality vs the promo?".
- **Dependency-free.** Unlike the tree models, this needs no native dependency, no extra,
  no flag — it ships on the already-pinned `scikit-learn`. Zero install-friction; perfectly
  aligned with the single-host vision.
- **The foundation is fully paid for.** Train, predict, scenarios, and backtesting all
  branch on `requires_features`. A new feature-aware model is a contained change.
- **Low blast radius.** No migration, no API-contract change, no existing-model change, no
  new dependency, no new vertical slice.

## What

A backend-only feature PRP. User-visible behaviour gains exactly one thing: `model_type:
"prophet_like"` becomes a real, trainable, scenario-re-forecastable, backtestable model.
Everything else is identical.

### The model design (READ THIS — it is the core of the PRP)

**Decomposition mapping.** The canonical 14 columns are partitioned into three
Prophet-style components. Define this as a module-level constant in `models.py`:

| Component | Canonical columns | Prophet analogue |
|-----------|-------------------|------------------|
| `trend` | `lag_1`, `lag_7`, `lag_14`, `lag_28`, `days_since_launch` | growth `g(t)` — autoregressive level + lifecycle ramp |
| `seasonality` | `dow_sin`, `dow_cos`, `month_sin`, `month_cos`, `is_weekend`, `is_month_end` | seasonal `s(t)` — weekly/monthly cycle (these are exactly `CALENDAR_COLUMNS`) |
| `holiday_regressor` | `price_factor`, `promo_active`, `is_holiday` | holiday + extra-regressor `h(t)` — known-in-advance exogenous effects |

**The additive math.** A `Ridge` fit gives `y_hat = intercept + Σ_i coef_i · x_i`. Group the
sum by component: `y_hat = intercept + trend_contrib + seasonality_contrib +
regressor_contrib`, where `<component>_contrib = Σ_{i ∈ component} coef_i · x_i`. This is the
literal additive decomposition — each component contribution is just the partial sum of that
component's columns. `decompose(X)` returns the four-way breakdown; the **additive
invariant** is `intercept + trend + seasonality + holiday_regressor == predict(...)`
(within float tolerance) and is a model-specific validation test.

**NaN tolerance.** Linear models reject `NaN` (`Ridge.fit` raises `ValueError: Input
contains NaN`). The future feature frame intentionally emits `NaN` for un-resolvable lag
cells. Mitigation: a `SimpleImputer(strategy="median")` as the first `Pipeline` step. The
imputer learns its per-column medians on **training `X` only** (`Pipeline.fit` enforces
this) and re-applies them at predict time — no leakage. `decompose()` therefore computes
`coef_ · x` on the **imputed** `X`, not the raw `X`.

**Determinism.** `Ridge(solver="cholesky")` has a closed-form, deterministic solution (no
`random_state` needed). `SimpleImputer` (median) is deterministic. The whole `Pipeline` is
deterministic — two fits on the same data produce identical coefficients and forecasts.

**Why `Ridge`, not `LinearRegression`.** The 14 engineered columns are heavily collinear
(`lag_1` vs `lag_7`, the calendar columns). Plain OLS is unstable under collinearity;
`Ridge`'s L2 penalty makes coefficients robust while staying closed-form and deterministic.
`ElasticNet` is rejected — its L1 term zeros coefficients (feature selection), which would
silently drop a curated calendar column and corrupt the seasonal component; it is also
iterative. (See `https://scikit-learn.org/stable/modules/linear_model.html#ridge-regression-and-classification`.)

### Technical requirements

1. **No new dependency.** `scikit-learn` is already a core dependency (`pyproject.toml:21`)
   and ships `Ridge`, `SimpleImputer`, `Pipeline`. **No** `pyproject.toml` change, **no**
   `uv.lock` change, **no** new optional extra (DECISIONS LOCKED #2).
2. **No feature flag.** The model is always available, exactly like `regression`. **No**
   `app/core/config.py` change, **no** `forecast_enable_*` setting, **no** route gate
   (DECISIONS LOCKED #2).
3. **`ProphetLikeModelConfig`** in `app/features/forecasting/schemas.py` — a
   `ModelConfigBase` subclass: `model_type: Literal["prophet_like"]`, `alpha: float`
   (Ridge regularization strength, `ge=0.0`, `le=10000.0`, default `1.0`),
   `feature_config_hash: str | None`. Conservative — no `seasonality_mode`, no Fourier
   order (DECISIONS LOCKED #4). Added to the `ModelConfig` union.
4. **`ProphetLikeForecaster`** in `app/features/forecasting/models.py` — a `BaseForecaster`
   subclass, `requires_features: ClassVar[bool] = True`, structurally closest to
   `RegressionForecaster`. It builds a `Pipeline([("impute", SimpleImputer(strategy=
   "median")), ("ridge", Ridge(alpha=self.alpha, solver="cholesky"))])` inside `fit()`,
   stores it as `self._estimator`, and stores the fitted column-component grouping. It
   exposes `decompose()` in addition to the base interface.
5. **`model_factory`** — a new `prophet_like` branch (no flag gate, mirroring the
   `regression` branch at `models.py:793-803`). The `ModelType` literal (`models.py:736`)
   gains `"prophet_like"`.
6. **Jobs integration.** `JobService._execute_train` (`jobs/service.py:454-478`) and
   `_execute_backtest` (`jobs/service.py:641-658`) each gain a `prophet_like` branch
   building `ProphetLikeModelConfig` — mirroring the `regression` branches.
7. **Persistence/metadata.** **No `ModelBundle` change.** The fitted `Pipeline` is pickled
   by joblib exactly like `HistGradientBoostingRegressor`; `sklearn_version` (already
   captured, `persistence.py:55,100`) and `runtime_info["sklearn_version"]` (already
   captured, `registry/service.py:96-100`) fully cover it. No new version field — there is
   no new library to version. (DECISIONS LOCKED #5.)
8. **Tests** — a new `test_prophet_like_forecaster.py` (no `importorskip` — pure sklearn,
   always runs) with the standard contract tests **plus** model-specific tests (additive
   invariant, imputer NaN tolerance, decomposition determinism); an
   `examples/models/prophet_like_additive.py` example; additive docs.

### Success Criteria

- [ ] `model_factory(ProphetLikeModelConfig(), random_state=42)` returns a
      `ProphetLikeForecaster` — **no flag, never raises a "not enabled" error**.
- [ ] `ProphetLikeForecaster.requires_features is True`; `fit`/`predict` require a
      non-`None` `X` and raise the same error-message substrings as `RegressionForecaster`
      (`"requires exogenous features"`, `"rows must match"`, `"horizon"`, `"fitted"`).
- [ ] A `predict` over a future frame containing `NaN` lag cells succeeds (the
      `SimpleImputer` fills them) — a plain `Ridge` would raise `ValueError: Input contains
      NaN`.
- [ ] Two fits on the same data produce **identical** forecasts
      (`np.testing.assert_array_equal`).
- [ ] **Additive invariant:** for any fitted model and any `X`,
      `decompose(X)` returns `{intercept, trend, seasonality, holiday_regressor}` summing
      (within `1e-9` relative tolerance) to `predict(len(X), X)`.
- [ ] `decompose()` uses the **imputed** `X` and the **trained** imputer statistics — a
      future-frame `NaN` is imputed with the *training* median, not a predict-time median.
- [ ] `ForecastingService.train_model` trains a `prophet_like` model with **no edit to
      `train_model`**; `POST /scenarios/simulate` returns `method="model_exogenous"`; a
      backtest produces per-fold metrics — all with **no edit to the four service layers**.
- [ ] `JobService._execute_train` and `_execute_backtest` accept `model_type="prophet_like"`.
- [ ] Every existing model and every existing test pass **with no behaviour change**.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"` all green.
- [ ] No Alembic migration; no new dependency; no `pyproject.toml`/`uv.lock`/`config.py`
      change; no route-path/response-schema/WebSocket change.

---

## All Needed Context

### Documentation & References

```yaml
- file: app/features/forecasting/models.py
  why: RegressionForecaster (lines 438-577) is the STRUCTURAL TEMPLATE — pure-sklearn
       wrapper, no optional dep, no flag, estimator constructed inside fit() and typed
       `Any`. Copy its __init__/fit/predict guard shape and error strings. The
       model_factory `regression` branch (lines 793-803) is the template for the
       prophet_like branch (NO flag gate). The ModelType literal is at line 736. The
       module already imports sklearn with `# type: ignore[import-untyped]` (lines 20-22)
       — add the Ridge/SimpleImputer/Pipeline imports the same way.

- file: app/features/forecasting/schemas.py
  why: RegressionModelConfig (lines 147-189) is the template for ProphetLikeModelConfig —
       same ModelConfigBase base, same Field(ge=, le=, default=) idiom, same
       feature_config_hash field. The ModelConfig union is at lines 192-199.

- file: app/features/forecasting/service.py
  why: train_model (lines 180-297) branches `if model.requires_features:` (line 219) —
       MODEL-AGNOSTIC, builds the historical frame via _build_regression_features and
       calls model.fit(features.y, features.X). predict (lines 383-393) rejects
       feature-aware models. DO NOT EDIT service.py — a prophet_like model trains and is
       predict-rejected purely because requires_features=True.

- file: app/features/scenarios/service.py
  why: model_exogenous dispatch branches on `bundle.model.requires_features` (line 114) —
       no model_type strings remain in app/features/scenarios/. A prophet_like bundle
       takes the genuine re-forecast path with ZERO scenarios changes.

- file: app/features/backtesting/service.py
  why: lines 384-409 probe `model_factory(...).requires_features` and build per-fold
       leakage-safe X. MODEL-AGNOSTIC. A prophet_like model backtests with ZERO
       backtesting-service changes.

- file: app/features/jobs/service.py
  why: _execute_train model_type chain at lines 454-478 (the `regression` branch is the
       template; final `else: raise ValueError("Unsupported model_type: ...")`).
       _execute_backtest has an IDENTICAL chain at lines 641-658. Forecasting-schemas
       import block at lines 426-433. ADD a prophet_like branch to BOTH chains.

- file: app/features/forecasting/persistence.py
  why: CONFIRM no change is needed. ModelBundle (lines 48-57) captures sklearn_version
       (line 55, 100). The prophet_like Pipeline pickles like HistGradientBoostingRegressor
       — sklearn_version covers it. No new field.

- file: app/features/forecasting/tests/test_regression_forecaster.py
  why: The 10-test contract template — clone the contract tests (fit/predict roundtrip,
       rejects-None-X, rejects-mismatched-rows, predict-before-fit, get/set params,
       determinism, factory creation). Copy the `_synthetic_data` helper verbatim. The
       prophet_like test file ADDS model-specific tests on top (see Tasks).

- file: app/features/forecasting/tests/test_service.py
  why: TestFeatureAwareContract (lines 349-412) — extend test_requires_features_flag with
       a prophet_like assertion.

- file: app/features/jobs/tests/test_service.py
  why: test_execute_train_builds_regression_config (lines 204-220) and
       test_execute_backtest_builds_regression_config (lines 263-284) are the templates
       for the prophet_like job tests. test_execute_train_rejects_unsupported_model_type
       (lines 243-249) uses "arima" — DO NOT touch it.

- url: https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html
  why: Ridge(alpha=1.0, solver="cholesky") — closed-form, deterministic. solver `"sag"`/
       `"saga"` are STOCHASTIC and need random_state — never use them. `"cholesky"`/`"svd"`/
       `"lsqr"` are deterministic; pin `"cholesky"` explicitly.
  critical: Ridge.fit raises `ValueError: Input contains NaN` on any NaN in X — hence the
       SimpleImputer.

- url: https://scikit-learn.org/stable/modules/generated/sklearn.impute.SimpleImputer.html
  why: SimpleImputer(strategy="median", missing_values=np.nan) — deterministic per-column
       medians, robust to right-skewed sales lag/rolling columns. Learns statistics on
       fit() only.

- url: https://scikit-learn.org/stable/modules/compose.html#pipeline
  why: Pipeline([("impute", SimpleImputer(...)), ("ridge", Ridge(...))]) — fit() learns
       imputer medians on the TRAINING X, predict()/transform() reuses them. Folding the
       imputer inside the Pipeline is what keeps the no-leakage invariant intact.

- url: https://scikit-learn.org/stable/modules/linear_model.html#ridge-regression-and-classification
  section: Ridge regression and classification
  critical: Ridge's L2 penalty makes coefficients robust to the collinear 14-column frame;
       OLS (LinearRegression) is "highly sensitive" under collinearity. ElasticNet's L1
       term zeros coefficients (unwanted feature selection) — rejected.

- docfile: docs/optional-features/05-advanced-ml-model-zoo.md
  why: § "Prophet-like Models" — the design vision (trend/seasonality/holiday/regressor,
       optional changepoints, optional regressors) and the explicit endorsement of the
       "lightweight additive model using sklearn regression" option this PRP implements.
```

### Current Codebase tree (relevant — all already exist)

```bash
app/features/forecasting/
├── models.py            # RegressionForecaster (the template), model_factory, ModelType
├── schemas.py           # RegressionModelConfig (the template), ModelConfig union
├── service.py           # train_model + predict branch on requires_features (untouched)
├── persistence.py       # ModelBundle — sklearn_version already covers prophet_like (untouched)
├── routes.py            # /forecasting/train — NO gate needed (no flag) (untouched)
└── tests/
    ├── test_regression_forecaster.py        # the contract-test template to clone
    ├── test_service.py                      # TestFeatureAwareContract
    └── test_regression_features_leakage.py  # load-bearing — already covers prophet_like's frame
app/features/scenarios/service.py            # model_exogenous on requires_features (untouched)
app/features/backtesting/service.py          # feature-aware fold loop on requires_features (untouched)
app/features/jobs/service.py                 # _execute_train + _execute_backtest model_type chains
app/shared/feature_frames/                   # the shared 14-column contract — reused, untouched
pyproject.toml                               # scikit-learn already core — NO change
```

### Desired Codebase tree — files to ADD

```bash
app/features/forecasting/tests/
└── test_prophet_like_forecaster.py    # contract tests + model-specific (additive) tests
examples/models/
└── prophet_like_additive.py           # minimal train / predict / decompose example
```

### Files to MODIFY (all additive or behaviour-preserving)

```bash
app/features/forecasting/schemas.py             # + ProphetLikeModelConfig; + to ModelConfig union
app/features/forecasting/models.py              # + Ridge/SimpleImputer/Pipeline imports;
                                                #   + _PROPHET_LIKE_COMPONENTS constant;
                                                #   + ProphetLikeForecaster; + "prophet_like"
                                                #   in ModelType; + model_factory branch
app/features/jobs/service.py                    # _execute_train + _execute_backtest: + prophet_like
app/features/forecasting/tests/test_service.py  # extend TestFeatureAwareContract
app/features/jobs/tests/test_service.py         # + prophet_like train + backtest job tests
app/features/scenarios/tests/test_routes_integration.py  # + prophet_like model_exogenous test
app/features/backtesting/tests/test_feature_aware_backtest.py  # + prophet_like backtest test
examples/models/model_interface.md              # additive: prophet_like row
examples/models/feature_frame_contract.md       # additive: prophet_like is a feature-aware model
README.md                                       # additive: prophet_like model type
```

> Note the **absence**: no `pyproject.toml`, no `uv.lock`, no `app/core/config.py`, no
> `forecasting/routes.py`, no `persistence.py`, no `registry/service.py`. That absence is
> the design — a pure-sklearn model needs none of the optional-dependency machinery the
> tree models carry.

### DECISIONS LOCKED (resolved during planning — do NOT re-litigate)

1. **C1 (XGBoost) and C2 (Prophet-like) are separate PRPs, branches, and review units.**
   This PRP touches **only** the Prophet-like model. (User-confirmed.)

2. **Dependency strategy = no new dependency, no optional extra, no feature flag.** The
   model is built from `Ridge` + `SimpleImputer` + `Pipeline`, all in `scikit-learn`, which
   is already a core dependency. There is therefore nothing to gate — the model ships
   always-enabled exactly like `regression`. No `ml-prophet` extra (the real `prophet`/Stan
   package is explicitly **not** used). This directly answers `INITIAL-MLZOO-C`'s
   "dependency strategy" requirement. (User-confirmed: "Lightweight sklearn additive
   model".)

3. **The model consumes the canonical 14-column frame UNCHANGED — no new columns.** It does
   **not** add Fourier seasonal columns. Rationale: (a) the frame already carries calendar
   columns (`dow_sin/cos`, `month_sin/cos`, `is_weekend`, `is_month_end`) that a linear
   model regresses on to capture weekly/monthly seasonality; (b) adding new columns would
   create a **new leakage surface** outside the pinned `test_leakage.py` specs — a
   disproportionate risk for a v1. Continuous yearly-Fourier terms are an explicit Open
   Question, not v1 scope.

4. **`ProphetLikeModelConfig` is conservative — `alpha` + `feature_config_hash` only.** No
   `seasonality_mode` (the model is strictly additive — multiplicative seasonality is an
   Open Question), no Fourier-order field (per #3), no changepoint field (changepoint trend
   is an Open Question). `alpha` is the one genuinely model-shaping knob (Ridge L2
   strength). Mirrors the conservative-config precedent (PRP-30 DECISIONS LOCKED #3).

5. **No `ModelBundle` / `runtime_info` change.** The fitted `Pipeline` pickles like any
   sklearn estimator; the existing `sklearn_version` capture (bundle + registry runtime
   info) fully covers it. There is no new library, so there is no new version to record.
   This answers `INITIAL-MLZOO-C`'s "persistence/metadata shape" requirement: the metadata
   shape is **unchanged** — and that is the correct, intentional answer.

6. **No new leakage test.** The model consumes `_build_regression_features` /
   `_assemble_regression_rows` and the shared `app/shared/feature_frames` builders
   byte-for-byte — already pinned by the load-bearing leakage specs. The model-specific
   tests this PRP adds (additive invariant, imputer NaN tolerance) test the *model*, not the
   frame. The SimpleImputer is leakage-safe **because** the `Pipeline` learns medians on
   train `X` only — a property covered by a model-specific test (Task 8), not a frame
   leakage test.

7. **`Ridge(solver="cholesky")` — deterministic, pinned explicitly.** `solver="auto"` would
   pick a deterministic solver for a dense matrix anyway, but pinning `"cholesky"` makes the
   determinism guarantee explicit and immune to a future sklearn default change. Never use
   `"sag"`/`"saga"` (stochastic). `SimpleImputer(strategy="median")` — median over `mean`
   for robustness to right-skewed retail lag/rolling columns.

8. **`model_type = "prophet_like"`, class `ProphetLikeForecaster`.** The `_like` suffix is
   the honesty marker — it states "approximates Prophet, is not Prophet".
   `docs/optional-features/05-advanced-ml-model-zoo.md` endorses "Prophet-like" as the
   intentional term. Docstrings and docs MUST reinforce that changepoint trend, uncertainty
   intervals, and automatic seasonality are out of scope (see Risks).

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: Ridge rejects NaN. `Ridge.fit(X, y)` and `.predict(X)` raise
#   `ValueError: Input contains NaN` on ANY NaN cell. The future feature frame
#   intentionally emits NaN for un-resolvable lag cells. The SimpleImputer as the FIRST
#   Pipeline step is mandatory, not optional — without it, every scenario re-forecast and
#   every backtest fold of a prophet_like model raises.

# CRITICAL: imputer leakage. The SimpleImputer MUST learn its medians on the TRAINING X
#   only. `Pipeline.fit(X_train, y)` does this automatically; `Pipeline.predict(X_future)`
#   reuses the trained medians. NEVER call SimpleImputer().fit_transform(X_future)
#   separately — that would leak future-window statistics. Keep the imputer INSIDE the
#   Pipeline; never impute X by hand.

# CRITICAL: decompose() operates on IMPUTED X. The Ridge coef_ multiply the imputed
#   feature values, not the raw NaN-containing values. decompose() must run
#   `self._estimator.named_steps["impute"].transform(X)` first, then compute
#   coef_ · imputed_X grouped by component. Computing coef_ · raw_X would (a) propagate
#   NaN and (b) break the additive invariant (sum != predict()).

# GOTCHA: interface argument order. BaseForecaster is fit(y, X) / predict(horizon, X);
#   the sklearn Pipeline is fit(X, y) / predict(X). ProphetLikeForecaster.fit adapts:
#   internally `self._estimator.fit(X, y)`. Mirror RegressionForecaster.fit (models.py:483)
#   exactly — it already does this adaptation.

# GOTCHA: mypy --strict + sklearn. models.py imports sklearn with
#   `# type: ignore[import-untyped]` (models.py:20-22). Add the Ridge/SimpleImputer/
#   Pipeline imports the SAME way. Type the estimator `Any` (mirror `estimator: Any =
#   HistGradientBoostingRegressor(...)` at models.py:510). decompose()'s return type is a
#   concrete typed dict/dataclass — define it explicitly so mypy --strict is satisfied.

# GOTCHA: no importorskip. test_prophet_like_forecaster.py needs NO `pytest.importorskip`
#   — scikit-learn is a core dependency, always installed. The test file always RUNS
#   (unlike the lightgbm/xgboost test files which skip without their optional extra).

# GOTCHA: Ridge with alpha=0 degenerates to OLS. ProphetLikeModelConfig.alpha has ge=0.0
#   so alpha=0 is permitted; that is fine (OLS is still deterministic with solver=
#   "cholesky") but loses the collinearity robustness. The default 1.0 is the sane value;
#   document that alpha=0 is OLS.

# GOTCHA: line endings — repo has mixed CRLF/LF, no .gitattributes. Run `git diff --stat`
#   before committing; re-normalise any whole-file noise diff to its original ending.

# SIBLING-PRP integration: PRP-MLZOO-C1 also edits the ModelType Literal (models.py:736)
#   and the ModelConfig union (schemas.py:192-199). Both edits are purely additive (one new
#   literal entry, one new union member). If C1 merged first you will see its "xgboost"
#   entry already present — just add "prophet_like" alongside. A trivial one-line rebase,
#   never a semantic conflict. C1 also edits config.py/pyproject.toml/persistence.py —
#   files this PRP does NOT touch, so no overlap there.
```

---

## Implementation Blueprint

### Data models and structure

```python
# app/features/forecasting/schemas.py — mirrors RegressionModelConfig (schemas.py:147-189)

class ProphetLikeModelConfig(ModelConfigBase):
    """Configuration for the Prophet-like additive forecaster (MLZOO-C2).

    A deterministic, regularized ADDITIVE linear model — a ``Ridge`` regressor
    over the canonical 14-column feature frame — that decomposes demand into
    trend / seasonality / holiday-regressor components. It approximates
    Prophet's additive shape WITHOUT the real ``prophet``/Stan dependency: it
    does not model changepoint trend, posterior uncertainty, or automatic
    seasonality discovery. Pure scikit-learn — no optional dependency, no
    feature flag, always available (like ``RegressionModelConfig``).

    Attributes:
        alpha: Ridge L2 regularization strength. 0.0 degenerates to ordinary
            least squares; the default 1.0 keeps coefficients robust to the
            collinear engineered-feature frame.
        feature_config_hash: Optional hash of the feature contract used.
    """

    model_type: Literal["prophet_like"] = "prophet_like"
    alpha: float = Field(
        default=1.0, ge=0.0, le=10000.0, description="Ridge L2 regularization strength"
    )
    feature_config_hash: str | None = Field(
        default=None, description="Hash of the feature contract used for training"
    )


# app/features/forecasting/models.py — additions

# Module scope, near the existing sklearn import (models.py:20-22):
from sklearn.impute import SimpleImputer       # type: ignore[import-untyped]
from sklearn.linear_model import Ridge         # type: ignore[import-untyped]
from sklearn.pipeline import Pipeline          # type: ignore[import-untyped]

# Module-scope constant — the decomposition column grouping (canonical 14-column order):
_PROPHET_LIKE_COMPONENTS: dict[str, tuple[str, ...]] = {
    "trend": ("lag_1", "lag_7", "lag_14", "lag_28", "days_since_launch"),
    "seasonality": ("dow_sin", "dow_cos", "month_sin", "month_cos", "is_weekend", "is_month_end"),
    "holiday_regressor": ("price_factor", "promo_active", "is_holiday"),
}

# A typed return type for decompose():
@dataclass
class ForecastDecomposition:
    """Additive component breakdown of a Prophet-like forecast.

    Invariant: ``intercept + trend + seasonality + holiday_regressor`` equals
    ``predict(...)`` for the same X (within float tolerance), element-wise.
    Each array has shape ``[n_rows]`` — one value per forecast row.
    """
    intercept: float
    trend: np.ndarray[Any, np.dtype[np.floating[Any]]]
    seasonality: np.ndarray[Any, np.dtype[np.floating[Any]]]
    holiday_regressor: np.ndarray[Any, np.dtype[np.floating[Any]]]


class ProphetLikeForecaster(BaseForecaster):
    """Feature-aware ADDITIVE forecaster — Ridge over the canonical frame.

    Prophet-LIKE, not Prophet: it approximates Prophet's additive trend +
    seasonality + holiday/regressor decomposition with a regularized linear
    model over the already-engineered 14-column feature frame. It REQUIRES a
    non-None exogenous X for fit and predict. A SimpleImputer (median) handles
    the NaN lag cells the future frame emits; a Ridge(solver="cholesky") gives
    a closed-form, deterministic fit. ``decompose()`` returns the per-component
    additive contributions.

    NOT modelled (see PRP Risks): changepoint trend, posterior uncertainty
    intervals, automatic seasonality discovery, multiplicative seasonality.
    """

    requires_features: ClassVar[bool] = True

    def __init__(self, *, alpha: float = 1.0, random_state: int = 42) -> None:
        super().__init__(random_state)        # random_state kept for interface parity;
        self.alpha = alpha                    #   Ridge(solver="cholesky") needs no seed
        self._estimator: Any = None
```

### list of tasks (dependency-ordered)

```yaml
# ════════ STEP 1 — Schema ════════

Task 1 — MODIFY app/features/forecasting/schemas.py — ADD ProphetLikeModelConfig:
  - PLACE the new class AFTER RegressionModelConfig (after schemas.py:189), before the
        ModelConfig union.
  - MIRROR RegressionModelConfig's ModelConfigBase idiom (see Data models above).
  - ADD `ProphetLikeModelConfig` to the ModelConfig union (schemas.py:192-199).
  - VALIDATE: uv run mypy app/features/forecasting/schemas.py

# ════════ STEP 2 — The forecaster + factory ════════

Task 2 — MODIFY app/features/forecasting/models.py — imports + _PROPHET_LIKE_COMPONENTS:
  - ADD the three sklearn imports (Ridge, SimpleImputer, Pipeline) near models.py:20-22,
        each with `# type: ignore[import-untyped]` (mirror the existing
        HistGradientBoostingRegressor import).
  - ADD the module-scope `_PROPHET_LIKE_COMPONENTS` dict and the `ForecastDecomposition`
        dataclass (see Data models above). Place the dataclass near FitResult (models.py:28).
  - VALIDATE: uv run ruff check app/features/forecasting/models.py

Task 3 — MODIFY app/features/forecasting/models.py — ADD ProphetLikeForecaster:
  - PLACE the new class AFTER LightGBMForecaster (after models.py:732), BEFORE the
        ModelType alias.
  - MIRROR RegressionForecaster for the guard shape + error strings: fit guards (X None ->
        ValueError "ProphetLikeForecaster requires exogenous features X for fit()"; empty y
        -> "Cannot fit on empty array"; row mismatch -> f"X has {X.shape[0]} rows but y has
        {len(y)} — feature/target rows must match"); predict guards (not fitted ->
        RuntimeError "Model must be fitted before predict"; X None -> ValueError
        "ProphetLikeForecaster requires exogenous features X for predict()"; shape mismatch
        -> f"X has {X.shape[0]} rows but horizon is {horizon} — they must match").
  - INSIDE fit(): build the Pipeline and fit it:
        estimator: Any = Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("ridge", Ridge(alpha=self.alpha, solver="cholesky")),
        ])
        estimator.fit(X, y)        # Pipeline is fit(X, y); imputer learns medians on X here
        self._estimator = estimator
  - set requires_features: ClassVar[bool] = True; get_params returns {alpha, random_state};
        set_params mirrors RegressionForecaster.set_params.
  - ADD the decompose() method (see Per-task pseudocode) — model-specific, NOT on
        BaseForecaster.
  - VALIDATE: uv run mypy app/features/forecasting/models.py && uv run pyright app/features/forecasting/

Task 4 — MODIFY app/features/forecasting/models.py — ModelType literal + model_factory:
  - ADD "prophet_like" to the ModelType Literal (models.py:736).
  - ADD an `elif model_type == "prophet_like":` branch to model_factory, mirroring the
        `regression` branch (models.py:793-803) — NO flag gate:
            elif model_type == "prophet_like":
                from app.features.forecasting.schemas import ProphetLikeModelConfig
                if isinstance(config, ProphetLikeModelConfig):
                    return ProphetLikeForecaster(alpha=config.alpha, random_state=random_state)
                raise ValueError("Invalid config type for prophet_like")
  - VALIDATE: uv run mypy app/ && uv run pyright app/

# ════════ STEP 3 — Jobs integration ════════

Task 5 — MODIFY app/features/jobs/service.py — _execute_train + _execute_backtest:
  - ADD `ProphetLikeModelConfig` to the forecasting-schemas import (jobs/service.py:426-433).
  - ADD a prophet_like branch to _execute_train (jobs/service.py:454-478), before the final
        `else`, mirroring the `regression` branch:
            elif model_type == "prophet_like":
                config = ProphetLikeModelConfig(alpha=params.get("alpha", 1.0))
  - ADD a prophet_like branch to _execute_backtest (jobs/service.py:641-658):
            elif model_type == "prophet_like":
                # Feature-aware — the backtest builds per-fold leakage-safe X.
                model_config = ProphetLikeModelConfig()
  - VALIDATE: uv run mypy app/features/jobs/ && uv run pyright app/features/jobs/

# ════════ STEP 4 — Tests ════════

Task 6 — CREATE app/features/forecasting/tests/test_prophet_like_forecaster.py:
  - NO importorskip — pure sklearn, always runs.
  - COPY the `_synthetic_data` helper from test_regression_forecaster.py verbatim, but use
        n_features=14 so the component grouping lines up with the canonical contract (the
        decompose tests need exactly the 14 canonical columns).
  - CLONE the contract tests: fit_predict_roundtrip, fit_rejects_none_features,
        fit_rejects_mismatched_rows, predict_rejects_none_features,
        predict_rejects_wrong_shape_features, predict_before_fit_raises,
        determinism_same_data (np.testing.assert_array_equal), get_and_set_params,
        requires_features_is_true, model_factory_creates_prophet_like_forecaster (NO flag).
  - VALIDATE: uv run pytest -v app/features/forecasting/tests/test_prophet_like_forecaster.py

Task 7 — MODIFY app/features/forecasting/tests/test_prophet_like_forecaster.py — model-specific tests:
  - test_handles_nan_features: a future frame with NaN lag cells predicts finite values
        (the SimpleImputer fills them) — a plain Ridge would raise. Assert np.all(isfinite).
  - test_additive_invariant: for a fitted model, `d = model.decompose(X)`;
        np.testing.assert_allclose(
            d.intercept + d.trend + d.seasonality + d.holiday_regressor,
            model.predict(len(X), X), rtol=1e-9)
  - test_decompose_components_have_horizon_length: each of d.trend/seasonality/
        holiday_regressor has shape (len(X),).
  - test_decompose_uses_trained_imputer_statistics: fit on X_train (no NaN), then call
        decompose on an X_future whose lag cell is NaN; assert the imputed value used is
        the TRAINING-column median (not the future-column median) — i.e. decompose's
        imputed X equals `model._estimator.named_steps["impute"].transform(X_future)`.
  - test_decompose_before_fit_raises: decompose() before fit() raises RuntimeError.
  - VALIDATE: uv run pytest -v app/features/forecasting/tests/test_prophet_like_forecaster.py

Task 8 — MODIFY app/features/forecasting/tests/test_service.py:
  - In TestFeatureAwareContract.test_requires_features_flag, ADD:
        from app.features.forecasting.models import ProphetLikeForecaster
        from app.features.forecasting.schemas import ProphetLikeModelConfig
        assert model_factory(ProphetLikeModelConfig()).requires_features is True
  - (No flag test — prophet_like has no feature flag.)
  - VALIDATE: uv run pytest -v -m "not integration" app/features/forecasting/tests/test_service.py

Task 9 — MODIFY app/features/jobs/tests/test_service.py:
  - ADD test_execute_train_builds_prophet_like_config mirroring
        test_execute_train_builds_regression_config (lines 204-220).
  - ADD test_execute_backtest_builds_prophet_like_config mirroring
        test_execute_backtest_builds_regression_config (lines 263-284).
  - VALIDATE: uv run pytest -v app/features/jobs/tests/test_service.py

Task 10 — MODIFY app/features/scenarios/tests/test_routes_integration.py:
  - ADD an integration test that trains a `prophet_like` model then POSTs
        /scenarios/simulate with its run_id and asserts `method == "model_exogenous"`.
        Mirror the existing regression model_exogenous test. NO importorskip, NO flag.
  - VALIDATE: uv run pytest -v -m integration app/features/scenarios/tests/test_routes_integration.py

Task 11 — MODIFY app/features/backtesting/tests/test_feature_aware_backtest.py:
  - ADD a test that runs the feature-aware backtest with a ProphetLikeModelConfig and
        asserts per-fold metrics + feature_aware=True — mirroring
        test_feature_aware_backtest_produces_per_fold_metrics. Satisfies INITIAL-MLZOO-B's
        "backtesting integration test comparing baseline and advanced model path".
  - VALIDATE: uv run pytest -v app/features/backtesting/tests/test_feature_aware_backtest.py

# ════════ STEP 5 — Docs & example ════════

Task 12 — CREATE examples/models/prophet_like_additive.py:
  - A runnable script: build a synthetic [n, 14] frame matching
        canonical_feature_columns(), fit ProphetLikeForecaster(alpha=1.0), predict a
        horizon, AND call decompose() and print the trend/seasonality/holiday_regressor
        split for the first few rows. Mirror the structure/header of
        examples/models/advanced_lightgbm.py.
  - VALIDATE: uv run python examples/models/prophet_like_additive.py

Task 13 — MODIFY examples/models/model_interface.md + feature_frame_contract.md:
  - model_interface.md: ADDITIVE — add a ProphetLikeModelConfig entry under "## Model
        Configurations" and a "### Prophet-like Forecaster" entry under "## Model
        Formulas" (give the additive formula y = intercept + trend + seasonality +
        holiday_regressor and the component column grouping). Note requires_features=True,
        no optional extra, and the decompose() affordance.
  - feature_frame_contract.md: ADDITIVE — record prophet_like as an IMPLEMENTED
        feature-aware model. Do NOT rewrite the file.
  - VALIDATE: uv run ruff check . && uv run ruff format --check .

Task 14 — MODIFY README.md:
  - ADDITIVE: add `prophet_like` to the Supported Model Types list (README.md:344 area) —
        "Prophet-like additive linear model (trend / seasonality / regressor
        decomposition); pure scikit-learn, always available, no extra to install". Mirror
        the existing tone.
  - VALIDATE: uv run ruff format --check .
```

### Per-task pseudocode (critical details only)

```python
# ── Task 3 — ProphetLikeForecaster.fit / predict / decompose ──

def fit(self, y, X=None):
    if X is None:
        raise ValueError("ProphetLikeForecaster requires exogenous features X for fit()")
    if len(y) == 0:
        raise ValueError("Cannot fit on empty array")
    if X.shape[0] != len(y):
        raise ValueError(
            f"X has {X.shape[0]} rows but y has {len(y)} — feature/target rows must match"
        )
    estimator: Any = Pipeline([
        ("impute", SimpleImputer(strategy="median")),   # learns medians on THIS X only
        ("ridge", Ridge(alpha=self.alpha, solver="cholesky")),  # deterministic, closed-form
    ])
    estimator.fit(X, y)              # sklearn order is fit(X, y); imputer NaN-safe
    self._estimator = estimator
    self._last_values = np.asarray(y[-1:], dtype=np.float64)
    self._is_fitted = True
    return self

def predict(self, horizon, X=None):
    # guards identical in shape to RegressionForecaster.predict (models.py:522-546)
    if not self._is_fitted or self._estimator is None:
        raise RuntimeError("Model must be fitted before predict")
    if X is None:
        raise ValueError("ProphetLikeForecaster requires exogenous features X for predict()")
    if X.shape[0] != horizon:
        raise ValueError(f"X has {X.shape[0]} rows but horizon is {horizon} — they must match")
    return np.asarray(self._estimator.predict(X), dtype=np.float64)   # Pipeline imputes then Ridge

def decompose(self, X):
    """Additive trend / seasonality / holiday-regressor breakdown of a forecast.

    Operates on the IMPUTED X (the trained imputer's transform) so the
    contributions sum exactly to predict(). Returns a ForecastDecomposition.
    """
    if not self._is_fitted or self._estimator is None:
        raise RuntimeError("Model must be fitted before decompose")
    imputer = self._estimator.named_steps["impute"]
    ridge = self._estimator.named_steps["ridge"]
    x_imputed = imputer.transform(X)                  # trained medians fill any NaN
    columns = canonical_feature_columns()             # the 14-name ordered contract
    contributions: dict[str, np.ndarray] = {}
    for component, comp_cols in _PROPHET_LIKE_COMPONENTS.items():
        idx = [columns.index(c) for c in comp_cols]   # column positions for this component
        # additive contribution = Σ coef_i · x_i over this component's columns
        contributions[component] = x_imputed[:, idx] @ ridge.coef_[idx]
    return ForecastDecomposition(
        intercept=float(ridge.intercept_),
        trend=contributions["trend"],
        seasonality=contributions["seasonality"],
        holiday_regressor=contributions["holiday_regressor"],
    )
    # Invariant: intercept + trend + seasonality + holiday_regressor == predict(len(X), X)
    # because the three component column-sets partition all 14 columns exactly.

# ── Task 4 — model_factory: no flag gate (unlike lightgbm/xgboost) ──
elif model_type == "prophet_like":
    from app.features.forecasting.schemas import ProphetLikeModelConfig
    if isinstance(config, ProphetLikeModelConfig):
        return ProphetLikeForecaster(alpha=config.alpha, random_state=random_state)
    raise ValueError("Invalid config type for prophet_like")
```

### Integration Points

```yaml
DEPENDENCY:    none. scikit-learn is already core. NO pyproject.toml / uv.lock change.
CONFIG:        none. No feature flag. NO app/core/config.py change.
ROUTES:        none. No flag -> no route gate. /forecasting/train accepts the new
               model_type with no code change (additive ModelConfig union member).
TRAIN/PREDICT/SCENARIOS/BACKTESTING: all UNCHANGED — every path branches on
               requires_features; a prophet_like model routes through automatically.
JOBS:          jobs/service.py — + prophet_like branch in _execute_train AND
               _execute_backtest (the one place a model_type string compare lives).
PERSISTENCE:   ModelBundle UNCHANGED — sklearn_version covers the pickled Pipeline.
REGISTRY:      _capture_runtime_info UNCHANGED — sklearn_version already recorded.
NO MIGRATION.  NO API CONTRACT CHANGE (a new request-body model_type value is additive
               and pre-1.0-permitted).
```

### Model-specific validation rules (required by INITIAL-MLZOO-C)

Beyond the shared contract tests, the Prophet-like model has four invariants that the tree
models do not, each pinned by a test in `test_prophet_like_forecaster.py`:

1. **Additive invariant** — `decompose()`'s four parts sum (rtol `1e-9`) to `predict()`.
   This is what makes the model "Prophet-like": the forecast genuinely *is* the sum of its
   components. (Task 7 `test_additive_invariant`.)
2. **NaN tolerance via the imputer** — a future frame with `NaN` lag cells must predict
   finite values; a model-specific guarantee the bare `Ridge` does not have. (Task 7
   `test_handles_nan_features`.)
3. **Imputer leakage-safety** — `decompose()`/`predict()` impute future-frame `NaN` with
   *training-window* medians, never future-window medians. (Task 7
   `test_decompose_uses_trained_imputer_statistics`.) This is the model-specific
   leakage rule; the frame-level leakage is already covered by the pinned shared specs.
4. **Determinism** — `Ridge(solver="cholesky")` + `SimpleImputer(median)` are deterministic;
   two fits give identical forecasts. (Task 6 `test_determinism_same_data`.)

---

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . --fix && uv run ruff format --check .
```

### Level 2: Type Checks

```bash
uv run mypy app/        # --strict
uv run pyright app/     # --strict
# The sklearn imports carry `# type: ignore[import-untyped]` (mirror models.py:20-22).
# ForecastDecomposition is a concretely-typed dataclass — no `Any` leakage in decompose()'s
# public return.
```

### Level 3: Unit Tests

```bash
uv run pytest -v app/features/forecasting/tests/test_prophet_like_forecaster.py
uv run pytest -v -m "not integration" app/features/forecasting/tests/test_service.py
uv run pytest -v app/features/jobs/tests/test_service.py
uv run pytest -v app/features/backtesting/tests/test_feature_aware_backtest.py

# Regression — must stay green, no behaviour change
uv run pytest -v -m "not integration"
# Expected: all green. test_prophet_like_forecaster.py RUNS unconditionally (no
# importorskip — sklearn is core). Every existing model's tests pass UNEDITED.
```

### Level 4: Integration Tests

```bash
docker compose up -d && uv run alembic upgrade head
uv run pytest -v -m integration app/features/forecasting/ app/features/scenarios/ \
  app/features/jobs/
# The scenarios prophet_like model_exogenous test (Task 10) must report
# method="model_exogenous".
```

### Level 5: Manual Validation (dogfood — REQUIRED)

```bash
# 1. Determinism + the additive invariant
uv run python -c "
import numpy as np
from app.features.forecasting.models import ProphetLikeForecaster
rng = np.random.default_rng(0)
X = rng.normal(size=(120, 14)); y = (3.0*X[:,0] - 2.0*X[:,4] + rng.normal(size=120)).astype(float)
m1 = ProphetLikeForecaster(alpha=1.0).fit(y, X)
m2 = ProphetLikeForecaster(alpha=1.0).fit(y, X)
np.testing.assert_array_equal(m1.predict(12, X[:12]), m2.predict(12, X[:12]))
d = m1.decompose(X[:12])
np.testing.assert_allclose(
    d.intercept + d.trend + d.seasonality + d.holiday_regressor, m1.predict(12, X[:12]), rtol=1e-9)
print('prophet_like deterministic + additive invariant OK')"

# 2. NaN tolerance
uv run python -c "
import numpy as np
from app.features.forecasting.models import ProphetLikeForecaster
rng = np.random.default_rng(1)
X = rng.normal(size=(80, 14)); y = X[:,0].astype(float)
m = ProphetLikeForecaster().fit(y, X)
fut = X[:6].copy(); fut[2, 0] = np.nan        # un-resolvable lag cell
preds = m.predict(6, fut)
assert np.all(np.isfinite(preds)); print('prophet_like NaN-tolerant OK', preds[:3])"

# 3. End-to-end: POST /forecasting/train with config {"model_type":"prophet_like"} -> 200
#    (no flag needed); POST /scenarios/simulate -> method == "model_exogenous";
#    submit a prophet_like backtest job -> completes with per-fold metrics.
```

---

## Final Validation Checklist

- [ ] `uv run ruff check .` and `uv run ruff format --check .` clean.
- [ ] `uv run mypy app/` and `uv run pyright app/` clean (both --strict).
- [ ] `uv run pytest -v -m "not integration"` fully green; `test_prophet_like_forecaster.py`
      RUNS unconditionally (no importorskip) and passes — including the additive-invariant,
      NaN-tolerance, and imputer-leakage-safety tests.
- [ ] `uv run pytest -v -m integration app/features/{forecasting,scenarios,jobs}/` green,
      including the scenarios `prophet_like` `model_exogenous` test.
- [ ] `model_factory(ProphetLikeModelConfig())` returns a `ProphetLikeForecaster` with
      **no flag and no "not enabled" path**.
- [ ] A `prophet_like` backtest produces per-fold metrics with **no edit to
      `backtesting/service.py`**.
- [ ] Every baseline / `regression` / `lightgbm` test passes with **no edit**.
- [ ] **No** `pyproject.toml`, `uv.lock`, `app/core/config.py`, `forecasting/routes.py`,
      `persistence.py`, or `registry/service.py` change — confirm via `git diff --name-only`.
- [ ] No Alembic migration; no new dependency; no route-path/response-schema/WebSocket
      change.
- [ ] `git diff --stat` shows only intended files — no whole-file CRLF/LF noise diffs.
- [ ] An OPEN GitHub issue exists (`gh issue view <N> --json state` → `OPEN`); commit
      `feat(forecast): add Prophet-like additive forecasting model (#<issue>)`; branch
      `feat/forecasting-prophet-like-model` off `dev`.
- [ ] The PR description states C2 is one of two MLZOO-C review units, links the sibling
      `PRP-MLZOO-C1`, and explicitly states the model is Prophet-LIKE (additive linear
      approximation), not the real `prophet` package.

---

## Anti-Patterns to Avoid

- ❌ Don't implement the XGBoost model — that is `PRP-MLZOO-C1`, a separate branch.
- ❌ Don't combine C1 and C2 into one branch or one PR (DECISIONS LOCKED #1).
- ❌ Don't add the real `prophet` package, `cmdstanpy`, Stan, or an `ml-prophet` extra —
  this model is deliberately pure scikit-learn (DECISIONS LOCKED #2).
- ❌ Don't add a `forecast_enable_prophet_like` flag or a route gate — a pure-sklearn model
  ships always-on, like `regression`.
- ❌ Don't add Fourier seasonal columns or any new feature-frame columns — the model
  consumes the canonical 14-column frame unchanged (DECISIONS LOCKED #3); new columns are a
  new leakage surface.
- ❌ Don't impute `X` by hand or call `SimpleImputer().fit_transform(X_future)` — keep the
  imputer INSIDE the `Pipeline` so it learns medians on train `X` only (leakage).
- ❌ Don't compute `decompose()` on the raw NaN-containing `X` — it must use the trained
  imputer's `transform(X)`, or the additive invariant breaks and NaN propagates.
- ❌ Don't use `LinearRegression` (unstable on the collinear frame) or `ElasticNet` (L1
  zeros curated columns; iterative) — use `Ridge(solver="cholesky")`.
- ❌ Don't use `Ridge(solver="sag"/"saga")` — they are stochastic and break determinism.
- ❌ Don't add `seasonality_mode`, Fourier-order, or changepoint fields to
  `ProphetLikeModelConfig` — DECISIONS LOCKED #4 keeps it to `alpha`.
- ❌ Don't edit `train_model`/`predict`, `scenarios/service.py`, or `backtesting/service.py`
  — they branch on `requires_features`.
- ❌ Don't write a new frame leakage test — the model reuses the pinned shared builders.
- ❌ Don't claim this is "Prophet" anywhere — it is "Prophet-like" / "additive linear".

## Risks & Open Questions

### Risks (document honestly in docstrings + docs)

- **Not real Prophet.** A `Ridge`-over-features model genuinely cannot do what Prophet does:
  - **No changepoint trend.** Prophet fits a piecewise-linear growth curve with automatic
    rate changes; this model's "trend" is only what the lag/`days_since_launch` columns
    encode — a long-horizon forecast trends roughly linearly.
  - **No uncertainty intervals.** `Ridge` returns a point forecast only; Prophet returns
    `yhat_lower`/`yhat_upper` via posterior simulation. Prediction intervals are an Open
    Question (residual quantiles / conformal prediction / `BayesianRidge`).
  - **No automatic seasonality discovery.** Seasonality is fixed at feature-engineering
    time — only the periodicity already in the 14 columns is visible.
  - **Strictly additive.** No multiplicative seasonality (`seasonality_mode`).
- **Extrapolation fragility.** Linear models extrapolate unboundedly; at long horizons the
  lag columns are increasingly imputed (median fill), degrading accuracy. The tree models
  and Prophet degrade more gracefully.
- **Component-grouping is a modelling choice.** Putting the lag columns under `trend` (vs a
  separate `autoregressive` component) is a deliberate, documented simplification — the
  additive invariant holds regardless, but the *labels* are an interpretation.

### Open Questions — to resolve at PRP review

- [ ] **Prediction/uncertainty intervals.** Should v1 expose `yhat_lower`/`yhat_upper`
      (e.g. from training-residual quantiles)? Currently out of scope — point forecast only.
- [ ] **Fourier seasonal columns.** A continuous yearly cycle is not in the canonical
      14-column frame. Adding Fourier yearly terms would improve long-period seasonality but
      requires new frame columns (new leakage surface). Deferred (DECISIONS LOCKED #3) —
      confirm deferral or scope a follow-up.
- [ ] **Changepoint trend.** A piecewise-linear trend basis would close the biggest gap
      vs real Prophet but is a substantial modelling addition. Deferred — flag if wanted.
- [ ] **Surfacing `decompose()`.** v1 keeps `decompose()` as a model method used by tests
      and the example only. Exposing it via an API endpoint / agent tool / the
      explainability slice is a natural MLZOO-D item — confirm it stays out of C2 scope.
- [ ] **`alpha` tuning.** v1 ships a fixed default `alpha=1.0` (caller-overridable). Per-
      series `alpha` selection (e.g. `RidgeCV`) is deferred to a tuning-focused future PRP.

## Confidence Score

**8 / 10** for one-pass implementation success.

Rationale: the consuming infrastructure is fully paid for — train, predict, scenarios, and
backtesting all branch on `requires_features`, and `RegressionForecaster` is a proven
pure-sklearn template, so the wiring is contained (one class, one config, one factory
branch, two jobs branches — and *fewer* touch-points than C1 because there is no
dependency/flag/metadata machinery). The −2 risk is concentrated in the genuinely *new*
design surface: (a) the `decompose()` additive math — the column-index mapping and
imputed-X discipline must be exact for the additive invariant to hold, but the invariant is
a precise, fast unit test that catches any error immediately; and (b) the imputer-leakage
discipline — keeping `SimpleImputer` inside the `Pipeline` is the one rule that, if broken,
silently leaks, and it too is pinned by a model-specific test. Both risks are caught at
Level 3. The "every existing test passes unedited" gate makes any regression impossible to
miss.
