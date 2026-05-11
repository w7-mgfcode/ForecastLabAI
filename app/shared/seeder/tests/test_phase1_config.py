"""Tests for Phase 1 seeder configuration dataclasses.

Covers ExogenousSignalConfig, MultiSeasonalityConfig, ChangepointEvent /
ChangepointConfig, ReturnsConfig, SubstitutionConfig — and confirms the
SeederConfig defaults wire them in with disabled / empty defaults.
"""

from datetime import date

from app.shared.seeder.config import (
    ChangepointConfig,
    ChangepointEvent,
    ExogenousSignalConfig,
    MultiSeasonalityConfig,
    ReturnsConfig,
    ScenarioPreset,
    SeederConfig,
    SubstitutionConfig,
)


class TestExogenousSignalConfig:
    def test_defaults_disabled(self):
        config = ExogenousSignalConfig()
        assert config.enable_weather is False
        assert config.enable_macro is False
        assert config.enable_events is False
        assert config.weather_temperature_sensitivity == 0.0
        assert config.event_dates == []

    def test_event_dates_is_independent(self):
        # Default-factory list must not be shared between instances.
        a = ExogenousSignalConfig()
        b = ExogenousSignalConfig()
        a.event_dates.append(date(2024, 1, 1))
        assert b.event_dates == []


class TestMultiSeasonalityConfig:
    def test_defaults_zero(self):
        config = MultiSeasonalityConfig()
        assert config.yearly_seasonality_amplitude == 0.0
        assert config.yearly_phase_offset_days == 0


class TestChangepointConfig:
    def test_default_empty(self):
        assert ChangepointConfig().changepoints == []

    def test_event_fields(self):
        event = ChangepointEvent(date=date(2024, 3, 15), demand_multiplier=2.5, decay_days=60)
        assert event.date == date(2024, 3, 15)
        assert event.demand_multiplier == 2.5
        assert event.decay_days == 60


class TestReturnsConfig:
    def test_defaults_disabled(self):
        cfg = ReturnsConfig()
        assert cfg.enable is False
        assert 0.0 <= cfg.return_probability <= 1.0
        assert cfg.return_lag_days_min <= cfg.return_lag_days_max
        # Reason distribution default must be non-empty so _pick_reason
        # always returns a real reason without falling back.
        assert sum(cfg.return_reason_distribution.values()) > 0


class TestSubstitutionConfig:
    def test_defaults_disabled(self):
        cfg = SubstitutionConfig()
        assert cfg.enable is False
        assert cfg.substitute_groups == []
        assert cfg.substitution_lift_on_stockout == 0.0


class TestSeederConfigPhase1Wiring:
    def test_phase1_defaults_present_and_disabled(self):
        cfg = SeederConfig()
        # Each Phase 1 sub-config must be present with disabled defaults
        # so existing scenarios are byte-identical when not opted in.
        assert isinstance(cfg.exogenous, ExogenousSignalConfig)
        assert isinstance(cfg.multi_seasonality, MultiSeasonalityConfig)
        assert isinstance(cfg.changepoints, ChangepointConfig)
        assert isinstance(cfg.returns, ReturnsConfig)
        assert isinstance(cfg.substitution, SubstitutionConfig)
        assert cfg.exogenous.enable_weather is False
        assert cfg.multi_seasonality.yearly_seasonality_amplitude == 0.0
        assert cfg.changepoints.changepoints == []
        assert cfg.returns.enable is False
        assert cfg.substitution.enable is False

    def test_from_scenario_does_not_enable_phase1(self):
        # Existing scenarios must keep Phase 1 off — this is the
        # regression invariant that protects pre-Phase-1 outputs.
        for scenario in ScenarioPreset:
            cfg = SeederConfig.from_scenario(scenario)
            assert cfg.exogenous.enable_weather is False, f"{scenario} unexpectedly enables weather"
            assert cfg.exogenous.enable_macro is False
            assert cfg.exogenous.enable_events is False
            assert cfg.multi_seasonality.yearly_seasonality_amplitude == 0.0
            assert cfg.changepoints.changepoints == []
            assert cfg.returns.enable is False
            assert cfg.substitution.enable is False
