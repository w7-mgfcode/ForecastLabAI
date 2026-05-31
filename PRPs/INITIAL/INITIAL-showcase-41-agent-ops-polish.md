# INITIAL-showcase-41-agent-ops-polish.md — Agent HITL + Ops + Final Polish

> **Status:** Planning. Fourth and final sliced INITIAL of the four-PRP
> `/showcase` upgrade epic.
> **Parent:** `PRPs/INITIAL/INITIAL-showcase-rich-demo-control-center.md`
> **Sequence index:** `PRPs/INITIAL/INITIAL-showcase-rich-demo-index.md`
> **Prerequisites:**
> - PRP-39 (#316) AND PRP-40 (#315) merged into `dev` ✅
> - Issue #312 (`fix(seeder): make phase2 enrichment idempotent`) merged
>   before PRP-41 dogfood — the 16-line manual checklist below re-runs
>   `showcase-rich` against a populated DB; the current `IntegrityError →
>   HTTP 500` on a repeated `POST /seeder/phase2-enrichment` would block
>   that. **Out of PRP-41 scope** (separate seeder fix), but must land
>   before PRP-41's dogfood pass to keep the checklist runnable.
> **Unlocks:** epic complete.

## FEATURE:

Close out the `/showcase` upgrade epic. PRP-41 ships the **last two pipeline
phases** (agent HITL approval round-trip + ops snapshot) and all the
**cross-cutting UI polish** that turns the now-rich timeline into a
production-feeling demo control center: a top KPI strip, a post-run
Inspect-Artifacts grid that deep-links into every dashboard surface the run
populated, a localStorage-backed "last 5 runs" replay strip, a Stop button
that cancels an in-flight run, and a one-click Approve button surfaced on
the HITL step card. The epic's walkthrough doc (`docs/user-guide/showcase-walkthrough.md`)
is also finalised here — every "planned" marker for behaviour this epic
delivered is removed, and the runbook gains the new failure-mode entries.

After this PRP merges, a first-time visitor lands on `/showcase`, picks
`showcase-rich`, clicks Run, and within ≤ 240 s sees:

- A live phase accordion (PRP-38) with V1+V2 runs landing in the modeling
  phase, decision + portfolio phases lighting up registry surfaces (PRP-39),
  planning + knowledge phases populating saved scenarios and the RAG corpus
  (PRP-40), then the new **`agents` phase** opening an experiment session,
  triggering `save_scenario`, surfacing an `approval_required` event the
  visitor can approve in one click (or auto-approve after 3 s), then the new
  **`ops` phase** snapshotting `/ops/summary` + `/ops/retraining-candidates`
  + `/ops/model-health/{grain}` into a small KPI grid in the step card.
- A **top KPI strip** with 5 populated tiles (runs registered, aliases live,
  batch items completed, scenario plans saved, RAG chunks indexed) — counts
  fold in from the running pipeline's step `data` payloads with no extra
  fetches.
- An **Inspect-Artifacts panel** rendered on `pipeline_complete` — a grid of
  10 deep-link cards into every dashboard surface the run populated.
- A **run history strip** above the controls card showing the last 5 pipeline
  runs (timestamp · scenario · duration · status · Replay), persisted in
  `localStorage` (no new tables).
- A **Stop button** visible during `phase === 'running'` — closes the
  WebSocket client-side so the visitor can free the module-level
  `asyncio.Lock` without waiting for a stuck step.

### Scope (one shippable PR — the largest in the epic)

**Backend (`app/features/demo/pipeline.py`):**

Add the two new phases that round out the lifecycle. Both REPLACE the
existing thin steps with richer ones; they do not delete those steps from
the public surface — they evolve `step_agent` into `agent_hitl_flow` (same
phase position) and append `ops_snapshot` as a brand-new step in a new
`ops` phase.

**Phase: `agents`** (sits after `knowledge` from PRP-40, replacing the
existing `agent` step's position)
- `agent_hitl_flow` — opens an experiment session via
  `POST /agents/sessions` (`agent_type="experiment"`), then sends a message
  that triggers `save_scenario` (the tool already lives in
  `agent_require_approval` per `app/core/config.py:184` and
  `app/features/agents/agents/experiment.py:419`). Suggested prompt:
  *"Save a 10% price-cut scenario plan for the demo-production model as
  'showcase-agent-savedplan'."*
  - The chat round-trip returns a response with an `approval_required` event
    in its tool-call list. The step captures the pending `tool_call_id`,
    sets Optional `awaiting_approval=true` + `approval_url="/agents/sessions/{id}/approve"`
    in the StepEvent `data` payload, and emits a `step_complete`-shaped
    intermediate event with status `running` so the UI can render the
    approve button (or the pipeline sleeps 3 s then auto-approves).
  - Calls `POST /agents/sessions/{id}/approve` after the 3 s display delay
    OR when a frontend one-click approve hits the same endpoint first
    (whichever wins).
  - Captures `tokens_used`, `tool_calls_count`, `approval_decision`,
    `session_id` into `step.data`.
  - Skip-gracefully gate: `_llm_key_present()` returns False → emit `skip`
    with the same wording the existing `step_agent` uses
    (`app/features/demo/pipeline.py::step_agent`; file lines drifted by
    PRP-39 + PRP-40 — locate by symbol, not by line number).
  - Hard fallback: if no approval within 90 s, emit `skip` with detail
    `"approval timed out — pipeline continued"` and continue.

**Phase: `ops`** (after `agents`, before `cleanup`)
- `ops_snapshot` — fetches `GET /ops/summary`,
  `GET /ops/retraining-candidates?limit=5`,
  `GET /ops/model-health?limit=5` — the model-health endpoint takes ONLY
  `limit`; **no `grain` query param exists**. Results are sorted
  degrading-first across all `(store, product)` grains; the demo step counts
  entries whose drift verdict is `degrading`. Embeds a small KPI summary in
  `step.data`:
  ```
  {
    "stale_aliases_count": int,           # sum(a.is_stale for a in summary.aliases)
    "retraining_candidates_count": int,   # len(retraining_candidates_body.candidates)
    "total_runs": int,                    # summary.runs.<count field on RunHealth>
    "total_aliases": int,                 # len(summary.aliases)
    "degrading_health_count": int         # count of entries with drift_verdict == "degrading"
  }
  ```
  so the frontend renders a small KPI mini-grid in the step card without a
  second fetch.

  **Derivation note.** `/ops/summary` (response model `OpsSummaryResponse`)
  has **no flat top-level** `stale_aliases` / `total_aliases` / `alias_count`
  keys. Its actual shape is `system`, `jobs`, `runs`, `aliases: list[AliasHealth]`,
  `freshness`, `attention_items`, `generated_at`. Staleness lives on each
  `AliasHealth.is_stale: bool` — the demo step computes
  `stale_aliases_count = sum(a.is_stale for a in body.aliases)` and
  `total_aliases = len(body.aliases)`. `retraining_candidates_count` is
  derived from the separate `/ops/retraining-candidates` response; the
  `degrading_health_count` filters `ModelHealthResponse.entries` (or the
  list field actually emitted — confirm in the Task-1 contract probe) by
  `drift_verdict == "degrading"`.

Update `step_cleanup` (existing, `app/features/demo/pipeline.py::step_cleanup`) only
if the HITL session is not already covered by its existing
`DELETE /agents/sessions/{id}` path — the existing close path likely
already covers `ctx.session_id`, but the contract probe MUST confirm.

**Backend `_step_table()` / `_phase_table()` extension:**

- Replace the legacy `("agent", step_agent)` row with
  `("agent_hitl_flow", step_agent_hitl_flow)` under `phase_name="agents"`.
- Append `("ops_snapshot", step_ops_snapshot)` under `phase_name="ops"` before
  the existing `cleanup` row.
- Bump phase totals + frontend `PHASE_DEFS` in lockstep (R7 already proved
  the test that enforces this).

**Schema additions (`app/features/demo/schemas.py`):**

- `StepEvent.data` is already free-form `dict[str, Any]`, so no model
  changes required. Document the new payload keys in the docstring
  additively (`awaiting_approval: bool | None`, `approval_url: str | None`,
  KPI keys for `ops_snapshot`).

**Frontend (`frontend/src/pages/showcase.tsx` + `components/demo/`):**

Five cross-cutting polish surfaces, all additive.

1. **KPI strip** — `frontend/src/components/demo/ShowcaseKpiStrip.tsx`
   (new). Horizontal strip of 5 tiles rendered at the top of `/showcase`,
   hidden until the first `step_complete` event arrives. Counts (every key
   name below has been verified against PRP-39/PRP-40 emitted `step.data`
   payloads on `dev` — never invent a key, always grep the step function in
   `app/features/demo/pipeline.py` first):
   - `runs_registered` — count `register` + `stale_alias_trigger` +
     `safer_promote_flow` + `v2_train` events with a populated
     `step.data.run_id` (all four steps emit `run_id` on PASS).
   - `aliases_live` — read the new `ops_snapshot` step's
     `step.data.total_aliases` (the step computes it from
     `len(OpsSummaryResponse.aliases)` — there is **no flat `alias_count`
     key** on `/ops/summary` to consume directly). Fall back to counting
     events with a populated `step.data.alias` key across `register` /
     `safer_promote_flow` / `stale_alias_trigger` when `ops_snapshot` was
     skipped.
   - `batch_items_completed` — from `batch_preset` `step.data.completed_items`
     (PRP-39 emits `completed_items` / `total_items` / `failed_items` —
     there is **no `completed_count` key**; see `step_batch_preset` in
     `app/features/demo/pipeline.py`).
   - `scenario_plans_saved` — count `scenario_simulate_and_save` events with
     a populated `step.data.scenario_id` (1 per run on PASS) PLUS
     `multi_plan_compare` events with a populated
     `step.data.winner_scenario_id` AND `step.data.ranked` of length ≥ 2
     (1 per run on PASS — the holiday plan saved successfully). PRP-40's
     actual step names are `scenario_simulate_and_save` and
     `multi_plan_compare` — there is **no `scenario_save` or
     `scenario_compare` step**.
   - `rag_chunks_indexed` — from `rag_index_subset` `step.data.total_chunks`
     (the chunks emitted across this run's curated 5-file index pass —
     PRP-40 does **not** emit a `chunks_indexed` key). `curated_hits`
     (files matched against the curated allow-list) is the natural
     files-indexed companion; `indexed` / `updated` / `unchanged` /
     `failed` give per-file outcome counts on the same payload.
   The hook returns derived counters; the tile renders `Card` + a single
   number + label.

2. **Inspect-Artifacts panel** —
   `frontend/src/components/demo/InspectArtifactsPanel.tsx` (new). Rendered
   after `phase === 'complete'`. A `grid grid-cols-2 lg:grid-cols-5 gap-4`
   of 10 deep-link cards:
   - `/visualize/forecast?store_id=…&product_id=…` — Forecast: V1 + V2
     ready
   - `/visualize/backtest?store_id=…&product_id=…` — Backtest with
     horizon buckets
   - `/visualize/batch/{batch_id}` — Portfolio sweep results
   - `/visualize/planner` — Saved scenario plans (the 10% price-cut)
   - `/explorer/runs` — Multi-run registry list
   - `/explorer/runs/{v2_prophet_run_id}` — V2 Feature Frame panel
   - `/explorer/runs/compare?a={v1_run_id}&b={v2_run_id}` — Champion-compat
     "Not comparable" badge
   - `/ops` — Stale-alias chip + Model Health table
   - `/knowledge` — Indexed corpus + semantic search probe
   - `/chat` — Agent transcript with the approved tool call
   Each card: page name + one-line "what's new here after this run" detail.
   Deep-link params come from the step `data` payloads cached in the hook;
   any missing id renders that card disabled with a tooltip.

3. **Run history strip** —
   `frontend/src/components/demo/RunHistoryStrip.tsx` (new). Reads/writes
   `localStorage` key `forecastlab.showcase.runs.v1` (cap 5 entries; FIFO
   eviction). Each row: timestamp · scenario · `wall_clock_s` · overall
   status · Replay button (re-fills the controls card with the saved
   scenario + checkboxes; one click and the visitor can press Run). Persists
   only on `pipeline_complete` / `error`; no schema, no fetch.

4. **Stop button** — visible in the controls card during
   `phase === 'running'`. Wires to a new `stop()` mutation exposed from
   `useDemoPipeline()` (`frontend/src/hooks/use-demo-pipeline.ts`) that
   calls the existing `disconnect()` from `useWebSocket()`. Backend already
   breaks on `WebSocketDisconnect` (verified — `/demo/stream` releases the
   `asyncio.Lock` on disconnect). UI returns to `idle` within 5 s of click;
   a toast or inline notice surfaces "Pipeline cancelled by user".

5. **One-click Approve button** — extends `DemoStepCard` so that when
   `step.data.awaiting_approval === true` and `step.status === 'running'`,
   the card renders a primary `Approve` button. Button calls
   `POST /agents/sessions/{session_id}/approve` (URL from
   `step.data.approval_url`), reflects the result inline (sets a local
   `optimistic_approved` flag). When the pending state exceeds 30 s, the
   card surfaces a warning callout *"Still waiting for approval — auto-approve
   in {N}s"* using the same step-start timestamp.

6. **Step card extension** — `DemoStepCard` renders a small KPI mini-grid
   from `step.data` when `step_name === 'ops_snapshot'` (5 number tiles in a
   `grid grid-cols-5 gap-2 text-xs` layout).

7. **Phase accordion unlock after completion (fold-in of issue #311)** —
   `frontend/src/components/demo/DemoPhasePanel.tsx` currently renders the
   shadcn `<Accordion value={value}>` fully-controlled with no
   `onValueChange` handler. While the pipeline runs, `value` follows
   `runningPhase` and auto-advances the open panel — works as intended.
   After `pipeline_complete`, `runningPhase` becomes `null` and `value`
   falls back to `phases[0]?.id` (i.e., `'data'`); clicks on later phase
   headers register focus but Radix immediately snaps the open panel back
   to `data` because the controlled `value` never moves. The PRP-41
   Inspect-Artifacts panel + Run-history Replay UX assumes the visitor
   can re-open any phase post-run to inspect step cards, so this is
   load-bearing polish for the dogfood checklist below.
   Fix: thread an `onValueChange={setValue}` handler (with `value` lifted
   to local state seeded from `runningPhase`), so post-run clicks toggle
   panels normally and a fresh run reseats the running phase. Tracked by
   GitHub issue #311.

### Walkthrough docs (in scope of PRP-41 only)

PRP-41 updates `docs/user-guide/showcase-walkthrough.md` (the planning-track
draft already exists per the parent INITIAL line 14) to remove all "planned"
markers for behaviour this epic has now delivered. Specifically:

- Phase walkthrough: ensure each of the six new phases (data / modeling /
  decision / portfolio / planning / knowledge / agents / ops) has a short
  prose description with a screenshot placeholder.
- KPI strip + Inspect-Artifacts panel: document both with the deep-link
  table.
- R6 callout: keep the `frontend/.env` `VITE_API_BASE_URL=http://localhost:8123`
  gotcha explicit and prominent.

Extend `docs/_base/RUNBOOKS.md` § "Showcase page (`/showcase`) pipeline
fails at step X" with the new failure modes PRP-41 introduces:

- `agent_hitl_flow` skipped (no LLM key) — point to `.env` check.
- `agent_hitl_flow` stuck > 90 s — auto-skip explanation.
- `ops_snapshot` empty payload — pre-PRP-39 DB (no stale aliases yet).
- Stop button used mid-run — explain the `asyncio.Lock` release semantics.

### What PRP-41 is NOT

These belong to earlier slices and MUST NOT regress:

- Phase accordion + scenario picker + V1/V2 modeling — **PRP-38**.
- Champion-compat compare + stale-alias trigger + safer-Promote walk-through
  + batch preset — **PRP-39**.
- Scenario simulate/save/compare + RAG indexing + embedding-provider probe —
  **PRP-40**.

PRP-41 also does NOT add:
- Persistent server-side run history (would force a new table — violation).
- Shareable replay URLs (out of scope per the parent's "NOT Option C" call).
- A guided-tour overlay (deferred indefinitely).

### Acceptance criteria

| # | Criterion | Verifiable by |
|---|-----------|---------------|
| D1 | After a `showcase-rich` run, `/showcase` shows a top KPI strip with 5 populated tiles. | Manual dogfood + `kpi-strip.test.tsx` |
| D2 | After `pipeline_complete`, the Inspect-Artifacts panel renders all 10 deep-link cards. | Manual dogfood + `inspect-artifacts-panel.test.tsx` |
| D3 | The `agent_hitl_flow` step card surfaces a one-click Approve button when `awaiting_approval=true`; clicking it advances the step within 3 s. | Manual dogfood + `demo-step-card.test.tsx` extension |
| D4 | Stop button cancels an in-flight run; the page returns to `idle` within 5 s of click. | Manual dogfood + `use-demo-pipeline.test.ts::stop` |
| D5 | localStorage holds the last 5 run summaries; the Replay button re-fills the controls. | Manual dogfood + `run-history-strip.test.tsx` |
| D6 | `docs/user-guide/showcase-walkthrough.md` has no remaining "planned" markers for behaviour this epic delivered. | `grep -n "planned" docs/user-guide/showcase-walkthrough.md` returns no in-scope hits |
| D7 | `showcase-rich` end-to-end (PRP-38 + PRP-39 + PRP-40 + PRP-41 phases) still ≤ 240 s. | `pytest -m integration` wall-clock assertion |
| D8 | Backend `_phase_table()` and frontend `PHASE_DEFS` still match. | `test_phase_table_stable` (both sides) |
| D9 | All five validation gates green. | CI |
| D10 | Phase accordion is no longer pinned to `data` after `pipeline_complete`; clicking any later phase header opens it (closes issue #311). | Manual dogfood + a new `DemoPhasePanel.test.tsx` case asserting `onValueChange` toggles the open panel post-run |

## EXAMPLES:

**Pattern to imitate (the existing demo slice — PRP-38..40 baseline):**

- `app/features/demo/pipeline.py::step_agent` — existing single-turn chat
  step. `agent_hitl_flow` extends this pattern with the approval
  round-trip; the `_StepError` → `skip` mapping stays identical. (Locate
  by symbol — PRP-39 + PRP-40 shifted file lines substantially.)
- `app/features/demo/pipeline.py::step_cleanup` — existing session-close
  pattern. `agent_hitl_flow` reuses `ctx.session_id` so cleanup keeps
  working unchanged.
- `app/features/demo/pipeline.py::_llm_key_present` — skip-gracefully gate.
  `agent_hitl_flow` MUST call this first.
- `app/features/demo/pipeline.py::_step_table` (and the matching
  `_phase_table`). PRP-41 replaces the `("agent", step_agent)` entry and
  appends `("ops_snapshot", …)`.

**Pattern to imitate (agents HITL flow):**

- `app/features/agents/service.py::approve_action` — the endpoint
  `agent_hitl_flow` calls. Returns the approved tool's result.
- `app/features/agents/service.py` — `approval_required` event emission
  (grep for `event_type="approval_required"`; the shape the chat response
  carries when a gated tool is hit).
- `app/features/agents/agents/experiment.py::tool_save_scenario` — gated by
  `requires_approval("save_scenario")` and lives in `agent_require_approval`
  (`app/core/config.py:184` — verified single-line cite). PRP-41 does NOT
  widen this list — it consumes the existing gate.

**Pattern to imitate (ops snapshot):**

- `app/features/ops/routes.py::get_ops_summary` — `GET /ops/summary`.
- `app/features/ops/routes.py::get_retraining_candidates` — `GET /ops/retraining-candidates` (takes `?limit=` only).
- `app/features/ops/routes.py::get_model_health` — `GET /ops/model-health`
  (takes `?limit=` only; **no `grain` query param** — results are sorted
  degrading-first across all grains).
- `app/features/ops/schemas.py` — `OpsSummaryResponse`,
  `RetrainingCandidatesResponse`, `ModelHealthResponse`. Verify the response
  shape in the Task 1 contract probe. Key fields actually on
  `OpsSummaryResponse`: `system`, `jobs`, `runs`, `aliases: list[AliasHealth]`,
  `freshness`, `attention_items`, `generated_at` — no flat
  `stale_aliases` / `alias_count` keys; derive those.

**Pattern to imitate (frontend):**

- `frontend/src/hooks/use-demo-pipeline.ts::useDemoPipeline` — existing
  hook shape; the hook already holds a `disconnectRef` pointing at the
  `disconnect()` returned by `useWebSocket()`. `stop()` is a new
  `useCallback` that calls `disconnectRef.current?.()` and resets the step
  state to idle.
- `frontend/src/pages/showcase.tsx` — `useDemoPipeline()` consumer
  pattern; `stop` joins the destructure alongside `start`.
- `frontend/src/lib/constants.ts:ROUTES` — deep-link source of truth the
  Inspect-Artifacts panel consumes; PRP-41 adds no new routes (every page
  the panel links to already exists post-PRP-37/38/39/40).

## DOCUMENTATION:

**Internal (load when authoring PRP-41):**

- `AGENTS.md` § Safety — `agent_require_approval` is the load-bearing list.
  PRP-41 verifies `save_scenario` is in it, does NOT modify it.
- `docs/_base/SECURITY.md` § "LLM / Agent Security" — HITL approval is the
  security boundary. PRP-41 invokes the gate from a non-agent caller (the
  pipeline) — confirm this is fine (it is — the pipeline's `approve_action`
  call is just a normal HTTP request from a server-side context with no
  human bypass).
- `docs/_base/API_CONTRACTS.md` — agents + ops + demo endpoints. The
  `WS /demo/stream` subsection is the additive-contract baseline; PRP-41
  documents the new `step.data` keys additively.
- `docs/_base/RUNBOOKS.md` § "Showcase page (`/showcase`) pipeline fails at
  step X" — extend additively for `agent_hitl_flow` + `ops_snapshot` +
  Stop button + KPI strip.
- `docs/_base/DOMAIN_MODEL.md` § "agent_session" aggregate — confirms the
  `ACTIVE → AWAITING_APPROVAL → ACTIVE` transition `agent_hitl_flow`
  traverses.
- `.claude/rules/security-patterns.md` § "LLM / Agent layer" — never log
  full prompts; the PRP-41 step MUST log key presence + the chat outcome
  shape only.
- `.claude/rules/test-requirements.md` — every new step ⇒ test in
  `app/features/demo/tests/test_pipeline.py`; new endpoint touch ⇒ no
  changes here, all ops/agents endpoints already exist.
- `.claude/rules/shadcn-ui.md` — Card, Button, Badge already imported; the
  KPI strip + Inspect-Artifacts panel reuse existing primitives.
- `.claude/rules/output-formatting.md` — step card status indicators stay
  consistent with the existing emoji set.

**External (load via `mcp__claude_ai_contex7__`):**

- React Router 7 deep linking: <https://reactrouter.com/en/main>
  (Inspect-Artifacts panel deep links).
- PydanticAI tool-call lifecycle: <https://ai.pydantic.dev/tools/>
  (HITL approval flow understanding).
- FastAPI WebSocket disconnect handling: <https://fastapi.tiangolo.com/advanced/websockets/>
  (Stop button release semantics).
- TanStack Query mutations: <https://tanstack.com/query/latest/docs/framework/react/guides/mutations>
  (one-click Approve + Stop wiring).

**Prior-art PRPs (read for pattern):**

- `PRPs/PRP-38-showcase-data-modeling-lifecycle.md` — PRP-41 prerequisite;
  the phase accordion + `PHASE_DEFS` lockstep invariant.
- `PRPs/PRP-39-showcase-decision-portfolio-lifecycle.md` — PRP-41
  prerequisite; the decision/portfolio surfaces the Inspect-Artifacts
  panel deep-links into.
- `PRPs/PRP-40-showcase-planning-knowledge-lifecycle.md` — PRP-41
  prerequisite; the saved scenarios + indexed RAG corpus the KPI strip
  counts.
- `PRPs/PRP-27-scenario-simulation-d-agent-integration.md` (or the slice
  that introduced `save_scenario`) — confirms the HITL gate semantics
  PRP-41 consumes.
- `PRPs/ai_docs/prp-40-contract-probe-report.md` (predecessor) — pattern
  for PRP-41's Task 1 contract probe.

## OTHER CONSIDERATIONS:

### Hard constraints (from the parent INITIAL — repeated for PRP authoring convenience)

- **No new tables.** Persistent run history goes to `localStorage` in the
  browser, keyed `forecastlab.showcase.runs.v1`, capped 5 entries.
- **Vertical-slice rule.** `app/features/demo/` does NOT import from
  `app/features/agents/` or `app/features/ops/`. All calls via
  `httpx.ASGITransport` (the existing `_Client` helper).
- **WebSocket contract additive only.** New Optional keys on the free-form
  `StepEvent.data` payload (`awaiting_approval`, `approval_url`, the KPI
  numeric keys for `ops_snapshot`). Existing keys unchanged.
- **Phase table lockstep.** Backend `_phase_table()` + frontend `PHASE_DEFS`
  ship in this PRP together; `test_phase_table_stable` enforces.
- **Skip gracefully on missing LLM key.** `agent_hitl_flow` MUST call
  `_llm_key_present()` first and emit `skip` when False — same pattern as
  the existing `step_agent`.
- **Do NOT widen the agent's mutation surface.** `save_scenario` already
  lives in `agent_require_approval`. PRP-41 verifies this in the contract
  probe and does NOT modify the list.

### Risks specific to PRP-41 (from the umbrella's risk register)

| # | Risk | Where it bites | Mitigation |
|---|------|----------------|------------|
| R5 (from parent) | Agent HITL approval blocks until `/agents/sessions/{id}/approve` returns; need stuck-on-approval > 30 s detection + one-click approve UI. | `agent_hitl_flow` step | Pipeline auto-approves after a 3 s display delay; frontend ALSO surfaces a one-click Approve button so a human can pre-empt. Hard fallback: 90 s timeout → emit `skip` with detail `"approval timed out — pipeline continued"` and continue (the `cleanup` step still closes the session). |
| R6 (from parent) | `frontend/.env` LAN-IP regression breaks `/demo/stream` from a localhost browser. | All PRPs' dogfood — PRP-41 owns the walkthrough doc | `docs/user-guide/showcase-walkthrough.md` calls out the gotcha explicitly with the fix (`VITE_API_BASE_URL=http://localhost:8123`). |
| R7 (from parent) | HANDOFF accuracy — `pnpm tsc --noEmit -p tsconfig.app.json` (NOT bare `tsc`). | PRP-41 validation | Required. Never trust prior HANDOFF green checks. |
| R8 (from parent) | `/demo/stream` allows one pipeline at a time. PRP-41 ships the Stop button that gives the visitor an explicit way to free the lock. | All PRPs' runtime | Stop calls `disconnect()`; backend releases the `asyncio.Lock` on `WebSocketDisconnect`. Verify in contract probe + integration test. |
| R9 (from parent) | Edit/Write CRLF noise — Edit/Write on CRLF files produces whole-file diffs. | All PRPs' commits | Confine edits to the smallest possible diff; check `git diff --stat` before committing. |
| R16 | KPI strip pulls from `step.data` keys that earlier PRPs may not have shipped (e.g., `chunks_indexed`). | KPI strip render | Each tile renders `—` when its source key is missing; no errors thrown. Tests cover the missing-key path. |
| R17 | Inspect-Artifacts panel deep-links use ids from `step.data` payloads that may be absent (e.g., `batch_id` if the batch step was skipped). | Inspect-Artifacts panel | Cards with missing ids render disabled + a tooltip `"Run with scenario=showcase-rich to populate this page"`. |
| R18 | `localStorage` quota / SSR mismatch — the run-history strip writes during render. | Run-history strip | Read on mount via `useEffect`; write only inside `pipeline_complete` / `error` handlers; wrap reads in a `try` for invalid JSON. |

### Performance budget

- PRP-41 adds ≤ 30 s to the `showcase-rich` end-to-end budget (agent flow
  ~10 s + ops snapshot ~3 s + a 3 s approval display delay; under typical
  conditions the auto-approve fires immediately and approval is ~1 s).
- Total `showcase-rich` budget stays ≤ 240 s.
- Per-step timeout: 120 s (`_HTTP_TIMEOUT`, unchanged).
- Approval hard fallback: 90 s.

### Validation plan (PRP-41 specific)

**Task 1 — Contract Probe** (mandatory per epic):

- Verify on `dev` post-PRP-40:
  - `POST /agents/sessions` request/response shape (`agent_type`, `session_id`).
  - `POST /agents/sessions/{id}/chat` response shape — confirm the field
    that signals `approval_required` (event list in response body).
  - `POST /agents/sessions/{id}/approve` request body (`action_id`,
    `approved`) + response shape.
  - `save_scenario` is in `agent_require_approval` per
    `app/core/config.py:184`.
  - `GET /ops/summary` response keys for `stale_aliases`, `aliases`, `runs`.
  - `GET /ops/retraining-candidates` response keys for `candidates`.
  - `GET /ops/model-health` request param name (`grain`) + response keys
    for the degrading-first sorted list.
  - `WebSocketDisconnect` releases the `asyncio.Lock` in
    `app/features/demo/routes.py`.
- Output to `PRPs/ai_docs/prp-41-contract-probe-report.md`.
- Stop and patch the PRP's wording if any cited contract is absent or drifted.

**Backend tests (new — under `app/features/demo/tests/test_pipeline.py`):**

- `test_agent_hitl_flow_step` — asserts the approval round-trip captures
  `approval_decision == "approved"` and embeds `session_id` + `tokens_used`
  + `tool_calls_count` in `step.data`.
- `test_agent_hitl_flow_step_skips_without_key` — `_llm_key_present()`
  returns False → step emits `skip`, no session opened.
- `test_agent_hitl_flow_step_timeout` — when approval never returns within
  90 s (mocked), emit `skip` with the timeout detail, no exception raised.
- `test_ops_snapshot_step` — asserts the KPI payload shape
  (5 numeric keys, all ints, all ≥ 0).
- `test_phase_table_stable` — extend the fixture with the new
  `(phase, step)` tuples; legacy `("agent", "agent")` row replaced with
  `("agents", "agent_hitl_flow")`; `("ops", "ops_snapshot")` appended.

**Frontend tests (new — under `frontend/src/components/demo/`):**

- `PHASE_DEFS.test.ts` — extend fixture with `agents` + `ops` phases.
- `ShowcaseKpiStrip.test.tsx` — populates from `step.data` payloads; renders
  `—` for missing keys; hidden until first `step_complete`.
- `InspectArtifactsPanel.test.tsx` — renders 10 deep-link cards on
  `pipeline_complete`; missing ids disable the corresponding card with the
  expected tooltip.
- `RunHistoryStrip.test.tsx` — localStorage round-trip (write on
  `pipeline_complete`, FIFO cap at 5); Replay re-fills the controls.
- `use-demo-pipeline.test.ts::stop` — Stop closes the WebSocket; phase
  returns to `idle` within 5 s; subsequent `start()` works.
- `demo-step-card.test.tsx` — `awaiting_approval=true` renders the Approve
  button; click triggers the approve endpoint; > 30 s pending renders the
  warning callout.

**Integration test (under `tests/`):**

- `tests/test_e2e_demo.py::test_showcase_rich_full_epic` — runs the full
  pipeline on `scenario=showcase-rich`, asserts:
  - All four PRPs' phases complete in order.
  - `agent_hitl_flow` either passes or skips gracefully.
  - `ops_snapshot` payload has the expected 5 KPI keys.
  - Wall-clock ≤ 240 s (soft warn at 240, hard fail at 300).

**Manual dogfood checklist (full 10-line dogfood from the umbrella):**

After running `/showcase` end-to-end on a fresh DB with
`scenario=showcase-rich`:

- [ ] `/visualize/forecast` — Train card available, V1/V2 toggle reachable,
      picker pre-fills the showcase store/product.
- [ ] `/visualize/backtest` — RMSE tile populated, horizon-bucket card
      renders per-bucket metrics.
- [ ] `/visualize/batch` — Batch preset + matrix picker reachable; the
      just-created batch appears in the list with completed items.
- [ ] `/visualize/planner` — saved scenario plan visible in library;
      multi-plan compare ranks two plans.
- [ ] `/explorer/runs` — ≥ 4 runs registered.
- [ ] `/explorer/runs/{v2_prophet_run_id}` — Feature Frame panel renders
      V=2 badge + populated coefs.
- [ ] `/explorer/runs/compare?a={v1}&b={v2}` — champion-compat badge reads
      "Not comparable".
- [ ] `/ops` — stale-alias card shows the `feature_frame_version_mismatch`
      reason; Model Health table populated.
- [ ] `/knowledge` — the 5 indexed user-guide docs visible; semantic search
      returns hits.
- [ ] `/chat` — agent session with the just-approved `save_scenario` tool
      call visible in the transcript.
- [ ] KPI strip on `/showcase` reads sensible numbers > 0 for all 5 tiles.
- [ ] Inspect-Artifacts panel renders 10 cards; every card navigates to a
      page with populated state.
- [ ] Run-history strip persists the run after refresh; Replay re-fills the
      controls.
- [ ] Stop button cancels a fresh run within 5 s; a subsequent Run works.
- [ ] `pnpm tsc --noEmit -p tsconfig.app.json` clean (do NOT trust prior
      HANDOFF green checks).
- [ ] `docs/user-guide/showcase-walkthrough.md` has no remaining "planned"
      markers for in-scope behaviour.

### Stop-and-ask gates (PRP-41)

- Before modifying `agent_require_approval` in `app/core/config.py` — STOP.
  PRP-41 must consume the existing `save_scenario` entry, not add new ones.
- Before any change to `app/features/demo/schemas.py:StepEvent` field that
  is NOT Optional + additive — STOP.
- Before adding any cross-slice import in `app/features/demo/` — STOP;
  drive `/agents/*` and `/ops/*` over the existing ASGI client.
- Before a `feat!:` (breaking) commit — STOP. PRP-41 is purely additive.
- Before cutting `dev → main` or pushing any tag — STOP (release-please
  owns tagging).

### Future issue title (suggested)

`feat(api,ui): showcase pipeline — agent + ops + final polish`

## PRP GENERATION COMMAND

Generate the PRP from this INITIAL with:

```
/base_prp:prp-create PRPs/INITIAL/INITIAL-showcase-41-agent-ops-polish.md
```

**Position in the epic:** **FOURTH and FINAL** of four PRPs in the
`/showcase` upgrade.
**Prerequisites:** PRP-39 AND PRP-40 must both be merged first. This slice
depends on:
- PRP-39 — the registry decision surfaces (stale-alias chip, safer-Promote
  dialog) PRP-41's Inspect-Artifacts panel deep-links into.
- PRP-40 — the saved scenarios and indexed RAG corpus PRP-41's KPI strip and
  Inspect-Artifacts panel count and link to.
