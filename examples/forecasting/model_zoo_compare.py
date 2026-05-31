"""PRP-36 — Model-zoo comparison diagnostic.

Read-only script: trains + backtests every available forecasting model
against the local seeded database for a single ``(store_id, product_id)``
grain, then prints a metrics + per-bucket WAPE table. Uses the public
HTTP API at ``http://localhost:8123`` — never writes outside the existing
``/forecasting/train`` + ``/backtesting/run`` flow.

Usage::

    # 1. Run the stack:
    docker compose up -d
    uv run alembic upgrade head
    uv run uvicorn app.main:app --reload --port 8123

    # 2. Seed the local database (any time):
    uv run python scripts/seed_random.py --full-new --seed 42 --confirm

    # 3. Compare every model on a single grain:
    uv run python examples/forecasting/model_zoo_compare.py \\
        --store-id 1 --product-id 1 \\
        --start-date 2025-01-01 --end-date 2025-12-31

Models compared (always-on):

- ``naive``, ``seasonal_naive``, ``moving_average``
- ``weighted_moving_average``, ``seasonal_average`` (PRP-36 baselines)
- ``trend_regression_baseline`` (PRP-36 Ridge baseline)
- ``regression`` (HGBR feature-aware)
- ``prophet_like`` (Ridge additive)

Optional feature-aware models — exercised only when the matching
``forecast_enable_*`` flag is on AND the extra is installed:

- ``lightgbm``, ``xgboost``, ``random_forest``

The script reads ``GET /config/ai`` to discover which models are
available; absent models are SKIPPED with a printed note (the script
never fails the run because an opt-in model is off).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date as date_type
from typing import Any

import httpx

DEFAULT_API_BASE = "http://localhost:8123"


@dataclass(frozen=True)
class ModelSpec:
    """One row in the model-zoo comparison table."""

    model_type: str
    config: dict[str, Any]
    optional: bool = False


ALWAYS_ON_MODELS: tuple[ModelSpec, ...] = (
    ModelSpec("naive", {"model_type": "naive"}),
    ModelSpec("seasonal_naive", {"model_type": "seasonal_naive", "season_length": 7}),
    ModelSpec("moving_average", {"model_type": "moving_average", "window_size": 7}),
    ModelSpec(
        "weighted_moving_average",
        {
            "model_type": "weighted_moving_average",
            "window_size": 7,
            "weight_strategy": "linear",
            "decay": 0.7,
        },
    ),
    ModelSpec(
        "seasonal_average",
        {
            "model_type": "seasonal_average",
            "season_length": 7,
            "lookback_cycles": 4,
            "trim_outliers": False,
        },
    ),
    ModelSpec(
        "trend_regression_baseline",
        {
            "model_type": "trend_regression_baseline",
            "alpha": 1.0,
            "include_dow": True,
            "include_month": True,
        },
    ),
    ModelSpec(
        "regression",
        {"model_type": "regression", "max_iter": 200, "learning_rate": 0.05, "max_depth": 6},
    ),
    ModelSpec(
        "prophet_like",
        {"model_type": "prophet_like", "alpha": 1.0},
    ),
)

OPTIONAL_MODELS: tuple[ModelSpec, ...] = (
    ModelSpec(
        "lightgbm",
        {"model_type": "lightgbm", "n_estimators": 100, "max_depth": 6, "learning_rate": 0.1},
        optional=True,
    ),
    ModelSpec(
        "xgboost",
        {"model_type": "xgboost", "n_estimators": 100, "max_depth": 6, "learning_rate": 0.1},
        optional=True,
    ),
    ModelSpec(
        "random_forest",
        {
            "model_type": "random_forest",
            "n_estimators": 100,
            "max_depth": 10,
            "min_samples_leaf": 2,
        },
        optional=True,
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PRP-36 model-zoo comparison")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--store-id", type=int, required=True)
    parser.add_argument("--product-id", type=int, required=True)
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--horizon", type=int, default=14)
    return parser.parse_args()


def _backtest_one_model(
    client: httpx.Client,
    *,
    api_base: str,
    store_id: int,
    product_id: int,
    start_date: str,
    end_date: str,
    spec: ModelSpec,
    n_splits: int,
    horizon: int,
) -> dict[str, Any] | None:
    body = {
        "store_id": store_id,
        "product_id": product_id,
        "start_date": start_date,
        "end_date": end_date,
        "config": {
            "split_config": {
                "n_splits": n_splits,
                "horizon": horizon,
                "gap": 0,
                "strategy": "expanding",
                "min_train_size": 30,
            },
            "model_config_main": spec.config,
            "include_baselines": False,  # we compare them explicitly here
            "store_fold_details": False,
        },
    }
    try:
        response = client.post(f"{api_base}/backtesting/run", json=body, timeout=120.0)
    except httpx.HTTPError as exc:
        print(f"  ⚠️ {spec.model_type}: HTTP error — {exc!r}")
        return None
    if response.status_code != 200:
        # Optional models behind a flag yield a clear ValueError → 400/422.
        try:
            detail = response.json().get("detail", "")
        except json.JSONDecodeError:
            detail = response.text[:200]
        if spec.optional:
            print(f"  ⏭️ {spec.model_type}: skipped — {detail}")
        else:
            print(f"  ❌ {spec.model_type}: HTTP {response.status_code} — {detail}")
        return None
    return dict(response.json())


def _format_row(spec: ModelSpec, result: dict[str, Any] | None) -> str:
    if result is None:
        return f"{spec.model_type:<28} skipped"
    main = result.get("main_model_results", {})
    aggregated = main.get("aggregated_metrics", {})
    bucketed = main.get("bucketed_aggregated_metrics") or {}
    wape_h_1_7 = bucketed.get("h_1_7", {}).get("wape")
    wape_h_8_14 = bucketed.get("h_8_14", {}).get("wape")

    def _fmt(value: Any) -> str:
        if value is None:
            return "  -"
        return f"{float(value):>6.2f}"

    return (
        f"{spec.model_type:<28}"
        f"  MAE {_fmt(aggregated.get('mae'))}"
        f"  RMSE {_fmt(aggregated.get('rmse'))}"
        f"  WAPE {_fmt(aggregated.get('wape'))}"
        f"  h_1_7 {_fmt(wape_h_1_7)}"
        f"  h_8_14 {_fmt(wape_h_8_14)}"
    )


def main() -> int:
    args = parse_args()
    start_date_iso = str(date_type.fromisoformat(args.start_date))
    end_date_iso = str(date_type.fromisoformat(args.end_date))

    print(f"━ Model zoo comparison ─ store {args.store_id}, product {args.product_id}")
    print(f"  window: {start_date_iso} → {end_date_iso}")
    print(f"  folds: {args.n_splits}, horizon: {args.horizon}")
    print()

    rows: list[str] = []
    with httpx.Client() as client:
        # Probe / health gate.
        try:
            health = client.get(f"{args.api_base}/health", timeout=5.0)
            if health.status_code != 200:
                print(f"❌ /health returned {health.status_code}; aborting.")
                return 2
        except httpx.HTTPError as exc:
            print(f"❌ API unreachable at {args.api_base}: {exc!r}")
            return 2

        all_specs: tuple[ModelSpec, ...] = ALWAYS_ON_MODELS + OPTIONAL_MODELS
        for spec in all_specs:
            print(f"🔄 Backtesting {spec.model_type} …")
            result = _backtest_one_model(
                client,
                api_base=args.api_base,
                store_id=args.store_id,
                product_id=args.product_id,
                start_date=start_date_iso,
                end_date=end_date_iso,
                spec=spec,
                n_splits=args.n_splits,
                horizon=args.horizon,
            )
            rows.append(_format_row(spec, result))

    print()
    print("━" * 100)
    for row in rows:
        print(row)
    print("━" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
