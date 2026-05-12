"""Tests for Phase 2 BundleGenerator promotion conversion.

The regression invariant is the most load-bearing assertion: with
``BundleConfig.enable=False`` (the default), ``BundleGenerator.apply``
must leave both the promotion list and the rng state byte-identical.
"""

from __future__ import annotations

import random
from copy import deepcopy
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.shared.seeder.config import BundleConfig
from app.shared.seeder.generators.bundles import BundleGenerator


def _sample_promotions() -> list[dict[str, Any]]:
    """Build a fixed sample of promotion records mimicking PromotionGenerator output."""
    return [
        {
            "product_id": 1,
            "store_id": None,
            "name": "Weekly Special",
            "discount_pct": Decimal("0.10"),
            "discount_amount": None,
            "start_date": date(2024, 1, 1),
            "end_date": date(2024, 1, 7),
        },
        {
            "product_id": 2,
            "store_id": 10,
            "name": "Flash Sale",
            "discount_pct": None,
            "discount_amount": Decimal("3.00"),
            "start_date": date(2024, 1, 5),
            "end_date": date(2024, 1, 12),
        },
        {
            "product_id": 3,
            "store_id": None,
            "name": "Clearance",
            "discount_pct": Decimal("0.20"),
            "discount_amount": None,
            "start_date": date(2024, 1, 10),
            "end_date": date(2024, 1, 17),
        },
        {
            "product_id": 4,
            "store_id": None,
            "name": "BOGO Deal",
            "discount_pct": Decimal("0.15"),
            "discount_amount": None,
            "start_date": date(2024, 1, 15),
            "end_date": date(2024, 1, 22),
        },
    ]


class TestBundleGeneratorDisabled:
    """Regression invariant: no mutation, no rng consumption when disabled."""

    def test_enabled_property_false_when_config_none(self) -> None:
        assert BundleGenerator(random.Random(0), None).enabled is False

    def test_enabled_property_false_when_config_default(self) -> None:
        assert BundleGenerator(random.Random(0), BundleConfig()).enabled is False

    def test_no_mutation_when_config_none(self) -> None:
        rng = random.Random(123)
        promos = _sample_promotions()
        snapshot = deepcopy(promos)
        result = BundleGenerator(rng, None).apply(promos, [1, 2, 3, 4, 5])
        assert result is promos
        assert result == snapshot

    def test_no_rng_consumption_when_config_none(self) -> None:
        rng = random.Random(42)
        baseline_state = rng.getstate()
        BundleGenerator(rng, None).apply(_sample_promotions(), [1, 2, 3, 4, 5])
        assert rng.getstate() == baseline_state

    def test_no_mutation_when_disabled_config(self) -> None:
        rng = random.Random(123)
        promos = _sample_promotions()
        snapshot = deepcopy(promos)
        BundleGenerator(rng, BundleConfig()).apply(promos, [1, 2, 3, 4, 5])
        assert promos == snapshot

    def test_no_rng_consumption_when_disabled_config(self) -> None:
        rng = random.Random(42)
        baseline_state = rng.getstate()
        BundleGenerator(rng, BundleConfig()).apply(_sample_promotions(), [1, 2, 3, 4, 5])
        assert rng.getstate() == baseline_state


