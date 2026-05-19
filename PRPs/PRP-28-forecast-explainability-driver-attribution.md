name: "PRP-28 — Forecast Explainability & Driver Attribution"
description: |
  A new `explainability` vertical slice that produces structured, rule-based
  explanations for forecast and registry-run outcomes. Decomposes each of the
  three baseline forecasters (`naive`, `seasonal_naive`, `moving_average`) into
  named, interpretable demand drivers, layers advisory retail "reason codes"
  read time-safely from the data-platform fact tables, and surfaces an
  agent-readable summary plus confidence band and caveats. MVP is rule-based
  only — SHAP is deliberately excluded.

---

## Goal

Ship `app/features/explainability/` — a read-only vertical slice that, given a
baseline model + the series it was trained on, computes a `ForecastExplanation`:
an ordered list of `DriverContribution` objects (name, feature value,
contribution, direction), a list of `ReasonCode` objects (advisory retail
signals), a `confidence` band, `caveats`, and an `agent_summary` string.

End state:

- Three HTTP endpoints under a self-owned `/explain` namespace: explain a
  completed `predict` job, explain a registry run, and an ad-hoc
  `POST /explain/forecast`.
- A pure, deterministic rule-based explainer registry keyed by `model_type`
  (`NaiveExplainer`, `SeasonalNaiveExplainer`, `MovingAverageExplainer`).
- A reason-code engine reading `inventory_snapshot_daily`, `promotion`,
  `product.launch_date`, and `calendar` — never causal claims.
- A `forecast_explanation` persistence table + Alembic migration.
- Frontend explanation panels on the run-detail page and the forecast page.
- The slice imports **only** from `app/core/`, `app/shared/`, and reads
  data-platform / registry / jobs ORM models as read-only data contracts — it
  imports no other slice's `service.py`.

## Why

- **Business value** — ForecastLabAI trains models and reports point forecasts
  plus aggregate error metrics (MAE/sMAPE/WAPE/bias), but the *reasoning* is
  opaque. A demand planner sees a number on `/visualize/forecast` or a WAPE on
  the run-detail page with no narrative connecting the backend's time-safe
  signals to the forecast.
- **User impact** — planners cannot tell whether a high forecast reflects
  genuine demand or stockout-suppressed history; they cannot compare two models
  on *behaviour*, only on a single error scalar; the chat agents cannot cite
  feature-level reasons when recommending a model.
- **Integration** — the slice composes existing surfaces (forecasting, registry,
  jobs, data platform) without owning any of them; it re-loads the series
  itself and re-fits a baseline explainer from the stored `model_config` JSONB.
- **Honest by construction** — a naive forecaster's "explanation" *is* its last
  observation; there is no inference gap. Rule-based explainers are exact, not
  approximate. Retail reason codes are explicitly labelled as correlation, not
  causation (grounded in NIST AI RMF guidance).

## What

User-visible behaviour:

- `POST /explain/forecast` — given `{store_id, product_id, model_type, as_of_date,
  season_length?, window_size?}`, returns a `ForecastExplanation` for the h=1
  forecast that the named baseline model would produce on the series ending at
  `as_of_date`.
- `GET /explain/runs/{run_id}` — explains a registry `model_run`; reconstructs
  the baseline config from `model_run.model_config` JSONB and uses
  `data_window_end` as the cutoff.
- `GET /explain/jobs/{job_id}` — explains a completed `predict` job; pulls
  `store_id`/`product_id`/`model_type`/`horizon`/`forecasts` from `job.result`.
- Run-detail page gains a "Forecast Explanation" card; forecast page gains an
  explanation panel below the chart.

Technical requirements:

- New vertical slice, RFC 7807 errors, Pydantic v2 + SQLAlchemy 2.0 async.
- `mypy --strict` + `pyright --strict` + `ruff` clean.
- Alembic migration chaining to the current head.
- Every new module/endpoint/model/migration ships a matching test; new
  endpoints get a 2xx happy path + ≥1 error path.
- Time-safety: every series load and every reason-code DB query bounded
  `<= as_of_date` / `<= data_window_end`. No future data, ever.

### Success Criteria

- [ ] New `app/features/explainability/` slice with
      `models/schemas/service/routes/explainers/reason_codes/tests` — no import
      from another `app/features/<slice>/service.py`.
- [ ] 3 endpoints live: `GET /explain/runs/{run_id}`, `GET /explain/jobs/{job_id}`,
      `POST /explain/forecast` — registered in `app/main.py`.
- [ ] Rule-based explainers for `naive`, `seasonal_naive`, `moving_average`;
      each reproduces the corresponding forecaster's h=1 value **exactly**.
- [ ] `ForecastExplanation` returns `drivers`, `reason_codes`, `confidence`,
      `caveats`, `agent_summary`.
- [ ] Retail reason codes (stockout, promotion, lifecycle, holiday,
      insufficient-history) computed time-safely (`<= as_of_date`).
- [ ] `lightgbm` runs return a clean 400 (MVP scope guard); SHAP is NOT added to
      `pyproject.toml`.
- [ ] New Alembic migration chains to head **`43e35957a248`**, applies and rolls
      back cleanly.
- [ ] All errors RFC 7807; all request schemas Pydantic v2; the `date` field on
      the `strict=True` request body has `Field(strict=False, ...)`.
- [ ] Frontend explanation panel on run-detail + forecast pages;
      `pnpm tsc --noEmit` clean.
- [ ] `ruff` + `mypy --strict` + `pyright --strict` + unit + integration tests
      pass.

## All Needed Context

### Documentation & References

