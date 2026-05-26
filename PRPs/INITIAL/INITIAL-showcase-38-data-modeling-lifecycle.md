# INITIAL-showcase-38-data-modeling-lifecycle.md — Showcase MVP Foundation: Data + V1/V2 Modeling

> **Status:** Planning. First sliced INITIAL of the four-PRP `/showcase`
> upgrade epic.
> **Parent:** `PRPs/INITIAL/INITIAL-showcase-rich-demo-control-center.md`
> **Sequence index:** `PRPs/INITIAL/INITIAL-showcase-rich-demo-index.md`
> **Prerequisites:** none (foundation slice — every later PRP depends on this).
> **Unlocks:** PRP-39 (multi-run decision surfaces depend on V2 runs existing).

## FEATURE:

Lay the **MVP foundation** for the rich showcase: extend `/showcase` from a
flat 11-step baseline-only timeline into a **phase-grouped, scenario-aware
demo** that creates richer data and trains both V1 baselines and ONE V2
feature-aware model — enough so the PRP-37 Feature Frame panel and PRP-36
horizon-bucket card light up end-to-end after a single pipeline run.

This is intentionally **NOT oversized**. It ships a foundation that is
**shippable on its own**:

1. **Phase grouping** — replace the flat 11-step list with a phase accordion
   (shadcn `Accordion`); the currently-running phase auto-expands.
2. **Scenario picker** — shadcn `Select` with three headline scenarios:
   `demo_minimal` (default, ~60 s), `showcase-rich` (new, ~3 min), `sparse`
   (edge-case).
3. **`showcase-rich` preset** — a new `ScenarioPreset.SHOWCASE_RICH` (5 stores
   × 15 products × 180 days), wired through `SeederConfig.from_scenario`.
4. **Phase-2 enrichment + historical backfill** — new `/seeder/*` endpoints
   wrapping `scripts/seed_phase2_only.py` + `scripts/seed_historical_activity.py`
   logic, called as new pipeline steps in the `data` phase.
5. **V1 baseline + ONE V2 prophet_like run** — extend the modeling phase with a
   `v2_train` step that trains ONE `prophet_like` model with
   `feature_frame_version=2` and registers it with the full
   `artifacts/models/...` artifact_uri so the Feature Frame panel works.
6. **Feature-aware backtest with bucket visibility** — the `backtest` step
   posts with `include_baselines=true` and `feature_frame_version=2` so
   PRP-36 `bucketed_aggregated_metrics` populate; the step card shows a
   per-bucket summary inline.
7. **Per-step Inspect links** — each terminal-status card with a populated
   `data` payload (`train`, `register`, `backtest`) gains a small "Inspect"
   button deep-linking to the relevant dashboard page (`/visualize/forecast`,
   `/explorer/runs/{id}`, `/visualize/backtest`).

### What PRP-38 is NOT

These belong to later PRPs and **MUST stay out of PRP-38 scope**:

- Champion-compat compare, stale-alias trigger, safer-Promote dialog walk
  through, batch preset/matrix — **PRP-39**.
- Scenario simulate/save/compare, RAG indexing, embedding-provider probe —
  **PRP-40**.
- Agent HITL flow, ops snapshot, KPI strip, Inspect-Artifacts post-run panel,
  localStorage run history, Stop button, walkthrough docs — **PRP-41**.

PRP-38 ships ONE V2 run (prophet_like) because that's enough to light up the
Feature Frame panel and prove V1↔V2 coexistence in the registry. PRP-39 picks
up the multi-run grain that powers champion-compat + stale-alias.

### Scope boundaries (sized for one shippable PR)

**Backend (`app/features/demo/` + `app/features/seeder/`):**

- Extend `_step_table()` (`app/features/demo/pipeline.py:670`) from 11 flat
  entries into a **phase-grouped table**. Each entry tagged with `phase_name`.
  Add Optional `phase_name` / `phase_index` / `phase_total` fields to
  `StepEvent` (additive — `app/features/demo/schemas.py:49`).
- Add two new steps under the **data** phase:
  - `phase2_enrichment` — `POST /seeder/phase2-enrichment` (NEW endpoint).
  - `historical_backfill` — `POST /seeder/historical-activity` (NEW endpoint).
- Add ONE new step under the **modeling** phase:
  - `v2_train` — `POST /forecasting/train` with
    `model_type="prophet_like"` and `feature_frame_version=2`, then
    `POST /registry/runs` + PATCH chain with
    `runtime_info_extras={"feature_frame_version": 2, "feature_columns": [...],
    "feature_groups": {...}}` and
    `artifact_uri = train_response["model_path"]` (full `artifacts/models/...`).
- Extend the **backtesting** step to pass `include_baselines=true` and
  `feature_frame_version=2`; capture
  `main_model_results.bucketed_aggregated_metrics` into the step's `data`
  payload.
- New `ScenarioPreset.SHOWCASE_RICH` in `app/shared/seeder/config.py:31` +
  factory branch in `SeederConfig.from_scenario` (target: 5 × 15 × 180 days,
  ~13.5k sales rows — middle-ground between `demo_minimal` and
  `retail_standard`).
- Existing `DemoRunRequest` gains an Optional `scenario: ScenarioPreset =
  ScenarioPreset.DEMO_MINIMAL` field (backwards compat: default keeps current
  behavior).
- Two new endpoints on the seeder slice (do NOT cross-import from `demo`):
  - `POST /seeder/phase2-enrichment` — wraps `scripts/seed_phase2_only.py`
    logic; reuses `app/shared/seeder/generators/{lifecycle,replenishment,exogenous,returns}.py`.
  - `POST /seeder/historical-activity` — wraps
    `scripts/seed_historical_activity.py` logic; reuses the same generators
    and the existing `RegistryService` over `httpx.ASGITransport`? **No** —
    the seeder slice cannot drive other slices over ASGI; it persists rows
    via its own SQLAlchemy session. Replicate the historical-activity logic
    as a service method.

**Frontend (`frontend/src/pages/showcase.tsx` + `components/demo/`):**

- New `DemoPhasePanel` component (shadcn `Accordion`) — one item per phase;
  the currently-running phase has `data-state="open"`.
- New `frontend/src/components/demo/PHASE_DEFS.ts` — single source of truth
  imported by both the page and the `use-demo-pipeline` hook. **Must match
  the backend `_phase_table()` order** (lockstep invariant — test enforces).
- Scenario picker (shadcn `Select`) + label/description for the three headline
  scenarios.
- Extend `useDemoPipeline()` (`frontend/src/hooks/use-demo-pipeline.ts`) to
  fold `StepEvent.phase_name` into a `Map<phase, Step[]>` instead of a flat
  `Step[]`. The hook stays additive — existing consumers keep working.
- Per-step Inspect button — small `Button asChild variant="outline" size="sm"`
  with a `Link to={...}` per step, gated on terminal `pass` status:
  - `train` → `/visualize/forecast?store_id=...&product_id=...`
  - `v2_train` → `/explorer/runs/{v2_run_id}` (Feature Frame panel)
  - `register` → `/explorer/runs/{winning_run_id}`
  - `backtest` → `/visualize/backtest?store_id=...&product_id=...`
- Backtest step card extension — render a per-bucket mini table
  (`h_1_7` / `h_8_14` / `h_15_28` / `h_29_plus`) when `bucketed_aggregated_metrics`
  is present in `step.data`. Reuse `frontend/src/components/forecast-intelligence/horizon-bucket-table.tsx`
  via its sub-component if extractable, otherwise render a 4-row mini table
  inline.

### Acceptance criteria

