"""Tests for Phase 2 MarkdownGenerator (clearance pricing).

Regression invariant: with ``MarkdownConfig.enable=False`` (default)
``MarkdownGenerator.generate`` returns empty containers and consumes
zero rng state. Enabled paths are deterministic — no rng draws even
with the generator on — so reproducibility falls out automatically.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.shared.seeder.config import LifecycleConfig, MarkdownConfig
from app.shared.seeder.generators.lifecycle import LifecycleGenerator
from app.shared.seeder.generators.markdowns import MarkdownGenerator

# ---------------------------------------------------------------------- #
# Fixtures
# ---------------------------------------------------------------------- #


def _dates(start: date, days: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(days)]


def _product_specs() -> list[dict[str, Any]]:
    """Four products: ids 1-4, varying launch dates for decline detection."""
    return [
        {
            "product_id": 1,
            "base_price": Decimal("10.00"),
            "launch_date": date(2023, 1, 1),  # launched a year before seeded range
            "discontinue_date": None,
        },
        {
            "product_id": 2,
            "base_price": Decimal("20.00"),
            "launch_date": date(2024, 1, 1),  # launches with the range
            "discontinue_date": None,
        },
        {
            "product_id": 3,
            "base_price": Decimal("5.00"),
            "launch_date": None,  # no lifecycle data
            "discontinue_date": None,
        },
        {
            "product_id": 4,
            "base_price": Decimal("15.00"),
            "launch_date": date(2024, 6, 1),  # launches mid-range
            "discontinue_date": None,
        },
    ]


def _lifecycle_enabled() -> LifecycleGenerator:
    """LifecycleGenerator tuned so product #1 hits decline early in 2024."""
    cfg = LifecycleConfig(
        enable=True,
        intro_ramp_days=30,
        growth_ramp_days=60,
        maturity_steady_days=180,
        decline_decay_days=90,
    )
    return LifecycleGenerator(cfg)


# ---------------------------------------------------------------------- #
# Disabled / regression invariant
# ---------------------------------------------------------------------- #


class TestMarkdownGeneratorDisabled:
    def test_enabled_false_when_config_none(self) -> None:
        assert MarkdownGenerator(random.Random(0), None).enabled is False

    def test_enabled_false_when_config_default(self) -> None:
        assert MarkdownGenerator(random.Random(0), MarkdownConfig()).enabled is False

    def test_empty_output_when_config_none(self) -> None:
        rng = random.Random(42)
        baseline_state = rng.getstate()
        promos, prices, md_dates = MarkdownGenerator(rng, None).generate(
            product_specs=_product_specs(),
            store_ids=[1, 2, 3],
            stockout_dates={(1, 1): {date(2024, 3, 15)}},
            dates=_dates(date(2024, 1, 1), 90),
            lifecycle=_lifecycle_enabled(),
        )
        assert promos == [] and prices == [] and md_dates == {}
        assert rng.getstate() == baseline_state  # no rng consumption

    def test_empty_output_when_disabled_config(self) -> None:
        rng = random.Random(42)
        baseline_state = rng.getstate()
        promos, prices, md_dates = MarkdownGenerator(rng, MarkdownConfig()).generate(
            product_specs=_product_specs(),
            store_ids=[1, 2, 3],
            stockout_dates={(1, 1): {date(2024, 3, 15)}},
            dates=_dates(date(2024, 1, 1), 90),
            lifecycle=_lifecycle_enabled(),
        )
        assert promos == [] and prices == [] and md_dates == {}
        assert rng.getstate() == baseline_state


# ---------------------------------------------------------------------- #
# lifecycle_decline trigger
# ---------------------------------------------------------------------- #


