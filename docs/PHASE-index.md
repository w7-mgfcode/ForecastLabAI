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
| 4 | Forecasting | Pending | PRP-5 | - |
| 5 | Backtesting | Pending | PRP-6 | - |
| 6 | Model Registry | Pending | PRP-7 | - |
| 7 | RAG Knowledge Base | Pending | PRP-8 | - |
| 8 | Dashboard | Pending | PRP-9 | - |
| 9 | Agentic Layer | Pending | - | - |

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

---

## Pending Phases

### Phase 4: Forecasting
Model zoo with unified interface for naive, seasonal, and ML models.

### Phase 5: Backtesting
Rolling and expanding time-based cross-validation with per-series metrics.

### Phase 6: Model Registry
Run tracking with config, metrics, artifacts, and data windows.

### Phase 7: RAG Knowledge Base
pgvector embeddings with evidence-grounded answers and citations.

### Phase 8: Dashboard
React + Vite + shadcn/ui frontend with data tables and visualizations.

### Phase 9: Agentic Layer (Optional)
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
