name: "PRP-39 — Showcase Rich Demo Control Center B: Decision + Portfolio Lifecycle"
description: |
  Extend the in-process demo pipeline so a single `/showcase` `showcase-rich`
  run walks a first-time visitor through an operator's *decision*: how a V1
  baseline stacks up against a V2 feature-aware run (champion-compat), how a
  V-mismatch lights up the `/ops` stale-alias chip, how the safer-Promote
  dialog gates fire when the alias swaps to a worse-WAPE run, and how a
  3 × 2 × 3 portfolio batch finishes on the showcase grain. Slice B of the
  four-PRP `/showcase` upgrade epic (PRP-38..41).

  > **PREREQUISITES — PRP-38 merged.** PRP-39 consumes the V2 prophet_like
  > run PRP-38 registers on the showcase grain (`champion_compat_compare`
  > anchors on it; `stale_alias_trigger` registers a SECOND V on that same
  > grain to fire the V-mismatch). PRP-39 is the SECOND of four PRPs in the
  > epic.
  >
  > **PRP-41 is NOT in scope.** Agent HITL, ops snapshot card, KPI strip,
  > Inspect-Artifacts post-run panel, localStorage last-5-runs strip, Stop
  > button, walkthrough docs polish — every one of these belongs to PRP-41.
  > Mention them ONLY in the "Out of Scope" block; do not implement, stub,
  > or scaffold.

## Purpose

A one-pass implementation contract for an AI agent (or human) with access
to the codebase but no prior session context. Insert three new steps
into the EXISTING `decision` phase (PRP-38 shipped `backtest` →
`register`) AFTER `register`, and add a brand-new `portfolio` phase
between `decision` and `verify`. Every change is additive — no contract
change to the registry / ops / batch slices, no new tables, no
agent_require_approval widening.

## Core Principles

1. **Backend contracts are read-only.** Every backend surface PRP-39 hits
   already exists on `dev` at `3e771c9` (PRP-38 merged). The Task-1
   contract probe (`PRPs/ai_docs/prp-39-contract-probe-report.md`)
   verifies presence + records three drift resolutions (D1, D2, D3); the
   PRP wires the new steps to the resolved shapes.
2. **Vertical-slice rule (load-bearing).** `app/features/demo/` MUST NOT
   import from any other `app/features/*` slice. Every backend call goes
   through `httpx.ASGITransport` exactly like the existing
   `step_register` + `step_v2_train` chain. Grep guard
   `git grep -nE "from app\.features\.[^.]+\." app/features/demo/ | grep -v "from app.features.demo"`
   MUST remain empty after PRP-39 edits. The `app.shared.*` /
   `app.core.*` imports are allowed.
3. **WebSocket contract is ADDITIVE ONLY.** Every new step emits the
   same `StepEvent` shape PRP-38 already ships. `phase_name`,
   `phase_index`, `phase_total` are populated for the new
   `decision`-extension steps AND for the new `portfolio` phase. No
   schema field bump; no version key bump; legacy clients ignore the new
   `step_name` values gracefully.
4. **Phase-table lockstep — RELATIVE ANCHORS ONLY.** Backend
   `_phase_table()` and frontend `PHASE_DEFS.ts` ship in the SAME PRP
   slice and stay lockstep. The lockstep test
   `test_phase_table_stable` (backend) + `PHASE_DEFS.test.ts` (frontend)
   are the gate. Every `_phase_table()` / `PHASE_DEFS` edit is phrased
   as "insert AFTER the `<anchor>` row" or "insert BEFORE the `<anchor>`
   phase row" — NEVER an absolute index. **Reason:** PRP-40 is a sibling
   slice that also touches both files; the second-to-merge slice must
   rebase cleanly against the first (see § "Parallel-merge coordination"
   below).
5. **No new tables.** `app/features/demo/` stays stateless. No Alembic
   migration is part of PRP-39.
6. **Skip gracefully.** None of PRP-39's steps depend on external
   providers; if a PRP-38 V2 run is missing (e.g., user ran
   `demo_minimal` instead of `showcase_rich`), `champion_compat_compare`
   emits `skip` with `detail="no V2 run on the showcase grain — run with
   scenario=showcase_rich"` (R14). Documented for consistency with
   PRP-40 / PRP-41.
7. **Pre-1.0 contract additivity.** Every new field is Optional; no
   `feat!:` / breaking commit. PRP-39 is purely additive.
8. **HITL stays bypass-free for the demo slice.** The demo pipeline
   POSTs `/registry/aliases` directly (as PRP-38 already does in
   `step_register`); HITL is an *agent-tool* gate, not an HTTP-layer
   one. PRP-39 does NOT add a new tool to `agent_require_approval`;
   PRP-41's agent flow does that.

---

## Goal

Deliver, on branch `feat/showcase-39-decision-portfolio-lifecycle`,
slice B of the `/showcase` rich demo upgrade so a first-time visitor
running `/showcase` with `scenario=showcase-rich` sees:

- A new `champion_compat_compare` step card in the `decision` phase
  showing `V_a=1 · V_b=2 · compatible=false · reason=feature_frame_version_mismatch`,
  with an Inspect button deep-linking to
  `/explorer/runs/compare?a={v1_run_id}&b={v2_run_id}` where the
  "Not comparable" champion-compatibility badge renders.
- A `stale_alias_trigger` step card showing the alias name +
  `stale_reason="feature_frame_version_mismatch"` chip, with an Inspect
  button deep-linking to `/ops` (the stale-alias row is now visible
  there).
- A `safer_promote_flow` step card showing before/after run_id chips,
  with an Inspect button deep-linking to `/ops` (the Promote button on
  the new champion row opens the safer-Promote dialog with the
  worse-WAPE-ack + V-mismatch-ack gates fired).
- A new `portfolio` phase between `decision` and `verify`, with one
  `batch_preset` step card showing
  `kind=MANUAL · preset_source=quick_baseline_sweep · 18/18 completed`
  (or `15/18 partial`, etc.), Inspect button deep-linking to
  `/visualize/batch/{batch_id}`.
- The `cleanup` phase restores the `demo-production` alias to the
  original V2 winner before the run finishes (R15).
- 7 phases render in the accordion (PRP-38 shipped 6; PRP-39 adds the
  new `portfolio` phase).

## Why

Without PRP-39, the `/showcase` page demonstrates only the *training*
half of the model lifecycle (data → V1 + V2 → backtest → register
winner). It never shows the *decision* half — the operator-facing
moments PRP-37 built UI surfaces for:

- The champion-compat badge that catches a cross-V comparison (V1 vs V2
  is "not comparable" — same model_type can mean different feature
  contracts).
- The stale-alias chip that surfaces a V-mismatch separately from a
  newer-run-exists staleness.
- The safer-Promote dialog with worse-WAPE-ack + V-mismatch-ack
  checkboxes that gate alias swaps.
- The portfolio batch preset that lets an operator forecast across
  multiple grains in one click.

PRP-39 is the slice that makes those surfaces *visible* in the
`/showcase` walkthrough — without it, a visitor has to hand-craft data
on `/explorer/*` to see them light up.

## What

### User-visible behaviour

- `/showcase` with `scenario=showcase-rich` renders 7 phase cards in
  idle state (PRP-38 shipped 6; PRP-39 adds `portfolio`).
- The `decision` phase accordion now shows 5 step rows in order:
  `backtest` → `register` → `champion_compat_compare` →
  `stale_alias_trigger` → `safer_promote_flow` (PRP-38 shipped 2;
  PRP-39 adds 3).
- The `portfolio` phase accordion shows 1 step row: `batch_preset`.
- The `cleanup` phase step card detail now includes "alias restored to
  V2 winner".
- Each new terminal-pass step card carries an Inspect button:
  - `champion_compat_compare` → `/explorer/runs/compare?a={v1_run_id}&b={v2_run_id}`
  - `stale_alias_trigger` → `/ops`
  - `safer_promote_flow` → `/ops`
  - `batch_preset` → `/visualize/batch/{batch_id}`
- Each new step card carries a one-row mini summary chip-line above the
  Inspect button (see § Implementation Blueprint § Task 10 for the
  exact strings).

### Technical requirements

- Backend: ruff + ruff format + mypy `--strict` + pyright `--strict`
  clean on `app/features/demo/pipeline.py` and
  `app/features/demo/tests/test_pipeline.py`. RFC 7807 errors via
  `app/core/problem_details.py`; no bare `HTTPException(500, "...")`.
- Frontend: `pnpm tsc --noEmit -p tsconfig.app.json` clean (NOT bare
  `pnpm tsc --noEmit`). `pnpm lint` + `pnpm test --run` clean.
- Vertical-slice rule preserved:
  `git grep -nE "from app\.features\.[^.]+\." app/features/demo/ | grep -v "from app.features.demo"`
  MUST be empty after PRP-39 edits.
- WebSocket contract additive only:
  `git diff app/features/demo/schemas.py` MUST show ZERO field
  additions or removals; the four new steps reuse the existing
  `StepEvent` shape.
- Performance: `showcase-rich` ≤ 240 s wall-clock (unchanged total
  budget); PRP-39 adds ≤ 60 s. Per-step timeout 120 s (`_HTTP_TIMEOUT`,
  unchanged).
- No new env vars; no managed-cloud SDK; no new tables; no agent
  mutation surface change; no `agent_require_approval` widening.

### Success Criteria (mirrors INITIAL-39 B1..B7)

- [ ] **B1** — After a `showcase-rich` run,
      `/explorer/runs/compare?a={v1}&b={v2}` renders the champion-compat
      badge "Not comparable" with `feature_frame_version` populated on
      both runs (verified via manual dogfood).
- [ ] **B2** — After a `showcase-rich` run, `/ops` shows a stale-alias
      row with `stale_reason="feature_frame_version_mismatch"` and the
      V mismatch detail row (`alias_feature_frame_version` +
      `comparable_run_feature_frame_version`) populated.
- [ ] **B3** — After a `showcase-rich` run, the `/ops` Promote button on
      the new champion run opens the safer-Promote dialog with the
      worse-WAPE-ack gate (if applicable) AND V-mismatch-ack gate (if
      applicable) fired.
- [ ] **B4** — After a `showcase-rich` run,
      `/visualize/batch/{batch_id}` shows the batch with completed items
      + the preset-source chip
      (`kind=MANUAL · preset_source=quick_baseline_sweep`, per D2 in
      probe report).
