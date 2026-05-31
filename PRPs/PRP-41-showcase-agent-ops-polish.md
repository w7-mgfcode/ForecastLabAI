name: "PRP-41 — Showcase Agent HITL + Ops + Final Polish"
description: |
  Fourth and FINAL slice of the four-PRP `/showcase` upgrade epic (PRP-38..41).
  PRP-41 closes the epic: ships the last two pipeline phases — an `agents`
  phase that exercises the experiment agent's HITL approval round-trip
  (`save_scenario` is already in `agent_require_approval`), and an `ops`
  phase that snapshots `/ops/summary` + `/ops/retraining-candidates` +
  `/ops/model-health` into a small KPI grid in its step card — plus
  cross-cutting `/showcase` UI polish: a top KPI strip, an Inspect-Artifacts
  post-run panel, a localStorage-backed run history strip, a Stop button
  that releases the pipeline lock, a one-click Approve button on the HITL
  step card, and a `DemoPhasePanel` `onValueChange` fix that closes
  issue #311.

  > **PREREQUISITES — PRP-38 + PRP-39 + PRP-40 merged AND issue #312
  > merged.** All cited surfaces (HITL approval, `/ops/*` endpoints,
  > `scenario_simulate_and_save` / `multi_plan_compare` / `rag_*` step
  > data payloads, phase accordion, scenario picker, `demo-production`
  > champion alias, idempotent `POST /seeder/phase2-enrichment`) are on
  > `dev`. The PRP-41 implementation MUST NOT re-implement them — only
  > consume.
  >
  > **Task 1 (Contract Probe) is the gate.** Some keys called out in
  > INITIAL-41's body draft against current dev: e.g. the
  > `ModelHealthEntry` drift field is `drift_direction` (NOT
  > `drift_verdict`), the approval body field is `action_id` (NOT
  > `tool_call_id`), the chat response surfaces approval via
  > `pending_approval: bool` + `pending_action: PendingAction` (NOT an
  > `approval_required` event — that event only fires on the WS
  > streaming `/agents/stream` path). The probe report MUST verify every
  > cited key field-for-field; STOP and patch the PRP if any cite drifts.

## Purpose

A one-pass implementation contract for an AI agent (or human) with access
to the codebase but no prior session context. Ship the agents + ops
phases of the `/showcase` rich demo upgrade PLUS the cross-cutting UI
polish: two new pipeline steps across two new phases, additive
`StepEvent.data` keys, five new frontend components, a Stop button, a
Phase-accordion bug-fix that closes issue #311, walkthrough doc cleanup,
and the RUNBOOKS extension — WITHOUT regressing PRP-38/39/40's
`showcase_rich` flow or violating the demo slice's "stateless orchestrator
over `httpx.ASGITransport`" invariant.

## Core Principles

1. **Backend contracts are read-only.** Every endpoint PRP-41 drives
   (`POST /agents/sessions`, `POST /agents/sessions/{id}/chat`,
   `POST /agents/sessions/{id}/approve`,
   `DELETE /agents/sessions/{id}`, `GET /ops/summary`,
   `GET /ops/retraining-candidates`, `GET /ops/model-health`) already
   exists on `dev`. Task 1's contract probe
   (`PRPs/ai_docs/prp-41-contract-probe-report.md`) verifies field-for-
   field presence. PRP-41 adds **ZERO** new backend endpoints and
   **ZERO** new schemas — every new payload key rides inside
   `StepEvent.data: dict[str, Any]`.
2. **Vertical-slice rule (load-bearing).** `app/features/demo/` MUST NOT
   import from `app/features/{agents,ops,registry,scenarios,rag}/`. Both
   new steps drive their respective slices over `httpx.ASGITransport`
   exactly like PRP-38/39/40's existing steps. Grep guard:
   `git grep -nE "from app\.features\.(agents|ops|registry|scenarios|rag)" app/features/demo/` MUST be empty.
3. **WebSocket contract is ADDITIVE ONLY.** `StepEvent.data` is
   `dict[str, Any]` — the new payloads add string / int / float /
   bool keys, no schema bump. The `phase_name` / `phase_index` /
   `phase_total` fields PRP-38 added stay Optional + Nullable.
   PRP-41 adds two NEW phase id VALUES (`"agents"` and `"ops"`), NOT
   new `event_type` values.
4. **Phase table is a stability invariant — RELATIVE ANCHORS only.**
   Backend `_phase_table()` REPLACES the legacy `(PHASE_AGENT, "agent",
   step_agent)` row with `(PHASE_AGENTS, "agent_hitl_flow",
   step_agent_hitl_flow)` AT THE SAME POSITION (after `verify`, before
   `cleanup`); appends `(PHASE_OPS, "ops_snapshot", step_ops_snapshot)`
   IMMEDIATELY AFTER `agents`, BEFORE the existing `cleanup` row. NEVER
   "at row index N". Frontend `PHASE_DEFS.ts` mirrors in lockstep —
   `PHASE_DEFS.test.ts` is the contract gate.
5. **No new tables, no Alembic migrations.** Persistent run history
   goes to `localStorage` in the browser, keyed
   `forecastlab.showcase.runs.v1`, capped at 5 entries.
6. **Skip gracefully on missing LLM key.** `step_agent_hitl_flow` MUST
   call `_llm_key_present()` first and emit `skip` when False — exact
   same pattern as the existing `step_agent`. Hard fallback: if approval
   never returns within 90 s, emit `skip` with detail
   `"approval timed out — pipeline continued"` and continue.
7. **Do NOT widen the agent's mutation surface.** `save_scenario`
   already lives in `agent_require_approval` per `app/core/config.py:184`.
   Task 1 verifies this; PRP-41 does NOT modify the list.
8. **Pre-1.0 contract additivity.** Every new field is Optional / dict-
   keyed; no `feat!:` / breaking commit. PRP-41 is purely additive.
9. **shadcn workflow.** PRP-41 adds NO new shadcn primitives (Card,
   Button, Badge, Accordion already imported by PRP-38/39/40). If a
   primitive turns out to be unavoidable, surface as a stop-and-ask
   gate and route through the `shadcn` skill per `.claude/rules/shadcn-ui.md`.

---

## Goal

Deliver, on branch `feat/showcase-41-agent-ops-polish`, the agent HITL +
ops snapshot + final polish slice of the `/showcase` rich demo upgrade so
a visitor running the `showcase_rich` scenario sees:

- A new **`agents` phase** (replacing the legacy single-step `agent`
  phase) whose one step `agent_hitl_flow` opens an experiment session,
  prompts it to save a scenario plan via the gated `save_scenario` tool,
  surfaces an `awaiting_approval=true` flag in `step.data` so the UI
  shows a one-click Approve button, then auto-approves after a 3 s
  display delay if the visitor doesn't click first.
- A new **`ops` phase** whose one step `ops_snapshot` fetches the three
  `/ops/*` endpoints and embeds a 5-key KPI summary in `step.data` so
  the step card renders a small KPI mini-grid without any extra fetch.
- A **top KPI strip** with 5 populated tiles (runs registered, aliases
  live, batch items completed, scenario plans saved, RAG chunks indexed)
  — counts fold in from earlier-phase `step.data` payloads with no
  extra fetches.
- An **Inspect-Artifacts panel** rendered on `pipeline_complete` — a
  grid of 10 deep-link cards into every dashboard surface this run
  populated.
- A **run history strip** above the controls card showing the last 5
  pipeline runs (timestamp · scenario · duration · status · Replay),
  persisted in `localStorage` (no new tables).
- A **Stop button** visible during `phase === 'running'` that closes the
  WebSocket client-side so the visitor can free the module-level
  `asyncio.Lock` without waiting for a stuck step.
- A **phase accordion** that no longer pins to `data` after
  `pipeline_complete` — clicking any phase header expands it (closes
  issue #311).
- The walkthrough doc (`docs/user-guide/showcase-walkthrough.md`) with
  **zero remaining "planned" markers** for behaviour the epic now
  delivers.

## Why

Without PRP-41, the `/showcase` page demonstrates data + modeling +
decision + portfolio + planning + knowledge (PRP-38..40) but stops short
of the operator-grade lifecycle. The **agent HITL gate** is the security
boundary that gates every mutating tool call in production; without
showcasing it, a visitor has no proof the demo respects the gate. The
**ops snapshot** is the operator's morning-coffee dashboard summary;
without it, the demo doesn't close the loop "trained → registered →
aliased → operationally watched". The **post-run UX polish** (KPI strip,
Inspect-Artifacts panel, run-history strip, Stop button) is what turns
the rich timeline into a true control-center experience — a first-time
visitor lands, runs `showcase_rich`, and within ≤ 240 s sees a fully
populated set of cross-page deep-links into every dashboard surface the
run touched.

This is the **fourth and final** slice of the epic. After PRP-41 lands,
the `/showcase` upgrade is complete; the walkthrough doc has no more
"planned" markers for in-scope behaviour; issue #311 closes; the
showcase serves both as the first-time-visitor demo and the operator's
regression-confidence smoke test.

## What

### User-visible behaviour

- `/showcase` on `showcase_rich` runs **two additional steps** grouped
  under two new phases — `agents` (1 step, replacing the legacy `agent`
  phase) and `ops` (1 step, NEW). Total step count on `showcase_rich`:
  **23 → 24** (PRP-41 replaces one row + appends one).
- The `agents` phase emits `agent_hitl_flow`. The step card shows a
  one-row mini summary (`session={id[:8]}... tokens={N}
  tool_calls={M} approved={true|false}`). When `step.data.awaiting_approval
  === true` and `step.status === 'running'`, the card renders a primary
  **Approve** button; clicking it POSTs to
  `/agents/sessions/{session_id}/approve` and resolves the step within
  3 s. After 30 s pending, the card surfaces an inline warning callout
  *"Still waiting for approval — auto-approve in {N}s"*.
- The `ops` phase emits `ops_snapshot`. The step card shows a small KPI
  mini-grid (5 number tiles in a `grid grid-cols-5 gap-2 text-xs`
  layout) populated from `step.data`.
- A **top KPI strip** with 5 populated tiles renders at the top of
  `/showcase`, hidden until the first `step_complete` event arrives.
- An **Inspect-Artifacts panel** renders below the phase accordion on
  `phase === 'done'`: a `grid grid-cols-2 lg:grid-cols-5 gap-4` of 10
  deep-link cards. Cards with missing ids render disabled with a
  tooltip.
- A **run history strip** above the controls card shows the last 5
  runs from `localStorage`; Replay re-fills the controls card with the
  saved scenario + checkboxes.
- A **Stop button** is visible in the controls card during
  `phase === 'running'`; click → page returns to `idle` within 5 s.
