# FAQ

Short answers to the questions this system actually gets, each linking to the chapter with the full story.

**Purpose:** fast orientation for questions that don't need a whole chapter.
**Intended reader:** everyone; skimmable.

## What this is

**Is this a real forecasting product I can point at my business?**
No. ForecastLabAI is a portfolio-grade system that exercises the *complete* forecasting lifecycle honestly, on one machine, with synthetic data. The engineering is real — leakage controls, reproducible runs, artifact integrity, an audited promotion gate. The data is generated. Pointing it at real data would mean replacing the seeder with real ingest and re-validating every measurement ([What ForecastLabAI is](operator/concepts.md)).

**Are the accuracy numbers meaningful?**
They are real measurements of model behavior on generated data — reproducible from a seed, and correct as measurements. They are **not** evidence about real retail demand. A model that wins here has won on patterns the generator created ([Backtesting](analyst/backtesting.md)).

**Do I need a cloud account?**
No. Everything runs on a single host by design. Adding a managed-cloud SDK to the `app/` core path is explicitly forbidden in [AGENTS.md](../../AGENTS.md) — it would violate the single-host vision.

**Do I need a GPU?**
No. The forecasting models are scikit-learn, LightGBM, and XGBoost on CPU. The only GPU path is optional: a Compose profile that runs **Ollama** on GPU for local embeddings and local agent models ([Running the stack](operator/running-the-stack.md)).

**Do I need an OpenAI or Anthropic key?**
Only for the chat agents and OpenAI-backed embeddings. Forecasting, backtesting, the registry, the Explorer, and every analytical dashboard page work with no key at all. Embeddings can run fully local through Ollama.

## Running it

**Why is everything zero after installing?**
A fresh database is empty and nothing seeds itself. Run `make demo`, or generate data from **Admin → Data seeding** ([Quickstart](operator/quickstart.md)).

**Why port 5433 for Postgres?**
So the Compose database does not collide with a Postgres you may already run on 5432. The container still listens on 5432 internally — 5433 is the host-side publication ([Running the stack](operator/running-the-stack.md)).

**Why does the database URL differ between host mode and Compose mode?**
Different networks. From the host it is `localhost:5433`; from inside the Compose network it is `postgres:5432`. The backend container sets `DATABASE_URL` itself, overriding `.env`, so the `.env` value can stay the host-mode default ([Configuration reference](configuration.md)).

**Is the seeded data the same every time?**
Yes, if the seed and scenario are the same. `seeder_default_seed` is 42. That reproducibility is the point — it lets two runs be compared honestly ([Seeding data](operator/seeding-data.md)).

**Can I safely re-send the same sales batch?**
Yes. `POST /ingest/sales-daily` resolves natural keys and upserts idempotently ([API reference](integrator/api-reference.md)).

## Models and results

**How many models are there?**
Eleven model types in three families: five baselines, four tree models, two additive models. The family is computed from the model type, never stored ([Forecasting](analyst/forecasting.md)).

**Why keep such simple baselines around?**
As honest comparison points. A machine-learning model that cannot beat "same day last week" is not worth deploying, and without the baseline you would not know.

**Which metric decides the winner?**
WAPE, with a fixed tie-break chain: WAPE → sMAPE → |bias| → MAE. WAPE is scale-free *and* stable at low volume, which sMAPE is not ([Backtesting](analyst/backtesting.md)).

**Positive bias — is that good?**
No. **Positive bias means the model under-forecasts**, which risks stockouts. Negative bias means it over-forecasts, which risks overstock ([Backtesting](analyst/backtesting.md)).

**Does feature importance tell me what drives demand?**
No. It reflects how much each feature reduced the model's *training* error — correlation with the model's fit, not real-world causation. Two products with similar importance profiles need not share a business driver ([Forecasting](analyst/forecasting.md)).

**Why can't my regression model just forecast forward?**
A feature-aware model needs a **future** feature frame — future prices, promotions, inventory. Rather than invent one, the system blocks the auto-forecast and routes you to the What-If Planner, where you state those assumptions explicitly ([Demand and planning](analyst/demand-and-planning.md)).

**Why won't these two runs compare?**
Comparability requires all three: same grain, overlapping data windows, same feature-frame version. Anything else is not an apples-to-apples comparison ([Champion selector](analyst/champion-selector.md)).

**Is the safety-stock number a real inventory optimisation?**
No, and the UI says so. It is a labelled deterministic heuristic over demand variability with a constant lead time. It **never** influences model ranking ([Champion selector](analyst/champion-selector.md)).

## Promotion and safety

**Can the system promote a model automatically?**
No. The app *recommends*; a human *approves*; the decision is recorded with the approver, the reason, and whether it overrode the recommendation ([Champion selector](analyst/champion-selector.md)).

**Can I promote a model that scores worse than the champion?**
Yes, deliberately — but you must tick an explicit acknowledgement showing the exact deltas. What you **cannot** override is a failed artifact verification: that gate has no checkbox ([Champion selector](analyst/champion-selector.md)).

**Can the chat agent change my registry behind my back?**
No. Every mutating tool is in `agent_require_approval` — `create_alias`, `archive_run`, `save_scenario` — and pauses for a person. Removing a name from that list is what would make it possible, which is why widening the list is a gated decision ([Chat and knowledge](analyst/chat-and-knowledge.md)).

**What happens if I ignore an approval prompt?**
It expires after `agent_approval_timeout_minutes` (60) and the tool does not run.

## Building on it

**Where is the authoritative API contract?**
The interactive OpenAPI schema at `http://localhost:8123/docs`. It is generated from the code, so it is always current; this manual is written by hand and explains *why* rather than restating every field ([API reference](integrator/api-reference.md)).

**Why do errors look like `application/problem+json`?**
RFC 7807, used uniformly. Ad-hoc error shapes and bare `HTTPException` with raw strings are forbidden by repository rules, so one parser handles every error from every endpoint.

**Why can't one feature slice import another?**
It is the rule that keeps the 19 slices independent and the import graph one-way (`app/features/* → app/shared`). Cross-cutting code goes through `app/core/` or `app/shared/`. The `ModelFamily` enum was moved to `app/shared/` for exactly this reason ([Code architecture](integrator/code-architecture.md)).

**Can I edit an existing Alembic migration?**
No. Migrations are forward-only once merged — add a new one ([Extending ForecastLabAI](integrator/extending.md)).

**Why does adding an unknown model type not crash the dashboard?**
`model_family_for` classifies unknown types as `baseline` and logs a warning, so a model added before the taxonomy map is updated degrades gracefully instead of raising ([Forecasting](analyst/forecasting.md)).

**Which checks must pass before I commit?**
Ruff (check and format), mypy `--strict`, pyright `--strict`, and the non-integration pytest suite. All of them gate merge ([CI and quality gates](integrator/ci-and-quality-gates.md)).
