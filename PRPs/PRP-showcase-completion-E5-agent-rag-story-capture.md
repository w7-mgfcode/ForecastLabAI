name: "PRP — Showcase Completion E5: Agent/HITL + RAG Story Capture (issue #411)"
description: |

## Purpose

Implement Parallel epic E5 of the showcase-completion initiative (umbrella #406):
persist the HITL approval story (decision approved/rejected/timed_out, action ids,
tool-call summary, transcript summary) into the workspace row's `approval_events`
slot; add a **Reject** button to the Showcase HITL step card alongside Approve —
and make both genuinely clickable by streaming the intermediate
`awaiting_approval` event DURING the decision window (today it flushes only after
the step ends, so the button can never render in time); render approval history
on Showcase and `/ops`; capture RAG events (probe/index/retrieve with provider
state) into `rag_events`; and mark on replay whether the knowledge/agent story
was reproduced. Capture is warn-and-continue — it must never fail a green
pipeline. **No widening of `agent_require_approval`. No agents-slice changes.**

## Core Principles

1. **Context is King**: every reference below was verified against live code on 2026-06-12 (branch `dev` @ `bdf85f6`).
2. **Validation Loops**: each level is executable as written.
3. **Information Dense**: patterns cite exact file:line.
4. **Progressive Success**: hitl relay module → pipeline capture → workspace writes → routes → frontend → tests → docs.
5. **Global rules**: follow CLAUDE.md / AGENTS.md; all five CI gates must pass; all changes ADDITIVE.

---

## ⛔ BLOCKED BY — E1 #407 (Foundation)

This epic writes the `approval_events` + `rag_events` JSONB story slots that the
E1 migration (`PRPs/PRP-showcase-completion-E1-metadata-provenance-backbone.md`)
creates, reads `replayed_from_workspace_id` for the reproduction marker, and
follows E1's frozen Decisions (slot-per-column, soft references, documented slot
schema, `config_schema_version` bump rule). **Do not start until E1 #407 is
merged to `dev`.** Verify before branching:

```bash
gh issue view 407 --json state          # must be CLOSED
grep -n "approval_events\|rag_events\|replayed_from_workspace_id" app/features/demo/models.py
# all three column names must exist on ShowcaseWorkspace
```

If E1 landed with deviations from its PRP (column names, slot shapes, response
fields), **the merged code wins** — re-anchor the blueprint below to it.

---

## Goal

A `showcase_rich` keep-run records its agent and knowledge story on the
workspace row, the operator can genuinely approve OR reject the HITL action
from the step card, and the story is visible afterwards:

- **`approval_events` capture**: `step_agent_hitl_flow` appends one entry per
  resolved approval (operator approve, operator reject, window-lapse
  auto-approve, hard timeout) carrying the E1-frozen base keys plus E5's
  documented additive keys (auto_approved, reason, execution_status,
  tool_call_summary, transcript_summary, tokens_used, tool_calls_count).
  `finalize_workspace` writes the list to the row (warn-and-continue).
- **`rag_events` capture**: the three knowledge steps
  (`embedding_provider_probe`, `rag_index_subset`, `rag_retrieve_probe`) append
  one entry each — event kind, status, detail, count, provider state, timestamp.
- **Interactive Reject (and a real Approve)**: a new in-demo decision relay —
  `POST /demo/hitl-decision` + a single-slot in-memory store — makes the
  PIPELINE the sole caller of `/agents/sessions/{id}/approve`. The step card's
  Approve/Reject buttons relay operator intent through the demo slice; the
  pipeline forwards the real decision to the agents HITL gate. The decision
  window grows 3 s → 10 s so a human can actually click.
- **Timely intermediate events**: `run_pipeline` drains the intermediate-event
  sink concurrently with the in-flight step (today it drains only after the
  step returns — `pipeline.py:2701-2715` — so the FE sees `awaiting_approval`
  only after the auto-approve already fired).
- **Approval history surfaces**: `GET /demo/approval-events` flattens recent
  workspaces' `approval_events` newest-first; the `/ops` page renders it as an
  "Approval History" table (frontend-only — no ops-slice backend change); the
  Showcase loaded-workspace view renders the full story (approval events + RAG
  events + reproduction marker).
- **Replay reproduction marker**: on a replay keep-run
  (`replayed_from_workspace_id` set), `finalize_workspace` compares the source
  row's story slots against the new run's capture and records
  `result_summary.story_reproduction = {"agent": ..., "knowledge": ...,
  "source_workspace_id": ...}` with values
  `reproduced | not_reproduced | not_applicable | unknown`.

A run/request without the new surfaces behaves byte-identically (ephemeral
runs, `demo_minimal`/`sparse` runs, legacy WS frames). **No Alembic migration**
— E1 shipped every column E5 touches.

**Deliverable** (all additive):

- `app/features/demo/hitl.py` — NEW single-slot in-memory decision relay
  (register / wait / resolve / clear), safe under the single-flight pipeline lock.
- `app/features/demo/pipeline.py` — DemoContext `approval_events`/`rag_events`
  accumulators; `step_agent_hitl_flow` rework (decision window, relay wait,
  reject path, event entry); RAG-event appends in the three knowledge steps;
  concurrent intermediate-event drain in `run_pipeline`.
- `app/features/demo/workspace.py` — `finalize_workspace` writes both slots +
  `story_reproduction`; NEW `list_approval_events` helper.
- `app/features/demo/schemas.py` — `HitlDecisionRequest`,
  `ApprovalEventItem`, `ApprovalEventsResponse`.
- `app/features/demo/routes.py` — `POST /demo/hitl-decision`,
  `GET /demo/approval-events`.
- `app/features/demo/models.py` — `config_schema_version` ORM default 1 → 2
  (slot-shape delta; E1 Decision 6 rule) + slot-schema comment delta.
- Frontend — `HitlDecisionButtons` (Approve + Reject) on the step card;
  `WorkspaceStoryPanel` on Showcase; "Approval History" section on `/ops`;
  `use-approval-events` hook; types.
- Tests: hitl-relay unit tests, HITL-step path tests, drain-ordering test,
  RAG-event capture tests, route tests, finalize/reproduction integration
  tests, FE component/hook tests.
- Docs: `docs/_base/API_CONTRACTS.md`, `docs/_base/DOMAIN_MODEL.md` (slot-schema
  v2 delta), `docs/_base/RUNBOOKS.md` (HITL incidents 23-25 + workspace section).

**Success definition**: all Success Criteria below check off; five CI gates
green; integration suite green; a manual `showcase_rich` keep-run lets the
operator click **Reject** within the 10 s window, the run stays green, the
workspace row carries the rejected `approval_events` entry + three `rag_events`
entries, `/ops` lists the event, and a Replay of that workspace records a
`story_reproduction` marker.

## Why

- Umbrella #406 success criterion: "HITL approval decisions (approve AND the
  new Reject path) and RAG events are captured on the workspace row and
  rendered as history on Showcase and /ops".
- The workspace row today records WHAT a run created but not the agent/HITL or
  knowledge STORY — the demo's most distinctive moments are unrecoverable
  after the run ends (RUNBOOKS § Showcase workspace, "Explicitly out of scope":
  "RAG-event and approval-decision capture on the workspace row" — this epic).
- The PRP-41 Approve button is effectively decorative: the intermediate
  `awaiting_approval` event is buffered in a plain list that `run_pipeline`
  drains only AFTER the step function returns (`pipeline.py:2660-2715`), and the
  step auto-approves after a 3 s sleep — so the browser learns about the
  approval window only once it has closed. E5's Reject button is meaningless
  without fixing this.
- No approval audit trail exists anywhere today: `AgentService.approve_action`
  clears `pending_action`, logs, and returns — nothing durable records the
  decision (`app/features/agents/service.py:825-907`). E5 is the first capture
  (brainstorm Round 5, `.flow/brainstorm-log.md`).

## What

### User-visible behavior

- The HITL step card on `/showcase` (scenario `showcase_rich`) shows **Approve**
  and **Reject** buttons while awaiting, with a live "auto-approve in Ns"
  countdown (10 s window). Either click resolves the action; no click
  auto-approves at window end. A reject keeps the pipeline GREEN — the step
  passes with detail `rejected by operator`, and the gated `save_scenario`
  never executes (no scenario_plan row is written).
