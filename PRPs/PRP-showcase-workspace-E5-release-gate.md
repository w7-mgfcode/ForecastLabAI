name: "PRP showcase-workspace-E5 — release gate: 8-preset dogfood + workspace-mode dogfood + doc sweep + umbrella close-out"
description: |
  Issue #401 (epic E5 of umbrella #389, milestone showcase-workspace).
  Release-gate epic: NO production code. Deliverables are (a) an executed
  verification — a per-preset dogfood matrix across all 8 ScenarioPreset cards
  on /showcase plus a workspace-mode (preservation=keep) dogfood with
  list/Load/Replay + tag retrieval, on a fresh-DB stack; (b) a tracked docs
  sweep — a Showcase-workspace section in docs/_base/RUNBOOKS.md and a
  showcase_workspace aggregate + ubiquitous-language entry in
  docs/_base/DOMAIN_MODEL.md; (c) evidence recorded on #401, umbrella #389
  ticked + closed. If any dogfood check fails OUTSIDE the documented
  expected-outcome matrix, the gate STOPS and files a fix issue — it never
  fixes forward inside this epic.

---

## Goal

Close umbrella #389 (showcase workspace — preserve, restore, replay) on **proof,
not per-epic merges**. E1 #390, E2 #391, E3 #392, E4 #393 are all CLOSED and
shipped in v0.2.22; nothing has yet verified their *combined* behavior across
all 8 presets, nor the workspace keep-path on `showcase_rich` (E4's manual
dogfood covered `demo_minimal` only), and the deferred RUNBOOKS/DOMAIN_MODEL
documentation never landed.

1. **8-preset dogfood matrix** — fresh-DB stack, then one `/showcase` run per
   `ScenarioPreset` card with **Re-seed first** ticked (+ **Reset database**
   where the matrix below requires it). Record green / expected-skip /
   expected-fail per the RUNBOOKS entry-28 matrix; any deviation → STOP RULE.
2. **Workspace-mode dogfood** — one `preservation="keep"` run each on
   `demo_minimal` and `showcase_rich` (these double as those presets' matrix
   rows). Verify: exactly one new `showcase_workspace` row per run, list/detail
   endpoints, UI **Load** (config + artifacts re-attach) and **Replay** (new
   row, green pipeline, no 409/500), and `GET /scenarios?tags=workspace:<name>`
   returns the showcase-saved plans (E3, `showcase_rich` only).
3. **Docs sweep** — add the Showcase-workspace operational section to
   `docs/_base/RUNBOOKS.md` and the `showcase_workspace` aggregate +
   `workspace` ubiquitous-language entry to `docs/_base/DOMAIN_MODEL.md`
   (both currently have ZERO "workspace" mentions — verified 2026-06-12).
4. **Regression coverage (verify only)** —
   `tests/test_e2e_demo.py::test_demo_replay_same_config_twice` green in CI
   (CI runs the full pytest incl. integration; latest dev run 27427250799 ✅)
   and green in a targeted local re-run.
5. **Close-out** — evidence comment on #401; tick ALL satisfied checkboxes on
   #389 (live body has 11/11 unticked — drift) and fix the E5 line
   ("not yet created" → "#401"); close #389; close #401 last.

**End state**: #389 and #401 CLOSED with linked evidence; the two `docs/_base/`
files document workspace semantics; this PRP file committed (`docs(repo)`
precedent b1c8593).

## Why

- Every umbrella #389 success criterion is implemented but **none is ticked
  with evidence**, and three of six are only provable by a live multi-preset
  dogfood (8-preset green/skip matrix; restore/replay without 409/500;
  workspace-tag retrieval).
- E4's dogfood covered `demo_minimal` keep-runs only. The `showcase_rich`
  keep-path is the one that exercises E3 tagging (planning phase exists only
  there) and the 24-step `created_objects` recording — untested live as a
  whole.
- The umbrella explicitly deferred RUNBOOKS/DOMAIN_MODEL documentation to E5;
  operators currently have no runbook for replay-of-`reset=true` destructive
  semantics, non-unique names, row accumulation (no DELETE), or the
  `holiday_rush` union-window replay trap.

## What

A verification campaign plus a docs-only repo change. No `app/`, `frontend/`,
or `alembic/` change is in scope. Tracked changes: this PRP file +
`docs/_base/RUNBOOKS.md` + `docs/_base/DOMAIN_MODEL.md`, one branch
(`docs/showcase-workspace-e5-gate`), one PR into `dev`.

### Success Criteria (mirror of #401 sub-tasks)

- [ ] Fresh-DB stack built via the **DROP/CREATE DATABASE** procedure (NOT
      `down -v` — see Known Gotchas) + `alembic upgrade head` clean.
- [ ] 8/8 preset matrix executed and recorded; every outcome matches the
      expected-outcome matrix (Known Gotchas) — zero undocumented ❌.
