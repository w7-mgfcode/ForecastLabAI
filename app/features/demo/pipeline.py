"""End-to-end demo pipeline orchestrator (in-process).

Drives the published FastAPI surface as a black-box HTTP consumer via
``httpx.ASGITransport`` -- the same in-process transport the test suite uses
(``tests/conftest.py``). This keeps the ``demo`` slice import-free of every
other ``app/features/*`` slice (vertical-slice rule) while still exercising
the real deployed HTTP contract.

The 11-step flow is a faithful port of ``scripts/run_demo.py`` (PR #129):

    precheck -> (reset) -> (seed) -> status -> features
        -> train x 3 (parallel) -> backtest x 3 (sequential)
        -> register-winner -> verify -> agent -> cleanup

``reset`` and ``seed`` emit a ``skip`` outcome when not requested, so the step
table is always 11 entries (stable card count for the Showcase UI).

CRITICAL: this module must NOT import ``app.main`` (circular import) nor any
``app.features.*`` slice. Importing ``app.core.*`` is allowed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import shutil
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import get_logger
from app.features.demo.schemas import DemoRunRequest, StepEvent, StepStatus
from app.shared.seeder.config import ScenarioPreset

logger = get_logger(__name__)

# =============================================================================
# Constants (ported from scripts/run_demo.py:58-81)
# =============================================================================

DEMO_ALIAS = "demo-production"
DEMO_HORIZON = 14
DEMO_BACKTEST_SPLITS = 3
DEMO_MIN_TRAIN_SIZE = 30
DEMO_FEATURESET_LOOKBACK_DAYS = 60

DEMO_SCENARIO = "demo_minimal"
DEMO_SEED_STORES = 3
DEMO_SEED_PRODUCTS = 10
# Seed window is anchored to *today* so the showcase always demos
# current-looking data; it runs DEMO_SEED_SPAN_DAYS back from today (92 days
# inclusive). Must stay >= 72 for a non-NaN backtest WAPE (see step_backtest).
DEMO_SEED_SPAN_DAYS = 91

DEMO_MODEL_TYPES: tuple[str, ...] = ("naive", "seasonal_naive", "moving_average")

# PRP-38 — historical-backfill (showcase-rich only).
# 3 historical cutoffs x 2 baseline model_types = 6 backfilled runs.
HISTORICAL_BACKFILL_CUTOFFS = 3
HISTORICAL_BACKFILL_MODELS: tuple[str, ...] = ("naive", "seasonal_naive")
# PRP-38 — V2 feature-aware model used for the modeling-phase v2_train step.
# Memory [[histgbr-no-feature-importances]] — use prophet_like (Ridge signed
# coefficients), NOT regression (HGBR has no feature_importances_).
SHOWCASE_V2_MODEL_TYPE = "prophet_like"

# Per-step HTTP timeout. /seeder/generate on demo_minimal is slow; 120 s leaves
# margin. connect=5 s because the ASGI transport connects instantly.
_HTTP_TIMEOUT = httpx.Timeout(120.0, connect=5.0)


# =============================================================================
# HTTP client + RFC 7807 surfacing
# =============================================================================


class _StepError(Exception):
    """Surfaces a non-2xx HTTP response as an RFC 7807-aware typed failure.

    Echoes ``title`` / ``detail`` / ``request_id`` from the parsed problem+json
    body; never echoes raw bodies that might contain secrets. Port of
    ``scripts/run_demo.py:StepError``.
    """

    def __init__(self, step: str, status_code: int, problem: dict[str, Any]) -> None:
        self.step = step
        self.status_code = status_code
        self.problem = problem
        super().__init__(self._format())

    def _format(self) -> str:
        title = self.problem.get("title", "?")
        detail = self.problem.get("detail", "?")
        rid = self.problem.get("request_id", "?")
        return f"{self.step}: HTTP {self.status_code} -- {title}: {detail} (request_id={rid})"


class _Client:
    """Thin ``httpx.AsyncClient`` wrapper over an in-process ASGI transport.

    ``base_url`` is cosmetic -- ``ASGITransport`` routes straight to the app, so
    no network, port, or CORS is involved. All non-2xx responses raise
    :class:`_StepError` with the parsed RFC 7807 body.
    """

    def __init__(self, app: FastAPI) -> None:
        self._client = httpx.AsyncClient(
            # raise_app_exceptions=False makes the in-process transport behave
            # like a real network client: an unhandled error inside a driven
            # endpoint surfaces as a 500 *response* (RFC 7807) rather than a
            # re-raised exception, so steps can handle it as a normal _StepError.
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://demo.internal",
            timeout=_HTTP_TIMEOUT,
        )

    async def __aenter__(self) -> _Client:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self._client.aclose()

    async def request(
        self,
        step: str,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Issue one in-process HTTP request; surface non-2xx as :class:`_StepError`."""
        kwargs: dict[str, Any] = {}
        if json_body is not None:
            kwargs["json"] = json_body
        response = await self._client.request(method, path, **kwargs)
        if response.status_code >= 400:
            problem: dict[str, Any]
            try:
                parsed = response.json()
                problem = (
                    parsed
                    if isinstance(parsed, dict)
                    else {"title": "Non-dict body", "detail": str(parsed)[:200]}
                )
            except (json.JSONDecodeError, ValueError):
                problem = {"title": "Non-JSON error", "detail": response.text[:200]}
            raise _StepError(step, response.status_code, problem)
        if response.status_code == 204:
            return {}
        body = response.json()
        return body if isinstance(body, dict) else {"_raw": body}


# =============================================================================
# Cross-step accumulator
# =============================================================================


