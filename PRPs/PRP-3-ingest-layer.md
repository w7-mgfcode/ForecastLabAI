# PRP-3: Ingest Layer — Idempotent Batch Upserts

## Goal

Implement typed, idempotent batch upsert endpoints for the ForecastLabAI data platform. The primary endpoint `POST /ingest/sales-daily` accepts sales records with natural keys (`store_code`, `sku`) and performs replay-safe upserts using PostgreSQL's `ON CONFLICT DO UPDATE`.

**End State:** A production-ready ingest layer with:
- `POST /ingest/sales-daily` — batch upsert endpoint accepting natural keys
- Key resolution service (store_code → store_id, sku → product_id)
- Configurable batch sizing and timeouts via Settings
- Comprehensive error handling with row-level validation
- Structured logging with inserted/updated counts and duration metrics
- All validation gates passing (ruff, mypy, pyright, pytest)

---

## Why

- **Foundation for ForecastOps**: Training and backtesting (INITIAL-4 through INITIAL-6) require populated sales data
- **Replay-Safe Ingestion**: `ON CONFLICT DO UPDATE` enables re-running pipelines without duplicates
- **External System Compatibility**: Real-world systems send natural keys (store_code, sku), not internal database IDs
- **Data Quality**: Row-level validation prevents bad data while allowing valid rows to succeed
- **Operational Visibility**: Structured logging enables monitoring ingestion health and performance

---

## What

### Success Criteria

- [ ] `POST /ingest/sales-daily` accepts batch of sales records with `store_code` and `sku`
- [ ] Service resolves natural keys to internal IDs via lookup (with basic caching)
- [ ] Unknown store_code/sku rejects individual row, continues processing valid rows
- [ ] `ON CONFLICT (date, store_id, product_id) DO UPDATE` ensures idempotency
- [ ] Response includes `inserted_count`, `updated_count`, `rejected_count`, `errors[]`
- [ ] Batch size configurable via `INGEST_BATCH_SIZE` setting (default: 1000)
- [ ] Request timeout configurable via `INGEST_TIMEOUT_SECONDS` setting (default: 60)
- [ ] All logs follow `ingest.{component}.{action}_{state}` naming convention
- [ ] Unit tests for schemas, service logic, key resolution
- [ ] Integration tests verify upsert idempotency and constraint enforcement
- [ ] Example files: `examples/api/ingest_sales_daily.http`

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ - Critical for implementation
- url: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert
  why: SQLAlchemy 2.0 PostgreSQL-specific INSERT...ON CONFLICT syntax
  critical: Use `from sqlalchemy.dialects.postgresql import insert` for pg_insert

- url: https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html
  why: ORM-enabled INSERT/UPDATE/DELETE operations with SQLAlchemy 2.0
  critical: Use `insert(Model).values()` not `session.add()` for bulk upserts

- url: https://docs.pydantic.dev/latest/concepts/validators/
  why: Pydantic v2 field validators and model validators
  critical: Use `@field_validator` and `@model_validator` decorators

- url: https://fastapi.tiangolo.com/tutorial/request-files/
  why: FastAPI request body handling patterns
  critical: Use `List[Model]` in request body for batch operations

- url: https://www.dbvis.com/thetable/postgresql-upsert-insert-on-conflict-guide/
  why: PostgreSQL UPSERT best practices and performance considerations
  critical: conflict_target must match unique constraint exactly

- url: https://overflow.no/blog/2025/1/5/using-staging-tables-for-faster-bulk-upserts-with-python-and-postgresql/
  why: Performance optimization for large batch upserts
  critical: For >10k rows, staging table approach is faster (YAGNI for now)

# Internal codebase files - MUST reference these patterns
- file: app/features/data_platform/models.py
  why: SalesDaily model with UniqueConstraint("date", "store_id", "product_id")

- file: app/features/data_platform/schemas.py
  why: Existing Pydantic schema patterns (Base/Create/Read pattern)

- file: app/core/database.py
  why: AsyncSession dependency pattern (get_db)

- file: app/core/exceptions.py
  why: ForecastLabError, ValidationError, DatabaseError patterns

- file: app/core/health.py
  why: Router structure and endpoint patterns

- file: app/core/logging.py
  why: get_logger() and request_id_ctx patterns

- file: docs/validation/logging-standard.md
  why: Event naming convention: `{domain}.{component}.{action}_{state}`

