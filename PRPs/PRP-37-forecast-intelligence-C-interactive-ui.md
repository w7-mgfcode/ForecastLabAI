name: "PRP-37 — Forecast Intelligence C: Interactive UI + Operator Workflow"
description: |
  Make the Forecast Intelligence A/B backend additions usable by planners
  and operators through the React SPA — model-family + feature-frame
  selectors, feature-pack toggles, per-horizon-bucket comparison surfaces,
  champion/challenger safety affordances, and an explainability layer that
  honours every backend caveat (HGBR-unavailable, stockout warning, V1-vs-V2
  alias mismatch). Slice C of the Forecast Intelligence roadmap
  (`PRPs/INITIAL/INITIAL-forecast-intelligence-index.md`).

  > **PREREQUISITES — HARD DEPENDENCY ON PRP-35 AND PRP-36.**
  >
  > This PRP MUST NOT introduce UI affordances for backend fields that have
  > not yet landed. Task 1 (Contract Probe) is the gate: it runs against the
  > live backend (or `app/features/**/schemas.py`) and produces the EXACT
  > field-name list this PRP wires UI to. If a cited PRP-35 / PRP-36 field
  > is absent, the corresponding UI task is DEFERRED — not implemented with
  > a placeholder, not faked. The INITIAL is explicit: "Do not fake backend
  > values in the UI." This PRP honours that as a hard rule.
  >
  > **Partial-execution mode is supported.** If PRP-35 is merged but PRP-36
  > is not, Tasks tagged `[gate:PRP-35]` ship; tasks tagged `[gate:PRP-36]`
  > are deferred to a follow-up PR. If neither is merged, only the
  > existing-fields refinements ship (segmented-control polish, table
  > refinements, stockout caveats from existing reason_codes).

## Purpose
A one-pass implementation contract for an AI agent (or human) with access
to the codebase but no prior session context. Land an operator-grade UI
that surfaces the backend semantics PRP-35 + PRP-36 add — feature_frame_version,
feature_groups, per-horizon-bucket metrics, comparable-run version
mismatch, RandomForest feature importances — without inventing values
that don't exist server-side and without bypassing the project's shadcn
component workflow.

## Core Principles
1. **Backend contracts are read-only.** Every visible value originates from
   a backend field. The UI NEVER fabricates a feature_frame_version,
   NEVER invents a feature_group, NEVER displays a metric that the backend
   did not return.
2. **shadcn workflow is the only path.** Per `.claude/rules/shadcn-ui.md`:
   every shadcn component arrives through `pnpm dlx shadcn@4.7.0 …` AND
   the `shadcn` skill / MCP. No raw GitHub fetches. Per memory
   `radix-ui-vs-per-component-imports`: per-component
   `@radix-ui/react-X` imports, never the `radix-ui` barrel. Per memory
   `shadcn-cli-version-pin`: pin shadcn@4.7.0 (NOT 5.x — 5.x silently
   writes a stub `pnpm-workspace.yaml` and skips the component).
3. **Dense, operator-grade UI.** Not a landing page. The first screen is
   the working tool. shadcn controls only — Tabs (used as segmented
   controls), Select, Checkbox/Toggle, Slider, Dialog/AlertDialog, Tooltip,
   DataTable, Recharts.
4. **URL-shareable state.** Every filter / sort / page parameter flows
   through `frontend/src/lib/url-params.ts` (existing). New
   model-family / feature-frame-version / feature-groups state goes the
   same route, parsed with the project's validation-at-read helpers.
5. **TypeScript strict + Vitest green.** `pnpm tsc --noEmit` + `pnpm lint` +
   `pnpm test --run` are merge gates. Every conditional rendering branch
   (missing feature_frame_version, no feature importances, stale-alias
   with worse latest WAPE, artifact-verification failure, HGBR-unsupported
   path) gets a test.
6. **No agent mutation surface widening.** This PRP touches the UI only;
   `agent_require_approval` is unchanged. If a future PRP adds a
   "Promote to alias via agent" tool, that's a separate scope.
7. **No backend logic.** Model classes, metric formulas, registry
   comparability rules — all live in PRP-35 / PRP-36. This PRP consumes
   them as JSON and renders them.

---

## Goal

Deliver, on branch `feat/forecast-ui-interactive-workflow`, an interactive
operator UI that exposes every backend capability PRP-35 + PRP-36 add:

- **Forecast training control surface** — segmented model-family picker
  (Tabs styled as segmented), model-type Select that toggles by family,
  V1/V2 feature-frame Select, conditional FeatureGroup multi-select
  toggle group, conservative defaults.
- **Backtest comparison surface** — multi-model fold comparison on
  identical splits, metric cards (MAE / sMAPE / WAPE / bias / RMSE),
  horizon-bucket metric table, "best WAPE / lowest bias" badges,
  "stale alias / degrading / stockout-constrained / feature-aware /
  baseline" badges, "newer-vs-better" callout.
- **Run detail + run-compare** — feature_frame_version + feature_groups
  panel; top feature importances or additive components; artifact hash
  verification badge; "comparable with current champion?" indicator.
- **What-if planner** — quick-vary sliders (price delta, promotion,
  holiday, inventory, lifecycle), side-by-side baseline-vs-scenario
  chart, "model_exogenous vs heuristic" method label,
  known-future-input vs hypothetical labelling.
- **Ops control center** — degrading-status explainability (latest
  WAPE, previous comparable WAPE, delta, n_comparable_runs, data-window
  freshness); safer Promote (AlertDialog with worse-WAPE confirm + artifact
  verify + champion/challenger comparison + stale-reason).
- **Batch sweeps** — multi-model + multi-feature-pack submission;
  presets (quick baseline sweep / feature-aware comparison / champion-
  challenger refresh / stockout-sensitive products / high-WAPE recovery);
  PRP-34 parallel-execution controls preserved.
- **Agent/RAG affordances** — copyable context buttons ("Explain why this
  model degraded", "Summarize champion vs challenger", "Recommend next
  backtest") that pipe into the existing /chat flow. RAG continues to
  cite user-guide docs; no new agent tool.

## Why

Without this PRP, the backend gains a model zoo + V2 features + per-horizon
metrics + feature_frame_version comparability rules — and operators see
none of it through the dashboard. They can't:

- choose between same-grain models on identical folds without writing curl;
- distinguish a V1 alias from a V2 challenger (silent drift);
- read the stockout caveat that the backend already emits in reason codes;
- avoid promoting a newer-but-worse run.

Slice C is the operator surface that makes the A/B work usable.

## What

### User-visible behaviour

- `/visualize/forecast`: New control row — Tabs (Baseline / Tree /
  Additive) → Select (model type, filtered by family) → Select
  (Feature frame V1 / V2 — disabled+tooltip when backend does not
  expose the field yet) → conditional Toggle group of feature packs
  (only when V2 is selected AND backend exposes feature_groups).
  Default selections are conservative: family=Baseline,
  model_type=seasonal_naive, feature_frame=V1.
- `/visualize/backtest`: New per-horizon-bucket metric table beneath
  the existing fold-metric chart, when `bucketed_aggregate_metrics`
  is present in the response. New RMSE column when
  `aggregate_metrics.rmse` is present. New baseline-vs-feature-aware
  comparison view when `baseline_results` is non-empty AND
  `comparison_summary` is populated.
- `/visualize/planner`: New "method" badge (`model_exogenous` |
  `heuristic`) next to the run-id picker; "known future input" vs
  "hypothetical" pill on each assumption row; baseline-vs-scenario
  multi-series chart already exists — extended to label units delta +
  revenue delta inline.
- `/explorer/run-detail`: New "Feature frame" panel showing
  feature_frame_version + feature_groups when present; the panel
  collapses gracefully (empty state) for pre-PRP-35 runs.
- `/explorer/run-compare`: New "Feature frame version" comparison row
  in the metrics table; "Champion compatibility" badge that surfaces
  the comparable-run rule's verdict (same grain + overlapping window +
  same V).
- `/ops`: Stale-alias panel adds a `feature_frame_version_mismatch`
  reason chip; degrading-status row exposes
  `latest_wape / previous_wape / wape_delta / n_comparable_runs /
  last_trained_at / staleness_days` (already in `ModelHealthEntry` —
  this PRP surfaces them).
- `/visualize/batch`: Adds preset Select (5 presets) and a multi-model
  multi-feature-pack matrix picker for batch sweeps.
- Every chat page: a "Use this context" copy button on the relevant
  panels (run-detail, ops health card) that pre-fills the chat input
  with a structured prompt; no new agent tool.

### Technical requirements

- TypeScript 5.9 strict — `pnpm tsc --noEmit` clean.
- ESLint clean — `pnpm lint` clean.
- Vitest 4 + @testing-library/react — every new component / hook /
  conditional-rendering branch has a test; `pnpm test --run` clean.
- shadcn workflow per `.claude/rules/shadcn-ui.md` — every new component
  arrives via `pnpm dlx shadcn@4.7.0 add …` from `frontend/` (NOT repo
  root); no hand-rolled clones of components that exist in the registry.
- URL-shareable state preserved on every page that currently has it
  (`/explorer/{stores,products,runs,jobs,sales}`,
  `/visualize/{forecast,backtest,planner,demand,batch}`).
- RFC 7807 error mapping intact — surface `ApiError.detail.detail` (or
  fallback to `.title`); never display the bare `.status`.
