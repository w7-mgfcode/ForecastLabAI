"""Phase 2 markdown (clearance) generator.

Emits ``Promotion(kind='markdown')`` rows + companion ``PriceHistory``
drop rows for two trigger modes:

- ``lifecycle_decline`` — fires chain-wide (``store_id=None``) on the
  first day a product enters the decline stage according to a
  ``LifecycleGenerator``.
- ``stockout_risk`` — fires per-``(store, product)`` ending the day
  before each observed stockout, with a window of
  ``markdown_duration_days``.

The ``age_days`` trigger is deferred to a follow-up; see issue #94.
``MarkdownGenerator`` raises ``NotImplementedError`` for that mode.

Disabled path (``MarkdownConfig`` is ``None`` or ``enable=False``)
returns empty containers and consumes zero rng state, preserving the
byte-identical regression invariant. The generator is currently
deterministic: even the enabled path issues no rng draws. The ``rng``
parameter is kept for API consistency with peer Phase 2 generators
in case future variants need randomness.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.shared.seeder.config import MarkdownConfig
    from app.shared.seeder.generators.lifecycle import LifecycleGenerator


# ``promotion.discount_pct`` is ``Numeric(5, 4)``; ``price_history.price``
# is ``Numeric(10, 2)``.
_PCT_QUANTIZE = Decimal("0.0001")
_PRICE_QUANTIZE = Decimal("0.01")


class MarkdownGenerator:
    """Emit markdown promo + price-history rows.

    The orchestration layer (DataSeeder) is responsible for wiring this
    generator's output to ``SalesDailyGenerator``'s ``markdown_dates``
    lookup so demand picks up the configured ``markdown_demand_lift``
    over markdown windows.
    """

    def __init__(self, rng: random.Random, config: MarkdownConfig | None) -> None:
        """Initialize the markdown generator.

        Args:
            rng: Random number generator. Reserved for future variants;
                the current implementation is fully deterministic.
            config: Phase 2 markdown configuration. When ``None`` or
                ``enable=False`` :meth:`generate` returns empty
                containers.
        """
        self.rng = rng
        self.config = config

    @property
    def enabled(self) -> bool:
        return self.config is not None and self.config.enable

    def generate(
        self,
        product_specs: list[dict[str, Any]],
        store_ids: list[int],
        stockout_dates: dict[tuple[int, int], set[date]],
        dates: list[date],
        lifecycle: LifecycleGenerator | None = None,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        dict[tuple[int, int], set[date]],
    ]:
        """Generate markdown promotions, price drops, and markdown_dates lookup.

        Args:
            product_specs: List of ``{"product_id", "base_price",
                "launch_date" (optional), "discontinue_date" (optional)}``
                dicts. Lifecycle dates are only needed for
                ``trigger='lifecycle_decline'``.
            store_ids: All store IDs in the seeded scenario. Used to
                populate ``markdown_dates`` for chain-wide markdowns so
                downstream ``SalesDailyGenerator`` can apply the demand
                lift uniformly across the chain.
            stockout_dates: ``(store_id, product_id) -> set[date]``
                from ``InventorySnapshotGenerator``. Used only for
                ``trigger='stockout_risk'``.
            dates: Full ordered list of dates in the seeded range.
                ``markdown_start`` is clamped to ``dates[0]`` when the
                computed start would precede the range.
            lifecycle: Optional pre-built ``LifecycleGenerator``. Used
                only for ``trigger='lifecycle_decline'``. When absent
                or disabled, the lifecycle trigger emits no rows.

        Returns:
            Three-tuple:
                - ``promo_records``: ``Promotion(kind='markdown')`` dicts.
                - ``price_history_records``: ``PriceHistory`` rows
                  carrying the discounted price over the markdown window.
                - ``markdown_dates``: ``(store_id, product_id) -> set[date]``
                  lookup of every active markdown day, useful for the
                  ``SalesDailyGenerator`` lift integration.

        Raises:
            NotImplementedError: If ``config.trigger == 'age_days'``.
                Tracked at issue #94.
            ValueError: If ``markdown_depth_pct`` is outside ``[0, 1]``
                or ``markdown_duration_days < 1``.
        """
        if not self.enabled or self.config is None:
            return ([], [], {})

        cfg = self.config
        if cfg.trigger == "age_days":
            raise NotImplementedError(
                "MarkdownConfig.trigger='age_days' is deferred. See follow-up "
                "issue #94 for the implementation plan."
            )
        if not 0.0 <= cfg.markdown_depth_pct <= 1.0:
            raise ValueError(f"markdown_depth_pct must be in [0, 1], got {cfg.markdown_depth_pct}")
        if cfg.markdown_duration_days < 1:
            raise ValueError(
                f"markdown_duration_days must be >= 1, got {cfg.markdown_duration_days}"
            )

        promo_records: list[dict[str, Any]] = []
        price_history_records: list[dict[str, Any]] = []
        markdown_dates: dict[tuple[int, int], set[date]] = {}

        if cfg.trigger == "lifecycle_decline":
            self._emit_lifecycle_decline(
                cfg=cfg,
                product_specs=product_specs,
                store_ids=store_ids,
                dates=dates,
                lifecycle=lifecycle,
                promo_records=promo_records,
                price_history_records=price_history_records,
                markdown_dates=markdown_dates,
            )
        else:  # cfg.trigger == "stockout_risk"
            self._emit_stockout_risk(
                cfg=cfg,
                product_specs=product_specs,
                stockout_dates=stockout_dates,
                dates=dates,
                promo_records=promo_records,
                price_history_records=price_history_records,
                markdown_dates=markdown_dates,
            )

        return (promo_records, price_history_records, markdown_dates)

    # ---------------------------------------------------------------------- #
    # Trigger implementations
    # ---------------------------------------------------------------------- #

    def _emit_lifecycle_decline(
        self,
        *,
        cfg: MarkdownConfig,
        product_specs: list[dict[str, Any]],
        store_ids: list[int],
        dates: list[date],
        lifecycle: LifecycleGenerator | None,
        promo_records: list[dict[str, Any]],
        price_history_records: list[dict[str, Any]],
        markdown_dates: dict[tuple[int, int], set[date]],
    ) -> None:
        if lifecycle is None or not lifecycle.enabled or not dates:
            return  # Cannot detect decline without a lifecycle source.

        discount_pct = Decimal(str(cfg.markdown_depth_pct)).quantize(_PCT_QUANTIZE)

        for spec in product_specs:
            launch = spec.get("launch_date")
            if launch is None:
                continue
            discontinue = spec.get("discontinue_date")
            decline_start = self._first_decline_date(
                dates=dates,
                launch=launch,
                discontinue=discontinue,
                lifecycle=lifecycle,
            )
            if decline_start is None:
                continue

            md_end = min(
                decline_start + timedelta(days=cfg.markdown_duration_days - 1),
                dates[-1],
            )
            base_price = self._as_decimal(spec["base_price"])
            markdown_price = (base_price * (Decimal("1") - discount_pct)).quantize(_PRICE_QUANTIZE)
            product_id = int(spec["product_id"])

            promo_records.append(
                {
                    "product_id": product_id,
                    "store_id": None,  # chain-wide
                    "name": "Lifecycle Clearance",
                    "kind": "markdown",
                    "discount_pct": discount_pct,
                    "discount_amount": None,
                    "bundle_member_product_ids": None,
                    "start_date": decline_start,
                    "end_date": md_end,
                }
            )
            price_history_records.append(
                {
                    "product_id": product_id,
                    "store_id": None,
                    "price": markdown_price,
                    "valid_from": decline_start,
                    "valid_to": md_end,
                }
            )
            # Chain-wide markdown: every store sees the lift.
            for sid in store_ids:
                self._fill_date_range(
                    markdown_dates.setdefault((sid, product_id), set()),
                    decline_start,
                    md_end,
                )

    def _emit_stockout_risk(
        self,
        *,
        cfg: MarkdownConfig,
        product_specs: list[dict[str, Any]],
        stockout_dates: dict[tuple[int, int], set[date]],
        dates: list[date],
        promo_records: list[dict[str, Any]],
        price_history_records: list[dict[str, Any]],
        markdown_dates: dict[tuple[int, int], set[date]],
    ) -> None:
        if not dates:
            return

        discount_pct = Decimal(str(cfg.markdown_depth_pct)).quantize(_PCT_QUANTIZE)
        first_date = dates[0]
        # Precompute base_price lookup for O(1) access.
        price_by_product: dict[int, Decimal] = {
            int(spec["product_id"]): self._as_decimal(spec["base_price"]) for spec in product_specs
        }

        # Sort keys for deterministic output order regardless of dict
        # iteration order.
        for key in sorted(stockout_dates.keys()):
            store_id, product_id = key
            base_price = price_by_product.get(product_id)
            if base_price is None:
                continue

            markdown_price = (base_price * (Decimal("1") - discount_pct)).quantize(_PRICE_QUANTIZE)
            last_md_end: date | None = None

            for stockout_date in sorted(stockout_dates[key]):
                md_end = stockout_date - timedelta(days=1)
                md_start = md_end - timedelta(days=cfg.markdown_duration_days - 1)
                if md_start < first_date:
                    md_start = first_date
                if md_end < md_start:
                    continue  # stockout on/before first date; no markdown room
                # Dedupe overlapping windows by collapsing into the most
                # recent. ``sorted_stockouts`` guarantees forward iteration.
                if last_md_end is not None and md_start <= last_md_end:
                    continue

                promo_records.append(
                    {
                        "product_id": product_id,
                        "store_id": store_id,
                        "name": "Stockout Clearance",
                        "kind": "markdown",
                        "discount_pct": discount_pct,
                        "discount_amount": None,
                        "bundle_member_product_ids": None,
                        "start_date": md_start,
                        "end_date": md_end,
                    }
                )
                price_history_records.append(
                    {
                        "product_id": product_id,
                        "store_id": store_id,
                        "price": markdown_price,
                        "valid_from": md_start,
                        "valid_to": md_end,
                    }
                )
                self._fill_date_range(
                    markdown_dates.setdefault(key, set()),
                    md_start,
                    md_end,
                )
                last_md_end = md_end

    # ---------------------------------------------------------------------- #
    # Helpers
    # ---------------------------------------------------------------------- #

    @staticmethod
    def _first_decline_date(
        *,
        dates: list[date],
        launch: date,
        discontinue: date | None,
        lifecycle: LifecycleGenerator,
    ) -> date | None:
        """Return the earliest date in ``dates`` where the product is in decline."""
        for d in dates:
            if lifecycle.stage_for(d, launch, discontinue) == "decline":
                return d
        return None

    @staticmethod
    def _fill_date_range(
        bucket: set[date],
        start: date,
        end: date,
    ) -> None:
        current = start
        while current <= end:
            bucket.add(current)
            current += timedelta(days=1)

    @staticmethod
    def _as_decimal(value: Decimal | int | float | str) -> Decimal:
        """Coerce numeric input to ``Decimal``.

        Product specs may carry ``Decimal``, ``int``, ``float`` or numeric
        strings depending on upstream provenance. Coercion through ``str``
        avoids binary-float artefacts.
        """
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
