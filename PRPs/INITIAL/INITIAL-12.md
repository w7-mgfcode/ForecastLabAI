# INITIAL-12.md — Randomized Database Seeder (The Forge)

## Architectural Role

**"The Forge"** - Development and testing data factory for generating realistic synthetic datasets.

This phase provides infrastructure for:
- Generating complete synthetic datasets from scratch
- Appending data without corrupting existing records
- Safe deletion with confirmation guards
- RAG + Agent workflow validation with generated documents
- Reproducible datasets via seeded randomness

---

## RESEARCH PHASE

### Codebase Analysis

**Existing Patterns Reviewed:**
- `examples/seed_demo_data.py` — Placeholder script (not implemented)
- `scripts/check_db.py` — Async SQLAlchemy pattern for database operations
- `app/features/data_platform/models.py` — 7 tables with constraints and relationships
- `app/features/ingest/service.py` — Idempotent upsert patterns for `ON CONFLICT`
- `docs/ARCHITECTURE.md` — Vertical slice architecture, data platform schema

**Schema Constraints (CRITICAL):**
| Table | Grain Constraint | Check Constraints |
|-------|------------------|-------------------|
| `sales_daily` | `UNIQUE(date, store_id, product_id)` | quantity >= 0, unit_price >= 0 |
| `inventory_snapshot_daily` | `UNIQUE(date, store_id, product_id)` | on_hand_qty >= 0 |
| `calendar` | `date` (PK) | day_of_week 0-6, month 1-12, quarter 1-4 |
| `price_history` | — | price >= 0, valid_to >= valid_from |
| `promotion` | — | discount_pct 0-1, end_date >= start_date |

**Foreign Key Dependencies:**
```
store ←─┬─ sales_daily
        ├─ price_history
        ├─ promotion
        └─ inventory_snapshot_daily

product ←─┬─ sales_daily
          ├─ price_history
          ├─ promotion
          └─ inventory_snapshot_daily

calendar ←─┬─ sales_daily
           └─ inventory_snapshot_daily
```

---

## BRAINSTORM PHASE

### Core Features (User Requested)
1. **Full new** — Generate complete synthetic dataset
2. **Delete** — Safe removal with confirmation flags
3. **Add more data** — Append without corruption
4. **RAG + Agent scenario** — End-to-end validation workflow

### Additional Features (Brainstormed)

#### Realistic Time-Series Patterns
- **Trend components**: Linear, exponential, or step trends
- **Seasonality**: Weekly (weekend spikes), monthly, yearly (holidays)
- **Noise injection**: Gaussian noise with configurable sigma
- **Anomalies**: Random spikes/dips for outlier testing

#### Retail-Specific Patterns
- **Promotion effects**: Sales lift during promotion windows
- **Stockout simulation**: Zero sales when inventory depleted
- **Price elasticity**: Inverse relationship between price and demand
- **New product launch**: Ramp-up pattern for new SKUs
- **End-of-life**: Decline pattern for discontinued products

#### Pre-Built Scenarios
- `holiday_rush` — Q4 surge with Black Friday/Cyber Monday
- `summer_slowdown` — Seasonal dip for certain categories
- `new_store_opening` — Gradual ramp-up for new locations
- `competitor_entry` — Demand shock simulation

#### Data Quality Utilities
- **Sparsity control**: Configure % of missing store/product/date combinations
- **Data gaps**: Intentional missing date ranges for testing
- **Dirty data mode**: Generate invalid records for validation testing

#### Export & Integration
- **Fixture export**: JSON/CSV fixtures for pytest
- **CI/CD integration**: GitHub Actions workflow for test data reset
- **Docker init**: Optional SQL dump for fresh containers

#### Performance & Scale
- **Streaming generation**: Memory-efficient batch inserts
- **Parallel workers**: Configurable concurrent insert threads
- **Progress reporting**: tqdm-style progress bars

---

## DECISION PHASE

### Architecture Decision: Script vs Service

