"""Configuration dataclasses for the seeder module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Literal


class ScenarioPreset(str, Enum):
    """Pre-built scenario presets for common testing needs."""

    RETAIL_STANDARD = "retail_standard"
    HOLIDAY_RUSH = "holiday_rush"
    HIGH_VARIANCE = "high_variance"
    STOCKOUT_HEAVY = "stockout_heavy"
    NEW_LAUNCHES = "new_launches"
    SPARSE = "sparse"


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
        batch_size: Batch size for database inserts.
        enable_progress: Whether to show progress bars.
    """

    seed: int = 42
    start_date: date = field(default_factory=lambda: date(2024, 1, 1))
    end_date: date = field(default_factory=lambda: date(2024, 12, 31))
    dimensions: DimensionConfig = field(default_factory=DimensionConfig)
    time_series: TimeSeriesConfig = field(default_factory=TimeSeriesConfig)
    retail: RetailPatternConfig = field(default_factory=RetailPatternConfig)
    sparsity: SparsityConfig = field(default_factory=SparsityConfig)
    holidays: list[HolidayConfig] = field(default_factory=list)
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

        # Default to retail_standard
        return cls(seed=seed)
