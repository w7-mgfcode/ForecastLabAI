"""Phase 2 product-lifecycle demand multiplier.

This module is pure compute — no DB writes. ``SalesDailyGenerator`` calls
``LifecycleGenerator.multiplier_for`` once per (product, date) to apply
intro / growth / maturity / decline / discontinued shaping on top of the
base demand math. When the feature is disabled the call returns 1.0
without consuming any rng state, preserving the byte-identical
regression invariant.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.shared.seeder.config import LifecycleConfig


class LifecycleGenerator:
    """Compute per-(product, date) demand multipliers from lifecycle stages.

    The model has four ramp segments stitched together:

    - ``intro``     — linear ramp from ``intro_multiplier`` to 1.0 over
      ``intro_ramp_days`` starting at ``launch_date``.
    - ``growth``    — held at 1.0 for ``growth_ramp_days``.
    - ``maturity``  — held at 1.0 for ``maturity_steady_days``.
    - ``decline``   — exponential decay toward ``decline_multiplier`` with
      e-folding time ``decline_decay_days``.

    After ``discontinue_date`` the multiplier is forced to 0 regardless of
    the curves, modelling a hard end-of-life.
    """

    def __init__(self, config: LifecycleConfig | None) -> None:
        """Initialize the lifecycle generator.

        Args:
            config: Phase 2 lifecycle configuration. When ``None`` or
                ``enable=False`` every call returns 1.0.
        """
        self.config = config

    @property
    def enabled(self) -> bool:
        return self.config is not None and self.config.enable

    def stage_for(
        self,
        current_date: date,
        launch_date: date | None,
        discontinue_date: date | None,
    ) -> str:
        """Return the lifecycle stage label for ``current_date``.

        The label is one of ``intro|growth|maturity|decline|discontinued``.
        When the generator is disabled or ``launch_date`` is missing we
        return ``"maturity"`` as a neutral default that produces a
        multiplier of 1.0 in :meth:`multiplier_for`.
        """
        if not self.enabled or launch_date is None or self.config is None:
            return "maturity"
        if discontinue_date is not None and current_date >= discontinue_date:
            return "discontinued"
        days_since_launch = (current_date - launch_date).days
        if days_since_launch < 0:
            # Product hasn't launched yet — treat as discontinued so demand
            # collapses to 0 in `multiplier_for`.
            return "discontinued"
        cfg = self.config
        boundary_intro = cfg.intro_ramp_days
        boundary_growth = boundary_intro + cfg.growth_ramp_days
        boundary_maturity = boundary_growth + cfg.maturity_steady_days
        if days_since_launch < boundary_intro:
            return "intro"
        if days_since_launch < boundary_growth:
            return "growth"
        if days_since_launch < boundary_maturity:
            return "maturity"
        return "decline"

    def multiplier_for(
        self,
        current_date: date,
        launch_date: date | None,
        discontinue_date: date | None,
    ) -> float:
        """Return the lifecycle demand multiplier for ``current_date``.

        Returns 1.0 when the generator is disabled or the product has no
        launch date — preserving pre-Phase-2 output byte-for-byte for
        callers that don't opt in.
        """
        if not self.enabled or launch_date is None or self.config is None:
            return 1.0
        cfg = self.config
        # Hard end-of-life after discontinue.
        if discontinue_date is not None and current_date >= discontinue_date:
            return 0.0
        days_since_launch = (current_date - launch_date).days
        if days_since_launch < 0:
            return 0.0  # Not yet launched.
        boundary_intro = cfg.intro_ramp_days
        boundary_growth = boundary_intro + cfg.growth_ramp_days
        boundary_maturity = boundary_growth + cfg.maturity_steady_days

        if days_since_launch < boundary_intro:
            # Linear ramp intro_multiplier -> 1.0.
            if cfg.intro_ramp_days <= 0:
                return 1.0
            t = days_since_launch / cfg.intro_ramp_days
            return cfg.intro_multiplier + (1.0 - cfg.intro_multiplier) * t
        if days_since_launch < boundary_maturity:
            # Growth + maturity held at 1.0.
            return 1.0
        # Decline: exponential decay from 1.0 toward decline_multiplier.
        days_in_decline = days_since_launch - boundary_maturity
        if cfg.decline_decay_days <= 0:
            return cfg.decline_multiplier
        # m(t) = decline + (1 - decline) * exp(-t / tau)
        import math  # local import keeps top-of-module surface lean

        decay = math.exp(-days_in_decline / cfg.decline_decay_days)
        return cfg.decline_multiplier + (1.0 - cfg.decline_multiplier) * decay
