# Advanced Forecasting Guide

This guide explains the interactive controls landed by **PRP-37 — Forecast
Intelligence C** (the operator-facing surface for the V2 feature contract and
the model zoo introduced by PRP-35 and PRP-36). It is RAG-indexable: ask the
Chat agent any question about model families, feature packs, horizon buckets,
or champion/challenger workflows and it will cite this document.

## Model families

ForecastLabAI groups its models into three families. The Family is a
property of the model code, not a label you pick — it is what the segmented
**Family** Tabs control on `/visualize/forecast` and `/visualize/backtest`
filter the Model Select against.

| Family   | Members                                                                                            | When it shines |
|----------|----------------------------------------------------------------------------------------------------|----------------|
| Baseline | `naive`, `seasonal_naive`, `moving_average`, `weighted_moving_average`, `seasonal_average`         | Sanity check, target-only history, very short windows |
| Tree     | `regression` (HistGBR), `lightgbm`, `xgboost`, `random_forest`                                     | Mid-to-long horizons with rich feature signal |
| Additive | `prophet_like` (Ridge additive), `trend_regression_baseline`                                       | Strong yearly seasonality, interpretable coefficients |

Baselines do **not consume features**. Tree and additive families do — and only
those families surface the V2 feature-frame option.

## Feature frame: V1 vs V2

The **Feature frame** Select is the second control in the Train-a-new-model
row. It chooses how the model sees the past.

- **V1 — target-only.** The classic lags + same-DOW mean. Every model in
  every family can train on V1.
- **V2 — feature-aware.** The PRP-35 contract. Adds eleven optional
  *feature packs* (see below). Available for tree and additive families only;
  baselines reject it with a tooltip explanation.

The backend default is V1; the UI only sends `feature_frame_version=2` when
the operator explicitly picks V2. A V1 train with `feature_groups` is
rejected by the backend with a 422.

## Feature packs (V2 only)

When V2 is picked, the **Feature packs** toggle row appears. Each pack is a
named subset of the V2 feature columns:

| Pack ID              | What it carries |
|----------------------|------------------|
| `target_history`     | Lag features and same-day-of-week mean |
| `rolling`            | Rolling means over multiple windows |
| `trend`              | 30-day and 90-day trend |
| `calendar`           | Day-of-week, month, sin/cos calendar signals |
| `price_promo`        | Price level and promotion indicators |
| `inventory`          | On-hand stock and stockout flags |
| `lifecycle`          | Product lifecycle stage |
| `replenishment`      | Inbound stock cadence |
| `returns`            | Return intensity |
| `exogenous_weather`  | Weather signals (when seeded) |
| `exogenous_macro`    | Macro signals (when seeded) |

Use the **Use defaults** button to load the six packs the V2 contract uses by
default (`target_history`, `calendar`, `rolling`, `trend`, `price_promo`,
`lifecycle`). The **Clear** button removes every pack; submitting with an
empty selection forwards `feature_groups: undefined` to the backend (treated
as the default set on the server).

A pack may carry a per-row safety chip (`Safe`, `Conditionally safe`,
`Requires supplied data`). The chip is rendered when the server returns a
`feature_safety_classes` map for the run. A `Requires supplied data` chip
means the pack reads a column the production pipeline must supply (e.g.
inventory or replenishment) — promote a run that uses it only if your
production pipeline can keep that column populated.

## Per-horizon-bucket metrics

The backtest visualization now surfaces a **Per-horizon-bucket** card under
the existing fold-metric chart, rendered only when the response carries
`bucketed_aggregated_metrics`. It splits the forecast error by horizon
distance:

| Bucket id   | Horizon range  |
|-------------|----------------|
| `h_1_7`     | Days 1-7       |
| `h_8_14`    | Days 8-14      |
| `h_15_28`   | Days 15-28     |
| `h_29_plus` | Days 29+       |

Empty buckets are dropped from the response. Unknown bucket ids (a forward-
compatible bucket from a newer backend) are appended to the end of the table
alphabetically.

