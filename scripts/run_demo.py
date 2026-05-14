#!/usr/bin/env python
"""ForecastLabAI end-to-end demo pipeline driver.

Drives the published FastAPI surface as a black-box HTTP consumer:

    precheck -> (reset) -> seed -> status -> features
        -> train x 3 (parallel) -> backtest x 3 (sequential)
        -> register-winner -> verify -> agent -> cleanup

The script consumes only the documented HTTP contract (see
``docs/_base/API_CONTRACTS.md``); it never imports from ``app.features.*``
services so any drift between the deployed surface and the runtime
behavior surfaces as a real failure.

Usage:
    # Full e2e (default scenario seed)
    uv run python scripts/run_demo.py --seed 42

    # Skip the seeder step (assumes data already present)
    uv run python scripts/run_demo.py --seed 42 --skip-seed

    # Wipe the DB before seeding (destructive)
    uv run python scripts/run_demo.py --seed 42 --reset

    # CI / log-capture mode (one line per step)
    uv run python scripts/run_demo.py --seed 42 --quiet

Exit codes:
    0 -- green verdict (or green with soft-warn for wall-clock budget)
    1 -- one or more steps failed
    2 -- precondition failure (API unreachable, DB down, etc.)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Final

import httpx

from app.core.config import get_settings

# =============================================================================
# Constants
# =============================================================================

DEFAULT_API_URL: Final[str] = "http://localhost:8123"
DEFAULT_TIMEOUT_S: Final[float] = 60.0
DEFAULT_SEED: Final[int] = 42

DEMO_ALIAS: Final[str] = "demo-production"
DEMO_STORE_ID: Final[int] = 1
DEMO_PRODUCT_ID: Final[int] = 1
DEMO_HORIZON: Final[int] = 14
DEMO_BACKTEST_SPLITS: Final[int] = 3
DEMO_MIN_TRAIN_SIZE: Final[int] = 30
DEMO_WALL_CLOCK_BUDGET_S: Final[float] = 180.0
DEMO_FEATURESET_LOOKBACK_DAYS: Final[int] = 60

DEMO_SCENARIO: Final[str] = "demo_minimal"
DEMO_SEED_STORES: Final[int] = 3
DEMO_SEED_PRODUCTS: Final[int] = 10
DEMO_SEED_START: Final[date] = date(2024, 10, 1)
DEMO_SEED_END: Final[date] = date(2024, 12, 31)

DEMO_MODEL_TYPES: Final[tuple[str, ...]] = ("naive", "seasonal_naive", "moving_average")

GLYPHS: Final[dict[str, str]] = {
    "pass": "✅",
    "fail": "❌",
    "warn": "⚠️",
    "skip": "⏭️",
    "run": "\U0001f504",
}


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class DemoArgs:
    """Parsed CLI arguments."""

    seed: int
    skip_seed: bool
    reset: bool
    quiet: bool
    api_url: str
    timeout: float


@dataclass
class StepOutcome:
    """One step's result for the summary block."""

    name: str
    status: str  # "pass" | "fail" | "skip" | "warn"
    detail: str
    duration_ms: float


@dataclass
class DemoContext:
    """Accumulator threaded through every step.

    Holds cross-step references (store_id, product_id, train run_ids, winner)
    so later steps can use earlier outputs without re-reading the API. The
    script never mutates server-side state via this struct -- it is a
    read-side cache only.
    """

    api_url: str
    seed: int
    skip_seed: bool
    reset: bool
    quiet: bool
    timeout: float
    store_id: int = DEMO_STORE_ID
    product_id: int = DEMO_PRODUCT_ID
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
    wall_clock_start: float = 0.0


# =============================================================================
# HTTP client + RFC 7807 surfacing
# =============================================================================


