"""Fact table generators with time-series patterns."""

from __future__ import annotations

import math
import random
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from app.shared.seeder.config import (
        ChangepointConfig,
        ChannelConfig,
        HolidayConfig,
        MultiSeasonalityConfig,
        RetailPatternConfig,
        SparsityConfig,
        SubstitutionConfig,
        TimeSeriesConfig,
    )
    from app.shared.seeder.generators.lifecycle import LifecycleGenerator


_VALID_CHANNELS = frozenset({"in_store", "online", "click_collect", "wholesale"})
"""Mirrors the SQL CHECK on ``sales_daily.channel`` (see PRP-12 §schema)."""


PriceLookup = dict[tuple[int, int | None], list[tuple[date, date | None, Decimal]]]
"""Price windows indexed by ``(product_id, store_id)``.

``store_id=None`` keys hold chain-wide windows; each value is a list of
``(valid_from, valid_to, price)`` tuples sorted by ``valid_from`` ascending
(``valid_to=None`` means open-ended).
"""


def build_price_lookup(
    price_records: list[dict[str, date | int | Decimal | None]],
) -> PriceLookup:
    """Index price-history records by ``(product_id, store_id)`` scope.

    Pure and rng-free — the seeder's byte-stability contract forbids any
    rng draw here. Accepts the row shape both :class:`PriceHistoryGenerator`
    and the Phase 2 ``MarkdownGenerator`` emit. Within a scope, windows are
    sorted by ``valid_from`` ascending (stable, so a markdown appended after
    the base window it overlaps wins on a ``valid_from`` tie).

    Args:
        price_records: Price-history row dicts carrying ``product_id``,
            ``store_id``, ``price``, ``valid_from``, ``valid_to``.

    Returns:
        The :data:`PriceLookup` mapping :func:`resolve_price` consumes.
    """
    lookup: PriceLookup = {}
    for record in price_records:
        product_id = cast("int", record["product_id"])
        store_id = cast("int | None", record["store_id"])
        price = cast("Decimal", record["price"])
        valid_from = cast("date", record["valid_from"])
        valid_to = cast("date | None", record["valid_to"])
        lookup.setdefault((product_id, store_id), []).append((valid_from, valid_to, price))
    for windows in lookup.values():
        windows.sort(key=lambda window: window[0])
    return lookup


def resolve_price(
    lookup: PriceLookup,
    product_id: int,
    store_id: int,
    day: date,
    base_price: Decimal,
) -> Decimal:
    """Resolve the active price for ``(product_id, store_id)`` on ``day``.

    Precedence (deterministic): a store-specific window beats a chain-wide
    one; within a scope the latest ``valid_from`` covering ``day`` wins
    (markdowns fire later than the base window they cut). ``valid_to=None``
    is open-ended. A day no window covers falls back to ``base_price``.

    Args:
        lookup: The index built by :func:`build_price_lookup`.
        product_id: Product the sales row belongs to.
        store_id: Store the sales row belongs to.
        day: The sales date to resolve.
        base_price: Fallback when no window covers ``day``.

    Returns:
        The active price as a :class:`~decimal.Decimal`.
    """
    for scope in ((product_id, store_id), (product_id, None)):
        windows = lookup.get(scope)
        if not windows:
            continue
        # Sorted by valid_from ASC at build time; scan from the latest so the
        # most recent window covering ``day`` wins (markdown overlaps cut the
        # base window they were appended after).
        for valid_from, valid_to, price in reversed(windows):
            if valid_from <= day and (valid_to is None or day <= valid_to):
                return price
    return base_price


