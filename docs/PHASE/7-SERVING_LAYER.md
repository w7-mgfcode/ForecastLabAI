# Phase 7: Serving Layer

**Date Completed**: 2026-02-01
**PRP**: PRP-8
**Status**: ✅ Completed

---

## Executive Summary

Phase 7 implements the agent-first API design for ForecastLabAI with RFC 7807 Problem Details for semantic error responses, dimension discovery endpoints for LLM tool-calling, KPI aggregations and drilldown analysis, and async-ready job orchestration.

### Objectives Achieved

1. **RFC 7807 Problem Details** - Semantic error responses with type URIs and correlation
2. **Dimensions Module** - Store/product discovery with LLM-optimized descriptions
3. **Analytics Module** - KPI aggregations and multi-dimension drilldowns
4. **Jobs Module** - Async-ready task orchestration for train/predict/backtest
5. **Rich OpenAPI Descriptions** - Optimized for LLM agent tool selection

---

## Deliverables

### 1. RFC 7807 Problem Details

**File**: `app/core/problem_details.py`

Implements RFC 7807 compliant error responses:

```python
class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details for HTTP APIs."""
    type: str = "/errors/unknown"  # URI identifying error type
    title: str                      # Human-readable summary
    status: int                     # HTTP status code
    detail: str | None              # Specific error description
    instance: str | None            # URI for this occurrence
    errors: list[dict] | None       # Field-level validation errors
    code: str | None                # Machine-readable error code
    request_id: str | None          # Correlation ID
```

**Error Type URIs**:
- `/errors/validation` - Request validation failed (422)
- `/errors/not-found` - Resource not found (404)
- `/errors/conflict` - Resource conflict (409)
- `/errors/database` - Database error (500)
- `/errors/unknown` - Unhandled error (500)

**Content-Type**: `application/problem+json`

### 2. Dimensions Module

**Directory**: `app/features/dimensions/`

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `schemas.py` | StoreResponse, ProductResponse with rich Field descriptions |
| `service.py` | DimensionService for pagination, filtering, search |
| `routes.py` | API endpoints with OpenAPI descriptions |
| `tests/conftest.py` | Test fixtures |

**API Endpoints**:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/dimensions/stores` | List stores with pagination and filtering |
| GET | `/dimensions/stores/{store_id}` | Get store details by ID |
| GET | `/dimensions/products` | List products with pagination and filtering |
| GET | `/dimensions/products/{product_id}` | Get product details by ID |

**Query Parameters**:
- `page` - Page number (1-indexed, default: 1)
- `page_size` - Items per page (max: 100, default: 20)
- `region` / `store_type` - Filter by region or store type (stores)
- `category` / `brand` - Filter by category or brand (products)
- `search` - Case-insensitive search in code/sku and name (min 2 chars)

**LLM-Optimized Field Descriptions**:

```python
class StoreResponse(BaseModel):
    id: int = Field(
        description="Internal store ID. Use this value for store_id parameters "
        "in /ingest/sales-daily, /forecasting/train, and /forecasting/predict."
    )
    code: str = Field(
        description="Business store code (e.g., 'S001'). Unique human-readable identifier. "
        "Use this for display and matching with external data sources."
    )
```

### 3. Analytics Module

**Directory**: `app/features/analytics/`

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `schemas.py` | KPIMetrics, KPIResponse, DrilldownItem, DrilldownResponse |
| `service.py` | AnalyticsService with compute_kpis() and compute_drilldown() |
| `routes.py` | API endpoints with rich OpenAPI descriptions |
| `tests/conftest.py` | Test fixtures |

**API Endpoints**:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/analytics/kpis` | Compute aggregated KPIs for date range |
| GET | `/analytics/drilldowns` | Drill into dimension with ranking |

**KPI Metrics Computed**:
- `total_revenue` - Sum of total_amount
- `total_units` - Sum of quantity
- `total_transactions` - Count of records
- `avg_unit_price` - Revenue / units
- `avg_basket_value` - Revenue / transactions

**Drilldown Dimensions**:

| Dimension | Groups By | Returns |
|-----------|-----------|---------|
| `store` | Store | code, id, metrics, rank, revenue_share_pct |
| `product` | Product | SKU, id, metrics, rank, revenue_share_pct |
| `category` | Category | name, metrics, rank, revenue_share_pct |
| `region` | Region | name, metrics, rank, revenue_share_pct |
| `date` | Date | date, metrics, rank, revenue_share_pct |

### 4. Jobs Module

**Directory**: `app/features/jobs/`

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `models.py` | Job ORM model with JSONB params/results |
| `schemas.py` | JobCreate, JobResponse, JobListResponse |
| `service.py` | JobService for create, execute, list, cancel |
| `routes.py` | API endpoints with async-ready semantics |
| `tests/conftest.py` | Test fixtures |

**API Endpoints**:

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| POST | `/jobs` | 202 | Create and execute job |
| GET | `/jobs` | 200 | List jobs with filtering |
| GET | `/jobs/{job_id}` | 200 | Get job status and result |
| DELETE | `/jobs/{job_id}` | 200 | Cancel pending job |

**Job Types**:

| Type | Description | Required Params |
|------|-------------|-----------------|
| `train` | Train forecasting model | model_type, store_id, product_id, start_date, end_date |
| `predict` | Generate predictions | model_path, store_id, product_id, horizon |
| `backtest` | Run cross-validation | model_type, store_id, product_id, start_date, end_date |

