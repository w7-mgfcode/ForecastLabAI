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

    # Maximum store code space: S0001-S9999 = 9,999 unique codes
    MAX_CODE_SPACE = 9999
    MAX_CODE_ATTEMPTS = 1000

    def __init__(self, rng: random.Random, config: DimensionConfig) -> None:
        """Initialize the store generator.

        Args:
            rng: Random number generator for reproducibility.
            config: Dimension configuration.

        Raises:
            ValueError: If requested stores exceed available code space.
        """
        self.rng = rng
        self.config = config
        self._used_codes: set[str] = set()

        # Validate code space capacity
        if config.stores > self.MAX_CODE_SPACE:
            raise ValueError(
                f"Cannot generate {config.stores} stores: "
                f"store code space only supports {self.MAX_CODE_SPACE} unique codes"
            )

    def _generate_unique_code(self) -> str:
        """Generate a unique store code.

        Uses randomized generation for efficiency, with deterministic fallback
        when near capacity to guarantee success.

        Raises:
            RuntimeError: If code space is completely exhausted.
        """
        # Check if code space is exhausted
        if len(self._used_codes) >= self.MAX_CODE_SPACE:
            raise RuntimeError(
                f"Store code space exhausted: {len(self._used_codes)} codes already generated"
            )

        remaining = self.MAX_CODE_SPACE - len(self._used_codes)

        # If plenty of space remaining, use randomized approach
        if remaining > self.MAX_CODE_ATTEMPTS:
            for _ in range(self.MAX_CODE_ATTEMPTS):
                code = f"S{self.rng.randint(1, 9999):04d}"
                if code not in self._used_codes:
                    self._used_codes.add(code)
                    return code

        # Near capacity or random attempts exhausted: use deterministic fallback
        # Compute all available codes and pick one
        all_codes = {f"S{i:04d}" for i in range(1, self.MAX_CODE_SPACE + 1)}
        available_codes = all_codes - self._used_codes

        if not available_codes:
            raise RuntimeError(
                f"Store code space exhausted: {len(self._used_codes)} codes already generated"
            )

        # Pick deterministically (sorted first available)
        code = min(available_codes)
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
