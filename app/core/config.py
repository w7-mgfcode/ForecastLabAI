"""Application configuration via Pydantic Settings v2."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    database_url: str = "postgresql+asyncpg://forecastlab:forecastlab@localhost:5432/forecastlab"

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

    # Backtesting
    backtest_max_splits: int = 20
    backtest_default_min_train_size: int = 30
    backtest_max_gap: int = 30
    backtest_results_dir: str = "./artifacts/backtests"

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
