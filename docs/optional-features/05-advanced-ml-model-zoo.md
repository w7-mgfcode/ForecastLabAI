# Advanced ML Model Zoo

## Summary

Add serious forecasting models beyond current baselines:

- LightGBM (opt-in extra)
- XGBoost (opt-in extra)
- Random Forest (pure scikit-learn, opt-in flag — PRP-36)
- Prophet-like models with trend, seasonality, holiday, and regressor components

PRP-36 also adds richer **always-on baselines** so a feature-aware
model's "extra complexity is justified" statement actually means
something:

- `weighted_moving_average` — linear or exponential weight strategy
- `seasonal_average` — average of last N seasonal cycles (with optional
  outlier-trim)
- `trend_regression_baseline` — Ridge over an elapsed-day index + dow/month
  one-hots

The goal is not just to add dependencies, but to upgrade ForecastLabAI
from baseline forecasting to a credible model comparison platform.

### PRP-36 — backtest comparison contract

`POST /backtesting/run` now returns, in addition to the existing
aggregate metrics:

- `aggregated_metrics.rmse` — root-mean-squared error alongside
  MAE / sMAPE / WAPE / bias.
- `fold_results[*].horizon_bucket_metrics` — per-fold, per-bucket
  metric dict, keyed by stable bucket ids: `h_1_7`, `h_8_14`,
  `h_15_28`, `h_29_plus`. **Empty buckets are dropped** (a 14-day
  horizon's payload never carries `h_29_plus`).
- `main_model_results.bucketed_aggregated_metrics` and
  `baseline_results[*].bucketed_aggregated_metrics` — per-bucket means
  across folds. `None` when every fold reported an empty bucket dict.

This is additive — older clients keep working unchanged.

### PRP-36 — diagnostic script

`examples/forecasting/model_zoo_compare.py` exercises every available
model (always-on baselines + opt-in feature-aware models) for one
`(store_id, product_id)` grain. It prints an aggregate metrics + per-bucket
WAPE table without writing anything outside the existing
`/forecasting/train` + `/backtesting/run` flow:

```bash
uv run python examples/forecasting/model_zoo_compare.py \
    --store-id 1 --product-id 1 \
    --start-date 2025-01-01 --end-date 2025-12-31
```

Optional models behind a flag (LightGBM / XGBoost / Random Forest) are
SKIPPED with a printed note when their flag is off — the script never
fails the run because an opt-in model is missing.

## Why It Fits ForecastLabAI

The current forecasting layer already has:

- A model interface in `app/features/forecasting/models.py`.
- Pydantic model config schemas.
- Training and prediction services.
- Backtesting and registry integrations.
- Feature engineering with time-safe feature generation.

Advanced models can reuse the existing interfaces if they are introduced carefully.

## User Value

- Better accuracy for non-trivial retail demand patterns.
- More credible model comparisons in demos.
- Support for exogenous signals such as price, promotions, holidays, inventory, markdowns, lifecycle, and replenishment.
- Foundation for scenario simulation and explainability.

## Model Families

### LightGBM

Best fit:

- Tabular features.
- Large portfolios of store-SKU time series.
- Fast training.
- Strong accuracy on engineered lag/rolling/calendar features.

Suggested config:

- `n_estimators`
- `learning_rate`
- `num_leaves`
- `max_depth`
- `min_child_samples`
- `subsample`
- `colsample_bytree`
- `random_state`

### XGBoost

Best fit:

- Strong tabular benchmark.
- Robust regularization.
- Useful comparison against LightGBM.

Suggested config:

- `n_estimators`
- `learning_rate`
- `max_depth`
- `subsample`
- `colsample_bytree`
- `reg_alpha`
- `reg_lambda`
- `random_state`

### Prophet-like Models

Use this term intentionally unless choosing the actual `prophet` dependency. A Prophet-like model can be implemented with:

- Trend component.
- Weekly/yearly seasonality.
- Holiday/event regressors.
- Optional changepoints.
- Optional external regressors.

Options:

- Use `prophet` if dependency weight is acceptable.
- Use `statsforecast`/`sktime` style models if compatible.
- Implement a lightweight additive model using sklearn regression over generated trend/seasonal features.

## Architecture Requirements

Current baseline models can train from `y` only. Advanced models need feature matrices:

- `fit(y, X=None)`
- `predict(horizon, X=None)`

This means the forecasting service must be able to:

- Build historical feature frames for training.
- Build future feature frames for prediction.
- Persist feature config with model config.
- Reject prediction if future features are missing.

## Backend Design

Likely files:

- `app/features/forecasting/models.py`
- `app/features/forecasting/schemas.py`
- `app/features/forecasting/service.py`
- `app/features/featuresets/service.py`
- `app/features/backtesting/service.py`
- `app/features/registry/schemas.py`

Potential new abstractions:

- `FeatureAwareForecaster`
- `TrainingFrame`
- `PredictionFrame`
- `FutureFeatureBuilder`

## MVP Scope

Add one advanced model first: LightGBM or a lightweight sklearn gradient boosting fallback if avoiding new dependencies.

MVP deliverables:

- Config schema.
- Model implementation.
- Feature-frame generation for training.
- Prediction requiring future calendar features.
- Backtesting integration.
- Registry metadata.
- Tests proving deterministic training.

## Full Version

- LightGBM, XGBoost, and Prophet-like models.
- Hyperparameter search.
- Portfolio/global models across many store-SKU pairs.
- Feature importance and explanations.
- Scenario-compatible future regressors.
- Model-specific validation gates.

## Dependency Strategy

Do not add all dependencies at once. Recommended sequence:

1. Add LightGBM support behind optional dependency group.
2. Add XGBoost as a second tree model.
3. Add Prophet-like model only after future regressor handling is stable.

Example dependency groups:

- `ml-lightgbm`
- `ml-xgboost`
- `ml-prophet`

## Risks

- Native dependencies may complicate installation.
- Future feature generation is easy to get wrong.
- Backtests must prevent leakage for every generated feature.
- Training can become slow if portfolio-scale models are introduced without job orchestration.

## Validation Plan

- Unit tests for model configs.
- Unit tests for deterministic output with fixed random state.
- Leakage tests for feature-frame generation.
- Backtesting tests comparing baseline vs advanced model.
- Registry persistence tests.
- Browser QA for model selection, run detail, comparison, and forecast visualization.

## Documentation

- LightGBM documentation: https://lightgbm.readthedocs.io/
- LightGBM Python API: https://lightgbm.readthedocs.io/en/stable/Python-API.html
- LightGBM parameters: https://lightgbm.readthedocs.io/en/stable/Parameters.html
- XGBoost documentation: https://xgboost.readthedocs.io/en/stable/
- XGBoost Python package documentation: https://xgboost.readthedocs.io/en/stable/python/
- XGBoost parameters: https://xgboost.readthedocs.io/en/stable/parameter.html
- Prophet documentation: https://facebook.github.io/prophet/docs/quick_start.html
- Prophet seasonality, holidays, and regressors: https://facebook.github.io/prophet/docs/seasonality,_holiday_effects,_and_regressors.html
- scikit-learn model persistence: https://scikit-learn.org/stable/model_persistence.html
- scikit-learn TimeSeriesSplit: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- Pandas time series documentation: https://pandas.pydata.org/docs/user_guide/timeseries.html
- Joblib persistence documentation: https://joblib.readthedocs.io/en/stable/persistence.html
