# PRP-0: Project Foundation — ForecastLabAI Core Infrastructure

## Goal

Bootstrap the complete ForecastLabAI project infrastructure from scratch, establishing:
- Python project configuration with all tooling (pyproject.toml, uv)
- Docker Compose for PostgreSQL + pgvector
- FastAPI application skeleton with vertical slice architecture
- Core infrastructure: config, database, logging, middleware, health, exceptions
- Shared utilities: pagination, timestamps, error schemas
- Example files and smoke test scripts

**End State:** A running FastAPI application on port 8123 with:
- Health endpoints (`GET /health`, `GET /health/ready`)
- Structured JSON logging with request correlation
- Async PostgreSQL connection via SQLAlchemy 2.0
- All validation gates passing (ruff, pytest, mypy, pyright)

---

## Why

- **Foundation for all features**: Every INITIAL (1-9) depends on this infrastructure
- **Portfolio-ready**: Professional project setup demonstrates engineering rigor
- **Developer experience**: One-command local dev (`docker-compose up -d && uv run uvicorn ...`)
- **AI-optimized**: Consistent structure reduces hallucinations in future PRPs

---

## What

### Success Criteria

- [ ] `docker-compose up -d` starts PostgreSQL with pgvector extension
- [ ] `uv run uvicorn app.main:app --reload --port 8123` starts the API
- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] `GET /health/ready` returns database connectivity status
- [ ] All responses include `X-Request-ID` header
- [ ] Logs are JSON-formatted with request correlation
- [ ] `uv run pytest -v` passes with at least 5 tests
- [ ] `uv run ruff check . && uv run ruff format --check .` passes
- [ ] `uv run mypy app/` passes with zero errors
- [ ] `uv run pyright app/` passes with zero errors
- [ ] `examples/e2e_smoke.sh` completes successfully

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ - Include these in your context window
- url: https://docs.astral.sh/uv/
  why: uv package manager - project setup, dependency management, virtual env

- url: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
  why: Pydantic Settings v2 for environment configuration
  critical: Use model_config with env_file, NOT class Config

- url: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
  why: Async SQLAlchemy 2.0 patterns
  critical: Use select() style, NOT legacy Query API

- url: https://www.structlog.org/en/stable/getting-started.html
  why: Structured logging setup
  critical: Configure processors for JSON output + request_id binding

- url: https://fastapi.tiangolo.com/tutorial/dependencies/
  why: FastAPI dependency injection for database sessions
  critical: Use Depends() with async generators

- url: https://github.com/pgvector/pgvector-docker
  why: pgvector Docker image for local development

- docfile: docs/validation/logging-standard.md
  why: Event naming taxonomy (domain.component.action_state)

- docfile: docs/validation/ruff-standard.md
  why: Ruff configuration for pyproject.toml

- docfile: docs/validation/mypy-standard.md
  why: MyPy strict configuration

- docfile: docs/validation/pyright-standard.md
  why: Pyright strict configuration

- docfile: docs/validation/pytest-standard.md
  why: Pytest configuration with asyncio_mode="auto"

- docfile: CLAUDE.md
  why: All project conventions, type safety requirements, logging patterns
