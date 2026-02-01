# ForecastLabAI

Portfolio-grade end-to-end retail demand forecasting system.

## Features

- **Data Platform**: Multi-table mini warehouse (store/product/calendar + sales + price/promo/inventory signals)
- **ForecastOps**: Model zoo with time-based backtesting (rolling/expanding splits) + metrics
- **Serving Layer**: Typed FastAPI endpoints (Pydantic v2 validation)
- **Model Registry**: Run configs, metrics, artifacts, and data windows for reproducibility
- **RAG Knowledge Base**: Postgres pgvector embeddings + evidence-grounded answers with citations

## Quick Start

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- uv (recommended) or pip

### Setup

1. **Clone and configure environment**

```bash
cp .env.example .env
```

2. **Start PostgreSQL + pgvector**

```bash
docker-compose up -d
```

3. **Install dependencies**

```bash
uv sync
# or: pip install -e ".[dev]"
```

4. **Run database migrations**

```bash
uv run alembic upgrade head
```

5. **Verify database connectivity**

```bash
uv run python scripts/check_db.py
```

6. **Start the API server**

```bash
uv run uvicorn app.main:app --reload --port 8123
```

7. **Verify the API is running**

```bash
curl http://localhost:8123/health
# Response: {"status":"ok"}
```

## Development

### Commands

```bash
# Run tests
uv run pytest -v

# Type checking
uv run mypy app/
uv run pyright app/

# Linting and formatting
uv run ruff check . --fix
uv run ruff format .

# Database migrations
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

### Project Structure

```
app/
├── core/           # Config, database, logging, middleware, exceptions
├── shared/         # Pagination, timestamps, error schemas
├── features/
│   ├── data_platform/  # Store, product, calendar, sales tables
│   ├── ingest/         # Batch upsert endpoints for sales data
│   ├── featuresets/    # Time-safe feature engineering (lags, rolling, calendar)
│   └── forecasting/    # Model training, prediction, persistence
└── main.py         # FastAPI entry point

tests/              # Test fixtures and helpers
alembic/            # Database migrations
examples/
├── api/            # HTTP client examples
├── schema/         # Table documentation
├── queries/        # Example SQL queries
├── models/         # Baseline model examples (naive, seasonal_naive, moving_average)
└── compute_features_demo.py  # Feature engineering demo
scripts/            # Utility scripts
```

### Database Schema

The data platform includes 7 tables for retail demand forecasting:

**Dimensions**: `store`, `product`, `calendar`
**Facts**: `sales_daily`, `price_history`, `promotion`, `inventory_snapshot_daily`

See [examples/schema/README.md](examples/schema/README.md) for detailed schema documentation.

## API Endpoints

### Health Check

- `GET /health` - Returns `{"status": "ok"}` when the API is running

### Ingest

- `POST /ingest/sales-daily` - Batch upsert daily sales records

**Example Request:**
```bash
curl -X POST http://localhost:8123/ingest/sales-daily \
  -H "Content-Type: application/json" \
  -d '{
    "records": [
      {
        "date": "2024-01-15",
        "store_code": "S001",
        "sku": "SKU-001",
        "quantity": 10,
        "unit_price": 9.99,
        "total_amount": 99.90
      }
    ]
  }'
```

**Features:**
- Natural key resolution (`store_code` -> `store_id`, `sku` -> `product_id`)
- Idempotent upsert using PostgreSQL `ON CONFLICT DO UPDATE`
- Partial success handling (valid rows processed, invalid rows returned with errors)
- Error codes: `UNKNOWN_STORE`, `UNKNOWN_PRODUCT`, `UNKNOWN_DATE`

See [examples/api/ingest_sales_daily.http](examples/api/ingest_sales_daily.http) for more examples.

### Feature Engineering

- `POST /featuresets/compute` - Compute time-safe features for a series
- `POST /featuresets/preview` - Preview features with sample rows

**Example Request:**
```bash
curl -X POST http://localhost:8123/featuresets/compute \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": 1,
    "product_id": 1,
    "cutoff_date": "2024-01-31",
    "lookback_days": 365,
    "config": {
      "name": "retail_forecast_v1",
      "lag_config": {"lags": [1, 7, 14, 28]},
      "rolling_config": {"windows": [7, 14], "aggregations": ["mean", "std"]},
      "calendar_config": {"include_day_of_week": true, "use_cyclical_encoding": true}
    }
  }'
```

**Features:**
- **Time-safe computation**: All features use only data up to cutoff_date (no future leakage)
- **Lag features**: Past values at specified lag periods (shift with positive values only)
- **Rolling features**: Rolling statistics with shift(1) to exclude current observation
- **Calendar features**: Cyclical encoding (sin/cos) for day of week, month
- **Group isolation**: Entity-aware groupby prevents cross-series leakage

See [examples/compute_features_demo.py](examples/compute_features_demo.py) for a complete demo.

### Forecasting

- `POST /forecasting/train` - Train a forecasting model for a store/product series
- `POST /forecasting/predict` - Generate forecasts using a trained model

**Example Training Request:**
```bash
curl -X POST http://localhost:8123/forecasting/train \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": 1,
    "product_id": 1,
    "train_start_date": "2024-01-01",
    "train_end_date": "2024-06-30",
    "config": {
      "model_type": "seasonal_naive",
      "seasonal_period": 7
    }
  }'
```

**Example Prediction Request:**
```bash
curl -X POST http://localhost:8123/forecasting/predict \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": 1,
    "product_id": 1,
    "horizon": 14,
    "model_path": "./artifacts/models/store_1_product_1_seasonal_naive_20240630.pkl"
  }'
```

**Supported Model Types:**
- `naive` - Last observed value (simple baseline)
- `seasonal_naive` - Same period from previous season
- `moving_average` - Mean of last N observations
- `lightgbm` - LightGBM regressor (requires `forecast_enable_lightgbm=True`)

See [examples/models/](examples/models/) for baseline model examples.

## API Documentation

Once the server is running:

- Swagger UI: http://localhost:8123/docs
- ReDoc: http://localhost:8123/redoc

## License

MIT
