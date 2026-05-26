name: "PRP-40 — Showcase Planning + Knowledge Lifecycle"
description: |
  Third slice of the four-PRP `/showcase` upgrade epic (PRP-38..41). PRP-40
  adds two new phases — `planning` and `knowledge` — to the in-process demo
  pipeline so a visitor running the `showcase_rich` scenario sees the full
  what-if planning workflow (simulate → save → multi-plan compare) and the
  curated RAG corpus workflow (provider probe → index → semantic-retrieve),
  both driven end-to-end against PRP-38's `demo-production` champion run.

  > **PREREQUISITES — PRP-38 merged.** PRP-40 depends on PRP-38's
  > `demo-production` alias and the `showcase_rich` scenario picker.
  > **PRP-40 does NOT require PRP-39.** PRP-39 (Decision + Portfolio lifecycle)
  > is a sibling slice authored in parallel. Both edit `_phase_table()` and
  > `PHASE_DEFS.ts`; PRP-40 uses **relative-anchor insertion** so the
  > second-to-merge slice rebases mechanically without re-numbering.
  >
  > **PRP-41 is NOT in scope.** Agent HITL flow, ops snapshot / KPI strip,
  > Inspect-Artifacts post-run panel, localStorage run history, Stop button,
  > walkthrough doc — every one of these belongs to PRP-41. Mention them
  > ONLY in the "Out of Scope" block; do NOT implement, scaffold, or stub.

## Purpose

A one-pass implementation contract for an AI agent (or human) with access to
the codebase but no prior session context. Ship the planning + knowledge
phases of the `/showcase` rich demo upgrade: five new pipeline steps across
two new phases, additive `phase_name` payloads, additive
`IndexProjectDocsRequest.path_prefix`, frontend phase-defs lockstep, step-card
mini-summaries, and per-step Inspect deep links — WITHOUT regressing PRP-38's
`showcase_rich` flow or violating the demo slice's "stateless orchestrator
over `httpx.ASGITransport`" invariant.

## Core Principles

1. **Backend contracts are read-only.** Every endpoint PRP-40 drives
   (`/scenarios/simulate`, `/scenarios`, `/scenarios/compare`, `/rag/retrieve`,
   `/config/providers/health`, `/registry/aliases/{name}`, `/registry/runs/{id}`)
   already exists on `dev`. Task 1's contract probe (`PRPs/ai_docs/prp-40-contract-probe-report.md`)
   verifies field-for-field presence. PRP-40 adds **ONE** additive backend
   field: `IndexProjectDocsRequest.path_prefix: str | None = None` (default
   None preserves back-compat).
2. **Vertical-slice rule (load-bearing).** `app/features/demo/` MUST NOT
   import from `app/features/{scenarios,rag,config,registry}/`. All five
   new steps drive their respective slices over `httpx.ASGITransport`
   exactly like PRP-38's existing steps. Grep guard:
   `git grep -nE "from app\.features\.(scenarios|rag|config|registry)" app/features/demo/` MUST be empty.
3. **WebSocket contract is ADDITIVE ONLY.** `StepEvent.data` is
   `dict[str, Any]` — the new payloads add string/int/float fields, no
   schema bump. The `phase_name` / `phase_index` / `phase_total` fields
   PRP-38 added stay Optional + Nullable.
4. **Phase table is a stability invariant — RELATIVE ANCHORS only.**
   Backend `_phase_table()` inserts the two new phases (`planning` and
   `knowledge`) **immediately BEFORE the `verify` phase row** — NEVER as
   "at row index N". PRP-39 (sibling) inserts a `portfolio` phase using
   the same anchor; whichever PRP merges second rebases cleanly because
   neither cites an absolute index.
5. **No new tables, no Alembic migrations.** The two saved plans persist
   through `POST /scenarios` into the existing `scenario_plan` table.
6. **Skip gracefully on missing providers.** Every `knowledge`-phase step
   uses the `_llm_key_present()` gating pattern. The new helper
   `_embedding_provider_reachable()` performs the same presence-only
   check (name-only logging, never the value).
7. **Pre-1.0 contract additivity.** Every new schema field is Optional;
   no `feat!:` / breaking commit. PRP-40 is purely additive.
8. **shadcn workflow.** PRP-40 adds NO new shadcn primitives (Card +
   Badge + Button already imported by the PRP-38 step card). If a new
   primitive turns out to be needed, route it through the `shadcn` skill
   per `.claude/rules/shadcn-ui.md`.

---

## Goal

Deliver, on branch `feat/showcase-40-planning-knowledge-lifecycle`, the
planning + knowledge slice of the `/showcase` rich demo upgrade so a visitor
running the `showcase_rich` scenario sees:

- Two named scenario plans persisted in the plan library (a 10% price-cut
  plan `showcase-price-cut-10pct` and a holiday-set plan
  `showcase-holiday-uplift`), both visible on `/visualize/planner`.
- A multi-plan compare row ranking the two plans against the shared
  baseline by `revenue_delta`.
- The 5 curated user-guide markdown files indexed in the RAG corpus,
  visible on `/knowledge` with chunk counts.
- A successful semantic-retrieve probe returning at least one hit with a
  populated similarity score.
- When the configured embedding provider is unreachable, the entire
  `knowledge` phase reports `skip` for its three steps (NOT `fail`) with
  a clear `detail`, and the pipeline still goes green.

## Why

Without PRP-40, the `/showcase` page demonstrates only data + modeling +
decision (PRP-38). The two big "operator workflows" — what-if planning and
the curated RAG corpus — are invisible to a first-time visitor unless they
hand-craft saved plans and re-index the docs library themselves. PRP-40
makes both workflows visible in-line with PRP-38's `showcase_rich` run, so
one click on `/showcase` exercises:

- The scenarios slice's full lifecycle (simulate, save, multi-plan compare)
  with deep-links into `/visualize/planner`.
- The RAG slice's project-docs index + retrieve flow scoped to a curated
  user-guide subset, with deep-links into `/knowledge`.

This is the third slice of the four-PRP epic. After PRP-40 + PRP-39 land,
PRP-41 plugs the agent HITL + ops snapshot lifecycle into the same phase
accordion (additively).

## What

### User-visible behaviour

- `/showcase` on `showcase_rich` runs five additional steps grouped under
  two new phases — `planning` (2 steps) and `knowledge` (3 steps) —
  inserted between `decision` and `verify`. Total step count on
  `showcase_rich`: 14 → 19 (PRP-40 adds 5).
- The `planning` phase emits `scenario_simulate_and_save` and
  `multi_plan_compare`. Each step card shows a one-row mini summary
  (`plan=showcase-price-cut-10pct · Δunits=…  · Δrevenue=… · method=…`
  / `winner=… · ranked_by=revenue_delta`).
- The `knowledge` phase emits `embedding_provider_probe`,
  `rag_index_subset`, `rag_retrieve_probe`. Each step card shows a
  one-row mini summary (provider chip / `files_indexed/5 · chunks=… ·
  failed=…` / top-1 hit title + similarity score).
- Each terminal-status step card shows an "Inspect" button deep-linking
  into the relevant page: `scenario_simulate_and_save` → `/visualize/planner?scenario_id={id}`,
  `multi_plan_compare` → `/visualize/planner`, `embedding_provider_probe`
  → `/admin`, `rag_index_subset` → `/knowledge`, `rag_retrieve_probe` →
  `/knowledge`.
- When the embedding provider is unreachable (no API key configured for
  the active `rag_embedding_provider` AND Ollama probe fails), the three
  `knowledge`-phase steps emit `skip` (NOT `fail`) with a clear `detail`;
  pipeline still goes green.

### Technical requirements

- **Backend (`app/features/demo/pipeline.py`)** — five new step functions
  + one helper (`_parse_artifact_key`) + one helper
  (`_embedding_provider_reachable`); `_phase_table()` inserts the two
  new phases using relative anchors.
- **Backend (`app/features/rag/schemas.py` + `service.py`)** — additive
  `path_prefix: str | None` field on `IndexProjectDocsRequest`; service
  discovery honours it with a path-traversal guard.
- **Frontend (`frontend/src/components/demo/PHASE_DEFS.ts`)** — extend
  `ALL_STEPS` with the 5 new rows + `PHASE_ORDER` / `PHASE_LABEL` with
  the two new phases.
- **Frontend (`frontend/src/pages/showcase.tsx`)** — extend
  `resolveInspectHref()` switch with the 5 new step cases.
- **Frontend (`frontend/src/components/demo/demo-step-card.tsx`)** —
  three new mini-summary helpers (`ScenarioSummary`, `CompareSummary`,
  `ProviderChip`, `IndexSummary`, `RetrieveSummary`).
- **Documentation (`docs/_base/RUNBOOKS.md`)** — extend the "Showcase
  page pipeline fails at step X" section with the 5 new step failure
  modes (additively).

