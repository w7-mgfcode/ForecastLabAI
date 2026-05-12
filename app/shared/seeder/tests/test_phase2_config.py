"""Tests for Phase 2 seeder configuration dataclasses.

Covers ChannelConfig, LifecycleConfig, BundleConfig, MarkdownConfig, and
LeadTimeConfig — plus the SeederConfig wiring that holds them with
disabled / empty defaults so existing scenarios stay byte-identical.
"""

from app.shared.seeder.config import (
    BundleConfig,
    ChannelConfig,
    LeadTimeConfig,
    LifecycleConfig,
    MarkdownConfig,
    ScenarioPreset,
    SeederConfig,
)


class TestChannelConfig:
    def test_defaults_disabled(self) -> None:
        cfg = ChannelConfig()
        assert cfg.enable_multichannel is False
        assert cfg.channel_mix == {}
        assert cfg.online_promo_uplift == 1.0
        assert cfg.online_substitution_to_instore == 0.0

    def test_channel_mix_is_independent(self) -> None:
        a = ChannelConfig()
        b = ChannelConfig()
        a.channel_mix["online"] = 0.3
        assert b.channel_mix == {}


class TestLifecycleConfig:
    def test_defaults_disabled(self) -> None:
        cfg = LifecycleConfig()
        assert cfg.enable is False
        assert cfg.auto_progression is True
        assert cfg.discontinue_probability == 0.0
        assert 0.0 <= cfg.intro_multiplier <= 1.0
        assert 0.0 <= cfg.decline_multiplier <= 1.0
        assert cfg.intro_ramp_days > 0
        assert cfg.growth_ramp_days > 0


class TestBundleConfig:
    def test_defaults_disabled(self) -> None:
        cfg = BundleConfig()
        assert cfg.enable is False
        assert cfg.bundle_probability == 0.0
        assert cfg.min_bundle_size >= 2
        assert cfg.max_bundle_size >= cfg.min_bundle_size
        assert 0.0 <= cfg.bundle_discount_pct_min <= cfg.bundle_discount_pct_max <= 1.0


class TestMarkdownConfig:
    def test_defaults_disabled(self) -> None:
        cfg = MarkdownConfig()
        assert cfg.enable is False
        assert cfg.trigger in ("age_days", "stockout_risk", "lifecycle_decline")
        assert 0.0 <= cfg.markdown_depth_pct <= 1.0
        assert cfg.markdown_duration_days > 0


class TestLeadTimeConfig:
    def test_defaults_disabled(self) -> None:
        cfg = LeadTimeConfig()
        assert cfg.enable is False
        assert cfg.mean_lead_time_days >= 0
        assert cfg.lead_time_sigma_days >= 0
        assert cfg.order_frequency_days > 0
        assert 0.0 <= cfg.fill_rate_mean <= 1.0


class TestSeederConfigPhase2Wiring:
    def test_phase2_defaults_present_and_disabled(self) -> None:
        cfg = SeederConfig()
        # Each Phase 2 sub-config must be present with disabled defaults
        # so existing scenarios remain byte-identical when not opted in.
        assert isinstance(cfg.channels, ChannelConfig)
        assert isinstance(cfg.lifecycle, LifecycleConfig)
        assert isinstance(cfg.bundles, BundleConfig)
        assert isinstance(cfg.markdowns, MarkdownConfig)
        assert isinstance(cfg.lead_time, LeadTimeConfig)
        assert cfg.channels.enable_multichannel is False
        assert cfg.lifecycle.enable is False
        assert cfg.bundles.enable is False
        assert cfg.markdowns.enable is False
        assert cfg.lead_time.enable is False

    def test_from_scenario_does_not_enable_phase2(self) -> None:
        # Regression invariant: pre-Phase-2 scenarios must not silently
        # enable any Phase 2 toggle, or the seeded outputs would shift.
        for scenario in ScenarioPreset:
            cfg = SeederConfig.from_scenario(scenario)
            assert cfg.channels.enable_multichannel is False, (
                f"{scenario} unexpectedly enables multichannel"
            )
            assert cfg.lifecycle.enable is False, f"{scenario} unexpectedly enables lifecycle"
            assert cfg.bundles.enable is False, f"{scenario} unexpectedly enables bundles"
            assert cfg.markdowns.enable is False, f"{scenario} unexpectedly enables markdowns"
            assert cfg.lead_time.enable is False, f"{scenario} unexpectedly enables lead_time"
