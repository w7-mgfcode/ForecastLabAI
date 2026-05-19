"""Integration tests for the scenarios routes.

Runs against a real PostgreSQL database and a real model bundle on disk — the
full path from HTTP request through artifact resolution, forecast, adjustment,
and persistence. Requires ``docker compose up -d``.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.scenarios.models import ScenarioPlan

# A price window covering the test bundle's 14-day horizon (train_end 2026-06-30).
_PRICE_ASSUMPTION = {
    "price": {"change_pct": -0.15, "start_date": "2026-07-01", "end_date": "2026-07-14"},
}


@pytest.mark.integration
@pytest.mark.asyncio
class TestSimulate:
    """Integration tests for POST /scenarios/simulate."""

    async def test_simulate_happy_path(self, client: AsyncClient, trained_model: str) -> None:
        """A price-cut simulation returns a full, well-formed comparison."""
        response = await client.post(
            "/scenarios/simulate",
            json={"run_id": trained_model, "horizon": 14, "assumptions": _PRICE_ASSUMPTION},
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["points"]) == 14
        assert data["horizon"] == 14
        assert data["method"] == "heuristic"
        assert data["disclaimer"], "every comparison must carry a non-empty disclaimer"
        # A price cut lifts demand — the scenario total must exceed the baseline.
        assert data["units_delta"] > 0.0
        assert data["scenario_total_units"] > data["baseline_total_units"]
        for point in data["points"]:
            assert point["applied_factor"] > 1.0

    async def test_simulate_empty_assumptions_equals_baseline(
        self, client: AsyncClient, trained_model: str
    ) -> None:
        """An empty ScenarioAssumptions yields scenario == baseline, all deltas 0."""
        response = await client.post(
            "/scenarios/simulate",
            json={"run_id": trained_model, "horizon": 10, "assumptions": {}},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["units_delta"] == 0.0
        assert data["revenue_delta"] == 0.0
        assert data["coverage_verdict"] == "unknown"
        for point in data["points"]:
            assert point["delta"] == 0.0
            assert point["applied_factor"] == 1.0

    async def test_simulate_bogus_run_id_returns_404(self, client: AsyncClient) -> None:
        """A run_id with no artifact returns an RFC 7807 404 — never a 500."""
        response = await client.post(
            "/scenarios/simulate",
            json={"run_id": "does-not-exist-999", "horizon": 14, "assumptions": {}},
        )

        assert response.status_code == 404
        assert response.status_code != 500
        assert "application/problem+json" in response.headers.get("content-type", "")

    async def test_simulate_invalid_horizon_rejected(self, client: AsyncClient) -> None:
        """horizon below the ge=1 bound returns 422."""
        response = await client.post(
            "/scenarios/simulate",
            json={"run_id": "anything", "horizon": 0, "assumptions": {}},
        )
        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestScenarioPlanCrud:
    """Integration tests for the scenario_plan CRUD endpoints."""

    async def test_crud_round_trip(self, client: AsyncClient, trained_model: str) -> None:
        """A plan can be created, listed, fetched, and deleted."""
        create = await client.post(
            "/scenarios",
            json={
                "name": "Summer price cut",
                "run_id": trained_model,
                "horizon": 14,
                "assumptions": _PRICE_ASSUMPTION,
            },
        )
        assert create.status_code == 201
        plan = create.json()
        scenario_id = plan["scenario_id"]
        assert plan["name"] == "Summer price cut"
        assert plan["method"] == "heuristic"
        assert len(plan["comparison"]["points"]) == 14

        listed = await client.get("/scenarios")
        assert listed.status_code == 200
        list_data = listed.json()
        assert list_data["total"] >= 1
        assert scenario_id in {item["scenario_id"] for item in list_data["scenarios"]}

        fetched = await client.get(f"/scenarios/{scenario_id}")
        assert fetched.status_code == 200
        assert fetched.json()["comparison"]["units_delta"] > 0.0

        deleted = await client.delete(f"/scenarios/{scenario_id}")
        assert deleted.status_code == 204

        missing = await client.get(f"/scenarios/{scenario_id}")
        assert missing.status_code == 404

    async def test_list_scenarios_empty_is_200(self, client: AsyncClient) -> None:
        """GET /scenarios returns 200 + an empty list, never 404."""
        response = await client.get("/scenarios")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["scenarios"], list)
        assert data["total"] >= 0

    async def test_get_missing_plan_returns_404(self, client: AsyncClient) -> None:
        """Fetching an unknown scenario_id returns 404."""
        response = await client.get(f"/scenarios/{uuid.uuid4().hex}")
        assert response.status_code == 404

    async def test_delete_missing_plan_returns_404(self, client: AsyncClient) -> None:
        """Deleting an unknown scenario_id returns 404."""
        response = await client.delete(f"/scenarios/{uuid.uuid4().hex}")
        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestSimulateModelExogenous:
    """Integration tests for the model-driven (regression) simulate path."""

    async def test_regression_baseline_returns_model_exogenous(
        self, client: AsyncClient, trained_regression_model: str
    ) -> None:
        """A regression baseline re-forecasts — method is 'model_exogenous'."""
        response = await client.post(
            "/scenarios/simulate",
            json={
                "run_id": trained_regression_model,
                "horizon": 14,
                "assumptions": _PRICE_ASSUMPTION,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert data["method"] == "model_exogenous"

    async def test_lightgbm_baseline_returns_model_exogenous(
        self, client: AsyncClient, trained_lightgbm_model: str
    ) -> None:
        """A LightGBM baseline is feature-aware — it re-forecasts (PRP-30).

        Pins the capability-based dispatch in ``ScenarioService.simulate`` —
        the branch is ``bundle.model.requires_features``, not a hard-coded
        ``model_type == "regression"`` string.
        """
        response = await client.post(
            "/scenarios/simulate",
            json={
                "run_id": trained_lightgbm_model,
                "horizon": 14,
                "assumptions": _PRICE_ASSUMPTION,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert data["method"] == "model_exogenous"
        assert data["disclaimer"], "every comparison must carry a non-empty disclaimer"
        assert len(data["points"]) == 14
        assert data["disclaimer"], "every comparison must carry a non-empty disclaimer"
        assert len(data["points"]) == 14
        # A price cut moves the re-forecast — the deltas are model-driven, not
        # a fixed multiplier, and the modelled price response lifts demand.
        assert data["units_delta"] > 0.0

    async def test_xgboost_baseline_returns_model_exogenous(
        self, client: AsyncClient, trained_xgboost_model: str
    ) -> None:
        """An XGBoost baseline is feature-aware — it re-forecasts (PRP-MLZOO-C1).

        Pins the capability-based dispatch in ``ScenarioService.simulate`` —
        the branch is ``bundle.model.requires_features``, not a hard-coded
        ``model_type == "regression"`` string.
        """
        response = await client.post(
            "/scenarios/simulate",
            json={
                "run_id": trained_xgboost_model,
                "horizon": 14,
                "assumptions": _PRICE_ASSUMPTION,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert data["method"] == "model_exogenous"
        assert data["disclaimer"], "every comparison must carry a non-empty disclaimer"
        assert len(data["points"]) == 14

    async def test_regression_empty_assumptions_equals_baseline(
        self, client: AsyncClient, trained_regression_model: str
    ) -> None:
        """With no assumptions the model re-forecasts to exactly the baseline."""
        response = await client.post(
            "/scenarios/simulate",
            json={"run_id": trained_regression_model, "horizon": 10, "assumptions": {}},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["method"] == "model_exogenous"
        assert data["units_delta"] == 0.0
        for point in data["points"]:
            assert point["delta"] == 0.0

    async def test_baseline_forecaster_still_heuristic(
        self, client: AsyncClient, trained_model: str
    ) -> None:
        """A naive baseline still produces a heuristic comparison — unchanged."""
        response = await client.post(
            "/scenarios/simulate",
            json={"run_id": trained_model, "horizon": 14, "assumptions": _PRICE_ASSUMPTION},
        )
        assert response.status_code == 200
        assert response.json()["method"] == "heuristic"

    async def test_model_exogenous_plan_persists(
        self, client: AsyncClient, trained_regression_model: str
    ) -> None:
        """A model_exogenous comparison saves cleanly — the widened CHECK accepts it."""
        create = await client.post(
            "/scenarios",
            json={
                "name": "Model-driven price cut",
                "run_id": trained_regression_model,
                "horizon": 14,
                "assumptions": _PRICE_ASSUMPTION,
            },
        )
        assert create.status_code == 201
        plan = create.json()
        assert plan["method"] == "model_exogenous"

        fetched = await client.get(f"/scenarios/{plan['scenario_id']}")
        assert fetched.status_code == 200
        assert fetched.json()["comparison"]["method"] == "model_exogenous"


@pytest.mark.integration
@pytest.mark.asyncio
class TestScenarioPlanModel:
    """Constraint tests for the ScenarioPlan ORM model."""

    async def test_method_check_rejects_unknown_value(self, db_session: AsyncSession) -> None:
        """The method CHECK constraint rejects a value outside the allow-list."""
        plan = ScenarioPlan(
            scenario_id=uuid.uuid4().hex,
            name="bad method",
            store_id=1,
            product_id=1,
            run_id="abc",
            horizon=7,
            assumptions={},
            comparison={},
            method="not_a_method",
        )
        db_session.add(plan)
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_method_check_accepts_model_exogenous(self, db_session: AsyncSession) -> None:
        """The widened CHECK constraint accepts the 'model_exogenous' method."""
        plan = ScenarioPlan(
            scenario_id=uuid.uuid4().hex,
            name="model exogenous plan",
            store_id=1,
            product_id=1,
            run_id="abc",
            horizon=7,
            assumptions={},
            comparison={},
            method="model_exogenous",
        )
        db_session.add(plan)
        await db_session.commit()
        await db_session.refresh(plan)
        assert plan.method == "model_exogenous"
