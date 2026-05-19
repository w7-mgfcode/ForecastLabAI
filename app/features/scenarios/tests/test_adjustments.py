"""Unit tests for the pure scenario adjustment engine.

These run without a database (-m "not integration"): every function in
``adjustments.py`` is pure. The tests assert *direction and bounds* — a price
cut lifts demand, the clamp keeps a factor in band — not exact magnitudes, so
re-tuning the heuristic constants does not break them.
"""

from datetime import date

import pytest

from app.features.scenarios import adjustments
from app.features.scenarios.schemas import (
    HolidayAssumption,
    InventoryAssumption,
    LifecycleAssumption,
    PriceAssumption,
    PromotionAssumption,
    ScenarioAssumptions,
)

# =============================================================================
# clamp
# =============================================================================


def test_clamp_inside_range_returns_value() -> None:
    """A value already in range is returned unchanged."""
    assert adjustments.clamp(0.5, 0.1, 5.0) == 0.5


def test_clamp_below_and_above() -> None:
    """Values outside the range snap to the nearest bound."""
    assert adjustments.clamp(-3.0, 0.1, 5.0) == 0.1
    assert adjustments.clamp(99.0, 0.1, 5.0) == 5.0


# =============================================================================
# price_factor
# =============================================================================


def test_price_cut_lifts_demand() -> None:
    """A price cut (negative change) yields a factor above 1."""
    assert adjustments.price_factor(-0.15) > 1.0


def test_price_rise_drags_demand() -> None:
    """A price rise (positive change) yields a factor below 1."""
    assert adjustments.price_factor(0.20) < 1.0


def test_price_factor_no_change_is_neutral() -> None:
    """A zero price change is exactly neutral."""
    assert adjustments.price_factor(0.0) == 1.0


def test_price_factor_tolerates_non_positive_price() -> None:
    """A change of -100% or worse clamps to the upper band, never raises."""
    assert adjustments.price_factor(-1.0) == adjustments.FACTOR_BAND[1]
    assert adjustments.price_factor(-5.0) == adjustments.FACTOR_BAND[1]


def test_price_factor_stays_in_band() -> None:
    """The factor never escapes the clamp band for extreme inputs."""
    lo, hi = adjustments.FACTOR_BAND
    for change in (-0.95, -0.5, 0.0, 1.0, 5.0):
        assert lo <= adjustments.price_factor(change) <= hi


# =============================================================================
# promotion_factor / holiday_factor / lifecycle_factor
# =============================================================================


def test_promotion_factor_known_kinds_lift_demand() -> None:
    """Every known promotion kind lifts demand when active."""
    for kind in ("pct_off", "bogo", "bundle", "markdown"):
        assert adjustments.promotion_factor(kind, active=True) > 1.0


def test_promotion_factor_inactive_or_unknown_is_neutral() -> None:
    """An inactive promotion or an unknown kind is neutral."""
    assert adjustments.promotion_factor("pct_off", active=False) == 1.0
    assert adjustments.promotion_factor("mystery", active=True) == 1.0


def test_holiday_factor() -> None:
    """A holiday lifts demand; a non-holiday is neutral."""
    assert adjustments.holiday_factor(True) > 1.0
    assert adjustments.holiday_factor(False) == 1.0


def test_lifecycle_factor_known_stages() -> None:
    """Known lifecycle stages map to their documented multipliers."""
    assert adjustments.lifecycle_factor("launch") > 1.0
    assert adjustments.lifecycle_factor("maturity") == 1.0
    assert adjustments.lifecycle_factor("decline") < 1.0


def test_lifecycle_factor_none_or_unknown_is_neutral() -> None:
    """``None`` and an unknown stage are neutral, never an exception."""
    assert adjustments.lifecycle_factor(None) == 1.0
    assert adjustments.lifecycle_factor("zombie") == 1.0


# =============================================================================
# combined_daily_factor
# =============================================================================


