"""Feature engineering service for time-safe feature computation.

CRITICAL: All feature computation respects cutoff_date to prevent leakage.
- Lag features use shift(lag) with positive lag values only
- Rolling features use shift(1) BEFORE rolling to exclude current observation
- Calendar features are derived from date column (no leakage risk)
- Exogenous features are lagged appropriately
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.features.data_platform.models import Calendar, SalesDaily
from app.features.featuresets.schemas import FeatureSetConfig

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


@dataclass
class FeatureComputationResult:
    """Result of feature computation.

    Attributes:
        df: DataFrame with computed features.
        feature_columns: List of computed feature column names.
        config_hash: Hash of the configuration used.
        stats: Statistics about the computation.
    """

    df: pd.DataFrame
    feature_columns: list[str]
    config_hash: str
    stats: dict[str, Any] = field(default_factory=lambda: {})


class FeatureEngineeringService:
    """Time-safe feature engineering service.

    CRITICAL: All feature computation respects cutoff_date to prevent leakage.
    Features are computed using only data available at prediction time.

    Example:
        >>> config = FeatureSetConfig(
        ...     name="test",
        ...     lag_config=LagConfig(lags=(1, 7)),
        ... )
        >>> service = FeatureEngineeringService(config)
        >>> result = service.compute_features(df, cutoff_date=date(2024, 1, 31))
    """

    def __init__(self, config: FeatureSetConfig) -> None:
        """Initialize service with configuration.

        Args:
            config: Feature set configuration.
        """
        self.config = config
        self.entity_cols = list(config.entity_columns)
        self.date_col = config.date_column
        self.target_col = config.target_column

    def compute_features(
        self,
        df: pd.DataFrame,
        cutoff_date: date_type | None = None,
    ) -> FeatureComputationResult:
        """Compute all configured features.

        CRITICAL: Filters data to cutoff_date BEFORE any feature computation
        to ensure no future data leakage.

        Args:
            df: Input dataframe with entity columns, date, and target.
            cutoff_date: Maximum date to include (CRITICAL for time-safety).

        Returns:
            FeatureComputationResult with computed features.
        """
        logger.info(
            "featureops.compute_started",
            config_hash=self.config.config_hash(),
            row_count=len(df),
            cutoff_date=str(cutoff_date) if cutoff_date else None,
        )

        input_rows = len(df)
        result = df.copy()

        # CRITICAL: Sort by entity + date for correct lag/rolling computation
        result = result.sort_values([*self.entity_cols, self.date_col])

        # CRITICAL: Filter to cutoff BEFORE any feature computation
        if cutoff_date:
            date_series = pd.to_datetime(result[self.date_col]).dt.date
            result = result[date_series <= cutoff_date]

        feature_columns: list[str] = []

        # 1. Apply imputation FIRST (fills gaps before lag/rolling)
        if self.config.imputation_config:
            result = self._apply_imputation(result)

        # 2. Lag features
        if self.config.lag_config:
            result, cols = self._compute_lag_features(result)
            feature_columns.extend(cols)

        # 3. Rolling features (uses shifted data)
        if self.config.rolling_config:
            result, cols = self._compute_rolling_features(result)
            feature_columns.extend(cols)

        # 4. Calendar features (no leakage risk)
        if self.config.calendar_config:
            result, cols = self._compute_calendar_features(result)
            feature_columns.extend(cols)

        # 5. Exogenous features
        if self.config.exogenous_config:
            result, cols = self._compute_exogenous_features(result)
            feature_columns.extend(cols)

        # Compute stats
        null_counts: dict[str, int] = {}
        if feature_columns:
            null_counts = {
                str(k): int(v) for k, v in result[feature_columns].isnull().sum().items()
            }

        stats: dict[str, Any] = {
            "input_rows": input_rows,
            "output_rows": len(result),
            "feature_count": len(feature_columns),
            "null_counts": null_counts,
        }

        logger.info(
            "featureops.compute_completed",
            config_hash=self.config.config_hash(),
            feature_count=len(feature_columns),
            output_rows=len(result),
        )

        return FeatureComputationResult(
            df=result,
            feature_columns=feature_columns,
            config_hash=self.config.config_hash(),
            stats=stats,
        )

    def _compute_lag_features(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        """Compute lag features with proper grouping.

        CRITICAL: shift(lag) uses PAST data only (positive lag = look back).
        Groups by entity columns to prevent cross-series leakage.

        Args:
            df: Input dataframe sorted by entity + date.

        Returns:
            Tuple of (dataframe with lag features, list of new column names).
        """
        config = self.config.lag_config
        if config is None:
            raise RuntimeError("_compute_lag_features called without lag_config")

        result = df.copy()
        columns: list[str] = []

        for lag in config.lags:
            col_name = f"lag_{lag}"
            # CRITICAL: Group by entity to prevent cross-series leakage
            result[col_name] = df.groupby(self.entity_cols, observed=True)[
                config.target_column
            ].shift(lag)  # Positive shift = look back in time
            if config.fill_value is not None:
                result[col_name] = result[col_name].fillna(config.fill_value)
            columns.append(col_name)

        return result, columns

    def _compute_rolling_features(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        """Compute rolling window features.

        CRITICAL: shift(1) BEFORE rolling to exclude current observation.
        Without shift(1), rolling(7).mean() at row i uses data from [i-6, i].
        With shift(1), it uses data from [i-7, i-1] — truly past data only.

        Args:
            df: Input dataframe sorted by entity + date.

        Returns:
            Tuple of (dataframe with rolling features, list of new column names).
        """
        config = self.config.rolling_config
        if config is None:
            raise RuntimeError("_compute_rolling_features called without rolling_config")

        result = df.copy()
        columns: list[str] = []

        for window in config.windows:
            min_per = config.min_periods if config.min_periods else window

            for agg in config.aggregations:
                col_name = f"rolling_{agg}_{window}"

                # CRITICAL: shift(1) prevents using current row in rolling calculation
                def compute_rolling(
                    x: pd.Series[float],
                    w: int = window,
                    m: int = min_per,
                    a: str = agg,
                ) -> pd.Series[float]:
                    return x.shift(1).rolling(window=w, min_periods=m).agg(a)

                result[col_name] = df.groupby(self.entity_cols, observed=True)[
                    config.target_column
                ].transform(compute_rolling)
                columns.append(col_name)

        return result, columns

    def _compute_calendar_features(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        """Compute calendar-based features.

        Calendar features are derived from the date column itself,
        so there's no risk of future leakage.

        Args:
            df: Input dataframe with date column.

        Returns:
            Tuple of (dataframe with calendar features, list of new column names).
        """
        config = self.config.calendar_config
        if config is None:
            raise RuntimeError("_compute_calendar_features called without calendar_config")

        result = df.copy()
        columns: list[str] = []
        dates = pd.to_datetime(result[self.date_col])

        if config.include_day_of_week:
            dow = dates.dt.dayofweek  # 0=Monday, 6=Sunday
            if config.use_cyclical_encoding:
                result["dow_sin"] = np.sin(2 * np.pi * dow / 7)
                result["dow_cos"] = np.cos(2 * np.pi * dow / 7)
                columns.extend(["dow_sin", "dow_cos"])
            else:
                result["day_of_week"] = dow
                columns.append("day_of_week")

        if config.include_month:
            month = dates.dt.month
            if config.use_cyclical_encoding:
                result["month_sin"] = np.sin(2 * np.pi * month / 12)
                result["month_cos"] = np.cos(2 * np.pi * month / 12)
                columns.extend(["month_sin", "month_cos"])
            else:
                result["month"] = month
                columns.append("month")

        if config.include_quarter:
            result["quarter"] = dates.dt.quarter
            columns.append("quarter")

        if config.include_year:
            result["year"] = dates.dt.year
            columns.append("year")

        if config.include_is_weekend:
            result["is_weekend"] = dates.dt.dayofweek.isin([5, 6]).astype(int)
            columns.append("is_weekend")

        if config.include_is_month_end:
            result["is_month_end"] = dates.dt.is_month_end.astype(int)
            columns.append("is_month_end")

        # is_holiday would require calendar table lookup
        # Handled separately if data is joined from Calendar table

        return result, columns

    def _apply_imputation(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply configured imputation strategies.

        CRITICAL: Group-aware imputation to prevent cross-series leakage.

        **Leakage Warnings:**
        - "bfill" (backward fill) uses FUTURE values to fill gaps — avoid in production
        - "mean" uses entire series mean including FUTURE values — avoid in production
        - Use "expanding_mean" for time-safe mean imputation (uses only past data)
        - "ffill" (forward fill) and "zero" are safe

        Args:
            df: Input dataframe.

        Returns:
            Dataframe with imputed values.
        """
        config = self.config.imputation_config
        if config is None:
            raise RuntimeError("_apply_imputation called without imputation_config")

        result = df.copy()

        for col, strategy in config.strategies.items():
            if col not in result.columns:
                continue

            if strategy == "zero":
                result[col] = result[col].fillna(0)
            elif strategy == "ffill":
                # CRITICAL: Group-aware forward fill (time-safe)
                result[col] = result.groupby(self.entity_cols, observed=True)[col].ffill()
            elif strategy == "bfill":
                # WARNING: bfill uses future data — use only for debugging/testing
                logger.warning(
                    "featureops.imputation_leakage_risk",
                    strategy="bfill",
                    column=col,
                    message="bfill uses future values to fill gaps; avoid in production",
                )
                result[col] = result.groupby(self.entity_cols, observed=True)[col].bfill()
            elif strategy == "mean":
                # WARNING: mean uses entire series including future — use only for debugging
                logger.warning(
                    "featureops.imputation_leakage_risk",
                    strategy="mean",
                    column=col,
                    message="mean uses entire series including future values; use 'expanding_mean' instead",
                )
                result[col] = result.groupby(self.entity_cols, observed=True)[col].transform(
                    lambda x: x.fillna(x.mean())
                )
            elif strategy == "expanding_mean":
                # TIME-SAFE: Uses only past values via expanding window
                result[col] = result.groupby(self.entity_cols, observed=True)[col].transform(
                    lambda x: x.fillna(x.expanding(min_periods=1).mean().shift(1))
                )
            elif strategy == "drop":
                result = result.dropna(subset=[col])

        return result

    def _compute_exogenous_features(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        """Compute exogenous features (price, promo, inventory).

        CRITICAL: All exogenous features are lagged to prevent leakage.

        Args:
            df: Input dataframe with exogenous columns.

        Returns:
            Tuple of (dataframe with exogenous features, list of new column names).
        """
        config = self.config.exogenous_config
        if config is None:
            raise RuntimeError("_compute_exogenous_features called without exogenous_config")

        result = df.copy()
        columns: list[str] = []

        # Price features (if price column exists)
        if config.include_price and "unit_price" in df.columns:
            for lag in config.price_lags:
                col_name = f"price_lag_{lag}"
                result[col_name] = df.groupby(self.entity_cols, observed=True)["unit_price"].shift(
                    lag
                )
                columns.append(col_name)

            if config.include_price_change:
                # CRITICAL: shift(1) before pct_change to prevent using current price
                # This computes: (price[t-1] - price[t-8]) / price[t-8]
                # Without shift(1), it would use current price at t, causing leakage
                result["price_pct_change_7d"] = df.groupby(self.entity_cols, observed=True)[
                    "unit_price"
                ].transform(lambda x: x.shift(1).pct_change(periods=7))
                columns.append("price_pct_change_7d")

        # Stockout flag (if inventory column exists)
        if config.include_stockout_flag and "is_stockout" in df.columns:
            # Lagged stockout flag (yesterday's stockout)
            result["stockout_lag_1"] = df.groupby(self.entity_cols, observed=True)[
                "is_stockout"
            ].shift(1)
            columns.append("stockout_lag_1")

        return result, columns


class FeatureDataLoader:
    """Async data loader for feature computation.

    Loads data from database for feature computation.
    """

    async def load_sales_data(
        self,
        db: AsyncSession,
        store_id: int,
        product_id: int,
        start_date: date_type,
        end_date: date_type,
    ) -> pd.DataFrame:
        """Load sales data for a single series.

        Args:
            db: Async database session.
            store_id: Store ID.
            product_id: Product ID.
            start_date: Start date (inclusive).
            end_date: End date (inclusive).

        Returns:
            DataFrame with sales data.
        """
        stmt = (
            select(
                SalesDaily.date,
                SalesDaily.store_id,
                SalesDaily.product_id,
                SalesDaily.quantity,
                SalesDaily.unit_price,
                SalesDaily.total_amount,
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
            return pd.DataFrame(
                columns=["date", "store_id", "product_id", "quantity", "unit_price", "total_amount"]
            )

        return pd.DataFrame(
            [
                {
                    "date": row.date,
                    "store_id": row.store_id,
                    "product_id": row.product_id,
                    "quantity": row.quantity,
                    "unit_price": float(row.unit_price),
                    "total_amount": float(row.total_amount),
                }
                for row in rows
            ]
        )

    async def load_calendar_data(
        self,
        db: AsyncSession,
        start_date: date_type,
        end_date: date_type,
    ) -> pd.DataFrame:
        """Load calendar data for date range.

        Args:
            db: Async database session.
            start_date: Start date (inclusive).
            end_date: End date (inclusive).

        Returns:
            DataFrame with calendar data.
        """
        stmt = (
            select(
                Calendar.date,
                Calendar.day_of_week,
                Calendar.month,
                Calendar.quarter,
                Calendar.year,
                Calendar.is_holiday,
                Calendar.holiday_name,
            )
            .where((Calendar.date >= start_date) & (Calendar.date <= end_date))
            .order_by(Calendar.date)
        )

        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            return pd.DataFrame(
                columns=[
                    "date",
                    "day_of_week",
                    "month",
                    "quarter",
                    "year",
                    "is_holiday",
                    "holiday_name",
                ]
            )

        return pd.DataFrame(
            [
                {
                    "date": row.date,
                    "day_of_week": row.day_of_week,
                    "month": row.month,
                    "quarter": row.quarter,
                    "year": row.year,
                    "is_holiday": row.is_holiday,
                    "holiday_name": row.holiday_name,
                }
                for row in rows
            ]
        )


async def compute_features_for_series(
    db: AsyncSession,
    store_id: int,
    product_id: int,
    cutoff_date: date_type,
    lookback_days: int,
    config: FeatureSetConfig,
) -> FeatureComputationResult:
    """Compute features for a single series.

    Convenience function that loads data and computes features.

    Args:
        db: Async database session.
        store_id: Store ID.
        product_id: Product ID.
        cutoff_date: Maximum date to include.
        lookback_days: Days of history to use.
        config: Feature set configuration.

    Returns:
        FeatureComputationResult with computed features.
    """
    loader = FeatureDataLoader()

    # Calculate start date
    start_date = cutoff_date - timedelta(days=lookback_days)

    # Load sales data
    df = await loader.load_sales_data(
        db=db,
        store_id=store_id,
        product_id=product_id,
        start_date=start_date,
        end_date=cutoff_date,
    )

    # Optionally load and merge calendar data
    if config.calendar_config and config.calendar_config.include_is_holiday:
        calendar_df = await loader.load_calendar_data(
            db=db,
            start_date=start_date,
            end_date=cutoff_date,
        )
        if not calendar_df.empty and not df.empty:
            df = df.merge(
                calendar_df[["date", "is_holiday"]],
                on="date",
                how="left",
            )

    # Compute features
    service = FeatureEngineeringService(config)
    return service.compute_features(df, cutoff_date=cutoff_date)
