"""Tests for application configuration."""

from app.core.config import Settings, get_settings


def test_settings_has_defaults():
    """Settings should have sensible defaults."""
    settings = Settings()

    assert settings.app_name == "ForecastLabAI"
    assert settings.app_env == "development"
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.log_format == "json"
    assert settings.api_port == 8123


def test_settings_is_development_property():
    """is_development should return True for development env."""
    settings = Settings(app_env="development")
    assert settings.is_development is True
    assert settings.is_production is False


def test_settings_is_production_property():
    """is_production should return True for production env."""
    settings = Settings(app_env="production")
    assert settings.is_development is False
    assert settings.is_production is True


def test_get_settings_returns_singleton():
    """get_settings should return cached singleton."""
    settings1 = get_settings()
    settings2 = get_settings()

    assert settings1 is settings2


def test_settings_from_environment(monkeypatch):
    """Settings should load from environment variables."""
    monkeypatch.setenv("APP_NAME", "TestApp")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    # Create new settings instance (not cached)
    settings = Settings()

    assert settings.app_name == "TestApp"
    assert settings.debug is True
    assert settings.log_level == "DEBUG"