```yaml
# MUST READ - external docs
- url: https://fastapi.tiangolo.com/tutorial/bigger-applications/#apirouter
  why: APIRouter wiring, path operations, Depends — new slice router mirrors existing slices.

- url: https://docs.pydantic.dev/latest/concepts/models/
  section: model_config, ConfigDict, field_validator
  why: Response/request schema construction.

- url: https://docs.pydantic.dev/latest/concepts/strict_mode/
  section: strict mode, per-field overrides
  critical: ExplainForecastRequest has an `as_of_date` (date) field on a
            ConfigDict(strict=True) body — it MUST carry Field(strict=False).
            Without it every HTTP caller 422s on the ISO-string JSON path.

- url: https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html
  section: declarative mapping, JSONB columns, indexes
  why: ForecastExplanation ORM model + GIN-index pattern.

- url: https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.create_table
  section: create_table, postgresql.JSONB, create_index
  critical: down_revision MUST be "43e35957a248" (current head — verified via
            `uv run alembic heads`).

- url: https://www.nist.gov/itl/ai-risk-management-framework
  why: grounding for the "drivers describe correlation/contribution, not
       business causality" caveat baked into every explanation.

- url: https://shap.readthedocs.io/en/stable/generated/shap.TreeExplainer.html
  why: REFERENCE ONLY — do NOT implement. Read so the MVP `method` field and
       DriverContribution shape stay forward-compatible with SHAP output.

# MUST READ - codebase files (verified 2026-05-19 against HEAD on feat/scenarios-what-if-planning)
- file: app/features/forecasting/models.py
  why: |
    NaiveForecaster (class L138-220), SeasonalNaiveForecaster (L223-323),
    MovingAverageForecaster (L326-422), model_factory (L429-476). The
    explainers MIRROR this exact math (see "Forecaster math — verified" below).
    `ModelType` alias at L426.

- file: app/features/forecasting/schemas.py
  why: |
    ModelConfigBase (L22-49: ConfigDict(frozen=True, extra="forbid"),
    schema_version, config_hash()), NaiveModelConfig (L52-62),
    SeasonalNaiveModelConfig (L65-83: season_length default 7, ge=1, le=365),
    MovingAverageModelConfig (L86-104: window_size default 7, ge=1, le=90),
    LightGBMModelConfig (L107-144), ModelConfig union (L148-150).
    TrainRequest (L158-198) is the canonical strict=True body + Field(strict=False)
    date + field_validator pattern to copy.

- file: app/features/forecasting/service.py
  why: |
    _load_training_data (L314-367) — the EXACT query to load a
    (store_id, product_id, date-range) series. Mirror in
    ExplainabilityService._load_series. Do NOT import ForecastingService.

- file: app/features/registry/models.py
  why: |
    ModelRun ORM model (class L51, __tablename__ L80). JSONB columns:
    model_config L88, feature_config L89, metrics L99, config_hash L90,
    data_window_start/end L93-94, store_id/product_id L95-96. __table_args__
    (L125-143) — GIN index + CheckConstraint pattern to copy. TimestampMixin used.

- file: app/features/registry/service.py
  why: |
    get_run (L247-265): `select(ModelRun).where(ModelRun.run_id == run_id)` →
    `.scalar_one_or_none()`. _model_to_response (L658+) documents the alias
    quirk — ORM attr `model_config` vs schema field `model_config_data`.

- file: app/features/jobs/models.py
  why: |
    Job ORM model (class L68, __tablename__ L88). job_id L91, job_type L92,
    status L93, params L96, result L99 (JSONB nullable), run_id L112.
    JobType enum L29, JobStatus enum L43. __table_args__ L114-128.

- file: app/features/jobs/service.py
  why: |
    _execute_predict (L498-574) — a completed predict job's `result` dict has the
    keys {"store_id", "product_id", "model_type", "horizon", "duration_ms",
    "forecasts": [{"date": iso, "forecast": float, "lower_bound", "upper_bound"}]}.
    The explainer uses store_id/product_id/model_type/horizon/forecasts; duration_ms
    is ignored.

- file: app/features/scenarios/routes.py
  why: |
    The most recent slice (PRP-26) — canonical router style: APIRouter(prefix=...,
    tags=[...]), Depends(get_db), rich summary/description, SQLAlchemyError →
    DatabaseError, service-layer ValueError/FileNotFoundError → RFC 7807.

- file: app/features/scenarios/models.py
  why: |
    Most recent ORM model — JSONB columns, CheckConstraint, TimestampMixin,
    Base import. GOTCHA documented: SQLAlchemy reserves the attr name `metadata`.

- file: alembic/versions/43e35957a248_create_scenario_plan_table.py
  why: |
    Migration TEMPLATE — `revision = "43e35957a248"`, `down_revision = "378c112e4b32"`.
    The NEW migration's `down_revision` MUST be "43e35957a248" (this file is the
    current head). Shows op.create_table + postgresql.JSONB + server_default now().

- file: app/features/registry/routes.py
  why: |
    get_run (L200-232): canonical GET /{id} → service → None-check →
    `HTTPException(status.HTTP_404_NOT_FOUND, detail=...)`.

- file: app/core/exceptions.py
  why: |
    NotFoundError (L63-83, status 404), ValidationError (L85), DatabaseError
    (L107-127), BadRequestError (L151-171, status 400). All RFC 7807. Handlers
    already registered in main.py. NEVER bare `raise HTTPException(500, "string")`.

- file: app/core/database.py
  why: |
    get_db (L43-53) — auto-commits on success. Therefore the service should
    `flush`/`refresh`, NOT `commit`.

- file: app/main.py
  why: |
    Import block L15-31, include_router block L133-149. The new
    explainability_router registers here (after forecasting/backtesting/registry).

- file: app/features/data_platform/models.py
  why: |
    Verified column names: SalesDaily (date L199, store_id L200, product_id L201,
    quantity L202, unit_price L203). InventorySnapshotDaily (date L364,
    store_id L365, product_id L366, on_hand_qty L367, is_stockout L369).
    Promotion (product_id L300, store_id L301, kind L305, start_date L315,
    end_date L316). Product (launch_date L101). Calendar (date L146 PK,
    is_holiday L151, holiday_name L152).

- file: app/features/featuresets/tests/test_leakage.py
  why: |
    The LOAD-BEARING time-safety spec. Internalise the leakage rule before
    writing the series load and reason-code queries — bound everything
    `<= as_of_date`.

- file: app/features/forecasting/tests/test_service.py
  why: |
    UNIT service-test pattern — class-grouped tests, numpy fixtures,
    AsyncMock/MagicMock DB. Mirror this for explainability's unit test_service.py.

- file: app/features/forecasting/tests/test_routes.py
  why: |
    UNIT route-test pattern — httpx AsyncClient(ASGITransport) with the test-DB
    dependency override, 2xx happy path + error paths, RFC 7807 body assertions.
    Mirror this for explainability's unit test_routes.py.

- file: app/features/scenarios/tests/test_routes_integration.py
  why: |
    @pytest.mark.integration route-test pattern — httpx AsyncClient fixture,
    happy path + 404 path, idempotent (no pre-seed assumptions). NOTE: the
    scenarios slice ships ONLY an integration route test — there is no unit
    test_routes.py / test_service.py there; mirror the forecasting slice for
    the unit-level patterns.

- file: frontend/src/hooks/use-runs.ts
  why: TanStack Query hook pattern — useQuery/useMutation, queryKey, api<T>(), enabled.

- file: frontend/src/types/api.ts
  why: |
    ModelRun (L173), ForecastPoint (L102), Job (L234), ScenarioComparison
    (L775) interfaces — snake_case field names mirroring the Pydantic schemas.

- file: frontend/src/pages/explorer/run-detail.tsx
  why: Card / CardHeader / CardContent composition; gets a new Explanation card.

- file: frontend/src/pages/visualize/forecast.tsx
  why: useJob, in-page predict-job results, EmptyState; gets an explanation panel.

- doc: .claude/rules/ui-design.md + .claude/rules/shadcn-ui.md
  section: frontend toolchain, shadcn skill + MCP
  critical: Use the shadcn skill/MCP for any NEW shadcn component; reuse
            already-installed card/badge/table first; verify in a real browser.
```

### Current Codebase tree (relevant subset)