- No new backend routes. No new env vars. No managed-cloud SDK.

### Success Criteria

- [ ] Contract Probe (Task 1) succeeds: every PRP-35 / PRP-36 field this
  PRP wires UI to is verified present (or its task is explicitly DEFERRED
  with a note pointing at the absent field).
- [ ] `/visualize/forecast` segmented-control + model-type select +
  feature-frame select + conditional feature-pack toggles render and
  submit a TrainRequest the backend accepts.
- [ ] `/visualize/backtest` renders the horizon-bucket metric table when
  the response contains `bucketed_aggregate_metrics`; falls back to a
  no-buckets state when absent.
- [ ] `/visualize/backtest` shows RMSE column when `aggregate_metrics.rmse`
  exists; column is omitted (not zero-padded) when absent.
- [ ] `/visualize/planner` labels each assumption row as
  "known future input" or "hypothetical" per the existing
  `is_known_future` flag (verify in Task 1; this PRP does NOT invent it).
- [ ] `/explorer/run-detail` "Feature frame" panel renders V1/V2 + groups
  when present; renders empty-state when absent.
- [ ] `/explorer/run-compare` "Champion compatibility" badge follows the
  comparable-run rule (same grain + overlap + same V); incompatible runs
  display a warning chip.
- [ ] `/ops` stale-alias view supports the new
  `feature_frame_version_mismatch` reason chip.
- [ ] `/ops` model-health view explains "degrading" via the WAPE delta
  + comparable-run count + staleness fields already on
  `ModelHealthEntry`.
- [ ] Promote dialog requires confirmation when latest WAPE >
  previous_wape; surfaces artifact verification + champion/challenger
  delta inline.
- [ ] `/visualize/batch` 5 presets work; the multi-model matrix picker
  emits a valid `BatchSubmitRequest`.
- [ ] Every conditional-rendering branch has a Vitest test:
  - missing feature_frame_version → empty state
  - missing feature_groups → V2 toggles hidden
  - HGBR explainability 422 → friendly "use lightgbm/xgboost for
    importances" message (the existing pattern in
    feature-importance-panel.tsx — confirm not weakened)
  - random_forest (if shipped by PRP-36) → tree-importance variant
  - stale alias with worse latest WAPE → Promote AlertDialog requires
    explicit confirm
  - artifact verification failed → red badge + tooltip with
    `stored_hash` vs `computed_hash`
- [ ] No raw `from 'radix-ui'` imports introduced (verified by grep).
- [ ] No new `components/ui/*` file hand-rolled where a shadcn registry
  component exists.
- [ ] `pnpm tsc --noEmit && pnpm lint && pnpm test --run` clean.
- [ ] Backend test suite still green
  (`uv run pytest -v app/features/forecasting/tests app/features/backtesting/tests app/features/registry/tests app/features/ops/tests -m "not integration"`)
  — this PRP touches no backend code.

---

## All Needed Context

### Documentation & References

