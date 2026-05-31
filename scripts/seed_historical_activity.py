"""Backfill historical model activity through the public API.

Creates a realistic spread of train/predict/backtest jobs over the seeded
date range so the Registry, Jobs, and Forecasts dashboards have meaningful
content. All rows have created_at=NOW (pure API flow, no SQL writes);
the historical FEEL comes from varied train_end_date / cutoff values
across 2024-2026.

Optionally finishes by creating a small batch job through /batch/forecasting.

Usage:
    uv run python scripts/seed_historical_activity.py --base http://localhost:8123
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date

import httpx

# (store_id, product_id) pairs hand-picked from high-volume series.
PAIRS: list[tuple[int, int]] = [
    (11, 67),
    (13, 86),
    (15, 86),
    (20, 67),
]

# train_end_date cutoffs spanning 2024-Q4 → 2026-Q1 — gives the registry
# "as_of" spread without backdating created_at.
CUTOFFS: list[date] = [
    date(2024, 12, 31),
    date(2025, 6, 30),
    date(2025, 12, 31),
]

BASELINES: list[str] = ["naive", "seasonal_naive", "moving_average"]


async def submit_job(
    client: httpx.AsyncClient, job_type: str, params: dict[str, object]
) -> dict[str, object]:
    r = await client.post("/jobs", json={"job_type": job_type, "params": params})
    r.raise_for_status()
    return r.json()


async def poll_job(
    client: httpx.AsyncClient, job_id: str, timeout_s: float = 60.0
) -> dict[str, object]:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        r = await client.get(f"/jobs/{job_id}")
        r.raise_for_status()
        body = r.json()
        if body.get("status") in {"completed", "failed", "cancelled"}:
            return body
        await asyncio.sleep(0.3)
    raise TimeoutError(f"Job {job_id} did not complete within {timeout_s}s")


async def train_one(
    client: httpx.AsyncClient,
    store_id: int,
    product_id: int,
    model_type: str,
    cutoff: date,
) -> dict[str, object]:
    params = {
        "model_type": model_type,
        "store_id": store_id,
        "product_id": product_id,
        "start_date": "2024-01-01",
        "end_date": cutoff.isoformat(),
    }
    submitted = await submit_job(client, "train", params)
    return await poll_job(client, str(submitted["job_id"]))


async def predict_for_run(
    client: httpx.AsyncClient, run_id: str, horizon: int = 14
) -> dict[str, object] | None:
    submitted = await submit_job(client, "predict", {"run_id": run_id, "horizon": horizon})
    return await poll_job(client, str(submitted["job_id"]))


async def backtest_one(
    client: httpx.AsyncClient,
    store_id: int,
    product_id: int,
    model_type: str,
) -> dict[str, object]:
    submitted = await submit_job(
        client,
        "backtest",
        {
            "model_type": model_type,
            "store_id": store_id,
            "product_id": product_id,
            "start_date": "2024-01-01",
            "end_date": "2026-05-01",
            "n_splits": 3,
            "test_size": 14,
        },
    )
    return await poll_job(client, str(submitted["job_id"]), timeout_s=120.0)


async def main(base_url: str) -> int:
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        # Phase 1: train across (pair x cutoff x baseline)
        train_results: list[dict[str, object]] = []
        for pair in PAIRS:
            for cutoff in CUTOFFS:
                for model_type in BASELINES:
                    res = await train_one(client, pair[0], pair[1], model_type, cutoff)
                    train_results.append(res)
                    status = res.get("status")
                    run = res.get("run_id")
                    print(
                        f"  train  store={pair[0]:>3} prod={pair[1]:>3} "
                        f"model={model_type:<16} cutoff={cutoff} → {status} run_id={run}"
                    )
        print(f"  ✅ trained {len(train_results)} models")

        # Phase 2: predict for every successful run at the latest cutoff
        successful_runs = [
            r for r in train_results if r.get("status") == "completed" and r.get("run_id")
        ]
        # only fan-predict the latest cutoff (one predict per pair x model)
        latest = CUTOFFS[-1].isoformat()
        latest_runs = [
            r for r in successful_runs if str(r.get("params", {}).get("end_date")) == latest
        ]
        predict_results = []
        for r in latest_runs:
            run_id = str(r["run_id"])
            pred = await predict_for_run(client, run_id, horizon=14)
            predict_results.append(pred)
            status = pred.get("status") if pred else "skip"
            print(f"  predict run_id={run_id[:8]}… → {status}")
        print(f"  ✅ predicted {len(predict_results)} horizons")

        # Phase 3: 2 backtests for variety (one fast baseline per pair)
        bt_results = []
        for pair in PAIRS[:2]:
            bt = await backtest_one(client, pair[0], pair[1], "seasonal_naive")
            bt_results.append(bt)
            print(
                f"  backtest store={pair[0]} prod={pair[1]} model=seasonal_naive → {bt.get('status')}"
            )
        print(f"  ✅ ran {len(bt_results)} backtests")

        # Phase 4: small batch through /batch/forecasting (variety, second batch_job row)
        try:
            batch_payload = {
                "operation": "train",
                "scope": {
                    "kind": "manual",
                    "store_ids": [11, 13],
                    "product_ids": [67, 86],
                },
                "model_configs": [
                    {"model_type": "naive"},
                    {"model_type": "seasonal_naive"},
                ],
                "start_date": "2024-01-01",
                "end_date": "2025-12-31",
                "max_parallel": 2,
            }
            r = await client.post("/batch/forecasting", json=batch_payload)
            r.raise_for_status()
            bj = r.json()
            print(f"  ✅ submitted batch_id={bj.get('batch_id')} items={bj.get('item_count')}")
        except httpx.HTTPStatusError as e:
            print(
                f"  ⚠️ batch submit failed (non-fatal): {e.response.status_code} {e.response.text[:120]}"
            )

        # Summary numbers
        print()
        print("Summary:")
        print(f"  train jobs       : {len(train_results)}")
        print(f"  predict jobs     : {len(predict_results)}")
        print(f"  backtest jobs    : {len(bt_results)}")
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8123")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(_parse_args().base)))
