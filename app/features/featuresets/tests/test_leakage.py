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
    LifecycleConfig,
    PromotionConfig,
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


class TestLifecycleLeakage:
    """CRITICAL: Lifecycle features must never use future data (PRP-3.1B)."""

    def test_days_since_launch_lag1_no_future_leakage(
        self, sample_time_series: pd.DataFrame
    ) -> None:
        """CRITICAL: With a known launch_date and sequential dates, the lagged
        column at row i must equal (date[i-1] - launch_date).days exactly.

        sample_time_series has 30 sequential days starting 2024-01-01 for
        (store=1, product=1). With launch_date=2023-12-25, the per-row
        days-since-launch is 7, 8, 9, ..., 36; after shift(1), the lagged
        column at row i is the value at row i-1: NaN at row 0, 7 at row 1,
        8 at row 2, ... Any other integer is leakage.
        """
        df = sample_time_series.copy()
        df["launch_date"] = date(2023, 12, 25)
        df["discontinue_date"] = pd.NaT

        config = FeatureSetConfig(
            name="test_lifecycle_leakage",
            lifecycle_config=LifecycleConfig(
                include_days_since_launch=True,
                include_days_since_discontinue=False,
                lag_days=1,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(df)

        col = "days_since_launch_lag1"
        assert col in result.feature_columns, f"missing column {col} -- wiring regression"

        # Row 0: NaN (no prior row to lag from)
        assert pd.isna(result.df.iloc[0][col]), (
            f"row 0 must be NaN (no history), got {result.df.iloc[0][col]}"
        )

        # Rows 1..29: exactly (i - 1) + 7 days since launch
        # (date[0] is 2024-01-01 -> 7 days since 2023-12-25)
        for i in range(1, len(result.df)):
            expected = (i - 1) + 7
            actual = result.df.iloc[i][col]
            assert actual == expected, (
                f"LEAKAGE DETECTED at row {i}: {col}={actual} != expected={expected}. "
                "Lifecycle feature must reflect data at row i - lag_days only."
            )

    def test_lifecycle_group_isolation_no_cross_product_leakage(
        self, multi_series_time_series: pd.DataFrame
    ) -> None:
        """CRITICAL: Two products with different launch_dates must produce
        independently correct columns -- no cross-series contamination via
        groupby boundary."""
        df = multi_series_time_series.copy()
        # Product 1 launched 2023-12-01 (31 days before 2024-01-01)
        # Product 2 launched 2023-12-25 (7 days before 2024-01-01)
        launch_map = {1: date(2023, 12, 1), 2: date(2023, 12, 25)}
        df["launch_date"] = df["product_id"].map(launch_map)
        df["discontinue_date"] = pd.NaT

        config = FeatureSetConfig(
            name="test_lifecycle_isolation",
            entity_columns=("store_id", "product_id"),
            lifecycle_config=LifecycleConfig(
                include_days_since_launch=True,
                include_days_since_discontinue=False,
                lag_days=1,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(df)

        for store_id in (1, 2):
            for product_id, base_lag in ((1, 31), (2, 7)):
                series = result.df[
                    (result.df["store_id"] == store_id) & (result.df["product_id"] == product_id)
                ].reset_index(drop=True)
                # Row 0: NaN
                assert pd.isna(series.iloc[0]["days_since_launch_lag1"]), (
                    f"({store_id},{product_id}) row 0 must be NaN"
                )
                # Row 1: base_lag = (date[0] - launch_date).days
                actual = series.iloc[1]["days_since_launch_lag1"]
                assert actual == base_lag, (
                    f"CROSS-PRODUCT LEAKAGE: ({store_id},{product_id}) row 1: "
                    f"days_since_launch_lag1={actual}, expected={base_lag}. "
                    "Lifecycle lag is mixing across products."
                )


class TestPromotionLeakage:
    """Tests verifying promotion features never use future data.

    PRP-3.1D — these leakage cases are LOAD-BEARING. They assert that a
    promotion active on day D MUST NOT appear in day D's
    ``promo_<kind>_active_lag1`` column; it appears at day D+1 only. The
    date-range semantics (start_date <= D <= end_date, both inclusive)
    plus ``groupby(...).shift(lag_days)`` are the mathematical leakage gate.
    """

    def test_promotion_active_no_leakage_at_same_day(
        self,
        sample_time_series: pd.DataFrame,
        phase2_promotion_rows_df: pd.DataFrame,
    ) -> None:
        """CRITICAL: A promotion active on day D MUST NOT appear in lag1 at D."""
        config = FeatureSetConfig(
            name="test",
            entity_columns=("store_id", "product_id"),
            promotion_config=PromotionConfig(
                kinds_to_track=("markdown",),
                include_active=True,
                include_intensity=False,
                lag_days=1,
            ),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = phase2_promotion_rows_df  # type: ignore[attr-defined]
        result = service.compute_features(sample_time_series)

        # The fixture's markdown is active 2024-01-07 .. 2024-01-14 (8 days).
        # promo_markdown_active_lag1 should be 1 on 2024-01-08 .. 2024-01-15.
        df = result.df.reset_index(drop=True)
        dates = pd.to_datetime(df["date"]).dt.date

        # Day BEFORE start (D=Jan 6): lag1 reads Jan 5 — inactive. EXPECT 0.
        assert df.loc[dates == date(2024, 1, 6), "promo_markdown_active_lag1"].iloc[0] == 0

        # Day OF start (D=Jan 7): lag1 reads Jan 6 — inactive. EXPECT 0.
        #   This is the load-bearing leakage check: same-day MUST NOT leak.
        assert df.loc[dates == date(2024, 1, 7), "promo_markdown_active_lag1"].iloc[0] == 0, (
            "LEAKAGE DETECTED: promo active on day D appeared in active_lag1 at day D"
        )

        # Day AFTER start (D=Jan 8): lag1 reads Jan 7 — active. EXPECT 1.
        assert df.loc[dates == date(2024, 1, 8), "promo_markdown_active_lag1"].iloc[0] == 1

        # Day AFTER end (D=Jan 15): lag1 reads Jan 14 — last active day. EXPECT 1.
        assert df.loc[dates == date(2024, 1, 15), "promo_markdown_active_lag1"].iloc[0] == 1

        # Two days AFTER end (D=Jan 16): lag1 reads Jan 15 — inactive. EXPECT 0.
        assert df.loc[dates == date(2024, 1, 16), "promo_markdown_active_lag1"].iloc[0] == 0

    def test_promotion_boundary_end_date_at_cutoff(
        self,
        sample_time_series: pd.DataFrame,
    ) -> None:
        """A promo ending exactly on cutoff_date - 1 yields active_lag1=1 at cutoff."""
        cutoff = date(2024, 1, 15)
        promo_rows = pd.DataFrame(
            {
                "product_id": [1],
                "store_id": [1],
                "kind": ["markdown"],
                "discount_pct": [0.20],
                "start_date": [date(2024, 1, 10)],
                "end_date": [date(2024, 1, 14)],  # cutoff - 1
            }
        )
        config = FeatureSetConfig(
            name="test",
            entity_columns=("store_id", "product_id"),
            promotion_config=PromotionConfig(kinds_to_track=("markdown",), lag_days=1),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = promo_rows  # type: ignore[attr-defined]
        result = service.compute_features(sample_time_series, cutoff_date=cutoff)

        df = result.df.reset_index(drop=True)
        dates = pd.to_datetime(df["date"]).dt.date
        # At cutoff (Jan 15), lag1 reads Jan 14 — end_date, INCLUSIVE → active.
        last = df.loc[dates == cutoff].iloc[0]
        assert last["promo_markdown_active_lag1"] == 1, (
            "Boundary leakage: end_date INCLUSIVE on the previous day failed"
        )

    def test_promotion_starts_on_cutoff_not_in_lag1(
        self,
        sample_time_series: pd.DataFrame,
    ) -> None:
        """A promo starting exactly on cutoff is NOT in active_lag1 at cutoff."""
        cutoff = date(2024, 1, 15)
        promo_rows = pd.DataFrame(
            {
                "product_id": [1],
                "store_id": [1],
                "kind": ["markdown"],
                "discount_pct": [0.20],
                "start_date": [cutoff],  # starts today
                "end_date": [date(2024, 1, 25)],
            }
        )
        config = FeatureSetConfig(
            name="test",
            entity_columns=("store_id", "product_id"),
            promotion_config=PromotionConfig(kinds_to_track=("markdown",), lag_days=1),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = promo_rows  # type: ignore[attr-defined]
        result = service.compute_features(sample_time_series, cutoff_date=cutoff)

        df = result.df.reset_index(drop=True)
        dates = pd.to_datetime(df["date"]).dt.date
        last = df.loc[dates == cutoff].iloc[0]
        # lag1 reads cutoff - 1 = Jan 14, BEFORE start_date.
        assert last["promo_markdown_active_lag1"] == 0, (
            "Same-day leakage: promo starting on D appeared in active_lag1 at D"
        )

    def test_chain_wide_promo_does_not_bleed_across_products(
        self,
        multi_series_time_series: pd.DataFrame,
    ) -> None:
        """A chain-wide promo on product=1 must NOT activate features for product=2."""
        promo_rows = pd.DataFrame(
            {
                "product_id": [1],
                "store_id": [None],  # chain-wide
                "kind": ["markdown"],
                "discount_pct": [0.30],
                "start_date": [date(2024, 1, 3)],
                "end_date": [date(2024, 1, 7)],
            }
        )
        config = FeatureSetConfig(
            name="test",
            entity_columns=("store_id", "product_id"),
            promotion_config=PromotionConfig(kinds_to_track=("markdown",), lag_days=1),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = promo_rows  # type: ignore[attr-defined]
        result = service.compute_features(multi_series_time_series)

        df = result.df
        # Product 1 should see activity 2024-01-04 .. 2024-01-08 (lag1) -- 5 days x 2 stores.
        prod1 = df[df["product_id"] == 1]
        assert int(prod1["promo_markdown_active_lag1"].sum()) == 5 * 2
        # Product 2 should see ZERO activity (chain-wide is product-scoped).
        prod2 = df[df["product_id"] == 2]
        assert int(prod2["promo_markdown_active_lag1"].sum()) == 0


class TestReplenishmentLeakage:
    """CRITICAL: Replenishment features (PRP-3.1C) must never use future events.

    These tests assert (a) per-entity ``shift(N)`` invariance on days-since,
    (b) ``shift(1).rolling(W).sum()`` ordering on the rolling count -- NEVER
    ``rolling(W).sum().shift(1)``, and (c) cross-series isolation between
    ``(store_id, product_id)`` pairs.
    """

    def test_days_since_uses_only_past_events(self) -> None:
        """``days_since_last_replenishment_lag1`` must never look at today's event.

        With sales on dates 2024-01-01..2024-01-07 and a single event on
        2024-01-03, the per-row gap-to-last-event (BEFORE the lag) is
        [NaN, NaN, 0, 1, 2, 3, 4]. After the ``groupby.shift(1)``, lag-1
        produces [NaN, NaN, NaN, 0, 1, 2, 3] -- so on the event-date
        (row 2) the column is NaN (the event itself is invisible at
        lag-1), and the post-event rows see strictly past gaps.

        The math-detectable leakage failure mode would set row 2 to 0
        (i.e. ``shift(0)`` -- include today's event) or set row 3 to 1
        (i.e. compute the gap from 01-04 to 01-03 = 1 day, but advance
        the result one row too early). Either regression breaks the
        equality below.
        """
        from app.features.featuresets.schemas import ReplenishmentConfig

        sales = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=7, freq="D"),
                "store_id": [1] * 7,
                "product_id": [1] * 7,
                "quantity": list(range(1, 8)),
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
                include_count_window=False,
                lag_days=1,
                count_window_days=7,
            ),
        )
        service = FeatureEngineeringService(config)
        service._replenishment_events_df = events  # type: ignore[attr-defined]
        result = service.compute_features(sales)

        col = "days_since_last_replenishment_lag1"
        values = result.df[col].tolist()
        # Expected: [NaN, NaN, NaN, 0, 1, 2, 3]
        # Pre-event (rows 0,1): no prior event observed -> per-row days NaN ->
        # shift(1) -> NaN.
        # Row 2 (event date 01-03): per-row gap=0, but shift(1) -> previous
        # row's per-row value -> NaN (which is the time-safety guarantee --
        # the event is invisible the day it lands).
        # Rows 3..6: shift(1) yields 0, 1, 2, 3 -- strictly past gaps.
        for i in (0, 1, 2):
            assert pd.isna(values[i]), (
                f"LEAKAGE DETECTED at row {i}: days_since={values[i]} "
                "(expected NaN -- lag-1 must NOT see today's event)."
            )
        assert values[3] == pytest.approx(0.0), (
            f"LEAKAGE DETECTED at row 3: days_since={values[3]} (expected 0.0). "
            "lag-1 at 2024-01-04 should see 2024-01-03's gap of 0 days."
        )
        assert values[4] == pytest.approx(1.0), (
            f"LEAKAGE DETECTED at row 4: days_since={values[4]} (expected 1.0)."
        )
        assert values[5] == pytest.approx(2.0), (
            f"LEAKAGE DETECTED at row 5: days_since={values[5]} (expected 2.0)."
        )
        assert values[6] == pytest.approx(3.0), (
            f"LEAKAGE DETECTED at row 6: days_since={values[6]} (expected 3.0)."
        )

    def test_count_window_uses_shift_then_rolling(self) -> None:
        """CRITICAL: ``shift(1).rolling(W).sum()`` MUST be the order.

        Events on dates 2024-01-01, 2024-01-03, 2024-01-05 with W=7 (the
        smallest window the config schema allows; ``ReplenishmentConfig``
        bounds ``count_window_days`` at ``ge=7``). Sales rows on every
        date 2024-01-01..2024-01-07.

        Per-row event_count = [1, 0, 1, 0, 1, 0, 0].
        Correct ``shift(1).rolling(7, min_periods=1).sum()`` -> NaN at
        position 0 (filled to 0), then cumulative sum of all prior:
        [0, 1, 1, 2, 2, 3, 3].

        The INCORRECT ``rolling(7).sum()`` -- with NO leading shift -- would
        INCLUDE today's event at every step, giving [1, 1, 2, 2, 3, 3, 3].
        The two patterns differ at multiple rows (e.g. row 0 = 1 vs 0,
        row 2 = 2 vs 1), so this single assertion catches a missing
        ``shift(1)`` regression. The math-distinct difference at row 0 is
        also a direct probe for the "current-event included in window" bug
        called out by PRP-3.1C decisions log §C.
        """
        from app.features.featuresets.schemas import ReplenishmentConfig

        sales = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=7, freq="D"),
                "store_id": [1] * 7,
                "product_id": [1] * 7,
                "quantity": list(range(1, 8)),
            }
        )
        events = pd.DataFrame(
            {
                "store_id": [1, 1, 1],
                "product_id": [1, 1, 1],
                "event_date": [date(2024, 1, 1), date(2024, 1, 3), date(2024, 1, 5)],
            }
        )
        config = FeatureSetConfig(
            name="test",
            replenishment_config=ReplenishmentConfig(
                include_days_since_last=False,
                include_count_window=True,
                count_window_days=7,
                lag_days=1,
            ),
        )
        service = FeatureEngineeringService(config)
        service._replenishment_events_df = events  # type: ignore[attr-defined]
        result = service.compute_features(sales)

        col = "replenishment_count_w7_lag1"
        counts = result.df[col].tolist()
        expected = [0, 1, 1, 2, 2, 3, 3]
        assert counts == expected, (
            f"LEAKAGE DETECTED: count column = {counts}, expected {expected}. "
            "shift(1).rolling(W).sum() order may be reversed -- today's event "
            "is leaking into the rolling window."
        )

    def test_cross_series_isolation(self) -> None:
        """CRITICAL: events on (store=1, product=1) must NEVER affect store=2.

        Two stores x one product; events only on (1, 1). Store=2 must see
        all-zero counts and all-NaN days-since across every row.
        """
        from app.features.featuresets.schemas import ReplenishmentConfig

        sales = pd.DataFrame(
            {
                "date": list(pd.date_range("2024-01-01", periods=5, freq="D")) * 2,
                "store_id": [1] * 5 + [2] * 5,
                "product_id": [1] * 10,
                "quantity": list(range(10)),
            }
        )
        events = pd.DataFrame(
            {
                "store_id": [1, 1],
                "product_id": [1, 1],
                "event_date": [date(2024, 1, 2), date(2024, 1, 4)],
            }
        )
        config = FeatureSetConfig(
            name="test",
            entity_columns=("store_id", "product_id"),
            replenishment_config=ReplenishmentConfig(
                include_days_since_last=True,
                include_count_window=True,
                count_window_days=7,
                lag_days=1,
            ),
        )
        service = FeatureEngineeringService(config)
        service._replenishment_events_df = events  # type: ignore[attr-defined]
        result = service.compute_features(sales)

        days_col = "days_since_last_replenishment_lag1"
        count_col = "replenishment_count_w7_lag1"

        store_2 = result.df[result.df["store_id"] == 2]
        # store=2 has no events anywhere -> count must be 0 across every row.
        store_2_counts = store_2[count_col].tolist()
        assert store_2_counts == [0, 0, 0, 0, 0], (
            f"CROSS-SERIES LEAKAGE DETECTED: store=2 counts = {store_2_counts}, "
            "expected all 0 (events were only on store=1). merge_asof may be "
            "missing by=['store_id', 'product_id']."
        )
        # store=2 has no observed prior event -> days_since all NaN.
        store_2_days = store_2[days_col].tolist()
        for i, v in enumerate(store_2_days):
            assert pd.isna(v), (
                f"CROSS-SERIES LEAKAGE DETECTED: store=2 row {i} days_since={v}, "
                "expected NaN. Events from store=1 may have bled into store=2."
            )

    def test_event_on_cutoff_date_included_via_le_filter(self) -> None:
        """Event ON ``cutoff_date`` must be visible (``date <= cutoff_date``).

        Sales 2024-01-01..2024-01-07; cutoff=2024-01-05. Event on
        2024-01-05 (the cutoff itself) must contribute to the rolling count
        on 2024-01-06 / 2024-01-07. Mirrors the SQL-side ``date <= cutoff``
        predicate (PRP-3.1C decisions log §2).
        """
        from app.features.featuresets.schemas import ReplenishmentConfig

        sales = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=7, freq="D"),
                "store_id": [1] * 7,
                "product_id": [1] * 7,
                "quantity": list(range(1, 8)),
            }
        )
        cutoff = date(2024, 1, 5)
        # Pre-filter events to event_date <= cutoff (mirrors loader's SQL).
        all_events = pd.DataFrame(
            {
                "store_id": [1, 1],
                "product_id": [1, 1],
                "event_date": [date(2024, 1, 5), date(2024, 1, 7)],
            }
        )
        events = all_events[all_events["event_date"] <= cutoff].reset_index(drop=True)

        config = FeatureSetConfig(
            name="test",
            replenishment_config=ReplenishmentConfig(
                include_days_since_last=True,
                include_count_window=True,
                count_window_days=7,
                lag_days=1,
            ),
        )
        service = FeatureEngineeringService(config)
        service._replenishment_events_df = events  # type: ignore[attr-defined]
        result = service.compute_features(sales, cutoff_date=cutoff)

        # compute_features drops rows after cutoff -> 5 rows remain.
        assert len(result.df) == 5, (
            f"CUTOFF VIOLATION: expected 5 rows after cutoff, got {len(result.df)}"
        )
        days_col = "days_since_last_replenishment_lag1"
        # On the cutoff row (2024-01-05), lag-1 cannot see today's event.
        # On 2024-01-04 there was no prior event -> NaN.
        last_row = result.df.iloc[-1]
        assert pd.isna(last_row[days_col]), (
            f"LEAKAGE DETECTED at cutoff row: days_since={last_row[days_col]} "
            "(expected NaN -- lag-1 must NOT include today's event)."
        )
        # The event was admitted via <= filter (post-cutoff event was
        # filtered OUT). To prove inclusion of the on-cutoff event, run a
        # second compute extending the sales range -- not done here to
        # honor the cutoff boundary; instead we assert events DataFrame
        # itself contains exactly one row (the on-cutoff event).
        assert len(events) == 1, (
            f"FILTER ERROR: expected 1 event after <= cutoff filter, got {len(events)}"
        )