```yaml
# ─── Backend contract PRPs (Slice A + B) — load first ───────────────────
- file: PRPs/PRP-35-forecast-intelligence-A-feature-frame-v2.md
  why: V2 feature contract (FeatureGroup names, bundle.metadata fields, TrainRequest.feature_frame_version + feature_groups). Slice C consumes these as JSON.

- file: PRPs/PRP-36-forecast-intelligence-B-model-zoo-backtesting.md
  why: New model_types, RMSE, horizon_bucket_metrics shape, RunResponse.feature_frame_version + feature_groups, StaleReason.FEATURE_FRAME_VERSION_MISMATCH. Slice C consumes these as JSON.

- file: PRPs/INITIAL/INITIAL-forecast-intelligence-C-interactive-ui.md
  why: Source of truth for THIS PRP's scope. Re-read on disagreement.

# ─── Project rules (enforce mechanically) ────────────────────────────────
- file: .claude/rules/ui-design.md
  why: UI workflow rule — Stitch / frontend-design / webapp-testing skill orchestration. The shadcn layer is governed by shadcn-ui.md below; ui-design.md governs the surrounding workflow (design system, browser verification).

- file: .claude/rules/shadcn-ui.md
  why: Mandatory shadcn workflow — invoke the shadcn skill + mcp__shadcn__* tools BEFORE writing any shadcn-touching code. Pin shadcn@4.7.0. From frontend/, NOT repo root. Verify project context (new-york, lucide, aliases) from frontend/components.json:1-23 first.

- file: .claude/rules/test-requirements.md
  why: Frontend testing matrix — every new component owning non-trivial state SHOULD have a vitest test; type-level changes MUST keep `pnpm tsc --noEmit` clean.

- file: .claude/rules/output-formatting.md
  why: Skill report shape only — does not gate UI code. Skip unless writing a skill.

- file: .claude/rules/security-patterns.md
  why: RFC 7807 error envelope is the only error shape the UI may parse; `verify=False` on outbound clients is forbidden (not applicable to UI). No secrets in code/logs (no client-side env vars carry secrets — VITE_API_BASE_URL is public).

# ─── Frontend codebase anchors ─────────────────────────────────────────
- file: frontend/components.json
  why: shadcn config — style=new-york, iconLibrary=lucide, aliases @/components @/ui @/lib @/hooks → src/. The shadcn CLI runs from frontend/, not repo root (otherwise it fails to find this file).

- file: frontend/package.json
  why: Versions. React 19.2, Vite 7.2, Tailwind 4.1, react-router-dom 7.13, @tanstack/react-query 5.90, @tanstack/react-table 8.21, recharts 2.15, vitest 4.1, @testing-library/react 16.3, lucide-react 0.563, date-fns 4.1, react-day-picker 9.13, next-themes 0.4.6. Per-component @radix-ui/* pinned.

- file: frontend/src/types/api.ts
  why: Source of truth for backend wire types. Extended by THIS PRP additively when PRP-35 / PRP-36 field names are confirmed in Task 1. Existing shapes anchored — ForecastPoint L102-107, FeatureMetadataResponse L216-223, ModelRun L179-203, Alias L229-237, RunCompareResponse L239-244, Job L261-274, BatchSubmitRequest L347-355, BatchSubmitResponse L357-375, BatchItemResponse L377-395, OpsSummaryResponse L790-798, ModelHealthEntry L830-843, RetrainingCandidate L801-810, ScenarioAssumptions L884-890, ScenarioComparison L923-943, MultiScenarioComparison L1000-1008, ForecastExplanation L1036-1048, ProblemDetail L540-549.

- file: frontend/src/lib/api.ts
  why: Typed fetch wrapper L23-92. RFC 7807 parsed at the error path (matches `application/problem+json` MIME). `getErrorMessage(error)` is the canonical extractor; never display raw `.status`.

- file: frontend/src/lib/url-params.ts
  why: parsePageParam L17-25, parseIdParam L27-35, parseEnumParam<T> L37-48. New URL params (e.g. `feature_frame_version`, `feature_groups`) use parseEnumParam against the FeatureGroup enum values delivered by PRP-35.

- file: frontend/src/App.tsx
  why: Routing skeleton. Routes via ROUTES constants — DASHBOARD '/', SHOWCASE, OPS, EXPLORER.* (SALES/STORES/PRODUCTS/RUNS/JOBS), VISUALIZE.* (FORECAST/BACKTEST/DEMAND/PLANNER/BATCH), CHAT, KNOWLEDGE, GUIDE, ADMIN. Lazy-loaded + Suspense fallback. NO new routes.

- file: frontend/src/components/layout/top-nav.tsx
  why: NavigationMenu + mobile Sheet pattern. NO change to nav entries; new affordances are page-internal.

# ─── Pages this PRP modifies ───────────────────────────────────────────
- file: frontend/src/pages/visualize/forecast.tsx
  why: Current HORIZON_OPTIONS, train job picker, showInterval, CSV export. ADD: family Tabs, model_type Select filtered by family, feature_frame Select (V1/V2), feature_groups toggle group. Default = (Baseline, seasonal_naive, V1).

- file: frontend/src/pages/visualize/backtest.tsx
  why: Current 7-model selector, date range, n_splits, BacktestFoldsChart. ADD: RMSE column when present; horizon-bucket metric table when `bucketed_aggregate_metrics` present; baseline-vs-feature-aware comparison view when both present.

- file: frontend/src/pages/visualize/planner.tsx
  why: Baseline job picker, ScenarioAssumptions form. ADD: method badge (`model_exogenous` | `heuristic`); known-future-input vs hypothetical pills.

- file: frontend/src/pages/explorer/run-detail.tsx
  why: Run metadata + ExplanationPanel + FeatureImportancePanel. ADD: Feature frame panel showing V1/V2 + groups + safety_classes.

- file: frontend/src/pages/explorer/run-compare.tsx
  why: Two-run side-by-side, DeltaCell, config_diff, metrics_diff. ADD: Feature frame version row; Champion compatibility badge.

- file: frontend/src/pages/ops.tsx
  why: OpsSummary + RetrainingCandidates + ModelHealth + Promote dialog. ADD: feature_frame_version_mismatch reason chip; degrading-explainer fields; safer Promote AlertDialog.

- file: frontend/src/pages/visualize/batch.tsx
  why: Current submit form, PRP-34 max_parallel slider + cancel AlertDialog. ADD: 5 preset Select; multi-model multi-feature-pack matrix picker.

# ─── Hooks this PRP modifies or adds ───────────────────────────────────
- file: frontend/src/hooks/use-runs.ts
  why: Existing query keys L24-56. Extend useRuns query params to accept feature_frame_version filter (when backend supports it — verify Task 1).

- file: frontend/src/hooks/use-ops.ts
  why: useOpsSummary refetchInterval 15s, useRetrainingCandidates, useModelHealth. NO new hooks; consume new fields from existing response shapes.

- file: frontend/src/hooks/use-feature-metadata.ts
  why: useRunFeatureMetadata(runId, enabled). The existing retry:false stays. Slice C reads new feature_groups / safety_classes from the same response when present.

- file: frontend/src/hooks/use-jobs.ts
  why: useJobs polling + useJob refetchInterval. NO change to logic; consume new fields when present.

- file: frontend/src/hooks/use-batches.ts
  why: Submit + cancel + items pagination. NO change to logic; presets are a UI concept that emits the same BatchSubmitRequest shape.

# ─── Existing components this PRP modifies ─────────────────────────────
- file: frontend/src/components/charts/backtest-folds-chart.tsx
  why: Bar chart over fold metrics. ADD a sibling `BacktestHorizonBucketsChart` for per-bucket WAPE / RMSE (do NOT extend this one — the data shape is different).

- file: frontend/src/components/charts/multi-series-chart.tsx
  why: Existing multi-scenario plotter. Reused for baseline-vs-feature-aware backtest comparison view.

- file: frontend/src/components/data-table/data-table.tsx
  why: Generic TanStack table wrapper L41-100. NEW columns added by passing ColumnDef arrays; no change to the generic.

- file: frontend/src/components/common/status-badge.tsx
  why: CVA variants — default/success/warning/error/info/pending. REUSED for "feature-aware" / "baseline" / "stale" / "degrading" / "stockout-constrained" badges (variant=info | warning).

- file: frontend/src/components/common/model-family-badge.tsx
  why: family ∈ ('baseline','tree','additive') → secondary+Activity / default+TreePine / outline+LineChart. REUSED.

- file: frontend/src/components/explainability/explanation-panel.tsx
  why: ForecastExplanation drivers + reason codes + confidence + caveats. NO weakening; reused as-is.

- file: frontend/src/components/explainability/feature-importance-panel.tsx
  why: Handles 400 (baseline), 404 (missing), 422 (HGBR — FeatureImportanceUnavailableError). The 422 path is the load-bearing user-facing message; DO NOT weaken. If PRP-36 ships random_forest, this panel renders a new "tree" variant.

# ─── shadcn registry components installed today ────────────────────────
- file: frontend/src/components/ui/tabs.tsx
  why: USED AS the segmented control for model-family picker (no separate segmented-control primitive exists in shadcn).

- file: frontend/src/components/ui/select.tsx
  why: Model-type, feature-frame-version, batch-preset.

- file: frontend/src/components/ui/checkbox.tsx
  why: Feature-pack toggles (conditional, V2-only).

- file: frontend/src/components/ui/slider.tsx
  why: Price-delta and quick-vary inputs in the planner page.

- file: frontend/src/components/ui/dialog.tsx + alert-dialog.tsx
  why: Promote confirmation when latest WAPE > previous_wape.

- file: frontend/src/components/ui/tooltip.tsx
  why: Disabled-state explanations (e.g. "V2 unavailable — server has not shipped Forecast Intelligence A").

- file: frontend/src/components/ui/badge.tsx
  why: Status / family / mismatch chips.

- file: frontend/src/components/ui/table.tsx
  why: Horizon-bucket metric table; comparable-run table.

# ─── Test patterns ─────────────────────────────────────────────────────
- file: frontend/src/components/common/model-family-badge.test.tsx
  why: Pattern for badge-shape tests (asserts icon + variant per family).

- file: frontend/src/components/explainability/feature-importance-panel.test.tsx
  why: Pattern for conditional-rendering tests against error states (400/404/422).

- file: frontend/src/lib/url-params.test.ts
  why: Pattern for URL-param parsing unit tests.

- file: frontend/src/hooks/use-batches.test.ts
  why: Pattern for hook tests (query key shape + refetch interval).

- file: frontend/src/hooks/use-demo-pipeline.test.ts
  why: WebSocket-driven hook test pattern (NOT needed for this PRP but available as a reference).

# ─── External docs (load on demand) ────────────────────────────────────
- url: https://ui.shadcn.com/docs/components/tabs
  section: "Anatomy" + "Examples → Vertical"
  critical: Tabs styled with `variant` + bold border-bottom is the project's segmented-control look. NEVER hand-roll a "SegmentedControl" component.

- url: https://www.radix-ui.com/primitives/docs/components/slider
  section: "API"
  critical: Used for price-delta slider; `min`, `max`, `step`, `defaultValue: [number]` (array), `onValueChange: (vals: number[]) => void`. Note: shadcn's slider wraps `@radix-ui/react-slider`; do NOT import the Radix barrel.

- url: https://tanstack.com/query/latest/docs/framework/react/guides/query-keys
  section: "Query Key Hashing"
  critical: New URL params land in the query key tuple after the page+pageSize prefix to keep invalidation stable.

- url: https://tanstack.com/table/latest/docs/api/core/column-def
  section: "ColumnDef"
  critical: New horizon-bucket columns are dynamic — the bucket id set depends on `bucketed_aggregate_metrics` keys at response time. Build ColumnDef[] at render time, NOT module-load time.

- url: https://recharts.org/en-US/api/ComposedChart
  section: "Props"
  critical: `data` MUST be an array of plain objects with stable keys. Bucket-aggregate chart maps {bucket_id: wape} into {bucket: 'h_1_7', value: 12.4}.

- url: https://date-fns.org/v4.1.0/docs/format
  section: "Format tokens"
  critical: Use `format(date, 'yyyy-MM-dd')` for backend-facing ISO dates; never the locale-dependent `'PP'`.

# ─── Memory anchors ────────────────────────────────────────────────────
- memory: shadcn-cli-version-pin
  why: Pin `shadcn@4.7.0`. 5.x silently writes a stub pnpm-workspace.yaml and skips the component install.

- memory: radix-ui-vs-per-component-imports
  why: This project uses `@radix-ui/react-X` per-component packages. Never `from 'radix-ui'` (the barrel shadcn 5.x emits). Grep + fix any newly-added file.

- memory: playwright-dogfood-snap-chromium
  why: Dogfood via the `webapp-testing` skill (or native Python Playwright with executable_path=/snap/bin/chromium). Playwright MCP fails on this host.

- memory: dogfood-stale-uvicorn-port-8123
  why: Check `ps -ef | grep uvicorn` for stale processes before claiming UI changes work; a previous-session uvicorn may serve stale code on :8123.

- memory: stale uvicorn pattern
  why: Same as above — surface as a HANDOFF note when smoke-testing.

- memory: computed-field-cross-slice-cycle
  why: Backend-side concern (Pydantic computed_field cycling across slices). Frontend simply consumes the resulting JSON; this memory is a sanity check, not a constraint here.
```

### Current Codebase tree (relevant frontend)

```
frontend/
├── components.json                           # shadcn config
├── package.json                              # versions (React 19, Vite 7, Tailwind 4)
├── src/
│   ├── App.tsx                               # routes
│   ├── lib/
│   │   ├── api.ts                            # typed fetch + RFC 7807
│   │   ├── url-params.ts                     # parsePageParam, parseIdParam, parseEnumParam
│   │   ├── scenario-utils.ts
│   │   ├── ops-actions.ts
│   │   └── ops-utils.ts
│   ├── types/
│   │   └── api.ts                            # backend wire types — additive
│   ├── hooks/
│   │   ├── use-runs.ts
│   │   ├── use-jobs.ts
│   │   ├── use-ops.ts
│   │   ├── use-batches.ts
│   │   ├── use-feature-metadata.ts
│   │   ├── use-explanations.ts
│   │   ├── use-scenarios.ts
│   │   ├── use-config.ts
│   │   ├── use-stores.ts / use-products.ts / use-kpis.ts / use-timeseries.ts / use-drilldowns.ts / use-inventory.ts / use-lifecycle-curve.ts / use-rag-sources.ts / use-seeder.ts / use-websocket.ts / use-demo-pipeline.ts
│   ├── pages/
│   │   ├── visualize/{forecast,backtest,planner,demand,batch}.tsx
│   │   ├── explorer/{run-detail,run-compare,runs,jobs,stores,products,sales,store-detail,product-detail,job-detail}.tsx
│   │   ├── ops.tsx
│   │   └── …
│   ├── components/
│   │   ├── ui/                               # 27 shadcn components (tabs, select, checkbox, slider, dialog, alert-dialog, tooltip, table, badge, …)
│   │   ├── charts/{backtest-folds-chart,multi-series-chart,time-series-chart,kpi-card,revenue-bar-chart}.tsx
│   │   ├── common/{model-family-badge,status-badge,date-range-picker,job-picker,json-block,loading-state,error-display}.tsx
│   │   ├── data-table/{data-table,data-table-column-header,data-table-pagination,data-table-toolbar,data-table-view-options}.tsx
│   │   ├── explainability/{explanation-panel,feature-importance-panel}.tsx
│   │   ├── chat/{chat-message,chat-input,tool-call-display}.tsx
│   │   ├── admin/ai-models-panel.tsx
│   │   ├── demo/demo-step-card.tsx
│   │   └── layout/{app-shell,top-nav,theme-toggle}.tsx
│   └── providers/
│       └── theme-provider.tsx                # next-themes
└── vitest.config.ts                          # jsdom; src/**/*.test.{ts,tsx}
```

