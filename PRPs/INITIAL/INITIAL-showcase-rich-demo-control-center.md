# INITIAL-showcase-rich-demo-control-center.md — Rich Operator Demo Control Center

> **Status:** Planning. Umbrella INITIAL for the multi-PRP `/showcase` upgrade
> (PRP-38 through PRP-41). NO implementation code is in scope of this brief.
> The four sliced INITIALs and the index doc that accompany this file are the
> entry points for `/base_prp:prp-create`.
>
> **Companion artifacts (planning only):**
> - `PRPs/INITIAL/INITIAL-showcase-rich-demo-index.md` — dependency map + execution sequence
> - `PRPs/INITIAL/INITIAL-showcase-38-data-modeling-lifecycle.md` (MVP foundation)
> - `PRPs/INITIAL/INITIAL-showcase-39-decision-portfolio-lifecycle.md`
> - `PRPs/INITIAL/INITIAL-showcase-40-planning-knowledge-lifecycle.md`
> - `PRPs/INITIAL/INITIAL-showcase-41-agent-ops-polish.md`
> - `docs/user-guide/showcase-walkthrough.md` (planned-features draft)

## FEATURE:

Upgrade the `/showcase` page from a thin 11-step baseline-only demo into a
**rich operator demo control center** that exercises the full ForecastLabAI
lifecycle in one live, browser-streamed run: data creation, V1+V2 modeling,
feature-aware backtesting with horizon buckets, model registry decisions
(champion/challenger, stale aliases, safer Promote), portfolio batch sweeps,
scenario simulation + saved plans + multi-plan compare, curated RAG indexing,
agent HITL approval, and ops health snapshots — with every result deep-linkable
into the existing dashboard pages so a first-time visitor "sees the whole
system" end-to-end, not just a baseline timeline.

### Current state (2026-05-26 — `dev @ 48cddf3`, post PRP-37 PR #306 + #308)

- `frontend/src/pages/showcase.tsx` (164 LOC) is a thin shell — a "Run pipeline"
  button + two checkboxes (Re-seed first, Reset database), an 11-step flat list
  of `DemoStepCard`s, a winner banner with a "View model runs" deep link.
- Backend `app/features/demo/pipeline.py` (771 LOC) drives 11 sequential steps
  via `httpx.ASGITransport` — `precheck → reset → seed → status → features →
  train×3 → backtest×3 → register → verify → agent → cleanup`. Uses the
  `demo_minimal` scenario (3 stores × 10 products × 92 days), trains three
  baselines (naive, seasonal_naive, moving_average), registers ONE alias
  (`demo-production`) on the lowest-WAPE winner.
- WebSocket schema (`StepEvent`, `app/features/demo/schemas.py:49-72`) is
  additively extensible — `data: dict[str, Any]` payload is free-form.
- Adjacent demo machinery exists but is **NOT** invoked from `/showcase`:
  `scripts/seed_phase2_only.py`, `scripts/seed_historical_activity.py`,
  `scripts/seed_registry_from_jobs.py`, `POST /batch/forecasting`,
  `POST /scenarios/simulate` + `/plans`, `POST /rag/index/project-docs`,
  `GET /ops/summary` + `/model-health/{grain}` + `/retraining-candidates`,
  `POST /agents/sessions/{id}/approve` (HITL gate).
- The entire **PRP-37 operator UI** (Feature Frame panel, champion-compat
  badge, stale-alias chip, safer Promote dialog, batch preset + matrix picker)
  is **invisible** to a `/showcase` visitor unless they hand-craft data first.

### Gap (lifecycle coverage today vs target)

