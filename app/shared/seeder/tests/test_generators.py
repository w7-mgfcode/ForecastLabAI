"""Tests for data generators."""

import random
from datetime import date
from decimal import Decimal

from app.shared.seeder.config import HolidayConfig, SparsityConfig
from app.shared.seeder.generators import (
    CalendarGenerator,
    InventorySnapshotGenerator,
    PriceHistoryGenerator,
    ProductGenerator,
    PromotionGenerator,
    SalesDailyGenerator,
    StoreGenerator,
)


class TestStoreGenerator:
    """Tests for StoreGenerator."""

    def test_generates_correct_count(self, rng, dimension_config):
        """Test generator produces correct number of stores."""
        gen = StoreGenerator(rng, dimension_config)
        stores = gen.generate()

        assert len(stores) == dimension_config.stores

    def test_unique_store_codes(self, rng, dimension_config):
        """Test all store codes are unique."""
        gen = StoreGenerator(rng, dimension_config)
        stores = gen.generate()

        codes = [s["code"] for s in stores]
        assert len(codes) == len(set(codes))

    def test_store_code_format(self, rng, dimension_config):
        """Test store codes follow expected format."""
        gen = StoreGenerator(rng, dimension_config)
        stores = gen.generate()

        for store in stores:
            assert store["code"].startswith("S")
            assert len(store["code"]) == 5  # S + 4 digits

    def test_regions_from_config(self, rng, dimension_config):
        """Test stores use regions from config."""
        gen = StoreGenerator(rng, dimension_config)
        stores = gen.generate()

        for store in stores:
            assert store["region"] in dimension_config.store_regions

    def test_store_types_from_config(self, rng, dimension_config):
        """Test stores use types from config."""
        gen = StoreGenerator(rng, dimension_config)
        stores = gen.generate()

        for store in stores:
            assert store["store_type"] in dimension_config.store_types

    def test_reproducibility(self, dimension_config):
        """Test same seed produces same stores."""
        rng1 = random.Random(42)
        rng2 = random.Random(42)

        gen1 = StoreGenerator(rng1, dimension_config)
        gen2 = StoreGenerator(rng2, dimension_config)

        stores1 = gen1.generate()
        stores2 = gen2.generate()

        assert stores1 == stores2


class TestProductGenerator:
    """Tests for ProductGenerator."""

    def test_generates_correct_count(self, rng, dimension_config):
        """Test generator produces correct number of products."""
        gen = ProductGenerator(rng, dimension_config)
        products = gen.generate()

        assert len(products) == dimension_config.products

    def test_unique_skus(self, rng, dimension_config):
        """Test all SKUs are unique."""
        gen = ProductGenerator(rng, dimension_config)
        products = gen.generate()

        skus = [p["sku"] for p in products]
        assert len(skus) == len(set(skus))

    def test_sku_format(self, rng, dimension_config):
        """Test SKU follows expected format."""
        gen = ProductGenerator(rng, dimension_config)
        products = gen.generate()

        for product in products:
            assert product["sku"].startswith("SKU-")
            assert len(product["sku"]) == 9  # SKU- + 5 digits

    def test_valid_prices(self, rng, dimension_config):
        """Test prices are positive and cost < price."""
        gen = ProductGenerator(rng, dimension_config)
        products = gen.generate()

        for product in products:
            assert product["base_price"] > 0
            assert product["base_cost"] > 0
            assert product["base_cost"] < product["base_price"]

    def test_categories_from_config(self, rng, dimension_config):
        """Test products use categories from config."""
        gen = ProductGenerator(rng, dimension_config)
        products = gen.generate()

        for product in products:
            assert product["category"] in dimension_config.product_categories