```bash
app/
  core/                       # config, database, exceptions, logging, problem_details
  shared/
    models.py                 # TimestampMixin
  features/
    data_platform/models.py   # SalesDaily, InventorySnapshotDaily, Promotion, Product, Calendar
    forecasting/{models,schemas,service,routes,persistence}.py + tests/
    registry/{models,schemas,service,routes}.py + tests/
    jobs/{models,schemas,service,routes}.py + tests/
    backtesting/{...}/        # FoldResult shape (read-only reference for full version)
    scenarios/{models,schemas,service,routes,adjustments}.py + tests/   # newest slice — PRP-26
alembic/versions/             # head: 43e35957a248_create_scenario_plan_table.py
frontend/src/
  hooks/use-runs.ts
  types/api.ts
  pages/explorer/run-detail.tsx
  pages/visualize/forecast.tsx
  components/                 # shadcn ui under components/ui/
```

### Desired Codebase tree (files added / modified)

```bash
app/features/explainability/                       # NEW SLICE
  __init__.py                                      # empty package marker
  schemas.py                                       # Pydantic v2: DriverContribution, ReasonCode,
                                                    #   ConfidenceLevel(enum), ForecastExplanation,
                                                    #   ExplainForecastRequest
  models.py                                        # ForecastExplanation ORM (forecast_explanation table)
  explainers.py                                    # BaseExplainer ABC + 3 explainers + explainer_factory
  reason_codes.py                                  # pure reason-code functions + build_caveats
  service.py                                       # ExplainabilityService
  routes.py                                        # APIRouter, 3 endpoints
  tests/
    __init__.py
    conftest.py                                    # series fixtures + sample ModelRun/Job rows
    test_explainers.py                             # unit (no DB) — forecaster-parity assertions
    test_reason_codes.py                           # unit (no DB)
    test_schemas.py                                # schema validation + JSON-path test
    test_service.py                                # service unit (mocked AsyncSession)
    test_routes.py                                 # route tests (2xx + 404 + 400)
    test_models_integration.py                     # @pytest.mark.integration — CRUD + CheckConstraints
    test_routes_integration.py                     # @pytest.mark.integration — end-to-end
alembic/versions/
  <newid>_create_forecast_explanation_table.py     # down_revision = "43e35957a248"
frontend/src/
  hooks/use-explanations.ts                        # NEW — 3 TanStack Query hooks
  components/explainability/explanation-panel.tsx  # NEW — drivers + reason codes + confidence + caveats
  components/explainability/explanation-panel.test.tsx  # NEW — vitest render test

# MODIFIED
app/main.py                                        # import + include explainability_router
frontend/src/types/api.ts                          # + DriverContribution, ReasonCode, ConfidenceLevel,
                                                    #   ForecastExplanation
frontend/src/pages/explorer/run-detail.tsx          # + Forecast Explanation card
frontend/src/pages/visualize/forecast.tsx           # + explanation panel for loaded predict job
docs/_base/API_CONTRACTS.md                         # + 3 endpoint rows (optional but recommended)
```

### Forecaster math — VERIFIED against `app/features/forecasting/models.py`

The explainer for a model MUST produce the **same h=1 value** the forecaster
would, or it is wrong. `test_explainers.py` asserts this against the real
forecasters.

```python
# NaiveForecaster (L156-199): fit stores last_value = float(y[-1]);
#   predict(h) → np.full(h, last_value).   h=1 forecast == y[-1].
#   fit raises ValueError("Cannot fit on empty array") when len(y) == 0.

# SeasonalNaiveForecaster (L252-302): fit stores _last_values = y[-season_length:];
#   predict(h): forecasts[k] = _last_values[k % season_length].
#   => h=1 forecast (k=0) == _last_values[0] == y[-season_length].
#   fit raises ValueError(f"Need at least {season_length} observations")
#   when len(y) < season_length.

# MovingAverageForecaster (L356-401): fit stores _forecast_value =
#   float(np.mean(y[-window_size:]));  predict(h) → np.full(h, _forecast_value).
#   => h=1 forecast == mean(y[-window_size:]).
#   fit raises ValueError(f"Need at least {window_size} observations")
#   when len(y) < window_size.
```

### Predict-job `result` shape — VERIFIED against `jobs/service.py:_execute_predict` (L559-574)

The relevant keys the explainer reads are `store_id`, `product_id`,
`model_type`, `horizon`, and `forecasts`. `_execute_predict` also emits a
`duration_ms` key, which the explainer ignores.

```python
{
  "store_id": int, "product_id": int, "model_type": str, "horizon": int,
  "duration_ms": float,                          # emitted by _execute_predict; ignored here
  "forecasts": [
    {"date": "YYYY-MM-DD", "forecast": float,
     "lower_bound": float | None, "upper_bound": float | None},
    ...
  ],
}
# NOTE: `run_id` in a predict job's *params* is the model-ARTIFACT key
# (model_{run_id}.joblib), NOT a registry run_id.
# as_of_date for a predict job = day before the FIRST forecast date.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: Current Alembic head is "43e35957a248" (create_scenario_plan_table).
#   The new migration's down_revision MUST be exactly "43e35957a248" or the
#   CI `migration-check` job fails. (The source plan said "378c112e4b32" —
#   that is STALE; PRP-26 added 43e35957a248 on top of it.)

# CRITICAL: Pydantic strict-mode policy (docs/_base/SECURITY.md, enforced by
#   app/core/tests/test_strict_mode_policy.py — an AST linter that FAILS CI).
#   On a ConfigDict(strict=True) request body, any field typed
#   date/datetime/time/UUID/Decimal MUST carry Field(strict=False, ...).
#   ExplainForecastRequest.as_of_date is a `date` → it MUST be
#   `Field(..., strict=False, ...)`. Response schemas are NOT strict=True → exempt.

# CRITICAL: Vertical-slice rule — app/features/explainability/ may import ONLY
#   from app/core/, app/shared/, and ORM models. It MUST NOT import
#   app.features.forecasting.service / registry.service / jobs.service /
#   backtesting.service. To explain a run/job, query ModelRun/Job ORM rows
#   directly. Importing registry.models.ModelRun and jobs.models.Job read-only
#   is the LOCKED decision (see "Open Questions & Decisions" #1) — same pattern
#   as importing data_platform.models. NEVER import a sibling slice's service.

# CRITICAL: Time-safety is LOAD-BEARING. Every series load and reason-code DB
#   query MUST be bounded `SalesDaily.date <= as_of_date` (and reason-code
#   tables `<= as_of_date`). Mirror forecasting/service.py:_load_training_data.
#   Treat any leakage path as a blocker, same discipline as test_leakage.py.

# GOTCHA: SQLAlchemy reserves the declarative attribute name `metadata` — do
#   NOT name any ORM column `metadata` (scenarios/models.py documents this).

# GOTCHA: get_db (app/core/database.py:43-53) auto-commits on success. The
#   service should `await db.flush()` + `await db.refresh(obj)` — do NOT call
#   `await db.commit()` inside the service.

# GOTCHA: ModelRun has an attr `model_config` (the JSONB column). Pydantic also
#   reserves `model_config` for ConfigDict — the registry schema aliases it to
#   `model_config_data`. The explainability slice reads the ORM attr
#   `ModelRun.model_config` (a dict) directly; no Pydantic alias needed there.

# GOTCHA: numpy floats are not JSON-serialisable as-is — cast every explainer
#   output through `float(...)` before placing it in a Pydantic schema.

# GOTCHA: FastAPI bodies — never raw `Body(Any)`. Use the Pydantic request model.
#   New endpoints need a 2xx happy path + ≥1 error path (test-requirements.md).
```

