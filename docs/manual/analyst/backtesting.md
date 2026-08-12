# Backtesting

How ForecastLabAI measures accuracy, what each metric means, and what none of them can tell you.

**Purpose:** read a backtest result correctly, including its limits.
**Intended reader:** analysts comparing models, and anyone about to quote a number.

## What you'll accomplish

A defensible answer to "how accurate is this model?" — and the judgement to know when that answer does not transfer.

## What a backtest is

A backtest replays history: train on data up to a point, predict forward, compare against what actually happened, then slide the window and repeat. Each train/test split is a **fold**.

This is not the same as a train/test split on shuffled rows — order matters. Shuffling time-series data lets a model learn from the future, which is the thing everything in this system is built to prevent. See [Forecasting](forecasting.md#leakage-the-guarantee-underneath-all-of-this).

```bash
curl -X POST http://localhost:8123/backtesting/run -H 'Content-Type: application/json' -d '{...}'
```

In the dashboard: **Visualize → Backtest Results**, which can also launch the run in-page.

## Rolling versus expanding

**Rolling** — the training window is a fixed width that slides forward. Each fold trains on the same *amount* of data, from a different period. Use it when you believe recent history matters more, or when you want folds that are directly comparable to each other.

**Expanding** — the training window starts at a minimum and grows. Each fold trains on everything up to its cutoff. Use it when you want to mirror how a model would actually be retrained in production, accumulating history.

Expanding folds are not comparable to each other in difficulty — later folds have more data — so a trend across folds partly reflects training-set size, not just period difficulty. Keep that in mind before reading a rising accuracy curve as improvement.

Three settings bound the design: `backtest_max_splits` (20), `backtest_default_min_train_size` (30 days), and `backtest_max_gap` (30).

## The metrics

| Metric | What it is | Read it when |
|---|---|---|
| **MAE** | Mean absolute error, in units | You want an answer in units: "off by 4 units/day". |
| **sMAPE** | Symmetric mean absolute percentage error | You want a scale-free number and demand is comfortably above zero. |
| **WAPE** | Total absolute error ÷ total actual demand | **The default.** Scale-free *and* stable at low volume. |
| **Bias** | Signed average error | You care about *direction* of error, which inventory always does. |
| **RMSE** | Root mean squared error | Large misses matter disproportionately. |
| **Stability** | Consistency of error across folds | You care whether the model is reliable, not just good on average. |

### Why WAPE is the default

sMAPE is the intuitive scale-free choice, and it misbehaves exactly where retail data lives. As actual demand approaches zero, the percentage error explodes — a single-unit miss on a day with one sale is a 100% error, and a day with zero sales is undefined or degenerate. Intermittent-demand SKUs are common, so a metric that is unstable there is a bad ranking key.

WAPE divides *total* absolute error by *total* actual demand across the whole window. Low-volume days contribute proportionally to their volume instead of dominating. It stays scale-free, so different SKUs are comparable, without the near-zero pathology.

WAPE still has a failure case: if total actual demand over a fold is zero, it is undefined. Two seeder presets deliberately tune their noise to avoid that trap — see [Seeding data](../operator/seeding-data.md).

### Bias has a direction, and the direction matters

**Positive bias means the model under-forecasts** — it predicted less than actually sold, and following it risks **stockouts**.

**Negative bias means the model over-forecasts** — it predicted more than sold, and following it risks **overstock** and tied-up cash.

This is the one metric where the sign carries a business decision, and it is easy to read backwards. Two models with identical MAE and opposite bias fail in opposite, non-interchangeable ways.

### Stability is a risk measure

A model averaging 12% WAPE across folds by scoring 11%, 12%, 13% is a different proposition from one scoring 4%, 8%, 24%. The averages match; the second is not something to plan inventory against. Read stability alongside the headline number, not after it.

## Per-horizon buckets

Accuracy is not uniform across the horizon. Predicting tomorrow is a different problem from predicting five weeks out, and one aggregate number hides that.

When the response carries `bucketed_aggregated_metrics`, a **Per-horizon-bucket** card splits error by forecast distance:

| Bucket | Horizon |
|---|---|
| `h_1_7` | Days 1–7 |
| `h_8_14` | Days 8–14 |
| `h_15_28` | Days 15–28 |
| `h_29_plus` | Days 29+ |

A metric switcher (MAE / sMAPE / WAPE / Bias / RMSE) sits beside the card title. Empty buckets are dropped. Unknown bucket ids from a newer backend are appended alphabetically rather than discarded — forward compatibility by design.

This card is what tells you a model is excellent for replenishment but unreliable for planning, or the reverse. If your decision has a horizon, read the bucket for that horizon rather than the aggregate.

The card renders only when the response carries the data; older jobs will not have it.

## Baseline versus feature-aware comparison

When the response carries `baseline_results`, a comparison table renders below the bucket card.

Every baseline in it runs on the **same folds, with identical splits**, as the main model. That is what makes the comparison meaningful — the models faced the same problem. Lower wins on MAE, sMAPE, WAPE, and RMSE.

If a feature-aware model cannot beat `seasonal_naive` on identical folds, it has not earned its complexity, its training cost, or its forward-forecast limitation. This table is where that gets settled.

## Batch sweeps

To compare many models across many pairs at once, use **Visualize → Batch Runner**. Five presets prefill the matrix:

| Preset | Loads |
|---|---|
| Quick baseline sweep | All five baselines on V1 |
| Feature-aware comparison | Regression / LightGBM / XGBoost / RandomForest / Prophet-like on V2 with default packs |
| Champion/challenger refresh | Champion plus strongest challenger from the registry |
| Stockout-sensitive products | Regression on V2 with inventory + replenishment + returns packs |
| High-WAPE recovery | Every feature-aware model on V2 with default packs |

A preset overwrites the matrix; you can hand-edit afterwards. The matrix caps at 24 rows by default. Batch scope and concurrency limits are in [Operations](../operator/operations.md).

## Reading a result honestly

**A backtest measures historical fit, not future performance.** It says how a model would have done on data it did not train on, in a period that already happened. That is genuinely informative and it is not a guarantee.

**The data is synthetic.** Every number here is measured against data the Forge generated from a seed. The measurements are real and reproducible; they are not evidence about real retail demand. A model that wins here won on patterns the generator created. See [What ForecastLabAI is](../operator/concepts.md#the-honesty-caveat-about-data).

**Metrics measure correlation, not causation.** Neither the accuracy numbers nor the feature-importance panel identify *why* demand moved.

**Suspect leakage before celebrating.** An unusually good score is more often a feature that saw the future than a breakthrough. `app/features/featuresets/tests/test_leakage.py` is the check.

**Compare like with like.** Two runs are comparable only if they share a grain, have overlapping data windows, and use the same feature-frame version — the Compare page badges the verdict. See [Champion selector](champion-selector.md).

## Next

- [Champion selector](champion-selector.md) — turning a comparison into a decision.
