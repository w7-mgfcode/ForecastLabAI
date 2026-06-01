"""Unit tests for ModelSelectionService orchestration (mocked sibling services)."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
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
    db.execute = AsyncMock()
    with pytest.raises(NotFoundError):
        await ModelSelectionService().get_selection(db, uuid4().hex)


# -----------------------------------------------------------------------------
# Slice B — async submit / settle / cancel (worker mocked or DB-free units)
# -----------------------------------------------------------------------------

from datetime import UTC, datetime  # noqa: E402

from app.core.exceptions import ConflictError  # noqa: E402
from app.features.model_selection import runner as _runner  # noqa: E402
from app.features.model_selection.models import (  # noqa: E402
    ModelSelectionCandidate,
    ModelSelectionRun,
    ModelSelectionStatus,
)


def _submit_mock_db() -> AsyncMock:
    """Mock ``AsyncSession`` whose ``refresh`` stamps ``created_at`` on the run."""
    db = AsyncMock()
    added: list[Any] = []

    def _add(obj: Any) -> None:
        added.append(obj)

    async def _refresh(obj: Any) -> None:
        if isinstance(obj, ModelSelectionRun) and obj.created_at is None:
            obj.created_at = datetime.now(UTC)

    db.add = MagicMock(side_effect=_add)
    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=_refresh)
    db._added = added  # expose for assertions
    return db


async def test_submit_run_inserts_running_parent_and_pending_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_availability(monkeypatch, "ready")
    # Stub the detached worker so create_task schedules a harmless no-op.
    monkeypatch.setattr(ModelSelectionService, "_run_in_background", AsyncMock())

    request = _request(
        candidate_models=[
            {"model_type": "naive", "params": {}},
            {"model_type": "seasonal_naive", "params": {"season_length": 7}},
        ]
    )
    db = _submit_mock_db()
    response = await ModelSelectionService().submit_run(db, request)

    assert response.status == "running"
    assert response.monitor_url == f"/model-selection/{response.selection_id}"
    assert response.cancel_url == f"/model-selection/{response.selection_id}"
    assert response.progress is not None
    assert response.progress.total == 2
    assert response.progress.pending == 2
    assert len(response.candidate_progress) == 2
    assert {c.status for c in response.candidate_progress} == {"pending"}

    parents = [o for o in db._added if isinstance(o, ModelSelectionRun)]
    children = [o for o in db._added if isinstance(o, ModelSelectionCandidate)]
    assert len(parents) == 1
    assert parents[0].status == ModelSelectionStatus.RUNNING.value
    assert parents[0].started_at is not None
    assert parents[0].total_candidates == 2
    assert len(children) == 2
    assert {c.status for c in children} == {"pending"}
    assert [c.ordinal for c in children] == [0, 1]


async def test_submit_run_unusable_availability_raises_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_availability(monkeypatch, "unusable")
    monkeypatch.setattr(ModelSelectionService, "_run_in_background", AsyncMock())
    db = _submit_mock_db()
    with pytest.raises(BadRequestError):
        await ModelSelectionService().submit_run(db, _request())
    # The parent was persisted as failed; no children were inserted.
    parents = [o for o in db._added if isinstance(o, ModelSelectionRun)]
    children = [o for o in db._added if isinstance(o, ModelSelectionCandidate)]
    assert parents[0].status == ModelSelectionStatus.FAILED.value
    assert children == []


def test_terminal_status_rule() -> None:
    svc = ModelSelectionService()
    f = svc._terminal_status
    assert f({"completed": 3, "failed": 0, "cancelled": 0}) is ModelSelectionStatus.COMPLETED
    assert f({"completed": 0, "failed": 3, "cancelled": 0}) is ModelSelectionStatus.FAILED
    assert f({"completed": 0, "failed": 0, "cancelled": 3}) is ModelSelectionStatus.CANCELLED
    assert f({"completed": 2, "failed": 1, "cancelled": 0}) is ModelSelectionStatus.PARTIAL
    assert f({"completed": 1, "failed": 0, "cancelled": 1}) is ModelSelectionStatus.PARTIAL


async def test_cancel_run_404_when_missing() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await ModelSelectionService().cancel_run(db, uuid4().hex)


async def test_cancel_run_409_when_terminal() -> None:
    row = ModelSelectionRun(
        selection_id="sel_terminal",
        status=ModelSelectionStatus.COMPLETED.value,
        store_id=1,
        product_id=1,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 5, 31),
        forecast_horizon=14,
        ranking_metric="wape",
        candidate_models=[],
        policy_snapshot={},
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=row)
    with pytest.raises(ConflictError):
        await ModelSelectionService().cancel_run(db, "sel_terminal")


async def test_cancel_run_409_when_settle_races_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the worker settled (no handle) between load and cancel → 409."""
    row = ModelSelectionRun(
        selection_id="sel_race",
        status=ModelSelectionStatus.RUNNING.value,
        store_id=1,
        product_id=1,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 5, 31),
        forecast_horizon=14,
        ranking_metric="wape",
        candidate_models=[],
        policy_snapshot={},
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=row)
    monkeypatch.setattr(_runner, "cancel_selection", lambda _sid: False)
    with pytest.raises(ConflictError):
        await ModelSelectionService().cancel_run(db, "sel_race")