## Implementation Blueprint

### Data models and structure

```python
# ---- app/features/explainability/schemas.py (Pydantic v2) ----
class ConfidenceLevel(str, Enum):
    HIGH = "high"; MEDIUM = "medium"; LOW = "low"

class DriverContribution(BaseModel):           # plain BaseModel (response sub-object)
    name: str
    feature_value: float
    contribution: float                         # model-units amount this driver adds
    direction: Literal["positive", "negative", "neutral"]
    description: str

class ReasonCode(BaseModel):                    # advisory only — correlation, never causation
    code: Literal["stockout_constrained", "promotion_overlap", "holiday_effect",
                  "lifecycle_decay", "trend_shift", "insufficient_history"]
    severity: Literal["info", "warn"]
    detail: str

class ForecastExplanation(BaseModel):           # response — NOT strict
    model_config = ConfigDict(from_attributes=True)
    store_id: int
    product_id: int
    model_type: str
    method: Literal["rule_based"]               # "shap"/"component" reserved for full version
    forecast_value: float
    drivers: list[DriverContribution]
    reason_codes: list[ReasonCode]
    confidence: ConfidenceLevel
    caveats: list[str]
    agent_summary: str
    as_of_date: date_type
    generated_at: datetime

class ExplainForecastRequest(BaseModel):        # request — strict=True
    model_config = ConfigDict(strict=True)
    store_id: int = Field(..., ge=1)
    product_id: int = Field(..., ge=1)
    model_type: Literal["naive", "seasonal_naive", "moving_average"]
    # date has no native JSON type -> strict=False per docs/_base/SECURITY.md
    as_of_date: date_type = Field(..., strict=False, description="Series cutoff date")
    season_length: int | None = Field(None, ge=1, le=365)
    window_size: int | None = Field(None, ge=1, le=90)

# ---- app/features/explainability/models.py (SQLAlchemy 2.0) ----
class ForecastExplanation(TimestampMixin, Base):
    __tablename__ = "forecast_explanation"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    explanation_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    store_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    model_type: Mapped[str] = mapped_column(String(50))
    method: Mapped[str] = mapped_column(String(20), default="rule_based")
    as_of_date: Mapped[datetime.date] = mapped_column(Date)
    forecast_value: Mapped[float] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(10))
    drivers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    reason_codes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    caveats: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    agent_summary: Mapped[str] = mapped_column(String(2000))
    __table_args__ = (
        Index("ix_forecast_explanation_drivers_gin", "drivers", postgresql_using="gin"),
        Index("ix_forecast_explanation_store_product", "store_id", "product_id"),
        CheckConstraint("confidence IN ('high','medium','low')",
                        name="ck_forecast_explanation_confidence"),
        CheckConstraint("method IN ('rule_based','shap','component')",
                        name="ck_forecast_explanation_method"),
    )
```

### List of tasks (execute in order — each is atomic and independently testable)

