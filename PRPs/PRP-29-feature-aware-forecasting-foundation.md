name: "PRP-29 — Feature-Aware Forecasting Foundation (MLZOO-A)"
description: |

## Purpose

The first PRP of the **Advanced ML Model Zoo** sequence (`PRPs/INITIAL/INITIAL-MLZOO-index.md`).
It builds the *foundation* a later LightGBM / XGBoost / Prophet-like model will stand on:
a single, leakage-safe, **shared** feature-frame contract — so a future advanced model can be
added without re-deriving the frame machinery and without breaking the baseline forecasters.

This PRP implements **contracts, consolidation, and leakage tests only**. It adds **no**
advanced model, **no** new dependency, **no** migration, **no** frontend, **no** agent tool,
and **no** API behaviour change. If you find yourself implementing LightGBM, stop — that is
PRP-MLZOO-B.

## What this PRP already inherits (DO NOT re-build)

The feature-aware *machinery* already exists — it is just **fragmented and duplicated**:

- `BaseForecaster` (`app/features/forecasting/models.py:47`) already has the feature-aware
  signature: `fit(y, X=None)` / `predict(horizon, X=None)`. The three baselines ignore `X`
  (every `fit`/`predict` carries `# noqa: ARG002`); `RegressionForecaster` (`models.py:428`)
  *consumes* it and is the first feature-aware model.
- The **historical training frame** is built by `ForecastingService._build_regression_features`
  (`app/features/forecasting/service.py:454-595`).
- The **future prediction frame** is built by `app/features/scenarios/feature_frame.py`
  (the leakage-safe `build_*_columns` + `assemble_future_frame` + `build_future_frame`).
- The leakage-safe rule and the long-lag-vs-recursion decision are documented in
  `PRPs/ai_docs/exogenous-regressor-forecasting.md` (§2, §5).

