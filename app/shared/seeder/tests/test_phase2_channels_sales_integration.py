"""Tests for Phase 2 channel integration into SalesDailyGenerator.

Regression invariant: with ``channels=None`` (or ``channels`` set to
a disabled ``ChannelConfig``) the generator emits rows with no
``channel`` key and consumes zero new rng state — byte-identical to
its pre-Phase-2 behavior.
"""

# mypy: disable-error-code="union-attr,arg-type,operator,return-value,misc"

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.shared.seeder.config import (
    ChannelConfig,
    RetailPatternConfig,
    SparsityConfig,
    TimeSeriesConfig,
)
from app.shared.seeder.generators.facts import SalesDailyGenerator


def _dates(start: date, n: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def _minimal_ts() -> TimeSeriesConfig:
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
        new_product_ramp_days=0,
        promotion_probability=0.0,
        stockout_probability=0.0,
    )


def _run_generator(
    *,
    seed: int = 42,
    channels: ChannelConfig | None = None,
    promotions: dict[tuple[int, int], set[date]] | None = None,
    dates: list[date] | None = None,
) -> list[dict[str, date | int | Decimal | str]]:
    rng = random.Random(seed)
    gen = SalesDailyGenerator(
        rng,
        _minimal_ts(),
        _minimal_retail(),
        SparsityConfig(),
        holidays=[],
        channels=channels,
    )
    return gen.generate(
        store_ids=[1, 2],
        product_data=[(10, Decimal("9.99")), (20, Decimal("4.99"))],
        dates=dates or _dates(date(2024, 1, 1), 30),
        promotions=promotions or {},
        stockouts={},
    )


# ---------------------------------------------------------------------- #
# Regression invariant
# ---------------------------------------------------------------------- #


class TestRegressionInvariant:
    def test_no_channels_kwarg_omits_channel_column(self) -> None:
        rows = _run_generator()
        for r in rows:
            assert "channel" not in r

    def test_disabled_config_matches_no_channels(self) -> None:
        baseline = _run_generator()
        with_disabled = _run_generator(channels=ChannelConfig())  # enable_multichannel=False
        assert baseline == with_disabled

    def test_disabled_channels_does_not_consume_rng(self) -> None:
        # Empty channel_mix + disabled config — even with channel_mix
        # populated, the disabled path must not draw an rng row-pick.
        baseline = _run_generator(seed=42)
        with_populated_disabled = _run_generator(
            seed=42,
            channels=ChannelConfig(
                enable_multichannel=False,
                channel_mix={"in_store": 0.5, "online": 0.5},
            ),
        )
        assert baseline == with_populated_disabled


# ---------------------------------------------------------------------- #
# Enabled-path correctness
# ---------------------------------------------------------------------- #


def _enabled_uniform() -> ChannelConfig:
    return ChannelConfig(
        enable_multichannel=True,
        channel_mix={"in_store": 0.5, "online": 0.5},
        online_promo_uplift=1.0,
        online_substitution_to_instore=0.0,
    )


class TestChannelDistribution:
    def test_chosen_channel_in_mix_keys(self) -> None:
        cfg = ChannelConfig(
            enable_multichannel=True,
            channel_mix={"in_store": 0.4, "online": 0.4, "click_collect": 0.2},
        )
        rows = _run_generator(channels=cfg)
        for r in rows:
            assert "channel" in r
            assert r["channel"] in {"in_store", "online", "click_collect"}

    def test_single_channel_mix_always_picks_that_channel(self) -> None:
        cfg = ChannelConfig(
            enable_multichannel=True,
            channel_mix={"wholesale": 1.0},
        )
        rows = _run_generator(channels=cfg)
        assert rows
        assert all(r["channel"] == "wholesale" for r in rows)

    def test_dominant_channel_appears_more_often(self) -> None:
        cfg = ChannelConfig(
            enable_multichannel=True,
            channel_mix={"in_store": 0.9, "online": 0.1},
        )
        rows = _run_generator(channels=cfg, dates=_dates(date(2024, 1, 1), 60))
        n_in_store = sum(1 for r in rows if r["channel"] == "in_store")
        n_online = sum(1 for r in rows if r["channel"] == "online")
        assert n_in_store > n_online
        assert n_online > 0  # some online rows still appear

    def test_zero_weight_channels_are_never_chosen(self) -> None:
        cfg = ChannelConfig(
            enable_multichannel=True,
            channel_mix={"in_store": 1.0, "online": 0.0},
        )
        rows = _run_generator(channels=cfg)
        assert all(r["channel"] == "in_store" for r in rows)


class TestOnlinePromoUplift:
    def test_uplift_increases_online_qty_on_promo_dates(self) -> None:
        cfg = ChannelConfig(
            enable_multichannel=True,
            channel_mix={"online": 1.0},  # force every row online
            online_promo_uplift=2.0,
            online_substitution_to_instore=0.0,
        )
        promo_set = {date(2024, 1, 5), date(2024, 1, 6)}
        promotions = {
            (1, 10): promo_set,
            (1, 20): promo_set,
            (2, 10): promo_set,
            (2, 20): promo_set,
        }
        rows = _run_generator(channels=cfg, promotions=promotions)
        promo_qty_avg = sum(int(r["quantity"]) for r in rows if r["date"] in promo_set) / max(
            1, sum(1 for r in rows if r["date"] in promo_set)
        )
        non_promo_qty_avg = sum(
            int(r["quantity"]) for r in rows if r["date"] not in promo_set
        ) / max(1, sum(1 for r in rows if r["date"] not in promo_set))
        # promotion_lift defaults to 1.0 in _minimal_retail so the only
        # quantity difference on promo dates comes from the uplift.
        assert promo_qty_avg > non_promo_qty_avg

    def test_uplift_does_not_apply_to_in_store_on_promo(self) -> None:
        cfg = ChannelConfig(
            enable_multichannel=True,
            channel_mix={"in_store": 1.0},  # force every row in_store
            online_promo_uplift=2.0,
            online_substitution_to_instore=0.0,
        )
        promo_set = {date(2024, 1, 5)}
        promotions = {
            (1, 10): promo_set,
            (1, 20): promo_set,
            (2, 10): promo_set,
            (2, 20): promo_set,
        }
        rows = _run_generator(channels=cfg, promotions=promotions)
        # All rows in_store; uplift should not fire.
        promo_qty = [int(r["quantity"]) for r in rows if r["date"] in promo_set]
        non_promo_qty = [int(r["quantity"]) for r in rows if r["date"] not in promo_set]
        # Both should be ~base_demand (100) since promotion_lift=1.0 and
        # in_store rows don't get online uplift.
        assert sum(promo_qty) // len(promo_qty) == sum(non_promo_qty) // len(non_promo_qty)


