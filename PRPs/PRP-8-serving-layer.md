# PRP-8: FastAPI Serving Layer (Typed Contracts, Agent-First API Design)

## Goal

Implement a production-ready serving layer that extends the existing ForecastOps API with:
- **Dimension Discovery**: Store/Product metadata endpoints for agent-driven resolution
- **Data Analytics**: KPI aggregations and drilldown queries
- **Job Orchestration**: Async-ready contracts with job_id tracking (sync implementation, async contracts)
- **RFC 7807 Problem Details**: Semantic error responses for agent troubleshooting
- **OpenAPI Export**: RAG-optimized schema export for LLM tool-calling
- **Standardized Mixins**: Unified pagination, filtering, and sorting patterns

**End State:** An agent-optimized serving layer where:
- LLM agents can discover available stores/products via dedicated endpoints
- Semantic error codes enable automatic troubleshooting workflows
- Rich OpenAPI descriptions optimize tool selection for LLM function calling
- Job orchestration contracts are async-ready for future background execution
- All validation gates passing (ruff, mypy, pyright, pytest)

---

## Why

- **Agent Discoverability**: LLM agents need to resolve natural keys (store_code, sku) before calling ingest/train/predict endpoints; dedicated discovery endpoints eliminate guesswork
- **Troubleshooting Autonomy**: RFC 7807 problem details with semantic error codes enable agents to diagnose and fix issues without human intervention
- **Data Exploration**: KPI and drilldown endpoints allow agents and dashboards to explore sales performance programmatically
- **Scalability Foundation**: Async-ready job contracts prepare for background execution of long-running operations (training, backtesting)
- **RAG Integration**: OpenAPI export with rich descriptions enables high-quality function calling via embeddings

---

## What

### User-Visible Behavior

1. **Dimension Discovery**
   - `GET /dimensions/stores` - List all stores with metadata (code, name, region, type)
   - `GET /dimensions/stores/{store_id}` - Get single store details
   - `GET /dimensions/products` - List all products with metadata (sku, name, category, brand)
   - `GET /dimensions/products/{product_id}` - Get single product details
   - Supports filtering by region, category, brand with pagination

2. **Data Analytics**
   - `GET /analytics/kpis` - Aggregated KPIs (total revenue, units, by store/category/date)
   - `GET /analytics/drilldowns` - Drill into KPIs by dimension (store, product, date range)

3. **Job Orchestration (Async-Ready)**
   - `POST /jobs` - Create new job (wraps train/predict/backtest)
   - `GET /jobs/{job_id}` - Poll job status (PENDING | RUNNING | COMPLETED | FAILED)
   - `GET /jobs` - List recent jobs with filtering
   - `DELETE /jobs/{job_id}` - Cancel pending/running job
   - Synchronous execution initially; contracts support future async migration

4. **RFC 7807 Error Responses**
   - All errors return structured Problem Details format
   - Domain-specific error types (URIs) for each error category
   - Instance URIs for error tracking/correlation

5. **OpenAPI Export**
   - `GET /openapi.json` - Standard OpenAPI 3.1 schema (already provided by FastAPI)
   - `scripts/export_openapi.py` - Export enriched schema for RAG indexing
   - All Field descriptions optimized for LLM tool selection

### Success Criteria

- [ ] Dimension discovery endpoints implemented with pagination and filtering
- [ ] KPI/drilldown endpoints with date range, store, product filters
- [ ] Job orchestration contracts defined (sync implementation)
- [ ] RFC 7807 ProblemDetail schema integrated with all error handlers
- [ ] All existing endpoints enhanced with rich Field descriptions
- [ ] OpenAPI export script produces RAG-ready documentation
- [ ] 50+ unit tests covering new features
- [ ] 15+ integration tests for new endpoints
- [ ] All validation gates green

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ - Include these in your context window

# RFC 7807/9457 Problem Details
- url: https://datatracker.ietf.org/doc/html/rfc7807
  why: "Original problem details standard"
  critical: "Use 'type' URI for error categorization, 'instance' for correlation"

- url: https://github.com/vapor-ware/fastapi-rfc7807
  why: "FastAPI RFC 7807 implementation reference"
  critical: "Pattern for exception handler integration"

