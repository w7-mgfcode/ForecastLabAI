# PRP-41 — Task 1 Contract Probe Report

> **Probed:** branch `feat/showcase-41-agent-ops-polish` (off `dev` at `58d593a`,
> which is the merge of PR #322 atop `b3ba1f4`). All citations verified
> field-for-field against current source — no live HTTP probe needed because
> every cited contract is determined by source (Pydantic models, route
> decorators, in-memory enums). Live `/ops/*` shape spot-checked against
> `OpsService.get_summary` source.
>
> **Verdict: GO — zero field-level drift. Four of five unresolved
> contract assumptions resolved by source inspection; one (#5) was
> already CONFIRMED in the PRP body. ONE wording patch required for
> PRP-41 Task 9 (filter restructure for design Z, see §7).**

---

## 1. Backend — agents slice (HITL approval surface)

### `app/features/agents/schemas.py`

| Symbol | Line | PRP cite | Live shape | Match |
|---|---|---|---|---|
| `SessionCreateRequest` | 27 | `agent_type: Literal["experiment","rag_assistant"]`, `initial_context: dict\|None` | `agent_type: Literal["experiment","rag_assistant"]`, `initial_context: dict[str, Any] \| None` | ✅ |
| `SessionResponse` | 45 | `session_id, agent_type, status, total_tokens_used, tool_calls_count, last_activity, expires_at, created_at` | exact same 8 fields | ✅ |
| `ChatRequest` | 108 | `message: str`, `stream: bool=False` | `message: str` + `stream: bool=False` | ✅ |
| `ChatResponse` | 145 | `session_id, message, tool_calls, pending_approval: bool, pending_action: PendingAction\|None, tokens_used: int` | exact match | ✅ |
| `PendingAction` | 170 | `action_id, action_type, description, arguments, created_at, expires_at` | exact match | ✅ |
| `ApprovalRequest` | 192 | `action_id: str` (NOT `tool_call_id`), `approved: bool`, `reason: str\|None` | exact match — `action_id` confirmed at line 203 | ✅ |
| `ApprovalResponse` | 208 | `action_id, approved, result: Any\|None, status: Literal["executed","rejected","expired"]` | exact match | ✅ |

**PRP wording drift in INITIAL-41 (already noted in PRP-41 body):**
- `tool_call_id` → `action_id` — PRP-41 body already corrected.
- `approval_required` event vs `pending_approval` field — PRP-41 body already corrected (the event only fires on `/agents/stream` WS path; the synchronous `/chat` REST response carries `pending_approval: bool` + `pending_action: PendingAction | None`).

### `app/features/agents/routes.py`

| Endpoint | Line | Body shape | Notes |
|---|---|---|---|
| `POST /agents/sessions` | 43 | `SessionCreateRequest` → `SessionResponse` (201 CREATED) | ✅ |
| `GET /agents/sessions/{id}` | 80 | `SessionResponse` | ✅ |
| `POST /agents/sessions/{id}/chat` | 109 | `ChatRequest` → `ChatResponse` | ✅ |
| `POST /agents/sessions/{id}/approve` | 152 | `ApprovalRequest` → `ApprovalResponse` | ✅ |
| `DELETE /agents/sessions/{id}` | 198 | `204 NO CONTENT` (already called by `step_cleanup`) | ✅ |

### `app/features/agents/agents/experiment.py`

- `tool_save_scenario` at **line 419** ✅
- Gated by `requires_approval("save_scenario")` at **line 453** + short-circuit at **line 468** ✅

### `app/features/agents/service.py`

- `approve_action` at **line 640** ✅
- Raises `SessionNotFoundError` → `HTTPException(404)` when session absent.
- Raises `NoApprovalPendingError` → `HTTPException(400)` when:
  - `session.pending_action is None` (already consumed) — **line 668**
  - `pending.action_id != action_id` (mismatch) — **line 672**
- After approving once, `session.pending_action = None` is set (line ~685), so a
  second `POST /approve` with the same `action_id` will get **400 Bad Request**
  with `detail="No pending action for session: {id}"`.

> ⚠️ **Note — RFC 7807 inconsistency** in agents/routes.py (lines 185–195): the
> raise paths use bare `HTTPException(status_code=..., detail=str(e))`, not the
> repo's `problem_details.py` envelope. `_Client.request` handles both formats
> via the `parsed if isinstance(parsed, dict)` fallback (pipeline.py line 173),
> so PRP-41 is unaffected. This is **pre-existing** and **out of PRP-41 scope.**

### `app/core/config.py`

- Line **184** — `agent_require_approval: list[str] = ["create_alias", "archive_run", "save_scenario"]` ✅ matches PRP-41 expectation. **`save_scenario` is in the list.** PRP-41 reads only; modifies nothing.

---

## 2. Backend — ops slice

### `app/features/ops/schemas.py`

| Symbol | Line | PRP cite | Live shape | Match |
|---|---|---|---|---|
| `StaleReason` | 16 | StrEnum w/ `newer_success_run`, `artifact_not_verified`, `run_not_success`, `feature_frame_version_mismatch` | exact match | ✅ |
| `SystemHealth` | 36 | n/a (consumed via `summary.system`) | `api_ok`, `database_connected`, `latest_successful_job_at` | ✅ |
| `DataFreshness` | 56 | n/a (consumed via `summary.freshness`) | matches | ✅ |
| `StatusCount` | 80 | `status: str`, `count: int` | exact match | ✅ |
| `JobHealth` | 89 | n/a | `counts, completed_today, failed_total, active_total` | ✅ |
| `RunHealth` | 111 | **`counts: list[StatusCount]`** | confirmed — `counts` (NOT `histogram`); each item carries `count` (NOT `value`) | ✅ |
| `AliasHealth` | 133 | `alias_name, run_id, is_stale, stale_reason, wape, alias_feature_frame_version, comparable_run_feature_frame_version` | match + `run_status`/`model_type`/`store_id`/`product_id` extras (additive — not used by PRP-41) | ✅ |
| `OpsSummaryResponse` | 209 | `system, jobs, runs, aliases: list[AliasHealth], freshness, attention_items, generated_at` — **NO flat `stale_aliases`/`total_aliases`** | exact match — must derive from `aliases` list | ✅ |
| `RetrainingCandidate` | 234 | `store_id, product_id, priority_score, staleness_days, wape, latest_run_id, reason` | match + `latest_run_status` (additive) | ✅ |
| `RetrainingCandidatesResponse` | 267 | `candidates, total_evaluated, generated_at` | exact match | ✅ |
| `DriftDirection` | 290 | `Literal["improving","stable","degrading","unknown"]` | exact match | ✅ |
| `ModelHealthEntry` | 306 | **`drift_direction`** (NOT `drift_verdict`) | confirmed line 338 — `drift_direction: DriftDirection` | ✅ |
| `ModelHealthResponse` | 372 | field is **`entries`** (NOT `health` / `items`) | confirmed line 377 — `entries: list[ModelHealthEntry]` | ✅ |

### `app/features/ops/routes.py`

| Endpoint | Line | Query params | Response | Match |
|---|---|---|---|---|
| `GET /ops/summary` | 22→41 | none | `OpsSummaryResponse` | ✅ |
| `GET /ops/retraining-candidates` | 55→70 | `limit=1..100` (default 20) | `RetrainingCandidatesResponse` | ✅ |
| `GET /ops/model-health` | 91→110 | `limit=1..100` (default 20) — **NO `grain` param** | `ModelHealthResponse` | ✅ |

### `app/features/ops/tests/test_routes_integration.py`

- `test_summary_resilient_structural` at **line 68** ✅ proves `GET /ops/summary` returns 200 (never 500) on an empty DB. `test_model_health_resilient_structural` at line 175 confirms the same for `/ops/model-health`. PRP-41's `step_ops_snapshot` can safely assume 200 with zero-filled fields.

---

## 3. Backend — demo slice (anchors for the new step fns)

### `app/features/demo/pipeline.py`

| Symbol | Line | Notes |
|---|---|---|
| `_HTTP_TIMEOUT` | 96 | `httpx.Timeout(120.0, connect=5.0)` — 120 s budget the new steps share. |
| `_StepError` | 104 | Has `.step`, `.status_code`, `.problem` attributes. **`status_code` confirmed** for the absorb-4xx logic. |
| `_Client` | 125 | Constructor `__init__(self, app: FastAPI)` — current signature has NO `event_sink` param. PRP-41 Task 3 extends it. |
| `_Client.request` | 152 | Returns `dict[str, Any]`; wraps non-dict 2xx bodies as `{"_raw": body}` (line 178); raises `_StepError(step, response.status_code, problem)` on any non-2xx. |
| `DemoContext` | 187 | Has `session_id`, `v2_run_id`, `scenario_artifact_key`, `price_cut_scenario_id`, `holiday_scenario_id`, `embedding_unreachable`. **NO `approval_action_id` / `agent_approval_decision`** — PRP-41 Task 2 adds them. |
| `_llm_key_present` | 253 | Bool helper; already used by `step_agent` line 1443. Mirror exactly. |
| `step_agent` (legacy) | 1436 | One-turn chat with `experiment` agent; skips on missing key. Replacement template for `step_agent_hitl_flow`. |
| `step_register` | 984 | Multi-call multi-PATCH precedent for `step_agent_hitl_flow`'s sequential pattern. |
| `step_cleanup` | 1897 | Already closes `ctx.session_id` via DELETE — PRP-41 changes nothing here. |
| `step_batch_preset` → `step.data.completed_items` | ~1820 | confirmed source of `completed_items` KPI tile. |
| `step_scenario_simulate_and_save` → `step.data.scenario_id` | ~1170 | confirmed (also sets `ctx.price_cut_scenario_id`). |
| `step_multi_plan_compare` → `step.data.{winner_scenario_id, ranked_by, ranked}` | ~1265 | confirmed; `ranked` is `list[dict]`. |
| `step_rag_index_subset` → `step.data.{total_chunks, curated_hits}` | ~1340 | confirmed. |
| `_phase_table` | 1999 | Current `SHOWCASE_RICH` branch returns **23 rows** (verified by `test_phase_table_showcase_rich_…` line 571). PRP-41 flips to 24 (swap `("agent","agent")` row + insert `("ops","ops_snapshot")`). |
| `PHASE_AGENT` constant | 1995 | `"agent"` — PRP-41 design Z **REPLACES** this with `PHASE_AGENTS = "agents"`. |
| `PHASE_CLEANUP` constant | 1996 | `"cleanup"` — unchanged. |
| `run_pipeline` | 2076 | Already computes `index`, `phase_index_by_phase[phase_name]`, `phase_total` per row (lines 2099–2102). **The orchestrator already knows these values** — Task 3's intermediate-event drain can stamp them on each yielded event. **Design Z is viable.** |

### `app/features/demo/routes.py`

- WS handler `/demo/stream` at lines 57–85; `WebSocketDisconnect` caught at **line 74** and returns silently — confirmed.

### `app/features/demo/service.py`

- `_pipeline_lock = asyncio.Lock()` at **line 18** ✅
- `if _pipeline_lock.locked(): raise PipelineBusyError(...)` at **line 38–39** ✅
- `async with _pipeline_lock:` at **line 41** — lock releases on exit which includes propagation of `WebSocketDisconnect`. **Stop button will release the lock correctly.**

---

## 4. Frontend — current state of every cited file

### `frontend/src/components/demo/PHASE_DEFS.ts`

- **`ALL_STEPS`** (lines 37–64) — 23 rows on `dev`. The legacy `{ phase: 'agent', step: 'agent', label: 'Agent chat' }` is at row 22 (1-indexed); cleanup at row 23.
- **`SHOWCASE_RICH_STEP_NAMES`** (lines 66–82) — currently 12 entries. **Semantics:** this set is the "EXCLUDE from demo_minimal" set, NOT the "include only in showcase_rich" set. The filter is:
  ```ts
  if (scenario === 'showcase_rich') return ALL_STEPS
  return ALL_STEPS.filter((d) => !SHOWCASE_RICH_STEP_NAMES.has(d.step))
  ```
  So adding `'agent_hitl_flow'` + `'ops_snapshot'` to this set causes them to be excluded from `demo_minimal` (correct).
- **`PHASE_LABEL`** (lines 95–106) — has `agent: 'Agent'` and `cleanup: 'Cleanup'`. No `agents` / `ops` yet.
- **`PHASE_ORDER`** (lines 109–121) — 9 phases (data, modeling, decision, portfolio, planning, knowledge, verify, agent, cleanup).

### `frontend/src/components/demo/PHASE_DEFS.test.ts` — the lockstep gate

- `demo_minimal` assertion (lines 13–28): 11-tuple list ending in `['agent', 'agent']`, `['cleanup', 'cleanup']`.
- `showcase_rich` assertion (lines 30–62): 23-tuple list ending in `['agent', 'agent']`, `['cleanup', 'cleanup']`.
- `PHASE_ORDER` assertion (lines 68–80): 9 phases.
- **PRP-41 changes:**
  - `demo_minimal` tuples: swap `['agent', 'agent']` → `['agents', 'agent']`.
  - `showcase_rich` tuples: swap `['agent', 'agent']` → `['agents', 'agent_hitl_flow']` AND insert `['ops', 'ops_snapshot']` immediately after, before the cleanup row. Tuple count 23 → 24.
  - `PHASE_ORDER`: 9 → 10 (`'agent'` → `'agents'`, then insert `'ops'`).

### `frontend/src/components/demo/DemoPhasePanel.tsx`

- **CONFIRMED MISSING `onValueChange`** — line 46:
  ```tsx
  <Accordion type="single" collapsible value={value} className="space-y-2">
  ```
  No handler. Issue #311 fix is precisely this hook addition. The PRP's Task 10 pattern is correct: lift `value` to `useState<string>` seeded from the computed value via `useEffect`, expose `onValueChange={setExpandedPhase}`.

### `frontend/src/components/demo/demo-step-card.tsx`

- 392 lines total.
- Mini-summary helpers (`BacktestBreakdown`, `RegisterDetail`, `ChampionCompatDetail`, `StaleAliasDetail`, `SaferPromoteDetail`, `BatchPresetDetail`, `ScenarioSummary`, `CompareSummary`, `ProviderChip`, `IndexSummary`, `RetrieveSummary`) live at lines ~35–305 — PRP-41's `HitlFlowSummary` + `OpsSnapshotMiniGrid` follow the same shape.
- Conditional rendering switch at lines 356–377 (per `step.name`) — PRP-41 inserts two more cases.
- Inspect button at lines 378–387 — PRP-41 inserts the Approve button as a peer block (rendered when `step.data.awaiting_approval === true && step.status === 'running'`).

### `frontend/src/hooks/use-demo-pipeline.ts`

- `disconnectRef` at **line 198** ✅
- `useWebSocket(...)` destructures `{status, send, disconnect, reconnect}` at **line 208** ✅
- `useEffect(() => { disconnectRef.current = disconnect }, [disconnect])` at lines 213–215 ✅
- **Return object (lines 247–263) currently exposes** `steps, phases, runningPhase, phase, summary, errorMessage, isRunning, connectionStatus, start, setScenario, scenario`. **`stop` is NOT exposed** — PRP-41 Task 13 adds it.

### `frontend/src/hooks/use-websocket.ts`

- `return { status, send, disconnect, reconnect }` at the bottom — `disconnect()` already cancels reconnect + closes socket. **No changes needed to this file.** ✅

### `frontend/src/pages/showcase.tsx`

- `resolveInspectHref(step)` at lines 17–84 — switch covers train / v2_train / register / backtest / champion_compat_compare / stale_alias_trigger / safer_promote_flow / batch_preset / scenario_simulate_and_save / multi_plan_compare / embedding_provider_probe / rag_index_subset / rag_retrieve_probe / default → null. **PRP-41 adds two cases:** `agent_hitl_flow` → `ROUTES.CHAT`, `ops_snapshot` → `ROUTES.OPS`.
- `useDemoPipeline()` destructure at lines 86–98 — PRP-41 adds `stop`.
- Page structure starts at line 141 — PRP-41 inserts KPI strip + RunHistoryStrip above controls, Stop button inside controls card (visible when `isRunning`), InspectArtifactsPanel after the phase accordion (visible when `phase === 'done'`).

### `frontend/src/lib/constants.ts`

- **All 10 inspect-target routes already exist** — verified:
  - `ROUTES.VISUALIZE.FORECAST`, `.BACKTEST`, `.BATCH`, `.PLANNER`
  - `ROUTES.EXPLORER.RUNS`, `.RUN_COMPARE`, `.RUN_DETAIL`
  - `ROUTES.OPS`, `.KNOWLEDGE`, `.CHAT`
- **Zero new routes required.** ✅

### `frontend/src/pages/admin.tsx`

- Line 431 — `const SEEDER_FORM_STORAGE_KEY = 'forecastlab.seederForm.v1'`
- Line 456 — `window.localStorage.getItem(SEEDER_FORM_STORAGE_KEY)`
- Line 485 — `window.localStorage.setItem(SEEDER_FORM_STORAGE_KEY, JSON.stringify(form))`
- Pattern: `forecastlab.<feature>.v<N>` versioned key + raw JSON serialization. PRP-41 mirrors as `forecastlab.showcase.runs.v1`.

---

## 5. Resolution of the 5 unresolved contract assumptions

### Assumption #1 — `_Client.yield_event` orchestrator fill-in

**Recommendation in PRP body:** orchestrator overwrites `step_index`, `total_steps`, `phase_index`, `phase_total` on every event drained from the sink.

**Verified — viable.** `run_pipeline` (line 2076) computes all four values per-row at the top of each loop iteration (`index` from `enumerate(rows, start=1)`, `phase_index = phase_index_by_phase[phase_name]`, `phase_total = len(phases_in_order)`, `total = len(rows)`). The orchestrator can stamp these on each intermediate event BEFORE the terminal yield. **Design Z works without breaking the existing 22 steps** because none of them currently use `client.yield_event(...)` (the helper doesn't exist on `dev`).

**Implementer guidance:** when draining `intermediate_events`, set
```python
ev.step_index = index
ev.total_steps = total
ev.phase_index = phase_index
ev.phase_total = phase_total
ev.phase_name = phase_name  # belt-and-braces; the step fn may have set it
```
on every event, in FIFO order, BEFORE yielding the terminal `step_complete`.

### Assumption #2 — Approve double-fire response shape

**Verified — 400 Bad Request.** `AgentService.approve_action` raises `NoApprovalPendingError` when:
- `session.pending_action is None` (already consumed by the first call), OR
- `pending.get("action_id") != action_id` (mismatch).

Both map to `HTTPException(status_code=400, detail=...)` in `agents/routes.py` lines 192–195. **PRP-41's `if 400 <= exc.status_code < 500:` absorption catches this correctly.**

**Implementer guidance:** the absorb branch should set `approval_decision = "executed"` (optimistic — visitor clicked first) per PRP pseudocode. The 200 path sets it from `approve_body["status"]` (one of `executed` / `rejected` / `expired`).

### Assumption #3 — `SHOWCASE_RICH_STEP_NAMES` filter semantics + PHASE_DEFS.ts filter restructure

**Filter shape verified:** the current filter (lines 87–93) keeps everything on `showcase_rich` and excludes `SHOWCASE_RICH_STEP_NAMES` on every other scenario:
```ts
if (scenario === 'showcase_rich') return ALL_STEPS
return ALL_STEPS.filter((d) => !SHOWCASE_RICH_STEP_NAMES.has(d.step))
```

**Design Z requires a small filter restructure** beyond what PRP-41 Task 9 reads. Under design Z, BOTH `'agent'` (legacy step name, demo_minimal) AND `'agent_hitl_flow'` (showcase_rich) appear in `ALL_STEPS`. The current `if scenario === 'showcase_rich' return ALL_STEPS` would return BOTH on showcase_rich (bug — we want only `agent_hitl_flow`).

**Recommended restructure (one of two options, pick either):**

**(a)** Introduce a `DEMO_MINIMAL_ONLY_STEP_NAMES` set:
```ts
const DEMO_MINIMAL_ONLY_STEP_NAMES = new Set(['agent'])  // legacy agent only

export function phaseDefsForScenario(scenario: ScenarioPreset): readonly PhaseDef[] {
  if (scenario === 'showcase_rich') {
    return ALL_STEPS.filter((d) => !DEMO_MINIMAL_ONLY_STEP_NAMES.has(d.step))
  }
  return ALL_STEPS.filter((d) => !SHOWCASE_RICH_STEP_NAMES.has(d.step))
}
```

**(b)** Add `'agent_hitl_flow'` and `'ops_snapshot'` to `SHOWCASE_RICH_STEP_NAMES`
AND add `'agent'` to a `DEMO_MINIMAL_ONLY_STEP_NAMES` set (same shape as a).

Both options produce the same result; (a) is the cleaner refactor.

> **PRP wording note:** PRP-41 § Task 9 pseudocode reads partially as if option (a) is intended ("ADD a sibling row preserving it … and exclude it from showcase_rich via SHOWCASE_RICH_STEP_NAMES") — but `SHOWCASE_RICH_STEP_NAMES` is the wrong direction (it's the exclude-from-demo-minimal set). The implementer **MUST** use option (a) (a NEW set, not the existing one) OR restructure the filter conditional.

### Assumption #4 — `OpsSummaryResponse.runs.counts` shape

**Verified — `runs.counts` (NOT `runs.histogram`); per-item key is `count` (NOT `value`).**

`RunHealth` (line 111) carries `counts: list[StatusCount]`; `StatusCount` (line 80) has `status: str` + `count: int`. PRP-41 pseudocode `sum(int(c.get("count", 0)) for c in counts if isinstance(c, dict))` is correct.

`OpsService.get_summary` (line 225, `app/features/ops/service.py`) constructs each `StatusCount(status=..., count=...)` from the DB grouping — confirmed live shape.

### Assumption #5 — `_Client.request` list-body wrapper

**Already CONFIRMED in PRP body.** Verified at pipeline.py line 178: `body if isinstance(body, dict) else {"_raw": body}`. Every `/ops/*` and `/agents/*` endpoint PRP-41 calls returns a dict body — `_raw` does not come into play for PRP-41.

---

## 6. step.data payload sources for KPI strip / Inspect-Artifacts panel

Verified each PRP-39/40 source step's `step.data` keys against current `pipeline.py`:

| KPI tile | Source step | Key | Confirmed location |
|---|---|---|---|
| `runs_registered` | `register` / `stale_alias_trigger` / `safer_promote_flow` / `v2_train` | `run_id` | pipeline.py line ~1100, ~1610, ~1750, ~970 |
| `aliases_live` | `ops_snapshot` (PRP-41) | `total_aliases` | new in PRP-41 |
| `batch_items_completed` | `batch_preset` | `completed_items` | pipeline.py ~1880 |
| `scenario_plans_saved` | `scenario_simulate_and_save` + `multi_plan_compare` | `scenario_id` + `winner_scenario_id` | pipeline.py ~1170 + ~1280 |
| `rag_chunks_indexed` | `rag_index_subset` | `total_chunks` | pipeline.py ~1350 |

All sources match PRP-41 § Task 14 expectations.

For Inspect-Artifacts deep-link dependencies, every required `step.data.*` key
already exists on `dev` and is documented in `resolveInspectHref` (showcase.tsx
lines 17–84) which PRP-41 extends.

---

## 7. PRP wording patches required

### Patch — Task 9 filter semantics

**Location:** PRP-41 § Per task pseudocode → "Task 9 — PHASE_DEFS.ts extension" (lines ~1528–1560).

**Current wording (incomplete):**
> NOTE: demo_minimal still emits the legacy step name "agent" — the FE's
> `phaseDefsForScenario('demo_minimal')` filter must keep both step ids in
> `ALL_STEPS` and select by name (Task 1 confirms the filter shape).
> If the lockstep test's demo_minimal assertion explicitly asserts `'agent'`
> step under `'agent'` phase, ADD a sibling row preserving it:
>   `{ phase: 'agent', step: 'agent', label: 'Agent chat (legacy)' }`,
> ... and exclude it from showcase_rich via SHOWCASE_RICH_STEP_NAMES.

**Issue:** PRP-41's recommended **design Z** unifies the phase id to `'agents'`
for BOTH demo_minimal and showcase_rich. Keeping `phase: 'agent'` on the
sibling row is **design X**, which the PRP § "demo_minimal phase rename
trade-off" recommends AGAINST. AND `SHOWCASE_RICH_STEP_NAMES` is the
"exclude from demo_minimal" set, NOT the "exclude from showcase_rich" set
— the current filter cannot exclude `'agent'` from showcase_rich.

**Required patch — implementer follows this revised pseudocode:**

```ts
// ALL_STEPS: keep the legacy "agent" row under the NEW phase id 'agents',
// and add a sibling row for the HITL flow + the new ops snapshot row.
//   { phase: 'agents', step: 'agent',           label: 'Agent chat (legacy)' },
//   { phase: 'agents', step: 'agent_hitl_flow', label: 'Agent HITL approval' },
//   { phase: 'ops',    step: 'ops_snapshot',    label: 'Ops snapshot' },

// NEW set — excludes the legacy step from showcase_rich:
const DEMO_MINIMAL_ONLY_STEP_NAMES = new Set(['agent'])

// SHOWCASE_RICH_STEP_NAMES gets 'agent_hitl_flow' + 'ops_snapshot' added
// (so they're excluded from demo_minimal). Filter restructured:
export function phaseDefsForScenario(scenario: ScenarioPreset): readonly PhaseDef[] {
  if (scenario === 'showcase_rich') {
    return ALL_STEPS.filter((d) => !DEMO_MINIMAL_ONLY_STEP_NAMES.has(d.step))
  }
  return ALL_STEPS.filter((d) => !SHOWCASE_RICH_STEP_NAMES.has(d.step))
}
```

**Implementer note:** This restructure is small and additive — the existing
`SHOWCASE_RICH_STEP_NAMES` set is preserved, and `DEMO_MINIMAL_ONLY_STEP_NAMES`
is new. Both filters now use the same shape. Lockstep test fixture changes
follow naturally:
- `demo_minimal`: tuple list ends `['agents', 'agent']`, `['cleanup', 'cleanup']` (10-tuple + cleanup = 11 tuples — count unchanged).
- `showcase_rich`: tuple list ends `['agents', 'agent_hitl_flow']`, `['ops', 'ops_snapshot']`, `['cleanup', 'cleanup']` (count: 22 + 2 = 24, swap + insert one row).

**This patch is purely a clarification — no PRP-41 task is added or removed.**

### No other PRP body patches required.

All other cited contracts match field-for-field. The PRP body's own notes
about `drift_direction`, `action_id`, `pending_approval` already capture the
INITIAL-41 drift correctly.

---

## 8. Verdict

✅ **GO for implementation. Proceed to Tasks 2–19.**

- All 5 contract assumptions resolved.
- Zero field-level drift in backend or frontend contracts.
- One small filter-restructure clarification documented (§7) — does NOT add
  scope; the implementer simply applies the resolved option (a) when
  implementing Task 9.
- Design Z is verified viable: `run_pipeline` already computes the four
  indices the orchestrator-fill-in needs.
- The Stop button design is sound: `WebSocketDisconnect` propagation
  releases `_pipeline_lock` (confirmed at `service.py:41` + `routes.py:74`).
- Approve double-fire: 400 absorption is correct.

### Implementer checklist (Task 2 onward)

1. Implement design Z verbatim — same phase id `'agents'` for both scenarios.
2. Add `DEMO_MINIMAL_ONLY_STEP_NAMES = new Set(['agent'])` and restructure
   the filter per §7.
3. Backend lockstep test updates:
   - `test_phase_table_demo_minimal_matches_legacy_11_steps`: rename to
     `test_phase_table_demo_minimal_matches_11_steps_with_agents_phase` and
     swap the agent tuple to `("agents", "agent")`.
   - `test_phase_table_showcase_rich_adds_…`: rename to include `_24_steps`
     and apply the swap + insert.
4. Frontend lockstep test updates: mirror the same shape in `PHASE_DEFS.test.ts`.
5. `step_agent_hitl_flow`: NEVER raise; map every error path to `("skip", ...)`.
6. `step_ops_snapshot`: `("warn", ...)` on all-three-failed, never `("fail", ...)`.
7. Vertical-slice grep guard must remain empty:
   ```bash
   git grep -nE "from app\.features\.(agents|ops|registry|scenarios|rag)" \
     app/features/demo/
   ```
8. Frontend type-check uses **project-scoped** invocation:
   `cd frontend && pnpm tsc --noEmit -p tsconfig.app.json`.

— end of report —
