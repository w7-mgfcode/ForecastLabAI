# Demand Anomaly and Data Quality Monitor

## Summary

Add automated checks for suspicious demand, missing data, stockout-like patterns, price/promo anomalies, stale dimensions, and failed ingestion assumptions.

## Why It Fits ForecastLabAI

Forecasting quality depends on input data quality. ForecastLabAI already has a rich synthetic retail warehouse, analytics endpoints, seeder status, and jobs. A monitor gives the platform a practical reliability layer.

## User Value

- Detect bad data before training.
- Explain poor forecast performance caused by input issues.
- Provide a useful first screen for operators.
- Improve trust in demos by showing data quality transparently.

## Checks

Candidate checks:

- Missing sales dates per store/product.
- Long zero-sales streaks.
- Sudden quantity spikes.
- Negative or impossible values.
- Price changes outside expected bounds.
- Promotion windows with no lift.
- Inventory snapshot gaps.
- Potential stockout periods.
- Calendar coverage gaps.
- Stale model input data.

## Backend Design

Candidate slice:

- `app/features/quality/routes.py`
- `app/features/quality/service.py`
- `app/features/quality/schemas.py`

Candidate endpoints:

- `GET /quality/summary`
- `GET /quality/issues`
- `POST /quality/run-checks`
- `GET /quality/issues/{issue_id}`

## Frontend Design

Add a page or Control Center section:

- Issue counts by severity.
- Table of issues.
- Filters by store, product, date, severity, issue type.
- Link to Sales Explorer with matching filters.
- Resolution notes.

## MVP Scope

- On-demand checks computed from current database.
- Issue table with severity and suggested action.
- Sales Explorer deep links.

## Full Version

- Persisted issue history.
- Scheduled quality runs.
- Alert thresholds.
- Agent-readable quality context.
- Quality-aware model promotion gates.

## Risks

- Synthetic data may intentionally contain patterns that look anomalous.
- Thresholds need calibration.
- Too many low-value warnings reduce usefulness.

## Validation Plan

- Unit tests for each check.
- Seeded fixtures with known anomalies.
- API tests for summary and issue filtering.
- Browser QA for filters and deep links.

## Documentation

- FastAPI documentation: https://fastapi.tiangolo.com/
- SQLAlchemy asyncio documentation: https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html
- Pandas time series documentation: https://pandas.pydata.org/docs/user_guide/timeseries.html
- scikit-learn anomaly detection overview: https://scikit-learn.org/stable/modules/outlier_detection.html
- scikit-learn metrics documentation: https://scikit-learn.org/stable/modules/model_evaluation.html
- OpenTelemetry FastAPI instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html
- TanStack Query React documentation: https://tanstack.com/query/latest/docs/framework/react/overview
- Recharts documentation: https://recharts.org/en-US/
