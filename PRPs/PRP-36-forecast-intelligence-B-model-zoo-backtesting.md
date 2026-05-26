name: "PRP-36 — Forecast Intelligence B: Model Zoo + Backtesting"
description: |
  Promote ForecastLabAI's model layer from "a regression model + 3 baselines"
  to a disciplined model zoo with fair, leakage-safe comparison. Slice B of the
  Forecast Intelligence roadmap
  (`PRPs/INITIAL/INITIAL-forecast-intelligence-index.md`). Slice A (PRP-35 —
  Feature Frame V2) is a HARD PREREQUISITE; Slice C (PRP-37 — Interactive UI)
  is the downstream consumer of every contract added here.

  > **PREREQUISITE — HARD DEPENDENCY ON PRP-35.**
  > This PRP MUST NOT execute until PRP-35 (Feature Frame V2) is merged to
  > `dev`. The V2 contract — `feature_frame_version`, `feature_columns`,
  > `feature_groups`, `feature_safety_classes`, `feature_pinned_constants`
  > in `ModelBundle.metadata`, plus `TrainRequest.feature_frame_version` /
  > `feature_groups` — is the load-bearing surface this PRP plugs into.
  > Task 1 below is a Contract Refresh gate that verifies PRP-35 actually
  > landed and patches any drift between the field names this PRP cites
  > and what PRP-35 ultimately shipped. **DO NOT start Task 2 if Task 1
  > flags drift; resolve the drift first.**

## Purpose
A one-pass implementation contract for an AI agent (or human) with access to
the codebase but no prior session context. Land richer baselines, sharper
metrics, feature-frame-aware backtests, comparable-run logic for registry +
ops, and full explainability metadata — all without weakening any of the four
load-bearing leakage specs and without modifying the V1 builders (frozen by
PRP-35).

## Core Principles
1. **PRP-35 is the contract.** V2 surface — `FeatureGroup` enum, the V2 builders,
   `bundle.metadata.feature_frame_version`, `TrainRequest.feature_frame_version`
   — is imported as-is. This PRP NEVER redefines, extends, or shadows it.
2. **`fit(y, X=None)` / `predict(horizon, X=None)` is the only forecaster
   contract.** Every new model class implements `BaseForecaster` exactly,
   sets `requires_features` correctly, and is dispatched through `model_factory`.
3. **Leakage safety is the central design constraint.** The four load-bearing
   leakage specs MUST stay byte-stable. New backtesting code dispatches via
   `bundle.metadata.feature_frame_version` (the seam PRP-35 already built);
   it never weakens a leakage assertion to fit a new model in.
4. **Deterministic by default.** Every new model takes a `random_state`,
   respects `forecast_random_seed`, runs single-threaded (`n_jobs=1` /
   `nthread=1`) when the library has thread-nondeterminism. No stochastic
   sampling unless explicitly configured AND reproducible.
5. **Comparable-run discipline.** Champion/challenger and stale-alias
   detection MUST require: same `(store_id, product_id)` grain AND
   overlapping `data_window_*` AND same `feature_frame_version`. A run with
   a different feature_frame_version is NOT comparable — promoting one
   would silently change the contract the alias points at.
6. **HGBR has no `feature_importances_`.** Verified at runtime (see "Known
   Gotchas"). The existing `FeatureImportanceUnavailableError` keeps this
   honest; this PRP does not relitigate it. New tree models
   (`random_forest` if added) DO expose `feature_importances_` and use it.
7. **Optional extras stay opt-in.** `lightgbm` and `xgboost` are off in the
   default environment. New optional model `random_forest` uses
   `scikit-learn` (already a core dep) so it can ship without a new extra.

---

## Goal

Deliver, on branch `feat/forecast-model-zoo-and-backtesting`, an end-to-end
disciplined model zoo against the V2 feature contract that PRP-35 lands:

- New target-only baseline models `weighted_moving_average` and
  `seasonal_average` (always-on); `trend_regression_baseline` OPTIONAL but
  scoped here; `random_forest` OPTIONAL feature-aware model (pure-sklearn).
- Conservative, deterministic config tightening for existing feature-aware
  models (`regression`, `prophet_like`, `lightgbm`, `xgboost`) — no new
  classes, no behavioural surprise for in-flight bundles.
- Backtesting that:
  - Compares baselines AND feature-aware models on identical fold boundaries;
  - Routes each fold to the V1 or V2 row builder via `bundle.metadata.
    feature_frame_version` (dispatch already added by PRP-35 Task 13);
  - Returns `RMSE` alongside MAE / sMAPE / WAPE / bias;
  - Returns per-horizon-bucket metrics (`h_1_7`, `h_8_14`, `h_15_28`, `h_29+`).
- Registry + ops that:
  - Persist `feature_frame_version` + `feature_groups` to every new
    `model_run.runtime_info`, AND surface them on `RunResponse` /
    `RunDetailResponse`;
  - Restrict the "comparable run" predicate to `(grain, overlapping
    data_window, same feature_frame_version)`;
  - Mark a stale-alias reason `feature_frame_version_mismatch` when the
    alias's run is V1 but a newer comparable V2 SUCCESS run exists (and
    vice versa).
- Explainability that:
  - Recognises every new model_type in `_MODEL_FAMILY_MAP`;
  - Preserves the additive decomposition for `prophet_like`;
  - Preserves simple arithmetic explanations for baselines;
  - Exposes `feature_importances_` for `random_forest` (when added) — never
    cites it for HGBR.
- Artifact hash verification intact (no change to `bundle_hash` flow).
- All five validation gates green.

## Why

Today the model zoo is heavily backloaded onto the four feature-aware models;
the three target-only baselines are weak comparators (`naive` =
last-observation, `seasonal_naive` = single-cycle copy, `moving_average` =
flat mean). After PRP-35 unlocks 25+ richer V2 columns, planners need:

- Stronger baselines (so "extra complexity is justified" actually means
  something).
