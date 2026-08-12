# Operations

Running the system past the first demo: work queues, batches, artifacts, health, and the upkeep that keeps results trustworthy.

**Purpose:** the day-two concerns — what accumulates, what can wedge, and what to watch.
**Intended reader:** operators maintaining a working install.

## What you'll accomplish

An understanding of how asynchronous work flows through the system, where its outputs land on disk, and how to read the operational surface at `/ops`.

## Jobs: the unit of asynchronous work

Training, prediction, and backtesting all run as **jobs** rather than blocking HTTP calls.

| Endpoint | Purpose |
|---|---|
| `POST /jobs` | Submit a `train`, `predict`, or `backtest` job; returns a `job_id`. |
| `GET /jobs` | List jobs with filters and sorting. |
| `GET /jobs/{job_id}` | Status and result JSON. |
| `DELETE /jobs/{job_id}` | Cancel a pending job. |

A job carries its parameters, its result, any error detail, and a link to the model run it produced. **Explorer → Jobs** is the same data in the dashboard, with live status polling and a cancel action.

`DELETE` cancels a **pending** job cleanly. A job already executing a model fit is a different matter — see [Cancellation and drain](#cancellation-and-drain).

Job records are retained for `jobs_retention_days` (default 30).

## Batches: many jobs as one submission

A **batch** expands a matrix — (store, product) pairs × model configurations — into many child items and runs them with bounded concurrency.

| Endpoint | Purpose |
|---|---|
| `POST /batch` | Submit a batch. |
| `GET /batch` | List batches. |
| `GET /batch/{batch_id}` | Batch status and per-item results. |
| `DELETE /batch/{batch_id}` | Cancel a batch (drains in-flight children). |

Two limits shape behavior, and both fail loudly rather than silently degrading:

**Scope.** Expanded scope is capped by `batch_max_scope_expansion` (default 1000). A batch that would expand past it is **rejected at submission**, not queued and truncated. Narrow the pair list or the model matrix.

**Concurrency.** Effective parallelism is `min(batch_job.max_parallel, batch_global_max_parallel)`. The global default is `4`, sized for the Compose Postgres pool (`pool_size=5`, `max_overflow=10`). Raising it without raising the pool surfaces as connection-pool exhaustion under load, not as faster throughput.

The dashboard equivalent is **Visualize → Batch Runner**, which offers five prefilled sweep presets — see [Backtesting](../analyst/backtesting.md).

## Cancellation and drain

**A scikit-learn or LightGBM fit cannot be cancelled mid-call.** This is a property of the libraries, not a gap in the system, and it shapes the cancellation contract.

When you cancel a batch or a champion-selection run, the API stops scheduling new work and then *waits* for in-flight fits to finish. That wait is bounded:

- `batch_cancel_drain_timeout_seconds` (default 30)
- `model_selection_cancel_drain_timeout_seconds` (default 30)

Exceeding the timeout returns an RFC 7807 **504**. That response means "the drain did not complete within the window" — **not** "cancellation failed". The batch is still cancelling; a long fit is simply still running. Re-check status rather than re-issuing the cancel.

## The operational surface: `/ops`

Three read-only endpoints back the Control Center page:

| Endpoint | What it answers |
|---|---|
| `GET /ops/summary` | Overall operational state. |
| `GET /ops/retraining-candidates` | Which models look due for a refresh. |
| `GET /ops/model-health` | Health of registered models and their aliases. |

The page surfaces **stale aliases** as a dedicated card with a reason chip per row — `newer success run`, `artifact not verified`, `run not success`, or `V mismatch`. These are the routine signals that a promoted model needs attention. Their meanings and the promotion gate are covered in [Champion selector](../analyst/champion-selector.md).

Of the four, **`artifact not verified` is the one to treat as urgent**: it means the file backing a promoted alias no longer matches its recorded SHA-256.

## What accumulates on disk

Four artifact roots, all configurable:

| Setting | Default | Holds |
|---|---|---|
| `forecast_model_artifacts_dir` | `./artifacts/models` | Fitted model artifacts. |
| `backtest_results_dir` | `./artifacts/backtests` | Backtest result files. |
| `registry_artifact_root` | `./artifacts/registry` | Registry-tracked artifacts. |
| `showcase_export_root` | `./artifacts/showcase` | Workspace export bundles with manifests and checksums. |

In container mode these live in the `forecastlab_artifacts` named volume, which survives `make docker-down`.

**Artifacts are what make a run verifiable.** Deleting a model artifact does not delete its registry row — it produces a run whose metrics still display but whose artifact verification now fails, and whose feature-importance endpoint returns `422`. If you are reclaiming space, archive runs through the registry rather than deleting files underneath it.

## Model runs and duplicates

`registry_duplicate_policy` (default `detect`) decides what happens when a run duplicates an existing one:

- `detect` — flag the duplicate but allow it.
- `deny` — reject it.
- `allow` — record it without comment.

`detect` is the useful default: it surfaces accidental repeat work without blocking a deliberate re-run.

## Logs

Structured logging via `structlog`. Two settings control it: `log_level` (default `INFO`) and `log_format` — `json` for machine-readable output, `console` for readable local development.

Every request carries a request ID via `RequestIdMiddleware`, which is the join key between a client-side failure and the server-side log lines for that request.

**Log key names, never key values.** That rule is in [AGENTS.md](../../../AGENTS.md); secrets must never reach a log line, and `GET /config/ai` masks API keys for the same reason.

## Routine upkeep

**After every `git pull`:** `uv run alembic upgrade head`. Migrations are forward-only, and a missed one surfaces as `relation "…" does not exist`.

**Before trusting a promoted model:** check `GET /ops/model-health` and confirm no alias is flagged `artifact not verified`.

**When comparing models:** hold the dataset fixed. Changing seed or scenario *and* model at once measures nothing. See [Seeding data](seeding-data.md).

**When results look surprisingly good:** suspect leakage first, and run `app/features/featuresets/tests/test_leakage.py`. Then remember the data is synthetic — see [Backtesting](../analyst/backtesting.md).

## Next

- [Dashboard tour](../analyst/dashboard-tour.md) — the operational pages in the UI.
- [Artifacts and the registry](../integrator/artifacts-and-registry.md) — the integrity contract in detail.
