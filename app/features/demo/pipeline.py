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
import re
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

# PRP-39 — quick_baseline_sweep portfolio preset.
# SOURCE: frontend/src/components/forecast-intelligence/batch-preset-utils.ts:22-28
# First 3 of the 5 quick_baseline_sweep baselines — gives 3 stores x 2 products
# x 3 models = 18 items, matching INITIAL-39 § Scope. Keep this list in sync
# with the frontend preset definition; the demo slice cannot import frontend
# code (vertical-slice rule), so a comment is the only drift signal.
BATCH_PRESET_QUICK_BASELINE_SWEEP_MODELS: tuple[str, ...] = (
    "naive",
    "seasonal_naive",
    "moving_average",
)

# PRP-39 — per probe report § D3, /batch/forecasting settles synchronously in
# most cases. The poll loop is a safety net guarding against a future
# async-runner mode.
_BATCH_POLL_INTERVAL_SECONDS = 2.0
_BATCH_POLL_TIMEOUT_SECONDS = 90.0

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

    def __init__(
        self,
        app: FastAPI,
        *,
        event_sink: list[StepEvent] | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            # raise_app_exceptions=False makes the in-process transport behave
            # like a real network client: an unhandled error inside a driven
            # endpoint surfaces as a 500 *response* (RFC 7807) rather than a
            # re-raised exception, so steps can handle it as a normal _StepError.
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://demo.internal",
            timeout=_HTTP_TIMEOUT,
        )
        # PRP-41 — opt-in intermediate event sink. Only the HITL step uses it;
        # `run_pipeline` drains the buffer just before each terminal step_complete
        # and stamps step_index / total_steps / phase_index / phase_total /
        # phase_name onto every drained event. None in unit tests where the
        # sink isn't wired up.
        self._event_sink = event_sink

    async def __aenter__(self) -> _Client:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self._client.aclose()

    def yield_event(self, event: StepEvent) -> None:
        """PRP-41 — buffer an intermediate StepEvent for the orchestrator.

        The orchestrator (``run_pipeline``) drains the sink between the step
        function's return and the terminal ``step_complete`` it yields. Step
        functions that do not need to surface intermediate state never call
        this. If no sink is wired (e.g. in unit tests), the event is silently
        dropped — callers must not rely on it for terminal payload.
        """
        if self._event_sink is None:
            return
        self._event_sink.append(event)

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
    # PRP-39 — additive Optional fields populated only on SHOWCASE_RICH runs
    # AND only by their respective step functions.
    compat_compare_result: dict[str, Any] | None = None
    stale_alias_run_id: str | None = None
    original_demo_alias_run_id: str | None = None
    batch_id: str | None = None
    batch_status: str | None = None
    # PRP-40 — additive fields for the planning + knowledge phases (set on
    # SHOWCASE_RICH runs only; remain None on demo_minimal / sparse).
    scenario_artifact_key: str | None = None
    price_cut_scenario_id: str | None = None
    holiday_scenario_id: str | None = None
    embedding_unreachable: bool = False
    # PRP-41 — additive HITL approval state, populated only by
    # step_agent_hitl_flow on SHOWCASE_RICH. Remain None on every other path.
    approval_action_id: str | None = None
    agent_approval_decision: str | None = None  # "executed"|"rejected"|"expired"|"timed_out"


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


# PRP-41 — HITL approval flow constants. Display delay gives the visitor a
# window to click Approve on the FE before the backend auto-fires; the hard
# timeout is the load-bearing fallback so a hung agent never stops the demo.
_APPROVAL_DISPLAY_DELAY_S = 3.0
_APPROVAL_HARD_TIMEOUT_S = 90.0
_HITL_PROMPT = (
    "Save a 10% price-cut scenario plan for the demo-production model "
    "as 'showcase-agent-savedplan'."
)


# PRP-40 — artifact-key parser for /scenarios/* run_id resolution. Two ID
# spaces: model_run.run_id (32-char UUID-hex) vs scenarios.run_id (12-char
# artifact key parsed from `model_{KEY}.joblib`). Memory anchor:
# [[scenario-run-id-vs-registry-run-id]].
_ARTIFACT_KEY_RE = re.compile(r"model_([0-9a-f]+)(?:\.joblib)?$")


def _parse_artifact_key(artifact_uri: str) -> str:
    """Extract the 12-char artifact-key from a registry artifact_uri.

    V1 demo: 'demo/{model_type}-model_{KEY}.joblib'   -> KEY
    V2:      'artifacts/models/model_{KEY}.joblib'    -> KEY
    """
    match = _ARTIFACT_KEY_RE.search(artifact_uri)
    if match is None:
        raise ValueError(f"Cannot parse artifact-key from artifact_uri: {artifact_uri!r}")
    return match.group(1)


# PRP-40 — curated 5-file user-guide corpus indexed by the knowledge phase.
# The path_prefix RAG indexing additive contract scopes discovery to this
# subset (memory anchor: [[rag-runtime-config-and-corpus-state]] — keep the
# blast radius small).
_USER_GUIDE_CURATED_FILES: frozenset[str] = frozenset(
    {
        "docs/user-guide/getting-started.md",
        "docs/user-guide/dashboard-guide.md",
        "docs/user-guide/feature-reference.md",
        "docs/user-guide/agents-and-rag-guide.md",
        "docs/user-guide/advanced-forecasting-guide.md",
    }
)


async def _embedding_provider_reachable(client: _Client) -> tuple[bool, str]:
    """Probe whether the configured RAG embedding provider is reachable.

    Mirrors ``_llm_key_present()`` for the embedding provider. Returns
    ``(reachable, provider_name)``. Logs key NAME only, never the value
    (security-patterns.md).

    - openai -> bool(settings.openai_api_key)
    - ollama -> live-probe via GET /config/providers/health (reads the
      ollama entry's ``reachable`` field)
    """
    settings = get_settings()
    provider = settings.rag_embedding_provider
    if provider == "openai":
        return (bool(settings.openai_api_key), provider)
    if provider == "ollama":
        # GET /config/providers/health returns a list (per
        # ConfigService.get_provider_health); _Client.request wraps top-level
        # JSON arrays as ``{"_raw": [...]}`` (pipeline.py:158-159).
        try:
            body = await client.request("knowledge[probe]", "GET", "/config/providers/health")
        except _StepError:
            return (False, provider)
        items = body.get("_raw", [])
        if isinstance(items, list):
            for entry in items:
                if isinstance(entry, dict) and entry.get("provider") == "ollama":
                    return (bool(entry.get("reachable")), provider)
    return (False, provider)


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