# OpenAPI for LLM Tool Calling
- url: https://medium.com/percolation-labs/how-llm-apis-use-the-openapi-spec-for-function-calling-f37d76e0fef3
  why: "How LLMs use OpenAPI for function selection"
  critical: "Clear semantic naming and descriptions are crucial for tool selection"

- url: https://github.com/samchon/openapi
  why: "OpenAPI to LLM function calling schema converter"
  critical: "Rich descriptions significantly improve function calling accuracy"

# Internal Codebase References
- file: app/features/registry/routes.py
  why: "Pattern for pagination with Query params"
  pattern: "page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)"

- file: app/features/registry/schemas.py
  why: "Pattern for RunListResponse with pagination fields"
  pattern: "runs: list[RunResponse], total: int, page: int, page_size: int"

- file: app/features/ingest/service.py
  why: "KeyResolver pattern for store_code → store_id resolution"
  pattern: "resolve_store_codes(), resolve_skus()"

- file: app/core/exceptions.py
  why: "Base exception hierarchy to extend with RFC 7807"
  pattern: "ForecastLabError, forecastlab_exception_handler"

- file: app/features/data_platform/models.py
  why: "Store, Product, SalesDaily ORM models"
  pattern: "Mapped[], mapped_column(), relationships"

- file: examples/queries/kpi_sales.sql
  why: "SQL patterns for KPI aggregations"
  pattern: "SUM, COUNT, GROUP BY, DATE_TRUNC, RANK, NTILE"

- file: app/shared/schemas.py
  why: "Existing PaginatedResponse generic"
  pattern: "PaginatedResponse[T] with items, total, page, page_size, pages"
```

### Current Codebase Tree (Relevant Parts)

```text
app/
├── core/
│   ├── config.py           # Settings singleton (extend with job settings)
│   ├── database.py         # AsyncSession, get_db
│   ├── exceptions.py       # ForecastLabError hierarchy (EXTEND with RFC 7807)
│   ├── logging.py          # Structured logging
│   └── middleware.py       # RequestIdMiddleware
├── shared/
│   ├── schemas.py          # PaginatedResponse (EXTEND with mixins)
│   └── models.py           # TimestampMixin
├── features/
│   ├── data_platform/
│   │   └── models.py       # Store, Product, SalesDaily, Calendar
│   ├── ingest/
│   │   └── service.py      # KeyResolver (REFERENCE for lookups)
│   ├── forecasting/
│   │   └── routes.py       # train/predict endpoints
│   ├── backtesting/
│   │   └── routes.py       # backtest/run endpoint
│   └── registry/
│       ├── routes.py       # Run/Alias CRUD (REFERENCE for pagination)
│       └── schemas.py      # RunListResponse (REFERENCE)
└── main.py                 # Router registration
```

### Desired Codebase Tree (New Files)

```text
app/features/dimensions/              # NEW: Dimension discovery
├── __init__.py
├── routes.py                         # GET /dimensions/stores, /products
├── schemas.py                        # StoreResponse, ProductResponse, filters
├── service.py                        # DimensionService (paginated lookups)
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_routes.py                # Route tests
    └── test_service.py               # Service tests

app/features/analytics/               # NEW: KPI/Drilldown endpoints
├── __init__.py
├── routes.py                         # GET /analytics/kpis, /drilldowns
├── schemas.py                        # KPIResponse, DrilldownRequest, filters
├── service.py                        # AnalyticsService (aggregation queries)
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_routes.py
    └── test_service.py

app/features/jobs/                    # NEW: Job orchestration layer
├── __init__.py
├── models.py                         # Job ORM model (JSONB for params/result)
├── routes.py                         # POST /jobs, GET /jobs/{job_id}
├── schemas.py                        # JobCreate, JobResponse, JobStatus enum
├── service.py                        # JobService (sync execution, async contracts)
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_routes.py
    └── test_service.py

app/core/problem_details.py           # NEW: RFC 7807 implementation
                                      # ProblemDetail schema, exception handlers

app/shared/mixins.py                  # NEW: Pagination/filter/sort mixins

scripts/export_openapi.py             # NEW: RAG-optimized OpenAPI export

examples/api/dimensions.http          # NEW: Dimension discovery examples
examples/api/analytics.http           # NEW: KPI/drilldown examples
examples/api/jobs.http                # NEW: Job orchestration examples

