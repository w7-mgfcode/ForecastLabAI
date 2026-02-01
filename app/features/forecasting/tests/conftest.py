"""Test fixtures for forecasting module."""

from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pytest

from app.features.forecasting.schemas import (
    MovingAverageModelConfig,
    NaiveModelConfig,
    SeasonalNaiveModelConfig,
)


@pytest.fixture
def sample_time_series() -> np.ndarray:
    """Create sample time series data for testing.

    Returns 60 days of sequential values (1, 2, 3, ...) for easy verification.
    """
    return np.array(range(1, 61), dtype=np.float64)


@pytest.fixture
def sample_seasonal_series() -> np.ndarray:
    """Create sample time series with weekly pattern.

    Returns 28 days (4 weeks) of data with a clear weekly pattern:
    Week pattern: [10, 20, 30, 40, 50, 60, 70] repeated.
    """
    weekly_pattern = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0])
    return np.tile(weekly_pattern, 4)  # 4 weeks = 28 days


@pytest.fixture
def sample_constant_series() -> np.ndarray:
    """Create constant time series for testing.

    Returns 30 days of constant value (100) for testing moving average.
    """
    return np.full(30, 100.0, dtype=np.float64)


@pytest.fixture
def sample_naive_config() -> NaiveModelConfig:
    """Create sample naive model configuration."""
    return NaiveModelConfig(
        schema_version="1.0",
        model_type="naive",
    )


@pytest.fixture
def sample_seasonal_config() -> SeasonalNaiveModelConfig:
    """Create sample seasonal naive configuration with weekly seasonality."""
    return SeasonalNaiveModelConfig(
        schema_version="1.0",
        model_type="seasonal_naive",
        season_length=7,
    )


@pytest.fixture
def sample_mavg_config() -> MovingAverageModelConfig:
    """Create sample moving average configuration."""
    return MovingAverageModelConfig(
        schema_version="1.0",
        model_type="moving_average",
        window_size=7,
    )


@pytest.fixture
def tmp_model_path() -> Generator[str, None, None]:
    """Create temporary path for model serialization tests.

    Yields:
        Path to temporary directory for saving test models.
    """
    with TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "test_model")