- file: CLAUDE.md
  why: Type safety requirements, vertical slice architecture, KISS/YAGNI principles
```

### Current Codebase Tree

```bash
app/
├── __init__.py
├── main.py                     # FastAPI entry, router registration
├── core/
│   ├── config.py               # Pydantic Settings (add ingest config here)
│   ├── database.py             # AsyncSession, get_db()
│   ├── exceptions.py           # ForecastLabError hierarchy
│   ├── health.py               # Router pattern example
│   ├── logging.py              # Structured logging, get_logger()
│   └── middleware.py           # RequestIdMiddleware
├── shared/
│   ├── models.py               # TimestampMixin
│   ├── schemas.py              # ErrorResponse, PaginationParams
│   └── utils.py                # Utilities
└── features/
    └── data_platform/
        ├── models.py           # Store, Product, Calendar, SalesDaily (with grain constraint)
        ├── schemas.py          # StoreRead, ProductRead, SalesDailyCreate, etc.
        └── tests/              # Model and constraint tests
```

### Desired Codebase Tree (files to be added)

```bash
app/
├── core/
│   └── config.py               # MODIFY: Add ingest_batch_size, ingest_timeout_seconds
└── features/
    └── ingest/                 # NEW: Ingest vertical slice
        ├── __init__.py         # Module exports
        ├── schemas.py          # IngestSalesDailyRequest, IngestSalesDailyResponse, IngestRowError
        ├── service.py          # KeyResolver, upsert_sales_daily_batch()
        ├── routes.py           # POST /ingest/sales-daily endpoint
        └── tests/
            ├── __init__.py
            ├── conftest.py     # Feature-specific fixtures
            ├── test_schemas.py # Schema validation tests
            ├── test_service.py # Service logic tests (with mocked DB)
            └── test_routes.py  # Integration tests for API endpoint

examples/
└── api/
    └── ingest_sales_daily.http # NEW: HTTP client example
```

### Known Gotchas & Library Quirks

```python
# CRITICAL: PostgreSQL-specific INSERT for ON CONFLICT support
# ❌ WRONG: from sqlalchemy import insert
# ✅ CORRECT: from sqlalchemy.dialects.postgresql import insert as pg_insert

# CRITICAL: ON CONFLICT index_elements must match UniqueConstraint EXACTLY
# The constraint is: UniqueConstraint("date", "store_id", "product_id", name="uq_sales_daily_grain")
# ✅ CORRECT:
stmt = pg_insert(SalesDaily).values(data).on_conflict_do_update(
    index_elements=["date", "store_id", "product_id"],  # Must be column names, not constraint name
    set_={...}
)

# CRITICAL: Use stmt.excluded for UPDATE values
# ✅ CORRECT:
stmt = pg_insert(SalesDaily).values(data).on_conflict_do_update(
    index_elements=["date", "store_id", "product_id"],
    set_={
        "quantity": stmt.excluded.quantity,
        "unit_price": stmt.excluded.unit_price,
        "total_amount": stmt.excluded.total_amount,
        "updated_at": func.now(),
    }
)

# CRITICAL: Batch execution with executemany semantics
# For bulk upserts, execute each statement individually or use RETURNING
# asyncpg has 32767 parameter limit - batch accordingly

# CRITICAL: Decimal precision for monetary values
# ❌ WRONG: total_amount: float
# ✅ CORRECT: total_amount: Decimal = Field(..., decimal_places=2)

# CRITICAL: Foreign key lookups must happen BEFORE upsert
# The ingest payload has store_code/sku, but SalesDaily needs store_id/product_id
# Resolve these first, reject rows with unknown codes

# CRITICAL: Calendar FK constraint
# SalesDaily.date has FK to calendar.date - calendar entry MUST exist
# Either auto-create calendar entries or reject if missing