- [ ] **B5** — `showcase-rich` end-to-end (PRP-38 + PRP-39 phases)
      finishes ≤ 240 s on `dev` hardware
      (`pytest -m integration tests/test_e2e_demo.py::test_e2e_showcase_rich_decision_portfolio`).
- [ ] **B6** — Backend `_phase_table()` and frontend `PHASE_DEFS` still
      match in order AND name; `test_phase_table_stable` (backend) +
      `PHASE_DEFS.test.ts` (frontend) both green.
- [ ] **B7** — All five validation gates green: ruff + ruff format +
      mypy + pyright + pytest (unit + integration) + migration-check;
      `pnpm lint && pnpm tsc --noEmit -p tsconfig.app.json && pnpm test --run`
      green from `frontend/`.
- [ ] CHANGELOG entry under "Unreleased":
      `feat(api,ui): showcase pipeline — decision + portfolio lifecycle (#<issue>)`.

### Out of Scope (explicit — do NOT implement in PRP-39)

These belong to later PRPs in the epic. Mention only in the walkthrough
disclaimer; do not scaffold, stub, or render placeholders.

- **PRP-40 (planning + knowledge)** — scenario simulate / save / multi-
  plan compare, `/config/providers/health` embedding-provider probe,
  `/rag/index/project-docs` curated 5-file corpus, `/rag/retrieve`
  probe. The `planning` + `knowledge` phases PRP-40 inserts ALSO use
  relative-anchor insertion; PRP-39 and PRP-40 are sibling slices.
- **PRP-41 (agent + ops + polish)** — agent HITL flow with
  `save_scenario` approval, `/ops/summary` + `/ops/retraining-candidates`
  + `/ops/model-health/{grain}` snapshot KPI strip, Inspect-Artifacts
  post-run grid panel, localStorage last-5-runs strip, Stop button,
  walkthrough docs polish (`docs/user-guide/showcase-walkthrough.md`).

### Parallel-merge coordination — relative phase anchors

PRP-39 and PRP-40 are sibling slices both touching `_phase_table()`
+ `PHASE_DEFS.ts`. To stay merge-order independent:

- PRP-39 INSERTs `("portfolio", "batch_preset", step_batch_preset)`
  BETWEEN the `decision` phase rows and the `verify` phase rows. The
  insertion point is named relative to the existing `PHASE_VERIFY`
  anchor: "rows.extend ... portfolio BEFORE the `verify` phase block".
- PRP-40 INSERTs its `planning` + `knowledge` phases at a different
  relative anchor (TBD by PRP-40; e.g., AFTER `portfolio` or BEFORE
  `agent`). PRP-39 does NOT bake an assumption about PRP-40's anchor.
- Both PRPs run the lockstep test after merge — if PRP-40 lands AFTER
  PRP-39, PRP-40's frozen-fixture update lands in PRP-40's PR; the
  PRP-39 fixture stays untouched.