| Option | Pros | Cons |
|--------|------|------|
| **CLI Script** (Recommended) | Simple, no runtime overhead, CI-friendly | No API access |
| Service Layer | API-accessible, reusable | Adds production code for dev utility |
| Hybrid | Flexibility | Complexity |

**Decision**: CLI Script in `scripts/seed_random.py` with importable core logic in `app/shared/seeder/` for potential service exposure later.

### Deletion Safety

| Guard | Description |
|-------|-------------|
| `--confirm` flag | Required for destructive operations |
| `--dry-run` | Preview what would be deleted |
| `APP_ENV != production` | Hard block in production environment |
| Backup prompt | Optional backup before delete |

---

## FEATURE

### Core Operations

#### 1. Full New (`--full-new`)
Generate complete synthetic dataset from scratch:

```bash
uv run python scripts/seed_random.py --full-new \
  --seed 42 \
  --stores 10 \
  --products 50 \
  --start-date 2024-01-01 \
  --end-date 2024-12-31 \
  --confirm
```

**Tables Generated:**
1. `store` — Random store codes, names, regions, types
2. `product` — Random SKUs, names, categories, brands, prices
3. `calendar` — Full date range with holidays
4. `sales_daily` — Synthetic sales with realistic patterns
5. `price_history` — Price change windows
6. `promotion` — Promotional campaigns
7. `inventory_snapshot_daily` — Daily inventory levels

#### 2. Delete (`--delete`)
Safe removal with guards:

```bash
# Delete all generated data
uv run python scripts/seed_random.py --delete --confirm

# Delete only sales data (keep dimensions)
uv run python scripts/seed_random.py --delete --scope facts --confirm

# Dry run (preview)
uv run python scripts/seed_random.py --delete --dry-run
```

**Scopes:**
- `all` — Everything (dimensions + facts)
- `facts` — Only fact tables (sales, inventory, price_history, promotion)
- `dimensions` — Only dimension tables (store, product, calendar)

#### 3. Append (`--append`)
Add more data without corrupting existing records:

```bash
# Add 3 more months
uv run python scripts/seed_random.py --append \
  --start-date 2025-01-01 \
  --end-date 2025-03-31 \
  --seed 43
```

**Append Logic:**
- Respects existing dimension IDs
- Generates sales only for existing store/product combinations
- Uses `ON CONFLICT DO UPDATE` for idempotency

#### 4. RAG + Agent Scenario (`--scenario rag-agent`)
End-to-end workflow validation:

```bash
uv run python scripts/seed_random.py --scenario rag-agent \
  --seed 42 \
  --confirm
```

**Workflow:**
1. Generate synthetic markdown documents
2. Index documents into pgvector via `/rag/index`
3. Create agent session via `/agents/sessions`
4. Send test query via `/agents/sessions/{id}/chat`
5. Verify response contains citations
6. Clean up session

---

### Realistic Data Generation

#### Time-Series Components

```python
@dataclass
class TimeSeriesConfig:
    """Configuration for realistic time-series generation."""
    base_demand: int = 100
    trend: Literal["none", "linear", "exponential"] = "linear"
    trend_slope: float = 0.1  # % daily change
    weekly_seasonality: list[float] = field(default_factory=lambda: [0.8, 0.9, 1.0, 1.0, 1.1, 1.3, 1.2])  # Mon-Sun
    monthly_seasonality: dict[int, float] = field(default_factory=dict)  # {12: 1.5} for December
    noise_sigma: float = 0.1  # Gaussian noise standard deviation
    anomaly_probability: float = 0.01  # Probability of random spike/dip
    anomaly_magnitude: float = 2.0  # Multiplier for anomalies
```

#### Retail Patterns

```python
@dataclass
class RetailPatternConfig:
    """Configuration for retail-specific patterns."""
    promotion_lift: float = 1.3  # Sales multiplier during promotions
    stockout_behavior: Literal["zero", "backlog"] = "zero"
    price_elasticity: float = -0.5  # % demand change per % price change
    new_product_ramp_days: int = 30  # Days to reach full demand
    weekend_spike: float = 1.2  # Weekend sales multiplier
```

