"""Test fixtures for backtesting module."""

from datetime import date, timedelta

import numpy as np
import pytest

from app.features.backtesting.schemas import BacktestConfig, SplitConfig
from app.features.forecasting.schemas import NaiveModelConfig, SeasonalNaiveModelConfig


@pytest.fixture
def sample_dates_120() -> list[date]:
    """Create 120 consecutive dates starting from 2024-01-01."""
    start = date(2024, 1, 1)
    return [start + timedelta(days=i) for i in range(120)]


@pytest.fixture
def sample_values_120() -> np.ndarray:
    """Create 120 sequential values (1, 2, 3, ..., 120)."""
    return np.array(range(1, 121), dtype=np.float64)


@pytest.fixture
def sample_dates_84() -> list[date]:
    """Create 84 consecutive dates (12 weeks) starting from 2024-01-01."""
    start = date(2024, 1, 1)
    return [start + timedelta(days=i) for i in range(84)]


@pytest.fixture
def sample_seasonal_values_84() -> np.ndarray:
    """Create 84 values with weekly pattern (12 weeks).

    Pattern: [10, 20, 30, 40, 50, 60, 70] repeated 12 times.
    """
    weekly_pattern = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0])
    return np.tile(weekly_pattern, 12)


@pytest.fixture
def sample_split_config_expanding() -> SplitConfig:
    """Create a SplitConfig with expanding window strategy."""
    return SplitConfig(
        strategy="expanding",
        n_splits=5,
        min_train_size=30,
        gap=0,
        horizon=14,
    )


@pytest.fixture
def sample_split_config_sliding() -> SplitConfig:
    """Create a SplitConfig with sliding window strategy."""
    return SplitConfig(
        strategy="sliding",
        n_splits=5,
        min_train_size=30,
        gap=0,
        horizon=14,
    )


@pytest.fixture
def sample_split_config_with_gap() -> SplitConfig:
    """Create a SplitConfig with gap between train and test."""
    return SplitConfig(
        strategy="expanding",
        n_splits=3,
        min_train_size=30,
        gap=7,
        horizon=14,
    )


@pytest.fixture
def sample_naive_config() -> NaiveModelConfig:
    """Create a naive model configuration."""
    return NaiveModelConfig()


@pytest.fixture
def sample_seasonal_config() -> SeasonalNaiveModelConfig:
    """Create a seasonal naive model configuration."""
    return SeasonalNaiveModelConfig(season_length=7)


@pytest.fixture
def sample_backtest_config_naive(sample_split_config_expanding: SplitConfig) -> BacktestConfig:
    """Create a BacktestConfig with naive model."""
    return BacktestConfig(
        split_config=sample_split_config_expanding,
        model_config_main=NaiveModelConfig(),
        include_baselines=True,
        store_fold_details=True,
    )


@pytest.fixture
def sample_backtest_config_no_baselines(
    sample_split_config_expanding: SplitConfig,
) -> BacktestConfig:
    """Create a BacktestConfig without baselines."""
    return BacktestConfig(
        split_config=sample_split_config_expanding,
        model_config_main=NaiveModelConfig(),
        include_baselines=False,
        store_fold_details=True,
    )
