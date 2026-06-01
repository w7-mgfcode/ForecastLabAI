"""Deterministic forecast-decision layer for the champion selector (Slice C).

Pure functions — NO LLM, NO DB, NO I/O (mirror ``explanations.py``). Translate a
horizon forecast into an inventory-decision heuristic a planner can act on:
peak/low demand day, a CLEARLY-LABELED safety-stock heuristic, and bias-risk
wording.

The safety-stock formula is the demand-variability-only form (King 2011,
constant lead time):

    safety_stock = z(service_level) * sigma_daily * sqrt(lead_time_days)
    expected_demand_over_lead_time = average_demand * lead_time_days
    reorder_point = expected_demand_over_lead_time + safety_stock

``z`` comes from a fixed one-sided service-level lookup (NO scipy); an
in-between service level falls back to the nearest table key. Every field is
labeled ``method="heuristic"`` and carries a caveat — this output NEVER feeds
ranking (LOCKED #3).
"""

from __future__ import annotations

import statistics
from datetime import date
from typing import Any

from app.features.model_selection.schemas import ForecastDecision

# LOCKED #4 — the canonical bias sentence, kept byte-identical to the frontend
# ``BIAS_EXPLANATION`` constant (``components/champion-selector/copy.ts``) so the
# wording never drifts between the two surfaces.
BIAS_EXPLANATION = (
    "Positive bias means the model under-forecasts (risk of stockouts); "
    "negative bias means it over-forecasts (risk of overstock)."
)

# One-sided service-level z values (NO scipy dependency). Source: King 2011
# safety-stock z-from-service-level table.
_Z_TABLE: dict[float, float] = {0.90: 1.2816, 0.95: 1.6449, 0.975: 1.9600, 0.99: 2.3263}

_CAVEATS = [
    "Safety stock is a deterministic heuristic (demand variability only; constant lead time).",
    "Not a substitute for a full inventory-optimisation model.",
]


def z_for_service_level(service_level: float) -> float:
    """Return the one-sided z for a service level (exact key, else nearest).

    An exact table key returns its z directly; any other level snaps to the
    nearest table key (documented heuristic — the table is coarse on purpose).
    """
    if service_level in _Z_TABLE:
        return _Z_TABLE[service_level]
    nearest = min(_Z_TABLE, key=lambda key: abs(key - service_level))
    return _Z_TABLE[nearest]


def _coerce_date(value: object) -> date | None:
    """Coerce a point's ``date`` (ISO string in JSON-mode dumps, or a date)."""
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def forecast_peak_low(
    points: list[dict[str, Any]],
) -> tuple[date | None, float | None, date | None, float | None]:
    """Return ``(peak_date, peak_demand, low_date, low_demand)`` over points.

    Picks the max/min ``forecast`` value; ``(None, None, None, None)`` on an
    empty forecast. Ties resolve to the first occurrence (deterministic).
    """
    if not points:
        return (None, None, None, None)
    peak = max(points, key=lambda p: float(p["forecast"]))
    low = min(points, key=lambda p: float(p["forecast"]))
    return (
        _coerce_date(peak.get("date")),
        float(peak["forecast"]),
        _coerce_date(low.get("date")),
        float(low["forecast"]),
    )


def _bias_direction(winner_bias: float | None) -> str:
    """Plain-English direction phrase for a winner's bias sign."""
    if winner_bias is None:
        return "has no recorded bias measurement"
    if winner_bias > 0:
        return "under-forecasts (risk of stockouts)"
    if winner_bias < 0:
        return "over-forecasts (risk of overstock)"
    return "is roughly unbiased"


def compute_forecast_decision(
    points: list[dict[str, Any]],
    average_demand: float,
    lead_time_days: int,
    service_level: float,
    winner_bias: float | None,
) -> ForecastDecision:
    """Build the deterministic, labeled inventory-decision heuristic.

    ``sigma_daily`` is the POPULATION stdev of the forecast values; a flat or
    single-point forecast yields ``sigma=0`` → ``safety_stock=0`` (honest, not
    an error).
    """
    values = [float(p["forecast"]) for p in points]
    sigma_daily = statistics.pstdev(values) if len(values) > 1 else 0.0
    z = z_for_service_level(service_level)
    safety_stock = z * sigma_daily * (lead_time_days**0.5)
    expected_lt = average_demand * lead_time_days
    bias_dir = _bias_direction(winner_bias)
    if winner_bias is None:
        bias_text = f"{BIAS_EXPLANATION} For this winner, bias {bias_dir}."
    else:
        bias_text = (
            f"{BIAS_EXPLANATION} For this winner, bias {winner_bias:.2f} indicates it {bias_dir}."
        )
    return ForecastDecision(
        lead_time_days=lead_time_days,
        service_level=service_level,
        z_value=z,
        sigma_daily_demand=sigma_daily,
        expected_demand_over_lead_time=expected_lt,
        safety_stock=safety_stock,
        reorder_point=expected_lt + safety_stock,
        bias_risk_text=bias_text,
        caveats=list(_CAVEATS),
    )
