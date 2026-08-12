# API reference

The conventions every endpoint shares, the error envelope, and a map of all twenty endpoint groups.

**Purpose:** enough to call the API confidently and handle its failures correctly.
**Intended reader:** integrators building against ForecastLabAI.

## What you'll accomplish

A working mental model of the API surface, and the ability to parse any error it returns with one code path.

## The authoritative contract is generated

The OpenAPI schema at **http://localhost:8123/docs** is generated from the code and is therefore always current. **It is the contract.** This chapter is written by hand and deliberately does not restate every field — it explains the conventions, the error semantics, and where each capability lives, so you can read the generated schema quickly.

Where this chapter and `/docs` disagree, `/docs` is right.

## Shared conventions

**Validation is Pydantic v2 at every boundary.** Malformed input fails at the edge with a field-level error, never deeper.

**Errors are RFC 7807** `application/problem+json`, uniformly. No endpoint returns an ad-hoc error shape; bare `HTTPException` with a raw string is forbidden by repository rules. One parser handles every error from every endpoint.

**Long work is asynchronous.** Training, prediction, backtesting, batches, and champion comparisons return a handle and are polled. Nothing blocks an HTTP connection on a model fit.

**Requests carry a correlation ID.** `RequestIdMiddleware` assigns one, and it appears in structured logs and in error bodies as `request_id` — the join key between a client failure and its server-side log lines.

**Ingest is idempotent.** `POST /ingest/sales-daily` resolves natural keys (store code, SKU) to IDs and upserts, so re-sending a batch is safe.

## The error envelope

```json
{
  "type": "/errors/unprocessable-entity",
  "title": "Unprocessable Entity",
  "status": 422,
  "detail": "…specific to this occurrence…",
  "instance": "…",
  "code": "UNPROCESSABLE_ENTITY",
  "request_id": "…"
}
```

`type` is a stable URI under `/errors` — **switch on it**, not on prose. `title` is stable per type; `detail` is specific to the occurrence. `errors` carries field-level detail on 422 validation failures. The model allows extensions, per RFC 7807.

### The type registry

| `type` | Typical status | Meaning |
|---|---|---|
| `/errors/validation` | 422 | The **input** failed validation. |
| `/errors/unprocessable-entity` | 422 | Input was well-formed; the **state** forbids the action. |
| `/errors/bad-request` | 400 | The request does not apply to this resource. |
| `/errors/not-found` | 404 | No such resource. |
| `/errors/conflict` | 409 | Conflicts with existing state. |
| `/errors/unauthorized` | 401 | — |
| `/errors/forbidden` | 403 | — |
| `/errors/rate-limited` | 429 | — |
| `/errors/gateway-timeout` | 504 | A drain or upstream wait timed out. |
| `/errors/service-unavailable` | 503 | — |
| `/errors/embedding-auth` | — | The embedding provider rejected the credential. |
| `/errors/agent-fallback-exhausted` | — | Primary **and** fallback agent models both failed. |
| `/errors/database` | 500 | Database-level failure. |
| `/errors/internal` | 500 | Unhandled server error. |

### The distinction that matters most

`validation` and `unprocessable-entity` are **both 422 and deliberately different**:

- **`/errors/validation`** — *you sent something wrong.* Fix the request.
- **`/errors/unprocessable-entity`** — *what you sent cannot be done right now.* The request is fine; the state is not.

Promoting an untrained model is `unprocessable-entity`; promoting with a malformed alias name is `validation`. Retrying the first after training makes sense; retrying the second unchanged never will. Client retry logic should branch here.

Similarly, `bad-request` (400) marks a request that does not apply at all — asking a baseline run for feature importances, for instance. It is permanent, not transient.

## Endpoint groups

Twenty routers. `/health` sits at the root; the rest are prefixed.

### Platform

| Prefix | Purpose |
|---|---|
| `/health` | Liveness probe → `{"status":"ok"}`. |
| `/ingest` | Batch sales load — idempotent. |
| `/dimensions` | Stores and products: list with filters, search, sorting, pagination; fetch by id. |
| `/analytics` | Read-only aggregates: `kpis`, `drilldowns`, `timeseries`, `inventory-status`. |
| `/seeder` | The Forge — see [Seeding data](../operator/seeding-data.md). |
| `/config` | Runtime AI configuration; keys always masked on read. |

Analytics responses are bounded by `analytics_max_rows` (10000) and `analytics_max_date_range_days` (730).

### Modelling

