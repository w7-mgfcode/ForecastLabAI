name: "PRP showcase-completion E7 — release gate: docs reconciliation + E1–E6 dogfood evidence matrix + regression/CI audit + release path + umbrella close-out"
description: |
  Issue #420 (epic E7 of umbrella #406, milestone showcase-workspace-completion).
  Release-gate epic: NO production code. Deliverables are (a) a docs
  reconciliation — verify docs/_base/{API_CONTRACTS,RUNBOOKS,DOMAIN_MODEL}.md
  reflect E1–E6 and fix the ONE stale line (DOMAIN_MODEL.md:79 still lists E6
  export as "not modeled yet"); (b) an executed dogfood evidence matrix across
  the E1–E6 *frontend* control surface on a fresh-DB stack, each action mapped
  to an umbrella success criterion; (c) a regression + CI-gate audit (the
  showcase_rich e2e tests + the #146/#324 replay guard + the legacy-frame
  byte-identical contract, all CI-covered — cite + targeted re-run); (d) the
  release path confirmed and the target version recorded (the dev→main cut is
  stop-and-ask, NOT autonomous); (e) evidence on #420, umbrella #406 success
  criteria ticked, #406 + #420 closed. If any dogfood check fails OUTSIDE the
  documented expected-outcome matrix, the gate STOPS and files a fix issue — it
  never fixes forward inside this epic.

---

## Goal