- Per-horizon metrics (a model that wins WAPE on h=1..7 but loses on h=29+
  is a different operational tool than one that's even across the horizon).
- A way to compare same-grain same-window runs across feature_frame_version
  without accidentally promoting a V1 alias over a V2 challenger.
- Honest feature-importance plumbing — including the "feature importance is
  unavailable for HGBR; use permutation_importance" path PRP-31 / issue
  #258 added — so Slice C's UI never invents a number that doesn't exist.

## What

### User-visible behaviour

- `POST /forecasting/train` accepts new `model_type` values:
  `weighted_moving_average`, `seasonal_average` (always), and OPTIONALLY
  `trend_regression_baseline`, `random_forest`.
- `POST /forecasting/predict` still rejects feature-aware models without `X`
  (no change to that contract).
- `POST /backtesting/run` returns:
  - The existing aggregate metrics (MAE, sMAPE, WAPE, bias, stability) PLUS
    `rmse`.
  - A NEW per-fold `horizon_bucket_metrics: dict[str, dict[str, float]]`
    block keyed by bucket id (`h_1_7`, `h_8_14`, `h_15_28`, `h_29+`) with
    the same metric names inside each bucket.
- `GET /registry/runs/{run_id}` exposes
  `feature_frame_version` + `feature_groups` on the response (additive —
  optional fields, default to V1 when absent).
- `GET /ops/model-health` and the stale-alias view classify a champion
  alias as `stale` with `reason=feature_frame_version_mismatch` when a
  newer comparable SUCCESS run on a different feature_frame_version exists.
- `GET /explain/runs/{run_id}` works for every NEW baseline (simple
  arithmetic explanation) AND for `random_forest` (tree feature
  importances).

### Technical requirements

- Pydantic v2 strict mode on every new request schema
  (`ConfigDict(strict=True)` + `Field(strict=False, ...)` for
  date / datetime / UUID / Decimal — see `docs/_base/SECURITY.md` §
  "Pydantic v2 strict mode on FastAPI request bodies"). Enforced by the
  AST-walker invariant in `app/core/tests/test_strict_mode_policy.py`.
- All new SQL uses SQLAlchemy 2.0 parameter binding.
- All five validation gates pass: `ruff check` + `ruff format --check` +
  `mypy --strict` + `pyright --strict` + `pytest -m "not integration"` +
  `pytest -m integration`.
- No new Alembic migration (verified by `alembic check`): feature
  metadata rides in existing JSONB columns (`model_run.runtime_info`,
  `model_run.metrics`).
- No new endpoint paths — existing endpoints gain additive optional fields.
- No managed-cloud SDK introduced. No AutoML. No hyperparameter sweep.

### Success Criteria

- [ ] Contract Refresh (Task 1) succeeds: the V2 symbols PRP-35 promised
  ALL import cleanly, AND every field name this PRP assumes matches what
  PRP-35 actually shipped.
- [ ] `weighted_moving_average` model trains, predicts, persists, loads.
- [ ] `seasonal_average` model trains, predicts, persists, loads.
- [ ] If included: `trend_regression_baseline` trains/predicts/persists/loads.
- [ ] If included: `random_forest` trains/predicts/persists/loads AND
  exposes `feature_importances_` through `extract_feature_importance`.
- [ ] `BacktestResponse.main_model_results.fold_results[*]` carries a
  `horizon_bucket_metrics` block; baseline AND feature-aware backtests
  run on identical folds and return mutually-comparable summaries.
- [ ] `BacktestResponse.main_model_results.aggregate_metrics` carries
  `rmse` alongside the existing four metrics.
- [ ] Backtesting routes V1 bundles through the V1 builder path and V2
  bundles through the V2 builder path — the dispatch PRP-35 Task 13
  added — and a V2 fold's `X_future` matches the V2 column count from
  `bundle.metadata.feature_columns`.
- [ ] V2 leakage spec at the backtesting layer
  (`app/features/backtesting/tests/test_feature_aware_backtest_v2.py`,
  introduced by PRP-35) stays green; this PRP adds NO weakening edits.
- [ ] `RegistryService._find_duplicate` includes
  `feature_frame_version` in its match key (an existing V1 run is NOT a
  duplicate of a new V2 run with the same other fields).
- [ ] `RegistryService.create_alias` keeps the "run.status == SUCCESS"
  precondition; aliases on V1 runs continue to work.
- [ ] `OpsService` comparable-run selection requires same grain, overlapping
  data window, AND same feature_frame_version.
- [ ] A V1 alias whose grain has a newer V2 SUCCESS run reports
  `is_stale=true, reason=feature_frame_version_mismatch`.
- [ ] `_MODEL_FAMILY_MAP` covers every new model_type; unknown family
  fallback path (existing) untouched.
- [ ] `extract_feature_importance` accepts the new feature-aware class
  (when `random_forest` added) and returns a 1-D importance vector of
  shape `(len(feature_columns),)`. HGBR remains the only feature-aware
  class that raises `FeatureImportanceUnavailableError`.
- [ ] `app/features/explainability` builds simple arithmetic explanations
  for every new baseline (the same shape it already builds for `naive`,
  `seasonal_naive`, `moving_average`).
- [ ] All five validation gates green.
- [ ] All four load-bearing leakage specs unchanged.
- [ ] `uv run alembic check` — no new migration.
- [ ] An `examples/forecasting/model_zoo_compare.py` script runs against
  the local seeded DB and prints a per-model metrics table.

---

## All Needed Context

### Documentation & References

```yaml
# ─── PRP-35 SURFACE — load first; everything downstream depends on it ────
- file: PRPs/PRP-35-forecast-intelligence-A-feature-frame-v2.md
  why: The V2 contract. This PRP imports `FeatureGroup`, the V2 builders, and the bundle.metadata fields PRP-35 added.

- file: app/shared/feature_frames/contract_v2.py        # CREATED BY PRP-35
  why: Source of FEATURE_FRAME_VERSION_V2, FeatureGroup, DEFAULT_V2_GROUPS, v2_column_manifest, v2_feature_groups_dict, v2_feature_safety_classes.

- file: app/shared/feature_frames/rows_v2.py            # CREATED BY PRP-35
  why: build_historical_feature_rows_v2 / build_future_feature_rows_v2.

- file: app/features/forecasting/v2_loaders.py          # CREATED BY PRP-35
  why: async sidecar loaders for inventory / replenishment / returns / exogenous / promotion / lifecycle. Reused by the model_zoo backtest path; never duplicated.

# ─── Forecasting model layer ────────────────────────────────────────────
- file: app/features/forecasting/models.py
  why: BaseForecaster (L109 `requires_features` ClassVar, L129 fit, L148 predict). NaiveForecaster L196, SeasonalNaiveForecaster L281, MovingAverageForecaster L384, RegressionForecaster L483 (HistGradientBoostingRegressor), LightGBMForecaster L625 (lazy import L706), XGBoostForecaster L787 (lazy import L870), ProphetLikeForecaster L950 (Ridge pipeline; `decompose()` L1069). `model_factory(config, random_state)` L1138-1227 (if-elif dispatch; lightgbm gate L1178, xgboost gate L1193). New model classes mirror the existing pattern.

- file: app/features/forecasting/schemas.py
  why: ModelConfigBase L23-51 (frozen=True; `config_hash()` L43-50). NaiveModelConfig L53, SeasonalNaiveModelConfig L66, MovingAverageModelConfig L87, LightGBMModelConfig L108, XGBoostModelConfig L148, RegressionModelConfig L191, ProphetLikeModelConfig L236. `ModelConfig` discriminated union L268-276 (discriminator=`model_type`). TrainRequest L284. FeatureMetadataResponse L462. ModelFamily enum L422-435.

- file: app/features/forecasting/feature_metadata.py
  why: `_MODEL_FAMILY_MAP` L42-50 — must be extended with every new model_type. `model_family_for(model_type)` L53-69 logs a warning and defaults BASELINE for unknowns (forward-compat, but every NEW model_type added here MUST appear in the map to avoid the warning in CI). `FeatureImportanceUnavailableError` L72-83 — the HGBR-specific 422 path; NEVER weaken. `importance_type_for(model)` L86-108. `extract_feature_importance(model, feature_columns)` L111-228 — sklearn imputer realignment for ProphetLike L169-200 (per memory `simpleimputer-drops-empty-columns`).

- file: app/features/forecasting/persistence.py
  why: ModelBundle dataclass L31-76 (metadata: dict[str, object] — additive; no schema change for any new field). save_model_bundle L78-133 (auto-populates created_at, sklearn/lightgbm/xgboost versions, bundle_hash). load_model_bundle L136-235 (path-traversal guard L157-171; version-mismatch warnings L178-226).

- file: app/features/forecasting/service.py
  why: ForecastingService.train_model L201 — branches on `requires_features` L244 and dispatches to V1 or V2 builder per PRP-35 Task 9. `_assemble_regression_rows` L132-182 (delegates to `build_historical_feature_rows`). `RegressionFeatureMatrix` L109-130. Constant `_MIN_REGRESSION_TRAIN_ROWS = 30` at L99. New target-only models bypass the feature-build branch entirely.

- file: app/features/forecasting/routes.py
  why: POST /forecasting/train handler ~L55-145 — flag-gates LightGBM and XGBoost (`forecast_enable_lightgbm` / `forecast_enable_xgboost`). New baselines do NOT need flag-gates. `random_forest` (if added) is an additional pure-sklearn model — no gate.

# ─── Backtesting layer ──────────────────────────────────────────────────
- file: app/features/backtesting/service.py
  why: BacktestingService.run_backtest L213 — validates config L240, loads series data L259, branches on `requires_features` L280, calls `_load_exogenous_frame()` L281. The V1 builder calls live at L493 (build_historical_feature_rows) and L553 (build_future_feature_rows) — PRP-35 Task 13 already added the V1/V2 dispatch around those sites. ExogenousFrame L65-87. `_MIN_FEATURE_AWARE_TRAIN_ROWS = 30` L61. Imports `build_historical_feature_rows`, `build_future_feature_rows` from `app.shared.feature_frames` at L46-50.

- file: app/features/backtesting/metrics.py
  why: MetricsCalculator with `mae` L57, `smape` L90, `wape` L148, `bias` L195, `stability_index` L242, `calculate_all` L294, `aggregate_fold_metrics` L315. `EPSILON = 1e-10` L54. **RMSE does NOT exist today** — added by this PRP. Per-horizon-bucket metrics do NOT exist today — added by this PRP.

- file: app/features/backtesting/schemas.py
  why: BacktestRequest L198-231. BacktestResponse L233-259 (`main_model_results`, `baseline_results`, `comparison_summary`, `leakage_check_passed`). FoldResult L147-165 (`fold_index`, `split: SplitBoundary`, `dates`, `actuals`, `predictions`, `metrics: dict[str, float]`). New per-horizon-bucket field is added to FoldResult and reflected in the aggregate.

# ─── Registry / Ops ─────────────────────────────────────────────────────
- file: app/features/registry/models.py
  why: ModelRun ORM L51-142 (run_id 32-char hex UUID; status RunStatus enum L36-49; `model_config` JSONB; `feature_config` JSONB nullable; `data_window_start/end`; `metrics` JSONB; `runtime_info` JSONB — feature_frame_version + feature_groups ride here). DeploymentAlias ORM L145-168.

- file: app/features/registry/service.py
  why: RegistryService.create_run L183-261. update_run L357-419. **_find_duplicate L629-672 — TODAY MATCHES ON (config_hash, store_id, product_id, data_window_start, data_window_end) ONLY.** This PRP extends the match key with feature_frame_version. create_alias / update_alias L421-495 (status == SUCCESS precondition — preserved). list_aliases L534-565.

- file: app/features/registry/schemas.py
  why: RunResponse / RunDetailResponse L118-167 — exposes `model_config_data`, `feature_config`, `config_hash`, `data_window_*`, `metrics`, `artifact_*`, `runtime_info`, `error_message`, timestamps. **TODAY DOES NOT EXPOSE feature_frame_version OR feature_groups** — added by this PRP as additive optional fields.

- file: app/features/ops/service.py
  why: Stale-alias detection `_alias_staleness(run, latest_success_by_grain)` L137-159 — currently stale iff `run.status != SUCCESS OR newer SUCCESS run exists for same (store_id, product_id)`. **TODAY READS ZERO FEATURE METADATA.** This PRP extends the comparable-run selection (L412-427) AND the staleness rule to honour feature_frame_version. Model-health classification `drift_direction ∈ {degrading, improving, stable, unknown}` L464-543 (rank map L534).

- file: app/features/ops/routes.py
  why: GET /ops/model-health and GET /ops/stale-aliases handlers — additive response fields, no path change.

# ─── Explainability ─────────────────────────────────────────────────────
- file: app/features/explainability/service.py
  why: TODAY HANDLES BASELINE ONLY (naive, seasonal_naive, moving_average). `explainer_factory` L205 rejects feature-aware with 400. Baseline explainers produce simple arithmetic explanations (last-value, season mean, moving-avg). New baselines MUST get explainers in the same shape.

- file: app/features/explainability/explainers.py
  why: Individual baseline explainer classes — pattern for new ones. Drives `ForecastExplanation` shape from `schemas.py`.

- file: app/features/explainability/reason_codes.py
  why: Retail signal warnings (correlation, not causation). Untouched by this PRP — preserved verbatim.

# ─── Configuration ──────────────────────────────────────────────────────
- file: app/core/config.py
  why: forecast_random_seed L97 (=42); forecast_default_horizon L98 (=14); forecast_max_horizon L99 (=90); forecast_model_artifacts_dir L100; forecast_enable_lightgbm L101 (=False); forecast_enable_xgboost L102 (=False). No new keys needed; `forecast_enable_random_forest` is OPTIONAL — only add it if `random_forest` ships in this PRP. Per the rule, it defaults False.

- file: pyproject.toml
  why: `[project.optional-dependencies]` L34-50 — `ml-lightgbm = ["lightgbm>=4.5.0"]` L47, `ml-xgboost = ["xgboost>=2.1.0"]` L50. NO new extra needed for `random_forest` (uses sklearn, already a core dep). NO new extra for the new baselines (pure numpy / stdlib).

# ─── Rules ──────────────────────────────────────────────────────────────
- file: docs/_base/RULES.md
  why: Never weaken leakage specs; never edit a merged migration; never widen agent mutation surface; never `git push --force`. None violated by this PRP.

- file: .claude/rules/test-requirements.md
  why: Every new model class + new metric + new schema field ships with a unit test; every new endpoint behavior ships with a route test; every bug fix ships a regression test.

- file: .claude/rules/commit-format.md
  why: Commit scope must match the dominant touched area. This PRP touches forecast / backtest / registry / ops / explainability — use a comma-pair scope: `feat(forecast,backtest): …` for the model + metrics work, `feat(registry,ops): …` for the comparability work, `feat(forecast,api): …` if the response shape changes hit the API surface. Each commit MUST reference the tracking issue.

# ─── Library / API references (load on demand) ──────────────────────────
- url: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html
  section: "Parameters" + "Attributes"
  critical: `n_estimators` default 100; `random_state` and `n_jobs=1` for deterministic fits; `feature_importances_` is the 1-D Gini importance vector (verified — shape `(n_features,)`).

- url: https://scikit-learn.org/stable/modules/generated/sklearn.inspection.permutation_importance.html
  section: "Notes"
  critical: The documented replacement for "tree models without feature_importances_". HGBR explainability uses this (or — if too slow — punts to the existing FeatureImportanceUnavailableError). DO NOT add permutation_importance behind /explain in this PRP; the existing 422 path is the contract until a separate PRP funds the compute budget.

- url: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
  section: "Notes"
  critical: Existing splitter is already gap-aware (see `app/features/backtesting/splitter.py`). No change to the splitter; only the per-fold metric output.

- url: https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.LGBMRegressor.html
  section: "Parameters" + "Attributes"
  critical: `deterministic=True` + `n_jobs=1` + `seed=random_state` for bit-reproducible fits. Library is OPT-IN (`pyproject.toml` extra); see "Known Gotchas" for the find_spec guard.

- url: https://xgboost.readthedocs.io/en/stable/python/python_api.html#xgboost.XGBRegressor
  section: "Parameters"
  critical: `tree_method="hist"` (deterministic) + `n_jobs=1` + `random_state=random_state` + `verbosity=0`. Library is OPT-IN.

- url: https://facebook.github.io/prophet/docs/seasonality%2C_holiday_effects%2C_and_regressors.html
  section: "Additional regressors"
  critical: Vocabulary inspiration only — the in-repo ProphetLikeForecaster is a Ridge additive pipeline, NOT real Prophet. `decompose()` returns the trend / seasonality / regressor components from the Ridge coefficients (`app/features/forecasting/models.py:1069`).

- url: https://unit8co.github.io/darts/userguide/covariates.html
  section: "Past vs Future Covariates"
  critical: Useful framing for the per-horizon-bucket metric labels in Slice C. Not loaded at runtime here.

- url: https://nixtlaverse.nixtla.io/statsforecast/src/core/models.html
  section: "WeightedAverage" + "SeasonalAverage"
  critical: Vocabulary alignment — `weighted_moving_average` and `seasonal_average` are not novel; pin the existing nomenclature in docstrings.

# ─── Memory anchors (load on conflict) ──────────────────────────────────
- memory: histgbr-no-feature-importances
  why: HGBR has no `feature_importances_` — verified at runtime in this PRP's "Known Gotchas". The existing FeatureImportanceUnavailableError path stays.

- memory: simpleimputer-drops-empty-columns
  why: ProphetLikeForecaster handles this in `extract_feature_importance` (L169-200 in feature_metadata.py). Any new pipeline that uses SimpleImputer MUST pass `keep_empty_features=True` OR replicate the imputer-statistics realignment.

- memory: computed-field-cross-slice-cycle
  why: `RunResponse.model_family` is a Pydantic computed_field whose return type lives in `forecasting`. The lazy in-method import pattern stays; new RunResponse fields MUST NOT introduce a similar cycle.

- memory: scenario-run-id-vs-registry-run-id
  why: Scenarios `/scenarios/simulate` uses the forecast-artifact `run_id` (model_{id}.joblib), NOT the registry `model_run.run_id`. Stays load-bearing for ops/comparable-run logic — do not conflate.

- memory: data-platform-shared-orm-layer
  why: CodeRabbit flags cross-slice imports of `data_platform.models`. This PRP keeps the existing pattern; it does NOT refactor.
```

### Current Codebase tree (relevant after PRP-35 merges)

```
app/
├── shared/
│   └── feature_frames/
│       ├── __init__.py             # V1 + V2 surface (PRP-35)
│       ├── contract.py             # V1 (frozen)
│       ├── contract_v2.py          # V2 (PRP-35)
│       ├── rows.py                 # V1 (frozen)
│       ├── rows_v2.py              # V2 (PRP-35)
│       ├── sidecar.py              # V2 (PRP-35)
│       └── tests/
│           ├── test_contract.py
│           ├── test_contract_v2.py
│           ├── test_leakage.py             # load-bearing
│           └── test_leakage_v2.py          # load-bearing (PRP-35)
├── features/
│   ├── forecasting/
│   │   ├── models.py               # BaseForecaster, 7 forecasters, model_factory
│   │   ├── schemas.py              # ModelConfig union; TrainRequest
│   │   ├── persistence.py          # ModelBundle.metadata dict[str, object]
│   │   ├── service.py              # train_model + V1/V2 dispatch (PRP-35)
│   │   ├── feature_metadata.py     # _MODEL_FAMILY_MAP + extract_feature_importance
│   │   ├── v2_loaders.py           # PRP-35 — reused here
│   │   └── routes.py
│   ├── backtesting/
│   │   ├── service.py              # fold loop + V1/V2 dispatch (PRP-35 Task 13)
│   │   ├── metrics.py              # MetricsCalculator (mae/smape/wape/bias/stability)
│   │   ├── schemas.py              # FoldResult + BacktestResponse
│   │   └── splitter.py             # TimeSeriesSplit-style
│   ├── registry/
│   │   ├── models.py               # ModelRun + DeploymentAlias
│   │   ├── schemas.py              # RunResponse / RunDetailResponse
│   │   ├── service.py              # _find_duplicate + create_alias
│   │   └── routes.py
│   ├── ops/
│   │   ├── service.py              # stale-alias + model-health
│   │   ├── schemas.py
│   │   └── routes.py
│   └── explainability/
│       ├── service.py              # baselines only today
│       ├── explainers.py
│       └── reason_codes.py
└── core/
    └── config.py
```

### Desired Codebase tree (new + modified files)

```
app/
├── features/
│   ├── forecasting/
│   │   ├── models.py               # MODIFIED — add WeightedMovingAverageForecaster, SeasonalAverageForecaster, [optional] TrendRegressionBaselineForecaster, [optional] RandomForestForecaster + factory dispatch
│   │   ├── schemas.py              # MODIFIED — add WeightedMovingAverageModelConfig, SeasonalAverageModelConfig, [optional] TrendRegressionBaselineModelConfig, [optional] RandomForestModelConfig + extend ModelConfig union
│   │   ├── feature_metadata.py     # MODIFIED — extend _MODEL_FAMILY_MAP with new model_types; extend extract_feature_importance to recognise RandomForestForecaster
│   │   ├── service.py              # MODIFIED — train_model branch for new target-only models (no feature build); persist feature_frame_version + feature_groups when V2 (additive over PRP-35)
│   │   └── tests/
│   │       ├── test_weighted_moving_average_forecaster.py    # NEW
│   │       ├── test_seasonal_average_forecaster.py           # NEW
│   │       ├── test_trend_regression_baseline_forecaster.py  # NEW (optional)
│   │       ├── test_random_forest_forecaster.py              # NEW (optional)
│   │       ├── test_feature_metadata.py                      # MODIFIED — assert new model_types map to families; assert random_forest exposes feature_importances_
│   │       └── test_models.py                                # MODIFIED — factory dispatch table covers new types
│   ├── backtesting/
│   │   ├── metrics.py              # MODIFIED — add MetricsCalculator.rmse + bucket_metrics helper
│   │   ├── service.py              # MODIFIED — emit per-fold horizon_bucket_metrics + per-bucket aggregates
│   │   ├── schemas.py              # MODIFIED — FoldResult gains horizon_bucket_metrics; aggregate gains rmse + bucketed dict
│   │   └── tests/
│   │       ├── test_metrics.py                                # MODIFIED — rmse + bucket helper unit tests
│   │       ├── test_service.py                                # MODIFIED — assert bucketed payload shape
│   │       └── test_feature_aware_backtest_v2.py              # PRP-35 — unchanged; new tests do NOT weaken
│   ├── registry/
│   │   ├── service.py              # MODIFIED — _find_duplicate includes feature_frame_version; comparable_runs predicate (new helper)
│   │   ├── schemas.py              # MODIFIED — RunResponse / RunDetailResponse expose feature_frame_version + feature_groups (Optional)
│   │   └── tests/
│   │       ├── test_service.py                                # MODIFIED — V1-vs-V2 not a duplicate; comparable_runs helper tests
│   │       └── test_schemas.py                                # MODIFIED — new fields round-trip
│   ├── ops/
│   │   ├── service.py              # MODIFIED — comparable-run selection by (grain, overlap window, same V); add stale-reason `feature_frame_version_mismatch`
│   │   ├── schemas.py              # MODIFIED — stale-reason enum extended; comparable-run metadata exposed
│   │   └── tests/
│   │       ├── test_service.py                                # MODIFIED — assert stale-reason mismatch path; assert V1 alias not compared to V2 newer run as "degrading"
│   │       └── test_routes_integration.py                     # MODIFIED — happy path + mismatch path
│   └── explainability/
│       ├── service.py              # MODIFIED — register new baseline explainers; route `random_forest` to existing tree feature-importance path through extract_feature_importance
│       ├── explainers.py           # MODIFIED — WeightedMovingAverageExplainer + SeasonalAverageExplainer + (optional) TrendRegressionBaselineExplainer
│       └── tests/
│           ├── test_explainers.py                             # MODIFIED — new explainer classes
│           └── test_service.py                                # MODIFIED — service routes new model_types correctly
└── examples/
    └── forecasting/
        └── model_zoo_compare.py    # NEW — small local sweep + per-model metrics + registry candidate summary
```

### Known Gotchas of our codebase & Library Quirks

```python
# ─────────────────────────────────────────────────────────────────────────
# CRITICAL: PRP-35 prerequisite — Task 1 (Contract Refresh) is the gate.
# ─────────────────────────────────────────────────────────────────────────
#
# If `from app.shared.feature_frames import (FEATURE_FRAME_VERSION_V2,
# FeatureGroup, build_historical_feature_rows_v2)` fails — STOP. PRP-35 has
# not landed. Do not execute any later task.
#
# If those imports succeed but PRP-35 shipped a different field name in
# bundle.metadata (e.g. `feature_safety` instead of `feature_safety_classes`),
# Task 1 PATCHES the names cited in this PRP before any code is written.
#
# ─────────────────────────────────────────────────────────────────────────
# Library verifications (executed at PRP-create time on the live env —
# sklearn 1.8.0, numpy 2.4.1, pandas 3.0.3). Re-verify after any library
# bump. Verification commands:
# ─────────────────────────────────────────────────────────────────────────

# VERIFIED: HistGradientBoostingRegressor has NO `feature_importances_`
#   uv run python -c "
#     from sklearn.ensemble import HistGradientBoostingRegressor
#     m = HistGradientBoostingRegressor()
#     m.fit([[1.0],[2.0],[3.0]], [1.0,2.0,3.0])
#     print('HAS_attr:', hasattr(m, 'feature_importances_'))
#   "
#   Output: HAS_attr: False
#   IMPLICATION: `extract_feature_importance` MUST continue to raise
#   FeatureImportanceUnavailableError for RegressionForecaster. This PRP
#   does NOT relitigate that contract.
#
# VERIFIED: RandomForestRegressor has `feature_importances_` as a 1-D vector
#   uv run python -c "
#     from sklearn.ensemble import RandomForestRegressor
#     m = RandomForestRegressor(n_estimators=3, random_state=42, n_jobs=1)
#     m.fit([[1.0,2.0],[2.0,1.0],[3.0,3.0],[4.0,2.0]], [1.0,2.0,3.0,4.0])
#     print('HAS_attr:', hasattr(m, 'feature_importances_'),
#           'NDIM:', m.feature_importances_.ndim,
#           'SHAPE:', m.feature_importances_.shape)
#   "
#   Output: HAS_attr: True NDIM: 1 SHAPE: (2,)
#   IMPLICATION: RandomForestForecaster (optional) reuses the existing
#   tree-importance branch in extract_feature_importance (L147-164) —
#   just add `RandomForestForecaster` to the isinstance check.
#
# VERIFIED: RandomForestRegressor deterministic with random_state=42, n_jobs=1
#   uv run python -c "
#     import numpy as np
#     from sklearn.ensemble import RandomForestRegressor
#     X = np.array([[i, i%7] for i in range(60)], dtype=float)
#     y = np.array([float(i) for i in range(60)])
#     a = RandomForestRegressor(n_estimators=5, random_state=42, n_jobs=1).fit(X, y).predict([[60.0, 4.0]])
#     b = RandomForestRegressor(n_estimators=5, random_state=42, n_jobs=1).fit(X, y).predict([[60.0, 4.0]])
#     print('EQ:', np.array_equal(a, b))
#   "
#   Output: EQ: True
#   IMPLICATION: random_state + n_jobs=1 is the deterministic recipe. Use
#   it in RandomForestForecaster.__init__; never set n_jobs > 1.
#
# VERIFIED: np.average(vals, weights=...) supports both linear + exponential
#   uv run python -c "
#     import numpy as np
#     vals = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
#     weights_linear = np.arange(1, len(vals)+1)
#     print('LIN_WMA:', np.average(vals, weights=weights_linear))
#     weights_exp = np.power(0.5, np.arange(len(vals)-1, -1, -1))
#     print('EXP_WMA:', np.average(vals, weights=weights_exp))
#   "
#   Output: LIN_WMA: 3.666... EXP_WMA: 4.161...
#   IMPLICATION: WeightedMovingAverageForecaster uses np.average with either
#   a "linear" or "exponential" weights strategy. Coverage: both branches
#   in unit tests.
#
# VERIFIED: Ridge deterministic by construction (closed-form solver)
#   uv run python -c "
#     import numpy as np
#     from sklearn.linear_model import Ridge
#     X = np.array([[i, i%7] for i in range(60)], dtype=float)
#     y = np.array([float(i) for i in range(60)])
#     a = Ridge(random_state=42).fit(X, y).coef_
#     b = Ridge(random_state=42).fit(X, y).coef_
#     print('EQ:', np.array_equal(a, b))
#   "
#   Output: EQ: True
#   IMPLICATION: TrendRegressionBaselineForecaster (optional, Ridge-based)
#   does not need n_jobs=1 to be deterministic.

# VERIFIED: lightgbm + xgboost are NOT installed in the default venv
#   uv run python -c "
#     import importlib.util
#     print('lightgbm:', importlib.util.find_spec('lightgbm') is not None,
#           'xgboost:', importlib.util.find_spec('xgboost') is not None)
#   "
#   Output: lightgbm: False xgboost: False
#   IMPLICATION: This PRP does NOT add new lightgbm/xgboost code paths that
#   require the libraries to be importable at module load time. ALL new
#   model configurations for the existing lightgbm/xgboost forecasters
#   adjust DEFAULTS in `LightGBMModelConfig` / `XGBoostModelConfig`. They
#   stay behind the existing `forecast_enable_*` flags and the existing
#   lazy-import-in-fit pattern (`models.py` L706 / L870). Unit tests for
#   the config tightening do NOT require the libraries; integration tests
#   that fit a real model MUST `pytest.mark.skipif(not importlib.util.
#   find_spec("lightgbm"), reason="lightgbm extra not installed")`.

# ─────────────────────────────────────────────────────────────────────────
# Repo-specific failure modes (anchored in memory + prior PRPs):
# ─────────────────────────────────────────────────────────────────────────

# - model_run.metrics is JSONB; nested dicts round-trip fine. BUT date /
#   datetime values DO NOT — store dates as ISO strings (the existing
#   pattern is `bundle.metadata["created_at"] = datetime.now(UTC).isoformat()`).
# - `RegistryService._find_duplicate` is called from RegistryService.create_run
#   BEFORE the run is persisted; adding feature_frame_version to its
#   match key needs the V flag passed in via RunCreate.runtime_info — the
#   forecasting service already populates runtime_info from
#   `extra_metadata` (PRP-35 Task 9). Confirm during Task 1.
# - `RunResponse.model_family` is a Pydantic computed_field whose return
#   type lives in forecasting. Adding `feature_frame_version` and
#   `feature_groups` to RunResponse MUST NOT introduce a similar cross-
#   slice cycle. Both new fields are plain Python types (int / dict[str,
#   list[str]]) so no import is needed (memory `computed-field-cross-slice-
#   cycle`).
# - Per-horizon-bucket metric names are stable string keys; do NOT keep
#   them as enums in the response JSON (TypeScript on the Slice C side
#   would have to map them). Bucket ids: "h_1_7", "h_8_14", "h_15_28",
#   "h_29_plus".
# - When OPTIONAL libraries are missing, route handlers MUST surface a
#   422 RFC 7807 with `detail="lightgbm extra not installed; install with
#   uv sync --extra ml-lightgbm and set forecast_enable_lightgbm=true"` —
#   never a 500. The existing flag-gate check in forecasting/routes.py is
#   the pattern.
# - `app/shared/feature_frames/**` remains leaf-level — backtesting and
#   forecasting service may import from it; it MAY NOT import from any
#   features slice (the AST-walk invariant catches this).
# - `make demo` / `scripts/run_demo.py` use the demo seeder and the existing
#   model types. Confirm none of the new model types break the demo path
#   — they shouldn't (demo trains naive / seasonal_naive / moving_average
#   per `app/features/demo/pipeline.py`). DO NOT change the demo to use new
#   models; that's Slice C territory.
# - Per-horizon-bucket aggregates MUST skip empty buckets (h_29+ on a 14-day
#   forecast is empty); the aggregate returns NaN for empty bucket values
#   AND drops empty buckets from the per-fold dict. Mirror the existing
#   sMAPE / WAPE empty-array handling at metrics.py L78.
# - `bundle_hash` is computed from the model class + config dict; tightening
#   the DEFAULTS on existing configs changes the hash for newly-trained
#   models. Old bundles (with the old defaults) MUST still load + predict
#   identically. The existing schema-version field at ModelConfigBase L37-41
#   IS the canary: bumping it triggers re-train; this PRP does NOT bump it.
```

---

## Implementation Blueprint

### Data models and structure

```python
# ─── app/features/forecasting/schemas.py — new ModelConfigs (additive) ───

class WeightedMovingAverageModelConfig(ModelConfigBase):
    """Target-only baseline: weighted average of last N observations."""
    model_type: Literal["weighted_moving_average"] = "weighted_moving_average"
    window_size: int = Field(default=7, ge=2, le=90)
    weight_strategy: Literal["linear", "exponential"] = "linear"
    # 'linear' → weights = np.arange(1, window_size+1)
    # 'exponential' → weights = np.power(decay, np.arange(window_size-1, -1, -1))
    decay: float = Field(default=0.7, gt=0.0, lt=1.0)


class SeasonalAverageModelConfig(ModelConfigBase):
    """Target-only baseline: average of prior matching seasonal positions."""
    model_type: Literal["seasonal_average"] = "seasonal_average"
    season_length: int = Field(default=7, ge=2, le=365)
    lookback_cycles: int = Field(default=4, ge=2, le=12)
    trim_outliers: bool = False  # if True, drop top + bottom value before mean


class TrendRegressionBaselineModelConfig(ModelConfigBase):  # OPTIONAL
    """Target-only Ridge baseline: elapsed-time + simple calendar features."""
    model_type: Literal["trend_regression_baseline"] = "trend_regression_baseline"
    alpha: float = Field(default=1.0, ge=0.0, le=1000.0)
    include_dow: bool = True
    include_month: bool = True


class RandomForestModelConfig(ModelConfigBase):  # OPTIONAL
    """Feature-aware sklearn RandomForest with feature_importances_."""
    model_type: Literal["random_forest"] = "random_forest"
    n_estimators: int = Field(default=100, ge=10, le=500)
    max_depth: int | None = Field(default=10, ge=2, le=64)
    min_samples_leaf: int = Field(default=2, ge=1, le=50)
    feature_config_hash: str | None = None  # matches existing tree-config pattern


# ─── Extend the discriminated union (app/features/forecasting/schemas.py:268) ─
ModelConfig = Annotated[
    NaiveModelConfig
    | SeasonalNaiveModelConfig
    | MovingAverageModelConfig
    | WeightedMovingAverageModelConfig    # NEW
    | SeasonalAverageModelConfig          # NEW
    | TrendRegressionBaselineModelConfig  # NEW (optional)
    | RandomForestModelConfig             # NEW (optional)
    | LightGBMModelConfig
    | XGBoostModelConfig
    | RegressionModelConfig
    | ProphetLikeModelConfig,
    Field(discriminator="model_type"),
]


# ─── app/features/backtesting/schemas.py — new fields (additive) ─────────

# FoldResult adds:
horizon_bucket_metrics: dict[str, dict[str, float]] = Field(
    default_factory=dict,
    description="Per-bucket metrics keyed by bucket id ('h_1_7','h_8_14',"
                "'h_15_28','h_29_plus'). Empty bucket entries are dropped.",
)

# main_model_results.aggregate_metrics gains a 'rmse' key and a new
# 'bucketed_aggregate_metrics: dict[str, dict[str, float]]' top-level dict
# whose keys are the same bucket ids.


# ─── app/features/registry/schemas.py — new fields (additive, Optional) ──

# Both RunResponse and RunDetailResponse gain:
feature_frame_version: int | None = Field(
    default=None,
    description="Feature frame version recorded by the training run "
                "(read from runtime_info; None when the run pre-dates PRP-35).",
)
feature_groups: dict[str, list[str]] | None = Field(
    default=None,
    description="Per-group canonical column manifest at training time "
                "(None for V1 and pre-PRP-35 runs).",
)


# ─── app/features/ops/schemas.py — extend stale-reason enum ──────────────

class StaleReason(str, Enum):
    NEWER_SUCCESS_RUN = "newer_success_run"             # existing
    ARTIFACT_NOT_VERIFIED = "artifact_not_verified"     # existing
    RUN_NOT_SUCCESS = "run_not_success"                 # existing
    FEATURE_FRAME_VERSION_MISMATCH = "feature_frame_version_mismatch"  # NEW
```

### List of tasks to be completed (dependency-ordered)

```yaml
Task 1 — CONTRACT REFRESH (gates every other task):
  - VERIFY PRP-35 is merged. Run:
      uv run python -c "from app.shared.feature_frames import FEATURE_FRAME_VERSION_V2, FeatureGroup, build_historical_feature_rows_v2, build_future_feature_rows_v2, v2_feature_groups_dict, v2_feature_safety_classes; print('PRP-35 surface OK')"
    If ImportError: STOP. PRP-35 has not landed. Do not write any code.
  - RE-READ PRPs/PRP-35-forecast-intelligence-A-feature-frame-v2.md § "Data models and structure" and § "Integration Points" — capture the FINAL bundle.metadata schema.
  - DIFF the metadata field names this PRP cites against what PRP-35 shipped. The cited names are:
      bundle.metadata["feature_frame_version"]    -> int
      bundle.metadata["feature_columns"]           -> list[str]
      bundle.metadata["feature_groups"]            -> dict[str, list[str]]
      bundle.metadata["feature_safety_classes"]    -> dict[str, str]
      bundle.metadata["feature_pinned_constants"]  -> dict[str, list[int]]
  - PATCH any drift between this PRP's assumed names and the merged contract by updating THIS PRP file in a `chore(docs): refresh PRP-36 against PRP-35 final contract (#<this-issue>)` commit BEFORE Task 2 starts.
  - CONFIRM bundle.metadata["feature_frame_version"] defaults to 1 when absent (the load-side back-compat).
  - VERIFY TrainRequest.feature_frame_version + TrainRequest.feature_groups exist in app/features/forecasting/schemas.py with the V1=default + V2-validator semantics PRP-35 locked.
  - VERIFY backtesting/service.py dispatches at lines 493 / 553 between V1 and V2 builders via bundle.metadata.get("feature_frame_version", 1) — the PRP-35 Task 13 work.
  - LOG the captured contract snapshot into PRPs/ai_docs/prp-35-final-contract-snapshot.md (one-off; gives Slice C a stable reference).
  - DO NOT proceed to Task 2 if any drift is unresolved.

Task 2 — CREATE app/features/forecasting/tests/test_weighted_moving_average_forecaster.py + IMPLEMENT WeightedMovingAverageForecaster:
  - TEST FIRST: write the unit-test file with: fit-raises-on-empty, fit-then-predict-shape, deterministic-with-seed, linear-weights-match-np.average, exponential-weights-match-np.average, window_size-larger-than-history-raises, persistence-round-trip.
  - IMPLEMENT class WeightedMovingAverageForecaster(BaseForecaster) in app/features/forecasting/models.py — mirror MovingAverageForecaster (L384):
      requires_features: ClassVar[bool] = False
      fit(y, X=None): stores last `window_size` observations; raises ValueError if len(y) < window_size.
      predict(horizon, X=None): np.average(self._tail, weights=self._weights) → np.full(horizon, mean_value)
  - ADD WeightedMovingAverageModelConfig in app/features/forecasting/schemas.py (per data model above).
  - EXTEND ModelConfig union at L268-276.
  - EXTEND _MODEL_FAMILY_MAP in app/features/forecasting/feature_metadata.py — map "weighted_moving_average" → ModelFamily.BASELINE.
  - WIRE INTO model_factory at L1138-1227 — add an elif branch that returns WeightedMovingAverageForecaster(window_size=config.window_size, weight_strategy=config.weight_strategy, decay=config.decay, random_state=random_state).
  - GATE: NO new flag in settings; this baseline is always on.

Task 3 — CREATE app/features/forecasting/tests/test_seasonal_average_forecaster.py + IMPLEMENT SeasonalAverageForecaster:
  - TEST FIRST: fit-then-predict-shape; same-DOW averaging actually picks matching positions; lookback_cycles smaller than history works; trim_outliers drops the top + bottom value when True; deterministic; persistence round-trip.
  - IMPLEMENT class SeasonalAverageForecaster(BaseForecaster) mirroring SeasonalNaiveForecaster (L281):
      requires_features: ClassVar[bool] = False
      fit(y, X=None): stores last (lookback_cycles * season_length) observations.
      predict(horizon, X=None): for each horizon day j, compute mean (or trimmed mean if trim_outliers) of y values at offsets {j - k*season_length} for k in [1..lookback_cycles] that lie within stored history.
  - ADD SeasonalAverageModelConfig; extend union; extend _MODEL_FAMILY_MAP → BASELINE; wire into model_factory.

Task 4 — OPTIONAL: CREATE TrendRegressionBaselineForecaster (decide YES/NO in the planning review; if NO, drop from this PRP):
  - TEST FIRST: deterministic seed; intercept + slope coefficients match np.polyfit on a perfect-line series; calendar features add expected columns when toggled.
  - IMPLEMENT class TrendRegressionBaselineForecaster(BaseForecaster) using sklearn.linear_model.Ridge inside a pure-numpy feature builder (elapsed-day + optional dow_one_hot + optional month_one_hot). DOES NOT use V1 or V2 row builders — its feature set is purely calendar-derived.
      requires_features: ClassVar[bool] = False
  - ADD TrendRegressionBaselineModelConfig; extend union; extend _MODEL_FAMILY_MAP → ADDITIVE; wire into model_factory.

Task 5 — OPTIONAL: CREATE RandomForestForecaster (decide YES/NO; gate with `forecast_enable_random_forest: bool = False` IF YES):
  - TEST FIRST: requires_features=True; fit with shape-matched X; deterministic with random_state=42 + n_jobs=1; feature_importances_ shape == (len(feature_columns),).
  - IMPLEMENT class RandomForestForecaster(BaseForecaster) wrapping sklearn.ensemble.RandomForestRegressor:
      requires_features: ClassVar[bool] = True
      __init__: stores n_estimators, max_depth, min_samples_leaf, random_state. n_jobs=1 (REQUIRED for determinism — verified).
      fit(y, X): self._estimator = RandomForestRegressor(...).fit(X, y); save self._feature_columns = X.columns if pandas else None.
      predict(horizon, X): X is the future feature matrix (built by forecasting service via V1 or V2 builders — same dispatch as RegressionForecaster); return self._estimator.predict(X).
  - ADD RandomForestModelConfig; extend union; extend _MODEL_FAMILY_MAP → TREE.
  - EXTEND extract_feature_importance L147 — add `RandomForestForecaster` to the isinstance tuple; nothing else changes (the existing tree-importance branch already reads `.feature_importances_`).
  - ADD `forecast_enable_random_forest: bool = False` to app/core/config.py + `.env.example`.
  - GATE in model_factory: `if not settings.forecast_enable_random_forest: raise ValueError("random_forest is opt-in; set forecast_enable_random_forest=true")`.

Task 6 — TIGHTEN existing feature-aware config defaults (conservative + documented):
  - app/features/forecasting/schemas.py:
      RegressionModelConfig — defaults unchanged unless the implementer can justify a strictly-better conservative default via backtest evidence; documented in commit message. Otherwise: NO CHANGE.
      LightGBMModelConfig — confirm defaults match the determinism recipe (deterministic=True is a runtime arg; n_jobs=1 is a runtime arg). EXPOSE: n_jobs (default 1, max 1 — fixed), deterministic (default True).
      XGBoostModelConfig — confirm tree_method="hist", n_jobs=1, verbosity=0 are wired into the forecaster instantiation. EXPOSE: n_jobs (default 1, max 1).
      ProphetLikeModelConfig — confirm Ridge alpha range. NO CHANGE without justification.
  - DOCUMENT every config tightening with a one-line comment in the schema docstring AND in CHANGELOG under "Unreleased".
  - CRITICAL: do NOT change any default that would break bundle_hash for already-trained models. The existing `schema_version` field (ModelConfigBase L37-41) is the canary; bump it ONLY if a backward-incompatible default change is unavoidable. Default position: no bump.

Task 7 — EXTEND backtesting metrics with RMSE + per-horizon-bucket helper:
  - app/features/backtesting/metrics.py:
      @staticmethod
      def rmse(actuals, predictions) -> MetricResult:
          # mirrors mae() shape; formula: sqrt(mean((A - F) ** 2))
  - ADD module-level constant HORIZON_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
        ("h_1_7", 1, 7),
        ("h_8_14", 8, 14),
        ("h_15_28", 15, 28),
        ("h_29_plus", 29, None),
    )
  - ADD function compute_bucket_metrics(actuals, predictions, horizon_offsets: list[int]) -> dict[str, dict[str, float]]:
      For each bucket, slice the (actuals, predictions) pair by horizon_offsets in [start, end] inclusive (end=None → unbounded). Skip a bucket if its slice is empty. Call calculate_all on each non-empty slice. Return dict keyed by bucket id.
  - EXTEND MetricsCalculator.calculate_all to include rmse alongside mae/smape/wape/bias.
  - DO NOT change aggregate_fold_metrics signature; ADD a sibling aggregate_bucket_metrics(fold_bucket_metrics: list[dict[str, dict[str, float]]]) -> dict[str, dict[str, float]] that returns per-bucket means across folds, skipping NaN.

Task 8 — WIRE backtesting service to emit per-fold horizon_bucket_metrics:
  - app/features/backtesting/service.py:
    - For each fold, compute `horizon_offsets = [(test_dates[i] - test_dates[0]).days + 1 for i in range(len(test_dates))]` (test_dates[0] is horizon day 1).
    - After computing the existing per-fold metrics, call compute_bucket_metrics(actuals, predictions, horizon_offsets) and attach to FoldResult.horizon_bucket_metrics.
    - After the fold loop, compute aggregate_bucket_metrics across all fold_bucket_metric dicts → main_model_results.bucketed_aggregate_metrics.
    - Mirror for baseline_results when baselines are run alongside.
  - PRESERVE the V1/V2 dispatch PRP-35 Task 13 added — no change to it.
  - PRESERVE leakage_check_passed flow.
  - LOG: per-fold metric log lines now include feature_frame_version (already added by PRP-35) AND the bucket count.

Task 9 — EXTEND backtesting schemas:
  - FoldResult: add horizon_bucket_metrics: dict[str, dict[str, float]] = Field(default_factory=dict, ...).
  - main_model_results.aggregate_metrics: include rmse (additive — no breaking change).
  - main_model_results: add bucketed_aggregate_metrics: dict[str, dict[str, float]] | None = None.
  - Mirror for baseline_results.
  - PRESERVE: ConfigDict(strict=True); plain numeric/string fields — no strict=False overrides needed (no date/UUID/Decimal involved).

Task 10 — MODIFY app/features/registry/service.py — _find_duplicate AND comparable_runs:
  - FIND _find_duplicate at L629-672.
  - ADD a `feature_frame_version` parameter to its match key (read from RunCreate.runtime_info["feature_frame_version"] when present; default 1 when absent — back-compat).
  - ADD a sibling helper async def find_comparable_runs(self, db, *, store_id: int, product_id: int, model_type: str | None, feature_frame_version: int, data_window_start: date, data_window_end: date, limit: int = 20) -> list[ModelRun]:
      Returns: SUCCESS runs for the same (store_id, product_id) where the data window overlaps AND feature_frame_version matches; ordered by created_at desc; limit applied.
  - DO NOT change create_alias / update_alias precondition (status == SUCCESS).
  - PRESERVE artifact_hash verification flow.

Task 11 — MODIFY app/features/registry/schemas.py:
  - RunResponse: add feature_frame_version: int | None = None, feature_groups: dict[str, list[str]] | None = None — both Optional, both read from `runtime_info` JSONB via a Pydantic validator (the existing model_family computed_field is the precedent).
  - RunDetailResponse: same additive fields.
  - DO NOT introduce a cross-slice import for these fields (the field types are plain Python — no risk of the computed-field cycle from memory `computed-field-cross-slice-cycle`).

Task 12 — MODIFY app/features/ops/service.py — comparable-run + stale-reason mismatch path:
  - FIND comparable-run selection L412-427.
  - REPLACE the selection with `await registry_service.find_comparable_runs(db, store_id=..., product_id=..., model_type=..., feature_frame_version=..., data_window_start=..., data_window_end=...)`.
  - FIND _alias_staleness at L137-159.
  - ADD a new staleness branch: when an alias's run has feature_frame_version=V_a AND a newer comparable SUCCESS run has feature_frame_version=V_b WHERE V_a != V_b → is_stale=True, reason=StaleReason.FEATURE_FRAME_VERSION_MISMATCH.
  - PRESERVE the existing reasons (NEWER_SUCCESS_RUN, ARTIFACT_NOT_VERIFIED, RUN_NOT_SUCCESS).
  - PRESERVE the drift_direction rank map (degrading > improving > stable > unknown).

Task 13 — MODIFY app/features/ops/schemas.py:
  - StaleReason enum: add FEATURE_FRAME_VERSION_MISMATCH = "feature_frame_version_mismatch".
  - StaleAliasResponse and ModelHealthEntry: expose `alias_feature_frame_version` and `comparable_run_feature_frame_version` (both Optional) so Slice C can render the mismatch.

Task 14 — MODIFY app/features/explainability/service.py + explainers.py:
  - explainers.py: ADD WeightedMovingAverageExplainer and SeasonalAverageExplainer — mirror the simple-arithmetic shape of MovingAverageExplainer / SeasonalNaiveExplainer. Reason codes from `reason_codes.py` flow through unchanged.
  - service.py: REGISTER the new explainers in the explainer_factory (the existing if-elif at L205 or its successor). NEW model_types route to their new explainer classes; the 400 "unsupported model type" path keeps catching anything truly unsupported.
  - If TrendRegressionBaselineForecaster ships: ADD TrendRegressionBaselineExplainer (Ridge coefficients → "trend coefficient X, dow coefficient Y_d for d in DOW").
  - If RandomForestForecaster ships: route /explain/runs/{run_id} for `random_forest` to a path that calls `extract_feature_importance` (feature-aware code path) AND a simple "tree-importance" explanation. Mirror the existing prophet_like explainability shape — but DO NOT introduce a /explain/forecast handler for random_forest in this PRP (that requires a forecast horizon + bundle reload, which is out of scope here).
  - PRESERVE: HGBR-not-supported path stays as is (FeatureImportanceUnavailableError continues to surface as 422).
  - PRESERVE: every reason code from reason_codes.py.

Task 15 — UPDATE tests:
  - app/features/forecasting/tests/test_feature_metadata.py — assert every new model_type appears in _MODEL_FAMILY_MAP; assert model_family_for("random_forest") == ModelFamily.TREE (if shipped).
  - app/features/backtesting/tests/test_metrics.py — rmse correctness + sign convention; compute_bucket_metrics on a hand-crafted horizon array with bucket boundary cases (empty h_29_plus on a 14-day horizon).
  - app/features/backtesting/tests/test_service.py — assert FoldResult.horizon_bucket_metrics shape; assert empty bucket is dropped.
  - app/features/backtesting/tests/test_feature_aware_backtest_v2.py — UNCHANGED (PRP-35 owns it; do not weaken).
  - app/features/registry/tests/test_service.py — V1-vs-V2 not a duplicate; find_comparable_runs returns only matching feature_frame_version runs.
  - app/features/registry/tests/test_schemas.py — RunResponse round-trips feature_frame_version + feature_groups from runtime_info.
  - app/features/ops/tests/test_service.py — stale-reason mismatch path; comparable-run selection excludes different feature_frame_version.
  - app/features/explainability/tests/test_service.py — every new baseline routes to its explainer; HGBR still 422; random_forest 200 with tree importances (if shipped).

Task 16 — CREATE examples/forecasting/model_zoo_compare.py:
  - Read-only diagnostic script — given a (store_id, product_id) pair, train + backtest the seven (or nine) models against the seeded DB, print a metrics + registry-candidate summary table with per-bucket WAPE.
  - Uses the public services (no DB writes outside the existing /forecasting/train + /backtesting/run flow).
  - Documented in docs/optional-features/05-advanced-ml-model-zoo.md (existing optional-features doc).

Task 17 — UPDATE docs:
  - docs/optional-features/05-advanced-ml-model-zoo.md — describe each new model + bucketed metrics + the example script.
  - docs/optional-features/09-model-champion-challenger-governance.md — describe the feature_frame_version comparability rule.
  - docs/_base/API_CONTRACTS.md — update /backtesting/run response shape (FoldResult.horizon_bucket_metrics; main_model_results.bucketed_aggregate_metrics; rmse in aggregate); update /registry/runs/{id} response shape (Optional feature_frame_version + feature_groups).
  - docs/_base/DOMAIN_MODEL.md — update the "comparable run" definition.

Task 18 — VERIFY no Alembic migration is needed:
  - All new state rides in existing JSONB columns. Run `uv run alembic check` → must report no pending revisions.
```

### Per task pseudocode (the load-bearing parts)

```python
# Task 7 — RMSE
@staticmethod
def rmse(actuals, predictions) -> MetricResult:
    """Root Mean Squared Error. Penalises large errors more than MAE."""
    warnings: list[str] = []
    if len(actuals) == 0:
        return MetricResult(name="rmse", value=float("nan"), n_samples=0, warnings=["Empty array"])
    if len(actuals) != len(predictions):
        raise ValueError(f"Length mismatch: actuals={len(actuals)}, predictions={len(predictions)}")
    rmse_value = float(np.sqrt(np.mean((actuals - predictions) ** 2)))
    return MetricResult(name="rmse", value=rmse_value, n_samples=len(actuals), warnings=warnings)


# Task 7 — bucket helper
HORIZON_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("h_1_7", 1, 7),
    ("h_8_14", 8, 14),
    ("h_15_28", 15, 28),
    ("h_29_plus", 29, None),
)

