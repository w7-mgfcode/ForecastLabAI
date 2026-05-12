"""Service-layer tests for Phase 1 seeder features.

Covers:
- _apply_phase1_overrides / _build_config_from_params translation of new
  GenerateParams fields into SeederConfig sub-configs.
- GenerateParams validation (inverted date range).
- query_exogenous date-window guards.
"""

from datetime import date

import pytest

from app.features.seeder import schemas, service


class TestApplyPhase1Overrides:
    def test_defaults_leave_phase1_off(self):
        """Calling generate with default params must keep Phase 1 off."""
        params = schemas.GenerateParams()
        config = service._build_config_from_params(params)
        assert config.exogenous.enable_weather is False
        assert config.exogenous.enable_macro is False
        assert config.multi_seasonality.yearly_seasonality_amplitude == 0.0
        assert config.changepoints.changepoints == []
        assert config.returns.enable is False
        assert config.substitution.enable is False

    def test_enable_exogenous_turns_on_weather_and_macro(self):
        params = schemas.GenerateParams(
            enable_exogenous=True,
            weather_temperature_sensitivity=0.03,
        )
        config = service._build_config_from_params(params)
        assert config.exogenous.enable_weather is True
        assert config.exogenous.enable_macro is True
        assert config.exogenous.weather_temperature_sensitivity == 0.03

    def test_yearly_seasonality_passthrough(self):
        params = schemas.GenerateParams(yearly_seasonality_amplitude=0.25)
        config = service._build_config_from_params(params)
        assert config.multi_seasonality.yearly_seasonality_amplitude == 0.25

    def test_changepoint_list_translation(self):
        params = schemas.GenerateParams(
            changepoints=[
                schemas.ChangepointEventParam(
                    date=date(2024, 3, 15),
                    demand_multiplier=2.0,
                    decay_days=60,
                )
            ]
        )
        config = service._build_config_from_params(params)
        assert len(config.changepoints.changepoints) == 1
        cp = config.changepoints.changepoints[0]
        assert cp.date == date(2024, 3, 15)
        assert cp.demand_multiplier == 2.0
        assert cp.decay_days == 60

    def test_enable_returns_flips_returns_config(self):
        params = schemas.GenerateParams(enable_returns=True)
        config = service._build_config_from_params(params)
        assert config.returns.enable is True

    def test_enable_substitution_with_groups(self):
        params = schemas.GenerateParams(
            enable_substitution=True,
            substitute_groups=[[1, 2, 3], [4, 5]],
            substitution_lift_on_stockout=0.4,
        )
        config = service._build_config_from_params(params)
        assert config.substitution.enable is True
        assert config.substitution.substitute_groups == [[1, 2, 3], [4, 5]]
        assert config.substitution.substitution_lift_on_stockout == 0.4

    def test_phase1_overrides_preserve_scenario_dimensions(self):
        """A Phase 1 override must not clobber scenario-defined region/brand
        lists — regression for the bug fix in service._build_config_from_params.
        """
        params = schemas.GenerateParams(
            scenario="holiday_rush",
            stores=20,
            products=80,
            enable_returns=True,
        )
        config = service._build_config_from_params(params)
        assert config.dimensions.stores == 20
        assert config.dimensions.products == 80
        # Holiday rush keeps its 4 holidays + monthly seasonality through
        # the phase-1 path.
        assert len(config.holidays) == 4
        assert config.time_series.monthly_seasonality[12] == 1.8


class TestGenerateParamsValidation:
    def test_rejects_inverted_date_range(self):
        with pytest.raises(ValueError, match="must be on or after"):
            schemas.GenerateParams(
                start_date=date(2024, 12, 31),
                end_date=date(2024, 1, 1),
            )

    def test_yearly_amplitude_bounds(self):
        # ge=0.0 / le=1.0 enforced by Field.
        with pytest.raises(ValueError):
            schemas.GenerateParams(yearly_seasonality_amplitude=-0.1)
        with pytest.raises(ValueError):
            schemas.GenerateParams(yearly_seasonality_amplitude=1.5)


class TestQueryExogenousValidation:
    """Date-window guards on the service helper. The DB path is covered in
    integration tests."""

    @pytest.mark.asyncio
    async def test_rejects_inverted_window(self):
        with pytest.raises(ValueError, match="must be on or after"):
            await service.query_exogenous(
                db=None,  # type: ignore[arg-type]
                signal_name="weather_temp_c",
                start_date=date(2024, 12, 31),
                end_date=date(2024, 1, 1),
                store_id=None,
            )

    @pytest.mark.asyncio
    async def test_rejects_overlong_window(self):
        with pytest.raises(ValueError, match="too large"):
            await service.query_exogenous(
                db=None,  # type: ignore[arg-type]
                signal_name="weather_temp_c",
                start_date=date(2020, 1, 1),
                end_date=date(2030, 1, 1),
                store_id=None,
            )