### Success Criteria (verifies INITIAL-40 C1..C6)

- [ ] **C1** — After a `showcase_rich` run, `/visualize/planner` shows
      `showcase-price-cut-10pct` AND `showcase-holiday-uplift` in the
      saved-plans library; the multi-plan compare row ranks them by
      `revenue_delta`. Verified by **manual dogfood**.
- [ ] **C2** — After a `showcase_rich` run, `/knowledge` lists the 5
      curated user-guide docs with non-zero chunk counts; a UI semantic
      search ("how do I run the demo") returns hits. Verified by
      **manual dogfood**.
- [ ] **C3** — With every embedding-provider env var unset AND Ollama
      unreachable, the `knowledge` phase emits 3× `skip` with a clear
      `detail`; pipeline still goes green. Verified by
      `pytest -m integration` with a key-stripped env fixture.
- [ ] **C4** — `showcase_rich` end-to-end (PRP-38 + PRP-40 steps; PRP-39
      sibling phases independent) still ≤ 240 s on the dev host.
      Verified by `pytest -m integration` wall-clock assertion.
- [ ] **C5** — Backend `_phase_table()` and frontend `PHASE_DEFS` still
      match (both updated in lockstep). Verified by `test_phase_table_*`
      (backend) + `PHASE_DEFS.test.ts` (frontend).
- [ ] **C6** — All five validation gates green (`ruff` / `ruff format` /
      `mypy --strict` / `pyright --strict` / `pytest`). Verified by CI.

### Out of Scope (explicit — do NOT implement in PRP-40)

- **PRP-39** territory: Champion-compat compare, stale-alias trigger,
  safer-Promote dialog, batch preset/matrix. PRP-39 is a sibling, NOT a
  hard prerequisite. PRP-40 can author in parallel with PRP-39 as long
  as each PRP's contract-probe report is done first.
- **PRP-41 territory:** Agent HITL flow, ops snapshot KPI strip,
  Inspect-Artifacts post-run panel, localStorage run history, Stop
  button, walkthrough doc. **PRP-41 is NOT in scope.**
- New shadcn primitives — Card / Badge / Button cover all five new step
  cards. If a new primitive turns out to be unavoidable, surface as a
  stop-and-ask gate and route through the `shadcn` skill.
- Sub-path filename allow-list filtering. PRP-40 ships `path_prefix` as
  the additive primitive; per-file allow-listing inside the discovery
  glob can land in a future PRP if needed.
- Wide-corpus indexing. The curated 5-file subset keeps blast radius
  small (memory `[[rag-runtime-config-and-corpus-state]]`).

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ — Include these in your context window
- docfile: PRPs/ai_docs/prp-40-contract-probe-report.md
  why: Task 1 output — field-for-field verification of every cited contract
       on dev at 3e771c9. Documents R16 / R17 / R18 resolutions and the
       drift INITIAL-40 → backend that PRP-40 patches in its first draft.

- docfile: PRPs/ai_docs/prp-38-contract-probe-report.md
  why: Pattern for the contract-probe report shape; PRP-40 mirrors it.

- docfile: PRPs/ai_docs/prp-37-contract-probe-report.md
  why: Same pattern, slightly different shape — second exemplar.

- file: PRPs/PRP-38-showcase-data-modeling-lifecycle.md
  why: Predecessor PRP. PRP-40 sits on top of PRP-38's phase accordion,
       scenario picker, `_phase_table()`, `PHASE_DEFS.ts`, and the
       `demo-production` champion alias step_register produces.

- file: PRPs/PRP-27-scenario-simulation-full-version.md
  why: Scenarios slice's design rationale (heuristic vs model_exogenous
       method, multi-plan compare, save_scenario HITL). PRP-40 consumes
       these contracts; it does NOT modify them.

- file: PRPs/INITIAL/INITIAL-showcase-40-planning-knowledge-lifecycle.md
  why: Source-of-truth INITIAL (410 lines, already patched). Acceptance
       criteria C1..C6 and the dogfood checklist live here.

- file: PRPs/INITIAL/INITIAL-showcase-rich-demo-control-center.md
  why: Parent INITIAL — the four-PRP epic's vision and the parallel
       sibling-slice merge coordination rules.

# Pattern files (read for shape)
- file: app/features/demo/pipeline.py
  why: |
    - Lines 77, 85-103, 106-159 — `_HTTP_TIMEOUT` + `_StepError` +
      `_Client.request` (the ASGI in-process transport).
    - Lines 221-237 — `_llm_key_present()` (the skip-gracefully gate
      to mirror for `_embedding_provider_reachable()`).
    - Lines 887-1007 — `step_register` (multi-call step pattern PRP-40's
      `scenario_simulate_and_save` and `multi_plan_compare` follow).
    - Lines 1108-1158 — `_phase_table()` + PHASE_* constants (the
      relative-anchor insertion point).
    - Lines 1166-1255 — `run_pipeline` orchestration (no change needed;
      it iterates `_phase_table()` agnostically).

- file: app/features/scenarios/schemas.py
  why: |
    - Lines 37-58 — `PriceAssumption.change_pct` / `start_date` / `end_date`.
      NOTE the field name is `change_pct`, NOT `pct_change` (INITIAL-40 was off).
    - Lines 82-96 — `HolidayAssumption.dates` (no `uplift_multiplier`).
    - Lines 147-173 — `SimulateScenarioRequest` (run_id is the artifact
      key, NOT model_run.run_id — R16).
    - Lines 176-212 — `CreateScenarioRequest` (requires run_id+horizon+
      assumptions+name; tags optional list[str]).
    - Lines 277-321 — `ScenarioComparison.units_delta`/`revenue_delta`/
      `method` (NOT `aggregate_*` — INITIAL-40 was off).
    - Lines 409-428 — `CompareScenariosRequest` (2..5 scenario_ids +
      `rank_by` Literal["revenue_delta","units_delta"]).
    - Lines 444-463 — `MultiScenarioComparison` (the response shape).

- file: app/features/rag/schemas.py
  why: |
    - Lines 68-87 — `RetrieveRequest` + `RetrieveResponse`.
    - Lines 184-241 — `IndexProjectDocsRequest` + `IndexProjectDocsResponse`.
      Lines 184-201 are what PRP-40 extends additively with `path_prefix`.

- file: app/features/rag/service.py
  why: |
    - Lines 260-291 — `_discover_project_doc_files`. PRP-40 changes the
      `if request.include_docs:` branch ONLY (one elif for path_prefix).
    - Lines 293-387 — `index_project_docs` (no change needed; consumes
      the discovery list verbatim).

- file: app/features/config/schemas.py
  why: |
    - Lines 136-145 — `ProviderHealth(provider, reachable, detail, models)`.

- file: app/features/config/service.py
  why: |
    - Lines 269-316 — `get_provider_health()` returns [ollama, openai,
      anthropic, google] in that order. PRP-40's
      `_embedding_provider_reachable()` consumes the list.

- file: app/features/registry/schemas.py
  why: |
    - Lines 129-160 — `RunResponse.artifact_uri` (str | None).
    - Lines 229-240 — `AliasResponse` — does NOT include `artifact_uri`.
      PRP-40 makes TWO calls: alias → run → artifact_uri (R16 ➕finding).

- file: frontend/src/components/demo/PHASE_DEFS.ts
  why: Lockstep contract with `_phase_table()`. PRP-40 extends ALL_STEPS
       + PHASE_ORDER + PHASE_LABEL.

- file: frontend/src/components/demo/demo-step-card.tsx
  why: Pattern for step-card mini summaries (BacktestBreakdown,
       RegisterDetail). PRP-40 adds five new helpers in the same shape.

- file: frontend/src/pages/showcase.tsx
  why: |
    - Lines 26-50 — `resolveInspectHref(step)` switch. PRP-40 adds five
      new cases.

- file: frontend/src/lib/constants.ts
  why: `ROUTES.VISUALIZE.PLANNER`, `ROUTES.KNOWLEDGE`, `ROUTES.ADMIN`
       already exist. Reuse — do NOT add new routes.

# Rules
- file: .claude/rules/security-patterns.md
  section: "Secrets handling" + "LLM / Agent layer"
  critical: Presence-only checks; key NAMES, never values. PRP-40's
            `_embedding_provider_reachable()` MUST log only the provider
            name + a bool, never an API-key value.

- file: .claude/rules/test-requirements.md
  section: "When new tests are required"
  critical: Each new pipeline step ships at least one per-step test
            (happy path + provider-unreachable skip variant for
            knowledge phase steps).

- file: .claude/rules/commit-format.md
  section: "Scope allow-list"
  critical: Use `feat(api,ui): showcase pipeline — planning + knowledge
            lifecycle (#<issue>)`. The `(api,ui)` comma-pair is allowed.