alembic/versions/xxx_create_jobs_table.py  # NEW: Jobs table migration
```

### Known Gotchas

```python
# CRITICAL: RFC 7807 requires specific content type
# Content-Type: application/problem+json
# FastAPI JSONResponse can set this via media_type parameter

# CRITICAL: 'type' in Problem Details should be a URI
# Use relative URIs like "/errors/validation" or absolute URIs
# Example: "type": "https://api.forecastlabai.com/errors/unknown-store"

# CRITICAL: 'instance' should be request-specific
# Use request_id from middleware: f"/requests/{request_id}"

# CRITICAL: OpenAPI descriptions are used by LLMs for tool selection
# Keep descriptions concise but semantically rich
# BAD: "The ID"
# GOOD: "Unique store identifier from /dimensions/stores endpoint"

# CRITICAL: Pagination uses 1-indexed pages (not 0-indexed)
# Offset = (page - 1) * page_size

# CRITICAL: Jobs table uses JSONB for params and result
# This allows arbitrary job configurations without schema migration

# CRITICAL: Job status transitions must be validated
# PENDING -> RUNNING -> COMPLETED|FAILED
# PENDING -> CANCELLED (via DELETE)
# No other transitions allowed

# CRITICAL: KPI queries should use calendar table for date validation
# Don't trust user-provided dates without checking calendar table

# CRITICAL: Use SQLAlchemy func for aggregations
# from sqlalchemy import func
# func.sum(), func.count(), func.avg()

# CRITICAL: For large result sets, add row limits
# Analytics queries should have max_rows setting (default 10000)
```

---

## Implementation Blueprint

### Data Models

#### RFC 7807 Problem Details Schema

```python
# app/core/problem_details.py

from typing import Any
from pydantic import BaseModel, Field, ConfigDict


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details for HTTP APIs.

    This schema enables machine-readable error responses that LLM agents
    can use for automatic troubleshooting and retry logic.

    Attributes:
        type: URI identifying the error type (for categorization)
        title: Short human-readable summary
        status: HTTP status code
        detail: Human-readable explanation
        instance: URI for this specific error occurrence
        errors: Optional field-level validation errors
    """
    model_config = ConfigDict(extra="allow")  # Allow extensions

    type: str = Field(
        default="about:blank",
        description="URI reference identifying the problem type"
    )
    title: str = Field(
        ...,
        description="Short, human-readable summary of the problem"
    )
    status: int = Field(
        ...,
        ge=400,
        le=599,
        description="HTTP status code"
    )
    detail: str | None = Field(
        None,
        description="Human-readable explanation specific to this occurrence"
    )
    instance: str | None = Field(
        None,
        description="URI reference for this specific problem occurrence"
    )
    # Extension: validation errors for 422 responses
    errors: list[dict[str, Any]] | None = Field(
        None,
        description="Field-level validation errors (for 422 responses)"
    )
```

#### Job Model

```python
# app/features/jobs/models.py

class JobType(str, Enum):
    """Types of jobs that can be executed."""
    TRAIN = "train"
    PREDICT = "predict"
    BACKTEST = "backtest"


class JobStatus(str, Enum):
    """Job lifecycle states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(TimestampMixin, Base):
    """Background job tracking.

    CRITICAL: Stores job configuration and results as JSONB for flexibility.
    """
    __tablename__ = "job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    job_type: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.PENDING.value)

    # Job configuration (stored as JSONB for flexibility)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Result/error storage
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Linkage to model run (for train/backtest jobs)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
```

#### Dimension Schemas (Agent-Optimized)

```python
# app/features/dimensions/schemas.py

