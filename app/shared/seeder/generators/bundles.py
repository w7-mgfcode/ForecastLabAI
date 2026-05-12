"""Phase 2 bundle/BOGO promotion converter.

Wraps :class:`PromotionGenerator`'s output: with probability
``BundleConfig.bundle_probability``, an eligible promotion is converted
into a ``kind='bundle'`` or ``kind='bogo'`` row with a list of member
product IDs and a discount drawn from the configured range. When the
feature is disabled the input list is returned untouched and no rng
state is consumed, preserving the byte-identical regression invariant.
"""

from __future__ import annotations

import random
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.shared.seeder.config import BundleConfig


# ``promotion.discount_pct`` is ``Numeric(5, 4)`` — 4 decimal places.
_DISCOUNT_QUANTIZE = Decimal("0.0001")


class BundleGenerator:
    """Convert a slice of generated promotions into bundle / BOGO rows.

    Each converted promotion consumes four rng draws in this locked
    order — ``random()`` (convert?), ``random()`` (bogo-or-bundle?),
    ``randint()`` (n_members), ``sample()`` (members), ``uniform()``
    (discount). Per-promo skips for too-small product pools happen
    *before* the first rng draw, so the rng stream is stable across
    runs where only the eligible pool shrinks.
    """

    def __init__(self, rng: random.Random, config: BundleConfig | None) -> None:
        """Initialize the bundle generator.

        Args:
            rng: Random number generator for reproducibility.
            config: Phase 2 bundle configuration. When ``None`` or
                ``enable=False`` :meth:`apply` is a no-op that touches
                neither the promotion list nor the rng.
        """
        self.rng = rng
        self.config = config

    @property
    def enabled(self) -> bool:
        return self.config is not None and self.config.enable

    def apply(
        self,
        promotions: list[dict[str, Any]],
        product_pool: list[int],
    ) -> list[dict[str, Any]]:
        """Convert a fraction of promotions to bundle/BOGO kinds.

        Args:
            promotions: List of promotion record dicts as produced by
                :class:`PromotionGenerator.generate`. Mutated in place
                when the generator is enabled.
            product_pool: All product IDs in the seeded scenario.
                Bundle members are drawn from this pool excluding the
                host product of each promotion.

        Returns:
            The same ``promotions`` list reference. Untouched and with
            zero rng consumption when the generator is disabled or when
            every promo's eligible pool is below ``min_bundle_size``.

        Raises:
            ValueError: If the configuration violates the bundle-size
                invariants (``min_bundle_size < 2`` or ``max < min``).
        """
        if not self.enabled or self.config is None:
            return promotions

        cfg = self.config
        if cfg.min_bundle_size < 2:
            raise ValueError(
                f"BundleConfig.min_bundle_size must be >= 2, got {cfg.min_bundle_size}"
            )
        if cfg.max_bundle_size < cfg.min_bundle_size:
            raise ValueError(
                "BundleConfig.max_bundle_size must be >= min_bundle_size "
                f"(got min={cfg.min_bundle_size}, max={cfg.max_bundle_size})"
            )

        for record in promotions:
            host_product_id = record["product_id"]
            eligible_members = [pid for pid in product_pool if pid != host_product_id]
            # Best-effort skip when the pool is too small to satisfy
            # ``min_bundle_size``. Done before any rng draw so a smaller
            # pool doesn't desync the rng stream from a larger run.
            if len(eligible_members) < cfg.min_bundle_size:
                continue

            if self.rng.random() >= cfg.bundle_probability:
                continue

            kind = "bogo" if self.rng.random() < cfg.bogo_share_within_bundles else "bundle"
            n_members = self.rng.randint(
                cfg.min_bundle_size,
                min(cfg.max_bundle_size, len(eligible_members)),
            )
            members = self.rng.sample(eligible_members, n_members)
            discount = self.rng.uniform(
                cfg.bundle_discount_pct_min,
                cfg.bundle_discount_pct_max,
            )

            record["kind"] = kind
            record["discount_pct"] = Decimal(str(discount)).quantize(_DISCOUNT_QUANTIZE)
            # ``ck_promotion_bundle_members_consistency`` allows either
            # discount on a bundle/BOGO row, but PromotionGenerator picks
            # exactly one of ``discount_pct`` / ``discount_amount`` per
            # source row. We always use ``discount_pct`` for bundles, so
            # clear any prior amount to keep the row internally tidy.
            record["discount_amount"] = None
            record["bundle_member_product_ids"] = members

        return promotions
