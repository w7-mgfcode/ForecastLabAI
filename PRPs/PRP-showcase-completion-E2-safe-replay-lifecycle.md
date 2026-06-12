name: "PRP — Showcase Completion E2: Safe Replay & Workspace Lifecycle (issue #408)"
description: |

## Purpose

Implement the safe-replay + workspace-lifecycle epic of the showcase-completion
initiative (umbrella #406): an explicit confirmation step (with preview/diff)
before every replay — destructive copy when `reset=true` — lineage rendering of
the E1 `replayed_from_workspace_id` chain, full lifecycle management on the
saved-workspaces panel (rename / archive / pin / notes / tags / search /
filter / sort / multi-select delete), a two-workspace compare view, and the
folded-in ops slice: artifact-link liveness checks with dead-link warnings on
soft references plus a per-workspace health summary (partial-run warning
included). Parallel epic after Foundation E1 (#407) — **execution starts only
AFTER E1 merges**; this PRP treats E1's epic body as a frozen contract (every
dependency on it is tagged `CONTRACT(E1)` below).

## Core Principles

1. **Context is King**: every reference below was verified against the live code on 2026-06-12 (branch `dev`, post-#404/#405 merge — E1 #407 NOT yet merged; see the E1-reconciliation task).
2. **Validation Loops**: each level is executable as written.
3. **Information Dense**: patterns cite exact file:line.
4. **Progressive Success**: backend list-filters + health endpoint → frontend types/hooks → confirm/diff dialog → lifecycle panel rework → lineage → compare page → docs.
5. **Global rules**: follow CLAUDE.md / AGENTS.md; all five CI gates must pass; UI work follows `.claude/rules/ui-design.md` + `.claude/rules/shadcn-ui.md`.

---

## Goal

An operator on `/showcase` can:

- (a) **Replay safely** — clicking Replay opens a confirmation dialog showing a
  preview/diff: the recorded config (seed / scenario / reset / skip_seed /
  name) side-by-side with the exact `DemoRunRequest` about to be sent, any
  divergence highlighted. When the recorded config has `reset=true`, the
  dialog carries explicit destructive copy ("Replaying this workspace WIPES
  the database") and a destructive-styled confirm button. No replay starts
  without confirmation.
- (b) **See lineage** — a workspace created by a replay carries a "replay"
  badge in the list; the loaded-workspace view renders the
  `replayed_from_workspace_id` chain (newest → original), with dangling
  ancestors (deleted rows) marked rather than erroring.
- (c) **Manage the library** — per-row actions: rename, edit notes, edit tags,
  pin/unpin, archive/unarchive (all via the E1 `PATCH /demo/workspaces/{id}`),
  plus the existing single delete. The list gains a search box (name), a
  show-archived toggle (archived hidden by default), a tag filter, and an
  allow-listed sort; pinned rows always sort first.
- (d) **Multi-select delete** — checkbox per row, "Delete selected (N)" behind
  one confirmation dialog, implemented as N sequential single
  `DELETE /demo/workspaces/{id}` calls. **No new bulk endpoint** (metadata-only
  singles; vision-compatible — no "wipe everything" operation).
- (e) **Compare two workspaces** — select exactly two rows → Compare navigates
  to a new deep-linkable page (`/showcase/compare?a=&b=`) mirroring the
  run-compare two-picker pattern: config diff, result-summary diff (winner /
  WAPE delta / wall-clock), created-objects presence matrix, lineage relation.
- (f) **See link health** — loading a workspace probes its soft references
  (model runs, scenario plans, alias, batch, agent session, E1 `job_ids`)
  through a new backend aggregation endpoint
  `GET /demo/workspaces/{id}/health`; dead references render a warning marker
  on the artifact cards and a per-workspace health summary chip shows
  alive/dead counts plus a partial-run warning when the run never completed.

**Deliverable** (all additive — no migration in E2; the schema delta is E1's):

- `app/features/demo/workspace.py` — `list_workspaces` / `count_workspaces`
  gain filter/sort parameters (`q`, `tags`, `include_archived`, `sort_by`,
  `sort_order`; pinned-first ordering).
- `app/features/demo/link_health.py` — NEW: in-process soft-reference probe
  module (httpx `ASGITransport`, mirroring `pipeline._Client`).
- `app/features/demo/schemas.py` — `WorkspaceRefHealth`,
  `WorkspaceHealthResponse` response models (plain BaseModel, NOT strict).
- `app/features/demo/routes.py` — query params on `GET /demo/workspaces`;
  NEW `GET /demo/workspaces/{workspace_id}/health`.
- `frontend/src/types/api.ts` — lifecycle fields on the workspace types
  (verify-or-add per CONTRACT(E1)), health types, list-params type,
  `WorkspaceUpdate` type.
- `frontend/src/hooks/use-workspaces.ts` — params-aware `useWorkspaces`,
  `usePatchWorkspace`, `useWorkspaceHealth`, `useWorkspaceLineage`.
- `frontend/src/components/demo/ReplayConfirmDialog.tsx` — NEW confirm +
  preview/diff dialog.
- `frontend/src/components/demo/WorkspaceEditDialog.tsx` — NEW
  rename/notes/tags editor.
- `frontend/src/components/demo/WorkspaceLineageStrip.tsx` — NEW lineage chain.
- `frontend/src/components/demo/WorkspacePanel.tsx` — reworked: toolbar
  (search / show-archived / sort), row badges (pinned, archived, replay),
  per-row actions dropdown, multi-select + delete-selected + compare-selected.
- `frontend/src/components/demo/WorkspaceArtifactsPanel.tsx` — health-aware
  cards (dead-link warnings) + health summary chip.
- `frontend/src/pages/workspace-compare.tsx` — NEW two-workspace compare page;
  route + `ROUTES.SHOWCASE_COMPARE` constant.
- `frontend/src/pages/showcase.tsx` — replay-confirm flow, lineage strip +
  health wiring, `replayed_from_workspace_id` on the replay start frame.
- Tests: backend route + module unit tests, integration tests for list filters
  and health; frontend vitest for every new/changed component + hook.
- `docs/_base/API_CONTRACTS.md` + `docs/_base/RUNBOOKS.md` — additive updates
  (incl. superseding the "deliberately no confirm dialog" note).

**Success definition**: all Success Criteria below check off, the five backend
CI gates and the frontend gates are green, and a manual browser dogfood on a
seeded stack walks: save → search/sort → rename/pin/archive → replay (confirm
dialog with diff, destructive variant on a reset workspace) → lineage chain
visible → two-workspace compare → delete a referenced run → health shows the
dead link.

## Why

- Umbrella #406 success criteria commit: "a `reset=true` replay requires an
  explicit confirmation step before it runs" and "Workspaces can be renamed,
  archived, pinned, annotated (notes/tags), searched, filtered, sorted, and
  multi-select-deleted (metadata-only) from the saved-workspaces panel".
- Today a replay of a `reset=true` workspace wipes the database with **no
  confirmation** — documented designed behavior
  (`docs/_base/RUNBOOKS.md` § "Showcase workspace", item 1: "there is
  deliberately no confirm dialog") that #406 explicitly reverses.
- E1 (#407) ships the storage + PATCH surface but no UI consumes it; E2 is the
  delivery surface that makes lifecycle, lineage, and provenance visible.
- `created_objects` ids are soft references by design — operator deletes leave
  dangling deep links ("expected; the workspace row records what WAS created,
  not what still exists", RUNBOOKS § Showcase workspace item 4). Link health
  turns that silent staleness into a visible, per-workspace signal — the novel
  ops slice #406 folded into this epic.

## What

### Decisions locked here (so implementation doesn't re-litigate)

These were the open questions this PRP owns; the decisions below are final for E2.

1. **Replay-policy picker (exact / safe-keep / modified): OUT OF SCOPE.**
   Replay stays verbatim (`E4 #393` semantics). Rationale: the umbrella
   commits only confirm + preview/diff; a "modified replay" already exists as
   Load → edit controls → Run (the Load path repopulates every control); a
   policy enum would add request-surface + backend validation for zero new
   capability. The confirm dialog's footer carries a one-line hint —
   "Want to change the config first? Use Load instead." Document the
   deferral in the PR description.
2. **Confirmation applies to EVERY replay, not just `reset=true`.** The
   preview/diff panel needs a pre-flight surface and a sometimes-there dialog
   is worse UX than an always-there one. The `reset=true` variant escalates:
   destructive copy + destructive-styled action button. This satisfies the
   umbrella's "explicit confirmation before any reset=true replay" as a
   strict superset. The direct Run button (operator-configured runs) is
   unchanged — confirmation guards replays only.
3. **Link-health architecture: BACKEND aggregation endpoint**
   (`GET /demo/workspaces/{id}/health`), implemented by probing the public
   API **in-process** via `httpx.ASGITransport` — the exact mechanism
   `pipeline._Client` already uses from inside a request context
   (`app/features/demo/pipeline.py:141-148`; `POST /demo/run` passes
   `request.app` into the pipeline at `routes.py:75`). Justification:
   (a) the demo slice may NOT import registry/scenarios/jobs/agents services
   (vertical-slice rule), and in-process HTTP through the public surface is
   the slice's established cross-slice seam; (b) one workspace has up to ~10+
   references (3 runs + N plans + alias + batch + session + M jobs) — a
   frontend-probed design costs 1+N browser round-trips per workspace and
   duplicates existence semantics per artifact type; (c) a backend endpoint
   gives the health summary a single testable contract and a place for the
   partial-run flag. Probes run concurrently (`asyncio.gather`), classify
   2xx→`alive`, 404→`dead`, anything else→`unknown`, and are fetched
   on-demand (loaded workspace only — never for every list row).
4. **Compare view: FRONTEND-ONLY page.** A workspace compare is a plain field
   diff over two already-served `WorkspaceDetail` payloads — no new backend
   endpoint (contrast: `GET /registry/compare/{a}/{b}` exists because metric
   diffing has server-side logic). New page `/showcase/compare?a=&b=`
   mirroring `frontend/src/pages/explorer/run-compare.tsx` (two `Select`
   pickers + `useSearchParams` deep-linking).
5. **Multi-select delete = N sequential single DELETEs.** The existing
   `DELETE /demo/workspaces/{id}` is called once per selected row behind one
   confirmation dialog. NO new bulk endpoint — product-vision guardrail ("no
   wipe-everything operations"); failures are collected and toasted, the list
   refetches once at the end.
6. **Search/filter/sort: SERVER-SIDE additive query params** on
   `GET /demo/workspaces`, mirroring established precedents: name search →
   `dimensions` `search` ILIKE pattern (`app/features/dimensions/routes.py:65`),
   tags → `scenarios` repeated-`tags` JSONB containment
   (`app/features/scenarios/routes.py:180`, `service.py:462-465`), sort →
   allow-listed `sort_by`/`sort_order` with silent fallback to default
   (`dimensions/routes.py:70-75`). `include_archived=false` is the default
   (archived rows hidden). Pinned rows always order first
   (`ORDER BY pinned DESC, <sort>`). Server-side keeps the panel honest as
   rows accumulate and gives the filter a route-test contract.

### Frozen contract — CONTRACT(E1) (#407 ships these; E2 consumes, never re-decides)

Every assumption below MUST be reconciled against the merged E1 diff before
implementation (Task 1). Where E1's PRP chose different names, adapt E2's code
to E1's names — never the reverse.

- `CONTRACT(E1)-1` — `showcase_workspace` columns exist post-migration:
  `replayed_from_workspace_id` (nullable String(32), soft reference — NO FK,
  consistent with `models.py` no-FK doctrine), `archived` (bool, default
  false), `pinned` (bool, default false), `notes` (nullable text), `tags`
  (JSONB string array, default `[]`), `config_schema_version` (int).
- `CONTRACT(E1)-2` — `tags` representation is a JSONB string array with a GIN
  index, mirroring `scenario_plan.tags`
  (`app/features/scenarios/models.py:74,97`), so SQLAlchemy
  `.contains([tag])` containment filtering works.
- `CONTRACT(E1)-3` — `PATCH /demo/workspaces/{workspace_id}` exists with an
  all-Optional partial-update body (rename/notes/tags/archive/pin — assumed
  schema name `WorkspaceUpdateRequest`, semantics mirroring registry
  `RunUpdate`, `app/features/registry/schemas.py:113-121`: absent field =
  unchanged), returns the updated workspace (assumed
  `WorkspaceDetailResponse`), 404 problem+json on a missing id.
- `CONTRACT(E1)-4` — the GET list/detail response schemas expose the new
  columns (`WorkspaceListItem` += `archived`, `pinned`, `tags`,
  `replayed_from_workspace_id`; `WorkspaceDetailResponse` += `notes`,
  `config_schema_version` and the JSONB story slots it serves). **Defensive
  rule**: if E1 did NOT extend the GET responses, E2 adds the fields
  additively in Task 3 (they are required reading surface for this epic).
- `CONTRACT(E1)-5` — replay provenance mechanism: `DemoRunRequest` (and the
  WS start frame) carries an additive Optional
  `replayed_from_workspace_id: str | None` that `workspace.create_workspace`
  persists onto the new row (E1's epic body: "Replay writes
  `replayed_from_workspace_id`"). NOTE: E1's PRP itself wires the frontend
  send (handleReplayWorkspace sends `ws.workspace_id` — an E1 success
  criterion), so E2 PRESERVES the field through the executeReplay refactor
  rather than adding it; if E1 instead derived it server-side, E2 adapts.
- `CONTRACT(E1)-6` — the `job_ids` JSONB story slot is a `list[str]` of job
  ids; the health endpoint probes each via `GET /jobs/{job_id}` when the slot
  is non-empty (and silently skips when absent/empty — pre-E1-backfill rows).
- `CONTRACT(E1)-7` — E1 does NOT add filtering/sorting to
  `GET /demo/workspaces` (its scope is migration + PATCH + schemas); the list
  query params are E2's to add. If E1's merged code already added any of
  them, reuse instead of duplicating.

### User-visible behavior

- **Replay confirm/diff**: Replay button → dialog titled "Replay workspace
  \"name\"?" with a two-column table (Recorded / Will send) over seed,
  scenario, reset, skip_seed, workspace name, preservation (always `keep`),
  replayed-from (the source workspace id). Rows where the two values differ
  are highlighted (defensive — verbatim replay means they normally match).
  `reset=true` → red warning block + destructive confirm button labeled
  "Replay & wipe database"; otherwise a default confirm labeled "Replay".
  Cancel never starts a run.
- **Lineage**: list rows with `replayed_from_workspace_id != null` show an
  outline `Badge` "replay". The loaded-workspace view renders a breadcrumb
  strip: `this ← parent ← grandparent …` (depth-capped at 5), each ancestor
  clickable (loads it); a deleted ancestor renders as
  "(original deleted)" — dangling soft references are expected, never errors.
- **Lifecycle panel**: toolbar = search `Input` (filters by name,
  debounced/enter-applied), "Show archived" `Checkbox`, sort `Select`
  (Newest / Oldest / Name / Status). Rows: pin icon (filled when pinned),
  muted styling + "archived" badge on archived rows, tags rendered as small
  chips (clicking a chip filters the list by that tag; an active tag filter
  shows as a clearable chip in the toolbar). Per-row `DropdownMenu` (lucide
  `MoreHorizontal`): Pin/Unpin, Archive/Unarchive, Edit details…, Delete….
  "Edit details…" opens `WorkspaceEditDialog` (name input with the
  `^[a-z0-9][a-z0-9\-_]*$` client validation already used by the run controls,
  notes `Textarea`, tags comma-separated input).
- **Multi-select**: leading `Checkbox` per row + header select-all; selection
  shows "N selected" with **Delete selected** (AlertDialog: "Delete N
  workspace records? Their created objects are NOT deleted.") and **Compare**
  (enabled only when exactly 2 selected → navigates to the compare page).
- **Compare page** (`/showcase/compare?a=&b=`): back-link to `/showcase`, two
  workspace `Select` pickers (deep-linkable URL params), then: config table
  (seed/scenario/reset/skip_seed/name/tags, mismatches highlighted),
  result-summary table (winner, WAPE with the `DeltaCell` sign-only
  indicator, wall-clock), created-objects presence matrix (per soft-reference
  key: recorded A / recorded B), lineage note when one side is a replay of
  the other, partial-run badge per side when `status != "completed"`.
- **Link health**: loading a workspace fires
  `GET /demo/workspaces/{id}/health`; the artifacts panel shows a summary
  chip — `✓ N live · ✕ M dead` (plus "partial run" warning chip when the
  row's status is not `completed`) — and each card whose reference probed
  `dead` gets a lucide `AlertTriangle` + tooltip "This object no longer
  exists — it was deleted after the run." `unknown` references render
  without a marker (no false alarms on transient 5xx).

### Technical requirements

- All five backend gates green; frontend `pnpm lint && pnpm test --run` green.
- New/changed endpoints: route tests covering 2xx + at least one error path
  (`.claude/rules/test-requirements.md`).
- RFC 7807 for every error path (`NotFoundError` from `app/core/exceptions.py:72`).
- Response models stay plain `BaseModel` (+`from_attributes` where ORM-built)
  — strict mode is request-body-only policy (`demo/schemas.py:88-95` precedent).
- The demo slice imports NO other feature slice — link health goes through
  in-process HTTP (`request.app` + `ASGITransport`), never a service import.
- Frontend: TanStack Query for all IO; shadcn/ui new-york primitives only
  (everything needed is already installed — see gotchas); lucide icons;
  semantic tokens only (`text-destructive`, `bg-muted`, …) — no raw colors.
- Legacy behavior byte-identical: a client that never touches the new query
  params / endpoints sees today's responses (new list params all default to
  today's semantics EXCEPT archived-hidden — see gotcha on `include_archived`).

### Success Criteria

- [ ] Replay (panel button) always opens the confirm dialog with the
      recorded-vs-sent preview; confirming a `reset=true` workspace requires
      the destructive-styled button; Cancel starts nothing. No code path
      starts a replay without the dialog.
- [ ] A confirmed replay sends the recorded config verbatim +
      `preservation="keep"` + the recorded name + `replayed_from_workspace_id`
      (CONTRACT(E1)-5); the new row carries the provenance id and the list
      shows its "replay" badge; the loaded view renders the ancestor chain,
      tolerating deleted ancestors.
- [ ] Rename / notes / tags / pin / archive each round-trip through
      `PATCH /demo/workspaces/{id}` and re-render without a manual refresh
      (query invalidation on list + detail).
- [ ] `GET /demo/workspaces` supports `q` (name ILIKE), `tags` (repeated,
      containment), `include_archived` (default false), allow-listed
      `sort_by`/`sort_order` (unknown → default `created_at desc`); pinned
      rows order first; `total` respects the active filters; route tests
      cover each param + the bad-param paths.
- [ ] Multi-select delete removes N metadata rows via N single DELETEs behind
      one confirmation; created objects untouched; NO new bulk endpoint exists.
- [ ] `/showcase/compare?a=&b=` deep-links two workspaces and renders config
      diff, result diff, created-objects matrix, lineage note, partial-run
      badges; invalid/missing ids degrade to the picker (no crash).
- [ ] `GET /demo/workspaces/{id}/health` returns per-reference
      `alive`/`dead`/`unknown` + counts + `partial_run`; 404 problem+json on a
      missing workspace; integration test proves a bogus reference probes
      `dead` and a real one probes `alive`.
- [ ] Loaded-workspace artifact cards show dead-link warnings + the health
      summary chip; the partial-run warning renders for non-completed rows.
- [ ] Legacy list calls (no new params) return archived-free, pinned-first,
      newest-first pages; all pre-existing demo tests still pass.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy app/
      && uv run pyright app/ && uv run pytest -v -m "not integration"` green;
      integration suite green; `cd frontend && pnpm lint && pnpm test --run`
      green.

## Assumptions (no user available — documented, not asked)

1. E1 (#407) merges before E2 execution begins (implementation-order gate from
   the umbrella). This PRP is authored against pre-E1 `dev`; Task 1
   reconciles every CONTRACT(E1) point against E1's actual merged shape.
2. Exact E1 schema/endpoint names (`WorkspaceUpdateRequest`, field names as
   listed in CONTRACT(E1)) — adapt to E1's real names on divergence.
3. Archived-by-default-hidden is the correct list semantics (that is what
   "archive" means for a library); the only consumer of `GET /demo/workspaces`
   is the Showcase panel (verified — no other frontend or backend caller), so
   the default-flip is safe.
4. Health probing is acceptable on-demand-only (loaded workspace), not for
   every list row — probing N rows × M references on list render would be a
   self-inflicted thundering herd through the in-process transport.
5. The lineage chain depth cap of 5 is sufficient (a replay-of-a-replay chain
   deeper than 5 is a pathological case; the strip renders "…" beyond it).
6. `sonner` `toast` (already used by `WorkspacePanel.tsx:20`) is the
   feedback surface for mutation success/failure — no new notification system.
7. Tag editing via a comma-separated text input is acceptable UX for a
   single-operator tool (no tag-autocomplete component is installed; building
   one is out of scope).

## All Needed Context

### Documentation & References

```yaml
# MUST READ — issues (the contract stack)
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/408
  why: The epic this PRP implements — scope list is exhaustive (this PRP covers all of it).
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/406
  why: Umbrella — success criteria rows 2 & 3 are E2's acceptance bar; out-of-scope list (no replay-policy infra beyond confirm+diff).
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/407
  why: Foundation epic body = the frozen CONTRACT(E1) surface (columns, JSONB slots, PATCH endpoint, replay provenance write).
- file: PRPs/PRP-showcase-workspace-E4-restore-replay.md
  why: Closest-analog predecessor PRP — the E4 restore/replay semantics E2 hardens; its "decisions locked" #2/#3 (no confirm dialog, no provenance) are the two designed behaviors #406/#407 now reverse.

# MUST READ — backend (verified 2026-06-12, dev pre-E1)
- file: app/features/demo/routes.py
  why: |
    Current surface: POST /run @51 (passes request.app into the pipeline @75 —
    the request-context app handle the health route also needs), GET
    /workspaces @80-107 (limit/offset only — EXTEND with filters), GET
    /workspaces/{workspace_id} @110-135 (NotFoundError 404 pattern @133-134),
    DELETE @138-163, WS /stream @166. Router prefix="/demo" @48. Health route
    lands between the GET detail and DELETE.
- file: app/features/demo/workspace.py
  why: |
    list_workspaces @174-196 (order created_at.desc, id.desc @192) and
    count_workspaces @224-234 — the two functions E2 extends with q/tags/
    include_archived/sort_by/sort_order. get_workspace @158, delete_workspace
    @199. All take caller-owned AsyncSession. create_workspace @46 is E1's to
    extend (replayed_from) — DO NOT touch unless E1 missed it.
- file: app/features/demo/models.py
  why: |
    ShowcaseWorkspace @37; current columns @59-81; CHECK + composite index
    @83-89. E1 adds the lifecycle/provenance columns here — E2 reads them,
    never migrates. No-FK doctrine in the module docstring @4-11 (the health
    feature exists BECAUSE of this doctrine).
- file: app/features/demo/schemas.py
  why: |
    DemoRunRequest @29 (strict=True @40; preservation @68; workspace_name
    pattern @72-78; requires-keep validator @80-85 — the model E1 extends with
    replayed_from_workspace_id). Response-model non-strict precedent: StepEvent
    docstring @88-95, WorkspaceListItem @169 (from_attributes @177),
    WorkspaceDetailResponse @192, WorkspaceListResponse @205. Append the two
    health models here.
- file: app/features/demo/pipeline.py
  why: |
    THE in-process probe mechanism to copy into link_health.py: _Client
    @127-204 — httpx.AsyncClient(transport=httpx.ASGITransport(app=app,
    raise_app_exceptions=False), base_url cosmetic, timeout @98) and
    request() status handling @188-200. link_health needs a SIMPLER client:
    status-code classification only, no _StepError. DO NOT modify pipeline.py
    in E2 (E1 owns the provenance write; replay flows through unchanged).
- file: app/features/demo/tests/test_routes.py
  why: |
    Route-test conventions to extend: unit tests monkeypatch the workspace
    module functions (list @236-251, pagination pass-through @253-276, 404
    @286-298, delete @324-347); integration tests @359+ use the db_session
    fixture and seed real rows. New filter/health tests follow these shapes.
- file: app/features/demo/tests/conftest.py
  why: client fixture (ASGITransport over app.main.app) + db_session fixture
    (real Postgres, wipes showcase_workspace on teardown).
- file: app/features/scenarios/routes.py
  why: |
    Repeated-tags Query param precedent @168-195 (tags: list[str] | None =
    Query(default=None)) — copy for the workspace list. GET detail 404 style
    @198-223.
- file: app/features/scenarios/service.py
  why: list_plans @436-472 — tags containment filter @462-465
    (stmt.where(ScenarioPlan.tags.contains(tags))) applied to BOTH count and
    rows statements; total respects filters. Mirror exactly.
- file: app/features/scenarios/models.py
  why: tags JSONB string-array column @70-74 + GIN index @97 — the
    representation CONTRACT(E1)-2 assumes for workspace tags.
- file: app/features/dimensions/routes.py
  why: |
    search + allow-listed sort precedent @65-105 (search Query min-2-chars,
    sort_by Query with allow-list note "unknown values use default order",
    sort_order asc|desc). Mirror the docstring + silent-fallback style.
- file: app/features/registry/schemas.py
  why: RunUpdate @113-121 — the all-Optional partial-update body shape
    CONTRACT(E1)-3 assumes for WorkspaceUpdateRequest (extra="forbid").
- file: app/features/registry/routes.py
  why: |
    PATCH precedent @235; probe targets for link health: GET /registry/runs/
    {run_id} @200-201, GET /registry/aliases/{alias_name} @503-504.
- file: app/features/jobs/routes.py
  why: probe target GET /jobs/{job_id} @219-220.
- file: app/features/batch/routes.py
  why: probe target GET /batch/{batch_id} @55-62 (NotFoundError on miss).
- file: app/features/agents/routes.py
  why: probe target GET /agents/sessions/{session_id} @80-104 — 404 via plain
    HTTPException (status code is all the probe reads; body shape irrelevant).
- file: app/core/exceptions.py
  why: NotFoundError @72 (RFC 7807 404). No new exception classes needed.

# MUST READ — frontend (verified 2026-06-12)
- file: frontend/src/pages/showcase.tsx
  why: |
    453 lines. State block @118-131 (seed/keepWorkspace/workspaceName/
    selectedWorkspaceId + useWorkspace detail resolution @128-131); handleRun
    @139-156; handleLoadWorkspace @160-168; handleReplayWorkspace @174-186 —
    THE function the confirm dialog intercepts (today it calls start()
    directly); WorkspacePanel mount @245-255; name-pattern client validation
    @26 + @135-137 (reuse in WorkspaceEditDialog); WorkspaceArtifactsPanel
    mount @448-450 (gets health props).
- file: frontend/src/components/demo/WorkspacePanel.tsx
  why: |
    219 lines — the component this epic reworks. Props @37-48; statusClass
    @50-59 (semantic-token status colors); DESTRUCTIVE marker @144-148
    (text-destructive span); per-row buttons @153-183; the AlertDialog
    delete-confirm pattern @191-216 (open-state via pendingDelete, shared
    one dialog for all rows, data-testid on the action) — COPY this pattern
    for ReplayConfirmDialog + the multi-delete confirm; list invalidation
    effect @106-110.
- file: frontend/src/components/demo/WorkspacePanel.test.tsx
  why: vitest conventions for this component family (mock use-workspaces
    hooks via vi.mock, fire dialog actions, assert mutation calls).
- file: frontend/src/components/demo/WorkspaceArtifactsPanel.tsx
  why: |
    157 lines. ArtifactCard shape @15-20, buildCards key mapping @30-107
    (winning_run_id/v2_run_id/scenario_plan_ids/batch_id/alias/
    agent_session_id + grain), disabled-card opacity-50 + title tooltip
    @128-149. Health markers extend buildCards: each card gains an optional
    `dead: boolean` resolved from the health response keyed by reference id.
- file: frontend/src/hooks/use-workspaces.ts
  why: |
    43 lines — extend in place. useWorkspaces @10-16 (queryKey ['workspaces',
    {limit}] — params object grows), useWorkspace @19-25, useDeleteWorkspace
    @33-42 (invalidate ['workspaces'] on success — same invalidation for
    usePatchWorkspace). useWorkspaceHealth + useWorkspaceLineage are new
    siblings here.
- file: frontend/src/pages/explorer/run-compare.tsx
  why: |
    THE compare-page pattern (370 lines): useSearchParams a/b @87-89,
    selectRun setParams updater @103-109, RunPicker Select @56-84, DeltaCell
    sign-only indicator @33-54, side-by-side Card/Table layout @114+. The
    workspace compare page mirrors all of it with useWorkspace×2 instead of
    useCompareRuns (frontend-only diff — Decision 4).
- file: frontend/src/lib/constants.ts
  why: ROUTES.SHOWCASE='/showcase' @4, ROUTES.EXPLORER.RUN_COMPARE @20 — add
    SHOWCASE_COMPARE='/showcase/compare' beside SHOWCASE.
- file: frontend/src/App.tsx
  why: lazy-page + Suspense route registration pattern (ShowcasePage @12,
    @54-61; RunComparePage @21, @119-126) — register WorkspaceComparePage
    identically.
- file: frontend/src/lib/api.ts
  why: api<T>(endpoint, {params, method, body}) wrapper; ApiError carries
    status (WorkspacePanel.tsx:97 shows instanceof usage); getErrorMessage.
- file: frontend/src/types/api.ts
  why: workspace types block @806-831 (WorkspaceListItem @806, WorkspaceDetail
    @819, WorkspaceListResponse @828); DemoRunRequest @778-787 — extend here.
- file: frontend/src/hooks/use-demo-pipeline.ts
  why: start(req) signature + the picker-desync gotcha (start() does not sync
    the scenario picker — Replay must setScenario first; already handled in
    handleReplayWorkspace, keep that ordering inside the confirmed path).

# Project docs to update (additive)
- file: docs/_base/API_CONTRACTS.md
  why: GET /demo/workspaces row gains the filter params; new health-endpoint
    row; WS section note for replayed_from (if E1 didn't already add it).
- file: docs/_base/RUNBOOKS.md
  why: § "Showcase workspace — preserve/restore/replay/delete semantics" item 1
    says "there is deliberately no confirm dialog" — E2 supersedes this
    (update the item; keep the DESTRUCTIVE-marker sentence). Items 2-4 gain
    one-line pointers to lineage badges / metadata-only multi-delete / health.
- file: docs/_base/DOMAIN_MODEL.md
  why: showcase_workspace § "Out of scope" lists the replayed_from column —
    E1's PRP owns that doc edit; E2 only verifies it happened (do not double-edit).
```

### Current Codebase tree (relevant subset, pre-E1)

```bash
app/features/demo/
├── link_health.py     # DOES NOT EXIST — E2 creates
├── models.py          # ShowcaseWorkspace @37 (E1 extends; E2 reads)
├── pipeline.py        # 2771 lines; _Client @127 — UNTOUCHED in E2
├── routes.py          # POST /run @51; GETs @80,@110; DELETE @138; WS @166
├── schemas.py         # 214 lines; workspace response models @169-213
├── service.py         # lock + PipelineBusyError — untouched
├── workspace.py       # 235 lines; list @174 / count @224 — E2 extends
└── tests/             # conftest, test_{models,pipeline,routes,schemas,workspace}.py
frontend/src/
├── pages/showcase.tsx                       # 453 lines
├── pages/explorer/run-compare.tsx           # 370 lines — compare pattern
├── components/demo/WorkspacePanel.tsx       # 219 lines — reworked in E2
├── components/demo/WorkspaceArtifactsPanel.tsx  # 157 lines — health-aware in E2
├── hooks/use-workspaces.ts                  # 43 lines — extended in E2
├── types/api.ts                             # workspace block @806-831
└── components/ui/                           # 27 primitives incl. alert-dialog,
                                             # dialog, dropdown-menu, textarea,
                                             # table, select, tooltip, badge
```

### Desired Codebase tree (files added/modified)

```bash
app/features/demo/
├── link_health.py                           # NEW — probe targets + probe_workspace_links()
├── schemas.py                               # MOD — +WorkspaceRefHealth +WorkspaceHealthResponse
├── workspace.py                             # MOD — list/count filters + sort
├── routes.py                                # MOD — list query params; +GET /workspaces/{id}/health
└── tests/
    ├── test_link_health.py                  # NEW — probe classification vs a stub ASGI app
    ├── test_routes.py                       # MOD — filter/sort/health unit + integration tests
    └── test_workspace.py                    # MOD — list/count filter unit coverage (db-less where possible)
frontend/src/
├── types/api.ts                             # MOD — lifecycle fields (verify-or-add), health types, params, update type
├── hooks/use-workspaces.ts                  # MOD — params-aware list; +usePatchWorkspace +useWorkspaceHealth +useWorkspaceLineage
├── hooks/use-workspaces.test.ts             # MOD — new hooks covered
├── components/demo/ReplayConfirmDialog.tsx       # NEW (+ .test.tsx)
├── components/demo/WorkspaceEditDialog.tsx       # NEW (+ .test.tsx)
├── components/demo/WorkspaceLineageStrip.tsx     # NEW (+ .test.tsx)
├── components/demo/WorkspacePanel.tsx       # MOD — toolbar/badges/dropdown/multi-select (+ test MOD)
├── components/demo/WorkspaceArtifactsPanel.tsx   # MOD — health markers + summary chip (+ test MOD)
├── components/demo/index.ts                 # MOD — barrel exports
├── pages/workspace-compare.tsx              # NEW (+ workspace-compare.test.tsx)
├── pages/showcase.tsx                       # MOD — confirm flow, lineage, health, provenance field
├── lib/constants.ts                         # MOD — ROUTES.SHOWCASE_COMPARE
└── App.tsx                                  # MOD — compare route registration
docs/_base/API_CONTRACTS.md                  # MOD — list params + health endpoint
docs/_base/RUNBOOKS.md                       # MOD — supersede "no confirm dialog"; lifecycle notes
```

### Known Gotchas & Library Quirks

```python
# CRITICAL — EXECUTION GATE: do not start until E1 (#407) is merged to dev.
#   Task 1 reconciles every CONTRACT(E1) point against the real merged code
#   (git log --oneline --grep "#407"; read the E1 PRP + diff). Adapt E2 to
#   E1's names; flag (don't silently fix) any E1 contract gap in the PR body.

# CRITICAL — NO migration, NO models.py edit, NO pipeline.py edit in E2.
#   The schema delta and the provenance/PATCH plumbing are E1's. If a column
#   you need is missing post-E1, STOP and surface it — don't ship a stealth
#   migration under E2.

# CRITICAL — no cross-slice imports from app/features/demo/. Link health MUST
#   go through in-process HTTP (request.app + httpx.ASGITransport — precedent
#   pipeline.py:141-148 driven from a request context via routes.py:75).
#   Importing RegistryService/ScenarioService/etc. fails the architecture rule.

# CRITICAL — health probe classification: 2xx -> "alive", 404 -> "dead",
#   EVERYTHING else (5xx, timeout, transport error) -> "unknown". Never let a
#   probe exception escape the endpoint (asyncio.gather(..., return_exceptions=
#   True) or per-probe try/except) — a flaky slice must not 500 the health
#   route. raise_app_exceptions=False is REQUIRED on the ASGITransport (an
#   unhandled error in a probed endpoint must surface as a 500 *response*).

# CRITICAL — multi-select delete is N SINGLE DELETEs (existing endpoint).
#   Adding POST /demo/workspaces/bulk-delete or DELETE /demo/workspaces is a
#   product-vision violation (no bulk-wipe operations) — do not create it.

# CRITICAL — the `total` returned by the filtered list MUST respect the active
#   filters (scenarios precedent: BOTH count_stmt and rows_stmt get the same
#   .where chain, scenarios/service.py:462-465). A filter-blind total breaks
#   the "showing X of Y" header.

# GOTCHA — include_archived default false flips list semantics for archived
#   rows. Pre-E1 rows have archived=false (E1 migration default), so legacy
#   lists are unchanged; route tests must still pin: no-param call returns
#   only archived=false rows, include_archived=true returns both.

# GOTCHA — sort allow-list: {created_at, name, seed, status}; unknown sort_by
#   silently falls back to created_at desc (dimensions precedent — NOT a 422).
#   Pinned-first is unconditional: ORDER BY pinned DESC, <sort>, id DESC
#   tiebreak. name sort: NULLS LAST (unnamed rows sink) — use
#   sqlalchemy .nulls_last() on the asc/desc expression.

# GOTCHA — tags Query param: list[str] | None = Query(default=None) gives
#   repeated-param parsing (?tags=a&tags=b). JSONB containment via
#   ShowcaseWorkspace.tags.contains(tags) requires CONTRACT(E1)-2 (JSONB array
#   column). Frontend sends ONE tag at a time (chip filter) — a single
#   `tags` param serializes fine through api()'s params.

# GOTCHA — q search: mirror dimensions ILIKE (case-insensitive, escape % and _
#   if the precedent does; check dimensions/service.py before writing).
#   Search NAME only (workspace_id prefixes are copy-paste handles, not search).

# GOTCHA — strict-mode policy: the new health/response models are response
#   models -> plain BaseModel, NO ConfigDict(strict=True). The AST walker
#   (app/core/tests/test_strict_mode_policy.py) only inspects strict=True
#   request models — keep it that way.

# GOTCHA — agents GET /agents/sessions/{id} 404s via plain HTTPException (not
#   NotFoundError) — irrelevant to the probe (status code only), but do NOT
#   "fix" the agents slice as a drive-by.

# GOTCHA — an EXPIRED-but-existing agent session returns 200 (row exists) ->
#   "alive". That is correct link-health semantics (the row is the link
#   target); the artifacts card blurb already says "the recorded session has
#   likely expired".

# GOTCHA — ReplayConfirmDialog destructive styling: AlertDialogAction renders
#   buttonVariants default; pass className="bg-destructive text-destructive-
#   foreground hover:bg-destructive/90" (semantic tokens — NEVER raw colors
#   like bg-red-500). Copy the shared-dialog open-state pattern from
#   WorkspacePanel.tsx:191-216 (pendingX state, one dialog for all rows).

# GOTCHA — confirm-dialog flow ordering: the confirmed replay must run the
#   EXISTING handleReplayWorkspace body (setScenario BEFORE start() — the
#   picker-desync gotcha from E4 still applies). Refactor: handleReplayWorkspace
#   becomes "setPendingReplay(ws)"; a new executeReplay(ws) holds the old body
#   + the CONTRACT(E1)-5 replayed_from_workspace_id field.

# GOTCHA — lineage walking: a deleted ancestor's GET returns 404 (ApiError
#   .status === 404) — render "(original deleted)" and STOP the walk; never
#   throw. Implement as one useQuery whose queryFn loops (await api(...) per
#   ancestor, depth cap 5), queryKey ['workspaces', id, 'lineage'] — N
#   serial fetches inside one query keeps cache + loading states simple.

# GOTCHA — useWorkspaces signature change (limit -> params object) touches its
#   existing call sites + use-workspaces.test.ts — update them in the same
#   commit; keep queryKey shape ['workspaces', paramsObject] so the blanket
#   invalidateQueries({queryKey: ['workspaces']}) keeps matching everything.

# GOTCHA — pnpm tsc --noEmit is VACUOUS (solution-style tsconfig, zero files)
#   and `tsc -b` fails on dev with PRE-EXISTING errors (known issue — memory
#   [[frontend-tsc-noemit-gate-vacuous]]). Do NOT chase those. JS gates that
#   must be green: pnpm lint && pnpm test --run. Optionally verify ONLY your
#   new files compile via their vitest imports.

# GOTCHA — every shadcn primitive needed (alert-dialog, dialog, dropdown-menu,
#   checkbox, input, textarea, select, table, tooltip, badge, card, button) is
#   ALREADY in frontend/src/components/ui/ (verified 2026-06-12). Do NOT run
#   `shadcn add`. If you believe a new primitive is required, stop and recheck
#   (.claude/rules/shadcn-ui.md; memory [[shadcn-cli-version-pin]]).

# GOTCHA — never call crypto.randomUUID directly (issue #332; ESLint guard) —
#   safeRandomUUID from @/lib/uuid-utils if any client id is needed.

# GOTCHA — repo has mixed CRLF/LF; Write/Edit emit LF. New files fine; for
#   showcase.tsx / WorkspacePanel.tsx / routes.py edits run `git diff --stat`
#   and confirm surgical line counts before committing.

# GOTCHA — mypy --strict AND pyright --strict gate merge: full annotations on
#   the new probe module (TypedDict/dataclass or Pydantic for probe targets),
#   `-> None` on tests, annotated fixtures.

# COORDINATION — E3 (#409), E4 (#410), E5 (#411), E6 (#412) are open parallel
#   epics. Shared-file risk: schemas.py / routes.py / showcase.tsx /
#   API_CONTRACTS.md. Keep every edit additive + self-contained; rebase on dev
#   before the PR.

# RUNTIME-VERIFICATION LOG (per prp-create step 3):
#   - demo routes/handlers + line refs — read routes.py (2026-06-12)
#   - list/count signatures + ordering — read workspace.py:174-234
#   - ShowcaseWorkspace pre-E1 columns — read models.py:59-89
#   - response-model non-strict precedent — read schemas.py:88-95,169-213
#   - ASGITransport in-process pattern — read pipeline.py:127-204
#   - scenario tags containment + GIN — read scenarios/service.py:462-465, models.py:74,97
#   - dimensions search/sort params — grep dimensions/routes.py:65-105
#   - probe targets exist: /registry/runs/{run_id} (registry/routes.py:200),
#     /registry/aliases/{alias_name} (:503), /jobs/{job_id} (jobs/routes.py:219),
#     /batch/{batch_id} (batch/routes.py:55), /agents/sessions/{session_id}
#     (agents/routes.py:80), /scenarios/{scenario_id} (scenarios/routes.py:198)
#   - RunUpdate partial-update shape — read registry/schemas.py:113-121
#   - frontend: WorkspacePanel AlertDialog pattern (191-216), run-compare
#     useSearchParams pattern (87-109), installed ui primitives (ls), api.ts
#     ApiError usage (WorkspacePanel.tsx:97)
#   - E1 #407 OPEN / unmerged as of 2026-06-12 — CONTRACT(E1) tags mark every
#     dependency; no third-party API claims beyond in-repo working patterns
#     (httpx ASGITransport, sqlalchemy .contains, TanStack useQuery/useMutation
#     — all already exercised in this repo; .nulls_last is standard
#     SQLAlchemy 2.0 API but has NO in-repo precedent — verify at impl time).
```

## Implementation Blueprint

### Data models and structure

```python
# app/features/demo/schemas.py — APPEND (response models; NOT strict)

RefHealthStatus = Literal["alive", "dead", "unknown"]
RefType = Literal["model_run", "scenario_plan", "alias", "batch", "agent_session", "job"]


class WorkspaceRefHealth(BaseModel):
    """Liveness of one soft reference recorded on a workspace (E2, #408)."""

    key: str = Field(..., description="created_objects key, e.g. 'winning_run_id' or 'scenario_plan_ids[0]'.")
    ref_type: RefType = Field(..., description="Kind of referenced object.")
    ref_id: str = Field(..., description="The recorded soft-reference id.")
    status: RefHealthStatus = Field(..., description="alive (2xx) / dead (404) / unknown (other).")
    probe_path: str = Field(..., description="The public API path probed.")


class WorkspaceHealthResponse(BaseModel):
    """Per-workspace link-health summary (E2, #408)."""

    workspace_id: str
    workspace_status: str = Field(..., description="running / completed / failed.")
    partial_run: bool = Field(..., description="True when workspace_status != 'completed'.")
    references: list[WorkspaceRefHealth] = Field(default_factory=list)
    alive: int = Field(..., ge=0)
    dead: int = Field(..., ge=0)
    unknown: int = Field(..., ge=0)
    checked_at: datetime = Field(default_factory=_utc_now)
```

```python
# app/features/demo/link_health.py — NEW (sketch; CRITICAL details only)

@dataclass(frozen=True)
class _ProbeTarget:
    key: str          # e.g. "scenario_plan_ids[1]"
    ref_type: str     # RefType value
    ref_id: str
    probe_path: str   # e.g. f"/registry/runs/{ref_id}"

def build_probe_targets(ws: ShowcaseWorkspace) -> list[_ProbeTarget]:
    # created_objects keys (workspace.py:_collect_created_objects:82-103):
    #   winning_run_id / v2_run_id / stale_alias_run_id -> /registry/runs/{id}
    #   scenario_plan_ids[i]                            -> /scenarios/{id}
    #   alias                                           -> /registry/aliases/{name}
    #   batch_id                                        -> /batch/{id}
    #   agent_session_id                                -> /agents/sessions/{id}
    # CONTRACT(E1)-6: job_ids JSONB slot [i]            -> /jobs/{id}
    # NON-probeable keys (v2_model_path, scenario_artifact_key,
    # train_model_types) are SKIPPED — no HTTP identity to check.
    ...

async def probe_workspace_links(app: FastAPI, ws: ShowcaseWorkspace) -> WorkspaceHealthResponse:
    targets = build_probe_targets(ws)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://demo.internal",
        timeout=httpx.Timeout(10.0, connect=5.0),
    ) as client:
        results = await asyncio.gather(
            *(_probe_one(client, t) for t in targets), return_exceptions=False
        )  # _probe_one NEVER raises: try/except httpx.HTTPError/OSError -> "unknown"
    # classify: 200<=s<300 alive; s==404 dead; else unknown
    # partial_run = ws.status != WORKSPACE_STATUS_COMPLETED
    ...
```

```typescript
// frontend/src/types/api.ts — extend the workspace block (806-831)

// CONTRACT(E1)-4 — verify E1 added these; add additively if not:
export interface WorkspaceListItem {
  /* existing fields ... */
  archived: boolean
  pinned: boolean
  tags: string[]
  replayed_from_workspace_id: string | null
}
export interface WorkspaceDetail extends WorkspaceListItem {
  /* existing fields ... */
  notes: string | null
  config_schema_version: number
}

// E2 (#408) — lifecycle PATCH body (CONTRACT(E1)-3 shape; adapt to E1 names):
export interface WorkspaceUpdate {
  name?: string | null
  notes?: string | null
  tags?: string[]
  archived?: boolean
  pinned?: boolean
}

export interface WorkspaceListParams {
  limit?: number
  offset?: number
  q?: string
  tags?: string
  include_archived?: boolean
  sort_by?: 'created_at' | 'name' | 'seed' | 'status'
  sort_order?: 'asc' | 'desc'
}

export type RefHealthStatus = 'alive' | 'dead' | 'unknown'
export interface WorkspaceRefHealth {
  key: string
  ref_type: 'model_run' | 'scenario_plan' | 'alias' | 'batch' | 'agent_session' | 'job'
  ref_id: string
  status: RefHealthStatus
  probe_path: string
}
export interface WorkspaceHealth {
  workspace_id: string
  workspace_status: 'running' | 'completed' | 'failed'
  partial_run: boolean
  references: WorkspaceRefHealth[]
  alive: number
  dead: number
  unknown: number
  checked_at: string
}
```

### List of tasks (dependency order)

```yaml
Task 1 — gate, branch & E1 reconciliation:
  VERIFY: gh issue view 407 --json state  -> MUST be closed (E1 merged) before continuing
  RUN: git switch dev && git pull && git switch -c feat/showcase-completion-e2-safe-replay-lifecycle
  VERIFY: gh issue view 408 --json state   # open
  RECONCILE every CONTRACT(E1) tag against the merged code:
    - read app/features/demo/models.py    -> column names (CONTRACT(E1)-1/-2)
    - read app/features/demo/schemas.py   -> PATCH body + GET response fields (CONTRACT(E1)-3/-4)
    - read app/features/demo/routes.py    -> PATCH route exists
    - grep replayed_from app/features/demo/ -> provenance mechanism (CONTRACT(E1)-5)
    - read PRPs/PRP-showcase-completion-E1-*.md (whatever E1's PRP file is named)
  ADAPT all names below to E1's reality; note any E1 gap in the PR body.

Task 2 — MODIFY app/features/demo/workspace.py (filters + sort):
  - EXTEND list_workspaces(db, *, limit=50, offset=0, q=None, tags=None,
      include_archived=False, sort_by=None, sort_order="desc"):
      # base stmt; if not include_archived: .where(~ShowcaseWorkspace.archived)
      # if q: .where(ShowcaseWorkspace.name.ilike(f"%{q}%"))   (name only)
      # if tags: .where(ShowcaseWorkspace.tags.contains(tags)) (CONTRACT(E1)-2)
      # sort: allow-list {created_at,name,seed,status}; unknown -> created_at
      #   desc; name uses .nulls_last(); ALWAYS ORDER BY pinned.desc() first,
      #   then the sort expr, then id.desc() tiebreak
  - EXTEND count_workspaces(db, *, q=None, tags=None, include_archived=False)
      # SAME where-chain as list (scenarios/service.py:462-465 precedent) —
      # extract a shared _apply_filters(stmt, ...) helper to keep them in sync
  - Update module docstring (E2 routes the filters).

Task 3 — MODIFY app/features/demo/schemas.py:
  - APPEND WorkspaceRefHealth + WorkspaceHealthResponse (blueprint above);
    docstring notes: response models, NOT strict (StepEvent precedent @88-95).
  - CONTRACT(E1)-4 defensive check: if E1 did not expose archived/pinned/tags/
    replayed_from_workspace_id on WorkspaceListItem (+notes/
    config_schema_version on WorkspaceDetailResponse), ADD them here
    additively (from_attributes picks them up from the ORM row).

Task 4 — CREATE app/features/demo/link_health.py:
  - build_probe_targets(ws) + probe_workspace_links(app, ws) per the blueprint.
  - MIRROR pipeline._Client transport flags exactly (raise_app_exceptions=False).
  - _probe_one catches (httpx.HTTPError, OSError) -> "unknown"; NEVER raises.
  - Full --strict annotations; module docstring states the no-cross-slice-
    import rationale (Decision 3) and the 2xx/404/other classification table.

Task 5 — MODIFY app/features/demo/routes.py:
  - EXTEND GET /workspaces signature with q / tags / include_archived /
    sort_by / sort_order Query params (mirror dimensions/routes.py:65-75 +
    scenarios/routes.py:180 styles; document the allow-list + silent fallback
    in the docstring); pass through to workspace.list_workspaces /
    count_workspaces (same filter args to BOTH).
  - ADD GET /workspaces/{workspace_id}/health -> WorkspaceHealthResponse:
      # async def get_workspace_health(workspace_id: str, request: Request,
      #                                db: AsyncSession = Depends(get_db)):
      #   row = await workspace.get_workspace(db, workspace_id)
      #   if row is None: raise NotFoundError(message=f"Workspace not found: {workspace_id}")
      #   return await link_health.probe_workspace_links(request.app, row)
      # Place between the GET detail (@110) and DELETE (@138). No path
      # collision: /workspaces/{id}/health is more specific than /workspaces/{id}.
  - Update the module docstring route inventory.

Task 6 — backend tests:
  - CREATE app/features/demo/tests/test_link_health.py (unit, no DB):
      # build a THROWAWAY FastAPI stub app with routes returning 200 / 404 /
      # 500 at the probed paths; construct a ShowcaseWorkspace instance
      # in-memory (not persisted) with created_objects covering every key +
      # job_ids slot; assert classification alive/dead/unknown + counts +
      # partial_run on status='failed'; assert non-probeable keys skipped;
      # assert empty created_objects -> empty references, partial_run logic.
  - MODIFY app/features/demo/tests/test_routes.py:
      UNIT (monkeypatch app.features.demo.routes.workspace / .link_health):
        - list passes q/tags/include_archived/sort args through (capture kwargs)
        - list rejects bad limit (existing) — keep green
        - health 404 on missing workspace (problem+json content-type)
        - health 200 happy path (monkeypatched probe returns canned response)
      INTEGRATION (@pytest.mark.integration, db_session):
        - seed rows: named/unnamed, archived, pinned, tagged ->
          default list hides archived; include_archived=true shows it;
          q matches name substring case-insensitively; tags containment;
          sort_by=name asc with NULLS LAST; pinned row first regardless of sort;
          total respects filters
        - health integration: insert a workspace whose created_objects carry
          one REAL reference (insert a scenario_plan row via its ORM, or use a
          bogus-vs-real registry pair) + one bogus id -> assert alive + dead
  - MODIFY app/features/demo/tests/test_workspace.py: filter unit coverage of
    _apply_filters where practical (or fold into the integration tests above).

Task 7 — MODIFY frontend/src/types/api.ts:
  - Lifecycle fields per CONTRACT(E1)-4 (verify-or-add), WorkspaceUpdate,
    WorkspaceListParams, WorkspaceRefHealth/WorkspaceHealth (blueprint above).
  - DemoRunRequest: verify E1 added replayed_from_workspace_id?: string
    (CONTRACT(E1)-5); add if missing.

Task 8 — MODIFY frontend/src/hooks/use-workspaces.ts (+ test):
  - useWorkspaces(params: WorkspaceListParams = {}, enabled = true):
      queryKey ['workspaces', params]; api('/demo/workspaces', { params })
      # update existing call site: WorkspacePanel.tsx:77 (the sole useWorkspaces
      # caller — showcase.tsx never calls it directly)
  - ADD usePatchWorkspace():
      mutationFn: ({workspaceId, update}: {workspaceId: string; update: WorkspaceUpdate}) =>
        api<WorkspaceDetail>(`/demo/workspaces/${workspaceId}`, { method: 'PATCH', body: update })
      onSuccess: invalidate ['workspaces']   # blanket key matches list+detail
  - ADD useWorkspaceHealth(workspaceId: string, enabled = true):
      queryKey ['workspaces', workspaceId, 'health']; staleTime 30_000
  - ADD useWorkspaceLineage(workspaceId: string | null):
      one useQuery; queryFn walks replayed_from_workspace_id via sequential
      api<WorkspaceDetail>() calls, depth cap 5; a 404 (ApiError.status===404)
      terminates the walk with a {deleted: true} sentinel entry; returns
      Array<{workspace_id, name, deleted}> oldest-last.
  - MODIFY use-workspaces.test.ts: params serialization, PATCH invalidation,
    lineage walk incl. 404 termination (mock api module).

Task 9 — CREATE frontend/src/components/demo/ReplayConfirmDialog.tsx (+ test):
  - Props: { workspace: WorkspaceListItem | null,        # null = closed
             requestPreview: DemoRunRequest | null,      # built by the page
             onConfirm: () => void, onCancel: () => void }
  - AlertDialog (open={workspace !== null}; onOpenChange close -> onCancel) —
    copy the shared-dialog pattern from WorkspacePanel.tsx:191-216.
  - Body: 3-column table (Field / Recorded / Will send) over seed, scenario,
    reset, skip_seed, name, preservation, replayed_from; per-row mismatch
    highlight (font-semibold text-destructive on the "Will send" cell when
    values differ — defensive; verbatim replay normally matches).
  - reset=true -> warning block (AlertTriangle + "Replaying this workspace
    WIPES the database and reseeds it.") + AlertDialogAction
    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
    label "Replay & wipe database"; else label "Replay".
  - Footer hint: "Want to change the config first? Use Load instead." (muted).
  - data-testid="replay-confirm" on the action (WorkspacePanel test precedent).
  - Test: renders preview values; destructive copy/label only when reset;
    confirm fires onConfirm once; cancel fires onCancel; mismatch highlight.

Task 10 — CREATE frontend/src/components/demo/WorkspaceEditDialog.tsx (+ test):
  - Props: { workspace: WorkspaceListItem | null, onClose: () => void }
  - Dialog (ui/dialog.tsx — form dialog, not AlertDialog) with: name Input
    (reuse WORKSPACE_NAME_PATTERN from showcase.tsx:26 — export it from a
    shared location, e.g. components/demo/workspace-name.ts, instead of
    duplicating), notes Textarea, tags Input (comma-separated -> trimmed
    string[]; render current tags as chips above the input).
  - Save -> usePatchWorkspace().mutate({workspaceId, update}); toast on
    success/failure (sonner pattern WorkspacePanel.tsx:88-99); close on success.
  - Send ONLY changed fields (partial update — CONTRACT(E1)-3 semantics).
  - Test: pattern violation disables Save with inline hint; save sends only
    dirty fields; success closes + toasts (mock usePatchWorkspace).

Task 11 — CREATE frontend/src/components/demo/WorkspaceLineageStrip.tsx (+ test):
  - Props: { workspaceId: string, onLoadAncestor: (id: string) => void }
  - useWorkspaceLineage(workspaceId); render breadcrumb: current ← parent ←
    … oldest; ancestors as Button variant="link" size="sm" (click ->
    onLoadAncestor); deleted sentinel renders muted "(original deleted)";
    depth-cap overflow renders trailing "…". Render nothing (null) when the
    workspace has no replayed_from_workspace_id.
  - Test: chain render order, deleted sentinel, null when no lineage.

Task 12 — MODIFY frontend/src/components/demo/WorkspacePanel.tsx (+ test):
  - Toolbar row above the list: search Input (icon lucide Search; applies as
    `q` on Enter/debounce), "Show archived" Checkbox, sort Select
    (Newest/Oldest/Name/Status -> sort_by+sort_order pairs), active-tag chip
    (clearable) when a tag filter is set.
  - Panel owns the list-params state and calls useWorkspaces(params).
  - Row additions: leading multi-select Checkbox; Pin icon button (lucide Pin
    / PinOff, fires usePatchWorkspace toggle); archived rows: opacity-60 +
    outline Badge "archived"; replay Badge (outline, "replay") when
    replayed_from_workspace_id != null; tags as clickable chips (sets the tag
    filter); DropdownMenu (MoreHorizontal): Pin/Unpin, Archive/Unarchive,
    Edit details…, Delete… (Delete keeps the existing pendingDelete dialog).
  - Replay button now calls a NEW prop onRequestReplay(ws) (the page owns the
    confirm dialog) — RENAME the old onReplay prop to make the break explicit.
  - Selection footer: "N selected" + Delete selected (AlertDialog confirm ->
    sequential `for (const id of selected) await deleteWorkspace.mutateAsync(id)`
    with per-failure collection -> one summary toast; clear selection) +
    Compare button (disabled unless exactly 2; useNavigate ->
    `${ROUTES.SHOWCASE_COMPARE}?a=${id1}&b=${id2}`).
  - Keep the component lean: extract WorkspaceToolbar + WorkspaceRow as
    file-local components if the file passes ~300 lines.
  - Tests: search/sort/archived params flow into useWorkspaces (mock + assert
    last call args); multi-select count + delete-selected confirm calls N
    mutateAsync; compare disabled at 1 and 3 selections; pin/archive fire
    PATCH mutations; replay fires onRequestReplay (NOT start).

Task 13 — MODIFY frontend/src/components/demo/WorkspaceArtifactsPanel.tsx (+ test):
  - Props += { health?: WorkspaceHealth | null }
  - buildCards gains the refId per card; a card whose refId matches a
    health.references entry with status==='dead' renders AlertTriangle
    (h-3 w-3 text-destructive) beside the label + title tooltip "This object
    no longer exists — it was deleted after the run." ('unknown' -> no marker).
  - Header chip row: `✓ {alive} live` (text-success) + `✕ {dead} dead`
    (text-destructive, only when dead>0) + outline Badge "partial run" when
    health.partial_run (tooltip: "This run never completed — artifacts may be
    missing."). Skeleton/silent when health undefined (query in flight/disabled).
  - Test: dead marker on matching card; summary chip counts; partial-run badge.

Task 14 — MODIFY frontend/src/pages/showcase.tsx:
  - State += pendingReplay: WorkspaceListItem | null.
  - handleReplayWorkspace(ws) -> setPendingReplay(ws)  (no start()).
  - NEW executeReplay(ws): the post-E1 body (showcase.tsx:174-186 today —
    setScenario first; E1 shifts these anchors and adds
    replayed_from_workspace_id: ws.workspace_id, which executeReplay PRESERVES
    — CONTRACT(E1)-5, preserve-not-add); clear pendingReplay.
  - buildReplayRequest(ws): pure helper producing the DemoRunRequest preview
    passed to the dialog AND used by executeReplay (single source — the diff
    can never lie about what's sent). Export for unit testing.
  - Mount <ReplayConfirmDialog workspace={pendingReplay}
      requestPreview={pendingReplay && buildReplayRequest(pendingReplay)}
      onConfirm={() => pendingReplay && executeReplay(pendingReplay)}
      onCancel={() => setPendingReplay(null)} />
  - Health: const health = useWorkspaceHealth(selectedWorkspaceId ?? '',
      !!selectedWorkspaceId); pass health.data into WorkspaceArtifactsPanel.
  - Lineage: mount <WorkspaceLineageStrip workspaceId={selectedWorkspaceId}
      onLoadAncestor={(id) => { /* fetch list item via detail + handleLoad */ }} />
      inside the loaded-workspace block (@448-450 region); simplest
    onLoadAncestor: setSelectedWorkspaceId(id) + repopulate controls from the
    lineage entry's detail (the strip's hook already has the details — pass
    the full WorkspaceDetail up instead of just the id if cleaner).
  - WorkspacePanel prop rename: onRequestReplay={handleReplayWorkspace}.

Task 15 — CREATE frontend/src/pages/workspace-compare.tsx (+ test) + routing:
  - MODIFY frontend/src/lib/constants.ts: SHOWCASE_COMPARE: '/showcase/compare'
    (beside SHOWCASE @4).
  - MODIFY frontend/src/App.tsx: lazy WorkspaceComparePage + <Route> (mirror
    RunComparePage @21, @119-126). '/showcase/compare' and '/showcase' are
    distinct paths — no nesting needed.
  - Page mirrors run-compare.tsx: useSearchParams a/b (@87-109 pattern);
    pickers = Select over useWorkspaces({limit: 100, include_archived: true})
    items (label: name ?? id.slice(0,8) · scenario · status); two
    useWorkspace(a/b) detail queries; render:
      * config table — seed/scenario/reset/skip_seed/name/tags; mismatch rows
        highlighted (font-semibold)
      * results table — winner_model_type, winner_wape (DeltaCell-style
        sign-only delta — copy the component from run-compare.tsx:33-54
        file-locally), wall_clock_s
      * created-objects matrix — union of soft-reference keys × (A: ✓/—,
        B: ✓/—)
      * lineage note — "B is a replay of A" (or inverse) when
        replayed_from_workspace_id links them
      * partial-run outline Badge per side when status !== 'completed'
    Missing/invalid id -> that side renders the picker + muted "select a
    workspace" (no crash; ApiError 404 -> same fallback).
  - Test: renders diff for two mocked details; mismatch highlight; lineage
    note; 404 side falls back to picker state.

Task 16 — barrel + docs:
  - MODIFY frontend/src/components/demo/index.ts — export the three new
    components.
  - MODIFY docs/_base/API_CONTRACTS.md:
      * GET /demo/workspaces row: append "E2 (#408) — `q` name search, `tags`
        containment filter, `include_archived` (default false), allow-listed
        `sort_by`/`sort_order`; pinned rows first; `total` respects filters"
      * NEW row: | demo | GET | `/demo/workspaces/{workspace_id}/health` |
        E2 (#408) — probe the workspace's soft references in-process; per-ref
        alive/dead/unknown + counts + `partial_run`; `404` when missing |
  - MODIFY docs/_base/RUNBOOKS.md § "Showcase workspace — …":
      * item 1: replace "there is deliberately no confirm dialog" with the E2
        reality (every panel Replay confirms; reset=true gets destructive
        copy; the DESTRUCTIVE row marker stays)
      * item 3/4: one-line additions — multi-select delete = N metadata-only
        singles; dead links now SURFACE via the health summary instead of
        silently dangling
  - VERIFY (not edit) DOMAIN_MODEL.md replayed_from note was updated by E1.

Task 17 — gates, dogfood, commits, PR:
  - Backend gates + integration suite (Validation Loop below).
  - Frontend: cd frontend && pnpm lint && pnpm test --run.
  - Browser dogfood via the webapp-testing skill (CLAUDE.md workflow step 4):
    seeded stack -> save 3 workspaces (one reset=true, one tagged, one
    replayed) -> search/sort/archive/pin -> replay with confirm (destructive
    variant) -> lineage chain -> compare page -> delete a referenced scenario
    plan -> reload workspace -> dead-link warning + health chip.
  - git diff --stat (CRLF surgical-diff check on edited files).
  - COMMITS (reference #408, no AI trailer), e.g.:
      feat(api): add workspace list filters and link-health endpoint (#408)
      feat(ui): add replay confirmation with config diff to showcase (#408)
      feat(ui): add workspace lifecycle controls and lineage rendering (#408)
      feat(ui): add two-workspace compare page (#408)
      test(api): cover workspace filters and link-health probes (#408)
      docs(api): document workspace lifecycle and health contracts (#408)
  - PR into dev; title `feat(api,ui): showcase-completion E2 — safe replay &
    workspace lifecycle (#408)`; body notes the replay-policy-picker deferral
    (Decision 1) + any CONTRACT(E1) reconciliation deltas.
```

### Integration Points

```yaml
DATABASE: none in E2 — reads the E1-migrated table; NO new migration.

CONFIG: none — no new settings or env vars (probe timeout is a module constant).

ROUTES: existing demo router only (app/main.py wiring unchanged): extended GET
  /demo/workspaces + new GET /demo/workspaces/{id}/health. PATCH is E1's.

FRONTEND ROUTES: one new React Router page at ROUTES.SHOWCASE_COMPARE
  ('/showcase/compare'); registered in App.tsx beside the existing pages.

DOCS: API_CONTRACTS.md + RUNBOOKS.md (Task 16). Full doc sweep belongs to the
  E7 release gate — keep E2's edits additive and minimal.
```

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
cd frontend && pnpm lint
# Expected: clean. Both Python type checkers are --strict and gate merge.
# (pnpm tsc --noEmit is vacuous; tsc -b fails with PRE-EXISTING errors — do
# not chase them. lint + vitest are the JS gates.)
```

### Level 2: Unit Tests (no DB)

```bash
uv run pytest app/features/demo -v -m "not integration"
uv run pytest app/core/tests/test_strict_mode_policy.py -v   # AST walker still green
cd frontend && pnpm test --run
# New/changed: test_link_health (stub-app probe classification), test_routes
# filter/health unit tests, use-workspaces hooks, ReplayConfirmDialog,
# WorkspaceEditDialog, WorkspaceLineageStrip, WorkspacePanel rework,
# WorkspaceArtifactsPanel health markers, workspace-compare page.
```

### Level 3: Integration (real Postgres)

```bash
docker compose up -d && uv run alembic upgrade head
uv run pytest app/features/demo -v -m integration
# List filters against seeded rows (archived hidden / shown, q, tags,
# sort + pinned-first, filtered total) + health probe (real + bogus refs).
```

### Level 4: Manual smoke + browser dogfood (seeded local stack, uvicorn :8123)

```bash
# 1. Filtered list + health round-trip
curl -s "http://localhost:8123/demo/workspaces?q=demo&sort_by=name&sort_order=asc" | python3 -m json.tool | head -30
curl -s "http://localhost:8123/demo/workspaces?include_archived=true" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['total'])"
WS_ID=$(curl -s -X POST http://localhost:8123/demo/run -H 'Content-Type: application/json' \
  -d '{"skip_seed": true, "preservation": "keep", "workspace_name": "e2-smoke"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['workspace_id'])")
curl -s "http://localhost:8123/demo/workspaces/${WS_ID}/health" | python3 -m json.tool
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" \
  http://localhost:8123/demo/workspaces/deadbeefdeadbeefdeadbeefdeadbeef/health   # 404 problem+json

# 2. Dead-link proof: delete a referenced scenario plan, re-probe
#    (pick a scenario_plan_id from the workspace detail's created_objects)
curl -s -X DELETE http://localhost:8123/scenarios/<plan-id> -o /dev/null -w "%{http_code}\n"
curl -s "http://localhost:8123/demo/workspaces/${WS_ID}/health" \
  | python3 -c "import sys,json; print([r for r in json.load(sys.stdin)['references'] if r['status']=='dead'])"

# 3. Browser dogfood (webapp-testing skill / agent-browser):
#    /showcase -> save workspaces -> toolbar search/sort/show-archived ->
#    pin (row jumps first) -> archive (vanishes until toggle) -> Edit details
#    (rename + tags chips) -> Replay -> confirm dialog shows the diff table ->
#    a reset=true workspace shows destructive copy + red button -> confirmed
#    replay goes green, new row carries the "replay" badge -> Load it ->
#    lineage strip shows the chain -> select 2 rows -> Compare page diff ->
#    multi-select 2 -> Delete selected -> rows gone, created objects intact ->
#    loaded workspace with the deleted plan shows the dead-link warning + chip.
```

## Final validation Checklist

- [ ] All five gates green: `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"`
- [ ] Integration suite green: `uv run pytest -v -m integration` (fresh docker-compose DB)
- [ ] Frontend gates green: `cd frontend && pnpm lint && pnpm test --run`
- [ ] No replay path bypasses the confirm dialog; reset=true shows destructive variant (vitest + dogfood)
- [ ] List filters: archived hidden by default, q/tags/sort behave, pinned-first, filtered total (route tests + curl)
- [ ] Health endpoint classifies alive/dead/unknown; dead-link warning + partial-run chip render (integration + dogfood step 2/3)
- [ ] Lineage chain renders incl. deleted-ancestor sentinel
- [ ] Compare page deep-links `?a=&b=` and degrades gracefully on bad ids
- [ ] Multi-select delete = N single DELETEs; **no new bulk endpoint in the diff**
- [ ] Legacy list calls + all pre-existing demo tests unchanged-green
- [ ] CONTRACT(E1) reconciliation notes in the PR body; replay-policy deferral noted
- [ ] `git diff --stat` surgical (no CRLF whole-file noise)
- [ ] docs/_base/API_CONTRACTS.md + RUNBOOKS.md updated additively
- [ ] Commits `type(scope): description (#408)`, no AI trailer; PR into dev; browser dogfood evidence per `.claude/rules/ui-design.md`

---

## Anti-Patterns to Avoid

- ❌ Don't start before E1 (#407) merges; don't re-implement E1 surface (migration, PATCH, provenance write).
- ❌ Don't import another feature slice from `app/features/demo/` — link health is in-process HTTP only.
- ❌ Don't add a bulk-delete endpoint or any "wipe everything" operation — N singles, period.
- ❌ Don't add a replay-policy picker (exact/safe-keep/modified) — explicitly deferred (Decision 1).
- ❌ Don't make health/response models strict — strict mode is request-body policy.
- ❌ Don't probe health for every list row — loaded workspace only.
- ❌ Don't let a probe exception 500 the health route — classify as `unknown`.
- ❌ Don't mutate the original workspace row on replay — replay still creates a NEW row (provenance points back).
- ❌ Don't duplicate the name pattern regex — share it between run controls and the edit dialog.
- ❌ Don't run `shadcn add` — every needed primitive is installed; don't use raw colors — semantic tokens only.
- ❌ Don't call `crypto.randomUUID` directly — `safeRandomUUID` (ESLint-enforced).
- ❌ Don't chase pre-existing `tsc -b` errors — lint + vitest are the JS gates.

## Confidence Score

**7.5/10** for one-pass implementation success. The backend half (list filters
+ health endpoint) is a composition of three verified in-repo precedents
(dimensions search/sort, scenarios tags containment, pipeline ASGITransport)
with clear test shapes. The deductions: (a) E2 is authored against a frozen
but UNMERGED E1 contract — seven CONTRACT(E1) points must reconcile against
E1's real merged shape, and any naming/shape divergence costs an adaptation
pass (mitigated by Task 1's reconciliation gate and verify-or-add fallbacks);
(b) the WorkspacePanel rework is the single largest UI delta of the showcase
initiative so far (toolbar + badges + dropdown + multi-select + confirm
rerouting in one component) where an interaction miss costs an iteration; and
(c) four parallel epics share `schemas.py` / `routes.py` / `showcase.tsx`,
so rebase friction is plausible even with additive-only edits.
