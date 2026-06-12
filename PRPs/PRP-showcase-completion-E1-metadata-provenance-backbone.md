name: "PRP — Showcase Completion E1: Workspace Metadata & Provenance Backbone (issue #407)"
description: |

## Purpose

Implement the Foundation epic of the showcase-completion initiative (umbrella #406):
one Alembic migration extends `showcase_workspace` with lifecycle + provenance columns
(`replayed_from_workspace_id`, `archived`, `pinned`, `notes`, `tags`,
`config_schema_version`) and six documented JSONB story-slot columns
(`seed_overrides`, `user_scope`, `approval_events`, `rag_events`, `job_ids`,
`phase_summaries`); a `PATCH /demo/workspaces/{id}` lifecycle endpoint
(rename/notes/tags/archive/pin) lands with its Pydantic schema surface; and Replay
writes `replayed_from_workspace_id`. Every Parallel epic (#408–#412) writes into or
reads from this surface, so it ships first. Blocks E2 #408, E3 #409, E4 #410,
E5 #411, E6 #412.

## Core Principles

1. **Context is King**: every reference below was verified against the live code on 2026-06-12 (branch `dev` @ `bdf85f6`).
2. **Validation Loops**: each level is executable as written.
3. **Information Dense**: patterns cite exact file:line.
4. **Progressive Success**: model+migration → schemas → service helpers → PATCH route → replay wiring → tests → docs.
5. **Global rules**: follow CLAUDE.md / AGENTS.md; all five CI gates must pass; all changes ADDITIVE.

---

## Goal

The `showcase_workspace` table gains the metadata + provenance backbone every other
epic of umbrella #406 consumes:

- **Lifecycle columns**: `archived` (bool), `pinned` (bool), `notes` (free text),
  `tags` (queryable JSONB string array, GIN-indexed — exact `scenario_plan.tags`
  pattern), `config_schema_version` (int, schema-evolution marker).
- **Provenance column**: `replayed_from_workspace_id` — a SOFT reference (String(32),
  indexed, deliberately **no ForeignKey**, not even self-referential) recorded when a
  run is a Replay of a saved workspace.
- **Six documented JSONB story slots** as dedicated nullable JSONB columns:
  `seed_overrides`, `user_scope`, `approval_events`, `rag_events`, `job_ids`,
  `phase_summaries`. E1 ships the columns + the documented per-slot schema; E1 writes
  NONE of them (all stay NULL) — E3 (#409) writes `seed_overrides` + `user_scope`,
  E5 (#411) writes `approval_events` + `rag_events`, later parallel epics write
  `job_ids` + `phase_summaries`.
- **`PATCH /demo/workspaces/{workspace_id}`** — partial-update lifecycle endpoint:
  rename / notes / tags / archive / pin. Missing id → RFC 7807 404. Returns the
  updated `WorkspaceDetailResponse`.
- **Replay provenance**: `DemoRunRequest` gains an additive Optional
  `replayed_from_workspace_id` field; the frontend Replay handler sends the source
  row's `workspace_id`; `create_workspace` records it on the NEW row.

A run/request without any new field behaves **byte-identically to today** (legacy WS
start frames and HTTP bodies unchanged). One migration applies AND downgrades cleanly
on a fresh DB.

**Deliverable** (all additive):

- `app/features/demo/models.py` — 12 new columns on `ShowcaseWorkspace` + tags GIN index + replayed-from index.
- `alembic/versions/<new>_add_showcase_workspace_metadata_provenance.py` — `down_revision = "324a2fa37fcc"`; add-columns + indexes; clean downgrade.
- `app/features/demo/schemas.py` — `DemoRunRequest.replayed_from_workspace_id`; new `WorkspaceUpdateRequest`; `WorkspaceListItem` / `WorkspaceDetailResponse` additive response fields.
- `app/features/demo/workspace.py` — `create_workspace` records `replayed_from_workspace_id`; new `update_workspace` helper.
- `app/features/demo/routes.py` — `PATCH /demo/workspaces/{workspace_id}`.
- `frontend/src/types/api.ts` + `frontend/src/pages/showcase.tsx` — two-line additive Replay wiring (see "Why the (ui) sliver" below).
- Tests: schema unit tests, model constraint/roundtrip integration tests, workspace-helper integration tests, PATCH route tests (2xx + 404 + 422), migration up/down.
- Docs: `docs/_base/API_CONTRACTS.md` + `docs/_base/DOMAIN_MODEL.md` additive notes (the documented story-slot schema lives in DOMAIN_MODEL — umbrella #406 risk mitigation).

**Success definition**: all Success Criteria below check off; the five CI gates are
green; integration suite green; a manual Replay from the `/showcase` Saved-workspaces
panel produces a new row whose `replayed_from_workspace_id` equals the source row's
`workspace_id`; `PATCH /demo/workspaces/{id}` round-trips rename/notes/tags/archive/pin.

## Why

- Umbrella #406: today workspaces cannot be renamed/archived/annotated/searched, the
  row lacks replay lineage, seed overrides, user scope, approval history, and RAG
  events. E1 is the Foundation — **every** Parallel epic writes into or reads from
  the columns added here, so the frozen column/slot contract ships first.
- Replays are currently indistinguishable from fresh keep-runs except by
  name/timestamp (documented gap, `docs/_base/RUNBOOKS.md` § Showcase workspace,
  "Explicitly out of scope" — the `replayed_from` provenance column is this epic).
- The umbrella's junk-drawer risk ("JSONB story slots become a junk drawer") is
  mitigated here by `config_schema_version` + a documented per-slot schema in
  `docs/_base/DOMAIN_MODEL.md`.

### Why the (ui) sliver in an (api,db) epic

"Replay writes `replayed_from_workspace_id`" is a frozen epic-level success
criterion, and Replay is frontend-initiated: `handleReplayWorkspace`
(`frontend/src/pages/showcase.tsx:174-186`) re-submits the recorded config through
the WS start frame. Without the sender including the field, the backend has nothing
to record. The wiring is two additive lines (one TS interface field + one start-frame
key) — deliberately included here so the criterion is verifiable in E1; the lineage
*rendering* (badge + chain) stays in E2 (#408).

## What

### User-visible behavior

- `PATCH /demo/workspaces/{workspace_id}` accepts a partial body of
  `{name?, notes?, tags?, archived?, pinned?}`; only provided fields change; explicit
  `null` clears `name` / `notes`. Missing id → `404 application/problem+json`. A
  malformed body (bad name pattern, unknown key, >20 tags) → `422
  application/problem+json`. Empty body `{}` → `200` no-op returning the current row
  (mirrors the `RunUpdate` precedent — see Decisions).
- `POST /demo/run` and the `WS /demo/stream` start frame accept an additive Optional
  `replayed_from_workspace_id: str | null` (`^[0-9a-f]{32}$`); supplying it without
  `preservation="keep"` is a 422 (a lineage pointer is meaningless when no row is
  written — same validator pattern as `workspace_name`).
- Clicking **Replay** on the Saved-workspaces panel now records the source
  `workspace_id` on the new row. The original row is never mutated (E4 #393
  invariant preserved).
- `GET /demo/workspaces` list items additively carry `archived`, `pinned`, `tags`,
  `replayed_from_workspace_id`; the detail response additively carries those plus
  `notes`, `config_schema_version`, and the six story slots. **List behavior is
  otherwise unchanged in E1** — archived rows are still listed; default-filtering /
  search / sort is E2 (#408).

### Technical requirements

- One Alembic migration off head `324a2fa37fcc` (verified `uv run alembic heads`,
  2026-06-12). Forward-only: a NEW revision — never edit
  `324a2fa37fcc_create_showcase_workspace_table.py`.
- Every new column is nullable OR carries a `server_default` so the migration applies
  on a table with existing rows; downgrade drops indexes then columns, cleanly.
- **No ForeignKeys anywhere** — `replayed_from_workspace_id` is an opaque soft
  reference, consistent with the table-wide invariant
  (`docs/_base/DOMAIN_MODEL.md` § `showcase_workspace`: "`created_objects` carries
  SOFT references only — no ForeignKeys by design"). Even a *self-referential* FK is
  ruled out: ancestor workspace rows must remain independently deletable
  (metadata-only delete, #404) without cascading to or blocking descendants. State
  this in the model docstring.
- `status` is NOT patchable — the pipeline finalize hook owns the
  running/completed/failed lifecycle; `archived` is an orthogonal boolean so the
  existing `ck_showcase_workspace_status` CHECK is untouched.
- Vertical slice: all backend changes inside `app/features/demo/` +
  `alembic/versions/`; no cross-slice imports (demo imports only `app.core.*`,
  `app.shared.*`, stdlib/3rd-party).
- RFC 7807 errors only — `NotFoundError` from `app/core/exceptions.py` (the demo
  routes' existing pattern, `routes.py:134`), never bare `HTTPException`.
- Pydantic v2 `ConfigDict(strict=True)` on the new request body. All new fields are
  JSON-native (`str`/`bool`/`list[str]`) → NO `Field(strict=False)` override needed;
  the AST policy walker (`app/core/tests/test_strict_mode_policy.py`) only fires on
  date/datetime/time/UUID/Decimal.
- Warn-and-continue invariant untouched: `create_workspace` /`finalize_workspace`
  keep swallowing all DB errors. The new `update_workspace` helper is
  request-scoped (caller-owned session, raises normally) — it backs an HTTP
  endpoint, not the pipeline.

### Success Criteria

- [ ] Migration applies AND downgrades cleanly on a fresh DB (`upgrade head` →
  `downgrade -1` → `upgrade head`); applies on a DB with pre-existing
  `showcase_workspace` rows (server defaults backfill `archived=false`,
  `pinned=false`, `tags=[]`, `config_schema_version=1`).
- [ ] `DemoRunRequest()` (no args) serializes identically to today plus
  `replayed_from_workspace_id=None`; a legacy start frame (no new keys) validates;
  `replayed_from_workspace_id` without `preservation="keep"` → 422; a non-32-hex
  value → 422.
- [ ] A keep-run with `replayed_from_workspace_id="<32hex>"` produces a row whose
  `replayed_from_workspace_id` column equals that value; the source row is unread
  and unmodified (the value is recorded verbatim — no existence check, it is a soft
  reference).
- [ ] Frontend Replay sends `replayed_from_workspace_id: ws.workspace_id`;
  `pnpm tsc -b` introduces no NEW errors (see gotcha on the pre-existing-failure
  baseline) and `pnpm test --run` green.
- [ ] `PATCH /demo/workspaces/{id}`: happy path updates exactly the provided fields
  and returns the updated detail; `{}` is a 200 no-op; missing id → 404
  problem+json; bad name pattern / unknown key / 21 tags → 422 problem+json.
- [ ] `tags` round-trips as a JSONB string array and is GIN-indexed
  (`ix_showcase_workspace_tags_gin`); a `.contains(["x"])` containment query works
  (E2 will route it — E1 proves it in an integration test).
- [ ] All six story-slot columns exist, default NULL, and round-trip a JSONB payload
  in an integration test; E1 production code writes none of them.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ &&
  uv run pyright app/ && uv run pytest -v -m "not integration"` all green;
  integration suite green against docker-compose Postgres;
  `test_strict_mode_policy.py` green.

## Decisions (the open questions this PRP resolves)

> These are FROZEN for the parallel epics. #408–#412 PRP authors: consume, don't re-decide.

1. **`tags` representation — CONFIRMED: mirror `scenario_plan.tags` exactly.**
   A dedicated JSONB string-array column, `nullable=False`,
   `server_default=text("'[]'::jsonb")`, with a GIN index
   (`ix_showcase_workspace_tags_gin`). Verified in code:
   `app/features/scenarios/models.py:74-76,97` (column + index), migration
   `alembic/versions/bb8c4587ef1d_add_scenario_library_columns.py:26-45`
   (add_column + GIN), and the containment query
   `app/features/scenarios/service.py:464` (`ScenarioPlan.tags.contains(tags)`).
   No deviation: the pattern is proven, queryable, and E2's tag filter reuses the
   same `.contains()` shape. Tags are free-text strings (scenario precedent has no
   per-item pattern); the PATCH boundary caps the list at 20 items
   (`Field(max_length=20)` — same cap as `ScenarioCreateRequest.tags`,
   `app/features/scenarios/schemas.py:203-206`).

2. **Story slots — six dedicated nullable JSONB columns** (NOT keys inside one
   `story` blob, NOT keys inside `created_objects`). Rationale: the existing
   precedent is purpose-named JSONB columns with documented internal schemas
   (`created_objects`, `result_summary` — `app/features/demo/models.py:77-81`);
   each slot has a different writer epic and a different write moment
   (create-time vs mid-run append vs finalize), and separate columns keep each
   write isolated, independently nullable (NULL = "never written", distinct from
   empty), individually typed in the ORM (`dict[str, Any] | None` vs
   `list[dict] | None`), and trivially additive in responses. A single `story`
   column would force read-modify-write of one blob across four epics and would
   itself need a documented sub-schema anyway — more coupling, zero benefit on a
   low-cardinality audit table. Per-slot documented schema: see the Data-models
   blueprint below + the DOMAIN_MODEL doc task.

3. **`replayed_from_workspace_id` — SOFT reference, no FK, confirmed.** String(32)
   nullable, btree index (`ix_showcase_workspace_replayed_from`), NO ForeignKey —
   including no self-referential FK: `docs/_base/DOMAIN_MODEL.md` pins
   "deletion in either direction never cascades", and an FK (even `ON DELETE SET
   NULL`) would couple delete behavior to lineage. Dangling lineage pointers after
   an ancestor delete are expected and harmless (same semantics as every
   `created_objects` id). Recorded verbatim from the request — no existence
   validation (a replay of a just-deleted workspace still records the id it came
   from; E2's liveness check surfaces dangles).

4. **PATCH semantics — `exclude_unset` partial update, `extra="forbid"`, empty body
   = no-op 200.** `model_dump(exclude_unset=True)` distinguishes absent from
   explicit-null (runtime-verified, see Gotchas); explicit `null` clears `name` /
   `notes`; `extra="forbid"` catches typo'd field names (the `RunUpdate` precedent,
   `app/features/registry/schemas.py:113-123`); an empty body is a valid no-op
   (mirrors `RunUpdate`, which has no min-fields validator). `archived`/`pinned`
   accept only `true`/`false` and `tags` accepts only a list (not null — all
   three back NOT NULL columns; send `[]` to clear tags). Explicit `null` on any
   of the three is rejected at the schema boundary (422), never reaching
   `setattr` → IntegrityError 500.

5. **E1 writes no story slot.** `seed_overrides`/`user_scope` writers land in E3
   (#409), `approval_events`/`rag_events` in E5 (#411), `job_ids`/
   `phase_summaries` in the remaining parallel epics (E2 #408 health summary /
   E4 #410 run-config echo — whichever lands first follows the documented schema).
   E1 ships columns + schema docs + roundtrip tests only.

6. **`config_schema_version` starts at 1.** Integer NOT NULL, `server_default
   text("1")`, ORM `default=1`. It versions the *workspace config + story-slot
   schema* as a whole; any epic that changes a documented slot shape bumps the
   ORM default and documents the delta in DOMAIN_MODEL. E1 does not branch on it.

### Assumptions (explicit, decided without user input)

- `notes` is `sa.Text()` in the DB with a 2000-char cap enforced at the Pydantic
  boundary only (no DB CHECK) — matches the repo's boundary-validation style
  (`RunUpdate.error_message` caps at the schema layer, `registry/schemas.py:123`).
- Renaming via PATCH uses the same `^[a-z0-9][a-z0-9\-_]*$` / ≤100 pattern as
  `DemoRunRequest.workspace_name` (`demo/schemas.py:72-77`) — names stay
  non-unique by design (E4 #393 invariant).
- The PATCH route reuses `WorkspaceDetailResponse` as its response model (the
  updated row, full detail) rather than introducing a new response shape.
- Pin/archive carry NO behavioral semantics in E1 (no list reordering, no
  default-filtering) — E2 (#408) wires the UX. E1 just persists the booleans.
- The umbrella's "destructive-replay confirmation" is E2 (#408) — NOT here.
  E1's replay change is provenance-recording only.
- `replayed_from_workspace_id` requires `preservation="keep"`: a lineage pointer
  on an ephemeral run has no row to land on. (The frontend Replay always sends
  `preservation: 'keep'` — `showcase.tsx:179-185` — so this constraint is
  invisible to the shipped UI.)

## All Needed Context

### Documentation & References

```yaml
# MUST READ — codebase patterns (all verified 2026-06-12, branch dev @ bdf85f6)

- file: app/features/demo/models.py
  why: |
    THE file you extend. ShowcaseWorkspace at line 37; status constants 32-34;
    JSONB precedent created_objects/result_summary at 77-81; __table_args__ with
    named CheckConstraint + composite index at 83-89. Module docstring documents
    the no-FK soft-reference decision — extend that docstring for
    replayed_from_workspace_id. GOTCHA in docstring: SQLAlchemy reserves the
    attr name `metadata`.

- file: alembic/versions/324a2fa37fcc_create_showcase_workspace_table.py
  why: |
    CURRENT HEAD (verified `uv run alembic heads` → 324a2fa37fcc). Your
    down_revision. Header/docstring format, typing (`revision: str`,
    `down_revision: str | None`), op.f() index-naming convention to mirror.
    NEVER edit this file — forward-only.

- file: alembic/versions/bb8c4587ef1d_add_scenario_library_columns.py
  why: |
    THE add-columns migration to mirror: op.add_column with JSONB
    server_default text("'[]'::jsonb") (lines 26-34), GIN index creation
    (39-45), downgrade drops index-then-columns (48-52) incl. the
    postgresql_using='gin' kwarg on drop_index.

- file: app/features/scenarios/models.py
  why: |
    tags JSONB-array pattern (lines 74-76: Mapped[list[str]], nullable=False,
    default=list, server_default=text("'[]'::jsonb")) + GIN index in
    __table_args__ (line 97). This is the tags representation E1 mirrors
    verbatim (Decision 1).

- file: app/features/scenarios/service.py
  why: |
    Line 464: `ScenarioPlan.tags.contains(tags)` — the JSONB containment query
    shape the tags column must support (prove it in an integration test; E2
    routes it).

- file: app/features/demo/schemas.py
  why: |
    DemoRunRequest at 29-85: ConfigDict(strict=True) line 40; the
    workspace_name pattern + model_validator _workspace_name_requires_keep
    (72-85) — copy this exact validator shape for replayed_from_workspace_id.
    WorkspaceListItem (169-189) / WorkspaceDetailResponse (192-203) /
    WorkspaceListResponse (205-213) — the response models you extend
    additively. Response models are plain BaseModel + from_attributes (NOT
    strict) — keep that split.

- file: app/features/demo/workspace.py
  why: |
    create_workspace (46-79): the insert you extend with one kwarg
    (replayed_from_workspace_id=req.replayed_from_workspace_id). get_workspace
    (158-171) — reuse inside update_workspace. delete_workspace (199-221) —
    the caller-owned-session + commit + logger.info shape update_workspace
    mirrors. NOTE the split: create/finalize open their OWN sessions
    (pipeline-scoped, warn-and-continue); get/list/delete take a caller-owned
    AsyncSession (request-scoped, raise normally) — update_workspace is the
    second kind.

- file: app/features/demo/routes.py
  why: |
    The router you extend. delete_showcase_workspace (138-163) — the exact
    route shape for PATCH: Depends(get_db), NotFoundError on missing (RFC 7807
    via registered handler), docstring style. get_showcase_workspace (110-135)
    — WorkspaceDetailResponse return shape.

- file: app/features/registry/schemas.py
  why: |
    RunUpdate (113-123) — THE partial-update request precedent:
    ConfigDict(extra="forbid"), all-Optional fields, no min-fields validator
    (empty body = no-op). E1's WorkspaceUpdateRequest adds strict=True on top
    (post-PRP-14 request-body policy; RunUpdate predates it).

- file: app/features/demo/pipeline.py
  why: |
    DemoContext workspace fields at 258-263; the keep-branch create hook at
    2652-2657; finalize hook at 2741-2746. E1 does NOT touch the pipeline —
    create_workspace reads the new field straight off `req`. Read only to
    confirm no hook change is needed.

- file: app/core/exceptions.py
  why: |
    NotFoundError (line 72) → RFC 7807 404 via registered handler. The 422s
    come FREE from Pydantic validation at the boundary (FastAPI → 422
    problem+json).

- file: app/features/demo/tests/test_schemas.py
  why: |
    Existing DemoRunRequest tests INCLUDING the mandatory JSON-dict path
    (Model.model_validate({...}) per .claude/rules/security-patterns.md
    § strict mode). Extend for the new field + add a WorkspaceUpdateRequest
    block.

- file: app/features/demo/tests/test_workspace.py
  why: |
    Integration-test patterns for create/finalize/get/list/delete — session
    fixture, @pytest.mark.integration, row-cleanup conventions. Extend with
    update_workspace + replayed_from cases.

- file: app/features/demo/tests/test_models.py
  why: |
    Constraint/roundtrip integration tests for ShowcaseWorkspace — extend with
    new-column defaults, tags containment, story-slot roundtrip.

- file: app/features/demo/tests/test_routes.py
  why: |
    Route-test conventions: ASGITransport client from conftest, workspace
    module monkeypatched for unit-shaped route tests, integration-marked tests
    for DB-backed paths. The DELETE 404 test is the template for PATCH 404.

- file: frontend/src/pages/showcase.tsx
  why: |
    handleReplayWorkspace at 174-186 — the start() call that gains ONE key:
    `replayed_from_workspace_id: ws.workspace_id`. handleLoadWorkspace
    (160-168) stays untouched (Load is read-only).

- file: frontend/src/types/api.ts
  why: |
    DemoRunRequest interface at 778-788 — add
    `replayed_from_workspace_id?: string` with an `// E1 (#407)` comment in
    the existing style.

- file: docs/_base/DOMAIN_MODEL.md
  why: |
    § showcase_workspace aggregate — additively document the new columns, the
    six story-slot schemas, the config_schema_version semantics, and restate
    that replayed_from_workspace_id is a soft reference (no FK). This is the
    umbrella's junk-drawer risk mitigation — non-optional.

- file: docs/_base/API_CONTRACTS.md
  why: |
    The /demo rows + "WebSocket Events (/demo/stream)" section — additive
    notes for the PATCH endpoint, the new request field, and the response
    additions, in the established "E1 (#407) — ..." style.

# Issue / initiative context
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/407
  why: The epic this PRP implements (Foundation; frozen column/slot/endpoint contract).
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/406
  why: Umbrella — success criteria, out-of-scope list, risk table (junk-drawer mitigation = config_schema_version + documented slot schema).

# Exemplar PRPs (style + validation-gate conventions)
- file: PRPs/PRP-showcase-workspace-E1-persistence-backbone.md
  why: Closest analog — created the table this PRP extends; task style, gates, anti-patterns.
- file: PRPs/PRP-showcase-workspace-E4-restore-replay.md
  why: Replay flow context — verbatim re-submission through the WS path; original row never mutated.
```

### Current Codebase tree (relevant subset)

```bash
app/features/demo/
├── models.py          # ShowcaseWorkspace @37 (16 columns today)
├── workspace.py       # create @46 / finalize @106 / get @158 / list @174 / delete @199 / count @224
├── schemas.py         # DemoRunRequest @29; WorkspaceListItem @169; WorkspaceDetailResponse @192
├── routes.py          # GET list @80; GET detail @110; DELETE @138; POST /run @51; WS @166
├── pipeline.py        # keep-branch create hook @2652; finalize hook @2741 (NO E1 changes)
├── service.py         # (NO E1 changes)
└── tests/             # conftest, test_models, test_workspace, test_schemas, test_routes, test_pipeline
alembic/
├── env.py             # demo models import already present @19
└── versions/          # head: 324a2fa37fcc
frontend/src/
├── pages/showcase.tsx # handleReplayWorkspace @174
└── types/api.ts       # DemoRunRequest @778
```

### Desired Codebase tree (files added/modified)

```bash
app/features/demo/
├── models.py                # MOD — +12 columns, +2 indexes, extended docstring
├── schemas.py               # MOD — DemoRunRequest +replayed_from_workspace_id (+validator);
│                            #       NEW WorkspaceUpdateRequest; ListItem/Detail additive fields
├── workspace.py             # MOD — create_workspace records replayed_from; NEW update_workspace
├── routes.py                # MOD — PATCH /demo/workspaces/{workspace_id}
└── tests/
    ├── test_schemas.py      # MOD — new-field + WorkspaceUpdateRequest unit tests
    ├── test_models.py       # MOD — column defaults, tags containment, slot roundtrip (integration)
    ├── test_workspace.py    # MOD — replayed_from recording; update_workspace semantics (integration)
    └── test_routes.py       # MOD — PATCH 200/404/422 (+ list/detail field passthrough)
alembic/versions/<rev>_add_showcase_workspace_metadata_provenance.py   # NEW
frontend/src/types/api.ts    # MOD — +replayed_from_workspace_id?: string
frontend/src/pages/showcase.tsx  # MOD — one start-frame key in handleReplayWorkspace
docs/_base/API_CONTRACTS.md  # MOD — additive contract notes
docs/_base/DOMAIN_MODEL.md   # MOD — columns + documented story-slot schemas
```

### Known Gotchas & Library Quirks

```python
# CRITICAL — forward-only migrations: down_revision = "324a2fa37fcc" (verified
#   `uv run alembic heads` → 324a2fa37fcc, 2026-06-12). NEVER edit the merged
#   create-table migration. Revision ids are hand-written 12-hex continuing the
#   chain (or keep an `alembic revision -m ...` generated id).

# CRITICAL — every new NOT NULL column needs a server_default or the migration
#   fails on tables with existing rows: archived/pinned text("false"),
#   config_schema_version text("1"), tags text("'[]'::jsonb"). All six story
#   slots + notes + replayed_from_workspace_id are nullable (no default needed).

# CRITICAL — strict-mode policy: WorkspaceUpdateRequest and the new
#   DemoRunRequest field are all JSON-native (str/bool/list[str]) → NO
#   Field(strict=False) override. The AST walker
#   (app/core/tests/test_strict_mode_policy.py) only fires on
#   date/datetime/time/UUID/Decimal — nothing here triggers it.

# CRITICAL — do NOT add extra="forbid" to DemoRunRequest (unknown-key tolerance
#   is the WS forward/backward-compat contract, routes.py:182). DO add it to
#   WorkspaceUpdateRequest (HTTP-only body; typo'd PATCH fields must 422, not
#   silently no-op — RunUpdate precedent).

# CRITICAL — JSONB change detection: always ASSIGN whole values
#   (row.tags = [...]), never mutate in place (row.tags.append(...)) — in-place
#   mutation is invisible to SQLAlchemy without flag_modified. The existing
#   finalize_workspace assigns; keep that style in update_workspace.

# GOTCHA — SQLAlchemy reserves the declarative attr name `metadata`
#   (demo/models.py docstring). None of the new names collide — keep it that way.

# GOTCHA — `status` stays out of WorkspaceUpdateRequest; the CHECK constraint
#   ck_showcase_workspace_status is untouched. `archived` is orthogonal.

# GOTCHA — update_workspace is caller-owned-session + raises normally (it backs
#   an HTTP route). Do NOT wrap it in the warn-and-continue pattern — that
#   contract is for the PIPELINE-scoped create/finalize only.

# GOTCHA — repo has mixed CRLF/LF line endings; run `git diff --stat` before
#   committing — Edit/Write emit LF, so verify schema/route/model diffs are
#   surgical, not whole-file noise.

# GOTCHA — frontend type gate: `pnpm tsc --noEmit` is vacuous (solution-style
#   tsconfig checks zero files) and `pnpm tsc -b` already fails on dev with
#   pre-existing errors. Gate on "no NEW errors vs the dev baseline" +
#   `pnpm lint` + `pnpm test --run`.

# GOTCHA — mypy --strict AND pyright --strict gate merge: full annotations incl.
#   `-> None` on tests and typed fixtures.

# CONVENTION — branch: feat/showcase-completion-e1-metadata-provenance (off dev).
#   Commits reference #407, e.g. `feat(db): ... (#407)` for the migration,
#   `feat(api): ... (#407)` for slice code, `feat(ui): ... (#407)` for the
#   replay wiring (or `feat(api,ui)` if combined). NO AI trailer (hook-enforced).

# RUNTIME-VERIFICATION LOG (per prp-create step 3 — re-run on library upgrade):
#   1. `uv run alembic heads` → 324a2fa37fcc (2026-06-12).
#   2. Pydantic exclude_unset distinguishes absent vs explicit-null, pattern
#      constraint skips the None arm of `str | None`, extra="forbid" 422s
#      unknown keys, strict=True accepts list[str] and rejects a bare str:
#      uv run python -c "
#      from pydantic import BaseModel, ConfigDict, Field
#      class P(BaseModel):
#          model_config = ConfigDict(strict=True, extra='forbid')
#          name: str | None = Field(default=None, max_length=100, pattern=r'^[a-z0-9][a-z0-9\-_]*$')
#          notes: str | None = Field(default=None, max_length=2000)
#          tags: list[str] | None = Field(default=None, max_length=20)
#      p = P.model_validate({'notes': None}); assert p.model_fields_set == {'notes'}
#      assert p.model_dump(exclude_unset=True) == {'notes': None}
#      assert P.model_validate({'name': None}).name is None        # null clears
#      assert P.model_validate({'tags': ['a','b']}).tags == ['a','b']
#      "
#      → verified on pydantic in-repo (2026-06-12).
#   3. SQLAlchemy 2.0.46: Boolean/Integer/JSONB server_default DDL compiles as
#      expected (`DEFAULT false NOT NULL`, `DEFAULT 1 NOT NULL`,
#      `DEFAULT '[]'::jsonb NOT NULL`):
#      uv run python -c "import sqlalchemy as sa; from sqlalchemy.dialects import postgresql; from sqlalchemy.schema import CreateTable; md=sa.MetaData(); t=sa.Table('x',md, sa.Column('archived',sa.Boolean(),nullable=False,server_default=sa.text('false')), sa.Column('v',sa.Integer(),nullable=False,server_default=sa.text('1')), sa.Column('tags',postgresql.JSONB(),nullable=False,server_default=sa.text(\"'[]'::jsonb\"))); print(CreateTable(t).compile(dialect=postgresql.dialect()))"
#      → verified (2026-06-12).
#   4. JSONB .contains() containment is already production code in this repo
#      (scenarios/service.py:464) — no external claim to probe.
```

## Implementation Blueprint

### Data models and structure

```python
# app/features/demo/models.py — ADD after result_summary (line 81), keep the
# existing __table_args__ entries and append the two new indexes.

    # ── E1 (#407) — lifecycle metadata ────────────────────────────────────
    # Orthogonal to `status` (which the pipeline owns): archive/pin are
    # operator curation flags, PATCH-mutable, default false.
    archived: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    pinned: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    # Free-text operator annotation; length capped at the Pydantic boundary (2000).
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Queryable JSONB string array — EXACT scenario_plan.tags pattern
    # (app/features/scenarios/models.py:74-76); GIN-indexed below.
    tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # Version of the workspace config + story-slot schema (umbrella #406
    # junk-drawer mitigation). Bump the ORM default when a slot shape changes.
    config_schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    # ── E1 (#407) — replay provenance ─────────────────────────────────────
    # SOFT reference to the workspace this run replayed (uuid4().hex of the
    # source row). Deliberately NO ForeignKey — not even self-referential:
    # ancestor rows must stay independently deletable (metadata-only delete),
    # and dangling lineage pointers are expected, like every created_objects id.
    replayed_from_workspace_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )

    # ── E1 (#407) — documented JSONB story slots ──────────────────────────
    # Six dedicated nullable JSONB columns (precedent: created_objects /
    # result_summary). NULL = "slot never written" (distinct from empty).
    # E1 writes NONE of them; documented schema per slot (authoritative copy
    # in docs/_base/DOMAIN_MODEL.md):
    #   seed_overrides   (E3 #409 writes) — dict: the curated seeder-override
    #                    payload from the start frame, stored verbatim
    #                    (model_dump(mode="json")); replay echoes it.
    #   user_scope       (E3 #409 writes) — dict: operator-selected focus,
    #                    {"store_id": int, "product_id": int} (additive keys
    #                    allowed later).
    #   approval_events  (E5 #411 writes) — list[dict], append-only:
    #                    {"action_id": str, "tool_name": str,
    #                     "decision": "approved"|"rejected",
    #                     "decided_at": iso8601-str, "session_id": str}.
    #   rag_events       (E5 #411 writes) — list[dict], append-only:
    #                    {"event": "index"|"retrieve"|"skip", "detail": str,
    #                     "count": int, "occurred_at": iso8601-str}.
    #   job_ids          (later parallel epic) — list[str]: job / batch
    #                    sub-job ids the run submitted (soft references).
    #   phase_summaries  (later parallel epic) — list[dict], one per phase:
    #                    {"phase_name": str, "status": "pass"|"fail"|"warn"|"skip",
    #                     "steps": int, "duration_ms": float}.
    seed_overrides: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    user_scope: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    approval_events: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    rag_events: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    job_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    phase_summaries: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    # __table_args__ — APPEND (keep existing CheckConstraint + composite index):
    #   Index("ix_showcase_workspace_tags_gin", "tags", postgresql_using="gin"),
    #   Index("ix_showcase_workspace_replayed_from", "replayed_from_workspace_id"),
    # imports to extend: Text from sqlalchemy (others already imported).
```

```python
# app/features/demo/schemas.py — DemoRunRequest addition (after workspace_name,
# line 78) + validator extension.

    # E1 (#407): replay provenance. The frontend Replay handler sends the
    # SOURCE row's workspace_id; create_workspace records it verbatim on the
    # NEW row (soft reference — no existence check). JSON-native str → no
    # Field(strict=False) needed.
    replayed_from_workspace_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{32}$",   # uuid4().hex shape of workspace_id
        description="workspace_id this run replays; requires preservation='keep'.",
    )

    @model_validator(mode="after")
    def _replayed_from_requires_keep(self) -> DemoRunRequest:
        """Reject a lineage pointer on a run that writes no workspace row."""
        if self.replayed_from_workspace_id is not None and self.preservation != "keep":
            raise ValueError("replayed_from_workspace_id requires preservation='keep'")
        return self


# NEW request model — place after DemoRunRequest.
# (add `field_validator` to the pydantic import at schemas.py:14 — the file
#  currently imports only BaseModel/ConfigDict/Field/model_validator)
class WorkspaceUpdateRequest(BaseModel):
    """Partial lifecycle update for PATCH /demo/workspaces/{workspace_id}.

    exclude_unset semantics: only fields present in the body are applied;
    explicit ``null`` clears ``name`` / ``notes``. Explicit ``null`` on
    ``archived`` / ``pinned`` / ``tags`` is rejected (422) — they back NOT NULL
    columns; send ``[]`` to clear tags. ``extra="forbid"`` so a typo'd field
    422s instead of silently no-opping (RunUpdate precedent,
    app/features/registry/schemas.py:113). All fields JSON-native -> the
    model-level strict=True needs no per-field override. ``status`` is
    deliberately absent — the pipeline owns the run lifecycle.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str | None = Field(
        default=None,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9\-_]*$",   # same as workspace_name
        description="Rename the workspace; explicit null clears the label.",
    )
    notes: str | None = Field(
        default=None, max_length=2000,
        description="Free-text annotation; explicit null clears it.",
    )
    tags: list[str] | None = Field(
        default=None, max_length=20,
        description="Replace the full tag list (not a merge).",
    )
    archived: bool | None = Field(default=None, description="Archive flag.")
    pinned: bool | None = Field(default=None, description="Pin flag.")

    @field_validator("archived", "pinned", "tags")
    @classmethod
    def _reject_explicit_null(cls, v: bool | list[str] | None) -> bool | list[str]:
        # Fires only on explicitly provided values (pydantic skips validators for
        # defaults unless validate_default=True), so absent stays None/unset while
        # an explicit {"archived": null} / {"tags": null} 422s instead of reaching
        # the NOT NULL column via exclude_unset -> setattr -> IntegrityError 500.
        # tags: send [] to clear, never null.
        if v is None:
            raise ValueError(
                "archived/pinned accept only true/false and tags accepts a list "
                "(send [] to clear) — explicit null is not allowed"
            )
        return v


# Response additions (additive — keep from_attributes, NOT strict):
# WorkspaceListItem  += archived: bool, pinned: bool, tags: list[str]
#                       (default_factory=list), replayed_from_workspace_id: str | None
# WorkspaceDetailResponse += notes: str | None, config_schema_version: int,
#                       seed_overrides / user_scope: dict[str, Any] | None,
#                       approval_events / rag_events / phase_summaries:
#                       list[dict[str, Any]] | None, job_ids: list[str] | None
```

```python
# app/features/demo/workspace.py — update_workspace (NEW; caller-owned session,
# raises normally — this backs an HTTP route, NOT the pipeline).
async def update_workspace(
    db: AsyncSession,
    workspace_id: str,
    update: WorkspaceUpdateRequest,
) -> ShowcaseWorkspace | None:
    """Apply a partial lifecycle update; return the row or None when missing."""
    row = await get_workspace(db, workspace_id)
    if row is None:
        return None
    changes = update.model_dump(exclude_unset=True)   # absent != explicit null
    for field, value in changes.items():
        setattr(row, field, value)                    # whole-value ASSIGNMENT (JSONB gotcha)
    await db.commit()
    await db.refresh(row)
    logger.info("demo.workspace_updated", workspace_id=workspace_id, fields=sorted(changes))
    return row

# create_workspace — ONE added kwarg in the ShowcaseWorkspace(...) constructor:
#     replayed_from_workspace_id=req.replayed_from_workspace_id,
```

```python
# app/features/demo/routes.py — PATCH route (mirror the DELETE shape @138).
@router.patch(
    "/workspaces/{workspace_id}",
    response_model=WorkspaceDetailResponse,
    summary="Update a saved showcase workspace's lifecycle metadata",
    description=(
        "Partial update: rename / notes / tags / archive / pin. Only fields "
        "present in the body change; explicit null clears name/notes. The run "
        "lifecycle status is not patchable."
    ),
)
async def update_showcase_workspace(
    workspace_id: str,
    update: WorkspaceUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> WorkspaceDetailResponse:
    row = await workspace.update_workspace(db, workspace_id, update)
    if row is None:
        raise NotFoundError(message=f"Workspace not found: {workspace_id}")
    return WorkspaceDetailResponse.model_validate(row)
```

### List of tasks (dependency order)

```yaml
Task 1 — branch & issue hygiene:
  RUN: git switch dev && git pull && git switch -c feat/showcase-completion-e1-metadata-provenance
  VERIFY: gh issue view 407 --json state   # open
  NOTE: git status shows untracked docker-compose.lan.yml on this host — leave it alone.

Task 2 — MODIFY app/features/demo/models.py:
  - ADD the 12 columns per the blueprint (lifecycle block, provenance column, six slots)
  - ADD `Text` to the sqlalchemy import line (others already imported)
  - APPEND the two indexes to __table_args__ (tags GIN + replayed_from btree)
  - EXTEND the module docstring: replayed_from_workspace_id is a soft reference
    (no FK, not even self-referential); story slots NULL until their writer epic lands
  - PRESERVE: existing columns, constants, CheckConstraint, composite index — untouched

Task 3 — CREATE alembic/versions/<rev>_add_showcase_workspace_metadata_provenance.py:
  - down_revision = "324a2fa37fcc"
  - MIRROR: bb8c4587ef1d_add_scenario_library_columns.py (add_column + GIN + downgrade order)
  - upgrade(): op.add_column x12 (server_defaults: archived/pinned text("false"),
    config_schema_version text("1"), tags text("'[]'::jsonb"); the rest nullable),
    then op.create_index("ix_showcase_workspace_tags_gin", ..., postgresql_using="gin")
    and op.create_index("ix_showcase_workspace_replayed_from", ...)
  - downgrade(): drop the two indexes (GIN drop with postgresql_using="gin",
    matching bb8c4587ef1d:50), then drop the 12 columns in reverse order
  - VERIFY: docker compose up -d &&
    uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head

Task 4 — MODIFY app/features/demo/schemas.py:
  - ADD DemoRunRequest.replayed_from_workspace_id + _replayed_from_requires_keep
    validator (blueprint); UPDATE the docstring sentence listing JSON-native fields
  - ADD WorkspaceUpdateRequest (blueprint) — placed after DemoRunRequest
  - EXTEND WorkspaceListItem (+archived/pinned/tags/replayed_from_workspace_id)
    and WorkspaceDetailResponse (+notes/config_schema_version/six slots) additively

Task 5 — MODIFY app/features/demo/workspace.py:
  - create_workspace: add replayed_from_workspace_id=req.replayed_from_workspace_id
    to the ShowcaseWorkspace(...) constructor (one line; warn-and-continue untouched)
  - ADD update_workspace (blueprint) + the WorkspaceUpdateRequest import
  - UPDATE module docstring routing note (PATCH now routed too)

Task 6 — MODIFY app/features/demo/routes.py:
  - ADD the PATCH route (blueprint) between GET detail and DELETE
  - ADD WorkspaceUpdateRequest to the schemas import block
  - UPDATE the module docstring endpoint list

Task 7 — MODIFY frontend (two additive lines):
  - frontend/src/types/api.ts DemoRunRequest (@778): add
    `// E1 (#407) — replay provenance: the source workspace_id a Replay re-runs.`
    `replayed_from_workspace_id?: string`
  - frontend/src/pages/showcase.tsx handleReplayWorkspace start() call (@179-185):
    add `replayed_from_workspace_id: ws.workspace_id,`
  - DO NOT touch handleLoadWorkspace (Load is read-only) or WorkspacePanel

Task 8 — tests (full matrix in Validation Loop):
  - MODIFY tests/test_schemas.py   (unit)
  - MODIFY tests/test_models.py    (@pytest.mark.integration)
  - MODIFY tests/test_workspace.py (@pytest.mark.integration)
  - MODIFY tests/test_routes.py    (PATCH 200/404/422; unit-shaped via monkeypatched
    workspace.update_workspace where the existing file does so, integration otherwise —
    follow whichever convention the existing GET/DELETE tests use)

Task 9 — docs (additive):
  - docs/_base/API_CONTRACTS.md:
    * NEW row: `demo | PATCH | /demo/workspaces/{workspace_id} | E1 (#407) — partial
      lifecycle update (name/notes/tags/archived/pinned; exclude_unset, explicit null
      clears name/notes; status NOT patchable); 404 problem+json when missing; 422 on
      unknown keys / bad name pattern / >20 tags; empty body = 200 no-op`
    * POST /demo/run row + WS /demo/stream section: additive Optional
      `replayed_from_workspace_id` (`^[0-9a-f]{32}$`, requires preservation='keep');
      Replay now sends it; recorded verbatim as a soft reference
    * GET /demo/workspaces rows: note the additive response fields
  - docs/_base/DOMAIN_MODEL.md § showcase_workspace:
    * Stored metadata: add lifecycle columns + config_schema_version semantics
    * JSONB fields: add the six story slots WITH their documented schemas (copy the
      model-comment schemas verbatim — this is the authoritative copy)
    * Invariants: replayed_from_workspace_id is a SOFT reference (no FK, dangles OK);
      status not patchable; archived orthogonal to status
    * Trim the "Out of scope" line that lists `replayed_from` as not-modeled (now shipped)
  - docs/_base/RUNBOOKS.md § Showcase workspace: remove `replayed_from` from the
    "Explicitly out of scope" list (one-line edit; the full runbook sweep is E7)

Task 10 — gates, commit, PR:
  - RUN the full Validation Loop (Levels 1-4)
  - git diff --stat   # surgical diffs only (CRLF noise check)
  - COMMITS (reference #407, no AI trailer), e.g.:
      feat(db): extend showcase_workspace with metadata and provenance columns (#407)
      feat(api): add workspace patch lifecycle endpoint and replay provenance (#407)
      feat(ui): send replayed_from_workspace_id on showcase replay (#407)
      docs(repo): document workspace story slots and patch contract (#407)
  - PR into dev; title `feat(api,db): showcase-completion E1 — workspace metadata & provenance backbone (#407)`
```

### Integration Points

```yaml
DATABASE:
  - migration: 12 add_column on showcase_workspace + ix_showcase_workspace_tags_gin (GIN)
    + ix_showcase_workspace_replayed_from (btree); clean downgrade
  - registration: alembic/env.py already imports demo models (line 19) — NO change

CONFIG: none — no new settings, no env vars.

ROUTES: PATCH /demo/workspaces/{workspace_id} on the existing demo router — no
  app/main.py change (router already wired).

PIPELINE: none — create_workspace reads the new field straight off req; the
  keep-branch hook (pipeline.py:2652) and finalize hook (2741) are untouched.

FRONTEND: two additive lines (Task 7). No new components; lineage badge/chain is E2.

DOCS: API_CONTRACTS + DOMAIN_MODEL (+ one-line RUNBOOKS trim). Full sweep is E7.
```

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
# Expected: clean. Both type checkers are --strict and gate merge.
```

### Level 2: Unit Tests (no DB)

```python
# tests/test_schemas.py — add:
def test_demo_run_request_replayed_from_default_none() -> None: ...
    # DemoRunRequest() -> replayed_from_workspace_id is None; legacy frame
    # model_validate({"seed": 7}) still validates

def test_demo_run_request_replayed_from_json_path() -> None: ...
    # MANDATORY json-dict path (security-patterns.md § strict mode):
    # model_validate({"preservation": "keep", "replayed_from_workspace_id": "a"*32})

def test_demo_run_request_replayed_from_requires_keep() -> None: ...
    # pytest.raises(ValidationError): model_validate({"replayed_from_workspace_id": "a"*32})

def test_demo_run_request_replayed_from_pattern_rejected() -> None: ...
    # "not-hex!", "ABC..." (uppercase), 31-char and 33-char values all raise

def test_workspace_update_request_partial_fields_set() -> None: ...
    # model_validate({"notes": None}).model_dump(exclude_unset=True) == {"notes": None}
    # model_validate({}).model_dump(exclude_unset=True) == {}

def test_workspace_update_request_rejects_unknown_key() -> None: ...
    # model_validate({"status": "archived"}) raises (extra="forbid" — status not patchable)

def test_workspace_update_request_name_pattern_and_tags_cap() -> None: ...
    # "Bad Name!" raises; 21 tags raises; ["workspace:x", "demo"] passes

def test_workspace_update_request_rejects_explicit_null_flags() -> None: ...
    # pytest.raises(ValidationError): model_validate({"archived": None})
    # pytest.raises(ValidationError): model_validate({"pinned": None})
    # pytest.raises(ValidationError): model_validate({"tags": None})
    # model_validate({"tags": []}) passes (the sanctioned clear path)
    # (NOT NULL columns — explicit null must 422, never reach setattr)

# tests/test_routes.py — add (follow the file's existing GET/DELETE conventions):
async def test_patch_workspace_happy_path(...) -> None: ...
    # PATCH {"name": "renamed", "pinned": true, "tags": ["t1"]} -> 200; response
    # echoes the changes and the untouched fields
async def test_patch_workspace_missing_404_problem_json(...) -> None: ...
    # status 404; content-type application/problem+json
async def test_patch_workspace_unknown_field_422(...) -> None: ...
    # body {"bogus": 1} -> 422 problem+json
async def test_patch_workspace_explicit_null_archived_422(...) -> None: ...
    # body {"archived": null} -> 422 problem+json (NOT NULL column guard)
async def test_patch_workspace_empty_body_noop_200(...) -> None: ...
async def test_run_demo_rejects_replayed_from_without_keep_422(...) -> None: ...
```

```bash
uv run pytest app/features/demo -v -m "not integration"
uv run pytest app/core/tests/test_strict_mode_policy.py -v   # AST walker still green
```

### Level 3: Integration (real Postgres)

```python
# tests/test_models.py — @pytest.mark.integration, extend:
#   - insert with NO new kwargs -> archived=False, pinned=False, tags=[],
#     config_schema_version=1, all six slots None, replayed_from None
#     (server_default + ORM default agreement)
#   - tags JSONB roundtrip + containment: insert tags=["workspace:x","demo"];
#     select(...).where(ShowcaseWorkspace.tags.contains(["demo"])) finds it
#     (scenarios/service.py:464 query shape)
#   - story-slot roundtrip: write a dict into seed_overrides and a list[dict]
#     into approval_events; read back identical
#   - status CHECK still enforced (regression — constraint untouched)

# tests/test_workspace.py — @pytest.mark.integration, extend:
#   - create_workspace with req.replayed_from_workspace_id set -> column recorded
#     verbatim; without it -> None (legacy identical)
#   - update_workspace partial: set name+pinned only -> other fields untouched;
#     explicit name=None clears; tags replaced whole (not merged);
#     missing workspace_id -> returns None (route maps to 404)
#   - update_workspace empty request -> no-op, row returned
```

```bash
docker compose up -d
uv run alembic upgrade head
uv run alembic downgrade -1 && uv run alembic upgrade head   # downgrade is clean
uv run pytest app/features/demo -v -m integration
```

### Level 4: Manual smoke (seeded local stack, uvicorn on :8123 + vite)

```bash
# 1. Keep-run, then PATCH lifecycle round-trip:
curl -s -X POST http://localhost:8123/demo/run -H 'Content-Type: application/json' \
  -d '{"skip_seed": true, "preservation": "keep", "workspace_name": "e1-smoke"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['workspace_id'])"
WS=<that id>
curl -s -X PATCH http://localhost:8123/demo/workspaces/$WS \
  -H 'Content-Type: application/json' \
  -d '{"name": "e1-renamed", "notes": "smoke", "tags": ["smoke"], "pinned": true}' | python3 -m json.tool
curl -s -X PATCH http://localhost:8123/demo/workspaces/deadbeef -H 'Content-Type: application/json' -d '{}' \
  | python3 -m json.tool    # 404 problem+json

# 2. Replay provenance (browser): /showcase -> Saved workspaces -> Replay on
#    the e1-renamed row; after the run:
docker exec forecastlab-postgres psql -U forecastlab -d forecastlab -c \
  "SELECT workspace_id, name, replayed_from_workspace_id FROM showcase_workspace ORDER BY created_at DESC LIMIT 2;"
# Expect: newest row's replayed_from_workspace_id == $WS; the $WS row unchanged.

# 3. Frontend gates:
cd frontend && pnpm lint && pnpm test --run
# pnpm tsc -b — confirm no NEW errors vs the dev baseline (gate is vacuous-aware,
# see Known Gotchas).
```

## Final validation Checklist

- [ ] All five gates green: `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"`
- [ ] Integration suite green: `uv run pytest -v -m integration` (fresh docker-compose DB; reset first if the shared DB is polluted)
- [ ] Migration upgrade + downgrade clean on a fresh DB AND applies on a DB with existing workspace rows
- [ ] Legacy surfaces byte-identical: start frame without new keys, GET list/detail for old rows (new fields all default/null), `test_strict_mode_policy.py` green
- [ ] PATCH 200 / 404 / 422 paths verified (Level 2 + Level 4)
- [ ] Replay records `replayed_from_workspace_id`; source row untouched (Level 4 step 2)
- [ ] `git diff --stat` shows surgical diffs (no CRLF whole-file noise)
- [ ] docs/_base/API_CONTRACTS.md + DOMAIN_MODEL.md updated additively (slot schemas documented); RUNBOOKS out-of-scope line trimmed
- [ ] Commits `feat(db)/feat(api)/feat(ui)/docs(repo): ... (#407)`, no AI trailer; PR into dev

---

## Anti-Patterns to Avoid

- ❌ Don't add ANY ForeignKey — not even self-referential on `replayed_from_workspace_id`. Soft references only.
- ❌ Don't edit `324a2fa37fcc_create_showcase_workspace_table.py` — new revision off head `324a2fa37fcc`.
- ❌ Don't make `status` patchable or widen `ck_showcase_workspace_status` — `archived` is the orthogonal flag.
- ❌ Don't add `extra="forbid"` to `DemoRunRequest` (WS compat) — but DO add it to `WorkspaceUpdateRequest`.
- ❌ Don't write any story slot from E1 production code — columns + docs + roundtrip tests only.
- ❌ Don't validate that `replayed_from_workspace_id` points at an existing row — it's a soft reference; dangles are designed.
- ❌ Don't wrap `update_workspace` in warn-and-continue — that contract is pipeline-only; HTTP helpers raise.
- ❌ Don't add list filtering/sorting/search or archive-hiding — that's E2 (#408).
- ❌ Don't add a replay confirmation dialog or lineage UI — E2 (#408).
- ❌ Don't mutate JSONB values in place — always assign whole values.
- ❌ Don't import another feature slice from `app/features/demo/` — core/shared only.

## Notes for parallel-epic PRP authors (#408–#412)

- The column set, slot names, and per-slot schemas above are the frozen E1 contract.
  `job_ids` / `phase_summaries` have a documented schema but NO assigned writer in
  E1 — E2 (#408, health summary) and E4 (#410, config echo) should agree on which
  populates which and follow the documented shapes.
- Slot writes that happen DURING a pipeline run inherit the warn-and-continue
  invariant (extend `finalize_workspace` / add sibling helpers in `workspace.py`);
  slot writes via HTTP go through caller-owned-session helpers like
  `update_workspace`.
- Tag filtering on `GET /demo/workspaces` (E2) should reuse the
  `ShowcaseWorkspace.tags.contains([...])` containment shape proven in E1's
  integration test, mirroring `GET /scenarios?tags=` (scenarios/routes.py:180).
- A schema change to any slot bumps `config_schema_version` (ORM default) and
  documents the delta in DOMAIN_MODEL.

## Confidence Score

**9/10** for one-pass implementation success. Every element has a verified in-repo
precedent: the add-columns+GIN migration (`bb8c4587ef1d`), the tags column
(`scenarios/models.py:74`), the partial-update schema (`registry RunUpdate`), the
404-on-missing route shape (the demo DELETE), and the request-field+validator pattern
(`workspace_name`, same file). The three judgment calls (tags representation, slot
shape, no-FK soft reference) are resolved and frozen above, and all changes are
additive — a wrong slot-schema guess costs a documented `config_schema_version` bump,
not a rework. The −1: the PATCH route tests must match whichever
unit-vs-integration convention `test_routes.py` currently uses for the workspace
GET/DELETE endpoints (read it first), and the frontend type-gate baseline is fuzzy
on this host (`tsc -b` has pre-existing dev failures — gate on "no NEW errors").
