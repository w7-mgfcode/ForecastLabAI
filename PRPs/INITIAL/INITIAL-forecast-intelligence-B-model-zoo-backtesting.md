# INITIAL-forecast-intelligence-B-model-zoo-backtesting.md - Forecast Intelligence B: Model Zoo and Backtesting

## FEATURE:

Upgrade ForecastLabAI's forecasting model layer so richer historical features actually improve forecasts, backtests, model selection, and registry decisions.

This slice depends on Forecast Intelligence A if it needs Feature Frame V2. It should not redefine the feature contract itself. Its job is to consume the richer feature frame through the existing forecasting model interface and make the model zoo easier to compare and operationalize.

Current repo state:

- Existing model types:
  - `naive`
  - `seasonal_naive`
  - `moving_average`
  - `regression` using `HistGradientBoostingRegressor`
  - `prophet_like` using a Ridge additive pipeline
  - `lightgbm` behind optional `ml-lightgbm` extra and `forecast_enable_lightgbm`
  - `xgboost` behind optional `ml-xgboost` extra and `forecast_enable_xgboost`
- `model_family_for()` maps models into `baseline`, `tree`, and `additive`.
- Feature-aware models require `X` for fit and predict.
- Plain `POST /forecasting/predict` rejects feature-aware models because it cannot provide future `X`; scenario simulation handles feature-aware re-forecasting through `model_exogenous`.
- Backtesting already exists and must remain leakage-safe.
- Registry stores model runs, metrics, artifacts, aliases, and model family metadata.

Problem:

The app has advanced model classes, but the user workflow still makes it easy to think only in terms of simple baselines. The next step is not just "add more algorithms"; it is to create a disciplined comparison path:

- better baseline variants
- better feature-aware model configs
- fair backtesting across the same data windows
- metric-driven champion/challenger decisions
- model health that distinguishes "newer" from "better"
- artifact and feature metadata that explain why a model won

Goals:

1. Add stronger baseline models:
   - `weighted_moving_average`
   - `seasonal_average`
   - optionally `trend_regression_baseline`

2. Improve feature-aware model configs:
   - allow selecting Feature Frame V1 or V2 where supported
   - expose conservative hyperparameters for `regression`, `prophet_like`, `lightgbm`, and `xgboost`
   - optionally add `random_forest` as a pure scikit-learn feature-aware model if the PRP finds it valuable and reviewable

3. Improve backtesting:
   - support V2 feature frames per fold without leakage
   - compare baselines and feature-aware models on identical folds
   - report metrics by horizon bucket, not only aggregate metrics
   - include WAPE, sMAPE, MAE, bias, and optional RMSE
   - record fold-level metadata needed for UI inspection

4. Improve registry/model selection:
   - store enough metadata to know which feature frame and feature groups trained each run
   - distinguish created-at freshness from data-window freshness
   - make stale alias logic metric-aware where possible
   - support champion/challenger comparison for the same `(store_id, product_id)` and comparable data windows

5. Improve explainability/metadata:
   - feature-aware models should expose feature importances where available
   - `prophet_like` should keep additive decomposition into trend, seasonality, and regressor components
   - baseline models should retain simple arithmetic explanations

Recommended user stories:

- As a demand planner, I want to compare `seasonal_naive`, `seasonal_average`, `weighted_moving_average`, `regression`, and `prophet_like` on the same history so I can see whether extra complexity is justified.
- As a forecasting engineer, I want backtests to use the exact feature frame that prediction will use so that model rankings are trustworthy.
- As an operator, I want a champion alias to be stale only when a newer comparable run is better or requires review, not merely because any newer run exists.

Out of scope:

- Building the frontend control surface. That belongs to Forecast Intelligence C.
- Redesigning the database registry from scratch.
- Adding managed-cloud model services.
- AutoML or large hyperparameter sweeps.
- Changing audit timestamps to make historical demo runs "look old".
- Any model that cannot be deterministic enough for this repo's reproducibility goals.

Expected model additions:

1. `weighted_moving_average`
   - Target-only baseline.
   - Gives more weight to recent observations.
   - Good for short-term trend without full feature-aware machinery.
   - Config fields: `window_size`, `decay` or explicit weight strategy.

2. `seasonal_average`
   - Target-only baseline.
   - Forecasts each horizon day from the average of prior matching seasonal positions.
   - Example: next Wednesday = average of last N Wednesdays.
   - More stable than `seasonal_naive`, which copies one prior cycle.
   - Config fields: `season_length`, `lookback_cycles`, optional `trim_outliers`.

3. `trend_regression_baseline`
   - Optional if scope permits.
   - Pure target/calendar model using elapsed time and simple calendar features.
   - Helps explain demand that rises or falls steadily.

4. `random_forest`
   - Optional feature-aware model.
   - Pure scikit-learn dependency, exposes `feature_importances_`.
   - Trade-off: weaker extrapolation for trend than additive/linear models, but useful as a robust non-linear baseline.

Feature-aware models to improve, not duplicate:

- `regression`
- `prophet_like`
- `lightgbm`
- `xgboost`

Backtesting expectations:

- Backtests must build training and future fold frames with the same feature-frame version.
- Do not slice future rows from a historical matrix if that would leak target values.
- Use gap-aware fold logic when configured.
- Store fold metrics in a shape the UI can render as:
  - total metric
  - metric by horizon bucket
  - metric by model family
  - metric by feature frame version

## EXAMPLES:

Reference existing repo examples and patterns:

- `app/features/forecasting/models.py`
  - Existing `BaseForecaster`, target-only models, feature-aware models, and factory.

- `app/features/forecasting/schemas.py`
  - Model config schema pattern and model family concepts.

- `app/features/forecasting/feature_metadata.py`
  - Feature importance extraction for tree/additive families.

- `app/features/backtesting/service.py`
  - Existing fold orchestration and metric calculation path.

- `app/features/backtesting/metrics.py`
  - Existing WAPE, sMAPE, MAE, bias, and related metric behavior.

- `app/features/registry/service.py`
  - Existing model run and alias persistence.

- `app/features/ops/service.py`
  - Existing model health and stale alias logic should be inspected before changing operational semantics.

- `app/features/explainability/service.py`
  - Baseline explanation path and retail signal warnings.

- `scripts/run_demo.py`
  - Existing end-to-end train/backtest/register/alias flow.

- `scripts/seed_historical_activity.py`
  - Local demo helper currently uncommitted in the working tree, if present, can inspire historical activity generation but should not be treated as merged project API.

Potential example artifact to add:

- `examples/forecasting/model_zoo_compare.py`
  - Runs a small local comparison for one `(store_id, product_id)` across baseline and feature-aware models.
  - Prints metrics and registry candidate summary.
  - Should rely on public services/API where practical.

## DOCUMENTATION:

External references to review during PRP creation and implementation:

- scikit-learn lagged features with `HistGradientBoostingRegressor`: https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html
- scikit-learn TimeSeriesSplit: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- scikit-learn RandomForestRegressor: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html
- LightGBM LGBMRegressor: https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.LGBMRegressor.html
- XGBoost Python API: https://xgboost.readthedocs.io/en/stable/python/
- Prophet seasonality, holidays, and regressors: https://facebook.github.io/prophet/docs/seasonality%2C_holiday_effects%2C_and_regressors.html
- Darts forecasting covariates: https://unit8co.github.io/darts/userguide/covariates.html
- Nixtla StatsForecast model overview, useful baseline vocabulary: https://nixtlaverse.nixtla.io/statsforecast/src/core/models.html

Internal docs to review:

- `docs/optional-features/05-advanced-ml-model-zoo.md`
- `docs/optional-features/09-model-champion-challenger-governance.md`
- `docs/optional-features/10-baseforecaster-feature-contract.md`
- `docs/optional-features/11-feature-aware-predict-serving.md`
- `docs/_base/API_CONTRACTS.md`
- `docs/_base/DOMAIN_MODEL.md`
- `docs/_base/REPO_MAP_INDEX.md`

## OTHER CONSIDERATIONS:

Implementation constraints:

- Preserve the scikit-learn-style `fit(y, X=None)` and `predict(horizon, X=None)` contract.
- Do not break target-only baseline forecasters.
- Gate optional dependencies exactly as the repo already does for LightGBM and XGBoost.
- Keep deterministic fitting where possible:
  - fixed `random_state`
  - single-threaded where needed
  - no stochastic sampling unless explicitly configured and reproducible
- Do not make model selection prefer "newer" when metrics are worse.
- Do not compare runs as champion/challenger unless they share a comparable grain and data window.
- Keep artifact hash verification intact.
- Keep all errors in API routes compatible with the project's RFC 7807 rules where routes are touched.

Testing requirements:

- Unit tests for each new model class.
- Factory tests for each new model config.
- Schema tests for strict config validation.
- Backtesting tests proving fold-level V2 features are leakage-safe.
- Registry tests for feature-frame metadata and comparable-run logic.
- Explainability/metadata tests for any new family.
- Route tests for training/backtesting new model types where route behavior changes.
- Integration tests for at least one feature-aware backtest path against real Docker Postgres if DB sidecar data is used.

Open design decisions for the PRP:

- Whether `random_forest` is worth adding now or should wait until Feature Frame V2 proves value through existing tree models.
- Whether `seasonal_average` should average by last N cycles or all available matching seasonal positions.
- Whether `weighted_moving_average` uses exponential decay or a simple linear weight ramp.
- How to mark "comparable" runs for stale alias and champion/challenger logic.
- Whether model health should classify `degrading` from all successful runs or only comparable successful runs.
- Whether registry should store the feature frame version as first-class columns or only in JSON metadata.

Recommended validation commands:

```bash
uv run ruff check app/features/forecasting app/features/backtesting app/features/registry app/features/ops app/features/explainability
uv run ruff format --check app/features/forecasting app/features/backtesting app/features/registry app/features/ops app/features/explainability
uv run mypy app/
uv run pyright app/
uv run pytest -v app/features/forecasting/tests app/features/backtesting/tests app/features/registry/tests app/features/ops/tests app/features/explainability/tests -m "not integration"
uv run pytest -v -m integration app/features/backtesting/tests app/features/registry/tests
```