# External (load via mcp__claude_ai_contex7__)
- url: https://www.python-httpx.org/async/#calling-into-python-web-apps
  why: ASGITransport pattern — the in-process call path the demo slice
       uses for cross-slice contract calls.

- url: https://github.com/pgvector/pgvector
  why: Embedding-dim caveat (R4). If the operator changes provider mid-
       showcase, indexed chunks orphan — PRP-40 documents this risk in
       the runbook patch (out-of-scope: a `clear_rag` UI toggle).
```

### Current Codebase tree (relevant slices)

```bash
app/features/
├── demo/                          # The slice PRP-40 extends
│   ├── pipeline.py                # _phase_table(), 14 step functions,
│   │                              # _HTTP_TIMEOUT, _llm_key_present,
│   │                              # _StepError, DemoContext
│   ├── routes.py                  # POST /demo/run + WS /demo/stream
│   ├── schemas.py                 # DemoRunRequest, StepEvent (the WS frame)
│   ├── service.py                 # thin layer around pipeline.run_pipeline
│   └── tests/
│       ├── test_pipeline.py       # per-step tests + lockstep test
│       ├── test_routes.py         # WS integration
│       └── test_schemas.py
├── scenarios/                     # READ-ONLY for PRP-40
│   ├── routes.py                  # POST /scenarios/{simulate,compare}, POST/GET/DELETE /scenarios
│   ├── schemas.py                 # PriceAssumption, HolidayAssumption,
│   │                              # ScenarioAssumptions, SimulateScenarioRequest,
│   │                              # CreateScenarioRequest, ScenarioComparison,
│   │                              # ScenarioPlanResponse, CompareScenariosRequest,
│   │                              # MultiScenarioComparison
│   ├── service.py                 # ScenarioService (loads bundle, applies adjustments,
│   │                              # OR re-forecasts through feature_frame for regression)
│   ├── adjustments.py             # PURE deterministic factor engine
│   ├── feature_frame.py           # X_future builder for model_exogenous re-forecast
│   ├── agent_tools.py             # save_scenario HITL gate (read-only for PRP-40)
│   └── models.py                  # ScenarioPlan ORM
├── rag/                           # MODIFIED by PRP-40 (additive path_prefix)
│   ├── routes.py                  # POST /rag/{index, index/project-docs, retrieve}
│   ├── schemas.py                 # IndexProjectDocsRequest (path_prefix added),
│   │                              # RetrieveRequest, RetrieveResponse
│   ├── service.py                 # _discover_project_doc_files (path_prefix branch added)
│   └── tests/
├── config/                        # READ-ONLY for PRP-40
│   ├── routes.py                  # GET /config/providers/health, etc.
│   ├── schemas.py                 # ProviderHealth
│   └── service.py                 # get_provider_health() (live Ollama probe + key presence)
├── registry/                      # READ-ONLY for PRP-40
│   ├── routes.py                  # GET /registry/aliases/{name}, GET /registry/runs/{id}
│   └── schemas.py                 # AliasResponse (no artifact_uri), RunResponse (has artifact_uri)
└── ...

frontend/src/
├── components/demo/
│   ├── PHASE_DEFS.ts              # MODIFIED — add 5 new step rows, 2 new phases
│   ├── PHASE_DEFS.test.ts         # MODIFIED — extend the lockstep tuple list
│   ├── demo-step-card.tsx         # MODIFIED — add 5 new mini-summary helpers
│   ├── demo-step-card.test.tsx    # MODIFIED — add 5 new Inspect deep-link tests
│   └── ...
├── pages/
│   └── showcase.tsx               # MODIFIED — extend resolveInspectHref switch
└── lib/constants.ts               # READ-ONLY — reuse ROUTES.VISUALIZE.PLANNER, ROUTES.KNOWLEDGE, ROUTES.ADMIN

docs/
├── user-guide/                    # READ-ONLY — the curated 5-file corpus
│   ├── getting-started.md
│   ├── dashboard-guide.md
│   ├── feature-reference.md
│   ├── agents-and-rag-guide.md
│   └── advanced-forecasting-guide.md
└── _base/
    └── RUNBOOKS.md                # MODIFIED — append the 5 new step failure modes
```

### Desired Codebase tree (additive + modified files)

```bash
# MODIFIED
app/features/demo/pipeline.py        # +5 step functions, +2 helpers, +2 phase constants,
                                     #  _phase_table() inserts before VERIFY
app/features/demo/tests/test_pipeline.py  # +10 tests (happy + skip per step)
app/features/rag/schemas.py          # +1 Optional field on IndexProjectDocsRequest
app/features/rag/service.py          # +1 branch in _discover_project_doc_files
app/features/rag/tests/test_service.py    # +1 test (path-traversal guard)

frontend/src/components/demo/PHASE_DEFS.ts        # +5 step rows, +2 phases
frontend/src/components/demo/PHASE_DEFS.test.ts   # lockstep tuple list extended
frontend/src/components/demo/demo-step-card.tsx   # +5 mini-summary helpers
frontend/src/components/demo/demo-step-card.test.tsx  # +5 Inspect link tests
frontend/src/pages/showcase.tsx       # +5 cases in resolveInspectHref

docs/_base/RUNBOOKS.md               # +5 failure-mode entries (additive)

# CREATED
PRPs/ai_docs/prp-40-contract-probe-report.md   # Task 1 output (already exists by Task 2)
```

### Known Gotchas of our codebase & Library Quirks

```python
# ─────────────────────────────────────────────────────────────────────────
# CRITICAL: Task 1 (Contract Probe) is the gate. Run it FIRST.
# ─────────────────────────────────────────────────────────────────────────
# Verify on `dev` (or current branch's tip):
#   - PriceAssumption.change_pct (NOT pct_change — INITIAL-40 was off).
#   - HolidayAssumption.dates (NO uplift_multiplier field exists).
#   - SimulateScenarioRequest.run_id is the 12-char artifact-key, NOT model_run.run_id.
#   - CreateScenarioRequest requires name+run_id+horizon+assumptions+optional tags.
#   - ScenarioComparison field names: units_delta / revenue_delta (NOT aggregate_*).
#   - ScenarioComparison.method ∈ {"heuristic","model_exogenous"}.
#   - CompareScenariosRequest: 2..5 scenario_ids + rank_by Literal.
#   - MultiScenarioComparison.scenarios is the ranked list (winner = scenarios[0]).
#   - IndexProjectDocsRequest has NO sub-path filter (R18) — PRP-40 adds it additively.
#   - RetrieveRequest top_k 1..50 default 5; RetrieveResponse.results[i].relevance_score.
#   - ProviderHealth list order: [ollama, openai, anthropic, google].
#   - AliasResponse has NO artifact_uri (➕ finding) — two-call resolution.
# Output to PRPs/ai_docs/prp-40-contract-probe-report.md.

# ─────────────────────────────────────────────────────────────────────────
# R16 — Scenario `run_id` is the artifact-key, NOT model_run.run_id.
# ─────────────────────────────────────────────────────────────────────────
# Two ID spaces:
#   - model_run.run_id  → 32-char UUID-hex (registry primary key).
#   - scenarios.run_id  → 12-char hex (parsed from `model_{KEY}.joblib` filename
#                          written by forecasting/service.py:374).
#
# Parse pattern (single regex covers BOTH V1 demo and V2 artifact_uri shapes):
#
#   _ARTIFACT_KEY_RE = re.compile(r"model_([0-9a-f]+)(?:\.joblib)?$")
#
# V1 demo:  "demo/{model_type}-model_{KEY}.joblib"   → KEY (12 char)
# V2:       "artifacts/models/model_{KEY}.joblib"    → KEY (12 char)
#
# Resolution flow in step_scenario_simulate_and_save:
#   1. GET /registry/aliases/demo-production
#        → alias_body["run_id"]  (the 32-char registry run_id)
#   2. GET /registry/runs/{run_id}
#        → run_body["artifact_uri"]  (the path; may be V1 or V2 shape)
#   3. _parse_artifact_key(artifact_uri)  → the 12-char artifact-key
#   4. POST /scenarios/simulate with run_id=<12-char artifact-key>
#
# Memory anchor: [[scenario-run-id-vs-registry-run-id]]

# ─────────────────────────────────────────────────────────────────────────
# R17 — method (heuristic vs model_exogenous) surfacing.
# ─────────────────────────────────────────────────────────────────────────
# ScenarioComparison.method IS the source of truth — surface it in BOTH
# step.detail and step.data["method"].
#
# - `regression` baseline → method=model_exogenous (genuine re-forecast).
# - naive/seasonal_naive/moving_average/prophet_like → method=heuristic.
#
# The demo's winner is always one of the latter four (regression is NOT
# in the demo's allow-list), so PRP-40's step will ALMOST ALWAYS surface
# method=heuristic. The dogfood checklist asserts this is reflected in
# the step card and is not a bug.
#
# Memory anchor: [[planner-ui-dogfood-findings]] — model_exogenous was
# inert to price assumptions in some PRP-27 builds. PRP-40 does NOT
# exercise that path.