```

### Current Codebase Tree

```bash
w7-ForecastLabAI/
├── .claude/                    # Claude Code configuration (exists)
├── .devcontainer/              # Dev container (exists)
├── .github/                    # CI/CD (exists)
├── .vscode/                    # Editor settings (exists)
├── docs/
│   ├── ADR/                    # Architecture decisions (exists)
│   ├── github/                 # GitHub docs (exists)
│   └── validation/             # Quality standards (exists)
├── PRPs/
│   └── templates/              # PRP templates (exists)
├── CLAUDE.md                   # AI guidance (exists)
├── INITIAL-*.md                # Feature specs (exists)
└── .gitignore                  # (exists)
```

### Desired Codebase Tree (files to be created)

```bash
w7-ForecastLabAI/
├── app/                        # FastAPI backend (NEW)
│   ├── __init__.py
│   ├── main.py                 # FastAPI entry point
│   ├── core/                   # Core infrastructure
│   │   ├── __init__.py
│   │   ├── config.py           # Pydantic Settings
│   │   ├── database.py         # Async SQLAlchemy setup
│   │   ├── logging.py          # Structlog configuration
│   │   ├── middleware.py       # Request ID middleware
│   │   ├── health.py           # Health check router
│   │   └── exceptions.py       # Custom exceptions + handlers
│   ├── shared/                 # Shared utilities
│   │   ├── __init__.py
│   │   ├── models.py           # TimestampMixin
│   │   ├── schemas.py          # Pagination, error schemas
│   │   └── utils.py            # Common utilities
│   └── features/               # Vertical slices (empty for now)
│       └── __init__.py
├── tests/                      # Global test fixtures (NEW)
│   ├── __init__.py
│   └── conftest.py             # Shared fixtures
├── alembic/                    # Migrations (NEW)
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── .gitkeep
├── examples/                   # Runnable examples (NEW)
│   ├── seed_demo_data.py       # Placeholder for synthetic data
│   ├── e2e_smoke.sh            # End-to-end smoke test
│   └── api/
│       └── health.http         # HTTP client examples
├── scripts/                    # Utility scripts (NEW)
│   └── check_db.py             # Database connectivity check
├── docker-compose.yml          # PostgreSQL + pgvector (NEW)
├── pyproject.toml              # Project configuration (NEW)
├── alembic.ini                 # Alembic configuration (NEW)
├── .env.example                # Environment template (NEW)
└── README.md                   # Project README (NEW)
```

### Known Gotchas & Library Quirks

```python
# CRITICAL: Pydantic v2 Settings syntax
# ❌ OLD (v1): class Config: env_file = ".env"
# ✅ NEW (v2): model_config = SettingsConfigDict(env_file=".env")

# CRITICAL: SQLAlchemy 2.0 async session
# ❌ OLD: session.query(Model).filter(...)
# ✅ NEW: await session.execute(select(Model).where(...))

# CRITICAL: FastAPI Depends with async generators
# ✅ CORRECT:
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session

# CRITICAL: structlog JSON logging requires explicit processor chain
# The order matters: add_log_level BEFORE JSONRenderer

# CRITICAL: pytest-asyncio mode must be "auto" for proper event loop handling
# ❌ WRONG: asyncio_mode = "strict" (creates issues with fixtures)
# ✅ CORRECT: asyncio_mode = "auto"

# CRITICAL: pgvector extension must be created BEFORE any vector columns
# Run: CREATE EXTENSION IF NOT EXISTS vector;

# CRITICAL: FastAPI middleware order matters
# Add RequestIDMiddleware BEFORE any logging middleware
```

---

## Implementation Blueprint

### Data Models and Structure

#### Pydantic Settings (app/core/config.py)

```python
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "ForecastLabAI"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    # Database
    database_url: PostgresDsn
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "console"
```

#### SQLAlchemy Base (app/core/database.py)

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass

# Engine and session factory setup
# get_db() dependency for FastAPI
```

#### Shared Schemas (app/shared/schemas.py)

```python
from pydantic import BaseModel

class ErrorResponse(BaseModel):
    """Standard error response schema."""
    detail: str
    error_type: str
    request_id: str | None = None

class PaginationParams(BaseModel):
    """Pagination query parameters."""
    offset: int = 0
    limit: int = 100

class PaginatedResponse[T](BaseModel):
    """Generic paginated response."""
    items: list[T]
    total: int
    offset: int
    limit: int
```

#### Timestamp Mixin (app/shared/models.py)

```python
from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

class TimestampMixin:
    """Mixin adding created_at and updated_at columns."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
```

---

## Tasks (Ordered Implementation)

### Task 1: Create pyproject.toml with all dependencies and tool configuration

**File:** `pyproject.toml`

**Dependencies:**
- Runtime: fastapi, uvicorn, pydantic, pydantic-settings, sqlalchemy[asyncio], asyncpg, structlog, alembic, python-dotenv
- Dev: pytest, pytest-asyncio, pytest-cov, httpx, ruff, mypy, pyright

