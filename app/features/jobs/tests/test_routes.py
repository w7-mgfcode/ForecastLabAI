"""Integration tests for jobs API routes.

These tests require PostgreSQL to be running (docker-compose up -d).
Run with: pytest app/features/jobs/tests/ -v -m integration
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.features.jobs.models import Job

pytestmark = pytest.mark.integration


class TestListJobsEndpoint:
    """Tests for GET /jobs endpoint."""

    async def test_list_jobs_ok(self, client: AsyncClient) -> None:
        """GET /jobs returns 200 with the paginated envelope."""
        response = await client.get("/jobs")
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert data["page"] == 1
        assert data["page_size"] == 20

    async def test_list_jobs_returns_seeded_rows(
        self, client: AsyncClient, sample_jobs_multi: list[Job]
    ) -> None:
        """Seeded jobs appear in the listing."""
        response = await client.get("/jobs?page_size=100")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
        listed_ids = {j["job_id"] for j in data["jobs"]}
        assert {job.job_id for job in sample_jobs_multi} <= listed_ids


class TestListJobsSortEndpoint:
    """Tests for sort_by / sort_order on GET /jobs."""

    @staticmethod
    def _test_job_types(payload: dict[str, Any]) -> list[str]:
        """Job types of the test-prefixed jobs, in response order."""
        return [j["job_type"] for j in payload["jobs"] if str(j["job_id"]).startswith("test")]

    async def test_sort_by_job_type_asc(
        self, client: AsyncClient, sample_jobs_multi: list[Job]
    ) -> None:
        """sort_by=job_type&sort_order=asc orders jobs ascending."""
        response = await client.get("/jobs?sort_by=job_type&sort_order=asc&page_size=100")
        assert response.status_code == 200
        assert self._test_job_types(response.json()) == ["backtest", "predict", "train"]

    async def test_sort_by_job_type_desc(
        self, client: AsyncClient, sample_jobs_multi: list[Job]
    ) -> None:
        """sort_by=job_type&sort_order=desc orders jobs descending."""
        response = await client.get("/jobs?sort_by=job_type&sort_order=desc&page_size=100")
        assert response.status_code == 200
        assert self._test_job_types(response.json()) == ["train", "predict", "backtest"]

    async def test_sort_by_status_asc(
        self, client: AsyncClient, sample_jobs_multi: list[Job]
    ) -> None:
        """sort_by=status&sort_order=asc orders jobs by status value."""
        response = await client.get("/jobs?sort_by=status&sort_order=asc&page_size=100")
        assert response.status_code == 200
        # status asc: completed < pending < running -> backtest, train, predict
        assert self._test_job_types(response.json()) == ["backtest", "train", "predict"]

    async def test_sort_by_created_at_desc(
        self, client: AsyncClient, sample_jobs_multi: list[Job]
    ) -> None:
        """sort_by=created_at&sort_order=desc returns newest first."""
        response = await client.get("/jobs?sort_by=created_at&sort_order=desc&page_size=100")
        assert response.status_code == 200
        # created_at 2024-01-03 > 01-02 > 01-01 -> backtest, predict, train
        assert self._test_job_types(response.json()) == ["backtest", "predict", "train"]

    async def test_unknown_sort_by_falls_back_to_default(
        self, client: AsyncClient, sample_jobs_multi: list[Job]
    ) -> None:
        """An unknown sort_by uses the default order, never errors."""
        default = await client.get("/jobs?page_size=100")
        unknown = await client.get("/jobs?sort_by=params&page_size=100")
        assert default.status_code == 200
        assert unknown.status_code == 200
        default_ids = [j["job_id"] for j in default.json()["jobs"]]
        unknown_ids = [j["job_id"] for j in unknown.json()["jobs"]]
        assert unknown_ids == default_ids

    async def test_invalid_sort_order_rejected(self, client: AsyncClient) -> None:
        """sort_order outside {asc,desc} is rejected with 422 via the Query regex."""
        response = await client.get("/jobs?sort_order=sideways")
        assert response.status_code == 422


class TestGetJobEndpoint:
    """Tests for GET /jobs/{job_id} endpoint."""

    async def test_get_job_success(self, client: AsyncClient, sample_jobs_multi: list[Job]) -> None:
        """GET /jobs/{job_id} returns the job."""
        job_id = sample_jobs_multi[0].job_id
        response = await client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["job_id"] == job_id

    async def test_get_job_not_found(self, client: AsyncClient) -> None:
        """GET /jobs/{job_id} returns 404 for an unknown job."""
        response = await client.get(f"/jobs/test{uuid.uuid4().hex[:28]}")
        assert response.status_code == 404