#### Pre-Built Scenarios

| Scenario | Description | Use Case |
|----------|-------------|----------|
| `retail_standard` | Normal retail patterns | General testing |
| `holiday_rush` | Q4 surge with peaks | Seasonal forecasting |
| `high_variance` | Noisy, unpredictable | Robustness testing |
| `stockout_heavy` | Frequent stockouts | Inventory modeling |
| `new_launches` | Multiple new products | Launch forecasting |
| `sparse` | Many missing combinations | Gap handling |

---

### Configuration

#### Environment Variables

```bash
# Seeder Configuration
SEEDER_DEFAULT_SEED=42
SEEDER_DEFAULT_STORES=10
SEEDER_DEFAULT_PRODUCTS=50
SEEDER_BATCH_SIZE=1000
SEEDER_ENABLE_PROGRESS=true

# Safety Guards
SEEDER_ALLOW_PRODUCTION=false
SEEDER_REQUIRE_CONFIRM=true
```

#### Config File (`seed_config.yaml`)

```yaml
# Reusable seed configuration
dimensions:
  stores:
    count: 10
    regions: ["North", "South", "East", "West"]
    types: ["supermarket", "express", "warehouse"]
  products:
    count: 50
    categories: ["Beverage", "Snack", "Dairy", "Frozen"]
    brands: ["BrandA", "BrandB", "Generic"]

date_range:
  start: "2024-01-01"
  end: "2024-12-31"

time_series:
  base_demand: 100
  trend: "linear"
  trend_slope: 0.05
  noise_sigma: 0.15

retail:
  promotion_probability: 0.1
  stockout_probability: 0.05

sparsity:
  missing_combinations_pct: 0.3
  random_gaps_per_series: 2

seed: 42
```

---

### CLI Interface

```
Usage: seed_random.py [OPTIONS]

Options:
  --full-new              Generate complete dataset from scratch
  --delete                Delete generated data
  --append                Append data to existing dataset
  --scenario TEXT         Run pre-built scenario (retail_standard, holiday_rush, rag-agent, etc.)

  --seed INTEGER          Random seed for reproducibility [default: 42]
  --stores INTEGER        Number of stores to generate [default: 10]
  --products INTEGER      Number of products to generate [default: 50]
  --start-date DATE       Start of date range [default: 2024-01-01]
  --end-date DATE         End of date range [default: 2024-12-31]
  --sparsity FLOAT        Fraction of missing combinations [default: 0.0]

  --config PATH           Load configuration from YAML file
  --scope TEXT            Deletion scope: all, facts, dimensions [default: all]

  --confirm               Confirm destructive operations
  --dry-run               Preview without executing
  --verbose               Enable detailed logging
  --batch-size INTEGER    Batch insert size [default: 1000]

  --help                  Show this message and exit

Examples:
  # Generate standard dataset
  seed_random.py --full-new --seed 42 --confirm

  # Holiday scenario with 20 stores
  seed_random.py --full-new --scenario holiday_rush --stores 20 --confirm

  # Preview deletion
  seed_random.py --delete --dry-run

  # Append 3 months
  seed_random.py --append --start-date 2025-01-01 --end-date 2025-03-31

  # RAG + Agent E2E test
  seed_random.py --scenario rag-agent --confirm
```

---

## PAGE STRUCTURE (Verification Dashboard)

### /admin/seeder (Optional UI)

```
┌─────────────────────────────────────────────────────────────┐
│  Data Seeder Dashboard                                      │
├─────────────────────────────────────────────────────────────┤
│  Current Data Summary                                       │
│  ┌─────────┬─────────┬─────────┬─────────┬─────────┐       │
│  │ Stores  │Products │ Days    │ Sales   │Inventory│       │
│  │   10    │   50    │  365    │ 127,450 │ 182,500 │       │
│  └─────────┴─────────┴─────────┴─────────┴─────────┘       │
├─────────────────────────────────────────────────────────────┤
│  Quick Actions                                              │
│  [🔄 Generate New] [➕ Append Data] [🗑️ Delete All]         │
├─────────────────────────────────────────────────────────────┤
│  Generation Log                                             │
│  ────────────────────────────────────────────────────────   │
│  2026-02-02 10:30:15  Generated 10 stores                   │
│  2026-02-02 10:30:16  Generated 50 products                 │
│  2026-02-02 10:30:17  Generated 365 calendar days           │
│  2026-02-02 10:30:45  Generated 127,450 sales records       │
│  2026-02-02 10:31:02  ✓ Complete (seed: 42)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## EXAMPLES

### examples/seed/README.md
```markdown
# Data Seeding Examples