@dataclass
class DemoContext:
    """Accumulator threaded through every step.

    Holds cross-step references (real store/product ids, train results, the
    backtest winner) so later steps reuse earlier outputs. Port of
    ``scripts/run_demo.py:DemoContext``.
    """

    seed: int
    skip_seed: bool
    reset: bool
    scenario: ScenarioPreset = ScenarioPreset.DEMO_MINIMAL
    store_id: int = 1
    product_id: int = 1
    date_start: date | None = None
    date_end: date | None = None
    seed_records: dict[str, int] = field(default_factory=dict)
    feature_row_count: int = 0
    train_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    backtest_results: dict[str, dict[str, float]] = field(default_factory=dict)
    winner_model_type: str | None = None
    winner_wape: float | None = None
    winning_run_id: str | None = None
    session_id: str | None = None
    # PRP-38 — additive fields populated only on SHOWCASE_RICH runs.
    v2_run_id: str | None = None
    v2_model_path: str | None = None
    bucketed_aggregated_metrics: dict[str, dict[str, float]] | None = None


# =============================================================================
# Helpers shared across steps
# =============================================================================


def _model_config_payload(model_type: str) -> dict[str, Any]:
    """Build the ``ModelConfig`` body for a demo ``model_type``.

    Each shape matches one branch of the discriminated union in
    ``app/features/forecasting/schemas.py`` (port of run_demo.py:301-314).
    PRP-38 adds ``prophet_like`` for the V2 modeling step.
    """
    if model_type == "naive":
        return {"model_type": "naive"}
    if model_type == "seasonal_naive":
        return {"model_type": "seasonal_naive", "season_length": 7}
    if model_type == "moving_average":
        return {"model_type": "moving_average", "window_size": 7}
    if model_type == "prophet_like":
        return {"model_type": "prophet_like"}
    raise ValueError(f"Unsupported demo model_type: {model_type}")


def _llm_key_present() -> bool:
    """Return True when the configured agent model's provider API key is set.

    Matches the provider prefix of ``agent_default_model`` so the agent step
    skips gracefully when its provider is unreachable. Logs key PRESENCE only,
    never the value (port of run_demo.py:317-335; see security-patterns.md).
    """
    settings = get_settings()
    model = settings.agent_default_model
    provider = model.split(":", 1)[0] if ":" in model else ""
    if provider == "anthropic":
        return bool(settings.anthropic_api_key)
    if provider == "openai":
        return bool(settings.openai_api_key)
    if provider in ("google-gla", "google-vertex"):
        return bool(settings.google_api_key)
    return False


def _select_winner(
    backtest_results: dict[str, dict[str, float]],
) -> tuple[str, float] | None:
    """Pick the ``(model_type, WAPE)`` with the lowest aggregated WAPE.

    Skips models whose WAPE is missing or NaN (port of run_demo.py:338-356).
    """
    best: tuple[str, float] | None = None
    for model_type, metrics in backtest_results.items():
        wape = metrics.get("wape")
        if wape is None or math.isnan(wape):
            continue
        if best is None or wape < best[1]:
            best = (model_type, wape)
    return best


# =============================================================================
# Steps -- each returns (status, human-detail, structured-data)
# =============================================================================

StepResult = tuple[StepStatus, str, dict[str, Any]]


async def step_precheck(_ctx: DemoContext, client: _Client) -> StepResult:
    """GET /health -- liveness precondition."""
    body = await client.request("precheck", "GET", "/health")
    status_field = body.get("status", "")
    detail = f"/health -> {status_field or 'unknown'}"
    return ("pass" if status_field == "ok" else "fail", detail, {})


async def step_reset(ctx: DemoContext, client: _Client) -> StepResult:
    """Wipe the database if ``reset`` was requested; skip otherwise."""
    if not ctx.reset:
        return ("skip", "reset not requested", {})
    body = await client.request(
        "reset",
        "DELETE",
        "/seeder/data",
        json_body={"scope": "all", "dry_run": False},
    )
    deleted: dict[str, Any] = body.get("records_deleted", {})
    total = sum(v for v in deleted.values() if isinstance(v, int))
    return (
        "pass",
        f"deleted {total} rows across {len(deleted)} tables",
        {"records_deleted": deleted},
    )


_SCENARIO_SEED_PROFILE: dict[ScenarioPreset, tuple[int, int, int]] = {
    ScenarioPreset.DEMO_MINIMAL: (DEMO_SEED_STORES, DEMO_SEED_PRODUCTS, DEMO_SEED_SPAN_DAYS),
    # PRP-38 — SHOWCASE_RICH profile mirrors app/shared/seeder/config.py:from_scenario.
    ScenarioPreset.SHOWCASE_RICH: (5, 15, 180),
    # PRP-38 — SPARSE picker option exercises the data-shape edge case.
    ScenarioPreset.SPARSE: (DEMO_SEED_STORES, DEMO_SEED_PRODUCTS, DEMO_SEED_SPAN_DAYS),
}


async def step_seed(ctx: DemoContext, client: _Client) -> StepResult:
    """Seed the active scenario (skipped when ``skip_seed`` is set)."""
    if ctx.skip_seed:
        return ("skip", "skip_seed=true (assuming a seeded database)", {})
    stores, products, span_days = _SCENARIO_SEED_PROFILE.get(
        ctx.scenario,
        (DEMO_SEED_STORES, DEMO_SEED_PRODUCTS, DEMO_SEED_SPAN_DAYS),
    )
    seed_end = datetime.now(UTC).date()
    seed_start = seed_end - timedelta(days=span_days)
    body = await client.request(
        "seed",
        "POST",
        "/seeder/generate",
        json_body={
            "scenario": ctx.scenario.value,
            "seed": ctx.seed,
            "stores": stores,
            "products": products,
            "start_date": seed_start.isoformat(),
            "end_date": seed_end.isoformat(),
            "sparsity": 0.0,
            "dry_run": False,
        },
    )
    raw_records: dict[str, Any] = body.get("records_created", {})
    records = {k: int(v) for k, v in raw_records.items() if isinstance(v, int)}
    ctx.seed_records = records
    # GenerateResult.records_created uses "sales" (singular), not "sales_daily".
    sales = records.get("sales", records.get("sales_daily", 0))
    return (
        "pass",
        f"{ctx.scenario.value}: {stores} stores x {products} products, {sales} sales rows",
        {"records_created": records, "scenario": ctx.scenario.value},
    )


