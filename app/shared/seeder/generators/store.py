"""Store dimension generator."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.shared.seeder.config import DimensionConfig


# Store name components for realistic generation
STORE_PREFIXES = [
    "Central",
    "Downtown",
    "Uptown",
    "Riverside",
    "Lakeside",
    "Hillcrest",
    "Valley",
    "Park",
    "Plaza",
    "Metro",
    "Gateway",
    "Harbor",
    "Summit",
    "Cedar",
    "Oak",
    "Pine",
    "Maple",
    "Elm",
    "Main",
    "Grand",
]

STORE_SUFFIXES = [
    "Market",
    "Mart",
    "Store",
    "Shop",
    "Center",
    "Depot",
    "Hub",
    "Point",
    "Place",
    "Square",
]

CITIES = [
    "New York",
    "Los Angeles",
    "Chicago",
    "Houston",
    "Phoenix",
    "Philadelphia",
    "San Antonio",
    "San Diego",
    "Dallas",
    "Austin",
    "Seattle",
    "Denver",
    "Boston",
    "Atlanta",
    "Miami",
    "Portland",
    "Minneapolis",
    "Detroit",
    "Tampa",
    "Charlotte",
]


class StoreGenerator:
    """Generator for store dimension data."""

    def __init__(self, rng: random.Random, config: DimensionConfig) -> None:
        """Initialize the store generator.

        Args:
            rng: Random number generator for reproducibility.
            config: Dimension configuration.
        """
        self.rng = rng
        self.config = config
        self._used_codes: set[str] = set()

    def _generate_unique_code(self) -> str:
        """Generate a unique store code."""
        while True:
            code = f"S{self.rng.randint(1, 9999):04d}"
            if code not in self._used_codes:
                self._used_codes.add(code)
                return code

    def _generate_name(self) -> str:
        """Generate a realistic store name."""
        prefix = self.rng.choice(STORE_PREFIXES)
        suffix = self.rng.choice(STORE_SUFFIXES)
        return f"{prefix} {suffix}"

    def generate(self) -> list[dict[str, str | None]]:
        """Generate store dimension records.

        Returns:
            List of store dictionaries ready for database insertion.
        """
        stores: list[dict[str, str | None]] = []

        for _ in range(self.config.stores):
            store: dict[str, str | None] = {
                "code": self._generate_unique_code(),
                "name": self._generate_name(),
                "region": self.rng.choice(self.config.store_regions),
                "city": self.rng.choice(CITIES),
                "store_type": self.rng.choice(self.config.store_types),
            }
            stores.append(store)

        return stores
