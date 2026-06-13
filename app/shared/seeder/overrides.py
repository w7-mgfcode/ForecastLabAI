"""Curated, allow-listed seed-override schema (E3, issue #409).

Shared between the seeder slice (``GenerateParams.overrides``) and the demo
slice (``DemoRunRequest.seed_overrides``) -- ``app/shared`` is the sanctioned
cross-slice home (vertical-slice rule; precedent: ``ScenarioPreset`` is
imported by both slices from ``app.shared.seeder.config``).

``extra="forbid"`` IS the allow-list: any knob not listed here is a 422 at
the HTTP boundary (umbrella #406 risk mitigation -- the seeder's full 25+
knob surface stays preset-driven; only these 7 curated knobs are exposed).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SeederOverrides(BaseModel):
    """The 7 curated seed knobs, applied LAST in ``_build_config_from_params``.

    Precedence: preset -> scalar ``stores``/``products``/``sparsity`` params ->
    phase 1/2 overrides -> THIS object (wins). Each knob maps onto one
    ``SeederConfig`` sub-dataclass field via ``dataclasses.replace`` so
    preset-customized sibling fields survive.
    """

    # strict=True catches JSON-native coercion bugs ("5" -> 5); every field is
    # int/float so no Field(strict=False) override is needed (see
    # docs/_base/SECURITY.md -> "Pydantic v2 strict mode").
    model_config = ConfigDict(strict=True, extra="forbid")

    stores: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description=("Store count -> DimensionConfig.stores; wins over the scalar `stores` param."),
    )
    products: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description=(
            "Product count -> DimensionConfig.products; wins over the scalar `products` param."
        ),
    )
    window_days: int | None = Field(
        default=None,
        ge=75,
        le=365,
        description=(
            "Seeded window length; start_date = end_date - window_days. >=75 keeps "
            "the showcase historical_backfill gate clear. Rejected on the "
            "calendar-pinned holiday_rush preset (demo surface)."
        ),
    )
    sparsity: float | None = Field(
        default=None,
        ge=0.0,
        le=0.9,
        description=(
            "Missing (store,product) grain fraction -> "
            "SparsityConfig.missing_combinations_pct; preserves the preset's gap "
            "config. 1.0 disallowed (would seed zero series)."
        ),
    )
    promotion_intensity: float | None = Field(
        default=None,
        ge=0.0,
        le=0.5,
        description="-> RetailPatternConfig.promotion_probability (preset max 0.25).",
    )
    stockout_intensity: float | None = Field(
        default=None,
        ge=0.0,
        le=0.5,
        description=(
            "-> RetailPatternConfig.stockout_probability. High values can "
            "legitimately NaN-WAPE-fail the backtest (documented expected outcome)."
        ),
    )
    noise_sigma: float | None = Field(
        default=None,
        ge=0.0,
        le=0.5,
        description="-> TimeSeriesConfig.noise_sigma (preset max 0.4).",
    )

    def is_empty(self) -> bool:
        """True when no knob is set (``{}`` on the wire) -- treated as None everywhere."""
        return not self.model_dump(exclude_none=True)