**Tool Config Sections:**
- `[tool.ruff]` - Per docs/validation/ruff-standard.md
- `[tool.mypy]` - Per docs/validation/mypy-standard.md
- `[tool.pyright]` - Per docs/validation/pyright-standard.md
- `[tool.pytest.ini_options]` - Per docs/validation/pytest-standard.md

```bash
# Validation
uv sync
uv run ruff check .
```

---

### Task 2: Create docker-compose.yml for PostgreSQL + pgvector

**File:** `docker-compose.yml`

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: forecastlab
      POSTGRES_PASSWORD: forecastlab
      POSTGRES_DB: forecastlab
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U forecastlab"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

```bash
# Validation
docker-compose up -d
docker-compose exec db psql -U forecastlab -c "CREATE EXTENSION IF NOT EXISTS vector;"
docker-compose down
```

---

### Task 3: Create .env.example with all required environment variables

**File:** `.env.example`

```bash
# Application
APP_NAME=ForecastLabAI
APP_VERSION=0.1.0
ENVIRONMENT=development
DEBUG=true

# Database
DATABASE_URL=postgresql+asyncpg://forecastlab:forecastlab@localhost:5432/forecastlab
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

---

### Task 4: Create app/core/config.py - Pydantic Settings

**File:** `app/core/config.py`

Implement Settings class with:
- All environment variables from .env.example
- Type hints for all fields
- Singleton pattern via `@lru_cache`

```python
from functools import lru_cache

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```bash
# Validation
uv run python -c "from app.core.config import get_settings; print(get_settings())"
```

---

### Task 5: Create app/core/logging.py - Structlog JSON logging

**File:** `app/core/logging.py`

Implement:
- Configure structlog with JSON processor chain
- Request ID binding via contextvars
- get_logger() function
- Console vs JSON format based on settings

Follow logging-standard.md for event naming.

```python
import structlog
from contextvars import ContextVar

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

def configure_logging(log_level: str, log_format: str) -> None:
    """Configure structlog for the application."""
    # Processor chain setup
    pass

def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a logger instance with request_id binding."""
    pass
```

```bash
# Validation
uv run python -c "from app.core.logging import get_logger; log = get_logger('test'); log.info('test.event_completed')"
```

---

### Task 6: Create app/core/database.py - Async SQLAlchemy setup

**File:** `app/core/database.py`

Implement:
- `Base` (DeclarativeBase)
- `create_db_engine()` function
- `async_session_maker` factory
- `get_db()` async generator dependency
- `init_db()` for creating tables (dev only)

```python
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
```

---

### Task 7: Create app/core/middleware.py - Request ID middleware

**File:** `app/core/middleware.py`

Implement:
- `RequestIDMiddleware` class
- Generate UUID4 for each request
- Set `X-Request-ID` response header
- Bind to logging context

```python
from starlette.middleware.base import BaseHTTPMiddleware
import uuid

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        # Bind to context, call next, add response header
        pass
```

---

### Task 8: Create app/core/exceptions.py - Custom exceptions and handlers

**File:** `app/core/exceptions.py`

Implement:
- `AppException` base class
- `NotFoundError`, `ValidationError`, `DatabaseError`
- FastAPI exception handlers
- Consistent error response format

```python
from fastapi import Request
from fastapi.responses import JSONResponse

class AppException(Exception):
    def __init__(self, detail: str, status_code: int = 500):
        self.detail = detail
        self.status_code = status_code

async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    # Return ErrorResponse schema
    pass
```

---

### Task 9: Create app/core/health.py - Health check router

**File:** `app/core/health.py`

Implement:
- `GET /health` - Basic liveness check
- `GET /health/ready` - Readiness check with DB connectivity
- Response models with proper typing

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

router = APIRouter(prefix="/health", tags=["health"])

@router.get("")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    # Check database connectivity
    pass
