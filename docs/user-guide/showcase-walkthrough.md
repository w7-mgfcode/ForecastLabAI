# Showcase walkthrough

> **Status:** Walkthrough draft. Sections marked **Planned (PRP-{N})** describe behavior the four-PRP `/showcase` upgrade epic will deliver — they are NOT in `dev` yet. Sections under "Quick start (current behavior)" and "What `/showcase` exercises today" describe the page as it ships on `dev` today.

## Overview

The Showcase page (`/showcase`) is the in-browser end-to-end demo of ForecastLab.
It is the first page a visitor opens when they want to see the whole system
work without reading code. Today it runs an eleven-step pipeline against the
`demo_minimal` scenario (3 stores, 10 products, ~92 days of seeded sales),
trains three baseline models in parallel, picks the lowest-WAPE winner, and
registers it under the `demo-production` alias — all streamed live to the
browser. For the broader dashboard tour see
[Dashboard Guide](./dashboard-guide.md).

## Quick start (current behavior, ships today)

A visitor needs three local processes running before opening the page:

1. The database is up: `docker compose up -d` shows a healthy `postgres`
   container on `localhost:5433`.
2. The backend is running: `uv run uvicorn app.main:app --port 8123`. Confirm
   with `curl http://localhost:8123/health`, which should return
   `{"status":"ok"}`.
3. The dashboard is running: in a second terminal, `cd frontend && pnpm dev`
   (the dashboard listens on `http://localhost:5173`). Make sure
   `frontend/.env` contains `VITE_API_BASE_URL=http://localhost:8123` — the
   browser uses this URL to reach the API.

Then:

```
http://localhost:5173/showcase
```

4. (Optional) Tick **Re-seed first** if the database is empty or stale.
   **Reset database** wipes existing data before re-seeding — destructive,
   leave unchecked unless you mean it.
5. Click **Run pipeline**. The page streams one card per step (~30–60 s on a
   pre-seeded database). Each card flips to a pass / fail / skip status as
   the backend reports it.
6. When the green **Pipeline complete** banner appears, click **View model
   runs** to open `/explorer/runs` and inspect the registered winner.

Only one pipeline can run at a time across the whole system — a second click
returns a "pipeline could not start" banner until the active run finishes.

## What `/showcase` exercises today

| Lifecycle stage     | Today                                                                                          |
| ------------------- | ---------------------------------------------------------------------------------------------- |
| Data platform       | `demo_minimal` scenario — 3 stores × 10 products × 92 days                                     |
| Feature engineering | V1 lag + rolling + calendar (lookback 60 days)                                                 |
| Forecasting         | 3 baselines (`naive`, `seasonal_naive`, `moving_average`) trained in parallel                  |
| Backtesting         | 3 expanding folds per model; aggregated metrics only (no horizon buckets, no V2)               |
| Registry            | One run + one alias (`demo-production`) for the lowest-WAPE winner                             |
| Agent               | One-turn chat with the experiment agent; skips gracefully without an LLM key                   |

The eleven streamed steps are: `precheck → reset → seed → status → features →
train → backtest → register → verify → agent → cleanup`. `reset` and `seed`
emit a Skip when the corresponding checkbox is unticked, so the card count
stays stable at eleven.

## Planned end-state (PRP-38..41)

The four-PRP `/showcase` upgrade reshapes the page from a flat eleven-step
list into a **phase-grouped control center** that exercises the full
ForecastLab lifecycle in one live run, with every result deep-linkable into
the existing dashboard pages. The phases below land incrementally — each
PRP is an independent PATCH release.

### Phase: Data — planned (PRP-38)

> **Planned (PRP-38):** A new **scenario picker** lets the visitor choose
> `demo_minimal`, `showcase-rich` (5 stores × 15 products × 180 days), or
> `sparse` before running. The Data phase calls the existing `/seeder/*`
> endpoints plus two new ones — `POST /seeder/phase2-enrichment` and
> `POST /seeder/historical-activity` — that wrap the existing CLI scripts
> (`scripts/seed_phase2_only.py`, `scripts/seed_historical_activity.py`) into
> the running pipeline so retail-depth tables (lifecycle, replenishment,
> exogenous, returns) get populated too. The Inspect button on the Data card
> deep-links to `/explorer/sales`.

### Phase: Modeling — planned (PRP-38)

> **Planned (PRP-38):** Three V1 baselines train in parallel (today's
> behavior, kept). A new `v2_train` step then trains a **V2 `prophet_like`**
> run with `feature_frame_version=2`, registers it with the full
> `artifacts/models/...` `artifact_uri`, and writes
> `runtime_info.feature_columns` + `feature_groups`. The Inspect button on
> the V2 card deep-links to `/explorer/runs/{v2_run_id}` so the Feature
> Frame panel and the signed-coefficient view from
> [Advanced Forecasting Guide](./advanced-forecasting-guide.md) light up
> after a single pipeline run.

### Phase: Backtesting — planned (PRP-38)

> **Planned (PRP-38):** The backtest step posts with `include_baselines=true`
> and `feature_frame_version=2` so PRP-36 per-horizon-bucket metrics
> (`h_1_7`, `h_8_14`, `h_15_28`, `h_29_plus`) populate. The step card renders
> a per-bucket mini table inline; the Inspect button deep-links to
> `/visualize/backtest?store_id=...&product_id=...` for the full
> baseline-vs-feature-aware comparison table.

### Phase: Registry decisions — planned (PRP-39)

