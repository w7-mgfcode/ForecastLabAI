"""Route tests for Phase 1 GET /seeder/exogenous endpoint."""

from datetime import date
from unittest.mock import patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.features.seeder import schemas
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestExogenousRoute:
    def test_happy_path(self, client):
        mock_response = schemas.ExogenousSignalResponse(
            signal_name="weather_temp_c",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
            store_id=None,
            records=[
                schemas.ExogenousSignalRecord(
                    date=date(2024, 1, 1),
                    signal_name="weather_temp_c",
                    store_id=1,
                    is_global=False,
                    value=12.3,
                ),
                schemas.ExogenousSignalRecord(
                    date=date(2024, 1, 2),
                    signal_name="weather_temp_c",
                    store_id=1,
                    is_global=False,
                    value=13.1,
                ),
            ],
            total=2,
        )

        async def _fake(*args, **kwargs):
            return mock_response

        with patch(
            "app.features.seeder.routes.service.query_exogenous",
            side_effect=_fake,
        ):
            response = client.get(
                "/seeder/exogenous",
                params={
                    "signal_name": "weather_temp_c",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-02",
                },
            )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["signal_name"] == "weather_temp_c"
        assert body["total"] == 2
        assert len(body["records"]) == 2

    def test_rejects_inverted_window(self, client):
        # Service raises ValueError → 400 per the error handler.
        async def _fake(*args, **kwargs):
            raise ValueError("end_date must be on or after start_date")

        with patch(
            "app.features.seeder.routes.service.query_exogenous",
            side_effect=_fake,
        ):
            response = client.get(
                "/seeder/exogenous",
                params={
                    "signal_name": "weather_temp_c",
                    "start_date": "2024-12-31",
                    "end_date": "2024-01-01",
                },
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_requires_signal_name(self, client):
        response = client.get(
            "/seeder/exogenous",
            params={"start_date": "2024-01-01", "end_date": "2024-01-02"},
        )
        # Missing required param → FastAPI validation 422.
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_optional_store_id_passes_through(self, client):
        captured: dict[str, object] = {}

        async def _fake(db, signal_name, start_date, end_date, store_id):
            captured["store_id"] = store_id
            return schemas.ExogenousSignalResponse(
                signal_name=signal_name,
                start_date=start_date,
                end_date=end_date,
                store_id=store_id,
                records=[],
                total=0,
            )

        with patch(
            "app.features.seeder.routes.service.query_exogenous",
            side_effect=_fake,
        ):
            response = client.get(
                "/seeder/exogenous",
                params={
                    "signal_name": "weather_temp_c",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-02",
                    "store_id": 7,
                },
            )
        assert response.status_code == status.HTTP_200_OK
        assert captured["store_id"] == 7
