# Phase 0: Project Foundation (INIT_PHASE)

**Status**: Completed
**PRP Reference**: `PRPs/PRP-0-project-foundation.md`
**Date Completed**: 2026-01-26

---

## Executive Summary

Phase 0 establishes the foundational infrastructure for ForecastLabAI, a portfolio-grade retail demand forecasting system. This phase focused on creating a robust, type-safe, and production-ready backend skeleton following vertical slice architecture principles. All code passes strict type checking (MyPy + Pyright), linting (Ruff), and comprehensive test coverage.

---

## Objectives

### Primary Goals
1. Establish project structure following vertical slice architecture
2. Configure strict type checking and linting toolchain
3. Implement core infrastructure (config, database, logging, middleware)
4. Create health check endpoints for service monitoring
5. Set up async database migrations with Alembic
6. Provide Docker-based infrastructure (PostgreSQL + pgvector)

### Design Principles Applied
- **KISS**: Simple, readable solutions without premature abstractions
- **YAGNI**: Only implemented what was required for foundation
- **Type Safety**: Strict MyPy + Pyright enforcement
- **AI-Optimized Patterns**: Structured JSON logging with request correlation

---

## Deliverables

### 1. Project Configuration (`pyproject.toml`)

Complete Python project configuration with:

```toml
[project]
name = "forecastlabai"
version = "0.1.0"
requires-python = ">=3.12"
```

**Dependencies**:
| Package | Version | Purpose |
|---------|---------|---------|
| FastAPI | >=0.115.0 | Web framework |
| Pydantic | >=2.10.0 | Data validation |
| Pydantic-Settings | >=2.6.0 | Environment configuration |
| SQLAlchemy | >=2.0.36 | Async ORM |
| asyncpg | >=0.30.0 | PostgreSQL async driver |
| structlog | >=24.4.0 | Structured logging |
| Alembic | >=1.14.0 | Database migrations |
| uvicorn | >=0.32.0 | ASGI server |

**Dev Dependencies**:
| Package | Version | Purpose |
|---------|---------|---------|
| pytest | >=8.3.0 | Testing framework |
| pytest-asyncio | >=0.24.0 | Async test support |
| httpx | >=0.28.0 | Async HTTP client for tests |
| ruff | >=0.8.0 | Linting and formatting |
| mypy | >=1.13.0 | Static type checking |
| pyright | >=1.1.390 | Static type checking |

**Tool Configurations**:
- Ruff: Target Python 3.12, 100 char line length, comprehensive rule set
- MyPy: Strict mode with practical adjustments for FastAPI
- Pyright: Strict type checking mode
- Pytest: Auto async mode, integration test markers

---

### 2. Infrastructure Files

#### Docker Compose (`docker-compose.yml`)

PostgreSQL 16 with pgvector extension for vector similarity search:

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: forecastlab-postgres
    environment:
      POSTGRES_USER: forecastlab
      POSTGRES_PASSWORD: forecastlab
      POSTGRES_DB: forecastlab
    ports:
      - "5432:5432"
    volumes:
      - forecastlab_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U forecastlab -d forecastlab"]
```

**Key Features**:
- Health checks for container orchestration
- Persistent volume for data durability
- pgvector for future RAG knowledge base

#### Environment Template (`.env.example`)

```bash
DATABASE_URL=postgresql+asyncpg://forecastlab:forecastlab@localhost:5432/forecastlab
APP_NAME=ForecastLabAI
APP_ENV=development
DEBUG=true
LOG_LEVEL=INFO
LOG_FORMAT=json
API_HOST=0.0.0.0
API_PORT=8123
VITE_API_BASE_URL=http://localhost:8123
```

---

### 3. Core Infrastructure (`app/core/`)

#### Configuration (`config.py`)

Pydantic Settings v2 with singleton pattern:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ForecastLabAI"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    database_url: str = "postgresql+asyncpg://..."
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    api_host: str = "0.0.0.0"
    api_port: int = 8123

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**Features**:
- Environment variable loading from `.env`
- Type-safe configuration with Literal types
- Cached singleton for performance
- Development/production property helpers

#### Logging (`logging.py`)

Structured JSON logging with request correlation:

```python
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