- [ ] `demo_minimal` keep-run: 1 new workspace row (status `completed`),
      listed in **Saved workspaces**, Load restores config + artifacts panel,
      Replay completes green with a NEW distinct `workspace_id`.
- [ ] `showcase_rich` keep-run: same as above PLUS `created_objects` carries
      `winning_run_id`/`v2_run_id`/`alias`/`scenario_plan_ids`/`batch_id`, and
      `GET /scenarios?tags=workspace:<name>` returns ≥1 plan tagged
      `["showcase", …, "source:showcase", "workspace:<name>"]`.
- [ ] Legacy frame back-compat re-confirmed: one run WITHOUT workspace fields
      behaves as today (no workspace row created for it).
- [ ] `test_demo_replay_same_config_twice` green: targeted local run + CI
      citation.
- [ ] RUNBOOKS.md gains the Showcase-workspace section (4 mandated topics);
      DOMAIN_MODEL.md gains the aggregate + ubiquitous-language row.
- [ ] Five validation gates green on the docs branch (ruff, format, mypy,
      pyright, unit pytest) + targeted frontend vitest for the workspace
      components.
- [ ] Evidence on #401; #389 checkboxes ticked + E5 line fixed; #389 closed;
      #401 closed.

## All Needed Context

### Documentation & References

```yaml
# ── The gate's contract ──────────────────────────────────────────────────────
- issue: "#401 — gh issue view 401"
  why: The epic's six sub-tasks this PRP encodes verbatim.

- issue: "#389 — gh issue view 389 --json body"
  why: "Umbrella. DRIFT (verified 2026-06-12): ALL 11 checkboxes unticked
       (5 decomposition + 6 success criteria); the E5 decomposition line still
       reads 'not yet created'. Tick every satisfied box, update the E5 line to
       '#401', close with a close-out comment. E1-E4 = #390 #391 #392 #393,
       all CLOSED, shipped v0.2.22."

- file: PRPs/PRP-reliability-E6-release-gate.md
  why: "The release-gate precedent this PRP mirrors (STOP rule, evidence
       format, close-out order). ONE CORRECTION: its 'docker compose down -v'
       fresh-stack step is superseded — see the fresh-stack procedure below."

- file: PRPs/PRP-showcase-workspace-E4-restore-replay.md
  why: "Restore-vs-Replay designed semantics (replay is always keep; config
       verbatim incl. reset/skip_seed; no provenance column; no DELETE) — the
       semantics the RUNBOOKS section must document."

# ── What 'green' means per preset ────────────────────────────────────────────
- file: docs/_base/RUNBOOKS.md
  why: "'Showcase page (/showcase) pipeline fails at step X' items 1-28.
       Entry 28 is THE per-preset expected-outcome matrix (sparse may-fail,
       holiday_rush pinned window + union-range trap, others green). Items
       9-26 list acceptable ⏭️/⚠️ on showcase_rich. ALSO the doc-sweep target:
       add the new '### Showcase workspace …' section AFTER this incident
       section's closing Notes paragraph."

- file: app/features/demo/pipeline.py
  why: "_phase_table(scenario) (line 2528): showcase_rich = 24 steps / 10
       phases (data 7, modeling 2, decision 5, portfolio 1, planning 2,
       knowledge 3, verify 1, agents 1, ops 1, cleanup 1); ALL other presets =
       the legacy 11-step / 6-phase table. _SCENARIO_SEED_PROFILE (lines
       513-538): showcase_rich/retail_standard/high_variance/stockout_heavy
       5×15×180d, new_launches 5×25×180d, holiday_rush PINNED
       2024-10-01..2024-12-31. READ-ONLY."

# ── Workspace surface (what the keep-runs must prove) ────────────────────────
- file: app/features/demo/models.py
  why: "showcase_workspace table (line 57): workspace_id String(32) UNIQUE,
       status CHECK ∈ {running, completed, failed} (lines 32-34), name
       NON-unique, seed/scenario/reset/skip_seed config columns,
       store_id/product_id/date_start/date_end grain columns, created_objects
       JSONB (sparse keys: winning_run_id, v2_run_id, v2_model_path, alias,
       agent_session_id, batch_id, scenario_plan_ids, scenario_artifact_key,
       train_model_types, stale_alias_run_id), result_summary JSONB. Soft
       references only — NO FKs. This is the DOMAIN_MODEL aggregate source."

- file: app/features/demo/routes.py
  why: "GET /demo/workspaces (lines 70-97; response {workspaces:[…]}, newest
       first, limit 1-100/offset), GET /demo/workspaces/{id} (100-125; 404
       problem+json when missing), POST /demo/run (41-67), WS /demo/stream
       (128-156; workspace_name without preservation='keep' → one error
       event). No DELETE endpoint exists — verified; that's a runbook fact."

- file: app/features/demo/schemas.py
  why: "DemoRunRequest defaults: seed=42, reset=false, skip_seed=true,
       scenario='demo_minimal', preservation='ephemeral', workspace_name=None;
       workspace_name pattern ^[a-z0-9][a-z0-9\\-_]*$, ≤100 chars. ScenarioPreset
       = the 8 enum values. WorkspaceListItem vs WorkspaceDetailResponse
       (detail adds grain/window + created_objects)."

- file: tests/test_e2e_demo.py
  why: "test_demo_replay_same_config_twice (line ~561, @pytest.mark.integration):
       POSTs the IDENTICAL keep-body (seed 42, reset=true, skip_seed=false,
       demo_minimal, workspace_name='replay-regression') twice against a
       SUBPROCESS uvicorn on :8124; asserts both pass, distinct workspace_ids,
       both listed completed. The #146/#324 regression guard. NOTE: it RESETS
       the DB — never run it mid-dogfood."

# ── Frontend dogfood surface ─────────────────────────────────────────────────
- file: frontend/src/pages/showcase.tsx
  why: "Controls: scenario card grid (8 presets), 'Re-seed first' →
       skip_seed=false, 'Reset database' → reset=true, seed input, 'Save as
       workspace' checkbox (line 332) + name input (344, mirrors the backend
       pattern), Run/Stop. handleReplayWorkspace (174-186) re-submits the
       recorded config VERBATIM with preservation='keep' (+ recorded name).
       Starting any run detaches a loaded workspace (140)."

- file: frontend/src/components/demo/WorkspacePanel.tsx
  why: "'Saved workspaces' panel — Load (restore config + artifacts, no run)
       and Replay buttons per row; reset=true rows render a destructive-styled
       marker (line ~38/94). Vitest: WorkspacePanel.test.tsx,
       WorkspaceArtifactsPanel.test.tsx, RunHistoryStrip.test.tsx,
       ScenarioPicker.test.tsx."

- file: frontend/src/components/demo/ScenarioPicker.tsx
  why: "The 8 preset cards with wall-clock estimates; sparse carries
       caveatKind='expected-skip' ('May fail at features/backtest (NaN WAPE) —
       expected; see runbook', line ~66-72)."

# ── Doc-sweep targets ────────────────────────────────────────────────────────
- file: docs/_base/DOMAIN_MODEL.md
  why: "Sweep target. Add '### showcase_workspace (Demo)' under Core
       Aggregates (mirror the scenario_plan entry's shape: Root / JSONB fields
       / Invariants), one Ubiquitous Language row ('workspace' vs seeder
       'scenario' vs 'scenario plan'), and one Entity Relationship Summary
       line (soft-references, no FK)."

- file: docs/_base/API_CONTRACTS.md
  why: "READ-ONLY here — E4 already documented the workspace endpoints + WS
       fields (commit ee844f1). Cross-check the docs sweep against it; do NOT
       duplicate endpoint tables into RUNBOOKS."

# ── Close-out mechanics ──────────────────────────────────────────────────────
- file: .claude/rules/umbrella-issue.md
  why: "Write discipline for gh mutations: dry-run echo → idempotent check →
       approval gate → confirm. Applies to the #389 body edit + closes."

- file: .claude/rules/output-formatting.md
  why: "Evidence-comment format: emoji status indicators, box separators,
       ≤40 lines."
```