- The frozen-fixture file
  (`app/features/demo/tests/test_pipeline.py::test_phase_table_stable`)
  references phase IDs by string + position-WITHIN-block (e.g., "the
  third `decision`-phase row is `champion_compat_compare`"), NOT by
  absolute index.

---

## All Needed Context

### Documentation & References

```yaml
# ─── Epic INITIAL bundle (load first, in this order) ─────────────────
- file: PRPs/INITIAL/INITIAL-showcase-rich-demo-control-center.md
  why: Umbrella INITIAL — strategy, risk register (R1..R15), performance budgets. PRP-39 is slice B; every umbrella constraint applies.

- file: PRPs/INITIAL/INITIAL-showcase-rich-demo-index.md
  why: Sequence + dependency graph. PRP-39 depends on PRP-38; PRP-41 depends on PRP-39 + PRP-40.

- file: PRPs/INITIAL/INITIAL-showcase-39-decision-portfolio-lifecycle.md
  why: Source of truth for THIS PRP's scope. Re-read on disagreement. Acceptance criteria B1..B7 are the verifiable contract.

# ─── Contract probe (load BEFORE any code change) ─────────────────────
- docfile: PRPs/ai_docs/prp-39-contract-probe-report.md
  why: D1 (compare envelope), D2 (preset Option A), D3 (sync settle). Every PRP-39 task descends from these resolutions. Read FIRST; the PRP-39 implementation re-derives nothing the probe already resolved.

# ─── Predecessor probes (pattern reference) ───────────────────────────
- docfile: PRPs/ai_docs/prp-38-contract-probe-report.md
  why: Probe report structure to mirror. Inherited finding: `RunUpdate` cannot patch `runtime_info` — V MUST be set on POST /registry/runs. PRP-39's `stale_alias_trigger` honours this.

- docfile: PRPs/ai_docs/prp-37-contract-probe-report.md
  why: Same probe structure precedent.

# ─── Project rules (enforce mechanically) ────────────────────────────
- file: AGENTS.md
  why: Universal agent brief — vertical-slice rule, validation gates, RFC 7807 envelope, hard-rules list, agent_require_approval invariant.

- file: CLAUDE.md
  why: Claude operating index — pulls in the docs/_base/* deep-dive references; AGENTS.md is imported at the top.

- file: .claude/rules/test-requirements.md
  why: Every new pipeline step ⇒ a step test; every new endpoint (none here) ⇒ a route test; every bug fix ⇒ a regression test.

- file: .claude/rules/security-patterns.md
  why: RFC 7807 errors only; no raw `HTTPException(500, "…")`. PRP-39 adds no new endpoints, but the new pipeline steps surface RFC 7807 via `_StepError` exactly like every other step.

- file: .claude/rules/output-formatting.md
  why: Step-detail strings stay terse + scannable (one-line summary + status indicator).

# ─── Backend codebase anchors (demo slice — the slice this PRP extends) ─
- file: app/features/demo/pipeline.py
  why: |
    The slice PRP-39 extends. Key anchors:
      - `_HTTP_TIMEOUT` at line 77 — 120 s per-step timeout (unchanged).
      - `_StepError` at line 85 — RFC 7807-aware exception surface.
      - `_Client` at line 106 — ASGI HTTP wrapper.
      - `DemoContext` at line 167 — accumulator threaded through every step. PRP-39 ADDS Optional fields: `compat_compare_result`, `stale_alias_run_id`, `original_demo_alias_run_id` (so cleanup can restore), `batch_id`, `batch_status`.
      - `step_register` at line 887 — pattern for create+running+success+alias POSTs (mirror for `stale_alias_trigger`).
      - `step_v2_train` at line 753 — pattern for V2 register-with-`runtime_info_extras` (mirror for `stale_alias_trigger`'s register-with-controlled-V).
      - `step_cleanup` at line 1088 — currently closes the agent session; PRP-39 EXTENDS it to ALSO restore the alias (R15).
      - `_phase_table()` at line 1118 — function PRP-39 extends with new rows.
      - Phase constants at lines 1110-1115 — PRP-39 ADDS `PHASE_PORTFOLIO = "portfolio"` between `PHASE_DECISION` and `PHASE_VERIFY`.
      - `run_pipeline` at line 1166 — orchestrator; no changes needed (it reads `_phase_table` results).

- file: app/features/demo/schemas.py
  why: `StepEvent` at line 64 — unchanged in PRP-39. `DemoRunRequest` at line 29 — unchanged. PRP-39 does NOT add wire fields.

- file: app/features/demo/tests/test_pipeline.py
  why: The coverage pattern each new step MUST mirror. PRP-39 ADDS `test_champion_compat_compare_step`, `test_stale_alias_trigger_step`, `test_safer_promote_step`, `test_batch_preset_step`, `test_cleanup_restores_alias`, plus a `test_phase_table_stable_showcase_rich_v2` (or extend the existing one) that asserts the new 4 step rows are in the canonical order.

# ─── Backend codebase anchors (registry / ops / batch slices PRP-39 hits over ASGI) ─
- file: app/features/registry/routes.py
  why: |
    - `POST /registry/runs` (lines ~88-180) — used by `stale_alias_trigger` (register a SECOND V2 run with `runtime_info_extras.feature_frame_version` set to a value DIFFERENT from PRP-38's V2 run).
    - `PATCH /registry/runs/{id}` (lines ~250-330) — used to drive pending→running→success.
    - `POST /registry/aliases` (lines ~430-500) — used by `safer_promote_flow` to swap the alias.
    - `GET /registry/compare/{a}/{b}` at line 582 — used by `champion_compat_compare` (PRP-39 derives `compatible` + `comparable_reason` + V_a/V_b client-side per D1; see probe report § D1).

- file: app/features/registry/schemas.py
  why: |
    - `RunCreate.runtime_info_extras` at lines 85-95 — accepts arbitrary keys including `feature_frame_version` (the lever for the V mismatch).
    - `RunResponse.feature_frame_version` (computed_field) at lines 179-192 — the value the compatibility predicate reads.
    - `RunCompareResponse` at lines 243-249 — ONLY `run_a`/`run_b`/`config_diff`/`metrics_diff`; NO top-level compatibility flags. PRP-39 derives those client-side per D1.

- file: app/features/registry/service.py
  why: |
    - `find_comparable_runs` at lines 726-778 — the comparable-run rule (same grain + overlapping window + same V; non-success excluded). The same predicate `OpsService._alias_staleness` uses.
    - `_find_duplicate` at lines 656-707 — V-aware duplicate matching; lets PRP-39's `stale_alias_trigger` register a second run with a fresh config without colliding.
    - `_feature_frame_version_filter` at lines 709-724 — `runtime_info["feature_frame_version"]` filter; legacy rows without the key are V=1.

- file: app/features/ops/schemas.py
  why: |
    - `StaleReason.FEATURE_FRAME_VERSION_MISMATCH` at line 28 — enum value PRP-39's `stale_alias_trigger` aims to surface.
    - `AliasHealth.alias_feature_frame_version` + `.comparable_run_feature_frame_version` at lines 161-174 — the V mismatch detail rows.

- file: app/features/ops/service.py
  why: |
    - `_alias_staleness` at lines 162-214 — V-mismatch wins over `NEWER_SUCCESS_RUN`; fires when alias_v ≠ latest_comparable_v on same grain. PRP-39 exploits this by injecting a SECOND V2 run with a controlled-V on the SAME grain as the existing alias's V2 run.
    - `_run_feature_frame_version` helper at lines 130-159 — legacy missing-key runs normalize to V=1.

- file: app/features/batch/schemas.py
  why: |
    - `BatchSubmitRequest` at lines 116-136 — `operation` + `scope` + `model_configs[]` + `start_date` + `end_date`. No `preset_id` field (Option A, per D2 in probe report).
    - `BatchScope.kind: Literal["manual", ...]` at line 71 — lowercase value.
    - `BatchModelConfig` at lines 99-113 — only `model_type` + `params`; no V2 fields on the backend (frontend type at `frontend/src/types/api.ts:427-448` diverges — out of scope for PRP-39).
    - `BatchSubmitResponse` at lines 164-205 — `total_items`, `completed_items`, `failed_items`, `running_items`, `cancelled_items`. NOT `item_count`/`completed_count` (INITIAL-39 field names are wrong; see probe report § C drift row).

- file: app/features/batch/routes.py
  why: |
    - `POST /batch/forecasting` at lines 34-52 — submit runs sequentially in-request and returns the settled parent (per D3 in probe report). Polling is a safety net, not the normal path.
    - `GET /batch/{batch_id}` at lines 55-72 — used for the 90 s safety poll.

- file: app/features/batch/models.py
  why: `BatchStatus` enum values at lines 46-60 — `pending`, `running`, `completed`, `failed`, `partial`, `cancelled`. PRP-39 maps `completed` → `pass`, `partial` → `warn`, `failed`/`cancelled` → `fail`, poll timeout → `warn`.

# ─── Frontend codebase anchors (UI PRP-39 extends) ────────────────────
- file: frontend/src/components/demo/PHASE_DEFS.ts
  why: |
    Single source of truth for phase grouping. PRP-39:
      - APPENDS three rows to the `decision` phase block (lines 39-40 currently `backtest`, `register`):
        `{ phase: 'decision', step: 'champion_compat_compare', label: 'Compare V1 vs V2' }`
        `{ phase: 'decision', step: 'stale_alias_trigger', label: 'Trigger stale-alias V mismatch' }`
        `{ phase: 'decision', step: 'safer_promote_flow', label: 'Safer Promote walkthrough' }`
      - INSERTS a NEW phase block `portfolio` BETWEEN `decision` and `verify` (currently between lines 40 and 41):
        `{ phase: 'portfolio', step: 'batch_preset', label: 'Portfolio batch (quick baseline sweep)' }`
      - APPENDS `'portfolio'` to `PHASE_ORDER` (currently lines 72-79) between `'decision'` and `'verify'`.
      - APPENDS `portfolio: 'Portfolio'` to `PHASE_LABEL` (lines 62-69).
      - Updates the `SHOWCASE_RICH_STEP_NAMES` set at lines 46-50 to include all 4 new step names so they only render under `scenario=showcase_rich`.

- file: frontend/src/pages/showcase.tsx
  why: |
    `resolveInspectHref` at lines 26-50 — the function PRP-39 extends. Add 4 new `case` arms (one per new step name) returning the Inspect deep-link strings per § Goal. PRP-39 also adds `getInspectHref` augmentation (similar to the current `train`/`backtest` grain-id forwarding pattern at lines 86-105) where the new step's `step.data` doesn't already carry the deep-link inputs.

- file: frontend/src/components/demo/demo-step-card.tsx
  why: Card renderer that PRP-39 extends with one-row mini-summary chip-lines for each of the four new steps (see § Implementation Blueprint § Task 10 for exact mini-summary strings).

- file: frontend/src/lib/constants.ts
  why: `ROUTES.EXPLORER.RUN_COMPARE` at line 20, `ROUTES.OPS` at line 5, `ROUTES.VISUALIZE.BATCH` at line 27. All deep-link strings PRP-39 reads from this map (never raw-concatenate).

# ─── Frontend codebase anchors (deep-link targets — read-only) ─────────
- file: frontend/src/components/forecast-intelligence/champion-compatibility-utils.ts
  why: |
    `computeCompatibility` at lines 14-47 — the CLIENT-SIDE predicate PRP-39's `champion_compat_compare` step MIRRORS in Python. Predicate: same grain + overlapping window + same V. Returns `{ ok, reason }` where `reason ∈ {"Different grain (store + product)", "Unparseable data-window dates", "No data-window overlap", "Different feature frame version (V{va} vs V{vb})"}`. The PRP-39 step emits `comparable_reason="feature_frame_version_mismatch"` (the WIRE enum value from `StaleReason.FEATURE_FRAME_VERSION_MISMATCH`) — NOT the human-readable string — so the same reason key works for both the compare card and the ops chip.

- file: frontend/src/components/forecast-intelligence/champion-compatibility-badge.tsx
  why: |
    The badge that renders "Not comparable" on `/explorer/runs/compare`. PRP-39 does NOT modify it — the page already feeds it `run_a` + `run_b` from the compare endpoint. PRP-39 only ensures the V1+V2 pair exists in the DB so the badge lights up.

- file: frontend/src/components/forecast-intelligence/promote-confirmation-dialog.tsx
  why: |
    The safer-Promote dialog `safer_promote_flow` triggers. Three gates: artifact-verifies + worse-WAPE-ack + V-mismatch-ack. PRP-39 step does NOT exercise the dialog itself — it just creates the alias-swap that, when a HUMAN visits `/ops`, surfaces the dialog with the appropriate gates fired. Verified in manual dogfood.

- file: frontend/src/components/forecast-intelligence/batch-preset-utils.ts
  why: |
    `BATCH_PRESETS` at lines 22-53 — `quick_baseline_sweep` is the first preset, with 5 baseline model_types (PRP-37). PRP-39 picks the FIRST 3 (`naive`, `seasonal_naive`, `moving_average`) for the 3×2×3 = 18-item budget. The Python constant in `app/features/demo/pipeline.py` carries the SAME 3 model_types with a citation comment.

# ─── Test patterns ──────────────────────────────────────────────────
- file: app/features/demo/tests/test_pipeline.py
  why: |
    Each new step gets a sibling unit test driving `step_<name>(ctx, _Client(app))` directly. Use `httpx.ASGITransport(app=app, raise_app_exceptions=False)` per `app/features/demo/pipeline.py:120`. PRP-38 added 5 step tests; PRP-39 adds 4 (`test_champion_compat_compare_step`, `test_stale_alias_trigger_step`, `test_safer_promote_step`, `test_batch_preset_step`) + 1 cleanup-restore (`test_cleanup_restores_alias`).

- file: tests/test_e2e_demo.py
  why: PRP-38 added `test_e2e_showcase_rich` with a ≤ 240 s soft-warn + ≤ 300 s hard-fail. PRP-39 EXTENDS it (or adds a new `test_e2e_showcase_rich_decision_portfolio`) that additionally asserts (a) the four new step events fire, (b) `/ops/summary` lists at least one stale alias with `feature_frame_version_mismatch`, (c) `/registry/compare/.../...` returns a 200 with `run_a.feature_frame_version=null` (V1) + `run_b.feature_frame_version=2` (V2), (d) `/batch/{batch_id}` is terminal.

- file: frontend/src/components/demo/PHASE_DEFS.test.ts
  why: Backend lockstep — PRP-39 extends the test fixture with the 4 new (phase, step) tuples in canonical order. The DEMO_MINIMAL fixture stays at 11 entries; the SHOWCASE_RICH fixture grows from 14 to 18.

# ─── External docs (load on demand via mcp__claude_ai_contex7__) ─────
- url: https://ui.shadcn.com/docs/components/alert-dialog
  section: "Examples → With trigger"
  critical: The safer-Promote dialog uses AlertDialog. PRP-39 does NOT modify the dialog; the step just sets up the alias-swap that makes it render the right gates.

- url: https://ui.shadcn.com/docs/components/badge
  section: "Variants"
  critical: The "Not comparable" badge and the stale-reason chip both use Badge. PRP-39 only feeds the data; no new variant.

- url: https://tanstack.com/query/latest/docs/framework/react/guides/query-options
  section: "refetchInterval"
  critical: NOT used in PRP-39 — the `batch_preset` step polls SERVER-SIDE inside the pipeline; the frontend just renders the terminal state from `step.data`.

# ─── Memory anchors (carry from PRP-38) ─────────────────────────────
- memory: dogfood-stale-uvicorn-port-8123
  why: Check `ps -ef | grep '[u]vicorn'` before claiming UI changes work; a previous-session uvicorn may still serve stale code on :8123.

- memory: playwright-dogfood-snap-chromium
  why: Dogfood via the `webapp-testing` skill, or native Python Playwright with `executable_path=/snap/bin/chromium`. Playwright MCP fails on this host.

- memory: repo-line-endings-crlf
  why: Some files in this repo are CRLF; `Edit`/`Write` emit LF. Run `git diff --stat` before committing; whole-file noise diffs go in a separate normalisation commit (not in this PRP).

- memory: scenario-run-id-vs-registry-run-id
  why: PRP-39 ONLY uses REGISTRY run_ids (the `run_id` returned by `POST /registry/runs`). No scenarios-slice run_ids touch the pipeline.

- memory: seeder-does-not-reset-id-sequences
  why: PRP-39's `batch_preset` step uses 3 stores × 2 products on the showcase grain's NEIGHBOURS. The 3 stores are discovered via `GET /dimensions/stores?limit=5` (mirroring `step_status` at `pipeline.py:307-356`); never hardcoded.

- memory: back-merge-needs-merge-commit
  why: Sibling PRP-40 may merge before PRP-39; if so, PRP-39's back-merge of dev needs a merge commit (not squash) so the phase-table-stable test rebases cleanly.
```

### Current Codebase tree (relevant subset)

```
app/
├── features/
│   ├── demo/
│   │   ├── pipeline.py                # 1277 LOC — the file PRP-39 extends
│   │   ├── routes.py                  # POST /demo/run, WS /demo/stream — unchanged in PRP-39
│   │   ├── schemas.py                 # 137 LOC — unchanged in PRP-39
│   │   ├── service.py                 # tiny — unchanged
│   │   └── tests/
│   │       ├── test_pipeline.py       # extended with 4 + 1 new tests
│   │       └── test_routes.py
│   ├── registry/
│   │   ├── routes.py                  # 621 LOC — read-only; PRP-39 hits over ASGI
│   │   ├── schemas.py                 # 250 LOC — read-only
│   │   └── service.py                 # 875 LOC — read-only
│   ├── ops/
│   │   ├── schemas.py                 # 386 LOC — read-only
│   │   └── service.py                 # 614 LOC — read-only
│   └── batch/
│       ├── routes.py                  # 190 LOC — read-only
│       ├── schemas.py                 # 214 LOC — read-only
│       └── service.py                 # read-only
frontend/
├── src/
│   ├── pages/
│   │   └── showcase.tsx               # 164 LOC + (PRP-38 ext) — `resolveInspectHref` extended
│   ├── components/
│   │   ├── demo/
│   │   │   ├── PHASE_DEFS.ts          # 80 LOC — extended with 4 rows + 1 phase
│   │   │   ├── PHASE_DEFS.test.ts     # fixture extended
│   │   │   ├── demo-step-card.tsx     # mini-summary chip-line added for 4 new steps
│   │   │   └── demo-step-card.test.tsx
│   │   └── forecast-intelligence/
│   │       ├── champion-compatibility-utils.ts   # read-only (mirror predicate)
│   │       ├── champion-compatibility-badge.tsx  # read-only
│   │       ├── promote-confirmation-dialog.tsx   # read-only
│   │       └── batch-preset-utils.ts             # read-only (source of model_type list)
│   └── lib/constants.ts               # read-only (ROUTES map)
PRPs/
└── ai_docs/
    └── prp-39-contract-probe-report.md   # Task 1 output
tests/
└── test_e2e_demo.py                     # extended with showcase-rich + decision/portfolio assertions
docs/
└── _base/
    └── RUNBOOKS.md                       # extended with 4 new failure-mode rows
```

### Desired Codebase tree (additive + modified files)

```
app/
└── features/
    └── demo/
        ├── pipeline.py                # MODIFY — adds 4 step funcs + new PHASE_PORTFOLIO constant + extends _phase_table + extends DemoContext + extends step_cleanup
        └── tests/
            └── test_pipeline.py       # MODIFY — adds test_champion_compat_compare_step, test_stale_alias_trigger_step, test_safer_promote_step, test_batch_preset_step, test_cleanup_restores_alias, extends test_phase_table_stable
frontend/
└── src/
    ├── pages/
    │   └── showcase.tsx               # MODIFY — extends resolveInspectHref with 4 new step cases
    └── components/
        └── demo/
            ├── PHASE_DEFS.ts          # MODIFY — adds 4 step rows + portfolio phase
            ├── PHASE_DEFS.test.ts     # MODIFY — extends fixture
            ├── demo-step-card.tsx     # MODIFY — adds 4 mini-summary chip-lines
            └── demo-step-card.test.tsx # MODIFY — adds 4 mini-summary render tests
tests/
└── test_e2e_demo.py                   # MODIFY — adds test_e2e_showcase_rich_decision_portfolio (or extends existing)
docs/
└── _base/
    └── RUNBOOKS.md                    # MODIFY — adds 4 new failure-mode entries under "Showcase page (/showcase) pipeline fails at step X"
PRPs/
└── ai_docs/
    └── prp-39-contract-probe-report.md   # CREATE — Task 1 output (already written by Task 1)
```

### Known Gotchas of our codebase & Library Quirks

```python
# ─────────────────────────────────────────────────────────────────────────
# D1 — RunCompareResponse has NO compatibility flag on the wire.
# ─────────────────────────────────────────────────────────────────────────
# The compare endpoint returns ONLY {run_a, run_b, config_diff,
# metrics_diff} (verified via probe report § (a)). The "Not comparable"
# verdict is computed CLIENT-SIDE by
# `frontend/src/components/forecast-intelligence/champion-compatibility-utils.ts:14-47`
# (`computeCompatibility`).
#
# RULE for step_champion_compat_compare: MIRROR the predicate in Python.
# - same (store_id, product_id) grain? else compatible=false,
#   reason="grain_mismatch".
# - data-window overlap? (a.data_window_end >= b.data_window_start AND
#   b.data_window_end >= a.data_window_start). Else compatible=false,
#   reason="no_window_overlap".
# - same feature_frame_version (None coerced to V=1)? else
#   compatible=false, reason="feature_frame_version_mismatch".
# - else compatible=true, reason=None.
#
# step.data emits: {v1_run_id, v2_run_id, feature_frame_version_a,
# feature_frame_version_b, compatible, comparable_reason}. The
# frontend step card mini-summary reads these keys directly.

# ─────────────────────────────────────────────────────────────────────────
# D2 — quick_baseline_sweep is frontend-only; pick Option A (client-side).
# ─────────────────────────────────────────────────────────────────────────
# `BatchSubmitRequest` does NOT accept `preset_id` (verified live; probe
# report § (c)). The demo slice cannot import from the frontend either
# (vertical-slice + language barrier). So PRP-39 HARD-CODES the same 3
# baseline model_types in a Python constant:
#
#     # SOURCE: frontend/src/components/forecast-intelligence/batch-preset-utils.ts:22-28
#     # First 3 of the 5 quick_baseline_sweep baselines (3×2×3 = 18-item budget).
#     BATCH_PRESET_QUICK_BASELINE_SWEEP_MODELS: tuple[str, ...] = (
#         "naive", "seasonal_naive", "moving_average",
#     )
#
# step.data carries preset_source="quick_baseline_sweep" so the step card
# chip reads "Preset: quick_baseline_sweep · kind=MANUAL · 18/18 done".

# ─────────────────────────────────────────────────────────────────────────
# D3 — POST /batch/forecasting settles synchronously.
# ─────────────────────────────────────────────────────────────────────────
# The submit endpoint runs the batch sequentially in-request and returns
# the final BatchSubmitResponse (verified live — 18-item batch returned
# terminal state in ~250 ms). The poll loop is a safety net.
#
# RULE for step_batch_preset:
#   1. POST /batch/forecasting → response carries terminal status in MOST
#      cases.
#   2. If status is still PENDING/RUNNING, GET /batch/{batch_id} every
#      2 s until terminal OR 90 s elapsed.
#   3. Emit pass on COMPLETED, warn on PARTIAL or poll-timeout, fail on
#      FAILED or CANCELLED.
#
# BatchStatus enum: pending, running, completed, failed, partial, cancelled.

# ─────────────────────────────────────────────────────────────────────────
# G1 — RunUpdate cannot patch runtime_info (inherited from PRP-38 probe).
# ─────────────────────────────────────────────────────────────────────────
# `runtime_info` (including `feature_frame_version`) is IMMUTABLE after
# `RunCreate`. To register a SECOND V2 run with a controlled V,
# stale_alias_trigger MUST set `runtime_info_extras={"feature_frame_version": <V>}`
# on the POST /registry/runs body. PATCH only accepts {status, metrics,
# artifact_uri, artifact_hash, artifact_size_bytes, error_message}.

# ─────────────────────────────────────────────────────────────────────────
# G2 — Alias may only point to a SUCCESS run.
# ─────────────────────────────────────────────────────────────────────────
# POST /registry/aliases enforces `run_status == SUCCESS`. Both
# stale_alias_trigger AND safer_promote_flow MUST take the second run
# through pending → running → success BEFORE the alias swap. The chain
# mirrors step_v2_train at `app/features/demo/pipeline.py:817-849`.

# ─────────────────────────────────────────────────────────────────────────
# G3 — R15 — cleanup MUST restore the alias before the run ends.
# ─────────────────────────────────────────────────────────────────────────
# safer_promote_flow swaps the demo-production alias to a worse-WAPE run
# so the dialog gates fire when a human visits /ops. Leaving the alias
# pointing at the worse run after the demo would be misleading
# (the "champion" is the V2 winner, not the deliberately-worse run).
# RULE: extend step_cleanup to POST /registry/aliases ONE MORE TIME
# restoring demo-production → ctx.original_demo_alias_run_id (captured
# BEFORE the swap in safer_promote_flow). Failure to restore is a `warn`
# (non-fatal) so the run still goes green.

# ─────────────────────────────────────────────────────────────────────────
# G4 — Vertical-slice rule (load-bearing for the demo slice).
# ─────────────────────────────────────────────────────────────────────────
# app/features/demo/ may import from app.core.* + app.shared.* +
# standard library only. NEVER `from app.features.<other_slice>.X import …`.
# All four new steps drive registry / ops / batch over httpx.ASGITransport
# exactly like every existing step. Grep guard:
#   git grep -nE "from app\.features\.[^.]+\." app/features/demo/ \
#     | grep -v "from app.features.demo"
# MUST be empty after PRP-39 edits.

# ─────────────────────────────────────────────────────────────────────────
# G5 — WebSocket contract additive-only — NO schema changes in PRP-39.
# ─────────────────────────────────────────────────────────────────────────
# PRP-38 added phase_name/phase_index/phase_total. PRP-39 does NOT add
# any new wire fields. `git diff app/features/demo/schemas.py` MUST show
# ZERO field additions after PRP-39. The four new steps use the existing
# StepEvent shape with their step_name values.

# ─────────────────────────────────────────────────────────────────────────
# G6 — Frontend type-check command is project-scoped (inherited from PRP-38).
# ─────────────────────────────────────────────────────────────────────────
# Use `pnpm tsc --noEmit -p tsconfig.app.json` — NOT bare `pnpm tsc --noEmit`.
# The root tsconfig.json has `"files": []` and will pass while the app
# tsconfig still has errors.

# ─────────────────────────────────────────────────────────────────────────
# G7 — RELATIVE phase anchors only (parallel-merge coordination).
# ─────────────────────────────────────────────────────────────────────────
# PRP-39 and PRP-40 are sibling slices. Phrase every _phase_table()
# edit as "extend the existing `decision`-phase block by 3 rows AFTER
# `register`" or "insert a new phase block `portfolio` BEFORE the
# `verify` block" — NEVER "insert at row index 11" or "after position 13".
# The frozen-fixture test references step rows by name + phase, not
# absolute index.

# ─────────────────────────────────────────────────────────────────────────
# G8 — Showcase grain discovery (mirrors PRP-38 step_status pattern).
# ─────────────────────────────────────────────────────────────────────────
# Seeder doesn't reset DB ID sequences (memory: seeder-does-not-reset-
# id-sequences). The showcase grain (ctx.store_id, ctx.product_id) is
# populated by step_status at `pipeline.py:307-356`. PRP-39's
# batch_preset step picks NEIGHBOURING stores + products by reading
# /dimensions/stores?limit=5 + /dimensions/products?limit=5 (DESC by
# id, then taking the first 3 stores + first 2 products). Never
# hardcode 1.

# ─────────────────────────────────────────────────────────────────────────
# G9 — CRLF/LF noise (inherited from PRP-38).
# ─────────────────────────────────────────────────────────────────────────
# Some files are CRLF; Edit/Write emit LF. Run `git diff --stat` before
# committing; whole-file noise diffs go in a separate normalisation
# commit, not this PRP.
```

---

## Implementation Blueprint

### Data models and structure (additive — NO schema changes)

`DemoContext` (`app/features/demo/pipeline.py:167`) gains 4 Optional
fields. The wire `StepEvent` is unchanged.

```python
# app/features/demo/pipeline.py — DemoContext additive fields

@dataclass
class DemoContext:
    # ... existing fields preserved ...

    # PRP-39 — additive Optional fields populated only on SHOWCASE_RICH runs
    # AND only by their respective step functions.
    compat_compare_result: dict[str, Any] | None = None
    stale_alias_run_id: str | None = None
    original_demo_alias_run_id: str | None = None  # captured pre-swap for R15 restore
    batch_id: str | None = None
    batch_status: str | None = None
```

```python
# app/features/demo/pipeline.py — new phase constant
# Inserted between PHASE_DECISION and PHASE_VERIFY (relative anchor).
PHASE_PORTFOLIO = "portfolio"  # PRP-39
```

```python
# app/features/demo/pipeline.py — module-level constant
# SOURCE: frontend/src/components/forecast-intelligence/batch-preset-utils.ts:22-28
# First 3 of the 5 quick_baseline_sweep baselines — gives 3 stores × 2 products
# × 3 models = 18 items, matching INITIAL-39 § Scope.
BATCH_PRESET_QUICK_BASELINE_SWEEP_MODELS: tuple[str, ...] = (
    "naive",
    "seasonal_naive",
    "moving_average",
)

# Per the probe report § D3, the batch endpoint settles synchronously in
# most cases. The poll is a safety net.
_BATCH_POLL_INTERVAL_SECONDS = 2.0
_BATCH_POLL_TIMEOUT_SECONDS = 90.0
```

### List of tasks to be completed (dependency-ordered)

```yaml
Task 1 — CONTRACT PROBE (DONE — gates every other task):
  - OUTPUT PRPs/ai_docs/prp-39-contract-probe-report.md.
  - VERIFY every backend field PRP-39 cites (registry, ops, batch).
  - RECORD drift resolutions D1 (compare envelope), D2 (preset Option A), D3 (sync settle).
  - GREEN — proceed to Task 2.

Task 2 — MODIFY app/features/demo/pipeline.py — `DemoContext` + phase constant [gate:always]:
  - FIND `class DemoContext` (line 167).
  - INJECT 4 new Optional fields after `bucketed_aggregated_metrics` (line 195):
      compat_compare_result, stale_alias_run_id, original_demo_alias_run_id, batch_id, batch_status.
  - FIND `PHASE_CLEANUP = "cleanup"` (line 1115).
  - INJECT `PHASE_PORTFOLIO = "portfolio"` between PHASE_DECISION (line 1112) and PHASE_VERIFY (line 1113) so source order matches insertion order. (No backend code depends on the order of these constants; the frontend reads them via wire `phase_name` strings.)

Task 3 — CREATE step_champion_compat_compare [gate:PRP-38]:
  - INSERT a new async step function after step_register (line 1007).
  - PSEUDOCODE per § "Per task pseudocode" below.
  - SKIP gracefully if ctx.v2_run_id is None (R14 — user ran scenario=demo_minimal so no V2 run exists).
  - On success: step.data = {v1_run_id, v2_run_id, feature_frame_version_a, feature_frame_version_b, compatible: false, comparable_reason: "feature_frame_version_mismatch"}.
  - ACCEPTANCE: unit test asserts compatible=False, V_a=None-or-1, V_b=2, reason="feature_frame_version_mismatch".

Task 4 — CREATE step_stale_alias_trigger [gate:PRP-38]:
  - INSERT new async step function after step_champion_compat_compare.
  - PSEUDOCODE per § "Per task pseudocode" below.
  - REGISTER a second prophet_like run on the SAME grain (ctx.store_id, ctx.product_id) as PRP-38's V2 run with `runtime_info_extras={"feature_frame_version": 3}` (controlled V ≠ 2). Mirror step_v2_train (line 753) for the create+running+success chain.
  - DO NOT alias the new run — `demo-production` keeps pointing at PRP-38's V2 run; the V-mismatch fires because the LATEST comparable run on the grain now has V=3 while the alias's run has V=2.
  - GET /ops/summary and find the stale alias row; capture stale_reason + alias_v + comparable_v into step.data.
  - On success: step.data = {alias_name, stale_reason: "feature_frame_version_mismatch", alias_feature_frame_version, comparable_run_feature_frame_version, second_v2_run_id}.
  - ACCEPTANCE: unit test asserts the GET /ops/summary response includes one alias with stale_reason="feature_frame_version_mismatch" + V mismatch detail row populated.

Task 5 — CREATE step_safer_promote_flow [gate:always]:
  - INSERT new async step function after step_stale_alias_trigger.
  - REGISTER a third baseline run (`seasonal_naive` on same grain, fresh data window OR with a tweaked model_config so config_hash differs) deliberately with WORSE metrics than PRP-38's V2 winner. Mirror step_register (line 887) for the create+running+success chain.
  - CAPTURE ctx.original_demo_alias_run_id = (current alias target run_id from GET /registry/aliases/demo-production) BEFORE the swap.
  - POST /registry/aliases swapping demo-production to the new worse-WAPE run.
  - On success: step.data = {alias_name: "demo-production", before_run_id, after_run_id, swap_intent: "demo_safer_promote_walkthrough"}.
  - ACCEPTANCE: unit test asserts GET /registry/aliases/demo-production returns the new run_id.

Task 6 — EXTEND step_cleanup to restore alias (R15) [gate:always]:
  - FIND step_cleanup at line 1088.
  - PRESERVE the existing agent-session-close behaviour.
  - INJECT: if ctx.original_demo_alias_run_id is not None, POST /registry/aliases swapping demo-production back to ctx.original_demo_alias_run_id. Failure is `warn`, not `fail`.
  - On success: step.data = {agent_session_closed, alias_restored: true, restored_run_id}.
  - ACCEPTANCE: unit test asserts after step_cleanup runs, GET /registry/aliases/demo-production returns ctx.original_demo_alias_run_id.

Task 7 — CREATE step_batch_preset [gate:always]:
  - INSERT new async step function in module-level position (alongside the other steps; canonical alphabetic-ish ordering is not enforced).
  - DISCOVER 3 stores via GET /dimensions/stores?limit=5 and 2 products via GET /dimensions/products?limit=5 (mirror step_status pattern at line 307-356). Pick the first 3 stores + first 2 products by store_id/product_id order.
  - POST /batch/forecasting per D2: operation="train", scope={kind:"manual", store_ids:[...], product_ids:[...]}, model_configs=[{"model_type": m} for m in BATCH_PRESET_QUICK_BASELINE_SWEEP_MODELS], start_date=ctx.date_start.isoformat(), end_date=ctx.date_end.isoformat().
  - CHECK terminal status on the submit response. If not terminal, POLL GET /batch/{batch_id} every 2 s until terminal OR 90 s.
  - MAP BatchStatus → StepStatus: completed → pass, partial → warn, failed → fail, cancelled → fail, poll-timeout → warn.
  - On success: step.data = {batch_id, kind: "manual", preset_source: "quick_baseline_sweep", model_types: list(BATCH_PRESET_QUICK_BASELINE_SWEEP_MODELS), total_items, completed_items, failed_items, partial_items, status}.
  - ACCEPTANCE: unit test asserts step.data.batch_id is non-empty + status in {completed, partial}; total_items == 18.

Task 8 — MODIFY _phase_table() [gate:always]:
  - FIND `def _phase_table(scenario: ScenarioPreset)` at line 1118.
  - FIND `decision_steps: list[tuple[str, StepFn]] = [...]` at line 1138.
  - APPEND the three new steps to the SHOWCASE_RICH branch of decision_steps (the if-block at line 1145). PRESERVE the order: champion_compat_compare → stale_alias_trigger → safer_promote_flow.
  - FIND `verify_steps: list[tuple[str, StepFn]]` at line 1142.
  - INJECT BEFORE the verify_steps line: `portfolio_steps: list[tuple[str, StepFn]] = [("batch_preset", step_batch_preset)] if scenario is ScenarioPreset.SHOWCASE_RICH else []`.
  - FIND `rows += [(PHASE_VERIFY, name, fn) for name, fn in verify_steps]` at line 1155.
  - INJECT BEFORE that line: `rows += [(PHASE_PORTFOLIO, name, fn) for name, fn in portfolio_steps]`.
  - ACCEPTANCE: test_phase_table_stable green; the SHOWCASE_RICH branch produces 18 rows (was 14 in PRP-38), DEMO_MINIMAL stays at 11.

Task 9 — MODIFY frontend/src/components/demo/PHASE_DEFS.ts [gate:always]:
  - FIND `const ALL_STEPS: ReadonlyArray<PhaseDef>` at line 29.
  - INJECT three rows AFTER `{ phase: 'decision', step: 'register', label: 'Register winner' }` (line 40):
      `{ phase: 'decision', step: 'champion_compat_compare', label: 'Compare V1 vs V2' }`
      `{ phase: 'decision', step: 'stale_alias_trigger', label: 'Trigger stale-alias V mismatch' }`
      `{ phase: 'decision', step: 'safer_promote_flow', label: 'Safer Promote walkthrough' }`
  - INJECT one row AFTER the three decision rows AND BEFORE `{ phase: 'verify', step: 'verify', ... }` (the previous line 41):
      `{ phase: 'portfolio', step: 'batch_preset', label: 'Portfolio batch (quick baseline sweep)' }`
  - FIND `SHOWCASE_RICH_STEP_NAMES` at line 46.
  - APPEND the 4 new step names to the set:
      'champion_compat_compare', 'stale_alias_trigger', 'safer_promote_flow', 'batch_preset'.
  - FIND `PHASE_LABEL` at line 62.
  - INJECT `portfolio: 'Portfolio',` between `decision: 'Decision',` (line 65) and `verify: 'Verify',` (line 66).
  - FIND `PHASE_ORDER` at line 72.
  - INJECT `'portfolio',` between `'decision',` (line 75) and `'verify',` (line 76).

Task 10 — MODIFY frontend/src/components/demo/demo-step-card.tsx [gate:always]:
  - ADD one-row mini-summary chip-line for each of the 4 new step names (when step.status === 'pass' or 'warn'):
      - `champion_compat_compare`: "V_a={v} · V_b={v} · compatible=false · reason=feature_frame_version_mismatch"
      - `stale_alias_trigger`: "alias={alias_name} · stale_reason=feature_frame_version_mismatch · V_alias={v} → V_comparable={v}"
      - `safer_promote_flow`: "alias=demo-production · before={before_run_id[:8]} → after={after_run_id[:8]}"
      - `batch_preset`: "preset=quick_baseline_sweep · {completed_items}/{total_items} done · status={status}"
  - PRESERVE existing card render structure (Inspect button branch at the bottom; mini-summary chip-line goes ABOVE the Inspect button).

Task 11 — MODIFY frontend/src/pages/showcase.tsx — `resolveInspectHref` [gate:always]:
  - FIND `function resolveInspectHref(step: DemoStep)` at line 26.
  - INJECT 4 new `case` arms (BEFORE the `default` branch at line 47):
      case 'champion_compat_compare': {
        const v1 = typeof data.v1_run_id === 'string' ? data.v1_run_id : null
        const v2 = typeof data.v2_run_id === 'string' ? data.v2_run_id : null
        return v1 && v2 ? `${ROUTES.EXPLORER.RUN_COMPARE}?a=${v1}&b=${v2}` : null
      }
      case 'stale_alias_trigger':
      case 'safer_promote_flow':
        return ROUTES.OPS
      case 'batch_preset': {
        const batchId = typeof data.batch_id === 'string' ? data.batch_id : null
        return batchId ? `${ROUTES.VISUALIZE.BATCH}/${batchId}` : null
      }
  - PRESERVE existing `case` arms (train / v2_train / register / backtest).

Task 12 — MODIFY app/features/demo/tests/test_pipeline.py [gate:always]:
  - ADD test_champion_compat_compare_step (asserts step.data.compatible == False, V_a != V_b, reason == "feature_frame_version_mismatch"; uses ASGITransport against a real seeded DB OR fixture-injected runs).
  - ADD test_stale_alias_trigger_step (asserts /ops/summary includes alias with stale_reason="feature_frame_version_mismatch"; asserts comparable_run_feature_frame_version is populated).
  - ADD test_safer_promote_step (asserts GET /registry/aliases/demo-production returns the new worse-WAPE run_id; ctx.original_demo_alias_run_id is set BEFORE the swap).
  - ADD test_batch_preset_step (asserts batch_id is non-empty, total_items == 18, status terminal).
  - ADD test_cleanup_restores_alias (asserts after step_cleanup runs, GET /registry/aliases/demo-production returns ctx.original_demo_alias_run_id; on missing original, the step is a no-op).
  - EXTEND test_phase_table_stable to assert the SHOWCASE_RICH branch carries the new 4 step rows in canonical order (champion_compat_compare → stale_alias_trigger → safer_promote_flow → batch_preset).

Task 13 — MODIFY frontend/src/components/demo/PHASE_DEFS.test.ts [gate:always]:
  - EXTEND the SHOWCASE_RICH fixture (formerly 14 entries) to 18 entries with the 4 new rows in canonical order.
  - PRESERVE the DEMO_MINIMAL fixture at 11 entries.

Task 14 — MODIFY frontend/src/components/demo/demo-step-card.test.tsx [gate:always]:
  - ADD 4 render tests — one per new step name — asserting the mini-summary chip-line text matches the specified format.
  - ADD a test asserting the Inspect button href for each new step name (champion_compat_compare → /explorer/runs/compare?a=&b=, stale_alias_trigger → /ops, safer_promote_flow → /ops, batch_preset → /visualize/batch/{batch_id}).

Task 15 — EXTEND tests/test_e2e_demo.py [gate:always]:
  - ADD test_e2e_showcase_rich_decision_portfolio (@pytest.mark.integration):
      - POST /demo/run with scenario=showcase_rich, reset=True, skip_seed=False.
      - Soft-warn on wall-clock > 240 s; hard-fail on > 300 s.
      - Assert 4 new step_complete events fire with status ∈ {pass, warn}.
      - Assert GET /ops/summary returns ≥ 1 alias with stale_reason="feature_frame_version_mismatch".
      - Assert GET /registry/compare/{v1}/{v2} returns 200 with run_a.feature_frame_version=null + run_b.feature_frame_version=2.
      - Assert GET /batch/{batch_id} is terminal.
      - Assert GET /registry/aliases/demo-production after cleanup returns the original V2 winner (R15).

Task 16 — DOC UPDATE [gate:always]:
  - APPEND to `docs/_base/RUNBOOKS.md` § "Showcase page (`/showcase`) pipeline fails at step X" — additive entries for each of the 4 new step names (champion_compat_compare, stale_alias_trigger, safer_promote_flow, batch_preset) covering:
      - champion_compat_compare: skips when no V2 run on grain; fails when compare endpoint returns 404 (one of the two run_ids is missing).
      - stale_alias_trigger: fails if RunCreate is rejected (PRP-38's V2 run had non-overlapping window OR an unexpected duplicate config).
      - safer_promote_flow: fails if alias POST is rejected (worse-WAPE run never reached SUCCESS; chain order bug); restoration failure in cleanup is a warn.
      - batch_preset: warn on poll timeout, fail on submission validation (e.g., scope expansion exceeds BATCH_MAX_SCOPE_EXPANSION).
  - DO NOT update docs/user-guide/showcase-walkthrough.md (PRP-41 scope per umbrella + index).

Task 17 — DOGFOOD [gate:always]:
  - Pre-flight: ps -ef | grep '[u]vicorn' (memory: dogfood-stale-uvicorn-port-8123).
  - Manual flow (capture screenshots):
      a) Open /showcase — confirm 7 phase cards in idle state.
      b) Pick `showcase-rich`, tick "Re-seed first", click Run — confirm wall-clock ≤ 240 s.
      c) After completion:
        - Click Inspect on `champion_compat_compare` → /explorer/runs/compare lights up the "Not comparable" badge.
        - Click Inspect on `stale_alias_trigger` → /ops shows the stale-alias chip.
        - Click Inspect on `safer_promote_flow` → /ops Promote button opens the safer-Promote dialog with the right gates.
        - Click Inspect on `batch_preset` → /visualize/batch/{batch_id} shows the populated batch.
      d) Confirm GET /registry/aliases/demo-production returns the V2 winner (R15 restore).
  - Attach screenshots to the PR.

Task 18 — VALIDATION GATES [gate:always]:
  - Backend:
      uv run ruff check . && uv run ruff format --check .
      uv run mypy app/
      uv run pyright app/
      uv run pytest -v -m "not integration"
      uv run pytest -v -m integration tests/test_e2e_demo.py::test_e2e_showcase_rich_decision_portfolio
  - Frontend (from frontend/):
      pnpm lint
      pnpm tsc --noEmit -p tsconfig.app.json
      pnpm test --run
  - Grep guards:
      git grep -nE "from app\.features\.[^.]+\." app/features/demo/ | grep -v "from app.features.demo"  # MUST be empty
      grep -rn "from 'radix-ui'" frontend/src   # MUST be empty
  - git diff --check  # zero whitespace errors
```

### Per task pseudocode (the load-bearing parts)

```python
# Task 3 — step_champion_compat_compare
#
# Mirrors the predicate at
# frontend/src/components/forecast-intelligence/champion-compatibility-utils.ts:14-47
# so the same comparable_reason key works for both the compare card and
# the ops chip.

async def step_champion_compat_compare(
    ctx: DemoContext, client: _Client
) -> StepResult:
    """Champion-compat compare V1 baseline vs V2 prophet_like (PRP-39)."""
    if ctx.v2_run_id is None or ctx.winning_run_id is None:
        # R14 — no V2 run on the showcase grain (user ran scenario=demo_minimal).
        return ("skip", "no V2 run on the showcase grain — run with scenario=showcase_rich", {})

    # Pick a V1 baseline run on the same grain. Use the original V1 baseline
    # winner the demo's `register` step trained ON DEMO_MINIMAL runs OR the
    # most recent V1 success on the showcase grain.
    runs_body = await client.request(
        "champion_compat_compare[runs]",
        "GET",
        f"/registry/runs?store_id={ctx.store_id}&product_id={ctx.product_id}&status=success&page_size=20",
    )
    runs = runs_body.get("runs", [])
    v1_run_id = None
    for run in runs:
        if run.get("feature_frame_version") in (None, 1) and run.get("run_id") != ctx.v2_run_id:
            v1_run_id = run.get("run_id")
            break
    if not isinstance(v1_run_id, str):
        return ("skip", "no V1 baseline run on the showcase grain", {})

    # GET the compare envelope. Per probe report § D1, the envelope is
    # {run_a, run_b, config_diff, metrics_diff} — no top-level
    # compatible/comparable_reason. Derive them client-side.
    compare_body = await client.request(
        "champion_compat_compare[compare]",
        "GET",
        f"/registry/compare/{v1_run_id}/{ctx.v2_run_id}",
    )
    run_a = compare_body.get("run_a", {})
    run_b = compare_body.get("run_b", {})
    v_a = run_a.get("feature_frame_version")  # None for legacy V1
    v_b = run_b.get("feature_frame_version")  # 2 for PRP-38's V2 run
    # Coerce legacy V1 (None) to V=1 for the compat predicate, matching
    # the frontend computeCompatibility logic AND OpsService._run_feature_frame_version.
    v_a_norm = 1 if v_a is None else v_a
    v_b_norm = 1 if v_b is None else v_b
    compatible = v_a_norm == v_b_norm  # grain + window are equal by construction
    reason = None if compatible else "feature_frame_version_mismatch"

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
```

```python
# Task 4 — step_stale_alias_trigger
#
# Mirrors step_v2_train's create+running+success chain at pipeline.py:817-849.

async def step_stale_alias_trigger(
    ctx: DemoContext, client: _Client
) -> StepResult:
    """Trigger feature_frame_version_mismatch stale-alias verdict (PRP-39)."""
    if ctx.v2_run_id is None or ctx.date_start is None or ctx.date_end is None:
        return ("skip", "no V2 run / date range — run with scenario=showcase_rich", {})

    # Register a SECOND prophet_like run on the SAME grain as PRP-38's V2 run,
    # with runtime_info_extras.feature_frame_version set to a value DIFFERENT
    # from PRP-38's V2 (which is V=2). V=3 is a synthetic value the ops layer
    # treats as opaque — the system only models V=1 and V=2, but the JSONB
    # key accepts any int.
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
    second_run_id = create_body["run_id"]
    ctx.stale_alias_run_id = second_run_id

    # PATCH pending → running → success. metrics + artifact_uri are
    # immaterial for this step's purpose; use placeholders consistent with
    # step_register's V1 artifact_uri shape (the run never gets aliased so
    # /forecasting feature-metadata won't be called).
    await client.request(
        "stale_alias_trigger[running]", "PATCH",
        f"/registry/runs/{second_run_id}",
        json_body={"status": "running"},
    )
    await client.request(
        "stale_alias_trigger[success]", "PATCH",
        f"/registry/runs/{second_run_id}",
        json_body={
            "status": "success",
            "metrics": {"wape": 999.0},  # deliberately worse — secondary signal
            # Reuse the V2 run's artifact_uri (the bundle already exists).
            # We're not aliasing this run, so verify is never called.
            "artifact_uri": "demo/stale-alias-placeholder.joblib",
            "artifact_hash": "0" * 64,
            "artifact_size_bytes": 1,
        },
    )

    # Hit /ops/summary to confirm the stale-alias verdict surfaces.
    ops_body = await client.request(
        "stale_alias_trigger[ops]", "GET", "/ops/summary",
    )
    aliases = ops_body.get("aliases", [])
    target = next(
        (a for a in aliases if a.get("alias_name") == DEMO_ALIAS),
        None,
    )
    if target is None:
        return ("fail", f"alias {DEMO_ALIAS} missing from /ops/summary", {})

    stale_reason = target.get("stale_reason")
    if stale_reason != "feature_frame_version_mismatch":
        return (
            "fail",
            f"expected stale_reason=feature_frame_version_mismatch, got {stale_reason}",
            {},
        )

    return (
        "pass",
        f"alias={DEMO_ALIAS} stale_reason={stale_reason} V_alias={target.get('alias_feature_frame_version')}→V_comparable={target.get('comparable_run_feature_frame_version')}",
        {
            "alias_name": DEMO_ALIAS,
            "stale_reason": stale_reason,
            "alias_feature_frame_version": target.get("alias_feature_frame_version"),
            "comparable_run_feature_frame_version": target.get(
                "comparable_run_feature_frame_version"
            ),
            "second_v2_run_id": second_run_id,
        },
    )
```

```python
# Task 5 — step_safer_promote_flow
#
# Mirrors step_register's create+running+success+alias chain at
# pipeline.py:946-1001. Deliberately registers a worse-WAPE run so the
# safer-Promote dialog gates fire when a human visits /ops.

async def step_safer_promote_flow(
    ctx: DemoContext, client: _Client
) -> StepResult:
    """Swap demo-production to a worse-WAPE run (PRP-39)."""
    if ctx.winning_run_id is None or ctx.date_start is None or ctx.date_end is None:
        return ("skip", "no winning run / date range — run with scenario=showcase_rich", {})

    # Capture the current alias target BEFORE the swap (R15 — for cleanup restore).
    alias_body = await client.request(
        "safer_promote[alias_pre]", "GET", f"/registry/aliases/{DEMO_ALIAS}",
    )
    ctx.original_demo_alias_run_id = alias_body.get("run_id")

    # Train a fresh baseline run with a tweaked config_hash so RegistryService
    # doesn't dedupe against the prior register step's run. Use seasonal_naive
    # with season_length=14 (default register uses 7) so config_hash differs.
    # Mirror step_register but skip the actual training — we go straight to a
    # synthetic worse-WAPE record. The dialog gates fire on WAPE delta + V
    # delta, not on artifact freshness.
    create_body = await client.request(
        "safer_promote[create]", "POST", "/registry/runs",
        json_body={
            "model_type": "seasonal_naive",
            "model_config": {"model_type": "seasonal_naive", "season_length": 14},
            "feature_config": None,
            "data_window_start": ctx.date_start.isoformat(),
            "data_window_end": ctx.date_end.isoformat(),
            "store_id": ctx.store_id,
            "product_id": ctx.product_id,
            # V=1 deliberately, to additionally fire the V-mismatch-ack
            # gate in the dialog (V2 winner → V1 challenger).
            "runtime_info_extras": {"feature_frame_version": 1},
        },
    )
    worse_run_id = create_body["run_id"]

    # pending → running → success
    await client.request(
        "safer_promote[running]", "PATCH",
        f"/registry/runs/{worse_run_id}",
        json_body={"status": "running"},
    )
    await client.request(
        "safer_promote[success]", "PATCH",
        f"/registry/runs/{worse_run_id}",
        json_body={
            "status": "success",
            "metrics": {"wape": 99.0},  # deliberately WORSE than V2's wape
            "artifact_uri": "demo/safer-promote-placeholder.joblib",
            "artifact_hash": "0" * 64,
            "artifact_size_bytes": 1,
        },
    )

    # Swap the alias.
    await client.request(
        "safer_promote[alias_swap]", "POST", "/registry/aliases",
        json_body={
            "alias_name": DEMO_ALIAS,
            "run_id": worse_run_id,
            "description": "PRP-39 safer-Promote walkthrough — deliberate worse-WAPE swap.",
        },
    )

    return (
        "pass",
        f"alias={DEMO_ALIAS} before={ctx.original_demo_alias_run_id[:8]}→after={worse_run_id[:8]}",
        {
            "alias_name": DEMO_ALIAS,
            "before_run_id": ctx.original_demo_alias_run_id,
            "after_run_id": worse_run_id,
            "swap_intent": "demo_safer_promote_walkthrough",
        },
    )
```

```python
# Task 7 — step_batch_preset
#
# Option A from D2 — Python-side preset expansion.

async def step_batch_preset(
    ctx: DemoContext, client: _Client
) -> StepResult:
    """Run the quick_baseline_sweep portfolio preset (PRP-39)."""
    if ctx.date_start is None or ctx.date_end is None:
        return ("skip", "no date range — run with scenario=showcase_rich", {})

    # Discover 3 stores + 2 products from the showcase grain's neighbours.
    # Mirror step_status pattern (pipeline.py:307-356).
    stores_body = await client.request(
        "batch_preset[stores]", "GET", "/dimensions/stores?limit=5",
    )
    products_body = await client.request(
        "batch_preset[products]", "GET", "/dimensions/products?limit=5",
    )
    store_ids = [s["id"] for s in stores_body.get("stores", [])][:3]
    product_ids = [p["id"] for p in products_body.get("products", [])][:2]
    if len(store_ids) < 3 or len(product_ids) < 2:
        return ("skip", "insufficient stores/products in the seeded grain", {})

    # POST /batch/forecasting per D2 — Option A (no preset_id; expanded
    # client-side from BATCH_PRESET_QUICK_BASELINE_SWEEP_MODELS).
    submit_body = await client.request(
        "batch_preset[submit]", "POST", "/batch/forecasting",
        json_body={
            "operation": "train",
            "scope": {
                "kind": "manual",
                "store_ids": store_ids,
                "product_ids": product_ids,
            },
            "model_configs": [
                {"model_type": m} for m in BATCH_PRESET_QUICK_BASELINE_SWEEP_MODELS
            ],
            "start_date": ctx.date_start.isoformat(),
            "end_date": ctx.date_end.isoformat(),
        },
    )
    batch_id = submit_body["batch_id"]
    ctx.batch_id = batch_id

    # Per D3, submit usually returns terminal status. Poll only if not terminal.
    terminal_statuses = {"completed", "failed", "partial", "cancelled"}
    status = submit_body.get("status")
    body = submit_body
    if status not in terminal_statuses:
        t0 = time.monotonic()
        while time.monotonic() - t0 < _BATCH_POLL_TIMEOUT_SECONDS:
            await asyncio.sleep(_BATCH_POLL_INTERVAL_SECONDS)
            body = await client.request(
                "batch_preset[poll]", "GET", f"/batch/{batch_id}",
            )
            status = body.get("status")
            if status in terminal_statuses:
                break
        else:
            ctx.batch_status = status or "unknown"
            return (
                "warn",
                f"batch poll timed out at {_BATCH_POLL_TIMEOUT_SECONDS}s; visit /visualize/batch/{batch_id}",
                {
                    "batch_id": batch_id,
                    "kind": "manual",
                    "preset_source": "quick_baseline_sweep",
                    "model_types": list(BATCH_PRESET_QUICK_BASELINE_SWEEP_MODELS),
                    "status": status or "unknown",
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

    return (
        step_status,
        f"preset=quick_baseline_sweep {body.get('completed_items')}/{body.get('total_items')} done status={status}",
        {
            "batch_id": batch_id,
            "kind": "manual",
            "preset_source": "quick_baseline_sweep",
            "model_types": list(BATCH_PRESET_QUICK_BASELINE_SWEEP_MODELS),
            "status": status,
            "total_items": body.get("total_items"),
            "completed_items": body.get("completed_items"),
            "failed_items": body.get("failed_items"),
        },
    )
```

```python
# Task 6 — step_cleanup extension (R15)

async def step_cleanup(ctx: DemoContext, client: _Client) -> StepResult:
    """Close agent session + restore demo-production alias (PRP-39 R15)."""
    alias_restored = False
    restored_run_id: str | None = None

    # NEW — R15 restore. Failure is `warn`, not `fail`.
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

    detail_parts = []
    if agent_closed:
        detail_parts.append("agent closed")
    if alias_restored:
        detail_parts.append(f"alias restored to {restored_run_id[:8]}...")
    if not detail_parts:
        detail_parts.append("nothing to do")

    return (
        "pass",
        " · ".join(detail_parts),
        {
            "agent_session_closed": agent_closed,
            "alias_restored": alias_restored,
            "restored_run_id": restored_run_id,
        },
    )
```

```python
# Task 8 — _phase_table extension

def _phase_table(scenario: ScenarioPreset) -> list[PhaseStep]:
    data_steps: list[tuple[str, StepFn]] = [...]   # unchanged
    modeling_steps: list[tuple[str, StepFn]] = [("train", step_train)]
    decision_steps: list[tuple[str, StepFn]] = [
        ("backtest", step_backtest),
        ("register", step_register),
    ]
    verify_steps: list[tuple[str, StepFn]] = [("verify", step_verify)]
    agent_steps: list[tuple[str, StepFn]] = [("agent", step_agent)]
    cleanup_steps: list[tuple[str, StepFn]] = [("cleanup", step_cleanup)]
    # PRP-39 — new portfolio phase, empty under demo_minimal/sparse.
    portfolio_steps: list[tuple[str, StepFn]] = []

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

    rows: list[PhaseStep] = []
    rows += [(PHASE_DATA, name, fn) for name, fn in data_steps]
    rows += [(PHASE_MODELING, name, fn) for name, fn in modeling_steps]
    rows += [(PHASE_DECISION, name, fn) for name, fn in decision_steps]
    # PRP-39 — INSERT portfolio BEFORE verify (relative anchor).
    rows += [(PHASE_PORTFOLIO, name, fn) for name, fn in portfolio_steps]
    rows += [(PHASE_VERIFY, name, fn) for name, fn in verify_steps]
    rows += [(PHASE_AGENT, name, fn) for name, fn in agent_steps]
    rows += [(PHASE_CLEANUP, name, fn) for name, fn in cleanup_steps]
    return rows
```

### Integration Points

```yaml
DATABASE:
  - No migration; no schema change.
  - Two NEW model_run rows per showcase_rich pipeline run (the
    stale_alias_trigger's V=3 run + the safer_promote_flow's V=1
    seasonal_naive run). Both rows are SUCCESS and never archived; they
    accumulate across runs (R15 cleanup restores the alias but does NOT
    delete the runs themselves — this is consistent with the "no
    destructive operations" product principle).

CONFIG:
  - No new env vars.
  - _HTTP_TIMEOUT unchanged at 120 s.
  - _BATCH_POLL_INTERVAL_SECONDS / _BATCH_POLL_TIMEOUT_SECONDS are
    module-level constants in pipeline.py; no settings dependency.

ROUTES:
  - No new routes. The demo slice (`/demo/run`, `/demo/stream`)
    surfaces the new steps via existing endpoints.

FRONTEND DEEP-LINKS (from showcase.tsx resolveInspectHref):
  - /explorer/runs/compare?a={v1_run_id}&b={v2_run_id}
  - /ops
  - /ops
  - /visualize/batch/{batch_id}
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Backend
uv run ruff check . && uv run ruff format --check .
uv run mypy app/
uv run pyright app/

# Frontend
cd frontend && pnpm lint && pnpm tsc --noEmit -p tsconfig.app.json && cd ..
```

### Level 2: Unit Tests

```bash
uv run pytest -v -m "not integration" app/features/demo/tests/test_pipeline.py
# Must include the 4 new step tests + 1 cleanup-restore test + extended
# test_phase_table_stable.

cd frontend && pnpm test --run && cd ..
# Must include the 4 new step-card mini-summary tests +
# 4 new Inspect-href tests + the extended PHASE_DEFS fixture.
```

### Level 3: Integration Test

```bash
# Backend integration (real docker-compose Postgres)
docker compose up -d
uv run alembic upgrade head
uv run pytest -v -m integration tests/test_e2e_demo.py::test_e2e_showcase_rich_decision_portfolio

# Frontend type-check (project-scoped per G6)
cd frontend && pnpm tsc --noEmit -p tsconfig.app.json && cd ..
```

### Level 4: Manual dogfood (verbatim from INITIAL-39 § Manual dogfood)

- [ ] B1..B4 acceptance criteria above all pass on a fresh `showcase-rich` run.
- [ ] `cleanup` restores the `demo-production` alias to the original winner.
- [ ] Phase accordion renders 7 phases (data / modeling / decision /
      portfolio / verify / agent / cleanup). **PRP-38 shipped 6;
      PRP-39 adds the new `portfolio` phase.**
- [ ] `pnpm tsc --noEmit -p tsconfig.app.json` clean.

---

## Final validation Checklist

- [ ] **B1** — `/explorer/runs/compare?a={v1}&b={v2}` Not-comparable badge with V row populated (manual dogfood).
- [ ] **B2** — `/ops` stale-alias row with `feature_frame_version_mismatch` + V mismatch detail row (manual dogfood).
- [ ] **B3** — `/ops` Promote button opens safer-Promote dialog with appropriate gates (manual dogfood).
- [ ] **B4** — `/visualize/batch/{batch_id}` shows completed batch with preset-source chip (manual dogfood).
- [ ] **B5** — `showcase-rich` e2e ≤ 240 s (`pytest -m integration`).
- [ ] **B6** — `test_phase_table_stable` + `PHASE_DEFS.test.ts` both green.
- [ ] **B7** — All five validation gates + frontend gates green.
- [ ] **R15** — `cleanup` step restores `demo-production` alias to original V2 winner (asserted in `test_cleanup_restores_alias` + integration test + manual dogfood).
- [ ] CHANGELOG entry: `feat(api,ui): showcase pipeline — decision + portfolio lifecycle (#<issue>)`.
- [ ] No `from 'radix-ui'` barrel imports introduced (grep guard).
- [ ] Vertical-slice guard empty: `git grep -nE "from app\.features\.[^.]+\." app/features/demo/ | grep -v "from app.features.demo"`.
- [ ] WebSocket schema diff empty: `git diff app/features/demo/schemas.py` shows no field changes.
- [ ] PHASE_DEFS lockstep: backend `_phase_table()` and frontend `PHASE_DEFS.ts` show the four new step rows in canonical order.
- [ ] `PRPs/ai_docs/prp-39-contract-probe-report.md` committed at `feat/showcase-39-decision-portfolio-lifecycle`'s first commit.
- [ ] RUNBOOKS extended with 4 new failure-mode entries.
- [ ] Manual dogfood: 7 phase cards render in idle state; PRP-38 shipped 6; PRP-39 adds the new portfolio phase.

---

## Anti-Patterns to Avoid

- ❌ **Do NOT import across slices.** No `from app.features.{registry,ops,batch}.X import Y` inside `app/features/demo/`. All calls go through `httpx.ASGITransport`. (G4 guard.)
- ❌ **Do NOT weaken `app/features/featuresets/tests/test_leakage.py`.** PRP-39 does not touch featuresets, but if any code path tempts a weakening, stop and reconsider.
- ❌ **Do NOT modify PRP-38 step implementations.** `step_v2_train`, `step_register`, `step_backtest` are read-only for PRP-39; PRP-39 ADDS new steps but never edits the ones PRP-38 shipped.
- ❌ **Do NOT use absolute phase indexes.** Every `_phase_table()` / `PHASE_DEFS` edit must be phrased relative to existing phase / step anchors. PRP-40 is a sibling slice; the second-to-merge must rebase cleanly. (G7.)
- ❌ **Do NOT add a backend `preset_id` field to `BatchSubmitRequest`.** Option A from D2 is decided; Option B is explicitly deferred. (D2.)
- ❌ **Do NOT extend `RunCompareResponse` with `compatible`/`comparable_reason`.** D1 is decided; derive client-side in the pipeline step. (D1.)
- ❌ **Do NOT add new wire fields to `StepEvent` or `DemoRunRequest`.** PRP-39 is purely additive at the step layer; the wire schema is frozen. (G5.)
- ❌ **Do NOT skip the alias restore in `cleanup`.** R15 is load-bearing; without it, the alias stays pointing at the deliberately-worse run after the demo finishes. The integration test catches this.
- ❌ **Do NOT widen the agent-mutation surface.** `agent_require_approval` is unchanged. PRP-41 handles the agent HITL flow.
- ❌ **Do NOT bake an assumption about PRP-40's phase anchor.** PRP-40 may insert `planning`/`knowledge` AFTER `portfolio` or BEFORE `agent` — PRP-39 must work either way.
- ❌ **Do NOT modify migrated Alembic migrations.** PRP-39 adds no migration; if a model_run insert ever needs a new column, that's a separate PRP.
- ❌ **Do NOT use bare `tsc --noEmit`.** Use `pnpm tsc --noEmit -p tsconfig.app.json` (G6). The root `tsconfig.json` has `"files": []` and will pass while the app tsconfig still has errors.
- ❌ **Do NOT hardcode store_id / product_id.** Use the `/dimensions/*` discovery pattern from `step_status`. (G8.)
- ❌ **Do NOT add AI co-author trailers to commits.** `.claude/rules/commit-format.md` enforces this; the hook blocks it.

---

## Confidence Score

**8 / 10** for one-pass implementation success.

**Why 8:**
- The contract probe is comprehensive; every backend surface PRP-39
  touches has been verified live against the running uvicorn.
- The four new steps reuse the well-trodden `step_v2_train` /
  `step_register` chain pattern; no novel mechanisms.
- D1/D2/D3 drift resolutions are baked into the pseudocode; the
  implementer doesn't need to re-derive them.
- The relative-anchor phase-insertion contract is spelled out (G7);
  the parallel-merge story with PRP-40 is documented.

**Why not 10:**
- The integration test depends on a real seeded `showcase_rich` DB
  that PRP-38 also depends on; cold-boot DB resets may add 90-180 s to
  the wall-clock budget that the soft-warn handles but the timing
  assertion may flake on slower hardware.
- The "synthetic V=3" trick in `stale_alias_trigger` works against the
  current OpsService logic because the integer JSONB key is opaque to
  the service — but if a future PRP adds a `V ∈ {1, 2}` validator on
  `runtime_info_extras`, this step breaks. (Mitigation: a regression
  test would catch it; the probe documents the trick explicitly.)
- The `batch_preset` step's `partial`-as-warn semantics depend on the
  underlying jobs actually succeeding. If a future change tightens the
  feature-pipeline so some grain×model pairs fail more often, the
  warn-vs-pass branch may flap. Acceptable but worth watching.

Reduce to 6 if any of D1/D2/D3 turn out to need a different
resolution after live integration; raise to 9 once the integration
test green-builds twice in CI.
