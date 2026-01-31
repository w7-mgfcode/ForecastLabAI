"""CRITICAL: Leakage prevention tests for feature engineering.

These tests verify that feature computation NEVER uses future data.
Sequential values (1, 2, 3...) are used so any leakage is mathematically detectable.
"""

from datetime import date

import pandas as pd
import pytest

from app.features.featuresets.schemas import (
    FeatureSetConfig,
    LagConfig,
    RollingConfig,
)
from app.features.featuresets.service import FeatureEngineeringService


class TestLagLeakage:
    """Tests verifying lag features never use future data."""

    def test_lag_features_no_future_data(self, sample_time_series: pd.DataFrame) -> None:
        """CRITICAL: Lag features must only use past data.

        With sequential values (1, 2, 3...), lag_1 at row i should equal i (the value at i-1).
        If lag_1 at row i equals i+1 or greater, we have future leakage.
        """
        config = FeatureSetConfig(
            name="test",
            lag_config=LagConfig(lags=(1,)),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        # For each row with a valid lag, verify it uses PAST data only
        for i in range(1, len(result.df)):
            lag_value = result.df.iloc[i]["lag_1"]
            current_quantity = result.df.iloc[i]["quantity"]

            # lag_1 should be the PREVIOUS row's value, which is always < current
            assert lag_value < current_quantity, (
                f"LEAKAGE DETECTED at row {i}: lag_1={lag_value} >= current={current_quantity}. "
                "Lag feature is using current or future data!"
            )

            # More specifically, lag_1 should exactly equal i (row index 0-based matches quantity-1)
            assert lag_value == i, (
                f"LEAKAGE DETECTED at row {i}: lag_1={lag_value} != expected={i}. "
                "Lag feature is not correctly shifted."
            )

    def test_lag_7_no_future_leakage(self, sample_time_series: pd.DataFrame) -> None:
        """Verify lag_7 uses data from exactly 7 days ago."""
        config = FeatureSetConfig(
            name="test",
            lag_config=LagConfig(lags=(7,)),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        # lag_7 at row 7 should be the value from row 0 (which is 1)
        # lag_7 at row 14 should be the value from row 7 (which is 8)
        for i in range(7, len(result.df)):
            lag_value = result.df.iloc[i]["lag_7"]
            expected = i - 7 + 1  # quantity at row (i-7) = (i-7) + 1

            assert lag_value == expected, (
                f"LEAKAGE or ERROR at row {i}: lag_7={lag_value} != expected={expected}"
            )

            # Verify no future data used
            current_quantity = result.df.iloc[i]["quantity"]
            assert lag_value < current_quantity, (
                f"LEAKAGE DETECTED: lag_7 at row {i} >= current value"
            )


class TestRollingLeakage:
    """Tests verifying rolling features exclude current observation."""

    def test_rolling_features_exclude_current(self, sample_time_series: pd.DataFrame) -> None:
        """CRITICAL: Rolling features must NOT include current row's value.

        With sequential values, rolling_mean_7 at row i should be the mean of
        values from rows (i-7) to (i-1), NOT including row i.

        If current value is included, the mean would be higher than expected.
        """
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

        # First 7 rows should be NaN (shift(1) + 7-day window)
        for i in range(7):
            assert pd.isna(result.df.iloc[i]["rolling_mean_7"]), (
                f"Row {i} should have NaN for rolling_mean_7 but has {result.df.iloc[i]['rolling_mean_7']}"
            )

        # Row 7 (index 7) should have mean of rows 0-6 (values 1-7)
        # Mean of [1,2,3,4,5,6,7] = 28/7 = 4.0
        rolling_at_7 = result.df.iloc[7]["rolling_mean_7"]
        assert rolling_at_7 == pytest.approx(4.0), (
            f"LEAKAGE DETECTED: rolling_mean_7 at row 7 = {rolling_at_7}, expected 4.0. "
            "Current observation may be included in rolling window!"
        )

        # Row 8 should have mean of rows 1-7 (values 2-8)
        # Mean of [2,3,4,5,6,7,8] = 35/7 = 5.0
        rolling_at_8 = result.df.iloc[8]["rolling_mean_7"]
        assert rolling_at_8 == pytest.approx(5.0), (
            f"LEAKAGE DETECTED: rolling_mean_7 at row 8 = {rolling_at_8}, expected 5.0"
        )

    def test_rolling_max_excludes_current(self, sample_time_series: pd.DataFrame) -> None:
        """Rolling max should never equal or exceed current value."""
        config = FeatureSetConfig(
            name="test",
            rolling_config=RollingConfig(
                windows=(7,),
                aggregations=("max",),
                min_periods=7,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        # For sequential data, rolling_max_7 at row i should be quantity[i-1]
        # which is always < quantity[i]
        for i in range(7, len(result.df)):
            rolling_max = result.df.iloc[i]["rolling_max_7"]
            current_quantity = result.df.iloc[i]["quantity"]

            # Rolling max of past 7 days (excluding current) should be < current
            assert rolling_max < current_quantity, (
                f"LEAKAGE DETECTED at row {i}: rolling_max_7={rolling_max} >= current={current_quantity}. "
                "Current observation is being included in rolling window!"
            )


class TestCutoffLeakage:
    """Tests verifying cutoff date is strictly enforced."""

    def test_cutoff_strictly_enforced(self, sample_time_series: pd.DataFrame) -> None:
        """CRITICAL: No data after cutoff should be accessible."""
        cutoff = date(2024, 1, 15)  # Only first 15 days

        config = FeatureSetConfig(
            name="test",
            lag_config=LagConfig(lags=(1,)),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series, cutoff_date=cutoff)

        # Should only have 15 rows
        assert len(result.df) == 15, f"Cutoff violation: expected 15 rows, got {len(result.df)}"

        # Max date should be cutoff
        max_date = pd.to_datetime(result.df["date"]).max().date()
        assert max_date <= cutoff, f"CUTOFF VIOLATION: max_date={max_date} > cutoff={cutoff}"

        # No quantity values > 15 should exist (they would be from after cutoff)
        max_quantity = result.df["quantity"].max()
        assert max_quantity <= 15, (
            f"CUTOFF VIOLATION: found quantity={max_quantity} which is from after cutoff"
        )

    def test_features_computed_only_from_pre_cutoff_data(
        self, sample_time_series: pd.DataFrame
    ) -> None:
        """Features at cutoff should only use data from before cutoff."""
        cutoff = date(2024, 1, 15)

        config = FeatureSetConfig(
            name="test",
            rolling_config=RollingConfig(
                windows=(7,),
                aggregations=("mean",),
                min_periods=7,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series, cutoff_date=cutoff)

        # At the last row (cutoff date), rolling_mean_7 should use rows 8-14
        # Values: 8, 9, 10, 11, 12, 13, 14 (not including 15!)
        # Mean = 77/7 = 11.0
        last_row = result.df.iloc[-1]
        expected_mean = pytest.approx(11.0)

        assert last_row["rolling_mean_7"] == expected_mean, (
            f"At cutoff, rolling_mean_7={last_row['rolling_mean_7']}, expected {expected_mean}. "
            "Data from after cutoff may be leaking into features!"
        )


class TestGroupIsolationLeakage:
    """Tests verifying no cross-series leakage."""

    def test_group_isolation_no_cross_series_leakage(
        self, multi_series_time_series: pd.DataFrame
    ) -> None:
        """CRITICAL: Features must not leak between different series.

        Each store/product combination should only use its own history.
        """
        config = FeatureSetConfig(
            name="test",
            entity_columns=("store_id", "product_id"),
            lag_config=LagConfig(lags=(1,)),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(multi_series_time_series)

        # Check each series independently
        for store_id in [1, 2]:
            for product_id in [1, 2]:
                series_mask = (result.df["store_id"] == store_id) & (
                    result.df["product_id"] == product_id
                )
                series_df = result.df[series_mask].reset_index(drop=True)

                # Base value for this series
                base = (store_id - 1) * 100 + (product_id - 1) * 10

                # First row of each series should have NaN lag
                assert pd.isna(series_df.iloc[0]["lag_1"]), (
                    f"Series ({store_id}, {product_id}) first row should have NaN lag_1"
                )

                # Second row should have lag from first row of SAME series only
                expected_lag = base + 1  # First value in this series
                actual_lag = series_df.iloc[1]["lag_1"]

                assert actual_lag == expected_lag, (
                    f"CROSS-SERIES LEAKAGE: Store {store_id}, Product {product_id}: "
                    f"lag_1={actual_lag}, expected={expected_lag}. "
                    "Lag is using data from a different series!"
                )

    def test_rolling_group_isolation(self, multi_series_time_series: pd.DataFrame) -> None:
        """Rolling features must not mix data from different series."""
        config = FeatureSetConfig(
            name="test",
            entity_columns=("store_id", "product_id"),
            rolling_config=RollingConfig(
                windows=(3,),
                aggregations=("mean",),
                min_periods=3,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(multi_series_time_series)

        # Check series (1, 1) - base=0, values: 1,2,3,4,5,6,7,8,9,10
        # At row 3 (value=4), rolling_mean_3 should be mean of [1,2,3] = 2.0
        series_11 = result.df[
            (result.df["store_id"] == 1) & (result.df["product_id"] == 1)
        ].reset_index(drop=True)

        # Row 3 (index 3) has value 4, rolling should use rows 0,1,2 (values 1,2,3)
        rolling_at_3 = series_11.iloc[3]["rolling_mean_3"]
        assert rolling_at_3 == pytest.approx(2.0), (
            f"Series (1,1) at row 3: rolling_mean_3={rolling_at_3}, expected 2.0. "
            "Cross-series contamination may have occurred!"
        )

        # Check series (2, 2) - base=110, values: 111,112,113,114...
        series_22 = result.df[
            (result.df["store_id"] == 2) & (result.df["product_id"] == 2)
        ].reset_index(drop=True)

        # Row 3 (value=114), rolling should use rows 0,1,2 (values 111,112,113)
        # Mean = 336/3 = 112.0
        rolling_22_at_3 = series_22.iloc[3]["rolling_mean_3"]
        assert rolling_22_at_3 == pytest.approx(112.0), (
            f"Series (2,2) at row 3: rolling_mean_3={rolling_22_at_3}, expected 112.0. "
            "Cross-series contamination detected!"
        )


class TestEdgeCaseLeakage:
    """Tests for edge cases that might cause subtle leakage."""

    def test_first_row_never_has_valid_lag(self, sample_time_series: pd.DataFrame) -> None:
        """First row of any series must have NaN for lag features (no history)."""
        config = FeatureSetConfig(
            name="test",
            lag_config=LagConfig(lags=(1, 7, 14)),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        first_row = result.df.iloc[0]
        assert pd.isna(first_row["lag_1"]), "First row must have NaN lag_1"
        assert pd.isna(first_row["lag_7"]), "First row must have NaN lag_7"
        assert pd.isna(first_row["lag_14"]), "First row must have NaN lag_14"

    def test_insufficient_history_has_nan(self, sample_time_series: pd.DataFrame) -> None:
        """Rows without sufficient history must have NaN features."""
        config = FeatureSetConfig(
            name="test",
            rolling_config=RollingConfig(
                windows=(14,),
                aggregations=("mean",),
                min_periods=14,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        # First 14 rows should have NaN (shift(1) + 14-day window)
        for i in range(14):
            assert pd.isna(result.df.iloc[i]["rolling_mean_14"]), (
                f"Row {i} should have NaN rolling_mean_14 due to insufficient history"
            )

        # Row 14 should have valid value
        assert not pd.isna(result.df.iloc[14]["rolling_mean_14"]), (
            "Row 14 should have valid rolling_mean_14"
        )