# ─────────────────────────────────────────────────────────────────────────
# R18 — IndexProjectDocsRequest sub-path filter.
# ─────────────────────────────────────────────────────────────────────────
# DECISION: ship Option B — additive `path_prefix: str | None = None`
# field on IndexProjectDocsRequest. Default None preserves back-compat.
# Rationale:
#   - Option A (`include_docs=true` wholesale) indexes ~80+ files; wall-
#     clock 30-90 s (over PRP-40's 30 s slice budget).
#   - Option B adds ONE Optional field; pre-1.0 contract additivity
#     preserved; curated 5-file corpus indexes in 5-15 s.
#
# Path-traversal guard (load-bearing security):
#   candidate = (self._base_dir / request.path_prefix).resolve()
#   if not str(candidate).startswith(str(self._base_dir.resolve())):
#       raise ValueError(...)
#
# A test (`test_rag_service.py::test_index_project_docs_rejects_path_traversal`)
# asserts `path_prefix="../../etc"` raises ValueError.

# ─────────────────────────────────────────────────────────────────────────
# R4 — RAG embedding-dim mismatch can orphan chunks (memory).
# ─────────────────────────────────────────────────────────────────────────
# PRP-40 indexes a curated 5-file subset; if the operator switches embedding
# provider mid-showcase, indexed chunks orphan. The pgvector index assumes
# one fixed dimension per column. PRP-40 docs this in the runbook patch:
# "if the operator changes embedding provider, a `clear_rag` toggle (gated
# by a separate UI control — out of scope for PRP-40) is the supported
# recovery; otherwise stick to one provider for the showcase."
# Memory anchor: [[rag-runtime-config-and-corpus-state]]

# ─────────────────────────────────────────────────────────────────────────
# Vertical-slice rule (load-bearing).
# ─────────────────────────────────────────────────────────────────────────
# app/features/demo/* may import from app.core.* + app.shared.* + standard
# library only. NEVER `from app.features.scenarios.X import ...`, NEVER
# `from app.features.rag.X import ...`, NEVER `from app.features.config.X
# import ...`, NEVER `from app.features.registry.X import ...`.
# Grep guard (MUST be empty):
#   git grep -nE "from app\.features\.(scenarios|rag|config|registry)" \
#     app/features/demo/

# ─────────────────────────────────────────────────────────────────────────
# Phase-table lockstep + RELATIVE-anchor insertion (parallel-merge safety).
# ─────────────────────────────────────────────────────────────────────────
# PRP-40 and PRP-39 are sibling slices. Both edit _phase_table() and
# PHASE_DEFS.ts. The second-to-merge slice MUST rebase mechanically.
# Rule: phrase every phase-table change as "insert BEFORE/AFTER the
# `<anchor-phase>` row" — never "insert at row index N". The lockstep
# test catches conflicts at merge time; relative anchors keep the rebase
# mechanical.
#
# PRP-40 anchor: insert `planning` + `knowledge` IMMEDIATELY BEFORE the
# `verify` phase row. PRP-39 anchor: insert `portfolio` IMMEDIATELY AFTER
# the `decision` phase row. The two slices do not overlap.

# ─────────────────────────────────────────────────────────────────────────
# WebSocket contract additive only.
# ─────────────────────────────────────────────────────────────────────────
# StepEvent.data is dict[str, Any] — new payload fields are additive (no
# schema bump). The phase_name / phase_index / phase_total fields PRP-38
# added stay Optional + Nullable; PRP-40 just adds NEW phase_name VALUES
# ("planning" / "knowledge"), not new event_type values.

# ─────────────────────────────────────────────────────────────────────────
# _HTTP_TIMEOUT.
# ─────────────────────────────────────────────────────────────────────────
# app/features/demo/pipeline.py:77 — `_HTTP_TIMEOUT = httpx.Timeout(120.0, connect=5.0)`.
# All five new steps reuse it via the existing _Client wrapper.

# ─────────────────────────────────────────────────────────────────────────
# Skip-gracefully pattern (memory: [[planner-ui-dogfood-findings]]).
# ─────────────────────────────────────────────────────────────────────────
# Mirror `_llm_key_present()` at pipeline.py:221-237 for
# `_embedding_provider_reachable()`:
#   - Read get_settings().rag_embedding_provider.
#   - When provider="openai" → return bool(settings.openai_api_key).
#   - When provider="ollama" → live-probe via GET /config/providers/health
#     and read the ollama entry's `reachable` field.
#   - Log key NAME only (`provider=...`, `reachable=...`); never the value.
# embedding_provider_probe step emits PASS with detail "embedding provider
# unreachable — knowledge phase will skip" when neither holds; sets a
# context flag (ctx.embedding_unreachable = True). The next two steps
# (rag_index_subset, rag_retrieve_probe) check the flag and emit SKIP.

# ─────────────────────────────────────────────────────────────────────────
# CRLF / LF + repo-line-endings memory.
# ─────────────────────────────────────────────────────────────────────────
# Edit/Write on CRLF files produces whole-file noise diffs. Run
# `git diff --stat` before committing; if a file shows a whole-file diff,
# normalise line endings deliberately in a separate commit (not in PRP-40).
# Memory anchor: [[repo-line-endings-crlf]]

# ─────────────────────────────────────────────────────────────────────────
# Frontend type-check command is project-scoped.
# ─────────────────────────────────────────────────────────────────────────
# Use `pnpm tsc --noEmit -p tsconfig.app.json` — NOT bare `pnpm tsc --noEmit`.
# The root tsconfig has `files: []` and will pass while the app tsconfig
# still has errors. Do NOT trust a prior HANDOFF's green check.

# ─────────────────────────────────────────────────────────────────────────
# Pydantic v2 strict-mode policy.
# ─────────────────────────────────────────────────────────────────────────
# IndexProjectDocsRequest already uses ConfigDict(extra="forbid") (not
# strict=True). The new path_prefix field is `str | None` — a JSON-native
# scalar, no Field(strict=False) override needed. The AST invariant test
# app/core/tests/test_strict_mode_policy.py stays green.
```

---

## Implementation Blueprint

### Data models and structure (additive)

```python
# app/features/rag/schemas.py — additive field (existing fields preserved)
class IndexProjectDocsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_docs: bool = Field(default=True, description="Index docs/**/*.md")
    include_prps: bool = Field(default=True, description="Index PRPs/**/*.md")
    include_root: bool = Field(default=True, description="...")

    # PRP-40 — additive sub-path filter for the docs/ root. None preserves
    # back-compat (wholesale rglob).
    path_prefix: str | None = Field(
        default=None,
        max_length=200,
        description="Optional repo-relative path under docs/ to restrict "
        "discovery to (e.g. 'docs/user-guide'). When None (default), "
        "discovery scans every docs/**/*.md (back-compat).",
    )
```

```python
# app/features/demo/pipeline.py — additive helpers + phase constants
PHASE_PLANNING = "planning"   # PRP-40
PHASE_KNOWLEDGE = "knowledge" # PRP-40

_ARTIFACT_KEY_RE = re.compile(r"model_([0-9a-f]+)(?:\.joblib)?$")

def _parse_artifact_key(artifact_uri: str) -> str:
    """Extract the 12-char artifact-key from a registry artifact_uri.

    V1 demo: 'demo/{model_type}-model_{KEY}.joblib'  → KEY
    V2:      'artifacts/models/model_{KEY}.joblib'    → KEY
    """
    m = _ARTIFACT_KEY_RE.search(artifact_uri)
    if not m:
        raise ValueError(f"Cannot parse artifact-key from artifact_uri: {artifact_uri!r}")
    return m.group(1)

async def _embedding_provider_reachable(client: _Client) -> tuple[bool, str]:
    """Mirror `_llm_key_present()` for the configured RAG embedding provider.

    Returns (reachable, provider_name). Logs name-only; never the key value.
    """
    settings = get_settings()
    provider = settings.rag_embedding_provider  # "openai" | "ollama"
    if provider == "openai":
        return (bool(settings.openai_api_key), provider)
    if provider == "ollama":
        # Live-probe via /config/providers/health (which already wraps the
        # Ollama /api/tags HTTP call).
        body = await client.request(
            "knowledge[probe]", "GET", "/config/providers/health"
        )
        # response body is a list (httpx returns {"_raw": [...]} since the
        # body is not a dict — see _Client.request line 158-159).
        items = body.get("_raw", [])
        if isinstance(items, list):
            for entry in items:
                if isinstance(entry, dict) and entry.get("provider") == "ollama":
                    return (bool(entry.get("reachable")), provider)
    return (False, provider)
