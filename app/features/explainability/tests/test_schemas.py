"""Unit tests for the explainability Pydantic schemas.

The JSON-path test (``test_request_accepts_iso_string_date``) is required by
``docs/_base/SECURITY.md`` — it exercises the ``validate_python`` path FastAPI
uses, catching the strict-mode date regression at unit-test time.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.features.explainability.schemas import (
    ConfidenceLevel,
    DriverContribution,
    ExplainForecastRequest,
    ForecastExplanation,
    ReasonCode,
)


class TestExplainForecastRequest:
    """Tests for the strict request body."""

    def test_request_accepts_iso_string_date(self) -> None:
        """as_of_date accepts an ISO-string (the FastAPI JSON path)."""
        request = ExplainForecastRequest.model_validate(
            {
                "store_id": 1,
                "product_id": 2,
                "model_type": "naive",
                "as_of_date": "2024-03-01",
            }
        )
        assert request.as_of_date == date(2024, 3, 1)

    def test_request_accepts_native_date(self) -> None:
        """as_of_date also accepts a native date object."""
        request = ExplainForecastRequest(
            store_id=1, product_id=2, model_type="naive", as_of_date=date(2024, 3, 1)
        )
        assert request.as_of_date == date(2024, 3, 1)

    def test_invalid_model_type_rejected(self) -> None:
        """A non-baseline model_type fails validation."""
        with pytest.raises(ValidationError):
            ExplainForecastRequest.model_validate(
                {
                    "store_id": 1,
                    "product_id": 2,
                    "model_type": "lightgbm",
                    "as_of_date": "2024-03-01",
                }
            )

    def test_non_positive_store_id_rejected(self) -> None:
        """store_id must be >= 1."""
        with pytest.raises(ValidationError):
            ExplainForecastRequest.model_validate(
                {
                    "store_id": 0,
                    "product_id": 2,
                    "model_type": "naive",
                    "as_of_date": "2024-03-01",
                }
            )

    def test_optional_params_default_to_none(self) -> None:
        """season_length and window_size default to None."""
        request = ExplainForecastRequest(
            store_id=1, product_id=2, model_type="naive", as_of_date=date(2024, 3, 1)
        )
        assert request.season_length is None
        assert request.window_size is None


class TestForecastExplanation:
    """Tests for the response schema."""

    def test_round_trips_through_model_dump(self) -> None:
        """A ForecastExplanation survives model_dump -> model_validate."""
        explanation = ForecastExplanation(
            store_id=1,
            product_id=2,
            model_type="naive",
            forecast_value=42.0,
            drivers=[
                DriverContribution(
                    name="last_observation",
                    feature_value=42.0,
                    contribution=42.0,
                    direction="positive",
                    description="x",
                )
            ],
            reason_codes=[ReasonCode(code="holiday_effect", severity="info", detail="x")],
            confidence=ConfidenceLevel.MEDIUM,
            caveats=["correlation not causation"],
            agent_summary="A summary.",
            as_of_date=date(2024, 3, 1),
        )
        restored = ForecastExplanation.model_validate(explanation.model_dump())
        assert restored.forecast_value == 42.0
        assert restored.method == "rule_based"
        assert restored.confidence == ConfidenceLevel.MEDIUM
        assert restored.drivers[0].name == "last_observation"

    def test_method_defaults_to_rule_based(self) -> None:
        """method defaults to rule_based."""
        explanation = ForecastExplanation(
            store_id=1,
            product_id=2,
            model_type="naive",
            forecast_value=1.0,
            drivers=[],
            reason_codes=[],
            confidence=ConfidenceLevel.LOW,
            caveats=[],
            agent_summary="x",
            as_of_date=date(2024, 3, 1),
        )
        assert explanation.method == "rule_based"


class TestConfidenceLevel:
    """Tests for the ConfidenceLevel enum."""

    def test_values(self) -> None:
        """The enum carries the three expected string values."""
        assert ConfidenceLevel.HIGH.value == "high"
        assert ConfidenceLevel.MEDIUM.value == "medium"
        assert ConfidenceLevel.LOW.value == "low"