def compute_bucket_metrics(
    actuals: np.ndarray,
    predictions: np.ndarray,
    horizon_offsets: list[int],
) -> dict[str, dict[str, float]]:
    """Per-horizon-bucket metric block. Empty buckets are dropped."""
    if not (len(actuals) == len(predictions) == len(horizon_offsets)):
        raise ValueError("array length mismatch")
    calc = MetricsCalculator()
    out: dict[str, dict[str, float]] = {}
    h = np.asarray(horizon_offsets)
    for bucket_id, start, end in HORIZON_BUCKETS:
        mask = (h >= start) & (h <= (end if end is not None else h.max()))
        if not mask.any():
            continue
        bucket = calc.calculate_all(actuals[mask], predictions[mask])
        bucket["rmse"] = calc.rmse(actuals[mask], predictions[mask]).value
        out[bucket_id] = bucket
    return out


# Task 2 — WeightedMovingAverageForecaster (key parts)
class WeightedMovingAverageForecaster(BaseForecaster):
    """Target-only baseline: weighted average of last `window_size` observations.

    Weighting:
    - 'linear': weights = [1, 2, ..., window_size] (most recent weighted highest)
    - 'exponential': weights = [decay**(W-1), ..., decay**1, decay**0]
    """

    requires_features: ClassVar[bool] = False

    def __init__(self, *, window_size: int, weight_strategy: str, decay: float, random_state: int = 42) -> None:
        super().__init__(random_state=random_state)
        self.window_size = window_size
        self.weight_strategy = weight_strategy
        self.decay = decay
        self._weights: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None
        self._weighted_mean: float | None = None

    def fit(self, y, X=None):
        y = np.asarray(y, dtype=np.float64)
        if y.size < self.window_size:
            raise ValueError(f"need at least {self.window_size} observations, got {y.size}")
        tail = y[-self.window_size:]
        if self.weight_strategy == "linear":
            self._weights = np.arange(1, self.window_size + 1, dtype=np.float64)
        else:  # exponential
            self._weights = np.power(self.decay, np.arange(self.window_size - 1, -1, -1, dtype=np.float64))
        self._weighted_mean = float(np.average(tail, weights=self._weights))
        self._is_fitted = True
        return self

    def predict(self, horizon, X=None):
        if not self._is_fitted or self._weighted_mean is None:
            raise RuntimeError("WeightedMovingAverageForecaster is not fitted")
        return np.full(horizon, self._weighted_mean, dtype=np.float64)


