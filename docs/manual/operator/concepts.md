# What ForecastLabAI is

The system in one chapter: what it does, the vocabulary it uses, and — just as important — what it deliberately is not.

**Purpose:** enough shared understanding that every later chapter reads as obvious.
**Intended reader:** everyone, before anything else. No installation required to read this.

## What you'll accomplish

You will be able to say what problem this system solves, name the stages of its lifecycle, and explain why a measurement it produces is trustworthy as engineering evidence but not as a claim about real retail demand.

## The problem

A retailer asks a narrow, repeating question: **how many units of this product will this store sell over the next N days?** Answer it too low and you stock out; too high and you tie up cash in inventory that ages.

ForecastLabAI answers that question at the grain of one **(store, product) pair**, one day at a time, and — more importantly — it shows its work: how the answer was produced, how accurate it has been historically, and who approved putting it into service.

## The lifecycle

Nine stages, each a working vertical slice rather than a specification:

1. **Data platform** — the retail tables: stores, products, calendar, daily sales, prices, promotions, inventory, replenishment, returns, exogenous signals.
2. **Ingest** — loading sales through a batch API that is safe to re-run.
3. **Feature engineering** — turning raw history into model-ready columns *without leaking the future*.
4. **Forecasting** — training one of eleven model types across three families.
5. **Backtesting** — replaying history to measure how accurate a model would have been.
6. **Model registry** — recording every run with its config, metrics, and a checksummed artifact.
7. **RAG knowledge base** — semantic search over indexed documentation.
8. **Agentic layer** — chat agents that can answer questions and run experiments, behind a human approval gate.
9. **Dashboard** — a React app that surfaces all of the above.

The stages are ordered but not rigid: you can backtest without promoting, explore without forecasting, and use the dashboard without touching a terminal.

## Five ideas that explain most decisions

**Leakage is the enemy.** A feature that peeks at the future makes a model look brilliant and be useless. Every feature is built with `shift(lag)` and `shift(1).rolling()` patterns so a future value structurally cannot reach the model, and `app/features/featuresets/tests/test_leakage.py` is treated as the specification — weakening it is forbidden. When a metric looks too good, leakage is the first suspect.

**Baselines are not filler.** Five deliberately simple forecasters ship as first-class models. "Predict last week's same weekday" is often hard to beat, and a machine-learning model that cannot beat it is not worth its complexity. Without the baseline in the comparison you would never learn that.

**A measurement is only as good as its provenance.** A run records its configuration, its data window, its seed, and a SHA-256 of its artifact. That is what lets two runs be compared honestly, and what lets the registry refuse to promote a model whose artifact no longer verifies.

**Recommendation is not authority.** The system ranks candidates and names a winner. It does not promote it. A person approves, with their name recorded, and overriding the recommendation requires an explicit acknowledgement. Automation proposes; a human disposes.

**Agents are bounded.** The chat agents can read freely and act only within a gate: every mutating tool pauses and waits for approval. Sessions are capped in tokens, tool calls, and wall-clock time.

## What this is not

- **Not a multi-tenant SaaS.** Single host, no tenancy model, no auth boundary between users.
- **Not real-time.** Daily grain, batch jobs, asynchronous work. Nothing streams.
- **Not cloud-dependent.** No managed-cloud SDK is permitted in the core path; that rule is in [AGENTS.md](../../../AGENTS.md) and it is what keeps `docker compose up` sufficient.
- **Not trained on real retail data.** The dataset comes from a synthetic generator. See below — this is the most important caveat in the manual.
- **Not an inventory optimiser.** The safety-stock figure is a labelled heuristic over demand variability, not a full optimisation, and it never influences model ranking.

## The honesty caveat about data

Everything ForecastLabAI measures, it measures on data it generated itself, from a seed, via the synthetic seeder known as **The Forge**.

That has two consequences, and this manual holds both at once:

- The measurements are **real and reproducible**. Same seed, same scenario, same configuration produces the same dataset and comparable runs. The metrics are correct measurements of model behavior, the leakage controls genuinely hold, and the artifact checksums genuinely verify.
- The measurements say **nothing about real-world retail demand**. A model that wins here won on patterns the generator put there. Carrying a conclusion from this system to a real business would require real data and a fresh validation of every claim.

This manual never blurs that line. Where a number appears, it is a configured default or a fixed constant you can check; runtime figures — durations, accuracy scores, which model wins — depend on your data, seed, and hardware, so the manual teaches you to *read* them rather than asserting values it cannot reproduce on your machine.

## The shape of the code

Nineteen **vertical slices** under `app/features/`, each owning its models, schemas, service, routes, and tests. A slice may not import another slice — shared code goes through `app/core/` or `app/shared/`. That single rule is why the system stays legible at this size, and it is covered in [Code architecture](../integrator/code-architecture.md).

## Next

- [Installation](installation.md) — prerequisites and first run.
- [Glossary](../glossary.md) — every term above, defined precisely.