> **Planned (PRP-39):** Three new steps walk the visitor through a real
> operator decision: `champion_compat_compare` calls
> `GET /registry/compare/{v1}/{v2}` and shows the "Not comparable" badge
> (V mismatch); `stale_alias_trigger` registers a second V2 run on the same
> grain with a different `feature_frame_version` so the Ops page surfaces
> `stale_reason="feature_frame_version_mismatch"`; `safer_promote_flow`
> swaps the alias to a worse-WAPE candidate so the next human click on
> Promote opens the safer-Promote dialog with its three gates (artifact
> verify, worse-WAPE acknowledgement, V-mismatch acknowledgement). Inspect
> buttons deep-link to `/explorer/runs/compare?a=&b=` and `/ops`.

### Phase: Portfolio batch — planned (PRP-39)

> **Planned (PRP-39):** A `batch_preset` step posts to `/batch/forecasting`
> with the `quick_baseline_sweep` preset over a 3 × 2 × 3 matrix and polls
> `/batch/{batch_id}` until it completes (90 s cap). The Inspect button
> deep-links to `/visualize/batch/{batch_id}` so the just-created sweep
> shows up populated in the Batch Runner page.

### Phase: Planning (scenarios) — planned (PRP-40)

> **Planned (PRP-40):** A `scenario_simulate` step calls
> `POST /scenarios/simulate` with a 10% price-cut assumption against the
> registered champion; `scenario_save` persists it as a named plan; a
> `scenario_compare` step ranks two saved plans via `POST /scenarios/compare`.
> The Inspect button deep-links to `/visualize/planner`, where the saved
> plan and the multi-plan comparison row are visible.

### Phase: Knowledge (RAG) — planned (PRP-40)

> **Planned (PRP-40):** A `providers_health` step probes
> `GET /config/providers/health`; `rag_index_subset` calls
> `POST /rag/index/project-docs` against a curated five-file subset of
> `docs/user-guide/`; `rag_retrieve_probe` runs a semantic search and
> reports the top-hit similarity score. See
> [Agents and RAG Guide](./agents-and-rag-guide.md) for the RAG model. The
> Inspect button deep-links to `/knowledge`.

### Phase: Agents (HITL) — planned (PRP-41)

> **Planned (PRP-41):** An `agent_hitl_flow` step opens an experiment-agent
> session and asks it to `save_scenario`. The pipeline pauses on the
> `approval_required` event and surfaces a one-click **Approve** button on
> the step card; on approval the tool completes and the step card resolves
> pass. A 90 s timeout falls back to Skip so a forgotten approval cannot
> wedge the run. The Inspect button deep-links to `/chat` where the
> approved tool call is visible in the transcript. See
> [Agents and RAG Guide](./agents-and-rag-guide.md) for the approval gate.

### Phase: Ops snapshot — planned (PRP-41)

> **Planned (PRP-41):** A final `ops_snapshot` step calls
> `GET /ops/summary`, `GET /ops/retraining-candidates`, and
> `GET /ops/model-health/{grain}`, rendering the results as a compact KPI
> grid (stale aliases, retraining queue depth, per-grain health). The
> Inspect button deep-links to `/ops`.

### Cross-cutting polish — planned (PRP-41)

> **Planned (PRP-41):** Four chrome-level additions wrap the page:
>
> - **KPI strip** at the top of `/showcase` — live counts of registered runs,
>   active aliases, indexed RAG sources, recent ops health.
> - **Inspect-Artifacts panel** rendered after `pipeline_complete` — a grid
>   of deep-link cards into every dashboard page that should now have
>   populated state (`/visualize/forecast`, `/visualize/backtest`,
>   `/visualize/batch`, `/visualize/planner`, `/explorer/runs`, `/ops`,
>   `/knowledge`, `/chat`).
> - **Run history strip** showing the last five runs, persisted in the
>   browser's `localStorage` (no new tables — the demo slice stays
>   stateless), with a one-click replay of parameters.
> - **Stop button** that cancels an in-flight run by releasing the
>   server-side pipeline lock.
> - **Scenario picker** wired through (introduced in PRP-38; polished here
>   with descriptions and estimated wall-clock per choice).

## Performance budgets (planned)

| Scenario                     | Target wall-clock | Notes                                              |
| ---------------------------- | ----------------- | -------------------------------------------------- |
| `demo_minimal` (default)     | ≤ 90 s            | Backwards-compatible with today's behavior          |
| `showcase-rich` (new — PRP-38)| ≤ 240 s          | Full lifecycle coverage across all phases           |
| Per-step timeout             | 120 s             | Unchanged from today                                |

## Troubleshooting

- **`Loading...` everywhere** — the browser cannot reach the backend. Check
  `frontend/.env`: `VITE_API_BASE_URL` must be `http://localhost:8123` from
  the browser host. A recurring regression sets it to a LAN IP such as
  `http://100.66.183.13:8123`, which breaks the `/demo/stream` WebSocket
  from a localhost browser. Fix: edit `frontend/.env`, restart Vite.
- **`Pipeline could not start` error banner** — another pipeline is already
  running. Only one run is allowed at a time across the whole backend. Wait
  for it to finish, or (planned PRP-41) use the **Stop** button.
- **A step shows Skip with "no API key matching agent_default_model
  provider"** — expected without `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` /
  `GOOGLE_API_KEY` in `.env`. The pipeline still goes green; the agent
  step is gated to never fail the run on a missing key.
- **A `make demo` run fails at step X** — cross-reference the per-step
  failure catalogue in [`docs/_base/RUNBOOKS.md`](../_base/RUNBOOKS.md)
  § "Showcase page (`/showcase`) pipeline fails at step X" rather than
  duplicating it here. The same step names apply to both `make demo` and
  the in-browser run; the source of both is
  [`frontend/src/pages/showcase.tsx`](../../frontend/src/pages/showcase.tsx)
  driving `app/features/demo/pipeline.py`.