class SalesDailyGenerator:
    """Generator for daily sales fact data with realistic time-series patterns.

    Phase 1 extensions (``multi_seasonality``, ``changepoints``,
    ``substitution``, ``exogenous_weather``) and Phase 2 extension
    (``lifecycle``) are all opt-in. When every opt-in input is None /
    disabled, the generator's output is byte-identical to its
    pre-Phase-1 behavior.
    """

    def __init__(
        self,
        rng: random.Random,
        time_series_config: TimeSeriesConfig,
        retail_config: RetailPatternConfig,
        sparsity_config: SparsityConfig,
        holidays: list[HolidayConfig],
        multi_seasonality: MultiSeasonalityConfig | None = None,
        changepoints: ChangepointConfig | None = None,
        substitution: SubstitutionConfig | None = None,
        exogenous_weather: dict[tuple[int, date], float] | None = None,
        weather_temperature_sensitivity: float = 0.0,
        weather_climatology_mean_c: float = 15.0,
        lifecycle: LifecycleGenerator | None = None,
        channels: ChannelConfig | None = None,
    ) -> None:
        """Initialize the sales generator.

        Args:
            rng: Random number generator for reproducibility.
            time_series_config: Time-series pattern configuration.
            retail_config: Retail-specific pattern configuration.
            sparsity_config: Data sparsity configuration.
            holidays: List of holiday configurations with multipliers.
            multi_seasonality: Optional yearly seasonality configuration.
                When None or amplitude=0, no yearly multiplier is applied.
            changepoints: Optional list of demand changepoints. When None or
                empty, no changepoint multiplier is applied.
            substitution: Optional substitution configuration. When None or
                disabled, no substitution lift is applied.
            exogenous_weather: Optional lookup ``{(store_id, date): temp_c}``.
                Each entry shifts demand by
                ``weather_temperature_sensitivity * (temp_c - climatology_mean_c)``
                fraction (i.e. linear, centered on the climatology mean).
                When None, no weather effect.
            weather_temperature_sensitivity: Demand delta per °C above the
                climatology mean (used only when ``exogenous_weather`` is set).
            weather_climatology_mean_c: Reference temperature for the linear
                weather term.
            lifecycle: Optional Phase 2 ``LifecycleGenerator``. When set
                and ``lifecycle.enabled``, the per-(product, date) demand
                multiplier from intro/growth/maturity/decline/discontinued
                curves is applied. Also supersedes the pre-Phase-2
                ``retail_config.new_product_ramp_days`` linear ramp —
                that ramp is suppressed when ``lifecycle.enabled`` so
                effects do not stack.
            channels: Optional Phase 2 ``ChannelConfig``. When set and
                ``enable_multichannel``, each emitted row's ``channel``
                column is drawn from ``channel_mix``. During promos the
                effective mix shifts per
                ``online_substitution_to_instore`` and online rows pick
                up ``online_promo_uplift``. Consumes one rng draw per
                emitted row when enabled; zero draws when disabled.
        """
        self.rng = rng
        self.ts_config = time_series_config
        self.retail_config = retail_config
        self.sparsity_config = sparsity_config
        self.holiday_map = {h.date: h.multiplier for h in holidays}
        self.multi_seasonality = multi_seasonality
        self.changepoints = changepoints
        self.substitution = substitution
        self.exogenous_weather = exogenous_weather
        self.weather_sensitivity = weather_temperature_sensitivity
        self.weather_climatology_mean_c = weather_climatology_mean_c
        self.lifecycle = lifecycle
        self.channels = channels

        # Pre-compute substitution group memberships for O(1) lookup.
        self._substitution_groups_by_product: dict[int, list[list[int]]] = {}
        if self.substitution is not None and self.substitution.enable:
            for group in self.substitution.substitute_groups:
                for product_id in group:
                    self._substitution_groups_by_product.setdefault(product_id, []).append(group)

    def _yearly_seasonality_multiplier(self, current_date: date) -> float:
        """Return the yearly seasonality multiplier for ``current_date``.

        Returns 1.0 when multi-seasonality is unset or amplitude is 0 — that
        preserves the pre-Phase-1 output byte-for-byte.
        """
        if (
            self.multi_seasonality is None
            or self.multi_seasonality.yearly_seasonality_amplitude == 0.0
        ):
            return 1.0
        day_of_year = current_date.timetuple().tm_yday
        offset = self.multi_seasonality.yearly_phase_offset_days
        phase = 2.0 * math.pi * (day_of_year + offset) / 365.0
        return 1.0 + self.multi_seasonality.yearly_seasonality_amplitude * math.sin(phase)

    def _changepoint_multiplier(self, current_date: date) -> float:
        """Aggregate multiplier from all changepoints active on ``current_date``.

        Each changepoint contributes ``(multiplier - 1) * exp(-Δ/decay)`` if
        ``current_date >= changepoint.date`` and 0 otherwise. The total
        multiplier is ``1 + Σ contributions``.

        Returns 1.0 when there are no changepoints — preserving byte-identical
        output for callers that don't opt in.
        """
        if self.changepoints is None or not self.changepoints.changepoints:
            return 1.0
        contribution = 0.0
        for cp in self.changepoints.changepoints:
            delta_days = (current_date - cp.date).days
            if delta_days < 0:
                continue
            if cp.decay_days <= 0:
                # Pure impulse on the changepoint date only.
                if delta_days == 0:
                    contribution += cp.demand_multiplier - 1.0
                continue
            decay = math.exp(-delta_days / cp.decay_days)
            contribution += (cp.demand_multiplier - 1.0) * decay
        return 1.0 + contribution

    def _weather_multiplier(self, current_date: date, store_id: int) -> float:
        """Linear weather effect centered on the climatology mean.

        Returns 1.0 when no weather data is configured.
        """
        if self.exogenous_weather is None or self.weather_sensitivity == 0.0:
            return 1.0
        temp_c = self.exogenous_weather.get((store_id, current_date))
        if temp_c is None:
            return 1.0
        return 1.0 + self.weather_sensitivity * (temp_c - self.weather_climatology_mean_c)

    # ---------------------------------------------------------------- #
    # Phase 2 channel helpers
    # ---------------------------------------------------------------- #

    def _validate_channels(self) -> None:
        """Validate ``ChannelConfig`` at the start of ``generate()``.

        No-op when channels is unset or disabled — keeps the
        regression invariant intact (no extra work when off).
        """
        if self.channels is None or not self.channels.enable_multichannel:
            return
        cfg = self.channels
        if not cfg.channel_mix:
            raise ValueError("ChannelConfig.channel_mix must be non-empty when enabled")
        invalid = set(cfg.channel_mix.keys()) - _VALID_CHANNELS
        if invalid:
            raise ValueError(
                f"ChannelConfig.channel_mix contains invalid channels {sorted(invalid)}; "
                f"allow-list is {sorted(_VALID_CHANNELS)}"
            )
        for name, weight in cfg.channel_mix.items():
            if weight < 0:
                raise ValueError(f"ChannelConfig.channel_mix['{name}']={weight} must be >= 0")
        if sum(cfg.channel_mix.values()) <= 0:
            raise ValueError("ChannelConfig.channel_mix must have at least one positive weight")
        if cfg.online_promo_uplift < 0:
            raise ValueError(
                f"ChannelConfig.online_promo_uplift={cfg.online_promo_uplift} must be >= 0"
            )
        if not 0.0 <= cfg.online_substitution_to_instore <= 1.0:
            raise ValueError(
                "ChannelConfig.online_substitution_to_instore="
                f"{cfg.online_substitution_to_instore} must be in [0, 1]"
            )

    def _effective_channel_mix(self, is_promotion: bool) -> dict[str, float]:
        """Build the effective channel mix for a single row.

        Applies ``online_substitution_to_instore`` as a weight shift
        from ``in_store`` to ``online`` when a promo is active. Returns
        the pristine mix otherwise.
        """
        if self.channels is None:
            return {}
        mix = dict(self.channels.channel_mix)
        if not is_promotion:
            return mix
        if "online" not in mix or "in_store" not in mix:
            return mix
        sub = self.channels.online_substitution_to_instore
        if sub <= 0:
            return mix
        shift = mix["online"] * sub
        mix["online"] += shift
        mix["in_store"] = max(0.0, mix["in_store"] - shift)
        return mix

    def _maybe_apply_channel(
        self,
        quantity: int,
        is_promotion: bool,
    ) -> tuple[int, str | None]:
        """Choose a channel and apply per-channel uplift.

        Returns ``(unchanged_quantity, None)`` when the channel feature
        is disabled — caller emits no ``channel`` key and the DB
        ``server_default='in_store'`` applies, preserving the
        byte-identical regression invariant.

        When enabled, draws a channel from the effective mix and
        multiplies ``quantity`` by ``online_promo_uplift`` for online
        rows on promo dates. Consumes exactly one rng draw per call.
        """
        if self.channels is None or not self.channels.enable_multichannel:
            return quantity, None
        mix = self._effective_channel_mix(is_promotion)
        if not mix or sum(mix.values()) <= 0:
            return quantity, None
        names = list(mix.keys())
        weights = list(mix.values())
        chosen = self.rng.choices(names, weights=weights, k=1)[0]
        if chosen == "online" and is_promotion:
            quantity = max(0, round(quantity * self.channels.online_promo_uplift))
        return quantity, chosen

    def _substitution_multiplier(
        self,
        product_id: int,
        stockouts_today: set[int],
    ) -> float:
        """Lift demand for ``product_id`` when stocked-out group-mates exist.

        ``stockouts_today`` is the set of product IDs stocked out on the
        current date at the same store. For each substitution group the
        product belongs to, we count how many other members are stocked out
        and distribute ``substitution_lift_on_stockout`` across the surviving
        in-stock members.

        Returns 1.0 when substitution is disabled or no group-mate is out.
        """
        if (
            self.substitution is None
            or not self.substitution.enable
            or self.substitution.substitution_lift_on_stockout == 0.0
        ):
            return 1.0
        groups = self._substitution_groups_by_product.get(product_id)
        if not groups:
            return 1.0
        if product_id in stockouts_today:
            return 1.0  # A stocked-out product can't pick up lift.

        contribution = 0.0
        for group in groups:
            out_members = sum(
                1 for member in group if member != product_id and member in stockouts_today
            )
            survivors = sum(
                1 for member in group if member != product_id and member not in stockouts_today
            )
            if out_members == 0 or survivors == 0:
                # Either no group-mate is out, or we'd divide by zero (e.g.
                # everyone but this product is out — in that case give all
                # the lift to this product).
                if out_members > 0 and survivors == 0:
                    contribution += self.substitution.substitution_lift_on_stockout * out_members
                continue
            # Each out member's lift is split among (survivors + 1) including
            # this product, so this product captures one share per out member.
            contribution += (
                self.substitution.substitution_lift_on_stockout * out_members / (survivors + 1)
            )
        return 1.0 + contribution

    def _compute_demand(
        self,
        current_date: date,
        base_date: date,
        base_price: Decimal,
        current_price: Decimal | None,
        is_promotion: bool,
        is_stockout: bool,
        product_launch_date: date | None,
        store_id: int | None = None,
        product_id: int | None = None,
        stockouts_today_for_store: set[int] | None = None,
        product_discontinue_date: date | None = None,
    ) -> int:
        """Compute demand for a single observation.

        Args:
            current_date: Date of the observation.
            base_date: Start date for trend calculation.
            base_price: Product base price.
            current_price: Current price (if different from base).
            is_promotion: Whether there's an active promotion.
            is_stockout: Whether there's a stockout.
            product_launch_date: Optional launch date for new product ramp.
            store_id: Store ID (used only by Phase 1 weather + substitution
                effects). Required when those features are enabled.
            product_id: Product ID (used only by Phase 1 substitution).
                Required when substitution is enabled.
            stockouts_today_for_store: Set of product IDs stocked out at
                ``store_id`` on ``current_date``. Used only by substitution.

        Returns:
            Computed demand quantity (non-negative integer).
        """
        if is_stockout and self.retail_config.stockout_behavior == "zero":
            return 0

        # Start with base demand
        demand = float(self.ts_config.base_demand)

        # Apply trend
        days_elapsed = (current_date - base_date).days
        if self.ts_config.trend == "linear":
            demand *= 1 + (self.ts_config.trend_slope * days_elapsed)
        elif self.ts_config.trend == "exponential":
            demand *= math.exp(self.ts_config.trend_slope * days_elapsed)

        # Apply weekly seasonality (0=Monday, 6=Sunday)
        day_of_week = current_date.weekday()
        if day_of_week < len(self.ts_config.weekly_seasonality):
            demand *= self.ts_config.weekly_seasonality[day_of_week]

        # Apply monthly seasonality
        if current_date.month in self.ts_config.monthly_seasonality:
            demand *= self.ts_config.monthly_seasonality[current_date.month]

        # Apply holiday multiplier
        if current_date in self.holiday_map:
            demand *= self.holiday_map[current_date]

        # Apply promotion lift
        if is_promotion:
            demand *= self.retail_config.promotion_lift

        # Apply price elasticity
        if current_price is not None and base_price > 0:
            price_change_pct = float((current_price - base_price) / base_price)
            demand *= 1 + (self.retail_config.price_elasticity * price_change_pct)

        # Apply legacy new-product ramp (pre-Phase-2). Suppressed when a
        # Phase 2 ``LifecycleGenerator`` is enabled — the lifecycle
        # multiplier already encodes a richer launch curve and stacking
        # both would double the launch suppression.
        legacy_ramp_on = self.lifecycle is None or not self.lifecycle.enabled
        if product_launch_date is not None and legacy_ramp_on:
            days_since_launch = (current_date - product_launch_date).days
            ramp_days = self.retail_config.new_product_ramp_days
            if ramp_days > 0 and days_since_launch < ramp_days:
                ramp_factor = days_since_launch / ramp_days
                demand *= ramp_factor
            # If ramp_days == 0, skip ramp calculation (demand unchanged)

        # Phase 1 multipliers (each returns 1.0 when its feature is off).
        demand *= self._yearly_seasonality_multiplier(current_date)
        demand *= self._changepoint_multiplier(current_date)
        if store_id is not None:
            demand *= self._weather_multiplier(current_date, store_id)
        if product_id is not None and stockouts_today_for_store is not None:
            demand *= self._substitution_multiplier(product_id, stockouts_today_for_store)

        # Phase 2 lifecycle multiplier. Gated on ``lifecycle.enabled`` so
        # the disabled path is byte-identical with pre-Phase-2 callers.
        if self.lifecycle is not None and self.lifecycle.enabled:
            demand *= self.lifecycle.multiplier_for(
                current_date, product_launch_date, product_discontinue_date
            )

        # Apply noise
        if self.ts_config.noise_sigma > 0:
            noise = self.rng.gauss(0, self.ts_config.noise_sigma)
            demand *= 1 + noise

        # Apply anomaly
        if self.rng.random() < self.ts_config.anomaly_probability:
            if self.rng.random() < 0.5:
                demand *= self.ts_config.anomaly_magnitude  # Spike
            else:
                demand /= self.ts_config.anomaly_magnitude  # Dip

        # Ensure non-negative integer
        return max(0, round(demand))

    def generate(
        self,
        store_ids: list[int],
        product_data: list[tuple[int, Decimal]],  # (product_id, base_price)
        dates: list[date],
        promotions: dict[tuple[int, int], set[date]],  # (store_id, product_id) -> promo dates
        stockouts: dict[tuple[int, int], set[date]],  # (store_id, product_id) -> stockout dates
        product_lifecycle_data: dict[int, tuple[date | None, date | None]] | None = None,
        *,
        price_lookup: PriceLookup | None = None,
    ) -> list[dict[str, date | int | Decimal]]:
        """Generate sales daily records.

        Args:
            store_ids: List of store IDs.
            product_data: List of (product_id, base_price) tuples.
            dates: List of dates in the range.
            promotions: Mapping of (store_id, product_id) to promotion dates.
            stockouts: Mapping of (store_id, product_id) to stockout dates.
            product_lifecycle_data: Optional Phase 2 mapping
                ``product_id -> (launch_date, discontinue_date)``. Only
                consulted when a ``LifecycleGenerator`` was passed to
                :meth:`__init__`. Missing entries fall back to
                ``(None, None)`` so the lifecycle multiplier evaluates to
                1.0 for that product.
            price_lookup: Optional :data:`PriceLookup` built from the
                generated price-history records (issue #237). When supplied,
                each row's ``unit_price`` is the day's resolved price and
                demand responds via ``retail_config.price_elasticity``.
                When ``None`` (the default) the legacy path is byte-identical:
                ``unit_price = base_price`` and no elasticity effect.

        Returns:
            List of sales dictionaries ready for database insertion.
        """
        self._validate_channels()
        sales: list[dict[str, date | int | Decimal]] = []
        base_date = dates[0] if dates else date(2024, 1, 1)

        # Determine active store/product combinations
        total_combinations = len(store_ids) * len(product_data)
        inactive_count = int(total_combinations * self.sparsity_config.missing_combinations_pct)

        # Create set of inactive combinations
        all_combinations = [
            (store_id, product_id) for store_id in store_ids for product_id, _ in product_data
        ]
        self.rng.shuffle(all_combinations)
        inactive_combinations = set(all_combinations[:inactive_count])

        # Generate random gaps for each active series
        gap_dates: dict[tuple[int, int], set[date]] = {}
        for store_id in store_ids:
            for product_id, _ in product_data:
                key = (store_id, product_id)
                if key in inactive_combinations:
                    continue

                gaps: set[date] = set()
                for _ in range(self.sparsity_config.random_gaps_per_series):
                    if len(dates) < 2:
                        continue
                    gap_start_idx = self.rng.randint(0, len(dates) - 2)
                    gap_length = self.rng.randint(
                        self.sparsity_config.gap_min_days,
                        self.sparsity_config.gap_max_days,
                    )
                    for i in range(gap_length):
                        if gap_start_idx + i < len(dates):
                            gaps.add(dates[gap_start_idx + i])
                gap_dates[key] = gaps

        # Phase 1: per-(store, date) lookup of stocked-out product IDs for
        # substitution. Only build it when substitution is enabled — keeps
        # the disabled-path byte-identical with pre-Phase-1.
        stockouts_by_store_date: dict[tuple[int, date], set[int]] = {}
        if self.substitution is not None and self.substitution.enable:
            for (s_id, p_id), out_dates in stockouts.items():
                for d in out_dates:
                    stockouts_by_store_date.setdefault((s_id, d), set()).add(p_id)

        # Generate sales for each active combination and date
        for store_id in store_ids:
            for product_id, base_price in product_data:
                key = (store_id, product_id)

                # Skip inactive combinations
                if key in inactive_combinations:
                    continue

                promo_dates = promotions.get(key, set())
                stockout_dates = stockouts.get(key, set())
                series_gaps = gap_dates.get(key, set())
                # Phase 2 lifecycle lookup — defaults keep the disabled
                # path byte-identical (legacy callers pass ``None`` for
                # ``product_lifecycle_data``, so this is always ``(None,
                # None)`` and the multiplier evaluates to 1.0).
                lifecycle_dates = (
                    product_lifecycle_data.get(product_id, (None, None))
                    if product_lifecycle_data is not None
                    else (None, None)
                )
                launch_date_for_product, discontinue_date_for_product = lifecycle_dates

                for current_date in dates:
                    # Skip gap dates
                    if current_date in series_gaps:
                        continue

                    is_promotion = current_date in promo_dates
                    is_stockout = current_date in stockout_dates

                    stockouts_today = stockouts_by_store_date.get((store_id, current_date))

                    # Resolved day price (issue #237): None on the legacy path
                    # so the elasticity term in _compute_demand stays dormant.
                    resolved_price = (
                        resolve_price(price_lookup, product_id, store_id, current_date, base_price)
                        if price_lookup is not None
                        else None
                    )

                    quantity = self._compute_demand(
                        current_date=current_date,
                        base_date=base_date,
                        base_price=base_price,
                        current_price=resolved_price,
                        is_promotion=is_promotion,
                        is_stockout=is_stockout,
                        product_launch_date=launch_date_for_product,
                        store_id=store_id,
                        product_id=product_id,
                        stockouts_today_for_store=stockouts_today,
                        product_discontinue_date=discontinue_date_for_product,
                    )

                    # Skip zero sales from stockouts to reduce data volume.
                    # Channel rng is drawn only for emitted rows so the
                    # channel stream is stable per emitted-row across runs.
                    if quantity == 0 and is_stockout:
                        continue

                    quantity, chosen_channel = self._maybe_apply_channel(quantity, is_promotion)

                    # Calculate total amount
                    unit_price = resolved_price if resolved_price is not None else base_price
                    total_amount = unit_price * quantity

                    row: dict[str, date | int | Decimal | str] = {
                        "date": current_date,
                        "store_id": store_id,
                        "product_id": product_id,
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "total_amount": total_amount,
                    }
                    if chosen_channel is not None:
                        row["channel"] = chosen_channel
                    sales.append(row)  # type: ignore[arg-type]

        return sales


