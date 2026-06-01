"""Service layer for the ForecastOps Control Center.

Read-only aggregation across sibling slices. This module imports the ORM
**models** of the ``jobs``, ``registry``, and ``data_platform`` slices and runs
read-only ``select()`` queries against them. It deliberately does NOT import any
sibling ``service.py`` or ``schemas.py`` — the cross-slice coupling is confined
to the verified, read-only ORM surface (see PRP-24, decision #1).
"""

from datetime import UTC, datetime
from itertools import groupby
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.features.data_platform.models import SalesDaily
from app.features.jobs.models import Job, JobStatus
from app.features.ops.schemas import (
    AliasHealth,
    AttentionItem,
    DataFreshness,
    DriftDirection,
    JobHealth,
    ModelHealthEntry,
    ModelHealthResponse,
    OpsSummaryResponse,
    RetrainingCandidate,
    RetrainingCandidatesResponse,
    RunHealth,
    StaleReason,
    StatusCount,
    SystemHealth,
    WapePoint,
)
from app.features.registry.models import DeploymentAlias, ModelRun, RunStatus

logger = get_logger(__name__)

# Staleness (days) at which the time-based component of the score saturates.
_STALENESS_CAP_DAYS = 90
# WAPE value at which the error-based component of the score saturates.
_WAPE_CAP = 100.0
# How many recent failed jobs / runs to surface in the attention list.
_ATTENTION_LIMIT = 10
# Relative WAPE-change band: forecast-error drift is only flagged outside ±10%.
_DRIFT_BAND = 0.10


# =============================================================================
# Pure helpers (no DB, no I/O — unit-tested directly)
# =============================================================================


def extract_wape(metrics: dict[str, Any] | None) -> float | None:
    """Pull a WAPE value out of a model run's ``metrics`` JSONB blob.

    Tolerant by design: ``model_run.metrics`` is frequently None or carries an
    unrelated metric set (backtest WAPE persists to ``job.result``, not run
    metrics), so this returns None rather than raising whenever a numeric WAPE
    cannot be found. Booleans are rejected — ``bool`` is an ``int`` subclass but
    is never a valid metric value.

    Args:
        metrics: The ``ModelRun.metrics`` JSONB dict, or None.

    Returns:
        The WAPE as a float, or None when absent / non-numeric.
    """
    if not metrics:
        return None
    for key in ("wape", "wape_mean", "WAPE"):
        value = metrics.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
    return None


def score_retraining_candidate(staleness_days: int, wape: float | None) -> float:
    """Compute a deterministic retraining-priority score in ``[0.0, 1.0]``.

    Blends a time-based signal (staleness, capped at 90 days, 60% weight) with a
    performance-based signal (WAPE, capped at 100, 40% weight) — the hybrid
    trigger recommended by MLOps retraining guidance. When WAPE is unknown the
    score degrades gracefully to staleness-only. Never raises.

    Args:
        staleness_days: Days since the run's training-data window ended.
        wape: The run's WAPE, or None when unknown.

    Returns:
        Priority score rounded to 4 decimals; higher means more urgent.
    """
    staleness_norm = min(max(staleness_days, 0), _STALENESS_CAP_DAYS) / _STALENESS_CAP_DAYS
    error_norm = min(max(wape, 0.0), _WAPE_CAP) / _WAPE_CAP if wape is not None else 0.0
    return round(0.6 * staleness_norm + 0.4 * error_norm, 4)


def classify_drift(
    wape_history: list[float | None],
) -> tuple[DriftDirection, float | None]:
    """Classify a grain's forecast-error (WAPE) trend.

    Pure and total: never raises, tolerates None gaps and sparse history.
    Compares the latest numeric WAPE against the mean of all prior numeric
    WAPEs, applying a ±10% relative band — the heuristic drift tolerance from
    MLOps monitoring guidance (a universal threshold does not exist).

    Args:
        wape_history: Chronological WAPE values; None marks a run with no WAPE.

    Returns:
        A ``(direction, delta)`` tuple. ``direction`` is improving / stable /
        degrading / unknown; ``delta`` is the latest numeric WAPE minus the
        previous numeric WAPE, or None when fewer than two numeric values exist.
    """
    numeric = [wape for wape in wape_history if wape is not None]
    if len(numeric) < 2:
        return "unknown", None
    latest = numeric[-1]
    prior = numeric[:-1]
    baseline = sum(prior) / len(prior)
    delta = round(latest - prior[-1], 4)
    if baseline <= 0:
        # Avoid div-by-zero on a zero baseline: any positive error is degrading.
        return ("degrading" if latest > 0 else "stable"), delta
    relative = (latest - baseline) / baseline
    if relative > _DRIFT_BAND:
        return "degrading", delta
    if relative < -_DRIFT_BAND:
        return "improving", delta
    return "stable", delta


