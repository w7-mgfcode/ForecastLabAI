# Phase 6: Model Registry

**Date Completed**: 2026-02-01
**PRP**: [PRP-7-model-registry.md](../../PRPs/PRP-7-model-registry.md)
**Release**: PR #35

---

## Executive Summary

Phase 6 implements the Model Registry for ForecastLabAI, providing comprehensive run tracking with deployment aliases and artifact integrity verification. The module enables reproducible ML workflows by capturing full experiment lineage: configurations, data windows, metrics, and artifacts with SHA-256 checksums.

**Key Achievement**: Complete run lifecycle management with state machine validation and secure artifact storage with path traversal prevention.

---

## Deliverables

### 1. ORM Models

**File**: `app/features/registry/models.py`

SQLAlchemy models for registry storage:

```python
class RunStatus(str, Enum):
    """Valid states for a model run.

    State transitions:
    - PENDING -> RUNNING -> SUCCESS | FAILED
    - Any state except ARCHIVED -> ARCHIVED
    """
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ARCHIVED = "archived"
```

**ModelRun Table**:

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer | Primary key |
| `run_id` | String(32) | Unique external identifier (UUID hex) |
| `status` | String(20) | Current lifecycle state |
| `model_type` | String(50) | Type of model |
| `model_config` | JSONB | Full model configuration |
| `feature_config` | JSONB | Feature engineering config (nullable) |
| `config_hash` | String(16) | Hash for deduplication |
| `data_window_start` | Date | Training data start |
| `data_window_end` | Date | Training data end |
| `store_id` | Integer | Store ID |
| `product_id` | Integer | Product ID |
| `metrics` | JSONB | Performance metrics |
| `artifact_uri` | String(500) | Relative path to artifact |
| `artifact_hash` | String(64) | SHA-256 checksum |
| `artifact_size_bytes` | Integer | File size |
| `runtime_info` | JSONB | Python/library versions |
| `agent_context` | JSONB | Agent/session IDs |
| `git_sha` | String(40) | Git commit hash |
| `error_message` | String(2000) | Error details (FAILED runs) |
| `started_at` | DateTime(tz) | Run start time |
| `completed_at` | DateTime(tz) | Run completion time |
| `created_at` | DateTime(tz) | Record creation (mixin) |
| `updated_at` | DateTime(tz) | Record update (mixin) |

**DeploymentAlias Table**:

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer | Primary key |
| `alias_name` | String(100) | Unique alias name |
| `run_id` | Integer | Foreign key to ModelRun |
| `description` | String(500) | Optional description |

**Indexes**:
- `ix_model_run_run_id` (unique)
- `ix_model_run_status`
- `ix_model_run_model_type`
- `ix_model_run_store_product` (composite)
- `ix_model_run_data_window` (composite)
- `ix_model_run_model_config_gin` (GIN for JSONB)
- `ix_model_run_metrics_gin` (GIN for JSONB)

### 2. State Machine

**Valid Transitions**:

```python
VALID_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.PENDING: {RunStatus.RUNNING, RunStatus.ARCHIVED},
    RunStatus.RUNNING: {RunStatus.SUCCESS, RunStatus.FAILED, RunStatus.ARCHIVED},
    RunStatus.SUCCESS: {RunStatus.ARCHIVED},
    RunStatus.FAILED: {RunStatus.ARCHIVED},
    RunStatus.ARCHIVED: set(),  # Terminal state
}
```

```
PENDING ──→ RUNNING ──→ SUCCESS ──→ ARCHIVED
   │           │           │            ↑
   │           └───→ FAILED ───────────→│
   └──────────────────────────────────→─┘
```

### 3. Storage Provider

**File**: `app/features/registry/storage.py`

Abstract interface with LocalFS implementation:

```python
class AbstractStorageProvider(ABC):
    """Abstract base class for artifact storage."""

    @abstractmethod
    def save(self, source_path: Path, artifact_uri: str) -> tuple[str, int]:
        """Save artifact, returns (sha256_hash, size_bytes)."""

    @abstractmethod
    def load(self, artifact_uri: str, expected_hash: str | None = None) -> Path:
        """Load artifact with optional hash verification."""

    @abstractmethod
    def delete(self, artifact_uri: str) -> bool:
        """Delete artifact, returns True if deleted."""

    @abstractmethod
    def exists(self, artifact_uri: str) -> bool:
        """Check if artifact exists."""

    @staticmethod
    def compute_hash(file_path: Path) -> str:
        """Compute SHA-256 hash of file."""
```