### Desired Codebase tree (additive + modified files)

```
frontend/
├── src/
│   ├── types/
│   │   └── api.ts                                                # MODIFIED — extend TrainRequest, BacktestResponse, RunResponse, StaleAliasResponse, FeatureMetadataResponse to mirror Task 1's confirmed contract. ALL new fields are Optional.
│   ├── lib/
│   │   ├── feature-frame-utils.ts                                # NEW — FeatureGroup enum mirror (defensive copy of backend), labelForGroup(group), safetyClassChipVariant(safety), isV2Available(features)
│   │   └── horizon-bucket-utils.ts                               # NEW — HORIZON_BUCKET_IDS, labelForBucket(id), sortBuckets(ids[])
│   ├── hooks/
│   │   └── use-runs.ts                                           # MODIFIED — accept optional feature_frame_version filter param when backend supports it (gated by isV2Available)
│   ├── pages/
│   │   ├── visualize/
│   │   │   ├── forecast.tsx                                      # MODIFIED — segmented family Tabs + model_type Select + feature_frame Select + conditional feature_groups toggle group
│   │   │   ├── backtest.tsx                                      # MODIFIED — RMSE column + horizon-bucket metric table + baseline-vs-feature-aware comparison view
│   │   │   ├── planner.tsx                                       # MODIFIED — method badge + known-future-input vs hypothetical pills
│   │   │   ├── batch.tsx                                         # MODIFIED — 5 preset Select + multi-model multi-feature-pack matrix picker
│   │   │   └── demand.tsx                                        # UNCHANGED in this PRP (separate scope)
│   │   ├── explorer/
│   │   │   ├── run-detail.tsx                                    # MODIFIED — Feature frame panel
│   │   │   └── run-compare.tsx                                   # MODIFIED — Feature frame version row + Champion compatibility badge
│   │   └── ops.tsx                                               # MODIFIED — feature_frame_version_mismatch chip + degrading-explainer + safer Promote AlertDialog
│   ├── components/
│   │   ├── forecast-intelligence/                                # NEW folder (cohesive feature surface)
│   │   │   ├── model-family-tabs.tsx                             # NEW — Tabs styled as segmented control; (family: ModelFamily, onChange)
│   │   │   ├── model-type-select.tsx                             # NEW — Select filtered by family; (family, value, onChange, availableModels: list from Task 1)
│   │   │   ├── feature-frame-select.tsx                          # NEW — Select V1 | V2; (value, onChange, isV2Available: bool, disabledReason?)
│   │   │   ├── feature-groups-toggle.tsx                         # NEW — multi-select Checkbox group of FeatureGroup; (value, onChange, availableGroups: list from Task 1)
│   │   │   ├── horizon-bucket-table.tsx                          # NEW — Table rendering bucketed_aggregate_metrics
│   │   │   ├── champion-compatibility-badge.tsx                  # NEW — Badge with tooltip explaining same grain / window / V rule
│   │   │   ├── feature-frame-panel.tsx                           # NEW — read-only summary of feature_frame_version + feature_groups + safety_classes (used in run-detail)
│   │   │   ├── promote-confirmation-dialog.tsx                   # NEW — AlertDialog with artifact-verify + WAPE-delta warning when worse-newer
│   │   │   ├── batch-preset-select.tsx                           # NEW — 5 hardcoded presets
│   │   │   └── batch-matrix-picker.tsx                           # NEW — multi-model × multi-feature-pack matrix
│   │   ├── charts/
│   │   │   └── backtest-horizon-buckets-chart.tsx                # NEW — sibling to backtest-folds-chart for per-bucket WAPE
│   │   └── explainability/
│   │       └── feature-importance-panel.tsx                      # MODIFIED ONLY IF PRP-36 ships random_forest — add a 'tree (random_forest)' label branch
│   └── pages/__tests__/                                          # not used; tests are colocated next to source
└── (No new directories outside src/)
```

### Known Gotchas of our codebase & Library Quirks

```typescript
// ─────────────────────────────────────────────────────────────────────────
// CRITICAL: This PRP MUST NOT pretend PRP-35 / PRP-36 landed.
// ─────────────────────────────────────────────────────────────────────────
//
// Task 1 (Contract Probe) is the gate. It runs against the live backend
// schemas AND the test fixtures and produces a structured report:
//   - feature_frame_version: PRESENT | ABSENT
//   - feature_groups: PRESENT | ABSENT
//   - rmse: PRESENT | ABSENT
//   - bucketed_aggregate_metrics: PRESENT | ABSENT
//   - StaleReason.FEATURE_FRAME_VERSION_MISMATCH: PRESENT | ABSENT
//   - random_forest model_type: PRESENT | ABSENT
//   - weighted_moving_average / seasonal_average / trend_regression_baseline: PRESENT | ABSENT
// If ANY field is ABSENT, the dependent UI task is DEFERRED — implementer
// MUST NOT scaffold a placeholder. The corresponding feature flag in
// lib/feature-frame-utils.ts (e.g. isV2Available()) reflects this at
// runtime so the affected control renders disabled + with a tooltip.

// ─────────────────────────────────────────────────────────────────────────
// Repo + framework gotchas (verified or anchored):
// ─────────────────────────────────────────────────────────────────────────

// - shadcn CLI: pin 4.7.0 (memory `shadcn-cli-version-pin`). Run from
//   frontend/, not repo root. Example:
//     cd frontend && pnpm dlx shadcn@4.7.0 add tabs   # NO `@latest`
//   shadcn 5.x silently writes a stub pnpm-workspace.yaml and the
//   component never lands.

// - Radix imports: per-component only (memory `radix-ui-vs-per-component-
//   imports`). shadcn 5.x writes `from 'radix-ui'` for new primitives;
//   if that happens, find/replace to `@radix-ui/react-X` before committing.
//   Grep guard for CI:
//     grep -rn "from 'radix-ui'" frontend/src   # MUST be empty
//     grep -rn 'from "radix-ui"' frontend/src   # MUST be empty

// - Tabs as segmented control: shadcn has no SegmentedControl primitive.
//   Use <Tabs> with a `variant=segmented` class composition. NEVER
//   hand-roll a SegmentedControl component.

// - Recharts on Tailwind 4: chart colour vars are `--chart-1` … `--chart-5`
//   (already wired into the project's `index.css`). New charts pull from
//   these CSS variables via the shadcn chart wrapper, not from raw hex.

// - TanStack Query key shape: dataKey for ('runs', filters) where
//   `filters` is an OBJECT (not a JSON-stringified key). New filter fields
//   land in the same object — invalidation by `['runs']` continues to
//   match every nested filter.

// - TanStack Table sorting + pagination: SERVER-DRIVEN (manualPagination,
//   manualSorting). Local state stays in the page component; pass
//   `pageCount` from the response.

// - URL params: every new param goes through `parseEnumParam` against
//   a frozen tuple of allowed values. For `feature_frame_version`, the
//   tuple is `['1', '2'] as const` and parsed → 1 | 2 | undefined.

// - Lazy-loaded routes: every new page-level component is loaded via
//   `React.lazy(() => import('./...'))`. The PageLoader fallback is
//   already wired in App.tsx; do NOT introduce a new fallback.

// - ApiError detail: ALWAYS read `error.detail?.detail || error.detail?.title
//   || error.message`. NEVER display the raw `.status` number to the user
//   (per security-patterns.md — information disclosure via stack traces).

// - Date inputs: backend wants 'yyyy-MM-dd'. date-fns `format(d, 'yyyy-MM-dd')`.
//   NEVER `d.toISOString().slice(0, 10)` — TZ-sensitive.

// - vitest + jsdom: no globals enabled in vitest.config.ts. Import `describe,
//   it, expect, vi` from 'vitest' in EVERY test file.

// - Testing async hooks: wrap with `renderHook(... , { wrapper: QueryClient
//   Wrapper })` per the existing pattern in use-batches.test.ts. Provide
//   a fresh QueryClient per test to avoid cache leakage.

// - shadcn workflow rule enforcement: per `.claude/rules/shadcn-ui.md`
//   §"Workflow", invoke the `shadcn` skill BEFORE adding any new component
//   from the registry. The skill loads project context and the
//   composition rules; the MCP tools (`mcp__shadcn__*`) handle discovery
//   + install commands. Audit checklist comes from
//   `mcp__shadcn__get_audit_checklist` AFTER install.

// - Dogfood: per memory `playwright-dogfood-snap-chromium`, the
//   `webapp-testing` skill is the path (or native Python Playwright with
//   executable_path=/snap/bin/chromium). Playwright MCP fails on this
//   host. Per memory `dogfood-stale-uvicorn-port-8123`, check `ps etime`
//   on uvicorn before trusting :8123 — a previous-session process may
//   serve stale code.

// - Tailwind 4 vs 3: arbitrary values use new syntax (e.g. `bg-(--chart-1)`
//   for CSS variable refs). Most code uses semantic tokens, so this is
//   rarely an issue.