class TestBundleGeneratorEnabled:
    """Enabled-path correctness: kinds, members, discounts, reproducibility."""

    def _cfg(self, **overrides: Any) -> BundleConfig:
        kwargs: dict[str, Any] = {
            "enable": True,
            "bundle_probability": 1.0,  # convert every promo for deterministic checks
            "bogo_share_within_bundles": 0.5,
            "min_bundle_size": 2,
            "max_bundle_size": 3,
            "bundle_discount_pct_min": 0.10,
            "bundle_discount_pct_max": 0.30,
        }
        kwargs.update(overrides)
        return BundleConfig(**kwargs)

    def test_kind_in_allowlist(self) -> None:
        promos = _sample_promotions()
        BundleGenerator(random.Random(7), self._cfg()).apply(promos, [1, 2, 3, 4, 5, 6])
        for p in promos:
            assert p["kind"] in ("bundle", "bogo")

    def test_members_drawn_from_pool_excluding_host(self) -> None:
        pool = [1, 2, 3, 4, 5, 6]
        promos = _sample_promotions()
        BundleGenerator(random.Random(11), self._cfg()).apply(promos, pool)
        for p in promos:
            members = p["bundle_member_product_ids"]
            assert isinstance(members, list)
            assert len(members) >= 2
            assert p["product_id"] not in members
            assert set(members).issubset(set(pool))
            assert len(set(members)) == len(members)

    def test_member_count_in_configured_range(self) -> None:
        promos = _sample_promotions()
        BundleGenerator(
            random.Random(13),
            self._cfg(min_bundle_size=2, max_bundle_size=4),
        ).apply(promos, [1, 2, 3, 4, 5, 6, 7])
        for p in promos:
            members = p["bundle_member_product_ids"]
            assert 2 <= len(members) <= 4

    def test_discount_pct_in_configured_range_and_amount_cleared(self) -> None:
        promos = _sample_promotions()
        BundleGenerator(
            random.Random(17),
            self._cfg(bundle_discount_pct_min=0.10, bundle_discount_pct_max=0.30),
        ).apply(promos, [1, 2, 3, 4, 5, 6])
        for p in promos:
            d = p["discount_pct"]
            assert isinstance(d, Decimal)
            assert Decimal("0.10") <= d <= Decimal("0.30")
            # Quantized to 4 decimal places to match ``Numeric(5, 4)``.
            exponent = d.as_tuple().exponent
            assert isinstance(exponent, int) and exponent == -4
            assert p["discount_amount"] is None

    def test_all_bogo_when_share_is_one(self) -> None:
        promos = _sample_promotions()
        BundleGenerator(random.Random(23), self._cfg(bogo_share_within_bundles=1.0)).apply(
            promos, [1, 2, 3, 4, 5, 6]
        )
        assert all(p["kind"] == "bogo" for p in promos)

    def test_all_bundle_when_share_is_zero(self) -> None:
        promos = _sample_promotions()
        BundleGenerator(random.Random(29), self._cfg(bogo_share_within_bundles=0.0)).apply(
            promos, [1, 2, 3, 4, 5, 6]
        )
        assert all(p["kind"] == "bundle" for p in promos)

    def test_zero_probability_leaves_records_unchanged(self) -> None:
        promos = _sample_promotions()
        snapshot = deepcopy(promos)
        BundleGenerator(random.Random(31), self._cfg(bundle_probability=0.0)).apply(
            promos, [1, 2, 3, 4, 5, 6]
        )
        assert promos == snapshot

    def test_reproducible_with_same_seed(self) -> None:
        cfg = self._cfg(bundle_probability=0.5)
        promos_a = _sample_promotions()
        promos_b = _sample_promotions()
        BundleGenerator(random.Random(42), cfg).apply(promos_a, [1, 2, 3, 4, 5])
        BundleGenerator(random.Random(42), cfg).apply(promos_b, [1, 2, 3, 4, 5])
        assert promos_a == promos_b

    def test_skips_when_pool_too_small_for_host(self) -> None:
        """Eligible pool below ``min_bundle_size`` → skip without rng consumption."""
        promos = _sample_promotions()
        snapshot = deepcopy(promos)
        rng = random.Random(37)
        baseline_state = rng.getstate()
        # Single-element pool: every host's eligible_pool has at most 1 element
        # which is below the default ``min_bundle_size=2`` — every promo skipped.
        BundleGenerator(rng, self._cfg(min_bundle_size=2)).apply(promos, [1])
        assert promos == snapshot
        assert rng.getstate() == baseline_state

    def test_max_clamps_to_eligible_pool_size(self) -> None:
        # min=2, max=10, pool=4 — each host excludes itself → 3 eligible.
        promos = _sample_promotions()
        BundleGenerator(
            random.Random(41),
            self._cfg(min_bundle_size=2, max_bundle_size=10),
        ).apply(promos, [1, 2, 3, 4])
        for p in promos:
            assert 2 <= len(p["bundle_member_product_ids"]) <= 3


class TestBundleGeneratorValidation:
    def test_min_bundle_size_below_two_raises(self) -> None:
        bg = BundleGenerator(
            random.Random(0),
            BundleConfig(enable=True, min_bundle_size=1),
        )
        with pytest.raises(ValueError, match="min_bundle_size must be >= 2"):
            bg.apply(_sample_promotions(), [1, 2, 3])

    def test_max_below_min_raises(self) -> None:
        bg = BundleGenerator(
            random.Random(0),
            BundleConfig(enable=True, min_bundle_size=3, max_bundle_size=2),
        )
        with pytest.raises(ValueError, match="max_bundle_size must be >="):
            bg.apply(_sample_promotions(), [1, 2, 3, 4, 5])