Close umbrella #406 (showcase workspace completion — the forecastlab control
story) on **proof, not per-epic merges**. E1 #407, E2 #408, E3 #409, E4 #410,
E5 #411, E6 #412 are all CLOSED and merged to `dev` (E6 in #419, merge commit
`0381edb`), but **none of the six is in a release** — `main` is still at
**v0.2.22**, which carries only the *prior* umbrella #389 (#390–#393). Nothing
has yet verified the six epics' *combined* live behavior across the new control
surface (lifecycle PATCH, safe replay, advanced seed config + scope, run-config,
HITL reject + story capture, export), the umbrella's eight success-criteria
checkboxes are 1/8 ticked (only E6's, ticked during E6 close-out), and one
`docs/_base/` line is stale.

1. **Docs reconciliation** — `API_CONTRACTS.md` + `RUNBOOKS.md` already document
   E1–E6 (audited 2026-06-13: complete). Fix the single stale line in
   `DOMAIN_MODEL.md:79` (E6 export bundles are SHIPPED, not "not modeled yet").
2. **Dogfood evidence matrix** — on a fresh-DB stack, exercise each E1–E6
   frontend control once and record the outcome, each mapped to an umbrella
   success criterion. The backend pipeline is CI-covered (see Task 1); the
   live gate's unique value is the *frontend* surface + the cross-epic combined
   behavior on a real browser.
3. **Regression + CI-gate audit** — cite the latest green `dev` CI run (all five
   gates incl. the showcase_rich e2e + replay regression run there) and re-run
   the load-bearing proofs locally: the legacy-frame contract test, the
   `test_demo_replay_same_config_twice` guard, the demo-slice units, and the
   frontend demo-component vitest.
4. **Release path** — confirm E1–E6 are release-ready on `dev`; record the
   target version (release-please will bump v0.2.22 → next on the dev→main
   merge). The actual cut is a separate **stop-and-ask** decision (release-please
   owns tagging) — this gate does NOT merge dev→main.
5. **Close-out** — evidence comment on #420; tick the 7 remaining #406
   success-criteria boxes (E6's is already ticked) with evidence; close #406;
   close #420 last.

**End state**: #406 and #420 CLOSED with linked evidence; `DOMAIN_MODEL.md:79`
corrected; this PRP file committed; E1–E6 confirmed release-ready with the
target version recorded for the maintainer's release decision.

## Why

- Every umbrella #406 success criterion is implemented but **only 1/8 is ticked
  with evidence**, and five of eight are only fully provable by live combined
  behavior (lineage + destructive-replay confirm; rename/archive/pin/search/
  multi-delete; seed-override + scope replay-verbatim; run-config echo; HITL
  reject + story capture on Showcase and /ops).
- E6 (#412) just merged; the six epics ship together as one user story but have
  never been exercised back-to-back on one stack. A gate proves the *seams*
  (e.g. a keep-run that sets seed overrides AND a custom run-config AND triggers
  an approval, then is replayed and exported).
- The umbrella deferred the close-out evidence + the final doc reconciliation to
  this gate (per its decomposition); without it #406 closes on faith.
- `main` is two umbrellas behind perception: operators reading the GitHub
  release list see only v0.2.22 (#389). E7 surfaces the unreleased-on-`dev`
  state and records the release path so the maintainer can cut it deliberately.

## What

A verification campaign plus a one-line docs fix. No `app/`, `frontend/`, or
`alembic/` change is in scope. Tracked changes: this PRP file +
`docs/_base/DOMAIN_MODEL.md` (one line), one branch
(`docs/showcase-completion-e7-gate`), one PR into `dev`.

### Success Criteria (mirror of #420 sub-tasks + the #406 criteria they close)

- [ ] Fresh-DB stack via **DROP/CREATE DATABASE** (NOT `down -v` — Known
      Gotchas) + `alembic upgrade b7c1d9e3f204` clean (the COMMITTED head — a
      bare `upgrade head` errors on the local two-head state; see Known
      Gotchas); a targeted downgrade→upgrade round-trip of the head-adjacent
      showcase migration (E4 run_config) proves "applies + downgrades cleanly"
      (#406 criterion 1).
- [ ] Latest `dev` CI run cited GREEN (all five gates; the showcase_rich e2e +
      replay regression run there); local re-run of the legacy-frame contract
      test + `test_demo_replay_same_config_twice` both pass (#406 criteria 8 + 2).
- [ ] **E1 dogfood**: a workspace renamed / annotated (notes+tags) via the Edit
      dialog, pinned, archived — each reflected in `GET /demo/workspaces/{id}`
      (#406 criterion 3).
- [ ] **E2 dogfood**: a `reset=true` workspace Replay opens the destructive-
      escalated confirm dialog (recorded-vs-sent diff) and only runs on confirm;
      a replayed row shows the lineage chain + replay badge and
      `replayed_from_workspace_id` set; search / tag-filter / sort / multi-select
      delete all work from the panel; the two-workspace compare page renders;
      a loaded workspace shows link-health markers (#406 criteria 2 + 3).
- [ ] **E3 dogfood**: a keep-run started with ≥2 seed-override knobs + an explicit
      focus pair persists both story slots (`GET /demo/workspaces/{id}` →
      `seed_overrides` + `user_scope`); Replay re-submits them verbatim and the
      new row carries identical slots (#406 criterion 4; backed by
      `test_demo_replay_preserves_seed_overrides_and_scope`).
- [ ] **E4 dogfood**: a keep-run started with a custom model set + backtest config
      records `run_config` on the row (the panel renders the "custom: …" badge);
      a default-config run leaves `run_config` null (#406 criterion 5).
- [ ] **E5 dogfood**: an approval is captured on a `showcase_rich` keep-run
      (auto-approve OR a live Reject if a cloud agent model is configured),
      surfaced in the loaded workspace's Run-story panel AND the `/ops` Approval
      History table; a Reject keeps the run GREEN and writes no `scenario_plan`
      (#406 criterion 6; backed by `test_run_demo_showcase_rich_full_epic`).
- [ ] **E6 dogfood**: Export on a saved row → `sha256sum -c checksums.sha256`
      passes (re-confirm; #406 criterion 7 already ticked).
- [ ] 8-preset run matrix executed/recorded against RUNBOOKS entry 28; outcomes
      conformant (no undocumented ❌).
- [ ] `DOMAIN_MODEL.md:79` corrected (export off the "not modeled yet" list;
      import/restore stays out); `git diff --stat` shows only intended lines.
- [ ] Five validation gates green on the docs branch + targeted frontend
      demo-component vitest green.
- [ ] Release path recorded (target version; dev→main is stop-and-ask).
- [ ] Evidence on #420; #406's 7 remaining success boxes ticked; #406 closed;
      #420 closed; docs PR open into `dev`.

## All Needed Context

### Documentation & References

```yaml
# ── The gate's contract ──────────────────────────────────────────────────────
- issue: "#420 — gh issue view 420"
  why: The epic's six sub-tasks this PRP encodes (docs sweep, dogfood matrix,
       regression audit, CI-gate audit, release path, umbrella close-out).

- issue: "#406 — gh issue view 406 --json body"
  why: "Umbrella. STATE (verified 2026-06-13): Decomposition E1–E6 ticked +
       E7 line wired to #420; Success-criteria 1/8 ticked (only the E6 'Export
       produces…' box). Tick the OTHER 7 with evidence; close with a close-out
       comment. E1–E6 = #407 #408 #409 #410 #411 #412, all CLOSED, merged to
       dev, UNRELEASED (main = v0.2.22 = prior umbrella #389)."

- file: PRPs/PRP-showcase-workspace-E5-release-gate.md
  why: "THE release-gate precedent this PRP mirrors directly (STOP rule, fresh-
       stack procedure, per-preset matrix, evidence format, close-out order).
       That gate closed the PRIOR umbrella #389; this one closes #406. Reuse
       its structure verbatim where it still applies; the deltas are: docs are
       already swept (verify + 1-line fix, not from-scratch), the dogfood centres
       on the E1–E6 frontend surface (backend is CI-covered), and there is a
       real release-path sub-task."

- file: PRPs/PRP-reliability-E6-release-gate.md
  why: "Second release-gate precedent (STOP rule + evidence + close-out order).
       Its 'docker compose down -v' fresh-stack step is SUPERSEDED — use the
       DROP/CREATE procedure in Known Gotchas."

# ── What E1–E6 shipped (the six PRPs — read the one a failing check touches) ──
- file: PRPs/PRP-showcase-completion-E1-metadata-provenance-backbone.md
  why: "E1 contract: showcase_workspace lifecycle/provenance columns + 6 JSONB
       story slots + PATCH /demo/workspaces/{id}. config_schema_version starts 1."
- file: PRPs/PRP-showcase-completion-E2-safe-replay-lifecycle.md
  why: "E2: destructive-replay confirm + diff, lineage, rename/archive/pin/tags,
       list search/filter/sort, multi-delete, compare, link-health probe."
- file: PRPs/PRP-showcase-completion-E3-seed-config-scope.md
  why: "E3: 7-knob SeederOverrides + user_scope; replay-verbatim slot contract."
- file: PRPs/PRP-showcase-completion-E4-run-config-phase-controls.md
  why: "E4: train_model_types + backtest (DemoBacktestConfig) → run_config column."
- file: PRPs/PRP-showcase-completion-E5-agent-rag-story-capture.md
  why: "E5: hitl-decision relay, approval_events/rag_events capture, Reject +
       10s window, /ops approval history, config_schema_version 1→2."
- file: PRPs/PRP-showcase-completion-E6-export-bundle.md
  why: "E6: POST /demo/workspaces/{id}/export + Export button + bundle layout."

# ── Frontend dogfood surface (the E1–E6 controls — file:line, verified 2026-06-13)
- file: frontend/src/pages/showcase.tsx
  why: "Core run controls: scenario card grid (ScenarioPicker), 'Re-seed first'
       checkbox (:345 → skip_seed=false), 'Reset database' (:363 → reset=true),
       Seed input (:383), 'Save as workspace' + name input (:398/:409), Run
       (:323) / Stop (:337). Dirty-only rule (:193-194): train_model_types /
       backtest omitted from the frame when equal to defaults (the byte-identical
       guard). SeedConfigPanel rendered only when reseed ticked (:432); ScopeSelector
       warns on reset (:446); WorkspaceArtifactsPanel link-health (:554)."
- file: frontend/src/components/demo/WorkspacePanel.tsx
  why: "Saved-workspaces panel. E1: pin (:379), Archive dropdown (:469), Edit
       details… → WorkspaceEditDialog. E2: search (:297), Show-archived (:306),
       Sort select (:312), tag chip filter (:324/:406), multi-select + Delete
       selected (:496), Compare → /showcase/compare (:517), replay/archived/
       pinned badges (:389-390). E6: Export button (:440), success toast (:251)."
- file: frontend/src/components/demo/ReplayConfirmDialog.tsx
  why: "E2 destructive-replay confirm. Recorded-vs-sent diff table (:56); the
       confirm button + warning escalate destructively when reset=true (:99-102).
       NO replay starts without this dialog."
- file: frontend/src/components/demo/WorkspaceLineageStrip.tsx
  why: "E2 lineage breadcrumb (:26); renders nothing when <2 entries (:31);
       '(original deleted)' for dangling ancestors."
- file: frontend/src/components/demo/WorkspaceEditDialog.tsx
  why: "E1 rename/notes/tags editor (:46); opened from the row 'Edit details…'."
- file: frontend/src/components/demo/SeedConfigPanel.tsx
  why: "E3 7-knob panel (:66/:91); window_days locks on holiday_rush (:109);
       risk warning at high sparsity/stockout. Only when Re-seed ticked."
- file: frontend/src/components/demo/ScopeSelector.tsx
  why: "E3 focus-pair selects (:40/:65/:90); 'Auto-discover' placeholders."
- file: frontend/src/components/demo/RunConfigPanel.tsx
  why: "E4 'Run configuration (advanced)' (:46/:82); CandidateModelPicker (:119,
       opt-in models only when forecast_enable_* on, filtered at :58-60);
       DemoBacktestSettingsForm; train-candidate preview (:137). 'custom: …'
       badge on the row via WorkspacePanel runConfigSummary."
- file: frontend/src/components/demo/demo-step-card.tsx
  why: "E5 HITL card: Approve (:417) + Reject (:425) + auto-approve countdown
       (:434, reads data.decision_window_s); rendered only when
       awaiting_approval && status='running' && action_id is str (:518-529).
       On this host the 2B agent often skips the tool → buttons may never appear
       (see Known Gotchas — acceptable; e2e test covers the path)."
- file: frontend/src/components/demo/WorkspaceStoryPanel.tsx
  why: "E5 Run-story panel on a loaded workspace (:74): approval history (:114),
       replay-reproduction markers (:95), knowledge/rag events (:152). Self-hides
       when no approval_events/rag_events/story_reproduction."
- file: frontend/src/pages/ops.tsx
  why: "E5 Approval History table (:101, useApprovalEvents) — flattened approvals
       across saved workspaces."

# ── Regression tests (CI-covered — cite + targeted re-run; verified 2026-06-13)
- file: tests/test_e2e_demo.py
  why: "@pytest.mark.integration, subprocess uvicorn :8124, real Postgres.
       test_demo_replay_same_config_twice (:561) — #146/#324 replay guard
       (reset=true; RESETS the shared DB — run ONLY after the dogfood, never
       concurrently). test_demo_replay_preserves_seed_overrides_and_scope (:618)
       — E3 replay-slot contract. test_run_demo_showcase_rich_full_epic (:410)
       — PRP-41 agent_hitl_flow + ops_snapshot (CI proof for E5 backend).
       test_run_demo_showcase_rich_e2e (:204) + _decision_portfolio (:295) —
       24-step pipeline. These make the backend pipeline CI-covered; the live
       dogfood need not re-prove it step-by-step."
- file: app/features/demo/tests/test_routes.py
  why: "test_demo_stream_websocket_legacy_frame_ignores_unknown_keys (:190) —
       THE legacy-frame byte-identical contract (#406 criterion 8). PATCH/DELETE/
       health/list integration tests (:696-834). Export route 404/409/200
       (:256-? via test_export.py)."
- file: app/features/demo/tests/test_workspace.py
  why: "Module-level @pytest.mark.integration. create/finalize + E3 slot
       persistence (:79/:97), E4 run_config (:110/:135), E5 story slots
       (:423/:439). The ORM-level proof behind the dogfood's curl assertions."
- file: app/features/demo/tests/test_export.py
  why: "E6 unit + integration (sha256/traversal/manifest + endpoint round-trip)."

# ── Doc-sweep targets ────────────────────────────────────────────────────────
- file: docs/_base/DOMAIN_MODEL.md
  why: "THE only stale line. Line 79: '**Out of scope (deliberately not modeled
       yet):** export bundles under `artifacts/showcase/<workspace>/` (E6 #412)
       and per-phase interactive configuration …'. E6 SHIPPED export — drop it
       from the out-of-scope clause, keep import/restore + per-phase config out.
       Mirror the RUNBOOKS.md:168 phrasing E6 already landed ('bundle import/
       restore … E6 ships export only')."
- file: docs/_base/API_CONTRACTS.md
  why: "READ-ONLY — audited complete for E1–E6 (the /demo + /seeder rows carry
       every epic's additive fields incl. the E6 export row at line 68). Cross-
       check; do NOT edit."
- file: docs/_base/RUNBOOKS.md
  why: "READ-ONLY — audited complete (Showcase-workspace section lines 154-168
       covers E1–E6; out-of-scope line 168 already correct after E6). Cross-check."

# ── Close-out mechanics ──────────────────────────────────────────────────────
- file: .claude/rules/umbrella-issue.md
  why: "Write discipline for gh mutations: echo each command → idempotent check
       → confirm. Applies to the #406 body edit + closes. Fetch the LIVE body;
       never retype it."
- file: .claude/rules/output-formatting.md
  why: "Evidence-comment format: emoji status indicators, box separators, ≤40 lines."
- doc: "Release flow — docs/_base/PIPELINE_CONTRACT.md + .claude/rules/versioning.md"
  why: "dev→main → release-please opens a Release PR → merge tags vX.Y.Z. Pre-1.0
       feat: → PATCH bump (v0.2.22 → v0.2.23). The merge-commit-subject trap
       (RUNBOOKS 'release-please skipped the bump'): use the GitHub web UI or a
       non-conventional --subject. This gate RECORDS the path; it does NOT cut."
```

### Current Codebase tree (verification-relevant subset)

```bash
app/features/demo/                         # the slice E1–E6 extended
  ├── models.py        # showcase_workspace ORM (E1 columns + story slots)
  ├── routes.py        # /demo/workspaces[,/{id}[,/health,/export]], PATCH, hitl-decision, approval-events
  ├── workspace.py     # create/finalize/list/get/update/delete (slot writers)
  ├── export.py        # E6 bundle writer
  └── tests/           # test_routes, test_workspace, test_export, test_link_health, test_pipeline, test_hitl, test_schemas
tests/test_e2e_demo.py                     # showcase_rich e2e + replay guard (CI)
frontend/src/pages/showcase.tsx            # dogfood entry point
frontend/src/pages/ops.tsx                 # E5 approval history
frontend/src/components/demo/              # E1–E6 controls + *.test.tsx (17 component tests)
docs/_base/DOMAIN_MODEL.md                 # sweep target (1 stale line :79)
docs/_base/API_CONTRACTS.md               # audited complete (read-only)
docs/_base/RUNBOOKS.md                     # audited complete (read-only)
docker-compose.yml                         # base Postgres+pgvector
docker-compose.gpu.yml                     # GPU overlay for ollama (REQUIRED for the rag legs)
docker-compose.lan.yml                     # untracked local overlay — do NOT use here
```

### Desired Codebase tree (files added/modified)

```bash
PRPs/PRP-showcase-completion-E7-release-gate.md   # ADD — this file
docs/_base/DOMAIN_MODEL.md                        # MOD — fix the one stale line (:79)
# No app/, frontend/, or alembic/ change is in scope.
```

### Known Gotchas & Environment Quirks

```python
# ── STOP RULE (governs the whole epic) ───────────────────────────────────────
# If ANY dogfood check deviates from the expected-outcome matrix below: capture
# evidence (response body / screenshot / step table), open a NEW fix issue
# referencing #406 + #420, comment the failure on #420, and STOP the close-out.
# The docs fix (Task 4) + the PR still land — they document already-shipped
# semantics and are independent of dogfood outcomes. A DOCUMENTED expected-skip
# (agent_hitl_flow ⏭️, rag legs ⏭️ when the provider is down, sparse fail) is NOT
# a deviation.

# ── Fresh stack — DROP/CREATE, NEVER `down -v` (memory: fresh-stack-gate-procedure)
# `down -v` removes ALL named volumes incl. forecastlab_ollama_models (pulled
# gemma4/qwen3 models, expensive to rebuild). Fresh-DB equivalent:
#   docker compose --profile gpu down --remove-orphans
#   docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile gpu up -d
#   docker compose exec -T postgres psql -U forecastlab -d postgres \
#     -c "DROP DATABASE IF EXISTS forecastlab WITH (FORCE);" \
#     -c "CREATE DATABASE forecastlab OWNER forecastlab;"
#   uv run alembic upgrade b7c1d9e3f204   # cold-boot proof to the COMMITTED head
# MULTI-HEAD BLOCKER (verified 2026-06-13): `alembic heads` returns TWO heads —
# b7c1d9e3f204 (committed E4 run_config) AND the untracked, LOCAL-ONLY
# a2b3c4d5e6f7_rag_embedding_dim_2560_qwen3 (branches off old rev c1d2e3f40512).
# So a BARE `alembic upgrade head` ERRORS "Multiple head revisions are present".
# Before upgrading, EITHER move the untracked qwen3 file out of alembic/versions/
# (then `alembic upgrade head` is unambiguous), OR target the committed head
# explicitly: `uv run alembic upgrade b7c1d9e3f204`. (CI never hits this — the
# qwen3 file is untracked, so CI's migration-check sees one head.)
# DOWNGRADE proof (#406 criterion 1 — "applies + downgrades cleanly"): after the
# clean upgrade, round-trip the head-adjacent showcase migration once:
#   uv run alembic downgrade -1 && uv run alembic upgrade b7c1d9e3f204   # both exit 0
# (The head-adjacent COMMITTED showcase migration is E4 b7c1d9e3f204 = run_config,
#  down_revision d45cf40dfe47 = the E1 #407 metadata/slots migration. `downgrade
#  -1` reverses E4 run_config — a clean round-trip that satisfies criterion 1;
#  to also exercise the E1 column/slot down-path, downgrade a second step.)
# GOTCHA (memory: rag-runtime-config-and-corpus-state): that untracked qwen3
# migration is LOCAL-ONLY — the committed tree's head yields the 1536-dim
# (OpenAI) embedding column. If .env has RAG_EMBEDDING_PROVIDER=ollama +
# qwen3-embedding:4b (2560-d), the showcase_rich knowledge legs dim-mismatch
# unless that local migration is applied too (keep it in alembic/versions/ and
# `alembic upgrade head` once BOTH heads are intended), OR accept the rag legs
# ⏭️-skipping (documented-acceptable RUNBOOKS entries 20-22) — both conformant.
# GOTCHA: WITHOUT the gpu overlay ollama runs CPU-only and rag_index_subset can
# 502 on the cold embedder load. Verify `docker exec forecastlab-ollama nvidia-smi`,
# then WARM the embedder before any showcase_rich run:
#   curl -s localhost:11434/api/embed -d '{"model":"<configured-embed-model>","input":"warmup"}'
# GOTCHA: fresh DB wipes app_config overrides — agent model reverts to .env
# (AGENT_DEFAULT_MODEL on this host is an ollama model). Re-check GET /config/ai.
# GOTCHA (memory: dogfood-stale-uvicorn-port-8123): a stale uvicorn from a prior
# session can hold :8123 → curl hits OLD code. `lsof -iTCP:8123 -sTCP:LISTEN`,
# kill stale PIDs first. Run the backend as LOCAL uvicorn from the REPO ROOT
# (host-filesystem artifacts + docs/ for the rag legs; the compose backend image
# lacks docs/, which is why docker-compose.lan.yml exists — do NOT use it here).
# pnpm 11 depsStatusCheck can stall `pnpm dev` → start Vite directly:
#   cd frontend && ./node_modules/.bin/vite --host 0.0.0.0
# GOTCHA (memory: seeder-does-not-reset-id-sequences): the seeder does NOT reset
# store/product id sequences. After a reset+reseed the focus-pair ids change —
# discover live ids via GET /dimensions/stores + /dimensions/products before
# entering an E3 focus pair; never assume id=1.

# ── E5 live-Reject caveat (memory: gemma4-agent-local-deployment) ─────────────
# AGENT_DEFAULT_MODEL on this host is a 2B ollama model that RELIABLY skips the
# save_scenario tool → the HITL Approve/Reject buttons may never render (step
# ⏭️ 'agent did not trigger save_scenario' — RUNBOOKS entry 25, acceptable).
# To live-dogfood the Reject BUTTON: PATCH /config/ai to a cloud agent model
# (e.g. anthropic:claude-… or openai:gpt-…; keys present in .env per
# CLAUDE.local.md) — no restart needed — so the agent reliably calls
# save_scenario and the 10s window opens; then click Reject and assert the run
# stays GREEN with NO new scenario_plan row. If you keep the ollama model, the
# E5 criterion rests on (a) test_run_demo_showcase_rich_full_epic (CI), (b) the
# unit tests test_step_agent_hitl_manual_approval / _auto_approved, and (c) the
# /ops Approval History + Run-story panel rendering an AUTO-APPROVED capture from
# a prior keep-run. Record which path you took. Revert the model override after.

# ── Per-preset expected-outcome matrix (RUNBOOKS entry 28 — the dogfood spec) ─
# Every run: 'Re-seed first' TICKED. seed=42.
#   demo_minimal / retail_standard / high_variance / stockout_heavy /
#   new_launches  → 11 steps GREEN.
#   sparse        → 11 steps GREEN **or documented FAIL** at features/backtest
#                   (50% missing grains / all-NaN WAPE gate) — the card carries
#                   the expected-skip badge; either outcome is matrix-conformant.
#   holiday_rush  → tick **Reset database** TOO (pinned 2024-10-01..12-31 window;
#                   re-seed without reset ADDS rows → union range). 11 steps GREEN.
#   showcase_rich → 24 steps / 10 phases; tick **Reset database** TOO. Acceptable
#                   non-green (RUNBOOKS 9-26, 23-26): agent_hitl_flow ⏭️ (2B agent),
#                   rag_index_subset / rag_retrieve_probe ⏭️ (provider down/dim-
#                   mismatch), verify ⏭️ (V2 prophet_like winner), batch_preset ⚠️
#                   (90s poll), ops_snapshot ⚠️. ANY other ❌/⏭️ = deviation → STOP.
# Only ONE pipeline at a time (module asyncio.Lock; 2nd start → 409 / one error
# event; Stop releases in ~5s). The 8-preset run matrix can be LIGHTER than the
# #401 gate's (the pipeline is CI-covered) — one representative GREEN per preset
# class + the two keep-runs (demo_minimal, showcase_rich) is sufficient evidence.

# ── Tests / gates (memory: integration-suite-shared-state-pollution) ─────────
# NEVER run the full `-m integration` suite as a gate — known shared-state
# pollution. Run TARGETED only. test_demo_replay_same_config_twice RESETS the
# shared DB (reset=true on :8124) — run it ONLY after the dogfood matrix, never
# concurrently with a :8123 run.
# memory: frontend-tsc-noemit-gate-vacuous — `pnpm tsc --noEmit` checks 0 files;
# `tsc -b` has PRE-EXISTING dev failures (baseline 30 at gate time). Frontend
# evidence = `pnpm lint` (0 errors) + targeted vitest, NOT a clean tsc.
# memory: playwright-dogfood-snap-chromium — Playwright MCP + `playwright install`
# FAIL on this host; use native Python Playwright with
# executable_path="/snap/bin/chromium" (symlink verified) or the agent-browser
# skill. localhost:5173 is fine.

# ── Docs fix (memory: repo-line-endings-crlf) ────────────────────────────────
# DOMAIN_MODEL.md is CRLF-dominant/mixed. Editing it can flip an unrelated LF
# block to CRLF → a whole-file noise diff. After the one-line edit, run
# `git diff --stat docs/_base/DOMAIN_MODEL.md`; if it dwarfs ~2 changed lines,
# restore from HEAD and re-apply byte-precisely (`git show HEAD:<file>` + Python
# binary-mode replace preserving the line's CRLF terminator). The single target
# line (:79) is CRLF — keep it CRLF.

# ── Third-party API claims ───────────────────────────────────────────────────
# None. This PRP cites no new library attributes; every verification command is
# first-party (curl / pytest / grep / gh / sha256sum). (Policy per #258.)

# ── GitHub close-out (write discipline: .claude/rules/umbrella-issue.md) ──────
# #406 body edit: fetch with `gh issue view 406 --json body`, tick the 7
# remaining Success-criteria boxes (leave the already-ticked E6 'Export
# produces…' box). Decomposition E1–E7 already correct (done during E6 + E7
# scaffold). Preserve everything else byte-identical; edit the FETCHED markdown,
# never retype it. Close order: PR opened → evidence on #420 → tick #406 →
# close #406 (comment links the #420 evidence) → close #420 last. The PR needs
# 1 review + CI — opening it suffices to proceed (reliability-E6 precedent).
# The dev→main RELEASE cut is a SEPARATE stop-and-ask — do NOT `gh pr merge`
# dev→main inside this gate.
```

## Implementation Blueprint

### Data models and structure

None. Zero schemas, zero migrations, zero source changes. The only authored
content is one corrected sentence in `DOMAIN_MODEL.md` (Task 4) and this PRP file.

### List of tasks in execution order

```yaml
Task 0 — Preflight:
  VERIFY branch: git switch dev && git pull --ff-only → clean, up to date.
  VERIFY no stale server: lsof -iTCP:8123 -sTCP:LISTEN → kill stale PIDs.
  VERIFY chromium: ls -la /snap/bin/chromium (else plan agent-browser skill).
  VERIFY epics CLOSED: gh issue view 407 408 409 410 411 412 → all CLOSED.
  RECORD: git rev-parse HEAD → the SHA all evidence refers to (expect the #419
    merge 0381edb or later).

Task 1 — Regression + CI-gate audit (committed proofs; do this BEFORE the live
         stack so a red gate stops the gate early):
  CITE CI: gh run list --workflow ci.yml --branch dev --limit 1 --json
    databaseId,conclusion,headSha → MUST be success on the current dev HEAD
    (27460856895 / 0381edb2 at authoring time; re-cite the latest). This run
    is the green proof of all five gates INCLUDING the showcase_rich e2e
    (test_run_demo_showcase_rich_* ) + the replay guard (they are -m integration
    and run in CI's test job).
  RUN the five gates locally on dev (fast, no live stack):
    uv run ruff check . && uv run ruff format --check .
    uv run mypy app/ && uv run pyright app/
    uv run pytest -v -m "not integration"          # ~2112 pass
  RUN the load-bearing targeted proofs:
    uv run pytest "app/features/demo/tests/test_routes.py::test_demo_stream_websocket_legacy_frame_ignores_unknown_keys" -v   # legacy-frame contract
    cd frontend && ./node_modules/.bin/eslint src && ./node_modules/.bin/vitest run src/components/demo/ && cd ..   # frontend demo components
  DEFER to Task 6 (resets the DB): test_demo_replay_same_config_twice.
  ON any red gate on an untouched surface → STOP RULE (regression).

Task 2 — Fresh-DB stack (memory-corrected; NEVER down -v):
  RUN: docker compose --profile gpu down --remove-orphans
  RUN: docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile gpu up -d
  VERIFY: docker exec forecastlab-ollama nvidia-smi → GPU visible (else rag legs ⏭️)
  RUN: docker compose exec -T postgres psql -U forecastlab -d postgres \
         -c "DROP DATABASE IF EXISTS forecastlab WITH (FORCE);" \
         -c "CREATE DATABASE forecastlab OWNER forecastlab;"
  RUN: uv run alembic upgrade b7c1d9e3f204   # MUST exit 0 (COMMITTED head; a bare
       `upgrade head` errors "Multiple head revisions" while the untracked qwen3
       migration is present — see the MULTI-HEAD BLOCKER in Known Gotchas)
  RUN: uv run alembic downgrade -1 && uv run alembic upgrade b7c1d9e3f204   # round-trip
       (the "applies + downgrades cleanly" proof for #406 criterion 1 — reverses
       the head-adjacent E4 run_config migration and re-applies it)
  (Optional rag path) To run the showcase_rich knowledge legs against ollama
       qwen3 embeddings, keep the local qwen3 migration in place and resolve
       BOTH heads (`alembic upgrade head` is then the two-head merge); else
       accept rag-leg ⏭️.
  WARM embedder: curl -s localhost:11434/api/embed \
       -d '{"model":"<configured-embed-model>","input":"warmup"}'
  START backend: uv run uvicorn app.main:app --port 8123  (background, repo root,
       log to file); VERIFY curl /health → {"status":"ok"}.
  VERIFY config: curl -s localhost:8123/config/ai → agent model = the .env value.
  START frontend: cd frontend && ./node_modules/.bin/vite --host 0.0.0.0
       (background); VERIFY curl -sI localhost:5173 → 200.

Task 3 — Dogfood evidence matrix (the live gate; browser at :5173/showcase). For
         each, drive the UI then ASSERT over curl; capture a screenshot.
  3a SEED + LEGACY-FRAME probe:
     DRIVE one run, defaults (demo_minimal, Re-seed ✓, Save-as-workspace UNticked)
     → green 11 steps. ASSERT GET '/demo/workspaces?limit=100' → zero rows
     (ephemeral created none — the live byte-compat echo of test :190).
  3b E3 keep-run (= demo_minimal matrix row + E3 + E4 proof in one):
     UI: demo_minimal, Re-seed ✓, open 'Advanced seed config' → set ≥2 knobs
       (e.g. stores=6, noise_sigma=0.2); open ScopeSelector → pick a live
       store+product pair (discover ids via /dimensions first); open 'Run
       configuration (advanced)' → change the model set and/or a backtest knob
       (e.g. metric=rmse); Save as workspace ✓, name=e7-gate-cfg → Run → green.
     ASSERT: GET /demo/workspaces/{id} → seed_overrides has the 2 knobs,
       user_scope = the picked pair, run_config = {train_model_types, backtest};
       the panel row shows the 'custom: …' badge.
     UI: Load the row → config repopulates (seed panel + scope + run-config);
       WorkspaceArtifactsPanel renders link-health markers.
  3c E1 lifecycle on that row:
     UI: 'Edit details…' → set notes + 2 tags → save; pin; archive (then show-
       archived to see it). ASSERT GET /demo/workspaces/{id} → notes/tags/
       pinned/archived reflect; the panel search + tag-chip filter + sort
       toolbar all narrow the list; select 2 rows → Compare → /showcase/compare
       renders a diff.
  3d E2 safe replay + lineage:
     UI: Replay the e7-gate-cfg row → the ReplayConfirmDialog opens with the
       recorded-vs-sent diff; confirm → green re-run → a NEW row appears with
       a 'replay' badge. ASSERT GET /demo/workspaces/{new_id} →
       replayed_from_workspace_id == the source id, AND seed_overrides /
       user_scope / run_config identical to the source (E3+E4 replay-verbatim).
       Load the new row → the lineage strip shows the chain (≥2 entries).
     UI (destructive escalation): make/keep a reset=true workspace, click Replay
       → the dialog shows destructive copy + 'Replay & wipe database' (do NOT
       confirm unless you intend the wipe — the dialog-open is the evidence).
     UI: multi-select 2 rows → Delete selected → confirm once → both gone;
       created objects survive (ASSERT a referenced run still GET-able).
  3e E5 keep-run on showcase_rich (the approval + story proof):
     (If live-Reject: PATCH /config/ai → a cloud agent model first.)
     UI: showcase_rich, Re-seed ✓, Reset database ✓, Save as workspace ✓,
       name=e7-gate-rich → Run → 24 steps, zero undocumented ❌. If the HITL
       Approve/Reject buttons render in the 10s window: click Reject → ASSERT
       the run stays GREEN (terminal pass 'rejected by operator') and GET
       /scenarios shows NO new plan from this run. Else record the auto-approve
       (⏭️/auto path) per the gemma4 caveat.
     ASSERT: GET /demo/workspaces/{id} → approval_events populated (the decision),
       rag_events populated (if the rag legs ran), created_objects has
       winning_run_id/v2_run_id/alias/scenario_plan_ids/batch_id.
     UI: Load the row → Run-story panel shows the approval history (+ reproduction
       markers if a replay); open /ops → Approval History table lists the entry.
  3f E6 export (re-confirm criterion 7):
     UI: Export the e7-gate-rich row → success toast (bundle path + checksums
       verified). SHELL: cd artifacts/showcase/<id> && sha256sum -c checksums.sha256
       → all OK.
  3g 8-preset run matrix (light — pipeline is CI-covered):
     FOR preset IN [retail_standard, high_variance, stockout_heavy, new_launches]:
       Re-seed ✓ → Run → record GREEN.
     sparse: Re-seed ✓ → Run → record GREEN or the documented features/backtest
       FAIL (either is conformant).
     holiday_rush: Re-seed ✓ AND Reset ✓ → Run → GREEN; RECORD /seeder/status
       range == 2024-10-01..2024-12-31 (pinned).
     ON any non-conformant outcome → STOP RULE.

Task 4 — Docs fix (lands regardless of dogfood outcome):
  BRANCH: git switch -c docs/showcase-completion-e7-gate  (off dev)
  MODIFY docs/_base/DOMAIN_MODEL.md line ~79 — drop 'export bundles under
    artifacts/showcase/<workspace>/ (E6 #412)' from the "Out of scope
    (deliberately not modeled yet)" clause; keep 'per-phase interactive
    configuration' out, and ADD the parenthetical that export shipped in E6
    #412 (import/restore remains out) — mirror RUNBOOKS.md:168 phrasing.
  CHECK: git diff --stat docs/_base/DOMAIN_MODEL.md → ~1-3 lines only (CRLF guard).
  COMMIT 1: docs(docs): reconcile domain model showcase export out-of-scope note (#420)
  COMMIT 2: docs(repo): track showcase completion e7 release-gate prp (#420)  # this file
  PUSH; OPEN PR into dev (needs 1 review + CI; opening suffices to proceed).

Task 5 — Five validation gates (on the docs branch):
  RUN: uv run ruff check . && uv run ruff format --check .
  RUN: uv run mypy app/ && uv run pyright app/
  RUN: uv run pytest -v -m "not integration"
  PLUS: cd frontend && ./node_modules/.bin/eslint src && ./node_modules/.bin/vitest run src/components/demo/
  ALL must pass. A failure on an untouched surface = regression → STOP RULE.

Task 6 — Replay regression (verify-only; AFTER the dogfood — it RESETS the DB):
  RUN: uv run pytest "tests/test_e2e_demo.py::test_demo_replay_same_config_twice" -v -m integration
  (Optional) uv run pytest "tests/test_e2e_demo.py::test_demo_replay_preserves_seed_overrides_and_scope" -v -m integration
  EXPECT: pass in ≤ ~8 min each (240s-budget runs on :8124).

Task 7 — Release path (record only; the cut is stop-and-ask):
  CONFIRM: gh pr list --base main → no open Release PR; main = v0.2.22.
  RECORD: the E1–E6 commits on dev are all feat:/fix:/docs: — release-please
    will bump v0.2.22 → v0.2.23 (pre-1.0 feat→PATCH) on the dev→main merge.
  WRITE in the #420 evidence: "Release-ready: dev is green; cutting v0.2.23
    requires a dev→main PR (web-UI merge or non-conventional --subject to avoid
    the merge-subject trap, RUNBOOKS 'release-please skipped the bump'). This
    gate does NOT cut — the release is the maintainer's stop-and-ask."

Task 8 — Evidence + close-out (gh write discipline: echo each command first;
         ONLY if Tasks 1-3 + 5-6 were fully matrix-conformant):
  COMMENT on #420: evidence block per output-formatting.md — HEAD SHA, CI
    citation, fresh-DB + downgrade proof, the dogfood matrix (per-epic
    action → outcome → curl assertion), 8-preset matrix, export sha256sum -c,
    gate results, replay-test result, screenshot paths, release path, PR link.
  EDIT #406 body: tick the 7 remaining Success-criteria boxes (leave E6's
    'Export produces…' already-ticked box). Byte-preserve the rest (fetch live).
  CLOSE #406: gh issue close 406 --comment "<close-out linking the #420
    evidence + epics #407-#412 + the docs PR + the recorded release path>"
  CLOSE #420: gh issue close 420 --comment "<gate complete — evidence above;
    docs PR <link> lands through normal review; release v0.2.23 pending the
    maintainer's dev→main cut>"

Task 9 — Teardown:
  STOP the background uvicorn + vite; REVERT any /config/ai agent-model override.
  LEAVE the seeded DB + workspace rows + export bundles in place (operator
    artifacts). LEAVE the compose stack (postgres + GPU ollama) up.
```

### Integration Points

```yaml
GITHUB:
  - issue #420: evidence comment + close
  - issue #406: 7 success-criteria checkbox ticks + close-out comment + close
  - PR: docs branch (DOMAIN_MODEL one-line fix + this PRP) into dev
  - (stop-and-ask, NOT in this gate): dev→main Release PR → release-please → v0.2.23

RUNTIME (consumers only — no code integration):
  - compose Postgres :5433 + GPU ollama :11434 (gpu overlay, warmed embedder)
  - local uvicorn :8123 (repo root), Vite :5173
  - test-owned uvicorn :8124 (Task 6 only)
```

## Validation Loop

### Level 1 — environment sanity (before the live stack)

```bash
git status --short && git rev-parse --abbrev-ref HEAD      # dev, clean
lsof -iTCP:8123 -sTCP:LISTEN                                # must be empty
gh run list --workflow ci.yml --branch dev --limit 1 --json conclusion  # success
docker compose ps                                           # postgres healthy
docker exec forecastlab-ollama nvidia-smi | head -3         # GPU overlay (after Task 2)
curl -s http://localhost:8123/health                        # {"status":"ok"} after Task 2
```

### Level 2 — targeted committed proofs

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
uv run pytest -v -m "not integration"                       # full unit gate (~2112)
uv run pytest "app/features/demo/tests/test_routes.py::test_demo_stream_websocket_legacy_frame_ignores_unknown_keys" -v
cd frontend && ./node_modules/.bin/eslint src && ./node_modules/.bin/vitest run src/components/demo/ && cd ..
# Task 6 ONLY (resets the shared DB):
uv run pytest "tests/test_e2e_demo.py::test_demo_replay_same_config_twice" -v -m integration
```

### Level 3 — live system (the dogfood matrix + curl probes)

```bash
# Browser: http://localhost:5173/showcase per Task 3.
curl -s 'http://localhost:8123/demo/workspaces?limit=100' | python3 -m json.tool | head -60
curl -s "http://localhost:8123/demo/workspaces/<id>" | python3 -m json.tool   # slots + run_config
curl -s 'http://localhost:8123/demo/approval-events?limit=20' | python3 -m json.tool
curl -s "http://localhost:8123/demo/workspaces/<id>/health" | python3 -m json.tool
curl -s -X POST "http://localhost:8123/demo/workspaces/<id>/export" | python3 -m json.tool
( cd artifacts/showcase/<id> && sha256sum -c checksums.sha256 )
curl -s 'http://localhost:8123/dimensions/stores?limit=5' | python3 -m json.tool   # focus-pair ids
```

### Level 4 — repo gates (docs branch)

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
uv run pytest -v -m "not integration"
git diff --stat docs/_base/DOMAIN_MODEL.md                  # ~1-3 lines (CRLF guard)
```

## Final validation Checklist

- [ ] dev CI cited green on the current HEAD (five gates + showcase_rich e2e +
      replay run there); local five gates + legacy-frame test + demo vitest green
- [ ] Fresh DB via DROP/CREATE (NOT down -v); `alembic upgrade b7c1d9e3f204`
      clean (committed head; multi-head note in Gotchas) +
      `downgrade -1 && upgrade b7c1d9e3f204` round-trip clean; GPU ollama up + warmed
- [ ] Legacy-frame run green; zero workspace rows created by it
- [ ] E1: rename/notes/tags/pin/archive reflected in GET detail + panel
- [ ] E2: destructive-replay confirm dialog gates the run; replay row has
      replayed_from_workspace_id + lineage chain; search/filter/sort/multi-delete/
      compare/link-health all exercised
- [ ] E3: keep-run with ≥2 seed knobs + focus pair → slots persist; replay carries
      identical slots
- [ ] E4: custom run-config → run_config recorded + 'custom: …' badge; default
      run → run_config null
- [ ] E5: approval captured on a showcase_rich keep-run (Reject live OR auto +
      CI/unit backing); Run-story panel + /ops Approval History render it; a
      Reject keeps the run green with no scenario_plan
- [ ] E6: Export → sha256sum -c passes
- [ ] 8-preset matrix conformant (sparse + holiday_rush per RUNBOOKS 28)
- [ ] DOMAIN_MODEL.md:79 corrected; git diff --stat shows only intended lines
- [ ] Five gates green on the docs branch + demo-component vitest green
- [ ] Replay regression test green (Task 6)
- [ ] Release path recorded (target v0.2.23; dev→main is stop-and-ask)
- [ ] Evidence on #420; #406's 7 boxes ticked; #406 closed; #420 closed; docs
      PR open into dev
- [ ] Background servers stopped; /config/ai override reverted; compose stack +
      seeded DB left in place

---

## Anti-Patterns to Avoid

- ❌ Don't `docker compose down -v` — it destroys the Ollama models volume; use
     the DROP/CREATE DATABASE procedure (memory: fresh-stack-gate-procedure)
- ❌ Don't fix forward inside the gate — a non-conformant outcome files a NEW
     issue and STOPS the close-out (the docs fix + PR still land)
- ❌ Don't treat a documented expected-skip (agent_hitl_flow ⏭️, rag legs ⏭️,
     sparse fail) as a deviation — but don't hand-wave an undocumented ❌
- ❌ Don't run `test_demo_replay_same_config_twice` (or the full integration
     suite) mid-dogfood — both mutate the shared DB
- ❌ Don't skip Reset on holiday_rush / showcase_rich — the union-window trap
- ❌ Don't gate on a clean `tsc` — it's vacuous/pre-failing; use lint + vitest
     (memory: frontend-tsc-noemit-gate-vacuous)
- ❌ Don't `gh pr merge` dev→main here — the release cut is a separate
     stop-and-ask (release-please owns tagging)
- ❌ Don't retype #406's body — fetch, tick the 7 boxes, push back byte-preserved
- ❌ Don't edit API_CONTRACTS.md / RUNBOOKS.md — audited complete; only
     DOMAIN_MODEL.md:79 is stale
- ❌ Don't assume focus-pair id=1 — the seeder doesn't reset sequences; discover
     live ids first (memory: seeder-does-not-reset-id-sequences)

## Confidence Score: 9/10

> Updated 8.5 → 9 after the prp-quality-agent pass (2026-06-13): the one
> high-severity gap it found — the local alembic two-head state that makes a
> bare `alembic upgrade head` error, plus a downgrade-target mislabel (the
> head-adjacent committed showcase migration is E4 `b7c1d9e3f204` run_config,
> not E1) — is now folded into Task 2 + Known Gotchas (target the committed head
> explicitly). All other load-bearing claims (CI run id/SHA, #406 criteria
> mapping, the DOMAIN_MODEL:79 stale line, every test marker, the
> expected-skip carve-outs) verified accurate against the live repo.

One-pass success likelihood is high: this is the second showcase release gate
(the #401 PRP is a proven, near-identical template), the docs audit already
reduced the doc work to one verified-stale line, the backend pipeline is
CI-covered (so the live dogfood is additive evidence, not the sole proof), every
dogfood action is pinned to a file:line UI control + a curl assertion + a backing
committed test, and all the hard-won environment corrections (Ollama volume, GPU
overlay, embedder warm-up, stale-uvicorn, seeder id sequences, snap chromium,
integration-suite pollution, CRLF) are folded in from memory. Residual risk
(−1.5): the E5 live-Reject depends on swapping to a cloud agent model (the 2B
ollama agent reliably skips the tool), the showcase_rich rag legs may ⏭️ on the
committed 1536-dim schema vs a local qwen3 setup, and browser automation on snap
chromium remains the most fragile dependency — none blocks the gate (each has a
documented-acceptable fallback that still closes the criterion via CI + unit
coverage).
```
