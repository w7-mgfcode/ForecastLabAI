"""Pytest fixtures for seeder tests."""

import random
from datetime import date

import pytest

from app.shared.seeder.config import (
    DimensionConfig,
    HolidayConfig,
    RetailPatternConfig,
    SeederConfig,
    SparsityConfig,
    TimeSeriesConfig,
)


@pytest.fixture
def rng():
    """Create a seeded random number generator."""
    return random.Random(42)


@pytest.fixture
def dimension_config():
    """Create a minimal dimension config for testing."""
    return DimensionConfig(
        stores=3,
        products=5,
        store_regions=["North", "South"],
        store_types=["supermarket", "express"],
        product_categories=["Beverage", "Snack"],
        product_brands=["BrandA", "Generic"],
    )


@pytest.fixture
def time_series_config():
    """Create a time series config for testing."""
    return TimeSeriesConfig(
        base_demand=100,
        trend="linear",
        trend_slope=0.01,
        weekly_seasonality=[0.8, 0.9, 1.0, 1.0, 1.1, 1.3, 1.2],
        monthly_seasonality={12: 1.5},
        noise_sigma=0.1,
        anomaly_probability=0.0,  # Disable for deterministic tests
    )


@pytest.fixture
def retail_config():
    """Create a retail config for testing."""
    return RetailPatternConfig(
        promotion_lift=1.3,
        stockout_behavior="zero",
        price_elasticity=-0.5,
        promotion_probability=0.1,
        stockout_probability=0.02,
    )


@pytest.fixture
def sparsity_config():
    """Create a sparsity config for testing."""
    return SparsityConfig(
        missing_combinations_pct=0.0,
        random_gaps_per_series=0,
    )


@pytest.fixture
def holiday_config():
    """Create a holiday config for testing."""
    return HolidayConfig(
        date=date(2024, 12, 25),
        name="Christmas Day",
        multiplier=0.5,
    )


@pytest.fixture
def seeder_config(dimension_config, time_series_config, retail_config, sparsity_config):
    """Create a complete seeder config for testing."""
    return SeederConfig(
        seed=42,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),  # One month for faster tests
        dimensions=dimension_config,
        time_series=time_series_config,
        retail=retail_config,
        sparsity=sparsity_config,
        holidays=[],
        batch_size=100,
    )
