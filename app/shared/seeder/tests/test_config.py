"""Tests for seeder configuration."""

from datetime import date

from app.shared.seeder.config import (
    ScenarioPreset,
    SeederConfig,
    TimeSeriesConfig,
)


class TestTimeSeriesConfig:
    """Tests for TimeSeriesConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = TimeSeriesConfig()

        assert config.base_demand == 100
        assert config.trend == "none"
        assert config.trend_slope == 0.001
        assert len(config.weekly_seasonality) == 7
        assert config.noise_sigma == 0.1
        assert config.anomaly_probability == 0.01

    def test_weekly_seasonality_length(self):
        """Test weekly seasonality has 7 days."""
        config = TimeSeriesConfig()
        assert len(config.weekly_seasonality) == 7

    def test_custom_monthly_seasonality(self):
        """Test custom monthly seasonality."""
        config = TimeSeriesConfig(monthly_seasonality={12: 1.5, 1: 0.8})
        assert config.monthly_seasonality[12] == 1.5
        assert config.monthly_seasonality[1] == 0.8


class TestSeederConfig:
    """Tests for SeederConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = SeederConfig()

        assert config.seed == 42
        assert config.start_date == date(2024, 1, 1)
        assert config.end_date == date(2024, 12, 31)
        assert config.dimensions.stores == 10
        assert config.dimensions.products == 50
        assert config.batch_size == 1000

    def test_from_scenario_retail_standard(self):
        """Test retail_standard scenario preset."""
        config = SeederConfig.from_scenario(ScenarioPreset.RETAIL_STANDARD, seed=123)

        assert config.seed == 123
        assert config.time_series.trend == "linear"
        assert config.retail.promotion_probability == 0.1

    def test_from_scenario_holiday_rush(self):
        """Test holiday_rush scenario preset."""
        config = SeederConfig.from_scenario(ScenarioPreset.HOLIDAY_RUSH)

        assert config.start_date == date(2024, 10, 1)
        assert config.end_date == date(2024, 12, 31)
        assert config.time_series.trend == "exponential"
        assert 12 in config.time_series.monthly_seasonality
        assert config.time_series.monthly_seasonality[12] == 1.8
        assert len(config.holidays) > 0

    def test_from_scenario_high_variance(self):
        """Test high_variance scenario preset."""
        config = SeederConfig.from_scenario(ScenarioPreset.HIGH_VARIANCE)

        assert config.time_series.noise_sigma == 0.4
        assert config.time_series.anomaly_probability == 0.05
        assert config.time_series.anomaly_magnitude == 3.0

    def test_from_scenario_stockout_heavy(self):
        """Test stockout_heavy scenario preset."""
        config = SeederConfig.from_scenario(ScenarioPreset.STOCKOUT_HEAVY)

        assert config.retail.stockout_probability == 0.25
        assert config.retail.stockout_behavior == "zero"

    def test_from_scenario_sparse(self):
        """Test sparse scenario preset."""
        config = SeederConfig.from_scenario(ScenarioPreset.SPARSE)

        assert config.sparsity.missing_combinations_pct == 0.5
        assert config.sparsity.random_gaps_per_series == 3


class TestScenarioPreset:
    """Tests for ScenarioPreset enum."""

    def test_all_scenarios_defined(self):
        """Test all expected scenarios are defined."""
        expected = {
            "retail_standard",
            "holiday_rush",
            "high_variance",
            "stockout_heavy",
            "new_launches",
            "sparse",
        }
        actual = {s.value for s in ScenarioPreset}
        assert actual == expected

    def test_scenario_string_values(self):
        """Test scenario values are strings."""
        for scenario in ScenarioPreset:
            assert isinstance(scenario.value, str)
