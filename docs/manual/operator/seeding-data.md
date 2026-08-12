# Seeding data

The Forge: how ForecastLabAI generates the retail data it forecasts, and how to control what that data looks like.

**Purpose:** produce a dataset that stresses the behavior you want to study, reproducibly.
**Intended reader:** operators preparing a demo or an experiment.

## What you'll accomplish

A populated dataset with realistic time-series structure — trend, weekly and monthly seasonality, noise, promotions, stockouts, product lifecycles — generated from a seed you control, so the same inputs always produce the same data.

## The honest framing, first

The Forge produces **synthetic data**. Nothing it generates is a real sales record. That is not a limitation to apologise for — it is what makes the system reproducible and shareable. But it bounds every conclusion drawn downstream: a model that wins on Forge data won on patterns the Forge created. See [What ForecastLabAI is](concepts.md#the-honesty-caveat-about-data).

## Reproducibility

Generation is seeded. **The same scenario plus the same seed produces the same dataset**, which is what lets two model runs be compared honestly. The default is `seeder_default_seed = 42`, alongside `seeder_default_stores = 10` and `seeder_default_products = 50`.

Change the seed to get a different-but-equally-valid world; keep it fixed when you are comparing models, because changing data *and* model at once measures nothing.

## The eight scenario presets

Each preset tunes the generator toward a different difficulty:

| Scenario | What it stresses |
|---|---|
| `retail_standard` | The general case — ordinary trend, seasonality, and noise. The sensible default. |
| `holiday_rush` | A Q4 demand surge with Black Friday and Christmas structure. |
| `high_variance` | Noisy, hard-to-predict demand. Punishes overconfident models. |
| `stockout_heavy` | Frequent stockouts — censored demand, where observed sales understate true demand. |
| `new_launches` | Many products with short histories and ramp-up curves (100 products, a 45-day ramp). Hard for lag-based features. |
| `sparse` | Intermittent demand with gaps of 2–10 days. Where sMAPE misbehaves and WAPE earns its keep. |
| `demo_minimal` | A small, fast dataset for smoke-testing the pipeline. |
| `showcase_rich` | Sized for the `/showcase` demo — large enough that a V2 `prophet_like` run gets full horizon-bucket coverage. |

Two details worth knowing:

- **`holiday_rush` is calendar-pinned.** Its holiday dates and Q4 seasonality model a specific 2024 window and are *not* re-anchored to today. Pass an explicit `start_date` / `end_date` to shift it. Every other window-anchored preset follows today's date.
- **`demo_minimal` and `showcase_rich` tune their noise deliberately** to avoid a degenerate case where WAPE evaluates to NaN because a fold's actual demand sums to zero. If you build a custom config with very low demand, expect to meet that trap.

## Generating data

### From the dashboard

**Admin → Data seeding.** Choose a scenario, set the seed, generate. The same tab hosts append, verify, and clear. This is the recommended route — no terminal, and the destructive actions are behind confirmations.

### From the API

```bash
# What is currently loaded?
curl http://localhost:8123/seeder/status

# What scenarios exist?
curl http://localhost:8123/seeder/scenarios

# Generate
curl -X POST http://localhost:8123/seeder/generate \
  -H 'Content-Type: application/json' \
  -d '{"scenario": "retail_standard", "seed": 42}'
```

The full endpoint set:

| Endpoint | Purpose |
|---|---|
| `GET /seeder/status` | Current dataset state. |
| `GET /seeder/scenarios` | Available presets. |
| `GET /seeder/channels` | Available sales channels. |
| `GET /seeder/exogenous` | Exogenous signal data. |
| `POST /seeder/generate` | Generate a dataset from a scenario. |
| `POST /seeder/append` | Extend an existing dataset. |
| `POST /seeder/verify` | Check dataset integrity. |
| `DELETE /seeder/data` | Clear generated data. |

Scenario presets are a *starting point*: explicit parameters in the request override the preset's values.

### As part of the demo

`make demo` seeds with seed 42 before running the pipeline. `make demo-quick` skips seeding to iterate on existing data. See [Quickstart](quickstart.md).

## What gets generated

The Forge populates the data-platform tables — stores and products, a calendar, daily sales, and the signals that explain them: price history, promotions, inventory snapshots, replenishment events, returns, and exogenous signals.

That last group matters for modelling: the V2 feature packs `price_promo`, `inventory`, `replenishment`, `returns`, `exogenous_weather`, and `exogenous_macro` read exactly these tables. **A pack whose underlying signal was not seeded contributes nothing.** If you want to study inventory-aware forecasting, seed a scenario that generates meaningful inventory dynamics — `stockout_heavy` is the obvious one. See [Forecasting](../analyst/forecasting.md).

## Two guards against destroying real data

| Setting | Default | Effect |
|---|---|---|
| `seeder_allow_production` | `false` | Blocks seeding entirely when `app_env` is `production`. |
| `seeder_require_confirm` | `true` | Requires explicit confirmation for destructive seeder operations. |

Both default to the safe position. `DELETE /seeder/data` and `make demo-clean` are genuinely destructive — they remove generated data with no undo.

## Appending versus regenerating

**Append** extends the existing dataset forward, preserving history and the entities already present. Use it to lengthen a series or simulate the arrival of new days.

**Regenerate** replaces. Use it when changing scenario or seed.

Appending after changing the seed produces a dataset with a discontinuity at the join — occasionally useful for testing robustness, usually just confusing. Prefer one seed per dataset.

## Verifying

```bash
curl -X POST http://localhost:8123/seeder/verify
```

Checks internal consistency — that sales reference real stores and products, dates fall inside the generated window, and the signal tables line up with the fact table. Worth running after an append, or when a model behaves strangely for reasons you cannot explain.

## Next

- [Running the stack](running-the-stack.md) — host mode, container mode, and the GPU profile.
- [Forecasting](../analyst/forecasting.md) — turning this data into models.