```

```python
# app/features/demo/pipeline.py — DemoContext extension (additive)
@dataclass
class DemoContext:
    # ... existing fields preserved ...

    # PRP-40 — additive context for the planning + knowledge phases.
    scenario_artifact_key: str | None = None     # 12-char artifact key parsed from artifact_uri
    price_cut_scenario_id: str | None = None     # showcase-price-cut-10pct id (Task 4)
    holiday_scenario_id: str | None = None       # showcase-holiday-uplift id (Task 5)
    embedding_unreachable: bool = False          # set by step_embedding_provider_probe
```

### List of tasks (dependency-ordered)

```yaml
Task 1:  Contract Probe (this PRP — output PRPs/ai_docs/prp-40-contract-probe-report.md)
Task 2:  Backend — additive path_prefix field on IndexProjectDocsRequest
Task 3:  Backend — additive helpers in app/features/demo/pipeline.py
Task 4:  Backend — step_scenario_simulate_and_save (planning phase)
Task 5:  Backend — step_multi_plan_compare (planning phase)
Task 6:  Backend — step_embedding_provider_probe (knowledge phase)
Task 7:  Backend — step_rag_index_subset (knowledge phase)
Task 8:  Backend — step_rag_retrieve_probe (knowledge phase)
Task 9:  Backend — _phase_table() RELATIVE-anchor insertion (planning + knowledge BEFORE verify)
Task 10: Frontend — PHASE_DEFS.ts extension (+ PHASE_DEFS.test.ts lockstep)
Task 11: Frontend — demo-step-card.tsx mini-summary helpers (+ tests)
Task 12: Frontend — showcase.tsx resolveInspectHref switch (+ tests)
Task 13: Backend tests — per-step happy-path + skip-gracefully suite
Task 14: Backend test — test_phase_table_showcase_rich_adds_planning_knowledge_steps
Task 15: Backend test — test_rag_service rejects path traversal
Task 16: Docs — extend docs/_base/RUNBOOKS.md with the 5 new step failure modes
Task 17: Dogfood (manual; checklist below) — verify C1..C5 against the running stack
```

### Per task pseudocode (the load-bearing parts)

```python
# ─────────────────────────────────────────────────────────────────────────
# Task 2 — Additive path_prefix on IndexProjectDocsRequest
# ─────────────────────────────────────────────────────────────────────────

# app/features/rag/schemas.py
# MODIFY IndexProjectDocsRequest:
#   - INJECT after the `include_root` field:
#       path_prefix: str | None = Field(default=None, max_length=200, ...)
#   - PRESERVE the three existing toggle fields exactly.
#   - PRESERVE ConfigDict(extra="forbid") (it ignores Optional defaults
#     correctly).

# app/features/rag/service.py
# MODIFY _discover_project_doc_files:
#   - FIND the `if request.include_docs:` branch.
#   - REPLACE the single `found += ...` line with a 6-line branch:
#       if request.path_prefix:
#           candidate = (self._base_dir / request.path_prefix).resolve()
#           base = self._base_dir.resolve()
#           # Guard: candidate MUST be inside self._base_dir.
#           if not str(candidate).startswith(str(base)):
#               raise ValueError(
#                   f"path_prefix escapes the project root: {request.path_prefix!r}"
#               )
#           found += [(p, "docs") for p in candidate.rglob("*.md")]
#       else:
#           found += [(p, "docs") for p in (self._base_dir / "docs").rglob("*.md")]
#   - PRESERVE the include_prps + include_root branches unchanged.

# ─────────────────────────────────────────────────────────────────────────
# Task 3 — Additive helpers in pipeline.py
# ─────────────────────────────────────────────────────────────────────────

# app/features/demo/pipeline.py
# MODIFY top-of-file imports:
#   - ADD `import re` (near the other stdlib imports).
# INJECT after line 237 (after _llm_key_present definition):
#   _ARTIFACT_KEY_RE = re.compile(r"model_([0-9a-f]+)(?:\.joblib)?$")
#
#   def _parse_artifact_key(artifact_uri: str) -> str:
#       ...  # see § Data models above
#
#   async def _embedding_provider_reachable(client: _Client) -> tuple[bool, str]:
#       ...  # see § Data models above

# INJECT after line 1115 (after PHASE_CLEANUP):
#   PHASE_PLANNING = "planning"   # PRP-40
#   PHASE_KNOWLEDGE = "knowledge" # PRP-40

# MODIFY DemoContext:
#   - INJECT after `bucketed_aggregated_metrics: ...` line:
#       scenario_artifact_key: str | None = None
#       price_cut_scenario_id: str | None = None
#       holiday_scenario_id: str | None = None
#       embedding_unreachable: bool = False

# ─────────────────────────────────────────────────────────────────────────
# Task 4 — step_scenario_simulate_and_save
# ─────────────────────────────────────────────────────────────────────────