| Lifecycle stage | Production-grade story | Showcase reality today |
|-----------------|------------------------|------------------------|
| Data platform | 7 dimensional + retail-depth tables, lifecycle/replenishment/returns | Phase-1 only on `demo_minimal` |
| Feature engineering | V1 (lag/rolling/calendar) + V2 (feature frame V2 manifest) | V1 only |
| Forecasting | 11 model types across baseline / tree / additive families | 3 baselines only |
| Backtesting | Folds + horizon buckets + baseline-vs-feature-aware comparison (PRP-36) | Aggregated metrics only; no buckets, no V2 |
| Registry | Multiple runs per series, champion/challenger aliases, V-mismatch staleness | One run + one alias, no staleness |
| Safer Promote | PR #306 dialog with artifact-verify + worse-WAPE-ack + V-mismatch-ack | Never invoked |
| Batch (portfolio) | PRP-37 batch presets + matrix picker | Never invoked |
| Scenarios | Simulate + save + multi-plan compare (PRP-27) | Never invoked |
| RAG | Project-docs indexing + semantic search | Never invoked |
| Agents | HITL gate (`save_scenario` / `create_alias` / `archive_run`), multi-turn chat | One-turn chat only |
| Ops | Stale-alias card, model health table, retraining queue | Never invoked |
| Forecast Intelligence UI (PRP-37) | Feature Frame panel, champion-compat, V-mismatch, horizon buckets | Zero showcase coverage |

Bottom line: ~10 of ~40 production endpoints touched; the page sells "the
demo" but doesn't sell "the system".

### Mixed MVP + Option B strategy

The chosen strategy is **a solid MVP foundation in PRP-38, completed by three
roadmap PRPs (39, 40, 41)**. This avoids both extremes:

- **NOT Option A** (one PRP, ~5 new flat steps) — too thin; PRP-37 surfaces
  stay hidden; no operator decision flow; no cross-linking.
- **NOT Option C** (~6-8 PRPs, drag-drop ordering, persistent run history in
  the database, shareable replays, guided-tour overlay) — scope creep;
  persistent history would force new tables (violates demo slice's
  "stateless orchestrator" invariant).
- **Mixed B** — PRP-38 lands an MVP-grade foundation that is **already
  shippable on its own** (phase accordion, scenario picker, `showcase-rich`
  preset, V1 baseline + ONE V2 prophet_like run, backtest bucket visibility,
  per-step Inspect-artifact links). PRP-39..41 then incrementally add the
  decision lifecycle, planning + knowledge lifecycle, and the agent + ops +
  polish surfaces.

PRP-38 is intentionally **NOT oversized** — it ships the foundation visible to
every operator (phase grouping + scenario choice + ONE V2 run that proves V1↔V2
co-existence in the registry), and PRP-39 picks up the multi-run decision
surfaces that depend on the V2 run existing.

### Target end-state (post-PRP-41)

A `/showcase` visitor lands on a phase-accordion view with a scenario picker
(`demo_minimal` / `showcase-rich` / `sparse`), an optional phase selector,
and a "Run pipeline" button. They click Run. The page streams a phase-grouped
timeline ≤ 240 s wall-clock on `showcase-rich`:

1. **Data** — scenario load → phase-2 enrichment → historical activity backfill
2. **Modeling** — V1 baselines (parallel ×3) → V2 (`regression` + `prophet_like`)
3. **Backtesting** — feature-aware backtest with PRP-36 horizon-bucket metrics
4. **Registry decisions** — champion-compat compare (V1 vs V2 → "Not comparable"),
   stale-alias trigger emits `stale_reason="feature_frame_version_mismatch"`,
   safer-Promote dialog walk-through
5. **Portfolio** — small batch preset (e.g., `quick_baseline_sweep`) over a
   3 × 2 × 3 matrix
6. **Planning** — scenario simulate (10% price-cut assumption) → save plan →
   multi-plan compare
7. **Knowledge** — `/config/providers/health` probe → `/rag/index/project-docs`
   on a curated 5-file subset of `docs/user-guide/` → `/rag/retrieve` probe
8. **Agents** — chat session triggers `save_scenario` tool → `approval_required`
   event → one-click Approve in the step card → tool completion
9. **Ops** — `/ops/summary` + `/ops/retraining-candidates` + `/ops/model-health/{grain}`
   snapshot rendered as a small KPI grid

