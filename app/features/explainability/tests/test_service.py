"""Unit tests for ExplainabilityService with a scripted-mock AsyncSession.

The mock session returns pre-built ``Result`` objects in ``execute`` call order
(see ``conftest.make_mock_db``) so the service logic is exercised without a DB.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Literal

import pytest

from app.core.exceptions import BadRequestError
from app.features.explainability.schemas import (
    ConfidenceLevel,
    ExplainForecastRequest,
    ForecastExplanation,
)
from app.features.explainability.service import ExplainabilityService
from app.features.explainability.tests.conftest import (
    forecast_result_db,
    make_mock_db,
    mock_result,
    sales_rows,
)


def _request(
    model_type: Literal["naive", "seasonal_naive", "moving_average"] = "naive",
) -> ExplainForecastRequest:
    """Build an ExplainForecastRequest for the given model type."""
    return ExplainForecastRequest(
        store_id=1, product_id=2, model_type=model_type, as_of_date=date(2024, 3, 1)
    )


class TestExplainForecast:
    """Tests for ExplainabilityService.explain_forecast."""

    async def test_returns_well_formed_explanation(self) -> None:
        """A naive forecast explanation reproduces the last observed value."""
        db = forecast_result_db([10.0, 12.0, 11.0, 9.0, 14.0])
        explanation = await ExplainabilityService().explain_forecast(db, _request())

        assert isinstance(explanation, ForecastExplanation)
        assert explanation.forecast_value == 14.0  # last observation
        assert explanation.method == "rule_based"
        assert explanation.drivers[0].name == "last_observation"
        assert explanation.agent_summary
        # The correlation-vs-causation caveat is always present.
        assert any("causality" in c for c in explanation.caveats)

    async def test_persists_the_explanation(self) -> None:
        """The service adds, flushes, and refreshes a forecast_explanation row."""
        db = forecast_result_db([10.0, 12.0, 11.0])
        await ExplainabilityService().explain_forecast(db, _request())

        db.add.assert_called_once()
        db.flush.assert_awaited_once()
        db.refresh.assert_awaited_once()

    async def test_short_series_flags_insufficient_history(self) -> None:
        """A short series yields LOW confidence and an insufficient_history code."""
        db = forecast_result_db([10.0, 12.0, 11.0])
        explanation = await ExplainabilityService().explain_forecast(db, _request())

        assert explanation.confidence == ConfidenceLevel.LOW
        codes = {rc.code for rc in explanation.reason_codes}
        assert "insufficient_history" in codes

    async def test_empty_series_raises_value_error(self) -> None:
        """An empty series raises ValueError (route maps it to 400)."""
        db = forecast_result_db([])
        with pytest.raises(ValueError, match="empty"):
            await ExplainabilityService().explain_forecast(db, _request())


class TestExplainRun:
    """Tests for ExplainabilityService.explain_run."""

    async def test_missing_run_returns_none(self) -> None:
        """A missing run_id returns None (route maps it to 404)."""
        db = make_mock_db([mock_result(one=None)])
        result = await ExplainabilityService().explain_run(db, "does-not-exist")
        assert result is None

    async def test_explains_a_baseline_run(self) -> None:
        """A baseline run resolves its config and produces an explanation."""
        run = SimpleNamespace(
            run_id="run-abc",
            model_type="naive",
            model_config={"model_type": "naive"},
            store_id=1,
            product_id=2,
            data_window_end=date(2024, 3, 1),
        )
        db = make_mock_db(
            [
                mock_result(one=run),
                mock_result(scalars=sales_rows([10.0, 20.0, 15.0])),
                mock_result(scalars=[]),
                mock_result(scalars=[]),
                mock_result(one=None),
                mock_result(one=None),
            ]
        )
        explanation = await ExplainabilityService().explain_run(db, "run-abc")
        assert explanation is not None
        assert explanation.forecast_value == 15.0

    async def test_lightgbm_run_raises_value_error(self) -> None:
        """A lightgbm run raises ValueError before any series load."""
        run = SimpleNamespace(
            run_id="run-lgbm",
            model_type="lightgbm",
            model_config={"model_type": "lightgbm"},
            store_id=1,
            product_id=2,
            data_window_end=date(2024, 3, 1),
        )
        db = make_mock_db([mock_result(one=run)])
        with pytest.raises(ValueError, match="baseline models only"):
            await ExplainabilityService().explain_run(db, "run-lgbm")


class TestExplainJob:
    """Tests for ExplainabilityService.explain_job."""

    async def test_missing_job_returns_none(self) -> None:
        """A missing job_id returns None (route maps it to 404)."""
        db = make_mock_db([mock_result(one=None)])
        result = await ExplainabilityService().explain_job(db, "does-not-exist")
        assert result is None

    async def test_non_completed_job_raises_bad_request(self) -> None:
        """A pending predict job raises BadRequestError."""
        job = SimpleNamespace(job_id="job-1", job_type="predict", status="pending", result=None)
        db = make_mock_db([mock_result(one=job)])
        with pytest.raises(BadRequestError, match="completed predict job"):
            await ExplainabilityService().explain_job(db, "job-1")

    async def test_non_predict_job_raises_bad_request(self) -> None:
        """A completed train job raises BadRequestError."""
        job = SimpleNamespace(job_id="job-2", job_type="train", status="completed", result={})
        db = make_mock_db([mock_result(one=job)])
        with pytest.raises(BadRequestError, match="completed predict job"):
            await ExplainabilityService().explain_job(db, "job-2")

    async def test_explains_a_completed_predict_job(self) -> None:
        """A completed predict job produces an explanation at the right cutoff."""
        job = SimpleNamespace(
            job_id="job-3",
            job_type="predict",
            status="completed",
            result={
                "store_id": 1,
                "product_id": 2,
                "model_type": "naive",
                "horizon": 7,
                "forecasts": [{"date": "2024-03-02", "forecast": 25.0}],
            },
        )
        db = make_mock_db(
            [
                mock_result(one=job),
                mock_result(scalars=sales_rows([10.0, 20.0, 25.0])),
                mock_result(scalars=[]),
                mock_result(scalars=[]),
                mock_result(one=None),
                mock_result(one=None),
            ]
        )
        explanation = await ExplainabilityService().explain_job(db, "job-3")
        assert explanation is not None
        # as_of_date = day before the first forecast date.
        assert explanation.as_of_date == date(2024, 3, 1)
        assert explanation.forecast_value == 25.0
