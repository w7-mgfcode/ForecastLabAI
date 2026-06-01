"""Service layer for the Forecast Champion Selector slice (issue #353).

Orchestrates pair-availability → candidate backtests → deterministic ranking →
optional winner train/predict, persisting an auditable ``model_selection_run``.

Cross-slice coupling rules (mirror ``OpsService`` + the forecasting/Batch
precedent):
- Read the data-platform ORM **models** at module scope (the sanctioned
  read-only ORM surface).
- Import sibling feature **services** (``BacktestingService`` /
  ``ForecastingService``) and the ``ModelConfig`` ``TypeAdapter`` LAZILY inside
  the methods that use them — avoids closing an alembic cold-boot import cycle.
- Reuse the backtesting ``SplitConfig`` schema directly (no cycle).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.database import get_session_maker
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    GatewayTimeoutError,
    NotFoundError,
)
from app.core.logging import get_logger
from app.features.backtesting.schemas import SplitConfig
from app.features.data_platform.models import Product, Promotion, SalesDaily, Store
from app.features.model_selection import runner
from app.features.model_selection.capabilities import build_model_catalog
from app.features.model_selection.explanations import explain_winner
from app.features.model_selection.models import (
    TERMINAL_SELECTION_STATES,
    CandidateStatus,
    ModelSelectionCandidate,
    ModelSelectionRun,
    ModelSelectionStatus,
)
from app.features.model_selection.ranking import build_chart_data, rank_candidates
from app.features.model_selection.schemas import (
    AvailabilityStatus,
    CandidateModelConfig,
    CandidateProgress,
    CandidateResult,
    ChartData,
    FoldChart,
    ForecastSummary,
    ModelCatalogResponse,
    ModelSelectionRunRequest,
    ModelSelectionRunResponse,
    PairAvailabilityResponse,
    RankingResult,
    SelectionProgress,
    SelectionWindow,
    SubmitRunResponse,
    TrainWinnerResponse,
    WinnerSummary,
)

if TYPE_CHECKING:
    from app.features.backtesting.schemas import BacktestResponse
    from app.features.forecasting.schemas import PredictResponse

logger = get_logger(__name__)

# Strong refs to detached background workers — asyncio holds only a WEAK ref to
# a bare ``create_task`` result, so without this set a worker can be GC'd
# mid-run (https://docs.python.org/3.12/library/asyncio-task.html#asyncio.create_task).
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()

# Availability policy constants (module-level; not operator-configurable in v1).
MIN_COVERAGE_RATIO = 0.8
DEFAULT_MIN_TRAIN_SIZE = 30
MAX_RECOMMENDED_SPLITS = 5

_TERMINAL_WITH_WINNER = frozenset(
    {ModelSelectionStatus.COMPLETED.value, ModelSelectionStatus.PARTIAL.value}
)


class ModelSelectionService:
    """Stateless orchestrator — a fresh ``db`` session per method."""

    # -------------------------------------------------------------------------
    # Capability catalog
    # -------------------------------------------------------------------------

    def get_model_catalog(self) -> ModelCatalogResponse:
        """Return the backend-owned candidate-model catalog (static, no I/O).

        Thin pass-through to the pure :func:`capabilities.build_model_catalog`;
        kept on the service for symmetry with ``get_availability`` / ``run``.
        """
        return build_model_catalog()

    # -------------------------------------------------------------------------
    # Availability
    # -------------------------------------------------------------------------

    async def get_availability(
        self,
        db: AsyncSession,
        store_id: int,
        product_id: int,
        forecast_horizon: int,
        split_config: SplitConfig | None = None,
    ) -> PairAvailabilityResponse:
        """Assess whether a (store, product) pair has enough history to model."""
        store = await db.get(Store, store_id)
        if store is None:
            raise NotFoundError(message=f"Store {store_id} not found")
        product = await db.get(Product, product_id)
        if product is None:
            raise NotFoundError(message=f"Product {product_id} not found")

        n_splits = split_config.n_splits if split_config else MAX_RECOMMENDED_SPLITS
        min_train = split_config.min_train_size if split_config else DEFAULT_MIN_TRAIN_SIZE

        agg = (
            await db.execute(
                select(
                    func.min(SalesDaily.date),
                    func.max(SalesDaily.date),
                    func.count(func.distinct(SalesDaily.date)),
                    func.avg(SalesDaily.quantity),
                    func.count().filter(SalesDaily.quantity == 0),
                ).where(
                    SalesDaily.store_id == store_id,
                    SalesDaily.product_id == product_id,
                )
            )
        ).one()
        first_date, last_date, observed_raw, avg_qty, zero_raw = agg
        observed_days = int(observed_raw or 0)
        zero_sale_days = int(zero_raw or 0)
        average_daily_demand = float(avg_qty) if avg_qty is not None else 0.0

        warnings: list[str] = []

        if first_date is None or last_date is None or observed_days == 0:
            expected_calendar_days = 0
            coverage_ratio = 0.0
            missing_days = 0
            promotion_days: int | None = 0
        else:
            expected_calendar_days = (last_date - first_date).days + 1
            coverage_ratio = (
                observed_days / expected_calendar_days if expected_calendar_days > 0 else 0.0
            )
            missing_days = max(0, expected_calendar_days - observed_days)
            promotion_days = await self._count_promotion_days(db, store_id, product_id, warnings)

        ready_threshold = min_train + forecast_horizon * n_splits
        limited_threshold = min_train + forecast_horizon
        status: AvailabilityStatus
        if observed_days >= ready_threshold and coverage_ratio >= MIN_COVERAGE_RATIO:
            status = "ready"
        elif observed_days >= limited_threshold:
            status = "limited"
        else:
            status = "unusable"

        if coverage_ratio and coverage_ratio < MIN_COVERAGE_RATIO and status != "unusable":
            warnings.append(
                f"Coverage {coverage_ratio:.0%} is below the {MIN_COVERAGE_RATIO:.0%} "
                "ready threshold."
            )

        feasible_splits = (observed_days - min_train) // max(forecast_horizon, 1)
        recommended_splits = min(20, max(2, min(MAX_RECOMMENDED_SPLITS, feasible_splits)))
        recommended_split_config = SplitConfig(
            strategy="expanding",
            n_splits=recommended_splits,
            min_train_size=min_train,
            gap=0,
            horizon=forecast_horizon,
        )

        return PairAvailabilityResponse(
            store_id=store_id,
            product_id=product_id,
            first_sales_date=first_date,
            last_sales_date=last_date,
            observed_days=observed_days,
            expected_calendar_days=expected_calendar_days,
            coverage_ratio=coverage_ratio,
            missing_days=missing_days,
            zero_sale_days=zero_sale_days,
            promotion_days=promotion_days,
            average_daily_demand=average_daily_demand,
            status=status,
            recommended_split_config=recommended_split_config,
            warnings=warnings,
        )

    async def _count_promotion_days(
        self,
        db: AsyncSession,
        store_id: int,
        product_id: int,
        warnings: list[str],
    ) -> int | None:
        """Count distinct sales dates inside any promotion for the pair.

        Includes chain-wide promos (``promotion.store_id IS NULL``). Returns
        ``None`` + a warning on any error (an acceptable fallback per the
        Success Criteria) — never sums ``(end-start)`` which would double-count
        overlapping ranges.
        """
        try:
            count = await db.scalar(
                select(func.count(func.distinct(SalesDaily.date)))
                .select_from(SalesDaily)
                .join(
                    Promotion,
                    and_(
                        Promotion.product_id == SalesDaily.product_id,
                        or_(
                            Promotion.store_id == SalesDaily.store_id,
                            Promotion.store_id.is_(None),
                        ),
                        SalesDaily.date >= Promotion.start_date,
                        SalesDaily.date <= Promotion.end_date,
                    ),
                )
                .where(
                    SalesDaily.store_id == store_id,
                    SalesDaily.product_id == product_id,
                )
            )
            return int(count or 0)
        except Exception as exc:  # promotion_days is best-effort; degrade gracefully
            warnings.append(f"promotion_days could not be derived: {exc}")
            return None

    # -------------------------------------------------------------------------
    # Orchestration
    # -------------------------------------------------------------------------

    async def run_selection(
        self, db: AsyncSession, request: ModelSelectionRunRequest
    ) -> ModelSelectionRunResponse:
        """Run the full champion-selection workflow and persist the audit row."""
        from pydantic import TypeAdapter  # lazy

        from app.features.backtesting.schemas import BacktestConfig  # lazy
        from app.features.backtesting.service import BacktestingService  # lazy
        from app.features.forecasting.schemas import ModelConfig  # lazy

        adapter: TypeAdapter[object] = TypeAdapter(ModelConfig)

        row = ModelSelectionRun(
            selection_id=uuid.uuid4().hex,
            status=ModelSelectionStatus.RUNNING.value,
            store_id=request.store_id,
            product_id=request.product_id,
            start_date=request.selection_window.start_date,
            end_date=request.selection_window.end_date,
            forecast_horizon=request.forecast_horizon,
            ranking_metric=request.ranking_metric,
            candidate_models=[c.model_dump() for c in request.candidate_models],
            policy_snapshot=request.ranking_policy.model_dump(mode="json"),
        )
        db.add(row)
        await db.flush()
        logger.info(
            "model_selection.run_received",
            selection_id=row.selection_id,
            store_id=request.store_id,
            product_id=request.product_id,
            n_candidates=len(request.candidate_models),
        )

        availability = await self.get_availability(
            db,
            request.store_id,
            request.product_id,
            request.forecast_horizon,
            request.split_config,
        )
        row.availability_snapshot = availability.model_dump(mode="json")
        logger.info(
            "model_selection.availability_checked",
            selection_id=row.selection_id,
            status=availability.status,
            observed_days=availability.observed_days,
        )

        if availability.status == "unusable":  # LOCKED #2 — fail fast (400)
            message = "Insufficient data for model selection (availability unusable)."
            row.status = ModelSelectionStatus.FAILED.value
            row.error_message = message
            await db.flush()
            logger.warning(
                "model_selection.run_failed",
                selection_id=row.selection_id,
                reason="unusable_availability",
            )
            raise BadRequestError(message=message)

        results: list[CandidateResult] = []
        backtesting_service = BacktestingService()
        for candidate in request.candidate_models:
            try:
                cfg = adapter.validate_python(
                    {"model_type": candidate.model_type, **candidate.params}
                )
                backtest = await backtesting_service.run_backtest(
                    db,
                    request.store_id,
                    request.product_id,
                    request.selection_window.start_date,
                    request.selection_window.end_date,
                    BacktestConfig(
                        split_config=request.split_config,
                        model_config_main=cfg,  # type: ignore[arg-type]
                        include_baselines=False,
                        store_fold_details=True,
                    ),
                )
                results.append(self._shape_candidate(candidate, backtest))
                logger.info(
                    "model_selection.candidate_completed",
                    selection_id=row.selection_id,
                    model_type=candidate.model_type,
                )
            except Exception as exc:  # never hide a failed candidate
                results.append(self._shape_failed_candidate(candidate, exc))
                logger.warning(
                    "model_selection.candidate_failed",
                    selection_id=row.selection_id,
                    model_type=candidate.model_type,
                    error=str(exc),
                )

        row.candidate_results = [r.model_dump(mode="json") for r in results]
        ranking = rank_candidates(
            results, request.ranking_policy, request.ranking_metric, availability.status
        )
        row.ranking_result = ranking.model_dump(mode="json")

        if ranking.winner is None:  # LOCKED #3 — persist failed, return 200
            row.status = ModelSelectionStatus.FAILED.value
            row.error_message = "No candidate produced a valid backtest."
            row.business_summary = explain_winner(ranking, availability)
            row.completed_at = datetime.now(UTC)
            await db.flush()
            await db.refresh(row)
            logger.warning(
                "model_selection.run_failed",
                selection_id=row.selection_id,
                reason="no_valid_winner",
            )
            return self._response(row, ranking)

        winner_cfg = adapter.validate_python(
            {"model_type": ranking.winner.model_type, **ranking.winner.params}
        )

        if request.auto_train_winner:
            from app.features.forecasting.service import ForecastingService  # lazy

            train = await ForecastingService().train_model(
                db,
                request.store_id,
                request.product_id,
                request.selection_window.start_date,
                request.selection_window.end_date,
                winner_cfg,  # type: ignore[arg-type]
                feature_frame_version=request.feature_frame_version,
                feature_groups=request.feature_groups,
            )
            row.final_model_path = train.model_path

        forecast_warning: str | None = None
        if request.auto_predict and row.final_model_path:
            from app.features.forecasting.service import ForecastingService  # lazy

            try:
                prediction = await ForecastingService().predict(
                    request.store_id,
                    request.product_id,
                    request.forecast_horizon,
                    row.final_model_path,
                )
                row.forecast_result = self._forecast_summary(
                    prediction, request.forecast_horizon
                ).model_dump(mode="json")
            except Exception as exc:  # e.g. feature-aware predict reject — warn, don't fail
                forecast_warning = f"Auto-predict skipped: {exc}"
                logger.warning(
                    "model_selection.predict_skipped",
                    selection_id=row.selection_id,
                    error=str(exc),
                )

        row.winner_model_type = ranking.winner.model_type
        row.winner_metrics = ranking.winner.metrics
        row.chart_data = build_chart_data(results, ranking).model_dump(mode="json")
        business = explain_winner(ranking, availability)
        if forecast_warning is not None:
            business["forecast_warning"] = forecast_warning
        row.business_summary = business
        row.status = (
            ModelSelectionStatus.PARTIAL.value
            if any(r.failed for r in results)
            else ModelSelectionStatus.COMPLETED.value
        )
        row.completed_at = datetime.now(UTC)
        await db.flush()
        await db.refresh(row)
        logger.info(
            "model_selection.run_completed",
            selection_id=row.selection_id,
            status=row.status,
            winner=row.winner_model_type,
        )
        return self._response(row, ranking)

    # -------------------------------------------------------------------------
    # Async orchestration (Slice B) — fire-and-forget LRO
    # -------------------------------------------------------------------------

    async def submit_run(
        self, db: AsyncSession, request: ModelSelectionRunRequest
    ) -> SubmitRunResponse:
        """Submit an async selection run: insert parent + children, detach worker.

        Returns 202-shaped ``SubmitRunResponse`` (status=running) IMMEDIATELY —
        the candidate backtests run in a detached :func:`asyncio.create_task`
        that uses its OWN sessions (never this request ``db``).
        """
        availability = await self.get_availability(
            db,
            request.store_id,
            request.product_id,
            request.forecast_horizon,
            request.split_config,
        )

        selection_id = uuid.uuid4().hex
        now = datetime.now(UTC)
        row = ModelSelectionRun(
            selection_id=selection_id,
            status=ModelSelectionStatus.RUNNING.value,
            store_id=request.store_id,
            product_id=request.product_id,
            start_date=request.selection_window.start_date,
            end_date=request.selection_window.end_date,
            forecast_horizon=request.forecast_horizon,
            ranking_metric=request.ranking_metric,
            candidate_models=[c.model_dump() for c in request.candidate_models],
            policy_snapshot=request.ranking_policy.model_dump(mode="json"),
            availability_snapshot=availability.model_dump(mode="json"),
            started_at=now,
            total_candidates=len(request.candidate_models),
        )
        db.add(row)
        # Flush the parent INSERT before the children — there is no ORM
        # ``relationship`` and the FK targets the non-PK ``selection_id``, so the
        # unit-of-work would not otherwise order parent-before-child.
        await db.flush()

        # Fail fast on unusable availability (LOCKED #2 parity with the sync path)
        # — persist a failed parent (no children, no worker) and raise 400.
        if availability.status == "unusable":
            message = "Insufficient data for model selection (availability unusable)."
            row.status = ModelSelectionStatus.FAILED.value
            row.error_message = message
            row.completed_at = now
            await db.commit()
            logger.warning(
                "model_selection.run_failed",
                selection_id=selection_id,
                reason="unusable_availability",
            )
            raise BadRequestError(message=message)

        candidates: list[ModelSelectionCandidate] = []
        for ordinal, candidate in enumerate(request.candidate_models):
            cand = ModelSelectionCandidate(
                candidate_id=uuid.uuid4().hex,
                selection_id=selection_id,
                ordinal=ordinal,
                model_type=candidate.model_type,
                params=candidate.params,
                status=CandidateStatus.PENDING.value,
            )
            db.add(cand)
            candidates.append(cand)
        await db.commit()
        await db.refresh(row)  # populate server-default created_at for the 202 body

        logger.info(
            "model_selection.run_submitted",
            selection_id=selection_id,
            store_id=request.store_id,
            product_id=request.product_id,
            n_candidates=len(candidates),
        )

        # Eagerly register the cancel handle so a DELETE arriving before the
        # detached worker starts still finds it (avoids a false "already settled"
        # 409). The worker's setdefault reuses this same handle.
        runner.register_selection(selection_id)

        # Detach the worker — hold a strong ref so it cannot be GC'd mid-run.
        task = asyncio.create_task(
            self._run_in_background(selection_id, request),
            name=f"model_selection_worker:{selection_id}",
        )
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)

        candidate_progress = [
            CandidateProgress(
                candidate_id=c.candidate_id,
                ordinal=c.ordinal,
                model_type=c.model_type,
                status="pending",
            )
            for c in candidates
        ]
        progress = SelectionProgress(
            total=len(candidates),
            pending=len(candidates),
            running=0,
            completed=0,
            failed=0,
            cancelled=0,
        )
        return SubmitRunResponse(
            selection_id=selection_id,
            store_id=request.store_id,
            product_id=request.product_id,
            status="running",
            selection_window=request.selection_window,
            forecast_horizon=request.forecast_horizon,
            ranking_metric=request.ranking_metric,
            availability=availability,
            ranking=[],
            winner=None,
            recommendation_confidence=None,
            confidence_reasons=[],
            chart_data=None,
            final_model=None,
            forecast=None,
            business_summary=None,
            error_message=None,
            created_at=row.created_at,
            started_at=now,
            completed_at=None,
            progress=progress,
            candidate_progress=candidate_progress,
            monitor_url=f"/model-selection/{selection_id}",
            cancel_url=f"/model-selection/{selection_id}",
        )

    async def _run_in_background(
        self, selection_id: str, request: ModelSelectionRunRequest
    ) -> None:
        """Detached worker — runs candidate backtests, then settles the parent.

        Uses ONLY sessions from ``get_session_maker()`` (the request session is
        long gone). Never raises out — settles the parent to its observed state.
        """
        session_maker = get_session_maker()
        settings = get_settings()

        async def _exec(candidate_id: str) -> None:
            from pydantic import TypeAdapter  # lazy

            from app.features.backtesting.schemas import BacktestConfig  # lazy
            from app.features.backtesting.service import BacktestingService  # lazy
            from app.features.forecasting.schemas import ModelConfig  # lazy

            async with session_maker() as session:
                cand = await session.scalar(
                    select(ModelSelectionCandidate).where(
                        ModelSelectionCandidate.candidate_id == candidate_id
                    )
                )
                if cand is None:  # deleted-parent race — survivable
                    return
                started = datetime.now(UTC)
                cand.status = CandidateStatus.RUNNING.value
                cand.started_at = started
                await session.commit()
                logger.info(
                    "model_selection.candidate_started",
                    selection_id=selection_id,
                    model_type=cand.model_type,
                )
                try:
                    adapter: TypeAdapter[object] = TypeAdapter(ModelConfig)
                    cfg = adapter.validate_python({"model_type": cand.model_type, **cand.params})
                    backtest = await BacktestingService().run_backtest(
                        session,
                        request.store_id,
                        request.product_id,
                        request.selection_window.start_date,
                        request.selection_window.end_date,
                        BacktestConfig(
                            split_config=request.split_config,
                            model_config_main=cfg,  # type: ignore[arg-type]
                            include_baselines=False,
                            store_fold_details=True,
                        ),
                    )
                    result = self._shape_candidate(
                        CandidateModelConfig.model_validate(
                            {"model_type": cand.model_type, "params": cand.params}
                        ),
                        backtest,
                    )
                    cand.result = result.model_dump(mode="json")
                    cand.status = CandidateStatus.COMPLETED.value
                    logger.info(
                        "model_selection.candidate_completed",
                        selection_id=selection_id,
                        model_type=cand.model_type,
                    )
                except Exception as exc:  # never hide a failed candidate
                    cand.status = CandidateStatus.FAILED.value
                    cand.error_message = str(exc)[:2000]
                    cand.error_type = type(exc).__name__
                    logger.warning(
                        "model_selection.candidate_failed",
                        selection_id=selection_id,
                        model_type=cand.model_type,
                        error=str(exc),
                    )
                finished = datetime.now(UTC)
                cand.completed_at = finished
                cand.duration_ms = int((finished - started).total_seconds() * 1000)
                await session.commit()

        try:
            candidate_ids = await self._candidate_ids(session_maker, selection_id)
            await runner.run_selection_candidates(
                selection_id=selection_id,
                candidate_ids=candidate_ids,
                max_parallel=settings.model_selection_global_max_parallel,
                global_max_parallel=settings.model_selection_global_max_parallel,
                session_maker=session_maker,
                execute_candidate=_exec,
            )
        finally:
            # Always settle + unblock any DELETE drain, even if loading the
            # candidate ids or the runner itself raised unexpectedly.
            await self._settle(selection_id, request, session_maker)
            runner.mark_completed(selection_id)

    async def _candidate_ids(
        self, session_maker: async_sessionmaker[AsyncSession], selection_id: str
    ) -> list[str]:
        """Load this run's candidate ids in submit (ordinal) order."""
        async with session_maker() as session:
            rows = (
                await session.execute(
                    select(ModelSelectionCandidate.candidate_id)
                    .where(ModelSelectionCandidate.selection_id == selection_id)
                    .order_by(ModelSelectionCandidate.ordinal)
                )
            ).all()
        return [r[0] for r in rows]

    async def _settle(
        self,
        selection_id: str,
        request: ModelSelectionRunRequest,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        """Aggregate terminal children → ranking/chart/business + final status.

        REUSES the pure ``rank_candidates`` / ``build_chart_data`` /
        ``explain_winner`` so the terminal GET output is byte-compatible with
        the synchronous ``/run`` path (LOCKED #7).
        """
        async with session_maker() as session:
            row = await session.scalar(
                select(ModelSelectionRun).where(ModelSelectionRun.selection_id == selection_id)
            )
            if row is None:  # deleted-parent race
                return
            children = (
                (
                    await session.execute(
                        select(ModelSelectionCandidate)
                        .where(ModelSelectionCandidate.selection_id == selection_id)
                        .order_by(ModelSelectionCandidate.ordinal)
                    )
                )
                .scalars()
                .all()
            )

            results: list[CandidateResult] = []
            for child in children:
                if child.status == CandidateStatus.COMPLETED.value and child.result:
                    results.append(CandidateResult.model_validate(child.result))
                elif child.status == CandidateStatus.CANCELLED.value:
                    results.append(
                        CandidateResult(
                            model_type=child.model_type,
                            params=child.params,
                            failed=True,
                            error="cancelled",
                            aggregated_metrics=None,
                            sample_size=0,
                            folds=[],
                        )
                    )
                else:  # failed (or any non-completed leftover)
                    results.append(
                        CandidateResult(
                            model_type=child.model_type,
                            params=child.params,
                            failed=True,
                            error=child.error_message or "candidate failed",
                            aggregated_metrics=None,
                            sample_size=0,
                            folds=[],
                        )
                    )

            availability = (
                PairAvailabilityResponse.model_validate(row.availability_snapshot)
                if row.availability_snapshot
                else None
            )
            availability_status: AvailabilityStatus = (
                availability.status if availability is not None else "ready"
            )
            ranking = rank_candidates(
                results, request.ranking_policy, row.ranking_metric, availability_status
            )
            row.candidate_results = [r.model_dump(mode="json") for r in results]
            row.ranking_result = ranking.model_dump(mode="json")
            if ranking.winner is not None:
                row.winner_model_type = ranking.winner.model_type
                row.winner_metrics = ranking.winner.metrics
                row.chart_data = build_chart_data(results, ranking).model_dump(mode="json")
            if availability is not None:
                row.business_summary = explain_winner(ranking, availability)

            counts = self._status_counts(children)
            row.completed_candidates = counts["completed"]
            row.failed_candidates = counts["failed"]
            row.cancelled_candidates = counts["cancelled"]
            row.status = self._terminal_status(counts).value
            row.completed_at = datetime.now(UTC)
            await session.commit()
            logger.info(
                "model_selection.run_settled",
                selection_id=selection_id,
                status=row.status,
                winner=row.winner_model_type,
            )

    async def cancel_run(self, db: AsyncSession, selection_id: str) -> ModelSelectionRunResponse:
        """Cooperatively cancel + drain an in-flight selection run."""
        row = await self._load(db, selection_id)
        if row.status in TERMINAL_SELECTION_STATES:
            raise ConflictError(
                message=f"Selection run already terminal: {row.status}",
                details={"selection_id": selection_id, "status": row.status},
            )
        logger.info("model_selection.run_cancel_requested", selection_id=selection_id)
        fired = runner.cancel_selection(selection_id)
        if not fired:
            # Race: the worker settled between our load and the cancel.
            raise ConflictError(
                message="Selection run settled before cancel could fire",
                details={"selection_id": selection_id},
            )
        settings = get_settings()
        drained = await runner.await_drain(
            selection_id,
            timeout_seconds=float(settings.model_selection_cancel_drain_timeout_seconds),
        )
        if not drained:
            raise GatewayTimeoutError(
                message=(
                    f"Drain exceeded {settings.model_selection_cancel_drain_timeout_seconds}s; "
                    "in-flight sklearn / LightGBM fits are uncancellable mid-call — "
                    "retry once the fit completes."
                ),
                details={"selection_id": selection_id},
            )
        # Re-load through a fresh read so the settled state is visible.
        await db.commit()
        refreshed = await self._load(db, selection_id)
        logger.info(
            "model_selection.run_cancel_drained",
            selection_id=selection_id,
            status=refreshed.status,
        )
        response = self._response(refreshed, self._load_ranking(refreshed))
        await self._attach_progress(db, selection_id, response)
        return response

    @staticmethod
    def _status_counts(children: Sequence[ModelSelectionCandidate]) -> dict[str, int]:
        """Tally child statuses into the five count buckets."""
        counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0, "cancelled": 0}
        for child in children:
            counts[child.status] = counts.get(child.status, 0) + 1
        return counts

    @staticmethod
    def _terminal_status(counts: dict[str, int]) -> ModelSelectionStatus:
        """Terminal-status rule at settle (mirror ``batch.service._settle``)."""
        completed = counts.get("completed", 0)
        failed = counts.get("failed", 0)
        cancelled = counts.get("cancelled", 0)
        if cancelled > 0 and completed == 0 and failed == 0:
            return ModelSelectionStatus.CANCELLED
        if completed > 0 and failed == 0 and cancelled == 0:
            return ModelSelectionStatus.COMPLETED
        if failed > 0 and completed == 0 and cancelled == 0:
            return ModelSelectionStatus.FAILED
        if completed > 0 or failed > 0:
            return ModelSelectionStatus.PARTIAL
        return ModelSelectionStatus.FAILED

    async def _attach_progress(
        self, db: AsyncSession, selection_id: str, response: ModelSelectionRunResponse
    ) -> None:
        """Attach live ``progress`` + ``candidate_progress`` to a response.

        A legacy synchronous ``/run`` row has no children → ``progress`` stays
        ``None`` and ``candidate_progress`` stays ``[]``.
        """
        children = (
            (
                await db.execute(
                    select(ModelSelectionCandidate)
                    .where(ModelSelectionCandidate.selection_id == selection_id)
                    .order_by(ModelSelectionCandidate.ordinal)
                )
            )
            .scalars()
            .all()
        )
        if not children:
            return
        counts = self._status_counts(children)
        response.progress = SelectionProgress(
            total=len(children),
            pending=counts["pending"],
            running=counts["running"],
            completed=counts["completed"],
            failed=counts["failed"],
            cancelled=counts["cancelled"],
        )
        response.candidate_progress = [
            CandidateProgress(
                candidate_id=child.candidate_id,
                ordinal=child.ordinal,
                model_type=child.model_type,
                status=child.status,  # type: ignore[arg-type]
                error=child.error_message,
                started_at=child.started_at,
                completed_at=child.completed_at,
                duration_ms=child.duration_ms,
            )
            for child in children
        ]

    # -------------------------------------------------------------------------
    # Read / re-run helpers
    # -------------------------------------------------------------------------

    async def get_selection(self, db: AsyncSession, selection_id: str) -> ModelSelectionRunResponse:
        """Return a persisted selection run by id (404 when missing).

        Attaches live async progress (Slice B) when the run has child rows; a
        legacy synchronous ``/run`` row has none and reads as before.
        """
        row = await self._load(db, selection_id)
        response = self._response(row, self._load_ranking(row))
        await self._attach_progress(db, selection_id, response)
        return response

    async def get_ranking(self, db: AsyncSession, selection_id: str) -> RankingResult:
        """Return just the ranking block for a selection run."""
        row = await self._load(db, selection_id)
        return self._load_ranking(row)

    async def train_winner(self, db: AsyncSession, selection_id: str) -> TrainWinnerResponse:
        """Train the winning model for a completed selection (V1 contract)."""
        from pydantic import TypeAdapter  # lazy

        from app.features.forecasting.schemas import ModelConfig  # lazy
        from app.features.forecasting.service import ForecastingService  # lazy

        row = await self._load(db, selection_id)
        ranking = self._load_ranking(row)
        if ranking.winner is None:
            raise BadRequestError(message="Selection has no winning model to train.")

        adapter: TypeAdapter[object] = TypeAdapter(ModelConfig)
        cfg = adapter.validate_python(
            {"model_type": ranking.winner.model_type, **ranking.winner.params}
        )
        train = await ForecastingService().train_model(
            db,
            row.store_id,
            row.product_id,
            row.start_date,
            row.end_date,
            cfg,  # type: ignore[arg-type]
        )
        row.final_model_path = train.model_path
        await db.flush()
        logger.info(
            "model_selection.winner_trained",
            selection_id=row.selection_id,
            model_type=ranking.winner.model_type,
        )
        return TrainWinnerResponse(
            selection_id=row.selection_id,
            model_type=ranking.winner.model_type,
            model_path=train.model_path,
        )

    async def predict_winner(self, db: AsyncSession, selection_id: str) -> ForecastSummary:
        """Forecast with the trained winning model (requires train-winner first)."""
        from app.features.forecasting.service import ForecastingService  # lazy

        row = await self._load(db, selection_id)
        if not row.final_model_path:
            raise BadRequestError(
                message="No trained model for this selection; call train-winner first."
            )
        prediction = await ForecastingService().predict(
            row.store_id, row.product_id, row.forecast_horizon, row.final_model_path
        )
        summary = self._forecast_summary(prediction, row.forecast_horizon)
        row.forecast_result = summary.model_dump(mode="json")
        await db.flush()
        logger.info(
            "model_selection.winner_predicted",
            selection_id=row.selection_id,
            horizon=row.forecast_horizon,
        )
        return summary

    # -------------------------------------------------------------------------
    # Pure mappers
    # -------------------------------------------------------------------------

    def _shape_candidate(
        self, candidate: CandidateModelConfig, backtest: BacktestResponse
    ) -> CandidateResult:
        main = backtest.main_model_results
        sample_size = sum(len(fold.actuals) for fold in main.fold_results)
        folds = [
            FoldChart(
                fold_index=fold.fold_index,
                dates=fold.dates,
                actuals=fold.actuals,
                predictions=fold.predictions,
            )
            for fold in main.fold_results
        ]
        return CandidateResult(
            model_type=candidate.model_type,
            params=candidate.params,
            failed=False,
            aggregated_metrics=main.aggregated_metrics,
            sample_size=sample_size,
            config_hash=backtest.config_hash,
            folds=folds,
        )

    def _shape_failed_candidate(
        self, candidate: CandidateModelConfig, exc: Exception
    ) -> CandidateResult:
        return CandidateResult(
            model_type=candidate.model_type,
            params=candidate.params,
            failed=True,
            error=str(exc),
            aggregated_metrics=None,
            sample_size=0,
            folds=[],
        )

    def _forecast_summary(self, prediction: PredictResponse, horizon: int) -> ForecastSummary:
        points = [point.model_dump(mode="json") for point in prediction.forecasts]
        total = float(sum(point.forecast for point in prediction.forecasts))
        average = total / len(prediction.forecasts) if prediction.forecasts else 0.0
        return ForecastSummary(
            points=points, total_demand=total, average_demand=average, horizon=horizon
        )

    async def _load(self, db: AsyncSession, selection_id: str) -> ModelSelectionRun:
        row = await db.scalar(
            select(ModelSelectionRun).where(ModelSelectionRun.selection_id == selection_id)
        )
        if row is None:
            raise NotFoundError(message=f"Selection run {selection_id} not found")
        return row

    def _load_ranking(self, row: ModelSelectionRun) -> RankingResult:
        if row.ranking_result:
            return RankingResult.model_validate(row.ranking_result)
        return RankingResult(winner=None, entries=[], confidence="low", reasons=[])

    def _response(
        self, row: ModelSelectionRun, ranking: RankingResult
    ) -> ModelSelectionRunResponse:
        availability = (
            PairAvailabilityResponse.model_validate(row.availability_snapshot)
            if row.availability_snapshot
            else None
        )
        chart_data = ChartData.model_validate(row.chart_data) if row.chart_data else None
        forecast = (
            ForecastSummary.model_validate(row.forecast_result) if row.forecast_result else None
        )
        winner: WinnerSummary | None = None
        if ranking.winner is not None and row.status in _TERMINAL_WITH_WINNER:
            winner = WinnerSummary(
                model_type=ranking.winner.model_type,
                params=ranking.winner.params,
                metrics=ranking.winner.metrics or {},
                rank=1,
            )
        confidence = ranking.confidence if (ranking.entries or ranking.winner) else None
        final_model = {"model_path": row.final_model_path} if row.final_model_path else None
        return ModelSelectionRunResponse(
            selection_id=row.selection_id,
            store_id=row.store_id,
            product_id=row.product_id,
            status=row.status,  # type: ignore[arg-type]
            selection_window=SelectionWindow(start_date=row.start_date, end_date=row.end_date),
            forecast_horizon=row.forecast_horizon,
            ranking_metric=row.ranking_metric,
            availability=availability,
            ranking=ranking.entries,
            winner=winner,
            recommendation_confidence=confidence,
            confidence_reasons=ranking.reasons,
            chart_data=chart_data,
            final_model=final_model,
            forecast=forecast,
            business_summary=row.business_summary,
            error_message=row.error_message,
            created_at=row.created_at,
            started_at=row.started_at,
            completed_at=row.completed_at,
        )