When the run completes, an "Inspect generated artifacts" panel renders a grid
of deep-link cards into every dashboard page that should now have populated
state (`/visualize/{forecast,backtest,batch,planner}`, `/explorer/runs`,
`/explorer/runs/{v2_run_id}` Feature Frame panel, `/explorer/runs/compare?a=&b=`
champion-compat badge, `/ops` stale-alias chip, `/knowledge` indexed corpus,
`/chat` the just-approved tool call). A persistent "last 5 runs" strip
(localStorage) lets the visitor replay parameters. A Stop button cancels an
in-flight run.

## EXAMPLES:

Read these in the order listed before sequencing the sliced PRP-38..41 INITIALs.

**Pattern this INITIAL imitates:**

- `PRPs/INITIAL/INITIAL-forecast-intelligence-index.md` — sibling umbrella + sliced
  INITIALs for the forecast-intelligence epic (PRP-35..37). Adopt its
  "Recommended PRP sequence" table layout, its dependency-graph block, and its
  "Recommended execution" enumeration verbatim where the structure fits.

**Demo slice — current state (the foundation each PRP extends):**

- `app/features/demo/pipeline.py` — `_step_table()` (line 670), `DemoContext`,
  `_HTTP_TIMEOUT=120s`, `_llm_key_present()` agent-skip gate, `_StepError`
  RFC 7807 surfacing.
- `app/features/demo/schemas.py` — `DemoRunRequest` (strict-mode), `StepEvent`
  (additively extensible `data: dict[str, Any]`), `StepStatus`, `EventType`.
- `app/features/demo/routes.py` — `POST /demo/run` (sync) + `WS /demo/stream`
  (streamed), module-level `asyncio.Lock` for "one run at a time".
- `app/features/demo/tests/test_pipeline.py` — coverage pattern each new step
  must mirror.

**Frontend — current state:**

- `frontend/src/pages/showcase.tsx` (164 LOC) — the page each PRP extends.
- `frontend/src/components/demo/demo-step-card.tsx` — the per-step renderer
  (currently flat; PRP-38 wraps it in a phase accordion).
- `frontend/src/hooks/use-demo-pipeline.ts` — the WebSocket-folding hook
  every PRP extends additively.
- `frontend/src/components/ui/accordion.tsx` — shadcn primitive PRP-38 uses
  for the phase accordion.

**Scenarios + presets:**

- `app/shared/seeder/config.py:31-40` — 7 `ScenarioPreset` enum values
  (`retail_standard`, `holiday_rush`, `high_variance`, `stockout_heavy`,
  `new_launches`, `sparse`, `demo_minimal`). PRP-38 adds an 8th
  `SHOWCASE_RICH` preset (5 stores × 15 products × 180 days).
- `app/shared/seeder/config.py:516-657` — `SeederConfig.from_scenario` is the
  factory each new preset extends.

**Multi-CLI seeders that PRP-38..39 wrap as `/seeder/*` endpoints:**

- `scripts/seed_phase2_only.py` — lifecycle/replenishment/exogenous/returns
  enrichment.
- `scripts/seed_historical_activity.py` — 36 historical jobs × 3 cutoffs ×
  3 baselines + champion/challenger aliases.

**PRP-37 surfaces each PRP must light up end-to-end:**

- `frontend/src/components/forecast-intelligence/feature-frame-panel.tsx` +
  `feature-groups-toggle.tsx` (V2 Feature Frame panel — needs a V2 run with
  full `artifacts/models/...` `artifact_uri`).
- `frontend/src/components/forecast-intelligence/champion-compatibility-badge.tsx` +
  `champion-compatibility-utils.ts` (champion-compat — needs ≥ 2 runs on the
  same grain with overlapping window and different `feature_frame_version`).
- `frontend/src/components/forecast-intelligence/horizon-bucket-table.tsx` —
  PRP-36 bucket metrics (`h_1_7`, `h_8_14`, `h_15_28`, `h_29_plus`).
- `frontend/src/components/forecast-intelligence/batch-preset-select.tsx` +
  `batch-matrix-picker.tsx` + `batch-preset-utils.ts` — 5 presets:
  `quick_baseline_sweep`, `feature_aware_comparison`,
  `champion_challenger_refresh`, `stockout_sensitive_products`,
  `high_wape_recovery`.