**Job Lifecycle**:

```
PENDING → RUNNING → COMPLETED | FAILED
PENDING → CANCELLED (via DELETE)
```

**ORM Model**:

```python
class Job(TimestampMixin, Base):
    __tablename__ = "job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    job_type: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000))
    error_type: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    run_id: Mapped[str | None]  # Link to model_run for train/backtest
```

---

## Configuration

### New Settings in `app/core/config.py`

```python
# Analytics
analytics_max_rows: int = 10000              # Max rows in KPI queries
analytics_max_date_range_days: int = 730     # Max date range (2 years)

# Jobs
jobs_retention_days: int = 30                # Job retention period
```

---

## Database Changes

### Migration: `37e16ecef223_create_jobs_table.py`

Creates the `job` table with:

**Columns**:
- `id` (PK), `job_id` (unique), `job_type`, `status`
- `params` (JSONB), `result` (JSONB)
- `error_message`, `error_type`
- `started_at`, `completed_at`
- `run_id` (FK to model_run)
- `created_at`, `updated_at` (from TimestampMixin)

**Indexes**:
- `ix_job_job_id` (unique)
- `ix_job_job_type`
- `ix_job_status`
- `ix_job_run_id`
- `ix_job_type_status` (composite)
- `ix_job_params_gin` (GIN for JSONB)
- `ix_job_result_gin` (GIN for JSONB)

**Check Constraints**:
- `ck_job_valid_status` - Validates status enum
- `ck_job_valid_type` - Validates job_type enum

---

## Integration

### Router Registration in `app/main.py`

```python
from app.features.analytics.routes import router as analytics_router
from app.features.dimensions.routes import router as dimensions_router
from app.features.jobs.routes import router as jobs_router

# In create_app():
app.include_router(dimensions_router)
app.include_router(analytics_router)
app.include_router(jobs_router)
```

### Alembic Model Import in `alembic/env.py`

```python
from app.features.jobs import models as jobs_models  # noqa: F401
```

---

## Test Coverage

### Test Files Created

| File | Description |
|------|-------------|
| `app/features/dimensions/tests/__init__.py` | Test module |
| `app/features/dimensions/tests/conftest.py` | Fixtures for store/product responses |
| `app/features/analytics/tests/__init__.py` | Test module |
| `app/features/analytics/tests/conftest.py` | Fixtures for KPI/drilldown responses |
| `app/features/jobs/tests/__init__.py` | Test module |
| `app/features/jobs/tests/conftest.py` | Fixtures for job create/response |

### Validation Results

```
Ruff:    All checks passed
MyPy:    0 errors (103 source files)
Pyright: 0 errors
Pytest:  426 unit tests passed (1 pre-existing env-specific failure)
```

---

## Directory Structure

```
app/
├── core/
│   ├── config.py           # MODIFIED: Added analytics/jobs settings
│   ├── exceptions.py       # MODIFIED: RFC 7807 error handlers
│   └── problem_details.py  # NEW: RFC 7807 schema and helpers
├── features/
│   ├── dimensions/         # NEW: Store/product discovery
│   │   ├── __init__.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   ├── routes.py
│   │   └── tests/
│   │       ├── __init__.py
│   │       └── conftest.py
│   ├── analytics/          # NEW: KPI and drilldown
│   │   ├── __init__.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   ├── routes.py
│   │   └── tests/
│   │       ├── __init__.py
│   │       └── conftest.py
│   └── jobs/               # NEW: Task orchestration
│       ├── __init__.py
│       ├── models.py
│       ├── schemas.py
│       ├── service.py
│       ├── routes.py
│       └── tests/
│           ├── __init__.py
│           └── conftest.py
└── main.py                 # MODIFIED: Router registration

alembic/
├── env.py                  # MODIFIED: Jobs model import
└── versions/
    └── 37e16ecef223_create_jobs_table.py  # NEW
```

---

## API Usage Examples

### Dimensions Discovery

```bash
# List all stores
curl "http://localhost:8123/dimensions/stores"

# Search stores by region
curl "http://localhost:8123/dimensions/stores?region=North&page_size=10"

# Get specific store
curl "http://localhost:8123/dimensions/stores/1"

# Search products
curl "http://localhost:8123/dimensions/products?search=Cola&category=Beverage"
```

### Analytics KPIs

```bash
# Total KPIs for January
curl "http://localhost:8123/analytics/kpis?start_date=2024-01-01&end_date=2024-01-31"

# KPIs for specific store
curl "http://localhost:8123/analytics/kpis?start_date=2024-01-01&end_date=2024-01-31&store_id=1"

# Top stores by revenue
curl "http://localhost:8123/analytics/drilldowns?dimension=store&start_date=2024-01-01&end_date=2024-01-31&max_items=10"

# Category breakdown
curl "http://localhost:8123/analytics/drilldowns?dimension=category&start_date=2024-01-01&end_date=2024-01-31"
```

### Jobs Orchestration

```bash
# Create train job
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

# Check job status
curl "http://localhost:8123/jobs/abc123def456..."

# List failed jobs
curl "http://localhost:8123/jobs?status=failed"

# Cancel pending job
curl -X DELETE "http://localhost:8123/jobs/abc123def456..."
```

---

## Next Phase Preparation

Phase 8 (RAG Knowledge Base) will build on this serving layer to:
- Index OpenAPI schema for agent tool discovery
- Index documentation for evidence-grounded answers
- Provide `/rag/query` endpoint with citations
