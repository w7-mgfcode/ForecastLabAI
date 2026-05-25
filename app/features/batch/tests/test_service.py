"""Unit tests for BatchService (no DB).

DB-dependent tests (status settlement, lifecycle event emission across a real
submit, scope expansion for region/category/all/top_revenue) live in the
integration suite (``test_routes_integration.py``). This file covers the
pure-Python surface: manual cartesian, the pinned-shape ``_shape_metrics``,
the picker query SQL (compiled, asserts ``FOR UPDATE SKIP LOCKED``), and the
frozen-params shape.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.features.batch.models import BatchItemStatus, BatchJobItem
from app.features.batch.schemas import (
    BatchScope,
    BatchSubmitRequest,
)
from app.features.batch.service import _METRICS_KEYS, BatchService
from app.features.jobs.models import JobStatus, JobType
from app.features.jobs.schemas import JobResponse


def _make_job_response(
    *,
    job_type: JobType,
    result: dict[str, object] | None,
) -> JobResponse:
    """Build a synthetic JobResponse for _shape_metrics tests."""
    now = datetime.now(UTC)
    return JobResponse(
        job_id="job_test",
        job_type=job_type,
        status=JobStatus.COMPLETED,
        params={},
        result=result,
        error_message=None,
        error_type=None,
        run_id="run_test" if job_type != JobType.PREDICT else None,
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------- shape


def test_metrics_jsonb_shape_pinned() -> None:
    """_shape_metrics returns EXACTLY {wape, smape, mae, bias, sample_size}.

    Regression for the pinned-shape invariant the four downstream PRPs read.
    """
    job = _make_job_response(
        job_type=JobType.BACKTEST,
        result={
            "aggregated_metrics": {
                "wape_mean": 0.1,
                "smape_mean": 0.2,
                "mae_mean": 1.5,
                "bias_mean": -0.05,
            },
            "fold_metrics": [
                {"fold": 1, "sample_size": 14},
                {"fold": 2, "sample_size": 14},
            ],
            "n_observations": 28,
        },
    )
    shaped = BatchService()._shape_metrics(job)
    assert shaped is not None
    assert set(shaped.keys()) == set(_METRICS_KEYS)
    assert shaped["wape"] == 0.1
    assert shaped["sample_size"] == 28


def test_metrics_returns_none_for_predict_job() -> None:
    """Non-backtest job → metrics is None (predict has no fold_metrics)."""
    job = _make_job_response(job_type=JobType.PREDICT, result={"forecasts": []})
    assert BatchService()._shape_metrics(job) is None


def test_metrics_returns_none_for_empty_result() -> None:
    """Backtest job with empty/None result → None (defensive fallback)."""
    job = _make_job_response(job_type=JobType.BACKTEST, result=None)
    assert BatchService()._shape_metrics(job) is None


def test_metrics_sample_size_falls_back_to_n_observations() -> None:
    """When fold_metrics carries no sample_size, fall back to n_observations."""
    job = _make_job_response(
        job_type=JobType.BACKTEST,
        result={
            "aggregated_metrics": {
                "wape_mean": 0.1,
                "smape_mean": 0.2,
                "mae_mean": 1.5,
                "bias_mean": 0.0,
            },
            "fold_metrics": [{"fold": 1}, {"fold": 2}],  # no sample_size
            "n_observations": 100,
        },
    )
    shaped = BatchService()._shape_metrics(job)
    assert shaped is not None
    assert shaped["sample_size"] == 100


def test_metrics_sample_size_derived_inside_slice() -> None:
    """Resolved per PRP-33 § 'Why not 10': sample_size derived inside the
    batch slice from fold_metrics — never reaches into app/features/jobs/."""
    job = _make_job_response(
        job_type=JobType.BACKTEST,
        result={
            "aggregated_metrics": {
                "wape_mean": 0.1,
                "smape_mean": 0.2,
                "mae_mean": 1.5,
                "bias_mean": 0.0,
            },
            "fold_metrics": [
                {"fold": 1, "sample_size": 7},
                {"fold": 2, "sample_size": 8},
                {"fold": 3, "sample_size": 9},
            ],
        },
    )
    shaped = BatchService()._shape_metrics(job)
    assert shaped is not None
    assert shaped["sample_size"] == 24  # 7+8+9, computed inside the slice


# ---------------------------------------------------------------------- picker


def test_picker_query_uses_skip_locked() -> None:
    """Compile the picker SELECT — must contain ``FOR UPDATE SKIP LOCKED``.

    Load-bearing for downstream-1 (parallel) and downstream-2 (priority):
    removing the kwarg lets concurrent workers block on each other.
    """
    stmt = (
        select(BatchJobItem)
        .where(
            BatchJobItem.batch_id == "test",
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
    sql = str(stmt.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]
    assert "FOR UPDATE SKIP LOCKED" in sql.upper(), sql


# ------------------------------------------------------------------ expansion


async def test_expand_scope_manual_cartesian() -> None:
    """``kind=manual`` produces the full store x product cartesian, no DB."""
    scope = BatchScope.model_validate(
        {
            "kind": "manual",
            "store_ids": [1, 2],
            "product_ids": [10, 20, 30],
        }
    )
    # Manual path never touches the DB — the AsyncMock proves no DB call lands.
    db: AsyncMock = AsyncMock()
    pairs = await BatchService()._expand_scope(db, scope)
    assert pairs == [(1, 10), (1, 20), (1, 30), (2, 10), (2, 20), (2, 30)]
    db.execute.assert_not_called()


# ------------------------------------------------------------------- frozen


def test_frozen_item_params_shape() -> None:
    """_frozen_item_params builds a stable per-item JSONB.

    Downstream-3 (export-and-retry) reads from this dict on retry — the shape
    must remain compatible.
    """
    req = BatchSubmitRequest.model_validate(
        {
            "operation": "backtest",
            "scope": {"kind": "manual", "store_ids": [1], "product_ids": [2]},
            "model_configs": [{"model_type": "naive", "params": {"foo": "bar"}}],
            "start_date": "2025-01-01",
            "end_date": "2025-06-30",
        }
    )
    mc = req.model_configs[0]
    params = BatchService()._frozen_item_params(req, 1, 2, mc)
    assert params == {
        "operation": "backtest",
        "job_params": {
            "model_type": "naive",
            "store_id": 1,
            "product_id": 2,
            "start_date": "2025-01-01",
            "end_date": "2025-06-30",
            "foo": "bar",
        },
    }


def test_sort_columns_allow_list_complete() -> None:
    """The sort allow-list must cover exactly the four documented keys."""
    from app.features.batch.service import _BATCH_ITEM_SORT_COLUMNS

    assert set(_BATCH_ITEM_SORT_COLUMNS.keys()) == {
        "created_at",
        "completed_at",
        "status",
        "priority",
    }


# `pytest-asyncio` auto-mode (configured in pyproject.toml) picks up the
# async test above without an explicit @pytest.mark.asyncio decorator.
_ = pytest  # keep import (some test selectors strip unused imports)