def _run_feature_frame_version(run: ModelRun) -> int:
    """Read ``feature_frame_version`` from ``run.runtime_info`` JSONB (PRP-36).

    Returns the int when the key is present, else **V=1**. This is the
    same load-bearing back-compat seam as
    :meth:`RegistryService._feature_frame_version_filter` — a legacy run
    that pre-dates PRP-35 is treated as V=1 everywhere in the ops layer
    so that ``_alias_staleness`` doesn't fabricate a
    ``feature_frame_version_mismatch`` between a legacy alias and an
    explicit-V=1 comparable run.

    Notes:
        The schema-side :attr:`RunResponse.feature_frame_version` deliberately
        keeps ``None`` for "key absent" — UIs that need to distinguish
        "no V info" from "V=1" can do so off the response, while internal
        comparison logic uses this normalized helper.
    """
    info = run.runtime_info or {}
    value = info.get("feature_frame_version")
    # Honor any positive int V (feature_frame_version is an opaque incrementing
    # integer per docs/_base/DOMAIN_MODEL.md). bool is excluded because it
    # subclasses int. Missing / invalid value -> V=1 back-compat (#338).
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return value
    return 1


def _alias_staleness(
    run: ModelRun,
    latest_success_by_grain: dict[tuple[int, int], ModelRun],
) -> tuple[bool, str | None, int, int | None]:
    """Decide whether an aliased run is stale, and why (PRP-36).

    An alias is stale when:
      1. its run is no longer a successful run, OR
      2. a newer successful run exists for the same ``(store, product)``
         grain — the industry-standard alias-staleness check, OR
      3. a comparable run exists at a DIFFERENT ``feature_frame_version``
         from the alias's run (PRP-36 — V1 vs V2 mismatch).

    The V-mismatch branch fires whenever an alias's run V_a differs from
    the latest comparable run V_b — even when timestamps match — because
    Slice C surfaces it distinctly from "a newer run exists".

    Args:
        run: The model run the alias points at.
        latest_success_by_grain: Latest successful run keyed by (store, product).

    Returns:
        ``(is_stale, reason, alias_v, comparable_v)``. ``reason`` is None
        when not stale. ``alias_v`` is always an int (legacy runs without
        the JSONB key are normalized to V=1 — see
        :func:`_run_feature_frame_version`). ``comparable_v`` is non-None
        only when the mismatch branch fires.
    """
    alias_v = _run_feature_frame_version(run)
    if run.status != RunStatus.SUCCESS.value:
        return True, StaleReason.RUN_NOT_SUCCESS.value, alias_v, None
    latest = latest_success_by_grain.get((run.store_id, run.product_id))
    if latest is None or latest.id == run.id:
        return False, None, alias_v, None

    latest_v = _run_feature_frame_version(latest)
    # PRP-36 — V-mismatch wins over NEWER_SUCCESS_RUN. A V1 alias with a
    # newer V2 comparable run is classified as a mismatch so Slice C can
    # surface "this alias's V is now stale" distinctly from "a newer run
    # exists at the same V". Both sides are normalized via the helper so
    # a legacy missing-key run never spuriously mismatches an explicit
    # V=1 comparable run.
    if alias_v != latest_v:
        return (
            True,
            StaleReason.FEATURE_FRAME_VERSION_MISMATCH.value,
            alias_v,
            latest_v,
        )

    if latest.created_at > run.created_at:
        return True, StaleReason.NEWER_SUCCESS_RUN.value, alias_v, None
    return False, None, alias_v, None


# =============================================================================
# Service
# =============================================================================


