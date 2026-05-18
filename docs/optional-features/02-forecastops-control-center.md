# ForecastOps Control Center

## Summary

Build a central operational dashboard for model health, forecast freshness, job failures, alias status, drift signals, and retraining candidates. The current app has useful individual pages for runs, jobs, forecasts, and analytics; the Control Center connects them into one operator workflow.

## Why It Fits ForecastLabAI

ForecastLabAI already has:

- Jobs in `app/features/jobs/`.
- Model registry and aliases in `app/features/registry/`.
- Backtesting metrics in `app/features/backtesting/`.
- Analytics KPIs in `app/features/analytics/`.
- Forecast visualization in `frontend/src/pages/visualize/forecast.tsx`.
- Explorer pages for jobs and runs.

This feature is the natural next layer above those primitives.

## User Value

- Operators can quickly answer: "Which forecasts need attention?"
- Demo reviewers see a mature ForecastOps story instead of isolated CRUD pages.
- Failed jobs and stale models become visible before they affect decisions.
- Retraining candidates can be ranked by value, error, and recency.

## Proposed UX

Create a new route, for example `/ops`.

Sections:

- System health: API, database, embedding provider, latest successful job.
- Forecast freshness: latest prediction per store/SKU or model alias.
- Model health: WAPE, sMAPE, MAE, bias, stability, last backtest date.
- Job health: failed, pending, running, cancelled, completed counts.
- Alias state: production alias, candidate alias, stale alias warnings.
- Retraining queue: ranked store/product pairs needing retrain.
- Action drawer: rerun backtest, train candidate, compare run, promote alias.

## Backend Design

Add an aggregation endpoint, likely a new feature slice:

- `app/features/ops/routes.py`
- `app/features/ops/service.py`
- `app/features/ops/schemas.py`

Candidate endpoints:

- `GET /ops/summary`
- `GET /ops/retraining-candidates`
- `GET /ops/model-health`
- `GET /ops/job-health`

The service should query existing tables; avoid duplicating model state.

## Frontend Design

Likely files:

- `frontend/src/pages/ops.tsx`
- `frontend/src/hooks/use-ops-summary.ts`
- `frontend/src/components/ops/*`
- Add nav item in `frontend/src/lib/constants.ts`

Keep the page dense and operational: cards, tables, filters, and compact charts.

## MVP Scope

- One `/ops` page.
- Summary cards for jobs, runs, aliases, data freshness.
- Table of stale or failed items.
- Links to existing Explorer detail pages.

## Full Version

- Retraining candidate scoring.
- Drift indicators.
- Bulk action queue.
- Human approval for promotion.
- WebSocket updates for running jobs.
- Exportable incident report.

## Risk Model

- False-positive drift alerts can reduce trust.
- Aggregation queries may become expensive without indexes.
- Actions must not bypass existing approval gates.
- The UI can become noisy if every metric is surfaced at once.

## Validation Plan

- Unit tests for scoring and stale detection.
- Integration tests against seeded jobs/runs.
- Frontend tests for empty, healthy, warning, and failure states.
- Browser QA for navigation from Control Center to runs/jobs/detail pages.

## Documentation

- FastAPI documentation: https://fastapi.tiangolo.com/
- SQLAlchemy asyncio documentation: https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html
- scikit-learn model persistence: https://scikit-learn.org/stable/model_persistence.html
- scikit-learn TimeSeriesSplit: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- MLflow Model Registry documentation: https://www.mlflow.org/docs/latest/ml/model-registry/
- OpenTelemetry Python documentation: https://opentelemetry.io/docs/languages/python/
- OpenTelemetry FastAPI instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html
- TanStack Query React documentation: https://tanstack.com/query/latest/docs/framework/react/overview
- Recharts documentation: https://recharts.org/en-US/
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework
