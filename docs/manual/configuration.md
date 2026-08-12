# Configuration reference

Every setting ForecastLabAI reads, what it controls, and how to change it.

**Purpose:** one complete, verifiable table of the configuration surface.
**Intended reader:** operators tuning a deployment and integrators who need to know which knobs exist.

## How configuration works

All settings live in one Pydantic Settings class, [`Settings` in `app/core/config.py`](../../app/core/config.py). Each field maps to an environment variable of the same name in **upper case** — `forecast_max_horizon` is set by `FORECAST_MAX_HORIZON`. Values are read from the process environment and from a `.env` file in the repository root; unknown variables are ignored (`extra="ignore"`), so a typo in a variable name fails silently as a *default*, not as an error.

Application code reads settings through `get_settings()`, which is `@lru_cache`d — a singleton for the process lifetime. Feature code must never touch `os.environ` directly; that rule is in [AGENTS.md](../../AGENTS.md) and is what makes this table complete.

Three consequences worth knowing:

- **`.env.example` is a starting point, not the full surface.** It ships the variables most deployments change. Many fields below have no line in it and are configured only by adding one.
- **Most changes need a restart**, because the settings object is cached at first read.
- **Except the AI-model settings**, which are the deliberate exception — see [Runtime-editable settings](#runtime-editable-settings-no-restart) below.

## Application

| Field | Env var | Default | What it controls |
|---|---|---|---|
| `app_name` | `APP_NAME` | `ForecastLabAI` | Service name in logs and startup events. |
| `app_env` | `APP_ENV` | `development` | One of `development`, `testing`, `staging`, `production`. Drives the `is_development` / `is_testing` / `is_production` properties. |
| `debug` | `DEBUG` | `false` | Debug flag surfaced at startup. `.env.example` ships `true`. |
| `log_level` | `LOG_LEVEL` | `INFO` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `log_format` | `LOG_FORMAT` | `json` | `json` for structured output, `console` for human-readable local logs. |

## Database and API

| Field | Env var | Default | What it controls |
|---|---|---|---|
| `database_url` | `DATABASE_URL` | `postgresql+asyncpg://forecastlab:forecastlab@localhost:5433/forecastlab` | Async SQLAlchemy connection string. The host-mode default targets the Compose Postgres on host port **5433**. |
| `api_host` | `API_HOST` | `0.0.0.0` | Bind address. The default listens on all interfaces. |
| `api_port` | `API_PORT` | `8123` | Backend port. |

Running the stack in containers changes the database host: the backend container's `environment:` block sets `DATABASE_URL` to `…@postgres:5432/…` (in-cluster DNS, container port), overriding whatever `.env` holds. This is why the `.env` value stays the *host-mode* default — see [Running the stack](operator/running-the-stack.md).

The dashboard reads one variable of its own, `VITE_API_BASE_URL` (default `http://localhost:8123`), from `frontend/.env`. It is a Vite build-time variable, not part of `Settings`.

## Ingest and feature engineering

| Field | Env var | Default | What it controls |
|---|---|---|---|
| `ingest_batch_size` | `INGEST_BATCH_SIZE` | `1000` | Rows per batch in `POST /ingest/sales-daily`. |
| `ingest_timeout_seconds` | `INGEST_TIMEOUT_SECONDS` | `60` | Ingest request timeout. |
| `feature_max_lookback_days` | `FEATURE_MAX_LOOKBACK_DAYS` | `1095` | Ceiling on history a feature computation may read — three years. |
| `feature_max_lag` | `FEATURE_MAX_LAG` | `365` | Largest permitted lag feature, in days. |
| `feature_max_window` | `FEATURE_MAX_WINDOW` | `90` | Largest permitted rolling window, in days. |

These three feature ceilings bound cost, not correctness. Leakage safety is enforced by the feature code and locked by `app/features/featuresets/tests/test_leakage.py` — see [Forecasting](analyst/forecasting.md).

## Forecasting

| Field | Env var | Default | What it controls |
|---|---|---|---|
| `forecast_random_seed` | `FORECAST_RANDOM_SEED` | `42` | Seed for model training. Fixing it is what makes a run reproducible. |
| `forecast_default_horizon` | `FORECAST_DEFAULT_HORIZON` | `14` | Default forecast horizon in days. |
| `forecast_max_horizon` | `FORECAST_MAX_HORIZON` | `90` | Maximum accepted horizon; a longer request is rejected. |
| `forecast_model_artifacts_dir` | `FORECAST_MODEL_ARTIFACTS_DIR` | `./artifacts/models` | Where fitted model artifacts are written. |
| `forecast_enable_lightgbm` | `FORECAST_ENABLE_LIGHTGBM` | `false` | Enables the `lightgbm` model type. Also needs the `ml-lightgbm` extra installed. |
| `forecast_enable_xgboost` | `FORECAST_ENABLE_XGBOOST` | `false` | Enables the `xgboost` model type. Also needs the `ml-xgboost` extra installed. |
| `forecast_enable_random_forest` | `FORECAST_ENABLE_RANDOM_FOREST` | `false` | Enables the `random_forest` model type. Pure scikit-learn — no extra dependency needed. |

The three `forecast_enable_*` flags are **opt-in gates, not installation checks**. Setting a flag to `true` without installing the matching extra will fail when the model is actually trained or unpickled, not at startup. `random_forest` is the exception with no extra to install.

## Backtesting

| Field | Env var | Default | What it controls |
|---|---|---|---|
| `backtest_max_splits` | `BACKTEST_MAX_SPLITS` | `20` | Maximum cross-validation folds per backtest. |
| `backtest_default_min_train_size` | `BACKTEST_DEFAULT_MIN_TRAIN_SIZE` | `30` | Minimum training rows before the first fold, in days. |
| `backtest_max_gap` | `BACKTEST_MAX_GAP` | `30` | Maximum permitted gap between train and test windows. |
| `backtest_results_dir` | `BACKTEST_RESULTS_DIR` | `./artifacts/backtests` | Where backtest result files are written. |

## Registry and artifacts

| Field | Env var | Default | What it controls |
|---|---|---|---|
| `registry_artifact_root` | `REGISTRY_ARTIFACT_ROOT` | `./artifacts/registry` | Root directory for registry-tracked artifacts. |
| `registry_duplicate_policy` | `REGISTRY_DUPLICATE_POLICY` | `detect` | One of `allow`, `deny`, `detect` — how a duplicate run registration is handled. |
| `showcase_export_root` | `SHOWCASE_EXPORT_ROOT` | `./artifacts/showcase` | Root for workspace export bundles (manifest plus checksums). |

## Analytics and jobs

| Field | Env var | Default | What it controls |
|---|---|---|---|
| `analytics_max_rows` | `ANALYTICS_MAX_ROWS` | `10000` | Row ceiling on an analytics response. |
| `analytics_max_date_range_days` | `ANALYTICS_MAX_DATE_RANGE_DAYS` | `730` | Largest queryable date range — two years. |
| `jobs_retention_days` | `JOBS_RETENTION_DAYS` | `30` | How long job records are kept. |

## Batch runner

| Field | Env var | Default | What it controls |
|---|---|---|---|
| `batch_max_scope_expansion` | `BATCH_MAX_SCOPE_EXPANSION` | `1000` | Cap on expanded scope (pairs × model configs). A batch that would expand past this is rejected rather than queued. |
| `batch_global_max_parallel` | `BATCH_GLOBAL_MAX_PARALLEL` | `4` | Host-wide ceiling on concurrent batch items across *all* active batches. Effective per-batch parallelism is `min(batch_job.max_parallel, this)`. |
| `batch_cancel_drain_timeout_seconds` | `BATCH_CANCEL_DRAIN_TIMEOUT_SECONDS` | `30` | How long `DELETE /batch/{batch_id}` waits for in-flight children before returning a 504. |

The default of `4` is sized for the Compose Postgres pool (`pool_size=5`, `max_overflow=10`). Raising it without raising the pool will surface as connection-pool exhaustion under load. Both parallelism settings require a backend restart.

## Champion selector (model selection)

| Field | Env var | Default | What it controls |
|---|---|---|---|
| `model_selection_global_max_parallel` | `MODEL_SELECTION_GLOBAL_MAX_PARALLEL` | `4` | Host-wide ceiling on concurrent candidate backtests. Set to `1` for sequential execution. |
| `model_selection_cancel_drain_timeout_seconds` | `MODEL_SELECTION_CANCEL_DRAIN_TIMEOUT_SECONDS` | `30` | How long `DELETE /model-selection/{id}` waits for in-flight candidates before returning a 504. |

Both drain timeouts exist because an in-flight scikit-learn or LightGBM fit **cannot be cancelled mid-call**. The timeout bounds how long the API will wait for a fit to finish on its own before giving up and reporting a 504.

## RAG: embeddings, chunking, retrieval, index

| Field | Env var | Default | What it controls |
|---|---|---|---|
| `rag_embedding_provider` | `RAG_EMBEDDING_PROVIDER` | `openai` | `openai` or `ollama`. Choosing `ollama` keeps document content off external services. |
| `openai_api_key` | `OPENAI_API_KEY` | *(empty)* | OpenAI credential, for embeddings and/or the agent. |
| `rag_embedding_model` | `RAG_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model name for the OpenAI provider. |
| `rag_embedding_dimension` | `RAG_EMBEDDING_DIMENSION` | `1536` | Vector width. **Must match the chosen model.** |
| `rag_embedding_batch_size` | `RAG_EMBEDDING_BATCH_SIZE` | `100` | Chunks embedded per API call. |
| `ollama_base_url` | `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint. In GPU Compose mode the backend injects `http://ollama:11434`. |
| `ollama_embedding_model` | `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model for the Ollama provider. |
| `rag_chunk_size` | `RAG_CHUNK_SIZE` | `512` | Target chunk size, in tokens. |
| `rag_chunk_overlap` | `RAG_CHUNK_OVERLAP` | `50` | Token overlap between adjacent chunks. |
| `rag_min_chunk_size` | `RAG_MIN_CHUNK_SIZE` | `100` | Minimum tokens for a chunk to be kept. |
| `rag_top_k` | `RAG_TOP_K` | `5` | Passages returned per retrieval. |
| `rag_similarity_threshold` | `RAG_SIMILARITY_THRESHOLD` | `0.7` | Cosine-similarity floor. Passages below it are not returned. |
| `rag_max_context_tokens` | `RAG_MAX_CONTEXT_TOKENS` | `4000` | Ceiling on retrieved context handed to an agent. |
| `rag_index_type` | `RAG_INDEX_TYPE` | `hnsw` | pgvector index type: `hnsw` or `ivfflat`. |
| `rag_hnsw_m` | `RAG_HNSW_M` | `16` | HNSW graph degree. |
| `rag_hnsw_ef_construction` | `RAG_HNSW_EF_CONSTRUCTION` | `64` | HNSW build-time search width. |

**`rag_embedding_dimension` is the setting that most often breaks RAG.** It must equal the width the embedding model actually emits — OpenAI `text-embedding-3-small` is 1536, `nomic-embed-text` is 768. A mismatch is a schema-level failure, not a quality problem: the stored vector column has a fixed width. Changing dimension means a migration, not just a settings edit. See [Troubleshooting](troubleshooting.md).

## Agent LLM and execution

| Field | Env var | Default | What it controls |
|---|---|---|---|
| `agent_default_model` | `AGENT_DEFAULT_MODEL` | `anthropic:claude-sonnet-4-5` | Primary agent model, as `provider:model-name`. |
| `agent_fallback_model` | `AGENT_FALLBACK_MODEL` | `openai:gpt-4o` | Model used when the primary fails. |
| `agent_temperature` | `AGENT_TEMPERATURE` | `0.1` | Sampling temperature. |
| `agent_max_tokens` | `AGENT_MAX_TOKENS` | `4096` | Response token ceiling. |
| `anthropic_api_key` | `ANTHROPIC_API_KEY` | *(empty)* | Anthropic credential. |
| `google_api_key` | `GOOGLE_API_KEY` | *(empty)* | Google credential, for `google-gla:*` / `google-vertex:*`. |
| `agent_thinking_budget` | `AGENT_THINKING_BUDGET` | *(unset)* | Optional token budget for Gemini extended reasoning. Unset disables it. |
| `agent_max_tool_calls` | `AGENT_MAX_TOOL_CALLS` | `10` | Tool calls allowed per session. |
| `agent_timeout_seconds` | `AGENT_TIMEOUT_SECONDS` | `120` | Wall-clock timeout wrapping one agent run. |
| `agent_retry_attempts` | `AGENT_RETRY_ATTEMPTS` | `3` | Retries on a failed model call. |
| `agent_retry_delay_seconds` | `AGENT_RETRY_DELAY_SECONDS` | `1.0` | Delay between retries. |
| `agent_session_ttl_minutes` | `AGENT_SESSION_TTL_MINUTES` | `120` | Session lifetime. |
| `agent_max_sessions_per_user` | `AGENT_MAX_SESSIONS_PER_USER` | `5` | Concurrent sessions per user. |
| `agent_enable_streaming` | `AGENT_ENABLE_STREAMING` | `true` | Enables token-by-token streaming over the WebSocket. |
| `agent_require_approval` | `AGENT_REQUIRE_APPROVAL` | `["create_alias","archive_run","save_scenario"]` | Tool names gated behind human approval. |
| `agent_approval_timeout_minutes` | `AGENT_APPROVAL_TIMEOUT_MINUTES` | `60` | How long a pending approval waits before expiring. |

### The model identifier format

`agent_default_model` and `agent_fallback_model` are validated on load by `validate_model_identifier`. The format is `provider:model-name`, where provider is one of `anthropic`, `openai`, `google-gla`, `google-vertex`, `ollama`. Three failures are rejected explicitly:

- **No colon** — `claude-sonnet-4-5` alone is not a valid identifier.
- **Empty or blank model name** — `anthropic:` is rejected.
- **A nested provider prefix** — `google-gla:google-gla:gemini-3-flash` is rejected with a suggested correction, because it otherwise fails only later as a 404 at request time. Multi-colon Ollama tags stay valid: `ollama:llama3.1:8b` is fine, because `llama3.1` is not a provider name.

Choosing an `ollama:` model runs the agent fully locally with no API key.

### `agent_require_approval` is a safety boundary

This list is the human-in-the-loop gate: every tool named in it pauses the agent and waits for an explicit approval before running. It ships with the three mutating tools — `create_alias`, `archive_run`, `save_scenario`. Removing a name from this list lets an agent perform that mutation **without asking anyone**. Per [AGENTS.md](../../AGENTS.md), widening an agent's mutation surface requires adding the new tool name here. See [Chat and knowledge](analyst/chat-and-knowledge.md).

Note the format: it is parsed as a **JSON array**, so `.env` needs `AGENT_REQUIRE_APPROVAL=["create_alias","archive_run","save_scenario"]` — not a comma-separated bare string.

## Seeder

| Field | Env var | Default | What it controls |
|---|---|---|---|
| `seeder_default_seed` | `SEEDER_DEFAULT_SEED` | `42` | Random seed. Same seed plus same scenario reproduces the same dataset. |
| `seeder_default_stores` | `SEEDER_DEFAULT_STORES` | `10` | Stores generated by default. |
| `seeder_default_products` | `SEEDER_DEFAULT_PRODUCTS` | `50` | Products generated by default. |
| `seeder_batch_size` | `SEEDER_BATCH_SIZE` | `1000` | Insert batch size. |
| `seeder_enable_progress` | `SEEDER_ENABLE_PROGRESS` | `true` | Emits progress events during generation. |
| `seeder_allow_production` | `SEEDER_ALLOW_PRODUCTION` | `false` | Whether seeding is permitted when `app_env` is `production`. |
| `seeder_require_confirm` | `SEEDER_REQUIRE_CONFIRM` | `true` | Requires explicit confirmation for destructive seeder operations. |

`seeder_allow_production` and `seeder_require_confirm` are the two guards that keep a synthetic-data generator from overwriting a dataset someone cares about. See [Seeding data](operator/seeding-data.md).

## Runtime-editable settings (no restart)

The AI-model settings are the deliberate exception to the restart rule. The **`/admin` → AI Models** tab persists overrides in an `app_config` database table and re-applies them onto the live `Settings` singleton — the same mechanism runs at startup, so an override survives a restart too.

What is editable live: the agent model, the RAG embedding provider/model/dimension, and provider API keys. The endpoints are `GET /config/ai`, `PATCH /config/ai`, `GET /config/providers/health`, and `GET /config/ollama/models`.

**API keys are always masked on read.** `GET /config/ai` never returns a key value.

## Next

- [Troubleshooting](troubleshooting.md) — when a setting is not doing what you expect.
- [Running the stack](operator/running-the-stack.md) — how host mode and Compose mode differ.
