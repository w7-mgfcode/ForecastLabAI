"""Product dimension generator."""

from __future__ import annotations

import random
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.shared.seeder.config import DimensionConfig


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
    """Generator for product dimension data."""

    # Maximum SKU space: 10000-99999 = 90,000 unique SKUs
    MAX_SKU_SPACE = 90000
    MAX_SKU_ATTEMPTS = 1000

    def __init__(self, rng: random.Random, config: DimensionConfig) -> None:
        """Initialize the product generator.

        Args:
            rng: Random number generator for reproducibility.
            config: Dimension configuration.

        Raises:
            ValueError: If requested products exceed available SKU space.
        """
        self.rng = rng
        self.config = config
        self._used_skus: set[str] = set()

        # Validate SKU space capacity
        if config.products > self.MAX_SKU_SPACE:
            raise ValueError(
                f"Cannot generate {config.products} products: "
                f"SKU space only supports {self.MAX_SKU_SPACE} unique SKUs"
            )

    def _generate_unique_sku(self) -> str:
        """Generate a unique SKU.

        Raises:
            RuntimeError: If SKU space is exhausted or max attempts exceeded.
        """
        # Check if SKU space is exhausted
        if len(self._used_skus) >= self.MAX_SKU_SPACE:
            raise RuntimeError(
                f"SKU space exhausted: {len(self._used_skus)} SKUs already generated"
            )

        for _ in range(self.MAX_SKU_ATTEMPTS):
            sku = f"SKU-{self.rng.randint(10000, 99999)}"
            if sku not in self._used_skus:
                self._used_skus.add(sku)
                return sku

        # If we hit max attempts, likely near capacity - raise error
        raise RuntimeError(
            f"Failed to generate unique SKU after {self.MAX_SKU_ATTEMPTS} attempts. "
            f"SKU space utilization: {len(self._used_skus)}/{self.MAX_SKU_SPACE}"
        )

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

    def generate(self) -> list[dict[str, str | Decimal | None]]:
        """Generate product dimension records.

        Returns:
            List of product dictionaries ready for database insertion.
        """
        products: list[dict[str, str | Decimal | None]] = []

        for _ in range(self.config.products):
            category = self.rng.choice(self.config.product_categories)
            brand = self.rng.choice(self.config.product_brands)
            base_price, base_cost = self._generate_price()

            product: dict[str, str | Decimal | None] = {
                "sku": self._generate_unique_sku(),
                "name": self._generate_name(category, brand),
                "category": category,
                "brand": brand,
                "base_price": base_price,
                "base_cost": base_cost,
            }
            products.append(product)

        return products