def test_combined_factor_empty_assumptions_is_neutral() -> None:
    """An empty ScenarioAssumptions yields exactly 1.0 for any day."""
    assert adjustments.combined_daily_factor(date(2026, 6, 1), ScenarioAssumptions()) == 1.0


def test_combined_factor_applies_price_inside_window() -> None:
    """A price assumption applies only inside its date window."""
    assumptions = ScenarioAssumptions(
        price=PriceAssumption(
            change_pct=-0.20, start_date=date(2026, 6, 5), end_date=date(2026, 6, 10)
        )
    )
    inside = adjustments.combined_daily_factor(date(2026, 6, 7), assumptions)
    outside = adjustments.combined_daily_factor(date(2026, 6, 20), assumptions)
    assert inside > 1.0
    assert outside == 1.0


def test_combined_factor_stacks_promotion_and_holiday() -> None:
    """Overlapping promotion and holiday assumptions compound multiplicatively."""
    day = date(2026, 6, 7)
    assumptions = ScenarioAssumptions(
        promotion=PromotionAssumption(
            kind="bogo", start_date=date(2026, 6, 1), end_date=date(2026, 6, 30)
        ),
        holiday=HolidayAssumption(dates=[day]),
    )
    assert adjustments.combined_daily_factor(day, assumptions) > 1.0


def test_combined_factor_is_clamped() -> None:
    """Even a stack of strong uplifts stays within the clamp band."""
    lo, hi = adjustments.FACTOR_BAND
    assumptions = ScenarioAssumptions(
        price=PriceAssumption(
            change_pct=-0.9, start_date=date(2026, 6, 1), end_date=date(2026, 6, 30)
        ),
        promotion=PromotionAssumption(
            kind="bogo", start_date=date(2026, 6, 1), end_date=date(2026, 6, 30)
        ),
        holiday=HolidayAssumption(dates=[date(2026, 6, 7)]),
        lifecycle=LifecycleAssumption(stage="launch"),
    )
    assert lo <= adjustments.combined_daily_factor(date(2026, 6, 7), assumptions) <= hi


# =============================================================================
# apply_adjustment
# =============================================================================


def test_apply_adjustment_element_wise() -> None:
    """Each baseline value is multiplied by its matching factor."""
    assert adjustments.apply_adjustment([10.0, 20.0], [1.5, 0.5]) == [15.0, 10.0]


def test_apply_adjustment_floors_at_zero() -> None:
    """A negative product is floored at 0.0 — demand is never negative."""
    assert adjustments.apply_adjustment([10.0], [-1.0]) == [0.0]


def test_apply_adjustment_length_mismatch_raises() -> None:
    """A length mismatch is a caller-contract violation and raises ValueError."""
    with pytest.raises(ValueError, match="equal length"):
        adjustments.apply_adjustment([1.0, 2.0], [1.0])


# =============================================================================
# coverage_verdict
# =============================================================================


def test_coverage_verdict_unknown_without_inventory() -> None:
    """No inventory assumption yields an 'unknown' verdict."""
    assert adjustments.coverage_verdict(100.0, None) == "unknown"


def test_coverage_verdict_covered_at_risk_stockout() -> None:
    """Demand vs. on-hand stock maps to the three coverage bands."""
    assert adjustments.coverage_verdict(50.0, 100) == "covered"
    assert adjustments.coverage_verdict(100.0, 100) == "at_risk"
    assert adjustments.coverage_verdict(500.0, 100) == "stockout"


def test_coverage_verdict_zero_stock() -> None:
    """Zero stock is a stockout when any demand exists."""
    assert adjustments.coverage_verdict(10.0, 0) == "stockout"
    assert adjustments.coverage_verdict(0.0, 0) == "at_risk"


def test_coverage_verdict_uses_inventory_assumption_field() -> None:
    """The verdict reads on_hand_units straight off the assumption model."""
    inventory = InventoryAssumption(on_hand_units=100)
    assert adjustments.coverage_verdict(50.0, inventory.on_hand_units) == "covered"