class TestLifecycleDeclineTrigger:
    def _cfg(self, **overrides: Any) -> MarkdownConfig:
        kwargs: dict[str, Any] = {
            "enable": True,
            "trigger": "lifecycle_decline",
            "markdown_depth_pct": 0.30,
            "markdown_duration_days": 14,
        }
        kwargs.update(overrides)
        return MarkdownConfig(**kwargs)

    def test_fires_chainwide_for_declining_products(self) -> None:
        # Product #1 launched 2023-01-01; with default ramp+steady=270 days
        # it enters decline ~2023-09-28, so it is *already* in decline on
        # 2024-01-01 (first date of the seeded range).
        promos, prices, md_dates = MarkdownGenerator(random.Random(0), self._cfg()).generate(
            product_specs=_product_specs(),
            store_ids=[10, 20, 30],
            stockout_dates={},
            dates=_dates(date(2024, 1, 1), 365),
            lifecycle=_lifecycle_enabled(),
        )

        # Product #1 should produce one chain-wide markdown.
        product_1_promos = [p for p in promos if p["product_id"] == 1]
        assert len(product_1_promos) == 1
        p = product_1_promos[0]
        assert p["store_id"] is None
        assert p["kind"] == "markdown"
        assert p["bundle_member_product_ids"] is None
        assert p["discount_pct"] == Decimal("0.3000")
        assert p["discount_amount"] is None
        # First decline date == seeded range start because product launched in 2023.
        assert p["start_date"] == date(2024, 1, 1)
        assert p["end_date"] == date(2024, 1, 14)

        # Companion price_history drop.
        product_1_prices = [r for r in prices if r["product_id"] == 1]
        assert len(product_1_prices) == 1
        ph = product_1_prices[0]
        assert ph["store_id"] is None
        # base_price 10.00 * (1 - 0.3) = 7.00.
        assert ph["price"] == Decimal("7.00")
        assert ph["valid_from"] == date(2024, 1, 1)
        assert ph["valid_to"] == date(2024, 1, 14)

        # markdown_dates populated per store for product #1.
        for sid in (10, 20, 30):
            assert (sid, 1) in md_dates
            assert md_dates[(sid, 1)] == set(_dates(date(2024, 1, 1), 14))

    def test_skips_products_without_lifecycle_data(self) -> None:
        promos, prices, md_dates = MarkdownGenerator(random.Random(0), self._cfg()).generate(
            product_specs=_product_specs(),
            store_ids=[10],
            stockout_dates={},
            dates=_dates(date(2024, 1, 1), 365),
            lifecycle=_lifecycle_enabled(),
        )
        # Product #3 has launch_date=None — never fires.
        assert all(p["product_id"] != 3 for p in promos)
        assert all(r["product_id"] != 3 for r in prices)
        assert all(key[1] != 3 for key in md_dates)

    def test_no_output_when_lifecycle_disabled(self) -> None:
        promos, prices, md_dates = MarkdownGenerator(random.Random(0), self._cfg()).generate(
            product_specs=_product_specs(),
            store_ids=[10],
            stockout_dates={},
            dates=_dates(date(2024, 1, 1), 365),
            lifecycle=LifecycleGenerator(None),  # disabled
        )
        assert promos == [] and prices == [] and md_dates == {}

    def test_no_output_when_no_product_in_decline(self) -> None:
        # Product #4 launches mid-2024 → with default ramp+steady=270d it
        # only enters decline in 2025. Within a 60-day window it never fires.
        promos, prices, _ = MarkdownGenerator(random.Random(0), self._cfg()).generate(
            product_specs=[_product_specs()[3]],  # only product #4
            store_ids=[10],
            stockout_dates={},
            dates=_dates(date(2024, 6, 1), 60),
            lifecycle=_lifecycle_enabled(),
        )
        assert promos == [] and prices == []

    def test_md_end_clamped_to_seeded_range(self) -> None:
        # Use only 5 days of seeded range so 14-day markdown gets clipped.
        promos, _, _ = MarkdownGenerator(
            random.Random(0), self._cfg(markdown_duration_days=14)
        ).generate(
            product_specs=[_product_specs()[0]],  # product #1, already in decline
            store_ids=[10],
            stockout_dates={},
            dates=_dates(date(2024, 1, 1), 5),
            lifecycle=_lifecycle_enabled(),
        )
        assert len(promos) == 1
        assert promos[0]["start_date"] == date(2024, 1, 1)
        assert promos[0]["end_date"] == date(2024, 1, 5)  # clamped


