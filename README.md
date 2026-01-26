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
│   └── data_platform/  # Store, product, calendar, sales tables
└── main.py         # FastAPI entry point

tests/              # Test fixtures and helpers
alembic/            # Database migrations
examples/
├── schema/         # Table documentation
└── queries/        # Example SQL queries
scripts/            # Utility scripts
```

### Database Schema

The data platform includes 7 tables for retail demand forecasting:

**Dimensions**: `store`, `product`, `calendar`
**Facts**: `sales_daily`, `price_history`, `promotion`, `inventory_snapshot_daily`

See [examples/schema/README.md](examples/schema/README.md) for detailed schema documentation.

## API Documentation

Once the server is running:

- Swagger UI: http://localhost:8123/docs
- ReDoc: http://localhost:8123/redoc

## License

MIT
