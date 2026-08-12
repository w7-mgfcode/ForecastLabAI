# Quickstart

The shortest honest path from a migrated-but-empty install to a system with data, trained models, a backtested winner, and a promoted alias.

**Purpose:** exercise the whole lifecycle in one command, and know what each step proved.
**Intended reader:** operators who finished [Installation](installation.md), and reviewers who want to see the system work.

## What you'll accomplish

A seeded dataset, three trained models, three backtests, a registered winner with a verified artifact, an alias pointing at it, and an agent round-trip — with a printed verdict.

## Preconditions

`make demo` is a **black-box HTTP consumer**: it drives the published API rather than starting anything. Two things must already be true:

1. Postgres is reachable on `:5433` (the target starts it for you).
2. **The backend is already serving on `http://localhost:8123`.**

```bash
uv run uvicorn app.main:app --reload --port 8123    # in its own terminal
```

If the API is unreachable, the demo exits `2` — a precondition failure, distinct from a step failure.

## Run it

```bash
make demo
```

The target runs `docker compose up -d`, applies migrations, and then drives the pipeline with seed 42.

## What it does

```
precheck → (reset) → seed → status → features
        → train ×3 (parallel) → backtest ×3 (sequential)
        → register-winner → verify → agent → cleanup
```

Each stage proves something specific:

| Stage | What a pass proves |
|---|---|
| **precheck** | The API and database are reachable — the environment is real. |
| **seed** | The Forge can generate a reproducible dataset from seed 42. |
| **features** | Time-safe feature computation runs over the seeded history. |
| **train ×3** | Three model types fit and produce artifacts, concurrently. |
| **backtest ×3** | Time-series cross-validation scores all three on identical folds. |
| **register-winner** | The registry records the ranked winner with its metrics. |
| **verify** | The winner's artifact passes SHA-256 verification. |
| **agent** | The agent layer answers through the live stack. |

The comparison is meaningful precisely because the three models are backtested on the **same folds** — that is what makes "winner" a claim rather than an impression.

## Reading the outcome

A green run ends with a summary line naming the run count, the winning model, the alias, and wall-clock time — for example:

```
runs=3 winner=seasonal_naive alias=demo-production wall_clock=87s
```

**Which model wins is not fixed**, and a baseline winning is a legitimate result, not a bug. On synthetic data with a short history, `seasonal_naive` frequently beats feature-aware models — that is exactly why the baselines are in the comparison.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | Green (possibly with a soft warning on the wall-clock budget). |
| `1` | One or more pipeline steps failed — a real observation about the system. |
| `2` | Precondition failure: the API or database was unreachable. Nothing was measured. |

Do not read a `2` as evidence about the models — nothing ran. Only a `1` is a statement about the pipeline itself.

## The same thing in the browser

With the backend and dashboard both running, open **http://localhost:5173/showcase** and click **Run pipeline**. The identical flow streams into the page as one status card per step, each flipping to pass / fail / skip, with a summary banner naming the winner.

Tick **Re-seed first** if the database is empty or stale. Only one pipeline may run at a time.

This is the best route for a guided demo — no terminal, same evidence.

## Variants

```bash
make demo-quick    # skip re-seeding — fast iteration on existing data
make demo-clean    # DESTRUCTIVE: wipe the database first, then run
```

`make demo-clean` drops your seeded data. Use it when you want a guaranteed-clean measurement; avoid it if you have a dataset you care about.

## Where to go from here

You now have a working system. Depending on who you are:

- **Explore what was built** → [Dashboard tour](../analyst/dashboard-tour.md).
- **Train your own model deliberately** → [Forecasting](../analyst/forecasting.md).
- **Understand the winner** → [Backtesting](../analyst/backtesting.md).
- **Do it properly, with promotion** → [Champion selector](../analyst/champion-selector.md).
- **Generate different data** → [Seeding data](seeding-data.md).
- **Call it from code** → [API reference](../integrator/api-reference.md).

## Next

- [Seeding data](seeding-data.md) — the eight scenario presets and what each stresses.
