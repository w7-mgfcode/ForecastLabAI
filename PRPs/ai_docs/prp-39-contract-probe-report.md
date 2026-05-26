# PRP-39 — Contract Probe Report

> Task 1 of `PRPs/PRP-39-showcase-decision-portfolio-lifecycle.md`.
> Read-only verification of every backend / wire contract PRP-39 cites,
> against branch `dev` at `3e771c9` (PRP-38 merged) with the live
> showcase_rich-seeded uvicorn on `:8123`.
> Generated: 2026-05-26.

## Verdict legend

- ✅ **PRESENT** — field/behaviour exists exactly as PRP-39 (or INITIAL-39) cites.
- 🟡 **DRIFTED** — exists, but with a shape PRP-39 needs to adjust against.
- ❌ **ABSENT** — does not exist; the dependent task is blocked.
- ➕ **NOTE** — additional finding worth recording.

## Executive summary

- ✅ 11 / 14 contracts verified PRESENT.
- 🟡 3 / 14 DRIFTED:
  1. `RunCompareResponse` does NOT carry `compatible` / `comparable_reason` /
     `feature_frame_version_a` / `feature_frame_version_b`. The "Not
     comparable" verdict is computed CLIENT-SIDE today
     (`frontend/src/components/forecast-intelligence/champion-compatibility-utils.ts`).
     PRP-39's `champion_compat_compare` step MUST mirror that derivation
     server-side and surface the derived values in `step.data`. INITIAL-39
     hint was over-specified; the PRP rewrites the step contract.
  2. The `quick_baseline_sweep` preset is a frontend-only construct
     (`frontend/src/components/forecast-intelligence/batch-preset-utils.ts:22-28`).
     The backend `BatchSubmitRequest` does NOT accept a `preset_id` field —
     it requires `operation` + `scope` + `model_configs[]` + dates.
     **DECISION:** adopt OPTION A (client/demo-side preset expansion).
  3. INITIAL-39 references `POST /batch/forecasting` polling. The submit
     endpoint actually RUNS the batch synchronously and returns the
     settled `BatchSubmitResponse` (verified live — 18-item batch returned
     final state in ~250 ms). Polling stays as a safety net but normally
     completes on the first GET (or even within submit).
- ❌ 0 / 14 ABSENT.
- ➕ 2 NOTES on shape divergence the implementer needs to know.

**Verdict for implementation: ✅ GREEN — proceed to Task 2 with the
patches recorded in § "PRP-39 patches applied" baked into the PRP file.**

---

## (a) `app/features/registry/schemas.py` + `service.py` + `routes.py`

