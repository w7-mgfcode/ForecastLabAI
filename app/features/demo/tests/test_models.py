"""Integration tests for the ShowcaseWorkspace ORM model (E1, #390).

Run against the real docker-compose Postgres (``docker compose up -d`` +
``uv run alembic upgrade head`` required). Constraint tests assert the
DB-level guarantees the migration created (unique workspace_id, status CHECK).
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.demo.models import (
    WORKSPACE_STATUS_COMPLETED,
    WORKSPACE_STATUS_RUNNING,
    ShowcaseWorkspace,
)
from app.features.demo.workspace import get_workspace

pytestmark = pytest.mark.integration


def _make_row(**overrides: object) -> ShowcaseWorkspace:
    """Build a valid ShowcaseWorkspace row; keyword overrides win."""
    values: dict[str, object] = {
        "workspace_id": uuid.uuid4().hex,
        "name": "it-row",
        "seed": 42,
        "scenario": "demo_minimal",
        "reset": False,
        "skip_seed": True,
    }
    values.update(overrides)
    return ShowcaseWorkspace(**values)


async def test_showcase_workspace_crud_roundtrip(db_session: AsyncSession) -> None:
    """Insert a full row incl. JSONB payloads and read it back intact."""
    created = {
        "winning_run_id": "run-abc123",
        "scenario_plan_ids": ["scn-1", "scn-2"],
    }
    summary = {"winner_model_type": "seasonal_naive", "winner_wape": 0.15}
    row = _make_row(
        status=WORKSPACE_STATUS_COMPLETED,
        store_id=7,
        product_id=3,
        date_start=date(2026, 1, 1),
        date_end=date(2026, 3, 31),
        created_objects=created,
        result_summary=summary,
    )
    db_session.add(row)
    await db_session.commit()

    loaded = await get_workspace(db_session, row.workspace_id)
    assert loaded is not None
    assert loaded.status == WORKSPACE_STATUS_COMPLETED
    assert loaded.name == "it-row"
    assert loaded.seed == 42
    assert loaded.scenario == "demo_minimal"
    assert loaded.store_id == 7
    assert loaded.product_id == 3
    assert loaded.date_start == date(2026, 1, 1)
    assert loaded.date_end == date(2026, 3, 31)
    assert loaded.created_objects == created
    assert loaded.result_summary == summary
    assert loaded.created_at is not None
    assert loaded.updated_at is not None


async def test_showcase_workspace_defaults_applied(db_session: AsyncSession) -> None:
    """A minimal insert gets running status + empty created_objects."""
    row = _make_row(name=None)
    db_session.add(row)
    await db_session.commit()

    loaded = await get_workspace(db_session, row.workspace_id)
    assert loaded is not None
    assert loaded.status == WORKSPACE_STATUS_RUNNING
    assert loaded.name is None
    assert loaded.created_objects == {}
    assert loaded.result_summary is None
    assert loaded.store_id is None
    assert loaded.product_id is None


async def test_showcase_workspace_duplicate_workspace_id_rejected(
    db_session: AsyncSession,
) -> None:
    """The unique index on workspace_id rejects a duplicate insert."""
    workspace_id = uuid.uuid4().hex
    db_session.add(_make_row(workspace_id=workspace_id))
    await db_session.commit()

    db_session.add(_make_row(workspace_id=workspace_id))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_showcase_workspace_status_check_violation(db_session: AsyncSession) -> None:
    """The status CHECK constraint rejects values outside the state set."""
    db_session.add(_make_row(status="archived"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# =============================================================================
# E1 (#407) -- metadata + provenance backbone
# =============================================================================


async def test_showcase_workspace_e1_defaults_applied(db_session: AsyncSession) -> None:
    """A minimal insert gets the E1 defaults.

    E5 (#411) D4 -- an ORM insert now applies the bumped ORM default
    (config_schema_version=2); the server_default stays 1 so pre-E5 rows
    inserted outside the ORM legitimately read 1.
    """
    row = _make_row()
    db_session.add(row)
    await db_session.commit()

    loaded = await get_workspace(db_session, row.workspace_id)
    assert loaded is not None
    assert loaded.archived is False
    assert loaded.pinned is False
    assert loaded.notes is None
    assert loaded.tags == []
    assert loaded.config_schema_version == 2
    assert loaded.replayed_from_workspace_id is None
    # All six story slots stay NULL until their writer epic lands.
    assert loaded.seed_overrides is None
    assert loaded.user_scope is None
    assert loaded.approval_events is None
    assert loaded.rag_events is None
    assert loaded.job_ids is None
    assert loaded.phase_summaries is None


async def test_showcase_workspace_tags_containment_query(db_session: AsyncSession) -> None:
    """tags round-trips as a JSONB string array and answers .contains()."""
    tagged = _make_row(tags=["workspace:x", "demo"])
    untagged = _make_row(tags=["other"])
    db_session.add_all([tagged, untagged])
    await db_session.commit()

    result = await db_session.execute(
        select(ShowcaseWorkspace).where(ShowcaseWorkspace.tags.contains(["demo"]))
    )
    matches = [r.workspace_id for r in result.scalars().all()]
    assert tagged.workspace_id in matches
    assert untagged.workspace_id not in matches

    loaded = await get_workspace(db_session, tagged.workspace_id)
    assert loaded is not None
    assert loaded.tags == ["workspace:x", "demo"]


async def test_showcase_workspace_story_slot_roundtrip(db_session: AsyncSession) -> None:
    """A dict slot and a list[dict] slot round-trip through JSONB intact."""
    seed_overrides = {"noise_sigma": 0.2, "promo_intensity": "high"}
    approval_events = [
        {
            "action_id": "act-1",
            "tool_name": "save_scenario",
            "decision": "approved",
            "decided_at": "2026-06-12T12:00:00+00:00",
            "session_id": "sess-1",
        }
    ]
    row = _make_row(seed_overrides=seed_overrides, approval_events=approval_events)
    db_session.add(row)
    await db_session.commit()

    loaded = await get_workspace(db_session, row.workspace_id)
    assert loaded is not None
    assert loaded.seed_overrides == seed_overrides
    assert loaded.approval_events == approval_events


async def test_showcase_workspace_replayed_from_recorded(db_session: AsyncSession) -> None:
    """replayed_from_workspace_id stores a verbatim soft reference (may dangle)."""
    dangling_source = uuid.uuid4().hex  # no such row -- dangles by design
    row = _make_row(replayed_from_workspace_id=dangling_source)
    db_session.add(row)
    await db_session.commit()

    loaded = await get_workspace(db_session, row.workspace_id)
    assert loaded is not None
    assert loaded.replayed_from_workspace_id == dangling_source


# =============================================================================
# E4 (#410) -- run_config replay-input column
# =============================================================================


async def test_showcase_workspace_run_config_roundtrip(db_session: AsyncSession) -> None:
    """run_config round-trips through JSONB intact."""
    run_config = {
        "train_model_types": ["naive", "regression"],
        "backtest": {
            "horizon": 21,
            "strategy": "expanding",
            "n_splits": 4,
            "min_train_size": 30,
            "gap": 0,
            "metric": "rmse",
        },
    }
    row = _make_row(run_config=run_config)
    db_session.add(row)
    await db_session.commit()

    loaded = await get_workspace(db_session, row.workspace_id)
    assert loaded is not None
    assert loaded.run_config == run_config


async def test_showcase_workspace_run_config_null_default(db_session: AsyncSession) -> None:
    """run_config stays NULL on a default-config insert."""
    row = _make_row()
    db_session.add(row)
    await db_session.commit()

    loaded = await get_workspace(db_session, row.workspace_id)
    assert loaded is not None
    assert loaded.run_config is None
