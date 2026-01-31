"""Test fixtures for featuresets module."""

import pandas as pd
import pytest

from app.features.featuresets.schemas import (
    CalendarConfig,
    ExogenousConfig,
    FeatureSetConfig,
    ImputationConfig,
    LagConfig,
    RollingConfig,
)


@pytest.fixture
def sample_time_series() -> pd.DataFrame:
    """Create sample time series data for testing.

    Returns 30 days of data for a single store/product with sequential
    quantity values (1, 2, 3, ...) for easy leakage detection.
    """
    dates = pd.date_range(start="2024-01-01", periods=30, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "store_id": [1] * 30,
            "product_id": [1] * 30,
            "quantity": list(range(1, 31)),  # Sequential for leakage detection
            "unit_price": [10.0] * 30,
            "total_amount": [q * 10.0 for q in range(1, 31)],
        }
    )


@pytest.fixture
def multi_series_time_series() -> pd.DataFrame:
    """Create sample time series with multiple series.

    Returns data for 2 stores x 2 products to test group isolation.
    """
    dates = pd.date_range(start="2024-01-01", periods=10, freq="D")
    rows = []

    for store_id in [1, 2]:
        for product_id in [1, 2]:
            base = (store_id - 1) * 100 + (product_id - 1) * 10
            for i, d in enumerate(dates):
                rows.append(
                    {
                        "date": d,
                        "store_id": store_id,
                        "product_id": product_id,
                        "quantity": base + i + 1,  # Unique per series
                        "unit_price": 10.0 + store_id,
                        "total_amount": (base + i + 1) * (10.0 + store_id),
                    }
                )

    return pd.DataFrame(rows)


@pytest.fixture
def sample_lag_config() -> LagConfig:
    """Create sample lag configuration."""
    return LagConfig(
        schema_version="1.0",
        lags=(1, 7, 14),
        target_column="quantity",
    )


@pytest.fixture
def sample_rolling_config() -> RollingConfig:
    """Create sample rolling configuration."""
    return RollingConfig(
        schema_version="1.0",
        windows=(7, 14),
        aggregations=("mean", "std"),
        target_column="quantity",
    )


@pytest.fixture
def sample_calendar_config() -> CalendarConfig:
    """Create sample calendar configuration."""
    return CalendarConfig(
        schema_version="1.0",
        include_day_of_week=True,
        include_month=True,
        include_quarter=True,
        include_is_weekend=True,
        use_cyclical_encoding=True,
    )


@pytest.fixture
def sample_exogenous_config() -> ExogenousConfig:
    """Create sample exogenous configuration."""
    return ExogenousConfig(
        schema_version="1.0",
        include_price=True,
        price_lags=(7,),
        include_price_change=False,
    )


@pytest.fixture
def sample_imputation_config() -> ImputationConfig:
    """Create sample imputation configuration."""
    return ImputationConfig(
        schema_version="1.0",
        strategies={
            "quantity": "zero",
            "unit_price": "ffill",
        },
    )


@pytest.fixture
def sample_feature_config(
    sample_lag_config: LagConfig,
    sample_rolling_config: RollingConfig,
    sample_calendar_config: CalendarConfig,
) -> FeatureSetConfig:
    """Create sample complete feature configuration."""
    return FeatureSetConfig(
        schema_version="1.0",
        name="test_config",
        description="Test feature configuration",
        entity_columns=("store_id", "product_id"),
        date_column="date",
        target_column="quantity",
        lag_config=sample_lag_config,
        rolling_config=sample_rolling_config,
        calendar_config=sample_calendar_config,
    )


@pytest.fixture
def minimal_feature_config() -> FeatureSetConfig:
    """Create minimal feature configuration with only lags."""
    return FeatureSetConfig(
        schema_version="1.0",
        name="minimal_config",
        lag_config=LagConfig(lags=(1,)),
    )


@pytest.fixture
def time_series_with_gaps() -> pd.DataFrame:
    """Create time series with missing dates for imputation testing."""
    # Create dates with gaps (missing day 5, 10, 15)
    all_dates = pd.date_range(start="2024-01-01", periods=20, freq="D")
    included_dates = [d for i, d in enumerate(all_dates) if (i + 1) not in [5, 10, 15]]

    df = pd.DataFrame(
        {
            "date": included_dates,
            "store_id": [1] * len(included_dates),
            "product_id": [1] * len(included_dates),
            "quantity": list(range(1, len(included_dates) + 1)),
            "unit_price": [10.0] * len(included_dates),
        }
    )

    # Add some NaN values
    df.loc[3, "quantity"] = None
    df.loc[7, "unit_price"] = None

    return df