# Task 3 — SeasonalAverageForecaster (key parts)
class SeasonalAverageForecaster(BaseForecaster):
    """Target-only baseline: average of prior matching seasonal positions.

    For horizon day j with season_length S, average the values at offsets
    {j - k*S} for k in [1..lookback_cycles] that fall inside the stored history.
    """

    requires_features: ClassVar[bool] = False

    def __init__(self, *, season_length: int, lookback_cycles: int, trim_outliers: bool, random_state: int = 42) -> None:
        super().__init__(random_state=random_state)
        self.season_length = season_length
        self.lookback_cycles = lookback_cycles
        self.trim_outliers = trim_outliers
        self._history: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None

    def fit(self, y, X=None):
        y = np.asarray(y, dtype=np.float64)
        min_required = self.season_length * 2  # at minimum, one full cycle to average over
        if y.size < min_required:
            raise ValueError(f"need at least {min_required} observations, got {y.size}")
        self._history = y[-(self.season_length * self.lookback_cycles):]
        self._is_fitted = True
        return self

    def predict(self, horizon, X=None):
        if not self._is_fitted or self._history is None:
            raise RuntimeError("SeasonalAverageForecaster is not fitted")
        out = np.zeros(horizon, dtype=np.float64)
        H = self._history
        S = self.season_length
        for j in range(horizon):
            target_offset = j + 1  # horizon day index, 1-based
            samples: list[float] = []
            for k in range(1, self.lookback_cycles + 1):
                idx_from_end = k * S - target_offset
                if 0 <= idx_from_end < H.size:
                    samples.append(float(H[H.size - 1 - idx_from_end]))
            if not samples:
                # Fallback: use the last observed value (defensive — should
                # not happen given the fit-time min_required check).
                out[j] = float(H[-1])
                continue
            arr = np.asarray(samples)
            if self.trim_outliers and arr.size >= 4:
                arr = np.sort(arr)[1:-1]  # drop min + max
            out[j] = float(arr.mean())
        return out


