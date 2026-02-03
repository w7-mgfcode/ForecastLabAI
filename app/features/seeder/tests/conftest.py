"""Test fixtures for seeder feature tests."""

import pytest


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Reset settings cache between tests."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
