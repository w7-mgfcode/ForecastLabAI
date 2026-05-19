"""Scenario plan ORM model.

A ``scenario_plan`` row persists a saved what-if analysis: the raw
``ScenarioAssumptions`` *and* the full ``ScenarioComparison`` snapshot, both as
JSONB. Storing the snapshot (PRP-26 decision #3) means a reloaded plan
re-renders without recomputation — and without the original model artifact
still having to exist on disk.

GOTCHA: SQLAlchemy reserves the declarative attribute name ``metadata``; the
JSONB columns are therefore named ``assumptions`` and ``comparison``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import TimestampMixin

# Adjustment methods — guarded by a CHECK constraint. ``heuristic`` is the MVP
# post-forecast multiplier; ``model_exogenous`` (PRP-27) re-forecasts through a
# feature-consuming regression model.
SCENARIO_METHOD_HEURISTIC = "heuristic"
SCENARIO_METHOD_MODEL_EXOGENOUS = "model_exogenous"


class ScenarioPlan(TimestampMixin, Base):
    """A saved scenario plan.

    Attributes:
        id: Surrogate primary key.
        scenario_id: Unique external identifier (UUID hex, 32 chars).
        name: Human-readable plan name.
        store_id: Store the baseline model targets.
        product_id: Product the baseline model targets.
        run_id: Artifact key of the baseline model (model_{run_id}.joblib).
        horizon: Number of days simulated.
        assumptions: Raw ScenarioAssumptions as JSONB.
        comparison: Full ScenarioComparison snapshot as JSONB.
        method: Adjustment method — always 'heuristic' (CHECK-constrained).
    """

    __tablename__ = "scenario_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    store_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)

    # JSONB blobs — never named ``metadata`` (SQLAlchemy reserves it).
    assumptions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    comparison: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    method: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SCENARIO_METHOD_HEURISTIC
    )

    # Scenario-library columns (PRP-27 Phase C). ``tags`` is a JSONB string
    # array — a real column (never folded into a JSONB blob) so it is
    # queryable/indexable. ``cloned_from`` is the scenario_id this plan was
    # cloned from, or NULL.
    tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    cloned_from: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        # GIN indexes for JSONB containment queries on either blob.
        Index("ix_scenario_plan_assumptions_gin", "assumptions", postgresql_using="gin"),
        Index("ix_scenario_plan_comparison_gin", "comparison", postgresql_using="gin"),
        # Composite index for the common "plans for this store/product" query.
        Index("ix_scenario_plan_store_product", "store_id", "product_id"),
        # GIN index so the saved-plans list can filter by tag containment.
        Index("ix_scenario_plan_tags_gin", "tags", postgresql_using="gin"),
        # heuristic (MVP) or model_exogenous (PRP-27) — kept in lock-step with
        # the alembic migration that widened this CHECK.
        CheckConstraint(
            "method IN ('heuristic', 'model_exogenous')",
            name="ck_scenario_plan_method",
        ),
    )