class PriceHistoryGenerator:
    """Generator for price history fact data."""

    def __init__(
        self,
        rng: random.Random,
        price_change_probability: float = 0.1,
        max_price_change_pct: float = 0.2,
    ) -> None:
        """Initialize the price history generator.

        Args:
            rng: Random number generator for reproducibility.
            price_change_probability: Probability of price change per month.
            max_price_change_pct: Maximum price change percentage.
        """
        self.rng = rng
        self.price_change_probability = price_change_probability
        self.max_price_change_pct = max_price_change_pct

    def generate(
        self,
        product_data: list[tuple[int, Decimal]],  # (product_id, base_price)
        store_ids: list[int],
        start_date: date,
        end_date: date,
    ) -> list[dict[str, date | int | Decimal | None]]:
        """Generate price history records.

        Args:
            product_data: List of (product_id, base_price) tuples.
            store_ids: List of store IDs (chain-wide prices use store_id=None).
            start_date: Start of date range.
            end_date: End of date range.

        Returns:
            List of price history dictionaries.
        """
        records: list[dict[str, date | int | Decimal | None]] = []

        for product_id, base_price in product_data:
            # Most prices are chain-wide (store_id = None)
            store_id: int | None = None

            # Occasionally create store-specific prices
            if self.rng.random() < 0.1:
                store_id = self.rng.choice(store_ids)

            current_price = base_price
            current_valid_from = start_date

            # Generate price changes at random intervals
            current = start_date
            while current <= end_date:
                # Check for price change (monthly probability)
                if self.rng.random() < self.price_change_probability / 30:
                    valid_to = current - timedelta(days=1)
                    # Skip degenerate window when a change fires on start_date
                    # itself: valid_to would precede valid_from and violate
                    # ck_price_history_valid_dates.
                    if valid_to >= current_valid_from:
                        records.append(
                            {
                                "product_id": product_id,
                                "store_id": store_id,
                                "price": current_price,
                                "valid_from": current_valid_from,
                                "valid_to": valid_to,
                            }
                        )
                        change_pct = self.rng.uniform(
                            -self.max_price_change_pct, self.max_price_change_pct
                        )
                        current_price = (current_price * Decimal(str(1 + change_pct))).quantize(
                            Decimal("0.01")
                        )
                        current_valid_from = current

                current += timedelta(days=1)

            # Add final price record (valid_to = None means current)
            records.append(
                {
                    "product_id": product_id,
                    "store_id": store_id,
                    "price": current_price,
                    "valid_from": current_valid_from,
                    "valid_to": None,
                }
            )

        return records


