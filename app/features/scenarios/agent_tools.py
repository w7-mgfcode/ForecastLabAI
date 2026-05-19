"""Agent-facing tools for the Scenario Simulation slice (PRP-27 Phase D).

This module is the *integration seam* between the agent layer and the
scenarios slice. ``app/features/agents/`` imports THIS module — never
``scenarios/service.py`` directly — so the no-cross-slice-``service.py``-import
rule (DECISIONS LOCKED #3) holds while the agent still gains scenario tools.

Two tools live here:

* :func:`propose_scenario` — **read-only**. Returns a candidate
  ``ScenarioAssumptions`` plus a plain-language recommendation. It proposes,
  it never persists, so it needs no approval.
* :func:`save_scenario` — **mutating**. Persists a ``scenario_plan`` row via the
  scenarios service create path, stamped ``source='agent'`` with the originating
  ``agent_session_id`` and the HITL approval audit trail. It runs only after the
  human-in-the-loop gate releases it — its tool name is in
  ``agent_require_approval`` (DECISIONS LOCKED #13).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.data_platform.models import SalesDaily
from app.features.scenarios.models import SCENARIO_SOURCE_AGENT
from app.features.scenarios.schemas import (
    CreateScenarioRequest,
    PriceAssumption,
    PromotionAssumption,
    SaveScenarioRequest,
    ScenarioAssumptions,
)
from app.features.scenarios.service import ScenarioService

logger = structlog.get_logger()

# Keywords in a free-text objective that steer the proposal toward a promotion
# rather than the default price cut.
_PROMOTION_KEYWORDS = ("promo", "promotion", "discount", "sale", "markdown")

# The default magnitude of the proposed price cut (a 15% reduction).
_PROPOSED_PRICE_CHANGE_PCT = -0.15

# Recorded as ``approved_by`` on an agent-saved plan. The system is single-host
# and unauthenticated, so the approving party is simply the local operator who
# released the HITL gate.
AGENT_SAVE_APPROVED_BY = "operator"


async def propose_scenario(
    db: AsyncSession,
    store_id: int,
    product_id: int,
    horizon: int,
    objective: str,
) -> dict[str, Any]:
    """Propose a candidate what-if scenario for a (store, product) grain.

    READ-ONLY: this tool builds a candidate ``ScenarioAssumptions`` and a
    recommendation; it performs no database writes. Persisting the proposal is
    a separate, approval-gated step (:func:`save_scenario`).

    Args:
        db: Database session (used only to read a recent unit price for a
            grounded recommendation).
        store_id: Store the proposed scenario targets.
        product_id: Product the proposed scenario targets.
        horizon: Number of days the proposed scenario should span.
        objective: Free-text planning objective — keywords such as "promotion"
            steer the proposal toward a promotion instead of a price cut.

    Returns:
        A dict with the target grain, the horizon, the originating objective,
        the candidate ``assumptions`` (JSON-mode dump so dates are ISO strings,
        ready to pass straight back into ``save_scenario``), and a
        plain-language ``recommendation``.
    """
    logger.info(
        "agents.scenario_tool.propose_scenario_called",
        store_id=store_id,
        product_id=product_id,
        horizon=horizon,
    )

    # Read the most recent unit price for a grounded recommendation. Read-only.
    latest_price = await db.scalar(
        select(SalesDaily.unit_price)
        .where(SalesDaily.store_id == store_id, SalesDaily.product_id == product_id)
        .order_by(SalesDaily.date.desc())
        .limit(1)
    )

    start = datetime.now(UTC).date() + timedelta(days=1)
    end = start + timedelta(days=horizon - 1)

    if any(keyword in objective.lower() for keyword in _PROMOTION_KEYWORDS):
        assumptions = ScenarioAssumptions(
            promotion=PromotionAssumption(kind="pct_off", start_date=start, end_date=end)
        )
        rationale = (
            f"Run a pct_off promotion from {start} to {end} ({horizon} days) and "
            "simulate the demand lift before committing."
        )
    else:
        assumptions = ScenarioAssumptions(
            price=PriceAssumption(
                change_pct=_PROPOSED_PRICE_CHANGE_PCT, start_date=start, end_date=end
            )
        )
        price_note = (
            f" The most recent unit price is ~{float(latest_price):.2f}."
            if latest_price is not None
            else ""
        )
        rationale = (
            f"Cut price {abs(_PROPOSED_PRICE_CHANGE_PCT) * 100:.0f}% from {start} to "
            f"{end} ({horizon} days) to test the demand response.{price_note}"
        )

    recommendation = (
        f"Proposed what-if for store {store_id} / product {product_id} toward the "
        f"objective '{objective}'. {rationale} This is a candidate only — review it "
        "and save it explicitly to persist a scenario plan."
    )
    return {
        "store_id": store_id,
        "product_id": product_id,
        "horizon": horizon,
        "objective": objective,
        "assumptions": assumptions.model_dump(mode="json"),
        "recommendation": recommendation,
    }


async def save_scenario(
    db: AsyncSession,
    request: SaveScenarioRequest,
    *,
    agent_session_id: str | None,
) -> dict[str, Any]:
    """Persist an agent-proposed scenario as a saved ``scenario_plan`` row.

    MUTATING: this tool writes a row. It runs only once the HITL approval gate
    has released it (``save_scenario`` is in ``agent_require_approval``), so the
    persisted plan always carries an ``approved`` audit trail.

    Args:
        db: Database session.
        request: The validated scenario to persist (name, run_id, horizon,
            assumptions).
        agent_session_id: The originating agent session id — the runtime truth,
            authoritative over any value carried on ``request``.

    Returns:
        The saved plan as a JSON-mode dict, including its embedded comparison
        snapshot and the provenance / audit fields.

    Raises:
        FileNotFoundError: When no model artifact exists for ``request.run_id``.
        ValueError: When the artifact path or its metadata is invalid.
    """
    logger.info(
        "agents.scenario_tool.save_scenario_called",
        store_id=request.store_id,
        product_id=request.product_id,
        agent_session_id=agent_session_id,
    )

    service = ScenarioService()
    create_request = CreateScenarioRequest(
        name=request.name,
        run_id=request.run_id,
        horizon=request.horizon,
        assumptions=request.assumptions,
    )
    plan = await service.create_plan(
        db,
        create_request,
        source=SCENARIO_SOURCE_AGENT,
        agent_session_id=agent_session_id,
        approved_by=AGENT_SAVE_APPROVED_BY,
        approval_decision="approved",
    )

    logger.info(
        "agents.scenario_tool.save_scenario_completed",
        scenario_id=plan.scenario_id,
        agent_session_id=agent_session_id,
    )
    return plan.model_dump(mode="json")