```

---

### Task 10: Create app/shared/models.py - TimestampMixin

**File:** `app/shared/models.py`

Implement `TimestampMixin` as shown in blueprint above.

---

### Task 11: Create app/shared/schemas.py - Shared Pydantic schemas

**File:** `app/shared/schemas.py`

Implement:
- `ErrorResponse`
- `PaginationParams`
- `PaginatedResponse[T]` (generic)

---

### Task 12: Create app/main.py - FastAPI application entry point

**File:** `app/main.py`

Implement:
- Create FastAPI app with metadata
- Configure logging on startup
- Add middleware (RequestIDMiddleware)
- Register exception handlers
- Include health router
- Lifespan for startup/shutdown

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: configure logging, log startup
    configure_logging(...)
    logger.info("application.lifecycle.started", ...)
    yield
    # Shutdown: log shutdown
    logger.info("application.lifecycle.stopped", ...)

app = FastAPI(
    title="ForecastLabAI",
    version="0.1.0",
    lifespan=lifespan,
)
```

---

### Task 13: Create alembic.ini and alembic/env.py for migrations

**Files:** `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/.gitkeep`

Configure Alembic for async SQLAlchemy:
- Use `run_async` in env.py
- Import Base from app.core.database
- Set sqlalchemy.url from Settings

```bash
# Validation
uv run alembic current
```

---

### Task 14: Create tests/conftest.py with shared fixtures

**File:** `tests/conftest.py`

Implement fixtures:
- `settings` - Test settings
- `app` - FastAPI TestClient
- `async_client` - httpx AsyncClient

```python
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from app.main import app as fastapi_app

@pytest.fixture
def app():
    return TestClient(fastapi_app)

@pytest.fixture
async def async_client():
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test"
    ) as client:
        yield client
```

---

### Task 15: Create app/core/tests/ with unit tests

**Files:**
- `app/core/tests/__init__.py`
- `app/core/tests/test_health.py`
- `app/core/tests/test_config.py`
- `app/core/tests/test_logging.py`
- `app/core/tests/test_middleware.py`

Minimum tests:
- Health endpoint returns 200
- Config loads from environment
- Logging produces JSON output
- Middleware adds request_id header

```bash
# Validation
uv run pytest app/core/tests/ -v
```

---

### Task 16: Create examples/e2e_smoke.sh - End-to-end smoke test

**File:** `examples/e2e_smoke.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "Starting PostgreSQL..."
docker-compose up -d

echo "Waiting for database..."
sleep 5

echo "Running migrations..."
uv run alembic upgrade head

echo "Starting API in background..."
uv run uvicorn app.main:app --port 8123 &
API_PID=$!
sleep 3

echo "Testing health endpoint..."
curl -f http://localhost:8123/health

echo "Testing readiness endpoint..."
curl -f http://localhost:8123/health/ready

echo "Stopping API..."
kill $API_PID

echo "Stopping PostgreSQL..."
docker-compose down

echo "Smoke test passed!"
```

---

### Task 17: Create examples/api/health.http - HTTP client examples

**File:** `examples/api/health.http`

```http
### Health Check
GET {{API_BASE_URL}}/health

### Readiness Check
GET {{API_BASE_URL}}/health/ready
```

---

### Task 18: Create examples/seed_demo_data.py placeholder

**File:** `examples/seed_demo_data.py`

```python
"""
Synthetic multi-store dataset generation.

This is a placeholder - implementation will come with INITIAL-2 (Data Platform).

Usage:
    uv run python examples/seed_demo_data.py

Configuration:
    - Number of stores
    - Number of products
    - Date range
    - Random seed
"""

def main() -> None:
    print("Seed data generation not yet implemented.")
    print("See INITIAL-2.md for data platform specification.")

if __name__ == "__main__":
    main()
```

---

### Task 19: Create scripts/check_db.py - Database connectivity check

**File:** `scripts/check_db.py`

