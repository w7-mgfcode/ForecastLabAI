"""Tests for Phase 2 lifecycle: ProductGenerator extension + LifecycleGenerator.

The regression invariant is the most load-bearing assertion here: with
``LifecycleConfig.enable=False`` (the default), ``ProductGenerator``
must emit rows byte-identical to its pre-Phase-2 output, and
``LifecycleGenerator.multiplier_for`` must always return 1.0.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from app.shared.seeder.config import DimensionConfig, LifecycleConfig
from app.shared.seeder.generators import ProductGenerator
from app.shared.seeder.generators.lifecycle import LifecycleGenerator


def _minimal_dimensions() -> DimensionConfig:
    return DimensionConfig(
        stores=2,
        products=4,
        store_regions=["North", "South"],
        store_types=["supermarket"],
        product_categories=["Beverage", "Snack"],
        product_brands=["BrandA", "BrandB"],
    )


class TestProductGeneratorLifecycleDisabled:
    """Regression invariant: byte-identical output when lifecycle is off."""

    def test_no_lifecycle_keys_when_disabled(self) -> None:
        gen = ProductGenerator(random.Random(123), _minimal_dimensions())
        products = gen.generate()
        for p in products:
            # Phase 2 keys MUST NOT appear when the feature is off — that
            # is what guarantees the regression invariant.
            assert "lifecycle_stage" not in p
            assert "launch_date" not in p
            assert "discontinue_date" not in p
            assert "pack_size" not in p
            assert "subcategory" not in p

    def test_disabled_config_same_as_none(self) -> None:
        # Passing a disabled LifecycleConfig must produce the same output
        # as passing None: no extra rng draws on either path.
        cfg = _minimal_dimensions()
        gen_none = ProductGenerator(random.Random(7), cfg)
        gen_disabled = ProductGenerator(
            random.Random(7),
            cfg,
            lifecycle_config=LifecycleConfig(),  # default enable=False
            date_range=(date(2024, 1, 1), date(2024, 12, 31)),
        )
        assert gen_none.generate() == gen_disabled.generate()

    def test_reproducible_across_runs(self) -> None:
        cfg = _minimal_dimensions()
        a = ProductGenerator(random.Random(42), cfg).generate()
        b = ProductGenerator(random.Random(42), cfg).generate()
        assert a == b


class TestProductGeneratorLifecycleEnabled:
    """When enabled, each product carries the five Phase 2 attrs."""

    def test_lifecycle_attrs_present(self) -> None:
        cfg = LifecycleConfig(enable=True, discontinue_probability=0.0)
        gen = ProductGenerator(
            random.Random(99),
            _minimal_dimensions(),
            lifecycle_config=cfg,
            date_range=(date(2024, 1, 1), date(2024, 12, 31)),
        )
        products = gen.generate()
        for p in products:
            assert p["lifecycle_stage"] in (
                "intro",
                "growth",
                "maturity",
                "decline",
            )
            assert isinstance(p["launch_date"], date)
            assert isinstance(p["pack_size"], int) and p["pack_size"] > 0
            assert isinstance(p["subcategory"], str) and p["subcategory"]
            # Discontinue_probability=0 means no product gets retired.
            assert p["discontinue_date"] is None

    def test_discontinue_respects_launch_order(self) -> None:
        cfg = LifecycleConfig(enable=True, discontinue_probability=1.0)
        gen = ProductGenerator(
            random.Random(7),
            _minimal_dimensions(),
            lifecycle_config=cfg,
            date_range=(date(2024, 1, 1), date(2024, 12, 31)),
        )
        for p in gen.generate():
            if p["discontinue_date"] is not None:
                assert p["discontinue_date"] >= p["launch_date"], p

    def test_reproducible_with_lifecycle_on(self) -> None:
        cfg = LifecycleConfig(enable=True, discontinue_probability=0.3)
        dr = (date(2024, 1, 1), date(2024, 12, 31))
        a = ProductGenerator(
            random.Random(42), _minimal_dimensions(), lifecycle_config=cfg, date_range=dr
        ).generate()
        b = ProductGenerator(
            random.Random(42), _minimal_dimensions(), lifecycle_config=cfg, date_range=dr
        ).generate()
        assert a == b


class TestLifecycleGeneratorDisabled:
    def test_returns_one_when_config_none(self) -> None:
        gen = LifecycleGenerator(None)
        assert gen.enabled is False
        assert gen.multiplier_for(date(2024, 6, 1), date(2024, 1, 1), None) == 1.0
        assert gen.stage_for(date(2024, 6, 1), date(2024, 1, 1), None) == "maturity"

    def test_returns_one_when_disabled(self) -> None:
        gen = LifecycleGenerator(LifecycleConfig())  # default enable=False
        assert gen.enabled is False
        assert gen.multiplier_for(date(2024, 6, 1), date(2024, 1, 1), None) == 1.0


class TestLifecycleGeneratorEnabled:
    def _gen(self, **overrides: object) -> LifecycleGenerator:
        kwargs: dict[str, object] = {
            "enable": True,
            "intro_ramp_days": 10,
            "growth_ramp_days": 10,
            "maturity_steady_days": 10,
            "decline_decay_days": 10,
            "intro_multiplier": 0.1,
            "decline_multiplier": 0.0,
        }
        kwargs.update(overrides)
        cfg = LifecycleConfig(**kwargs)  # type: ignore[arg-type]
        return LifecycleGenerator(cfg)

    def test_pre_launch_demand_is_zero(self) -> None:
        gen = self._gen()
        launch = date(2024, 6, 1)
        assert gen.multiplier_for(date(2024, 5, 31), launch, None) == 0.0

    def test_intro_ramp_linear(self) -> None:
        gen = self._gen()
        launch = date(2024, 1, 1)
        # Day 0 == intro_multiplier (0.1), day 10 (end of ramp) == 1.0.
        assert gen.multiplier_for(launch, launch, None) == 0.1
        midway = launch + timedelta(days=5)
        m = gen.multiplier_for(midway, launch, None)
        # Linear ramp midpoint between 0.1 and 1.0 is 0.55.
        assert abs(m - 0.55) < 1e-9

    def test_maturity_held_at_one(self) -> None:
        gen = self._gen()
        launch = date(2024, 1, 1)
        # maturity starts at day intro_ramp + growth_ramp = 20.
        assert gen.multiplier_for(launch + timedelta(days=25), launch, None) == 1.0

    def test_decline_decays_toward_floor(self) -> None:
        gen = self._gen(decline_multiplier=0.2, decline_decay_days=10)
        launch = date(2024, 1, 1)
        # Decline starts at day 30.
        # decline_multiplier=0.2 means asymptote is 0.2; m(decline_start)=1.0.
        m_start = gen.multiplier_for(launch + timedelta(days=30), launch, None)
        assert abs(m_start - 1.0) < 1e-9
        m_far = gen.multiplier_for(launch + timedelta(days=130), launch, None)
        assert 0.2 <= m_far < 0.3  # well into the decay tail

    def test_discontinue_overrides_all_curves(self) -> None:
        gen = self._gen()
        launch = date(2024, 1, 1)
        discontinue = date(2024, 3, 1)
        assert gen.multiplier_for(discontinue, launch, discontinue) == 0.0
        assert gen.multiplier_for(discontinue + timedelta(days=10), launch, discontinue) == 0.0
        assert gen.stage_for(discontinue, launch, discontinue) == "discontinued"

    def test_stage_for_traverses_segments(self) -> None:
        gen = self._gen()
        launch = date(2024, 1, 1)
        assert gen.stage_for(launch, launch, None) == "intro"
        assert gen.stage_for(launch + timedelta(days=11), launch, None) == "growth"
        assert gen.stage_for(launch + timedelta(days=21), launch, None) == "maturity"
        assert gen.stage_for(launch + timedelta(days=31), launch, None) == "decline"
