# INITIAL-showcase-39-decision-portfolio-lifecycle.md — Decision + Portfolio Lifecycle

> **Status:** Planning. Second sliced INITIAL of the four-PRP `/showcase`
> upgrade epic.
> **Parent:** `PRPs/INITIAL/INITIAL-showcase-rich-demo-control-center.md`
> **Sequence index:** `PRPs/INITIAL/INITIAL-showcase-rich-demo-index.md`
> **Prerequisites:** PRP-38 merged (needs phase accordion + ≥ 1 V2 run on the
> showcase grain).
> **Unlocks:** PRP-40 (scenarios run against the registered champion run).

## FEATURE:

Add the **registry-decision and portfolio-batch lifecycle** to `/showcase` so
visitors see how a real operator decides which model wins: champion-compat
comparison between a V1 baseline and a V2 feature-aware run, a deliberate
stale-alias trigger (V mismatch), a safer-Promote dialog walk-through, and a
small portfolio batch sweep that exercises the PRP-37 batch preset + matrix
picker.

After this PRP merges, a visitor running `/showcase` on the `showcase-rich`
scenario can see:

- A "Not comparable" badge with `feature_frame_version` row populated on the
  `/explorer/runs/compare?a={v1_run}&b={v2_run}` page that the Inspect link
  opens.
- A stale-alias chip on `/ops` with `stale_reason="feature_frame_version_mismatch"`
  and the V mismatch detail row populated.
- A safer-Promote dialog (`PromoteConfirmationDialog`) walked through end-to-end
  by the pipeline step, with the alias swapped to the new champion when the
  step completes.
- A completed batch detail page (`/visualize/batch/{batch_id}`) populated by a
  3 × 2 × 3 `quick_baseline_sweep` preset run on the showcase grain.

### Scope (one shippable PR)

**Backend (`app/features/demo/pipeline.py`):**

Add four new steps. Three extend the existing `decision` phase that PRP-38
already shipped (currently `backtest` → `register`); one lands in a brand-new
`portfolio` phase. PRP-39 does NOT create the `decision` phase — it only
extends it.

**Phase: `decision`** — **extends** the existing PRP-38 phase. Insert the
three new steps AFTER `register` (so the new champion run is available to
the comparison + promotion steps that follow) and BEFORE the next phase
(`verify` today, `portfolio` once PRP-39 lands).

- `champion_compat_compare` — `GET /registry/compare/{v1_run_id}/{v2_run_id}`.
  Captures the diff and embeds `feature_frame_version_a`/`_b` +
  `compatible: false` in `step.data`.
- `stale_alias_trigger` — register a SECOND V2 run with controlled
  `runtime_info_extras.feature_frame_version` value different from PRP-38's V2
  run on the SAME grain with OVERLAPPING `data_window_start`/`data_window_end`,
  so `OpsService` surfaces `stale_reason="feature_frame_version_mismatch"`
  via `GET /ops/summary`. Captures the stale alias detail in `step.data`.
- `safer_promote_flow` — `POST /registry/aliases` to swap the alias to a new
  run with worse (or comparable) WAPE so the safer-Promote dialog gates fire
  when a human visits the page. Captures the alias name + before/after run_id
  pair.

