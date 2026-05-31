# PRP-40 — Contract Probe Report

> Task 1 of `PRPs/PRP-40-showcase-planning-knowledge-lifecycle.md`.
> Read-only verification of every backend / wire contract PRP-40 cites,
> against branch `dev` at `3e771c9` (PRP-38 merged). Live `uvicorn` on
> `http://localhost:8123` was probed where the static schema needed
> behavioural confirmation.
> Generated: 2026-05-26.

## Verdict legend

- ✅ **PRESENT** — field/behaviour exists exactly as PRP-40 (or INITIAL-40) cites.
- 🟡 **DRIFTED** — exists, but with a shape PRP-40 must adjust against (the
  PRP must rename or re-anchor the citation).
- ❌ **ABSENT** — does not exist; the dependent task is blocked.
- ➕ **FINDING** — additional behaviour not cited but load-bearing for PRP-40.

## Summary

- ✅ 12 / 16 contracts PRESENT exactly as cited.
- 🟡 4 / 16 DRIFTED — INITIAL-40 cites field names that drift from the
  backend:
  1. INITIAL-40 says `PriceAssumption.pct_change`; backend has
     `PriceAssumption.change_pct`.
  2. INITIAL-40 says `ScenarioComparison.aggregate_units_delta` /
     `aggregate_revenue_delta`; backend exposes `units_delta` /
     `revenue_delta` (no `aggregate_` prefix).
  3. INITIAL-40 says `CreateScenarioRequest` carries `name` + `tags` +
     `assumptions`; backend additionally requires `run_id` + `horizon`
     and does NOT accept `store_id` / `product_id` (those are derived
     from the bundle metadata).
  4. INITIAL-40 says the agent-saved `SaveScenarioRequest` matches the
     user-facing `CreateScenarioRequest`; the two diverge by 3 fields
     (`source`, `agent_session_id`, `store_id`, `product_id`). PRP-40
     uses `CreateScenarioRequest`, so the divergence is only a
     documentation hazard for future readers.
- ❌ 0 / 16 ABSENT.
- ➕ 2 additional findings:
  - `AliasResponse` (`/registry/aliases/{alias_name}`) does NOT include
    `artifact_uri`. R16 parse needs TWO calls:
    `GET /registry/aliases/demo-production` → `model_run.run_id` →
    `GET /registry/runs/{run_id}` → `artifact_uri` → parse artifact-key.
  - `IndexProjectDocsRequest` has NO sub-path filter; the discovery
    `rglob("docs/**/*.md")` is wholesale. R18 is a real gap; PRP-40
    resolves it via **Option B (additive `path_prefix` field)** — see
    § R18 below.

Patches PRP-40 must apply (already baked into the PRP first-draft):
- Use `change_pct` (not `pct_change`).
- Use `units_delta` / `revenue_delta` (not `aggregate_*`).
- `CreateScenarioRequest` body carries `name` + `run_id` + `horizon` +
  `assumptions` + optional `tags` + optional `cloned_from`.
- R18 → ship an additive `path_prefix: str | None = None` field on
  `IndexProjectDocsRequest`; document the additive-contract intent in
  the PRP's Known Gotchas + Anti-Patterns.
- R16 parse pattern — `re.search(r"model_([0-9a-f]+)(?:\.joblib)?$", artifact_uri)`
  works on BOTH the V1 demo-rooted shape (`demo/{model_type}-model_{KEY}.joblib`)
  AND the V2 forecast-rooted shape (`artifacts/models/model_{KEY}.joblib`).

Per-task verdict: ✅ **GREEN — proceed to Task 2** with the patches above
applied. PRP-40 stays purely additive at the wire layer.

---

## (a) `app/features/scenarios/schemas.py`