# CRITICAL: Error handling - partial success pattern
# Don't fail entire batch on one bad row
# Return inserted/updated/rejected counts with error details
```

---

## Implementation Blueprint

### Data Models and Structure

#### Request/Response Schemas (app/features/ingest/schemas.py)

```python
"""Pydantic schemas for ingest API."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


class SalesDailyIngestRow(BaseModel):
    """Single row in sales daily ingest payload.

    Uses natural keys (store_code, sku) instead of internal IDs.
    Service resolves these to store_id, product_id before upsert.
    """

    date: date
    store_code: str = Field(..., min_length=1, max_length=20, description="Store code (natural key)")
    sku: str = Field(..., min_length=1, max_length=50, description="Product SKU (natural key)")
    quantity: int = Field(..., ge=0, description="Units sold (non-negative)")
    unit_price: Decimal = Field(..., ge=0, description="Price per unit")
    total_amount: Decimal = Field(..., ge=0, description="Total sales amount")

    @model_validator(mode="after")
    def validate_total_amount_consistency(self) -> "SalesDailyIngestRow":
        """Warn if total_amount doesn't match quantity * unit_price."""
        expected = self.quantity * self.unit_price
        if abs(self.total_amount - expected) > Decimal("0.01"):
            # Allow through but could log warning
            pass
        return self


class SalesDailyIngestRequest(BaseModel):
    """Request body for POST /ingest/sales-daily."""

    records: list[SalesDailyIngestRow] = Field(
        ...,
        min_length=1,
        max_length=10000,  # Configurable max batch size
        description="Sales records to upsert"
    )


class IngestRowError(BaseModel):
    """Error detail for a single rejected row."""

    row_index: int = Field(..., description="0-based index of the failed row")
    store_code: str = Field(..., description="Store code from the row")
    sku: str = Field(..., description="SKU from the row")
    date: date = Field(..., description="Date from the row")
    error_code: str = Field(..., description="Machine-readable error code")
    error_message: str = Field(..., description="Human-readable error message")


class SalesDailyIngestResponse(BaseModel):
    """Response body for POST /ingest/sales-daily."""

    inserted_count: int = Field(..., ge=0, description="Number of new rows inserted")
    updated_count: int = Field(..., ge=0, description="Number of existing rows updated")
    rejected_count: int = Field(..., ge=0, description="Number of rows rejected")
    total_processed: int = Field(..., ge=0, description="Total rows processed")
    errors: list[IngestRowError] = Field(default_factory=list, description="Details of rejected rows")
    duration_ms: float = Field(..., ge=0, description="Processing duration in milliseconds")
```

#### Settings Extension (app/core/config.py)

```python
# Add to Settings class:
# Ingest configuration
ingest_batch_size: int = Field(default=1000, ge=1, le=10000, description="Max rows per upsert batch")
ingest_timeout_seconds: int = Field(default=60, ge=1, le=300, description="Request timeout for ingest")
```

### Tasks (Ordered Implementation)

```yaml
Task 1: Create ingest feature directory structure
  FILES:
    - app/features/ingest/__init__.py
    - app/features/ingest/schemas.py
    - app/features/ingest/service.py
    - app/features/ingest/routes.py
    - app/features/ingest/tests/__init__.py
    - app/features/ingest/tests/conftest.py
  VALIDATION:
    - ls -la app/features/ingest/

Task 2: Add ingest configuration to Settings
  MODIFY: app/core/config.py
  ADD:
    - ingest_batch_size: int = 1000
    - ingest_timeout_seconds: int = 60
  VALIDATION:
    - uv run python -c "from app.core.config import get_settings; s = get_settings(); print(f'batch_size={s.ingest_batch_size}')"

Task 3: Implement ingest schemas
  FILE: app/features/ingest/schemas.py
  IMPLEMENT:
    - SalesDailyIngestRow (natural keys: store_code, sku)
    - SalesDailyIngestRequest (list of rows with validation)
    - IngestRowError (error details for rejected rows)
    - SalesDailyIngestResponse (counts + errors + duration)
  VALIDATION:
    - uv run mypy app/features/ingest/schemas.py
    - uv run pyright app/features/ingest/schemas.py

Task 4: Implement KeyResolver service
  FILE: app/features/ingest/service.py
  IMPLEMENT:
    - KeyResolver class with resolve_store_codes() and resolve_skus() methods
    - Uses simple dict lookup from DB (can optimize with caching later)
    - Returns mapping: {store_code: store_id} and {sku: product_id}
  PSEUDOCODE:
    ```python
    class KeyResolver:
        async def resolve_store_codes(
            self, db: AsyncSession, codes: set[str]
        ) -> dict[str, int]:
            """Resolve store codes to IDs. Returns {code: id} for found stores."""
            stmt = select(Store.code, Store.id).where(Store.code.in_(codes))
            result = await db.execute(stmt)
            return {row.code: row.id for row in result}

        async def resolve_skus(
            self, db: AsyncSession, skus: set[str]
        ) -> dict[str, int]:
            """Resolve SKUs to product IDs. Returns {sku: id} for found products."""
            stmt = select(Product.sku, Product.id).where(Product.sku.in_(skus))
            result = await db.execute(stmt)
            return {row.sku: row.id for row in result}
    ```
  VALIDATION:
    - uv run mypy app/features/ingest/service.py

