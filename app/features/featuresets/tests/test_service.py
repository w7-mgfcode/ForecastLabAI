"""Unit tests for FeatureEngineeringService."""

from datetime import date

import pandas as pd
import pytest

from app.features.featuresets.schemas import (
    CalendarConfig,
    FeatureSetConfig,
    ImputationConfig,
    LagConfig,
    RollingConfig,
)
from app.features.featuresets.service import FeatureEngineeringService


class TestLagFeatures:
    """Tests for lag feature computation."""

    def test_lag_1_computation(self, sample_time_series):
        """Lag 1 should shift values by 1 position."""
        config = FeatureSetConfig(
            name="test",
            lag_config=LagConfig(lags=(1,)),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        # First row should have NaN for lag_1
        assert pd.isna(result.df.iloc[0]["lag_1"])

        # Second row should have value from first row
        assert result.df.iloc[1]["lag_1"] == 1  # quantity[0] = 1

        # Third row should have value from second row
        assert result.df.iloc[2]["lag_1"] == 2  # quantity[1] = 2

    def test_lag_7_computation(self, sample_time_series):
        """Lag 7 should shift values by 7 positions."""
        config = FeatureSetConfig(
            name="test",
            lag_config=LagConfig(lags=(7,)),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        # First 7 rows should have NaN
        for i in range(7):
            assert pd.isna(result.df.iloc[i]["lag_7"])

        # Row 8 (index 7) should have value from row 1 (index 0)
        assert result.df.iloc[7]["lag_7"] == 1

        # Row 15 (index 14) should have value from row 8 (index 7)
        assert result.df.iloc[14]["lag_7"] == 8

    def test_multiple_lags(self, sample_time_series):
        """Multiple lags should be computed correctly."""
        config = FeatureSetConfig(
            name="test",
            lag_config=LagConfig(lags=(1, 7)),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        assert "lag_1" in result.feature_columns
        assert "lag_7" in result.feature_columns
        assert len(result.feature_columns) == 2

    def test_lag_fill_value(self, sample_time_series):
        """fill_value should replace NaN in lag features."""
        config = FeatureSetConfig(
            name="test",
            lag_config=LagConfig(lags=(1,), fill_value=0.0),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        # First row should have 0 instead of NaN
        assert result.df.iloc[0]["lag_1"] == 0.0


class TestRollingFeatures:
    """Tests for rolling feature computation."""

    def test_rolling_mean_7_computation(self, sample_time_series):
        """Rolling mean should use shift(1) + rolling window."""
        config = FeatureSetConfig(
            name="test",
            rolling_config=RollingConfig(
                windows=(7,),
                aggregations=("mean",),
                min_periods=7,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        # First 7 rows should have NaN (shift(1) + 7-day window)
        for i in range(7):
            assert pd.isna(result.df.iloc[i]["rolling_mean_7"])

        # Row 8 (index 7) should have mean of rows 1-7 (indices 0-6)
        # Values: 1, 2, 3, 4, 5, 6, 7 -> mean = 4.0
        assert result.df.iloc[7]["rolling_mean_7"] == pytest.approx(4.0)

        # Row 9 (index 8) should have mean of rows 2-8 (indices 1-7)
        # Values: 2, 3, 4, 5, 6, 7, 8 -> mean = 5.0
        assert result.df.iloc[8]["rolling_mean_7"] == pytest.approx(5.0)

    def test_rolling_std_computation(self, sample_time_series):
        """Rolling std should be computed correctly."""
        config = FeatureSetConfig(
            name="test",
            rolling_config=RollingConfig(
                windows=(7,),
                aggregations=("std",),
                min_periods=7,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        # Check that std is computed (non-zero for sequential data)
        valid_stds = result.df["rolling_std_7"].dropna()
        assert len(valid_stds) > 0
        assert all(std > 0 for std in valid_stds)

    def test_multiple_aggregations(self, sample_time_series):
        """Multiple aggregations should be computed."""
        config = FeatureSetConfig(
            name="test",
            rolling_config=RollingConfig(
                windows=(7,),
                aggregations=("mean", "std", "min", "max"),
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        assert "rolling_mean_7" in result.feature_columns
        assert "rolling_std_7" in result.feature_columns
        assert "rolling_min_7" in result.feature_columns
        assert "rolling_max_7" in result.feature_columns


class TestCalendarFeatures:
    """Tests for calendar feature computation."""

    def test_cyclical_day_of_week(self, sample_time_series):
        """Day of week should use cyclical encoding."""
        config = FeatureSetConfig(
            name="test",
            calendar_config=CalendarConfig(
                include_day_of_week=True,
                use_cyclical_encoding=True,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        assert "dow_sin" in result.feature_columns
        assert "dow_cos" in result.feature_columns

        # Values should be in [-1, 1] range
        assert result.df["dow_sin"].between(-1, 1).all()
        assert result.df["dow_cos"].between(-1, 1).all()

    def test_non_cyclical_day_of_week(self, sample_time_series):
        """Non-cyclical day of week should be integer."""
        config = FeatureSetConfig(
            name="test",
            calendar_config=CalendarConfig(
                include_day_of_week=True,
                use_cyclical_encoding=False,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        assert "day_of_week" in result.feature_columns
        # Day of week should be in [0, 6] range
        assert result.df["day_of_week"].between(0, 6).all()

    def test_is_weekend(self, sample_time_series):
        """is_weekend should correctly identify weekends."""
        config = FeatureSetConfig(
            name="test",
            calendar_config=CalendarConfig(
                include_is_weekend=True,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        assert "is_weekend" in result.feature_columns
        # Values should be 0 or 1
        assert set(result.df["is_weekend"].unique()).issubset({0, 1})

    def test_quarter(self, sample_time_series):
        """Quarter should be computed correctly."""
        config = FeatureSetConfig(
            name="test",
            calendar_config=CalendarConfig(
                include_quarter=True,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        assert "quarter" in result.feature_columns
        # January data should be Q1
        assert (result.df["quarter"] == 1).all()


class TestImputation:
    """Tests for imputation strategies."""

    def test_zero_fill(self, time_series_with_gaps):
        """Zero fill should replace NaN with 0."""
        config = FeatureSetConfig(
            name="test",
            imputation_config=ImputationConfig(
                strategies={"quantity": "zero"},
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(time_series_with_gaps)

        # No NaN in quantity column after imputation
        assert not result.df["quantity"].isna().any()

    def test_ffill(self, time_series_with_gaps):
        """Forward fill should propagate last valid value."""
        config = FeatureSetConfig(
            name="test",
            imputation_config=ImputationConfig(
                strategies={"unit_price": "ffill"},
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(time_series_with_gaps)

        # No NaN in unit_price column after imputation (except possibly first rows)
        # Forward fill only fills if there's a previous value
        non_null_count = result.df["unit_price"].notna().sum()
        assert non_null_count >= len(result.df) - 1


class TestCutoffEnforcement:
    """Tests for cutoff date enforcement."""

    def test_cutoff_filters_data(self, sample_time_series):
        """Cutoff should filter out data after cutoff date."""
        cutoff = date(2024, 1, 15)  # Only first 15 days
        config = FeatureSetConfig(name="test")
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series, cutoff_date=cutoff)

        # Should only have 15 rows
        assert len(result.df) == 15

        # All dates should be <= cutoff
        max_date = pd.to_datetime(result.df["date"]).max().date()
        assert max_date <= cutoff

    def test_no_cutoff_uses_all_data(self, sample_time_series):
        """No cutoff should use all data."""
        config = FeatureSetConfig(name="test")
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series, cutoff_date=None)

        assert len(result.df) == 30


class TestComputeFeatures:
    """Integration tests for compute_features."""

    def test_combined_features(self, sample_time_series, sample_feature_config):
        """All feature types should be computed together."""
        service = FeatureEngineeringService(sample_feature_config)
        result = service.compute_features(sample_time_series)

        # Should have lag, rolling, and calendar features
        assert any("lag_" in col for col in result.feature_columns)
        assert any("rolling_" in col for col in result.feature_columns)
        assert any(col in result.feature_columns for col in ["dow_sin", "dow_cos", "quarter"])

    def test_config_hash_in_result(self, sample_time_series, sample_feature_config):
        """Result should include config hash."""
        service = FeatureEngineeringService(sample_feature_config)
        result = service.compute_features(sample_time_series)

        assert result.config_hash == sample_feature_config.config_hash()

    def test_stats_populated(self, sample_time_series, sample_feature_config):
        """Stats should be populated in result."""
        service = FeatureEngineeringService(sample_feature_config)
        result = service.compute_features(sample_time_series)

        assert "input_rows" in result.stats
        assert "output_rows" in result.stats
        assert "feature_count" in result.stats
        assert "null_counts" in result.stats
        assert result.stats["input_rows"] == 30

    def test_empty_dataframe_handling(self):
        """Empty dataframe should be handled gracefully."""
        config = FeatureSetConfig(
            name="test",
            lag_config=LagConfig(lags=(1,)),
        )
        service = FeatureEngineeringService(config)
        empty_df = pd.DataFrame(columns=["date", "store_id", "product_id", "quantity"])
        result = service.compute_features(empty_df)

        assert len(result.df) == 0
        assert result.feature_columns == ["lag_1"]