// - StatusBadge variants: 'default' | 'success' | 'warning' | 'error' |
//   'info' | 'pending'. For "feature-aware" use 'info'; "baseline" use
//   'default'; "stale" use 'warning'; "degrading" use 'warning';
//   "stockout-constrained" use 'warning'; "best WAPE" use 'success';
//   "artifact verified" use 'success'; "verification failed" use 'error'.

// - Tooltip: use the existing Tooltip component for every disabled
//   control. Disabled-without-explanation is a UX regression.

// - ConditionalRendering: the implementer's pattern for "render if backend
//   has the field" is `feature_frame_version !== undefined`. NEVER
//   `feature_frame_version === 1` (that would render the V1 chip on V1 runs
//   but hide the chip on pre-PRP-35 runs — semantically different).
//   Hide the entire Feature-frame panel only when the field is `undefined`
//   AND `feature_groups === undefined`.
```

---

## Implementation Blueprint

### Data models and structure (additive types)

```typescript
// frontend/src/types/api.ts — additions (CONFIRM each in Task 1)

export type FeatureFrameVersion = 1 | 2;

// Defensive copy of PRP-35 FeatureGroup enum. Implementer MUST keep this
// in sync with app/shared/feature_frames/contract_v2.py:FeatureGroup —
// Task 1 verifies the values match.
export type FeatureGroup =
  | 'target_history'
  | 'rolling'
  | 'trend'
  | 'calendar'
  | 'price_promo'
  | 'inventory'
  | 'lifecycle'
  | 'replenishment'
  | 'returns'
  | 'exogenous_weather'
  | 'exogenous_macro';

export const FEATURE_GROUP_VALUES = [
  'target_history','rolling','trend','calendar','price_promo','inventory',
  'lifecycle','replenishment','returns','exogenous_weather','exogenous_macro',
] as const satisfies readonly FeatureGroup[];

export type FeatureSafetyClass =
  | 'safe'
  | 'conditionally_safe'
  | 'unsafe_unless_supplied';

// Backend wire shape additions — ALL Optional, all read defensively.

export interface TrainRequest {
  // existing fields preserved …
  feature_frame_version?: FeatureFrameVersion; // PRP-35
  feature_groups?: FeatureGroup[];             // PRP-35 (V2 only)
}

export interface ModelRun {
  // existing fields preserved …
  feature_frame_version?: FeatureFrameVersion;             // PRP-36
  feature_groups?: Partial<Record<FeatureGroup, string[]>>; // PRP-36
}

export interface FeatureMetadataResponse {
  // existing fields preserved …
  feature_frame_version?: FeatureFrameVersion;                       // PRP-35
  feature_groups?: Partial<Record<FeatureGroup, string[]>>;          // PRP-35
  feature_safety_classes?: Record<string, FeatureSafetyClass>;       // PRP-35
}

// BacktestResponse additions — additive sub-fields.
export interface FoldResult {
  // existing fields …
  horizon_bucket_metrics?: Record<string, Record<string, number>>;   // PRP-36
}
export interface AggregateMetrics {
  // existing mae/smape/wape/bias/stability …
  rmse?: number;                                                     // PRP-36
}
export interface ModelBacktestResult {
  // existing aggregate_metrics, fold_results, …
  bucketed_aggregate_metrics?: Record<string, Record<string, number>>; // PRP-36
}

// Ops additions
export type StaleReason =
  | 'newer_success_run'
  | 'artifact_not_verified'
  | 'run_not_success'
  | 'feature_frame_version_mismatch';                                // PRP-36 (NEW value)

export interface StaleAliasResponse {
  // existing fields …
  alias_feature_frame_version?: FeatureFrameVersion;                 // PRP-36
  comparable_run_feature_frame_version?: FeatureFrameVersion;        // PRP-36
}
```

### List of tasks to be completed (dependency-ordered)

```yaml
Task 1 — CONTRACT PROBE (gates every other task):
  - VERIFY which PRP-35 / PRP-36 fields are present in the live backend by:
      a) Reading `app/features/forecasting/schemas.py` and confirming `TrainRequest.feature_frame_version` + `feature_groups` exist.
      b) Reading `app/features/backtesting/schemas.py` and confirming `FoldResult.horizon_bucket_metrics`, `AggregateMetrics.rmse`, `ModelBacktestResult.bucketed_aggregate_metrics`.
      c) Reading `app/features/registry/schemas.py` and confirming `RunResponse.feature_frame_version` + `feature_groups`.
      d) Reading `app/features/ops/schemas.py` and confirming `StaleReason.FEATURE_FRAME_VERSION_MISMATCH`.
      e) Reading `app/features/forecasting/models.py` factory branch list and capturing the SUPERSET of `model_type` values the backend dispatches.
  - PRODUCE a Task 1 report (commit as `docs/contract-probe-report.md` under PRPs/ai_docs/) listing every probed field with PRESENT / ABSENT + the source file:line.
  - FOR each ABSENT field, FLAG the dependent Task as DEFERRED in the PR description AND in the comment block at the top of the affected file. Implementer MUST NOT scaffold a placeholder for an ABSENT field.
  - VERIFY also that:
      - The `BacktestRequest.config` (model_config field) accepts the new model_type values from PRP-36 (read the discriminated union in forecasting/schemas.py).
      - `forecast_enable_random_forest` setting (if added by PRP-36 Task 5) is exposed to the UI via `/config/ai` or remains a server-side-only gate (the latter is acceptable — the UI catches the 422 from the train route and renders the unsupported message).
  - If PRP-35 surface (FeatureGroup, feature_frame_version on TrainRequest) is ABSENT: STOP. This PRP cannot execute.
  - If PRP-36 surface is partially ABSENT: continue with the [gate:PRP-35]-tagged tasks only.

Task 2 — CREATE frontend/src/lib/feature-frame-utils.ts:
  - EXPORT type FeatureFrameVersion = 1 | 2.
  - EXPORT type FeatureGroup + FEATURE_GROUP_VALUES (mirror of PRP-35 enum). Note: this is a DEFENSIVE COPY; runtime backend membership is the authoritative check via Task 1.
  - EXPORT labelForGroup(group: FeatureGroup): string — UI-facing labels ("Target history", "Rolling means", "Yearly seasonality"…). Map captured from `docs/optional-features/10-baseforecaster-feature-contract.md` (PRP-35 V2 section).
  - EXPORT safetyClassChipVariant(safety: FeatureSafetyClass): BadgeVariant — 'safe' → 'success', 'conditionally_safe' → 'warning', 'unsafe_unless_supplied' → 'error'.
  - EXPORT isV2Available(featureMetadata: FeatureMetadataResponse | undefined): bool — returns true iff `featureMetadata?.feature_frame_version === 2 || (featureMetadata?.feature_groups && Object.keys(featureMetadata.feature_groups).length > 0)`.
  - EXPORT defaultV2Groups(): FeatureGroup[] — the V2 default subset for the UI's "use defaults" affordance. Sources from PRP-35 DEFAULT_V2_GROUPS = (target_history, rolling, trend, calendar, price_promo, lifecycle). Hard-coded here; Task 1 verifies match.
  - ADD test file feature-frame-utils.test.ts: every exported function on every branch.

Task 3 — CREATE frontend/src/lib/horizon-bucket-utils.ts:
  - EXPORT HORIZON_BUCKET_IDS = ['h_1_7', 'h_8_14', 'h_15_28', 'h_29_plus'] as const.
  - EXPORT labelForBucket(id) → 'Days 1-7' | 'Days 8-14' | 'Days 15-28' | 'Days 29+'.
  - EXPORT sortBuckets(ids: string[]): string[] — stable order matching HORIZON_BUCKET_IDS, unknown bucket ids appended at the end.
  - ADD test file: every label + sort + unknown handling.

Task 4 — MODIFY frontend/src/types/api.ts:
  - ADD the type extensions in the "Data models and structure" section above. EVERY new field is Optional.
  - PRESERVE every existing exported type.
  - ADD a JSDoc note on each new field citing the PRP that ships it (PRP-35 or PRP-36).
  - DO NOT remove or rename any existing field.

Task 5 — CREATE frontend/src/components/forecast-intelligence/model-family-tabs.tsx [gate:always]:
  - INVOKE the `shadcn` skill first; CONFIRM components/ui/tabs.tsx is present.
  - IMPLEMENT a Tabs-as-segmented-control component:
      props: { family: ModelFamily; onChange: (f: ModelFamily) => void; disabled?: boolean }
      values: 'baseline' | 'tree' | 'additive' (mirror frontend/src/components/common/model-family-badge.tsx variants).
      visual: shadcn Tabs primitive with a `variant=segmented` Tailwind class composition (a thin rounded-md border + a sliding-bg active state). NO custom segmented-control file.
  - ADD test: each value selects + emits onChange; disabled state blocks emission.

Task 6 — CREATE frontend/src/components/forecast-intelligence/model-type-select.tsx [gate:always]:
  - props: { family: ModelFamily; value: string; onChange: (modelType: string) => void; availableModels: string[]; disabled?: boolean }.
  - When family changes, the Select options narrow to model_types whose ModelFamily matches (computed via a static map mirroring backend `_MODEL_FAMILY_MAP`).
  - Defensive: if `value` is incompatible with the new family, the parent component MUST reset value — but the component itself does NOT reset (avoid unexpected resets if the parent has its own logic).
  - ADD test: family change narrows options; emits onChange on selection.

