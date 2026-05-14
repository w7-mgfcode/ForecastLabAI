"""HTTP-level smoke tests for featuresets routes.

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
async def test_compute_features_accepts_iso_string_date(client: AsyncClient) -> None:
    payload = {
        "store_id": 1,
        "product_id": 1,
        "cutoff_date": "2024-01-31",
        "lookback_days": 365,
        "config": {"name": "test"},
    }
    response = await client.post("/featuresets/compute", json=payload)
    _assert_no_date_type_422(response)


@pytest.mark.integration
async def test_preview_features_accepts_iso_string_date(client: AsyncClient) -> None:
    payload = {
        "store_id": 1,
        "product_id": 1,
        "cutoff_date": "2024-01-31",
        "sample_rows": 5,
        "config": {"name": "test"},
    }
    response = await client.post("/featuresets/preview", json=payload)
    _assert_no_date_type_422(response)
