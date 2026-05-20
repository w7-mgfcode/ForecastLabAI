# Feature Reference

This is a capability-by-capability reference for ForecastLab's backend. Every feature
is a REST API served at **http://localhost:8123**; the interactive Swagger UI at
**/docs** is the authoritative, always-current contract. All errors use the RFC 7807
`application/problem+json` format.

## Health

- `GET /health` — liveness probe; returns `{"status": "ok"}`.

## Data Platform and Ingest

The data platform owns seven retail tables: `store`, `product`, `calendar`,
`sales_daily`, `price_history`, `promotion`, and `inventory_snapshot_daily`.

- `POST /ingest/sales-daily` — batch-load daily sales. Resolves natural keys
  (store code, SKU) to IDs and upserts idempotently, so re-sending the same batch is
  safe.

## Dimensions

Reference data — the "who" and "what" behind the sales facts.

- `GET /dimensions/stores` — list stores (pagination, region / store-type filters,
  case-insensitive search, optional sorting).
- `GET /dimensions/stores/{store_id}` — one store by ID.
- `GET /dimensions/products` — list products (category / brand filters, SKU / name
  search, optional sorting).
- `GET /dimensions/products/{product_id}` — one product by ID.

## Analytics

Read-only aggregates computed over the sales data.

- `GET /analytics/kpis` — headline KPIs: revenue, units, transactions, average unit
  price, average basket.
- `GET /analytics/drilldowns` — group sales by store, product, category, region, or date.
- `GET /analytics/timeseries` — period-bucketed sales series (day / week / month /
  quarter) for revenue-over-time charts.
- `GET /analytics/inventory-status` — latest inventory snapshot per store-product pair.

## Feature Engineering

Turns raw sales into model-ready features while strictly preventing **data leakage** —
features never use information from the future.

- `POST /featuresets/compute` — compute time-safe features (lags, rolling-window
  statistics, calendar effects) up to a cutoff date.
- `POST /featuresets/preview` — preview computed features with sample rows.

## Forecasting

Trains demand-forecasting models and generates predictions.

- `POST /forecasting/train` — train a model. Supported model types:
  - **Baselines**: `naive`, `seasonal_naive`, `moving_average` — always available.
  - **Tree (feature-aware)**: `regression` (HistGradientBoostingRegressor, always
    available), `lightgbm` (requires the `ml-lightgbm` extra), `xgboost` (requires
    the `ml-xgboost` extra).
  - **Additive (feature-aware)**: `prophet_like` — a Ridge regressor over the
    canonical 14-column feature frame; always available.
- `POST /forecasting/predict` — generate horizon predictions from a trained model.
- `GET /forecasting/runs/{run_id}/feature-metadata` — return the canonical
  feature columns the trained model consumed and the fitted estimator's native
  feature importance (tree models) or signed coefficients (additive
  `prophet_like`). See **Advanced Model Metadata** below.
- `GET /forecasting/jobs/{job_id}/feature-metadata` — the job-keyed sibling of
  the run endpoint; use it from the forecast viz page, which only holds a
  `job_id`.

The three baselines exist as honest comparison points — a machine-learning model is
only worth using if it beats them.

### Advanced Model Metadata

Every model returned by `/registry/runs` carries a computed `model_family` field
— `baseline` (naive / seasonal_naive / moving_average), `tree` (regression /
lightgbm / xgboost), or `additive` (prophet_like). The dashboard surfaces this
in four places: a **Family** badge column on the runs explorer, a badge + cards
on the run detail page (the 14 canonical feature columns and a feature
importance panel), a side-by-side comparison on the run compare page (rendered
only when both runs share a non-baseline family), and a collapsible importance
panel on the forecast viz page tied to the train job.

For a `tree`-family run the panel renders non-negative bars whose length
reflects relative magnitude (the boosters' native `feature_importances_`
attribute — LightGBM's `'split'`, XGBoost's `'weight'`, etc.; the label is
shown at the top of the panel). For an `additive` (`prophet_like`) run the
panel preserves the **sign** of the Ridge coefficient — a positive coefficient
renders green with a `TrendingUp` icon; a negative one renders red with
`TrendingDown`.

> **Correlation, not causation.** Feature importance is model-derived. It
> reflects how much each feature reduced the model's training error — not
> real-world causation. Two products with similar importance profiles are not
> necessarily driven by the same business factors.

