# PRP-7: Model Registry + Artifacts + Reproducibility

## Goal

Implement a Model Registry feature that provides comprehensive run tracking, artifact management, and reproducibility guarantees for the ForecastOps platform. The registry captures full experiment lineage including configurations, metrics, data windows, and artifact integrity verification.

**End State:** A production-ready `registry` vertical slice with:
- `ModelRun` database table with JSONB columns for flexible metadata storage
- `DeploymentAlias` table for mutable pointers (e.g., 'prod-v1') to successful runs
- Lifecycle state machine: PENDING | RUNNING | SUCCESS | FAILED | ARCHIVED
- SHA-256 checksum verification for artifact integrity
- Runtime environment snapshots (Python/library versions)
- Agent context tracking (agent_id, session_id) for autonomous run traceability
- Abstract storage provider interface (LocalFS default, future S3/GCS)
- RESTful API: create, list, get, update runs; manage aliases; compare runs
- All validation gates passing (ruff, mypy, pyright, pytest)

---

## Why

- **Reproducibility**: Every training run must be exactly reproducible via stored configs, data windows, and environment snapshots
- **Auditability**: Full lineage from data → features → model → predictions with agent context for autonomous workflows
- **Artifact Integrity**: SHA-256 checksums prevent corrupted or tampered model artifacts from being deployed
- **Deployment Safety**: Aliases provide stable references (e.g., 'production') that can be updated atomically
- **Leaderboard/Comparison**: Metrics storage enables model comparison and performance tracking over time
- **ForecastOps Integration**: Registry integrates with existing forecasting/backtesting modules for end-to-end workflows

---

## What

### User-Visible Behavior

1. **Create Run**: Start a new model run with PENDING state, capture configs
2. **Update Run**: Transition states (RUNNING → SUCCESS/FAILED), attach metrics and artifact metadata
3. **List Runs**: Query runs with filtering by model_type, status, date range
4. **Get Run**: Retrieve full run details including configs, metrics, lineage
5. **Compare Runs**: Side-by-side comparison of two runs (configs + metrics diff)
6. **Manage Aliases**: Create/update deployment aliases pointing to successful runs
7. **Artifact Verification**: Validate artifact integrity via stored checksum

### Success Criteria

- [ ] ModelRun table created with JSONB columns for model_config, feature_config, metrics
- [ ] DeploymentAlias table created with unique constraint on (alias_name)
- [ ] Run lifecycle state machine enforced (valid transitions only)
- [ ] SHA-256 checksum computed and verified for all artifacts
- [ ] Python/library version snapshots stored per run
- [ ] Agent context (agent_id, session_id) stored for traceability
- [ ] AbstractStorageProvider interface with LocalFSProvider implementation
- [ ] 60+ unit tests covering models, schemas, service, storage, routes
- [ ] 10+ integration tests for database operations
- [ ] Example files demonstrating registry workflows

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ - Include these in your context window

# SQLAlchemy JSONB with PostgreSQL
- url: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html
  why: "Official JSONB type usage, Mapped[] annotations"
  critical: "Use JSONB from sqlalchemy.dialects.postgresql, not JSON"

# JSONB Indexing Best Practices
- url: https://www.crunchydata.com/blog/indexing-jsonb-in-postgres
  why: "GIN index patterns for JSONB columns"
  critical: "Use @> containment operator for indexed queries"

# JSONB Storage Patterns
- url: https://scalegrid.io/blog/using-jsonb-in-postgresql-how-to-effectively-store-index-json-data-in-postgresql/
  why: "Referenced in INITIAL-7.md for JSONB patterns"
  critical: "JSONB stores binary format, faster queries than JSON"

# MLflow Model Registry Design
- url: https://mlflow.org/docs/latest/ml/model-registry/
  why: "Industry-standard registry design patterns"
  critical: "Separate metadata store from artifact store"

# Internal Codebase References
- file: app/features/forecasting/persistence.py
  why: "Existing ModelBundle with hash computation, version recording"
  pattern: "compute_hash(), save_model_bundle(), load_model_bundle()"

- file: app/features/forecasting/schemas.py
  why: "Pattern for ModelConfig with config_hash(), frozen=True"

- file: app/features/backtesting/schemas.py
  why: "Pattern for complex nested configs, schema_version field"

- file: app/features/backtesting/service.py
  why: "Pattern for service orchestration with async DB operations"

- file: app/features/data_platform/models.py
  why: "Pattern for SQLAlchemy 2.0 Mapped[] models with TimestampMixin"

- file: app/core/config.py
  why: "Pattern for Settings with environment variables"

- file: alembic/versions/e1165ebcef61_create_data_platform_tables.py
  why: "Pattern for Alembic migrations"
