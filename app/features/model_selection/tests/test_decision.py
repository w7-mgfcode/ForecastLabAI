"""Unit tests for the pure forecast-decision module (Slice C).

``decision.py`` has NO DB/IO — every function is deterministic and tested here
directly (z-table, safety-stock formula, peak/low, bias wording).
"""

from __future__ import annotations

import statistics
from datetime import date

import pytest

from app.features.model_selection.decision import (
    BIAS_EXPLANATION,
    compute_forecast_decision,
    forecast_peak_low,
    z_for_service_level,
)


def _points(values: list[float], start: date = date(2026, 1, 1)) -> list[dict[str, object]]:
    """Build forecast points (JSON-mode shape: ISO date string + forecast)."""
    return [
        {
            "date": (start.fromordinal(start.toordinal() + i)).isoformat(),
            "forecast": v,
            "lower_bound": None,
            "upper_bound": None,
        }
        for i, v in enumerate(values)
    ]


# -----------------------------------------------------------------------------
# z-table
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("service_level", "expected_z"),
    [(0.90, 1.2816), (0.95, 1.6449), (0.975, 1.9600), (0.99, 2.3263)],
)
def test_decision_z_table_exact(service_level: float, expected_z: float) -> None:
    assert z_for_service_level(service_level) == expected_z


@pytest.mark.parametrize(
    ("service_level", "expected_z"),
    [(0.92, 1.2816), (0.93, 1.6449), (0.96, 1.6449), (0.98, 1.9600)],
)
def test_decision_z_table_nearest(service_level: float, expected_z: float) -> None:
    """In-between service levels snap to the nearest table key."""
    assert z_for_service_level(service_level) == expected_z


# -----------------------------------------------------------------------------
# Safety stock
# -----------------------------------------------------------------------------


def test_safety_stock_formula_matches_z_sigma_sqrt_l() -> None:
    values = [10.0, 12.0, 8.0, 11.0, 9.0]
    decision = compute_forecast_decision(
        _points(values), average_demand=10.0, lead_time_days=7, service_level=0.95, winner_bias=0.5
    )
    sigma = statistics.pstdev(values)
    expected_ss = 1.6449 * sigma * (7**0.5)
    assert decision.method == "heuristic"
    assert decision.z_value == 1.6449
    assert decision.sigma_daily_demand == pytest.approx(sigma)
    assert decision.safety_stock == pytest.approx(expected_ss)
    assert decision.expected_demand_over_lead_time == pytest.approx(70.0)
    assert decision.reorder_point == pytest.approx(70.0 + expected_ss)
    assert decision.caveats  # always carries a caveat


def test_flat_forecast_safety_stock_zero() -> None:
    """A flat (zero-variance) forecast → sigma 0 → safety stock 0 (honest)."""
    decision = compute_forecast_decision(
        _points([10.0, 10.0, 10.0]),
        average_demand=10.0,
        lead_time_days=7,
        service_level=0.95,
        winner_bias=0.0,
    )
    assert decision.sigma_daily_demand == 0.0
    assert decision.safety_stock == 0.0


def test_single_point_forecast_safety_stock_zero() -> None:
    decision = compute_forecast_decision(
        _points([42.0]),
        average_demand=42.0,
        lead_time_days=3,
        service_level=0.95,
        winner_bias=None,
    )
    assert decision.sigma_daily_demand == 0.0
    assert decision.safety_stock == 0.0


# -----------------------------------------------------------------------------
# Peak / low
# -----------------------------------------------------------------------------


def test_forecast_peak_low_picks_max_and_min() -> None:
    points = _points([10.0, 25.0, 5.0, 18.0])
    peak_date, peak_demand, low_date, low_demand = forecast_peak_low(points)
    assert peak_demand == 25.0
    assert low_demand == 5.0
    assert peak_date == date(2026, 1, 2)
    assert low_date == date(2026, 1, 3)


def test_forecast_peak_low_empty_returns_none() -> None:
    assert forecast_peak_low([]) == (None, None, None, None)


# -----------------------------------------------------------------------------
# Bias wording (LOCKED #4 — reuses BIAS_EXPLANATION)
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bias", "fragment"),
    [
        (1.5, "under-forecasts (risk of stockouts)"),
        (-1.5, "over-forecasts (risk of overstock)"),
        (0.0, "roughly unbiased"),
    ],
)
def test_bias_risk_text_under_over_neutral(bias: float, fragment: str) -> None:
    decision = compute_forecast_decision(
        _points([10.0, 12.0]),
        average_demand=11.0,
        lead_time_days=7,
        service_level=0.95,
        winner_bias=bias,
    )
    assert BIAS_EXPLANATION in decision.bias_risk_text
    assert fragment in decision.bias_risk_text


def test_bias_risk_text_handles_missing_bias() -> None:
    decision = compute_forecast_decision(
        _points([10.0, 12.0]),
        average_demand=11.0,
        lead_time_days=7,
        service_level=0.95,
        winner_bias=None,
    )
    assert BIAS_EXPLANATION in decision.bias_risk_text
    assert "no recorded bias" in decision.bias_risk_text