Three error semantics map cleanly to RFC 7807 `application/problem+json`:
- **400 `BAD_REQUEST`** — the run is a baseline (no native importance vector
  exists). The panel renders a neutral muted message.
- **404 `NOT_FOUND`** — the run or job is not in the registry.
- **422 `UNPROCESSABLE_ENTITY`** — the run has no artifact yet
  (`pending` / `running` / `failed`), the artifact file has been deleted from
  disk, an optional `ml-*` extra is not installed at unpickle time, or the
  underlying estimator does not expose `feature_importances_` (sklearn's
  `HistGradientBoostingRegressor`, used by `regression`, does not).
  The 422 type URI is `UNPROCESSABLE_ENTITY` (distinct from `VALIDATION_ERROR`,
  which is reserved for input failures).

## Backtesting

Measures how accurate a model would have been, using time-series cross-validation.

- `POST /backtesting/run` — run rolling or expanding train/test splits and report
  accuracy metrics: **MAE**, **sMAPE**, **WAPE**, **bias**, and **stability**.

## Model Registry

Tracks every trained model so runs are reproducible and comparable.

- `POST /registry/runs` — create a model run record (starts `pending`).
- `GET /registry/runs` — list runs with filters, pagination, and sorting.
- `GET /registry/runs/{run_id}` — run details, including metrics and runtime info.
- `PATCH /registry/runs/{run_id}` — update a run's status, metrics, or artifact location.
- `GET /registry/runs/{run_id}/verify` — verify the model artifact's SHA-256 integrity.
- `GET /registry/compare/{run_id_a}/{run_id_b}` — diff two runs.
- `POST /registry/aliases` — create or move an alias (e.g. `production`); aliases may
  point only to a successful run.
- `GET /registry/aliases`, `GET /registry/aliases/{name}`, `DELETE /registry/aliases/{name}`
  — manage aliases.

A run moves through `pending → running → success` (or `failed`), and an alias is a
human-friendly pointer (like `production` or `champion`) to a chosen successful run.

## Jobs

Long-running work — training, prediction, backtesting — submitted as jobs.

- `POST /jobs` — submit a `train`, `predict`, or `backtest` job; returns a `job_id`.
- `GET /jobs` — list jobs with filters and sorting.
- `GET /jobs/{job_id}` — job status and result JSON.
- `DELETE /jobs/{job_id}` — cancel a pending job.

## RAG Knowledge Base

Semantic search over indexed documents. See the Agents and RAG Guide for the full
picture.

- `POST /rag/index` — index a markdown or OpenAPI document; idempotent via content hash.
- `POST /rag/retrieve` — semantic search; returns the top-k most relevant passages.
- `GET /rag/sources` — list indexed sources.
- `DELETE /rag/sources/{source_id}` — delete a source and its chunks.

## Agents

The conversational AI layer. See the Agents and RAG Guide.

- `POST /agents/sessions` — open a chat session (`experiment` or `rag_assistant`).
- `GET /agents/sessions/{id}` — session status and message history.
- `POST /agents/sessions/{id}/chat` — send a message; returns the full response.
- `POST /agents/sessions/{id}/approve` — approve or reject a pending tool call.
- `DELETE /agents/sessions/{id}` — close a session.
- `WS /agents/stream` — token-by-token streaming with tool-call events.

## Seeder ("The Forge")

Generates realistic synthetic retail data so you have something to forecast.

- `GET /seeder/status` — current dataset state.
- `GET /seeder/scenarios` — available named scenarios.
- `GET /seeder/channels` — available sales channels.
- `POST /seeder/generate` — generate a dataset from a scenario.
- `POST /seeder/append` — append more data to an existing dataset.
- `DELETE /seeder/data` — clear the generated data.
- `GET /seeder/exogenous` — exogenous signal data.
- `POST /seeder/verify` — verify dataset integrity.

## Demo Pipeline

- `POST /demo/run` — run the full end-to-end pipeline in one call.
- `WS /demo/stream` — stream per-step events for the live Showcase page.

## Configuration

- `GET /config/ai` — effective AI-model configuration (agent LLM + RAG embeddings);
  API keys are always masked.
- `PATCH /config/ai` — change AI-model settings live, with no restart.
- `GET /config/providers/health` — per-provider connectivity status.
- `GET /config/ollama/models` — models available on the configured Ollama host.
