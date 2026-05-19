"""Service layer for the Scenario Simulation slice.

``ScenarioService`` does two things:

* **simulate** — resolve a baseline model artifact, run its forecast, apply the
  pure deterministic factors from ``adjustments.py``, and return a
  ``ScenarioComparison``. Stateless.
* **CRUD** — persist a comparison as a named ``scenario_plan`` row, then list /
  fetch / delete saved plans.

DECISIONS LOCKED (PRP-26 #2): this service must NOT import a sibling slice's
``service.py``. It imports only the stable lower-level building block
``load_model_bundle`` from ``forecasting/persistence.py`` and produces the
baseline forecast by calling ``bundle.model.predict(horizon)`` directly —
replicating the ``ForecastPoint``-construction block of
``ForecastingService.predict`` rather than calling that class. Read-only ORM
imports of sibling ``models.py`` (``data_platform``) are allowed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.features.data_platform.models import SalesDaily
from app.features.forecasting.persistence import ModelBundle, load_model_bundle
from app.features.scenarios import adjustments
from app.features.scenarios.models import SCENARIO_METHOD_HEURISTIC, ScenarioPlan
from app.features.scenarios.schemas import (
    CreateScenarioRequest,
    ScenarioAssumptions,
    ScenarioComparison,
    ScenarioListItem,
    ScenarioListResponse,
    ScenarioPlanResponse,
    ScenarioPoint,
    SimulateScenarioRequest,
)

logger = get_logger(__name__)

# Plain-language caveat stamped on every comparison — the NIST-AI-RMF
# transparency control against over-trusting a heuristic number.
HEURISTIC_DISCLAIMER = (
    "Heuristic estimate: this scenario applies fixed, deterministic adjustment "
    "factors to a baseline forecast — it is not a re-trained, causal model. "
    "Treat the demand and revenue deltas as directional planning signals, not "
    "precise predictions."
)

# Fallback unit price when a (store, product) has no sales history.
DEFAULT_UNIT_PRICE = 1.0


class ScenarioService:
    """Stateless simulation plus saved-plan CRUD for scenario planning."""

    # -- Simulation --------------------------------------------------------

    async def simulate(
        self, db: AsyncSession, request: SimulateScenarioRequest
    ) -> ScenarioComparison:
        """Run a baseline forecast and apply the what-if assumptions.

        Args:
            db: Database session (used only to estimate a unit price).
            request: The baseline ``run_id``, horizon, and assumptions.

        Returns:
            A full baseline-vs-scenario comparison.

        Raises:
            FileNotFoundError: When no model artifact exists for ``run_id``.
            ValueError: When the artifact path is invalid or its metadata is
                missing the store / product identity.
        """
        bundle = self._load_baseline_bundle(request.run_id)

        store_id_raw = bundle.metadata.get("store_id")
        product_id_raw = bundle.metadata.get("product_id")
        if store_id_raw is None or product_id_raw is None:
            raise ValueError(
                f"Model artifact for run_id '{request.run_id}' is missing "
                "store_id / product_id metadata."
            )
        store_id = int(str(store_id_raw))
        product_id = int(str(product_id_raw))

        # Replicate the ForecastingService.predict body (DECISIONS LOCKED #2).
        raw_forecast = bundle.model.predict(request.horizon)
        baseline_values = [float(value) for value in raw_forecast]
        start_date = self._forecast_start_date(bundle.metadata.get("train_end_date"))

        # Per-day deterministic factors — adjustments.py is pure.
        factors: list[float] = []
        for offset in range(request.horizon):
            point_date = start_date + timedelta(days=offset)
            factors.append(adjustments.combined_daily_factor(point_date, request.assumptions))
        scenario_values = adjustments.apply_adjustment(baseline_values, factors)

        points = [
            ScenarioPoint(
                date=start_date + timedelta(days=offset),
                baseline=baseline_values[offset],
                scenario=scenario_values[offset],
                delta=scenario_values[offset] - baseline_values[offset],
                applied_factor=factors[offset],
            )
            for offset in range(request.horizon)
        ]

        baseline_total = sum(baseline_values)
        scenario_total = sum(scenario_values)
        units_delta = scenario_total - baseline_total
        units_delta_pct = (units_delta / baseline_total * 100.0) if baseline_total > 0 else 0.0

        unit_price = await self._latest_unit_price(db, store_id, product_id)
        baseline_revenue = baseline_total * unit_price
        scenario_revenue = scenario_total * unit_price

        inventory = request.assumptions.inventory
        on_hand = inventory.on_hand_units if inventory is not None else None
        verdict = adjustments.coverage_verdict(scenario_total, on_hand)

        logger.info(
            "scenarios.simulated",
            run_id=request.run_id,
            store_id=store_id,
            product_id=product_id,
            horizon=request.horizon,
            model_type=bundle.config.model_type,
            units_delta=round(units_delta, 4),
            coverage_verdict=verdict,
        )

        return ScenarioComparison(
            store_id=store_id,
            product_id=product_id,
            model_type=bundle.config.model_type,
            horizon=request.horizon,
            points=points,
            baseline_total_units=baseline_total,
            scenario_total_units=scenario_total,
            units_delta=units_delta,
            units_delta_pct=units_delta_pct,
            unit_price_used=unit_price,
            baseline_revenue=baseline_revenue,
            scenario_revenue=scenario_revenue,
            revenue_delta=scenario_revenue - baseline_revenue,
            coverage_verdict=verdict,
            method="heuristic",
            disclaimer=HEURISTIC_DISCLAIMER,
            generated_at=datetime.now(UTC),
        )

    # -- Persistence -------------------------------------------------------

    async def create_plan(
        self, db: AsyncSession, request: CreateScenarioRequest
    ) -> ScenarioPlanResponse:
        """Run a simulation and persist it as a named scenario plan.

        Args:
            db: Database session.
            request: Plan name plus the baseline / horizon / assumptions.

        Returns:
            The saved plan with its embedded comparison snapshot.

        Raises:
            FileNotFoundError: When no model artifact exists for ``run_id``.
            ValueError: When the artifact path or its metadata is invalid.
        """
        comparison = await self.simulate(
            db,
            SimulateScenarioRequest(
                run_id=request.run_id,
                horizon=request.horizon,
                assumptions=request.assumptions,
                name=request.name,
            ),
        )

        plan = ScenarioPlan(
            scenario_id=uuid.uuid4().hex,
            name=request.name,
            store_id=comparison.store_id,
            product_id=comparison.product_id,
            run_id=request.run_id,
            horizon=request.horizon,
            # JSONB cannot store Python date/datetime — dump in JSON mode.
            assumptions=request.assumptions.model_dump(mode="json"),
            comparison=comparison.model_dump(mode="json"),
            method=SCENARIO_METHOD_HEURISTIC,
        )
        db.add(plan)
        await db.commit()
        await db.refresh(plan)

        logger.info(
            "scenarios.plan_created",
            scenario_id=plan.scenario_id,
            store_id=plan.store_id,
            product_id=plan.product_id,
        )
        return self._to_plan_response(plan)

    async def list_plans(self, db: AsyncSession, limit: int, offset: int) -> ScenarioListResponse:
        """List saved scenario plans, newest first.

        Args:
            db: Database session.
            limit: Maximum plans to return.
            offset: Number of plans to skip.

        Returns:
            A page of plan list items plus the total count.
        """
        total = int(await db.scalar(select(func.count()).select_from(ScenarioPlan)) or 0)

        rows = (
            (
                await db.execute(
                    select(ScenarioPlan)
                    .order_by(ScenarioPlan.created_at.desc(), ScenarioPlan.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return ScenarioListResponse(
            scenarios=[self._to_list_item(row) for row in rows],
            total=total,
        )

    async def get_plan(self, db: AsyncSession, scenario_id: str) -> ScenarioPlanResponse | None:
        """Fetch one saved plan by its external id, or ``None`` when absent."""
        plan = await db.scalar(select(ScenarioPlan).where(ScenarioPlan.scenario_id == scenario_id))
        if plan is None:
            return None
        return self._to_plan_response(plan)

    async def delete_plan(self, db: AsyncSession, scenario_id: str) -> bool:
        """Delete a saved plan; return ``True`` when a row was removed."""
        plan = await db.scalar(select(ScenarioPlan).where(ScenarioPlan.scenario_id == scenario_id))
        if plan is None:
            return False
        await db.delete(plan)
        await db.commit()
        logger.info("scenarios.plan_deleted", scenario_id=scenario_id)
        return True

    # -- Internal helpers --------------------------------------------------

    def _load_baseline_bundle(self, run_id: str) -> ModelBundle:
        """Resolve and load the baseline model artifact for ``run_id``.

        Mirrors the load-bearing path-traversal guard in
        ``ForecastingService.predict``: reject a non-``.joblib`` suffix and any
        path that escapes the configured artifacts directory.
        """
        settings = get_settings()
        artifacts_dir = Path(settings.forecast_model_artifacts_dir).resolve()
        model_path = (artifacts_dir / f"model_{run_id}.joblib").resolve()

        if model_path.suffix != ".joblib":
            raise ValueError(f"Invalid model path for run_id '{run_id}'.")
        try:
            model_path.relative_to(artifacts_dir)
        except ValueError:
            raise ValueError(f"Invalid model path for run_id '{run_id}'.") from None
        if not model_path.exists():
            raise FileNotFoundError(f"No model artifact found for run_id '{run_id}'.")

        return load_model_bundle(model_path)

    @staticmethod
    def _forecast_start_date(train_end_raw: object) -> date:
        """Return the first forecast day — train_end_date + 1, or today + 1.

        ``train_end_date`` is persisted as an ISO string in the bundle metadata;
        when it is absent the forecast simply starts tomorrow.
        """
        if isinstance(train_end_raw, str):
            return date.fromisoformat(train_end_raw) + timedelta(days=1)
        return datetime.now(UTC).date() + timedelta(days=1)

    async def _latest_unit_price(self, db: AsyncSession, store_id: int, product_id: int) -> float:
        """Estimate a unit price from the most recent sale of this grain.

        Falls back to ``DEFAULT_UNIT_PRICE`` (and logs a warning) when the
        grain has no sales history.
        """
        price = await db.scalar(
            select(SalesDaily.unit_price)
            .where(SalesDaily.store_id == store_id, SalesDaily.product_id == product_id)
            .order_by(SalesDaily.date.desc())
            .limit(1)
        )
        if price is None:
            logger.warning(
                "scenarios.unit_price_fallback",
                store_id=store_id,
                product_id=product_id,
                fallback=DEFAULT_UNIT_PRICE,
            )
            return DEFAULT_UNIT_PRICE
        return float(price)

    @staticmethod
    def _to_plan_response(plan: ScenarioPlan) -> ScenarioPlanResponse:
        """Build a full plan response from a persisted row.

        The JSONB blobs round-trip cleanly: ``ScenarioComparison`` is not strict,
        and every ``date`` field of ``ScenarioAssumptions`` carries
        ``Field(strict=False)``, so the stored ISO strings re-validate.
        """
        return ScenarioPlanResponse(
            scenario_id=plan.scenario_id,
            name=plan.name,
            store_id=plan.store_id,
            product_id=plan.product_id,
            run_id=plan.run_id,
            horizon=plan.horizon,
            method=plan.method,
            created_at=plan.created_at,
            assumptions=ScenarioAssumptions.model_validate(plan.assumptions),
            comparison=ScenarioComparison.model_validate(plan.comparison),
        )

    @staticmethod
    def _to_list_item(plan: ScenarioPlan) -> ScenarioListItem:
        """Build a compact list row, reading the deltas from the snapshot."""
        return ScenarioListItem(
            scenario_id=plan.scenario_id,
            name=plan.name,
            store_id=plan.store_id,
            product_id=plan.product_id,
            horizon=plan.horizon,
            units_delta=float(plan.comparison.get("units_delta", 0.0)),
            revenue_delta=float(plan.comparison.get("revenue_delta", 0.0)),
            created_at=plan.created_at,
        )