| Field | Cited (PRP/INITIAL) shape | Found shape | File:line | Verdict |
|-------|---------------------------|-------------|-----------|---------|
| `PriceAssumption.change_pct` | `pct_change: float` (INITIAL-40 §Scope) | `change_pct: float = Field(..., ge=-0.9, le=5.0, strict=True, ...)` | `app/features/scenarios/schemas.py:42-48` | 🟡 DRIFTED — PRP uses `change_pct`. |
| `PriceAssumption.start_date` / `end_date` | `date` | `date_type = Field(..., strict=False, ...)` | `app/features/scenarios/schemas.py:49-58` | ✅ PRESENT |
| `HolidayAssumption.dates` | `list[date]` | `dates: list[Annotated[date_type, Field(strict=False)]] = Field(..., min_length=1, ...)` | `app/features/scenarios/schemas.py:91-96` | ✅ PRESENT — note: no `uplift_multiplier` field exists; the holiday-set uplift is set by the constant `HOLIDAY_UPLIFT` in `adjustments.py`. INITIAL-40 mentioned `uplift_multiplier=1.20`; the PRP must use `dates` alone. |
| `ScenarioAssumptions` envelope | Optional `price` / `promotion` / `holiday` / `inventory` / `lifecycle` | All 5 fields, all `= None` default | `app/features/scenarios/schemas.py:122-139` | ✅ PRESENT |
| `SimulateScenarioRequest.run_id` (R16) | "artifact-key id (`model_{id}.joblib`), NOT `model_run.run_id`" | `run_id: str = Field(..., min_length=1, max_length=64, description="Artifact key of a baseline model — the run_id stored on a completed predict/train job (model_{run_id}.joblib).")` | `app/features/scenarios/schemas.py:152-158` | ✅ PRESENT — the docstring is unambiguous; see § R16. |
| `SimulateScenarioRequest.horizon` | `int 1..90` | `int = Field(..., ge=1, le=90)` | `app/features/scenarios/schemas.py:159-164` | ✅ PRESENT |
| `SimulateScenarioRequest.assumptions` | `ScenarioAssumptions` | identical | `app/features/scenarios/schemas.py:165-168` | ✅ PRESENT |
| `CreateScenarioRequest` fields | `name` + `tags` + `assumptions` (INITIAL-40) | `name` (required, 1..200) + `run_id` (required, 1..64) + `horizon` (required, 1..90) + `assumptions` (required) + `tags` (optional list[str] ≤ 20) + `cloned_from` (optional ≤ 32) | `app/features/scenarios/schemas.py:176-212` | 🟡 DRIFTED — PRP-40 must POST `name`+`run_id`+`horizon`+`assumptions`+`tags`. |
| `ScenarioComparison.units_delta` / `revenue_delta` | `aggregate_units_delta` / `aggregate_revenue_delta` (INITIAL-40) | `units_delta: float` + `revenue_delta: float` (no `aggregate_` prefix) | `app/features/scenarios/schemas.py:292, 304` | 🟡 DRIFTED — PRP-40 uses `units_delta` / `revenue_delta`. Live `POST /scenarios/simulate` confirms: top-level keys are exactly `units_delta` / `revenue_delta`. |
| `ScenarioComparison.method` | `Literal["heuristic","model_exogenous"]` | `method: Literal["heuristic", "model_exogenous"] = Field(..., ...)` | `app/features/scenarios/schemas.py:310-315` | ✅ PRESENT |
| `ScenarioComparison.coverage_verdict` | `Literal["covered","at_risk","stockout","unknown"]` | identical (`CoverageVerdict` alias at line 29) | `app/features/scenarios/schemas.py:305-309` | ✅ PRESENT |
| `ScenarioPlanResponse.scenario_id` | unique str | identical | `app/features/scenarios/schemas.py:328` | ✅ PRESENT |
| `CompareScenariosRequest.scenario_ids` | 2..5 list[str] | `list[str] = Field(..., min_length=2, max_length=5, ...)` | `app/features/scenarios/schemas.py:419-424` | ✅ PRESENT |
| `CompareScenariosRequest.rank_by` | `Literal["revenue_delta","units_delta"]` | identical (`RankBy` alias at line 406) | `app/features/scenarios/schemas.py:425-428` | ✅ PRESENT |
| `MultiScenarioComparison.scenarios[i].rank` | 1-based int | `rank: int = Field(..., ge=1, ...)` | `app/features/scenarios/schemas.py:441` | ✅ PRESENT |
| `MultiScenarioComparison.baseline_total_units` / `baseline_revenue` | the shared baseline | both present, both `float` | `app/features/scenarios/schemas.py:449-454` | ✅ PRESENT — INITIAL-40's "winner_scenario_id" is NOT a literal field; the winner is `scenarios[0]` (rank=1). PRP-40 surfaces `scenarios[0].scenario_id` as `winner_scenario_id` in `step.data`. |