# ---------------------------------------------------------------------- #
# stockout_risk trigger
# ---------------------------------------------------------------------- #


class TestStockoutRiskTrigger:
    def _cfg(self, **overrides: Any) -> MarkdownConfig:
        kwargs: dict[str, Any] = {
            "enable": True,
            "trigger": "stockout_risk",
            "markdown_depth_pct": 0.25,
            "markdown_duration_days": 7,
        }
        kwargs.update(overrides)
        return MarkdownConfig(**kwargs)

    def test_markdown_ends_day_before_stockout(self) -> None:
        promos, prices, md_dates = MarkdownGenerator(random.Random(0), self._cfg()).generate(
            product_specs=_product_specs(),
            store_ids=[10, 20],
            stockout_dates={(10, 1): {date(2024, 3, 15)}},
            dates=_dates(date(2024, 1, 1), 90),
            lifecycle=None,  # not used for stockout_risk
        )
        assert len(promos) == 1
        p = promos[0]
        assert p["store_id"] == 10
        assert p["product_id"] == 1
        assert p["kind"] == "markdown"
        assert p["bundle_member_product_ids"] is None
        assert p["discount_pct"] == Decimal("0.2500")
        assert p["end_date"] == date(2024, 3, 14)
        assert p["start_date"] == date(2024, 3, 8)  # 7-day window

        # 10.00 * (1 - 0.25) = 7.50.
        assert prices[0]["price"] == Decimal("7.50")
        assert md_dates[(10, 1)] == set(_dates(date(2024, 3, 8), 7))

    def test_dedupe_overlapping_stockouts(self) -> None:
        # Three stockouts within a 7-day window: only the first should fire.
        promos, _, _ = MarkdownGenerator(random.Random(0), self._cfg()).generate(
            product_specs=_product_specs(),
            store_ids=[10],
            stockout_dates={
                (10, 1): {
                    date(2024, 3, 15),
                    date(2024, 3, 17),
                    date(2024, 3, 18),
                }
            },
            dates=_dates(date(2024, 1, 1), 90),
        )
        assert len(promos) == 1
        assert promos[0]["end_date"] == date(2024, 3, 14)

    def test_clamps_to_first_date_when_stockout_near_start(self) -> None:
        promos, _, _ = MarkdownGenerator(
            random.Random(0), self._cfg(markdown_duration_days=14)
        ).generate(
            product_specs=_product_specs(),
            store_ids=[10],
            stockout_dates={(10, 1): {date(2024, 1, 5)}},
            dates=_dates(date(2024, 1, 1), 30),
        )
        assert len(promos) == 1
        assert promos[0]["start_date"] == date(2024, 1, 1)  # clamped
        assert promos[0]["end_date"] == date(2024, 1, 4)

    def test_skips_stockout_on_first_date(self) -> None:
        # Stockout on day 1 leaves no room for a markdown window.
        promos, prices, md_dates = MarkdownGenerator(random.Random(0), self._cfg()).generate(
            product_specs=_product_specs(),
            store_ids=[10],
            stockout_dates={(10, 1): {date(2024, 1, 1)}},
            dates=_dates(date(2024, 1, 1), 30),
        )
        assert promos == [] and prices == [] and md_dates == {}

    def test_per_store_markdowns(self) -> None:
        # Two stores stocked out for product 1 → two distinct markdowns.
        promos, _, _ = MarkdownGenerator(random.Random(0), self._cfg()).generate(
            product_specs=_product_specs(),
            store_ids=[10, 20],
            stockout_dates={
                (10, 1): {date(2024, 3, 15)},
                (20, 1): {date(2024, 3, 20)},
            },
            dates=_dates(date(2024, 1, 1), 90),
        )
        assert len(promos) == 2
        store_ids = {p["store_id"] for p in promos}
        assert store_ids == {10, 20}

    def test_unknown_product_silently_skipped(self) -> None:
        promos, _, _ = MarkdownGenerator(random.Random(0), self._cfg()).generate(
            product_specs=_product_specs(),  # ids 1-4
            store_ids=[10],
            stockout_dates={(10, 99): {date(2024, 3, 15)}},
            dates=_dates(date(2024, 1, 1), 90),
        )
        assert promos == []

    def test_deterministic_output_order(self) -> None:
        cfg = self._cfg()
        specs = _product_specs()
        dates_ = _dates(date(2024, 1, 1), 90)
        # Build stockouts in two different dict orders.
        stockouts_a = {
            (20, 2): {date(2024, 3, 10)},
            (10, 1): {date(2024, 3, 15)},
        }
        stockouts_b = {
            (10, 1): {date(2024, 3, 15)},
            (20, 2): {date(2024, 3, 10)},
        }
        promos_a, _, _ = MarkdownGenerator(random.Random(0), cfg).generate(
            product_specs=specs,
            store_ids=[10, 20],
            stockout_dates=stockouts_a,
            dates=dates_,
        )
        promos_b, _, _ = MarkdownGenerator(random.Random(0), cfg).generate(
            product_specs=specs,
            store_ids=[10, 20],
            stockout_dates=stockouts_b,
            dates=dates_,
        )
        assert promos_a == promos_b