The **problem this PRP fixes**: the regression feature-column contract is **physically
duplicated** across two slices — `_REGRESSION_FEATURE_COLUMNS` (`forecasting/service.py:87-99`)
and `canonical_feature_columns()` / `CALENDAR_COLUMNS` / `EXOGENOUS_COLUMNS`
(`scenarios/feature_frame.py:74-127`) — because a cross-slice import is forbidden
(AGENTS.md § Architecture, PRP-27 DECISIONS LOCKED #3). They are kept in lock-step only by a
fragile integration-test side-effect ("an empty-assumption simulation must yield a zero
delta"). A future model cannot safely build on a contract that lives in two places.

## DEPENDS ON — read before starting

- `PRPs/INITIAL/INITIAL-MLZOO-A-foundation-feature-frames.md` — this PRP's brief.
- `PRPs/INITIAL/INITIAL-MLZOO-index.md` — the MLZOO roadmap (A → B → C → D).
- `docs/optional-features/05-advanced-ml-model-zoo.md` — the full model-zoo vision and risks.
- `PRPs/ai_docs/exogenous-regressor-forecasting.md` — the exogenous-regressor + future-frame
  leakage reference (§1 contract, §2 leakage rule, §5 de-risking recommendations).

---

## Goal

Move the regression feature-frame **contract** and its **leakage-safe pure builders** into a
single cross-cutting module, `app/shared/feature_frames/`, that both the forecasting slice
(training frame) and the scenarios slice (future frame) import — eliminating the duplicated
`_REGRESSION_FEATURE_COLUMNS` ↔ `canonical_feature_columns()` pair. Formalise the
feature-aware model contract with a `requires_features` class attribute, document the
historical/future frame requirements and the safe / conditionally-safe / unsafe feature-class
taxonomy, and add load-bearing leakage tests for the shared builders and the historical
training builder.

**End state:** there is exactly **one** definition of the regression feature-column set,
imported (not re-typed) by both slices; a future advanced model in PRP-MLZOO-B sets
`requires_features = True` and reuses the shared frame builders with zero new contract code.

## Why

- **Foundation for the model zoo.** PRP-MLZOO-B (LightGBM / sklearn fallback) needs a tested,
  single-source frame contract. Today it would have to choose *which* of two duplicated column
  lists to extend — a guaranteed drift bug.
- **Eliminates a latent correctness hazard.** A silent mismatch between the two column lists
  corrupts the `model_exogenous` re-forecast (the model is fed columns in the wrong order).
  Today only an integration-test side-effect catches it; after this PRP a mismatch is
  structurally impossible (one shared list).
- **Codifies the leakage rules.** `docs/optional-features/05-advanced-ml-model-zoo.md:158-163`
  names "Future feature generation is easy to get wrong" and "Backtests must prevent leakage
  for every generated feature" as the top risks. This PRP turns the implicit rules into a
  documented taxonomy + a load-bearing test file.
- **No behaviour change, no risk to baselines.** Pure consolidation + tests + docs. The
  baseline forecasters, the registry, persisted model bundles, and every HTTP/WS contract are
  untouched.

## What

A refactor-and-document PRP. User-visible behaviour is **identical** before and after; the
value is entirely structural (one contract, tested rules, a foundation doc).

### Technical requirements

1. New cross-cutting package `app/shared/feature_frames/` owning: the pinned constants
   (`EXOGENOUS_LAGS`, `HISTORY_TAIL_DAYS`), the column-name tuples (`CALENDAR_COLUMNS`,
   `EXOGENOUS_COLUMNS`), `canonical_feature_columns()`, the `FutureFeatureFrame` dataclass,
   the leakage-safe pure builders (`build_calendar_columns`, `build_long_lag_columns`), and a
   `FeatureSafety` taxonomy (`FEATURE_CLASS` map).
2. `app/features/scenarios/feature_frame.py` imports the above from the shared package and
   **re-exports** them (back-compat for existing importers); it keeps only the
   assumption-driven, DB-touching parts (`build_exogenous_columns`, `assemble_future_frame`,
   `build_future_frame`, `MAX_COMPARE_SCENARIOS`).
3. `app/features/forecasting/service.py::_build_regression_features` imports the shared
   contract; the local `_REGRESSION_FEATURE_COLUMNS` / `_REGRESSION_LAGS` /
   `_REGRESSION_HISTORY_TAIL_DAYS` constants are deleted.
4. `BaseForecaster` gains a `requires_features: ClassVar[bool] = False`; `RegressionForecaster`
   overrides it to `True`. `ForecastingService.train_model` / `predict` branch on
   `model.requires_features` instead of the `config.model_type == "regression"` string check.
5. Load-bearing leakage tests: `app/shared/feature_frames/tests/test_leakage.py` (shared
   builders) and `app/features/forecasting/tests/test_regression_features_leakage.py`
   (historical training builder).
6. The curated contract doc `examples/models/feature_frame_contract.md` (historical vs future
   frame shape, required columns, the safe/conditional/unsafe taxonomy); an additive update to
   `examples/models/model_interface.md`.

### Success Criteria

- [ ] The regression feature-column set is defined **exactly once** (`canonical_feature_columns()`
      in `app/shared/feature_frames/`); `grep -rn "_REGRESSION_FEATURE_COLUMNS" app/` returns nothing.
- [ ] `app/shared/feature_frames/` imports nothing from `app/features/**` (verified by a test).
- [ ] `BaseForecaster.requires_features` exists; `NaiveForecaster/SeasonalNaiveForecaster/MovingAverageForecaster` → `False`, `RegressionForecaster` → `True`.
- [ ] All existing tests pass unchanged: baseline forecasters, `test_regression_forecaster.py`,
      every scenarios test (including the empty-assumption zero-delta integration test).
- [ ] New leakage tests prove no shared builder and no historical training row ever reads a
      target value at or after the forecast origin / cutoff.
- [ ] `examples/models/feature_frame_contract.md` exists and documents both frame shapes + the taxonomy.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"` all green.
- [ ] No new dependency in `pyproject.toml`; no Alembic migration; no change to any route, schema, or WebSocket contract.

---

## All Needed Context

### Documentation & References

```yaml
- file: app/features/scenarios/feature_frame.py
  why: The future-frame builder. Its lines 62-127 (constants, CALENDAR_COLUMNS,
       EXOGENOUS_COLUMNS, canonical_feature_columns) and 93-216 (FutureFeatureFrame,
       _is_month_end, build_calendar_columns, build_long_lag_columns) MOVE VERBATIM to the
       shared package. Lines 219-407 (build_exogenous_columns, assemble_future_frame,
       build_future_frame) STAY — they depend on ScenarioAssumptions / the calendar table.
  critical: build_long_lag_columns is the leakage-critical helper; its `idx = (j-1)-k`,
       `idx < 0` guard is the spec. Move it byte-for-byte; do not "improve" it.

- file: app/features/scenarios/tests/test_future_frame_leakage.py
  why: The load-bearing leakage spec to mirror. The calendar/long-lag tests (the builders that
       MOVE) become app/shared/feature_frames/tests/test_leakage.py; the exogenous/assemble
       tests STAY here. Mirror its disjoint value-pool idiom (lines 50-56).
  critical: AGENTS.md § Safety — a *_leakage.py file may never be weakened. Splitting it
       across the move is allowed; deleting an assertion is not.

- file: app/features/forecasting/service.py
  why: Lines 74-99 are the duplicated constants to DELETE; lines 454-595
       (_build_regression_features) import the shared contract instead; lines 182-216
       (train_model branch) and 348-353 (predict branch) switch to `requires_features`.

- file: app/features/forecasting/models.py
  why: BaseForecaster (line 47) gets the `requires_features` ClassVar; RegressionForecaster
       (line 428) overrides it. The `# noqa: ARG002` on the baseline fit/predict is the marker
       that "this model ignores X" — `requires_features=False` is the formal version of it.

- file: app/features/featuresets/tests/test_leakage.py
  why: The canonical sequential-value leakage idiom for the *historical* builder test.
       Mirror its two-tier assertion (direction check THEN exact-equality check) and the
       "LEAKAGE DETECTED at row {i}" message convention.

- file: app/features/forecasting/persistence.py
  why: ModelBundle stores `feature_columns` in `metadata` as a plain list[str]. Moving the
       *function* that produces those strings does not change the strings — persisted bundles
       stay loadable. Do NOT change ModelBundle.

- file: app/shared/seeder/
  why: The precedent for a package under app/shared/ (with its own tests/ subdir). Mirror its
       layout: __init__.py re-exporting the public surface, tests/ alongside.

- docfile: PRPs/ai_docs/exogenous-regressor-forecasting.md
  why: §2 states the future-frame leakage rule verbatim and the feature-family table; §5 is
       the "long-lag + calendar + exogenous, no recursion" decision. The taxonomy in this PRP
       is the executable form of that table. Reference it from feature_frame_contract.md.

- doc: https://scikit-learn.org/stable/developers/develop.html
  section: Estimator interface conventions (get_params / set_params / fit returns self)
  critical: BaseForecaster already follows this. requires_features is an ADDITIVE class
       attribute — it does not break the sklearn-style contract.
```

### Current Codebase tree (relevant slices — all already exist)

```bash
app/
├── shared/
│   ├── __init__.py
│   ├── models.py
│   ├── schemas.py
│   ├── utils.py
│   └── seeder/                      # precedent: a package under app/shared/ with tests/
├── features/
│   ├── forecasting/
│   │   ├── models.py                # BaseForecaster + 4 forecasters + model_factory
│   │   ├── schemas.py               # ModelConfig union, TrainRequest/PredictRequest
│   │   ├── service.py               # _build_regression_features + _REGRESSION_* constants
│   │   ├── persistence.py           # ModelBundle (UNTOUCHED)
│   │   └── tests/
│   │       ├── test_regression_forecaster.py
│   │       └── test_service.py
│   ├── scenarios/
│   │   ├── feature_frame.py         # future-frame builder + duplicated contract
│   │   ├── service.py               # imports build_future_frame
│   │   ├── schemas.py
│   │   └── tests/
│   │       ├── conftest.py          # imports canonical_feature_columns
│   │       ├── test_feature_frame.py
│   │       └── test_future_frame_leakage.py   # load-bearing spec
│   └── backtesting/
│       ├── service.py               # _run_model_backtest fold loop (target-only)
│       └── tests/test_service.py
examples/models/
├── baseline_naive.py / baseline_seasonal.py / baseline_mavg.py
└── model_interface.md               # stale: no regression/lightgbm config rows
PRPs/ai_docs/exogenous-regressor-forecasting.md
```

### Desired Codebase tree — files to ADD

```bash
app/shared/feature_frames/
├── __init__.py                      # public re-exports of contract.py
├── contract.py                      # constants + taxonomy + columns + FutureFeatureFrame
│                                    #   + build_calendar_columns + build_long_lag_columns
└── tests/
    ├── __init__.py
    ├── test_contract.py             # column order, taxonomy, dataclass shape, determinism
    └── test_leakage.py              # LOAD-BEARING: calendar + long-lag leakage spec

app/features/forecasting/tests/
└── test_regression_features_leakage.py   # LOAD-BEARING: historical training-frame leakage

examples/models/
└── feature_frame_contract.md        # the curated contract doc (INITIAL-A asks for this)
```

### Files to MODIFY (all additive or behaviour-preserving)

```bash
app/features/scenarios/feature_frame.py        # import from shared + re-export; delete moved defs
app/features/scenarios/tests/test_feature_frame.py        # update imports (re-export keeps it passing)
app/features/scenarios/tests/test_future_frame_leakage.py # trim moved tests; keep exogenous/assemble
app/features/forecasting/models.py             # + requires_features ClassVar
app/features/forecasting/service.py            # import shared contract; requires_features branching
app/features/forecasting/tests/test_service.py # + requires_features assertions
app/features/backtesting/tests/test_service.py # + 1 guard test (no production-code change)
examples/models/model_interface.md             # additive: requires_features + regression row
```

### DECISIONS LOCKED (resolved during planning — do NOT re-litigate)

1. **Contract home = `app/shared/feature_frames/`.** A cross-cutting package (not a new
   vertical slice, not document-only). Both `forecasting` and `scenarios` import it. This is
   sanctioned by AGENTS.md § Architecture ("cross-cutting code goes through `app/core/` or
   `app/shared/`"). It is **not** a vertical slice — it has no `models.py`/`routes.py`/router;
   it is a pure library, like `app/shared/utils.py`.

2. **No `FeatureAwareForecaster` subclass.** `BaseForecaster` already carries the feature-aware
   signature. Formalise it with a `requires_features: ClassVar[bool]` attribute instead of a
   new base class — zero churn to the class hierarchy, zero change to persisted bundle types,
   and the service branches on `model.requires_features` with no `isinstance` check. A future
   `LightGBMForecaster` just sets `requires_features = True`.

3. **`POST /forecasting/predict` is NOT changed.** It still rejects feature-aware models
   (today: regression). Wiring an assumptions-free future frame into the predict path is
   PRP-MLZOO-B scope. The rejection branch is only *generalised* from a `model_type` string
   check to `model.requires_features` — same behaviour, future-proof condition.

4. **No `TrainingFrame` dataclass.** The historical training frame's requirements are *defined*
   by `canonical_feature_columns()` (the executable column contract, now shared) plus
   `examples/models/feature_frame_contract.md` (the prose spec) plus the new historical
   leakage test. `ForecastingService` keeps its existing internal `RegressionFeatureMatrix`
   carrier (it is not persisted; only its `.feature_columns` list is copied into bundle
   metadata). Introducing a second frame dataclass that nothing returns would be dead code
   (product-vision.md: do not add abstractions speculatively).

5. **Builders move; the contract is shared by IMPORT, not by re-typing.** `build_calendar_columns`
   and `build_long_lag_columns` are pure (no slice imports) → they move to the shared package.
   `build_exogenous_columns` takes a `ScenarioAssumptions` and `build_future_frame` reads the
   `calendar` table → they STAY in `scenarios/feature_frame.py` (the shared package may not
   import `app/features/**`). The forecasting historical builder keeps its own *value
   derivation* (DB-observed price/promo) but consumes the shared *column list and calendar
   builder*.

6. **NaN means "unknown", never a fabricated default.** A builder emits `math.nan` for a cell
   whose source is genuinely unknowable at origin `T` (a long-lag whose source day is in the
   horizon; `days_since_launch` when the product has no launch date). `HistGradientBoostingRegressor`
   tolerates NaN natively. The contract forbids silently substituting `0.0`. A future model
   that is *not* NaN-tolerant must impute explicitly in its own `fit`/`predict` — the frame
   builder must not.

7. **Backtesting is not wired for feature-aware models in this PRP.** The fold loop
   (`backtesting/service.py` `_run_model_backtest`) calls `model.fit(y_train)` target-only; a
   `RegressionForecaster` there raises `ValueError("RegressionForecaster requires exogenous
   features X")` — a *loud, non-leaky* failure. We add one regression test pinning that
   loud-failure behaviour and document it as a known limitation. Wiring feature-aware
   backtesting is PRP-MLZOO-B.

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: app/shared/** may NEVER import from app/features/** (AGENTS.md § Architecture).
#   The shared package is leaf-level. build_calendar_columns / build_long_lag_columns are pure
#   (stdlib `math`, `datetime`, `dataclasses` only) so this holds. A test asserts it (see Task 3).

# CRITICAL: build_long_lag_columns must move BYTE-FOR-BYTE. The leakage guard is the line
#   `idx = (j - 1) - lag` then `if idx < 0 and -tail_len <= idx:`. Any "tidy-up" risks
#   re-introducing the exact bug the load-bearing test exists to catch.

# GOTCHA: 6+ files import names from `app.features.scenarios.feature_frame`
#   (service.py, tests/conftest.py, tests/test_feature_frame.py, tests/test_future_frame_leakage.py).
#   After the move, feature_frame.py MUST re-export the moved names
#   (`from app.shared.feature_frames import (...)  # noqa: F401`) so those imports keep
#   resolving. Verified import sites — re-export ALL of: EXOGENOUS_LAGS, HISTORY_TAIL_DAYS,
#   CALENDAR_COLUMNS, EXOGENOUS_COLUMNS, canonical_feature_columns, FutureFeatureFrame,
#   build_calendar_columns, build_long_lag_columns.

# GOTCHA: MAX_COMPARE_SCENARIOS stays in scenarios/feature_frame.py — it is a Phase-C scenario
#   comparison cap, NOT a feature-frame concept. scenarios/schemas.py:413-414 references it by
#   comment. Do not move it to the shared package.

# CRITICAL: ConfigDict(strict=True) on request bodies — N/A here. This PRP adds no request
#   schema. The forecasting ModelConfig union is untouched.

# GOTCHA: `requires_features` is a ClassVar — annotate it `ClassVar[bool]` from `typing`.
#   mypy --strict / pyright --strict both gate merge; a bare `requires_features = False`
#   without the ClassVar annotation reads as an instance attribute and will type-error on the
#   subclass override pattern.

# GOTCHA: model bundles are joblib-pickled. `requires_features` is a *class* attribute, not an
#   instance attribute — it is NOT pickled into the bundle, so old bundles loaded after this
#   PRP transparently gain the attribute from the (new) class definition. No bundle migration.

# GOTCHA: the scenarios "empty-assumption simulation → zero delta" integration test is the
#   OLD drift detector for the duplicated contract. After consolidation the two lists ARE one
#   import, so that test still passes — and now for a structural reason, not a coincidence.
#   It must stay green; do not delete it.

# GOTCHA: line endings — this repo has mixed CRLF/LF files. Run `git diff --stat` before
#   committing; if a moved file shows a whole-file diff, normalise to the original file's
#   ending so the review shows only the real change.
```

---

## Implementation Blueprint

### Data models and structure

No ORM models, no Pydantic schemas, no migration. The only new structured types:

```python
# app/shared/feature_frames/contract.py

from enum import Enum

class FeatureSafety(Enum):
    """Leakage classification of a feature column in a FUTURE prediction frame."""
    SAFE = "safe"                 # pure function of the date (calendar) — never a leak
    CONDITIONALLY_SAFE = "cond"   # target long-lag: safe iff source day <= origin T, else NaN
    UNSAFE_UNLESS_SUPPLIED = "unsafe"  # future price/promo/inventory — knowable ONLY if the
                                  #   caller posits it (scenario assumption); never inferred

# FutureFeatureFrame — MOVED VERBATIM from scenarios/feature_frame.py:93-107 (unchanged).
@dataclass
class FutureFeatureFrame:
    dates: list[date]
    feature_columns: list[str]
    matrix: list[list[float]]     # [horizon][n_features]; NaN allowed and expected

# FEATURE_CLASS — the executable taxonomy: every canonical column → its FeatureSafety.
FEATURE_CLASS: dict[str, FeatureSafety] = {
    # lag_1 .. lag_28  -> CONDITIONALLY_SAFE
    # dow_sin/dow_cos/month_sin/month_cos/is_weekend/is_month_end -> SAFE
    # price_factor/promo_active -> UNSAFE_UNLESS_SUPPLIED
    # is_holiday -> SAFE (calendar table is a timeless attribute)
    # days_since_launch -> SAFE (pure function of date once launch_date is known)
}
```

### list of tasks (dependency-ordered)

```yaml
# ════════ STEP 1 — Shared feature-frame package ════════

Task 1 — CREATE app/shared/feature_frames/contract.py:
  - PURPOSE: the single source of truth for the regression feature-frame contract.
  - MOVE VERBATIM from app/features/scenarios/feature_frame.py:
      * EXOGENOUS_LAGS (line 65), HISTORY_TAIL_DAYS (line 68)   # NOT MAX_COMPARE_SCENARIOS
      * CALENDAR_COLUMNS (lines 74-81), EXOGENOUS_COLUMNS (lines 85-90)
      * FutureFeatureFrame dataclass (lines 93-107)
      * canonical_feature_columns() (lines 110-127)
      * _is_month_end() (lines 141-143)
      * build_calendar_columns() (lines 146-170)
      * build_long_lag_columns() (lines 173-216)
  - ADD: `FeatureSafety` Enum + `FEATURE_CLASS` dict (see Data models above).
  - ADD: `feature_safety(column: str) -> FeatureSafety` — looks up FEATURE_CLASS; for a
      `lag_*` column not literally in the map (custom lag offsets), returns CONDITIONALLY_SAFE;
      raises KeyError for a genuinely unknown column (callers must classify every column).
  - IMPORTS: stdlib only — `math`, `dataclasses`, `datetime`, `enum`, `typing`. NOTHING from
      `app.features.*`. May import `app.core.logging.get_logger` (app/core is allowed).
  - PRESERVE: every docstring on the moved functions verbatim (they carry the leakage proof).
  - VALIDATE: uv run ruff check app/shared/feature_frames/ && uv run mypy app/shared/feature_frames/contract.py && uv run pyright app/shared/feature_frames/

Task 2 — CREATE app/shared/feature_frames/__init__.py:
  - RE-EXPORT the public surface from contract.py:
      EXOGENOUS_LAGS, HISTORY_TAIL_DAYS, CALENDAR_COLUMNS, EXOGENOUS_COLUMNS,
      FutureFeatureFrame, FeatureSafety, FEATURE_CLASS, feature_safety,
      canonical_feature_columns, build_calendar_columns, build_long_lag_columns.
  - PATTERN: mirror app/shared/seeder/__init__.py — explicit `from .contract import (...)`
      plus an `__all__` tuple.
  - VALIDATE: uv run python -c "from app.shared.feature_frames import canonical_feature_columns; print(canonical_feature_columns())"

Task 3 — CREATE app/shared/feature_frames/tests/__init__.py + test_contract.py:
  - test_contract.py covers:
      * test_canonical_feature_columns_order — 4 lags, then CALENDAR_COLUMNS, then
        EXOGENOUS_COLUMNS; total length == sum. (MIRROR scenarios/tests/test_feature_frame.py:48-54.)
      * test_pinned_constants — EXOGENOUS_LAGS == (1,7,14,28), HISTORY_TAIL_DAYS == 90.
      * test_feature_class_covers_every_canonical_column — every column from
        canonical_feature_columns() has a FEATURE_CLASS entry (or feature_safety() resolves it).
      * test_calendar_columns_are_all_SAFE / test_lag_columns_are_CONDITIONALLY_SAFE.
      * test_shared_package_imports_nothing_from_features — IMPORTANT architectural test:
          walk app/shared/feature_frames/*.py source, assert no line matches
          `import app.features` or `from app.features`. (AST-walk or a simple text scan;
          mirror app/core/tests/test_strict_mode_policy.py's AST-walker style.)
      * test_build_calendar_columns_is_deterministic — same dates → identical output.
  - CONVENTION: module-level `def test_*` functions (no class), inline constants — mirror
      scenarios/tests/test_feature_frame.py. No conftest. No @pytest.mark.integration.
  - VALIDATE: uv run pytest -v -m "not integration" app/shared/feature_frames/tests/test_contract.py

Task 4 — CREATE app/shared/feature_frames/tests/test_leakage.py:
  - THIS IS A LOAD-BEARING SPEC (module docstring must say so, mirroring
      scenarios/tests/test_future_frame_leakage.py:1-6 — "this file IS the spec, never weaken
      it, AGENTS.md § Safety").
  - MOVE the calendar + long-lag leakage tests OUT of
      scenarios/tests/test_future_frame_leakage.py INTO this file (they now test shared code):
      * test_long_lag_columns_never_emit_a_future_target
      * test_long_lag_source_index_is_never_at_or_after_the_horizon
      * test_calendar_columns_ignore_the_target_series
      (the assemble/exogenous tests STAY in scenarios — see Task 7.)
  - MIRROR the disjoint value-pool idiom verbatim (scenarios/tests/test_future_frame_leakage.py:50-56):
      _HISTORY_TAIL = [1000.0 + i for i in range(90)]   # observed pool
      _FUTURE_TARGETS = {9000.0 + i for i in range(_HORIZON)}  # disjoint sentinel pool
      → any _FUTURE_TARGETS value in a cell == proven leak.
  - IMPORT the builders from app.shared.feature_frames (the new home).
  - VALIDATE: uv run pytest -v -m "not integration" app/shared/feature_frames/tests/test_leakage.py

# ════════ STEP 2 — Rewire the scenarios slice onto the shared contract ════════

Task 5 — MODIFY app/features/scenarios/feature_frame.py:
  - DELETE the moved definitions: EXOGENOUS_LAGS, HISTORY_TAIL_DAYS, CALENDAR_COLUMNS,
      EXOGENOUS_COLUMNS, FutureFeatureFrame, canonical_feature_columns, _is_month_end,
      build_calendar_columns, build_long_lag_columns.
  - KEEP: MAX_COMPARE_SCENARIOS, _in_window, build_exogenous_columns, assemble_future_frame,
      build_future_frame.
  - ADD at the top: `from app.shared.feature_frames import (EXOGENOUS_LAGS, HISTORY_TAIL_DAYS,
      CALENDAR_COLUMNS, EXOGENOUS_COLUMNS, FutureFeatureFrame, canonical_feature_columns,
      build_calendar_columns, build_long_lag_columns)` — and a `# noqa: F401` because they are
      RE-EXPORTED for back-compat (assemble_future_frame still calls build_*; the names also
      stay importable by existing call sites).
  - UPDATE the module docstring: the "feature-column contract" paragraph now points at
      `app/shared/feature_frames` as the single source of truth.
  - GOTCHA: assemble_future_frame calls build_long_lag_columns / build_calendar_columns —
      after the import they resolve to the shared functions. No logic change.
  - VALIDATE: uv run mypy app/features/scenarios/ && uv run pyright app/features/scenarios/

Task 6 — VERIFY scenarios import sites still resolve:
  - These files import from app.features.scenarios.feature_frame and rely on the re-export:
      tests/conftest.py (canonical_feature_columns), service.py (build_future_frame),
      tests/test_feature_frame.py, tests/test_future_frame_leakage.py.
  - PREFERRED: update tests/conftest.py and tests/test_feature_frame.py to import the MOVED
      names directly from `app.shared.feature_frames` (the stays-in-scenarios names —
      build_exogenous_columns, assemble_future_frame — still come from feature_frame.py).
      Keep service.py importing build_future_frame from feature_frame.py (it stays there).
  - VALIDATE: uv run pytest -v -m "not integration" app/features/scenarios/tests/test_feature_frame.py

Task 7 — MODIFY app/features/scenarios/tests/test_future_frame_leakage.py:
  - REMOVE the three calendar/long-lag tests moved to the shared test_leakage.py (Task 4).
  - KEEP every test that exercises build_exogenous_columns, assemble_future_frame, or the
      end-to-end assembled frame (those builders stay in scenarios).
  - The module docstring still declares it a load-bearing spec — its remaining scope is the
      assumption-driven exogenous columns + the assembled frame.
  - VALIDATE: uv run pytest -v -m "not integration" app/features/scenarios/tests/test_future_frame_leakage.py

# ════════ STEP 3 — Formalise the feature-aware model contract ════════

Task 9 — MODIFY app/features/forecasting/models.py:
  - ADD to BaseForecaster (class body, near `random_state`):
      `requires_features: ClassVar[bool] = False`
      with a docstring: "True when fit()/predict() REQUIRE a non-None X feature frame.
      Baseline (target-only) models leave this False; feature-aware models override to True."
  - ADD `from typing import ClassVar` to the imports if not present.
  - OVERRIDE in RegressionForecaster: `requires_features: ClassVar[bool] = True`.
  - The three baselines inherit False — no edit needed.
  - GOTCHA: ClassVar, not a plain assignment — see Known Gotchas.
  - VALIDATE: uv run mypy app/features/forecasting/models.py && uv run pyright app/features/forecasting/

Task 10 — MODIFY app/features/forecasting/service.py:
  - DELETE the local constants _REGRESSION_LAGS (line 79), _REGRESSION_HISTORY_TAIL_DAYS
      (line 77), _REGRESSION_FEATURE_COLUMNS (lines 87-99). KEEP _MIN_REGRESSION_TRAIN_ROWS
      (line 74 — a training-data threshold, not a frame-contract constant).
  - ADD: `from app.shared.feature_frames import (canonical_feature_columns, EXOGENOUS_LAGS,
      HISTORY_TAIL_DAYS, build_calendar_columns)`.
  - In _build_regression_features: replace `_REGRESSION_FEATURE_COLUMNS` with
      `canonical_feature_columns()`, `_REGRESSION_LAGS` with `EXOGENOUS_LAGS`,
      `_REGRESSION_HISTORY_TAIL_DAYS` with `HISTORY_TAIL_DAYS`. The per-row inline calendar
      math (lines 561-566) is replaced by the shared build_calendar_columns — see pseudocode.
  - In train_model: replace `if config.model_type == "regression":` with
      `model = model_factory(config, ...)` FIRST, then `if model.requires_features:`.
  - In predict(): replace `if bundle.config.model_type == "regression":` (line 348) with
      `if bundle.model.requires_features:`. Generalise the error string: "Regression models"
      → "Feature-aware models".
  - GOTCHA: canonical_feature_columns() returns the SAME 14 strings in the SAME order as the
      deleted _REGRESSION_FEATURE_COLUMNS — verify by eye against forecasting/service.py:87-99.
      A column-list test (Task 12) pins it.
  - VALIDATE: uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration" app/features/forecasting/tests/

Task 11 — CREATE app/features/forecasting/tests/test_regression_features_leakage.py:
  - LOAD-BEARING spec for the HISTORICAL training builder (_build_regression_features).
  - MIRROR featuresets/tests/test_leakage.py's sequential-value idiom: seed SalesDaily-shaped
      input where quantity is sequential, assert lag_k at row i equals quantity[i-k] exactly
      and is strictly < quantity[i] ("LEAKAGE DETECTED at row {i}" message convention).
  - Assert the SQL window guard: no feature row has a date > end_date (the cutoff/origin).
  - This is a service-level test → it needs the async DB session fixture; mark
      @pytest.mark.integration if it hits Postgres, OR factor the pure row-assembly into a
      testable helper. PREFERRED: add a small pure helper `_assemble_regression_rows(dates,
      quantities, prices, ...)` inside service.py and unit-test THAT (no DB, no marker) —
      mirrors how scenarios split pure `assemble_future_frame` from async `build_future_frame`.
  - VALIDATE: uv run pytest -v -m "not integration" app/features/forecasting/tests/test_regression_features_leakage.py

Task 12 — MODIFY app/features/forecasting/tests/test_service.py:
  - ADD: test_requires_features_flag — model_factory(NaiveModelConfig()).requires_features is
      False; same for seasonal_naive, moving_average; model_factory(RegressionModelConfig())
      .requires_features is True.
  - ADD: test_canonical_columns_match_regression_contract — assert
      canonical_feature_columns() equals the exact 14-name list the regression bundle expects
      (pins the contract after the constant deletion).
  - VALIDATE: uv run pytest -v -m "not integration" app/features/forecasting/tests/test_service.py

# ════════ STEP 4 — Backtesting guard + docs ════════

Task 13 — MODIFY app/features/backtesting/tests/test_service.py:
  - ADD ONE test (no production-code change): test_feature_aware_model_fails_loud_in_backtest
      — a backtest of a feature-aware model must raise a clear ValueError (the fold loop calls
      model.fit(y_train) target-only → RegressionForecaster.fit raises), NEVER silently run.
      This pins DECISIONS LOCKED #7 — feature-aware backtesting is loud-fail until PRP-MLZOO-B.
  - VALIDATE: uv run pytest -v -m "not integration" app/features/backtesting/tests/test_service.py

Task 14 — CREATE examples/models/feature_frame_contract.md:
  - SECTIONS:
      * Historical training frame — shape [n_observations, n_features], rows = observed days
        in [train_start, train_end], the `date <= end_date` SQL filter IS the cutoff guard,
        lag_k reads quantity[i-k] (i >= k else NaN).
      * Future prediction frame — shape [horizon, n_features], rows = T+1..T+horizon, lag_k
        reads history_tail[(j-1)-k] only when (j-1)-k < 0 else NaN, NO recursion in v1.
      * The canonical column set — the 14 columns, the order, where they come from (cite
        app/shared/feature_frames).
      * Feature-class taxonomy — the SAFE / CONDITIONALLY_SAFE / UNSAFE_UNLESS_SUPPLIED table,
        one row per column, "how to populate / leakage trap" (mirror the table in
        PRPs/ai_docs/exogenous-regressor-forecasting.md §2).
      * The NaN-as-unknown rule (DECISIONS LOCKED #6) — builders never fabricate defaults.
      * How a future advanced model plugs in — set requires_features=True, reuse the shared
        builders; backtesting is loud-fail until PRP-MLZOO-B.
  - VALIDATE: test -f examples/models/feature_frame_contract.md

Task 15 — MODIFY examples/models/model_interface.md:
  - ADDITIVE only: document the `requires_features` class attribute on the BaseForecaster
      interface; add a `regression` row to the Model Configurations / Model Formulas sections;
      add a one-line pointer to examples/models/feature_frame_contract.md.
  - Do NOT rewrite the file; do NOT "fix" the ModelBundle drift noted in research (out of scope).
  - VALIDATE: uv run ruff check . && uv run ruff format --check .
```

### Per-task pseudocode (critical details only)

```python
# ── Task 1 — contract.py: the moved long-lag builder is the leakage core ──
# MOVE VERBATIM. Shown here ONLY so you can confirm it arrived unchanged.
def build_long_lag_columns(history_tail, horizon, lags=EXOGENOUS_LAGS):
    tail_len = len(history_tail)
    columns = {}
    for lag in lags:
        column = []
        for j in range(1, horizon + 1):
            idx = (j - 1) - lag                       # <-- the leakage guard
            if idx < 0 and -tail_len <= idx:          # idx<0 => source day <= origin T
                column.append(float(history_tail[idx]))
            else:
                column.append(math.nan)               # future target => NaN, never recursion
        columns[f"lag_{lag}"] = column
    return columns

# ── Task 1 — the new taxonomy ──
FEATURE_CLASS = {
    **{f"lag_{k}": FeatureSafety.CONDITIONALLY_SAFE for k in EXOGENOUS_LAGS},
    "dow_sin": FeatureSafety.SAFE, "dow_cos": FeatureSafety.SAFE,
    "month_sin": FeatureSafety.SAFE, "month_cos": FeatureSafety.SAFE,
    "is_weekend": FeatureSafety.SAFE, "is_month_end": FeatureSafety.SAFE,
    "is_holiday": FeatureSafety.SAFE,            # calendar table = timeless attribute
    "days_since_launch": FeatureSafety.SAFE,     # pure fn of date once launch_date known
    "price_factor": FeatureSafety.UNSAFE_UNLESS_SUPPLIED,
    "promo_active": FeatureSafety.UNSAFE_UNLESS_SUPPLIED,
}

def feature_safety(column: str) -> FeatureSafety:
    if column in FEATURE_CLASS:
        return FEATURE_CLASS[column]
    if column.startswith("lag_"):                # custom lag offset
        return FeatureSafety.CONDITIONALLY_SAFE
    raise KeyError(f"Unclassified feature column: {column!r}")

# ── Task 3 — the architectural-invariant test ──
def test_shared_package_imports_nothing_from_features():
    """app/shared/** is leaf-level — it may never import a vertical slice."""
    pkg_dir = Path(__file__).resolve().parents[1]   # app/shared/feature_frames/
    for py_file in pkg_dir.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.features"), (
                    f"ARCHITECTURE BREACH: {py_file} imports {node.module}"
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("app.features"), ...

# ── Task 10 — train_model: branch on the model, not on a string ──
async def train_model(self, db, store_id, product_id, train_start, train_end, config):
    # PATTERN: build the model first (cheap, no fit), then branch on its capability.
    model = model_factory(config, random_state=self.settings.forecast_random_seed)
    extra_metadata: dict[str, object] = {}
    if model.requires_features:                              # was: config.model_type == "regression"
        features = await self._build_regression_features(db, store_id, product_id,
                                                          train_start, train_end)
        model.fit(features.y, features.X)
        n_observations = features.n_observations
        extra_metadata = {"feature_columns": features.feature_columns,
                          "history_tail": features.history_tail,
                          "history_tail_dates": features.history_tail_dates,
                          "launch_date": features.launch_date_iso}
    else:
        training_data = await self._load_training_data(db, store_id, product_id,
                                                       train_start, train_end)
        if training_data.n_observations == 0:
            raise ValueError(f"No training data found for store={store_id} ...")
        model.fit(training_data.y)
        n_observations = training_data.n_observations
    # ... bundle creation, save, TrainResponse — UNCHANGED below this line.

# ── Task 10 — predict(): generalise the rejection condition ──
    bundle = load_model_bundle(resolved_path)
    # ... store/product validation unchanged ...
    if bundle.model.requires_features:                       # was: bundle.config.model_type == "regression"
        raise ValueError(
            "Feature-aware models forecast through POST /scenarios/simulate, which supplies "
            "the exogenous feature frame. POST /forecasting/predict does not support them."
        )

# ── Task 10 — _build_regression_features: consume the shared contract ──
#   The DB reads (sales, calendar holidays, promotions, launch_date) are UNCHANGED.
#   Replace the per-row inline calendar math with the shared column builder, and the
#   local constants with the shared ones:
    feature_columns = canonical_feature_columns()            # was list(_REGRESSION_FEATURE_COLUMNS)
    calendar_cols = build_calendar_columns(dates)            # shared; replaces lines 561-566
    rows = []
    for index, day in enumerate(dates):
        row = []
        for lag in EXOGENOUS_LAGS:                           # was _REGRESSION_LAGS
            row.append(quantities[index - lag] if index >= lag else math.nan)
        for name in CALENDAR_COLUMNS:                        # imported from shared
            row.append(calendar_cols[name][index])
        row.append(prices[index] / baseline_price)           # price_factor — DB-observed
        row.append(1.0 if day in promo_dates else 0.0)
        row.append(1.0 if day in holiday_dates else 0.0)
        row.append(float((day - launch_date).days) if launch_date else math.nan)
        rows.append(row)
    tail = quantities[-HISTORY_TAIL_DAYS:]                    # was _REGRESSION_HISTORY_TAIL_DAYS
    # CRITICAL: the column ORDER above (lags, calendar, price_factor, promo_active,
    # is_holiday, days_since_launch) MUST equal canonical_feature_columns() — Task 12 pins it.
```

### Integration Points

```yaml
PACKAGE WIRING:
  - app/shared/feature_frames/ is a pure library — NO router, NO app/main.py change.
  - It is imported by: app/features/scenarios/feature_frame.py and
    app/features/forecasting/service.py (both directions are app/features -> app/shared, which
    is the allowed direction).

CONFIG:
  - No new settings. `forecast_random_seed` (config.py, default 42) is still the determinism
    source. EXOGENOUS_LAGS / HISTORY_TAIL_DAYS are code constants, not settings (matches the
    PRP-27 precedent — they were code constants in feature_frame.py).

PERSISTENCE:
  - ModelBundle is UNTOUCHED. `feature_columns` in bundle metadata is still a list[str]; the
    strings are identical (canonical_feature_columns() == the deleted _REGRESSION_FEATURE_COLUMNS).
  - `requires_features` is a class attribute — not pickled — so bundles trained before this PRP
    load cleanly and gain the attribute from the new class definition.

NO MIGRATION: this PRP touches no SQLAlchemy model and no Alembic version.
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . --fix && uv run ruff format --check .
# Expected: no errors. Fix everything before Level 2.
```

### Level 2: Type Checks

```bash
uv run mypy app/        # --strict; gates merge
uv run pyright app/     # --strict; gates merge
# Expected: clean. Watch for: ClassVar annotation on requires_features; the F401 re-export
# in scenarios/feature_frame.py needs a `# noqa: F401` (ruff), not a type ignore.
```

### Level 3: Unit Tests

```bash
# New + moved tests
uv run pytest -v -m "not integration" app/shared/feature_frames/tests/
uv run pytest -v -m "not integration" app/features/forecasting/tests/test_regression_features_leakage.py

# Regression — the slices this PRP rewired MUST stay green unchanged
uv run pytest -v -m "not integration" app/features/forecasting/tests/
uv run pytest -v -m "not integration" app/features/scenarios/tests/
uv run pytest -v -m "not integration" app/features/backtesting/tests/

# Whole fast suite
uv run pytest -v -m "not integration"
# Expected: all green. The baseline-forecaster tests and test_regression_forecaster.py must
# pass with ZERO edits — if one fails, the consolidation changed behaviour (it must not).
```

### Level 4: Integration Tests + Contract Drift

```bash
docker compose up -d && uv run alembic upgrade head
uv run pytest -v -m integration app/features/scenarios/ app/features/forecasting/
# CRITICAL: the scenarios "empty-assumption model_exogenous simulation -> zero delta" test is
# the old drift detector for the duplicated contract. It MUST stay green — now structurally,
# because both slices import the one shared column list.
# No migration in this PRP -> no `alembic downgrade` round-trip needed.
```

### Level 5: Manual Validation (dogfood — REQUIRED)

```bash
# 1. Shared package wires up
uv run python -c "from app.shared.feature_frames import canonical_feature_columns, FeatureSafety, feature_safety; \
cols = canonical_feature_columns(); assert len(cols) == 14; \
assert all(feature_safety(c) for c in cols); print('contract OK:', cols)"

# 2. The duplicated constant is GONE
grep -rn "_REGRESSION_FEATURE_COLUMNS\|_REGRESSION_LAGS\|_REGRESSION_HISTORY_TAIL_DAYS" app/ \
  && echo "FAIL: duplicate still present" || echo "OK: single source of truth"

# 3. requires_features is correct on every forecaster
uv run python -c "
from app.features.forecasting.models import (NaiveForecaster, SeasonalNaiveForecaster, \
MovingAverageForecaster, RegressionForecaster);
assert NaiveForecaster.requires_features is False;
assert SeasonalNaiveForecaster.requires_features is False;
assert MovingAverageForecaster.requires_features is False;
assert RegressionForecaster.requires_features is True;
print('requires_features OK')"

# 4. End-to-end behaviour unchanged — train a regression model and run a model_exogenous
#    scenario; confirm it still produces a comparison (start backend first):
#    uv run uvicorn app.main:app --port 8123 &
#    curl -sX POST localhost:8123/forecasting/train -H 'Content-Type: application/json' \
#      -d '{"store_id":1,"product_id":1,"train_start_date":"2024-01-01",
#           "train_end_date":"2024-06-01","config":{"model_type":"regression"}}'
#    -> 200; then POST /scenarios/simulate with that run_id -> method "model_exogenous".
```

---

## Final Validation Checklist

- [ ] `uv run ruff check .` and `uv run ruff format --check .` clean.
- [ ] `uv run mypy app/` and `uv run pyright app/` clean (both --strict).
- [ ] `uv run pytest -v -m "not integration"` fully green.
- [ ] `uv run pytest -v -m integration app/features/scenarios/ app/features/forecasting/` green — including the empty-assumption zero-delta test.
- [ ] `grep -rn "_REGRESSION_FEATURE_COLUMNS" app/` returns nothing.
- [ ] `app/shared/feature_frames/tests/test_contract.py::test_shared_package_imports_nothing_from_features` passes.
- [ ] `app/shared/feature_frames/tests/test_leakage.py` and `app/features/forecasting/tests/test_regression_features_leakage.py` exist, carry the load-bearing-spec docstring, and pass.
- [ ] Baseline-forecaster tests and `test_regression_forecaster.py` pass with **no edits**.
- [ ] `examples/models/feature_frame_contract.md` exists and documents both frame shapes + the taxonomy; `examples/models/model_interface.md` updated additively.
- [ ] `git diff --stat` shows only the intended files — no whole-file CRLF/LF noise diffs.
- [ ] No new dependency in `pyproject.toml`; no Alembic migration; no route/schema/WebSocket change.
- [ ] An OPEN GitHub issue exists for this work (`gh issue view <N> --json state` → `OPEN`); commit `feat(forecast): feature-aware forecasting foundation — shared feature-frame contract (#<issue>)`; branch `feat/feature-aware-forecasting-foundation` off `dev`.

---

## Anti-Patterns to Avoid

- ❌ Don't implement LightGBM, XGBoost, Prophet, or any new model — that is PRP-MLZOO-B+ (INITIAL-MLZOO-index.md). This PRP is contracts + tests + docs only.
- ❌ Don't add a `FeatureAwareForecaster` base class — DECISIONS LOCKED #2 chose the `requires_features` attribute.
- ❌ Don't introduce a `TrainingFrame` dataclass nothing returns — DECISIONS LOCKED #4 (dead code; product-vision.md forbids speculative abstraction).
- ❌ Don't change `POST /forecasting/predict` behaviour — it still rejects feature-aware models (DECISIONS LOCKED #3).
- ❌ Don't "tidy up" `build_long_lag_columns` while moving it — move it byte-for-byte; the `idx = (j-1)-k` guard is the leakage spec.
- ❌ Don't weaken or delete an assertion in any `*_leakage.py` file — AGENTS.md § Safety. Splitting tests across the module move is fine; dropping coverage is not.
- ❌ Don't let `app/shared/feature_frames/` import from `app/features/**` — it is leaf-level; a test enforces it.
- ❌ Don't silently zero-fill an unknown feature cell — emit `math.nan` (DECISIONS LOCKED #6).
- ❌ Don't add an Alembic migration or touch `ModelBundle` — persistence is untouched.
- ❌ Don't wire feature-aware backtesting — DECISIONS LOCKED #7; loud-fail + a guard test is the deliverable here.

## Open Questions — ALL RESOLVED

The three "Required decisions" in INITIAL-MLZOO-A were resolved during planning and are
recorded as DECISIONS LOCKED #1 (contract home → `app/shared/feature_frames/`), #2 (no
`FeatureAwareForecaster` class → `requires_features` attribute), and #3 (`/forecasting/predict`
unchanged). #4–#7 record the derived decisions (no `TrainingFrame`, builders move by import,
NaN-as-unknown, backtesting loud-fail). Nothing is left to litigate at implementation time.

## Confidence Score

**8 / 10** for one-pass implementation success.

Rationale: this is a consolidation-and-test PRP with no new dependency, no migration, no API
change, and no new algorithm — the highest-confidence PRP class. The feature-frame machinery
already exists and is well-tested; the work is moving pure functions into `app/shared/`,
swapping a string check for a class attribute, and adding leakage tests that mirror an
existing, proven idiom. The −2 risk is entirely in **import-update completeness**: 6+ sites
import from `scenarios/feature_frame.py`, and the `_build_regression_features` calendar
refactor (row-major inline math → shared column builder) must reproduce the exact 14-column
order. Both risks are caught fast — by `mypy`/`pyright` (unresolved imports) and by the Task 12
column-order test plus the scenarios zero-delta integration test. Following the per-task
pseudocode and the Level 3 "baselines must pass unedited" gate makes a regression hard to miss.
