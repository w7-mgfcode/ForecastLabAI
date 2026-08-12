# Troubleshooting

Symptom → cause → fix, for the failures this system actually produces.

**Purpose:** get you unstuck without reading source.
**Intended reader:** operators and analysts; integrators should also read the error envelope in [API reference](integrator/api-reference.md).

## First, locate the layer

Four things can be independently broken. Check them in this order — each depends on the ones above it.

```
Postgres (:5433)  →  migrations  →  backend API (:8123)  →  dashboard (:5173)
```

```bash
docker compose ps                        # is Postgres up and healthy?
uv run python scripts/check_db.py        # can the app reach and authenticate to it?
uv run alembic current                   # are migrations applied?
curl http://localhost:8123/health        # is the API up?  → {"status":"ok"}
```

If `/health` answers `ok`, the backend and its database connection are both fine, and the problem is above that line — in the dashboard, or in the specific request you are making.

## Startup and connectivity

**The dashboard shows "Loading…" on every panel.**
The frontend cannot reach the backend. Confirm the API answers (`curl http://localhost:8123/health`), then check `frontend/.env` has `VITE_API_BASE_URL=http://localhost:8123`. `VITE_API_BASE_URL` is a **build-time** variable — after changing it, restart `pnpm dev`; a hot reload will not pick it up.

**`connection refused` to the database.**
Postgres is not up, or is on a different port. The Compose service publishes host port **5433**, not the default 5432, so a `DATABASE_URL` pointing at 5432 will fail against a healthy container. Run `docker compose up -d` and confirm with `docker compose ps`.

**The database works from the host but not from the backend container.**
Different network, different hostname. In Compose mode the backend reaches Postgres at `postgres:5432` (service DNS, container port), and the backend container's `environment:` block sets `DATABASE_URL` accordingly — it overrides `.env`. The `.env` value is the *host-mode* default. See [Running the stack](operator/running-the-stack.md).

**`relation "…" does not exist`.**
Migrations were never applied, or a new migration landed after your last pull. Run `uv run alembic upgrade head`.

**The backend starts but every write fails after a `git pull`.**
Same cause. Migrations are forward-only; pull then migrate.

## Empty dashboard, no error

**KPI cards all read zero and tables are empty.**
The database is migrated but has no data. A fresh install is empty by design — nothing seeds itself. Generate a dataset from **Admin → Data seeding**, or run `make demo`, or call `POST /seeder/generate`. See [Seeding data](operator/seeding-data.md).

**The Knowledge page shows an empty corpus.**
No documents are indexed yet. Index one from **Admin → RAG Sources** or `POST /rag/index`. An empty corpus also means the `rag_assistant` agent has nothing to cite.

**Demand Planner shows no SKUs.**
It rolls up **completed `predict` jobs**. With no successful prediction jobs there is nothing to display. Train a model and run a forecast first.

## Model training and forecasting

**`422` when training with `feature_groups` on V1.**
Feature packs belong to the V2 feature frame. A V1 training request carrying `feature_groups` is rejected. Either pick V2 or drop the packs. See [Forecasting](analyst/forecasting.md).

**The V2 option is disabled for the model I picked.**
You picked a baseline. Baselines do not consume features, so V2 has no meaning for them — the UI disables the combination and explains it in a tooltip. Pick a tree or additive model.

**`lightgbm` / `xgboost` is missing from the model list.**
Both are opt-in twice over: install the extra *and* set the flag.

```bash
uv sync --extra dev --extra ml-lightgbm     # then FORECAST_ENABLE_LIGHTGBM=true
uv sync --extra dev --extra ml-xgboost      # then FORECAST_ENABLE_XGBOOST=true
```

`random_forest` needs only the flag (`FORECAST_ENABLE_RANDOM_FOREST=true`) — it is pure scikit-learn. All three flags require a backend restart.

**A model trains, then unpickling its artifact fails later.**
The flag was set but the extra is not installed in the environment doing the loading. The `forecast_enable_*` flags are permission gates, not installation checks — they do not verify the library is present. Install the matching extra.

**Champion selector refuses to forecast: "blocked".**
Expected, not a bug. A feature-aware model needs a **future** feature frame to predict forward, and the selector will not fabricate one. Use the [What-If Planner](analyst/demand-and-planning.md), which builds the forward frame from explicit assumptions.

**The comparison is refused with `400` for a store/product pair.**
Too little history at that grain for a valid cross-validation split. The page flags the pair as unusable before submitting. Pick a pair with more history, or seed a longer date range.

**Feature importance is unavailable for a run.**
Three distinct causes, distinguished by status code:
- **`400`** — the run is a baseline. Baselines have no learned importance vector; nothing is wrong.
- **`404`** — the run or job is not in the registry.
- **`422`** — the run has no artifact yet (`pending` / `running` / `failed`), the artifact file was deleted from disk, an optional `ml-*` extra is missing at unpickle time, or the estimator simply does not expose one. Note that `regression` uses scikit-learn's `HistGradientBoostingRegressor`, which **does not** expose `feature_importances_` — a `422` there is permanent, not transient.

## Backtesting and metrics

**No RMSE tile on an older backtest.**
RMSE was added later; backtest jobs recorded before it landed do not carry the key, and the UI omits the tile rather than showing a zero. Re-run the backtest to get it.

**No per-horizon-bucket card.**
It renders only when the response carries `bucketed_aggregated_metrics`. Older jobs and some configurations do not produce it.

