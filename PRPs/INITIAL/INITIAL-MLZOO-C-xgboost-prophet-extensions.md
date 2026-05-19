# INITIAL-MLZOO-C-xgboost-prophet-extensions.md - XGBoost and Prophet-like Extensions

## FEATURE:

Extend the Advanced ML Model Zoo after the feature-frame foundation and first advanced model path are stable.

This INITIAL is for later work, not PRP-29.

Goals:

- Add XGBoost as a second tree-based feature-aware model.
- Add a Prophet-like additive model path or choose the real Prophet dependency if justified.
- Support holiday/regressor-style features where appropriate.
- Add model-family-specific validation and metadata.

Out of scope:

- Foundation feature-frame work.
- First advanced model architecture.
- Frontend/explainability polish unless explicitly needed.
- Hyperparameter search unless separately scoped.

## EXAMPLES:

Read these before PRP creation:

- `PRPs/INITIAL/INITIAL-MLZOO-A-foundation-feature-frames.md`
  - Foundation dependency.

- `PRPs/INITIAL/INITIAL-MLZOO-B-lightgbm-first-model.md`
  - First advanced model pattern to follow.

- `app/features/forecasting/models.py`
  - Model factory and advanced model pattern.

- `app/features/forecasting/schemas.py`
  - Config schema pattern.

- `app/features/featuresets/service.py`
  - Regressor and calendar feature source.

## DOCUMENTATION:

- XGBoost documentation: https://xgboost.readthedocs.io/en/stable/
- XGBoost Python package documentation: https://xgboost.readthedocs.io/en/stable/python/
- XGBoost parameters: https://xgboost.readthedocs.io/en/stable/parameter.html
- Prophet documentation: https://facebook.github.io/prophet/docs/quick_start.html
- Prophet seasonality, holidays, and regressors: https://facebook.github.io/prophet/docs/seasonality,_holiday_effects,_and_regressors.html
- scikit-learn model persistence: https://scikit-learn.org/stable/model_persistence.html
- Pandas time series documentation: https://pandas.pydata.org/docs/user_guide/timeseries.html

## OTHER CONSIDERATIONS:

- XGBoost should mirror the first advanced model path where possible.
- Prophet-like work should be carefully evaluated because dependency weight and API shape differ from sklearn-style regressors.
- Real Prophet support should be chosen only if install/runtime constraints are acceptable.
- A lightweight additive sklearn model may be safer than the real Prophet dependency.
- Holiday/regressor support must use known-in-advance or explicitly supplied future values.

