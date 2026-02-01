"""Integration tests for backtesting routes.

These tests run against a real PostgreSQL database to verify the complete flow
from API request through database queries to response.

Requires PostgreSQL to be running: docker-compose up -d
"""

from datetime import date

import pytest
from httpx import AsyncClient

from app.features.data_platform.models import Product, SalesDaily, Store


@pytest.mark.integration
@pytest.mark.asyncio
class TestBacktestingRouteIntegration:
    """Integration tests for POST /backtesting/run endpoint."""

    async def test_run_backtest_expanding_strategy(
        self,
        client: AsyncClient,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test backtest with expanding window strategy."""
        response = await client.post(
            "/backtesting/run",
            json={
                "store_id": sample_store.id,
                "product_id": sample_product.id,
                "start_date": "2024-01-01",
                "end_date": "2024-04-29",
                "config": {
                    "split_config": {
                        "strategy": "expanding",
                        "n_splits": 5,
                        "min_train_size": 30,
                        "gap": 0,
                        "horizon": 14,
                    },
                    "model_config_main": {"model_type": "naive"},
                    "include_baselines": False,
                    "store_fold_details": True,
                },
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["store_id"] == sample_store.id
        assert data["product_id"] == sample_product.id
        assert data["leakage_check_passed"] is True
        assert data["main_model_results"]["model_type"] == "naive"
        assert len(data["main_model_results"]["fold_results"]) == 5

        # Verify train size increases with expanding window
        fold_results = data["main_model_results"]["fold_results"]
        train_sizes = [f["split"]["train_size"] for f in fold_results]
        assert train_sizes == sorted(train_sizes), (
            "Train sizes should increase for expanding window"
        )

    async def test_run_backtest_sliding_strategy(
        self,
        client: AsyncClient,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test backtest with sliding window strategy."""
        response = await client.post(
            "/backtesting/run",
            json={
                "store_id": sample_store.id,
                "product_id": sample_product.id,
                "start_date": "2024-01-01",
                "end_date": "2024-04-29",
                "config": {
                    "split_config": {
                        "strategy": "sliding",
                        "n_splits": 5,
                        "min_train_size": 30,
                        "gap": 0,
                        "horizon": 14,
                    },
                    "model_config_main": {"model_type": "naive"},
                    "include_baselines": False,
                    "store_fold_details": True,
                },
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["main_model_results"]["model_type"] == "naive"
        assert len(data["main_model_results"]["fold_results"]) == 5

        # Verify train size is constant with sliding window
        fold_results = data["main_model_results"]["fold_results"]
        train_sizes = [f["split"]["train_size"] for f in fold_results]
        assert len(set(train_sizes)) == 1, "Train sizes should be constant for sliding window"

    async def test_run_backtest_with_gap(
        self,
        client: AsyncClient,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test backtest with gap between train and test."""
        response = await client.post(
            "/backtesting/run",
            json={
                "store_id": sample_store.id,
                "product_id": sample_product.id,
                "start_date": "2024-01-01",
                "end_date": "2024-04-29",
                "config": {
                    "split_config": {
                        "strategy": "expanding",
                        "n_splits": 3,
                        "min_train_size": 30,
                        "gap": 7,
                        "horizon": 14,
                    },
                    "model_config_main": {"model_type": "naive"},
                    "include_baselines": False,
                    "store_fold_details": True,
                },
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Verify gap is respected: test_start should be > train_end + gap days
        fold_results = data["main_model_results"]["fold_results"]
        for fold in fold_results:
            train_end = date.fromisoformat(fold["split"]["train_end"])
            test_start = date.fromisoformat(fold["split"]["test_start"])
            gap_days = (test_start - train_end).days
            assert gap_days >= 7, f"Gap should be at least 7 days, got {gap_days}"

    async def test_run_backtest_with_baselines(
        self,
        client: AsyncClient,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test backtest with baseline comparison enabled."""
        response = await client.post(
            "/backtesting/run",
            json={
                "store_id": sample_store.id,
                "product_id": sample_product.id,
                "start_date": "2024-01-01",
                "end_date": "2024-04-29",
                "config": {
                    "split_config": {
                        "strategy": "expanding",
                        "n_splits": 5,
                        "min_train_size": 30,
                        "gap": 0,
                        "horizon": 14,
                    },
                    "model_config_main": {"model_type": "naive"},
                    "include_baselines": True,
                    "store_fold_details": True,
                },
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Verify baseline results are present
        assert data["baseline_results"] is not None
        assert len(data["baseline_results"]) >= 1

        # Verify comparison summary is present
        assert data["comparison_summary"] is not None
        assert "mae" in data["comparison_summary"]

        # Check baseline model types
        baseline_types = [r["model_type"] for r in data["baseline_results"]]
        assert "naive" in baseline_types or "seasonal_naive" in baseline_types

    async def test_run_backtest_without_fold_details(
        self,
        client: AsyncClient,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test backtest with store_fold_details=False."""
        response = await client.post(
            "/backtesting/run",
            json={
                "store_id": sample_store.id,
                "product_id": sample_product.id,
                "start_date": "2024-01-01",
                "end_date": "2024-04-29",
                "config": {
                    "split_config": {
                        "strategy": "expanding",
                        "n_splits": 5,
                        "min_train_size": 30,
                        "gap": 0,
                        "horizon": 14,
                    },
                    "model_config_main": {"model_type": "naive"},
                    "include_baselines": False,
                    "store_fold_details": False,
                },
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Verify fold results exist but have empty arrays
        fold_results = data["main_model_results"]["fold_results"]
        assert len(fold_results) == 5
        for fold in fold_results:
            assert fold["dates"] == []
            assert fold["actuals"] == []
            assert fold["predictions"] == []
            # Metrics should still be present
            assert "mae" in fold["metrics"]

    async def test_run_backtest_insufficient_data_returns_400(
        self,
        client: AsyncClient,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test that insufficient data returns 400 error."""
        # Request a date range with only 20 days of data but require min_train=30
        response = await client.post(
            "/backtesting/run",
            json={
                "store_id": sample_store.id,
                "product_id": sample_product.id,
                "start_date": "2024-01-01",
                "end_date": "2024-01-20",  # Only 20 days
                "config": {
                    "split_config": {
                        "strategy": "expanding",
                        "n_splits": 5,
                        "min_train_size": 30,  # Requires 30 days minimum
                        "gap": 0,
                        "horizon": 14,
                    },
                    "model_config_main": {"model_type": "naive"},
                    "include_baselines": False,
                    "store_fold_details": True,
                },
            },
        )

        assert response.status_code == 400
        assert "detail" in response.json()

    async def test_run_backtest_no_data_returns_400(
        self,
        client: AsyncClient,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test that no data for given filters returns 400 error."""
        # Request data for a different store that doesn't exist
        response = await client.post(
            "/backtesting/run",
            json={
                "store_id": 9999,  # Non-existent store
                "product_id": sample_product.id,
                "start_date": "2024-01-01",
                "end_date": "2024-04-29",
                "config": {
                    "split_config": {
                        "strategy": "expanding",
                        "n_splits": 5,
                        "min_train_size": 30,
                        "gap": 0,
                        "horizon": 14,
                    },
                    "model_config_main": {"model_type": "naive"},
                    "include_baselines": False,
                    "store_fold_details": True,
                },
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "No data found" in data["detail"]

    async def test_response_contains_all_expected_fields(
        self,
        client: AsyncClient,
        sample_store: Store,
        sample_product: Product,
        sample_sales_120: list[SalesDaily],
    ) -> None:
        """Test that response contains all expected fields with correct types."""
        response = await client.post(
            "/backtesting/run",
            json={
                "store_id": sample_store.id,
                "product_id": sample_product.id,
                "start_date": "2024-01-01",
                "end_date": "2024-04-29",
                "config": {
                    "split_config": {
                        "strategy": "expanding",
                        "n_splits": 5,
                        "min_train_size": 30,
                        "gap": 0,
                        "horizon": 14,
                    },
                    "model_config_main": {"model_type": "naive"},
                    "include_baselines": True,
                    "store_fold_details": True,
                },
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Top-level fields
        assert "backtest_id" in data
        assert isinstance(data["backtest_id"], str)
        assert len(data["backtest_id"]) == 16

        assert "store_id" in data
        assert isinstance(data["store_id"], int)

        assert "product_id" in data
        assert isinstance(data["product_id"], int)

        assert "config_hash" in data
        assert isinstance(data["config_hash"], str)

        assert "split_config" in data
        assert isinstance(data["split_config"], dict)

        assert "duration_ms" in data
        assert isinstance(data["duration_ms"], float)
        assert data["duration_ms"] > 0

        assert "leakage_check_passed" in data
        assert isinstance(data["leakage_check_passed"], bool)

        # Main model results
        main_results = data["main_model_results"]
        assert "model_type" in main_results
        assert "config_hash" in main_results
        assert "fold_results" in main_results
        assert "aggregated_metrics" in main_results
        assert "metric_std" in main_results

        # Aggregated metrics
        agg_metrics = main_results["aggregated_metrics"]
        expected_metrics = ["mae", "smape", "wape", "bias"]
        for metric in expected_metrics:
            assert metric in agg_metrics, f"Missing metric: {metric}"
            assert isinstance(agg_metrics[metric], float)

        # Fold results
        for fold in main_results["fold_results"]:
            assert "fold_index" in fold
            assert "split" in fold
            assert "dates" in fold
            assert "actuals" in fold
            assert "predictions" in fold
            assert "metrics" in fold

            # Split details
            split = fold["split"]
            assert "train_start" in split
            assert "train_end" in split
            assert "test_start" in split
            assert "test_end" in split
            assert "train_size" in split
            assert "test_size" in split