- The **phase accordion** stays controlled by `runningPhase` during
  the run, but post-`pipeline_complete` any phase header click toggles
  the open panel correctly (issue #311 closed).
- When `_llm_key_present()` returns False, the `agents` phase emits
  one `skip` event with the same wording as the legacy `step_agent`;
  pipeline still goes green.
- When the approve round-trip never completes within 90 s (network
  hang, agent stuck), the step emits `skip` with detail
  `"approval timed out — pipeline continued"`; `cleanup` still closes
  the session via `DELETE /agents/sessions/{id}`.

### Technical requirements

- **Backend (`app/features/demo/pipeline.py`)** — two new step functions
  (`step_agent_hitl_flow`, `step_ops_snapshot`); two new phase constants
  (`PHASE_AGENTS = "agents"`, `PHASE_OPS = "ops"`); `_phase_table()`
  REPLACES the legacy `(PHASE_AGENT, "agent", step_agent)` row and
  APPENDS the new ops row; `DemoContext` gains two additive Optional
  fields (`approval_action_id: str | None`, `agent_approval_decision: str | None`).
- **Backend (`app/features/demo/tests/test_pipeline.py`)** — 7 new
  tests (happy + skip-no-key + skip-timeout + approve-409-absorbed for
  HITL; happy + empty-payload-warn for ops; lockstep `_phase_table`
  count flip 23 → 24).
- **Frontend (`frontend/src/components/demo/PHASE_DEFS.ts` +
  `PHASE_DEFS.test.ts`)** — rename existing `agent` phase to `agents`;
  swap the `'agent'` step id to `'agent_hitl_flow'`; append `ops` phase
  + `ops_snapshot` step row; tuple list flips 23 → 24.
- **Frontend (`frontend/src/components/demo/DemoPhasePanel.tsx`)** —
  add `onValueChange` handler with local state (issue #311 / D10).
- **Frontend (`frontend/src/components/demo/demo-step-card.tsx`)** —
  two new mini-summary helpers (`HitlFlowSummary`,
  `OpsSnapshotMiniGrid`); a conditional Approve button when
  `step.data.awaiting_approval === true` and `step.status === 'running'`.
- **Frontend (`frontend/src/components/demo/ShowcaseKpiStrip.tsx`)** —
  NEW. 5-tile strip rendered above the controls card.
- **Frontend (`frontend/src/components/demo/InspectArtifactsPanel.tsx`)**
  — NEW. 10-card deep-link grid rendered post-`pipeline_complete`.
- **Frontend (`frontend/src/components/demo/RunHistoryStrip.tsx`)** —
  NEW. localStorage-backed strip, FIFO cap 5.
- **Frontend (`frontend/src/hooks/use-demo-pipeline.ts`)** — add `stop`
  callback exposing the existing `disconnect` from `useWebSocket`.
- **Frontend (`frontend/src/pages/showcase.tsx`)** — wire the four new
  components + Stop button + extended `resolveInspectHref` switch (2
  new cases: `agent_hitl_flow`, `ops_snapshot`).
- **Documentation (`docs/_base/RUNBOOKS.md`)** — extend the "Showcase
  page pipeline fails at step X" section with the 5 new failure modes.
- **Documentation (`docs/user-guide/showcase-walkthrough.md`)** —
  remove every "planned" marker for in-scope behaviour, add screenshot
  placeholders for the new phase / KPI strip / Inspect-Artifacts panel.

### Success Criteria (verifies INITIAL-41 D1..D10)

- [ ] **D1** — After a `showcase_rich` run, `/showcase` shows a top
      KPI strip with 5 populated tiles. Verified by **manual dogfood**
      + `ShowcaseKpiStrip.test.tsx`.
- [ ] **D2** — After `pipeline_complete`, the Inspect-Artifacts panel
      renders all 10 deep-link cards. Verified by **manual dogfood** +
      `InspectArtifactsPanel.test.tsx`.
- [ ] **D3** — The `agent_hitl_flow` step card surfaces a one-click
      Approve button when `awaiting_approval=true`; clicking advances
      the step within 3 s. Verified by **manual dogfood** + extension
      to `demo-step-card.test.tsx`.
- [ ] **D4** — Stop button cancels an in-flight run; the page returns
      to `idle` within 5 s of click. Verified by **manual dogfood** +
      `use-demo-pipeline.test.ts::stop` case.
- [ ] **D5** — localStorage holds the last 5 run summaries; the Replay
      button re-fills the controls. Verified by **manual dogfood** +
      `RunHistoryStrip.test.tsx`.
- [ ] **D6** — `docs/user-guide/showcase-walkthrough.md` has no
      remaining "planned" markers for behaviour this epic delivered.
      Verified by `grep -nE 'planned|TBD|TODO' docs/user-guide/showcase-walkthrough.md`
      returning no in-scope hits.
- [ ] **D7** — `showcase-rich` end-to-end (PRP-38 + PRP-39 + PRP-40 +
      PRP-41 phases) still ≤ 240 s on the dev host. Verified by
      `pytest -m integration` wall-clock assertion.
- [ ] **D8** — Backend `_phase_table()` and frontend `PHASE_DEFS` still
      match (both updated in lockstep). Verified by
      `test_phase_table_showcase_rich_emits_24_steps` (backend) +
      `PHASE_DEFS.test.ts` (frontend) — both swap the legacy
      `('agent','agent')` tuple for `('agents','agent_hitl_flow')`
      and append `('ops','ops_snapshot')`.
- [ ] **D9** — All five validation gates green (`ruff` /
      `ruff format` / `mypy --strict` / `pyright --strict` / `pytest`).
      Verified by CI.
- [ ] **D10** — Phase accordion is no longer pinned to `data` after
      `pipeline_complete`; clicking any later phase header opens it
      (closes issue #311). Verified by **manual dogfood** + a new
      `DemoPhasePanel.test.tsx` case asserting `onValueChange` toggles
      the open panel post-run.

### Out of Scope (explicit — do NOT implement in PRP-41)

- **Persistent server-side run history** — would force a new table
  (single-host vision violation). PRP-41 uses `localStorage` exclusively.
- **Shareable replay URLs** — out of scope per the parent epic's
  "NOT Option C" call.
- **A guided-tour overlay** — deferred indefinitely.
- **Widening `agent_require_approval`** — `save_scenario` is already
  in the list (`app/core/config.py:184`). PRP-41 verifies in the
  contract probe and does NOT modify.
- **New `/ops/*` query params** — `GET /ops/model-health` takes only
  `?limit=` (no `grain` param). PRP-41 consumes the existing signature
  exactly.
- **New shadcn primitives** — Card / Badge / Button / Accordion /
  Checkbox cover every use case PRP-41 introduces.
- **PRP-38/39/40 territory** — phase accordion + scenario picker +
  V1/V2 modeling (PRP-38), champion-compat compare + stale-alias
  trigger + safer-Promote walk-through + batch preset (PRP-39),
  scenario simulate/save/compare + RAG indexing + embedding-provider
  probe (PRP-40). PRP-41 CONSUMES their `step.data` payloads (for the
  KPI strip + Inspect-Artifacts panel deep-links) but does NOT modify
  any of those steps.

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ — Include these in your context window
- docfile: PRPs/ai_docs/prp-41-contract-probe-report.md
  why: Task 1 output — field-for-field verification of every cited
       contract on dev at b3ba1f4. Documents R5 / R6 / R7 / R8 / R16-R18
       resolutions and any drift the implementer's first probe finds.

- docfile: PRPs/ai_docs/prp-40-contract-probe-report.md
  why: Pattern for the contract-probe report shape; PRP-41 mirrors it.

- docfile: PRPs/ai_docs/prp-39-contract-probe-report.md
  why: Same pattern, slightly different shape — second exemplar.

- file: PRPs/PRP-40-showcase-planning-knowledge-lifecycle.md
  why: Predecessor PRP. PRP-41 sits on top of PRP-40's planning +
       knowledge phases. The `scenario_id` / `winner_scenario_id` /
       `total_chunks` / `curated_hits` keys the KPI strip counts come
       from PRP-40's `step_scenario_simulate_and_save`,
       `step_multi_plan_compare`, `step_rag_index_subset`.

- file: PRPs/PRP-39-showcase-decision-portfolio-lifecycle.md
  why: Predecessor PRP. The `completed_items` key the KPI strip counts
       comes from PRP-39's `step_batch_preset`. The Inspect-Artifacts
       panel deep-links into stale-alias chip / safer-Promote dialog
       PRP-39 shipped.

- file: PRPs/PRP-38-showcase-data-modeling-lifecycle.md
  why: Predecessor PRP. The phase accordion + scenario picker +
       `demo-production` alias the HITL step consumes.

- file: PRPs/INITIAL/INITIAL-showcase-41-agent-ops-polish.md
  why: Source-of-truth INITIAL (588 lines, already patched). Acceptance
       criteria D1..D10, manual dogfood checklist, R5-R18 risk
       register live here.

- file: PRPs/INITIAL/INITIAL-showcase-rich-demo-control-center.md
  why: Parent INITIAL — the four-PRP epic vision.

# Pattern files (read for shape)
- file: app/features/demo/pipeline.py
  why: |
    Locate by symbol — PRP-39/40 shifted file lines substantially:
    - ``_HTTP_TIMEOUT`` (constant): the 120 s budget the new steps share.
    - ``_StepError``: RFC 7807-aware typed failure the new steps raise.
    - ``_Client.request()``: in-process ASGI transport — returns
      ``{"_raw": body}`` for non-dict 2xx bodies; raises ``_StepError``
      on non-2xx. ``GET /ops/*`` returns dict bodies, so `_raw` does
      NOT come into play for PRP-41 — but the implementer should
      verify in Task 1.
    - ``_llm_key_present()``: skip-gracefully gate, mirror exactly.
    - ``DemoContext`` dataclass: the accumulator the new steps thread
      `approval_action_id` / `agent_approval_decision` through.
    - ``step_agent``: existing single-turn chat step. PRP-41's
      ``step_agent_hitl_flow`` REPLACES this row but reuses the session
      open / chat call patterns.
    - ``step_cleanup``: the session-close pattern. Already closes
      ``ctx.session_id`` via DELETE — PRP-41 changes nothing here.
    - ``step_register``: multi-call multi-PATCH pattern; the closest
      precedent for ``step_agent_hitl_flow``'s multi-call shape.
    - ``step_batch_preset``: the source of ``step.data.completed_items``.
    - ``step_rag_index_subset``: the source of ``step.data.total_chunks``
      + ``step.data.curated_hits``.
    - ``step_multi_plan_compare``: the source of
      ``step.data.winner_scenario_id`` + ``step.data.ranked``.
    - ``step_scenario_simulate_and_save``: the source of
      ``step.data.scenario_id`` (the saved plan id).
    - ``_phase_table()``: the relative-anchor table — REPLACE the
      ``(PHASE_AGENT, "agent", step_agent)`` row with
      ``(PHASE_AGENTS, "agent_hitl_flow", step_agent_hitl_flow)`` and
      INSERT ``(PHASE_OPS, "ops_snapshot", step_ops_snapshot)``
      IMMEDIATELY AFTER the agents row, BEFORE the cleanup row.
    - ``PHASE_*`` constants block: append ``PHASE_AGENTS = "agents"``
      and ``PHASE_OPS = "ops"``. ``PHASE_AGENT`` stays (legacy demo_
      minimal / sparse branches still use the singular "agent" phase
      with the legacy `step_agent`; **OR** rewrite both branches to
      use the new phase id — pick ONE answer in Task 1).
    - ``run_pipeline``: iterator agnostic to phase ids — no change.

- file: app/features/demo/routes.py
  why: |
    - The ``/demo/stream`` WS handler at lines 57–85 catches
      ``WebSocketDisconnect`` and returns; ``service.stream_pipeline``
      wraps the ``run_pipeline`` generator in ``async with
      _pipeline_lock``, so the lock releases on disconnect. PRP-41's
      Stop button relies on this — Task 1 verifies it still holds.

- file: app/features/demo/service.py
  why: |
    - Lines 18–19: ``_pipeline_lock = asyncio.Lock()`` (module-level).
    - Lines 39–43: ``async with _pipeline_lock`` wrap. Single-flight
      guard. The Stop button releases by triggering the disconnect.

- file: app/features/agents/schemas.py
  why: |
    - Lines 27–42 — ``SessionCreateRequest`` (agent_type: Literal,
      initial_context: dict | None).
    - Lines 45–68 — ``SessionResponse`` (session_id, agent_type,
      status, total_tokens_used, tool_calls_count, last_activity,
      expires_at, created_at).
    - Lines 108–124 — ``ChatRequest`` (message: str, stream: bool=False).
    - Lines 145–162 — ``ChatResponse`` (session_id, message,
      tool_calls: list[ToolCallResult], pending_approval: bool,
      pending_action: PendingAction | None, tokens_used: int).
    - Lines 170–189 — ``PendingAction`` (action_id, action_type,
      description, arguments, created_at, expires_at).
    - Lines 192–205 — ``ApprovalRequest`` (action_id: str,
      approved: bool, reason: str | None). **Field name is
      ``action_id``, NOT ``tool_call_id`` — INITIAL-41 §480 wording
      was loose; Task 1 confirms.**
    - Lines 208–221 — ``ApprovalResponse`` (action_id, approved,
      result: Any | None, status: Literal["executed","rejected","expired"]).

- file: app/features/agents/routes.py
  why: |
    - Lines 43–77 — ``POST /agents/sessions`` (returns 201, SessionResponse).
    - Lines 109–150 — ``POST /agents/sessions/{session_id}/chat``
      (returns ChatResponse).
    - Lines 152–196 — ``POST /agents/sessions/{session_id}/approve``
      (returns ApprovalResponse).
    - Lines 198–223 — ``DELETE /agents/sessions/{session_id}``
      (returns 204; ``step_cleanup`` already calls this).

- file: app/features/agents/agents/experiment.py
  why: |
    - Line 419 — ``tool_save_scenario`` (the gated tool the HITL step
      triggers via a chat prompt). PRP-41 does NOT call this tool
      directly — it sends a chat message that causes the agent to
      invoke it, which surfaces ``pending_approval=true`` in the chat
      response.

- file: app/features/agents/service.py
  why: |
    - Line 640 — ``approve_action`` (the service method behind
      ``POST /approve``). Approves the pending action; rejects with
      404 if no pending action exists, or 400 if the action_id mismatch.

- file: app/features/ops/schemas.py
  why: |
    - Lines 16–28 — ``StaleReason`` StrEnum (newer_success_run,
      artifact_not_verified, run_not_success,
      feature_frame_version_mismatch).
    - Lines 133–175 — ``AliasHealth`` (alias_name, run_id, is_stale,
      stale_reason, wape, alias_feature_frame_version,
      comparable_run_feature_frame_version).
    - Lines 209–226 — ``OpsSummaryResponse`` (system, jobs, runs,
      aliases: list[AliasHealth], freshness, attention_items,
      generated_at). **NO flat ``stale_aliases`` / ``total_aliases``
      keys — derive from ``aliases`` list (D6 fix).**
    - Lines 234–265 — ``RetrainingCandidate`` (store_id, product_id,
      priority_score, staleness_days, wape, latest_run_id, reason).
    - Lines 267–281 — ``RetrainingCandidatesResponse`` (candidates,
      total_evaluated, generated_at).
    - Line 290 — ``DriftDirection`` Literal
      ``["improving","stable","degrading","unknown"]``. **Field name
      is ``drift_direction``, NOT ``drift_verdict`` — INITIAL-41 body
      drift; Task 1 confirms.**
    - Lines 306–370 — ``ModelHealthEntry`` (store_id, product_id,
      run_count, latest_wape, drift_direction, ...).
    - Lines 372–386 — ``ModelHealthResponse`` (entries: list[ModelHealthEntry],
      total_evaluated, generated_at). **Field name is ``entries``,
      NOT ``health`` or ``items``.**

- file: app/features/ops/routes.py
  why: |
    - Lines 41–43 — ``GET /ops/summary`` (no query params).
    - Lines 70–78 — ``GET /ops/retraining-candidates?limit=1..100``
      (default 20).
    - Lines 110–117 — ``GET /ops/model-health?limit=1..100`` (default
      20). **NO ``grain`` query param exists.**

- file: app/features/ops/tests/test_routes_integration.py
  why: |
    - Lines 68–87 — ``test_summary_resilient_structural`` proves
      ``GET /ops/summary`` returns 200 (never 500) on an empty DB —
      PRP-41's `step_ops_snapshot` can safely assume 200 with zero-
      filled fields.

- file: app/core/config.py
  why: |
    - Line 184 — ``agent_require_approval: list[str] = ["create_alias",
      "archive_run", "save_scenario"]``. Task 1 verifies; PRP-41
      DOES NOT modify.

- file: frontend/src/components/demo/PHASE_DEFS.ts
  why: |
    - Lines 37–64 — ``ALL_STEPS`` (23 rows on `dev`). PRP-41 SWAPS the
      legacy ``{ phase: 'agent', step: 'agent', label: 'Agent chat' }``
      row for ``{ phase: 'agents', step: 'agent_hitl_flow', label:
      'Agent HITL approval' }`` AND INSERTS a new row
      ``{ phase: 'ops', step: 'ops_snapshot', label: 'Ops snapshot' }``
      IMMEDIATELY AFTER it, BEFORE the cleanup row.
    - Lines 66–82 — ``SHOWCASE_RICH_STEP_NAMES`` set. PRP-41 adds
      ``'ops_snapshot'`` (and ``'agent_hitl_flow'`` if it doesn't
      already render on demo_minimal — confirm in Task 1).
    - Lines 94–106 — ``PHASE_LABEL`` Record. PRP-41 swaps ``agent``
      → ``agents`` (and the human label) and adds ``ops``.
    - Lines 109–121 — ``PHASE_ORDER`` const. PRP-41 swaps ``agent``
      → ``agents`` and inserts ``ops`` between ``agents`` and
      ``cleanup``.

- file: frontend/src/components/demo/PHASE_DEFS.test.ts
  why: |
    - Lines 13–28 — ``demo_minimal`` 11-step tuple list. **If the
      demo_minimal phase id rename (agent → agents) is in scope for
      this PRP, the tuple list flips here too.** Task 1 picks the
      design (see Known Gotchas § "demo_minimal phase rename trade-off").
    - Lines 30–60 — ``showcase_rich`` 23-step tuple list. PRP-41
      flips the count to 24 and swaps the legacy ``[ 'agent', 'agent' ]``
      tuple for ``[ 'agents', 'agent_hitl_flow' ]`` and appends
      ``[ 'ops', 'ops_snapshot' ]`` IMMEDIATELY AFTER it.
    - Lines 68–80 — ``PHASE_ORDER`` test (currently 9 phases).
      PRP-41 flips this to 10 — rename ``agent`` → ``agents`` and
      append ``ops``.

- file: frontend/src/components/demo/DemoPhasePanel.tsx
  why: |
    - Lines 42–43 — current ``value`` derivation (running phase OR
      fallback OR phases[0]).
    - Line 46 — current ``<Accordion type="single" collapsible
      value={value} className=...>`` — ** MISSING ``onValueChange``**.
      Issue #311 fix: lift ``value`` to local state seeded from the
      computed value via ``useState`` + ``useEffect``, add
      ``onValueChange={setExpandedPhase}``.

- file: frontend/src/components/demo/demo-step-card.tsx
  why: |
    - Lines 35–111 — mini-summary helper patterns for PRP-38/39/40
      steps. PRP-41 adds two new helpers (``HitlFlowSummary``,
      ``OpsSnapshotMiniGrid``) in the same shape.
    - Lines 356–377 — conditional rendering switch on
      ``step.name``. PRP-41 adds two more conditional blocks.
    - Lines 378–387 — Inspect button render. PRP-41 inserts the new
      Approve button as a peer (rendered when
      ``step.data.awaiting_approval === true`` and
      ``step.status === 'running'``).

- file: frontend/src/components/demo/demo-step-card.test.tsx
  why: |
    - Lines 14–37 — ``makeStep()`` + ``renderCard()`` helper pattern.
    - Lines 39–126 — existing PRP-39 mini-summary tests. PRP-41 adds
      new test cases for the HITL mini-summary + Approve button +
      ops_snapshot KPI grid.

- file: frontend/src/hooks/use-demo-pipeline.ts
  why: |
    - Lines 1–38 — types (DemoStep, DemoSummary, DemoPipelineState).
    - Line 198 — ``disconnectRef = useRef<(() => void) | null>(null)``.
    - Line 208 — ``useWebSocket(DEMO_WS_URL, ...)`` returns
      ``{status, send, disconnect, reconnect}``. PRP-41 captures
      ``disconnect`` for the Stop button.
    - Lines 213–215 — ``disconnectRef.current = disconnect`` effect.
      ADD a sibling ``stop`` callback exposed via the hook return.
    - Lines 247–259 — destructured return; ADD ``stop`` here.

- file: frontend/src/hooks/use-websocket.ts
  why: |
    - Line 158 — returns ``{ status, send, disconnect, reconnect }``.
      ``disconnect()`` cancels reconnect and closes the socket —
      already does what the Stop button needs.

- file: frontend/src/pages/showcase.tsx
  why: |
    - Lines 17–84 — ``resolveInspectHref(step)``. PRP-41 adds two
      new cases (``agent_hitl_flow`` → ``ROUTES.CHAT``,
      ``ops_snapshot`` → ``ROUTES.OPS``).
    - Lines 87–99 — ``useDemoPipeline()`` destructure. ADD ``stop``.
    - Lines 141–278 — Page structure. PRP-41 inserts (in this order):
      1. ``<ShowcaseKpiStrip steps={steps} />`` at the top.
      2. ``<RunHistoryStrip onReplay={(req) => start(req)} />``
         above the controls card.
      3. The Stop button inside the controls card, visible when
         ``phase === 'running'``.
      4. ``<InspectArtifactsPanel steps={steps} summary={summary} />``
         after the phase accordion, visible when ``phase === 'done'``.

- file: frontend/src/lib/constants.ts
  why: |
    - Lines 1–34 — ``ROUTES`` table. ALL 10 deep-link targets the
      Inspect-Artifacts panel needs already exist:
      ``ROUTES.VISUALIZE.FORECAST``, ``BACKTEST``, ``BATCH``,
      ``PLANNER`` / ``ROUTES.EXPLORER.RUNS``, ``RUN_COMPARE``,
      ``RUN_DETAIL`` / ``ROUTES.OPS``, ``KNOWLEDGE``, ``CHAT``.
      Zero new routes required.

- file: frontend/src/pages/admin.tsx
  why: |
    - Lines 431–486 — localStorage versioned-key pattern
      (``forecastlab.seederForm.v1``). PRP-41 mirrors the same
      shape under ``forecastlab.showcase.runs.v1`` for the run-
      history strip.

# Rules
- file: .claude/rules/security-patterns.md
  section: "LLM / Agent layer"
  critical: PRP-41's ``step_agent_hitl_flow`` is a non-agent caller of
            the approval endpoint (the pipeline runs in a server-side
            context). This is fine — the approval endpoint just
            releases the pending action; no human-bypass is granted.
            Never log full prompts / responses; key NAMES only.

- file: .claude/rules/test-requirements.md
  section: "When new tests are required"
  critical: Each new pipeline step ships per-step tests (happy path +
            skip variant + timeout variant for HITL). Every new
            frontend component ships a vitest suite.

- file: .claude/rules/commit-format.md
  section: "Scope allow-list"
  critical: Use ``feat(api,ui): showcase pipeline — agent + ops +
            final polish (#<issue>)``. The ``(api,ui)`` comma-pair is
            allowed.

- file: .claude/rules/shadcn-ui.md
  critical: PRP-41 adds NO new primitives. If one turns out to be
            unavoidable, surface as a stop-and-ask gate.

- file: AGENTS.md
  section: "Safety"
  critical: ``agent_require_approval`` is the load-bearing list.
            PRP-41 verifies ``save_scenario`` is in it; does NOT modify.

# External (load via mcp__claude_ai_contex7__)
- url: https://www.python-httpx.org/async/#calling-into-python-web-apps
  why: ASGITransport pattern — the in-process call path the demo
       slice uses.

- url: https://ai.pydantic.dev/tools/
  why: PydanticAI tool-call lifecycle — understanding how the
       experiment agent's ``tool_save_scenario`` surfaces a pending
       action when ``requires_approval("save_scenario")`` short-
       circuits.

- url: https://fastapi.tiangolo.com/advanced/websockets/
  why: ``WebSocketDisconnect`` exception semantics — Stop button
       releases the pipeline lock by propagating this.

- url: https://tanstack.com/query/latest/docs/framework/react/guides/mutations
  why: Wiring the one-click Approve + Stop buttons.

- url: https://www.radix-ui.com/primitives/docs/components/accordion#controlled
  why: Controlled-vs-uncontrolled Radix Accordion. Issue #311's bug
       is missing ``onValueChange`` on a controlled accordion.
```

### Current Codebase tree (relevant slices)

```bash
app/features/
├── demo/                          # The slice PRP-41 extends
│   ├── pipeline.py                # _phase_table() (~22 steps on showcase_rich),
│   │                              # _HTTP_TIMEOUT, _llm_key_present,
│   │                              # _Client, _StepError, DemoContext,
│   │                              # PHASE_* constants, step_* functions
│   ├── routes.py                  # POST /demo/run + WS /demo/stream
│   │                              # (WebSocketDisconnect releases the lock)
│   ├── schemas.py                 # DemoRunRequest, StepEvent (the WS frame),
│   │                              # StepStatus, EventType
│   ├── service.py                 # asyncio.Lock + stream_pipeline wrapper
│   └── tests/
│       ├── test_pipeline.py       # 51 per-step + lockstep tests
│       ├── test_routes.py         # WS integration
│       └── test_schemas.py
├── agents/                        # READ-ONLY for PRP-41
│   ├── routes.py                  # POST /agents/sessions, /chat, /approve, DELETE
│   ├── schemas.py                 # SessionCreate/Response, ChatRequest/Response,
│   │                              # PendingAction, ApprovalRequest/Response
│   ├── service.py                 # AgentService.approve_action (line 640)
│   └── agents/
│       └── experiment.py          # tool_save_scenario (line 419), gated by
│                                  # requires_approval("save_scenario")
├── ops/                           # READ-ONLY for PRP-41
│   ├── routes.py                  # GET /ops/{summary,retraining-candidates,model-health}
│   ├── schemas.py                 # OpsSummaryResponse, RetrainingCandidatesResponse,
│   │                              # ModelHealthResponse, AliasHealth, ModelHealthEntry,
│   │                              # StaleReason, DriftDirection
│   └── service.py                 # OpsService.get_summary / .get_retraining_candidates /
│                                  # .get_model_health (all 200-safe on empty DB)
└── ...                            # other slices unchanged

frontend/src/
├── components/demo/
│   ├── PHASE_DEFS.ts              # MODIFIED — swap `agent` → `agents`,
│   │                              #             swap `'agent'` step → `'agent_hitl_flow'`,
│   │                              #             append `ops` phase + `ops_snapshot` step
│   ├── PHASE_DEFS.test.ts         # MODIFIED — flip tuple count 23→24, swap rows
│   ├── DemoPhasePanel.tsx         # MODIFIED — add onValueChange handler (#311 / D10)
│   ├── DemoPhasePanel.test.tsx    # CREATED — onValueChange toggle test
│   ├── demo-step-card.tsx        # MODIFIED — HitlFlowSummary + OpsSnapshotMiniGrid
│   │                              #             + conditional Approve button
│   ├── demo-step-card.test.tsx   # MODIFIED — new test cases
│   ├── ShowcaseKpiStrip.tsx       # CREATED — 5-tile KPI strip
│   ├── ShowcaseKpiStrip.test.tsx  # CREATED
│   ├── InspectArtifactsPanel.tsx  # CREATED — 10-card deep-link grid
│   ├── InspectArtifactsPanel.test.tsx  # CREATED
│   ├── RunHistoryStrip.tsx        # CREATED — localStorage FIFO 5
│   └── RunHistoryStrip.test.tsx   # CREATED
├── hooks/
│   ├── use-demo-pipeline.ts       # MODIFIED — add `stop` callback
│   ├── use-demo-pipeline.test.ts  # MODIFIED — add stop case
│   └── use-websocket.ts           # READ-ONLY — disconnect() already exposed
├── pages/
│   └── showcase.tsx               # MODIFIED — wire new components + Stop button
│                                  #             + extended resolveInspectHref
└── lib/constants.ts              # READ-ONLY — every ROUTES key already exists

docs/
├── user-guide/
│   └── showcase-walkthrough.md    # MODIFIED — drop "planned" markers, add
│                                  #             screenshot placeholders
└── _base/
    └── RUNBOOKS.md                # MODIFIED — extend with 5 new failure modes
```

### Desired Codebase tree (additive + modified files)

```bash
# MODIFIED
app/features/demo/pipeline.py
  # +2 step functions (step_agent_hitl_flow, step_ops_snapshot)
  # +2 phase constants (PHASE_AGENTS, PHASE_OPS)
  # +2 DemoContext fields (approval_action_id, agent_approval_decision)
  # _phase_table() row swap + insert (relative anchors)

app/features/demo/tests/test_pipeline.py
  # +7 tests:
  #   test_agent_hitl_flow_happy_path
  #   test_agent_hitl_flow_skips_without_key
  #   test_agent_hitl_flow_skips_on_session_failure
  #   test_agent_hitl_flow_absorbs_double_approve_409
  #   test_agent_hitl_flow_skips_on_approval_timeout
  #   test_ops_snapshot_happy_path
  #   test_ops_snapshot_emits_zero_filled_payload_on_empty_db
  # MODIFIED:
  #   test_phase_table_showcase_rich_adds_… (flips count to 24, swaps row)

frontend/src/components/demo/PHASE_DEFS.ts
  # +1 row, +1 phase id, swap of legacy `agent` phase id → `agents`,
  #  swap of `'agent'` step id → `'agent_hitl_flow'`

frontend/src/components/demo/PHASE_DEFS.test.ts
  # tuple list 23 → 24, agent row swapped, ops row appended,
  #  PHASE_ORDER count 9 → 10

frontend/src/components/demo/DemoPhasePanel.tsx
  # onValueChange handler + local useState (issue #311 fix)

frontend/src/components/demo/demo-step-card.tsx
  # +2 mini-summary helpers (HitlFlowSummary, OpsSnapshotMiniGrid)
  # +1 conditional Approve button block

frontend/src/components/demo/demo-step-card.test.tsx
  # +3 test cases (HITL summary, Approve button, ops mini-grid)

frontend/src/hooks/use-demo-pipeline.ts
  # +1 `stop` useCallback, exposed in return

frontend/src/hooks/use-demo-pipeline.test.ts
  # +1 stop case

frontend/src/pages/showcase.tsx
  # +2 cases in resolveInspectHref
  # render KpiStrip + RunHistoryStrip + InspectArtifactsPanel + Stop button

docs/_base/RUNBOOKS.md
  # +5 failure-mode entries (additive — agent_hitl_flow skipped/timeout,
  #  ops_snapshot empty payload, Stop button used mid-run, KPI strip
  #  missing key fallback)

docs/user-guide/showcase-walkthrough.md
  # remove "planned (PRP-41)" markers; add "Phase: Agents (HITL)" +
  #  "Phase: Ops snapshot" + "KPI strip" + "Inspect-Artifacts panel"
  #  + "Run history strip" + "Stop button" prose with screenshot
  #  placeholders

# CREATED
frontend/src/components/demo/DemoPhasePanel.test.tsx
frontend/src/components/demo/ShowcaseKpiStrip.tsx
frontend/src/components/demo/ShowcaseKpiStrip.test.tsx
frontend/src/components/demo/InspectArtifactsPanel.tsx
frontend/src/components/demo/InspectArtifactsPanel.test.tsx
frontend/src/components/demo/RunHistoryStrip.tsx
frontend/src/components/demo/RunHistoryStrip.test.tsx

PRPs/ai_docs/prp-41-contract-probe-report.md   # Task 1 output
```

### Known Gotchas of our codebase & Library Quirks

```python
# ─────────────────────────────────────────────────────────────────────────
# CRITICAL: Task 1 (Contract Probe) is the gate. Run it FIRST.
# ─────────────────────────────────────────────────────────────────────────
# Verify on `dev` (or current branch tip):
#   - POST /agents/sessions body: {agent_type: "experiment"|"rag_assistant",
#     initial_context: dict|None}. Response: {session_id, agent_type,
#     status, total_tokens_used, tool_calls_count, last_activity,
#     expires_at, created_at}. 201 CREATED on success.
#   - POST /agents/sessions/{id}/chat body: {message: str, stream: bool=False}.
#     Response: ChatResponse {session_id, message, tool_calls: list,
#     pending_approval: bool, pending_action: PendingAction|None,
#     tokens_used: int}. *** PRP-41 reads pending_approval / pending_action
#     directly off the synchronous chat response — NOT a WS event. ***
#   - PendingAction shape: {action_id: str, action_type: str, description: str,
#     arguments: dict, created_at: datetime, expires_at: datetime}.
#   - POST /agents/sessions/{id}/approve body: {action_id: str, approved: bool,
#     reason: str|None}. ** Field name is action_id, NOT tool_call_id. **
#     Response: {action_id, approved, result: Any|None,
#     status: Literal["executed","rejected","expired"]}.
#   - DELETE /agents/sessions/{id} returns 204. ** step_cleanup already
#     handles this; PRP-41 changes NOTHING here. **
#   - GET /ops/summary: no query params. Response: OpsSummaryResponse —
#     fields {system, jobs, runs, aliases: list[AliasHealth], freshness,
#     attention_items, generated_at}. ** No flat stale_aliases /
#     total_aliases / alias_count — derive from aliases list. **
#   - AliasHealth: {alias_name, run_id, is_stale: bool, stale_reason:
#     str|None, wape, ...}. stale_reason values: "newer_success_run",
#     "artifact_not_verified", "run_not_success",
#     "feature_frame_version_mismatch".
#   - GET /ops/retraining-candidates?limit=1..100 (default 20). Response:
#     {candidates: list[RetrainingCandidate], total_evaluated,
#     generated_at}.
#   - GET /ops/model-health?limit=1..100 (default 20). ** No `grain`
#     query param. ** Response: {entries: list[ModelHealthEntry],
#     total_evaluated, generated_at}. ** Field name is `entries`, NOT
#     `health` / `items`. **
#   - ModelHealthEntry.drift_direction: Literal["improving","stable",
#     "degrading","unknown"]. ** Field name is drift_direction, NOT
#     drift_verdict — INITIAL-41 body drift. **
#   - app/core/config.py:184 — agent_require_approval contains
#     "save_scenario". PRP-41 does NOT modify.
#   - WebSocketDisconnect releases _pipeline_lock — confirmed in
#     app/features/demo/routes.py:74 + service.py:39-43.
# Output to PRPs/ai_docs/prp-41-contract-probe-report.md.
# STOP and patch the PRP wording if any cited contract is absent / drifted.

# ─────────────────────────────────────────────────────────────────────────
# R5 — Agent HITL approval blocks until POST /approve returns.
# ─────────────────────────────────────────────────────────────────────────
# The HITL gate works like this on the synchronous chat path:
#   1. step sends chat message → agent calls tool_save_scenario.
#   2. tool_save_scenario sees requires_approval("save_scenario") fires;
#      short-circuits and returns {status: "approval_required",
#      action: "save_scenario", ...}.
#   3. ChatResponse comes back with pending_approval=true,
#      pending_action: PendingAction (carrying the action_id).
#   4. The step IMMEDIATELY emits an intermediate event:
#        StepEvent(event_type="step_complete", status="running",
#                  step.data={"awaiting_approval": true,
#                             "approval_url": "/agents/sessions/{id}/approve",
#                             "action_id": pending_action["action_id"],
#                             "session_id": session_id})
#      This is a fenced exception to "step_complete carries terminal
#      status only" — the FE renders the Approve button when status
#      == 'running' AND awaiting_approval == true. The state-machine
#      treats it as still-in-flight.
#   5. Pipeline sleeps the 3 s display delay (asyncio.sleep(3.0)).
#   6. POST /approve with {action_id, approved: true}. If a frontend
#      one-click pre-empts, the POST returns 4xx — absorb gracefully
#      (the step still emits PASS because the approval landed).
#   7. Emit step_complete with the terminal status (pass/skip), the
#      ApprovalResponse fields (action_id, approved,
#      approval_decision="approved"|"rejected"|"expired"), and the
#      original session_id+tokens+tool_calls_count.
# Hard fallback: if the 90 s timeout fires before either the auto-approve
# OR the frontend pre-empt completes, emit skip with detail
# "approval timed out — pipeline continued"; cleanup still closes
# the session.

# ─────────────────────────────────────────────────────────────────────────
# Multi-event semantics for step_agent_hitl_flow.
# ─────────────────────────────────────────────────────────────────────────
# The run_pipeline orchestrator yields step_start → step_complete per
# step in lockstep. step_agent_hitl_flow needs to surface "awaiting
# approval" mid-step. Two options (Task 1 picks ONE):
#
#   (A) The step function YIELDS an intermediate StepEvent in addition
#       to its terminal (status, detail, data) return. Would require
#       changing the StepFn signature from
#         async def fn(ctx, client) -> StepResult
#       to
#         async def fn(ctx, client) -> StepResult OR
#         AsyncIterator[StepResult] (with the orchestrator switching).
#       INVASIVE — touches every step function's signature.
#
#   (B) The step function carries the awaiting_approval flag in its
#       terminal step.data WHEN the auto-approve eventually fires. The
#       frontend reads the same step.data (`awaiting_approval: true`)
#       on the eventual step_complete event and only renders the
#       Approve button if `step.status === 'running'`. Since the
#       terminal event is `pass` (status='pass'), the Approve button
#       does NOT render at terminal — only the historical
#       awaiting_approval flag is visible (for debugging).
#       Means: the visitor cannot pre-empt; the auto-approve always
#       wins. CONTRADICTS the INITIAL-41 D3 acceptance criterion
#       ("clicking it advances the step within 3 s").
#
#   (C) HYBRID: step_agent_hitl_flow yields an intermediate
#       step_complete event with status='running' via a NEW orchestrator
#       hook. The orchestrator (run_pipeline) provides a `yield_event`
#       callable in the client wrapper that the step function can call
#       to emit an intermediate event. The terminal return remains
#       (status, detail, data) as today. Minimal change to other
#       steps; the new hook is opt-in.
#
# DECISION RECOMMENDATION: pick (C). Task 1 must validate that
# run_pipeline can accept the intermediate-yield helper without breaking
# the existing 22 steps. The implementer SHOULD write the new helper as
# a property on `_Client` (e.g., `client.yield_event(StepEvent)`) so
# steps remain `async def fn(ctx, client) -> StepResult` and only the
# HITL step uses the new hook.
#
# Alternatively (D) — a NON-invasive simplification: emit the
# "awaiting_approval" state through a single terminal step_complete
# whose `status="running"` is the **already-supported** intermediate
# status (`StepStatus` allows "running"). The orchestrator's
# fail-fast check is `if status == "fail": break` so a "running"
# terminal does NOT stop the loop — BUT this also means the
# orchestrator will emit a step_start for the NEXT step right after.
# That breaks the visual model (FE expects each step to flip to a
# terminal status before the next one starts).
#
# *** Implementer guidance: (C) is the design. The
# `_Client.yield_event(StepEvent)` hook is added as part of Task 3.
# Other steps remain untouched. Task 1 must verify this design fits
# the existing `run_pipeline` loop without breaking back-compat. ***

# ─────────────────────────────────────────────────────────────────────────
# demo_minimal phase rename trade-off.
# ─────────────────────────────────────────────────────────────────────────
# The legacy PHASE_AGENT = "agent" constant + its single step "agent"
# is used on BOTH demo_minimal/sparse AND showcase_rich branches in
# `_phase_table()`. PRP-41 wants to introduce `PHASE_AGENTS = "agents"`
# with `step_agent_hitl_flow`. Two options:
#
#   (X) Rename ONLY on showcase_rich. demo_minimal + sparse keep the
#       legacy `agent` phase + `step_agent` row. The HITL flow is
#       showcase_rich-only.
#       Pros: minimal back-compat risk; HITL needs LLM key which
#             demo_minimal CI environments may not have.
#       Cons: lockstep test has two parallel branches; PHASE_DEFS.ts
#             needs scenario-aware phase_id selection.
#
#   (Y) Rename for ALL scenarios (demo_minimal also gets the new
#       phase id `agents` + still uses the existing `step_agent`
#       function, just under the new phase id).
#       Pros: lockstep stays simple; one phase id everywhere.
#       Cons: visitor on demo_minimal sees an "agents" phase that
#             only does a single-turn chat (no approval gate). The
#             phase label is mildly misleading.
#
#   (Z) Rename for ALL + step_agent (demo_minimal) and
#       step_agent_hitl_flow (showcase_rich) coexist as two distinct
#       step fns under the same `agents` phase id, picked by
#       `_phase_table()` based on scenario.
#       Pros: best of both — phase id stays unified; HITL only fires
#             on showcase_rich.
#       Cons: PHASE_DEFS.ts needs ALL_STEPS to include BOTH step ids;
#             frontend renders the right one based on the WS payload.
#
# DECISION RECOMMENDATION: pick (Z) — gives the cleanest end-state.
# Both step ids appear in ALL_STEPS; on demo_minimal/sparse the wire
# emits `"agent"` (the legacy step name), on showcase_rich the wire
# emits `"agent_hitl_flow"`. Task 1 confirms with the lockstep test
# fixture which step id maps to which scenario.

# ─────────────────────────────────────────────────────────────────────────
# Vertical-slice rule (load-bearing).
# ─────────────────────────────────────────────────────────────────────────
# app/features/demo/* may import from app.core.* + app.shared.* + standard
# library only. NEVER `from app.features.agents.X import ...`, NEVER
# `from app.features.ops.X import ...`, NEVER `from app.features.{registry,
# scenarios,rag}.X import ...`. Grep guard (MUST be empty):
#   git grep -nE "from app\.features\.(agents|ops|registry|scenarios|rag)" \
#     app/features/demo/

# ─────────────────────────────────────────────────────────────────────────
# WebSocket contract additive only.
# ─────────────────────────────────────────────────────────────────────────
# StepEvent.data is dict[str, Any] — new payload fields ride inside
# without a schema bump. New keys PRP-41 introduces:
#   - On `agent_hitl_flow` step_complete:
#       session_id: str
#       awaiting_approval: bool        # only on intermediate event
#       approval_url: str | None       # only on intermediate event
#       action_id: str | None
#       approval_decision: str | None  # "approved"|"rejected"|"expired"|"timed_out"
#       tokens_used: int
#       tool_calls_count: int
#   - On `ops_snapshot` step_complete:
#       stale_aliases_count: int
#       retraining_candidates_count: int
#       total_runs: int
#       total_aliases: int
#       degrading_health_count: int
# Existing keys unchanged.

# ─────────────────────────────────────────────────────────────────────────
# CRLF / LF + repo-line-endings memory.
# ─────────────────────────────────────────────────────────────────────────
# Edit/Write on CRLF files produces whole-file noise diffs. Run
# `git diff --stat` before committing; if a file shows a whole-file diff,
# DO NOT bundle the normalisation into PRP-41. Memory anchor:
# [[repo-line-endings-crlf]]

# ─────────────────────────────────────────────────────────────────────────
# Frontend type-check command is project-scoped.
# ─────────────────────────────────────────────────────────────────────────
# Use `pnpm tsc --noEmit -p tsconfig.app.json` — NOT bare `pnpm tsc --noEmit`.
# The root tsconfig has `files: []` and will pass while the app tsconfig
# still has errors. Do NOT trust a prior HANDOFF green check.

# ─────────────────────────────────────────────────────────────────────────
# localStorage SSR + quota safety (R18).
# ─────────────────────────────────────────────────────────────────────────
# - Guard `typeof window === 'undefined'` on every read/write.
# - Wrap reads in try/except for invalid JSON.
# - Cap at 5 entries (FIFO eviction).
# - Versioned key (`forecastlab.showcase.runs.v1`) so a future schema
#   change can switch keys without colliding.
# - Write ONLY inside `pipeline_complete` / `error` handlers; NEVER
#   during render (SSR mismatch + thrash).

# ─────────────────────────────────────────────────────────────────────────
# Approve button double-fire race.
# ─────────────────────────────────────────────────────────────────────────
# Frontend click + backend auto-approve both fire `POST /approve`. The
# second call lands after the first commits → returns 4xx (probably 400
# "action not found" or 409 if implemented as conflict — Task 1 confirms).
# Absorb gracefully on the backend side; the step still emits PASS.
# On the frontend side, the Approve button is disabled after the first
# click (optimistic state).
```

---

## Implementation Blueprint

### Data models / additive helpers

```python
# app/features/demo/pipeline.py — additive phase constants
PHASE_AGENTS = "agents"   # PRP-41 (replaces PHASE_AGENT for showcase_rich,
                          #         and for demo_minimal/sparse under design Z)
PHASE_OPS = "ops"         # PRP-41
# PHASE_AGENT stays in the file as a legacy constant ONLY if Task 1 picks
# design X (per-scenario phase id). Under design Z (recommended), the
# constant is REMOVED in favour of PHASE_AGENTS.
```

```python
# app/features/demo/pipeline.py — additive DemoContext fields
@dataclass
class DemoContext:
    # ... existing fields preserved ...

    # PRP-41 — additive context for the agents + ops phases. Set ONLY by
    # step_agent_hitl_flow / step_ops_snapshot; remain None on demo_minimal
    # / sparse runs that don't exercise them (under design Z, demo_minimal
    # still uses the legacy step_agent which does NOT touch these).
    approval_action_id: str | None = None
    agent_approval_decision: str | None = None  # "approved" | "rejected"
                                                # | "expired" | "timed_out"
```

```python
# app/features/demo/pipeline.py — module-level constants (PRP-41)
_APPROVAL_DISPLAY_DELAY_S = 3.0        # auto-approve fires after this delay
_APPROVAL_HARD_TIMEOUT_S = 90.0        # hard fallback skip after this
_HITL_PROMPT = (
    "Save a 10% price-cut scenario plan for the demo-production model "
    "as 'showcase-agent-savedplan'."
)
```

```python
# app/features/demo/pipeline.py — _Client extension (PRP-41)
# Under design Z (recommended), _Client gains an opt-in helper that lets
# the HITL step yield an intermediate StepEvent. Other steps unchanged.

class _Client:
    # ... existing __init__, __aenter__, __aexit__, request unchanged ...

    def __init__(self, app: FastAPI, *, event_sink: list[StepEvent] | None = None) -> None:
        # event_sink is set by run_pipeline; collected events are flushed
        # to the WS by the orchestrator between fn call iterations.
        self._app = app
        self._client: AsyncClient | None = None
        self._event_sink = event_sink

    def yield_event(self, event: StepEvent) -> None:
        """Buffer an intermediate StepEvent for the orchestrator to flush.

        PRP-41 — only step_agent_hitl_flow uses this. Other steps remain
        terminal-only.
        """
        if self._event_sink is None:
            return  # silently drop in tests that don't set the sink
        self._event_sink.append(event)
```

### List of tasks (dependency-ordered)

```yaml
Task 1:  Contract Probe (this PRP — output PRPs/ai_docs/prp-41-contract-probe-report.md)
Task 2:  Backend — additive phase constants + DemoContext fields + module constants
Task 3:  Backend — _Client.yield_event helper + run_pipeline event-sink wiring
Task 4:  Backend — step_agent_hitl_flow implementation
Task 5:  Backend — step_ops_snapshot implementation
Task 6:  Backend — _phase_table() row swap + insert (relative anchors)
Task 7:  Backend tests — per-step happy + skip + timeout suite (5 new tests)
Task 8:  Backend test — test_phase_table_showcase_rich_… flip (23 → 24)
Task 9:  Frontend — PHASE_DEFS.ts extension (swap + append) + PHASE_DEFS.test.ts lockstep
Task 10: Frontend — DemoPhasePanel.tsx onValueChange fix (#311 / D10) + test
Task 11: Frontend — demo-step-card.tsx HitlFlowSummary + Approve button + OpsSnapshotMiniGrid (+ tests)
Task 12: Frontend — showcase.tsx resolveInspectHref switch extension + Stop button wiring
Task 13: Frontend — use-demo-pipeline.ts stop callback (+ test)
Task 14: Frontend — ShowcaseKpiStrip component (+ test)
Task 15: Frontend — InspectArtifactsPanel component (+ test)
Task 16: Frontend — RunHistoryStrip component (+ test)
Task 17: Backend integration test — tests/test_e2e_demo.py::test_showcase_rich_full_epic
Task 18: Docs — extend docs/_base/RUNBOOKS.md with 5 new step failure modes
Task 19: Docs — clean docs/user-guide/showcase-walkthrough.md "planned" markers
Task 20: Dogfood (manual; checklist below) — verify D1..D10 against the running stack
```

### Per task pseudocode (the load-bearing parts)

```python
# ─────────────────────────────────────────────────────────────────────────
# Task 2 — Additive phase constants + DemoContext fields
# ─────────────────────────────────────────────────────────────────────────

# app/features/demo/pipeline.py
# INJECT after PHASE_CLEANUP line (~1996 on dev tip — locate by symbol):
#   PHASE_AGENTS = "agents"  # PRP-41 (replaces legacy "agent" under design Z)
#   PHASE_OPS = "ops"        # PRP-41

# MODIFY PHASE_AGENT line (~1995): under design Z, REPLACE the line
# with PHASE_AGENTS = "agents". DO NOT keep both — the lockstep test
# would conflict. The legacy "agent" string LITERAL (used by step_agent
# return values, etc.) is unrelated to the phase id; only the phase id
# moves.

# MODIFY DemoContext (locate by `@dataclass class DemoContext`):
#   INJECT after `embedding_unreachable: bool = False` line:
#     # PRP-41 — additive HITL approval state.
#     approval_action_id: str | None = None
#     agent_approval_decision: str | None = None  # "approved" | "rejected"
#                                                 # | "expired" | "timed_out"

# INJECT after the _APPROVAL_HARD_TIMEOUT_S line:
#   _HITL_PROMPT = (
#       "Save a 10% price-cut scenario plan for the demo-production "
#       "model as 'showcase-agent-savedplan'."
#   )
#   _APPROVAL_DISPLAY_DELAY_S = 3.0
#   _APPROVAL_HARD_TIMEOUT_S = 90.0

# ─────────────────────────────────────────────────────────────────────────
# Task 3 — _Client.yield_event helper + run_pipeline event-sink wiring
# ─────────────────────────────────────────────────────────────────────────

# app/features/demo/pipeline.py
# MODIFY _Client.__init__ to accept an optional event_sink list.
# MODIFY _Client.__aenter__ / __aexit__: no change.
# INJECT method:
#   def yield_event(self, event: StepEvent) -> None:
#       if self._event_sink is None:
#           return
#       self._event_sink.append(event)
#
# MODIFY run_pipeline:
#   - Inside `async with _Client(app) as client:` (currently line ~2105),
#     CREATE `intermediate_events: list[StepEvent] = []`.
#   - PASS `event_sink=intermediate_events` to the _Client constructor.
#   - INSIDE the for-loop, AFTER the step fn returns its terminal
#     (status, detail, data) but BEFORE yielding the step_complete event,
#     drain `intermediate_events` by yielding each one in FIFO order then
#     `intermediate_events.clear()`. Then yield the terminal step_complete.
#   - Order matters: intermediate events MUST emit BEFORE the terminal
#     event so the FE state machine processes "awaiting_approval" before
#     "approved".

# Pseudo (only the modified inner-loop):
async with _Client(app, event_sink=intermediate_events) as client:
    for index, (phase_name, name, fn) in enumerate(rows, start=1):
        # ... yield step_start as before ...
        try:
            status, detail, data = await fn(ctx, client)
        except _StepError as exc:
            status, detail, data = "fail", str(exc), {}
        except ...:
            ...
        # NEW: drain intermediate events FIRST.
        for ev in intermediate_events:
            yield ev
        intermediate_events.clear()
        # THEN yield the terminal step_complete.
        yield StepEvent(event_type="step_complete", ..., status=status,
                        detail=detail, data=data, ...)
        if status == "fail":
            any_fail = True
            break

# ─────────────────────────────────────────────────────────────────────────
# Task 4 — step_agent_hitl_flow
# ─────────────────────────────────────────────────────────────────────────

async def step_agent_hitl_flow(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-41 — HITL approval round-trip on the experiment agent.

    Sequence:
      1. _llm_key_present() → if False, return ('skip', "no API key ...", {}).
      2. POST /agents/sessions {agent_type="experiment"} → session_id.
      3. POST /agents/sessions/{id}/chat with _HITL_PROMPT, stream=False.
         Response carries pending_approval=true + pending_action.
      4. Emit intermediate StepEvent(status="running", data={
           "awaiting_approval": true,
           "approval_url": f"/agents/sessions/{session_id}/approve",
           "action_id": pending_action["action_id"],
           "session_id": session_id,
         }) via client.yield_event(...).
      5. Sleep _APPROVAL_DISPLAY_DELAY_S (3 s); meanwhile a frontend
         one-click Approve may fire first.
      6. POST /approve {action_id, approved: true}. Absorb 4xx as
         "already approved by frontend".
      7. ctx.approval_action_id = action_id;
         ctx.agent_approval_decision = approval_response["status"]
         ("executed"|"rejected"|"expired").
      8. Return ('pass', detail, data) with the terminal payload.

    Hard timeout: if total elapsed > _APPROVAL_HARD_TIMEOUT_S BEFORE step 6
    completes, return ('skip', "approval timed out — pipeline continued",
    {"timed_out": true, "session_id": session_id}).

    NEVER raises (all _StepError caught, mapped to skip).
    """
    key_present = _llm_key_present()
    logger.info("demo.agent_hitl_flow.key_present", present=key_present)
    if not key_present:
        return ("skip", "no API key matching agent_default_model provider", {})

    started_at = time.monotonic()

    # (1+2) — session.
    try:
        create_body = await client.request(
            "agent_hitl_flow[session]", "POST",
            "/agents/sessions",
            json_body={"agent_type": "experiment", "initial_context": None},
        )
    except _StepError as exc:
        return ("skip", f"session-create failed: {exc}", {})
    session_id = create_body.get("session_id")
    if not isinstance(session_id, str):
        return ("skip", "no session_id returned", {})
    ctx.session_id = session_id

    # (3) — chat that triggers the gated tool.
    try:
        chat_body = await client.request(
            "agent_hitl_flow[chat]", "POST",
            f"/agents/sessions/{session_id}/chat",
            json_body={"message": _HITL_PROMPT, "stream": False},
        )
    except _StepError as exc:
        return ("skip", f"chat round-trip failed: {exc}", {})

    pending_approval = bool(chat_body.get("pending_approval", False))
    pending_action = chat_body.get("pending_action") or {}
    tokens_used = int(chat_body.get("tokens_used", 0))
    tool_calls = chat_body.get("tool_calls", [])
    tool_count = len(tool_calls) if isinstance(tool_calls, list) else 0

    if not pending_approval or not pending_action:
        # The agent didn't trigger the gate (e.g. it answered without
        # calling tool_save_scenario). Skip-by-design: not a failure.
        return (
            "skip",
            f"agent did not trigger save_scenario (tokens={tokens_used}, "
            f"tool_calls={tool_count})",
            {
                "session_id": session_id,
                "tokens_used": tokens_used,
                "tool_calls_count": tool_count,
            },
        )

    action_id = pending_action.get("action_id")
    if not isinstance(action_id, str):
        return ("skip", "pending_action.action_id missing", {})
    ctx.approval_action_id = action_id

    # (4) — yield intermediate event for the FE to render Approve.
    client.yield_event(StepEvent(
        event_type="step_complete",
        step_name="agent_hitl_flow",
        step_index=0,             # filled in by orchestrator? — see Task 3
        total_steps=0,            # ditto
        status="running",
        detail="awaiting approval (auto-approve in 3 s)",
        duration_ms=(time.monotonic() - started_at) * 1000.0,
        data={
            "awaiting_approval": True,
            "approval_url": f"/agents/sessions/{session_id}/approve",
            "action_id": action_id,
            "session_id": session_id,
            "tokens_used": tokens_used,
            "tool_calls_count": tool_count,
        },
        phase_name=PHASE_AGENTS,
        phase_index=None,         # filled in by orchestrator
        phase_total=None,
    ))

    # NOTE: step_index / total_steps / phase_index / phase_total —
    # cannot be set here because the step fn doesn't know its index.
    # Two options:
    #   - Plumb the index through (would change StepFn signature) —
    #     INVASIVE.
    #   - Orchestrator fills them in when draining the event sink
    #     (it knows the index — see Task 3).
    # Task 1 verifies orchestrator-fill-in works.

    # (5) — display delay.
    elapsed_after_intermediate = time.monotonic() - started_at
    delay = max(0.0, _APPROVAL_DISPLAY_DELAY_S - elapsed_after_intermediate)
    if delay > 0:
        await asyncio.sleep(delay)

    # (5b) — hard-timeout check.
    elapsed_before_approve = time.monotonic() - started_at
    if elapsed_before_approve > _APPROVAL_HARD_TIMEOUT_S:
        ctx.agent_approval_decision = "timed_out"
        return (
            "skip",
            "approval timed out — pipeline continued",
            {
                "timed_out": True,
                "session_id": session_id,
                "action_id": action_id,
            },
        )

    # (6) — POST /approve. Absorb 4xx (frontend pre-empted).
    approval_decision = "expired"  # default if absorbed
    try:
        approve_body = await client.request(
            "agent_hitl_flow[approve]", "POST",
            f"/agents/sessions/{session_id}/approve",
            json_body={"action_id": action_id, "approved": True},
        )
        approval_decision = str(approve_body.get("status", "executed"))
    except _StepError as exc:
        if 400 <= exc.status_code < 500:
            # Frontend likely pre-empted — absorb. The approval already
            # landed; the decision is whatever the server recorded.
            logger.info(
                "demo.agent_hitl_flow.approve_pre_empted",
                session_id=session_id,
                action_id=action_id,
                status_code=exc.status_code,
            )
            approval_decision = "executed"  # optimistic — visitor clicked
        else:
            return ("skip", f"approve failed: {exc}", {
                "session_id": session_id,
                "action_id": action_id,
            })

    ctx.agent_approval_decision = approval_decision

    return (
        "pass",
        f"session={session_id[:8]}... tokens={tokens_used} "
        f"tool_calls={tool_count} approved={approval_decision}",
        {
            "session_id": session_id,
            "action_id": action_id,
            "approval_decision": approval_decision,
            "tokens_used": tokens_used,
            "tool_calls_count": tool_count,
        },
    )

# ─────────────────────────────────────────────────────────────────────────
# Task 5 — step_ops_snapshot
# ─────────────────────────────────────────────────────────────────────────

async def step_ops_snapshot(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-41 — fetch /ops/* endpoints and embed a 5-key KPI payload.

    Reads:
      GET /ops/summary
      GET /ops/retraining-candidates?limit=5
      GET /ops/model-health?limit=5

    Returns ('pass', detail, data) on green or ('warn', ...) on a partial
    failure (one of the three endpoints 4xx/5xx). Never fails the whole
    pipeline.
    """
    summary: dict[str, Any] = {}
    candidates_body: dict[str, Any] = {}
    health_body: dict[str, Any] = {}

    try:
        summary = await client.request(
            "ops_snapshot[summary]", "GET", "/ops/summary",
        )
    except _StepError as exc:
        logger.warning("demo.ops_snapshot.summary_failed", error=str(exc))

    try:
        candidates_body = await client.request(
            "ops_snapshot[retraining]", "GET",
            "/ops/retraining-candidates?limit=5",
        )
    except _StepError as exc:
        logger.warning("demo.ops_snapshot.retraining_failed", error=str(exc))

    try:
        health_body = await client.request(
            "ops_snapshot[health]", "GET",
            "/ops/model-health?limit=5",
        )
    except _StepError as exc:
        logger.warning("demo.ops_snapshot.health_failed", error=str(exc))

    aliases = summary.get("aliases") or []
    if not isinstance(aliases, list):
        aliases = []
    stale_count = sum(1 for a in aliases if isinstance(a, dict) and a.get("is_stale"))
    total_aliases = len(aliases)

    runs = summary.get("runs") or {}
    if not isinstance(runs, dict):
        runs = {}
    # RunHealth carries a `counts` list of {status, count}; total_runs is
    # the sum across statuses (Task 1 confirms the exact field name).
    counts = runs.get("counts") or []
    total_runs = (
        sum(int(c.get("count", 0)) for c in counts if isinstance(c, dict))
        if isinstance(counts, list)
        else 0
    )

    candidates = candidates_body.get("candidates") or []
    retraining_count = len(candidates) if isinstance(candidates, list) else 0

    entries = health_body.get("entries") or []
    degrading_count = (
        sum(
            1
            for e in entries
            if isinstance(e, dict) and e.get("drift_direction") == "degrading"
        )
        if isinstance(entries, list)
        else 0
    )

    data = {
        "stale_aliases_count": stale_count,
        "retraining_candidates_count": retraining_count,
        "total_runs": total_runs,
        "total_aliases": total_aliases,
        "degrading_health_count": degrading_count,
    }

    # If all three calls returned non-empty data, PASS. If at least one
    # was empty (e.g., empty DB), still PASS (the test asserts the keys
    # are present and >= 0).
    if summary or candidates_body or health_body:
        detail = (
            f"stale_aliases={stale_count} retraining={retraining_count} "
            f"runs={total_runs} aliases={total_aliases} degrading={degrading_count}"
        )
        return ("pass", detail, data)

    # All three endpoints failed — warn (pipeline still goes green).
    return ("warn", "/ops/* all 4xx/5xx — ops snapshot unavailable", data)

# ─────────────────────────────────────────────────────────────────────────
# Task 6 — _phase_table() row swap + insert
# ─────────────────────────────────────────────────────────────────────────

# app/features/demo/pipeline.py — MODIFY _phase_table:
#
# FIND the line:
#   agent_steps: list[tuple[str, StepFn]] = [("agent", step_agent)]
# REPLACE with (under design Z):
#   # PRP-41 — replace the legacy single step with the HITL flow on
#   # showcase_rich; demo_minimal / sparse keep the legacy step_agent.
#   agent_steps: list[tuple[str, StepFn]] = (
#       [("agent_hitl_flow", step_agent_hitl_flow)]
#       if scenario is ScenarioPreset.SHOWCASE_RICH
#       else [("agent", step_agent)]
#   )
#
# FIND the line:
#   cleanup_steps: list[tuple[str, StepFn]] = [("cleanup", step_cleanup)]
# INJECT BEFORE it:
#   # PRP-41 — new ops phase, empty under demo_minimal/sparse.
#   ops_steps: list[tuple[str, StepFn]] = (
#       [("ops_snapshot", step_ops_snapshot)]
#       if scenario is ScenarioPreset.SHOWCASE_RICH
#       else []
#   )
#
# FIND the line:
#   rows += [(PHASE_AGENT, name, fn) for name, fn in agent_steps]
# REPLACE with:
#   rows += [(PHASE_AGENTS, name, fn) for name, fn in agent_steps]
#
# FIND the line:
#   rows += [(PHASE_CLEANUP, name, fn) for name, fn in cleanup_steps]
# INJECT BEFORE it:
#   rows += [(PHASE_OPS, name, fn) for name, fn in ops_steps]
#
# Result phase order:
#   data → modeling → decision → portfolio → planning → knowledge →
#   verify → agents → ops → cleanup
# Step count on showcase_rich: 23 → 24 (one row swap from `agent` to
# `agent_hitl_flow` PLUS one new `ops_snapshot` row). Phase count: 9
# → 10 (rename + append).

# ─────────────────────────────────────────────────────────────────────────
# Task 9 — PHASE_DEFS.ts extension
# ─────────────────────────────────────────────────────────────────────────

# frontend/src/components/demo/PHASE_DEFS.ts
# MODIFY ALL_STEPS:
#   FIND:
#     { phase: 'agent', step: 'agent', label: 'Agent chat' },
#   REPLACE with (in this order — DESIGN Z, unified phase id "agents"):
#     { phase: 'agents', step: 'agent', label: 'Agent chat (legacy)' },
#     { phase: 'agents', step: 'agent_hitl_flow', label: 'Agent HITL approval' },
#     { phase: 'ops', step: 'ops_snapshot', label: 'Ops snapshot' },
#   PRESERVE everything before / after.
#   NOTE: BOTH 'agent' and 'agent_hitl_flow' live under the same phase id
#   'agents'. demo_minimal renders the legacy `'agent'` row; showcase_rich
#   renders `'agent_hitl_flow'` + `'ops_snapshot'`. The legacy 'agent'
#   step function stays in pipeline.py and is wired by `_phase_table()`
#   on the non-showcase-rich branch (Task 6).
#
# MODIFY the filter — design Z requires a SECOND exclusion set, because
# `SHOWCASE_RICH_STEP_NAMES` is the "exclude from demo_minimal" set, not
# the "exclude from showcase_rich" set. Task 1 contract probe § 7
# confirmed this filter restructure is required:
#
#   const DEMO_MINIMAL_ONLY_STEP_NAMES = new Set(['agent'])  // legacy
#
#   export function phaseDefsForScenario(scenario: ScenarioPreset): readonly PhaseDef[] {
#     if (scenario === 'showcase_rich') {
#       return ALL_STEPS.filter((d) => !DEMO_MINIMAL_ONLY_STEP_NAMES.has(d.step))
#     }
#     return ALL_STEPS.filter((d) => !SHOWCASE_RICH_STEP_NAMES.has(d.step))
#   }
#
# MODIFY SHOWCASE_RICH_STEP_NAMES (lines 66–82):
#   ADD: 'agent_hitl_flow', 'ops_snapshot'.
#   (So they're excluded from demo_minimal / sparse.)
#
# MODIFY PHASE_LABEL (lines 94–106):
#   REPLACE: agent: 'Agent' → agents: 'Agents (HITL)'.
#   ADD: ops: 'Ops snapshot'.
#
# MODIFY PHASE_ORDER (lines 109–121):
#   REPLACE: 'agent' → 'agents'.
#   INSERT AFTER 'agents': 'ops'.
#   Result: data, modeling, decision, portfolio, planning, knowledge,
#           verify, agents, ops, cleanup (10 entries).

# ─────────────────────────────────────────────────────────────────────────
# Task 10 — DemoPhasePanel.tsx onValueChange fix
# ─────────────────────────────────────────────────────────────────────────

# frontend/src/components/demo/DemoPhasePanel.tsx
# MODIFY the component body. CURRENT pattern:
#   const value = runningPhase ?? fallback ?? phases[0]?.id ?? ''
#   return <Accordion value={value} type="single" collapsible> ... </Accordion>
#
# FIX pattern:
#   const computedValue = runningPhase ?? fallback ?? phases[0]?.id ?? ''
#   const [expandedPhase, setExpandedPhase] = useState<string>(computedValue)
#   useEffect(() => {
#       setExpandedPhase(computedValue)
#   }, [computedValue])
#   return <Accordion
#     value={expandedPhase}
#     onValueChange={setExpandedPhase}
#     type="single" collapsible
#   > ... </Accordion>
#
# Add `useState` + `useEffect` imports if not already.
# Add a vitest in DemoPhasePanel.test.tsx asserting that:
#   - Initial render: value === runningPhase OR phases[0].id
#   - After runningPhase change: value updates
#   - After pipeline_complete (runningPhase null) + user click on
#     phase 'verify': value moves to 'verify' (no snap-back).

# ─────────────────────────────────────────────────────────────────────────
# Task 11 — demo-step-card.tsx HitlFlowSummary + Approve + OpsSnapshotMiniGrid
# ─────────────────────────────────────────────────────────────────────────

# frontend/src/components/demo/demo-step-card.tsx
# ADD helper components (after the existing PRP-39/40 helpers):
#
#   function HitlFlowSummary({ data }: { data: Record<string, unknown> }) {
#       const sessionId = String(data.session_id ?? '')
#       const tokens = Number(data.tokens_used ?? 0)
#       const toolCalls = Number(data.tool_calls_count ?? 0)
#       const decision = String(data.approval_decision ?? '')
#       return (
#           <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
#               {sessionId && <Badge variant="outline">session={sessionId.slice(0,8)}...</Badge>}
#               <Badge variant="outline">tokens={tokens}</Badge>
#               <Badge variant="outline">tool_calls={toolCalls}</Badge>
#               {decision && <Badge>approval={decision}</Badge>}
#           </div>
#       )
#   }
#
#   function OpsSnapshotMiniGrid({ data }: { data: Record<string, unknown> }) {
#       const tiles = [
#           ['stale_aliases', data.stale_aliases_count],
#           ['retraining', data.retraining_candidates_count],
#           ['runs', data.total_runs],
#           ['aliases', data.total_aliases],
#           ['degrading', data.degrading_health_count],
#       ] as const
#       return (
#           <div className="mt-3 grid grid-cols-5 gap-2 text-xs">
#               {tiles.map(([label, value]) => (
#                   <div key={label} className="rounded border p-2 text-center">
#                       <div className="text-muted-foreground">{label}</div>
#                       <div className="font-semibold">{value !== undefined ? String(value) : '—'}</div>
#                   </div>
#               ))}
#           </div>
#       )
#   }
#
# ADD conditional rendering blocks in the main card body:
#   {step.name === 'agent_hitl_flow' && <HitlFlowSummary data={step.data} />}
#   {step.name === 'ops_snapshot' && <OpsSnapshotMiniGrid data={step.data} />}
#
# ADD Approve button block (sibling of the existing Inspect button):
#   {step.data.awaiting_approval === true && step.status === 'running' && (
#       <ApproveButton
#           approvalUrl={String(step.data.approval_url ?? '')}
#           actionId={String(step.data.action_id ?? '')}
#       />
#   )}
#
# ADD ApproveButton internal component (in same file or a small sibling):
#   function ApproveButton(props: { approvalUrl: string, actionId: string }) {
#       const [clicked, setClicked] = useState(false)
#       const [waitingMs, setWaitingMs] = useState(0)
#       // ... POST to approvalUrl with {action_id, approved: true}
#       // ... tick a 1-second interval; render "Still waiting for approval —
#       //     auto-approve in {N}s" when waitingMs > 30_000.
#       // Use fetch() — TanStack Query is overkill for a one-shot button.
#       return (
#           <div className="mt-3 flex items-center gap-3">
#               <Button onClick={onClick} disabled={clicked} size="sm">
#                   {clicked ? 'Approving...' : 'Approve'}
#               </Button>
#               {waitingMs > 30_000 && (
#                   <span className="text-xs text-muted-foreground">
#                       Still waiting for approval — auto-approve in {N}s
#                   </span>
#               )}
#           </div>
#       )
#   }
#
# Tests (in demo-step-card.test.tsx):
#   - HitlFlowSummary renders the 4 badges with truthy data.
#   - OpsSnapshotMiniGrid renders 5 tiles; missing keys render '—'.
#   - Approve button appears only when awaiting_approval=true AND
#     status='running'.
#   - Clicking Approve disables the button and POSTs to approvalUrl.
#   - Waiting > 30s renders the warning callout.

# ─────────────────────────────────────────────────────────────────────────
# Task 12 — showcase.tsx resolveInspectHref + Stop button wiring
# ─────────────────────────────────────────────────────────────────────────

# frontend/src/pages/showcase.tsx
# MODIFY resolveInspectHref switch (lines ~41–83):
#   ADD cases:
#     case 'agent_hitl_flow': return ROUTES.CHAT
#     case 'ops_snapshot':    return ROUTES.OPS
#
# MODIFY hook destructure (lines ~87–99):
#   ADD `stop` to the destructure.
#
# MODIFY controls card body:
#   INSERT a Stop button visible when `phase === 'running'`:
#     {phase === 'running' && (
#         <Button onClick={stop} variant="outline" size="sm">
#             Stop
#         </Button>
#     )}
#
# INSERT new components in this order (top to bottom):
#   <ShowcaseKpiStrip steps={steps} />        // above controls card
#   <RunHistoryStrip                          // above controls card,
#       onReplay={(req) => start(req)}        //   below KPI strip
#       lastRun={summary}
#   />
#   <ControlsCard ... />                       // existing
#   <DemoPhasePanel ... />                     // existing
#   {phase === 'done' && summary && (
#       <InspectArtifactsPanel steps={steps} summary={summary} />
#   )}

# ─────────────────────────────────────────────────────────────────────────
# Task 13 — use-demo-pipeline.ts stop callback
# ─────────────────────────────────────────────────────────────────────────

# frontend/src/hooks/use-demo-pipeline.ts
# CURRENT (line 198):
#   const disconnectRef = useRef<(() => void) | null>(null)
#
# Add a stop callback (in the hook body, near the start callback):
#   const stop = useCallback(() => {
#       disconnectRef.current?.()
#       // Reset state to idle (omit summary to preserve any in-flight data).
#       setState((prev) => ({ ...prev, phase: 'idle', errorMessage: 'Pipeline cancelled by user.' }))
#   }, [])
#
# Add `stop` to the return object (line ~247–259):
#   return { steps, phases, runningPhase, phase, summary, errorMessage,
#            isRunning, connectionStatus, start, stop, scenario, setScenario }
#
# Test in use-demo-pipeline.test.ts:
#   - stop closes the WS (assert disconnect mock was called).
#   - phase returns to 'idle' within 5 s.
#   - subsequent start() works (reconnect fires).

# ─────────────────────────────────────────────────────────────────────────
# Task 14 — ShowcaseKpiStrip.tsx
# ─────────────────────────────────────────────────────────────────────────

# frontend/src/components/demo/ShowcaseKpiStrip.tsx (NEW)
# Renders 5 tiles. Hidden until at least one step_complete event arrives
# (i.e. `steps.some(s => s.status !== 'idle')`).
#
# Tile sources (every key already verified against PRP-39/40 step.data):
#   runs_registered:
#     count steps whose name ∈ {register, stale_alias_trigger,
#     safer_promote_flow, v2_train} AND step.data.run_id is set.
#   aliases_live:
#     ops_snapshot.step.data.total_aliases (preferred); fallback to
#     counting steps with step.data.alias set across register /
#     safer_promote_flow / stale_alias_trigger.
#   batch_items_completed:
#     batch_preset.step.data.completed_items (number).
#   scenario_plans_saved:
#     count steps where (name='scenario_simulate_and_save' AND
#     step.data.scenario_id) PLUS (name='multi_plan_compare' AND
#     step.data.winner_scenario_id AND len(step.data.ranked) >= 2).
#   rag_chunks_indexed:
#     rag_index_subset.step.data.total_chunks.
#
# Renders each tile as <Card><CardContent>{value or '—'}</CardContent></Card>
# in `grid grid-cols-5 gap-3`.

# ─────────────────────────────────────────────────────────────────────────
# Task 15 — InspectArtifactsPanel.tsx
# ─────────────────────────────────────────────────────────────────────────

# frontend/src/components/demo/InspectArtifactsPanel.tsx (NEW)
# 10 deep-link cards in `grid grid-cols-2 lg:grid-cols-5 gap-4`. Each
# card: page name + one-line "what's new here after this run" detail.
# Disabled+tooltip when the required id is missing from step.data.
#
# Map of (label, href fn, dataDependency):
#   Forecast (V1+V2 ready):
#     href = ROUTES.VISUALIZE.FORECAST?store_id={store}&product_id={prod}
#     deps = train.step.data.store_id, .product_id (or summary)
#   Backtest with horizon buckets:
#     href = ROUTES.VISUALIZE.BACKTEST?store_id={...}&product_id={...}
#     deps = same
#   Portfolio sweep:
#     href = ROUTES.VISUALIZE.BATCH/{batch_id}
#     deps = batch_preset.step.data.batch_id
#   Saved scenario plans:
#     href = ROUTES.VISUALIZE.PLANNER (with optional ?scenario_id={...})
#     deps = scenario_simulate_and_save.step.data.scenario_id
#   Multi-run registry:
#     href = ROUTES.EXPLORER.RUNS
#     deps = always available (runs are always registered)
#   V2 Feature Frame panel:
#     href = ROUTES.EXPLORER.RUNS/{v2_run_id}
#     deps = summary.v2_run_id (from pipeline_complete) OR v2_train.step.data.run_id
#   Champion-compat "Not comparable":
#     href = ROUTES.EXPLORER.RUN_COMPARE?a={v1}&b={v2}
#     deps = champion_compat_compare.step.data.{a_run_id, b_run_id}
#   Stale-alias + Model Health:
#     href = ROUTES.OPS
#     deps = always available
#   Indexed corpus + search probe:
#     href = ROUTES.KNOWLEDGE
#     deps = rag_index_subset.step.data.total_chunks > 0
#   Agent transcript:
#     href = ROUTES.CHAT
#     deps = agent_hitl_flow.step.data.session_id

# ─────────────────────────────────────────────────────────────────────────
# Task 16 — RunHistoryStrip.tsx
# ─────────────────────────────────────────────────────────────────────────

# frontend/src/components/demo/RunHistoryStrip.tsx (NEW)
# Mirrors admin.tsx's localStorage pattern:
#
#   const STORAGE_KEY = 'forecastlab.showcase.runs.v1'
#   interface RunHistoryItem { id, runId, timestamp, scenario, status,
#                              wallClockS }
#
#   const loadHistory = (): RunHistoryItem[] => {
#       if (typeof window === 'undefined') return []
#       try {
#           const raw = window.localStorage.getItem(STORAGE_KEY)
#           return raw ? JSON.parse(raw) : []
#       } catch { return [] }
#   }
#
#   const saveHistory = (items: RunHistoryItem[]) => {
#       if (typeof window === 'undefined') return
#       try {
#           window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
#       } catch { /* quota exceeded — silently drop */ }
#   }
#
#   export function RunHistoryStrip({ onReplay, lastRun }: {
#       onReplay: (req: DemoRunRequest) => void
#       lastRun: DemoSummary | null
#   }) {
#       const [items, setItems] = useState<RunHistoryItem[]>(() => loadHistory())
#       useEffect(() => {
#           // Persist lastRun on pipeline_complete (parent re-renders us).
#           if (!lastRun || !lastRun.overallStatus) return
#           const newItem: RunHistoryItem = { ... }
#           const next = [newItem, ...items].slice(0, 5)
#           setItems(next)
#           saveHistory(next)
#       }, [lastRun])
#       return (
#           <Card><CardContent>
#               <ul>
#                   {items.map((item) => (
#                       <li key={item.id}>
#                           {item.timestamp} · {item.scenario} ·
#                           {item.wallClockS.toFixed(0)}s · {item.status}
#                           <Button size="sm" onClick={() => onReplay({
#                               scenario: item.scenario,
#                               skip_seed: false,
#                               reset: false,
#                           })}>Replay</Button>
#                       </li>
#                   ))}
#               </ul>
#           </CardContent></Card>
#       )
#   }

# ─────────────────────────────────────────────────────────────────────────
# Task 18 — RUNBOOKS.md extension
# ─────────────────────────────────────────────────────────────────────────

# docs/_base/RUNBOOKS.md
# MODIFY the "Showcase page (/showcase) pipeline fails at step X" section.
# ADD entries (numbered to continue the existing list):
#
#   - agent_hitl_flow step shows ⏭️ "no API key matching agent_default_model
#     provider" — expected when no LLM key. Pipeline still goes green. Fix:
#     set OPENAI_API_KEY/ANTHROPIC_API_KEY/GOOGLE_API_KEY (per provider).
#   - agent_hitl_flow step shows ⏭️ "approval timed out — pipeline continued"
#     — the pipeline auto-approved after 3s display delay but the approval
#     round-trip exceeded 90s. Cause: agent retry / network hang. Fix: check
#     uvicorn logs for the session_id; pipeline still green.
#   - agent_hitl_flow step shows ⏭️ "agent did not trigger save_scenario" —
#     the agent answered the prompt without invoking the gated tool. Cause:
#     model picked a different tool / answered directly. Fix: re-run; the
#     pipeline still goes green.
#   - ops_snapshot step shows ⚠️ "/ops/* all 4xx/5xx — ops snapshot
#     unavailable" — all three /ops/* endpoints failed. Cause: DB
#     unreachable. Fix: docker compose ps; pipeline still warn (not fail).
#   - Stop button clicked during a run — the WS closes, asyncio.Lock
#     releases. Page returns to 'idle' within 5s. To resume, click Run again.

# ─────────────────────────────────────────────────────────────────────────
# Task 19 — showcase-walkthrough.md cleanup
# ─────────────────────────────────────────────────────────────────────────

# docs/user-guide/showcase-walkthrough.md
# REMOVE every "(planned)" / "— planned (PRP-XX)" marker for behaviour
# this epic now delivers. The file currently has ~12 such markers.
#
# ADD prose blocks (with screenshot placeholders `<!-- screenshot:
# kpi-strip.png -->`) for:
#   - Phase: Agents (HITL) — 1-2 paragraphs.
#   - Phase: Ops snapshot — 1-2 paragraphs.
#   - KPI strip + Inspect-Artifacts panel — paired prose + deep-link table.
#   - Run-history strip — usage notes.
#   - Stop button — usage notes.
#
# Performance budget block: update "Performance budgets (planned)" →
# "Performance budgets" with concrete numbers (showcase_rich ≤ 240s,
# HITL ≤ 90s, per-step ≤ 120s).
#
# R6 callout (VITE_API_BASE_URL=http://localhost:8123 gotcha) stays
# explicit and prominent.
```

### Integration Points

```yaml
DATABASE:
  - No new tables. No Alembic migration in PRP-41.

CONFIG:
  - No new settings. PRP-41 reads existing
    settings.agent_default_model + per-provider API keys via
    _llm_key_present() (no new env vars).

ROUTES:
  - No new HTTP routes. PRP-41 extends app/features/demo/pipeline.py
    (a helper module, not a route) and consumes existing routes on
    the agents + ops slices.

SCHEMAS:
  - No new schema files. PRP-41 only adds keys inside the existing
    StepEvent.data: dict[str, Any]:
      Backend → wire:
        agent_hitl_flow.step.data: session_id, awaiting_approval,
          approval_url, action_id, approval_decision, tokens_used,
          tool_calls_count
        ops_snapshot.step.data: stale_aliases_count,
          retraining_candidates_count, total_runs, total_aliases,
          degrading_health_count

FRONTEND DEEP-LINKS:
  - agent_hitl_flow → ROUTES.CHAT
  - ops_snapshot    → ROUTES.OPS

PHASE_DEFS lockstep:
  - Backend: _phase_table() returns 24 tuples on SHOWCASE_RICH; the
    legacy 11-tuple base on DEMO_MINIMAL is updated to use
    (PHASE_AGENTS, "agent") if Task 1 picks design Y/Z.
  - Frontend: PHASE_DEFS.ts ALL_STEPS carries the swap + insert.
    phaseDefsForScenario('demo_minimal') still filters to 11.

LOCALSTORAGE:
  - Key: forecastlab.showcase.runs.v1
  - Cap: 5 entries (FIFO)
  - Wrapped reads in try/except; SSR-guarded with
    `typeof window === 'undefined'`.
```

---

## Validation Loop

### Level 1: Syntax + style + types

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/
uv run pyright app/
# Expected: zero errors (xgboost stub gap is pre-existing on dev).
```

### Level 2: Backend unit + integration tests

```bash
# Per-step unit suite (fast, no DB):
uv run pytest -v -m "not integration" app/features/demo/tests/test_pipeline.py

# Integration test (DB + showcase_rich end-to-end):
docker compose up -d
uv run alembic upgrade head
uv run pytest -v -m integration tests/test_e2e_demo.py
# Expected: wall-clock ≤ 240 s for showcase_rich (D7).
```

### Level 3: Frontend lint + types + tests

```bash
cd frontend
pnpm lint
pnpm tsc --noEmit -p tsconfig.app.json    # CRITICAL — project-scoped
pnpm test --run

# Expected: zero TS errors, all vitest suites pass (incl. lockstep
# tuple list 24-row count and the 5 new Inspect-Artifacts + KPI strip
# + Stop button + Approve button + onValueChange tests).
```

### Level 4: Vertical-slice grep guard

```bash
# MUST be empty (PRP-41 never imports across feature slices):
git grep -nE "from app\.features\.(agents|ops|registry|scenarios|rag)" \
  app/features/demo/

# Confirm the new step functions live in pipeline.py only (no new
# files under app/features/demo/):
ls app/features/demo/
# Expected: only existing files (pipeline.py / routes.py / schemas.py
# / service.py + tests/) — no new top-level files.
```

### Level 5: Dogfood the running UI

(Manual — see "Final validation Checklist" below.)

---

## Final validation Checklist

- [ ] All five validation gates green (`ruff` / `ruff format` /
      `mypy --strict` / `pyright --strict` / `pytest`) — **D9**.
- [ ] `git grep` vertical-slice guard returns no rows.
- [ ] `pnpm tsc --noEmit -p tsconfig.app.json` clean (do NOT trust prior
      HANDOFF; cf. R7).
- [ ] Backend test `test_phase_table_showcase_rich_emits_24_steps` (or
      equivalently-named replacement of the 23-step test) passes.
- [ ] Frontend test `PHASE_DEFS.test.ts` passes (matching 24-row list
      for showcase_rich).
- [ ] `git grep -nE "planned|TBD|TODO" docs/user-guide/showcase-walkthrough.md`
      shows no in-scope hits — **D6**.

### Manual dogfood (PRP-41 + full 16-line epic dogfood)

After running `/showcase` end-to-end on a fresh DB with
`scenario=showcase-rich`:

- [ ] **D1** — Top KPI strip shows 5 populated tiles.
- [ ] **D2** — Inspect-Artifacts panel renders all 10 deep-link cards
      post-`pipeline_complete`.
- [ ] **D3** — Approve button is rendered on `agent_hitl_flow` step
      card when `awaiting_approval=true`; clicking advances within 3 s.
- [ ] **D4** — Stop button cancels an in-flight run; page returns to
      'idle' within 5 s.
- [ ] **D5** — RunHistoryStrip persists the run; Replay re-fills the
      controls.
- [ ] **D6** — No "planned" markers remain in the walkthrough doc.
- [ ] **D7** — Wall-clock ≤ 240 s.
- [ ] **D8** — Lockstep tests (backend + frontend) green.
- [ ] **D9** — CI green.
- [ ] **D10** — Phase accordion unlocks after `pipeline_complete`;
      clicking any later phase header expands it normally.
- [ ] `/visualize/forecast` — Train card available; V1/V2 toggle
      reachable.
- [ ] `/visualize/backtest` — RMSE tile populated; horizon-bucket
      card renders per-bucket metrics.
- [ ] `/visualize/batch` — the just-created batch appears in the list
      with `completed_items` > 0.
- [ ] `/visualize/planner` — saved scenario plan visible; multi-plan
      compare ranks two plans.
- [ ] `/explorer/runs` — ≥ 4 runs registered.
- [ ] `/explorer/runs/{v2_prophet_run_id}` — V2 Feature Frame panel
      renders.
- [ ] `/explorer/runs/compare?a={v1}&b={v2}` — champion-compat badge
      reads "Not comparable".
- [ ] `/ops` — stale-alias card + Model Health table populated.
- [ ] `/knowledge` — 5 indexed user-guide docs visible; semantic
      search returns hits.
- [ ] `/chat` — agent session with the approved `save_scenario` tool
      call visible.
- [ ] Skip-gracefully: with all LLM keys unset, `agent_hitl_flow`
      emits ⏭️ skip; pipeline still goes green.
- [ ] Approve double-fire: clicking Approve before the 3 s auto-
      approve fires causes a single 200 + a silent backend
      4xx-absorption; the step still emits PASS.

---

## Anti-Patterns to Avoid

- ❌ Do NOT add `from app.features.agents.X import ...` (or
  ops / registry / scenarios / rag) anywhere in `app/features/demo/`.
  Drive every call over `httpx.ASGITransport`.
- ❌ Do NOT widen the `agent_require_approval` allow-list. PRP-41
  consumes the existing `save_scenario` entry; never adds new ones.
- ❌ Do NOT modify PRP-38/39/40 step functions or their `step.data`
  payload shapes. PRP-41 reads them; modification breaks the KPI
  strip and Inspect-Artifacts contracts.
- ❌ Do NOT use absolute phase indexes ("insert at row 12"). Use
  RELATIVE anchors ("insert IMMEDIATELY BEFORE the cleanup phase
  row").
- ❌ Do NOT block on a stuck `/approve` call. The 90 s hard timeout
  is load-bearing — without it a hung agent stops the whole demo.
- ❌ Do NOT log full prompts / responses / API-key values in any
  HITL step logging. Key NAMES + counts only, per
  `.claude/rules/security-patterns.md`.
- ❌ Do NOT bump `StepEvent` schema. New payload fields ride inside
  `StepEvent.data: dict[str, Any]`; no version key change.
- ❌ Do NOT add a new shadcn primitive. Card / Button / Badge /
  Accordion / Checkbox cover every use case.
- ❌ Do NOT persist run history server-side. localStorage only
  (parent epic's "NOT Option C" call).
- ❌ Do NOT skip the `onValueChange` fix on `DemoPhasePanel` — D10
  is a load-bearing acceptance criterion (the post-run UX assumes
  free panel toggling).
- ❌ Do NOT weaken `app/features/featuresets/tests/test_leakage.py` —
  leakage spec stays load-bearing across the whole epic.
- ❌ Do NOT add managed-cloud SDK code to the demo slice. Single-
  host vision is a hard constraint.
- ❌ Do NOT bundle CRLF→LF line-ending normalisation into this PRP.
  Memory anchor [[repo-line-endings-crlf]] applies.

---

## Confidence

**Confidence: 7 / 10** for one-pass implementation success.

Strengths:
- Every cited contract verified field-for-field by the four parallel
  research agents (HITL approval surface, ops endpoints + schemas, demo
  slice patterns, frontend showcase surfaces). Task 1's contract probe
  is incremental, not from scratch.
- The pattern for `step_agent_hitl_flow` is precedented by
  `step_register`'s multi-call multi-PATCH shape — and by `step_agent`'s
  graceful-skip baseline.
- The pattern for `step_ops_snapshot` is straightforward (3 GETs +
  derive 5 keys); the 200-safe-on-empty-DB property is verified by an
  existing integration test (`test_summary_resilient_structural`).
- The frontend lockstep contract is enforced by an existing test pair
  (`PHASE_DEFS.test.ts` + `test_phase_table_…`).
- `useWebSocket.disconnect()` already exists — the Stop button is a
  tiny wrapper.
- localStorage pattern already in use in `admin.tsx`.

Risks (and why confidence is not 8+):
- **R5 multi-event semantics (design Z)** — the `_Client.yield_event`
  hook is the load-bearing design choice. If the implementer
  misinterprets it (e.g. yields directly from the step fn return), the
  orchestrator never emits the intermediate event and the frontend
  never sees `awaiting_approval=true`. Task 1 MUST verify the
  orchestrator-fill-in works (step_index, phase_index, phase_total
  injected by the orchestrator when draining the sink).
- **Approve double-fire** (frontend pre-empt vs auto-approve) — the
  4xx absorption logic depends on the server returning a 4xx (not 200)
  on a duplicate approve. Task 1 verifies the exact response shape
  (`AgentService.approve_action` at `service.py:640`).
- **demo_minimal phase rename trade-off** — three design options
  (X / Y / Z). The PRP recommends Z but the lockstep test fixture
  will catch any drift; the implementer MUST follow the recommendation
  AND update both the backend lockstep test and the frontend test fixture
  in the same PR.
- **Two new frontend components × four state shapes each** (KPI strip,
  Inspect-Artifacts panel, RunHistoryStrip, Approve button) — coverage
  by 5 vitest suites; the missing-key fallback paths (R16/R17) are
  prone to silent regressions without those tests.

Mitigations baked in:
- Task 1 contract probe verifies every cited contract before
  implementation (including the design Z multi-event orchestrator
  validation).
- 7 backend tests (happy + skip + timeout + double-fire-absorb +
  ops happy + ops empty + lockstep flip).
- 5 frontend tests for the new components + 1 for DemoPhasePanel
  onValueChange.
- Vertical-slice grep guard blocks accidental cross-slice imports.
- Memory anchors `[[repo-line-endings-crlf]]`, `[[scenario-run-id-vs-
  registry-run-id]]`, `[[planner-ui-dogfood-findings]]`,
  `[[shadcn-cli-version-pin]]` documented in Known Gotchas for the
  implementer to reference.
- Dogfood checklist explicitly covers the D1–D10 surface plus the
  inherited dogfood items from PRP-38/39/40.

---

## Unresolved Contract Assumptions

1. **`_Client.yield_event` orchestrator-fill-in semantics.** The
   recommended design Z assumes the orchestrator (`run_pipeline`)
   fills in `step_index`, `phase_index`, `phase_total` on intermediate
   events drained from the sink. The step function itself cannot
   set them (it doesn't know its own index). The PRP's Task 3
   pseudocode shows the orchestrator drain happening "BEFORE the
   terminal step_complete" — but it leaves the question of WHO sets
   the index fields. **Recommendation: the orchestrator overwrites
   `step_index = index`, `total_steps = total`, `phase_index =
   phase_index_by_phase[phase_name]`, `phase_total = phase_total`
   on every event drained from the sink, just before yielding it.**
   Task 1 MUST verify this overwrite logic doesn't break the existing
   PRP-39 + PRP-40 events (none currently use the sink, so overwrite
   is a no-op on them).

2. **Approve double-fire response shape.** When the frontend's
   `/approve` call lands first, the backend's `/approve` call comes
   second and should return a 4xx (probably 400 "action not found"
   because the action_id was consumed). The exact status code +
   problem detail shape is implementation-specific to
   `AgentService.approve_action` — Task 1 MUST POST `/approve` twice
   in succession against a real session and record the exact response
   to verify the 4xx-absorption logic. If the second call returns
   200 (idempotent), the PRP's "executed" optimistic default is fine;
   if 4xx, the absorption catches `400 <= exc.status_code < 500`.

3. **`SHOWCASE_RICH_STEP_NAMES` filter semantics.** PHASE_DEFS.ts
   filters ALL_STEPS by step name to produce per-scenario phase defs.
   PRP-41 adds `'agent_hitl_flow'` + `'ops_snapshot'` to the set;
   `'agent'` (the legacy step name) stays OUT of the showcase_rich
   set so demo_minimal still sees `'agent'` and showcase_rich sees
   `'agent_hitl_flow'`. **Task 1 confirms the filter expression
   shape** (is it `ALL_STEPS.filter(s => SHOWCASE_RICH_STEP_NAMES.has(s.step))`
   or `ALL_STEPS.filter(s => !SHOWCASE_RICH_STEP_NAMES.has(s.step) ||
   scenario==='showcase_rich')`?). The pattern under design Z requires
   the filter to KEEP `'agent'` on demo_minimal AND `'agent_hitl_flow'`
   on showcase_rich — verify which selector achieves this.

4. **`OpsSummaryResponse.runs.counts` shape.** The PRP's `step_ops_snapshot`
   computes `total_runs = sum(c["count"] for c in summary["runs"]["counts"])`.
   Task 1 verifies the exact path (is it `runs.counts` or `runs.histogram`?)
   and the per-item key (`count` vs `value`). The `OpsService.get_summary`
   integration test exists; reading its assertion is the fastest path
   to ground truth.

5. **The `_Client.request` body wrapper for list responses.** Confirmed:
   `_Client.request` wraps non-dict 2xx bodies as `{"_raw": body}`. The
   three `/ops/*` endpoints all return dict bodies (verified field-for-
   field by Research Agent 2), so `_raw` does not come into play for
   PRP-41. If a future endpoint refactor returns a list body, the wrapper
   already handles it (verified pattern in PRP-40's
   `_embedding_provider_reachable`).
