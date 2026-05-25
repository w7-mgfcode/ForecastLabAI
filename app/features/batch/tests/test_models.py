"""Unit tests for batch models (no DB)."""

from __future__ import annotations

from app.features.batch.models import (
    VALID_BATCH_ITEM_TRANSITIONS,
    VALID_BATCH_TRANSITIONS,
    BatchItemStatus,
    BatchOperation,
    BatchStatus,
)


def test_batch_status_enum_round_trip() -> None:
    """Every BatchStatus value round-trips via its string."""
    for status in BatchStatus:
        assert BatchStatus(status.value) is status


def test_batch_operation_enum_round_trip() -> None:
    """Every BatchOperation value round-trips via its string."""
    for op in BatchOperation:
        assert BatchOperation(op.value) is op


def test_batch_item_status_enum_round_trip() -> None:
    """Every BatchItemStatus value round-trips via its string."""
    for status in BatchItemStatus:
        assert BatchItemStatus(status.value) is status


def test_valid_transitions_dict_parent() -> None:
    """Parent transition map: terminal states have no out-edges."""
    assert VALID_BATCH_TRANSITIONS[BatchStatus.PENDING] == {
        BatchStatus.RUNNING,
        BatchStatus.CANCELLED,
    }
    for terminal in (
        BatchStatus.COMPLETED,
        BatchStatus.FAILED,
        BatchStatus.PARTIAL,
        BatchStatus.CANCELLED,
    ):
        assert VALID_BATCH_TRANSITIONS[terminal] == set()


def test_valid_transitions_dict_item() -> None:
    """Item transition map: PENDING -> RUNNING or CANCELLED only."""
    assert VALID_BATCH_ITEM_TRANSITIONS[BatchItemStatus.PENDING] == {
        BatchItemStatus.RUNNING,
        BatchItemStatus.CANCELLED,
    }
    assert VALID_BATCH_ITEM_TRANSITIONS[BatchItemStatus.RUNNING] == {
        BatchItemStatus.COMPLETED,
        BatchItemStatus.FAILED,
    }
    for terminal in (
        BatchItemStatus.COMPLETED,
        BatchItemStatus.FAILED,
        BatchItemStatus.CANCELLED,
    ):
        assert VALID_BATCH_ITEM_TRANSITIONS[terminal] == set()


def test_check_constraints_named_predictably() -> None:
    """CHECK constraints carry stable names (downstream tests assert on them)."""
    from sqlalchemy import Table

    from app.features.batch.models import BatchJob, BatchJobItem

    parent_table: Table = BatchJob.__table__  # type: ignore[assignment]
    child_table: Table = BatchJobItem.__table__  # type: ignore[assignment]

    parent_names = {c.name for c in parent_table.constraints if c.name is not None}
    assert "ck_batch_job_valid_status" in parent_names
    assert "ck_batch_job_valid_operation" in parent_names
    assert "ck_batch_job_priority_band" in parent_names

    child_names = {c.name for c in child_table.constraints if c.name is not None}
    assert "ck_batch_job_item_valid_status" in child_names
    assert "ck_batch_job_item_priority_band" in child_names
