"""Pure deterministic adjustment engine for scenario simulation.

Every function here is a pure factor computation — no DB, no I/O, no mutation
of its inputs, and it NEVER raises on junk input (a negative price change, an
unknown promotion kind, a ``None`` lifecycle stage all return a sane factor).

DECISIONS LOCKED (PRP-26 #1): the baseline forecasters ignore exogenous
regressors, so a what-if cannot be answered by re-prediction. The MVP applies
these factors as a post-forecast multiplier on a baseline forecast. Each factor
is a documented, tunable constant so a reviewer can see and adjust the
heuristic; the tests assert direction and bounds, not exact magnitudes.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.features.scenarios.schemas import ScenarioAssumptions

# Constant-elasticity price response: factor = (1 + change_pct) ** PRICE_ELASTICITY.
# A negative elasticity means a price cut (change_pct < 0) lifts demand.
PRICE_ELASTICITY: float = -1.2

# Multiplicative demand uplift per promotion kind (1.0 == no effect).
PROMOTION_UPLIFT_BY_KIND: dict[str, float] = {
    "pct_off": 1.25,
    "bogo": 1.40,
    "bundle": 1.15,
    "markdown": 1.30,
}

# Demand uplift applied on a holiday / event day.
HOLIDAY_UPLIFT: float = 1.30

# Demand multiplier per forced product lifecycle stage.
LIFECYCLE_FACTOR: dict[str, float] = {
    "launch": 1.2,
    "growth": 1.1,
    "maturity": 1.0,
    "decline": 0.85,
}

# Clamp band — keeps a combined factor away from a zero / explosive forecast.
FACTOR_BAND: tuple[float, float] = (0.1, 5.0)

# Relative band around on-hand stock within which coverage is "at_risk".
COVERAGE_AT_RISK_BAND: float = 0.10

CoverageVerdict = Literal["covered", "at_risk", "stockout", "unknown"]


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp ``value`` into the inclusive ``[lo, hi]`` range."""
    return max(lo, min(hi, value))


def price_factor(price_change_pct: float) -> float:
    """Return the demand multiplier for a relative price change.

    Constant-elasticity response: ``(1 + change) ** PRICE_ELASTICITY``. A price
    cut (negative change) yields a factor > 1; a price rise yields < 1.
    Tolerates junk — a change of -100% or worse (a non-positive price) clamps to
    the upper band rather than raising or returning a complex / NaN value.
    """
    base = 1.0 + price_change_pct
    if base <= 0.0:
        return FACTOR_BAND[1]
    return clamp(base**PRICE_ELASTICITY, *FACTOR_BAND)


def promotion_factor(kind: str, active: bool) -> float:
    """Return the demand multiplier for a promotion of ``kind``.

    Returns ``1.0`` when the promotion is not active or the kind is unknown.
    """
    if not active:
        return 1.0
    return PROMOTION_UPLIFT_BY_KIND.get(kind, 1.0)


def holiday_factor(is_holiday: bool) -> float:
    """Return the demand multiplier for a holiday / event day."""
    return HOLIDAY_UPLIFT if is_holiday else 1.0


def lifecycle_factor(stage: str | None) -> float:
    """Return the demand multiplier for a product lifecycle stage.

    Returns ``1.0`` for ``None`` or an unknown stage.
    """
    if stage is None:
        return 1.0
    return LIFECYCLE_FACTOR.get(stage, 1.0)


def _in_window(point_date: date, start: date, end: date) -> bool:
    """True when ``point_date`` is inside the inclusive ``[start, end]`` window.

    A reversed window (``start`` after ``end``) is normalised rather than
    treated as empty — junk input must not raise.
    """
    lo, hi = (start, end) if start <= end else (end, start)
    return lo <= point_date <= hi


def combined_daily_factor(point_date: date, assumptions: ScenarioAssumptions) -> float:
    """Multiply every applicable per-day factor for ``point_date``, then clamp.

    Time-safety: every window test is keyed on ``point_date`` — always a horizon
    (future) date — so an assumption window that falls entirely before the
    forecast start contributes factor ``1.0`` and can never reach back into the
    historical series. An empty ``ScenarioAssumptions`` yields exactly ``1.0``.
    """
    factor = 1.0

    price = assumptions.price
    if price is not None and _in_window(point_date, price.start_date, price.end_date):
        factor *= price_factor(price.change_pct)

    promotion = assumptions.promotion
    if promotion is not None and _in_window(point_date, promotion.start_date, promotion.end_date):
        factor *= promotion_factor(promotion.kind, active=True)

    holiday = assumptions.holiday
    if holiday is not None and point_date in holiday.dates:
        factor *= holiday_factor(True)

    lifecycle = assumptions.lifecycle
    if lifecycle is not None:
        factor *= lifecycle_factor(lifecycle.stage)

    return clamp(factor, *FACTOR_BAND)


def apply_adjustment(baseline: list[float], factors: list[float]) -> list[float]:
    """Element-wise multiply ``baseline`` by ``factors``, flooring each at 0.0.

    Returns a NEW list — the input ``baseline`` is never mutated (the leakage
    spec depends on this). Raises ``ValueError`` on a length mismatch: that is a
    caller-contract violation, not junk data.
    """
    if len(baseline) != len(factors):
        raise ValueError(
            f"baseline and factors must be equal length: {len(baseline)} != {len(factors)}"
        )
    return [max(0.0, value * factor) for value, factor in zip(baseline, factors, strict=True)]


def coverage_verdict(scenario_total_units: float, on_hand_units: int | None) -> CoverageVerdict:
    """Classify whether projected demand is covered by on-hand stock.

    Returns ``unknown`` when no inventory assumption was supplied. Otherwise:
    ``covered`` when demand sits comfortably below stock, ``at_risk`` when it is
    within ``COVERAGE_AT_RISK_BAND`` of stock, ``stockout`` when it exceeds that
    band. Never raises.
    """
    if on_hand_units is None:
        return "unknown"
    if on_hand_units <= 0:
        return "stockout" if scenario_total_units > 0.0 else "at_risk"
    upper = on_hand_units * (1.0 + COVERAGE_AT_RISK_BAND)
    lower = on_hand_units * (1.0 - COVERAGE_AT_RISK_BAND)
    if scenario_total_units > upper:
        return "stockout"
    if scenario_total_units >= lower:
        return "at_risk"
    return "covered"
