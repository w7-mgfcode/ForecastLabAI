"""Service layer for the explainability slice.

``ExplainabilityService`` is READ-ONLY with respect to every other slice. It
imports ``app.features.registry.models.ModelRun`` and
``app.features.jobs.models.Job`` directly, but ONLY as read-only data contracts
— a locked maintainer decision (PRP-28 "Open Questions & Decisions" #1), the
same pattern by which slices already import ``app.features.data_platform.models``.
It NEVER imports another slice's ``service.py``.

To explain a run or job, the service re-loads the target series from
``sales_daily`` and re-fits a rule-based explainer from the stored config — it
does not reload the model artifact. Every series load and reason-code query is
bounded ``<= as_of_date`` (time-safety is load-bearing).
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import timedelta
from typing import Any

import numpy as np
import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import BadRequestError
from app.features.data_platform.models import (
    Calendar,
    InventorySnapshotDaily,
    Product,
    Promotion,
    SalesDaily,
)
from app.features.explainability.explainers import FloatArray, explainer_factory
from app.features.explainability.models import (
    ForecastExplanation as ForecastExplanationORM,
)
from app.features.explainability.reason_codes import (
    build_caveats,
    history_reason,
    holiday_reason,
    lifecycle_reason,
    promotion_reason,
    stockout_reason,
)
from app.features.explainability.schemas import (
    ConfidenceLevel,
    DriverContribution,
    ExplainForecastRequest,
    ForecastExplanation,
    ReasonCode,
)
from app.features.jobs.models import Job  # read-only data contract — see module docstring
from app.features.registry.models import (  # read-only data contract — see module docstring
    ModelRun,
)

logger = structlog.get_logger(__name__)

# Trailing window (days) used for stockout / promotion reason-code lookups.
_REASON_WINDOW_DAYS = 30


class ExplainabilityService:
    """Produces rule-based forecast explanations for the baseline models."""

    def __init__(self) -> None:
        """Initialise the service."""
        self.settings = get_settings()

    # ------------------------------------------------------------------ #
    # Public entry points
    # ------------------------------------------------------------------ #

    async def explain_forecast(
        self, db: AsyncSession, request: ExplainForecastRequest
    ) -> ForecastExplanation:
        """Explain the h=1 forecast a baseline model produces ad hoc.

        Args:
            db: Async database session.
            request: Store/product/model/cutoff parameters.

        Returns:
            The persisted forecast explanation.

        Raises:
            ValueError: For an unsupported model type or a too-short series.
        """
        return await self._explain(
            db,
            store_id=request.store_id,
            product_id=request.product_id,
            model_type=request.model_type,
            as_of_date=request.as_of_date,
            season_length=request.season_length,
            window_size=request.window_size,
            weight_strategy=request.weight_strategy,
            decay=request.decay,
            lookback_cycles=request.lookback_cycles,
            trim_outliers=request.trim_outliers,
        )

    async def explain_run(self, db: AsyncSession, run_id: str) -> ForecastExplanation | None:
        """Explain a registry ``model_run``.

        Args:
            db: Async database session.
            run_id: External run identifier.

        Returns:
            The explanation, or ``None`` when the run does not exist.

        Raises:
            ValueError: For a non-baseline run or a too-short series.
        """
        run = (
            await db.execute(select(ModelRun).where(ModelRun.run_id == run_id))
        ).scalar_one_or_none()
        if run is None:
            return None
        config: dict[str, Any] = run.model_config or {}
        return await self._explain(
            db,
            store_id=run.store_id,
            product_id=run.product_id,
            model_type=run.model_type,
            as_of_date=run.data_window_end,
            season_length=config.get("season_length"),
            window_size=config.get("window_size"),
            weight_strategy=config.get("weight_strategy"),
            decay=config.get("decay"),
            lookback_cycles=config.get("lookback_cycles"),
            trim_outliers=config.get("trim_outliers"),
            run_id=run_id,
        )

    async def explain_job(self, db: AsyncSession, job_id: str) -> ForecastExplanation | None:
        """Explain a completed ``predict`` job.

        Args:
            db: Async database session.
            job_id: External job identifier.

        Returns:
            The explanation, or ``None`` when the job does not exist.

        Raises:
            BadRequestError: When the job is not a completed predict job, or
                its result carries no forecasts.
            ValueError: For an unsupported model type or a too-short series.
        """
        job = (await db.execute(select(Job).where(Job.job_id == job_id))).scalar_one_or_none()
        if job is None:
            return None
        if job.job_type != "predict" or job.status != "completed":
            raise BadRequestError(
                message="explain_job requires a completed predict job",
                details={"job_id": job_id, "job_type": job.job_type, "status": job.status},
            )
        result: dict[str, Any] = job.result or {}
        forecasts: list[Any] = result.get("forecasts") or []
        if not forecasts:
            raise BadRequestError(
                message="predict job has no forecasts to explain",
                details={"job_id": job_id},
            )
        store_id = result.get("store_id")
        product_id = result.get("product_id")
        model_type = result.get("model_type")
        if store_id is None or product_id is None or model_type is None:
            raise BadRequestError(
                message="predict job result is missing store/product/model_type",
                details={"job_id": job_id},
            )
        # as_of_date = the day before the first forecast date (PRP-28 assumption #4).
        first_forecast_date = date_type.fromisoformat(forecasts[0]["date"])
        as_of_date = first_forecast_date - timedelta(days=1)
        return await self._explain(
            db,
            store_id=int(store_id),
            product_id=int(product_id),
            model_type=str(model_type),
            as_of_date=as_of_date,
            # A predict job's result does not record season_length/window_size;
            # the explainer falls back to the forecaster defaults (7).
            season_length=None,
            window_size=None,
            weight_strategy=None,
            decay=None,
            lookback_cycles=None,
            trim_outliers=None,
            job_id=job_id,
        )

    # ------------------------------------------------------------------ #
    # Core
    # ------------------------------------------------------------------ #

    async def _explain(
        self,
        db: AsyncSession,
        *,
        store_id: int,
        product_id: int,
        model_type: str,
        as_of_date: date_type,
        season_length: int | None,
        window_size: int | None,
        weight_strategy: str | None = None,
        decay: float | None = None,
        lookback_cycles: int | None = None,
        trim_outliers: bool | None = None,
        run_id: str | None = None,
        job_id: str | None = None,
    ) -> ForecastExplanation:
        """Build, persist, and return one rule-based explanation."""
        explainer = explainer_factory(
            model_type,
            season_length=season_length,
            window_size=window_size,
            weight_strategy=weight_strategy,
            decay=decay,
            lookback_cycles=lookback_cycles,
            trim_outliers=trim_outliers,
        )
        y, _dates = await self._load_series(db, store_id, product_id, as_of_date)
        forecast_value, drivers = explainer.explain(y)
        confidence = explainer.confidence(y)
        forecast_date = as_of_date + timedelta(days=1)

        reason_codes = await self._assemble_reason_codes(
            db,
            store_id=store_id,
            product_id=product_id,
            model_type=model_type,
            as_of_date=as_of_date,
            forecast_date=forecast_date,
            season_length=season_length,
            window_size=window_size,
            n_obs=len(y),
        )
        caveats = build_caveats(model_type, reason_codes)
        agent_summary = self._build_agent_summary(
            store_id=store_id,
            product_id=product_id,
            model_type=model_type,
            forecast_value=forecast_value,
            forecast_date=forecast_date,
            drivers=drivers,
            reason_codes=reason_codes,
            confidence=confidence,
        )
        explanation = ForecastExplanation(
            store_id=store_id,
            product_id=product_id,
            model_type=model_type,
            forecast_value=forecast_value,
            drivers=drivers,
            reason_codes=reason_codes,
            confidence=confidence,
            caveats=caveats,
            agent_summary=agent_summary,
            as_of_date=as_of_date,
        )
        await self._persist(db, explanation, run_id=run_id, job_id=job_id)
        logger.info(
            "explainability.explanation_generated",
            store_id=store_id,
            product_id=product_id,
            model_type=model_type,
            confidence=confidence.value,
            n_reason_codes=len(reason_codes),
        )
        return explanation

    async def _load_series(
        self,
        db: AsyncSession,
        store_id: int,
        product_id: int,
        end_date: date_type,
    ) -> tuple[FloatArray, list[date_type]]:
        """Load the time-ordered sales series, bounded ``<= end_date``.

        TIME-SAFETY: the ``date <= end_date`` bound is load-bearing — no data
        past the cutoff may inform an explanation.
        """
        stmt = (
            select(SalesDaily)
            .where(
                SalesDaily.store_id == store_id,
                SalesDaily.product_id == product_id,
                SalesDaily.date <= end_date,
            )
            .order_by(SalesDaily.date)
        )
        rows = (await db.execute(stmt)).scalars().all()
        y: FloatArray = np.array([float(r.quantity) for r in rows], dtype=np.float64)
        return y, [r.date for r in rows]

    async def _assemble_reason_codes(
        self,
        db: AsyncSession,
        *,
        store_id: int,
        product_id: int,
        model_type: str,
        as_of_date: date_type,
        forecast_date: date_type,
        season_length: int | None,
        window_size: int | None,
        n_obs: int,
    ) -> list[ReasonCode]:
        """Run the time-safe reason-code queries and assemble the code list."""
        window_start = as_of_date - timedelta(days=_REASON_WINDOW_DAYS)

        inventory_rows = (
            (
                await db.execute(
                    select(InventorySnapshotDaily).where(
                        InventorySnapshotDaily.store_id == store_id,
                        InventorySnapshotDaily.product_id == product_id,
                        InventorySnapshotDaily.date <= as_of_date,
                        InventorySnapshotDaily.date >= window_start,
                    )
                )
            )
            .scalars()
            .all()
        )

        promotion_rows = (
            (
                await db.execute(
                    select(Promotion).where(
                        Promotion.product_id == product_id,
                        or_(Promotion.store_id == store_id, Promotion.store_id.is_(None)),
                        Promotion.start_date <= as_of_date,
                        Promotion.end_date >= window_start,
                    )
                )
            )
            .scalars()
            .all()
        )

        product = (
            await db.execute(select(Product).where(Product.id == product_id))
        ).scalar_one_or_none()

        calendar_row = (
            await db.execute(select(Calendar).where(Calendar.date == forecast_date))
        ).scalar_one_or_none()

        # Extract primitives — the reason-code engine is DB- and ORM-free.
        stockout_flags = [row.is_stockout for row in inventory_rows]
        promotion_windows = [(row.start_date, row.end_date) for row in promotion_rows]
        launch_date = product.launch_date if product is not None else None
        is_holiday = calendar_row.is_holiday if calendar_row is not None else False
        holiday_name = calendar_row.holiday_name if calendar_row is not None else None
        min_required = self._min_required_history(model_type, season_length, window_size)

        candidates = [
            stockout_reason(stockout_flags),
            promotion_reason(promotion_windows, as_of_date),
            lifecycle_reason(launch_date, as_of_date),
            holiday_reason(is_holiday, holiday_name, forecast_date),
            history_reason(n_obs, min_required),
        ]
        return [code for code in candidates if code is not None]

    @staticmethod
    def _min_required_history(
        model_type: str, season_length: int | None, window_size: int | None
    ) -> int:
        """Comfortable minimum observation count for a confident explanation."""
        if model_type == "seasonal_naive":
            return 2 * (season_length or 7)
        if model_type == "moving_average":
            return 2 * (window_size or 7)
        if model_type == "weighted_moving_average":
            return 2 * (window_size or 7)
        if model_type == "seasonal_average":
            return 2 * (season_length or 7)
        return 14

    @staticmethod
    def _build_agent_summary(
        *,
        store_id: int,
        product_id: int,
        model_type: str,
        forecast_value: float,
        forecast_date: date_type,
        drivers: list[DriverContribution],
        reason_codes: list[ReasonCode],
        confidence: ConfidenceLevel,
    ) -> str:
        """Compose a one-paragraph natural-language summary for chat agents."""
        main_driver = drivers[0]
        sentences = [
            f"For store {store_id} / product {product_id}, the {model_type} model "
            f"forecasts {forecast_value:.1f} units for {forecast_date.isoformat()}.",
            f"The forecast is driven by '{main_driver.name}' "
            f"(value {main_driver.feature_value:.1f}).",
            f"Explanation confidence is {confidence.value}.",
        ]
        if reason_codes:
            codes = ", ".join(rc.code for rc in reason_codes)
            sentences.append(f"Advisory retail signals present: {codes}.")
        else:
            sentences.append("No advisory retail signals were detected.")
        return " ".join(sentences)

    async def _persist(
        self,
        db: AsyncSession,
        explanation: ForecastExplanation,
        *,
        run_id: str | None,
        job_id: str | None,
    ) -> None:
        """Persist the explanation as a ``forecast_explanation`` row.

        Uses ``flush``/``refresh`` — ``get_db`` auto-commits on success.
        """
        row = ForecastExplanationORM(
            explanation_id=uuid.uuid4().hex,
            run_id=run_id,
            job_id=job_id,
            store_id=explanation.store_id,
            product_id=explanation.product_id,
            model_type=explanation.model_type,
            method=explanation.method,
            as_of_date=explanation.as_of_date,
            forecast_value=explanation.forecast_value,
            confidence=explanation.confidence.value,
            drivers=[d.model_dump() for d in explanation.drivers],
            reason_codes=[rc.model_dump() for rc in explanation.reason_codes],
            caveats=list(explanation.caveats),
            agent_summary=explanation.agent_summary,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