| # | Criterion | Verifiable by |
|---|-----------|---------------|
| A1 | `/showcase` renders three phase cards (data / modeling / decision-stub / verify-stub / agent-stub / cleanup-stub) on first load (idle state, no run). | Manual + a vitest `phase-accordion.test.tsx` |
| A2 | Selecting `showcase-rich` and clicking Run finishes in ≤ 240 s on `dev` hardware. | `pytest -m integration` wall-clock assertion (soft warn if > 240 s, hard fail if > 300 s) |
| A3 | After a `showcase-rich` run, `/explorer/runs/{v2_run_id}` Feature Frame panel renders V=2 badge + populated columns + signed coefs. | Manual dogfood checklist |
| A4 | After a `showcase-rich` run, `/visualize/backtest` for the showcase grain renders the horizon-bucket card with populated per-bucket metrics. | Manual dogfood checklist |
| A5 | `demo_minimal` scenario still finishes in ≤ 90 s with the same step set the existing `make demo` produces (no regression). | Existing `tests/test_e2e_demo.py` + new soft-warn |
| A6 | Backend `_phase_table()` and frontend `PHASE_DEFS` match in order + name. | `test_phase_table_stable` (backend) + `phase-defs.test.ts` (frontend) |
| A7 | All five validation gates green. | CI |

## EXAMPLES:

**Pattern to imitate (the existing demo slice):**

- `app/features/demo/pipeline.py:670-684` — `_step_table()` (the function to
  extend from a flat list into a phase-grouped table). Keep the function name;
  evolve the return type.
- `app/features/demo/pipeline.py:394-428` — `step_train()` (the parallel-train
  pattern using `asyncio.gather` — `v2_train` adopts a similar shape).
- `app/features/demo/pipeline.py:487-586` — `step_register()` (the
  two-step pending → running → success registry transition + alias create
  pattern — `v2_train` must follow this verbatim except for the artifact_uri
  rule, see § R1 in the parent INITIAL).
- `app/features/demo/pipeline.py:203-219` — `_llm_key_present()` (the
  skip-gracefully gate pattern — adopt for any new step that hits an external
  service).
- `app/features/demo/tests/test_pipeline.py` — pattern for per-step coverage.

**Pattern to imitate (PRP-37 frontend):**

- `frontend/src/components/forecast-intelligence/feature-frame-panel.tsx` —
  rendered by `/explorer/runs/{id}` for V2 runs; PRP-38's `v2_train` step's
  Inspect link points here.
- `frontend/src/components/forecast-intelligence/horizon-bucket-table.tsx` —
  the per-bucket mini-table component the backtest card embeds.
- `frontend/src/components/ui/accordion.tsx` — shadcn primitive for the phase
  accordion.

**Scenarios + presets:**

- `app/shared/seeder/config.py:516-657` — `SeederConfig.from_scenario` factory.
  Add a `SHOWCASE_RICH` branch after `DEMO_MINIMAL`.
- `app/shared/seeder/tests/test_phase1_regression.py` — pattern for the new
  preset's regression test (verifies the moderate-noise + no-sparsity tuning
  avoids the NaN-WAPE trap).

**Seeder enrichment + historical:**

- `scripts/seed_phase2_only.py` — port the orchestration logic into a new
  `SeederService.phase2_enrichment()` method; the route layer
  (`/seeder/phase2-enrichment`) wraps it.
- `scripts/seed_historical_activity.py` — port the orchestration logic into a
  new `SeederService.historical_activity()` method; the route layer
  (`/seeder/historical-activity`) wraps it. Keep the CLI scripts as thin
  wrappers around the service method so the existing CLI continues to work.

## DOCUMENTATION:

**Internal (load when authoring PRP-38):**

- `AGENTS.md` § Architecture & Conventions — vertical-slice rule. The two new
  `/seeder/*` endpoints MUST live in `app/features/seeder/routes.py`, NOT in
  `app/features/demo/`.
- `docs/_base/API_CONTRACTS.md` — current seeder + forecasting + backtesting +
  registry endpoints. PRP-38 adds two seeder endpoints; document additively.
- `docs/_base/RUNBOOKS.md` § "Showcase page (`/showcase`) pipeline fails at
  step X" — extend additively with `phase2_enrichment`,
  `historical_backfill`, and `v2_train` failure modes.
- `docs/_base/DOMAIN_MODEL.md` § "Key Invariants" — note R1 (V2 runs MUST use
  the full `artifacts/models/...` `artifact_uri`).
- `.claude/rules/test-requirements.md` — new endpoints ⇒ route test for 2xx
  happy path + at least one error path.
