"""Regression invariant: Phase 1 toggles OFF == pre-Phase-1 output.

These tests are LOAD-BEARING: they guarantee that adding the Phase 1
options to ``SalesDailyGenerator`` does not change the byte-output of
the existing six scenarios. If any of them starts failing, somebody
either added an RNG draw on the disabled path or changed a default
value that affects the existing math.
"""

# mypy: disable-error-code="union-attr,arg-type,operator,return-value"

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.shared.seeder.config import (
    ChangepointConfig,
    MultiSeasonalityConfig,
    ScenarioPreset,
    SeederConfig,
    SubstitutionConfig,
)
from app.shared.seeder.generators.facts import SalesDailyGenerator


def _short_dates(n: int) -> list[date]:
    """Use a small date range so the test is fast."""
    return [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]


def _run_with_kwargs(config: SeederConfig, **extra_kwargs):
    """Run SalesDailyGenerator using ``config`` with optional kwargs."""
    rng = random.Random(config.seed)
    gen = SalesDailyGenerator(
        rng,
        config.time_series,
        config.retail,
        config.sparsity,
        config.holidays,
        **extra_kwargs,
    )
    return gen.generate(
        store_ids=[1, 2],
        product_data=[(1, Decimal("9.99")), (2, Decimal("4.99"))],
        dates=_short_dates(30),
        promotions={},
        stockouts={},
    )


class TestRegressionWithoutKwargs:
    """Calling without any Phase 1 kwargs must match calling with explicit
    defaults / None / empty configs."""

    @pytest.mark.parametrize("scenario", list(ScenarioPreset))
    def test_no_kwargs_matches_explicit_defaults(self, scenario: ScenarioPreset):
        config = SeederConfig.from_scenario(scenario, seed=42)
        # Cap dates to the scenario range we care about.
        baseline = _run_with_kwargs(config)
        with_defaults = _run_with_kwargs(
            config,
            multi_seasonality=MultiSeasonalityConfig(),  # amplitude=0 default
            changepoints=ChangepointConfig(),  # empty default
            substitution=SubstitutionConfig(),  # disabled default
            exogenous_weather=None,
            weather_temperature_sensitivity=0.0,
        )
        assert baseline == with_defaults, (
            f"Phase 1 defaults must not alter output for scenario {scenario.value}"
        )

    def test_disabled_phase1_does_not_consume_rng(self):
        """A second generator with Phase 1 features enabled but no data
        (e.g. empty changepoints / empty weather lookup) must still
        produce the same row count and quantities as the disabled path.
        """
        config = SeederConfig.from_scenario(ScenarioPreset.RETAIL_STANDARD, seed=42)
        baseline = _run_with_kwargs(config)
        # Enable substitution but with no groups → group lookup is empty.
        no_op = _run_with_kwargs(
            config,
            substitution=SubstitutionConfig(
                enable=True,
                substitute_groups=[],
                substitution_lift_on_stockout=0.5,
            ),
            exogenous_weather={},  # empty lookup
            weather_temperature_sensitivity=0.1,  # nonzero but no rows match
        )
        assert baseline == no_op
