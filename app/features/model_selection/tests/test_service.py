"""Unit tests for ModelSelectionService orchestration (mocked sibling services)."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import TypeAdapter

from app.core.exceptions import BadRequestError, NotFoundError
from app.features.forecasting.schemas import ModelConfig
from app.features.model_selection.schemas import ModelSelectionRunRequest
from app.features.model_selection.service import ModelSelectionService
from app.features.model_selection.tests.conftest import (
    make_availability,
    make_backtest_response,
    make_mock_db,
)


def _request(**overrides: Any) -> ModelSelectionRunRequest:
    payload: dict[str, Any] = {
        "store_id": 1,
        "product_id": 1,
        "selection_window": {"start_date": "2026-01-01", "end_date": "2026-05-31"},
        "forecast_horizon": 14,
        "split_config": {
            "strategy": "expanding",
            "n_splits": 5,
            "min_train_size": 30,
            "gap": 0,
            "horizon": 14,
        },
        "candidate_models": [{"model_type": "naive", "params": {}}],
    }
    payload.update(overrides)
    return ModelSelectionRunRequest.model_validate(payload)


def _patch_backtester(
    monkeypatch: pytest.MonkeyPatch, *, side_effect: list[Any]
) -> SimpleNamespace:
    instance = SimpleNamespace(run_backtest=AsyncMock(side_effect=side_effect))
    monkeypatch.setattr("app.features.backtesting.service.BacktestingService", lambda: instance)
    return instance


def _patch_availability(monkeypatch: pytest.MonkeyPatch, status: str) -> None:
    monkeypatch.setattr(
        ModelSelectionService,
        "get_availability",
        AsyncMock(return_value=make_availability(status=status)),
    )


# -----------------------------------------------------------------------------
# Flattening
# -----------------------------------------------------------------------------


def test_build_model_config_flattens_params() -> None:
    """The service's flatten-then-validate builds a typed ModelConfig."""
    adapter: TypeAdapter[Any] = TypeAdapter(ModelConfig)
    cfg = adapter.validate_python({"model_type": "seasonal_naive", "season_length": 7})
    assert cfg.model_type == "seasonal_naive"
    assert cfg.season_length == 7


# -----------------------------------------------------------------------------
# Availability thresholds
# -----------------------------------------------------------------------------


def _availability_db(observed: int) -> AsyncMock:
    """Mock DB returning a contiguous `observed`-day aggregate for one pair."""
    first = date(2024, 1, 1) if observed else None
    last = date(2024, 1, 1) + timedelta(days=observed - 1) if observed else None
    db = AsyncMock()
    db.get = AsyncMock(return_value=SimpleNamespace(id=1))
    result = AsyncMock()
    result.one = lambda: (first, last, observed, 12.0, 0)
    db.execute = AsyncMock(return_value=result)
    db.scalar = AsyncMock(return_value=0)
    return db


@pytest.mark.parametrize(
    ("observed", "expected"),
    [(120, "ready"), (50, "limited"), (20, "unusable")],
)
async def test_availability_ready_limited_unusable_thresholds(observed: int, expected: str) -> None:
    service = ModelSelectionService()
    db = _availability_db(observed)
    availability = await service.get_availability(db, 1, 1, forecast_horizon=14)
    assert availability.status == expected


async def test_availability_missing_store_raises_not_found() -> None:
    service = ModelSelectionService()
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.get_availability(db, 999, 1, forecast_horizon=14)


# -----------------------------------------------------------------------------
# Orchestration
# -----------------------------------------------------------------------------


async def test_run_selection_partial_success_chooses_valid_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_availability(monkeypatch, "ready")
    _patch_backtester(
        monkeypatch,
        side_effect=[make_backtest_response(wape=10.0), ValueError("insufficient data")],
    )
    request = _request(
        candidate_models=[
            {"model_type": "naive", "params": {}},
            {"model_type": "seasonal_naive", "params": {"season_length": 7}},
        ]
    )
    response = await ModelSelectionService().run_selection(make_mock_db(), request)

    assert response.status == "partial"
    assert response.winner is not None
    assert response.winner.model_type == "naive"
    failed = [e for e in response.ranking if not e.included]
    assert [e.model_type for e in failed] == ["seasonal_naive"]
    assert failed[0].exclusion_reason is not None


async def test_run_selection_all_candidates_fail_returns_failed_status_not_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LOCKED #3 — every candidate failing persists FAILED and returns (no raise)."""
    _patch_availability(monkeypatch, "ready")
    _patch_backtester(monkeypatch, side_effect=[ValueError("boom-1"), ValueError("boom-2")])
    request = _request(
        candidate_models=[
            {"model_type": "naive", "params": {}},
            {"model_type": "seasonal_naive", "params": {"season_length": 7}},
        ]
    )
    response = await ModelSelectionService().run_selection(make_mock_db(), request)

    assert response.status == "failed"
    assert response.winner is None
    assert response.selection_id
    assert all(not e.included for e in response.ranking)


async def test_run_selection_unusable_availability_raises_bad_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LOCKED #2 — unusable availability fails fast with 400."""
    _patch_availability(monkeypatch, "unusable")
    with pytest.raises(BadRequestError):
        await ModelSelectionService().run_selection(make_mock_db(), _request())


async def test_run_selection_auto_train_passes_feature_frame_version_and_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_availability(monkeypatch, "ready")
    _patch_backtester(monkeypatch, side_effect=[make_backtest_response(wape=10.0)])
    train_mock = AsyncMock(
        return_value=SimpleNamespace(model_path="artifacts/models/model_abc.joblib")
    )
    monkeypatch.setattr(
        "app.features.forecasting.service.ForecastingService",
        lambda: SimpleNamespace(train_model=train_mock),
    )
    request = _request(
        feature_frame_version=2,
        feature_groups=["calendar"],
        auto_train_winner=True,
        auto_predict=False,
    )
    response = await ModelSelectionService().run_selection(make_mock_db(), request)

    assert response.final_model == {"model_path": "artifacts/models/model_abc.joblib"}
    train_mock.assert_awaited_once()
    assert train_mock.await_args is not None
    assert train_mock.await_args.kwargs["feature_frame_version"] == 2
    assert train_mock.await_args.kwargs["feature_groups"] == ["calendar"]


async def test_response_uses_recommendation_confidence_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The response carries ``recommendation_confidence`` (not ``confidence``)."""
    _patch_availability(monkeypatch, "ready")
    _patch_backtester(
        monkeypatch,
        side_effect=[make_backtest_response(wape=10.0), make_backtest_response(wape=20.0)],
    )
    request = _request(
        candidate_models=[
            {"model_type": "naive", "params": {}},
            {"model_type": "seasonal_naive", "params": {"season_length": 7}},
        ]
    )
    response = await ModelSelectionService().run_selection(make_mock_db(), request)
    dumped = response.model_dump()
    assert "recommendation_confidence" in dumped
    assert "confidence" not in dumped
    assert response.recommendation_confidence in {"high", "medium", "low"}
    assert response.chart_data is not None


async def test_get_selection_missing_raises_not_found() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await ModelSelectionService().get_selection(db, uuid4().hex)
