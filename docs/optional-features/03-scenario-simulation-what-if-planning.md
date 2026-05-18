# Scenario Simulation and What-If Planning

## Summary

Build a planner that lets users change future assumptions such as price, promotions, inventory, markdowns, lifecycle phase, holiday effects, and exogenous signals, then compare forecast outcomes against a baseline.

## Why It Fits ForecastLabAI

ForecastLabAI already models retail demand drivers:

- Price history, promotion, inventory, calendar, lifecycle, returns, replenishment, and markdown concepts exist in the data platform and seeder.
- Feature engineering already supports lagged, rolling, calendar, exogenous, lifecycle, promotion, and replenishment features.
- Forecast visualization already displays prediction job output.

This feature turns forecasting from "predict the future" into "plan possible futures."

## User Value

- Business users can ask "What if we discount this SKU by 15% next week?"
- Inventory users can estimate stockout risk under demand spikes.
- Demo reviewers see a high-value retail planning workflow.
- Agents can propose scenarios and request approval before running them.

## Proposed UX

Create route `/planner` or extend a future demand planner page.

Workflow:

1. Select store, product, horizon, and baseline model/run.
2. Define scenario assumptions:
   - Price changes.
   - Promotion windows.
   - Inventory constraints.
   - Holiday/event flags.
   - Markdown schedule.
   - Lifecycle stage override.
3. Run scenario forecast.
4. Compare baseline vs scenario:
   - Units delta.
   - Revenue delta.
   - Stockout risk.
   - Confidence/uncertainty.
5. Save scenario as a named plan.

## Backend Design

Candidate slice:

- `app/features/scenarios/routes.py`
- `app/features/scenarios/service.py`
- `app/features/scenarios/schemas.py`
- Optional models/migration if saved scenarios are needed.

Candidate endpoints:

- `POST /scenarios/simulate`
- `POST /scenarios`
- `GET /scenarios`
- `GET /scenarios/{scenario_id}`
- `DELETE /scenarios/{scenario_id}`

## Forecasting Requirements

The current baseline models mostly forecast from historical target series, so full what-if planning becomes much more useful after advanced ML models support exogenous features. For MVP, the feature can:

- Store and display scenarios.
- Run baseline forecast.
- Apply simple deterministic uplift/drag assumptions.
- Mark results as heuristic.

For the full version, models must consume future feature frames.

## MVP Scope

- Select store/product/horizon.
- Define price/promotion/inventory assumptions.
- Generate a heuristic baseline-vs-scenario comparison.
- Save scenario JSON.
- Render comparison chart.

## Full Version

- Feature-frame generator for future dates.
- Model support for exogenous regressors.
- Scenario library.
- Multi-scenario comparison.
- Agent-generated scenario suggestions.
- Approval flow for operational recommendations.

## Risks

- Users may over-trust heuristic scenarios.
- Future feature generation can leak future information if not clearly separated from historical features.
- Scenario forecasts need uncertainty bounds or confidence labeling.
- Strong validation is needed before exposing revenue impact claims.

## Validation Plan

- Schema tests for scenario inputs.
- Unit tests for deterministic future feature generation.
- API tests for simulate/save/list.
- Browser QA for creating, comparing, and saving a scenario.
- Explicit tests preventing historical leakage into future scenario frames.

## Documentation

- FastAPI documentation: https://fastapi.tiangolo.com/
- Pydantic documentation: https://docs.pydantic.dev/latest/
- scikit-learn TimeSeriesSplit: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- LightGBM Python API: https://lightgbm.readthedocs.io/en/stable/Python-API.html
- XGBoost Python package documentation: https://xgboost.readthedocs.io/en/stable/python/
- Prophet documentation: https://facebook.github.io/prophet/docs/quick_start.html
- Pandas time series documentation: https://pandas.pydata.org/docs/user_guide/timeseries.html
- Recharts documentation: https://recharts.org/en-US/
- TanStack Query React documentation: https://tanstack.com/query/latest/docs/framework/react/overview
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework
