# INITIAL-showcase-40-planning-knowledge-lifecycle.md — Planning + Knowledge Lifecycle

> **Status:** Planning. Third sliced INITIAL of the four-PRP `/showcase` upgrade epic.
> **Parent:** `PRPs/INITIAL/INITIAL-showcase-rich-demo-control-center.md`
> **Sequence index:** `PRPs/INITIAL/INITIAL-showcase-rich-demo-index.md`
> **Prerequisites:** PRP-38 merged.
> **Unlocks:** PRP-41 (which consumes both the saved scenarios and the
> indexed RAG corpus in its agent HITL + ops snapshot demo).

## FEATURE:

Add the **planning** and **knowledge** lifecycle phases to `/showcase` so a
visitor running `showcase-rich` sees the full what-if workflow (simulate →
save → multi-plan compare) and the curated RAG corpus workflow (provider
probe → index → semantic-retrieve) — both driven end-to-end against the
champion run PRP-38 registered, both deep-linkable into the existing
`/visualize/planner` and `/knowledge` pages.

After this PRP merges, a visitor running `/showcase` on the `showcase-rich`
scenario sees:

- Two named scenario plans persisted in the plan library (a 10% price-cut
  plan and a holiday-set plan), visible on `/visualize/planner`.
- A multi-plan compare row ranking the two plans against the shared baseline.
- The 5 curated user-guide markdown files indexed in the RAG corpus, visible
  on `/knowledge` with chunk counts.
- A successful semantic-retrieve probe returning at least one hit with a
  populated similarity score.
- When the configured embedding provider is unreachable, the entire
  `knowledge` phase reports `skip` for its three steps (NOT `fail`) with a
  clear `detail`, and the pipeline still goes green.

### Scope (one shippable PR)

**Backend (`app/features/demo/pipeline.py`):**

Add five new steps under two new phases.

**Phase: `planning`** — **new** phase. Insert after the latest decision-class
phase that exists at merge time and before the existing `verify` phase:

- If PRP-39 has NOT merged yet → insert immediately after the existing
  `decision` phase (the one PRP-38 shipped with `backtest` → `register`),
  before `verify`.
- If PRP-39 has merged → insert immediately after PRP-39's new `portfolio`
  phase, before `verify`.

Adopt a relative-anchor insertion in `_phase_table()` (e.g.,
"immediately before the `verify` phase row") — NEVER an absolute index.
PRP-39 may be authored / merged in parallel; the second-to-merge PRP
must rebase its phase-table edit cleanly without re-numbering.

- `scenario_simulate_and_save` — `POST /scenarios/simulate` with a
  `PriceAssumption` (e.g., `pct_change=-0.10` for a 10% cut) against the
  champion run (`demo-production` alias resolved to the underlying
  forecast-artifact `run_id` — note this is the artifact-key `run_id`, NOT
  the registry `model_run.run_id`; see the gotcha in § Risks). Then
  `POST /scenarios` to persist the comparison snapshot as a named plan
  `showcase-price-cut-10pct` with tags `["showcase","price"]`. Captures
  `scenario_id`, baseline-vs-scenario units delta, revenue delta, and the
  `method` (`heuristic` or `model_exogenous` depending on the underlying
  baseline) in `step.data`.
- `multi_plan_compare` — Persist a SECOND plan with a `HolidayAssumption`
  (e.g., a single in-horizon holiday-set day with `uplift_multiplier=1.20`)
  named `showcase-holiday-uplift`. Then `POST /scenarios/compare` with
  `scenario_ids=[price_cut_id, holiday_uplift_id]` and a sensible `rank_by`
  (e.g., `revenue_delta`). Captures the ranked-row summary
  (`winner_scenario_id`, per-plan `units_delta`, `revenue_delta`) in
  `step.data`.

**Phase: `knowledge`** — **new** phase. Insert immediately after PRP-40's
own `planning` phase (both phases land in the same PRP, so the anchor is
local) and before the existing `verify` phase. Same relative-anchor rule
as `planning` — no absolute indexes.

- `embedding_provider_probe` — `GET /config/providers/health`. The step
  considers the embedding provider reachable when either (a) the configured
  cloud provider's API key is set OR (b) the Ollama probe returns healthy.
  When neither holds, the step emits `pass` with `detail="embedding
  provider unreachable — knowledge phase will skip"` AND sets a context flag
  the next two steps consult so THEY emit `skip` (not `fail`). Mirrors the
  `_llm_key_present()` pattern at `app/features/demo/pipeline.py:203` —
  add a sibling `_embedding_provider_reachable()` helper that performs the
  same kind of presence-only check (no value logging, per
  `.claude/rules/security-patterns.md`).
