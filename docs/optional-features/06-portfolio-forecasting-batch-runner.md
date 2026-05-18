# Portfolio Forecasting Batch Runner

## Summary

Add batch orchestration for training, backtesting, and predicting across many store-product pairs. The current app is strong for single store/SKU workflows; this feature makes it useful for portfolio-level retail operations.

## Why It Fits ForecastLabAI

ForecastLabAI already has:

- Store/product dimensions.
- Jobs layer.
- Forecasting service.
- Backtesting service.
- Registry and run explorer.
- Seeder capable of generating many store/product combinations.

Batch execution is the orchestration layer above these existing capabilities.

## User Value

- Users can forecast all active store-SKU pairs.
- Operators can prioritize high-revenue or high-error series.
- Model performance can be compared across the portfolio.
- The app becomes closer to real ForecastOps practice.

## Proposed UX

Create batch workflow in ForecastOps or Admin:

1. Select scope:
   - All stores/products.
   - Region/category.
   - Top N revenue series.
   - Manual selection.
2. Select model configs.
3. Select operation:
   - Train.
   - Backtest.
   - Predict.
   - Train + backtest + register best.
4. Run batch.
5. Track progress.
6. Review results table.

## Backend Design

Candidate endpoints:

- `POST /batch/forecasting`
- `GET /batch/{batch_id}`
- `GET /batch/{batch_id}/items`
- `DELETE /batch/{batch_id}`

Use the existing jobs layer if possible. A batch can be a parent job with child jobs per store-product-model tuple.

## Data Model

Potential tables:

- `batch_job`
- `batch_job_item`

Fields:

- `batch_id`
- `operation`
- `scope`
- `status`
- `total_items`
- `completed_items`
- `failed_items`
- `params`
- `result_summary`

## MVP Scope

- Batch backtest for selected store/product pairs.
- Parent job status.
- Child item table.
- Basic failure reporting.
- Link child results to registry runs/jobs.

## Full Version

- Parallel execution controls.
- Retry failed items.
- Priority queue.
- Batch-level champion selection.
- Portfolio heatmaps.
- Exportable results.

## Risks

- Long-running requests must not block the API process.
- Unbounded batch size can overload local machines.
- Failed child jobs need resumability.
- Batch results need clear lineage into registry artifacts.

## Validation Plan

- Unit tests for scope expansion.
- API tests for batch lifecycle.
- Tests for partial failure handling.
- Browser QA for batch creation, progress, result drilldown, and retry.

## Documentation

- FastAPI background tasks: https://fastapi.tiangolo.com/tutorial/background-tasks/
- FastAPI WebSockets: https://fastapi.tiangolo.com/advanced/websockets/
- SQLAlchemy asyncio documentation: https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html
- Python asyncio documentation: https://docs.python.org/3/library/asyncio.html
- scikit-learn TimeSeriesSplit: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- TanStack Query React documentation: https://tanstack.com/query/latest/docs/framework/react/overview
- TanStack Table documentation: https://tanstack.com/table/latest/docs/overview
- OpenTelemetry Python documentation: https://opentelemetry.io/docs/languages/python/
