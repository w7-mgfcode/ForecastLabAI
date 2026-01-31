#!/usr/bin/env python
"""Demo script for feature engineering computation.

Usage:
    uv run python examples/compute_features_demo.py

This script demonstrates how to:
1. Configure feature engineering with various feature types
2. Compute time-safe features via the API
3. Preview features for debugging

Requirements:
    - API server running: uv run uvicorn app.main:app --port 8123
    - Database seeded with sales data
"""

import json
from datetime import date

import httpx

# API configuration
API_BASE = "http://localhost:8123"
FEATURES_ENDPOINT = f"{API_BASE}/featuresets"


def create_sample_config() -> dict:
    """Create a sample feature configuration.

    Returns:
        FeatureSetConfig as a dictionary.
    """
    return {
        "name": "retail_forecast_v1",
        "description": "Standard retail forecasting features",
        "entity_columns": ["store_id", "product_id"],
        "date_column": "date",
        "target_column": "quantity",
        "lag_config": {
            "lags": [1, 7, 14, 28],
            "target_column": "quantity",
            "fill_value": None,
        },
        "rolling_config": {
            "windows": [7, 14, 28],
            "aggregations": ["mean", "std", "min", "max"],
            "target_column": "quantity",
            "min_periods": 7,
        },
        "calendar_config": {
            "include_day_of_week": True,
            "include_month": True,
            "include_quarter": True,
            "include_year": False,
            "include_is_weekend": True,
            "include_is_month_end": False,
            "include_is_holiday": False,
            "use_cyclical_encoding": True,
        },
        "imputation_config": {
            "strategies": {
                "quantity": "zero",
                "unit_price": "ffill",
            }
        },
    }


def compute_features(
    store_id: int,
    product_id: int,
    cutoff_date: date,
    lookback_days: int = 365,
) -> dict:
    """Compute features for a single series.

    Args:
        store_id: Store identifier.
        product_id: Product identifier.
        cutoff_date: Date up to which features are computed.
        lookback_days: Number of days of history to use.

    Returns:
        API response with computed features.
    """
    request_body = {
        "store_id": store_id,
        "product_id": product_id,
        "cutoff_date": cutoff_date.isoformat(),
        "lookback_days": lookback_days,
        "config": create_sample_config(),
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{FEATURES_ENDPOINT}/compute",
            json=request_body,
        )
        response.raise_for_status()
        return response.json()


def preview_features(
    store_id: int,
    product_id: int,
    cutoff_date: date,
    sample_rows: int = 10,
) -> dict:
    """Preview features for debugging.

    Args:
        store_id: Store identifier.
        product_id: Product identifier.
        cutoff_date: Date up to which features are computed.
        sample_rows: Number of sample rows to return.

    Returns:
        API response with sample feature rows.
    """
    request_body = {
        "store_id": store_id,
        "product_id": product_id,
        "cutoff_date": cutoff_date.isoformat(),
        "sample_rows": sample_rows,
        "config": create_sample_config(),
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{FEATURES_ENDPOINT}/preview",
            json=request_body,
        )
        response.raise_for_status()
        return response.json()


def main() -> None:
    """Run the feature engineering demo."""
    print("ForecastLabAI - Feature Engineering Demo")
    print("=" * 50)
    print()

    # Demo parameters
    store_id = 1
    product_id = 1
    cutoff_date = date(2024, 1, 31)

    print(f"Store ID: {store_id}")
    print(f"Product ID: {product_id}")
    print(f"Cutoff Date: {cutoff_date}")
    print()

    # Show configuration
    print("Feature Configuration:")
    print("-" * 30)
    config = create_sample_config()
    print(f"  Name: {config['name']}")
    print(f"  Lag features: {config['lag_config']['lags']}")
    print(f"  Rolling windows: {config['rolling_config']['windows']}")
    print(f"  Rolling aggregations: {config['rolling_config']['aggregations']}")
    print(f"  Cyclical encoding: {config['calendar_config']['use_cyclical_encoding']}")
    print()

    try:
        # Preview features
        print("Previewing features (10 sample rows)...")
        print("-" * 30)

        result = preview_features(
            store_id=store_id,
            product_id=product_id,
            cutoff_date=cutoff_date,
            sample_rows=10,
        )

        print(f"  Config hash: {result['config_hash']}")
        print(f"  Row count: {result['row_count']}")
        print(f"  Feature columns: {len(result['feature_columns'])}")
        print(f"  Duration: {result['duration_ms']:.2f}ms")
        print()

        print("Feature columns:")
        for col in result["feature_columns"]:
            print(f"    - {col}")
        print()

        print("Sample rows (last 3):")
        for row in result["rows"][-3:]:
            print(f"  Date: {row['date']}")
            print(f"    Features: {json.dumps(row['features'], indent=6)}")
        print()

        # Compute full features
        print("Computing full features...")
        print("-" * 30)

        full_result = compute_features(
            store_id=store_id,
            product_id=product_id,
            cutoff_date=cutoff_date,
            lookback_days=365,
        )

        print(f"  Total rows: {full_result['row_count']}")
        print(f"  Duration: {full_result['duration_ms']:.2f}ms")
        print()

        # Show null counts
        if full_result["null_counts"]:
            print("Null counts per feature:")
            for col, count in sorted(full_result["null_counts"].items()):
                if count > 0:
                    print(f"    {col}: {count}")
        print()

        print("Demo completed successfully!")

    except httpx.ConnectError:
        print("ERROR: Cannot connect to API server.")
        print("Please start the server with:")
        print("  uv run uvicorn app.main:app --port 8123")

    except httpx.HTTPStatusError as e:
        print(f"ERROR: API returned status {e.response.status_code}")
        print(f"Response: {e.response.text}")


if __name__ == "__main__":
    main()