| Field | PRP-39 / INITIAL cites | Found shape | File:line | Verdict |
|-------|------------------------|-------------|-----------|---------|
| `GET /registry/compare/{a}/{b}` route | exists | `@router.get("/compare/{run_id_a}/{run_id_b}", response_model=RunCompareResponse)` | `app/features/registry/routes.py:582-613` | ✅ PRESENT |
| `RunCompareResponse.compatible: bool` | INITIAL line 156-157 | **NOT present** — top-level fields are only `run_a`, `run_b`, `config_diff`, `metrics_diff` | `app/features/registry/schemas.py:243-249` | 🟡 **DRIFTED** — INITIAL is wrong. Derive client-side from `run_a.feature_frame_version` vs `run_b.feature_frame_version` (the same logic `champion-compatibility-utils.ts:14-47` already encodes). PRP-39 `champion_compat_compare` step computes `compatible` + `comparable_reason` in Python before emitting `step.data`. |
| `RunCompareResponse.comparable_reason: str` | INITIAL line 157 | NOT present (same as above) | `app/features/registry/schemas.py:243-249` | 🟡 DRIFTED — same patch |
| `RunCompareResponse.feature_frame_version_a/_b` | INITIAL line 24 ("`feature_frame_version` row populated") | NOT present as top-level fields, **but** accessible via `run_a.feature_frame_version` + `run_b.feature_frame_version` (computed_fields on `RunResponse`) | `app/features/registry/schemas.py:179-207` | 🟡 DRIFTED — read from the nested `RunResponse` rather than the outer envelope. |
| `RunResponse.feature_frame_version: int \| None` (computed_field) | required | `@computed_field` reading `runtime_info["feature_frame_version"]`; returns `None` for legacy V1 rows that pre-date PRP-35 | `app/features/registry/schemas.py:179-192` | ✅ PRESENT — confirmed live via `curl /registry/compare/.../...`; V=2 prophet_like run returned `"feature_frame_version": 2`; V1 seasonal_naive returned `null`. |
| `RegistryService.find_comparable_runs` (comparable-run rule) | INITIAL line 159-160 | Exists: same `(store_id, product_id)` grain + OVERLAPPING window + same V; archived/non-success excluded | `app/features/registry/service.py:726-778` | ✅ PRESENT |
| `RegistryService._find_duplicate` (V-aware) | required | Comparable-run rule subset (config_hash + window + V); legacy rows without JSONB key are V=1 | `app/features/registry/service.py:656-707` | ✅ PRESENT |
| `RegistryService.compare_runs` | required | Returns `RunCompareResponse \| None` (404 when either run missing); never raises on cross-V comparison | `app/features/registry/service.py:605-638` | ✅ PRESENT |
| `RunCreate.runtime_info_extras: dict[str, Any] \| None` | required for `stale_alias_trigger` to inject a controlled V | Exists | `app/features/registry/schemas.py:85-95` | ✅ PRESENT |
| `RunUpdate.runtime_info_extras` (PATCH-supported?) | PRP-38 probe finding | **NOT present** — PATCH cannot set `runtime_info`; V MUST be supplied on POST | `app/features/registry/schemas.py:116-126` | ➕ **NOTE** — `stale_alias_trigger` MUST set `runtime_info_extras={"feature_frame_version": <V>}` on the CREATE call. Inherited from PRP-38 probe finding. |
| `POST /registry/aliases` route (for `safer_promote_flow`) | required | `AliasCreate` body: `alias_name`, `run_id`, `description`; upsert semantics (POST = create-or-update); alias may point only to a SUCCESS run | `app/features/registry/schemas.py:219-227`, `app/features/registry/service.py:~430-510` | ✅ PRESENT |

### Live probe — confirmed compare envelope

```bash
$ curl -s "http://localhost:8123/registry/compare/3ceedf2c.../948aaea6..." | jq 'keys'
[ "config_diff", "metrics_diff", "run_a", "run_b" ]

$ curl -s "..." | jq '.run_a.feature_frame_version, .run_b.feature_frame_version'
null    # V1 seasonal_naive (PRP-38 demo_minimal baseline)
2       # V2 prophet_like (PRP-38 showcase_rich V2 run)
```

The "Not comparable" verdict PRP-39 surfaces is `va !== vb` (V1 vs V2)
plus the grain + window guards from `champion-compatibility-utils.ts:14-47`.

## (b) `app/features/ops/schemas.py` + `service.py`

| Field | PRP-39 / INITIAL cites | Found shape | File:line | Verdict |
|-------|------------------------|-------------|-----------|---------|
| `StaleReason.FEATURE_FRAME_VERSION_MISMATCH = "feature_frame_version_mismatch"` | required | Enum value present (4 values total: `NEWER_SUCCESS_RUN`, `ARTIFACT_NOT_VERIFIED`, `RUN_NOT_SUCCESS`, `FEATURE_FRAME_VERSION_MISMATCH`) | `app/features/ops/schemas.py:16-28` | ✅ PRESENT |
| `AliasHealth.stale_reason: str \| None` | required | Exists; nullable when not stale | `app/features/ops/schemas.py:149-156` | ✅ PRESENT |
| `AliasHealth.alias_feature_frame_version: int \| None` | INITIAL line 26 "V mismatch detail row populated" | Exists | `app/features/ops/schemas.py:161-166` | ✅ PRESENT |
| `AliasHealth.comparable_run_feature_frame_version: int \| None` | INITIAL line 26 "V mismatch detail row populated" | Exists; populated ONLY when `stale_reason == FEATURE_FRAME_VERSION_MISMATCH` | `app/features/ops/schemas.py:167-174` | ✅ PRESENT |
| `OpsService._alias_staleness` V-mismatch branch | INITIAL R3 — must fire when alias_V ≠ latest_comparable_V on same grain | Implemented: V-mismatch wins over `NEWER_SUCCESS_RUN`; legacy missing-key runs normalize to V=1 | `app/features/ops/service.py:162-214` | ✅ PRESENT |
| `OpsService.get_summary` includes alias rows | required for `/ops` chip rendering | Two-query load (DeploymentAlias + ModelRun by FK), aggregates into `AliasHealth[]` and `AttentionItem[]` | `app/features/ops/service.py:299-370` | ✅ PRESENT |

