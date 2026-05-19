# BaseForecaster Feature Contract

## Summary

Formalize the existing `BaseForecaster` interface as the canonical model contract for both target-only baseline models and feature-aware ML models. Add a `requires_features` class attribute or property so services can branch on model capability without `isinstance` checks or a new `FeatureAwareForecaster` subclass.

This is a small but important foundation item for the Advanced ML Model Zoo.

## Why It Fits ForecastLabAI

ForecastLabAI already has a forecasting model interface where models expose:

- `fit(y, X=None)`
- `predict(horizon, X=None)`

Baseline models can ignore `X`; regression and future advanced models need `X`. Introducing a second base class too early would create inheritance churn without solving the harder platform problems: feature-frame contracts, future feature availability, leakage safety, and train/serve skew.

## User Value

- Keeps current baseline behavior stable.
- Makes feature-aware model support explicit.
- Prepares LightGBM/XGBoost/Prophet-like work without API churn.
- Avoids brittle `isinstance` checks in services.
- Reduces persistence risk for existing joblib model bundles.

## Proposed Design

Keep `BaseForecaster` as the single canonical model interface.

Add a class-level capability flag:

```python
requires_features: ClassVar[bool] = False
```

Baseline models:

```python
class NaiveForecaster(BaseForecaster):
    requires_features = False
```

Feature-aware models:

```python
class RegressionForecaster(BaseForecaster):
    requires_features = True
```

Service code branches on the model contract:

```python
if model.requires_features:
    # require and validate X / X_future
else:
    # y-only baseline path
```

## Backend Design

Likely files:

- `app/features/forecasting/models.py`
- `app/features/forecasting/service.py`
- `app/features/forecasting/tests/test_models.py`
- `examples/models/model_interface.md`
- `docs/PHASE/4-FORECASTING.md`

The change should document that:

- `fit(y, X=None)` is the universal train contract.
- `predict(horizon, X=None)` is the universal predict contract.
- `requires_features = False` models may ignore `X`.
- `requires_features = True` models must receive valid feature frames.
- A `FeatureAwareForecaster` subclass should be revisited only after multiple advanced model families need shared behavior beyond the flag.

## MVP Scope

- Add `requires_features` to the model interface.
- Set it explicitly on existing baseline and regression models.
- Update service branching where it currently relies on model type checks.
- Add tests proving baseline models ignore `X` and regression requires it.
- Update model interface documentation.

## Full Version

- Add richer capability flags if needed:
  - `supports_prediction_intervals`
  - `supports_feature_importance`
  - `supports_exogenous_future`
  - `supports_recursive_prediction`
- Introduce a `FeatureAwareForecaster` subclass only when shared advanced-model behavior justifies the abstraction.

## Risks

- Adding a flag without tests can become another implicit contract.
- Service code must not silently pass `None` into feature-aware models.
- Documentation must be precise so future LightGBM work does not reinterpret the contract.

## Validation Plan

- Unit tests for each existing model's `requires_features` value.
- Unit tests proving baseline models still fit/predict with `X=None`.
- Unit tests proving feature-aware models reject missing required features.
- Regression tests for existing forecasting service behavior.
- `uv run pytest -q -m "not integration"`
- `uv run ruff check app tests`

## Documentation

- scikit-learn estimator development guide: https://scikit-learn.org/stable/developers/develop.html
- scikit-learn Pipeline composition: https://scikit-learn.org/stable/modules/compose.html
- scikit-learn model persistence: https://scikit-learn.org/stable/model_persistence.html
- Joblib persistence documentation: https://joblib.readthedocs.io/en/stable/persistence.html
- Pydantic documentation: https://docs.pydantic.dev/latest/