class TestSubstitutionShift:
    def test_substitution_shifts_mix_during_promo(self) -> None:
        # Start with even 50/50 mix; substitution shifts to favor online
        # during promo. Compare promo-day channel distribution to
        # non-promo-day distribution.
        cfg = ChannelConfig(
            enable_multichannel=True,
            channel_mix={"in_store": 0.5, "online": 0.5},
            online_promo_uplift=1.0,
            online_substitution_to_instore=0.8,  # strong shift to online
        )
        promo_set = set(_dates(date(2024, 1, 15), 15))  # promo Jan 15-29
        promotions = {
            (1, 10): promo_set,
            (1, 20): promo_set,
            (2, 10): promo_set,
            (2, 20): promo_set,
        }
        rows = _run_generator(
            channels=cfg, promotions=promotions, dates=_dates(date(2024, 1, 1), 30)
        )
        promo_online_share = sum(
            1 for r in rows if r["date"] in promo_set and r["channel"] == "online"
        ) / max(1, sum(1 for r in rows if r["date"] in promo_set))
        non_promo_online_share = sum(
            1 for r in rows if r["date"] not in promo_set and r["channel"] == "online"
        ) / max(1, sum(1 for r in rows if r["date"] not in promo_set))
        assert promo_online_share > non_promo_online_share

    def test_substitution_zero_means_no_shift(self) -> None:
        cfg_a = ChannelConfig(
            enable_multichannel=True,
            channel_mix={"in_store": 0.5, "online": 0.5},
            online_promo_uplift=1.0,
            online_substitution_to_instore=0.0,
        )
        promo_set = {date(2024, 1, 15)}
        promotions = {
            (1, 10): promo_set,
            (1, 20): promo_set,
            (2, 10): promo_set,
            (2, 20): promo_set,
        }
        rows_with_promo = _run_generator(channels=cfg_a, promotions=promotions)
        rows_no_promo = _run_generator(channels=cfg_a, promotions={})
        # With substitution=0, channels are picked from the same mix
        # whether or not a promo is active. The two channel streams
        # should be identical at the same seed since promo doesn't
        # touch the mix.
        chosen_a = [r["channel"] for r in rows_with_promo]
        chosen_b = [r["channel"] for r in rows_no_promo]
        assert chosen_a == chosen_b


# ---------------------------------------------------------------------- #
# Validation
# ---------------------------------------------------------------------- #


class TestChannelValidation:
    def test_empty_mix_raises(self) -> None:
        cfg = ChannelConfig(enable_multichannel=True, channel_mix={})
        with pytest.raises(ValueError, match="channel_mix must be non-empty"):
            _run_generator(channels=cfg)

    def test_invalid_channel_name_raises(self) -> None:
        cfg = ChannelConfig(
            enable_multichannel=True,
            channel_mix={"in_store": 0.5, "telegraph": 0.5},
        )
        with pytest.raises(ValueError, match="invalid channels"):
            _run_generator(channels=cfg)

    def test_negative_weight_raises(self) -> None:
        cfg = ChannelConfig(
            enable_multichannel=True,
            channel_mix={"in_store": 0.5, "online": -0.1},
        )
        with pytest.raises(ValueError, match="must be >= 0"):
            _run_generator(channels=cfg)

    def test_all_zero_weights_raises(self) -> None:
        cfg = ChannelConfig(
            enable_multichannel=True,
            channel_mix={"in_store": 0.0, "online": 0.0},
        )
        with pytest.raises(ValueError, match="at least one positive weight"):
            _run_generator(channels=cfg)

    def test_negative_uplift_raises(self) -> None:
        cfg = ChannelConfig(
            enable_multichannel=True,
            channel_mix={"online": 1.0},
            online_promo_uplift=-0.5,
        )
        with pytest.raises(ValueError, match="online_promo_uplift"):
            _run_generator(channels=cfg)

    def test_substitution_out_of_range_raises(self) -> None:
        cfg = ChannelConfig(
            enable_multichannel=True,
            channel_mix={"in_store": 0.5, "online": 0.5},
            online_substitution_to_instore=1.5,
        )
        with pytest.raises(ValueError, match="online_substitution_to_instore"):
            _run_generator(channels=cfg)


# ---------------------------------------------------------------------- #
# Row shape
# ---------------------------------------------------------------------- #


class TestRowShape:
    def test_channel_key_present_when_enabled(self) -> None:
        rows = _run_generator(channels=_enabled_uniform())
        assert rows
        for r in rows:
            assert "channel" in r
            assert r["channel"] in {"in_store", "online"}

    def test_channel_key_absent_when_disabled(self) -> None:
        rows = _run_generator()
        for r in rows:
            assert "channel" not in r