**LocalFSProvider**:
- Default provider for development/single-node
- Root directory from `registry_artifact_root` setting
- **CRITICAL**: Path traversal prevention via `relative_to()` validation
- SHA-256 checksum on save and optional verify on load

**Security**:
```python
def _resolve_path(self, artifact_uri: str) -> Path:
    full_path = (self.root_dir / artifact_uri).resolve()
    # Security: ensure path is within root
    try:
        full_path.relative_to(self.root_dir)
    except ValueError:
        raise StorageError(f"Path traversal attempt: {artifact_uri}")
    return full_path
```

### 4. Registry Schemas

**File**: `app/features/registry/schemas.py`

| Schema | Purpose |
|--------|---------|
| `RunStatus` | Enum for run lifecycle states |
| `RuntimeInfo` | Python/library versions snapshot |
| `AgentContext` | Agent ID and session ID |
| `RunCreate` | Create run request |
| `RunUpdate` | Update run (status, metrics, artifacts) |
| `RunResponse` | Full run details response |
| `RunListResponse` | Paginated list of runs |
| `AliasCreate` | Create/update alias request |
| `AliasResponse` | Alias details with run info |
| `RunCompareResponse` | Side-by-side run comparison |

**Alias Naming Rules**:
- Pattern: `^[a-z0-9][a-z0-9\-_]*$`
- Start with lowercase letter or number
- Contains letters, numbers, hyphens, underscores
- Maximum 100 characters

### 5. RegistryService

**File**: `app/features/registry/service.py`

Core service for registry operations:

```python
class RegistryService:
    """Service for model run tracking and alias management."""

    async def create_run(self, db: AsyncSession, run_data: RunCreate) -> RunResponse
    async def get_run(self, db: AsyncSession, run_id: str) -> RunResponse | None
    async def list_runs(self, db, page, page_size, filters...) -> RunListResponse
    async def update_run(self, db, run_id, update_data) -> RunResponse | None
    async def create_alias(self, db, alias_data: AliasCreate) -> AliasResponse
    async def get_alias(self, db, alias_name) -> AliasResponse | None
    async def list_aliases(self, db) -> list[AliasResponse]
    async def delete_alias(self, db, alias_name) -> bool
    async def compare_runs(self, db, run_id_a, run_id_b) -> RunCompareResponse | None
```

**Duplicate Detection**:
Based on `registry_duplicate_policy` setting:
- `allow`: Always create new runs
- `deny`: Reject if duplicate config+window exists
- `detect`: Log warning but allow creation

**Runtime Capture**:
Automatically captures Python and library versions:
```python
RuntimeInfo(
    python_version="3.12.0",
    sklearn_version="1.4.0",
    numpy_version="1.26.0",
    pandas_version="2.1.0",
    joblib_version="1.3.0",
)
```

### 6. API Endpoints

