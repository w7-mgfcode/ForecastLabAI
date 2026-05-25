"""Unit tests for batch schemas (no DB).

Covers the strict-mode JSON path regression (mirrors PR #115 / #119
precedent on ComputeFeaturesRequest / TrainRequest), and the scope
kind/selector consistency rules.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.features.batch.schemas import (
    BatchScope,
    BatchSubmitRequest,
)


def test_submit_request_strict_mode_json_path() -> None:
    """JSON-string dates coerce under Field(strict=False); other JSON-native
    fields stay strict — the regression class from PR #115 / #119."""
    req = BatchSubmitRequest.model_validate(
        {
            "operation": "backtest",
            "scope": {
                "kind": "manual",
                "store_ids": [1, 2],
                "product_ids": [1, 2, 3],
            },
            "model_configs": [{"model_type": "naive", "params": {}}],
            "start_date": "2025-01-01",
            "end_date": "2025-06-30",
        }
    )
    assert req.operation == "backtest"
    assert req.scope.kind == "manual"
    assert req.start_date.isoformat() == "2025-01-01"


def test_submit_request_strict_rejects_str_as_int() -> None:
    """ConfigDict(strict=True) refuses to coerce JSON string into int."""
    with pytest.raises(ValidationError):
        BatchSubmitRequest.model_validate(
            {
                "operation": "backtest",
                "scope": {
                    "kind": "manual",
                    "store_ids": ["1"],  # str → int coercion blocked
                    "product_ids": [1],
                },
                "model_configs": [{"model_type": "naive"}],
                "start_date": "2025-01-01",
                "end_date": "2025-06-30",
            }
        )


def test_scope_top_revenue_requires_top_n() -> None:
    """kind=top_revenue without top_n → ValidationError."""
    with pytest.raises(ValidationError) as excinfo:
        BatchScope.model_validate({"kind": "top_revenue"})
    assert "top_n" in str(excinfo.value)


def test_scope_manual_requires_both_id_lists() -> None:
    """kind=manual without product_ids → ValidationError."""
    with pytest.raises(ValidationError):
        BatchScope.model_validate({"kind": "manual", "store_ids": [1]})
    with pytest.raises(ValidationError):
        BatchScope.model_validate({"kind": "manual", "product_ids": [1]})


def test_scope_region_requires_region() -> None:
    with pytest.raises(ValidationError):
        BatchScope.model_validate({"kind": "region"})


def test_scope_category_requires_category() -> None:
    with pytest.raises(ValidationError):
        BatchScope.model_validate({"kind": "category"})


def test_scope_all_requires_nothing() -> None:
    """kind=all accepts no selectors."""
    scope = BatchScope.model_validate({"kind": "all"})
    assert scope.kind == "all"


def test_model_configs_min_max_length() -> None:
    """model_configs has min_length=1, max_length=10."""
    base = {
        "operation": "backtest",
        "scope": {"kind": "all"},
        "start_date": "2025-01-01",
        "end_date": "2025-06-30",
    }
    # Zero is rejected.
    with pytest.raises(ValidationError):
        BatchSubmitRequest.model_validate({**base, "model_configs": []})
    # 11 is rejected.
    too_many = [{"model_type": "naive"}] * 11
    with pytest.raises(ValidationError):
        BatchSubmitRequest.model_validate({**base, "model_configs": too_many})
    # 10 is accepted.
    ten = [{"model_type": "naive"}] * 10
    req = BatchSubmitRequest.model_validate({**base, "model_configs": ten})
    assert len(req.model_configs) == 10


def test_unknown_operation_rejected() -> None:
    """Unknown operation literal rejected by Literal[...]."""
    with pytest.raises(ValidationError):
        BatchSubmitRequest.model_validate(
            {
                "operation": "explode",
                "scope": {"kind": "all"},
                "model_configs": [{"model_type": "naive"}],
                "start_date": "2025-01-01",
                "end_date": "2025-06-30",
            }
        )


def test_unknown_model_type_rejected() -> None:
    """Unknown model_type rejected by Literal[...]."""
    with pytest.raises(ValidationError):
        BatchSubmitRequest.model_validate(
            {
                "operation": "backtest",
                "scope": {"kind": "all"},
                "model_configs": [{"model_type": "magic_forest"}],
                "start_date": "2025-01-01",
                "end_date": "2025-06-30",
            }
        )