```

### Current Codebase Tree (Relevant Parts)

```text
app/
├── core/
│   ├── config.py           # Settings singleton
│   ├── database.py         # Base, AsyncSession, get_db
│   ├── exceptions.py       # ForecastLabError hierarchy
│   └── logging.py          # Structured logging
├── shared/
│   └── models.py           # TimestampMixin
├── features/
│   ├── data_platform/
│   │   └── models.py       # SalesDaily, Store, Product, Calendar
│   ├── forecasting/
│   │   ├── models.py       # BaseForecaster, model_factory
│   │   ├── persistence.py  # ModelBundle, save/load (HAS HASH!)
│   │   ├── schemas.py      # ModelConfig, config_hash()
│   │   └── service.py      # ForecastingService
│   └── backtesting/
│       ├── schemas.py      # BacktestConfig, SplitConfig
│       └── service.py      # BacktestingService
└── main.py                 # FastAPI app with router registration
```

### Desired Codebase Tree

```text
app/features/registry/                    # NEW: Registry vertical slice
├── __init__.py                           # Module exports
├── models.py                             # ModelRun, DeploymentAlias ORM models
├── schemas.py                            # RunConfig, RunCreate, RunResponse, AliasResponse, etc.
├── storage.py                            # AbstractStorageProvider, LocalFSProvider
├── service.py                            # RegistryService (orchestration)
├── routes.py                             # CRUD routes + alias management + compare
└── tests/
    ├── __init__.py
    ├── conftest.py                       # Fixtures: sample runs, configs
    ├── test_models.py                    # ORM model tests
    ├── test_schemas.py                   # Schema validation, immutability
    ├── test_storage.py                   # Storage provider tests
    ├── test_service.py                   # Service orchestration tests
    ├── test_service_integration.py       # Integration tests with DB
    └── test_routes_integration.py        # Route integration tests

examples/registry/                        # NEW: Example scripts
├── create_run.py                         # Create run record + persist configs
├── list_runs.py                          # Leaderboard preview
└── compare_runs.py                       # Compare two runs (metrics + configs)

app/core/config.py                        # MODIFY: Add registry settings
app/main.py                               # MODIFY: Register registry router
alembic/versions/xxx_create_registry_tables.py  # NEW: Migration
```

### Known Gotchas

```python
# CRITICAL: SQLAlchemy JSONB requires PostgreSQL dialect import
from sqlalchemy.dialects.postgresql import JSONB
# NOT: from sqlalchemy import JSON (different type!)

# CRITICAL: JSONB columns should use Mapped[dict[str, Any]] for typing
# SQLAlchemy 2.0 uses Mapped[] annotations
model_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

# CRITICAL: For async queries with JSONB containment (@>), use:
from sqlalchemy.dialects.postgresql import JSONB
stmt = select(ModelRun).where(ModelRun.model_config.contains({"model_type": "naive"}))

# CRITICAL: GIN index on JSONB for efficient containment queries
# Add in migration: op.create_index('ix_model_run_model_config_gin', 'model_run', ['model_config'], postgresql_using='gin')

# CRITICAL: State transitions must be validated
# PENDING -> RUNNING -> SUCCESS|FAILED
# PENDING|RUNNING|SUCCESS|FAILED -> ARCHIVED
# No other transitions allowed

# CRITICAL: Checksum verification before loading artifacts
# 1. Load stored checksum from DB
# 2. Compute checksum of artifact file
# 3. Compare - raise if mismatch

# CRITICAL: artifact_uri is relative to REGISTRY_ARTIFACT_ROOT setting
# Never store absolute paths in DB - allows migration between environments

# CRITICAL: Duplicate run detection uses config_hash + data_window_hash
# Policy is Settings-driven: allow/deny/detect

# CRITICAL: Alias can only point to SUCCESS runs
# Attempting to alias a FAILED/ARCHIVED run should raise ValueError

# CRITICAL: When comparing runs, use model_dump() for Pydantic serialization
# This handles nested objects and dates correctly

# CRITICAL: We use Pydantic v2 - ConfigDict not Config class
model_config = ConfigDict(frozen=True, extra="forbid")
```

---

## Implementation Blueprint

### Data Models (ORM)

```python
# app/features/registry/models.py

from __future__ import annotations

import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.models import TimestampMixin


