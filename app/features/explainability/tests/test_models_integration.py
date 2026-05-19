"""Integration tests for the ForecastExplanation ORM model.

Run against the real docker-compose Postgres (``docker compose up -d``).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.explainability.models import ForecastExplanation


@pytest.mark.integration
@pytest.mark.asyncio
class TestForecastExplanationModel:
    """CRUD and constraint tests for the forecast_explanation table."""

    async def test_insert_and_read_back(
        self, db_session: AsyncSession, explanation_row_kwargs: dict[str, Any]
    ) -> None:
        """A forecast_explanation row persists and reads back intact."""
        row = ForecastExplanation(**explanation_row_kwargs)
        db_session.add(row)
        await db_session.commit()

        fetched = (
            await db_session.execute(
                select(ForecastExplanation).where(
                    ForecastExplanation.explanation_id == explanation_row_kwargs["explanation_id"]
                )
            )
        ).scalar_one()
        assert fetched.forecast_value == 42.0
        assert fetched.model_type == "naive"
        assert fetched.confidence == "medium"
        assert fetched.drivers[0]["name"] == "last_observation"
        assert fetched.created_at is not None

    async def test_confidence_check_constraint_rejects_bad_value(
        self, db_session: AsyncSession, explanation_row_kwargs: dict[str, Any]
    ) -> None:
        """An out-of-allow-list confidence value is rejected by the CHECK."""
        bad = ForecastExplanation(**{**explanation_row_kwargs, "confidence": "bogus"})
        db_session.add(bad)
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()

    async def test_method_check_constraint_rejects_bad_value(
        self, db_session: AsyncSession, explanation_row_kwargs: dict[str, Any]
    ) -> None:
        """An out-of-allow-list method value is rejected by the CHECK."""
        bad = ForecastExplanation(**{**explanation_row_kwargs, "method": "telepathy"})
        db_session.add(bad)
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()
