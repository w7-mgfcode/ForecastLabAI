# INITIAL-2.md — Data Platform: Schema + Migrations

## FEATURE:
- Mini-warehouse schema enabling forecasting with exogenous drivers:
  - Dimensions: `store`, `product`, `calendar`
  - Facts: `sales_daily` (required), `price_history`, `promotion`, `inventory_snapshot_daily`
  - Optional: `sales_txn`, `weather_daily`, `traffic_daily`
- Alembic migrations:
  - baseline migration (minimum viable tables)
  - indexes + unique constraints (grain protection)
- Postgres-first design (while keeping code reasonably portable).

## EXAMPLES:
- `examples/schema/README.md` — table grains + keys + rationale.
- `examples/queries/kpi_sales.sql` — KPI query shapes.
- `examples/queries/exog_join.sql` — join pattern: sales + price/promo/inventory.

## DOCUMENTATION:
- Postgres constraints/indexing
- Alembic autogenerate + revision workflow
- SQLModel/SQLAlchemy modeling conventions

## OTHER CONSIDERATIONS:
- Explicit grain: `sales_daily` unique key = (date, store_id, product_id).
- Avoid “everything in JSON”: JSONB only where justified (e.g., model_config).
- Index strategy optimized for time-range + store/product filtering.
