name: "PRP-38 — Showcase Rich Demo Control Center A: Data + V1/V2 Modeling Foundation"
description: |
  Lay the MVP foundation for the four-PRP `/showcase` upgrade epic (PRP-38..41):
  extend the in-process demo pipeline from a flat 11-step baseline-only
  timeline into a **phase-grouped, scenario-aware demo** that creates richer
  data (phase-2 enrichment + historical activity backfill), trains V1 baselines
  AND one V2 feature-aware `prophet_like` run, and surfaces feature-aware
  backtest horizon-bucket metrics — enough so a single `/showcase` run lights
  up the PRP-37 Feature Frame panel and the PRP-36 horizon-bucket card
  end-to-end. Slice A of the rich-showcase roadmap
  (`PRPs/INITIAL/INITIAL-showcase-rich-demo-control-center.md`).

  > **PREREQUISITES — none.** PRP-38 is the foundation slice of the epic;
  > PRP-39, PRP-40, and PRP-41 all depend on it. Tasks below stay strictly
  > inside PRP-38 scope. Champion-compat compare, stale-alias trigger, safer
  > Promote dialog, batch preset/matrix, scenario simulate/save/compare, RAG
  > indexing, agent HITL flow, ops snapshot/KPI strip, Inspect-Artifacts
  > post-run panel, localStorage run history, Stop button — every one of
  > these belongs to PRP-39, PRP-40, or PRP-41. Mention them ONLY in the
  > "Out of Scope" block; do not implement, scaffold, or stub.

## Purpose

A one-pass implementation contract for an AI agent (or human) with access to
the codebase but no prior session context. Ship the MVP-grade foundation of
the `/showcase` rich demo upgrade: phase grouping, scenario picker,
`showcase-rich` preset, phase-2 + historical seeder endpoints, ONE V2
`prophet_like` run registered with the full `artifacts/models/...` artifact
URI, bucket-visible feature-aware backtest, and per-step Inspect deep links —
WITHOUT regressing the existing `demo_minimal` 11-step flow or violating the
demo slice's "stateless orchestrator over `httpx.ASGITransport`" invariant.

## Core Principles

1. **Backend contracts are read-only.** Every new field the pipeline reads
   originates from an existing PRP-35 / PRP-36 backend surface. The Task-1
   contract probe verifies presence before any other task starts. PRP-38
   adds NEW backend surface only in `app/features/seeder/` (the two new
   endpoints) and `app/features/demo/` (phase fields, new pipeline steps);
   it does not modify any PRP-35 / PRP-36 contract.
2. **Vertical-slice rule (load-bearing).** `app/features/demo/` MUST NOT
   import from any other `app/features/*` slice. The new phase-2 enrichment
   and historical-activity helpers land as `/seeder/phase2-enrichment` and
   `/seeder/historical-activity` endpoints on the seeder slice; the demo
   pipeline drives them over `httpx.ASGITransport` exactly like the existing
   `/seeder/generate`, `/forecasting/train`, `/registry/runs` calls. The CLI
   scripts `scripts/seed_phase2_only.py` + `scripts/seed_historical_activity.py`
   stay as thin wrappers around the new service methods so existing CLI use
   keeps working.
3. **WebSocket contract is ADDITIVE ONLY.** New Optional fields on
   `StepEvent` (`phase_name`, `phase_index`, `phase_total`). Existing fields
   keep their type and semantics. No version key bump — clients ignore
   unknown fields.
4. **Phase table is a stability invariant.** Backend `_phase_table()` and
   frontend `PHASE_DEFS.ts` ship in the SAME PRP slice and stay lockstep.
   `test_phase_table_stable` (backend) + `phase-defs.test.ts` (frontend)
   are the lockstep enforcement.
5. **No new tables.** `app/features/demo/` stays stateless. No Alembic
   migration is part of PRP-38. (PRP-41's run-history strip will live in
   localStorage.)
6. **Skip gracefully on missing providers.** Every step that depends on an
   external provider MUST use the `_llm_key_present()` gating pattern at
   `app/features/demo/pipeline.py:203-219` and emit `skip` with a clear
   `detail`. A missing key is NEVER `fail`. PRP-38 itself adds no
   external-provider dependencies, but the pattern is the documented
   precedent for PRP-40 / PRP-41.
7. **Pre-1.0 contract additivity.** Every new schema field is Optional; no
   `feat!:`/breaking commit. PRP-38 is purely additive.
8. **shadcn workflow.** Every UI primitive (Accordion + Select) arrives via
   `pnpm dlx shadcn@4.7.0 add …` from `frontend/`, per
   `.claude/rules/shadcn-ui.md` and memories
   `[[shadcn-cli-version-pin]]` + `[[radix-ui-vs-per-component-imports]]`.

---

## Goal

Deliver, on branch `feat/showcase-38-data-modeling-lifecycle`, the
foundation slice of the `/showcase` rich demo upgrade so a first-time
visitor to `/showcase` sees:

- A **phase accordion** grouping the pipeline into 6 phases (`data`,
  `modeling`, `decision`, `verify`, `agent`, `cleanup`); the currently
  running phase auto-expands.
- A **scenario picker** (shadcn `Select`) with three headline scenarios —
  `demo_minimal` (default, fast loop, ~60 s), `showcase-rich` (new
  preset, ~3 min), `sparse` (edge-case).
- A **`showcase-rich` preset** (5 stores × 15 products × 180 days) wired
  through `SeederConfig.from_scenario`.
- New `data`-phase steps for **phase-2 enrichment** (lifecycle /
  replenishment / exogenous / returns) and **historical activity backfill**
  (a small set of historical jobs at past cutoffs to populate the runs/jobs
  pages), driven by two new `/seeder/*` endpoints.
- New `modeling`-phase step `v2_train` that trains ONE `prophet_like` model
  with `feature_frame_version=2`, registers it with
  `runtime_info_extras={"feature_frame_version": 2, "feature_columns": [...],
  "feature_groups": {...}}`, and uses `artifact_uri = train_response["model_path"]`
  (the FULL `artifacts/models/...` path, NOT the registry-relative
  `demo/...joblib` form the existing `step_register` uses for V1).
- A **feature-aware backtest** with bucket-visible per-horizon-bucket
  metrics (`h_1_7` / `h_8_14` / `h_15_28` / `h_29_plus`) rendered inline
  in the backtest step card.
- **Per-step Inspect buttons** on terminal-status step cards with payload:
  `train` → `/visualize/forecast?store_id=…&product_id=…`, `v2_train` →
  `/explorer/runs/{v2_run_id}`, `register` → `/explorer/runs/{winning_run_id}`,
  `backtest` → `/visualize/backtest?store_id=…&product_id=…`.

## Why

Without PRP-38, the `/showcase` page demonstrates only baselines on
`demo_minimal`; ~10 of the system's ~40 endpoints are exercised; the
entire PRP-37 operator UI (Feature Frame panel, horizon-bucket card,
champion-compat badge, safer Promote dialog) is invisible to a first-time
visitor unless they hand-craft data first.

PRP-38 is the foundation that makes the rest of the epic possible:

- The V2 `prophet_like` run unlocks the PRP-37 Feature Frame panel
  (depends on `runtime_info_extras.feature_frame_version=2` +
  `feature_columns` + signed coefficients).
- The bucket-visible backtest unlocks the PRP-36 horizon-bucket card.
- The phase accordion + scenario picker is the orchestration surface
  PRP-39, PRP-40, PRP-41 plug into additively (each new step lands inside
  the right phase; no UI shell rewrites).
- The `showcase-rich` preset is the multi-grain dataset PRP-39's
  champion-compat compare and PRP-40's saved-scenario library need.

## What

### User-visible behaviour

- `/showcase` renders a phase accordion (6 phases) on first load; the
  currently-running phase auto-expands, completed phases collapse with a
  status icon + step count.
- A scenario `Select` above the Run button offers `demo_minimal` /
  `showcase-rich` / `sparse` with one-line descriptions and an estimated
  wall-clock label. Default = `demo_minimal` (backwards compat).
- Selecting `showcase-rich` and clicking Run starts a phase-grouped
  streaming pipeline that finishes in ≤ 240 s on `dev` hardware. The
  `data` phase emits `seed` (now from the chosen scenario), then
  `phase2_enrichment`, then `historical_backfill`. The `modeling` phase
  emits V1 `train` (×3 baselines in parallel) and `v2_train` (×1
  `prophet_like`). The `decision` phase emits `backtest` (now feature-aware
  with bucket metrics) and `register` (winner alias). The `verify`,
  `agent`, and `cleanup` phases remain unchanged in shape.
- The `backtest` step card shows a 4-row mini table of per-horizon-bucket
  metrics when `bucketed_aggregated_metrics` is present in the response
  (`h_1_7` / `h_8_14` / `h_15_28` / `h_29_plus`).
- Each terminal-status step card with a populated `data` payload shows a
  small "Inspect" button deep-linking into the relevant dashboard page.
- After a `showcase-rich` run, `/explorer/runs/{v2_run_id}` Feature Frame
  panel renders V=2 badge + populated feature columns + signed Ridge
  coefficients.
- After a `showcase-rich` run, `/visualize/backtest` for the showcase
  grain shows the horizon-bucket card with populated per-bucket metrics.

### Technical requirements

- Backend: ruff + mypy `--strict` + pyright `--strict` clean on every new
  module (`app/features/demo/`, `app/features/seeder/`). RFC 7807 errors
  via `app/core/problem_details.py`; no bare `HTTPException(500, "…")`.
- Frontend: `pnpm tsc --noEmit -p tsconfig.app.json` clean (NOT bare `tsc`
  — root `tsconfig.json` has `"files": []`; the project type-check uses
  the app config — risk R7 below). `pnpm lint` + `pnpm test --run` clean.
- Vertical-slice rule preserved: `git grep -nE "from app\.features\.[^d][^.]*" app/features/demo/`
  MUST return empty (only `app.features.demo.*` and `app.core.*` /
  `app.shared.*` imports allowed in the demo slice).
- WebSocket contract additive only: `git grep -n "phase_" app/features/demo/schemas.py`
  shows the three new Optional fields; no existing field changed.
- Performance: `demo_minimal` ≤ 90 s wall-clock (no regression);
  `showcase-rich` ≤ 240 s wall-clock; per-step timeout 120 s
  (`_HTTP_TIMEOUT`, unchanged).
- No new env vars; no managed-cloud SDK; no new tables; no agent mutation
  surface change; no `agent_require_approval` widening.

### Success Criteria

- [ ] Task 1 (Contract Probe) report committed at
      `PRPs/ai_docs/prp-38-contract-probe-report.md` and every cited
      backend field is verified PRESENT on `dev`. If any cited field is
      ABSENT, the dependent task is patched (deferred or rewired) before
      Task 2 starts.
- [ ] Backend `_phase_table()` and frontend `PHASE_DEFS` match in order
      AND name; `test_phase_table_stable` (backend) + `phase-defs.test.ts`
      (frontend) both green.
- [ ] `/seeder/phase2-enrichment` returns a 2xx happy path on a seeded DB
      AND a 4xx RFC-7807 error on an empty DB; both have route tests.
- [ ] `/seeder/historical-activity` returns a 2xx happy path on a seeded
      DB AND a 4xx RFC-7807 error on an empty DB; both have route tests.
- [ ] `ScenarioPreset.SHOWCASE_RICH` is added to the enum AND wired
      through `SeederConfig.from_scenario` with deterministic noise/sparsity
      tuning (mirrors `demo_minimal` to avoid the NaN-WAPE trap); a
      `test_phase1_regression`-style invariant asserts a non-NaN backtest
      WAPE under the standard split config.
