# Phase 2: Ingest Layer

**Status**: Completed
**PRP Reference**: `PRPs/PRP-3-ingest-layer.md`
**Date Completed**: 2026-01-26
**Branch**: `feat/prp-3-ingest-layer`

---

## Executive Summary

Phase 2 implements the ingest layer for ForecastLabAI - a typed, idempotent batch upsert endpoint for sales data. The primary endpoint `POST /ingest/sales-daily` accepts sales records with natural keys (`store_code`, `sku`) and performs replay-safe upserts using PostgreSQL's `ON CONFLICT DO UPDATE`.

---

## Objectives

### Primary Goals
1. Create batch upsert endpoint for sales_daily data
2. Implement natural key resolution (store_code -> store_id, sku -> product_id)
3. Enforce idempotency using PostgreSQL ON CONFLICT DO UPDATE
4. Support partial success (valid rows processed, invalid rows returned with errors)
5. Validate calendar dates exist (FK constraint)
6. Provide structured logging with duration metrics
7. Add configurable batch size and timeout settings

### Design Principles Applied
- **KISS**: Simple key resolution without premature caching optimization
- **YAGNI**: Single endpoint for sales_daily, no staging table optimization yet
- **Partial Success**: Don't fail entire batch on one bad row
- **Type Safety**: Strict Pydantic v2 schemas with Decimal for monetary values

---

## Deliverables

### 1. API Endpoint

#### POST /ingest/sales-daily

Batch upsert daily sales records using natural keys.

**Request Body:**
```json
{
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
}
```

**Response Body:**
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

**Validation Rules:**
- `records` array: 1-10,000 items
- `store_code`: 1-20 characters
- `sku`: 1-50 characters
- `quantity`: non-negative integer
- `unit_price`: non-negative decimal (2 decimal places)
- `total_amount`: non-negative decimal (2 decimal places)

**Error Codes:**
| Code | Description |
|------|-------------|
| `UNKNOWN_STORE` | Store code not found in database |
| `UNKNOWN_PRODUCT` | SKU not found in database |
| `UNKNOWN_DATE` | Date not found in calendar table |

---

### 2. Pydantic Schemas (`app/features/ingest/schemas.py`)

```python
class SalesDailyIngestRow(BaseModel):
    """Single row in sales daily ingest payload."""
    date: date_type
    store_code: str = Field(..., min_length=1, max_length=20)
    sku: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., ge=0)
    unit_price: Decimal = Field(..., ge=0, decimal_places=2)
    total_amount: Decimal = Field(..., ge=0, decimal_places=2)

class SalesDailyIngestRequest(BaseModel):
    """Request body for POST /ingest/sales-daily."""
    records: list[SalesDailyIngestRow] = Field(
        ..., min_length=1, max_length=10000
    )

class IngestRowError(BaseModel):
    """Error detail for a single rejected row."""
    row_index: int
    store_code: str
    sku: str
    date: date_type
    error_code: str
    error_message: str

class SalesDailyIngestResponse(BaseModel):
    """Response body for POST /ingest/sales-daily."""
    processed_count: int = Field(..., ge=0)
    rejected_count: int = Field(..., ge=0)
    total_received: int = Field(..., ge=0)
    errors: list[IngestRowError] = Field(default_factory=list)
    duration_ms: float = Field(..., ge=0)
```

---

### 3. Service Layer (`app/features/ingest/service.py`)

#### KeyResolver Class

Resolves natural keys to internal database IDs:

```python
class KeyResolver:
    async def resolve_store_codes(
        self, db: AsyncSession, codes: set[str]
    ) -> dict[str, int]:
        """Resolve store codes to store IDs."""
        stmt = select(Store.code, Store.id).where(Store.code.in_(codes))
        result = await db.execute(stmt)
        return {row.code: row.id for row in result}

    async def resolve_skus(
        self, db: AsyncSession, skus: set[str]
    ) -> dict[str, int]:
        """Resolve SKUs to product IDs."""
        stmt = select(Product.sku, Product.id).where(Product.sku.in_(skus))
        result = await db.execute(stmt)
        return {row.sku: row.id for row in result}

    async def resolve_dates(
        self, db: AsyncSession, dates: set[date_type]
    ) -> set[date_type]:
        """Check which dates exist in the calendar table."""
        stmt = select(Calendar.date).where(Calendar.date.in_(dates))
        result = await db.execute(stmt)
        return {row.date for row in result}
```