- `frontend/src/components/forecast-intelligence/promote-confirmation-dialog.tsx` —
  safer-Promote artifact-verify + worse-WAPE-ack + V-mismatch-ack.
- `app/features/ops/schemas.py:20-30` — `StaleReason` enum
  (`NEWER_SUCCESS_RUN`, `FEATURE_FRAME_VERSION_MISMATCH`,
  `ARTIFACT_NOT_VERIFIED`, `RUN_NOT_SUCCESS`).

**Endpoints PRPs 38..41 drive (none new — all over ASGITransport):**

- `POST /seeder/generate`, `DELETE /seeder/data`, `GET /seeder/status`
- `POST /featuresets/compute`
- `POST /forecasting/train`, `POST /forecasting/predict`,
  `GET /forecasting/runs/{id}/feature-metadata` (V2 Feature Frame panel —
  requires `artifact_uri` to resolve under `artifacts/models/`, NOT
  registry-relative `demo/...joblib`)
- `POST /backtesting/run` (with `include_baselines=true` and
  `feature_frame_version=2` for PRP-36 bucket metrics)
- `POST /registry/runs`, `PATCH /registry/runs/{id}`, `POST /registry/aliases`,
  `GET /registry/runs/{id}/verify`, `GET /registry/compare/{a}/{b}`
- `POST /batch/forecasting`
- `POST /scenarios/simulate`, `POST /scenarios`, `POST /scenarios/compare`
- `POST /rag/index/project-docs`, `POST /rag/retrieve`,
  `GET /config/providers/health` (embedding-provider probe)
- `POST /agents/sessions`, `POST /agents/sessions/{id}/chat`,
  `POST /agents/sessions/{id}/approve`
- `GET /ops/summary`, `GET /ops/retraining-candidates`,
  `GET /ops/model-health/{grain}`

## DOCUMENTATION:

**Internal — load when authoring each sliced PRP:**

- `AGENTS.md` § Architecture & Conventions — vertical-slice rule, RFC 7807,
  Pydantic v2 strict-mode policy.
- `CLAUDE.md` — operating index and the deep-dive doc map.
- `docs/_base/API_CONTRACTS.md` — every endpoint each PRP drives is
  documented here; the demo slice subsection at the bottom (`POST /demo/run`,
  `WS /demo/stream`) is the additive-contract baseline.
- `docs/_base/RUNBOOKS.md` § "Showcase page (`/showcase`) pipeline fails at
  step X" — the current incident catalogue. Each PRP extends this list
  additively for the new steps it ships.
- `docs/_base/SECURITY.md` § "LLM / Agent Security" — `agent_require_approval`
  + HITL gate (relevant to PRP-41).
- `docs/_base/DOMAIN_MODEL.md` § "Key Invariants" — registry comparable-run
  rule + stale-alias V mismatch enum value (relevant to PRP-39).
- `docs/optional-features/03-scenario-simulation-what-if-planning.md` — the
  scenarios slice's design rationale (relevant to PRP-40).
- `.claude/rules/product-vision.md` — single-host, no managed cloud, no
  notebook-first, vertical-slice. Every PRP must pass the litmus test.
- `.claude/rules/output-formatting.md` — emoji status indicators + box-line
  separators; each step card status should remain consistent with this rule.
- `.claude/rules/shadcn-ui.md` — every UI delta MUST go through `shadcn`
  skill + MCP; no hand-rolled primitives.
- `.claude/rules/test-requirements.md` — new step ⇒ new test in
  `app/features/demo/tests/test_pipeline.py` + a route test for any new
  `/seeder/*` endpoint added.
- `.claude/rules/versioning.md` — pre-1.0 `feat:` → PATCH, so all four PRPs
  bump PATCH; the 4-PRP epic produces 4 sequential PATCH releases.

**External — reference during execution (load via `mcp__claude_ai_contex7__`):**