**File**: `app/features/registry/routes.py`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/registry/runs` | POST | Create a new run |
| `/registry/runs` | GET | List runs with filters |
| `/registry/runs/{run_id}` | GET | Get run details |
| `/registry/runs/{run_id}` | PATCH | Update run status/metrics/artifacts |
| `/registry/runs/{run_id}/verify` | GET | Verify artifact integrity |
| `/registry/aliases` | POST | Create/update alias |
| `/registry/aliases` | GET | List all aliases |
| `/registry/aliases/{alias_name}` | GET | Get alias details |
| `/registry/aliases/{alias_name}` | DELETE | Delete alias |
| `/registry/compare/{run_id_a}/{run_id_b}` | GET | Compare two runs |

**Create Run Request**:
```json
{
  "model_type": "seasonal_naive",
  "model_config": {
    "model_type": "seasonal_naive",
    "season_length": 7
  },
  "data_window_start": "2024-01-01",
  "data_window_end": "2024-12-31",
  "store_id": 1,
  "product_id": 101,
  "agent_context": {
    "agent_id": "backtest-agent-v1",
    "session_id": "abc123"
  }
}
```

**Update Run Request**:
```json
{
  "status": "success",
  "metrics": {
    "mae": 3.45,
    "smape": 12.34
  },
  "artifact_uri": "runs/abc123/model.joblib",
  "artifact_hash": "sha256:a1b2c3...",
  "artifact_size_bytes": 102400
}
```

**Compare Response**:
```json
{
  "run_a": { ... },
  "run_b": { ... },
  "config_diff": {
    "season_length": {"a": 7, "b": 14}
  },
  "metrics_diff": {
    "mae": {"a": 3.45, "b": 4.12, "diff": -0.67},
    "smape": {"a": 12.34, "b": 15.67, "diff": -3.33}
  }
}
```

### 7. Database Migration

**File**: `alembic/versions/a2f7b3c8d901_create_model_registry_tables.py`

Creates:
- `model_run` table with all columns and indexes
- `deployment_alias` table with foreign key
- Check constraints for status and data window validity

### 8. Test Suite

**Directory**: `app/features/registry/tests/`

| File | Tests | Coverage |
|------|-------|----------|
| `test_schemas.py` | 22 | Schema validation, config hash, transitions |
| `test_storage.py` | 28 | LocalFS save/load, hash verification, path security |
| `test_service.py` | 35 | Service operations, state machine, duplicates |
| `test_routes.py` | 42 | All endpoints, error cases, pagination |

**Total**: 127 tests (103 unit + 24 integration)

**Integration Tests**:
- Require PostgreSQL via `docker-compose up -d`
- Test full CRUD lifecycle
- Verify JSONB queries work correctly
- Test GIN indexes for containment queries

### 9. Example Script

**File**: `examples/registry_demo.py`

Demonstrates:
- Creating a run
- Transitioning through states
- Adding metrics and artifacts
- Creating deployment aliases
- Comparing runs

---

## Configuration

**File**: `app/core/config.py`

New settings added:

```python
# Registry
registry_artifact_root: str = "./artifacts/registry"
registry_duplicate_policy: Literal["allow", "deny", "detect"] = "detect"
```

| Setting | Default | Description |
|---------|---------|-------------|
| `registry_artifact_root` | `./artifacts/registry` | Root directory for artifacts |
| `registry_duplicate_policy` | `detect` | How to handle duplicate runs |

---

## Directory Structure

```
app/features/registry/
├── __init__.py          # Module exports
├── models.py            # SQLAlchemy ORM models
├── schemas.py           # Pydantic request/response schemas
├── storage.py           # AbstractStorageProvider + LocalFSProvider
├── service.py           # RegistryService
├── routes.py            # FastAPI endpoints
└── tests/
    ├── __init__.py
    ├── conftest.py      # Test fixtures
    ├── test_schemas.py  # Schema validation tests
    ├── test_storage.py  # Storage provider tests
    ├── test_service.py  # Service unit tests
    └── test_routes.py   # Route integration tests

alembic/versions/
└── a2f7b3c8d901_create_model_registry_tables.py

examples/
└── registry_demo.py     # Registry usage demo
```

---

## Validation Results

```
$ uv run ruff check app/features/registry/
All checks passed!

$ uv run mypy app/features/registry/
Success: no issues found in 11 source files

$ uv run pyright app/features/registry/
0 errors, 0 warnings, 0 informations

$ uv run pytest app/features/registry/tests/ -v
127 passed in 3.45s

$ uv run pytest app/features/registry/tests/ -v -m integration
24 passed in 5.67s
```

---

## Logging Events

| Event | Description |
|-------|-------------|
| `registry.create_run_request_received` | Run creation request received |
| `registry.create_run_request_completed` | Run created successfully |
| `registry.create_run_request_failed` | Run creation failed |
| `registry.update_run_request_received` | Run update request received |
| `registry.update_run_request_completed` | Run updated successfully |
| `registry.update_run_request_failed` | Run update failed |
| `registry.create_alias_request_received` | Alias creation received |
| `registry.create_alias_request_completed` | Alias created/updated |
| `registry.delete_alias_request_received` | Alias deletion received |
| `registry.delete_alias_request_completed` | Alias deleted |
| `registry.artifact_saved` | Artifact saved to storage |
| `registry.artifact_deleted` | Artifact deleted |
| `registry.checksum_mismatch` | Artifact hash verification failed |
| `registry.path_traversal_attempt` | Path traversal attack detected |
| `registry.duplicate_run_detected` | Duplicate run detected (warn/deny) |

---

## Security Considerations

1. **Path Traversal Prevention**: All artifact URIs validated to stay within root
2. **SHA-256 Integrity**: Checksums computed on save, verified on load
3. **State Machine Enforcement**: Invalid transitions rejected
4. **Alias Validation**: Only SUCCESS runs can have aliases
5. **Input Validation**: Pydantic schemas with strict constraints

---

## Next Phase Preparation

Phase 7 (RAG Knowledge Base) will integrate with the registry to:
1. Index model configurations and metrics for retrieval
2. Enable natural language queries about model performance
3. Provide evidence-grounded answers with run citations
4. Support experiment comparison queries

**Integration Points**:
- `ModelRun.model_config` and `metrics` JSONB for embedding
- `RunCompareResponse` for structured comparison answers
- `DeploymentAlias` for production model references
