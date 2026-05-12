# Data Seeder: The Forge

**The Forge** is ForecastLabAI's randomized database seeder for generating reproducible synthetic test data with realistic time-series patterns.

## Overview

The seeder generates synthetic retail demand data that mimics real-world patterns, enabling:

- **Development**: Populate local databases with realistic test data
- **Testing**: Create deterministic datasets for reproducible test suites
- **Demos**: Generate visually compelling data for demonstrations
- **Benchmarking**: Compare model performance across standardized scenarios

## Architecture

```
app/shared/seeder/
├── __init__.py          # Public exports (DataSeeder, SeederConfig, etc.)
├── config.py            # Configuration dataclasses and scenario presets
├── core.py              # DataSeeder orchestrator class
├── rag_scenario.py      # RAG-specific seeding for knowledge base
├── generators/
│   ├── __init__.py      # Generator exports
│   ├── calendar.py      # CalendarGenerator (dates, holidays)
│   ├── dimensions.py    # StoreGenerator, ProductGenerator
│   ├── facts.py         # SalesDailyGenerator, time-series logic
│   ├── inventory.py     # InventorySnapshotGenerator
│   ├── price.py         # PriceHistoryGenerator
│   ├── product.py       # ProductGenerator with SKU allocation
│   ├── promotions.py    # PromotionGenerator
│   └── store.py         # StoreGenerator with code allocation
└── tests/
    ├── conftest.py      # Test fixtures
    ├── test_config.py   # Configuration tests
    ├── test_core.py     # Orchestrator tests
    ├── test_generators.py  # Generator unit tests
    └── test_integration.py # Full database integration tests
```

## Quick Start

```bash
# 1. Start PostgreSQL
docker-compose up -d

# 2. Apply migrations
uv run alembic upgrade head

# 3. Generate test data
uv run python scripts/seed_random.py --full-new --seed 42 --confirm

# 4. Verify data
uv run python scripts/seed_random.py --status
```

## CLI Reference

### Operations

| Flag | Description |
|------|-------------|
| `--full-new` | Generate complete dataset (dimensions + facts) |
| `--delete` | Delete data (use with `--scope`) |
| `--append` | Append fact data for new date range |
| `--status` | Show current table row counts |
| `--verify` | Validate data integrity |

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `--seed` | 42 | Random seed for reproducibility |
| `--stores` | 10 | Number of stores to generate |
| `--products` | 50 | Number of products to generate |
| `--start-date` | 2024-01-01 | Start of date range |
| `--end-date` | 2024-12-31 | End of date range |
| `--sparsity` | 0.0 | Fraction of missing store/product combinations |
| `--scenario` | — | Pre-built scenario name |
| `--config` | — | Path to YAML configuration file |
| `--scope` | all | Deletion scope: `all`, `facts`, `dimensions` |
| `--batch-size` | 1000 | Records per INSERT statement |

### Safety Flags

| Flag | Description |
|------|-------------|
| `--confirm` | Required for destructive operations |
| `--dry-run` | Preview changes without executing |

## Scenario Presets

Pre-configured scenarios for common testing patterns:

| Scenario | Description | Key Settings |
|----------|-------------|--------------|
| `retail_standard` | Normal retail patterns | Linear trend, 15% noise, 10% promotions |
| `holiday_rush` | Q4 holiday surge | Oct-Dec, exponential trend, 1.8x December multiplier |
| `high_variance` | Noisy, unpredictable | 40% noise, 5% anomalies, 3x anomaly magnitude |
| `stockout_heavy` | Frequent stockouts | 25% stockout probability |
| `new_launches` | Product launch ramps | 100 products, 30-day ramp period |
| `sparse` | Missing data patterns | 50% missing combinations, random gaps |

### Usage

```bash
# Use built-in scenario
uv run python scripts/seed_random.py --full-new --scenario holiday_rush --confirm

# Override scenario parameters
uv run python scripts/seed_random.py --full-new --scenario holiday_rush --stores 20 --confirm
```

## YAML Configuration

For complex scenarios, use YAML configuration files:

```yaml
# examples/seed/config_custom.yaml
dimensions:
  stores:
    count: 15
    regions: ["North", "South", "East", "West", "Central"]
    types: ["supermarket", "express", "warehouse", "online"]
  products:
    count: 100
    categories: ["Beverage", "Snack", "Dairy", "Frozen", "Fresh"]
    brands: ["PremiumCo", "ValueMax", "Generic", "Organic"]

date_range:
  start: "2024-01-01"
  end: "2024-12-31"

time_series:
  base_demand: 100
  trend: "linear"
  trend_slope: 0.001
  weekly_seasonality: [0.8, 0.9, 1.0, 1.0, 1.1, 1.3, 1.2]
  monthly_seasonality:
    11: 1.2  # November
    12: 1.5  # December
  noise_sigma: 0.15
  anomaly_probability: 0.01
  anomaly_magnitude: 2.0

retail:
  promotion_probability: 0.1
  promotion_lift: 1.3
  stockout_probability: 0.02
  stockout_behavior: "zero"  # or "partial"
  price_elasticity: -0.5

sparsity:
  missing_combinations_pct: 0.1
  random_gaps_per_series: 2

holidays:
  - date: "2024-11-29"
    name: "Black Friday"
    multiplier: 2.0
  - date: "2024-12-25"
    name: "Christmas Day"
    multiplier: 0.3

seed: 42
```

```bash
uv run python scripts/seed_random.py --full-new --config examples/seed/config_custom.yaml --confirm
```

## Time-Series Patterns

### Trend Components

- **none**: Stationary demand (no trend)
- **linear**: `demand * (1 + slope * days_from_start)`
- **exponential**: `demand * (1 + slope) ^ days_from_start`

### Seasonality

**Weekly**: Day-of-week multipliers (Mon=0.8, Sat=1.3, etc.)

**Monthly**: Optional month-specific multipliers

**Holidays**: US federal holidays + custom dates with multipliers

### Noise & Anomalies

- Gaussian noise with configurable sigma
- Random anomalies (spikes/dips) with configurable probability and magnitude

### Retail Effects

- **Promotions**: Random promotional periods with demand lift
- **Stockouts**: Zero or partial sales during stockout events
- **Price Elasticity**: Demand adjustment based on price changes
- **New Product Ramps**: Gradual demand increase for new launches

## Phase 1 Realism Extensions

Phase 1 adds opt-in realism: exogenous signals, multi-seasonality, trend changepoints,
returns volume, and stockout substitution. Each extension is gated behind its own flag
on `GenerateParams` (or its dataclass on `SeederConfig`). **Existing scenarios with no
flags set produce byte-identical seeded data to pre-Phase-1** — the regression invariant
is enforced by `app/shared/seeder/tests/test_phase1_regression.py`.

### Exogenous Signals

Persisted in the `exogenous_signal` table. Three signals available:

| Signal | Scope | Shape |
|--------|-------|-------|
| `weather_temp_c` | per (store, date) | sinusoidal climatology + Gaussian noise |
| `macro_index` | per date (global) | random walk from `macro_initial_value` |
| `event_flag` | per `event_dates` entry | binary 1.0 marker on configured dates |

Toggle via `GenerateParams.enable_exogenous=true` (turns on weather + macro). To also
drive demand from weather, pass `weather_temperature_sensitivity` (e.g. `0.02` = +2%
demand per °C above the climatology mean).

Read back:

```bash
curl "http://localhost:8123/seeder/exogenous?signal_name=weather_temp_c&start_date=2024-01-01&end_date=2024-01-31"
```

### Multi-Seasonality

Yearly sin wave on top of weekly + monthly seasonality:

```json
{"yearly_seasonality_amplitude": 0.15}
```

Amplitude is a fraction of base demand (0–1). 0 or unset = disabled.

### Changepoints

COVID-style demand impulses with exponential decay:

```json
{
  "changepoints": [
    {"date": "2024-03-15", "demand_multiplier": 2.0, "decay_days": 60}
  ]
}
```

`decay_days=0` means a pure impulse on the changepoint date.

### Returns

Synthetic returns volume in the `sales_returns` table. A configurable fraction of
sales rows generates a delayed return:

```json
{"enable_returns": true}
```

Tune via `ReturnsConfig` on `SeederConfig` (default ~2% of sales, lag 1–14 days, with
reasons drawn from `defective`/`wrong_size`/`not_as_described`/`changed_mind`/
`damaged_in_transit`).