### Current Codebase tree (verification-relevant subset)

```bash
app/features/demo/models.py          # showcase_workspace ORM (E1)
app/features/demo/pipeline.py        # _phase_table + _SCENARIO_SEED_PROFILE
app/features/demo/routes.py          # /demo/run, /demo/workspaces[,/{id}], WS
app/features/demo/schemas.py         # DemoRunRequest, ScenarioPreset, Workspace*
app/features/demo/tests/             # test_workspace.py, test_routes.py, test_pipeline.py
tests/test_e2e_demo.py               # test_demo_replay_same_config_twice (:561)
frontend/src/pages/showcase.tsx      # dogfood entry point
frontend/src/components/demo/        # WorkspacePanel, ScenarioPicker, … (+ vitest)
docs/_base/RUNBOOKS.md               # sweep target 1 (zero 'workspace' today)
docs/_base/DOMAIN_MODEL.md           # sweep target 2 (zero 'workspace' today)
docker-compose.gpu.yml               # GPU overlay — REQUIRED for ollama legs
docker-compose.lan.yml               # untracked local overlay — NOT used here
```

### Desired Codebase tree (files added/modified)

```bash
PRPs/PRP-showcase-workspace-E5-release-gate.md   # ADD — this file
docs/_base/RUNBOOKS.md                           # MOD — +'### Showcase workspace' section
docs/_base/DOMAIN_MODEL.md                       # MOD — +aggregate, +UL row, +ER line
# No app/, frontend/, or alembic/ change is in scope.
```