#### upsert_sales_daily_batch Function

Performs idempotent upsert with partial success handling:

```python
async def upsert_sales_daily_batch(
    db: AsyncSession,
    records: list[SalesDailyIngestRow],
    key_resolver: KeyResolverProtocol,
) -> UpsertResult:
    """Upsert sales daily records with key resolution and partial success."""
    # 1. Extract unique codes, SKUs, and dates
    # 2. Resolve all keys in batch
    # 3. Validate and prepare rows (collect errors for invalid)
    # 4. Perform upsert using pg_insert().on_conflict_do_update()
    # 5. Return UpsertResult with counts and errors
```

**PostgreSQL Upsert Pattern:**
```python
insert_stmt = pg_insert(SalesDaily).values(valid_rows)
upsert_stmt = insert_stmt.on_conflict_do_update(
    index_elements=["date", "store_id", "product_id"],
    set_={
        "quantity": insert_stmt.excluded.quantity,
        "unit_price": insert_stmt.excluded.unit_price,
        "total_amount": insert_stmt.excluded.total_amount,
        "updated_at": func.now(),
    },
)
await db.execute(upsert_stmt)
```

---

### 4. Configuration (`app/core/config.py`)

Added ingest-specific settings:

```python
class Settings(BaseSettings):
    # ... existing settings ...

    # Ingest
    ingest_batch_size: int = 1000
    ingest_timeout_seconds: int = 60
```

| Setting | Default | Description |
|---------|---------|-------------|
| `INGEST_BATCH_SIZE` | 1000 | Max rows per upsert batch |
| `INGEST_TIMEOUT_SECONDS` | 60 | Request timeout for ingest |

---

### 5. Logging Events

Following the `{domain}.{component}.{action}_{state}` naming convention:

| Event | Level | Context |
|-------|-------|---------|
| `ingest.sales_daily.request_received` | INFO | record_count |
| `ingest.sales_daily.upsert_started` | INFO | batch_size |
| `ingest.sales_daily.upsert_completed` | INFO | processed, rejected, total_valid |
| `ingest.sales_daily.request_completed` | INFO | processed, rejected, duration_ms |
| `ingest.sales_daily.request_failed` | ERROR | error, error_type, exc_info |

---

## Directory Structure

```
app/features/ingest/
├── __init__.py
├── routes.py           # POST /ingest/sales-daily endpoint
├── schemas.py          # Pydantic request/response schemas
├── service.py          # KeyResolver + upsert_sales_daily_batch
└── tests/
    ├── __init__.py
    ├── conftest.py     # Feature-specific fixtures
    ├── test_schemas.py # Schema validation tests
    ├── test_service.py # Service logic tests
    └── test_routes.py  # Integration tests

examples/api/
└── ingest_sales_daily.http  # HTTP client examples
```

---

## Examples

### Example: Happy Path Ingest

```bash
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
```

Response:
```json
{
  "processed_count": 1,
  "rejected_count": 0,
  "total_received": 1,
  "errors": [],
  "duration_ms": 32.15
}
```

### Example: Idempotent Replay

Running the same request twice updates (not duplicates) due to ON CONFLICT:

```bash
# First request: inserts row
# Second request: updates row (same grain)
# Result: 1 row in database, not 2
```

### Example: Partial Success

```json
{
  "records": [
    {"date": "2024-01-15", "store_code": "S001", "sku": "SKU-001", ...},
    {"date": "2024-01-15", "store_code": "INVALID", "sku": "SKU-001", ...}
  ]
}
```

