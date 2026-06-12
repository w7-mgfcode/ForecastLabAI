"""Integration tests for the scenarios routes.

Runs against a real PostgreSQL database and a real model bundle on disk — the
full path from HTTP request through artifact resolution, forecast, adjustment,
and persistence. Requires ``docker compose up -d``.
"""

import random
import uuid
from collections.abc import AsyncGenerator
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.data_platform.models import Calendar, Product, SalesDaily, Store
from app.features.scenarios.models import ScenarioPlan
from app.shared.seeder.config import RetailPatternConfig, SparsityConfig, TimeSeriesConfig
from app.shared.seeder.generators import SalesDailyGenerator, build_price_lookup

# A price window covering the test bundle's 14-day horizon (train_end 2026-06-30).
_PRICE_ASSUMPTION = {
    "price": {"change_pct": -0.15, "start_date": "2026-07-01", "end_date": "2026-07-14"},
}

# Grain for the seeded end-to-end repro (issue #237) — deliberately high IDs no
# seeder uses, mirroring the TEST_STORE_ID convention in conftest.py.
_SEEDED_STORE_ID = 990101
_SEEDED_PRODUCT_ID = 990102
_SEEDED_BASE_PRICE = Decimal("10.00")
_SEEDED_START = date(2026, 2, 1)
_SEEDED_END = date(2026, 6, 30)  # the training origin T; horizon is July 1..14


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

    async def test_list_scenarios_filters_by_workspace_tag(
        self, client: AsyncClient, trained_model: str
    ) -> None:
        """E3 (#392) — plans tagged workspace:<label> are retrievable by tag.

        Proves the umbrella #389 criterion verbatim: two plans saved with a
        workspace tag come back from ``GET /scenarios?tags=workspace:<label>``
        — and adding a second tag narrows by JSONB containment (AND).
        The tag is unique per run so a shared/stale DB can't skew the counts.
        """
        workspace_tag = f"workspace:e3-it-{uuid.uuid4().hex[:8]}"
        created_ids: list[str] = []
        try:
            for name, kind in (
                ("showcase-price-cut-10pct", "price"),
                ("showcase-holiday-uplift", "holiday"),
            ):
                create = await client.post(
                    "/scenarios",
                    json={
                        "name": name,
                        "run_id": trained_model,
                        "horizon": 14,
                        "assumptions": _PRICE_ASSUMPTION,
                        "tags": ["showcase", kind, "source:showcase", workspace_tag],
                    },
                )
                assert create.status_code == 201
                created_ids.append(create.json()["scenario_id"])

            # Control plan WITHOUT the workspace tag — must not match the filter.
            control = await client.post(
                "/scenarios",
                json={
                    "name": "ephemeral-control",
                    "run_id": trained_model,
                    "horizon": 14,
                    "assumptions": _PRICE_ASSUMPTION,
                    "tags": ["showcase", "price", "source:showcase"],
                },
            )
            assert control.status_code == 201
            created_ids.append(control.json()["scenario_id"])

            listed = await client.get("/scenarios", params={"tags": [workspace_tag]})
            assert listed.status_code == 200
            data = listed.json()
            assert data["total"] == 2
            assert {item["scenario_id"] for item in data["scenarios"]} == set(created_ids[:2])

            # Containment is AND — a second tag narrows to the price plan only.
            narrowed = await client.get("/scenarios", params={"tags": [workspace_tag, "price"]})
            assert narrowed.status_code == 200
            narrowed_data = narrowed.json()
            assert narrowed_data["total"] == 1
            assert narrowed_data["scenarios"][0]["scenario_id"] == created_ids[0]
        finally:
            for scenario_id in created_ids:
                await client.delete(f"/scenarios/{scenario_id}")

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
        """A regression baseline re-forecasts — and the delta is non-zero.

        The conftest bundle is trained price-sensitive (demand falls with
        ``price_factor``), so a price cut MUST lift the re-forecast. This is
        the assertion gap issue #237 closed: the LightGBM twin always pinned
        ``units_delta > 0.0``; the regression twin — the exact model type from
        the issue's repro — only pinned the method.
        """
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
        assert data["disclaimer"], "every comparison must carry a non-empty disclaimer"
        assert len(data["points"]) == 14
        # A price cut moves the re-forecast — the deltas are model-driven, not
        # a fixed multiplier, and the modelled price response lifts demand.
        assert data["units_delta"] > 0.0

    async def test_regression_deeper_cut_moves_at_least_as_much(
        self, client: AsyncClient, trained_regression_model: str
    ) -> None:
        """A -40% cut moves demand at least as much as -15% — never less.

        ``>=`` (not ``>``) is deliberate: HistGBR bins features by TRAINING
        quantiles, so a scenario price below the trained range saturates at
        the lowest bin instead of extrapolating linearly (issue #237).
        """
        deltas: dict[float, float] = {}
        for change_pct in (-0.15, -0.40):
            response = await client.post(
                "/scenarios/simulate",
                json={
                    "run_id": trained_regression_model,
                    "horizon": 14,
                    "assumptions": {
                        "price": {
                            "change_pct": change_pct,
                            "start_date": "2026-07-01",
                            "end_date": "2026-07-14",
                        },
                    },
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["method"] == "model_exogenous"
            deltas[change_pct] = data["units_delta"]

        assert deltas[-0.15] > 0.0
        assert deltas[-0.40] >= deltas[-0.15]

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

    async def test_prophet_like_baseline_returns_model_exogenous(
        self, client: AsyncClient, trained_prophet_like_model: str
    ) -> None:
        """A prophet_like baseline is feature-aware — it re-forecasts (MLZOO-C2).

        Pins that the capability-based dispatch in ``ScenarioService.simulate``
        (the ``bundle.model.requires_features`` branch) routes the pure-sklearn
        additive model through the genuine re-forecast path with zero scenarios
        changes — no flag, no optional dependency.
        """
        response = await client.post(
            "/scenarios/simulate",
            json={
                "run_id": trained_prophet_like_model,
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


@pytest.fixture
async def seeded_price_elastic_grain(
    db_session: AsyncSession,
) -> AsyncGenerator[tuple[int, int], None]:
    """Seed one (store, product) grain whose sales carry real price variance.

    Inserts the dimension rows, the calendar days the grain needs (skipping
    any that already exist — CI shares the Postgres service), and sales rows
    generated by ``SalesDailyGenerator`` WITH a price lookup: three multi-week
    -20% price windows, so a trained regression model sees ``price_factor``
    spanning {0.8, 1.0} and can learn the demand response (issue #237).
    Everything inserted here is removed on teardown.
    """
    days = [
        _SEEDED_START + timedelta(days=offset)
        for offset in range((_SEEDED_END - _SEEDED_START).days + 1)
    ]

    db_session.add(Store(id=_SEEDED_STORE_ID, code=f"S{_SEEDED_STORE_ID}", name="Seeded E2E Store"))
    db_session.add(
        Product(
            id=_SEEDED_PRODUCT_ID,
            sku=f"SKU{_SEEDED_PRODUCT_ID}",
            name="Seeded E2E Product",
            base_price=_SEEDED_BASE_PRICE,
        )
    )

    existing_dates = set(
        (
            await db_session.execute(
                select(Calendar.date).where(
                    Calendar.date >= _SEEDED_START, Calendar.date <= _SEEDED_END
                )
            )
        )
        .scalars()
        .all()
    )
    inserted_dates = [day for day in days if day not in existing_dates]
    for day in inserted_dates:
        db_session.add(
            Calendar(
                date=day,
                day_of_week=day.weekday(),
                month=day.month,
                quarter=(day.month - 1) // 3 + 1,
                year=day.year,
            )
        )

    # Three -20% windows of varying, non-week-aligned lengths so price_factor
    # — not a quantity lag — is the cleanest predictor of the demand lift.
    cut_price = Decimal("8.00")
    price_lookup = build_price_lookup(
        [
            {
                "product_id": _SEEDED_PRODUCT_ID,
                "store_id": None,
                "price": cut_price,
                "valid_from": window_start,
                "valid_to": window_end,
            }
            for window_start, window_end in (
                (date(2026, 3, 1), date(2026, 3, 18)),
                (date(2026, 4, 10), date(2026, 4, 30)),
                (date(2026, 5, 20), date(2026, 6, 5)),
            )
        ]
    )
    generator = SalesDailyGenerator(
        random.Random(42),
        TimeSeriesConfig(
            base_demand=100,
            trend="none",
            weekly_seasonality=[1.0] * 7,
            monthly_seasonality={},
            noise_sigma=0.05,
            anomaly_probability=0.0,
        ),
        # A strong elasticity so the learnable signal dwarfs the 5% noise:
        # -20% price x -2.0 elasticity = +40% demand inside each window.
        RetailPatternConfig(price_elasticity=-2.0),
        SparsityConfig(),
        [],
    )
    sales_rows = generator.generate(
        [_SEEDED_STORE_ID],
        [(_SEEDED_PRODUCT_ID, _SEEDED_BASE_PRICE)],
        days,
        {},
        {},
        price_lookup=price_lookup,
    )
    for row in sales_rows:
        db_session.add(SalesDaily(**row))
    await db_session.commit()

    try:
        yield (_SEEDED_STORE_ID, _SEEDED_PRODUCT_ID)
    finally:
        await db_session.execute(
            delete(SalesDaily).where(
                SalesDaily.store_id == _SEEDED_STORE_ID,
                SalesDaily.product_id == _SEEDED_PRODUCT_ID,
            )
        )
        if inserted_dates:
            await db_session.execute(delete(Calendar).where(Calendar.date.in_(inserted_dates)))
        await db_session.execute(delete(Product).where(Product.id == _SEEDED_PRODUCT_ID))
        await db_session.execute(delete(Store).where(Store.id == _SEEDED_STORE_ID))
        await db_session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
class TestModelExogenousOnSeededData:
    """Issue #237's repro, automated: seed → train regression → simulate.

    This is the end-to-end proof the fix targets. On pre-fix dev the seeder
    emitted a constant ``unit_price``, the trained model learned zero price
    elasticity, and any price assumption returned an exact 0.0 delta. With
    the price/sales coupling on, a freshly seeded grain trains a model whose
    re-forecast genuinely responds to a price cut.
    """

    async def test_seeded_train_simulate_price_cut_moves_demand(
        self, client: AsyncClient, seeded_price_elastic_grain: tuple[int, int]
    ) -> None:
        """A price cut on a model trained on coupled seeded data → non-zero delta."""
        store_id, product_id = seeded_price_elastic_grain

        train = await client.post(
            "/forecasting/train",
            json={
                "store_id": store_id,
                "product_id": product_id,
                "train_start_date": _SEEDED_START.isoformat(),
                "train_end_date": _SEEDED_END.isoformat(),
                "config": {"model_type": "regression"},
            },
        )
        assert train.status_code == 200, train.text
        model_path = Path(train.json()["model_path"])
        run_id = model_path.stem.removeprefix("model_")

        try:
            response = await client.post(
                "/scenarios/simulate",
                json={
                    "run_id": run_id,
                    "horizon": 14,
                    "assumptions": {
                        "price": {
                            "change_pct": -0.20,
                            "start_date": "2026-07-01",
                            "end_date": "2026-07-14",
                        },
                    },
                },
            )
            assert response.status_code == 200, response.text
            data = response.json()

            assert data["method"] == "model_exogenous"
            assert data["units_delta"] != 0.0
        finally:
            model_path.unlink(missing_ok=True)


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
