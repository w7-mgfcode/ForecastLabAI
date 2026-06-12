"""Integration tests for the ShowcaseWorkspace ORM model (E1, #390).

Run against the real docker-compose Postgres (``docker compose up -d`` +
``uv run alembic upgrade head`` required). Constraint tests assert the
DB-level guarantees the migration created (unique workspace_id, status CHECK).
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
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
