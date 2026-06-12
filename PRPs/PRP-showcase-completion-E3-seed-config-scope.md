name: "PRP — Showcase Completion E3: Advanced Seed Config MVP + Store/Product Scope Selection (issue #409)"
description: |

## Purpose

Implement Parallel epic E3 of the showcase-completion initiative (umbrella #406):
an additive, allow-listed nested override schema on the seeder HTTP contract
(7 curated knobs), an additive `seed_overrides` field on `DemoRunRequest` / the
WS start frame, a store/product focus-pair selector with pre-run preview on the
Showcase page, frontend + backend validation of every knob, and persistence of
overrides + user-selected scope into the workspace row (E1 #407 story slots) so
replay honors them verbatim.

**Execution gate:** this epic is Parallel after Foundation — implementation
starts ONLY after E1 #407 merges to `dev` (its migration ships the
`seed_overrides` / `user_scope` JSONB story slots E3 writes into). Every
dependency on E1's surface is tagged `CONTRACT(E1):` below; re-verify each tag
against the merged E1 code before starting Task 1.

## Core Principles

1. **Context is King**: every file reference below was verified against the live code on 2026-06-12 (branch dev @ bdf85f6, post-E4/#404 merge — PRE-E1-#407; line numbers will drift slightly after E1 merges, re-anchor by symbol name).
2. **Validation Loops**: each level is executable as written.
3. **Information Dense**: patterns cite exact file:line (or symbol when post-E1 drift is likely).
4. **Progressive Success**: shared override schema → seeder contract → demo start frame → pipeline consumption → workspace persistence → frontend → docs → browser dogfood.
5. **Global rules**: follow CLAUDE.md / AGENTS.md; all five backend CI gates must pass; UI work follows `.claude/rules/ui-design.md` + `.claude/rules/shadcn-ui.md`.

---

## Goal

A user on `/showcase` ticking **Re-seed first** can open an **Advanced seed
config** panel and turn 7 curated knobs (store count, product count, window
days, sparsity, promotion intensity, stockout intensity, noise sigma) before
running; independently, the user can pick an explicit **store/product focus
pair** (with a pre-run preview of the selected entities and the seeded window)
that the pipeline models instead of the auto-discovered first pair. Both the
overrides and the scope persist into a kept workspace row and are re-submitted
verbatim on Replay. A start frame without the new fields behaves
byte-identically to today.

**Deliverable** (all additive; ZERO migrations — E1 #407 owns the schema):

- `app/shared/seeder/overrides.py` — NEW: `SeederOverrides` Pydantic model (the single shared allow-list, `extra="forbid"`), importable by both the seeder and demo slices through `app/shared/` (vertical-slice-legal).
- `app/features/seeder/schemas.py` — `GenerateParams.overrides: SeederOverrides | None = None` (additive nested optional object on the EXISTING endpoint — decision rationale below).
- `app/features/seeder/service.py` — `_apply_seed_overrides(config, overrides)` applied LAST in `_build_config_from_params` (wins over the legacy scalar `stores`/`products`/`sparsity`), mapping each knob onto its `SeederConfig` sub-dataclass via `dataclasses.replace`.
- `app/features/demo/schemas.py` — `DemoRunRequest.seed_overrides: SeederOverrides | None` + `DemoRunRequest.user_scope: UserScope | None` (NEW small model) + two cross-field validators.
- `app/features/demo/pipeline.py` — `DemoContext` carries both; `step_seed` forwards `overrides` to `POST /seeder/generate`; `step_status` honors `user_scope` (validate via `/dimensions/*/{id}`; warn + fallback to discovery on a dangling pair).
- `app/features/demo/workspace.py` — `create_workspace` writes the two E1 story slots; list/detail response schemas expose them (replay reads list rows).
- `frontend/src` — `SeedConfigPanel.tsx` + `ScopeSelector.tsx` (composed from installed shadcn primitives), `lib/workspace-replay.ts` pure replay-frame builder, `types/api.ts` additions, `showcase.tsx` wiring.
- Tests: seeder schema/route/service tests (incl. out-of-bounds 422 + unknown-knob 422), demo schema JSON-path tests, pipeline `_RecordingClient` forwarding tests, workspace slot persistence tests, replay-verbatim regression (backend integration + frontend pure-helper test), component vitests.
- Docs: `docs/_base/API_CONTRACTS.md` (3 rows), `docs/_base/RUNBOOKS.md` (new incident entry + workspace-section update), `docs/_base/DOMAIN_MODEL.md` (slot schema documentation).

**Success definition**: all Success Criteria check off, the five backend gates +
frontend lint/test are green, and a real-browser dogfood shows: an
overridden re-seed run (e.g. 8 stores × 20 products, promo 0.3) goes green with
the seed card echoing the overrides; a scope-selected run models the chosen
pair; a kept run replays both verbatim.

## Why

- Umbrella #406: today the showcase accepts only `seed`/`scenario`/`reset`/`skip_seed`; the preset's behavioral character (noise, promos, stockouts, sparsity) is take-it-or-leave-it, and the modeled grain is always the first discovered `(store, product)` pair (`app/features/demo/pipeline.py:582-631`) — the operator cannot tell the story of a specific SKU.
- The seeder HTTP contract already accepts 25+ FLAT scalar/flag fields (`app/features/seeder/schemas.py:78-298`) — the umbrella's top risk is that surface growing unbounded. A curated nested object with `extra="forbid"` is the documented mitigation: 7 knobs, mechanically allow-listed, everything else stays preset-driven.
- E1 #407 reserves `seed_overrides` + `user_scope` JSONB story slots on `showcase_workspace` precisely so this epic's config survives into Replay — without persistence, replay of an overridden run would silently regenerate different data.
- E3 is Parallel after Foundation: it can land independently of E2 #408 / E4 #410 / E5 #411 / E6 #412 (no shared files beyond additive edits to `showcase.tsx` / `workspace.py` — coordinate merge order if simultaneous).

## What

### Open question resolved — seeder override contract shape

**DECISION: expand `GenerateParams` with an additive nested optional object
(`overrides: SeederOverrides | None = None`). NO new endpoint.** Rationale,
researched against the current code:

1. **The layering already exists.** `_build_config_from_params` (`app/features/seeder/service.py:202-247`) is a layered override pipeline: preset → scalar dims/window/sparsity → `_apply_phase1_overrides` (:74-137) → `_apply_phase2_overrides` (:139-199). A `_apply_seed_overrides` applied last is a fourth layer in an established pattern — a new endpoint would have to reimplement or call into this exact function anyway.
2. **A new endpoint duplicates load-bearing guards.** `POST /seeder/generate` carries `_check_seeder_enabled()` (production guard, `routes.py:21-33`), the ValueError→400 / Exception→500 RFC 7807 envelope (`routes.py:114-136`), and the seeder-is-the-only-bulk-mutation-path invariant. A second generate-shaped endpoint doubles that audit surface for zero contract benefit.
3. **Back-compat is free.** Absent field = `None` = byte-identical behavior — the exact precedent the Phase 1/Phase 2 field comments in `schemas.py:121-123,175-177` already promise and test.
4. **Nested (not more flat scalars) is the allow-list mechanism.** `ConfigDict(extra="forbid")` on the nested model makes an unknown knob a 422 — the umbrella's "contract grows unbounded" mitigation becomes machine-enforced, and the 7 curated knobs stay visually distinct from the 25+ legacy scalars.
5. **One schema serves both slices.** The demo start frame forwards the same object verbatim; placing `SeederOverrides` in `app/shared/seeder/overrides.py` lets `app/features/seeder/schemas.py` and `app/features/demo/schemas.py` both import it without a cross-slice import (precedent: `demo/schemas.py:16` already imports `ScenarioPreset` from `app/shared/seeder/config`).

Trade-off accepted: `extra="forbid"` means a FUTURE knob sent by a newer client
to an older backend errors loudly instead of being ignored. That asymmetry vs.
the top-level start frame (unknown TOP-LEVEL keys remain ignored) is
deliberate — silent knob-dropping would fake-honor a config the run never used.

### Allow-listed knob → config-field mapping (the complete MVP surface)

| Knob (wire name) | Type / bounds | Maps to (via `dataclasses.replace`) | Preset reference values |
|---|---|---|---|
| `stores` | `int`, ge=1 le=100 | `config.dimensions.stores` (`DimensionConfig.stores`, `app/shared/seeder/config.py:118`) | demo profiles 3–5; scalar `GenerateParams.stores` caps 100 |
| `products` | `int`, ge=1 le=500 | `config.dimensions.products` (`DimensionConfig.products`, config.py:119) | demo profiles 10–25; scalar caps 500 |
| `window_days` | `int`, ge=75 le=365 | `config.start_date = config.end_date - timedelta(days=window_days)` (end_date untouched) | ≥75 keeps the `historical_backfill` gate clear (`pipeline.py` gate = `3*(14+1)+30 = 75`); ≤365 = `DEFAULT_SEED_SPAN_DAYS` |
| `sparsity` | `float`, ge=0.0 le=0.9 | `config.sparsity = replace(config.sparsity, missing_combinations_pct=v)` (`SparsityConfig.missing_combinations_pct`, config.py:141) — `replace` PRESERVES the preset's `random_gaps_*` fields | sparse preset uses 0.5; 1.0 would seed zero series (hard-fail), hence the 0.9 cap |
| `promotion_intensity` | `float`, ge=0.0 le=0.5 | `config.retail = replace(config.retail, promotion_probability=v)` (`RetailPatternConfig.promotion_probability`, config.py:101) | preset max 0.25 (holiday_rush); 0.5 cap = 2× headroom |
| `stockout_intensity` | `float`, ge=0.0 le=0.5 | `config.retail = replace(config.retail, stockout_probability=v)` (config.py:102) | preset max 0.25 (stockout_heavy); higher values risk NaN-WAPE (documented expected-fail, mirrors sparse) |
| `noise_sigma` | `float`, ge=0.0 le=0.5 | `config.time_series = replace(config.time_series, noise_sigma=v)` (`TimeSeriesConfig.noise_sigma`, config.py:72) | preset max 0.4 (high_variance) |

Precedence (document in the field description AND a service test): nested
`overrides` is applied LAST in `_build_config_from_params` and therefore WINS
over the legacy scalar `stores` / `products` / `sparsity` when both are sent.
`window_days` recomputes `start_date` from the (scalar-or-default) `end_date`.
The pipeline keeps sending `sparsity=0.0` as the scalar (preserves preset
character per the `if params.sparsity > 0` guard at `service.py:225-226`);
`overrides.sparsity` is the only way the demo overrides sparsity.

### `seed_overrides` / `user_scope` slot schemas (THIS PRP's contract to define)

E1 #407 reserves the slots; the JSON inside them is defined HERE:

```jsonc
// showcase_workspace.seed_overrides  (JSONB; NULL when the run had none)
// = SeederOverrides.model_dump(mode="json", exclude_none=True) — SPARSE:
//   only operator-set knobs appear; {} never stored (None instead).
{
  "stores": 8,                  // int 1..100, optional
  "products": 20,               // int 1..500, optional
  "window_days": 120,           // int 75..365, optional
  "sparsity": 0.3,              // float 0.0..0.9, optional
  "promotion_intensity": 0.3,   // float 0.0..0.5, optional
  "stockout_intensity": 0.1,    // float 0.0..0.5, optional
  "noise_sigma": 0.25           // float 0.0..0.5, optional
}

// showcase_workspace.user_scope  (JSONB; NULL when no pair was picked)
// = UserScope.model_dump(mode="json") — both keys always present when non-null:
{
  "store_id": 12,               // int ge=1 — REAL discovered id (sequences
  "product_id": 47              // int ge=1    never reset; ids are NOT 1-based)
}
```

Replay semantics: the slots record the REQUESTED config (replay-verbatim
contract, mirrors the E1 seed/scenario/reset/skip_seed columns). The EFFECTIVE
grain a run actually modeled is already recorded separately by
`finalize_workspace` into the `store_id` / `product_id` columns
(`workspace.py:136-137`) — when a replayed `user_scope` dangles (warn+fallback,
below), the two will legitimately differ; that divergence is visible, not
hidden.

### User-visible behavior

- **Advanced seed config panel** (`/showcase`): a collapsible "Advanced seed config" section appears under the run controls, enabled ONLY while **Re-seed first** is ticked (overrides are meaningless on `skip_seed=true` and the backend rejects the combination). 7 controls with the bounds above; a "live summary" line echoes the effective config (e.g. "8 stores × 20 products × 120 days · promo 0.30"); a caveat notes high sparsity/stockout values can legitimately fail the backtest (NaN WAPE — same documented semantics as the `sparse` preset). `window_days` control is disabled with an explanatory tooltip when the `holiday_rush` preset is selected (calendar-pinned window).
- **Store/product focus-pair selector**: two dropdowns (stores, products — fed by `GET /dimensions/stores` / `GET /dimensions/products`, `page_size=100`) plus a pre-run preview card showing the chosen store (code/name/region/type), product (sku/name/category/brand) and the currently seeded window (from `GET /seeder/status`). Works WITHOUT re-seeding (scope selection on the existing dataset is the primary use). Ticking **Reset database** clears the selection with a caveat ("a wipe re-issues ids — re-pick after the run"), because Postgres sequences never reset (memory anchor: seeder-does-not-reset-id-sequences).
- **Run**: the start frame carries `seed_overrides` (only when re-seeding and ≥1 knob set) and `user_scope` (when a pair is picked). The seed step card echoes the overridden dims; the status step card says "user-selected pair" vs "discovered pair".
- **Replay** of a kept run re-submits recorded `seed_overrides` + `user_scope` verbatim alongside the existing 4 config fields. Load repopulates the panel + selector.
- **Legacy behavior**: a start frame without the new fields is byte-identical to today (contract test).

### Technical requirements

- All new request fields are additive `Optional` with `None` defaults; the WS start frame keeps ignoring unknown TOP-LEVEL keys (`DemoRunRequest` default `extra=ignore`); the nested models use `extra="forbid"` (allow-list enforcement).
- `SeederOverrides` and `UserScope` carry `ConfigDict(strict=True, extra="forbid")`. All fields are JSON-native (`int`/`float`) → NO `Field(strict=False)` override needed and the strict-mode AST policy test (`app/core/tests/test_strict_mode_policy.py`) stays green. Runtime-verified on pydantic 2.12.5: a nested-model field under a `strict=True` parent validates from the JSON-parsed dict (FastAPI's `validate_python` path) — see verification log.
- All config is start-frame-time. NOTHING is configurable mid-run — the pipeline is strictly linear under the module-level `asyncio.Lock` (design invariant from umbrella #406; do not add any mid-run mutation channel).
- The demo slice must not import `app/features/seeder/*` — `SeederOverrides` lives in `app/shared/seeder/overrides.py`; `UserScope` lives in `app/features/demo/schemas.py` (demo-only concept). `pipeline.py` may import both (`app.shared.*` + own-slice schemas are already imported at `pipeline.py:43-45`).
- The seeder stays the only bulk-mutation path; no new wipe semantics; `_check_seeder_enabled` untouched.
- E3 ships ZERO Alembic migrations. CONTRACT(E1): the `seed_overrides` + `user_scope` JSONB slots exist on `showcase_workspace` (E1 #407 migration) before this epic executes.

### Success Criteria

- [ ] `POST /seeder/generate` accepts `{"overrides": {"stores": 8, "promotion_intensity": 0.3}}` → 201, and the generated config reflects the knobs (service unit test); `{"overrides": {"stores": 0}}` → 422; `{"overrides": {"bogus_knob": 1}}` → 422; a body WITHOUT `overrides` produces a byte-identical `SeederConfig` to today (regression test).
- [ ] `DemoRunRequest.model_validate({...})` JSON-path tests: `seed_overrides` with `skip_seed=true` → ValidationError; `window_days` with `scenario="holiday_rush"` → ValidationError; legacy 4-field frame still validates; `user_scope` happy path.
- [ ] `step_seed` forwards `overrides` in the `/seeder/generate` POST body (`_RecordingClient` assertion); `step_status` uses a valid `user_scope` pair (asserts the GET-by-id calls + ctx fields), and WARNS + falls back to discovery on a 404 pair.
- [ ] A `preservation="keep"` run records `seed_overrides` + `user_scope` into the E1 story slots; `GET /demo/workspaces` list items AND `/{id}` detail expose both; the e2e replay regression (`tests/test_e2e_demo.py::test_demo_replay_same_config_twice` extended or sibling test) proves a replayed row carries identical slot JSON.
- [ ] Frontend: panel renders 7 bounded controls only when Re-seed is ticked; selector previews the chosen pair; `workspaceToRunRequest(ws)` unit test proves replay-verbatim including the new fields; `pnpm lint && pnpm test --run` green; no NEW `tsc -b` errors in touched files.
- [ ] Legacy start frames byte-identical (backend contract test + existing demo tests untouched-green).
- [ ] Backend gates green: `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"`.
- [ ] Docs updated additively: API_CONTRACTS (seeder + demo + WS rows), RUNBOOKS (new showcase incident entry + workspace-section note), DOMAIN_MODEL (slot schemas under the `showcase_workspace` aggregate).
- [ ] Real-browser dogfood (Level 4) performed.

## All Needed Context

### Documentation & References

```yaml
# MUST READ — codebase patterns (verified 2026-06-12, dev @ bdf85f6 — PRE-E1;
# re-anchor line numbers by symbol after E1 #407 merges)

- file: app/features/seeder/schemas.py
  why: |
    GenerateParams at 78-298 — the contract to extend. Note the Phase 1
    comment block at 121-123 ("All flags default off so existing scenarios
    remain byte-identical") — copy that promise onto the new field. The model
    is plain BaseModel (NO ConfigDict(strict=True)) — do NOT add strict mode
    to GenerateParams itself (it has date fields start_date/end_date; only
    the NEW nested SeederOverrides model is strict).
    ChangepointEventParam at 51-64 is the existing nested-model-in-params
    precedent (list[ChangepointEventParam] at 153-156).

- file: app/features/seeder/service.py
  why: |
    _build_config_from_params at 202-247 — THE integration point. Scalar
    overrides at 218-226 (dataclasses.replace on dimensions; sparsity only
    when > 0); _apply_phase1_overrides at 74-137 and _apply_phase2_overrides
    at 139-199 are the mutate-config-in-place pattern to mirror for
    _apply_seed_overrides. APPLY THE NEW LAYER LAST (after :241) so nested
    wins over scalars. from dataclasses import replace already imported (:7).

- file: app/shared/seeder/config.py
  why: |
    The override targets: TimeSeriesConfig.noise_sigma :72,
    RetailPatternConfig.promotion_probability/stockout_probability :101-102,
    DimensionConfig.stores/products :118-119,
    SparsityConfig.missing_combinations_pct :141 (+ random_gaps fields to
    PRESERVE via replace). ScenarioPreset :37-47. holiday_rush pinned window
    :553-579 (the reason window_days is rejected for that preset).
    DEFAULT_SEED_SPAN_DAYS=365 :10. NO Pydantic here — config.py stays
    dataclasses; the new Pydantic model goes in a NEW sibling module
    app/shared/seeder/overrides.py.

- file: app/features/seeder/routes.py
  why: |
    POST /seeder/generate at 85-136 — NO route-code change needed (the body
    model change flows through); read for the _check_seeder_enabled guard
    (21-33) and the error envelope you must NOT duplicate (the
    no-new-endpoint rationale).

- file: app/features/demo/schemas.py
  why: |
    DemoRunRequest at 29-85 — the model to extend. The model_validator
    _workspace_name_requires_keep at 80-85 is the EXACT cross-field-rule
    pattern for the two new validators. The docstring at 30-38 explains the
    strict-mode policy; scenario's strict=False override at 59-63 (enum) —
    nested BaseModel fields need NO such override (runtime-verified).
    WorkspaceListItem at 169-190 / WorkspaceDetailResponse at 192-203 — add
    seed_overrides + user_scope to BOTH (replay reads LIST rows:
    showcase.tsx:174-186). CONTRACT(E1): E1's PRP may already have surfaced
    the story slots on these response models — if so, verify shape
    (dict[str, Any] | None) and skip the duplicate edit.

- file: app/features/demo/pipeline.py
  why: |
    DemoContext at 212-263 — add seed_overrides/user_scope fields (follow the
    PRP-38/39/40 additive-Optional comment style). step_seed at 541-579 —
    extend the POST body; _SCENARIO_SEED_PROFILE at 513-538 supplies the
    defaults overrides partially replace. step_status at 582-631 — the
    first-pair discovery to branch around for user_scope (its docstring
    already states ids are NOT 1-based). run_pipeline ctx construction at
    2646-2651 — thread the two new req fields. StepStatus literal includes
    "warn" (schemas.py:19) and only "fail" stops the run (:2729-2738) — the
    warn+fallback path is safe. CRITICAL header rule :18-19: pipeline must
    NOT import app.features.* outside its own slice — app.shared.* is fine.

- file: app/features/demo/workspace.py
  why: |
    create_workspace at 46-79 — add the two slot writes on the
    ShowcaseWorkspace(...) constructor; warn-and-continue contract at 10-13
    (a slot-write failure must never break the run — the try/except already
    guarantees it). finalize_workspace at 106-155 — NO change for the slots
    (recorded at create); note store_id/product_id columns at 136-137 record
    the EFFECTIVE grain (divergence-visible design).
    CONTRACT(E1): E1 refactors create_workspace to write its new columns —
    rebase this edit onto E1's merged version.

- file: app/features/demo/models.py
  why: |
    ShowcaseWorkspace ORM — E3 does NOT edit this file. CONTRACT(E1): after
    E1 merges it carries seed_overrides/user_scope as JSONB story slots;
    verify the exact attribute names/types there before writing
    workspace.py code. (Assumed shape: nullable JSONB columns mirroring the
    created_objects precedent at 77-79.)

- file: app/features/demo/tests/test_pipeline.py
  why: |
    _RecordingClient at 1025-1068 (records (method, path, json_body) per
    call, canned responses keyed by (method, path-prefix)); _as_client cast
    at 1070+. Reuse for: overrides-forwarding, user_scope GET-by-id calls,
    warn+fallback (404 canned response).

- file: app/features/demo/tests/test_schemas.py
  why: |
    The JSON-path test conventions: test_demo_run_request_json_path_keep_
    with_name :67, test_demo_run_request_legacy_frame_still_validates :75,
    test_demo_run_request_workspace_name_requires_keep :83 — mirror all
    three shapes for the new fields.

- file: app/features/seeder/tests/test_routes.py
  why: |
    Route-test harness: client fixture :15 (TestClient + mocked settings,
    seeder_allow_production=True), TestGenerate :96 — add overrides 201 /
    422-bounds / 422-unknown-knob cases here. test_generate_validation_error
    :157 is the 422 pattern.

- file: app/features/seeder/tests/test_service.py
  why: |
    Service-test patterns for _build_config_from_params — add: knob→field
    mapping, precedence-over-scalars, window_days math, preset-character
    preservation (e.g. sparse preset's random_gaps survive an overrides.
    sparsity replace), and the no-overrides byte-identical regression.

- file: tests/test_e2e_demo.py
  why: |
    test_demo_replay_same_config_twice at 561-609 — the replay-regression
    guard to extend (or sibling): a keep-run with seed_overrides+user_scope,
    replayed, must produce a second row with identical slot JSON.

- file: frontend/src/pages/showcase.tsx
  why: |
    Wiring surface. handleRun start frame at 139-156 (conditional-spread
    pattern for optional fields — reuse for seed_overrides/user_scope);
    handleLoadWorkspace at 160-168 (repopulate panel+selector);
    handleReplayWorkspace at 174-186 (REPLACE its inline object with the new
    workspaceToRunRequest helper); controls block at 269-363 (panel +
    selector land after the existing checkboxes); reset checkbox at 301-311
    (hook the scope-clearing caveat here).

- file: frontend/src/types/api.ts
  why: |
    DemoRunRequest at 778-788 (+ seed_overrides?/user_scope?);
    WorkspaceListItem at 806-816 and WorkspaceDetail at 819-825 (+ both
    fields, `| null`); add SeedOverrides + UserScope interfaces near the
    demo block. WARNING: MIXED CRLF/LF line endings — surgical edits only;
    verify `git diff --stat` stays small.

- file: frontend/src/hooks/use-stores.ts
  why: |
    useStores at 16-43 (TanStack Query over /dimensions/stores with
    page/page_size/enabled) — the selector's data source; use-products.ts
    mirrors it (useProducts :16, useProduct :45). page_size hard cap is 100
    (app/features/dimensions/routes.py:62,187).

- file: frontend/src/hooks/use-seeder.ts
  why: useSeederStatus :15 — the seeded-window source for the preview card.

- file: frontend/src/hooks/use-demo-pipeline.ts
  why: |
    start(req) at 241-249 sends the req object as the WS start frame
    verbatim — generic over the widened DemoRunRequest; NO change needed
    (read to confirm). RunHistoryStrip replays stored req objects, so
    localStorage replays inherit the new fields for free.

- file: frontend/src/components/demo/ScenarioPicker.test.tsx
  why: |
    The vitest + @testing-library/react + afterEach(cleanup) harness pattern
    for the two new component test files.

- file: frontend/src/components/ui/
  why: |
    Installed primitives: collapsible.tsx, select.tsx, slider.tsx, input.tsx,
    badge.tsx, card.tsx, tooltip.tsx, checkbox.tsx — the panel + selector
    compose from these; NO new shadcn install required. If one becomes
    necessary anyway: pin `pnpm dlx shadcn@4.7.0 add ...` (5.x writes a stub
    pnpm-workspace.yaml and skips the component) and use per-component
    @radix-ui/react-X imports, never the radix barrel.

- file: docs/_base/RUNBOOKS.md
  why: |
    "Showcase page (/showcase) pipeline fails at step X" — numbered entries
    end at 28; append entry 29 (overrides/scope incident matrix) in the same
    bold-trigger/Cause/Fix format. The "Showcase workspace —
    preserve/restore/replay/delete semantics" section's "Explicitly out of
    scope" list says advanced seed configuration is NOT implemented — E3
    DELIVERS it: rewrite that bullet (move seed_overrides/user_scope to the
    documented surface; phase-level config stays out of scope).

- file: docs/_base/API_CONTRACTS.md
  why: |
    Rows to extend additively: the /seeder/* row (mention the overrides
    object on POST /seeder/generate), POST /demo/run, and the WS
    /demo/stream start-frame bullet (E1/E2 notes were just added — append an
    "E3 (#409)" note, don't disturb them).

- file: docs/_base/DOMAIN_MODEL.md
  why: |
    showcase_workspace aggregate section — document the seed_overrides /
    user_scope slot JSON schemas (the umbrella's "JSONB story slots become a
    junk drawer" mitigation requires documented slot schemas here).

- file: PRPs/PRP-showcase-workspace-E2-preset-exposure.md
  why: |
    Closest predecessor (preset exposure + seed profiles) — its gotcha block
    (holiday_rush pinning, seeder precedence, sparse NaN-WAPE, frontend tsc
    gate) all recur in E3; this PRP inherits and extends them.

# Issue / initiative context
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/409
  why: The epic this PRP implements (Parallel after Foundation E1 #407).
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/406
  why: |
    Umbrella — Approach ("all configuration is start-frame-time", "no new
    router outside existing slices"), Risks table row 1 (the allow-list
    mitigation this PRP implements), out-of-scope list (NO mid-run controls,
    NO embedded scenario-builder).
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/407
  why: |
    Foundation epic whose contract is GIVEN: JSONB story slots incl.
    seed_overrides + user_scope; columns replayed_from_workspace_id /
    archived / pinned / notes / tags / config_schema_version; PATCH
    /demo/workspaces/{id}. E3 builds on, never re-decides, this surface.

# External references
- url: https://docs.pydantic.dev/latest/concepts/strict_mode/
  why: |
    Strict-mode semantics for nested models: a model-typed field validates
    dict input using the NESTED model's own config — confirmed empirically
    (verification log) so no doc-faith is required. NOTE: the docs site
    301-redirects and anchors have drifted; the runtime verification in the
    Known Gotchas log is the authoritative claim, not this URL.
- url: https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.extra
  why: extra="forbid" → unknown nested keys raise ValidationError (the 422 allow-list mechanism).
```

### Current Codebase tree (relevant subset, pre-E1)

```bash
app/shared/seeder/
├── config.py                 # dataclasses; override TARGETS (no Pydantic here)
├── core.py / generators/     # consume SeederConfig — untouched by E3
app/features/seeder/
├── schemas.py                # GenerateParams @78 (25+ flat fields)
├── service.py                # _build_config_from_params @202; _apply_phaseN @74/@139
├── routes.py                 # POST /generate @85 (guard @21; no route change)
└── tests/                    # test_routes.py, test_service.py, test_schemas.py
app/features/demo/
├── schemas.py                # DemoRunRequest @29; Workspace* responses @169
├── pipeline.py               # DemoContext @212; step_seed @541; step_status @582; run_pipeline @2618
├── workspace.py              # create_workspace @46; finalize_workspace @106
├── models.py                 # ShowcaseWorkspace (E1 adds the story slots — not edited here)
└── tests/                    # test_pipeline.py (_RecordingClient @1025), test_schemas.py, test_workspace.py
tests/test_e2e_demo.py        # replay regression @561
frontend/src/
├── pages/showcase.tsx        # handleRun @139; handleLoad @160; handleReplay @174; controls @269
├── types/api.ts              # DemoRunRequest @778; WorkspaceListItem @806 (MIXED CRLF/LF)
├── hooks/use-stores.ts, use-products.ts, use-seeder.ts, use-demo-pipeline.ts
└── components/demo/          # ScenarioPicker, WorkspacePanel, ... (+ index.ts barrel)
```

### Desired Codebase tree (files added/modified)

```bash
app/shared/seeder/overrides.py            # NEW — SeederOverrides (strict, extra=forbid, 7 knobs)
app/shared/seeder/tests/test_overrides.py # NEW — bounds, forbid, JSON-path, sparse-dump tests
app/features/seeder/schemas.py            # MOD — GenerateParams.overrides: SeederOverrides | None
app/features/seeder/service.py            # MOD — _apply_seed_overrides, wired LAST in _build_config_from_params
app/features/seeder/tests/test_service.py # MOD — mapping/precedence/window/byte-identical tests
app/features/seeder/tests/test_routes.py  # MOD — 201-with-overrides, 422-bounds, 422-unknown-knob
app/features/demo/schemas.py              # MOD — UserScope; DemoRunRequest fields + validators; Workspace* responses
app/features/demo/pipeline.py             # MOD — DemoContext fields; step_seed forward; step_status scope branch
app/features/demo/workspace.py            # MOD — create_workspace writes both slots
app/features/demo/tests/test_schemas.py   # MOD — JSON-path + validator tests
app/features/demo/tests/test_pipeline.py  # MOD — forwarding + scope + warn/fallback tests
app/features/demo/tests/test_workspace.py # MOD — slot persistence tests
tests/test_e2e_demo.py                    # MOD — replay-verbatim regression incl. slots (integration)
frontend/src/types/api.ts                 # MOD — SeedOverrides, UserScope, DemoRunRequest, Workspace* (surgical)
frontend/src/lib/workspace-replay.ts      # NEW — workspaceToRunRequest(ws) pure helper
frontend/src/lib/workspace-replay.test.ts # NEW — replay-verbatim FE regression
frontend/src/components/demo/SeedConfigPanel.tsx        # NEW — collapsible 7-knob panel
frontend/src/components/demo/SeedConfigPanel.test.tsx   # NEW
frontend/src/components/demo/ScopeSelector.tsx          # NEW — pair selector + preview card
frontend/src/components/demo/ScopeSelector.test.tsx     # NEW
frontend/src/components/demo/index.ts     # MOD — export the two new components (match barrel style)
frontend/src/pages/showcase.tsx           # MOD — wiring (state, panel, selector, start frames)
docs/_base/API_CONTRACTS.md               # MOD — seeder overrides + /demo/run + WS start-frame E3 notes
docs/_base/RUNBOOKS.md                    # MOD — showcase incident 29 + workspace-section scope update
docs/_base/DOMAIN_MODEL.md                # MOD — slot schemas on the showcase_workspace aggregate
```

### Known Gotchas & Library Quirks

```python
# CRITICAL — EXECUTION ORDER: do not start until E1 #407 is merged to dev.
#   E3 writes JSONB slots that E1's migration creates. First action of Task 1:
#   re-read app/features/demo/models.py + workspace.py on the post-E1 dev and
#   re-anchor every CONTRACT(E1) tag in this PRP.

# CRITICAL — pydantic strict + nested models (runtime-verified 2026-06-12 on
#   pydantic 2.12.5; re-run on lib upgrade):
#   uv run python -c "
#   from pydantic import BaseModel, ConfigDict, Field
#   class N(BaseModel):
#       model_config = ConfigDict(strict=True, extra='forbid')
#       stores: int | None = Field(default=None, ge=1, le=100)
#   class P(BaseModel):
#       model_config = ConfigDict(strict=True)
#       seed_overrides: N | None = None
#   print(P.model_validate({'seed_overrides': {'stores': 5}}))          # OK — dict→model under strict
#   P.model_validate({'seed_overrides': {'stores': 999}})               # ValidationError (bounds)
#   "
#   and N.model_validate({'stores': 5, 'bogus': 1}) → ValidationError (forbid).
#   Conclusions baked into the design: NO Field(strict=False) needed on the
#   nested field; extra='forbid' IS the allow-list; FastAPI's validate_python
#   path (the JSON dict) works. All knobs are int/float → the strict-mode AST
#   policy test (app/core/tests/test_strict_mode_policy.py) does not fire.

# CRITICAL — do NOT add ConfigDict(strict=True) to GenerateParams itself: it
#   has date fields (start_date/end_date) and is deliberately non-strict today.
#   Only the NEW nested models are strict.

# CRITICAL — seeder override precedence (service.py:213-226 + the new layer):
#   preset → scalar stores/products/window/sparsity → phase1 → phase2 →
#   overrides (LAST, wins). Use dataclasses.replace for every sub-config so
#   preset-customized sibling fields survive (e.g. sparse preset's
#   random_gaps_per_series when overrides.sparsity is set; scenario-customized
#   region/category lists when overrides.stores is set — same reason the
#   existing scalar override at :218-222 uses replace).

# CRITICAL — holiday_rush is CALENDAR-PINNED (config.py:553-579): its
#   HolidayConfig spikes are fixed 2024 dates. seed_overrides.window_days on
#   scenario='holiday_rush' must be REJECTED at DemoRunRequest validation
#   (clear ValueError message), not silently ignored — a shifted window
#   silently drops every holiday spike. Direct /seeder/generate callers who
#   combine them are out of scope (the preset docstring already documents
#   explicit-dates-to-shift).

# CRITICAL — seed_overrides requires skip_seed=False. The seed step is skipped
#   on skip_seed=true (pipeline.py:543-544) so overrides would be a silent
#   no-op; reject in a model_validator (mirror _workspace_name_requires_keep,
#   schemas.py:80-85). The frontend enforces the same by gating the panel on
#   the Re-seed checkbox.

# CRITICAL — ids are NOT 1-based (step_status docstring, pipeline.py:585-587;
#   memory anchor seeder-does-not-reset-id-sequences). The scope selector MUST
#   be fed from live /dimensions data, never synthesized ids. user_scope can
#   dangle after reset+reseed → step_status WARN + fallback to discovery (the
#   replay path of a reset=true workspace would otherwise hard-fail forever).
#   "warn" does NOT stop the run (only "fail" does — pipeline.py:2729-2738).

# CRITICAL — high stockout_intensity / sparsity overrides can legitimately
#   FAIL the backtest (all-NaN WAPE → step_backtest FAIL by design; same
#   semantics as the sparse preset, RUNBOOKS incident 28). Do NOT add a
#   graceful-skip; ship the panel caveat + runbook entry 29 instead.

# CRITICAL — workspace writes stay warn-and-continue (workspace.py:10-13).
#   The slot writes go INSIDE the existing try/except in create_workspace; a
#   failure yields workspace_id=None and a green run, never an exception.

# GOTCHA — replay reads WorkspaceListItem (the LIST row — showcase.tsx:174):
#   seed_overrides/user_scope must be on the LIST response, not detail-only.
#   CONTRACT(E1): if E1 already exposed the slots detail-only, ADD them to the
#   list item here (cheap; sparse JSONB).

# GOTCHA — frontend type gates: `pnpm tsc --noEmit` is vacuous (solution-style
#   tsconfig) and `pnpm tsc -b` fails with ~24 PRE-EXISTING errors on dev,
#   none in demo components. Gate on `pnpm lint && pnpm test --run` plus:
#   cd frontend && pnpm tsc -b 2>&1 | grep -E "SeedConfigPanel|ScopeSelector|workspace-replay|types/api|pages/showcase"  # expect empty

# GOTCHA — frontend/src/types/api.ts has MIXED CRLF/LF line endings; repo-wide
#   files are inconsistently CRLF/LF. Keep edits surgical; check
#   `git diff --stat` before committing (Edit/Write emit LF — avoid whole-file
#   noise diffs).

# GOTCHA — shadcn: compose from INSTALLED primitives (collapsible, select,
#   slider, input, badge, tooltip — frontend/src/components/ui/). Semantic
#   tokens only (text-muted-foreground, border-primary, text-destructive for
#   the reset caveat — mirrors showcase.tsx:309). Never raw colors.

# GOTCHA — mypy --strict AND pyright --strict gate every backend edit. The
#   DemoContext additions need full annotations (SeederOverrides | None);
#   pipeline.py imports them from app.shared.seeder.overrides (NOT from the
#   seeder feature slice — vertical-slice rule, pipeline.py:18-19).

# GOTCHA — step_seed currently derives the detail line from profile dims
#   (pipeline.py:577). With overrides, compute effective stores/products =
#   override-or-profile for BOTH the POST scalars and the detail string so
#   the card tells the truth; keep scalar sparsity=0.0 (preset-character
#   guard); the nested object carries the operator's sparsity.

# CONVENTION — commits (every one references #409; no AI trailer; scopes from
#   .claude/rules/commit-format.md — seeder slice ⊂ `data`, demo slice ⊂ `api`):
#   feat(data): add allow-listed nested seed overrides to seeder contract (#409)
#   feat(api): thread seed overrides and user scope through demo pipeline (#409)
#   feat(ui): add advanced seed config panel and scope selector to showcase (#409)
#   test(api): cover replay-verbatim seed overrides and scope slots (#409)
#   docs(docs): document seed override contract and workspace slots (#409)
#   docs(repo): track showcase completion e3 prp (#409)
#   Branch off dev: feat/showcase-completion-e3-seed-config-scope (49 chars ≤ 50).

# RUNTIME-VERIFICATION LOG (per prp-create step 3):
#   - pydantic 2.12.5 nested-strict + extra=forbid + bounds behavior verified
#     with the command in the CRITICAL block above (all four assertions pass).
#   - Seeder precedence semantics read directly from service.py:202-247 (not
#     inferred); the `if params.sparsity > 0` guard confirmed at :225-226.
#   - dimensions page_size cap 100 confirmed at app/features/dimensions/
#     routes.py:62 and :187.
#   - `pnpm tsc -b` pre-existing-failure state re-confirmed by the E2 PRP log
#     (2026-06-12); no demo-component errors.
#   - No other third-party API claims — everything else cites in-repo code.
```

## Implementation Blueprint

### Data models and structure

```python
# app/shared/seeder/overrides.py  (NEW)
"""Curated, allow-listed seed-override schema (E3, issue #409).

Shared between the seeder slice (GenerateParams.overrides) and the demo slice
(DemoRunRequest.seed_overrides) — app/shared is the sanctioned cross-slice
home (vertical-slice rule). extra='forbid' IS the allow-list: any knob not
listed here is a 422 at the HTTP boundary (umbrella #406 risk mitigation —
the full 25+ knob surface stays preset-driven).
"""
from pydantic import BaseModel, ConfigDict, Field

class SeederOverrides(BaseModel):
    # strict=True catches JSON-native coercion bugs ("5" → 5); every field is
    # int/float so no Field(strict=False) override is needed (security-patterns.md).
    model_config = ConfigDict(strict=True, extra="forbid")

    stores: int | None = Field(default=None, ge=1, le=100, description="Store count → DimensionConfig.stores; wins over the scalar `stores` param.")
    products: int | None = Field(default=None, ge=1, le=500, description="Product count → DimensionConfig.products; wins over the scalar `products` param.")
    window_days: int | None = Field(default=None, ge=75, le=365, description="Seeded window length; start_date = end_date - window_days. >=75 keeps the showcase historical_backfill gate clear. Rejected on the calendar-pinned holiday_rush preset (demo surface).")
    sparsity: float | None = Field(default=None, ge=0.0, le=0.9, description="Missing (store,product) grain fraction → SparsityConfig.missing_combinations_pct; preserves the preset's gap config. 1.0 disallowed (zero series).")
    promotion_intensity: float | None = Field(default=None, ge=0.0, le=0.5, description="→ RetailPatternConfig.promotion_probability (preset max 0.25).")
    stockout_intensity: float | None = Field(default=None, ge=0.0, le=0.5, description="→ RetailPatternConfig.stockout_probability. High values can legitimately NaN-WAPE-fail the backtest (documented).")
    noise_sigma: float | None = Field(default=None, ge=0.0, le=0.5, description="→ TimeSeriesConfig.noise_sigma (preset max 0.4).")

    def is_empty(self) -> bool:
        """True when no knob is set ({} on the wire) — treated as None everywhere."""
        return not self.model_dump(exclude_none=True)
```

```python
# app/features/demo/schemas.py — additions (demo-only concept stays in-slice)
class UserScope(BaseModel):
    """Operator-selected (store, product) focus pair (E3, issue #409).

    Ids are REAL discovered ids (sequences never reset — ids are not 1-based);
    step_status validates them and warn-falls-back to discovery when dangling.
    """
    model_config = ConfigDict(strict=True, extra="forbid")
    store_id: int = Field(..., ge=1)
    product_id: int = Field(..., ge=1)

# DemoRunRequest — two additive Optional fields + two validators:
#   seed_overrides: SeederOverrides | None = None   (import from app.shared.seeder.overrides)
#   user_scope: UserScope | None = None
#
# @model_validator(mode="after") _seed_overrides_require_reseed:
#   if self.seed_overrides is not None and not self.seed_overrides.is_empty()
#      and self.skip_seed:
#       raise ValueError("seed_overrides requires skip_seed=false (Re-seed first)")
#   # normalize: an empty overrides object collapses to None
#   if self.seed_overrides is not None and self.seed_overrides.is_empty():
#       self.seed_overrides = None      # NOTE: model_validator(after) may mutate self
#
# @model_validator(mode="after") _window_days_forbidden_on_holiday_rush:
#   if (self.seed_overrides is not None
#       and self.seed_overrides.window_days is not None
#       and self.scenario is ScenarioPreset.HOLIDAY_RUSH):
#       raise ValueError("window_days cannot override the calendar-pinned holiday_rush window")
#
# WorkspaceListItem (+ WorkspaceDetailResponse inherits):
#   seed_overrides: dict[str, Any] | None = Field(default=None, ...)
#   user_scope: dict[str, Any] | None = Field(default=None, ...)
#   (from_attributes=True already set — ORM JSONB maps straight through.
#    CONTRACT(E1): skip if E1's PRP already added them; ensure LIST exposure.)
```

```python
# app/features/seeder/service.py — the new layer (mirror _apply_phase2_overrides)
def _apply_seed_overrides(config: SeederConfig, overrides: SeederOverrides | None) -> None:
    """Apply the curated nested overrides LAST — wins over scalar params.

    dataclasses.replace is field-precise: preset-customized sibling fields
    (region/category lists, random_gaps_*) survive every knob.
    """
    if overrides is None:
        return
    if overrides.stores is not None or overrides.products is not None:
        config.dimensions = replace(
            config.dimensions,
            stores=overrides.stores if overrides.stores is not None else config.dimensions.stores,
            products=overrides.products if overrides.products is not None else config.dimensions.products,
        )
    if overrides.window_days is not None:
        config.start_date = config.end_date - timedelta(days=overrides.window_days)
    if overrides.sparsity is not None:
        config.sparsity = replace(config.sparsity, missing_combinations_pct=overrides.sparsity)
    if overrides.promotion_intensity is not None or overrides.stockout_intensity is not None:
        config.retail = replace(
            config.retail,
            promotion_probability=(overrides.promotion_intensity
                                   if overrides.promotion_intensity is not None
                                   else config.retail.promotion_probability),
            stockout_probability=(overrides.stockout_intensity
                                  if overrides.stockout_intensity is not None
                                  else config.retail.stockout_probability),
        )
    if overrides.noise_sigma is not None:
        config.time_series = replace(config.time_series, noise_sigma=overrides.noise_sigma)
# Wire-in (one line, AFTER _apply_phase2_overrides at :241):
#   _apply_seed_overrides(config, params.overrides)
```

```python
# app/features/demo/pipeline.py — step changes (sketch)

# DemoContext additions (after workspace_name, with an E3 #409 comment):
#   seed_overrides: SeederOverrides | None = None
#   user_scope: UserScope | None = None
# run_pipeline ctx construction: thread req.seed_overrides / req.user_scope.

# step_seed — effective dims + verbatim forward:
#   stores = ctx.seed_overrides.stores if (ctx.seed_overrides and ctx.seed_overrides.stores) else profile.stores
#   products = ... same for products ...
#   window: if ctx.seed_overrides and ctx.seed_overrides.window_days:
#       seed_end = datetime.now(UTC).date(); seed_start = seed_end - timedelta(days=ctx.seed_overrides.window_days)
#   elif profile.window is not None: ... (existing pinned branch; validator already
#       guarantees window_days is never set on holiday_rush)
#   json_body gains: **({"overrides": ctx.seed_overrides.model_dump(exclude_none=True)}
#                      if ctx.seed_overrides else {})
#   detail line + data echo the effective dims and "overrides" keys applied.

# step_status — user-scope branch BEFORE first-pair discovery:
#   if ctx.user_scope is not None:
#       try:
#           store_body = await client.request("status[scope-store]", "GET",
#               f"/dimensions/stores/{ctx.user_scope.store_id}")
#           product_body = await client.request("status[scope-product]", "GET",
#               f"/dimensions/products/{ctx.user_scope.product_id}")
#       except _StepError:
#           scope_warn = ("user_scope (store=%d, product=%d) not found — fell back "
#                         "to discovered pair" % (...))   # WARN, never fail (replay safety)
#       else:
#           ctx.store_id, ctx.product_id = ctx.user_scope.store_id, ctx.user_scope.product_id
#           -> return ("pass", f"... store_id={..} product_id={..} (user-selected)",
#                      {..., "user_scope_applied": True})
#   # fallback / no-scope path: existing discovery (582-631) unchanged; when the
#   # scope dangled return ("warn", scope_warn + discovery detail,
#   #                       {..., "user_scope_applied": False}).
```

```python
# app/features/demo/workspace.py — create_workspace constructor additions
#   (INSIDE the existing try; attribute names per the merged E1 model —
#    CONTRACT(E1): assumed `seed_overrides` / `user_scope` nullable JSONB):
#   seed_overrides=(req.seed_overrides.model_dump(mode="json", exclude_none=True)
#                   if req.seed_overrides else None),
#   user_scope=(req.user_scope.model_dump(mode="json") if req.user_scope else None),
```

```tsx
// frontend/src/lib/workspace-replay.ts (NEW) — replay-verbatim in ONE place
import type { DemoRunRequest, WorkspaceListItem } from '@/types/api'

/** Build the verbatim replay start frame for a saved workspace (E4 semantics
 *  + E3 #409 slots). Omits absent optionals so legacy rows replay byte-
 *  identically to today. */
export function workspaceToRunRequest(ws: WorkspaceListItem): DemoRunRequest {
  return {
    seed: ws.seed,
    scenario: ws.scenario,
    reset: ws.reset,
    skip_seed: ws.skip_seed,
    preservation: 'keep',
    // CONTRACT(E1): replay provenance — post-E1, handleReplayWorkspace's inline
    // object sends this field (an E1 frozen success criterion); this helper
    // REPLACES that object and must preserve it or lineage silently regresses.
    replayed_from_workspace_id: ws.workspace_id,
    ...(ws.name ? { workspace_name: ws.name } : {}),
    ...(ws.seed_overrides ? { seed_overrides: ws.seed_overrides } : {}),
    ...(ws.user_scope ? { user_scope: ws.user_scope } : {}),
  }
}

// types/api.ts additions (surgical):
//   export interface SeedOverrides { stores?: number; products?: number;
//     window_days?: number; sparsity?: number; promotion_intensity?: number;
//     stockout_intensity?: number; noise_sigma?: number }
//   export interface UserScope { store_id: number; product_id: number }
//   DemoRunRequest += seed_overrides?: SeedOverrides; user_scope?: UserScope
//   WorkspaceListItem += seed_overrides: SeedOverrides | null; user_scope: UserScope | null

// SeedConfigPanel.tsx — props: { value: SeedOverrides | null; onChange(v: SeedOverrides | null): void;
//   disabled?: boolean; windowLocked?: boolean /* holiday_rush */ }
//   <Collapsible> "Advanced seed config"; Inputs (stores 1..20 UI-range, products 1..50,
//   window_days 75..365) + Sliders (sparsity 0..0.9 step .05, promo/stockout 0..0.5,
//   noise 0..0.5); live summary line; NaN-WAPE caveat <Badge>; emits null when all unset.
//   UI ranges are TIGHTER than the API bounds (laptop-scale); the API bounds are the law.

// ScopeSelector.tsx — props: { value: UserScope | null; onChange(v: UserScope | null): void;
//   disabled?: boolean }
//   two shadcn <Select>s fed by useStores/useProducts({ page: 1, pageSize: 100 });
//   preview <Card>: store code/name/region/type · product sku/name/category/brand ·
//   seeded window from useSeederStatus(); "Clear" button → onChange(null).

// showcase.tsx wiring:
//   const [seedOverrides, setSeedOverrides] = useState<SeedOverrides | null>(null)
//   const [userScope, setUserScope] = useState<UserScope | null>(null)
//   - panel rendered when `reseed` ticked (windowLocked={scenario === 'holiday_rush'});
//     unticking Re-seed clears overrides (validator parity).
//   - ticking Reset database clears userScope + shows the re-pick caveat
//     (text-destructive, mirrors :309).
//   - handleRun spread: ...(reseed && seedOverrides ? { seed_overrides: seedOverrides } : {}),
//                       ...(userScope ? { user_scope: userScope } : {})
//   - handleLoadWorkspace: setSeedOverrides(ws.seed_overrides ?? null); setUserScope(ws.user_scope ?? null)
//   - handleReplayWorkspace: start(workspaceToRunRequest(ws))  // replaces the inline object
```

### List of tasks (dependency order)

```yaml
Task 0 — E1 gate & re-anchor (BLOCKING):
  VERIFY: gh issue view 407 --json state   # must be CLOSED (E1 merged)
  RUN: git switch dev && git pull
  READ on the post-E1 dev: app/features/demo/models.py (slot attribute names/types),
    app/features/demo/workspace.py (create_workspace shape), app/features/demo/schemas.py
    (whether E1 surfaced slots on Workspace* responses), frontend/src/types/api.ts,
    AND frontend/src/pages/showcase.tsx handleReplayWorkspace — E1 wires
    replayed_from_workspace_id into the inline replay object that Task 9's
    workspaceToRunRequest replaces; confirm the helper preserves it.
  RESOLVE every CONTRACT(E1) tag in this PRP against reality; adjust attribute
    names below if E1's PRP chose different ones (e.g. a single story JSONB).
  RUN: git switch -c feat/showcase-completion-e3-seed-config-scope
  VERIFY: gh issue view 409 --json state   # open

Task 1 — CREATE app/shared/seeder/overrides.py (+ tests):
  - SeederOverrides per the blueprint (strict, extra=forbid, 7 bounded knobs, is_empty()).
  - CREATE app/shared/seeder/tests/test_overrides.py (the shared/seeder/tests dir exists):
      bounds (each knob low/high rejection), unknown-knob forbid, JSON-path
      model_validate({...}) happy path, model_dump(exclude_none=True) sparseness,
      is_empty() truth table.
  - Optionally re-export from app/shared/seeder/__init__.py (match how
    ScenarioPreset/SeederConfig are exported there — service.py:32 imports them
    from the package).

Task 2 — MODIFY app/features/seeder/schemas.py + service.py:
  - GenerateParams: ADD `overrides: SeederOverrides | None = Field(default=None,
    description="Curated nested overrides (E3 #409); applied LAST — wins over the
    scalar stores/products/sparsity. Absent = byte-identical legacy behavior.")`
    (import from app.shared.seeder.overrides; do NOT touch strict-mode config).
  - service.py: ADD _apply_seed_overrides (blueprint); CALL it after
    _apply_phase2_overrides(config, params) in _build_config_from_params.
  - timedelta already imported in service.py (:8).

Task 3 — seeder tests:
  - test_service.py: (a) each knob maps to its config field; (b) overrides.stores
    beats params.stores (precedence); (c) window_days math
    (config.start_date == config.end_date - timedelta(days=N)); (d) sparse-preset
    character preserved (overrides.sparsity set → random_gaps_per_series still 3);
    (e) REGRESSION: params without overrides → config equal to today's output.
  - test_routes.py (TestGenerate class): 201 with {"overrides": {"stores": 8,
    "promotion_intensity": 0.3}}; 422 on {"overrides": {"stores": 0}};
    422 on {"overrides": {"bogus_knob": 1}} (extra=forbid).

Task 4 — MODIFY app/features/demo/schemas.py:
  - ADD UserScope; ADD DemoRunRequest.seed_overrides / .user_scope; ADD the two
    model_validators (blueprint). Update the class docstring's strict-mode note
    (nested models are JSON-native — cite the runtime verification).
  - ADD seed_overrides/user_scope to WorkspaceListItem (Detail inherits) —
    CONTRACT(E1): skip/merge if E1 already exposed them; ensure LIST exposure.

Task 5 — demo schema tests (app/features/demo/tests/test_schemas.py):
  - JSON-path: DemoRunRequest.model_validate({"skip_seed": False,
    "seed_overrides": {"stores": 8}}) OK; seed_overrides + skip_seed True →
    ValidationError; empty overrides {} normalizes to None; window_days +
    scenario "holiday_rush" → ValidationError; user_scope happy path +
    extra-key forbid + ge=1 bounds; LEGACY 4-field frame still validates
    (extend test_demo_run_request_legacy_frame_still_validates' sibling).
  - WorkspaceListItem from_attributes round-trip with slot dicts and with NULLs.

Task 6 — MODIFY app/features/demo/pipeline.py:
  - DemoContext: + seed_overrides / user_scope (typed, E3 #409 comment block).
  - run_pipeline: thread req.seed_overrides / req.user_scope into ctx (:2646-2651).
  - step_seed: effective dims + window_days branch + "overrides" body key
    (blueprint); detail/data echo.
  - step_status: user-scope validate/adopt/warn-fallback branch (blueprint);
    data gains "user_scope_applied".

Task 7 — pipeline tests (test_pipeline.py, _RecordingClient @1025):
  - test_step_seed_forwards_seed_overrides: ctx with overrides; assert POST
    /seeder/generate body["overrides"] == {"stores": 8, ...}, body["stores"] == 8
    (effective), sparsity scalar stays 0.0.
  - test_step_seed_window_days_overrides_profile_window: 120-day delta between
    posted start/end.
  - test_step_status_honors_user_scope: canned 200s for
    /dimensions/stores/{id} + /dimensions/products/{id}; assert ctx.store_id/
    product_id == scope, status "pass", data["user_scope_applied"] is True.
  - test_step_status_dangling_scope_warns_and_falls_back: canned 404 for the
    store GET + normal discovery responses; assert status "warn",
    ctx ids == discovered pair, data["user_scope_applied"] is False.
  - test_run_pipeline_threads_new_fields (ctx construction).

Task 8 — MODIFY app/features/demo/workspace.py + tests:
  - create_workspace: write both slots (blueprint; INSIDE the try —
    warn-and-continue intact).
  - test_workspace.py: keep-run with overrides+scope persists sparse JSON;
    keep-run without them persists NULLs; create failure still returns None
    (existing warn-and-continue test stays green).
  - tests/test_e2e_demo.py (integration): extend test_demo_replay_same_config_
    twice (or add a sibling test_demo_replay_preserves_seed_overrides_and_scope):
    keep-run with seed_overrides + user_scope (skip_seed=False so the validator
    passes — use the smallest overrides, e.g. {"stores": 3, "products": 10},
    to keep wall-clock sane); replay via a second run with the row's recorded
    config; assert both rows' seed_overrides/user_scope JSON identical.

Task 9 — frontend types + replay helper:
  - types/api.ts: SeedOverrides + UserScope interfaces; DemoRunRequest +2
    optional fields; WorkspaceListItem +2 nullable fields (surgical — CRLF trap).
  - CREATE lib/workspace-replay.ts + workspace-replay.test.ts:
    legacy row (null slots) → frame WITHOUT the E3 keys (seed_overrides/
    user_scope) but ALWAYS WITH replayed_from_workspace_id = ws.workspace_id
    (CONTRACT(E1): deep-equal to the POST-E1 inline object, not the pre-E1
    shape); slotted row → frame includes both E3 keys verbatim; named/unnamed.

Task 10 — CREATE SeedConfigPanel.tsx + ScopeSelector.tsx (+ tests, + barrel):
  - Blueprint above; compose from installed primitives; semantic tokens only.
  - SeedConfigPanel.test.tsx: renders 7 controls; emits a sparse object (only
    touched knobs); emits null when cleared; disabled state; windowLocked
    disables the window control; caveat badge visible at high stockout/sparsity.
  - ScopeSelector.test.tsx: renders options from mocked useStores/useProducts
    (mock the hooks via vi.mock — keep the harness light per
    test-requirements.md); selection fires onChange with real ids; preview
    shows store/product names; Clear → onChange(null).
  - components/demo/index.ts: export both (match barrel style).

Task 11 — MODIFY frontend/src/pages/showcase.tsx:
  - State + wiring per the blueprint; handleReplayWorkspace uses
    workspaceToRunRequest; handleLoadWorkspace repopulates panel + selector;
    Reset-database tick clears userScope (+ caveat); Re-seed untick clears
    seedOverrides.

Task 12 — docs:
  - API_CONTRACTS.md: seeder row — "E3 (#409) — POST /seeder/generate accepts an
    additive Optional `overrides` object (allow-listed knobs: stores, products,
    window_days, sparsity, promotion_intensity, stockout_intensity, noise_sigma;
    `extra=forbid` → unknown knob 422; applied last, wins over the scalar
    stores/products/sparsity)". POST /demo/run row + WS start-frame bullet —
    "E3 (#409) — additive Optional `seed_overrides` (same object; requires
    skip_seed=false; window_days rejected on holiday_rush) and `user_scope`
    ({store_id, product_id}; validated by the status step, warn+fallback on a
    dangling pair); both persist to the workspace row and replay verbatim."
  - RUNBOOKS.md: showcase incident 29 — overrides/scope failure matrix:
    (a) 422 "seed_overrides requires skip_seed=false" → tick Re-seed first;
    (b) 422 window_days on holiday_rush → expected, pinned window;
    (c) status step ⚠️ "user_scope ... not found" → expected after reset/reseed
    (ids re-issued; sequences never reset) — re-pick the pair;
    (d) backtest ❌ NaN WAPE on high stockout/sparsity overrides → documented
    expected outcome (mirrors incident 28's sparse row).
    Workspace section: move "advanced seed configuration" out of the
    "Explicitly out of scope" list (now shipped: seed_overrides + user_scope;
    phase-level config remains out of scope) and note replay-verbatim covers
    the two new slots.
  - DOMAIN_MODEL.md: showcase_workspace aggregate — document both slot JSON
    schemas (the table above) + the requested-vs-effective-grain distinction.

Task 13 — gates, dogfood, commit, PR:
  - Validation Loop below (all levels).
  - Level 4 browser dogfood (mandatory per .claude/rules/ui-design.md).
  - git diff --stat surgical check (types/api.ts CRLF trap).
  - Commits per the convention block; PR into dev titled
    "feat(api,ui): showcase advanced seed config and scope selection (#409)".
```

### Integration Points

```yaml
DATABASE: none in E3 — the seed_overrides/user_scope JSONB slots ship in E1
  #407's migration. CONTRACT(E1): verify slots exist before Task 1.
CONFIG: none — no new settings or env vars.
ROUTES: none new — POST /seeder/generate, POST /demo/run, WS /demo/stream all
  extend via request-model changes only (umbrella: "no new router outside
  existing slices").
SHARED: app/shared/seeder/overrides.py is the one new module — the sanctioned
  cross-slice seam (both slices already import app/shared/seeder).
WS CONTRACT: start frame gains two additive optional keys; event stream shape
  unchanged (step data dicts gain echo keys only).
WORKSPACE ROW: create_workspace writes the slots; finalize untouched;
  PATCH /demo/workspaces/{id} (E1) deliberately NOT extended — overrides/scope
  are immutable run records, not patchable metadata.
FRONTEND: 2 new components + 1 lib helper + types + showcase wiring; WorkspacePanel /
  RunHistoryStrip / use-demo-pipeline are generic over the widened types (no edits).
```

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/          # both --strict, gate merge
cd frontend && pnpm lint
# Types: no NEW errors mentioning touched files (pre-existing tsc -b failures exist on dev):
cd frontend && pnpm tsc -b 2>&1 | grep -E "SeedConfigPanel|ScopeSelector|workspace-replay|types/api|pages/showcase" ; echo "exit=$? (1 = no matches = good)"
```

### Level 2: Unit Tests

```bash
uv run pytest app/shared/seeder app/features/seeder app/features/demo -v -m "not integration"
cd frontend && pnpm test --run src/components/demo/ src/lib/
cd frontend && pnpm test --run                      # full frontend suite
```

### Level 3: Integration (real Postgres — E1's migrated schema)

```bash
docker compose up -d && uv run alembic upgrade head
# CAVEAT: destructive seeder tests pollute the shared DB mid-suite — reset to a
# fresh DB before trusting Level-3 results (DROP/CREATE DATABASE, never `down -v`).
uv run pytest -v -m integration -k "demo or seeder"   # incl. the replay-slot regression
# Manual contract probes:
curl -s -X POST localhost:8123/seeder/generate -H 'content-type: application/json' \
  -d '{"scenario":"demo_minimal","stores":3,"products":10,"overrides":{"promotion_intensity":0.3,"noise_sigma":0.25}}' | head -c 300
curl -s -X POST localhost:8123/seeder/generate -H 'content-type: application/json' \
  -d '{"overrides":{"bogus":1}}' -o /dev/null -w '%{http_code}\n'        # 422
curl -s -X POST localhost:8123/demo/run -H 'content-type: application/json' \
  -d '{"skip_seed":true,"seed_overrides":{"stores":5}}' -o /dev/null -w '%{http_code}\n'  # 422
```

### Level 4: Browser dogfood (uvicorn :8123 + vite :5173)

```bash
uv run uvicorn app.main:app --port 8123 &
cd frontend && ./node_modules/.bin/vite --host 0.0.0.0 &   # bypasses pnpm 11 depsStatusCheck
# Real browser (webapp-testing / agent-browser; on this host Playwright needs
# executable_path=/snap/bin/chromium):
#  1. /showcase: tick "Re-seed first" → Advanced seed config panel appears;
#     untick → panel collapses and overrides clear.
#  2. Set stores=8, products=20, promo=0.3 → Run: green; seed card detail
#     echoes "8 stores x 20 products"; /seeder/status confirms dims.
#  3. Pick a focus pair in the ScopeSelector (preview shows names + window) →
#     Run (skip_seed): status card says "(user-selected)"; train/backtest
#     Inspect links target the chosen pair.
#  4. Save as workspace + Run → workspace panel row → Replay: the replayed run
#     uses the same overrides + scope (status card user-selected; second
#     workspace row's slots identical — check GET /demo/workspaces).
#  5. Tick "Reset database" → scope selection clears with the caveat.
#  6. Pick holiday_rush + Re-seed → window_days control disabled (tooltip).
#  7. Legacy path: no overrides, no scope → run is indistinguishable from today.
```

## Final validation Checklist

- [ ] Backend gates: `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"`
- [ ] Frontend: `pnpm lint && pnpm test --run` green; no NEW tsc -b errors in touched files
- [ ] Seeder: overrides 201 / bounds 422 / unknown-knob 422 / no-overrides byte-identical (tests enforce)
- [ ] Demo validators: seed_overrides×skip_seed and window_days×holiday_rush rejected; legacy frame green (JSON-path tests)
- [ ] Pipeline: overrides forwarded; user_scope honored; dangling scope WARNS + falls back (tests enforce)
- [ ] Workspace: slots persisted sparse/NULL; replay-verbatim regression green (integration)
- [ ] Replay helper: workspaceToRunRequest covers legacy + slotted rows (FE test)
- [ ] Browser dogfood (Level 4) performed in a real browser — not just tests
- [ ] `git diff --stat` surgical (types/api.ts CRLF trap)
- [ ] API_CONTRACTS + RUNBOOKS 29 + workspace-section + DOMAIN_MODEL slot schemas updated additively
- [ ] Commits reference #409, scopes from the allow-list, no AI trailer; PR into dev
- [ ] Every CONTRACT(E1) tag was re-verified against the merged E1 code (Task 0)

---

## Assumptions (explicit — no user clarification was available)

1. **CONTRACT(E1):** `showcase_workspace` carries `seed_overrides` and `user_scope` as TWO separate nullable JSONB columns (precedent: `created_objects` / `result_summary`, `models.py:77-81`). If E1's PRP instead nests all story slots under one JSONB column, only the `create_workspace` write and the response-schema mapping change (Task 0 re-anchor).
2. **CONTRACT(E1):** E1's migration ships the slots; E3 ships ZERO migrations. If E1 somehow deferred a slot, E3 must STOP and add it to E1, not ship its own migration.
3. **CONTRACT(E1):** `config_schema_version` semantics are E1's; populating reserved slots does NOT bump it (assumed to stay at E1's initial value). E3 writes nothing to that column.
4. **CONTRACT(E1):** workspace API responses — E3 requires `seed_overrides` + `user_scope` on the LIST item (replay reads list rows, `showcase.tsx:174-186`). If E1 exposed them detail-only (or not at all), E3 adds them to `WorkspaceListItem`; if E1 already added them, Task 4 merges instead of duplicating.
5. **CONTRACT(E1):** replay provenance (`replayed_from_workspace_id`) is written by the E1/E2 replay surface; E3's replay-verbatim test must tolerate (not assert away) that column being populated.
6. **CONTRACT(E1):** `PATCH /demo/workspaces/{id}` exists (E1) and is deliberately NOT extended by E3 — overrides/scope are immutable run records.
7. Knob names (`promotion_intensity`, `stockout_intensity`, `noise_sigma`, `window_days`) are this PRP's choice — business-friendly on the wire, mapped to the internal dataclass names in one documented table. Renaming costs a constant, not a rework.
8. Bounds are this PRP's choice (table above), justified against preset reference values; the UI constrains tighter (laptop-scale) than the API.
9. `user_scope` dangling resolution = WARN + fallback (not fail): chosen so replay of a `reset=true` workspace can never hard-fail forever; divergence stays visible via the requested-slot vs effective-columns split.
10. The seeder-side field is named `overrides` (the slice context makes `seed_` redundant); the demo-side field is `seed_overrides` (epic-specified name). The pipeline maps one to the other in `step_seed`.

## Anti-Patterns to Avoid

- ❌ Don't create a new seeder endpoint — the decision above is final for E3; the nested object rides the existing contract.
- ❌ Don't widen the knob allow-list beyond the 7 — the umbrella names this the top risk; everything else stays preset-driven (`extra="forbid"` enforces it).
- ❌ Don't add any mid-run configuration channel — all config is start-frame-time; the single-`asyncio.Lock` linear pipeline is a design invariant.
- ❌ Don't import `app/features/seeder/*` from the demo slice (or vice versa) — the shared schema lives in `app/shared/seeder/overrides.py`.
- ❌ Don't add `ConfigDict(strict=True)` to `GenerateParams` (it has date fields) — only the new nested models are strict.
- ❌ Don't make a dangling `user_scope` fail the run — warn + fallback (replay safety); equally, don't silently adopt it without validation.
- ❌ Don't let a workspace slot write break the pipeline — slot writes stay inside the warn-and-continue try/except.
- ❌ Don't ship a migration — E1 owns the schema.
- ❌ Don't NaN-WAPE-proof the backtest for extreme overrides — document the expected fail (runbook 29), mirroring the sparse-preset decision in E2/#391.
- ❌ Don't hand-roll new UI primitives or install shadcn components when collapsible/select/slider/input/badge/tooltip already exist; if forced, pin `shadcn@4.7.0`.
- ❌ Don't ship the UI without a real-browser check — `.claude/rules/ui-design.md` makes that a hard requirement.

## Confidence Score

**8/10** for one-pass implementation success. Every backend change extends a
verified, line-cited in-repo pattern (the seeder's layered override pipeline,
the `DemoRunRequest` cross-field validators, `_RecordingClient` step tests, the
warn-and-continue workspace writes), the pydantic strict/nested/forbid
behavior was runtime-verified rather than assumed, and the riskiest judgment
calls (contract shape, knob mapping, bounds, dangling-scope semantics, slot
schemas) are decided with rationale and pinned by tests. The −2: (a) this PRP
is authored PRE-E1 — six CONTRACT(E1) tags must survive a cross-check against
the merged E1 code, and attribute-name drift there would touch 3 files (Task 0
exists precisely to absorb this); (b) the two new frontend components are the
usual UI-iteration surface (styling/dogfood may need a second pass), and
`showcase.tsx` is a merge hotspot shared with parallel epics E2/E4/E5.
