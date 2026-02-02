# ForecastLabAI

Portfolio-grade end-to-end retail demand forecasting system.

## Features

- **Data Platform**: Multi-table mini warehouse (store/product/calendar + sales + price/promo/inventory signals)
- **ForecastOps**: Model zoo with time-based backtesting (rolling/expanding splits) + metrics
- **Serving Layer**: Typed FastAPI endpoints (Pydantic v2 validation)
- **Model Registry**: Run configs, metrics, artifacts, and data windows for reproducibility
- **Dashboard**: React 19 + Vite + Tailwind CSS 4 + shadcn/ui for data exploration and model management
- **RAG Knowledge Base**: Postgres pgvector embeddings + evidence-grounded answers with citations
- **Agentic Layer**: PydanticAI agents for autonomous experimentation and evidence-grounded Q&A with human-in-the-loop approval
- **Data Seeder (The Forge)**: Reproducible synthetic data generator with realistic time-series patterns, scenario presets, and retail effects

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+ and pnpm (for frontend)
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

### Frontend Setup

8. **Install frontend dependencies**

```bash
cd frontend
pnpm install
```

9. **Start the development server**

```bash
pnpm dev
# Frontend available at http://localhost:5173
```

The frontend proxies API requests to the backend at `http://localhost:8123`.

## Development

### Testing

```bash
# Run all tests
uv run pytest -v

# Run unit tests only (no database required)
uv run pytest -v -m "not integration"

# Run integration tests (requires PostgreSQL via docker-compose)
docker-compose up -d  # Start database first
uv run pytest -v -m integration

# Run feature-specific tests
uv run pytest app/features/backtesting/tests/ -v              # All backtesting tests
uv run pytest app/features/forecasting/tests/ -v              # All forecasting tests
uv run pytest app/features/backtesting/tests/ -v -m integration  # Backtesting integration tests
```

**Test Coverage:**
- Unit tests: Fast, isolated tests that mock database dependencies
- Integration tests: End-to-end tests against real PostgreSQL database
  - Marked with `@pytest.mark.integration`
  - Require `docker-compose up -d` before running

### Backend Commands

```bash
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

### Frontend Commands

```bash
cd frontend

# Development server (http://localhost:5173)
pnpm dev

# Production build
pnpm build

# Linting
pnpm lint

# Type checking
pnpm tsc --noEmit

# Preview production build
pnpm preview
```

### Project Structure

```
app/                    # FastAPI backend
├── core/               # Config, database, logging, middleware, exceptions
├── shared/
│   ├── seeder/         # The Forge - randomized database seeder
│   └── ...             # Pagination, timestamps, error schemas
├── features/
│   ├── data_platform/  # Store, product, calendar, sales tables
│   ├── ingest/         # Batch upsert endpoints for sales data
│   ├── featuresets/    # Time-safe feature engineering (lags, rolling, calendar)
│   ├── forecasting/    # Model training, prediction, persistence
│   ├── backtesting/    # Time-series CV, metrics, baseline comparisons
│   ├── registry/       # Model run tracking, artifacts, deployment aliases
│   ├── rag/            # pgvector embeddings, semantic search, citations
│   ├── agents/         # PydanticAI agents (experiment, RAG assistant)
│   ├── dimensions/     # Store/product discovery for LLM tool-calling
│   ├── analytics/      # KPI aggregations and drilldown analysis
│   └── jobs/           # Async-ready task orchestration
└── main.py             # FastAPI entry point

frontend/               # React dashboard (Vite + shadcn/ui)
├── src/
│   ├── components/ui/  # shadcn/ui components (26 components)
│   ├── lib/            # Utilities (cn helper)
│   ├── App.tsx         # Main app component
│   └── main.tsx        # Entry point
├── components.json     # shadcn/ui configuration
├── vite.config.ts      # Vite + Tailwind + path aliases
└── package.json        # Dependencies

tests/                  # Test fixtures and helpers
alembic/                # Database migrations
examples/
├── api/                # HTTP client examples
├── schema/             # Table documentation
├── queries/            # Example SQL queries
├── models/             # Baseline model examples (naive, seasonal_naive, moving_average)
├── backtest/           # Backtesting examples (run_backtest, inspect_splits, metrics_demo)
├── seed/               # Data seeder configs and examples (YAML scenarios)
├── compute_features_demo.py  # Feature engineering demo
└── registry_demo.py    # Model registry workflow demo
scripts/                # Utility scripts
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
      "season_length": 7
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

