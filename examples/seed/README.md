# Data Seeding Examples

This directory contains examples and configurations for the ForecastLabAI data seeder.

## Quick Start

```bash
# Generate standard test dataset
uv run python scripts/seed_random.py --full-new --seed 42 --confirm

# Verify data was created
uv run python scripts/seed_random.py --status

# Check data integrity
uv run python scripts/seed_random.py --verify

# Query via API
curl http://localhost:8123/analytics/kpis?start_date=2024-01-01&end_date=2024-12-31
```

## CLI Reference

### Operations

| Flag | Description |
|------|-------------|
| `--full-new` | Generate complete dataset from scratch |
| `--delete` | Delete generated data |
| `--append` | Append data to existing dataset |
| `--status` | Show current data counts |
| `--verify` | Verify data integrity |

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--seed` | 42 | Random seed for reproducibility |
| `--stores` | 10 | Number of stores to generate |
| `--products` | 50 | Number of products to generate |
| `--start-date` | 2024-01-01 | Start of date range |
| `--end-date` | 2024-12-31 | End of date range |
| `--sparsity` | 0.0 | Fraction of missing combinations |
| `--scenario` | — | Pre-built scenario name |
| `--config` | — | Path to YAML config file |
| `--scope` | all | Deletion scope (all/facts/dimensions) |
| `--batch-size` | 1000 | Batch insert size |

### Safety Flags

| Flag | Description |
|------|-------------|
| `--confirm` | Required for destructive operations |
| `--dry-run` | Preview without executing |

## Scenarios

| Scenario | Description | Use Case |
|----------|-------------|----------|
| `retail_standard` | Normal retail patterns with mild seasonality | General development and testing |
| `holiday_rush` | Q4 surge with Black Friday/Christmas peaks | Seasonal forecasting validation |
| `high_variance` | Noisy, unpredictable data with anomalies | Model robustness testing |
| `stockout_heavy` | Frequent stockouts (25% probability) | Inventory modeling scenarios |
| `new_launches` | 100 products with launch ramp patterns | Launch forecasting validation |
| `sparse` | 50% missing combinations, random gaps | Gap handling and missing data tests |

### Example: Holiday Scenario

```bash
uv run python scripts/seed_random.py --full-new \
  --scenario holiday_rush \
  --stores 15 \
  --confirm
```

### Example: Using YAML Config

```bash
uv run python scripts/seed_random.py --full-new \
  --config examples/seed/config_holiday.yaml \
  --confirm
```

## Reproducibility

All generated data is deterministic given the same seed:

```bash
# These produce identical datasets
uv run python scripts/seed_random.py --full-new --seed 42 --confirm
uv run python scripts/seed_random.py --delete --confirm
uv run python scripts/seed_random.py --full-new --seed 42 --confirm
```

## Appending Data

Add data for additional time periods without affecting existing records:

```bash
# First, generate initial dataset
uv run python scripts/seed_random.py --full-new \
  --start-date 2024-01-01 \
  --end-date 2024-12-31 \
  --seed 42 \
  --confirm

# Later, append Q1 2025
uv run python scripts/seed_random.py --append \
  --start-date 2025-01-01 \
  --end-date 2025-03-31 \
  --seed 43
```

## Deletion Options

```bash
# Delete everything
uv run python scripts/seed_random.py --delete --confirm

# Delete only fact tables (keep dimensions)
uv run python scripts/seed_random.py --delete --scope facts --confirm

# Preview what would be deleted
uv run python scripts/seed_random.py --delete --dry-run
```

## Configuration Files

See `config_holiday.yaml` for a complete example of YAML configuration.

### Configuration Structure

```yaml
dimensions:
  stores:
    count: 10
    regions: ["North", "South", "East", "West"]
    types: ["supermarket", "express", "warehouse"]
  products:
    count: 50
    categories: ["Beverage", "Snack", "Dairy"]
    brands: ["BrandA", "BrandB", "Generic"]

date_range:
  start: "2024-01-01"
  end: "2024-12-31"

time_series:
  base_demand: 100
  trend: "linear"           # none, linear, exponential
  trend_slope: 0.001        # daily % change
  noise_sigma: 0.15         # demand variance

retail:
  promotion_probability: 0.1
  stockout_probability: 0.02
  promotion_lift: 1.3

sparsity:
  missing_combinations_pct: 0.0
  random_gaps_per_series: 0

holidays:
  - date: "2024-12-25"
    name: "Christmas Day"
    multiplier: 0.3

seed: 42
```

## Time-Series Patterns

The seeder generates realistic time-series data with:

### Trend Components
- **None**: Stationary demand
- **Linear**: Gradual growth/decline
- **Exponential**: Accelerating growth

### Seasonality
- **Weekly**: Different demand by day of week (Mon-Sun)
- **Monthly**: Optional multipliers by month
- **Holiday**: Special multipliers for specific dates

### Noise & Anomalies
- Gaussian noise with configurable variance
- Random spikes/dips for anomaly testing

### Retail Effects
- Promotion lift during promotional periods
- Stockout handling (zero sales or backlog)
- Price elasticity effects

## Integration with ForecastLabAI

After seeding, you can:

1. **Explore data**: Use `/analytics/kpis` and `/analytics/drilldowns`
2. **Train models**: Call `/forecasting/train` with store/product IDs
3. **Run backtests**: Call `/backtesting/run` to validate models
4. **Test RAG**: Index documents and query with `/rag/*` endpoints
5. **Use agents**: Create sessions and chat with `/agents/*` endpoints