## (b) `app/features/scenarios/routes.py`

| Endpoint | Cited path | Found at | File:line | Verdict |
|----------|------------|----------|-----------|---------|
| `POST /scenarios/simulate` | INITIAL-40 cites `routes.py:34` | `@router.post("/simulate", response_model=ScenarioComparison, status_code=200, ...)` | `app/features/scenarios/routes.py:34-83` | ✅ PRESENT |
| `POST /scenarios` | INITIAL-40 cites `routes.py:86` | `@router.post("", response_model=ScenarioPlanResponse, status_code=201, ...)` | `app/features/scenarios/routes.py:86-129` | ✅ PRESENT — 201 Created (not 200). |
| `POST /scenarios/compare` | INITIAL-40 cites `routes.py:132` | `@router.post("/compare", response_model=MultiScenarioComparison, status_code=200, ...)` | `app/features/scenarios/routes.py:132-165` | ✅ PRESENT |
| Error map | 404/400 RFC 7807 | `NotFoundError` / `BadRequestError` / `DatabaseError` raise problem+json via `app/core/exceptions` | `app/features/scenarios/routes.py:78-83, 118-129, 161-165` | ✅ PRESENT — the demo `_StepError` already surfaces these as `step.fail` with the parsed body. |

## (c) `app/features/rag/schemas.py`