# Task 10 — find_comparable_runs (key parts)
async def find_comparable_runs(
    self,
    db,
    *,
    store_id: int,
    product_id: int,
    model_type: str | None,
    feature_frame_version: int,
    data_window_start: date,
    data_window_end: date,
    limit: int = 20,
) -> list[ModelRun]:
    """SUCCESS runs comparable to the (grain, window, V) tuple given.

    Comparable predicate:
      - same store_id AND same product_id;
      - data windows overlap (run.data_window_end >= start AND run.data_window_start <= end);
      - same feature_frame_version (read from runtime_info JSONB; defaults 1 when absent);
      - status == SUCCESS.

    Ordered by created_at desc; capped by `limit`. `model_type=None` means
    "any model_type" — caller filters further if narrower.
    """
    stmt = (
        select(ModelRun)
        .where(ModelRun.store_id == store_id)
        .where(ModelRun.product_id == product_id)
        .where(ModelRun.status == RunStatus.SUCCESS)
        .where(ModelRun.data_window_end >= data_window_start)
        .where(ModelRun.data_window_start <= data_window_end)
        # JSONB extraction: coalesce missing key to '1' string then cast.
        .where(
            (cast(ModelRun.runtime_info["feature_frame_version"].astext, Integer) == feature_frame_version)
            | (and_(feature_frame_version == 1, ModelRun.runtime_info["feature_frame_version"].astext.is_(None)))
        )
        .order_by(ModelRun.created_at.desc())
        .limit(limit)
    )
    if model_type is not None:
        stmt = stmt.where(ModelRun.model_type == model_type)
    result = await db.execute(stmt)
    return list(result.scalars().all())