Task 5: Implement upsert_sales_daily_batch service function
  FILE: app/features/ingest/service.py (append)
  IMPLEMENT:
    - upsert_sales_daily_batch(db, records) -> UpsertResult
    - Uses pg_insert with on_conflict_do_update
    - Handles partial success (collects errors for invalid rows)
    - Tracks inserted vs updated counts
  PSEUDOCODE:
    ```python
    @dataclass
    class UpsertResult:
        inserted_count: int
        updated_count: int
        rejected_count: int
        errors: list[IngestRowError]

    async def upsert_sales_daily_batch(
        db: AsyncSession,
        records: list[SalesDailyIngestRow],
        key_resolver: KeyResolver,
    ) -> UpsertResult:
        """Upsert sales daily records with key resolution and partial success."""
        logger = get_logger(__name__)
        logger.info("ingest.sales_daily.upsert_started", batch_size=len(records))

        # 1. Extract unique codes and SKUs
        store_codes = {r.store_code for r in records}
        skus = {r.sku for r in records}

        # 2. Resolve keys
        store_map = await key_resolver.resolve_store_codes(db, store_codes)
        product_map = await key_resolver.resolve_skus(db, skus)

        # 3. Validate and prepare rows
        valid_rows = []
        errors = []
        for idx, record in enumerate(records):
            store_id = store_map.get(record.store_code)
            product_id = product_map.get(record.sku)

            if store_id is None:
                errors.append(IngestRowError(
                    row_index=idx,
                    store_code=record.store_code,
                    sku=record.sku,
                    date=record.date,
                    error_code="UNKNOWN_STORE",
                    error_message=f"Store code '{record.store_code}' not found",
                ))
                continue

            if product_id is None:
                errors.append(IngestRowError(
                    row_index=idx,
                    store_code=record.store_code,
                    sku=record.sku,
                    date=record.date,
                    error_code="UNKNOWN_PRODUCT",
                    error_message=f"SKU '{record.sku}' not found",
                ))
                continue

            valid_rows.append({
                "date": record.date,
                "store_id": store_id,
                "product_id": product_id,
                "quantity": record.quantity,
                "unit_price": record.unit_price,
                "total_amount": record.total_amount,
            })

        # 4. Perform upsert for valid rows
        inserted = 0
        updated = 0

        if valid_rows:
            # Use PostgreSQL INSERT...ON CONFLICT
            stmt = pg_insert(SalesDaily).values(valid_rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["date", "store_id", "product_id"],
                set_={
                    "quantity": stmt.excluded.quantity,
                    "unit_price": stmt.excluded.unit_price,
                    "total_amount": stmt.excluded.total_amount,
                    "updated_at": func.now(),
                }
            )
            # Note: Counting inserted vs updated requires RETURNING + checking xmax
            # Simplified: count all as "processed" for now
            await db.execute(stmt)
            await db.commit()
            # For accurate counts, would need separate logic
            inserted = len(valid_rows)  # Simplified

        logger.info(
            "ingest.sales_daily.upsert_completed",
            inserted=inserted,
            updated=updated,
            rejected=len(errors),
        )

        return UpsertResult(
            inserted_count=inserted,
            updated_count=updated,
            rejected_count=len(errors),
            errors=errors,
        )
    ```
  VALIDATION:
    - uv run mypy app/features/ingest/service.py
    - uv run pyright app/features/ingest/service.py

