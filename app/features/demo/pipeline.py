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
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import get_logger
from app.features.demo.schemas import DemoRunRequest, StepEvent, StepStatus

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
DEMO_SEED_START = date(2024, 10, 1)
DEMO_SEED_END = date(2024, 12, 31)

DEMO_MODEL_TYPES: tuple[str, ...] = ("naive", "seasonal_naive", "moving_average")

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


# =============================================================================
# Helpers shared across steps
# =============================================================================


def _model_config_payload(model_type: str) -> dict[str, Any]:
    """Build the ``ModelConfig`` body for a baseline ``model_type``.

    Each shape matches one branch of the discriminated union in
    ``app/features/forecasting/schemas.py`` (port of run_demo.py:301-314).
    """
    if model_type == "naive":
        return {"model_type": "naive"}
    if model_type == "seasonal_naive":
        return {"model_type": "seasonal_naive", "season_length": 7}
    if model_type == "moving_average":
        return {"model_type": "moving_average", "window_size": 7}
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


async def step_seed(ctx: DemoContext, client: _Client) -> StepResult:
    """Seed the ``demo_minimal`` scenario (skipped when ``skip_seed`` is set)."""
    if ctx.skip_seed:
        return ("skip", "skip_seed=true (assuming a seeded database)", {})
    body = await client.request(
        "seed",
        "POST",
        "/seeder/generate",
        json_body={
            "scenario": DEMO_SCENARIO,
            "seed": ctx.seed,
            "stores": DEMO_SEED_STORES,
            "products": DEMO_SEED_PRODUCTS,
            "start_date": DEMO_SEED_START.isoformat(),
            "end_date": DEMO_SEED_END.isoformat(),
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
        f"{DEMO_SCENARIO}: {DEMO_SEED_STORES} stores x {DEMO_SEED_PRODUCTS} products, "
        f"{sales} sales rows",
        {"records_created": records},
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


async def step_backtest(ctx: DemoContext, client: _Client) -> StepResult:
    """Run one backtest per model_type sequentially; pick the lowest-WAPE winner."""
    if ctx.date_start is None or ctx.date_end is None:
        return ("fail", "no date range on ctx", {})

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
        aggregated = (
            main_results.get("aggregated_metrics", {}) if isinstance(main_results, dict) else {}
        )
        clean: dict[str, float] = {}
        if isinstance(aggregated, dict):
            for k, v in aggregated.items():
                if isinstance(v, (int, float)):
                    clean[str(k)] = float(v)
        ctx.backtest_results[model_type] = clean

    winner = _select_winner(ctx.backtest_results)
    if winner is None:
        return ("fail", "no model produced a usable WAPE (all NaN?)", {})
    ctx.winner_model_type, ctx.winner_wape = winner
    return (
        "pass",
        f"{len(ctx.backtest_results)} models, winner={ctx.winner_model_type} "
        f"wape={ctx.winner_wape:.4f}",
        {
            "per_model": dict(ctx.backtest_results),
            "winner": ctx.winner_model_type,
            "winner_wape": ctx.winner_wape,
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
    """SHA-256 artifact-integrity check via the public verify endpoint."""
    if ctx.winning_run_id is None:
        return ("fail", "no winning_run_id to verify", {})
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


def _step_table() -> list[tuple[str, StepFn]]:
    """Return the ordered 11-step table (name, callable)."""
    return [
        ("precheck", step_precheck),
        ("reset", step_reset),
        ("seed", step_seed),
        ("status", step_status),
        ("features", step_features),
        ("train", step_train),
        ("backtest", step_backtest),
        ("register", step_register),
        ("verify", step_verify),
        ("agent", step_agent),
        ("cleanup", step_cleanup),
    ]


async def run_pipeline(app: FastAPI, req: DemoRunRequest) -> AsyncIterator[StepEvent]:
    """Drive the 11-step pipeline; yield one step_start + step_complete per step.

    A final ``pipeline_complete`` event always follows. Never raises -- step
    failures become ``fail`` events and stop the run after the failing step.

    Args:
        app: The live FastAPI application (driven in-process via ASGITransport).
        req: Run parameters (seed, reset, skip_seed).

    Yields:
        StepEvent instances, in execution order.
    """
    steps = _step_table()
    total = len(steps)
    ctx = DemoContext(seed=req.seed, skip_seed=req.skip_seed, reset=req.reset)
    wall_start = time.monotonic()
    any_fail = False

    async with _Client(app) as client:
        for index, (name, fn) in enumerate(steps, start=1):
            yield StepEvent(
                event_type="step_start",
                step_name=name,
                step_index=index,
                total_steps=total,
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
        },
    )