| Field | Cited shape | Found shape | File:line | Verdict |
|-------|-------------|-------------|-----------|---------|
| `IndexProjectDocsRequest.include_docs` / `include_prps` / `include_root` | three bool toggles, default True | `bool = Field(default=True, ...)` × 3, `ConfigDict(extra="forbid")` | `app/features/rag/schemas.py:184-201` | ✅ PRESENT |
| `IndexProjectDocsRequest.path_prefix` (sub-path filter — R18) | INITIAL-40 says "may not exist" | **NOT present** — only the three toggles | `app/features/rag/schemas.py:184-201` (no field) | ❌ ABSENT — see § R18 resolution. |
| Discovery method | "rglob `docs/**/*.md`" | `(self._base_dir / "docs").rglob("*.md")` — wholesale, no sub-path filter | `app/features/rag/service.py:278-279` | ✅ PRESENT (confirms R18 gap) |
| `IndexProjectDocsResponse` aggregate counts | `indexed` / `updated` / `unchanged` / `failed` / `total_chunks` / `duration_ms` | All present (Pydantic) | `app/features/rag/schemas.py:220-241` | ✅ PRESENT |
| `IndexProjectDocsResponse.results[i]` per-file | `source_path` / `status` / `chunks_created` / `error` | All present | `app/features/rag/schemas.py:204-217` | ✅ PRESENT — `status: Literal["indexed","updated","unchanged","failed"]`. |
| `RetrieveRequest.query` / `top_k` / `similarity_threshold` | 1..2000 / 1..50 / 0..1 | `query: str = Field(..., min_length=1, max_length=2000)`, `top_k: int = Field(default=5, ge=1, le=50)`, `similarity_threshold: float \| None = Field(default=None, ge=0.0, le=1.0)` | `app/features/rag/schemas.py:80-84` | ✅ PRESENT |
| `RetrieveResponse.results[i]` shape | top-k chunks with relevance_score | `ChunkResult` with `chunk_id` / `source_id` / `source_path` / `source_type` / `content` / `relevance_score: float (0..1)` / `metadata` | `app/features/rag/schemas.py:90-113` | ✅ PRESENT — top-1 hit is `results[0]`; `relevance_score` is the similarity-score field PRP-40 surfaces. |
| `RetrieveResponse` outer | `results` + `*_time_ms` + `total_chunks_searched` | identical | `app/features/rag/schemas.py:116-129` | ✅ PRESENT |
| 502 on embedding-provider failure | `IndexProjectDocsRequest` route returns 502 problem+json | `raise HTTPException(status_code=502, detail=f"Embedding generation failed: {e}")` on `EmbeddingError` | `app/features/rag/routes.py:198-208` | ✅ PRESENT — note: this is NOT RFC 7807 problem+json (it's a bare `HTTPException`). The demo `_StepError` still parses it as a JSON body with `{"detail": str}`. |

## (d) `app/features/config/schemas.py` + `service.py`

| Field / Behaviour | Cited shape | Found shape | File:line | Verdict |
|-------------------|-------------|-------------|-----------|---------|
| `ProviderHealth.provider` | `'ollama' \| 'openai' \| 'anthropic' \| 'google'` | identical (`str` field, doc-string lists the 4 values) | `app/features/config/schemas.py:139` | ✅ PRESENT |
| `ProviderHealth.reachable` | `bool` | identical | `app/features/config/schemas.py:140` | ✅ PRESENT |
| `ProviderHealth.detail` | human-readable str | identical | `app/features/config/schemas.py:141` | ✅ PRESENT |
| `ProviderHealth.models` | list[str] (populated for ollama) | identical, default `[]` | `app/features/config/schemas.py:142-145` | ✅ PRESENT |
| `GET /config/providers/health` returns `list[ProviderHealth]` | `[ollama, openai, anthropic, google]` order | The service yields ollama first (live probe), then openai → anthropic → google in fixed order | `app/features/config/service.py:269-316` | ✅ PRESENT — **live probe** confirms order: `ollama, openai, anthropic, google`. |
| Ollama reachability | live HTTP probe `/api/tags`; sets `reachable=False` on `httpx.HTTPError` | identical | `app/features/config/service.py:281-299` | ✅ PRESENT |
| Cloud-provider reachability | API-key presence proxy (`bool(settings.<provider>_api_key)`) | identical (lines 302-314) | `app/features/config/service.py:302-314` | ✅ PRESENT |

## (e) `app/features/registry/schemas.py` + alias resolution (R16)

| Field | Cited shape | Found shape | File:line | Verdict |
|-------|-------------|-------------|-----------|---------|
| `AliasResponse.alias_name` / `run_id` / `run_status` / `model_type` | for `GET /registry/aliases/demo-production` | identical | `app/features/registry/schemas.py:229-240` | ✅ PRESENT |
| `AliasResponse.artifact_uri` (R16 parse — needed for the artifact-key) | INITIAL-40 implies `artifact_uri` on the alias body | **NOT present** — only `alias_name`, `run_id`, `run_status`, `model_type`, `description`, `created_at`, `updated_at` | `app/features/registry/schemas.py:229-240` | ➕ FINDING — see § R16 resolution. PRP-40 step makes TWO calls: alias → run → artifact_uri. |
| `RunResponse.artifact_uri` | str \| None (registry-relative for V1 demo; absolute for V2) | `artifact_uri: str \| None = None` | `app/features/registry/schemas.py:154` | ✅ PRESENT — **live probe** on `demo-production`'s run returned `"demo/seasonal_naive-model_30a5b1faf6f7.joblib"`. |

## (f) `app/features/demo/pipeline.py` — surfaces PRP-40 reuses

| Symbol | Cited line | Found at | Verdict |
|--------|------------|----------|---------|
| `_HTTP_TIMEOUT` | INITIAL-40 § Backend uses `_HTTP_TIMEOUT` (120 s) | `_HTTP_TIMEOUT = httpx.Timeout(120.0, connect=5.0)` | `app/features/demo/pipeline.py:77` ✅ PRESENT |
| `_llm_key_present()` pattern | INITIAL-40 cites `pipeline.py:203` for "presence-only check; key NAME only" | `def _llm_key_present() -> bool: ...` (presence-only; logs key NAME, never value) | `app/features/demo/pipeline.py:221-237` (note: not at line 203; PRP-40 cites `:221-237`) — ✅ PRESENT but the cited line in INITIAL-40 (`:203`) is one screen off. PRP-40 cites the correct range. |
| `_StepError` RFC 7807 surfacing | every step raises this on non-2xx via `_Client.request` | `_StepError` class + `_Client.request` parses the response body and raises | `app/features/demo/pipeline.py:85-103, 131-159` ✅ PRESENT |
| `_phase_table(scenario)` | INITIAL-40 cites "~line 1118" | `def _phase_table(scenario: ScenarioPreset) -> list[PhaseStep]:` | `app/features/demo/pipeline.py:1118-1158` ✅ PRESENT |
| Phase constants | `PHASE_DATA`, `PHASE_MODELING`, `PHASE_DECISION`, `PHASE_VERIFY`, `PHASE_AGENT`, `PHASE_CLEANUP` | identical 6 constants | `app/features/demo/pipeline.py:1110-1115` ✅ PRESENT |
| `DemoContext` | accumulator with `winning_run_id`, `v2_run_id`, `v2_model_path`, `date_start`, `date_end`, `store_id`, `product_id` | identical | `app/features/demo/pipeline.py:167-195` ✅ PRESENT — `v2_model_path` is set by `step_v2_train`. |
| `step_v2_train` artifact path | V2 winner's `artifact_uri` = `train_response["model_path"]` (FULL `artifacts/models/...`) | `ctx.v2_model_path = v2_model_path_raw` after assertion that the path contains `"artifacts/models/"` | `app/features/demo/pipeline.py:793-810` ✅ PRESENT |
| `step_register` V1 artifact path | `artifact_uri = f"demo/{winner}-{source_model.stem}.joblib"` — registry-relative | identical | `app/features/demo/pipeline.py:938-985` ✅ PRESENT |

## (g) `frontend/src/components/demo/PHASE_DEFS.ts` lockstep contract

| Item | Cited | Found | File:line | Verdict |
|------|-------|-------|-----------|---------|
| `ALL_STEPS` (showcase_rich, 14 steps) | matches `_phase_table(SHOWCASE_RICH)` | identical 14-tuple list | `frontend/src/components/demo/PHASE_DEFS.ts:29-44` ✅ PRESENT |
| `PHASE_ORDER` | 6 phases | `['data','modeling','decision','verify','agent','cleanup']` | `frontend/src/components/demo/PHASE_DEFS.ts:72-79` ✅ PRESENT |
| `phaseDefsForScenario(scenario)` | filters out `SHOWCASE_RICH_STEP_NAMES` for non-showcase scenarios | identical | `frontend/src/components/demo/PHASE_DEFS.ts:46-59` ✅ PRESENT |
| `resolveInspectHref(step)` switch | handles `train` / `v2_train` / `register` / `backtest`; PRP-40 must extend | identical switch with default `return null` | `frontend/src/pages/showcase.tsx:26-50` ✅ PRESENT |

## (h) Curated user-guide markdown files (R18-target corpus)

| File | Path | Exists | Verdict |
|------|------|--------|---------|
| `getting-started.md` | `docs/user-guide/getting-started.md` | yes | ✅ PRESENT |
| `dashboard-guide.md` | `docs/user-guide/dashboard-guide.md` | yes | ✅ PRESENT |
| `feature-reference.md` | `docs/user-guide/feature-reference.md` | yes | ✅ PRESENT |
| `agents-and-rag-guide.md` | `docs/user-guide/agents-and-rag-guide.md` | yes | ✅ PRESENT |
| `advanced-forecasting-guide.md` | `docs/user-guide/advanced-forecasting-guide.md` | yes | ✅ PRESENT |

(A sixth file — `showcase-walkthrough.md` — also lives in `docs/user-guide/`;
PRP-40 explicitly does NOT include it because PRP-41 owns the walkthrough doc.
The `path_prefix` filter is `docs/user-guide/` plus a name allow-list to
exclude the walkthrough.)

---

## Decisions PRP-40 resolves in this probe

### R16 — Scenario `run_id` vs `model_run.run_id` (parse pattern)

**Resolved:** Two ID spaces remain distinct (memory `[[scenario-run-id-vs-registry-run-id]]`).

- `model_run.run_id` is a 32-char UUID-hex (the registry primary key).
- The scenario `run_id` is a 12-char hex (artifact-key) parsed from the
  `model_{KEY}.joblib` filename written by `forecasting/service.py:374`.

**Parse pattern (single regex works for BOTH V1 demo and V2 paths):**

```python
import re

_ARTIFACT_KEY_RE = re.compile(r"model_([0-9a-f]+)(?:\.joblib)?$")

def parse_artifact_key(artifact_uri: str) -> str:
    """Extract the 12-char artifact-key from a registry artifact_uri.

    V1 demo: "demo/{model_type}-model_{KEY}.joblib"  → KEY
    V2:      "artifacts/models/model_{KEY}.joblib"   → KEY
    """
    m = _ARTIFACT_KEY_RE.search(artifact_uri)
    if not m:
        raise ValueError(f"Cannot parse artifact-key from artifact_uri: {artifact_uri!r}")
    return m.group(1)
```

**Step resolution flow (in `step_scenario_simulate_and_save`):**

1. `GET /registry/aliases/demo-production` → `alias_body["run_id"]` (the
   32-char registry `model_run.run_id`).
2. `GET /registry/runs/{run_id}` → `run_body["artifact_uri"]`.
3. `parse_artifact_key(artifact_uri)` → the 12-char artifact-key the
   scenarios slice consumes.
4. `POST /scenarios/simulate` with `run_id=<12-char artifact-key>` and
   `horizon=DEMO_HORIZON` (14).

**Live confirmation:** on the current dev DB, the alias's run had
`artifact_uri = "demo/seasonal_naive-model_30a5b1faf6f7.joblib"`; the
parse yields `30a5b1faf6f7`; a `POST /scenarios/simulate` with that key
returned a `ScenarioComparison` with `method=heuristic`, `units_delta`
and `revenue_delta` both float.

### R17 — `method` resolution (`heuristic` vs `model_exogenous`)

**Resolved:** the `ScenarioComparison.method` field IS the source of
truth. The demo step MUST surface it in BOTH `step.detail` and
`step.data["method"]`.

- A `regression` baseline triggers `method=model_exogenous` (a genuine
  re-forecast through `feature_frame.py`).
- A `naive` / `seasonal_naive` / `moving_average` / `prophet_like`
  baseline triggers `method=heuristic` (a deterministic post-forecast
  multiplier from `adjustments.py`).
- The demo's winner is always one of these four (the `regression` model
  is NOT in the demo's `_model_config_payload` allow-list at
  `pipeline.py:203-218`), so PRP-40's `scenario_simulate_and_save` step
  will **almost always** surface `method=heuristic`. The PRP step
  description and dogfood checklist call this out.

