# Forecasting

The eleven model types, the three families they group into, and the feature-frame contract that decides what a model is allowed to see.

**Purpose:** pick a model deliberately and know what it can and cannot do.
**Intended reader:** analysts training models from the dashboard or the API.

## What you'll accomplish

A trained model at a chosen grain, and the vocabulary to explain why you picked it.

## The grain

Every forecast in ForecastLabAI is made for one **(store, product) pair**, one day at a time, out to a horizon. The horizon defaults to 14 days (`forecast_default_horizon`) and is capped at 90 (`forecast_max_horizon`).

Grain matters beyond training: two runs are only comparable if they share one.

## The three families

**Family is a property of the model code, not a label you choose.** It is computed from the model type by `app/shared/model_taxonomy.py` and never stored in the database — it appears on API responses as a computed field and drives the Family badge in the dashboard.

| Family | Model types | Where it shines |
|---|---|---|
| **Baseline** | `naive`, `seasonal_naive`, `moving_average`, `weighted_moving_average`, `seasonal_average` | Sanity checks, target-only history, very short windows. |
| **Tree** | `regression` (HistGradientBoostingRegressor), `lightgbm`, `xgboost`, `random_forest` | Mid-to-long horizons with rich feature signal. |
| **Additive** | `prophet_like` (Ridge additive), `trend_regression_baseline` | Strong yearly seasonality; interpretable coefficients. |

Eleven model types in total. Note that `trend_regression_baseline` classifies as **additive**, not baseline, despite its name — it fits a trend rather than repeating history.

An unknown model type classifies as `baseline` and logs a warning rather than raising, so a model added before the taxonomy map is updated degrades gracefully instead of breaking the dashboard.

### Availability

Three model types are opt-in and absent from the picker until enabled:

| Model | Needs |
|---|---|
| `lightgbm` | `uv sync --extra ml-lightgbm` **and** `FORECAST_ENABLE_LIGHTGBM=true` |
| `xgboost` | `uv sync --extra ml-xgboost` **and** `FORECAST_ENABLE_XGBOOST=true` |
| `random_forest` | `FORECAST_ENABLE_RANDOM_FOREST=true` only — pure scikit-learn |

The flags are **permission gates, not installation checks**. Setting one without the library succeeds at startup and fails later at fit or unpickle time. All three need a backend restart.

### Why baselines are first-class

Five baselines ship as real, rankable models. "Predict the same weekday last week" is a genuinely strong forecaster for seasonal retail demand, and a gradient-boosted model that cannot beat it has earned no complexity budget.

A baseline winning a comparison is a **legitimate result**, not a misconfiguration. It happens regularly on short histories and synthetic data — and you would never learn it without the baseline in the race.

## The feature frame: V1 versus V2

The feature frame is the versioned contract for what a model sees.

**V1 — target-only.** Lags plus same-day-of-week means, derived from the sales history alone. Every model in every family can train on V1. **It is the backend default.**

**V2 — feature-aware.** The richer contract, adding eleven optional feature packs. Available to **tree and additive families only** — baselines ignore features, so the UI disables the combination with a tooltip rather than letting you pick a no-op.

Two rules the backend enforces:

- The UI sends `feature_frame_version=2` only when you explicitly pick V2.
- A **V1 request carrying `feature_groups` is rejected with `422`.** Packs are a V2 concept; silently ignoring them would hide a mistake.

## The eleven feature packs

Each pack is a named subset of V2 columns you toggle independently.

| Pack | What it carries | On by default |
|---|---|---|
| `target_history` | Lag features and same-day-of-week means | ✅ |
| `calendar` | Day-of-week, month, sin/cos calendar signals | ✅ |
| `rolling` | Rolling means over multiple windows | ✅ |
| `trend` | 30-day and 90-day trend | ✅ |
| `price_promo` | Price level and promotion indicators | ✅ |
| `lifecycle` | Product lifecycle stage | ✅ |
| `inventory` | On-hand stock and stockout flags | — |
| `replenishment` | Inbound stock cadence | — |
| `returns` | Return intensity | — |
| `exogenous_weather` | Weather signals (when seeded) | — |
| `exogenous_macro` | Macro signals (when seeded) | — |

The six defaults are what the backend uses when `feature_groups` is omitted. The five off-by-default packs read sidecar tables that a smaller seeded database may not populate meaningfully — enabling one whose signal was never seeded contributes nothing. If you want to study inventory-aware forecasting, seed `stockout_heavy` first. See [Seeding data](../operator/seeding-data.md).

In the dashboard, **Use defaults** loads the six; **Clear** empties the selection, which forwards no `feature_groups` at all and is therefore treated by the server as the default set — clearing does not mean "no features".

