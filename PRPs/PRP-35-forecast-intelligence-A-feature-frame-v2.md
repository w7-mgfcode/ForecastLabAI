name: "PRP-35 — Forecast Intelligence A: Feature Frame V2"
description: |
  Expand `app/shared/feature_frames/` from V1 (14 columns) to V2 — a richer,
  versioned, leakage-safe feature contract for retail demand forecasting.
  Preserve V1 byte-for-byte so existing model bundles, registry rows, and the
  load-bearing leakage spec stay green. Slice A of the Forecast Intelligence
  roadmap (`PRPs/INITIAL/INITIAL-forecast-intelligence-index.md`). Slice B
  (model zoo + backtesting comparison) and Slice C (interactive UI) are
  explicitly **out of scope** here.

## Purpose
A one-pass implementation contract for an AI agent (or human) who has access
to the codebase but no prior session context. The goal is to land V2 as an
additive surface — V1 callers never change, V2 callers opt in by request.

## Core Principles
1. **V1 is frozen.** Every V1 function, constant, and exported symbol keeps
   its current signature, return type, and behaviour. The load-bearing
   leakage spec (`app/shared/feature_frames/tests/test_leakage.py`) MUST stay
   green without modification.
2. **Leakage safety is the central design constraint.** Every V2 column
   carries an explicit `FeatureSafety` class; the future-frame builder
   structurally cannot read an observed target at a horizon day.
3. **Version metadata is on the bundle, not on `ModelConfig`.** Adding a
   field to `ModelConfigBase` would change every existing `config_hash()`
   value (`config_hash()` hashes the full `model_dump_json()`); we instead
   put `feature_frame_version` on `TrainRequest` + bundle `metadata`. V1
   registry rows / dedup keys stay stable.
4. **Pure builders, DB-side loaders.** `app/shared/feature_frames/` stays
   leaf-level (no `app.features.*` import). Async sidecar loaders live in
   `app/features/forecasting/v2_loaders.py`.
