# Phase 1: Data Platform

**Status**: In Progress
**PRP Reference**: `PRPs/PRP-2-data-platform-schema.md`
**Branch**: `feat/prp-2-data-platform-schema`
**PR**: #12

---

## Executive Summary

Phase 1 implements the data platform for ForecastLabAI - a mini-warehouse schema for retail demand forecasting. This phase creates 7 SQLAlchemy 2.0 ORM models following star schema patterns with strict type safety, grain protection, and data quality constraints.

---

## Objectives

### Primary Goals
1. Create dimension tables (Store, Product, Calendar)
2. Create fact tables (SalesDaily, PriceHistory, Promotion, InventorySnapshotDaily)
3. Enforce data grain via unique constraints for idempotent upserts
4. Add check constraints for data quality
5. Create composite indexes for common query patterns
6. Provide Pydantic v2 schemas for API validation
7. Comprehensive test coverage (unit + integration)

### Design Principles Applied
- **Star Schema**: Dimension and fact table separation
- **Grain Protection**: Unique constraints prevent duplicate rows
- **Type Safety**: SQLAlchemy 2.0 `Mapped[]` type annotations
- **Data Quality**: Check constraints at database level
- **Query Performance**: Composite indexes for time-range queries

---

## Deliverables

### 1. ORM Models (`app/features/data_platform/models.py`)

#### Dimension Tables

| Table | Primary Key | Unique Constraint | Purpose |
|-------|-------------|-------------------|---------|
| `store` | id | code | Retail store locations |
| `product` | id | sku | Product catalog |
| `calendar` | date | - | Time dimension with holiday flags |

#### Fact Tables

| Table | Grain | Purpose |
|-------|-------|---------|
| `sales_daily` | (date, store_id, product_id) | Daily sales aggregates |
| `price_history` | - | Price validity windows |
| `promotion` | - | Promotional campaigns |
| `inventory_snapshot_daily` | (date, store_id, product_id) | End-of-day inventory levels |

### 2. Pydantic Schemas (`app/features/data_platform/schemas.py`)

Base and response schemas for each model:
- `StoreBase`, `StoreCreate`, `StoreResponse`
- `ProductBase`, `ProductCreate`, `ProductResponse`
- `CalendarBase`, `CalendarCreate`, `CalendarResponse`
- `SalesDailyBase`, `SalesDailyCreate`, `SalesDailyResponse`
- `PriceHistoryBase`, `PriceHistoryCreate`, `PriceHistoryResponse`
- `PromotionBase`, `PromotionCreate`, `PromotionResponse`
- `InventorySnapshotDailyBase`, `InventorySnapshotDailyCreate`, `InventorySnapshotDailyResponse`

All schemas use `ConfigDict(from_attributes=True)` for ORM compatibility.

### 3. Database Migration

**File**: `alembic/versions/e1165ebcef61_create_data_platform_tables.py`

Creates all 7 tables with:
- Primary keys and foreign keys
- Unique constraints for grain protection
- Check constraints for data quality
- Composite indexes for query performance

---

## Database Schema Details

### Store Dimension

```python
class Store(TimestampMixin, Base):
    __tablename__ = "store"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    city: Mapped[str | None] = mapped_column(String(50), nullable=True)
    store_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
```

### Product Dimension

```python
class Product(TimestampMixin, Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    base_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    base_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
```

### Calendar Dimension

```python
class Calendar(TimestampMixin, Base):
    __tablename__ = "calendar"

    date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0=Monday, 6=Sunday
    month: Mapped[int] = mapped_column(Integer)
    quarter: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer, index=True)
    is_holiday: Mapped[bool] = mapped_column(Boolean, default=False)
    holiday_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        CheckConstraint("day_of_week >= 0 AND day_of_week <= 6"),
        CheckConstraint("month >= 1 AND month <= 12"),
        CheckConstraint("quarter >= 1 AND quarter <= 4"),
    )
```

### SalesDaily Fact

```python
class SalesDaily(TimestampMixin, Base):
    __tablename__ = "sales_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, ForeignKey("calendar.date"))
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("store.id"))
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("product.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    __table_args__ = (
        UniqueConstraint("date", "store_id", "product_id", name="uq_sales_daily_grain"),
        Index("ix_sales_daily_date_store", "date", "store_id"),
        Index("ix_sales_daily_date_product", "date", "product_id"),
        CheckConstraint("quantity >= 0"),
        CheckConstraint("unit_price >= 0"),
        CheckConstraint("total_amount >= 0"),
    )
```

---

## Test Coverage

### Unit Tests (`app/features/data_platform/tests/test_models.py`)

| Test Class | Tests | Coverage |
|------------|-------|----------|
| `TestStoreModel` | 4 | Tablename, columns, unique constraint, relationships |
| `TestProductModel` | 4 | Tablename, columns, unique constraint, relationships |
| `TestCalendarModel` | 4 | Tablename, columns, check constraints, relationships |
| `TestSalesDailyModel` | 5 | Columns, grain constraint, FKs, checks, relationships |
| `TestPriceHistoryModel` | 4 | Tablename, validity dates, checks, nullable store_id |
| `TestPromotionModel` | 4 | Tablename, discount fields, dates, checks |
| `TestInventorySnapshotDailyModel` | 4 | Tablename, columns, grain constraint, checks |