class TestCalendarGenerator:
    """Tests for CalendarGenerator."""

    def test_generates_full_date_range(self):
        """Test generator covers entire date range."""
        start = date(2024, 1, 1)
        end = date(2024, 1, 31)
        gen = CalendarGenerator(start, end)
        calendar = gen.generate()

        assert len(calendar) == 31  # January has 31 days
        assert calendar[0]["date"] == start
        assert calendar[-1]["date"] == end

    def test_day_of_week_correct(self):
        """Test day_of_week values are correct."""
        start = date(2024, 1, 1)  # Monday
        end = date(2024, 1, 7)  # Sunday
        gen = CalendarGenerator(start, end)
        calendar = gen.generate()

        assert calendar[0]["day_of_week"] == 0  # Monday
        assert calendar[6]["day_of_week"] == 6  # Sunday

    def test_month_quarter_year(self):
        """Test month, quarter, year values are correct."""
        start = date(2024, 12, 15)
        end = date(2024, 12, 15)
        gen = CalendarGenerator(start, end)
        calendar = gen.generate()

        assert calendar[0]["month"] == 12
        assert calendar[0]["quarter"] == 4
        assert calendar[0]["year"] == 2024

    def test_custom_holidays(self):
        """Test custom holidays are included."""
        start = date(2024, 12, 24)
        end = date(2024, 12, 26)
        holidays = [
            HolidayConfig(date(2024, 12, 25), "Custom Holiday", 1.0),
        ]
        gen = CalendarGenerator(start, end, holidays)
        calendar = gen.generate()

        christmas = next(c for c in calendar if c["date"] == date(2024, 12, 25))
        assert christmas["is_holiday"] is True
        assert christmas["holiday_name"] == "Custom Holiday"

    def test_us_holidays_included(self):
        """Test US federal holidays are included."""
        start = date(2024, 7, 4)
        end = date(2024, 7, 4)
        gen = CalendarGenerator(start, end)
        calendar = gen.generate()

        assert calendar[0]["is_holiday"] is True
        assert calendar[0]["holiday_name"] == "Independence Day"


class TestSalesDailyGenerator:
    """Tests for SalesDailyGenerator."""

    def test_generates_sales(self, rng, time_series_config, retail_config, sparsity_config):
        """Test generator produces sales records."""
        gen = SalesDailyGenerator(rng, time_series_config, retail_config, sparsity_config, [])

        store_ids = [1, 2]
        product_data = [(1, Decimal("9.99")), (2, Decimal("4.99"))]
        dates = [date(2024, 1, 1), date(2024, 1, 2)]

        sales = gen.generate(store_ids, product_data, dates, {}, {})

        # Should have records for each store/product/date combo
        assert len(sales) == len(store_ids) * len(product_data) * len(dates)

    def test_non_negative_quantities(self, rng, time_series_config, retail_config, sparsity_config):
        """Test all quantities are non-negative."""
        gen = SalesDailyGenerator(rng, time_series_config, retail_config, sparsity_config, [])

        store_ids = [1]
        product_data = [(1, Decimal("9.99"))]
        dates = [date(2024, 1, d) for d in range(1, 32)]

        sales = gen.generate(store_ids, product_data, dates, {}, {})

        for sale in sales:
            assert sale["quantity"] >= 0

    def test_stockout_zero_sales(self, rng, time_series_config, retail_config, sparsity_config):
        """Test stockout produces zero or missing sales."""
        retail_config.stockout_behavior = "zero"
        gen = SalesDailyGenerator(rng, time_series_config, retail_config, sparsity_config, [])

        store_ids = [1]
        product_data = [(1, Decimal("9.99"))]
        dates = [date(2024, 1, 1)]
        stockouts = {(1, 1): {date(2024, 1, 1)}}

        sales = gen.generate(store_ids, product_data, dates, {}, stockouts)

        # Stockout should result in no sales record (skipped)
        assert len(sales) == 0

    def test_total_amount_calculation(
        self, rng, time_series_config, retail_config, sparsity_config
    ):
        """Test total_amount = unit_price * quantity."""
        gen = SalesDailyGenerator(rng, time_series_config, retail_config, sparsity_config, [])

        store_ids = [1]
        product_data = [(1, Decimal("10.00"))]
        dates = [date(2024, 1, 1)]

        sales = gen.generate(store_ids, product_data, dates, {}, {})

        for sale in sales:
            expected_total = sale["unit_price"] * sale["quantity"]
            assert sale["total_amount"] == expected_total

    def test_sparsity_reduces_combinations(self, rng, time_series_config, retail_config):
        """Test sparsity config reduces active combinations."""
        sparsity = SparsityConfig(missing_combinations_pct=0.5)
        gen = SalesDailyGenerator(rng, time_series_config, retail_config, sparsity, [])

        store_ids = [1, 2, 3, 4]
        product_data = [(i, Decimal("9.99")) for i in range(1, 5)]
        dates = [date(2024, 1, 1)]

        sales = gen.generate(store_ids, product_data, dates, {}, {})

        # With 50% sparsity, expect roughly half the combinations
        max_sales = len(store_ids) * len(product_data) * len(dates)
        assert len(sales) < max_sales


