name: "PRP-MLZOO-B.2 — Feature-Aware Backtesting Wiring"
description: |

## Purpose

The third unit of the **Advanced ML Model Zoo** sequence (`PRPs/INITIAL/INITIAL-MLZOO-index.md`),
sitting between MLZOO-B (PRP-30) and MLZOO-C. It wires the **existing feature-aware
forecasting models** — `RegressionForecaster` (PRP-27) and `LightGBMForecaster` (PRP-30),
i.e. every model with `requires_features=True` — into the **backtesting fold loop** so they
can be evaluated by `POST /backtesting/run` and `backtest` jobs.

This is the explicit follow-up deferred by **PRP-30 DECISIONS LOCKED #6**, which named it
`PRP-MLZOO-B.2` and stated the reason: `BacktestingService._run_model_backtest` is
synchronous, DB-free, and target-only, so per-fold leakage-safe `X_train` / `X_future`
construction is itself PRP-sized.

This PRP wires **zero new models**. It adds **no** XGBoost/Prophet, **no** frontend, **no**
explainability, **no** scenario-persistence change, **no** Alembic migration. If you find
yourself adding a model family, touching `frontend/`, or editing a `scenario_plan` schema —
stop; that is out of scope (see DECISIONS LOCKED #9).

## What this PRP already inherits (DO NOT re-build)

MLZOO-A (PRP-29, merged `b116489`) and MLZOO-B (PRP-30, merged `2f1b8a5` / PR #243) shipped
everything a feature-aware *model* needs. Re-use it; do not re-derive it:

- **The capability flag.** `BaseForecaster.requires_features: ClassVar[bool]`
  (`app/features/forecasting/models.py:64`). `RegressionForecaster` and `LightGBMForecaster`
  both set it `True`; all three baselines leave it `False`. **Branch on this flag — never on
  a `model_type` string.**
- **The shared feature-frame contract.** `app/shared/feature_frames/` owns the pinned
  constants (`EXOGENOUS_LAGS`, `HISTORY_TAIL_DAYS`), `canonical_feature_columns()` (the
  14-column set + order), the leakage-safe pure builders `build_long_lag_columns` /
  `build_calendar_columns`, and the `FeatureSafety` taxonomy + `feature_safety()` classifier.
  This PRP **extends** that package; it writes no new contract constants.
- **The historical feature matrix.** `ForecastingService._assemble_regression_rows`
  (`app/features/forecasting/service.py:114`) is the pure, leakage-safe historical row
  builder, pinned by `app/features/forecasting/tests/test_regression_features_leakage.py`.
  This PRP **promotes** it into `app/shared/feature_frames` so the backtesting slice can
  consume it without a forbidden cross-slice import.
- **The future-frame pattern.** `app/features/scenarios/feature_frame.py::assemble_future_frame`
  is the reference for a feature-aware model's *future* matrix (calendar + leakage-safe lags +
  exogenous). This PRP builds the backtesting equivalent in `app/shared/feature_frames`.
  The scenarios module is **read as a pattern, never imported or modified.**
- **The fold splitter.** `app/features/backtesting/splitter.py::TimeSeriesSplitter` is purely
  index-based — each `TimeSeriesSplit` already carries `train_indices` / `test_indices` /
  `train_dates` / `test_dates`. **It needs no change.**

The **problem this PRP fixes**: `BacktestingService._load_series_data` loads only
`(date, quantity)`; `_run_model_backtest` calls `model.fit(y_train)` target-only; a
`requires_features=True` model raises `ValueError` at `fit()`. That loud failure is the
*interim* contract pinned by
`app/features/backtesting/tests/test_service.py::test_feature_aware_model_fails_loud_in_backtest`
(PRP-29 DECISIONS LOCKED #7). `JobService._execute_backtest` hard-rejects every non-baseline
`model_type`. The advanced LightGBM model from PRP-30 can be trained and scenario-re-forecast
but **cannot be evaluated against the baselines** — backtesting is the only honest comparison.

## DEPENDS ON — read before starting

- `PRPs/INITIAL/INITIAL-MLZOO-B.2-feature-aware-backtesting.md` — this PRP's brief.
- `PRPs/INITIAL/INITIAL-MLZOO-index.md` — the roadmap (A ✅ → B ✅ → **B.2 (this)** → C → D).
- `PRPs/PRP-29-feature-aware-forecasting-foundation.md` — DECISIONS LOCKED #2
  (`requires_features`), #6 (NaN-as-unknown), #7 (the interim backtest loud-fail superseded here).
- `PRPs/PRP-30-lightgbm-first-advanced-model.md` — DECISIONS LOCKED #6 defers feature-aware
  backtesting to this PRP and explains why.
- `PRPs/ai_docs/exogenous-regressor-forecasting.md` — the leakage-safe future-frame rule.

## Goal

Make `POST /backtesting/run` (and `backtest` jobs) accept `regression` and `lightgbm` model
configs and evaluate them across time-series CV folds with **per-fold, leakage-safe**
`X_train` / `X_future` feature matrices — the advanced models compared head-to-head against
the naive / seasonal baselines, with **no target leakage** and **no train/serve skew**.

## Why

- **Portfolio completeness.** A forecasting system whose advanced model cannot be backtested
  has no defensible model-selection story. PRP-30 delivered the model; this delivers its
  evaluation.
- **Time-safety is the repo's load-bearing invariant** (`product-vision.md` §5). Wiring a
  feature-consuming model into CV is exactly where leakage creeps in — doing it once, in a
  shared and test-pinned way, protects every future MLZOO model (C, D).
- **It unblocks the MLZOO sequence.** MLZOO-C (XGBoost/Prophet) and MLZOO-D
  (frontend/registry) both assume feature-aware models are backtestable; this is their gate.

## What

### Technical requirements

1. **Per-fold `X_train`** — the historical feature matrix sliced to the fold's train rows.
   Built once over the full series via the promoted shared builder; sliced by
   `split.train_indices`. Leakage-safe by position: every row reads only strictly-earlier
   observed targets.
2. **Per-fold `X_future`** — the test-window feature matrix, **rebuilt per fold** (never
   sliced from the historical matrix). Target-lag columns use `build_long_lag_columns` with a
   `history_tail` ending at the fold origin `T = train_end`; a lag cell whose source is a
   test-window day is `NaN`.
3. **Async exogenous loading up front.** `run_backtest` (already `async`) resolves
   `unit_price`, `promotion` windows, `calendar` holidays, and `product.launch_date` once,
   into pure in-memory arrays. `_run_model_backtest` stays **sync and DB-free**.
4. **Capability branch.** `_run_model_backtest` branches on `model.requires_features`.
   Target-only models keep the exact current code path; feature-aware models take the new
   per-fold builder path.
5. **`JobService._execute_backtest`** accepts `regression` and `lightgbm` (the latter still
   gated by `forecast_enable_lightgbm` inside `model_factory`).
6. **Loud failure** on every unsupported path — never a silent `NaN`/`0.0` fill.
7. **No frontend contract drift.** `_shape_backtest_result` and the `/visualize/backtest`
   job-result keys stay byte-stable; new schema fields are additive only.

### Future feature classes — the `X_future` policy (the architectural core)

Every canonical column is classified by the **existing** `FeatureSafety` enum
(`app/shared/feature_frames/contract.py`). `X_future` populates each class as follows:

| Class | Columns | `X_future` source | Leakage status |
|-------|---------|-------------------|----------------|
| `SAFE` | `dow_sin/cos`, `month_sin/cos`, `is_weekend`, `is_month_end`, `is_holiday`, `days_since_launch` | Pure function of the test-window date / timeless attribute (calendar table, product launch date) | None — never reads a target |
| `CONDITIONALLY_SAFE` | `lag_1`, `lag_7`, `lag_14`, `lag_28` | `build_long_lag_columns(history_tail, …)` — `history_tail` ends at `T`; a cell whose source day is in the test window is `NaN` | None — `NaN`-where-future is structurally enforced |
| `UNSAFE_UNLESS_SUPPLIED` | `price_factor`, `promo_active` | v1 policy `observed`: recorded `sales_daily.unit_price` / `promotion` rows for the test window | **No target leakage**; *is* exogenous foresight (see below) |

**Target leakage vs. exogenous foresight — the line this PRP draws explicitly.** The repo's
load-bearing leakage rule is: *never read an observed target at a horizon day*. Target-lag
columns obey it structurally (`build_long_lag_columns`). The `UNSAFE_UNLESS_SUPPLIED`
exogenous columns (`price_factor`, `promo_active`) read **recorded price/promotion** for the
test window — never the target `y`. That is **not** target leakage. It **is** *exogenous
foresight*: the backtest assumes the future price/promotion calendar was known at `T`. For
retail demand that is realistic (promo calendars are planned ahead) and it keeps `X_train`
and `X_future` distributionally identical (no train/serve skew — both read same-day observed
exogenous). It is, however, optimistic, so the result **records `exogenous_policy="observed"`**
and the metric must be interpreted as "accuracy given a known promo/price plan". A future
PRP may add an `assumptions` policy; v1 ships exactly one.

### Success Criteria

- [ ] `POST /backtesting/run` with a `regression` model config returns `200` with per-fold
      metrics and a baseline comparison.
- [ ] A `backtest` job with `model_type="regression"` completes `success`.
- [ ] A feature-aware backtest's `X_future` lag cells are `NaN` exactly where their source
      day falls in the test window — pinned by a new shared leakage test.
- [ ] `X_train` and `X_future` use the identical `canonical_feature_columns()` set and order.
- [ ] Every existing baseline backtest test passes with **zero** edits.
- [ ] `_shape_backtest_result` output keys are byte-stable (frontend contract intact).
- [ ] An unsupported feature-aware path raises a loud `ValueError`, never silently degrades.
- [ ] `ruff` + `mypy --strict` + `pyright --strict` clean; unit + integration suites green.

## All Needed Context

### Documentation & References

```yaml
- file: app/features/backtesting/service.py
  why: _load_series_data (extend), SeriesData (extend), _run_model_backtest (branch),
       _run_baseline_comparisons, _validate_config (add min-train guard).

- file: app/features/backtesting/splitter.py
  why: TimeSeriesSplit carries train/test indices + dates. NO CHANGE — index-based.

- file: app/features/forecasting/service.py
  why: _build_regression_features = the async exogenous-resolution pattern to mirror;
       _assemble_regression_rows = the pure historical builder to promote to shared.

- file: app/shared/feature_frames/contract.py
  why: canonical_feature_columns(), build_long_lag_columns, build_calendar_columns,
       FeatureSafety + feature_safety(). The contract this PRP extends.

- file: app/features/scenarios/feature_frame.py
  why: assemble_future_frame = the future-matrix PATTERN. Reference only — do NOT import
       (backtesting -> scenarios is a forbidden cross-slice import).

- file: app/features/jobs/service.py
  why: _execute_backtest (widen the model_type allow-list); _shape_backtest_result
       (the frontend contract — additive changes only, keys must not move).

- file: app/shared/feature_frames/tests/test_leakage.py
  why: the load-bearing leakage-test pattern the new builder must follow.

- file: app/features/forecasting/tests/test_regression_features_leakage.py
  why: pins _assemble_regression_rows — must stay GREEN after the promotion (shim).

- url: https://otexts.com/fpp3/tscv.html
  why: time-series cross-validation — the standard this fold loop implements.
```

### Current Codebase tree (relevant — all already exist)

```text
app/
  shared/feature_frames/
    __init__.py            # re-exports the contract surface
    contract.py            # constants, builders, FeatureSafety
    tests/test_leakage.py  # load-bearing leakage spec
    tests/test_contract.py # AST walk — no app/features import
  features/
    backtesting/
      service.py           # SeriesData, run_backtest, _run_model_backtest (target-only)
      splitter.py          # TimeSeriesSplitter — index-based, unchanged
      schemas.py           # BacktestConfig, ModelBacktestResult, BacktestResponse
      tests/test_service.py, test_service_integration.py, test_routes_integration.py
    forecasting/
      service.py           # _assemble_regression_rows (to promote), _build_regression_features
    jobs/
      service.py           # _execute_backtest (allow-list), _shape_backtest_result
```

### Desired Codebase tree — files to ADD

```text
app/shared/feature_frames/
  rows.py                                    # build_historical_feature_rows (promoted),
                                             # build_future_feature_rows (NEW, leakage-safe)
app/features/backtesting/tests/
  test_feature_aware_backtest.py             # unit tests for the fold builders + loud-fail
PRPs/
  PRP-MLZOO-B.2-feature-aware-backtesting.md # this file
```

### Files to MODIFY (all additive or behaviour-preserving)

```text
app/shared/feature_frames/__init__.py        # export the two row builders
app/shared/feature_frames/tests/test_leakage.py   # ADD build_future_feature_rows leakage spec
app/shared/feature_frames/tests/test_contract.py  # ADD: rows.py imports nothing from app/features
app/features/forecasting/service.py          # _assemble_regression_rows -> delegating shim
app/features/backtesting/service.py          # ExogenousFrame, exogenous load, fold branch
app/features/backtesting/schemas.py          # ADD feature_aware + exogenous_policy (additive)
app/features/jobs/service.py                 # _execute_backtest: accept regression + lightgbm
app/features/backtesting/tests/test_service.py            # repurpose the interim loud-fail test
app/features/backtesting/tests/test_service_integration.py # feature-aware DB-backed backtest
app/features/backtesting/tests/test_routes_integration.py  # POST /backtesting/run regression
app/features/backtesting/tests/test_schemas.py            # the new additive fields
app/features/jobs/tests/test_service.py      # backtest job with model_type=regression
examples/models/feature_frame_contract.md    # document the backtest future-frame
docs/PHASE/5-BACKTESTING.md                  # feature-aware backtesting section
README.md                                    # backtest model list: add regression/lightgbm
PRPs/INITIAL/INITIAL-MLZOO-index.md           # note B.2 -> this PRP
```

### DECISIONS LOCKED (resolved during planning — do NOT re-litigate)

1. **The per-fold row builders live in `app/shared/feature_frames/rows.py`.** `backtesting`
   may not import `forecasting` or `scenarios` (vertical-slice rule). `app/shared/` is the
   sanctioned cross-cutting home and already owns the column builders. `rows.py` (pure,
   stdlib-only, `app/features` import forbidden — same as `contract.py`) holds the two
   row-matrix assemblers. `contract.py` stays the column-builder + taxonomy home.

2. **`_assemble_regression_rows` is PROMOTED, not duplicated, and the promotion is additive.**
   Its body moves verbatim to `build_historical_feature_rows` in `rows.py`.
   `ForecastingService._assemble_regression_rows` becomes a one-line delegating shim
   (`return build_historical_feature_rows(...)`). `test_regression_features_leakage.py`
   imports the shim by its old name and stays **GREEN with zero edits** — the existing
   leakage test is not weakened, not moved, not touched.

3. **`X_train` is sliced from one full-series historical matrix; `X_future` is NEVER sliced.**
   The historical matrix is built once over `dates[0:N]` (each row reads only strictly-earlier
   targets → leakage-safe as a *training* row). Per fold, `X_train = matrix[train_indices]`.
   `X_future` MUST be rebuilt per fold via `build_future_feature_rows` — slicing the
   historical matrix for test rows would let `lag_1` read an adjacent test-day observed target
   (**target leakage**). This asymmetry is the crux of the PRP (see GOTCHA below).

4. **The v1 `X_future` exogenous policy is `observed`, recorded on the result.** `price_factor`
   / `promo_active` for the test window come from recorded `sales_daily.unit_price` /
   `promotion` rows. This is exogenous foresight, not target leakage (it never reads `y`), and
   it keeps `X_train`/`X_future` skew-free (both read same-day observed exogenous).
   `ModelBacktestResult.exogenous_policy` records `"observed"` so the metric is interpreted
   honestly. A `Literal["observed"]` (one value in v1) is the documented extension seam — a
   future PRP may add `"assumptions"` without a breaking change.

5. **Branch on `model.requires_features`, never on a `model_type` string.** `run_backtest`
   builds a cheap probe model from `config.model_config_main` to read the flag *before* the
   fold loop, deciding whether to load exogenous data. Mirrors
   `ForecastingService.train_model`, which already branches on exactly this flag.
   The probe is a no-fit `model_factory(...)` construction (cheap) — each of the three
   sites that need the flag (`_validate_config`, `run_backtest`, `_run_model_backtest`)
   builds its own probe locally; there is no need to thread one instance through, and
   `BacktestingService` keeps no probe/matrix instance state.

6. **The fold loop stays sync and DB-free.** All DB I/O happens once in `run_backtest`
   (`async`), resolved into a pure `ExogenousFrame`. `_run_model_backtest` and the row
   builders remain unit-testable without a database — the existing architecture is preserved.

7. **`min_train_size >= 30` is enforced for feature-aware backtests.** `_validate_config`
   raises `ValueError` when the main model `requires_features` and
   `split_config.min_train_size < 30` (`_MIN_REGRESSION_TRAIN_ROWS`) — each fold's train
   window must resolve the lag features. Loud, not silent.

8. **The interim loud-fail test is REPURPOSED, not deleted.**
   `test_feature_aware_model_fails_loud_in_backtest` asserted a `regression` backtest raises
   `ValueError`. After this PRP it succeeds. The test is rewritten as (a) a positive
   "feature-aware backtest runs and yields metrics" assertion and (b) a new loud-fail
   assertion for the genuinely-unsupported path (a `requires_features` model with no
   `ExogenousFrame` loaded → `ValueError`). PRP-29 DECISIONS LOCKED #7 and PRP-30 DECISIONS
   LOCKED #6 are **superseded** — note this in the PRP commit body and the test docstring.

9. **OUT OF SCOPE — do not touch.** No new model family (XGBoost/Prophet = MLZOO-C). No
   `frontend/` change — `_shape_backtest_result` keys stay byte-stable. No explainability
   (MLZOO-D). No `scenario_plan` / `/scenarios/*` change. No Alembic migration (this PRP adds
   no table/column). No recursive multi-step forecasting — `NaN`-as-unknown is kept.

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: X_future is NEVER a slice of the historical matrix. The historical row for a
#   test day reads quantities[i-1] (lag_1) — for a test day that source is an adjacent
#   observed TEST-DAY target == target leakage. X_future MUST be rebuilt per fold with
#   build_long_lag_columns(history_tail_ending_at_T, ...) so future-sourced lag cells are NaN.

# CRITICAL: gap offset. With gap > 0 the first test day is T + gap + 1, but
#   build_long_lag_columns indexes test day m as T + m. Call it with
#   horizon = gap + test_size and DROP the first `gap` rows. With gap=0 (the common case)
#   this is a no-op. test_feature_aware_backtest.py MUST cover a gap>0 fold.

# CRITICAL: history_tail ends at T = train_end, and EXCLUDES the gap days. The gap simulates
#   operational data latency — data for gap days is "not yet available" at forecast time.
#   history_tail = series.values[:train_end_idx][-HISTORY_TAIL_DAYS:] where
#   train_end_idx = split.train_indices[-1] + 1.

# GOTCHA: leaf-level import rule. app/shared/feature_frames/rows.py may NEVER import from
#   app/features/** (test_contract.py enforces it with an AST walk). Keep rows.py pure —
#   stdlib math/datetime only, same as contract.py.

# GOTCHA: SeriesData.__post_init__ computes n_observations from `values`. Adding an optional
#   `exogenous: ExogenousFrame | None = None` field is fine — keep it last, keep the default.

# GOTCHA: ModelBacktestResult is frozen-free but consumed by _shape_backtest_result. New
#   fields (feature_aware: bool = False, exogenous_policy: str | None = None) MUST have
#   defaults so every existing construction site and test stays valid.

# GOTCHA: lightgbm in a backtest job. _execute_backtest building a LightGBMModelConfig is
#   fine — model_factory still raises ValueError if forecast_enable_lightgbm is False. That
#   surfaces as a failed job (loud), which is correct. Do not pre-check the flag in jobs.

# GOTCHA: baseline comparison. _run_baseline_comparisons runs naive + seasonal_naive — both
#   target-only (requires_features=False). They take the UNCHANGED target-only fold path
#   even when the main model is feature-aware. Do not feed them X.

# GOTCHA: line endings — repo has mixed CRLF/LF, no .gitattributes. Run `git diff --stat`
#   before committing; re-normalise any whole-file diff to the file's original ending.
```

## Implementation Blueprint

### Data models and structure

```python
# app/shared/feature_frames/rows.py  (NEW — pure, stdlib only)

def build_historical_feature_rows(
    *, dates: list[date], quantities: list[float], prices: list[float],
    baseline_price: float, promo_dates: set[date], holiday_dates: set[date],
    launch_date: date | None,
) -> list[list[float]]:
    """Promoted verbatim from ForecastingService._assemble_regression_rows.
    Row i: target lags read quantities[i-lag] (strictly earlier), calendar columns
    are pure, exogenous columns read same-day observed attributes. canonical order."""

def build_future_feature_rows(
    *, test_dates: list[date], history_tail: list[float], gap: int,
    test_prices: list[float], baseline_price: float, test_promo_dates: set[date],
    test_holiday_dates: set[date], launch_date: date | None,
) -> list[list[float]]:
    """Leakage-safe test-window matrix. lag_* columns come from
    build_long_lag_columns(history_tail, gap + len(test_dates))[gap:] — NaN where the
    source day is in the test window. Calendar columns pure. price_factor / promo_active
    from the OBSERVED test-window records (policy='observed'). canonical order.
    Raises ValueError if asked to emit a column it cannot classify/source."""
```

```python
# app/features/backtesting/service.py  (MODIFY)

@dataclass
class ExogenousFrame:
    """Pre-loaded exogenous data for one series — resolved async in run_backtest,
    consumed by the pure/sync fold loop."""
    prices: list[float]              # aligned with SeriesData.dates
    baseline_price: float            # median positive price (>0 fallback 1.0)
    promo_dates: set[date]
    holiday_dates: set[date]
    launch_date: date | None

@dataclass
class SeriesData:
    dates: list[date]
    values: np.ndarray
    store_id: int
    product_id: int
    exogenous: ExogenousFrame | None = None   # NEW — present only for feature-aware runs
    n_observations: int = field(init=False)
```

### list of tasks (dependency-ordered)

```yaml
# ════════ STEP 1 — Shared row builders (pure, no behaviour change) ════════
Task 1: CREATE app/shared/feature_frames/rows.py
  - build_historical_feature_rows: body lifted verbatim from _assemble_regression_rows.
  - build_future_feature_rows: NEW — see Per-task pseudocode.
  - Pure: import only math/datetime + the contract builders. No app/features import.

Task 2: MODIFY app/shared/feature_frames/__init__.py
  - Export build_historical_feature_rows, build_future_feature_rows.

Task 3: MODIFY app/features/forecasting/service.py
  - _assemble_regression_rows becomes a one-line shim delegating to
    build_historical_feature_rows. Keep the signature and name byte-identical so
    test_regression_features_leakage.py imports stay valid.

# ════════ STEP 2 — Shared leakage spec ════════
Task 4: MODIFY app/shared/feature_frames/tests/test_leakage.py
  - ADD: build_future_feature_rows lag cells are NaN exactly where source day is in the
    test window; an observed test-day target never appears as a lag value out of place;
    gap>0 case; the historical-vs-future asymmetry.
Task 5: MODIFY app/shared/feature_frames/tests/test_contract.py
  - ADD rows.py to the AST walk asserting no app/features import.

# ════════ STEP 3 — Backtesting schemas (additive) ════════
Task 6: MODIFY app/features/backtesting/schemas.py
  - ModelBacktestResult: ADD feature_aware: bool = False,
    exogenous_policy: Literal["observed"] | None = None  (defaults preserve all callers).

# ════════ STEP 4 — Backtesting service wiring ════════
Task 7: MODIFY app/features/backtesting/service.py
  - ADD ExogenousFrame; ADD optional SeriesData.exogenous.
  - _validate_config: if main model requires_features and min_train_size < 30 -> ValueError.
  - run_backtest: build a probe model from config.model_config_main; if requires_features,
    call new async _load_exogenous_frame and attach to series_data.exogenous.
  - _run_model_backtest: signature is UNCHANGED (still series_data, splitter,
    model_config, store_fold_details). It builds a probe model, branches on
    probe.requires_features, reads gap from splitter.config.gap, and builds the full
    historical matrix as a LOCAL once before the fold loop.
      target-only  -> existing code path, untouched.
      feature-aware -> _run_feature_aware_fold (new helper, all args explicit): per fold
                       slice X_train from the local historical matrix, build X_future,
                       fit(y,X_train), predict(test_size, X_future). Set feature_aware +
                       exogenous_policy on the ModelBacktestResult.
  - ADD _load_exogenous_frame (async): unit_price per date, promotion windows, calendar
    holidays, product.launch_date — mirrors _build_regression_features.

# ════════ STEP 5 — Jobs integration ════════
Task 8: MODIFY app/features/jobs/service.py
  - _execute_backtest: add regression + lightgbm branches building RegressionModelConfig /
    LightGBMModelConfig. _shape_backtest_result UNCHANGED (frontend contract byte-stable).

# ════════ STEP 6 — Tests ════════
Task 9:  CREATE app/features/backtesting/tests/test_feature_aware_backtest.py
  - Pure unit tests: per-fold X_train/X_future shape + column order; gap>0 fold;
    feature-aware model with exogenous=None -> loud ValueError.
Task 10: MODIFY app/features/backtesting/tests/test_service.py
  - Repurpose test_feature_aware_model_fails_loud_in_backtest (DECISIONS LOCKED #8).
Task 11: MODIFY app/features/backtesting/tests/test_service_integration.py
  - DB-backed regression backtest vs naive/seasonal baselines in one response.
Task 12: MODIFY app/features/backtesting/tests/test_routes_integration.py
  - POST /backtesting/run with a regression model config -> 200 + per-fold metrics.
Task 13: MODIFY app/features/backtesting/tests/test_schemas.py
  - ModelBacktestResult new fields: defaults + explicit values.
Task 14: MODIFY app/features/jobs/tests/test_service.py
  - backtest job with model_type="regression" -> success + shaped result.

# ════════ STEP 7 — Docs ════════
Task 15: MODIFY examples/models/feature_frame_contract.md, docs/PHASE/5-BACKTESTING.md,
         README.md (backtest model list), PRPs/INITIAL/INITIAL-MLZOO-index.md (B.2 row).
```

### Per-task pseudocode (critical details only)

```python
# ── Task 1 — build_future_feature_rows (the leakage-critical builder) ──
def build_future_feature_rows(*, test_dates, history_tail, gap, test_prices,
                              baseline_price, test_promo_dates, test_holiday_dates,
                              launch_date):
    horizon = len(test_dates)
    columns = canonical_feature_columns()
    # lags: build for gap+horizon days, drop the gap lead-in. NaN where source > T.
    lag_cols = build_long_lag_columns(history_tail, gap + horizon)   # {"lag_k": [...]}
    lag_cols = {k: v[gap:] for k, v in lag_cols.items()}
    cal_cols = build_calendar_columns(test_dates)                    # SAFE — pure
    rows: list[list[float]] = []
    for j, day in enumerate(test_dates):
        row: list[float] = []
        for col in columns:
            safety = feature_safety(col)              # raises KeyError on unknown -> loud
            if col.startswith("lag_"):                # CONDITIONALLY_SAFE
                row.append(lag_cols[col][j])
            elif col in cal_cols:                     # SAFE
                row.append(cal_cols[col][j])
            elif col == "price_factor":               # UNSAFE_UNLESS_SUPPLIED -> observed
                row.append(test_prices[j] / baseline_price)
            elif col == "promo_active":               # UNSAFE_UNLESS_SUPPLIED -> observed
                row.append(1.0 if day in test_promo_dates else 0.0)
            elif col == "is_holiday":                 # SAFE — calendar timeless attribute
                row.append(1.0 if day in test_holiday_dates else 0.0)
            elif col == "days_since_launch":          # SAFE — pure fn of date
                row.append(float((day - launch_date).days) if launch_date else math.nan)
            else:
                raise ValueError(f"build_future_feature_rows: unsourced column {col!r}")
        rows.append(row)
    return rows

# ── Task 7 — _run_model_backtest branch + _run_feature_aware_fold (pure, sync) ──
# _run_model_backtest gains NO new parameters. `gap` is read from the splitter it already
# receives (splitter.config.gap — SplitConfig is reachable as TimeSeriesSplitter.config).
# The full historical matrix is a LOCAL built once before the fold loop — there is no
# self._historical_matrix and no self.config on BacktestingService (__init__ sets only
# self.settings + self.metrics_calculator). _run_feature_aware_fold takes everything it
# needs as explicit arguments — no phantom instance state.

def _run_model_backtest(self, series_data, splitter, model_config, store_fold_details):
    probe = model_factory(model_config, random_state=self.settings.forecast_random_seed)
    feature_aware = probe.requires_features            # capability flag, never a string
    historical_matrix: np.ndarray | None = None
    if feature_aware:
        if series_data.exogenous is None:
            raise ValueError("feature-aware backtest requires a loaded ExogenousFrame")
        exo = series_data.exogenous
        historical_matrix = np.array(build_historical_feature_rows(
            dates=series_data.dates, quantities=series_data.values.tolist(),
            prices=exo.prices, baseline_price=exo.baseline_price,
            promo_dates=exo.promo_dates, holiday_dates=exo.holiday_dates,
            launch_date=exo.launch_date), dtype=np.float64)
    for split in splitter.split(series_data.dates, series_data.values):
        if feature_aware:
            predictions = self._run_feature_aware_fold(
                series_data, split, model_config, historical_matrix, splitter.config.gap)
        else:
            ...  # existing target-only path — UNCHANGED
        ...  # metrics / FoldResult assembly is shared, unchanged
    # set feature_aware=feature_aware and exogenous_policy on the returned ModelBacktestResult.

def _run_feature_aware_fold(self, series_data, split, model_config,
                            historical_matrix, gap):
    exo = series_data.exogenous                        # caller already guaranteed non-None
    # X_train — slice the full historical matrix (built once, leakage-safe by position)
    X_train = historical_matrix[split.train_indices]
    y_train = series_data.values[split.train_indices]
    # X_future — rebuilt per fold; history_tail ends at T = train_end, excludes gap
    train_end_idx = int(split.train_indices[-1]) + 1
    history_tail = series_data.values[:train_end_idx][-HISTORY_TAIL_DAYS:].tolist()
    test_idx = split.test_indices
    X_future = np.array(build_future_feature_rows(
        test_dates=split.test_dates, history_tail=history_tail, gap=gap,
        test_prices=[exo.prices[i] for i in test_idx], baseline_price=exo.baseline_price,
        test_promo_dates={series_data.dates[i] for i in test_idx if series_data.dates[i] in exo.promo_dates},
        test_holiday_dates={d for d in split.test_dates if d in exo.holiday_dates},
        launch_date=exo.launch_date), dtype=np.float64)
    model = model_factory(model_config, random_state=self.settings.forecast_random_seed)
    model.fit(y_train, X_train)
    return model.predict(len(test_idx), X_future)

# ── Task 8 — _execute_backtest allow-list ──
#   elif model_type == "regression":  model_config = RegressionModelConfig()
#   elif model_type == "lightgbm":    model_config = LightGBMModelConfig()
#   else: raise ValueError(f"Unsupported model_type: {model_type}")   # e.g. "arima"
```

### Integration Points

```yaml
BACKTESTING SERVICE:
  - run_backtest stays the only async entry; _run_model_backtest stays sync.
  - the full historical matrix is built once per _run_model_backtest call (feature-aware
    path) as a LOCAL variable, sliced per fold — never per-fold rebuilt for X_train, and
    never stored on the service instance.

JOBS:
  - _execute_backtest gains regression + lightgbm; _shape_backtest_result is NOT touched.
  - a backtest job for a disabled lightgbm fails loud via model_factory — expected.

SHARED CONTRACT:
  - rows.py joins contract.py under app/shared/feature_frames; __init__.py re-exports both.
  - forecasting + backtesting both consume one definition — no column-order drift possible.

NO CHANGE:
  - splitter.py, scenarios/**, frontend/**, alembic/**, registry/** — untouched.
```

## Phased Execution Plan

This is one coherent architectural change and **fits one reviewable PR** (~1 branch,
`feat/backtesting-feature-aware-folds`, off `dev`, tracked by **GitHub issue #244** —
every commit references `(#244)`). If the reviewer
prefers a smaller diff, split along the natural seam — Phase 1 is independently mergeable
because it is pure and behaviour-preserving:

- **Phase 1 — Shared builders + leakage spec (Tasks 1–5).** Promote
  `build_historical_feature_rows`, add `build_future_feature_rows`, wire the delegating shim,
  add the shared leakage tests. Zero behaviour change — every existing test stays green. A
  self-contained PR that lands the contract without touching backtesting.
- **Phase 2 — Backtesting + jobs wiring (Tasks 6–15).** Consume the builders: schema fields,
  async exogenous load, the fold-loop branch, jobs allow-list, integration tests, docs.

Recommended: ship as **one PR** unless the diff is judged too large at review time; the
phase boundary is the fallback, not the default.

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . && uv run ruff format --check .
```

### Level 2: Type Checks

```bash
uv run mypy app/ && uv run pyright app/
# Watch: rows.py must type cleanly with no app/features import; the new optional
# SeriesData.exogenous and the additive ModelBacktestResult fields must not break callers.
```

### Level 3: Unit Tests

```bash
uv run pytest -v -m "not integration" \
  app/shared/feature_frames/tests/ \
  app/features/backtesting/tests/test_service.py \
  app/features/backtesting/tests/test_feature_aware_backtest.py \
  app/features/backtesting/tests/test_schemas.py \
  app/features/forecasting/tests/test_regression_features_leakage.py \
  app/features/jobs/tests/test_service.py
# test_regression_features_leakage.py MUST pass with ZERO edits (the shim preserves it).
uv run pytest -v -m "not integration"          # whole fast suite — all green
```

### Level 4: Integration Tests

```bash
docker compose up -d
uv run pytest -v -m integration \
  app/features/backtesting/tests/test_service_integration.py \
  app/features/backtesting/tests/test_routes_integration.py
# A regression backtest must return per-fold metrics + a baseline comparison;
# the response carries exogenous_policy="observed" on the main-model result.
```

### Level 5: Manual Validation (dogfood — REQUIRED)

```bash
# 1. A regression backtest runs end-to-end (needs seeded data).
curl -sX POST localhost:8123/backtesting/run -H 'Content-Type: application/json' \
  -d '{"store_id":1,"product_id":1,"start_date":"2024-01-01","end_date":"2024-12-01",
       "config":{"model_config_main":{"model_type":"regression"},
                 "split_config":{"n_splits":3,"min_train_size":60,"horizon":14}}}'
#   -> 200; main_model_results.feature_aware == true; exogenous_policy == "observed";
#      baseline_results has naive + seasonal_naive; leakage_check_passed == true.

# 2. min_train_size guard fires loud.
#   ... same call with "min_train_size":20  -> 400 RFC-7807, "at least 30".

# 3. A backtest job with model_type=regression completes success.
curl -sX POST localhost:8123/jobs -H 'Content-Type: application/json' \
  -d '{"job_type":"backtest","params":{"model_type":"regression","store_id":1,
       "product_id":1,"start_date":"2024-01-01","end_date":"2024-12-01","n_splits":3}}'
#   -> poll GET /jobs/{id} -> status "success", result has per-fold metrics.

# 4. Baselines unaffected — a naive backtest still works exactly as before.
```

## Final Validation Checklist

- [ ] `ruff` + `mypy --strict` + `pyright --strict` clean.
- [ ] Whole fast unit suite green; `test_regression_features_leakage.py` unedited & green.
- [ ] New shared leakage spec proves `X_future` lag cells are `NaN`-where-future (incl. gap>0).
- [ ] Integration: a `regression` backtest returns per-fold metrics + baseline comparison.
- [ ] `POST /backtesting/run` with `regression` → `200`; with `min_train_size<30` → `400`.
- [ ] A `backtest` job with `model_type="regression"` → `success`.
- [ ] `_shape_backtest_result` output keys byte-identical to pre-PRP (frontend contract).
- [ ] Every baseline backtest test green with zero edits.
- [ ] The interim loud-fail test is repurposed (not deleted); supersession noted.
- [ ] No `frontend/`, `scenarios/`, `alembic/` change; no new migration.
- [ ] `git diff --stat` shows no whole-file CRLF/LF noise.

## Anti-Patterns to Avoid

- ❌ Slicing the historical matrix for `X_future` — that leaks adjacent test-day targets.
- ❌ Filling an unknowable future column with `0.0`/`NaN` silently — raise `ValueError`.
- ❌ Branching the fold loop on a `model_type` string — branch on `requires_features`.
- ❌ Importing `forecasting`/`scenarios` from `backtesting` — promote to `app/shared/`.
- ❌ Doing DB I/O inside `_run_model_backtest` — keep it sync; load async up front.
- ❌ Re-deriving `build_long_lag_columns` / `canonical_feature_columns()` — reuse the contract.
- ❌ Weakening or deleting `test_feature_aware_model_fails_loud_in_backtest` — repurpose it.
- ❌ Editing `_shape_backtest_result` keys or any `frontend/` file — out of scope.
- ❌ Adding XGBoost/Prophet, hyperparameter search, or a migration — all out of scope.

## Open Questions

1. **`exogenous_policy` v1 = `observed` only.** This PRP ships exactly one policy (recorded
   `price`/`promo` for the test window — exogenous foresight, target-leakage-free). A stricter
   `origin_carry_forward` policy (carry the last observed price/promo state from `T`, zero
   foresight) and an `assumptions` policy (planner-supplied, mirroring the scenarios slice)
   are deliberately deferred. **Resolve at PRP review:** is one policy acceptable for v1, or
   should `origin_carry_forward` ship alongside as the conservative default? The `Literal`
   field is the seam either way.
2. **Feature-aware baseline comparison.** v1 compares a feature-aware main model only against
   the *target-only* naive/seasonal baselines. Whether `regression` should also auto-run as a
   baseline for a `lightgbm` main model (advanced-vs-advanced) is left to MLZOO-D — flag if
   the reviewer wants it sooner.
3. **Per-series caching of the historical matrix.** Built once per `run_backtest` call; not
   cached across calls. Fine for single-series backtests; revisit only if a portfolio/batch
   backtester (a separate optional feature) ever lands.

## Confidence Score

**9/10** for one-pass implementation. The contract (MLZOO-A), both feature-aware models
(PRP-27, PRP-30), the splitter, and the leakage-test patterns all already exist and are
stable. The only genuine design judgement — the `X_future` exogenous policy — is resolved
and locked (DECISIONS LOCKED #4) with Open Question #1 as the explicit review hook. The work
is additive, single-slice-plus-shared, and needs no migration.
