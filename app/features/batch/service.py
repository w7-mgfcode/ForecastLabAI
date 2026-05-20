"""BatchService — orchestration layer for portfolio forecasting batches (PRP-33).

Submits one ``batch_job`` and N ``batch_job_item`` rows in one transaction,
then loops a partial-index-backed picker (``FOR UPDATE SKIP LOCKED``) and
delegates each item to ``JobService.create_job`` via a lazy in-method
import. The metrics JSONB is pinned to the exact five-key shape
``{wape, smape, mae, bias, sample_size}`` — every downstream PRP
(parallel-execution, priority-queue, export-and-retry,
champion-and-heatmap) consumes this shape directly. ``sample_size`` is
derived **inside this slice** from ``fold_metrics`` so the jobs slice
stays untouched (the non-regression boundary declared in PRP-33).

structlog lifecycle events (every event carries a ``request_id`` via the
middleware-bound logger): ``batch.created``, ``batch.item_started``,
``batch.item_completed``, ``batch.item_failed``, ``batch.completed``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.features.batch.models import (
    BatchItemStatus,
    BatchJob,
    BatchJobItem,
    BatchOperation,
    BatchStatus,
)
from app.features.batch.schemas import (
    BatchItemListResponse,
    BatchItemResponse,
    BatchModelConfig,
    BatchScope,
    BatchSubmitRequest,
    BatchSubmitResponse,
)

# data_platform is the de-facto shared ORM layer (see the
# data-platform-shared-orm-layer memory) — module-scope import for scope
# expansion is permitted; cross-slice *service* calls stay lazy.
from app.features.data_platform.models import Product, SalesDaily, Store

if TYPE_CHECKING:
    from app.features.jobs.schemas import JobResponse

logger = get_logger(__name__)

# Pinned metrics keys — the test_metrics_jsonb_shape_pinned regression locks
# this exact list. Downstream PRPs read from these keys; adding a sixth key
# (or renaming one) is a breaking change requiring a new INITIAL.
_METRICS_KEYS: tuple[str, ...] = ("wape", "smape", "mae", "bias", "sample_size")

# Allow-listed sort columns for GET /batch/{id}/items. ``sort_by`` is user
# input — it MUST resolve through this map to a real mapped column; unknown
# keys fall back to the default order (never an error, never raw SQL).
_BATCH_ITEM_SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "created_at": BatchJobItem.created_at,
    "completed_at": BatchJobItem.completed_at,
    "status": BatchJobItem.status,
    "priority": BatchJobItem.priority,
}


class BatchService:
    """Service for submitting, executing, and observing portfolio batches.

    MVP runs items sequentially in-process via a single picker loop. The
    picker compiles to ``FOR UPDATE SKIP LOCKED`` — a no-op with one worker
    but load-bearing for downstream-1 (parallel) and downstream-2 (priority),
    so the picker query needs no code retrofit when those land.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    # ------------------------------------------------------------------ submit
    async def submit(self, db: AsyncSession, req: BatchSubmitRequest) -> BatchSubmitResponse:
        """Submit a batch: expand scope, insert N+1 rows, run picker, settle.

        Raises:
            ValidationError: scope expanded beyond ``batch_max_scope_expansion``.
        """
        pairs = await self._expand_scope(db, req.scope)
        triples = [(s, p, mc) for (s, p) in pairs for mc in req.model_configs]

        if len(triples) > self.settings.batch_max_scope_expansion:
            raise ValidationError(
                message=(
                    f"Scope expanded to {len(triples)} items, exceeds the cap of "
                    f"{self.settings.batch_max_scope_expansion}. Narrow the scope "
                    f"or raise BATCH_MAX_SCOPE_EXPANSION."
                ),
                details={
                    "expanded_items": len(triples),
                    "cap": self.settings.batch_max_scope_expansion,
                },
            )

        # 1. Insert parent + N children in one transaction.
        batch = BatchJob(
            batch_id=uuid.uuid4().hex,
            operation=req.operation,
            scope=req.scope.model_dump(mode="json"),
            model_configs=[mc.model_dump(mode="json") for mc in req.model_configs],
            status=BatchStatus.PENDING.value,
            total_items=len(triples),
            params=req.model_dump(mode="json"),
            default_child_priority=req.default_child_priority,
            max_parallel=req.max_parallel,
        )
        db.add(batch)
        for store_id, product_id, mc in triples:
            item = BatchJobItem(
                item_id=uuid.uuid4().hex,
                batch_id=batch.batch_id,
                store_id=store_id,
                product_id=product_id,
                model_type=mc.model_type,
                priority=req.default_child_priority,
                status=BatchItemStatus.PENDING.value,
                params=self._frozen_item_params(req, store_id, product_id, mc),
            )
            db.add(item)
        await db.commit()
        await db.refresh(batch)

        logger.info(
            "batch.created",
            batch_id=batch.batch_id,
            operation=req.operation,
            total_items=len(triples),
        )

        # 2. Settle parent to running.
        batch.status = BatchStatus.RUNNING.value
        batch.started_at = datetime.now(UTC)
        await db.commit()

        # 3. Loop the picker until no PENDING item remains. The explicit
        # ``BatchJobItem | None`` annotation prevents mypy from re-narrowing
        # ``item`` to ``BatchJobItem`` on the second iteration after the
        # first ``if item is None: break`` branch.
        while True:
            next_item: BatchJobItem | None = await self._pick_next(db, batch.batch_id)
            if next_item is None:
                break
            await self._execute_item(db, next_item)

        # 4. Settle the parent.
        await self._settle(db, batch)
        await db.refresh(batch)

        logger.info(
            "batch.completed",
            batch_id=batch.batch_id,
            status=batch.status,
            completed_items=batch.completed_items,
            failed_items=batch.failed_items,
        )

        return BatchSubmitResponse.model_validate(batch)

    # --------------------------------------------------------------------- get
    async def get(self, db: AsyncSession, batch_id: str) -> BatchSubmitResponse | None:
        """Get parent batch by ``batch_id``."""
        stmt = select(BatchJob).where(BatchJob.batch_id == batch_id)
        batch = (await db.execute(stmt)).scalar_one_or_none()
        if batch is None:
            return None
        return BatchSubmitResponse.model_validate(batch)

    # ------------------------------------------------------------------- items
    async def list_items(
        self,
        db: AsyncSession,
        batch_id: str,
        page: int = 1,
        page_size: int = 50,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> BatchItemListResponse | None:
        """List items for ``batch_id`` with pagination + allow-listed sort.

        Returns ``None`` when the batch does not exist (route maps to 404).
        """
        parent = (
            await db.execute(select(BatchJob).where(BatchJob.batch_id == batch_id))
        ).scalar_one_or_none()
        if parent is None:
            return None

        base = select(BatchJobItem).where(BatchJobItem.batch_id == batch_id)
        total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

        sort_column = _BATCH_ITEM_SORT_COLUMNS.get(sort_by) if sort_by else None
        if sort_column is not None:
            order_by = sort_column.desc() if sort_order == "desc" else sort_column.asc()
        else:
            order_by = BatchJobItem.created_at.desc()

        offset = (page - 1) * page_size
        stmt = (
            base.order_by(order_by, BatchJobItem.created_at.asc(), BatchJobItem.id.asc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return BatchItemListResponse(
            items=[BatchItemResponse.model_validate(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    # --------------------------------------------------------------- internals
    async def _pick_next(self, db: AsyncSession, batch_id: str) -> BatchJobItem | None:
        """Pick the next PENDING item — partial-index-backed, SKIP LOCKED wired.

        With one worker, ``skip_locked=True`` is a no-op; with N workers it
        prevents the picker from blocking on a row another worker holds.
        The integration test asserts the SKIP LOCKED clause is in the
        compiled SQL — never remove the kwarg.
        """
        stmt = (
            select(BatchJobItem)
            .where(
                BatchJobItem.batch_id == batch_id,
                BatchJobItem.status == BatchItemStatus.PENDING.value,
            )
            .order_by(
                BatchJobItem.priority.desc(),
                BatchJobItem.created_at.asc(),
                BatchJobItem.id.asc(),
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    async def _execute_item(self, db: AsyncSession, item: BatchJobItem) -> None:
        """Run one item: delegate to ``JobService.create_job`` and capture metrics.

        Lazy cross-slice imports break the alembic cold-boot cycle
        (precedent: ``app/features/forecasting/service.py:786-787``).
        """
        from app.features.jobs.models import JobStatus
        from app.features.jobs.schemas import JobCreate
        from app.features.jobs.service import JobService

        item.status = BatchItemStatus.RUNNING.value
        item.started_at = datetime.now(UTC)
        await db.commit()

        logger.info(
            "batch.item_started",
            batch_id=item.batch_id,
            item_id=item.item_id,
            store_id=item.store_id,
            product_id=item.product_id,
            model_type=item.model_type,
        )

        try:
            operation = item.params["operation"]
            job_params = item.params["job_params"]
            if operation not in ("train", "predict", "backtest"):
                # train_backtest_register is reserved for a downstream PRP that
                # chains three calls; the MVP rejects it at submit time but the
                # path is wired so the future change does not need a refactor.
                raise NotImplementedError(
                    f"operation={operation!r} not supported in MVP "
                    "(use train, predict, or backtest)"
                )

            job_create = JobCreate.model_validate({"job_type": operation, "params": job_params})
            job = await JobService().create_job(db=db, job_create=job_create)
            item.child_job_id = job.job_id
            item.child_run_id = job.run_id

            if job.status == JobStatus.FAILED:
                raise RuntimeError(job.error_message or "child job failed")

            item.metrics = self._shape_metrics(job)
            item.status = BatchItemStatus.COMPLETED.value
        except Exception as exc:
            item.status = BatchItemStatus.FAILED.value
            item.error_message = str(exc)[:2000]
            item.error_type = type(exc).__name__

        completed_at = datetime.now(UTC)
        item.completed_at = completed_at
        started_at = item.started_at
        if started_at is not None:
            item.duration_ms = int((completed_at - started_at).total_seconds() * 1000)
        await db.commit()

        if item.status == BatchItemStatus.COMPLETED.value:
            logger.info(
                "batch.item_completed",
                batch_id=item.batch_id,
                item_id=item.item_id,
                duration_ms=item.duration_ms,
            )
        else:
            logger.warning(
                "batch.item_failed",
                batch_id=item.batch_id,
                item_id=item.item_id,
                error_type=item.error_type,
                error_message=item.error_message,
            )

    def _shape_metrics(self, job: JobResponse) -> dict[str, Any] | None:
        """Coerce ``JobResponse.result`` into the pinned five-key JSONB.

        CRITICAL: returns EXACTLY ``{wape, smape, mae, bias, sample_size}``
        or ``None`` (the four downstream PRPs read these keys verbatim).
        ``sample_size`` is computed inside this slice from ``fold_metrics``;
        Option (b) — extending ``app/features/jobs/service.py:_shape_backtest_result``
        to emit a new aggregate — is REJECTED because it would touch the
        jobs slice and violate the no-cross-import rule (PRP-33 § "Why not 10").
        """
        # Lazy import — the JobType enum lives in the jobs slice; we only need
        # the value for comparison, so a string compare is sufficient.
        if job.job_type.value != "backtest" or not job.result:
            # Predict-only items have no per-fold metrics in the job result.
            return None
        agg = job.result.get("aggregated_metrics", {})
        fold_metrics = job.result.get("fold_metrics", [])
        sample_size = sum(f.get("sample_size", 0) for f in fold_metrics)
        if sample_size == 0:
            sample_size = job.result.get("n_observations") or 0
        return {
            "wape": agg.get("wape_mean"),
            "smape": agg.get("smape_mean"),
            "mae": agg.get("mae_mean"),
            "bias": agg.get("bias_mean"),
            "sample_size": sample_size,
        }

    async def _settle(self, db: AsyncSession, batch: BatchJob) -> None:
        """Aggregate per-status counts and settle the parent.

        - all COMPLETED → ``completed``
        - all FAILED → ``failed``
        - mixed (>=1 of each) → ``partial``
        - 0 items (degenerate empty batch) → ``completed`` (vacuous)
        """
        stmt = (
            select(BatchJobItem.status, func.count())
            .where(BatchJobItem.batch_id == batch.batch_id)
            .group_by(BatchJobItem.status)
        )
        rows = (await db.execute(stmt)).all()
        counts: dict[str, int] = {status: int(count) for status, count in rows}

        completed = counts.get(BatchItemStatus.COMPLETED.value, 0)
        failed = counts.get(BatchItemStatus.FAILED.value, 0)
        cancelled = counts.get(BatchItemStatus.CANCELLED.value, 0)

        if completed > 0 and failed == 0:
            final = BatchStatus.COMPLETED
        elif failed > 0 and completed == 0:
            final = BatchStatus.FAILED
        elif completed > 0 and failed > 0:
            final = BatchStatus.PARTIAL
        else:
            # No completed + no failed: empty batch or all-cancelled. Treat
            # as ``completed`` (vacuous) — the integration test asserts on
            # completed_items=N, not on status when items=0.
            final = BatchStatus.COMPLETED

        batch.status = final.value
        batch.completed_items = completed
        batch.failed_items = failed
        batch.cancelled_items = cancelled
        batch.completed_at = datetime.now(UTC)
        batch.result_summary = {
            "by_status": counts,
            "final_status": final.value,
        }
        await db.commit()

    # --------------------------------------------------------- scope expansion
    async def _expand_scope(self, db: AsyncSession, scope: BatchScope) -> list[tuple[int, int]]:
        """Expand a ``BatchScope`` into a deterministic list of (store, product) pairs.

        For ``region``/``category`` we query ``Store`` / ``Product`` directly
        — those models live in the shared ORM layer (``data_platform``) per
        the data-platform-shared-orm-layer memory; that does NOT count as a
        cross-slice import. For ``top_revenue`` we run a direct revenue
        aggregation against ``sales_daily`` (the ranking semantics are
        narrow enough that calling into ``AnalyticsService`` would be
        indirection for indirection's sake).
        """
        if scope.kind == "manual":
            # The model_validator already guarantees both lists are non-empty.
            return [(s, p) for s in (scope.store_ids or []) for p in (scope.product_ids or [])]
        if scope.kind == "region":
            store_ids = await self._stores_in_region(db, scope.region or "")
            product_ids = await self._all_product_ids(db)
            return [(s, p) for s in store_ids for p in product_ids]
        if scope.kind == "category":
            store_ids = await self._all_store_ids(db)
            product_ids = await self._products_in_category(db, scope.category or "")
            return [(s, p) for s in store_ids for p in product_ids]
        if scope.kind == "top_revenue":
            return await self._top_revenue_pairs(db, scope.top_n or 0)
        # kind == "all"
        store_ids = await self._all_store_ids(db)
        product_ids = await self._all_product_ids(db)
        return [(s, p) for s in store_ids for p in product_ids]

    async def _all_store_ids(self, db: AsyncSession) -> list[int]:
        stmt = select(Store.id).order_by(Store.id.asc())
        return [int(r) for r in (await db.execute(stmt)).scalars().all()]

    async def _all_product_ids(self, db: AsyncSession) -> list[int]:
        stmt = select(Product.id).order_by(Product.id.asc())
        return [int(r) for r in (await db.execute(stmt)).scalars().all()]

    async def _stores_in_region(self, db: AsyncSession, region: str) -> list[int]:
        stmt = select(Store.id).where(Store.region == region).order_by(Store.id.asc())
        return [int(r) for r in (await db.execute(stmt)).scalars().all()]

    async def _products_in_category(self, db: AsyncSession, category: str) -> list[int]:
        stmt = select(Product.id).where(Product.category == category).order_by(Product.id.asc())
        return [int(r) for r in (await db.execute(stmt)).scalars().all()]

    async def _top_revenue_pairs(self, db: AsyncSession, top_n: int) -> list[tuple[int, int]]:
        """Top-N (store, product) pairs by sum(total_amount) over all time.

        For the MVP we rank across the full ``sales_daily`` history — the
        submit window is used for child-job training, not for ranking. A
        future PRP may add a date-window arg.
        """
        if top_n <= 0:
            return []
        stmt = (
            select(
                SalesDaily.store_id,
                SalesDaily.product_id,
                func.sum(SalesDaily.total_amount).label("revenue"),
            )
            .group_by(SalesDaily.store_id, SalesDaily.product_id)
            .order_by(
                func.sum(SalesDaily.total_amount).desc(),
                SalesDaily.store_id.asc(),
                SalesDaily.product_id.asc(),
            )
            .limit(top_n)
        )
        rows = (await db.execute(stmt)).all()
        return [(int(s), int(p)) for s, p, _ in rows]

    # ------------------------------------------------------- per-item payload
    def _frozen_item_params(
        self,
        req: BatchSubmitRequest,
        store_id: int,
        product_id: int,
        mc: BatchModelConfig,
    ) -> dict[str, Any]:
        """Build per-item JSONB args, frozen at expansion time.

        The runner reads from this dict on every ``_execute_item`` call but
        never mutates it. The shape maps directly to ``JobCreate.params``
        for the relevant ``job_type``.
        """
        return {
            "operation": req.operation,
            "job_params": {
                "model_type": mc.model_type,
                "store_id": store_id,
                "product_id": product_id,
                "start_date": req.start_date.isoformat(),
                "end_date": req.end_date.isoformat(),
                **mc.params,
            },
        }


__all__ = [
    "BatchItemStatus",
    "BatchOperation",
    "BatchService",
    "BatchStatus",
]