### Substitution on Stockout

When a member of a substitute group is stocked out, the surviving members pick up a
share of demand:

```json
{
  "enable_substitution": true,
  "substitute_groups": [[1, 2, 3]],
  "substitution_lift_on_stockout": 0.5
}
```

`product_id` values must already exist in the dataset. The lift is split across in-stock
group-mates.

### Phase 1 API surface

- `POST /seeder/generate` accepts the Phase 1 fields above; defaults keep Phase 1 off.
- `GET /seeder/exogenous?signal_name=&start_date=&end_date=&store_id=` returns signal rows.
- `GET /seeder/status` adds `exogenous_signals` and `sales_returns` counts.

## Phase 2 Retail Depth Extensions

Phase 2 adds five orthogonal toggles for richer retail realism: multi-channel
sales, product lifecycles, bundle/BOGO promotions, clearance markdowns, and
replenishment lead times. Like Phase 1, every toggle defaults off — the
disabled path is byte-identical with pre-Phase-2 output for every existing
scenario.

### Multi-Channel Sales

Splits each emitted `sales_daily` row across channels drawn from a configurable
mix.

```json
{
  "enable_multichannel": true,
  "channel_mix": {"in_store": 0.6, "online": 0.3, "click_collect": 0.1},
  "online_promo_uplift": 1.2,
  "online_substitution_to_instore": 0.1
}
```

- Allow-list for channel keys: `in_store`, `online`, `click_collect`, `wholesale`.
- Weights must be non-negative; at least one must be positive.
- `online_promo_uplift` multiplies quantity for online rows on promo dates.
- `online_substitution_to_instore` shifts the effective mix toward `online`
  during promos (0.0 = independent; 1.0 = pure substitution).

### Product Lifecycles

Assigns each product a `launch_date` (and optionally a `discontinue_date`) and
shapes demand over intro → growth → maturity → decline → discontinued.

```json
{
  "enable_lifecycle": true,
  "lifecycle_discontinue_probability": 0.05
}
```

When enabled:
- `Product.launch_date` / `Product.discontinue_date` are populated.
- `SalesDailyGenerator` applies the lifecycle multiplier per `(product, date)`.
- The legacy `new_product_ramp_days` linear ramp is suppressed to avoid
  double-attenuation.

### Bundle / BOGO Promotions

Converts a fraction of `PromotionGenerator`'s output into `kind='bundle'` or
`kind='bogo'` rows with explicit member product IDs.

```json
{
  "enable_bundles": true,
  "bundle_probability": 0.2
}
```

- `bundle_probability` is the per-promotion conversion rate.
- Each converted row carries a `bundle_member_product_ids` list (enforced by
  the `ck_promotion_bundle_members_consistency` CHECK).

### Markdowns (Clearance)

Emits `Promotion(kind='markdown')` rows + companion `PriceHistory` drops on
two triggers:

```json
{
  "enable_markdowns": true,
  "markdown_trigger": "lifecycle_decline"
}
```

- `lifecycle_decline` (default): fires chain-wide on the first date a product
  enters the decline stage. Requires `enable_lifecycle=true` to produce rows.
- `stockout_risk`: fires per-`(store, product)` ending the day before each
  observed stockout, with the configured `markdown_duration_days` window.