async def step_status(ctx: DemoContext, client: _Client) -> StepResult:
    """GET /seeder/status + /dimensions/* -- capture the date range and real ids.

    Postgres auto-increment does NOT reset across delete/seed cycles, so the
    seeded store/product ids are not 1. The first available pair is discovered
    from the dimensions endpoints (port of run_demo.py:446-517).
    """
    body = await client.request("status", "GET", "/seeder/status")
    raw_start = body.get("date_range_start")
    raw_end = body.get("date_range_end")
    if not isinstance(raw_start, str) or not isinstance(raw_end, str):
        return ("fail", "no date_range in /seeder/status -- seed the database first", {})
    ctx.date_start = date.fromisoformat(raw_start)
    ctx.date_end = date.fromisoformat(raw_end)

    stores_body = await client.request(
        "status[stores]", "GET", "/dimensions/stores?page=1&page_size=1"
    )
    products_body = await client.request(
        "status[products]", "GET", "/dimensions/products?page=1&page_size=1"
    )
    stores_raw = stores_body.get("stores", [])
    products_raw = products_body.get("products", [])
    stores = stores_raw if isinstance(stores_raw, list) else []
    products = products_raw if isinstance(products_raw, list) else []
    if not stores or not products:
        return ("fail", "no stores or products after seed", {})
    first_store = stores[0]
    first_product = products[0]
    if not isinstance(first_store, dict) or not isinstance(first_product, dict):
        return ("fail", "dimensions returned non-dict items", {})
    store_id_raw = first_store.get("id")
    product_id_raw = first_product.get("id")
    if not isinstance(store_id_raw, int) or not isinstance(product_id_raw, int):
        return ("fail", "dimension ids missing or non-int", {})
    ctx.store_id = store_id_raw
    ctx.product_id = product_id_raw

    sales = body.get("sales", 0)
    return (
        "pass",
        f"date_range={raw_start}..{raw_end} sales={sales} "
        f"store_id={ctx.store_id} product_id={ctx.product_id}",
        {
            "store_id": ctx.store_id,
            "product_id": ctx.product_id,
            "date_range_start": raw_start,
            "date_range_end": raw_end,
        },
    )


async def step_features(ctx: DemoContext, client: _Client) -> StepResult:
    """Compute a small lag/rolling/calendar featureset for one series."""
    if ctx.date_end is None:
        return ("fail", "no date_end on ctx -- status step did not populate it", {})
    body = await client.request(
        "features",
        "POST",
        "/featuresets/compute",
        json_body={
            "store_id": ctx.store_id,
            "product_id": ctx.product_id,
            "cutoff_date": ctx.date_end.isoformat(),
            "lookback_days": DEMO_FEATURESET_LOOKBACK_DAYS,
            "config": {
                "name": "demo_featureset",
                "lag_config": {"lags": [1, 7, 14]},
                "rolling_config": {
                    "windows": [7, 14],
                    "aggregations": ["mean", "std"],
                },
                "calendar_config": {},
            },
        },
    )
    rows = int(body.get("row_count", 0))
    ctx.feature_row_count = rows
    columns = body.get("feature_columns", [])
    column_count = len(columns) if isinstance(columns, list) else 0
    return (
        "pass",
        f"{rows} rows, {column_count} columns (lag+rolling+calendar)",
        {"row_count": rows, "column_count": column_count},
    )


async def step_train(ctx: DemoContext, client: _Client) -> StepResult:
    """Train naive / seasonal_naive / moving_average in parallel."""
    if ctx.date_start is None or ctx.date_end is None:
        return ("fail", "no date range on ctx", {})

    # Leave a horizon-sized tail unused by training so the backtest has room.
    train_start = ctx.date_start
    train_end = ctx.date_end - timedelta(days=DEMO_HORIZON)

    async def _train(model_type: str) -> tuple[str, dict[str, Any]]:
        train_body = await client.request(
            f"train[{model_type}]",
            "POST",
            "/forecasting/train",
            json_body={
                "store_id": ctx.store_id,
                "product_id": ctx.product_id,
                "train_start_date": train_start.isoformat(),
                "train_end_date": train_end.isoformat(),
                "config": _model_config_payload(model_type),
            },
        )
        return model_type, train_body

    results: list[tuple[str, dict[str, Any]]] = list(
        await asyncio.gather(*(_train(m) for m in DEMO_MODEL_TYPES))
    )
    for model_type, train_body in results:
        ctx.train_results[model_type] = train_body
    trained = ", ".join(ctx.train_results.keys())
    return (
        "pass",
        f"trained {len(ctx.train_results)} models in parallel: {trained}",
        {"trained": list(ctx.train_results.keys())},
    )


