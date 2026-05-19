name: "PRP-25 — ForecastOps Control Center (Full Version)"
description: |
  Context-rich PRP that takes the ForecastOps Control Center from its PRP-24 MVP
  to the "Full Version" of docs/optional-features/02-forecastops-control-center.md:
  model-health + performance-drift indicators, an exportable incident report, and
  an operator action layer (bulk retrain + promote-to-alias). Phased so each phase
  is independently shippable and one-pass implementable.

## Purpose

PRP-24 shipped the Control Center MVP — a read-only `app/features/ops/` slice
(`GET /ops/summary`, `GET /ops/retraining-candidates`) and a `/ops` page. This PRP
delivers the remaining "Full Version" capabilities from the feature brief:

- **Phase A — Model Health & Drift**: a new `GET /ops/model-health` endpoint that
  classifies forecast-error *performance drift* per `(store, product)` from run
  history, plus a Model Health section on `/ops`.
- **Phase B — Incident Report Export**: client-side CSV + Markdown export of the
  operational snapshot.
- **Phase C — Action Layer**: operator bulk-retrain (multi-select the retraining
  queue → fan out to `POST /jobs`) and promote-to-alias (`POST /registry/aliases`),
  both behind a confirmation dialog.

---

## DEPENDS ON — read before starting