```yaml
Task 1 — CREATE app/features/explainability/__init__.py:
  - Empty file (slice package marker).
  - MIRROR: any app/features/<slice>/__init__.py.
  - VALIDATE: test -f app/features/explainability/__init__.py && echo OK

Task 2 — CREATE app/features/explainability/schemas.py:
  - IMPLEMENT ConfidenceLevel, DriverContribution, ReasonCode, ForecastExplanation,
    ExplainForecastRequest exactly as in "Data models and structure" above.
  - Optional field_validator on ExplainForecastRequest: default season_length=7 /
    window_size=7 when None (mirror SeasonalNaiveModelConfig / MovingAverageModelConfig
    defaults) rather than hard-failing.
  - MIRROR: app/features/forecasting/schemas.py L22-150 (config style),
    L158-198 (strict=True body + Field(strict=False) date + field_validator).
  - IMPORTS: from __future__ import annotations; from datetime import
    date as date_type, datetime; from enum import Enum; from typing import Literal;
    from pydantic import BaseModel, ConfigDict, Field, field_validator.
  - GOTCHA: as_of_date MUST carry Field(strict=False) (test_strict_mode_policy.py).
  - VALIDATE: uv run python -c "from app.features.explainability.schemas import
    ForecastExplanation, ExplainForecastRequest, DriverContribution, ReasonCode; print('OK')"

Task 3 — CREATE app/features/explainability/models.py:
  - IMPLEMENT ForecastExplanation ORM model exactly as above.
  - MIRROR: app/features/scenarios/models.py (newest — JSONB cols, CheckConstraint,
    TimestampMixin, Base import) + app/features/registry/models.py L125-143
    (GIN index pattern).
  - IMPORTS: from __future__ import annotations; import datetime; from typing
    import Any; from sqlalchemy import CheckConstraint, Date, Float, Index,
    Integer, String; from sqlalchemy.dialects.postgresql import JSONB;
    from sqlalchemy.orm import Mapped, mapped_column; from app.core.database
    import Base; from app.shared.models import TimestampMixin.
  - VALIDATE: uv run python -c "from app.features.explainability.models import
    ForecastExplanation; print(ForecastExplanation.__tablename__)"

Task 3b — REGISTER the model with Alembic env (so migration drift check sees it):
  - FIND: how registry/jobs/scenarios models are imported into the Alembic
    `target_metadata` (alembic/env.py or a models aggregator). Commit
    9e7a9e1 registered scenario_plan for the drift check — mirror it.
  - VALIDATE: uv run alembic check  (should report no drift after Task 4).

Task 4 — CREATE alembic/versions/<newid>_create_forecast_explanation_table.py:
  - IMPLEMENT op.create_table("forecast_explanation", ...) with EVERY column
    from the ORM model + created_at/updated_at (DateTime(timezone=True),
    server_default=sa.text("now()")), then op.create_index for the GIN index
    (postgresql_using="gin"), the composite (store_id, product_id) index, and
    the unique explanation_id index. downgrade() = op.drop_table.
  - revision = "<newid>"; down_revision = "43e35957a248".  <-- CRITICAL
  - MIRROR: alembic/versions/43e35957a248_create_scenario_plan_table.py
    + a2f7b3c8d901_create_model_registry_tables.py (JSONB + GIN + CheckConstraint).
  - Generate <newid> with: `uv run alembic revision -m "create forecast explanation table"`
    then fill in the body, OR hand-pick a 12-hex id not already used.
  - VALIDATE (needs docker compose up -d): uv run alembic upgrade head &&
    uv run alembic downgrade -1 && uv run alembic upgrade head

Task 5 — CREATE app/features/explainability/explainers.py:
  - IMPLEMENT BaseExplainer(ABC) with abstract
    explain(self, y: np.ndarray) -> tuple[float, list[DriverContribution]] and
    confidence(self, y: np.ndarray) -> ConfidenceLevel.
  - NaiveExplainer: forecast = float(y[-1]); main driver "last_observation"
    (feature_value=y[-1], contribution=y[-1], direction="positive"). Add an
    informational "recent_trend" driver = mean(y[-7:]) - mean(y[-14:-7]) with
    contribution=0.0 (direction from sign) labelled "context, not used by model".
    confidence: LOW if len(y) < 14 else MEDIUM.
  - SeasonalNaiveExplainer(season_length): forecast = float(y[-season_length]);
    main driver "season_match" (feature_value/contribution = y[-season_length],
    direction="positive"). confidence: LOW if len(y) < 2*season_length else MEDIUM.
  - MovingAverageExplainer(window_size): forecast = float(mean(y[-window_size:]));
    one aggregate "window_mean" driver (contribution = forecast) + informational
    "window_dispersion" driver = float(std(y[-window_size:])) contribution=0.0.
    confidence: HIGH if len(y) >= window_size and std/mean < 0.5;
    MEDIUM if len(y) >= window_size; else LOW.
  - explainer_factory(model_type, season_length, window_size) -> BaseExplainer;
    raise ValueError for "lightgbm"/unknown (caught at route layer -> 400).
  - Empty y -> raise ValueError (mirror NaiveForecaster.fit). Cast all outputs
    to float(). Sum of MAIN driver contributions must ≈ forecast_value
    (informational drivers contribution=0.0, excluded).
  - MIRROR: app/features/forecasting/models.py — BaseForecaster ABC (L44-126),
    each forecaster's math, model_factory (L429-476) dispatch pattern.
  - IMPORTS: from __future__ import annotations; from abc import ABC,
    abstractmethod; import numpy as np; from app.features.explainability.schemas
    import ConfidenceLevel, DriverContribution.
  - VALIDATE: uv run python -c "import numpy as np;
    from app.features.explainability.explainers import explainer_factory;
    e=explainer_factory('moving_average',None,7); print(e.explain(np.arange(30.0)))"

Task 6 — CREATE app/features/explainability/reason_codes.py:
  - IMPLEMENT pure functions (DB-free — the service does the queries and passes
    already-windowed rows):
    * stockout_reason(inventory_rows) -> ReasonCode | None — fires
      "stockout_constrained" (warn) if any is_stockout day in the trailing
      window; detail counts stockout days.
    * promotion_reason(promotion_rows, as_of_date) -> ReasonCode | None —
      "promotion_overlap" (info) if a promotion overlaps the trailing window
      or is active at as_of_date.
    * lifecycle_reason(launch_date, as_of_date) -> ReasonCode | None —
      days_since_launch = (as_of_date - launch_date).days; < 30 -> "lifecycle_decay"
      (info).
    * holiday_reason(calendar_rows, forecast_date) -> ReasonCode | None —
      "holiday_effect" (info) if the immediate forecast horizon hits a flagged
      Calendar.is_holiday row.
    * history_reason(n_obs, min_required) -> ReasonCode | None —
      "insufficient_history" (warn) if n_obs < min_required.
    * build_caveats(model_type, reason_codes) -> list[str] — ALWAYS includes the
      NIST-grounded "drivers describe correlation/contribution, not business
      causality" caveat; adds model-specific ones (naive: "ignores seasonality
      & trend"; seasonal_naive: "assumes the prior cycle repeats";
      moving_average: "smooths over recent shifts").
  - GOTCHA: each function's docstring states it must only receive rows already
    windowed `<= as_of_date` by the caller. holiday_reason must not peek past
    the explained horizon's last date.
  - IMPORTS: from __future__ import annotations; from datetime import
    date as date_type; from app.features.explainability.schemas import ReasonCode.
  - VALIDATE: uv run python -c "from app.features.explainability.reason_codes
    import build_caveats; print(build_caveats('naive', []))"

Task 7 — CREATE app/features/explainability/service.py:
  - IMPLEMENT ExplainabilityService (see pseudocode below).
  - MIRROR: app/features/forecasting/service.py (_load_training_data shape),
    registry/service.py:get_run (select(ModelRun)... scalar_one_or_none),
    scenarios/service.py (persist via flush/refresh, NOT commit).
  - IMPORTS: from __future__ import annotations; import uuid; from datetime
    import UTC, datetime, timedelta; from datetime import date as date_type;
    import numpy as np; import structlog; from sqlalchemy import select;
    from sqlalchemy.ext.asyncio import AsyncSession; from app.core.config import
    get_settings; from app.core.exceptions import BadRequestError, NotFoundError;
    from app.features.data_platform.models import (SalesDaily,
    InventorySnapshotDaily, Promotion, Product, Calendar);
    from app.features.registry.models import ModelRun;     # read-only data contract
    from app.features.jobs.models import Job;               # read-only data contract
    + slice-local explainers / reason_codes / schemas / models.
  - NOTE: importing registry/jobs ORM models read-only is the locked decision
    (see "Open Questions & Decisions" #1) — document it in the service module
    docstring + PR description. DO NOT import any *.service.
  - VALIDATE: uv run mypy app/features/explainability/service.py &&
    uv run pyright app/features/explainability/service.py

Task 8 — CREATE app/features/explainability/routes.py:
  - IMPLEMENT router = APIRouter(prefix="/explain", tags=["explainability"]):
    * GET /explain/jobs/{job_id}  -> explain_job   (404 missing, 400 not a
      completed predict job)
    * GET /explain/runs/{run_id}  -> explain_run   (404 missing, 400 lightgbm)
    * POST /explain/forecast      -> explain_forecast  (status_code=200)
  - Each route: service = ExplainabilityService(); try/except
    ValueError -> HTTPException(400, ...); SQLAlchemyError ->
    DatabaseError(...); None from service -> HTTPException(404, ...).
  - Add rich summary/description on every route (agents read these).
  - MIRROR: app/features/scenarios/routes.py + registry/routes.py:get_run (L200-232).
  - IMPORTS: from fastapi import APIRouter, Depends, HTTPException, status;
    from sqlalchemy.exc import SQLAlchemyError; from sqlalchemy.ext.asyncio
    import AsyncSession; from app.core.database import get_db; from
    app.core.exceptions import DatabaseError; from app.core.logging import
    get_logger; + slice schemas + service.
  - VALIDATE: uv run python -c "from app.features.explainability.routes import
    router; print([r.path for r in router.routes])"

Task 9 — MODIFY app/main.py:
  - FIND import block (L15-31). INJECT (near forecasting):
    `from app.features.explainability.routes import router as explainability_router`
  - FIND include_router block (L133-149). INJECT after `forecasting_router`:
    `app.include_router(explainability_router)`
  - PRESERVE all other wiring; no other change.
  - VALIDATE: uv run python -c "from app.main import app;
    print([r.path for r in app.routes if 'explain' in getattr(r,'path','')])"

Task 10 — CREATE tests/__init__.py + tests/conftest.py:
  - __init__.py empty. conftest.py: sample_series (np.ndarray ~60 values),
    flat_series, short_series (<14), sample_run_row (ModelRun-shaped object or
    dict with model_config JSONB), sample_predict_job (completed Job-shaped row).
    Reuse the integration DB/client fixture pattern from
    app/features/scenarios/tests/conftest.py for @pytest.mark.integration tests.
  - VALIDATE: uv run pytest app/features/explainability/tests/ --collect-only -q

Task 11 — CREATE tests/test_explainers.py:
  - For each explainer: (a) forecast value EQUALS the real forecasting/models.py
    forecaster's `.fit(y).predict(1)[0]` on the same y (import the real
    forecasters — allowed in tests); (b) main driver contribution sum ≈
    forecast_value (pytest.approx); (c) direction signs correct;
    (d) empty y raises ValueError; (e) confidence downgrades on short series.
  - MIRROR: app/features/forecasting/tests/test_service.py (class-grouped, numpy).
  - VALIDATE: uv run pytest app/features/explainability/tests/test_explainers.py
    -v -m "not integration"

Task 12 — CREATE tests/test_reason_codes.py:
  - stockout_reason fires on stockout rows / None otherwise; promotion_reason on
    overlap; lifecycle_reason on recent launch; history_reason on short series;
    build_caveats always includes the correlation-vs-causation caveat.
  - VALIDATE: uv run pytest app/features/explainability/tests/test_reason_codes.py
    -v -m "not integration"

Task 13 — CREATE tests/test_schemas.py:
  - ExplainForecastRequest.model_validate({...}) accepts an ISO date STRING for
    as_of_date (THE JSON PATH — required by docs/_base/SECURITY.md, catches the
    strict regression). ForecastExplanation round-trips model_dump/model_validate.
    ConfidenceLevel enum values. Invalid model_type rejected.
  - VALIDATE: uv run pytest app/features/explainability/tests/test_schemas.py
    -v -m "not integration"

Task 14 — CREATE tests/test_service.py:
  - ExplainabilityService with a mocked AsyncSession (AsyncMock) — explain_forecast
    returns a well-formed ForecastExplanation; explain_run resolves config from a
    fake ModelRun.model_config dict; explain_job rejects a non-completed /
    non-predict job (BadRequestError); missing run/job -> None or NotFoundError.
  - GOTCHA: mock the select(...) result chain — db.execute.return_value ->
    object with .all() / .scalar_one_or_none().
  - MIRROR: app/features/forecasting/tests/test_service.py (UNIT service-test
    pattern — class-grouped, AsyncMock/MagicMock DB). The scenarios slice ships
    no unit test_service.py — do NOT mirror it for this.
  - VALIDATE: uv run pytest app/features/explainability/tests/test_service.py
    -v -m "not integration"

Task 15 — CREATE tests/test_routes.py:
  - httpx AsyncClient(transport=ASGITransport(app=app)) with the test-DB
    dependency override. POST /explain/forecast 200;
    GET /explain/runs/{missing} 404; GET /explain/jobs/{missing} 404;
    GET /explain/runs/{lightgbm-run} 400. Assert RFC 7807 body shape
    (type, title, status, detail) on error paths.
  - MIRROR: app/features/forecasting/tests/test_routes.py (UNIT route-test
    pattern — ASGITransport, dependency override, RFC 7807 assertions). The
    scenarios slice ships only an integration route test — do NOT mirror it for
    this unit task; see Task 16 for the integration route test.
  - VALIDATE: uv run pytest app/features/explainability/tests/test_routes.py
    -v -m "not integration"

Task 16 — CREATE tests/test_models_integration.py + tests/test_routes_integration.py:
  - @pytest.mark.integration — ForecastExplanation CRUD against real Postgres;
    confidence/method CheckConstraint rejects bad values; end-to-end: seed a
    tiny series + a baseline ModelRun -> GET /explain/runs/{run_id} returns a
    real explanation; explanation row persisted and re-readable.
  - GOTCHA: never mock the DB; tests idempotent (no pre-seed assumptions).
  - VALIDATE (docker compose up -d): uv run alembic upgrade head &&
    uv run pytest app/features/explainability/tests/ -v -m integration

Task 17 — MODIFY frontend/src/types/api.ts:
  - ADD DriverContribution, ReasonCode, ConfidenceLevel ('high'|'medium'|'low'),
    ForecastExplanation TS interfaces — snake_case field names mirroring the
    Pydantic response schema EXACTLY.
  - MIRROR: existing ModelRun (L173) / ForecastPoint (L102) interfaces.
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task 18 — CREATE frontend/src/hooks/use-explanations.ts:
  - useRunExplanation(runId, enabled) -> api<ForecastExplanation>('/explain/runs/'+runId);
    useJobExplanation(jobId, enabled) -> '/explain/jobs/'+jobId;
    useExplainForecast() -> useMutation POST '/explain/forecast'.
  - MIRROR: frontend/src/hooks/use-runs.ts.
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task 19 — CREATE frontend/src/components/explainability/explanation-panel.tsx:
  - <ExplanationPanel explanation isLoading error /> — a Card with a drivers
    table (name, value, contribution, direction colour), a reason-codes list
    (icon by severity), a confidence Badge, and a caveats footnote list.
  - Reuse already-installed shadcn card/badge/table FIRST. For any NEW shadcn
    component follow .claude/rules/shadcn-ui.md (shadcn skill + MCP).
  - MIRROR: run-detail.tsx Card composition; forecast.tsx EmptyState/LoadingState.
  - VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 20 — CREATE frontend/src/components/explainability/explanation-panel.test.tsx:
  - vitest render test — panel renders drivers/reason codes/confidence/caveats
    from a fixture; loading + error states.
  - VALIDATE: cd frontend && pnpm test --run

Task 21 — MODIFY frontend/src/pages/explorer/run-detail.tsx:
  - After the Metrics card, add a "Forecast Explanation" Card rendering
    <ExplanationPanel> fed by useRunExplanation(runId, true). Gracefully handle
    lightgbm runs (400 -> "Explanations are available for baseline models only").
  - VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 22 — MODIFY frontend/src/pages/visualize/forecast.tsx:
  - When a completed predict job is loaded (job.status==='completed' &&
    job.job_type==='predict'), render <ExplanationPanel> fed by
    useJobExplanation(job.job_id, true) below the forecast chart.
  - VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task 23 — MODIFY docs/_base/API_CONTRACTS.md:
  - ADD 3 rows under a new `explainability` slice grouping in the HTTP endpoint
    table: GET /explain/runs/{run_id}, GET /explain/jobs/{job_id},
    POST /explain/forecast.
  - VALIDATE: grep -c "/explain/" docs/_base/API_CONTRACTS.md
```