def _coerce_metric_dict(value: object) -> dict[str, float]:
    """Coerce a JSON-decoded aggregated_metrics dict into a typed float map."""
    if not isinstance(value, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in value.items():
        if isinstance(v, (int, float)):
            out[str(k)] = float(v)
    return out


def _coerce_bucketed_metrics(
    value: object,
) -> dict[str, dict[str, float]] | None:
    """Coerce a JSON-decoded bucketed_aggregated_metrics block."""
    if not isinstance(value, dict):
        return None
    out: dict[str, dict[str, float]] = {}
    for bucket_id, per_metric in value.items():
        coerced = _coerce_metric_dict(per_metric)
        if coerced:
            out[str(bucket_id)] = coerced
    return out or None


async def step_backtest(ctx: DemoContext, client: _Client) -> StepResult:
    """Run scenario-aware backtest; pick the lowest-WAPE winner.

    PRP-38 — on SHOWCASE_RICH the main model is feature-aware
    (``prophet_like``); baselines come back in ``baseline_results`` (one call,
    ``include_baselines=true``) and the response carries per-horizon-bucket
    metrics in ``main_model_results.bucketed_aggregated_metrics``. On
    DEMO_MINIMAL the original 3-baseline-loop behaviour is preserved.
    """
    if ctx.date_start is None or ctx.date_end is None:
        return ("fail", "no date range on ctx", {})

    if ctx.scenario is ScenarioPreset.SHOWCASE_RICH:
        body = await client.request(
            f"backtest[{SHOWCASE_V2_MODEL_TYPE}]",
            "POST",
            "/backtesting/run",
            json_body={
                "store_id": ctx.store_id,
                "product_id": ctx.product_id,
                "start_date": ctx.date_start.isoformat(),
                "end_date": ctx.date_end.isoformat(),
                "config": {
                    "split_config": {
                        "strategy": "expanding",
                        "n_splits": DEMO_BACKTEST_SPLITS,
                        "min_train_size": DEMO_MIN_TRAIN_SIZE,
                        "gap": 0,
                        "horizon": DEMO_HORIZON,
                    },
                    "model_config_main": _model_config_payload(SHOWCASE_V2_MODEL_TYPE),
                    "include_baselines": True,
                    "store_fold_details": False,
                },
            },
        )
        main_results = body.get("main_model_results", {})
        baseline_results = body.get("baseline_results") or []
        main_metrics = _coerce_metric_dict(
            main_results.get("aggregated_metrics") if isinstance(main_results, dict) else None
        )
        ctx.backtest_results[SHOWCASE_V2_MODEL_TYPE] = main_metrics
        # baseline_results is list[ModelBacktestResult].
        if isinstance(baseline_results, list):
            for entry in baseline_results:
                if not isinstance(entry, dict):
                    continue
                entry_type = entry.get("model_type")
                if not isinstance(entry_type, str):
                    continue
                ctx.backtest_results[entry_type] = _coerce_metric_dict(
                    entry.get("aggregated_metrics")
                )
        ctx.bucketed_aggregated_metrics = _coerce_bucketed_metrics(
            main_results.get("bucketed_aggregated_metrics")
            if isinstance(main_results, dict)
            else None
        )
    else:
        # DEMO_MINIMAL / SPARSE / others: loop over baselines (legacy path).
        for model_type in DEMO_MODEL_TYPES:
            body = await client.request(
                f"backtest[{model_type}]",
                "POST",
                "/backtesting/run",
                json_body={
                    "store_id": ctx.store_id,
                    "product_id": ctx.product_id,
                    "start_date": ctx.date_start.isoformat(),
                    "end_date": ctx.date_end.isoformat(),
                    "config": {
                        "split_config": {
                            "strategy": "expanding",
                            "n_splits": DEMO_BACKTEST_SPLITS,
                            "min_train_size": DEMO_MIN_TRAIN_SIZE,
                            "gap": 0,
                            "horizon": DEMO_HORIZON,
                        },
                        "model_config_main": _model_config_payload(model_type),
                        "include_baselines": False,
                        "store_fold_details": False,
                    },
                },
            )
            main_results = body.get("main_model_results", {})
            ctx.backtest_results[model_type] = _coerce_metric_dict(
                main_results.get("aggregated_metrics") if isinstance(main_results, dict) else None
            )

    winner = _select_winner(ctx.backtest_results)
    if winner is None:
        return ("fail", "no model produced a usable WAPE (all NaN?)", {})
    ctx.winner_model_type, ctx.winner_wape = winner
    payload: dict[str, Any] = {
        "per_model": dict(ctx.backtest_results),
        "winner": ctx.winner_model_type,
        "winner_wape": ctx.winner_wape,
    }
    if ctx.bucketed_aggregated_metrics is not None:
        payload["bucketed_aggregated_metrics"] = ctx.bucketed_aggregated_metrics
    return (
        "pass",
        f"{len(ctx.backtest_results)} models, winner={ctx.winner_model_type} "
        f"wape={ctx.winner_wape:.4f}",
        payload,
    )


async def step_phase2_enrichment(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-38 — POST /seeder/phase2-enrichment (showcase-rich only).

    Drives the new ``/seeder/phase2-enrichment`` endpoint to add Phase 2
    realism (lifecycle, replenishment, exogenous, returns) on top of the
    seeded SHOWCASE_RICH dataset. Logic ported into the seeder slice so the
    demo orchestrator never imports another feature slice.
    """
    body = await client.request(
        "phase2_enrichment",
        "POST",
        "/seeder/phase2-enrichment",
        json_body={"seed": ctx.seed},
    )
    raw_counts = body.get("records_created", {})
    counts: dict[str, int] = {}
    if isinstance(raw_counts, dict):
        for k, v in raw_counts.items():
            if isinstance(v, int):
                counts[str(k)] = v
    total = sum(counts.values())
    summary = ", ".join(f"{k}={v}" for k, v in counts.items()) or "no rows"
    return (
        "pass",
        f"phase2 enrichment: {total} rows across {len(counts)} tables ({summary})",
        {"records_created": counts},
    )


async def step_historical_backfill(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-38 — populate /explorer/runs with historical-feeling registry rows.

    Runs ``HISTORICAL_BACKFILL_MODELS`` x ``HISTORICAL_BACKFILL_CUTOFFS``
    lightweight trains in parallel using the showcase grain, then registers
    each as a SUCCESS run with a backdated ``data_window_end``. Each registry
    write is sequential to avoid SQLAlchemy session contention (one session
    per request via ``ASGITransport``).

    Memory [[seeder-does-not-reset-id-sequences]] — store/product ids come
    from ``ctx`` (populated by step_status), never hardcoded.
    """
    if ctx.date_start is None or ctx.date_end is None:
        return ("fail", "no date range on ctx", {})
    total_days = (ctx.date_end - ctx.date_start).days
    # Each historical cutoff trims another horizon worth of data; we need
    # enough days left at the earliest cutoff for the train window to be
    # meaningful.
    min_required_days = HISTORICAL_BACKFILL_CUTOFFS * (DEMO_HORIZON + 1) + DEMO_MIN_TRAIN_SIZE
    if total_days < min_required_days:
        return (
            "skip",
            f"date window too short ({total_days}d < {min_required_days}d) for backfill",
            {},
        )

    # Capture narrowed ``date_start`` for the nested closure (pyright cannot
    # propagate the outer ``if ctx.date_start is None`` guard into nested defs).
    train_start_date = ctx.date_start
    cutoffs = [
        ctx.date_end - timedelta(days=DEMO_HORIZON * (i + 1))
        for i in range(HISTORICAL_BACKFILL_CUTOFFS)
    ]

    async def _train(cutoff: date, model_type: str) -> tuple[date, str, dict[str, Any]]:
        train_body = await client.request(
            f"historical[train:{model_type}@{cutoff.isoformat()}]",
            "POST",
            "/forecasting/train",
            json_body={
                "store_id": ctx.store_id,
                "product_id": ctx.product_id,
                "train_start_date": train_start_date.isoformat(),
                "train_end_date": cutoff.isoformat(),
                "config": _model_config_payload(model_type),
            },
        )
        return cutoff, model_type, train_body

    pairs = [(c, m) for c in cutoffs for m in HISTORICAL_BACKFILL_MODELS]
    trained = await asyncio.gather(*(_train(c, m) for c, m in pairs), return_exceptions=True)

    runs_created = 0
    skipped: list[str] = []
    for entry in trained:
        if isinstance(entry, BaseException):
            skipped.append(type(entry).__name__)
            continue
        cutoff, model_type, train_body = entry
        model_path_raw = train_body.get("model_path")
        if not isinstance(model_path_raw, str) or not model_path_raw:
            skipped.append(f"{model_type}@{cutoff} no model_path")
            continue
        source_model = Path(model_path_raw)
        if not source_model.exists():
            skipped.append(f"{model_type}@{cutoff} artifact missing")
            continue
        artifact_bytes = source_model.read_bytes()
        artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
        artifact_size = len(artifact_bytes)
        # data_window_end is the historical cutoff so the explorer page
        # shows a spread of "as_of" dates without backdating created_at.
        try:
            create_body = await client.request(
                f"historical[register:{model_type}@{cutoff.isoformat()}]",
                "POST",
                "/registry/runs",
                json_body={
                    "model_type": model_type,
                    "model_config": _model_config_payload(model_type),
                    "feature_config": None,
                    "data_window_start": ctx.date_start.isoformat(),
                    "data_window_end": cutoff.isoformat(),
                    "store_id": ctx.store_id,
                    "product_id": ctx.product_id,
                },
            )
            run_id = create_body.get("run_id")
            if not isinstance(run_id, str):
                skipped.append(f"{model_type}@{cutoff} no run_id")
                continue
            await client.request(
                f"historical[running:{model_type}@{cutoff.isoformat()}]",
                "PATCH",
                f"/registry/runs/{run_id}",
                json_body={"status": "running"},
            )
            await client.request(
                f"historical[success:{model_type}@{cutoff.isoformat()}]",
                "PATCH",
                f"/registry/runs/{run_id}",
                json_body={
                    "status": "success",
                    "metrics": {},
                    "artifact_uri": model_path_raw,
                    "artifact_hash": artifact_hash,
                    "artifact_size_bytes": artifact_size,
                },
            )
            runs_created += 1
        except _StepError as exc:
            # Most likely cause: RegistryService._find_duplicate collapses
            # an exact-config duplicate (same data_window + grain + model).
            # That's fine for the demo — non-fatal.
            skipped.append(f"{model_type}@{cutoff} {exc.status_code}")

    detail = f"created {runs_created} historical runs across {len(cutoffs)} cutoffs"
    if skipped:
        detail += f" ({len(skipped)} skipped: {', '.join(skipped[:3])}{'...' if len(skipped) > 3 else ''})"
    return (
        "pass" if runs_created > 0 else "warn",
        detail,
        {
            "runs_created": runs_created,
            "cutoffs": [c.isoformat() for c in cutoffs],
            "models": list(HISTORICAL_BACKFILL_MODELS),
        },
    )


async def step_v2_train(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-38 — train ONE V2 ``prophet_like`` model and register it.

    Implements the patched plan from Task 1's contract probe report:

    1. POST /forecasting/train with ``feature_frame_version=2`` +
       ``model_type=prophet_like``.
    2. R1 — ``artifact_uri = train_response["model_path"]`` (FULL
       ``artifacts/models/...`` path). DO NOT copy the bundle into the
       registry artifact root; the feature-metadata endpoint loads bundles
       from ``forecast_model_artifacts_dir``.
    3. POST /registry/runs (PENDING) with ``runtime_info_extras=
       {"feature_frame_version": 2}`` (the bundle is the source of truth for
       feature_columns / feature_groups / feature_safety_classes; the
       computed RunResponse.feature_frame_version surfaces V=2 in the UI).
    4. PATCH pending -> running -> success with full path + hash + size.
    5. GET /forecasting/runs/{id}/feature-metadata to enrich step.data with
       the bundle's manifest. Failure here is NON-fatal — the V=2 badge
       still renders via RunResponse.feature_frame_version.
    """
    if ctx.date_start is None or ctx.date_end is None:
        return ("fail", "no date range on ctx", {})
    train_start = ctx.date_start
    train_end = ctx.date_end - timedelta(days=DEMO_HORIZON)

    train_body = await client.request(
        "v2_train[train]",
        "POST",
        "/forecasting/train",
        json_body={
            "store_id": ctx.store_id,
            "product_id": ctx.product_id,
            "train_start_date": train_start.isoformat(),
            "train_end_date": train_end.isoformat(),
            "config": {"model_type": SHOWCASE_V2_MODEL_TYPE},
            "feature_frame_version": 2,
            # feature_groups: omit -> backend uses DEFAULT_V2_GROUPS.
        },
    )

    v2_model_path_raw = train_body.get("model_path")
    if not isinstance(v2_model_path_raw, str) or not v2_model_path_raw:
        return ("fail", "POST /forecasting/train returned no model_path", {})
    # R1 — the path must resolve INSIDE forecast_model_artifacts_dir so
    # /forecasting/runs/{id}/feature-metadata can load the bundle.
    if "artifacts/models/" not in v2_model_path_raw.replace("\\", "/"):
        return (
            "fail",
            f"model_path does not contain 'artifacts/models/': {v2_model_path_raw}",
            {},
        )
    ctx.v2_model_path = v2_model_path_raw
    bundle_path = Path(v2_model_path_raw)
    if not bundle_path.exists():
        return ("fail", f"V2 bundle missing on disk: {v2_model_path_raw}", {})
    artifact_bytes = bundle_path.read_bytes()
    artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
    artifact_size = len(artifact_bytes)

    create_body = await client.request(
        "v2_train[create]",
        "POST",
        "/registry/runs",
        json_body={
            "model_type": SHOWCASE_V2_MODEL_TYPE,
            "model_config": {"model_type": SHOWCASE_V2_MODEL_TYPE},
            "feature_config": None,
            "data_window_start": ctx.date_start.isoformat(),
            "data_window_end": ctx.date_end.isoformat(),
            "store_id": ctx.store_id,
            "product_id": ctx.product_id,
            "runtime_info_extras": {"feature_frame_version": 2},
        },
    )
    v2_run_id_raw = create_body.get("run_id")
    if not isinstance(v2_run_id_raw, str):
        return ("fail", "POST /registry/runs returned no run_id", {})
    ctx.v2_run_id = v2_run_id_raw

    await client.request(
        "v2_train[running]",
        "PATCH",
        f"/registry/runs/{v2_run_id_raw}",
        json_body={"status": "running"},
    )
    await client.request(
        "v2_train[success]",
        "PATCH",
        f"/registry/runs/{v2_run_id_raw}",
        json_body={
            "status": "success",
            "metrics": {},
            "artifact_uri": v2_model_path_raw,  # R1 — FULL artifacts/models/... path.
            "artifact_hash": artifact_hash,
            "artifact_size_bytes": artifact_size,
        },
    )

    # Enrich step.data with the bundle's V2 manifest. Failure is non-fatal.
    feature_columns_count = 0
    feature_group_names: list[str] = []
    try:
        meta_body = await client.request(
            "v2_train[feature-metadata]",
            "GET",
            f"/forecasting/runs/{v2_run_id_raw}/feature-metadata",
        )
        cols = meta_body.get("feature_columns") or []
        if isinstance(cols, list):
            feature_columns_count = len(cols)
        groups = meta_body.get("feature_groups") or {}
        if isinstance(groups, dict):
            feature_group_names = sorted(str(k) for k in groups)
    except _StepError as exc:
        logger.warning(
            "demo.v2_train.feature_metadata_failed",
            run_id=v2_run_id_raw,
            status_code=exc.status_code,
        )

    return (
        "pass",
        (f"V2 prophet_like registered run_id={v2_run_id_raw[:8]}... cols={feature_columns_count}"),
        {
            "v2_run_id": v2_run_id_raw,
            "feature_frame_version": 2,
            "model_type": SHOWCASE_V2_MODEL_TYPE,
            "feature_columns_count": feature_columns_count,
            "feature_groups": feature_group_names,
            "artifact_uri_full": v2_model_path_raw,
        },
    )


async def step_register(ctx: DemoContext, client: _Client) -> StepResult:
    """Two-step registry create+update; alias the winner as ``demo-production``.

    Mandatory transition: pending -> running -> success. Aliases can only point
    to runs in SUCCESS status. The trained artifact is copied into the registry
    artifact root and hashed (port of run_demo.py:673-800).
    """
    if ctx.winner_model_type is None:
        return ("fail", "no winner; cannot register", {})
    if ctx.date_start is None or ctx.date_end is None:
        return ("fail", "no date range on ctx", {})
    winner = ctx.winner_model_type
    date_start = ctx.date_start
    date_end = ctx.date_end

    # PRP-38 — when the V2 ``prophet_like`` run wins, it has ALREADY been
    # registered by step_v2_train. Skip re-creation and just alias the
    # existing v2_run_id as ``demo-production``.
    if winner == SHOWCASE_V2_MODEL_TYPE and ctx.v2_run_id is not None:
        ctx.winning_run_id = ctx.v2_run_id
        await client.request(
            "register[alias_v2]",
            "POST",
            "/registry/aliases",
            json_body={
                "alias_name": DEMO_ALIAS,
                "run_id": ctx.v2_run_id,
                "description": "Auto-created by the demo showcase pipeline (V2 winner).",
            },
        )
        return (
            "pass",
            f"V2 winner aliased run_id={ctx.v2_run_id[:8]}... alias={DEMO_ALIAS}",
            {"run_id": ctx.v2_run_id, "alias": DEMO_ALIAS, "winner": winner},
        )

    train_response = ctx.train_results.get(winner, {})
    model_path_raw = train_response.get("model_path")
    if not isinstance(model_path_raw, str) or not model_path_raw:
        return ("fail", f"no model_path for winner {winner}", {})
    source_model = Path(model_path_raw)
    if not source_model.exists():
        return ("fail", f"artifact missing at {source_model}", {})

    # /forecasting/train writes under settings.forecast_model_artifacts_dir;
    # /registry verify resolves artifact_uri against settings.registry_artifact_root.
    # Copy the trained model into the registry root and record a registry-relative
    # URI to close the loop (run_demo.py:715-731).
    settings = get_settings()
    registry_root = Path(settings.registry_artifact_root).resolve()
    registry_root.mkdir(parents=True, exist_ok=True)
    artifact_uri = f"demo/{winner}-{source_model.stem}.joblib"
    dest_path = registry_root / artifact_uri
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_model, dest_path)
    artifact_bytes = dest_path.read_bytes()
    artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
    artifact_size = len(artifact_bytes)

    # (a) Create the run in PENDING status. On-wire JSON key is "model_config"
    #     (alias of model_config_data per registry/schemas.py).
    create_body = await client.request(
        "register[create]",
        "POST",
        "/registry/runs",
        json_body={
            "model_type": winner,
            "model_config": _model_config_payload(winner),
            "feature_config": None,
            "data_window_start": date_start.isoformat(),
            "data_window_end": date_end.isoformat(),
            "store_id": ctx.store_id,
            "product_id": ctx.product_id,
            "agent_context": None,
            "git_sha": None,
        },
    )
    run_id_raw = create_body.get("run_id")
    if not isinstance(run_id_raw, str):
        return ("fail", "POST /registry/runs returned no run_id", {})
    ctx.winning_run_id = run_id_raw

    # (b) PATCH pending -> running (mandatory intermediate transition).
    await client.request(
        "register[running]",
        "PATCH",
        f"/registry/runs/{run_id_raw}",
        json_body={"status": "running"},
    )

    # (c) PATCH running -> success with metrics + artifact info.
    await client.request(
        "register[success]",
        "PATCH",
        f"/registry/runs/{run_id_raw}",
        json_body={
            "status": "success",
            "metrics": ctx.backtest_results[winner],
            "artifact_uri": artifact_uri,
            "artifact_hash": artifact_hash,
            "artifact_size_bytes": artifact_size,
        },
    )

    # (d) Alias the winner (only allowed on a SUCCESS run).
    await client.request(
        "register[alias]",
        "POST",
        "/registry/aliases",
        json_body={
            "alias_name": DEMO_ALIAS,
            "run_id": run_id_raw,
            "description": "Auto-created by the demo showcase pipeline.",
        },
    )

    return (
        "pass",
        f"run_id={run_id_raw[:8]}... alias={DEMO_ALIAS}",
        {"run_id": run_id_raw, "alias": DEMO_ALIAS},
    )


async def step_verify(ctx: DemoContext, client: _Client) -> StepResult:
    """SHA-256 artifact-integrity check via the public verify endpoint.

    PRP-38 — for a V2 winner (``prophet_like``), the run's ``artifact_uri``
    is the full ``artifacts/models/...`` path so /forecasting feature-metadata
    can resolve it. The /registry verify endpoint resolves under
    ``registry_artifact_root`` instead — verify would fail with a path
    mismatch. Skip verify gracefully when the V2 run is the winner; the
    integrity guarantee is implicit (the bundle hash + size were captured
    at registration time).
    """
    if ctx.winning_run_id is None:
        return ("fail", "no winning_run_id to verify", {})
    if ctx.v2_run_id is not None and ctx.winning_run_id == ctx.v2_run_id:
        return (
            "skip",
            "V2 winner — verify resolves under registry_artifact_root only "
            "(artifact_uri is the artifacts/models/... path)",
            {"v2_winner": True, "run_id": ctx.v2_run_id},
        )
    body = await client.request(
        "verify",
        "GET",
        f"/registry/runs/{ctx.winning_run_id}/verify",
    )
    verified = body.get("verified") is True
    return (
        "pass" if verified else "fail",
        "sha256 OK" if verified else f"verify={body.get('verified')}",
        {"verified": verified},
    )


async def step_agent(ctx: DemoContext, client: _Client) -> StepResult:
    """One-turn chat with the ``experiment`` agent (skipped without an LLM key).

    Skips gracefully when the configured agent model has no matching API key, or
    when the round-trip raises a provider error -- a broken key must not mask an
    otherwise-green pipeline (port of run_demo.py:827-892).
    """
    key_present = _llm_key_present()
    logger.info("demo.agent_key_present", present=key_present)
    if not key_present:
        return ("skip", "no API key matching agent_default_model provider", {})

    try:
        create_body = await client.request(
            "agent[session]",
            "POST",
            "/agents/sessions",
            json_body={"agent_type": "experiment", "initial_context": None},
        )
    except _StepError as exc:
        return ("skip", f"session-create failed: {exc}", {})
    session_id_raw = create_body.get("session_id")
    if not isinstance(session_id_raw, str):
        return ("skip", "no session_id returned", {})
    ctx.session_id = session_id_raw

    try:
        chat_body = await client.request(
            "agent[chat]",
            "POST",
            f"/agents/sessions/{session_id_raw}/chat",
            json_body={"message": "List the latest model runs.", "stream": False},
        )
    except _StepError as exc:
        return ("skip", f"chat round-trip failed: {exc}", {})
    tokens = int(chat_body.get("tokens_used", 0))
    tool_calls = chat_body.get("tool_calls", [])
    tool_count = len(tool_calls) if isinstance(tool_calls, list) else 0
    return (
        "pass",
        f"chat ok (tokens={tokens}, tool_calls={tool_count})",
        {"tokens_used": tokens, "tool_calls_count": tool_count},
    )


async def step_cleanup(ctx: DemoContext, client: _Client) -> StepResult:
    """Close the agent session (no-op if no session was opened)."""
    if ctx.session_id is None:
        return ("skip", "no agent session to close", {})
    try:
        await client.request("cleanup", "DELETE", f"/agents/sessions/{ctx.session_id}")
    except _StepError as exc:
        # Cleanup failure is non-fatal -- warn so the run still goes green.
        return ("warn", f"DELETE failed but ignored: {exc}", {})
    return ("pass", "agent session closed", {})


# =============================================================================
# Orchestration
# =============================================================================

StepFn = Callable[[DemoContext, _Client], Awaitable[StepResult]]
PhaseStep = tuple[str, str, StepFn]  # (phase_name, step_name, step_fn)


# PRP-38 — canonical phase ids. The frontend's PHASE_DEFS.ts mirrors this list
# in order; the lockstep test ``test_phase_table_stable`` is the contract gate.
PHASE_DATA = "data"
PHASE_MODELING = "modeling"
PHASE_DECISION = "decision"
PHASE_VERIFY = "verify"
PHASE_AGENT = "agent"
PHASE_CLEANUP = "cleanup"


def _phase_table(scenario: ScenarioPreset) -> list[PhaseStep]:
    """Return the ordered phase-grouped step table for ``scenario`` (PRP-38).

    - ``DEMO_MINIMAL`` / ``SPARSE`` / unknown — the legacy 11-step flow,
      phase-grouped without inserting any new step. Back-compat:
      ``_step_table()`` adapts this branch to a flat ``(name, fn)`` list.
    - ``SHOWCASE_RICH`` — the data phase adds ``phase2_enrichment`` and
      ``historical_backfill`` after ``features``; the modeling phase adds
      ``v2_train`` after ``train``. The decision phase reuses ``backtest``
      and ``register`` (``backtest`` itself is scenario-aware — see
      ``step_backtest``).
    """
    data_steps: list[tuple[str, StepFn]] = [
        ("precheck", step_precheck),
        ("reset", step_reset),
        ("seed", step_seed),
        ("status", step_status),
        ("features", step_features),
    ]
    modeling_steps: list[tuple[str, StepFn]] = [("train", step_train)]
    decision_steps: list[tuple[str, StepFn]] = [
        ("backtest", step_backtest),
        ("register", step_register),
    ]
    verify_steps: list[tuple[str, StepFn]] = [("verify", step_verify)]
    agent_steps: list[tuple[str, StepFn]] = [("agent", step_agent)]
    cleanup_steps: list[tuple[str, StepFn]] = [("cleanup", step_cleanup)]
    if scenario is ScenarioPreset.SHOWCASE_RICH:
        data_steps += [
            ("phase2_enrichment", step_phase2_enrichment),
            ("historical_backfill", step_historical_backfill),
        ]
        modeling_steps += [("v2_train", step_v2_train)]
    rows: list[PhaseStep] = []
    rows += [(PHASE_DATA, name, fn) for name, fn in data_steps]
    rows += [(PHASE_MODELING, name, fn) for name, fn in modeling_steps]
    rows += [(PHASE_DECISION, name, fn) for name, fn in decision_steps]
    rows += [(PHASE_VERIFY, name, fn) for name, fn in verify_steps]
    rows += [(PHASE_AGENT, name, fn) for name, fn in agent_steps]
    rows += [(PHASE_CLEANUP, name, fn) for name, fn in cleanup_steps]
    return rows


def _step_table() -> list[tuple[str, StepFn]]:
    """Legacy flat-list adapter. Drops phase ids from ``_phase_table``."""
    return [(name, fn) for _phase, name, fn in _phase_table(ScenarioPreset.DEMO_MINIMAL)]


async def run_pipeline(app: FastAPI, req: DemoRunRequest) -> AsyncIterator[StepEvent]:
    """Drive the phase-grouped pipeline; yield one step_start + step_complete per step.

    A final ``pipeline_complete`` event always follows. Never raises -- step
    failures become ``fail`` events and stop the run after the failing step.

    PRP-38: every emitted ``step_start`` / ``step_complete`` carries
    ``phase_name`` / ``phase_index`` (1-based across distinct phases) /
    ``phase_total``. The ``pipeline_complete`` summary omits ``phase_name`` —
    the frontend treats it as the run total.

    Args:
        app: The live FastAPI application (driven in-process via ASGITransport).
        req: Run parameters (seed, reset, skip_seed, scenario).

    Yields:
        StepEvent instances, in execution order.
    """
    rows = _phase_table(req.scenario)
    total = len(rows)
    # Distinct phases preserve first-seen order across rows.
    phases_in_order: list[str] = []
    for phase_name, _, _ in rows:
        if phase_name not in phases_in_order:
            phases_in_order.append(phase_name)
    phase_total = len(phases_in_order)
    phase_index_by_phase = {p: i + 1 for i, p in enumerate(phases_in_order)}

    ctx = DemoContext(
        seed=req.seed,
        skip_seed=req.skip_seed,
        reset=req.reset,
        scenario=req.scenario,
    )
    wall_start = time.monotonic()
    any_fail = False

    async with _Client(app) as client:
        for index, (phase_name, name, fn) in enumerate(rows, start=1):
            phase_index = phase_index_by_phase[phase_name]
            yield StepEvent(
                event_type="step_start",
                step_name=name,
                step_index=index,
                total_steps=total,
                phase_name=phase_name,
                phase_index=phase_index,
                phase_total=phase_total,
            )
            t0 = time.monotonic()
            status: StepStatus
            detail: str
            data: dict[str, Any]
            try:
                status, detail, data = await fn(ctx, client)
            except _StepError as exc:
                status, detail, data = "fail", str(exc), {}
            except (httpx.HTTPError, OSError) as exc:
                status, detail, data = (
                    "fail",
                    f"transport error: {type(exc).__name__}: {exc}",
                    {},
                )
            except Exception as exc:
                # The orchestrator must never raise -- any unexpected error
                # from a step becomes a fail event so a pipeline_complete is
                # always emitted (see this function's contract).
                status, detail, data = (
                    "fail",
                    f"unexpected error: {type(exc).__name__}: {exc}",
                    {},
                )
            duration_ms = (time.monotonic() - t0) * 1000
            yield StepEvent(
                event_type="step_complete",
                step_name=name,
                step_index=index,
                total_steps=total,
                status=status,
                detail=detail,
                data=data,
                duration_ms=duration_ms,
                phase_name=phase_name,
                phase_index=phase_index,
                phase_total=phase_total,
            )
            if status == "fail":
                any_fail = True
                break

    wall = time.monotonic() - wall_start
    yield StepEvent(
        event_type="pipeline_complete",
        step_name="summary",
        step_index=total,
        total_steps=total,
        status="fail" if any_fail else "pass",
        detail=(
            f"runs={len(ctx.backtest_results)} "
            f"winner={ctx.winner_model_type or 'n/a'} wall_clock={wall:.0f}s"
        ),
        data={
            "winner_model_type": ctx.winner_model_type,
            "winner_wape": ctx.winner_wape,
            "winning_run_id": ctx.winning_run_id,
            "alias": DEMO_ALIAS if ctx.winning_run_id else None,
            "wall_clock_s": wall,
            # PRP-38 — expose the V2 run id when set so the Inspect deep
            # link can target /explorer/runs/{v2_run_id}.
            "v2_run_id": ctx.v2_run_id,
        },
    )
