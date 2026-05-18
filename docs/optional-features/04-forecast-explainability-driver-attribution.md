# Forecast Explainability and Driver Attribution

## Summary

Add explanations that show which demand drivers influenced a forecast or backtest outcome: seasonality, lagged demand, trend, promotions, price changes, inventory limits, stockouts, lifecycle stage, holidays, and replenishment events.

## Why It Fits ForecastLabAI

The repository already emphasizes time-safe feature engineering and retail domain signals. Explainability would make those signals visible to users and connect the backend ML logic to frontend decisions.

## User Value

- Users can understand why a forecast changed.
- Operators can distinguish true demand from stockout-constrained demand.
- Model comparisons become more meaningful than "lower WAPE wins."
- Agents can cite feature-level reasons when recommending a model or promotion.

## Proposed UX

Add explanation panels to:

- Forecast visualization.
- Backtest results.
- Run detail page.
- Scenario planner.

Display:

- Top positive and negative drivers.
- Historical context chart.
- Feature contribution table.
- "Reason codes" such as promotion lift, holiday effect, stockout risk, lifecycle decay.
- Confidence level and caveats.

## Backend Design

Candidate endpoints:

- `GET /forecasting/explanations/{job_id}`
- `GET /registry/runs/{run_id}/explanations`
- `POST /explain/forecast`

For simple models, explanations can be rule-based:

- Naive: last observation.
- Seasonal naive: matching seasonal positions.
- Moving average: recent window mean.

For advanced ML models, add model-specific explainers:

- LightGBM/XGBoost: feature importance, SHAP-like contribution summaries if dependency is acceptable.
- Prophet-like: trend, seasonality, holiday, regressor components.

## Data Requirements

Store explanation metadata with prediction jobs or model runs:

- Feature names.
- Feature values.
- Contribution scores.
- Explanation method.
- Model version.
- Generated timestamp.

Avoid storing large raw explainer objects unless there is a clear reuse case.

## MVP Scope

- Rule-based explanations for existing baseline models.
- Run detail explanation section.
- Forecast job explanation section.
- Agent-readable explanation summary.

## Full Version

- SHAP-style contribution summaries for tree models.
- Component decomposition for Prophet-like models.
- Natural-language explanation generation grounded in computed values.
- Explanation drift tracking across model versions.

## Risks

- Explanation quality depends on model family.
- Feature attribution can be misleading if correlated features are interpreted causally.
- SHAP dependencies may add runtime weight.
- Explanations must distinguish correlation, contribution, and business causality.

## Validation Plan

- Unit tests for baseline explanation logic.
- Snapshot tests for explanation schemas.
- Browser QA for forecast/run detail pages.
- Tests that explanations only reference features actually available to the model.

## Documentation

- SHAP documentation: https://shap.readthedocs.io/en/stable/
- SHAP TreeExplainer API: https://shap.readthedocs.io/en/stable/generated/shap.TreeExplainer.html
- scikit-learn inspection and permutation importance: https://scikit-learn.org/stable/modules/permutation_importance.html
- LightGBM Python API: https://lightgbm.readthedocs.io/en/stable/Python-API.html
- XGBoost Python package documentation: https://xgboost.readthedocs.io/en/stable/python/
- Prophet documentation: https://facebook.github.io/prophet/docs/quick_start.html
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework
- FastAPI documentation: https://fastapi.tiangolo.com/
- Recharts documentation: https://recharts.org/en-US/
