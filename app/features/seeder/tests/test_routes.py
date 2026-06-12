"""Unit tests for seeder routes."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.features.seeder import schemas
from app.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_settings():
    """Mock settings to allow seeder in tests."""
    with patch("app.features.seeder.routes.get_settings") as mock:
        mock.return_value.seeder_allow_production = True
        mock.return_value.app_env = "testing"
        yield mock


@pytest.fixture
def mock_db():
    """Mock database session."""
    with patch("app.features.seeder.routes.get_db") as mock:
        mock_session = AsyncMock()
        mock.return_value = mock_session
        yield mock_session


class TestGetStatus:
    """Tests for GET /seeder/status endpoint."""

    def test_returns_status(self, client, mock_db):
        """Test status endpoint returns counts."""
        mock_status = schemas.SeederStatus(
            stores=10,
            products=50,
            calendar=365,
            sales=182500,
            inventory=182500,
            price_history=1500,
            promotions=500,
            date_range_start=date(2024, 1, 1),
            date_range_end=date(2024, 12, 31),
        )

        with patch("app.features.seeder.routes.service.get_status", return_value=mock_status):
            response = client.get("/seeder/status")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["stores"] == 10
        assert data["products"] == 50
        assert data["sales"] == 182500


class TestListScenarios:
    """Tests for GET /seeder/scenarios endpoint."""

    def test_returns_scenarios(self, client):
        """Test scenarios endpoint returns list."""
        response = client.get("/seeder/scenarios")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 7

        names = [s["name"] for s in data]
        assert "retail_standard" in names
        assert "holiday_rush" in names
        assert "demo_minimal" in names

    def test_scenario_structure(self, client):
        """Test scenario response structure."""
        response = client.get("/seeder/scenarios")

        data = response.json()
        scenario = data[0]

        assert "name" in scenario
        assert "description" in scenario
        assert "stores" in scenario
        assert "products" in scenario
        assert "start_date" in scenario
        assert "end_date" in scenario


class TestGenerate:
    """Tests for POST /seeder/generate endpoint."""

    def test_generate_with_defaults(self, client, mock_settings, mock_db):
        """Test generate with default parameters."""
        mock_result = schemas.GenerateResult(
            success=True,
            records_created={"stores": 10, "products": 50, "sales": 182500},
            duration_seconds=45.5,
            message="Successfully generated data",
            seed=42,
        )

        with patch("app.features.seeder.routes.service.generate_data", return_value=mock_result):
            response = client.post("/seeder/generate", json={})

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["success"] is True
        assert data["seed"] == 42

    def test_generate_with_scenario(self, client, mock_settings, mock_db):
        """Test generate with specific scenario."""
        mock_result = schemas.GenerateResult(
            success=True,
            records_created={"stores": 10, "sales": 50000},
            duration_seconds=30.0,
            message="Success",
            seed=123,
        )

        with patch("app.features.seeder.routes.service.generate_data", return_value=mock_result):
            response = client.post(
                "/seeder/generate",
                json={
                    "scenario": "holiday_rush",
                    "seed": 123,
                    "stores": 20,
                    "products": 100,
                },
            )

        assert response.status_code == status.HTTP_201_CREATED

    def test_generate_dry_run(self, client, mock_settings, mock_db):
        """Test generate with dry_run flag."""
        mock_result = schemas.GenerateResult(
            success=True,
            records_created={"stores": 10},
            duration_seconds=0.0,
            message="Dry run preview",
            seed=42,
        )

        with patch("app.features.seeder.routes.service.generate_data", return_value=mock_result):
            response = client.post("/seeder/generate", json={"dry_run": True})

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["duration_seconds"] == 0.0

    def test_generate_validation_error(self, client, mock_settings):
        """Test generate with invalid parameters."""
        response = client.post(
            "/seeder/generate",
            json={"stores": 0},  # Invalid - must be >= 1
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_generate_with_overrides(self, client, mock_settings, mock_db):
        """E3 (#409) — the nested overrides object is accepted (201)."""
        mock_result = schemas.GenerateResult(
            success=True,
            records_created={"stores": 8, "products": 20, "sales": 5000},
            duration_seconds=12.0,
            message="Success",
            seed=42,
        )

        with patch(
            "app.features.seeder.routes.service.generate_data", return_value=mock_result
        ) as mock_generate:
            response = client.post(
                "/seeder/generate",
                json={
                    "scenario": "demo_minimal",
                    "overrides": {"stores": 8, "promotion_intensity": 0.3},
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        # The validated params object carries the parsed nested model.
        params = mock_generate.call_args.args[1]
        assert params.overrides is not None
        assert params.overrides.stores == 8
        assert params.overrides.promotion_intensity == 0.3

    def test_generate_overrides_out_of_bounds_rejected(self, client, mock_settings):
        """E3 (#409) — an out-of-bounds knob is a 422."""
        response = client.post(
            "/seeder/generate",
            json={"overrides": {"stores": 0}},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_generate_overrides_unknown_knob_rejected(self, client, mock_settings):
        """E3 (#409) — extra='forbid' rejects knobs outside the allow-list."""
        response = client.post(
            "/seeder/generate",
            json={"overrides": {"bogus_knob": 1}},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_generate_blocked_in_production(self, client, mock_db):
        """Test generate is blocked in production."""
        with patch("app.features.seeder.routes.get_settings") as mock_settings:
            mock_settings.return_value.seeder_allow_production = False
            mock_settings.return_value.app_env = "production"

            response = client.post("/seeder/generate", json={})

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestAppend:
    """Tests for POST /seeder/append endpoint."""

    def test_append_data(self, client, mock_settings, mock_db):
        """Test append endpoint."""
        mock_result = schemas.GenerateResult(
            success=True,
            records_created={"calendar": 90, "sales": 45000},
            duration_seconds=15.0,
            message="Appended data",
            seed=43,
        )

        with patch("app.features.seeder.routes.service.append_data", return_value=mock_result):
            response = client.post(
                "/seeder/append",
                json={
                    "start_date": "2025-01-01",
                    "end_date": "2025-03-31",
                    "seed": 43,
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["success"] is True

    def test_append_requires_dates(self, client, mock_settings):
        """Test append requires start_date and end_date."""
        response = client.post("/seeder/append", json={})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestDelete:
    """Tests for DELETE /seeder/data endpoint."""

    def test_delete_all(self, client, mock_settings, mock_db):
        """Test delete with scope 'all'."""
        mock_result = schemas.DeleteResult(
            success=True,
            records_deleted={"sales_daily": 182500, "store": 10},
            message="Deleted all data",
            dry_run=False,
        )

        with patch("app.features.seeder.routes.service.delete_data", return_value=mock_result):
            response = client.request(
                "DELETE",
                "/seeder/data",
                json={"scope": "all"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True

    def test_delete_facts_only(self, client, mock_settings, mock_db):
        """Test delete with scope 'facts'."""
        mock_result = schemas.DeleteResult(
            success=True,
            records_deleted={"sales_daily": 182500},
            message="Deleted facts",
            dry_run=False,
        )

        with patch("app.features.seeder.routes.service.delete_data", return_value=mock_result):
            response = client.request(
                "DELETE",
                "/seeder/data",
                json={"scope": "facts"},
            )

        assert response.status_code == status.HTTP_200_OK

    def test_delete_dry_run(self, client, mock_settings, mock_db):
        """Test delete with dry_run flag."""
        mock_result = schemas.DeleteResult(
            success=True,
            records_deleted={"sales_daily": 182500},
            message="Dry run: would delete",
            dry_run=True,
        )

        with patch("app.features.seeder.routes.service.delete_data", return_value=mock_result):
            response = client.request(
                "DELETE",
                "/seeder/data",
                json={"scope": "all", "dry_run": True},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["dry_run"] is True


class TestVerify:
    """Tests for POST /seeder/verify endpoint."""

    def test_verify_success(self, client, mock_db):
        """Test verify endpoint with passing checks."""
        mock_result = schemas.VerifyResult(
            passed=True,
            checks=[
                schemas.VerifyCheck(
                    name="FK Integrity",
                    status="passed",
                    message="All FKs valid",
                ),
            ],
            total_checks=1,
            passed_count=1,
            warning_count=0,
            failed_count=0,
        )

        with patch("app.features.seeder.routes.service.verify_data", return_value=mock_result):
            response = client.post("/seeder/verify")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["passed"] is True
        assert data["total_checks"] == 1

    def test_verify_with_failures(self, client, mock_db):
        """Test verify endpoint with failing checks."""
        mock_result = schemas.VerifyResult(
            passed=False,
            checks=[
                schemas.VerifyCheck(
                    name="FK Integrity",
                    status="failed",
                    message="5 orphaned records",
                    details=["Detail 1"],
                ),
            ],
            total_checks=1,
            passed_count=0,
            warning_count=0,
            failed_count=1,
        )

        with patch("app.features.seeder.routes.service.verify_data", return_value=mock_result):
            response = client.post("/seeder/verify")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["passed"] is False
        assert data["failed_count"] == 1


class TestPhase2Enrichment:
    """Tests for POST /seeder/phase2-enrichment endpoint (PRP-38)."""

    def test_happy_path(self, client, mock_settings, mock_db):
        """Service returns counts; route surfaces them with 201."""
        mock_result = schemas.Phase2EnrichmentResponse(
            success=True,
            records_created={
                "product": 15,
                "replenishment_event": 1300,
                "exogenous_signal": 360,
                "sales_returns": 42,
            },
            duration_ms=234.5,
        )
        with patch(
            "app.features.seeder.routes.service.phase2_enrichment",
            return_value=mock_result,
        ):
            response = client.post(
                "/seeder/phase2-enrichment",
                json={"seed": 42, "returns_probability": 0.02},
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["success"] is True
        assert data["records_created"]["product"] == 15
        assert data["records_created"]["replenishment_event"] == 1300

    def test_strict_mode_rejects_string_seed(self, client, mock_settings):
        """ConfigDict(strict=True) — JSON string is not coerced to int."""
        response = client.post(
            "/seeder/phase2-enrichment",
            json={"seed": "42"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_invalid_probability_rejected(self, client, mock_settings):
        """returns_probability > 1.0 is rejected by Field(le=1.0)."""
        response = client.post(
            "/seeder/phase2-enrichment",
            json={"returns_probability": 1.5},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_empty_database_returns_rfc7807(self, client, mock_settings, mock_db):
        """Service raises UnprocessableEntityError on empty dimensions/calendar.

        The global exception handler converts it to RFC 7807
        ``application/problem+json``.
        """
        from app.core.exceptions import UnprocessableEntityError

        with patch(
            "app.features.seeder.routes.service.phase2_enrichment",
            side_effect=UnprocessableEntityError(
                message="Empty dimensions or calendar — Phase 2 enrichment requires a "
                "seeded database. Run /seeder/generate first.",
            ),
        ):
            response = client.post("/seeder/phase2-enrichment", json={})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert "Empty dimensions or calendar" in body["detail"]

    def test_blocked_in_production(self, client, mock_db):
        """Production guard returns 403 (mirrors other seeder endpoints)."""
        with patch("app.features.seeder.routes.get_settings") as mock_settings_local:
            mock_settings_local.return_value.seeder_allow_production = False
            mock_settings_local.return_value.app_env = "production"
            response = client.post("/seeder/phase2-enrichment", json={})

        assert response.status_code == status.HTTP_403_FORBIDDEN
