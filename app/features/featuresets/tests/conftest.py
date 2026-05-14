"""Test fixtures for featuresets module."""

from datetime import date

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


# =============================================================================
# Phase 2 fixtures (PRP-3.1A) — consumed by PRP-3.1B/C/D leakage cases.
# Sequential / derivable values let downstream tests mathematically detect
# any contamination from future-date data into past-date feature rows.
# =============================================================================


@pytest.fixture
def phase2_product_attrs_df() -> pd.DataFrame:
    """Phase 2 product lifecycle attributes.

    Grain: one row per ``product_id``. Mirrors a subset of
    ``app/features/data_platform/models.py:Product`` columns:
        - product_id (int)
        - launch_date (date | None)
        - discontinue_date (date | None)  -- None = still active

    Two products:
      * P1 launched 2023-06-01, discontinued 2025-12-31 (closed lifecycle)
      * P2 launched 2024-03-15, still active (open lifecycle)
    """
    return pd.DataFrame(
        {
            "product_id": [1, 2],
            "launch_date": [date(2023, 6, 1), date(2024, 3, 15)],
            "discontinue_date": [date(2025, 12, 31), None],
        }
    )


@pytest.fixture
def phase2_replenishment_events_df() -> pd.DataFrame:
    """Phase 2 replenishment events.

    Grain: one row per (store_id, product_id, event_date). Mirrors
    ``app/features/data_platform/models.py:ReplenishmentEvent`` columns:
        - store_id (int)
        - product_id (int)
        - event_date (date)
        - lead_time_days (int)
        - ordered_qty (int)
        - received_qty (int)  -- received_qty <= ordered_qty per CHECK

    Three events for (store=1, product=1) at 7-day then 14-day gaps so
    PRP-3.1C tests can compute ``days_since_last`` (=7, then 14) plus
    rolling counts over W=14.
    """
    return pd.DataFrame(
        {
            "store_id": [1, 1, 1],
            "product_id": [1, 1, 1],
            "event_date": [date(2024, 1, 5), date(2024, 1, 12), date(2024, 1, 26)],
            "lead_time_days": [7, 5, 10],
            "ordered_qty": [100, 100, 200],
            "received_qty": [98, 100, 195],
        }
    )


@pytest.fixture
def phase2_promotion_rows_df() -> pd.DataFrame:
    """Phase 2 promotion rows.

    Grain: one row per active campaign. Mirrors a subset of
    ``app/features/data_platform/models.py:Promotion`` columns:
        - product_id (int)
        - store_id (int | None)  -- None = chain-wide
        - kind (Literal["pct_off", "bogo", "bundle", "markdown"])
        - discount_pct (float | None)  -- NULL for bogo / bundle
        - start_date (date), end_date (date)

    Mix of kinds + chain-wide vs store-specific to exercise PRP-3.1D's
    per-kind one-hot branch and NULL-discount handling.
    """
    return pd.DataFrame(
        {
            "product_id": [1, 1, 2],
            "store_id": [1, None, 1],
            "kind": ["markdown", "pct_off", "bogo"],
            "discount_pct": [0.20, 0.10, None],
            "start_date": [date(2024, 1, 7), date(2024, 1, 1), date(2024, 1, 15)],
            "end_date": [date(2024, 1, 14), date(2024, 1, 31), date(2024, 1, 28)],
        }
    )
