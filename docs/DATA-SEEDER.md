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

## Data Integrity

The seeder enforces data integrity:

1. **Foreign Keys**: All fact records reference valid dimension records
2. **Non-Negative Values**: Quantities and prices are always non-negative
3. **Date Coverage**: Calendar table covers entire date range
4. **Uniqueness**: Store codes and product SKUs are unique

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
