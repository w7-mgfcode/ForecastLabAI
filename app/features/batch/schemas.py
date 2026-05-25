"""Pydantic v2 schemas for the batch runner slice (PRP-33).

All request bodies use ``ConfigDict(strict=True)`` per docs/_base/SECURITY.md
§ "Pydantic v2 strict mode on FastAPI request bodies"; the only JSON-non-native
fields (``start_date`` / ``end_date``) carry ``Field(strict=False, ...)`` so
the strict-mode policy linter (app/core/tests/test_strict_mode_policy.py)
passes.

The ``BatchScope.kind`` / selector consistency check uses
``model_validator(mode="after")`` — invalid combinations (e.g. ``kind=manual``
without ``store_ids``) raise ``ValueError`` and FastAPI surfaces as RFC 7807
422 via the validation exception handler in ``app/core/exceptions.py``.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.features.batch.models import BatchItemStatus, BatchOperation, BatchStatus

# Allow-listed model types — mirrors ``app/features/jobs/service.py``'s
# accepted set. Adding a type here REQUIRES adding it to the JobService's
# _execute_train/_execute_backtest branches; the runner delegates blindly.
VALID_MODEL_TYPES: frozenset[str] = frozenset(
    {
        "naive",
        "seasonal_naive",
        "moving_average",
        "regression",
        "lightgbm",
        "xgboost",
        "prophet_like",
    }
)


class BatchScopeKind(str, Enum):
    """Five ways to express a batch's (store, product) coverage.

    - MANUAL: explicit ``store_ids`` x``product_ids`` cartesian.
    - REGION: every store in ``region`` xall products.
    - CATEGORY: all stores xevery product in ``category``.
    - TOP_REVENUE: top ``top_n`` (store, product) pairs by revenue over the
      submit window.
    - ALL: full store xproduct cartesian.
    """

    MANUAL = "manual"
    REGION = "region"
    CATEGORY = "category"
    TOP_REVENUE = "top_revenue"
    ALL = "all"


class BatchScope(BaseModel):
    """Scope selector — one shape, five kinds enforced by model_validator.

    ``kind`` is ``Literal[...]`` (not the ``BatchScopeKind`` enum) because the
    enclosing ``BatchSubmitRequest`` runs in strict mode — Pydantic v2's
    strict mode refuses to coerce a JSON string into a str-enum instance.
    The literal carries the same value set; ``BatchScopeKind`` is retained
    for the response side and for internal callers.
    """

    model_config = ConfigDict(strict=True)

    kind: Literal["manual", "region", "category", "top_revenue", "all"]
    store_ids: list[int] | None = Field(default=None, description="Required if kind=manual")
    product_ids: list[int] | None = Field(default=None, description="Required if kind=manual")
    region: str | None = Field(default=None, description="Required if kind=region")
    category: str | None = Field(default=None, description="Required if kind=category")
    top_n: int | None = Field(
        default=None, ge=1, le=1000, description="Required if kind=top_revenue"
    )

    @model_validator(mode="after")
    def _check_kind_consistency(self) -> BatchScope:
        """Enforce kind→selector pairing. Mismatches surface as RFC 7807 422."""
        if self.kind == "manual":
            if not self.store_ids or not self.product_ids:
                raise ValueError("kind=manual requires non-empty store_ids and product_ids")
        elif self.kind == "region":
            if not self.region:
                raise ValueError("kind=region requires region")
        elif self.kind == "category":
            if not self.category:
                raise ValueError("kind=category requires category")
        elif self.kind == "top_revenue":
            if self.top_n is None:
                raise ValueError("kind=top_revenue requires top_n")
        # kind == "all": no extra selector required.
        return self


class BatchModelConfig(BaseModel):
    """One model spec — one row in the batch's model_configs list."""

    model_config = ConfigDict(strict=True)

    model_type: Literal[
        "naive",
        "seasonal_naive",
        "moving_average",
        "regression",
        "lightgbm",
        "xgboost",
        "prophet_like",
    ]
    params: dict[str, Any] = Field(default_factory=dict)


class BatchSubmitRequest(BaseModel):
    """POST /batch/forecasting request body.

    JSON-native fields stay strict; the two ``date`` fields carry
    ``Field(strict=False, ...)`` so the JSON ISO-string path works (see
    docs/_base/SECURITY.md and PR #115 / #119 for the precedent).
    """

    model_config = ConfigDict(strict=True)

    # ``operation`` is ``Literal[...]`` (not the BatchOperation enum) for the
    # same reason ``BatchScope.kind`` is: strict mode + str-enums coerce
    # poorly. Convert to the enum at the service boundary.
    operation: Literal["train", "predict", "backtest", "train_backtest_register"]
    scope: BatchScope
    model_configs: list[BatchModelConfig] = Field(min_length=1, max_length=10)
    start_date: date = Field(strict=False, description="YYYY-MM-DD")
    end_date: date = Field(strict=False, description="YYYY-MM-DD")
    # Forward-compat — accepted, validated, persisted; runner ignores in MVP.
    max_parallel: int = Field(default=4, ge=1, le=64)
    default_child_priority: int = Field(default=0, ge=-1, le=2)


class BatchItemResponse(BaseModel):
    """One item row — returned from /batch/{id}/items and embedded in the
    parent's settle path."""

    model_config = ConfigDict(from_attributes=True)

    item_id: str
    batch_id: str
    store_id: int
    product_id: int
    model_type: str
    status: BatchItemStatus
    priority: int
    metrics: dict[str, Any] | None
    child_job_id: str | None
    child_run_id: str | None
    error_message: str | None
    error_type: str | None
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    created_at: datetime
    updated_at: datetime


class BatchSubmitResponse(BaseModel):
    """Parent batch record — returned by submit + GET /batch/{id}.

    ``effective_max_parallel`` is a :func:`computed_field` resolved from
    ``result_summary["effective_max_parallel"]`` — the PRP-34 runner writes
    that key on every batch it executes. Legacy batches (pre-PRP-34) and any
    batch where the key is missing return ``0``. Storing the value in JSONB
    (rather than a real column) means PRP-34 ships with NO Alembic migration.
    """

    model_config = ConfigDict(from_attributes=True)

    batch_id: str
    operation: BatchOperation
    status: BatchStatus
    total_items: int
    completed_items: int
    failed_items: int
    running_items: int
    cancelled_items: int
    max_parallel: int
    started_at: datetime | None
    completed_at: datetime | None
    result_summary: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_max_parallel(self) -> int:
        """Resolved ``min(max_parallel, settings.batch_global_max_parallel)``.

        The PRP-34 runner persists this under ``result_summary`` on settle.
        Returns ``0`` for legacy pre-PRP-34 rows or where the key is missing.
        """
        if self.result_summary is None:
            return 0
        value = self.result_summary.get("effective_max_parallel", 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0


class BatchItemListResponse(BaseModel):
    """Paginated item listing — GET /batch/{id}/items."""

    items: list[BatchItemResponse]
    total: int
    page: int
    page_size: int