### Known Gotchas & Environment Quirks

```python
# ── STOP RULE (governs the whole epic) ───────────────────────────────────────
# If ANY preset run or workspace check deviates from the expected-outcome
# matrix below: capture evidence (step table / screenshot / response body),
# open a NEW fix issue referencing #389 + #401, comment the failure on #401,
# and STOP the close-out. The docs sweep (Task 7) still lands — it documents
# already-shipped E1-E4 semantics and is independent of dogfood outcomes.
# A DOCUMENTED expected-fail (sparse) or sanctioned ⏭️/⚠️ is NOT a deviation.

# ── Fresh stack — SUPERSEDES the reliability-E6 procedure ────────────────────
# NEVER `docker compose down -v`: it removes ALL named volumes incl.
# forecastlab_ollama_models (pulled gemma4/qwen3 models, expensive to rebuild).
# Fresh-DB equivalent (memory: fresh-stack-gate-procedure, hit 2026-06-12):
#   docker compose --profile gpu down --remove-orphans
#   docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile gpu up -d
#   docker compose exec -T postgres psql -U forecastlab -d postgres \
#     -c "DROP DATABASE IF EXISTS forecastlab WITH (FORCE);" \
#     -c "CREATE DATABASE forecastlab OWNER forecastlab;"
#   uv run alembic upgrade head        # cold-boot proof on the empty DB
# GOTCHA: WITHOUT the gpu overlay, ollama runs CPU-only and the showcase
# rag_index_subset step HARD-FAILS (probe says reachable=True but the cold
# qwen3-embedding:4b load exceeds the 60s embedding ReadTimeout → 502).
# Verify `docker exec forecastlab-ollama nvidia-smi` works, then WARM the
# embedder before any showcase_rich run (~41s cold-on-GPU, ~2.4s warm):
#   curl -s localhost:11434/api/embed -d '{"model":"qwen3-embedding:4b","input":"warmup"}'
# GOTCHA: the fresh DB wipes app_config runtime overrides — agent model
# reverts to .env (agent_default_model=ollama:gemma4-agent on this host).
# Re-check GET /config/ai after boot.
# GOTCHA: a stale uvicorn from a prior session can hold :8123 — curl then hits
# OLD code. lsof -iTCP:8123 -sTCP:LISTEN and kill stale PIDs first.
# Run the backend as LOCAL uvicorn from the REPO ROOT (host-filesystem
# artifacts for verify/feature-metadata; docs/ visible to rag_index_subset —
# the compose backend image lacks docs/, which is why docker-compose.lan.yml
# exists; do NOT use that overlay here). pnpm 11 depsStatusCheck can stall
# `pnpm dev` — start Vite directly: cd frontend && ./node_modules/.bin/vite --host 0.0.0.0

# ── Per-preset expected-outcome matrix (RUNBOOKS entry 28 — the gate's spec) ─
# Every run: 'Re-seed first' TICKED (skip_seed=false). seed=42.
#   demo_minimal      11 steps  GREEN (this run = the demo_minimal keep-run)
#   retail_standard   11 steps  GREEN
#   high_variance     11 steps  GREEN
#   stockout_heavy    11 steps  GREEN
#   new_launches      11 steps  GREEN
#   sparse            11 steps  GREEN **or documented FAIL** at features/
#                     backtest (50% missing grains / all-NaN WAPE gate) —
#                     the card carries the expected-skip badge; either
#                     outcome = matrix-conformant; record which occurred
#   holiday_rush      11 steps  GREEN — tick **Reset database** TOO (pinned
#                     2024-10-01..12-31 window; re-seed without reset ADDS
#                     rows → /seeder/status reports the union range)
#   showcase_rich     24 steps / 10 phases GREEN — run LAST, tick **Reset
#                     database** TOO (clears holiday_rush's pinned window so
#                     the 180d today-anchored window seeds clean; also clears
#                     accumulated model_run rows). This run = the
#                     showcase_rich keep-run.
# ACCEPTABLE non-green steps on showcase_rich (RUNBOOKS items 9-26):
#   agent_hitl_flow ⏭️ (KNOWN on this host: gemma4-agent 2B reliably skips —
#   no Approve button appears; memory showcase-crypto-randomuuid-lan-crash),
#   rag_index_subset / rag_retrieve_probe ⏭️ (provider unreachable/rejected —
#   should NOT happen with the GPU overlay + warm-up; investigate if hit),
#   verify ⏭️ (V2 prophet_like winner — artifact roots differ),
#   champion_compat_compare / safer_promote_flow ⏭️ (missing V1/V2 — should
#   NOT happen with Re-seed; investigate), batch_preset ⚠️ (90s poll timeout),
#   ops_snapshot ⚠️. ANY other ❌/⏭️ = deviation → STOP RULE.
# Only ONE pipeline at a time (module asyncio.Lock; 2nd start → one error
# event / 409; Stop releases the lock in ~5s). Budget: ~90s-3min per 11-step
# run, 5-10 min showcase_rich; whole matrix ~25-40 min.

# ── Workspace-mode mechanics ─────────────────────────────────────────────────
# workspace_name pattern ^[a-z0-9][a-z0-9\-_]*$ (lowercase!) ≤100 — use
# e5-gate-minimal / e5-gate-rich. 'Save as workspace' + name without the
# checkbox is impossible in the UI; over raw WS, workspace_name without
# preservation='keep' → one error event (negative probe, optional).
# Replay re-submits reset/skip_seed VERBATIM: replaying a reset=true row IS
# DESTRUCTIVE (wipes + reseeds) — that's designed semantics (E4) and a
# mandated RUNBOOKS topic, not a bug. Names are NON-unique by design; every
# replay creates a NEW row. Rows accumulate; there is NO DELETE endpoint.
# localStorage run-history ('forecastlab.showcase.runs.v1', FIFO 5) EXCLUDES
# workspace runs — keep-runs appear only in the server-backed panel.
# GET /scenarios?tags=workspace:<label> — label is the workspace_name when
# provided, else workspace_id; JSONB containment, ALL listed tags must match.
# Planning phase (scenario plans) exists ONLY on showcase_rich — the tag
# check is meaningless on demo_minimal keep-runs.
# The /scenarios run_id field is the ARTIFACT KEY, not registry run_id —
# different ID spaces (memory: scenario-run-id-vs-registry-run-id).

# ── Tests / gates ────────────────────────────────────────────────────────────
# test_demo_replay_same_config_twice spins its OWN uvicorn on :8124 but hits
# the SAME compose Postgres and RESETS it (reset=true) — run it ONLY in
# Task 6, after the dogfood matrix, never concurrently with a :8123 run.
# NEVER run the full integration suite as a gate — known shared-state
# pollution (memory: integration-suite-shared-state-pollution). Targeted only.
# `pnpm tsc --noEmit` is VACUOUS (solution-style tsconfig, 0 files) and
# `tsc -b` has pre-existing dev failures — frontend evidence = targeted vitest.
# Seeder does NOT reset ID sequences — discover store/product IDs via
# /dimensions/* if any manual curl needs them; never assume id=1.
# Playwright MCP + `playwright install` fail on this host — use native Python
# Playwright with executable_path="/snap/bin/chromium" (symlink verified
# present) or the agent-browser skill. localhost:5173 is fine (no E3
# secure-context requirement in this gate).

# ── Docs sweep ───────────────────────────────────────────────────────────────
# Repo has MIXED CRLF/LF line endings (memory: repo-line-endings-crlf) —
# after editing the two docs, check `git diff --stat` for whole-file noise
# before committing; touch only the lines you mean to.
# RUNBOOKS insertion point: a NEW '### Showcase workspace …' incident-style
# section AFTER the '### Showcase page (/showcase) pipeline fails at step X'
# section's closing **Notes** paragraph (before '### release-please skipped…').
# DOMAIN_MODEL: mirror the scenario_plan aggregate's structure; the no-FK
# rationale: created_objects are SOFT references because the referenced
# objects (runs, plans, aliases) are independently operator-deletable — the
# workspace row is an audit record, not an ownership root.
# These files are imported into every agent session's context — keep both
# additions tight (~25-35 lines RUNBOOKS, ~15-20 lines DOMAIN_MODEL).

# ── Third-party API claims ───────────────────────────────────────────────────
# None. This PRP cites no new library attributes; every verification command
# is first-party (curl/pytest/grep/gh) and listed inline. (Policy per #258.)

# ── GitHub close-out ─────────────────────────────────────────────────────────
# Write discipline (.claude/rules/umbrella-issue.md): echo each gh mutation
# before running it.
# #389 body edit: fetch with `gh issue view 389 --json body`, tick the 5
# Decomposition boxes + all 6 Success-criteria boxes, change the E5 line's
# 'not yet created' → '#401', push back via `gh issue edit 389 --body-file`.
# Preserve everything else byte-identical. Do NOT pattern-match checkbox text
# from this PRP — edit the fetched live markdown.
# Close order: PR opened first → evidence comment on #401 → tick #389 →
# close #389 (comment links the #401 evidence) → close #401 last.
# The PR needs 1 approving review + CI — it will NOT merge autonomously;
# opening it is enough to proceed (reliability-E6 precedent).
```

