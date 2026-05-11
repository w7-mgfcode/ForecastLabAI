"""Tests for ExogenousSignalGenerator (Phase 1)."""

# mypy: disable-error-code="union-attr,arg-type,operator,return-value"
# Generator dicts have a wide union; tests narrow at access time.

import math
import random
from datetime import date, timedelta

from app.shared.seeder.config import ExogenousSignalConfig
from app.shared.seeder.generators.exogenous import (
    EVENT_SIGNAL_NAME,
    MACRO_SIGNAL_NAME,
    WEATHER_SIGNAL_NAME,
    ExogenousSignalGenerator,
)


def _date_range(start: date, days: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(days)]


class TestExogenousSignalGeneratorDisabled:
    def test_all_disabled_produces_no_rows(self):
        gen = ExogenousSignalGenerator(random.Random(42), ExogenousSignalConfig())
        rows = gen.generate(_date_range(date(2024, 1, 1), 5), [1, 2])
        assert rows == []


class TestWeather:
    def test_weather_emits_row_per_store_and_date(self):
        cfg = ExogenousSignalConfig(enable_weather=True, weather_noise_sigma_c=0.0)
        gen = ExogenousSignalGenerator(random.Random(42), cfg)
        store_ids = [1, 2, 3]
        dates = _date_range(date(2024, 1, 1), 7)
        rows = gen.generate(dates, store_ids)
        weather_rows = [r for r in rows if r["signal_name"] == WEATHER_SIGNAL_NAME]
        assert len(weather_rows) == len(store_ids) * len(dates)
        # Sanity: each row is per-store (is_global=False), store_id non-null.
        for r in weather_rows:
            assert r["is_global"] is False
            assert r["store_id"] in store_ids
            assert isinstance(r["value"], float)

    def test_weather_seasonal_peak_in_summer(self):
        # With zero noise the value should follow the deterministic sin wave.
        cfg = ExogenousSignalConfig(
            enable_weather=True,
            weather_amplitude_c=10.0,
            weather_climatology_mean_c=15.0,
            weather_noise_sigma_c=0.0,
        )
        gen = ExogenousSignalGenerator(random.Random(0), cfg)
        # July 14 = doy 196 → peak
        # January 14 = doy 14 → near trough
        rows = gen.generate([date(2024, 7, 14), date(2024, 1, 14)], [1])
        by_date = {r["date"]: r["value"] for r in rows}
        # Peak is roughly mean + amplitude; trough roughly mean - amplitude.
        assert by_date[date(2024, 7, 14)] > by_date[date(2024, 1, 14)]
        assert abs(by_date[date(2024, 7, 14)] - 25.0) < 0.5
        assert by_date[date(2024, 1, 14)] < 10.0

    def test_weather_reproducible(self):
        cfg = ExogenousSignalConfig(enable_weather=True)
        gen1 = ExogenousSignalGenerator(random.Random(7), cfg)
        gen2 = ExogenousSignalGenerator(random.Random(7), cfg)
        dates = _date_range(date(2024, 1, 1), 30)
        assert gen1.generate(dates, [1, 2]) == gen2.generate(dates, [1, 2])


class TestMacroIndex:
    def test_macro_row_per_date(self):
        cfg = ExogenousSignalConfig(enable_macro=True)
        gen = ExogenousSignalGenerator(random.Random(42), cfg)
        dates = _date_range(date(2024, 6, 1), 10)
        rows = gen.generate(dates, [])
        macro = [r for r in rows if r["signal_name"] == MACRO_SIGNAL_NAME]
        assert len(macro) == len(dates)
        for r in macro:
            assert r["is_global"] is True
            assert r["store_id"] is None

    def test_macro_random_walk_changes_value(self):
        cfg = ExogenousSignalConfig(
            enable_macro=True, macro_initial_value=100.0, macro_step_sigma=1.0
        )
        gen = ExogenousSignalGenerator(random.Random(1), cfg)
        dates = _date_range(date(2024, 1, 1), 30)
        rows = [r for r in gen.generate(dates, []) if r["signal_name"] == MACRO_SIGNAL_NAME]
        values = [r["value"] for r in rows]
        # The first value already has one rng step applied so it's not
        # exactly 100; just confirm the walk produces variation.
        assert len({round(v, 6) for v in values}) > 1
        assert abs(values[0] - 100.0) < 5.0  # one small step

    def test_zero_step_sigma_yields_constant(self):
        cfg = ExogenousSignalConfig(
            enable_macro=True, macro_initial_value=42.0, macro_step_sigma=0.0
        )
        gen = ExogenousSignalGenerator(random.Random(99), cfg)
        rows = gen.generate(_date_range(date(2024, 1, 1), 5), [])
        macro_values = [r["value"] for r in rows if r["signal_name"] == MACRO_SIGNAL_NAME]
        assert all(math.isclose(v, 42.0) for v in macro_values)


class TestEvents:
    def test_events_only_within_range(self):
        cfg = ExogenousSignalConfig(
            enable_events=True,
            event_dates=[date(2024, 1, 3), date(2025, 6, 1)],
        )
        gen = ExogenousSignalGenerator(random.Random(0), cfg)
        rows = gen.generate(_date_range(date(2024, 1, 1), 31), [])
        events = [r for r in rows if r["signal_name"] == EVENT_SIGNAL_NAME]
        # 2024-01-03 is in range; 2025-06-01 is not.
        assert len(events) == 1
        assert events[0]["date"] == date(2024, 1, 3)
        assert events[0]["value"] == 1.0
        assert events[0]["is_global"] is True

    def test_events_disabled_emits_nothing(self):
        cfg = ExogenousSignalConfig(enable_events=False, event_dates=[date(2024, 1, 3)])
        gen = ExogenousSignalGenerator(random.Random(0), cfg)
        rows = gen.generate(_date_range(date(2024, 1, 1), 31), [])
        assert all(r["signal_name"] != EVENT_SIGNAL_NAME for r in rows)