# CRITICAL: the JSONB "missing key = V1" clause is the back-compat seam —
# legacy V1 runs never wrote feature_frame_version, so absent key MUST
# resolve to V=1.
```

### Integration Points

```yaml
DATABASE:
  - migration: NONE — all new state rides in existing JSONB columns. Verify with `uv run alembic check`.
  - reads: ModelRun.runtime_info JSONB; ModelRun.data_window_start / data_window_end / store_id / product_id / status / created_at.
  - writes: model_run.runtime_info gains `feature_frame_version: int` + `feature_groups: dict[str, list[str]]` (additive — PRP-35 already populates these via ForecastingService.train_model extra_metadata).

CONFIG:
  - app/core/config.py: NO new settings if random_forest is dropped from scope. IF random_forest ships: `forecast_enable_random_forest: bool = False`.
  - .env.example: matches the new setting if added.

ROUTES:
  - No new endpoint paths.
  - /forecasting/train: accepts new model_type values transparently via the discriminated union.
  - /backtesting/run: response gains horizon_bucket_metrics + bucketed_aggregate_metrics + rmse (additive — Slice C reads these).
  - /registry/runs/{id}: response gains feature_frame_version + feature_groups (additive).
  - /ops/stale-aliases, /ops/model-health: response gains StaleReason.FEATURE_FRAME_VERSION_MISMATCH variant + comparable-run feature_frame_version (additive).

