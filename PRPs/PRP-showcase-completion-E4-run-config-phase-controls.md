name: "PRP — showcase-completion E4: run-config phase controls (model set + backtest params in start frame)"
issue: "#410 (epic) · umbrella #406 · depends on E1 #407 (Foundation — MUST be merged first)"
branch: "feat/showcase-run-config-phase-controls (off dev)"
description: |
  Start-frame-time run configuration for the showcase pipeline: a model-family
  picker (baselines + feature-aware, with opt-in lightgbm/xgboost/random_forest
  toggles surfaced ONLY when the matching `forecast_enable_*` flag is on),
  backtest configuration (horizon, split strategy, min train size, n_splits,
  gap, ranking metric WAPE/MAE/RMSE), a train-candidate preview before launch,
  and the chosen config echoed into the workspace row and visible on the run.
  NO mid-run re-entry — the linear single-`asyncio.Lock` pipeline is preserved;
  all configuration happens in the start frame.

## Core Principles

1. **Context is King** — every file/line cited below was verified on 2026-06-12.
2. **Validation Loops** — Levels 1–4 below are executable; Level 4 browser dogfood is MANDATORY (UI work, `.claude/rules/ui-design.md`).
3. **Additive only** — a legacy start frame (no new fields) behaves **byte-identically** to today. This is a frozen umbrella #406 success criterion.
4. **Global rules** — CLAUDE.md / AGENTS.md / `.claude/rules/*` apply. Commits: `feat(api,db): … (#410)` for backend+migration, `feat(ui): … (#410)` for frontend (or one `feat(api,ui): … (#410)`).

---

## Goal

**Feature Goal**: An operator on `/showcase` can, before launching a run, (a) pick which forecasting models the pipeline trains/backtests, (b) tune the backtest split (horizon / strategy / n_splits / min_train_size / gap) and the winner-ranking metric (WAPE / MAE / RMSE), (c) see a train-candidate preview of exactly what will run, and (d) find that config recorded on the saved workspace row and honored verbatim on Replay.

**Deliverable** (all additive):

- `app/features/demo/schemas.py` — new `DemoBacktestConfig`; `DemoRunRequest` gains `train_model_types: list[str] | None` + `backtest: DemoBacktestConfig | None`; `WorkspaceListItem` gains `run_config: dict | None`.
- `app/shared/model_taxonomy.py` — public `KNOWN_MODEL_TYPES` frozenset (validation allow-list source of truth).
- `app/features/demo/models.py` + one Alembic migration — nullable `run_config` JSONB column on `showcase_workspace` (a **replay-input column** like `seed`/`scenario`, NOT an E1 story slot — see Decision D1).
- `app/features/demo/workspace.py` — `create_workspace` records `run_config`.
- `app/features/demo/pipeline.py` — `DemoContext` carries the resolved run config; `step_train` / `step_backtest` / `step_v2_train` honor it; `_select_winner` gains a metric parameter; `pipeline_complete` echoes the config.
- `app/features/model_selection/` — `CandidateModelInfo` gains `enabled: bool` (settings overlay in the service; `capabilities.py` stays pure) so the frontend knows which opt-in toggles to surface.
- `frontend/` — `RunConfigPanel` (collapsible advanced section on `/showcase`): model picker (reuses `CandidateModelPicker` with an enabled-filtered catalog), `DemoBacktestSettingsForm` (mirrors the champion-selector form), train-candidate preview; start-frame wiring with a dirty-only inclusion rule; Load/Replay honor `run_config`; WorkspacePanel shows a config summary.
- Docs: `docs/_base/API_CONTRACTS.md`, `docs/_base/DOMAIN_MODEL.md`, `docs/_base/RUNBOOKS.md` additive notes.
- Tests at every layer (schema, taxonomy drift-lock, pipeline, workspace, migration, catalog overlay, vitest).

**Success Definition**: all Success Criteria check off; five CI gates green; integration suite green; a Level-4 dogfood run launches a custom-config run from `/showcase`, the preview matched what ran, the workspace row carries `run_config`, and Replay re-runs it verbatim.

## Why

