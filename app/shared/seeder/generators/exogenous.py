"""Exogenous signal generator (weather, macro index, event flags).

Phase 1 of the seeder realism extension. Produces rows for the
``exogenous_signal`` table. Each enabled signal contributes records;
disabled signals contribute zero rows so callers that don't opt in see
no Phase 1 side effects.

The output schema matches ``app.features.data_platform.models.ExogenousSignal``:

    {"date", "signal_name", "store_id", "is_global", "value"}

Reproducibility: this generator uses the seeder's ``random.Random`` instance
(NOT numpy.random) so identical seeds produce identical signal series.
"""

from __future__ import annotations

import math
import random
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.shared.seeder.config import ExogenousSignalConfig


WEATHER_SIGNAL_NAME = "weather_temp_c"
MACRO_SIGNAL_NAME = "macro_index"
EVENT_SIGNAL_NAME = "event_flag"


class ExogenousSignalGenerator:
    """Generator for exogenous demand signals.

    Produces one row per (signal, date[, store]) for each enabled signal:

    - ``weather_temp_c``: per (store, date). Temperature in °C following a
      yearly sin wave with Gaussian noise. ``is_global=False``.
    - ``macro_index``: per date. Random walk starting at
      ``macro_initial_value``. ``is_global=True``.
    - ``event_flag``: per ``event_dates`` entry. Binary 1.0 marker.
      ``is_global=True``.
    """

    def __init__(self, rng: random.Random, config: ExogenousSignalConfig) -> None:
        """Initialize the generator.

        Args:
            rng: Seeded random number generator.
            config: Exogenous signal configuration.
        """
        self.rng = rng
        self.config = config

    def _weather_row(
        self,
        signal_date: date,
        store_id: int,
        day_of_year: int,
    ) -> dict[str, date | int | bool | str | float | None]:
        """Compute one weather sample for (store, date).

        Uses a sinusoidal seasonal cycle around the climatological mean with
        peak in mid-July (day-of-year 196) for the northern hemisphere.
        """
        # Phase chosen so peak is around day 196 (mid-July): sin peaks at π/2,
        # so we want 2π(d - 105)/365 = π/2 → d = 196.
        phase_rad = 2.0 * math.pi * (day_of_year - 105) / 365.0
        seasonal = self.config.weather_amplitude_c * math.sin(phase_rad)
        noise = self.rng.gauss(0.0, self.config.weather_noise_sigma_c)
        value = self.config.weather_climatology_mean_c + seasonal + noise
        return {
            "date": signal_date,
            "signal_name": WEATHER_SIGNAL_NAME,
            "store_id": store_id,
            "is_global": False,
            "value": value,
        }

    def _macro_rows(
        self, dates: list[date]
    ) -> list[dict[str, date | int | bool | str | float | None]]:
        """Random-walk macro index, one row per date."""
        records: list[dict[str, date | int | bool | str | float | None]] = []
        value = self.config.macro_initial_value
        for d in dates:
            value += self.rng.gauss(0.0, self.config.macro_step_sigma)
            records.append(
                {
                    "date": d,
                    "signal_name": MACRO_SIGNAL_NAME,
                    "store_id": None,
                    "is_global": True,
                    "value": value,
                }
            )
        return records

    def _event_rows(
        self, dates: list[date]
    ) -> list[dict[str, date | int | bool | str | float | None]]:
        """Binary event-flag rows for configured event dates within range."""
        if not self.config.event_dates:
            return []
        date_set = set(dates)
        return [
            {
                "date": event_date,
                "signal_name": EVENT_SIGNAL_NAME,
                "store_id": None,
                "is_global": True,
                "value": 1.0,
            }
            for event_date in self.config.event_dates
            if event_date in date_set
        ]

    def generate(
        self, dates: list[date], store_ids: list[int]
    ) -> list[dict[str, date | int | bool | str | float | None]]:
        """Generate exogenous signal rows.

        Args:
            dates: Dates in the seeded range (sorted ascending).
            store_ids: Store IDs for per-store signals.

        Returns:
            List of row dicts ready for batch insert. Empty when no signal
            is enabled.
        """
        records: list[dict[str, date | int | bool | str | float | None]] = []

        if self.config.enable_weather and store_ids and dates:
            # Iterate stores in the outer loop so the rng draws per store
            # are deterministic and reproducible.
            for store_id in store_ids:
                for d in dates:
                    records.append(self._weather_row(d, store_id, d.timetuple().tm_yday))

        if self.config.enable_macro and dates:
            records.extend(self._macro_rows(dates))

        if self.config.enable_events:
            records.extend(self._event_rows(dates))

        return records
