#!/usr/bin/env python
"""Demonstrate model registry workflow.

Usage:
    uv run python examples/registry_demo.py

This script demonstrates:
1. Creating a model run
2. Transitioning through lifecycle states
3. Recording metrics and artifact info
4. Creating deployment aliases
5. Comparing runs

Prerequisites:
    - PostgreSQL running (docker-compose up -d)
    - Database migrated (uv run alembic upgrade head)
    - API running (uv run uvicorn app.main:app --reload --port 8123)
"""

import json
import sys
from datetime import date

import httpx

API_BASE = "http://localhost:8123"


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def print_response(response: httpx.Response, label: str = "") -> dict:
    """Print HTTP response details."""
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    status_emoji = "✓" if response.status_code < 400 else "✗"
    print(f"{status_emoji} {label} [{response.status_code}]")
    if data:
        print(json.dumps(data, indent=2, default=str))
    return data


def main() -> int:
    """Run the registry demo workflow."""
    print_section("ForecastLabAI - Model Registry Demo")

    client = httpx.Client(base_url=API_BASE, timeout=30)

    # Check API is running
    try:
        health = client.get("/health")
        if health.status_code != 200:
            print(f"API not healthy: {health.status_code}")
            return 1
    except httpx.ConnectError:
        print(f"Cannot connect to API at {API_BASE}")
        print("Start the API with: uv run uvicorn app.main:app --reload --port 8123")
        return 1

    print("✓ API is healthy\n")

    # ==========================================================================
    # Step 1: Create a model run
    # ==========================================================================
    print_section("Step 1: Create a Model Run")

    run_request = {
        "model_type": "seasonal_naive",
        "model_config": {
            "season_length": 7,
            "strategy": "repeat_pattern",
        },
        "feature_config": {
            "lags": [1, 7, 14],
            "rolling_windows": [7, 14, 28],
        },
        "data_window_start": str(date(2024, 1, 1)),
        "data_window_end": str(date(2024, 3, 31)),
        "store_id": 1,
        "product_id": 42,
        "agent_context": {
            "agent_id": "demo-agent",
            "session_id": "demo-session-001",
        },
        "git_sha": "abc123def456",
    }

    print("Request body:")
    print(json.dumps(run_request, indent=2))
    print()

    response = client.post("/registry/runs", json=run_request)
    run_data = print_response(response, "POST /registry/runs")

    if response.status_code != 201:
        print("\nFailed to create run. Exiting.")
        return 1

    run_id = run_data["run_id"]
    print(f"\n→ Created run: {run_id}")
    print(f"→ Config hash: {run_data['config_hash']}")
    print(f"→ Status: {run_data['status']}")

    # ==========================================================================
    # Step 2: Transition to RUNNING
    # ==========================================================================
    print_section("Step 2: Start the Run (PENDING → RUNNING)")

    response = client.patch(f"/registry/runs/{run_id}", json={"status": "running"})
    run_data = print_response(response, f"PATCH /registry/runs/{run_id}")

    print(f"\n→ Status: {run_data['status']}")
    print(f"→ Started at: {run_data['started_at']}")

    # ==========================================================================
    # Step 3: Complete with SUCCESS and metrics
    # ==========================================================================
    print_section("Step 3: Complete the Run (RUNNING → SUCCESS)")

    update_request = {
        "status": "success",
        "metrics": {
            "mae": 12.5,
            "smape": 8.3,
            "wape": 0.065,
            "bias": -0.02,
            "stability_index": 0.92,
        },
        "artifact_uri": f"models/{run_id[:8]}/model.pkl",
        "artifact_hash": "abc123def456789012345678901234567890abcdef0123456789012345678901",
        "artifact_size_bytes": 15360,
    }

    print("Update request:")
    print(json.dumps(update_request, indent=2))
    print()

    response = client.patch(f"/registry/runs/{run_id}", json=update_request)
    run_data = print_response(response, f"PATCH /registry/runs/{run_id}")

    print(f"\n→ Status: {run_data['status']}")
    print(f"→ Completed at: {run_data['completed_at']}")
    print(f"→ MAE: {run_data['metrics']['mae']}")

    # ==========================================================================
    # Step 4: Create deployment alias
    # ==========================================================================
    print_section("Step 4: Create Deployment Alias")

    alias_request = {
        "alias_name": "demo-production",
        "run_id": run_id,
        "description": "Production model for demo store/product",
    }

    response = client.post("/registry/aliases", json=alias_request)
    alias_data = print_response(response, "POST /registry/aliases")

    print(f"\n→ Alias '{alias_data['alias_name']}' → run {alias_data['run_id'][:12]}...")

    # ==========================================================================
    # Step 5: Create another run for comparison
    # ==========================================================================
    print_section("Step 5: Create Second Run for Comparison")

    run2_request = {
        "model_type": "naive",
        "model_config": {
            "strategy": "last_value",
        },
        "data_window_start": str(date(2024, 1, 1)),
        "data_window_end": str(date(2024, 3, 31)),
        "store_id": 1,
        "product_id": 42,
    }

    response = client.post("/registry/runs", json=run2_request)
    run2_data = print_response(response, "POST /registry/runs")
    run2_id = run2_data["run_id"]

    # Transition to success
    client.patch(f"/registry/runs/{run2_id}", json={"status": "running"})
    response = client.patch(
        f"/registry/runs/{run2_id}",
        json={
            "status": "success",
            "metrics": {"mae": 18.2, "smape": 12.1, "wape": 0.095},
        },
    )
    run2_data = response.json()

    print(f"\n→ Created comparison run: {run2_id[:12]}...")

    # ==========================================================================
    # Step 6: Compare runs
    # ==========================================================================
    print_section("Step 6: Compare Runs")

    response = client.get(f"/registry/compare/{run_id}/{run2_id}")
    compare_data = print_response(response, "GET /registry/compare/...")

    print("\n→ Configuration differences:")
    for key, values in compare_data["config_diff"].items():
        print(f"   {key}: {values['a']} vs {values['b']}")

    print("\n→ Metrics differences:")
    for metric, values in compare_data["metrics_diff"].items():
        if values["diff"] is not None:
            diff_pct = values["diff"] / values["b"] * 100 if values["b"] else 0
            print(f"   {metric}: {values['a']:.2f} vs {values['b']:.2f} (Δ{values['diff']:+.2f}, {diff_pct:+.1f}%)")

    # ==========================================================================
    # Step 7: List runs and aliases
    # ==========================================================================
    print_section("Step 7: List Runs and Aliases")

    response = client.get("/registry/runs?status=success&page_size=5")
    list_data = print_response(response, "GET /registry/runs?status=success")
    print(f"\n→ Found {list_data['total']} successful runs")

    response = client.get("/registry/aliases")
    aliases = print_response(response, "GET /registry/aliases")
    print(f"\n→ Found {len(aliases)} aliases")

    # ==========================================================================
    # Cleanup info
    # ==========================================================================
    print_section("Demo Complete!")

    print("Summary:")
    print(f"  - Created runs: {run_id[:12]}..., {run2_id[:12]}...")
    print("  - Created alias: demo-production")
    print()
    print("To clean up, delete the alias and runs:")
    print(f"  curl -X DELETE {API_BASE}/registry/aliases/demo-production")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