class RunStatus(str, Enum):
    """Valid states for a model run."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ARCHIVED = "archived"


class ModelRun(TimestampMixin, Base):
    """Model run registry entry.

    CRITICAL: Captures full experiment lineage for reproducibility.

    Attributes:
        id: Primary key.
        run_id: Unique external identifier (UUID hex).
        status: Current lifecycle state.
        model_type: Type of model (naive, seasonal_naive, etc.).
        model_config: Full model configuration as JSONB.
        feature_config: Feature engineering config as JSONB (nullable).
        data_window_start: Training data start date.
        data_window_end: Training data end date.
        store_id: Store ID for this run.
        product_id: Product ID for this run.
        metrics: Performance metrics as JSONB.
        artifact_uri: Relative path to artifact (from ARTIFACT_ROOT).
        artifact_hash: SHA-256 checksum of artifact.
        artifact_size_bytes: Size of artifact file.
        runtime_info: Python/library versions as JSONB.
        agent_context: Agent ID and session ID for traceability.
        git_sha: Optional git commit hash.
        config_hash: Hash of model_config for deduplication.
        error_message: Error details if status=FAILED.
        started_at: When run started.
        completed_at: When run completed (success or failed).
    """

    __tablename__ = "model_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default=RunStatus.PENDING.value, index=True)

    # Model configuration
    model_type: Mapped[str] = mapped_column(String(50), index=True)
    model_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    feature_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    config_hash: Mapped[str] = mapped_column(String(16), index=True)

    # Data window
    data_window_start: Mapped[datetime.date] = mapped_column()
    data_window_end: Mapped[datetime.date] = mapped_column()
    store_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)

    # Metrics
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Artifact info
    artifact_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    artifact_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # SHA-256
    artifact_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Environment & lineage
    runtime_info: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    agent_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    git_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # Timing
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship to aliases
    aliases: Mapped[list[DeploymentAlias]] = relationship(back_populates="run")

    __table_args__ = (
        # GIN index for JSONB containment queries
        Index("ix_model_run_model_config_gin", "model_config", postgresql_using="gin"),
        Index("ix_model_run_metrics_gin", "metrics", postgresql_using="gin"),
        # Composite index for common query pattern
        Index("ix_model_run_store_product", "store_id", "product_id"),
        Index("ix_model_run_data_window", "data_window_start", "data_window_end"),
        # Constraint: valid status values
        CheckConstraint(
            "status IN ('pending', 'running', 'success', 'failed', 'archived')",
            name="ck_model_run_valid_status",
        ),
        # Constraint: data window validity
        CheckConstraint(
            "data_window_end >= data_window_start",
            name="ck_model_run_valid_data_window",
        ),
    )


class DeploymentAlias(TimestampMixin, Base):
    """Mutable pointer to a specific successful run.

    CRITICAL: Aliases provide stable references for deployment.

    Attributes:
        id: Primary key.
        alias_name: Unique alias name (e.g., 'production', 'staging-v2').
        run_id: Foreign key to the aliased run.
        description: Optional description of this alias.
    """

    __tablename__ = "deployment_alias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alias_name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("model_run.id"), index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationship
    run: Mapped[ModelRun] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("alias_name", name="uq_deployment_alias_name"),
    )
```

### Pydantic Schemas

```python
# app/features/registry/schemas.py

from __future__ import annotations

import hashlib
from datetime import date as date_type, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RunStatus(str, Enum):
    """Run lifecycle states."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ARCHIVED = "archived"


# Valid state transitions
VALID_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.PENDING: {RunStatus.RUNNING, RunStatus.ARCHIVED},
    RunStatus.RUNNING: {RunStatus.SUCCESS, RunStatus.FAILED, RunStatus.ARCHIVED},
    RunStatus.SUCCESS: {RunStatus.ARCHIVED},
    RunStatus.FAILED: {RunStatus.ARCHIVED},
    RunStatus.ARCHIVED: set(),  # Terminal state
}


class RuntimeInfo(BaseModel):
    """Runtime environment snapshot."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    python_version: str
    sklearn_version: str | None = None
    numpy_version: str | None = None
    pandas_version: str | None = None
    joblib_version: str | None = None


class AgentContext(BaseModel):
    """Agent context for autonomous run traceability."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str | None = None
    session_id: str | None = None


class RunCreate(BaseModel):
    """Request to create a new run."""
    model_config = ConfigDict(extra="forbid")

    model_type: str = Field(..., min_length=1, max_length=50)
    model_config_data: dict[str, Any] = Field(..., alias="model_config")
    feature_config: dict[str, Any] | None = None
    data_window_start: date_type
    data_window_end: date_type
    store_id: int = Field(..., ge=1)
    product_id: int = Field(..., ge=1)
    agent_context: AgentContext | None = None
    git_sha: str | None = Field(None, max_length=40)

    @field_validator("data_window_end")
    @classmethod
    def validate_data_window(cls, v: date_type, info: object) -> date_type:
        """Ensure data_window_end >= data_window_start."""
        data = getattr(info, "data", {})
        if "data_window_start" in data and v < data["data_window_start"]:
            raise ValueError("data_window_end must be >= data_window_start")
        return v