SCHEMAS:
  - app/features/forecasting/schemas.py: 2-4 new ModelConfig subclasses + extend ModelConfig union; ModelFamily enum unchanged.
  - app/features/backtesting/schemas.py: FoldResult + aggregate gain bucketed fields + rmse.
  - app/features/registry/schemas.py: RunResponse + RunDetailResponse gain Optional feature_frame_version + feature_groups.
  - app/features/ops/schemas.py: StaleReason enum extended; StaleAliasResponse + ModelHealthEntry gain alias_feature_frame_version + comparable_run_feature_frame_version.
  - app/features/forecasting/feature_metadata.py: _MODEL_FAMILY_MAP extended; isinstance tuple in extract_feature_importance gains RandomForestForecaster (if shipped).

REGISTRY MUTATION SURFACE:
  - No new agent tool — agent_require_approval is unchanged. (Tasks 10-13 are pure backend; the agent layer does not see them directly.)

CHANGELOG:
  - Under "Unreleased" → "feat(forecast,backtest,registry,ops): forecast intelligence B — model zoo + backtesting metrics + comparability (#<issue>)" (release-please-feed format).
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check app/features/forecasting app/features/backtesting \
                  app/features/registry app/features/ops \
                  app/features/explainability examples/forecasting --fix
uv run ruff format app/features/forecasting app/features/backtesting \
                   app/features/registry app/features/ops \
                   app/features/explainability examples/forecasting
uv run ruff format --check .

uv run mypy app/
uv run pyright app/

# Expected: zero errors. If errors, READ the message and fix; never silence.
```

### Level 2: Pure unit tests (no DB)

```bash
# Load-bearing leakage specs MUST stay byte-stable — re-run them first
uv run pytest -v app/shared/feature_frames/tests/test_leakage.py
uv run pytest -v app/shared/feature_frames/tests/test_leakage_v2.py
uv run pytest -v app/features/forecasting/tests/test_regression_features_leakage.py
uv run pytest -v app/features/forecasting/tests/test_regression_features_v2_leakage.py
uv run pytest -v app/features/scenarios/tests/test_future_frame_leakage.py
uv run pytest -v app/features/scenarios/tests/test_future_frame_v2_leakage.py
uv run pytest -v app/features/featuresets/tests/test_leakage.py

# New / modified unit tests
uv run pytest -v app/features/forecasting/tests/test_weighted_moving_average_forecaster.py
uv run pytest -v app/features/forecasting/tests/test_seasonal_average_forecaster.py
uv run pytest -v app/features/forecasting/tests/test_feature_metadata.py
uv run pytest -v app/features/forecasting/tests/test_models.py
uv run pytest -v app/features/backtesting/tests/test_metrics.py
uv run pytest -v app/features/backtesting/tests/test_service.py
uv run pytest -v app/features/registry/tests/test_service.py
uv run pytest -v app/features/registry/tests/test_schemas.py
uv run pytest -v app/features/ops/tests/test_service.py
uv run pytest -v app/features/explainability/tests/test_service.py

# If random_forest + trend_regression_baseline ship:
uv run pytest -v app/features/forecasting/tests/test_random_forest_forecaster.py
uv run pytest -v app/features/forecasting/tests/test_trend_regression_baseline_forecaster.py

# Full unit suite gate
uv run pytest -v -m "not integration"
```

### Level 3: Integration tests (real Postgres)

```bash
docker compose up -d
uv run alembic upgrade head
uv run python scripts/check_db.py

uv run alembic check   # expect "no problems detected"

# Existing V2 backtest stays green
uv run pytest -v -m integration app/features/backtesting/tests/test_feature_aware_backtest_v2.py

# New integration tests
uv run pytest -v -m integration app/features/ops/tests/test_routes_integration.py
uv run pytest -v -m integration app/features/backtesting/tests/test_service_integration.py
uv run pytest -v -m integration app/features/registry/tests/test_service.py
```

### Level 4: Smoke — model zoo end-to-end

```bash
uv run uvicorn app.main:app --reload --port 8123

# Train each new baseline
curl -sS -X POST http://localhost:8123/forecasting/train \
  -H 'Content-Type: application/json' \
  -d '{
        "store_id": 15, "product_id": 52,
        "train_start_date": "2025-01-01", "train_end_date": "2025-12-31",
        "config": {"model_type": "weighted_moving_average", "window_size": 7, "weight_strategy": "linear", "decay": 0.7}
      }' | jq .

curl -sS -X POST http://localhost:8123/forecasting/train \
  -H 'Content-Type: application/json' \
  -d '{
        "store_id": 15, "product_id": 52,
        "train_start_date": "2025-01-01", "train_end_date": "2025-12-31",
        "config": {"model_type": "seasonal_average", "season_length": 7, "lookback_cycles": 4, "trim_outliers": false}
      }' | jq .

# Backtest a feature-aware model and confirm horizon_bucket_metrics + rmse appear
curl -sS -X POST http://localhost:8123/backtesting/run \
  -H 'Content-Type: application/json' \
  -d '{
        "store_id": 15, "product_id": 52,
        "start_date": "2025-01-01", "end_date": "2025-12-31",
        "config": {
          "model_config": {"model_type": "regression", "max_iter": 200, "learning_rate": 0.05, "max_depth": 6, "feature_config_hash": null},
          "split_config": {"n_splits": 4, "horizon": 14, "gap": 0, "strategy": "expanding"},
          "feature_frame_version": 2,
          "include_baselines": true
        }
      }' | jq '.main_model_results.aggregate_metrics, .main_model_results.bucketed_aggregate_metrics'

# Registry response carries feature_frame_version + feature_groups
curl -sS http://localhost:8123/registry/runs | jq '.[0]'

# Stale-alias / model-health — when a V1 alias has a newer comparable V2 SUCCESS run
curl -sS http://localhost:8123/ops/stale-aliases | jq '.[] | select(.reason == "feature_frame_version_mismatch")'