Task 6: Implement ingest routes
  FILE: app/features/ingest/routes.py
  IMPLEMENT:
    - Router with tag "ingest"
    - POST /ingest/sales-daily endpoint
    - Uses get_db() dependency
    - Returns SalesDailyIngestResponse
  PSEUDOCODE:
    ```python
    router = APIRouter(prefix="/ingest", tags=["ingest"])

    @router.post(
        "/sales-daily",
        response_model=SalesDailyIngestResponse,
        status_code=status.HTTP_200_OK,
    )
    async def ingest_sales_daily(
        request: SalesDailyIngestRequest,
        db: AsyncSession = Depends(get_db),
    ) -> SalesDailyIngestResponse:
        """Batch upsert daily sales records.

        Accepts sales records with natural keys (store_code, sku).
        Resolves to internal IDs and performs idempotent upsert.

        Returns counts of inserted, updated, and rejected rows.
        Rejected rows include error details for debugging.
        """
        logger = get_logger(__name__)
        start_time = time.time()

        logger.info("ingest.sales_daily.request_received", record_count=len(request.records))

        try:
            key_resolver = KeyResolver()
            result = await upsert_sales_daily_batch(db, request.records, key_resolver)

            duration_ms = (time.time() - start_time) * 1000

            return SalesDailyIngestResponse(
                inserted_count=result.inserted_count,
                updated_count=result.updated_count,
                rejected_count=result.rejected_count,
                total_processed=len(request.records),
                errors=result.errors,
                duration_ms=round(duration_ms, 2),
            )
        except Exception as e:
            logger.error(
                "ingest.sales_daily.request_failed",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise DatabaseError(
                message="Failed to process sales daily ingest",
                details={"error": str(e)},
            )
    ```
  VALIDATION:
    - uv run mypy app/features/ingest/routes.py
    - uv run pyright app/features/ingest/routes.py

Task 7: Register ingest router in main.py
  MODIFY: app/main.py
  ADD:
    - from app.features.ingest.routes import router as ingest_router
    - app.include_router(ingest_router)
  VALIDATION:
    - uv run python -c "from app.main import app; print([r.path for r in app.routes])"

Task 8: Create unit tests for schemas
  FILE: app/features/ingest/tests/test_schemas.py
  IMPLEMENT:
    - Test SalesDailyIngestRow validation (valid inputs)
    - Test SalesDailyIngestRow rejection (negative quantity, etc.)
    - Test SalesDailyIngestRequest with empty list (should fail)
    - Test SalesDailyIngestResponse serialization
  VALIDATION:
    - uv run pytest app/features/ingest/tests/test_schemas.py -v

Task 9: Create unit tests for service
  FILE: app/features/ingest/tests/test_service.py
  IMPLEMENT:
    - Test KeyResolver with mocked DB session
    - Test upsert_sales_daily_batch with valid records
    - Test partial success with unknown store_code
    - Test partial success with unknown sku
  VALIDATION:
    - uv run pytest app/features/ingest/tests/test_service.py -v

Task 10: Create integration tests for routes
  FILE: app/features/ingest/tests/test_routes.py
  IMPLEMENT:
    - Test POST /ingest/sales-daily with valid payload
    - Test idempotency (same payload twice = updates, not duplicates)
    - Test partial success response with mixed valid/invalid rows
    - Test empty records list returns 422
  REQUIRES:
    - Running PostgreSQL (docker-compose up -d)
    - Sample store, product, calendar data
  VALIDATION:
    - docker-compose up -d
    - uv run alembic upgrade head
    - uv run pytest app/features/ingest/tests/test_routes.py -v -m integration
    - docker-compose down

