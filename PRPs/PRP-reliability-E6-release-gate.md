name: "PRP reliability-E6 — release gate: showcase_rich dogfood + per-epic spot checks + umbrella close-out"
description: |
  Issue #387 (epic E6 of umbrella #380, milestone reliability-hardening).
  Release-gate epic: NO new production code. The deliverable is an executed
  verification: a green end-to-end showcase_rich dogfood run on a fresh stack,
  one live spot check per closed reliability epic (E1 #334, E2 #335, E3 #332,
  E4 #268, E5 #237), all five validation gates green on dev, evidence recorded
  on #387, and umbrella #380 closed. If any check fails, the gate STOPS and
  files a fix issue — it never fixes forward inside this epic.

---

## Goal

Prove that the five reliability fixes hold **as one system** on `dev`, not just as
isolated epic PRs, then close the reliability-hardening umbrella:

1. **Fresh-stack showcase_rich dogfood** — `docker compose down -v` → up → migrate,
   then a `/showcase` run with `scenario=showcase_rich` + **Re-seed first**: all
   24 steps / 10 phases green (PRP-41 layout). Provider-dependent steps may ⏭️ skip
   or ⚠️ warn per `docs/_base/RUNBOOKS.md`; the pipeline must still end green
   (`pipeline_complete`, no ❌ step).
2. **Five per-epic spot checks** on `dev` — each is a committed regression test
   re-run PLUS (where meaningful) a live HTTP probe against the running stack.
3. **All five validation gates green** on `dev` (ruff check, ruff format --check,
   mypy --strict, pyright --strict, pytest unit).
4. **Close-out** — evidence comment on #387, tick every satisfied checkbox on
   #380 (the live body has drifted — see Known Gotchas), close #380 with a
   close-out comment linking the evidence, close #387.

**End state**: #387 and #380 are CLOSED with linked evidence; `dev` is demonstrably
green end-to-end; this PRP file is committed as `docs(repo)` (the E1–E5 precedent).

## Why

- "showcase_rich demo pipeline runs green end-to-end after E6" is the **last open
  success criterion** on umbrella #380 — every other epic (#334, #335, #332, #268,
  #237) is closed as of 2026-06-12. Nothing verifies their *combined* behavior yet.
- The five fixes interact: E1 changed the failure surface E2 classifies; E5's seeder
  coupling changes the data every showcase step trains on; E4 moved an import the
  alembic cold-boot path exercises; E3 only manifests in a real browser over LAN HTTP.
  An isolated-PR-green ≠ system-green.
- The umbrella is also the flow-pack dogfood evidence (#368/#375) — a clean,
  evidence-linked close-out is part of the methodology being proven.

## What

A verification campaign, not a feature. No `app/` or `frontend/` source change is
in scope. The only repo change this PRP itself produces is the PRP file
(`PRPs/PRP-reliability-E6-release-gate.md`) committed as
`docs(repo): track reliability E6 prp (#387)`.

### Success Criteria (mirror of #387 exit criteria)

- [ ] Fresh stack rebuilt: `docker compose down -v && docker compose up -d &&
      uv run alembic upgrade head` exits clean (this is ALSO the E4 cold-boot proof).
- [ ] showcase_rich dogfood green end-to-end via the `/showcase` page loaded over a
      **plain-HTTP LAN origin** (covers E3 simultaneously) — evidence: final step
      summary + screenshot; no white-screen, no ❌ step.
- [ ] E1 #334 spot check passes: doubled provider prefix → 422 (live PATCH + tests).
- [ ] E2 #335 spot check passes: exhausted fallback → 502 `AGENT_FALLBACK_EXHAUSTED`
      with classified `failures[]` (committed route test on fresh DB + optional live probe).
- [ ] E3 #332 spot check passes: LAN-HTTP page load completes a run without
      white-screen; `safeRandomUUID` vitest green.
- [ ] E4 #268 spot check passes: `ModelFamily` imports from
      `app.shared.model_taxonomy`; zero lazy-import NOTEs reference the old
      registry↔forecasting cycle; alembic cold-boot clean (from the fresh-stack step).
- [ ] E5 #237 spot check passes: seeded grain → train `regression` → price-cut
      simulate → `method == "model_exogenous"` and `units_delta != 0.0`
      (committed integration test + optional live curl chain).
- [ ] All five validation gates green on `dev`.
- [ ] Evidence comment posted on #387; all satisfied checkboxes ticked on #380;
      #380 closed with close-out comment; #387 closed.

## All Needed Context

### Documentation & References

```yaml
# ── The gate's contract ──────────────────────────────────────────────────────
- issue: "#387 — gh issue view 387"
  why: The epic's sub-task list and exit criteria this PRP encodes verbatim.

- issue: "#380 — gh issue view 380"
  why: Umbrella. Success-criteria checklist — the LAST unchecked item
       ("showcase_rich demo pipeline runs green end-to-end after E6") gets ticked
       here; then the issue is closed with a close-out comment.

# ── showcase_rich pipeline (what 'green' means) ─────────────────────────────
- file: app/features/demo/pipeline.py
  why: "_phase_table() (~line 2464) is the step registry. showcase_rich = 24 steps /
       10 phases: data(7: precheck, reset, seed, status, features, phase2_enrichment,
       historical_backfill), modeling(2: train, v2_train), decision(5: backtest,
       register, champion_compat_compare, stale_alias_trigger, safer_promote_flow),
       portfolio(1: batch_preset), planning(2: scenario_simulate_and_save,
       multi_plan_compare), knowledge(3: embedding_provider_probe, rag_index_subset,
       rag_retrieve_probe), verify(1), agents(1: agent_hitl_flow), ops(1:
       ops_snapshot), cleanup(1). READ-ONLY."

- file: docs/_base/RUNBOOKS.md
  why: "'Showcase page (/showcase) pipeline fails at step X' — items 1–27 are the
       per-step diagnosis table. Defines which skips/warns are ACCEPTABLE on a green
       run (see Known Gotchas below). Consult before treating any non-✅ as failure."

- file: docs/_base/API_CONTRACTS.md
  why: "WS /demo/stream contract — start frame, StepEvent shape, pipeline_complete
       fields (winner_model_type, winner_wape, winning_run_id, alias, wall_clock_s,
       v2_run_id). The headless fallback path drives this directly."

- file: frontend/src/pages/showcase.tsx
  why: "UI controls and their request mapping (~line 110-115):
       start({ seed: 42, skip_seed: !reseed, reset: resetDb, scenario }).
       'Re-seed first' checkbox → skip_seed=false. 'Reset database' → reset=true.
       ScenarioPicker carries demo_minimal | showcase_rich | sparse."

# ── E1 spot-check surface (#334) ─────────────────────────────────────────────
- file: app/core/config.py
  why: "validate_model_identifier (line 20) — rejects nested provider prefix
       ('google-gla:google-gla:…') with the 'Did you mean' ValueError; ollama
       multi-colon tags stay valid. Settings.agent_default_model (192) /
       agent_fallback_model (193) field_validator at line 231. READ-ONLY."

- file: app/features/config/tests/test_routes.py
  why: "test_patch_rejects_doubled_provider_prefix (line 120) — the live-route 422
       regression test to re-run."

- file: app/features/config/tests/test_schemas.py
  why: "test_rejects_doubled_provider_prefix (55), test_rejects_mixed_provider_prefix
       (60), test_rejects_doubled_prefix_via_model_validate (134)."

- file: app/features/agents/tests/test_config_validation.py
  why: "test_doubled_prefix_rejected_at_settings_boot (line 41) — the Settings-boot
       validation path."

# ── E2 spot-check surface (#335) ─────────────────────────────────────────────
- file: app/core/exceptions.py
  why: "AgentFallbackExhaustedError → 502 problem+json, code=AGENT_FALLBACK_EXHAUSTED,
       type=…/errors/agent-fallback-exhausted, failures[] extension (line ~272)."

- file: app/features/agents/service.py
  why: "chat fallback-exhausted path (~line 316) and stream path (~line 717,
       error_type='fallback_exhausted', recoverable=true). READ-ONLY."

- file: app/features/agents/tests/test_routes.py
  why: "TestChatRoutes (integration-marked) ::
       test_chat_fallback_exhausted_returns_502_problem_json (line 167) — asserts 502,
       code, two classified failures (model_not_found + quota_exhausted), secret
       scrubbing. This is the committed ≥2-failure-leg proof; re-run it."

# ── E3 spot-check surface (#332) ─────────────────────────────────────────────
- file: frontend/src/lib/uuid-utils.ts
  why: "safeRandomUUID — crypto.randomUUID → getRandomValues-v4 → Math.random-v4
       fallback chain."

- file: frontend/src/lib/uuid-utils.test.ts
  why: "vitest incl. the explicit 'LAN-HTTP shape' case (randomUUID undefined).
       Run: cd frontend && pnpm test --run src/lib/uuid-utils.test.ts"

- file: frontend/eslint.config.js
  why: "no-restricted-properties guard (~lines 30-44) banning raw crypto.randomUUID."

# ── E4 spot-check surface (#268) ─────────────────────────────────────────────
- file: app/shared/model_taxonomy.py
  why: "Exports ModelFamily (str Enum: BASELINE/TREE/ADDITIVE) + model_family_for +
       _MODEL_FAMILY_MAP. Module docstring documents the resolved cycle. READ-ONLY."

- file: docs/_base/ARCHITECTURE.md
  why: "'Cross-slice read-only import pattern' section — records #268 as RESOLVED;
       the ONLY legitimately remaining lazy pair is forecasting↔jobs."

# ── E5 spot-check surface (#237) ─────────────────────────────────────────────
- file: app/features/scenarios/tests/test_routes_integration.py
  why: "TestModelExogenousOnSeededData::test_seeded_train_simulate_price_cut_moves_demand
       (line 480) — THE committed end-to-end proof: seeded elastic grain → train
       regression → simulate -20% price cut → method=='model_exogenous' &&
       units_delta != 0.0. Re-run it on the fresh DB. Also shows the exact live-curl
       request bodies (train: lines 486-496, simulate: lines 503-516)."

- file: PRPs/PRP-reliability-E5-model-exogenous-price-inertia.md
  why: "The E5 verdict + fix narrative — context for interpreting a failure here
       (seeder coupling flag RetailPatternConfig.price_sales_coupling=True)."

# ── Close-out mechanics ──────────────────────────────────────────────────────
- file: .claude/rules/umbrella-issue.md
  why: "Write discipline for gh mutations: dry-run echo → idempotent check →
       approval gate → confirm. Applies to the #380 body edit + closes."

- file: .claude/rules/output-formatting.md
  why: "Evidence comment format: emoji status indicators, box separators, ≤40 lines."
```

### Current Codebase tree (verification-relevant subset)

```bash
app/core/config.py                  # validate_model_identifier (E1)
app/core/exceptions.py              # AGENT_FALLBACK_EXHAUSTED (E2)
app/shared/model_taxonomy.py        # ModelFamily home (E4)
app/features/demo/pipeline.py       # _phase_table — 24-step showcase_rich registry
app/features/config/tests/          # E1 regression tests
app/features/agents/tests/          # E2 route test (integration), E1 boot test
app/features/scenarios/tests/test_routes_integration.py  # E5 e2e test (integration)
frontend/src/lib/uuid-utils.{ts,test.ts}                 # E3
frontend/src/pages/showcase.tsx     # dogfood entry point
scripts/run_demo.py                 # legacy CLI pipeline (NOT the dogfood target)
```

### Desired Codebase tree

```bash
PRPs/PRP-reliability-E6-release-gate.md   # this file — the ONLY tracked change
# No app/, frontend/, alembic/, or docs/_base/ source change is in scope.
```

### Known Gotchas & Environment Quirks

```python
# ── STOP RULE (governs the whole epic) ───────────────────────────────────────
# If ANY spot check or the dogfood FAILS: capture evidence (response body /
# screenshot / log excerpt), open a NEW fix issue referencing #380 + the failed
# epic issue, comment the failure on #387, and STOP. The release gate never
# fixes forward — a fix is a new branch/PR through the normal flow, and the
# gate re-runs after it merges.

# ── Fresh stack / processes ──────────────────────────────────────────────────
# GOTCHA: a stale uvicorn from a prior session can hold :8123 — curl then hits
# OLD code while you think you're testing dev. Before starting the backend:
#   lsof -iTCP:8123 -sTCP:LISTEN   # kill any stale PID first
# GOTCHA: `docker compose down -v` ERASES the DB incl. RAG corpus and app_config
# runtime overrides (agent model settings revert to .env values on next boot).
# That's desired here (clean gate), but means: re-check GET /config/ai after boot.
# GOTCHA: run the BACKEND AS LOCAL UVICORN (uv run uvicorn app.main:app --port
# 8123), NOT the compose backend container — model artifacts must land on the
# host filesystem for verify/feature-metadata steps, and the docker-compose.yml
# default brings up Postgres only on :5433 anyway.
# GOTCHA: pnpm 11 depsStatusCheck can stall `pnpm dev` — start Vite directly:
#   cd frontend && ./node_modules/.bin/vite --host 0.0.0.0

# ── Dogfood / browser ────────────────────────────────────────────────────────
# CRITICAL (E3): crypto.randomUUID is undefined only in NON-SECURE contexts.
# http://localhost:5173 IS a secure context — it cannot reproduce #332. Load the
# page via a real LAN IP: http://$(hostname -I | awk '{print $1}'):5173/showcase.
# frontend/.env VITE_API_BASE_URL=http://localhost:8123 still works when browsing
# from this same host (the browser resolves localhost locally), and the backend
# CORS dev regex already allows 10.x/192.168.x/172.16-31.x origins.
# GOTCHA: Playwright MCP and `playwright install` both fail on this host. Use
# native Python Playwright with executable_path="/snap/bin/chromium", or the
# agent-browser skill. Verify the chromium path exists before relying on it.
# ACCEPTABLE NON-GREEN STEPS on showcase_rich (RUNBOOKS items 9-26): per #387,
# "provider-dependent steps may ⏭️ skip per RUNBOOKS, pipeline still green":
#   - agent_hitl_flow ⏭️ — no key for agent_default_model provider / approval
#     timeout / model didn't call save_scenario (known recurring skip on this host)
#   - rag_index_subset / rag_retrieve_probe ⏭️ — embedding provider unreachable
#     or rejected credentials (#329); embedding_provider_probe ✅ even when
#     reachable=False
#   - verify ⏭️ — expected on a prophet_like (V2) winner: artifact roots differ
#   - champion_compat_compare / safer_promote_flow ⏭️ — missing V2 run or V1
#     baseline (should NOT happen with Re-seed first ticked — investigate if hit)
#   - batch_preset ⚠️ — 90 s poll timeout on a loaded laptop (non-fatal)
#   - ops_snapshot ⚠️ — /ops/* unavailable (warn, never fail)
# ANY ❌ step = gate failure → STOP RULE.
# GOTCHA: only one pipeline runs at a time (module asyncio.Lock); a second start
# gets one `error` event / POST gets 409. Stop button releases the lock in ~5 s.
# Wall-clock: budget ~5-10 min for showcase_rich on this laptop; per-step HTTP
# timeout is 120 s, batch poll 90 s, HITL approval 90 s.

# ── Spot-check mechanics ─────────────────────────────────────────────────────
# E2 (integration test): TestChatRoutes is @pytest.mark.integration — needs the
# compose Postgres up + migrations applied. Run TARGETED tests, NOT the full
# integration suite: the full suite is known to pollute shared DB state mid-run
# (destructive seeder tests) and produce false negatives. Run the E2 + E5 tests
# individually, E5 BEFORE anything that mutates seeded data, or on a fresh DB.
# E2 (optional live probe): PATCH /config/ai persists overrides to app_config
# AND applies live. To provoke real exhaustion: GET /config/ai (record current
# agent_default_model/agent_fallback_model), PATCH both to
# "ollama:nonexistent-model-e6" (valid format — passes E1 validation; Ollama at
# localhost:11434 returns 404 → reason="model_not_found"), create session, chat,
# expect 502; then PATCH the recorded values BACK. NEVER leave the override in
# place — it would break the showcase agent step on the next run.
# E5 (live curl variant): the /scenarios/* run_id is the ARTIFACT KEY parsed
# from TrainResponse.model_path ("model_{key}.joblib" → stem minus "model_"),
# NOT the registry model_run.run_id. Different ID spaces.
# E5 (live curl variant): the seeder does NOT reset Postgres ID sequences —
# discover real store/product IDs + date window via GET /dimensions/stores,
# GET /dimensions/products, and the seeded calendar range; never assume id=1.
#   (Fresh `down -v` stack makes IDs 1-based again, but discover anyway.)
# E4: the ONLY remaining lazy-import NOTE in app/ must be the forecasting↔jobs
# pair (app/features/forecasting/service.py:~1050). Anything mentioning a
# ModelFamily / registry↔forecasting cycle = E4 regression → STOP RULE.

# ── Validation gates / frontend ──────────────────────────────────────────────
# GOTCHA: `pnpm tsc --noEmit` is VACUOUS here (solution-style tsconfig checks 0
# files) and `tsc -b` has known pre-existing failures on dev — frontend
# type-check is NOT one of this gate's five criteria. Frontend evidence = the
# uuid-utils vitest + the browser dogfood.
# The five gates (#387 wording): ruff check, ruff format --check, mypy app/,
# pyright app/, pytest -m "not integration".
# GOTCHA: app/core/tests/test_config.py settings tests can fail if they pick up
# the local .env — known issue, fixed via Settings(_env_file=None) in the tests
# already; if a gate failure looks like .env-bleed, see RUNBOOKS before STOPping.

# ── GitHub close-out ─────────────────────────────────────────────────────────
# Write discipline (.claude/rules/umbrella-issue.md): echo each gh mutation
# before running it.
# DRIFT WARNING (verified 2026-06-12): #380's live body has ALL 12 checkboxes
# unticked — the five per-epic success criteria were never ticked when E1-E5
# closed, and the E6 Decomposition line still says "not yet created". Closing
# the umbrella with unticked boxes contradicts umbrella-issue.md ("checkbox list
# an outside reviewer uses as the close-or-not decision"). So: tick EVERY
# satisfied box (5 success criteria + 5 E1-E5 decomposition lines + the final
# showcase_rich criterion + the E6 line), and update the E6 line's "not yet
# created" → "#387". Do NOT pattern-match checkbox text literally — the live
# body contains backticks (`showcase_rich`) the issue text elsewhere omits;
# fetch with `gh issue view 380 --json body`, edit the markdown, push back via
# `gh issue edit 380 --body-file`. Preserve everything else byte-identical —
# the body carries an HTML provenance comment.
# Close order: evidence comment on #387 → tick #380 → close #380 (comment links
# #387 evidence) → close #387 last (it's the epic doing the closing).
```

## Implementation Blueprint

### Data models and structure

None. This epic ships zero schemas, zero migrations, zero source changes.

### List of tasks in execution order

```yaml
Task 0 — Preflight:
  VERIFY branch: git switch dev && git pull → clean, up to date with origin/dev.
  VERIFY no stale server: lsof -iTCP:8123 -sTCP:LISTEN → kill stale PIDs.
  VERIFY chromium for dogfood: ls /snap/bin/chromium (else plan agent-browser skill).
  RECORD: git rev-parse HEAD → the SHA all evidence refers to.

Task 1 — Fresh stack (E4 cold-boot proof rides along):
  RUN: docker compose down -v
  RUN: docker compose up -d            # Postgres+pgvector on :5433
  RUN: uv run alembic upgrade head     # MUST exit 0 on the EMPTY db — E4 evidence
  RUN: uv run python scripts/check_db.py   # connectivity sanity
  START backend:  uv run uvicorn app.main:app --port 8123  (background, log to file)
  VERIFY: curl -s http://localhost:8123/health → {"status":"ok"}
  START frontend: cd frontend && ./node_modules/.bin/vite --host 0.0.0.0  (background)
  VERIFY: curl -sI http://localhost:5173 → 200.

Task 2 — showcase_rich dogfood over LAN origin (primary deliverable; covers E3):
  DISCOVER LAN IP: hostname -I | awk '{print $1}'
  DRIVE BROWSER (native Python Playwright, executable_path=/snap/bin/chromium):
    - goto http://<LAN_IP>:5173/showcase     # NON-secure context — E3 surface
    - assert page renders (no white-screen), zero console errors mentioning
      randomUUID / crypto
    - select scenario "showcase_rich"; tick "Re-seed first"
      (→ {seed:42, skip_seed:false, reset:false, scenario:"showcase_rich"})
    - click Run; poll up to ~10 min for the completion banner
    - if the HITL step card shows an Approve button within its 90 s window,
      click it (a ⏭️ skip on agent_hitl_flow is acceptable per RUNBOOKS 23-25)
    - capture: full-page screenshot + the per-step status list (24 rows)
  ASSERT: pipeline green — every step ✅/⏭️/⚠️ per the acceptable-list in Known
    Gotchas; zero ❌. Record winner_model_type / winner_wape / v2_run_id from the
    summary if surfaced.
  FALLBACK (only if browser automation is unusable): drive WS /demo/stream
    headlessly with start frame {"seed":42,"reset":false,"skip_seed":false,
    "scenario":"showcase_rich"}, assert pipeline_complete + zero fail events —
    THEN still do a LAN-origin page load + one demo_minimal UI run for E3.
  ON ANY ❌ STEP: STOP RULE (RUNBOOKS items 1-27 give the diagnosis per step).

Task 3 — E1 #334 spot check (doubled provider prefix → 422):
  LIVE: curl -s -o /dev/null -w '%{http_code}' -X PATCH \
          http://localhost:8123/config/ai -H 'Content-Type: application/json' \
          -d '{"agent_default_model":"google-gla:google-gla:gemini-2.0-flash"}'
        → expect 422; re-run without -o to capture the problem+json body
        (RFC 7807, mentions nested provider prefix). NOTE: a 422 means nothing
        was persisted — no restore needed.
  TESTS: uv run pytest \
          app/features/config/tests/test_schemas.py \
          app/features/config/tests/test_routes.py::TestUpdateAIConfig \
          "app/features/agents/tests/test_config_validation.py::TestModelIdentifierValidation::test_doubled_prefix_rejected_at_settings_boot" \
          -v -k "doubled or mixed or prefix"

Task 4 — E2 #335 spot check (fallback exhaustion classified):
  TEST (the committed ≥2-leg proof; integration-marked, fresh DB is up):
    uv run pytest "app/features/agents/tests/test_routes.py::TestChatRoutes::test_chat_fallback_exhausted_returns_502_problem_json" -v -m integration
  OPTIONAL LIVE PROBE (only if Ollama responds on localhost:11434):
    - GET /config/ai → record agent_default_model + agent_fallback_model
    - PATCH /config/ai {"agent_default_model":"ollama:nonexistent-model-e6",
                        "agent_fallback_model":"ollama:nonexistent-model-e6"}
    - POST /agents/sessions {"agent_type":"experiment"} → session_id
    - POST /agents/sessions/{id}/chat {"message":"hello"}
      → expect 502 application/problem+json, code=AGENT_FALLBACK_EXHAUSTED,
        failures[] with reason model_not_found, no secret values in body
    - DELETE the session; PATCH /config/ai back to the recorded values; GET to
      confirm restore. (MANDATORY restore — see Known Gotchas.)

Task 5 — E4 #268 spot check (taxonomy home + no stale cycle NOTEs):
  RUN: uv run python -c "from app.shared.model_taxonomy import ModelFamily, model_family_for; print(model_family_for('regression'), model_family_for('prophet_like'), model_family_for('naive'))"
       → "ModelFamily.TREE ModelFamily.ADDITIVE ModelFamily.BASELINE"
  RUN: grep -rn "ModelFamily" app/ --include="*.py" | grep -v "model_taxonomy" \
         | grep -iE "lazy|cycle|circular|NOTE" → MUST be empty
  RUN: grep -rn "NOTE" app/ --include="*.py" | grep -iE "lazy|cycle|circular"
       → ONLY the forecasting↔jobs pair (app/features/forecasting/service.py).
  EVIDENCE: alembic cold-boot already proven in Task 1 (upgrade head on empty DB).

Task 6 — E5 #237 spot check (price cut moves model_exogenous demand):
  TEST (the committed e2e proof; run BEFORE anything further mutates seed data —
        Task 2's run is fine, the test seeds its own isolated grain and cleans up):
    uv run pytest "app/features/scenarios/tests/test_routes_integration.py::TestModelExogenousOnSeededData::test_seeded_train_simulate_price_cut_moves_demand" -v -m integration
  OPTIONAL LIVE CURL CHAIN (mirrors the test, against the showcase-seeded data):
    - GET /dimensions/stores + /dimensions/products → pick a real (store_id,
      product_id) with sales (never assume id=1)
    - POST /forecasting/train {"store_id":S,"product_id":P,
        "train_start_date":"<window start>","train_end_date":"<window end>",
        "config":{"model_type":"regression"}} → 200; model_path
    - run_id = basename(model_path) minus "model_" prefix minus ".joblib"
    - POST /scenarios/simulate {"run_id":run_id,"horizon":14,"assumptions":
        {"price":{"change_pct":-0.20,"start_date":"<D+1>","end_date":"<D+14>"}}}
      → 200, method=="model_exogenous", units_delta != 0.0

Task 7 — Five validation gates on dev:
  RUN: uv run ruff check . && uv run ruff format --check .
  RUN: uv run mypy app/ && uv run pyright app/
  RUN: uv run pytest -v -m "not integration"
  PLUS frontend E3 unit evidence: cd frontend && pnpm test --run src/lib/uuid-utils.test.ts
  ALL must pass. A failure here on untouched dev = regression → STOP RULE.

Task 8 — Evidence + close-out (gh write discipline: echo each command first):
  COMMIT this PRP file FIRST (before any close): branch docs/reliability-e6-prp
    off dev, `docs(repo): track reliability E6 prp (#387)`, PR into dev (E5
    precedent: commit 82300eb). NOTE: the PR needs 1 approving review + CI —
    it will NOT merge autonomously; opening it is enough to proceed, the merge
    lands through the normal flow.
  COMMENT on #387: evidence block per .claude/rules/output-formatting.md —
    HEAD SHA, fresh-stack proof, dogfood result table (24 steps with ✅/⏭️/⚠️ and
    skip reasons), the five spot-check results with the exact commands run,
    gate results, screenshot attached or path referenced.
  EDIT #380 body (see DRIFT WARNING in Known Gotchas): tick ALL satisfied
    checkboxes — the 5 per-epic success criteria, the 5 E1-E5 Decomposition
    lines, the E6 Decomposition line (updating "not yet created" → "#387"), and
    the final "...showcase_rich demo pipeline runs green end-to-end after E6"
    criterion. Preserve everything else byte-identical.
  CLOSE #380: gh issue close 380 --comment "<close-out linking the #387 evidence
    comment + per-epic issue list #334 #335 #332 #268 #237>"
  CLOSE #387: gh issue close 387 --comment "<gate complete — evidence above>"

Task 9 — Teardown:
  STOP the background uvicorn + vite processes started in Task 1.
  LEAVE the seeded DB in place (operator-visible artifacts are fine post-gate).
```

### Integration Points

```yaml
GITHUB:
  - issue #387: evidence comment + close
  - issue #380: body checkbox tick + close-out comment + close
  - PR: docs(repo) commit of this PRP file into dev

RUNTIME (no code integration — consumers only):
  - docker compose Postgres :5433, local uvicorn :8123, Vite :5173 (LAN-bound)
  - Ollama localhost:11434 (optional, E2 live probe + agent/knowledge steps)
```

## Validation Loop

### Level 1 — environment sanity (before anything else)

```bash
git -C . status --short && git rev-parse --abbrev-ref HEAD     # dev, clean
lsof -iTCP:8123 -sTCP:LISTEN                                   # must be empty
docker compose ps                                              # postgres healthy
curl -s http://localhost:8123/health                           # {"status":"ok"} after Task 1
```

### Level 2 — targeted regression tests (the per-epic committed proofs)

```bash
# E1
uv run pytest app/features/config/tests/ app/features/agents/tests/test_config_validation.py -v -k "doubled or mixed or prefix"
# E2 (integration — fresh DB)
uv run pytest "app/features/agents/tests/test_routes.py::TestChatRoutes::test_chat_fallback_exhausted_returns_502_problem_json" -v -m integration
# E3
cd frontend && pnpm test --run src/lib/uuid-utils.test.ts && cd ..
# E4
uv run python -c "from app.shared.model_taxonomy import ModelFamily, model_family_for; print(model_family_for('regression'))"
# E5 (integration — self-seeding, self-cleaning)
uv run pytest "app/features/scenarios/tests/test_routes_integration.py::TestModelExogenousOnSeededData::test_seeded_train_simulate_price_cut_moves_demand" -v -m integration
```

### Level 3 — live system (dogfood + probes)

```bash
# Dogfood: browser at http://<LAN_IP>:5173/showcase, scenario=showcase_rich,
# Re-seed first ticked → green pipeline, screenshot captured. (Task 2.)

# E1 live:
curl -s -X PATCH http://localhost:8123/config/ai -H 'Content-Type: application/json' \
  -d '{"agent_default_model":"google-gla:google-gla:gemini-2.0-flash"}' | head -c 400
# → 422 problem+json mentioning the nested provider prefix

# E5 live: train→simulate chain per Task 6 (IDs discovered, never assumed).
```

### Level 4 — repo gates

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
uv run pytest -v -m "not integration"
```

## Final validation Checklist

- [ ] Fresh stack: `down -v` → `up -d` → `alembic upgrade head` clean (E4 cold-boot)
- [ ] showcase_rich dogfood: 24 steps / 10 phases, zero ❌, over plain-HTTP LAN
      origin, screenshot + step table captured (E3 white-screen proof included)
- [ ] E1: live PATCH → 422; doubled/mixed-prefix tests green
- [ ] E2: `test_chat_fallback_exhausted_returns_502_problem_json` green
      (+ optional live 502 probe, config RESTORED afterwards)
- [ ] E3: uuid-utils vitest green; LAN page load clean
- [ ] E4: taxonomy import one-liner correct; zero stale cycle NOTEs
      (only forecasting↔jobs remains)
- [ ] E5: `test_seeded_train_simulate_price_cut_moves_demand` green
      (+ optional live chain: method=model_exogenous, units_delta != 0.0)
- [ ] Five gates green: ruff, format, mypy, pyright, unit pytest
- [ ] Evidence comment on #387; #380 checkbox ticked; #380 closed; #387 closed
- [ ] This PRP committed via `docs(repo): track reliability E6 prp (#387)`
- [ ] Background servers stopped; no config overrides left in app_config

---

## Anti-Patterns to Avoid

- ❌ Don't fix forward inside the gate — a failed check files a new issue and STOPS
- ❌ Don't treat a RUNBOOKS-sanctioned ⏭️/⚠️ as failure — but don't hand-wave a ❌ either
- ❌ Don't verify E3 on localhost — it's a secure context; #332 only manifests on LAN IP
- ❌ Don't run the FULL integration suite as a gate — known shared-state pollution;
     run the targeted tests listed above
- ❌ Don't leave `ollama:nonexistent-model-e6` (or any probe override) in app_config
- ❌ Don't assume store/product IDs or date windows — discover via /dimensions/*
- ❌ Don't rewrite #380's body beyond ticking satisfied checkboxes + the E6 line update
- ❌ Don't `gh pr merge --merge` anything dev→main here — this epic ends at `dev`;
     the release cut is a separate decision (stop-and-ask gate)

## Confidence Score: 8.5/10

One-pass success likelihood is high: every spot check maps to a committed,
named regression test plus an exact live command; the dogfood path, acceptable
skip list, and environment traps (stale uvicorn, LAN secure-context, ID
discovery, config restore) are all pinned with file:line grounding. Residual
risk (−1.5): the showcase_rich browser run has non-deterministic legs
(agent_hitl_flow, provider reachability, batch timing on a loaded laptop) that
may force a re-run or RUNBOOKS triage, and host browser automation has a known
fragile setup (snap chromium path).