# =============================================================================
# Slice C — train-selected (override) / predict-decision / promote
# =============================================================================

from app.core.exceptions import UnprocessableEntityError  # noqa: E402
from app.features.forecasting.schemas import ForecastPoint  # noqa: E402
from app.features.model_selection.schemas import PromoteRequest  # noqa: E402


def _ranking_dict(
    *,
    winner_type: str = "naive",
    extra_included: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A persisted ``ranking_result`` JSONB with a winner + ranked entries."""
    winner_metrics = {"wape": 10.0, "smape": 8.0, "mae": 4.0, "bias": 0.5}
    entries: list[dict[str, Any]] = [
        {
            "rank": 1,
            "model_type": winner_type,
            "params": {},
            "included": True,
            "exclusion_reason": None,
            "metrics": winner_metrics,
        }
    ]
    if extra_included:
        entries.extend(extra_included)
    return {
        "winner": {
            "rank": 1,
            "model_type": winner_type,
            "params": {},
            "included": True,
            "exclusion_reason": None,
            "metrics": winner_metrics,
        },
        "entries": entries,
        "confidence": "high",
        "reasons": [],
    }


def _decision_row(
    *,
    candidate_models: list[dict[str, Any]] | None = None,
    ranking_result: dict[str, Any] | None = None,
    feature_frame_version: int = 1,
    final_model_path: str | None = None,
    trained_model_type: str | None = None,
    is_override: bool = False,
    winner_metrics: dict[str, Any] | None = None,
) -> ModelSelectionRun:
    """Build an in-memory ModelSelectionRun for decision-layer unit tests."""
    return ModelSelectionRun(
        selection_id="sel_decision",
        status=ModelSelectionStatus.COMPLETED.value,
        store_id=3,
        product_id=8,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 5, 31),
        forecast_horizon=14,
        ranking_metric="wape",
        candidate_models=candidate_models or [{"model_type": "naive", "params": {}}],
        policy_snapshot={},
        ranking_result=ranking_result,
        feature_frame_version=feature_frame_version,
        final_model_path=final_model_path,
        trained_model_type=trained_model_type,
        is_override=is_override,
        winner_metrics=winner_metrics,
    )


def _row_db(row: ModelSelectionRun) -> AsyncMock:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=row)
    db.flush = AsyncMock()
    return db


def _patch_train(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    train_mock = AsyncMock(
        return_value=SimpleNamespace(model_path="artifacts/models/model_sel.joblib")
    )
    monkeypatch.setattr(
        "app.features.forecasting.service.ForecastingService",
        lambda: SimpleNamespace(train_model=train_mock),
    )
    return train_mock


async def test_train_selected_trains_chosen_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    train_mock = _patch_train(monkeypatch)
    row = _decision_row(
        candidate_models=[
            {"model_type": "naive", "params": {}},
            {"model_type": "seasonal_naive", "params": {"season_length": 7}},
        ],
        ranking_result=_ranking_dict(winner_type="naive"),
    )
    resp = await ModelSelectionService().train_selected(_row_db(row), "sel_decision", "naive", None)
    assert resp.model_type == "naive"
    assert resp.is_override is False
    assert resp.override_warning is None
    assert row.trained_model_type == "naive"
    assert row.is_override is False
    train_mock.assert_awaited_once()


async def test_train_selected_rejects_non_candidate_model_type_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    train_mock = _patch_train(monkeypatch)
    row = _decision_row(
        candidate_models=[{"model_type": "naive", "params": {}}],
        ranking_result=_ranking_dict(winner_type="naive"),
    )
    with pytest.raises(BadRequestError):
        await ModelSelectionService().train_selected(_row_db(row), "sel_decision", "lightgbm", None)
    train_mock.assert_not_awaited()


async def test_train_selected_sets_is_override_and_warning_for_non_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_train(monkeypatch)
    row = _decision_row(
        candidate_models=[
            {"model_type": "naive", "params": {}},
            {"model_type": "seasonal_naive", "params": {"season_length": 7}},
        ],
        ranking_result=_ranking_dict(
            winner_type="naive",
            extra_included=[
                {
                    "rank": 2,
                    "model_type": "seasonal_naive",
                    "params": {"season_length": 7},
                    "included": True,
                    "exclusion_reason": None,
                    "metrics": {"wape": 15.0, "smape": 9.0, "mae": 5.0, "bias": 0.2},
                }
            ],
        ),
    )
    resp = await ModelSelectionService().train_selected(
        _row_db(row), "sel_decision", "seasonal_naive", "domain seasonality"
    )
    assert resp.is_override is True
    assert resp.override_warning is not None
    assert "seasonal_naive" in resp.override_warning
    assert "naive" in resp.override_warning
    assert row.override_reason == "domain seasonality"


async def test_train_selected_failed_candidate_still_trainable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A candidate that FAILED its backtest (no ranked metrics) stays trainable."""
    _patch_train(monkeypatch)
    row = _decision_row(
        candidate_models=[
            {"model_type": "naive", "params": {}},
            {"model_type": "moving_average", "params": {}},
        ],
        # moving_average failed its backtest → not in ranking entries.
        ranking_result=_ranking_dict(winner_type="naive"),
    )
    resp = await ModelSelectionService().train_selected(
        _row_db(row), "sel_decision", "moving_average", None
    )
    assert resp.is_override is True
    assert resp.override_warning is not None
    assert "not successfully evaluated" in resp.override_warning


async def test_train_selected_threads_feature_frame_version_into_train_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    train_mock = _patch_train(monkeypatch)
    row = _decision_row(
        candidate_models=[{"model_type": "prophet_like", "params": {}}],
        ranking_result=_ranking_dict(winner_type="prophet_like"),
        feature_frame_version=2,
    )
    await ModelSelectionService().train_selected(_row_db(row), "sel_decision", "prophet_like", None)
    assert train_mock.await_args is not None
    assert train_mock.await_args.kwargs["feature_frame_version"] == 2


async def test_train_winner_now_persists_trained_model_type_not_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression — train-winner persists trained_model_type, is_override=False."""
    train_mock = _patch_train(monkeypatch)
    row = _decision_row(
        candidate_models=[{"model_type": "naive", "params": {}}],
        ranking_result=_ranking_dict(winner_type="naive"),
        feature_frame_version=2,
    )
    resp = await ModelSelectionService().train_winner(_row_db(row), "sel_decision")
    assert resp.model_type == "naive"
    assert resp.is_override is False
    assert resp.override_warning is None
    assert row.trained_model_type == "naive"
    assert row.is_override is False
    assert train_mock.await_args is not None
    assert train_mock.await_args.kwargs["feature_frame_version"] == 2


def _predict_points() -> list[ForecastPoint]:
    base = date(2026, 6, 1)
    values = [10.0, 25.0, 8.0, 12.0]
    return [
        ForecastPoint(date=base.fromordinal(base.toordinal() + i), forecast=v)
        for i, v in enumerate(values)
    ]


async def test_predict_attaches_decision_and_peak_low(monkeypatch: pytest.MonkeyPatch) -> None:
    predict_mock = AsyncMock(return_value=SimpleNamespace(forecasts=_predict_points()))
    monkeypatch.setattr(
        "app.features.forecasting.service.ForecastingService",
        lambda: SimpleNamespace(predict=predict_mock),
    )
    row = _decision_row(
        final_model_path="artifacts/models/model_sel.joblib",
        trained_model_type="naive",
        winner_metrics={"wape": 10.0, "bias": 0.5},
    )
    forecast, decision = await ModelSelectionService().predict_winner(
        _row_db(row), "sel_decision", 7, 0.95
    )
    assert decision is not None
    assert decision.lead_time_days == 7
    assert decision.method == "heuristic"
    assert forecast.peak_demand == 25.0
    assert forecast.low_demand == 8.0
    assert forecast.peak_date == date(2026, 6, 2)


async def test_predict_winner_untrained_raises_400() -> None:
    row = _decision_row(final_model_path=None)
    with pytest.raises(BadRequestError):
        await ModelSelectionService().predict_winner(_row_db(row), "sel_decision", 7, 0.95)


def _patch_registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    from app.features.registry.schemas import RunStatus

    run_resp = SimpleNamespace(run_id="run_abc123def456")
    alias_resp = SimpleNamespace(alias_name="champion-test", run_status=RunStatus.SUCCESS)
    create_run = AsyncMock(return_value=run_resp)
    update_run = AsyncMock(return_value=run_resp)
    create_alias = AsyncMock(return_value=alias_resp)
    monkeypatch.setattr(
        "app.features.registry.service.RegistryService",
        lambda: SimpleNamespace(
            create_run=create_run, update_run=update_run, create_alias=create_alias
        ),
    )
    monkeypatch.setattr(
        ModelSelectionService,
        "_register_artifact",
        staticmethod(lambda final_model_path, run_id: ("champion-selector/x.joblib", "h", 100)),
    )
    return {"create_run": create_run, "update_run": update_run, "create_alias": create_alias}


async def test_promote_orchestrates_create_run_success_and_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_registry(monkeypatch)
    row = _decision_row(
        final_model_path="artifacts/models/model_sel.joblib",
        trained_model_type="naive",
        is_override=False,
        winner_metrics={"wape": 10.0},
        feature_frame_version=1,
    )
    req = PromoteRequest(alias_name="champion-test", approved_by="gabor")
    resp = await ModelSelectionService().promote(_row_db(row), "sel_decision", req)
    assert resp.run_id == "run_abc123def456"
    assert resp.run_status == "success"
    assert resp.alias_name == "champion-test"
    mocks["create_run"].assert_awaited_once()
    mocks["create_alias"].assert_awaited_once()
    # two update_run calls: RUNNING then SUCCESS
    assert mocks["update_run"].await_count == 2


async def test_promote_persists_promotion_decision_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_registry(monkeypatch)
    row = _decision_row(
        final_model_path="artifacts/models/model_sel.joblib",
        trained_model_type="naive",
        winner_metrics={"wape": 10.0},
    )
    req = PromoteRequest(alias_name="champion-test", approved_by="gabor", description="Q3")
    await ModelSelectionService().promote(_row_db(row), "sel_decision", req)
    assert row.champion_run_id == "run_abc123def456"
    assert row.promoted_alias == "champion-test"
    assert row.promotion_decision is not None
    assert row.promotion_decision["approved_by"] == "gabor"
    assert row.promotion_decision["decision"] == "promoted"
    assert row.promotion_decision["reason"] == "Q3"


async def test_promote_carries_real_feature_frame_version_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_registry(monkeypatch)
    row = _decision_row(
        final_model_path="artifacts/models/model_sel.joblib",
        trained_model_type="prophet_like",
        winner_metrics={"wape": 10.0},
        feature_frame_version=2,
    )
    req = PromoteRequest(alias_name="champion-v2", approved_by="gabor")
    await ModelSelectionService().promote(_row_db(row), "sel_decision", req)
    assert mocks["create_run"].await_args is not None
    run_create = mocks["create_run"].await_args.args[1]
    assert run_create.runtime_info_extras["feature_frame_version"] == 2


async def test_promote_defaults_feature_frame_version_1_for_legacy_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_registry(monkeypatch)
    row = _decision_row(
        final_model_path="artifacts/models/model_sel.joblib",
        trained_model_type="naive",
        winner_metrics={"wape": 10.0},
        feature_frame_version=1,  # legacy / server_default
    )
    req = PromoteRequest(alias_name="champion-legacy", approved_by="gabor")
    await ModelSelectionService().promote(_row_db(row), "sel_decision", req)
    assert mocks["create_run"].await_args is not None
    run_create = mocks["create_run"].await_args.args[1]
    assert run_create.runtime_info_extras["feature_frame_version"] == 1


async def test_promote_requires_trained_model_422(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_registry(monkeypatch)
    row = _decision_row(final_model_path=None, trained_model_type=None)
    req = PromoteRequest(alias_name="champion-test", approved_by="gabor")
    with pytest.raises(UnprocessableEntityError):
        await ModelSelectionService().promote(_row_db(row), "sel_decision", req)


async def test_promote_non_recommended_requires_ack_422(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_registry(monkeypatch)
    row = _decision_row(
        final_model_path="artifacts/models/model_sel.joblib",
        trained_model_type="seasonal_naive",
        is_override=True,
        winner_metrics={"wape": 10.0},
    )
    req = PromoteRequest(
        alias_name="champion-test", approved_by="gabor", acknowledge_non_recommended=False
    )
    with pytest.raises(UnprocessableEntityError):
        await ModelSelectionService().promote(_row_db(row), "sel_decision", req)


def _capturing_run_db() -> AsyncMock:
    db = AsyncMock()
    rows: list[Any] = []
    db.add = MagicMock(side_effect=lambda o: rows.append(o))

    async def _flush() -> None:
        for obj in rows:
            if isinstance(obj, ModelSelectionRun) and obj.created_at is None:
                obj.created_at = datetime.now(UTC)

    db.flush = AsyncMock(side_effect=_flush)
    db.refresh = AsyncMock()
    db._rows = rows
    return db


async def test_run_creation_persists_request_feature_frame_version_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_availability(monkeypatch, "ready")
    _patch_backtester(monkeypatch, side_effect=[make_backtest_response(wape=10.0)])
    db = _capturing_run_db()
    await ModelSelectionService().run_selection(db, _request(feature_frame_version=2))
    runs = [r for r in db._rows if isinstance(r, ModelSelectionRun)]
    assert runs[0].feature_frame_version == 2


async def test_run_creation_persists_request_feature_frame_version_async(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_availability(monkeypatch, "ready")
    monkeypatch.setattr(ModelSelectionService, "_run_in_background", AsyncMock())
    db = _submit_mock_db()
    await ModelSelectionService().submit_run(db, _request(feature_frame_version=2))
    runs = [o for o in db._added if isinstance(o, ModelSelectionRun)]
    assert runs[0].feature_frame_version == 2