class StepError(Exception):
    """Surfaces a non-2xx HTTP response as an RFC 7807-aware typed failure.

    Echoes ``title`` / ``detail`` / ``request_id`` from the parsed
    problem+json body (per ``app/core/problem_details.py``); never echoes
    raw bodies that might contain secrets.
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


class HttpClient:
    """Thin ``httpx.AsyncClient`` wrapper.

    httpx's default 5-second timeout is too short for ``/seeder/generate``
    (can take ~10-20 s for ``demo_minimal``), so callers pass an explicit
    per-client timeout. All non-2xx responses raise ``StepError`` with the
    parsed RFC 7807 body.
    """

    def __init__(self, base_url: str, timeout: float) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout, connect=5.0),
        )

    async def __aenter__(self) -> HttpClient:
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
        """Issue one HTTP request; surface non-2xx as :class:`StepError`."""
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
            raise StepError(step, response.status_code, problem)
        if response.status_code == 204:
            return {}
        body = response.json()
        return body if isinstance(body, dict) else {"_raw": body}


# =============================================================================
# Reporter (output-formatting.md compliant)
# =============================================================================


class Reporter:
    """Per-step + final-summary output.

    Honors ``.claude/rules/output-formatting.md``: ASCII glyphs, box-drawing
    separators, capped at 40 lines. ``--quiet`` collapses each step to a
    single line for CI/log capture.
    """

    def __init__(self, *, quiet: bool, total_steps: int) -> None:
        self._quiet = quiet
        self._total = total_steps
        self._index = 0

    def header(self) -> None:
        if self._quiet:
            return
        line = "━" * 44
        print(line)
        print("  \U0001f50d ForecastLabAI Demo")
        print(line)

    def record(self, outcome: StepOutcome) -> None:
        self._index += 1
        glyph = GLYPHS.get(outcome.status, "?")
        if self._quiet:
            print(f"{glyph} {outcome.name}: {outcome.detail} ({outcome.duration_ms:.0f}ms)")
        else:
            print(
                f"{glyph} Step {self._index:2d}/{self._total}: {outcome.name} -- {outcome.detail}"
            )

    def summary(
        self,
        outcomes: list[StepOutcome],
        ctx: DemoContext,
        wall_clock_s: float,
    ) -> bool:
        line = "─" * 44
        any_fail = any(o.status == "fail" for o in outcomes)
        within_budget = wall_clock_s <= DEMO_WALL_CLOCK_BUDGET_S
        if not self._quiet:
            print(line)
            if any_fail:
                failed = sum(1 for o in outcomes if o.status == "fail")
                print(f"  {GLYPHS['fail']} Result: NOT READY -- {failed} step(s) failed")
            elif within_budget:
                print(f"  {GLYPHS['pass']} Result: GREEN")
            else:
                print(
                    f"  {GLYPHS['warn']} Result: GREEN "
                    f"(over budget {wall_clock_s:.0f}s > "
                    f"{int(DEMO_WALL_CLOCK_BUDGET_S)}s)"
                )
            print(line)
        # Always emit the canonical final line so CI / scripts can grep for it.
        winner = ctx.winner_model_type or "n/a"
        print(
            f"runs={len(ctx.backtest_results)} winner={winner} "
            f"alias={DEMO_ALIAS} wall_clock={wall_clock_s:.0f}s"
        )
        return not any_fail


# =============================================================================
# Helpers shared across steps
# =============================================================================


def _model_config_payload(model_type: str) -> dict[str, Any]:
    """Build the ``ModelConfig`` body for a given baseline ``model_type``.

    Demo models are LightGBM-free baselines per PRP-15 scope (Phase-2-aware
    LightGBM is queued as PRP-16). Each shape matches one branch of the
    discriminated union in ``app/features/forecasting/schemas.py``.
    """
    if model_type == "naive":
        return {"model_type": "naive"}
    if model_type == "seasonal_naive":
        return {"model_type": "seasonal_naive", "season_length": 7}
    if model_type == "moving_average":
        return {"model_type": "moving_average", "window_size": 7}
    raise ValueError(f"Unsupported demo model_type: {model_type}")


def _llm_key_present() -> bool:
    """Return True if any agent-capable LLM key is set in Settings."""
    settings = get_settings()
    return bool(settings.openai_api_key) or bool(settings.anthropic_api_key)


def _select_winner(
    backtest_results: dict[str, dict[str, float]],
) -> tuple[str, float] | None:
    """Pick the (model_type, WAPE) with the lowest aggregated WAPE.

    Skips models whose aggregated metrics are missing / NaN -- the
    backtester can legitimately return NaN on degenerate folds. Returns
    ``None`` if no model has a usable WAPE.
    """
    best: tuple[str, float] | None = None
    for model_type, metrics in backtest_results.items():
        wape = metrics.get("wape")
        if wape is None:
            continue
        if math.isnan(wape):
            continue
        if best is None or wape < best[1]:
            best = (model_type, wape)
    return best


# =============================================================================
# Steps
# =============================================================================


async def step_precheck(_ctx: DemoContext, client: HttpClient) -> StepOutcome:
    """GET /health -- precondition; failure exits with code 2."""
    start = time.monotonic()
    body = await client.request("precheck", "GET", "/health")
    status_field = body.get("status", "")
    detail = f"/health -> {status_field or 'unknown'}"
    return StepOutcome(
        name="precheck",
        status="pass" if status_field == "ok" else "fail",
        detail=detail,
        duration_ms=(time.monotonic() - start) * 1000,
    )


async def step_reset(ctx: DemoContext, client: HttpClient) -> StepOutcome:
    """Wipe the DB if ``--reset``; no-op otherwise."""
    start = time.monotonic()
    if not ctx.reset:
        return StepOutcome(
            name="reset",
            status="skip",
            detail="--reset not set",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    body = await client.request(
        "reset",
        "DELETE",
        "/seeder/data",
        json_body={"scope": "all", "dry_run": False},
    )
    deleted = body.get("records_deleted", {})
    total = sum(v for v in deleted.values() if isinstance(v, int))
    return StepOutcome(
        name="reset",
        status="pass",
        detail=f"deleted {total} rows across {len(deleted)} tables",
        duration_ms=(time.monotonic() - start) * 1000,
    )


async def step_seed(ctx: DemoContext, client: HttpClient) -> StepOutcome:
    """Seed the demo_minimal scenario (synchronous POST /seeder/generate)."""
    start = time.monotonic()
    if ctx.skip_seed:
        return StepOutcome(
            name="seed",
            status="skip",
            detail="--skip-seed set",
            duration_ms=(time.monotonic() - start) * 1000,
        )
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
    records: dict[str, int] = {
        k: int(v) for k, v in body.get("records_created", {}).items() if isinstance(v, int)
    }
    ctx.seed_records = records
    sales = records.get("sales_daily", 0)
    return StepOutcome(
        name="seed",
        status="pass",
        detail=(
            f"{DEMO_SCENARIO}: {DEMO_SEED_STORES} stores x "
            f"{DEMO_SEED_PRODUCTS} products, {sales} sales rows"
        ),
        duration_ms=(time.monotonic() - start) * 1000,
    )


async def step_status(ctx: DemoContext, client: HttpClient) -> StepOutcome:
    """GET /seeder/status -- confirm seed landed; capture date range."""
    start = time.monotonic()
    body = await client.request("status", "GET", "/seeder/status")
    raw_start = body.get("date_range_start")
    raw_end = body.get("date_range_end")
    if not isinstance(raw_start, str) or not isinstance(raw_end, str):
        return StepOutcome(
            name="status",
            status="fail",
            detail="no date_range in /seeder/status (was DB seeded?)",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    ctx.date_start = date.fromisoformat(raw_start)
    ctx.date_end = date.fromisoformat(raw_end)
    sales = body.get("sales", 0)
    return StepOutcome(
        name="status",
        status="pass",
        detail=f"date_range={raw_start}..{raw_end} sales={sales}",
        duration_ms=(time.monotonic() - start) * 1000,
    )


async def step_features(ctx: DemoContext, client: HttpClient) -> StepOutcome:
    """Compute a small lag/rolling/calendar featureset for one series.

    Demonstration-only: the three baseline models below do not consume
    these features. PRP-16 (Phase-2-aware LightGBM) will wire features
    into training.
    """
    start = time.monotonic()
    if ctx.date_end is None:
        return StepOutcome(
            name="features",
            status="fail",
            detail="no date_end on ctx; status step did not populate it",
            duration_ms=(time.monotonic() - start) * 1000,
        )
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
    return StepOutcome(
        name="features",
        status="pass",
        detail=f"{rows} rows, {len(columns)} columns (lag+rolling+calendar)",
        duration_ms=(time.monotonic() - start) * 1000,
    )


async def step_train_all(ctx: DemoContext, client: HttpClient) -> StepOutcome:
    """Train naive / seasonal_naive / moving_average in parallel."""
    start = time.monotonic()
    if ctx.date_start is None or ctx.date_end is None:
        return StepOutcome(
            name="train",
            status="fail",
            detail="no date range on ctx",
            duration_ms=(time.monotonic() - start) * 1000,
        )

    # Leave a horizon-sized tail of data unused by training so the backtest
    # has room to evaluate. Expanding-window backtest reuses the full range.
    train_end = ctx.date_end - timedelta(days=DEMO_HORIZON)

    async def _train(model_type: str) -> tuple[str, dict[str, Any]]:
        body = await client.request(
            f"train[{model_type}]",
            "POST",
            "/forecasting/train",
            json_body={
                "store_id": ctx.store_id,
                "product_id": ctx.product_id,
                # ISO date strings -- server-side Field(strict=False) accepts them
                "train_start_date": ctx.date_start.isoformat() if ctx.date_start else "",
                "train_end_date": train_end.isoformat(),
                "config": _model_config_payload(model_type),
            },
        )
        return model_type, body

    results = await asyncio.gather(*(_train(m) for m in DEMO_MODEL_TYPES))
    for model_type, body in results:
        ctx.train_results[model_type] = body
    trained = ", ".join(ctx.train_results.keys())
    return StepOutcome(
        name="train",
        status="pass",
        detail=f"trained {len(ctx.train_results)} models in parallel: {trained}",
        duration_ms=(time.monotonic() - start) * 1000,
    )


async def step_backtest_all(ctx: DemoContext, client: HttpClient) -> StepOutcome:
    """Run one backtest per model_type sequentially; pick winner by lowest WAPE."""
    start = time.monotonic()
    if ctx.date_start is None or ctx.date_end is None:
        return StepOutcome(
            name="backtest",
            status="fail",
            detail="no date range on ctx",
            duration_ms=(time.monotonic() - start) * 1000,
        )

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
        aggregated = main_results.get("aggregated_metrics", {})
        # Coerce metric values to floats; ignore non-numeric keys.
        clean: dict[str, float] = {}
        for k, v in aggregated.items():
            if isinstance(v, (int, float)):
                clean[str(k)] = float(v)
        ctx.backtest_results[model_type] = clean

    winner = _select_winner(ctx.backtest_results)
    if winner is None:
        return StepOutcome(
            name="backtest",
            status="fail",
            detail="no model produced a usable WAPE (all NaN?)",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    ctx.winner_model_type, ctx.winner_wape = winner
    return StepOutcome(
        name="backtest",
        status="pass",
        detail=(
            f"{len(ctx.backtest_results)} models, "
            f"winner={ctx.winner_model_type} wape={ctx.winner_wape:.4f}"
        ),
        duration_ms=(time.monotonic() - start) * 1000,
    )


async def step_register(ctx: DemoContext, client: HttpClient) -> StepOutcome:
    """Two-step registry create+update; alias the winner as ``demo-production``.

    Mandatory transition: pending -> running -> success. Aliases can only
    point to runs in SUCCESS status (``app/features/registry/routes.py:404``).
    Artifact hash is computed client-side; we share the filesystem with the
    API on this single-host system.
    """
    start = time.monotonic()
    if ctx.winner_model_type is None:
        return StepOutcome(
            name="register",
            status="fail",
            detail="no winner; cannot register",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    if ctx.date_start is None or ctx.date_end is None:
        return StepOutcome(
            name="register",
            status="fail",
            detail="no date range on ctx",
            duration_ms=(time.monotonic() - start) * 1000,
        )

    train_response = ctx.train_results.get(ctx.winner_model_type, {})
    model_path_raw = train_response.get("model_path")
    if not isinstance(model_path_raw, str) or not model_path_raw:
        return StepOutcome(
            name="register",
            status="fail",
            detail=f"no model_path for winner {ctx.winner_model_type}",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    model_path = Path(model_path_raw)
    if not model_path.exists():
        return StepOutcome(
            name="register",
            status="fail",
            detail=f"artifact missing at {model_path}",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    artifact_bytes = model_path.read_bytes()
    artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
    artifact_size = len(artifact_bytes)

    # (a) Create run in PENDING status. On-wire JSON key is "model_config"
    #     (alias of model_config_data per registry/schemas.py:68).
    create_body = await client.request(
        "register[create]",
        "POST",
        "/registry/runs",
        json_body={
            "model_type": ctx.winner_model_type,
            "model_config": _model_config_payload(ctx.winner_model_type),
            "feature_config": None,
            "data_window_start": ctx.date_start.isoformat(),
            "data_window_end": ctx.date_end.isoformat(),
            "store_id": ctx.store_id,
            "product_id": ctx.product_id,
            "agent_context": None,
            "git_sha": None,
        },
    )
    run_id_raw = create_body.get("run_id")
    if not isinstance(run_id_raw, str):
        return StepOutcome(
            name="register",
            status="fail",
            detail="POST /registry/runs returned no run_id",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    ctx.winning_run_id = run_id_raw

    # (b) PATCH pending -> running (mandatory intermediate).
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
            "metrics": ctx.backtest_results[ctx.winner_model_type],
            "artifact_uri": str(model_path),
            "artifact_hash": artifact_hash,
            "artifact_size_bytes": artifact_size,
        },
    )

    # (d) Alias the winner.
    await client.request(
        "register[alias]",
        "POST",
        "/registry/aliases",
        json_body={
            "alias_name": DEMO_ALIAS,
            "run_id": run_id_raw,
            "description": "Auto-created by scripts/run_demo.py",
        },
    )

    return StepOutcome(
        name="register",
        status="pass",
        detail=f"run_id={run_id_raw[:8]}... alias={DEMO_ALIAS}",
        duration_ms=(time.monotonic() - start) * 1000,
    )


async def step_verify(ctx: DemoContext, client: HttpClient) -> StepOutcome:
    """SHA-256 artifact-integrity check via the public verify endpoint."""
    start = time.monotonic()
    if ctx.winning_run_id is None:
        return StepOutcome(
            name="verify",
            status="fail",
            detail="no winning_run_id to verify",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    body = await client.request(
        "verify",
        "GET",
        f"/registry/runs/{ctx.winning_run_id}/verify",
    )
    verified = body.get("verified") is True
    return StepOutcome(
        name="verify",
        status="pass" if verified else "fail",
        detail="sha256 OK" if verified else f"verify={body.get('verified')}",
        duration_ms=(time.monotonic() - start) * 1000,
    )


async def step_agent(ctx: DemoContext, client: HttpClient) -> StepOutcome:
    """One-turn chat with the ``experiment`` agent; skip if no LLM key."""
    start = time.monotonic()
    if not _llm_key_present():
        return StepOutcome(
            name="agent",
            status="skip",
            detail="no OPENAI_API_KEY / ANTHROPIC_API_KEY set",
            duration_ms=(time.monotonic() - start) * 1000,
        )

    create_body = await client.request(
        "agent[session]",
        "POST",
        "/agents/sessions",
        json_body={"agent_type": "experiment", "initial_context": None},
    )
    session_id_raw = create_body.get("session_id")
    if not isinstance(session_id_raw, str):
        return StepOutcome(
            name="agent",
            status="fail",
            detail="no session_id returned",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    ctx.session_id = session_id_raw

    chat_body = await client.request(
        "agent[chat]",
        "POST",
        f"/agents/sessions/{session_id_raw}/chat",
        json_body={"message": "List the latest model runs.", "stream": False},
    )
    tokens = int(chat_body.get("tokens_used", 0))
    tool_calls = chat_body.get("tool_calls", [])
    tool_count = len(tool_calls) if isinstance(tool_calls, list) else 0
    return StepOutcome(
        name="agent",
        status="pass",
        detail=f"chat ok (tokens={tokens}, tool_calls={tool_count})",
        duration_ms=(time.monotonic() - start) * 1000,
    )


async def step_cleanup(ctx: DemoContext, client: HttpClient) -> StepOutcome:
    """Close the agent session (no-op if no session was opened)."""
    start = time.monotonic()
    if ctx.session_id is None:
        return StepOutcome(
            name="cleanup",
            status="skip",
            detail="no agent session to close",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    try:
        await client.request(
            "cleanup",
            "DELETE",
            f"/agents/sessions/{ctx.session_id}",
        )
    except StepError as exc:
        # Cleanup failure is non-fatal; emit a warn so the run still goes green.
        return StepOutcome(
            name="cleanup",
            status="warn",
            detail=f"DELETE failed but ignored: {exc}",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    return StepOutcome(
        name="cleanup",
        status="pass",
        detail="agent session closed",
        duration_ms=(time.monotonic() - start) * 1000,
    )


# =============================================================================
# Orchestration
# =============================================================================


StepFn = Callable[[DemoContext, "HttpClient"], Awaitable[StepOutcome]]


def _step_table() -> list[tuple[str, StepFn, bool]]:
    """Return the ordered step table.

    Tuple: (name, callable, is_precondition). A precondition failure exits 2;
    any other step failure exits 1.
    """
    return [
        ("precheck", step_precheck, True),
        ("reset", step_reset, False),
        ("seed", step_seed, False),
        ("status", step_status, False),
        ("features", step_features, False),
        ("train", step_train_all, False),
        ("backtest", step_backtest_all, False),
        ("register", step_register, False),
        ("verify", step_verify, False),
        ("agent", step_agent, False),
        ("cleanup", step_cleanup, False),
    ]


async def _run_one_step(
    step_fn: StepFn,
    ctx: DemoContext,
    client: HttpClient,
    name: str,
) -> StepOutcome:
    """Wrap a single step; convert exceptions into a ``fail`` outcome."""
    start = time.monotonic()
    try:
        return await step_fn(ctx, client)
    except StepError as exc:
        return StepOutcome(
            name=name,
            status="fail",
            detail=str(exc),
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except (httpx.HTTPError, OSError) as exc:
        return StepOutcome(
            name=name,
            status="fail",
            detail=f"transport error: {type(exc).__name__}: {exc}",
            duration_ms=(time.monotonic() - start) * 1000,
        )


async def main_async(args: DemoArgs) -> int:
    """Run the demo; return the process exit code."""
    steps = _step_table()
    ctx = DemoContext(
        api_url=args.api_url,
        seed=args.seed,
        skip_seed=args.skip_seed,
        reset=args.reset,
        quiet=args.quiet,
        timeout=args.timeout,
    )
    reporter = Reporter(quiet=args.quiet, total_steps=len(steps))
    reporter.header()
    outcomes: list[StepOutcome] = []
    ctx.wall_clock_start = time.monotonic()
    exit_code = 0

    try:
        async with HttpClient(args.api_url, args.timeout) as client:
            for name, step_fn, is_precondition in steps:
                outcome = await _run_one_step(step_fn, ctx, client, name)
                reporter.record(outcome)
                outcomes.append(outcome)
                if outcome.status == "fail":
                    exit_code = 2 if is_precondition else 1
                    break
    except (httpx.ConnectError, OSError) as exc:
        outcomes.append(
            StepOutcome(
                name="precheck",
                status="fail",
                detail=f"could not reach {args.api_url}: {exc}",
                duration_ms=0.0,
            )
        )
        exit_code = 2

    wall = time.monotonic() - ctx.wall_clock_start
    reporter.summary(outcomes, ctx, wall)
    return exit_code


# =============================================================================
# CLI
# =============================================================================


def parse_args(argv: list[str] | None = None) -> DemoArgs:
    """Parse CLI args into a :class:`DemoArgs`."""
    parser = argparse.ArgumentParser(
        prog="run_demo.py",
        description="ForecastLabAI end-to-end demo pipeline driver",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Deterministic seed for the seeder (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Skip the seeder scenario step (assumes data already present)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe the DB before seeding (destructive)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="One-line-per-step output (default: verbose)",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=DEFAULT_API_URL,
        help=f"Backend base URL (default: {DEFAULT_API_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help=f"Per-step HTTP timeout in seconds (default: {DEFAULT_TIMEOUT_S})",
    )
    ns = parser.parse_args(argv)
    return DemoArgs(
        seed=int(ns.seed),
        skip_seed=bool(ns.skip_seed),
        reset=bool(ns.reset),
        quiet=bool(ns.quiet),
        api_url=str(ns.api_url),
        timeout=float(ns.timeout),
    )


def main() -> None:
    sys.exit(asyncio.run(main_async(parse_args())))


if __name__ == "__main__":
    main()
