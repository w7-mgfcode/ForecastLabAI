# Champion Selector Guide

The **Champion Selector** turns "which forecasting model is best for this
store + product?" into a guided, end-to-end workflow: compare candidate models
on a leakage-safe backtest, read a recommendation, **decide** (accept it or
override), train the chosen model, generate and interpret its forecast, and —
only with explicit approval — **promote** it to a registry alias.

It lives at **`/visualize/champion`** in the dashboard and is served by the
`/model-selection/*` REST API (Swagger at **/docs** is the authoritative
contract).

> **The golden rule of promotion:** the app *recommends* a champion, but a
> human *approves* it, and that decision is **recorded**. Promotion is never
> automatic.

## The journey at a glance

```
Select → Run comparison → Results → Decide / override → Train → Forecast → Interpret → Promote
```

### 1 · Select & check availability

Pick a store, a product, a time period, a forecast horizon (1–90 days), and the
candidate models to compare. The page checks **data availability** for the pair
and recommends a cross-validation split. A pair with too little history is
flagged *unusable* and the comparison is refused (`400`).

### 2 · Run the comparison

`POST /model-selection/runs` submits an asynchronous run (returns `202` with a
monitor URL); the page polls it to a terminal state. Each candidate is
backtested with time-series cross-validation; results are ranked deterministically.

**Ranking** is by **WAPE** by default, with a fixed tie-break chain:
*WAPE, then sMAPE, then |bias|, then MAE.* The winner, runners-up, and any
failed candidates are all shown.

### 3 · Decide — accept or override

The recommended winner is pre-selected. You can:

- **Accept the recommendation** → trains the ranked winner.
- **Override to another candidate** → you must confirm an explicit warning (the
  recommended model and the WAPE gap are named) and may record a reason. The
  override is flagged (`is_override=true`) and audited. A candidate that *failed*
  its backtest is still override-trainable (training is independent of backtesting).

`POST /model-selection/{id}/train-selected` trains the chosen model;
`train-winner` trains the recommendation.

### 4 · Forecast

`POST /model-selection/{id}/predict` generates the horizon forecast for the
trained model. The response carries the **peak** and **low** demand days plus a
**decision** block (see below).

> **Capability limit.** A *feature-aware* model (`regression`, `prophet_like`,
> `lightgbm`, `xgboost`, `random_forest`) cannot auto-forecast here — it needs a
> future feature frame. The page shows a blocked state and routes you to the
> **What-If Planner** (Scenarios) instead of faking a forecast.

### 5 · Interpret

The **business interpretation** panel restates *why the model won*, the
**expected demand over the lead time**, and the **bias risk**:

> Positive bias means the model under-forecasts (risk of stockouts); negative
> bias means it over-forecasts (risk of overstock).

The **safety stock** panel shows a clearly-labeled, deterministic heuristic:

```
safety_stock        = z(service_level) · σ_daily · √(lead_time_days)
expected_demand     = average_demand · lead_time_days
reorder_point       = expected_demand + safety_stock
```

`σ_daily` is the standard deviation of the daily forecast; `z` comes from a fixed
service-level table (90% → 1.2816, 95% → 1.6449, 97.5% → 1.9600, 99% → 2.3263),
snapping to the nearest level in between. Adjust the lead time / service level and
recompute.

> **This is a heuristic** (demand variability only, constant lead time) — not a
> full inventory-optimisation model, and it **never** influences the model
> ranking.

### 6 · Promote (approval-gated, audited)

`POST /model-selection/{id}/promote` registers the trained model as a registry
`model_run` (transitioned to **SUCCESS** with a verified artifact) and points a
**registry alias** at it. It records a `promotion_decision` audit
(`approved_by`, the alias, the run id, the decision, the reason, and whether it
was an override).

Promotion requires:

- a valid **alias name** (`^[a-z0-9][a-z0-9\-_]*$`) — a bad name is rejected `422`;
- an **approver** (`approved_by`) — promotion is never anonymous;
- for a **non-recommended** (override) model, an explicit
  `acknowledge_non_recommended=true` — else `422`;
- a **trained** model first — promoting before training is `422`.

Re-promoting the same alias name repoints the existing alias (registry upsert
semantics). **Compare and promote stay separate** — promote performs no
ranking or comparison; it only registers and aliases the already-trained champion.

## Endpoint reference

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/model-selection/runs` | Submit an async comparison (202) |
| GET | `/model-selection/{id}` | Poll progress / fetch terminal results |
| POST | `/model-selection/{id}/train-winner` | Train the ranked winner |
| POST | `/model-selection/{id}/train-selected` | Train a chosen candidate (override) |
| POST | `/model-selection/{id}/predict` | Forecast + inventory decision |
| POST | `/model-selection/{id}/promote` | Promote to a registry alias (audited) |

## Notes & caveats

- Backtest accuracy reflects historical fit, not a guarantee of future
  performance; metrics measure correlation with past demand, not causation.
- The decision layer is **deterministic** — no LLM is involved.
- V2 (richer feature frame) runs promote as V2: the registry run records the
  real `feature_frame_version`.