- `POST /demo/hitl-decision` accepts `{action_id, decision: "approved"|"rejected",
  reason?}`; `404 application/problem+json` when no matching action is pending;
  `409` when the action was already decided; `422` on a malformed body.
- `GET /demo/approval-events?limit=N` returns recent approval events flattened
  across saved workspaces, newest-workspace-first; `200` + empty list when none.
- The `/ops` page gains an "Approval History" card (table: decision badge, tool,
  workspace, transcript snippet, when). The Showcase loaded-workspace view gains
  a story panel: approval events, RAG events (with provider state), and — on
  replay rows — a "story reproduced / not reproduced" marker.
- Ephemeral runs and `demo_minimal` / `sparse` runs are unchanged; legacy WS
  start frames are byte-identical (no new request fields on `DemoRunRequest`).

### Technical requirements

- **No agents-slice changes.** The pipeline remains the only writer of the
  approve POST in the showcase path; `agent_require_approval` is untouched;
  no agents migration, no `AgentSession` column. (The durable per-session
  approval audit is deliberately deferred — see Decisions D8.)
- **No Alembic migration** — E1 (#407) shipped `approval_events`, `rag_events`,
  `replayed_from_workspace_id`, `config_schema_version`.
- **Warn-and-continue invariant**: all capture writes ride inside the existing
  `finalize_workspace` try/except (`workspace.py:147-154`); a capture failure
  must never break a green run. ctx accumulators always append in-memory (cheap,
  cannot fail); only the DB write is fallible.
- **Single-flight safety**: the in-memory decision relay is correct because at
  most one pipeline runs per process (`service.py:19` `_pipeline_lock`) and the
  HITL step registers at most one pending action per run. The relay is
  module-level state in the demo slice (precedent: `_pipeline_lock`).
- **Vertical slice**: all backend changes inside `app/features/demo/`; the
  `/ops` approval-history surface is FRONTEND-ONLY (the ops page queries the
  demo endpoint — no ops-slice import of demo code, no cross-slice edge).
- RFC 7807 errors only — `NotFoundError` / `ConflictError` from
  `app/core/exceptions.py` (demo routes precedent, `routes.py:34,76,134`).
- Pydantic v2 `ConfigDict(strict=True, extra="forbid")` on `HitlDecisionRequest`
  (HTTP-only body; all fields JSON-native → no `Field(strict=False)`; the AST
  policy walker `app/core/tests/test_strict_mode_policy.py` only fires on
  date/datetime/time/UUID/Decimal).
- `StepEvent` data additions are additive dict keys only (legacy clients ignore
  unknown keys — the WS forward-compat contract).

### Success Criteria

- [ ] `run_pipeline` yields buffered intermediate events while the step is
  still executing: an orchestrator-level test proves the `awaiting_approval`
  event is received BEFORE the HITL step's terminal `step_complete` in wall
  time (not just stream order).
- [ ] Operator approve within the window → approve POST `approved=true`,
  `approval_events` entry `decision="approved"`, `auto_approved=false`.
- [ ] Operator reject within the window → approve POST `approved=false`, step
  terminal `pass` with detail `rejected by operator`, entry
  `decision="rejected"` (+ optional `reason`), pipeline green, NO scenario_plan
  row written by the agent.
- [ ] No decision → auto-approve at 10 s, entry `decision="approved"`,
  `auto_approved=true`. Hard timeout (90 s) → entry `decision="timed_out"`,
  step skips (existing semantics preserved).
- [ ] Each knowledge step appends exactly one `rag_events` entry on every
  outcome path (pass / warn / skip / auth-skip), carrying `provider` state.
- [ ] `finalize_workspace` writes both slots (NULL when empty — never `[]`),
  and on a replay row writes `result_summary.story_reproduction` with the
  documented values incl. `unknown` for a dangling source.
- [ ] `POST /demo/hitl-decision`: 204 happy path; 404 no-pending; 409
  already-decided; 422 bad body (problem+json each).
- [ ] `GET /demo/approval-events`: 200 + empty list on empty table; flattened
  entries carry `workspace_id` / `workspace_name`.
- [ ] FE: Reject button renders alongside Approve, both POST the demo relay via
  `lib/api.ts` `api()` (not bare `fetch`), countdown reads
  `data.decision_window_s`; `/ops` Approval History table renders; Showcase
  story panel renders events + reproduction marker.
- [ ] Legacy byte-compat: `DemoRunRequest` unchanged; `demo_minimal`/`sparse`
  emit no relay events and write no slots; `config_schema_version` ORM default
  is 2 (new rows) while old rows keep 1.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy app/
  && uv run pyright app/ && uv run pytest -v -m "not integration"` green;
  integration suite green; `cd frontend && pnpm lint && pnpm test --run` green
  with no NEW `tsc -b` errors vs the dev baseline.

## Decisions (the open questions this PRP resolves)

> Frozen for execution. E7 (release gate) authors: consume, don't re-decide.

1. **D1 — Decision relay: the pipeline is the SOLE approver.** The FE buttons
   POST `/demo/hitl-decision` (demo slice, in-memory single-slot store); the
   HITL step waits on the relay up to the window, then POSTs
   `/agents/sessions/{id}/approve` with the operator's decision (or
   `approved=true` on window lapse). Rationale: `approve_action` persists NO
   decision record (`agents/service.py:868-871` clears `pending_action`, logs,
   returns), so the PRP-41 pattern — FE pre-empts the agents endpoint directly
   and the pipeline absorbs the 4xx as "executed" (`pipeline.py:2357-2366`) —
   cannot distinguish an FE approve from an FE reject. Routing intent through
   the demo slice gives the pipeline ground truth with zero agents-slice
   changes and zero migrations. The 4xx-absorb stays as belt-and-braces for an
   operator curl-ing `/agents/.../approve` directly mid-run (recorded as
   `decision="approved"`, `execution_status="external_4xx"` — honest about the
   residual ambiguity).
2. **D2 — Concurrent intermediate-event drain in `run_pipeline`.** Replace
   `await fn(ctx, client)` with `task = asyncio.ensure_future(fn(ctx, client))`
   + a `while` loop that `asyncio.wait({task}, timeout=0.25)` and flushes the
   sink each tick (stamping index/phase fields exactly as the existing
   post-step drain does, `pipeline.py:2707-2714`). This is NOT a pipeline
   re-architecture: steps still run strictly one at a time under the same lock;
   only event flushing overlaps the in-flight step. The post-step drain block
   stays (final flush). Exception mapping moves to `task.result()` inside the
   same try/except ladder (`pipeline.py:2681-2699`).
3. **D3 — Decision window 10 s.** `_APPROVAL_DISPLAY_DELAY_S = 3.0`
   (`pipeline.py:317`) is replaced by `_APPROVAL_DECISION_WINDOW_S = 10.0`.
   3 s is unclickable by a human; 10 s keeps the showcase brisk (well under the
   90 s hard timeout and the 180 s soft budget) and is emitted to the FE as
   `data.decision_window_s` so the countdown never hardcodes it.
4. **D4 — Slot-schema delta ⇒ `config_schema_version` ORM default 1 → 2.**
   E5 widens the E1-frozen `approval_events.decision` enum
   (`"approved"|"rejected"` → `+"timed_out"`), adds additive entry keys, and
   adds `"probe"` to the `rag_events.event` enum + additive keys. Per E1
   Decision 6 ("any epic that changes a documented slot shape bumps the ORM
   default and documents the delta") this is a bump; E3's PRP explicitly does
   NOT bump (its CONTRACT(E1) note: populating verbatim ≠ shape change), so no
   collision is expected — but if another parallel epic bumped first, take the
   next integer and update DOMAIN_MODEL accordingly. ORM `default=` only —
   `server_default` stays `text("1")` (no migration; old rows legitimately
   read 1).
5. **D5 — Reject keeps the pipeline GREEN.** A human rejection is a SUCCESSFUL
   demonstration of the HITL gate, not an error: terminal `("pass", "rejected
   by operator", {..., "approval_decision": "rejected"})`. Only transport/5xx
   failures keep the existing skip semantics. `step_cleanup` still closes the
   session either way.
6. **D6 — Approval history endpoint lives in the DEMO slice.** "Render on
   /ops" is a frontend statement: the ops PAGE queries
   `GET /demo/approval-events`. Putting the endpoint in the ops slice would
   force a cross-slice demo import for data the demo slice owns
   (`showcase_workspace.approval_events`). Flattening is Python-side over the
   newest ≤50 rows with a non-NULL slot — a low-cardinality audit table; no
   `jsonb_array_elements` SQL needed.
7. **D7 — Reproduction marker lives in `result_summary`** (an existing
   demo-owned JSONB whose shape is not E1-frozen), NOT a new column and not a
   slot entry: `{"story_reproduction": {"agent": V, "knowledge": V,
   "source_workspace_id": str}}` with `V ∈ reproduced | not_reproduced |
   not_applicable | unknown`. `agent`: source row had ≥1 approval event →
   compare with the new run (`reproduced`/`not_reproduced`); source had none →
   `not_applicable`; source row missing (soft reference dangles) → `unknown`.
   `knowledge`: same logic over `rag_events` entries whose `event` is
   `index`/`retrieve` with `status != "skip"`. Computed inside
   `finalize_workspace` (one extra `get`-by-id select in the same session,
   inside the existing warn-and-continue try).
8. **D8 — No durable approval audit on `agent_session` (deferred).** The
   architecturally complete fix (an `approval_history` JSONB on the agents
   aggregate) needs an agents migration + schema surface — out of this epic
   per the umbrella approach ("additive-only delta on the existing demo +
   seeder slices") and the epic's own scope line ("No widening of
   agent_require_approval"; agents untouched). If E7 review wants it, it is a
   follow-up issue, not scope creep here.

### Assumptions (explicit, decided without user input)

- `tool_call_summary` carries `{"description": str, "arguments_keys":
  list[str]}` from `pending_action` — argument KEYS only, never values
  (security-patterns.md: never echo full payloads; values may embed
  user-supplied text).
- `transcript_summary` is the agent's chat `message` truncated to 200 chars
  (precedent: the #335 failure-detail 300-char cap).
- The relay rejects decisions for an `action_id` that is not the registered
  one with 404 (not 409): a mismatched id is "nothing pending under that id".
- `GET /demo/approval-events` scans the newest 50 workspace rows with a
  non-NULL slot and caps the flattened list at `limit` (1-200, default 50).
  No offset/pagination — audit-glance surface, not a browse API.
- The live-run Showcase surface for history is the step card itself (terminal
  detail + `HitlFlowSummary`); the story PANEL renders for loaded workspaces.
- FE buttons disable after either click; 404/409 responses are absorbed
  silently (the auto-approve raced) — same UX contract as the PRP-41 button.

## All Needed Context

### Documentation & References

```yaml
# MUST READ — codebase patterns (verified 2026-06-12, dev @ bdf85f6)

- file: PRPs/PRP-showcase-completion-E1-metadata-provenance-backbone.md
  why: |
    THE frozen upstream contract: slot columns + per-slot documented schemas
    (approval_events / rag_events base keys), Decision 2 (slot-per-column),
    Decision 5 (E5 writes these two slots), Decision 6 (config_schema_version
    bump rule), and "Notes for parallel-epic PRP authors" (warn-and-continue
    for pipeline-time slot writes; HTTP writes go through caller-owned-session
    helpers). Re-verify the merged code matches before relying on line numbers.

- file: app/features/demo/pipeline.py
  why: |
    THE file you rework. _Client.__init__ event_sink @136-155 and
    yield_event @163-174 (plain-list sink, silently dropped when None);
    DemoContext @213-263 (PRP-41 approval fields @254-257 — the comment style
    your new accumulator fields follow); _llm_key_present @289;
    HITL constants @314-322 (_APPROVAL_DISPLAY_DELAY_S=3.0 @317 — replaced;
    _APPROVAL_HARD_TIMEOUT_S=90.0 @318 — kept; _HITL_PROMPT @319);
    _embedding_provider_reachable @390; _is_embedding_auth_error @431;
    step_embedding_provider_probe @1449-1468; step_rag_index_subset
    @1471-1525 (note the auth-skip path @1493-1501); step_rag_retrieve_probe
    @1528-1576 (warn-on-zero-hits @1552-1560); step_agent_hitl_flow
    @2192-2394 (every outcome path you extend — skip-no-key @2222, skip-no-
    pending @2269, intermediate event @2295-2318, display sleep @2320-2324,
    hard-timeout @2326-2341, approve POST + 4xx absorb @2343-2377, terminal
    @2381-2394); _phase_table @2528 (knowledge steps @2589-2593, agents step
    @2560-2564 — registry unchanged in E5); run_pipeline @2618-2771
    (intermediate_events buffer @2660-2663, step await + except ladder
    @2681-2699, post-step drain @2701-2715 — THE BLOCK D2 generalizes,
    finalize hook @2744-2747).

- file: app/features/demo/workspace.py
  why: |
    finalize_workspace @106-155 — the warn-and-continue write you extend with
    the two slot assignments + story_reproduction (whole-value assignment,
    inside the existing try). get_workspace @158-171 (reuse the select shape
    for the source-row read INSIDE finalize's own session — do NOT call
    get_workspace, it takes a caller-owned session). list_workspaces @174-196
    — the newest-first select your list_approval_events mirrors (add
    .where(ShowcaseWorkspace.approval_events.isnot(None))).
    CONTRACT in module docstring @10-13: create/finalize swallow all errors.

- file: app/features/demo/service.py
  why: |
    _pipeline_lock @19 — the single-flight guarantee that makes the in-memory
    relay safe. PipelineBusyError @22 + the 409 mapping (routes.py:74-77) —
    the error-translation pattern the hitl-decision route mirrors.

- file: app/features/demo/routes.py
  why: |
    Router you extend. delete_showcase_workspace @138-163 — NotFoundError
    shape; run_demo_pipeline @74-77 — ConflictError shape; list_showcase_
    workspaces @80-107 — Query(ge/le) param + list response shape for
    GET /demo/approval-events; WS handler @166-194 (unchanged in E5).

- file: app/features/demo/schemas.py
  why: |
    DemoRunRequest @29-85 (UNCHANGED in E5 — no new request fields);
    StepEvent @88-127 (data is dict[str, Any] — additive keys free);
    WorkspaceListItem @169-189 / WorkspaceDetailResponse @192-203 — E1 adds
    the slot fields to Detail; E5 only READS them. New models follow the
    response-model split: plain BaseModel, from_attributes only where built
    from ORM rows (ApprovalEventItem is built from dicts — no from_attributes).

- file: app/features/demo/models.py
  why: |
    ShowcaseWorkspace — after E1: config_schema_version (ORM default you bump
    to 2), approval_events / rag_events slot columns + the documented
    per-slot schema comments (extend with the E5 delta; DOMAIN_MODEL carries
    the authoritative copy).

- file: app/features/agents/schemas.py
  why: |
    PendingAction @170-190 (action_id / action_type / description / arguments
    — the tool_call_summary source); ApprovalRequest @192-206 (action_id,
    approved: bool, reason ≤500 — REJECT ALREADY EXISTS in the agents API;
    the pipeline just sends approved=false); ApprovalResponse @208+ (status:
    "executed"|"rejected"|"expired" — mapped into execution_status; NOTE an
    approved-but-failed execution also reports "rejected", see
    frontend/src/lib/approval-report.ts:10-16).

- file: app/features/agents/service.py
  why: |
    approve_action @825-907 — READ ONLY: proves no decision is persisted
    (pending_action cleared @868, status → ACTIVE @869, returns the response)
    and that a consumed action raises NoApprovalPendingError → the 400 the
    4xx-absorb handles. DO NOT MODIFY (D8).

- file: app/features/demo/tests/test_pipeline.py
  why: |
    _make_hitl_client @1838-1921 — THE fake-client harness for HITL step
    tests; extend it (approve body capture, decision injection).
    test_agent_hitl_flow_happy_path @1959 + the FOUR monkeypatches of
    _APPROVAL_DISPLAY_DELAY_S @1973/2047/2063/2081 — every one must move to
    _APPROVAL_DECISION_WINDOW_S (set 0.0 so tests don't sleep). Phase-table
    test @629-674 pins the 24-row layout (unchanged).

- file: app/features/demo/tests/conftest.py
  why: |
    client fixture (ASGITransport, monkeypatched-service unit route tests) +
    db_session fixture (integration; wipes showcase_workspace on teardown) —
    reuse both; do not invent new fixtures.

- file: frontend/src/components/demo/demo-step-card.tsx
  why: |
    ApproveButton @371-421 — REPLACED by HitlDecisionButtons. Note the bare
    relative fetch(approvalUrl) @393 — only works when SPA origin == API
    origin; the replacement MUST use lib/api.ts api() (API_BASE_URL-prefixed,
    frontend/src/lib/api.ts:3,23-26). Render condition @496-505 (keep shape;
    swap component). HitlFlowSummary mount @494.

- file: frontend/src/pages/showcase.tsx
  why: |
    Page wiring: loadedWorkspace detail query @128-131; WorkspaceArtifacts
    Panel mount @448-450 — mount WorkspaceStoryPanel beside it (same
    `phase !== 'running' && loadedWorkspace` guard). handleReplayWorkspace
    @174-186 (E1 adds replayed_from_workspace_id here — E5 does not touch it).

- file: frontend/src/pages/ops.tsx
  why: |
    "Needs Attention" section @394-446 — THE Card+Table pattern (empty-state
    paragraph, StatusBadge, formatWhen) the Approval History section mirrors.
    Place the new section directly after Needs Attention.

- file: frontend/src/hooks/use-workspaces.ts + frontend/src/hooks/use-ops.ts
  why: |
    TanStack patterns: queryKey arrays, api<T>() calls, refetchInterval
    choices. use-approval-events.ts mirrors useWorkspaces (no polling — the
    table changes only when a run finishes; document that in the hook docstring
    like useRetrainingCandidates does).

- file: frontend/src/types/api.ts
  why: |
    StepEvent @760 / DemoRunRequest @778 / WorkspaceListItem @806 /
    WorkspaceDetail @819 — add ApprovalEventItem / ApprovalEventsResponse and
    (if E1 did not already) the WorkspaceDetail slot fields E5 reads
    (approval_events, rag_events). Comment style: `// E5 (#411) — ...`.

- file: frontend/src/lib/approval-report.ts
  why: |
    Documents the executed/rejected/expired semantics of ApprovalResponse
    (incl. approved-but-execution-failed → "rejected") — the mapping
    execution_status follows.

- file: docs/_base/DOMAIN_MODEL.md
  why: |
    § showcase_workspace — E1 documents the frozen slot schemas; E5 appends
    the v2 delta (decision enum widening, additive keys, "probe" event,
    story_reproduction in result_summary) and the config_schema_version=2
    note. Authoritative slot-schema copy lives HERE.

- file: docs/_base/RUNBOOKS.md
  why: |
    Incidents 23-25 (agent_hitl_flow) — update for the 10 s window, the
    Reject path, and the relay endpoint; § Showcase workspace — trim
    "RAG-event and approval-decision capture" from the out-of-scope list.

- file: PRPs/PRP-showcase-completion-E3-seed-config-scope.md
  why: |
    Parallel-epic coordination: E3 also extends DemoContext and touches
    create_workspace-time writes. Expect textual merge conflicts in
    DemoContext / workspace.py if E3 lands first — both additions are
    independent; resolve by keeping both blocks. E3's CONTRACT(E1) note
    (line 1031) confirms E3 does NOT bump config_schema_version — E5 does (D4).

# Issue / initiative context
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/411
  why: The epic this PRP implements.
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/406
  why: Umbrella — success criteria, out-of-scope list, warn-and-continue risk row.
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/407
  why: Foundation epic (BLOCKING) — frozen column/slot/endpoint contract.

# Exemplar PRPs (style + validation-gate conventions)
- file: PRPs/PRP-41-showcase-agent-ops-polish.md
  why: Authored the HITL step + intermediate-event sink E5 reworks.
- file: PRPs/ai_docs/prp-41-contract-probe-report.md
  why: Verified agents HITL contracts (chat pending_approval shape, approve 400 on consumed action).
```

### Current Codebase tree (relevant subset, post-E1)

```bash
app/features/demo/
├── models.py          # ShowcaseWorkspace + E1 columns (approval_events/rag_events/config_schema_version/replayed_from_workspace_id)
├── pipeline.py        # _Client sink @136; DemoContext @213; HITL constants @314; knowledge steps @1449-1576; step_agent_hitl_flow @2192; run_pipeline @2618
├── workspace.py       # create @46; finalize @106; get @158; list @174; delete @199; count @224 (+ E1 update_workspace)
├── schemas.py         # DemoRunRequest @29; StepEvent @88; Workspace* @169-213 (+ E1 WorkspaceUpdateRequest, slot fields on Detail)
├── routes.py          # POST /run @51; GET/PATCH/DELETE /workspaces @80-163; WS /stream @166
├── service.py         # _pipeline_lock @19 (UNCHANGED)
└── tests/             # conftest, test_models, test_pipeline (_make_hitl_client @1838), test_routes, test_schemas, test_workspace
frontend/src/
├── components/demo/demo-step-card.tsx   # ApproveButton @371; render condition @496
├── components/demo/WorkspaceArtifactsPanel.tsx
├── pages/showcase.tsx                   # loadedWorkspace @128; panels @244-450
├── pages/ops.tsx                        # Needs Attention table @394-446
├── hooks/use-workspaces.ts / use-ops.ts
├── lib/api.ts                           # api<T>() @23 (API_BASE_URL @3)
└── types/api.ts                         # StepEvent @760; Workspace* @806-830
```

### Desired Codebase tree (files added/modified)

```bash
app/features/demo/
├── hitl.py                       # NEW — single-slot decision relay (register/wait/resolve/clear)
├── pipeline.py                   # MOD — ctx accumulators; HITL step rework; rag-event appends; D2 drain
├── workspace.py                  # MOD — finalize slot writes + story_reproduction; NEW list_approval_events
├── schemas.py                    # MOD — HitlDecisionRequest; ApprovalEventItem; ApprovalEventsResponse
├── routes.py                     # MOD — POST /hitl-decision; GET /approval-events
├── models.py                     # MOD — config_schema_version ORM default 2; slot-comment delta
└── tests/
    ├── test_hitl.py              # NEW — relay unit tests (asyncio)
    ├── test_pipeline.py          # MOD — HITL paths, rag capture, drain-ordering, constant rename
    ├── test_routes.py            # MOD — hitl-decision 204/404/409/422; approval-events 200
    ├── test_schemas.py           # MOD — HitlDecisionRequest (+ JSON path); response models
    └── test_workspace.py         # MOD — finalize slots + story_reproduction (integration)
frontend/src/
├── components/demo/demo-step-card.tsx      # MOD — HitlDecisionButtons (Approve+Reject, api(), countdown)
├── components/demo/demo-step-card.test.tsx # MOD — Reject render + POST body
├── components/demo/WorkspaceStoryPanel.tsx       # NEW — approval + rag events + reproduction marker
├── components/demo/WorkspaceStoryPanel.test.tsx  # NEW
├── components/demo/index.ts                # MOD — export
├── pages/showcase.tsx                      # MOD — mount WorkspaceStoryPanel
├── pages/ops.tsx                           # MOD — Approval History section
├── hooks/use-approval-events.ts            # NEW — useApprovalEvents
├── hooks/use-approval-events.test.ts       # NEW
├── hooks/index.ts                          # MOD — export
└── types/api.ts                            # MOD — ApprovalEventItem/Response (+ Detail slot fields if E1 didn't)
docs/_base/API_CONTRACTS.md                 # MOD — 2 endpoints + WS data-key notes
docs/_base/DOMAIN_MODEL.md                  # MOD — slot-schema v2 delta + story_reproduction
docs/_base/RUNBOOKS.md                      # MOD — HITL incidents + out-of-scope trim
```

### Known Gotchas & Library Quirks

```python
# CRITICAL — intermediate events flush only AFTER the step returns today
#   (run_pipeline drains the list sink post-await, pipeline.py:2701-2715).
#   PRP-41's Approve button therefore never renders during the window. D2's
#   concurrent drain is LOAD-BEARING for this whole epic — implement and test
#   it FIRST (Task 3) or every FE-interaction test downstream is meaningless.

# CRITICAL — the relay wait must use asyncio primitives, not polling sleeps:
#   asyncio.wait_for(event.wait(), timeout=...) raises TimeoutError on lapse
#   (stdlib-verified 2026-06-12:
#   uv run python -c "import asyncio
#   async def m():
#       ev=asyncio.Event()
#       async def r(): await asyncio.sleep(0.05); ev.set()
#       t=asyncio.ensure_future(r())
#       await asyncio.wait_for(ev.wait(), timeout=1.0); print(True); await t
#   asyncio.run(m())"  -> True).

# CRITICAL — warn-and-continue: ALL new finalize_workspace logic (slot writes,
#   source-row read, story_reproduction) goes INSIDE the existing try block
#   (workspace.py:126-146). Never add a second commit path; never let a
#   malformed source row raise out.

# CRITICAL — JSONB whole-value assignment: build the full list on ctx, then
#   row.approval_events = ctx.approval_events or None. NEVER append to a
#   loaded row's JSONB in place (invisible to SQLAlchemy without
#   flag_modified). Empty list -> None (E1: NULL = "slot never written").

# CRITICAL — the relay is process-global mutable state. It is safe ONLY
#   because service._pipeline_lock enforces one run at a time. Guard anyway:
#   register() overwrites any stale slot (a crashed run must not wedge the
#   next one) and the step clears it in a finally block.

# CRITICAL — do NOT modify app/features/agents/** (D8) and do NOT touch
#   agent_require_approval. The reject path is expressed entirely through the
#   EXISTING ApprovalRequest.approved=false contract (agents/schemas.py:192).

# GOTCHA — FE ApproveButton today uses bare fetch(approvalUrl) with a
#   RELATIVE url (demo-step-card.tsx:393) — breaks when VITE_API_BASE_URL
#   points off-origin. HitlDecisionButtons must use api() from lib/api.ts.

# GOTCHA — tests monkeypatch pipeline._APPROVAL_DISPLAY_DELAY_S at FOUR
#   sites: test_pipeline.py:1973, 2047, 2063, 2081. Renaming the constant
#   without sweeping all four fails loudly (monkeypatch.setattr
#   AttributeError). The "auto-approve in 3 s" detail string lives only in
#   pipeline.py:2306 (no test asserts it); the FE countdown copy at
#   demo-step-card.tsx:415 computes from the 90 s HARD timeout, not the
#   window — replace it with the decision_window_s countdown.
#   Grep "_APPROVAL_DISPLAY_DELAY_S\|auto-approve in" before renaming.

# GOTCHA — StepEvent attribute stamping (ev.step_index = index) relies on
#   Pydantic validate_assignment being OFF (default) — existing production
#   behavior (pipeline.py:2708); keep the drained-event stamping identical.

# GOTCHA — D2's task wrapper changes exception flow: _StepError raised inside
#   the step now surfaces from task.result(). Keep the EXACT except ladder
#   (_StepError -> fail / httpx.HTTPError|OSError -> transport fail /
#   Exception -> unexpected fail).
#   CRITICAL sub-case: the Stop button closes the WebSocket -> the async
#   generator is CLOSED, which throws **GeneratorExit** (a BaseException) into
#   the frame at D2's new mid-step `yield ev` suspension point. Neither
#   `except asyncio.CancelledError` nor `except Exception` catches it, so the
#   in-flight step task would be orphaned ("Task was destroyed but it is
#   pending") with the _Client context exiting underneath it. The drain loop
#   MUST therefore sit inside `try/finally: if not task.done(): task.cancel()`
#   — cancellation on ANY exit (GeneratorExit, CancelledError, or a raise),
#   never only on CancelledError. Verify the Stop path by hand in Level 4.

# GOTCHA — parallel-epic merge friction: E3 (#409) extends DemoContext and
#   the create-time workspace write; E2/E4 may touch finalize for
#   job_ids/phase_summaries. All additions are disjoint — resolve conflicts
#   by keeping both hunks; re-run the full demo test file after any rebase.

# GOTCHA — repo has mixed CRLF/LF line endings; run `git diff --stat` before
#   committing (Edit/Write emit LF — whole-file noise diffs are a regression).

# GOTCHA — frontend type gate: `pnpm tsc --noEmit` is vacuous and `tsc -b`
#   already fails on dev with pre-existing errors. Gate on "no NEW errors vs
#   the dev baseline" + `pnpm lint` + `pnpm test --run`.

# GOTCHA — mypy --strict AND pyright --strict gate merge: full annotations
#   incl. `-> None` on tests, typed module-level relay state
#   (e.g. _slot: _PendingDecision | None), and dataclass field types.

# CONVENTION — branch: feat/showcase-completion-e5-agent-rag-story (off dev,
#   slug ≤50). Commits reference #411: feat(api): ... (#411) for slice code,
#   feat(ui): ... (#411) for frontend, docs(repo)/docs(docs): ... (#411).
#   NO AI trailer (hook-enforced).

# RUNTIME-VERIFICATION LOG (per prp-create step 3 — re-run on upgrade):
#   1. asyncio.Event + wait_for timeout semantics — verified 2026-06-12
#      (command above, prints True).
#   2. No NEW third-party API claims: httpx-ASGITransport step client,
#      SQLAlchemy JSONB whole-value writes, Pydantic strict-literal bodies,
#      and TanStack query/mutation shapes are all existing production code in
#      this repo (pipeline.py / workspace.py / schemas.py / use-workspaces.ts).
#   3. agents approve contract probed in PRPs/ai_docs/prp-41-contract-probe-
#      report.md (approved=false path + 400-on-consumed) — re-verify only if
#      the agents slice changes upstream.
```

## Implementation Blueprint

### Data shapes (documented slot-schema v2 — authoritative copy goes to DOMAIN_MODEL)

```python
# approval_events entry (list[dict], append-only). E1-frozen base keys first;
# E5 additive keys below the marker. decision enum WIDENED in v2.
{
    "action_id": str,
    "tool_name": str,                  # pending_action.action_type
    "decision": "approved" | "rejected" | "timed_out",
    "decided_at": str,                 # iso8601 UTC
    "session_id": str,
    # -- E5 (#411) additive, config_schema_version >= 2 --
    "auto_approved": bool,             # True when the window lapsed
    "reason": str | None,              # operator-supplied (Reject), <=500
    "execution_status": str | None,    # ApprovalResponse.status: executed|rejected|expired;
                                       # "external_4xx" on the absorbed pre-empt edge; None on timed_out
    "tool_call_summary": {"description": str, "arguments_keys": list[str]},
    "transcript_summary": str,         # agent chat message, <=200 chars
    "tokens_used": int,
    "tool_calls_count": int,
}

# rag_events entry (list[dict], append-only). "probe" event ADDED in v2.
{
    "event": "probe" | "index" | "retrieve" | "skip",
    "status": "pass" | "warn" | "skip",   # E5 additive
    "detail": str,
    "count": int,                      # chunks indexed / results returned / 0
    "occurred_at": str,                # iso8601 UTC
    "provider": str | None,            # E5 additive — embedding provider name
    "reachable": bool | None,          # E5 additive — probe only
}

# result_summary additive key (replay keep-runs only):
{"story_reproduction": {"agent": V, "knowledge": V, "source_workspace_id": str}}
# V ∈ "reproduced" | "not_reproduced" | "not_applicable" | "unknown"
```

```python
# app/features/demo/hitl.py — NEW. Single-slot in-memory decision relay.
# Safe because service._pipeline_lock enforces one pipeline per process and
# the HITL step registers at most one action per run (precedent for
# module-level state: service.py:19).
"""HITL decision relay for the showcase pipeline (E5, issue #411). ..."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Literal

Decision = Literal["approved", "rejected"]
ResolveOutcome = Literal["applied", "already_decided", "not_found"]

@dataclass
class _PendingDecision:
    action_id: str
    event: asyncio.Event = field(default_factory=asyncio.Event)
    decision: Decision | None = None
    reason: str | None = None

_slot: _PendingDecision | None = None   # module-level; one pipeline at a time

def register(action_id: str) -> None:
    """Open the decision window; overwrites any stale slot from a dead run."""
    global _slot
    _slot = _PendingDecision(action_id=action_id)

def resolve(action_id: str, decision: Decision, reason: str | None = None) -> ResolveOutcome:
    """Record the operator's decision; called by POST /demo/hitl-decision."""
    if _slot is None or _slot.action_id != action_id:
        return "not_found"
    if _slot.decision is not None:
        return "already_decided"
    _slot.decision = decision
    _slot.reason = reason
    _slot.event.set()
    return "applied"

async def wait_for_decision(action_id: str, timeout: float) -> tuple[Decision, str | None] | None:
    """Block up to ``timeout`` for an operator decision; None on lapse."""
    if _slot is None or _slot.action_id != action_id:
        return None
    try:
        await asyncio.wait_for(_slot.event.wait(), timeout=timeout)
    except TimeoutError:
        return None
    if _slot.decision is None:   # defensive: set() without decision
        return None
    return (_slot.decision, _slot.reason)

def clear() -> None:
    """Close the window (step's finally)."""
    global _slot
    _slot = None
```

```python
# app/features/demo/pipeline.py — DemoContext additions (after workspace_name,
# E3-comment style):
    # E5 (#411) -- story-capture accumulators. Appended by step_agent_hitl_flow
    # and the knowledge steps on SHOWCASE_RICH; finalize_workspace persists
    # them to the workspace slots (empty -> slot stays NULL).
    approval_events: list[dict[str, Any]] = field(default_factory=list)
    rag_events: list[dict[str, Any]] = field(default_factory=list)

# Constants — REPLACE _APPROVAL_DISPLAY_DELAY_S (line 317):
_APPROVAL_DECISION_WINDOW_S = 10.0   # D3 — operator decision window

# RAG-event helper (near the knowledge steps):
def _record_rag_event(ctx, *, event, status, detail, count=0, provider=None, reachable=None) -> None:
    ctx.rag_events.append({... per the v2 shape, "occurred_at": datetime.now(UTC).isoformat()})
# Call once on EVERY return path of the three knowledge steps:
#   probe   -> event="probe",   status="pass", provider=, reachable=
#   index   -> event="index"|"skip", count=total_chunks
#   retrieve-> event="retrieve"|"skip", status="warn" on zero hits, count=results_count
# (provider for index/retrieve: reuse the probe's provider via a ctx echo or
#  re-read get_settings().rag_embedding_provider — settings read is simplest.)

# step_agent_hitl_flow rework (between the intermediate event and terminal):
#   - intermediate event data ADDS: "decision_window_s": _APPROVAL_DECISION_WINDOW_S
#     and "decision_url": "/demo/hitl-decision"; detail becomes
#     f"awaiting approval (auto-approve in {int(_APPROVAL_DECISION_WINDOW_S)} s)"
#   - hitl.register(action_id) BEFORE yielding the intermediate event;
#     try/finally hitl.clear() around everything after registration.
#   - replace the sleep @2320-2324 with:
#       remaining = max(0.0, _APPROVAL_DECISION_WINDOW_S - (time.monotonic() - started_at))
#       operator = await hitl.wait_for_decision(action_id, timeout=remaining)
#   - keep the hard-timeout check @2326-2341; on timed_out ALSO append the
#     approval_events entry (decision="timed_out", execution_status=None).
#   - approved = operator is None or operator[0] == "approved"
#     reason = operator[1] if operator else None
#     POST /approve with {"action_id": ..., "approved": approved,
#     **({"reason": reason} if reason else {})}
#   - 4xx absorb stays; record execution_status="external_4xx" on that edge.
#   - append the approval_events entry on EVERY resolved path, then terminal:
#       reject -> ("pass", "rejected by operator", {..., "approval_decision": "rejected"})
#       approve -> existing pass shape (+ "auto_approved" key in data)

# run_pipeline D2 drain — replace `status, detail, data = await fn(ctx, client)`
# (and its except ladder) with:
    task = asyncio.ensure_future(fn(ctx, client))
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=0.25)
            for ev in intermediate_events:           # same stamping as today
                ev.step_index = index; ev.total_steps = total
                ev.phase_index = phase_index; ev.phase_total = phase_total
                ev.phase_name = phase_name
                yield ev                              # NEW suspension point —
                                                      # generator close lands HERE
            intermediate_events.clear()
            if done:
                break
        status, detail, data = task.result()
    except _StepError as exc: ...                    # EXACT existing ladder
    finally:
        # LOAD-BEARING (quality-gate Finding 3): the Stop button closes the
        # async generator, throwing GeneratorExit (BaseException) into the
        # mid-step `yield ev` above — no except clause sees it. The finally
        # is the ONLY hook that runs on every exit path; without it the
        # in-flight step task is orphaned while _Client closes under it.
        if not task.done():
            task.cancel()
# The existing post-task drain block @2701-2715 stays as the final flush.
```

```python
# app/features/demo/workspace.py — inside finalize_workspace's try, after
# row.result_summary assignment (@141-145):
            row.approval_events = ctx.approval_events or None   # E5 (#411)
            row.rag_events = ctx.rag_events or None
            summary: dict[str, Any] = {... existing three keys ...}
            if row.replayed_from_workspace_id:                  # D7 marker
                src = (await db.execute(select(ShowcaseWorkspace).where(
                    ShowcaseWorkspace.workspace_id == row.replayed_from_workspace_id
                ))).scalar_one_or_none()
                summary["story_reproduction"] = _story_reproduction(src, ctx)
            row.result_summary = summary

def _story_reproduction(src: ShowcaseWorkspace | None, ctx: DemoContext) -> dict[str, Any]:
    """D7 — compare the source row's story slots against this run's capture."""
    if src is None:
        return {"agent": "unknown", "knowledge": "unknown",
                "source_workspace_id": None}
    def _verdict(source_had: bool, new_has: bool) -> str:
        if not source_had: return "not_applicable"
        return "reproduced" if new_has else "not_reproduced"
    src_knowledge = any(e.get("event") in ("index", "retrieve") and e.get("status") != "skip"
                        for e in (src.rag_events or []))
    new_knowledge = any(e.get("event") in ("index", "retrieve") and e.get("status") != "skip"
                        for e in ctx.rag_events)
    return {
        "agent": _verdict(bool(src.approval_events), bool(ctx.approval_events)),
        "knowledge": _verdict(src_knowledge, new_knowledge),
        "source_workspace_id": src.workspace_id,
    }

async def list_approval_events(db: AsyncSession, *, limit: int = 50) -> list[dict[str, Any]]:
    """Flatten approval_events across the newest rows that carry the slot."""
    result = await db.execute(
        select(ShowcaseWorkspace)
        .where(ShowcaseWorkspace.approval_events.isnot(None))
        .order_by(ShowcaseWorkspace.created_at.desc(), ShowcaseWorkspace.id.desc())
        .limit(50)
    )
    events: list[dict[str, Any]] = []
    for row in result.scalars():
        for entry in row.approval_events or []:
            events.append({"workspace_id": row.workspace_id,
                           "workspace_name": row.name, **entry})
            if len(events) >= limit:
                return events
    return events
```

```python
# app/features/demo/schemas.py — new models.
class HitlDecisionRequest(BaseModel):
    """Operator decision relay for the showcase HITL step (E5, #411). ..."""
    model_config = ConfigDict(strict=True, extra="forbid")
    action_id: str = Field(..., min_length=1, description="Pending action to decide.")
    decision: Literal["approved", "rejected"] = Field(..., description="Operator decision.")
    reason: str | None = Field(default=None, max_length=500,
                               description="Optional reason (mirrors agents ApprovalRequest.reason).")

class ApprovalEventItem(BaseModel):
    """One flattened approval event (built from JSONB dicts — tolerant typing)."""
    workspace_id: str
    workspace_name: str | None = None
    action_id: str | None = None
    tool_name: str | None = None
    decision: str | None = None
    decided_at: str | None = None
    session_id: str | None = None
    auto_approved: bool | None = None
    reason: str | None = None
    execution_status: str | None = None
    transcript_summary: str | None = None

class ApprovalEventsResponse(BaseModel):
    events: list[ApprovalEventItem]
    total: int   # number returned (flattened cap), not a table count
```

```python
# app/features/demo/routes.py — two routes.
@router.post("/hitl-decision", status_code=status.HTTP_204_NO_CONTENT,
             summary="Relay an operator decision to the in-flight HITL step", ...)
async def submit_hitl_decision(body: HitlDecisionRequest) -> None:
    outcome = hitl.resolve(body.action_id, body.decision, body.reason)
    if outcome == "not_found":
        raise NotFoundError(message=f"No pending HITL action: {body.action_id}")
    if outcome == "already_decided":
        raise ConflictError(f"Action already decided: {body.action_id}")

@router.get("/approval-events", response_model=ApprovalEventsResponse,
            summary="Recent HITL approval events across saved workspaces", ...)
async def list_hitl_approval_events(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
) -> ApprovalEventsResponse:
    events = await workspace.list_approval_events(db, limit=limit)
    return ApprovalEventsResponse(
        events=[ApprovalEventItem.model_validate(e) for e in events],
        total=len(events),
    )
```

```tsx
// frontend — HitlDecisionButtons replaces ApproveButton (demo-step-card.tsx):
//  - props: actionId, decisionWindowS (from step.data.decision_window_s ?? 10)
//  - api('/demo/hitl-decision', { method: 'POST', body: { action_id, decision } })
//    via lib/api.ts (NOT bare fetch); absorb 404/409 silently, surface 5xx.
//  - Approve: variant "default"; Reject: variant "destructive" + size "sm";
//    both disable after either click ("Approving…"/"Rejecting…").
//  - countdown: `auto-approve in ${remaining}s` ticking from decisionWindowS.
// WorkspaceStoryPanel (new): Card titled "Run story"; sections —
//  Approval history (decision StatusBadge + tool + transcript snippet + when),
//  Knowledge events (event/status/provider/count), Reproduction marker chips
//  (from result_summary.story_reproduction; render only when present).
//  Render nothing when the workspace has no slots (legacy rows).
// ops.tsx: "Approval History" Card+Table after Needs Attention, fed by
//  useApprovalEvents() (hooks/use-approval-events.ts; queryKey
//  ['demo','approval-events',limit]; no polling); empty-state paragraph.
```

### List of tasks (dependency order)

```yaml
Task 0 — preconditions:
  VERIFY: gh issue view 407 --json state -> CLOSED; the three E1 columns exist
    on ShowcaseWorkspace; re-anchor blueprint line numbers if E1/E3 moved code.
  RUN: git switch dev && git pull && git switch -c feat/showcase-completion-e5-agent-rag-story

Task 1 — CREATE app/features/demo/hitl.py:
  - IMPLEMENT the relay per blueprint (typed module state, register/resolve/
    wait_for_decision/clear, structlog on resolve)
  - CREATE tests/test_hitl.py: resolve-before-wait, wait-then-resolve,
    timeout->None, wrong-action->not_found, double-resolve->already_decided,
    register-overwrites-stale-slot, clear()

Task 2 — MODIFY app/features/demo/models.py:
  - config_schema_version ORM default 1 -> 2 (server_default UNCHANGED)
  - EXTEND the slot-schema comments with the v2 delta (blueprint shapes)

Task 3 — MODIFY pipeline.py run_pipeline (D2 drain) — FIRST pipeline change:
  - task wrapper + 0.25s asyncio.wait flush loop per blueprint; preserve the
    exact except ladder; `finally: if not task.done(): task.cancel()` so a
    generator close (Stop button -> GeneratorExit at the mid-step yield)
    never orphans the in-flight step task
  - ADD orchestrator tests: (a) a stub step that emits an intermediate event
    then blocks on an asyncio.Event; assert the intermediate event is yielded
    while the step is still pending, then release and assert terminal order;
    (b) close the generator (aclose()) while the stub step is in-flight and
    assert the step task ends cancelled (no "destroyed but pending" warning)

Task 4 — MODIFY pipeline.py HITL step + constants:
  - REPLACE _APPROVAL_DISPLAY_DELAY_S with _APPROVAL_DECISION_WINDOW_S = 10.0
    (sweep tests: monkeypatches @1973/2047/2063 + "auto-approve in 3 s" asserts)
  - DemoContext: + approval_events / rag_events accumulators (E5 comment block)
  - step_agent_hitl_flow: hitl.register before the intermediate event;
    intermediate data += decision_window_s + decision_url; wait_for_decision;
    reject path (approved=false POST, terminal pass "rejected by operator");
    approval_events entry on every resolved path (incl. timed_out);
    try/finally hitl.clear()
  - EXTEND _make_hitl_client: capture approve POST json_body; tests for
    operator-approve / operator-reject (resolve via hitl.resolve before the
    wait) / window-lapse auto-approve / hard-timeout entry / skip paths
    append nothing

Task 5 — MODIFY pipeline.py knowledge steps:
  - _record_rag_event helper + one call per return path of probe/index/retrieve
  - tests: each path appends the right entry (pass/skip/auth-skip/warn),
    provider populated, demo_minimal run leaves ctx.rag_events empty

Task 6 — MODIFY workspace.py:
  - finalize_workspace: slot writes + story_reproduction per blueprint
    (all inside the existing try); _story_reproduction helper
  - NEW list_approval_events helper
  - tests/test_workspace.py (@integration): finalize writes slots (and NULL
    when empty); replay row vs source-with-story -> reproduced; source-empty
    -> not_applicable; dangling source -> unknown; list_approval_events
    flattens newest-first and respects limit

Task 7 — MODIFY schemas.py + routes.py:
  - HitlDecisionRequest / ApprovalEventItem / ApprovalEventsResponse
  - POST /demo/hitl-decision (204/404/409) + GET /demo/approval-events
  - tests/test_schemas.py: JSON-dict path (security-patterns.md § strict mode):
    HitlDecisionRequest.model_validate({"action_id": "a", "decision": "rejected"});
    extra-key 422; bad decision literal 422; reason >500 422
  - tests/test_routes.py: decision 204 (hitl registered via monkeypatch/
    direct register) / 404 / 409 / 422; approval-events 200 empty + populated
    (monkeypatch workspace.list_approval_events for the unit-shaped test,
    follow the file's existing convention)

Task 8 — frontend:
  - types/api.ts: ApprovalEventItem/ApprovalEventsResponse (+ WorkspaceDetail
    approval_events/rag_events fields IF E1 didn't add them); `// E5 (#411)` comments
  - demo-step-card.tsx: HitlDecisionButtons per blueprint (replace
    ApproveButton; keep the @496-505 render condition shape); update
    demo-step-card.test.tsx (Reject renders, POST body, countdown text)
  - hooks/use-approval-events.ts + test; export from hooks/index.ts
  - components/demo/WorkspaceStoryPanel.tsx + test; export from index.ts;
    mount in showcase.tsx beside WorkspaceArtifactsPanel (@448-450 guard)
  - pages/ops.tsx: Approval History section after Needs Attention (@446),
    mirroring its Card+Table+empty-state pattern
  - GATES: pnpm lint && pnpm test --run; tsc -b no NEW errors

Task 9 — docs (additive):
  - API_CONTRACTS.md: two new demo rows (POST /demo/hitl-decision incl.
    204/404/409 semantics; GET /demo/approval-events); WS /demo/stream section:
    intermediate HITL event now streams DURING the window and data gains
    decision_window_s/decision_url; note the 10 s window and the Reject path
  - DOMAIN_MODEL.md § showcase_workspace: slot-schema v2 delta (decision enum,
    additive keys, "probe" event), config_schema_version=2 note,
    story_reproduction in result_summary
  - RUNBOOKS.md: incidents 23-25 — window now 10 s, Reject button exists, a
    rejected run is GREEN by design; § Showcase workspace — trim "RAG-event
    and approval-decision capture" from the out-of-scope list

Task 10 — gates, dogfood, PR:
  - full Validation Loop (Levels 1-4); git diff --stat (CRLF noise check)
  - COMMITS (reference #411, no AI trailer), e.g.:
      feat(api): add hitl decision relay and story capture to demo pipeline (#411)
      feat(ui): add reject button, run story panel and ops approval history (#411)
      docs(docs): document approval and rag story capture contracts (#411)
  - PR into dev; title:
      feat(api,ui): showcase-completion E5 — agent/hitl + rag story capture (#411)
```

### Integration Points

```yaml
DATABASE: none — no migration (E1 shipped the columns). ORM default bump only.
CONFIG: none — no new settings; the window is a module constant emitted to the FE.
ROUTES: two additions on the existing demo router — no app/main.py change.
AGENTS SLICE: untouched (D8). The pipeline keeps using the public
  /agents/sessions/{id}/approve contract (approved=true|false + reason).
OPS SLICE: untouched — /ops approval history is a frontend section over the
  demo endpoint.
FRONTEND: one replaced component, one new panel, one new ops section, one hook.
PARALLEL EPICS: E3 touches DemoContext + create-time writes; E2/E4 may write
  job_ids/phase_summaries in finalize — keep-both merge resolution; whoever
  lands after a slot-shape change rebases the config_schema_version default.
```

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
```

### Level 2: Unit Tests (no DB)

```bash
uv run pytest app/features/demo -v -m "not integration"
uv run pytest app/core/tests/test_strict_mode_policy.py -v
# Key new/updated cases (see Tasks 1,3,4,5,7):
#   test_hitl.py — relay semantics incl. timeout + already_decided
#   test_pipeline.py — drain-ordering (intermediate BEFORE step completion);
#     HITL operator-approve / operator-reject / auto-approve / timed-out
#     entries; reject terminal is pass + green; rag-event appends per path;
#     demo_minimal leaves both accumulators empty
#   test_routes.py — hitl-decision 204/404/409/422; approval-events 200
#   test_schemas.py — HitlDecisionRequest JSON path + extra=forbid
```

### Level 3: Integration (real Postgres)

```bash
docker compose up -d && uv run alembic upgrade head
uv run pytest app/features/demo -v -m integration
# test_workspace.py — finalize writes approval_events/rag_events (NULL when
# empty); story_reproduction matrix (reproduced / not_applicable / unknown);
# list_approval_events flatten + limit
```

### Level 4: Manual smoke (seeded local stack, uvicorn :8123 + vite)

```bash
# 1. showcase_rich keep-run from /showcase with "Save as workspace" ticked.
#    During the agents phase the HITL card must show Approve + Reject with a
#    ticking "auto-approve in Ns" — click REJECT. Expect: step flips to pass
#    with "rejected by operator"; run finishes GREEN.
# 2. Verify capture:
curl -s "http://localhost:8123/demo/approval-events?limit=5" | python3 -m json.tool
#    -> one entry, decision="rejected", workspace_id set
docker exec forecastlab-postgres psql -U forecastlab -d forecastlab -c \
  "SELECT name, jsonb_array_length(approval_events) AS approvals, \
          jsonb_array_length(rag_events) AS rag, config_schema_version \
   FROM showcase_workspace ORDER BY created_at DESC LIMIT 1;"
#    -> approvals=1, rag=3, config_schema_version=2
# 3. Decision relay error paths:
curl -s -X POST http://localhost:8123/demo/hitl-decision \
  -H 'Content-Type: application/json' \
  -d '{"action_id": "bogus", "decision": "approved"}' | python3 -m json.tool   # 404 problem+json
# 4. Replay the kept workspace (Replay button) and let it auto-approve; then:
#    GET /demo/workspaces/{new_id} -> result_summary.story_reproduction.agent
#    == "reproduced" (source had an approval event; replay produced one too).
# 5. /ops page shows the Approval History table; Showcase Load on the kept
#    workspace renders the story panel (events + reproduction chips).
# 6. Regression: run demo_minimal — no buttons, no relay calls, slots NULL.
```

## Final validation Checklist

- [ ] Five gates green: `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"`
- [ ] Integration suite green on a fresh docker-compose DB (reset first if the shared DB is polluted)
- [ ] Drain-ordering test proves intermediate events stream mid-step; Stop button still cancels cleanly (CancelledError passthrough)
- [ ] Reject path: green run, entry captured, no scenario_plan written by the agent
- [ ] Slots NULL on empty capture; `config_schema_version`=2 on new rows, old rows still 1
- [ ] `POST /demo/hitl-decision` 204/404/409/422 and `GET /demo/approval-events` verified (Levels 2+4)
- [ ] story_reproduction matrix covered (reproduced / not_reproduced / not_applicable / unknown)
- [ ] Frontend: `pnpm lint` + `pnpm test --run` green; no NEW `tsc -b` errors; manual browser pass (Level 4 steps 1, 5)
- [ ] No agents-slice diff; no migration; `git diff --stat` surgical (no CRLF noise)
- [ ] Docs updated (API_CONTRACTS, DOMAIN_MODEL v2 slot delta, RUNBOOKS trim)
- [ ] Commits `feat(api)/feat(ui)/docs(...): ... (#411)`, no AI trailer; PR into dev

---

## Anti-Patterns to Avoid

- ❌ Don't touch `app/features/agents/**` or `agent_require_approval` — the reject path uses the EXISTING `approved=false` contract (D1/D8).
- ❌ Don't let a reject (or any capture failure) fail the pipeline — reject is `pass`; capture rides warn-and-continue.
- ❌ Don't re-architect the pipeline beyond the D2 drain loop — steps stay strictly sequential under the single lock; no mid-run frame reading on the WS.
- ❌ Don't make the FE call `/agents/sessions/{id}/approve` directly anymore — the relay is the single intent channel (keep emitting `approval_url` for back-compat, but the buttons use the relay).
- ❌ Don't echo tool-call argument VALUES or full transcripts into `approval_events` — keys + 200-char summary only.
- ❌ Don't write `[]` into a slot — empty capture leaves the column NULL (E1: NULL = "never written").
- ❌ Don't add a migration or change `server_default` for the version bump — ORM `default=` only.
- ❌ Don't put the approval-history endpoint in the ops slice — demo owns the data; /ops renders client-side.
- ❌ Don't validate that the replay source row exists — dangles are designed; `unknown` is the honest verdict.
- ❌ Don't mutate row JSONB in place — whole-value assignment only.
- ❌ Don't add list pagination/filtering to approval-events — audit glance, not a browse API (E7 can extend).

## Notes for the release-gate epic (E7)

- E5 bumps the documented slot schema to v2 (D4) — the DOMAIN_MODEL delta is
  the authoritative copy; verify E2/E4/E6 didn't race the same default.
- The D2 drain generalizes intermediate-event streaming for ANY step — if a
  later epic wants mid-step progress (e.g. batch sub-job ticks), the plumbing
  now exists; document it if used.
- The deferred durable approval audit on `agent_session` (D8) is a candidate
  follow-up issue if the chat surface (non-showcase) needs history too.

## Confidence Score

**8/10** for one-pass implementation success. Every write path has a verified
in-repo precedent: the slot columns + warn-and-continue hook (E1/`workspace.py`),
the module-level single-flight state (`service.py:19`), the HITL step's fake-client
test harness (`test_pipeline.py:1838`), the agents `approved=false` contract
(`agents/schemas.py:192` — no agents change needed), and the ops Card+Table /
TanStack patterns. The two judgment calls with real risk are resolved and frozen:
D1 (relay; eliminates the unknowable FE-pre-empt decision) and D2 (concurrent
drain; the one structural change, contained to a single loop body with a
dedicated ordering test). The −2: (a) D2 touches the orchestrator's exception/
cancellation flow — the Stop-button path (`WebSocketDisconnect` → generator
close → CancelledError) must be re-verified by hand in Level 4; (b) this PRP is
written against E1's PRP rather than E1's merged code, and E3 may land in
parallel — Task 0's re-anchoring step and the keep-both merge note mitigate but
can't eliminate rebase friction.