**Total Unit Tests**: 32

### Integration Tests (`app/features/data_platform/tests/test_constraints.py`)

| Test | Purpose |
|------|---------|
| `test_store_code_unique_constraint` | Verify store code uniqueness at DB level |
| `test_product_sku_unique_constraint` | Verify SKU uniqueness at DB level |
| `test_calendar_check_constraints` | Verify calendar value ranges |
| `test_sales_daily_grain_constraint` | Verify grain protection prevents duplicates |
| `test_sales_daily_positive_quantity` | Verify quantity check constraint |
| `test_price_history_valid_dates` | Verify valid_to >= valid_from |
| `test_promotion_valid_dates` | Verify end_date >= start_date |
| `test_promotion_discount_pct_range` | Verify discount percentage 0-1 range |
| `test_inventory_grain_constraint` | Verify inventory grain protection |
| `test_inventory_positive_quantities` | Verify positive quantity checks |
| `test_cascade_relationships` | Verify FK relationships work correctly |

**Total Integration Tests**: 11

---

## Validation Results

### Ruff (Linting + Formatting)
```
All checks passed!
```

### MyPy (Static Type Checking)
```
Success: no issues found in 25 source files
```

### Pyright (Static Type Checking)
```
0 errors, 0 warnings, 0 informations
```

### Pytest
```
58 passed (14 core + 32 unit + 11 integration + 1 fixture)
```

---

## Directory Structure

```
app/features/data_platform/
├── __init__.py
├── models.py           # 7 ORM models (309 lines)
├── schemas.py          # Pydantic validation schemas
└── tests/
    ├── __init__.py
    ├── conftest.py     # db_session fixture
    ├── test_models.py  # Unit tests (32 tests)
    └── test_constraints.py  # Integration tests (11 tests)

alembic/versions/
└── e1165ebcef61_create_data_platform_tables.py  # Baseline migration

examples/
├── schema/
│   └── README.md       # Table documentation
└── queries/
    ├── kpi_sales.sql   # Sales KPI query examples
    └── exog_join.sql   # Exogenous signal join patterns
```

---

## Examples

### Example: Sales KPI Query

```sql
-- examples/queries/kpi_sales.sql
SELECT
    c.year,
    c.month,
    s.region,
    p.category,
    SUM(sd.quantity) as total_units,
    SUM(sd.total_amount) as total_revenue
FROM sales_daily sd
JOIN calendar c ON sd.date = c.date
JOIN store s ON sd.store_id = s.id
JOIN product p ON sd.product_id = p.id
WHERE c.year = 2024
GROUP BY c.year, c.month, s.region, p.category
ORDER BY c.year, c.month, total_revenue DESC;
```

### Example: Exogenous Signal Join

```sql
-- examples/queries/exog_join.sql
SELECT
    sd.date,
    sd.store_id,
    sd.product_id,
    sd.quantity,
    sd.total_amount,
    ph.price as current_price,
    pr.discount_pct,
    inv.on_hand_qty,
    inv.is_stockout,
    c.is_holiday
FROM sales_daily sd
JOIN calendar c ON sd.date = c.date
LEFT JOIN price_history ph ON
    ph.product_id = sd.product_id
    AND (ph.store_id = sd.store_id OR ph.store_id IS NULL)
    AND sd.date >= ph.valid_from
    AND (ph.valid_to IS NULL OR sd.date <= ph.valid_to)
LEFT JOIN promotion pr ON
    pr.product_id = sd.product_id
    AND (pr.store_id = sd.store_id OR pr.store_id IS NULL)
    AND sd.date BETWEEN pr.start_date AND pr.end_date
LEFT JOIN inventory_snapshot_daily inv ON
    inv.date = sd.date
    AND inv.store_id = sd.store_id
    AND inv.product_id = sd.product_id;
```

---

## Next Phase Preparation

Phase 1 provides the foundation for:

1. **Phase 2 (Ingest Layer)**: Idempotent upsert endpoints using `ON CONFLICT` with the grain constraints
2. **Phase 3 (Feature Engineering)**: Time-safe features using the calendar dimension
3. **Phase 4 (Forecasting)**: Model training on `sales_daily` data
4. **Phase 5 (Backtesting)**: Time-based splits using calendar dates

---

## Lessons Learned

1. **Date Type Shadowing**: Using `from datetime import date` causes pyright errors when defining `date` columns. Solution: Use `import datetime` and `datetime.date` type.

2. **Fixture Discovery**: pytest fixtures in `tests/conftest.py` aren't auto-discovered by tests in `app/features/*/tests/`. Solution: Add fixtures to feature-specific conftest.py files.

3. **Grain Protection**: Use `UniqueConstraint` not just `Index(unique=True)` for proper `ON CONFLICT` upsert support.

---

## References

- [PRP-2: Data Platform Schema](../../PRPs/PRP-2-data-platform-schema.md)
- [Architecture Overview](../ARCHITECTURE.md)
- [Schema Documentation](../../examples/schema/README.md)
- [Query Examples](../../examples/queries/)