```python
"""Check database connectivity."""
import asyncio
from sqlalchemy import text
from app.core.database import async_session_maker
from app.core.config import get_settings

async def main() -> None:
    settings = get_settings()
    print(f"Checking database: {settings.database_url}")

    async with async_session_maker() as session:
        result = await session.execute(text("SELECT 1"))
        print(f"Database connection successful: {result.scalar()}")

        # Check pgvector extension
        result = await session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        if result.scalar():
            print("pgvector extension: installed")
        else:
            print("pgvector extension: NOT installed")

if __name__ == "__main__":
    asyncio.run(main())
```

---

### Task 20: Create README.md with project documentation

**File:** `README.md`

Include:
- Project overview
- Quick start guide
- Development setup
- Available commands
- Project structure
- Links to docs

---

### Task 21: Final validation - Run all quality gates

```bash
# Format and lint
uv run ruff check . --fix
uv run ruff format .

# Type checking
uv run mypy app/
uv run pyright app/

# Tests
uv run pytest -v

# Integration test (requires Docker)
docker-compose up -d
sleep 5
uv run pytest -v -m integration
docker-compose down
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run FIRST - fix any errors before proceeding
uv run ruff check . --fix
uv run ruff format .

# Expected: No errors
```

### Level 2: Type Checking

```bash
# Run SECOND - type safety is non-negotiable
uv run mypy app/
uv run pyright app/

# Expected: 0 errors, 0 warnings
```

### Level 3: Unit Tests

```bash
# Run THIRD - verify functionality
uv run pytest app/core/tests/ -v

# Expected: All tests pass
```

### Level 4: Integration Test

```bash
# Run FOURTH - full system test
docker-compose up -d
sleep 5
curl -f http://localhost:8123/health
curl -f http://localhost:8123/health/ready
docker-compose down

# Expected: Both endpoints return 200
```

---

## Final Validation Checklist

- [ ] `uv sync` completes without errors
- [ ] `docker-compose up -d` starts PostgreSQL with pgvector
- [ ] `uv run uvicorn app.main:app --port 8123` starts without errors
- [ ] `curl http://localhost:8123/health` returns `{"status": "ok"}`
- [ ] `curl -I http://localhost:8123/health` includes `X-Request-ID` header
- [ ] `uv run ruff check .` passes with no errors
- [ ] `uv run ruff format --check .` passes
- [ ] `uv run mypy app/` passes with 0 errors
- [ ] `uv run pyright app/` passes with 0 errors
- [ ] `uv run pytest -v` passes with 5+ tests
- [ ] `examples/e2e_smoke.sh` completes successfully
- [ ] All `__init__.py` files export appropriate symbols
- [ ] All files have proper type annotations
- [ ] Logs are JSON formatted with event names following taxonomy

---

## Anti-Patterns to Avoid

- **Don't** use `from typing import Optional` - use `X | None` (Python 3.10+)
- **Don't** use `class Config` in Pydantic models - use `model_config`
- **Don't** use sync SQLAlchemy - only async with `select()`
- **Don't** hardcode URLs, ports, or credentials - use Settings
- **Don't** use `# type: ignore` without documenting why
- **Don't** create empty `pass` functions - implement or raise NotImplementedError
- **Don't** use print() for logging - use structlog
- **Don't** skip tests for "simple" code - test everything

---

## Confidence Score: 8/10

**Rationale:**
- (+) Comprehensive documentation references provided
- (+) Clear task decomposition with validation steps
- (+) All gotchas explicitly documented
- (+) Quality gates are executable
- (-) First-time project setup has inherent complexity
- (-) Database connectivity issues may require debugging
- (-) Some library version quirks may surface

**Recommended Approach:**
1. Execute tasks 1-3 first (pyproject.toml, docker-compose, .env.example)
2. Validate environment before proceeding
3. Execute tasks 4-12 (core infrastructure)
4. Run all type checkers after each file
5. Execute tasks 13-19 (tests, examples)
6. Final validation with e2e_smoke.sh

---

## Version

- **PRP Version:** 1.0
- **Target INITIAL:** INITIAL-0.md
- **Created:** 2026-01-26
- **Author:** Claude Code