### Backtesting

- `POST /backtesting/run` - Run time-series cross-validation backtest

**Example Request:**
```bash
curl -X POST http://localhost:8123/backtesting/run \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": 1,
    "product_id": 1,
    "start_date": "2024-01-01",
    "end_date": "2024-06-30",
    "config": {
      "split_config": {
        "strategy": "expanding",
        "n_splits": 5,
        "min_train_size": 30,
        "gap": 0,
        "horizon": 14
      },
      "model_config_main": {
        "model_type": "naive"
      },
      "include_baselines": true,
      "store_fold_details": true
    }
  }'
```

**Split Strategies:**
- `expanding` - Training window grows with each fold (sklearn-like TimeSeriesSplit)
- `sliding` - Fixed-size training window slides forward

**Gap Parameter:**
- Simulates operational data latency between training and test periods
- `gap=7` means 7 days between train end and test start

**Metrics Calculated:**
- MAE: Mean Absolute Error
- sMAPE: Symmetric Mean Absolute Percentage Error (0-200 scale)
- WAPE: Weighted Absolute Percentage Error
- Bias: Forecast bias (positive = under-forecast)
- Stability Index: Coefficient of variation across folds

**Baseline Comparisons:**
When `include_baselines=true`, automatically compares against naive and seasonal_naive models.

See [examples/backtest/](examples/backtest/) for usage examples.

### Model Registry

- `POST /registry/runs` - Create a new model run
- `GET /registry/runs` - List runs with filtering and pagination
- `GET /registry/runs/{run_id}` - Get run details
- `PATCH /registry/runs/{run_id}` - Update run (status, metrics, artifacts)
- `GET /registry/runs/{run_id}/verify` - Verify artifact integrity
- `POST /registry/aliases` - Create or update deployment alias
- `GET /registry/aliases` - List all aliases
- `GET /registry/aliases/{alias_name}` - Get alias details
- `DELETE /registry/aliases/{alias_name}` - Delete an alias
- `GET /registry/compare/{run_id_a}/{run_id_b}` - Compare two runs

**Example Create Run Request:**
```bash
curl -X POST http://localhost:8123/registry/runs \
  -H "Content-Type: application/json" \
  -d '{
    "model_type": "seasonal_naive",
    "model_config": {"season_length": 7},
    "data_window_start": "2024-01-01",
    "data_window_end": "2024-03-31",
    "store_id": 1,
    "product_id": 1
  }'
```

**Run Lifecycle:**
- `pending` → `running` → `success` | `failed` → `archived`
- Aliases can only point to runs with `success` status

**Features:**
- JSONB storage for model_config, metrics, runtime_info
- SHA-256 artifact integrity verification
- Duplicate detection (configurable: allow/deny/detect)
- Runtime environment capture (Python, numpy, pandas versions)
- Agent context tracking for autonomous workflows

See [examples/registry_demo.py](examples/registry_demo.py) for a complete workflow demo.

### Dimensions (Discovery)

- `GET /dimensions/stores` - List stores with pagination and filtering
- `GET /dimensions/stores/{store_id}` - Get store details by ID
- `GET /dimensions/products` - List products with pagination and filtering
- `GET /dimensions/products/{product_id}` - Get product details by ID

**Example Request:**
```bash
# List stores with filtering
curl "http://localhost:8123/dimensions/stores?region=North&page=1&page_size=20"

# Search for products
curl "http://localhost:8123/dimensions/products?search=Cola&category=Beverage"
```

**Purpose:** Resolve store/product metadata to IDs before calling forecasting endpoints. Optimized for LLM agent tool-calling with rich Field descriptions.

**Features:**
- 1-indexed pagination (page=1 is first page)
- Case-insensitive search in code/sku and name fields
- Filter by region, store_type, category, or brand

### Analytics

- `GET /analytics/kpis` - Compute aggregated KPIs for a date range
- `GET /analytics/drilldowns` - Drill into data by dimension (store, product, category, region, date)

**Example KPI Request:**
```bash
curl "http://localhost:8123/analytics/kpis?start_date=2024-01-01&end_date=2024-01-31&store_id=1"
```

**Example Drilldown Request:**
```bash
curl "http://localhost:8123/analytics/drilldowns?dimension=store&start_date=2024-01-01&end_date=2024-01-31&max_items=10"
```

