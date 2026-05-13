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
from app.features.data_platform.models import Calendar, Product, SalesDaily
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

        # 6. Lifecycle features (PRP-3.1B — Phase 2)
        if self.config.lifecycle_config:
            result, cols = self._compute_lifecycle_features(result)
            feature_columns.extend(cols)

        # 7. Promotion features (PRP-3.1D — Phase 2)
        if self.config.promotion_config:
            promotion_rows_df = getattr(self, "_promotion_rows_df", None)
            if promotion_rows_df is None:
                # PRP-3.1E wires the DB JOIN that sets this attribute.
                # In unit tests, the test sets it directly on the service.
                # An empty DataFrame is the safe no-op fallback.
                promotion_rows_df = pd.DataFrame(
                    columns=[
                        "product_id",
                        "store_id",
                        "kind",
                        "discount_pct",
                        "start_date",
                        "end_date",
                    ]
                )
            result, cols = self._compute_promotion_features(result, promotion_rows_df)
            feature_columns.extend(cols)

        # 8. Replenishment features (PRP-3.1C — Phase 2)
        if self.config.replenishment_config:
            events_df = getattr(self, "_replenishment_events_df", None)
            # PRP-3.1E wires the DB JOIN that sets this attribute via the
            # loader; tests set it via private-attr access. Mirrors the
            # PRP-3.1D promotion sidecar pattern (no public setter).
            result, cols = self._compute_replenishment_features(result, events_df=events_df)
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
            min_per = config.min_periods if config.min_periods is not None else window

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

    def _compute_lifecycle_features(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        """Compute product-lifecycle features from launch/discontinue dates.

        CRITICAL: This method assumes ``df`` has already been sorted by
        [*entity_cols, date_col] and cutoff-filtered upstream in
        :meth:`compute_features`. It does NOT re-sort or re-filter.

        The compute is two-step:
          1. Per-row date deltas: ``date - launch_date`` (int days, NaN-safe).
          2. Lagged by ``config.lag_days`` per ``(store_id, product_id)`` to
             ensure the value at row ``i`` reflects only data at row
             ``i - lag_days``.

        Source columns (must be joined upstream — typically by an extended
        :class:`FeatureDataLoader`; see PRP-3.1E):
          * ``launch_date`` — ``datetime.date | NaT`` per product
          * ``discontinue_date`` — ``datetime.date | NaT`` per product

        Defensive behavior: if BOTH source columns are absent (the legacy
        ``/featuresets/compute`` endpoint does not join product attrs), emit
        zero columns and a single info-level log line. This preserves the
        additive-contract invariant: callers who set ``lifecycle_config`` but
        don't join attrs see ``"lifecycle"`` in ``enabled_features`` but no
        new columns in ``feature_columns``. The end-to-end wiring lands in
        PRP-3.1E.

        Note on signed deltas: ``days_since_discontinue`` is signed (negative
        pre-retire, positive post-retire). LightGBM learns the sign — do NOT
        clip to non-negative.

        Args:
            df: Input dataframe (already sorted + cutoff-filtered).

        Returns:
            Tuple of (dataframe with lifecycle features, list of new column
            names).
        """
        config = self.config.lifecycle_config
        if config is None:
            raise RuntimeError("_compute_lifecycle_features called without lifecycle_config")

        result = df.copy()
        columns: list[str] = []
        lag = config.lag_days

        # Defensive: skip silently if product attrs were not joined upstream.
        # PRP-3.1E will extend FeatureDataLoader to join product.launch_date /
        # product.discontinue_date; until then, callers without an extended
        # loader see the "lifecycle" family token but zero new columns.
        if "launch_date" not in df.columns and "discontinue_date" not in df.columns:
            logger.info(
                "featureops.lifecycle_skipped_no_product_attrs",
                reason="launch_date / discontinue_date columns absent from input df",
                hint="loader must join product.launch_date / product.discontinue_date "
                "before calling compute_features (see PRP-3.1E)",
            )
            return result, columns

        date_series = pd.to_datetime(result[self.date_col])

        if config.include_days_since_launch and "launch_date" in df.columns:
            launch = pd.to_datetime(result["launch_date"])
            # Pre-shift delta: int days where both dates set, NaN otherwise.
            delta_launch: pd.Series[Any] = (date_series - launch).dt.days
            # Lag per (store_id, product_id) so row i reflects row i-lag's delta.
            col_name = f"days_since_launch_lag{lag}"
            result[col_name] = delta_launch.groupby(
                [result[c] for c in self.entity_cols], observed=True
            ).shift(lag)
            columns.append(col_name)

        if config.include_days_since_discontinue and "discontinue_date" in df.columns:
            discontinue = pd.to_datetime(result["discontinue_date"])
            # Signed delta: negative pre-retire, positive post-retire, NaN if NULL.
            delta_discontinue: pd.Series[Any] = (date_series - discontinue).dt.days
            col_name = f"days_since_discontinue_lag{lag}"
            result[col_name] = delta_discontinue.groupby(
                [result[c] for c in self.entity_cols], observed=True
            ).shift(lag)
            columns.append(col_name)

        return result, columns

    def _compute_promotion_features(
        self,
        df: pd.DataFrame,
        promotion_rows_df: pd.DataFrame,
    ) -> tuple[pd.DataFrame, list[str]]:
        """Compute promotion-family features (active + intensity per kind).

        CRITICAL: Time-safe via ``groupby(entity_cols).shift(lag_days)`` on
        a daily-grain indicator. Per the time-safety contract, the active
        indicator at row D reads activity from D - lag_days. A promotion
        active on D itself must NOT appear in active_lag{N} at D.

        Date-range semantics: ``start_date <= D <= end_date`` (both inclusive).

        Chain-wide promotions: rows with ``store_id`` NaN/None apply to
        EVERY store of that product. Handled via a two-pass match (store-
        specific OR chain-wide), never via a NaN-key merge.

        Overlapping promotions on the same kind/day reduce via ``max`` over
        ``discount_pct`` for intensity (Decision §15-C); active stays 0/1.

        Args:
            df: Sales DataFrame, pre-sorted and cutoff-filtered (per
                compute_features pipeline).
            promotion_rows_df: Promotion rows. Columns:
                ``[product_id, store_id, kind, discount_pct, start_date, end_date]``.
                ``store_id`` may be NaN (chain-wide). ``discount_pct`` may
                be NaN (bogo / bundle kinds).

        Returns:
            Tuple of (DataFrame with new columns, list of new column names).
        """
        config = self.config.promotion_config
        if config is None:
            raise RuntimeError("_compute_promotion_features called without promotion_config")

        result = df.copy()
        columns: list[str] = []
        lag = config.lag_days

        # Defensive re-sort to match the caller invariant.
        result = result.sort_values([*self.entity_cols, self.date_col])
        dates = pd.to_datetime(result[self.date_col]).dt.date

        # Deterministic column ordering: sorted kinds, active before intensity.
        sorted_kinds: tuple[str, ...] = tuple(sorted(config.kinds_to_track))

        for kind in sorted_kinds:
            kind_rows = promotion_rows_df[promotion_rows_df["kind"] == kind]

            # Per-row daily indicators (D-day truth, BEFORE lag shift).
            active_today: pd.Series[Any] = pd.Series(0, index=result.index, dtype="int64")
            intensity_today: pd.Series[Any] = pd.Series(np.nan, index=result.index, dtype="float64")

            # Two-pass match: store-specific then chain-wide. Never merge on NaN keys.
            store_specific = kind_rows[kind_rows["store_id"].notna()]
            chain_wide = kind_rows[kind_rows["store_id"].isna()]

            for _, promo in store_specific.iterrows():
                mask = (
                    (result["store_id"] == promo["store_id"])
                    & (result["product_id"] == promo["product_id"])
                    & (dates >= promo["start_date"])
                    & (dates <= promo["end_date"])
                )
                active_today = active_today.where(~mask, 1)
                disc = promo["discount_pct"]
                if pd.notna(disc):
                    # Overlapping-on-same-kind reduction = max (Decision §15-C).
                    masked_disc = intensity_today.where(~mask, float(disc))
                    intensity_today = pd.concat([intensity_today, masked_disc], axis=1).max(axis=1)

            for _, promo in chain_wide.iterrows():
                mask = (
                    (result["product_id"] == promo["product_id"])
                    & (dates >= promo["start_date"])
                    & (dates <= promo["end_date"])
                )
                active_today = active_today.where(~mask, 1)
                disc = promo["discount_pct"]
                if pd.notna(disc):
                    masked_disc = intensity_today.where(~mask, float(disc))
                    intensity_today = pd.concat([intensity_today, masked_disc], axis=1).max(axis=1)

            # CRITICAL: groupby(entity_cols).shift(lag) — the leakage gate.
            # Feature at row D reads daily indicator at D - lag.
            if config.include_active:
                col = f"promo_{kind}_active_lag{lag}"
                shifted_active = (
                    result.assign(_a=active_today)
                    .groupby(self.entity_cols, observed=True)["_a"]
                    .shift(lag)
                )
                # Nullable Int64 preserves NaN at the start of each series
                # (mirrors the lag-feature idiom — Decision §15-D).
                result[col] = shifted_active.astype("Int64")
                columns.append(col)

            if config.include_intensity:
                col = f"promo_{kind}_intensity_lag{lag}"
                shifted_intensity = (
                    result.assign(_i=intensity_today)
                    .groupby(self.entity_cols, observed=True)["_i"]
                    .shift(lag)
                )
                result[col] = shifted_intensity.astype("float64")
                columns.append(col)

        return result, columns

    def _compute_replenishment_features(
        self,
        df: pd.DataFrame,
        events_df: pd.DataFrame | None = None,
    ) -> tuple[pd.DataFrame, list[str]]:
        """Compute replenishment-event features (PRP-3.1C).

        CRITICAL: All replenishment features are lagged to prevent leakage.
        The events DataFrame must be pre-filtered to event_date <= cutoff_date
        by the caller (the loader does this SQL-side; tests do it explicitly).

        Produced columns (when matching flags are set):
            * days_since_last_replenishment_lag{N}: float64 -- gap (days) from
              the current sales-row date to the most-recent prior event for
              the SAME (store_id, product_id). NaN when no prior event exists.
            * replenishment_count_w{W}_lag{N}: int64 -- number of events in
              the trailing W-day window, excluding the current day (via
              shift(1)). 0 for entity-windows with no events.

        Args:
            df: Sales-shape DataFrame sorted by entity_cols + date_col.
            events_df: ReplenishmentEvent rows with columns
                [store_id, product_id, event_date]. May include extra columns
                (lead_time_days, ordered_qty, received_qty) -- they are ignored.
                REQUIRED for this method; pass None and the method raises.

        Returns:
            Tuple of (df with new columns appended, list of new column names).

        Raises:
            RuntimeError: If replenishment_config is None, or events_df is None.
        """
        config = self.config.replenishment_config
        if config is None:
            raise RuntimeError(
                "_compute_replenishment_features called without replenishment_config"
            )
        if events_df is None:
            raise RuntimeError(
                "_compute_replenishment_features requires events_df "
                "(load via FeatureDataLoader.load_replenishment_events or "
                "inject in tests)"
            )

        result = df.copy()
        columns: list[str] = []

        # Internal helper column for date alignment (dropped before return).
        # Force ``datetime64[ns]`` on both sides so merge_asof sees matching
        # dtypes regardless of how the caller built the input frames
        # (``datetime.date`` columns from SQLAlchemy land as ``[s]``;
        # ``pd.date_range`` defaults to ``[ns]``).
        sales_dt_col = "_sales_dt_internal"
        result[sales_dt_col] = pd.to_datetime(result[self.date_col]).astype("datetime64[ns]")

        # Normalize events: select needed cols, coerce dtype, sort by date.
        # merge_asof requires the right-side key sorted.
        events = events_df.loc[:, ["store_id", "product_id", "event_date"]].copy()
        events["event_date"] = pd.to_datetime(events["event_date"]).astype("datetime64[ns]")
        events = events.sort_values(["event_date", "store_id", "product_id"]).reset_index(drop=True)

        # --- Feature 1: days_since_last_replenishment_lag{N} -----------------
        if config.include_days_since_last:
            # merge_asof requires the left side sorted by the on-key. Sort
            # result by sales_dt_col, run the asof, then restore canonical
            # (entity, date) order before shifting.
            sorted_result = result.sort_values(sales_dt_col).reset_index(drop=True)
            with_last = pd.merge_asof(
                sorted_result,
                events.rename(columns={"event_date": "_last_event_dt"}),
                left_on=sales_dt_col,
                right_on="_last_event_dt",
                by=["store_id", "product_id"],
                direction="backward",
                allow_exact_matches=True,
            )
            with_last = with_last.sort_values([*self.entity_cols, self.date_col]).reset_index(
                drop=True
            )

            # Days-since-last: (sales_date - last_event_date).dt.days; cast to
            # float64 so NaN survives (numpy int can't represent missing).
            days_since = (with_last[sales_dt_col] - with_last["_last_event_dt"]).dt.days.astype(
                "float64"
            )

            col_name = f"days_since_last_replenishment_lag{config.lag_days}"
            result[col_name] = (
                days_since.groupby(
                    [with_last[c] for c in self.entity_cols],
                    observed=True,
                )
                .shift(config.lag_days)
                .reset_index(drop=True)
            )
            columns.append(col_name)

        # --- Feature 2: replenishment_count_w{W}_lag{N} -----------------------
        if config.include_count_window:
            # Aggregate events to per-(entity, date) counts then left-merge
            # onto sales. Multiple events on the same date are summed.
            event_counts = (
                events.assign(_one=1)
                .groupby(["store_id", "product_id", "event_date"], observed=True)["_one"]
                .sum()
                .reset_index()
                .rename(
                    columns={"_one": "_event_count", "event_date": sales_dt_col},
                )
            )
            merged = result.merge(
                event_counts,
                on=["store_id", "product_id", sales_dt_col],
                how="left",
            )
            merged["_event_count"] = merged["_event_count"].fillna(0).astype("int64")

            # CRITICAL: shift(1).rolling(W).sum() per entity --
            # NEVER rolling(W).sum().shift(1).
            window = config.count_window_days

            def _shift_rolling_count(
                x: pd.Series[int],
                w: int = window,
            ) -> pd.Series[float]:
                return x.shift(1).rolling(window=w, min_periods=1).sum()

            rolling_counts = merged.groupby(self.entity_cols, observed=True)[
                "_event_count"
            ].transform(_shift_rolling_count)

            # For lag_days > 1, layer an extra shift on the already-shifted
            # rolling result. Preserves the canonical shift(1).rolling(W)
            # safety boundary (PRP-3.1C §15 Decision C).
            if config.lag_days > 1:
                rolling_counts = rolling_counts.groupby(
                    [merged[c] for c in self.entity_cols],
                    observed=True,
                ).shift(config.lag_days - 1)

            col_name = f"replenishment_count_w{window}_lag{config.lag_days}"
            result[col_name] = rolling_counts.fillna(0).astype("int64").reset_index(drop=True)
            columns.append(col_name)

        # Drop the internal helper column so the response shape stays clean.
        result = result.drop(columns=[sales_dt_col])

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

    async def load_replenishment_events(
        self,
        db: AsyncSession,
        store_ids: list[int],
        product_ids: list[int],
        cutoff_date: date_type,
    ) -> pd.DataFrame:
        """Load replenishment events for the given entities up to cutoff_date.

        CRITICAL: SQL-side filter ``date <= cutoff_date`` enforces time-safety
        BEFORE any pandas code sees the rows (PRP-3.1C decisions log §2).

        Args:
            db: Async database session.
            store_ids: Store IDs to include.
            product_ids: Product IDs to include.
            cutoff_date: Maximum event date (inclusive).

        Returns:
            DataFrame with columns
            ``[store_id, product_id, event_date, lead_time_days, ordered_qty,
            received_qty]``. The DB column ``date`` is renamed to ``event_date``
            for clarity at the compute boundary.
        """
        from app.features.data_platform.models import ReplenishmentEvent

        stmt = (
            select(
                ReplenishmentEvent.store_id,
                ReplenishmentEvent.product_id,
                ReplenishmentEvent.date,
                ReplenishmentEvent.lead_time_days,
                ReplenishmentEvent.ordered_qty,
                ReplenishmentEvent.received_qty,
            )
            .where(
                ReplenishmentEvent.store_id.in_(store_ids),
                ReplenishmentEvent.product_id.in_(product_ids),
                ReplenishmentEvent.date <= cutoff_date,
            )
            .order_by(
                ReplenishmentEvent.store_id,
                ReplenishmentEvent.product_id,
                ReplenishmentEvent.date,
            )
        )

        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            return pd.DataFrame(
                columns=[
                    "store_id",
                    "product_id",
                    "event_date",
                    "lead_time_days",
                    "ordered_qty",
                    "received_qty",
                ]
            )

        return pd.DataFrame(
            [
                {
                    "store_id": row.store_id,
                    "product_id": row.product_id,
                    "event_date": row.date,  # rename at the boundary
                    "lead_time_days": row.lead_time_days,
                    "ordered_qty": row.ordered_qty,
                    "received_qty": row.received_qty,
                }
                for row in rows
            ]
        )

    async def load_product_attrs(
        self,
        db: AsyncSession,
        product_ids: list[int],
    ) -> pd.DataFrame:
        """Load product lifecycle attributes for the given product IDs.

        Returns a per-product slice of dimension columns relevant to the
        lifecycle feature family. ``launch_date`` and ``discontinue_date``
        are timeless attributes of the product (NOT facts), so there's no
        cutoff filter -- the values are constant across time and the
        ``_compute_lifecycle_features`` method derives the per-row delta
        downstream.

        Args:
            db: Async database session.
            product_ids: Product IDs to include.

        Returns:
            DataFrame with columns ``[product_id, launch_date,
            discontinue_date]``. Empty DataFrame (with correct columns)
            when no matching products are found.
        """
        stmt = (
            select(
                Product.id,
                Product.launch_date,
                Product.discontinue_date,
            )
            .where(Product.id.in_(product_ids))
            .order_by(Product.id)
        )

        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            return pd.DataFrame(columns=["product_id", "launch_date", "discontinue_date"])

        return pd.DataFrame(
            [
                {
                    "product_id": row.id,
                    "launch_date": row.launch_date,
                    "discontinue_date": row.discontinue_date,
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

    # Optionally load product attrs and merge for lifecycle features
    # (#116). ``launch_date`` / ``discontinue_date`` are timeless product
    # attributes, so no cutoff filter is needed -- the merge attaches
    # the same per-product values to every sales row, and
    # ``_compute_lifecycle_features`` derives per-row deltas downstream.
    if config.lifecycle_config and not df.empty:
        product_attrs_df = await loader.load_product_attrs(
            db=db,
            product_ids=[product_id],
        )
        if not product_attrs_df.empty:
            df = df.merge(
                product_attrs_df[["product_id", "launch_date", "discontinue_date"]],
                on="product_id",
                how="left",
            )

    # Optionally load replenishment events (PRP-3.1C) before constructing
    # the service. SQL-side date filter enforces time-safety.
    events_df: pd.DataFrame | None = None
    if config.replenishment_config:
        events_df = await loader.load_replenishment_events(
            db=db,
            store_ids=[store_id],
            product_ids=[product_id],
            cutoff_date=cutoff_date,
        )

    # Compute features
    service = FeatureEngineeringService(config)
    if events_df is not None:
        # Sidecar attach via setattr — see PRP-3.1C §15 Decision A and the
        # matching ``_promotion_rows_df`` pattern in PRP-3.1D. setattr keeps
        # the attribute dynamic so mypy/pyright don't flag a private-member
        # access on a non-declared attribute.
        setattr(service, "_replenishment_events_df", events_df)  # noqa: B010
    return service.compute_features(df, cutoff_date=cutoff_date)
