"""Backtesting service for model evaluation.

Orchestrates:
- Loading time series data from database
- Generating time-based CV splits
- Training and predicting with models per fold
- Calculating metrics and aggregating results
- Running baseline comparisons
- Saving results to configured directory

CRITICAL: All operations respect time-safety constraints.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import date as date_type
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.backtesting.metrics import MetricsCalculator
from app.features.backtesting.schemas import (
    BacktestConfig,
    BacktestResponse,
    FoldResult,
    ModelBacktestResult,
    SplitBoundary,
)
from app.features.backtesting.splitter import TimeSeriesSplitter
from app.features.data_platform.models import SalesDaily
from app.features.forecasting.models import model_factory
from app.features.forecasting.schemas import (
    ModelConfig,
    NaiveModelConfig,
    SeasonalNaiveModelConfig,
)

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


@dataclass
class SeriesData:
    """Container for loaded time series data.

    Attributes:
        dates: List of dates in chronological order.
        values: Target values as numpy array.
        store_id: Store ID.
        product_id: Product ID.
        n_observations: Number of observations.
    """

    dates: list[date_type]
    values: np.ndarray[Any, np.dtype[np.floating[Any]]]
    store_id: int
    product_id: int
    n_observations: int = field(init=False)

    def __post_init__(self) -> None:
        """Compute derived fields."""
        self.n_observations = len(self.values)


class BacktestingService:
    """Service for running backtests on forecasting models.

    Provides orchestration layer for:
    - Loading time series data from database
    - Generating time-based CV splits
    - Training and predicting per fold
    - Computing and aggregating metrics
    - Running mandatory baseline comparisons

    CRITICAL: All operations use Settings for reproducibility.
    """

    def __init__(self) -> None:
        """Initialize the backtesting service."""
        self.settings = get_settings()
        self.metrics_calculator = MetricsCalculator()

    def _validate_config(self, config: BacktestConfig) -> None:
        """Validate backtest configuration against settings constraints.

        Args:
            config: Backtest configuration to validate.

        Raises:
            ValueError: If config violates settings constraints.
        """
        split_config = config.split_config

        # Validate n_splits against backtest_max_splits
        if split_config.n_splits > self.settings.backtest_max_splits:
            raise ValueError(
                f"n_splits ({split_config.n_splits}) exceeds maximum allowed "
                f"({self.settings.backtest_max_splits}). "
                f"Adjust split_config.n_splits or increase BACKTEST_MAX_SPLITS setting."
            )

        # Validate gap against backtest_max_gap
        if split_config.gap > self.settings.backtest_max_gap:
            raise ValueError(
                f"gap ({split_config.gap}) exceeds maximum allowed "
                f"({self.settings.backtest_max_gap}). "
                f"Adjust split_config.gap or increase BACKTEST_MAX_GAP setting."
            )

        # Validate min_train_size meets minimum threshold
        if split_config.min_train_size < self.settings.backtest_default_min_train_size:
            logger.warning(
                "backtesting.min_train_size_below_default",
                provided=split_config.min_train_size,
                default=self.settings.backtest_default_min_train_size,
                message="Using provided min_train_size below recommended default",
            )

    def save_results(
        self,
        response: BacktestResponse,
        filename: str | None = None,
    ) -> Path:
        """Save backtest results to configured results directory.

        Args:
            response: BacktestResponse to save.
            filename: Optional custom filename. Defaults to backtest_id.json.

        Returns:
            Path to saved results file.
        """
        results_dir = Path(self.settings.backtest_results_dir)
        results_dir.mkdir(parents=True, exist_ok=True)

        if filename is None:
            filename = f"{response.backtest_id}.json"

        file_path = results_dir / filename
        file_path.write_text(response.model_dump_json(indent=2))

        logger.info(
            "backtesting.results_saved",
            backtest_id=response.backtest_id,
            file_path=str(file_path),
        )

        return file_path

    async def run_backtest(
        self,
        db: AsyncSession,
        store_id: int,
        product_id: int,
        start_date: date_type,
        end_date: date_type,
        config: BacktestConfig,
    ) -> BacktestResponse:
        """Run a complete backtest for a single series.

        Args:
            db: Database session.
            store_id: Store ID to backtest.
            product_id: Product ID to backtest.
            start_date: Start date of data range.
            end_date: End date of data range.
            config: Backtest configuration.

        Returns:
            BacktestResponse with all results.

        Raises:
            ValueError: If insufficient data for requested splits or config
                violates settings constraints.
        """
        # Validate config against settings constraints
        self._validate_config(config)

        start_time = time.perf_counter()
        backtest_id = uuid.uuid4().hex[:16]

        logger.info(
            "backtesting.run_started",
            backtest_id=backtest_id,
            store_id=store_id,
            product_id=product_id,
            start_date=str(start_date),
            end_date=str(end_date),
            config_hash=config.config_hash(),
            model_type=config.model_config_main.model_type,
            strategy=config.split_config.strategy,
            n_splits=config.split_config.n_splits,
        )

        # Load series data
        series_data = await self._load_series_data(
            db=db,
            store_id=store_id,
            product_id=product_id,
            start_date=start_date,
            end_date=end_date,
        )

        if series_data.n_observations == 0:
            raise ValueError(
                f"No data found for store={store_id}, product={product_id} "
                f"between {start_date} and {end_date}"
            )

        # Create splitter and validate
        splitter = TimeSeriesSplitter(config.split_config)

        # Run main model backtest
        main_results = self._run_model_backtest(
            series_data=series_data,
            splitter=splitter,
            model_config=config.model_config_main,
            store_fold_details=config.store_fold_details,
        )

        # Run baseline comparisons if requested
        baseline_results: list[ModelBacktestResult] | None = None
        comparison_summary: dict[str, dict[str, float]] | None = None

        if config.include_baselines:
            baseline_results = self._run_baseline_comparisons(
                series_data=series_data,
                splitter=splitter,
                store_fold_details=config.store_fold_details,
            )
            comparison_summary = self._generate_comparison_summary(
                main_results=main_results,
                baseline_results=baseline_results,
            )

        # Validate no leakage
        leakage_check_passed = splitter.validate_no_leakage(
            dates=series_data.dates,
            y=series_data.values,
        )

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "backtesting.run_completed",
            backtest_id=backtest_id,
            store_id=store_id,
            product_id=product_id,
            n_folds=len(main_results.fold_results),
            main_model_mae=main_results.aggregated_metrics.get("mae"),
            leakage_check_passed=leakage_check_passed,
            duration_ms=duration_ms,
        )

        return BacktestResponse(
            backtest_id=backtest_id,
            store_id=store_id,
            product_id=product_id,
            config_hash=config.config_hash(),
            split_config=config.split_config,
            main_model_results=main_results,
            baseline_results=baseline_results,
            comparison_summary=comparison_summary,
            duration_ms=duration_ms,
            leakage_check_passed=leakage_check_passed,
        )

    def _run_model_backtest(
        self,
        series_data: SeriesData,
        splitter: TimeSeriesSplitter,
        model_config: ModelConfig,
        store_fold_details: bool,
    ) -> ModelBacktestResult:
        """Run backtest for a single model configuration.

        Args:
            series_data: Loaded time series data.
            splitter: Time series splitter.
            model_config: Model configuration.
            store_fold_details: Whether to store per-fold details.

        Returns:
            ModelBacktestResult with all fold results.
        """
        fold_results: list[FoldResult] = []
        fold_metrics: list[dict[str, float]] = []

        for split in splitter.split(series_data.dates, series_data.values):
            # Extract train and test data
            y_train = series_data.values[split.train_indices]
            y_test = series_data.values[split.test_indices]

            # Create and fit model
            model = model_factory(model_config, random_state=self.settings.forecast_random_seed)
            model.fit(y_train)

            # Generate predictions
            horizon = len(split.test_indices)
            predictions = model.predict(horizon)

            # Calculate metrics
            metrics = self.metrics_calculator.calculate_all(
                actuals=y_test,
                predictions=predictions,
            )
            fold_metrics.append(metrics)

            # Create fold result
            split_boundary = SplitBoundary(
                fold_index=split.fold_index,
                train_start=split.train_dates[0],
                train_end=split.train_dates[-1],
                test_start=split.test_dates[0],
                test_end=split.test_dates[-1],
                train_size=len(split.train_indices),
                test_size=len(split.test_indices),
            )

            if store_fold_details:
                fold_result = FoldResult(
                    fold_index=split.fold_index,
                    split=split_boundary,
                    dates=split.test_dates,
                    actuals=[float(v) for v in y_test],
                    predictions=[float(v) for v in predictions],
                    metrics=metrics,
                )
            else:
                # Store minimal fold result without detailed arrays
                fold_result = FoldResult(
                    fold_index=split.fold_index,
                    split=split_boundary,
                    dates=[],
                    actuals=[],
                    predictions=[],
                    metrics=metrics,
                )

            fold_results.append(fold_result)

        # Aggregate metrics
        aggregated_metrics, metric_std = self.metrics_calculator.aggregate_fold_metrics(
            fold_metrics
        )

        return ModelBacktestResult(
            model_type=model_config.model_type,
            config_hash=model_config.config_hash(),
            fold_results=fold_results,
            aggregated_metrics=aggregated_metrics,
            metric_std=metric_std,
        )

    def _run_baseline_comparisons(
        self,
        series_data: SeriesData,
        splitter: TimeSeriesSplitter,
        store_fold_details: bool,
    ) -> list[ModelBacktestResult]:
        """Run backtests for baseline models.

        Args:
            series_data: Loaded time series data.
            splitter: Time series splitter.
            store_fold_details: Whether to store per-fold details.

        Returns:
            List of ModelBacktestResult for each baseline.
        """
        baselines: list[ModelConfig] = [
            NaiveModelConfig(),
            SeasonalNaiveModelConfig(season_length=7),
        ]

        results: list[ModelBacktestResult] = []

        for baseline_config in baselines:
            try:
                result = self._run_model_backtest(
                    series_data=series_data,
                    splitter=splitter,
                    model_config=baseline_config,
                    store_fold_details=store_fold_details,
                )
                results.append(result)
            except ValueError as e:
                # Log warning but continue with other baselines
                logger.warning(
                    "backtesting.baseline_failed",
                    model_type=baseline_config.model_type,
                    error=str(e),
                )

        return results

    # Metrics where the sign matters and we should compare absolute values
    # for percentage improvement calculations
    SIGNED_METRICS: frozenset[str] = frozenset({"bias"})

    def _generate_comparison_summary(
        self,
        main_results: ModelBacktestResult,
        baseline_results: list[ModelBacktestResult],
    ) -> dict[str, dict[str, float]]:
        """Generate summary comparing main model to baselines.

        Args:
            main_results: Results for the main model.
            baseline_results: Results for baseline models.

        Returns:
            Dictionary with comparison metrics.
            Keys are metric names, values are dicts with:
            - main: Main model value (original signed value)
            - naive: Naive baseline value (original signed value, if available)
            - seasonal_naive: Seasonal naive value (original signed value, if available)
            - vs_naive_pct: Percentage improvement over naive
            - vs_seasonal_pct: Percentage improvement over seasonal

        Note:
            For signed metrics (e.g., bias), percentage improvements are computed
            using absolute values since a smaller absolute value is better
            regardless of sign.
        """
        summary: dict[str, dict[str, float]] = {}

        # Get baseline values by type
        baseline_by_type: dict[str, dict[str, float]] = {}
        for result in baseline_results:
            baseline_by_type[result.model_type] = result.aggregated_metrics

        # Compare each metric
        for metric_name, main_value in main_results.aggregated_metrics.items():
            comparison: dict[str, float] = {"main": main_value}

            # Determine if this is a signed metric
            is_signed = metric_name in self.SIGNED_METRICS

            # Add baseline values and compute improvements
            if "naive" in baseline_by_type:
                naive_value = baseline_by_type["naive"].get(metric_name, np.nan)
                comparison["naive"] = naive_value

                if not np.isnan(naive_value):
                    if is_signed:
                        # For signed metrics, compare absolute values
                        abs_main = abs(main_value)
                        abs_naive = abs(naive_value)
                        if abs_naive != 0:
                            # Improvement = (abs_baseline - abs_main) / abs_baseline * 100
                            comparison["vs_naive_pct"] = ((abs_naive - abs_main) / abs_naive) * 100
                    elif naive_value != 0:
                        # For unsigned metrics, use original formula
                        comparison["vs_naive_pct"] = (
                            (naive_value - main_value) / naive_value
                        ) * 100

            if "seasonal_naive" in baseline_by_type:
                seasonal_value = baseline_by_type["seasonal_naive"].get(metric_name, np.nan)
                comparison["seasonal_naive"] = seasonal_value

                if not np.isnan(seasonal_value):
                    if is_signed:
                        # For signed metrics, compare absolute values
                        abs_main = abs(main_value)
                        abs_seasonal = abs(seasonal_value)
                        if abs_seasonal != 0:
                            comparison["vs_seasonal_pct"] = (
                                (abs_seasonal - abs_main) / abs_seasonal
                            ) * 100
                    elif seasonal_value != 0:
                        # For unsigned metrics, use original formula
                        comparison["vs_seasonal_pct"] = (
                            (seasonal_value - main_value) / seasonal_value
                        ) * 100

            summary[metric_name] = comparison

        return summary

    async def _load_series_data(
        self,
        db: AsyncSession,
        store_id: int,
        product_id: int,
        start_date: date_type,
        end_date: date_type,
    ) -> SeriesData:
        """Load time series data from database.

        Args:
            db: Database session.
            store_id: Store ID.
            product_id: Product ID.
            start_date: Start date (inclusive).
            end_date: End date (inclusive).

        Returns:
            SeriesData container with loaded data.
        """
        stmt = (
            select(
                SalesDaily.date,
                SalesDaily.quantity,
            )
            .where(
                (SalesDaily.store_id == store_id)
                & (SalesDaily.product_id == product_id)
                & (SalesDaily.date >= start_date)
                & (SalesDaily.date <= end_date)
            )
            .order_by(SalesDaily.date)
        )

        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            return SeriesData(
                dates=[],
                values=np.array([], dtype=np.float64),
                store_id=store_id,
                product_id=product_id,
            )

        dates = [row.date for row in rows]
        values = np.array([float(row.quantity) for row in rows], dtype=np.float64)

        return SeriesData(
            dates=dates,
            values=values,
            store_id=store_id,
            product_id=product_id,
        )
