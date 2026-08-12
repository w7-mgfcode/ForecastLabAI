# Champion selector

The guided workflow that turns "which model is best for this store and product?" into a decision someone signed for.

**Purpose:** compare candidates, decide, train, forecast, and promote — with every gate explained.
**Intended reader:** analysts choosing a model to put into service.

## What you'll accomplish

A ranked comparison at one grain, a trained winner, a business reading of its forecast, and — if you approve it — an audited promotion to a registry alias.

It lives at **`/visualize/champion`** and is served by the `/model-selection/*` API.

> **The golden rule of promotion:** the app *recommends* a champion; a human *approves* it; and the decision is **recorded**. Promotion is never automatic.

## The journey

```
Select → Run comparison → Results → Decide / override → Train → Forecast → Interpret → Promote
```

## 1 · Select and check availability

Pick a store, a product, a time period, a horizon (1–90 days), and the candidate models.

The page first checks **data availability** for the pair and recommends a cross-validation split. A pair with too little history is flagged *unusable* and the comparison is refused with `400` — before any compute is spent. That refusal is a real finding: it means you cannot honestly measure anything at that grain yet, not that the tool is broken.

## 2 · Run the comparison

`POST /model-selection/runs` submits an **asynchronous** run, returning `202` with a monitor URL. The page polls to a terminal state.

Each candidate is backtested with time-series cross-validation on the **same folds**, and results are ranked deterministically.

Concurrency is bounded by `model_selection_global_max_parallel` (default 4); set it to `1` for sequential execution.

## 3 · Read the ranking

**Ranking is by WAPE**, with a fixed tie-break chain:

```
WAPE  →  sMAPE  →  |bias|  →  MAE
```

