"""Tests for Phase 2 lifecycle integration into SalesDailyGenerator.

These tests are LOAD-BEARING: they guarantee the byte-identical
regression invariant — when ``lifecycle=None`` and
``product_lifecycle_data=None`` (the defaults), the generator emits
exactly the same rows as before the integration. The enabled-path
tests cover the new multiplier behaviour (pre-launch zero, decline
attenuation, discontinue cutoff) plus the legacy ramp suppression.
"""

# mypy: disable-error-code="union-attr,arg-type,operator,return-value,misc"

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from app.shared.seeder.config import (
    LifecycleConfig,
    RetailPatternConfig,
    SparsityConfig,
    TimeSeriesConfig,
)
from app.shared.seeder.generators.facts import SalesDailyGenerator
from app.shared.seeder.generators.lifecycle import LifecycleGenerator


def _dates(start: date, n: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def _minimal_ts() -> TimeSeriesConfig:
    """Deterministic-friendly TimeSeriesConfig (no anomalies, no noise)."""
    return TimeSeriesConfig(
        base_demand=100,
        trend="none",
        weekly_seasonality=[1.0] * 7,
        monthly_seasonality={},
        noise_sigma=0.0,
        anomaly_probability=0.0,
        anomaly_magnitude=1.0,
    )


def _minimal_retail() -> RetailPatternConfig:
    return RetailPatternConfig(
        promotion_lift=1.0,
        stockout_behavior="zero",
        price_elasticity=0.0,
        new_product_ramp_days=0,  # disable legacy ramp for most tests
        promotion_probability=0.0,
        stockout_probability=0.0,
    )


def _run_generator(
    *,
    seed: int = 42,
    ts: TimeSeriesConfig | None = None,
    retail: RetailPatternConfig | None = None,
    lifecycle: LifecycleGenerator | None = None,
    product_lifecycle_data: dict[int, tuple[date | None, date | None]] | None = None,
    dates: list[date] | None = None,
) -> list[dict[str, date | int | Decimal]]:
    rng = random.Random(seed)
    gen = SalesDailyGenerator(
        rng,
        ts or _minimal_ts(),
        retail or _minimal_retail(),
        SparsityConfig(),
        holidays=[],
        lifecycle=lifecycle,
    )
    return gen.generate(
        store_ids=[1, 2],
        product_data=[(10, Decimal("9.99")), (20, Decimal("4.99"))],
        dates=dates or _dates(date(2024, 1, 1), 60),
        promotions={},
        stockouts={},
        product_lifecycle_data=product_lifecycle_data,
    )


# ---------------------------------------------------------------------- #
# Regression invariant: pre-Phase-2 callers see byte-identical output.
# ---------------------------------------------------------------------- #


class TestRegressionInvariant:
    def test_no_kwargs_matches_explicit_none(self) -> None:
        baseline = _run_generator()
        with_explicit_none = _run_generator(
            lifecycle=None,
            product_lifecycle_data=None,
        )
        assert baseline == with_explicit_none

    def test_disabled_lifecycle_matches_no_lifecycle(self) -> None:
        baseline = _run_generator()
        with_disabled = _run_generator(
            lifecycle=LifecycleGenerator(LifecycleConfig()),  # default enable=False
        )
        assert baseline == with_disabled

    def test_disabled_lifecycle_does_not_consume_rng(self) -> None:
        # Both runs use seed=42; the disabled lifecycle path must not
        # add any rng draws, so quantities must match exactly.
        baseline = _run_generator(seed=42)
        with_disabled = _run_generator(
            seed=42,
            lifecycle=LifecycleGenerator(LifecycleConfig()),
            product_lifecycle_data={10: (date(2024, 1, 1), None)},
        )
        # When lifecycle is disabled, ``product_lifecycle_data`` still
        # threads ``launch_date`` to ``_compute_demand``, which keeps
        # the row count and rng order intact — only the legacy ramp
        # path could fire, and ``new_product_ramp_days=0`` neuters it.
        assert baseline == with_disabled


# ---------------------------------------------------------------------- #
# Enabled-path correctness
# ---------------------------------------------------------------------- #


def _enabled_lifecycle() -> LifecycleGenerator:
    return LifecycleGenerator(
        LifecycleConfig(
            enable=True,
            intro_ramp_days=10,
            growth_ramp_days=10,
            maturity_steady_days=20,
            decline_decay_days=10,
            intro_multiplier=0.1,
            decline_multiplier=0.0,
        )
    )


class TestLifecycleMultiplierEnabled:
    def test_pre_launch_demand_is_zero(self) -> None:
        # Product 10 launches mid-range; all earlier dates should have qty=0.
        rows = _run_generator(
            lifecycle=_enabled_lifecycle(),
            product_lifecycle_data={
                10: (date(2024, 1, 31), None),  # launches Jan 31
                20: (date(2024, 1, 1), None),  # launched at range start
            },
            dates=_dates(date(2024, 1, 1), 60),
        )
        pre_launch = [r for r in rows if r["product_id"] == 10 and r["date"] < date(2024, 1, 31)]
        assert pre_launch  # there ARE rows
        assert all(r["quantity"] == 0 for r in pre_launch)

    def test_post_discontinue_demand_is_zero(self) -> None:
        rows = _run_generator(
            lifecycle=_enabled_lifecycle(),
            product_lifecycle_data={
                10: (date(2024, 1, 1), date(2024, 1, 31)),  # discontinued Jan 31
                20: (date(2024, 1, 1), None),
            },
            dates=_dates(date(2024, 1, 1), 60),
        )
        post_disc = [r for r in rows if r["product_id"] == 10 and r["date"] >= date(2024, 1, 31)]
        assert post_disc
        assert all(r["quantity"] == 0 for r in post_disc)

    def test_decline_demand_lower_than_maturity(self) -> None:
        # Lifecycle: intro(10)+growth(10)+maturity(20)=40 days to decline.
        # Launch on Jan 1 → decline starts Feb 10.
        rows = _run_generator(
            lifecycle=_enabled_lifecycle(),
            product_lifecycle_data={
                10: (date(2024, 1, 1), None),
                20: (date(2024, 1, 1), None),
            },
            dates=_dates(date(2024, 1, 1), 90),
        )
        maturity_qty_sum = sum(
            r["quantity"]
            for r in rows
            if r["product_id"] == 10
            and date(2024, 1, 31) <= r["date"] < date(2024, 2, 10)  # maturity window
        )
        decline_qty_sum = sum(
            r["quantity"]
            for r in rows
            if r["product_id"] == 10
            and date(2024, 3, 1) <= r["date"] < date(2024, 3, 11)  # well into decline
        )
        assert maturity_qty_sum > decline_qty_sum > 0

    def test_intro_demand_lower_than_maturity(self) -> None:
        rows = _run_generator(
            lifecycle=_enabled_lifecycle(),
            product_lifecycle_data={
                10: (date(2024, 1, 1), None),
                20: (date(2024, 1, 1), None),
            },
            dates=_dates(date(2024, 1, 1), 60),
        )
        intro_qty_sum = sum(
            r["quantity"]
            for r in rows
            if r["product_id"] == 10
            and date(2024, 1, 1) <= r["date"] < date(2024, 1, 11)  # intro window
        )
        maturity_qty_sum = sum(
            r["quantity"]
            for r in rows
            if r["product_id"] == 10
            and date(2024, 1, 31) <= r["date"] < date(2024, 2, 10)  # maturity window
        )
        assert intro_qty_sum < maturity_qty_sum


class TestLegacyRampSuppression:
    def test_legacy_ramp_does_not_double_apply_when_lifecycle_enabled(self) -> None:
        retail = RetailPatternConfig(
            promotion_lift=1.0,
            stockout_behavior="zero",
            price_elasticity=0.0,
            new_product_ramp_days=30,  # legacy ramp would otherwise apply
            promotion_probability=0.0,
            stockout_probability=0.0,
        )
        rows_with_lifecycle = _run_generator(
            retail=retail,
            lifecycle=_enabled_lifecycle(),
            product_lifecycle_data={
                10: (date(2024, 1, 1), None),
                20: (date(2024, 1, 1), None),
            },
            dates=_dates(date(2024, 1, 1), 30),
        )
        # Reference: same lifecycle on, but legacy ramp_days = 0
        retail_no_legacy = RetailPatternConfig(
            promotion_lift=1.0,
            stockout_behavior="zero",
            price_elasticity=0.0,
            new_product_ramp_days=0,
            promotion_probability=0.0,
            stockout_probability=0.0,
        )
        rows_no_legacy = _run_generator(
            retail=retail_no_legacy,
            lifecycle=_enabled_lifecycle(),
            product_lifecycle_data={
                10: (date(2024, 1, 1), None),
                20: (date(2024, 1, 1), None),
            },
            dates=_dates(date(2024, 1, 1), 30),
        )
        # Legacy ramp must be suppressed when lifecycle is enabled — the
        # two runs must produce identical output, proving no stacking.
        assert rows_with_lifecycle == rows_no_legacy

    def test_legacy_ramp_still_fires_when_lifecycle_disabled(self) -> None:
        retail = RetailPatternConfig(
            promotion_lift=1.0,
            stockout_behavior="zero",
            price_elasticity=0.0,
            new_product_ramp_days=30,
            promotion_probability=0.0,
            stockout_probability=0.0,
        )
        # Lifecycle is None (pre-Phase-2) but product_lifecycle_data
        # threads launch_date — legacy ramp should fire.
        with_legacy = _run_generator(
            retail=retail,
            lifecycle=None,
            product_lifecycle_data={
                10: (date(2024, 1, 1), None),
                20: (date(2024, 1, 1), None),
            },
            dates=_dates(date(2024, 1, 1), 30),
        )
        # Reference: same retail but no launch date — legacy ramp is dormant.
        no_launch = _run_generator(
            retail=retail,
            lifecycle=None,
            product_lifecycle_data=None,
            dates=_dates(date(2024, 1, 1), 30),
        )
        # Early-range quantities for product 10 must be *lower* in
        # ``with_legacy`` because the linear ramp attenuates demand.
        early_with = sum(
            r["quantity"]
            for r in with_legacy
            if r["product_id"] == 10 and r["date"] < date(2024, 1, 10)
        )
        early_without = sum(
            r["quantity"]
            for r in no_launch
            if r["product_id"] == 10 and r["date"] < date(2024, 1, 10)
        )
        assert early_with < early_without


class TestLifecycleDataLookup:
    def test_missing_product_id_defaults_to_no_lifecycle(self) -> None:
        # product_lifecycle_data only has entry for product 10 — product
        # 20 should evaluate the lifecycle multiplier with launch=None
        # → 1.0 (no attenuation).
        rows = _run_generator(
            lifecycle=_enabled_lifecycle(),
            product_lifecycle_data={
                10: (date(2024, 6, 1), None),  # not launched yet in early Jan
            },
            dates=_dates(date(2024, 1, 1), 5),
        )
        product_10 = [r for r in rows if r["product_id"] == 10]
        product_20 = [r for r in rows if r["product_id"] == 20]
        # Product 10 hasn't launched → all zeros.
        assert all(r["quantity"] == 0 for r in product_10)
        # Product 20 has no lifecycle data → full demand.
        assert sum(r["quantity"] for r in product_20) > 0