**Metrics Computed:**
- `total_revenue`: Sum of sales amount
- `total_units`: Sum of quantity sold
- `total_transactions`: Count of unique sales records
- `avg_unit_price`: Revenue / units
- `avg_basket_value`: Revenue / transactions

**Drilldown Dimensions:**
- `store` - Group by store (returns code and ID)
- `product` - Group by product (returns SKU and ID)
- `category` - Group by product category
- `region` - Group by store region
- `date` - Daily breakdown

### Jobs (Task Orchestration)

- `POST /jobs` - Create and execute a job (train, predict, backtest)
- `GET /jobs` - List jobs with filtering and pagination
- `GET /jobs/{job_id}` - Get job status and result
- `DELETE /jobs/{job_id}` - Cancel a pending job

**Example Train Job:**
```bash
curl -X POST http://localhost:8123/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "train",
    "params": {
      "model_type": "seasonal_naive",
      "store_id": 1,
      "product_id": 1,
      "start_date": "2024-01-01",
      "end_date": "2024-06-30",
      "season_length": 7
    }
  }'
```

**Example Backtest Job:**
```bash
curl -X POST http://localhost:8123/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "backtest",
    "params": {
      "model_type": "naive",
      "store_id": 1,
      "product_id": 1,
      "start_date": "2024-01-01",
      "end_date": "2024-06-30",
      "n_splits": 5,
      "test_size": 14
    }
  }'
```

**Job Types:**
- `train` - Train a forecasting model (returns model_path)
- `predict` - Generate predictions using a trained model
- `backtest` - Run time-series cross-validation

**Job Lifecycle:**
- `pending` → `running` → `completed` | `failed`
- `pending` → `cancelled` (via DELETE)

**Features:**
- Jobs execute synchronously but use async-ready API contracts (202 Accepted)
- JSONB storage for flexible params and results
- Links to model_run for train/backtest jobs

### RAG Knowledge Base

- `POST /rag/index` - Index a document into the knowledge base
- `POST /rag/retrieve` - Semantic search across indexed documents
- `GET /rag/sources` - List indexed sources
- `DELETE /rag/sources/{source_id}` - Delete a source and its chunks

**Embedding Providers:**

The RAG system supports two embedding providers:

1. **OpenAI** (default):
```bash
RAG_EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-your-key
RAG_EMBEDDING_MODEL=text-embedding-3-small
RAG_EMBEDDING_DIMENSION=1536
```

2. **Ollama** (local/LAN):
```bash
RAG_EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
RAG_EMBEDDING_DIMENSION=768
```

**Example Index Request:**
```bash
curl -X POST http://localhost:8123/rag/index \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "markdown",
    "source_path": "docs/ARCHITECTURE.md"
  }'
```

**Example Retrieve Request:**
```bash
curl -X POST http://localhost:8123/rag/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How does backtesting work?",
    "top_k": 5
  }'
```

**Features:**
- pgvector for HNSW similarity search
- Idempotent indexing via content hash
- Markdown and OpenAPI chunking strategies
- Configurable embedding dimensions

### Agentic Layer

- `POST /agents/sessions` - Create a new agent session
- `GET /agents/sessions/{session_id}` - Get session status and details
- `POST /agents/sessions/{session_id}/chat` - Send a message to the agent
- `POST /agents/sessions/{session_id}/approve` - Approve or reject a pending action
- `DELETE /agents/sessions/{session_id}` - Close a session
- `WS /agents/stream` - WebSocket streaming endpoint for real-time responses

**Agent Types:**

1. **Experiment Orchestrator** (`agent_type: "experiment"`):
   - Autonomous model experimentation workflow
   - Runs backtests and compares configurations
   - Recommends best model with human-in-the-loop approval

2. **RAG Assistant** (`agent_type: "rag_assistant"`):
   - Evidence-grounded documentation Q&A
   - Citation-backed responses with confidence scoring
   - "Insufficient evidence" detection to prevent hallucination

**Example Create Session Request:**
```bash
curl -X POST http://localhost:8123/agents/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "rag_assistant",
    "initial_context": null
  }'
```

**Example Chat Request:**
```bash
curl -X POST http://localhost:8123/agents/sessions/{session_id}/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How does backtesting prevent data leakage?"
  }'
```