class TestInventorySnapshotGenerator:
    """Tests for InventorySnapshotGenerator."""

    def test_generates_snapshots(self, rng):
        """Test generator produces inventory snapshots."""
        gen = InventorySnapshotGenerator(rng, stockout_probability=0.0)

        store_ids = [1, 2]
        product_ids = [1, 2, 3]
        dates = [date(2024, 1, 1), date(2024, 1, 2)]

        records, _stockouts = gen.generate(store_ids, product_ids, dates)

        expected_count = len(store_ids) * len(product_ids) * len(dates)
        assert len(records) == expected_count

    def test_non_negative_quantities(self, rng):
        """Test all quantities are non-negative."""
        gen = InventorySnapshotGenerator(rng)

        store_ids = [1]
        product_ids = [1]
        dates = [date(2024, 1, d) for d in range(1, 15)]

        records, _ = gen.generate(store_ids, product_ids, dates)

        for record in records:
            assert record["on_hand_qty"] >= 0
            assert record["on_order_qty"] >= 0


class TestPromotionGenerator:
    """Tests for PromotionGenerator."""

    def test_generates_promotions(self, rng):
        """Test generator produces promotions."""
        gen = PromotionGenerator(rng, promotion_probability=0.5)

        product_ids = [1, 2, 3]
        store_ids = [1, 2]
        start = date(2024, 1, 1)
        end = date(2024, 3, 31)

        records, _promo_dates = gen.generate(product_ids, store_ids, start, end)

        # With high probability, should generate some promotions
        assert len(records) > 0

    def test_valid_date_ranges(self, rng):
        """Test promotion end_date >= start_date."""
        gen = PromotionGenerator(rng, promotion_probability=0.3)

        product_ids = [1]
        store_ids = [1]
        start = date(2024, 1, 1)
        end = date(2024, 6, 30)

        records, _ = gen.generate(product_ids, store_ids, start, end)

        for record in records:
            assert record["end_date"] >= record["start_date"]

    def test_valid_discount_values(self, rng):
        """Test discount values are valid."""
        gen = PromotionGenerator(rng, promotion_probability=0.5)

        product_ids = [1, 2, 3]
        store_ids = [1]
        start = date(2024, 1, 1)
        end = date(2024, 3, 31)

        records, _ = gen.generate(product_ids, store_ids, start, end)

        for record in records:
            if record["discount_pct"] is not None:
                assert 0 <= record["discount_pct"] <= 1
            if record["discount_amount"] is not None:
                assert record["discount_amount"] >= 0


class TestPriceHistoryGenerator:
    """Tests for PriceHistoryGenerator."""

    def test_generates_price_history(self, rng):
        """Test generator produces price history records."""
        gen = PriceHistoryGenerator(rng, price_change_probability=0.2)

        product_data = [(1, Decimal("9.99")), (2, Decimal("4.99"))]
        store_ids = [1, 2]
        start = date(2024, 1, 1)
        end = date(2024, 6, 30)

        records = gen.generate(product_data, store_ids, start, end)

        # Should have at least one record per product
        assert len(records) >= len(product_data)

    def test_valid_price_windows(self, rng):
        """Test price validity windows don't overlap."""
        gen = PriceHistoryGenerator(rng, price_change_probability=0.1)

        product_data = [(1, Decimal("9.99"))]
        store_ids = [1]
        start = date(2024, 1, 1)
        end = date(2024, 12, 31)

        records = gen.generate(product_data, store_ids, start, end)

        # Filter records for product 1
        product_records = [r for r in records if r["product_id"] == 1]

        # Sort by valid_from
        product_records.sort(key=lambda r: r["valid_from"])

        # Check no overlaps
        for i in range(len(product_records) - 1):
            current = product_records[i]
            next_record = product_records[i + 1]

            if current["valid_to"] is not None:
                assert current["valid_to"] < next_record["valid_from"]

    def test_positive_prices(self, rng):
        """Test all prices are positive."""
        gen = PriceHistoryGenerator(rng, price_change_probability=0.3)

        product_data = [(1, Decimal("9.99"))]
        store_ids = [1]
        start = date(2024, 1, 1)
        end = date(2024, 12, 31)

        records = gen.generate(product_data, store_ids, start, end)

        for record in records:
            assert record["price"] > 0
