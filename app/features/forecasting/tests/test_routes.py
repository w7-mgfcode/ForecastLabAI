"""HTTP-level smoke tests for forecasting routes.

These tests POST JSON request bodies containing ISO date strings and assert
the request is NOT rejected with a 422 ``date_type`` error on a date field.
Downstream may return any non-validation status (404 no data, 500 db error,
200 success) -- only the strict-mode JSON-date gotcha is gated here.

Regression for #117 (and the original discovery in PR #115).
See ``docs/_base/SECURITY.md`` -> "Pydantic v2 strict mode on FastAPI
request bodies".
"""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> Any:
    """ASGI test client against the live FastAPI app.

    No DB override -- downstream may fail with 404/500 if the service hits
    the DB; we only care that Pydantic validation passes.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _assert_no_date_type_422(response: Any) -> None:
    """Fail if the response is a 422 with a ``date_type`` error on any field.

    Any other status (200/4xx/5xx) means Pydantic accepted the request body,
    which is the only invariant this test guards.
    """
    if response.status_code != 422:
        return
    body = response.json()
    errors = body.get("errors") or []
    date_type_errors = [err for err in errors if err.get("type") == "date_type"]
    assert not date_type_errors, (
        "strict-mode JSON date regression: request body rejected with "
        f"date_type errors: {date_type_errors}"
    )


@pytest.mark.integration
async def test_train_accepts_iso_string_dates(client: AsyncClient) -> None:
    payload = {
        "store_id": 1,
        "product_id": 2,
        "train_start_date": "2024-01-01",
        "train_end_date": "2024-01-31",
        "config": {"model_type": "naive"},
    }
    response = await client.post("/forecasting/train", json=payload)
    _assert_no_date_type_422(response)


@pytest.mark.integration
async def test_train_lightgbm_rejected_when_disabled(client: AsyncClient) -> None:
    """LightGBM training is refused with 400 while the feature flag is off.

    ``forecast_enable_lightgbm`` defaults to ``False``; the route gate returns a
    400 before any DB or model work (PRP-30 / MLZOO-B).
    """
    payload = {
        "store_id": 1,
        "product_id": 2,
        "train_start_date": "2024-01-01",
        "train_end_date": "2024-01-31",
        "config": {"model_type": "lightgbm"},
    }
    response = await client.post("/forecasting/train", json=payload)
    assert response.status_code == 400
    assert "lightgbm" in response.text.lower()


@pytest.mark.integration
async def test_train_xgboost_rejected_when_disabled(client: AsyncClient) -> None:
    """XGBoost training is refused with 400 while the feature flag is off.

    ``forecast_enable_xgboost`` defaults to ``False``; the route gate returns a
    400 before any DB or model work (PRP-MLZOO-C1).
    """
    payload = {
        "store_id": 1,
        "product_id": 2,
        "train_start_date": "2024-01-01",
        "train_end_date": "2024-01-31",
        "config": {"model_type": "xgboost"},
    }
    response = await client.post("/forecasting/train", json=payload)
    assert response.status_code == 400
    assert "xgboost" in response.text.lower()


@pytest.mark.integration
async def test_predict_accepts_request(client: AsyncClient) -> None:
    # PredictRequest has no date fields; this is a smoke test for completeness
    # so a future contributor who adds a date field is forced to confirm the
    # strict-mode override survives a real HTTP roundtrip.
    payload = {
        "store_id": 1,
        "product_id": 2,
        "horizon": 14,
        "model_path": "/artifacts/models/model_abc123.joblib",
    }
    response = await client.post("/forecasting/predict", json=payload)
    _assert_no_date_type_422(response)