- `rag_index_subset` — `POST /rag/index/project-docs` with a request shape
  scoped to the curated 5-file subset under `docs/user-guide/`
  (`getting-started.md`, `dashboard-guide.md`, `feature-reference.md`,
  `agents-and-rag-guide.md`, `advanced-forecasting-guide.md`). The existing
  endpoint takes `include_docs` / `include_prps` / `include_root` toggles —
  if a sub-path filter does not yet exist on the request schema, the
  Task 1 contract probe will catch it and the PRP author must choose
  between (a) using the existing `include_docs=true` and accepting the
  broader corpus or (b) a tiny additive `path_prefix: str | None` field on
  `IndexProjectDocsRequest`. Either way, captures per-file `status` plus
  aggregate `total_chunks` / `failed` in `step.data`.
- `rag_retrieve_probe` — `POST /rag/retrieve` with
  `query="How do I run the demo pipeline?"`, `top_k=3`. Asserts at least one
  hit; captures the top-1 hit's `source.title` (or filename) and
  `similarity_score` in `step.data`. A zero-result response is `warn`, not
  `fail` (it means the corpus indexed but the query didn't match — still
  not a pipeline error).

Each new step:
- Emits `step_start` + `step_complete` events with
  `phase_name=planning|knowledge` (Optional fields already added by PRP-38).
- Uses `_HTTP_TIMEOUT` (120 s).
- Mirrors the existing `_StepError` RFC 7807 surfacing.
- The two `knowledge`-phase index/retrieve steps consult the
  `embedding_provider_probe` context flag and emit `skip` when set.

**Frontend (`frontend/src/pages/showcase.tsx` + `components/demo/`):**

- Extend `PHASE_DEFS` (`frontend/src/components/demo/PHASE_DEFS.ts`) with
  the new `planning` and `knowledge` phases — backend `_phase_table()`
  ships the matching addition in lockstep.
- Per-step Inspect button (PRP-38 pattern):
  - `scenario_simulate_and_save` → `/visualize/planner?scenario_id={id}`
  - `multi_plan_compare` → `/visualize/planner` (the saved-plans library
    surfaces the two plans + the most-recent compare result)
  - `embedding_provider_probe` → `/admin` (provider health surface)
  - `rag_index_subset` → `/knowledge`
  - `rag_retrieve_probe` → `/knowledge`
- Step card extensions:
  - `scenario_simulate_and_save` card renders a one-row mini summary:
    `plan=showcase-price-cut-10pct · Δunits=… · Δrevenue=… · method=…`.
  - `multi_plan_compare` card renders `winner=… · ranked_by=revenue_delta`.
  - `embedding_provider_probe` card renders the resolved provider chip
    (`openai` / `anthropic` / `ollama` / `none`).
  - `rag_index_subset` card renders `files_indexed/5 · chunks=… ·
    failed=…`.
  - `rag_retrieve_probe` card renders the top-1 hit title + similarity
    score (or "no hits — corpus empty?" on `warn`).
- No new shadcn primitives required — Card + Badge + Button already
  imported by the PRP-38 step card.

### What PRP-40 is NOT

