"""Backtesting tools for agent interaction with the backtesting service.

Provides PydanticAI-compatible tool functions for:
- Running backtests with configurable parameters
- Comparing backtest results between models

CRITICAL: Respects time-based CV constraints and Settings limits.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.backtesting.schemas import (
    BacktestConfig,
    BacktestResponse,
    SplitConfig,
)
from app.features.backtesting.service import BacktestingService
from app.features.forecasting.schemas import (
    ModelConfig,
    MovingAverageModelConfig,
    NaiveModelConfig,
    SeasonalNaiveModelConfig,
)

logger = structlog.get_logger()


def _create_model_config(
    model_type: str,
    season_length: int | None = None,
) -> ModelConfig:
    """Create model configuration from type string.

    Args:
        model_type: Type of model ('naive', 'seasonal_naive', 'linear_regression').
        season_length: Season length for seasonal models (default 7 for weekly).

    Returns:
        Configured ModelConfig instance.

    Raises:
        ValueError: If model_type is not supported.
    """
    if model_type == "naive":
        return NaiveModelConfig()
    elif model_type == "seasonal_naive":
        return SeasonalNaiveModelConfig(season_length=season_length or 7)
    elif model_type == "moving_average":
        return MovingAverageModelConfig()
    else:
        raise ValueError(
            f"Unsupported model type: {model_type}. "
            f"Supported: naive, seasonal_naive, moving_average"
        )


async def run_backtest(
    db: AsyncSession,
    store_id: int,
    product_id: int,
    start_date: date,
    end_date: date,
    model_type: str = "naive",
    n_splits: int = 5,
    horizon: int = 7,
    strategy: Literal["expanding", "sliding"] = "expanding",
    min_train_size: int = 30,
    gap: int = 0,
    include_baselines: bool = True,
    store_fold_details: bool = False,
    season_length: int | None = None,
) -> dict[str, Any]:
    """Run a backtest to evaluate model performance with time-based CV.

    Use this tool to evaluate a model's forecasting performance using proper
    time-series cross-validation. Automatically compares against baseline models.

    CRITICAL: Uses time-based splits to prevent data leakage.

    Args:
        db: Database session (injected via agent context).
        store_id: Store ID to backtest.
        product_id: Product ID to backtest.
        start_date: Start date of data range (YYYY-MM-DD).
        end_date: End date of data range (YYYY-MM-DD).
        model_type: Model to test ('naive', 'seasonal_naive', 'moving_average').
        n_splits: Number of CV folds (default 5, max from settings).
        horizon: Forecast horizon in days (default 7).
        strategy: CV strategy - 'expanding' (growing train) or 'sliding' (fixed train).
        min_train_size: Minimum training observations (default 30).
        gap: Gap between train and test in days (default 0).
        include_baselines: Compare against naive and seasonal_naive (default True).
        store_fold_details: Store per-fold predictions (default False, saves memory).
        season_length: Season length for seasonal models (default 7 for weekly).

    Returns:
        BacktestResponse with aggregated metrics and comparison summary.

    Example:
        # Run 5-fold expanding window backtest
        result = await run_backtest(
            db,
            store_id=1,
            product_id=101,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            model_type='seasonal_naive',
            n_splits=5,
            horizon=14,
        )
    """
    logger.info(
        "agents.backtesting_tool.run_backtest_called",
        store_id=store_id,
        product_id=product_id,
        start_date=str(start_date),
        end_date=str(end_date),
        model_type=model_type,
        n_splits=n_splits,
        horizon=horizon,
        strategy=strategy,
    )

    # Create model configuration
    model_config = _create_model_config(model_type, season_length)

    # Create split configuration
    split_config = SplitConfig(
        strategy=strategy,
        n_splits=n_splits,
        horizon=horizon,
        min_train_size=min_train_size,
        gap=gap,
    )

    # Create backtest configuration
    backtest_config = BacktestConfig(
        model_config_main=model_config,
        split_config=split_config,
        include_baselines=include_baselines,
        store_fold_details=store_fold_details,
    )

    # Run backtest
    service = BacktestingService()
    result: BacktestResponse = await service.run_backtest(
        db=db,
        store_id=store_id,
        product_id=product_id,
        start_date=start_date,
        end_date=end_date,
        config=backtest_config,
    )

    logger.info(
        "agents.backtesting_tool.run_backtest_completed",
        backtest_id=result.backtest_id,
        store_id=store_id,
        product_id=product_id,
        main_mae=result.main_model_results.aggregated_metrics.get("mae"),
        leakage_check_passed=result.leakage_check_passed,
        duration_ms=result.duration_ms,
    )

    return result.model_dump()


def compare_backtest_results(
    result_a: dict[str, Any],
    result_b: dict[str, Any],
) -> dict[str, Any]:
    """Compare two backtest results to analyze model performance differences.

    Use this tool to compare backtest results from two different experiments.
    Helps identify which model configuration performs better.

    Args:
        result_a: First backtest result (from run_backtest).
        result_b: Second backtest result (from run_backtest).

    Returns:
        Comparison summary with metric differences and recommendations.

    Example:
        # Compare naive vs seasonal_naive backtests
        comparison = compare_backtest_results(naive_result, seasonal_result)
    """
    logger.info(
        "agents.backtesting_tool.compare_backtest_results_called",
        backtest_id_a=result_a.get("backtest_id"),
        backtest_id_b=result_b.get("backtest_id"),
    )

    # Extract main model results
    main_a = result_a.get("main_model_results", {})
    main_b = result_b.get("main_model_results", {})

    metrics_a = main_a.get("aggregated_metrics", {})
    metrics_b = main_b.get("aggregated_metrics", {})

    # Build comparison
    comparison: dict[str, Any] = {
        "model_a": {
            "backtest_id": result_a.get("backtest_id"),
            "model_type": main_a.get("model_type"),
            "config_hash": main_a.get("config_hash"),
            "metrics": metrics_a,
        },
        "model_b": {
            "backtest_id": result_b.get("backtest_id"),
            "model_type": main_b.get("model_type"),
            "config_hash": main_b.get("config_hash"),
            "metrics": metrics_b,
        },
        "metric_comparison": {},
        "recommendation": "",
    }

    # Compare each metric
    all_metrics = set(metrics_a.keys()) | set(metrics_b.keys())
    for metric_name in all_metrics:
        val_a = metrics_a.get(metric_name)
        val_b = metrics_b.get(metric_name)

        metric_comp: dict[str, Any] = {
            "model_a": val_a,
            "model_b": val_b,
        }

        if val_a is not None and val_b is not None:
            # Lower is better for most metrics
            diff = val_b - val_a
            metric_comp["difference"] = diff
            if abs(val_a) > 1e-10:
                metric_comp["percent_change"] = (diff / abs(val_a)) * 100
            metric_comp["better_model"] = "a" if val_a <= val_b else "b"

        comparison["metric_comparison"][metric_name] = metric_comp

    # Generate recommendation based on MAE (primary metric)
    mae_a = metrics_a.get("mae")
    mae_b = metrics_b.get("mae")
    if mae_a is not None and mae_b is not None:
        if mae_a < mae_b:
            pct_better = ((mae_b - mae_a) / mae_b) * 100
            comparison["recommendation"] = (
                f"Model A ({main_a.get('model_type')}) performs better with "
                f"{pct_better:.1f}% lower MAE ({mae_a:.2f} vs {mae_b:.2f})."
            )
        elif mae_b < mae_a:
            pct_better = ((mae_a - mae_b) / mae_a) * 100
            comparison["recommendation"] = (
                f"Model B ({main_b.get('model_type')}) performs better with "
                f"{pct_better:.1f}% lower MAE ({mae_b:.2f} vs {mae_a:.2f})."
            )
        else:
            comparison["recommendation"] = (
                f"Both models have identical MAE ({mae_a:.2f}). "
                f"Consider other metrics or simpler model."
            )

    return comparison