- Umbrella #406 success criterion: *"The start frame accepts model-set + backtest config; the chosen config is echoed into the workspace row and visible on the run."*
- Today `DEMO_MODEL_TYPES` (`pipeline.py:67`) hard-codes 3 baselines and `DEMO_HORIZON`/`DEMO_BACKTEST_SPLITS`/`DEMO_MIN_TRAIN_SIZE` (`pipeline.py:54-56`) hard-code the split — the showcase cannot demonstrate the 11-model zoo (PRP-36) or metric-driven champion selection it actually ships.
- Replay (E4 #393) is verbatim-by-design; without recording the run config, a custom run could not be replayed faithfully — breaking the workspace story the whole umbrella is about.
- Brainstorm Round 5 (`.flow/brainstorm-log.md`): mid-run/per-phase re-run was explicitly DEFERRED ("re-architects locked linear pipeline") — start-frame-only is the negotiated scope. Do not add mid-run controls.

## What

### User-visible behavior

1. `/showcase` controls card gains a collapsible **"Run configuration (advanced)"** section (collapsed by default — untouched = legacy behavior):
   - **Model picker**: checkboxes grouped by family (Baseline / Additive / Tree-based), fed by `GET /model-selection/models`. Opt-in models (`lightgbm`, `xgboost`, `random_forest`) appear **only when** their `forecast_enable_*` flag is on (new catalog `enabled` field). Default selection: `naive`, `seasonal_naive`, `moving_average` (the legacy trio). Cap 10, min 1.
   - **Backtest settings**: ranking metric (WAPE default / MAE / RMSE), horizon (1–90, default 14), and an "Advanced split settings" collapsible: strategy (expanding/sliding), splits (2–20, default 3), min train (≥7, default 30), gap (0–30, default 0). Inline validation mirrors backend bounds; soft warning when `min_train_size + n_splits×(horizon+gap)` exceeds the scenario's seeded window.
   - **Train-candidate preview**: a read-only chip list of exactly which models will train (selection, plus `prophet_like (V2)` appended on `showcase_rich`), with family badges and a count.
2. The WS start frame / `POST /demo/run` body carry `train_model_types` + `backtest` **only when the operator changed something** (dirty-only rule → untouched UI sends a byte-identical legacy frame).
3. The pipeline trains/backtests the selected models; the winner is the best **configured metric**; `pipeline_complete.data.run_config` echoes the config; the train/backtest step cards show what was requested.
4. On `preservation="keep"` runs the workspace row records `run_config`; the Saved-workspaces panel shows a compact config summary; **Load** repopulates the controls; **Replay** re-submits it verbatim.
5. A request naming a disabled/unknown model fails fast with an actionable message (422 on unknown at validation; a clear `fail` step detail on disabled-flag models).

### Technical requirements

- Pydantic v2 strict-mode policy respected (all new request fields JSON-native; nested model validated from a plain dict — add the JSON-path test).
- Vertical-slice rule: the demo slice NEVER imports `app/features/model_selection` (or any sibling) in Python — the model allow-list comes from `app/shared/model_taxonomy.py`; the frontend talks to the catalog over HTTP.
- Migration forward-only, applies + downgrades cleanly on a fresh DB.
- Workspace writes stay warn-and-continue (must never break a green run).

### Success Criteria

- [ ] `DemoRunRequest` accepts `train_model_types` + `backtest` (additive Optional); a legacy frame validates byte-identically (existing `test_demo_run_request_legacy_frame_still_validates` extended).
- [ ] Unknown model type → 422 / WS `error` event; duplicate model types rejected; `gap >= horizon` rejected; selection size 1–10 enforced.
- [ ] A run with `train_model_types=["naive","seasonal_average"]` trains exactly those models; `step_backtest` sends the configured `split_config` and picks the winner by the configured metric (unit-asserted against the canned `_Client` request bodies).
- [ ] A disabled opt-in model in the selection fails the `train` step with a detail naming the flag (`forecast_enable_lightgbm=false …`).
- [ ] `GET /model-selection/models` items carry `enabled`; `enabled=false` exactly when the matching `forecast_enable_*` flag is off (lightgbm/xgboost/random_forest), `true` for all always-on models.
- [ ] `showcase_workspace.run_config` records the config on keep-runs (NULL when defaults were used); migration up+down clean.
- [ ] `/showcase` advanced section renders the picker (opt-ins hidden when disabled), backtest form, and preview; Load/Replay honor `run_config`; untouched controls send a legacy frame (vitest-asserted).
- [ ] `pipeline_complete.data.run_config` echo present on custom runs, absent (None) on legacy runs.
- [ ] All five CI gates green; integration tests green; Level-4 dogfood evidence captured.

## All Needed Context

### Documentation & References

```yaml
# ── The work order ───────────────────────────────────────────────────────────
- issue: "#410"
  why: Epic scope (verbatim). Parallel after Foundation E1 #407.
- issue: "#406"
  why: Umbrella — approach ("additive-only delta", "start-frame-time only"), success criteria, risk table.
- file: PRPs/PRP-showcase-completion-E1-metadata-provenance-backbone.md
  why: |
    The Foundation this epic builds on. CRITICAL: E1 defines six JSONB story
    slots (seed_overrides, user_scope, approval_events, rag_events, job_ids,
    phase_summaries) — NONE of them is a run-config slot, and E1 assigns no
    slot to E4. See Decision D1 below. Also the migration-task pattern to
    MIRROR (down_revision discovery, up/down test) and config_schema_version
    semantics (lines 25-70, 228-236, 560-610 of that PRP).

# ── Backend: demo slice (primary surface) ────────────────────────────────────
- file: app/features/demo/schemas.py
  why: |
    DemoRunRequest (lines 29-86) — the additive-field pattern to MIRROR exactly:
    PRP-38 scenario field (enum-on-wire strict=False override, lines 51-63),
    E1 #390 preservation/workspace_name + model_validator (lines 64-85).
    WorkspaceListItem lines 169-189 (from_attributes response pattern).
- file: app/features/demo/pipeline.py
  why: |
    THE file. Constants to make configurable: DEMO_HORIZON=14,
    DEMO_BACKTEST_SPLITS=3, DEMO_MIN_TRAIN_SIZE=30 (54-56), DEMO_MODEL_TYPES
    (67). _model_config_payload (271-286) — extend. _select_winner (446-460)
    — hard-codes "wape"; gains metric param. step_train (669-703) — gather
    over DEMO_MODEL_TYPES, train tail = date_end - DEMO_HORIZON. step_backtest
    (731-836) — two branches (SHOWCASE_RICH single-call include_baselines=True
    at 743-788 vs legacy per-model loop at 789-818); split_config bodies at
    753-760/801-808. step_v2_train (998-1090) — V2 train tail also uses
    DEMO_HORIZON (1021). run_pipeline (2618-2771) — ctx construction (2646),
    create_workspace keep-branch (2655-2657), pipeline_complete data (2758-2770).
    DemoContext dataclass (212-264) — where resolved config fields land.
- file: app/features/demo/workspace.py
  why: |
    create_workspace (46-79) — records replay inputs at insert time; E4 adds
    run_config here (NOT in finalize: it is an input, known before step 1).
    Warn-and-continue pattern is load-bearing.
- file: app/features/demo/models.py
  why: ShowcaseWorkspace ORM (37-89). run_config column lands next to the
       "Run configuration -- replay inputs" block (line 65-69 comment).
- file: app/features/demo/routes.py
  why: WS start-frame parse (166-194) — ValidationError → one error event +
       close. No route changes needed beyond what schemas give for free
       (POST /demo/run + WS validate via DemoRunRequest).
- file: app/features/demo/tests/test_schemas.py
  why: Test naming + the legacy-frame contract test to extend
       (test_demo_run_request_legacy_frame_still_validates, line 75).
- file: app/features/demo/tests/test_pipeline.py
  why: Canned-_Client mocking pattern for step unit tests (assert on captured
       request bodies — exactly how the split_config assertion should work).
- file: app/features/demo/tests/test_workspace.py
  why: Integration-test pattern for create/finalize roundtrips.

# ── Backend: contracts the pipeline drives ───────────────────────────────────
- file: app/features/forecasting/schemas.py
  why: |
    TrainRequest (441-525): store/product/dates/config (+feature_frame_version,
    feature_groups — leave at V1 defaults for E4 training). ModelConfig is a
    discriminated union; ALL 11 members validate from a minimal
    {"model_type": X} payload (runtime-verified, see Gotchas). season_length
    default 7 (line 86), window_size default 7 (line 107).
- file: app/features/forecasting/routes.py
  why: Flag gates — lightgbm (line 76-81) and xgboost (82-86) raise
       BadRequestError 400 "… is disabled. Set forecast_enable_…". NOTE:
       random_forest is gated deeper (forecasting/models.py:1761) — another
       reason step_train must pre-check flags itself for a clean message.
- file: app/core/config.py
  why: "forecast_enable_lightgbm / forecast_enable_xgboost /
       forecast_enable_random_forest — all default False (lines 118-120)."
- file: app/features/backtesting/schemas.py
  why: |
    SplitConfig (24-73) — the canonical bounds DemoBacktestConfig MUST mirror:
    strategy Literal["expanding","sliding"] def "expanding"; n_splits 2-20
    def 5; min_train_size ge=7 def 30; gap 0-30 def 0; horizon 1-90 def 14;
    validator horizon > gap. BacktestConfig (81-108): split_config +
    model_config_main + include_baselines + store_fold_details.
    aggregated_metrics keys: mae, smape, wape, bias, rmse (PRP-36;
    rmse verified at app/features/backtesting/metrics.py:349).
- file: app/shared/model_taxonomy.py
  why: _MODEL_FAMILY_MAP — the 11 known model types. E4 adds public
       KNOWN_MODEL_TYPES here (one-way import app/features/* → app/shared OK).

# ── Backend: model catalog (flag exposure) ───────────────────────────────────
- file: app/features/model_selection/capabilities.py
  why: build_model_catalog (line 126) — pure/static by design (module
       docstring). Do NOT read settings here; overlay in the service.
- file: app/features/model_selection/service.py
  why: get_model_catalog (113-119) — thin pass-through; the enabled overlay
       goes here (model_copy(update={"enabled": …}) per item).
- file: app/features/model_selection/schemas.py
  why: CandidateModelInfo (412-429) + ModelCatalogResponse (431) — add
       `enabled: bool = True` (additive, defaulted for back-compat).
- file: app/features/model_selection/routes.py
  why: GET /model-selection/models (74-86) — no route change; response model
       picks up the new field automatically.

# ── Frontend ─────────────────────────────────────────────────────────────────
- file: frontend/src/pages/showcase.tsx
  why: |
    453 lines. Start-frame construction handleRun (139-156) — the
    spread-only-when-set pattern for byte-compat; handleLoadWorkspace
    (160-168) + handleReplayWorkspace (174-186) — must consume run_config;
    controls card (257-371) — the advanced section slots after the
    workspace-name block (line 362).
- file: frontend/src/components/champion-selector/candidate-model-picker.tsx
  why: REUSE this component (family-grouped checkbox grid, cap badge,
       extra/feature-aware badges). Feed it an enabled-filtered catalog.
- file: frontend/src/components/champion-selector/backtest-settings-form.tsx
  why: MIRROR for DemoBacktestSettingsForm — Field helper, metric Select,
       Collapsible advanced split knobs, splitConfigErrors display. Differences:
       horizon is EDITABLE here (champion's is locked), metric list is
       wape/mae/rmse (champion's is wape/smape/mae/bias).
- file: frontend/src/components/champion-selector/split-config.ts
  why: splitConfigErrors — REUSE as-is (field names match DemoBacktestConfig).
- file: frontend/src/hooks/use-model-selection.ts
  why: useModelCatalog (line 30) — REUSE for the picker's data.
- file: frontend/src/types/api.ts
  why: DemoRunRequest (778-788), WorkspaceListItem (805-815),
       CandidateModelInfo (1279-1290), SplitConfig comment block (~1262-1268).
- file: frontend/src/hooks/use-demo-pipeline.ts
  why: start(req) serializes DemoRunRequest verbatim into the WS start frame —
       no hook change needed; the dirty-only rule lives in showcase.tsx.
- file: frontend/src/components/demo/ScenarioPicker.tsx
  why: Disabled-while-running prop pattern; the scenario value feeds the
       preview (windowDays map mirrors pipeline.py _SCENARIO_SEED_PROFILE,
       513-538: demo_minimal/sparse/holiday_rush = 92d window, others = 180d).
- file: frontend/src/components/demo/WorkspacePanel.tsx
  why: Row layout to extend with the compact run-config summary line/badge.
- file: frontend/src/components/demo/RunHistoryStrip.test.tsx
  why: Representative vitest + RTL pattern for the new component tests.

# ── Project docs to update (additive) ────────────────────────────────────────
- file: docs/_base/API_CONTRACTS.md
  why: DemoRunRequest/WS start-frame field docs + catalog `enabled` +
       workspace run_config (follow the existing E1/E2/PRP-38 annotation style).
- file: docs/_base/DOMAIN_MODEL.md
  why: showcase_workspace aggregate — document run_config as a replay-input
       column (explicitly NOT a story slot; D1 rationale).
- file: docs/_base/RUNBOOKS.md
  why: § Showcase runbook — two new numbered incidents (disabled-model fail;
       aggressive split → NaN/insufficient-fold fail is a documented outcome,
       sparse-preset precedent in incident 28).
```

### Current Codebase tree (relevant subset)

```bash
app/
├── core/config.py                      # forecast_enable_* flags (118-120)
├── shared/model_taxonomy.py            # ModelFamily + _MODEL_FAMILY_MAP (11 types)
└── features/
    ├── demo/
    │   ├── models.py                   # ShowcaseWorkspace (89 lines)
    │   ├── schemas.py                  # DemoRunRequest / StepEvent / Workspace* (213)
    │   ├── pipeline.py                 # orchestrator + steps (2771)
    │   ├── workspace.py                # create/finalize/list/get/delete helpers
    │   ├── routes.py                   # POST /demo/run, WS /demo/stream, workspaces CRUD
    │   ├── service.py                  # run lock + sync/stream wrappers
    │   └── tests/                      # test_{schemas,pipeline,workspace,models,routes}.py
    ├── forecasting/{schemas,routes,models}.py   # TrainRequest, flag gates
    ├── backtesting/schemas.py          # SplitConfig / BacktestConfig
    └── model_selection/
        ├── capabilities.py             # build_model_catalog (pure)
        ├── service.py                  # get_model_catalog pass-through
        ├── schemas.py                  # CandidateModelInfo / ModelCatalogResponse
        └── routes.py                   # GET /model-selection/models
alembic/versions/                       # head TODAY = 324a2fa37fcc; E1 #407 adds one on top
frontend/src/
├── pages/showcase.tsx                  # controls card + start frame + load/replay
├── hooks/{use-demo-pipeline,use-model-selection,use-workspaces}.ts
├── components/demo/                    # ScenarioPicker, WorkspacePanel, … (+ tests)
├── components/champion-selector/       # candidate-model-picker, backtest-settings-form, split-config
└── types/api.ts                        # DemoRunRequest, WorkspaceListItem, CandidateModelInfo
```

### Desired Codebase tree (files added/changed)

```bash
app/shared/model_taxonomy.py                          # MODIFY: + KNOWN_MODEL_TYPES frozenset
app/shared/tests/test_model_taxonomy.py               # MODIFY (or create if missing): drift-lock test
app/features/demo/schemas.py                          # MODIFY: + DemoBacktestConfig; DemoRunRequest fields; WorkspaceListItem.run_config
app/features/demo/models.py                           # MODIFY: + run_config JSONB column
alembic/versions/<rev>_add_showcase_workspace_run_config.py   # CREATE: add/drop run_config
app/features/demo/workspace.py                        # MODIFY: create_workspace records run_config
app/features/demo/pipeline.py                         # MODIFY: ResolvedRunConfig, ctx, steps, winner metric, echo
app/features/model_selection/schemas.py               # MODIFY: CandidateModelInfo.enabled
app/features/model_selection/service.py               # MODIFY: enabled settings-overlay
app/features/model_selection/tests/test_capabilities.py  # MODIFY: overlay unit tests (patched settings)
app/features/demo/tests/test_schemas.py               # MODIFY: new-field + legacy-frame + JSON-path tests
app/features/demo/tests/test_pipeline.py              # MODIFY: selection/flag/split/metric/echo tests
app/features/demo/tests/test_workspace.py             # MODIFY: run_config persistence (integration)
app/features/demo/tests/test_models.py                # MODIFY: column roundtrip
frontend/src/types/api.ts                             # MODIFY: DemoBacktestConfig, DemoRunRequest, WorkspaceListItem, CandidateModelInfo.enabled
frontend/src/components/demo/run-config-utils.ts      # CREATE: defaults, isDefault*, buildTrainPlan, windowDays
frontend/src/components/demo/run-config-utils.test.ts # CREATE
frontend/src/components/demo/DemoBacktestSettingsForm.tsx       # CREATE (mirror champion form)
frontend/src/components/demo/DemoBacktestSettingsForm.test.tsx  # CREATE
frontend/src/components/demo/RunConfigPanel.tsx       # CREATE: collapsible section composing picker+form+preview
frontend/src/components/demo/RunConfigPanel.test.tsx  # CREATE
frontend/src/pages/showcase.tsx                       # MODIFY: state + dirty-rule + load/replay + panel mount
frontend/src/components/demo/WorkspacePanel.tsx       # MODIFY: config summary line
docs/_base/{API_CONTRACTS,DOMAIN_MODEL,RUNBOOKS}.md   # MODIFY: additive notes
```

### Design Decisions (locked — do not re-litigate during implementation)

```text
D1 — run_config is a DEDICATED nullable JSONB COLUMN, not an E1 story slot.
     E1 (#407) defines six slots and assigns writers for all of them to E3/E5/
     "later epics" — none is a run-config slot. The model set + backtest params
     are REPLAY INPUTS (same class as the existing seed/scenario/reset/skip_seed
     columns, models.py:65-69), not run-story output. So: one additive column
     `run_config JSONB NULL`, written by create_workspace at insert time,
     consumed by Load/Replay. config_schema_version is NOT bumped — E1 defines
     it as the STORY-SLOT schema marker; run_config presence is detectable by
     NULL-check and carries its own documented shape in DOMAIN_MODEL.md.
     NOTE: the E1 PRP (~line 230) loosely names "E4 #410 run-config echo" as a
     candidate writer for job_ids/phase_summaries — this PRP supersedes that
     phrasing: neither slot is run-config-shaped; job_ids/phase_summaries
     writing stays with the later parallel epics (E2 #408 / E5 #411).

D2 — E1 #407 MUST merge before this epic's migration is authored.
     E4's migration down_revision = the head AT IMPLEMENTATION TIME (E1's
     revision). Discover with `uv run alembic heads` — do NOT hardcode
     324a2fa37fcc (that is today's pre-E1 head).

D3 — Flag exposure rides the EXISTING catalog endpoint.
     CandidateModelInfo gains `enabled: bool = True`; the model_selection
     SERVICE overlays get_settings() (lightgbm→forecast_enable_lightgbm,
     xgboost→forecast_enable_xgboost, random_forest→forecast_enable_random_forest,
     everything else True). capabilities.build_model_catalog stays pure/static
     (its module docstring is a contract). No new /config endpoint.

D4 — Selection semantics in step_backtest:
     • train_model_types is None → BOTH branches byte-identical to today
       (SHOWCASE_RICH single call include_baselines=True; legacy per-model loop).
     • train_model_types provided → ONE unified per-model loop over
       selection ∪ ({prophet_like} when scenario==SHOWCASE_RICH), each call
       include_baselines=False; bucketed_aggregated_metrics captured from the
       prophet_like call's main_model_results when present. prophet_like is
       appended because v2_train trains/registers it unconditionally on
       SHOWCASE_RICH — it must stay in the competition or the V2 story breaks.

D5 — Winner metric: Literal["wape","mae","rmse"], default "wape", all
     lower-is-better; _select_winner(results, metric=…) skips missing/NaN.
     (smape/bias deliberately excluded — issue #410 names WAPE/MAE/RMSE.)

D6 — Flag enforcement is fail-fast in step_train (clear detail naming the
     flag), NOT in the Pydantic schema. Settings reads inside schemas caused
     the documented ".env-bleed" test incidents (RUNBOOKS § Settings tests);
     schemas validate only against the static KNOWN_MODEL_TYPES allow-list.

D7 — Dirty-only start-frame inclusion: showcase.tsx omits train_model_types /
     backtest keys when they equal the defaults (legacy trio + default split).
     Untouched UI ⇒ byte-identical legacy frame (umbrella criterion).

D8 — The configured horizon drives ONLY the modeling steps: step_train /
     step_v2_train train-tail reservation and step_backtest split_config.
     Planning/scenario steps keep DEMO_HORIZON (out of scope; document).
```

### Known Gotchas & Library Quirks

```python
# VERIFIED 2026-06-12 (re-run these on library/schema upgrades):
#
# 1. ALL 11 ModelConfig union members validate from a minimal {"model_type": X}:
#    uv run python -c "
#    from pydantic import TypeAdapter
#    from app.features.forecasting.schemas import TrainRequest
#    ta = TypeAdapter(TrainRequest.model_fields['config'].annotation)
#    [ta.validate_python({'model_type': t}) for t in (
#      'naive','seasonal_naive','moving_average','weighted_moving_average',
#      'seasonal_average','trend_regression_baseline','regression',
#      'prophet_like','lightgbm','xgboost','random_forest')]"
#    → _model_config_payload can fall back to {"model_type": t} for new types.
#    KEEP the explicit seasonal_naive(season_length=7)/moving_average(window_size=7)
#    branches — they match schema defaults but are load-bearing for config_hash
#    stability of existing registry rows.
#
# 2. "rmse" IS in aggregated_metrics (backtesting/metrics.py:349, PRP-36) —
#    alongside mae/smape/wape/bias. Do not invent other keys.
#
# 3. forecast_enable_{lightgbm,xgboost,random_forest} all default False
#    (app/core/config.py:118-120). lightgbm/xgboost are gated at the train
#    ROUTE (BadRequestError 400, routes.py:76-86); random_forest only deep in
#    the model factory (models.py:1761) → without the D6 pre-check a
#    random_forest request fails uglier. Also: flag ON but extra NOT installed
#    still ImportErrors (catalog requires_extra badge covers the UI hint).
#
# 4. Pydantic strict mode: ConfigDict(strict=True) on DemoRunRequest is fine
#    for the new fields — list[str] and a nested BaseModel validated from a
#    JSON dict are allowed under strict (strict forbids primitive coercion,
#    not dict→model validation). STILL add the JSON-path test
#    (Model.model_validate({...nested dict...})) per the repo strict-mode
#    policy (docs/_base/SECURITY.md, test_strict_mode_policy.py precedent).
#    All new fields are JSON-native → no Field(strict=False) needed anywhere.
#
# 5. Demo windows are finite: demo_minimal/sparse = 92d, holiday_rush = 92d
#    pinned, others = 180d (pipeline.py:513-538 _SCENARIO_SEED_PROFILE). An aggressive
#    split (e.g. h=28, n_splits=5, min_train=60) CANNOT fit → backtest NaN /
#    splitter error → step fail. This is a DOCUMENTED OUTCOME (same policy as
#    the sparse preset's expected-fail, RUNBOOKS incident 28) — the backend
#    must NOT silently clamp; the frontend shows the soft warning.
#
# 6. Feature-aware models (regression/prophet_like/…) train fine through
#    POST /forecasting/train with V1 defaults (feature_frame_version=1) — the
#    service builds the feature frame internally. Do NOT set
#    feature_frame_version=2 in step_train; V2 stays step_v2_train's job.
#    Expect noticeably longer wall-clock when selected (no budget gate change).
#
# 7. step_register reuses _model_config_payload(winner) and the winner's
#    train_results model_path — both work unchanged for any selected winner.
#    BUT registry _find_duplicate accumulation across repeated identical runs
#    is a known trap (RUNBOOKS showcase incident 2) — unchanged risk profile,
#    just more reachable configs now. No action; aware.
#
# 8. The demo slice may NOT import app/features/model_selection (vertical-slice
#    rule). The model allow-list source is app/shared/model_taxonomy.py.
#    Add KNOWN_MODEL_TYPES there + a drift-lock test asserting it equals
#    _MODEL_FAMILY_MAP.keys() (precedent: forecasting's
#    test_model_family_map_covers_every_known_model_type).
#
# 9. capabilities.build_model_catalog is PURE by contract (docstring: "No DB,
#    no I/O… deterministic and unit-tested directly"). The enabled overlay
#    belongs in ModelSelectionService.get_model_catalog (D3) via
#    item.model_copy(update={"enabled": …}).
#
# 10. WS error path: a ValidationError on the start frame becomes ONE error
#     StepEvent then close (routes.py:188-191) — new-field validation failures
#     surface there for free; assert it in test_routes.py.
#
# 11. Repo quirks: mixed CRLF/LF — check `git diff --stat` for whole-file
#     noise before committing. `pnpm tsc --noEmit` is VACUOUS (solution-style
#     tsconfig) — rely on `pnpm lint` + `pnpm test --run` + the real `tsc -b`
#     only informationally (it has pre-existing failures on dev). A stale
#     uvicorn can squat :8123 during Level 3/4 — check `ps etime` first.
#     NEVER `docker compose down -v` (kills the Ollama models volume).
```

## Implementation Blueprint

### Data models and structure

```python
# ── app/shared/model_taxonomy.py (additive) ──────────────────────────────────
KNOWN_MODEL_TYPES: frozenset[str] = frozenset(_MODEL_FAMILY_MAP)
# Public allow-list for request validation across slices. Drift-locked by test.

# ── app/features/demo/schemas.py (additive) ──────────────────────────────────
class DemoBacktestConfig(BaseModel):
    """Backtest knobs for the showcase pipeline (E4 #410).

    Bounds MIRROR app/features/backtesting/schemas.py:SplitConfig exactly —
    the pipeline forwards them verbatim into POST /backtesting/run.
    """
    model_config = ConfigDict(strict=True)

    horizon: int = Field(default=14, ge=1, le=90)
    strategy: Literal["expanding", "sliding"] = "expanding"
    n_splits: int = Field(default=3, ge=2, le=20)        # demo default 3, NOT SplitConfig's 5
    min_train_size: int = Field(default=30, ge=7)
    gap: int = Field(default=0, ge=0, le=30)
    metric: Literal["wape", "mae", "rmse"] = "wape"      # D5

    @model_validator(mode="after")
    def _gap_lt_horizon(self) -> DemoBacktestConfig:
        if self.gap >= self.horizon:
            raise ValueError(f"horizon ({self.horizon}) must be greater than gap ({self.gap})")
        return self

class DemoRunRequest(BaseModel):
    ...existing fields unchanged...
    # E4 (#410): additive run-config. None → legacy DEMO_MODEL_TYPES +
    # legacy split constants, byte-identical behavior.
    train_model_types: list[str] | None = Field(default=None, min_length=1, max_length=10)
    backtest: DemoBacktestConfig | None = None

    @field_validator("train_model_types")
    @classmethod
    def _known_unique_models(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        unknown = [m for m in v if m not in KNOWN_MODEL_TYPES]
        if unknown:
            raise ValueError(f"Unknown model type(s): {unknown!r}. Valid: {sorted(KNOWN_MODEL_TYPES)}")
        if len(set(v)) != len(v):
            raise ValueError("train_model_types contains duplicates")
        return v

class WorkspaceListItem(BaseModel):
    ...existing...
    # E4 (#410): replay-input echo; None on default-config / pre-E4 rows.
    run_config: dict[str, Any] | None = Field(default=None)

# ── app/features/demo/models.py (additive column) ────────────────────────────
# E4 (#410) — replay-input column (NOT an E1 story slot, see PRP D1):
# {"train_model_types": [...], "backtest": {...}} via model_dump(mode="json");
# NULL when the run used defaults.
run_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

# ── app/features/demo/pipeline.py (resolved config) ──────────────────────────
@dataclass(frozen=True)
class ResolvedRunConfig:
    """req.train_model_types/backtest with legacy defaults filled in."""
    model_types: tuple[str, ...] = DEMO_MODEL_TYPES
    horizon: int = DEMO_HORIZON
    strategy: str = "expanding"
    n_splits: int = DEMO_BACKTEST_SPLITS
    min_train_size: int = DEMO_MIN_TRAIN_SIZE
    gap: int = 0
    metric: str = "wape"
    customized: bool = False     # True when the request carried either field

# DemoContext gains: run_config: ResolvedRunConfig = field(default_factory=ResolvedRunConfig)

# ── app/features/model_selection/schemas.py (additive) ───────────────────────
class CandidateModelInfo(BaseModel):
    ...existing...
    enabled: bool = True   # E4 #410 — forecast_enable_* overlay (service-set)
```

### Tasks (dependency-ordered)

```yaml
Task 0 — PRE-FLIGHT (read-only):
  - VERIFY E1 #407 is merged: `gh issue view 407 --json state` + `uv run alembic heads`
    (head must be E1's revision, NOT 324a2fa37fcc). If E1 is not merged: STOP —
    this epic is Parallel-after-Foundation.
  - RE-RUN the three verification commands in Known Gotchas 1-3.
  - READ: PRPs/PRP-showcase-completion-E1-metadata-provenance-backbone.md (slot
    contract), pipeline.py:40-90/440-470/660-840, schemas.py (demo), showcase.tsx.

Task 1 — shared taxonomy allow-list:
  MODIFY app/shared/model_taxonomy.py:
    - ADD `KNOWN_MODEL_TYPES: frozenset[str] = frozenset(_MODEL_FAMILY_MAP)` below the map,
      with a docstring naming it the cross-slice request-validation allow-list.
  CREATE/EXTEND app/shared/tests/test_model_taxonomy.py:
    - test_known_model_types_matches_family_map (drift-lock: == set(_MODEL_FAMILY_MAP)).
    - test_known_model_types_contains_demo_trio.

Task 2 — demo schemas:
  MODIFY app/features/demo/schemas.py:
    - ADD DemoBacktestConfig (exact shape above; module placement after DemoRunRequest's
      dependencies — define BEFORE DemoRunRequest).
    - ADD train_model_types + backtest to DemoRunRequest (after workspace_name block,
      comment-tagged "E4 (#410)"); field_validator as above; import KNOWN_MODEL_TYPES
      from app.shared.model_taxonomy.
    - ADD run_config to WorkspaceListItem (detail inherits).
  EXTEND app/features/demo/tests/test_schemas.py (mirror existing naming):
    - test_demo_run_request_run_config_defaults_none
    - test_demo_run_request_accepts_model_selection_json_path  # model_validate on plain dicts
    - test_demo_run_request_rejects_unknown_model_type
    - test_demo_run_request_rejects_duplicate_model_types
    - test_demo_run_request_rejects_empty_and_oversized_selection  # [] and 11 entries
    - test_demo_backtest_config_defaults_and_bounds              # n_splits=1→err, gap>=horizon→err
    - test_demo_run_request_legacy_frame_still_validates         # EXTEND: assert new fields None
    - test_workspace_list_item_run_config_round_trip

Task 3 — ORM column + migration:
  MODIFY app/features/demo/models.py: run_config column (snippet above) inside the
    "Run configuration -- replay inputs" block; extend class docstring Attributes.
  CREATE alembic/versions/<rev>_add_showcase_workspace_run_config.py:
    - revision = autogen id; down_revision = OUTPUT OF `uv run alembic heads` (D2).
    - upgrade: op.add_column("showcase_workspace", sa.Column("run_config",
      postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    - downgrade: op.drop_column. MIRROR the E1 migration's structure/comments.
  EXTEND app/features/demo/tests/test_models.py: run_config JSONB roundtrip +
    NULL-default assertions (integration-marked, same pattern as existing).

Task 4 — workspace write:
  MODIFY app/features/demo/workspace.py:
    - ADD module-level `def _run_config_payload(req: DemoRunRequest) -> dict[str, Any] | None`:
      returns None when BOTH fields are None; else
      {"train_model_types": req.train_model_types,
       "backtest": req.backtest.model_dump(mode="json") if req.backtest else None}.
    - create_workspace: pass run_config=_run_config_payload(req) into ShowcaseWorkspace(...).
  EXTEND app/features/demo/tests/test_workspace.py:
    - test_create_workspace_records_run_config (custom req → JSONB persisted verbatim)
    - test_create_workspace_run_config_null_on_defaults

Task 5 — pipeline:
  MODIFY app/features/demo/pipeline.py:
    - ADD ResolvedRunConfig dataclass (near DemoContext) + a
      `def _resolve_run_config(req: DemoRunRequest) -> ResolvedRunConfig` helper.
    - DemoContext: ADD run_config field (default_factory=ResolvedRunConfig).
    - run_pipeline (2646): ctx = DemoContext(..., run_config=_resolve_run_config(req)).
    - _model_config_payload (271): ADD fallback branch
      `if model_type in KNOWN_MODEL_TYPES: return {"model_type": model_type}`
      BEFORE the raise; keep existing explicit branches untouched (Gotcha 1).
    - _select_winner (446): signature → (backtest_results, metric="wape");
      replace metrics.get("wape") with metrics.get(metric). ONE production call
      site (pipeline.py:820); existing tests keep passing via the default.
    - step_train (669): iterate ctx.run_config.model_types; train tail uses
      ctx.run_config.horizon; PREPEND fail-fast flag check (D6):
        settings = get_settings()
        _FLAG_BY_MODEL = {"lightgbm": settings.forecast_enable_lightgbm,
                          "xgboost": settings.forecast_enable_xgboost,
                          "random_forest": settings.forecast_enable_random_forest}
        disabled = [m for m in ctx.run_config.model_types if _FLAG_BY_MODEL.get(m) is False]
        if disabled: return ("fail", f"model(s) {disabled} requested but the matching "
                             "forecast_enable_* flag is off — enable it or deselect", {...})
      step data: ADD "requested_models": list(ctx.run_config.model_types).
    - step_backtest (731): implement D4. Extract one
      `_backtest_body(ctx, model_type, *, include_baselines)` helper building the
      request body from ctx.run_config (split_config: strategy/n_splits/
      min_train_size/gap/horizon). Branching:
        if not ctx.run_config.customized: → EXISTING two branches verbatim.
        else: loop over models = list(ctx.run_config.model_types)
              + ([SHOWCASE_V2_MODEL_TYPE] if scenario is SHOWCASE_RICH and not
                 already in selection else [])
              each include_baselines=False; capture bucketed metrics from the
              SHOWCASE_V2_MODEL_TYPE call when present.
      winner = _select_winner(ctx.backtest_results, ctx.run_config.metric)
      step data: ADD "metric": ctx.run_config.metric.
    - step_v2_train (1021): train tail uses ctx.run_config.horizon (D8).
    - run_pipeline pipeline_complete data (2758): ADD
      "run_config": ({"train_model_types": ..., "backtest": {...}} if customized else None).
  EXTEND app/features/demo/tests/test_pipeline.py (canned-_Client pattern):
    - test_resolve_run_config_defaults_and_custom
    - test_model_config_payload_minimal_fallback_for_all_known_types
    - test_select_winner_honors_metric (+ NaN/missing skip per metric)
    - test_step_train_trains_selected_models (capture POSTed bodies)
    - test_step_train_fails_fast_on_disabled_flag (patch get_settings)
    - test_step_backtest_sends_configured_split_config (assert body verbatim)
    - test_step_backtest_custom_selection_appends_prophet_like_on_showcase_rich
    - test_step_backtest_legacy_path_unchanged_when_not_customized
    - test_pipeline_complete_echoes_run_config (+ None on legacy run)

Task 6 — catalog enabled overlay:
  MODIFY app/features/model_selection/schemas.py: CandidateModelInfo.enabled: bool = True
    (comment: "E4 #410 — runtime forecast_enable_* overlay; service-set").
  MODIFY app/features/model_selection/service.py get_model_catalog:
    base = build_model_catalog(); settings = get_settings()
    flag = {"lightgbm": settings.forecast_enable_lightgbm,
            "xgboost": settings.forecast_enable_xgboost,
            "random_forest": settings.forecast_enable_random_forest}
    return ModelCatalogResponse(
        models=[m.model_copy(update={"enabled": flag.get(m.model_type, True)}) for m in base.models],
        default_candidate_model_types=base.default_candidate_model_types)
  EXTEND model_selection tests (mirror existing catalog tests):
    - test_catalog_enabled_false_when_flags_off (default settings)
    - test_catalog_enabled_true_when_flag_on (patched settings)
    - test_capabilities_stays_pure (build_model_catalog items default enabled=True)

Task 7 — frontend types:
  MODIFY frontend/src/types/api.ts:
    - ADD `export interface DemoBacktestConfig` (horizon/strategy/n_splits/
      min_train_size/gap + `metric: DemoRankingMetric`) and
      `export type DemoRankingMetric = 'wape' | 'mae' | 'rmse'`.
    - DemoRunRequest: + `train_model_types?: string[]`, `backtest?: DemoBacktestConfig`
      (comment-tagged E4 #410, mirror the E1 comment style at 783-787).
    - WorkspaceListItem: + `run_config?: Record<string, unknown> | null`.
    - CandidateModelInfo: + `enabled: boolean`.

Task 8 — frontend run-config building blocks:
  CREATE frontend/src/components/demo/run-config-utils.ts:
    - DEFAULT_TRAIN_MODELS = ['naive','seasonal_naive','moving_average']
    - DEFAULT_BACKTEST: DemoBacktestConfig = {horizon:14, strategy:'expanding',
      n_splits:3, min_train_size:30, gap:0, metric:'wape'}
    - isDefaultSelection(models) / isDefaultBacktest(cfg) (order-insensitive for models)
    - buildTrainPlan(models, scenario): {model_type, family?, v2?}[] — appends
      'prophet_like (V2)' marker on showcase_rich (skip if already selected)
    - windowDaysFor(scenario): 92 for demo_minimal/sparse/holiday_rush, 180 others
      (source of truth: pipeline.py _SCENARIO_SEED_PROFILE:513-538 — keep a sync comment)
    - splitFitWarning(cfg, scenario): string | null when
      min_train_size + n_splits*(horizon+gap) > windowDaysFor(scenario)
  CREATE run-config-utils.test.ts covering all of the above.
  CREATE frontend/src/components/demo/DemoBacktestSettingsForm.tsx:
    - MIRROR champion-selector/backtest-settings-form.tsx structure (Field
      helper, metric Select, Collapsible advanced knobs), DIFFERENCES:
      editable horizon Input (1-90), metrics wape/mae/rmse, REUSE
      splitConfigErrors from '@/components/champion-selector/split-config'
      (field names align), plus the splitFitWarning line (amber, non-blocking).
  CREATE DemoBacktestSettingsForm.test.tsx (mirror champion form's test).
  CREATE frontend/src/components/demo/RunConfigPanel.tsx:
    - Collapsible "Run configuration (advanced)" (collapsed default; chevron
      pattern from backtest-settings-form.tsx:125-137); props: scenario,
      disabled, selection+onSelectionChange, backtest+onBacktestChange.
    - Inside: CandidateModelPicker fed `{...catalog, models: catalog.models
      .filter(m => m.enabled)}` from useModelCatalog() (REUSE both);
      DemoBacktestSettingsForm; train-candidate preview (Badge chips from
      buildTrainPlan + count line).
    - "Reset to defaults" ghost button (restores DEFAULT_* values).
  CREATE RunConfigPanel.test.tsx:
    - opt-in models hidden when enabled=false (mock catalog)
    - preview appends prophet_like on showcase_rich only
    - reset restores defaults

Task 9 — showcase page wiring:
  MODIFY frontend/src/pages/showcase.tsx:
    - state: trainModels (DEFAULT_TRAIN_MODELS), backtestCfg (DEFAULT_BACKTEST).
    - handleRun: spread-only-when-dirty (D7), mirroring the existing
      preservation spread (149-154):
        ...(isDefaultSelection(trainModels) ? {} : {train_model_types: trainModels}),
        ...(isDefaultBacktest(backtestCfg) ? {} : {backtest: backtestCfg}),
    - handleLoadWorkspace: when ws.run_config present, repopulate
      trainModels/backtestCfg (fallback to defaults for missing keys);
      when absent, reset to defaults.
    - handleReplayWorkspace: forward ws.run_config fields verbatim into start()
      (same omit-when-null rule).
    - Mount <RunConfigPanel/> inside the controls CardContent below the
      flex-wrap control row (after line 363), disabled={isRunning}.
    - Run button disabled when trainModels.length === 0 (picker enforces ≥1
      anyway via toggle, belt-and-braces).
  MODIFY frontend/src/components/demo/WorkspacePanel.tsx:
    - rows with run_config render a compact summary line, e.g.
      "custom: 4 models · rmse · 5×h21" (Badge 'custom config' + muted text).
  EXTEND showcase/WorkspacePanel vitest specs:
    - untouched controls → start() called WITHOUT the new keys (dirty rule)
    - changed metric → start() includes backtest
    - replay of a run_config workspace forwards it verbatim
    - WorkspacePanel renders the custom-config badge only when run_config set.

Task 10 — docs sweep (docs(docs): … (#410) or fold into the feat commits):
  - docs/_base/API_CONTRACTS.md: POST /demo/run + WS /demo/stream rows — E4
    (#410) additive fields (shape, defaults, validation, dirty-rule note);
    GET /demo/workspaces run_config field; GET /model-selection/models
    `enabled` field.
  - docs/_base/DOMAIN_MODEL.md: showcase_workspace — run_config replay-input
    column + D1 rationale sentence ("NOT a story slot; config_schema_version
    unaffected").
  - docs/_base/RUNBOOKS.md § Showcase: two numbered incidents — (a) train step
    fails "forecast_enable_* flag is off"; (b) custom split too aggressive for
    the seeded window → backtest fail is a documented outcome (cite incident 28
    sparse precedent).
```

### Integration Points

```yaml
DATABASE:
  - migration: add nullable JSONB run_config to showcase_workspace
  - NO index (read path is by workspace_id; config is display/replay payload)
CONFIG:
  - none added; READS forecast_enable_* via get_settings() in step_train (D6)
    and model_selection service (D3). Never os.environ.
ROUTES:
  - none added. DemoRunRequest changes flow through POST /demo/run + WS
    /demo/stream automatically; catalog field flows through GET /model-selection/models.
FRONTEND DATA:
  - useModelCatalog() (existing) powers the picker; no new hooks.
COMMITS (every one references #410, no AI trailers):
  - feat(api,db): showcase run-config start-frame contract + workspace column (#410)
  - feat(api): honor run config in demo pipeline + catalog enabled overlay (#410)
  - feat(ui): showcase run-config panel, preview, and replay wiring (#410)
  - docs(docs): document showcase run-config contract (#410)
```

## Validation Loop

### Level 1 — Syntax & Style (after every task)

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/          # both --strict, both gate merge
cd frontend && pnpm lint                          # NOTE: pnpm tsc --noEmit is vacuous (memory)
```

### Level 2 — Unit tests (no DB)

```bash
uv run pytest app/shared/tests/ app/features/demo/tests/ app/features/model_selection/tests/ -v -m "not integration"
uv run pytest -v -m "not integration"             # full unit suite before push
cd frontend && pnpm test --run                    # vitest incl. new specs
```

### Level 3 — Integration (real Postgres; respect [[fresh-stack-gate-procedure]] — no `down -v`)

```bash
docker compose up -d && uv run alembic upgrade head
uv run alembic downgrade -1 && uv run alembic upgrade head   # migration round-trip
uv run pytest app/features/demo/tests/ -v -m integration
# Live contract probe (backend on :8123 — kill stale uvicorn first, check ps etime):
curl -s -X POST http://localhost:8123/demo/run -H 'Content-Type: application/json' -d '{
  "skip_seed": true, "preservation": "keep", "workspace_name": "e4-probe",
  "train_model_types": ["naive", "seasonal_average"],
  "backtest": {"horizon": 14, "n_splits": 3, "min_train_size": 30, "gap": 0,
               "strategy": "expanding", "metric": "rmse"}}' | python3 -m json.tool