- Champion-compat compare, stale-alias trigger, safer-Promote dialog,
  batch preset/matrix — **PRP-39** (prerequisite-adjacent, NOT a hard
  prerequisite for PRP-40; PRP-40 can be authored in parallel with
  PRP-39 as long as each PRP's contract-probe report is done first).
- Agent HITL flow, ops snapshot KPI strip, Inspect-Artifacts post-run
  panel, localStorage run history, Stop button, walkthrough doc — **PRP-41**.

### Acceptance criteria

| # | Criterion | Verifiable by |
|---|-----------|---------------|
| C1 | After a `showcase-rich` run, `/visualize/planner` shows ≥ 2 named scenario plans (price-cut + holiday-set) and a multi-plan-compare result. | Manual dogfood |
| C2 | After a `showcase-rich` run, `/knowledge` lists the 5 indexed user-guide docs with chunk counts; a semantic search returns hits. | Manual dogfood |
| C3 | When the embedding provider is unreachable, the `knowledge` phase emits `skip` for the three knowledge steps with a clear detail; pipeline still goes green. | `pytest -m integration` with a key-stripped env fixture |
| C4 | `showcase-rich` end-to-end (PRP-38 + PRP-39 + PRP-40 phases) still ≤ 240 s. | `pytest -m integration` wall-clock assertion |
| C5 | Backend `_phase_table()` and frontend `PHASE_DEFS` still match (both updated in lockstep). | `test_phase_table_stable` (backend) + `PHASE_DEFS.test.ts` (frontend) |
| C6 | All five validation gates green. | CI |

## EXAMPLES:

**Pattern to imitate (the existing demo slice):**

- `app/features/demo/pipeline.py:203-219` — `_llm_key_present()`
  skip-gracefully gate. PRP-40's `_embedding_provider_reachable()` mirrors
  this verbatim: presence-only checks, key-name-only logging, never the
  value.
- `app/features/demo/pipeline.py::step_register` — pattern for the multi-step
  service-orchestration shape `scenario_simulate_and_save` and
  `multi_plan_compare` follow (a step that drives two endpoints in sequence
  and captures both response payloads into `step.data`).
- `app/features/demo/tests/test_pipeline.py` — pattern for per-step
  coverage, including a skip-gracefully variant.

**Scenarios slice (consumed over ASGI — NEVER imported):**

- `app/features/scenarios/routes.py:34` — `POST /scenarios/simulate`
  (response: `ScenarioComparison`).
- `app/features/scenarios/routes.py:86` — `POST /scenarios` (saves a plan;
  response: `ScenarioPlanResponse` with `scenario_id`).
- `app/features/scenarios/routes.py:132` — `POST /scenarios/compare`
  (response: `MultiScenarioComparison`).
- `app/features/scenarios/schemas.py:37` — `PriceAssumption` (the
  `scenario_simulate_and_save` step uses this).
- `app/features/scenarios/schemas.py:82` — `HolidayAssumption` (the
  `multi_plan_compare` step's second plan uses this).
- `app/features/scenarios/schemas.py:122` — `ScenarioAssumptions` envelope.
- `app/features/scenarios/schemas.py:147` — `SimulateScenarioRequest`
  (note the `run_id` field is the artifact-key id, NOT
  `model_run.run_id` — see Risks).
- `app/features/scenarios/schemas.py:176` — `CreateScenarioRequest`
  (name + assumptions + optional tags).
- `app/features/scenarios/schemas.py:409` — `CompareScenariosRequest`
  (2-5 `scenario_ids` + `rank_by`).

**RAG slice (consumed over ASGI):**

- `app/features/rag/routes.py:138` — `POST /rag/index/project-docs`
  (`IndexProjectDocsRequest` with `include_docs` / `include_prps` /
  `include_root` toggles + per-file results + aggregate counts +
  `502` problem+json on embedding-provider failure).
- `app/features/rag/routes.py:228` — `POST /rag/retrieve`
  (`RetrieveRequest` with `query`, `top_k`, `similarity_threshold`).
- `docs/user-guide/getting-started.md` + `dashboard-guide.md` +
  `feature-reference.md` + `agents-and-rag-guide.md` +
  `advanced-forecasting-guide.md` — the curated 5-file corpus
  `rag_index_subset` targets.

**Config slice (consumed over ASGI):**

- `app/features/config/routes.py:58` — `GET /config/providers/health`
  (response: `list[ProviderHealth]` — Ollama probed live, cloud providers
  reflect API-key presence). The `embedding_provider_probe` step parses
  this against the configured `rag_embedding_provider` and the
  reachable-or-not decision flows from the result.

## DOCUMENTATION:

**Internal (load when authoring PRP-40):**

- `AGENTS.md` § Architecture & Conventions — vertical-slice rule.
  `app/features/demo/` MUST NOT import from `app/features/{scenarios,rag,config}`.
- `docs/_base/API_CONTRACTS.md` — scenarios, RAG, and config endpoints. The
  Task 1 contract probe verifies every cited field against the actual `dev`
  branch, NOT against this doc (the doc is the orientation, code is the truth).
- `docs/_base/RUNBOOKS.md` § "Showcase page (`/showcase`) pipeline fails at
  step X" — extend additively for `scenario_simulate_and_save`,
  `multi_plan_compare`, `embedding_provider_probe`, `rag_index_subset`,
  `rag_retrieve_probe` failure modes.
- `docs/_base/SECURITY.md` § "Secrets Management" — key-name-only logging
  in the new helper.
- `docs/_base/DOMAIN_MODEL.md` § "scenario plan" + "applied factor" +
  "model_exogenous" — the ubiquitous-language terms PRP-40's step `detail`
  strings should adopt verbatim.
- `docs/optional-features/03-scenario-simulation-what-if-planning.md` —
  the scenarios slice's design rationale (heuristic vs model_exogenous).
- `.claude/rules/security-patterns.md` — presence-only logging for env-var
  checks; never log decrypted values, even at DEBUG.
- `.claude/rules/test-requirements.md` — new pipeline steps ⇒ new
  per-step tests in `app/features/demo/tests/test_pipeline.py`.
- `.claude/rules/shadcn-ui.md` — no new shadcn primitives expected; if any
  are needed, route them through the `shadcn` skill + MCP.

**External (load via `mcp__claude_ai_contex7__`):**

- FastAPI WebSocket additive payloads: <https://fastapi.tiangolo.com/advanced/websockets/>
- HTTPX ASGITransport (the in-process demo→other-slice call path):
  <https://www.python-httpx.org/async/#calling-into-python-web-apps>
- pgvector index behavior (relevant to the embedding-dim caveat in R4):
  <https://github.com/pgvector/pgvector>

**Prior-art PRPs (read for pattern):**

- `PRPs/PRP-27-*` — the scenarios slice itself (saved-plan + multi-plan
  compare contracts PRP-40 drives).
- `PRPs/PRP-38-showcase-data-modeling-lifecycle.md` — PRP-40's
  prerequisite; ships the phase accordion + the `demo-production` champion
  alias `scenario_simulate_and_save` targets.
- `PRPs/PRP-39-showcase-decision-portfolio-lifecycle.md` — sibling slice;
  PRP-40 follows the same step-card extension pattern and Inspect-link
  conventions.
- `PRPs/ai_docs/prp-37-contract-probe-report.md` — pattern for PRP-40's
  Task 1 contract-probe report.

## OTHER CONSIDERATIONS:

### Hard constraints (from the parent INITIAL — repeated for PRP authoring convenience)

- **No new tables.** The two saved plans persist into the existing
  `scenario_plan` table via the existing `POST /scenarios` endpoint —
  PRP-40 adds no schema.
- **Vertical-slice rule.** `app/features/demo/` does NOT import from
  `app/features/scenarios/`, `app/features/rag/`, or `app/features/config/`.
  All five new steps drive their respective slices over `httpx.ASGITransport`.
- **WebSocket contract additive only.** `StepEvent.data` is already
  `dict[str, Any]` — the new payloads add string/int/float fields, no
  schema bump.
- **Phase table lockstep** — backend `_phase_table()` + frontend
  `PHASE_DEFS` updated together. `test_phase_table_stable` enforces the
  match.
- **Phase insertion uses RELATIVE anchors, not absolute indexes.** PRP-39
  and PRP-40 may be authored / implemented / merged in parallel. Both
  PRPs edit `_phase_table()` and `PHASE_DEFS.ts`. The author must phrase
  every phase-table change as "insert before/after the `<anchor-phase>`
  row" (e.g., "before the `verify` phase row"), never as "insert at row
  index N". This way the second-to-merge PR rebases cleanly without
  re-numbering. The lockstep test catches conflicts at merge time, but
  relative anchors keep the rebase mechanical.
- **Skip gracefully on missing providers.** Every `knowledge`-phase step
  emits `skip` (not `fail`) when the embedding provider isn't reachable.
  Adopt the `_llm_key_present()` pattern verbatim — presence-only checks,
  no value logging.

### Risks specific to PRP-40

| # | Risk | Mitigation |
|---|------|------------|
| R4 (from parent) | RAG embedding-dim mismatch can orphan chunks when providers swap (memory `[[rag-runtime-config-and-corpus-state]]`). | The pipeline runs `rag_index_subset` ONLY after a fresh reset OR against a known-empty curated-corpus space. The PRP-40 PRP MUST document the toggle in the walkthrough: if the operator changes embedding provider, a `clear_rag` toggle (gated by a separate UI control — out of scope for PRP-40) is the supported recovery; otherwise stick to one provider for the showcase. Curated 5-file subset keeps blast radius small. |
| R16 | Scenario `run_id` is the **artifact-key id** (`model_{id}.joblib`), NOT `model_run.run_id` (memory `[[scenario-run-id-vs-registry-run-id]]`). | The `scenario_simulate_and_save` step resolves the `demo-production` alias via `GET /registry/aliases/demo-production` to get `model_run.run_id`, then reads the artifact-key from the alias's run's `artifact_uri` (parses the `model_{KEY}.joblib` filename). The PRP author MUST verify in the Task 1 contract probe that the two ID spaces are still distinct and that the parse pattern is current. |
| R17 | A `regression` baseline triggers `method=model_exogenous` and re-runs through a leakage-safe future feature frame; a non-regression baseline triggers `method=heuristic`. The step's `detail` string must reflect the resolved method or it will mislead the visitor. | Read `method` from the `ScenarioComparison` response and surface it in `step.data` + `step.detail`. Reference: dogfood memory `[[planner-ui-dogfood-findings]]` — `model_exogenous` was inert to price assumptions for some PRP-27 builds; verify behavior in the Task 1 probe AND in the dogfood checklist. |
| R18 | `POST /rag/index/project-docs` does not currently expose a sub-path filter — the existing toggles index `docs/**`, `PRPs/**`, or root markdown wholesale. Restricting to the 5 user-guide files needs either a tiny additive `path_prefix` field on `IndexProjectDocsRequest` OR acceptance of the wider corpus. | Task 1 contract probe MUST resolve this. The PRP author MUST choose one (additive `path_prefix` is the cleanest; the wider-corpus fallback is acceptable but bumps the `rag_index_subset` step's wall-clock budget). |
| R19 | `POST /scenarios/compare` requires 2-5 distinct `scenario_id`s; if `multi_plan_compare`'s second plan persistence fails, the compare step receives 1 id and fails with 422. | Wrap the second save in the same step as the compare; emit `warn` (not `fail`) when the second-plan save fails with a clear `detail` so the visitor sees the first plan was saved successfully. |
| R6 (from parent) | `frontend/.env` LAN-IP regression has bitten 3+ times. | Dogfood checklist verifies `/demo/stream` connects from a `localhost` browser. |
| R7 (from parent) | HANDOFF accuracy — re-run `pnpm tsc --noEmit -p tsconfig.app.json` (NOT the root `tsc --noEmit`). | Required. |
| R8 (from parent) | Module-level `asyncio.Lock` already serializes pipeline runs. | No change needed; document in the walkthrough that a stuck run requires explicit cancel (PRP-41 ships the Stop button). |
| R9 (from parent) | CRLF/LF noise — Edit/Write on CRLF files produces whole-file diffs. | Confine edits to the smallest possible diff; `git diff --stat` before committing. |

### Performance budget

- PRP-40 adds ≤ 30 s to the `showcase-rich` end-to-end budget. Total
  stays ≤ 240 s.
- Per-step timeout: 120 s (`_HTTP_TIMEOUT`, unchanged).
- `rag_index_subset` on a curated 5-file corpus typically completes in
  5-15 s on the dev host; the wider-corpus fallback (R18) can take 30-90 s.

### Validation plan (PRP-40 specific)

**Task 1 — Contract Probe** (mandatory per epic):

- Verify these backend fields/endpoints exist on `dev` post-PRP-38:
  - `POST /scenarios/simulate` request/response shape — `SimulateScenarioRequest`
    fields (`run_id`, `horizon`, `assumptions`) and `ScenarioComparison`
    response fields (especially `method` ∈ `{heuristic, model_exogenous}`,
    `aggregate_units_delta`, `aggregate_revenue_delta`).
  - `POST /scenarios` request shape — `CreateScenarioRequest` (`name`,
    `tags`, `assumptions`).
  - `POST /scenarios/compare` request/response shape — `CompareScenariosRequest`
    (`scenario_ids`, `rank_by`) and `MultiScenarioComparison`.
  - `POST /rag/index/project-docs` — `IndexProjectDocsRequest` toggles
    (`include_docs`, `include_prps`, `include_root`) and whether a
    sub-path filter exists (resolves R18).
  - `POST /rag/retrieve` — `RetrieveRequest` (`query`, `top_k`,
    `similarity_threshold`) and `RetrieveResponse` (top-k result shape).
  - `GET /config/providers/health` — `ProviderHealth` schema and how the
    embedding provider's reachability is expressed.
  - `GET /registry/aliases/demo-production` — confirm the alias resolves
    to a `model_run.run_id` and the artifact-key parse pattern for R16.
- Output to `PRPs/ai_docs/prp-40-contract-probe-report.md`.
- Stop and patch PRP wording if any cited contract is absent or drifted.

**Backend tests (new):**

- `app/features/demo/tests/test_pipeline.py::test_scenario_simulate_and_save_step`
  — asserts a `scenario_id` is persisted, `step.data` carries
  `aggregate_units_delta` + `aggregate_revenue_delta` + `method`.
- `app/features/demo/tests/test_pipeline.py::test_multi_plan_compare_step`
  — asserts both plans are persisted, the compare response is captured,
  and a `winner_scenario_id` is surfaced in `step.data`.
- `app/features/demo/tests/test_pipeline.py::test_embedding_provider_probe_step`
  — asserts `pass` when reachable; asserts `pass` with the context flag set
  when neither key is set nor Ollama reachable (with a fixture stripping the
  embedding-provider env vars + monkeypatching the Ollama probe).
- `app/features/demo/tests/test_pipeline.py::test_rag_index_subset_step`
  — asserts the curated subset is indexed (per-file `status` + aggregate
  `total_chunks` present); a sibling
  `test_rag_index_subset_step_skips_when_provider_unreachable` asserts
  `skip` with a clear `detail` and zero ASGI calls to `/rag/*`.
- `app/features/demo/tests/test_pipeline.py::test_rag_retrieve_probe_step`
  — asserts at least one hit on a known-good query against the curated
  corpus; sibling `_skips_when_provider_unreachable` mirrors the index test.

**Frontend tests (new):**

- `frontend/src/components/demo/PHASE_DEFS.test.ts` — extends the fixture
  with the `planning` + `knowledge` phases (after `decision` + `portfolio`
  from PRP-39).
- `frontend/src/components/demo/demo-step-card.test.tsx` — Inspect button
  deep-links for the five new steps (`planning` steps → `/visualize/planner`;
  `knowledge` provider step → `/admin`; index + retrieve → `/knowledge`).

**Manual dogfood checklist (PRP-40 specific):**

- [ ] C1..C3 acceptance criteria above all pass on a fresh `showcase-rich` run.
- [ ] `/visualize/planner` shows `showcase-price-cut-10pct` AND
      `showcase-holiday-uplift` in the saved-plans library; the compare row
      ranks them.
- [ ] `/knowledge` shows the 5 curated user-guide docs with non-zero chunk
      counts; a UI semantic search ("how do I run the demo") returns hits.
- [ ] With OPENAI_API_KEY + ANTHROPIC_API_KEY + GOOGLE_API_KEY unset AND
      Ollama unreachable, the `knowledge` phase reports 3× `skip`; the
      pipeline still goes green.
- [ ] The `scenario_simulate_and_save` step `detail` correctly reports
      `method=heuristic` OR `method=model_exogenous` based on the underlying
      baseline (verify against R17).
- [ ] `pnpm tsc --noEmit -p tsconfig.app.json` clean (don't trust prior
      HANDOFF green checks; cf. R7).

### Stop-and-ask gates (PRP-40)

- Before any non-additive change to `StepEvent` schema — stop and surface.
- Before adding any cross-slice import in `app/features/demo/` — stop;
  drive the call over `httpx.ASGITransport` instead.
- Before adding a `path_prefix` field on `IndexProjectDocsRequest` without
  documenting the additive-contract intent in the PRP risks — stop.
- Before a `feat!:` (breaking) commit — stop. PRP-40 is purely additive.

### Future issue title (suggested)

`feat(api,ui): showcase pipeline — planning + knowledge lifecycle`

## PRP GENERATION COMMAND

Generate the PRP from this INITIAL with:

```
/base_prp:prp-create PRPs/INITIAL/INITIAL-showcase-40-planning-knowledge-lifecycle.md
```

**Position in the epic:** **THIRD** of four PRPs in the `/showcase` upgrade.
**Prerequisite:** PRP-38 must be merged first — this slice depends on the
registered champion run (`demo-production` alias) that PRP-38 produces. PRP-40
does NOT require PRP-39 to be merged; it can be generated in parallel with
PRP-39 if desired, but DO author each PRP's contract-probe report first.
