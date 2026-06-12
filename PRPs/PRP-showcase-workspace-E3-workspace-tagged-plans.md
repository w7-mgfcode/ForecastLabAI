name: "PRP — Showcase Workspace E3: Workspace-Tagged Scenario Plans (issue #392)"
description: |

## Purpose

Implement the workspace-tagging epic of the showcase-workspace initiative
(umbrella #389): the two scenario plans the showcase pipeline saves
(`showcase-price-cut-10pct`, `showcase-holiday-uplift`) gain workspace-aware
tags — `["showcase", "<kind>", "source:showcase"]` plus `workspace:<name>` on
`preservation="keep"` runs — via the existing GIN-indexed `scenario_plan.tags`
column, and the What-If Planner's saved-plans library gains a tag filter (with
deep-linkable `?tags=` URL state) so a workspace's plans are retrievable via
`GET /scenarios?tags=workspace:<name>`. Parallel epic after Foundation E1
(#390); independent of E2 (#391, merged) and E4 (#393, PRP authored, not
started).

## Core Principles

1. **Context is King**: every reference below was verified against the live code on 2026-06-12 (branch `dev` @ 3194fe8, post-E1/E2 merge).
2. **Validation Loops**: each level is executable as written.
3. **Information Dense**: patterns cite exact file:line.
4. **Progressive Success**: tag helper → pipeline steps → step tests → planner filter → URL state → docs.
5. **Global rules**: follow CLAUDE.md / AGENTS.md; all five CI gates must pass; UI work follows `.claude/rules/ui-design.md` + `shadcn-ui.md`.

---

## Goal

