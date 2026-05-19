# INITIAL-MLZOO-B.2-feature-aware-backtesting.md - Feature-Aware Backtesting Wiring

## FEATURE:

Wire **feature-aware forecasting models** (`RegressionForecaster`, `LightGBMForecaster` —
every model with `requires_features=True`) into the backtesting fold loop so they can be
evaluated by `POST /backtesting/run` and `train`/`backtest` jobs — **without** introducing
target leakage and **without** train/serve skew.

This is the explicit follow-up deferred by **PRP-30 DECISIONS LOCKED #6** and named there as
`PRP-MLZOO-B.2`. It depends on MLZOO-A (PRP-29, merged `b116489`) and MLZOO-B (PRP-30, merged
`2f1b8a5` / PR #243) being in place. It is the third MLZOO unit, after A (foundation) and
B (first advanced model), and before C (XGBoost/Prophet) and D (frontend/registry).

### Why current backtesting is incompatible with feature-aware models

The backtesting slice was built for target-only baseline models and has three structural
gaps that block feature-aware models:

1. **No exogenous data is loaded.** `BacktestingService._load_series_data`
   (`app/features/backtesting/service.py`) selects only `(date, quantity)` from `sales_daily`.
   `SeriesData` carries only `dates` + `values`. A feature-aware model needs the canonical
   14-column frame (`canonical_feature_columns()`): target lags, calendar columns, and the
   exogenous columns `price_factor` / `promo_active` / `is_holiday` / `days_since_launch`.

2. **The fold loop is target-only.** `_run_model_backtest` calls `model.fit(y_train)` and
   `model.predict(horizon)` with **no `X`**. `RegressionForecaster` / `LightGBMForecaster`
   (`requires_features=True`) raise `ValueError("… requires exogenous features X …")` at
   `fit()`. That loud failure is the *current interim contract*, pinned by
   `app/features/backtesting/tests/test_service.py::test_feature_aware_model_fails_loud_in_backtest`
   (cites PRP-29 DECISIONS LOCKED #7). This PRP **supersedes** that interim contract.

3. **`JobService._execute_backtest` hard-rejects** any `model_type` other than
   `naive` / `seasonal_naive` / `moving_average` with `ValueError("Unsupported model_type…")`.

A backtest of a feature-aware model is the only honest way to compare an advanced model
against the naive/seasonal baselines — without it, PRP-30's LightGBM model can be trained
and scenario-re-forecast but never *evaluated*.

### Per-fold X_train and X_future construction

The backtest must build, **per fold**, two leakage-safe feature matrices:

- **`X_train`** — the historical feature matrix restricted to the fold's train rows. Every
  column is observed-and-knowable: target lags read strictly-earlier observed targets,
  calendar columns are pure functions of the date, exogenous columns read same-day observed
  price/promotion/holiday/launch attributes. This is exactly the matrix
  `ForecastingService._build_regression_features` / `_assemble_regression_rows` already
  builds for training — it must be **reused**, not re-derived.

- **`X_future`** — the feature matrix for the fold's test window (`test_size` days, after the
  `gap`). The test window has **no observed target**, so its target-lag columns must be built
  with the leakage-safe future-lag rule (`build_long_lag_columns`): a lag cell whose source
  day lies in the test window is `NaN`, never the observed test value.

### Leakage-safe fold contracts

Each fold defines a forecast origin `T` = the fold's `train_end`. The invariant, mirroring
`app/shared/feature_frames/tests/test_leakage.py` and
`app/features/featuresets/tests/test_leakage.py`:

> A feature value for a test-window day `D` may use ONLY information knowable at the fold
> origin `T`: the observed history at or before `T`, or the calendar (a pure function of the
> date). It may **NEVER** read an observed target at a test-window day.

The `gap` between `train_end` and `test_start` simulates operational data latency — the
fold's `history_tail` ends at `T` and does **not** include the gap days; lag columns whose
source falls in the gap are therefore `NaN` too.

The PRP must classify every canonical feature column with the **existing**
`app/shared/feature_frames.FeatureSafety` taxonomy (`SAFE` / `CONDITIONALLY_SAFE` /
`UNSAFE_UNLESS_SUPPLIED`) and decide, per class, how `X_future` is populated. It must also
draw the line — explicitly — between **target leakage** (reading `y` at a horizon day:
forbidden, must be structurally impossible) and **exogenous foresight** (assuming the future
price/promotion calendar is known: a disclosed modelling choice, not target leakage). The
result must record which exogenous policy it used so the metric is interpreted honestly.

### Async / DB-backed loading requirements

The fold loop (`_run_model_backtest`) is currently **synchronous and DB-free** — a property
worth keeping (it is unit-testable without a database). Feature-aware folds need exogenous
data (`unit_price`, `promotion` windows, `calendar` holidays, `product.launch_date`) that
only the DB has. The PRP must resolve all of that **async, once, up front** in `run_backtest`
(already `async`) into pure in-memory arrays, then keep the per-fold builders pure and sync —
mirroring how `ForecastingService._build_regression_features` resolves async then delegates
to the pure `_assemble_regression_rows`.

### How feature-aware models should fail loudly until supported

Even after this PRP, some paths stay unsupported and must fail **loud**, never silent:

- A feature-aware model whose required feature frame cannot be sourced (e.g. an
  `UNSAFE_UNLESS_SUPPLIED` column with no observed data-platform record and no supplied
  assumptions) → raise `ValueError`, never a silent `NaN`/`0.0` fill.
- An unclassifiable feature column (`FeatureSafety` / `feature_safety()` raises `KeyError`)
  → propagate loudly.
- The interim `test_feature_aware_model_fails_loud_in_backtest` is **repurposed**, not
  deleted: feature-aware backtesting now *succeeds* on the supported path, so the test
  becomes (a) a positive "regression model backtests and yields metrics" test plus (b) a new
  loud-fail test for the genuinely-unsupported path.

### Explicit out-of-scope items

- **No new model families.** No XGBoost, no Prophet-like models — that is MLZOO-C. This PRP
  wires the *existing* `regression` and `lightgbm` forecasters into backtesting and adds none.
- **No frontend work.** No changes to `frontend/`, no backtest-page model selector, no new UI.
  The `/visualize/backtest` job-result contract (`_shape_backtest_result`) stays byte-stable.
- **No explainability work.** No driver attribution, no `ForecastExplanation`, no
  `/explain/*` change — that is MLZOO-D.
- **No scenario persistence changes.** No `scenario_plan` schema change, no `/scenarios/*`
  contract change. The scenarios slice's `feature_frame.py` is read as a reference pattern
  only; it is not modified.
- **No hyperparameter search, no portfolio/global models, no recursive multi-step
  forecasting.** `NaN`-as-unknown for future-sourced lags is kept (PRP-29 DECISIONS #6).
- **No new Alembic migration** — this PRP adds no table or column to the database.

## EXAMPLES:

Read these before PRP creation:

- `PRPs/PRP-29-feature-aware-forecasting-foundation.md`
  - The merged foundation. DECISIONS LOCKED #2 (`requires_features` capability flag),
    #6 (NaN-as-unknown), #7 (the interim backtest loud-fail this PRP supersedes).

- `PRPs/PRP-30-lightgbm-first-advanced-model.md`
  - The merged first advanced model. DECISIONS LOCKED #6 explicitly defers feature-aware
    backtesting to *this* PRP and states why (`_run_model_backtest` is sync, DB-free,
    target-only).

- `app/features/backtesting/service.py`
  - `_load_series_data` (target-only load), `SeriesData` (the container to extend),
    `_run_model_backtest` (the sync fold loop to branch), `_run_baseline_comparisons`.

- `app/features/backtesting/splitter.py`
  - `TimeSeriesSplitter` — index-based, needs **no change**; each `TimeSeriesSplit` already
    carries `train_indices` / `test_indices` / `train_dates` / `test_dates`.

- `app/features/forecasting/service.py`
  - `_build_regression_features` (async exogenous resolution pattern) and
    `_assemble_regression_rows` (the pure, leakage-safe historical row builder to promote).

- `app/shared/feature_frames/contract.py`
  - `canonical_feature_columns()`, `build_long_lag_columns`, `build_calendar_columns`,
    the `FeatureSafety` enum and `feature_safety()` classifier — the contract to reuse.

- `app/features/scenarios/feature_frame.py`
  - `assemble_future_frame` / `build_exogenous_columns` — the future-frame *pattern* for a
    feature-aware model. Reference only; do not import (cross-slice import is forbidden).

- `app/shared/feature_frames/tests/test_leakage.py` and
  `app/features/forecasting/tests/test_regression_features_leakage.py`
  - The load-bearing leakage-test patterns the new builders must follow.

- `app/features/jobs/service.py`
  - `_execute_backtest` (the `model_type` allow-list to widen) and `_shape_backtest_result`
    (the frontend contract that must NOT drift).

## DOCUMENTATION:

- scikit-learn TimeSeriesSplit: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- scikit-learn HistGradientBoostingRegressor (NaN-tolerant): https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html
- LightGBM (NaN handling / missing values): https://lightgbm.readthedocs.io/en/stable/Advanced-Topics.html
- Forecasting cross-validation / leakage: https://otexts.com/fpp3/tscv.html
- Pandas time series documentation: https://pandas.pydata.org/docs/user_guide/timeseries.html
- Pydantic documentation: https://docs.pydantic.dev/latest/
- `PRPs/ai_docs/exogenous-regressor-forecasting.md` — repo-local notes on exogenous-regressor
  forecasting and the leakage-safe future-frame rule.

## OTHER CONSIDERATIONS:

The main architectural risk is the **train/serve-skew and leakage boundary** — get the
`X_future` exogenous-column policy wrong and the backtest is either leaky (optimistic and
worthless) or skewed (the model sees different feature distributions at train vs evaluate).

Required decisions for the PRP:

- **Where the per-fold builders live.** `backtesting` may not import `forecasting` or
  `scenarios` (vertical-slice rule). The pure row builders must be promoted into
  `app/shared/feature_frames` (the sanctioned cross-cutting home) so both slices consume one
  definition. The promotion must be **additive** — `forecasting`'s `_assemble_regression_rows`
  and its leakage test must keep working unchanged (a thin delegating shim is acceptable).

- **The `X_future` exogenous-column policy.** `price_factor` / `promo_active` are
  `UNSAFE_UNLESS_SUPPLIED`. In a *scenario* a planner supplies them; a *backtest* has no
  assumptions. Decide v1 policy explicitly (recorded as a field on the result), and document
  it as target-leakage-free but optimistic (it assumes the future promo/price calendar was
  known at `T`).

- **`gap` handling for future-lag columns.** With `gap > 0` the first test day is
  `T + gap + 1`; `build_long_lag_columns` indexes test day `m` as `T + m`. The PRP must state
  the offset correction (build `gap + test_size` rows, drop the first `gap`).

- **The job-result contract.** `_shape_backtest_result` feeds `/visualize/backtest`. Any new
  field must be additive; the existing keys must not move.

Recommended defaults:

- Reuse `canonical_feature_columns()` for both `X_train` and `X_future` — identical column
  set and order on both sides is the train/serve-skew guard.
- Keep the per-fold builders pure and sync; do all DB I/O once in `run_backtest`.
- Branch on `model.requires_features` (a capability flag), never on a `model_type` string.
- Keep `NaN`-as-unknown for future-sourced lag cells — the estimators tolerate it natively.
- Prefer a loud `ValueError` on an unsupported path over any implicit guess or silent fill.

Validation expectations:

- Shared-builder leakage tests proving `X_future` lag cells are `NaN` where their source is a
  test-window day (the new load-bearing spec).
- Unit tests for the per-fold `X_train` / `X_future` builders (pure, no DB).
- An integration test running a real DB-backed feature-aware (`regression`) backtest and
  comparing it against the naive/seasonal baselines in the same response.
- A route test: `POST /backtesting/run` with a `regression` model config → `200`.
- A jobs test: a `backtest` job with `model_type="regression"` succeeds.
- A repurposed loud-fail test for the genuinely-unsupported feature-aware path.
- Regression proof: every existing baseline backtest test stays green with no behaviour change.
