# Data model

The twenty-three tables, grouped by the slice that owns them, and how they relate.

**Purpose:** read or query the database without reverse-engineering it from ORM classes.
**Intended reader:** integrators querying directly, or adding a schema change.

## What you'll accomplish

A map of what is stored where, and which tables feed which features.

## Ownership

Every table belongs to exactly one slice, defined in that slice's `models.py`. Nothing is shared-write across slices — a slice that needs another's data goes through its service, not its tables.

## The retail core — `data_platform` (10 tables)

The warehouse the whole system forecasts over.

| Table | Holds |
|---|---|
| `store` | Retail locations — region, store type. |
| `product` | SKUs — category, brand. |
| `calendar` | The date dimension: day-of-week, month, holiday flags. |
| `sales_daily` | **The fact table.** Daily units and revenue per (store, product). |
| `price_history` | Price level over time. |
| `promotion` | Promotional periods and their kind. |
| `inventory_snapshot_daily` | Daily on-hand stock per (store, product). |
| `replenishment_event` | Inbound stock arrivals. |
| `sales_returns` | Return events. |
| `exogenous_signal` | External drivers — weather, macro indicators. |

`sales_daily` at the **(store, product, date)** grain is the spine. Everything else either describes an entity (`store`, `product`, `calendar`) or explains a movement in it.

### These tables are the feature packs

The last six map directly onto V2 feature packs, which is the practical reason to care about them:

| Table | Feeds pack |
|---|---|
| `price_history`, `promotion` | `price_promo` |
| `inventory_snapshot_daily` | `inventory` |
| `replenishment_event` | `replenishment` |
| `sales_returns` | `returns` |
| `exogenous_signal` | `exogenous_weather`, `exogenous_macro` |

**A pack whose table was never populated contributes nothing.** Enabling `inventory` against a dataset seeded without inventory dynamics adds empty columns, not signal. This is why the five sidecar packs are off by default — see [Forecasting](../analyst/forecasting.md).

## Modelling and orchestration

| Table | Slice | Holds |
|---|---|---|
| `job` | `jobs` | One async unit of work: type, params, status, result JSON, error, linked run. |
| `batch_job` | `batch` | A matrix submission. |
| `batch_job_item` | `batch` | One expanded child of a batch. |
| `model_run` | `registry` | **One training execution**: config, metrics, artifact location, status. |
| `deployment_alias` | `registry` | A movable pointer to one successful run. |
| `model_selection_run` | `model_selection` | One champion-selector comparison. |
| `model_selection_candidate` | `model_selection` | One candidate within a comparison, with its backtest result. |
| `scenario_plan` | `scenarios` | A saved what-if plan and its assumptions. |
| `forecast_explanation` | `explainability` | Stored forecast explanations. |
| `showcase_workspace` | `demo` | Saved showcase workspace state. |

### `model_run` is the centre of gravity

Nearly every question about "what happened" resolves to a `model_run` row: what was trained, at what grain, over which data window, with which configuration and seed, scoring what, backed by which artifact and checksum.

Two facts about it are easy to get wrong:

- **`model_family` is not a column.** It is computed from `model_type` at response time by `app/shared/model_taxonomy.py`. Querying the table for a family means filtering on the model types that map to it.
- **`feature_frame_version` may be absent on older rows.** Runs predating the field default to V1 for comparability purposes.

A run's lifecycle is `pending → running → success`, or `failed`. An alias may point **only** at a successful run.

## Conversational

| Table | Slice | Holds |
|---|---|---|
| `document_source` | `rag` | An indexed document: path and content hash. |
| `document_chunk` | `rag` | A chunk with its **pgvector** embedding. |
| `agent_session` | `agents` | One conversation with its message history and state. |

`document_source` carries the content hash that makes indexing idempotent: same path, same hash → nothing to do.

`document_chunk.embedding` is a **fixed-width** pgvector column sized by `rag_embedding_dimension`. Changing embedding model to one with a different width is therefore a **migration plus a full re-index**, not a settings change. This is the single most common RAG configuration mistake — see [Troubleshooting](../troubleshooting.md).

`agent_session` is where the `awaiting_approval` state lives when the human-in-the-loop gate pauses an agent.

## Configuration

| Table | Slice | Holds |
|---|---|---|
| `app_config` | `config` | Persisted runtime setting overrides. |

This is what makes **Admin → AI models** changes survive a restart: overrides are written here and re-applied onto the `Settings` singleton at startup by `apply_overrides_on_startup`. It is the only table that can change application behavior without a redeploy, and it holds provider API keys — which is why `GET /config/ai` always masks them.

## Migrations

Schema lives in `alembic/versions/`. Three rules:

1. **Every schema change ships a migration.** No implicit table creation.
2. **Migrations are forward-only once merged.** Editing a merged migration is forbidden — add a new one.
3. **Run `uv run alembic upgrade head` after every pull.** A missed migration surfaces as `relation "…" does not exist`.

The database is PostgreSQL 16 with the **pgvector** extension (`pgvector/pgvector:pg16`), which the RAG tables require.

## Querying directly

```bash
psql postgresql://forecastlab:forecastlab@localhost:5433/forecastlab
```

Read-only exploration is fine. Writing directly is not: it bypasses Pydantic validation, the service-layer invariants, and the registry's artifact bookkeeping. A hand-written `model_run` row with no verifiable artifact will pass a metrics display and fail the promotion gate.

Note also that all application access is **async** SQLAlchemy with parameter binding. Building SQL by string concatenation is forbidden repository-wide.

## Next

- [Artifacts and the registry](artifacts-and-registry.md) — what lives on disk beside these rows.
- [Extending ForecastLabAI](extending.md) — adding a table safely.