**Features:**
- PydanticAI v1.48.0 for structured, type-safe agent orchestration
- Session management with PostgreSQL JSONB message history
- Human-in-the-loop approval for sensitive actions (create_alias, archive_run)
- WebSocket streaming for real-time token delivery
- Token usage tracking and tool call auditing

**Configuration:**
```bash
# Agent LLM Configuration
# Model format: "provider:model-name" (e.g., anthropic:claude-sonnet-4-5)
AGENT_DEFAULT_MODEL=anthropic:claude-sonnet-4-5
AGENT_FALLBACK_MODEL=openai:gpt-4o
AGENT_TEMPERATURE=0.1
AGENT_MAX_TOKENS=4096

# API Keys (set based on your chosen provider)
ANTHROPIC_API_KEY=sk-ant-your-key
# OPENAI_API_KEY=sk-your-key
# GOOGLE_API_KEY=your-google-api-key  # For Gemini models

# Execution Configuration
AGENT_MAX_TOOL_CALLS=10
AGENT_TIMEOUT_SECONDS=120
AGENT_RETRY_ATTEMPTS=3
AGENT_RETRY_DELAY_SECONDS=1.0

# Session Configuration
AGENT_SESSION_TTL_MINUTES=120
AGENT_MAX_SESSIONS_PER_USER=5

# Human-in-the-loop Configuration (JSON array format)
AGENT_REQUIRE_APPROVAL=["create_alias","archive_run"]
AGENT_APPROVAL_TIMEOUT_MINUTES=60

# Streaming Configuration
AGENT_ENABLE_STREAMING=true
```

### Data Seeder (The Forge)

Generate reproducible synthetic test data with realistic time-series patterns.

**CLI Commands:**
```bash
# Generate complete dataset
uv run python scripts/seed_random.py --full-new --seed 42 --confirm

# Delete all data
uv run python scripts/seed_random.py --delete --confirm

# Append data for new date range
uv run python scripts/seed_random.py --append --start-date 2025-01-01 --end-date 2025-03-31

# Run pre-built scenario
uv run python scripts/seed_random.py --full-new --scenario holiday_rush --confirm

# Show current data counts
uv run python scripts/seed_random.py --status

# Verify data integrity
uv run python scripts/seed_random.py --verify
```

**Scenario Presets:**

| Scenario | Description |
|----------|-------------|
| `retail_standard` | Normal retail patterns with mild seasonality |
| `holiday_rush` | Q4 surge with Black Friday/Christmas peaks |
| `high_variance` | Noisy data with anomalies for robustness testing |
| `stockout_heavy` | Frequent stockouts (25% probability) |
| `new_launches` | 100 products with launch ramp patterns |
| `sparse` | 50% missing combinations, random gaps |

**Features:**
- Deterministic generation with configurable seeds for reproducibility
- Realistic time-series patterns (trend, weekly/monthly seasonality, noise, anomalies)
- Retail effects (promotions, stockouts, price elasticity)
- YAML configuration support for custom scenarios
- Safe deletion with scope control (all/facts/dimensions)
- Dry-run mode for previewing changes

See [examples/seed/README.md](examples/seed/README.md) for detailed configuration options.

### Error Responses (RFC 7807)

All error responses follow RFC 7807 Problem Details format with `Content-Type: application/problem+json`:

```json
{
  "type": "/errors/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "Store not found: 999. Use GET /dimensions/stores to list available stores.",
  "instance": "/requests/abc123",
  "code": "NOT_FOUND",
  "request_id": "abc123"
}
```

**Error Types:**
- `/errors/validation` - Request validation failed (422)
- `/errors/not-found` - Resource not found (404)
- `/errors/conflict` - Resource conflict (409)
- `/errors/database` - Database error (500)

## API Documentation

Once the backend is running:

- Swagger UI: http://localhost:8123/docs
- ReDoc: http://localhost:8123/redoc

## Frontend Stack

The dashboard is built with modern React tooling:

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 19 | UI framework |
| Vite | 7 | Build tool and dev server |
| TypeScript | 5.9 | Type safety |
| Tailwind CSS | 4 | Utility-first styling |
| shadcn/ui | New York | Component library (26 components) |
| TanStack Query | 5 | Server state management |
| TanStack Table | 8 | Data tables |
| React Router | 7 | Client-side routing |
| Recharts | 2 | Charts and visualizations |

**Development URLs:**
- Frontend: http://localhost:5173
- Backend API: http://localhost:8123
- API Docs: http://localhost:8123/docs

## License

MIT