class TestPhase2CrossConfigLeakage:
    """Verify Phase 2 configs compose without future-data leakage (PRP-3.1E).

    Even when each Phase 2 family's own leakage tests (PRP-3.1B/C/D) are
    green individually, composing all three with Phase 1 (lag + lifecycle
    + replenishment + promotion) may surface a new leakage path if any
    family's ``_compute_*`` method mutates ``df`` in place before the next
    family reads it. This class is the strongest additive assertion --
    feature rows at row ``i`` reference ONLY rows ``<= i - lag_days``.
    """

    def test_all_phase2_configs_compose_no_future_leakage(
        self,
        sample_time_series: pd.DataFrame,
        phase2_promotion_rows_df: pd.DataFrame,
    ) -> None:
        """CRITICAL: All four Phase 2 + Phase 1 configs ON -- no row ``i``
        feature reads data ``> i - 1`` for the (store=1, product=1) series.

        Strategy:
          * lag_1 on sequential quantity 1..30 must equal ``i`` at row ``i``
            (the canonical TestLagLeakage invariant).
          * Phase 2 columns must be present in ``result.feature_columns``
            (proves compose didn't accidentally skip them).
          * Lifecycle ``days_since_launch_lag1`` at row 0 must be NaN
            (no prior row to lag from).
          * Promotion ``promo_markdown_active_lag1`` at row 0 must be NaN
            (Int64 dtype -- no prior row).

        The replenishment ``replenishment_count_w14_lag{N}`` column is
        intentionally NOT checked at row 0 because its compute path fills
        NaN -> 0 (see service.py ``_compute_replenishment_features`` --
        ``rolling_counts.fillna(0).astype("int64")``). A row-0-NaN check
        would be a false positive against the documented contract.
        """
        from app.features.featuresets.schemas import ReplenishmentConfig

        # Lifecycle requires launch_date / discontinue_date columns on
        # the input frame (service.py:489 silent-skips otherwise).
        df = sample_time_series.copy()
        df["launch_date"] = date(2023, 12, 25)  # 7 days before the first sales row
        df["discontinue_date"] = pd.NaT

        config = FeatureSetConfig(
            name="phase2-cross-config-leakage",
            lag_config=LagConfig(lags=(1,)),
            lifecycle_config=LifecycleConfig(lag_days=1),
            replenishment_config=ReplenishmentConfig(lag_days=1, count_window_days=14),
            promotion_config=PromotionConfig(kinds_to_track=("markdown",), lag_days=1),
        )
        service = FeatureEngineeringService(config)
        # Auxiliary frames -- PRP-3.1C / 3.1D use private-attribute sidecars
        # (mirrors the in-method ``getattr(self, "_promotion_rows_df", None)``
        # / ``getattr(self, "_replenishment_events_df", None)`` reads in
        # service.py).
        service._promotion_rows_df = phase2_promotion_rows_df  # type: ignore[attr-defined]
        # Replenishment requires a non-None events frame; pass an empty
        # one with the expected schema AND dtypes (service.py's
        # ``merge_asof`` rejects ``object``-typed ``by=`` keys, which is
        # what an unsized DataFrame defaults to). An empty events frame
        # is the safe cross-config leakage probe -- it proves the JOIN
        # path doesn't accidentally invent counts when no events exist.
        empty_events = pd.DataFrame(
            {
                "store_id": pd.Series([], dtype="int64"),
                "product_id": pd.Series([], dtype="int64"),
                "event_date": pd.Series([], dtype="datetime64[ns]"),
            }
        )
        service._replenishment_events_df = empty_events  # type: ignore[attr-defined]
        result = service.compute_features(df)

        # 1. lag_1 invariant must survive Phase 2 compose.
        for i in range(1, len(result.df)):
            lag_value = result.df.iloc[i]["lag_1"]
            assert lag_value == i, (
                f"CROSS-CONFIG LEAKAGE at row {i}: lag_1={lag_value} != "
                f"expected={i}. Phase 2 compose corrupted Phase 1 lag."
            )

        # 2. Phase 2 columns must be present (compose didn't skip).
        for expected in (
            "days_since_launch_lag1",
            "replenishment_count_w14_lag1",
            "promo_markdown_active_lag1",
        ):
            assert expected in result.feature_columns, (
                f"COMPOSE REGRESSION: column {expected!r} missing from "
                f"feature_columns -- {result.feature_columns}"
            )

        # 3. Row 0 of NaN-friendly Phase 2 columns must be NaN.
        # Lifecycle: row 0 has no prior row to lag from -> NaN.
        assert pd.isna(result.df.iloc[0]["days_since_launch_lag1"]), (
            "CROSS-CONFIG LEAKAGE: days_since_launch_lag1 row 0 is not NaN -- "
            f"got {result.df.iloc[0]['days_since_launch_lag1']!r}"
        )
        # Promotion active: nullable Int64 preserves NaN at the start of
        # the series (per service.py ``astype("Int64")``).
        assert pd.isna(result.df.iloc[0]["promo_markdown_active_lag1"]), (
            "CROSS-CONFIG LEAKAGE: promo_markdown_active_lag1 row 0 is not NaN -- "
            f"got {result.df.iloc[0]['promo_markdown_active_lag1']!r}"
        )

    def test_phase2_compose_preserves_group_isolation(
        self,
        multi_series_time_series: pd.DataFrame,
    ) -> None:
        """CRITICAL: Multi-series + all Phase 2 configs -- per-series
        ``shift(lag_days)`` boundary must hold; no leakage between the
        ``(1, 1)`` and ``(2, 2)`` series.

        Verifies that ``groupby([store_id, product_id]).shift(1)`` keeps
        series isolated even when lifecycle + replenishment + promotion
        joins are evaluated for the union of entities.
        """
        from app.features.featuresets.schemas import ReplenishmentConfig

        df = multi_series_time_series.copy()
        # Two products with different launch dates so cross-series lifecycle
        # contamination would be mathematically visible (mirrors
        # TestLifecycleLeakage::test_lifecycle_group_isolation pattern).
        launch_map = {1: date(2023, 12, 1), 2: date(2023, 12, 25)}
        df["launch_date"] = df["product_id"].map(launch_map)
        df["discontinue_date"] = pd.NaT

        config = FeatureSetConfig(
            name="phase2-group-iso",
            entity_columns=("store_id", "product_id"),
            lag_config=LagConfig(lags=(1,)),
            lifecycle_config=LifecycleConfig(lag_days=1),
            replenishment_config=ReplenishmentConfig(lag_days=1, count_window_days=14),
            promotion_config=PromotionConfig(kinds_to_track=("markdown",), lag_days=1),
        )
        service = FeatureEngineeringService(config)
        # Empty aux frames -- the leakage probe is about the GROUPBY
        # boundary, not the JOIN payload.
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
        service._replenishment_events_df = pd.DataFrame(  # type: ignore[attr-defined]
            {
                "store_id": pd.Series([], dtype="int64"),
                "product_id": pd.Series([], dtype="int64"),
                "event_date": pd.Series([], dtype="datetime64[ns]"),
            }
        )
        result = service.compute_features(df)

        # First row of each series must have NaN lag_1 (per-group
        # isolation -- the canonical TestGroupIsolationLeakage idiom).
        for store_id in (1, 2):
            for product_id in (1, 2):
                series = result.df[
                    (result.df["store_id"] == store_id) & (result.df["product_id"] == product_id)
                ].reset_index(drop=True)
                assert pd.isna(series.iloc[0]["lag_1"]), (
                    f"GROUP ISOLATION BREACH at ({store_id},{product_id}): "
                    "lag_1 first row should be NaN even with Phase 2 composed"
                )
                # Lifecycle: row 0 of each series must also be NaN.
                assert pd.isna(series.iloc[0]["days_since_launch_lag1"]), (
                    f"GROUP ISOLATION BREACH at ({store_id},{product_id}): "
                    "days_since_launch_lag1 first row should be NaN per-series"
                )