class OpsService:
    """Read-only operational aggregation for the Control Center."""

    async def get_summary(self, db: AsyncSession) -> OpsSummaryResponse:
        """Aggregate system, job, run, alias, and freshness state.

        Args:
            db: Database session.

        Returns:
            The full operational summary. Never raises on an empty database —
            every section degrades to zeros / nulls / empty lists.
        """
        now = datetime.now(UTC)

        # ---- System health ------------------------------------------------
        try:
            await db.execute(text("SELECT 1"))
            database_connected = True
        except Exception:
            # Deliberate connectivity probe: any failure means "not connected".
            database_connected = False

        latest_successful_job_at = await db.scalar(
            select(func.max(Job.completed_at)).where(Job.status == JobStatus.COMPLETED.value)
        )

        # ---- Job health ---------------------------------------------------
        job_count_rows = (
            await db.execute(select(Job.status, func.count()).group_by(Job.status))
        ).all()
        job_count_map: dict[str, int] = {str(row[0]): int(row[1]) for row in job_count_rows}
        job_counts = [
            StatusCount(status=status.value, count=job_count_map.get(status.value, 0))
            for status in JobStatus
        ]
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        completed_today = int(
            await db.scalar(
                select(func.count())
                .select_from(Job)
                .where(
                    Job.status == JobStatus.COMPLETED.value,
                    Job.completed_at >= start_of_day,
                )
            )
            or 0
        )
        jobs = JobHealth(
            counts=job_counts,
            completed_today=completed_today,
            failed_total=job_count_map.get(JobStatus.FAILED.value, 0),
            active_total=(
                job_count_map.get(JobStatus.PENDING.value, 0)
                + job_count_map.get(JobStatus.RUNNING.value, 0)
            ),
        )

        # ---- Run health ---------------------------------------------------
        run_count_rows = (
            await db.execute(select(ModelRun.status, func.count()).group_by(ModelRun.status))
        ).all()
        run_count_map: dict[str, int] = {str(row[0]): int(row[1]) for row in run_count_rows}
        run_counts = [
            StatusCount(status=status.value, count=run_count_map.get(status.value, 0))
            for status in RunStatus
        ]
        eligible = sum(run_count_map.values()) - run_count_map.get(RunStatus.ARCHIVED.value, 0)
        success_rate = (
            run_count_map.get(RunStatus.SUCCESS.value, 0) / eligible if eligible > 0 else None
        )
        runs = RunHealth(
            counts=run_counts,
            success_rate=success_rate,
            failed_total=run_count_map.get(RunStatus.FAILED.value, 0),
        )

        # ---- Alias health -------------------------------------------------
        # Latest successful run per (store, product) — the staleness baseline.
        latest_success_runs = (
            (
                await db.execute(
                    select(ModelRun)
                    .where(ModelRun.status == RunStatus.SUCCESS.value)
                    .distinct(ModelRun.store_id, ModelRun.product_id)
                    .order_by(
                        ModelRun.store_id,
                        ModelRun.product_id,
                        ModelRun.created_at.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        latest_success_by_grain: dict[tuple[int, int], ModelRun] = {
            (run.store_id, run.product_id): run for run in latest_success_runs
        }

        # Two-query alias load. NEVER touch DeploymentAlias.run — accessing that
        # relationship under AsyncSession triggers a lazy load (MissingGreenlet).
        # Resolve the integer FK into a typed map of single-entity rows instead.
        alias_rows = (await db.execute(select(DeploymentAlias))).scalars().all()
        alias_run_ids = {alias.run_id for alias in alias_rows}
        runs_by_id: dict[int, ModelRun] = {}
        if alias_run_ids:
            runs_by_id = {
                run.id: run
                for run in (
                    (await db.execute(select(ModelRun).where(ModelRun.id.in_(alias_run_ids))))
                    .scalars()
                    .all()
                )
            }

        aliases: list[AliasHealth] = []
        stale_alias_items: list[AttentionItem] = []
        for alias in alias_rows:
            run = runs_by_id.get(alias.run_id)
            if run is None:  # orphan FK — defensive; the FK constraint forbids it
                continue
            is_stale, stale_reason, alias_v, comparable_v = _alias_staleness(
                run, latest_success_by_grain
            )
            aliases.append(
                AliasHealth(
                    alias_name=alias.alias_name,
                    run_id=run.run_id,
                    run_status=run.status,
                    model_type=run.model_type,
                    store_id=run.store_id,
                    product_id=run.product_id,
                    is_stale=is_stale,
                    stale_reason=stale_reason,
                    wape=extract_wape(run.metrics),
                    alias_feature_frame_version=alias_v,
                    comparable_run_feature_frame_version=comparable_v,
                )
            )
            if is_stale:
                stale_alias_items.append(
                    AttentionItem(
                        item_type="stale_alias",
                        entity_id=run.run_id,
                        label=f"alias '{alias.alias_name}' is stale",
                        detail=stale_reason or "alias is stale",
                        occurred_at=run.created_at,
                    )
                )

        # ---- Data freshness -----------------------------------------------
        freshness = DataFreshness(
            latest_sales_date=await db.scalar(select(func.max(SalesDaily.date))),
            latest_job_completed_at=await db.scalar(select(func.max(Job.completed_at))),
            latest_run_completed_at=await db.scalar(
                select(func.max(ModelRun.completed_at)).where(
                    ModelRun.status == RunStatus.SUCCESS.value
                )
            ),
        )

        # ---- Attention items ----------------------------------------------
        failed_jobs = (
            (
                await db.execute(
                    select(Job)
                    .where(Job.status == JobStatus.FAILED.value)
                    .order_by(Job.created_at.desc())
                    .limit(_ATTENTION_LIMIT)
                )
            )
            .scalars()
            .all()
        )
        failed_runs = (
            (
                await db.execute(
                    select(ModelRun)
                    .where(ModelRun.status == RunStatus.FAILED.value)
                    .order_by(ModelRun.created_at.desc())
                    .limit(_ATTENTION_LIMIT)
                )
            )
            .scalars()
            .all()
        )

        attention_items: list[AttentionItem] = [
            AttentionItem(
                item_type="failed_job",
                entity_id=job.job_id,
                label=f"{job.job_type} job failed",
                detail=job.error_message or job.error_type or "Job failed",
                occurred_at=job.created_at,
            )
            for job in failed_jobs
        ]
        attention_items.extend(
            AttentionItem(
                item_type="failed_run",
                entity_id=run.run_id,
                label=f"{run.model_type} run failed",
                detail=run.error_message or "Run failed",
                occurred_at=run.created_at,
            )
            for run in failed_runs
        )
        attention_items.extend(stale_alias_items)

        logger.info(
            "ops.summary_computed",
            database_connected=database_connected,
            failed_jobs=len(failed_jobs),
            failed_runs=len(failed_runs),
            stale_aliases=len(stale_alias_items),
        )

        return OpsSummaryResponse(
            system=SystemHealth(
                api_ok=True,
                database_connected=database_connected,
                latest_successful_job_at=latest_successful_job_at,
            ),
            jobs=jobs,
            runs=runs,
            aliases=aliases,
            freshness=freshness,
            attention_items=attention_items,
            generated_at=now,
        )

    async def get_retraining_candidates(
        self, db: AsyncSession, limit: int
    ) -> RetrainingCandidatesResponse:
        """Rank ``(store, product)`` grains by retraining priority.

        One candidate per grain — derived from its latest successful run.

        Args:
            db: Database session.
            limit: Maximum candidates to return (bounded 1..100 by the route).

        Returns:
            Candidates sorted by ``priority_score`` descending, capped at limit.
        """
        today = datetime.now(UTC).date()

        # Latest successful run per (store, product) — DISTINCT ON requires the
        # ORDER BY to lead with the DISTINCT ON columns; created_at (non-null
        # TimestampMixin column) is the "latest" tiebreaker.
        latest_success_runs = (
            (
                await db.execute(
                    select(ModelRun)
                    .where(ModelRun.status == RunStatus.SUCCESS.value)
                    .distinct(ModelRun.store_id, ModelRun.product_id)
                    .order_by(
                        ModelRun.store_id,
                        ModelRun.product_id,
                        ModelRun.created_at.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )

        candidates: list[RetrainingCandidate] = []
        for run in latest_success_runs:
            raw_staleness = (today - run.data_window_end).days
            staleness_days = max(raw_staleness, 0)
            wape = extract_wape(run.metrics)
            score = score_retraining_candidate(raw_staleness, wape)
            wape_part = f"WAPE {wape:.1f}" if wape is not None else "WAPE unknown"
            candidates.append(
                RetrainingCandidate(
                    store_id=run.store_id,
                    product_id=run.product_id,
                    priority_score=score,
                    staleness_days=staleness_days,
                    wape=wape,
                    latest_run_id=run.run_id,
                    latest_run_status=run.status,
                    reason=f"{staleness_days}d since last training window; {wape_part}",
                )
            )

        candidates.sort(key=lambda candidate: candidate.priority_score, reverse=True)

        logger.info(
            "ops.retraining_candidates_computed",
            total_evaluated=len(candidates),
            returned=min(limit, len(candidates)),
        )

        return RetrainingCandidatesResponse(
            candidates=candidates[:limit],
            total_evaluated=len(candidates),
            generated_at=datetime.now(UTC),
        )

    async def get_model_health(self, db: AsyncSession, limit: int) -> ModelHealthResponse:
        """Classify per-grain forecast-error drift from full run history.

        Unlike the retraining queue, this needs the *full* WAPE history per
        grain (not just the latest run), so it queries every successful run
        ordered by grain then creation time and groups in Python with
        ``itertools.groupby`` — NOT ``DISTINCT ON``.

        Args:
            db: Database session.
            limit: Maximum grains to return (bounded 1..100 by the route).

        Returns:
            Grains sorted degrading-first, then by ``|wape_delta|`` descending,
            capped at ``limit``. Never raises on an empty database.
        """
        today = datetime.now(UTC).date()

        # FULL history — NOT DISTINCT ON. Ordered by (store, product, created_at)
        # so itertools.groupby batches each grain in chronological order.
        success_runs = (
            (
                await db.execute(
                    select(ModelRun)
                    .where(ModelRun.status == RunStatus.SUCCESS.value)
                    .order_by(
                        ModelRun.store_id,
                        ModelRun.product_id,
                        ModelRun.created_at,
                    )
                )
            )
            .scalars()
            .all()
        )

        entries: list[ModelHealthEntry] = []
        for (store_id, product_id), grain_iter in groupby(
            success_runs, key=lambda run: (run.store_id, run.product_id)
        ):
            grain_runs = list(grain_iter)  # already chronological
            history = [
                WapePoint(
                    run_id=run.run_id,
                    created_at=run.created_at,
                    wape=extract_wape(run.metrics),
                )
                for run in grain_runs
            ]
            direction, delta = classify_drift([point.wape for point in history])
            numeric = [point.wape for point in history if point.wape is not None]
            latest_run = grain_runs[-1]
            # PRP-36 — surface the alias (latest-run) V and, when an earlier
            # run in the chain carries a DIFFERENT V, the comparable V so
            # Slice C can flag the mismatch on the model-health view too.
            latest_run_v = _run_feature_frame_version(latest_run)
            mismatch_v: int | None = None
            for prior_run in grain_runs[:-1]:
                prior_v = _run_feature_frame_version(prior_run)
                if prior_v != latest_run_v:
                    mismatch_v = prior_v
                    break
            entries.append(
                ModelHealthEntry(
                    store_id=store_id,
                    product_id=product_id,
                    run_count=len(grain_runs),
                    latest_run_id=latest_run.run_id,
                    latest_run_status=latest_run.status,
                    latest_wape=(numeric[-1] if numeric else None),
                    previous_wape=(numeric[-2] if len(numeric) > 1 else None),
                    wape_delta=delta,
                    drift_direction=direction,
                    last_trained_at=latest_run.created_at,
                    staleness_days=max((today - latest_run.data_window_end).days, 0),
                    wape_history=history,
                    alias_feature_frame_version=latest_run_v,
                    comparable_run_feature_frame_version=mismatch_v,
                )
            )

        # Degrading grains first; within a tier, the largest WAPE move leads.
        rank: dict[str, int] = {"degrading": 0, "improving": 1, "stable": 2, "unknown": 3}
        entries.sort(key=lambda entry: (rank[entry.drift_direction], -abs(entry.wape_delta or 0.0)))

        logger.info("ops.model_health_computed", grains=len(entries))

        return ModelHealthResponse(
            entries=entries[:limit],
            total_evaluated=len(entries),
            generated_at=datetime.now(UTC),
        )