| Prefix | Purpose |
|---|---|
| `/featuresets` | `compute` and `preview` time-safe features up to a cutoff. |
| `/forecasting` | `train`, `predict`, and feature metadata by run or job. |
| `/backtesting` | `run` — rolling or expanding cross-validation. |
| `/model-selection` | The champion selector workflow. |
| `/explain` | Forecast explainability. Note the prefix is `/explain`, not `/explainability`. |
| `/scenarios` | What-if simulation, saved plans, and multi-plan comparison. |

### Orchestration

| Prefix | Purpose |
|---|---|
| `/jobs` | Submit, list, inspect, and cancel `train` / `predict` / `backtest` jobs. |
| `/batch` | Matrix submissions with bounded concurrency. |
| `/registry` | Runs, comparison, artifact verification, and aliases. |
| `/ops` | `summary`, `retraining-candidates`, `model-health`. |
| `/demo` | `run` the pipeline, and a WebSocket event stream. |

### Conversational

| Prefix | Purpose |
|---|---|
| `/rag` | Index, retrieve, list, and delete knowledge sources. |
| `/agents` | Sessions, chat, approval, plus `WS /agents/stream`. |

## Worked flows

### Train, then check on it

```bash
# Submit
curl -X POST http://localhost:8123/jobs \
  -H 'Content-Type: application/json' \
  -d '{"job_type": "train", ...}'
# → {"job_id": "..."}

# Poll
curl http://localhost:8123/jobs/{job_id}
```

A job carries status, result JSON, error detail, and the run it produced.

### Verify an artifact before trusting a run

```bash
curl http://localhost:8123/registry/runs/{run_id}/verify
```

Re-computes the artifact's SHA-256 against the recorded value. This is the check the promotion gate runs, and the one gate with no operator override — see [Artifacts and the registry](artifacts-and-registry.md).

### Compare two runs

```bash
curl http://localhost:8123/registry/compare/{run_id_a}/{run_id_b}
```

Comparability requires the same grain, overlapping data windows, and the same `feature_frame_version`.

### The champion workflow

```
POST /model-selection/runs            → 202 + monitor URL
GET  /model-selection/{id}            → poll to terminal
POST /model-selection/{id}/train-winner    (or /train-selected)
POST /model-selection/{id}/predict
POST /model-selection/{id}/promote
```

`promote` requires a valid alias name, an `approved_by`, `acknowledge_non_recommended=true` for an override, and a trained model — each a distinct 422. See [Champion selector](../analyst/champion-selector.md).

## Behaviors worth designing for

**A 504 from a cancel is not a failed cancel.** `DELETE /batch/{id}` and `DELETE /model-selection/{id}` drain in-flight work first. scikit-learn and LightGBM fits cannot be cancelled mid-call, so the drain is bounded by a timeout (default 30s) and exceeding it returns 504. The cancellation is still in progress — re-poll rather than re-issuing.

**Batches are rejected, not truncated.** Expanded scope over `batch_max_scope_expansion` (1000) fails at submission.

**Feature-aware models refuse to auto-forecast.** `POST /model-selection/{id}/predict` blocks for `regression`, `prophet_like`, `lightgbm`, `xgboost`, and `random_forest` — they need a future feature frame. Use `/scenarios` instead. This is a designed refusal, not a bug to work around.

**V1 plus `feature_groups` is a 422.** Feature packs are V2-only.

**Feature importance has three distinct failure codes.** 400 (baseline — no learned importance), 404 (unknown run/job), 422 (no artifact yet, artifact deleted, missing `ml-*` extra at unpickle, or an estimator without `feature_importances_` — which includes `regression`'s `HistGradientBoostingRegressor`).

**Model family is computed, never stored.** It arrives as a computed field derived from `model_type`; unknown types classify as `baseline` and log a warning rather than raising.

## WebSockets

| Endpoint | Streams |
|---|---|
| `WS /agents/stream` | Agent tokens and tool-call events, including `approval_required`. |
| `WS /demo/stream` | Per-step demo pipeline events for the Showcase page. |

An `approval_required` event means the agent has **stopped** and will not proceed until `POST /agents/sessions/{id}/approve` resolves it, or it expires after `agent_approval_timeout_minutes`.

## No authentication

There is none. The API is unauthenticated and intended for single-host local use — consistent with the system's scope ([What ForecastLabAI is](../operator/concepts.md#what-this-is-not)). `api_host` defaults to `0.0.0.0`, which listens on all interfaces; binding it to a reachable network exposes an unauthenticated API, and that is your deliberate choice.

## Next

- [Code architecture](code-architecture.md) — where each endpoint group lives.
- [Artifacts and the registry](artifacts-and-registry.md) — the integrity contract.