# Expect: steps green, winner picked by rmse, data.run_config echoed, workspace_id set.
curl -s "http://localhost:8123/demo/workspaces?limit=1" | python3 -m json.tool   # run_config on the row
curl -s http://localhost:8123/model-selection/models | python3 -c "
import json,sys; [print(m['model_type'], m['enabled']) for m in json.load(sys.stdin)['models']]"
# Error paths:
curl -s -X POST http://localhost:8123/demo/run -d '{"train_model_types":["bogus"]}' \
  -H 'Content-Type: application/json' | head -c 300    # 422 problem+json
```

### Level 4 — Browser dogfood (MANDATORY — UI change; webapp-testing / agent-browser per ui-design.md; [[playwright-dogfood-needs-snap-chromium]] on this host)

```bash
# Backend :8123 + vite :5173 up, then drive /showcase:
# 1. Expand "Run configuration (advanced)" — opt-in models absent with default flags.
# 2. Select naive + seasonal_average, metric RMSE → preview shows 2 chips (+V2 only on showcase_rich).
# 3. Tick "Save as workspace", name e4-dogfood, Run → pipeline green, train card
#    shows the 2 requested models, summary winner consistent with RMSE.
# 4. Saved-workspaces panel: row shows the custom-config badge; Load repopulates
#    the panel controls; Replay re-runs verbatim (watch the WS frame in devtools).
# 5. Run once with UNTOUCHED controls → WS start frame has NO new keys (devtools).
# Capture screenshots for the PR.
```

## Final Validation Checklist

- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run mypy app/ && uv run pyright app/` clean (strict)
- [ ] `uv run pytest -v -m "not integration"` green
- [ ] `uv run pytest -v -m integration` green on a fresh stack (reset first — [[integration-suite-shared-state-pollution]])
- [ ] Migration upgrade + downgrade + re-upgrade clean on fresh DB
- [ ] `cd frontend && pnpm lint && pnpm test --run` green
- [ ] Level-3 curl probes match expectations (incl. 422 path)
- [ ] Level-4 dogfood evidence captured (screenshots + WS frame byte-compat check)
- [ ] Legacy-frame byte-compat test extended and green (umbrella criterion)
- [ ] Docs updated (API_CONTRACTS, DOMAIN_MODEL, RUNBOOKS)
- [ ] `git diff --stat` shows no CRLF whole-file noise
- [ ] Commits `type(scope): … (#410)`, no AI trailers; PR into dev

