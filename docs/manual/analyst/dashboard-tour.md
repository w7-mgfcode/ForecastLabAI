# Dashboard tour

Every page in the web app, grouped the way the navigation groups them.

**Purpose:** know which page answers which question, so you can stop hunting.
**Intended reader:** analysts and anyone driving a demo. No terminal required.

## What you'll accomplish

A map of the dashboard: what each page shows, what it needs in order to show anything, and which chapter goes deeper.

## Before you start

The dashboard is at **http://localhost:5173** and reads from the backend at `:8123`. Two conditions must hold or every page looks broken in the same way:

- The backend is running. If every panel reads "Loading…", it is not — see [Troubleshooting](../troubleshooting.md).
- The database has data. A migrated-but-empty database renders zeros and empty tables, which is correct behavior, not a fault. Seed from **Admin → Data seeding** or run `make demo`.

The nav groups pages as: Dashboard, Showcase, **Explorer** (menu), **Visualize** (menu), Knowledge, Chat, Agent Guide, Admin. A light/dark toggle sits at the right.

## Dashboard (`/`)

The landing page and health check. Headline KPI cards — total revenue, units sold, transactions, average unit price, average basket — over a revenue-over-time chart.

Use it to confirm at a glance that data is loaded and roughly shaped as you expect. Zeros mean an empty database.

## Showcase (`/showcase`)

Runs the **entire end-to-end pipeline live in the browser**: seed → features → train three models → backtest → register the winner → alias → agent check. Each step streams in as a status card that flips to pass, fail, or skip, with a summary banner naming the winning model and its accuracy.

This is the best page for a guided demo — the same evidence as `make demo`, with no terminal.

Tick **Re-seed first** if the database is empty or stale. Only one pipeline may run at a time. See [Quickstart](../operator/quickstart.md).

## Explorer

Read-only pages for browsing data and model history. Every table supports pagination, filtering, search, and server-side sorting, exports to CSV, has column-visibility toggles, and encodes filter/sort/page state **in the URL** — so a view you are looking at is a link you can send someone.

Detail pages are reached by **clicking a table row**; they are not in the nav.

- **Sales** (`/explorer/sales`) — daily sales records, with date-scoped KPIs, revenue bar/line charts, and cross-filtering.
- **Stores** (`/explorer/stores`) — the store list. A row opens a store profile with date-scoped KPIs, a revenue-over-time chart, and a top-products drilldown.
- **Products** (`/explorer/products`) — the product list. A row opens a profile with KPIs, revenue and lifecycle-demand curves, and a top-stores drilldown.
- **Model Runs** (`/explorer/runs`) — every trained model in the registry, with a **Family** badge distinguishing baseline, tree, and additive at a glance. The detail page shows configuration, metrics, runtime info, cross-links to the store and product, an artifact-integrity check, and — for non-baseline runs — the canonical feature columns and a feature-importance panel.
- **Jobs** (`/explorer/jobs`) — submitted train, predict, and backtest jobs. The detail page shows parameters, result JSON, error details, the linked run, a cancel action, and live status polling.

**Comparing two runs.** From the runs list you can open a side-by-side comparison. It carries a **Champion compatibility** badge — the verdict on whether the two runs are legitimately comparable — and a metrics-diff table including a feature-frame-version row. Comparability is not cosmetic; see [Champion selector](champion-selector.md).

## Visualize

The analytical, chart-heavy pages.

- **Demand Planner** (`/visualize/demand`) — every completed forecast rolled into a multi-SKU table: tomorrow, next-week, and next-month demand plus the inventory required to cover it. Includes a lead-time selector and a single-SKU drill-in. Answers "how much will this sell, and do I have enough?" See [Demand and planning](demand-and-planning.md).
- **Forecast** (`/visualize/forecast`) — a model's horizon predictions, with an optional prediction-interval band. The top of the page hosts a **Train a new model** card: family picker, model select, feature-frame V1/V2 select, and feature-pack toggles. See [Forecasting](forecasting.md).
- **Backtest Results** (`/visualize/backtest`) — fold charts and accuracy metrics, with a per-horizon-bucket card and a baseline-versus-feature-aware comparison table when the response carries them. See [Backtesting](backtesting.md).
- **Champion** (`/visualize/champion`) — the guided compare → decide → train → forecast → promote workflow. See [Champion selector](champion-selector.md).
- **What-If Planner** (`/visualize/planner`) — apply price, promotion, holiday, inventory, and lifecycle assumptions to an existing forecast and see the baseline-versus-scenario impact. The impact card carries a **method badge** telling you whether the result came from a real re-forecast or a heuristic adjustment. See [Demand and planning](demand-and-planning.md).
- **Batch Runner** (`/visualize/batch`) — run a matrix of jobs, with five sweep presets and a model × V1/V2 matrix picker.

Both the Forecast and Backtest pages run jobs **in-page**, export CSV, and cross-link back to runs and jobs.

## Knowledge (`/knowledge`)

The RAG knowledge base: the indexed corpus, a live semantic search box, and the current system state the agents draw on — seeded data, model runs, deployment aliases.

Type a question to retrieve the most relevant documentation passages with similarity scores. An empty corpus shows an empty state until documents are indexed via **Admin → RAG Sources**. See [Chat and knowledge](chat-and-knowledge.md).

## Chat (`/chat`)

The AI agent chat. Ask in natural language; the answer streams token by token and every tool the agent calls is displayed with its result.

Some actions **pause for your approval** before running — that is the human-in-the-loop gate working, not a hang. See [Chat and knowledge](chat-and-knowledge.md).

Requires an LLM API key. Everything else in the dashboard works without one.

## Agent Guide (`/guide`)

An in-product reference for the two agents: the tools they can call, the approval gate, the live session limits, and copy-paste example prompts. Worth opening before your first chat session — the limits shown are the live configured values, not documentation that can drift.

## Admin (`/admin`)

Operational controls, in tabs:

- **Data seeding** — generate synthetic data from a scenario, append more, verify integrity, or clear. See [Seeding data](../operator/seeding-data.md).
- **RAG Sources** — list, index, and delete knowledge documents.
- **Aliases** — manage registry aliases, including promoting a run to `production`.
- **AI models** — swap the agent LLM (including fully local Ollama), the embedding model, and provider API keys **live, with no restart**, with per-provider health indicators.

The Promote action here opens a confirmation dialog with three gates — artifact verification, a worse-WAPE acknowledgement, and a feature-frame-mismatch acknowledgement. Only the first has no override. See [Champion selector](champion-selector.md).

## Which page answers which question

| Question | Page |
|---|---|
| Is the system loaded and healthy? | Dashboard (`/`) |
| Can I see the whole system work? | Showcase |
| What does the underlying data look like? | Explorer → Sales / Stores / Products |
| What models have been trained? | Explorer → Model Runs |
| Why did that job fail? | Explorer → Jobs |
| How much will this SKU sell? | Visualize → Demand Planner |
| How accurate is this model? | Visualize → Backtest Results |
| Which model should I use? | Visualize → Champion |
| What if we ran a promotion? | Visualize → What-If Planner |
| What does the documentation say? | Knowledge, or Chat |
| How do I change the agent model? | Admin → AI models |

## Next

- [Forecasting](forecasting.md) — the model families and the feature frame.