- [ ] `DemoRunRequest` gains an Optional `scenario: ScenarioPreset =
      ScenarioPreset.DEMO_MINIMAL` field; existing default behaviour
      preserved (skip_seed=True → no scenario change).
- [ ] `step_v2_train` registers a `prophet_like` run with
      `feature_frame_version=2` AND `artifact_uri = train_response["model_path"]`
      (the FULL `artifacts/models/...` path, NOT the registry-relative
      form). Unit test asserts both fields.
- [ ] `step_backtest` posts `include_baselines=true` with a feature-aware
      `model_config_main` (`prophet_like`); response's
      `main_model_results.bucketed_aggregated_metrics` is non-empty AND
      the step's `data` payload echoes it. A unit test asserts the bucket
      keys subset against
      `app.features.backtesting.metrics.HORIZON_BUCKETS`.
- [ ] `/showcase` default load shows 6 phase cards in idle state with
      the legacy 11 step names grouped under them; clicking Run with
      default scenario reproduces the existing 11-step `demo_minimal`
      flow in ≤ 90 s (no regression). Existing `tests/test_e2e_demo.py`
      stays green.
- [ ] `/showcase` with `scenario=showcase-rich` selected finishes in
      ≤ 240 s wall-clock; phase accordion auto-expands the currently
      running phase; soft-warn on > 240 s, hard-fail on > 300 s.
- [ ] `/explorer/runs/{v2_run_id}` Feature Frame panel renders V=2 badge,
      populated `feature_columns`, populated `feature_groups`, and at
      least one signed coefficient row (manual dogfood + screenshot).
- [ ] `/visualize/backtest` for the showcase grain renders the
      horizon-bucket card with all 4 bucket keys populated (manual
      dogfood + screenshot).
- [ ] Per-step Inspect button: present on terminal `pass` step cards
      where `data` has the deep-link inputs; absent otherwise. Vitest
      verifies both branches.
- [ ] All five validation gates green: ruff + ruff format + mypy +
      pyright + pytest (unit + integration) + migration-check.
- [ ] `pnpm lint && pnpm tsc --noEmit -p tsconfig.app.json && pnpm test --run`
      green from `frontend/`.
- [ ] No `from 'radix-ui'` barrel imports introduced (grep guard).
- [ ] CHANGELOG entry under "Unreleased":
      `feat(api,ui): showcase pipeline — richer data + V1/V2 modeling foundation (#<issue>)`.

### Out of Scope (explicit — do NOT implement in PRP-38)

These belong to later PRPs in the epic. Mention only in the walkthrough
disclaimer; do not scaffold, stub, or render placeholders.

- **PRP-39 (decision + portfolio)** — champion-compat compare badge on
  `/explorer/runs/compare`, stale-alias trigger emitting
  `stale_reason="feature_frame_version_mismatch"`, safer-Promote
  AlertDialog dogfood walk-through, `quick_baseline_sweep` 3×2×3 batch.
- **PRP-40 (planning + knowledge)** — scenario simulate / save / multi-plan
  compare, `/config/providers/health` embedding-provider probe,
  `/rag/index/project-docs` curated 5-file corpus, `/rag/retrieve` probe.
- **PRP-41 (agent + ops + polish)** — agent HITL flow with
  `save_scenario` approval, `/ops/summary` + `/ops/retraining-candidates`
  + `/ops/model-health/{grain}` snapshot KPI strip, Inspect-Artifacts
  post-run grid panel, localStorage last-5-runs strip, Stop button,
  walkthrough docs polish (`docs/user-guide/showcase-walkthrough.md`).

---

## All Needed Context

### Documentation & References

