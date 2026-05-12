"""Tests for Phase 1 SalesDailyGenerator demand-multiplier extensions.

Covers yearly seasonality, changepoints, weather-driven demand, and
substitution-on-stockout. The regression invariant — that disabling all
Phase 1 toggles produces byte-identical output to the pre-Phase-1 code
path — is verified in ``test_phase1_regression.py``.
"""

# mypy: disable-error-code="union-attr,arg-type,operator,return-value"

import math
import random
from datetime import date, timedelta
from decimal import Decimal

from app.shared.seeder.config import (
    ChangepointConfig,
    ChangepointEvent,
    MultiSeasonalityConfig,
    RetailPatternConfig,
    SparsityConfig,
    SubstitutionConfig,
    TimeSeriesConfig,
)
from app.shared.seeder.generators.facts import SalesDailyGenerator


def _deterministic_ts_config() -> TimeSeriesConfig:
    """A noise/anomaly-free config so multipliers can be asserted exactly."""
    return TimeSeriesConfig(
        base_demand=100,
        trend="none",
        weekly_seasonality=[1.0] * 7,
        monthly_seasonality={},
        noise_sigma=0.0,
        anomaly_probability=0.0,
    )


def _deterministic_retail_config() -> RetailPatternConfig:
    return RetailPatternConfig(
        promotion_lift=1.0,
        stockout_behavior="zero",
        price_elasticity=0.0,
        promotion_probability=0.0,
        stockout_probability=0.0,
    )


def _flat_sparsity() -> SparsityConfig:
    return SparsityConfig(missing_combinations_pct=0.0, random_gaps_per_series=0)


class TestYearlySeasonality:
    def test_amplitude_zero_no_effect(self):
        gen = SalesDailyGenerator(
            random.Random(0),
            _deterministic_ts_config(),
            _deterministic_retail_config(),
            _flat_sparsity(),
            [],
            multi_seasonality=MultiSeasonalityConfig(yearly_seasonality_amplitude=0.0),
        )
        # Demand = base_demand exactly under the deterministic config.
        assert gen._yearly_seasonality_multiplier(date(2024, 7, 1)) == 1.0

    def test_amplitude_nonzero_introduces_swing(self):
        cfg = MultiSeasonalityConfig(yearly_seasonality_amplitude=0.2)
        gen = SalesDailyGenerator(
            random.Random(0),
            _deterministic_ts_config(),
            _deterministic_retail_config(),
            _flat_sparsity(),
            [],
            multi_seasonality=cfg,
        )
        # On day-of-year 91 (≈ April 1) sin(2π · 91 / 365) ≈ 1; check sign.
        m_apr = gen._yearly_seasonality_multiplier(date(2024, 4, 1))
        m_oct = gen._yearly_seasonality_multiplier(date(2024, 10, 1))
        assert m_apr > 1.0
        assert m_oct < 1.0
        # Bounded by ±amplitude.
        assert 0.8 - 1e-9 <= m_oct <= 1.0
        assert 1.0 <= m_apr <= 1.2 + 1e-9


class TestChangepoints:
    def test_no_changepoints_returns_one(self):
        gen = SalesDailyGenerator(
            random.Random(0),
            _deterministic_ts_config(),
            _deterministic_retail_config(),
            _flat_sparsity(),
            [],
            changepoints=ChangepointConfig(changepoints=[]),
        )
        assert gen._changepoint_multiplier(date(2024, 6, 1)) == 1.0

    def test_impulse_decays_exponentially(self):
        cp = ChangepointEvent(date=date(2024, 6, 1), demand_multiplier=2.0, decay_days=10)
        gen = SalesDailyGenerator(
            random.Random(0),
            _deterministic_ts_config(),
            _deterministic_retail_config(),
            _flat_sparsity(),
            [],
            changepoints=ChangepointConfig(changepoints=[cp]),
        )
        # Day 0: multiplier == 2.0
        assert math.isclose(gen._changepoint_multiplier(date(2024, 6, 1)), 2.0)
        # Day 10: multiplier ≈ 1 + (2-1) * e^-1 ≈ 1.3679
        m10 = gen._changepoint_multiplier(date(2024, 6, 11))
        assert 1.35 < m10 < 1.40
        # Before the changepoint: 1.0
        assert gen._changepoint_multiplier(date(2024, 5, 31)) == 1.0

    def test_pure_impulse_zero_decay(self):
        cp = ChangepointEvent(date=date(2024, 6, 1), demand_multiplier=3.0, decay_days=0)
        gen = SalesDailyGenerator(
            random.Random(0),
            _deterministic_ts_config(),
            _deterministic_retail_config(),
            _flat_sparsity(),
            [],
            changepoints=ChangepointConfig(changepoints=[cp]),
        )
        assert gen._changepoint_multiplier(date(2024, 6, 1)) == 3.0
        assert gen._changepoint_multiplier(date(2024, 6, 2)) == 1.0