# =============================================================================
# PRP-40 — Planning + Knowledge phase steps (SHOWCASE_RICH only)
# =============================================================================


async def step_scenario_simulate_and_save(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-40 — save a 10% price-cut scenario against the champion run.

    Resolves the demo-production champion -> artifact_uri -> 12-char artifact
    key, then POSTs /scenarios to run the simulation AND persist it as
    ``showcase-price-cut-10pct`` in one round-trip. R16 — scenarios.run_id is
    the artifact key, not model_run.run_id.
    """
    if ctx.date_end is None:
        return ("fail", "no date_end on ctx (status step did not populate it)", {})

    # (1) Resolve alias -> registry run_id (32-char uuid).
    alias_body = await client.request(
        "scenario_simulate_and_save[alias]",
        "GET",
        f"/registry/aliases/{DEMO_ALIAS}",
    )
    winner_run_id = alias_body.get("run_id")
    if not isinstance(winner_run_id, str):
        return ("fail", f"{DEMO_ALIAS} alias has no run_id", {})

    # (2) Resolve run -> artifact_uri.
    run_body = await client.request(
        "scenario_simulate_and_save[run]",
        "GET",
        f"/registry/runs/{winner_run_id}",
    )
    artifact_uri = run_body.get("artifact_uri")
    if not isinstance(artifact_uri, str):
        return ("fail", f"run {winner_run_id[:8]}... has no artifact_uri", {})

    # (3) Parse the 12-char artifact key.
    try:
        artifact_key = _parse_artifact_key(artifact_uri)
    except ValueError as exc:
        return ("fail", str(exc), {})
    ctx.scenario_artifact_key = artifact_key

    # (4+5) Build a price-cut assumption inside the forecast horizon and persist.
    # POST /scenarios runs the simulation internally and stores the resulting
    # ScenarioComparison in the response, so we don't need a separate
    # /scenarios/simulate round-trip.
    horizon_start = ctx.date_end + timedelta(days=1)
    horizon_end = ctx.date_end + timedelta(days=DEMO_HORIZON)
    assumptions = {
        "price": {
            "change_pct": -0.10,
            "start_date": horizon_start.isoformat(),
            "end_date": horizon_end.isoformat(),
        }
    }
    plan_body = await client.request(
        "scenario_simulate_and_save[save]",
        "POST",
        "/scenarios",
        json_body={
            "name": "showcase-price-cut-10pct",
            "run_id": artifact_key,
            "horizon": DEMO_HORIZON,
            "assumptions": assumptions,
            "tags": ["showcase", "price"],
        },
    )
    scenario_id_raw = plan_body.get("scenario_id")
    if isinstance(scenario_id_raw, str):
        ctx.price_cut_scenario_id = scenario_id_raw

    comparison = plan_body.get("comparison") or {}
    method = comparison.get("method", "unknown") if isinstance(comparison, dict) else "unknown"
    units_delta_raw = comparison.get("units_delta", 0.0) if isinstance(comparison, dict) else 0.0
    revenue_delta_raw = (
        comparison.get("revenue_delta", 0.0) if isinstance(comparison, dict) else 0.0
    )
    try:
        units_delta = float(units_delta_raw)
    except (TypeError, ValueError):
        units_delta = 0.0
    try:
        revenue_delta = float(revenue_delta_raw)
    except (TypeError, ValueError):
        revenue_delta = 0.0

    return (
        "pass",
        (
            f"plan=showcase-price-cut-10pct method={method} "
            f"Δunits={units_delta:+.1f} Δrevenue={revenue_delta:+.2f}"
        ),
        {
            "scenario_id": scenario_id_raw,
            "method": method,
            "units_delta": units_delta,
            "revenue_delta": revenue_delta,
            "winner_run_id": winner_run_id,
            "artifact_key": artifact_key,
        },
    )


async def step_multi_plan_compare(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-40 — save the holiday plan and rank both plans by revenue_delta.

    WARN (not FAIL) when the second-plan save fails so the visitor still sees
    the first plan was saved (R19 partial-success surfacing).
    """
    if ctx.price_cut_scenario_id is None or ctx.scenario_artifact_key is None:
        return ("fail", "price_cut plan not saved by previous step", {})
    if ctx.date_end is None:
        return ("fail", "no date_end on ctx", {})

    # (1) Build a one-day holiday inside the horizon and persist plan #2.
    holiday_day = (ctx.date_end + timedelta(days=DEMO_HORIZON // 2)).isoformat()
    try:
        plan_body = await client.request(
            "multi_plan_compare[save]",
            "POST",
            "/scenarios",
            json_body={
                "name": "showcase-holiday-uplift",
                "run_id": ctx.scenario_artifact_key,
                "horizon": DEMO_HORIZON,
                "assumptions": {"holiday": {"dates": [holiday_day]}},
                "tags": ["showcase", "holiday"],
            },
        )
    except _StepError as exc:
        return (
            "warn",
            f"holiday-plan save failed: {exc}; price-cut plan still saved",
            {"price_cut_scenario_id": ctx.price_cut_scenario_id},
        )
    holiday_id_raw = plan_body.get("scenario_id")
    if not isinstance(holiday_id_raw, str):
        return ("warn", "holiday-plan save returned no scenario_id", {})
    ctx.holiday_scenario_id = holiday_id_raw

    # (2+3) Rank both plans by revenue_delta.
    compare_body = await client.request(
        "multi_plan_compare[compare]",
        "POST",
        "/scenarios/compare",
        json_body={
            "scenario_ids": [ctx.price_cut_scenario_id, holiday_id_raw],
            "rank_by": "revenue_delta",
        },
    )
    scenarios_raw = compare_body.get("scenarios") or []
    # Filter on the runtime type up-front so the local list is typed as a
    # ``list[dict[str, Any]]`` and downstream calls don't need to re-check.
    scenarios_list: list[dict[str, Any]] = (
        [s for s in scenarios_raw if isinstance(s, dict)] if isinstance(scenarios_raw, list) else []
    )
    if not scenarios_list:
        return ("fail", "/scenarios/compare returned empty ranked list", {})
    winner = scenarios_list[0]
    winner_id = winner.get("scenario_id", "unknown")
    winner_name = winner.get("name", "unknown")
    ranked = [
        {
            "scenario_id": s.get("scenario_id"),
            "name": s.get("name"),
            "units_delta": s.get("units_delta"),
            "revenue_delta": s.get("revenue_delta"),
            "rank": s.get("rank"),
        }
        for s in scenarios_list
    ]
    return (
        "pass",
        f"winner={winner_name} ranked_by=revenue_delta",
        {
            "winner_scenario_id": winner_id,
            "winner_name": winner_name,
            "ranked_by": "revenue_delta",
            "ranked": ranked,
        },
    )


async def step_embedding_provider_probe(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-40 — probe the configured embedding provider. Always PASS.

    When reachable, downstream knowledge steps run normally. When unreachable,
    sets ``ctx.embedding_unreachable=True`` so the next two steps SKIP with a
    clear detail; the pipeline still goes green.
    """
    reachable, provider = await _embedding_provider_reachable(client)
    ctx.embedding_unreachable = not reachable
    logger.info(
        "demo.embedding_provider_probe",
        provider=provider,
        reachable=reachable,
    )
    detail = (
        f"provider={provider} reachable={reachable}"
        if reachable
        else f"provider={provider} unreachable — knowledge phase will skip"
    )
    return ("pass", detail, {"provider": provider, "reachable": reachable})


async def step_rag_index_subset(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-40 — index the curated 5-file docs/user-guide corpus.

    SKIPs when ``ctx.embedding_unreachable`` is set (by the prior probe step).
    Uses the additive ``path_prefix`` field on IndexProjectDocsRequest so the
    blast radius stays scoped to the user-guide subset.
    """
    if ctx.embedding_unreachable:
        return ("skip", "embedding provider unreachable", {})

    body = await client.request(
        "rag_index_subset",
        "POST",
        "/rag/index/project-docs",
        json_body={
            "include_docs": True,
            "include_prps": False,
            "include_root": False,
            "path_prefix": "docs/user-guide",
        },
    )
    results = body.get("results") or []
    total_chunks = int(body.get("total_chunks", 0))
    failed = int(body.get("failed", 0))
    indexed = int(body.get("indexed", 0))
    updated = int(body.get("updated", 0))
    unchanged = int(body.get("unchanged", 0))
    curated_hits = sum(
        1
        for r in results
        if isinstance(r, dict) and r.get("source_path") in _USER_GUIDE_CURATED_FILES
    )
    return (
        "pass",
        f"files_indexed={curated_hits}/5 chunks={total_chunks} failed={failed}",
        {
            "total_files": int(body.get("total_files", 0)),
            "indexed": indexed,
            "updated": updated,
            "unchanged": unchanged,
            "failed": failed,
            "total_chunks": total_chunks,
            "curated_hits": curated_hits,
        },
    )


async def step_rag_retrieve_probe(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-40 — semantic-retrieve probe against the curated corpus.

    SKIPs when ``ctx.embedding_unreachable``. WARN (not FAIL) on zero hits so
    a green-but-empty corpus still lets the pipeline go green.
    """
    if ctx.embedding_unreachable:
        return ("skip", "embedding provider unreachable", {})

    body = await client.request(
        "rag_retrieve_probe",
        "POST",
        "/rag/retrieve",
        json_body={"query": "How do I run the demo pipeline?", "top_k": 3},
    )
    results = body.get("results") or []
    if not results:
        return (
            "warn",
            "no hits — corpus indexed but query did not match",
            {
                "results_count": 0,
                "total_chunks_searched": body.get("total_chunks_searched", 0),
            },
        )
    top = results[0] if isinstance(results, list) else {}
    title = top.get("source_path", "unknown") if isinstance(top, dict) else "unknown"
    score_raw = top.get("relevance_score", 0.0) if isinstance(top, dict) else 0.0
    try:
        score = float(score_raw)
    except (TypeError, ValueError):
        score = 0.0
    return (
        "pass",
        f"top hit: {title} (score={score:.3f})",
        {
            "results_count": len(results),
            "top_source_path": title,
            "top_relevance_score": score,
        },
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


async def step_champion_compat_compare(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-39 — Compare V1 baseline vs V2 prophet_like (champion-compat).

    Derives ``compatible`` + ``comparable_reason`` client-side per probe
    report § D1 (the compare endpoint envelope has only ``run_a``,
    ``run_b``, ``config_diff``, ``metrics_diff`` — no top-level
    compatibility flags). Mirrors the predicate at
    ``frontend/src/components/forecast-intelligence/champion-compatibility-utils.ts:14-47``
    so the same reason key works for both the compare card and the ops
    chip.
    """
    if ctx.v2_run_id is None or ctx.winning_run_id is None:
        # R14 — no V2 run on the showcase grain (user ran scenario=demo_minimal).
        return (
            "skip",
            "no V2 run on the showcase grain — run with scenario=showcase_rich",
            {},
        )

    # Discover a V1 baseline run on the same grain. Use the registry's
    # status filter to narrow to SUCCESS runs, then pick the first one
    # whose feature_frame_version is None-or-1 and that isn't the V2 run.
    runs_body = await client.request(
        "champion_compat_compare[runs]",
        "GET",
        (
            f"/registry/runs?store_id={ctx.store_id}&product_id={ctx.product_id}"
            "&status=success&page_size=20"
        ),
    )
    runs_raw = runs_body.get("runs", [])
    runs = runs_raw if isinstance(runs_raw, list) else []
    v1_run_id: str | None = None
    for run in runs:
        if not isinstance(run, dict):
            continue
        ffv = run.get("feature_frame_version")
        run_id_raw = run.get("run_id")
        if (
            (ffv is None or ffv == 1)
            and isinstance(run_id_raw, str)
            and run_id_raw != ctx.v2_run_id
        ):
            v1_run_id = run_id_raw
            break
    if v1_run_id is None:
        return ("skip", "no V1 baseline run on the showcase grain", {})

    # GET the compare envelope. Per D1, derive compatible + reason client-side.
    compare_body = await client.request(
        "champion_compat_compare[compare]",
        "GET",
        f"/registry/compare/{v1_run_id}/{ctx.v2_run_id}",
    )
    run_a_raw = compare_body.get("run_a", {})
    run_b_raw = compare_body.get("run_b", {})
    run_a = run_a_raw if isinstance(run_a_raw, dict) else {}
    run_b = run_b_raw if isinstance(run_b_raw, dict) else {}
    v_a = run_a.get("feature_frame_version")  # None for legacy V1
    v_b = run_b.get("feature_frame_version")  # 2 for PRP-38's V2 run
    # Coerce legacy V1 (None) to V=1 for the compat predicate, matching the
    # frontend computeCompatibility logic AND OpsService._run_feature_frame_version.
    v_a_norm = 1 if v_a is None else v_a
    v_b_norm = 1 if v_b is None else v_b
    compatible = v_a_norm == v_b_norm  # grain + window equal by construction
    reason: str | None = None if compatible else "feature_frame_version_mismatch"

    ctx.compat_compare_result = {
        "v1_run_id": v1_run_id,
        "v2_run_id": ctx.v2_run_id,
        "compatible": compatible,
        "comparable_reason": reason,
    }

    return (
        "pass",
        f"V_a={v_a_norm} V_b={v_b_norm} compatible={compatible}",
        {
            "v1_run_id": v1_run_id,
            "v2_run_id": ctx.v2_run_id,
            "feature_frame_version_a": v_a,
            "feature_frame_version_b": v_b,
            "compatible": compatible,
            "comparable_reason": reason,
        },
    )


async def step_stale_alias_trigger(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-39 — trigger feature_frame_version_mismatch stale-alias verdict.

    Registers a SECOND prophet_like run on the SAME grain as PRP-38's V2 run,
    with ``runtime_info_extras.feature_frame_version`` set to a value
    DIFFERENT from PRP-38's V2 (which is V=2). The integer JSONB key is
    opaque to the ops service, so V=3 is a valid "synthetic" value that
    fires the V-mismatch branch (see probe report § (b)).
    """
    if ctx.v2_run_id is None or ctx.date_start is None or ctx.date_end is None:
        return (
            "skip",
            "no V2 run / date range — run with scenario=showcase_rich",
            {},
        )

    # Register the V=3 run. Mirror step_v2_train's create+running+success chain.
    create_body = await client.request(
        "stale_alias_trigger[create]",
        "POST",
        "/registry/runs",
        json_body={
            "model_type": "prophet_like",
            "model_config": _model_config_payload("prophet_like"),
            "feature_config": None,
            "data_window_start": ctx.date_start.isoformat(),
            "data_window_end": ctx.date_end.isoformat(),
            "store_id": ctx.store_id,
            "product_id": ctx.product_id,
            # The whole point of this step — controlled V different from V=2.
            "runtime_info_extras": {"feature_frame_version": 3},
        },
    )
    second_run_id_raw = create_body.get("run_id")
    if not isinstance(second_run_id_raw, str):
        return ("fail", "POST /registry/runs returned no run_id", {})
    ctx.stale_alias_run_id = second_run_id_raw

    # PATCH pending → running → success.
    await client.request(
        "stale_alias_trigger[running]",
        "PATCH",
        f"/registry/runs/{second_run_id_raw}",
        json_body={"status": "running"},
    )
    await client.request(
        "stale_alias_trigger[success]",
        "PATCH",
        f"/registry/runs/{second_run_id_raw}",
        json_body={
            "status": "success",
            "metrics": {"wape": 999.0},
            "artifact_uri": "demo/stale-alias-placeholder.joblib",
            "artifact_hash": "0" * 64,
            "artifact_size_bytes": 1,
        },
    )

    # Hit /ops/summary to confirm the stale-alias verdict surfaces.
    ops_body = await client.request("stale_alias_trigger[ops]", "GET", "/ops/summary")
    aliases_raw = ops_body.get("aliases", [])
    aliases = aliases_raw if isinstance(aliases_raw, list) else []
    target: dict[str, Any] | None = None
    for alias in aliases:
        if isinstance(alias, dict) and alias.get("alias_name") == DEMO_ALIAS:
            target = alias
            break
    if target is None:
        return ("fail", f"alias {DEMO_ALIAS} missing from /ops/summary", {})

    stale_reason = target.get("stale_reason")
    if stale_reason != "feature_frame_version_mismatch":
        return (
            "fail",
            (f"expected stale_reason=feature_frame_version_mismatch, got {stale_reason}"),
            {},
        )

    alias_v = target.get("alias_feature_frame_version")
    comparable_v = target.get("comparable_run_feature_frame_version")
    return (
        "pass",
        (
            f"alias={DEMO_ALIAS} stale_reason={stale_reason} "
            f"V_alias={alias_v}→V_comparable={comparable_v}"
        ),
        {
            "alias_name": DEMO_ALIAS,
            "stale_reason": stale_reason,
            "alias_feature_frame_version": alias_v,
            "comparable_run_feature_frame_version": comparable_v,
            "second_v2_run_id": second_run_id_raw,
        },
    )


async def step_safer_promote_flow(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-39 — swap ``demo-production`` to a worse-WAPE run.

    Mirrors step_register's create+running+success+alias chain at
    ``pipeline.py``. Deliberately registers a worse-WAPE run so the
    safer-Promote dialog gates fire when a human visits /ops. The
    original alias target is captured BEFORE the swap so step_cleanup can
    restore it (R15).
    """
    if ctx.winning_run_id is None or ctx.date_start is None or ctx.date_end is None:
        return (
            "skip",
            "no winning run / date range — run with scenario=showcase_rich",
            {},
        )

    # Capture the current alias target BEFORE the swap (R15).
    alias_body = await client.request(
        "safer_promote[alias_pre]",
        "GET",
        f"/registry/aliases/{DEMO_ALIAS}",
    )
    pre_run_id_raw = alias_body.get("run_id")
    if not isinstance(pre_run_id_raw, str):
        return ("fail", f"GET /registry/aliases/{DEMO_ALIAS} returned no run_id", {})
    ctx.original_demo_alias_run_id = pre_run_id_raw

    # Register a fresh baseline run with a tweaked config so config_hash differs
    # from the prior register step's run. Use seasonal_naive season_length=14
    # (the default register uses 7).
    create_body = await client.request(
        "safer_promote[create]",
        "POST",
        "/registry/runs",
        json_body={
            "model_type": "seasonal_naive",
            "model_config": {
                "model_type": "seasonal_naive",
                "season_length": 14,
            },
            "feature_config": None,
            "data_window_start": ctx.date_start.isoformat(),
            "data_window_end": ctx.date_end.isoformat(),
            "store_id": ctx.store_id,
            "product_id": ctx.product_id,
            # V=1 deliberately to additionally fire the V-mismatch-ack gate
            # in the dialog (V2 winner → V1 challenger).
            "runtime_info_extras": {"feature_frame_version": 1},
        },
    )
    worse_run_id_raw = create_body.get("run_id")
    if not isinstance(worse_run_id_raw, str):
        return ("fail", "POST /registry/runs returned no run_id", {})

    # pending → running → success
    await client.request(
        "safer_promote[running]",
        "PATCH",
        f"/registry/runs/{worse_run_id_raw}",
        json_body={"status": "running"},
    )
    await client.request(
        "safer_promote[success]",
        "PATCH",
        f"/registry/runs/{worse_run_id_raw}",
        json_body={
            "status": "success",
            "metrics": {"wape": 99.0},
            "artifact_uri": "demo/safer-promote-placeholder.joblib",
            "artifact_hash": "0" * 64,
            "artifact_size_bytes": 1,
        },
    )

    # Swap the alias.
    await client.request(
        "safer_promote[alias_swap]",
        "POST",
        "/registry/aliases",
        json_body={
            "alias_name": DEMO_ALIAS,
            "run_id": worse_run_id_raw,
            "description": ("PRP-39 safer-Promote walkthrough — deliberate worse-WAPE swap."),
        },
    )

    return (
        "pass",
        (f"alias={DEMO_ALIAS} before={pre_run_id_raw[:8]}→after={worse_run_id_raw[:8]}"),
        {
            "alias_name": DEMO_ALIAS,
            "before_run_id": pre_run_id_raw,
            "after_run_id": worse_run_id_raw,
            "swap_intent": "demo_safer_promote_walkthrough",
        },
    )


async def step_batch_preset(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-39 — run the quick_baseline_sweep portfolio preset (Option A).

    Per probe report § D2, the preset is frontend-only — the backend
    ``BatchSubmitRequest`` does not accept ``preset_id``. The demo slice
    expands the preset client-side using
    ``BATCH_PRESET_QUICK_BASELINE_SWEEP_MODELS``.
    """
    if ctx.date_start is None or ctx.date_end is None:
        return ("skip", "no date range — run with scenario=showcase_rich", {})

    # Discover 3 stores + 2 products via the dimensions endpoints (mirrors
    # step_status pattern). Never hardcode ids — seeder doesn't reset IDs.
    stores_body = await client.request(
        "batch_preset[stores]",
        "GET",
        "/dimensions/stores?page=1&page_size=5",
    )
    products_body = await client.request(
        "batch_preset[products]",
        "GET",
        "/dimensions/products?page=1&page_size=5",
    )
    stores_raw = stores_body.get("stores", [])
    products_raw = products_body.get("products", [])
    stores = stores_raw if isinstance(stores_raw, list) else []
    products = products_raw if isinstance(products_raw, list) else []
    store_ids: list[int] = []
    for s in stores:
        if isinstance(s, dict):
            sid = s.get("id")
            if isinstance(sid, int):
                store_ids.append(sid)
                if len(store_ids) >= 3:
                    break
    product_ids: list[int] = []
    for p in products:
        if isinstance(p, dict):
            pid = p.get("id")
            if isinstance(pid, int):
                product_ids.append(pid)
                if len(product_ids) >= 2:
                    break
    if len(store_ids) < 3 or len(product_ids) < 2:
        return ("skip", "insufficient stores/products in the seeded grain", {})

    # POST /batch/forecasting — Option A expansion.
    submit_body = await client.request(
        "batch_preset[submit]",
        "POST",
        "/batch/forecasting",
        json_body={
            "operation": "train",
            "scope": {
                "kind": "manual",
                "store_ids": store_ids,
                "product_ids": product_ids,
            },
            "model_configs": [{"model_type": m} for m in BATCH_PRESET_QUICK_BASELINE_SWEEP_MODELS],
            "start_date": ctx.date_start.isoformat(),
            "end_date": ctx.date_end.isoformat(),
        },
    )
    batch_id_raw = submit_body.get("batch_id")
    if not isinstance(batch_id_raw, str):
        return ("fail", "POST /batch/forecasting returned no batch_id", {})
    ctx.batch_id = batch_id_raw

    terminal_statuses = {"completed", "failed", "partial", "cancelled"}
    status_raw = submit_body.get("status")
    status: str = status_raw if isinstance(status_raw, str) else "unknown"
    body: dict[str, Any] = submit_body
    if status not in terminal_statuses:
        t0 = time.monotonic()
        timed_out = True
        while time.monotonic() - t0 < _BATCH_POLL_TIMEOUT_SECONDS:
            await asyncio.sleep(_BATCH_POLL_INTERVAL_SECONDS)
            body = await client.request(
                "batch_preset[poll]",
                "GET",
                f"/batch/{batch_id_raw}",
            )
            status_raw = body.get("status")
            status = status_raw if isinstance(status_raw, str) else "unknown"
            if status in terminal_statuses:
                timed_out = False
                break
        if timed_out:
            ctx.batch_status = status
            return (
                "warn",
                (
                    f"batch poll timed out at {_BATCH_POLL_TIMEOUT_SECONDS:.0f}s; "
                    f"visit /visualize/batch/{batch_id_raw} to follow up"
                ),
                {
                    "batch_id": batch_id_raw,
                    "kind": "manual",
                    "preset_source": "quick_baseline_sweep",
                    "model_types": list(BATCH_PRESET_QUICK_BASELINE_SWEEP_MODELS),
                    "status": status,
                    "total_items": body.get("total_items"),
                    "completed_items": body.get("completed_items"),
                    "failed_items": body.get("failed_items"),
                },
            )

    ctx.batch_status = status
    step_status: StepStatus
    if status == "completed":
        step_status = "pass"
    elif status == "partial":
        step_status = "warn"
    else:  # failed or cancelled
        step_status = "fail"

    completed = body.get("completed_items")
    total = body.get("total_items")
    return (
        step_status,
        (f"preset=quick_baseline_sweep {completed}/{total} done status={status}"),
        {
            "batch_id": batch_id_raw,
            "kind": "manual",
            "preset_source": "quick_baseline_sweep",
            "model_types": list(BATCH_PRESET_QUICK_BASELINE_SWEEP_MODELS),
            "status": status,
            "total_items": total,
            "completed_items": completed,
            "failed_items": body.get("failed_items"),
        },
    )


async def step_cleanup(ctx: DemoContext, client: _Client) -> StepResult:
    """Close the agent session + restore the demo-production alias (PRP-39 R15).

    PRP-39 extends the original PRP-15 cleanup to ALSO restore the
    ``demo-production`` alias when ``safer_promote_flow`` swapped it to a
    worse-WAPE run. Failure to restore is a ``warn``, never a fail.
    """
    alias_restored = False
    restored_run_id: str | None = None

    # PRP-39 — R15 restore. Failure is `warn`, not `fail`.
    if ctx.original_demo_alias_run_id is not None:
        try:
            await client.request(
                "cleanup[restore_alias]",
                "POST",
                "/registry/aliases",
                json_body={
                    "alias_name": DEMO_ALIAS,
                    "run_id": ctx.original_demo_alias_run_id,
                    "description": "Restored by demo cleanup (PRP-39).",
                },
            )
            alias_restored = True
            restored_run_id = ctx.original_demo_alias_run_id
        except _StepError as exc:
            logger.warning(
                "demo.cleanup.alias_restore_failed",
                run_id=ctx.original_demo_alias_run_id,
                status_code=exc.status_code,
            )

    # PRESERVED — existing agent-session-close.
    agent_closed = False
    if ctx.session_id is not None:
        try:
            await client.request("cleanup", "DELETE", f"/agents/sessions/{ctx.session_id}")
            agent_closed = True
        except _StepError as exc:
            return (
                "warn",
                f"DELETE agent failed but ignored: {exc}",
                {
                    "agent_session_closed": False,
                    "alias_restored": alias_restored,
                    "restored_run_id": restored_run_id,
                },
            )

    detail_parts: list[str] = []
    if agent_closed:
        detail_parts.append("agent closed")
    if alias_restored and restored_run_id is not None:
        detail_parts.append(f"alias restored to {restored_run_id[:8]}...")

    # Preserve PRP-15 skip-semantics: when neither an agent session was
    # closed NOR an alias was restored, the step is a no-op.
    if not detail_parts:
        return (
            "skip",
            "no agent session to close",
            {
                "agent_session_closed": False,
                "alias_restored": False,
                "restored_run_id": None,
            },
        )
    return (
        "pass",
        " · ".join(detail_parts),
        {
            "agent_session_closed": agent_closed,
            "alias_restored": alias_restored,
            "restored_run_id": restored_run_id,
        },
    )


# =============================================================================
# PRP-41 — Agents (HITL) + Ops snapshot phases (showcase_rich only)
# =============================================================================


async def step_agent_hitl_flow(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-41 — HITL approval round-trip on the experiment agent.

    Flow:
      1. ``_llm_key_present()`` -> skip when no key.
      2. ``POST /agents/sessions`` (agent_type=experiment) -> session_id.
      3. ``POST /agents/sessions/{id}/chat`` with the HITL prompt; the
         experiment agent calls ``tool_save_scenario`` which short-circuits
         on the ``save_scenario`` entry in ``agent_require_approval``. The
         chat response carries ``pending_approval=true`` +
         ``pending_action: PendingAction``.
      4. ``client.yield_event(...)`` an intermediate step_complete with
         ``status='running'`` + ``awaiting_approval=true`` so the FE can
         render the Approve button.
      5. Sleep ``_APPROVAL_DISPLAY_DELAY_S`` -- a one-click FE Approve may
         pre-empt the auto-approve in this window.
      6. ``POST /agents/sessions/{id}/approve`` with ``{action_id,
         approved: true}``. Absorb 4xx (the FE pre-empted; the action was
         already consumed).
      7. Terminal: ``pass`` with the approval decision in step.data.

    Skip-gracefully on every error path (session-create / chat / approve
    failure, or the agent never triggers ``save_scenario``). Never raises.

    Hard timeout: if the elapsed time exceeds ``_APPROVAL_HARD_TIMEOUT_S``
    before step (6) completes, returns ``skip`` with
    ``approval_decision='timed_out'``.
    """
    key_present = _llm_key_present()
    logger.info("demo.agent_hitl_flow.key_present", present=key_present)
    if not key_present:
        return (
            "skip",
            "no API key matching agent_default_model provider",
            {},
        )

    started_at = time.monotonic()

    # (1+2) -- session.
    try:
        create_body = await client.request(
            "agent_hitl_flow[session]",
            "POST",
            "/agents/sessions",
            json_body={"agent_type": "experiment", "initial_context": None},
        )
    except _StepError as exc:
        return ("skip", f"session-create failed: {exc}", {})
    session_id_raw = create_body.get("session_id")
    if not isinstance(session_id_raw, str):
        return ("skip", "no session_id returned", {})
    session_id: str = session_id_raw
    ctx.session_id = session_id

    # (3) -- chat that triggers the gated tool.
    try:
        chat_body = await client.request(
            "agent_hitl_flow[chat]",
            "POST",
            f"/agents/sessions/{session_id}/chat",
            json_body={"message": _HITL_PROMPT, "stream": False},
        )
    except _StepError as exc:
        return (
            "skip",
            f"chat round-trip failed: {exc}",
            {"session_id": session_id},
        )

    pending_approval = bool(chat_body.get("pending_approval", False))
    raw_action = chat_body.get("pending_action") or {}
    pending_action: dict[str, Any] = raw_action if isinstance(raw_action, dict) else {}
    tokens_used = int(chat_body.get("tokens_used", 0))
    raw_tool_calls = chat_body.get("tool_calls", [])
    tool_count = len(raw_tool_calls) if isinstance(raw_tool_calls, list) else 0

    if not pending_approval or not pending_action:
        # The agent didn't trigger save_scenario (e.g. answered directly or
        # picked a different tool). Skip-by-design: not a failure.
        return (
            "skip",
            (
                f"agent did not trigger save_scenario "
                f"(tokens={tokens_used}, tool_calls={tool_count})"
            ),
            {
                "session_id": session_id,
                "tokens_used": tokens_used,
                "tool_calls_count": tool_count,
            },
        )

    action_id_raw = pending_action.get("action_id")
    if not isinstance(action_id_raw, str):
        return (
            "skip",
            "pending_action.action_id missing",
            {"session_id": session_id},
        )
    action_id: str = action_id_raw
    ctx.approval_action_id = action_id

    # (4) -- intermediate event so the FE renders Approve. step_index /
    # total_steps / phase_index / phase_total are stamped by the orchestrator
    # when it drains the sink (see run_pipeline).
    elapsed_ms = (time.monotonic() - started_at) * 1000.0
    client.yield_event(
        StepEvent(
            event_type="step_complete",
            step_name="agent_hitl_flow",
            step_index=0,
            total_steps=0,
            status="running",
            detail="awaiting approval (auto-approve in 3 s)",
            duration_ms=elapsed_ms,
            data={
                "awaiting_approval": True,
                "approval_url": f"/agents/sessions/{session_id}/approve",
                "action_id": action_id,
                "session_id": session_id,
                "tokens_used": tokens_used,
                "tool_calls_count": tool_count,
            },
            phase_name=PHASE_AGENTS,
        )
    )

    # (5) -- display delay.
    elapsed_after_intermediate = time.monotonic() - started_at
    delay = max(0.0, _APPROVAL_DISPLAY_DELAY_S - elapsed_after_intermediate)
    if delay > 0:
        await asyncio.sleep(delay)

    # (5b) -- hard-timeout check BEFORE the approve POST.
    elapsed_before_approve = time.monotonic() - started_at
    if elapsed_before_approve > _APPROVAL_HARD_TIMEOUT_S:
        ctx.agent_approval_decision = "timed_out"
        return (
            "skip",
            "approval timed out -- pipeline continued",
            {
                "session_id": session_id,
                "action_id": action_id,
                "approval_decision": "timed_out",
                "tokens_used": tokens_used,
                "tool_calls_count": tool_count,
                "timed_out": True,
            },
        )

    # (6) -- POST /approve. Absorb 4xx (FE pre-empted) per Task 1 §5 #2:
    # AgentService.approve_action returns 400 ("No pending action") when the
    # action was already consumed by the FE's optimistic Approve click.
    approval_decision = "executed"
    try:
        approve_body = await client.request(
            "agent_hitl_flow[approve]",
            "POST",
            f"/agents/sessions/{session_id}/approve",
            json_body={"action_id": action_id, "approved": True},
        )
        raw_status = approve_body.get("status", "executed")
        if isinstance(raw_status, str):
            approval_decision = raw_status
    except _StepError as exc:
        if 400 <= exc.status_code < 500:
            # FE pre-empted -- the approval already landed. Optimistic default.
            logger.info(
                "demo.agent_hitl_flow.approve_pre_empted",
                session_id=session_id,
                action_id=action_id,
                status_code=exc.status_code,
            )
            approval_decision = "executed"
        else:
            return (
                "skip",
                f"approve failed: {exc}",
                {
                    "session_id": session_id,
                    "action_id": action_id,
                    "tokens_used": tokens_used,
                    "tool_calls_count": tool_count,
                },
            )

    ctx.agent_approval_decision = approval_decision

    return (
        "pass",
        (
            f"session={session_id[:8]}... tokens={tokens_used} "
            f"tool_calls={tool_count} approved={approval_decision}"
        ),
        {
            "session_id": session_id,
            "action_id": action_id,
            "approval_decision": approval_decision,
            "tokens_used": tokens_used,
            "tool_calls_count": tool_count,
        },
    )


async def step_ops_snapshot(_ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-41 — fetch /ops/* endpoints and embed a 5-key KPI payload.

    Three GETs:
      - GET /ops/summary
      - GET /ops/retraining-candidates?limit=5
      - GET /ops/model-health?limit=5

    All endpoints are 200-safe on an empty DB (verified by
    ``test_summary_resilient_structural`` + ``test_model_health_resilient_structural``).

    Returns ``("pass", ...)`` when at least one of the three returned a body.
    Returns ``("warn", ...)`` only when all three failed -- never ``fail``
    (ops is observability, not a hard pipeline dependency).
    """
    summary: dict[str, Any] = {}
    candidates_body: dict[str, Any] = {}
    health_body: dict[str, Any] = {}

    try:
        summary = await client.request(
            "ops_snapshot[summary]",
            "GET",
            "/ops/summary",
        )
    except _StepError as exc:
        logger.warning("demo.ops_snapshot.summary_failed", status_code=exc.status_code)

    try:
        candidates_body = await client.request(
            "ops_snapshot[retraining]",
            "GET",
            "/ops/retraining-candidates?limit=5",
        )
    except _StepError as exc:
        logger.warning("demo.ops_snapshot.retraining_failed", status_code=exc.status_code)

    try:
        health_body = await client.request(
            "ops_snapshot[health]",
            "GET",
            "/ops/model-health?limit=5",
        )
    except _StepError as exc:
        logger.warning("demo.ops_snapshot.health_failed", status_code=exc.status_code)

    raw_aliases = summary.get("aliases") or []
    aliases: list[dict[str, Any]] = (
        [a for a in raw_aliases if isinstance(a, dict)] if isinstance(raw_aliases, list) else []
    )
    stale_count = sum(1 for a in aliases if a.get("is_stale"))
    total_aliases = len(aliases)

    raw_runs = summary.get("runs") or {}
    runs: dict[str, Any] = raw_runs if isinstance(raw_runs, dict) else {}
    raw_counts = runs.get("counts") or []
    # Task 1 confirmed: RunHealth.counts is list[StatusCount] where
    # StatusCount = {status: str, count: int}.
    total_runs = (
        sum(int(c.get("count", 0)) for c in raw_counts if isinstance(c, dict))
        if isinstance(raw_counts, list)
        else 0
    )

    raw_candidates = candidates_body.get("candidates") or []
    retraining_count = len(raw_candidates) if isinstance(raw_candidates, list) else 0

    raw_entries = health_body.get("entries") or []
    degrading_count = (
        sum(
            1
            for e in raw_entries
            if isinstance(e, dict) and e.get("drift_direction") == "degrading"
        )
        if isinstance(raw_entries, list)
        else 0
    )

    data: dict[str, Any] = {
        "stale_aliases_count": stale_count,
        "retraining_candidates_count": retraining_count,
        "total_runs": total_runs,
        "total_aliases": total_aliases,
        "degrading_health_count": degrading_count,
    }

    if summary or candidates_body or health_body:
        detail = (
            f"stale_aliases={stale_count} retraining={retraining_count} "
            f"runs={total_runs} aliases={total_aliases} "
            f"degrading={degrading_count}"
        )
        return ("pass", detail, data)

    # All three endpoints failed -- warn (pipeline still goes green).
    return (
        "warn",
        "/ops/* all 4xx/5xx -- ops snapshot unavailable",
        data,
    )


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
# PRP-39 — new portfolio phase, inserted between decision and verify.
PHASE_PORTFOLIO = "portfolio"
# PRP-40 — planning + knowledge phases inserted AFTER portfolio, BEFORE verify
# on SHOWCASE_RICH.
PHASE_PLANNING = "planning"
PHASE_KNOWLEDGE = "knowledge"
PHASE_VERIFY = "verify"
# PRP-41 — design Z: unified "agents" phase id used by BOTH demo_minimal/sparse
# (legacy step_agent) AND showcase_rich (step_agent_hitl_flow). The PRP-38
# PHASE_AGENT constant is replaced; no other code referenced it by name.
PHASE_AGENTS = "agents"
# PRP-41 — new ops phase, populated only on SHOWCASE_RICH.
PHASE_OPS = "ops"
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
    # PRP-39 — new portfolio phase, empty under demo_minimal/sparse.
    portfolio_steps: list[tuple[str, StepFn]] = []
    # PRP-40 — planning + knowledge default to empty; populated on SHOWCASE_RICH.
    planning_steps: list[tuple[str, StepFn]] = []
    knowledge_steps: list[tuple[str, StepFn]] = []
    verify_steps: list[tuple[str, StepFn]] = [("verify", step_verify)]
    # PRP-41 — design Z: same phase id "agents" for both branches; SHOWCASE_RICH
    # swaps the legacy single-turn `step_agent` for the HITL flow.
    agent_steps: list[tuple[str, StepFn]] = (
        [("agent_hitl_flow", step_agent_hitl_flow)]
        if scenario is ScenarioPreset.SHOWCASE_RICH
        else [("agent", step_agent)]
    )
    # PRP-41 — new ops phase. Empty on demo_minimal / sparse (no row emitted).
    ops_steps: list[tuple[str, StepFn]] = (
        [("ops_snapshot", step_ops_snapshot)] if scenario is ScenarioPreset.SHOWCASE_RICH else []
    )
    cleanup_steps: list[tuple[str, StepFn]] = [("cleanup", step_cleanup)]
    if scenario is ScenarioPreset.SHOWCASE_RICH:
        data_steps += [
            ("phase2_enrichment", step_phase2_enrichment),
            ("historical_backfill", step_historical_backfill),
        ]
        modeling_steps += [("v2_train", step_v2_train)]
        # PRP-39 — extend decision phase (AFTER register) with 3 new steps.
        decision_steps += [
            ("champion_compat_compare", step_champion_compat_compare),
            ("stale_alias_trigger", step_stale_alias_trigger),
            ("safer_promote_flow", step_safer_promote_flow),
        ]
        # PRP-39 — new portfolio phase has its one step under showcase_rich.
        portfolio_steps = [("batch_preset", step_batch_preset)]
        # PRP-40 — planning + knowledge phases live in the SHOWCASE_RICH branch.
        planning_steps = [
            ("scenario_simulate_and_save", step_scenario_simulate_and_save),
            ("multi_plan_compare", step_multi_plan_compare),
        ]
        knowledge_steps = [
            ("embedding_provider_probe", step_embedding_provider_probe),
            ("rag_index_subset", step_rag_index_subset),
            ("rag_retrieve_probe", step_rag_retrieve_probe),
        ]
    rows: list[PhaseStep] = []
    rows += [(PHASE_DATA, name, fn) for name, fn in data_steps]
    rows += [(PHASE_MODELING, name, fn) for name, fn in modeling_steps]
    rows += [(PHASE_DECISION, name, fn) for name, fn in decision_steps]
    # PRP-39 — INSERT portfolio BEFORE verify (relative anchor).
    rows += [(PHASE_PORTFOLIO, name, fn) for name, fn in portfolio_steps]
    # PRP-40 — planning + knowledge inserted AFTER portfolio, BEFORE verify
    # (relative anchor; both are no-ops outside SHOWCASE_RICH).
    rows += [(PHASE_PLANNING, name, fn) for name, fn in planning_steps]
    rows += [(PHASE_KNOWLEDGE, name, fn) for name, fn in knowledge_steps]
    rows += [(PHASE_VERIFY, name, fn) for name, fn in verify_steps]
    # PRP-41 — both branches use PHASE_AGENTS; SHOWCASE_RICH ALSO appends an
    # ops_snapshot row under the new PHASE_OPS, BEFORE cleanup.
    rows += [(PHASE_AGENTS, name, fn) for name, fn in agent_steps]
    rows += [(PHASE_OPS, name, fn) for name, fn in ops_steps]
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
    # PRP-41 — buffer for intermediate events the HITL step emits via
    # ``client.yield_event(...)``. Drained + stamped with the row's
    # index/phase fields immediately BEFORE each terminal step_complete.
    intermediate_events: list[StepEvent] = []

    async with _Client(app, event_sink=intermediate_events) as client:
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
            # PRP-41 — drain any intermediate events the step buffered BEFORE
            # the terminal step_complete. Stamp the row's index/phase fields
            # so the FE state machine processes them as if they were emitted
            # by the orchestrator. Order matters: intermediate events must
            # land before the terminal so "awaiting_approval" precedes
            # "approved" in the WS stream.
            for ev in intermediate_events:
                ev.step_index = index
                ev.total_steps = total
                ev.phase_index = phase_index
                ev.phase_total = phase_total
                # phase_name is set by the step fn already, but mirror in case.
                ev.phase_name = phase_name
                yield ev
            intermediate_events.clear()
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