## Quick Start

\`\`\`bash
# Generate standard test dataset
uv run python scripts/seed_random.py --full-new --seed 42 --confirm

# Verify data
uv run python scripts/check_db.py
curl http://localhost:8123/analytics/kpis?start_date=2024-01-01&end_date=2024-12-31
\`\`\`

## Scenarios

| Scenario | Command | Use Case |
|----------|---------|----------|
| Standard | `--scenario retail_standard` | General development |
| Holiday | `--scenario holiday_rush` | Seasonal testing |
| Sparse | `--scenario sparse --sparsity 0.5` | Gap handling |
| RAG E2E | `--scenario rag-agent` | Agent validation |

## Reproducibility

All generated data is deterministic given the same seed:

\`\`\`bash
# These produce identical datasets
uv run python scripts/seed_random.py --full-new --seed 42 --confirm
uv run python scripts/seed_random.py --full-new --seed 42 --confirm
\`\`\`
```

### examples/seed/config_holiday.yaml
```yaml
# Holiday rush scenario configuration
dimensions:
  stores:
    count: 15
    regions: ["North", "South", "East", "West", "Central"]
  products:
    count: 100
    categories: ["Beverage", "Snack", "Dairy", "Frozen", "Gift", "Seasonal"]

date_range:
  start: "2024-10-01"
  end: "2024-12-31"

time_series:
  base_demand: 80
  trend: "exponential"
  trend_slope: 0.02
  monthly_seasonality:
    10: 1.0   # October baseline
    11: 1.3   # November (Thanksgiving)
    12: 1.8   # December (Holiday rush)

retail:
  promotion_probability: 0.25  # More promotions
  stockout_probability: 0.15   # More stockouts during rush

holidays:
  - date: "2024-11-28"
    name: "Thanksgiving"
    multiplier: 2.0
  - date: "2024-11-29"
    name: "Black Friday"
    multiplier: 3.0
  - date: "2024-12-24"
    name: "Christmas Eve"
    multiplier: 1.5
  - date: "2024-12-25"
    name: "Christmas Day"
    multiplier: 0.3  # Most stores closed

seed: 2024
```

---

## SUCCESS CRITERIA

### Functional Requirements
- [ ] `--full-new` generates valid data for all 7 tables
- [ ] `--delete` removes data with confirmation guard
- [ ] `--append` adds data without violating constraints
- [ ] `--scenario rag-agent` completes E2E workflow
- [ ] `--dry-run` previews without side effects
- [ ] `--seed` produces reproducible datasets
- [ ] Generated data passes all constraint checks

### Data Quality
- [ ] Foreign keys always reference valid parents
- [ ] Unique constraints never violated
- [ ] Check constraints respected (quantities >= 0, valid dates)
- [ ] Realistic distributions (not uniform random)
- [ ] Time-series patterns visible in visualizations

### Performance
- [ ] 1M+ sales records generated in < 5 minutes
- [ ] Memory usage stays under 500MB
- [ ] Batch inserts use transactions efficiently
- [ ] Progress reporting for long operations

### Safety
- [ ] Production environment blocked by default
- [ ] `--confirm` required for destructive operations
- [ ] Dry run available for all destructive operations
- [ ] Clear error messages for invalid configurations

---

## CROSS-MODULE INTEGRATION

