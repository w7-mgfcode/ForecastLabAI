"""Integration tests for the workspace persistence helpers (E1, #390).

``create_workspace`` / ``finalize_workspace`` open their OWN sessions via
``get_session_maker()`` -- these tests exercise that real write path against
the docker-compose Postgres; the ``db_session`` fixture is used only to read
back and to wipe rows on teardown.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.demo import workspace
from app.features.demo.models import (
    WORKSPACE_STATUS_COMPLETED,
    WORKSPACE_STATUS_FAILED,
    WORKSPACE_STATUS_RUNNING,
)
from app.features.demo.pipeline import DemoContext
from app.features.demo.schemas import DemoRunRequest
from app.shared.seeder.config import ScenarioPreset

pytestmark = pytest.mark.integration


def _keep_request(**overrides: object) -> DemoRunRequest:
    """Build a preservation='keep' request; keyword overrides win."""
    payload: dict[str, object] = {
        "seed": 7,
        "reset": False,
        "skip_seed": True,
        "preservation": "keep",
        "workspace_name": "it-keep",
    }
    payload.update(overrides)
    return DemoRunRequest.model_validate(payload)


def _finished_ctx() -> DemoContext:
    """Build a DemoContext as a green showcase run would leave it."""
    ctx = DemoContext(
        seed=7,
        skip_seed=True,
        reset=False,
        scenario=ScenarioPreset.DEMO_MINIMAL,
    )
    ctx.store_id = 7
    ctx.product_id = 3
    ctx.date_start = date(2026, 1, 1)
    ctx.date_end = date(2026, 3, 31)
    ctx.winner_model_type = "seasonal_naive"
    ctx.winner_wape = 0.15
    ctx.winning_run_id = "run-abc123def456"
    ctx.train_results = {"naive": {}, "seasonal_naive": {}, "moving_average": {}}
    ctx.session_id = "sess-0123abcd"
    return ctx


async def test_create_workspace_persists_config(db_session: AsyncSession) -> None:
    """create_workspace inserts a running row carrying the request config."""
    workspace_id = await workspace.create_workspace(_keep_request())
    assert workspace_id is not None

    row = await workspace.get_workspace(db_session, workspace_id)
    assert row is not None
    assert row.status == WORKSPACE_STATUS_RUNNING
    assert row.name == "it-keep"
    assert row.seed == 7
    assert row.scenario == "demo_minimal"
    assert row.reset is False
    assert row.skip_seed is True
    assert row.created_objects == {}
    assert row.result_summary is None


async def test_finalize_workspace_completed(db_session: AsyncSession) -> None:
    """finalize(failed=False) settles to completed with collected ids."""
    workspace_id = await workspace.create_workspace(_keep_request())
    assert workspace_id is not None

    await workspace.finalize_workspace(
        workspace_id, _finished_ctx(), failed=False, wall_clock_s=12.5
    )

    row = await workspace.get_workspace(db_session, workspace_id)
    assert row is not None
    assert row.status == WORKSPACE_STATUS_COMPLETED
    assert row.store_id == 7
    assert row.product_id == 3
    assert row.date_start == date(2026, 1, 1)
    assert row.date_end == date(2026, 3, 31)
    assert row.created_objects["winning_run_id"] == "run-abc123def456"
    assert row.created_objects["alias"] == "demo-production"
    assert row.created_objects["agent_session_id"] == "sess-0123abcd"
    assert row.created_objects["train_model_types"] == [
        "moving_average",
        "naive",
        "seasonal_naive",
    ]
    # None-valued accumulators are dropped, not stored as nulls.
    assert "v2_run_id" not in row.created_objects
    assert "batch_id" not in row.created_objects
    assert row.result_summary == {
        "winner_model_type": "seasonal_naive",
        "winner_wape": 0.15,
        "wall_clock_s": 12.5,
    }


async def test_finalize_workspace_failed(db_session: AsyncSession) -> None:
    """finalize(failed=True) settles to failed, still recording partial ids."""
    workspace_id = await workspace.create_workspace(_keep_request(workspace_name="it-fail"))
    assert workspace_id is not None

    ctx = _finished_ctx()
    ctx.winning_run_id = None  # run died before register
    ctx.winner_model_type = None
    ctx.winner_wape = None
    await workspace.finalize_workspace(workspace_id, ctx, failed=True, wall_clock_s=3.0)

    row = await workspace.get_workspace(db_session, workspace_id)
    assert row is not None
    assert row.status == WORKSPACE_STATUS_FAILED
    assert "winning_run_id" not in row.created_objects
    assert "alias" not in row.created_objects
    # Partial state still recorded -- the agent session + trained models.
    assert row.created_objects["agent_session_id"] == "sess-0123abcd"
    assert row.created_objects["train_model_types"] == [
        "moving_average",
        "naive",
        "seasonal_naive",
    ]


async def test_finalize_workspace_missing_id_is_noop(db_session: AsyncSession) -> None:
    """Finalizing an unknown workspace_id neither raises nor inserts."""
    await workspace.finalize_workspace(
        "deadbeef" * 4, _finished_ctx(), failed=False, wall_clock_s=1.0
    )
    rows = await workspace.list_workspaces(db_session)
    assert rows == []


async def test_list_workspaces_newest_first_limit_offset(db_session: AsyncSession) -> None:
    """list_workspaces orders newest first and honours limit/offset."""
    ids: list[str] = []
    for index in range(3):
        workspace_id = await workspace.create_workspace(
            _keep_request(workspace_name=f"it-list-{index}")
        )
        assert workspace_id is not None
        ids.append(workspace_id)

    rows = await workspace.list_workspaces(db_session)
    assert [r.workspace_id for r in rows] == list(reversed(ids))

    page = await workspace.list_workspaces(db_session, limit=1, offset=1)
    assert [r.workspace_id for r in page] == [ids[1]]


async def test_get_workspace_missing_returns_none(db_session: AsyncSession) -> None:
    """get_workspace returns None for an unknown id."""
    assert await workspace.get_workspace(db_session, "0" * 32) is None