## Implementation Blueprint

### Data models and structure

None. Zero schemas, zero migrations, zero source changes. The only authored
content is two markdown sections (Task 7) whose required topics are fixed by
issue #401.

### List of tasks in execution order

```yaml
Task 0 — Preflight:
  VERIFY branch: git switch dev && git pull → clean, up to date.
  VERIFY no stale server: lsof -iTCP:8123 -sTCP:LISTEN → kill stale PIDs.
  VERIFY chromium: ls -la /snap/bin/chromium (else plan agent-browser skill).
  VERIFY epics: gh issue view 390 391 392 393 → all CLOSED (re-confirm).
  RECORD: git rev-parse HEAD → the SHA all evidence refers to.

Task 1 — Fresh-DB stack (memory-corrected procedure; NEVER down -v):
  RUN: docker compose --profile gpu down --remove-orphans
  RUN: docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile gpu up -d
  VERIFY: docker exec forecastlab-ollama nvidia-smi → GPU visible
  RUN: docker compose exec -T postgres psql -U forecastlab -d postgres \
         -c "DROP DATABASE IF EXISTS forecastlab WITH (FORCE);" \
         -c "CREATE DATABASE forecastlab OWNER forecastlab;"
  RUN: uv run alembic upgrade head           # MUST exit 0 on the empty DB
  WARM embedder: curl -s localhost:11434/api/embed \
         -d '{"model":"qwen3-embedding:4b","input":"warmup"}'  # expect <60s
  START backend: uv run uvicorn app.main:app --port 8123  (background, repo
         root, log to file); VERIFY curl /health → {"status":"ok"}
  VERIFY config: curl -s localhost:8123/config/ai → agent model is the .env
         value (ollama:gemma4-agent); providers health as expected.
  START frontend: cd frontend && ./node_modules/.bin/vite --host 0.0.0.0
         (background); VERIFY curl -sI localhost:5173 → 200.

Task 2 — Legacy-frame back-compat probe (cheap, before the matrix):
  DRIVE one run with NO workspace fields (UI defaults: demo_minimal,
  Re-seed first ticked, Save-as-workspace UNticked) → green 11 steps.
  ASSERT: curl -s 'localhost:8123/demo/workspaces?limit=100' → zero rows
  (fresh DB + ephemeral run created none). This is the byte-compat evidence.
  NOTE: this same run seeds demo data; it is NOT the demo_minimal matrix row
  (that one is the keep-run in Task 3).

Task 3 — Workspace keep-run #1 (= demo_minimal matrix row):
  UI: scenario=demo_minimal, Re-seed first ✓, Save as workspace ✓,
      name=e5-gate-minimal → Run → green 11 steps.
  ASSERT (curl): GET /demo/workspaces → exactly 1 row named e5-gate-minimal,
      status=completed; GET /demo/workspaces/{id} → seed=42, scenario,
      reset=false, skip_seed=false, created_objects.winning_run_id set.
  UI: 'Saved workspaces' panel lists the row → click Load → config
      repopulates + WorkspaceArtifactsPanel renders (links resolve) →
      click Replay → green pipeline → a SECOND distinct row appears.
  CAPTURE: screenshot of panel with both rows + the step table.

Task 4 — Preset matrix (the five remaining 11-step presets):
  FOR preset IN [retail_standard, high_variance, stockout_heavy,
                 new_launches, sparse]:
    UI: select card, Re-seed first ✓ (no Reset, no workspace) → Run.
    RECORD: per-step outcome table; expected GREEN for the first four;
            sparse = GREEN or the documented features/backtest FAIL
            (record which; a sparse fail is matrix-conformant, NOT a stop).
  THEN holiday_rush: Re-seed first ✓ AND Reset database ✓ → Run → GREEN;
    RECORD /seeder/status date range == 2024-10-01..2024-12-31 (pinned,
    no union range because Reset was ticked).
  ON ANY non-conformant outcome: STOP RULE (RUNBOOKS items 1-28 give the
  per-step diagnosis; file the fix issue; docs sweep still proceeds).

Task 5 — Workspace keep-run #2 (= showcase_rich matrix row; E3 tag proof):
  UI: scenario=showcase_rich, Re-seed first ✓, Reset database ✓ (clears the
      holiday_rush pinned window), Save as workspace ✓, name=e5-gate-rich
      → Run → 24 steps / 10 phases, zero ❌ (acceptable ⏭️/⚠️ per matrix);
      if the HITL Approve button appears within its 90s window, click it
      (a ⏭️ skip is acceptable — KNOWN on this host).
  ASSERT (curl): GET /demo/workspaces/{id} → created_objects carries
      winning_run_id, v2_run_id, alias, scenario_plan_ids (≥1), batch_id.
  ASSERT (curl): GET '/scenarios?tags=workspace:e5-gate-rich' → ≥1 plan;
      its tags ⊇ ["showcase", "source:showcase", "workspace:e5-gate-rich"].
  UI: Load + Replay the e5-gate-rich row → green re-run, NEW distinct row
      (replay survives accumulated model_run rows — the live #146/#324 proof
      on the 24-step path). NOTE the row renders reset=true destructively
      styled, and the replay re-seeds — expected designed semantics.
  CAPTURE: full-page screenshot + step table + the two curl bodies.

Task 6 — Replay regression test (verify-only sub-task):
  CITE CI: gh run list --workflow ci.yml --branch dev --limit 1 → success
      (run 27427250799 at gate time; re-cite the current latest).
  RUN targeted (AFTER the dogfood — the test RESETS the shared DB):
      uv run pytest "tests/test_e2e_demo.py::test_demo_replay_same_config_twice" -v -m integration
  EXPECT: pass in ≤ ~8 min (two 240s-budget runs on :8124).

Task 7 — Docs sweep (lands regardless of dogfood outcome):
  BRANCH: git switch -c docs/showcase-workspace-e5-gate  (off dev)
  MODIFY docs/_base/RUNBOOKS.md — ADD '### Showcase workspace (E1-E4 #389)'
    AFTER the showcase-incident section's Notes paragraph, covering exactly:
    (1) Replay is verbatim incl. reset — replaying a reset=true workspace is
        DESTRUCTIVE (wipes + reseeds); the panel styles such rows
        destructively; this is designed (E4), not a bug.
    (2) Names are non-unique by design — every replay creates a NEW row;
        disambiguate by workspace_id / created_at.
    (3) Rows accumulate — no DELETE endpoint yet (future epic); harmless
        audit records; created_objects are soft references that may dangle
        if an operator deletes the underlying run/plan/alias.
    (4) holiday_rush replay: the row replays the pinned 2024 window; without
        Reset the re-seed ADDS rows → /seeder/status reports the union
        range; tick Reset for a clean pinned window (cross-ref entry 28).
  MODIFY docs/_base/DOMAIN_MODEL.md —
    ADD '### showcase_workspace (Demo)' under Core Aggregates (mirror the
      scenario_plan entry): Root ShowcaseWorkspace(workspace_id, status);
      status machine running → completed | failed; JSONB created_objects
      (sparse soft-reference keys) + result_summary; invariants: name
      non-unique, config columns (seed/scenario/reset/skip_seed) sufficient
      for verbatim replay, NO FKs (audit record, not ownership root — the
      referenced objects are independently deletable).
    ADD Ubiquitous Language row: `workspace` = a saved showcase run record
      (config + soft references) | NOT: seeder `scenario` (a preset), NOT
      `scenario plan` (a saved what-if).
    ADD ER summary line:
      showcase_workspace ──soft-references──► model_run / scenario_plan /
      run_alias / job artifacts (JSONB ids, no FK)
  CHECK: git diff --stat → only intended lines (CRLF/LF noise guard).
  COMMIT 1: docs(docs): add showcase workspace runbook and domain model entries (#401)
  COMMIT 2: docs(repo): track showcase workspace e5 prp (#401)   # this file
  PUSH; OPEN PR into dev (needs 1 review + CI; opening suffices to proceed).

Task 8 — Five validation gates (on the docs branch):
  RUN: uv run ruff check . && uv run ruff format --check .
  RUN: uv run mypy app/ && uv run pyright app/
  RUN: uv run pytest -v -m "not integration"
  PLUS frontend workspace evidence:
       cd frontend && pnpm test --run src/components/demo/
  ALL must pass. A failure on an untouched surface = regression → STOP RULE.

Task 9 — Evidence + close-out (gh write discipline: echo each command first;
         ONLY if Tasks 1-6 were fully matrix-conformant):
  COMMENT on #401: evidence block per output-formatting.md — HEAD SHA,
    fresh-DB proof, the 8-preset matrix table (preset / steps / outcome /
    skips with reasons), workspace keep-run + Load/Replay + tag-retrieval
    results, replay-test + CI citation, gate results, screenshot paths,
    PR link for the docs sweep.
  EDIT #389 body: tick the 5 Decomposition boxes + all 6 Success-criteria
    boxes; update the E5 line 'not yet created' → '#401'. Byte-preserve the
    rest (fetch live body; never retype it).
  CLOSE #389: gh issue close 389 --comment "<close-out linking the #401
    evidence + epics #390 #391 #392 #393 + v0.2.22>"
  CLOSE #401: gh issue close 401 --comment "<gate complete — evidence above;
    docs PR <link> lands through normal review>"

Task 10 — Teardown:
  STOP the background uvicorn + vite processes.
  LEAVE the seeded DB + workspace rows in place (operator-visible artifacts).
  LEAVE the compose stack (postgres + GPU ollama) up — shared session state.
```