The chain is fixed so ranking is reproducible — the same results always produce the same winner, with no hidden tie-breaking. Why WAPE leads is explained in [Backtesting](backtesting.md#why-wape-is-the-default).

The winner, the runners-up, **and any failed candidates** are all shown. A candidate that failed is information, not noise.

## 4 · Decide — accept or override

The recommended winner is pre-selected. Two paths:

- **Accept** → `POST /model-selection/{id}/train-winner` trains the ranked winner.
- **Override** → `POST /model-selection/{id}/train-selected` trains a different candidate.

Overriding requires confirming an explicit warning that names the recommended model and the WAPE gap, and lets you record a reason. The override is flagged `is_override=true` and audited.

Override exists because ranking is not omniscient. A model with marginally worse WAPE but better bias direction, better stability, or fewer feature dependencies can be the right operational choice. The system's job is to make that choice **visible and attributed**, not to prevent it.

A candidate that *failed its backtest* is still override-trainable — training and backtesting are independent operations.

## 5 · Forecast

`POST /model-selection/{id}/predict` generates the horizon forecast. The response carries the **peak** and **low** demand days plus a **decision** block.

> **Capability limit.** A feature-aware model — `regression`, `prophet_like`, `lightgbm`, `xgboost`, `random_forest` — **cannot auto-forecast here.** It needs a future feature frame, and the system will not invent one. The page shows a blocked state and routes you to the [What-If Planner](demand-and-planning.md).

This is a real constraint on model choice, not an inconvenience: a model that backtests better but cannot forecast forward without assumptions may be the worse practical pick. Weigh it before promoting.

## 6 · Interpret

The **business interpretation** panel restates why the model won, the expected demand over the lead time, and the bias risk:

> Positive bias means the model **under**-forecasts — stockout risk. Negative bias means it **over**-forecasts — overstock risk.

The **safety stock** panel shows a deterministic heuristic:

```
safety_stock     = z(service_level) · σ_daily · √(lead_time_days)
expected_demand  = average_demand · lead_time_days
reorder_point    = expected_demand + safety_stock
```

`σ_daily` is the standard deviation of the daily forecast. `z` comes from a fixed service-level table — 90% → 1.2816, 95% → 1.6449, 97.5% → 1.9600, 99% → 2.3263 — snapping to the nearest level in between. Adjust lead time or service level and recompute.

> **This is a heuristic, and it is labelled as one.** It models demand variability with a constant lead time. It is not a full inventory optimisation — it ignores supply variability, order costs, and capacity — and it **never** influences model ranking. The decision layer is entirely deterministic; **no LLM is involved.**

## 7 · Promote

`POST /model-selection/{id}/promote` registers the trained model as a registry `model_run` (transitioned to SUCCESS with a verified artifact) and points a **registry alias** at it. It records a `promotion_decision` audit: approver, alias, run id, decision, reason, and whether it was an override.

Four preconditions, each returning `422` with its own message:

| Requirement | Why |
|---|---|
| Valid alias name matching `^[a-z0-9][a-z0-9\-_]*$` | Aliases are addressable identifiers. |
| `approved_by` present | **Promotion is never anonymous.** |
| `acknowledge_non_recommended=true` for an override | Promoting a non-recommended model must be deliberate. |
| The model is trained first | You cannot promote what does not exist. |

Re-promoting the same alias name repoints the existing alias — registry upsert semantics.

**Compare and promote stay separate.** Promote performs no ranking or comparison; it only registers and aliases the already-trained champion. Keeping them apart is what makes the audit trail meaningful: the comparison is evidence, the promotion is a decision.

### The Promote dialog's three gates

Promoting from the Control Center opens a confirmation dialog gating on:

1. **Artifact verification.** The dialog auto-fetches the run's SHA-256 result. A failure renders a red callout and the Promote button **stays disabled — no operator override.** A corrupt or missing artifact is not a judgement call.
2. **Worse-WAPE acknowledgement.** If the candidate's WAPE is higher than the current champion's, a red callout shows the exact deltas and requires an explicit checkbox.
3. **Feature-frame-version mismatch acknowledgement.** If the candidate's `feature_frame_version` differs from the champion's, an amber callout warns that the alias's feature contract will silently change, and a checkbox releases the button.

The alias defaults to `production`. Cancel preserves nothing — both acknowledgements reset.

Gate 3 is the subtle one: nothing *fails* when the contract changes. A downstream pipeline feeding the alias keeps working while quietly supplying the wrong columns. That is why it is a deliberate acknowledgement rather than a warning banner.

## Comparability: when two runs can be compared

Two runs are comparable for champion/challenger evaluation **if and only if all three hold**:

1. **Same grain** — same `store_id` and `product_id`.
2. **Overlapping data windows.**
3. **Same `feature_frame_version`** — runs predating the field default to V1.

The Compare page renders a **Champion compatibility** badge with the verdict, and the metrics-diff table adds a feature-frame-version row when either run declares one.

Comparing across a grain or a frame version is not a stricter-or-looser judgement call; it is comparing answers to different questions.

## Stale aliases

The Control Center flags stale aliases with a reason chip, alongside **Alias V** and **Comparable V** columns showing version drift:

| Chip | Meaning |
|---|---|
| `newer success run` | A newer successful run exists for this grain. |
| `artifact not verified` | The alias's artifact failed SHA-256 verification. |
| `run not success` | The alias points at a failed or archived run. |
| `V mismatch` | The newest comparable run uses a different `feature_frame_version`. |

`artifact not verified` is the urgent one — something promoted is no longer what it claimed to be.

## Anti-patterns

- **Don't promote without checking bias direction.** Two models with equal WAPE and opposite bias fail in opposite ways.
- **Don't promote a worse run by reflex-ticking the acknowledgement.** The checkbox exists to make you read the deltas.
- **Don't cross a feature-frame boundary without verifying your pipeline supplies the columns the new version demands.**
- **Don't treat the safety-stock number as an inventory plan.** It is a labelled heuristic.
- **Don't read a ranking as a causal claim.** Backtest accuracy is historical fit on synthetic data.

## Next

- [Demand and planning](demand-and-planning.md) — forecasting forward with explicit assumptions.
- [Artifacts and the registry](../integrator/artifacts-and-registry.md) — the integrity contract behind the promotion gate.
