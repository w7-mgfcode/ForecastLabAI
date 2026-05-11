"""Product dimension generator."""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.shared.seeder.config import DimensionConfig, LifecycleConfig


# Product name components for realistic generation
PRODUCT_ADJECTIVES = [
    "Classic",
    "Premium",
    "Organic",
    "Fresh",
    "Natural",
    "Original",
    "Lite",
    "Zero",
    "Sugar-Free",
    "Low-Fat",
    "Whole",
    "Crispy",
    "Creamy",
    "Smooth",
    "Bold",
    "Mild",
    "Spicy",
    "Sweet",
    "Tangy",
    "Rich",
]

PRODUCT_NOUNS_BY_CATEGORY = {
    "Beverage": [
        "Cola",
        "Juice",
        "Water",
        "Tea",
        "Coffee",
        "Soda",
        "Energy Drink",
        "Lemonade",
        "Smoothie",
        "Milk",
    ],
    "Snack": [
        "Chips",
        "Crackers",
        "Pretzels",
        "Popcorn",
        "Nuts",
        "Cookies",
        "Granola Bar",
        "Trail Mix",
        "Jerky",
        "Cheese Puffs",
    ],
    "Dairy": [
        "Milk",
        "Yogurt",
        "Cheese",
        "Butter",
        "Cream",
        "Cottage Cheese",
        "Sour Cream",
        "Ice Cream",
        "Cream Cheese",
        "Kefir",
    ],
    "Frozen": [
        "Pizza",
        "Ice Cream",
        "Vegetables",
        "Dinner",
        "Breakfast",
        "Burrito",
        "Fish Sticks",
        "Waffles",
        "Fruit",
        "Pot Pie",
    ],
    "Produce": [
        "Apples",
        "Bananas",
        "Oranges",
        "Tomatoes",
        "Lettuce",
        "Carrots",
        "Potatoes",
        "Onions",
        "Peppers",
        "Berries",
    ],
    "Bakery": [
        "Bread",
        "Bagels",
        "Muffins",
        "Croissants",
        "Donuts",
        "Rolls",
        "Cake",
        "Pie",
        "Cookies",
        "Buns",
    ],
}

# Default nouns if category not in dict
DEFAULT_NOUNS = [
    "Product",
    "Item",
    "Good",
    "Supply",
    "Commodity",
]