Pick the displayed metric (MAE / sMAPE / WAPE / Bias / RMSE) with the
Select to the right of the card title. **RMSE** is a key inside the
`aggregated_metrics` dict — surfaced as a fourth tile on the Aggregated
Metrics card when the backend emits it.

## Baseline vs feature-aware comparison

When the backtest response carries `baseline_results` (a non-empty list of
ModelBacktestResult rows), a **Baseline vs feature-aware** table renders
below the bucket card. Every baseline runs on the **same folds, identical
splits** as the main model — so MAE / sMAPE / WAPE / RMSE comparisons are
apples-to-apples. Lower wins.

## Champion compatibility

Two runs are **comparable** for champion/challenger evaluation iff
ALL three hold:

1. Same grain (`store_id`, `product_id`).
2. Overlapping data windows.
3. Same `feature_frame_version` (legacy runs without the field default to V1).

The Compare runs page renders a **Champion compatibility** badge that
surfaces the verdict, and the metrics diff table adds a **Feature frame
version** row when at least one of the two runs declares it.

## Stale aliases

The Control Center page now surfaces stale aliases as their own card with a
**Reason** chip per row:

| Reason chip                       | What it means                                                        |
|-----------------------------------|-----------------------------------------------------------------------|
| `newer success run`               | A newer successful run for this grain has landed.                     |
| `artifact not verified`           | The alias's run artifact failed SHA-256 verification.                 |
| `run not success`                 | The alias is pointing at a non-success run (failed or archived).      |
| `V mismatch`                      | The newest comparable run uses a different `feature_frame_version`.   |

Alongside each chip, the row shows the **Alias V** and **Comparable V**
columns so the operator can read the version drift at a glance.

## Safer Promote dialog

The Control Center's **Promote** action now opens a confirmation dialog that
gates the promotion on three conditions:

1. **Artifact verifies.** The dialog auto-fetches the candidate run's
   SHA-256 verification result. A failure renders a red callout and the
   Promote button stays disabled — no operator override.
2. **Worse-WAPE acknowledgement.** When the candidate's latest WAPE is
   HIGHER than the current champion's, a red callout appears with the
   exact deltas and a checkbox the operator must explicitly tick.
3. **Feature-frame-version mismatch acknowledgement.** When the candidate's
   `feature_frame_version` differs from the champion's, an amber callout
   warns that the alias's feature contract will silently change. A
   checkbox the operator must tick releases the Promote button.

The alias name input remains; the dialog defaults the alias to
`production`. Cancel preserves no state — both acknowledgements reset.

## Batch sweep presets

The Batch Runner page now hosts a **Sweep preset** Select with five built-in
presets. Picking a preset overwrites the matrix; the matrix can still be
hand-edited afterward.

| Preset                          | What it loads |
|---------------------------------|---------------|
| Quick baseline sweep            | All five baseline models on V1 |
| Feature-aware comparison        | Regression / LightGBM / XGBoost / RandomForest / Prophet-like on V2 with default packs |
| Champion/challenger refresh     | Champion + strongest challenger from the registry (supplied by the page) |
| Stockout-sensitive products     | Regression on V2 with the inventory + replenishment + returns packs |
| High-WAPE recovery              | Every feature-aware model on V2 with default packs |

Below the preset Select is the **Sweep matrix** picker — a checkbox grid of
model × V1/V2. Toggling a V2 cell adds a per-row feature-packs editor below
the grid. The matrix caps at 24 rows by default (configurable on the
picker).

## Anti-patterns

- **Do not** pick V2 for a baseline model — V2 has no effect on a model that
  ignores features. The UI disables this combination with a tooltip.
- **Do not** promote a worse run without checking the explicit
  acknowledgement checkbox. The gate exists for a reason.
- **Do not** promote across a feature-frame-version boundary without
  verifying your production pipeline supplies the columns the new V demands.
- **Do not** read RMSE from `aggregated_metrics["rmse"]` for old jobs —
  RMSE landed in PRP-36, and pre-PRP-36 backtest jobs in the registry will
  not carry it. The UI omits the RMSE tile in that case.
