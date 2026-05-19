"""End-to-end integration tests for the explainability endpoints.

Run against the real docker-compose Postgres (``docker compose up -d``). The
``client`` fixture shares the test session, so a persisted explanation is
readable back through the same session after the request.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.explainability.models import ForecastExplanation
from app.features.explainability.tests.conftest import TEST_END


@pytest.mark.integration
@pytest.mark.asyncio
class TestExplainEndpointsIntegration:
    """End-to-end tests over a real database."""

    async def test_explain_run_returns_explanation(
        self, client: AsyncClient, seeded_run: str
    ) -> None:
        """GET /explain/runs/{run_id} explains a real baseline run."""
        response = await client.get(f"/explain/runs/{seeded_run}")
        assert response.status_code == 200
        body = response.json()
        assert body["model_type"] == "naive"
        assert body["method"] == "rule_based"
        assert body["drivers"]
        assert body["confidence"] in ("high", "medium", "low")
        assert body["caveats"]
        assert body["agent_summary"]
        # The naive forecast is the last observed value — a positive quantity.
        assert body["forecast_value"] > 0

    async def test_explain_run_persists_row(
        self, client: AsyncClient, db_session: AsyncSession, seeded_run: str
    ) -> None:
        """The explanation is persisted as a forecast_explanation row."""
        await client.get(f"/explain/runs/{seeded_run}")
        row = (
            await db_session.execute(
                select(ForecastExplanation).where(ForecastExplanation.run_id == seeded_run)
            )
        ).scalar_one()
        assert row.model_type == "naive"
        assert row.run_id == seeded_run

    async def test_explain_forecast_end_to_end(
        self, client: AsyncClient, seeded_series: dict[str, int]
    ) -> None:
        """POST /explain/forecast explains an ad-hoc forecast over a real series."""
        response = await client.post(
            "/explain/forecast",
            json={
                "store_id": seeded_series["store_id"],
                "product_id": seeded_series["product_id"],
                "model_type": "seasonal_naive",
                "as_of_date": TEST_END.isoformat(),
                "season_length": 7,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["model_type"] == "seasonal_naive"
        assert body["drivers"][0]["name"] == "season_match"
        assert body["forecast_value"] > 0

    async def test_explain_run_missing_returns_404(self, client: AsyncClient) -> None:
        """GET /explain/runs/{missing} returns an RFC 7807 404."""
        response = await client.get("/explain/runs/no-such-run-id")
        assert response.status_code == 404
        body = response.json()
        assert body["status"] == 404
        assert "title" in body

    async def test_explain_job_missing_returns_404(self, client: AsyncClient) -> None:
        """GET /explain/jobs/{missing} returns an RFC 7807 404."""
        response = await client.get("/explain/jobs/no-such-job-id")
        assert response.status_code == 404
        assert response.json()["status"] == 404
