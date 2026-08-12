# Glossary

The vocabulary this manual uses, defined once and used consistently.

**Purpose:** settle what each term means in *this* system, especially where a general ML word has a specific local meaning.
**Intended reader:** everyone; skimmable and cross-linked.

## Retail and demand

**SKU** — a stock-keeping unit; one row in the `product` table. This manual uses "product" and "SKU" interchangeably.

**Grain** — the level a forecast is made at. In ForecastLabAI the grain is always a **(store, product) pair** over daily time steps. Two model runs are only comparable if they share a grain.

**Horizon** — how many days ahead a forecast predicts. Bounded by `forecast_max_horizon` (default 90); the default is `forecast_default_horizon` (14).

**Lead time** — the days between placing a replenishment order and receiving it. An input to the safety-stock heuristic, not something the models predict.

**Safety stock** — buffer inventory held to absorb demand variability over the lead time. Computed here by a deterministic, clearly-labelled heuristic — see [Champion selector](analyst/champion-selector.md).

**Reorder point** — expected demand over the lead time plus safety stock; the level at which you should reorder.

**Exogenous signal** — a driver outside the sales history itself (weather, macro indicators). Stored in `exogenous_signal` and exposed as optional V2 feature packs.

## Data and features

**Feature** — a model-ready column derived from raw history: a lag, a rolling statistic, a calendar flag, a price level.

**Leakage** — letting information from the future reach a model that is supposed to predict the future. It inflates accuracy and invalidates the measurement. Prevented structurally with `shift(lag)` and `shift(1).rolling()` patterns, and locked by `app/features/featuresets/tests/test_leakage.py`, which is the spec.

**Time-safe** — a feature computation that provably cannot leak. The word appears throughout the API and this manual with that exact meaning.

**Feature frame** — the versioned contract describing which columns a model consumes.
- **V1** — target-only: lags plus same-day-of-week mean. Every model can train on V1. It is the backend default.
- **V2** — feature-aware: the richer contract, with eleven optional feature packs. Available to the tree and additive families only.

**Feature pack** — a named subset of V2 columns you can toggle on or off (`calendar`, `price_promo`, `inventory`, and so on). See [Forecasting](analyst/forecasting.md).

**Feature safety class** — a per-pack chip: `Safe`, `Conditionally safe`, or `Requires supplied data`. The last one means the pack reads a column your production pipeline must keep populated.

**Cutoff date** — the date a feature computation treats as "now". Nothing after it may influence a feature.

## Models

**Model type** — one of the eleven concrete forecasters (`naive`, `regression`, `prophet_like`, …). The full list is in [Forecasting](analyst/forecasting.md).

**Model family** — the computed grouping of a model type into `baseline`, `tree`, or `additive`. Derived from `model_type` by `app/shared/model_taxonomy.py`; **never stored in the database**, and surfaced on API responses as a computed field. An unknown model type classifies as `baseline` so a newly added model does not break the dashboard.

**Baseline** — a deliberately simple forecaster (last value, same day last week, moving average). Baselines exist as honest comparison points: a machine-learning model is only worth using if it beats them.

**Feature-aware model** — a tree- or additive-family model that consumes a feature frame. These cannot auto-forecast forward without a future feature frame — see the capability limit in [Champion selector](analyst/champion-selector.md).

## Measurement

**Backtest** — replaying history with time-series cross-validation to measure how accurate a model *would have been*.

**Fold** — one train/test split within a backtest. Splits are **rolling** (fixed-width training window) or **expanding** (training window grows).

**MAE** — mean absolute error, in units. Interpretable, but not comparable across SKUs of different volume.

**sMAPE** — symmetric mean absolute percentage error. Scale-free, but unstable when actual demand is near zero.

**WAPE** — weighted absolute percentage error: total absolute error divided by total actual demand. **The default ranking metric**, because it is scale-free *and* stable at low volumes.

**Bias** — signed average error. **Positive bias means the model under-forecasts** (stockout risk); negative means it over-forecasts (overstock risk).

