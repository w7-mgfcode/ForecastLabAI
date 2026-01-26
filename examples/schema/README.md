# ForecastLabAI Data Platform Schema

## Overview

The data platform implements a mini-warehouse schema optimized for retail demand forecasting.
It follows a star schema pattern with dimension and fact tables.

## Dimension Tables

### store
- **Primary Key**: `id` (surrogate)
- **Business Key**: `code` (unique)
- **Purpose**: Store locations and attributes

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Surrogate primary key |
| code | VARCHAR(20) | Unique store code |
| name | VARCHAR(100) | Store display name |
| region | VARCHAR(50) | Geographic region |
| city | VARCHAR(50) | City location |
| store_type | VARCHAR(30) | Store format |

### product
- **Primary Key**: `id` (surrogate)
- **Business Key**: `sku` (unique)
- **Purpose**: Product catalog

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Surrogate primary key |
| sku | VARCHAR(50) | Stock keeping unit |
| name | VARCHAR(200) | Product name |
| category | VARCHAR(100) | Product category |
| brand | VARCHAR(100) | Product brand |
| base_price | NUMERIC(10,2) | Standard retail price |
| base_cost | NUMERIC(10,2) | Standard cost/COGS |

### calendar
- **Primary Key**: `date` (natural key)
- **Purpose**: Time dimension for date-based analysis

| Column | Type | Description |
|--------|------|-------------|
| date | DATE | Calendar date (primary key) |
| day_of_week | INTEGER | 0=Monday, 6=Sunday |
| month | INTEGER | Month (1-12) |
| quarter | INTEGER | Quarter (1-4) |
| year | INTEGER | Year |
| is_holiday | BOOLEAN | Holiday flag |
| holiday_name | VARCHAR(100) | Holiday name |

## Fact Tables

### sales_daily (REQUIRED)
- **Grain**: One row per (date, store_id, product_id)
- **Purpose**: Daily aggregated sales transactions

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Surrogate primary key |
| date | DATE | Sales date (FK→calendar) |
| store_id | INTEGER | Store (FK→store) |
| product_id | INTEGER | Product (FK→product) |
| quantity | INTEGER | Units sold |
| unit_price | NUMERIC(10,2) | Price per unit |
| total_amount | NUMERIC(12,2) | Total sales amount |

**Critical Constraint**: `UNIQUE(date, store_id, product_id)` ensures grain protection
for idempotent upserts.

### price_history
- **Purpose**: Historical price tracking with validity windows
- **Grain**: One row per (product_id, store_id, valid_from)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Surrogate primary key |
| product_id | INTEGER | Product (FK→product) |
| store_id | INTEGER | Store (FK→store, nullable for chain-wide) |
| price | NUMERIC(10,2) | Price during validity window |
| valid_from | DATE | Start of validity period |
| valid_to | DATE | End of validity period (NULL = current) |

### promotion
- **Purpose**: Promotional campaigns with discount mechanics
- **Grain**: One row per promotion campaign

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Surrogate primary key |
| product_id | INTEGER | Product (FK→product) |
| store_id | INTEGER | Store (FK→store, nullable for chain-wide) |
| name | VARCHAR(200) | Promotion name |
| discount_pct | NUMERIC(5,4) | Discount percentage (0.15 = 15% off) |
| discount_amount | NUMERIC(10,2) | Fixed discount amount |
| start_date | DATE | Promotion start |
| end_date | DATE | Promotion end |

### inventory_snapshot_daily
- **Grain**: One row per (date, store_id, product_id)
- **Purpose**: Daily inventory levels for stockout detection

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Surrogate primary key |
| date | DATE | Snapshot date (FK→calendar) |
| store_id | INTEGER | Store (FK→store) |
| product_id | INTEGER | Product (FK→product) |
| on_hand_qty | INTEGER | Units on hand at end of day |
| on_order_qty | INTEGER | Units on order (incoming) |
| is_stockout | BOOLEAN | True if on_hand_qty = 0 |

**Critical Constraint**: `UNIQUE(date, store_id, product_id)` ensures grain protection.

## Index Strategy

Indexes are optimized for common forecasting query patterns:

1. **Time-range queries**: `ix_sales_daily_date_store`, `ix_sales_daily_date_product`
2. **Dimension lookups**: `ix_store_code`, `ix_product_sku`, `ix_product_category`
3. **Validity windows**: `ix_price_history_product_validity`
4. **Inventory analysis**: `ix_inventory_snapshot_date_store`

## Grain Protection

The `sales_daily` and `inventory_snapshot_daily` tables enforce grain via unique constraints.
This enables:
- **Idempotent upserts**: Re-running ingestion won't create duplicates
- **Data quality**: Prevents accidental double-counting
- **ON CONFLICT support**: PostgreSQL upsert pattern for replay-safe loading

## Data Quality Constraints

All tables include check constraints to ensure data integrity:

- **Calendar**: day_of_week (0-6), month (1-12), quarter (1-4)
- **Sales**: quantity >= 0, unit_price >= 0, total_amount >= 0
- **Inventory**: on_hand_qty >= 0, on_order_qty >= 0
- **Price History**: price >= 0, valid_to >= valid_from (when not NULL)
- **Promotion**: discount_pct in [0,1], discount_amount >= 0, end_date >= start_date

## Relationships

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    Store     │     │   Product    │     │   Calendar   │
│──────────────│     │──────────────│     │──────────────│
│ id (PK)      │     │ id (PK)      │     │ date (PK)    │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────┐
│                     SalesDaily                          │
│─────────────────────────────────────────────────────────│
│ UNIQUE(date, store_id, product_id) ← GRAIN PROTECTION  │
└─────────────────────────────────────────────────────────┘
```

All fact tables (sales_daily, price_history, promotion, inventory_snapshot_daily)
reference the dimension tables via foreign keys.
