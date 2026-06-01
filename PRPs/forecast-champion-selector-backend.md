name: "Forecast Champion Selector Backend"
description: |
  Backend foundation for an interactive Forecast Champion Selector. Adds a
  first-class `model_selection` vertical slice that validates a store/product
  pair, recommends/selects backtest settings, runs candidate model comparison,
  ranks results by WAPE/sMAPE/bias/MAE, persists an auditable selection record,
  and optionally trains/predicts with the winning model. This PRP deliberately
  scopes UI work out; it creates the stable backend contract the UI can consume.

**Created:** 2026-06-01 · **Refined:** 2026-06-01 (signatures verified against live code)
**Current repo base observed:** `dev` at `1b4c3f3` (`Merge pull request #352 ...fix/agents-finalizer-fallback`)
**Current alembic head observed:** `c1d2e3f40512` (`create_batch_tables`) — verify with `uv run alembic heads` at implementation time and chain to whatever head exists THEN.
**Working-tree caveat observed:** `docker-compose.lan.yml` is an untracked local dogfood override; do not commit it.
**Tracking issue:** create before implementation, suggested title `feat(api): add forecast champion selector backend`.
**Suggested branch:** `feat/forecast-champion-selector-backend` (off `dev`, per `.claude/rules/branch-naming.md`).
**Commit scope:** `api` (cross-feature backend wiring + new slice + `app/main.py`) and `db` (migration). Every commit references the tracking issue.

---

## VALIDATE — Missing Backend Surface Check

The lower-level primitives exist; the business workflow does not.

### Reusable backend primitives already present (verified)

- `POST /backtesting/run` → single store/product/model backtest with fold metrics,
  aggregated metrics, optional baselines, bucketed horizon metrics, leakage status.
  `app/features/backtesting/routes.py:24` (router), `:60` (handler).
  **Service entry point is `BacktestingService().run_backtest(db, store_id, product_id, start_date, end_date, config)`** — see verified signature below.
- `POST /forecasting/train` → trains one model; supports `feature_frame_version` (1|2) and
  `feature_groups`. `app/features/forecasting/routes.py:25`. Service:
  `ForecastingService().train_model(db, store_id, product_id, train_start_date, train_end_date, config, *, feature_frame_version=1, feature_groups=None) -> TrainResponse`.
- `POST /forecasting/predict` → predicts from a saved bundle. Service:
  `ForecastingService().predict(store_id, product_id, horizon, model_path) -> PredictResponse`
  (**no db arg** — loads bundle from disk; rejects feature-aware models, `service.py:491`).
- `POST /batch/forecasting` fan-out exists but pins metrics to five keys and does **not**
  expose fold-level chart data — NOT suitable for this slice's chart payload.
- `GET /dimensions/stores`, `GET /dimensions/products` provide dimension metadata.
- `app/features/ops/service.py` is the canonical read-only cross-slice ORM aggregation precedent.

### Backend pieces missing for the full feature

- No `app/features/model_selection/` slice; no `POST /model-selection/run`; no persisted
  `model_selection_run` table; no orchestration of pair-validation → candidate backtests →
  ranking → optional final train → optional predict; no pair-availability endpoint; no
  backend ranking/confidence policy; no deterministic business explanation layer; no
  chart-ready comparison payload.
- Batch/Job model allow-lists are narrower than forecasting's full `ModelConfig` union, and
  job/batch training does not pass `feature_frame_version`/`feature_groups`. **Therefore this
  slice calls the direct backtesting/forecasting services**, not batch/jobs.

---

## BRAINSTORM / RERANK — Chosen Scope

Chosen: **Option A — Backend foundation only** (new `model_selection` slice: pair
availability, candidate comparison, ranking/confidence, persisted audit, optional
train/predict, chart-ready payload). It covers every backend gap the eventual UI needs,
reuses mature primitives, creates a stable testable contract, and avoids frontend coupling.

Non-goals (out of scope for this PRP):

- No React page / shadcn UI / frontend routing.
- No agent tool, no `agent_require_approval` entry, no agent mutation surface.
- No alias auto-promotion (the selector may *recommend* a winner; alias mutation is a future
  approval-gated PRP).
- No batch model-zoo retrofit. Use direct services for the single selected pair.

---

## Goal

**Feature Goal:** A backend-only Forecast Champion Selector vertical slice that, given one
store/product pair + window + horizon + candidate models, validates data availability, runs
comparable backtests for every candidate, deterministically ranks completed candidates,
computes a recommendation confidence with reasons, persists an auditable selection run, and
returns chart-ready comparison data plus optional final-model training and forecast output.

**Deliverable:** `app/features/model_selection/` slice (`models.py`, `schemas.py`,
`ranking.py`, `explanations.py`, `service.py`, `routes.py`, `tests/`) + one Alembic migration
creating `model_selection_run`, wired in `app/main.py`.

**Success Definition:** `POST /model-selection/run` with the default five candidates against
a seeded pair returns HTTP 200 with a persisted `selection_id`, a non-empty deterministic
`ranking`, a `winner`, a `recommendation_confidence`, and a `chart_data` payload; the row is
retrievable by `GET /model-selection/{selection_id}`; all validation gates pass.

## Why

- Business users want to ask "which model should I use for this store/product?" without
  manually coordinating `/backtesting/run`, `/forecasting/train`, `/forecasting/predict`.
- The UI needs **one stable backend contract** rather than re-implementing ranking in TypeScript.
- A persisted selection run makes the model choice auditable: which models competed, which
  window, which policy, and why the winner won.
- Keeps the single-host architecture intact — no queue, no cloud SDK, no new service.

## What

### New endpoints (all under `APIRouter(prefix="/model-selection", tags=["model-selection"])`)

```http
GET  /model-selection/availability?store_id=...&product_id=...&forecast_horizon=14
POST /model-selection/run
GET  /model-selection/{selection_id}
GET  /model-selection/{selection_id}/ranking
POST /model-selection/{selection_id}/train-winner
POST /model-selection/{selection_id}/predict
```

### Core request shape (`POST /model-selection/run`)

```json
{
  "store_id": 1,
  "product_id": 1,
  "selection_window": { "start_date": "2026-01-01", "end_date": "2026-05-31" },
  "forecast_horizon": 14,
  "ranking_metric": "wape",
  "split_config": { "strategy": "expanding", "n_splits": 5, "min_train_size": 30, "gap": 0, "horizon": 14 },
  "candidate_models": [
    {"model_type": "naive", "params": {}},
    {"model_type": "seasonal_naive", "params": {"season_length": 7}},
    {"model_type": "moving_average", "params": {"window_size": 7}},
    {"model_type": "regression", "params": {}},
    {"model_type": "prophet_like", "params": {}}
  ],
  "feature_frame_version": 1,
  "feature_groups": null,
  "auto_train_winner": false,
  "auto_predict": false
}
```

### LOCKED decisions (these remove every "choose one and test" ambiguity in the prior draft)

