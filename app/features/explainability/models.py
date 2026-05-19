"""ORM model for the explainability slice.

A ``forecast_explanation`` row persists one rule-based explanation: the driver
breakdown, advisory reason codes, and caveats as JSONB, plus scalar columns for
the forecast context. Persisting it means a re-requested explanation is a cheap
read and gives the slice an audit trail.

GOTCHA: SQLAlchemy reserves the declarative attribute name ``metadata`` — no
column here uses it.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import TimestampMixin


class ForecastExplanation(TimestampMixin, Base):
    """A persisted rule-based forecast explanation.

    Attributes:
        id: Surrogate primary key.
        explanation_id: Unique external identifier (UUID hex, 32 chars).
        run_id: Originating registry run, when explained via ``/explain/runs``.
        job_id: Originating predict job, when explained via ``/explain/jobs``.
        store_id: Store the forecast targets.
        product_id: Product the forecast targets.
        model_type: Baseline model type explained.
        method: Explanation method — always ``rule_based`` for the MVP.
        as_of_date: Series cutoff date.
        forecast_value: The h=1 forecast value.
        confidence: Qualitative confidence band (``high|medium|low``).
        drivers: Driver contributions as JSONB.
        reason_codes: Advisory reason codes as JSONB.
        caveats: Plain-language caveats as a JSONB string array.
        agent_summary: One-paragraph natural-language summary.
    """

    __tablename__ = "forecast_explanation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    explanation_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    store_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    model_type: Mapped[str] = mapped_column(String(50))
    method: Mapped[str] = mapped_column(String(20), default="rule_based")
    as_of_date: Mapped[datetime.date] = mapped_column(Date)
    forecast_value: Mapped[float] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(10))

    # JSONB blobs — never named ``metadata`` (SQLAlchemy reserves it).
    drivers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    reason_codes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    caveats: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    agent_summary: Mapped[str] = mapped_column(String(2000))

    __table_args__ = (
        # GIN index for JSONB containment queries on the driver breakdown.
        Index("ix_forecast_explanation_drivers_gin", "drivers", postgresql_using="gin"),
        # Composite index for the common "explanations for this store/product" query.
        Index("ix_forecast_explanation_store_product", "store_id", "product_id"),
        # Kept in lock-step with the alembic migration that created this table.
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="ck_forecast_explanation_confidence",
        ),
        CheckConstraint(
            "method IN ('rule_based', 'shap', 'component')",
            name="ck_forecast_explanation_method",
        ),
    )
