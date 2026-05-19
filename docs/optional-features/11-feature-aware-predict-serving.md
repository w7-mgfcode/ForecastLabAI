# Feature-Aware Forecasting Predict Serving

## Summary

Extend `POST /forecasting/predict` so feature-aware models can produce forecasts outside `/scenarios/simulate` when a leakage-safe future feature frame can be constructed or supplied.

Today feature-aware regression models are rejected by `/forecasting/predict` because the endpoint cannot supply future `X`. That is correct for the current foundation, but it becomes a missing serving capability once MLZOO-B introduces the first advanced model.

## Why It Fits ForecastLabAI

ForecastLabAI is evolving from y-only baseline forecasting toward ML forecasting with `y + X`. Scenario simulation already provides a context where future assumptions can produce `X_future`. The standard forecasting endpoint needs a safe, explicit serving path for feature-aware models too, but only after the shared feature-frame contract is stable.

## User Value

- Advanced models become usable through the normal forecast API.
- Forecast visualization can load predictions from feature-aware jobs.
- LightGBM and future XGBoost models can serve without requiring the scenario UI.
- The product can distinguish baseline forecasts, scenario forecasts, and assumptions-free ML forecasts.

## Proposed Design

Add feature-aware predict support in a later PRP, not in the foundation-only MLZOO-A work.

Supported future-frame modes:

1. **Calendar-only / history-tail mode**
   - Use known future calendar features.
   - Use historical tail for lag and rolling seeds.
   - Generate recursive target-derived features only from history and prior predictions.
   - Reject unsafe feature columns that require explicit future assumptions.

2. **Supplied future-frame mode**
   - Client or service supplies validated `X_future`.
   - API verifies required columns, order, dtypes, horizon length, and no target leakage.

3. **Scenario-backed mode**
   - Reuse saved scenario assumptions to construct `X_future`.
   - Clearly mark the result as scenario-conditioned.

## Backend Design

Likely files:

- `app/features/forecasting/routes.py`
- `app/features/forecasting/service.py`
- `app/features/forecasting/schemas.py`
- `app/shared/feature_frames/`
- `app/features/jobs/service.py`
- `frontend/src/pages/visualize/forecast.tsx`

Possible request additions:

- `feature_mode`: `baseline`, `history_calendar`, `supplied_frame`, `scenario`
- `future_frame`: optional structured future features
- `scenario_id`: optional saved scenario reference
- `history_tail_days`: optional bounded history window

The endpoint must reject feature-aware predictions when required future features are unavailable.

## MVP Scope

- Keep current rejection behavior until the first advanced model lands.
- Add a dedicated PRP later for `history_calendar` mode.
- Support only safe known-ahead features and recursive target-derived features.
- Return metadata that states how `X_future` was built.

## Full Version

- Supplied future-frame mode.
- Scenario-backed mode.
- Prediction interval support where available.
- Feature availability diagnostics.
- UI warnings when forecasts are assumptions-free vs scenario-conditioned.

## Risks

- Assumptions-free future frames can be misleading if users expect promotions, inventory, or exogenous events to be included.
- Recursive lag generation can leak future targets if implemented incorrectly.
- Train/serve skew can silently degrade advanced model quality.
- API shape can become too broad if scenario, supplied-frame, and history-calendar modes are mixed without clear validation.

## Validation Plan

- Unit tests for future-frame validation.
- Leakage tests proving `X_future` never reads true future targets.
- API tests:
  - baseline model predict still works
  - feature-aware predict rejects missing future features
  - feature-aware predict accepts valid history-calendar frame
  - unsafe future feature requirements produce clear errors
- Job result metadata tests.
- Browser QA for forecast visualization using a feature-aware prediction job.

## Documentation

- FastAPI documentation: https://fastapi.tiangolo.com/
- Pydantic documentation: https://docs.pydantic.dev/latest/
- scikit-learn TimeSeriesSplit: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- Pandas time series documentation: https://pandas.pydata.org/docs/user_guide/timeseries.html
- LightGBM Python API: https://lightgbm.readthedocs.io/en/stable/Python-API.html
- XGBoost Python package documentation: https://xgboost.readthedocs.io/en/stable/python/
- Recharts documentation: https://recharts.org/en-US/