class RunUpdate(BaseModel):
    """Request to update a run."""
    model_config = ConfigDict(extra="forbid")

    status: RunStatus | None = None
    metrics: dict[str, Any] | None = None
    artifact_uri: str | None = None
    artifact_hash: str | None = None
    artifact_size_bytes: int | None = Field(None, ge=0)
    error_message: str | None = Field(None, max_length=2000)


class RunResponse(BaseModel):
    """Run details response."""
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    status: RunStatus
    model_type: str
    model_config_data: dict[str, Any] = Field(..., alias="model_config")
    feature_config: dict[str, Any] | None = None
    config_hash: str
    data_window_start: date_type
    data_window_end: date_type
    store_id: int
    product_id: int
    metrics: dict[str, Any] | None = None
    artifact_uri: str | None = None
    artifact_hash: str | None = None
    artifact_size_bytes: int | None = None
    runtime_info: dict[str, Any] | None = None
    agent_context: dict[str, Any] | None = None
    git_sha: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RunListResponse(BaseModel):
    """Paginated list of runs."""
    runs: list[RunResponse]
    total: int
    page: int
    page_size: int


class AliasCreate(BaseModel):
    """Request to create/update an alias."""
    model_config = ConfigDict(extra="forbid")

    alias_name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-_]*$")
    run_id: str
    description: str | None = Field(None, max_length=500)


class AliasResponse(BaseModel):
    """Alias details response."""
    model_config = ConfigDict(from_attributes=True)

    alias_name: str
    run_id: str
    run_status: RunStatus
    model_type: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class RunCompareResponse(BaseModel):
    """Comparison of two runs."""
    run_a: RunResponse
    run_b: RunResponse
    config_diff: dict[str, Any]  # Keys that differ
    metrics_diff: dict[str, dict[str, float | None]]  # {metric: {a: val, b: val, diff: val}}
```

### Storage Provider (Abstract)

```python
# app/features/registry/storage.py

from __future__ import annotations

import hashlib
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

import structlog

from app.core.config import get_settings

logger = structlog.get_logger()


class StorageError(Exception):
    """Base exception for storage operations."""
    pass


class ArtifactNotFoundError(StorageError):
    """Artifact not found at specified URI."""
    pass


class ChecksumMismatchError(StorageError):
    """Artifact checksum does not match stored value."""
    pass


