"""Application configuration via Pydantic Settings v2."""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valid agent LLM provider prefixes for a "provider:model-name" identifier.
# "ollama" runs the agent fully local via Ollama's OpenAI-compatible endpoint.
VALID_MODEL_PROVIDERS: tuple[str, ...] = (
    "anthropic",
    "openai",
    "google-gla",
    "google-vertex",
    "ollama",
)


def validate_model_identifier(v: str) -> str:
    """Validate an agent model identifier of the form ``provider:model-name``.

    Shared by the ``Settings`` field validators and the runtime config service
    (``app/features/config``) so a UI-driven model change is checked the same
    way an env-var-driven one is.

    Args:
        v: Model identifier string (e.g. ``anthropic:claude-sonnet-4-5``,
            ``ollama:llama3.1``).

    Returns:
        The validated model identifier, unchanged.

    Raises:
        ValueError: If the format is invalid, the model name is blank, or the
            provider is not in :data:`VALID_MODEL_PROVIDERS`.
    """
    if ":" not in v:
        raise ValueError(
            f"Invalid model identifier '{v}'. "
            "Expected format: 'provider:model-name' "
            "(e.g., 'anthropic:claude-sonnet-4-5', 'ollama:llama3.1')"
        )
    provider, model_name = v.split(":", 1)

    # Validate model name is non-empty and not just whitespace
    if not model_name or not model_name.strip():
        raise ValueError(
            f"Invalid model identifier '{v}'. "
            "Model name after ':' cannot be empty or blank. "
            "Expected format: 'provider:model-name' "
            "(e.g., 'anthropic:claude-sonnet-4-5', 'ollama:llama3.1')"
        )

    if provider not in VALID_MODEL_PROVIDERS:
        raise ValueError(
            f"Unknown provider '{provider}'. Valid providers: {list(VALID_MODEL_PROVIDERS)}"
        )
    return v


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "ForecastLabAI"
    app_env: Literal["development", "testing", "staging", "production"] = "development"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://forecastlab:forecastlab@localhost:5433/forecastlab"

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    # API
    api_host: str = "0.0.0.0"  # noqa: S104
    api_port: int = 8123

    # Ingest
    ingest_batch_size: int = 1000
    ingest_timeout_seconds: int = 60

    # Feature Engineering
    feature_max_lookback_days: int = 1095  # 3 years
    feature_max_lag: int = 365
    feature_max_window: int = 90

    # Forecasting
    forecast_random_seed: int = 42
    forecast_default_horizon: int = 14
    forecast_max_horizon: int = 90
    forecast_model_artifacts_dir: str = "./artifacts/models"
    forecast_enable_lightgbm: bool = False
    forecast_enable_xgboost: bool = False

    # Backtesting
    backtest_max_splits: int = 20
    backtest_default_min_train_size: int = 30
    backtest_max_gap: int = 30
    backtest_results_dir: str = "./artifacts/backtests"

    # Registry
    registry_artifact_root: str = "./artifacts/registry"
    registry_duplicate_policy: Literal["allow", "deny", "detect"] = "detect"

    # Analytics
    analytics_max_rows: int = 10000
    analytics_max_date_range_days: int = 730

    # Jobs
    jobs_retention_days: int = 30

    # Batch runner (PRP-33) — cap on scope expansion (pairs x model_configs).
    batch_max_scope_expansion: int = 1000

    # Batch runner concurrency (PRP-34) — hard upper bound on concurrent
    # in-flight batch_job_item executions across all active batches on this
    # host. Sized for the docker-compose Postgres pool (pool_size=5,
    # max_overflow=10). Effective per-batch parallelism is
    # min(batch_job.max_parallel, this). Env override:
    # BATCH_GLOBAL_MAX_PARALLEL=8 — requires uvicorn restart.
    batch_global_max_parallel: int = 4
    # Max seconds DELETE /batch/{batch_id} waits for in-flight children to
    # settle before returning RFC 7807 504. In-flight sklearn/LightGBM fits
    # are uncancellable mid-call, so a long fit can stall the drain.
    batch_cancel_drain_timeout_seconds: int = 30

    # RAG Embedding Configuration
    rag_embedding_provider: Literal["openai", "ollama"] = "openai"
    openai_api_key: str = ""
    rag_embedding_model: str = "text-embedding-3-small"
    rag_embedding_dimension: int = 1536
    rag_embedding_batch_size: int = 100

    # Ollama Configuration (when rag_embedding_provider = "ollama")
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "nomic-embed-text"

    # RAG Chunking Configuration
    rag_chunk_size: int = 512  # tokens
    rag_chunk_overlap: int = 50  # tokens
    rag_min_chunk_size: int = 100  # minimum tokens per chunk

    # RAG Retrieval Configuration
    rag_top_k: int = 5
    rag_similarity_threshold: float = 0.7
    rag_max_context_tokens: int = 4000

    # RAG Index Configuration
    rag_index_type: Literal["hnsw", "ivfflat"] = "hnsw"
    rag_hnsw_m: int = 16
    rag_hnsw_ef_construction: int = 64

    # Agent LLM Configuration
    agent_default_model: str = "anthropic:claude-sonnet-4-5"
    agent_fallback_model: str = "openai:gpt-4o"
    agent_temperature: float = 0.1
    agent_max_tokens: int = 4096
    anthropic_api_key: str = ""
    google_api_key: str = ""  # For Gemini models (google-gla:* or google-vertex:*)

    # Gemini Extended Reasoning Configuration (optional)
    agent_thinking_budget: int | None = None  # Token budget for Gemini 2.5+ thinking mode

    # Agent Execution Configuration
    agent_max_tool_calls: int = 10
    agent_timeout_seconds: int = 120
    agent_retry_attempts: int = 3
    agent_retry_delay_seconds: float = 1.0

    # Human-in-the-Loop Configuration
    # ``save_scenario`` (PRP-27 Phase D) lets the experiment agent persist a
    # scenario_plan row — a deliberate mutation-surface widening, so it is
    # gated here exactly like create_alias / archive_run.
    agent_require_approval: list[str] = ["create_alias", "archive_run", "save_scenario"]
    agent_approval_timeout_minutes: int = 60

    # Session Configuration
    agent_session_ttl_minutes: int = 120
    agent_max_sessions_per_user: int = 5

    # Streaming Configuration
    agent_enable_streaming: bool = True

    # Seeder Configuration
    seeder_default_seed: int = 42
    seeder_default_stores: int = 10
    seeder_default_products: int = 50
    seeder_batch_size: int = 1000
    seeder_enable_progress: bool = True
    seeder_allow_production: bool = False
    seeder_require_confirm: bool = True

    @field_validator("agent_default_model", "agent_fallback_model")
    @classmethod
    def _validate_agent_model(cls, v: str) -> str:
        """Validate agent model identifiers via :func:`validate_model_identifier`."""
        return validate_model_identifier(v)

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env == "development"

    @property
    def is_testing(self) -> bool:
        """Check if running in testing mode."""
        return self.app_env == "testing"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings singleton."""
    return Settings()
