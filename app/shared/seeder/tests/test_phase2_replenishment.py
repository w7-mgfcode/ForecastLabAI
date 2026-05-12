"""Tests for Phase 2 ReplenishmentGenerator.

Regression invariant: with ``LeadTimeConfig.enable=False`` (default)
``ReplenishmentGenerator.generate`` returns ``[]`` and consumes zero
rng state.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

import pytest

from app.shared.seeder.config import LeadTimeConfig
from app.shared.seeder.generators.replenishment import ReplenishmentGenerator


def _dates(start: date, days: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(days)]


# ---------------------------------------------------------------------- #
# Disabled / regression invariant
# ---------------------------------------------------------------------- #


class TestReplenishmentGeneratorDisabled:
    def test_enabled_false_when_config_none(self) -> None:
        assert ReplenishmentGenerator(random.Random(0), None).enabled is False

    def test_enabled_false_when_config_default(self) -> None:
        assert ReplenishmentGenerator(random.Random(0), LeadTimeConfig()).enabled is False

    def test_empty_output_when_config_none(self) -> None:
        rng = random.Random(42)
        baseline_state = rng.getstate()
        out = ReplenishmentGenerator(rng, None).generate(
            [1, 2], [10, 20], _dates(date(2024, 1, 1), 90)
        )
        assert out == []
        assert rng.getstate() == baseline_state

    def test_empty_output_when_disabled_config(self) -> None:
        rng = random.Random(42)
        baseline_state = rng.getstate()
        out = ReplenishmentGenerator(rng, LeadTimeConfig()).generate(
            [1, 2], [10, 20], _dates(date(2024, 1, 1), 90)
        )
        assert out == []
        assert rng.getstate() == baseline_state


# ---------------------------------------------------------------------- #
# Enabled-path correctness
# ---------------------------------------------------------------------- #


class TestReplenishmentGeneratorEnabled:
    def _cfg(self, **overrides: Any) -> LeadTimeConfig:
        kwargs: dict[str, Any] = {
            "enable": True,
            "mean_lead_time_days": 7,
            "lead_time_sigma_days": 1.5,
            "safety_stock_days": 3,
            "order_frequency_days": 14,
            "fill_rate_mean": 0.97,
            "fill_rate_sigma": 0.05,
        }
        kwargs.update(overrides)
        return LeadTimeConfig(**kwargs)

    def test_record_shape_and_invariants(self) -> None:
        out = ReplenishmentGenerator(random.Random(0), self._cfg()).generate(
            [1, 2], [10, 20], _dates(date(2024, 1, 1), 90), base_demand=100
        )
        assert len(out) > 0
        for r in out:
            assert set(r.keys()) == {
                "date",
                "store_id",
                "product_id",
                "lead_time_days",
                "ordered_qty",
                "received_qty",
            }
            assert isinstance(r["date"], date)
            assert r["store_id"] in (1, 2)
            assert r["product_id"] in (10, 20)
            assert r["lead_time_days"] >= 0
            assert r["ordered_qty"] >= 0
            assert 0 <= r["received_qty"] <= r["ordered_qty"]

    def test_ordered_qty_formula(self) -> None:
        # base_demand=100, order_freq=14, safety=3 → ordered = 100*17 = 1700.
        out = ReplenishmentGenerator(random.Random(0), self._cfg()).generate(
            [1], [10], _dates(date(2024, 1, 1), 90), base_demand=100
        )
        assert all(r["ordered_qty"] == 1700 for r in out)

    def test_dates_within_seeded_range(self) -> None:
        dates_ = _dates(date(2024, 1, 1), 365)
        out = ReplenishmentGenerator(random.Random(0), self._cfg()).generate(
            [1], [10], dates_, base_demand=100
        )
        for r in out:
            assert dates_[0] <= r["date"] <= dates_[-1]

    def test_reproducible_with_same_seed(self) -> None:
        cfg = self._cfg()
        a = ReplenishmentGenerator(random.Random(42), cfg).generate(
            [1, 2], [10, 20], _dates(date(2024, 1, 1), 90)
        )
        b = ReplenishmentGenerator(random.Random(42), cfg).generate(
            [1, 2], [10, 20], _dates(date(2024, 1, 1), 90)
        )
        assert a == b

    def test_input_order_does_not_affect_output(self) -> None:
        cfg = self._cfg()
        a = ReplenishmentGenerator(random.Random(42), cfg).generate(
            [1, 2], [10, 20], _dates(date(2024, 1, 1), 90)
        )
        b = ReplenishmentGenerator(random.Random(42), cfg).generate(
            [2, 1], [20, 10], _dates(date(2024, 1, 1), 90)
        )
        assert a == b

    def test_empty_dates_returns_empty(self) -> None:
        out = ReplenishmentGenerator(random.Random(0), self._cfg()).generate([1], [10], [])
        assert out == []

    def test_high_fill_rate_yields_full_orders(self) -> None:
        cfg = self._cfg(fill_rate_mean=1.0, fill_rate_sigma=0.0)
        out = ReplenishmentGenerator(random.Random(0), cfg).generate(
            [1], [10], _dates(date(2024, 1, 1), 90)
        )
        assert len(out) > 0
        for r in out:
            assert r["received_qty"] == r["ordered_qty"]

    def test_zero_fill_rate_yields_zero_received(self) -> None:
        cfg = self._cfg(fill_rate_mean=0.0, fill_rate_sigma=0.0)
        out = ReplenishmentGenerator(random.Random(0), cfg).generate(
            [1], [10], _dates(date(2024, 1, 1), 90)
        )
        assert len(out) > 0
        for r in out:
            assert r["received_qty"] == 0

    def test_zero_lead_time_gives_immediate_receipt(self) -> None:
        cfg = self._cfg(mean_lead_time_days=0, lead_time_sigma_days=0.0)
        dates_ = _dates(date(2024, 1, 1), 84)
        out = ReplenishmentGenerator(random.Random(0), cfg).generate([1], [10], dates_)
        # 6 POs placed at days 0, 14, 28, 42, 56, 70 (day 84 > end day 83).
        assert len(out) == 6
        for r in out:
            assert r["lead_time_days"] == 0
            day_offset = (r["date"] - dates_[0]).days
            assert day_offset % cfg.order_frequency_days == 0

    def test_output_sorted_by_store_product_date(self) -> None:
        cfg = self._cfg(mean_lead_time_days=0, lead_time_sigma_days=0.0)
        out = ReplenishmentGenerator(random.Random(0), cfg).generate(
            [2, 1], [20, 10], _dates(date(2024, 1, 1), 90)
        )
        keys = [(r["store_id"], r["product_id"], r["date"]) for r in out]
        assert keys == sorted(keys)


# ---------------------------------------------------------------------- #
# Validation
# ---------------------------------------------------------------------- #


class TestReplenishmentGeneratorValidation:
    def test_negative_mean_lead_time_raises(self) -> None:
        gen = ReplenishmentGenerator(
            random.Random(0),
            LeadTimeConfig(enable=True, mean_lead_time_days=-1),
        )
        with pytest.raises(ValueError, match="mean_lead_time_days"):
            gen.generate([1], [1], _dates(date(2024, 1, 1), 30))

    def test_negative_lead_time_sigma_raises(self) -> None:
        gen = ReplenishmentGenerator(
            random.Random(0),
            LeadTimeConfig(enable=True, lead_time_sigma_days=-0.5),
        )
        with pytest.raises(ValueError, match="lead_time_sigma_days"):
            gen.generate([1], [1], _dates(date(2024, 1, 1), 30))

    def test_zero_order_frequency_raises(self) -> None:
        gen = ReplenishmentGenerator(
            random.Random(0),
            LeadTimeConfig(enable=True, order_frequency_days=0),
        )
        with pytest.raises(ValueError, match="order_frequency_days"):
            gen.generate([1], [1], _dates(date(2024, 1, 1), 30))

    def test_fill_rate_mean_above_one_raises(self) -> None:
        gen = ReplenishmentGenerator(
            random.Random(0),
            LeadTimeConfig(enable=True, fill_rate_mean=1.5),
        )
        with pytest.raises(ValueError, match="fill_rate_mean"):
            gen.generate([1], [1], _dates(date(2024, 1, 1), 30))

    def test_negative_fill_rate_sigma_raises(self) -> None:
        gen = ReplenishmentGenerator(
            random.Random(0),
            LeadTimeConfig(enable=True, fill_rate_sigma=-0.1),
        )
        with pytest.raises(ValueError, match="fill_rate_sigma"):
            gen.generate([1], [1], _dates(date(2024, 1, 1), 30))

    def test_negative_safety_stock_raises(self) -> None:
        gen = ReplenishmentGenerator(
            random.Random(0),
            LeadTimeConfig(enable=True, safety_stock_days=-1),
        )
        with pytest.raises(ValueError, match="safety_stock_days"):
            gen.generate([1], [1], _dates(date(2024, 1, 1), 30))

    def test_negative_base_demand_raises(self) -> None:
        gen = ReplenishmentGenerator(
            random.Random(0),
            LeadTimeConfig(enable=True),
        )
        with pytest.raises(ValueError, match="base_demand"):
            gen.generate([1], [1], _dates(date(2024, 1, 1), 30), base_demand=-10)