class PromotionGenerator:
    """Generator for promotion fact data."""

    def __init__(
        self,
        rng: random.Random,
        promotion_probability: float = 0.1,
        min_duration_days: int = 3,
        max_duration_days: int = 14,
    ) -> None:
        """Initialize the promotion generator.

        Args:
            rng: Random number generator for reproducibility.
            promotion_probability: Probability of promotion per product per month.
            min_duration_days: Minimum promotion duration.
            max_duration_days: Maximum promotion duration.
        """
        self.rng = rng
        self.promotion_probability = promotion_probability
        self.min_duration_days = min_duration_days
        self.max_duration_days = max_duration_days

    def generate(
        self,
        product_ids: list[int],
        store_ids: list[int],
        start_date: date,
        end_date: date,
    ) -> tuple[
        list[dict[str, date | int | str | Decimal | None]],
        dict[tuple[int, int], set[date]],
    ]:
        """Generate promotion records and return promotion date mapping.

        Args:
            product_ids: List of product IDs.
            store_ids: List of store IDs.
            start_date: Start of date range.
            end_date: End of date range.

        Returns:
            Tuple of (promotion records, mapping of (store_id, product_id) to promo dates).
        """
        records: list[dict[str, date | int | str | Decimal | None]] = []
        promo_dates: dict[tuple[int, int], set[date]] = {}

        promo_names = [
            "Weekly Special",
            "Flash Sale",
            "BOGO Deal",
            "Clearance",
            "Holiday Promo",
            "Member Exclusive",
            "Buy More Save More",
            "Manager's Special",
        ]

        for product_id in product_ids:
            # Determine if chain-wide or store-specific
            is_chain_wide = self.rng.random() < 0.7
            affected_stores: list[int | None] = (
                [None] if is_chain_wide else [self.rng.choice(store_ids)]
            )

            # Generate promotions throughout the date range
            current = start_date
            while current <= end_date:
                # Check for promotion start (scaled to monthly probability)
                if self.rng.random() < self.promotion_probability / 30:
                    duration = self.rng.randint(self.min_duration_days, self.max_duration_days)
                    promo_end = min(current + timedelta(days=duration - 1), end_date)

                    # Generate discount
                    discount_type = self.rng.choice(["pct", "amount"])
                    discount_pct: Decimal | None = None
                    discount_amount: Decimal | None = None

                    if discount_type == "pct":
                        pct = self.rng.choice([0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50])
                        discount_pct = Decimal(str(pct))
                    else:
                        amount = self.rng.choice([1.00, 2.00, 3.00, 5.00])
                        discount_amount = Decimal(str(amount))

                    for store_id in affected_stores:
                        records.append(
                            {
                                "product_id": product_id,
                                "store_id": store_id,
                                "name": self.rng.choice(promo_names),
                                "discount_pct": discount_pct,
                                "discount_amount": discount_amount,
                                "start_date": current,
                                "end_date": promo_end,
                            }
                        )

                        # Track promotion dates for sales calculation
                        actual_stores = store_ids if store_id is None else [store_id]
                        for sid in actual_stores:
                            key = (sid, product_id)
                            if key not in promo_dates:
                                promo_dates[key] = set()

                            promo_current = current
                            while promo_current <= promo_end:
                                promo_dates[key].add(promo_current)
                                promo_current += timedelta(days=1)

                    # Skip past this promotion
                    current = promo_end + timedelta(days=1)
                else:
                    current += timedelta(days=1)

        return records, promo_dates


