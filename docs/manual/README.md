# User manual

The complete operating, analysis, and integration manual for ForecastLabAI: how to install and run the stack, how to use the dashboard to forecast demand and choose a model, and how to build against the REST API, the data model, and the artifact registry.

**Purpose:** one navigable place that takes a reader from an empty checkout to a running system with trained models — and explains every number the system reports.
**Intended reader:** anyone running ForecastLabAI for the first time, anyone using the dashboard to make a demand decision, and anyone integrating against the API or extending the code.

This manual documents behavior; it does not define it. The authoritative contracts live in the code and its generated OpenAPI schema at [`/docs`](http://localhost:8123/docs), and the agent-facing deep dives live in [`docs/_base/`](../_base/). Where this manual and the running system disagree, the system wins — and the disagreement is a bug in this manual.

## Three tracks

**Operator track** — you want to *run* ForecastLabAI: stand up Postgres, migrate, seed data, run the pipeline, and keep it healthy.

1. [What ForecastLabAI is](operator/concepts.md) — the lifecycle, the vocabulary, and what this system is not.
2. [Installation](operator/installation.md) — prerequisites, `.env`, Docker, `uv sync`, migrations.
3. [Quickstart](operator/quickstart.md) — the shortest path to a working system with trained models.
4. [Seeding data](operator/seeding-data.md) — The Forge: scenarios, generation, append, verify, clear.
5. [Running the stack](operator/running-the-stack.md) — backend, frontend, Docker Compose profiles, ports.
6. [Operations](operator/operations.md) — jobs, batches, artifacts, logs, health, and routine upkeep.

**Analyst track** — you want to *use* ForecastLabAI: explore the data, train and compare models, and decide what to stock. No terminal required.

1. [Dashboard tour](analyst/dashboard-tour.md) — every page in the web app, grouped as the nav groups them.
2. [Forecasting](analyst/forecasting.md) — the eleven model types, the three families, and the V1/V2 feature frame.
3. [Backtesting](analyst/backtesting.md) — how accuracy is measured, and what each metric does and does not tell you.
4. [Champion selector](analyst/champion-selector.md) — the guided compare → decide → train → promote workflow.
5. [Demand and planning](analyst/demand-and-planning.md) — the Demand Planner and the What-If scenario planner.
6. [Chat and knowledge](analyst/chat-and-knowledge.md) — the two agents, the RAG knowledge base, and the approval gate.

**Integrator track** — you want to *build on* ForecastLabAI: call its API, read its artifacts, or add to it.

1. [API reference](integrator/api-reference.md) — the shared conventions, the error envelope, and every endpoint group.
2. [Code architecture](integrator/code-architecture.md) — the vertical-slice layout and the import rules that hold it together.
3. [Data model](integrator/data-model.md) — the retail tables, the registry tables, and how they relate.
4. [Artifacts and the registry](integrator/artifacts-and-registry.md) — run lifecycle, artifact integrity, and aliases.
5. [Extending ForecastLabAI](integrator/extending.md) — adding a model, a slice, or a migration, and what must not change.
6. [CI and quality gates](integrator/ci-and-quality-gates.md) — the five gates, the pipeline, and the release flow.

**Shared references** — used by all three tracks:

- [Configuration reference](configuration.md) — every `Settings` field and the environment variables that set them.
- [Troubleshooting](troubleshooting.md) — symptom → cause → fix.
- [FAQ](faq.md)
- [Glossary](glossary.md) — the product vocabulary, used consistently across this manual.

## Prerequisites, once

Everything in this manual assumes: Docker and Docker Compose, Python 3.12 with [`uv`](https://docs.astral.sh/uv/), and Node.js 20+ with `pnpm` (via `corepack`) for the dashboard. Everything runs on a single host — there is no cloud account, no managed service, and no multi-tenant deployment anywhere in this system, by design.

An LLM API key is optional. Forecasting, backtesting, the registry, and the entire dashboard work without one; only the chat agents and OpenAI-backed RAG embeddings require `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`. Embeddings can run fully local through Ollama instead.

## How this manual reports numbers

ForecastLabAI ships a **synthetic data generator**, not a real retail dataset. Every accuracy metric you will see — MAE, sMAPE, WAPE, bias, RMSE — is measured against data the system generated from a seed. Those numbers are reproducible, and they are real measurements of model behavior, but they are **not** evidence about real-world retail demand, and this manual never presents them as such.

Where this manual quotes a number, it is either a configured default (traceable to [`app/core/config.py`](../../app/core/config.py) and repeated in the [configuration reference](configuration.md)) or a fixed constant in the code. Runtime figures — how long a run takes, what WAPE a model achieves, which model wins — depend on your data, your seed, and your hardware, so this manual describes how to read them rather than asserting values it cannot reproduce on your machine.