### Disabled means absent, not blank

Disabling a pack **omits its columns entirely** — it does not fill them with NaN placeholders. That distinction matters when you read a feature-importance panel: a column that is not there cannot rank.

A NaN *inside an enabled* pack means something different: "the source data is unknown for this day." The tree models handle NaN natively rather than requiring imputation, so a partially-populated signal is usable rather than fatal.

### Safety classes

A pack may carry a safety chip when the server returns a `feature_safety_classes` map: `Safe`, `Conditionally safe`, or `Requires supplied data`.

**`Requires supplied data` is the one to act on.** It means the pack reads a column your production pipeline must keep populated — inventory or replenishment, typically. Promote a run using such a pack only if you can guarantee that column keeps arriving. A model silently starved of a feature it was trained on does not fail loudly; it just gets worse.

## Leakage: the guarantee underneath all of this

A feature that sees the future makes a model look excellent and be worthless.

Every feature is built so this cannot happen structurally — `shift(lag)` and `shift(1).rolling()` patterns with entity-aware grouping, computed only up to a cutoff date. The guarantee is locked by `app/features/featuresets/tests/test_leakage.py`, which the repository treats as the specification: weakening it is explicitly forbidden.

Practically: **if a metric looks too good, suspect leakage before celebrating**, and run that test. It is the fastest way to tell a real result from an artifact.

Three settings bound feature cost — `feature_max_lookback_days` (1095), `feature_max_lag` (365), `feature_max_window` (90). These are budget ceilings, not safety controls; safety comes from the code.

## Training a model

### From the dashboard

**Visualize → Forecast**, in the *Train a new model* card: pick a family, then a model type (the list filters to the family), then the feature frame, then — for V2 — the packs. Submit, and the page tracks the job.

### From the API

```bash
# Compute features up to a cutoff
curl -X POST http://localhost:8123/featuresets/compute -H 'Content-Type: application/json' -d '{...}'

# Train
curl -X POST http://localhost:8123/forecasting/train -H 'Content-Type: application/json' -d '{...}'

# Predict
curl -X POST http://localhost:8123/forecasting/predict -H 'Content-Type: application/json' -d '{...}'
```

`POST /featuresets/preview` returns sample rows without committing, which is the quickest way to see what a pack actually contributes.

Training runs as a **job** — see [Operations](../operator/operations.md).

## The capability limit worth knowing early

**A feature-aware model cannot auto-forecast forward.** To predict day *N+7*, a tree or additive model needs the feature values for that day — future prices, future promotions, future inventory. Those are assumptions, not facts.

Rather than fabricate them, the system blocks the auto-forecast and routes you to the **What-If Planner**, where you state the assumptions explicitly and see them labelled. Baselines are unaffected: they only need history.

This is why a baseline can be the *practical* choice even when a feature-aware model backtests better. See [Demand and planning](demand-and-planning.md).

## Feature importance, and how to read it

For a non-baseline run, the run detail page shows the canonical feature columns and an importance panel.

- **Tree family** — non-negative bars from the booster's native `feature_importances_`. The exact meaning varies by library (LightGBM's `split`, XGBoost's `weight`); the panel labels which.
- **Additive `prophet_like`** — signed Ridge coefficients: positive renders green with an up arrow, negative red with a down arrow. The sign is preserved because direction is the interpretable part.

> **Correlation, not causation.** Importance reflects how much a feature reduced the model's *training* error. It is not evidence about real-world demand drivers, and two products with similar importance profiles need not share a business cause.

When the panel is unavailable, the status code says why: **400** the run is a baseline (nothing is wrong), **404** the run or job is not in the registry, **422** no artifact yet, artifact deleted, a missing `ml-*` extra at unpickle time, or an estimator that does not expose importances. Note `regression` uses scikit-learn's `HistGradientBoostingRegressor`, which **does not** expose `feature_importances_` — a 422 there is permanent.

## Choosing a model

1. **Always include baselines.** They set the bar.
2. **Reach for V2 only with signal to feed it.** V2 on a dataset with no promotions or inventory dynamics adds columns, not information.
3. **Match the family to the question.** Strong yearly seasonality with a need to explain coefficients → additive. Rich features and mid-to-long horizons → tree. Short history → baseline.
4. **Mind the forward-forecast limit.** If you need to forecast forward without stating assumptions, a baseline is the model that can.
5. **Let the backtest decide.** Intuition about which model *should* win is exactly what backtesting exists to check — [Backtesting](backtesting.md).

## Next

- [Backtesting](backtesting.md) — measuring whether the model you picked is any good.
