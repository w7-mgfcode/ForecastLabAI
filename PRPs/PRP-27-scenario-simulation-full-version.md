name: "PRP-27 — Scenario Simulation / What-If Planning (Full Version)"
description: |
  Context-rich PRP that promotes the **"Full Version"** section of
  `docs/optional-features/03-scenario-simulation-what-if-planning.md` (lines
  82-89) into code. It is a strict **increment on the already-shipped MVP**
  (`app/features/scenarios/`, PRP-26, issue #221, branch
  `feat/scenarios-what-if-planning`). It adds: a leakage-safe future
  feature-frame generator, an exogenous-regressor forecaster the scenario
  engine can drive, a real `method="model_exogenous"` simulation path, a
  multi-scenario comparison surface, and an agent that proposes scenarios
  behind the HITL approval gate. Delivered as **four independently-shippable
  phases** so each is one-pass implementable.

## Purpose

The MVP turned ForecastLabAI from "predict the future" into "plan possible
futures" — but every scenario number is a **deterministic post-forecast
multiplier** stamped `method="heuristic"`. The factors (`PRICE_ELASTICITY`,
`PROMOTION_UPLIFT_BY_KIND`, …) are hand-picked constants, not learned from data.
The feature brief's **"Full Version"** closes that gap:

- **Phase A — Future Feature-Frame Generator (backend)**: a leakage-safe module
  that builds a per-horizon-day feature matrix (`X_future`) for a `(store,
  product)` series, with the scenario assumptions injected as exogenous columns.
- **Phase B — Exogenous-Regressor Forecaster + model-driven simulation
  (backend)**: a `RegressionForecaster` (`BaseForecaster` subclass) that
  *consumes* `X`, a new `method="model_exogenous"` value, and a
  `ScenarioService.simulate` path that produces a model-causal comparison when
  the baseline model supports exogenous features — falling back to the
  heuristic path otherwise.
- **Phase C — Scenario Library + Multi-Scenario Comparison (backend + frontend)**:
  scenario-library tagging/cloning over the existing `scenario_plan` table, a
  `POST /scenarios/compare` endpoint, and a What-If Planner comparison view that
  charts a baseline against N saved scenarios.
- **Phase D — Agent-Proposed Scenarios + Approval Flow (backend)**: two `scenarios`
  agent tools — a read-only `propose_scenario` that returns a candidate
  `ScenarioAssumptions` payload + an operational recommendation, and a
  mutating `save_scenario` that persists a `scenario_plan` row **only after
  the human approves it via the existing HITL gate** (`save_scenario` is added
  to `agent_require_approval`). Persisted agent scenarios carry author/source
  provenance and an audit trail linking back to the agent session and the
  approval decision; a Phase D migration adds the provenance/audit columns to
  `scenario_plan`.

The MVP code is **not re-specified** — see § "What the MVP already delivered".

> Source brief: `docs/optional-features/03-scenario-simulation-what-if-planning.md`
> § "Full Version". MVP PRP: `PRPs/PRP-26-scenario-simulation-what-if-planning.md`.
> Validated against the repo as of 2026-05-19.

---

## SCOPE WARNING — this is a large PRP; it is phased deliberately

The Full Version spans two genuinely large pieces of work — a leakage-safe
future-feature-frame generator and exogenous-regressor model support. Either one
alone is a normal PRP's worth of work. **This PRP is therefore explicitly
phased: ship one PR per phase, in order.** Phase A and B are backend-only and
gate Phase C/D. A team that can only land part of this should land **Phase A +
B** (the model-causal core) and defer C + D — the brief's other three bullets
(scenario library, multi-scenario comparison, agent suggestions) are valuable
but lower-risk and do not unblock anything.

If the implementer judges Phase A + B alone is still too large for one PR, split
Phase B into B1 (the `RegressionForecaster` + training path) and B2 (the
scenario `simulate` integration) — they have a clean seam at the
`BaseForecaster` interface.

---

## What the MVP already delivered (DO NOT re-build)

PRP-26 shipped and merged the entire `app/features/scenarios/` slice. **Every
file below already exists** — this PRP modifies or extends them, never recreates
them.

| File | What it already does |
|------|----------------------|
| `app/features/scenarios/__init__.py` | Slice package + `__all__`. |
| `app/features/scenarios/adjustments.py` | PURE deterministic factor engine — `price_factor`, `promotion_factor`, `holiday_factor`, `lifecycle_factor`, `combined_daily_factor`, `apply_adjustment`, `coverage_verdict`. Constants `PRICE_ELASTICITY`, `PROMOTION_UPLIFT_BY_KIND`, `HOLIDAY_UPLIFT`, `LIFECYCLE_FACTOR`, `FACTOR_BAND`. |
| `app/features/scenarios/schemas.py` | `PriceAssumption`, `PromotionAssumption`, `HolidayAssumption`, `InventoryAssumption`, `LifecycleAssumption`, `ScenarioAssumptions`, `SimulateScenarioRequest`, `CreateScenarioRequest`, `ScenarioPoint`, `ScenarioComparison`, `ScenarioPlanResponse`, `ScenarioListItem`, `ScenarioListResponse`. Request bodies use `ConfigDict(strict=True)` + `Field(strict=False)` on dates; responses use `from_attributes=True`. `ScenarioComparison.method` is `Literal["heuristic"]`. |
| `app/features/scenarios/models.py` | `ScenarioPlan(TimestampMixin, Base)` ORM — `scenario_id`, `name`, `store_id`, `product_id`, `run_id`, `horizon`, `assumptions` JSONB, `comparison` JSONB, `method` String(20). `CheckConstraint("method IN ('heuristic')")`, GIN indexes, composite `(store_id, product_id)` index. Constant `SCENARIO_METHOD_HEURISTIC = "heuristic"`. |
| `app/features/scenarios/service.py` | `ScenarioService` — `simulate` (heuristic post-forecast multiplier; loads a bundle via `load_model_bundle`, calls `bundle.model.predict(horizon)`, applies `adjustments.combined_daily_factor`), plus `create_plan` / `list_plans` / `get_plan` / `delete_plan`. Helpers `_load_baseline_bundle` (path-traversal guard), `_forecast_start_date`, `_latest_unit_price`, `_to_plan_response`, `_to_list_item`. Constant `HEURISTIC_DISCLAIMER`. |
| `app/features/scenarios/routes.py` | `router = APIRouter(prefix="/scenarios", tags=["scenarios"])`. Endpoints: `POST /scenarios/simulate`, `POST /scenarios`, `GET /scenarios`, `GET /scenarios/{scenario_id}`, `DELETE /scenarios/{scenario_id}`. Maps `FileNotFoundError`→`NotFoundError`, `ValueError`→`BadRequestError`, `SQLAlchemyError`→`DatabaseError`. |
| `app/features/scenarios/tests/` | `conftest.py`, `test_adjustments.py`, `test_schemas.py`, `test_leakage.py` (LOAD-BEARING), `test_routes_integration.py`. |
| `alembic/versions/43e35957a248_create_scenario_plan_table.py` | Creates `scenario_plan`. **This is the current Alembic head** — verified `uv run alembic heads` → `43e35957a248`. |
| `frontend/src/types/api.ts` | `Scenario*` interfaces. |
| `frontend/src/hooks/use-scenarios.ts` | `useSimulateScenario`, `useScenarios`, `useScenario`, `useCreateScenario`, `useDeleteScenario`. |
| `frontend/src/lib/scenario-utils.ts` (+ `.test.ts`) | `mergeComparisonSeries`, `formatDelta`, `coverageLabel`, `coverageVariant`, `deltaCsvColumns`, `summariseAssumptions`. |
| `frontend/src/pages/visualize/planner.tsx` | The `/visualize/planner` What-If Planner page. |

> The Full Version **never weakens** `test_leakage.py`, never edits the merged
> migration `43e35957a248`, and never drops the `method="heuristic"` path —
> it adds a second, model-driven path alongside it.

---

## DEPENDS ON — read before starting

- **MVP merged** — `app/features/scenarios/` exists. If it does not, this PRP
  cannot start; build PRP-26 first.
- **No unmerged-PRP dependency.** Builds on already-merged `forecasting`
  (PRP-5), `featuresets` (PRP-4 + PRP-3.1*), `data_platform` (PRP-2),
  `registry` (PRP-7), `jobs` (PRP-8), `agents` (PRP-10), dashboard (PRP-11).
- **Sanity-check before starting**: `app/features/forecasting/models.py` must
  still define `BaseForecaster` with the `fit(y, X=None)` / `predict(horizon,
  X=None)` interface and `model_factory`; `app/features/featuresets/service.py`
  must still define `FeatureEngineeringService.compute_features` and
  `FeatureDataLoader`. If either moved, the Phase A/B plan needs revisiting.

---

## Goal

**Feature Goal**: Make Scenario Simulation **model-causal** — a what-if can be
answered by re-forecasting through a model that consumes a leakage-safe future
feature frame built from the scenario assumptions — and **collaborative** — an
agent can propose a scenario and a human approves it. The MVP heuristic path
stays as the transparent fallback.

**Deliverable**:
- **Phase A** — `app/features/scenarios/feature_frame.py` (new): a pure +
  DB-reading future-feature-frame generator, plus a load-bearing leakage test.
- **Phase B** — `RegressionForecaster` added to `forecasting/models.py`, a
  `RegressionModelConfig` schema, `model_factory` wiring, a training path that
  builds historical features and fits the estimator; `ScenarioService.simulate`
  extended with a `method="model_exogenous"` branch; one Alembic migration
  widening the `scenario_plan.method` CHECK constraint.
- **Phase C** — `POST /scenarios/compare` + `MultiScenarioComparison` schema +
  scenario-library fields (`tags`, `cloned_from`) on `scenario_plan` (second
  migration); a multi-series chart variant and a comparison view on the planner
  page; new hooks + types.
- **Phase D** — `app/features/scenarios/agent_tools.py` (new): a read-only
  `propose_scenario` tool and a mutating `save_scenario` tool registered on the
  experiment agent, with `save_scenario` gated by `agent_require_approval`; a
  Phase D Alembic migration adding provenance/audit columns to `scenario_plan`
  (`source`, `agent_session_id`, `approved_by`, `approved_at`, `approval_decision`);
  the `ScenarioPlan` ORM model + schemas extended accordingly; `save_scenario`
  added to the `agent_require_approval` config list in `app/core/config.py`.

