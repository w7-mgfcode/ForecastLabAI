"""Integration test for the demo showcase pipeline.

Exercises ``POST /demo/run`` end-to-end against a real Postgres database via
the in-process ASGITransport ``client`` fixture (``tests/conftest.py``).

Requires ``docker-compose up -d`` + ``alembic upgrade head``. Marked
``integration`` so it is excluded from the fast unit run.
"""

import pytest

pytestmark = pytest.mark.integration


async def test_demo_run_pipeline_end_to_end(client):
    """Seed demo_minimal, run the demo pipeline, and verify the registered winner."""
    # Precondition: seed the demo_minimal scenario so skip_seed=true has data.
    seed_resp = await client.post(
        "/seeder/generate",
        json={
            "scenario": "demo_minimal",
            "seed": 42,
            "stores": 3,
            "products": 10,
            "start_date": "2024-10-01",
            "end_date": "2024-12-31",
            "sparsity": 0.0,
            "dry_run": False,
        },
    )
    assert seed_resp.status_code == 201, seed_resp.text

    try:
        resp = await client.post(
            "/demo/run",
            json={"skip_seed": True, "reset": False},
        )
        assert resp.status_code == 200, resp.text
        result = resp.json()

        # Every step must end pass or skip; nothing failed.
        assert result["overall_status"] == "pass", result
        for step in result["steps"]:
            assert step["status"] in {"pass", "skip"}, step

        # A backtest winner was selected and registered.
        assert result["winner_model_type"] is not None
        assert result["winner_wape"] is not None
        assert result["winning_run_id"] is not None
        assert result["alias"] == "demo-production"

        # The demo-production alias resolves to the winning run.
        alias_resp = await client.get("/registry/aliases/demo-production")
        assert alias_resp.status_code == 200, alias_resp.text
        assert alias_resp.json()["run_id"] == result["winning_run_id"]
    finally:
        # Best-effort teardown -- drop the alias the run created.
        await client.delete("/registry/aliases/demo-production")