1. **HTTP status codes:** `POST /model-selection/run` → **200** (synchronous, returns the
   full result, mirrors `/backtesting/run` which is `status.HTTP_200_OK`). All GETs → 200.
   `train-winner` / `predict` → 200. (201 is *not* used; the row is an audit side-effect, the
   response is the computed result. Tests lock 200.)
2. **Availability gate:** if `availability.status == "unusable"`, **fail fast** — persist the
   row as `status="failed"` with `error_message`, then raise `BadRequestError` (RFC 7807 **400**).
   Nothing is ranked.
3. **All-candidates-fail (availability OK but every backtest errored):** **do NOT raise.**
   Persist `status="failed"`, `ranking_result` with the failed entries, `winner=null`, and
   return **200** with the failed-status response. Rationale: the run was validly attempted and
   is an auditable outcome, not a client error. (Distinguish from #2: #2 is "we never started".)
4. **Per-candidate backtest config:** `BacktestConfig(split_config=req.split_config,
   model_config_main=<ModelConfig>, include_baselines=False, store_fold_details=True)`.
   `include_baselines=False` because each candidate is itself a `model_config_main` run — we do
   not want N redundant baseline runs. `store_fold_details=True` so fold chart data is populated.
5. **`split_config.horizon` MUST equal `forecast_horizon`** (model-validator on the request).
   The window dates from `selection_window` become `run_backtest`'s `start_date`/`end_date`.
6. **Ranking determinism:** primary = `ranking_metric` (default `"wape"`), then the fixed
   tie-break chain `wape → smape → abs(bias) → mae → model_type`. With the default, the sort key
   is exactly `(wape, smape, abs(bias), mae, model_type)` (success-criteria order). A non-default
   `ranking_metric` puts that metric first, remaining chain follows excluding the duplicate.
7. **`auto_predict=True` requires `auto_train_winner=True`** (request model-validator) — predict
   needs a freshly trained `final_model.model_path` from this run.

### Success Criteria

- [ ] `app/features/model_selection/` slice exists and is wired in `app/main.py`.
- [ ] `POST /model-selection/run` with the default five candidates returns a persisted
      `status="completed"` (or `"partial"`) selection with `winner`, `ranking`, confidence, and `chart_data`.
- [ ] `GET /model-selection/availability` returns: `first_sales_date`, `last_sales_date`,
      `observed_days`, `expected_calendar_days`, `coverage_ratio`, `missing_days`,
      `zero_sale_days`, `promotion_days` (or `null` + warning), `average_daily_demand`,
      `status` ∈ `{ready, limited, unusable}`, and `recommended_split_config`.
- [ ] Ranking is deterministic per LOCKED decision #6.
- [ ] Partial success supported (LOCKED #3): failed candidates appear in `ranking` with error
      detail and are excluded from winner selection; a valid candidate still wins.
- [ ] `auto_train_winner=True` stores `final_model.model_path` via the **direct**
      `ForecastingService.train_model`, preserving `feature_frame_version` + `feature_groups`.
- [ ] `auto_predict=True` (with train) returns forecast points + total/average demand summary.
- [ ] New migration creates `model_selection_run` with JSONB snapshots and named indexes;
      `downgrade` drops indexes then table cleanly.
- [ ] `app/core/tests/test_strict_mode_policy.py` stays green for all new strict request schemas.
- [ ] No agent tools / `agent_require_approval` entries; no frontend files; no cloud SDK.

## All Needed Context

### Documentation & References

```yaml
# PRP conventions
- file: PRPs/templates/prp_base.md
  why: Base template (Goal/Context/Blueprint/Validation). NOTE — the user referenced a
       "PRPs/prp-readme.md.md"; it does NOT exist (`find PRPs -iname '*readme*'` empty on 2026-06-01).
- file: PRPs/PRP-33-batch-runner-mvp.md
  why: Strongest backend vertical-slice precedent — migration assertions, strict-mode gotchas,
       route/test detail. Mirror its structure.
- file: PRPs/PRP-28-forecast-explainability-driver-attribution.md
  why: Read/composition-slice precedent consuming existing contracts; deterministic explanation layer.
- docfile: PRPs/ai_docs/forecast-champion-selector-backend-research.md
  why: External-lib + runtime verification (FastAPI APIRouter, Pydantic strict, JSONB, Alembic
       create_index, sklearn TimeSeriesSplit). Versions: pydantic 2.12.5, sqlalchemy 2.0.46,
       sklearn 1.8.0, fastapi 0.128.0, alembic 1.18.4.

# Verified service contracts to reuse (DO NOT re-derive — exact signatures below in Gotchas)
- file: app/features/backtesting/service.py
  why: BacktestingService().run_backtest(db, store_id, product_id, start_date, end_date, config). :213
- file: app/features/backtesting/schemas.py
  why: SplitConfig :24, BacktestConfig :81, BacktestResponse :257, ModelBacktestResult :180,
       FoldResult :147. aggregated_metrics keys = {mae,rmse,smape,wape,bias}.
- file: app/features/backtesting/routes.py
  why: EXACT route error-mapping pattern to mirror (try/except ValueError->BadRequestError,
       SQLAlchemyError->DatabaseError; service instantiated as BacktestingService()). :60-140
- file: app/features/forecasting/service.py
  why: ForecastingService().train_model :247 (db first; feature_frame_version/feature_groups
       keyword-only after *), predict :402 (NO db). Lazy cross-slice import precedent :55-61, :967.
- file: app/features/forecasting/schemas.py
  why: ModelConfig union :417-429 (flat members, model_type discriminator, NO module-level helper);
       TrainResponse.model_path :540; PredictResponse.forecasts :605; ForecastPoint :574.
- file: app/features/data_platform/models.py
  why: Store :40 (business key `code`, not store_code), Product :68 (`sku`, `launch_date`),
       SalesDaily :172 (date/store_id/product_id/quantity/unit_price/total_amount), Promotion :274.
- file: app/features/ops/service.py
  why: Read-only cross-slice ORM aggregation precedent — module-scope ORM-model imports, stateless
       service, db: AsyncSession per method, func.min/max/count/sum + group_by style. :225, :456.
- file: app/features/analytics/routes.py
  why: validate_date_range :36 (raises BadRequestError, inverted-range + 730-day-max). CANNOT be
       cross-slice imported — reimplement the two checks locally raising BadRequestError.
- file: app/core/exceptions.py
  why: BadRequestError(400) :152, NotFoundError(404) :64, DatabaseError(500) :108,
       ConflictError(409) :130, UnprocessableEntityError(422) :174. Each: (message=..., details=None).
- file: app/core/problem_details.py
  why: RFC 7807 envelope; never raise bare HTTPException with raw strings.
- file: app/core/config.py
  why: get_settings() cached singleton :225; Settings(BaseSettings) :62; add a plain typed attr
       with literal default; env var = UPPER_SNAKE of the field name.
- file: app/core/database.py
  why: Base (ORM declarative base) + get_db dependency used by routes/tests.
- file: app/shared/models.py
  why: TimestampMixin (created_at/updated_at, server_default func.now(), updated_at onupdate). Mix in first.
- file: app/main.py
  why: Router wiring — `from app.features.<slice>.routes import router as <slice>_router` (:18-26),
       `app.include_router(<slice>_router)` with NO prefix at include (:137-155), inside create_app().
- file: app/core/tests/test_strict_mode_policy.py
  why: AST policy — scans app/features/*/schemas.py; any ConfigDict(strict=True) model field typed
       date/datetime/time/UUID/Decimal (anywhere in the annotation) MUST carry Field(strict=False, ...).

# Migration / test patterns
- file: alembic/versions/c1d2e3f40512_create_batch_tables.py
  why: JSONB via `from sqlalchemy.dialects import postgresql` -> postgresql.JSONB(astext_type=sa.Text());
       named CheckConstraint; op.create_index (op.f for single-col, explicit name for composite);
       sa.DateTime(timezone=True) server_default sa.text("now()"); downgrade drops indexes THEN table.
- file: app/features/batch/models.py
  why: ORM JSONB via `from sqlalchemy.dialects.postgresql import JSONB` (bare); Mapped[]+mapped_column;
       status as String + default=Enum.PENDING.value + CheckConstraint in __table_args__; TimestampMixin.
- file: app/features/batch/schemas.py
  why: Strict request pattern — ConfigDict(strict=True), Literal[...] for JSON enums, Field(strict=False)
       on date fields (:132-133), @model_validator cross-field checks.
- file: app/features/explainability/tests/test_routes.py
  why: ASGITransport + AsyncClient + app.dependency_overrides[get_db]; RFC 7807 4-key body assert; async tests.
- file: app/features/explainability/tests/conftest.py
  why: Integration fixture — real engine from get_settings().database_url, prefix-scoped teardown in finally.

# External official docs (verified in research doc)
- url: https://fastapi.tiangolo.com/tutorial/bigger-applications/
  why: APIRouter prefix/tags multi-file pattern.
- url: https://pydantic.dev/docs/validation/latest/concepts/strict_mode/
  why: strict mode + field-level Field(strict=False) override (runtime-verified, pydantic 2.12.5).
- url: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#json-types
  why: JSONB column type for audit snapshots.
- url: https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.create_index
  why: create_index signature (alembic 1.18.4: index_name, table_name, columns, *, unique, **kw).
- url: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
  why: split semantics (sklearn 1.8.0 signature: n_splits, *, max_train_size, test_size, gap).
```

### Current Codebase Tree (relevant slices)

```bash
app/features/
├── analytics/       # KPI/drilldown/timeseries; validate_date_range lives in routes.py (slice-local)
├── backtesting/     # single-pair single-model backtesting; fold/chart data via store_fold_details
├── batch/           # batch fan-out; pinned 5-key metrics; NO fold chart data
├── data_platform/   # shared ORM: Store, Product, SalesDaily, Promotion, InventorySnapshotDaily, ...
├── dimensions/      # store/product discovery
├── forecasting/     # direct train/predict; full ModelConfig union
├── jobs/            # train/predict/backtest job orchestration
├── ops/             # read-only cross-slice ORM aggregation precedent (OpsService)
└── registry/        # model runs, aliases, compare, artifact verify
alembic/versions/    # current head: c1d2e3f40512 (create_batch_tables)
```

### Desired Codebase Tree

```bash
app/features/model_selection/
├── __init__.py
├── models.py            # ModelSelectionRun ORM + ModelSelectionStatus enum
├── schemas.py           # strict request models + response models
├── ranking.py           # PURE: normalize metrics, filter, rank, confidence
├── explanations.py      # PURE: deterministic business summary + confidence_reasons
├── service.py           # ModelSelectionService: availability + orchestration (lazy cross-slice imports)
├── routes.py            # APIRouter(prefix="/model-selection")
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_models.py
    ├── test_schemas.py
    ├── test_ranking.py
    ├── test_explanations.py
    ├── test_service.py
    ├── test_routes.py
    └── test_routes_integration.py
alembic/versions/<rev>_create_model_selection_run.py
```

### Known Gotchas & VERIFIED Library/Internal Contracts

```python
# ── VERIFIED INTERNAL SIGNATURES (exact, read 2026-06-01) ─────────────────────
# BacktestingService.__init__(self) -> None      # takes NO db; instantiate as BacktestingService()
# await BacktestingService().run_backtest(
#     db, store_id, product_id, start_date, end_date, config: BacktestConfig
# ) -> BacktestResponse                            # service.py:213 ; db is FIRST arg
#
# ForecastingService.__init__(self) -> None
# await ForecastingService().train_model(
#     db, store_id, product_id, train_start_date, train_end_date, config: ModelConfig,
#     *, feature_frame_version: int = 1, feature_groups: list[str] | None = None
# ) -> TrainResponse                               # service.py:247 ; .model_path is the artifact path
# await ForecastingService().predict(
#     store_id, product_id, horizon, model_path     # NO db arg — loads bundle from disk
# ) -> PredictResponse                              # service.py:402 ; .forecasts: list[ForecastPoint]
#                                                   #   ForecastPoint: {date, forecast, lower_bound?, upper_bound?}
#   GOTCHA: predict() REJECTS feature-aware models (service.py:491). For a feature-aware winner,
#   auto_predict may raise; catch and surface a warning rather than failing the whole run.

# ── METRIC KEYS — CORRECTED (draft was incomplete) ────────────────────────────
# BacktestResponse.main_model_results.aggregated_metrics has FIVE keys:
#   {"mae", "rmse", "smape", "wape", "bias"}        # metrics.py:347 — draft MISSED "rmse"
# metric_std keys are SUFFIXED "{name}_stability" (a coefficient of variation, NOT raw std).
# sample_size is NOT in aggregated_metrics — derive it from fold actuals length
#   (sum of len(fold.actuals) across fold_results) or n_folds; normalize in ranking.py.
# Fold chart data path: BacktestResponse.main_model_results.fold_results[i].{dates, actuals, predictions}
#   populated ONLY when config.store_fold_details=True (LOCKED #4 sets it True).
# bucketed_aggregated_metrics lives on each ModelBacktestResult (optional, may be None).

# ── ModelConfig CONSTRUCTION — members are FLAT, no nested "params" ────────────
# The request uses {"model_type": "seasonal_naive", "params": {"season_length": 7}} but the
# ModelConfig members are FLAT (SeasonalNaiveModelConfig has model_type + season_length at top
# level). There is NO module-level TypeAdapter/helper. Build at the service boundary by FLATTENING:
#   from pydantic import TypeAdapter
#   from app.features.forecasting.schemas import ModelConfig
#   _MODEL_CONFIG_ADAPTER = TypeAdapter(ModelConfig)
#   cfg = _MODEL_CONFIG_ADAPTER.validate_python({"model_type": c.model_type, **c.params})
# Members are frozen + extra="forbid", so unknown params raise a ValidationError (good — surfaces
# bad candidate params as a failed candidate with a reason). Do this import LAZILY in-method.
# Valid model_type values (full union, forecasting/schemas.py:417): naive, seasonal_naive,
#   moving_average, weighted_moving_average, seasonal_average, trend_regression_baseline,
#   random_forest, lightgbm, xgboost, regression, prophet_like.
#   (lightgbm/xgboost are opt-in extras — may ImportError at runtime; treat as a failed candidate.)

# ── CROSS-SLICE IMPORT RULE ───────────────────────────────────────────────────
# Vertical-slice rule: app/features/X must not import app/features/Y at MODULE scope when it
# would close an alembic cold-boot cycle. model_selection is a NEW leaf (nothing imports it), but
# to match the BatchService/forecasting precedent and stay safe, import the SERVICE CLASSES
# (BacktestingService, ForecastingService) and the ModelConfig TypeAdapter LAZILY inside the
# methods that use them. Read ORM models (Store/Product/SalesDaily/Promotion) at module scope —
# that mirrors OpsService and is the sanctioned read-only ORM surface.

# ── validate_date_range IS NOT IMPORTABLE ─────────────────────────────────────
# It lives in app/features/analytics/routes.py (slice-local). Reimplement the two checks locally
# (inverted range; max-span) raising app.core.exceptions.BadRequestError, OR rely on schema
# validators. Do NOT import across the slice boundary.
# NOTE: analytics' max-span is settings.analytics_max_date_range_days (configurable, ~730), not a
#   hardcoded constant — pick your own local bound (or reuse the setting) when reimplementing.

# ── STRICT-MODE POLICY (app/core/tests/test_strict_mode_policy.py) ────────────
# Every request model with model_config = ConfigDict(strict=True) MUST add Field(strict=False, ...)
# to EVERY field typed date|datetime|time|UUID|Decimal (incl. inside Optional/Annotated/list/dict).
# Use Literal[...] for JSON enum strings (NOT a str-Enum — strict won't coerce). The AST walker does
# NOT follow inheritance, so set ConfigDict(strict=True) on each concrete request model directly.

# ── ORM / MIGRATION QUIRKS ────────────────────────────────────────────────────
# JSONB import DIFFERS by layer:
#   migration: from sqlalchemy.dialects import postgresql  ->  postgresql.JSONB(astext_type=sa.Text())
#   ORM:       from sqlalchemy.dialects.postgresql import JSONB  ->  mapped_column(JSONB)
# Status enum enforced via CheckConstraint("status IN (...)", name="ck_...") in BOTH migration and
#   ORM __table_args__; ORM column is String(N) with default=ModelSelectionStatus.PENDING.value.
# created_at/updated_at come from TimestampMixin (app/shared/models.py) — declare class as
#   `class ModelSelectionRun(TimestampMixin, Base)` (mixin FIRST). Declare completed_at explicitly.
# Migration down_revision: chain to the CURRENT head at implementation time (observed c1d2e3f40512);
#   run `uv run alembic heads` to confirm — do NOT hardcode this PRP's observed value blindly.

# ── DATA-PLATFORM COLUMN NAMES (availability aggregation) ─────────────────────
# Store.id (int PK), Store.code (business key). Product.id, Product.sku, Product.launch_date (date|None).
# SalesDaily: .date (Date FK calendar.date), .store_id, .product_id, .quantity (Integer, CHECK >=0),
#   .unit_price (Numeric), .total_amount (Numeric). Grain unique (date, store_id, product_id).
#   => For ONE pair: count(distinct date) == count(*); zero_sale_days = count where quantity == 0.
# Promotion: per-product (product_id NOT NULL), store_id NULLABLE (NULL = CHAIN-WIDE, applies to all
#   stores), date RANGE [start_date, end_date], kind in {pct_off,bogo,bundle,markdown}. To count
#   promotion_days for (store, product) within the window, JOIN promotion to the pair's sales dates
#   ON sd.date BETWEEN p.start_date AND p.end_date AND p.product_id=? AND (p.store_id=? OR p.store_id IS NULL),
#   then COUNT(DISTINCT sd.date). If this proves complex/edge-casey, return promotion_days=None with a
#   warning string (acceptable per Success Criteria) — do NOT sum (end-start) per row (double-counts overlaps).

# ── RUNTIME-VERIFIED LIBRARY FACTS (research doc) ─────────────────────────────
# Pydantic 2.12.5 accepts Field(strict=False) date string under a strict model. sklearn 1.8.0
# TimeSeriesSplit(n_splits, *, max_train_size, test_size, gap). FastAPI 0.128.0 APIRouter(prefix=...).
# Alembic 1.18.4 Operations.create_index(index_name, table_name, columns, *, unique, **kw).
```

## Implementation Blueprint

### Data Models and Schemas

`app/features/model_selection/models.py`:

```python
from datetime import date, datetime
from enum import Enum
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import TimestampMixin


class ModelSelectionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ModelSelectionRun(TimestampMixin, Base):   # TimestampMixin FIRST → created_at/updated_at
    __tablename__ = "model_selection_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    selection_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    store_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    forecast_horizon: Mapped[int] = mapped_column(Integer)
    ranking_metric: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=ModelSelectionStatus.PENDING.value, index=True)
    candidate_models: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    availability_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ranking_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    winner_model_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    winner_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    final_model_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    forecast_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    business_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','partial','failed')",
            name="ck_model_selection_run_valid_status",
        ),
        Index("ix_model_selection_run_store_product_created", "store_id", "product_id", "created_at"),
        Index("ix_model_selection_run_status_created", "status", "created_at"),
    )
```

`app/features/model_selection/schemas.py` — strict request models + response models:

- `SelectionWindow(start_date, end_date)` — `ConfigDict(strict=True)`, both dates `Field(strict=False, ...)`.
- `CandidateModelConfig(model_type: Literal[<11 model_types>], params: dict[str, Any] = {})`.
- `RankingPolicy(minimum_sample_size: int = 0, high_confidence_rel_improvement: float = 0.10,
   max_acceptable_abs_bias: float = ...)` — defaults; snapshotted into `policy_snapshot`.
- `ModelSelectionRunRequest` — `ConfigDict(strict=True)`; fields: `store_id`, `product_id`,
  `selection_window`, `forecast_horizon` (int, ge=1, le=90), `ranking_metric: Literal["wape","smape","mae","bias"]="wape"`,
  `split_config: SplitConfig` (reuse backtesting's? — see NOTE), `candidate_models: list` (min_length=1, max_length=10),
  `feature_frame_version: int = 1` (ge=1, le=2), `feature_groups: list[str] | None = None`,
  `ranking_policy: RankingPolicy = Field(default_factory=RankingPolicy)`,
  `auto_train_winner: bool = False`, `auto_predict: bool = False`.
  - `@model_validator(mode="after")`: `split_config.horizon == forecast_horizon` (LOCKED #5);
    `auto_predict implies auto_train_winner` (LOCKED #7).
  - NOTE on `split_config`: `backtesting.schemas.SplitConfig` is `frozen=True, extra="forbid"`
    (NOT strict). Either (a) reuse it directly (import lazily is unnecessary for a schema type —
    it's safe at module scope since backtesting.schemas has no cycle back to model_selection), or
    (b) define a local `SplitSettings` mirror. **Prefer reusing `SplitConfig`** to avoid drift; it
    already validates n_splits/min_train_size/gap/horizon. Since it is not strict-mode, its `date`-free
    fields don't trip the strict-mode linter.
**Response + intermediate models (plain `BaseModel` — outputs don't need `strict=True`). These
fields ARE the stable contract the UI consumes; specify them exactly, do not improvise.**

```python
# ── intermediate (service-internal, also embedded in JSONB) ───────────────────
class CandidateResult(BaseModel):            # what shape_candidate()/shape_failed_candidate() return
    model_type: str
    params: dict[str, Any]                   # ORIGINAL candidate params — REQUIRED so the winner can be rebuilt (pseudocode L667)
    failed: bool
    error: str | None = None                 # reason when failed=True
    aggregated_metrics: dict[str, float] | None = None   # raw 5-key dict from backtest (mae,rmse,smape,wape,bias) or None
    sample_size: int = 0                      # RULE: sum(len(fold.actuals)) across main_model_results.fold_results
    config_hash: str | None = None
    folds: list[FoldChart] = []              # per-fold chart points (empty when failed)

class FoldChart(BaseModel):
    fold_index: int
    dates: list[date]
    actuals: list[float]
    predictions: list[float]

class ModelRankEntry(BaseModel):             # one row in the ranking table (valid OR excluded)
    rank: int | None                          # 1-based; None when excluded/failed
    model_type: str
    params: dict[str, Any]                    # carried through (see CandidateResult.params)
    included: bool                            # False = failed or filtered out
    exclusion_reason: str | None = None
    metrics: dict[str, float] | None = None   # normalized {wape,smape,mae,rmse,bias,sample_size}

class RankingResult(BaseModel):              # Pydantic (model_dump'd into ranking_result JSONB, L663)
    winner: ModelRankEntry | None
    entries: list[ModelRankEntry]             # ALL candidates, ranked-then-failed, never hidden
    confidence: Literal["high", "medium", "low"]
    reasons: list[str]

class WinnerSummary(BaseModel):
    model_type: str
    params: dict[str, Any]
    metrics: dict[str, float]                 # normalized winner metrics
    rank: int                                 # always 1

class ChartData(BaseModel):                  # chart-ready comparison payload (Success Criteria deliverable)
    wape_by_model: dict[str, float]           # {model_type: wape}  → WAPE bar chart
    bias_by_model: dict[str, float]           # {model_type: bias}  → bias chart
    fold_stability: dict[str, list[float]]    # {model_type: per-fold wape}  → stability lines
    winner_actual_vs_predicted: list[FoldChart]   # the WINNER's folds only → actual-vs-predicted overlay

class PairAvailabilityResponse(BaseModel):
    store_id: int
    product_id: int
    first_sales_date: date | None
    last_sales_date: date | None
    observed_days: int
    expected_calendar_days: int
    coverage_ratio: float
    missing_days: int
    zero_sale_days: int
    promotion_days: int | None                # None + a warning when not safely derivable
    average_daily_demand: float               # CAST float(...) — func.avg over Integer quantity returns Decimal
    status: Literal["ready", "limited", "unusable"]
    recommended_split_config: SplitConfig     # reuse backtesting.schemas.SplitConfig
    warnings: list[str] = []

class ForecastSummary(BaseModel):
    points: list[dict[str, Any]]              # ForecastPoint.model_dump(mode="json") list
    total_demand: float
    average_demand: float
    horizon: int

class ModelSelectionRunResponse(BaseModel):  # THE /run + /{id} contract
    selection_id: str
    store_id: int
    product_id: int
    status: Literal["pending", "running", "completed", "partial", "failed"]
    selection_window: SelectionWindow
    forecast_horizon: int
    ranking_metric: str
    availability: PairAvailabilityResponse | None
    ranking: list[ModelRankEntry]             # == RankingResult.entries
    winner: WinnerSummary | None
    recommendation_confidence: Literal["high", "medium", "low"] | None   # CANONICAL KEY (maps from RankingResult.confidence)
    confidence_reasons: list[str]             # == RankingResult.reasons
    chart_data: ChartData | None
    final_model: dict[str, Any] | None        # {"model_path": ...} when auto_train_winner
    forecast: ForecastSummary | None          # when auto_predict
    business_summary: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

class TrainWinnerResponse(BaseModel):
    selection_id: str
    model_type: str
    model_path: str

class PredictWinnerResponse(BaseModel):
    selection_id: str
    forecast: ForecastSummary
```

> **NAMING (resolves the only internal-consistency nit):** the response key is
> **`recommendation_confidence`** (Success Criteria + manual probe + Goal all use it).
> `RankingResult.confidence` is the service-internal field; `_response()` maps
> `RankingResult.confidence → ModelSelectionRunResponse.recommendation_confidence` and
> `RankingResult.reasons → confidence_reasons`. Tests assert the response key
> `recommendation_confidence`.

> **`self._response(row, ranking)` helper:** pure mapping `ModelSelectionRun` ORM row +
> `RankingResult` → `ModelSelectionRunResponse` (rehydrate `availability_snapshot`/`ranking_result`/
> `business_summary`/`forecast_result` JSONB back into the response models; build `chart_data` from
> the per-candidate `CandidateResult.folds` + normalized metrics; map the confidence keys per above).

### Implementation Tasks (dependency-ordered)

```yaml
Task 1 — Migration + ORM:
  RUN: uv run alembic heads   # confirm current head (observed c1d2e3f40512)
  CREATE alembic/versions/<rev>_create_model_selection_run.py:
    - down_revision = "<current head>"
    - MIRROR alembic/versions/c1d2e3f40512_create_batch_tables.py exactly:
      - from sqlalchemy.dialects import postgresql  ->  postgresql.JSONB(astext_type=sa.Text())
      - sa.DateTime(timezone=True), server_default=sa.text("now()") for created_at/updated_at
      - CheckConstraint name="ck_model_selection_run_valid_status"
      - op.create_index(op.f("ix_model_selection_run_selection_id"), ..., unique=True)
      - op.create_index("ix_model_selection_run_store_product_created", ..., ["store_id","product_id","created_at"])
      - op.create_index("ix_model_selection_run_status_created", ..., ["status","created_at"])
      - downgrade(): drop indexes (reverse order) THEN op.drop_table("model_selection_run")
  CREATE app/features/model_selection/models.py:   # as blueprint above; mirror batch/models.py

Task 2 — Schemas:
  CREATE app/features/model_selection/schemas.py:
    - all REQUEST models ConfigDict(strict=True); date fields Field(strict=False, ...)
    - Literal[...] for model_type + ranking_metric (NOT str-Enum)
    - candidate_models min_length=1 max_length=10 (or settings.model_selection_max_candidates)
    - @model_validator: horizon match (LOCKED #5) + auto_predict implies auto_train_winner (LOCKED #7)
    - reuse backtesting.schemas.SplitConfig (module-scope import OK; no cycle)

Task 3 — Ranking pure logic:
  CREATE app/features/model_selection/ranking.py:
    - NormalizedMetrics dataclass {wape, smape, mae, rmse, bias, sample_size}
    - normalize_metrics(aggregated_metrics, sample_size) -> NormalizedMetrics | None
        (None when the primary metric is missing OR NaN — use math.isnan guard; np.nan can appear,
         metrics.py:381; keys are mae/rmse/smape/wape/bias)
    - input: list[CandidateResult] (Task-2 schema). Each entry CARRIES model_type + params through to
      ModelRankEntry/WinnerSummary so the winner can be rebuilt (pseudocode L667 reads winner.params).
    - filter: not failed AND numeric primary metric AND sample_size >= policy.minimum_sample_size
    - rank key (default ranking_metric="wape"): (wape, smape, abs(bias), mae, model_type)  [LOCKED #6]
    - confidence (PIN the rel-improvement formula — denominator is the SECOND-place value):
        rel_improvement = (second.wape - winner.wape) / second.wape   # guard second.wape == 0 → treat as 0.0
        HIGH  : >=2 valid AND rel_improvement >= policy.high_confidence_rel_improvement (default 0.10)
                AND abs(winner.bias) <= policy.max_acceptable_abs_bias AND winner.sample_size sufficient
        MEDIUM: a valid winner exists but HIGH not met (narrow lead OR mild warnings) and >=2 valid
        LOW   : exactly one valid candidate, OR availability "limited", OR abs(bias) over threshold,
                OR rel_improvement < some near-tie epsilon (document the epsilon as a module constant)
    - emit human-readable reasons[] strings explaining the chosen level (consumed as confidence_reasons)
    - return RankingResult(winner, entries[ALL ranked-then-failed, never hidden], confidence, reasons)

Task 4 — Business explanation pure logic:
  CREATE app/features/model_selection/explanations.py:
    - explain_winner(ranking, availability) -> business_summary dict + confidence_reasons + warnings
    - translate WAPE/sMAPE/MAE/bias into short deterministic English; NO LLM, NO external call

Task 5 — Pair availability:
  CREATE ModelSelectionService.get_availability(db, store_id, product_id, forecast_horizon, split_config?) -> PairAvailabilityResponse:
    - verify Store and Product exist (NotFoundError if absent) via data_platform ORM (module-scope import OK)
    - aggregate SalesDaily for the pair (SQLAlchemy 2.0 async, mirror OpsService style):
        select(func.min(SalesDaily.date), func.max(SalesDaily.date),
               func.count(func.distinct(SalesDaily.date)), func.sum(SalesDaily.quantity),
               func.avg(SalesDaily.quantity),
               func.count().filter(SalesDaily.quantity == 0))   # FILTER aggregate; valid async idiom
        .where(SalesDaily.store_id == store_id, SalesDaily.product_id == product_id)
      # CAST: func.avg over Integer quantity returns Decimal; wrap average_daily_demand in float(...).
      # func.count().filter(...) is a Postgres FILTER aggregate (not shown in OpsService, but supported);
      #   alternatively a second scalar count with .where(quantity == 0). One round-trip is fine.
    - expected_calendar_days = (max_date - min_date).days + 1
    - coverage_ratio = observed_days / expected_calendar_days   (guard div-by-zero / no rows)
    - missing_days = expected_calendar_days - observed_days
    - promotion_days: JOIN promotion ON date BETWEEN start/end AND product_id match AND
        (store_id == X OR store_id IS NULL); COUNT(DISTINCT date). On any doubt → None + warning.
    - status (LOCKED thresholds):
        ready    if observed_days >= min_train_size + horizon*n_splits AND coverage_ratio >= 0.8
        limited  if observed_days >= min_train_size + horizon
        unusable otherwise
    - recommended_split_config: expanding, n_splits=min(5, feasible), min_train_size=30 (or adjusted),
        gap=0, horizon=forecast_horizon
    - NO rows for the pair -> status="unusable" with zeros/None and a warning

Task 6 — Orchestration:
  CREATE ModelSelectionService.run_selection(db, request) -> ModelSelectionRunResponse:
    - persist ModelSelectionRun(selection_id=uuid4().hex, status="running", snapshots); flush
    - availability = get_availability(...); persist snapshot
    - if availability.status == "unusable": status="failed", error_message, flush, raise BadRequestError  [LOCKED #2]
    - for each candidate (LAZY import services + ModelConfig adapter):
        try: cfg = flatten+validate ModelConfig; bt = await BacktestingService().run_backtest(
                 db, store_id, product_id, window.start, window.end,
                 BacktestConfig(split_config=req.split_config, model_config_main=cfg,
                                include_baselines=False, store_fold_details=True))
             collect aggregated_metrics, sample_size, fold dates/actuals/predictions for chart
        except Exception as exc: append failed entry with reason=str(exc)   [never hide — Anti-Patterns]
    - ranking = rank_candidates(results, req.ranking_policy, req.ranking_metric)
    - if ranking.winner is None: status="failed", persist ranking_result, flush, RETURN 200 response  [LOCKED #3]
    - if req.auto_train_winner:
        train = await ForecastingService().train_model(db, store_id, product_id, window.start, window.end,
                    winner_cfg, feature_frame_version=req.feature_frame_version, feature_groups=req.feature_groups)
        row.final_model_path = train.model_path
    - if req.auto_predict:   # requires auto_train_winner (validated)
        try: pred = await ForecastingService().predict(store_id, product_id, req.forecast_horizon, row.final_model_path)
             row.forecast_result = pred.model_dump(mode="json")
        except <feature-aware reject>: warning, leave forecast_result None
    - business_summary = explain_winner(ranking, availability)
    - status = "partial" if any candidate failed else "completed"; completed_at = datetime.now(UTC)
    - persist all JSONB via model_dump(mode="json"); flush + refresh; return response_from_row(row)
  ADD methods: get_selection(db, selection_id)->row|NotFoundError ; get_ranking ; train_winner ; predict_winner

Task 7 — Routes:
  CREATE app/features/model_selection/routes.py:
    - router = APIRouter(prefix="/model-selection", tags=["model-selection"])
    - GET /availability ; POST /run (200) ; GET /{selection_id} ; GET /{selection_id}/ranking ;
      POST /{selection_id}/train-winner ; POST /{selection_id}/predict
    - MIRROR backtesting/routes.py error mapping EXACTLY:
        service instantiated locally; try/except ValueError->BadRequestError(str(e)),
        SQLAlchemyError->DatabaseError("...", details={"error": str(e)}); NotFoundError from service bubbles.
    - structured logger.info events (see Integration Points)
  MODIFY app/main.py:
    - `from app.features.model_selection.routes import router as model_selection_router`  (alpha order with siblings)
    - `app.include_router(model_selection_router)`  inside create_app(), near backtesting/forecasting (NO prefix arg)

Task 8 — Tests (see Validation Loop for required names):
  CREATE app/features/model_selection/tests/{conftest,test_models,test_schemas,test_ranking,
    test_explanations,test_service,test_routes,test_routes_integration}.py
    - unit route tests: ASGITransport + app.dependency_overrides[get_db]=AsyncMock; 4-key RFC7807 assert
    - service tests: mock BacktestingService/ForecastingService (patch the lazy import targets) for
      happy/partial/all-fail/auto-train/auto-predict paths
    - integration tests (@pytest.mark.integration): real engine, prefix-scoped teardown in finally
```

### Pseudocode (CRITICAL details only)

```python
# ranking.py — deterministic, pure
def rank_candidates(results, policy, ranking_metric="wape"):
    valid, failed = [], []
    for r in results:
        m = normalize_metrics(r.aggregated_metrics, r.sample_size)  # keys: mae,rmse,smape,wape,bias
        if m is None or m.sample_size < policy.minimum_sample_size:
            failed.append(r.as_failed("missing/NaN primary metric or sample_size below minimum"))
            continue
        valid.append((r, m))
    if not valid:
        return RankingResult(winner=None, entries=failed, confidence="low", reasons=["no valid candidate"])
    primary = lambda m: getattr(m, ranking_metric) if ranking_metric != "bias" else abs(m.bias)
    ordered = sorted(valid, key=lambda p: (primary(p[1]), p[1].smape, abs(p[1].bias), p[1].mae, p[0].model_type))
    winner = ordered[0]
    return build_ranking_result(ordered, failed, policy)   # computes confidence vs 2nd place
```

```python
# service.py — orchestration (exact verified service calls)
async def run_selection(self, db, req):
    from pydantic import TypeAdapter                                  # lazy
    from app.features.backtesting.schemas import BacktestConfig       # lazy
    from app.features.backtesting.service import BacktestingService   # lazy
    from app.features.forecasting.schemas import ModelConfig          # lazy
    from app.features.forecasting.service import ForecastingService   # lazy
    adapter = TypeAdapter(ModelConfig)

    row = ModelSelectionRun(selection_id=uuid.uuid4().hex, status="running",
                            store_id=req.store_id, product_id=req.product_id,
                            start_date=req.selection_window.start_date, end_date=req.selection_window.end_date,
                            forecast_horizon=req.forecast_horizon, ranking_metric=req.ranking_metric,
                            candidate_models=[c.model_dump() for c in req.candidate_models],
                            policy_snapshot=req.ranking_policy.model_dump(mode="json"))
    db.add(row); await db.flush()

    availability = await self.get_availability(db, req.store_id, req.product_id, req.forecast_horizon, req.split_config)
    row.availability_snapshot = availability.model_dump(mode="json")
    if availability.status == "unusable":
        row.status = "failed"; row.error_message = "Insufficient data for model selection"
        await db.flush(); raise BadRequestError(message=row.error_message)   # LOCKED #2

    results = []
    for c in req.candidate_models:
        try:
            cfg = adapter.validate_python({"model_type": c.model_type, **c.params})   # FLATTEN
            bt = await BacktestingService().run_backtest(
                db, req.store_id, req.product_id,
                req.selection_window.start_date, req.selection_window.end_date,
                BacktestConfig(split_config=req.split_config, model_config_main=cfg,
                               include_baselines=False, store_fold_details=True))   # LOCKED #4
            results.append(shape_candidate(c, bt))
        except Exception as exc:
            results.append(shape_failed_candidate(c, exc))

    ranking = rank_candidates(results, req.ranking_policy, req.ranking_metric)
    row.ranking_result = ranking.model_dump(mode="json")
    if ranking.winner is None:
        row.status = "failed"; await db.flush(); return self._response(row, ranking)   # LOCKED #3 (HTTP 200)

    winner_cfg = adapter.validate_python({"model_type": ranking.winner.model_type, **ranking.winner.params})
    if req.auto_train_winner:
        train = await ForecastingService().train_model(
            db, req.store_id, req.product_id, req.selection_window.start_date, req.selection_window.end_date,
            winner_cfg, feature_frame_version=req.feature_frame_version, feature_groups=req.feature_groups)
        row.final_model_path = train.model_path
    if req.auto_predict and row.final_model_path:
        try:
            pred = await ForecastingService().predict(req.store_id, req.product_id, req.forecast_horizon, row.final_model_path)
            row.forecast_result = pred.model_dump(mode="json")
        except Exception as exc:   # e.g. feature-aware reject (forecasting service.py:491)
            row.forecast_result = None  # surface a warning in business_summary

    row.winner_model_type = ranking.winner.model_type
    row.winner_metrics = ranking.winner.metrics
    row.business_summary = explain_winner(ranking, availability)
    row.status = "partial" if any(r.failed for r in results) else "completed"
    row.completed_at = datetime.now(UTC)
    await db.flush(); await db.refresh(row)
    return self._response(row, ranking)
```

### Integration Points

```yaml
DATABASE:
  - migration: add `model_selection_run` (JSONB snapshots: candidate_models, policy_snapshot,
    availability_snapshot, ranking_result, winner_metrics, forecast_result, business_summary)
  - indexes: ix_model_selection_run_selection_id (unique), ix_model_selection_run_store_product_created,
    ix_model_selection_run_status_created
ROUTES:
  - app/main.py: import + app.include_router(model_selection_router)  (router carries its own prefix)
CONFIG (optional — only if used; then ADD to .env.example with UPPER_SNAKE + a comment, and a test):
  - model_selection_max_candidates: int = 10
  - model_selection_min_coverage_ratio: float = 0.8
  - model_selection_default_min_train_size: int = 30
OBSERVABILITY (structlog events, mirror ops/backtesting naming):
  - model_selection.run_received / .availability_checked / .candidate_completed /
    .candidate_failed / .run_completed / .run_failed
```

## Validation Loop

### Level 1 — Focused syntax & policy

```bash
uv run ruff check app/features/model_selection app/main.py alembic/versions
uv run ruff format --check app/features/model_selection app/main.py alembic/versions
uv run mypy app/features/model_selection app/main.py
uv run pyright app/features/model_selection app/main.py
uv run pytest app/core/tests/test_strict_mode_policy.py -v
```

### Level 2 — Focused unit tests

```bash
uv run pytest app/features/model_selection/tests -v -m "not integration"
```

Required test names:

- `test_schema_accepts_iso_dates_under_strict_model` (JSON path: `Model.model_validate({"start_date":"2026-01-01",...})`)
- `test_schema_rejects_auto_predict_without_train_winner`
- `test_schema_rejects_horizon_mismatch_between_split_and_forecast`
- `test_rank_candidates_wape_smape_abs_bias_mae_tie_break`
- `test_rank_candidates_excludes_missing_or_nan_metrics`
- `test_rank_candidates_normalizes_five_metric_keys_including_rmse`
- `test_confidence_high_when_winner_beats_second_by_10_percent`
- `test_availability_ready_limited_unusable_thresholds`
- `test_build_model_config_flattens_params` (e.g. seasonal_naive + {"season_length":7})
- `test_run_selection_partial_success_chooses_valid_winner`
- `test_run_selection_all_candidates_fail_returns_failed_status_not_500` (LOCKED #3)
- `test_run_selection_unusable_availability_raises_bad_request` (LOCKED #2)
- `test_run_selection_auto_train_passes_feature_frame_version_and_groups`
- `test_routes_return_problem_json_on_bad_request` (4-key RFC 7807 body)
- `test_response_uses_recommendation_confidence_key` (NOT `confidence`; maps from `RankingResult.confidence`)
- `test_winner_entry_carries_params_for_rebuild` (`ModelRankEntry.params` / `WinnerSummary.params` preserved)
- `test_chart_data_has_wape_bias_fold_stability_and_winner_actual_vs_predicted`

### Level 3 — Migration & integration

```bash
docker compose up -d
uv run alembic upgrade head
uv run pytest app/features/model_selection/tests -v -m integration
uv run alembic downgrade -1 && uv run alembic upgrade head   # downgrade/upgrade round-trips cleanly
```

Integration expectations:

- `model_selection_run` exists with the three named indexes.
- `POST /model-selection/run` persists a row; `GET /model-selection/{selection_id}` returns the same id.
- Availability detects an inserted pair with enough history (`ready`) and a too-short pair (`limited`/`unusable`).
- Partial failure persists the failed candidate reason and still ranks a valid winner.

### Level 4 — Full backend gates (must be green before PR)

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
uv run pytest -v -m "not integration"
uv run pytest -v -m integration
```

> Known-local-noise: mypy/pyright report pre-existing `lightgbm`/`xgboost` optional-dep import
> errors in `forecasting/`+`registry/` (untouched here; CI installs the extras). Do not "fix" them.

### Manual API probe (seeded DB; discover real store/product ids + date window first — IDs are
not guaranteed 1-based, see memory `seeder-does-not-reset-id-sequences`)

```bash
uv run uvicorn app.main:app --port 8123 &
curl -s "http://localhost:8123/model-selection/availability?store_id=5&product_id=8&forecast_horizon=14" | python3 -m json.tool
curl -s -X POST http://localhost:8123/model-selection/run -H "Content-Type: application/json" -d '{
  "store_id": 5, "product_id": 8,
  "selection_window": {"start_date": "2026-01-01", "end_date": "2026-05-31"},
  "forecast_horizon": 14,
  "split_config": {"strategy":"expanding","n_splits":5,"min_train_size":30,"gap":0,"horizon":14},
  "candidate_models": [
    {"model_type":"naive","params":{}},
    {"model_type":"seasonal_naive","params":{"season_length":7}},
    {"model_type":"moving_average","params":{"window_size":7}},
    {"model_type":"regression","params":{}},
    {"model_type":"prophet_like","params":{}}
  ],
  "auto_train_winner": false, "auto_predict": false
}' | python3 -m json.tool
```

Expected: HTTP 200; response carries `selection_id`, non-empty `ranking`, `winner.model_type`,
`recommendation_confidence`, `chart_data`.

## Final Validation Checklist

- [ ] New slice follows `app/features/<slice>/{models,schemas,service,routes,tests}.py`.
- [ ] Router wired in `app/main.py` (import alias + `include_router`, no prefix at include).
- [ ] Migration `down_revision` chains to the live head; downgrade drops indexes then table.
- [ ] Request schemas use `ConfigDict(strict=True)` + `Field(strict=False)` for every date field; strict-mode test green.
- [ ] All 4xx responses use project exceptions (`BadRequestError`/`NotFoundError`/`DatabaseError`) → RFC 7807.
- [ ] Ranking + explanation logic is pure and unit-tested; normalizer handles all five metric keys incl. `rmse`.
- [ ] Availability covered for ready/limited/unusable + no-rows.
- [ ] `auto_train_winner` uses direct `ForecastingService.train_model` (db first, feature args keyword-only).
- [ ] `auto_predict` handles feature-aware-reject gracefully (warning, not 500).
- [ ] LOCKED decisions #1–#7 are implemented and tested.
- [ ] No frontend files, no agent mutation surface, no managed-cloud SDK.
- [ ] All four Level-4 gates pass; `gh issue view <N>` confirms the referenced issue is open.

## Anti-Patterns to Avoid

- Don't implement the React UI; don't rank models in TypeScript — backend owns ranking/confidence.
- Don't use batch item metrics for fold-level chart data (batch has none) — use direct `BacktestingService` with `store_fold_details=True`.
- Don't import sibling feature *services* at module scope — lazy in-method (matches forecasting/BatchService precedent). ORM *models* at module scope is fine (OpsService precedent).
- Don't import `validate_date_range` from analytics — reimplement locally.
- Don't pass the candidate `params` as a nested dict to `ModelConfig` — FLATTEN (`{"model_type":..., **params}`).
- Don't assume four metric keys — there are five (`rmse` included); normalize, never index a raw shape blindly.
- Don't sum `(end_date - start_date)` for promotion days (double-counts overlaps; ignores chain-wide `store_id IS NULL`).
- Don't mutate aliases automatically; don't add an agent tool.
- Don't hide failed candidates — include them with `reason`.
- Don't use an LLM for explanations — deterministic text only.
- Don't raise on all-candidates-fail (LOCKED #3 → persist failed + return 200); DO raise on unusable availability (LOCKED #2 → 400).
- Don't build SQL with string concatenation; don't weaken strict-mode or leakage tests.

## Confidence Score

**9.5/10** for one-pass backend implementation success. The prior draft self-rated 8/10 with
"service signatures must be rechecked at implementation time" as the top risk — that risk is now
**retired**: every `run_backtest` / `train_model` / `predict` signature, the corrected five-key
metric shape, the `ModelConfig` flattening, the strict-mode rule, the migration/JSONB/exception
patterns, and seven previously-ambiguous decisions are verified and locked here. An independent
quality-gate pass confirmed every cited signature/line-number/field-name against live source
("tried to break the cited signatures and could not") and its findings — the full response/
intermediate contract (`CandidateResult`, `ModelRankEntry`, `RankingResult`, `WinnerSummary`,
`ChartData`, `ModelSelectionRunResponse`, …), the `recommendation_confidence` naming, the
`winner.params` carry-through, the `_response` mapping, and the rel-improvement denominator — are
now specified inline.

Residual risks:

- Per-candidate backtest runtime: five models × a multi-fold backtest is synchronous in-process.
  On a slow host the `/run` request can be slow (acceptable for a single pair; mirrors
  `/backtesting/run`). If it becomes a problem, a future PRP can move it behind the jobs slice.
- `promotion_days` derivation has real edge cases (chain-wide promos, overlapping ranges); the
  PRP explicitly permits `null + warning` as a correct fallback.
- `lightgbm`/`xgboost` candidates can `ImportError` when extras are absent — they degrade to a
  failed candidate with a reason (verified path), not a 500.