**Success Definition**: `docker compose up` → seed → train a `regression`
model → `POST /scenarios/simulate` with that model's `run_id` and a price-cut
assumption returns a `ScenarioComparison` with `method="model_exogenous"` whose
deltas come from re-forecasting (not a fixed multiplier); the future-frame
leakage test proves no observed target at/after the forecast origin is read;
`POST /scenarios/compare` ranks N saved scenarios; the planner comparison view
charts baseline + N scenarios; the experiment agent can `propose_scenario`
(read-only) and `save_scenario`, and a `save_scenario` call is blocked pending
`/agents/sessions/{id}/approve` — once approved, the persisted `scenario_plan`
row carries `source="agent"`, the originating `agent_session_id`, and the
approval audit trail (`approved_by`, `approved_at`, `approval_decision`); every gate
(`ruff`, `mypy --strict`, `pyright --strict`, `pytest` unit + integration,
frontend `tsc`/`lint`/`test`) is green.

## Why

- **User value** — heuristic deltas are directional only; a model-causal
  scenario lets a planner trust the *magnitude* of "discount 15% next week".
  A scenario library + multi-scenario comparison turns one-off analyses into a
  reusable planning portfolio. Agent-proposed scenarios surface options a
  planner would not have thought to try.
- **Demo value** — the brief calls this out: the Full Version is what makes the
  feature a *planning system* rather than a labelled-heuristic demo.
- **Integration** — featuresets already produces every exogenous feature
  (`price_lag_*`, `promo_*`, lifecycle, calendar) and is time-safe by
  construction; this PRP reuses that machinery for the *future* frame and adds
  the one model class that can consume it.

## What

### User-visible behavior

1. **Train a regression model** — a new `model_type="regression"` is trainable
   via the existing `POST /forecasting/train` (or a `train` job). It fits a
   feature-driven estimator on historical features.
2. **Model-causal simulation** — on the What-If Planner, when the picked
   baseline job's model is a `regression` model, `POST /scenarios/simulate`
   returns `method="model_exogenous"`: the price/promotion/holiday assumptions
   become real future feature-frame columns and the model re-forecasts. A
   `naive`/`seasonal_naive`/`moving_average` baseline still returns
   `method="heuristic"` exactly as today. The result always declares its method.
