# Advanced ML Model Zoo

## Summary

Add serious forecasting models beyond current baselines:

- LightGBM
- XGBoost
- Prophet-like models with trend, seasonality, holiday, and regressor components

The goal is not just to add dependencies, but to upgrade ForecastLabAI from baseline forecasting to a credible model comparison platform.

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