A showcase run that saves scenario plans stamps them with discoverable,
namespaced tags: every pipeline-saved plan carries `source:showcase` (alongside
the existing `showcase` + `price`/`holiday` tags, kept for back-compat), and a
`preservation="keep"` run additionally stamps `workspace:<name>` (falling back
to `workspace:<workspace_id>` on unnamed keep runs). On the What-If Planner,
the operator filters the saved-plans library by tag — clicking a tag badge in
the table adds it to the filter, active filters render as removable chips, the
filter round-trips through the `?tags=` query string (so
`/visualize/planner?tags=workspace:black-friday` deep-links straight to one
workspace's plans), and the server does the filtering via the existing JSONB
containment query. Ephemeral runs and legacy plans behave exactly as today.

**Deliverable** (all additive — no migration, no schema change, no new endpoints):

- `app/features/demo/pipeline.py` — `DemoContext.workspace_name` field; new pure `_showcase_plan_tags()` helper; the two `POST /scenarios` bodies use it.
- `app/features/demo/tests/test_pipeline.py` — helper unit tests + updated step-body assertions (keep vs ephemeral, named vs unnamed).
- `app/features/scenarios/tests/test_routes_integration.py` — one integration test proving the umbrella criterion verbatim: plans saved with `workspace:<name>` are retrievable via `GET /scenarios?tags=workspace:<name>`.
- `frontend/src/lib/url-params.ts` — `parseTagsParam()` reader (+ tests in `url-params.test.ts`).
- `frontend/src/pages/visualize/planner.tsx` — tag-filter state wired into `useScenarios(tags)`, clickable tag badges, active-filter chips, `?tags=` URL sync.
- `docs/_base/API_CONTRACTS.md` — additive E3 note on the `WS /demo/stream` planning steps.

**Success definition**: all Success Criteria below check off, the five CI gates
are green, frontend gates green, and a manual dogfood shows a keep-run's plans
filtered by `workspace:<name>` in the planner — and reachable by pasting the
deep-link URL.

## Why

- E1 records *which* plan ids a workspace created (`created_objects.scenario_plan_ids`, `app/features/demo/workspace.py:97`), but the plans themselves are unfindable from the planner — the library has NO filter UI even though the backend (`GET /scenarios?tags=`, JSONB `@>` containment, `app/features/scenarios/service.py:462-465`) and the frontend hook (`useScenarios(tags)`, `frontend/src/hooks/use-scenarios.ts:28-38`) have supported tag filtering since PRP-27.
- The pipeline already tags plans — but with fixed, workspace-blind values: `["showcase", "price"]` (`app/features/demo/pipeline.py:1309`) and `["showcase", "holiday"]` (`pipeline.py:1371`). Across runs, every plan looks identical.
- Umbrella #389 success criterion: "Showcase-saved scenario plans carry `["showcase", "workspace:<name>", "source:showcase"]` and are retrievable via `GET /scenarios?tags=workspace:<name>`".
- E4 (#393, PRP authored) renders per-workspace plan deep links from `created_objects`; E3's tag filter is the complementary bulk view ("all plans of workspace X") and the `?tags=` deep link gives E4/E5 a stable URL target.

## What

### Designed tag taxonomy (locked decisions)

| Run | Tags on `showcase-price-cut-10pct` | Tags on `showcase-holiday-uplift` |
|-----|-----|-----|
| Ephemeral showcase run | `["showcase", "price", "source:showcase"]` | `["showcase", "holiday", "source:showcase"]` |
| Keep run, named `bf-demo` | `[..., "source:showcase", "workspace:bf-demo"]` | same + `workspace:bf-demo` |
| Keep run, unnamed | `[..., "source:showcase", "workspace:<workspace_id>"]` | same |

1. **`showcase` + `price`/`holiday` stay** — existing plans and any operator filters keep working (back-compat; tags are append-only semantics).
2. **`source:showcase` always** — every pipeline-saved plan is showcase-sourced regardless of preservation; this is the namespaced successor to the bare `showcase` tag (umbrella triple).
3. **`workspace:<label>` only when a workspace row exists** (`ctx.workspace_id` non-None — i.e. `preservation="keep"` AND the E1 insert succeeded). Label = `workspace_name` when set, else the 32-hex `workspace_id` — an unnamed workspace's plans stay findable, and the label can never be empty.
4. **The agent-HITL plan is OUT OF SCOPE** — `step_agent_hitl_flow`'s plan is saved through the agent tool path (`SaveScenarioRequest`, `app/features/scenarios/agent_tools.py:35,199`) which carries no `tags` field; threading workspace context into the agent session is a cross-slice change deferred to a future epic. Note it in the PR description.
5. **No tag editing/deleting UI** — the filter reads tags; managing them is out of scope (umbrella).

### User-visible behavior

- New keep-run plans carry the workspace tag; `GET /scenarios?tags=workspace:<label>` returns exactly that workspace's two plans (JSONB containment, all listed tags must match).
- Planner saved-plans library: tags render as clickable badges; clicking adds the tag to the active filter; active filters show as chips with per-chip remove and a "Clear" action; the table re-queries server-side via `useScenarios(tagFilter)`; an active filter with zero matches shows a distinct empty-state ("No plans match the selected tags") instead of the no-plans-yet message.
- The filter syncs to the URL as repeated `?tags=` params (read on mount, written on change) — shareable/deep-linkable.
- The `scenario_simulate_and_save` step's `data` payload additively carries the `tags` list it sent (UI/e2e observability).

### Technical requirements

- Tag derivation is one pure, unit-testable helper in `pipeline.py`; both save steps call it (no duplicated literals).
- `ctx.workspace_name` is set in `run_pipeline` alongside the E1 `create_workspace` hook — steps never see the request object (signature is `(ctx, client)`, `pipeline.py:1242`).
- `CreateScenarioRequest.tags` caps at 20 items (`app/features/scenarios/schemas.py:203-207`, `Field(max_length=20)` = max list items); E3 sends 4 — no limit risk. Items are unconstrained `str` — colons are fine (the existing `cloned_from`/tag tests and the `workspace:<name>` umbrella spec rely on this).
- No scenarios-slice production code changes — routes/service/schemas already support everything.
- Frontend: `useScenarios(tags)` already encodes repeated `tags=` params and keys the query on `{tags}` (`use-scenarios.ts:28-38`) — refetch on filter change is free.

### Success Criteria

- [ ] `_showcase_plan_tags` unit-tested: ephemeral → 3 tags, keep+named → +`workspace:<name>`, keep+unnamed → +`workspace:<workspace_id>`; both steps send helper output.
- [ ] Integration: two plans POSTed with `workspace:e3-it` among tags → `GET /scenarios?tags=workspace:e3-it` returns exactly them; adding a second tag (`tags=workspace:e3-it&tags=price`) narrows to one (containment semantics).
- [ ] Planner: clicking a tag badge filters the table server-side; chips removable; Clear resets; filtered-empty state distinct from no-plans state.
- [ ] `/visualize/planner?tags=workspace:x` pre-applies the filter on load; changing the filter updates the URL.
- [ ] Legacy behavior intact: plans saved before E3 (no `source:showcase`) still list unfiltered; ephemeral-run plans carry no `workspace:` tag.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"` green; integration suite green; `pnpm lint && pnpm test --run` green.

## All Needed Context

### Documentation & References

```yaml
# MUST READ — backend (verified 2026-06-12, dev @ 3194fe8)

- file: app/features/demo/pipeline.py
  why: |
    THE file E3 changes. DemoContext dataclass at 212-260 — add
    `workspace_name: str | None = None` directly under `workspace_id` (260)
    with an `# E3 (#392)` comment (per-PRP comment convention visible at
    238/241/249/254/258). step_scenario_simulate_and_save at 1242 — the POST
    /scenarios body with `"tags": ["showcase", "price"]` is at 1300-1311
    (tags literal: 1309); its return data dict at 1337-1344 (add "tags").
    step_multi_plan_compare at 1348 — body with ["showcase", "holiday"] at
    1362-1372 (tags literal: 1371). run_pipeline ctx construction at
    2625-2630; the E1 keep-branch `ctx.workspace_id = await
    workspace.create_workspace(req)` at 2634-2635 — set ctx.workspace_name
    in the same branch. Steps receive ONLY (ctx, client) — never req.

- file: app/features/demo/workspace.py
  why: |
    _collect_created_objects (81-102) records scenario_plan_ids — E3's tags
    complement (don't replace) this linkage. READ-ONLY; cite for the
    workspace_id format (uuid4().hex, 32 chars — the unnamed-fallback label).

- file: app/features/demo/schemas.py
  why: |
    DemoRunRequest.workspace_name (72-78): max_length=100, pattern
    ^[a-z0-9][a-z0-9\-_]*$ — so the derived tag is ≤ 110 chars of safe
    charset; no sanitization needed in the helper. READ-ONLY in E3.

- file: app/features/scenarios/schemas.py
  why: |
    CreateScenarioRequest.tags at 203-207: list[str], Field(max_length=20)
    = max 20 ITEMS, items unconstrained str. NO schema change needed.

- file: app/features/scenarios/service.py
  why: |
    list_plans tags containment at 462-465: `ScenarioPlan.tags.contains(tags)`
    (JSONB @>) on both count and rows statements — "a plan matches when it
    carries EVERY listed tag". This is the server-side filter the planner UI
    drives. NO change needed.

- file: app/features/scenarios/routes.py
  why: |
    GET /scenarios `tags: list[str] | None = Query(...)` at 176-195 — repeated
    query params. NO change needed; cited so the implementer trusts the wire
    format useScenarios already emits.

- file: app/features/scenarios/agent_tools.py
  why: |
    Lines 35, 199 — the agent save path uses SaveScenarioRequest (NO tags
    field). Out-of-scope boundary for decision #4; do not modify.

- file: app/features/demo/tests/test_pipeline.py
  why: |
    The canned _Client fake echoes tags ("tags": json_body.get("tags", []),
    line 140). EXISTING ASSERTIONS TO UPDATE: line 1133 asserts
    body["tags"] == ["showcase", "price"] in
    test_scenario_simulate_and_save_happy_path (1094); multi-plan tests at
    1268/1312/1333. Test ctx factories build DemoContext directly — keep
    runs are simulated by setting ctx.workspace_id/workspace_name, NOT by
    running the orchestrator.

- file: app/features/scenarios/tests/test_routes_integration.py
  why: |
    Target file for the round-trip integration test (currently has NO tags
    coverage — verified by grep). Reuse its existing client/DB fixtures and
    cleanup conventions; mark @pytest.mark.integration like its siblings.

- file: app/features/scenarios/tests/conftest.py
  why: Integration DB/client fixture precedent for the new test.

# MUST READ — frontend (verified 2026-06-12)

- file: frontend/src/pages/visualize/planner.tsx
  why: |
    814 lines. Results/persistence state block at 117-126 — add tagFilter
    state here. Hook calls at 128-133: `const scenariosQuery = useScenarios()`
    at 132 — becomes useScenarios(tagFilter). Saved-plans Card at 669-762:
    CardHeader 671-694 (add the active-filter chip row + Clear here), Tags
    cell at 724-726 (`plan.tags.join(', ')` — replace with clickable Badge
    list), empty-state at 756-760 (branch on active filter). NO
    useSearchParams usage today (verified) — add it.

- file: frontend/src/hooks/use-scenarios.ts
  why: |
    useScenarios(tags = [], enabled = true) at 28-38: encodes repeated
    `tags=` params, queryKey ['scenarios', { tags }] — the page only needs
    to pass state in. NO hook change needed.

- file: frontend/src/lib/url-params.ts
  why: |
    Safe query-param readers with validate-at-read-boundary docstring
    pattern (1-9). parsePageParam (17), parseIdParam (29), parseEnumParam
    (41) — ADD parseTagsParam following this style. Tests colocated in
    url-params.test.ts.

- file: frontend/src/pages/explorer/run-compare.tsx
  why: |
    useSearchParams precedent at 87 (`const [params, setParams] =
    useSearchParams()`) — the read/write URL-state pattern to mirror
    (explorer pages treat the query string as filter source of truth).

- file: frontend/src/components/ui/badge.tsx
  why: |
    Installed shadcn Badge — use for tag chips (variant="secondary" for
    inactive, "default" for active filters). Do NOT run shadcn add.

- file: frontend/src/types/api.ts
  why: |
    ScenarioListItem.tags: string[] already typed (search "tags" in the
    scenarios block) — NO type changes needed in E3.

# Issue / initiative context
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/392
  why: The epic this PRP implements.
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/389
  why: Umbrella — tag-triple success criterion + out-of-scope list.
- file: PRPs/PRP-showcase-workspace-E1-persistence-backbone.md
  why: Foundation PRP — workspace row lifecycle the tags piggyback on.
- file: PRPs/PRP-showcase-workspace-E4-restore-replay.md
  why: |
    Parallel epic (authored, not started). File-overlap check: E4 touches
    demo routes/schemas/workspace.py + showcase.tsx; E3 touches pipeline.py +
    planner.tsx + url-params.ts. ONLY shared file: docs/_base/API_CONTRACTS.md
    (both additive). E4's WorkspaceArtifactsPanel links plans by id;
    E3's ?tags= deep link is the complementary bulk view.
```

### Current Codebase tree (relevant subset)

```bash
app/features/demo/
├── pipeline.py            # DemoContext @212-260; save steps @1242/@1348; ctx build @2626
└── tests/test_pipeline.py # canned client echoes tags @140; assertions @1133 etc.
app/features/scenarios/    # NO production changes — tags filter fully built (PRP-27)
└── tests/test_routes_integration.py   # no tags coverage yet
frontend/src/
├── pages/visualize/planner.tsx        # library card @669-762; useScenarios() @132
├── hooks/use-scenarios.ts             # useScenarios(tags) ready @28-38
└── lib/url-params.ts (+ .test.ts)     # param-reader helpers
```

### Desired Codebase tree (files added/modified)

```bash
app/features/demo/
├── pipeline.py                        # MOD — ctx.workspace_name; _showcase_plan_tags(); 2 call sites; step data +tags
└── tests/test_pipeline.py             # MOD — helper tests; updated step assertions; keep/unnamed variants
app/features/scenarios/tests/
└── test_routes_integration.py         # MOD — +workspace-tag containment round-trip test
frontend/src/
├── lib/url-params.ts                  # MOD — +parseTagsParam
├── lib/url-params.test.ts             # MOD — +parseTagsParam cases
└── pages/visualize/planner.tsx        # MOD — tagFilter state + URL sync + badges + chips + empty-state
docs/_base/API_CONTRACTS.md            # MOD — E3 note on the planning steps
```

### Known Gotchas & Library Quirks

```python
# CRITICAL — steps never see the request. step signatures are (ctx, client)
#   (pipeline.py:1242). workspace_name MUST travel on DemoContext, set in
#   run_pipeline's keep-branch (2634-2635). Do NOT widen step signatures.

# CRITICAL — set ctx.workspace_name from req.workspace_name INSIDE the
#   `if req.preservation == "keep":` branch BUT independent of the
#   create_workspace result: if the row insert failed (workspace_id None),
#   decision #3 says NO workspace tag — so the helper keys on
#   ctx.workspace_id (not workspace_name) for the "is this a workspace run"
#   check. A name with a dead DB produces NO tag (consistent with E1's
#   warn-and-continue: no row -> nothing to find later anyway).

# CRITICAL — JSONB containment filter is ALL-tags-must-match
#   (service.py:462-465, .contains = @>). The planner filter is therefore an
#   AND filter — say so in the UI copy ("plans carrying every selected tag").

# GOTCHA — tags order: append new tags AFTER the existing ones
#   (["showcase", "price", "source:showcase", "workspace:..."]) so the
#   existing test diffs stay minimal and human-readable. Order is irrelevant
#   to containment.

# GOTCHA — test_pipeline.py:1133 asserts the OLD exact list
#   ["showcase", "price"] — it (and the multi-plan equivalents) MUST be
#   updated, not deleted: assert the new exact list for an ephemeral ctx
#   (the default test ctx has workspace_id=None).

# GOTCHA — pyright/mypy --strict: _showcase_plan_tags returns list[str];
#   annotate fully. The dataclass field needs `str | None = None` (matches
#   sibling style at pipeline.py:236-260).

# GOTCHA — planner.tsx is a 814-line monolith with NO test file. Keep page
#   logic thin: validation logic goes in parseTagsParam (tested in
#   url-params.test.ts); the page just wires state. Do not extract a new
#   component unless the diff stays smaller that way (it won't — chips and
#   badges are ~30 lines inline).

# GOTCHA — useSearchParams: write with { replace: true } to avoid polluting
#   browser history on every chip toggle (run-compare.tsx:87 precedent uses
#   setParams; explorer pages show the read pattern). Read ONCE for initial
#   state (useState initializer) then treat React state as canonical and
#   mirror to the URL in the toggle handlers — planner has heavy local state
#   already; do not refactor it to URL-as-source-of-truth in this epic.

# GOTCHA — repeated params: searchParams.getAll('tags') reads them;
#   useScenarios already ENCODES each tag (encodeURIComponent,
#   use-scenarios.ts:31) — parseTagsParam receives DECODED values from
#   getAll (URLSearchParams decodes) — do not double-decode.

# GOTCHA — parseTagsParam hygiene: trim, drop empties, dedupe (Set), cap at
#   20 (matches CreateScenarioRequest.tags max items — a hand-edited URL
#   with 50 tags must not produce a 50-param query).

# GOTCHA — `pnpm tsc --noEmit` is VACUOUS (solution-style tsconfig); `tsc -b`
#   fails on dev with PRE-EXISTING errors — don't chase them. JS gates:
#   `pnpm lint && pnpm test --run`.

# GOTCHA — repo has mixed CRLF/LF line endings; pipeline.py + planner.tsx
#   edits must be surgical — check `git diff --stat` before committing.

# COORDINATION — E4 (#393) PRP is authored but unstarted; only shared file is
#   docs/_base/API_CONTRACTS.md (both additive notes). If E4 lands first, the
#   E4 demo-routes diff does not collide with E3's pipeline.py diff.

# RUNTIME-VERIFICATION LOG (per prp-create step 3):
#   - tags literals at pipeline.py:1309 / 1371 — read 2026-06-12
#   - DemoContext field block ends @260 (workspace_id) — read 2026-06-12
#   - ctx build @2625-2630; keep-branch @2634-2635 — read 2026-06-12
#   - CreateScenarioRequest.tags Field(max_length=20) @scenarios/schemas.py:203
#     — Pydantic v2 semantics: max_length on list = max ITEMS (in-repo
#     precedent relies on it; re-verify on pydantic major bump with:
#     uv run python -c "from pydantic import BaseModel, Field;
#     class M(BaseModel): t: list[str] = Field(default_factory=list, max_length=2)
#     import pydantic; M(t=['a','b','c'])"  -> expect ValidationError)
#   - list_plans containment @scenarios/service.py:462-465 — read 2026-06-12
#   - useScenarios(tags) encoding @use-scenarios.ts:28-38 — read 2026-06-12
#   - planner.tsx has NO useSearchParams; library card @669-762 — read 2026-06-12
#   - test_pipeline.py fake echoes tags @140; old assertion @1133 — read 2026-06-12
#   - agent_tools.py SaveScenarioRequest has NO tags @35,199 — grep-verified
```

## Implementation Blueprint

### Data models and structure

```python
# app/features/demo/pipeline.py — DemoContext addition (after workspace_id, line 260)
    # E3 (#392) -- workspace label for plan tagging. Set alongside
    # workspace_id in run_pipeline's keep-branch; None on ephemeral runs.
    workspace_name: str | None = None


# app/features/demo/pipeline.py — pure helper (place near the other module
# helpers under "Helpers shared across steps", after _parse_artifact_key)
def _showcase_plan_tags(ctx: DemoContext, kind: str) -> list[str]:
    """Build the tag list for a pipeline-saved scenario plan (E3, #392).

    Always: ["showcase", <kind>, "source:showcase"]. When the run records a
    workspace (ctx.workspace_id set -- preservation="keep" AND the E1 insert
    succeeded), append "workspace:<label>" where label is the human
    workspace_name or, on unnamed runs, the 32-hex workspace_id -- the label
    is never empty. No workspace row -> no workspace tag (nothing to find).
    """
    tags = ["showcase", kind, "source:showcase"]
    if ctx.workspace_id is not None:
        tags.append(f"workspace:{ctx.workspace_name or ctx.workspace_id}")
    return tags


# Call sites:
#   pipeline.py:1309  "tags": ["showcase", "price"]    -> "tags": _showcase_plan_tags(ctx, "price")
#   pipeline.py:1371  "tags": ["showcase", "holiday"]  -> "tags": _showcase_plan_tags(ctx, "holiday")
# Step data (1337-1344): add "tags": <the list sent> for observability.

# run_pipeline keep-branch (2634-2635) becomes:
    if req.preservation == "keep":
        ctx.workspace_id = await workspace.create_workspace(req)
        ctx.workspace_name = req.workspace_name  # E3 (#392) -- plan-tag label
```

```typescript
// frontend/src/lib/url-params.ts — append (mirror parseEnumParam doc style)
/**
 * Parse repeated `tags` query params into a clean filter list.
 *
 * Trims each value, drops empties, dedupes, and caps at 20 entries
 * (matches the backend CreateScenarioRequest.tags item cap) so a
 * hand-edited URL degrades to a sane query instead of a 50-param request.
 */
export function parseTagsParam(values: string[]): string[] {
  const seen = new Set<string>()
  for (const value of values) {
    const tag = value.trim()
    if (tag) seen.add(tag)
    if (seen.size >= 20) break
  }
  return [...seen]
}
```

```tsx
// frontend/src/pages/visualize/planner.tsx — wiring sketch
const [searchParams, setSearchParams] = useSearchParams()           // + import
const [tagFilter, setTagFilter] = useState<string[]>(() =>
  parseTagsParam(searchParams.getAll('tags'))
)
const scenariosQuery = useScenarios(tagFilter)                      // line 132

function applyTagFilter(next: string[]) {
  setTagFilter(next)
  setSearchParams(
    (prev) => {
      const params = new URLSearchParams(prev)
      params.delete('tags')
      next.forEach((t) => params.append('tags', t))
      return params
    },
    { replace: true }
  )
}
const addTag = (tag: string) => !tagFilter.includes(tag) && applyTagFilter([...tagFilter, tag])
const removeTag = (tag: string) => applyTagFilter(tagFilter.filter((t) => t !== tag))

// CardHeader (671-694): under the CardDescription, when tagFilter.length > 0:
//   <Badge> per active tag with an inline ✕ (lucide X, h-3 w-3) onClick=removeTag
//   + a ghost "Clear" Button onClick={() => applyTagFilter([])}
//   CardDescription suffix: "Filtering to plans carrying every selected tag."
// Tags cell (724-726): replace join(', ') with
//   plan.tags.map(tag => <Badge variant="secondary" className="cursor-pointer"
//     onClick={() => addTag(tag)}>{tag}</Badge>)  (keep '—' when empty)
// Empty state (756-760): tagFilter.length > 0
//   ? "No plans match the selected tags." + Clear button
//   : existing "No saved plans yet..." copy
```

### List of tasks (dependency order)

```yaml
Task 1 — branch & issue hygiene:
  RUN: git switch dev && git pull && git switch -c feat/showcase-workspace-tagged-plans
  VERIFY: gh issue view 392 --json state   # open

Task 2 — MODIFY app/features/demo/pipeline.py:
  - ADD DemoContext.workspace_name (blueprint above; after line 260, E3 comment)
  - ADD _showcase_plan_tags helper (blueprint above; full docstring + annotations)
  - REPLACE tags literal at 1309 with _showcase_plan_tags(ctx, "price");
    capture the list in a local (sent_tags) and ADD "tags": sent_tags to the
    step's return data dict (1337-1344)
  - REPLACE tags literal at 1371 with _showcase_plan_tags(ctx, "holiday")
  - run_pipeline keep-branch (2634-2635): + ctx.workspace_name = req.workspace_name

Task 3 — MODIFY app/features/demo/tests/test_pipeline.py:
  - ADD test__showcase_plan_tags_ephemeral / _keep_named / _keep_unnamed
    (pure-function tests; build DemoContext(seed=42, skip_seed=True,
    reset=False) and set workspace_id/workspace_name directly)
  - UPDATE test_scenario_simulate_and_save_happy_path (1094): assertion at
    1133 -> ["showcase", "price", "source:showcase"]; also assert
    data["tags"] echoes the same list
  - ADD test_scenario_simulate_and_save_keep_run_carries_workspace_tag:
    ctx.workspace_id = "a"*32; ctx.workspace_name = "bf-demo";
    assert "workspace:bf-demo" in captured body["tags"]
  - ADD a body-tags assertion to the multi-plan happy path (1268) — it has
    NO tags assertion today: holiday body tags ==
    ["showcase", "holiday", "source:showcase"] (+ a keep-run variant
    asserting the workspace tag flows to plan #2)

Task 4 — MODIFY app/features/scenarios/tests/test_routes_integration.py:
  - ADD @pytest.mark.integration test_list_scenarios_filters_by_workspace_tag:
    # POST /scenarios twice (existing create-body fixture/pattern in this
    # file) with tags ["showcase","price","source:showcase","workspace:e3-it"]
    # and ["showcase","holiday","source:showcase","workspace:e3-it"];
    # POST a third plan WITHOUT the workspace tag (control);
    # GET /scenarios?tags=workspace:e3-it -> exactly the 2, total == 2;
    # GET /scenarios?tags=workspace:e3-it&tags=price -> exactly 1 (AND);
    # cleanup via DELETE /scenarios/{id} (or the file's fixture teardown)

Task 5 — MODIFY frontend/src/lib/url-params.ts + url-params.test.ts:
  - ADD parseTagsParam (blueprint above)
  - Tests: empty array -> []; whitespace/empty entries dropped; duplicates
    deduped; >20 entries capped at 20; passthrough of 'workspace:bf-demo'

Task 6 — MODIFY frontend/src/pages/visualize/planner.tsx:
  - Imports: useSearchParams (react-router-dom), Badge, X (lucide),
    parseTagsParam
  - State + applyTagFilter/addTag/removeTag + useScenarios(tagFilter)
    (blueprint above)
  - CardHeader chips + Clear; clickable Badge tags cell; filtered empty-state
  - NOTE: 'scenarios' queryKey includes {tags} -> create/delete mutations
    invalidate the prefix and the filtered view refetches — no extra work

Task 7 — MODIFY docs/_base/API_CONTRACTS.md:
  - WS /demo/stream section, planning-phase description: append
    "E3 (#392) — pipeline-saved plans now carry source:showcase plus
    workspace:<name|workspace_id> on preservation='keep' runs; retrievable
    via GET /scenarios?tags=workspace:<label>. The
    scenario_simulate_and_save step's data additively echoes `tags`."

Task 8 — gates, dogfood, commit, PR:
  - Backend gates + integration suite (Validation Loop)
  - Frontend: pnpm lint && pnpm test --run
  - Browser dogfood via the webapp-testing skill (CLAUDE.md workflow step 4)
  - git diff --stat (CRLF noise check on pipeline.py / planner.tsx)
  - COMMITS (reference #392, no AI trailer), e.g.:
      feat(api): tag showcase plans with workspace label (#392)
      feat(ui): add tag filter to planner saved-plans library (#392)
      test(api): cover workspace-tag containment round trip (#392)
      docs(api): document workspace plan tags (#392)
  - PR into dev; title `feat(api,ui): showcase workspace-tagged scenario plans (#392)`
```

### Integration Points

```yaml
DATABASE: none — scenario_plan.tags (JSONB, GIN) exists since PRP-27.

CONFIG: none.

ROUTES: none — GET /scenarios?tags= already shipped.

FRONTEND: planner.tsx only; no new React Router routes; ?tags= deep link
  becomes a stable target for E4/E5 ("view this workspace's plans").

DOCS: docs/_base/API_CONTRACTS.md one additive note (Task 7). RUNBOOKS /
  DOMAIN_MODEL sweeps belong to the E5 release gate.
```

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
cd frontend && pnpm lint
```

### Level 2: Unit Tests (no DB)

```bash
uv run pytest app/features/demo -v -m "not integration"
cd frontend && pnpm test --run
# New/changed: _showcase_plan_tags cases; updated step-body assertions;
# parseTagsParam cases in url-params.test.ts.
```

### Level 3: Integration (real Postgres)

```bash
docker compose up -d && uv run alembic upgrade head
uv run pytest app/features/scenarios -v -m integration   # incl. the new tags round-trip
uv run pytest app/features/demo -v -m integration
```

### Level 4: Manual smoke + browser dogfood (seeded stack, uvicorn :8123)

```bash
# 1. Keep-run produces workspace-tagged plans (showcase_rich saves the plans).
#    NOTE: scenario_plan rows persist across showcase runs (reset does not wipe
#    them — RUNBOOKS incident 27), so use a UNIQUE name per smoke run:
WS_NAME="e3-smoke-$(date +%s)"
curl -s -X POST http://localhost:8123/demo/run -H 'Content-Type: application/json' \
  -d "{\"seed\":42,\"reset\":true,\"skip_seed\":false,\"scenario\":\"showcase_rich\",\"preservation\":\"keep\",\"workspace_name\":\"$WS_NAME\"}" \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['overall_status'], r['workspace_id'])"
curl -s "http://localhost:8123/scenarios?tags=workspace:$WS_NAME" \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['total'], [s['name'] for s in r['scenarios']])"
# Expect: 2 ['showcase-holiday-uplift', 'showcase-price-cut-10pct'] (order: newest first)

# 2. Browser dogfood (webapp-testing skill / agent-browser):
#    /visualize/planner -> Saved plans table shows tag badges -> click
#    workspace:e3-smoke -> table narrows to the 2 plans, chip appears, URL
#    carries ?tags=workspace%3Ae3-smoke -> paste that URL in a fresh tab ->
#    filter pre-applied -> remove chip -> full list returns.
```

## Final validation Checklist

- [ ] All five gates green: `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"`
- [ ] Integration suite green: `uv run pytest -v -m integration` (fresh docker-compose DB)
- [ ] Frontend gates green: `pnpm lint && pnpm test --run`
- [ ] Manual smoke (Level 4 step 1): keep-run plans retrievable via `?tags=workspace:<name>`
- [ ] Browser dogfood (Level 4 step 2) passes — UI verified in a real browser per `.claude/rules/ui-design.md`
- [ ] Ephemeral-run plans carry NO `workspace:` tag (unit-asserted); legacy plans unaffected
- [ ] `git diff --stat` shows surgical diffs (no CRLF whole-file noise)
- [ ] docs/_base/API_CONTRACTS.md updated additively
- [ ] Commits formatted `feat(api)/feat(ui)/test(api)/docs(api): ... (#392)`, no AI trailer; PR into dev

---

## Anti-Patterns to Avoid

- ❌ Don't widen step signatures to pass the request — workspace_name travels on DemoContext.
- ❌ Don't touch scenarios production code — routes/service/schemas already do everything.
- ❌ Don't tag the agent-HITL plan — SaveScenarioRequest has no tags field; cross-slice threading is a future epic.
- ❌ Don't drop the legacy `showcase`/`price`/`holiday` tags — append, never replace.
- ❌ Don't ship a migration — `scenario_plan.tags` + GIN index exist since PRP-27.
- ❌ Don't refactor planner.tsx to URL-as-source-of-truth — read once, mirror on change.
- ❌ Don't run `shadcn add` — Badge is installed.
- ❌ Don't chase pre-existing `tsc -b` errors — lint + vitest are the JS gates.

## Confidence Score

**9/10** for one-pass implementation success. The backend delta is a pure
helper + two literal replacements + one context field, with the exact existing
test assertions that must change already located (test_pipeline.py:1133 etc.);
the server-side filter and the frontend hook are fully built and verified, so
the UI work is pure wiring with installed components. The −1: planner.tsx is a
large untested page, so the chip/badge wiring is verified only by lint +
browser dogfood — a styling or state-sync slip there costs one iteration, not
a redesign.
