# ForecastLabAI - Phase Index

This document indexes all implementation phases of the ForecastLabAI project.

---

## Phase Overview

| Phase | Name | Status | PRP | Documentation |
|-------|------|--------|-----|---------------|
| 0 | Project Foundation | Completed | PRP-0, PRP-1 | [0-INIT_PHASE.md](./PHASE/0-INIT_PHASE.md) |
| 1 | Data Platform | Completed | PRP-2 | [1-DATA_PLATFORM.md](./PHASE/1-DATA_PLATFORM.md) |
| 2 | Ingest Layer | Completed | PRP-3 | [2-INGEST_LAYER.md](./PHASE/2-INGEST_LAYER.md) |
| 3 | Feature Engineering | Completed | PRP-4 | [3-FEATURE_ENGINEERING.md](./PHASE/3-FEATURE_ENGINEERING.md) |
| 4 | Forecasting | Completed | PRP-5 | [4-FORECASTING.md](./PHASE/4-FORECASTING.md) |
| 5 | Backtesting | Completed | PRP-6 | [5-BACKTESTING.md](./PHASE/5-BACKTESTING.md) |
| 6 | Model Registry | Completed | PRP-7 | [6-MODEL_REGISTRY.md](./PHASE/6-MODEL_REGISTRY.md) |
| 7 | Serving Layer | Completed | PRP-8 | [7-SERVING_LAYER.md](./PHASE/7-SERVING_LAYER.md) |
| 8 | RAG Knowledge Base | Pending | PRP-9 | - |
| 9 | Dashboard | Pending | PRP-10 | - |
| 10 | Agentic Layer | Pending | - | - |

---

## Completed Phases

### [Phase 0: Project Foundation (INIT_PHASE)](./PHASE/0-INIT_PHASE.md)

**Date Completed**: 2026-01-26

**Summary**: Established the foundational infrastructure for ForecastLabAI including:
- Project configuration with strict type checking (MyPy + Pyright)
- Docker-based PostgreSQL + pgvector infrastructure
- Core modules: config, database, logging, middleware, exceptions
- Health check endpoints with request correlation
- Async Alembic migrations
- Comprehensive test suite (14 tests)

**Key Deliverables**:
- `pyproject.toml` - Project configuration with all dependencies
- `docker-compose.yml` - PostgreSQL + pgvector container
- `app/core/` - Core infrastructure (7 modules)
- `app/shared/` - Shared utilities (3 modules)
- `app/main.py` - FastAPI application entry point
- `alembic/` - Async migration setup
- `.github/workflows/` - CI/CD pipelines (5 workflows)
  - `ci.yml` - Lint, typecheck, test, migration check
  - `schema-validation.yml` - Migration drift detection
  - `dependency-check.yml` - Weekly vulnerability scanning
  - `phase-snapshot.yml` - Audit snapshots for phase-* branches
  - `cd-release.yml` - Automated semantic versioning releases

**Validation Results**:
- Ruff: All checks passed
- MyPy: 0 errors (20 files)
- Pyright: 0 errors
- Pytest: 14 tests passed

### [Phase 1: Data Platform](./PHASE/1-DATA_PLATFORM.md)

**Date Completed**: 2026-01-26
**Release**: v0.1.3

**Summary**: Mini-warehouse schema for retail demand forecasting with:
- 7 SQLAlchemy 2.0 ORM models (3 dimension + 4 fact tables)
- Star schema: Store, Product, Calendar (dimensions) + SalesDaily, PriceHistory, Promotion, InventorySnapshotDaily (facts)
- Grain protection via unique constraints for idempotent upserts
- Check constraints for data quality (positive quantities, valid date ranges)
- Composite indexes for query performance
- 32 unit tests + 11 integration tests

**Key Deliverables**:
- `app/features/data_platform/models.py` - All ORM models with relationships
- `app/features/data_platform/schemas.py` - Pydantic validation schemas
- `alembic/versions/e1165ebcef61_create_data_platform_tables.py` - Baseline migration
- `examples/schema/README.md` - Table documentation with ERD
- `examples/queries/` - KPI and join pattern examples

**Validation Results**:
- Ruff: All checks passed
- MyPy: 0 errors
- Pyright: 0 errors
- Pytest: 43 tests passed (32 unit + 11 integration)

### [Phase 2: Ingest Layer](./PHASE/2-INGEST_LAYER.md)

**Date Completed**: 2026-01-26

**Summary**: Idempotent batch upsert endpoint for sales data ingestion with:
- `POST /ingest/sales-daily` endpoint for batch upserts
- Natural key resolution (store_code -> store_id, sku -> product_id)
- PostgreSQL `ON CONFLICT DO UPDATE` for replay-safe idempotency
- Partial success handling (valid rows processed, invalid rows returned with errors)
- Calendar date validation (FK constraint enforcement)
- Structured logging with duration metrics