**RMSE** — root mean squared error; penalises large misses more than MAE.

**Stability** — how consistent a model's error is across folds. A model that is accurate on average but wild fold-to-fold is a risk.

**Horizon bucket** — error grouped by forecast distance: `h_1_7`, `h_8_14`, `h_15_28`, `h_29_plus`. Near-term and far-term accuracy are different questions.

## Registry and lifecycle

**Model run** — one training execution, tracked in `model_run` with its config, metrics, and artifact. Moves through `pending → running → success` (or `failed`).

**Artifact** — the serialized fitted model on disk, with a SHA-256 checksum the registry can re-verify on demand.

**Alias** — a human-friendly, movable pointer to one successful run (`production`, `champion`). Stored in `deployment_alias`. An alias may point only to a successful run.

**Stale alias** — an alias the system flags as possibly out of date, with a reason: a newer successful run exists, the artifact failed verification, the target run is no longer successful, or the feature-frame version drifted.

**Promotion** — pointing an alias at a run. Approval-gated and audited: it records who approved it, the reason, and whether it overrode the recommendation. **Never automatic.**

**Champion / challenger** — the currently promoted model versus a candidate competing to replace it. Two runs are comparable only if they share a grain, have overlapping data windows, and use the same feature-frame version.

**Override** — training or promoting a model that was *not* the ranked recommendation. Flagged `is_override=true` and audited.

## Jobs and batches

**Job** — an asynchronous unit of work (`train`, `predict`, or `backtest`), tracked in `job` with status and result JSON.

**Batch** — a matrix of jobs submitted together, expanded across (store, product) pairs × model configs. Bounded by `batch_max_scope_expansion`.

**Sweep preset** — a named, prefilled batch matrix (for example "Quick baseline sweep").

**Drain** — the wait when cancelling a batch or selection run, while in-flight fits finish. A scikit-learn or LightGBM fit **cannot be cancelled mid-call**, which is why the drain has a timeout.

## Agents and RAG

**RAG** — retrieval-augmented generation: answering from indexed documents rather than model memory alone.

**Chunk** — a passage a document is split into for embedding. Markdown splits by heading; OpenAPI splits by endpoint.

**Embedding** — the numeric vector representing a chunk's meaning, stored in Postgres via **pgvector**.

**Cosine similarity** — how retrieval scores a chunk against a query. Results below `rag_similarity_threshold` (default 0.7) are not returned.

**Agent** — a PydanticAI conversational assistant. Two types: **`rag_assistant`** (answers from the knowledge base) and **`experiment`** (can run forecasting experiments).

**Tool** — a typed function an agent may call. Read-only tools run immediately.

**Human-in-the-loop (HITL) approval gate** — the mechanism that pauses an agent before a *mutating* tool runs and waits for a person. The gated set is `agent_require_approval` — by default `create_alias`, `archive_run`, `save_scenario`.

**Session** — one conversation, bounded by a token budget, a tool-call cap, and a timeout.

## Scenarios

**Scenario plan** — a saved set of what-if assumptions (price, promotion, holiday, inventory, lifecycle) applied to an existing forecast. Stored in `scenario_plan`.

**`model_exogenous`** — the scenario method that genuinely **re-forecasts** through the assumptions using a regression baseline.

**Heuristic adjustment** — the fallback scenario method: a deterministic, clearly-labelled adjustment rather than a real re-forecast. The dashboard always shows which of the two produced a result.

## System shape

**Vertical slice** — a self-contained feature directory under `app/features/<slice>/` holding its own models, schemas, service, routes, and tests. There are **19**. A slice may not import another slice; shared code lives in `app/core/` or `app/shared/`.

**Problem details** — the RFC 7807 `application/problem+json` error envelope every endpoint uses. See [API reference](integrator/api-reference.md).

**The Forge** — the synthetic data seeder. Everything it produces is generated, reproducible from a seed, and **not real retail data**.

**Showcase** — the `/showcase` page that runs the whole pipeline live in the browser as streamed status cards.