- `.claude/rules/shadcn-ui.md` — Accordion + Select must come through the
  `shadcn` skill + MCP, not hand-rolled.

**External (load via `mcp__claude_ai_contex7__`):**

- shadcn/ui Accordion: <https://ui.shadcn.com/docs/components/accordion>
- shadcn/ui Select: <https://ui.shadcn.com/docs/components/select>
- TanStack Query mutations: <https://tanstack.com/query/latest/docs/framework/react/guides/mutations>
- FastAPI WebSocket: <https://fastapi.tiangolo.com/advanced/websockets/>

**Prior-art PRPs (read for pattern):**

- `PRPs/PRP-35-forecast-intelligence-A-feature-frame-v2.md` — the contract that
  defines `feature_frame_version=2`, `runtime_info_extras.feature_columns`,
  `feature_groups`, etc. PRP-38's `v2_train` consumes these contracts.
- `PRPs/PRP-36-forecast-intelligence-B-model-zoo-backtesting.md` — the contract
  that defines `bucketed_aggregated_metrics`. PRP-38's `backtest` extension
  consumes this contract.
- `PRPs/PRP-37-forecast-intelligence-C-interactive-ui.md` — the frontend
  contract for the Feature Frame panel + horizon-bucket table. PRP-38's
  Inspect deep links land on PRP-37 surfaces.
- `PRPs/ai_docs/prp-37-contract-probe-report.md` — pattern for PRP-38's Task 1
  contract probe.

## OTHER CONSIDERATIONS:

### Hard constraints (from the parent INITIAL — repeated for PRP authoring convenience)

- **No new tables.** Persistent state goes to localStorage in PRP-41.
- **Vertical-slice rule.** `app/features/demo/` does NOT import from
  `app/features/seeder/` (or any other slice). The two new `/seeder/*`
  endpoints live in the seeder slice; the demo pipeline drives them over
  `httpx.ASGITransport`.
- **WebSocket contract is additive only.** New Optional fields on `StepEvent`
  (`phase_name`, `phase_index`, `phase_total`) — existing fields unchanged.
- **Phase table lockstep.** Backend `_phase_table()` + frontend `PHASE_DEFS`
  ship in this same PRP; tests enforce the match.
- **Skip gracefully.** Any phase that depends on a missing provider emits
  `skip` with a clear `detail` — never `fail`. (PRP-38's scope has no
  external-provider dependencies; this is forward-looking documentation
  for PRP-40/PRP-41.)

### Risks specific to PRP-38

| # | Risk | Mitigation |
|---|------|------------|
| R1 (from parent) | V2 runs registered with registry-relative `artifact_uri = "demo/...joblib"` break `/forecasting/runs/{id}/feature-metadata` because the latter resolves against `forecast_model_artifacts_dir`. | `v2_train` step MUST set `artifact_uri = train_response["model_path"]` (full `artifacts/models/...` path). Pin in the PRP risks; add a unit test. |
| R2 (from parent) | `HistGradientBoostingRegressor` (the `regression` model) has no `feature_importances_`. | Use `prophet_like` (Ridge → signed coefs) for the v2_train step. |
| R10 | `SHOWCASE_RICH` preset risks NaN-WAPE if noise/sparsity tuning is wrong. | Mirror `demo_minimal` tuning (moderate `noise_sigma=0.10`, `sparsity=0.0`); add a `test_phase1_regression`-style invariant. |
| R11 | New `/seeder/*` endpoints are slow on a cold DB; can blow the 120 s `_HTTP_TIMEOUT`. | Endpoint-level streaming response is out of scope. Pre-warm: the new scenario seed is the first slow step; `phase2_enrichment` runs after and is incremental. If `historical_backfill` regularly exceeds 60 s, slice it into a smaller cutoff window for the showcase context. |
| R12 | Phase table additions break existing `tests/test_e2e_demo.py` count assertions. | Assertions migrate to per-phase counts; existing 11-step baseline must remain reachable via `scenario=demo_minimal` (default). |

### Performance budget