### Per-task pseudocode (CRITICAL details)

```python
# ---- Task 5: explainers.py ----
class BaseExplainer(ABC):
    @abstractmethod
    def explain(self, y: np.ndarray) -> tuple[float, list[DriverContribution]]: ...
    @abstractmethod
    def confidence(self, y: np.ndarray) -> ConfidenceLevel: ...

class NaiveExplainer(BaseExplainer):
    def explain(self, y):
        if len(y) == 0:                       # GOTCHA: mirror NaiveForecaster.fit
            raise ValueError("Cannot explain an empty series")
        forecast = float(y[-1])
        drivers = [DriverContribution(
            name="last_observation", feature_value=forecast, contribution=forecast,
            direction="positive",
            description="Naive forecast IS the last observed value.")]
        if len(y) >= 14:                       # informational only — contribution=0.0
            trend = float(np.mean(y[-7:]) - np.mean(y[-14:-7]))
            drivers.append(DriverContribution(
                name="recent_trend", feature_value=trend, contribution=0.0,
                direction="positive" if trend > 0 else "negative" if trend < 0 else "neutral",
                description="Context only — the naive model does not use trend."))
        return forecast, drivers

# ---- Task 7: service.py ----
class ExplainabilityService:
    """Read-only explainability slice service.

    Imports registry.models.ModelRun and jobs.models.Job as READ-ONLY data
    contracts (locked decision — see PRP "Open Questions & Decisions" #1; same
    pattern as importing data_platform.models). It imports NO other slice's
    service.py. To explain a run/job it re-loads the series from sales_daily and
    re-fits a rule-based explainer from the stored config.
    """
    def __init__(self) -> None:
        self.settings = get_settings()

    async def _load_series(self, db, store_id, product_id, end_date):
        # MIRROR forecasting/service.py:_load_training_data — TIME-SAFE upper bound
        stmt = (select(SalesDaily.date, SalesDaily.quantity)
                .where((SalesDaily.store_id == store_id)
                       & (SalesDaily.product_id == product_id)
                       & (SalesDaily.date <= end_date))     # <-- LOAD-BEARING
                .order_by(SalesDaily.date))
        rows = (await db.execute(stmt)).all()
        y = np.array([float(r.quantity) for r in rows], dtype=np.float64)
        return y, [r.date for r in rows]

    async def explain_forecast(self, db, request: ExplainForecastRequest) -> ForecastExplanation:
        y, dates = await self._load_series(db, request.store_id, request.product_id,
                                           request.as_of_date)
        explainer = explainer_factory(request.model_type, request.season_length,
                                      request.window_size)        # ValueError -> route 400
        forecast_value, drivers = explainer.explain(y)            # ValueError on empty y
        confidence = explainer.confidence(y)
        inv, promos, product, cal = await self._load_reason_code_inputs(
            db, request.store_id, request.product_id, request.as_of_date)
        reason_codes = self._assemble_reason_codes(inv, promos, product, cal,
                                                   request.as_of_date, len(y),
                                                   request.model_type)
        caveats = build_caveats(request.model_type, reason_codes)
        agent_summary = self._build_agent_summary(drivers, reason_codes, confidence,
                                                  forecast_value)
        explanation = ForecastExplanation(... fields ...)
        # PERSIST — flush/refresh, NOT commit (get_db auto-commits)
        row = ExplanationORM(explanation_id=uuid.uuid4().hex, ...)
        db.add(row); await db.flush(); await db.refresh(row)
        return explanation

    async def explain_run(self, db, run_id: str) -> ForecastExplanation | None:
        run = (await db.execute(
            select(ModelRun).where(ModelRun.run_id == run_id))).scalar_one_or_none()
        if run is None:
            return None                                # route -> 404
        cfg = run.model_config                          # JSONB dict
        model_type = cfg["model_type"]
        if model_type == "lightgbm":
            raise ValueError("Explanations available for baseline models only")  # -> 400
        season_length = cfg.get("season_length")
        window_size = cfg.get("window_size")
        # as_of_date = run.data_window_end ; store/product from the run
        ... dispatch as explain_forecast ...

    async def explain_job(self, db, job_id: str) -> ForecastExplanation | None:
        job = (await db.execute(
            select(Job).where(Job.job_id == job_id))).scalar_one_or_none()
        if job is None:
            return None                                # route -> 404
        if job.job_type != "predict" or job.status != "completed":
            raise BadRequestError(message="explain_job requires a completed predict job",
                                  details={"job_id": job_id, "status": job.status})
        result = job.result or {}
        forecasts = result.get("forecasts", [])
        # as_of_date = day BEFORE the first forecast date
        first = date_type.fromisoformat(forecasts[0]["date"])
        as_of_date = first - timedelta(days=1)
        ... dispatch ...
```