Task 7 — CREATE frontend/src/components/forecast-intelligence/feature-frame-select.tsx [gate:PRP-35]:
  - props: { value: FeatureFrameVersion; onChange: (v: FeatureFrameVersion) => void; isV2Available: boolean; v2DisabledReason?: string }.
  - Renders shadcn Select with 'V1' and 'V2' options; V2 disabled when !isV2Available with a Tooltip rendering `v2DisabledReason` (default: "V2 unavailable — server has not shipped Forecast Intelligence A").
  - ADD test: when isV2Available=false, the V2 option is disabled AND a Tooltip renders; onChange respected for V1.

Task 8 — CREATE frontend/src/components/forecast-intelligence/feature-groups-toggle.tsx [gate:PRP-35]:
  - props: { value: FeatureGroup[]; onChange: (groups: FeatureGroup[]) => void; availableGroups: FeatureGroup[]; defaults: FeatureGroup[]; disabled?: boolean }.
  - Renders a vertical Checkbox list (shadcn Checkbox component); a "Use defaults" button resets to `defaults`; an empty selection emits a 0-element array (the parent decides whether to send `undefined` instead of `[]` to the backend).
  - Each group label uses labelForGroup; each row shows a safety-class chip if safety_classes is available (otherwise omitted).
  - ADD test: toggle on/off; use-defaults; empty selection emits []; safety chip renders when supplied.

Task 9 — CREATE frontend/src/components/forecast-intelligence/horizon-bucket-table.tsx [gate:PRP-36]:
  - props: { bucketed: Record<string, Record<string, number>> | undefined; metric: 'mae' | 'smape' | 'wape' | 'bias' | 'rmse'; metricLabel?: string }.
  - Renders a shadcn Table with one row per bucket (sorted via sortBuckets); columns = bucket id, bucket label, metric value (formatted to 2 decimals).
  - Empty state: when `bucketed` is undefined or empty, renders "No horizon-bucket metrics available" inside the Card.
  - ADD test: renders 4 buckets in order; empty state when undefined; unknown-bucket appended.

Task 10 — CREATE frontend/src/components/forecast-intelligence/feature-frame-panel.tsx [gate:PRP-35]:
  - props: { feature_frame_version?: FeatureFrameVersion; feature_groups?: Partial<Record<FeatureGroup, string[]>>; feature_safety_classes?: Record<string, FeatureSafetyClass>; isLoading?: boolean }.
  - Renders a Card with:
      - the version chip (V1 / V2 — version=1 uses 'default', version=2 uses 'info' variant).
      - per-group list when V2 — each group name (label) + collapsed columns (shadcn Collapsible — Slice C already uses it in /admin).
      - per-column safety-class chip when safety_classes is supplied.
  - Empty state: when both fields are undefined → "Feature frame information not available (pre-PRP-35 run)."
  - ADD test: each branch (V1 / V2 with groups / V2 with safety / empty).

Task 11 — CREATE frontend/src/components/forecast-intelligence/champion-compatibility-badge.tsx [gate:PRP-36]:
  - props: { runA: ModelRun; runB: ModelRun }.
  - Computes compatibility: SAME (store_id, product_id) AND windows OVERLAP AND SAME feature_frame_version (treating undefined as 1).
  - Renders a Badge variant=success ("Comparable") or variant=warning ("Not comparable — different feature frame version" OR "Not comparable — no data window overlap" OR "Not comparable — different grain").
  - Tooltip carries the precise reason.
  - ADD test: every reason branch + the "comparable" success branch.

Task 12 — CREATE frontend/src/components/forecast-intelligence/promote-confirmation-dialog.tsx [gate:always]:
  - props: { open: boolean; onOpenChange: (open: boolean) => void; run: ModelRun; currentChampion?: ModelRun; onConfirm: () => Promise<void>; isPromoting: boolean }.
  - Renders shadcn AlertDialog:
      - Headline: "Promote run {run.run_id.slice(0,8)} to alias `production`?"
      - If `currentChampion` exists AND `run.metrics.wape > currentChampion.metrics.wape`: a red callout "Latest WAPE is HIGHER than current champion (X% > Y%)" — confirmation requires checking a "I understand promoting a worse run" checkbox.
      - If `run.artifact_hash` does not match a freshly-computed verify: a red "Artifact verification failed" callout (the verify call is the existing useArtifactVerify hook).
      - If `currentChampion?.feature_frame_version !== run.feature_frame_version`: an amber callout "Feature frame version mismatch — promotion will silently change the contract this alias represents".
      - "Promote" button is disabled until every warning is acknowledged.
  - ADD tests: each branch (worse-WAPE requires checkbox; verify-fail blocks; V-mismatch requires acknowledge; clean promote auto-enables).

Task 13 — CREATE frontend/src/components/forecast-intelligence/batch-preset-select.tsx [gate:always]:
  - props: { value: PresetId; onChange: (preset: PresetId) => void }.
  - Hardcoded presets:
      - 'quick_baseline_sweep' → naive + seasonal_naive + moving_average + (if PRP-36) weighted_moving_average + seasonal_average.
      - 'feature_aware_comparison' → regression + (gated) lightgbm + (gated) xgboost + prophet_like + (PRP-36) random_forest; feature_frame_version=2 + defaultV2Groups().
      - 'champion_challenger_refresh' → current champion model_type + the next best WAPE family.
      - 'stockout_sensitive_products' → regression + V2 with `inventory` + `replenishment` + `returns` groups enabled.
      - 'high_wape_recovery' → all available feature-aware models + V2 with defaults.
  - The component emits the preset id; the parent (`pages/visualize/batch.tsx`) translates the preset into a `BatchSubmitRequest`.

Task 14 — CREATE frontend/src/components/forecast-intelligence/batch-matrix-picker.tsx [gate:always]:
  - props: { availableModels: string[]; availableGroups: FeatureGroup[]; value: { model_type: string; feature_frame_version: FeatureFrameVersion; feature_groups: FeatureGroup[] }[]; onChange: (rows: …) => void; max_rows?: number }.
  - Renders a Checkbox grid: one row per available model, one column per (frame version × group set). User toggles cells to build a list of (model_type, version, groups) tuples the batch will sweep.
  - Cap at max_rows (default 24); render an error chip when exceeded.
  - ADD tests: add/remove rows; respect cap.

Task 15 — CREATE frontend/src/components/charts/backtest-horizon-buckets-chart.tsx [gate:PRP-36]:
  - props: { bucketed: Record<string, Record<string, number>> | undefined; metric: 'mae' | 'smape' | 'wape' | 'bias' | 'rmse' }.
  - Recharts ComposedChart (or BarChart): X = bucket label, Y = metric. Data built from `bucketed` via sortBuckets.
  - Empty state matches the bucket-table empty state.
  - ADD test: renders bars for each bucket; empty state when undefined.

Task 16 — MODIFY frontend/src/pages/visualize/forecast.tsx:
  - INSERT the new control row above the existing form: <ModelFamilyTabs> → <ModelTypeSelect> → <FeatureFrameSelect> → <FeatureGroupsToggle (when V2 + isV2Available)>.
  - Wire each control to local React state; on submit, build a TrainRequest with the new optional fields ONLY when set (avoid sending `feature_frame_version: 1` explicitly — backend treats absent as V1).
  - PRESERVE the existing horizon selector + showInterval + CSV export.
  - PRESERVE URL-shareable state.

Task 17 — MODIFY frontend/src/pages/visualize/backtest.tsx:
  - INSERT <HorizonBucketTable> + <BacktestHorizonBucketsChart> beneath the existing <BacktestFoldsChart> when `main_model_results.bucketed_aggregate_metrics` is present.
  - INSERT RMSE column in the existing metric-card row when `aggregate_metrics.rmse` is present.
  - PRESERVE the existing baseline-vs-feature-aware comparison logic (or extend it: when `baseline_results` is non-empty, render the comparison view above the single-model view).
  - PRESERVE URL-shareable state + the existing model_type Select (replaced by <ModelTypeSelect> tied to <ModelFamilyTabs>).

Task 18 — MODIFY frontend/src/pages/visualize/planner.tsx:
  - INSERT a method Badge near the run-id picker: 'model_exogenous' (variant=info) or 'heuristic' (variant=warning) per `ScenarioComparison.method`.
  - INSERT a known-future-input vs hypothetical Pill next to each assumption row.
  - PRESERVE the multi-scenario chart + save/clone/delete flow.

Task 19 — MODIFY frontend/src/pages/explorer/run-detail.tsx:
  - INSERT <FeatureFramePanel> beneath the existing run metadata card.
  - When PRP-36 ships random_forest: ensure the existing FeatureImportancePanel renders the new 'tree (random_forest)' variant (it already supports `kind=tree`; verify in Task 1).
  - PRESERVE the artifact verify section + the existing Explanation/FeatureImportance panels.

Task 20 — MODIFY frontend/src/pages/explorer/run-compare.tsx:
  - INSERT a "Feature frame version" row in the metrics-diff table when at least one of the runs has `feature_frame_version` defined.
  - INSERT <ChampionCompatibilityBadge runA={…} runB={…} /> beneath the picker row.
  - PRESERVE the DeltaCell sign-only behaviour.

