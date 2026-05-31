"""Configuration dataclasses for the seeder module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Literal

DEFAULT_SEED_SPAN_DAYS = 365
"""Span of the default seeded window. Generated data ends *today* and runs
this many days backwards, so datasets, forecasts, and the demo showcase
always look current instead of being frozen in a hard-coded calendar year."""

DEMO_MINIMAL_SPAN_DAYS = 91
"""Span of the ``demo_minimal`` window (92 calendar days inclusive). Must stay
>= 72 so an expanding backtest with n_splits=3 + horizon=14 +
min_train_size=30 produces a non-NaN WAPE."""

SHOWCASE_RICH_SPAN_DAYS = 180
"""Span of the ``showcase_rich`` window (181 calendar days inclusive). Larger
than ``demo_minimal`` to power the V2 prophet_like training and feature-aware
backtest's full bucket coverage; must stay >= 72 so the expanding backtest
with n_splits=3 + horizon=14 + min_train_size=30 produces a non-NaN WAPE."""


def default_seed_end_date() -> date:
    """End of the default seeded window — anchored to the current (UTC) date."""
    return datetime.now(UTC).date()


def default_seed_start_date() -> date:
    """Start of the default seeded window — ``DEFAULT_SEED_SPAN_DAYS`` before today."""
    return datetime.now(UTC).date() - timedelta(days=DEFAULT_SEED_SPAN_DAYS)


class ScenarioPreset(str, Enum):
    """Pre-built scenario presets for common testing needs."""

    RETAIL_STANDARD = "retail_standard"
    HOLIDAY_RUSH = "holiday_rush"
    HIGH_VARIANCE = "high_variance"
    STOCKOUT_HEAVY = "stockout_heavy"
    NEW_LAUNCHES = "new_launches"
    SPARSE = "sparse"
    DEMO_MINIMAL = "demo_minimal"
    SHOWCASE_RICH = "showcase_rich"


@dataclass
class TimeSeriesConfig:
    """Configuration for realistic time-series generation.

    Attributes:
        base_demand: Base demand level before applying patterns.
        trend: Type of trend to apply (none, linear, exponential).
        trend_slope: Daily percentage change for trend (0.1 = 10% per period).
        weekly_seasonality: Multipliers for each day of week (Mon-Sun, index 0-6).
        monthly_seasonality: Multipliers by month number (1-12).
        noise_sigma: Standard deviation for Gaussian noise (as fraction of demand).
        anomaly_probability: Probability of random spike/dip per observation.
        anomaly_magnitude: Multiplier for anomaly magnitude (2.0 = double/half).
    """

    base_demand: int = 100
    trend: Literal["none", "linear", "exponential"] = "none"
    trend_slope: float = 0.001  # % daily change
    weekly_seasonality: list[float] = field(
        default_factory=lambda: [0.8, 0.9, 1.0, 1.0, 1.1, 1.3, 1.2]  # Mon-Sun
    )
    monthly_seasonality: dict[int, float] = field(default_factory=dict)
    noise_sigma: float = 0.1
    anomaly_probability: float = 0.01
    anomaly_magnitude: float = 2.0


@dataclass
class RetailPatternConfig:
    """Configuration for retail-specific patterns.

    Attributes:
        promotion_lift: Sales multiplier during promotions.
        stockout_behavior: How to handle stockouts (zero sales or backlog).
        price_elasticity: % demand change per % price change (negative = inverse).
        new_product_ramp_days: Days to reach full demand for new products.
        weekend_spike: Additional weekend multiplier on top of weekly seasonality.
        promotion_probability: Probability of a product having a promotion per period.
        stockout_probability: Probability of stockout per store/product/day.
    """

    promotion_lift: float = 1.3
    stockout_behavior: Literal["zero", "backlog"] = "zero"
    price_elasticity: float = -0.5
    new_product_ramp_days: int = 30
    weekend_spike: float = 1.0  # Already in weekly_seasonality, this is additional
    promotion_probability: float = 0.05
    stockout_probability: float = 0.02


@dataclass
class DimensionConfig:
    """Configuration for dimension generation.

    Attributes:
        stores: Number of stores to generate.
        products: Number of products to generate.
        store_regions: List of regions to use for stores.
        store_types: List of store types.
        product_categories: List of product categories.
        product_brands: List of product brands.
    """

    stores: int = 10
    products: int = 50
    store_regions: list[str] = field(default_factory=lambda: ["North", "South", "East", "West"])
    store_types: list[str] = field(default_factory=lambda: ["supermarket", "express", "warehouse"])
    product_categories: list[str] = field(
        default_factory=lambda: ["Beverage", "Snack", "Dairy", "Frozen", "Produce", "Bakery"]
    )
    product_brands: list[str] = field(
        default_factory=lambda: ["BrandA", "BrandB", "BrandC", "Generic", "Premium"]
    )


@dataclass
class SparsityConfig:
    """Configuration for data sparsity and gaps.

    Attributes:
        missing_combinations_pct: Fraction of store/product combos with no sales.
        random_gaps_per_series: Number of random date gaps per active series.
        gap_min_days: Minimum days for a random gap.
        gap_max_days: Maximum days for a random gap.
    """

    missing_combinations_pct: float = 0.0
    random_gaps_per_series: int = 0
    gap_min_days: int = 1
    gap_max_days: int = 7


@dataclass
class HolidayConfig:
    """Configuration for a holiday event.

    Attributes:
        date: Holiday date.
        name: Holiday name.
        multiplier: Sales multiplier for this holiday.
    """

    date: date
    name: str
    multiplier: float = 1.5


@dataclass
class ExogenousSignalConfig:
    """Configuration for exogenous demand signals (weather, macro, events).

    All signals are disabled by default — enabling them does not change the
    sales math unless `weather_temperature_sensitivity` is also non-zero or
    a feature consumer reads `exogenous_signal` rows. Default values keep
    existing scenarios byte-identical.

    Attributes:
        enable_weather: Emit `weather_temp_c` rows per (store, date).
        enable_macro: Emit `macro_index` rows per date (random walk).
        enable_events: Emit `event_flag` rows per date (binary, sparse).
        weather_temperature_sensitivity: Demand delta as a fraction per °C
            above/below the climatological mean. 0.0 = no demand impact even
            when weather rows are emitted.
        weather_climatology_mean_c: Annual mean temperature (°C) used as the
            sinusoidal center for weather generation.
        weather_amplitude_c: Peak-to-peak amplitude of the seasonal sin wave.
        weather_noise_sigma_c: Gaussian noise standard deviation in °C.
        macro_indicator_lag_days: How many days a macro signal lags demand by
            (consumers may use this; the generator itself emits values daily).
        macro_initial_value: Starting value of the random-walk index.
        macro_step_sigma: Standard deviation of the daily Gaussian increment.
        event_dates: Specific dates marked with `event_flag=1` (e.g. promo
            launch days). Empty list = no event rows emitted even when
            `enable_events=True`.
    """

    enable_weather: bool = False
    enable_macro: bool = False
    enable_events: bool = False
    weather_temperature_sensitivity: float = 0.0
    weather_climatology_mean_c: float = 15.0
    weather_amplitude_c: float = 12.0
    weather_noise_sigma_c: float = 2.0
    macro_indicator_lag_days: int = 0
    macro_initial_value: float = 100.0
    macro_step_sigma: float = 0.5
    event_dates: list[date] = field(default_factory=list)


@dataclass
class MultiSeasonalityConfig:
    """Configuration for yearly seasonality on top of weekly + monthly.

    Demand multiplier on day-of-year d is `1 + amplitude * sin(2π·(d + phase)/365)`.

    Attributes:
        yearly_seasonality_amplitude: Fraction of base demand swung by the
            yearly sin wave (e.g. 0.15 = ±15%). 0.0 disables.
        yearly_phase_offset_days: Phase shift in days (positive = later peak).
    """

    yearly_seasonality_amplitude: float = 0.0
    yearly_phase_offset_days: int = 0


@dataclass
class ChangepointEvent:
    """A single demand changepoint (COVID-style impulse + exponential decay).

    Demand multiplier on day t for a changepoint at day t0 is:
        `1 + (demand_multiplier - 1) * exp(-(t - t0) / decay_days)`
    for `t >= t0`; 1.0 otherwise.

    Attributes:
        date: Date of the changepoint impulse.
        demand_multiplier: Peak multiplier on the changepoint date.
        decay_days: e-folding time of the exponential decay. 0 = pure impulse.
    """

    date: date
    demand_multiplier: float = 1.0
    decay_days: int = 30


@dataclass
class ChangepointConfig:
    """Configuration for trend changepoints.

    Attributes:
        changepoints: List of changepoint events. Empty = disabled.
    """

    changepoints: list[ChangepointEvent] = field(default_factory=list)


@dataclass
class ReturnsConfig:
    """Configuration for synthetic returns volume.

    Attributes:
        enable: Whether to emit `sales_returns` rows at all.
        return_probability: Probability that a given sale generates a return
            (0.0 to 1.0).
        return_lag_days_min: Minimum days between sale and return.
        return_lag_days_max: Maximum days between sale and return.
        return_quantity_fraction: Fraction of the original sale quantity that
            is returned (clamped to ≥ 1 unit when a return fires).
        return_reason_distribution: Probability-weighted reasons. Weights are
            normalized at use time.
    """

    enable: bool = False
    return_probability: float = 0.02
    return_lag_days_min: int = 1
    return_lag_days_max: int = 14
    return_quantity_fraction: float = 0.5
    return_reason_distribution: dict[str, float] = field(
        default_factory=lambda: {
            "defective": 0.25,
            "wrong_size": 0.20,
            "not_as_described": 0.15,
            "changed_mind": 0.30,
            "damaged_in_transit": 0.10,
        }
    )


@dataclass
class SubstitutionConfig:
    """Configuration for cross-product substitution on stockout.

    When product A in a substitute group is stocked out at a given store on
    a given date, each other group-mate B sees its demand multiplied by
    `1 + substitution_lift_on_stockout / (group_size - 1)` for that day.

    Attributes:
        enable: Whether substitution is applied.
        substitute_groups: Sets of product IDs that substitute for each
            other. A product may appear in multiple groups.
        substitution_lift_on_stockout: Total demand lift distributed across
            group-mates when one member is stocked out (e.g. 0.5 = +50%
            split among the others).
    """

    enable: bool = False
    substitute_groups: list[list[int]] = field(default_factory=list)
    substitution_lift_on_stockout: float = 0.0


SalesChannel = Literal["in_store", "online", "click_collect", "wholesale"]
"""Valid values for ``sales_daily.channel`` — mirrors the SQL CHECK allow-list."""

LifecycleStage = Literal["intro", "growth", "maturity", "decline", "discontinued"]
"""Valid values for ``product.lifecycle_stage`` — mirrors the SQL CHECK allow-list."""

PromotionKind = Literal["pct_off", "bogo", "bundle", "markdown"]
"""Valid values for ``promotion.kind`` — mirrors the SQL CHECK allow-list."""

MarkdownTrigger = Literal["age_days", "stockout_risk", "lifecycle_decline"]
"""How a markdown event fires: stale inventory, projected stockout, or
lifecycle decline."""


@dataclass
class ChannelConfig:
    """Configuration for multi-channel sales (Phase 2).

    When ``enable_multichannel=False`` (default), every ``sales_daily`` row
    carries ``channel='in_store'`` via the SQL server default, keeping the
    regression invariant intact. When enabled, daily demand at a
    ``(store, product, date)`` is split across the configured channel mix.

    Attributes:
        enable_multichannel: Whether to split demand across channels.
        channel_mix: Probability weights per channel name. Keys must be a
            subset of ``("in_store", "online", "click_collect", "wholesale")``.
            Weights are normalized at use time; sum need not equal 1.
        online_promo_uplift: Multiplier applied to the online slice when a
            promotion is active (e.g. 1.2 = +20%).
        online_substitution_to_instore: Fraction of online-channel demand
            that cannibalizes from the in-store channel when both are active
            (0.0 = independent; 1.0 = pure substitution).
    """

    enable_multichannel: bool = False
    channel_mix: dict[str, float] = field(default_factory=dict)
    online_promo_uplift: float = 1.0
    online_substitution_to_instore: float = 0.0


@dataclass
class LifecycleConfig:
    """Configuration for product lifecycle stages (Phase 2).

    Disabled by default. When enabled, each product is assigned a
    ``launch_date`` (drawn from a distribution within or before
    ``start_date``) and optionally a ``discontinue_date``; the
    lifecycle multiplier shapes demand over the ramp / steady / decay
    curves.

    Attributes:
        enable: Whether the lifecycle generator emits stage + dates.
        intro_ramp_days: Days from ``launch_date`` to full velocity.
        growth_ramp_days: Days the ``growth`` stage lasts.
        maturity_steady_days: Days the ``maturity`` stage lasts before
            decline begins.
        decline_decay_days: e-folding time of demand decay in the
            ``decline`` stage.
        auto_progression: If True, the current stage is computed from
            ``launch_date`` relative to each sales date; if False, the
            stage is set once on the product row and held constant.
        discontinue_probability: Probability that a given product is
            discontinued during the seeded range (assigned a
            ``discontinue_date`` after launch).
        intro_multiplier: Demand floor at launch day (e.g. 0.1 = 10% of
            base for the first day, ramping to 1.0 over ``intro_ramp_days``).
        decline_multiplier: Demand floor at end of decline (e.g. 0.0
            means demand decays toward zero in the decline stage).
    """

    enable: bool = False
    intro_ramp_days: int = 30
    growth_ramp_days: int = 60
    maturity_steady_days: int = 180
    decline_decay_days: int = 90
    auto_progression: bool = True
    discontinue_probability: float = 0.0
    intro_multiplier: float = 0.1
    decline_multiplier: float = 0.0


@dataclass
class BundleConfig:
    """Configuration for BOGO/bundle promotion mechanics (Phase 2).

    Disabled by default. When enabled, a fraction of generated promotions
    become bundle/BOGO promotions with explicit member product IDs.

    Attributes:
        enable: Whether to emit bundle/BOGO promotions.
        bundle_probability: Per-promotion probability that the promotion is
            a bundle rather than the default ``pct_off``.
        bogo_share_within_bundles: Of the bundle-classed promotions, the
            fraction that are BOGO (the rest are multi-SKU bundles).
        min_bundle_size: Minimum number of member products (>= 2).
        max_bundle_size: Maximum number of member products.
        bundle_discount_pct_min: Lower bound of the bundle discount.
        bundle_discount_pct_max: Upper bound of the bundle discount.
        bundle_uplift: Demand lift on each member when a bundle promo is
            active (e.g. 1.4 = +40%).
    """

    enable: bool = False
    bundle_probability: float = 0.0
    bogo_share_within_bundles: float = 0.5
    min_bundle_size: int = 2
    max_bundle_size: int = 3
    bundle_discount_pct_min: float = 0.10
    bundle_discount_pct_max: float = 0.30
    bundle_uplift: float = 1.4


@dataclass
class MarkdownConfig:
    """Configuration for clearance markdowns (Phase 2).

    Markdowns are price-driven clearance events distinct from promo lifts.
    Disabled by default. When enabled, eligible products are marked down
    according to the chosen trigger, and the markdown is recorded both as
    a ``price_history`` drop and a ``promotion`` row with ``kind='markdown'``.

    Attributes:
        enable: Whether markdowns fire.
        trigger: Criterion: ``age_days`` (inventory older than X days),
            ``stockout_risk`` (projected stockout within Y days), or
            ``lifecycle_decline`` (product in decline stage).
        markdown_depth_pct: Fraction below base price (0.0-1.0).
        markdown_min_units_remaining: Required inventory level for the
            markdown to fire under ``age_days`` / ``stockout_risk``.
        age_days_threshold: Days of stale inventory under ``age_days``.
        markdown_demand_lift: Demand multiplier while markdown is active.
        markdown_duration_days: How long a markdown lasts.
    """

    enable: bool = False
    trigger: MarkdownTrigger = "lifecycle_decline"
    markdown_depth_pct: float = 0.30
    markdown_min_units_remaining: int = 5
    age_days_threshold: int = 60
    markdown_demand_lift: float = 1.2
    markdown_duration_days: int = 14


@dataclass
class LeadTimeConfig:
    """Configuration for lead-time-driven replenishment (Phase 2).

    Disabled by default. When enabled, ``ReplenishmentGenerator`` emits
    ``replenishment_event`` rows that drive inventory and stockout
    clustering: orders are placed every ``order_frequency_days`` and
    received ``lead_time_days`` later; on-hand inventory between
    receipts can drop to zero, producing realistic stockout windows.

    Attributes:
        enable: Whether to emit replenishment events.
        mean_lead_time_days: Mean of the Normal-distributed lead time.
        lead_time_sigma_days: Standard deviation of the lead time.
        safety_stock_days: Days of average demand kept as safety stock.
        order_frequency_days: How often a new PO is placed per
            (store, product).
        fill_rate_mean: Mean fraction of ordered units that arrive
            (1.0 = always fully shipped).
        fill_rate_sigma: Standard deviation of the fill rate.
    """

    enable: bool = False
    mean_lead_time_days: int = 7
    lead_time_sigma_days: float = 1.5
    safety_stock_days: int = 3
    order_frequency_days: int = 14
    fill_rate_mean: float = 0.97
    fill_rate_sigma: float = 0.05


@dataclass
class SeederConfig:
    """Master configuration for the data seeder.

    Attributes:
        seed: Random seed for reproducibility.
        start_date: Start of date range for data generation.
        end_date: End of date range for data generation.
        dimensions: Dimension generation configuration.
        time_series: Time-series pattern configuration.
        retail: Retail-specific pattern configuration.
        sparsity: Data sparsity configuration.
        holidays: List of holiday configurations.
        exogenous: Phase 1 exogenous signal generation (disabled by default).
        multi_seasonality: Phase 1 yearly seasonality (disabled by default).
        changepoints: Phase 1 trend changepoints (empty by default).
        returns: Phase 1 returns volume (disabled by default).
        substitution: Phase 1 stockout substitution (disabled by default).
        channels: Phase 2 multi-channel sales (disabled by default).
        lifecycle: Phase 2 product lifecycle (disabled by default).
        bundles: Phase 2 BOGO/bundle promotions (disabled by default).
        markdowns: Phase 2 clearance markdowns (disabled by default).
        lead_time: Phase 2 replenishment lead time (disabled by default).
        batch_size: Batch size for database inserts.
        enable_progress: Whether to show progress bars.
    """

    seed: int = 42
    start_date: date = field(default_factory=default_seed_start_date)
    end_date: date = field(default_factory=default_seed_end_date)
    dimensions: DimensionConfig = field(default_factory=DimensionConfig)
    time_series: TimeSeriesConfig = field(default_factory=TimeSeriesConfig)
    retail: RetailPatternConfig = field(default_factory=RetailPatternConfig)
    sparsity: SparsityConfig = field(default_factory=SparsityConfig)
    holidays: list[HolidayConfig] = field(default_factory=list)
    exogenous: ExogenousSignalConfig = field(default_factory=ExogenousSignalConfig)
    multi_seasonality: MultiSeasonalityConfig = field(default_factory=MultiSeasonalityConfig)
    changepoints: ChangepointConfig = field(default_factory=ChangepointConfig)
    returns: ReturnsConfig = field(default_factory=ReturnsConfig)
    substitution: SubstitutionConfig = field(default_factory=SubstitutionConfig)
    channels: ChannelConfig = field(default_factory=ChannelConfig)
    lifecycle: LifecycleConfig = field(default_factory=LifecycleConfig)
    bundles: BundleConfig = field(default_factory=BundleConfig)
    markdowns: MarkdownConfig = field(default_factory=MarkdownConfig)
    lead_time: LeadTimeConfig = field(default_factory=LeadTimeConfig)
    batch_size: int = 1000
    enable_progress: bool = True

    @classmethod
    def from_scenario(cls, scenario: ScenarioPreset, seed: int = 42) -> SeederConfig:
        """Create configuration from a pre-built scenario.

        Args:
            scenario: The scenario preset to use.
            seed: Random seed for reproducibility.

        Returns:
            SeederConfig configured for the scenario.
        """
        if scenario == ScenarioPreset.RETAIL_STANDARD:
            return cls(
                seed=seed,
                time_series=TimeSeriesConfig(
                    base_demand=100,
                    trend="linear",
                    trend_slope=0.0005,
                    noise_sigma=0.15,
                ),
                retail=RetailPatternConfig(
                    promotion_probability=0.1,
                    stockout_probability=0.02,
                ),
            )

        if scenario == ScenarioPreset.HOLIDAY_RUSH:
            # Deliberately calendar-pinned: the holiday dates and Q4 monthly
            # seasonality below model a specific 2024 Black Friday / Christmas
            # window, so this scenario is NOT re-anchored to today. Pass an
            # explicit start_date/end_date to shift it.
            return cls(
                seed=seed,
                start_date=date(2024, 10, 1),
                end_date=date(2024, 12, 31),
                time_series=TimeSeriesConfig(
                    base_demand=80,
                    trend="exponential",
                    trend_slope=0.005,
                    monthly_seasonality={10: 1.0, 11: 1.3, 12: 1.8},
                    noise_sigma=0.2,
                ),
                retail=RetailPatternConfig(
                    promotion_probability=0.25,
                    stockout_probability=0.15,
                ),
                holidays=[
                    HolidayConfig(date(2024, 11, 28), "Thanksgiving", 2.0),
                    HolidayConfig(date(2024, 11, 29), "Black Friday", 3.0),
                    HolidayConfig(date(2024, 12, 24), "Christmas Eve", 1.5),
                    HolidayConfig(date(2024, 12, 25), "Christmas Day", 0.3),
                ],
            )

        if scenario == ScenarioPreset.HIGH_VARIANCE:
            return cls(
                seed=seed,
                time_series=TimeSeriesConfig(
                    base_demand=100,
                    trend="none",
                    noise_sigma=0.4,
                    anomaly_probability=0.05,
                    anomaly_magnitude=3.0,
                ),
                retail=RetailPatternConfig(
                    promotion_probability=0.15,
                    stockout_probability=0.05,
                ),
            )

        if scenario == ScenarioPreset.STOCKOUT_HEAVY:
            return cls(
                seed=seed,
                time_series=TimeSeriesConfig(
                    base_demand=50,
                    trend="none",
                    noise_sigma=0.2,
                ),
                retail=RetailPatternConfig(
                    promotion_probability=0.2,
                    stockout_probability=0.25,
                    stockout_behavior="zero",
                ),
            )

        if scenario == ScenarioPreset.NEW_LAUNCHES:
            return cls(
                seed=seed,
                dimensions=DimensionConfig(
                    stores=10,
                    products=100,  # More products for launch variety
                ),
                time_series=TimeSeriesConfig(
                    base_demand=80,
                    trend="linear",
                    trend_slope=0.002,
                ),
                retail=RetailPatternConfig(
                    new_product_ramp_days=45,
                    promotion_probability=0.15,
                ),
            )

        if scenario == ScenarioPreset.SPARSE:
            return cls(
                seed=seed,
                time_series=TimeSeriesConfig(
                    base_demand=100,
                ),
                sparsity=SparsityConfig(
                    missing_combinations_pct=0.5,
                    random_gaps_per_series=3,
                    gap_min_days=2,
                    gap_max_days=10,
                ),
            )

        if scenario == ScenarioPreset.SHOWCASE_RICH:
            # PRP-38: foundation preset for the rich `/showcase` demo.
            # Larger than ``demo_minimal`` (5 stores x 15 products x 180 days)
            # so the V2 ``prophet_like`` run has enough history for full
            # horizon-bucket coverage in the feature-aware backtest, while
            # mirroring DEMO_MINIMAL's deterministic-noise tuning to avoid
            # the NaN-WAPE trap. Window anchored to *today* like DEMO_MINIMAL.
            rich_end = default_seed_end_date()
            return cls(
                seed=seed,
                start_date=rich_end - timedelta(days=SHOWCASE_RICH_SPAN_DAYS),
                end_date=rich_end,
                dimensions=DimensionConfig(stores=5, products=15),
                time_series=TimeSeriesConfig(
                    base_demand=100,
                    trend="linear",
                    trend_slope=0.0005,
                    noise_sigma=0.10,
                ),
                retail=RetailPatternConfig(
                    promotion_probability=0.15,
                    stockout_probability=0.05,
                ),
            )

        if scenario == ScenarioPreset.DEMO_MINIMAL:
            # Tiny preset for the `make demo` target. Anchored to *today* so the
            # showcase always demos current-looking data; the window runs
            # DEMO_MINIMAL_SPAN_DAYS back from today (92 days inclusive). Keeps
            # wall-clock comfortable on a developer laptop while still producing
            # a non-NaN backtest WAPE with strategy=expanding, n_splits=3,
            # horizon=14, min_train_size=30 (needs >= 30 + 3*14 = 72 days).
            demo_end = default_seed_end_date()
            return cls(
                seed=seed,
                start_date=demo_end - timedelta(days=DEMO_MINIMAL_SPAN_DAYS),
                end_date=demo_end,
                dimensions=DimensionConfig(stores=3, products=10),
                time_series=TimeSeriesConfig(
                    base_demand=100,
                    trend="linear",
                    trend_slope=0.0005,
                    noise_sigma=0.10,
                ),
                retail=RetailPatternConfig(
                    promotion_probability=0.1,
                    stockout_probability=0.02,
                ),
            )

        # Default to retail_standard
        return cls(seed=seed)