- `demo_minimal`: ≤ 90 s wall-clock (existing budget — no regression).
- `showcase-rich`: ≤ 240 s wall-clock (new budget).
- Per-step timeout: 120 s (`_HTTP_TIMEOUT`, unchanged).

### Validation plan (PRP-38 specific)

**Task 1 — Contract Probe** (mandatory per epic):

- Verify every backend field PRP-38 cites exists on `dev`:
  - `runtime_info_extras.feature_frame_version`, `.feature_columns`,
    `.feature_groups`, `.feature_safety_classes`, `.feature_pinned_constants`
  - `BacktestRequest.include_baselines`, `.feature_frame_version`
  - `BacktestResponse.main_model_results.bucketed_aggregated_metrics`
  - `GET /forecasting/runs/{id}/feature-metadata` response shape
- Output to `PRPs/ai_docs/prp-38-contract-probe-report.md`.

**Backend tests (new):**

- `app/features/demo/tests/test_pipeline.py::test_phase_table_stable` — list of
  `(phase_name, step_name)` tuples is fixed.
- `app/features/demo/tests/test_pipeline.py::test_v2_train_step` — registers
  with `feature_frame_version=2` + full `artifacts/models/...` `artifact_uri`.
- `app/features/demo/tests/test_pipeline.py::test_phase2_enrichment_step` +
  `test_historical_backfill_step`.
- `app/features/demo/tests/test_pipeline.py::test_backtest_buckets_populated`
  on `showcase-rich`.
- `app/features/seeder/tests/test_routes.py` — happy + error for the two new
  endpoints.
- `app/shared/seeder/tests/test_phase1_regression.py` — `SHOWCASE_RICH` preset
  variant.
- `tests/test_e2e_demo.py` — assert `scenario=showcase-rich` finishes
  ≤ 240 s + V2 run registered + bucket metrics populated.

**Frontend tests (new):**

- `frontend/src/components/demo/PHASE_DEFS.test.ts` — matches backend
  `_phase_table()` order/name (string-list equality against a fixture).
- `frontend/src/components/demo/DemoPhasePanel.test.tsx` — phase grouping +
  auto-expand on running phase.
- `frontend/src/hooks/use-demo-pipeline.test.ts` — phase folding.
- `frontend/src/components/demo/demo-step-card.test.tsx` — per-step Inspect
  button renders with correct deep link on terminal `pass` status only.

**Manual dogfood checklist (PRP-38 specific):**

- [ ] Default `/showcase` (no scenario change) still runs in ≤ 90 s with the
      11-step legacy flow under the new phase grouping.
- [ ] `showcase-rich` selected → run finishes ≤ 240 s; phase accordion
      auto-expands the running phase.
- [ ] V2 prophet_like run appears in `/explorer/runs` with V=2 badge.
- [ ] `/explorer/runs/{v2_run_id}` Feature Frame panel renders V=2 + populated
      coefs.
- [ ] `/visualize/backtest` for the showcase grain shows the horizon-bucket
      card.
- [ ] Each terminal-status step card with payload has an Inspect button that
      navigates correctly.
- [ ] `pnpm tsc --noEmit -p tsconfig.app.json` clean (don't trust prior
      HANDOFF green checks).

### Stop-and-ask gates (PRP-38)

- Before any change to `app/features/demo/schemas.py:StepEvent` field that is
  NOT Optional + additive — stop and surface.
- Before adding any cross-slice import in `app/features/demo/` — stop;
  refactor through a new seeder endpoint instead.
- Before a `feat!:` (breaking) commit — stop. PRP-38 is purely additive.

### Future issue title (suggested)

`feat(api,ui): showcase pipeline — richer data + V1/V2 modeling foundation`

## PRP GENERATION COMMAND

Generate the PRP from this INITIAL with:

```
/base_prp:prp-create PRPs/INITIAL/INITIAL-showcase-38-data-modeling-lifecycle.md
```

**Position in the epic:** **FIRST** of four PRPs in the `/showcase` upgrade.
No prerequisites — this slice is the foundation. Merge before generating
PRP-39 (the decision-lifecycle slice consumes the V2 run this slice
registers on the showcase grain).
