"""Tests for backtesting service."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from app.features.backtesting.schemas import (
    BacktestConfig,
    BacktestResponse,
    SplitConfig,
)
from app.features.backtesting.service import BacktestingService, SeriesData
from app.features.forecasting.schemas import NaiveModelConfig, SeasonalNaiveModelConfig


class TestSeriesData:
    """Tests for SeriesData dataclass."""

    def test_series_data_creation(self) -> None:
        """Test SeriesData creation and n_observations computation."""
        dates = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
        values = np.array([10.0, 20.0, 30.0])

        data = SeriesData(
            dates=dates,
            values=values,
            store_id=1,
            product_id=1,
        )

        assert data.n_observations == 3
        assert data.store_id == 1
        assert data.product_id == 1

    def test_series_data_empty(self) -> None:
        """Test SeriesData with empty data."""
        data = SeriesData(
            dates=[],
            values=np.array([], dtype=np.float64),
            store_id=1,
            product_id=1,
        )

        assert data.n_observations == 0


class TestBacktestingServiceRunModelBacktest:
    """Tests for _run_model_backtest method."""

    def test_run_model_backtest_naive(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test running backtest with naive model."""
        service = BacktestingService()

        series_data = SeriesData(
            dates=sample_dates_120,
            values=sample_values_120,
            store_id=1,
            product_id=1,
        )

        from app.features.backtesting.splitter import TimeSeriesSplitter

        splitter = TimeSeriesSplitter(sample_split_config_expanding)

        result = service._run_model_backtest(
            series_data=series_data,
            splitter=splitter,
            model_config=NaiveModelConfig(),
            store_fold_details=True,
        )

        assert result.model_type == "naive"
        assert len(result.fold_results) == sample_split_config_expanding.n_splits
        assert "mae" in result.aggregated_metrics
        assert "smape" in result.aggregated_metrics

    def test_run_model_backtest_without_fold_details(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test running backtest without storing fold details."""
        service = BacktestingService()

        series_data = SeriesData(
            dates=sample_dates_120,
            values=sample_values_120,
            store_id=1,
            product_id=1,
        )

        from app.features.backtesting.splitter import TimeSeriesSplitter

        splitter = TimeSeriesSplitter(sample_split_config_expanding)

        result = service._run_model_backtest(
            series_data=series_data,
            splitter=splitter,
            model_config=NaiveModelConfig(),
            store_fold_details=False,
        )

        # Fold results should have empty arrays
        for fold in result.fold_results:
            assert fold.dates == []
            assert fold.actuals == []
            assert fold.predictions == []
            # But metrics should still be present
            assert fold.metrics is not None


class TestBacktestingServiceBaselineComparisons:
    """Tests for baseline comparison functionality."""

    def test_run_baseline_comparisons(
        self,
        sample_dates_84: list[date],
        sample_seasonal_values_84: np.ndarray,
    ) -> None:
        """Test running baseline comparisons."""
        service = BacktestingService()

        series_data = SeriesData(
            dates=sample_dates_84,
            values=sample_seasonal_values_84,
            store_id=1,
            product_id=1,
        )

        config = SplitConfig(
            strategy="expanding",
            n_splits=3,
            min_train_size=21,
            gap=0,
            horizon=7,
        )

        from app.features.backtesting.splitter import TimeSeriesSplitter

        splitter = TimeSeriesSplitter(config)

        results = service._run_baseline_comparisons(
            series_data=series_data,
            splitter=splitter,
            store_fold_details=True,
        )

        # Should have naive and seasonal_naive baselines
        model_types = [r.model_type for r in results]
        assert "naive" in model_types
        assert "seasonal_naive" in model_types

    def test_generate_comparison_summary(
        self,
        sample_dates_84: list[date],
        sample_seasonal_values_84: np.ndarray,
    ) -> None:
        """Test comparison summary generation."""
        service = BacktestingService()

        series_data = SeriesData(
            dates=sample_dates_84,
            values=sample_seasonal_values_84,
            store_id=1,
            product_id=1,
        )

        config = SplitConfig(
            strategy="expanding",
            n_splits=3,
            min_train_size=21,
            gap=0,
            horizon=7,
        )

        from app.features.backtesting.splitter import TimeSeriesSplitter

        splitter = TimeSeriesSplitter(config)

        main_results = service._run_model_backtest(
            series_data=series_data,
            splitter=splitter,
            model_config=NaiveModelConfig(),
            store_fold_details=True,
        )

        baseline_results = service._run_baseline_comparisons(
            series_data=series_data,
            splitter=splitter,
            store_fold_details=True,
        )

        summary = service._generate_comparison_summary(
            main_results=main_results,
            baseline_results=baseline_results,
        )

        # Check summary structure
        assert "mae" in summary
        assert "main" in summary["mae"]

        # Check baseline comparisons are present
        if "naive" in [r.model_type for r in baseline_results]:
            assert "naive" in summary["mae"]

    def test_comparison_improvement_percentage(self) -> None:
        """Test improvement percentage calculation."""
        service = BacktestingService()

        from app.features.backtesting.schemas import ModelBacktestResult

        # Create mock results
        main_results = ModelBacktestResult(
            model_type="test_model",
            config_hash="abc123",
            fold_results=[],
            aggregated_metrics={"mae": 10.0},
            metric_std={"mae_std": 1.0},
        )

        baseline_results = [
            ModelBacktestResult(
                model_type="naive",
                config_hash="def456",
                fold_results=[],
                aggregated_metrics={"mae": 20.0},  # Naive is worse
                metric_std={"mae_std": 2.0},
            )
        ]

        summary = service._generate_comparison_summary(
            main_results=main_results,
            baseline_results=baseline_results,
        )

        # Main model has MAE=10, naive has MAE=20
        # Improvement = (20-10)/20 * 100 = 50%
        assert summary["mae"]["vs_naive_pct"] == pytest.approx(50.0)


class TestBacktestingServiceLoadData:
    """Tests for _load_series_data method."""

    @pytest.mark.asyncio
    async def test_load_series_data_returns_empty_for_no_data(self) -> None:
        """Test loading returns empty SeriesData when no data found."""
        service = BacktestingService()

        # Mock database session
        mock_result = MagicMock()
        mock_result.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = await service._load_series_data(
            db=mock_db,
            store_id=999,
            product_id=999,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        assert data.n_observations == 0
        assert len(data.dates) == 0
        assert len(data.values) == 0

    @pytest.mark.asyncio
    async def test_load_series_data_with_rows(self) -> None:
        """Test loading series data with mock rows."""
        service = BacktestingService()

        # Create mock rows
        mock_rows = [
            type("Row", (), {"date": date(2024, 1, 1), "quantity": 100.0})(),
            type("Row", (), {"date": date(2024, 1, 2), "quantity": 150.0})(),
            type("Row", (), {"date": date(2024, 1, 3), "quantity": 200.0})(),
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = await service._load_series_data(
            db=mock_db,
            store_id=1,
            product_id=1,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert data.n_observations == 3
        assert data.store_id == 1
        assert data.product_id == 1
        assert len(data.dates) == 3
        assert data.values[0] == 100.0


class TestBacktestingServiceRunBacktest:
    """Tests for run_backtest method."""

    @pytest.mark.asyncio
    async def test_run_backtest_no_data_raises(self) -> None:
        """Test run_backtest raises ValueError when no data found."""
        service = BacktestingService()

        # Mock database returning no data
        mock_result = MagicMock()
        mock_result.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        config = BacktestConfig(
            split_config=SplitConfig(),
            model_config_main=NaiveModelConfig(),
        )

        with pytest.raises(ValueError, match="No data found"):
            await service.run_backtest(
                db=mock_db,
                store_id=1,
                product_id=1,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 12, 31),
                config=config,
            )

    @pytest.mark.asyncio
    async def test_run_backtest_returns_response(self) -> None:
        """Test run_backtest returns BacktestResponse."""
        service = BacktestingService()

        # Create mock rows for 120 days
        start = date(2024, 1, 1)
        mock_rows = [
            type("Row", (), {"date": start + timedelta(days=i), "quantity": float(i + 1)})()
            for i in range(120)
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        config = BacktestConfig(
            split_config=SplitConfig(
                strategy="expanding",
                n_splits=3,
                min_train_size=30,
                gap=0,
                horizon=14,
            ),
            model_config_main=NaiveModelConfig(),
            include_baselines=True,
            store_fold_details=True,
        )

        response = await service.run_backtest(
            db=mock_db,
            store_id=1,
            product_id=1,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 30),
            config=config,
        )

        assert isinstance(response, BacktestResponse)
        assert response.store_id == 1
        assert response.product_id == 1
        assert response.backtest_id is not None
        assert len(response.main_model_results.fold_results) == 3
        assert response.baseline_results is not None
        assert response.comparison_summary is not None
        assert response.leakage_check_passed is True

    @pytest.mark.asyncio
    async def test_run_backtest_without_baselines(self) -> None:
        """Test run_backtest without baseline comparisons."""
        service = BacktestingService()

        # Create mock rows for 120 days
        start = date(2024, 1, 1)
        mock_rows = [
            type("Row", (), {"date": start + timedelta(days=i), "quantity": float(i + 1)})()
            for i in range(120)
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        config = BacktestConfig(
            split_config=SplitConfig(
                strategy="expanding",
                n_splits=3,
                min_train_size=30,
                gap=0,
                horizon=14,
            ),
            model_config_main=NaiveModelConfig(),
            include_baselines=False,
            store_fold_details=True,
        )

        response = await service.run_backtest(
            db=mock_db,
            store_id=1,
            product_id=1,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 30),
            config=config,
        )

        assert response.baseline_results is None
        assert response.comparison_summary is None


class TestBacktestingServiceMetrics:
    """Tests for metrics in backtest results."""

    def test_fold_metrics_are_computed(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test that fold metrics are computed correctly."""
        service = BacktestingService()

        series_data = SeriesData(
            dates=sample_dates_120,
            values=sample_values_120,
            store_id=1,
            product_id=1,
        )

        from app.features.backtesting.splitter import TimeSeriesSplitter

        splitter = TimeSeriesSplitter(sample_split_config_expanding)

        result = service._run_model_backtest(
            series_data=series_data,
            splitter=splitter,
            model_config=NaiveModelConfig(),
            store_fold_details=True,
        )

        # Check each fold has metrics
        for fold in result.fold_results:
            assert "mae" in fold.metrics
            assert "smape" in fold.metrics
            assert "wape" in fold.metrics
            assert "bias" in fold.metrics

    def test_aggregated_metrics_include_stability(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test that aggregated metrics include stability index."""
        service = BacktestingService()

        series_data = SeriesData(
            dates=sample_dates_120,
            values=sample_values_120,
            store_id=1,
            product_id=1,
        )

        from app.features.backtesting.splitter import TimeSeriesSplitter

        splitter = TimeSeriesSplitter(sample_split_config_expanding)

        result = service._run_model_backtest(
            series_data=series_data,
            splitter=splitter,
            model_config=NaiveModelConfig(),
            store_fold_details=True,
        )

        # Check stability metrics exist
        assert "mae_stability" in result.metric_std
        assert "smape_stability" in result.metric_std


class TestBacktestingServiceSeasonalModel:
    """Tests for seasonal model in backtesting."""

    def test_seasonal_naive_on_seasonal_data(
        self,
        sample_dates_84: list[date],
        sample_seasonal_values_84: np.ndarray,
    ) -> None:
        """Test seasonal naive performs well on seasonal data."""
        service = BacktestingService()

        series_data = SeriesData(
            dates=sample_dates_84,
            values=sample_seasonal_values_84,
            store_id=1,
            product_id=1,
        )

        config = SplitConfig(
            strategy="expanding",
            n_splits=3,
            min_train_size=21,  # 3 weeks minimum
            gap=0,
            horizon=7,
        )

        from app.features.backtesting.splitter import TimeSeriesSplitter

        splitter = TimeSeriesSplitter(config)

        # Run both naive and seasonal naive
        naive_result = service._run_model_backtest(
            series_data=series_data,
            splitter=splitter,
            model_config=NaiveModelConfig(),
            store_fold_details=True,
        )

        seasonal_result = service._run_model_backtest(
            series_data=series_data,
            splitter=splitter,
            model_config=SeasonalNaiveModelConfig(season_length=7),
            store_fold_details=True,
        )

        # Seasonal naive should perform better on seasonal data
        # (lower MAE)
        assert seasonal_result.aggregated_metrics["mae"] < naive_result.aggregated_metrics["mae"]
