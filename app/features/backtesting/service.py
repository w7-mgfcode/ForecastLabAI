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
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.backtesting.metrics import MetricsCalculator, compute_bucket_metrics
from app.features.backtesting.schemas import (
    BacktestConfig,
    BacktestResponse,
    FoldResult,
    ModelBacktestResult,
    SplitBoundary,
)
from app.features.backtesting.splitter import TimeSeriesSplit, TimeSeriesSplitter
from app.features.data_platform.models import Calendar, Product, Promotion, SalesDaily
from app.features.forecasting.models import model_factory
from app.features.forecasting.schemas import (
    ModelConfig,
    NaiveModelConfig,
    SeasonalNaiveModelConfig,
)
from app.shared.feature_frames import (
    HISTORY_TAIL_DAYS,
    build_future_feature_rows,
    build_historical_feature_rows,
)

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()

# Minimum observed train rows a feature-aware model needs per fold to resolve
# its lag features — mirrors ``forecasting.service._MIN_REGRESSION_TRAIN_ROWS``.
# A feature-aware backtest with a smaller ``min_train_size`` fails loud in
# ``_validate_config`` rather than producing all-NaN lag columns silently.
_MIN_FEATURE_AWARE_TRAIN_ROWS = 30


@dataclass
class ExogenousFrame:
    """Pre-loaded exogenous data for one series — resolved async, consumed sync.

    A feature-aware backtest needs price / promotion / holiday / launch-date
    data to build its per-fold feature matrices, but the fold loop is sync and
    DB-free by design. ``run_backtest`` resolves all of it once into this pure
    in-memory carrier; the fold builders read it without touching the database.

    Attributes:
        prices: Observed unit prices, aligned index-for-index with
            :attr:`SeriesData.dates`.
        baseline_price: Median positive price (``>0``); fallback ``1.0``.
        promo_dates: Days a promotion covered anywhere in the data window.
        holiday_dates: Calendar holiday days in the data window.
        launch_date: The product's launch date, or ``None``.
    """

    prices: list[float]
    baseline_price: float
    promo_dates: set[date_type]
    holiday_dates: set[date_type]
    launch_date: date_type | None


