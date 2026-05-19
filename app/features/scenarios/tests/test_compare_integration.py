"""Integration tests for the scenario library + multi-scenario comparison.

PRP-27 Phase C. Runs against a real PostgreSQL database and a real model
bundle on disk. Requires ``docker compose up -d``.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

_PRICE_CUT: dict[str, object] = {
    "price": {"change_pct": -0.15, "start_date": "2026-07-01", "end_date": "2026-07-14"},
}
_PRICE_RISE: dict[str, object] = {
    "price": {"change_pct": 0.20, "start_date": "2026-07-01", "end_date": "2026-07-14"},
}


async def _create_plan(
    client: AsyncClient,
    run_id: str,
    name: str,
    assumptions: dict[str, object],
    *,
    tags: list[str] | None = None,
    cloned_from: str | None = None,
) -> dict[str, Any]:
    """Create a saved scenario plan and return its JSON body."""
    body: dict[str, object] = {
        "name": name,
        "run_id": run_id,
        "horizon": 14,
        "assumptions": assumptions,
    }
    if tags is not None:
        body["tags"] = tags
    if cloned_from is not None:
        body["cloned_from"] = cloned_from
    response = await client.post("/scenarios", json=body)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


@pytest.mark.integration
@pytest.mark.asyncio
class TestCompareScenarios:
    """Integration tests for POST /scenarios/compare."""

    async def test_compare_ranks_plans(self, client: AsyncClient, trained_model: str) -> None:
        """Comparing a price cut and a price rise ranks the cut first."""
        cut = await _create_plan(client, trained_model, "Cut", _PRICE_CUT)
        rise = await _create_plan(client, trained_model, "Rise", _PRICE_RISE)

        response = await client.post(
            "/scenarios/compare",
            json={
                "scenario_ids": [rise["scenario_id"], cut["scenario_id"]],
                "rank_by": "revenue_delta",
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert data["rank_by"] == "revenue_delta"
        assert len(data["scenarios"]) == 2
        # A price cut lifts revenue, so it outranks the price rise.
        assert data["scenarios"][0]["name"] == "Cut"
        assert data["scenarios"][0]["rank"] == 1
        assert data["scenarios"][1]["rank"] == 2
        assert data["chart_series"], "chart_series must carry merged date rows"
        assert "baseline" in data["chart_series"][0]

    async def test_compare_too_few_returns_422(self, client: AsyncClient) -> None:
        """Fewer than 2 scenario_ids is rejected at the schema boundary."""
        response = await client.post("/scenarios/compare", json={"scenario_ids": ["only-one"]})
        assert response.status_code == 422

    async def test_compare_too_many_returns_422(self, client: AsyncClient) -> None:
        """More than MAX_COMPARE_SCENARIOS (5) scenario_ids is rejected."""
        response = await client.post(
            "/scenarios/compare",
            json={"scenario_ids": [f"id-{index}" for index in range(6)]},
        )
        assert response.status_code == 422

    async def test_compare_bogus_id_returns_404(
        self, client: AsyncClient, trained_model: str
    ) -> None:
        """An unknown scenario_id returns an RFC 7807 404 — never a 500."""
        plan = await _create_plan(client, trained_model, "Real", _PRICE_CUT)
        response = await client.post(
            "/scenarios/compare",
            json={"scenario_ids": [plan["scenario_id"], "does-not-exist-xyz"]},
        )
        assert response.status_code == 404
        assert "application/problem+json" in response.headers.get("content-type", "")


@pytest.mark.integration
@pytest.mark.asyncio
class TestScenarioLibrary:
    """Integration tests for tag filtering and plan cloning."""

    async def test_create_with_tags_and_filter(
        self, client: AsyncClient, trained_model: str
    ) -> None:
        """A tag filter returns only plans carrying every listed tag."""
        await _create_plan(client, trained_model, "Tagged", _PRICE_CUT, tags=["q3", "promo"])
        await _create_plan(client, trained_model, "Untagged", _PRICE_CUT, tags=[])

        response = await client.get("/scenarios", params={"tags": ["q3"]})
        assert response.status_code == 200
        data = response.json()

        names = {item["name"] for item in data["scenarios"]}
        assert "Tagged" in names
        assert "Untagged" not in names
        for item in data["scenarios"]:
            assert "q3" in item["tags"]

    async def test_clone_records_cloned_from(self, client: AsyncClient, trained_model: str) -> None:
        """A plan created with cloned_from records its origin."""
        original = await _create_plan(client, trained_model, "Original", _PRICE_CUT)
        clone = await _create_plan(
            client,
            trained_model,
            "Clone of original",
            _PRICE_CUT,
            cloned_from=original["scenario_id"],
        )
        assert clone["cloned_from"] == original["scenario_id"]

        fetched = await client.get(f"/scenarios/{clone['scenario_id']}")
        assert fetched.status_code == 200
        assert fetched.json()["cloned_from"] == original["scenario_id"]