### Integration Points

```yaml
DATABASE:
  - migration: "create forecast_explanation table, down_revision = 43e35957a248"
  - indexes: GIN on drivers, composite (store_id, product_id), unique explanation_id
  - constraints: CHECK confidence IN (high,medium,low); CHECK method IN
    (rule_based,shap,component)
  - alembic env: register the model with target_metadata (mirror commit 9e7a9e1
    which registered scenario_plan for the drift check)

CONFIG:
  - none new — ExplainabilityService.__init__ calls get_settings() only for
    parity; no new settings keys.

ROUTES:
  - add to: app/main.py
  - import: from app.features.explainability.routes import router as explainability_router
  - include: app.include_router(explainability_router)   # after forecasting_router

FRONTEND:
  - types: frontend/src/types/api.ts (+4 interfaces)
  - hook:  frontend/src/hooks/use-explanations.ts
  - component: frontend/src/components/explainability/explanation-panel.tsx
  - pages: run-detail.tsx + forecast.tsx mount <ExplanationPanel>

DOCS:
  - docs/_base/API_CONTRACTS.md — 3 endpoint rows under an `explainability` group
```

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check .
uv run ruff format --check .
# Expected: no errors. If errors, READ the error and fix (ruff check --fix for autofixable).
```

### Level 2: Type checks + Unit Tests

```bash
uv run mypy app/ && uv run pyright app/         # both --strict — gate merge
uv run pytest -v -m "not integration"
# Iterate until green. Never weaken a test to pass; fix the code.
# Key assertions: each explainer's h=1 value == the real forecaster's
#   .fit(y).predict(1)[0]; ExplainForecastRequest accepts an ISO-string as_of_date.
```

### Level 3: Integration Tests

```bash
docker compose up -d
uv run alembic upgrade head
uv run alembic downgrade -1 && uv run alembic upgrade head   # migration round-trips
uv run pytest -v -m integration
```

### Level 4: Manual Validation

```bash
# Backend: uv run uvicorn app.main:app --reload --port 8123
curl -s -X POST http://localhost:8123/explain/forecast \
  -H 'Content-Type: application/json' \
  -d '{"store_id":1,"product_id":1,"model_type":"moving_average","as_of_date":"2024-06-30","window_size":7}' \
  | python -m json.tool
