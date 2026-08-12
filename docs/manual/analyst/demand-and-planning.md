# Demand and planning

Turning forecasts into stocking decisions, and asking what would happen if you changed something.

**Purpose:** use the Demand Planner to see what you need, and the What-If Planner to test a decision before making it.
**Intended reader:** analysts planning inventory or evaluating a promotion.

## What you'll accomplish

A multi-SKU view of upcoming demand with inventory requirements, and a saved, comparable scenario showing the impact of price, promotion, holiday, inventory, or lifecycle assumptions.

## Demand Planner (`/visualize/demand`)

Rolls **every completed `predict` job** into one table: for each SKU, demand for tomorrow, next week, and next month, plus the inventory required to cover it.

Controls: a **lead-time selector** that reshapes the requirement columns, and a single-SKU **drill-in** for one product's detail.

**It shows what has been forecast, not what could be.** With no completed prediction jobs the table is empty — that is the page working correctly on an empty input. Train a model and run a forecast first ([Forecasting](forecasting.md)).

Because it aggregates completed jobs rather than forecasting on demand, the view is only as fresh as your most recent prediction run. A SKU whose forecast is three weeks old will say so; it will not silently re-forecast.

## What-If Planner (`/visualize/planner`)

Takes an existing forecast, applies assumptions, and shows baseline-versus-scenario demand and revenue impact.

### The five assumption types

| Assumption | What you state |
|---|---|
| **Price** | A different price level. |
| **Promotion** | A promotion of kind `pct_off`, `bogo`, `bundle`, or `markdown`. |
| **Holiday** | A holiday effect on the window. |
| **Inventory** | An on-hand position, which drives a coverage verdict. |
| **Lifecycle** | A stage: `launch`, `growth`, `maturity`, or `decline`. |

Inventory assumptions produce a **coverage verdict** — `covered`, `at_risk`, `stockout`, or `unknown`. `unknown` is a real answer, not a failure: it means the inputs do not support a verdict.

### The method badge — read this first

Every impact card carries a **method badge**, and it changes what the result means:

| Badge | Method | What actually happened |
|---|---|---|
| **model-driven re-forecast** | `model_exogenous` | A regression baseline genuinely **re-forecast** through your assumptions. |
| **heuristic adjustment** | `heuristic` | A deterministic post-forecast multiplier was applied. |

A `model_exogenous` result is a model's answer to "given these inputs, what happens?". A `heuristic` result is arithmetic applied *after* forecasting — transparent and reproducible, but it did not consult the model.

Both are legitimate; they answer with different authority. The badge exists so you never have to guess which you are looking at, and it is why this page can afford to always return an answer instead of refusing.

### Why this page exists

Recall the capability limit from [Forecasting](forecasting.md#the-capability-limit-worth-knowing-early): a feature-aware model cannot auto-forecast forward, because it needs future feature values that do not exist yet.

The What-If Planner is the resolution. Rather than fabricating those values, it makes you **state them** — and then labels which mechanism produced the result. The Champion selector's blocked forecast state routes here for exactly this reason. Assumptions you declared beat assumptions the system invented on your behalf.

### Saving, tagging, and comparing

Scenarios are first-class objects, not throwaway calculations:

| Endpoint | Purpose |
|---|---|
| `POST /scenarios/simulate` | Run a simulation. |
| `POST /scenarios` | Save a named plan. |
| `GET /scenarios` | List saved plans. |
| `GET /scenarios/{scenario_id}` | Fetch one. |
| `DELETE /scenarios/{scenario_id}` | Delete one. |
| `POST /scenarios/compare` | Rank 2–5 saved plans side by side. |

Save, tag, reload, clone, and delete named plans; then rank **2 to 5** of them in a multi-scenario comparison, ordered by `revenue_delta` or `units_delta`.

Comparison is where the page earns its keep. A single scenario tells you an assumption's effect; ranking several tells you which lever is worth pulling.

Each plan records its `source` — `user` or `agent` — so a scenario the experiment agent proposed is distinguishable from one you built.

### The agent can propose a scenario

The experiment agent can propose a scenario and, **behind the human-in-the-loop approval gate**, save it. `save_scenario` is in `agent_require_approval` alongside `create_alias` and `archive_run`, so the agent pauses and waits for you before persisting anything.

See [Chat and knowledge](chat-and-knowledge.md).

## Safety stock, once

The inventory arithmetic surfaced in the Champion selector applies here too:

```
safety_stock     = z(service_level) · σ_daily · √(lead_time_days)
expected_demand  = average_demand · lead_time_days
reorder_point    = expected_demand + safety_stock
```

It is a **labelled deterministic heuristic** over demand variability with a constant lead time — not a full inventory optimisation, and it never influences model ranking. Full detail in [Champion selector](champion-selector.md#6--interpret).

## Reading a planning result honestly

**A scenario is a conditional, not a prediction.** "If we run 20% off, demand rises by X" holds only insofar as the assumption is right and the mechanism behind the badge is trustworthy for your case.

**Check the badge before quoting a number.** A heuristic adjustment is arithmetic on top of a forecast; do not present it as the model's opinion.

**The underlying data is synthetic.** Elasticity the Forge generated is elasticity the Forge generated. See [What ForecastLabAI is](../operator/concepts.md#the-honesty-caveat-about-data).

**Lead time is an input, not a forecast.** Nothing here predicts supplier behavior.

## Next

- [Chat and knowledge](chat-and-knowledge.md) — the agents, including the one that proposes scenarios.
