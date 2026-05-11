"""Phase 2 lead-time-driven replenishment generator.

Emits ``replenishment_event`` rows that mark each receipt of inbound
stock at a store. Per ``(store, product)`` pair a purchase order is
placed every ``order_frequency_days`` starting from ``dates[0]``. Each
PO has a sampled lead time (Gaussian, clamped to ``>= 0``) and a
sampled fill rate (Gaussian, clamped to ``[0, 1]``);
``date_received = date_placed + lead_time_days`` and ``received_qty =
round(ordered_qty * fill_rate)``.

Receipts whose computed ``date_received`` would fall past
``dates[-1]`` are dropped, keeping the FK to ``calendar`` valid.

Downstream coupling: a follow-up commit will adjust
``InventorySnapshotGenerator`` to consume these events so the
realistic stockout windows emerge between scheduled receipts. This
slice only emits the rows.

Disabled path (``LeadTimeConfig`` is ``None`` or ``enable=False``)
returns ``[]`` and consumes zero rng state, preserving the
byte-identical regression invariant.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.shared.seeder.config import LeadTimeConfig


class ReplenishmentGenerator:
    """Generate replenishment events per ``(store, product)`` PO chain.

    The rng order per PO is locked: ``gauss`` for lead time, then
    ``gauss`` for fill rate. Pairs are visited in sorted
    ``(store_id, product_id)`` order so the rng stream is stable
    regardless of input ordering.
    """

    def __init__(self, rng: random.Random, config: LeadTimeConfig | None) -> None:
        """Initialize the replenishment generator.

        Args:
            rng: Random number generator for reproducibility.
            config: Phase 2 lead-time configuration. When ``None`` or
                ``enable=False`` :meth:`generate` returns ``[]`` and
                touches no rng state.
        """
        self.rng = rng
        self.config = config

    @property
    def enabled(self) -> bool:
        return self.config is not None and self.config.enable

    def generate(
        self,
        store_ids: list[int],
        product_ids: list[int],
        dates: list[date],
        base_demand: int = 100,
    ) -> list[dict[str, Any]]:
        """Emit ``replenishment_event`` records.

        Args:
            store_ids: All store IDs in the seeded scenario.
            product_ids: All product IDs in the seeded scenario.
            dates: Ordered list of seeded dates. Used as the calendar
                domain for ``date_received``; receipts past
                ``dates[-1]`` are skipped to keep the FK to
                ``calendar`` valid.
            base_demand: Daily demand assumption used to size
                ``ordered_qty``. Defaults to 100 so the generator can
                stand alone in tests; the orchestration layer should
                pass ``TimeSeriesConfig.base_demand``.

        Returns:
            List of ``replenishment_event`` dicts with keys ``date``,
            ``store_id``, ``product_id``, ``lead_time_days``,
            ``ordered_qty``, ``received_qty``. Emitted in
            ``(store_id, product_id, date_placed)`` order.

        Raises:
            ValueError: On invalid config (negative mean, zero order
                frequency, fill_rate_mean outside ``[0, 1]``, etc.).
        """
        if not self.enabled or self.config is None:
            return []

        cfg = self.config
        self._validate(cfg, base_demand)

        if not dates:
            return []

        start = dates[0]
        end = dates[-1]
        records: list[dict[str, Any]] = []
        po_window_days = cfg.order_frequency_days + cfg.safety_stock_days
        ordered_qty = max(0, base_demand * po_window_days)

        # Sort to make the rng stream stable regardless of caller order.
        for store_id in sorted(store_ids):
            for product_id in sorted(product_ids):
                self._generate_chain(
                    cfg=cfg,
                    store_id=store_id,
                    product_id=product_id,
                    start=start,
                    end=end,
                    ordered_qty=ordered_qty,
                    records=records,
                )
        return records

    def _generate_chain(
        self,
        *,
        cfg: LeadTimeConfig,
        store_id: int,
        product_id: int,
        start: date,
        end: date,
        ordered_qty: int,
        records: list[dict[str, Any]],
    ) -> None:
        """Emit PO chain for a single ``(store, product)``."""
        date_placed = start
        while date_placed <= end:
            lead_time_days = max(
                0,
                round(self.rng.gauss(cfg.mean_lead_time_days, cfg.lead_time_sigma_days)),
            )
            fill_rate = self.rng.gauss(cfg.fill_rate_mean, cfg.fill_rate_sigma)
            fill_rate = min(1.0, max(0.0, fill_rate))
            date_received = date_placed + timedelta(days=lead_time_days)
            if date_received <= end:
                received_qty = round(ordered_qty * fill_rate)
                # Defensive clamp — protects ``ck_replenishment_event_*`` even
                # under pathological fill-rate samples that round to > 1.
                received_qty = max(0, min(received_qty, ordered_qty))
                records.append(
                    {
                        "date": date_received,
                        "store_id": store_id,
                        "product_id": product_id,
                        "lead_time_days": lead_time_days,
                        "ordered_qty": ordered_qty,
                        "received_qty": received_qty,
                    }
                )
            date_placed += timedelta(days=cfg.order_frequency_days)

    @staticmethod
    def _validate(cfg: LeadTimeConfig, base_demand: int) -> None:
        if cfg.mean_lead_time_days < 0:
            raise ValueError(f"mean_lead_time_days must be >= 0, got {cfg.mean_lead_time_days}")
        if cfg.lead_time_sigma_days < 0:
            raise ValueError(f"lead_time_sigma_days must be >= 0, got {cfg.lead_time_sigma_days}")
        if cfg.safety_stock_days < 0:
            raise ValueError(f"safety_stock_days must be >= 0, got {cfg.safety_stock_days}")
        if cfg.order_frequency_days < 1:
            raise ValueError(f"order_frequency_days must be >= 1, got {cfg.order_frequency_days}")
        if not 0.0 <= cfg.fill_rate_mean <= 1.0:
            raise ValueError(f"fill_rate_mean must be in [0, 1], got {cfg.fill_rate_mean}")
        if cfg.fill_rate_sigma < 0:
            raise ValueError(f"fill_rate_sigma must be >= 0, got {cfg.fill_rate_sigma}")
        if base_demand < 0:
            raise ValueError(f"base_demand must be >= 0, got {base_demand}")
