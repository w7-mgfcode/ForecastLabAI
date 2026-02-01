"""Test fixtures for dimensions module."""

import pytest


@pytest.fixture
def sample_store_data():
    """Sample store data for testing."""
    return {
        "code": "S001",
        "name": "Main Street Store",
        "region": "North",
        "city": "Springfield",
        "store_type": "supermarket",
    }


@pytest.fixture
def sample_product_data():
    """Sample product data for testing."""
    return {
        "sku": "SKU-001",
        "name": "Cola Classic",
        "category": "Beverage",
        "brand": "CocaCola",
        "base_price": "2.99",
        "base_cost": "1.50",
    }
