"""Integration tests for registry API routes.

These tests require PostgreSQL to be running (docker-compose up -d).
Run with: pytest app/features/registry/tests/ -v -m integration
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


class TestCreateRunEndpoint:
    """Tests for POST /registry/runs endpoint."""

    async def test_create_run_success(self, client: AsyncClient) -> None:
        """Should create a new run with valid data."""
        response = await client.post(
            "/registry/runs",
            json={
                "model_type": "test-naive",
                "model_config": {"strategy": "last_value"},
                "data_window_start": "2024-01-01",
                "data_window_end": "2024-03-31",
                "store_id": 1,
                "product_id": 1,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["model_type"] == "test-naive"
        assert data["status"] == "pending"
        assert data["run_id"] is not None
        assert len(data["run_id"]) == 32
        assert data["config_hash"] is not None
        assert len(data["config_hash"]) == 16

    async def test_create_run_with_all_fields(self, client: AsyncClient) -> None:
        """Should create a run with all optional fields."""
        response = await client.post(
            "/registry/runs",
            json={
                "model_type": "test-seasonal",
                "model_config": {"season_length": 7},
                "feature_config": {"lags": [1, 7, 14]},
                "data_window_start": "2024-01-01",
                "data_window_end": "2024-06-30",
                "store_id": 5,
                "product_id": 10,
                "agent_context": {
                    "agent_id": "test-agent",
                    "session_id": "test-session",
                },
                "git_sha": "abc123def456",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["feature_config"] == {"lags": [1, 7, 14]}
        assert data["agent_context"]["agent_id"] == "test-agent"
        assert data["git_sha"] == "abc123def456"
        assert data["runtime_info"]["python_version"].startswith("3.")

    async def test_create_run_validation_error(self, client: AsyncClient) -> None:
        """Should return 422 for invalid data."""
        response = await client.post(
            "/registry/runs",
            json={
                "model_type": "",  # Too short
                "model_config": {},
                "data_window_start": "2024-01-01",
                "data_window_end": "2024-01-31",
                "store_id": 1,
                "product_id": 1,
            },
        )
        assert response.status_code == 422

    async def test_create_run_invalid_date_order(self, client: AsyncClient) -> None:
        """Should return 422 if end date before start date."""
        response = await client.post(
            "/registry/runs",
            json={
                "model_type": "test-naive",
                "model_config": {},
                "data_window_start": "2024-03-01",
                "data_window_end": "2024-01-01",
                "store_id": 1,
                "product_id": 1,
            },
        )
        assert response.status_code == 422


class TestListRunsEndpoint:
    """Tests for GET /registry/runs endpoint."""

    async def test_list_runs_empty(self, client: AsyncClient) -> None:
        """Should return empty list when no runs exist."""
        response = await client.get("/registry/runs")
        assert response.status_code == 200
        data = response.json()
        assert data["runs"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    async def test_list_runs_with_data(self, client: AsyncClient) -> None:
        """Should return paginated list of runs."""
        # Create some runs
        for i in range(3):
            await client.post(
                "/registry/runs",
                json={
                    "model_type": f"test-list-{i}",
                    "model_config": {"index": i},
                    "data_window_start": "2024-01-01",
                    "data_window_end": "2024-01-31",
                    "store_id": 1,
                    "product_id": 1,
                },
            )

        response = await client.get("/registry/runs")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
        assert data["page"] == 1
        assert data["page_size"] == 20

    async def test_list_runs_filter_by_model_type(self, client: AsyncClient) -> None:
        """Should filter runs by model_type."""
        # Create runs with different types
        await client.post(
            "/registry/runs",
            json={
                "model_type": "test-filter-a",
                "model_config": {},
                "data_window_start": "2024-01-01",
                "data_window_end": "2024-01-31",
                "store_id": 1,
                "product_id": 1,
            },
        )
        await client.post(
            "/registry/runs",
            json={
                "model_type": "test-filter-b",
                "model_config": {},
                "data_window_start": "2024-01-01",
                "data_window_end": "2024-01-31",
                "store_id": 1,
                "product_id": 1,
            },
        )

        response = await client.get("/registry/runs?model_type=test-filter-a")
        assert response.status_code == 200
        data = response.json()
        for run in data["runs"]:
            assert run["model_type"] == "test-filter-a"

    async def test_list_runs_filter_by_status(self, client: AsyncClient) -> None:
        """Should filter runs by status."""
        response = await client.get("/registry/runs?status=pending")
        assert response.status_code == 200
        data = response.json()
        for run in data["runs"]:
            assert run["status"] == "pending"

    async def test_list_runs_pagination(self, client: AsyncClient) -> None:
        """Should paginate results correctly."""
        # Create runs
        for i in range(5):
            await client.post(
                "/registry/runs",
                json={
                    "model_type": f"test-page-{i}",
                    "model_config": {},
                    "data_window_start": "2024-01-01",
                    "data_window_end": "2024-01-31",
                    "store_id": 1,
                    "product_id": 1,
                },
            )

        response = await client.get("/registry/runs?page=1&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["runs"]) <= 2
        assert data["page"] == 1
        assert data["page_size"] == 2


class TestGetRunEndpoint:
    """Tests for GET /registry/runs/{run_id} endpoint."""

    async def test_get_run_success(self, client: AsyncClient) -> None:
        """Should return run details."""
        # Create a run
        create_response = await client.post(
            "/registry/runs",
            json={
                "model_type": "test-get",
                "model_config": {"test": True},
                "data_window_start": "2024-01-01",
                "data_window_end": "2024-01-31",
                "store_id": 1,
                "product_id": 1,
            },
        )
        run_id = create_response.json()["run_id"]

        # Get the run
        response = await client.get(f"/registry/runs/{run_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert data["model_type"] == "test-get"

    async def test_get_run_not_found(self, client: AsyncClient) -> None:
        """Should return 404 for non-existent run."""
        response = await client.get("/registry/runs/nonexistent12345678901234567890")
        assert response.status_code == 404


class TestUpdateRunEndpoint:
    """Tests for PATCH /registry/runs/{run_id} endpoint."""

    async def test_update_run_status(self, client: AsyncClient) -> None:
        """Should update run status."""
        # Create a run
        create_response = await client.post(
            "/registry/runs",
            json={
                "model_type": "test-update",
                "model_config": {},
                "data_window_start": "2024-01-01",
                "data_window_end": "2024-01-31",
                "store_id": 1,
                "product_id": 1,
            },
        )
        run_id = create_response.json()["run_id"]

        # Update to running
        response = await client.patch(
            f"/registry/runs/{run_id}",
            json={"status": "running"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["started_at"] is not None

    async def test_update_run_metrics(self, client: AsyncClient) -> None:
        """Should update run metrics."""
        # Create and start a run
        create_response = await client.post(
            "/registry/runs",
            json={
                "model_type": "test-metrics",
                "model_config": {},
                "data_window_start": "2024-01-01",
                "data_window_end": "2024-01-31",
                "store_id": 1,
                "product_id": 1,
            },
        )
        run_id = create_response.json()["run_id"]

        # Transition to running first
        await client.patch(f"/registry/runs/{run_id}", json={"status": "running"})

        # Update to success with metrics
        response = await client.patch(
            f"/registry/runs/{run_id}",
            json={
                "status": "success",
                "metrics": {"mae": 1.5, "smape": 10.2, "wape": 0.08},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["metrics"]["mae"] == 1.5
        assert data["completed_at"] is not None

    async def test_update_run_invalid_transition(self, client: AsyncClient) -> None:
        """Should return 400 for invalid status transition."""
        # Create a run
        create_response = await client.post(
            "/registry/runs",
            json={
                "model_type": "test-invalid",
                "model_config": {},
                "data_window_start": "2024-01-01",
                "data_window_end": "2024-01-31",
                "store_id": 1,
                "product_id": 1,
            },
        )
        run_id = create_response.json()["run_id"]

        # Try to go directly from pending to success
        response = await client.patch(
            f"/registry/runs/{run_id}",
            json={"status": "success"},
        )
        assert response.status_code == 400
        assert "transition" in response.json()["detail"].lower()

    async def test_update_run_not_found(self, client: AsyncClient) -> None:
        """Should return 404 for non-existent run."""
        response = await client.patch(
            "/registry/runs/nonexistent12345678901234567890",
            json={"status": "running"},
        )
        assert response.status_code == 404


class TestAliasEndpoints:
    """Tests for alias CRUD endpoints."""

    async def test_create_alias_success(self, client: AsyncClient) -> None:
        """Should create an alias for a successful run."""
        # Create a run and transition to success
        create_response = await client.post(
            "/registry/runs",
            json={
                "model_type": "test-alias",
                "model_config": {},
                "data_window_start": "2024-01-01",
                "data_window_end": "2024-01-31",
                "store_id": 1,
                "product_id": 1,
            },
        )
        run_id = create_response.json()["run_id"]

        await client.patch(f"/registry/runs/{run_id}", json={"status": "running"})
        await client.patch(f"/registry/runs/{run_id}", json={"status": "success"})

        # Create alias
        response = await client.post(
            "/registry/aliases",
            json={
                "alias_name": "production",
                "run_id": run_id,
                "description": "Production model",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["alias_name"] == "production"
        assert data["run_id"] == run_id
        assert data["run_status"] == "success"

    async def test_create_alias_non_success_run(self, client: AsyncClient) -> None:
        """Should return 400 when aliasing non-success run."""
        # Create a pending run
        create_response = await client.post(
            "/registry/runs",
            json={
                "model_type": "test-alias-fail",
                "model_config": {},
                "data_window_start": "2024-01-01",
                "data_window_end": "2024-01-31",
                "store_id": 1,
                "product_id": 1,
            },
        )
        run_id = create_response.json()["run_id"]

        # Try to create alias for pending run
        response = await client.post(
            "/registry/aliases",
            json={
                "alias_name": "staging",
                "run_id": run_id,
            },
        )
        assert response.status_code == 400

    async def test_list_aliases(self, client: AsyncClient) -> None:
        """Should list all aliases."""
        response = await client.get("/registry/aliases")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_get_alias_success(self, client: AsyncClient) -> None:
        """Should return alias details."""
        # Create a successful run and alias
        create_response = await client.post(
            "/registry/runs",
            json={
                "model_type": "test-get-alias",
                "model_config": {},
                "data_window_start": "2024-01-01",
                "data_window_end": "2024-01-31",
                "store_id": 1,
                "product_id": 1,
            },
        )
        run_id = create_response.json()["run_id"]
        await client.patch(f"/registry/runs/{run_id}", json={"status": "running"})
        await client.patch(f"/registry/runs/{run_id}", json={"status": "success"})
        await client.post(
            "/registry/aliases",
            json={"alias_name": "get-test", "run_id": run_id},
        )

        response = await client.get("/registry/aliases/get-test")
        assert response.status_code == 200
        data = response.json()
        assert data["alias_name"] == "get-test"

    async def test_get_alias_not_found(self, client: AsyncClient) -> None:
        """Should return 404 for non-existent alias."""
        response = await client.get("/registry/aliases/nonexistent")
        assert response.status_code == 404

    async def test_delete_alias_success(self, client: AsyncClient) -> None:
        """Should delete an alias."""
        # Create a successful run and alias
        create_response = await client.post(
            "/registry/runs",
            json={
                "model_type": "test-delete-alias",
                "model_config": {},
                "data_window_start": "2024-01-01",
                "data_window_end": "2024-01-31",
                "store_id": 1,
                "product_id": 1,
            },
        )
        run_id = create_response.json()["run_id"]
        await client.patch(f"/registry/runs/{run_id}", json={"status": "running"})
        await client.patch(f"/registry/runs/{run_id}", json={"status": "success"})
        await client.post(
            "/registry/aliases",
            json={"alias_name": "delete-test", "run_id": run_id},
        )

        response = await client.delete("/registry/aliases/delete-test")
        assert response.status_code == 204

        # Verify deleted
        get_response = await client.get("/registry/aliases/delete-test")
        assert get_response.status_code == 404

    async def test_delete_alias_not_found(self, client: AsyncClient) -> None:
        """Should return 404 for non-existent alias."""
        response = await client.delete("/registry/aliases/nonexistent")
        assert response.status_code == 404


class TestCompareRunsEndpoint:
    """Tests for GET /registry/compare/{run_id_a}/{run_id_b} endpoint."""

    async def test_compare_runs_success(self, client: AsyncClient) -> None:
        """Should compare two runs."""
        # Create two runs with different configs
        run_a_response = await client.post(
            "/registry/runs",
            json={
                "model_type": "test-compare",
                "model_config": {"horizon": 7},
                "data_window_start": "2024-01-01",
                "data_window_end": "2024-01-31",
                "store_id": 1,
                "product_id": 1,
            },
        )
        run_a_id = run_a_response.json()["run_id"]

        run_b_response = await client.post(
            "/registry/runs",
            json={
                "model_type": "test-compare",
                "model_config": {"horizon": 14},
                "data_window_start": "2024-01-01",
                "data_window_end": "2024-01-31",
                "store_id": 1,
                "product_id": 1,
            },
        )
        run_b_id = run_b_response.json()["run_id"]

        # Compare
        response = await client.get(f"/registry/compare/{run_a_id}/{run_b_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["run_a"]["run_id"] == run_a_id
        assert data["run_b"]["run_id"] == run_b_id
        assert "config_diff" in data
        assert "metrics_diff" in data
        assert "horizon" in data["config_diff"]

    async def test_compare_runs_not_found(self, client: AsyncClient) -> None:
        """Should return 404 if either run not found."""
        response = await client.get(
            "/registry/compare/nonexistent1234567890123456/nonexistent0987654321098765"
        )
        assert response.status_code == 404