### Integration Points

```yaml
GITHUB:
  - issue #401: evidence comment + close
  - issue #389: body checkbox tick + E5-line fix + close-out comment + close
  - PR: docs branch (RUNBOOKS + DOMAIN_MODEL + this PRP) into dev

RUNTIME (consumers only — no code integration):
  - compose Postgres :5433 + GPU ollama :11434 (gpu overlay, warmed embedder)
  - local uvicorn :8123 (repo root), Vite :5173
  - test-owned uvicorn :8124 (Task 6 only)
```

## Validation Loop

### Level 1 — environment sanity (before anything else)

```bash
git status --short && git rev-parse --abbrev-ref HEAD      # dev, clean
lsof -iTCP:8123 -sTCP:LISTEN                                # must be empty
docker compose ps                                           # postgres healthy
docker exec forecastlab-ollama nvidia-smi | head -3         # GPU overlay active
curl -s http://localhost:8123/health                        # {"status":"ok"} after Task 1
```

### Level 2 — targeted committed proofs

```bash
# Workspace slice units (fast, no DB):
uv run pytest app/features/demo/tests/ -v -m "not integration"
# Replay regression (Task 6 ONLY — resets the shared DB; integration):
uv run pytest "tests/test_e2e_demo.py::test_demo_replay_same_config_twice" -v -m integration
# Frontend workspace components:
cd frontend && pnpm test --run src/components/demo/ && cd ..
```

