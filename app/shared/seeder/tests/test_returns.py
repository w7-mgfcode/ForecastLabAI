"""Tests for ReturnsGenerator (Phase 1)."""

# mypy: disable-error-code="union-attr,arg-type,operator,return-value"

import random
from datetime import date, timedelta
from decimal import Decimal

from app.shared.seeder.config import ReturnsConfig
from app.shared.seeder.generators.returns import ReturnsGenerator


def _sales_records(n: int, start: date = date(2024, 1, 1)) -> list[dict[str, object]]:
    """Build n synthetic sales rows in the shape SalesDailyGenerator emits."""
    return [
        {
            "date": start + timedelta(days=i),
            "store_id": 1,
            "product_id": 100,
            "quantity": 10,
            "unit_price": Decimal("9.99"),
            "total_amount": Decimal("99.90"),
        }
        for i in range(n)
    ]


class TestReturnsGeneratorDisabled:
    def test_disabled_emits_nothing(self):
        gen = ReturnsGenerator(random.Random(42), ReturnsConfig(enable=False))
        assert gen.generate(_sales_records(50), date(2024, 1, 31)) == []


class TestReturnsGeneratorEnabled:
    def test_returns_fire_at_configured_rate(self):
        # Probability 1.0 means every sale generates a return.
        cfg = ReturnsConfig(enable=True, return_probability=1.0)
        gen = ReturnsGenerator(random.Random(0), cfg)
        sales = _sales_records(200)
        returns = gen.generate(sales, date(2024, 1, 31))
        assert len(returns) == 200

    def test_probability_zero_no_returns(self):
        cfg = ReturnsConfig(enable=True, return_probability=0.0)
        gen = ReturnsGenerator(random.Random(0), cfg)
        assert gen.generate(_sales_records(50), date(2024, 1, 31)) == []

    def test_return_quantity_is_positive_and_capped(self):
        # quantity_fraction=2.0 should be clamped to original quantity.
        cfg = ReturnsConfig(enable=True, return_probability=1.0, return_quantity_fraction=2.0)
        gen = ReturnsGenerator(random.Random(0), cfg)
        sales = _sales_records(20)
        returns = gen.generate(sales, date(2024, 1, 31))
        for r in returns:
            assert 1 <= r["return_quantity"] <= 10  # capped at sale quantity

    def test_return_date_clamped_to_end_date(self):
        cfg = ReturnsConfig(
            enable=True,
            return_probability=1.0,
            return_lag_days_min=30,
            return_lag_days_max=30,
        )
        gen = ReturnsGenerator(random.Random(0), cfg)
        sales = _sales_records(5, start=date(2024, 1, 20))
        end = date(2024, 1, 31)
        returns = gen.generate(sales, end)
        for r in returns:
            assert r["date"] <= end

    def test_reasons_drawn_from_distribution(self):
        cfg = ReturnsConfig(
            enable=True,
            return_probability=1.0,
            return_reason_distribution={"defective": 1.0},
        )
        gen = ReturnsGenerator(random.Random(0), cfg)
        sales = _sales_records(10)
        returns = gen.generate(sales, date(2024, 1, 31))
        assert all(r["return_reason"] == "defective" for r in returns)

    def test_reproducible(self):
        cfg = ReturnsConfig(enable=True, return_probability=0.5)
        sales = _sales_records(100)
        a = ReturnsGenerator(random.Random(7), cfg).generate(sales, date(2024, 12, 31))
        b = ReturnsGenerator(random.Random(7), cfg).generate(sales, date(2024, 12, 31))
        assert a == b

    def test_zero_quantity_sales_skipped(self):
        cfg = ReturnsConfig(enable=True, return_probability=1.0)
        gen = ReturnsGenerator(random.Random(0), cfg)
        sales = [
            {
                "date": date(2024, 1, 1),
                "store_id": 1,
                "product_id": 2,
                "quantity": 0,
                "unit_price": Decimal("9.99"),
                "total_amount": Decimal("0.00"),
            }
        ]
        assert gen.generate(sales, date(2024, 1, 31)) == []
