name: "PRP — Showcase Workspace E4: Restore/Replay (issue #393)"
description: |

## Purpose

Implement the restore/replay epic of the showcase-workspace initiative (umbrella
#389): the E1 (#390) `showcase_workspace` rows become listable and loadable over
two new GET endpoints, the Showcase UI gains workspace controls (keep + name),
a server-backed workspace panel with **Load** (re-attach) and **Replay** (re-run)
actions, deep links to every object a kept run created, and a backend regression
test proving a same-config replay completes without 409/500 (blockers #146/#324
stay fixed). Parallel epic after Foundation E1; independent of E2 (#391, merged)
and E3 (#392, not started).

## Core Principles

1. **Context is King**: every reference below was verified against the live code on 2026-06-12 (branch `dev` @ 3194fe8, post-E1/E2 merge).
2. **Validation Loops**: each level is executable as written.
3. **Information Dense**: patterns cite exact file:line.
4. **Progressive Success**: backend read endpoints → frontend types/hooks → controls UI → workspace panel → replay test.
5. **Global rules**: follow CLAUDE.md / AGENTS.md; all five CI gates must pass; UI work follows `.claude/rules/ui-design.md` + `shadcn-ui.md`.

---

## Goal

An operator on `/showcase` can (a) mark a run **"Save as workspace"** with an
optional name, (b) see every saved workspace in a server-backed panel (newest
first, replacing the localStorage FIFO-5 for *workspace* runs — localStorage
stays for ephemeral runs only), (c) **Load** a workspace: its recorded config
(seed, scenario, reset, skip_seed, keep+name) populates the run controls and its
created objects (runs, plans, batch, alias, artifacts, grain) render as deep-link
cards — read-only, no run starts, and (d) **Replay** a workspace: the recorded
configuration is re-submitted verbatim through the existing WS run path with
`preservation="keep"`, producing a NEW workspace row, without any 409/500 from
the registry/scenario layers. Legacy clients and ephemeral runs behave
byte-identically to today.

**Deliverable** (all additive — no migration, no schema change, no new tables):

- `app/features/demo/schemas.py` — `WorkspaceListItem`, `WorkspaceDetailResponse`, `WorkspaceListResponse` (plain `BaseModel` + `from_attributes`, NOT strict).
- `app/features/demo/workspace.py` — `count_workspaces()` helper (list/get already exist, unrouted since E1).
- `app/features/demo/routes.py` — `GET /demo/workspaces` (paginated list) + `GET /demo/workspaces/{workspace_id}` (detail, 404 on miss) — the demo slice's first DB-dependent routes.
- `frontend/src/types/api.ts` — `DemoRunRequest` +`preservation`/`workspace_name`; `DemoRunResult` +`workspace_id`; new workspace types.
- `frontend/src/hooks/use-demo-pipeline.ts` — `DemoSummary.workspaceId` (from `pipeline_complete.data.workspace_id`).
- `frontend/src/hooks/use-workspaces.ts` — NEW TanStack Query hooks (list + detail), pattern: `use-scenarios.ts`.
- `frontend/src/components/demo/WorkspacePanel.tsx` — NEW list panel with Load/Replay actions.
- `frontend/src/components/demo/WorkspaceArtifactsPanel.tsx` — NEW re-attach deep-link card grid driven by `created_objects` (pattern: `InspectArtifactsPanel.tsx`).
- `frontend/src/components/demo/RunHistoryStrip.tsx` — skip-append when the summary carries a `workspaceId` (server is source of truth for workspace runs).
- `frontend/src/pages/showcase.tsx` — keep-checkbox + name input + seed input wired into the start frame; panels mounted.
- Tests: backend route unit + integration tests, the **replay regression** integration test (same config twice → both green, two distinct workspace rows), frontend vitest for the reducer/strip/panels/hooks.
- `docs/_base/API_CONTRACTS.md` — two new endpoint rows + E4 notes.

**Success definition**: all Success Criteria below check off, the five CI gates
are green, the frontend gates are green, and a manual browser dogfood on a
seeded stack shows save → list → load (links resolve) → replay (green pipeline,
new workspace row).

## Why

- E1 records workspaces but nothing reads them: `get_workspace`/`list_workspaces` are explicitly "unrouted in E1 -- consumed ... by the E4 restore/replay routes later" (`app/features/demo/workspace.py:15-17`).
- The only run memory in the UI is the localStorage FIFO-5 (`frontend/src/components/demo/RunHistoryStrip.tsx:21-22`), whose Replay button hardcodes `seed: 42` and drops the preservation fields (`RunHistoryStrip.tsx:133-138`) — it cannot restore a real configuration.
- Umbrella #389 success criterion: "A prior workspace can be restored: its config reloads into the UI and a replay with the same seed/preset completes without 409/500" + risk row: "add a replay regression test that runs the same config twice".
- Replay blockers are fixed but untested-for-regression: #146 (`registry/service.py` `_find_duplicate` now `.limit(1)` + `.scalars().first()`, ~lines 659-710) and #324 (champion via `ctx.winning_run_id`, parseable `safer_promote_flow` artifact_uri, `_restore_demo_alias_after_failure` at `pipeline.py:2708-2716`). No test currently runs the pipeline twice back-to-back (verified `tests/test_e2e_demo.py`).

## What

### Designed semantics — Restore vs Replay (required by issue #393)

| Action | Meaning | Effect |
|--------|---------|--------|
| **Load** (= restore, re-attach) | "Show me that run again" | Read-only. Recorded config populates the Showcase controls (scenario picker, Re-seed/Reset checkboxes, seed, keep-checkbox ON, name). Created objects render as deep-link cards from `created_objects` + grain columns. **No run starts; no rows are written.** |
| **Replay** (= re-run) | "Run that configuration again" | Load, then immediately `start()` through the existing WS path with the recorded `seed`/`scenario`/`reset`/`skip_seed` **verbatim** and `preservation="keep"` + the recorded `workspace_name` (names are non-unique by design, `models.py:61`). A NEW workspace row is created; the original row is never mutated. |

Decisions locked here (so implementation doesn't re-litigate):
1. **Replay is always `preservation="keep"`** — a replay is itself a workspace run; its row is the audit trail of the re-run.
2. **Config replays verbatim** — incl. `reset`/`skip_seed`. A `reset=true` workspace replays destructively; the panel renders a destructive badge on such rows (same styling language as the Reset checkbox, `showcase.tsx:218-228`).
3. **No provenance column** (`replayed_from`) in E4 — that needs a migration + request-field threading; deferred (note it in the PR description as a possible follow-up).
4. **No DELETE endpoint** — issue scope is "list/load + replay". Deletion is a future epic.
5. **localStorage split**: `RunHistoryStrip` keeps recording **ephemeral** runs only; a summary with `workspaceId != null` is NOT appended (umbrella risk table: "server is source of truth in workspace mode; localStorage stays for ephemeral runs only").

### User-visible behavior

- `GET /demo/workspaces?limit=&offset=` → `{"workspaces": [...], "total": N}`, newest first, `200` + empty list on an empty table (mirror `GET /scenarios`).
- `GET /demo/workspaces/{workspace_id}` → full row incl. `created_objects` + `result_summary`; `404 application/problem+json` when missing.
- `/showcase` controls gain: **Save as workspace** checkbox + **Workspace name** input (visible only when checked; client-side pattern validation) + a small **Seed** number input (today `handleRun` hardcodes `seed: 42`, `showcase.tsx:115` — restore is meaningless without a controllable seed).
- A **Workspaces** panel lists saved workspaces (name, scenario, seed, status, winner, created_at, destructive-reset badge) with **Load** and **Replay** buttons (both disabled while `isRunning`).
- Loading a workspace also renders its **artifacts panel**: deep-link cards for winning run, V2 run, scenario plans, batch, alias, grain-scoped forecast/backtest, agent session.
- After a kept run completes, the panel refreshes (query invalidation keyed on the new `summary.workspaceId`).

### Technical requirements

- The two GET routes use `Depends(get_db)` (`app/core/database.py:43`) — first DB dependency in `demo/routes.py`; they delegate to `workspace.get_workspace` / `workspace.list_workspaces` / new `count_workspaces` and build response models via `model_validate` (from_attributes).
- Response schemas are plain `BaseModel` — NOT `ConfigDict(strict=True)`; strict mode is for request bodies only (precedent + rationale: `demo/schemas.py:88-95` StepEvent docstring).
- 404 via `NotFoundError` from `app.core.exceptions` (pattern: `scenarios/routes.py:220-223`).
- The demo slice still imports no other feature slice (`app.core.*` / `app.shared.*` only).
- Frontend start frame sends `preservation`/`workspace_name` only when relevant (omitting them keeps legacy byte-compat; backend defaults apply).
- The replay regression test runs the in-process pipeline twice with the same config and asserts both runs green + two distinct `workspace_id`s.

### Success Criteria

- [ ] `GET /demo/workspaces` returns `200` + `{"workspaces": [], "total": 0}` on an empty table; after a `preservation="keep"` run it lists the row newest-first with config + `result_summary`.
- [ ] `GET /demo/workspaces/{id}` returns the full row (incl. `created_objects`); unknown id → `404` `application/problem+json`.
- [ ] Showcase: a run with "Save as workspace" checked sends `preservation="keep"` (+ name when filled); the panel shows the new row after `pipeline_complete`.
- [ ] Load populates scenario/seed/reset/skip_seed/keep/name controls and renders working deep links (at minimum: winning run → `/explorer/runs/{id}`).
- [ ] Replay re-runs the recorded config verbatim through `WS /demo/stream` and ends green with a NEW `workspace_id`; the original row is unchanged.
- [ ] Ephemeral runs: zero workspace queries on the write path (unchanged E1 behavior); `RunHistoryStrip` still records them; kept runs are NOT appended to localStorage.
- [ ] Backend replay regression test: same config twice → both `overall_status="pass"`, no 409/500, distinct workspace ids.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"` green; integration suite green; frontend `pnpm lint && pnpm test --run` green.

## All Needed Context

### Documentation & References

```yaml
# MUST READ — backend (verified 2026-06-12, dev @ 3194fe8)

- file: app/features/demo/workspace.py
  why: |
    get_workspace (line 157) and list_workspaces (line 173) ALREADY EXIST,
    take a caller-owned AsyncSession, and were written for these E4 routes
    (docstring lines 15-17). list_workspaces orders created_at.desc, id.desc
    (line 191) — the routes reuse them as-is. ADD count_workspaces here
    (pattern: scenarios/service.py:455 func.count().select_from()).

- file: app/features/demo/models.py
  why: |
    ShowcaseWorkspace columns (lines 59-81): workspace_id String(32) unique,
    name (nullable), status (running/completed/failed CHECK), seed, scenario,
    reset, skip_seed, store_id/product_id/date_start/date_end (nullable),
    created_objects JSONB, result_summary JSONB nullable, + TimestampMixin
    created_at/updated_at. The response schemas mirror EXACTLY these fields.

- file: app/features/demo/schemas.py
  why: |
    DemoRunRequest (29) already carries preservation (68) + workspace_name
    (72) + the requires-keep validator (80) — NO request changes in E4.
    StepEvent docstring (88-95) is the precedent for "response/event models
    are plain BaseModel, NOT strict". DemoRunResult.workspace_id (163)
    already exists. Append the three new workspace response models here.

- file: app/features/demo/routes.py
  why: |
    Current surface: POST /run (28-54), WS /stream (57-85), _error_event (88).
    Router prefix="/demo" tags=["demo"] (25). NO GET endpoints and NO DB
    dependency today — add both. ConflictError import precedent at line 18;
    add NotFoundError + Depends/Query/AsyncSession/get_db imports.

- file: app/features/scenarios/routes.py
  why: |
    THE list/get precedent to mirror: GET "" list with Query(ge/le) params
    (168-195), GET "/{id}" raising NotFoundError(message=...) when the
    service returns None (198-223). Copy the docstring/summary/description
    style verbatim.

- file: app/features/scenarios/schemas.py
  why: |
    Response-model precedent: ScenarioPlanResponse (323), ScenarioListItem
    (~362), ScenarioListResponse (390) — all ConfigDict(from_attributes=True),
    Field(...) with descriptions, list+total page shape. Mirror this shape.

- file: app/features/scenarios/service.py
  why: |
    list_plans (436-472): count_stmt = select(func.count()).select_from(...),
    rows query, total = int(await db.scalar(count_stmt) or 0). Use the same
    count idiom in workspace.count_workspaces.

- file: app/core/database.py
  why: get_db dependency (line 43) — yields request-scoped AsyncSession.

- file: app/core/exceptions.py
  why: NotFoundError -> RFC 7807 404 problem+json via registered handlers.

- file: app/features/demo/pipeline.py
  why: |
    DO NOT MODIFY in E4 (E1 hooks complete): create hook 2631-2635, finalize
    2719-2724, pipeline_complete.data.workspace_id 2747. #324 alias-restore
    safeguard 2708-2716. Cite only; replay flows through it unchanged.

- file: app/features/registry/service.py
  why: |
    _find_duplicate (~659-710) — the #146 fix (.limit(1) + .scalars().first()
    under the "detect" policy) is what makes back-to-back replays survive
    accumulated duplicate model_run rows. The replay regression test is the
    guard that keeps this true. READ-ONLY for this PRP.

- file: app/features/demo/tests/conftest.py
  why: |
    client fixture: ASGITransport over app.main.app (route unit tests
    monkeypatch the service/workspace fns — no DB needed). db_session
    fixture: real-Postgres session that WIPES showcase_workspace on teardown
    — reuse for the new integration route tests.

- file: app/features/demo/tests/test_routes.py
  why: |
    Route-test conventions: async tests over the client fixture,
    monkeypatch.setattr(service, "run_pipeline_sync", fake) (lines 40-52),
    409 path (55+). New GET unit tests monkeypatch
    app.features.demo.routes.workspace functions the same way.

- file: tests/test_e2e_demo.py
  why: |
    Integration e2e conventions: @pytest.mark.integration, uvicorn_subprocess
    fixture, urllib.request POST to /demo/run with json body + budget asserts
    (210-295, test_run_demo_showcase_rich_e2e). The replay regression test
    follows this exact shape with scenario=demo_minimal for speed.

# MUST READ — frontend (verified 2026-06-12)

- file: frontend/src/pages/showcase.tsx
  why: |
    313 lines. useDemoPipeline destructure (94-108), reseed/resetDb state
    (109-110), handleRun hardcoding seed 42 (114-116), RunHistoryStrip mount
    (168-172), controls Card (175-237: ScenarioPicker + Run + Stop + two
    Checkbox labels — add the keep-checkbox/name/seed inputs here),
    resolveInspectHref deep-link map (38-92 — the href vocabulary
    WorkspaceArtifactsPanel reuses).

- file: frontend/src/hooks/use-demo-pipeline.ts
  why: |
    DemoSummary (24-33) — ADD workspaceId: string | null. applyEvent
    pipeline_complete branch (117-127) — read event.data.workspace_id via the
    existing toStringOrNull helper. start() (238-246) accepts a full
    DemoRunRequest and uses req.scenario for the idle layout; NOTE it does
    NOT update the `scenario` picker state — Replay must call setScenario
    first, then start (same latent desync exists in today's strip replay).
    Exported pure helpers (applyEvent, initialState) are unit-tested in
    use-demo-pipeline.test.ts — extend there.

- file: frontend/src/components/demo/RunHistoryStrip.tsx
  why: |
    localStorage key forecastlab.showcase.runs.v1 (21), cap 5 (22),
    append-once-during-render pattern (71-86 — the sanctioned React pattern;
    copy it for the workspace-panel query invalidation trigger), onReplay
    hardcoded req (129-142). E4 change: skip append when
    summary.workspaceId != null. Its test file shows the localStorage-mock
    vitest conventions.

- file: frontend/src/components/demo/InspectArtifactsPanel.tsx
  why: |
    THE re-attach precedent: InspectCard {label, blurb, href|null,
    disabledReason} (15-20), buildCards (35+), disabled-card rendering, ROUTES
    deep links. WorkspaceArtifactsPanel mirrors this but reads
    created_objects JSONB + grain columns instead of live step.data.

- file: frontend/src/hooks/use-scenarios.ts
  why: |
    TanStack Query conventions to copy for use-workspaces.ts: api<T> calls,
    queryKey ['scenarios', {...}] shapes (28-47), invalidateQueries on
    mutation success (50-59).

- file: frontend/src/lib/api.ts
  why: api<T>(endpoint, {params}) wrapper; ApiError carries RFC 7807 detail.

- file: frontend/src/types/api.ts
  why: |
    Demo block (740-795): ScenarioPreset union (748), StepEvent (760),
    DemoRunRequest (778 — MISSING preservation/workspace_name), DemoRunResult
    (787 — MISSING workspace_id). Add the workspace types next to this block.

- file: frontend/src/lib/constants.ts
  why: |
    ROUTES map (2+): EXPLORER.RUNS, VISUALIZE.{PLANNER,BATCH,FORECAST,BACKTEST},
    OPS, CHAT, KNOWLEDGE, ADMIN. DEMO_WS_URL (76-78).

- file: frontend/src/components/demo/index.ts
  why: Barrel — export the two new components here.

- file: frontend/src/lib/uuid-utils.ts
  why: safeRandomUUID — NEVER call crypto.randomUUID directly (LAN/non-secure
    context crash, issue #332/PR #384; an ESLint guard enforces this).

# Issue / initiative context
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/393
  why: The epic this PRP implements (restore-vs-replay semantics designed above).
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/389
  why: Umbrella — success criteria, out-of-scope list (no export bundle, no
       per-phase config), replay-regression risk row.
- file: PRPs/PRP-showcase-workspace-E1-persistence-backbone.md
  why: The Foundation PRP — table design rationale, no-FK decision, E1 test map.
```

### Current Codebase tree (relevant subset)

```bash
app/features/demo/
├── models.py          # ShowcaseWorkspace @37 (E1; complete — untouched in E4)
├── pipeline.py        # E1 hooks complete — UNTOUCHED in E4
├── routes.py          # POST /run @28; WS /stream @57 — NO GETs, NO DB dep
├── schemas.py         # 166 lines; DemoRunRequest @29; DemoRunResult @130
├── service.py         # lock @19; PipelineBusyError @22 — untouched
├── workspace.py       # get @157 / list @173 exist; NO count helper
└── tests/             # conftest (client + db_session), test_{schemas,models,pipeline,routes,workspace}.py
frontend/src/
├── pages/showcase.tsx                    # 313 lines
├── hooks/use-demo-pipeline.ts            # DemoSummary @24; applyEvent @86
├── hooks/use-scenarios.ts                # TanStack precedent
├── components/demo/{RunHistoryStrip,InspectArtifactsPanel,ScenarioPicker,...}.tsx
└── types/api.ts                          # demo block @740-795
tests/test_e2e_demo.py                    # integration e2e; NO back-to-back run test
```

### Desired Codebase tree (files added/modified)

```bash
app/features/demo/
├── schemas.py                            # MOD — +WorkspaceListItem +WorkspaceDetailResponse +WorkspaceListResponse
├── workspace.py                          # MOD — +count_workspaces(db) -> int
├── routes.py                             # MOD — +GET /demo/workspaces +GET /demo/workspaces/{workspace_id}
└── tests/
    ├── test_routes.py                    # MOD — GET unit tests (workspace fns monkeypatched) + integration GET tests (db_session)
    └── test_schemas.py                   # MOD — response-model from_attributes round-trip
tests/test_e2e_demo.py                    # MOD — +test_demo_replay_same_config_twice (integration)
frontend/src/
├── types/api.ts                          # MOD — DemoRunRequest/+2, DemoRunResult/+1, +3 workspace types
├── hooks/use-demo-pipeline.ts            # MOD — DemoSummary.workspaceId
├── hooks/use-demo-pipeline.test.ts       # MOD — pipeline_complete carries workspace_id
├── hooks/use-workspaces.ts               # NEW — useWorkspaces / useWorkspace
├── hooks/index.ts                        # MOD — re-export (match existing barrel style)
├── components/demo/WorkspacePanel.tsx    # NEW — list + Load/Replay
├── components/demo/WorkspacePanel.test.tsx        # NEW
├── components/demo/WorkspaceArtifactsPanel.tsx    # NEW — created_objects deep links
├── components/demo/WorkspaceArtifactsPanel.test.tsx  # NEW
├── components/demo/RunHistoryStrip.tsx   # MOD — ephemeral-only append
├── components/demo/RunHistoryStrip.test.tsx  # MOD — kept-run not appended
├── components/demo/index.ts              # MOD — barrel exports
└── pages/showcase.tsx                    # MOD — controls + panels wiring
docs/_base/API_CONTRACTS.md               # MOD — 2 endpoint rows + E4 notes
```

### Known Gotchas & Library Quirks

```python
# CRITICAL — NO pipeline.py / models.py / migration changes in E4. The E1 hooks
#   and table are complete; replay flows through the existing run path. If you
#   think you need a schema change, you've scope-crept (provenance is deferred).

# CRITICAL — response models are NOT strict. Strict mode is a REQUEST-body
#   policy (security-patterns.md); StepEvent's docstring (schemas.py:88-95) is
#   the in-file precedent. Use ConfigDict(from_attributes=True) like
#   scenarios/schemas.py:323+. date_start/date_end are plain `date` fields —
#   fine on response models (test_strict_mode_policy only walks strict=True
#   request models).

# CRITICAL — route order: register the two GET routes on the SAME router
#   (prefix="/demo"). Paths /demo/workspaces and /demo/workspaces/{id} cannot
#   collide with /demo/run or the WS /demo/stream. Static-vs-param ordering is
#   irrelevant here (no /demo/workspaces/{x} value equals a static sibling).

# CRITICAL — replay regression test budget: use scenario=demo_minimal (11 steps,
#   fastest). First run: reset=true, skip_seed=false (clean deterministic data).
#   Second run: SAME body but skip_seed=true is WRONG for "verbatim" semantics —
#   replay the IDENTICAL body (reset=true, skip_seed=false) to prove the
#   harshest path (re-seed + re-register over accumulated rows) stays green.
#   Both with preservation="keep". Assert distinct workspace_ids.

# GOTCHA — useDemoPipeline.start(req) does NOT sync the scenario picker state
#   (use-demo-pipeline.ts:238-246 reads req.scenario only for the idle layout).
#   Replay/Load must call setScenario(ws.scenario) explicitly, then start().

# GOTCHA — workspace_name pattern is ^[a-z0-9][a-z0-9\-_]*$ (schemas.py:76).
#   Validate client-side (lowercase letters/digits/-/_ , must not start with
#   - or _) and disable Run with an inline hint on violation — otherwise the
#   operator gets a raw 422 problem+json from the WS error event.

# GOTCHA — sending workspace_name requires preservation="keep" (model_validator
#   schemas.py:80-85). The UI must OMIT workspace_name (not send "") when the
#   keep-checkbox is off or the input is empty.

# GOTCHA — workspace.scenario is stored as a plain string (models.py:67).
#   Type it ScenarioPreset on the frontend; values come from the enum, but the
#   replay path passes it through verbatim — backend re-validates on start.

# GOTCHA — replaying a reset=true workspace WIPES the database (destructive).
#   Render the destructive badge; do not add a confirm dialog (the run controls
#   already expose reset with the same severity styling — consistency wins).
#   sparse-preset workspaces may legitimately replay RED (RUNBOOKS incident 28:
#   expected-fail preset) — the panel shows recorded status, not a promise.

# GOTCHA — holiday_rush replays with reset=false ADD rows (union date window,
#   RUNBOOKS incident 28). Verbatim replay inherits this documented behavior.

# GOTCHA — never call crypto.randomUUID directly in frontend code — use
#   safeRandomUUID from @/lib/uuid-utils (issue #332; ESLint guard fires).

# GOTCHA — `pnpm tsc --noEmit` is VACUOUS on this repo (solution-style
#   tsconfig checks zero files) and `tsc -b` currently fails on dev with
#   PRE-EXISTING errors. Do not chase those. The real frontend gates that must
#   be green: `pnpm lint && pnpm test --run`. Verify your new files compile by
#   their vitest imports + eslint.

# GOTCHA — shadcn: every primitive needed (card, button, checkbox, input,
#   badge, skeleton) is ALREADY installed under frontend/src/components/ui/.
#   Do NOT run shadcn add. If you believe a new primitive is required, stop —
#   recheck the design (rule: .claude/rules/shadcn-ui.md; CLI pin gotchas in
#   memory shadcn-cli-version-pin).

# GOTCHA — repo has mixed CRLF/LF line endings; check `git diff --stat` before
#   committing (Write/Edit emit LF — fine for NEW files; for showcase.tsx /
#   routes.py edits verify the diff is surgical).

# GOTCHA — mypy --strict AND pyright --strict gate merge: annotate route params
#   (AsyncSession = Depends(get_db)), `-> None` on tests, full fixture types.

# COORDINATION — E3 (#392, workspace-tagged scenario plans) is an open parallel
#   epic touching pipeline.py + scenario tags. No shared files with E4 except
#   docs/_base/API_CONTRACTS.md — keep that edit additive and self-contained.

# RUNTIME-VERIFICATION LOG (per prp-create step 3):
#   - workspace.get_workspace/list_workspaces signatures — read workspace.py:157,173 (2026-06-12)
#   - ShowcaseWorkspace full column set — read models.py:59-89 (2026-06-12)
#   - DemoRunRequest already has preservation/workspace_name — read schemas.py:64-85
#   - pipeline_complete.data.workspace_id emitted — read pipeline.py:2747
#   - #146 fix present (.limit(1)+.scalars().first()) — Explore-agent verified registry/service.py:659-710
#   - #324 fix present (winning_run_id champion + alias-restore) — read pipeline.py:2708-2716
#   - frontend ui/input.tsx exists — `ls frontend/src/components/ui/` (2026-06-12)
#   - No third-party API claims beyond in-repo working patterns (func.count,
#     from_attributes, TanStack useQuery) — no import probe required.
```

## Implementation Blueprint

### Data models and structure

```python
# app/features/demo/schemas.py — APPEND (mirror scenarios/schemas.py:362-397 shape)

class WorkspaceListItem(BaseModel):
    """A compact row in the saved-workspaces list (E4, issue #393)."""

    model_config = ConfigDict(from_attributes=True)

    workspace_id: str = Field(..., description="Unique external identifier (UUID hex).")
    name: str | None = Field(default=None, description="Optional human label.")
    status: str = Field(..., description="running / completed / failed.")
    seed: int = Field(..., description="Seeder seed the run was started with.")
    scenario: str = Field(..., description="Seeder scenario preset value.")
    reset: bool = Field(..., description="Whether the run wiped the database first.")
    skip_seed: bool = Field(..., description="Whether the run skipped the seed step.")
    result_summary: dict[str, Any] | None = Field(
        default=None, description="Winner / WAPE / wall-clock display payload."
    )
    created_at: datetime = Field(..., description="When the run was recorded (UTC).")


class WorkspaceDetailResponse(WorkspaceListItem):
    """Full workspace row incl. created objects (E4, issue #393)."""

    store_id: int | None = Field(default=None, description="Showcase grain store id.")
    product_id: int | None = Field(default=None, description="Showcase grain product id.")
    date_start: date | None = Field(default=None, description="Seeded window start.")
    date_end: date | None = Field(default=None, description="Seeded window end.")
    created_objects: dict[str, Any] = Field(
        default_factory=dict,
        description="Soft-reference ids of everything the run created.",
    )


class WorkspaceListResponse(BaseModel):
    """A page of saved workspaces, newest first (E4, issue #393)."""

    model_config = ConfigDict(from_attributes=True)

    workspaces: list[WorkspaceListItem] = Field(
        ..., description="Saved workspaces for the current page; empty when none."
    )
    total: int = Field(..., ge=0, description="Total saved workspaces.")
```

```typescript
// frontend/src/types/api.ts — extend the demo block (after line 795)
export interface DemoRunRequest {
  seed?: number
  reset?: boolean
  skip_seed?: boolean
  scenario?: ScenarioPreset
  // E4 (#393) — preservation policy (E1 backend fields, first UI exposure).
  preservation?: 'ephemeral' | 'keep'
  workspace_name?: string
}
// DemoRunResult: + workspace_id: string | null

export interface WorkspaceListItem {
  workspace_id: string
  name: string | null
  status: 'running' | 'completed' | 'failed'
  seed: number
  scenario: ScenarioPreset
  reset: boolean
  skip_seed: boolean
  result_summary: Record<string, unknown> | null
  created_at: string
}
export interface WorkspaceDetail extends WorkspaceListItem {
  store_id: number | null
  product_id: number | null
  date_start: string | null
  date_end: string | null
  created_objects: Record<string, unknown>
}
export interface WorkspaceListResponse {
  workspaces: WorkspaceListItem[]
  total: number
}
```

### List of tasks (dependency order)

```yaml
Task 1 — branch & issue hygiene:
  RUN: git switch dev && git pull && git switch -c feat/showcase-workspace-restore-replay
  VERIFY: gh issue view 393 --json state   # open

Task 2 — MODIFY app/features/demo/schemas.py:
  - ADD import: date (datetime is already imported at schemas.py:11)
  - APPEND WorkspaceListItem / WorkspaceDetailResponse / WorkspaceListResponse (blueprint above)
  - Docstring note: response models, from_attributes, NOT strict (StepEvent precedent)

Task 3 — MODIFY app/features/demo/workspace.py:
  - ADD: async def count_workspaces(db: AsyncSession) -> int
      # select(func.count()).select_from(ShowcaseWorkspace); int(await db.scalar(...) or 0)
      # pattern: scenarios/service.py:455,467
  - UPDATE module docstring line 15-17 ("unrouted in E1") -> note E4 routes them

Task 4 — MODIFY app/features/demo/routes.py:
  - ADD imports: Depends, Query (fastapi); AsyncSession; get_db; NotFoundError;
    workspace module; the three new schemas
  - ADD GET "/workspaces" -> WorkspaceListResponse
      # limit: Query(default=20, ge=1, le=100), offset: Query(default=0, ge=0)
      # rows = await workspace.list_workspaces(db, limit=limit, offset=offset)
      # total = await workspace.count_workspaces(db)
      # WorkspaceListResponse(workspaces=[WorkspaceListItem.model_validate(r) for r in rows], total=total)
  - ADD GET "/workspaces/{workspace_id}" -> WorkspaceDetailResponse
      # row = await workspace.get_workspace(db, workspace_id)
      # if row is None: raise NotFoundError(message=f"Workspace not found: {workspace_id}")
      # mirror scenarios/routes.py:198-223 docstring style
  - Place both ABOVE the WS handler for file readability (no routing semantics)

Task 5 — backend tests:
  - MODIFY app/features/demo/tests/test_schemas.py (unit):
      # WorkspaceListItem.model_validate(orm-like SimpleNamespace/ShowcaseWorkspace(), from_attributes)
      # detail model carries created_objects verbatim
  - MODIFY app/features/demo/tests/test_routes.py:
      UNIT (monkeypatch app.features.demo.routes.workspace):
        - test_list_workspaces_empty -> 200 {"workspaces": [], "total": 0}
        - test_list_workspaces_passes_pagination -> limit/offset forwarded
        - test_get_workspace_404 -> problem+json content-type, status 404
        - test_get_workspace_success -> detail fields round-trip
        # NOTE: monkeypatched fns never touch db -> get_db yields an unused
        # session; no DB needed (session connects lazily on first query)
      INTEGRATION (@pytest.mark.integration, db_session fixture seeds rows):
        - insert 3 rows via db_session -> GET list newest-first, total=3
        - GET detail by workspace_id -> created_objects round-trips JSONB
  - MODIFY tests/test_e2e_demo.py (@pytest.mark.integration):
      test_demo_replay_same_config_twice(uvicorn_subprocess):
        # body = {"seed": 42, "reset": true, "skip_seed": false,
        #         "scenario": "demo_minimal", "preservation": "keep",
        #         "workspace_name": "replay-regression"}
        # POST /demo/run twice sequentially (urllib pattern, lines 210-250).
        # Assert: both 200 + overall_status == "pass" (replay blockers
        # #146/#324 regression guard); workspace_id non-null and DIFFERENT
        # across the two runs; GET /demo/workspaces lists >= 2 rows named
        # replay-regression with status completed.

Task 6 — MODIFY frontend/src/types/api.ts:
  - DemoRunRequest += preservation? / workspace_name?  (comment: E4 #393)
  - DemoRunResult += workspace_id: string | null
  - ADD WorkspaceListItem / WorkspaceDetail / WorkspaceListResponse

Task 7 — MODIFY frontend/src/hooks/use-demo-pipeline.ts (+ test):
  - DemoSummary += workspaceId: string | null
  - applyEvent pipeline_complete: workspaceId: toStringOrNull(event.data.workspace_id)
  - test: pipeline_complete event with workspace_id -> summary.workspaceId set;
    absent key -> null (legacy back-compat)

Task 8 — CREATE frontend/src/hooks/use-workspaces.ts (pattern: use-scenarios.ts):
  - useWorkspaces(limit = 20):
      useQuery({ queryKey: ['workspaces', { limit }],
                 queryFn: () => api<WorkspaceListResponse>('/demo/workspaces', { params: { limit } }) })
  - useWorkspace(workspaceId: string, enabled = true):
      queryKey ['workspaces', workspaceId]; enabled: enabled && !!workspaceId
  - Re-export from hooks/index.ts (match existing barrel entries)

Task 9 — CREATE frontend/src/components/demo/WorkspacePanel.tsx (+ test):
  - Props: { onLoad: (ws: WorkspaceListItem) => void,
             onReplay: (ws: WorkspaceListItem) => void,
             isRunning: boolean,
             lastWorkspaceId: string | null }   # summary.workspaceId — triggers refetch
    # RESOLVED design: props receive the LIST item; the PAGE resolves the full
    # detail via useWorkspace(selectedId) and only then setLoadedWorkspace —
    # WorkspaceArtifactsPanel needs detail-only created_objects. Replay needs
    # only list-item fields (seed/scenario/reset/skip_seed/name) — no detail
    # fetch required on the replay path.
  - useWorkspaces() list; invalidate ['workspaces'] when lastWorkspaceId changes
    (append-once-during-render pattern, RunHistoryStrip.tsx:71-86, or a
    useEffect keyed on lastWorkspaceId — syncing to an external system).
  - Row: name (or workspace_id slice), scenario badge, seed, status color
    (pass green / fail red — RunHistoryStrip styling 118-126), winner from
    result_summary, created_at toLocaleString, DESTRUCTIVE badge when reset.
  - Buttons: Load + Replay (variant outline, size sm), disabled when isRunning.
    Per the RESOLVED design above: the panel stays dumb (list items only);
    detail fetching lives in the page (Task 12).
  - Render null-state: "No saved workspaces yet" muted text (do NOT hide the
    panel entirely — discoverability of the new feature).

Task 10 — CREATE frontend/src/components/demo/WorkspaceArtifactsPanel.tsx (+ test):
  - Props: { workspace: WorkspaceDetail }
  - Mirror InspectArtifactsPanel InspectCard shape (label/blurb/href/disabledReason).
  - Cards from created_objects (keys per workspace.py:_collect_created_objects:88-101):
      winning_run_id        -> `${ROUTES.EXPLORER.RUNS}/${id}`
      v2_run_id             -> `${ROUTES.EXPLORER.RUNS}/${id}`
      scenario_plan_ids[]   -> `${ROUTES.VISUALIZE.PLANNER}?scenario_id=${id}` (one card per plan, label Plan 1/2)
      batch_id              -> `${ROUTES.VISUALIZE.BATCH}/${id}`
      alias                 -> ROUTES.OPS
      agent_session_id      -> ROUTES.CHAT (blurb: session likely expired — link is the chat surface)
      grain (store_id+product_id cols) -> FORECAST + BACKTEST query links
        (`?store_id=&product_id=` — resolveInspectHref vocabulary, showcase.tsx:46-57)
  - Missing key -> disabled card with disabledReason (InspectArtifactsPanel pattern).

Task 11 — MODIFY frontend/src/components/demo/RunHistoryStrip.tsx (+ test):
  - In the append-once block (71-86): skip append when summary.workspaceId is
    non-null (comment: E4 #393 — server-backed workspaces own kept runs).
  - Test: summary with workspaceId -> items unchanged; without -> appended.

Task 12 — MODIFY frontend/src/pages/showcase.tsx:
  - State: keepWorkspace (bool), workspaceName (string), seed (number, default 42),
    selectedWorkspaceId (string | null).
  - Detail resolution (RESOLVED design from Task 9): const { data: loadedWorkspace } =
    useWorkspace(selectedWorkspaceId ?? '', !!selectedWorkspaceId) — the page,
    not the panel, owns the detail fetch; WorkspaceArtifactsPanel renders only
    when the detail query has data.
  - Controls card: ADD Seed <Input type="number"> (small, labeled), ADD
    "Save as workspace" Checkbox (same label pattern as Re-seed, 206-216), ADD
    name <Input> shown when checked, with inline pattern-violation hint
    (^[a-z0-9][a-z0-9\-_]*$) that disables Run.
  - handleRun: build req { seed, skip_seed: !reseed, reset: resetDb, scenario,
    ...(keepWorkspace ? { preservation: 'keep' as const,
        ...(workspaceName ? { workspace_name: workspaceName } : {}) } : {}) }
  - onLoad(ws: WorkspaceListItem): setScenario(ws.scenario); setSeed(ws.seed);
    setReseed(!ws.skip_seed); setResetDb(ws.reset); setKeepWorkspace(true);
    setWorkspaceName(ws.name ?? ''); setSelectedWorkspaceId(ws.workspace_id)
    # useWorkspace then resolves the detail -> WorkspaceArtifactsPanel renders
  - onReplay(ws: WorkspaceListItem): onLoad(ws) THEN start({ seed: ws.seed, scenario: ws.scenario,
    reset: ws.reset, skip_seed: ws.skip_seed, preservation: 'keep',
    ...(ws.name ? { workspace_name: ws.name } : {}) })
    # setScenario before start — picker-desync gotcha
  - Mount <WorkspacePanel ... lastWorkspaceId={summary?.workspaceId ?? null} />
    near RunHistoryStrip; mount <WorkspaceArtifactsPanel workspace={loadedWorkspace}/>
    when loadedWorkspace && phase === 'idle' (a started run replaces it with live cards).

Task 13 — MODIFY docs/_base/API_CONTRACTS.md:
  - Endpoint table, after the demo WS row:
      | demo | GET | `/demo/workspaces` | E4 (#393) — list saved showcase workspaces, newest first (`limit`/`offset`); `200` + empty list on an empty table |
      | demo | GET | `/demo/workspaces/{workspace_id}` | E4 (#393) — full workspace row incl. `created_objects` soft references; `404` when missing |
  - WS /demo/stream section: append an E4 note — the start frame's E1
    preservation fields are now exercised by the Showcase UI; replay re-submits
    a recorded config verbatim with preservation="keep".

Task 14 — gates, dogfood, commit, PR:
  - Backend gates + integration suite (Validation Loop below)
  - Frontend: pnpm lint && pnpm test --run
  - Browser dogfood via the webapp-testing skill (CLAUDE.md workflow step 4):
    seeded stack -> save -> list -> load -> links -> replay green
  - git diff --stat (CRLF noise check)
  - COMMITS (reference #393, no AI trailer), e.g.:
      feat(api): expose showcase workspace list and detail endpoints (#393)
      feat(ui): add workspace restore and replay to showcase page (#393)
      test(api): add demo replay same-config regression test (#393)
      docs(api): document workspace restore endpoints (#393)
  - PR into dev; title `feat(api,ui): showcase workspace restore/replay (#393)`
```

### Integration Points

```yaml
DATABASE: none — E4 reads the E1 table; no migration.

CONFIG: none — no new settings or env vars.

ROUTES: two GETs on the existing demo router (app/main.py:156 wiring unchanged).

FRONTEND: showcase page only; no new React Router routes (deep links target
  existing pages). New components exported via components/demo/index.ts barrel.

DOCS: docs/_base/API_CONTRACTS.md only (Task 13). RUNBOOKS/DOMAIN_MODEL sweeps
  belong to the E5 release gate — do not scope-creep them here.
```

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
cd frontend && pnpm lint
# Expected: clean. Both Python type checkers are --strict and gate merge.
# (pnpm tsc --noEmit is vacuous on this repo — lint + vitest are the JS gates.)
```

### Level 2: Unit Tests (no DB)

```bash
uv run pytest app/features/demo -v -m "not integration"
uv run pytest app/core/tests/test_strict_mode_policy.py -v   # AST walker still green
cd frontend && pnpm test --run
# New/changed: test_routes GET unit tests (workspace fns monkeypatched),
# test_schemas from_attributes round-trip, use-demo-pipeline workspaceId,
# WorkspacePanel/WorkspaceArtifactsPanel/RunHistoryStrip vitest.
```

### Level 3: Integration (real Postgres)

```bash
docker compose up -d && uv run alembic upgrade head
uv run pytest app/features/demo -v -m integration
# Workspace GET routes against seeded rows (db_session fixture wipes on teardown).

# Replay regression (slow — runs the demo pipeline twice; needs the e2e harness):
uv run pytest tests/test_e2e_demo.py::test_demo_replay_same_config_twice -v -m integration
```

### Level 4: Manual smoke + browser dogfood (seeded local stack, uvicorn :8123)

```bash
# 1. Keep-run + list + detail round-trip
curl -s -X POST http://localhost:8123/demo/run -H 'Content-Type: application/json' \
  -d '{"skip_seed": true, "preservation": "keep", "workspace_name": "e4-smoke"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['workspace_id'])"
curl -s "http://localhost:8123/demo/workspaces?limit=5" | python3 -m json.tool | head -30
curl -s "http://localhost:8123/demo/workspaces/<id-from-above>" | python3 -m json.tool | head -40
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" \
  http://localhost:8123/demo/workspaces/deadbeefdeadbeefdeadbeefdeadbeef   # 404 problem+json

# 2. Browser dogfood (webapp-testing skill / agent-browser):
#    /showcase -> tick "Save as workspace", name "e4-dogfood", Run -> green ->
#    panel shows the row -> Load -> controls repopulate + artifact links resolve
#    (winning run opens /explorer/runs/{id}) -> Replay -> second green run ->
#    panel shows TWO rows named e4-dogfood -> ephemeral run -> localStorage
#    strip appends it, workspace panel does NOT.
```

## Final validation Checklist

- [ ] All five gates green: `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"`
- [ ] Integration suite green: `uv run pytest -v -m integration` (fresh docker-compose DB)
- [ ] Replay regression test green: same config twice → both pass, distinct workspace ids
- [ ] Frontend gates green: `pnpm lint && pnpm test --run`
- [ ] Legacy behavior byte-identical: ephemeral runs write no rows; start frames without new keys validate; `GET /demo/workspaces` on empty table → `200 {"workspaces": [], "total": 0}`
- [ ] Browser dogfood passes (Level 4 step 2) — UI verified in a real browser per `.claude/rules/ui-design.md`
- [ ] `git diff --stat` shows surgical diffs (no CRLF whole-file noise)
- [ ] docs/_base/API_CONTRACTS.md updated additively
- [ ] Commits formatted `feat(api)/feat(ui)/test(api)/docs(api): ... (#393)`, no AI trailer; PR into dev

---

## Anti-Patterns to Avoid

- ❌ Don't touch `pipeline.py`, `models.py`, or migrations — E4 is read-endpoints + UI + tests only.
- ❌ Don't add `replayed_from` provenance, DELETE endpoints, or export bundles — out of scope (umbrella #389).
- ❌ Don't make the workspace response models strict — strict mode is request-body policy.
- ❌ Don't mutate the original workspace row on replay — replay creates a new row, period.
- ❌ Don't remove the localStorage RunHistoryStrip — it stays for ephemeral runs only.
- ❌ Don't call `crypto.randomUUID` directly — `safeRandomUUID` (ESLint-enforced).
- ❌ Don't run `shadcn add` — every needed primitive is already installed.
- ❌ Don't chase pre-existing `tsc -b` errors — lint + vitest are the JS gates.
- ❌ Don't import another feature slice from `app/features/demo/` — core/shared only.

## Confidence Score

**8.5/10** for one-pass implementation success. The backend half is a near-copy
of the scenarios list/get precedent over helpers E1 deliberately pre-built for
this epic, and the restore-vs-replay semantics the issue required designing are
fully specified above. The deductions: (a) the showcase.tsx wiring touches many
small pieces (controls, two new panels, picker-desync ordering) where a missed
interaction costs an iteration, and (b) the replay regression test runs the real
pipeline twice and may surface environment-dependent flakiness (wall-clock,
accumulated rows) that needs tuning rather than code fixes.