| Direction | Module | Integration Point |
|-----------|--------|-------------------|
| **→ Data Platform** | Phase 1 | Generates data for all 7 tables |
| **→ Ingest** | Phase 2 | Uses same upsert patterns |
| **→ Feature Engineering** | Phase 3 | Generated data usable for feature computation |
| **→ Forecasting** | Phase 4 | Train models on synthetic data |
| **→ Backtesting** | Phase 5 | Backtest with controlled patterns |
| **→ Registry** | Phase 6 | Track runs on synthetic data |
| **→ RAG** | Phase 8 | Index generated documents |
| **→ Agents** | Phase 9 | E2E scenario validation |
| **→ Dashboard** | Phase 10 | Visualize generated data |
| **→ Tests** | All | Fixture generation for pytest |

---

## DOCUMENTATION LINKS

### Python Libraries
- [Faker](https://faker.readthedocs.io/) — Realistic fake data generation
- [NumPy Random](https://numpy.org/doc/stable/reference/random/index.html) — Random number generation
- [Click](https://click.palletsprojects.com/) — CLI framework
- [tqdm](https://tqdm.github.io/) — Progress bars
- [PyYAML](https://pyyaml.org/wiki/PyYAMLDocumentation) — YAML configuration

### SQLAlchemy
- [SQLAlchemy 2.0 Tutorial](https://docs.sqlalchemy.org/en/20/tutorial/index.html)
- [Async SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Bulk Operations](https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html#orm-queryguide-bulk-insert)

### Testing
- [pytest Fixtures](https://docs.pytest.org/en/stable/explanation/fixtures.html)
- [Factory Boy](https://factoryboy.readthedocs.io/) — Test fixtures (alternative pattern)

### Time Series
- [Synthetic Time Series Generation](https://arxiv.org/abs/2401.04912) — Academic reference
- [Time Series Decomposition](https://otexts.com/fpp3/decomposition.html) — Forecasting textbook

### Project References
- [CLAUDE.md](./CLAUDE.md) — Project coding standards
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) — System architecture
- [app/features/data_platform/models.py](./app/features/data_platform/models.py) — Schema definitions

---

## OTHER CONSIDERATIONS

### Best Practices

1. **Keep generator logic isolated** — `app/shared/seeder/` module, not in feature directories
2. **Clear CLI flags** — `--full-new`, `--delete`, `--append` with `--dry-run` options
3. **Transaction boundaries** — Atomic operations prevent partial corruption
4. **Document reproducibility** — README explains how to reproduce any dataset
5. **Smoke tests** — Generated data queryable by existing API endpoints

### Security

- **No production execution** — Hard check for `APP_ENV != production`
- **No sensitive data** — Generated data is purely synthetic
- **Confirmation required** — `--confirm` flag for all mutations
- **Audit logging** — Log all generation operations with parameters

### Observability

- **Structured logging** — JSON logs with event taxonomy
- **Metrics** — Row counts, duration, memory usage
- **Progress reporting** — Real-time progress for long operations

### Verification

After generation, automated checks validate:
- Row counts match configuration
- Foreign key integrity
- Constraint compliance
- Date range coverage
- Sparsity matches target

---

## WORKFLOW NOTES

### RESEARCH → BRAINSTORM → PLAN → EXECUTE → VERIFY → FINAL

1. **RESEARCH**: Analyze existing codebase patterns, schema constraints, FK relationships
2. **BRAINSTORM**: Generate feature ideas beyond core requirements
3. **PLAN**: Design CLI interface, module structure, configuration format
4. **EXECUTE**: Implement in vertical slice with tests
5. **VERIFY**: Run generated data through all downstream modules
6. **FINAL**: Document, add examples, update README

### Implementation Order

1. Core module structure (`app/shared/seeder/`)
2. Dimension generators (store, product, calendar)
3. Fact generators (sales_daily with time-series patterns)
4. CLI wrapper (`scripts/seed_random.py`)
5. Delete operations with safety guards
6. Append operations with idempotency
7. RAG + Agent scenario
8. Configuration file support
9. Pre-built scenarios
10. Verification dashboard (optional)

---

*Phase 12: The Forge — Where synthetic data is forged for development and testing.*
