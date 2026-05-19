"""Integration tests for the ops Control Center routes.

Runs against a real PostgreSQL database — the full path from HTTP request
through SQL aggregation to response. Requires ``docker-compose up -d``.

Assertions are structural (status-key coverage, sort order, bounds) rather than
exact global totals, so the tests stay idempotent against a shared dataset.
"""

import pytest
from httpx import AsyncClient

from app.features.data_platform.models import SalesDaily
from app.features.jobs.models import Job, JobStatus
from app.features.registry.models import DeploymentAlias, ModelRun, RunStatus

_JOB_STATUSES = {s.value for s in JobStatus}
_RUN_STATUSES = {s.value for s in RunStatus}
_DRIFT_RANK = {"degrading": 0, "improving": 1, "stable": 2, "unknown": 3}


@pytest.mark.integration
@pytest.mark.asyncio
class TestOpsSummary:
    """Integration tests for GET /ops/summary."""

    async def test_summary_happy_path(
        self,
        client: AsyncClient,
        sample_jobs: list[Job],
        sample_runs: dict[str, ModelRun],
        sample_alias: DeploymentAlias,
        sample_sales: list[SalesDaily],
    ) -> None:
        """A seeded database yields a fully populated summary."""
        response = await client.get("/ops/summary")

        assert response.status_code == 200
        data = response.json()

        assert data["system"]["api_ok"] is True
        assert data["system"]["database_connected"] is True

        # Job and run histograms cover every status key (zero-filled).
        assert {c["status"] for c in data["jobs"]["counts"]} == _JOB_STATUSES
        assert {c["status"] for c in data["runs"]["counts"]} == _RUN_STATUSES

        # The seeded failed job surfaces in the attention list. It is the most
        # recently created failed job, so the limit-10 window always includes it.
        failed_job_id = next(j.job_id for j in sample_jobs if j.status == JobStatus.FAILED.value)
        failed_job_ids = {
            item["entity_id"]
            for item in data["attention_items"]
            if item["item_type"] == "failed_job"
        }
        assert failed_job_id in failed_job_ids

        # Freshness reflects the seeded sales.
        assert data["freshness"]["latest_sales_date"] is not None
        assert data["freshness"]["latest_sales_date"] >= "2026-03-03"

        # The alias seeded against the older successful run is reported stale.
        stale_alias = next(a for a in data["aliases"] if a["alias_name"] == sample_alias.alias_name)
        assert stale_alias["is_stale"] is True
        assert stale_alias["stale_reason"] is not None
        assert stale_alias["wape"] == 31.0

    async def test_summary_resilient_structural(self, client: AsyncClient) -> None:
        """Without any seeded fixtures the summary still returns 200, never 500."""
        response = await client.get("/ops/summary")

        assert response.status_code == 200
        data = response.json()

        # Every histogram bucket is non-negative and every status key present.
        for section in ("jobs", "runs"):
            for count in data[section]["counts"]:
                assert count["count"] >= 0
        assert {c["status"] for c in data["jobs"]["counts"]} == _JOB_STATUSES
        assert {c["status"] for c in data["runs"]["counts"]} == _RUN_STATUSES

        assert data["jobs"]["completed_today"] >= 0
        assert data["jobs"]["active_total"] >= 0
        assert data["jobs"]["failed_total"] >= 0
        assert data["runs"]["failed_total"] >= 0
        assert isinstance(data["attention_items"], list)
        assert isinstance(data["aliases"], list)


@pytest.mark.integration
@pytest.mark.asyncio
class TestRetrainingCandidates:
    """Integration tests for GET /ops/retraining-candidates."""

    async def test_candidates_sorted_and_limited(
        self,
        client: AsyncClient,
        sample_runs: dict[str, ModelRun],
    ) -> None:
        """Candidates are sorted by priority_score desc and capped at limit."""
        response = await client.get("/ops/retraining-candidates", params={"limit": 5})

        assert response.status_code == 200
        data = response.json()

        candidates = data["candidates"]
        assert len(candidates) <= 5
        assert data["total_evaluated"] >= len(candidates)

        scores = [c["priority_score"] for c in candidates]
        assert scores == sorted(scores, reverse=True), "candidates must be sorted desc"

        for candidate in candidates:
            assert 0.0 <= candidate["priority_score"] <= 1.0
            assert candidate["staleness_days"] >= 0
            assert candidate["latest_run_status"] == RunStatus.SUCCESS.value

    async def test_candidates_default_limit(self, client: AsyncClient) -> None:
        """The endpoint works with no explicit limit (default 20)."""
        response = await client.get("/ops/retraining-candidates")

        assert response.status_code == 200
        assert len(response.json()["candidates"]) <= 20

    async def test_candidates_limit_zero_rejected(self, client: AsyncClient) -> None:
        """limit=0 is below the ge=1 bound and returns 422."""
        response = await client.get("/ops/retraining-candidates", params={"limit": 0})
        assert response.status_code == 422

    async def test_candidates_limit_too_high_rejected(self, client: AsyncClient) -> None:
        """limit=200 is above the le=100 bound and returns 422."""
        response = await client.get("/ops/retraining-candidates", params={"limit": 200})
        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestModelHealth:
    """Integration tests for GET /ops/model-health."""

    async def test_model_health_happy_path(
        self,
        client: AsyncClient,
        sample_health_runs: list[ModelRun],
    ) -> None:
        """The seeded 3-run degrading grain surfaces with a drift verdict."""
        response = await client.get("/ops/model-health", params={"limit": 100})

        assert response.status_code == 200
        data = response.json()

        entry = next(
            e for e in data["entries"] if e["store_id"] == 9101 and e["product_id"] == 8101
        )
        assert entry["drift_direction"] == "degrading"
        assert entry["run_count"] == 3
        assert entry["latest_wape"] == 25.0
        assert entry["previous_wape"] == 11.0
        assert entry["wape_delta"] == 14.0
        assert len(entry["wape_history"]) == 3
        assert data["total_evaluated"] >= 1

    async def test_model_health_degrading_first_sort(
        self,
        client: AsyncClient,
        sample_health_runs: list[ModelRun],
    ) -> None:
        """Entries are ordered degrading-first (drift rank non-decreasing)."""
        response = await client.get("/ops/model-health", params={"limit": 100})

        assert response.status_code == 200
        ranks = [_DRIFT_RANK[e["drift_direction"]] for e in response.json()["entries"]]
        assert ranks == sorted(ranks), "entries must be sorted degrading-first"

    async def test_model_health_resilient_structural(self, client: AsyncClient) -> None:
        """Without seeded fixtures the endpoint still returns 200, never 500."""
        response = await client.get("/ops/model-health")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["entries"], list)
        assert data["total_evaluated"] >= 0
        for entry in data["entries"]:
            assert entry["drift_direction"] in _DRIFT_RANK
            assert entry["run_count"] >= 0
            assert entry["staleness_days"] >= 0

    async def test_model_health_limit_zero_rejected(self, client: AsyncClient) -> None:
        """limit=0 is below the ge=1 bound and returns 422."""
        response = await client.get("/ops/model-health", params={"limit": 0})
        assert response.status_code == 422

    async def test_model_health_limit_too_high_rejected(self, client: AsyncClient) -> None:
        """limit=200 is above the le=100 bound and returns 422."""
        response = await client.get("/ops/model-health", params={"limit": 200})
        assert response.status_code == 422