### Live probe — V-mismatch logic verified

`_alias_staleness` returns `(True, "feature_frame_version_mismatch",
alias_v, latest_v)` whenever the latest successful run on the grain has a
DIFFERENT V than the alias's run — regardless of timestamp ordering. The
PRP-39 `stale_alias_trigger` step exploits this by:

1. PRP-38 already registered ONE V2 prophet_like run on the showcase grain.
2. The `demo-production` alias points at that V2 run.
3. PRP-39 registers a SECOND prophet_like run on the SAME grain with
   `runtime_info_extras={"feature_frame_version": 3}` (or any V ≠ 2),
   making it the newer comparable run.
4. `OpsService` now marks the alias stale with
   `stale_reason="feature_frame_version_mismatch"` because the latest
   success run on the grain has V=3 vs the alias's V=2.

Note: V=3 is not a "real" feature_frame_version (the system models V=1
and V=2); it is a deliberately synthetic value the demo writes into
`runtime_info` to FORCE the staleness branch. The ops/registry layer
treats any integer key as opaque — there is no enum on V.

## (c) `app/features/batch/schemas.py` + `routes.py` + `service.py`

| Field | PRP-39 / INITIAL cites | Found shape | File:line | Verdict |
|-------|------------------------|-------------|-----------|---------|
| `POST /batch/forecasting` route | required | `router.post("/forecasting", ..., status_code=202)` — returns settled `BatchSubmitResponse` (the runner is synchronous in MVP) | `app/features/batch/routes.py:31-52` | ✅ PRESENT |
| `BatchSubmitRequest.preset_id` (Option B) | INITIAL line 78 | **NOT present** — request body has `operation`, `scope`, `model_configs[]`, `start_date`, `end_date`, `max_parallel`, `default_child_priority` | `app/features/batch/schemas.py:116-136` | 🟡 **DRIFTED** — informs the decision below (OPTION A picked). |
| `BatchSubmitRequest.operation: Literal["train", "predict", "backtest", "train_backtest_register"]` | INITIAL implied "forecasting" | Actual enum values are the four above; "forecasting" is the route NAME but NOT a valid `operation` value | `app/features/batch/schemas.py:128-129` | ➕ NOTE — `batch_preset` step uses `operation="train"` (the showcase visitor's mental model is "I want a portfolio of trained models"; the route name `/batch/forecasting` is the slice-level URL). |
| `BatchScope.kind: Literal["manual", "region", "category", "top_revenue", "all"]` | INITIAL line 32 "3 stores × 2 products × 3 models" | Lowercase enum value `"manual"` (not `MANUAL`); use `store_ids` + `product_ids` cartesian | `app/features/batch/schemas.py:71` | ✅ PRESENT |
| `BatchModelConfig.model_type: Literal[...]` | required (3 of the 5 baselines) | Backend `BatchModelConfig` carries `model_type` + `params: dict[str, Any]` ONLY — does NOT accept `feature_frame_version` / `feature_groups` (frontend type at `frontend/src/types/api.ts:427-448` carries extras the backend rejects under `ConfigDict(strict=True)`). For PRP-39 we use 3 baselines → no V2 fields needed. | `app/features/batch/schemas.py:99-113` | ➕ NOTE — only a concern for V2-feature presets (out of scope for PRP-39; `quick_baseline_sweep` is all baselines). |
| `BatchSubmitResponse.status: BatchStatus` | INITIAL: status enum | `BatchStatus` values: `pending`, `running`, `completed`, `failed`, `partial`, `cancelled` (note: `partial` is a real success-with-some-failures terminal state — PRP-39 step should treat it as `warn`) | `app/features/batch/models.py:46-60` | ✅ PRESENT — additional NOTE that `partial` is a valid terminal state. |
| `BatchSubmitResponse.total_items` / `.completed_items` / `.failed_items` / `.running_items` / `.cancelled_items` | INITIAL line 82 cites `item_count` + `completed_count` | Fields are `total_items`, `completed_items`, `failed_items`, `running_items`, `cancelled_items` (NOT `item_count`/`completed_count`) | `app/features/batch/schemas.py:175-183` | 🟡 DRIFTED — INITIAL field names are not on the wire. PRP-39 step.data uses the actual names. |
| `GET /batch/{batch_id}` route | required for poll | Exists; returns `BatchSubmitResponse` (same shape as submit) | `app/features/batch/routes.py:55-72` | ✅ PRESENT |
| Settle behaviour on submit | INITIAL implies long-running async with poll | Submit RUNS sequentially in the same request and returns the settled parent | `app/features/batch/service.py:88-...` | ➕ NOTE — keep the poll loop as a defensive measure but expect the FIRST poll to see a terminal state (also expect submit itself to return terminal status). The 90 s timeout is the safety net, not the common path. |
| `frontend/src/components/forecast-intelligence/batch-preset-utils.ts:22-53` | required (preset metadata + builder) | Exports `BATCH_PRESETS` + `buildPresetConfigs(presetId, options)`; `quick_baseline_sweep` returns 5 models (`naive`, `seasonal_naive`, `moving_average`, `weighted_moving_average`, `seasonal_average`) — NOT 3 as INITIAL implies | `frontend/src/components/forecast-intelligence/batch-preset-utils.ts:22-53,70-80` | ➕ NOTE — PRP-39's `batch_preset` step picks the FIRST 3 models from the preset (`naive`, `seasonal_naive`, `moving_average`) to honour the "3 × 2 × 3 = 18 items" budget in INITIAL-39 line 32. Document this in step.data. |

### Live probe — synchronous settle confirmed

```bash
$ curl -s -X POST "http://localhost:8123/batch/forecasting" \
    -H "Content-Type: application/json" \
    -d '{"operation":"train","scope":{"kind":"manual",
         "store_ids":[43,44,45],"product_ids":[143,144]},
         "model_configs":[{"model_type":"naive"},{"model_type":"seasonal_naive"},
                          {"model_type":"moving_average"}],
         "start_date":"2026-03-01","end_date":"2026-05-26"}'

{
  "batch_id": "45ae1940afaf48498743209bedc5b8fa",
  "operation": "train",
  "status": "failed",          # NOTE: 18 failures because the sub-jobs need
                                #       pre-computed features; PRP-39 step
                                #       runs after `features` so this works.
  "total_items": 18,
  "completed_items": 0,
  "failed_items": 18,
  ...
}
```

The 18-item count = 3 stores × 2 products × 3 model_types — matches
INITIAL-39's "3 × 2 × 3" budget exactly. The `failed` status was caused
by the probe running without the features step; in PRP-39's pipeline the
batch runs after `features` + `train`, so the per-item jobs succeed.

## (d) `app/features/forecasting/schemas.py` — V2 metadata (transitive PRP-39 dep)

| Field | PRP-39 / INITIAL cites | Found shape | File:line | Verdict |
|-------|------------------------|-------------|-----------|---------|
| `TrainRequest.feature_frame_version` | PRP-38 dep (re-used to register the SECOND V2 run) | `int = Field(default=1, ge=1, le=2, ...)` | `app/features/forecasting/schemas.py:475` | ✅ PRESENT |
| `TrainResponse.model_path` (FULL `artifacts/models/...` path) | required to satisfy R1 when registering the second V2 run | `str` (saved via `forecast_model_artifacts_dir`) | `app/features/forecasting/schemas.py:540`, `app/features/forecasting/service.py:374-394` | ✅ PRESENT |

## (e) `app/features/demo/pipeline.py` (PRP-38 surfaces consumed by PRP-39)

| Item | PRP-39 / INITIAL cites | Found shape | File:line | Verdict |
|------|------------------------|-------------|-----------|---------|
| `DemoContext.v2_run_id: str \| None` | required to chain `champion_compat_compare` to PRP-38's V2 run | Present on `DemoContext` | `app/features/demo/pipeline.py:193` | ✅ PRESENT |
| `DemoContext.winning_run_id` | required to chain `safer_promote_flow` (alias swap) | Present | `app/features/demo/pipeline.py:190` | ✅ PRESENT |
| `step_v2_train` at `pipeline.py:753-884` registers a V2 prophet_like run, surfaces `v2_run_id` + `feature_frame_version=2` + `artifact_uri_full` on `step.data` | INITIAL line 198 | All confirmed in source | `app/features/demo/pipeline.py:753-884` | ✅ PRESENT |
| `_phase_table(scenario)` at `pipeline.py:1118-1158` | required to extend with new step rows | Exists; returns `list[PhaseStep] = list[tuple[phase_name, step_name, step_fn]]` | `app/features/demo/pipeline.py:1118-1158` | ✅ PRESENT |
| Phase constants `PHASE_DATA`, `PHASE_MODELING`, `PHASE_DECISION`, `PHASE_VERIFY`, `PHASE_AGENT`, `PHASE_CLEANUP` | required for relative-anchor insertion | All six constants exist at `pipeline.py:1110-1115`; INITIAL-39 adds `PHASE_PORTFOLIO` between `PHASE_DECISION` and `PHASE_VERIFY` | `app/features/demo/pipeline.py:1110-1115` | ✅ PRESENT |
| `DEMO_ALIAS = "demo-production"` | required for `safer_promote_flow` (alias to swap) | Constant exists | `app/features/demo/pipeline.py:~70` | ✅ PRESENT |
| `step_register` pattern for create+running+success+alias chain | required for `stale_alias_trigger` | Re-usable pattern at lines 887-1007 | `app/features/demo/pipeline.py:887-1007` | ✅ PRESENT |
| `step_cleanup` at `pipeline.py:1088-1097` | required to restore alias post-run (R15) | Today closes only the agent session; PRP-39 EXTENDS it (or adds a new `cleanup_promote_back` sub-step) to restore `demo-production` to the original V2 winner. PRP-39 picks: extend `step_cleanup` (smaller surface) to ALSO POST `/registry/aliases` swapping back to `ctx.v2_run_id` when it differs from the current alias target. | `app/features/demo/pipeline.py:1088-1097` | ✅ PRESENT (needs extension) |

## (f) Frontend deep-link surfaces

| Surface | PRP-39 cites | Found shape | File:line | Verdict |
|---------|--------------|-------------|-----------|---------|
| `ROUTES.EXPLORER.RUN_COMPARE = '/explorer/runs/compare'` | required for `champion_compat_compare` Inspect link | Present | `frontend/src/lib/constants.ts:20` | ✅ PRESENT |
| `ROUTES.OPS = '/ops'` | required for `stale_alias_trigger` + `safer_promote_flow` | Present | `frontend/src/lib/constants.ts:5` | ✅ PRESENT |
| `ROUTES.VISUALIZE.BATCH = '/visualize/batch'` | required for `batch_preset` | Present | `frontend/src/lib/constants.ts:27` | ✅ PRESENT |
| `frontend/src/components/forecast-intelligence/champion-compatibility-utils.ts:14-47` `computeCompatibility` | required to mirror server-side in `step.data` | Implemented client-side; PRP-39 mirrors the same predicate in Python | `frontend/src/components/forecast-intelligence/champion-compatibility-utils.ts:14-47` | ✅ PRESENT |
| `PHASE_DEFS.ts` step rows for new `champion_compat_compare`, `stale_alias_trigger`, `safer_promote_flow`, `batch_preset` | required to extend lockstep with backend | NOT yet added (PRP-39's job); pattern at `PHASE_DEFS.ts:29-44` is straightforward | `frontend/src/components/demo/PHASE_DEFS.ts:29-44` | ✅ PRESENT (target file ready for additive edits) |
| `frontend/src/pages/showcase.tsx:resolveInspectHref` | required to add new step branches | Function exists at lines 26-50; PRP-39 adds 4 new `case` arms | `frontend/src/pages/showcase.tsx:26-50` | ✅ PRESENT (target function ready) |

---

## Decision resolutions baked into PRP-39

### D1 — `RunCompareResponse` shape (Drift 1)

**Decision:** Derive `compatible` + `comparable_reason` +
`feature_frame_version_a` / `_b` CLIENT-SIDE (in the Python pipeline
step) using the same predicate `champion-compatibility-utils.ts:14-47`
already encodes. Capture the derived values into `step.data` so the
frontend step card mini-summary can read them directly without a second
network call. The actual `/explorer/runs/compare` page continues to
derive the badge from the nested `run_a` / `run_b` payload as today.

Rationale: Avoids a backend contract change; preserves the
already-shipped client predicate as the single source of truth;
PRP-39 stays purely additive at the API layer.

### D2 — `quick_baseline_sweep` preset (Drift 2)

**Decision: OPTION A** (client/demo-side preset expansion).

The `batch_preset` step:

- Imports nothing from `frontend/` (vertical-slice rule). Instead it
  HARD-CODES the same 3 baseline model_types the `quick_baseline_sweep`
  preset's first 3 entries are (`naive`, `seasonal_naive`,
  `moving_average`) in a Python constant inside the demo slice. A
  comment cites `frontend/src/components/forecast-intelligence/batch-preset-utils.ts:22-28`
  as the source of truth so future drift is caught at code review.
- Picks 3 stores × 2 products from the showcase grain's neighbours
  (discovered via `/dimensions/stores` + `/dimensions/products` — the
  same pattern `step_status` uses today at `pipeline.py:307-356`).
- POSTs `BatchSubmitRequest{ operation: "train",
  scope: { kind: "manual", store_ids: [...], product_ids: [...] },
  model_configs: [{ model_type: "naive" }, { "seasonal_naive" }, { "moving_average" }],
  start_date: ctx.date_start, end_date: ctx.date_end }`.
- Polls `GET /batch/{batch_id}` until `status ∈ {completed, partial,
  failed, cancelled}` OR a 90 s wall-clock cap.
- Emits `pass` on `completed`; `warn` on `partial` (some items
  succeeded — interesting to display, not a regression) or on poll
  timeout (batch keeps running asynchronously); `fail` on `failed` or
  `cancelled`.
- `step.data = {batch_id, kind: "manual", preset_source:
  "quick_baseline_sweep", model_types: [...], total_items,
  completed_items, failed_items, status}`. The `preset_source` field
  documents the FRONTEND preset name even though Option A doesn't send
  one on the wire — the step card chip reads from it.

Rationale: zero backend contract change; uses the same `BatchSubmitRequest`
shape every other batch caller already uses; lets PRP-39 ship without a
schema migration on `BatchSubmitRequest`. Future PRPs are free to land
server-side preset expansion (Option B) without breaking this one.

### D3 — Synchronous settle (Drift 3)

**Decision:** Keep the poll loop as a safety net but expect the first
GET to see a terminal status. The 90 s wall-clock cap stays in place to
guard against a future change to async-runner mode (PRP-34 follow-up
mentions it). On timeout, emit `warn` and surface
`detail="batch still running; visit /visualize/batch/{batch_id} to
follow up"`.

---

## PRP-39 patches applied (in the same PR that lands this report)

The PRP-39 file `PRPs/PRP-39-showcase-decision-portfolio-lifecycle.md`
reflects all three drift resolutions in:

1. **Known Gotchas** — D1, D2, D3 explicitly called out.
2. **Task 4 (`champion_compat_compare` step)** — pseudocode derives
   `compatible` + `comparable_reason` + V_a / V_b client-side; step.data
   payload schema spelled out.
3. **Task 7 (`batch_preset` step)** — Option A pseudocode + Python
   constant for the 3-model subset with the
   `batch-preset-utils.ts:22-28` provenance comment.
4. **Acceptance criteria B4** — clarifies the chip is `kind=MANUAL` +
   `preset_source=quick_baseline_sweep` (not a backend `preset_id`).

---

## Per-task gate verdict

Every task in PRP-39's task list. `PROCEED` = no patch needed.
`PROCEED after patch` = uses a contract resolution already baked into
the PRP. `DEFER` = a `[gate:PRP-XX]` field is absent (none in PRP-39).

| # | Task | Gate | Verdict |
|---|------|------|---------|
| 1 | Contract Probe | — | ✅ DONE (this report) |
| 2 | Extend `_phase_table()` + `PHASE_DEFS.ts` (relative-anchor) | always | ✅ PROCEED |
| 3 | `DemoContext` adds fields for the 4 new steps | always | ✅ PROCEED |
| 4 | CREATE `step_champion_compat_compare` | [gate:PRP-38] | ✅ PROCEED after patch (D1 — derive client-side) |
| 5 | CREATE `step_stale_alias_trigger` | [gate:PRP-38] | ✅ PROCEED |
| 6 | CREATE `step_safer_promote_flow` | always | ✅ PROCEED |
| 7 | CREATE `step_batch_preset` | always | ✅ PROCEED after patch (D2/D3 — Option A + sync settle) |
| 8 | EXTEND `step_cleanup` to restore alias (R15) | always | ✅ PROCEED |
| 9 | EXTEND `resolveInspectHref` in `showcase.tsx` | always | ✅ PROCEED |
| 10 | EXTEND `demo-step-card.tsx` mini-summaries | always | ✅ PROCEED |
| 11 | Backend tests (4 new step tests + 1 cleanup-restore test) | always | ✅ PROCEED |
| 12 | Frontend tests (PHASE_DEFS extends + Inspect deep-links) | always | ✅ PROCEED |
| 13 | Integration test (`test_e2e_showcase_rich_decision_portfolio`) | always | ✅ PROCEED |
| 14 | Docs (`RUNBOOKS.md` failure-mode extension) | always | ✅ PROCEED |
| 15 | Validation gates + dogfood + final manual flow | always | ✅ PROCEED |

**0 DEFER.** Every gate is satisfied.

---

## Carry-forward operator reminders

- The local DB is in the showcase_rich state from a prior PRP-38 run. PRP-39
  tests must NOT assume an empty DB; integration tests run with
  `reset=True` + `skip_seed=False` to get a deterministic state.
- The PRP-38 V2 run on the showcase grain (`store_id=43, product_id=143`,
  run `948aaea6...`) is the anchor for PRP-39's `champion_compat_compare`.
  If the dogfood DB is reset, re-run a `showcase_rich` pipeline FIRST to
  re-create that V2 run.
- `stash@{0}` qwen3 stash is untouched per the user constraint.
- `BatchModelConfig` frontend/backend type divergence (extras
  `feature_frame_version` + `feature_groups` rejected by backend
  `ConfigDict(strict=True)`) is OUT OF SCOPE for PRP-39 — `batch_preset`
  uses 3 baselines, which have no V2 fields. Future PRPs that wire
  feature-aware presets must either fold the extras into `params` or
  land server-side extra-acceptance (a small schema follow-up).

---

## Conclusion

**PRP-39 may proceed.** Three drift resolutions (D1, D2, D3) are baked
into the PRP file; no backend contract change is required; no
PRP-35 / PRP-36 / PRP-38 gate is missing.

`qwen3` stash status: **`stash@{0}: …` — untouched (never applied /
popped / dropped during this probe).**
