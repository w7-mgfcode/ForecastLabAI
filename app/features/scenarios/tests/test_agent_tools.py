"""Tests for the scenarios agent tools and the HITL save gate (PRP-27 Phase D).

Two layers:

* A unit test that the ``save_scenario`` tool name is wired into
  ``agent_require_approval`` — the mutation-surface guard.
* Integration tests (real PostgreSQL + a real model bundle, ``docker compose up
  -d`` required) covering ``propose_scenario`` (read-only — persists nothing),
  ``save_scenario`` (persists with agent provenance), and the HITL gate firing
  through ``AgentService.approve_action``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.agents.agents.base import requires_approval
from app.features.agents.models import AgentSession, AgentType, SessionStatus
from app.features.agents.service import AgentService
from app.features.scenarios.agent_tools import propose_scenario, save_scenario
from app.features.scenarios.models import ScenarioPlan
from app.features.scenarios.schemas import SaveScenarioRequest, ScenarioAssumptions
from app.features.scenarios.tests.conftest import TEST_PRODUCT_ID, TEST_STORE_ID


def test_save_scenario_requires_approval() -> None:
    """``save_scenario`` is in agent_require_approval — the mutation-surface gate."""
    assert "save_scenario" in get_settings().agent_require_approval
    assert requires_approval("save_scenario") is True


@pytest.mark.integration
class TestProposeScenario:
    """propose_scenario drafts a candidate and persists nothing."""

    async def test_returns_valid_assumptions_and_recommendation(
        self, db_session: AsyncSession
    ) -> None:
        """A default objective yields a valid price-cut candidate."""
        result = await propose_scenario(
            db_session,
            store_id=TEST_STORE_ID,
            product_id=TEST_PRODUCT_ID,
            horizon=14,
            objective="grow demand for the summer range",
        )

        # The candidate assumptions round-trip through the real schema.
        assumptions = ScenarioAssumptions.model_validate(result["assumptions"])
        assert assumptions.price is not None
        assert assumptions.price.change_pct < 0.0
        assert isinstance(result["recommendation"], str)
        assert result["recommendation"]

    async def test_promotion_keyword_proposes_a_promotion(self, db_session: AsyncSession) -> None:
        """An objective mentioning a promotion steers the candidate accordingly."""
        result = await propose_scenario(
            db_session,
            store_id=TEST_STORE_ID,
            product_id=TEST_PRODUCT_ID,
            horizon=7,
            objective="run a promotion next week",
        )

        assumptions = ScenarioAssumptions.model_validate(result["assumptions"])
        assert assumptions.promotion is not None
        assert assumptions.price is None

    async def test_persists_no_row(self, db_session: AsyncSession) -> None:
        """propose_scenario is read-only — it never writes a scenario_plan row."""
        await propose_scenario(
            db_session,
            store_id=TEST_STORE_ID,
            product_id=TEST_PRODUCT_ID,
            horizon=10,
            objective="test",
        )
        count = await db_session.scalar(select(func.count()).select_from(ScenarioPlan))
        assert count == 0


@pytest.mark.integration
class TestSaveScenario:
    """save_scenario persists a plan stamped with agent provenance."""

    async def test_persists_with_agent_provenance(
        self, db_session: AsyncSession, trained_model: str
    ) -> None:
        """A save stamps source='agent', the session id, and the audit trail."""
        request = SaveScenarioRequest(
            name="Saved by agent",
            assumptions=ScenarioAssumptions(),
            store_id=TEST_STORE_ID,
            product_id=TEST_PRODUCT_ID,
            horizon=7,
            run_id=trained_model,
        )

        result = await save_scenario(db_session, request, agent_session_id="sess-xyz")

        assert result["source"] == "agent"
        assert result["agent_session_id"] == "sess-xyz"
        assert result["approved_by"] == "operator"
        assert result["approval_decision"] == "approved"
        assert result["approved_at"] is not None

        rows = (await db_session.execute(select(ScenarioPlan))).scalars().all()
        assert len(rows) == 1
        assert rows[0].source == "agent"
        assert rows[0].agent_session_id == "sess-xyz"


@pytest.mark.integration
class TestSaveScenarioHITLGate:
    """The save_scenario HITL gate persists a row only once approved."""

    @staticmethod
    def _pending_save_action(session_id: str, run_id: str) -> dict[str, object]:
        """Build a pending save_scenario action for the given session."""
        now = datetime.now(UTC)
        return {
            "action_id": "act-save-1",
            "action_type": "save_scenario",
            "description": "Save the proposed scenario",
            "arguments": {
                "name": "Agent-proposed plan",
                "run_id": run_id,
                "store_id": TEST_STORE_ID,
                "product_id": TEST_PRODUCT_ID,
                "horizon": 7,
                "assumptions": {},
                "source": "agent",
                "agent_session_id": session_id,
            },
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        }

    async def _seed_session(self, db_session: AsyncSession, session_id: str, run_id: str) -> None:
        """Insert an experiment session awaiting a save_scenario approval."""
        now = datetime.now(UTC)
        db_session.add(
            AgentSession(
                session_id=session_id,
                agent_type=AgentType.EXPERIMENT.value,
                status=SessionStatus.AWAITING_APPROVAL.value,
                message_history=[],
                pending_action=self._pending_save_action(session_id, run_id),
                total_tokens_used=0,
                tool_calls_count=1,
                last_activity=now,
                expires_at=now + timedelta(minutes=30),
            )
        )
        await db_session.commit()

    async def test_approve_persists_agent_plan(
        self, db_session: AsyncSession, trained_model: str
    ) -> None:
        """Approving the pending action persists a row with the audit trail."""
        session_id = uuid.uuid4().hex  # session_id is VARCHAR(32) — hex is exactly 32
        await self._seed_session(db_session, session_id, trained_model)
        try:
            response = await AgentService().approve_action(
                db=db_session,
                session_id=session_id,
                action_id="act-save-1",
                approved=True,
            )

            assert response.status == "executed"
            assert isinstance(response.result, dict)
            assert response.result["source"] == "agent"

            rows = (
                (
                    await db_session.execute(
                        select(ScenarioPlan).where(ScenarioPlan.agent_session_id == session_id)
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 1
            assert rows[0].source == "agent"
            assert rows[0].approved_by == "operator"
            assert rows[0].approval_decision == "approved"
            assert rows[0].approved_at is not None
        finally:
            await db_session.execute(
                delete(AgentSession).where(AgentSession.session_id == session_id)
            )
            await db_session.commit()

    async def test_reject_persists_no_plan(
        self, db_session: AsyncSession, trained_model: str
    ) -> None:
        """Rejecting the pending action writes no scenario_plan row."""
        session_id = uuid.uuid4().hex  # session_id is VARCHAR(32) — hex is exactly 32
        await self._seed_session(db_session, session_id, trained_model)
        try:
            response = await AgentService().approve_action(
                db=db_session,
                session_id=session_id,
                action_id="act-save-1",
                approved=False,
            )

            assert response.status == "rejected"
            count = await db_session.scalar(select(func.count()).select_from(ScenarioPlan))
            assert count == 0
        finally:
            await db_session.execute(
                delete(AgentSession).where(AgentSession.session_id == session_id)
            )
            await db_session.commit()