class StoreResponse(BaseModel):
    """Store dimension record for agent discovery.

    Use this endpoint to resolve store_code to store_id before calling
    ingest or forecasting endpoints.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(
        ...,
        description="Internal store ID. Use this value for store_id parameters."
    )
    code: str = Field(
        ...,
        description="Business store code (e.g., 'S001'). Unique identifier."
    )
    name: str = Field(
        ...,
        description="Human-readable store name for display purposes."
    )
    region: str | None = Field(
        None,
        description="Geographic region. Filter using region parameter."
    )
    city: str | None = Field(
        None,
        description="City where store is located."
    )
    store_type: str | None = Field(
        None,
        description="Store format (e.g., 'supermarket', 'express', 'warehouse')."
    )


class StoreListResponse(BaseModel):
    """Paginated list of stores with filtering metadata."""
    stores: list[StoreResponse] = Field(
        ...,
        description="Array of store records for current page."
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of stores matching filters."
    )
    page: int = Field(
        ...,
        ge=1,
        description="Current page number (1-indexed)."
    )
    page_size: int = Field(
        ...,
        ge=1,
        description="Number of stores per page."
    )


class StoreFilter(BaseModel):
    """Filter parameters for store queries."""
    region: str | None = Field(
        None,
        description="Filter by region (exact match)."
    )
    store_type: str | None = Field(
        None,
        description="Filter by store type (exact match)."
    )
    search: str | None = Field(
        None,
        min_length=2,
        description="Search in store code and name (case-insensitive)."
    )
```

### Task List

#### Task 1: Create RFC 7807 Problem Details module

```yaml
FILE: app/core/problem_details.py
ACTION: CREATE
IMPLEMENT:
  - ProblemDetail schema with RFC 7807 fields
  - Error type URIs for each error category:
    - /errors/not-found
    - /errors/validation
    - /errors/database
    - /errors/conflict
    - /errors/unauthorized
    - /errors/rate-limited
  - problem_detail_handler() exception handler
  - Mapping from ForecastLabError types to problem details
CRITICAL:
  - Set Content-Type: application/problem+json
  - Include instance URI with request_id
  - Handle Pydantic ValidationError specially (field-level errors)
VALIDATION:
  - uv run mypy app/core/problem_details.py
  - uv run pyright app/core/problem_details.py
```

#### Task 2: Integrate Problem Details into exception handlers

```yaml
FILE: app/core/exceptions.py
ACTION: MODIFY
IMPLEMENT:
  - Import ProblemDetail from problem_details
  - Update forecastlab_exception_handler to return ProblemDetail
  - Update unhandled_exception_handler to return ProblemDetail
  - Add error_type URI property to ForecastLabError subclasses
FIND: "async def forecastlab_exception_handler"
MODIFY: Return ProblemDetailResponse instead of dict
VALIDATION:
  - uv run pytest app/core/tests/test_exceptions.py -v
```

#### Task 3: Create dimensions module structure

```yaml
ACTION: CREATE directories and files
FILES:
  - app/features/dimensions/__init__.py
  - app/features/dimensions/schemas.py
  - app/features/dimensions/service.py
  - app/features/dimensions/routes.py
  - app/features/dimensions/tests/__init__.py
  - app/features/dimensions/tests/conftest.py
PATTERN: Mirror registry module structure
```

#### Task 4: Implement dimensions schemas

```yaml
FILE: app/features/dimensions/schemas.py
ACTION: CREATE
IMPLEMENT:
  - StoreResponse with rich Field descriptions
  - StoreListResponse for paginated results
  - StoreFilter for query parameters
  - ProductResponse with sku, name, category, brand
  - ProductListResponse for paginated results
  - ProductFilter for query parameters
CRITICAL:
  - Every Field must have a description optimized for LLM tool selection
  - Use pattern validation for code/sku formats
VALIDATION:
  - uv run mypy app/features/dimensions/schemas.py
```

#### Task 5: Implement dimensions service

```yaml
FILE: app/features/dimensions/service.py
ACTION: CREATE
IMPLEMENT:
  - DimensionService class
  - list_stores() - Paginated store list with filters
  - get_store() - Single store by ID
  - list_products() - Paginated product list with filters
  - get_product() - Single product by ID
  - search_stores() - Search by code/name
  - search_products() - Search by sku/name
PATTERN: Mirror registry service pattern
CRITICAL:
  - Use async SQLAlchemy queries
  - Apply filters with ilike() for case-insensitive search
  - Count total before applying pagination
VALIDATION:
  - uv run mypy app/features/dimensions/service.py
```

#### Task 6: Implement dimensions routes

```yaml
FILE: app/features/dimensions/routes.py
ACTION: CREATE
IMPLEMENT:
  - APIRouter(prefix="/dimensions", tags=["dimensions"])
  - GET /stores - List stores with pagination and filters
  - GET /stores/{store_id} - Get store by ID
  - GET /products - List products with pagination and filters
  - GET /products/{product_id} - Get product by ID
CRITICAL:
  - Rich OpenAPI descriptions on each endpoint
  - Include example responses in docstrings
  - Log dimension queries for analytics
VALIDATION:
  - uv run mypy app/features/dimensions/routes.py
```

#### Task 7: Create analytics module structure

```yaml
ACTION: CREATE directories and files
FILES:
  - app/features/analytics/__init__.py
  - app/features/analytics/schemas.py
  - app/features/analytics/service.py
  - app/features/analytics/routes.py
  - app/features/analytics/tests/__init__.py
  - app/features/analytics/tests/conftest.py
```

#### Task 8: Implement analytics schemas

```yaml
FILE: app/features/analytics/schemas.py
ACTION: CREATE
IMPLEMENT:
  - DateRange filter (start_date, end_date with validation)
  - KPIRequest (dimensions to group by, date range)
  - KPIResponse (revenue, units, orders, avg_basket)
  - DrilldownRequest (dimension, filter, date range)
  - DrilldownResponse (breakdown by dimension value)
  - TimeGranularity enum (day, week, month, quarter)
CRITICAL:
  - Validate date range (end >= start)
  - Max date range constraint (e.g., 2 years)
  - Rich descriptions for LLM tool selection
VALIDATION:
  - uv run mypy app/features/analytics/schemas.py
```

#### Task 9: Implement analytics service

```yaml
FILE: app/features/analytics/service.py
ACTION: CREATE
IMPLEMENT:
  - AnalyticsService class
  - compute_kpis() - Aggregate revenue/units by dimension
  - compute_drilldown() - Drill into specific dimension
  - _build_kpi_query() - SQL builder for aggregations
PATTERN: Use SQLAlchemy func for aggregations
CRITICAL:
  - Validate dates exist in calendar table
  - Apply max_rows limit (setting)
  - Use DATE_TRUNC for time grouping
VALIDATION:
  - uv run mypy app/features/analytics/service.py
```

#### Task 10: Implement analytics routes

```yaml
FILE: app/features/analytics/routes.py
ACTION: CREATE
IMPLEMENT:
  - APIRouter(prefix="/analytics", tags=["analytics"])
  - GET /kpis - Compute KPIs with filters
  - GET /drilldowns - Drill into dimension
CRITICAL:
  - Rich OpenAPI descriptions with examples
  - Response models for type safety
  - Appropriate caching headers
VALIDATION:
  - uv run mypy app/features/analytics/routes.py
```

#### Task 11: Create jobs module structure

```yaml
ACTION: CREATE directories and files
FILES:
  - app/features/jobs/__init__.py
  - app/features/jobs/models.py
  - app/features/jobs/schemas.py
  - app/features/jobs/service.py
  - app/features/jobs/routes.py
  - app/features/jobs/tests/__init__.py
  - app/features/jobs/tests/conftest.py
```

#### Task 12: Implement jobs ORM model

```yaml
FILE: app/features/jobs/models.py
ACTION: CREATE
IMPLEMENT:
  - JobType enum (train, predict, backtest)
  - JobStatus enum (pending, running, completed, failed, cancelled)
  - Job model with JSONB params and result
  - Indexes on job_id, status, job_type
  - Check constraint for valid status values
PATTERN: Mirror registry ModelRun model
VALIDATION:
  - uv run mypy app/features/jobs/models.py
```

#### Task 13: Create jobs migration

```yaml
ACTION: Run alembic revision
COMMAND: uv run alembic revision --autogenerate -m "create_jobs_table"
IMPLEMENT:
  - Create job table with JSONB columns
  - Add indexes
  - Add check constraints
VALIDATION:
  - uv run alembic upgrade head
  - uv run alembic downgrade -1
  - uv run alembic upgrade head
```

#### Task 14: Implement jobs schemas

```yaml
FILE: app/features/jobs/schemas.py
ACTION: CREATE
IMPLEMENT:
  - JobType, JobStatus enums
  - VALID_JOB_TRANSITIONS dict
  - JobCreate (job_type, params as dict)
  - JobResponse (job_id, status, params, result, timing)
  - JobListResponse (pagination)
CRITICAL:
  - params is flexible JSONB - validated by job type handlers
  - Rich descriptions for LLM orchestration
VALIDATION:
  - uv run mypy app/features/jobs/schemas.py
```

#### Task 15: Implement jobs service

```yaml
FILE: app/features/jobs/service.py
ACTION: CREATE
IMPLEMENT:
  - JobService class
  - create_job() - Create PENDING job, execute synchronously
  - get_job() - Get job by job_id
  - list_jobs() - List with filtering and pagination
  - cancel_job() - Cancel PENDING job
  - _execute_train() - Delegate to ForecastingService
  - _execute_predict() - Delegate to ForecastingService
  - _execute_backtest() - Delegate to BacktestingService
  - _validate_params() - Validate params for job type
CRITICAL:
  - Jobs execute synchronously (contracts ready for async)
  - Capture execution time
  - Store result or error in JSONB
  - Link to run_id for train/backtest jobs
VALIDATION:
  - uv run mypy app/features/jobs/service.py
```

#### Task 16: Implement jobs routes

```yaml
FILE: app/features/jobs/routes.py
ACTION: CREATE
IMPLEMENT:
  - APIRouter(prefix="/jobs", tags=["jobs"])
  - POST /jobs - Create and execute job (returns job_id)
  - GET /jobs - List jobs with filtering
  - GET /jobs/{job_id} - Get job status and result
  - DELETE /jobs/{job_id} - Cancel pending job
CRITICAL:
  - Response includes job_id for polling
  - Rich descriptions explain job types and params
  - 202 Accepted for creation (async-ready semantics)
VALIDATION:
  - uv run mypy app/features/jobs/routes.py
```

#### Task 17: Add settings for new features

```yaml
FILE: app/core/config.py
ACTION: MODIFY
IMPLEMENT:
  - analytics_max_rows: int = 10000
  - analytics_max_date_range_days: int = 730
  - jobs_retention_days: int = 30
FIND: "registry_duplicate_policy"
INJECT AFTER: New settings
VALIDATION:
  - uv run mypy app/core/config.py
```

#### Task 18: Register new routers in main.py

```yaml
FILE: app/main.py
ACTION: MODIFY
IMPLEMENT:
  - Import dimensions, analytics, jobs routers
  - Register with app.include_router()
FIND: "from app.features.registry.routes import router as registry_router"
INJECT AFTER:
  - "from app.features.dimensions.routes import router as dimensions_router"
  - "from app.features.analytics.routes import router as analytics_router"
  - "from app.features.jobs.routes import router as jobs_router"
FIND: "app.include_router(registry_router)"
INJECT AFTER:
  - "app.include_router(dimensions_router)"
  - "app.include_router(analytics_router)"
  - "app.include_router(jobs_router)"
VALIDATION:
  - uv run python -c "from app.main import app; print('OK')"
```

#### Task 19: Create shared mixins module

```yaml
FILE: app/shared/mixins.py
ACTION: CREATE
IMPLEMENT:
  - SortOrder enum (asc, desc)
  - SortParams generic mixin
  - FilterMixin base class
  - PaginationMixin with helper methods
  - DateRangeMixin with validation
PATTERN: Reusable across all list endpoints
VALIDATION:
  - uv run mypy app/shared/mixins.py
```

#### Task 20: Enhance existing endpoint descriptions

```yaml
FILES:
  - app/features/ingest/schemas.py
  - app/features/forecasting/schemas.py
  - app/features/backtesting/schemas.py
  - app/features/registry/schemas.py
ACTION: MODIFY
IMPLEMENT:
  - Add rich Field descriptions to all fields
  - Include "Use X endpoint to get valid values" hints
  - Add examples where helpful
PATTERN:
  - store_id: int = Field(..., description="Store ID from GET /dimensions/stores")
  - sku: str = Field(..., description="Product SKU from GET /dimensions/products")
VALIDATION:
  - uv run mypy app/features/*/schemas.py
```

#### Task 21: Create OpenAPI export script

```yaml
FILE: scripts/export_openapi.py
ACTION: CREATE
IMPLEMENT:
  - Load FastAPI app
  - Extract OpenAPI schema via app.openapi()
  - Enrich with additional metadata for RAG
  - Export to artifacts/openapi/schema.json
  - Export markdown summary for embedding
CRITICAL:
  - Include all operation descriptions
  - Include all schema descriptions
  - Include error response schemas
VALIDATION:
  - uv run python scripts/export_openapi.py
  - Check artifacts/openapi/schema.json exists
```

#### Task 22: Create dimension tests

```yaml
FILES:
  - app/features/dimensions/tests/test_schemas.py
  - app/features/dimensions/tests/test_service.py
  - app/features/dimensions/tests/test_routes.py
ACTION: CREATE
IMPLEMENT:
  - Schema validation tests
  - Service pagination tests
  - Service filter tests
  - Route integration tests
VALIDATION:
  - uv run pytest app/features/dimensions/tests/ -v
```

#### Task 23: Create analytics tests

```yaml
FILES:
  - app/features/analytics/tests/test_schemas.py
  - app/features/analytics/tests/test_service.py
  - app/features/analytics/tests/test_routes.py
ACTION: CREATE
IMPLEMENT:
  - Date range validation tests
  - KPI computation tests
  - Drilldown tests
  - Route integration tests
VALIDATION:
  - uv run pytest app/features/analytics/tests/ -v
```

#### Task 24: Create jobs tests

```yaml
FILES:
  - app/features/jobs/tests/test_models.py
  - app/features/jobs/tests/test_schemas.py
  - app/features/jobs/tests/test_service.py
  - app/features/jobs/tests/test_routes.py
ACTION: CREATE
IMPLEMENT:
  - Model creation tests
  - Status transition tests
  - Job execution tests (mock services)
  - Route integration tests
VALIDATION:
  - uv run pytest app/features/jobs/tests/ -v
```

#### Task 25: Create example HTTP files

```yaml
FILES:
  - examples/api/dimensions.http
  - examples/api/analytics.http
  - examples/api/jobs.http
ACTION: CREATE
IMPLEMENT:
  - Dimension discovery examples
  - KPI query examples
  - Job creation and polling examples
PATTERN: Mirror ingest_sales_daily.http format
```

#### Task 26: Update module __init__.py exports

```yaml
FILES:
  - app/features/dimensions/__init__.py
  - app/features/analytics/__init__.py
  - app/features/jobs/__init__.py
ACTION: MODIFY
IMPLEMENT:
  - Export all public classes
  - Alphabetically sorted __all__
VALIDATION:
  - uv run python -c "from app.features.dimensions import *"
  - uv run python -c "from app.features.analytics import *"
  - uv run python -c "from app.features.jobs import *"
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run after EACH file creation
uv run ruff check app/features/dimensions/ app/features/analytics/ app/features/jobs/ app/core/problem_details.py --fix
uv run ruff format app/features/dimensions/ app/features/analytics/ app/features/jobs/ app/core/

# Expected: All checks passed!
```

### Level 2: Type Checking

```bash
# Run after completing each module
uv run mypy app/features/dimensions/
uv run mypy app/features/analytics/
uv run mypy app/features/jobs/
uv run mypy app/core/problem_details.py

uv run pyright app/features/dimensions/
uv run pyright app/features/analytics/
uv run pyright app/features/jobs/

# Expected: Success: no issues found
```

### Level 3: Database Migration

```bash
# After creating jobs models.py
uv run alembic revision --autogenerate -m "create_jobs_table"
uv run alembic upgrade head

# Verify table exists
docker exec -it postgres psql -U forecastlab -d forecastlab -c "\d job"
```

### Level 4: Unit Tests

```bash
# Run incrementally
uv run pytest app/features/dimensions/tests/ -v -m "not integration"
uv run pytest app/features/analytics/tests/ -v -m "not integration"
uv run pytest app/features/jobs/tests/ -v -m "not integration"

# Run all unit tests
uv run pytest app/features/dimensions/ app/features/analytics/ app/features/jobs/ -v -m "not integration"

# Expected: 50+ tests passed
```

### Level 5: Integration Tests

```bash
# Start database
docker-compose up -d

# Seed test data
uv run python examples/seed_demo_data.py

# Run integration tests
uv run pytest app/features/dimensions/tests/ -v -m integration
uv run pytest app/features/analytics/tests/ -v -m integration
uv run pytest app/features/jobs/tests/ -v -m integration

# Expected: 15+ integration tests passed
```

### Level 6: API Integration Test

```bash
# Start API
uv run uvicorn app.main:app --reload --port 8123

# Test dimension discovery
curl http://localhost:8123/dimensions/stores
curl http://localhost:8123/dimensions/stores?region=North
curl http://localhost:8123/dimensions/products?category=Beverage

# Test analytics
curl "http://localhost:8123/analytics/kpis?start_date=2024-01-01&end_date=2024-01-31"
curl "http://localhost:8123/analytics/drilldowns?dimension=store&start_date=2024-01-01&end_date=2024-01-31"

# Test job creation
curl -X POST http://localhost:8123/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "train",
    "params": {
      "store_id": 1,
      "product_id": 1,
      "train_start_date": "2024-01-01",
      "train_end_date": "2024-06-30",
      "config": {"model_type": "naive"}
    }
  }'

# Poll job status
curl http://localhost:8123/jobs/{job_id}
```

### Level 7: OpenAPI Export

```bash
# Export schema
uv run python scripts/export_openapi.py

# Verify export
ls -la artifacts/openapi/
cat artifacts/openapi/schema.json | jq '.info'
```

### Level 8: Full Validation

```bash
# Complete validation suite
uv run ruff check . && \
uv run mypy app/ && \
uv run pyright app/ && \
uv run pytest -v

# Expected: All green
```

---

## Final Checklist

- [ ] All 26 tasks completed
- [ ] `uv run ruff check .` — no errors
- [ ] `uv run mypy app/` — no errors
- [ ] `uv run pyright app/` — no errors
- [ ] `uv run pytest -v` — 50+ new tests passed
- [ ] Alembic migration runs successfully
- [ ] Dimension endpoints return paginated results
- [ ] Analytics endpoints compute KPIs correctly
- [ ] Job orchestration creates and executes jobs
- [ ] RFC 7807 error responses include type/instance URIs
- [ ] OpenAPI export script produces valid JSON
- [ ] All Field descriptions optimized for LLM tool selection
- [ ] Example HTTP files work with VS Code REST Client
- [ ] Routers registered in main.py

---

## Anti-Patterns to Avoid

- **DON'T** use generic descriptions like "The ID" — be specific about where to get values
- **DON'T** skip error type URIs — they enable agent troubleshooting
- **DON'T** use 0-indexed pagination — always 1-indexed
- **DON'T** allow unbounded queries — always apply max_rows limits
- **DON'T** skip date validation against calendar table
- **DON'T** use sync operations in async context
- **DON'T** hardcode settings — use config.py
- **DON'T** forget to register routers in main.py
- **DON'T** create jobs without validating params against job type
- **DON'T** return 200 for job creation — use 202 Accepted (async-ready)

---

## Sources

- [RFC 7807: Problem Details for HTTP APIs](https://datatracker.ietf.org/doc/html/rfc7807)
- [fastapi-rfc7807 Library](https://github.com/vapor-ware/fastapi-rfc7807)
- [How LLM APIs Use OpenAPI for Function Calling](https://medium.com/percolation-labs/how-llm-apis-use-the-openapi-spec-for-function-calling-f37d76e0fef3)
- [OpenAPI LLM Function Calling Composer](https://github.com/samchon/openapi)
- [Optimizing Tool Calling for LLMs](https://www.useparagon.com/learn/rag-best-practices-optimizing-tool-calling/)
- [Use OpenAPI Instead of MCP for LLM Tools](https://www.binwang.me/2025-04-27-Use-OpenAPI-Instead-of-MCP-for-LLM-Tools.html)

---

## Confidence Score: 8.5/10

**Strengths:**
- Clear patterns from existing registry/forecasting modules
- Well-defined RFC 7807 standard to follow
- Existing dimension models (Store, Product) are already in data_platform
- Job orchestration mirrors registry run lifecycle pattern
- KPI queries have SQL patterns in examples/queries/
- Comprehensive test patterns from backtesting module

**Risks:**
- RFC 7807 integration requires careful exception handler refactoring
- Analytics queries may need optimization for large datasets
- Job execution delegates to multiple services (coupling)
- OpenAPI enrichment may require custom schema extensions

**Mitigation:**
- Start with simple Problem Details, enhance incrementally
- Add analytics_max_rows setting and query timeouts
- Use dependency injection for job executors
- Test OpenAPI export with actual LLM tool calling

---

## Implementation Order (Suggested)

1. **Phase A**: RFC 7807 Problem Details (Tasks 1-2) — Foundational
2. **Phase B**: Dimensions Module (Tasks 3-6) — Simple, high value
3. **Phase C**: Analytics Module (Tasks 7-10) — Medium complexity
4. **Phase D**: Jobs Module (Tasks 11-16) — Most complex
5. **Phase E**: Integration (Tasks 17-21) — Wire everything together
6. **Phase F**: Testing & Polish (Tasks 22-26) — Validation
