# Dashboard Guide

The ForecastLab dashboard is a React web app at **http://localhost:5173**. This guide
walks through every page. The top navigation bar groups pages as: Dashboard,
Showcase, **Explorer** (menu), **Visualize** (menu), Knowledge, Chat, Agent Guide,
and Admin. A light/dark theme toggle sits on the right.

## Dashboard (`/`)

The landing page. It shows headline **KPI cards** — total revenue, units sold,
transactions, average unit price, average basket — plus a revenue-over-time chart.
Use it for a quick health check of the seeded dataset. If the database is empty,
the cards read zero; seed data first (see Admin, or run `make demo`).

## Showcase (`/showcase`)

Runs the **end-to-end demo pipeline live in your browser**. Click to start, and the
page streams one status card per step: seed → features → train three models →
backtest → register the winner → alias → agent check. Each card flips to a
pass / fail / skip state, and a summary banner reports the winning model and its
accuracy. This is the best page for a guided demo of the whole system.

Tip: tick **Re-seed first** if the database is empty or stale. Only one pipeline can
run at a time.

## Explorer

The Explorer menu contains read-only pages for browsing the underlying data and
model history. Tables support pagination, filtering, search, and sorting; clicking a
row opens a detail page.

- **Sales** (`/explorer/sales`) — browse daily sales records.
- **Stores** (`/explorer/stores`) — list of retail stores. Click a store to open its
  **detail page**: an entity profile, date-scoped KPIs, a revenue-over-time chart,
  and a top-products drilldown.
- **Products** (`/explorer/products`) — list of products (SKUs). Click a product for
  its **detail page**: profile, KPIs, revenue and lifecycle-demand curves, and a
  top-stores drilldown.
- **Model Runs** (`/explorer/runs`) — every trained model tracked in the registry.
  A run **detail page** shows its configuration, metrics, and runtime info as JSON,
  cross-links to the store/product, an artifact-integrity check, and a compare link.
  Two runs can be compared side by side (config diff + metrics diff with deltas).
- **Jobs** (`/explorer/jobs`) — submitted train/predict/backtest jobs. A job
  **detail page** shows parameters, result JSON, error details, the linked run, a
  cancel action, and live status polling.

## Visualize

The Visualize menu holds the analytical, chart-heavy pages.

- **Demand Planner** (`/visualize/demand`) — rolls completed `predict` jobs into a
  multi-SKU table showing tomorrow / next-week / next-month demand and the
  inventory required to cover it. Includes a lead-time selector and a single-SKU
  drill-in. Answers "how much will this SKU sell, and do I have enough stock?"
- **Forecast** (`/visualize/forecast`) — visualizes a model's horizon predictions.
- **Backtest Results** (`/visualize/backtest`) — charts backtest folds and the
  accuracy metrics (MAE, sMAPE, WAPE, bias, stability) for a model run.

## Knowledge (`/knowledge`)

Surfaces the **RAG knowledge base**: the indexed document corpus, a live semantic
search box, and current system state. Type a question to retrieve the most relevant
documentation passages with similarity scores. If the corpus is empty, the page
shows an empty state until documents are indexed (see the Admin page).

## Chat (`/chat`)

The **AI agent chat**. Ask questions in natural language; the assistant streams its
answer token by token and shows any tools it calls. Some actions pause for your
approval before they run. See the Agents and RAG Guide for details.

## Agent Guide (`/guide`)

An in-app reference for the chat agents: the tools they can use, the human-in-the-loop
approval gate, live session limits, and example prompts to try.

## Admin (`/admin`)

Operational controls, organized into tabs:

- **Data seeding** — generate synthetic retail data from named scenarios, append more,
  verify integrity, or clear the dataset.
- **RAG Sources** — list indexed knowledge documents, index a new document, and
  delete sources.
- **Aliases** — manage model registry aliases (e.g. promote a run to `production`).
- **AI models** — view and change the agent LLM and RAG embedding configuration
  live, with per-provider health indicators.

## Notes

- Pages fetch data from the backend API; if everything shows "Loading…", confirm the
  backend is running and `VITE_API_BASE_URL` points at it.
- Explorer detail pages are reached by clicking table rows — they are not in the nav.
