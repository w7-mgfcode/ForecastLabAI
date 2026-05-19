# INITIAL-MLZOO-B-lightgbm-first-model.md - LightGBM First Advanced Model

## FEATURE:

Add the first advanced feature-aware model to ForecastLabAI after the MLZOO foundation is merged.

Preferred model: LightGBM.

Fallback model: sklearn `HistGradientBoostingRegressor` or another sklearn-native gradient boosting model if LightGBM creates unacceptable dependency or CI risk.

This PRP must depend on `INITIAL-MLZOO-A-foundation-feature-frames.md` being implemented first.

Goals:

- Add one advanced model config schema.
- Add one feature-aware model implementation.
- Support deterministic training.
- Integrate with forecasting train/predict.
- Integrate with backtesting.
- Persist model metadata needed for reproducibility.
- Preserve all existing baseline model behavior.

Out of scope:

- XGBoost.
- Prophet-like models.
- Hyperparameter search.
- Portfolio/global models.
- Frontend model administration.
- Explainability UI.

## EXAMPLES:

Read these before PRP creation:

- `PRPs/INITIAL/INITIAL-MLZOO-A-foundation-feature-frames.md`
  - Required prerequisite.

- `docs/optional-features/05-advanced-ml-model-zoo.md`
  - Full advanced model vision.

- `app/features/forecasting/models.py`
  - Model factory and baseline model patterns.

- `app/features/forecasting/schemas.py`
  - Model config schema patterns.

- `app/features/forecasting/service.py`
  - Training/prediction service integration.

- `app/features/forecasting/persistence.py`
  - Model bundle save/load behavior.

- `app/features/backtesting/service.py`
  - Backtesting orchestration.

- `app/features/registry/service.py`
  - Registry run metadata patterns.

Potential example artifacts:

- `examples/models/advanced_lightgbm.py`
  - Minimal training/prediction example.

## DOCUMENTATION:

- LightGBM documentation: https://lightgbm.readthedocs.io/
- LightGBM Python API: https://lightgbm.readthedocs.io/en/stable/Python-API.html
- LightGBM parameters: https://lightgbm.readthedocs.io/en/stable/Parameters.html
- scikit-learn HistGradientBoostingRegressor: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html
- scikit-learn model persistence: https://scikit-learn.org/stable/model_persistence.html
- Joblib persistence documentation: https://joblib.readthedocs.io/en/stable/persistence.html
- Pydantic documentation: https://docs.pydantic.dev/latest/

## OTHER CONSIDERATIONS:

Dependency strategy is the main open risk.

Required decisions:

- Whether to add LightGBM as a hard dependency, optional dependency group, or defer to sklearn fallback.
- Exact advanced model config fields.
- How model dependency versions are captured in registry/runtime metadata.
- How prediction rejects missing future feature frames.

Recommended defaults:

- Use fixed `random_state` from settings.
- Start with single store/product training.
- Keep the first config conservative.
- Avoid hyperparameter search.
- Persist feature column order.

Validation expectations:

- Config schema tests.
- Deterministic training tests.
- Save/load persistence tests.
- Backtesting integration test comparing baseline and advanced model path.
- Tests proving baselines still work unchanged.