**Key Deliverables**:
- `app/features/ingest/routes.py` - POST /ingest/sales-daily endpoint
- `app/features/ingest/schemas.py` - Request/response Pydantic schemas
- `app/features/ingest/service.py` - KeyResolver and upsert_sales_daily_batch logic
- `app/core/config.py` - Added ingest_batch_size, ingest_timeout_seconds settings
- `examples/api/ingest_sales_daily.http` - HTTP client examples

**Error Codes**:
- `UNKNOWN_STORE` - Store code not found in database
- `UNKNOWN_PRODUCT` - SKU not found in database
- `UNKNOWN_DATE` - Date not found in calendar table

**API Response Schema**:
```json
{
  "processed_count": 10,
  "rejected_count": 2,
  "total_received": 12,
  "errors": [
    {
      "row_index": 5,
      "store_code": "INVALID",
      "sku": "SKU-001",
      "date": "2024-01-15",
      "error_code": "UNKNOWN_STORE",
      "error_message": "Store code 'INVALID' not found"
    }
  ],
  "duration_ms": 45.23
}
```

### [Phase 3: Feature Engineering](./PHASE/3-FEATURE_ENGINEERING.md)

**Date Completed**: 2026-01-31

**Summary**: Time-safe feature engineering with CRITICAL leakage prevention:
- FeatureEngineeringService with lag, rolling, calendar, and exogenous features
- CRITICAL: Lag features use positive shift() only (no future data access)
- CRITICAL: Rolling features use shift(1) BEFORE rolling to exclude current observation
- CRITICAL: Group-aware operations prevent cross-series leakage
- FastAPI endpoints: POST /featuresets/compute, POST /featuresets/preview
- 55 unit tests including comprehensive leakage prevention tests

**Key Deliverables**:
- `app/features/featuresets/schemas.py` - Pydantic schemas for feature configuration
- `app/features/featuresets/service.py` - FeatureEngineeringService
- `app/features/featuresets/routes.py` - API endpoints
- `app/features/featuresets/tests/` - 55 tests (schemas, service, leakage prevention)
- `examples/compute_features_demo.py` - Demo script

**Feature Types**:
- **Lag features**: Past values at specified lag periods with optional fill_value
- **Rolling features**: Mean, std, min, max, sum over configurable windows
- **Calendar features**: Day of week, month, quarter with cyclical encoding (sin/cos)
- **Imputation**: Zero-fill for sales, forward-fill for prices

**Validation Results**:
- Ruff: All checks passed
- MyPy: 0 errors
- Pyright: 0 errors
- Pytest: 55 tests passed

### Phase 4: Forecasting

**Date Completed**: 2026-01-31

**Summary**: Model zoo with unified forecaster interface:
- BaseForecaster abstract class with `fit()` and `predict()` methods
- Naive, SeasonalNaive, MovingAverage models implemented
- LightGBM model (feature-flagged, disabled by default)
- Model bundle persistence with joblib (fitted model + config + metadata)
- POST /forecasting/train and POST /forecasting/predict endpoints

**Key Deliverables**:
- `app/features/forecasting/models.py` - BaseForecaster and model implementations
- `app/features/forecasting/persistence.py` - ModelBundle save/load
- `app/features/forecasting/schemas.py` - Request/response schemas
- `app/features/forecasting/service.py` - ForecastingService
- `app/features/forecasting/routes.py` - API endpoints
- `examples/models/` - Baseline model examples

### Phase 5: Backtesting

**Date Completed**: 2026-01-31

**Summary**: Time-series cross-validation with comprehensive metrics:
- TimeSeriesSplitter with expanding/sliding window strategies
- Gap parameter for operational latency simulation
- Metrics: MAE, sMAPE (0-200), WAPE, Bias, Stability Index
- Automatic baseline comparisons (naive, seasonal_naive)
- Per-fold and aggregated metric storage
- POST /backtesting/run endpoint

**Key Deliverables**:
- `app/features/backtesting/splitter.py` - TimeSeriesSplitter
- `app/features/backtesting/metrics.py` - Metrics computation
- `app/features/backtesting/schemas.py` - Request/response schemas
- `app/features/backtesting/service.py` - BacktestingService
- `app/features/backtesting/routes.py` - API endpoint
- `examples/backtest/` - Usage examples (95 unit + 16 integration tests)

### Phase 6: Model Registry

**Date Completed**: 2026-02-01

**Summary**: Full run tracking and deployment alias management:
- ModelRun ORM with JSONB columns (model_config, metrics, runtime_info)
- DeploymentAlias for mutable pointers to successful runs
- State machine: PENDING → RUNNING → SUCCESS/FAILED → ARCHIVED
- LocalFSProvider with SHA-256 integrity verification
- Duplicate detection (configurable: allow/deny/detect)
- Runtime environment capture and agent context tracking

