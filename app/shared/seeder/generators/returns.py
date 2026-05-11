"""Returns generator: synthetic ``sales_returns`` rows.

Phase 1 of the seeder realism extension. Samples sales rows
(probabilistically) and emits a delayed return event for each pick. The
return is *not* subtracted from ``sales_daily.quantity`` — returns are an
additive, separately queryable table so the forecasting/feature layer can
opt in.

Output schema matches ``app.features.data_platform.models.SalesReturn``:

    {"date", "store_id", "product_id", "return_quantity", "return_reason"}

Reproducibility: uses the seeder's ``random.Random`` instance.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.shared.seeder.config import ReturnsConfig


class ReturnsGenerator:
    """Generator for synthetic sales returns."""

    def __init__(self, rng: random.Random, config: ReturnsConfig) -> None:
        """Initialize the generator.

        Args:
            rng: Seeded random number generator.
            config: Returns configuration.
        """
        self.rng = rng
        self.config = config

    def _pick_reason(self) -> str:
        """Sample a return reason from the configured distribution.

        Returns:
            Reason string. Falls back to ``"unspecified"`` if the
            distribution is empty (defensive — config defaults are non-empty).
        """
        reasons = list(self.config.return_reason_distribution.keys())
        weights = list(self.config.return_reason_distribution.values())
        if not reasons:
            return "unspecified"
        # random.choices is deterministic under self.rng.
        return self.rng.choices(reasons, weights=weights, k=1)[0]

    def generate(
        self,
        sales_records: list[dict[str, date | int | Decimal]],
        end_date: date,
    ) -> list[dict[str, date | int | str]]:
        """Generate return rows from a list of sales rows.

        Args:
            sales_records: Sales dicts from ``SalesDailyGenerator.generate``.
                Each must contain ``date``, ``store_id``, ``product_id``,
                ``quantity``.
            end_date: Calendar end date. Returns lagged beyond ``end_date``
                are clamped to ``end_date`` (so they have a calendar FK
                target and don't trigger FK violations).

        Returns:
            List of return-row dicts. Empty when the returns feature is
            disabled or no sales qualify.
        """
        if not self.config.enable or not sales_records:
            return []

        lag_min = self.config.return_lag_days_min
        lag_max = max(self.config.return_lag_days_max, lag_min)

        returns: list[dict[str, date | int | str]] = []
        for sale in sales_records:
            quantity = sale["quantity"]
            sale_date = sale["date"]
            store_id = sale["store_id"]
            product_id = sale["product_id"]
            # Sales rows from SalesDailyGenerator carry these types; the
            # union annotation is wider than the runtime guarantees because
            # the same dict shape is reused for inserts. Defensive narrowing
            # here keeps mypy --strict happy without a cast.
            if not (
                isinstance(quantity, int)
                and isinstance(sale_date, date)
                and isinstance(store_id, int)
                and isinstance(product_id, int)
            ):
                continue
            if quantity <= 0:
                continue
            if self.rng.random() >= self.config.return_probability:
                continue

            lag = self.rng.randint(lag_min, lag_max)
            return_date = sale_date + timedelta(days=lag)
            if return_date > end_date:
                return_date = end_date

            # Fraction of original quantity, with a minimum of 1 unit.
            raw_qty = quantity * self.config.return_quantity_fraction
            return_qty = max(1, round(raw_qty))
            return_qty = min(return_qty, quantity)

            returns.append(
                {
                    "date": return_date,
                    "store_id": store_id,
                    "product_id": product_id,
                    "return_quantity": return_qty,
                    "return_reason": self._pick_reason(),
                }
            )

        return returns