@dataclass
class SeriesData:
    """Container for loaded time series data.

    Attributes:
        dates: List of dates in chronological order.
        values: Target values as numpy array.
        store_id: Store ID.
        product_id: Product ID.
        exogenous: Pre-loaded exogenous data — present only for a feature-aware
            backtest; ``None`` for a target-only run.
        n_observations: Number of observations.
    """

    dates: list[date_type]
    values: np.ndarray[Any, np.dtype[np.floating[Any]]]
    store_id: int
    product_id: int
    exogenous: ExogenousFrame | None = None
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

        # Feature-aware models need enough train rows per fold to resolve their
        # lag features. Build a cheap probe (no fit) and branch on the
        # capability flag — never on a model_type string. Loud, not silent.
        probe = model_factory(
            config.model_config_main, random_state=self.settings.forecast_random_seed
        )
        if probe.requires_features and split_config.min_train_size < _MIN_FEATURE_AWARE_TRAIN_ROWS:
            raise ValueError(
                f"A feature-aware model ({config.model_config_main.model_type}) needs "
                f"min_train_size of at least {_MIN_FEATURE_AWARE_TRAIN_ROWS} to resolve its "
                f"lag features per fold; got {split_config.min_train_size}."
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

        # Feature-aware models consume a per-fold feature matrix. Branch on the
        # capability flag (not a model_type string) and resolve the exogenous
        # data once, here in the async entry point — the fold loop stays sync
        # and DB-free. Target-only models skip this entirely.
        probe = model_factory(
            config.model_config_main, random_state=self.settings.forecast_random_seed
        )
        if probe.requires_features:
            series_data.exogenous = await self._load_exogenous_frame(
                db=db,
                store_id=store_id,
                product_id=product_id,
                dates=series_data.dates,
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

        Branches on the model's ``requires_features`` capability flag (never a
        ``model_type`` string). A target-only model takes the unchanged
        target-only path; a feature-aware model builds the full historical
        feature matrix once (a local — never instance state) and runs each fold
        through :meth:`_run_feature_aware_fold` with a leakage-safe per-fold
        ``X_train`` slice and a rebuilt ``X_future``. The method signature is
        unchanged — ``gap`` is read from ``splitter.config.gap``. Sync and
        DB-free: all exogenous I/O happened in :meth:`run_backtest`.

        Args:
            series_data: Loaded time series data (carries ``exogenous`` for a
                feature-aware run).
            splitter: Time series splitter.
            model_config: Model configuration.
            store_fold_details: Whether to store per-fold details.

        Returns:
            ModelBacktestResult with all fold results; ``feature_aware`` and
            ``exogenous_policy`` are set for a feature-aware model.

        Raises:
            ValueError: If a feature-aware model has no loaded ``ExogenousFrame``.
        """
        fold_results: list[FoldResult] = []
        fold_metrics: list[dict[str, float]] = []
        fold_bucket_metrics: list[dict[str, dict[str, float]]] = []

        # Probe the capability flag, then build the historical matrix once for
        # the whole run (feature-aware path only) — sliced, never rebuilt, for
        # each fold's X_train.
        probe = model_factory(model_config, random_state=self.settings.forecast_random_seed)
        feature_aware: bool = probe.requires_features
        historical_matrix: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None
        if feature_aware:
            historical_matrix = self._build_historical_matrix(series_data)

        for split in splitter.split(series_data.dates, series_data.values):
            # Extract train and test data
            y_test = series_data.values[split.test_indices]
            horizon = len(split.test_indices)

            if historical_matrix is not None:
                # Feature-aware path — per-fold leakage-safe X_train / X_future.
                predictions = self._run_feature_aware_fold(
                    series_data=series_data,
                    split=split,
                    model_config=model_config,
                    historical_matrix=historical_matrix,
                    gap=splitter.config.gap,
                )
            else:
                # Target-only path — unchanged.
                y_train = series_data.values[split.train_indices]
                model = model_factory(model_config, random_state=self.settings.forecast_random_seed)
                model.fit(y_train)
                predictions = model.predict(horizon)

            # Calculate metrics
            metrics = self.metrics_calculator.calculate_all(
                actuals=y_test,
                predictions=predictions,
            )
            fold_metrics.append(metrics)

            # PRP-36 — per-horizon-bucket metrics. ``test_dates[0]`` anchors
            # horizon day 1 so ``(d - test_dates[0]).days + 1`` lands in
            # bucket ``h_1_7`` for the first 7 days and walks outward.
            horizon_offsets = [(d - split.test_dates[0]).days + 1 for d in split.test_dates]
            bucket_metrics = compute_bucket_metrics(
                actuals=y_test,
                predictions=predictions,
                horizon_offsets=horizon_offsets,
            )
            fold_bucket_metrics.append(bucket_metrics)

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
                    horizon_bucket_metrics=bucket_metrics,
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
                    horizon_bucket_metrics=bucket_metrics,
                )

            fold_results.append(fold_result)

            logger.debug(
                "backtest.fold_complete",
                fold_index=split.fold_index,
                bucket_count=len(bucket_metrics),
                model_type=model_config.model_type,
            )

        # Aggregate metrics
        aggregated_metrics, metric_std = self.metrics_calculator.aggregate_fold_metrics(
            fold_metrics
        )
        bucketed_aggregated = self.metrics_calculator.aggregate_bucket_metrics(fold_bucket_metrics)

        return ModelBacktestResult(
            model_type=model_config.model_type,
            config_hash=model_config.config_hash(),
            fold_results=fold_results,
            aggregated_metrics=aggregated_metrics,
            metric_std=metric_std,
            bucketed_aggregated_metrics=bucketed_aggregated if bucketed_aggregated else None,
            feature_aware=feature_aware,
            exogenous_policy="observed" if feature_aware else None,
        )

    def _build_historical_matrix(
        self, series_data: SeriesData
    ) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
        """Build the full-series historical feature matrix for a backtest.

        Built once per :meth:`_run_model_backtest` call as a local — never
        instance state. Each row is leakage-safe *as a training row*: its lag
        columns read only strictly-earlier observed targets. Per-fold
        ``X_train`` is a positional slice of this matrix; ``X_future`` is NEVER
        sliced from it (that would leak an adjacent test-day target).

        Args:
            series_data: Loaded time series data — must carry ``exogenous``.

        Returns:
            Row-major feature matrix aligned with ``series_data.dates``.

        Raises:
            ValueError: If ``series_data.exogenous`` is ``None`` — the
                genuinely-unsupported path for a feature-aware backtest.
        """
        exo = series_data.exogenous
        if exo is None:
            raise ValueError(
                "feature-aware backtest requires a loaded ExogenousFrame on series_data; "
                "run_backtest must resolve exogenous data before the fold loop"
            )
        rows = build_historical_feature_rows(
            dates=series_data.dates,
            quantities=[float(v) for v in series_data.values],
            prices=exo.prices,
            baseline_price=exo.baseline_price,
            promo_dates=exo.promo_dates,
            holiday_dates=exo.holiday_dates,
            launch_date=exo.launch_date,
        )
        return np.array(rows, dtype=np.float64)

    def _run_feature_aware_fold(
        self,
        *,
        series_data: SeriesData,
        split: TimeSeriesSplit,
        model_config: ModelConfig,
        historical_matrix: np.ndarray[Any, np.dtype[np.floating[Any]]],
        gap: int,
    ) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
        """Fit + predict one fold of a feature-aware backtest — pure, sync.

        ``X_train`` is a positional slice of the full historical matrix (built
        once, leakage-safe by position). ``X_future`` is rebuilt here per fold
        via :func:`build_future_feature_rows`: its ``history_tail`` ends at the
        fold origin ``T`` (the last train day, gap days excluded), so a lag
        cell whose source day falls in the test window is ``NaN``.

        Args:
            series_data: Loaded time series data — carries ``exogenous``.
            split: The fold's train/test split.
            model_config: Model configuration (feature-aware).
            historical_matrix: The full-series historical feature matrix.
            gap: Gap days between train end and test start.

        Returns:
            Per-day predictions for the fold's test window.

        Raises:
            ValueError: If ``series_data.exogenous`` is ``None``.
        """
        exo = series_data.exogenous
        if exo is None:  # defensive — the caller guarantees this is non-None
            raise ValueError("feature-aware backtest requires a loaded ExogenousFrame")

        # X_train — slice the historical matrix (leakage-safe by position).
        x_train = historical_matrix[split.train_indices]
        y_train = series_data.values[split.train_indices]

        # X_future — rebuilt per fold. history_tail ends at T = last train day
        # and EXCLUDES the gap days (data "not yet available" at forecast time).
        train_end_idx = int(split.train_indices[-1]) + 1
        history_tail = [float(v) for v in series_data.values[:train_end_idx][-HISTORY_TAIL_DAYS:]]
        test_indices = [int(i) for i in split.test_indices]
        test_prices = [exo.prices[i] for i in test_indices]
        test_promo_dates = {
            series_data.dates[i] for i in test_indices if series_data.dates[i] in exo.promo_dates
        }
        test_holiday_dates = {d for d in split.test_dates if d in exo.holiday_dates}
        x_future = np.array(
            build_future_feature_rows(
                test_dates=split.test_dates,
                history_tail=history_tail,
                gap=gap,
                test_prices=test_prices,
                baseline_price=exo.baseline_price,
                test_promo_dates=test_promo_dates,
                test_holiday_dates=test_holiday_dates,
                launch_date=exo.launch_date,
            ),
            dtype=np.float64,
        )

        model = model_factory(model_config, random_state=self.settings.forecast_random_seed)
        model.fit(y_train, x_train)
        return model.predict(len(test_indices), x_future)

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

    async def _load_exogenous_frame(
        self,
        db: AsyncSession,
        store_id: int,
        product_id: int,
        dates: list[date_type],
    ) -> ExogenousFrame:
        """Load exogenous data for a feature-aware backtest — async, once.

        Mirrors ``ForecastingService._build_regression_features``: resolves the
        recorded unit price per date, the promotion-covered days, the calendar
        holidays, and the product launch date into a pure :class:`ExogenousFrame`
        the sync fold loop consumes. The only ``y``-free reads — never a target.

        Args:
            db: Database session.
            store_id: Store ID.
            product_id: Product ID.
            dates: The series dates (from :meth:`_load_series_data`) the prices
                must align with index-for-index.

        Returns:
            The resolved :class:`ExogenousFrame`.
        """
        start_date = dates[0]
        end_date = dates[-1]

        # Recorded unit price per date — aligned with the series dates. Every
        # series date came from the same SalesDaily window, so each resolves.
        price_rows = (
            await db.execute(
                select(SalesDaily.date, SalesDaily.unit_price).where(
                    (SalesDaily.store_id == store_id)
                    & (SalesDaily.product_id == product_id)
                    & (SalesDaily.date >= start_date)
                    & (SalesDaily.date <= end_date)
                )
            )
        ).all()
        price_by_date = {row.date: float(row.unit_price) for row in price_rows}
        prices = [price_by_date.get(day, 0.0) for day in dates]

        # Baseline price = median of the positive prices, so price_factor is
        # ~1.0 on a typical day and < 1.0 on a markdown/promo day.
        positive_prices = sorted(price for price in prices if price > 0.0)
        baseline_price = positive_prices[len(positive_prices) // 2] if positive_prices else 1.0

        holiday_dates: set[date_type] = set(
            (
                await db.execute(
                    select(Calendar.date).where(
                        Calendar.date >= start_date,
                        Calendar.date <= end_date,
                        Calendar.is_holiday.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )

        # Promotion-active days: store-specific OR chain-wide rows overlapping
        # the data window, expanded to the set of dates they cover.
        promo_rows = (
            await db.execute(
                select(Promotion.start_date, Promotion.end_date).where(
                    Promotion.product_id == product_id,
                    (Promotion.store_id == store_id) | (Promotion.store_id.is_(None)),
                    Promotion.start_date <= end_date,
                    Promotion.end_date >= start_date,
                )
            )
        ).all()
        promo_dates: set[date_type] = set()
        for promo in promo_rows:
            day = max(promo.start_date, start_date)
            last = min(promo.end_date, end_date)
            while day <= last:
                promo_dates.add(day)
                day += timedelta(days=1)

        launch_date: date_type | None = await db.scalar(
            select(Product.launch_date).where(Product.id == product_id)
        )

        logger.info(
            "backtesting.exogenous_frame_loaded",
            store_id=store_id,
            product_id=product_id,
            n_dates=len(dates),
            n_holidays=len(holiday_dates),
            n_promo_days=len(promo_dates),
        )

        return ExogenousFrame(
            prices=prices,
            baseline_price=baseline_price,
            promo_dates=promo_dates,
            holiday_dates=holiday_dates,
            launch_date=launch_date,
        )