Task 21 — MODIFY frontend/src/pages/ops.tsx:
  - INSERT the new `feature_frame_version_mismatch` chip handling in the stale-alias table — map the reason via the existing StaleReason switch.
  - INSERT degrading-status explanation row beneath each ModelHealthEntry: latest_wape, previous_wape, wape_delta (color-coded), n_comparable_runs, last_trained_at, staleness_days. All these fields ALREADY exist on `ModelHealthEntry` (frontend/src/types/api.ts:830-843); this PRP just surfaces them.
  - REPLACE the existing Promote affordance with <PromoteConfirmationDialog>.
  - PRESERVE the OpsSummary + RetrainingCandidates table.

Task 22 — MODIFY frontend/src/pages/visualize/batch.tsx:
  - INSERT <BatchPresetSelect> at the top of the form.
  - INSERT <BatchMatrixPicker> below the preset (the preset prefills the matrix).
  - PRESERVE the PRP-34 max_parallel Slider and cancel AlertDialog.
  - When user picks a preset, the matrix populates; user can still toggle cells manually.

Task 23 — MODIFY frontend/src/hooks/use-runs.ts:
  - EXTEND the useRuns query-key tuple to include `feature_frame_version` when supplied (additive; backwards-compat).
  - When the backend does not support filtering by feature_frame_version (Task 1 ABSENT), the hook accepts the param locally but does NOT forward it to the API — to avoid a 422.

Task 24 — UPDATE tests:
  - feature-frame-utils.test.ts (Task 2).
  - horizon-bucket-utils.test.ts (Task 3).
  - model-family-tabs.test.tsx; model-type-select.test.tsx; feature-frame-select.test.tsx; feature-groups-toggle.test.tsx (Tasks 5-8).
  - horizon-bucket-table.test.tsx (Task 9).
  - feature-frame-panel.test.tsx (Task 10).
  - champion-compatibility-badge.test.tsx (Task 11).
  - promote-confirmation-dialog.test.tsx (Task 12).
  - batch-preset-select.test.tsx; batch-matrix-picker.test.tsx (Tasks 13-14).
  - backtest-horizon-buckets-chart.test.tsx (Task 15).
  - UPDATE forecast.tsx.test? (page-level tests are rare in this repo — colocate component tests; page tests only when there's nontrivial conditional logic in the page itself).
  - REGRESSION: confirm feature-importance-panel.test.tsx still green; explanation-panel.test.tsx unchanged; model-family-badge.test.tsx unchanged.

Task 25 — DOC UPDATE:
  - CREATE docs/user-guide/advanced-forecasting-guide.md — user-facing explanation of model families, feature frame V1 vs V2, feature packs, WAPE / RMSE / per-horizon-buckets, stale aliases, safer Promote affordance. Indexable by RAG.
  - UPDATE docs/user-guide/dashboard-guide.md — reference the new affordances on each touched page.
  - UPDATE docs/_base/API_CONTRACTS.md — only if the BACKEND response shape changed and PRP-36 missed the doc update.

Task 26 — DOGFOOD (per memory `playwright-dogfood-snap-chromium`):
  - Run `pnpm dev` (via `./node_modules/.bin/vite --host 0.0.0.0` per the WSL workaround in CLAUDE.local.md).
  - Use the `webapp-testing` skill to exercise the golden paths:
      a) Train a V1 baseline → confirm the existing-fields path still works (no regressions).
      b) Train a V2 feature-aware run (gated on PRP-35) → confirm feature-groups toggles are visible.
      c) Backtest a feature-aware run → confirm horizon-bucket table renders.
      d) Open a V2 run in /explorer/run-detail → confirm FeatureFramePanel renders.
      e) Open /ops → confirm stale-alias mismatch chip renders if seeded.
      f) Open /visualize/batch → confirm preset prefills the matrix.
  - Capture screenshots; attach to the PR.
  - CHECK `ps -ef | grep uvicorn` BEFORE asserting "it works" (per memory `dogfood-stale-uvicorn-port-8123`).
```

### Per task pseudocode (the load-bearing parts)

```typescript
// Task 2 — feature-frame-utils.ts (key parts)
import type { FeatureMetadataResponse } from '@/types/api';

export type FeatureFrameVersion = 1 | 2;
export type FeatureGroup =
  | 'target_history' | 'rolling' | 'trend' | 'calendar' | 'price_promo'
  | 'inventory' | 'lifecycle' | 'replenishment' | 'returns'
  | 'exogenous_weather' | 'exogenous_macro';

const LABELS: Record<FeatureGroup, string> = {
  target_history: 'Target history (lags + same-DOW mean)',
  rolling: 'Rolling means',
  trend: 'Trend (30/90-day)',
  calendar: 'Calendar (DOW, month, sin/cos)',
  price_promo: 'Price + promotion',
  inventory: 'Inventory + stockout',
  lifecycle: 'Product lifecycle',
  replenishment: 'Replenishment cadence',
  returns: 'Returns intensity',
  exogenous_weather: 'Weather signals',
  exogenous_macro: 'Macro signals',
};

export function labelForGroup(group: FeatureGroup): string {
  return LABELS[group];
}

export function isV2Available(meta: FeatureMetadataResponse | undefined): boolean {
  if (!meta) return false;
  if (meta.feature_frame_version === 2) return true;
  if (meta.feature_groups && Object.keys(meta.feature_groups).length > 0) return true;
  return false;
}

export function defaultV2Groups(): FeatureGroup[] {
  return ['target_history','rolling','trend','calendar','price_promo','lifecycle'];
}

export function safetyClassChipVariant(safety: 'safe' | 'conditionally_safe' | 'unsafe_unless_supplied') {
  switch (safety) {
    case 'safe': return 'success' as const;
    case 'conditionally_safe': return 'warning' as const;
    case 'unsafe_unless_supplied': return 'error' as const;
  }
}


// Task 11 — champion-compatibility-badge.tsx (key parts)
function computeCompatibility(a: ModelRun, b: ModelRun): { ok: boolean; reason?: string } {
  if (a.store_id !== b.store_id || a.product_id !== b.product_id) {
    return { ok: false, reason: 'Different grain (store + product)' };
  }
  const a_start = new Date(a.data_window_start).getTime();
  const a_end = new Date(a.data_window_end).getTime();
  const b_start = new Date(b.data_window_start).getTime();
  const b_end = new Date(b.data_window_end).getTime();
  if (a_end < b_start || b_end < a_start) {
    return { ok: false, reason: 'No data-window overlap' };
  }
  const va = a.feature_frame_version ?? 1;
  const vb = b.feature_frame_version ?? 1;
  if (va !== vb) {
    return { ok: false, reason: `Different feature frame version (V${va} vs V${vb})` };
  }
  return { ok: true };
}


// Task 12 — promote-confirmation-dialog.tsx (key parts)
function PromoteConfirmationDialog({ open, onOpenChange, run, currentChampion, onConfirm, isPromoting }: Props) {
  const [worseAcknowledged, setWorseAcknowledged] = useState(false);
  const [versionMismatchAcknowledged, setVersionMismatchAcknowledged] = useState(false);
  const { data: verify } = useArtifactVerify(run.run_id, open); // existing hook

  const worseWape =
    currentChampion?.metrics?.wape != null &&
    run.metrics?.wape != null &&
    run.metrics.wape > currentChampion.metrics.wape;

  const verifyFailed = verify?.verified === false;

  const versionMismatch =
    (currentChampion?.feature_frame_version ?? 1) !== (run.feature_frame_version ?? 1);

  const canConfirm =
    !verifyFailed &&
    (!worseWape || worseAcknowledged) &&
    (!versionMismatch || versionMismatchAcknowledged) &&
    !isPromoting;

  // … AlertDialog body renders each callout + checkbox …
}
```

### Integration Points

```yaml
BACKEND:
  - No backend changes. Every new UI field reads an EXISTING backend response field that PRP-35 / PRP-36 add. Slice C does NOT ship backend code.
  - Task 1 (Contract Probe) is the only "backend" interaction; it's a read-only schema audit.

FRONTEND ROUTES:
  - No new routes. Top-nav unchanged.

FRONTEND HOOKS:
  - use-runs.ts: query-key tuple gets an optional `feature_frame_version` filter (passthrough when supported).
  - All other hooks unchanged in shape; they consume new Optional fields.

CONFIG:
  - No new VITE_* env vars. No `.env.example` change in frontend/.

TESTING:
  - vitest config unchanged. New `*.test.{ts,tsx}` files colocated next to source.

CHANGELOG:
  - Under "Unreleased": `feat(ui): forecast intelligence C — operator workflow surfaces for V2 features + model zoo + per-horizon metrics (#<issue>)`.
```

---

## Validation Loop

### Level 1: Frontend syntax + types + lint

```bash
cd frontend
pnpm tsc --noEmit          # strict TypeScript
pnpm lint                  # ESLint clean

# shadcn import guards
grep -rn "from 'radix-ui'" src && echo "FAIL: barrel import found" && exit 1
grep -rn 'from "radix-ui"' src && echo "FAIL: barrel import found" && exit 1
echo "OK: per-component radix imports only"

# Expected: zero errors. Fix every reported issue; do not silence via @ts-ignore.
```

### Level 2: Unit tests

```bash
cd frontend
pnpm test --run

# Expected: every new test green; every existing test still green.
# If a snapshot file exists, only update it when the change is deliberate.
```

### Level 3: Backend regression (sanity check — this PRP touches no backend code)

```bash
# Run from repo root
uv run pytest -v -m "not integration" \
  app/features/forecasting/tests \
  app/features/backtesting/tests \
  app/features/registry/tests \
  app/features/ops/tests

