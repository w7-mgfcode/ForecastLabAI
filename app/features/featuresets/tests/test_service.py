"""Unit tests for FeatureEngineeringService."""

from datetime import date

import pandas as pd
import pytest

from app.features.featuresets.schemas import (
    CalendarConfig,
    FeatureSetConfig,
    ImputationConfig,
    LagConfig,
    LifecycleConfig,
    PromotionConfig,
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


class TestLifecycleFeatures:
    """Tests for _compute_lifecycle_features (PRP-3.1B)."""

    def test_compute_lifecycle_happy_path(self, sample_time_series: pd.DataFrame) -> None:
        """Happy path: launch_date and discontinue_date both set; produces
        both lagged columns with expected integer values."""
        df = sample_time_series.copy()
        df["launch_date"] = date(2024, 1, 1)  # delta starts at 0
        df["discontinue_date"] = date(2024, 1, 15)  # signed crossover

        config = FeatureSetConfig(
            name="lc_happy",
            lifecycle_config=LifecycleConfig(
                include_days_since_launch=True,
                include_days_since_discontinue=True,
                lag_days=1,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(df)

        assert "days_since_launch_lag1" in result.feature_columns
        assert "days_since_discontinue_lag1" in result.feature_columns

        # Row 1 (date=2024-01-02): lag1 reflects row 0 (date=2024-01-01)
        # days_since_launch at row 0 = 0; days_since_discontinue at row 0 = -14
        assert result.df.iloc[1]["days_since_launch_lag1"] == 0
        assert result.df.iloc[1]["days_since_discontinue_lag1"] == -14

        # Row 16 (date=2024-01-17): lag1 reflects row 15 (date=2024-01-16)
        # days_since_launch at row 15 = 15; days_since_discontinue at row 15 = +1
        assert result.df.iloc[16]["days_since_launch_lag1"] == 15
        assert result.df.iloc[16]["days_since_discontinue_lag1"] == 1

    def test_compute_lifecycle_null_launch_date(self, sample_time_series: pd.DataFrame) -> None:
        """NULL launch_date -> all-NaN lifecycle column, no exception."""
        df = sample_time_series.copy()
        df["launch_date"] = pd.NaT
        df["discontinue_date"] = pd.NaT

        config = FeatureSetConfig(
            name="lc_null",
            lifecycle_config=LifecycleConfig(
                include_days_since_launch=True,
                include_days_since_discontinue=False,
                lag_days=1,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(df)

        col = "days_since_launch_lag1"
        assert col in result.feature_columns
        assert result.df[col].isna().all(), "NULL launch_date must produce all-NaN column"

    def test_compute_lifecycle_discontinue_before_cutoff(
        self, sample_time_series: pd.DataFrame
    ) -> None:
        """discontinue_date before all rows -> positive integer for every row."""
        df = sample_time_series.copy()
        df["launch_date"] = date(2023, 1, 1)
        df["discontinue_date"] = date(2023, 12, 25)  # 7 days before row 0

        config = FeatureSetConfig(
            name="lc_post_discontinue",
            lifecycle_config=LifecycleConfig(
                include_days_since_launch=False,
                include_days_since_discontinue=True,
                lag_days=1,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(df)

        # Row 1: lag1 reflects row 0 -> date=2024-01-01 - discontinue=2023-12-25 = +7
        assert result.df.iloc[1]["days_since_discontinue_lag1"] == 7
        # Row 8: lag1 reflects row 7 -> 2024-01-08 - 2023-12-25 = +14
        assert result.df.iloc[8]["days_since_discontinue_lag1"] == 14
        # All non-NaN values must be >= 0 (discontinue is in the past)
        non_na = result.df["days_since_discontinue_lag1"].dropna()
        assert (non_na >= 0).all(), "with discontinue in the past, all lagged values must be >= 0"

    def test_compute_lifecycle_skipped_when_attrs_absent(
        self, sample_time_series: pd.DataFrame
    ) -> None:
        """Defensive: missing product-attrs columns -> zero new columns, no crash.

        This is the contract for the legacy /featuresets/compute path; PRP-3.1E
        adds the loader extension that joins product attrs.
        """
        # sample_time_series has NO launch_date / discontinue_date columns.
        config = FeatureSetConfig(
            name="lc_no_attrs",
            lifecycle_config=LifecycleConfig(),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        assert "days_since_launch_lag1" not in result.feature_columns
        assert "days_since_discontinue_lag1" not in result.feature_columns
        # The family token still appears via get_enabled_features (set in PRP-3.1A).
        assert "lifecycle" in config.get_enabled_features()

    def test_compute_lifecycle_uses_phase2_fixture(
        self,
        sample_time_series: pd.DataFrame,
        phase2_product_attrs_df: pd.DataFrame,
    ) -> None:
        """End-to-end merge with the PRP-3.1A fixture: P1 launched 2023-06-01."""
        df = sample_time_series.merge(phase2_product_attrs_df, on="product_id", how="left")
        config = FeatureSetConfig(
            name="lc_phase2_fixture",
            lifecycle_config=LifecycleConfig(lag_days=1),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(df)

        # P1 launched 2023-06-01; 2024-01-01 is 214 days after
        # -> row 1 (date=2024-01-02, lag1 reflects row 0) = 214
        expected = (date(2024, 1, 1) - date(2023, 6, 1)).days
        assert result.df.iloc[1]["days_since_launch_lag1"] == expected


class TestPromotionFeatures:
    """Tests for promotion feature computation (PRP-3.1D)."""

    def test_single_kind_happy_path(
        self,
        sample_time_series: pd.DataFrame,
        phase2_promotion_rows_df: pd.DataFrame,
    ) -> None:
        """Single-kind config produces exactly active+intensity columns for that kind."""
        config = FeatureSetConfig(
            name="test",
            promotion_config=PromotionConfig(kinds_to_track=("markdown",)),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = phase2_promotion_rows_df  # type: ignore[attr-defined]
        result = service.compute_features(sample_time_series)

        assert "promo_markdown_active_lag1" in result.feature_columns
        assert "promo_markdown_intensity_lag1" in result.feature_columns
        # Determinism: exactly 2 columns, active before intensity.
        promo_cols = [c for c in result.feature_columns if c.startswith("promo_")]
        assert promo_cols == [
            "promo_markdown_active_lag1",
            "promo_markdown_intensity_lag1",
        ]

    def test_multi_kind_produces_all_columns_sorted(
        self,
        sample_time_series: pd.DataFrame,
        phase2_promotion_rows_df: pd.DataFrame,
    ) -> None:
        """Multi-kind config produces columns in deterministic (sorted-kind) order."""
        config = FeatureSetConfig(
            name="test",
            promotion_config=PromotionConfig(
                # Intentionally NOT alphabetical — assert the method sorts.
                kinds_to_track=("pct_off", "markdown"),
            ),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = phase2_promotion_rows_df  # type: ignore[attr-defined]
        result = service.compute_features(sample_time_series)

        promo_cols = [c for c in result.feature_columns if c.startswith("promo_")]
        # Decision §15-A: sorted by kind, then active before intensity.
        assert promo_cols == [
            "promo_markdown_active_lag1",
            "promo_markdown_intensity_lag1",
            "promo_pct_off_active_lag1",
            "promo_pct_off_intensity_lag1",
        ]

    def test_chain_wide_promo_applies_to_all_stores(
        self,
        multi_series_time_series: pd.DataFrame,
    ) -> None:
        """A chain-wide promo (store_id IS NULL) applies to every store of the product."""
        promo_rows = pd.DataFrame(
            {
                "product_id": [1],
                "store_id": [None],
                "kind": ["pct_off"],
                "discount_pct": [0.10],
                "start_date": [date(2024, 1, 3)],
                "end_date": [date(2024, 1, 5)],
            }
        )
        config = FeatureSetConfig(
            name="test",
            promotion_config=PromotionConfig(kinds_to_track=("pct_off",)),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = promo_rows  # type: ignore[attr-defined]
        result = service.compute_features(multi_series_time_series)

        # All product=1 rows in 2024-01-04..2024-01-06 (lag1) should be active.
        df = result.df
        prod1_active = df[(df["product_id"] == 1) & (df["promo_pct_off_active_lag1"] == 1)]
        # 2 stores x 3 active-lagged days = 6
        assert len(prod1_active) == 6

    def test_null_discount_pct_yields_nan_intensity_but_active_one(self) -> None:
        """A bogo promo with NULL discount_pct: active=1, intensity=NaN."""
        sample = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=10, freq="D"),
                "store_id": [1] * 10,
                "product_id": [1] * 10,
                "quantity": list(range(1, 11)),
                "unit_price": [10.0] * 10,
                "total_amount": [q * 10.0 for q in range(1, 11)],
            }
        )
        promo_rows = pd.DataFrame(
            {
                "product_id": [1],
                "store_id": [1],
                "kind": ["bogo"],
                "discount_pct": [None],
                "start_date": [date(2024, 1, 3)],
                "end_date": [date(2024, 1, 5)],
            }
        )
        config = FeatureSetConfig(
            name="test",
            promotion_config=PromotionConfig(kinds_to_track=("bogo",)),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = promo_rows  # type: ignore[attr-defined]
        result = service.compute_features(sample)

        df = result.df.reset_index(drop=True)
        dates = pd.to_datetime(df["date"]).dt.date
        # D=Jan 4 reads Jan 3 (start). active=1.
        row = df.loc[dates == date(2024, 1, 4)].iloc[0]
        assert row["promo_bogo_active_lag1"] == 1
        assert pd.isna(row["promo_bogo_intensity_lag1"])

    def test_overlapping_promos_intensity_uses_max(self) -> None:
        """Two markdowns active on the same (store, product, day) → intensity = max."""
        sample = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=10, freq="D"),
                "store_id": [1] * 10,
                "product_id": [1] * 10,
                "quantity": list(range(1, 11)),
                "unit_price": [10.0] * 10,
                "total_amount": [q * 10.0 for q in range(1, 11)],
            }
        )
        promo_rows = pd.DataFrame(
            {
                "product_id": [1, 1],
                "store_id": [1, 1],
                "kind": ["markdown", "markdown"],
                "discount_pct": [0.15, 0.25],  # overlap → max = 0.25
                "start_date": [date(2024, 1, 3), date(2024, 1, 4)],
                "end_date": [date(2024, 1, 6), date(2024, 1, 5)],
            }
        )
        config = FeatureSetConfig(
            name="test",
            promotion_config=PromotionConfig(kinds_to_track=("markdown",)),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = promo_rows  # type: ignore[attr-defined]
        result = service.compute_features(sample)

        df = result.df.reset_index(drop=True)
        dates = pd.to_datetime(df["date"]).dt.date
        # D=Jan 5 reads Jan 4 — BOTH active. intensity = max(0.15, 0.25) = 0.25.
        row = df.loc[dates == date(2024, 1, 5)].iloc[0]
        assert row["promo_markdown_active_lag1"] == 1
        assert row["promo_markdown_intensity_lag1"] == pytest.approx(0.25)

    def test_no_active_promo_yields_zero_active_and_nan_intensity(
        self,
        sample_time_series: pd.DataFrame,
    ) -> None:
        """No promo rows at all → active is NaN at first row then 0, intensity all NaN."""
        config = FeatureSetConfig(
            name="test",
            promotion_config=PromotionConfig(kinds_to_track=("markdown",)),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = pd.DataFrame(  # type: ignore[attr-defined]
            columns=[
                "product_id",
                "store_id",
                "kind",
                "discount_pct",
                "start_date",
                "end_date",
            ]
        )
        result = service.compute_features(sample_time_series)

        active = result.df["promo_markdown_active_lag1"]
        intensity = result.df["promo_markdown_intensity_lag1"]
        # First row of each series has NaN from the lag shift; remaining rows are 0.
        assert pd.isna(active.iloc[0])
        assert (active.iloc[1:] == 0).all()
        assert intensity.isna().all()

    def test_defensive_skip_when_rows_absent_via_orchestrator(
        self,
        sample_time_series: pd.DataFrame,
    ) -> None:
        """When ``_promotion_rows_df`` attribute is unset, orchestrator falls back
        to an empty DataFrame and emits all-NaN-then-zero columns — never crashes.
        """
        config = FeatureSetConfig(
            name="test",
            promotion_config=PromotionConfig(kinds_to_track=("markdown",)),
        )
        service = FeatureEngineeringService(config)
        # Deliberately DO NOT set _promotion_rows_df — exercises the getattr fallback.
        result = service.compute_features(sample_time_series)

        # Columns are still emitted (additive contract preserved).
        assert "promo_markdown_active_lag1" in result.feature_columns
        assert "promo_markdown_intensity_lag1" in result.feature_columns
        # No exception. No active days because the rows-DataFrame is empty.
        active = result.df["promo_markdown_active_lag1"]
        intensity = result.df["promo_markdown_intensity_lag1"]
        assert pd.isna(active.iloc[0])
        assert (active.iloc[1:] == 0).all()
        assert intensity.isna().all()

    def test_cutoff_alignment_drops_post_cutoff_rows(
        self,
        sample_time_series: pd.DataFrame,
    ) -> None:
        """cutoff_date filtering applies BEFORE promotion compute; result is bounded."""
        cutoff = date(2024, 1, 10)
        promo_rows = pd.DataFrame(
            {
                "product_id": [1],
                "store_id": [1],
                "kind": ["markdown"],
                "discount_pct": [0.20],
                "start_date": [date(2024, 1, 5)],
                "end_date": [date(2024, 1, 9)],
            }
        )
        config = FeatureSetConfig(
            name="test",
            promotion_config=PromotionConfig(kinds_to_track=("markdown",)),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = promo_rows  # type: ignore[attr-defined]
        result = service.compute_features(sample_time_series, cutoff_date=cutoff)

        # No rows past cutoff.
        result_dates = pd.to_datetime(result.df["date"]).dt.date
        assert (result_dates <= cutoff).all()
        # At cutoff Jan 10, lag1 reads Jan 9 — last active day. active=1.
        row = result.df.loc[result_dates == cutoff].iloc[0]
        assert row["promo_markdown_active_lag1"] == 1

    def test_active_column_dtype_is_nullable_int(
        self,
        sample_time_series: pd.DataFrame,
        phase2_promotion_rows_df: pd.DataFrame,
    ) -> None:
        """Active column is Int64 (nullable int) to preserve NaN at series start."""
        config = FeatureSetConfig(
            name="test",
            promotion_config=PromotionConfig(kinds_to_track=("markdown",)),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = phase2_promotion_rows_df  # type: ignore[attr-defined]
        result = service.compute_features(sample_time_series)

        # Decision §15-D — Int64 nullable extension dtype.
        assert str(result.df["promo_markdown_active_lag1"].dtype) == "Int64"
        # Intensity stays plain float64.
        assert str(result.df["promo_markdown_intensity_lag1"].dtype) == "float64"


class TestReplenishmentFeatures:
    """Unit tests for replenishment-event features (PRP-3.1C).

    These cases exercise the happy path, zero-event entities, single-event
    entities, cutoff-boundary alignment, and dtype contracts. Time-safety is
    covered separately in ``TestReplenishmentLeakage``.
    """

    def test_happy_path_three_events(self) -> None:
        """Three events on (1,1) yield monotonically growing rolling counts."""
        from app.features.featuresets.schemas import ReplenishmentConfig

        sales = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=10, freq="D"),
                "store_id": [1] * 10,
                "product_id": [1] * 10,
                "quantity": list(range(1, 11)),
            }
        )
        events = pd.DataFrame(
            {
                "store_id": [1, 1, 1],
                "product_id": [1, 1, 1],
                "event_date": [date(2024, 1, 2), date(2024, 1, 5), date(2024, 1, 8)],
            }
        )
        config = FeatureSetConfig(
            name="test",
            replenishment_config=ReplenishmentConfig(
                include_days_since_last=True,
                include_count_window=True,
                lag_days=1,
                count_window_days=7,
            ),
        )
        service = FeatureEngineeringService(config)
        service._replenishment_events_df = events  # type: ignore[attr-defined]
        result = service.compute_features(sales)

        # Both columns should be in feature_columns.
        assert "days_since_last_replenishment_lag1" in result.feature_columns
        assert "replenishment_count_w7_lag1" in result.feature_columns

        # Per-row event_count = [0,1,0,0,1,0,0,1,0,0]; shifted then rolling:
        # shift(1) = [NaN,0,1,0,0,1,0,0,1,0]; rolling(7,min_periods=1).sum():
        # pos 7 window=[0,1,0,0,1,0,0] -> 2
        # pos 8 window=[1,0,0,1,0,0,1] -> 3
        # pos 9 window=[0,0,1,0,0,1,0] -> 2  (the day-2 event has now rolled
        #   out of the trailing-7 window — this is the expected behavior of
        #   ``count_window_days=7``).
        # fillna 0 -> [0,0,1,1,1,2,2,2,3,2].
        counts = result.df["replenishment_count_w7_lag1"].tolist()
        assert counts == [0, 0, 1, 1, 1, 2, 2, 2, 3, 2]

    def test_zero_events_entity(self) -> None:
        """An entity with zero events must have count=0 and days-since=NaN.

        Dtype contracts: count is int64 (with 0 fill), days-since is float64
        (NaN for no-prior-event). PRP-3.1C §15 Decision B.
        """
        from app.features.featuresets.schemas import ReplenishmentConfig

        sales = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=5, freq="D"),
                "store_id": [1] * 5,
                "product_id": [1] * 5,
                "quantity": [1, 2, 3, 4, 5],
            }
        )
        # Zero events — DataFrame with named columns but no rows.
        events = pd.DataFrame(
            {
                "store_id": pd.Series([], dtype="int64"),
                "product_id": pd.Series([], dtype="int64"),
                "event_date": pd.Series([], dtype="datetime64[ns]"),
            }
        )
        config = FeatureSetConfig(
            name="test",
            replenishment_config=ReplenishmentConfig(
                include_days_since_last=True,
                include_count_window=True,
                lag_days=1,
                count_window_days=7,
            ),
        )
        service = FeatureEngineeringService(config)
        service._replenishment_events_df = events  # type: ignore[attr-defined]
        result = service.compute_features(sales)

        count_col = "replenishment_count_w7_lag1"
        days_col = "days_since_last_replenishment_lag1"
        assert result.df[count_col].tolist() == [0, 0, 0, 0, 0]
        assert result.df[count_col].dtype == "int64"
        assert result.df[days_col].isna().all()
        assert result.df[days_col].dtype == "float64"

    def test_single_event_entity(self) -> None:
        """One event on day 3; days-since and count cross the boundary cleanly."""
        from app.features.featuresets.schemas import ReplenishmentConfig

        sales = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=5, freq="D"),
                "store_id": [1] * 5,
                "product_id": [1] * 5,
                "quantity": [1, 2, 3, 4, 5],
            }
        )
        events = pd.DataFrame(
            {
                "store_id": [1],
                "product_id": [1],
                "event_date": [date(2024, 1, 3)],
            }
        )
        config = FeatureSetConfig(
            name="test",
            replenishment_config=ReplenishmentConfig(
                include_days_since_last=True,
                include_count_window=True,
                lag_days=1,
                count_window_days=7,
            ),
        )
        service = FeatureEngineeringService(config)
        service._replenishment_events_df = events  # type: ignore[attr-defined]
        result = service.compute_features(sales)

        count_col = "replenishment_count_w7_lag1"
        days_col = "days_since_last_replenishment_lag1"
        # event_count = [0,0,1,0,0]; shift(1)=[NaN,0,0,1,0]; rolling sum =
        # [NaN,0,0,1,1] -> fillna 0 -> [0,0,0,1,1].
        assert result.df[count_col].tolist() == [0, 0, 0, 1, 1]
        # Per-row days-since = [NaN, NaN, 0, 1, 2]; shift(1) =
        # [NaN, NaN, NaN, 0, 1].
        values = result.df[days_col].tolist()
        for i in (0, 1, 2):
            assert pd.isna(values[i]), f"row {i} should be NaN, got {values[i]}"
        assert values[3] == pytest.approx(0.0)
        assert values[4] == pytest.approx(1.0)

    def test_cutoff_excludes_post_events(self) -> None:
        """Events AFTER cutoff (filtered by caller) must not influence features.

        Mirrors the loader's SQL-side ``date <= cutoff_date`` predicate.
        """
        from app.features.featuresets.schemas import ReplenishmentConfig

        sales = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=5, freq="D"),
                "store_id": [1] * 5,
                "product_id": [1] * 5,
                "quantity": [1, 2, 3, 4, 5],
            }
        )
        cutoff = date(2024, 1, 4)
        # Build events with one pre-cutoff and one post-cutoff row, then
        # apply the same time-safety filter the loader applies SQL-side.
        all_events = pd.DataFrame(
            {
                "store_id": [1, 1],
                "product_id": [1, 1],
                "event_date": [date(2024, 1, 2), date(2024, 1, 5)],
            }
        )
        events = all_events[all_events["event_date"] <= cutoff].reset_index(drop=True)
        assert len(events) == 1  # post-cutoff event filtered out

        config = FeatureSetConfig(
            name="test",
            replenishment_config=ReplenishmentConfig(
                include_days_since_last=True,
                include_count_window=True,
                lag_days=1,
                count_window_days=7,
            ),
        )
        service = FeatureEngineeringService(config)
        service._replenishment_events_df = events  # type: ignore[attr-defined]
        result = service.compute_features(sales, cutoff_date=cutoff)

        # 4 rows survive the cutoff (01..04).
        assert len(result.df) == 4
        count_col = "replenishment_count_w7_lag1"
        # event_count = [0,1,0,0] (post-cutoff filtered); shift(1) =
        # [NaN,0,1,0]; rolling = [NaN,0,1,1] -> [0,0,1,1].
        assert result.df[count_col].tolist() == [0, 0, 1, 1]

    def test_dtypes_are_int64_and_float64(self) -> None:
        """Column dtype contracts: count=int64, days-since=float64.

        Verifies PRP-3.1C §15 Decision B. Tested against a small frame
        with mixed-population entities so both NaN-then-fill paths are
        exercised.
        """
        from app.features.featuresets.schemas import ReplenishmentConfig

        sales = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=4, freq="D"),
                "store_id": [1] * 4,
                "product_id": [1] * 4,
                "quantity": [1, 2, 3, 4],
            }
        )
        events = pd.DataFrame(
            {
                "store_id": [1],
                "product_id": [1],
                "event_date": [date(2024, 1, 2)],
            }
        )
        config = FeatureSetConfig(
            name="test",
            replenishment_config=ReplenishmentConfig(
                include_days_since_last=True,
                include_count_window=True,
                lag_days=1,
                count_window_days=7,
            ),
        )
        service = FeatureEngineeringService(config)
        service._replenishment_events_df = events  # type: ignore[attr-defined]
        result = service.compute_features(sales)

        assert result.df["replenishment_count_w7_lag1"].dtype == "int64"
        assert result.df["days_since_last_replenishment_lag1"].dtype == "float64"