class AbstractStorageProvider(ABC):
    """Abstract base class for artifact storage.

    CRITICAL: All storage providers must implement these methods.
    This allows future S3/GCS implementations.
    """

    @abstractmethod
    def save(self, source_path: Path, artifact_uri: str) -> tuple[str, int]:
        """Save an artifact to storage.

        Args:
            source_path: Local path to artifact file.
            artifact_uri: Relative URI for storage.

        Returns:
            Tuple of (sha256_hash, size_bytes).

        Raises:
            StorageError: If save fails.
        """
        pass

    @abstractmethod
    def load(self, artifact_uri: str, expected_hash: str | None = None) -> Path:
        """Load an artifact from storage.

        Args:
            artifact_uri: Relative URI of artifact.
            expected_hash: If provided, verify checksum.

        Returns:
            Path to artifact (may be temp file for remote storage).

        Raises:
            ArtifactNotFoundError: If artifact doesn't exist.
            ChecksumMismatchError: If hash verification fails.
        """
        pass

    @abstractmethod
    def delete(self, artifact_uri: str) -> bool:
        """Delete an artifact from storage.

        Args:
            artifact_uri: Relative URI of artifact.

        Returns:
            True if deleted, False if not found.
        """
        pass

    @abstractmethod
    def exists(self, artifact_uri: str) -> bool:
        """Check if an artifact exists.

        Args:
            artifact_uri: Relative URI of artifact.

        Returns:
            True if exists, False otherwise.
        """
        pass

    @staticmethod
    def compute_hash(file_path: Path) -> str:
        """Compute SHA-256 hash of a file.

        Args:
            file_path: Path to file.

        Returns:
            Hexadecimal SHA-256 hash.
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()


class LocalFSProvider(AbstractStorageProvider):
    """Local filesystem storage provider.

    CRITICAL: Default provider for development and single-node deployments.
    """

    def __init__(self, root_dir: Path | None = None) -> None:
        """Initialize with root directory.

        Args:
            root_dir: Root directory for artifacts. Defaults to Settings value.
        """
        if root_dir is None:
            settings = get_settings()
            root_dir = Path(settings.registry_artifact_root)
        self.root_dir = root_dir.resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, artifact_uri: str) -> Path:
        """Resolve artifact URI to full path.

        CRITICAL: Validates path is within root to prevent traversal.
        """
        full_path = (self.root_dir / artifact_uri).resolve()
        # Security: ensure path is within root
        try:
            full_path.relative_to(self.root_dir)
        except ValueError:
            raise StorageError(f"Path traversal attempt: {artifact_uri}") from None
        return full_path

    def save(self, source_path: Path, artifact_uri: str) -> tuple[str, int]:
        """Save artifact to local filesystem."""
        dest_path = self._resolve_path(artifact_uri)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Compute hash before copy
        file_hash = self.compute_hash(source_path)
        file_size = source_path.stat().st_size

        # Copy file
        shutil.copy2(source_path, dest_path)

        logger.info(
            "registry.artifact_saved",
            artifact_uri=artifact_uri,
            hash=file_hash,
            size_bytes=file_size,
        )

        return file_hash, file_size

    def load(self, artifact_uri: str, expected_hash: str | None = None) -> Path:
        """Load artifact from local filesystem."""
        full_path = self._resolve_path(artifact_uri)

        if not full_path.exists():
            raise ArtifactNotFoundError(f"Artifact not found: {artifact_uri}")

        # Verify hash if provided
        if expected_hash is not None:
            actual_hash = self.compute_hash(full_path)
            if actual_hash != expected_hash:
                logger.warning(
                    "registry.checksum_mismatch",
                    artifact_uri=artifact_uri,
                    expected=expected_hash,
                    actual=actual_hash,
                )
                raise ChecksumMismatchError(
                    f"Checksum mismatch for {artifact_uri}: "
                    f"expected {expected_hash}, got {actual_hash}"
                )

        return full_path

    def delete(self, artifact_uri: str) -> bool:
        """Delete artifact from local filesystem."""
        full_path = self._resolve_path(artifact_uri)

        if not full_path.exists():
            return False

        full_path.unlink()
        logger.info("registry.artifact_deleted", artifact_uri=artifact_uri)
        return True

    def exists(self, artifact_uri: str) -> bool:
        """Check if artifact exists on local filesystem."""
        full_path = self._resolve_path(artifact_uri)
        return full_path.exists()
```

---

## Task List

### Task 1: Add registry settings to config

```yaml
FILE: app/core/config.py
ACTION: MODIFY
FIND: "backtest_results_dir: str = './artifacts/backtests'"
INJECT AFTER:
  - ""
  - "# Registry"
  - "registry_artifact_root: str = './artifacts/registry'"
  - "registry_duplicate_policy: Literal['allow', 'deny', 'detect'] = 'detect'"
VALIDATION:
  - uv run mypy app/core/config.py
  - uv run pyright app/core/config.py
```

### Task 2: Create registry module structure

```yaml
ACTION: CREATE directories and __init__.py
FILES:
  - app/features/registry/__init__.py
  - app/features/registry/tests/__init__.py
PATTERN: Mirror backtesting module exports
```

### Task 3: Implement models.py (ORM)

```yaml
FILE: app/features/registry/models.py
ACTION: CREATE
IMPLEMENT:
  - RunStatus enum (PENDING, RUNNING, SUCCESS, FAILED, ARCHIVED)
  - ModelRun model with JSONB columns
  - DeploymentAlias model
  - GIN indexes for JSONB columns
  - Constraints for valid status, data window
PATTERN: Mirror app/features/data_platform/models.py
CRITICAL:
  - Use JSONB from sqlalchemy.dialects.postgresql
  - Use Mapped[dict[str, Any]] for JSONB typing
  - Add GIN indexes in __table_args__
VALIDATION:
  - uv run mypy app/features/registry/models.py
  - uv run pyright app/features/registry/models.py
```

### Task 4: Create Alembic migration

```yaml
FILE: alembic/versions/xxx_create_registry_tables.py
ACTION: CREATE (via alembic revision)
COMMAND: uv run alembic revision --autogenerate -m "create_registry_tables"
IMPLEMENT:
  - Create model_run table with JSONB columns
  - Create deployment_alias table
  - Add GIN indexes for model_config and metrics
  - Add composite indexes
  - Add check constraints
VALIDATION:
  - uv run alembic upgrade head
  - uv run alembic downgrade -1
  - uv run alembic upgrade head
```

### Task 5: Implement schemas.py

```yaml
FILE: app/features/registry/schemas.py
ACTION: CREATE
IMPLEMENT:
  - RunStatus enum (must match ORM enum)
  - VALID_TRANSITIONS dict for state machine
  - RuntimeInfo schema
  - AgentContext schema
  - RunCreate, RunUpdate, RunResponse schemas
  - RunListResponse for pagination
  - AliasCreate, AliasResponse schemas
  - RunCompareResponse schema
PATTERN: Mirror app/features/backtesting/schemas.py
CRITICAL:
  - Use ConfigDict(frozen=True) for immutable configs
  - Use alias="model_config" for field naming conflict
  - Validate data_window_end >= data_window_start
VALIDATION:
  - uv run mypy app/features/registry/schemas.py
  - uv run pyright app/features/registry/schemas.py
```

### Task 6: Implement storage.py

```yaml
FILE: app/features/registry/storage.py
ACTION: CREATE
IMPLEMENT:
  - StorageError, ArtifactNotFoundError, ChecksumMismatchError exceptions
  - AbstractStorageProvider ABC
  - LocalFSProvider implementation
  - compute_hash static method (SHA-256)
  - Path traversal prevention
CRITICAL:
  - Always validate paths are within root_dir
  - Compute hash BEFORE copy for save()
  - Verify hash in load() if expected_hash provided
VALIDATION:
  - uv run mypy app/features/registry/storage.py
  - uv run pyright app/features/registry/storage.py
```

### Task 7: Implement service.py

```yaml
FILE: app/features/registry/service.py
ACTION: CREATE
IMPLEMENT:
  - RegistryService class
  - create_run() - Create new run with PENDING status
  - get_run() - Get run by run_id
  - list_runs() - List with filtering and pagination
  - update_run() - Update status, metrics, artifact info
  - _validate_transition() - Validate state transitions
  - _compute_config_hash() - Hash for deduplication
  - _capture_runtime_info() - Python/library versions
  - create_alias() - Create/update deployment alias
  - get_alias() - Get alias by name
  - list_aliases() - List all aliases
  - delete_alias() - Remove alias
  - compare_runs() - Compare two runs
PATTERN: Mirror app/features/backtesting/service.py
CRITICAL:
  - State transitions must follow VALID_TRANSITIONS
  - config_hash computed from model_config JSON
  - Alias can only point to SUCCESS runs
  - Duplicate detection uses config_hash + data_window
VALIDATION:
  - uv run mypy app/features/registry/service.py
  - uv run pyright app/features/registry/service.py
```

### Task 8: Implement routes.py

```yaml
FILE: app/features/registry/routes.py
ACTION: CREATE
IMPLEMENT:
  - APIRouter(prefix="/registry", tags=["registry"])
  - POST /runs - Create new run
  - GET /runs - List runs with filters (model_type, status, store_id, product_id)
  - GET /runs/{run_id} - Get run details
  - PATCH /runs/{run_id} - Update run
  - GET /runs/{run_id}/verify - Verify artifact integrity
  - POST /aliases - Create/update alias
  - GET /aliases - List all aliases
  - GET /aliases/{alias_name} - Get alias details
  - DELETE /aliases/{alias_name} - Delete alias
  - GET /compare/{run_id_a}/{run_id_b} - Compare two runs
PATTERN: Mirror app/features/forecasting/routes.py
CRITICAL:
  - Use Depends(get_db) for database session
  - Structured logging: registry.run_created, registry.run_updated, etc.
  - Return 404 for not found, 400 for invalid transitions
  - Return 409 for duplicate if policy='deny'
VALIDATION:
  - uv run mypy app/features/registry/routes.py
  - uv run pyright app/features/registry/routes.py
```

### Task 9: Register router in main.py

```yaml
FILE: app/main.py
ACTION: MODIFY
FIND: "from app.features.backtesting.routes import router as backtesting_router"
INJECT AFTER:
  - "from app.features.registry.routes import router as registry_router"
FIND: "app.include_router(backtesting_router)"
INJECT AFTER:
  - "app.include_router(registry_router)"
VALIDATION:
  - uv run python -c "from app.main import app; print('OK')"
```

### Task 10: Create test fixtures (conftest.py)

```yaml
FILE: app/features/registry/tests/conftest.py
ACTION: CREATE
IMPLEMENT:
  - sample_model_config: NaiveModelConfig as dict
  - sample_run_create: RunCreate with valid data
  - sample_runtime_info: RuntimeInfo with current versions
  - sample_agent_context: AgentContext with test IDs
  - db_session fixture for integration tests
  - client fixture for route tests
  - temp_artifact: Temporary artifact file for storage tests
PATTERN: Mirror app/features/backtesting/tests/conftest.py
```

### Task 11: Create test_models.py

```yaml
FILE: app/features/registry/tests/test_models.py
ACTION: CREATE
IMPLEMENT:
  - Test ModelRun creation with JSONB columns
  - Test DeploymentAlias creation and FK relationship
  - Test run_id uniqueness constraint
  - Test alias_name uniqueness constraint
  - Test data_window constraint validation
  - Test status enum values
VALIDATION:
  - uv run pytest app/features/registry/tests/test_models.py -v
```

### Task 12: Create test_schemas.py

```yaml
FILE: app/features/registry/tests/test_schemas.py
ACTION: CREATE
IMPLEMENT:
  - Test RunStatus enum values
  - Test VALID_TRANSITIONS correctness
  - Test RunCreate validation (date range, model_type)
  - Test RunUpdate partial updates
  - Test RunResponse from_attributes
  - Test AliasCreate pattern validation
  - Test config_hash determinism
VALIDATION:
  - uv run pytest app/features/registry/tests/test_schemas.py -v
```

### Task 13: Create test_storage.py

```yaml
FILE: app/features/registry/tests/test_storage.py
ACTION: CREATE
IMPLEMENT:
  - Test LocalFSProvider.save() creates file and returns hash
  - Test LocalFSProvider.load() returns correct path
  - Test LocalFSProvider.load() with hash verification
  - Test ChecksumMismatchError on bad hash
  - Test ArtifactNotFoundError on missing file
  - Test path traversal prevention
  - Test delete() removes file
  - Test exists() returns correct boolean
VALIDATION:
  - uv run pytest app/features/registry/tests/test_storage.py -v
```

### Task 14: Create test_service.py

```yaml
FILE: app/features/registry/tests/test_service.py
ACTION: CREATE
IMPLEMENT:
  - Test create_run() with valid data
  - Test create_run() computes config_hash
  - Test create_run() captures runtime_info
  - Test update_run() state transitions
  - Test update_run() rejects invalid transitions
  - Test list_runs() filtering
  - Test list_runs() pagination
  - Test create_alias() with SUCCESS run
  - Test create_alias() rejects non-SUCCESS run
  - Test compare_runs() returns correct diff
  - Test duplicate detection (when policy='detect')
VALIDATION:
  - uv run pytest app/features/registry/tests/test_service.py -v
```

### Task 15: Create test_service_integration.py

```yaml
FILE: app/features/registry/tests/test_service_integration.py
ACTION: CREATE
IMPLEMENT:
  - Test full run lifecycle: PENDING -> RUNNING -> SUCCESS
  - Test alias creation and update
  - Test run listing with database
  - Test JSONB containment queries
  - Test GIN index usage (via EXPLAIN)
PATTERN: Mirror app/features/backtesting/tests/test_service_integration.py
VALIDATION:
  - uv run pytest app/features/registry/tests/test_service_integration.py -v -m integration
```

### Task 16: Create test_routes_integration.py

```yaml
FILE: app/features/registry/tests/test_routes_integration.py
ACTION: CREATE
IMPLEMENT:
  - Test POST /registry/runs creates run
  - Test GET /registry/runs returns list
  - Test GET /registry/runs/{run_id} returns details
  - Test PATCH /registry/runs/{run_id} updates status
  - Test POST /registry/aliases creates alias
  - Test GET /registry/aliases returns list
  - Test GET /registry/compare/{a}/{b} returns diff
  - Test 404 for non-existent run
  - Test 400 for invalid state transition
VALIDATION:
  - uv run pytest app/features/registry/tests/test_routes_integration.py -v -m integration
```

### Task 17: Create example files

```yaml
FILES:
  - examples/registry/create_run.py
  - examples/registry/list_runs.py
  - examples/registry/compare_runs.py
ACTION: CREATE
IMPLEMENT:
  - create_run.py: Create run, transition to SUCCESS, attach metrics
  - list_runs.py: List runs with filtering, show leaderboard
  - compare_runs.py: Compare two runs, show config/metrics diff
```

### Task 18: Update module `__init__.py` exports

```yaml
FILE: app/features/registry/__init__.py
ACTION: MODIFY
IMPLEMENT:
  - Export all public classes
  - `__all__` list (sorted alphabetically)
VALIDATION:
  - uv run python -c "from app.features.registry import *; print('OK')"
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run after EACH file creation
uv run ruff check app/features/registry/ --fix
uv run ruff format app/features/registry/

# Expected: All checks passed!
```

### Level 2: Type Checking

```bash
# Run after completing models, schemas, storage, service
uv run mypy app/features/registry/
uv run pyright app/features/registry/

# Expected: Success: no issues found
```

### Level 3: Database Migration

```bash
# After creating models.py, generate and run migration
uv run alembic revision --autogenerate -m "create_registry_tables"
uv run alembic upgrade head

# Verify tables exist
docker exec -it postgres psql -U forecastlab -d forecastlab -c "\d model_run"
docker exec -it postgres psql -U forecastlab -d forecastlab -c "\d deployment_alias"
```

### Level 4: Unit Tests

```bash
# Run incrementally as tests are created
uv run pytest app/features/registry/tests/test_schemas.py -v
uv run pytest app/features/registry/tests/test_storage.py -v
uv run pytest app/features/registry/tests/test_service.py -v

# Run all unit tests
uv run pytest app/features/registry/tests/ -v -m "not integration"

# Expected: 60+ tests passed
```

### Level 5: Integration Tests

```bash
# Start database
docker-compose up -d

# Run integration tests
uv run pytest app/features/registry/tests/test_service_integration.py -v -m integration
uv run pytest app/features/registry/tests/test_routes_integration.py -v -m integration

# Expected: 10+ integration tests passed
```

### Level 6: API Integration Test

```bash
# Start API
uv run uvicorn app.main:app --reload --port 8123

# Create a run
curl -X POST http://localhost:8123/registry/runs \
  -H "Content-Type: application/json" \
  -d '{
    "model_type": "naive",
    "model_config": {"model_type": "naive", "schema_version": "1.0"},
    "data_window_start": "2024-01-01",
    "data_window_end": "2024-06-30",
    "store_id": 1,
    "product_id": 1
  }'

# List runs
curl http://localhost:8123/registry/runs

# Update run status
curl -X PATCH http://localhost:8123/registry/runs/{run_id} \
  -H "Content-Type: application/json" \
  -d '{"status": "running"}'

# Complete run with metrics
curl -X PATCH http://localhost:8123/registry/runs/{run_id} \
  -H "Content-Type: application/json" \
  -d '{
    "status": "success",
    "metrics": {"mae": 1.5, "smape": 12.3}
  }'

# Create alias
curl -X POST http://localhost:8123/registry/aliases \
  -H "Content-Type: application/json" \
  -d '{
    "alias_name": "production",
    "run_id": "{run_id}",
    "description": "Current production model"
  }'
```

### Level 7: Full Validation

```bash
# Complete validation suite
uv run ruff check app/features/registry/ && \
uv run mypy app/features/registry/ && \
uv run pyright app/features/registry/ && \
uv run pytest app/features/registry/tests/ -v

# Expected: All green
```

---

## Final Checklist

- [ ] All 18 tasks completed
- [ ] `uv run ruff check .` — no errors
- [ ] `uv run mypy app/features/registry/` — no errors
- [ ] `uv run pyright app/features/registry/` — no errors
- [ ] `uv run pytest app/features/registry/tests/ -v` — 60+ tests passed
- [ ] Alembic migration runs successfully
- [ ] GIN indexes created for JSONB columns
- [ ] Example scripts run successfully
- [ ] Router registered in main.py
- [ ] Settings added to config.py
- [ ] Logging events follow standard format
- [ ] State machine transitions validated
- [ ] Checksum verification works
- [ ] Alias only points to SUCCESS runs
- [ ] Duplicate detection works per policy

---

## Anti-Patterns to Avoid

- **DON'T** use JSON instead of JSONB — JSONB is faster for queries
- **DON'T** store absolute paths in artifact_uri — use relative paths
- **DON'T** skip state transition validation — corrupts run lifecycle
- **DON'T** allow aliases to non-SUCCESS runs — undefined behavior in production
- **DON'T** skip checksum verification on load — security risk
- **DON'T** use plain index on JSONB — use GIN for containment queries
- **DON'T** forget to compute config_hash — needed for deduplication
- **DON'T** hardcode storage paths — use Settings
- **DON'T** catch generic Exception — be specific about error types
- **DON'T** use sync operations in async context — will block event loop

---

## Confidence Score: 8/10

**Strengths:**
- Clear patterns from forecasting and backtesting modules to follow
- Existing ModelBundle in persistence.py has hash computation pattern
- Well-documented SQLAlchemy JSONB support
- Comprehensive task breakdown with validation gates
- MLflow provides industry-standard registry design reference
- Strong test patterns from backtesting module

**Risks:**
- JSONB GIN indexing may require tuning for large datasets
- State machine transitions add complexity
- Alias update atomicity needs careful handling
- Integration with existing forecasting module needs coordination
- Duplicate detection edge cases (same config, different data windows)

**Mitigation:**
- Start with simple GIN index, optimize later if needed
- Use explicit transition validation function
- Use database transactions for alias updates
- Add integration tests covering forecasting → registry flow
- Define clear duplicate policy (config_hash + data_window_hash)

---

## Sources

- [SQLAlchemy PostgreSQL JSONB](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)
- [JSONB Indexing in Postgres](https://www.crunchydata.com/blog/indexing-jsonb-in-postgres)
- [JSONB Storage Patterns](https://scalegrid.io/blog/using-jsonb-in-postgresql-how-to-effectively-store-index-json-data-in-postgresql/)
- [MLflow Model Registry](https://mlflow.org/docs/latest/ml/model-registry/)
- [PostgreSQL GIN Indexes](https://www.postgresql.org/docs/current/gin.html)