**Key Deliverables**:
- `app/features/registry/models.py` - ModelRun, DeploymentAlias ORM models
- `app/features/registry/storage.py` - LocalFSProvider with abstract interface
- `app/features/registry/schemas.py` - Request/response schemas
- `app/features/registry/service.py` - RegistryService
- `app/features/registry/routes.py` - API endpoints (runs, aliases, compare)
- `alembic/versions/a2f7b3c8d901_create_model_registry_tables.py` - Migration
- `examples/registry_demo.py` - Workflow demo

**API Endpoints**:
- `POST /registry/runs` - Create run
- `GET /registry/runs` - List with filters and pagination
- `PATCH /registry/runs/{run_id}` - Update status/metrics/artifacts
- `GET /registry/runs/{run_id}/verify` - Verify artifact integrity
- `POST /registry/aliases` - Create deployment alias
- `GET /registry/compare/{run_id_a}/{run_id_b}` - Compare runs

**Validation Results**:
- Ruff: All checks passed
- Pyright: 0 errors
- Pytest: 103 unit + 24 integration tests

### Phase 7: Serving Layer

**Date Completed**: 2026-02-01

**Summary**: Agent-first API design with RFC 7807 error responses:
- RFC 7807 Problem Details for semantic error responses
- Dimensions module for store/product discovery (LLM tool-calling optimized)
- Analytics module for KPI aggregations and drilldown analysis
- Jobs module for async-ready task orchestration
- Rich OpenAPI descriptions for all endpoints

**Key Deliverables**:
- `app/core/problem_details.py` - RFC 7807 ProblemDetail schema and helpers
- `app/features/dimensions/` - Store/product discovery endpoints
- `app/features/analytics/` - KPI and drilldown endpoints
- `app/features/jobs/` - Job ORM model, service, and endpoints
- `alembic/versions/37e16ecef223_create_jobs_table.py` - Job table migration

**API Endpoints**:
- `GET /dimensions/stores` - List stores with pagination and filtering
- `GET /dimensions/stores/{store_id}` - Get store by ID
- `GET /dimensions/products` - List products with pagination and filtering
- `GET /dimensions/products/{product_id}` - Get product by ID
- `GET /analytics/kpis` - Compute KPIs for date range
- `GET /analytics/drilldowns` - Drill into dimension
- `POST /jobs` - Create and execute job
- `GET /jobs` - List jobs with filtering
- `GET /jobs/{job_id}` - Get job status
- `DELETE /jobs/{job_id}` - Cancel pending job

**Configuration (Settings)**:
```python
analytics_max_rows: int = 10000
analytics_max_date_range_days: int = 730
jobs_retention_days: int = 30
```

**Validation Results**:
- Ruff: All checks passed
- MyPy: 0 errors (103 source files)
- Pyright: 0 errors
- Pytest: 426 unit tests passed

---

## Pending Phases

### Phase 8: RAG Knowledge Base
pgvector embeddings with evidence-grounded answers and citations.

### Phase 9: Dashboard
React + Vite + shadcn/ui frontend with data tables and visualizations.

### Phase 10: Agentic Layer (Optional)
PydanticAI integration for experiment orchestration.

---

## Phase Documentation Structure

Each phase document (`docs/PHASE/X-PHASE_NAME.md`) contains:

1. **Executive Summary** - High-level overview and objectives
2. **Deliverables** - Detailed description of all created files
3. **Configuration** - Settings and environment variables
4. **API Endpoints** - New routes and schemas (if applicable)
5. **Database Changes** - Models and migrations (if applicable)
6. **Test Coverage** - Test files and results
7. **Validation Results** - Linting and type checking outcomes
8. **Directory Structure** - File tree of changes
9. **Next Phase Preparation** - Dependencies for upcoming work

---

## Quick Links

- [Architecture Overview](./ARCHITECTURE.md)
- [ADR Index](./ADR/ADR-INDEX.md)
- [GitHub Workflows Guide](./github/github-quickstart.md)
- [GitHub Workflow Diagrams](./github/diagrams/README.md)
- [Logging Standard](./validation/logging-standard.md)
- [MyPy Standard](./validation/mypy-standard.md)
- [Pyright Standard](./validation/pyright-standard.md)
- [Pytest Standard](./validation/pytest-standard.md)
- [Ruff Standard](./validation/ruff-standard.md)

---

## Version History

| Date | Phase | Action |
|------|-------|--------|
| 2026-01-26 | 0 | Initial project foundation completed |
| 2026-01-26 | 0 | Added CI/CD infrastructure (5 GitHub Actions workflows) |
| 2026-01-26 | 1 | Data Platform schema and migrations completed (v0.1.3) |
| 2026-01-26 | 2 | Ingest Layer with POST /ingest/sales-daily endpoint completed |
| 2026-01-31 | 3 | Feature Engineering with time-safe leakage prevention completed |
| 2026-01-31 | 4 | Forecasting module with model zoo completed |
| 2026-01-31 | 5 | Backtesting module with time-series CV completed |
| 2026-02-01 | 6 | Model Registry with run tracking and deployment aliases completed |
| 2026-02-01 | 7 | Serving Layer with RFC 7807, dimensions, analytics, and jobs completed |