## Anti-Patterns to Avoid

- ❌ Don't add mid-run / per-phase re-entry of any kind — explicitly DEFERRED scope (brainstorm Round 5); the single `asyncio.Lock` linear stream is preserved.
- ❌ Don't write run_config into an E1 story slot or bump `config_schema_version` (D1).
- ❌ Don't import `app/features/model_selection` (or any sibling slice) from the demo slice — allow-list lives in `app/shared/model_taxonomy.py`.
- ❌ Don't read settings inside Pydantic schemas (`.env`-bleed incident class) — flags are enforced in `step_train` and overlaid in the catalog service.
- ❌ Don't make `capabilities.build_model_catalog` impure — overlay in the service.
- ❌ Don't clamp/auto-fix an aggressive split server-side — fail honestly (sparse-preset policy precedent).
- ❌ Don't send the new start-frame keys when the controls are untouched — byte-compat is a frozen criterion.
- ❌ Don't hand-roll new UI primitives — reuse `CandidateModelPicker`, mirror `BacktestSettingsForm`, shadcn components only (`.claude/rules/shadcn-ui.md`).
- ❌ Don't weaken or touch `test_leakage.py`, merged migrations, or the champion-selector's existing behavior beyond the additive `enabled` field.

---

## Confidence Score: 8.5/10

One-pass implementation likelihood. **+** Every contract was read and runtime-verified today (minimal model-config payloads, rmse key, flag names/defaults, SplitConfig bounds, catalog purity, start-frame parse path); the additive-field, migration, and byte-compat patterns have three shipped precedents in this exact slice (PRP-38 scenario, E1 #390, E2 #391); the frontend reuses two existing, tested components. **−0.5** D4's unified-loop branch in `step_backtest` is the one genuinely new control-flow path (showcase_rich + custom selection interplay with bucketed metrics). **−0.5** Pre-flight dependency: E1 #407 must merge first and its final migration revision id is unknowable today (mitigated by the `alembic heads` instruction in Task 0/D2).