```yaml
# ─── Epic INITIAL bundle (load first, in this order) ─────────────────
- file: PRPs/INITIAL/INITIAL-showcase-rich-demo-control-center.md
  why: Umbrella INITIAL — strategy ("mixed MVP + Option B"), R1..R9 risk register, performance budgets, validation plan. PRP-38 is the foundation slice; every constraint in the umbrella applies.

- file: PRPs/INITIAL/INITIAL-showcase-rich-demo-index.md
  why: Sequence + dependency graph. PRP-38 has no prerequisites. PRP-39 + PRP-40 depend on PRP-38; PRP-41 depends on PRP-39 AND PRP-40.

- file: PRPs/INITIAL/INITIAL-showcase-38-data-modeling-lifecycle.md
  why: Source of truth for THIS PRP's scope. Re-read on disagreement.

# ─── Project rules (enforce mechanically) ────────────────────────────
- file: AGENTS.md
  why: Universal agent brief — vertical-slice rule, validation gates, RFC 7807 envelope, hard-rules list, agent_require_approval invariant. The architecture & conventions section is THE source of the no-cross-slice-import rule the demo slice MUST hold.

- file: CLAUDE.md
  why: Claude operating index — pulls in the docs/_base/* deep-dive references; AGENTS.md is imported at the top.

- file: .claude/rules/test-requirements.md
  why: Every new endpoint ⇒ route test (2xx + at least one error); every new pipeline step ⇒ a step test; every new module ⇒ a module test.

- file: .claude/rules/shadcn-ui.md
  why: Mandatory shadcn workflow — invoke the shadcn skill + mcp__shadcn__* tools BEFORE writing any shadcn-touching code. Pin shadcn@4.7.0. From `frontend/`, NOT repo root.

- file: .claude/rules/security-patterns.md
  why: RFC 7807 errors only; no raw `HTTPException(500, "…")`. Pydantic v2 strict-mode-on-request-bodies policy (no JSON-incompatible types on a `ConfigDict(strict=True)` body without `Field(strict=False, …)`); see SECURITY.md cross-reference for the dated PRP-14 precedent.

- file: docs/_base/RUNBOOKS.md
  why: "Showcase page (/showcase) pipeline fails at step X" failure-mode catalogue. PRP-38 extends this section additively for the new steps (phase2_enrichment, historical_backfill, v2_train).

- file: docs/_base/DOMAIN_MODEL.md
  why: Comparable-run rule + R1 (V2 artifact_uri must be the full artifacts/models/... path). PRP-38 v2_train step is the first place this contract bites.

# ─── Backend codebase anchors (demo slice — the slice this PRP extends) ─
- file: app/features/demo/pipeline.py
  why: `_step_table()` at line 670 is the function that becomes the phase-grouped table. `step_register()` at line 487 is the registry create+update+alias pattern; v2_train must mirror it EXCEPT for the artifact_uri rule (full path, not registry-relative). `step_train()` at line 394 is the parallel-train pattern v2_train borrows. `_llm_key_present()` at line 203 is the skip-gracefully pattern. `_HTTP_TIMEOUT` at line 67 is the 120 s per-step timeout — unchanged.

- file: app/features/demo/schemas.py
  why: `StepEvent` at line 49 is the additively-extensible streamed event. PRP-38 adds `phase_name`, `phase_index`, `phase_total` as Optional fields. `DemoRunRequest` at line 27 gains an Optional `scenario` field.

- file: app/features/demo/routes.py
  why: `POST /demo/run` and `WS /demo/stream` wiring + the module-level `asyncio.Lock` for one-pipeline-at-a-time. No change in PRP-38; pattern reference for understanding the WebSocket start frame.

- file: app/features/demo/tests/test_pipeline.py
  why: The coverage pattern each new step must mirror. PRP-38 adds `test_phase_table_stable`, `test_v2_train_step`, `test_phase2_enrichment_step`, `test_historical_backfill_step`, `test_backtest_buckets_populated`.

# ─── Backend codebase anchors (seeder slice — extended additively) ─────
- file: app/features/seeder/routes.py
  why: Existing routes (`/seeder/{status, scenarios, channels, generate, append, data, query-exogenous, verify}`). PRP-38 adds `/seeder/phase2-enrichment` and `/seeder/historical-activity`. Follow the existing `@router.post(...)` / 422 / RFC 7807 patterns.

- file: app/features/seeder/service.py
  why: SeederService methods the new endpoints call. PRP-38 adds `phase2_enrichment(...)` and `historical_activity(...)` instance methods — port logic from scripts/seed_phase2_only.py + scripts/seed_historical_activity.py respectively.

- file: app/features/seeder/schemas.py
  why: Pydantic request/response models. PRP-38 adds `Phase2EnrichmentRequest`, `Phase2EnrichmentResponse`, `HistoricalActivityRequest`, `HistoricalActivityResponse` — all `BaseModel` (response) and `BaseModel` + `ConfigDict(strict=True)` (request) per `app/core/tests/test_strict_mode_policy.py` (any date/datetime fields use `Field(strict=False, ...)`).

- file: app/shared/seeder/config.py
  why: `ScenarioPreset` enum at line 31 — add `SHOWCASE_RICH = "showcase_rich"` (string value, lowercase + underscore). `SeederConfig.from_scenario` factory at line 516 — add the `SHOWCASE_RICH` branch AFTER `DEMO_MINIMAL` (line 632), mirror the `DEMO_MINIMAL` deterministic-noise tuning to avoid the NaN-WAPE trap (R10). Target dimensions: 5 stores × 15 products × 180 days, noise_sigma=0.10, sparsity=0.0.

- file: app/shared/seeder/tests/test_phase1_regression.py
  why: Pattern for the new `SHOWCASE_RICH` regression test — assert a non-NaN backtest WAPE under expanding splits, n=3, horizon=14, min_train_size=30.

- file: scripts/seed_phase2_only.py
  why: Source logic for the new `SeederService.phase2_enrichment` method. The CLI script becomes a thin wrapper around the service method so existing CLI use keeps working.

- file: scripts/seed_historical_activity.py
  why: Source logic for the new `SeederService.historical_activity` method. The CLI script becomes a thin wrapper around the service method so existing CLI use keeps working. CRITICAL: the script today drives the HTTP API; the service version operates over an async SQLAlchemy session within the seeder slice (NO cross-slice imports). Replicate the logic at the data layer; do NOT have the seeder service call `RegistryService` over `httpx.ASGITransport` (the seeder slice cannot drive other slices over ASGI — vertical-slice rule).

# ─── Backend codebase anchors (PRP-35 / PRP-36 contracts the v2_train + backtest steps consume) ───
- file: app/features/forecasting/schemas.py
  why: `TrainRequest` at line 437 — `feature_frame_version: int = Field(default=1, ge=1, le=2, ...)` at line 475; `feature_groups: list[str] | None` at line 484. `validate_feature_frame_version_and_groups` model_validator at line 504 rejects `feature_groups` when V1 (422) and rejects unknown group names when V2 (422). `TrainResponse.model_path: str` at line 540/568 — the full `artifacts/models/...` path. `FeatureMetadataResponse` at line ~700 — `feature_frame_version`, `feature_groups`, `feature_safety_classes` Optional fields populated for V2 bundles.

- file: app/features/registry/schemas.py
  why: `RunCreate.runtime_info_extras: dict[str, Any] | None` at line 85 — this is where the v2_train step writes `feature_frame_version`, `feature_columns`, `feature_groups`, `feature_safety_classes`. `RunResponse.feature_frame_version` + `feature_groups` are `@computed_field` properties reading `runtime_info`.

- file: app/features/backtesting/schemas.py
  why: `BacktestConfig.model_config_main: ModelConfig` at line 100 — the V2-ness of a backtest comes from the model_type (a feature-aware family like `prophet_like` / `regression`), NOT from a top-level `feature_frame_version` on the request. `FoldResult.horizon_bucket_metrics: dict[str, dict[str, float]]` at line 171 with `default_factory=dict`. `ModelBacktestResult.bucketed_aggregated_metrics: dict[str, dict[str, float]] | None` at line 206 — None when no fold emitted a non-empty bucket dict. `BacktestRequest` at line 222 (store_id, product_id, start_date, end_date, config) — there is NO top-level `feature_frame_version` field; do NOT add one.

- file: app/features/backtesting/metrics.py
  why: `HORIZON_BUCKETS` constant — the 4 stable bucket ids (`h_1_7`, `h_8_14`, `h_15_28`, `h_29_plus`). `MetricsCalculator.calculate_all` emits `"rmse"` inside the `aggregated_metrics: dict[str, float]` dict (PRP-36) — no separate `AggregateMetrics` class.

# ─── Frontend codebase anchors (UI the showcase page extends) ──────────
- file: frontend/src/pages/showcase.tsx
  why: 164-line shell PRP-38 extends. Header + controls (Run button + Re-seed / Reset checkboxes) + error banner + summary banner + flat step cards. PRP-38 inserts the scenario picker above Run, the phase accordion replaces the flat cards.

- file: frontend/src/hooks/use-demo-pipeline.ts
  why: WebSocket reducer hook. `STEP_DEFS` at line 39 is the current flat list; PRP-38 imports `PHASE_DEFS` from a new `components/demo/PHASE_DEFS.ts` (single source of truth shared with the page). `applyEvent` at line 83 stays additive — when an event carries `phase_name` it groups steps; when absent (legacy), it falls back to the flat list (`demo_minimal` runs without `phase_name` keep rendering).

- file: frontend/src/components/demo/demo-step-card.tsx
  why: Per-step card renderer. PRP-38 adds an Optional Inspect button render slot driven by the parent component (passes `inspectHref?: string | null`). PRP-38 also adds a small `<HorizonBucketsMini>` sub-component or table block when `step.data.bucketed_aggregated_metrics` is present (backtest step only).

- file: frontend/src/components/ui/accordion.tsx
  why: shadcn primitive. CONFIRM present via `mcp__shadcn__list_items_in_registries` or `cd frontend && pnpm dlx shadcn@4.7.0 add accordion --dry-run` — already installed today, but `frontend/components.json` is the authoritative check.

- file: frontend/src/components/ui/select.tsx
  why: shadcn primitive — already installed; reused for the scenario picker.

- file: frontend/src/types/api.ts
  why: Source of truth for backend wire types. PRP-38 adds Optional `phase_name` / `phase_index` / `phase_total` on `StepEvent`, and `scenario` on `DemoRunRequest`. Existing types preserved; everything additive.

- file: frontend/src/lib/url-params.ts
  why: `parseEnumParam<T>` at L37-48 is the canonical URL-state parser. PRP-38 does NOT add new URL params on `/showcase` (out of scope; PRP-41 may add a `scenario=...` query param for deep-linking — flagged in PRP-41 only).

# ─── Frontend codebase anchors (deep-link targets the Inspect buttons hit) ───
- file: frontend/src/components/forecast-intelligence/feature-frame-panel.tsx
  why: V2 Feature Frame panel rendered by `/explorer/runs/{id}` — depends on the v2_train step having registered with the FULL `artifacts/models/...` `artifact_uri` so the feature-metadata endpoint resolves the bundle. R1 — verify in Task 1 (dogfood).

- file: frontend/src/components/forecast-intelligence/horizon-bucket-table.tsx
  why: Source for the small horizon-bucket table the backtest step card embeds. Reuse via composition if possible; otherwise render an inline 4-row mini table that matches the bucket ids (`h_1_7`, `h_8_14`, `h_15_28`, `h_29_plus`) and the label scheme from `frontend/src/lib/horizon-bucket-utils.ts`.

- file: frontend/src/lib/constants.ts
  why: `ROUTES` map — the canonical deep-link constants (`ROUTES.VISUALIZE.FORECAST`, `ROUTES.EXPLORER.RUNS`, `ROUTES.VISUALIZE.BACKTEST`). PRP-38 deep links go through these, NOT raw string concatenation.

# ─── Test patterns ──────────────────────────────────────────────────
- file: app/features/demo/tests/test_pipeline.py
  why: Each new pipeline step adds a sibling test that drives `step_<name>(ctx, _Client(app))` directly. Use `httpx.ASGITransport(app=app, raise_app_exceptions=False)` per `app/features/demo/pipeline.py:104-113`.

- file: tests/test_e2e_demo.py
  why: Soft-warn wall-clock pattern (>240 s warn, >300 s fail). PRP-38 extends this with a `scenario=showcase-rich` integration test that asserts (a) wall-clock budget, (b) at least one V2 run registered with V=2, (c) bucket metrics populated.

- file: frontend/src/hooks/use-demo-pipeline.test.ts
  why: Vitest pattern for the WebSocket-folding reducer. PRP-38 extends to cover phase-aware folding (steps grouped under their `phase_name`).

- file: frontend/src/components/demo/demo-step-card.test.tsx
  why: Pattern for per-step card tests — PRP-38 extends with the Inspect-button render test (present on terminal pass, absent otherwise).

# ─── External docs (load on demand via mcp__claude_ai_contex7__) ─────
- url: https://ui.shadcn.com/docs/components/accordion
  section: "Anatomy" + "Examples → Default open"
  critical: The accordion `defaultValue` / `value` controls which item starts expanded; PRP-38 binds this to the currently-running phase so it auto-expands as the pipeline advances.

- url: https://ui.shadcn.com/docs/components/select
  section: "Anatomy"
  critical: The scenario picker uses `<Select>` with a controlled `value`/`onValueChange` plus `<SelectItem>` children inside a `<SelectGroup>` (per `.claude/rules/shadcn-ui.md` "Composition rules" — `SelectItem` MUST live inside `SelectGroup`).

- url: https://fastapi.tiangolo.com/advanced/websockets/
  section: "Handling disconnections" + "Closing the connection"
  critical: The demo slice's existing WS handler in routes.py closes the socket on `pipeline_complete` / `error`. PRP-38 changes neither path; the new phase fields ride inside the existing per-event payload.

- url: https://tanstack.com/query/latest/docs/framework/react/guides/mutations
  section: "Mutation lifecycle"
  critical: The scenario `Select` does NOT trigger a mutation by itself — it sets local React state. The Run button is the mutation trigger; nothing changes about TanStack Query wiring.

# ─── Memory anchors ─────────────────────────────────────────────────
- memory: shadcn-cli-version-pin
  why: Pin `shadcn@4.7.0`. 5.x silently writes a stub `pnpm-workspace.yaml` and skips the component install. Accordion + Select are likely already installed; verify via `mcp__shadcn__list_items_in_registries` before re-adding.

- memory: radix-ui-vs-per-component-imports
  why: This project uses `@radix-ui/react-X` per-component packages. Never `from 'radix-ui'`. Grep guard `grep -rn "from 'radix-ui'" frontend/src` must remain empty after PRP-38 edits.

- memory: dogfood-stale-uvicorn-port-8123
  why: Check `ps -ef | grep uvicorn` before claiming UI changes work; a previous-session uvicorn may still serve stale code on :8123.

- memory: playwright-dogfood-snap-chromium
  why: Dogfood via the `webapp-testing` skill, or native Python Playwright with `executable_path=/snap/bin/chromium`. Playwright MCP fails on this host.

- memory: repo-line-endings-crlf
  why: Some files in this repo are CRLF; `Edit`/`Write` emit LF and can produce whole-file noise diffs. Run `git diff --stat` before committing; if a file shows a whole-file diff, normalise the line endings deliberately in a separate commit (not in this PRP).

- memory: histgbr-no-feature-importances
  why: R2 — `HistGradientBoostingRegressor` has NO `feature_importances_`. Do NOT use `regression` for the V2 Feature Frame demo; use `prophet_like` (Ridge → signed coefficients).

- memory: scenario-run-id-vs-registry-run-id
  why: `/scenarios/*` run_id is the forecast artifact key (`model_{id}.joblib`), NOT the registry `model_run.run_id`. PRP-38 does NOT touch scenarios — but the Feature Frame Inspect link uses the REGISTRY run_id (the `winning_run_id` / new V2 `run_id` returned by `POST /registry/runs`).

- memory: seeder-does-not-reset-id-sequences
  why: `step_status` already discovers the real `store_id` / `product_id` via `/dimensions/*` (pipeline.py:307-356) — DO NOT hardcode 1. The new `historical_backfill` step must also discover IDs the same way.
```

### Current Codebase tree (relevant slices)

```
app/
├── core/
│   ├── config.py                        # Settings(); forecast_model_artifacts_dir; registry_artifact_root
│   └── problem_details.py               # RFC 7807 envelope (re-used)
├── features/
│   ├── demo/
│   │   ├── pipeline.py                  # 771 LOC; _step_table() at 670; step_register at 487
│   │   ├── routes.py                    # POST /demo/run; WS /demo/stream
│   │   ├── schemas.py                   # 106 LOC; StepEvent at 49; DemoRunRequest at 27
│   │   ├── service.py                   # tiny — just a dispatch wrapper
│   │   └── tests/
│   │       ├── test_pipeline.py
│   │       ├── test_routes.py
│   │       └── test_schemas.py
│   ├── seeder/
│   │   ├── routes.py                    # 8 existing /seeder/* routes
│   │   ├── schemas.py
│   │   ├── service.py                   # SeederService — append/generate/verify/...
│   │   └── tests/
│   ├── forecasting/
│   │   └── schemas.py                   # TrainRequest @ 437; TrainResponse @ 522
│   ├── registry/
│   │   └── schemas.py                   # RunCreate @ 71; RunResponse w/ computed feature_frame_version
│   ├── backtesting/
│   │   ├── schemas.py                   # BacktestRequest @ 222; ModelBacktestResult @ 180
│   │   └── metrics.py                   # HORIZON_BUCKETS constant
│   └── …
└── shared/
    └── seeder/
        ├── config.py                    # ScenarioPreset @ 31; SeederConfig.from_scenario @ 516
        ├── core.py
        └── generators/{lifecycle, replenishment, exogenous, returns, …}.py
frontend/
├── components.json                      # shadcn config (new-york, lucide)
├── src/
│   ├── pages/
│   │   └── showcase.tsx                 # 164 LOC; shell PRP-38 extends
│   ├── hooks/
│   │   └── use-demo-pipeline.ts         # 190 LOC; reducer + WS
│   ├── components/
│   │   ├── demo/demo-step-card.tsx
│   │   ├── ui/{accordion,select,…}.tsx
│   │   └── forecast-intelligence/{feature-frame-panel, horizon-bucket-table, …}.tsx
│   ├── types/api.ts                     # StepEvent, DemoRunRequest mirror
│   └── lib/{constants.ts (ROUTES), …}
└── …
scripts/
├── seed_phase2_only.py                  # 227 LOC — becomes a wrapper around SeederService.phase2_enrichment
└── seed_historical_activity.py          # 199 LOC — becomes a wrapper around SeederService.historical_activity
```

### Desired Codebase tree (additive + modified files)

```
app/
├── features/
│   ├── demo/
│   │   ├── pipeline.py                  # MODIFIED — _step_table() returns phase-grouped tuples; new step_v2_train; step_backtest extended for feature-aware + buckets; existing 11 steps preserved
│   │   ├── schemas.py                   # MODIFIED — StepEvent gains Optional phase_name/phase_index/phase_total; DemoRunRequest gains Optional scenario
│   │   └── tests/
│   │       └── test_pipeline.py         # MODIFIED — adds test_phase_table_stable, test_v2_train_step, test_phase2_enrichment_step, test_historical_backfill_step, test_backtest_buckets_populated
│   └── seeder/
│       ├── routes.py                    # MODIFIED — POST /seeder/phase2-enrichment, POST /seeder/historical-activity
│       ├── service.py                   # MODIFIED — phase2_enrichment(), historical_activity() instance methods
│       ├── schemas.py                   # MODIFIED — Phase2EnrichmentRequest/Response, HistoricalActivityRequest/Response
│       └── tests/
│           └── test_routes.py           # MODIFIED — happy + error for the two new endpoints
└── shared/
    └── seeder/
        ├── config.py                    # MODIFIED — ScenarioPreset.SHOWCASE_RICH + SeederConfig.from_scenario branch
        └── tests/
            └── test_phase1_regression.py # MODIFIED — adds SHOWCASE_RICH non-NaN-WAPE invariant
frontend/
├── src/
│   ├── pages/
│   │   └── showcase.tsx                 # MODIFIED — scenario Select + phase accordion + per-step Inspect; legacy flat-list fallback when phase_name absent on events (demo_minimal back-compat)
│   ├── hooks/
│   │   └── use-demo-pipeline.ts         # MODIFIED — phase-aware folding (steps grouped by phase_name when present); existing reducer preserved
│   ├── components/
│   │   ├── demo/
│   │   │   ├── PHASE_DEFS.ts            # NEW — single source of truth for phase order/name/label; lockstep-tested against backend _phase_table()
│   │   │   ├── DemoPhasePanel.tsx       # NEW — shadcn Accordion wrapping the per-phase step lists
│   │   │   ├── ScenarioPicker.tsx       # NEW — shadcn Select for the 3 headline scenarios
│   │   │   ├── HorizonBucketsMini.tsx   # NEW — 4-row mini table for the backtest step card; reuses sortBuckets/labelForBucket from frontend/src/lib/horizon-bucket-utils.ts
│   │   │   ├── demo-step-card.tsx       # MODIFIED — Inspect button slot; embeds <HorizonBucketsMini> on backtest pass
│   │   │   └── tests/
│   │   │       ├── PHASE_DEFS.test.ts
│   │   │       ├── DemoPhasePanel.test.tsx
│   │   │       ├── ScenarioPicker.test.tsx
│   │   │       ├── HorizonBucketsMini.test.tsx
│   │   │       └── demo-step-card.test.tsx (extends existing)
│   ├── types/api.ts                     # MODIFIED — StepEvent + DemoRunRequest additive fields
│   └── ...
tests/
├── test_e2e_demo.py                     # MODIFIED — adds scenario=showcase-rich integration test with ≤240 s soft-warn, V2 run + bucket metric assertions
PRPs/
└── ai_docs/
    └── prp-38-contract-probe-report.md  # NEW — Task 1 output; PRESENT/ABSENT verdicts per cited field with file:line
docs/
└── _base/
    └── RUNBOOKS.md                      # MODIFIED — Showcase failure-mode catalogue extended with phase2_enrichment, historical_backfill, v2_train failure modes
```

### Known Gotchas of our codebase & Library Quirks

```python
# ─────────────────────────────────────────────────────────────────────────
# CRITICAL: Task 1 (Contract Probe) is the gate. Run it FIRST.
# ─────────────────────────────────────────────────────────────────────────
# Verify on `dev` (or current branch's tip):
#   - TrainRequest.feature_frame_version + feature_groups exist + reject V1+groups (422).
#   - TrainResponse.model_path is a FULL path (artifacts/models/...), not registry-relative.
#   - RunCreate.runtime_info_extras: dict | None accepts arbitrary keys (no strict subset).
#   - FoldResult.horizon_bucket_metrics defaults to {}; ModelBacktestResult.bucketed_aggregated_metrics is None when no fold emitted buckets.
#   - HORIZON_BUCKETS in app/features/backtesting/metrics.py = ('h_1_7','h_8_14','h_15_28','h_29_plus').
#   - prophet_like is a feature-aware model (not target-only) — confirms it picks up V2 features.
#   - BacktestRequest has NO `feature_frame_version` field. V2-ness of a backtest comes from `model_config_main.model_type` being feature-aware. DO NOT add a `feature_frame_version` to the backtest request; the INITIAL's phrasing "post with feature_frame_version=2" is shorthand for "pick a feature-aware model_type".
# Output to PRPs/ai_docs/prp-38-contract-probe-report.md. If any verdict is
# ABSENT/DRIFTED, patch the task it gates BEFORE Task 2 starts.

# ─────────────────────────────────────────────────────────────────────────
# R1 — V2 artifact_uri MUST be the full artifacts/models/... path.
# ─────────────────────────────────────────────────────────────────────────
# The existing step_register (pipeline.py:487-586) copies the V1 baseline
# artifact into settings.registry_artifact_root and registers a
# REGISTRY-RELATIVE uri (`demo/{winner}-{stem}.joblib`). That works for V1
# baselines because /forecasting/runs/{id}/feature-metadata is NOT called
# on baseline runs. For V2, the Feature Frame panel calls
# /forecasting/runs/{id}/feature-metadata which loads the bundle via
# forecast_model_artifacts_dir (artifacts/models/...). If the v2_train
# step copies the bundle into the registry root and records a relative
# URI, the metadata endpoint will FAIL.
#
# RULE: step_v2_train sets `artifact_uri = train_response["model_path"]`
# (the absolute or repo-relative `artifacts/models/...` form returned by
# /forecasting/train). DO NOT copy the bundle a second time; DO NOT
# rewrite the path. A unit test asserts the literal prefix and the
# success of a subsequent /forecasting/runs/{id}/feature-metadata call.
# (Optionally also compute + store sha256 of the bundle at its original
# location; the existing step_verify endpoint resolves under the
# registry root, so the SHA must match. If integration breaks for V2
# verify, document it as a known limitation in the runbook and skip the
# verify call for V2 runs — verify stays load-bearing only for V1 baselines.)

# ─────────────────────────────────────────────────────────────────────────
# R2 — use prophet_like (NOT regression) for the V2 Feature Frame demo.
# ─────────────────────────────────────────────────────────────────────────
# `regression` wraps HistGradientBoostingRegressor; sklearn does NOT expose
# `feature_importances_` on HGBR — only on GradientBoostingRegressor. The
# PRP-37 Feature Frame panel surfaces signed coefs / importance rows; with
# `regression`, the importance section renders empty. Use `prophet_like`
# (Ridge → signed coefficients) — its `feature_importances_`-equivalent
# surface populates the panel cleanly.
# Memory anchor: [[histgbr-no-feature-importances]]

# ─────────────────────────────────────────────────────────────────────────
# R7 — frontend type-check command is project-scoped.
# ─────────────────────────────────────────────────────────────────────────
# Use `pnpm tsc --noEmit -p tsconfig.app.json` — NOT bare `pnpm tsc --noEmit`.
# The root `tsconfig.json` has `"files": []` and will pass while the app
# tsconfig still has errors. Prior PRP-37 HANDOFF claimed tsc clean while
# 6 TS errors persisted — root cause was the wrong tsconfig. Re-run for
# every PR; do NOT trust a prior HANDOFF's green check.

# ─────────────────────────────────────────────────────────────────────────
# R8 — module-level asyncio.Lock in app/features/demo/routes.py.
# ─────────────────────────────────────────────────────────────────────────
# Only one demo pipeline runs at a time. A second POST /demo/run returns 409;
# a second WS /demo/stream gets one `error` event. Existing behaviour is
# correct; do NOT widen. The PRP-41 Stop button is the future cancel path.

# ─────────────────────────────────────────────────────────────────────────
# R9 — CRLF/LF noise.
# ─────────────────────────────────────────────────────────────────────────
# Edit/Write on CRLF files produces whole-file noise diffs (memory
# [[repo-line-endings-crlf]]). Run `git diff --stat` before committing;
# if a file shows a whole-file diff, normalise line endings deliberately
# in a separate commit (not in this PRP).

# ─────────────────────────────────────────────────────────────────────────
# Vertical-slice rule (load-bearing for the demo + seeder slices).
# ─────────────────────────────────────────────────────────────────────────
# - app/features/demo/* may import from app.core.* + app.shared.* + standard
#   library only. NEVER `from app.features.<other_slice>.X import ...`.
# - app/features/seeder/* may import from app.core.* + app.shared.* + standard
#   library only. The historical_activity service method MUST NOT drive
#   /registry/runs over httpx.ASGITransport — that would be the demo slice's
#   job. The seeder service persists rows directly via its own async session.
#   Grep guard:
#     git grep -nE "from app\.features\.[^.]+\." app/features/demo/ app/features/seeder/ \
#       | grep -v "from app.features.demo" | grep -v "from app.features.seeder"
#   MUST be empty.

# ─────────────────────────────────────────────────────────────────────────
# Pydantic v2 strict-mode policy on request bodies.
# ─────────────────────────────────────────────────────────────────────────
# Any new request schema with `ConfigDict(strict=True)` MUST use
# `Field(strict=False, ...)` for fields whose JSON wire form has no native
# representation (date, datetime, UUID, Decimal). app/core/tests/test_strict_mode_policy.py
# is the AST invariant test that enforces this. PRP-38's new endpoints:
#   - Phase2EnrichmentRequest: probably has no date fields (the phase-2
#     enrichment runs on the current scenario's date window). If a date
#     field is needed, use `Field(strict=False, ...)`.
#   - HistoricalActivityRequest: very likely has `cutoff_dates: list[date]` —
#     each date MUST be `Field(strict=False, ...)` per the policy.

# ─────────────────────────────────────────────────────────────────────────
# shadcn workflow (per .claude/rules/shadcn-ui.md).
# ─────────────────────────────────────────────────────────────────────────
# - Invoke the `shadcn` skill (and mcp__shadcn__* tools) BEFORE adding any
#   component from the registry.
# - From `frontend/`, NOT repo root: `pnpm dlx shadcn@4.7.0 add accordion`.
# - shadcn 4.x writes `@radix-ui/react-X` per-component imports. shadcn 5.x
#   writes `from 'radix-ui'` (the barrel) — pin 4.7.0 explicitly.
# - Accordion and Select are likely already installed; CONFIRM with the MCP
#   tools / by reading frontend/components.json + listing components/ui/*
#   BEFORE running `add` again.

# ─────────────────────────────────────────────────────────────────────────
# Phase-table lockstep invariant.
# ─────────────────────────────────────────────────────────────────────────
# Backend _phase_table() returns: list[tuple[phase_name, step_name, step_fn]].
# Frontend PHASE_DEFS.ts is a `ReadonlyArray<{ phase: string; step: string;
# label: string }>` whose (phase, step) tuples MUST equal the backend's in
# the same order. Two tests gate this:
#   - app/features/demo/tests/test_pipeline.py::test_phase_table_stable —
#     asserts the (phase_name, step_name) tuple list is frozen.
#   - frontend/src/components/demo/tests/PHASE_DEFS.test.ts — asserts the
#     same list (sourced from a small fixture imported from a generated
#     JSON file, or hand-mirrored with a comment pointing at the backend
#     test's frozen list).
# If a phase or step is added in either tier WITHOUT the other, the
# matching test fails. Both tiers ship in the SAME PRP slice.
```

---

## Implementation Blueprint

### Data models and structure (additive)

```python
# app/features/demo/schemas.py — additive fields (existing fields preserved)

from app.shared.seeder.config import ScenarioPreset

class DemoRunRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    seed: int = Field(default=42, ge=0)
    reset: bool = Field(default=False)
    skip_seed: bool = Field(default=True)
    # PRP-38 — optional scenario picker. Default keeps existing demo_minimal
    # behaviour. Wire-compatible with prior clients that omit the field.
    scenario: ScenarioPreset = Field(
        default=ScenarioPreset.DEMO_MINIMAL,
        description="Seeder scenario for the run.",
    )

class StepEvent(BaseModel):
    event_type: EventType
    step_name: str
    step_index: int
    total_steps: int
    status: StepStatus | None = None
    detail: str = ""
    duration_ms: float = 0.0
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utc_now)
    # PRP-38 — additive phase grouping. Optional + Nullable so legacy clients
    # that don't render phases keep working. Phase index is 1-based.
    phase_name: str | None = Field(default=None)
    phase_index: int | None = Field(default=None, ge=1)
    phase_total: int | None = Field(default=None, ge=1)
```

```python
# app/features/seeder/schemas.py — new request/response shapes
class Phase2EnrichmentRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    seed: int = Field(default=42, ge=0)
    # No date fields → no `Field(strict=False, ...)` needed.

class Phase2EnrichmentResponse(BaseModel):
    records_created: dict[str, int]  # {"lifecycle": N, "replenishment": M, ...}
    duration_ms: float

class HistoricalActivityRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    seed: int = Field(default=42, ge=0)
    n_cutoffs: int = Field(default=3, ge=1, le=12)
    model_types: list[str] = Field(default_factory=lambda: ["naive", "seasonal_naive", "moving_average"])
    # CUTOFF dates may be passed-through; if so, each cutoff is `date` with `Field(strict=False, ...)`.
    cutoffs: list[date] | None = Field(default=None, strict=False)

class HistoricalActivityResponse(BaseModel):
    runs_created: int
    aliases_created: int
    duration_ms: float
```

```python
# app/features/demo/pipeline.py — _step_table() evolves into phase-grouped form

PhaseStep = tuple[str, str, StepFn]  # (phase_name, step_name, fn)

def _phase_table(scenario: ScenarioPreset) -> list[PhaseStep]:
    """Return the ordered phase-grouped step table.

    - For ScenarioPreset.DEMO_MINIMAL (backwards compat) the phases group
      the existing 11 steps without inserting any new step. The flat list
      `_step_table()` (legacy) is now a thin wrapper that drops phase
      names from this list.
    - For ScenarioPreset.SHOWCASE_RICH (PRP-38 preset) phases additionally
      include phase2_enrichment + historical_backfill in `data`, and v2_train
      in `modeling`. The decision phase's `backtest` step targets a
      feature-aware main model (prophet_like) and asks for include_baselines=True
      so PRP-36 bucket metrics populate.
    - For ScenarioPreset.SPARSE the phases group the existing 11 steps;
      no PRP-38 enrichment. (SPARSE is offered in the picker to demonstrate
      edge-case data shapes — not to extend the pipeline.)
    """
    # Default data-phase steps shared by every scenario:
    data_steps = [("precheck", step_precheck), ("reset", step_reset),
                  ("seed", step_seed), ("status", step_status),
                  ("features", step_features)]
    modeling_steps = [("train", step_train)]
    decision_steps = [("backtest", step_backtest), ("register", step_register)]
    verify_steps = [("verify", step_verify)]
    agent_steps = [("agent", step_agent)]
    cleanup_steps = [("cleanup", step_cleanup)]
    if scenario is ScenarioPreset.SHOWCASE_RICH:
        data_steps += [("phase2_enrichment", step_phase2_enrichment),
                       ("historical_backfill", step_historical_backfill)]
        modeling_steps += [("v2_train", step_v2_train)]
    rows: list[PhaseStep] = []
    rows += [("data", name, fn) for name, fn in data_steps]
    rows += [("modeling", name, fn) for name, fn in modeling_steps]
    rows += [("decision", name, fn) for name, fn in decision_steps]
    rows += [("verify", name, fn) for name, fn in verify_steps]
    rows += [("agent", name, fn) for name, fn in agent_steps]
    rows += [("cleanup", name, fn) for name, fn in cleanup_steps]
    return rows

def _step_table() -> list[tuple[str, StepFn]]:
    """Legacy flat-list adapter. Existing callers keep working."""
    return [(name, fn) for _phase, name, fn in _phase_table(ScenarioPreset.DEMO_MINIMAL)]
```

### List of tasks to be completed (dependency-ordered)

```yaml
Task 1 — CONTRACT PROBE (gates every other task):
  - VERIFY presence of every backend field PRP-38 cites:
      a) app/features/forecasting/schemas.py
          - TrainRequest.feature_frame_version (default=1, ge=1, le=2)
          - TrainRequest.feature_groups (list[str] | None)
          - TrainRequest model_validator that rejects V1 + non-None groups (422) and unknown V2 group names (422)
          - TrainResponse.model_path (str, FULL artifacts/models/... path)
      b) app/features/registry/schemas.py
          - RunCreate.runtime_info_extras: dict[str, Any] | None
          - RunResponse.feature_frame_version (computed_field, None for legacy)
          - RunResponse.feature_groups (computed_field, None for legacy)
      c) app/features/backtesting/schemas.py
          - FoldResult.horizon_bucket_metrics: dict[str, dict[str, float]] (default {})
          - ModelBacktestResult.bucketed_aggregated_metrics: dict[str, dict[str, float]] | None (default None)
          - BacktestConfig.include_baselines: bool (default True)
          - CONFIRM BacktestRequest has NO top-level `feature_frame_version` (the INITIAL's wording is shorthand for "use a feature-aware model_type in model_config_main")
      d) app/features/backtesting/metrics.py — HORIZON_BUCKETS = ("h_1_7","h_8_14","h_15_28","h_29_plus")
      e) app/features/forecasting/models.py — prophet_like is feature-aware (not target-only); confirm by looking at the factory branch
      f) app/features/forecasting/schemas.py — FeatureMetadataResponse exposes feature_frame_version + feature_groups + feature_safety_classes
  - VERIFY frontend wire types in `frontend/src/types/api.ts`:
      - DemoRunRequest fields match the backend (add `scenario` Optional)
      - StepEvent fields match (add `phase_name`, `phase_index`, `phase_total` Optional)
  - PRODUCE PRPs/ai_docs/prp-38-contract-probe-report.md with PER-FIELD PRESENT/ABSENT verdict + source file:line. Mirror the structure of `PRPs/ai_docs/prp-37-contract-probe-report.md`.
  - IF any verdict is ABSENT or DRIFTED, STOP. Patch the dependent task block in THIS PRP file before Task 2 starts. Implementer does NOT scaffold against an absent field.

Task 2 — MODIFY app/features/demo/schemas.py [gate:always]:
  - ADD Optional `scenario: ScenarioPreset = ScenarioPreset.DEMO_MINIMAL` on DemoRunRequest. Import `ScenarioPreset` from `app.shared.seeder.config` (NOT from any app.features.<slice> path — `app.shared.*` is allowed).
  - ADD Optional `phase_name: str | None`, `phase_index: int | None`, `phase_total: int | None` on StepEvent. Preserve existing field defaults.
  - DO NOT change `DemoRunResult` (PRP-38 has no scope for that).
  - ADD test: `app/features/demo/tests/test_schemas.py` cases for the new fields (default + override; JSON path via `model_validate({...})` to match FastAPI's validate_python — see test_strict_mode_policy.py precedent).

Task 3 — MODIFY app/shared/seeder/config.py [gate:always]:
  - ADD `SHOWCASE_RICH = "showcase_rich"` to ScenarioPreset (after `DEMO_MINIMAL`).
  - ADD a `from_scenario` branch for `SHOWCASE_RICH`:
      - DimensionConfig(stores=5, products=15)
      - 180-day window anchored to today (mirror DEMO_MINIMAL pattern)
      - TimeSeriesConfig(base_demand=100, trend="linear", trend_slope=0.0005, noise_sigma=0.10) — mirror DEMO_MINIMAL tuning to avoid the NaN-WAPE trap (R10).
      - RetailPatternConfig(promotion_probability=0.15, stockout_probability=0.05)
      - SparsityConfig defaults (no random gaps); sparsity=0.0 implicitly (no SparsityConfig override).
  - ADD `app/shared/seeder/tests/test_phase1_regression.py` invariant for SHOWCASE_RICH: assert a non-NaN backtest WAPE under expanding splits, n_splits=3, horizon=14, min_train_size=30. Mirror the existing DEMO_MINIMAL invariant.

Task 4 — CREATE app/features/seeder/schemas.py additions [gate:always]:
  - ADD Phase2EnrichmentRequest / Response (Pydantic v2; request strict; date fields if any get `Field(strict=False, ...)`).
  - ADD HistoricalActivityRequest / Response. `cutoffs: list[date] | None` MUST use `Field(strict=False, ...)`.
  - ALL request bodies covered by a unit test that calls `Model.model_validate({"…": "iso-string"})` (the FastAPI validate_python path).

Task 5 — CREATE SeederService.phase2_enrichment [gate:always]:
  - PORT logic from scripts/seed_phase2_only.py into `SeederService.phase2_enrichment(seed: int) -> Phase2EnrichmentResponse`.
  - Use `app.shared.seeder.generators.{lifecycle,replenishment,exogenous,returns}.*` directly.
  - Persist rows via the seeder's own AsyncSession.
  - Return counts of rows created per table.
  - WIRE the new endpoint `POST /seeder/phase2-enrichment` in app/features/seeder/routes.py.
  - ROUTE TEST: 2xx happy path on a seeded DB + at least one 4xx error path (e.g., empty DB → RFC 7807 with `title="Empty database"`).

Task 6 — CREATE SeederService.historical_activity [gate:always]:
  - PORT logic from scripts/seed_historical_activity.py into `SeederService.historical_activity(seed: int, n_cutoffs: int, model_types: list[str], cutoffs: list[date] | None) -> HistoricalActivityResponse`.
  - Persist `model_run` rows + alias rows directly via async SQLAlchemy. NEVER drive /registry over httpx.ASGITransport from inside the seeder slice (vertical-slice rule).
  - WIRE `POST /seeder/historical-activity` in app/features/seeder/routes.py.
  - ROUTE TEST: 2xx happy path + 4xx error path.

Task 7 — CREATE frontend/src/components/demo/PHASE_DEFS.ts [gate:always]:
  - EXPORT `PHASE_DEFS = [{phase, step, label}, ...]` matching the backend `_phase_table(ScenarioPreset.DEMO_MINIMAL)` flat order. Augment with `showcase-rich` extension entries gated by a comment block (the frontend ALWAYS exports the full union; the page hides items not present in the streamed run by reading event step_name).
  - LABELS: human-readable per step ("Health check", "Reset database", "Seed demo data", "Inspect dataset", "Compute features", "Phase-2 enrichment", "Historical backfill", "Train models", "Train feature-aware (V2)", "Backtest models", "Register winner", "Verify artifact", "Agent chat", "Cleanup").
  - PHASES (id → label): `data` → "Data", `modeling` → "Modeling", `decision` → "Decision", `verify` → "Verify", `agent` → "Agent", `cleanup` → "Cleanup".
  - ADD test `PHASE_DEFS.test.ts` — asserts the (phase, step) tuple list (DEMO_MINIMAL view) equals a hand-mirrored fixture; if backend `_phase_table` changes, this test fails.

Task 8 — CREATE frontend/src/components/demo/ScenarioPicker.tsx [gate:always]:
  - shadcn `<Select>` with three SelectItems inside a SelectGroup: `demo_minimal` / `showcase_rich` / `sparse`.
  - Props: `value: ScenarioPreset; onChange: (v: ScenarioPreset) => void; disabled?: boolean`.
  - Tooltip per option with a one-line description AND an estimated wall-clock label ("~60 s", "~3 min", "~90 s").
  - ADD test: each option emits onChange; disabled state blocks emission; default selection.

Task 9 — CREATE frontend/src/components/demo/DemoPhasePanel.tsx [gate:always]:
  - shadcn `<Accordion type="single" collapsible value={runningPhase}>` (controlled).
  - Props: `phases: { id: string; label: string; steps: DemoStep[] }[]; runningPhase?: string`.
  - Per-phase trigger: phase label + a small step-count chip (e.g., "5/5"); per-phase content: vertical stack of `<DemoStepCard>` instances.
  - Auto-expand: when `runningPhase` changes, the accordion expands that phase; on `pipeline_complete`, all phases collapse.
  - ADD test: phase grouping renders; running phase auto-expands; idle state renders all phases collapsed.

Task 10 — MODIFY frontend/src/components/demo/demo-step-card.tsx [gate:always]:
  - ADD optional prop `inspectHref?: string | null` — when present AND step.status === 'pass', render a `<Button asChild variant="outline" size="sm">` with `<Link to={inspectHref}>Inspect</Link>` and an icon.
  - For the `backtest` step specifically (step.name === 'backtest'), when `step.data.bucketed_aggregated_metrics` is present render a `<HorizonBucketsMini>` block inline.
  - ADD tests:
      - inspectHref rendering branch (pass + truthy href → button present; pass + null href → absent; non-pass → absent).
      - bucket-mini rendering branch (present → table; absent → null).

Task 11 — CREATE frontend/src/components/demo/HorizonBucketsMini.tsx [gate:always]:
  - Props: `bucketed: Record<string, Record<string, number>>; metric?: 'wape' | 'mae' | 'rmse' | 'bias' | 'smape'` (default 'wape').
  - Renders a small 4-row table using `sortBuckets` + `labelForBucket` from frontend/src/lib/horizon-bucket-utils.ts (already exists from PRP-37). One row per bucket id in canonical order.
  - Empty state: when `bucketed` is empty → "No horizon-bucket metrics available".
  - ADD tests: 4-row render; metric-selector branch; empty state.

Task 12 — MODIFY frontend/src/hooks/use-demo-pipeline.ts [gate:always]:
  - EXTEND `applyEvent` to PROPAGATE `phase_name` from incoming `StepEvent` into the step object (additive — new `phaseName?: string` on `DemoStep`).
  - ADD a derived `phases` map: when steps are folded, group by `phaseName` if present; otherwise fall back to the flat list (legacy `demo_minimal` clients that don't see `phase_name` keep working).
  - EXTEND `STEP_DEFS` to read from `PHASE_DEFS.ts` (single source of truth); preserve backwards compatibility with the flat 11-step layout when scenario === 'demo_minimal'.
  - ADD test cases to use-demo-pipeline.test.ts: phase-aware folding; flat-list fallback; running-phase tracking.

Task 13 — MODIFY frontend/src/pages/showcase.tsx [gate:always]:
  - INSERT `<ScenarioPicker>` above the Run button. Bind to local React state; default `demo_minimal`.
  - REPLACE the flat `steps.map(...)` block with `<DemoPhasePanel phases={derivedPhases} runningPhase={runningPhase} />`.
  - WIRE the per-step Inspect button:
      - `step.name === 'train'`     → `${ROUTES.VISUALIZE.FORECAST}?store_id=${ctx.store_id}&product_id=${ctx.product_id}` (read from step.data when present)
      - `step.name === 'v2_train'`  → `${ROUTES.EXPLORER.RUNS}/${step.data.v2_run_id}` (Feature Frame panel)
      - `step.name === 'register'`  → `${ROUTES.EXPLORER.RUNS}/${step.data.winning_run_id}`
      - `step.name === 'backtest'`  → `${ROUTES.VISUALIZE.BACKTEST}?store_id=${ctx.store_id}&product_id=${ctx.product_id}`
      - default → null (no Inspect button)
  - PRESERVE existing controls (Run button, Re-seed checkbox, Reset checkbox), summary banner, error banner.
  - PRESERVE URL-shareable state (currently `/showcase` has no URL params — keep that constraint; PRP-41 may add `?scenario=...`).

Task 14 — MODIFY app/features/demo/pipeline.py — phase fields on events [gate:always]:
  - EVOLVE `_step_table()` into `_phase_table(scenario)`:
      - Returns `list[PhaseStep]` = `list[tuple[phase_name, step_name, step_fn]]`.
      - `_step_table()` becomes a thin adapter that drops phase names (preserve every existing test).
  - EVOLVE `run_pipeline(app, req)`:
      - Read `req.scenario` (new in DemoRunRequest); compute phase-aware step list.
      - On every yielded `step_start` / `step_complete` event, set `phase_name`, `phase_index` (1-based within the phase, OR 1-based across all phases — pick across-phases for stability; document the choice in a comment), and `phase_total` (total number of distinct phases).
      - On `pipeline_complete`, `phase_name=None`, `phase_index=phase_total` (or omit; the frontend treats it as the run summary).
  - PRESERVE the existing "fail short-circuit" behaviour (any `fail` stops the run after the failing step).
  - ADD `test_phase_table_stable` — assert the (phase_name, step_name) tuple list for each known scenario equals a frozen fixture.

Task 15 — CREATE step_phase2_enrichment + step_historical_backfill + step_v2_train in pipeline.py [gate:always]:
  - `step_phase2_enrichment` — POST /seeder/phase2-enrichment; capture `records_created` into step.data.
  - `step_historical_backfill` — POST /seeder/historical-activity; capture `runs_created` + `aliases_created` into step.data. CRITICAL: discover real store_id/product_id via /dimensions/* before calling (seeder doesn't reset sequences — memory [[seeder-does-not-reset-id-sequences]]).
  - `step_v2_train`:
      a) POST /forecasting/train with `feature_frame_version=2`, `model_type="prophet_like"`, `train_start_date=ctx.date_start`, `train_end_date=ctx.date_end - timedelta(days=DEMO_HORIZON)`.
      b) Capture `train_response["model_path"]` as `v2_model_path` (FULL artifacts/models/... path — R1).
      c) **[PATCHED — see PRPs/ai_docs/prp-38-contract-probe-report.md]** `TrainResponse` does NOT expose V2 metadata (probe verdict: DRIFTED — only `store_id, product_id, model_type, model_path, config_hash, n_observations, train_start_date, train_end_date, duration_ms` are returned). The bundle on disk carries the full V2 manifest (`feature_columns`, `feature_groups`, `feature_safety_classes`), and `GET /forecasting/runs/{v2_run_id}/feature-metadata` loads it. Step (c) is deferred to AFTER step (f): set `runtime_info_extras={"feature_frame_version": 2}` ONLY on RunCreate (Step d); fetch the full manifest from `/feature-metadata` in NEW step (g) and capture it into step.data for the demo card + Inspect link.
      d) POST /registry/runs with `model_type="prophet_like"`, `model_config`, `data_window_start`/`end`, `runtime_info_extras={"feature_frame_version": 2}`. (V=2 is the minimum needed for `RunResponse.feature_frame_version` to compute V=2; the bundle is the source of truth for columns/groups/safety classes and the Feature Frame panel reads it via `/feature-metadata`.) Capture `run_id` as `v2_run_id` in ctx.
      e) PATCH /registry/runs/{v2_run_id} pending → running.
      f) PATCH /registry/runs/{v2_run_id} running → success with `artifact_uri=v2_model_path` (FULL path — DO NOT copy into registry root), `artifact_hash=<sha256-of-bundle>`, `artifact_size_bytes=<file size>`.
      g) **[NEW — PATCH]** GET /forecasting/runs/{v2_run_id}/feature-metadata. Capture `feature_columns` (list[str]), `feature_groups` (dict[str, list[str]] | None), `feature_safety_classes` (dict[str, str] | None). On a non-200 (e.g., legacy bundle without V2 metadata) log + carry the empty defaults — DO NOT fail the step; the V=2 badge still renders from `RunResponse.feature_frame_version`.
      h) Emit `step.data = {"v2_run_id": ..., "feature_frame_version": 2, "model_type": "prophet_like", "feature_columns_count": len(feature_columns), "feature_groups": list(feature_groups or {}), "artifact_uri_full": v2_model_path}`.
  - ADD tests: `test_v2_train_step` asserts (i) the registered `artifact_uri` literal equals `train_response["model_path"]` (R1 — same string, no rewriting), (ii) `runtime_info["feature_frame_version"] == 2` (via RunResponse computed_field), (iii) the post-success `GET /…/feature-metadata` call returns a 200 with `feature_frame_version=2`, (iv) step.data exposes `feature_columns_count >= 1`. `test_phase2_enrichment_step` and `test_historical_backfill_step` assert at least one row written.

Task 16 — EVOLVE step_backtest for feature-aware + buckets [gate:always]:
  - ON ScenarioPreset.SHOWCASE_RICH: change main-model `model_config` from the loop-of-3-baselines into ONE call with `model_type="prophet_like"`, `include_baselines=true`, and `store_fold_details=false`. (Baselines come back in `baseline_results`; the winner-selection logic uses the per-model WAPE in `baseline_results[i].aggregated_metrics["wape"]` + `main_model_results.aggregated_metrics["wape"]`.)
  - CAPTURE `main_model_results.bucketed_aggregated_metrics` (PRP-36 — may be None when the horizon=14 covers only h_1_7 + h_8_14 buckets; that is acceptable) into step.data.
  - PRESERVE the ScenarioPreset.DEMO_MINIMAL behaviour (3-baselines loop) for backwards compat.
  - ADD `test_backtest_buckets_populated` on ScenarioPreset.SHOWCASE_RICH — assert at least h_1_7 and h_8_14 keys present.

Task 17 — EXTEND tests/test_e2e_demo.py [gate:always]:
  - ADD `test_e2e_showcase_rich` (@pytest.mark.integration):
      - POST /demo/run with `scenario=showcase_rich`, `reset=True`, `skip_seed=False`.
      - Soft-warn on wall-clock > 240 s; hard-fail on > 300 s.
      - Assert at least one V2 run registered (query /registry/runs with `?feature_frame_version=2` if backend supports the filter, else parse the runs list and look for V=2 in computed_field).
      - Assert `bucketed_aggregated_metrics` non-empty on the backtest event.
      - Assert pipeline overall_status === 'pass'.
  - PRESERVE `test_e2e_demo` (the existing demo_minimal happy path); soft-warn budget unchanged at 180 s.

Task 18 — DOC UPDATE [gate:always]:
  - APPEND to `docs/_base/RUNBOOKS.md` § "Showcase page (`/showcase`) pipeline fails at step X":
      - `phase2_enrichment` failure modes (empty DB, missing scenario, slow generator).
      - `historical_backfill` failure modes (missing dimensions, n_cutoffs too large for the data window).
      - `v2_train` failure modes (registry registration with relative URI breaks /feature-metadata — R1; HGBR no importances — R2; PRP-37 Feature Frame panel renders empty).
  - APPEND to `docs/_base/API_CONTRACTS.md` Slice table: 2 new seeder endpoints (`/seeder/phase2-enrichment`, `/seeder/historical-activity`) — additively, mirroring the existing seeder row.
  - DO NOT update `docs/user-guide/showcase-walkthrough.md` (that doc is PRP-41's scope per the umbrella + index).

Task 19 — DOGFOOD (per memory [[playwright-dogfood-snap-chromium]]) [gate:always]:
  - Pre-flight: `ps -ef | grep '[u]vicorn'` to confirm the current-session backend on :8123 (memory [[dogfood-stale-uvicorn-port-8123]]).
  - Start servers per AGENTS.md Setup; use `./node_modules/.bin/vite --host 0.0.0.0` from frontend/ per CLAUDE.local.md WSL workaround.
  - Manual flow (capture screenshots):
      a) Open /showcase → confirm 6 phase cards in idle state.
      b) Pick `showcase-rich` → click Run → confirm phase auto-expand + ≤ 240 s wall-clock.
      c) After completion: navigate /explorer/runs → confirm a V=2 prophet_like run is listed.
      d) Open the V2 run detail page → confirm Feature Frame panel renders V=2 badge + populated coefs (R1 + R2 sanity).
      e) Open /visualize/backtest for the showcase store/product → confirm horizon-bucket card populated.
      f) Use Inspect buttons on `train`, `v2_train`, `register`, `backtest` step cards → each navigates to a populated page.
  - Attach screenshots to the PR.

Task 20 — VALIDATION GATES [gate:always]:
  - Backend:
      uv run ruff check . && uv run ruff format --check .
      uv run mypy app/
      uv run pyright app/
      uv run pytest -v -m "not integration"
      uv run pytest -v -m integration              # MUST include the new showcase-rich test
  - Frontend (from frontend/):
      pnpm lint
      pnpm tsc --noEmit -p tsconfig.app.json       # NOT bare tsc — see R7
      pnpm test --run
  - Grep guards:
      grep -rn "from 'radix-ui'" frontend/src      # MUST be empty
      grep -rn 'from "radix-ui"' frontend/src      # MUST be empty
      git grep -nE "from app\.features\.[^.]+\." app/features/demo/ app/features/seeder/ | grep -v "from app.features.demo" | grep -v "from app.features.seeder"   # MUST be empty (vertical-slice rule)
  - git diff --check                               # zero whitespace errors
```

### Per task pseudocode (the load-bearing parts)

```python
# Task 15 — step_v2_train (the R1-critical path)

async def step_v2_train(ctx: DemoContext, client: _Client) -> StepResult:
    """Train ONE V2 prophet_like model and register with full artifacts/models path."""
    if ctx.date_start is None or ctx.date_end is None:
        return ("fail", "no date range on ctx", {})
    train_start = ctx.date_start
    train_end = ctx.date_end - timedelta(days=DEMO_HORIZON)

    # (a) POST /forecasting/train — V2 + prophet_like + default V2 groups.
    train_body = await client.request(
        "v2_train[train]",
        "POST",
        "/forecasting/train",
        json_body={
            "store_id": ctx.store_id,
            "product_id": ctx.product_id,
            "train_start_date": train_start.isoformat(),
            "train_end_date": train_end.isoformat(),
            "config": {"model_type": "prophet_like"},   # ProphetLikeConfig
            "feature_frame_version": 2,
            # feature_groups: omit → backend uses DEFAULT_V2_GROUPS.
        },
    )

    # (b) Capture the FULL artifacts/models/... path — R1.
    v2_model_path = train_body["model_path"]            # str — full path from forecast_model_artifacts_dir
    # The path is either "./artifacts/models/model_<id>" (repo-relative) or
    # the resolved absolute form. Either way it MUST contain artifacts/models/
    # so load_model_bundle's base_dir check succeeds.
    assert "artifacts/models/" in v2_model_path

    # (c) [PATCHED — see PRPs/ai_docs/prp-38-contract-probe-report.md]
    # TrainResponse does NOT carry V2 metadata. The bundle on disk does.
    # Defer the metadata pull to NEW step (g), AFTER the success patch.

    # Hash + size the bundle in-place (no copy — R1).
    bundle_path = Path(v2_model_path).resolve()
    artifact_bytes = bundle_path.read_bytes()
    artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
    artifact_size = len(artifact_bytes)

    # (d) POST /registry/runs (PENDING). runtime_info_extras carries the
    # minimum needed for RunResponse.feature_frame_version to compute V=2;
    # the bundle is the source of truth for columns/groups/safety classes.
    create_body = await client.request(
        "v2_train[create]",
        "POST",
        "/registry/runs",
        json_body={
            "model_type": "prophet_like",
            "model_config": {"model_type": "prophet_like"},
            "feature_config": None,
            "data_window_start": ctx.date_start.isoformat(),
            "data_window_end": ctx.date_end.isoformat(),
            "store_id": ctx.store_id,
            "product_id": ctx.product_id,
            "runtime_info_extras": {"feature_frame_version": 2},
        },
    )
    v2_run_id = create_body["run_id"]

    # (e) PATCH pending → running.
    await client.request(
        "v2_train[running]", "PATCH",
        f"/registry/runs/{v2_run_id}",
        json_body={"status": "running"},
    )

    # (f) PATCH running → success — artifact_uri is the FULL path (R1).
    await client.request(
        "v2_train[success]", "PATCH",
        f"/registry/runs/{v2_run_id}",
        json_body={
            "status": "success",
            "metrics": {},                              # backtest metrics not in scope here
            "artifact_uri": v2_model_path,              # R1 — FULL artifacts/models/... path
            "artifact_hash": artifact_hash,
            "artifact_size_bytes": artifact_size,
        },
    )

    # (g) [NEW — PATCH] Fetch the full V2 manifest from the bundle via the
    # feature-metadata endpoint. Failure is non-fatal — the V=2 badge still
    # renders from RunResponse.feature_frame_version computed_field.
    feature_columns: list[str] = []
    feature_groups: dict[str, list[str]] = {}
    feature_safety: dict[str, str] = {}
    try:
        metadata_body = await client.request(
            "v2_train[feature-metadata]", "GET",
            f"/forecasting/runs/{v2_run_id}/feature-metadata",
        )
        feature_columns = list(metadata_body.get("feature_columns") or [])
        feature_groups = dict(metadata_body.get("feature_groups") or {})
        feature_safety = dict(metadata_body.get("feature_safety_classes") or {})
    except Exception as exc:  # noqa: BLE001 — non-fatal enrichment
        logger.warning("v2_train.feature_metadata_failed", run_id=v2_run_id, error=str(exc))

    return (
        "pass",
        f"V2 prophet_like registered run_id={v2_run_id[:8]}... cols={len(feature_columns)}",
        {
            "v2_run_id": v2_run_id,
            "feature_frame_version": 2,
            "model_type": "prophet_like",
            "feature_columns_count": len(feature_columns),
            "feature_groups": list(feature_groups),
            "artifact_uri_full": v2_model_path,
        },
    )
```

```python
# Task 14 — phase fields on every event

async def run_pipeline(app: FastAPI, req: DemoRunRequest) -> AsyncIterator[StepEvent]:
    rows = _phase_table(req.scenario)
    total_steps = len(rows)
    phases_in_order = list(dict.fromkeys(phase for phase, _name, _fn in rows))
    phase_total = len(phases_in_order)
    phase_index_by_phase = {p: i + 1 for i, p in enumerate(phases_in_order)}

    async with _Client(app) as client:
        for index, (phase_name, step_name, fn) in enumerate(rows, start=1):
            yield StepEvent(
                event_type="step_start",
                step_name=step_name,
                step_index=index,
                total_steps=total_steps,
                phase_name=phase_name,
                phase_index=phase_index_by_phase[phase_name],
                phase_total=phase_total,
            )
            # … existing try/except wrapping fn(ctx, client) …
            yield StepEvent(
                event_type="step_complete",
                step_name=step_name,
                step_index=index,
                total_steps=total_steps,
                status=status,
                detail=detail,
                data=data,
                duration_ms=duration_ms,
                phase_name=phase_name,
                phase_index=phase_index_by_phase[phase_name],
                phase_total=phase_total,
            )
            if status == "fail":
                break
        yield StepEvent(
            event_type="pipeline_complete",
            step_name="summary",
            step_index=total_steps,
            total_steps=total_steps,
            status="fail" if any_fail else "pass",
            detail=f"runs={len(ctx.backtest_results)} winner={ctx.winner_model_type} wall={wall:.0f}s",
            data={"winner_model_type": ctx.winner_model_type, "winner_wape": ctx.winner_wape,
                  "winning_run_id": ctx.winning_run_id, "alias": DEMO_ALIAS, "wall_clock_s": wall,
                  "v2_run_id": ctx.v2_run_id},   # NEW — exposed for the Inspect deep link
            # No phase_name on summary — it's the run total.
        )
```

```typescript
// Task 12 — use-demo-pipeline.ts (phase-aware extension)

export interface DemoStep {
  name: string
  label: string
  status: DemoStepUiStatus
  detail: string
  durationMs: number
  data: Record<string, unknown>
  phaseName?: string        // PRP-38 — set when event carries phase_name; absent on legacy events.
}

// In applyEvent's step_start branch:
const steps = state.steps.map((step) =>
  step.name === event.step_name
    ? { ...step, status: 'running' as const, phaseName: event.phase_name ?? step.phaseName }
    : step
)

// New derived selector — group by phase when phaseName is present.
export function derivePhases(steps: DemoStep[]): { id: string; label: string; steps: DemoStep[] }[] {
  // If any step has a phaseName, group; otherwise fallthrough to a single 'all' bucket.
  const hasPhases = steps.some((s) => !!s.phaseName)
  if (!hasPhases) return [{ id: 'all', label: 'Pipeline', steps }]
  const phasesInOrder: string[] = []
  const byPhase = new Map<string, DemoStep[]>()
  for (const s of steps) {
    const p = s.phaseName ?? 'unknown'
    if (!byPhase.has(p)) { phasesInOrder.push(p); byPhase.set(p, []) }
    byPhase.get(p)!.push(s)
  }
  return phasesInOrder.map((id) => ({
    id, label: PHASE_LABEL[id] ?? id, steps: byPhase.get(id) ?? [],
  }))
}
```

### Integration Points

```yaml
DATABASE:
  - No migrations. The seeder slice writes to existing tables
    (`lifecycle`, `replenishment_event`, `exogenous_signal`, `returns`,
    `model_run`, `run_alias`) — all already covered by prior PRPs.

CONFIG:
  - No new VITE_* env vars. No new app settings.

ROUTES:
  - Add 2 new seeder endpoints in app/features/seeder/routes.py.
  - No new top-level slice. The existing seeder router is included by
    app/main.py; no main.py change required.

FRONTEND ROUTES:
  - No new pages, no new route entries.

CHANGELOG:
  - Under "Unreleased":
    `feat(api,ui): showcase pipeline — richer data + V1/V2 modeling foundation (#<issue>)`.

ISSUE:
  - Open `feat(api,ui): showcase pipeline — richer data + V1/V2 modeling foundation` and
    capture the issue number `<N>` BEFORE the first commit (every commit references it).
```

---

## Validation Loop

### Level 1: Syntax + style + types (backend)

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/                         # --strict via pyproject.toml
uv run pyright app/                      # --strict
# Expected: zero errors. Do NOT silence via type: ignore. Fix the cause.
```

### Level 2: Backend unit + integration tests

```bash
uv run pytest -v -m "not integration"    # fast, no DB
# Expected: every new test green; the legacy demo_minimal test stays green.

docker compose up -d
uv run pytest -v -m integration          # requires Postgres on :5433
# Includes the new test_e2e_showcase_rich integration test.
```

### Level 3: Frontend lint + types + tests

```bash
cd frontend
pnpm lint
pnpm tsc --noEmit -p tsconfig.app.json   # R7 — NOT bare tsc
pnpm test --run

# shadcn import guards
grep -rn "from 'radix-ui'" src && echo "FAIL: barrel import" && exit 1
grep -rn 'from "radix-ui"' src && echo "FAIL: barrel import" && exit 1
echo "OK: per-component imports only"
```

### Level 4: Vertical-slice grep guard

```bash
# Demo slice may only import from app.core.*, app.shared.*, stdlib, third-party.
git grep -nE "from app\.features\.[^.]+\." app/features/demo/ \
  | grep -v "from app.features.demo" \
  && echo "FAIL: cross-slice import" && exit 1
# Seeder slice may only import from app.core.*, app.shared.*, stdlib, third-party.
git grep -nE "from app\.features\.[^.]+\." app/features/seeder/ \
  | grep -v "from app.features.seeder" \
  && echo "FAIL: cross-slice import" && exit 1
echo "OK: vertical-slice rule preserved"
```

### Level 5: Dogfood the running UI

```bash
# Pre-flight (memory dogfood-stale-uvicorn-port-8123)
ps -ef | grep '[u]vicorn'                # confirm current-session backend
curl -s http://localhost:8123/health     # {"status":"ok"}

# Start frontend (CLAUDE.local.md WSL workaround)
cd frontend && ./node_modules/.bin/vite --host 0.0.0.0

# Use the webapp-testing skill OR native Python Playwright
#   (executable_path=/snap/bin/chromium per memory playwright-dogfood-snap-chromium)
# to exercise the Task-19 manual flow. Attach screenshots to the PR.
```

---

## Final validation Checklist

> **GATE FIRST:** Task 1 produced `PRPs/ai_docs/prp-38-contract-probe-report.md`
> with every cited backend field marked PRESENT. Any ABSENT verdict patched in
> THIS PRP before Task 2 starts.

- [ ] Task 1 (Contract Probe) report committed at `PRPs/ai_docs/prp-38-contract-probe-report.md`.
- [ ] Every Optional field added to `app/features/demo/schemas.py` and `frontend/src/types/api.ts` corresponds to a present backend / wire-level field per Task 1.
- [ ] `_phase_table()` returns 11 entries for ScenarioPreset.DEMO_MINIMAL and 14 entries for ScenarioPreset.SHOWCASE_RICH (count subject to Task 1's confirmed step set).
- [ ] `test_phase_table_stable` (backend) + `PHASE_DEFS.test.ts` (frontend) both green; the (phase, step) tuple lists match.
- [ ] `/seeder/phase2-enrichment` happy + error route tests green.
- [ ] `/seeder/historical-activity` happy + error route tests green.
- [ ] `ScenarioPreset.SHOWCASE_RICH` regression test green (non-NaN backtest WAPE invariant).
- [ ] `step_v2_train`:
  - [ ] Sets `artifact_uri = train_response["model_path"]` (FULL artifacts/models/... path — R1).
  - [ ] Writes `runtime_info_extras={"feature_frame_version": 2, ...}`.
  - [ ] Unit test asserts both fields.
- [ ] `step_backtest` on SHOWCASE_RICH posts `include_baselines=true` with a feature-aware `model_config_main`; response's `main_model_results.bucketed_aggregated_metrics` non-empty AND echoed into step.data.
- [ ] Bucket keys subset against `app.features.backtesting.metrics.HORIZON_BUCKETS` (at minimum: `h_1_7`, `h_8_14`).
- [ ] `/showcase` default (no scenario change) still runs in ≤ 90 s; existing `tests/test_e2e_demo.py` green.
- [ ] `/showcase` with `scenario=showcase_rich` finishes ≤ 240 s wall-clock soft-warn / ≤ 300 s hard-fail.
- [ ] Phase accordion auto-expands the currently-running phase; idle state renders all collapsed.
- [ ] Per-step Inspect button: present on terminal `pass` cards with payload; absent otherwise. Vitest covers both branches.
- [ ] `/explorer/runs/{v2_run_id}` Feature Frame panel renders V=2 + populated columns + signed Ridge coefficients (dogfood screenshot in PR).
- [ ] `/visualize/backtest` for the showcase grain renders the horizon-bucket card with populated metrics (dogfood screenshot in PR).
- [ ] All five validation gates green: ruff + ruff format + mypy + pyright + pytest (unit + integration) + migration-check.
- [ ] `pnpm lint && pnpm tsc --noEmit -p tsconfig.app.json && pnpm test --run` green.
- [ ] No `from 'radix-ui'` barrel imports introduced (grep guard).
- [ ] Vertical-slice grep guard empty for `app/features/demo/` and `app/features/seeder/`.
- [ ] `git diff --check` exit 0 (no whitespace errors).
- [ ] CHANGELOG entry under "Unreleased" lands with the issue reference.
- [ ] Dogfood screenshots attached to the PR (Task 19).

---

## Unresolved Contract Assumptions

These items are verified by Task 1 (Contract Probe). If verification fails
for an item, the corresponding task is PATCHED in this PRP before Task 2
starts — implementer marks the task `DEFERRED — pending {field}` and stops
to re-plan.

1. `TrainResponse` exposes `feature_columns` + `feature_groups` +
   `feature_safety_classes` directly (or via a sibling
   `GET /forecasting/runs/{id}/feature-metadata` call after train). Task 1
   confirms WHICH source the v2_train step reads. If neither path
   yields the V2 manifest, the registry's `runtime_info_extras` carries
   `feature_frame_version: 2` only (the Feature Frame panel falls back to
   "V=2, manifest unavailable").
2. `BacktestRequest` does NOT have a top-level `feature_frame_version`
   field — the V2-ness of a backtest comes from a feature-aware
   `model_config_main.model_type` (`prophet_like` / `regression` / ...).
   Task 1 confirms and PATCHES this PRP's wording if the schema has
   changed in the interim.
3. `prophet_like` is a feature-aware family (not target-only) — confirms
   it picks up the V2 features the train step computes. Task 1 verifies
   via `app/features/forecasting/models.py` factory + `_MODEL_FAMILY_MAP`.
4. `RunCreate.runtime_info_extras` accepts arbitrary keys including
   `feature_columns`, `feature_groups`, `feature_safety_classes` (already
   used by PRP-35). Task 1 verifies via `app/features/registry/schemas.py`.
5. `ModelBacktestResult.bucketed_aggregated_metrics` is `None` when no
   fold emitted bucket data (horizon=14 + n_splits=3 yields at minimum
   h_1_7 + h_8_14; h_15_28 + h_29_plus may be missing). The acceptance
   criterion accepts a 2-bucket result as valid.
6. `/forecasting/runs/{id}/feature-metadata` resolves bundles under
   `forecast_model_artifacts_dir` (R1). Task 1 verifies by reading
   `app/features/forecasting/persistence.py` (or wherever the loader
   lives) and confirming the resolution rule.

---

## Anti-Patterns to Avoid

- ❌ Don't import from another `app/features/*` slice inside
  `app/features/demo/` or `app/features/seeder/`. Use the new
  `/seeder/*` endpoints + `httpx.ASGITransport` instead.
- ❌ Don't copy the V2 bundle into the registry artifact root and
  register a registry-relative URI (R1). The full `artifacts/models/...`
  path is the contract for V2.
- ❌ Don't use `regression` for the V2 Feature Frame demo (R2). The
  Feature Frame panel's importance section renders empty for HGBR; use
  `prophet_like`.
- ❌ Don't change any existing field on `StepEvent` or `DemoRunRequest`.
  All new fields are Optional with defaults.
- ❌ Don't bump a major version of pydantic-ai / FastAPI / SQLAlchemy.
  This PRP is purely additive at the framework level.
- ❌ Don't fabricate a V2 run if the train call fails or the backend
  ABSENT-flags V2. The step emits `skip` with a clear reason; PRP-39's
  champion-compat would then DEFER on the V2 run absence.
- ❌ Don't run `pnpm tsc --noEmit` against the root tsconfig (R7). Use
  `-p tsconfig.app.json` explicitly.
- ❌ Don't introduce a Stop button, run history strip, agent HITL flow,
  scenario simulate/save/compare, ops snapshot panel, batch preset/matrix,
  RAG indexing, or champion-compat compare in PRP-38 (out of scope —
  belong to PRP-39 / PRP-40 / PRP-41).
- ❌ Don't widen the agent's `agent_require_approval` config. PRP-38
  does not touch the agent layer at all.
- ❌ Don't introduce a new Alembic migration. PRP-38 has no schema
  changes.
- ❌ Don't bypass the shadcn workflow. Run `mcp__shadcn__get_audit_checklist`
  after every install.
- ❌ Don't trust a prior HANDOFF's "tsc clean" claim — re-run the
  project-scoped type-check yourself.
- ❌ Don't trust `:8123` without `ps -ef | grep uvicorn` (memory
  [[dogfood-stale-uvicorn-port-8123]]).

---

## Confidence

**Confidence: 7.5/10** for one-pass implementation success.

What grounds the 7.5:

- PRP-38 scope is intentionally narrow — phase grouping + one V2 run +
  bucket-visible backtest + Inspect links. The scope explicitly excludes
  the multi-run decision surfaces, scenario library, RAG, agent HITL, and
  the polish layer.
- Every cited backend contract exists on `dev` today (PRP-35 + PRP-36 +
  PRP-37 all merged); the Task-1 probe is a verify-existing-fields pass,
  not a discovery exercise.
- The vertical-slice rule is the highest-blast-radius constraint; the
  grep guards in Level 4 catch a violation deterministically.
- The phase-table lockstep invariant is enforced by two tests (one
  per tier).
- R1 + R2 are pinned in the pseudocode for the v2_train step.
- The two new `/seeder/*` endpoints are port-only — the underlying logic
  already exists in the CLI scripts; service-method extraction is
  mechanical.
- demo_minimal back-compat is a hard test (existing `tests/test_e2e_demo.py`
  + the budget-soft-warn pattern).

What costs the 2.5 points:

- The seeder slice has not previously hosted endpoints that drive
  cross-slice persistence (e.g., the historical_activity method writes
  `model_run` + `run_alias` rows directly). Verifying this stays
  semantically faithful to the CLI script — without driving the registry
  over ASGI — is the highest implementation risk. Mitigation: the CLI
  scripts are short (~200 LOC each); the service method is a straight
  port at the SQLAlchemy layer.
- The exact V2 bundle metadata (columns / groups / safety classes) surface
  needs Task-1 confirmation — `TrainResponse` may or may not expose them
  directly; the fallback is `GET /forecasting/runs/{id}/feature-metadata`
  but PRP-38 should NOT introduce a new round-trip just to populate
  `runtime_info_extras` if the train response already carries the data.
- shadcn 4.7.0 vs already-installed components: Accordion + Select are
  almost certainly present, but a stale lockfile (or shadcn 5.x drift
  introduced by a prior session) could quietly skip an install.
  Mitigation: invoke `mcp__shadcn__list_items_in_registries` + audit
  checklist before any `add` command.
- The `/showcase` page is the single visible artefact of this PRP;
  a regression that breaks the demo_minimal back-compat path is high-cost.
  Mitigation: the legacy `_step_table()` adapter + the existing
  `tests/test_e2e_demo.py` pass through unchanged are the load-bearing
  back-compat tests.
