# INITIAL-MLZOO-A-foundation-feature-frames.md - Feature-Aware Forecasting Foundation

## FEATURE:

Create the foundation for feature-aware forecasting in ForecastLabAI.

This is the first MLZOO PRP input and should become PRP-29. It must not implement LightGBM, XGBoost, Prophet-like models, frontend UI, explainability UI, hyperparameter search, or portfolio/global orchestration. Its job is to make the existing forecasting layer capable of supporting future advanced ML models without breaking current baseline forecasters.

Goals:

- Define a feature-aware forecasting contract that supports `fit(y, X=None)` and `predict(horizon, X=None)`.
- Preserve existing target-only baseline models: `naive`, `seasonal_naive`, and `moving_average`.
- Define historical training feature-frame requirements.
- Define future prediction feature-frame requirements.
- Add or document leakage-safe feature-frame generation rules.
- Add load-bearing leakage tests that prove future rows do not use future target values.
- Make future advanced models possible without adding their dependencies yet.

Expected user value:

- ForecastLabAI gains a safe foundation for serious ML forecasting.
- Future LightGBM/XGBoost/Prophet-like work can build on a tested frame contract.
- Scenario simulation and explainability can later depend on a consistent feature-frame interface.

Recommended user story:

As a forecasting engineer,
I want a leakage-safe feature-frame contract for training and prediction,
So that advanced ML models can be added without breaking baseline models or leaking future data.

Out of scope:

- LightGBM implementation.
- XGBoost implementation.
- Prophet-like implementation.
- New database migrations unless absolutely required.
- Frontend pages.
- Agent tools.
- Hyperparameter search.

## EXAMPLES:

Read these before PRP creation:

- `docs/optional-features/05-advanced-ml-model-zoo.md`
  - Full feature vision and risks.

- `PRPs/INITIAL/INITIAL-5.md`
  - Existing forecasting model brief.

- `docs/PHASE/4-FORECASTING.md`
  - Current forecasting layer documentation.

- `app/features/forecasting/models.py`
  - Existing `BaseForecaster` and baseline model implementations.

- `app/features/forecasting/schemas.py`
  - Existing model config schemas and discriminated union pattern.

- `app/features/forecasting/service.py`
  - Existing train/predict orchestration.

- `app/features/forecasting/persistence.py`
  - Existing `ModelBundle` persistence.

- `app/features/featuresets/service.py`
  - Existing time-safe feature computation.

- `app/features/featuresets/schemas.py`
  - Feature configuration schemas.

- `app/features/featuresets/tests/test_leakage.py`
  - Existing leakage tests to mirror and extend.

- `app/features/backtesting/service.py`
  - Current backtesting integration points.

Potential example artifacts:

- `examples/models/feature_frame_contract.md`
  - Describes historical and future frame shape, required columns, safe/unsafe feature classes.

## DOCUMENTATION:

- scikit-learn estimator interface conventions: https://scikit-learn.org/stable/developers/develop.html
- scikit-learn Pipeline composition: https://scikit-learn.org/stable/modules/compose.html
- scikit-learn TimeSeriesSplit: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- Pandas time series documentation: https://pandas.pydata.org/docs/user_guide/timeseries.html
- Pydantic documentation: https://docs.pydantic.dev/latest/
- Joblib persistence documentation: https://joblib.readthedocs.io/en/stable/persistence.html

## OTHER CONSIDERATIONS:

This PRP is primarily about contracts and leakage safety.

Required decisions:

- How to represent feature-aware models without forcing every baseline model to require `X`.
- Whether to introduce a `FeatureAwareForecaster` protocol/base class or extend the existing base interface only.
- Where historical training frames are built.
- Where future prediction frames are built.
- Which feature classes are safe for future frames:
  - Safe: calendar features known in advance.
  - Conditionally safe: lag/rolling features generated from historical tail and prior predictions.
  - Unsafe unless explicitly supplied: future price, promotion, inventory, markdown, exogenous signals.
- How to reject missing future features instead of silently filling misleading defaults.

Validation expectations:

- Existing baseline forecasting tests still pass.
- New feature-frame contract tests exist.
- New leakage tests prove future target values are not used.
- Backtesting remains time-safe.
- `uv run pytest -q -m "not integration"` should pass.
- `uv run ruff check app tests` should pass for touched Python code.

Important gotchas:

- Do not break current target-only baseline forecasters.
- Do not add LightGBM or other heavy ML dependencies in this PRP.
- Do not silently convert unknown future exogenous values into zeros.
- Do not let training frames include rows after the cutoff date.
- Do not let future prediction frames read true future targets.