def add_request_id(
    _logger: structlog.types.WrappedLogger,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    request_id = request_id_ctx.get()
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict
```

**Log Output Format** (JSON):
```json
{
  "event": "http.request_completed",
  "level": "info",
  "timestamp": "2026-01-26T10:30:00.000Z",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "method": "GET",
  "path": "/health",
  "status_code": 200
}
```

**Features**:
- JSON format for production (machine-readable)
- Console format for development (human-readable)
- Request ID injection via context variables
- Log level filtering based on configuration

#### Database (`database.py`)

Async SQLAlchemy 2.0 with session dependency:
- `Base` - DeclarativeBase for models
- `get_engine()` - Async engine with pool_pre_ping
- `get_db()` - FastAPI dependency with auto-commit/rollback

#### Middleware (`middleware.py`)

Request ID correlation: generates UUID if no X-Request-ID header, preserves client-provided IDs, injects into all logs, returns in response header.

#### Exceptions (`exceptions.py`)

Custom hierarchy: `ForecastLabError` base class with `NotFoundError` (404), `ValidationError` (422), `DatabaseError` (500).

**Error Response Format**:
```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Resource not found",
    "details": {"resource_id": "123"},
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

#### Health Check (`health.py`)

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `GET /health` | Liveness | `{"status": "ok"}` |
| `GET /health/ready` | Readiness + DB | `{"status": "ok", "database": "connected"}` |

---

### 4. Shared Utilities (`app/shared/`)

- **TimestampMixin**: `created_at` and `updated_at` with server defaults

**Pagination Types** (`schemas.py`):
```python
class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=1000)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int
```

---

### 5. FastAPI Application (`app/main.py`)

```python
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    logger.info("app.startup_started", app_name=settings.app_name)
    yield
    logger.info("app.shutdown_completed")

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="Portfolio-grade retail demand forecasting system",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    return app
```

**Features**:
- Lifespan context manager for startup/shutdown
- Conditional API docs (development only)
- Middleware and exception handler registration
- Modular router inclusion

---

### 6. Alembic Configuration

Async-compatible migration setup:

```python
# alembic/env.py
async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
```

**Migration Commands**:
```bash
# Create migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1
```

---

### 7. Test Suite

**Test Files**:
| File | Tests | Coverage |
|------|-------|----------|
| `test_config.py` | 5 | Settings defaults, singleton, env loading |
| `test_logging.py` | 3 | Logger creation, context variables |
| `test_health.py` | 3 | Health endpoints, request ID headers |
| `test_middleware.py` | 3 | Request ID generation and propagation |

**Total**: 14 tests, all passing

**Test Fixture** (`conftest.py`):
```python
@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
```

---

### 8. Examples and Scripts

#### Smoke Test (`examples/e2e_smoke.sh`)

Validates:
1. Health check returns status "ok"
2. X-Request-ID header is present
3. Custom request ID is propagated

#### Database Check (`scripts/check_db.py`)

Verifies:
- PostgreSQL connectivity
- Server version
- pgvector extension status

---

## Validation Results

### Ruff (Linting + Formatting)
```
All checks passed!
```

### MyPy (Static Type Checking)
```
Success: no issues found in 20 source files
```

### Pyright (Static Type Checking)
```
0 errors, 0 warnings, 0 informations
```

### Pytest (Unit Tests)
```
14 passed in 0.05s
```

---

## Directory Structure

```
app/
├── __init__.py
├── main.py                 # FastAPI entry point
├── core/
│   ├── __init__.py
│   ├── config.py           # Pydantic Settings
│   ├── database.py         # Async SQLAlchemy
│   ├── exceptions.py       # Custom exceptions
│   ├── health.py           # Health endpoints
│   ├── logging.py          # Structlog setup
│   ├── middleware.py       # Request ID middleware
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_config.py
│       ├── test_health.py
│       ├── test_logging.py
│       └── test_middleware.py
├── shared/
│   ├── __init__.py
│   ├── models.py           # TimestampMixin
│   ├── schemas.py          # Pagination, ErrorResponse
│   └── utils.py            # Pagination helper
└── features/
    └── __init__.py         # Ready for vertical slices

alembic/
├── env.py                  # Async migration runner
├── script.py.mako          # Migration template
└── versions/
    └── .gitkeep

tests/
├── __init__.py
└── conftest.py             # Shared fixtures

examples/
├── e2e_smoke.sh            # End-to-end smoke test
├── seed_demo_data.py       # Data seeding placeholder
└── api/
    └── health.http         # HTTP client examples

scripts/
└── check_db.py             # Database connectivity check
```

---

## File Count Summary

| Category | Files |
|----------|-------|
| Configuration | 3 (pyproject.toml, alembic.ini, .env.example) |
| Infrastructure | 1 (docker-compose.yml) |
| Core Module | 7 (+1 __init__.py) |
| Shared Module | 4 (+1 __init__.py) |
| Entry Point | 2 (main.py, features/__init__.py) |
| Alembic | 3 (+1 .gitkeep) |
| Tests | 6 (+2 conftest.py) |
| Examples/Scripts | 4 |
| Documentation | 1 (README.md) |
| **Total** | **~32 files** |

---

### 9. CI/CD Infrastructure (`.github/workflows/`)

#### Core CI Pipeline (`ci.yml`)

Runs on push/PR to main and dev branches:

| Job | Purpose | Tools |
|-----|---------|-------|
| `lint` | Code quality | ruff check, ruff format |
| `typecheck` | Static analysis | mypy, pyright |
| `test` | Unit/integration tests | pytest with PostgreSQL |
| `migration-check` | Migration integrity | alembic upgrade head |

**Key Features**:
- Concurrency groups to cancel stale runs
- PostgreSQL service container (pgvector:pg16)
- uv package manager with caching
- Python 3.12 environment

#### Schema Validation (`schema-validation.yml`)

Triggers on changes to `alembic/**` or `app/**/models.py`.

**Steps:**
1. Fresh DB migration test (`alembic upgrade head`)
2. Migration chain integrity (single head enforcement)
3. Schema drift detection (`alembic check`)
4. Downgrade/upgrade cycle test
5. Schema report generation

**Purpose**: Catches migration drift and schema issues before merge.

#### Dependency Security Check (`dependency-check.yml`)

Triggers weekly (Sunday 00:00 UTC) or manual dispatch.

**Steps:**
1. Export requirements from uv lock
2. Run pip-audit (JSON + SARIF output)
3. Upload SARIF to GitHub Security tab
4. Upload JSON artifact (90-day retention)
5. Analyze and optionally fail on vulnerabilities

**Features**: SARIF integration, configurable `fail_on_vulnerabilities` toggle, audit trail artifacts.

#### Phase Snapshot (`phase-snapshot.yml`)

Triggers on push to `phase-*` branches.

**Job: validate**
- Run lint, typecheck, test, migrations
- Expose status outputs for downstream job

**Job: create-snapshot**
- Extract phase number from branch name
- Generate `audit-data.json` + `requirements-frozen.txt`
- Create `SNAPSHOT-REPORT.md`
- Upload artifacts (365-day retention)
- Create annotated git tag: `phase-{N}-snapshot-{YYYYMMDD}-{sha}`

**Purpose**: Creates audit snapshots at phase milestones.

#### CD Release (`cd-release.yml`)

Triggers on push to main.

**Job: release-please**
- Parse conventional commits
- Create/update release PR
- Outputs: `release_created`, `tag_name`, `version`

**Job: build-package** (runs if release created)
- Checkout at release tag
- Build Python package (`python -m build`)
- Upload to GitHub Release
- Store as workflow artifact

**Supporting Files**:
| File | Purpose |
|------|---------|
| `release-please-config.json` | Package config (python type, version bumping) |
| `.release-please-manifest.json` | Version tracker (starts at 0.1.0) |

**Conventional Commits → Versions**:
- `fix:` → patch (0.1.0 → 0.1.1)
- `feat:` → minor (0.1.0 → 0.2.0)
- `BREAKING CHANGE:` → major (0.1.0 → 1.0.0)

#### Workflow Diagrams

All workflow diagrams documented in `docs/github/diagrams/`:

| Diagram | Description |
|---------|-------------|
| `cd-release-sequence.md` | Actor interactions during release |
| `cd-release-flow.md` | Release workflow job flow |
| `phase-snapshot-flow.md` | Phase-* branch snapshot flow |
| `schema-validation-flow.md` | Migration/drift check flow |
| `dependency-check-flow.md` | pip-audit scan flow |

---

## Next Phase Preparation

Phase 0 provides the foundation for:

1. **Phase 1 (Data Platform)**: Database models for store, product, calendar, sales
2. **Phase 2 (Ingest)**: Idempotent data loading endpoints
3. **Phase 3 (Feature Engineering)**: Time-safe feature computation
4. **Phase 4 (Forecasting)**: Model zoo implementation
5. **Phase 5 (Backtesting)**: Time-based cross-validation
6. **Phase 6 (Registry)**: Run tracking and artifact storage
7. **Phase 7 (RAG)**: pgvector-based knowledge retrieval
8. **Phase 8 (Dashboard)**: React + shadcn/ui frontend

---

## Lessons Learned

1. **Structlog Configuration**: PrintLoggerFactory requires compatible processors; stdlib processors (add_logger_name) don't work with PrintLogger
2. **Pyright Strictness**: Test files need explicit exclusion in strict mode
3. **Hatch Build**: Requires explicit package declaration for editable installs
4. **MyPy Module Patterns**: Must use fully-qualified patterns (e.g., `tests.*` not `test_*`)

---

## References

- [PRP-0: Project Foundation](../PRPs/PRP-0-project-foundation.md)
- [INITIAL-0: Foundation Requirements](../INITIAL-0.md)
- [Architecture Overview](../ARCHITECTURE.md)
- [Logging Standard](../validation/logging-standard.md)
- [Type Checking Standards](../validation/mypy-standard.md)