class TestWeatherMultiplier:
    def test_no_lookup_returns_one(self):
        gen = SalesDailyGenerator(
            random.Random(0),
            _deterministic_ts_config(),
            _deterministic_retail_config(),
            _flat_sparsity(),
            [],
            exogenous_weather=None,
            weather_temperature_sensitivity=0.01,
        )
        assert gen._weather_multiplier(date(2024, 7, 1), 1) == 1.0

    def test_sensitivity_zero_returns_one_even_with_lookup(self):
        gen = SalesDailyGenerator(
            random.Random(0),
            _deterministic_ts_config(),
            _deterministic_retail_config(),
            _flat_sparsity(),
            [],
            exogenous_weather={(1, date(2024, 7, 1)): 30.0},
            weather_temperature_sensitivity=0.0,
            weather_climatology_mean_c=15.0,
        )
        assert gen._weather_multiplier(date(2024, 7, 1), 1) == 1.0

    def test_warm_day_lifts_demand(self):
        gen = SalesDailyGenerator(
            random.Random(0),
            _deterministic_ts_config(),
            _deterministic_retail_config(),
            _flat_sparsity(),
            [],
            exogenous_weather={(1, date(2024, 7, 1)): 25.0},
            weather_temperature_sensitivity=0.02,
            weather_climatology_mean_c=15.0,
        )
        # 1 + 0.02 * (25 - 15) = 1.2
        assert math.isclose(gen._weather_multiplier(date(2024, 7, 1), 1), 1.2)


class TestSubstitution:
    def test_disabled_returns_one(self):
        sub = SubstitutionConfig(
            enable=False,
            substitute_groups=[[1, 2]],
            substitution_lift_on_stockout=0.5,
        )
        gen = SalesDailyGenerator(
            random.Random(0),
            _deterministic_ts_config(),
            _deterministic_retail_config(),
            _flat_sparsity(),
            [],
            substitution=sub,
        )
        assert gen._substitution_multiplier(1, {2}) == 1.0

    def test_no_group_member_returns_one(self):
        sub = SubstitutionConfig(
            enable=True,
            substitute_groups=[[1, 2]],
            substitution_lift_on_stockout=0.5,
        )
        gen = SalesDailyGenerator(
            random.Random(0),
            _deterministic_ts_config(),
            _deterministic_retail_config(),
            _flat_sparsity(),
            [],
            substitution=sub,
        )
        # Product 3 isn't in any group → no lift.
        assert gen._substitution_multiplier(3, {2}) == 1.0

    def test_lift_when_groupmate_out(self):
        sub = SubstitutionConfig(
            enable=True,
            substitute_groups=[[1, 2, 3]],
            substitution_lift_on_stockout=0.6,
        )
        gen = SalesDailyGenerator(
            random.Random(0),
            _deterministic_ts_config(),
            _deterministic_retail_config(),
            _flat_sparsity(),
            [],
            substitution=sub,
        )
        # Product 1 in stock, products 2 in stock, product 3 stocked out.
        # out_members=1, survivors=1 (product 2). product 1's share is
        # 0.6 * 1 / (survivors + 1) = 0.3 → multiplier 1.3.
        m = gen._substitution_multiplier(1, {3})
        assert math.isclose(m, 1.3)

    def test_stocked_out_product_gets_no_lift(self):
        sub = SubstitutionConfig(
            enable=True,
            substitute_groups=[[1, 2]],
            substitution_lift_on_stockout=0.5,
        )
        gen = SalesDailyGenerator(
            random.Random(0),
            _deterministic_ts_config(),
            _deterministic_retail_config(),
            _flat_sparsity(),
            [],
            substitution=sub,
        )
        # Product 1 itself stocked out → multiplier is 1.0.
        assert gen._substitution_multiplier(1, {1}) == 1.0


class TestPhase1EndToEnd:
    def test_phase1_features_alter_quantities(self):
        # With deterministic ts/retail config and a changepoint impulse,
        # the day-of-change quantity should equal base x multiplier.
        ts = _deterministic_ts_config()
        retail = _deterministic_retail_config()
        cp = ChangepointEvent(date=date(2024, 1, 1), demand_multiplier=2.0, decay_days=0)
        gen = SalesDailyGenerator(
            random.Random(0),
            ts,
            retail,
            _flat_sparsity(),
            [],
            changepoints=ChangepointConfig(changepoints=[cp]),
        )
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(3)]
        sales = gen.generate(
            store_ids=[1],
            product_data=[(1, Decimal("10.00"))],
            dates=dates,
            promotions={},
            stockouts={},
        )
        by_date = {s["date"]: s["quantity"] for s in sales}
        # Day 0: 200 (2x base). Days 1+: 100 (no decay, decay_days=0).
        assert by_date[date(2024, 1, 1)] == 200
        assert by_date[date(2024, 1, 2)] == 100
        assert by_date[date(2024, 1, 3)] == 100