class InventorySnapshotGenerator:
    """Generator for daily inventory snapshot data."""

    def __init__(
        self,
        rng: random.Random,
        stockout_probability: float = 0.02,
        base_on_hand: int = 500,
        on_hand_variance: float = 0.3,
    ) -> None:
        """Initialize the inventory snapshot generator.

        Args:
            rng: Random number generator for reproducibility.
            stockout_probability: Daily probability of stockout.
            base_on_hand: Base inventory level.
            on_hand_variance: Variance in inventory levels.
        """
        self.rng = rng
        self.stockout_probability = stockout_probability
        self.base_on_hand = base_on_hand
        self.on_hand_variance = on_hand_variance

    def generate(
        self,
        store_ids: list[int],
        product_ids: list[int],
        dates: list[date],
    ) -> tuple[
        list[dict[str, date | int | bool]],
        dict[tuple[int, int], set[date]],
    ]:
        """Generate inventory snapshot records.

        Args:
            store_ids: List of store IDs.
            product_ids: List of product IDs.
            dates: List of dates.

        Returns:
            Tuple of (inventory records, mapping of (store_id, product_id) to stockout dates).
        """
        records: list[dict[str, date | int | bool]] = []
        stockout_dates: dict[tuple[int, int], set[date]] = {}

        for store_id in store_ids:
            for product_id in product_ids:
                key = (store_id, product_id)
                stockout_dates[key] = set()

                # Track inventory state
                on_hand = self.base_on_hand

                for current_date in dates:
                    # Check for stockout
                    is_stockout = self.rng.random() < self.stockout_probability

                    if is_stockout:
                        on_hand = 0
                        stockout_dates[key].add(current_date)
                    else:
                        # Random inventory fluctuation
                        variance = self.rng.gauss(0, self.on_hand_variance)
                        on_hand = max(
                            0,
                            round(self.base_on_hand * (1 + variance)),
                        )

                    # Generate on_order quantity (higher when inventory is low)
                    on_order = 0
                    if on_hand < self.base_on_hand * 0.3:
                        on_order = self.rng.randint(100, 500)

                    records.append(
                        {
                            "date": current_date,
                            "store_id": store_id,
                            "product_id": product_id,
                            "on_hand_qty": on_hand,
                            "on_order_qty": on_order,
                            "is_stockout": is_stockout,
                        }
                    )

        return records, stockout_dates
