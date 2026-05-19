"""Unit tests for the scenario request / response schemas.

The critical case exercises the FastAPI ``validate_python`` path — calling
``model_validate`` on a dict with ISO-string dates — to prove the
``Field(strict=False)`` overrides on every ``date`` field hold. Without them
every HTTP caller would 422 (see ``docs/_base/SECURITY.md``).
"""

from datetime import date

import pytest
from pydantic import ValidationError

from app.features.scenarios.schemas import (
    CreateScenarioRequest,
    PriceAssumption,
    ScenarioAssumptions,
    SimulateScenarioRequest,
)


def test_simulate_request_accepts_iso_string_dates() -> None:
    """A JSON-shaped dict with ISO-string dates validates (validate_python path)."""
    request = SimulateScenarioRequest.model_validate(
        {
            "run_id": "abc123def456",
            "horizon": 14,
            "assumptions": {
                "price": {
                    "change_pct": -0.15,
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-14",
                },
                "holiday": {"dates": ["2026-06-07", "2026-06-08"]},
            },
        }
    )
    assert request.assumptions.price is not None
    assert request.assumptions.price.start_date == date(2026, 6, 1)
    assert request.assumptions.holiday is not None
    assert request.assumptions.holiday.dates == [date(2026, 6, 7), date(2026, 6, 8)]


def test_simulate_request_defaults_to_empty_assumptions() -> None:
    """Omitting ``assumptions`` yields an empty (no-change) ScenarioAssumptions."""
    request = SimulateScenarioRequest.model_validate({"run_id": "abc", "horizon": 7})
    assert isinstance(request.assumptions, ScenarioAssumptions)
    assert request.assumptions.price is None
    assert request.assumptions.promotion is None


def test_price_assumption_change_pct_bounds() -> None:
    """change_pct outside [-0.9, 5.0] is rejected."""
    with pytest.raises(ValidationError):
        PriceAssumption.model_validate(
            {"change_pct": -1.5, "start_date": "2026-06-01", "end_date": "2026-06-14"}
        )
    with pytest.raises(ValidationError):
        PriceAssumption.model_validate(
            {"change_pct": 9.0, "start_date": "2026-06-01", "end_date": "2026-06-14"}
        )


def test_simulate_request_horizon_bounds() -> None:
    """horizon must be within 1..90."""
    with pytest.raises(ValidationError):
        SimulateScenarioRequest.model_validate({"run_id": "abc", "horizon": 0})
    with pytest.raises(ValidationError):
        SimulateScenarioRequest.model_validate({"run_id": "abc", "horizon": 200})


def test_create_request_requires_name() -> None:
    """CreateScenarioRequest requires a non-empty name."""
    with pytest.raises(ValidationError):
        CreateScenarioRequest.model_validate({"name": "", "run_id": "abc", "horizon": 14})
    request = CreateScenarioRequest.model_validate(
        {"name": "Summer discount", "run_id": "abc", "horizon": 14}
    )
    assert request.name == "Summer discount"