3. **Scenario library** — saved plans carry `tags` and can be cloned (a new plan
   pre-filled from an existing one's assumptions). The saved-plans list filters
   by tag.
4. **Multi-scenario comparison** — pick 2-5 saved plans → a comparison view
   charts the baseline against every scenario series, ranks them by revenue
   delta, and shows a verdict table.
5. **Agent-proposed scenarios** — in the chat agent, a user can ask "what
   scenarios should I try for store 1 product 101?"; the agent calls
   `propose_scenario` (read-only), which returns a candidate
   `ScenarioAssumptions` + a plain-language recommendation. If the user then
   asks the agent to save the proposal, the agent calls `save_scenario` — a
   mutating tool that is in `agent_require_approval`, so it pauses at the
   existing HITL gate and writes the `scenario_plan` row **only after** the
   human approves via `/agents/sessions/{id}/approve`. The persisted row records
   who/what created it (`source="agent"`, the `agent_session_id`) and the
   approval decision (`approved_by`, `approved_at`, `approval_decision`).

### Technical requirements

- **Time-safety is the #1 invariant.** The future-feature-frame generator must
  never read an observed target at or after the forecast origin. A new
  load-bearing leakage test is the spec.
- New forecaster implements the existing `BaseForecaster` ABC — `fit(y, X)` /
  `predict(horizon, X)` — and is deterministic (`random_state`).
- **No new external dependency by default** — use scikit-learn's
  `HistGradientBoostingRegressor` (already a transitive dep via `scikit-learn`).
  Adding LightGBM is a **stop-and-ask** gate (see § Vision Tensions).
- `method` stays forward-compatible: a migration widens the CHECK constraint to
  `IN ('heuristic','model_exogenous')`.
- Pydantic v2 at every boundary; SQLAlchemy 2.0 async; RFC 7807 errors;
  `mypy --strict` + `pyright --strict` clean. No WebSocket. No managed-cloud SDK.

### Success Criteria

- [ ] `app/features/scenarios/feature_frame.py` builds a horizon-length feature
      matrix for a `(store, product)` series with assumption-driven exogenous
      columns; it is unit-tested and a leakage test proves no at/after-origin
      target read.
- [ ] A `regression` model is trainable and persists a `ModelBundle` whose
      `model` is a `RegressionForecaster`; `bundle.metadata` carries the feature
      column list and the historical tail needed to seed lags.
- [ ] `POST /scenarios/simulate` with a `regression` baseline returns
      `method="model_exogenous"`; with a baseline forecaster returns
      `method="heuristic"` (unchanged). Both pass through RFC 7807 on a bogus
      `run_id` — never a 500.
- [ ] An empty `ScenarioAssumptions` on the model path yields scenario ≈
      baseline (the unmodified future frame re-forecast).
- [ ] The Alembic migration widening the `method` CHECK upgrades **and**
      downgrades cleanly on a fresh DB; `down_revision = "43e35957a248"`.
- [ ] `POST /scenarios/compare` accepts 2-5 `scenario_id`s and returns a ranked
      `MultiScenarioComparison`; saved plans carry `tags`; cloning works.
- [ ] The planner page renders a multi-series comparison chart + ranked verdict
      table; dogfooded in a real browser.
- [ ] The experiment agent exposes `tool_propose_scenario` (read-only — never
      writes a row) and `tool_save_scenario` (mutating). `save_scenario` is in
      `agent_require_approval`, so a call pauses for HITL approval and persists
      the `scenario_plan` row only after `/agents/sessions/{id}/approve`.
- [ ] An agent-persisted `scenario_plan` row carries provenance — `source`,
      `agent_session_id` — and an audit trail — `approved_by`, `approved_at`,
      `approval_decision`. The Phase D migration adding those columns upgrades
      **and** downgrades cleanly on a fresh DB.
- [ ] `test_leakage.py` (MVP) still passes unweakened; the new future-frame
      leakage test passes.
- [ ] All gates green; no new external dependency (unless the LightGBM
      stop-and-ask is explicitly approved); no WebSocket; no cross-slice
      `service.py` import (see DECISIONS LOCKED #3).
- [ ] README + `docs/_base/{API_CONTRACTS,REPO_MAP_INDEX,DOMAIN_MODEL}.md`
      updated.

---

## All Needed Context

### DECISIONS LOCKED (resolved during planning — do NOT re-litigate)

1. **The heuristic path STAYS — the model path is ADDITIVE.** The MVP's
   `method="heuristic"` post-forecast multiplier is the documented fallback for
   any baseline that cannot consume exogenous features (`naive`,
   `seasonal_naive`, `moving_average` — every `fit`/`predict` carries
   `# noqa: ARG002`). `ScenarioService.simulate` branches on the loaded
   `bundle.config.model_type`: `regression` → model path, anything else →
   the existing heuristic path. A scenario result always carries an accurate
   `method`. Do NOT delete `adjustments.py` or the heuristic branch.

2. **Use `HistGradientBoostingRegressor`, NOT LightGBM, by default.** LightGBM
   is **not in `pyproject.toml`** (only `scikit-learn>=1.6.0` is) and
   `model_factory` raises `NotImplementedError` for `lightgbm`.
   `HistGradientBoostingRegressor` (`sklearn.ensemble`) is already importable,
   deterministic with `random_state`, NaN-tolerant (critical — lag features are
   `NaN` at series start), and needs no `pyproject.toml` change and no
   stop-and-ask gate. The new `RegressionForecaster` wraps it. LightGBM remains
   a future option behind `forecast_enable_lightgbm` — adding it is a separate,
   explicitly-approved change (§ Vision Tensions). See
   `PRPs/ai_docs/exogenous-regressor-forecasting.md` § 1, § 5.

3. **No cross-slice `service.py` import — same rule as the MVP.** A slice may
   NOT import another slice's `service.py` (`AGENTS.md` § Architecture). The
   future-feature-frame generator (`scenarios/feature_frame.py`) imports the
   **stable lower-level building blocks** only:
   `FeatureEngineeringService` + `FeatureDataLoader` from
   `featuresets/service.py` are *service-layer* classes — importing them is the
   forbidden cross-slice service import. RESOLUTION: `feature_frame.py` reuses
   the *featureset config schemas* (`featuresets/schemas.py` —
   `FeatureSetConfig`, `LagConfig`, `CalendarConfig`, `ExogenousConfig` — these
   are schema/value objects, allowed) and reads `data_platform` ORM models
   directly (allowed read-only ORM import, the sanctioned exception). It
   **replicates** the small slice of leakage-safe lag/calendar logic it needs —
   exactly as the MVP `scenarios/service.py` replicates the
   `ForecastingService.predict` body rather than importing `ForecastingService`.
   The `RegressionForecaster` itself lives in `forecasting/models.py` (it IS a
   forecasting concern — a `BaseForecaster` subclass), so the `scenarios` slice
   only imports `load_model_bundle` + `model_factory` + the `BaseForecaster`
   interface from `forecasting`, never `ForecastingService`. **Cite this in the
   PR** per `product-vision.md`.

4. **Long-lag + calendar + exogenous feature set — no recursion in v1.** The
   future feature frame uses ONLY: lags `k ≥ horizon` (knowable at the forecast
   origin), calendar features (pure function of the date), and assumption-driven
   exogenous columns (`price_*`, `promo_*`, `is_holiday`, lifecycle). It
   deliberately does NOT use lags shorter than the horizon, which would require
   recursive (iterative) forecasting — `ŷ[T+j-k]` feeding `lag_k` at `T+j`.
   Recursion is a documented Phase-2 extension. This keeps the leakage proof a
   direct assertion and the PRP one-pass implementable. See
   `PRPs/ai_docs/exogenous-regressor-forecasting.md` § 2.

5. **New `method` value = `"model_exogenous"`.** The MVP CHECK constraint is
   `method IN ('heuristic')`. The Phase B migration widens it to
   `IN ('heuristic','model_exogenous')`. The `ScenarioComparison.method` field
   becomes `Literal["heuristic", "model_exogenous"]`. The `disclaimer` string is
   method-specific: the model path gets a *model-driven* disclaimer (still a
   transparency control — a model estimate is not certainty) distinct from the
   heuristic one.

6. **There is no `scenarios` commit scope.** `.claude/rules/commit-format.md`
   has no `scenarios` scope. Use `feat(forecast)` for `RegressionForecaster`
   and the training path, `feat(api)` for the `scenarios`-slice backend,
   `feat(api,db)` for slice + migration, `feat(agents)` for the agent tool,
   `feat(ui)` for the frontend, `test(...)` matching the slice, `docs(docs)`.

7. **Current Alembic head is `43e35957a248`** (`create_scenario_plan_table`) —
   verified via `uv run alembic heads`. The Phase B migration sets
   `down_revision = "43e35957a248"`; the Phase C migration chains off the
   Phase B revision. **Re-verify with `uv run alembic heads` immediately before
   writing each migration** — another PRP merging first would move the head.

8. **No WebSocket, no managed-cloud SDK, no streaming.** Simulation and
   comparison are request/response. Consistent with `product-vision.md`.

9. **`scenario_plan` JSONB columns stay `assumptions` / `comparison`.** New
   library fields are real columns (`tags` as `JSONB` array, `cloned_from` as
   `String(32)` nullable) — never folded into the JSONB blobs, so they are
   queryable/indexable. Never name a column `metadata` (SQLAlchemy reserves it).

10. **Exogenous feature lag offsets = `(1, 7, 14, 28)` days — PINNED.** The
    maintainer resolved this (formerly an Open Question). The exogenous-feature
    lag offsets used by both the historical feature matrix (Phase B training,
    Task B4) and the future feature frame (Phase A, `feature_frame.py`) are
    `EXOGENOUS_LAGS = (1, 7, 14, 28)` — daily, weekly, fortnightly, and a
    four-week lag covering the dominant retail seasonality. The future *target*
    long-lag frame may use only the subset with `k >= horizon` (DECISIONS
    LOCKED #4); the rest are exogenous-driven (`price_*`, `promo_*`,
    `is_holiday`, lifecycle) and therefore knowable at the origin regardless of
    `k`. The trained bundle's `feature_columns` must reflect this exact offset
    set so the future frame matches column-for-column.

11. **`history_tail` length = `90` days — PINNED.** The maintainer resolved
    this (formerly an Open Question). The persisted historical tail —
    `history_tail` in the bundle metadata, fed to the future-feature-frame
    generator and used as regression context — is the last
    `HISTORY_TAIL_DAYS = 90` observed target values ending at the forecast
    origin `T`. 90 days exceeds the largest lag offset (28) with a comfortable
    buffer, so every long-lag column resolves inside the tail.

12. **Multi-scenario comparison cap = `5` — PINNED.** The maintainer resolved
    this (formerly an Open Question). `POST /scenarios/compare` accepts 2–5
    `scenario_id`s; the upper bound `MAX_COMPARE_SCENARIOS = 5` keeps the
    multi-series chart legible. Enforced at the schema boundary via
    `Field(..., min_length=2, max_length=5)` on `CompareScenariosRequest.
    scenario_ids` (a >5 list → 422), and the comparison-route integration test
    asserts the 6-scenario rejection.

13. **The agent CAN persist a scenario — behind the HITL approval gate.** The
    maintainer resolved this (formerly Open Question 4). Phase D ships TWO agent
    tools, not one:
    - `propose_scenario` — READ-ONLY. Returns a candidate `ScenarioAssumptions`
      + recommendation. No DB write, no approval needed.
    - `save_scenario` — MUTATING. Persists a `scenario_plan` row, but ONLY after
      a human approves via the existing HITL gate. It is gated EXACTLY like
      `tool_create_alias` / `tool_archive_run`: the tool name `save_scenario`
      is added to `agent_require_approval` in `app/core/config.py` (currently
      `["create_alias", "archive_run"]` → `["create_alias", "archive_run",
      "save_scenario"]`).
    This widens the agent's mutation surface. `AGENTS.md` § Safety requires a
    stop-and-ask before "widening an agent's mutation surface without adding
    the tool name to `agent_require_approval`" — this PRP IS that approval, and
    the change correctly adds the tool to the list, so the gate is satisfied.
    The PR description MUST call the widening out explicitly.
    An agent-persisted plan MUST capture, beyond the MVP's `assumptions` +
    `comparison`: target scope (`store_id`/`product_id` already exist; a
    `category` field is added if category-scoped plans are in play), horizon
    (already exists), AUTHOR/SOURCE metadata (`source ∈ {"agent","user"}`,
    `agent_session_id`), and an AUDIT TRAIL of the approval decision
    (`approved_by`, `approved_at`, `approval_decision ∈ {"approved","rejected"}`).
    The MVP `scenario_plan` table (per PRP-26) has only `assumptions` +
    `comparison` JSONB plus the scalar columns — so Phase D ships an Alembic
    migration adding the provenance/audit columns. Verified against
    `app/features/scenarios/models.py` and
    `alembic/versions/43e35957a248_create_scenario_plan_table.py`: the table
    today has `id, scenario_id, name, store_id, product_id, run_id, horizon,
    assumptions, comparison, method, created_at, updated_at` — no provenance
    columns exist yet. The Phase D migration adds discrete columns:
    `source` `String(16)` NOT NULL `server_default='user'` (CHECK
    `source IN ('agent','user')`); `agent_session_id` `String(32)` nullable;
    `approved_by` `String(120)` nullable; `approved_at` `DateTime(timezone=True)`
    nullable; `approval_decision` `String(16)` nullable (CHECK
    `approval_decision IN ('approved','rejected')`). Discrete columns (not a
    single `provenance` JSONB blob) so they are queryable/indexable, consistent
    with DECISIONS LOCKED #9. User-created plans default to `source='user'`
    with the audit columns NULL, so the existing MVP create path is
    backward-compatible.

### Documentation & References

```yaml
# ── MUST READ — the MVP (this PRP extends it) ──

- file: PRPs/PRP-26-scenario-simulation-what-if-planning.md
  why: The MVP PRP. Its DECISIONS LOCKED, Known Gotchas table, and Anti-Patterns
       all still hold. This PRP is an increment — read the MVP first to know
       what already exists.

- file: app/features/scenarios/service.py
  why: ScenarioService.simulate is the method this PRP branches. Read the
       heuristic body, _load_baseline_bundle (path-traversal guard — REUSE it
       verbatim), _forecast_start_date, _latest_unit_price. The model path is a
       NEW branch alongside the existing one.

- file: app/features/scenarios/schemas.py
  why: ScenarioComparison.method is Literal["heuristic"] — Phase B widens it.
       ScenarioAssumptions is the input both paths consume. Request bodies use
       ConfigDict(strict=True) + Field(strict=False) on dates — keep that.

- file: app/features/scenarios/models.py
  why: ScenarioPlan ORM + the method CHECK constraint Phase B widens. Phase C
       adds tags/cloned_from columns here.

- file: app/features/scenarios/adjustments.py
  why: The heuristic engine — NOT modified, but the model path mirrors its
       "pure, never raises" discipline for feature_frame.py helpers.

- file: app/features/scenarios/tests/test_leakage.py
  why: The MVP leakage spec — LOAD-BEARING, never weakened. The new
       future-frame leakage test follows this exact philosophy.

# ── MUST READ — forecasting (where RegressionForecaster lands) ──

- file: app/features/forecasting/models.py
  why: BaseForecaster ABC — fit(y, X=None) / predict(horizon, X=None) /
       get_params / set_params. RegressionForecaster subclasses it. model_factory
       (line 429) is the dispatch — add a "regression" branch. ModelType alias
       (line 426) gains "regression". CRITICAL: the existing baselines carry
       # noqa: ARG002 because they ignore X — RegressionForecaster is the FIRST
       to actually use X.

- file: app/features/forecasting/schemas.py
  why: ModelConfigBase (frozen, extra=forbid, config_hash). LightGBMModelConfig
       (line 107) is the closest precedent for a new ML model config — mirror
       it for RegressionModelConfig. ModelConfig union (line 148) gains the new
       config. TrainRequest strict-mode pattern.

- file: app/features/forecasting/persistence.py
  why: ModelBundle (model + config + metadata dict) and load_model_bundle /
       save_model_bundle. The regression bundle's metadata MUST additionally
       carry the feature column list and the historical tail (last N target
       values + dates) needed to build long-lag future-frame columns.

- file: app/features/forecasting/service.py
  why: ForecastingService.train_model + predict. The regression training path
       loads features instead of raw y; predict() must pass X for a regression
       model. Read _load_training_data (line 314) — the regression path needs a
       feature-loading sibling. The path-traversal guard in predict() (lines
       218-249) is the pattern _load_baseline_bundle already mirrors.

# ── MUST READ — featuresets (the time-safe machinery the future frame reuses) ──

- file: app/features/featuresets/service.py
  why: FeatureEngineeringService.compute_features — the time-safe HISTORICAL
       feature builder. _compute_lag_features (shift(positive)),
       _compute_rolling_features (shift(1).rolling), _compute_calendar_features,
       _compute_exogenous_features. CRITICAL: cutoff filter happens BEFORE any
       compute. feature_frame.py REPLICATES the leakage-safe lag+calendar logic
       it needs (DECISIONS LOCKED #3) — it does NOT import this class.
       FeatureDataLoader shows the SQL load patterns to mirror.

- file: app/features/featuresets/schemas.py
  why: FeatureSetConfig, LagConfig, CalendarConfig, ExogenousConfig — schema
       value-objects feature_frame.py MAY import (they are not service code).

- file: app/features/featuresets/tests/test_leakage.py
  why: The original load-bearing leakage spec. The future-frame leakage test
       mirrors its assertion style.

- file: PRPs/PRP-3.1B-lifecycle-compute.md
- file: PRPs/PRP-3.1D-promotion-compute.md
  why: The time-safety reasoning for lifecycle / promotion features — the
       future frame's exogenous columns must respect the same boundaries.

# ── MUST READ — agents (Phase D) ──

- file: app/features/agents/agents/experiment.py
  why: The agent that gains tool_propose_scenario. Mirror tool_create_alias
       EXACTLY — it shows the @agent.tool + @recoverable decorators, the
       requires_approval("create_alias") check, and the
       {"status":"approval_required", ...} early return.

- file: app/features/agents/agents/base.py
  why: requires_approval(action_name) (line ~255) checks
       settings.agent_require_approval. SYSTEM_PROMPT_HEADER /
       TOOL_USAGE_INSTRUCTIONS — the new tool's name goes in
       TOOL_USAGE_INSTRUCTIONS.

- file: app/features/agents/tools/registry_tools.py
  why: create_alias / archive_run — the "REQUIRES HUMAN APPROVAL" tool-function
       shape. scenarios/agent_tools.py mirrors this.

- file: app/features/agents/tools/forecasting_tools.py
  why: train_model / predict tool functions — how a tool wraps a service call
       and returns model_dump(). The propose_scenario tool mirrors the shape but
       is READ-ONLY (it proposes, it does not persist).

- file: app/core/config.py
  why: agent_require_approval (line 164) = ["create_alias", "archive_run"].
       Phase D adds "save_scenario" to this list — verified the current value
       is exactly the two-element list. This is a deliberate widening of the
       agent's mutation surface; AGENTS.md § Safety requires a stop-and-ask for
       that — this PRP IS that approval (see DECISIONS LOCKED #13).
       forecast_model_artifacts_dir (line 100), forecast_enable_lightgbm (101).

# ── MUST READ — frontend (Phase C) ──

- file: frontend/src/pages/visualize/planner.tsx
  why: The existing What-If Planner page — Phase C adds a multi-scenario
       comparison view to it (or a sibling tab). Read its Card/Select/Table
       skeleton, the saved-plans table, the TimeSeriesChart wiring.

- file: frontend/src/components/charts/time-series-chart.tsx
  why: The Recharts wrapper — currently 2-series (actualKey/predictedKey). The
       multi-scenario chart needs an M+1-series variant; verify the exact prop
       names before extending. Do NOT hand-roll a chart.

- file: frontend/src/hooks/use-scenarios.ts
  why: The existing hooks. Phase C adds useCompareScenarios (a mutation) and
       extends useScenarios with a tag filter param. Mirror the existing shape.

- file: frontend/src/lib/scenario-utils.ts
  why: Pure utils. Phase C adds mergeMultiScenarioSeries and a ranking helper —
       unit-tested in scenario-utils.test.ts.

- file: frontend/src/types/api.ts
  why: Scenario* interfaces — Phase C adds MultiScenarioComparison and extends
       ScenarioPlanResponse with tags/cloned_from. Phase B changes method to a
       'heuristic' | 'model_exogenous' union.

# ── External documentation (curated) ──

- docfile: PRPs/ai_docs/exogenous-regressor-forecasting.md
  why: THE primary reference for Phase A + B. Condenses the exogenous-regressor
       model contract, the leakage rule for FUTURE feature frames (the
       load-bearing part), the recursion-avoiding "long-lag" feature set, the
       HistGradientBoostingRegressor-vs-LightGBM decision, and multi-scenario
       comparison math. Read it before writing feature_frame.py or the
       RegressionForecaster.

- url: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html
  why: The estimator RegressionForecaster wraps — fit/predict signatures,
       random_state for determinism, native NaN handling.

- url: https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMRegressor.html
  why: ONLY if the LightGBM stop-and-ask is approved — the alternative estimator.

- url: https://pandas.pydata.org/docs/user_guide/timeseries.html
  why: Date ranges, shifting, rolling — for building the future feature frame.

- url: https://recharts.org/en-US/api/LineChart
  why: The multi-series scenario-comparison chart (Phase C).

- url: https://tanstack.com/query/latest/docs/framework/react/guides/mutations
  why: useCompareScenarios is a mutation; the tag-filtered list stays a query.

- url: https://www.nist.gov/itl/ai-risk-management-framework
  why: The transparency control — every ScenarioComparison declares its
       `method` and carries a method-appropriate `disclaimer`. A model-driven
       estimate still gets a caveat (not certainty).

# ── Rules — read before writing any code ──

- file: .claude/rules/product-vision.md
  why: Principle 5 (time-safety — the leakage test is load-bearing), principle 8
       (single-host — the HistGradientBoostingRegressor choice keeps it so),
       "not a generic ML platform" / "not a streaming system". Answer all 6
       Litmus-Test questions in the PR description.

- file: .claude/rules/security-patterns.md
  why: Pydantic v2 at every boundary; SQLAlchemy parameter binding;
       pathlib.Path.resolve() for artifact paths; strict-mode request-body
       policy; agent mutation tools MUST be in agent_require_approval.

- file: .claude/rules/test-requirements.md
  why: New module → test file; new endpoint → route test (2xx + 1 error);
       new model → constraint test; new migration → upgrade/downgrade clean.

- file: .claude/rules/commit-format.md
  why: type(scope): description (#issue). No `scenarios` scope (DECISIONS
       LOCKED #6).

- file: .claude/rules/branch-naming.md
  why: branch feat/scenario-simulation-full-version off dev.

- file: .claude/rules/ui-design.md
- file: .claude/rules/shadcn-ui.md
  why: Build the comparison view via frontend-design + shadcn-ui skills;
       dogfood in a real browser. Green tsc ≠ working UI.
```

### Current Codebase tree (relevant slices — all already exist)

```bash
app/features/
├── scenarios/                       # THE MVP SLICE — extended by this PRP
│   ├── __init__.py
│   ├── adjustments.py               # heuristic engine — unchanged
│   ├── models.py                    # ScenarioPlan — Phase B/C extend
│   ├── schemas.py                   # Phase B/C extend
│   ├── service.py                   # ScenarioService.simulate — Phase B branches
│   ├── routes.py                    # Phase C adds /scenarios/compare
│   └── tests/
├── forecasting/
│   ├── models.py                    # BaseForecaster + model_factory — Phase B
│   ├── schemas.py                   # ModelConfig union — Phase B
│   ├── persistence.py               # ModelBundle, load/save
│   └── service.py                   # train_model/predict — Phase B
├── featuresets/
│   ├── service.py                   # FeatureEngineeringService — pattern source
│   └── schemas.py                   # FeatureSetConfig etc. — importable value-objects
├── agents/
│   ├── agents/experiment.py         # gains tool_propose_scenario — Phase D
│   ├── agents/base.py               # requires_approval()
│   └── tools/                       # tool-function shape
└── data_platform/models.py          # SalesDaily, Calendar, Promotion, Product, PriceHistory
alembic/versions/
└── 43e35957a248_create_scenario_plan_table.py   # CURRENT HEAD (verify)
frontend/src/
├── pages/visualize/planner.tsx
├── hooks/use-scenarios.ts
├── lib/scenario-utils.ts (+ .test.ts)
├── components/charts/time-series-chart.tsx
└── types/api.ts
```

### Desired Codebase tree — files to ADD

```bash
# ── Phase A — future feature-frame generator ──
app/features/scenarios/feature_frame.py                 # leakage-safe X_future builder
app/features/scenarios/tests/test_feature_frame.py      # unit tests
app/features/scenarios/tests/test_future_frame_leakage.py  # LOAD-BEARING leakage spec

# ── Phase B — exogenous-regressor model + migration ──
alembic/versions/<revB>_widen_scenario_method_check.py  # method CHECK widen
app/features/forecasting/tests/test_regression_forecaster.py  # new forecaster unit tests

# ── Phase C — scenario library + multi-scenario comparison ──
alembic/versions/<revC>_add_scenario_library_columns.py # tags + cloned_from columns
app/features/scenarios/tests/test_compare_integration.py

# ── Phase D — agent-proposed scenarios ──
alembic/versions/<revD>_add_scenario_provenance_columns.py  # source + audit-trail columns
app/features/scenarios/agent_tools.py                   # propose_scenario + save_scenario tool functions
app/features/scenarios/tests/test_agent_tools.py

# ── docs ──
PRPs/ai_docs/exogenous-regressor-forecasting.md         # ALREADY CREATED by this PRP
```

### Files to MODIFY (all additive)

```bash
# Phase A
app/features/scenarios/__init__.py        # +export the frame builder if public

# Phase B
app/features/forecasting/models.py        # +RegressionForecaster, +model_factory branch, +ModelType
app/features/forecasting/schemas.py       # +RegressionModelConfig, +ModelConfig union member
app/features/forecasting/service.py       # +regression training/predict feature path
app/features/scenarios/schemas.py         # method -> Literal[...,"model_exogenous"]; +model disclaimer
app/features/scenarios/models.py          # CHECK constraint widened to match the migration
app/features/scenarios/service.py         # +_simulate_model_exogenous branch in simulate()

# Phase C
app/features/scenarios/models.py          # +tags JSONB, +cloned_from String(32)
app/features/scenarios/schemas.py         # +MultiScenarioComparison, +CompareScenariosRequest, +tags
app/features/scenarios/service.py         # +compare_scenarios, +clone, +tag filter on list_plans
app/features/scenarios/routes.py          # +POST /scenarios/compare, +tag query param, +clone
frontend/src/types/api.ts                 # +MultiScenarioComparison; method union; tags
frontend/src/hooks/use-scenarios.ts       # +useCompareScenarios, tag filter
frontend/src/lib/scenario-utils.ts (+test)# +mergeMultiScenarioSeries, +rankScenarios
frontend/src/pages/visualize/planner.tsx  # +comparison view
frontend/src/components/charts/time-series-chart.tsx  # +multi-series variant (or new component)

# Phase D
app/features/scenarios/models.py          # +source, +agent_session_id, +approved_by, +approved_at, +approval_decision
app/features/scenarios/schemas.py         # +provenance/audit fields on ScenarioPlanResponse; +SaveScenarioRequest
app/features/scenarios/service.py         # +create_plan provenance args; +approval-decision write path
app/features/agents/agents/experiment.py  # +tool_propose_scenario, +tool_save_scenario (HITL-gated)
app/features/agents/agents/base.py        # +tool names in TOOL_USAGE_INSTRUCTIONS
app/core/config.py                        # +"save_scenario" in agent_require_approval

# docs (all phases)
README.md
docs/_base/API_CONTRACTS.md
docs/_base/REPO_MAP_INDEX.md
docs/_base/DOMAIN_MODEL.md
```

### Known Gotchas of our codebase & Library Quirks

| # | Gotcha | Mitigation |
|---|--------|-----------|
| 1 | The future feature frame is a NEW leakage surface the MVP did not have — building `X_future` wrong leaks future targets into the forecast. | DECISIONS LOCKED #4: long-lag (`k ≥ horizon`) + calendar + assumption-driven exogenous columns ONLY — every value knowable at the forecast origin. The new `test_future_frame_leakage.py` is the load-bearing spec. |
| 2 | `BaseForecaster.predict(horizon, X=None)` — the baseline forecasters carry `# noqa: ARG002` because they ignore `X`. `RegressionForecaster` is the FIRST that uses it. | `RegressionForecaster.predict` must reject a `None` X (it cannot forecast without features) with a clear `ValueError`, and assert `X.shape[0] == horizon`. |
| 3 | `HistGradientBoostingRegressor` is deterministic ONLY with a fixed `random_state`; without it the bundle hash drifts. | Pass `random_state=settings.forecast_random_seed`. `BaseForecaster.__init__` already stores `random_state` — use it. |
| 4 | Lag features have `NaN` at the start of a series. A model that cannot handle `NaN` would crash on fit. | `HistGradientBoostingRegressor` handles `NaN` natively — do NOT impute it away (imputation that uses the series mean would itself leak). |
| 5 | The regression bundle must carry MORE metadata than a baseline bundle — the feature column list (so predict reproduces column order) and the historical target tail (to seed long lags). | Extend the `metadata` dict in the training path: `feature_columns: list[str]`, `history_tail: list[float]`, `history_tail_dates: list[str]`. `metadata` is `dict[str, object]` — JSON-safe values only. |
| 6 | `ScenarioComparison.method` is `Literal["heuristic"]` and the `scenario_plan.method` column has `CHECK method IN ('heuristic')`. Persisting `"model_exogenous"` against the un-migrated DB fails the CHECK. | Phase B ships the migration widening the CHECK **and** updates the `Literal` + the ORM `CheckConstraint` in `models.py` in the SAME PR. Migrations are forward-only — never edit `43e35957a248`. |
| 7 | The current Alembic head is `43e35957a248`. THREE new migrations chain in order: Phase B off `43e35957a248`, Phase C off the Phase B revision, Phase D off the Phase C revision. | `uv run alembic heads` immediately before writing EACH migration; never guess `down_revision`. Each migration's `down_revision` is the *previous* PRP-27 migration's revision id. |
| 8 | Importing `FeatureEngineeringService` / `FeatureDataLoader` from `scenarios` is a cross-slice **service** import — forbidden. | DECISIONS LOCKED #3: `feature_frame.py` imports only featureset *schema* value-objects + `data_platform` ORM models, and replicates the leakage-safe lag/calendar logic. Cite in the PR. |
| 9 | `JSONB` rejects Python `date`/`datetime`; the `tags` column is a JSON array. | `tags` is `list[str]` — JSON-native, fine. Continue persisting `assumptions`/`comparison` via `model_dump(mode="json")`. |
| 10 | An agent tool that *persists* a scenario without approval widens the agent's mutation surface — a security regression. | Phase D ships two tools: `propose_scenario` is READ-ONLY (returns a candidate payload, no approval). `save_scenario` is MUTATING — its name MUST be in `agent_require_approval` and it MUST be gated exactly like `tool_create_alias` (DECISIONS LOCKED #13). The PR explicitly calls out the mutation-surface widening. |
| 11 | A `regression` model trained for store A / product B cannot simulate store C — same store/product check as `ForecastingService.predict`. | `simulate` already reads `store_id`/`product_id` from `bundle.metadata`; the model path reuses that — no cross-grain forecast. |
| 12 | The repo uses CRLF on `.py` files (no `.gitattributes`); scripted text-mode writes flip them to LF. | Edit `forecasting/models.py`, `app/main.py`, `config.py` minimally; preserve line endings. |
| 13 | `units_delta_pct` divide-by-zero when baseline demand is 0 — already guarded in the MVP. | The model path reuses the same guard; do not regress it. |
| 14 | A regression model with too few training rows (short history) over-fits or fails the long-lag construction (no row at `T+1-k` for `k ≥ horizon`). | The training path requires `n_observations >= horizon_max + min_train_rows`; raise a clear `ValueError` otherwise — surfaces as RFC 7807. |

---

## Implementation Blueprint

### Data models and structure

**Phase A — `app/features/scenarios/feature_frame.py` (pure builder + thin DB read):**

```python
# Builds X_future — a (horizon, n_features) matrix — for one (store, product).
# Time-safety: every column is knowable at the forecast origin T (DECISIONS #4).

@dataclass
class FutureFeatureFrame:
    dates: list[date]            # T+1 .. T+horizon
    feature_columns: list[str]   # column order — MUST match the trained bundle
    matrix: list[list[float]]    # row-major; NaN allowed (HGBR handles it)

def build_calendar_columns(dates: list[date], config: CalendarConfig) -> ...: ...
    # PURE — dow/month/quarter/is_weekend from the date itself. Never leaks.

def build_long_lag_columns(history_tail: list[float], dates: list[date],
                            lags: tuple[int, ...]) -> ...: ...
    # lag_k at T+j == observed y[T+j-k]; REQUIRES k >= horizon so the index
    # T+j-k <= T is always inside history_tail. ASSERT min(lags) >= horizon.
    # PINNED: exogenous feature lag offsets are EXOGENOUS_LAGS = (1, 7, 14, 28)
    # days (DECISION LOCKED #10). For the long-lag *target* frame the same
    # offsets apply but only those with k >= horizon are usable in v1; offsets
    # below the horizon are deferred to the recursive Phase-2 extension.

def apply_assumption_columns(matrix, dates, assumptions: ScenarioAssumptions) -> ...: ...
    # price_*, promo_*, is_holiday, lifecycle columns DRIVEN BY the assumptions —
    # this is the intended what-if input (not leakage). Out-of-window day -> neutral.

async def build_future_frame(db, *, store_id, product_id, forecast_origin: date,
                              horizon, feature_columns, history_tail,
                              assumptions) -> FutureFeatureFrame: ...
    # Orchestrates the above; the only DB read is the optional Calendar lookup
    # for baseline (non-assumption) holidays — reading a Calendar row is a
    # timeless attribute, allowed.
    # PINNED: `history_tail` carries the last HISTORY_TAIL_DAYS = 90 observed
    # target values (ending at the forecast origin T). 90 days >= max lag
    # offset (28) plus a comfortable buffer, so every long-lag column resolves
    # inside the tail (DECISION LOCKED #11).

# ── PINNED modelling constants (DECISIONS LOCKED #10/#11/#12) ──
EXOGENOUS_LAGS: tuple[int, ...] = (1, 7, 14, 28)   # exogenous-feature lag offsets, days
HISTORY_TAIL_DAYS: int = 90                        # history fed to the future-frame generator
MAX_COMPARE_SCENARIOS: int = 5                     # cap on POST /scenarios/compare
```

**Phase B — `RegressionForecaster` in `forecasting/models.py`:**

```python
class RegressionForecaster(BaseForecaster):
    """Feature-driven forecaster wrapping HistGradientBoostingRegressor.

    The FIRST forecaster that consumes the exogenous X argument.
    """
    def __init__(self, *, max_iter=200, learning_rate=0.05, max_depth=6,
                 random_state=42) -> None: ...
    def fit(self, y, X) -> RegressionForecaster:        # X REQUIRED — no noqa
        # raise ValueError if X is None or X.shape[0] != len(y)
    def predict(self, horizon, X) -> np.ndarray:        # X REQUIRED
        # raise ValueError if X is None or X.shape[0] != horizon
    def get_params(self) -> dict[str, Any]: ...
    def set_params(self, **params) -> RegressionForecaster: ...

# forecasting/schemas.py:
class RegressionModelConfig(ModelConfigBase):
    model_type: Literal["regression"] = "regression"
    max_iter: int = Field(default=200, ge=10, le=1000)
    learning_rate: float = Field(default=0.05, ge=0.001, le=1.0)
    max_depth: int = Field(default=6, ge=1, le=20)
    feature_config_hash: str | None = None
# ModelConfig union gains RegressionModelConfig.
# model_factory gains: model_type == "regression" -> RegressionForecaster(...)
```

**Phase B — `scenarios/schemas.py` changes:**

```python
ScenarioMethod = Literal["heuristic", "model_exogenous"]
# ScenarioComparison.method: ScenarioMethod
MODEL_EXOGENOUS_DISCLAIMER = (
    "Model estimate: this scenario re-forecasts demand through a feature-driven "
    "model using the assumptions as future inputs. It reflects learned patterns "
    "but remains an estimate under uncertainty — not a guarantee."
)
```

**Phase C — `scenarios/models.py` + `schemas.py` additions:**

```python
# models.py — ScenarioPlan gains:
tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
cloned_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
# + a GIN index on tags.

# schemas.py:
class CompareScenariosRequest(BaseModel):       # ConfigDict(strict=True)
    # max_length is the PINNED cap MAX_COMPARE_SCENARIOS = 5 (DECISION LOCKED
    # #12). Keep the literal 5 in the Field constraint (Pydantic constraints
    # must be literal) and reference the constant in the docstring/validation
    # test so the two never drift.
    scenario_ids: list[str] = Field(..., min_length=2, max_length=5)
    rank_by: Literal["revenue_delta","units_delta"] = "revenue_delta"
class ScenarioComparisonRow(BaseModel):         # from_attributes
    scenario_id, name, units_delta, revenue_delta, coverage_verdict, rank
class MultiScenarioComparison(BaseModel):       # from_attributes
    baseline_total_units, baseline_revenue
    scenarios: list[ScenarioComparisonRow]
    chart_series: list[dict[str, ...]]          # merged date-keyed rows for Recharts
```

**Phase D — `scenarios/models.py` + `schemas.py` provenance/audit additions:**

```python
# models.py — ScenarioPlan gains (DECISIONS LOCKED #13):
SCENARIO_SOURCE_USER = "user"
SCENARIO_SOURCE_AGENT = "agent"

source: Mapped[str] = mapped_column(
    String(16), nullable=False, server_default=SCENARIO_SOURCE_USER
)
agent_session_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
approved_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True
)
approval_decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
# + CheckConstraint("source IN ('user','agent')", name="ck_scenario_plan_source")
# + CheckConstraint(
#       "approval_decision IN ('approved','rejected')",
#       name="ck_scenario_plan_approval_decision")
# + an index on source for "show me agent-proposed plans" queries.

# schemas.py:
class SaveScenarioRequest(BaseModel):           # ConfigDict(strict=True)
    # what the save_scenario agent tool persists once HITL-approved.
    name: str
    assumptions: ScenarioAssumptions
    store_id: int
    product_id: int
    horizon: int
    run_id: str
    source: Literal["user", "agent"] = "agent"
    agent_session_id: str | None = None         # the originating agent session
# ScenarioPlanResponse / ScenarioListItem gain: source, agent_session_id,
#   approved_by, approved_at, approval_decision (all from_attributes).
```

### list of tasks (dependency-ordered)

```yaml
Task 0 — SETUP:
  - Open a GitHub issue "Scenario Simulation — Full Version (#)"; confirm OPEN.
  - git fetch origin && git switch -c feat/scenario-simulation-full-version origin/dev
  - GOTCHA: no `scenarios` commit scope (DECISIONS LOCKED #6).
  - VALIDATE: gh issue view <N> --json state -> OPEN

# ════════ PHASE A — Future Feature-Frame Generator (backend) ════════

Task A1 — CREATE app/features/scenarios/feature_frame.py:
  - The leakage-safe X_future builder (see Data models above). PURE helpers for
    calendar + long-lag + assumption columns; one async build_future_frame that
    does the optional Calendar read.
  - PINNED constants (DECISIONS LOCKED #10/#11/#12): define module-level
    EXOGENOUS_LAGS = (1, 7, 14, 28), HISTORY_TAIL_DAYS = 90,
    MAX_COMPARE_SCENARIOS = 5. The exogenous columns built are price_*, promo_*,
    is_holiday, and lifecycle, lagged at EXOGENOUS_LAGS.
  - GOTCHA #1/#8: long-lag only (assert min(lags) >= horizon); import featureset
    SCHEMA value-objects + data_platform ORM only — never FeatureEngineeringService.
  - PATTERN: featuresets/service.py _compute_calendar_features /
    _compute_lag_features (REPLICATE the leakage-safe logic, do not import).
  - VALIDATE: uv run mypy app/features/scenarios/feature_frame.py && uv run pyright app/features/scenarios/

Task A2 — CREATE tests/test_feature_frame.py:
  - Calendar columns are a pure function of the date; long-lag columns equal the
    correct history_tail index; assumption columns apply only inside windows;
    matrix shape == (horizon, len(feature_columns)).
  - PATTERN: scenarios/tests/test_adjustments.py.
  - VALIDATE: uv run pytest -v -m "not integration" app/features/scenarios/tests/test_feature_frame.py

Task A3 — CREATE tests/test_future_frame_leakage.py (LOAD-BEARING):
  - Assert: no feature value for any horizon day reads an observed target at or
    after the forecast origin T; a long-lag column with k >= horizon only ever
    indexes history_tail (index <= T); calendar columns ignore the target
    entirely; an assumption window before T contributes nothing.
  - PATTERN: scenarios/tests/test_leakage.py + featuresets/tests/test_leakage.py.
  - GOTCHA: never weaken this test to make a feature pass (AGENTS.md § Safety).
  - VALIDATE: uv run pytest -v -m "not integration" app/features/scenarios/tests/test_future_frame_leakage.py

# ════════ PHASE B — Exogenous-Regressor Model + model-driven simulation ════════

Task B1 — MODIFY app/features/forecasting/schemas.py:
  - Add RegressionModelConfig (mirror LightGBMModelConfig); add it to the
    ModelConfig union.
  - VALIDATE: uv run python -c "from app.features.forecasting.schemas import RegressionModelConfig; print('ok')"

Task B2 — MODIFY app/features/forecasting/models.py:
  - Add RegressionForecaster(BaseForecaster) wrapping HistGradientBoostingRegressor;
    add "regression" to the ModelType alias; add the model_factory branch.
  - GOTCHA #2/#3/#4: X is REQUIRED for fit/predict (raise ValueError on None /
    shape mismatch); pass random_state; do NOT impute NaN away.
  - PATTERN: the existing forecaster classes (interface), LightGBM branch in
    model_factory (the feature-flag shape — but regression needs NO flag).
  - VALIDATE: uv run mypy app/features/forecasting/ && uv run pyright app/features/forecasting/

Task B3 — CREATE app/features/forecasting/tests/test_regression_forecaster.py:
  - fit/predict round-trip on synthetic features; predict rejects None X and a
    wrong-shape X; determinism (same random_state -> same output); get/set_params.
  - PATTERN: forecasting/tests/test_models.py.
  - VALIDATE: uv run pytest -v -m "not integration" app/features/forecasting/tests/test_regression_forecaster.py

Task B4 — MODIFY app/features/forecasting/service.py:
  - Add a regression training path: when config.model_type == "regression",
    build HISTORICAL features (replicate the leakage-safe lag/calendar logic, or
    a minimal long-lag set matching feature_frame.py), fit RegressionForecaster,
    and persist a ModelBundle whose metadata carries feature_columns +
    history_tail + history_tail_dates (GOTCHA #5). Predict for a regression
    model passes X.
  - PINNED (DECISIONS LOCKED #10/#11): the historical feature matrix uses the
    SAME exogenous lag offsets EXOGENOUS_LAGS = (1, 7, 14, 28) as the future
    frame; metadata `history_tail` / `history_tail_dates` persist the last
    HISTORY_TAIL_DAYS = 90 observed target values + dates. The persisted
    `feature_columns` order MUST match feature_frame.py column-for-column.
  - GOTCHA #14: require enough history; raise ValueError otherwise.
  - VALIDATE: uv run mypy app/ && uv run pyright app/

Task B5 — CREATE alembic migration <revB>_widen_scenario_method_check.py:
  - uv run alembic heads (expect 43e35957a248); revision -m "widen scenario
    method check"; hand-write upgrade()/downgrade() that drop+recreate the
    ck_scenario_plan_method CheckConstraint (upgrade -> IN
    ('heuristic','model_exogenous'); downgrade -> IN ('heuristic')).
  - GOTCHA #6/#7: down_revision = "43e35957a248" (VERIFY). Postgres needs
    op.drop_constraint + op.create_check_constraint.
  - VALIDATE: docker compose up -d && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head

Task B6 — MODIFY app/features/scenarios/models.py + schemas.py:
  - models.py: widen the ORM CheckConstraint to match the migration; add the
    SCENARIO_METHOD_MODEL_EXOGENOUS constant.
  - schemas.py: ScenarioComparison.method -> Literal["heuristic","model_exogenous"];
    add MODEL_EXOGENOUS_DISCLAIMER.
  - VALIDATE: uv run mypy app/features/scenarios/

Task B7 — MODIFY app/features/scenarios/service.py:
  - In simulate(): after loading the bundle, branch on bundle.config.model_type.
    "regression" -> _simulate_model_exogenous (build the future frame via
    feature_frame.build_future_frame from the bundle's feature_columns +
    history_tail + the assumptions; call bundle.model.predict(horizon, X);
    derive the same ScenarioPoint/aggregate shape; method="model_exogenous",
    disclaimer=MODEL_EXOGENOUS_DISCLAIMER). Anything else -> the existing
    heuristic branch UNCHANGED.
  - GOTCHA: a baseline run that lacks feature_columns metadata -> a clear
    ValueError -> RFC 7807 (never a 500).
  - PATTERN: the existing heuristic simulate body (point/aggregate construction).
  - VALIDATE: uv run mypy app/ && uv run pyright app/

Task B8 — EXTEND tests/test_routes_integration.py + add a model-path test:
  - A trained_regression_model fixture (real bundle on disk); simulate with a
    regression run_id -> 200, method=="model_exogenous"; empty assumptions ->
    scenario ≈ baseline; persisting that comparison -> the CHECK accepts it; a
    baseline run_id still -> method=="heuristic". Migration constraint test.
  - GOTCHA: never mock the DB; integration needs docker compose up + alembic.
  - VALIDATE: docker compose up -d && uv run alembic upgrade head && uv run pytest -v -m integration app/features/scenarios/

# ════════ PHASE C — Scenario Library + Multi-Scenario Comparison ════════

Task C1 — CREATE alembic migration <revC>_add_scenario_library_columns.py:
  - uv run alembic heads (expect <revB>); add tags JSONB (server_default '[]',
    not null) + cloned_from String(32) nullable + a GIN index on tags.
  - GOTCHA #7: down_revision = "<revB>".
  - VALIDATE: docker compose up -d && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head

Task C2 — MODIFY scenarios/models.py + schemas.py:
  - models.py: tags + cloned_from columns + GIN index (match the migration).
  - schemas.py: CompareScenariosRequest, ScenarioComparisonRow,
    MultiScenarioComparison; add tags to ScenarioPlanResponse/ScenarioListItem;
    add an optional cloned_from to CreateScenarioRequest.
  - VALIDATE: uv run mypy app/features/scenarios/

Task C3 — MODIFY scenarios/service.py + routes.py:
  - service.py: compare_scenarios (load N plans, rank by the metric, build
    chart_series), tag handling on create_plan, a tag filter on list_plans,
    clone (a create_plan variant pre-filled from an existing plan).
  - routes.py: POST /scenarios/compare; a `tags` query param on GET /scenarios;
    a POST /scenarios/{id}/clone (or a cloned_from field on POST /scenarios).
  - PATTERN: the MVP routes (404 mapping, RFC 7807).
  - VALIDATE: uv run python -c "from app.main import app; assert '/scenarios/compare' in {r.path for r in app.routes}; print('wired')"

Task C4 — CREATE tests/test_compare_integration.py:
  - compare 2-5 saved plans -> ranked rows; <2 or >5 -> 422 (the >5 case
    exercises the PINNED MAX_COMPARE_SCENARIOS = 5 cap, DECISIONS LOCKED #12);
    a bogus id -> 404; tag filter; clone round-trip.
  - VALIDATE: docker compose up -d && uv run pytest -v -m integration app/features/scenarios/tests/test_compare_integration.py

Task C5 — MODIFY frontend types/hooks/utils:
  - types/api.ts: method union; tags; MultiScenarioComparison + rows.
  - use-scenarios.ts: useCompareScenarios (mutation); tag filter on useScenarios.
  - scenario-utils.ts (+test): mergeMultiScenarioSeries, rankScenarios.
  - VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm test --run src/lib/scenario-utils.test.ts

Task C6 — MODIFY frontend planner page + chart:
  - A multi-series chart variant (extend time-series-chart.tsx with a `series`
    prop, or a new MultiSeriesChart) — pass M+1 series; a comparison panel on
    planner.tsx (multi-select saved plans, run compare, ranked verdict table,
    chart). Build via frontend-design + shadcn-ui skills.
  - GOTCHA #12: green tsc ≠ working UI.
  - VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

# ════════ PHASE D — Agent-Proposed Scenarios + Approval Flow ════════

Task D1 — CREATE alembic migration <revD>_add_scenario_provenance_columns.py:
  - uv run alembic heads (expect <revC>); revision -m "add scenario provenance
    columns". upgrade() adds five columns to scenario_plan: source String(16)
    NOT NULL server_default 'user'; agent_session_id String(32) nullable;
    approved_by String(120) nullable; approved_at DateTime(timezone=True)
    nullable; approval_decision String(16) nullable. Add CHECK constraints
    ck_scenario_plan_source ("source IN ('user','agent')") and
    ck_scenario_plan_approval_decision ("approval_decision IN
    ('approved','rejected')"), and an index on source. downgrade() drops the
    index, the two constraints, and the five columns.
  - GOTCHA #6/#7: down_revision = "<revC>" (VERIFY with alembic heads). The
    server_default 'user' makes existing rows backward-compatible.
  - VALIDATE: docker compose up -d && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head

Task D2 — MODIFY app/features/scenarios/models.py + schemas.py + service.py:
  - models.py: add source / agent_session_id / approved_by / approved_at /
    approval_decision columns + the two CHECK constraints + the source index
    (match the migration). Add SCENARIO_SOURCE_USER / SCENARIO_SOURCE_AGENT.
  - schemas.py: add SaveScenarioRequest; add source/agent_session_id/
    approved_by/approved_at/approval_decision to ScenarioPlanResponse +
    ScenarioListItem.
  - service.py: extend create_plan to accept the provenance fields (defaulting
    source='user', audit columns None — keeps the MVP create path
    backward-compatible); add the approval-decision write path that stamps
    approved_by/approved_at/approval_decision when an agent save is approved.
  - GOTCHA #9: discrete columns, never a `metadata`-named column.
  - VALIDATE: uv run mypy app/features/scenarios/

Task D3 — CREATE app/features/scenarios/agent_tools.py (TWO tools):
  - propose_scenario(db, store_id, product_id, horizon, objective) -> a candidate
    ScenarioAssumptions + a plain-language recommendation. READ-ONLY — proposes,
    never persists (GOTCHA #10).
  - save_scenario(db, request: SaveScenarioRequest, *, agent_session_id) ->
    persists a scenario_plan row via the scenarios service create path, stamping
    source='agent', the agent_session_id, and the approval audit trail. This is
    the MUTATING tool — it runs only after the HITL gate releases it.
  - PATTERN: agents/tools/forecasting_tools.py (read-only tool shape);
    agents/tools/registry_tools.py create_alias (the mutating, approval-gated
    tool shape).
  - GOTCHA #8: import scenarios *schemas* + the service create path through this
    module — agent_tools.py is the seam; agents/ imports agent_tools.py, never
    scenarios/service.py directly.
  - VALIDATE: uv run mypy app/features/scenarios/agent_tools.py

Task D4 — MODIFY app/core/config.py + agents/agents/base.py:
  - config.py: add "save_scenario" to agent_require_approval. Current value is
    ["create_alias", "archive_run"] (verified, app/core/config.py:164) ->
    ["create_alias", "archive_run", "save_scenario"]. This is a deliberate
    mutation-surface widening — DECISIONS LOCKED #13; flag it in the PR.
  - base.py: add tool_propose_scenario + tool_save_scenario to
    TOOL_USAGE_INSTRUCTIONS.
  - GOTCHA #12: preserve line endings.
  - VALIDATE: uv run python -c "from app.core.config import get_settings; print(get_settings().agent_require_approval)"

Task D5 — MODIFY app/features/agents/agents/experiment.py:
  - Register @agent.tool @recoverable tool_propose_scenario (read-only — calls
    scenarios.agent_tools.propose_scenario; no approval gate).
  - Register @agent.tool @recoverable tool_save_scenario, gated EXACTLY like
    tool_create_alias: a requires_approval("save_scenario") check + a
    {"status":"approval_required", ...} early return; the persist happens only
    once the approval is granted.
  - GOTCHA #8/#10: do NOT import scenarios/service.py into agents — the tool
    functions in scenarios/agent_tools.py are the seam; agents imports that module.
  - VALIDATE: uv run mypy app/ && uv run pyright app/

Task D6 — CREATE tests/test_agent_tools.py:
  - propose_scenario returns a valid ScenarioAssumptions + a non-empty
    recommendation; it performs NO DB writes.
  - save_scenario, when approved, persists a scenario_plan row with
    source='agent', the agent_session_id, and the audit columns populated.
  - An integration test asserts the HITL gate fires: a save_scenario call on the
    experiment agent returns {"status":"approval_required"} and writes no row
    until /agents/sessions/{id}/approve is called.
  - PATTERN: agents/tests/ tool tests; the create_alias HITL test.
  - VALIDATE: docker compose up -d && uv run pytest -v -m integration app/features/scenarios/tests/test_agent_tools.py

# ════════ CROSS-PHASE — docs + dogfood + PR ════════

Task E1 — Dogfood (MANDATORY per .claude/rules/ui-design.md):
  - docker compose up -d && alembic upgrade head && seed; train a regression
    model; exercise /visualize/planner via webapp-testing / agent-browser:
    model-causal simulation (confirm method="model_exogenous" in the response),
    save 2-3 plans, run a multi-scenario comparison, confirm the chart + ranked
    table; in the chat agent ask for scenario suggestions and confirm the
    proposal renders. Capture screenshots.
  - VALIDATE: screenshots captured; all manual checks pass.

Task E2 — UPDATE docs:
  - README.md; docs/_base/API_CONTRACTS.md (+/scenarios/compare row, the new
    method value, the regression model_type); REPO_MAP_INDEX.md
    (feature_frame.py, agent_tools.py); DOMAIN_MODEL.md (the model_exogenous
    method, tags/cloned_from + the source/agent_session_id/approved_by/
    approved_at/approval_decision provenance-audit columns on the scenario_plan
    aggregate, the future-feature-frame concept, the agent save_scenario HITL
    invariant, + ubiquitous-language rows). docs/_base/SECURITY.md — note
    save_scenario added to agent_require_approval (the HITL-gated tool list).
  - VALIDATE: git diff --stat docs/ README.md

Task E3 — Commit + PR (one PR per phase preferred):
  - Commits (each (#issue), no AI co-author trailer), e.g.:
    feat(forecast): add exogenous-regressor forecaster (#N)
    feat(api): add leakage-safe future feature-frame generator (#N)
    feat(api,db): add model-driven scenario simulation path (#N)
    feat(api,db): add scenario library and multi-scenario comparison (#N)
    feat(ui): add multi-scenario comparison view (#N)
    feat(api,db): add scenario provenance and audit columns (#N)
    feat(agents): add agent-proposed and HITL-gated save scenario tools (#N)
    test(...) / docs(docs): ...
  - GOTCHA: the PR description MUST (a) cite the no-cross-slice-service-import
    decision (DECISIONS LOCKED #3); (b) flag the new leakage surface and point
    at test_future_frame_leakage.py as its spec; (c) state HistGradientBoosting
    over LightGBM and why (no new dependency); (d) answer the 6 product-vision
    Litmus questions; (e) note the model path is additive — the heuristic path
    stays; (f) explicitly call out the agent mutation-surface widening — the
    `save_scenario` tool added to `agent_require_approval` (DECISIONS LOCKED
    #13) — per AGENTS.md § Safety "Stop and ask before widening an agent's
    mutation surface".
  - VALIDATE: open PR(s) into dev; CI green; merge.
```

### Per-task pseudocode (critical details only)

```python
# Task A1 — the long-lag column builder (the leakage-critical helper)
def build_long_lag_columns(history_tail, dates, lags, horizon):
    # history_tail[-1] is the observed target at the forecast origin T.
    # history_tail holds HISTORY_TAIL_DAYS = 90 values (DECISIONS LOCKED #11).
    # `lags` is the subset of EXOGENOUS_LAGS = (1, 7, 14, 28) with k >= horizon.
    # For horizon day T+j (j in 1..horizon) and lag k, the value is y[T+j-k].
    # SAFETY: require k >= horizon so j-k <= 0, i.e. the index lands in history.
    assert min(lags) >= horizon, "long-lag frame forbids k < horizon (DECISIONS #4)"
    columns = {}
    for k in lags:
        col = []
        for j in range(1, horizon + 1):
            # offset back from the END of history_tail: index = -k + (j-1) ... <= -1
            idx = -k + (j - 1)
            col.append(history_tail[idx] if -len(history_tail) <= idx < 0 else float("nan"))
        columns[f"lag_{k}"] = col
    return columns

# Task B7 — the model-exogenous simulate branch
async def _simulate_model_exogenous(self, db, request, bundle) -> ScenarioComparison:
    meta = bundle.metadata
    feature_columns = meta.get("feature_columns")
    history_tail = meta.get("history_tail")
    if not feature_columns or not history_tail:
        raise ValueError(
            f"run_id '{request.run_id}' is a regression model without the "
            "feature metadata required for a scenario forecast."
        )
    origin = self._forecast_start_date(meta.get("train_end_date")) - timedelta(days=1)
    frame = await build_future_frame(
        db, store_id=..., product_id=..., forecast_origin=origin,
        horizon=request.horizon, feature_columns=feature_columns,
        history_tail=history_tail, assumptions=request.assumptions)
    X = np.array(frame.matrix, dtype=np.float64)
    scenario_values = [float(v) for v in bundle.model.predict(request.horizon, X)]
    # baseline = predict with the SAME frame but assumptions stripped (empty)
    baseline_frame = await build_future_frame(..., assumptions=ScenarioAssumptions())
    baseline_values = [float(v) for v in bundle.model.predict(
        request.horizon, np.array(baseline_frame.matrix, dtype=np.float64))]
    # ... build ScenarioPoint list + aggregates exactly like the heuristic path,
    #     guarding units_delta_pct /0; method="model_exogenous",
    #     disclaimer=MODEL_EXOGENOUS_DISCLAIMER.
```

### Integration Points

```yaml
DATABASE:
  - migration B: "drop+recreate ck_scenario_plan_method ->
                  IN ('heuristic','model_exogenous')"
  - migration C: "add scenario_plan.tags JSONB (default '[]') +
                  cloned_from String(32) nullable + GIN index on tags"
  - migration D: "add scenario_plan.source String(16) NOT NULL default 'user' +
                  agent_session_id String(32) + approved_by String(120) +
                  approved_at DateTime(tz) + approval_decision String(16);
                  CHECK source IN ('user','agent'); CHECK approval_decision IN
                  ('approved','rejected'); index on source"
  - down_revision: "B off 43e35957a248; C off <revB>; D off <revC> —
                    VERIFY with alembic heads before each"

ROUTES:
  - POST /scenarios/compare added to the existing scenarios router; a `tags`
    query param on GET /scenarios; a clone path. (Router already wired in
    app/main.py — no main.py change.)

FORECASTING:
  - model_factory gains a "regression" branch (no feature flag — unlike lightgbm).
  - ModelType / ModelConfig union gain the regression member.

AGENTS:
  - tool_propose_scenario (read-only) AND tool_save_scenario (mutating,
    HITL-gated) on the experiment agent; TOOL_USAGE_INSTRUCTIONS updated for
    both; agent_require_approval gains "save_scenario".

CONFIG:
  - app/core/config.py: agent_require_approval gains "save_scenario"
    (["create_alias","archive_run"] -> [...,"save_scenario"]) — a deliberate
    mutation-surface widening (DECISIONS LOCKED #13).
  - no other new setting; reuses forecast_model_artifacts_dir,
    forecast_random_seed. forecast_enable_lightgbm stays unused by this PRP.

FRONTEND ROUTING:
  - no new route — the comparison view extends the existing /visualize/planner
    page (a panel or tab).
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . --fix && uv run ruff format --check .
cd frontend && pnpm lint
# Traps: date.today()/naive datetime -> ruff DTZ (use datetime.now(UTC));
#        os.path -> ruff PTH; a stray # noqa -> RUF100.
```

### Level 2: Type Checks

```bash
uv run mypy app/ && uv run pyright app/        # both --strict, both gate merge
cd frontend && pnpm tsc --noEmit
```

### Level 3: Unit Tests

```bash
uv run pytest -v -m "not integration" app/features/scenarios/ app/features/forecasting/
cd frontend && pnpm test --run src/lib/scenario-utils.test.ts
# MUST include the un-weakened MVP leakage spec + the new future-frame leakage spec.
```

### Level 4: Integration Tests + Migrations

```bash
docker compose up -d && uv run alembic upgrade head
uv run pytest -v -m integration app/features/scenarios/
uv run alembic downgrade -3 && uv run alembic upgrade head   # all 3 new migrations up/down
```

### Level 5: Manual Validation (dogfood — REQUIRED)

```bash
docker compose up -d && uv run alembic upgrade head
uv run python scripts/seed_random.py --full-new --seed 42 --confirm
# train a regression model:
curl -s -X POST http://localhost:8123/forecasting/train -H 'content-type: application/json' \
  -d '{"store_id":1,"product_id":101,"train_start_date":"2025-01-01",
       "train_end_date":"2026-04-30","config":{"model_type":"regression"}}'
# model-causal simulate (use the run_id from the train response):
curl -s -X POST http://localhost:8123/scenarios/simulate -H 'content-type: application/json' \
  -d '{"run_id":"<regression-run-id>","horizon":14,
       "assumptions":{"price":{"change_pct":-0.15,
       "start_date":"2026-05-02","end_date":"2026-05-15"}}}' | grep -o '"method":"[a-z_]*"'
#   -> expect "method":"model_exogenous"
# bogus run_id -> 404, not 500:
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8123/scenarios/simulate \
  -H 'content-type: application/json' -d '{"run_id":"nope","horizon":14,"assumptions":{}}'
# multi-scenario compare (after saving >=2 plans):
curl -s -X POST http://localhost:8123/scenarios/compare -H 'content-type: application/json' \
  -d '{"scenario_ids":["<id1>","<id2>"],"rank_by":"revenue_delta"}' | head -c 400
# Frontend: cd frontend && ./node_modules/.bin/vite --host 0.0.0.0
#   -> /visualize/planner via webapp-testing/agent-browser: run a model-causal
#      sim, save 2-3 plans, run the comparison view, confirm the multi-series
#      chart + ranked table; chat agent -> ask for scenario suggestions.
```

---

## Final Validation Checklist

- [ ] `uv run ruff check . && uv run ruff format --check .` — clean
- [ ] `uv run mypy app/ && uv run pyright app/` — clean (`--strict`)
- [ ] `uv run pytest -v -m "not integration"` — green (MVP leakage spec
      UNWEAKENED + new future-frame leakage spec passing)
- [ ] `docker compose up -d && uv run pytest -v -m integration` — green
- [ ] All three new migrations (B method-CHECK widen, C library columns,
      D provenance/audit columns) upgrade **and** downgrade cleanly on a fresh DB
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` — green
- [ ] A `regression` model trains and persists feature_columns + history_tail
- [ ] `POST /scenarios/simulate` returns `method="model_exogenous"` for a
      regression baseline, `method="heuristic"` for a baseline forecaster; a
      bogus run_id → RFC 7807, not 500
- [ ] `POST /scenarios/compare` ranks 2-5 saved plans; tag filter + clone work
- [ ] The planner comparison view renders a multi-series chart + ranked table —
      dogfooded in a browser (screenshots captured)
- [ ] `tool_propose_scenario` works and persists nothing; `tool_save_scenario`
      is in `agent_require_approval`, pauses for HITL approval, and only then
      writes a `scenario_plan` row carrying `source="agent"`, `agent_session_id`,
      and the approval audit trail (`approved_by`/`approved_at`/`approval_decision`)
- [ ] No new external dependency (LightGBM NOT added unless the stop-and-ask was
      explicitly approved); no WebSocket; no cross-slice `service.py` import
- [ ] README + `docs/_base/{API_CONTRACTS,REPO_MAP_INDEX,DOMAIN_MODEL}.md`
      updated
- [ ] Branch `feat/scenario-simulation-full-version`; every commit references
      the issue; scopes are `forecast`/`api`/`api,db`/`agents`/`ui`/`docs`; no
      AI co-author trailer
- [ ] PR description cites DECISIONS LOCKED #3, flags the new leakage surface +
      its spec, states the HistGradientBoosting-over-LightGBM choice, and
      answers the 6 Litmus questions

---

## Anti-Patterns to Avoid

- ❌ Don't re-build the MVP slice — `app/features/scenarios/` already exists.
- ❌ Don't delete `adjustments.py` or the heuristic `simulate` branch — the
  model path is ADDITIVE (DECISIONS LOCKED #1).
- ❌ Don't build a future feature frame that uses lags `k < horizon` — that
  needs recursion and a far harder leakage proof (DECISIONS LOCKED #4).
- ❌ Don't import `FeatureEngineeringService` / `FeatureDataLoader` /
  `ForecastingService` into `scenarios` — cross-slice service import
  (DECISIONS LOCKED #3). Import schema value-objects + ORM models; replicate.
- ❌ Don't weaken `scenarios/tests/test_leakage.py` or skip
  `test_future_frame_leakage.py` — they are the leakage spec.
- ❌ Don't add LightGBM to `pyproject.toml` without an explicit stop-and-ask —
  `HistGradientBoostingRegressor` is the no-new-dependency default.
- ❌ Don't impute the `NaN` out of lag features with a series mean — that
  itself leaks; `HistGradientBoostingRegressor` handles `NaN` natively.
- ❌ Don't edit the merged migration `43e35957a248` — add new forward-only
  migrations.
- ❌ Don't persist `"model_exogenous"` before the CHECK-widening migration
  ships in the same PR.
- ❌ Don't let the agent persist a scenario without the HITL gate — `propose_
  scenario` is read-only; `save_scenario` is mutating and MUST be in
  `agent_require_approval` and gated exactly like `tool_create_alias`.
- ❌ Don't fold the provenance/audit fields into the `assumptions`/`comparison`
  JSONB blobs — they are discrete, queryable columns (DECISIONS LOCKED #13).
- ❌ Don't add a WebSocket — simulation and comparison are request/response.
- ❌ Don't hand-roll a chart — extend `TimeSeriesChart` / add a multi-series
  variant.
- ❌ Don't claim the UI works on a green type-check — dogfood it in a browser.
- ❌ Don't invent a `scenarios` commit scope.

## Vision Tensions — flag these in the PR

1. **Exogenous ML vs "not a generic ML platform" (`product-vision.md`).** The
   Full Version adds a feature-driven ML model. This is *aligned* — it stays
   retail-demand-specific (one model class, retail features, no
   classification/NLP/vision) and single-host (`HistGradientBoostingRegressor`
   ships with `scikit-learn`, already a dependency; nothing managed-cloud).
   Note this reasoning explicitly in the PR.
2. **LightGBM is a deliberate non-goal of this PRP.** `forecast_enable_lightgbm`
   and `LightGBMModelConfig` exist but `model_factory` raises
   `NotImplementedError` and LightGBM is not in `pyproject.toml`. Adding it is a
   separate change — and adding any new dependency is a **stop-and-ask** gate
   (`AGENTS.md` § Safety: "Bumping … major versions"; a new core dependency
   warrants the same pause). If a reviewer wants LightGBM, that is its own
   issue + PR.
3. **Over-trust of revenue claims (the brief's "Risks").** A model-driven number
   reads as more authoritative than a heuristic one. Mitigation: every
   `ScenarioComparison` still declares its `method` and carries a
   method-appropriate `disclaimer` — `MODEL_EXOGENOUS_DISCLAIMER` states the
   result is an estimate under uncertainty, not a guarantee (NIST AI RMF
   transparency control).
4. **Agent mutation-surface widening (`AGENTS.md` § Safety).** Phase D's
   `save_scenario` tool lets the agent write a `scenario_plan` row — a new
   mutation. `AGENTS.md` § Safety lists "widening an agent's mutation surface
   without adding the tool name to `agent_require_approval`" as a stop-and-ask
   gate. This PRP is that approval: the maintainer resolved OQ4 to allow the
   persist tool, and the design correctly (a) adds `save_scenario` to
   `agent_require_approval` so every agent save pauses for explicit human
   approval, and (b) records a full provenance/audit trail on the persisted
   row. The PR description MUST call this widening out explicitly so a reviewer
   sees the gate was satisfied deliberately, not by omission.

## Open Questions — ALL RESOLVED

The maintainer resolved every Open Question during planning. They are recorded
here as DECISION LOCKED entries (and cross-referenced into the DECISIONS LOCKED
section above) — there is nothing left to confirm before coding.

- **DECISION LOCKED — Regression feature set composition.** Exogenous-feature
  lag offsets are PINNED to `EXOGENOUS_LAGS = (1, 7, 14, 28)` days; the
  exogenous columns are `price_*`, `promo_*`, `is_holiday`, and lifecycle. Both
  the historical feature matrix (Task B4) and the future feature frame
  (`feature_frame.py`) use this exact set, so the trained bundle's
  `feature_columns` matches column-for-column. See DECISIONS LOCKED #10.
- **DECISION LOCKED — `history_tail` length.** PINNED to
  `HISTORY_TAIL_DAYS = 90` days — the last 90 observed target values ending at
  the forecast origin, comfortably exceeding the largest lag offset (28). See
  DECISIONS LOCKED #11.
- **DECISION LOCKED — Multi-scenario comparison cap.** PINNED to
  `MAX_COMPARE_SCENARIOS = 5`. `POST /scenarios/compare` accepts 2–5
  `scenario_id`s, enforced via `Field(..., min_length=2, max_length=5)`. See
  DECISIONS LOCKED #12.
- **DECISION LOCKED (OQ4) — Agent persist tool.** The agent gets BOTH a
  read-only `propose_scenario` tool AND a mutating `save_scenario` tool. The
  `save_scenario` tool persists a `scenario_plan` row only after the human
  approves via the existing HITL gate — it is added to `agent_require_approval`
  and gated exactly like `tool_create_alias`. The persisted row carries
  author/source provenance (`source`, `agent_session_id`) and an approval
  audit trail (`approved_by`, `approved_at`, `approval_decision`); Phase D
  ships an Alembic migration adding those columns. See DECISIONS LOCKED #13.

## Confidence Score

**7 / 10** for one-pass implementation success.

Rationale: the PRP is grounded in a fully-read MVP and verified repo facts (the
Alembic head, the un-implemented `lightgbm` factory branch, the missing LightGBM
dependency, the `BaseForecaster` interface, the agent HITL pattern). The two
highest-risk pieces are de-risked by locked decisions: (a) the future-feature-
frame leakage surface is bounded to "long-lag + calendar + exogenous" so the
proof is a direct assertion and no recursion is needed; (b) exogenous-regressor
support uses `HistGradientBoostingRegressor` — already a dependency — so there
is no `pyproject.toml` change and no stop-and-ask gate on the critical path.
Phase C and D are near-mechanical (CRUD + a chart variant + two agent tools that
mirror `tool_create_alias`). The score is 7 rather than 9 because the Full
Version is genuinely large — four phases, three migrations, a new model class, a
new leakage spec, a frontend comparison view, and an HITL-gated agent persist
tool — and the regression *training* path (Task B4) requires building a
historical feature matrix that the future frame must exactly mirror; a
column-order or lag-offset mismatch between the two is the most likely one-pass
failure. That risk is now substantially reduced because the maintainer pinned
the three modelling defaults — the exogenous lag offsets `(1, 7, 14, 28)`, the
90-day `history_tail`, and the 5-scenario comparison cap — so `feature_frame.py`
and the Task B4 training path build against the same fixed constants rather than
an implementer's guess; the residual risk is mechanical column-order discipline,
mitigated by persisting `feature_columns` in the bundle metadata and asserting
it on both sides. The PRP explicitly recommends shipping Phase A + B first and
deferring C + D if scope pressure appears — splitting reduces per-PR risk
substantially.