# ---------------------------------------------------------------------- #
# Validation
# ---------------------------------------------------------------------- #


class TestMarkdownGeneratorValidation:
    def test_age_days_trigger_raises_not_implemented(self) -> None:
        gen = MarkdownGenerator(
            random.Random(0),
            MarkdownConfig(enable=True, trigger="age_days"),
        )
        with pytest.raises(NotImplementedError, match="#94"):
            gen.generate(
                product_specs=_product_specs(),
                store_ids=[10],
                stockout_dates={},
                dates=_dates(date(2024, 1, 1), 30),
            )

    def test_depth_pct_below_zero_raises(self) -> None:
        gen = MarkdownGenerator(
            random.Random(0),
            MarkdownConfig(enable=True, markdown_depth_pct=-0.1),
        )
        with pytest.raises(ValueError, match="markdown_depth_pct"):
            gen.generate(
                product_specs=_product_specs(),
                store_ids=[10],
                stockout_dates={},
                dates=_dates(date(2024, 1, 1), 30),
            )

    def test_depth_pct_above_one_raises(self) -> None:
        gen = MarkdownGenerator(
            random.Random(0),
            MarkdownConfig(enable=True, markdown_depth_pct=1.5),
        )
        with pytest.raises(ValueError, match="markdown_depth_pct"):
            gen.generate(
                product_specs=_product_specs(),
                store_ids=[10],
                stockout_dates={},
                dates=_dates(date(2024, 1, 1), 30),
            )

    def test_zero_duration_raises(self) -> None:
        gen = MarkdownGenerator(
            random.Random(0),
            MarkdownConfig(enable=True, markdown_duration_days=0),
        )
        with pytest.raises(ValueError, match="markdown_duration_days"):
            gen.generate(
                product_specs=_product_specs(),
                store_ids=[10],
                stockout_dates={},
                dates=_dates(date(2024, 1, 1), 30),
            )

    def test_no_rng_consumption_enabled_path(self) -> None:
        """Enabled generator is deterministic — rng should be untouched."""
        rng = random.Random(42)
        baseline_state = rng.getstate()
        MarkdownGenerator(
            rng,
            MarkdownConfig(enable=True, trigger="stockout_risk"),
        ).generate(
            product_specs=_product_specs(),
            store_ids=[10],
            stockout_dates={(10, 1): {date(2024, 3, 15)}},
            dates=_dates(date(2024, 1, 1), 90),
        )
        assert rng.getstate() == baseline_state