**Phase: `portfolio`** — **new** phase. Insert between the existing `decision`
phase (after PRP-39's `safer_promote_flow` step) and the existing `verify`
phase. Adopt a relative-anchor insertion (e.g., "before the `verify` phase
row"), NOT an absolute index — PRP-40 may be authored / merged in parallel
and will also touch `_phase_table()` + `PHASE_DEFS`.

- `batch_preset` — drive `POST /batch/forecasting` for the
  `quick_baseline_sweep` preset's expanded matrix (3 stores × 2 products ×
  3 models, drawn from the showcase grain's neighbors). **Caveat:** the
  `quick_baseline_sweep` preset is a frontend-only construct today
  (`frontend/src/components/forecast-intelligence/batch-preset-utils.ts:24`);
  the backend `BatchSubmitRequest` does NOT currently accept a `preset_id`
  field — it takes `kind` + explicit `store_ids` × `product_ids`. Task 1
  (contract probe) MUST resolve this; the PRP author picks ONE of:
  (a) expand the preset client-side and POST the same `BatchSubmitRequest`
  shape the UI already uses (`kind=MANUAL`, explicit `store_ids` +
  `product_ids` + `model_types`), OR
  (b) add a small additive `preset_id: str | None` field to
  `BatchSubmitRequest` + server-side expansion. Then poll
  `GET /batch/{batch_id}` until `status="completed"` or a 90 s timeout.
  Captures `batch_id`, `preset_id` (or `kind` if option a), `item_count`,
  `completed_count`.

Each new step:
- Emits `step_start` + `step_complete` events with `phase_name=decision|portfolio`.
- Uses `_HTTP_TIMEOUT` (120 s).
- Mirrors the existing `_StepError` RFC 7807 surfacing.

**Frontend (`frontend/src/pages/showcase.tsx` + `components/demo/`):**

- Extend `PHASE_DEFS` (`frontend/src/components/demo/PHASE_DEFS.ts`):
  append the three new step rows under the EXISTING `decision` phase, and
  insert the brand-new `portfolio` phase between `decision` and `verify`
  (relative-anchor insertion — PRP-40 may concurrently insert
  `planning` / `knowledge` and the merge order must not break either
  PRP). Backend `_phase_table()` ships the matching addition in lockstep.
- Per-step Inspect button (PRP-38 pattern):
  - `champion_compat_compare` → `/explorer/runs/compare?a={v1_run_id}&b={v2_run_id}`
  - `stale_alias_trigger` → `/ops` (the stale-alias chip should now be visible)
  - `safer_promote_flow` → `/ops` (the Promote button opens the safer-Promote
    dialog with the new alias state)
  - `batch_preset` → `/visualize/batch/{batch_id}`
- Step card extensions:
  - `champion_compat_compare` card renders a one-row mini summary:
    `V_a=1 · V_b=2 · compatible=false · reason=feature_frame_version_mismatch`.
  - `stale_alias_trigger` card renders the alias name + stale_reason chip.
  - `safer_promote_flow` card renders before/after run_id chips.
  - `batch_preset` card renders preset_id (option b) OR `kind=MANUAL`
    (option a) + completed_count/item_count.
- No new shadcn primitives required — Card + Badge + Button already imported.

### What PRP-39 is NOT

- Scenario simulate/save/compare — **PRP-40**.
- RAG indexing + embedding-provider probe — **PRP-40**.
- Agent HITL flow — **PRP-41**.
- Ops snapshot card / KPI strip / Inspect-Artifacts post-run panel /
  localStorage run history / Stop button / walkthrough docs — **PRP-41**.

### Acceptance criteria

| # | Criterion | Verifiable by |
|---|-----------|---------------|
| B1 | After a `showcase-rich` run, `/explorer/runs/compare?a={v1}&b={v2}` champion-compat badge reads "Not comparable" with `feature_frame_version` populated. | Manual dogfood |
| B2 | After a `showcase-rich` run, `/ops` shows a stale-alias row with `stale_reason="feature_frame_version_mismatch"` and the V mismatch detail row populated. | Manual dogfood |
| B3 | After a `showcase-rich` run, `/ops` Promote button on the new champion run opens the safer-Promote dialog with the worse-WAPE-ack gate (if applicable) and V-mismatch-ack gate (if applicable). | Manual dogfood |
| B4 | After a `showcase-rich` run, `/visualize/batch/{batch_id}` shows the batch with completed items + the preset-source chip (preset_id if option b is taken, or `kind=MANUAL` if option a). | Manual dogfood |
| B5 | `showcase-rich` end-to-end (PRP-38 + PRP-39 phases) finishes ≤ 240 s. | `pytest -m integration` |
| B6 | Backend `_phase_table()` and frontend `PHASE_DEFS` still match (both updated in lockstep). | `test_phase_table_stable` |
| B7 | All five validation gates green. | CI |

## EXAMPLES:

**Pattern to imitate (the existing demo slice — PRP-38 baseline):**

- `app/features/demo/pipeline.py` — extend `_step_table()` additively.
- `app/features/demo/pipeline.py::step_register` (line 487) — pattern for the
  registry create + PATCH chain used in `stale_alias_trigger`.

**Pattern to imitate (PRP-37 frontend surfaces):**

- `frontend/src/components/forecast-intelligence/champion-compatibility-badge.tsx`
  + `champion-compatibility-utils.ts` — the badge `champion_compat_compare`
  lights up.
- `frontend/src/components/forecast-intelligence/promote-confirmation-dialog.tsx`
  — the dialog `safer_promote_flow` walks through.
- `frontend/src/components/forecast-intelligence/batch-preset-select.tsx` +
  `batch-matrix-picker.tsx` + `batch-preset-utils.ts` — the 5 presets
  (`batch_preset` step uses `quick_baseline_sweep`).
- `frontend/src/pages/ops.tsx` — the stale-alias chip rendering (no change
  required; PRP-39 just produces the data that lights it up).

**Backend surfaces consumed:**

- `app/features/registry/routes.py:GET /registry/compare/{a}/{b}` — diff
  endpoint. Response shape: `{run_a, run_b, config_diff, metrics_diff,
  comparable, comparable_reason}` (verify in Task 1 contract probe).
- `app/features/registry/service.py:find_comparable_runs` — the comparable-run
  rule (`grain + overlapping window + same feature_frame_version`).
- `app/features/ops/service.py` — stale-alias detection (V mismatch enum
  `FEATURE_FRAME_VERSION_MISMATCH` at `app/features/ops/schemas.py:28`).
- `app/features/batch/routes.py:POST /batch/forecasting` + `GET /batch/{id}`
  — batch endpoints. Verify the preset/matrix request shape in the Task 1
  probe (`app/features/batch/schemas.py`).

## DOCUMENTATION:

**Internal (load when authoring PRP-39):**

- `AGENTS.md` § Architecture & Conventions — vertical-slice rule.
- `docs/_base/DOMAIN_MODEL.md` § "Key Invariants" — **Comparable-run rule**
  (same grain + overlapping window + same `feature_frame_version`) and
  **Stale-alias V mismatch** (`feature_frame_version_mismatch` is a distinct
  enum value from `newer_success_run`). PRP-39 produces both.
- `docs/_base/API_CONTRACTS.md` — registry, ops, batch endpoints.
- `docs/_base/RUNBOOKS.md` § "Showcase page (`/showcase`) pipeline fails at
  step X" — extend additively for `champion_compat_compare`,
  `stale_alias_trigger`, `safer_promote_flow`, `batch_preset` failure modes.
- `.claude/rules/security-patterns.md` — registry mutations stay HITL-gated
  (PRP-39 only invokes them automatically as part of the demo pipeline; this
  is fine because the demo slice has no agent-tool surface).

**External (load via `mcp__claude_ai_contex7__`):**

- shadcn/ui Badge: <https://ui.shadcn.com/docs/components/badge>
- shadcn/ui AlertDialog: <https://ui.shadcn.com/docs/components/alert-dialog>
  (already used by PromoteConfirmationDialog)
- TanStack Query polling: <https://tanstack.com/query/latest/docs/framework/react/guides/query-options#refetchinterval>

**Prior-art PRPs (read for pattern):**

- `PRPs/PRP-36-forecast-intelligence-B-model-zoo-backtesting.md` — defines the
  comparable-run rule and the stale-alias V mismatch enum value.
- `PRPs/PRP-37-forecast-intelligence-C-interactive-ui.md` — defines the
  champion-compat badge, safer-Promote dialog, batch preset + matrix picker.
- `PRPs/PRP-38-showcase-data-modeling-lifecycle.md` — PRP-39's prerequisite;
  ships the phase accordion + the FIRST V2 run on the showcase grain that
  PRP-39's `champion_compat_compare` consumes.

## OTHER CONSIDERATIONS:

### Hard constraints (from the parent INITIAL)

- **No new tables.**
- **Vertical-slice rule.** No new direct imports — all calls through ASGI.
- **WebSocket contract additive only.**
- **Phase table lockstep** — `_phase_table()` + `PHASE_DEFS` updated together.
- **Skip gracefully** — none of PRP-39's steps depend on external providers,
  but document the pattern for consistency with PRP-40/41.

### Risks specific to PRP-39

| # | Risk | Mitigation |
|---|------|------------|
| R3 (from parent) | V-mismatch staleness needs hand-crafted run pairs. | `stale_alias_trigger` registers a SECOND V2 run on the same `(store_id, product_id)` as PRP-38's V2 run, with OVERLAPPING window, and `runtime_info_extras.feature_frame_version` set to a value different from the existing alias's run (e.g., V=3 vs V=2 on the existing alias). The alias is left pointing at the older V; `OpsService.find_stale_aliases` then surfaces the V mismatch. Unit test asserts the stale-alias row's `stale_reason`. |
| R13 | Batch poll can exceed 90 s on a slow host. | Cap matrix at 3 × 2 × 3 = 18 items (smallest meaningful preset coverage). If the integration test exceeds 90 s, drop to 2 × 2 × 3 = 12. The `batch_preset` step emits `warn` (not `fail`) if the poll times out — the batch keeps running asynchronously, the visitor can refresh `/visualize/batch` later. |
| R14 | `champion_compat_compare` fails if PRP-38's V2 run doesn't exist (e.g., user ran with `scenario=demo_minimal` so V2 was skipped). | Step emits `skip` with detail `"no V2 run on the showcase grain — run with scenario=showcase-rich"`. |
| R15 | `safer_promote_flow` may flip the production alias to a worse-WAPE run — undesirable for a demo "left in production" state. | After the demo run, register a final `cleanup_promote_back` sub-step (or rely on the existing `cleanup` step) that restores the alias to the original winner. Confirm in the dogfood checklist. |
| R7 (from parent) | HANDOFF accuracy — re-run `pnpm tsc --noEmit -p tsconfig.app.json`. | Required. |

### Performance budget

- PRP-39 adds ≤ 60 s to the `showcase-rich` end-to-end budget. Total stays
  ≤ 240 s.
- Per-step timeout: 120 s. Batch poll uses an explicit 90 s cap.

### Validation plan (PRP-39 specific)

**Task 1 — Contract Probe:**

- Verify these backend fields/endpoints exist on `dev` post-PRP-38:
  - `GET /registry/compare/{a}/{b}` — response schema fields.
  - `OpsService` stale-alias detection — `stale_reason` enum values,
    `v_mismatch_detail` field (or equivalent in `app/features/ops/schemas.py`).
  - `POST /batch/forecasting` — request shape (preset, matrix), response shape.
  - `GET /batch/{id}` — status enum + item count fields.
- Output to `PRPs/ai_docs/prp-39-contract-probe-report.md`.

**Backend tests (new):**

- `app/features/demo/tests/test_pipeline.py::test_champion_compat_compare_step`
  — asserts `data.compatible == False` + `data.feature_frame_version_a == 1` +
  `data.feature_frame_version_b == 2`.
- `app/features/demo/tests/test_pipeline.py::test_stale_alias_trigger_step`
  — registers two V2 runs with different V; asserts `/ops/summary` lists the
  alias with `stale_reason="feature_frame_version_mismatch"`.
- `app/features/demo/tests/test_pipeline.py::test_safer_promote_step` —
  asserts the alias points to the new run after the step + `cleanup` restores
  the original.
- `app/features/demo/tests/test_pipeline.py::test_batch_preset_step` — asserts
  a batch row exists with the expected matrix size + completed status (or
  `warn` on poll timeout).

**Frontend tests (new):**

- `frontend/src/components/demo/PHASE_DEFS.test.ts` — extends the fixture
  with the three new `decision`-phase step rows AND the brand-new
  `portfolio` phase.
- `frontend/src/components/demo/demo-step-card.test.tsx` — Inspect button
  deep-links for the four new steps.

**Manual dogfood checklist (PRP-39 specific):**

- [ ] B1..B4 acceptance criteria above all pass on a fresh `showcase-rich` run.
- [ ] `cleanup` restores the `demo-production` alias to the original winner.
- [ ] Phase accordion renders 7 phases (data / modeling / decision / portfolio
      / verify / agent / cleanup). PRP-38 shipped 6; PRP-39 adds the new
      `portfolio` phase.
- [ ] `pnpm tsc --noEmit -p tsconfig.app.json` clean.

### Stop-and-ask gates (PRP-39)

- Before flipping the `demo-production` alias permanently — confirm the
  cleanup restore is wired and tested.
- Before adding a new `app/features/demo/` cross-slice import — refactor
  through the existing ASGI client.

### Future issue title (suggested)

`feat(api,ui): showcase pipeline — decision + portfolio lifecycle`

## PRP GENERATION COMMAND

Generate the PRP from this INITIAL with:

```
/base_prp:prp-create PRPs/INITIAL/INITIAL-showcase-39-decision-portfolio-lifecycle.md
```

**Position in the epic:** **SECOND** of four PRPs in the `/showcase` upgrade.
**Prerequisite:** PRP-38 must be merged first — this slice consumes the V2
run on the showcase grain that PRP-38 registers (powers
`champion_compat_compare` and seeds the same-grain target for
`stale_alias_trigger`).