# Expected: unchanged from pre-PR baseline. If anything changes, you
# accidentally touched backend code — back it out.
```

### Level 4: Dogfood the running UI

```bash
# WSL workaround per CLAUDE.local.md
cd frontend && ./node_modules/.bin/vite --host 0.0.0.0

# In a separate shell:
ps -ef | grep '[u]vicorn'   # verify backend is the current-session process
curl -s http://localhost:8123/health   # should print {"status":"ok"}

# Use the webapp-testing skill to exercise (no manual flow in this PRP —
# the skill is the orchestration; capture screenshots for the PR).
```

---

## Final validation Checklist

> **GATE FIRST:** Task 1 produced a written contract-probe report. Every
> task tagged `[gate:PRP-35]` or `[gate:PRP-36]` has been verified
> against the live backend OR explicitly deferred with a note pointing
> at the absent field.

- [ ] Task 1 (Contract Probe) report committed under `PRPs/ai_docs/contract-probe-report.md`.
- [ ] Every Optional field added to `frontend/src/types/api.ts` corresponds to a present backend field per Task 1.
- [ ] `pnpm tsc --noEmit` clean.
- [ ] `pnpm lint` clean.
- [ ] `pnpm test --run` clean.
- [ ] No `from 'radix-ui'` barrel imports introduced.
- [ ] No hand-rolled `components/ui/*` file where the shadcn registry has an equivalent component.
- [ ] `shadcn@4.7.0` was used for every new shadcn install (memory `shadcn-cli-version-pin`).
- [ ] URL-shareable state preserved on every page that has it today.
- [ ] `/visualize/forecast`: family Tabs + model-type Select + feature-frame Select + conditional feature-groups Toggles render; submit produces a valid TrainRequest.
- [ ] `/visualize/backtest`: RMSE column appears when present; horizon-bucket table + chart render when present; baseline-vs-feature-aware comparison renders when both present; empty states cover every absent field.
- [ ] `/visualize/planner`: method badge + known-future-input pills present.
- [ ] `/visualize/batch`: 5 presets prefill the matrix; matrix-picker emits a valid BatchSubmitRequest.
- [ ] `/explorer/run-detail`: Feature frame panel renders V1/V2 + groups + safety; empty-state for pre-PRP-35 runs.
- [ ] `/explorer/run-compare`: Feature frame version row + ChampionCompatibilityBadge per the comparable-run rule.
- [ ] `/ops`: feature_frame_version_mismatch chip handled; degrading-status fields surfaced; PromoteConfirmationDialog blocks worse-WAPE without acknowledgement, blocks verify-fail, requires V-mismatch acknowledgement.
- [ ] Every conditional-rendering branch has a Vitest test (missing feature_frame_version, missing feature_groups, HGBR 422, random_forest tree-importance, stale-with-worse-WAPE, artifact-fail, V-mismatch).
- [ ] No backend code touched in this PRP (`git diff app/` and `git diff alembic/` empty).
- [ ] No new agent tool; `agent_require_approval` unchanged.
- [ ] No new VITE_* env vars; no `.env.example` change.
- [ ] Documentation (advanced-forecasting-guide.md) created and indexed; dashboard-guide.md updated.
- [ ] Dogfood (Level 4) screenshots attached to the PR.
- [ ] CHANGELOG entry under "Unreleased": `feat(ui): forecast intelligence C — operator workflow surfaces for V2 features + model zoo + per-horizon metrics (#<issue>)`.

---

## Unresolved Contract Assumptions (waiting on PRP-35 + PRP-36 execution)

Each assumption is verified by Task 1 (Contract Probe). If verification
fails for an item, the corresponding UI task is DEFERRED — implementer
patches THIS PRP file to mark the task `DEFERRED — pending {field}` and
proceeds with the rest.

1. PRP-35 ships `TrainRequest.feature_frame_version: int = 1` and
   `TrainRequest.feature_groups: list[str] | None`. UI Tasks 7 + 8 + 16
   depend on this. ASSUMPTION: when V1, `feature_groups` is rejected
   (422) by the backend per the post-patch wording in PRP-35.
2. PRP-35 ships `FeatureGroup` enum with the exact 11 values listed in
   `lib/feature-frame-utils.ts`. Task 1 verifies value-by-value.
3. PRP-35 ships `FeatureMetadataResponse.feature_frame_version`,
   `feature_groups`, `feature_safety_classes`. Tasks 10 + 19 depend.
4. PRP-36 ships `BacktestResponse.main_model_results.aggregate_metrics.rmse`,
   `bucketed_aggregate_metrics`, and `FoldResult.horizon_bucket_metrics`.
   Tasks 9 + 15 + 17 depend.
5. PRP-36 ships `StaleReason.FEATURE_FRAME_VERSION_MISMATCH` AND
   `StaleAliasResponse.alias_feature_frame_version` +
   `comparable_run_feature_frame_version`. Tasks 11 + 21 depend.
6. PRP-36 ships `RunResponse.feature_frame_version` +
   `feature_groups`. Tasks 10 + 19 + 20 depend.
7. PRP-36 ships new model_type values (`weighted_moving_average`,
   `seasonal_average`, optionally `trend_regression_baseline` and
   `random_forest`). Task 6 + Task 13 depend. If a value is ABSENT, the
   model-type Select hides it AND the corresponding preset omits it.
8. PRP-36 keeps `FeatureImportanceUnavailableError` 422 path intact
   for HGBR. Feature-importance-panel.tsx already handles this; this
   PRP must NOT weaken it.
9. Backend rejects `feature_groups` when `feature_frame_version=1`.
   Slice C MUST NOT send `feature_groups: []` when V1 is selected —
   send `feature_groups: undefined` (i.e. omit the field).
10. `ScenarioComparison.method` is `'heuristic' | 'model_exogenous'`
    (no other values). Task 18 depends. If a future PRP adds a third
    method, this PRP's badge defaults to neutral.

---

## Anti-Patterns to Avoid

- ❌ Don't render a value the backend did not return. The
  Feature-frame panel's empty state is the contract for absent fields.
- ❌ Don't bypass `.claude/rules/shadcn-ui.md`. Every shadcn component
  arrives through `pnpm dlx shadcn@4.7.0 add …` from `frontend/`.
  No raw GitHub fetches; no copying a published component into
  `components/ui/*` manually.
- ❌ Don't introduce `from 'radix-ui'` (the barrel shadcn 5.x writes).
  Per-component `@radix-ui/react-X` only.
- ❌ Don't add `permutation_importance` calls in the UI — that's a
  separate PRP (the existing 422 path is the operator-facing contract).
- ❌ Don't fake a feature_frame_version on a run that doesn't carry
  one — render the empty state.
- ❌ Don't downgrade the FeatureImportancePanel's existing 422
  (HGBR-unavailable) UX. The "use lightgbm/xgboost for native
  importances" message is the contract; preserve it.
- ❌ Don't send `feature_groups: []` to the backend when V1 is selected.
  Omit the field entirely.
- ❌ Don't introduce a new agent tool — `agent_require_approval`
  unchanged. The "Use this context" copy buttons are pure DOM/
  clipboard-API; they do NOT call the agent layer.
- ❌ Don't compare runs across `feature_frame_version` in the
  ChampionCompatibilityBadge — incompatibility is the explicit signal.
- ❌ Don't widen the agent layer / backend / Alembic; this PRP touches
  the frontend only.
- ❌ Don't promote a worse run without explicit checkbox acknowledgement
  in the PromoteConfirmationDialog.
- ❌ Don't introduce a SegmentedControl component — Tabs styled as
  segmented is the project pattern.
- ❌ Don't trust `:8123` without checking `ps -ef | grep uvicorn` first
  (memory `dogfood-stale-uvicorn-port-8123`).

---

## Confidence

**Confidence: 6.5/10** for one-pass implementation success after PRP-35
+ PRP-36 land.

What grounds the 6.5:
- The frontend codebase research is anchored at file:line for every
  hook + page + component + chart this PRP touches.
- Every new component is colocated under `frontend/src/components/
  forecast-intelligence/` so the review surface is cohesive.
- The shadcn workflow is explicitly invoked (skill + MCP + 4.7.0 pin).
- Every conditional-rendering branch has a Vitest test path called out.
- The "do not fabricate backend values" rule has a single enforcement
  point (Task 1's contract-probe report), and every dependent task is
  tagged with its gate.

What costs the 3.5 points:
- **Two prior PRPs have not landed yet.** Even with Task 1, the UI
  surface area is wide; a late field-name change in PRP-35 or PRP-36
  rippling into the type extensions can require multiple cross-file
  edits. Mitigation: every new field is Optional and read defensively.
- Dogfood depends on a live backend with V2-aware runs seeded. The
  current dev DB has 49 model_runs + 12 aliases (per HANDOFF.md), but
  none are V2 — PRP-35's execution session needs to create at least one
  V2 SUCCESS run before Slice C's dogfood is meaningful.
- shadcn 5.x has known regressions (memories `shadcn-cli-version-pin`,
  `radix-ui-vs-per-component-imports`); the 4.7.0 pin must hold
  through this PRP's life. CI does not gate shadcn version drift today;
  the implementer enforces it manually.
- Recharts 2.x + Tailwind 4 + React 19 is a fresh combination — the
  existing charts work, but new charts may surface visual regressions
  on small terminals. Dogfood at 1024px and 1440px both.
