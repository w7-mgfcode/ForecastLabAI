"""Populate the registry from previously-completed train jobs.

``/jobs/train`` produces a forecast artifact but does NOT create a
``model_run`` row — the canonical registry flow lives in
``scripts/run_demo.py:step_register`` and goes:

    /forecasting/train  →  artifact at forecast_model_artifacts_dir
    POST /registry/runs                    (pending)
    PATCH /registry/runs/{id} status=running
    PATCH /registry/runs/{id} status=success + metrics + artifact_uri

This script walks every completed train job and runs steps 2-4 against
the registry, then picks per-(store, product) winners and stamps aliases.

Metrics are deterministic-stub values keyed off the job's `run_id` so the
dashboard surfaces meaningful spread without re-running backtests.

Usage:
    uv run python scripts/seed_registry_from_jobs.py --base http://localhost:8123
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import random
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import httpx

from app.core.config import get_settings


def _stub_metrics(model_type: str, key: str) -> dict[str, float]:
    """Deterministic-but-varied metrics derived from ``key`` (e.g. job run_id)."""
    digest = hashlib.sha256(f"{model_type}:{key}".encode()).hexdigest()
    rng = random.Random(int(digest, 16))
    # Bands chosen so seasonal_naive usually wins, regression sometimes beats it.
    bands = {
        "naive": (0.20, 0.28),
        "seasonal_naive": (0.12, 0.18),
        "moving_average": (0.15, 0.22),
        "regression": (0.10, 0.20),
        "lightgbm": (0.10, 0.18),
        "xgboost": (0.10, 0.18),
        "prophet_like": (0.13, 0.20),
    }
    lo, hi = bands.get(model_type, (0.15, 0.25))
    wape = rng.uniform(lo, hi)
    mae = wape * rng.uniform(80, 120)  # base demand ≈ 100
    return {
        "mae": round(mae, 4),
        "wape": round(wape, 4),
        "smape": round(wape * rng.uniform(0.9, 1.1), 4),
        "bias": round(rng.uniform(-3, 3), 4),
    }


def _model_config_payload(model_type: str) -> dict[str, object]:
    if model_type == "naive":
        return {"model_type": "naive"}
    if model_type == "seasonal_naive":
        return {"model_type": "seasonal_naive", "season_length": 7}
    if model_type == "moving_average":
        return {"model_type": "moving_average", "window_size": 7}
    raise ValueError(f"Unsupported model_type: {model_type}")


async def fetch_completed_train_jobs(client: httpx.AsyncClient) -> list[dict[str, object]]:
    """Fetch every completed train job through the public API."""
    page_size = 100
    out: list[dict[str, object]] = []
    page = 1
    while True:
        r = await client.get(
            "/jobs",
            params={
                "page": page,
                "page_size": page_size,
                "job_type": "train",
                "status": "completed",
            },
        )
        r.raise_for_status()
        body = r.json()
        jobs = body.get("jobs") or []
        out.extend(jobs)
        total = int(body.get("total", 0))
        # Exit on empty page, short page (last page partially filled), or
        # once accumulated count covers reported total.
        if not jobs or len(jobs) < page_size or len(out) >= total:
            break
        page += 1
    return out


async def register_one(
    client: httpx.AsyncClient, job: dict[str, object], registry_root: Path
) -> dict[str, str] | None:
    params = job.get("params") or {}
    result = job.get("result") or {}
    if not isinstance(params, dict) or not isinstance(result, dict):
        return None
    model_type = str(params.get("model_type", ""))
    if model_type not in {"naive", "seasonal_naive", "moving_average"}:
        return None  # only baselines for this backfill
    model_path_raw = str(result.get("model_path") or "").strip()
    if not model_path_raw:
        # job result didn't carry a path — nothing to backfill
        return None
    source_path = Path(model_path_raw)
    if not source_path.is_file():
        # try relative-to-cwd; reject if the candidate is missing or a directory
        rel = Path.cwd() / source_path
        if rel.is_file():
            source_path = rel
        else:
            return None
    forecast_run_id = str(result.get("run_id", ""))
    artifact_uri = f"backfill/{model_type}-{source_path.stem}.joblib"
    dest = registry_root / artifact_uri
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(source_path, dest)
    raw = dest.read_bytes()
    artifact_hash = hashlib.sha256(raw).hexdigest()

    # (a) create
    r = await client.post(
        "/registry/runs",
        json={
            "model_type": model_type,
            "model_config": _model_config_payload(model_type),
            "feature_config": None,
            "data_window_start": str(params.get("start_date")),
            "data_window_end": str(params.get("end_date")),
            "store_id": int(params["store_id"]),
            "product_id": int(params["product_id"]),
            "agent_context": None,
            "git_sha": None,
        },
    )
    if r.status_code == 409:
        # duplicate config_hash with registry_duplicate_policy="deny" → idempotent skip
        return None
    if r.status_code >= 400:
        # surface unexpected 4xx / 5xx so registry downtime or validation errors
        # aren't silently swallowed as duplicates
        try:
            detail: object = r.json()
        except ValueError:
            detail = r.text
        raise RuntimeError(f"POST /registry/runs failed (status {r.status_code}): {detail!r}")
    run_id = str(r.json().get("run_id"))

    # (b) running
    r = await client.patch(f"/registry/runs/{run_id}", json={"status": "running"})
    r.raise_for_status()

    # (c) success + metrics + artifact info
    metrics = _stub_metrics(model_type, forecast_run_id)
    r = await client.patch(
        f"/registry/runs/{run_id}",
        json={
            "status": "success",
            "metrics": metrics,
            "artifact_uri": artifact_uri,
            "artifact_hash": artifact_hash,
            "artifact_size_bytes": len(raw),
        },
    )
    r.raise_for_status()
    return {
        "run_id": run_id,
        "store_id": str(params["store_id"]),
        "product_id": str(params["product_id"]),
        "model_type": model_type,
        "wape": str(metrics["wape"]),
        "data_window_end": str(params.get("end_date")),
    }


async def main(base_url: str) -> int:
    settings = get_settings()
    registry_root = Path(settings.registry_artifact_root).resolve()
    registry_root.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        jobs = await fetch_completed_train_jobs(client)
        print(f"Found {len(jobs)} completed train jobs")
        registered: list[dict[str, str]] = []
        for j in jobs:
            row = await register_one(client, j, registry_root)
            if row:
                registered.append(row)
                print(
                    f"  ✅ registered store={row['store_id']:>3} prod={row['product_id']:>3} "
                    f"model={row['model_type']:<16} cutoff={row['data_window_end']} "
                    f"wape={row['wape']} run_id={row['run_id'][:8]}…"
                )
            else:
                print(f"  ⏭️  skipped job_id={j.get('job_id')}")
        print(f"\nTotal registered: {len(registered)}")

        # Pick winners (lowest WAPE) per (store, product) on the LATEST cutoff
        latest = max(r["data_window_end"] for r in registered) if registered else None
        if latest:
            by_pair: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
            for r_ in registered:
                if r_["data_window_end"] == latest:
                    by_pair[(r_["store_id"], r_["product_id"])].append(r_)
            alias_specs = [
                ("champion", 0),
                ("challenger", 1),
            ]
            print(f"\nAliasing for latest cutoff = {latest}")
            for (sid, pid), rows in sorted(by_pair.items()):
                rows.sort(key=lambda x: float(x["wape"]))
                for alias_base, idx in alias_specs:
                    if idx >= len(rows):
                        continue
                    alias_name = f"{alias_base}-s{sid}-p{pid}"
                    body = {
                        "alias_name": alias_name,
                        "run_id": rows[idx]["run_id"],
                        "description": f"Auto: {alias_base} for store={sid} product={pid}",
                    }
                    r = await client.post("/registry/aliases", json=body)
                    if r.status_code >= 400:
                        print(f"  ⚠️  alias {alias_name}: {r.status_code} {r.text[:100]}")
                    else:
                        print(
                            f"  🏷️  {alias_name} → {rows[idx]['model_type']} "
                            f"(wape={rows[idx]['wape']})"
                        )
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8123")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(_parse_args().base)))