class ProductGenerator:
    """Generator for product dimension data.

    Phase 2 ``lifecycle`` is opt-in: when ``LifecycleConfig.enable=False``
    (default) the generator emits byte-identical output to its
    pre-Phase-2 behavior — no extra rng draws, no extra dict keys.
    """

    # Maximum SKU space: 10000-99999 = 90,000 unique SKUs
    MAX_SKU_SPACE = 90000
    MAX_SKU_ATTEMPTS = 1000

    # Discrete pack-size distribution sampled when lifecycle is enabled.
    _PACK_SIZE_CHOICES = (1, 1, 1, 2, 4, 6, 12)

    def __init__(
        self,
        rng: random.Random,
        config: DimensionConfig,
        lifecycle_config: LifecycleConfig | None = None,
        date_range: tuple[date, date] | None = None,
    ) -> None:
        """Initialize the product generator.

        Args:
            rng: Random number generator for reproducibility.
            config: Dimension configuration.
            lifecycle_config: Optional Phase 2 lifecycle configuration. When
                ``None`` or ``enable=False`` the generator emits pre-Phase-2
                rows byte-identically.
            date_range: ``(start_date, end_date)`` of the seeded range. Used
                only when ``lifecycle_config.enable`` is True so launch dates
                land near or before ``start_date``.

        Raises:
            ValueError: If requested products exceed available SKU space.
        """
        self.rng = rng
        self.config = config
        self.lifecycle_config = lifecycle_config
        self.date_range = date_range
        self._used_skus: set[str] = set()

        # Validate SKU space capacity
        if config.products > self.MAX_SKU_SPACE:
            raise ValueError(
                f"Cannot generate {config.products} products: "
                f"SKU space only supports {self.MAX_SKU_SPACE} unique SKUs"
            )

    def _generate_unique_sku(self) -> str:
        """Generate a unique SKU.

        Uses randomized generation for efficiency, with deterministic fallback
        when near capacity to guarantee success.

        Raises:
            RuntimeError: If SKU space is completely exhausted.
        """
        # Check if SKU space is exhausted
        if len(self._used_skus) >= self.MAX_SKU_SPACE:
            raise RuntimeError(
                f"SKU space exhausted: {len(self._used_skus)} SKUs already generated"
            )

        remaining = self.MAX_SKU_SPACE - len(self._used_skus)

        # If plenty of space remaining, use randomized approach
        if remaining > self.MAX_SKU_ATTEMPTS:
            for _ in range(self.MAX_SKU_ATTEMPTS):
                sku = f"SKU-{self.rng.randint(10000, 99999)}"
                if sku not in self._used_skus:
                    self._used_skus.add(sku)
                    return sku

        # Near capacity or random attempts exhausted: use deterministic fallback
        # Compute all available SKUs and pick one
        all_skus = {f"SKU-{i}" for i in range(10000, 10000 + self.MAX_SKU_SPACE)}
        available_skus = all_skus - self._used_skus

        if not available_skus:
            raise RuntimeError(
                f"SKU space exhausted: {len(self._used_skus)} SKUs already generated"
            )

        # Pick deterministically (sorted first available)
        sku = min(available_skus)
        self._used_skus.add(sku)
        return sku

    def _generate_name(self, category: str, brand: str) -> str:
        """Generate a realistic product name.

        Args:
            category: Product category for context-aware naming.
            brand: Brand name to include.

        Returns:
            Generated product name.
        """
        adjective = self.rng.choice(PRODUCT_ADJECTIVES)
        nouns = PRODUCT_NOUNS_BY_CATEGORY.get(category, DEFAULT_NOUNS)
        noun = self.rng.choice(nouns)
        return f"{brand} {adjective} {noun}"

    def _generate_price(self) -> tuple[Decimal, Decimal]:
        """Generate realistic base price and cost.

        Returns:
            Tuple of (base_price, base_cost).
        """
        # Generate price between $0.99 and $29.99
        price_cents = self.rng.randint(99, 2999)
        base_price = Decimal(price_cents) / Decimal(100)

        # Cost is 40-70% of price (margin 30-60%)
        margin_pct = self.rng.uniform(0.30, 0.60)
        base_cost = base_price * Decimal(str(1 - margin_pct))
        base_cost = base_cost.quantize(Decimal("0.01"))

        return base_price, base_cost

    def _generate_lifecycle_attrs(self, category: str) -> dict[str, Any]:
        """Sample lifecycle attributes for a single product.

        Returns the additive dict appended to the product row when
        ``lifecycle_config.enable`` is True. The order of rng calls inside
        this method must remain stable across Phase 2 sub-releases — any
        rearrangement would shift downstream rng state and break
        reproducibility for Phase-2-enabled scenarios.
        """
        cfg = self.lifecycle_config
        if cfg is None or not cfg.enable or self.date_range is None:
            raise RuntimeError(
                "_generate_lifecycle_attrs called with lifecycle disabled — "
                "the caller must gate on lifecycle_config.enable."
            )
        start, end = self.date_range

        # Sub-category: re-use the category->nouns map so subcategory ties to
        # category coherently. Keeps the seeded corpus believable.
        nouns = PRODUCT_NOUNS_BY_CATEGORY.get(category, DEFAULT_NOUNS)
        subcategory = self.rng.choice(nouns)

        # Pack size: discrete distribution that favours single units.
        pack_size = self.rng.choice(self._PACK_SIZE_CHOICES)

        # Launch date: uniform between (start - 90d) and (start + 60d).
        # Products with launch_date < start are already mature by start; those
        # within [start, start+60d] are in intro/growth during the seeded
        # window.
        launch_offset_min = -90
        launch_offset_max = 60
        launch_offset_days = self.rng.randint(launch_offset_min, launch_offset_max)
        launch_date = start + timedelta(days=launch_offset_days)

        # Discontinue date: small probability the product is retired during
        # the range. Always after launch_date.
        discontinue_date: date | None = None
        roll = self.rng.random()
        if cfg.discontinue_probability > 0.0 and roll < cfg.discontinue_probability:
            min_disc_offset = max(
                cfg.intro_ramp_days + cfg.growth_ramp_days + 30,
                30,
            )
            disc_offset_days = self.rng.randint(min_disc_offset, max(min_disc_offset, 365))
            candidate = launch_date + timedelta(days=disc_offset_days)
            if candidate <= end:
                discontinue_date = candidate

        # Initial stage: pick from the allow-list. When auto_progression is
        # True, the stage on the row is the *initial* stage at launch_date
        # and downstream code re-derives the current stage by date.
        if cfg.auto_progression:
            lifecycle_stage = "intro"
        else:
            lifecycle_stage = self.rng.choice(("intro", "growth", "maturity", "decline"))

        return {
            "subcategory": subcategory,
            "pack_size": pack_size,
            "launch_date": launch_date,
            "discontinue_date": discontinue_date,
            "lifecycle_stage": lifecycle_stage,
        }

    def generate(self) -> list[dict[str, Any]]:
        """Generate product dimension records.

        Returns:
            List of product dictionaries ready for database insertion. When
            ``lifecycle_config.enable`` is True each row also carries
            ``subcategory``, ``pack_size``, ``launch_date``,
            ``discontinue_date``, and ``lifecycle_stage``.
        """
        products: list[dict[str, Any]] = []
        lifecycle_on = (
            self.lifecycle_config is not None
            and self.lifecycle_config.enable
            and self.date_range is not None
        )

        for _ in range(self.config.products):
            category = self.rng.choice(self.config.product_categories)
            brand = self.rng.choice(self.config.product_brands)
            base_price, base_cost = self._generate_price()

            product: dict[str, Any] = {
                "sku": self._generate_unique_sku(),
                "name": self._generate_name(category, brand),
                "category": category,
                "brand": brand,
                "base_price": base_price,
                "base_cost": base_cost,
            }
            if lifecycle_on:
                product.update(self._generate_lifecycle_attrs(category))
            products.append(product)

        return products