async def step_scenario_simulate_and_save(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-40 — run a 10% price-cut simulation against the champion run, save it.

    Steps:
      1. GET /registry/aliases/demo-production → alias_body["run_id"] (registry uuid).
      2. GET /registry/runs/{run_id} → run_body["artifact_uri"].
      3. _parse_artifact_key(artifact_uri) → 12-char artifact-key.
      4. POST /scenarios/simulate {run_id=<key>, horizon=DEMO_HORIZON,
         assumptions={price: {change_pct: -0.10, start_date: <ctx.date_end-13>, end_date: <ctx.date_end>}}}
         → ScenarioComparison.
      5. POST /scenarios {name="showcase-price-cut-10pct", run_id=<key>, horizon=DEMO_HORIZON,
         assumptions=...same..., tags=["showcase","price"]} → ScenarioPlanResponse.scenario_id.
      6. ctx.price_cut_scenario_id = scenario_id; ctx.scenario_artifact_key = key.

    Status:
      - PASS on a successful save; detail =
        "plan=showcase-price-cut-10pct method={method} Δunits={units_delta:+.1f} Δrevenue={revenue_delta:+.2f}"
        step.data = {"scenario_id": ..., "method": ..., "units_delta": ...,
                     "revenue_delta": ..., "winner_run_id": ..., "artifact_key": ...}
      - FAIL if any of the 5 calls returns non-2xx (the _StepError propagates).
    """
    if ctx.date_end is None:
        return ("fail", "no date_end on ctx (status step did not populate it)", {})

    # 1+2 — resolve alias → run → artifact_uri (R16).
    alias_body = await client.request(
        "scenario_simulate_and_save[alias]", "GET",
        "/registry/aliases/demo-production",
    )
    winner_run_id = alias_body.get("run_id")
    if not isinstance(winner_run_id, str):
        return ("fail", "demo-production alias has no run_id", {})

    run_body = await client.request(
        "scenario_simulate_and_save[run]", "GET",
        f"/registry/runs/{winner_run_id}",
    )
    artifact_uri = run_body.get("artifact_uri")
    if not isinstance(artifact_uri, str):
        return ("fail", f"run {winner_run_id[:8]}... has no artifact_uri", {})

    # 3 — parse the 12-char artifact key.
    try:
        artifact_key = _parse_artifact_key(artifact_uri)
    except ValueError as exc:
        return ("fail", str(exc), {})
    ctx.scenario_artifact_key = artifact_key

    # 4+5 — build a price-cut assumption inside the horizon, simulate, save.
    horizon_start = ctx.date_end - timedelta(days=DEMO_HORIZON - 1)  # train_end + 1
    horizon_end = ctx.date_end  # final horizon day
    assumptions = {
        "price": {
            "change_pct": -0.10,
            "start_date": horizon_start.isoformat(),
            "end_date": horizon_end.isoformat(),
        }
    }

    # POST /scenarios persists the snapshot; we don't need to call /simulate
    # first (POST /scenarios runs the simulation internally and stores the
    # resulting ScenarioComparison). Read the saved snapshot back for the
    # method / units_delta / revenue_delta values.
    plan_body = await client.request(
        "scenario_simulate_and_save[save]", "POST", "/scenarios",
        json_body={
            "name": "showcase-price-cut-10pct",
            "run_id": artifact_key,
            "horizon": DEMO_HORIZON,
            "assumptions": assumptions,
            "tags": ["showcase", "price"],
        },
    )
    scenario_id = plan_body.get("scenario_id")
    comparison = plan_body.get("comparison") or {}
    method = comparison.get("method", "unknown")
    units_delta = float(comparison.get("units_delta", 0.0))
    revenue_delta = float(comparison.get("revenue_delta", 0.0))
    ctx.price_cut_scenario_id = scenario_id if isinstance(scenario_id, str) else None

    return (
        "pass",
        f"plan=showcase-price-cut-10pct method={method} "
        f"Δunits={units_delta:+.1f} Δrevenue={revenue_delta:+.2f}",
        {
            "scenario_id": scenario_id,
            "method": method,
            "units_delta": units_delta,
            "revenue_delta": revenue_delta,
            "winner_run_id": winner_run_id,
            "artifact_key": artifact_key,
        },
    )

# ─────────────────────────────────────────────────────────────────────────
# Task 5 — step_multi_plan_compare
# ─────────────────────────────────────────────────────────────────────────

async def step_multi_plan_compare(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-40 — save a second (holiday) plan, then compare both plans.

    Steps:
      1. POST /scenarios {name="showcase-holiday-uplift", run_id=ctx.scenario_artifact_key,
         horizon=DEMO_HORIZON, assumptions={holiday: {dates: [<one-day-in-horizon>]}},
         tags=["showcase","holiday"]} → ScenarioPlanResponse.scenario_id.
      2. POST /scenarios/compare {scenario_ids=[ctx.price_cut_scenario_id, holiday_id],
         rank_by="revenue_delta"} → MultiScenarioComparison.
      3. winner = comparison.scenarios[0].scenario_id (rank=1).

    Status:
      - PASS on a successful compare; detail =
        "winner={winner_name} ranked_by=revenue_delta"
      - WARN if the second-plan save returns 4xx with a clear detail (the
        first plan was saved OK so the visitor sees partial success). R19.
      - FAIL if /compare itself fails.
    """
    if ctx.price_cut_scenario_id is None or ctx.scenario_artifact_key is None:
        return ("fail", "price_cut plan not saved by previous step", {})
    if ctx.date_end is None:
        return ("fail", "no date_end on ctx", {})

    # 1 — second plan with a one-day holiday set inside the horizon.
    holiday_day = (ctx.date_end - timedelta(days=DEMO_HORIZON // 2)).isoformat()
    try:
        plan_body = await client.request(
            "multi_plan_compare[save]", "POST", "/scenarios",
            json_body={
                "name": "showcase-holiday-uplift",
                "run_id": ctx.scenario_artifact_key,
                "horizon": DEMO_HORIZON,
                "assumptions": {"holiday": {"dates": [holiday_day]}},
                "tags": ["showcase", "holiday"],
            },
        )
    except _StepError as exc:
        # R19 — second-plan save failed; surface as WARN so the visitor
        # sees the first plan was saved (partial success).
        return (
            "warn",
            f"holiday-plan save failed: {exc}; price-cut plan still saved",
            {"price_cut_scenario_id": ctx.price_cut_scenario_id},
        )
    holiday_id = plan_body.get("scenario_id")
    if not isinstance(holiday_id, str):
        return ("warn", "holiday-plan save returned no scenario_id", {})
    ctx.holiday_scenario_id = holiday_id

    # 2+3 — compare and rank.
    compare_body = await client.request(
        "multi_plan_compare[compare]", "POST", "/scenarios/compare",
        json_body={
            "scenario_ids": [ctx.price_cut_scenario_id, holiday_id],
            "rank_by": "revenue_delta",
        },
    )
    scenarios = compare_body.get("scenarios") or []
    if not scenarios:
        return ("fail", "/scenarios/compare returned empty ranked list", {})
    winner = scenarios[0]
    winner_id = winner.get("scenario_id", "unknown")
    winner_name = winner.get("name", "unknown")
    return (
        "pass",
        f"winner={winner_name} ranked_by=revenue_delta",
        {
            "winner_scenario_id": winner_id,
            "ranked_by": "revenue_delta",
            "ranked": [
                {
                    "scenario_id": s.get("scenario_id"),
                    "name": s.get("name"),
                    "units_delta": s.get("units_delta"),
                    "revenue_delta": s.get("revenue_delta"),
                    "rank": s.get("rank"),
                }
                for s in scenarios
            ],
        },
    )

# ─────────────────────────────────────────────────────────────────────────
# Task 6 — step_embedding_provider_probe
# ─────────────────────────────────────────────────────────────────────────

async def step_embedding_provider_probe(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-40 — probe the configured embedding provider. Always PASS.

    When reachable → ctx.embedding_unreachable=False; downstream knowledge
    steps run normally.
    When unreachable → ctx.embedding_unreachable=True; downstream knowledge
    steps SKIP with a clear detail. Pipeline still goes green.
    """
    reachable, provider = await _embedding_provider_reachable(client)
    ctx.embedding_unreachable = not reachable
    detail = (
        f"provider={provider} reachable={reachable}"
        if reachable
        else f"provider={provider} unreachable — knowledge phase will skip"
    )
    return ("pass", detail, {"provider": provider, "reachable": reachable})

# ─────────────────────────────────────────────────────────────────────────
# Task 7 — step_rag_index_subset
# ─────────────────────────────────────────────────────────────────────────

_USER_GUIDE_CURATED_FILES = frozenset({
    "docs/user-guide/getting-started.md",
    "docs/user-guide/dashboard-guide.md",
    "docs/user-guide/feature-reference.md",
    "docs/user-guide/agents-and-rag-guide.md",
    "docs/user-guide/advanced-forecasting-guide.md",
})

async def step_rag_index_subset(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-40 — index the curated 5-file user-guide subset.

    SKIPs when ctx.embedding_unreachable is set (set by the prior probe step).
    """
    if ctx.embedding_unreachable:
        return ("skip", "embedding provider unreachable", {})

    body = await client.request(
        "rag_index_subset", "POST", "/rag/index/project-docs",
        json_body={
            "include_docs": True,
            "include_prps": False,
            "include_root": False,
            "path_prefix": "docs/user-guide",   # PRP-40 additive field
        },
    )
    results = body.get("results") or []
    total_chunks = int(body.get("total_chunks", 0))
    failed = int(body.get("failed", 0))
    indexed = int(body.get("indexed", 0))
    updated = int(body.get("updated", 0))
    unchanged = int(body.get("unchanged", 0))
    curated_hits = sum(
        1 for r in results
        if isinstance(r, dict) and r.get("source_path") in _USER_GUIDE_CURATED_FILES
    )
    return (
        "pass",
        f"files_indexed={curated_hits}/5 chunks={total_chunks} failed={failed}",
        {
            "total_files": int(body.get("total_files", 0)),
            "indexed": indexed,
            "updated": updated,
            "unchanged": unchanged,
            "failed": failed,
            "total_chunks": total_chunks,
            "curated_hits": curated_hits,
        },
    )

# ─────────────────────────────────────────────────────────────────────────
# Task 8 — step_rag_retrieve_probe
# ─────────────────────────────────────────────────────────────────────────

async def step_rag_retrieve_probe(ctx: DemoContext, client: _Client) -> StepResult:
    """PRP-40 — semantic-retrieve probe against the curated corpus.

    SKIPs when ctx.embedding_unreachable. WARN (not FAIL) on zero hits.
    """
    if ctx.embedding_unreachable:
        return ("skip", "embedding provider unreachable", {})

    body = await client.request(
        "rag_retrieve_probe", "POST", "/rag/retrieve",
        json_body={"query": "How do I run the demo pipeline?", "top_k": 3},
    )
    results = body.get("results") or []
    if not results:
        return (
            "warn",
            "no hits — corpus indexed but query did not match",
            {"results_count": 0, "total_chunks_searched": body.get("total_chunks_searched", 0)},
        )
    top = results[0]
    title = top.get("source_path", "unknown")
    score = float(top.get("relevance_score", 0.0))
    return (
        "pass",
        f"top hit: {title} (score={score:.3f})",
        {
            "results_count": len(results),
            "top_source_path": title,
            "top_relevance_score": score,
        },
    )

# ─────────────────────────────────────────────────────────────────────────
# Task 9 — _phase_table() RELATIVE-anchor insertion
# ─────────────────────────────────────────────────────────────────────────

# app/features/demo/pipeline.py
# MODIFY _phase_table:
#   - INJECT after the `verify_steps` declaration, BEFORE the rows
#     accumulator loop:
#       planning_steps: list[tuple[str, StepFn]] = []
#       knowledge_steps: list[tuple[str, StepFn]] = []
#       if scenario is ScenarioPreset.SHOWCASE_RICH:
#           planning_steps = [
#               ("scenario_simulate_and_save", step_scenario_simulate_and_save),
#               ("multi_plan_compare", step_multi_plan_compare),
#           ]
#           knowledge_steps = [
#               ("embedding_provider_probe", step_embedding_provider_probe),
#               ("rag_index_subset", step_rag_index_subset),
#               ("rag_retrieve_probe", step_rag_retrieve_probe),
#           ]
#   - INJECT the planning + knowledge phase rows IMMEDIATELY BEFORE the
#     `rows += [(PHASE_VERIFY, ...)]` line (RELATIVE anchor: before VERIFY):
#       rows += [(PHASE_PLANNING, name, fn) for name, fn in planning_steps]
#       rows += [(PHASE_KNOWLEDGE, name, fn) for name, fn in knowledge_steps]
#   - PRESERVE every other existing row in the same order.

# ─────────────────────────────────────────────────────────────────────────
# Task 10 — Frontend PHASE_DEFS.ts extension
# ─────────────────────────────────────────────────────────────────────────

# frontend/src/components/demo/PHASE_DEFS.ts
# MODIFY ALL_STEPS:
#   - INSERT five new entries between the `register` row and the `verify`
#     row (RELATIVE anchor):
#       { phase: 'planning',  step: 'scenario_simulate_and_save', label: 'Simulate & save plan' },
#       { phase: 'planning',  step: 'multi_plan_compare',         label: 'Compare plans' },
#       { phase: 'knowledge', step: 'embedding_provider_probe',   label: 'Probe embedding provider' },
#       { phase: 'knowledge', step: 'rag_index_subset',           label: 'Index user-guide corpus' },
#       { phase: 'knowledge', step: 'rag_retrieve_probe',         label: 'Semantic-retrieve probe' },
# MODIFY SHOWCASE_RICH_STEP_NAMES:
#   - ADD all five new step names to the Set.
# MODIFY PHASE_ORDER:
#   - INSERT 'planning' and 'knowledge' BEFORE 'verify' in the array.
# MODIFY PHASE_LABEL:
#   - ADD planning: 'Planning' and knowledge: 'Knowledge'.

# frontend/src/components/demo/PHASE_DEFS.test.ts
# MODIFY the showcase_rich tuple list:
#   - INSERT five new tuples ['planning','scenario_simulate_and_save'],
#     ['planning','multi_plan_compare'], ['knowledge','embedding_provider_probe'],
#     ['knowledge','rag_index_subset'], ['knowledge','rag_retrieve_probe']
#     between ['decision','register'] and ['verify','verify'].
# MODIFY the PHASE_ORDER assertion:
#   - Extend to ['data','modeling','decision','planning','knowledge','verify','agent','cleanup'].

# ─────────────────────────────────────────────────────────────────────────
# Task 11 — demo-step-card.tsx mini-summaries
# ─────────────────────────────────────────────────────────────────────────

# frontend/src/components/demo/demo-step-card.tsx
# INJECT five new helpers next to BacktestBreakdown / RegisterDetail:
#   - ScenarioSummary({ data })       → renders plan name + method + Δunits + Δrevenue.
#   - CompareSummary({ data })        → renders winner + ranked_by + per-plan deltas.
#   - ProviderChip({ data })          → renders provider chip + reachable badge.
#   - IndexSummary({ data })          → renders curated_hits/5 + chunks + failed.
#   - RetrieveSummary({ data })       → renders top hit title + score.
# MODIFY the DemoStepCard render block:
#   - ADD five new `step.name === '...' && <Summary data={step.data} />` lines
#     before the existing showInspect branch.

# ─────────────────────────────────────────────────────────────────────────
# Task 12 — showcase.tsx resolveInspectHref extension
# ─────────────────────────────────────────────────────────────────────────

# frontend/src/pages/showcase.tsx
# MODIFY resolveInspectHref switch:
#   - INSERT five new case arms before the `default`:
#       case 'scenario_simulate_and_save': {
#         const id = typeof data.scenario_id === 'string' ? data.scenario_id : null
#         return id ? `${ROUTES.VISUALIZE.PLANNER}?scenario_id=${id}` : null
#       }
#       case 'multi_plan_compare':
#         return ROUTES.VISUALIZE.PLANNER
#       case 'embedding_provider_probe':
#         return ROUTES.ADMIN
#       case 'rag_index_subset':
#       case 'rag_retrieve_probe':
#         return ROUTES.KNOWLEDGE

# ─────────────────────────────────────────────────────────────────────────
# Task 13 — Backend per-step tests
# ─────────────────────────────────────────────────────────────────────────

# app/features/demo/tests/test_pipeline.py
# CREATE these new test functions (mirror the existing test_run_pipeline_*
# patterns + the conftest fixtures):
#   - test_scenario_simulate_and_save_step_happy_path
#       asserts scenario_id persisted + step.data has method/units_delta/revenue_delta.
#   - test_scenario_simulate_and_save_step_alias_missing
#       asserts FAIL on missing demo-production alias.
#   - test_multi_plan_compare_step_happy_path
#       asserts winner_scenario_id + ranked array.
#   - test_multi_plan_compare_step_second_save_fails_emits_warn
#       asserts WARN (not FAIL) when the second-plan POST returns 4xx (R19).
#   - test_embedding_provider_probe_step_reachable
#       asserts PASS + ctx.embedding_unreachable=False when openai_api_key is set.
#   - test_embedding_provider_probe_step_unreachable
#       monkeypatches settings.openai_api_key="" and the live Ollama probe;
#       asserts PASS + ctx.embedding_unreachable=True + the "knowledge phase
#       will skip" detail substring.
#   - test_rag_index_subset_step_happy_path
#       asserts curated_hits >= 1 + total_chunks > 0 (mocking the embedding
#       provider; the path-traversal guard tested separately).
#   - test_rag_index_subset_step_skips_when_provider_unreachable
#       asserts SKIP with detail "embedding provider unreachable" and zero
#       calls to /rag/* (verified via httpx ASGITransport recording).
#   - test_rag_retrieve_probe_step_happy_path
#       asserts PASS + top_source_path + top_relevance_score.
#   - test_rag_retrieve_probe_step_zero_hits_emits_warn
#       asserts WARN (not FAIL) on results=[].
#   - test_rag_retrieve_probe_step_skips_when_provider_unreachable
#       mirror of rag_index_subset skip test.

# ─────────────────────────────────────────────────────────────────────────
# Task 14 — Phase-table lockstep test
# ─────────────────────────────────────────────────────────────────────────

# app/features/demo/tests/test_pipeline.py
# MODIFY test_phase_table_showcase_rich_adds_v2_steps OR ADD a new test
# test_phase_table_showcase_rich_adds_planning_knowledge_steps:
#   - Asserts the showcase_rich row list equals the canonical 19-row list:
#       data: precheck/reset/seed/status/features/phase2_enrichment/historical_backfill
#       modeling: train/v2_train
#       decision: backtest/register
#       planning: scenario_simulate_and_save/multi_plan_compare
#       knowledge: embedding_provider_probe/rag_index_subset/rag_retrieve_probe
#       verify: verify
#       agent: agent
#       cleanup: cleanup

# ─────────────────────────────────────────────────────────────────────────
# Task 15 — Path-traversal guard test
# ─────────────────────────────────────────────────────────────────────────

# app/features/rag/tests/test_service.py
# CREATE test_index_project_docs_rejects_path_traversal:
#   - Calls IndexProjectDocsRequest(path_prefix="../../etc") in-process.
#   - Asserts service raises ValueError with message containing
#     "escapes the project root".

# ─────────────────────────────────────────────────────────────────────────
# Task 16 — RUNBOOKS.md extension
# ─────────────────────────────────────────────────────────────────────────

# docs/_base/RUNBOOKS.md
# MODIFY the "Showcase page (/showcase) pipeline fails at step X" section:
#   - ADD entries for the 5 new step failure modes following the same shape
#     as the existing entries (numbered list under the same heading).
```

### Integration Points

```yaml
DATABASE:
  - No new tables. No Alembic migration in PRP-40.
  - The two saved plans persist into the existing `scenario_plan` table
    via the existing `POST /scenarios` endpoint.

CONFIG:
  - No new settings. PRP-40 reuses `settings.rag_embedding_provider`,
    `settings.openai_api_key`, `settings.ollama_base_url` (all existing).

ROUTES:
  - No new HTTP routes. PRP-40 extends `app/features/demo/pipeline.py`
    (a helper module, not a route) and consumes existing routes on the
    scenarios / rag / config / registry slices.

SCHEMAS:
  - One additive field: `IndexProjectDocsRequest.path_prefix: str | None
    = None` (default preserves back-compat).

FRONTEND DEEP-LINKS:
  - scenario_simulate_and_save → /visualize/planner?scenario_id={id}
  - multi_plan_compare         → /visualize/planner
  - embedding_provider_probe   → /admin
  - rag_index_subset           → /knowledge
  - rag_retrieve_probe         → /knowledge

PHASE_DEFS lockstep:
  - Backend: `_phase_table()` returns the 19 (phase, step) tuples on
    SHOWCASE_RICH; non-showcase paths still return the 11-tuple base.
  - Frontend: PHASE_DEFS.ts `ALL_STEPS` carries 19 entries;
    `phaseDefsForScenario('demo_minimal')` filters down to 11.
```

---

## Validation Loop

### Level 1: Syntax + style + types

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/
uv run pyright app/
# Expected: zero errors. If errors, READ the error and fix.
```

### Level 2: Backend unit + integration tests

```bash
# Per-step unit suite (fast, no DB):
uv run pytest -v -m "not integration" app/features/demo/tests/test_pipeline.py

# Path-traversal guard test:
uv run pytest -v -m "not integration" app/features/rag/tests/test_service.py::test_index_project_docs_rejects_path_traversal

# Integration test (DB + showcase_rich end-to-end + key-stripped fixture for C3):
docker compose up -d
uv run alembic upgrade head
uv run pytest -v -m integration tests/test_e2e_demo.py
# Expected: wall-clock ≤ 240 s for showcase_rich (C4).
```

### Level 3: Frontend lint + types + tests

```bash
cd frontend
pnpm lint
pnpm tsc --noEmit -p tsconfig.app.json    # CRITICAL — project-scoped, not root
pnpm test --run

# Expected: zero TS errors, all vitest suites pass (including the lockstep
# tuple list and the 5 new Inspect deep-link tests).
```

### Level 4: Vertical-slice grep guard

```bash
# MUST be empty (PRP-40 never imports across feature slices):
git grep -nE "from app\.features\.(scenarios|rag|config|registry)" \
  app/features/demo/

# Also confirm the new helpers stay in pipeline.py (no new module under
# app/features/demo/):
ls app/features/demo/   # No new files — only pipeline.py + existing scaffolding modified.
```

### Level 5: Dogfood the running UI

(Manual — see "Final validation Checklist" below.)

---

## Final validation Checklist

- [ ] All five validation gates green (`ruff` / `ruff format` /
      `mypy --strict` / `pyright --strict` / `pytest`) — **C6**.
- [ ] `git grep` vertical-slice guard returns no rows.
- [ ] `pnpm tsc --noEmit -p tsconfig.app.json` clean (do NOT trust prior
      HANDOFF; cf. R7).
- [ ] Backend test `test_phase_table_showcase_rich_adds_planning_knowledge_steps`
      passes (19-row tuple list frozen).
- [ ] Frontend test `PHASE_DEFS.test.ts` passes (matching 19-row list).

### Manual dogfood (PRP-40-specific)

- [ ] **C1** — Fresh `showcase_rich` run on the dev host. Open
      `/visualize/planner`. Confirm:
      - `showcase-price-cut-10pct` is in the saved-plans library with
        tags `["showcase","price"]`.
      - `showcase-holiday-uplift` is in the saved-plans library with
        tags `["showcase","holiday"]`.
      - A multi-plan compare row ranks the two plans by `revenue_delta`.
- [ ] **C2** — Open `/knowledge`. Confirm:
      - The 5 curated user-guide files are visible with non-zero chunk
        counts.
      - Typing "how do I run the demo" into the UI semantic search
        returns at least one hit.
- [ ] **C3** — Skip-gracefully scenario:
      - `unset OPENAI_API_KEY && unset ANTHROPIC_API_KEY && unset GOOGLE_API_KEY`
        in the uvicorn env.
      - Stop ollama (`pkill ollama` or block its port).
      - Re-run `/showcase` on `showcase_rich`.
      - Confirm: `embedding_provider_probe` PASS, `rag_index_subset`
        SKIP, `rag_retrieve_probe` SKIP. Pipeline still goes green.
- [ ] **R17 verification** — the `scenario_simulate_and_save` step
      `detail` reports `method=heuristic` (the showcase winner is one of
      naive/seasonal_naive/moving_average/prophet_like; regression is
      NOT in the demo allow-list). If `method=model_exogenous` appears,
      investigate before merging.
- [ ] Step-card mini summaries render the expected values (visual
      regression check — screenshot before/after).
- [ ] Inspect buttons deep-link to the expected pages with the expected
      query strings.

---

## Anti-Patterns to Avoid

- ❌ Do NOT add `from app.features.scenarios.X import ...` (or rag /
  config / registry) anywhere in `app/features/demo/`. Drive every
  call over `httpx.ASGITransport`.
- ❌ Do NOT weaken `app/features/featuresets/tests/test_leakage.py` —
  the leakage spec stays load-bearing.
- ❌ Do NOT weaken `app/features/scenarios/tests/test_leakage.py` —
  scenarios' future-frame leakage spec stays load-bearing.
- ❌ Do NOT modify PRP-38 implementation (`step_v2_train`, `step_register`,
  `step_phase2_enrichment`, `step_historical_backfill`) — PRP-40 is
  additive on top of them.
- ❌ Do NOT use absolute phase indexes ("insert at row 12"). Use
  RELATIVE anchors ("insert BEFORE the verify phase row") so PRP-39
  (sibling) rebases cleanly.
- ❌ Do NOT block on PRP-39 merge. PRP-40 is independent of PRP-39;
  authoring + implementing + merging in parallel is intended.
- ❌ Do NOT make `path_prefix` REQUIRED on `IndexProjectDocsRequest`.
  Default MUST be None so existing clients keep working unchanged.
- ❌ Do NOT skip the path-traversal guard test on `path_prefix`. Even an
  Optional Pydantic field that lands in an `rglob` call is a security
  surface.
- ❌ Do NOT log API-key values in `_embedding_provider_reachable()`. Log
  the provider name + bool only, per `.claude/rules/security-patterns.md`.
- ❌ Do NOT bump `StepEvent` schema. New payload fields ride inside
  `StepEvent.data: dict[str, Any]`; no version key change.
- ❌ Do NOT add a new shadcn primitive when Card + Badge + Button cover
  the use case.
- ❌ Do NOT widen the `agent_require_approval` allow-list. PRP-40 makes
  no agent-tool calls; the HITL surface is unchanged.
- ❌ Do NOT add managed-cloud SDK code to the demo slice. Single-host
  vision is a hard constraint.

---

## Confidence

**Confidence: 8 / 10** for one-pass implementation success.

Strengths:
- Task 1 contract probe verified every cited contract against the live
  uvicorn on the dev host; R16 / R17 / R18 resolutions are concrete and
  unambiguous.
- The pattern for each of the 5 new step functions is well-precedented
  by `step_register` (multi-call) and `step_v2_train` (multi-call with
  registry + post-success enrichment).
- The frontend lockstep contract is enforced by an existing test pair.
- Helpers (`_parse_artifact_key`, `_embedding_provider_reachable`) are
  small + self-contained + testable.

Risks:
- Sibling parallel-merge with PRP-39: if both PRPs author their phase-
  table edits with relative anchors, the merge is mechanical. If PRP-39
  drifts to absolute indexes, the conflict surfaces at PHASE_DEFS.test.ts
  / `test_phase_table_*` time.
- The `_Client.request()` helper assumes a JSON dict body — when the
  endpoint returns a top-level JSON array (e.g., `GET /config/providers/health`
  returns `list[ProviderHealth]`), the wrapper returns `{"_raw": [...]}`.
  PRP-40's `_embedding_provider_reachable` handles this correctly (see
  pseudocode), but a careless implementer might miss it.
- The path-traversal guard on `path_prefix` is load-bearing security
  surface; missing the test or weakening the guard is a regression.

Mitigations baked in:
- Per-step happy + skip tests (`Task 13`) cover the wire contract.
- Vertical-slice grep guard (`Task 4` validation) blocks accidental
  cross-slice imports.
- The dogfood checklist explicitly calls out R17 (method=heuristic
  expected) and the key-stripped C3 scenario.
- The `path_prefix` test asserts traversal rejection at unit-test time.

---

## Unresolved Contract Assumptions

1. **The `_Client.request()` `{"_raw": ...}` non-dict body wrapping.**
   `_Client.request()` at `pipeline.py:158-159` returns `{"_raw": body}`
   when the JSON body is not a dict. `GET /config/providers/health`
   returns a list, so PRP-40's `_embedding_provider_reachable` reads
   `body.get("_raw", [])`. This is correct against the current
   `_Client.request()` implementation but is implicit — a future
   refactor of that helper could break it. Recommend a unit test that
   pins the wrapper's behaviour for list bodies (out of scope for
   PRP-40; flagged here for transparency).
2. **`POST /scenarios` snapshot-vs-recompute on response.** The route's
   docstring at `app/features/scenarios/routes.py:91-96` says the saved
   plan "stores both the raw assumptions and the full comparison
   snapshot, so a reloaded plan re-renders without recomputation". The
   PRP-40 step reads `comparison.units_delta` / `comparison.revenue_delta`
   / `comparison.method` straight off the POST response — verified by
   the Task 1 probe to work. If a future change makes `POST /scenarios`
   omit the embedded `comparison`, PRP-40's step would need to call
   `POST /scenarios/simulate` first and read the same fields off the
   simulate response (one extra round-trip).
3. **R5 — `feature_columns_count` for V1 baselines is N/A.** The
   PRP-40 step does NOT call `/forecasting/runs/{id}/feature-metadata`
   (only the V2 winner has that data, and PRP-38's `step_v2_train`
   already surfaces it). No assumption here; flagging for the implementer
   to NOT add this call by accident.