This PRP **builds directly on PRP-24** (`PRPs/PRP-24-forecastops-control-center.md`,
issue #217, PR #218). It modifies files PRP-24 created. **PR #218 is merged to
`dev`** (dev tip `aac7735 Merge pull request #218`), so the dependency gate is
satisfied — cut this PRP's branch from `dev`. Sanity-check before starting: if
`app/features/ops/service.py` does not already define `OpsService`,
`extract_wape`, and `score_retraining_candidate`, stop — the dependency is missing.

---

## Goal

Ship the Full Version of the Control Center as three independently-validatable
phases on top of the PRP-24 slice:

- **Backend** — one new read-only endpoint (`GET /ops/model-health`). The `ops`
  slice stays read-only: **no new table, no migration, no new mutating endpoint.**
- **Frontend** — a Model Health section, an incident-report export control, and an
  action layer on the Retraining Queue, all on the existing `/ops` page.

End state: `docker compose up` → seed → open `/ops` → operator sees drift signals,
can export an incident report, and can trigger retraining / promote a model —
without leaving the page.

## Why

- **User value** — the MVP shows *what* needs attention; the Full Version lets the
  operator *understand why* (drift), *communicate it* (export), and *act on it*
  (retrain / promote) in one place. This is the "operator workflow" the feature
  brief calls for (`docs/optional-features/02-forecastops-control-center.md`).
- **Demo value** — a closed-loop ForecastOps story (observe → diagnose → act)
  instead of a read-only dashboard.
- **Integration** — Phase A extends the `ops` slice's existing aggregation
  pattern; Phases B & C are frontend layers over **already-shipped endpoints**
  (`POST /jobs`, `POST /registry/aliases`) — no new backend mutation surface.

## What

### User-visible behavior

On the existing `/ops` page, the Full Version adds:

1. **Model Health section** (Phase A) — a table of `(store, product)` grains, each
   showing its forecast-error (WAPE) history, a **drift badge**
   (`improving` / `stable` / `degrading` / `unknown`), and the WAPE delta. Backed
   by `GET /ops/model-health`.
2. **Export control** (Phase B) — an "Export report" button in the page header
   offering **CSV** (attention items) and **Markdown** (full incident report)
   downloads, generated entirely client-side.
3. **Action layer** (Phase C) — the Retraining Queue gains row checkboxes and a
   **"Retrain selected (N)"** button; each Model Health / candidate row gains a
   **"Promote to alias"** action. Both open a confirmation dialog, then call the
   existing job / alias endpoints, reporting per-item success/failure via toasts.

### Technical requirements

- Phase A: extend `app/features/ops/{schemas,service,routes,__init__}.py` and the
  slice's tests. Server-side SQL, `mypy --strict` + `pyright --strict` clean,
  RFC 7807 errors, Pydantic v2 response models (`from_attributes=True`, no
  `strict=True`).
- Phases B & C: **frontend only** — new pure util modules (+ vitest), new TanStack
  Query hooks reusing existing ones, page wiring. No backend changes.
- No new external dependency, no new table, no Alembic migration.

### Success Criteria

- [ ] `GET /ops/model-health?limit=` → 200 with `entries` (each carrying
      `drift_direction`, `latest_wape`, `wape_delta`, `wape_history`), sorted with
      `degrading` grains first; `422` when `limit` is outside `[1, 100]`.
- [ ] `GET /ops/model-health` → 200 (never 500) on an empty database.
- [ ] `classify_drift` is a pure, unit-tested function that never raises on
      missing / sparse WAPE history.
- [ ] `/ops` renders a Model Health section with drift badges and a delta.
- [ ] An "Export report" control downloads a valid CSV and a Markdown report
      built entirely client-side from already-loaded data.
- [ ] The Retraining Queue supports multi-select; "Retrain selected" opens a
      confirm dialog and creates one `train` job per selected grain via
      `POST /jobs`, reporting per-item outcome.
- [ ] A "Promote to alias" action creates/updates an alias via
      `POST /registry/aliases` behind a confirm dialog.
- [ ] The `ops` backend slice remains read-only — no new `models.py`, no
      migration, no new mutating endpoint.
- [ ] All gates pass: `ruff`, `mypy --strict`, `pyright --strict`, `pytest`
      (unit + integration), frontend `tsc` + `lint` + `test`.

---

## All Needed Context

### DECISIONS LOCKED (resolved during planning — do NOT re-litigate)

1. **The `ops` backend stays read-only.** Phase C's "action layer" is a
   *frontend* feature: the `/ops` page calls the **existing, already-sanctioned**
   `POST /jobs` and `POST /registry/aliases` endpoints. No `POST /ops/*` mutating
   endpoint is added; the slice keeps no `models.py` and ships no migration. This
   keeps the PRP-24 "read-only slice" invariant intact. The mild tension — the
   `/ops` *page* becomes an action launcher — is **accepted** (the Forecast page
   already triggers train jobs the same way) and **MUST be noted in the PR
   description** per `.claude/rules/product-vision.md`.

2. **Drift = performance drift, not data drift.** Phase A classifies the **trend
   of forecast error (WAPE) across a grain's successful-run history** — a
   performance-based signal computable read-only from `model_run.metrics`. True
   *data drift* (input-feature distribution shift, PSI/KL tests) is **OUT OF
   SCOPE**: featuresets are computed in-memory and never persisted, so there are
   no feature snapshots to compare. Do NOT add drift infrastructure.

3. **WebSocket live job updates — DECLINED, do NOT build.** The feature brief's
   Full Version lists "WebSocket updates for running jobs". This conflicts with
   the `.claude/rules/product-vision.md` guardrail *"Not a real-time streaming
   system … the agent WebSocket is for response streaming only."* PRP-24 already
   polls `GET /ops/summary` every 15 s and `use-jobs.ts` polls every 5 s — live
   job state is already covered. Keeping polling is the deliberate decision; a WS
   would be a new streaming surface for no real gain. If a WS is ever wanted it is
   a **separate PRP** mirroring the `demo/stream` pattern — not this one.

4. **Retraining scoring is unchanged.** PRP-24's `score_retraining_candidate`
   (60% staleness / 40% WAPE) is locked. Phase A adds drift as a *separate*
   `/ops/model-health` signal; it does NOT fold drift into the retraining score.

5. **No new dependencies.** Recharts, shadcn `Checkbox`, `AlertDialog`, and
   `sonner` are already installed (`frontend/package.json`,
   `frontend/src/components/ui/{chart,checkbox,alert-dialog,sonner}.tsx`). Reuse
   them; do not `pnpm add` anything.

### Documentation & References

```yaml
# MUST READ — the PRP-24 slice this PRP extends (already on dev after #218)
- file: PRPs/PRP-24-forecastops-control-center.md
  why: The MVP PRP. Its "Known Gotchas" section applies verbatim here — status
       columns are String (compare `Enum.X.value`); `datetime.now(UTC)` (ruff DTZ);
       DISTINCT ON order_by must lead with the distinct cols; AsyncSession forbids
       lazy-loading; response models use ConfigDict(from_attributes=True), NEVER
       strict=True; do NOT add a `# noqa: BLE001` (BLE is not in the ruff select).
- file: app/features/ops/service.py
  why: EXTEND THIS. Already defines `extract_wape(metrics)` — REUSE it, do not
       redefine. `OpsService.get_retraining_candidates` is the near-exact mirror
       for the new `get_model_health` (DISTINCT ON vs. full-history difference
       noted in Gotchas). Module-scope pure helpers (`score_retraining_candidate`)
       are the pattern for the new `classify_drift`.
- file: app/features/ops/schemas.py
  why: EXTEND THIS. `RetrainingCandidate` / `RetrainingCandidatesResponse` are the
       exact shape to mirror for `ModelHealthEntry` / `ModelHealthResponse`.
- file: app/features/ops/routes.py
  why: EXTEND THIS. `get_retraining_candidates` is the exact mirror for the new
       `get_model_health` route — same `Query(default=20, ge=1, le=100)` bound.
- file: app/features/ops/__init__.py
  why: EXTEND `__all__` with the new response model.
- file: app/features/ops/tests/conftest.py
  why: EXTEND. `sample_runs` already creates two success runs for grain
       (9001, 8001) — that grain already has a 2-point WAPE history (31.0 → 12.0,
       i.e. `improving`). Add a third run if a `degrading` case is wanted.
- file: app/features/ops/tests/{test_service,test_schemas,test_routes_integration}.py
  why: EXTEND. `test_service.py` is the pattern for pure-function tests of
       `classify_drift`; `test_routes_integration.py` for the new endpoint.
- file: app/features/registry/models.py
  why: `ModelRun.metrics` (JSONB, nullable), `status`, `store_id`, `product_id`,
       `created_at`, `run_id`. `RunStatus.SUCCESS`.

# MUST READ — endpoints Phase C reuses (no backend changes — frontend calls these)
- file: app/features/jobs/routes.py
  why: `POST /jobs` (202) creates+executes a job. Body is `JobCreate`
       {job_type, params}. The train-job `params` contract is documented in the
       route docstring — model_type, store_id, product_id, start_date, end_date.
- file: app/features/jobs/schemas.py
  why: `JobCreate` = {job_type: JobType, params: dict}. `JobResponse` shape.
- file: app/features/jobs/service.py
  why: VERIFY the exact train-job `params` keys `JobService` consumes BEFORE
       writing `buildRetrainJob` — this is Phase C's main risk.
- file: app/features/forecasting/schemas.py
  why: `ModelConfig` (discriminated union on `model_type`) — the shape of
       `model_run.model_config`; tells you what to flatten into the retrain params.
- file: app/features/registry/routes.py
  why: `POST /registry/aliases` (201) body `AliasCreate` {alias_name, run_id,
       description?}; aliases only point at SUCCESS runs (400 otherwise).
- file: app/features/registry/schemas.py
  why: `AliasCreate`, `AliasResponse`, `RunResponse` field names.

# MUST READ — frontend patterns
- file: frontend/src/pages/ops.tsx
  why: MODIFY THIS in every phase. PRP-24's page — header, error/loading/empty
       early returns, Card/Table sections, `@/` imports.
- file: frontend/src/hooks/use-ops.ts
  why: EXTEND. `useOpsSummary` / `useRetrainingCandidates` are the exact pattern
       for `useModelHealth`.
- file: frontend/src/hooks/use-jobs.ts
  why: `useCreateJob()` — REUSE for Phase C bulk retrain. Do not write a new
       job-creation hook.
- file: frontend/src/hooks/use-runs.ts
  why: `useCreateAlias()` — REUSE for Phase C promote. `useRun(runId)` fetches a
       run's detail (needed to clone model_config for a retrain).
- file: frontend/src/lib/csv-export.ts
  why: `toCsv` / `downloadCsv` / `CsvColumn<T>` — REUSE for Phase B CSV export.
       Already CSV-injection-safe.
- file: frontend/src/lib/ops-utils.ts + ops-utils.test.ts
  why: PRP-24's pure util module + colocated vitest test — the exact pattern for
       the new `incident-report.ts` and `ops-actions.ts` modules.
- file: frontend/src/pages/visualize/demand.tsx
  why: A dense data page that already does CSV export (`downloadCsv`/`toCsv`) and
       row interaction — mirror its export-button placement and table patterns.
- file: frontend/src/components/ui/checkbox.tsx
  why: shadcn Checkbox — Phase C row selection. Already installed.
- file: frontend/src/components/ui/alert-dialog.tsx
  why: shadcn AlertDialog — Phase C confirm dialogs. Already installed.
- file: frontend/src/components/ui/sonner.tsx
  why: `sonner` toast. VERIFY a `<Toaster/>` is mounted (app-shell / main) before
       calling `toast()`; if not, mount it once in the app shell.
- file: frontend/src/components/ui/chart.tsx
  why: shadcn Recharts wrapper — optional WAPE sparkline in Model Health.
- file: frontend/src/components/charts/time-series-chart.tsx
  why: existing Recharts usage pattern if a sparkline is added.
- file: frontend/src/types/api.ts
  why: EXTEND. The `Ops*` interfaces PRP-24 added (`OpsSummaryResponse`,
       `RetrainingCandidate`, …) are the mirror for `ModelHealth*`.

# External docs
- url: https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#order-by
  why: ordering the full run history per grain (NOT DISTINCT ON — see Gotchas).
- url: https://tanstack.com/query/latest/docs/framework/react/guides/mutations
  why: reusing `useMutation` (useCreateJob/useCreateAlias) for the action layer.
- url: https://ui.shadcn.com/docs/components/alert-dialog
  why: AlertDialog composition for the confirm gates.
- url: https://recharts.org/en-US/api/LineChart
  why: minimal WAPE sparkline (optional Phase A polish).
- url: https://www.mlflow.org/docs/latest/ml/model-registry/
  why: alias-promotion governance — the conceptual basis for Phase C promote.

- docfile: docs/optional-features/02-forecastops-control-center.md
  why: the feature brief — § "Full Version" (lines 76-83) is exactly this PRP's
       scope, minus retraining scoring (done in PRP-24) and WebSocket (declined).
```

### Current Codebase tree (post-PRP-24, relevant subset)

```bash
app/features/ops/                  # read-only slice from PRP-24
├── __init__.py  schemas.py  service.py  routes.py
└── tests/ (__init__.py conftest.py test_schemas.py test_service.py
            test_routes_integration.py)
frontend/src/
├── pages/ops.tsx                  # PRP-24 Control Center page (5 sections)
├── hooks/use-ops.ts               # useOpsSummary, useRetrainingCandidates
├── lib/ops-utils.ts (+ .test.ts)  # pure helpers
├── types/api.ts                   # Ops* response interfaces
├── hooks/use-jobs.ts              # useCreateJob (REUSE)
├── hooks/use-runs.ts              # useCreateAlias, useRun (REUSE)
└── lib/csv-export.ts              # toCsv, downloadCsv (REUSE)
```

### Desired Codebase tree (files to add / touch)

```bash
# ── Phase A — Model Health & Drift ──
app/features/ops/schemas.py        # MODIFY — add WapePoint, ModelHealthEntry,
                                   #          ModelHealthResponse
app/features/ops/service.py        # MODIFY — add classify_drift() + get_model_health()
app/features/ops/routes.py         # MODIFY — add GET /ops/model-health
app/features/ops/__init__.py       # MODIFY — export ModelHealthResponse
app/features/ops/tests/test_schemas.py            # MODIFY — new models
app/features/ops/tests/test_service.py            # MODIFY — classify_drift
app/features/ops/tests/conftest.py                # MODIFY — degrading-grain fixture
app/features/ops/tests/test_routes_integration.py # MODIFY — /ops/model-health
frontend/src/types/api.ts          # MODIFY — ModelHealth* interfaces
frontend/src/hooks/use-ops.ts      # MODIFY — useModelHealth
frontend/src/pages/ops.tsx         # MODIFY — Model Health section

# ── Phase B — Incident Report Export ──
frontend/src/lib/incident-report.ts        # NEW — pure builders (CSV cols + markdown)
frontend/src/lib/incident-report.test.ts   # NEW — vitest
frontend/src/pages/ops.tsx                 # MODIFY — export control in header

# ── Phase C — Action Layer ──
frontend/src/lib/ops-actions.ts            # NEW — pure buildRetrainJob()
frontend/src/lib/ops-actions.test.ts       # NEW — vitest
frontend/src/pages/ops.tsx                 # MODIFY — selection, dialogs, actions

# NOT created: any app/features/ops/models.py, any Alembic migration,
#              any POST /ops/* endpoint, any WebSocket.
```

### Known Gotchas & Library Quirks

```python
# CRITICAL: ALL PRP-24 gotchas still apply. Re-read PRP-24 § "Known Gotchas".
#   Headlines: compare String status columns against `Enum.X.value`; use
#   `datetime.now(UTC)` (ruff DTZ bans date.today()/naive now()); response models
#   use ConfigDict(from_attributes=True) and NEVER strict=True; never add a
#   `# noqa: BLE001` (BLE is not in the ruff select — it would trip RUF100).
#
# CRITICAL (Phase A): model-health needs the FULL run history per grain, NOT the
#   latest-per-grain. Do NOT use DISTINCT ON here. Query every SUCCESS run, ordered
#   by (store_id, product_id, created_at ASC), and group in Python:
#     select(ModelRun).where(ModelRun.status == RunStatus.SUCCESS.value)
#       .order_by(ModelRun.store_id, ModelRun.product_id, ModelRun.created_at)
#   Then itertools.groupby over (store_id, product_id) — rows are already ordered.
#
# CRITICAL (Phase A): REUSE the existing `extract_wape` from ops/service.py — it
#   already tolerates None / non-numeric / bool. Do NOT redefine it. WAPE history
#   will contain None entries (runs whose metrics lack WAPE); classify_drift MUST
#   tolerate a list with None gaps and never raise.
#
# CRITICAL (Phase C): POST /jobs executes SYNCHRONOUSLY (returns 202 but runs the
#   job inline before responding). Bulk-retrain of N grains = N blocking calls on
#   a single-process backend. Fire them SEQUENTIALLY (await each before the next),
#   show per-item progress, and keep N modest. Do NOT Promise.all() them.
#
# CRITICAL (Phase C): a train job's `params` shape is consumed by JobService —
#   VERIFY the exact keys in app/features/jobs/service.py + forecasting/schemas.py
#   BEFORE writing buildRetrainJob(). `_execute_train` in jobs/service.py reads a
#   FLAT params dict: model_type, store_id, product_id, start_date, end_date, plus
#   model-specific keys `season_length` (seasonal_naive) / `window_size`
#   (moving_average) — there is NO `period` key. Pick those keys explicitly from
#   the source run's `model_config`; do NOT blind-spread `model_config` (it also
#   carries `schema_version` + a duplicate `model_type`).
#
# CRITICAL (Phase C): aliases may only point at SUCCESS runs (registry returns 400
#   otherwise). Only offer "Promote to alias" on rows whose run status is success.
#
# GOTCHA (Phase C): retrain window — clone the source run's `model_type` +
#   `model_config`; set start_date = source run `data_window_start`, end_date =
#   `summary.freshness.latest_sales_date` (the freshest data). If latest_sales_date
#   is null, fall back to the run's own data_window_end and surface a warning.
#
# GOTCHA: `sonner` `toast()` needs a mounted `<Toaster/>`. It is ALREADY mounted —
#   `frontend/src/components/layout/app-shell.tsx` renders `<Toaster/>` from
#   `@/components/ui/sonner`. Task C4 is verification-only; do NOT add a second one.
#
# GOTCHA: commit-format scope allow-list has NO `ops` scope. Use feat(api) for the
#   backend phase, feat(ui) for the frontend phases.
#
# GOTCHA: the /ops page renders inside AppShell — no nav/container/Toaster added by
#   the page; semantic shadcn tokens only, never raw colors.
```

---

## External Research Findings

Verified May 2026. Each finding ends with a **verdict**.

### 1. Performance-drift vs. data-drift triggers (web search, May 2026)

MLOps practice splits retraining triggers into **performance-based** (monitor a
core error metric; retrain when it degrades past a threshold) and **drift-based**
(statistical tests — PSI, KL divergence — on input/target distributions). 2025
reviews report models left unmonitored for 6+ months saw error rates rise ~35%,
and that proactive performance-trigger policies outperform reactive ones.

- **Verdict — Phase A is a performance-drift indicator.** It tracks the WAPE trend
  across a grain's run history and classifies `improving / stable / degrading`.
  This is exactly the recommended performance-based signal and needs **no new
  infrastructure** — it reads `model_run.metrics`. PSI/KL **data drift** is
  correctly out of scope (no persisted feature snapshots; see Decision #2).
- Sources: [What Is Model Drift?](https://www.articsledge.com/post/model-drift),
  [Advanced ML Model Monitoring](https://enhancedmlops.com/advanced-ml-model-monitoring-drift-detection-explainability-and-automated-retraining/),
  [MLOps Model Monitoring](https://durapid.com/blog/mlops-model-monitoring-how-to-track-model-drift-and-performance-in-production/).

### 2. Drift threshold (heuristic)

There is no universal "drift threshold"; teams pick a relative tolerance band.
A ±10% relative change in the error metric is a defensible, deterministic default
for a portfolio system.

- **Verdict — applied.** `classify_drift` uses a ±10% relative band: latest WAPE
  vs. the mean of prior WAPEs. `degrading` if latest is >10% worse, `improving` if
  >10% better, `stable` within the band, `unknown` if fewer than two numeric WAPEs.

### 3. Alias-promotion governance (MLflow)

MLflow models alias promotion (`champion` / production alias) as a deliberate,
human-gated step decoupling deployment from a specific version.

- **Verdict — confirms Phase C.** "Promote to alias" reuses `POST /registry/aliases`
  behind a confirmation `AlertDialog` — the human gate. No new backend gate is
  needed; the registry already restricts aliases to SUCCESS runs.
- Source: [MLflow Model Registry](https://www.mlflow.org/docs/latest/ml/model-registry/).

### 4. WebSocket job updates — assessed and DECLINED

The feature brief lists WS job updates under "Full Version". `product-vision.md`
forbids new streaming surfaces ("Not a real-time streaming system"). PRP-24's
`/ops/summary` 15 s poll + `use-jobs.ts` 5 s poll already deliver live job state.

- **Verdict — do NOT build (Decision #3).** Polling is the deliberate choice.

---

## Implementation Blueprint

### Phase A — data models (`app/features/ops/schemas.py`, additions)

All response models — `ConfigDict(from_attributes=True)`, every field a
`Field(..., description=...)`, counts `ge=0`, **no `strict=True`**.

```python
from typing import Literal
DriftDirection = Literal["improving", "stable", "degrading", "unknown"]

class WapePoint(BaseModel):                      # one run's WAPE observation
    run_id: str
    created_at: datetime
    wape: float | None                           # None when the run lacks WAPE

class ModelHealthEntry(BaseModel):
    store_id: int
    product_id: int
    run_count: int = Field(..., ge=0)
    latest_run_id: str | None
    latest_run_status: str | None
    latest_wape: float | None
    previous_wape: float | None                  # the prior numeric WAPE
    wape_delta: float | None                     # latest - previous (numeric only)
    drift_direction: DriftDirection
    last_trained_at: datetime | None
    staleness_days: int = Field(..., ge=0)
    wape_history: list[WapePoint]                # chronological, may hold gaps

class ModelHealthResponse(BaseModel):
    entries: list[ModelHealthEntry]              # degrading-first sort
    total_evaluated: int = Field(..., ge=0)
    generated_at: datetime
```

### Phase A — pseudocode (`app/features/ops/service.py`, additions)

```python
# ── module-scope pure helper (mirror of score_retraining_candidate) ──
_DRIFT_BAND = 0.10   # ±10% relative WAPE change

def classify_drift(wape_history: list[float | None]) -> tuple[str, float | None]:
    """Classify the WAPE trend. Pure; never raises. Returns (direction, delta).
    direction ∈ improving|stable|degrading|unknown; delta = latest - previous."""
    numeric = [w for w in wape_history if w is not None]
    if len(numeric) < 2:
        return "unknown", None
    latest = numeric[-1]
    prior = numeric[:-1]
    baseline = sum(prior) / len(prior)
    delta = round(latest - prior[-1], 4)
    if baseline <= 0:                            # avoid div-by-zero on a 0 WAPE
        return ("degrading" if latest > 0 else "stable"), delta
    rel = (latest - baseline) / baseline
    if rel > _DRIFT_BAND:
        return "degrading", delta
    if rel < -_DRIFT_BAND:
        return "improving", delta
    return "stable", delta

# ── OpsService.get_model_health ──
async def get_model_health(self, db, limit: int) -> ModelHealthResponse:
    today = datetime.now(UTC).date()
    # FULL history — NOT DISTINCT ON. Ordered so itertools.groupby works.
    runs = (await db.execute(
        select(ModelRun).where(ModelRun.status == RunStatus.SUCCESS.value)
        .order_by(ModelRun.store_id, ModelRun.product_id, ModelRun.created_at)
    )).scalars().all()
    entries = []
    for (store_id, product_id), grain_runs in groupby(runs, key=lambda r: (r.store_id, r.product_id)):
        grain_runs = list(grain_runs)            # already chronological
        history = [WapePoint(run_id=r.run_id, created_at=r.created_at,
                             wape=extract_wape(r.metrics)) for r in grain_runs]
        direction, delta = classify_drift([p.wape for p in history])
        numeric = [p.wape for p in history if p.wape is not None]
        latest_run = grain_runs[-1]
        entries.append(ModelHealthEntry(
            store_id=store_id, product_id=product_id, run_count=len(grain_runs),
            latest_run_id=latest_run.run_id, latest_run_status=latest_run.status,
            latest_wape=(numeric[-1] if numeric else None),
            previous_wape=(numeric[-2] if len(numeric) > 1 else None),
            wape_delta=delta, drift_direction=direction,
            last_trained_at=latest_run.created_at,
            staleness_days=max((today - latest_run.data_window_end).days, 0),
            wape_history=history))
    # degrading first, then by |wape_delta| desc; unknown/stable last
    _rank = {"degrading": 0, "improving": 1, "stable": 2, "unknown": 3}
    entries.sort(key=lambda e: (_rank[e.drift_direction], -abs(e.wape_delta or 0.0)))
    logger.info("ops.model_health_computed", grains=len(entries))
    return ModelHealthResponse(entries=entries[:limit], total_evaluated=len(entries),
                               generated_at=datetime.now(UTC))
```

```python
# ── app/features/ops/routes.py (add; mirror get_retraining_candidates) ──
@router.get("/model-health", response_model=ModelHealthResponse,
            summary="Per-(store,product) forecast-error health and drift")
async def get_model_health(
    limit: int = Query(default=20, ge=1, le=100, description="Max grains to return"),
    db: AsyncSession = Depends(get_db),
) -> ModelHealthResponse:
    return await OpsService().get_model_health(db, limit)
```

### Phase B — pseudocode (`frontend/src/lib/incident-report.ts`, NEW, pure)

```typescript
import type { CsvColumn } from '@/lib/csv-export'
import type { AttentionItem, OpsSummaryResponse, RetrainingCandidate } from '@/types/api'

// CSV column set for the attention-items export (reuse toCsv/downloadCsv).
export const attentionCsvColumns: CsvColumn<AttentionItem>[] = [
  { key: 'item_type', header: 'Type' }, { key: 'entity_id', header: 'Entity' },
  { key: 'label', header: 'Item' }, { key: 'detail', header: 'Detail' },
  { key: 'occurred_at', header: 'When' },
]

// Build a human-readable Markdown incident report from already-loaded page data.
export function buildIncidentMarkdown(
  summary: OpsSummaryResponse, candidates: RetrainingCandidate[],
): string {
  // Sections: # ForecastOps Incident Report (generated_at) ; System Health
  // (api/db + provider lines) ; KPIs (active/failed jobs, success rate, stale
  // aliases) ; Data Freshness ; Needs Attention (a markdown table) ; Top
  // Retraining Candidates (a markdown table). Pure string assembly — no fetch.
  // Return the assembled string.
}
```

### Phase C — pseudocode (`frontend/src/lib/ops-actions.ts`, NEW, pure)

```typescript
import type { JobCreate, ModelRun, RetrainingCandidate } from '@/types/api'

// Build the POST /jobs body that retrains a grain from its latest run.
// VERIFY param keys against app/features/jobs/service.py before finalizing.
export function buildRetrainJob(
  run: ModelRun,                       // GET /registry/runs/{latest_run_id}
  latestSalesDate: string | null,      // summary.freshness.latest_sales_date
): JobCreate {
  return {
    job_type: 'train',
    params: {
      model_type: run.model_type,
      store_id: run.store_id,
      product_id: run.product_id,
      start_date: run.data_window_start,
      end_date: latestSalesDate ?? run.data_window_end,  // freshest data
      // model-specific keys picked explicitly — NOT a blind ...model_config spread:
      ...(run.model_config.season_length != null
        ? { season_length: run.model_config.season_length } : {}),
      ...(run.model_config.window_size != null
        ? { window_size: run.model_config.window_size } : {}),
    },
  }
}
```

Page wiring (`ops.tsx`): Retraining Queue rows get a `Checkbox`; selection is
`useState<Set<string>>`. "Retrain selected (N)" opens an `AlertDialog`; on confirm,
**sequentially** for each selected candidate: `useRun`-fetch its `latest_run_id`,
`buildRetrainJob(...)`, `useCreateJob().mutateAsync(...)`, `toast` the outcome.
"Promote to alias" (on success-status rows only) opens an `AlertDialog` with an
alias-name input, then `useCreateAlias().mutateAsync({alias_name, run_id})`.

### Tasks (in order)

```yaml
# ════════ PHASE A — Model Health & Drift (backend + page section) ════════
Task A1 — MODIFY app/features/ops/schemas.py:
  - ADD DriftDirection Literal, WapePoint, ModelHealthEntry, ModelHealthResponse
  - VALIDATE: uv run python -c "from app.features.ops.schemas import ModelHealthResponse; print('ok')"

Task A2 — MODIFY app/features/ops/service.py:
  - ADD module-scope `classify_drift` (pseudocode above); import `groupby` from itertools
  - ADD `OpsService.get_model_health` (full-history query — NOT DISTINCT ON; reuse extract_wape)
  - VALIDATE: uv run mypy app/features/ops/ && uv run pyright app/features/ops/

Task A3 — MODIFY app/features/ops/routes.py + __init__.py:
  - ADD GET /ops/model-health (mirror get_retraining_candidates); export ModelHealthResponse
  - VALIDATE: uv run python -c "from app.main import app; assert '/ops/model-health' in {r.path for r in app.routes}; print('wired')"

Task A4 — MODIFY ops tests (test_schemas.py, test_service.py, conftest.py):
  - test_service.py: classify_drift cases — <2 numeric → unknown; degrading;
    improving; stable within band; None-gap tolerance; zero-baseline guard
  - test_schemas.py: construct ModelHealthEntry/Response; ge=0 rejects negatives
  - conftest.py: extend sample_runs (or a new fixture) so one grain has a
    degrading 3-point WAPE history
  - VALIDATE: uv run pytest -v -m "not integration" app/features/ops/tests/test_service.py app/features/ops/tests/test_schemas.py

Task A5 — MODIFY app/features/ops/tests/test_routes_integration.py:
  - /ops/model-health 200 happy (seeded), entries carry drift_direction;
    200 resilient (empty); ?limit=0 → 422; ?limit=200 → 422; degrading-first sort
  - VALIDATE: docker compose up -d && uv run pytest -v -m integration app/features/ops/

Task A6 — MODIFY frontend/src/types/api.ts:
  - ADD DriftDirection, WapePoint, ModelHealthEntry, ModelHealthResponse (dates as string)
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task A7 — MODIFY frontend/src/hooks/use-ops.ts:
  - ADD useModelHealth(limit=20, enabled=true) — queryKey ['ops','model-health',limit];
    no refetchInterval (slow-moving). MIRROR useRetrainingCandidates.
  - VALIDATE: cd frontend && pnpm tsc --noEmit

Task A8 — MODIFY frontend/src/pages/ops.tsx:
  - ADD a "Model Health" Card+Table section: grain, drift StatusBadge
    (degrading→error, improving→success, stable→info, unknown→default),
    latest WAPE, wape_delta, run_count. Optional: a Recharts sparkline of
    wape_history. GOTCHA: renders inside AppShell — no raw colors.
  - VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

# ════════ PHASE B — Incident Report Export (frontend only) ════════
Task B1 — CREATE frontend/src/lib/incident-report.ts + incident-report.test.ts:
  - attentionCsvColumns + buildIncidentMarkdown (pure; pseudocode above)
  - MIRROR: csv-export.ts + ops-utils.test.ts
  - VALIDATE: cd frontend && pnpm test --run src/lib/incident-report.test.ts

Task B2 — MODIFY frontend/src/pages/ops.tsx:
  - ADD an "Export report" control in the page header — a dropdown (or two
    buttons): "CSV (attention items)" → downloadCsv(toCsv(...)); "Markdown
    report" → download buildIncidentMarkdown(...) as ops-incident-report.md
  - MIRROR: demand.tsx export button
  - VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

# ════════ PHASE C — Action Layer (frontend only) ════════
Task C0 — RESEARCH (no code): read app/features/jobs/service.py +
  app/features/forecasting/schemas.py — confirm the exact train-job `params`
  keys. Adjust buildRetrainJob accordingly. This de-risks the whole phase.

Task C1 — CREATE frontend/src/lib/ops-actions.ts + ops-actions.test.ts:
  - buildRetrainJob(run, latestSalesDate) (pseudocode above)
  - VALIDATE: cd frontend && pnpm test --run src/lib/ops-actions.test.ts

Task C2 — MODIFY frontend/src/pages/ops.tsx — bulk retrain:
  - Retraining Queue rows get a shadcn Checkbox; selection via useState<Set>
  - "Retrain selected (N)" → AlertDialog confirm → SEQUENTIALLY per candidate:
    fetch run (useRun / api), buildRetrainJob, useCreateJob().mutateAsync, toast
  - GOTCHA: sequential awaits, not Promise.all (POST /jobs runs synchronously)
  - VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task C3 — MODIFY frontend/src/pages/ops.tsx — promote to alias:
  - "Promote to alias" action on success-status rows → AlertDialog with an
    alias-name input → useCreateAlias().mutateAsync({alias_name, run_id}) → toast
  - GOTCHA: only success runs are promotable (registry returns 400 otherwise)
  - VALIDATE: cd frontend && pnpm tsc --noEmit && pnpm lint

Task C4 — VERIFY the <Toaster/> in frontend/src/components/layout/app-shell.tsx
  is mounted (it already is). Verification-only — do NOT add a second Toaster.
  - VALIDATE: cd frontend && pnpm tsc --noEmit

# ════════ FINAL ════════
Task D1 — FULL validation sweep (all gates — see Validation Loop).
Task D2 — Browser dogfood per .claude/rules/ui-design.md (webapp-testing /
  agent-browser): Model Health renders with drift badges; export downloads a
  valid CSV + Markdown; bulk-retrain creates jobs (verify on /explorer/jobs);
  promote creates an alias (verify on /ops summary aliases).
```

### Integration Points

```yaml
DATABASE:
  - migration: NONE — Phase A is a read-only query; Phases B/C touch no schema.
  - tables read (existing): model_run (Phase A).

ROUTES (backend):
  - add to app/features/ops/routes.py: GET /ops/model-health
  - already wired: app/main.py includes ops_router (PRP-24) — no main.py change.

ROUTES (frontend):
  - none — no new page, no new route; all work lands on the existing /ops page.

HOOKS:
  - new: useModelHealth in frontend/src/hooks/use-ops.ts
  - reuse: useCreateJob (use-jobs.ts), useCreateAlias + useRun (use-runs.ts)

CONFIG: none — no new settings, no new env var, no new dependency.
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . --fix && uv run ruff format --check .
cd frontend && pnpm lint
# Trap: date.today() → ruff DTZ; a stray `# noqa: BLE001` → RUF100.
```

### Level 2: Type Checks

```bash
uv run mypy app/ && uv run pyright app/      # both --strict
cd frontend && pnpm tsc --noEmit
```

### Level 3: Unit Tests

```bash
uv run pytest -v -m "not integration" app/features/ops/
cd frontend && pnpm test --run src/lib/incident-report.test.ts src/lib/ops-actions.test.ts
```

Pure-function cases that MUST exist (`test_service.py`):
```python
def test_classify_drift_unknown_when_under_two_numeric():
    assert classify_drift([None, 10.0]) == ("unknown", None)

def test_classify_drift_degrading():
    d, delta = classify_drift([10.0, 10.0, 20.0])   # latest 20 vs baseline 10
    assert d == "degrading"

def test_classify_drift_improving():
    d, _ = classify_drift([20.0, 20.0, 10.0])
    assert d == "improving"

def test_classify_drift_stable_within_band():
    d, _ = classify_drift([10.0, 10.5])             # +5% < 10% band
    assert d == "stable"

def test_classify_drift_tolerates_none_gaps():
    assert classify_drift([None, 10.0, None, 12.0])[0] in {"stable", "degrading"}
```

### Level 4: Integration Tests

```bash
docker compose up -d && uv run alembic upgrade head
uv run pytest -v -m integration app/features/ops/
```

`/ops/model-health` → 200; entries cover seeded grains; `drift_direction` present;
empty DB → 200 (never 500); `?limit=0` and `?limit=200` → 422; degrading-first sort.

### Level 5: Manual Validation

```bash
uv run uvicorn app.main:app --reload --port 8123 &
curl -s "http://localhost:8123/ops/model-health?limit=5" | head -c 400
curl -s -o /dev/null -w '%{http_code}\n' "http://localhost:8123/ops/model-health?limit=0"  # 422
# Frontend: seed (make demo), open http://localhost:5173/ops via the
# webapp-testing skill / agent-browser — verify the Model Health section,
# CSV + Markdown export downloads, bulk-retrain → new jobs on /explorer/jobs,
# promote → alias on the summary. Type-check passing ≠ UI works.
```

---

## Final Validation Checklist

- [ ] `uv run ruff check . && uv run ruff format --check .` — clean
- [ ] `uv run mypy app/ && uv run pyright app/` — clean (`--strict`)
- [ ] `uv run pytest -v -m "not integration"` — green
- [ ] `docker compose up -d && uv run pytest -v -m integration` — green
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` — green
- [ ] `GET /ops/model-health` behaves per Success Criteria (sort, 422, empty-DB)
- [ ] `/ops` shows Model Health with drift badges; export downloads CSV + Markdown;
      bulk-retrain creates jobs; promote creates an alias — dogfooded in a browser
- [ ] `ops` backend slice still read-only — no `models.py`, no migration, no
      `POST /ops/*`
- [ ] No new dependency
- [ ] PR description flags: the `/ops` page is now an action launcher (calls
      existing `POST /jobs` / `POST /registry/aliases`); WebSocket job updates
      were assessed and deliberately declined (Decision #3)
- [ ] Commits use `feat(api)` (Phase A) / `feat(ui)` (Phases B, C) and reference
      an open issue

---

## Anti-Patterns to Avoid

- ❌ Don't add a `POST /ops/*` mutating endpoint — Phase C is frontend-only over
  existing endpoints; the `ops` slice stays read-only.
- ❌ Don't build the WebSocket — it was assessed and declined (Decision #3).
- ❌ Don't add data-drift / PSI infrastructure — performance drift only (Decision #2).
- ❌ Don't use DISTINCT ON for model-health — it needs the full per-grain history.
- ❌ Don't redefine `extract_wape` — reuse the one in `ops/service.py`.
- ❌ Don't `Promise.all()` the bulk retrains — `POST /jobs` runs synchronously;
  go sequential.
- ❌ Don't change `score_retraining_candidate` — PRP-24's scoring is locked.
- ❌ Don't `pnpm add` anything — Recharts/Checkbox/AlertDialog/sonner are installed.
- ❌ Don't add `ConfigDict(strict=True)` to the new response models.
- ❌ Don't claim the UI works on a green type-check — dogfood it in a browser.

## Workflow Notes

- Open a GitHub issue first; branch `feat/ops-control-center-full` off `dev`
  (`.claude/rules/branch-naming.md`) — **only after PR #218 (PRP-24) is merged**.
- The phases are independently shippable. Prefer **one PR per phase** (smaller
  reviews) or a single phased PR — either way: `feat(api)` for Phase A,
  `feat(ui)` for Phases B and C.
- The PR description MUST state (a) the `/ops` page becomes an action launcher
  via existing endpoints, and (b) WebSocket job updates were deliberately
  declined — per `.claude/rules/product-vision.md` § "When Ideas Don't Align".

## Confidence Score

**8 / 10** for one-pass implementation success.

Rationale: Phase A is a near-exact mirror of PRP-24's verified `get_retraining_candidates`
pattern (the one structural difference — full history vs. DISTINCT ON — is called
out as a CRITICAL gotcha). Phase B is pure frontend over the existing, CSV-safe
`csv-export.ts`. Both score ~9/10. Phase C is the residual risk: it depends on the
exact `train`-job `params` contract, mitigated by the mandatory Task C0 research
step (read `jobs/service.py` + `forecasting/schemas.py` first) and by reusing the
existing `useCreateJob` / `useCreateAlias` hooks rather than inventing mutation
code. The biggest scope risks of the feature brief's "Full Version" — a WebSocket
streaming surface and turning `ops` into a backend mutation slice — are removed by
Decisions #1 and #3, keeping every phase aligned with the single-host, non-streaming
product vision.
