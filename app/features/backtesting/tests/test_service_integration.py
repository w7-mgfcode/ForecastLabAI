"""Integration tests for BacktestingService.

These tests verify the service layer interacts correctly with the database,
focusing on data loading and full backtest execution.

Requires PostgreSQL to be running: docker-compose up -d
"""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.backtesting.schemas import BacktestConfig, SplitConfig
from app.features.backtesting.service import BacktestingService
from app.features.data_platform.models import Product, SalesDaily, Store
from app.features.forecasting.schemas import NaiveModelConfig


@pytest.mark.integration
@pytest.mark.asyncio
class TestBacktestingServiceIntegration:
    """Integration tests for BacktestingService._load_series_data and run_backtest."""

    async def test_load_series_data_returns_correct_values(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test that _load_series_data returns correct values from database."""
        service = BacktestingService()

        series_data = await service._load_series_data(
            db=db_session,
            store_id=sample_store.id,
            product_id=sample_product.id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 29),
        )

        assert series_data.store_id == sample_store.id
        assert series_data.product_id == sample_product.id
        assert series_data.n_observations == 120

        # Verify values are 1, 2, 3, ..., 120 (sequential)
        for i, val in enumerate(series_data.values):
            expected = float(i + 1)
            assert val == expected, f"Expected {expected} at index {i}, got {val}"

    async def test_load_series_data_filters_by_date_range(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test that _load_series_data correctly filters by date range."""
        service = BacktestingService()

        # Request only first 30 days
        series_data = await service._load_series_data(
            db=db_session,
            store_id=sample_store.id,
            product_id=sample_product.id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 30),
        )

        assert series_data.n_observations == 30
        assert series_data.dates[0] == date(2024, 1, 1)
        assert series_data.dates[-1] == date(2024, 1, 30)

        # Values should be 1 through 30
        assert float(series_data.values[0]) == 1.0
        assert float(series_data.values[-1]) == 30.0

    async def test_load_series_data_filters_by_store_product(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test that _load_series_data returns empty for non-matching store/product."""
        service = BacktestingService()

        # Request with non-existent store
        series_data = await service._load_series_data(
            db=db_session,
            store_id=9999,
            product_id=sample_product.id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 29),
        )

        assert series_data.n_observations == 0
        assert len(series_data.dates) == 0
        assert len(series_data.values) == 0

    async def test_load_series_data_returns_chronological_order(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test that _load_series_data returns dates in chronological order."""
        service = BacktestingService()

        series_data = await service._load_series_data(
            db=db_session,
            store_id=sample_store.id,
            product_id=sample_product.id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 29),
        )

        # Verify dates are sorted
        dates = series_data.dates
        assert dates == sorted(dates), "Dates should be in chronological order"

        # Verify each date is one day after previous
        for i in range(1, len(dates)):
            delta = (dates[i] - dates[i - 1]).days
            assert delta == 1, f"Gap between dates at index {i}: expected 1, got {delta}"

    async def test_full_backtest_with_real_data(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test complete backtest execution with real database data."""
        service = BacktestingService()

        config = BacktestConfig(
            split_config=SplitConfig(
                strategy="expanding",
                n_splits=5,
                min_train_size=30,
                gap=0,
                horizon=14,
            ),
            model_config_main=NaiveModelConfig(),
            include_baselines=True,
            store_fold_details=True,
        )

        response = await service.run_backtest(
            db=db_session,
            store_id=sample_store.id,
            product_id=sample_product.id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 29),
            config=config,
        )

        # Verify response structure
        assert response.store_id == sample_store.id
        assert response.product_id == sample_product.id
        assert response.leakage_check_passed is True
        assert response.duration_ms > 0

        # Verify main model results
        main_results = response.main_model_results
        assert main_results.model_type == "naive"
        assert len(main_results.fold_results) == 5

        # Verify aggregated metrics exist and are reasonable
        agg_metrics = main_results.aggregated_metrics
        assert "mae" in agg_metrics
        assert "smape" in agg_metrics
        assert "wape" in agg_metrics
        assert "bias" in agg_metrics
        assert agg_metrics["mae"] >= 0
        assert 0 <= agg_metrics["smape"] <= 200

        # Verify baseline results
        assert response.baseline_results is not None
        assert len(response.baseline_results) >= 1

        # Verify comparison summary
        assert response.comparison_summary is not None

    async def test_full_backtest_with_sliding_window(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test complete backtest with sliding window strategy."""
        service = BacktestingService()

        config = BacktestConfig(
            split_config=SplitConfig(
                strategy="sliding",
                n_splits=5,
                min_train_size=30,
                gap=0,
                horizon=14,
            ),
            model_config_main=NaiveModelConfig(),
            include_baselines=False,
            store_fold_details=True,
        )

        response = await service.run_backtest(
            db=db_session,
            store_id=sample_store.id,
            product_id=sample_product.id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 29),
            config=config,
        )

        # Verify sliding window: train sizes should be constant
        fold_results = response.main_model_results.fold_results
        train_sizes = [f.split.train_size for f in fold_results]
        assert len(set(train_sizes)) == 1, f"Train sizes should be constant, got {train_sizes}"

    async def test_backtest_raises_for_no_data(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test that backtest raises ValueError when no data is found."""
        service = BacktestingService()

        config = BacktestConfig(
            split_config=SplitConfig(
                strategy="expanding",
                n_splits=5,
                min_train_size=30,
                gap=0,
                horizon=14,
            ),
            model_config_main=NaiveModelConfig(),
            include_baselines=False,
            store_fold_details=True,
        )

        with pytest.raises(ValueError, match="No data found"):
            await service.run_backtest(
                db=db_session,
                store_id=9999,  # Non-existent
                product_id=sample_product.id,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 4, 29),
                config=config,
            )

    async def test_backtest_with_gap_produces_correct_splits(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test that gap parameter creates correct separation between train and test."""
        service = BacktestingService()

        gap_days = 7
        config = BacktestConfig(
            split_config=SplitConfig(
                strategy="expanding",
                n_splits=3,
                min_train_size=30,
                gap=gap_days,
                horizon=14,
            ),
            model_config_main=NaiveModelConfig(),
            include_baselines=False,
            store_fold_details=True,
        )

        response = await service.run_backtest(
            db=db_session,
            store_id=sample_store.id,
            product_id=sample_product.id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 29),
            config=config,
        )

        # Verify gap between train_end and test_start
        for fold in response.main_model_results.fold_results:
            train_end = fold.split.train_end
            test_start = fold.split.test_start
            actual_gap = (test_start - train_end).days
            # Gap should be at least gap_days (could be more if data is sparse)
            assert actual_gap >= gap_days, f"Expected gap >= {gap_days}, got {actual_gap}"