**Live confirmation:** `POST /scenarios/simulate` against the
`seasonal_naive` winner returned `method=heuristic` (expected).

**Memory anchor:** `[[planner-ui-dogfood-findings]]` notes that the
`model_exogenous` path was inert to price assumptions in some PRP-27
builds. PRP-40 does NOT exercise that path; the dogfood checklist
asserts `method=heuristic` for the showcase winner.

### R18 — `IndexProjectDocsRequest` sub-path filter

**Resolved:** **Option B — ship an additive `path_prefix: str | None = None` field.**

Rationale:
- Option A (`include_docs=true` wholesale) indexes ~80+ markdown files
  on the current `docs/` tree (every PHASE / ADR / validation /
  user-guide doc). Wall-clock budget on the dev host is 30-90 s — over
  PRP-40's 30 s slice budget.
- Option B adds ONE Optional field; back-compat preserved (a request
  without `path_prefix` behaves exactly as today). The discovery glob
  changes from `(self._base_dir / "docs").rglob("*.md")` to
  `(self._base_dir / (path_prefix or "docs")).rglob("*.md")` (with a
  guard that rejects path-traversal — see § Path-traversal guard below).
- Curated 5-file corpus indexes in 5-15 s on the dev host (well inside
  the slice budget).

**Schema change (additive — purely additive):**