Task 11: Create HTTP example file
  FILE: examples/api/ingest_sales_daily.http
  CONTENT:
    ```http
    ### Ingest Sales Daily - Happy Path
    POST {{API_BASE_URL}}/ingest/sales-daily
    Content-Type: application/json

    {
      "records": [
        {
          "date": "2024-01-15",
          "store_code": "S001",
          "sku": "SKU-001",
          "quantity": 10,
          "unit_price": 9.99,
          "total_amount": 99.90
        },
        {
          "date": "2024-01-15",
          "store_code": "S001",
          "sku": "SKU-002",
          "quantity": 5,
          "unit_price": 19.99,
          "total_amount": 99.95
        }
      ]
    }

    ### Expected Response:
    # {
    #   "inserted_count": 2,
    #   "updated_count": 0,
    #   "rejected_count": 0,
    #   "total_processed": 2,
    #   "errors": [],
    #   "duration_ms": 45.23
    # }

    ### Ingest Sales Daily - Replay (Idempotent)
    # Running the same request again should update, not duplicate
    POST {{API_BASE_URL}}/ingest/sales-daily
    Content-Type: application/json

    {
      "records": [
        {
          "date": "2024-01-15",
          "store_code": "S001",
          "sku": "SKU-001",
          "quantity": 15,
          "unit_price": 9.99,
          "total_amount": 149.85
        }
      ]
    }

    ### Expected Response:
    # {
    #   "inserted_count": 0,
    #   "updated_count": 1,
    #   "rejected_count": 0,
    #   "total_processed": 1,
    #   "errors": [],
    #   "duration_ms": 32.15
    # }

    ### Ingest Sales Daily - Partial Success
    POST {{API_BASE_URL}}/ingest/sales-daily
    Content-Type: application/json

    {
      "records": [
        {
          "date": "2024-01-15",
          "store_code": "S001",
          "sku": "SKU-001",
          "quantity": 10,
          "unit_price": 9.99,
          "total_amount": 99.90
        },
        {
          "date": "2024-01-15",
          "store_code": "UNKNOWN",
          "sku": "SKU-001",
          "quantity": 5,
          "unit_price": 9.99,
          "total_amount": 49.95
        }
      ]
    }

    ### Expected Response:
    # {
    #   "inserted_count": 1,
    #   "updated_count": 0,
    #   "rejected_count": 1,
    #   "total_processed": 2,
    #   "errors": [
    #     {
    #       "row_index": 1,
    #       "store_code": "UNKNOWN",
    #       "sku": "SKU-001",
    #       "date": "2024-01-15",
    #       "error_code": "UNKNOWN_STORE",
    #       "error_message": "Store code 'UNKNOWN' not found"
    #     }
    #   ],
    #   "duration_ms": 38.45
    # }
    ```
  VALIDATION:
    - ls -la examples/api/ingest_sales_daily.http

Task 12: Create feature-specific test fixtures
  FILE: app/features/ingest/tests/conftest.py
  IMPLEMENT:
    - sample_ingest_row fixture
    - sample_ingest_request fixture
    - mock_key_resolver fixture for unit tests
  VALIDATION:
    - uv run pytest app/features/ingest/tests/ --collect-only

Task 13: Final validation - Run all quality gates
  COMMANDS:
    - uv run ruff check app/features/ingest/ --fix
    - uv run ruff format app/features/ingest/
    - uv run mypy app/features/ingest/
    - uv run pyright app/features/ingest/
    - uv run pytest app/features/ingest/tests/ -v
    - docker-compose up -d && sleep 5
    - uv run alembic upgrade head
    - uv run pytest app/features/ingest/tests/ -v -m integration
    - docker-compose down
```

### Integration Points

```yaml
DATABASE:
  - No new migrations required (uses existing SalesDaily, Store, Product tables)
  - Uses existing grain constraint: uq_sales_daily_grain(date, store_id, product_id)

CONFIG:
  - MODIFY: app/core/config.py
  - ADD: INGEST_BATCH_SIZE (default: 1000)
  - ADD: INGEST_TIMEOUT_SECONDS (default: 60)

ROUTES:
  - MODIFY: app/main.py
  - ADD: app.include_router(ingest_router)
  - ENDPOINT: POST /ingest/sales-daily

DEPENDENCIES:
  - Store table must have stores with matching codes
  - Product table must have products with matching SKUs
  - Calendar table must have entries for dates in payload (FK constraint)
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run FIRST - fix any errors before proceeding
uv run ruff check app/features/ingest/ --fix
uv run ruff format app/features/ingest/

# Expected: No errors
```

### Level 2: Type Checking

```bash
# Run SECOND - type safety is non-negotiable
uv run mypy app/features/ingest/
uv run pyright app/features/ingest/

# Expected: 0 errors, 0 warnings
```

### Level 3: Unit Tests

```bash
# Run THIRD - verify schemas and service logic
uv run pytest app/features/ingest/tests/test_schemas.py -v
uv run pytest app/features/ingest/tests/test_service.py -v

# Expected: All tests pass
```

### Level 4: Integration Tests

```bash
# Run FOURTH - verify API and database behavior
docker-compose up -d
sleep 5
uv run alembic upgrade head

# Seed test data (stores, products, calendar)
uv run python examples/seed_demo_data.py

# Run integration tests
uv run pytest app/features/ingest/tests/test_routes.py -v -m integration

docker-compose down

# Expected: All tests pass
```

### Level 5: Manual API Test

```bash
# Start API server
uv run uvicorn app.main:app --reload --port 8123

# In another terminal, test endpoint
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