### Level 3 — live system (the dogfood matrix + workspace probes)

```bash
# Matrix: 8 preset runs at http://localhost:5173/showcase per Tasks 2-5.
# Workspace API probes:
curl -s 'http://localhost:8123/demo/workspaces?limit=100' | python3 -m json.tool | head -40
curl -s "http://localhost:8123/demo/workspaces/<id>" | python3 -m json.tool
curl -s 'http://localhost:8123/scenarios?tags=workspace:e5-gate-rich' | python3 -m json.tool | head -40
# Negative probe (404 problem+json):
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8123/demo/workspaces/nonexistent000
```

### Level 4 — repo gates (docs branch)

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
uv run pytest -v -m "not integration"
```

## Final validation Checklist

- [ ] Fresh DB via DROP/CREATE (NOT down -v); `alembic upgrade head` clean;
      GPU ollama up + embedder warmed
- [ ] Legacy-frame run green; zero workspace rows created by it
- [ ] 8/8 matrix rows recorded; outcomes conformant (sparse fail OK if it
      matches the documented mode; holiday_rush pinned window verified)
- [ ] demo_minimal keep-run: row completed; Load + Replay green; distinct ids
- [ ] showcase_rich keep-run: 24 steps zero ❌; created_objects populated;
      `tags=workspace:e5-gate-rich` retrieval returns tagged plans;
      Load + Replay green with a new row
- [ ] `test_demo_replay_same_config_twice` green locally + CI run cited
- [ ] RUNBOOKS section (4 topics) + DOMAIN_MODEL aggregate/UL/ER added;
      `git diff --stat` shows only intended lines
- [ ] Five gates green + frontend demo-component vitest green
- [ ] Evidence on #401; #389 ticked (11 boxes) + E5 line fixed; #389 closed;
      #401 closed; docs PR open into dev
- [ ] Background servers stopped; compose stack + seeded DB left in place

---

## Anti-Patterns to Avoid

- ❌ Don't `docker compose down -v` — it destroys the Ollama models volume;
     use the DROP/CREATE DATABASE procedure
- ❌ Don't run showcase_rich with CPU-only Ollama or a cold embedder —
     rag_index_subset hard-fails (502 ReadTimeout), polluting the matrix
- ❌ Don't fix forward inside the gate — a non-conformant outcome files a new
     issue and STOPS the close-out (the docs sweep still lands)
- ❌ Don't treat the documented sparse fail or RUNBOOKS-sanctioned ⏭️/⚠️ as a
     deviation — but don't hand-wave an undocumented ❌ either
- ❌ Don't run `test_demo_replay_same_config_twice` (or the full integration
     suite) mid-dogfood — both mutate the shared DB
- ❌ Don't skip Reset on holiday_rush or on the showcase_rich run after it —
     the union-window trap corrupts both rows of the matrix
- ❌ Don't uppercase the workspace name — the pattern rejects it at 422
- ❌ Don't retype #389's body — fetch, tick, push back byte-preserved
- ❌ Don't duplicate API_CONTRACTS endpoint tables into RUNBOOKS — link them
- ❌ Don't `gh pr merge` anything dev→main here — the release cut is a
     separate stop-and-ask decision

## Confidence Score: 8.5/10

One-pass success likelihood is high: every check maps to a named committed
test, an exact curl, or a UI control pinned to file:line; the per-preset
expected-outcome matrix is lifted verbatim from RUNBOOKS entry 28; the
fresh-stack procedure incorporates the hard-won 2026-06-12 corrections
(Ollama volume, GPU overlay, embedder warm-up); and the umbrella-drift state
was verified live. Residual risk (−1.5): the matrix has non-deterministic legs
(sparse's two sanctioned outcomes, agent_hitl_flow timing, batch_preset on a
loaded laptop) that may force a re-run or RUNBOOKS triage, and browser
automation on snap chromium remains the most fragile dependency.