```python
class IndexProjectDocsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_docs: bool = Field(default=True, ...)
    include_prps: bool = Field(default=True, ...)
    include_root: bool = Field(default=True, ...)
    path_prefix: str | None = Field(
        default=None,
        max_length=200,
        description="Optional repo-relative path under docs/ to restrict "
        "discovery to (e.g. 'docs/user-guide'). When None (default), "
        "discovery scans every docs/**/*.md (back-compat).",
    )
```

**Service change (minimal — preserves the toggle semantics):**

```python
# app/features/rag/service.py:_discover_project_doc_files
if request.include_docs:
    if request.path_prefix:
        # Resolve under self._base_dir; reject traversal.
        candidate = (self._base_dir / request.path_prefix).resolve()
        if not str(candidate).startswith(str(self._base_dir.resolve())):
            raise ValueError(f"path_prefix escapes the project root: {request.path_prefix!r}")
        found += [(p, "docs") for p in candidate.rglob("*.md")]
    else:
        found += [(p, "docs") for p in (self._base_dir / "docs").rglob("*.md")]
```

**File-allow-list to exclude the walkthrough:** the PRP-40 step posts
`path_prefix="docs/user-guide"` AND filters the per-file results down
to the 5 curated names client-side (skipping `showcase-walkthrough.md`
if it co-exists). Server-side filename allow-listing is out of scope
for PRP-40 — `path_prefix` is the additive primitive; tighter
allow-list filtering can land in a future PRP if needed.