# Optional preview
uv run python examples/forecasting/model_zoo_compare.py --store-id 15 --product-id 52
```

---

## Final validation Checklist

> **GATE FIRST:** PRP-35 is merged. Task 1 succeeded. The bundle.metadata
> contract this PRP cites matches PRP-35's final shipped names.

- [ ] Task 1 (Contract Refresh) succeeded with zero drift.
- [ ] V1 leakage spec passes unchanged (`app/shared/feature_frames/tests/test_leakage.py`).
- [ ] V2 leakage spec passes unchanged (`app/shared/feature_frames/tests/test_leakage_v2.py`).
- [ ] V1 forecasting leakage spec unchanged.
- [ ] V2 forecasting leakage spec unchanged.
- [ ] V1 + V2 scenarios leakage specs unchanged.
- [ ] V1 + V2 backtesting leakage specs unchanged.
- [ ] V1 featuresets leakage spec unchanged.
- [ ] AST-walk leaf-level invariant passes — `app/shared/feature_frames/**` imports nothing from `app/features/**`.
- [ ] Strict-mode policy linter (`app/core/tests/test_strict_mode_policy.py`) passes — every new request schema with date/UUID/Decimal carries `Field(strict=False)`.
- [ ] New model classes train, predict, persist, load:
  - [ ] `weighted_moving_average`
  - [ ] `seasonal_average`
  - [ ] (optional) `trend_regression_baseline`
  - [ ] (optional) `random_forest` AND exposes `feature_importances_`
- [ ] `_MODEL_FAMILY_MAP` covers every new model_type; unknown-fallback path unchanged.
- [ ] `extract_feature_importance` still raises `FeatureImportanceUnavailableError` for HGBR. RandomForestForecaster (if shipped) returns a 1-D importance vector matching `feature_columns` length.
- [ ] `BacktestResponse.main_model_results.aggregate_metrics` includes `rmse`.
- [ ] `BacktestResponse.main_model_results.bucketed_aggregate_metrics` is non-empty when the horizon spans bucket boundaries; empty buckets are dropped.
- [ ] `FoldResult.horizon_bucket_metrics` shape verified on a synthetic horizon.
- [ ] V1 bundle backtest + V2 bundle backtest both run on identical fold boundaries.
- [ ] `RegistryService._find_duplicate` distinguishes V1 vs V2 (a V1 run and a V2 run with otherwise-identical fields are NOT duplicates).
- [ ] `RegistryService.find_comparable_runs` returns only runs with matching feature_frame_version (and overlapping window, same grain).
- [ ] `RunResponse` + `RunDetailResponse` expose `feature_frame_version` + `feature_groups` (None for pre-PRP-35 runs).
- [ ] `OpsService` stale-alias reports `FEATURE_FRAME_VERSION_MISMATCH` when an alias's run V_a differs from a newer comparable run V_b.
- [ ] `OpsService` "comparable run" predicate honours feature_frame_version (no cross-version contamination).
- [ ] Explainability handles every new baseline AND `random_forest` (if shipped). HGBR continues to 422.
- [ ] No new endpoint paths.
- [ ] No new Alembic migration (`uv run alembic check` clean).
- [ ] No new managed-cloud SDK; no AutoML.
- [ ] No agent tool added (`agent_require_approval` unchanged).
- [ ] CHANGELOG entry under "Unreleased": `feat(forecast,backtest,registry,ops): forecast intelligence B — model zoo + backtesting metrics + comparability (#<issue>)`.
- [ ] `examples/forecasting/model_zoo_compare.py` runs against the local DB and prints the metrics table.
- [ ] Manual smoke (Level 4) — all curls 200; JSON shapes match this PRP's spec.
- [ ] `uv run ruff check .` + `uv run ruff format --check .` clean.
- [ ] `uv run mypy app/` clean (strict).
- [ ] `uv run pyright app/` clean (strict).
- [ ] `uv run pytest -v -m "not integration"` green.
- [ ] `uv run pytest -v -m integration` green (with docker-compose up).

---

## Open Design Decisions

Locked here; do not relitigate during execution unless Task 1 surfaces a
mismatch with PRP-35's final shape.

| # | Decision | Resolution | Why |
|---|----------|------------|-----|
| 1 | `trend_regression_baseline` shipped now or deferred? | **Ship it** unless Task 1 surfaces unresolved drift. The Ridge baseline gives a clean target-only "trend + calendar" comparator and matches the existing prophet_like additive lineage. Cost: ~150 LoC + 1 test file. | Marginal scope; outsized comparator value. |
| 2 | `random_forest` shipped now or deferred? | **Ship it.** Pure sklearn dep (already core); exposes `feature_importances_` (verified); deterministic with `random_state=42, n_jobs=1` (verified). Compute cost on a single store/product is acceptable for the local-host vision. | Adds an honest tree comparator with feature_importances_ that HGBR cannot give. |
| 3 | `weighted_moving_average` decay strategy: linear vs exponential? | **Both, via `weight_strategy` enum.** Default = "linear" (simpler, more intuitive). "Exponential" is the StatsForecast canon. | One model class, two weighting schemes, two test paths. |
| 4 | `seasonal_average` averages over last N cycles or all available? | **Last N cycles (config: lookback_cycles, default 4).** All-available is a degenerate special case; the N-cycle window is the StatsForecast / Nixtla canon and keeps the estimator stable across long histories. | Bounded memory; predictable behaviour. |
| 5 | "Comparable run" must share `feature_frame_version`? | **Yes — same grain AND overlapping data window AND same feature_frame_version.** Cross-V comparison silently breaks the alias contract. | Champion alias must point at a stable training contract. |
| 6 | Per-horizon-bucket id naming: `h_1_7` vs `h_1-7` vs camelCase? | **Snake_case with underscore range (`h_1_7`, `h_8_14`, `h_15_28`, `h_29_plus`).** JSON-key-safe; TypeScript-friendly; matches the existing metric naming (`mae`, `wape`). | Stable string keys; no enum confusion in JSON. |
| 7 | Stale reason on V_a != V_b: separate enum value or NEWER_SUCCESS_RUN with extra metadata? | **Separate enum value `FEATURE_FRAME_VERSION_MISMATCH`.** The UI affordance is different (Slice C wants to surface a "this alias's V is now stale" badge separately from "a newer run exists"). | Distinct operational meaning → distinct enum. |
| 8 | Where does `feature_frame_version` ride on `RunResponse`? | **As an Optional top-level field, parsed from `runtime_info` JSONB via a Pydantic validator.** No DB-column promotion. | Avoids an Alembic migration; matches the additive pattern PRP-35 used. |
| 9 | Tightening existing model config defaults? | **NO change unless backtest evidence justifies it AND the implementer adds the regression test.** Defaults that change `bundle_hash` are forbidden in this PRP. | Don't break in-flight bundles. |
| 10 | Per-horizon-bucket aggregate dropped or NaN'd for empty buckets? | **DROPPED.** A 14-day horizon's `h_29_plus` bucket simply does not appear in the response — JSON stays terse and Slice C never has to interpret a NaN. | Slimmer payloads; clear semantics. |

---

## Unresolved Contract Assumptions (waiting on PRP-35 execution)

Each item below is an assumption this PRP makes about PRP-35's final shape.
Task 1 (Contract Refresh) MUST verify each one. If any assumption breaks,
patch the relevant Task in this PRP file BEFORE writing any new code.

1. `bundle.metadata["feature_frame_version"]: int` exists for V2 bundles and
   defaults to 1 for V1 bundles (via `.get(key, 1)` at the consumer side).
   PRP-35 Tasks 9 + 12 + 13 promise this; Task 1 verifies.
2. `bundle.metadata["feature_columns"]: list[str]` is set for V1 AND V2
   bundles. PRP-35 Task 9 promises this; the V1 path already existed
   pre-PRP-35 (we rely on PRP-35 keeping it).
3. `bundle.metadata["feature_groups"]: dict[str, list[str]]` is set for V2
   bundles ONLY (absent for V1). PRP-35 § Integration Points promises this.
4. `bundle.metadata["feature_safety_classes"]: dict[str, str]` is set for V2
   bundles ONLY. PRP-35 § Integration Points promises this.
5. `bundle.metadata["feature_pinned_constants"]: dict[str, list[int]]` is
   set for V2 bundles ONLY. PRP-35 Task 9 promises this.
6. `TrainRequest.feature_frame_version: int = 1` and
   `TrainRequest.feature_groups: list[str] | None = None` exist on the
   schema with the V1-rejects-feature_groups validator (the post-patch
   wording from this conversation). PRP-35 Task 7 promises this.
7. `backtesting/service.py` already reads
   `bundle.metadata.get("feature_frame_version", 1)` BEFORE the fold loop
   AND dispatches the build_*_feature_rows_v2 calls at the V1 call sites
   (lines 493 / 553 in the V1 codebase). PRP-35 Task 13 promises this.
8. `forecasting/service.py` already writes `feature_frame_version` AND
   `feature_groups` into `extra_metadata` (and thence `model_run.runtime_info`
   via the registry create_run path). PRP-35 Task 9 promises this.
9. `app/features/forecasting/v2_loaders.py` exposes `load_lifecycle_attrs`,
   `load_inventory_history`, `load_replenishment_history`,
   `load_returns_history`, `load_promotion_history`, `load_exogenous_history`,
   `assemble_v2_historical_sidecar`, `assemble_v2_future_sidecar`. PRP-35
   Task 8 promises this. The model_zoo backtest path reuses them.
10. `FeatureGroup` enum names match the values used in
    `DEFAULT_V2_GROUPS = (TARGET_HISTORY, ROLLING, TREND, CALENDAR,
    PRICE_PROMO, LIFECYCLE)`. PRP-35 Task 1 promises this.

If ANY assumption above fails Task 1 verification: open a `chore(docs):
refresh PRP-36 against PRP-35 final contract (#<this-issue>)` PR that
edits THIS PRP file in place, THEN proceed to Task 2.

---

## Anti-Patterns to Avoid

- ❌ Don't modify any V1 builder signature, return type, or body — PRP-35
  froze V1. Dispatch lives at the service layer.
- ❌ Don't cite `HistGradientBoostingRegressor.feature_importances_` — it
  does not exist on HGBR (memory `histgbr-no-feature-importances`). The
  existing `FeatureImportanceUnavailableError` is the contract; don't
  weaken it.
- ❌ Don't add `permutation_importance` behind the existing explainability
  endpoints in this PRP — that's a separate PRP (compute budget + UI
  question).
- ❌ Don't introduce a new Alembic migration; every new field rides in
  existing JSONB columns.
- ❌ Don't change the demo pipeline (`scripts/run_demo.py` /
  `app/features/demo/pipeline.py`) — it's Slice C territory.
- ❌ Don't change `bundle_hash` for in-flight bundles — every config-default
  change must justify itself with a regression test AND a `schema_version`
  bump if it's behaviour-changing.
- ❌ Don't compare across `feature_frame_version` in champion/challenger or
  stale-alias logic — that silently breaks the alias contract.
- ❌ Don't import `lightgbm` or `xgboost` at module load time; the lazy
  imports stay inside `fit`.
- ❌ Don't add an agent tool in this PRP — `agent_require_approval` is
  unchanged.
- ❌ Don't widen `app/shared/feature_frames/**` to import from any features
  slice — the AST-walk invariant catches it.
- ❌ Don't refactor `data_platform.models` consumers (memory
  `data-platform-shared-orm-layer`) — that's a different PRP.
- ❌ Don't fabricate per-horizon-bucket data — if no test point falls in a
  bucket, drop the bucket from the response.
- ❌ Don't promote a "newer-but-worse" run. The Promote affordance in
  Slice C will surface the comparable-run metrics — this PRP's job is to
  make those metrics correctly computed and correctly grouped.

---

## Confidence

**Confidence: 7/10** for one-pass implementation success after PRP-35 lands.

What grounds the 7:
- The four library claims this PRP needs (HGBR no fi, RF has fi 1-D,
  RF deterministic with `random_state + n_jobs=1`, np.average weights) are
  verified at runtime against the live env (sklearn 1.8.0, numpy 2.4.1).
  Commands captured in "Known Gotchas".
- Every seam is anchored at file:line — both the existing surfaces (model
  factory, _MODEL_FAMILY_MAP, _find_duplicate, _alias_staleness, metrics
  calculator) and the PRP-35-created surfaces.
- The "comparable run" rule resolves the ops semantic cleanly: same grain
  + overlapping window + same V. The mismatch path gets its own enum
  value so Slice C can surface it distinctly.
- The bucket-id naming is stable string keys; the empty-bucket drop rule
  keeps the JSON terse for Slice C.

What costs the 3 points:
- **PRP-35 has not landed.** Task 1 is the gate; until it succeeds, every
  later task is conditional on assumptions matching reality. The
  "Unresolved Contract Assumptions" list spells out exactly what to
  re-verify.
- `lightgbm` / `xgboost` are not installed in the default venv. Config
  tightening is paper-only until the extras are installed; this PRP cannot
  prove the runtime tightening works without an integration step.
- Optional models (`trend_regression_baseline`, `random_forest`) add
  surface area; if the planning review punts either, several tasks shrink.
  Recommended position: ship both.