5. **NaN-where-unknown.** Every V2 column whose source data lies in the
   future (rolling, trend, stockout windows, replenishment count, returns
   count, exogenous signal) emits `NaN` at that horizon row. `HistGradient­
   BoostingRegressor` tolerates `NaN` natively (verified, see "Known
   Gotchas").
6. **No target rewriting.** Stockout is exposed as features only; the target
   `quantity` is never adjusted for stockouts in V2 (that needs a separate
   PRP).

---

## Goal

Deliver a working `feature_frame_version = 2` end-to-end:

- A train request can opt into V2 via `TrainRequest.feature_frame_version=2`
  and optional `feature_groups=[…]`.
- `_build_regression_features_v2` produces an `[n_observations × N]` feature
  matrix (`N` ≥ 14 + V2 additions, ≤ ~30 depending on enabled groups).
- The trained bundle persists `feature_frame_version`, `feature_columns`,
  `feature_groups`, and `feature_safety_classes` in `metadata`.
- Scenario `model_exogenous` and backtesting fold construction read those
  metadata fields and dispatch to V1 or V2 builders accordingly.
- V1 bundles trained before this PRP still load, predict, scenario-simulate,
  and backtest unchanged.
- Every V2 column has a unit test, and the V2 leakage spec parallels the V1
  load-bearing spec.

## Why

The current 14-column feature frame can learn weekly seasonality (`lag_7`),
calendar shape, holidays, price, and promotion. It cannot learn:

- yearly seasonality (`lag_364` preserves DOW; `lag_365` does not — verified)
- recent demand level (rolling means)
- trend (rolling-vs-prior-window ratios)
- stockout-aware demand (lost-sales proxies)
- richer lifecycle (`is_new_product`, `is_mature_product`, `is_discontinued`)
- replenishment cadence (Phase-2 `replenishment_event` data is already in
  the DB and unused by the regression frame today)
- returns intensity (Phase-2 `sales_returns` rows, also unused)
- exogenous weather/macro signals (Phase-2 `exogenous_signal` rows, unused)
- richer promotion shape (`promo_kind_markdown_active`, `promo_kind_bundle_
  active`, `promo_discount_pct`)

The local DB already holds all of these (see HANDOFF.md — 31,420
`replenishment_event` rows, 9,647 `exogenous_signal` rows, 8,585
`sales_returns`, 50/50 products with `lifecycle_stage` + `launch_date`).
V2 makes them available to the feature-aware regressor without changing
the model class, the dashboard, or the registry/champion logic.

## What

### User-visible behaviour

- `POST /forecasting/train` accepts an optional `feature_frame_version: int
  = 1` and `feature_groups: list[str] | None = None` on the request body.
  When omitted, V1 behaviour is preserved exactly.
- `POST /backtesting/run` and `POST /scenarios/simulate` work with both V1
  and V2 bundles transparently.
- `GET /forecasting/runs/{run_id}/feature-metadata` returns the bundle's
  `feature_columns`, `feature_groups`, `feature_safety_classes`,
  `feature_frame_version`. (UI in Slice C will surface this; we just make
  it accessible.)

### Technical requirements

- Pydantic v2 strict mode on every new request schema (`ConfigDict(strict=
  True)` + `Field(strict=False, ...)` on `date`/`datetime`/`UUID`/`Decimal`
  fields — see `docs/_base/SECURITY.md` § "Pydantic v2 strict mode on
  FastAPI request bodies").
- All new SQL queries use SQLAlchemy 2.0 parameter binding and time-safe
  `<= cutoff_date` filters at the SQL boundary.
- All five validation gates pass: `ruff check` + `ruff format --check` +
  `mypy --strict` + `pyright --strict` + `pytest`.
- `app/shared/feature_frames/**` remains leaf-level (the AST-walk invariant
  in `tests/test_contract.py` continues to assert no `app.features.*`
  import).

### Success Criteria

- [ ] V1 leakage spec (`app/shared/feature_frames/tests/test_leakage.py`)
  passes unchanged. **Not weakened.**
- [ ] New V2 leakage spec (`app/shared/feature_frames/tests/test_leakage_v2.py`)
  passes; every V2 column has at least one assertion proving it cannot read
  a future target.
- [ ] A V1 bundle saved before this PRP loads, predicts, scenario-simulates,
  and backtests with no errors — V1/V2 dispatch is transparent.
- [ ] A V2 training request produces a bundle whose `metadata` carries
  `feature_frame_version=2`, `feature_columns=[…]`,
  `feature_groups={group_name: [columns]}`, and
  `feature_safety_classes={column: "safe"|"conditionally_safe"|"unsafe_
  unless_supplied"}`.
- [ ] V2 future-frame assembly emits `NaN` for every cell whose source day
  > T (long lag, rolling, trend, stockout-window, replenishment-window,
  returns-window).
- [ ] All four `lag_*` and `same_dow_mean_*` cells at horizon day `j` are
  `NaN` exactly when `(j-1) - k >= 0` (the V1 invariant generalised).
- [ ] `lag_364` (not `lag_365`) is the canonical yearly lag (verified DOW
  preservation).
- [ ] No cross-slice import — `app/shared/feature_frames/**` imports
  nothing from `app.features.**` (AST-walk invariant test passes).
- [ ] All five validation gates green: `uv run ruff check . && uv run ruff
  format --check . && uv run mypy app/ && uv run pyright app/ && uv run
  pytest -v -m "not integration"`.

---

## All Needed Context

### Documentation & References

```yaml
- file: app/shared/feature_frames/contract.py
  why: V1 single source of truth — pinned constants, canonical columns, FeatureSafety taxonomy, pure long-lag + calendar builders. The "shape of V2" must mirror this file exactly.

- file: app/shared/feature_frames/rows.py
  why: V1 row assemblers (historical + future). V2 row assemblers mirror these two functions (build_historical_feature_rows_v2 / build_future_feature_rows_v2).

- file: app/shared/feature_frames/__init__.py
  why: V1 public surface. V2 names are added to __all__ alongside (not replacing) V1.

- file: app/shared/feature_frames/tests/test_contract.py
  why: V1 contract tests AND the AST-walk invariant that pins "shared/** never imports features/**". V2 tests follow the same style; the AST-walk must still pass on V2 modules.

- file: app/shared/feature_frames/tests/test_leakage.py
  why: V1 load-bearing leakage spec. MUST stay byte-stable. V2's parallel spec at tests/test_leakage_v2.py uses the same idioms (sequential targets so leakage is mathematically detectable; disjoint future-target set; pytest.mark.parametrize over gap values).

- file: app/features/forecasting/service.py
  why: Where `_build_regression_features` lives (line 515). V2 adds a sibling `_build_regression_features_v2` and a router method `_build_regression_features` (no version) that dispatches on `request.feature_frame_version`. Bundle metadata is enriched at line 280-287.

- file: app/features/forecasting/persistence.py
  why: ModelBundle and save/load. No schema change — `metadata: dict[str, object]` already accepts arbitrary keys. V2 metadata fields ride in there. Load-side back-compat: `bundle.metadata.get("feature_frame_version", 1)` defaults V1.

- file: app/features/forecasting/schemas.py
  why: TrainRequest at line 284 — strict=True with date_type Field(strict=False) for FastAPI JSON-body compatibility (docs/_base/SECURITY.md). New `feature_frame_version: int = 1` and `feature_groups: list[str] | None = None` fields added here.

- file: app/features/scenarios/feature_frame.py
  why: build_future_frame (line 232) already reads `feature_columns` from the bundle and threads it through. V2 work here: the assemble_future_frame function (line 181) needs a V2 branch that consumes V2 sidecars (lifecycle, knowable-only) for assumption-driven V2 columns. Where a V2 column has no future input (e.g. weather forecast), it stays NaN.

- file: app/features/backtesting/service.py
  why: Calls build_historical_feature_rows (line 493) and build_future_feature_rows (line 553) WITHOUT a feature_columns argument — so today's path hard-uses canonical_feature_columns() (V1). V2 work: pass the bundle's recorded version + columns through, dispatch to V1 or V2 builders.

- file: app/features/featuresets/service.py
  why: PATTERN ONLY (no import). Existing rolling / trend / stockout / lifecycle / promotion / replenishment compute idioms — V2 builders mirror the safety idioms (groupby(entity).shift(1).rolling(window) for time-safe rolling) without importing this slice.

- file: app/features/data_platform/models.py
  why: Authoritative ORM for `inventory_snapshot_daily` (lines 345-383), `replenishment_event` (471-514), `sales_returns` (439-468), `exogenous_signal` (386-436), `promotion` (274-342), `product` (68-126). V2 loaders read these tables directly.

- file: app/features/forecasting/tests/test_regression_features_leakage.py
  why: V1 forecasting-specific leakage spec — pattern for V2 to mirror at app/features/forecasting/tests/test_regression_features_v2_leakage.py.

- file: app/features/scenarios/tests/test_future_frame_leakage.py
  why: V1 scenarios leakage spec — pattern for V2 future-frame leakage tests in scenarios slice.

- url: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html
  section: "Missing values support"
  critical: HGBR tolerates NaN natively in both fit() and predict(). Verified in this codebase at `uv run python -c "...HistGradientBoostingRegressor; m.fit(X_with_nan, y)..."` (PRP § Known Gotchas).

- url: https://pandas.pydata.org/docs/user_guide/timeseries.html
  section: "Rolling windows"
  critical: Default `min_periods` equals the window size. Verified: `pd.Series([1..8]).rolling(3).mean()` returns [nan, nan, 2.0, 3.0, ...]. The leakage-safe idiom is `s.shift(1).rolling(window).mean()` — V2 rolling features use this composition.

- url: https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html
  section: "Cyclical / lagged features"
  critical: The lag + calendar + cyclical pattern this PRP extends.

- docfile: PRPs/ai_docs/exogenous-regressor-forecasting.md
  why: Pre-existing ai_doc on past vs future covariates terminology — useful framing for the V2 OBSERVED_ONLY note.

- file: docs/DATA-SEEDER.md
  why: Documents what the seeder produces for inventory, replenishment, returns, exogenous signals, markdowns, bundles — i.e. what V2 sidecar loaders will see.

- file: docs/_base/SECURITY.md
  section: "Pydantic v2 strict mode on FastAPI request bodies"
  critical: Every new request-body field whose Python type lacks a native JSON representation (date, datetime, UUID, Decimal) MUST carry `Field(strict=False, ...)` to avoid breaking JSON-string inputs. `feature_frame_version: int` and `feature_groups: list[str] | None` are JSON-native so they need no override.

- file: docs/_base/RULES.md
  why: NEVER weaken the leakage tests; NEVER skip mypy/pyright strict; NEVER edit a merged Alembic migration; NEVER widen the agent's mutation surface without updating agent_require_approval. (None of those are violated by this PRP — it adds no migrations, no agent tools, no mutating endpoints.)

- file: PRPs/PRP-29-feature-aware-forecasting-foundation.md
  why: The V1 PRP. Read for tone, structure, and to see how the "feature contract is the source of truth" principle was originally landed. V2 inherits all of its safety idioms.

- file: PRPs/PRP-MLZOO-B.2-feature-aware-backtesting.md
  why: The PRP that promoted the row assemblers from forecasting to app/shared. Documents how the historical / future asymmetry was solved.
```

### Current Codebase tree (relevant slice)

```
app/
├── shared/
│   └── feature_frames/
│       ├── __init__.py            # V1 public surface (and where V2 names will be added)
│       ├── contract.py            # V1 — pinned constants, canonical columns, taxonomy, pure builders
│       ├── rows.py                # V1 — historical and future row assemblers
│       └── tests/
│           ├── __init__.py
│           ├── test_contract.py   # V1 contract tests + AST-walk leaf-level invariant
│           └── test_leakage.py    # V1 load-bearing leakage spec — DO NOT WEAKEN
├── features/
│   ├── forecasting/
│   │   ├── service.py             # _build_regression_features (V1) at line 515
│   │   ├── persistence.py         # ModelBundle.metadata is dict[str, object] — V2 metadata rides here
│   │   ├── schemas.py             # TrainRequest at line 284; ModelConfig union at 268
│   │   ├── models.py              # BaseForecaster.requires_features at line 109
│   │   └── tests/test_regression_features_leakage.py  # V1 forecasting leakage spec — DO NOT WEAKEN
│   ├── backtesting/
│   │   └── service.py             # calls V1 row builders at lines 493, 553 — V2 dispatch lands here
│   ├── scenarios/
│   │   ├── feature_frame.py       # assemble_future_frame at line 181, build_future_frame at line 232
│   │   └── tests/
│   │       ├── test_future_frame_leakage.py    # V1 scenarios leakage spec — DO NOT WEAKEN
│   │       └── test_leakage.py
│   ├── featuresets/
│   │   ├── service.py             # PATTERN ONLY (rolling/trend/stockout/lifecycle compute idioms)
│   │   └── tests/test_leakage.py  # other load-bearing leakage spec — DO NOT WEAKEN
│   └── data_platform/
│       └── models.py              # sidecar ORM: InventorySnapshotDaily, ReplenishmentEvent, SalesReturn, ExogenousSignal, Promotion, Product
└── core/
    └── config.py                  # Settings — no new keys needed
```

### Desired Codebase tree (new files)

```
app/
├── shared/
│   └── feature_frames/
│       ├── __init__.py            # MODIFIED — adds V2 exports next to V1
│       ├── contract.py            # UNCHANGED
│       ├── contract_v2.py         # NEW — V2 column manifest, group taxonomy, pure pandas-free builders
│       ├── rows.py                # UNCHANGED
│       ├── rows_v2.py             # NEW — V2 historical + future row assemblers
│       ├── sidecar.py             # NEW — V2HistoricalSidecar / V2FutureSidecar dataclasses (pure data carriers)
│       └── tests/
│           ├── test_contract.py   # UNCHANGED (still asserts AST-walk against new files)
│           ├── test_leakage.py    # UNCHANGED — DO NOT WEAKEN
│           ├── test_contract_v2.py    # NEW — V2 contract + taxonomy + group manifest tests
│           └── test_leakage_v2.py     # NEW — LOAD-BEARING V2 leakage spec (mirror of test_leakage.py)
├── features/
│   ├── forecasting/
│   │   ├── service.py             # MODIFIED — V2 dispatch + _build_regression_features_v2 + V2 metadata persistence
│   │   ├── schemas.py             # MODIFIED — TrainRequest gains feature_frame_version + feature_groups; FeatureMetadataResponse gains V2 fields (additive)
│   │   ├── v2_loaders.py          # NEW — async sidecar loaders (inventory, replenishment, returns, exogenous, promotion, lifecycle); leaf-level wrt other slices
│   │   └── tests/
│   │       ├── test_regression_features_leakage.py    # UNCHANGED — DO NOT WEAKEN
│   │       ├── test_regression_features_v2_leakage.py # NEW — V2 leakage spec at the forecasting-slice layer
│   │       ├── test_v2_loaders.py # NEW — DB integration tests for the loaders
│   │       └── test_service_v2.py # NEW — end-to-end V2 train test (integration; uses docker-compose Postgres)
│   ├── backtesting/
│   │   ├── service.py             # MODIFIED — read feature_frame_version from bundle; dispatch row builders
│   │   └── tests/
│   │       └── test_feature_aware_backtest_v2.py     # NEW — V2 fold leakage test
│   └── scenarios/
│       ├── feature_frame.py       # MODIFIED — assemble_future_frame dispatches on feature_frame_version from bundle/metadata
│       └── tests/
│           └── test_future_frame_v2_leakage.py       # NEW — V2 scenarios leakage spec
└── examples/
    └── forecasting/
        └── feature_frame_v2_preview.py  # NEW — read-only V1 vs V2 column dump for a (store, product) pair
```

### Known Gotchas of our codebase & Library Quirks

```python
# ─────────────────────────────────────────────────────────────────────────
# CRITICAL: V1 must keep working. Three concrete risks to avoid:
# ─────────────────────────────────────────────────────────────────────────

# 1. config_hash() drift
#    `app/features/forecasting/schemas.py:43-50` hashes the entire
#    `model_dump_json()`. Adding `feature_frame_version` to `ModelConfigBase`
#    would silently change *every* V1 config's hash, breaking the registry
#    dedup key and orphaning every "champion"/"production" alias.
#    POLICY: put `feature_frame_version` on `TrainRequest`, NOT on
#    `ModelConfigBase`. Bundle metadata records the resolved version.

# 2. Backtesting hard-codes canonical_feature_columns() at the builder call
#    site (`app/features/backtesting/service.py:493, 553`). The V1 builders
#    today internally call canonical_feature_columns(); they have no
#    `feature_columns` or `feature_frame_version` parameter and are NOT to
#    be modified by this PRP (V1 is frozen — Core Principle #1). For V2:
#    - DO NOT add `feature_frame_version`, `feature_columns`, or any other
#      parameter to V1 `build_historical_feature_rows` /
#      `build_future_feature_rows` — V1 signatures, return types, and
#      bodies remain byte-stable.
#    - DO ship NEW sibling functions `build_historical_feature_rows_v2` and
#      `build_future_feature_rows_v2` in `app/shared/feature_frames/rows_v2.py`
#      (Task 3). V2 callers invoke the V2 functions; V1 callers continue to
#      invoke the V1 functions unchanged.
#    - Dispatch (V1 vs V2) happens EXCLUSIVELY at the service layer —
#      `forecasting/service.py` train_model branches on
#      `request.feature_frame_version`; `backtesting/service.py` and
#      `scenarios/feature_frame.py` read `feature_frame_version` from the
#      bundle metadata. `app/shared/feature_frames/` itself contains no
#      runtime dispatch logic.
#    - When `feature_frame_version` is absent from a bundle's metadata,
#      service-layer code defaults it to 1 (`bundle.metadata.get(
#      "feature_frame_version", 1)`) — legacy bundles route to V1 builders
#      unchanged.

# 3. The load-bearing leakage tests use SEQUENTIAL targets (1.0, 2.0, ...,
#    60.0) so any leakage is mathematically detectable. V2 leakage tests
#    use the same trick PLUS a DISJOINT future-target set
#    ({9000.0..9999.0}) for the future-frame builder so leakage is
#    detectable by set membership. Mirror exactly.

# ─────────────────────────────────────────────────────────────────────────
# Library verifications (run before locking PRP claims, mandated by
# the prp-create skill's "Third-party API runtime verification" rule):
# ─────────────────────────────────────────────────────────────────────────

# VERIFIED: HistGradientBoostingRegressor tolerates NaN in fit() and predict()
#   uv run python -c "
#     from sklearn.ensemble import HistGradientBoostingRegressor
#     import numpy as np
#     X = np.array([[1.0, np.nan], [2.0, 0.5], [3.0, 1.5], [4.0, np.nan], [5.0, 2.5]])
#     y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
#     m = HistGradientBoostingRegressor(max_iter=5); m.fit(X, y)
#     print(m.predict(np.array([[6.0, np.nan]]))[0])
#   "
#   Output: 3.0 (no exception). sklearn 1.8.0.

# VERIFIED: pandas .rolling(window).mean() default min_periods == window
#   uv run python -c "
#     import pandas as pd
#     s = pd.Series([1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0])
#     print(list(s.rolling(3).mean()))
#   "
#   Output: [nan, nan, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]. pandas 3.0.3.
#   Use this default — the leading NaNs are the leakage-safe answer.
#   V2 rolling uses `s.shift(1).rolling(window).mean()` so row i reads
#   strictly earlier observations only.

# VERIFIED: lag_364 preserves day-of-week; lag_365 does NOT
#   uv run python -c "
#     from datetime import date, timedelta
#     d = date(2026, 6, 15)  # Monday
#     print((d - timedelta(days=364)).weekday(),  # 0 = Monday — PRESERVED
#           (d - timedelta(days=365)).weekday())  # 6 = Sunday — shifted
#   "
#   POLICY: V2 uses `lag_364` for "same weekday last year". The INITIAL's
#   open design decision is RESOLVED in favour of lag_364.

# VERIFIED: joblib round-trips arbitrary metadata dicts; legacy-bundle
# back-compat via dict.get(key, default)
#   uv run python -c "
#     import joblib, tempfile, os
#     sample = {'feature_columns': ['lag_1','lag_7'], 'feature_frame_version': 2}
#     with tempfile.NamedTemporaryFile(suffix='.joblib', delete=False) as f:
#       joblib.dump(sample, f.name); fname = f.name
#     loaded = joblib.load(fname); os.unlink(fname)
#     legacy = {'feature_columns': ['lag_1','lag_7']}
#     print(loaded == sample, legacy.get('feature_frame_version', 1))
#   "
#   Output: True 1. joblib 1.5.3.

# ─────────────────────────────────────────────────────────────────────────
# Repo-specific failure modes to avoid (anchored in memory + prior PRPs):
# ─────────────────────────────────────────────────────────────────────────

# - DO NOT cite `HistGradientBoostingRegressor.feature_importances_` — it
#   does not exist on HGBR; sklearn exposes it on `GradientBoostingRegressor`
#   only (memory `histgbr-no-feature-importances`, issue #258). V2 leaves
#   feature-importance extraction untouched in this PRP; Slice B owns model
#   work.

# - SimpleImputer in sklearn 1.2+ defaults to `keep_empty_features=False`,
#   silently dropping all-NaN columns and shortening downstream coef arrays
#   (memory `simpleimputer-drops-empty-columns`). V2 does NOT use
#   SimpleImputer at the row-builder layer — the matrix carries NaN
#   directly to HGBR. If a downstream consumer adds imputation later
#   (Slice B / a new ridge model), it MUST pass `keep_empty_features=True`.

# - Pydantic v2 strict mode + FastAPI: `ConfigDict(strict=True)` on a request
#   body causes FastAPI to reject ISO-string date inputs (a 422 storm).
#   `feature_frame_version: int` and `feature_groups: list[str] | None` are
#   JSON-native so they need no `Field(strict=False, ...)` override.

# - app/shared/** never imports app/features/** — the AST-walk invariant in
#   tests/test_contract.py catches violations. V2 sidecar dataclasses live
#   in app/shared/feature_frames/sidecar.py and stay leaf-level; the DB
#   loading lives in app/features/forecasting/v2_loaders.py.

# - Backtesting cross-slice rule: `backtesting -> forecasting` is forbidden;
#   `backtesting -> app/shared` is allowed. V2 dispatch in backtesting reads
#   feature_frame_version from the bundle.metadata (not from a forecasting
#   service call) and routes to app/shared/feature_frames/rows_v2.

# - Mixed line endings warning (memory `repo-line-endings-crlf`): on this
#   host some files are CRLF and Edit/Write emit LF. Check `git diff --stat`
#   before committing any modified file to avoid whole-file noise diffs.
```

---

## Implementation Blueprint

### Data models and structure

```python
# ─── app/shared/feature_frames/contract_v2.py ─────────────────────────────
from enum import Enum
from dataclasses import dataclass

# Version tag (also persisted to bundle metadata)
FEATURE_FRAME_VERSION_V1: int = 1
FEATURE_FRAME_VERSION_V2: int = 2

# Pinned V2 modelling constants — DECISIONS LOCKED in this PRP
EXOGENOUS_LAGS_V2: tuple[int, ...] = (1, 7, 14, 28, 56, 364)  # lag_364 (DOW-aligned)
ROLLING_WINDOWS_V2: tuple[int, ...] = (7, 28, 90)             # same-DOW-mean uses (4, 8)
TREND_WINDOWS_V2: tuple[int, ...] = (30, 90)
STOCKOUT_WINDOWS_V2: tuple[int, ...] = (7, 28)
REPLENISHMENT_WINDOWS_V2: tuple[int, ...] = (14, 28)
RETURNS_WINDOWS_V2: tuple[int, ...] = (7, 28)
INVENTORY_AVAILABILITY_WINDOW_V2: int = 28
# Observed-target tail length: max(EXOGENOUS_LAGS_V2 + ROLLING_WINDOWS_V2) + safety
HISTORY_TAIL_DAYS_V2: int = 400  # >= 364 + 28 buffer

# Feature groups (used to enable/disable + label in Slice C metadata)
class FeatureGroup(str, Enum):
    TARGET_HISTORY = "target_history"   # lag_1, lag_7, ..., lag_364, same_dow_mean_*
    ROLLING = "rolling"                  # rolling_mean_7/28/90, rolling_median_28, rolling_std_28
    TREND = "trend"                      # trend_30, trend_90, rolling_mean_7_vs_28, rolling_mean_28_vs_prev_28
    CALENDAR = "calendar"                # V1 calendar + week_of_year_sin/cos, day_of_month_sin/cos
    PRICE_PROMO = "price_promo"          # V1 price_factor/promo_active + promo_discount_pct, promo_kind_markdown_active, promo_kind_bundle_active
    INVENTORY = "inventory"              # is_stockout_lag1, stockout_days_7/28, inventory_available_ratio_28
    LIFECYCLE = "lifecycle"              # days_since_launch, is_new_product, is_mature_product, is_discontinued, days_until_discontinue
    REPLENISHMENT = "replenishment"      # days_since_last_replenishment, replenishment_count_14, replenishment_qty_28
    RETURNS = "returns"                  # returns_qty_7, returns_qty_28, returns_rate_28
    EXOGENOUS_WEATHER = "exogenous_weather"  # store-specific weather signals (NaN if unavailable in future)
    EXOGENOUS_MACRO = "exogenous_macro"      # global macro signals (NaN if unavailable in future)

# Default V2 groups when feature_groups is None — every group with a fully-
# determinate future projection. Phase 2 sidecars off by default to keep
# the MVP green on smaller seeded DBs.
DEFAULT_V2_GROUPS: tuple[FeatureGroup, ...] = (
    FeatureGroup.TARGET_HISTORY,
    FeatureGroup.ROLLING,
    FeatureGroup.TREND,
    FeatureGroup.CALENDAR,
    FeatureGroup.PRICE_PROMO,
    FeatureGroup.LIFECYCLE,
)

@dataclass(frozen=True)
class V2ColumnSpec:
    """One V2 feature column — name, group, safety class."""
    name: str
    group: FeatureGroup
    safety: FeatureSafety  # SAFE | CONDITIONALLY_SAFE | UNSAFE_UNLESS_SUPPLIED

def v2_column_manifest(
    groups: tuple[FeatureGroup, ...] = DEFAULT_V2_GROUPS,
) -> list[V2ColumnSpec]:
    """The ordered, canonical V2 column manifest for the given groups.
    Order: target_history → calendar → rolling → trend → price_promo →
           inventory → lifecycle → replenishment → returns → exogenous_*
    """
    ...

def canonical_feature_columns_v2(
    groups: tuple[FeatureGroup, ...] = DEFAULT_V2_GROUPS,
) -> list[str]:
    """Equivalent of canonical_feature_columns() for V2."""
    return [spec.name for spec in v2_column_manifest(groups)]


# ─── app/shared/feature_frames/sidecar.py ─────────────────────────────────
from datetime import date

@dataclass(frozen=True)
class V2HistoricalSidecar:
    """Pure data carrier for everything V2 historical builder needs beyond
    the V1 inputs.

    Alignment contract (ENFORCED — violation → ValueError in the builder):
    - Every per-day array (on_hand_qty, is_stockout_per_day, returns_qty_per_day,
      promo_kinds_per_day, promo_discount_pct_per_day) has length equal to
      `len(dates)` whenever its owning group is enabled.
    - Sets / mappings (promo_dates, holiday_dates, weather_per_day,
      macro_per_day) are queried by membership; absent keys for a given date
      → NaN at that cell, never zero-fill.
    - replenishment_event_dates / replenishment_event_qty are event-time
      (one entry per event), NOT per-day-aligned; length parity between
      these two tuples is the only alignment invariant.

    Group enablement vs. data presence:
    - If a FeatureGroup is NOT passed in the builder's `groups` argument,
      this sidecar's corresponding fields MAY be empty (the builder won't
      read them) and NO column for that group is emitted.
    - If a FeatureGroup IS in `groups` but a specific day has no source
      data inside the matching sidecar field (e.g. `on_hand_qty[i] is None`,
      no replenishment event before day i, missing weather entry for the
      date), the column cell at row i is NaN. HGBR consumes NaN directly.
    - If a FeatureGroup IS in `groups` and its sidecar field's per-day array
      length disagrees with `len(dates)`, the builder raises ValueError —
      that's a programmer/contract error, not a "missing data" case.
    """
    # V1 carryover
    promo_dates: set[date]
    holiday_dates: set[date]
    launch_date: date | None
    # Lifecycle
    discontinue_date: date | None
    # Inventory (per-day, aligned with dates)
    on_hand_qty: tuple[float | None, ...]
    is_stockout_per_day: tuple[bool, ...]
    # Replenishment (timestamps, NOT per-day)
    replenishment_event_dates: tuple[date, ...]
    replenishment_event_qty: tuple[int, ...]
    # Returns (per-day quantity, 0 when no return)
    returns_qty_per_day: tuple[int, ...]
    # Promotion (per-day kind set + discount pct)
    promo_kinds_per_day: tuple[frozenset[str], ...]   # {"pct_off","markdown","bogo","bundle"} subset per day
    promo_discount_pct_per_day: tuple[float, ...]     # 0.0 when no discount; else 0.0..1.0
    # Exogenous (date → signal_name → value)
    weather_per_day: dict[date, dict[str, float]]
    macro_per_day: dict[date, dict[str, float]]

@dataclass(frozen=True)
class V2FutureSidecar:
    """Inputs the future-frame builder accepts when re-forecasting.
    EVERY field is either knowable at origin T (calendar, launch date,
    discontinue_date), or *posited by the caller as an assumption*
    (price, promotion, holiday); for the truly-unknowable groups
    (weather, macro) the caller MAY supply observed-then-projected values
    or leave them None → the future column is NaN.
    """
    holiday_dates: set[date]            # calendar + scenario assumption
    launch_date: date | None
    discontinue_date: date | None
    # Future inputs — None means "not posited" → corresponding column = NaN
    price_factor_per_day: tuple[float | None, ...]
    promo_active_per_day: tuple[bool, ...]
    promo_kinds_per_day: tuple[frozenset[str], ...]
    promo_discount_pct_per_day: tuple[float, ...]
    # Phase 2 future inputs — typically None for V2 MVP
    inventory_on_hand_per_day: tuple[float | None, ...]
    weather_per_day: dict[date, dict[str, float]]
    macro_per_day: dict[date, dict[str, float]]
```

### List of tasks to be completed (dependency-ordered)

```yaml
Task 1 — CREATE app/shared/feature_frames/contract_v2.py:
  - DEFINE FEATURE_FRAME_VERSION_V1 = 1, FEATURE_FRAME_VERSION_V2 = 2
  - DEFINE pinned constants (EXOGENOUS_LAGS_V2, ROLLING_WINDOWS_V2, etc.)
  - DEFINE FeatureGroup enum with the 11 groups from the data model above
  - DEFINE V2ColumnSpec frozen dataclass
  - IMPLEMENT v2_column_manifest(groups) → list[V2ColumnSpec] (ordered: target_history → calendar → rolling → trend → price_promo → inventory → lifecycle → replenishment → returns → weather → macro)
  - IMPLEMENT canonical_feature_columns_v2(groups) → list[str]
  - IMPLEMENT v2_feature_groups_dict(columns) → dict[str, list[str]] (group_name → columns)
  - IMPLEMENT v2_feature_safety_classes(columns) → dict[str, str] (column → safety.value)
  - PURE: stdlib only (math, datetime, dataclasses, enum); never imports app.features.*
  - MIRROR the V1 docstring conventions (load-bearing leakage rule restated)
  - VERIFY: every column in DEFAULT_V2_GROUPS resolves through feature_safety_v2(column)

Task 2 — CREATE app/shared/feature_frames/sidecar.py:
  - DEFINE V2HistoricalSidecar frozen dataclass (per data-model section above)
  - DEFINE V2FutureSidecar frozen dataclass (per data-model section above)
  - PURE: stdlib only; never imports app.features.*
  - DOC: explain the alignment invariants (all per-day arrays align with `dates`; replenishment_event_* is event-time not day-time)

Task 3 — CREATE app/shared/feature_frames/rows_v2.py:
  - IMPLEMENT build_historical_feature_rows_v2(
        *, dates, quantities, prices, baseline_price, sidecar: V2HistoricalSidecar, groups: tuple[FeatureGroup, ...]
    ) -> list[list[float]]
  - IMPLEMENT build_future_feature_rows_v2(
        *, test_dates, history_tail, gap, baseline_price, sidecar: V2FutureSidecar, history_tail_dates: list[date], history_tail_stockouts: list[bool], history_tail_replenishment_dates: list[date], history_tail_returns_qty: list[int], groups
    ) -> list[list[float]]
  - REUSE V1 builders: build_long_lag_columns, build_calendar_columns
  - EXTEND lags: add lag_56, lag_364 by parameterising V1 build_long_lag_columns with EXOGENOUS_LAGS_V2
  - ADD same_dow_mean_4, same_dow_mean_8: helper that picks the 4 (or 8) same-weekday observations before each row
  - ADD rolling_mean_7/28/90, rolling_median_28, rolling_std_28: leakage-safe via "history_tail[-W..-1]" indexing (pure Python; no pandas needed — the tail is at most HISTORY_TAIL_DAYS_V2)
  - ADD trend_30, trend_90: linear-slope over the trailing W days (numpy.polyfit on the tail)
  - ADD rolling_mean_7_vs_28, rolling_mean_28_vs_prev_28: ratio columns (NaN-safe division)
  - ADD week_of_year_sin/cos, day_of_month_sin/cos: pure date functions
  - ADD promo_discount_pct, promo_kind_markdown_active, promo_kind_bundle_active: from sidecar.promo_kinds_per_day and promo_discount_pct_per_day
  - ADD is_stockout_lag1, stockout_days_7/28, inventory_available_ratio_28: stockout windows + on_hand / max(on_hand-history) ratio
  - ADD is_new_product, is_mature_product, is_discontinued, days_until_discontinue: derived from launch_date + discontinue_date thresholds (intro ≤ 30d, mature ≥ 180d)
  - ADD days_since_last_replenishment, replenishment_count_14, replenishment_qty_28: from sidecar.replenishment_event_dates
  - ADD returns_qty_7/28, returns_rate_28: from sidecar.returns_qty_per_day; rate = returns_qty / max(sales_qty, 1)
  - For future builder: NaN-where-future is enforced cell-by-cell — NEVER read history_tail beyond the supplied tail; NEVER fabricate a value when source day > T
  - GROUP-GATED COLUMN EMISSION: the column manifest is derived ENTIRELY from the `groups` parameter. If a FeatureGroup is NOT in `groups`, NO column from that group appears in the output matrix or in `feature_columns`. (i.e. disabled group = silent omission, not NaN-filled placeholder.)
  - PER-CELL NaN: when a group IS enabled but a specific day lacks source data (e.g. INVENTORY enabled but `sidecar.on_hand_qty[i] is None`, REPLENISHMENT enabled but no event has occurred before day i, EXOGENOUS_WEATHER enabled but `sidecar.weather_per_day` has no entry for that date), the corresponding cell is `NaN`. HGBR tolerates NaN; downstream consumers MUST NOT impute with zero.
  - LOUD failure (ValueError) — ONLY for programmer / contract errors:
      * `groups` is empty (would produce a zero-column matrix — that's a misuse, not "no features").
      * `groups` contains a name that does not match any `FeatureGroup` enum value (unsupported requested group).
      * A sidecar per-day array length does not match `len(dates)` (alignment contract violated).
      * A sidecar mapping references a date outside the `dates` range when the column's spec requires alignment.
      * Required scalar inputs are missing for an enabled group (e.g. INVENTORY enabled but `sidecar.on_hand_qty` field is entirely absent — distinct from "present but all None").
    NEVER raise ValueError merely because a specific day has no source data within an enabled group; that's the NaN case.
  - NEVER silent zero-fill any sidecar source — zero is a real demand-domain value (0 units returned, 0 stockout days, $0 discount) and would corrupt the feature signal. Use NaN for "unknown" and let the model see it.
  - PURE: stdlib + numpy (for polyfit only); never imports app.features.*

Task 4 — CREATE app/shared/feature_frames/tests/test_contract_v2.py:
  - MIRROR app/shared/feature_frames/tests/test_contract.py structure
  - TEST: pinned constants (EXOGENOUS_LAGS_V2, ROLLING_WINDOWS_V2, …)
  - TEST: every column in v2_column_manifest(DEFAULT_V2_GROUPS) is classifiable (no KeyError)
  - TEST: enabling a subset of groups produces a strict subset of columns
  - TEST: column order is stable and deterministic for the same groups input
  - TEST: V2 manifest INCLUDES every V1 column at the SAME relative position (V1-then-extensions order in the V1-group subset)
  - TEST: the AST-walk in test_contract.py STILL passes (extend it to walk contract_v2.py + rows_v2.py + sidecar.py)

Task 5 — CREATE app/shared/feature_frames/tests/test_leakage_v2.py — LOAD-BEARING:
  - MIRROR app/shared/feature_frames/tests/test_leakage.py exactly in style
  - USE sequential targets (1.0..N.0) so leakage is detectable by arithmetic
  - USE disjoint future-target set ({9000.0..9999.0}) — any future-target value appearing in a feature cell is a leak
  - TEST for every V2 column: the cell at horizon day j is NaN exactly when its source day > T
  - PARAMETRIZE over gap = 0, 3, 7 for the future builder
  - TEST: rolling_mean_7 at horizon day j=1 is computable (window T-6..T); at j=2 it is NaN (window touches T+1)
  - TEST: lag_364 at j=1 is history_tail[-364] (verified DOW-preserving); at j=365 it is NaN
  - TEST: stockout_days_7 at j=1 reads only observed stockout flags; at j=2 it is NaN unless the caller supplies projected stockout flags (and the V2 MVP does NOT support that — so always NaN for j>=2)
  - DOCSTRING: load-bearing — must never be weakened to make a feature pass (mirror the V1 spec docstring)

Task 6 — MODIFY app/shared/feature_frames/__init__.py:
  - ADD V2 exports (FEATURE_FRAME_VERSION_V1/V2, EXOGENOUS_LAGS_V2, ROLLING_WINDOWS_V2, …, FeatureGroup, V2ColumnSpec, V2HistoricalSidecar, V2FutureSidecar, v2_column_manifest, canonical_feature_columns_v2, v2_feature_groups_dict, v2_feature_safety_classes, build_historical_feature_rows_v2, build_future_feature_rows_v2)
  - KEEP every V1 export at the same position (back-compat)
  - DO NOT introduce a circular import — V2 contract module imports nothing from V1 module (they share constants by VALUE, not by re-export)

Task 7 — MODIFY app/features/forecasting/schemas.py:
  - FIND class TrainRequest (line 284)
  - INJECT after line containing `config: ModelConfig` two new fields:
      feature_frame_version: int = Field(default=1, ge=1, le=2, description="Which feature contract version to build for this training run. 1 = V1 (default, back-compat); 2 = V2 (opt-in, requires regression / additive / tree feature-aware models).")
      feature_groups: list[str] | None = Field(default=None, description="When feature_frame_version=2: optional list of FeatureGroup names to enable (None → DEFAULT_V2_GROUPS). When feature_frame_version=1: MUST be None / omitted; supplying any value returns 422.")
  - VALIDATE (model_validator, mode="after"): when feature_frame_version == 1 AND feature_groups is not None → raise ValueError("feature_groups is only valid when feature_frame_version=2"). FastAPI surfaces this as a 422 RFC 7807 problem+json — V1 does NOT silently ignore feature_groups.
  - VALIDATE (model_validator, mode="after"): when feature_frame_version == 2 AND feature_groups is not None → every string in feature_groups MUST match a FeatureGroup enum value (raise ValueError → 422 with the offending name). When feature_groups is None at V2, the service layer resolves it to DEFAULT_V2_GROUPS.
  - DO NOT touch ModelConfigBase or any ModelConfig — preserves all V1 config_hash values byte-for-byte
  - PRESERVE: ConfigDict(strict=True) at the model level
  - PRESERVE: train_start_date/train_end_date Field(strict=False) override

Task 8 — CREATE app/features/forecasting/v2_loaders.py:
  - DEFINE async load_lifecycle_attrs(db, product_id) -> tuple[date|None, date|None, str|None]
      (launch_date, discontinue_date, lifecycle_stage)
  - DEFINE async load_inventory_history(db, store_id, product_id, start_date, end_date) -> dict[date, tuple[int, bool]]
      Returns: {date: (on_hand_qty, is_stockout)} — TIME-SAFE filter date <= end_date at SQL boundary
  - DEFINE async load_replenishment_history(db, store_id, product_id, start_date, end_date) -> tuple[list[date], list[int]]
      Returns: (event_dates, event_qty) sorted ascending — TIME-SAFE filter
  - DEFINE async load_returns_history(db, store_id, product_id, start_date, end_date) -> dict[date, int]
      Returns: {date: total_return_quantity} — TIME-SAFE filter
  - DEFINE async load_promotion_history(db, store_id, product_id, start_date, end_date) -> list[PromoSpan]
      PromoSpan = (start_date, end_date, kind, discount_pct) — expand to per-day kind sets at caller
  - DEFINE async load_exogenous_history(db, store_id, start_date, end_date, signal_names: list[str] | None) -> dict[date, dict[str, float]]
      Returns: {date: {signal_name: value}} — TIME-SAFE filter; per-store + global rows merged
  - HELPER: assemble_v2_historical_sidecar(...) — pure synchronous assembly of V2HistoricalSidecar from the loader outputs, given the `dates` list
  - HELPER: assemble_v2_future_sidecar(...) — pure synchronous assembly of V2FutureSidecar
  - PATTERN: mirror app/features/forecasting/service.py:_build_regression_features (uses `select(ColumnSet).where(...).order_by(date)` and `await db.execute(stmt)`)
  - SECURITY: every where clause uses SQLAlchemy 2.0 parameter binding (NEVER string concat)
  - LOGGING: structlog INFO event per loader on completion with row counts

Task 9 — MODIFY app/features/forecasting/service.py:
  - ADD an enum-style helper `_resolve_feature_frame_version(request_version: int) -> int` (clamp + validate against {1, 2})
  - FIND _build_regression_features (line 515)
  - ADD a sibling async method `_build_regression_features_v2(db, store_id, product_id, start_date, end_date, groups: tuple[FeatureGroup, ...]) -> RegressionFeatureMatrix`
    - LOAD: sales (already in V1 loader), holidays, promotions (with kind + discount_pct), lifecycle, inventory, replenishment, returns, exogenous (when groups include them)
    - ASSEMBLE: V2HistoricalSidecar via the new helper
    - BUILD: feature_rows = build_historical_feature_rows_v2(dates=…, quantities=…, prices=…, baseline_price=…, sidecar=…, groups=…)
    - history_tail length = HISTORY_TAIL_DAYS_V2 (400) not HISTORY_TAIL_DAYS (90)
    - feature_columns = canonical_feature_columns_v2(groups)
  - FIND train_model (line 201)
  - INJECT a branch on `request.feature_frame_version` (passed in via the routes layer):
      if version == 2:
          features = await self._build_regression_features_v2(...)
      else:
          features = await self._build_regression_features(...)  # unchanged
  - EXTEND extra_metadata (line 254) when features were built via V2:
      extra_metadata["feature_frame_version"] = 2
      extra_metadata["feature_groups"] = v2_feature_groups_dict(features.feature_columns)
      extra_metadata["feature_safety_classes"] = v2_feature_safety_classes(features.feature_columns)
      extra_metadata["feature_pinned_constants"] = {"exogenous_lags": list(EXOGENOUS_LAGS_V2), "rolling_windows": list(ROLLING_WINDOWS_V2), ...}
  - EXTEND extra_metadata when V1 (additive, harmless):
      extra_metadata["feature_frame_version"] = 1
  - PRESERVE: ModelBundle persistence path; persistence.py is unchanged
  - PRESERVE: _build_regression_features signature, return type, and body — byte-stable for V1 callers

Task 10 — MODIFY app/features/forecasting/routes.py:
  - FIND the /forecasting/train handler
  - THREAD request.feature_frame_version (and request.feature_groups when version=2) into ForecastingService.train_model
  - NO change to /forecasting/predict (predict path is version-agnostic; bundle metadata is self-describing)

Task 11 — MODIFY app/features/scenarios/feature_frame.py:
  - FIND build_future_frame (line 232)
  - ADD an optional `feature_frame_version: int = 1` parameter (default = 1 → V1 path unchanged byte-for-byte)
  - WHEN version == 2:
    - PARSE the requested groups from `feature_columns` (read group via v2_feature_groups_dict reverse mapping)
    - LOAD discontinue_date + lifecycle attrs via load_lifecycle_attrs (NOT a forecasting-service call; either move the helper to app/shared or duplicate the tiny query — the latter mirrors the existing same-slice ORM-only pattern at lines 271-281)
    - ASSEMBLE V2FutureSidecar: holiday_dates (from Calendar table + assumptions.holiday); price_factor_per_day / promo_active_per_day / promo_kinds_per_day / promo_discount_pct_per_day from assumptions; weather/macro/inventory left None (NaN columns in the future frame are acceptable)
    - CALL build_future_feature_rows_v2(...)
    - WRAP in FutureFeatureFrame
  - PRESERVE: V1 dispatch via the assemble_future_frame path (line 181) is byte-stable
  - DO NOT cross-slice-import — keep the lifecycle loader inline in this slice (mirror the data_platform.models import already used at line 55)

Task 12 — MODIFY app/features/scenarios/service.py:
  - FIND the `feature_columns = …` cast at the model_exogenous path (~line 213-222 per the explorer report)
  - INJECT a sibling read: feature_frame_version = int(bundle.metadata.get("feature_frame_version", 1))
  - THREAD feature_frame_version into build_future_frame (new optional parameter from Task 11)
  - V1 bundles (without the metadata key) default to 1 → byte-stable V1 path

Task 13 — MODIFY app/features/backtesting/service.py:
  - FIND the calls to build_historical_feature_rows (line 493) and build_future_feature_rows (line 553)
  - READ feature_frame_version from the fitted bundle BEFORE the fold loop:
      version = int(getattr(bundle, "metadata", {}).get("feature_frame_version", 1))
      feature_columns = bundle.metadata.get("feature_columns") if version == 2 else None
  - WHEN version == 2:
    - BEFORE the per-fold work, load the V2 sidecar data ONCE for the full training window and slice per fold
    - CALL build_historical_feature_rows_v2(...) instead of the V1 builder
    - PER fold: CALL build_future_feature_rows_v2(..., test_dates=split.test_dates, history_tail=history_tail_slice, gap=split.gap, sidecar=fold_future_sidecar, groups=…)
  - WHEN version == 1: unchanged byte-for-byte
  - LOGGING: include feature_frame_version in the fold-start log line

Task 14 — CREATE app/features/forecasting/tests/test_regression_features_v2_leakage.py:
  - MIRROR app/features/forecasting/tests/test_regression_features_leakage.py
  - SEQUENTIAL targets so leakage is mathematically detectable
  - TEST every V2 column emitted by build_historical_feature_rows_v2: cells read strictly earlier observations only
  - TEST: with sequential targets, rolling_mean_7 at row i == mean of quantities[i-7..i-1]; NEVER includes quantities[i] or later
  - DOCSTRING: LOAD-BEARING — never weaken

Task 15 — CREATE app/features/forecasting/tests/test_v2_loaders.py (integration, requires docker-compose):
  - SEED a minimal fixture: 1 store, 1 product, 60 days of sales + inventory + a handful of replenishment events + returns + exogenous signals
  - TEST load_inventory_history: rows beyond cutoff are NOT returned (time-safe)
  - TEST load_replenishment_history: same
  - TEST load_returns_history: same
  - TEST load_exogenous_history: per-store + global rows merge correctly; signal_name filter narrows the result set

Task 16 — CREATE app/features/forecasting/tests/test_service_v2.py (integration, requires docker-compose):
  - End-to-end: POST a V2 TrainRequest, verify the response, load the saved bundle, assert bundle.metadata contains feature_frame_version=2 and the expected feature_columns / feature_groups / feature_safety_classes
  - Assert HGBR can fit + predict on the V2 matrix (the existing model code path)
  - Assert V1 → V2 → V1 round-trip: a V1 train + V2 train coexist; no shared state mutation

Task 17 — CREATE app/features/scenarios/tests/test_future_frame_v2_leakage.py:
  - MIRROR test_future_frame_leakage.py
  - Build a V2 future frame against a synthetic V2 bundle (metadata-only — no real estimator needed)
  - Assert: every V2 column whose safety class is CONDITIONALLY_SAFE is NaN at j>=2 unless the corresponding sidecar slice was supplied
  - Assert: assumption-driven columns (price_factor, promo_active, promo_discount_pct, promo_kind_*) reflect the assumptions exactly
  - Assert: weather/macro columns are NaN when sidecar.*_per_day is empty

Task 18 — CREATE app/features/backtesting/tests/test_feature_aware_backtest_v2.py:
  - End-to-end: train a V2 regression model, run a backtest, verify the fold loop dispatched to rows_v2 (assert a fold-start log carries feature_frame_version=2)
  - Verify the fold's X_future has the V2 column count

Task 19 — CREATE examples/forecasting/feature_frame_v2_preview.py:
  - Read-only diagnostic script — given a (store_id, product_id) pair and a cutoff_date, prints:
    - V1 feature columns + first 3 rows of the V1 matrix
    - V2 feature columns + first 3 rows of the V2 matrix
    - Per-group NaN counts in V2 (to flag missing sidecar data on smaller seeded DBs)
  - Local-development only — no network egress, no DB writes

Task 20 — UPDATE docs/optional-features/10-baseforecaster-feature-contract.md:
  - ADD a "V2" section after the existing V1 contract documentation
  - Document the FeatureGroup enum, the default groups, the safety classes, and the NaN-where-future contract
  - Cross-reference test_leakage_v2.py as the load-bearing spec

Task 21 — UPDATE docs/PHASE/3-FEATURE_ENGINEERING.md and docs/PHASE/4-FORECASTING.md:
  - Note: V2 is opt-in via TrainRequest.feature_frame_version=2; V1 remains the default and the back-compat path

Task 22 — VERIFY no Alembic migration is needed:
  - V2 reads only existing tables (inventory_snapshot_daily, replenishment_event, sales_returns, exogenous_signal, promotion, product)
  - V2 writes nothing to the DB
  - No schema change → no migration. Verify by running `uv run alembic current` and `uv run alembic check` (no pending revisions).
```

### Per task pseudocode (the leakage-critical parts)

```python
# Task 3 — build_historical_feature_rows_v2 (rolling-mean column)
def _rolling_mean_column(
    quantities: list[float],
    window: int,
) -> list[float]:
    """Leakage-safe rolling mean: row i reads quantities[i-window..i-1] ONLY.
    The first `window` rows are NaN.
    """
    out = []
    for i in range(len(quantities)):
        if i < window:
            out.append(math.nan)
        else:
            out.append(sum(quantities[i - window : i]) / window)
    return out
# CRITICAL: NEVER include quantities[i] in the slice — that's current-day leakage.

# Task 3 — build_future_feature_rows_v2 (rolling-mean future column)
def _future_rolling_mean_column(
    history_tail: list[float],
    horizon: int,
    window: int,
) -> list[float]:
    """For horizon day j (1..horizon), the rolling-mean source window covers
    T+j-window .. T+j-1. If ANY source day > T (i.e. j-1 >= 1), emit NaN.
    Equivalently: source covers the future ⟺ horizon day > 1 AND window > 1;
    for window=W the j-th horizon day's window is [T+j-W .. T+j-1].
    The window is fully observed ⟺ j-1 <= 0 (only j=1, when the
    window is T-W+1..T — all observed). For j >= 2 emit NaN.
    """
    out = []
    for j in range(1, horizon + 1):
        if j == 1 and len(history_tail) >= window:
            out.append(sum(history_tail[-window:]) / window)
        else:
            out.append(math.nan)
    return out
# CRITICAL: This is the canonical V2 NaN-where-future rule for rolling/trend/window-aggregate features.

# Task 3 — same_dow_mean_4
def _same_dow_mean_column(
    dates: list[date],
    quantities: list[float],
    n_back: int,
) -> list[float]:
    """For row i with weekday w, average the `n_back` most recent earlier
    observations whose weekday is also w. NaN when fewer than n_back are
    available.
    """
    out = []
    for i, day in enumerate(dates):
        same_dow = [quantities[j] for j in range(i) if dates[j].weekday() == day.weekday()]
        if len(same_dow) >= n_back:
            out.append(sum(same_dow[-n_back:]) / n_back)
        else:
            out.append(math.nan)
    return out

# Task 9 — train_model dispatch (key lines, NOT full code)
async def train_model(self, db, store_id, product_id, train_start_date, train_end_date, config, *, feature_frame_version: int = 1, feature_groups: list[str] | None = None):
    model = model_factory(config, random_state=self.settings.forecast_random_seed)
    extra_metadata: dict[str, object] = {}
    if model.requires_features:
        if feature_frame_version == 2:
            groups = _resolve_groups(feature_groups)
            features = await self._build_regression_features_v2(
                db, store_id, product_id, train_start_date, train_end_date, groups=groups,
            )
            extra_metadata["feature_frame_version"] = 2
            extra_metadata["feature_groups"] = v2_feature_groups_dict(features.feature_columns)
            extra_metadata["feature_safety_classes"] = v2_feature_safety_classes(features.feature_columns)
        else:
            features = await self._build_regression_features(  # unchanged V1
                db, store_id, product_id, train_start_date, train_end_date,
            )
            extra_metadata["feature_frame_version"] = 1  # additive; legacy bundles default via .get(..., 1)
        model.fit(features.y, features.X)
        n_observations = features.n_observations
        extra_metadata.update({
            "feature_columns": features.feature_columns,
            "history_tail": features.history_tail,
            "history_tail_dates": features.history_tail_dates,
            "launch_date": features.launch_date_iso,
        })
    else:
        # … V1 baseline path unchanged …
        pass
    # … bundle save unchanged …
```

### Integration Points

```yaml
DATABASE:
  - migration: NONE — V2 reads only existing tables. Verify with `uv run alembic check`.
  - read-only loaders: app/features/forecasting/v2_loaders.py
  - time-safe filter: every `where` clause includes `<= cutoff_date`

CONFIG:
  - app/core/config.py: NO new settings keys. V2 reuses forecast_model_artifacts_dir, etc.
  - .env.example: unchanged

ROUTES:
  - app/features/forecasting/routes.py: thread request.feature_frame_version and request.feature_groups into ForecastingService.train_model
  - app/features/backtesting/routes.py: no change (dispatch happens inside service via bundle metadata)
  - app/features/scenarios/routes.py: no change (dispatch happens inside build_future_frame)
  - No new endpoint paths

SCHEMAS:
  - app/features/forecasting/schemas.py:
      TrainRequest:
        + feature_frame_version: int = Field(default=1, ge=1, le=2, description="V1 (default) or V2 feature contract")
        + feature_groups: list[str] | None = Field(default=None, description="V2 groups; MUST be None when version=1, else 422")
        + @model_validator (mode="after"): when version=1 AND feature_groups is not None → reject (422). When version=2 AND feature_groups is not None → every name must match FeatureGroup (reject unknown names → 422). V1 does NOT silently ignore feature_groups.
  - app/features/forecasting/schemas.py (FeatureMetadataResponse): no breaking change — feature_columns already exists; consider adding optional feature_frame_version + feature_groups (purely additive)

BUNDLE METADATA (additive — no schema migration):
  - feature_frame_version: int
  - feature_columns: list[str]                    # already exists for V1
  - feature_groups: dict[str, list[str]]          # NEW (V2)
  - feature_safety_classes: dict[str, str]        # NEW (V2)
  - feature_pinned_constants: dict[str, list[int]] # NEW (V2) — for reproducibility audits
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Auto-fix what you can, then re-check
uv run ruff check app/shared/feature_frames app/features/forecasting \
                  app/features/backtesting app/features/scenarios --fix
uv run ruff format app/shared/feature_frames app/features/forecasting \
                   app/features/backtesting app/features/scenarios
uv run ruff format --check .

# Strict type checks (BOTH gate merge)
uv run mypy app/
uv run pyright app/

# Expected: zero errors. If errors, READ the message and fix; never silence.
```

### Level 2: Pure unit tests (no DB)

```bash
# V1 leakage spec must stay byte-stable
uv run pytest -v app/shared/feature_frames/tests/test_leakage.py
uv run pytest -v app/features/forecasting/tests/test_regression_features_leakage.py
uv run pytest -v app/features/scenarios/tests/test_future_frame_leakage.py
uv run pytest -v app/features/featuresets/tests/test_leakage.py

# V2 leakage spec — load-bearing, MUST pass on first green run
uv run pytest -v app/shared/feature_frames/tests/test_leakage_v2.py
uv run pytest -v app/shared/feature_frames/tests/test_contract_v2.py
uv run pytest -v app/features/forecasting/tests/test_regression_features_v2_leakage.py
uv run pytest -v app/features/scenarios/tests/test_future_frame_v2_leakage.py

# Full pure-Python suite — pretest gate
uv run pytest -v -m "not integration"
# Expected: every test in the V1 baseline passes (unchanged); every new V2 test passes.
```

### Level 3: Integration tests (real Postgres)

```bash
# Ensure docker-compose is up
docker compose up -d
uv run alembic upgrade head
uv run python scripts/check_db.py

# Verify no new migration was introduced (V2 reads only existing tables)
uv run alembic check
# Expected: "no problems detected" — V2 introduces no schema change.

# DB-touching V2 tests
uv run pytest -v -m integration app/features/forecasting/tests/test_v2_loaders.py
uv run pytest -v -m integration app/features/forecasting/tests/test_service_v2.py
uv run pytest -v -m integration app/features/backtesting/tests/test_feature_aware_backtest_v2.py
```

### Level 4: Smoke — V1 round-trip + V2 happy path against the live demo DB

```bash
# Start backend (or reuse the running one)
uv run uvicorn app.main:app --reload --port 8123

# V1 train (back-compat) — feature_frame_version omitted → defaults to 1
curl -sS -X POST http://localhost:8123/forecasting/train \
  -H 'Content-Type: application/json' \
  -d '{
        "store_id": 15, "product_id": 52,
        "train_start_date": "2025-01-01", "train_end_date": "2025-12-31",
        "config": {"model_type": "regression"}
      }' | jq .
# Expected: 200; bundle saved; the saved bundle metadata.get("feature_frame_version", 1) == 1.

# V2 train — opt in
curl -sS -X POST http://localhost:8123/forecasting/train \
  -H 'Content-Type: application/json' \
  -d '{
        "store_id": 15, "product_id": 52,
        "train_start_date": "2025-01-01", "train_end_date": "2025-12-31",
        "config": {"model_type": "regression"},
        "feature_frame_version": 2,
        "feature_groups": ["target_history","rolling","trend","calendar","price_promo","lifecycle"]
      }' | jq .
# Expected: 200; bundle metadata carries feature_frame_version=2 with the
# right feature_columns / feature_groups / feature_safety_classes shape.

# V2 scenario simulation against the V2 bundle (no API change required)
# Slice C will surface this in the UI; here we just confirm the dispatch.
curl -sS -X POST http://localhost:8123/scenarios/simulate \
  -H 'Content-Type: application/json' \
  -d '{ "run_id": "<v2_model_artifact_key>", "horizon": 14, "assumptions": {"price": {"start_date":"2026-01-01","end_date":"2026-01-07","change_pct":-0.15}} }' | jq .
# Expected: 200; method="model_exogenous"; comparison populated.

# Optional: run the preview script
uv run python examples/forecasting/feature_frame_v2_preview.py --store-id 15 --product-id 52 --cutoff-date 2025-12-31
```

---

## Final validation Checklist

- [ ] V1 leakage spec passes unchanged (`app/shared/feature_frames/tests/test_leakage.py`)
- [ ] V1 forecasting leakage spec passes unchanged (`app/features/forecasting/tests/test_regression_features_leakage.py`)
- [ ] V1 scenarios leakage spec passes unchanged (`app/features/scenarios/tests/test_future_frame_leakage.py`)
- [ ] V1 featuresets leakage spec passes unchanged (`app/features/featuresets/tests/test_leakage.py`)
- [ ] AST-walk leaf-level invariant passes — `app/shared/feature_frames/**` imports nothing from `app/features/**`
- [ ] V2 leakage spec passes on first green run (`app/shared/feature_frames/tests/test_leakage_v2.py`)
- [ ] V2 contract tests pass (`app/shared/feature_frames/tests/test_contract_v2.py`)
- [ ] V2 forecasting integration test passes (`app/features/forecasting/tests/test_service_v2.py`)
- [ ] V2 backtest integration test passes
- [ ] V2 scenarios integration test passes
- [ ] V1 bundle (saved pre-PRP) loads and predicts; bundle.metadata.get("feature_frame_version", 1) == 1
- [ ] V2 bundle round-trip: save → load → predict (via scenarios) → backtest
- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run mypy app/` clean (strict)
- [ ] `uv run pyright app/` clean (strict)
- [ ] `uv run pytest -v -m "not integration"` green
- [ ] `uv run pytest -v -m integration` green (with docker-compose up)
- [ ] `uv run alembic check` — no new migration
- [ ] examples/forecasting/feature_frame_v2_preview.py runs against the local DB
- [ ] No new endpoint paths added
- [ ] No new dependencies in pyproject.toml
- [ ] No managed-cloud SDK introduced
- [ ] No agent tool added (no change to `agent_require_approval`)
- [ ] CHANGELOG entry under "Unreleased" (release-please rules — `feat(forecast): …` → PATCH bump pre-1.0)
- [ ] Manual smoke: V1 curl → 200, V2 curl → 200, both bundles round-trip

---

## Open Design Decisions — RESOLVED in this PRP

The INITIAL listed open design decisions; each is locked here so the
implementer does not relitigate them.

| # | Decision | Resolution | Why |
|---|----------|------------|-----|
| 1 | `lag_364` vs `lag_365` | **lag_364** | Verified: 364 = 52×7, preserves day-of-week; 365 shifts DOW (verified with `(date - timedelta(days=364)).weekday() == date.weekday()`). |
| 2 | Recursive rolling vs origin-fixed | **Origin-fixed / NaN-where-future** | The leakage-safe MVP. Any rolling window at horizon day j whose source covers a future day emits NaN. Recursion is a separate, riskier feature (Slice B at earliest). |
| 3 | Stockout: feature only or target rewriting | **Feature only** | Target rewriting changes the loss surface and the metric semantics — needs its own PRP. V2 exposes `is_stockout_lag1` / `stockout_days_7/28` / `inventory_available_ratio_28` as features. |
| 4 | Phase 2 exogenous in V2 MVP or optional | **Optional groups** | Defaults are `(TARGET_HISTORY, ROLLING, TREND, CALENDAR, PRICE_PROMO, LIFECYCLE)`. `INVENTORY`, `REPLENISHMENT`, `RETURNS`, `EXOGENOUS_WEATHER`, `EXOGENOUS_MACRO` are off by default — opt-in via `feature_groups` on the request. Keeps the MVP green on smaller seeded DBs. |
| 5 | UI labelling | **Bundle metadata carries group names** | `feature_groups: dict[str, list[str]]` in bundle metadata maps every column to its group; Slice C consumes this in the UI. No UI code in this PRP. |
| 6 | Where to put `feature_frame_version` | **`TrainRequest` + bundle metadata** | NOT on `ModelConfigBase` — that would change every existing `config_hash()` value and orphan registry rows / aliases. Put it on the request and persist it to bundle metadata. |
| 7 | History tail length for V2 | **400 days** | max(EXOGENOUS_LAGS_V2) + max(ROLLING_WINDOWS_V2) + buffer = 364 + 28 + 8 = 400. V1's 90 is too short for lag_364. |

---

## Anti-Patterns to Avoid

- ❌ Don't add `feature_frame_version` to `ModelConfigBase` — it changes every V1 hash.
- ❌ Don't recursively project rolling/trend/stockout features into the future — emit NaN.
- ❌ Don't introduce a new SafetyClass enum value — the three existing classes cover every V2 column.
- ❌ Don't import any sibling slice (`forecasting → featuresets`, `backtesting → forecasting`, `scenarios → forecasting`). Use `app/shared/feature_frames` only.
- ❌ Don't silently zero-fill a sidecar cell when a specific day has no source data — emit NaN and let HGBR handle it. Zero is a real demand-domain value (0 returns, 0 stockout days, $0 discount) and zero-filling would corrupt the signal.
- ❌ Don't NaN-fill columns for a DISABLED feature group — omit those columns entirely. Group enablement (controlled by `groups`) decides which columns appear; data presence decides only their values.
- ❌ Don't raise ValueError because a single day inside an enabled group has no data — that's the NaN case. ValueError is reserved for misaligned sidecar array lengths, an empty `groups` parameter, an unknown group name, or a sidecar field that's entirely missing for an enabled group.
- ❌ Don't weaken any existing leakage spec to make a V2 test pass.
- ❌ Don't add an Alembic migration; V2 reads only existing tables.
- ❌ Don't introduce a new endpoint path; opt-in to V2 via the existing `/forecasting/train` body.
- ❌ Don't use SimpleImputer with the default `keep_empty_features=False` (memory `simpleimputer-drops-empty-columns`) — V2 doesn't impute; the matrix carries NaN directly to HGBR.
- ❌ Don't cite `HistGradientBoostingRegressor.feature_importances_` — it does not exist (memory `histgbr-no-feature-importances`). V2 leaves feature-importance extraction untouched in this PRP; that's Slice B / a future PRP.

---

## Confidence

**Confidence: 8/10** for one-pass implementation success.

What grounds the 8:
- Every seam is anchored to a file:line, including the surprising ones (backtesting hard-coding `canonical_feature_columns()` at the builder call site; `config_hash()` hashing the full `model_dump_json`).
- Every "open design decision" from the INITIAL is locked with a justification.
- Every cited library default is verified by an executed `uv run python -c …` command, with the output captured in "Known Gotchas".
- The PRP keeps Slice B (new model classes) and Slice C (UI) explicitly out of scope, so the surface stays reviewable.
- V1 byte-stability is enforced by keeping `_build_regression_features` and the V1 builders unchanged; the AST-walk invariant still passes.

What costs the 2 points:
- The V2 surface is large (≈25 new columns × historical + future builder × leakage tests). A diligent implementer can land it in one branch but it's not a tiny PRP.
- The exact column emission order inside each V2 group has freedom; the PRP locks the group order but allows the implementer to choose within-group ordering as long as the bundle metadata records it.
- Phase 2 sidecar groups (replenishment / returns / exogenous / inventory) are off by default — they get fewer integration tests against the small CI DB. Mitigation: the live local DB (HANDOFF.md — 31,420 replenishment events, 9,647 exogenous signals, 8,585 returns) is sufficient to smoke-test them manually before merge.