**Metrics look implausibly good.**
Suspect leakage before celebrating. Everything in the feature path is built to prevent it and `app/features/featuresets/tests/test_leakage.py` locks the guarantee — but if you have added a feature, that test is the thing to run. Also remember the data is synthetic: patterns the generator put in are patterns a model can find.

## Registry and promotion

**Promotion rejected `422`.**
Four separate preconditions, each with its own message:
- the alias name must match `^[a-z0-9][a-z0-9\-_]*$`;
- `approved_by` must be present — promotion is never anonymous;
- a **non-recommended** model needs `acknowledge_non_recommended=true`;
- the model must be **trained** first.

**The Promote button stays disabled and no checkbox releases it.**
The candidate's artifact failed SHA-256 verification. That is the one gate with **no operator override**, deliberately — a corrupt or missing artifact is not a judgement call. Re-train to produce a verifiable artifact.

**An alias is flagged stale.**
Read the reason chip: `newer success run` (a better candidate exists), `artifact not verified` (integrity failure), `run not success` (target failed or was archived), or `V mismatch` (feature-frame drift). Only the last one is subtle — it means the alias's feature contract would silently change, which matters if a production pipeline feeds it.

**Two runs will not compare.**
They must share a grain, have overlapping data windows, **and** share a `feature_frame_version`. The Compare page shows a champion-compatibility badge naming which condition failed. Runs predating the field default to V1.

## Batches and cancellation

**`DELETE /batch/{id}` returns `504`.**
The drain timed out. In-flight scikit-learn and LightGBM fits cannot be cancelled mid-call, so cancellation waits for them — bounded by `batch_cancel_drain_timeout_seconds` (default 30). The batch is still cancelling; the response only means it did not finish within the window.

**A batch is slower than its `max_parallel` suggests.**
Effective parallelism is `min(batch_job.max_parallel, batch_global_max_parallel)`, and the global default is `4`.

**Connection-pool exhaustion under load.**
`batch_global_max_parallel` was raised without raising the Postgres pool. The default of 4 is sized for the Compose pool (`pool_size=5`, `max_overflow=10`).

**A batch is rejected before it starts.**
Expanded scope (pairs × model configs) exceeded `batch_max_scope_expansion` (default 1000). Narrow the scope.

## RAG and agents

**Indexing fails, or search returns nothing sensible after switching embedding models.**
`rag_embedding_dimension` must equal the width the model emits — OpenAI `text-embedding-3-small` is 1536, `nomic-embed-text` is 768. The vector column has a **fixed width**, so this is a schema mismatch, not a tuning problem: changing dimension requires a migration and re-indexing the corpus, not just a settings edit.

**Retrieval returns nothing for an obviously relevant question.**
`rag_similarity_threshold` (default 0.7) is a floor — passages below it are dropped. Either the corpus lacks the content or the threshold is too strict for your embedding model.

**Chat is unavailable but everything else works.**
The agents need an LLM API key (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY`). Forecasting, backtesting, the registry, and the whole dashboard work without one.

**Agent model rejected at startup.**
`agent_default_model` and `agent_fallback_model` are validated as `provider:model-name`. The three rejections: no colon, blank model name, or a **nested provider prefix** (`google-gla:google-gla:gemini-3-flash` — the error suggests the correction). Multi-colon Ollama tags like `ollama:llama3.1:8b` are valid.

**The agent stops mid-task and waits.**
Working as designed. It hit a tool in `agent_require_approval` (`create_alias`, `archive_run`, `save_scenario` by default) and entered `awaiting_approval`. Approve or reject it in the chat, or via `POST /agents/sessions/{id}/approve`. Pending approvals expire after `agent_approval_timeout_minutes` (60).

**The agent gives up partway through a longer task.**
Session bounds: `agent_max_tool_calls` (10), `agent_timeout_seconds` (120), `agent_max_tokens` (4096). The `/guide` page shows the live limits.

**Ollama works on the host but not in Compose.**
`OLLAMA_BASE_URL` must be `http://ollama:11434` inside the Compose network, not `localhost`. GPU Compose mode injects this automatically.

## Reading an API error

Every endpoint returns RFC 7807 `application/problem+json` with a stable `type` URI under `/errors`. The code tells you which class of problem it is:

| `type` | Typical status | Meaning |
|---|---|---|
| `/errors/validation` | 422 | The **input** failed validation. |
| `/errors/unprocessable-entity` | 422 | Input was well-formed but the **state** does not permit the action. |
| `/errors/bad-request` | 400 | The request does not apply to this resource at all. |
| `/errors/not-found` | 404 | No such resource. |
| `/errors/conflict` | 409 | Conflicts with existing state. |
| `/errors/gateway-timeout` | 504 | A drain or upstream wait timed out. |
| `/errors/embedding-auth` | — | The embedding provider rejected the credential. |
| `/errors/agent-fallback-exhausted` | — | Primary *and* fallback agent models both failed. |
| `/errors/database` | 500 | Database-level failure. |
| `/errors/internal` | 500 | Unhandled server error. |

`validation` and `unprocessable-entity` are deliberately distinct: the first means *you sent something wrong*, the second means *what you sent cannot be done right now*.

## Still stuck

- [Configuration reference](configuration.md) — confirm the setting is what you think it is, and whether it needs a restart.
- [FAQ](faq.md) — several "is this broken?" questions answered as "no, here's why".
- `docs/_base/RUNBOOKS.md` — the deeper operational runbooks.
- The interactive API contract at `http://localhost:8123/docs` is always current; this manual is not generated from it.