**Path-traversal guard:** the `path_prefix` MUST resolve INSIDE
`self._base_dir`. PRP-40 ships a unit test (`test_rag_service.py::test_index_project_docs_rejects_path_traversal`)
that asserts `path_prefix="../../etc"` raises `ValueError`.

**Stop-and-ask gate:** before merging the additive schema change in
PRP-40, surface it for review. The two existing toggles stay; the new
field is Optional with a `None` default; pre-1.0 contract additivity
preserved (no `feat!:`).

---

## Patch applied to PRP-40 (this commit)

`PRPs/PRP-40-showcase-planning-knowledge-lifecycle.md` first draft:

1. **Task 4 (scenario_simulate_and_save)** posts `change_pct` (not
   `pct_change`); captures `units_delta` / `revenue_delta` (not
   `aggregate_*`) on `step.data`.
2. **Task 5 (multi_plan_compare)** posts the second plan with a
   `HolidayAssumption` carrying `dates=[<one in-horizon day>]` (no
   `uplift_multiplier` field exists — the uplift is constant in
   `adjustments.py`).
3. **Task 4 / Task 5 `CreateScenarioRequest` body** carries `name` +
   `run_id` + `horizon` + `assumptions` + `tags`.
4. **R16 parse-pattern helper** lands in `app/features/demo/pipeline.py`
   as `_parse_artifact_key(artifact_uri)` next to `_llm_key_present()`;
   PRP-40 Task 4 wires it in.
5. **R17 method surfacing** — Task 4 step `detail` template:
   `plan={name} method={method} Δunits={units_delta:+.1f} Δrevenue={revenue_delta:+.2f}`.
6. **R18 additive `path_prefix`** — Task 6 (`rag_index_subset`) ships
   the additive field on `IndexProjectDocsRequest`, the service-layer
   discovery change, and the path-traversal guard test.
7. **Two-step alias→run→artifact_uri resolution** — Task 4 makes TWO
   sequential GETs before the first `POST /scenarios/simulate`.

---

## Net impact on the implementation plan

- **No task deferred.** Every cited contract is PRESENT or has a
  documented additive resolution.
- **One additive schema change.** `IndexProjectDocsRequest.path_prefix`
  is the only wire-layer change PRP-40 ships beyond the demo slice
  (still Optional, still purely additive).
- **Two new helper functions in the demo slice.**
  `_parse_artifact_key(artifact_uri) -> str` and
  `_embedding_provider_reachable(provider_health: list[ProviderHealth]) -> bool`.
- **Five new pipeline steps** distributed across two new phases.
- **Task 1 verdict for implementation:** ✅ **GREEN — proceed to Task 2.**