# Expected: {"inserted_count":1,"updated_count":0,"rejected_count":0,...}
```

---

## Final Validation Checklist

- [ ] `uv run ruff check app/features/ingest/` passes with no errors
- [ ] `uv run ruff format --check app/features/ingest/` passes
- [ ] `uv run mypy app/features/ingest/` passes with 0 errors
- [ ] `uv run pyright app/features/ingest/` passes with 0 errors
- [ ] `uv run pytest app/features/ingest/tests/test_schemas.py -v` all tests pass
- [ ] `uv run pytest app/features/ingest/tests/test_service.py -v` all tests pass
- [ ] `uv run pytest app/features/ingest/tests/test_routes.py -v -m integration` all tests pass
- [ ] POST /ingest/sales-daily returns correct response structure
- [ ] Replay same payload = updated_count > 0, no duplicates in DB
- [ ] Unknown store_code returns UNKNOWN_STORE error for that row
- [ ] Unknown sku returns UNKNOWN_PRODUCT error for that row
- [ ] Valid rows processed despite invalid rows in same batch
- [ ] Logs follow `ingest.{component}.{action}_{state}` naming convention
- [ ] Duration tracked in response and logs
- [ ] `examples/api/ingest_sales_daily.http` created with examples

---

## Anti-Patterns to Avoid

- ❌ **Don't** fail entire batch on one bad row — use partial success pattern
- ❌ **Don't** use `session.add()` for bulk inserts — use `pg_insert().values()`
- ❌ **Don't** resolve keys one-by-one — batch lookup with `WHERE code IN (...)`
- ❌ **Don't** skip calendar FK validation — dates must exist in calendar table
- ❌ **Don't** use float for money — use `Decimal` with explicit precision
- ❌ **Don't** hardcode batch sizes — make configurable via Settings
- ❌ **Don't** catch generic `Exception` and hide errors — log and re-raise appropriately
- ❌ **Don't** skip type hints — strict mypy/pyright enforcement
- ❌ **Don't** use sync DB operations — all database calls must be async

---

## Confidence Score: 8/10

**Rationale:**

- (+) Clear endpoint contract with natural key → ID resolution
- (+) Idempotent upsert pattern well-documented for PostgreSQL
- (+) Partial success pattern handles mixed valid/invalid rows
- (+) Follows existing codebase patterns (vertical slice, schemas, logging)
- (+) Comprehensive test strategy (unit + integration)
- (+) Type-safe throughout with Pydantic v2 and SQLAlchemy 2.0
- (+) Configurable batch size and timeout
- (-) Calendar FK constraint requires calendar entries to exist (may need seeding)
- (-) Accurate inserted vs updated count requires additional logic (xmax trick or two-phase)
- (-) Large batch performance (>10k rows) may need staging table optimization (YAGNI for now)

**Recommended Approach:**

1. Execute tasks 1-3 (directory structure, config, schemas)
2. Run type checkers after each file
3. Execute tasks 4-6 (service, routes)
4. Run unit tests
5. Execute task 7 (register router)
6. Execute tasks 8-10 (all tests)
7. Execute tasks 11-12 (examples, fixtures)
8. Run full validation loop

---

## Version

- **PRP Version:** 1.0
- **Target INITIAL:** INITIAL-3.md (Ingest Layer)
- **Created:** 2026-01-26
- **Author:** Claude Code

---

## References

### SQLAlchemy 2.0
- [PostgreSQL Dialect - INSERT ON CONFLICT](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert)
- [ORM-Enabled INSERT/UPDATE/DELETE](https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html)

### PostgreSQL
- [INSERT Statement with ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html)
- [PostgreSQL Upsert Guide](https://www.dbvis.com/thetable/postgresql-upsert-insert-on-conflict-guide/)

### FastAPI + asyncpg
- [FastAPI SQLAlchemy asyncpg Example](https://github.com/grillazz/fastapi-sqlalchemy-asyncpg)
- [Building High-Performance Async APIs](https://leapcell.io/blog/building-high-performance-async-apis-with-fastapi-sqlalchemy-2-0-and-asyncpg)

### Pydantic v2
- [Field Validators](https://docs.pydantic.dev/latest/concepts/validators/)

### Performance Optimization (Future)
- [Staging Tables for Faster Bulk Upserts](https://overflow.no/blog/2025/1/5/using-staging-tables-for-faster-bulk-upserts-with-python-and-postgresql/)