- `age_days` is **deferred** — see issue [#94](https://github.com/w7-mgfcode/ForecastLabAI/issues/94).
  The generator raises `NotImplementedError` for that mode.

### Replenishment Lead Time

Emits `replenishment_event` rows that mark receipts of inbound stock per
`(store, product)` PO chain.

```json
{
  "enable_lead_time": true,
  "mean_lead_time_days": 7
}
```

- One PO every `order_frequency_days` (default 14) per `(store, product)`.
- Lead time sampled Gaussian; fill rate sampled Gaussian and clamped to [0, 1].
- Receipts past the seeded `end_date` are dropped to keep the FK to
  `calendar` valid.

### Phase 2 API surface

- `POST /seeder/generate` accepts all five Phase 2 enable flags plus
  `channel_mix`, `online_promo_uplift`, `online_substitution_to_instore`,
  `lifecycle_discontinue_probability`, `bundle_probability`, `markdown_trigger`,
  and `mean_lead_time_days`. Defaults keep Phase 2 off.
- `GET /seeder/channels` returns the sorted allow-list for
  `sales_daily.channel` and `ChannelConfig.channel_mix` keys —
  `["click_collect", "in_store", "online", "wholesale"]`.
- `GET /dimensions/products/{id}/lifecycle-curve` returns the reference
  demand-multiplier curve for a product using the default `LifecycleConfig`
  ramp parameters (respects the product's own `launch_date` /
  `discontinue_date`). Useful for UI charts.
- `GET /seeder/status` adds a `replenishment_events` count.

## Data Integrity

The seeder enforces data integrity:

1. **Foreign Keys**: All fact records reference valid dimension records
2. **Non-Negative Values**: Quantities and prices are always non-negative
3. **Date Coverage**: Calendar table covers entire date range
4. **Uniqueness**: Store codes and product SKUs are unique
5. **Phase 1 — Returns positive**: `sales_returns.return_quantity` is always ≥ 1
6. **Phase 1 — Exogenous consistency**: every `exogenous_signal` row satisfies
   `is_global = true ⇔ store_id IS NULL` (enforced by a CHECK constraint and verified
   by `verify_data_integrity`)
7. **Phase 2 — Bundle members non-NULL**: every `promotion` row with
   `kind in (bundle, bogo)` carries a non-NULL `bundle_member_product_ids`
8. **Phase 2 — Lifecycle ordering**: `discontinue_date >= launch_date` when both are set
9. **Phase 2 — Replenishment fill**: `received_qty <= ordered_qty` on every
   `replenishment_event` row

Verify with:
```bash
uv run python scripts/seed_random.py --verify
```

## Reproducibility

Same seed = identical data:

```bash
# These produce identical datasets
uv run python scripts/seed_random.py --full-new --seed 42 --confirm
uv run python scripts/seed_random.py --delete --confirm
uv run python scripts/seed_random.py --full-new --seed 42 --confirm
```

## Environment Variables

Configure defaults via settings:

```bash
SEEDER_DEFAULT_SEED=42           # Default random seed
SEEDER_DEFAULT_STORES=10         # Default store count
SEEDER_DEFAULT_PRODUCTS=50       # Default product count
SEEDER_BATCH_SIZE=1000           # Records per INSERT
SEEDER_ENABLE_PROGRESS=True      # Show progress bar
SEEDER_ALLOW_PRODUCTION=False    # Block in production
SEEDER_REQUIRE_CONFIRM=True      # Require --confirm flag
```

## Integration Tests

The seeder includes a comprehensive test suite:

```bash
# Unit tests (no database required)
uv run pytest app/shared/seeder/tests/ -v -m "not integration"

# Integration tests (requires PostgreSQL + explicit opt-in)
APP_ENV=testing uv run pytest app/shared/seeder/tests/test_integration.py -v
```

**Safety Guard**: Integration tests require explicit opt-in via `APP_ENV=testing` or `ALLOW_DESTRUCTIVE_TEST_DB=true` to prevent accidental data loss.

## Common Workflows

### Development Setup

```bash
# Quick start with standard data
uv run python scripts/seed_random.py --full-new --confirm
```

### Seasonal Testing

```bash
# Test holiday forecasting
uv run python scripts/seed_random.py --full-new --scenario holiday_rush --confirm
```

### Missing Data Testing

```bash
# Test gap handling
uv run python scripts/seed_random.py --full-new --scenario sparse --confirm
```

### Extending Data

```bash
# Add Q1 2025 data
uv run python scripts/seed_random.py --append \
  --start-date 2025-01-01 \
  --end-date 2025-03-31 \
  --seed 43
```

### Clean Slate

```bash
# Delete everything and regenerate
uv run python scripts/seed_random.py --delete --confirm
uv run python scripts/seed_random.py --full-new --seed 42 --confirm
```

## Related Documentation

- [CLI Reference](../examples/seed/README.md) - Detailed CLI options and examples
- [YAML Configs](../examples/seed/) - Example configuration files
- [Architecture](./ARCHITECTURE.md) - Overall system design
- [Data Platform](./PHASE/1-DATA_PLATFORM.md) - Database schema details
