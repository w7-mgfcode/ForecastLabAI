"""Tests for agent configuration validation."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.features.agents.agents.base import validate_api_key_for_model


class TestModelIdentifierValidation:
    """Test model identifier format validation."""

    def test_valid_model_identifiers(self):
        """Test valid model identifier formats."""
        valid_identifiers = [
            "anthropic:claude-sonnet-4-5",
            "openai:gpt-4o",
            "google-gla:gemini-3-flash",
            "google-vertex:gemini-3-pro",
        ]
        for identifier in valid_identifiers:
            # Should not raise
            settings = Settings(agent_default_model=identifier)
            assert settings.agent_default_model == identifier

    def test_invalid_model_identifier_missing_provider(self):
        """Test invalid model identifier without provider prefix."""
        with pytest.raises(ValidationError, match="Invalid model identifier"):
            Settings(agent_default_model="claude-sonnet-4-5")

    def test_invalid_model_identifier_unknown_provider(self):
        """Test invalid model identifier with unknown provider."""
        with pytest.raises(ValidationError, match="Unknown provider"):
            Settings(agent_default_model="unknown:model-name")

    def test_invalid_model_identifier_empty_provider(self):
        """Test invalid model identifier with empty provider."""
        with pytest.raises(ValidationError, match="Unknown provider"):
            Settings(agent_default_model=":model-name")


class TestAPIKeyValidation:
    """Test API key validation for models."""

    def test_validate_anthropic_key_missing(self, monkeypatch):
        """Test validation fails when Anthropic key missing."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        with pytest.raises(ValueError, match="Anthropic API key not configured"):
            validate_api_key_for_model("anthropic:claude-sonnet-4-5")

    def test_validate_google_key_missing(self, monkeypatch):
        """Test validation fails when Google key missing."""
        monkeypatch.setenv("GOOGLE_API_KEY", "")
        with pytest.raises(ValueError, match="Google API key not configured"):
            validate_api_key_for_model("google-gla:gemini-3-flash")

    def test_validate_openai_key_missing(self, monkeypatch):
        """Test validation fails when OpenAI key missing."""
        monkeypatch.setenv("OPENAI_API_KEY", "")
        with pytest.raises(ValueError, match="OpenAI API key not configured"):
            validate_api_key_for_model("openai:gpt-4o")


class TestThinkingModeConfiguration:
    """Test Gemini thinking mode configuration."""

    def test_thinking_budget_none_by_default(self):
        """Test thinking budget is None by default."""
        settings = Settings()
        assert settings.agent_thinking_budget is None

    def test_thinking_budget_configured(self):
        """Test thinking budget can be configured."""
        settings = Settings(agent_thinking_budget=4000)
        assert settings.agent_thinking_budget == 4000