# Expect: drivers[], reason_codes[], confidence, caveats[], agent_summary, forecast_value
curl -s http://localhost:8123/explain/runs/<a-real-baseline-run-id> | python -m json.tool
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8123/explain/runs/does-not-exist  # 404
```

### Level 5: Frontend

```bash
cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run
# Then: ./node_modules/.bin/vite --host 0.0.0.0
# Browser dogfood (webapp-testing / agent-browser per .claude/rules/ui-design.md):
#   /explorer/runs/<id>     -> Forecast Explanation card renders
#   /visualize/forecast     -> explanation panel renders below the chart
```

## Final Validation Checklist

- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run mypy app/ && uv run pyright app/` clean (both --strict)
- [ ] `uv run pytest -v -m "not integration"` green
- [ ] `docker compose up -d && uv run pytest -v -m integration` green
- [ ] Migration applies + rolls back cleanly; `uv run alembic check` reports no drift
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` green
- [ ] Manual curl + browser dogfood confirm the feature
- [ ] All Success Criteria met
- [ ] Commit `feat(api,ui): add forecast explainability & driver attribution slice (#<issue>)`
      referencing an OPEN GitHub issue; branch `feat/forecast-explainability` off `dev`

## Testing Strategy

### Unit Tests (`-m "not integration"`, mocked externals, no DB)

Cover: every explainer's forecast-value parity vs the real forecasters; driver
contribution sums; confidence downgrades; reason-code firing logic; caveat
content; schema JSON-path validation; service dispatch with `AsyncMock` DB;
route happy + error paths via `ASGITransport`.

### Integration Tests (`@pytest.mark.integration`, real docker-compose Postgres)

Cover: the Alembic migration applies + rolls back cleanly; `ForecastExplanation`
`CheckConstraint`s reject bad `confidence`/`method`; end-to-end
`GET /explain/runs/{run_id}` after seeding a real series + `ModelRun`;
explanation row persisted and re-readable. Never mock the DB.

### Edge Cases

- Empty series for a `(store, product)` → explainer raises `ValueError` → route 400.
- Series shorter than `season_length`/`window_size` → confidence `LOW` +
  `insufficient_history` reason code (not a crash).
- A `lightgbm` run → 400 "baseline models only" (MVP scope guard).
- A `predict` job that is `pending`/`failed`/`cancelled` → 400.
- A series with stockout days → `stockout_constrained` reason code present,
  caveat about understated demand.
- Flat (constant) series → moving-average confidence `HIGH`, naive
  `recent_trend` driver `neutral`.
- ISO-date string body for `POST /explain/forecast` (the `strict`-mode JSON path).

## Open Questions & Decisions

1. **[DECISION LOCKED] Cross-slice ORM-model import is ALLOWED (read-only).**
   `explain_run`/`explain_job` need to read `ModelRun`/`Job` rows. The
   vertical-slice rule forbids importing another slice's `service.py`; importing
   another slice's `models.py` was the one gray area. **Maintainer ruling:** the
   `explainability` slice MAY import `app.features.registry.models.ModelRun` and
   `app.features.jobs.models.Job` directly as **read-only data contracts** — it
   must NEVER import those slices' `service.py`. This mirrors how slices already
   import `app.features.data_platform.models` directly. The decision is final;
   there is no fallback path. The implementer must document the choice in the
   `service.py` module docstring and the PR description.

2. **[ASSUMPTION] Endpoint namespace.** This PRP owns a self-contained `/explain`
   prefix rather than mounting paths under `/forecasting` or `/registry` (the
   original brief suggested `GET /forecasting/explanations/{job_id}` and
   `GET /registry/runs/{run_id}/explanations`). A self-owned prefix keeps the
   slice from mounting routes under another slice's prefix. Flag in the PR for
   maintainer sign-off.

3. **[ASSUMPTION] `seasonal_naive` horizon.** Explanations are computed for the
   **h=1** forecast (the dominant, most-interpretable case). Multi-horizon
   driver attribution is deferred to a future PRP.

4. **[ASSUMPTION] `as_of_date` for a predict job.** Derived as the day before
   the first forecast date in `job.result["forecasts"]`. If a future predict-job
   result records the training cutoff explicitly, prefer that.

5. **[ASSUMPTION] No GitHub issue exists yet.** The implementer must open/secure
   an open issue before committing (`commit-format.md` requires `(#issue)`).
   Branch `feat/forecast-explainability` off `dev`.

6. **[OUT OF SCOPE] Backtest explanation.** Per-fold backtest explanation is
   future-version work — noted, not built here. MVP covers forecast + run + job.

7. **[OUT OF SCOPE] SHAP / tree-model explainers.** Deliberately excluded. SHAP
   would add `shap` + a transitive tree (numba, llvmlite, cloudpickle) — a heavy
   footprint for a single-host portfolio repo, and `lightgbm` itself is still
   feature-flagged and `NotImplementedError` in `model_factory`. There is no tree
   model to explain yet. The MVP rule-based explainers are **exact**, not
   approximate. The `method` field (`"rule_based"` now; `"shap"`/`"component"`
   reserved) keeps the schema forward-compatible. **Adding SHAP later needs its
   own PRP + an ADR** — a new core-path dependency touches
   `.claude/rules/product-vision.md` (single-host vision).

## Anti-Patterns to Avoid

- ❌ Importing another slice's `service.py` (vertical-slice rule violation).
- ❌ Setting `down_revision` to `378c112e4b32` — the head is `43e35957a248`.
- ❌ Omitting `Field(strict=False)` on `ExplainForecastRequest.as_of_date`
  (`test_strict_mode_policy.py` fails CI).
- ❌ Reading any data past `as_of_date` / `data_window_end` (leakage — blocker).
- ❌ Calling `await db.commit()` inside the service (`get_db` auto-commits).
- ❌ Bare `raise HTTPException(500, "string")` — use the RFC 7807 exception classes.
- ❌ Adding `shap` / `lightgbm` to `pyproject.toml`.
- ❌ Naming any ORM column `metadata` (SQLAlchemy reserves it).
- ❌ Returning numpy floats unwrapped — cast through `float()`.
- ❌ Making a reason code a causal claim — they are advisory correlation only.
- ❌ Hand-rolling a shadcn install — use the `shadcn` skill + MCP.

---

## Confidence Score: 9/10 for one-pass success

The slice pattern, schema/route/migration patterns, and the exact forecaster
math are all well-established in the codebase and reproduced above with verified
line/symbol references. The newest slice (`scenarios`, PRP-26) is a near-exact
structural template. The cross-slice ORM-import question (Open Question #1) is
now a locked decision — no mid-implementation maintainer call is needed.
Residual risks: (a) the frontend panel needs real-browser verification per
`ui-design.md`, which can surface layout iteration; (b) the Alembic
model-registration step (Task 3b) must mirror commit 9e7a9e1 precisely so the
drift check stays green. Both are bounded and flagged.