- shadcn/ui Accordion: <https://ui.shadcn.com/docs/components/accordion>
  (phase accordion — PRP-38)
- TanStack Query mutations + streaming: <https://tanstack.com/query/latest/docs/framework/react/guides/mutations>
- React Router 7 deep linking: <https://reactrouter.com/en/main>
  (Inspect-Artifacts panel — PRP-41)
- FastAPI WebSocket: <https://fastapi.tiangolo.com/advanced/websockets/>
  (additive `StepEvent` schema — every PRP)
- PydanticAI tool-call lifecycle: <https://ai.pydantic.dev/tools/>
  (HITL approval flow — PRP-41)

**Internal artifacts from the prior epic (PRP-35..37) — read for pattern:**

- `PRPs/PRP-35-forecast-intelligence-A-feature-frame-v2.md` — pattern for an
  A-slice in a multi-PRP epic (mostly backend, defines new contracts).
- `PRPs/PRP-36-forecast-intelligence-B-model-zoo-backtesting.md` — pattern for
  a B-slice (consumes A's contracts; adds bucket metrics).
- `PRPs/PRP-37-forecast-intelligence-C-interactive-ui.md` — pattern for a
  C-slice (frontend wires the contracts A+B shipped); contains a "Task 1
  contract probe report" pattern (`PRPs/ai_docs/prp-37-contract-probe-report.md`)
  that each sliced PRP-38..41 should adopt.

## OTHER CONSIDERATIONS:

### Hard architectural constraints (DO NOT VIOLATE)

These constraints apply to every PRP in this epic. Each sliced INITIAL repeats
the constraints relevant to its scope so the PRP author can write to them
directly.

- **No new tables.** `app/features/demo/` stays stateless; persistent state
  goes to **localStorage in the browser** (run history strip in PRP-41).
- **Vertical-slice rule.** `app/features/demo/` MUST NOT import from any other
  `app/features/*` slice. Every cross-slice call uses `httpx.ASGITransport`.
  Where the demo needs functionality CLI scripts provide today (phase-2
  enrichment, historical backfill), add a new **endpoint** to the owning
  slice (e.g., `POST /seeder/phase2-enrichment` in `app/features/seeder/`),
  do not import the helper.
- **WebSocket contract is additive only.** `StepEvent` may gain new Optional
  fields (`phase_name`, `substep_index`, `substep_total`); existing fields
  may NOT change type or semantics. Bump no version key — clients ignore
  unknown additive fields.
- **Phase table is a stability invariant.** Both backend `_phase_table()` and
  frontend `PHASE_DEFS` ship in the **same PRP slice** in lockstep. A change
  to one without the other is a regression. Tests (`test_phase_table_stable`
  on both sides) enforce.
- **Skip gracefully on missing providers.** Every step that depends on an
  external provider (LLM key for `/agents/*`, embedding key for `/rag/*`)
  MUST use the `_llm_key_present()` gating pattern (`app/features/demo/pipeline.py:203`)
  and emit `skip` with a clear `detail`. A missing key is NEVER a `fail`.
- **No DB reset implied by this epic.** A `reset` option exists on the
  existing `DemoRunRequest`; it stays opt-in via the existing
  "Reset database" checkbox.

### Risks (baked into each PRP — listed by where they bite)

| # | Risk | Where it bites | Mitigation |
|---|------|----------------|------------|
| R1 | Two-artifact-root divergence — V2 runs registered with `artifact_uri = "demo/...joblib"` (registry-relative) break `/forecasting/runs/{id}/feature-metadata` because the latter resolves against `forecast_model_artifacts_dir` (`artifacts/models/`), not `registry_artifact_root`. | **PRP-38** v2_train step | V2 runs MUST set `artifact_uri = train_response["model_path"]` (full `artifacts/models/...` path). Pin in PRP-38 risks. |
| R2 | `HistGradientBoostingRegressor` (the `regression` model's wrapped estimator) exposes no `feature_importances_`; sklearn ships it on `GradientBoostingRegressor` only. The Feature Frame panel's importance section renders empty for a V2 `regression` run. | **PRP-38** v2_train step | Use `prophet_like` (Ridge → signed coefficients) for the V2 Feature Frame demo. `regression` may still be trained separately for the backtest comparison row. |
| R3 | V-mismatch staleness needs hand-crafted run pairs (same grain, overlapping window, different `feature_frame_version`). | **PRP-39** stale_alias_trigger step | Register two consecutive V2 runs with controlled `runtime_info_extras.feature_frame_version` (e.g., V=2 and a hypothetical V=3) — or simulate via two distinct (V, feature_groups) sets — so `OpsService` surfaces `stale_reason="feature_frame_version_mismatch"`. |
| R4 | RAG embedding dim mismatch — switching providers mid-corpus orphans chunks (memory `[[rag-runtime-config-and-corpus-state]]`). | **PRP-40** rag_index_subset step | Run after a fresh reset OR against a known-empty corpus; add a `clear_rag` sub-step gated by a "rebuild RAG" toggle. Use the curated `docs/user-guide/` subset only (5 files). |
| R5 | Agent HITL approval blocks until `/agents/sessions/{id}/approve` returns. Showcase needs "stuck on approval > 30 s" detection + one-click approve UI. | **PRP-41** agent_hitl_flow step | Frontend emits a callout when the `approval_required` event arrives; one-click Approve button hits the existing endpoint. Timeout fallback: surface a "skip" terminal status if no approval within 90 s. |
| R6 | `frontend/.env` LAN-IP regression (`VITE_API_BASE_URL=http://100.66.183.13:8123`) breaks `/demo/stream` from a localhost browser. Has bitten 3+ times. | **All PRPs** dogfood | Walkthrough doc (PRP-41) calls out the gotcha explicitly with the fix. Each PRP's dogfood checklist verifies the WebSocket connects. |
| R7 | HANDOFF accuracy — prior PRP-37 HANDOFF claimed `pnpm tsc --noEmit clean` but had `TS2451` errors. | **All PRPs** validation | Each PRP MUST re-run `pnpm tsc --noEmit -p tsconfig.app.json` (not `tsc --noEmit` against the thin root). Never trust prior HANDOFF green checks. |
| R8 | Multi-run lock — module-level `asyncio.Lock` allows one pipeline at a time. A second `POST /demo/run` returns 409; a second `WS /demo/stream` receives one `error` event. | **All PRPs** runtime | Existing behavior is correct; document in walkthrough that a stuck run requires explicit cancel. PRP-41 ships the Stop button. |
| R9 | CRLF/LF noise — Edit/Write on CRLF files produces whole-file diffs (memory `[[repo-line-endings-crlf]]`). | **All PRPs** commits | Confine edits to the smallest possible diff; check `git diff --stat` before committing. |

### Performance budgets

| Scenario | Target wall-clock | Per-step timeout |
|----------|-------------------|------------------|
| `demo_minimal` (existing — backwards compat) | ≤ 90 s | 120 s (`_HTTP_TIMEOUT`) |
| `showcase-rich` (new — PRP-38 preset) | ≤ 240 s | 120 s |
| Per-phase progress | ≥ 1 `step_complete` (or `substep_progress` if added) every 10 s | — |

Mitigations if a phase exceeds budget: parallel sub-steps within a phase (the
existing `step_train` pattern), skip-gracefully gates, and the scenario picker
itself (visitors can stay on `demo_minimal` for the fast loop).

### Validation plan (every PRP MUST satisfy)

**Backend gates:**

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
uv run pytest -v -m "not integration"
uv run pytest -v -m integration            # MUST include a /demo/stream e2e test
```

**Frontend gates:**

```bash
cd frontend
pnpm lint
pnpm tsc --noEmit -p tsconfig.app.json     # NOT the root tsconfig.json (it's a "files: []" shell)
pnpm test --run                            # vitest
```

**Integration / demo-stream test (per PRP, added under `app/features/demo/tests/`):**

- `test_phase_table_stable` — backend phase list matches frontend `PHASE_DEFS`
  (string list assertion).
- Per-step success + skip-gracefully test for every new step the PRP adds.

**Manual dogfood checklist (post-merge per PRP, with screenshots):**

After running `/showcase` end-to-end on a fresh DB:

- [ ] `/visualize/forecast` — Train card available, V1/V2 toggle reachable,
      picker pre-fills the showcase store/product. (PRP-38)
- [ ] `/visualize/backtest` — RMSE tile populated, horizon-bucket card renders
      per-bucket metrics, baseline-vs-feature-aware comparison table populated.
      (PRP-38)
- [ ] `/visualize/batch` — Batch preset + matrix picker reachable; the
      just-created batch appears in the list with completed items. (PRP-39)
- [ ] `/visualize/planner` — saved scenario plan visible in library; multi-plan
      compare ranks two plans. (PRP-40)
- [ ] `/explorer/runs` — at least 4 runs registered (V1 baseline winner,
      V2 regression, V2 prophet_like, V1 historical winner). (PRP-38 + PRP-39)
- [ ] `/explorer/runs/{v2_prophet_run_id}` — Feature Frame panel renders V=2
      badge + populated feature columns + signed coefs. (PRP-38)
- [ ] `/explorer/runs/compare?a={v1}&b={v2}` — champion-compat badge reads
      "Not comparable" with feature-frame-version row populated. (PRP-39)
- [ ] `/ops` — stale-alias card shows an alias with
      `feature_frame_version_mismatch` reason; Model Health table populated;
      Promote button opens the safer-promote dialog. (PRP-39 + PRP-41)
- [ ] `/knowledge` — the 5 indexed user-guide docs visible; a semantic search
      returns hits. (PRP-40)
- [ ] `/chat` — agent session with the just-completed approval visible in the
      transcript. (PRP-41)

### Stop-and-ask gates (per AGENTS.md § Safety)

Each PRP MUST stop and surface a concern before:
- Adding a managed-cloud SDK (forbidden).
- Bumping pydantic-ai / FastAPI / SQLAlchemy major versions.
- Widening the agent's mutation surface without adding the new tool name to
  `agent_require_approval` (PRP-41 only).
- Cutting `dev → main` or pushing any tag (release-please owns tagging).

### Pre-execution contract probe (mandatory per PRP)

Each PRP-38..41 task list MUST start with a **Task 1 — Contract Probe**
mirroring `PRPs/ai_docs/prp-37-contract-probe-report.md`:

- Verify every backend field/endpoint the PRP cites exists on `dev`.
- Verify the response shape the frontend code wires to.
- Output the probe to `PRPs/ai_docs/prp-{N}-contract-probe-report.md`.
- Stop and patch the PRP's wording if any cited contract is absent or drifted.

This prevents the field-name drifts and absent-field issues PRP-37 hit
(`bucketed_aggregate` vs `bucketed_aggregated`, `n_comparable_runs`,
`is_known_future`).

### Recommended execution

1. Generate the umbrella INITIAL (this file) and the four sliced INITIALs and
   the index doc — **all planning, no code**.
2. From `INITIAL-showcase-38-data-modeling-lifecycle.md`, generate
   `PRPs/PRP-38-showcase-data-modeling-lifecycle.md` via `/base_prp:prp-create`.
3. Implement and merge PRP-38 on a `feat/showcase-38-*` branch off `dev`.
4. Generate PRP-39 against the actual PRP-38 result (contract probe first).
5. Implement and merge PRP-39.
6. Same loop for PRP-40 and PRP-41.

Each PRP lands as one PATCH release (pre-1.0 `feat:` → PATCH).

### Future issue titles (suggested)

- `feat(api,ui): showcase pipeline — richer data + V1/V2 modeling foundation` (PRP-38)
- `feat(api,ui): showcase pipeline — decision + portfolio lifecycle` (PRP-39)
- `feat(api,ui): showcase pipeline — planning + knowledge lifecycle` (PRP-40)
- `feat(api,ui): showcase pipeline — agent + ops + final polish` (PRP-41)