Response:
```json
{
  "processed_count": 1,
  "rejected_count": 1,
  "total_received": 2,
  "errors": [
    {
      "row_index": 1,
      "store_code": "INVALID",
      "sku": "SKU-001",
      "date": "2024-01-15",
      "error_code": "UNKNOWN_STORE",
      "error_message": "Store code 'INVALID' not found"
    }
  ],
  "duration_ms": 38.45
}
```

---

## Key Design Decisions

### 1. Natural Keys in Request

**Decision**: Accept `store_code` and `sku` instead of internal IDs.

**Rationale**: External systems (POS, ERP) don't know internal database IDs. Natural keys provide a stable interface that doesn't require ID lookups before ingestion.

### 2. Batch Key Resolution

**Decision**: Resolve all store codes, SKUs, and dates in three batch queries upfront.

**Rationale**: Avoids N+1 queries. For 1000 records with 10 unique stores and 50 unique SKUs, this is 3 queries instead of potentially 2000.

### 3. Calendar FK Validation

**Decision**: Reject rows with dates not in the calendar table.

**Rationale**: The `sales_daily.date` column has a FK to `calendar.date`. Rather than auto-create calendar entries (which could mask data issues), we reject and report the error.

### 4. Partial Success Pattern

**Decision**: Process valid rows even when some rows fail validation.

**Rationale**: In real-world batch processing, failing an entire 10,000 row batch because of one bad row is unacceptable. Report errors but process what's valid.

### 5. No Insert/Update Count Distinction

**Decision**: Report `processed_count` without distinguishing inserts from updates.

**Rationale**: PostgreSQL's ON CONFLICT doesn't easily distinguish inserts from updates without additional complexity (checking xmax). The important metric is "rows successfully written."

---

## Integration Points

```yaml
DATABASE:
  - No new migrations required
  - Uses existing SalesDaily, Store, Product, Calendar tables
  - Relies on grain constraint: uq_sales_daily_grain(date, store_id, product_id)

CONFIG:
  - app/core/config.py: Added INGEST_BATCH_SIZE, INGEST_TIMEOUT_SECONDS

ROUTES:
  - app/main.py: Registered ingest_router
  - Endpoint: POST /ingest/sales-daily

DEPENDENCIES:
  - Store table must have stores with matching codes
  - Product table must have products with matching SKUs
  - Calendar table must have entries for dates in payload
```

---

## Next Phase Preparation

Phase 2 provides the foundation for:

1. **Phase 3 (Feature Engineering)**: With sales data ingested, compute time-safe features (lags, rolling windows)
2. **Phase 4 (Forecasting)**: Train models on ingested sales_daily data
3. **Phase 5 (Backtesting)**: Ingest historical data for backtesting experiments
4. **Future Ingest Endpoints**: Same pattern can be extended for price_history, promotion, inventory_snapshot_daily

---

## Lessons Learned

1. **PostgreSQL Dialect Import**: Must use `from sqlalchemy.dialects.postgresql import insert as pg_insert` for ON CONFLICT support, not generic SQLAlchemy insert.

2. **Index Elements vs Constraint Name**: `on_conflict_do_update()` requires `index_elements=["date", "store_id", "product_id"]` (column names), not the constraint name.

3. **Rowcount Type Stubs**: SQLAlchemy's generic Result type doesn't expose `rowcount` in type stubs, but it's available at runtime for DML operations. Required type ignore comment.

4. **Decimal for Money**: Always use `Decimal` with explicit `decimal_places` for monetary values to avoid floating point precision issues.

---

## References

- [PRP-3: Ingest Layer](../../PRPs/PRP-3-ingest-layer.md)
- [Phase 1: Data Platform](./1-DATA_PLATFORM.md) - Schema foundation
- [SQLAlchemy PostgreSQL INSERT ON CONFLICT](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert)
- [HTTP Client Examples](../../examples/api/ingest_sales_daily.http)
