name: "Forecast Champion Selector — Slice C: Forecast Decision, Business Summary + Operationalization"
description: |
  Close the champion-selection workflow after comparison. Slice C adds the
  *decision* half: accept the recommended winner OR manually override to another
  candidate (with an explicit non-recommended warning + audit), train the chosen
  model, generate its forecast, surface a business-readable interpretation
  (why it won, expected demand, bias risk, a clearly-labeled safety-stock
  heuristic, confidence caveats), and — through an explicit, approval-gated,
  audited path — promote the trained champion to a registry alias. It ships the
  user-guide page and an end-to-end dogfood that closes the full journey.

  Slice C builds on (does NOT redefine) Slice A (selection shell + capability
  catalog) and Slice B (async run + per-candidate progress + ranking/winner/
  chart results). It reuses the ALREADY-MERGED `POST /{id}/train-winner` and
  `POST /{id}/predict` endpoints verbatim and ADDS: `POST /{id}/train-selected`
  (override), an optional forecast-decision body on predict, and
  `POST /{id}/promote` (the future approval-gated promotion the backend
  foundation PRP explicitly deferred).

**Created:** 2026-06-01 · **Slice:** C of 3 (A → B → C)
**Current repo base observed:** `dev` @ `6c3f8d4` (Merge PR #354 — `model_selection` backend merged); alembic head `b667d321603c`.
**Backend foundation (source of truth):** `PRPs/forecast-champion-selector-backend.md` (issue #353, MERGED) + the live slice
`app/features/model_selection/{models,schemas,service,routes,ranking,explanations}.py` (verified 2026-06-01).
**Slice A (FIXED upstream):** `PRPs/forecast-champion-selector-slice-a-selection-capability.md` — owns `/visualize/champion`
page, `hooks/use-model-selection.ts`, `types/api.ts` "Model Selection" section, `components/champion-selector/*`,
`GET /model-selection/models` catalog (incl. `supports_auto_predict`), the `BIAS_EXPLANATION`/`RANKING_TIE_BREAK`
copy constants. Slice C EXTENDS these.
**Slice B (FIXED upstream):** `PRPs/forecast-champion-selector-slice-b-async-comparison-results.md` — owns `POST /runs`
(202 async), `model_selection_candidate` child table, `DELETE /{id}` cancel, the live progress + ranking table +
winner card + comparison charts + model-detail drawer, the `cancelled` status, `SubmitRunResponse`/`SelectionProgress`/
`CandidateProgress`. Slice C consumes a terminal run's `winner`/`ranking`/`business_summary` and adds the decision layer
BELOW the results. Slice C MUST NOT redefine Slice B's run/progress/cancel/results contracts.
**Working-tree caveat:** `docker-compose.lan.yml` is an untracked local dogfood override; do NOT commit it. `uv.lock` (M) is pre-existing — do NOT stage.
**Tracking issue:** create before implementation, suggested title
`feat(api,db,ui): forecast champion selector slice C — forecast decision, business summary & promotion`.
**Suggested branch:** `feat/champion-selector-slice-c` (off `dev`, per `.claude/rules/branch-naming.md`).
**Commit scope:** `api` (override-train + predict-decision + promote endpoints, decision module, service), `db` (one
migration: additive decision/promotion columns on `model_selection_run`), `ui` (decision components/hooks/types),
`docs` (user-guide page). Every commit references the tracking issue.

---

## VALIDATE — Scope vs. backend foundation, Slice A, Slice B

### Already merged (the foundation Slice C builds on — verified 2026-06-01)

- **`POST /model-selection/{selection_id}/train-winner`** EXISTS (`routes.py:132`, `service.train_winner` `service.py:405`).
  It trains `ranking.winner` ONLY (no override), writes `row.final_model_path`, returns
  `TrainWinnerResponse{selection_id, model_type, model_path}` (`schemas.py:291`). It takes **no request body**.
- **`POST /model-selection/{selection_id}/predict`** EXISTS (`routes.py:154`, `service.predict_winner` `service.py:442`).
  Requires a trained model (`row.final_model_path`, else `BadRequestError`), calls
  `ForecastingService().predict(...)`, returns `PredictWinnerResponse{selection_id, forecast: ForecastSummary}`
  (`schemas.py:299`). It takes **no request body**.
- **`ForecastingService().predict()` REJECTS feature-aware models** (`forecasting/service.py:491`):
  `if bundle.model.requires_features: raise ValueError("Feature-aware models forecast through POST /scenarios/simulate …")`.
  The reject set is `regression`, `prophet_like`, `lightgbm`, `xgboost`, `random_forest`. Slice A's catalog already
  encodes this as `supports_auto_predict = not feature_aware`.
- **`ForecastSummary`** (`schemas.py:258`) = `{points, total_demand, average_demand, horizon}` — has **no peak/low day**.
- **`business_summary`** (built by `explanations.explain_winner`, `explanations.py:26`) = `{headline, winner{model_type,
  summary}, recommendation_confidence, confidence_reasons, comparison{runner_up…}, data_notes, caveats}` — has **no
  bias-risk wording, no safety stock, no expected-demand-from-forecast**.
- **`ModelSelectionRun` ORM** (`models.py:43`) has `final_model_path: str|None` but **no registry `run_id` linkage, no
  `trained_model_type`/override columns, no promotion/alias columns**.
- **Forecasting `train_model` does NOT register a registry run** (verified `forecasting/service.py:247` — writes a joblib
  bundle to `./artifacts/models`, returns `TrainResponse.model_path`; **no `run_id`**). Therefore promotion must itself
  orchestrate the registry: `RegistryService.create_run` → `update_run`(→SUCCESS w/ artifact) → `create_alias`.
- **Registry promotion mechanics** (`registry/service.py`): `create_run(db, RunCreate) -> RunResponse` (`:183`, PENDING,
  generates `run_id`); `update_run(db, run_id, RunUpdate) -> RunResponse|None` (`:368`, state machine
  PENDING→RUNNING→SUCCESS); `create_alias(db, AliasCreate) -> AliasResponse` (`:432`) with the **hard precondition**
  "Only SUCCESS runs can be aliased" (`service.py:457`). `AliasCreate.alias_name` regex `^[a-z0-9][a-z0-9\-_]*$`
  (`registry/schemas.py:224`). Artifact storage: `LocalFSProvider.save(source_path, artifact_uri) -> (sha256, size)`
  (`registry/storage.py:169`); `compute_hash` (`:106`).
- **Backend foundation PRP Non-Goals** (`forecast-champion-selector-backend.md:65`):
  *"No alias auto-promotion (the selector may recommend a winner; alias mutation is a **future approval-gated PRP**)."*
  **Slice C IS that PRP** — promotion lands here, explicitly approval-gated + audited (never auto).

### Slice C's gaps to fill

1. **Manual winner override** — there is no way to train a user-chosen non-winner candidate. Need `train-selected` +
   override audit + a non-recommended warning contract.
2. **Forecast decision enrichment** — peak/low day, a labeled safety-stock heuristic, bias-risk interpretation, and
   expected demand are absent. Deterministic, not LLM-dependent. Safety stock must NOT influence ranking.
3. **Capability-limited forecast state** — a feature-aware winner cannot auto-predict; today predict 400s with a raw
   error. The UI must show an explicit blocked/unsupported state (driven by Slice A's `supports_auto_predict`).
4. **Approval-gated, audited promotion** — no promote path exists. Need a single orchestrated, explicitly-approved,
   recorded promotion to a registry alias (the deferred future PRP).
5. **Decision UI + user guide + dogfood** — no decision components, no guide page, no end-to-end dogfood of the journey.

---

## BRAINSTORM / RERANK — Chosen packaging

Three packaging alternatives (the brief's expected three), scored on user value / repo fit / implementation clarity /
risk control / dependency isolation (each 1–5; total /25):

| # | Option | User | Repo fit | Clarity | Risk | Isolation | **Total** |
|---|--------|:----:|:--------:|:-------:|:----:|:---------:|:---------:|
| **1** | **Extend `model_selection` with decision endpoints (`train-selected` override, optional decision body on `predict`, `POST /{id}/promote` orchestrating registry) + a pure `decision.py` + a `components/champion-selector/decision/*` UI family. Backend owns capability + audit.** | 5 | 5 | 4 | 4 | 4 | **22 ✅** |
| 3 | Forecast output only (override/train/predict/summary/chart/table/business/safety-stock) and **defer promotion + governance** to a later PRP | 2 | 4 | 5 | 5 | 5 | 21 |
| 2 | Reuse `/forecasting` + `/registry` endpoints **directly from the frontend**; no new `model_selection` orchestration endpoints (TS orchestrates train→register→alias) | 4 | 2 | 2 | 2 | 2 | 12 |

**Chosen: Option 1.** It is the only option that delivers the brief's full operationalization (override + train +
forecast + business interpretation + safety stock + **promotion with approval/audit** + docs + dogfood) while keeping
capability **backend-owned** (coordination contract) and respecting the vertical-slice rule (the service already
lazy-imports `BacktestingService`/`ForecastingService`; Slice C lazy-imports `RegistryService` the same way). It matches
the merged slice's pattern, the governance doc's promotion-decision-record, and the existing
`promote-confirmation-dialog.tsx` UX precedent.

**Option 3 is the de-risking fallback, not a rival.** Promotion (Task set 5) is the LAST, separable task; if its registry
artifact-registration mechanic proves heavier than budgeted, the slice can ship Option-3 scope (everything except
`POST /{id}/promote` + the promote dialog) and a follow-up issue, still passing all gates. Its low user-value score
reflects that it drops a *required* Slice-C deliverable. **Option 2 is rejected:** it bypasses the merged backend-owned
`train-winner`/`predict`, pushes a fragile multi-step registry write (artifact copy + hash + alias) into TypeScript with
no audit record, and violates "backend-owned model capability metadata is preferred over frontend hardcoding."

**Non-goals (NOT built here):** re-running comparison / async progress / cancel / ranking math (Slice B); the selection
shell / catalog / availability (Slice A); feature-aware *auto*-predict (explicitly unsupported — surfaced as a capability
limitation, NOT faked); any agent tool / `agent_require_approval` entry (promotion is a user REST flow, not an agent
mutation); batch model-zoo; multi-tenant/cloud anything.

---

## Goal

**Feature Goal:** Let a user, after a champion comparison run (Slice B) finishes with a winner, **decide and operate**:
accept the recommended model or override to another candidate (warned + audited), train it, generate and read its
forecast (summary with peak/low, chart, daily table), understand it in business terms (why it won, expected demand,
bias risk, a labeled safety-stock heuristic, confidence caveats), and — only on explicit approval — promote the trained
champion to a registry alias with a recorded decision. All deterministic, no LLM.

**Deliverable:**
- **Backend (additive to the `model_selection` slice):**
  - `POST /model-selection/{selection_id}/train-selected` — train a user-chosen candidate (override); persists
    `trained_model_type` / `is_override` / `override_reason`; returns a `TrainWinnerResponse` + `override_warning`.
  - `POST /model-selection/{selection_id}/predict` — KEEP existing behavior; ADD an **optional** `ForecastDecisionParams`
    body (`lead_time_days`, `service_level`); response gains peak/low (on `ForecastSummary`) + a `decision: ForecastDecision`.
  - `POST /model-selection/{selection_id}/promote` — approval-gated, audited orchestration: register a registry
    `model_run`, transition it to SUCCESS with the verified artifact + winner metrics, create the alias; persist a
    `promotion_decision` audit + `champion_run_id` + `promoted_alias`. Returns `PromoteResponse`.
  - A pure `app/features/model_selection/decision.py` (mirrors `ranking.py`/`explanations.py`): forecast peak/low,
    safety-stock heuristic (deterministic z-table, King formula), bias-risk text, expected demand.
  - One Alembic migration: additive columns on `model_selection_run`.
- **Frontend (extends the Slice A/B `/visualize/champion` page):** decision hooks
  (`useTrainWinner`/`useTrainSelected`/`usePredictWinner`/`usePromoteChampion`), a
  `components/champion-selector/decision/*` family (override panel, train/forecast actions with the capability-limited
  state, forecast summary card, forecast chart, daily forecast table, business-interpretation panel, safety-stock panel,
  promote dialog), and additive types in the Slice-A "Model Selection" section.
- **Docs:** `docs/user-guide/champion-selector-guide.md` + a row in any guide index.
- **Dogfood:** an end-to-end manual probe (select → run → decide → train → forecast → promote) over `localhost`.

**Success Definition:**
1. `POST /{id}/train-selected` trains a chosen candidate; an override to a non-winner returns `override_warning` and
   persists `is_override=true` + `override_reason`; an unknown/non-candidate `model_type` → RFC 7807 400.
2. `POST /{id}/predict` returns the forecast PLUS peak/low day and a `decision` block (safety stock, expected demand,
   bias-risk text, caveats); the safety-stock value never feeds ranking; a feature-aware winner returns a clear 400 and
   the UI shows a blocked/unsupported state instead of calling predict.
3. `POST /{id}/promote` requires `approved_by` (and explicit ack for a non-recommended model), creates a SUCCESS
   registry run + alias, and persists a `promotion_decision` audit; promoting before training → 422; a bad `alias_name`
   → 422; promoting a non-recommended model without ack → 422.
4. The `/visualize/champion` page, after a terminal winning run, renders the decision section: accept/override → train →
   forecast (summary + chart + daily table) → business interpretation (incl. safety stock + bias risk) → gated promote.
5. All Slice C validation gates pass (backend Level-1..4 incl. migration up/down + integration; frontend `tsc`/`lint`/
   `test`); the new guide page exists; the dogfood journey completes.

## Why

- Comparison answers "which model is best?"; operationalization answers "now what?" — train it, see the forecast, judge
  its business impact, and (deliberately, with a record) put it into service. Without Slice C the selector stops at a
  ranking table and never produces a usable forecast or a promoted champion.
- Promotion must be **explicit + audited** (governance doc + foundation PRP): the app may *recommend* a champion, but a
  human approves and the decision is recorded. This is the controlled counterpart to the recommendation.
- A labeled safety-stock heuristic + bias-risk wording turn raw metrics into an inventory decision a planner can act on,
  while staying honest (heuristic, correlation-not-causation caveats, never influences ranking).
- Keeps the single-host architecture: deterministic Python + Postgres + the existing registry; no new dependency,
  no queue, no cloud SDK, no LLM in the decision path.

## What

### New / changed endpoints (all under the existing `APIRouter(prefix="/model-selection")`)

```http
POST /model-selection/{selection_id}/train-winner    # EXISTING (unchanged) — train the ranked winner
POST /model-selection/{selection_id}/train-selected  # NEW — train a chosen candidate (override + audit)
POST /model-selection/{selection_id}/predict         # EXISTING — ADD optional ForecastDecisionParams body + decision in response
POST /model-selection/{selection_id}/promote         # NEW — approval-gated, audited registry promotion
# UNCHANGED & KEPT: GET /availability, GET /models (A); POST /run, POST /runs, DELETE /{id}, GET /{id}, GET /{id}/ranking (A/B)
```

`POST /{id}/train-selected` request `TrainSelectedRequest` (strict):
```json
{ "model_type": "seasonal_naive", "override_reason": "domain seasonality outweighs WAPE lead" }
```
Response = `TrainWinnerResponse` superset: `{ selection_id, model_type, model_path, is_override, override_warning }`.

`POST /{id}/predict` optional body `ForecastDecisionParams` (strict; all JSON-native → no `Field(strict=False)` needed):
```json
{ "lead_time_days": 7, "service_level": 0.95 }
```
Response `PredictWinnerResponse` (additive): `forecast: ForecastSummary` (now incl. `peak_date/peak_demand/low_date/low_demand`)
+ `decision: ForecastDecision`.

`POST /{id}/promote` request `PromoteRequest` (strict):
```json
{ "alias_name": "champion-store5-prod8", "approved_by": "gabor", "acknowledge_non_recommended": false, "description": "Q3 champion" }
```
Response `PromoteResponse`: `{ selection_id, alias_name, run_id, run_status, model_type, is_override, promoted_at }`.

### LOCKED Slice-C decisions

1. **Override is a NEW sibling endpoint `POST /{id}/train-selected`, NOT a change to `train-winner`.** `train-winner`
   stays byte-for-byte as merged (Slice B treats it as fixed; its tests must not break). `train-selected` validates that
   `model_type` is one of the run's `candidate_models` AND appears as a ranking entry; trains it via the SAME
   `ForecastingService.train_model` call `train_winner` uses; sets `final_model_path`, `trained_model_type`,
   `is_override = (model_type != ranking.winner.model_type)`, `override_reason`. If `is_override`, the response carries
   `override_warning` (deterministic copy naming the recommended model + the chosen model's WAPE gap). A model_type not in
   the candidate set → `BadRequestError` (400). `train-winner` ALSO now persists `trained_model_type=winner`,
   `is_override=False` (one tiny additive write in the existing method — its response shape is unchanged; the new columns
   are nullable so this is back-compatible).
2. **Predict gains an OPTIONAL decision body + an additive `decision` block.** The body is
   `ForecastDecisionParams{lead_time_days: int = 7 (ge=1, le=365), service_level: float = 0.95 (ge=0.5, lt=1.0)}`. Declare
   the route param so an empty body still works (`request: ForecastDecisionParams | None = Body(default=None)`; treat
   `None` as defaults). `ForecastSummary` gains `peak_date/peak_demand/low_date/low_demand` (all `Optional`, default
   `None` → back-compatible with Slice B's reuse of `ForecastSummary`). `PredictWinnerResponse` gains
   `decision: ForecastDecision | None`. The existing `predict_winner` still 400s for an untrained model and for a
   feature-aware model (the `ForecastingService.predict` `ValueError`).
3. **Safety stock is a pure, deterministic heuristic in `decision.py`, CLEARLY LABELED, and NEVER touches ranking.**
   `compute_forecast_decision(points, average_demand, lead_time_days, service_level) -> ForecastDecision`. Formula
   (King 2011, demand-variability-only, constant lead time):
   `safety_stock = z(service_level) * sigma_daily * sqrt(lead_time_days)`, `sigma_daily = stdev(daily forecast values)`,
   `expected_demand_over_lead_time = average_demand * lead_time_days`,
   `reorder_point = expected_demand_over_lead_time + safety_stock`. `z` from a fixed lookup (NO scipy): `0.90→1.2816,
   0.95→1.6449, 0.975→1.9600, 0.99→2.3263`; nearest-key fallback for in-between levels (documented). Every `ForecastDecision`
   field carries a `method="heuristic"` marker and a caveat string; the UI labels the panel "Safety stock (heuristic)".
   `rank_candidates`/`build_chart_data` are NOT touched and never receive safety-stock inputs.
4. **Bias-risk wording is locked and reuses Slice A's `BIAS_EXPLANATION` constant.** Wherever bias is surfaced (business
   interpretation panel + `decision.bias_risk_text`): *"Positive bias means the model under-forecasts (risk of stockouts);
   negative bias means it over-forecasts (risk of overstock)."* The backend `decision.py` returns the same sentence
   (single source) plus the winner's bias sign read from `winner_metrics["bias"]`.
5. **Feature-aware winners are a CAPABILITY LIMITATION, not a faked forecast.** The UI reads the winner's
   `supports_auto_predict` from the Slice-A catalog (`GET /model-selection/models`); when `false` it renders a blocked
   "Forecast not available for feature-aware models — use the What-If Planner (`/scenarios`)" state and does NOT call
   `POST /{id}/predict`. The backend keeps `predict`'s clean 400 as a server-side guard (the `ForecastingService.predict`
   `ValueError` message is already explicit). Do NOT add a scenarios call here (out of slice).
6. **Promotion is approval-gated, audited, and orchestrates the registry — never auto.** `POST /{id}/promote`:
   (a) load run; require `final_model_path` + `trained_model_type` (else 422 "train the model first");
   (b) if `is_override` (a non-recommended model was trained) and `acknowledge_non_recommended` is `False` → 422;
   (c) `RegistryService.create_run(db, RunCreate(model_type=trained_model_type, model_config_data=<trained params>,
       data_window_start=row.start_date, data_window_end=row.end_date, store_id, product_id,
       runtime_info_extras={"feature_frame_version": row.feature_frame_version}))` → PENDING `run_id`
       — pass the **REAL persisted** `feature_frame_version` (V1 or V2) read off the run row, NEVER a hardcoded literal
       (see LOCKED #7 for the column + run-creation persistence, and Known Gotchas for the V2 fidelity rule);
   (d) `update_run(db, run_id, RunUpdate(status=RUNNING))`;
   (e) register the artifact: copy the bundle at `row.final_model_path` into registry storage via the provider's
       `save(Path(final_model_path), artifact_uri) -> (hash, size)` (see Known Gotchas — VERIFY the exact
       artifact-registration call before coding);
   (f) `update_run(db, run_id, RunUpdate(status=SUCCESS, metrics=row.winner_metrics, artifact_uri, artifact_hash=hash,
       artifact_size_bytes=size))`;
   (g) `create_alias(db, AliasCreate(alias_name=request.alias_name, run_id=run_id, description=request.description))`
       — alias only attaches to a SUCCESS run (guaranteed by step f);
   (h) persist on `model_selection_run`: `champion_run_id=run_id`, `promoted_alias=alias_name`, and a `promotion_decision`
       JSONB = `{decision_id, alias, champion_run_id, approved_by, approved_at, decision:"promoted", reason,
       trained_model_type, is_override}` (governance-doc decision-record shape).
   `alias_name` is validated against the registry regex `^[a-z0-9][a-z0-9\-_]*$` at the schema layer (422 on violation).
   **Compare and promote stay separate** — promote performs NO ranking/comparison; it only registers + aliases the
   already-trained champion.
7. **One migration, additive only (seven columns).** `model_selection_run` gains: `trained_model_type VARCHAR(40)`
   (nullable), `is_override BOOLEAN NOT NULL DEFAULT false` (server_default `'false'`), `override_reason VARCHAR(2000)`
   (nullable), `champion_run_id VARCHAR(32)` (nullable), `promoted_alias VARCHAR(100)` (nullable), `promotion_decision
   JSONB` (nullable), and **`feature_frame_version INTEGER NOT NULL server_default '1'`** (M1 — V2-promotion support).
   The `'1'` server_default backfills pre-existing rows only; it is NOT a code hardcode. **Run-creation persists the
   real value:** Slice C ADDS `row.feature_frame_version = request.feature_frame_version` to BOTH `run_selection` (sync,
   merged) AND `submit_run` (async, Slice B's) so every new run records what the user configured (V1 or V2); this is an
   additive column write, not a redefinition of Slice B's run contract. No table drop, no CheckConstraint change. Chain
   `down_revision` off the LIVE head at impl time (Slice B's migration must land first; run `uv run alembic heads`).
   `downgrade` drops all seven columns.
8. **WAPE stays default; tie-break unchanged; ranking math untouched.** Slice C reads `winner_metrics`/`ranking` as
   produced by Slice A/B; it does not re-rank, re-derive confidence, or alter `ranking.py`/`explanations.py`.
   **Coordination (ownership of "Explain Winner"):** `business_summary` is computed ONCE by the backend
   (`explanations.explain_winner`, unchanged here). Slice B's winner-card already renders it read-only; Slice C's
   business-interpretation-panel renders the SAME `business_summary` read-only and ADDS only the decision-layer fields
   (bias-risk text + labeled safety stock from `decision.py`). Slice C does NOT re-derive explanation text or duplicate
   Slice B's winner-card — it renders the decision section BELOW it.
9. **No new strict request model carries a date/datetime/UUID/Decimal field.** `TrainSelectedRequest`,
   `ForecastDecisionParams`, `PromoteRequest` are all `str`/`int`/`float`/`bool` only → `ConfigDict(strict=True)` with
   NO `Field(strict=False)` needed; `app/core/tests/test_strict_mode_policy.py` stays green. `promoted_at`/`approved_at`
   are server-set, never request fields.

### Success Criteria

- [ ] `POST /{id}/train-selected` trains a chosen candidate; non-candidate `model_type` → 400; override persists
      `is_override=true` + `override_reason` and returns `override_warning`; `train-winner` still passes its existing tests.
- [ ] `POST /{id}/predict` (with or without a body) returns `forecast` incl. `peak_date/peak_demand/low_date/low_demand`
      and a `decision` block; safety stock is labeled heuristic; ranking output is unchanged by the decision call.
- [ ] A feature-aware winner: `predict` returns a clean 400; the UI shows the blocked state and never calls predict.
- [ ] `POST /{id}/promote` requires `approved_by`; non-recommended without ack → 422; before-train → 422; bad alias_name
      → 422; on success creates a SUCCESS registry run + alias and persists `champion_run_id`/`promoted_alias`/
      `promotion_decision`; a re-promote with the same alias_name updates the alias (registry upsert semantics).
- [ ] Migration adds the seven columns (incl. `feature_frame_version`) and `downgrade` removes them cleanly on a fresh DB; strict-mode policy test green.
- [ ] `decision.py` is pure (no DB/IO); its z-table + safety-stock + peak/low + bias-risk text are unit-tested deterministically.
- [ ] `/visualize/champion` decision section renders after a terminal winning run: accept/override → train → forecast
      (summary card + chart + daily table) → business interpretation (bias risk + labeled safety stock + caveats) →
      gated promote dialog (alias name + approver + non-recommended ack); feature-aware → blocked forecast state.
- [ ] `docs/user-guide/champion-selector-guide.md` exists and documents the full journey incl. the promotion-is-audited rule.
- [ ] All backend Level-1..4 gates + frontend `pnpm tsc --noEmit && pnpm lint && pnpm test --run` pass; dogfood completes.

## All Needed Context

### Documentation & References

```yaml
# Slice / contract source of truth
- file: PRPs/forecast-champion-selector-backend.md
  why: Merged foundation. Non-Goals (:61-67) defer alias promotion to a "future approval-gated PRP" — THIS slice.
       The /train-winner + /predict endpoint contract (:106-107). Do NOT re-derive ranking/availability.
- file: PRPs/forecast-champion-selector-slice-a-selection-capability.md
  why: FIXED upstream. Owns the page, hooks module, types/api.ts "Model Selection" section, champion-selector/*,
       GET /models catalog (supports_auto_predict = not feature_aware), and the BIAS_EXPLANATION / RANKING_TIE_BREAK
       constants in components/champion-selector/copy.ts. Slice C REUSES BIAS_EXPLANATION and the catalog flag.
- file: PRPs/forecast-champion-selector-slice-b-async-comparison-results.md
  why: FIXED upstream. Owns POST /runs, the child table, DELETE cancel, the results UI (winner card/ranking table/
       charts/detail drawer) + 'cancelled' status. Slice C renders the decision section BELOW Slice B's results and
       reuses winner/ranking/business_summary read-only. Do NOT redefine these.
- file: PRPs/templates/prp_base.md
  why: Base template. NOTE — "PRPs/prp-readme.md.md" does NOT exist (find PRPs -iname '*readme*' empty 2026-06-01);
       all three prior champion PRPs record the same.

# Live model_selection slice (the contract Slice C extends — verified 2026-06-01)
- file: app/features/model_selection/service.py
  why: train_winner (:405) + predict_winner (:442) are the methods Slice C extends/mirrors. _load (:513), _load_ranking
       (:521), _forecast_summary (:505), _response (:526). Lazy cross-slice imports of ForecastingService inside methods
       (:410, :444) — MIRROR that for the lazy RegistryService import in promote. train_winner builds the winner
       ModelConfig via TypeAdapter(ModelConfig).validate_python({"model_type":…, **params}) (:417) — reuse for selected.
- file: app/features/model_selection/schemas.py
  why: ForecastSummary (:258) — ADD peak/low (Optional). TrainWinnerResponse (:291)/PredictWinnerResponse (:299) — ADD
       fields. ModelType Literal (:34). ConfigDict(strict=True) on request bodies; SelectionWindow uses Field(strict=False)
       ONLY for its dates (:64) — the new request bodies need NO strict=False (no date/uuid/decimal fields). ADD
       TrainSelectedRequest, ForecastDecisionParams, ForecastDecision, PromoteRequest, PromoteResponse.
- file: app/features/model_selection/models.py
  why: ModelSelectionRun (:43) — ADD the seven columns: six decision/promotion + feature_frame_version (LOCKED #7). The status CheckConstraint
       (:82) is NOT changed by Slice C (it is by Slice B). final_model_path (:73) is the trained-bundle path promote copies.
- file: app/features/model_selection/routes.py
  why: APIRouter(prefix="/model-selection") (:38); train_winner (:132) + predict_winner (:154) handlers + error mapping
       (ValueError→BadRequestError, SQLAlchemyError→DatabaseError). ADD POST /train-selected, /promote; extend predict body.
- file: app/features/model_selection/ranking.py
  why: rank_candidates/build_chart_data — Slice C does NOT touch ranking. Read-only awareness only.
- file: app/features/model_selection/explanations.py
  why: explain_winner (:26) builds business_summary; decision.py is the SECOND pure module (mirror its style/imports).
       Slice C does NOT change explain_winner; the bias-risk/safety-stock additions live in decision.py + the UI panel.
- file: app/features/model_selection/tests/conftest.py
  why: client fixture (:226 — app.dependency_overrides[get_db]=yield db_session; ASGITransport+AsyncClient) and the
       integration db_session fixture (:191 — real engine, prefix-scoped teardown deleting ModelSelectionRun by store_id).
- file: app/features/model_selection/tests/test_routes.py
  why: _client() route harness (:32 — override get_db with AsyncMock; ASGITransport). MIRROR for /train-selected,
       /predict-with-body, /promote route tests.
- file: app/features/model_selection/tests/test_service.py
  why: monkeypatch target for ForecastingService is the STRING "app.features.forecasting.service.ForecastingService"
       (:176). For promote, monkeypatch "app.features.registry.service.RegistryService" the same way.

# Forecasting + registry (services Slice C orchestrates via lazy import — verified 2026-06-01)
- file: app/features/forecasting/service.py
  why: train_model(db, store_id, product_id, train_start, train_end, config, *, feature_frame_version=1,
       feature_groups=None) -> TrainResponse{model_path,…} (:247) — NO registry write. predict(store_id, product_id,
       horizon, model_path) -> PredictResponse (:402); REJECTS feature-aware at :491 (ValueError). ForecastPoint has
       {date, forecast, lower_bound, upper_bound}.
- file: app/features/forecasting/feature_metadata.py
  why: model_family_for(model_type) (:57) — only needed if you ever derive feature_aware backend-side; Slice C prefers
       Slice A's catalog flag. Reject set = requires_features models (regression/lightgbm/xgboost/random_forest/prophet_like).
- file: app/features/registry/service.py
  why: create_run(db, RunCreate) -> RunResponse (:183, PENDING, generates run_id); update_run(db, run_id, RunUpdate)
       -> RunResponse|None (:368, state machine); create_alias(db, AliasCreate) -> AliasResponse (:432) — "Only SUCCESS
       runs can be aliased" (:457). These are the three calls promote() orchestrates (lazy import RegistryService()).
- file: app/features/registry/schemas.py
  why: RunCreate (:71 — model_type, model_config_data[alias model_config], data_window_start/end, store_id, product_id;
       optional runtime_info_extras), RunUpdate (:116 — status/metrics/artifact_uri/artifact_hash/artifact_size_bytes),
       AliasCreate (:219 — alias_name regex ^[a-z0-9][a-z0-9\-_]*$, run_id, description), RunStatus (:30), RunResponse
       (:129), AliasResponse (:229).
- file: app/features/registry/storage.py
  why: LocalFSProvider.save(source_path: Path, artifact_uri: str) -> (sha256, size) (:169); compute_hash (:106);
       load (:201). The artifact-registration step in promote() (LOCKED #6e) uses this — VERIFY the exact call/URI
       convention against how ops/demo register artifacts before coding (see Known Gotchas).
- file: app/core/config.py
  why: forecast_model_artifacts_dir = "./artifacts/models" (:100); registry_artifact_root = "./artifacts/registry" (:112).
       The trained bundle lives under forecast_model_artifacts_dir; promote copies it into the registry root.
- file: app/core/exceptions.py
  why: BadRequestError(400, :152), NotFoundError(404, :64), ConflictError(409, :130), UnprocessableEntityError(422, :174),
       DatabaseError(500, :108). Use UnprocessableEntityError for "train first" / "ack required" / bad-alias states; the
       schema regex already 422s a bad alias_name at validation.

# Frontend examples to MIRROR (verified 2026-06-01)
- file: frontend/src/components/forecast-intelligence/promote-confirmation-dialog.tsx
  why: THE gated-promotion UX (props open/onOpenChange/run/currentChampion/defaultAliasName/onConfirm(aliasName)/
       isPromoting; alias-name input; verify-artifact gate; worse-WAPE + version-mismatch checkbox acknowledgements).
       MIRROR its structure for promote-champion-dialog.tsx (alias name + approver + non-recommended ack), but call the
       NEW usePromoteChampion hook (POST /model-selection/{id}/promote), not useCreateAlias.
- file: frontend/src/components/forecast-intelligence/champion-compatibility-badge.tsx
  why: Compatibility signalling (Comparable/Not comparable badge from grain+window+feature-frame). Use read-only in the
       promote dialog if showing champion-vs-current context; do NOT make promote perform the comparison (keep separate).
- file: frontend/src/pages/visualize/forecast.tsx
  why: Forecast rendering pattern — TimeSeriesChart usage (:448, predictedKey="forecast", showInterval + lower/upper_bound)
       and CSV export. NOTE: there is NO daily-table pattern here (it CSV-exports) — Slice C BUILDS the daily table.
- file: frontend/src/components/charts/time-series-chart.tsx
  why: The forecast curve chart (ComposedChart; actual/predicted lines + optional interval band). Props data + predictedKey
       + lowerKey/upperKey + showInterval. ResizeObserver beforeAll stub needed in jsdom tests.
- file: frontend/src/components/charts/kpi-card.tsx
  why: KPI metric tile — for the forecast summary card (total demand / average / peak day / low day / horizon).
- file: frontend/src/components/data-table/data-table.tsx  AND  frontend/src/components/ui/table.tsx
  why: The daily forecast table — a plain shadcn Table (date, forecast, lower, upper) is sufficient; DataTable only if
       sortable columns are wanted. Mirror the batch.tsx plain-Table usage from Slice B.
- file: frontend/src/pages/explorer/run-compare.tsx
  why: Champion-vs-challenger side-by-side + DeltaCell pattern — reference for any compatibility/delta display in the
       promote dialog (read-only context only; promote ≠ compare).
- file: frontend/src/hooks/use-runs.ts
  why: useCreateAlias (:136 — POST /registry/aliases) + useVerifyArtifact patterns. Slice C does NOT reuse these for
       promotion (promotion is a single model_selection endpoint) but mirrors their useMutation + invalidate shape.
- file: frontend/src/hooks/use-model-selection.ts
  why: Slice A/B module. Slice C ADDS useTrainWinner/useTrainSelected/usePredictWinner/usePromoteChampion (useMutation,
       invalidate the run query so Slice B's poll/GET reflects the new final_model_path/forecast/promotion). Do NOT
       redefine Slice A/B hooks.
- file: frontend/src/lib/api.ts
  why: api<T>(endpoint,{method,body,params}) (:23); 202 (:79) / 204 (:44) handling; getErrorMessage (:95). POST bodies
       are JSON; promote/train/predict are plain POSTs returning JSON 200.
- file: frontend/src/types/api.ts
  why: ModelFamily union (:177), ForecastPoint (:102 — date/forecast/lower_bound/upper_bound), Alias (:276),
       RunCompareResponse (:286). ADD (additive, Model Selection section) TrainSelectedRequest, ForecastDecisionParams,
       ForecastDecision, PromoteRequest, PromoteResponse; EXTEND ForecastSummary (peak/low) + the train/predict response types.
- file: frontend/src/lib/constants.ts
  why: ROUTES.VISUALIZE.CHAMPION + the Visualize NAV entry are added by Slice A — Slice C adds NO route/nav.
- file: frontend/vitest.config.ts
  why: jsdom; include src/**/*.test.{ts,tsx}; @→./src. Chart tests need a ResizeObserver beforeAll stub.

# Governance / external docs (with reasoning)
- file: docs/optional-features/09-model-champion-challenger-governance.md
  why: The promotion-decision-record shape (decision_id, alias, champion_run_id, challenger_run_id, gate_results,
       approved_by, approved_at, decision, reason) + the "require approval and record the decision" rule. Slice C's
       promotion_decision JSONB mirrors this (challenger_run_id/gate_results omitted in this slice — compare is separate).
- file: docs/user-guide/  (advanced-forecasting-guide.md, agents-and-rag-guide.md, dashboard-guide.md, feature-reference.md,
        getting-started.md, showcase-manual-demo-guide.md, showcase-walkthrough.md)
  why: Naming convention `{feature}-guide.md`. ADD champion-selector-guide.md; cross-link from feature-reference.md.
- url: https://www.mlflow.org/docs/latest/ml/model-registry/workflow/
  why: Alias/champion registry workflow — confirms the "register a versioned model, then move a named alias to it"
       pattern Slice C's promote() implements (create_run → success → create_alias). Aliases are mutable pointers; the
       run/version is immutable.
- url: https://web.mit.edu/course/2/2.810/www/files/readings/King_SafetyStock.pdf
  why: Safety-stock formula reference. Slice C uses the demand-variability-only form SS = z·σ_D·√L (constant lead time);
       the doc's z-from-service-level table grounds the z lookup in decision.py. Cite as the heuristic's source in the UI.
- url: https://otexts.com/fpp2/accuracy.html
  why: Forecast-accuracy metric definitions (WAPE/MAE/bias) — so the business-interpretation copy describes each metric
       correctly and the bias under/over-forecast wording stays accurate.
- url: https://cloud.google.com/vertex-ai/docs/evaluation/introduction
  why: Model-evaluation framing (a recommended model is a recommendation, not an automatic deployment) — supports the
       explicit-approval gate on promotion.
- url: https://fastapi.tiangolo.com/tutorial/bigger-applications/#apirouter
  why: APIRouter route registration — the new /train-selected + /promote handlers follow the slice's existing pattern.
```

### Current Codebase Tree (relevant)

```bash
app/features/model_selection/        # MERGED (issue #353) — train-winner + predict already present
├── models.py        # ModelSelectionRun                 ← ADD trained_model_type/is_override/override_reason/champion_run_id/promoted_alias/promotion_decision
├── schemas.py       # request/response contract          ← ADD TrainSelectedRequest, ForecastDecisionParams, ForecastDecision, PromoteRequest, PromoteResponse; EXTEND ForecastSummary + train/predict responses
├── service.py       # train_winner/predict_winner present ← ADD train_selected, promote; EXTEND predict_winner (decision); persist trained_model_type in train_winner
├── ranking.py       # rank_candidates / build_chart_data  ← UNCHANGED
├── explanations.py  # explain_winner                      ← UNCHANGED (decision.py is the new pure module)
├── routes.py        # APIRouter(/model-selection)         ← ADD POST /train-selected, POST /promote; extend POST /predict body
└── tests/           # conftest + unit + integration       ← ADD test_decision; extend test_routes/test_service/test_models/test_routes_integration
app/features/forecasting/service.py  # train_model / predict (feature-aware reject)   — orchestrated, not changed
app/features/registry/{service,schemas,storage}.py  # create_run/update_run/create_alias + LocalFSProvider.save — orchestrated, not changed
app/core/{config,exceptions}.py
alembic/versions/                     # head b667d321603c today; Slice B adds one; chain Slice C off the live head at impl time
frontend/src/
├── pages/visualize/champion.tsx      # Slice A/B page          ← ADD the decision section below Slice B's results
├── hooks/use-model-selection.ts      # Slice A/B hooks          ← ADD useTrainWinner/useTrainSelected/usePredictWinner/usePromoteChampion
├── types/api.ts                      # Model Selection section  ← ADD decision/promote types; EXTEND ForecastSummary
├── components/champion-selector/     # Slice A/B components      ← ADD decision/ subfamily
├── components/charts/{time-series-chart,kpi-card}.tsx
├── components/ui/{table,dialog,alert-dialog,input,select,checkbox,card,badge}.tsx
└── components/forecast-intelligence/{promote-confirmation-dialog,champion-compatibility-badge}.tsx  # promotion-UX precedents
docs/user-guide/                      # ADD champion-selector-guide.md
```

### Desired Codebase Tree (Slice C additions)

```bash
# Backend
app/features/model_selection/decision.py                       # NEW: pure forecast-decision (peak/low, z-table, safety stock, bias-risk text)
app/features/model_selection/models.py                         # MOD: + 6 nullable decision/promotion columns
app/features/model_selection/schemas.py                        # MOD: + TrainSelectedRequest, ForecastDecisionParams, ForecastDecision, PromoteRequest, PromoteResponse; EXTEND ForecastSummary + TrainWinnerResponse + PredictWinnerResponse
app/features/model_selection/service.py                        # MOD: + train_selected, promote; EXTEND predict_winner; train_winner persists trained_model_type
app/features/model_selection/routes.py                         # MOD: + POST /train-selected, POST /promote; predict gains optional body
alembic/versions/<rev>_add_model_selection_decision_promotion.py  # NEW migration (additive columns)
app/features/model_selection/tests/test_decision.py            # NEW: pure decision unit tests (z-table, safety stock, peak/low, bias text)
app/features/model_selection/tests/test_routes.py              # MOD: + train-selected, predict-with-body, promote route tests
app/features/model_selection/tests/test_service.py             # MOD: + train_selected/promote/predict-decision unit (mock Forecasting + Registry services)
app/features/model_selection/tests/test_models.py              # MOD: + new columns CRUD/default
app/features/model_selection/tests/test_schemas.py             # MOD: + new request/response schema cases (alias regex 422, defaults)
app/features/model_selection/tests/test_routes_integration.py  # MOD: + train-selected → predict → promote integration (real registry run + alias)

# Frontend (extends Slice A/B — no new route/nav)
frontend/src/types/api.ts                                      # MOD: + decision/promote types; EXTEND ForecastSummary
frontend/src/hooks/use-model-selection.ts                      # MOD: + useTrainWinner/useTrainSelected/usePredictWinner/usePromoteChampion
frontend/src/hooks/use-model-selection.test.ts                 # MOD: + train/predict/promote hook tests
frontend/src/pages/visualize/champion.tsx                      # MOD: render decision section after a terminal winning run
frontend/src/components/champion-selector/decision/winner-decision-panel.tsx       # NEW (+test): accept winner OR override (candidate select + non-recommended warning AlertDialog)
frontend/src/components/champion-selector/decision/train-forecast-actions.tsx      # NEW (+test): train + forecast buttons; capability-limited (feature-aware) blocked state
frontend/src/components/champion-selector/decision/forecast-summary-card.tsx       # NEW (+test): total/avg/peak/low/horizon KPI tiles
frontend/src/components/champion-selector/decision/forecast-chart.tsx              # NEW (+test): TimeSeriesChart wrapper
frontend/src/components/champion-selector/decision/daily-forecast-table.tsx        # NEW (+test): shadcn Table (date, forecast, lower, upper)
frontend/src/components/champion-selector/decision/business-interpretation-panel.tsx # NEW (+test): why-won + expected demand + bias risk (BIAS_EXPLANATION) + caveats
frontend/src/components/champion-selector/decision/safety-stock-panel.tsx          # NEW (+test): lead_time/service_level inputs → safety stock (labeled heuristic)
frontend/src/components/champion-selector/decision/promote-champion-dialog.tsx     # NEW (+test): alias name + approver + non-recommended ack (mirror promote-confirmation-dialog.tsx)

# Docs
docs/user-guide/champion-selector-guide.md                     # NEW: full journey + promotion-is-audited rule
docs/user-guide/feature-reference.md                           # MOD: cross-link the new guide (if it carries an index)
```

### Known Gotchas & VERIFIED Contracts

```python
# ── train-winner IS ALREADY PRESENT — DO NOT REWRITE IT ────────────────────────
# service.train_winner (service.py:405) trains ranking.winner and its tests exist. Slice C ADDS train_selected as a
# SIBLING and makes ONE additive write inside train_winner: row.trained_model_type = ranking.winner.model_type;
# row.is_override = False. The TrainWinnerResponse shape is UNCHANGED (new fields go on TrainSelectedResponse-superset,
# or set defaults on the shared response model — keep train-winner's response back-compatible).

# ── OVERRIDE VALIDATION ────────────────────────────────────────────────────────
# train_selected must reject a model_type not in the run's candidate set. The candidates live on the row:
# row.candidate_models (JSONB list of {model_type, params}). Validate against THAT set — {c["model_type"] for c in
#   row.candidate_models} — NOT only the included/ranked entries: a candidate that FAILED its backtest is still
#   override-trainable (training ≠ backtesting), so it must remain selectable. A model never offered as a candidate → 400.
# Build the ModelConfig the SAME way train_winner does:
#   TypeAdapter(ModelConfig).validate_python({"model_type": mt, **params})  (lazy import ModelConfig).
# is_override = (mt != ranking.winner.model_type). The override_warning text names the recommended model + the WAPE gap
# read from ranking entries (deterministic; no LLM). NOTE: if the chosen candidate failed backtesting it has no ranked
# metrics — the warning then states the model was not successfully evaluated rather than quoting a WAPE gap.

# ── PREDICT OPTIONAL BODY (FastAPI) ────────────────────────────────────────────
# predict currently takes NO body. To stay backward-compatible, declare:
#   request: ForecastDecisionParams | None = Body(default=None)
# and treat None as ForecastDecisionParams() defaults. A single Pydantic-model param without Body(default=...) is a
# REQUIRED body in FastAPI — that would break empty-body callers. VERIFY the empty-body path in a route test
# (POST with no body returns 200 + decision computed from defaults).
# RETURN CONTRACT: predict_winner now returns tuple[ForecastSummary, ForecastDecision | None]; the ROUTE (not the
#   service) builds PredictWinnerResponse(selection_id, forecast, decision). Do NOT have the service return the
#   response model — keep it a pure (forecast, decision) tuple so the existing happy-path service tests stay simple and
#   the route owns the HTTP shape (mirrors the merged routes.py:168 which already builds the response in the route).

# ── ForecastSummary EXTENSION IS REUSED BY SLICE A/B — KEEP IT ADDITIVE ─────────
# ForecastSummary is serialized by the sync /run auto_predict path AND Slice B. ADD peak_date/peak_demand/low_date/
# low_demand as Optional (default None) so old JSONB snapshots still validate (forecast_result reload at service.py:535).

# ── SAFETY STOCK MUST NOT TOUCH RANKING (LOCKED #3) ────────────────────────────
# decision.py is called only by predict_winner (and the UI). rank_candidates / build_chart_data NEVER receive
# safety-stock inputs. z-table is a fixed dict (NO scipy): {0.90:1.2816, 0.95:1.6449, 0.975:1.9600, 0.99:2.3263}.
# sigma_daily = statistics.pstdev([p["forecast"] for p in points]) (population stdev; 0.0 for a flat/1-point forecast →
# safety_stock 0.0 — that is honest). Verify the z math with:
#   uv run python -c "import statistics as s; pts=[10,12,8,11,9]; z=1.6449; ss=z*s.pstdev(pts)*(7**0.5); print(round(ss,3))"
# Label every decision field method='heuristic' + a caveat; the UI panel header says 'Safety stock (heuristic)'.

# ── PROMOTION ARTIFACT REGISTRATION IS THE #1 RISK — VERIFY BEFORE CODING ───────
# Forecasting train writes a joblib to row.final_model_path under ./artifacts/models (NOT registry storage). To make
# the promoted run's artifact verifiable, promote() must register the artifact into registry storage. There is NO
# RegistryService.register_artifact wrapper (verified: artifact_uri is set via PATCH; storage.save returns (hash,size)).
# BEFORE coding promote, grep how existing code registers an artifact + names artifact_uri:
#   grep -rn "\.save(" app/features/registry app/features/demo app/features/ops scripts | grep -i artifact
#   grep -rn "artifact_uri=" app/features --include=*.py | grep -v test
# Then in promote(): construct artifact_uri per that convention, call the provider's save(Path(final_model_path),
# artifact_uri) -> (hash, size), then update_run(SUCCESS, artifact_uri, artifact_hash=hash, artifact_size_bytes=size).
# FALLBACK (documented, Option-3 boundary): if artifact registration proves out of budget, ship train/predict/decision
# WITHOUT promote (a follow-up issue) rather than registering an unverifiable artifact — promotion is the LAST task.

# ── REGISTRY STATE MACHINE ─────────────────────────────────────────────────────
# create_run → PENDING (run_id = uuid hex). update_run(status=RUNNING) THEN update_run(status=SUCCESS, …). create_alias
# requires SUCCESS (registry/service.py:457 raises ValueError → map to BadRequestError/422). Do all promote DB work in
# the REQUEST db session (one transaction); RegistryService takes the same db. Lazy-import RegistryService inside
# promote() (mirror the ForecastingService lazy import at service.py:410) to avoid an alembic cold-boot import cycle.
# VERIFIED: create_run/update_run/create_alias each `await db.flush()` (NOT commit) — registry/service.py:260,419,495 —
#   so the whole promote orchestration is ONE atomic request transaction: any step raising rolls the lot back (no
#   half-promoted run). Pass the trained params via the field name `model_config_data=` (RunCreate aliases it to
#   `model_config` with populate_by_name=True, registry/schemas.py:74,77) — do NOT use the `model_config=` alias kwarg,
#   it shadows Pydantic's own ConfigDict attribute name and reads as a bug.

# ── FEATURE-FRAME-VERSION PERSISTENCE → V2 PROMOTION (LOCKED #7) ───────────────
# Slice C SUPPORTS V2 promotion by PERSISTING the run's feature_frame_version and carrying it end-to-end — NO hardcoded
# `1` in code (the only `1` is the column's server_default for legacy rows, and a fallback-error case in tests).
# WHY a column is required: feature_frame_version is a ModelSelectionRunRequest field consumed at run-creation, but it
#   is NOT available at train/promote time unless persisted (the merged ORM never stored it). To train the winner as the
#   user configured (V1 or V2) AND record the true version on the registry run, the value must live on the row.
# WIRING (all additive, Slice C owns service.py):
#   1. Migration adds `feature_frame_version INTEGER NOT NULL server_default '1'` to model_selection_run (LOCKED #7).
#      server_default '1' backfills pre-existing rows ONLY; new rows always carry the real request value.
#   2. Run-creation writes the real value: ADD `row.feature_frame_version = request.feature_frame_version` to BOTH
#      run_selection (sync, merged) AND submit_run (async, Slice B's) — both live in service.py which Slice C edits.
#      This is additive (a new column write), not a redefinition of Slice B's contract.
#   3. train_winner / train_selected pass `feature_frame_version=row.feature_frame_version` to
#      ForecastingService.train_model (the merged auto-train path already threads it — mirror that). feature_groups stays
#      None → forecasting's DEFAULT_V2_GROUPS (the champion-selector UI never exposes per-group selection; a custom-group
#      V2 run via raw curl would train on default groups — documented limitation, future PRP may persist feature_groups).
#   4. promote passes `runtime_info_extras={"feature_frame_version": row.feature_frame_version}` (the REAL value).
# This is load-bearing: the registry's PRP-36 comparable-run / stale-alias logic keys on feature_frame_version
#   (docs/_base/DOMAIN_MODEL.md; memory feature-frame-version-clamp-1-2) — a wrong value silently corrupts comparability.
# TEST the REAL propagation: a V2 run → promote records 2 (test_promote_carries_real_feature_frame_version_v2); a
#   legacy/unset row → the server_default 1 (test_promote_defaults_feature_frame_version_1_for_legacy_run, the ONLY place
#   the literal 1 appears, as a fallback case).

# ── MIGRATION (LOCKED #7) ──────────────────────────────────────────────────────
# uv run alembic heads   # chain down_revision off the LIVE head (Slice B's migration must land first).
# All seven columns are ADDITIVE (is_override + feature_frame_version are NOT NULL with server_defaults 'false'/'1';
# the rest nullable). No CheckConstraint change.
# downgrade() drops the seven columns. JSONB import in migration: from sqlalchemy.dialects import postgresql ->
# postgresql.JSONB(astext_type=sa.Text()).

# ── STRICT-MODE POLICY (LOCKED #9) ─────────────────────────────────────────────
# TrainSelectedRequest/ForecastDecisionParams/PromoteRequest are ConfigDict(strict=True) with ONLY str/int/float/bool
# fields → NO Field(strict=False) needed. app/core/tests/test_strict_mode_policy.py stays green. Add a request-body
# test that exercises Model.model_validate({...}) (the validate_python path) per the security policy.

# ── NO AGENT SURFACE ───────────────────────────────────────────────────────────
# Promotion is a USER REST flow (approved_by in the body), NOT an agent tool. Do NOT add an agent tool or an entry to
# agent_require_approval. (Widening the agent mutation surface is out of scope and would require that list update.)
```

```typescript
// ── FRONTEND ────────────────────────────────────────────────────────────────
// Slice C EXTENDS the Slice A/B champion page — it adds NO route/nav. The decision section renders only when a Slice B
// run is terminal (completed|partial) AND response.winner is non-null. Reuse Slice B's useSelectionRun(selectionId).
// HOOKS (mirror use-batches.ts / use-runs.ts useMutation shape): useTrainWinner / useTrainSelected / usePredictWinner /
//   usePromoteChampion all POST to /model-selection/{id}/... and on success invalidate ['model-selection','run',id] so
//   Slice B's GET reflects the new final_model_path / forecast / promotion. Do NOT redefine Slice A/B hooks.
// CAPABILITY LIMIT (LOCKED #5): read the winner's supports_auto_predict from useModelCatalog() (Slice A). If false,
//   render the blocked forecast state ("Forecast not available for feature-aware models — use the What-If Planner") and
//   DO NOT call usePredictWinner. The Train + Promote actions still work for feature-aware winners.
// OVERRIDE WARNING: when the user picks a candidate != winner, confirm via AlertDialog before train-selected; carry the
//   override_reason. Reuse BIAS_EXPLANATION from components/champion-selector/copy.ts (Slice A) for bias wording.
// PROMOTE DIALOG: mirror forecast-intelligence/promote-confirmation-dialog.tsx — alias-name input (regex
//   ^[a-z0-9][a-z0-9\-_]*$), approver field (required), a "promote a non-recommended model" checkbox shown only when
//   is_override; confirm → usePromoteChampion. Promote performs NO comparison (compare is separate).
// CHARTS need a ResizeObserver beforeAll stub in jsdom (backtest-horizon-buckets-chart.test.tsx pattern); pass chart
//   height via inline style (Tailwind JIT drops dynamic h-[Npx]).
// react-refresh/only-export-components: keep any non-component constants in a .ts file (reuse Slice A copy.ts or a
//   decision/constants.ts), not exported from a .tsx component.
// IDs are NOT 1-based (memory: seeder-does-not-reset-id-sequences); selection_id is backend-owned — never
//   crypto.randomUUID() client-side (memory: showcase-crypto-randomuuid-lan-crash). Dogfood over http://localhost:5173.
// Mixed CRLF/LF repo-wide (memory: repo-line-endings-crlf) — git diff --stat before committing; new files LF.
```

## Implementation Blueprint

### Backend data models

`app/features/model_selection/models.py` — additive columns on `ModelSelectionRun`:

```python
trained_model_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
is_override: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
override_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
champion_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)        # registry model_run.run_id
promoted_alias: Mapped[str | None] = mapped_column(String(100), nullable=True)
promotion_decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)  # audit record
feature_frame_version: Mapped[int] = mapped_column(                                   # M1 — V2 promotion support
    Integer, default=1, server_default="1", nullable=False
)  # set from request at run-creation (run_selection + submit_run); promote passes the REAL value to the registry
```

`app/features/model_selection/schemas.py` — additive models:

```python
class TrainSelectedRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    model_type: ModelType
    override_reason: str | None = Field(default=None, max_length=2000)

# EXTEND TrainWinnerResponse additively (defaults keep train-winner back-compatible):
#   is_override: bool = False
#   override_warning: str | None = None

class ForecastDecisionParams(BaseModel):
    model_config = ConfigDict(strict=True)
    lead_time_days: int = Field(default=7, ge=1, le=365)
    service_level: float = Field(default=0.95, ge=0.5, lt=1.0)

class ForecastDecision(BaseModel):                  # plain BaseModel (response)
    method: Literal["heuristic"] = "heuristic"
    lead_time_days: int
    service_level: float
    z_value: float
    sigma_daily_demand: float
    expected_demand_over_lead_time: float
    safety_stock: float
    reorder_point: float
    bias_risk_text: str                              # reuses BIAS_EXPLANATION + the winner's bias sign
    caveats: list[str]

# EXTEND ForecastSummary additively:
#   peak_date: date | None = None ; peak_demand: float | None = None
#   low_date: date | None = None  ; low_demand: float | None = None
# EXTEND PredictWinnerResponse additively:
#   decision: ForecastDecision | None = None

class PromoteRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    alias_name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9\-_]*$")
    approved_by: str = Field(..., min_length=1, max_length=100)
    acknowledge_non_recommended: bool = False
    description: str | None = Field(default=None, max_length=500)

class PromoteResponse(BaseModel):                    # plain BaseModel (response)
    selection_id: str
    alias_name: str
    run_id: str
    run_status: str
    model_type: str
    is_override: bool
    promoted_at: datetime
```

`app/features/model_selection/decision.py` (pure — mirror `explanations.py`):

```python
# from app.features.model_selection.copy or a local constant: the locked bias sentence (single source).
_Z_TABLE = {0.90: 1.2816, 0.95: 1.6449, 0.975: 1.9600, 0.99: 2.3263}  # one-sided service-level z (no scipy)

def z_for_service_level(service_level: float) -> float:
    # exact key, else nearest key (documented heuristic)
    ...

def compute_forecast_decision(points: list[dict], average_demand: float, lead_time_days: int,
                              service_level: float, winner_bias: float | None) -> ForecastDecision:
    import statistics
    values = [float(p["forecast"]) for p in points]
    sigma = statistics.pstdev(values) if len(values) > 1 else 0.0
    z = z_for_service_level(service_level)
    safety_stock = z * sigma * (lead_time_days ** 0.5)
    expected_lt = average_demand * lead_time_days
    bias_dir = "under-forecasts (risk of stockouts)" if (winner_bias or 0) > 0 else \
               "over-forecasts (risk of overstock)" if (winner_bias or 0) < 0 else "is roughly unbiased"
    return ForecastDecision(lead_time_days=lead_time_days, service_level=service_level, z_value=z,
        sigma_daily_demand=sigma, expected_demand_over_lead_time=expected_lt,
        safety_stock=safety_stock, reorder_point=expected_lt + safety_stock,
        bias_risk_text=f"{BIAS_EXPLANATION} For this winner, bias {winner_bias:.2f} indicates it {bias_dir}.",
        caveats=["Safety stock is a deterministic heuristic (demand variability only; constant lead time).",
                 "Not a substitute for a full inventory-optimisation model."])

def forecast_peak_low(points: list[dict]) -> tuple[date|None, float|None, date|None, float|None]:
    # max/min over points by 'forecast'; None on empty.
    ...
```

### Backend service (`app/features/model_selection/service.py`)

```python
async def train_selected(self, db, selection_id, model_type, override_reason) -> TrainWinnerResponse:
    # _load row; _load_ranking.
    # ELIGIBILITY (LOCKED #1): model_type must be one of the run's CONFIGURED candidates —
    #   {c["model_type"] for c in row.candidate_models} — else BadRequestError(400). A candidate that FAILED its
    #   backtest is STILL override-trainable (training is independent of backtesting), so validate against
    #   candidate_models, NOT only the ranked/included entries. (A model never offered as a candidate → 400.)
    # build cfg = TypeAdapter(ModelConfig).validate_python({"model_type": model_type, **params_for(model_type)});
    # train = ForecastingService().train_model(db, store, product, start, end, cfg,
    #             feature_frame_version=row.feature_frame_version)   # M1 — train as the run was configured (V1/V2)
    # row.final_model_path = train.model_path; row.trained_model_type = model_type
    # row.is_override = (model_type != ranking.winner.model_type if ranking.winner else True)
    # row.override_reason = override_reason; await db.flush()
    # override_warning = deterministic copy when is_override (names recommended model + WAPE gap), else None
    # return TrainWinnerResponse(..., is_override=row.is_override, override_warning=warning)
    # NOTE: train_winner (the merged sibling) likewise threads feature_frame_version=row.feature_frame_version when
    #   Slice C adds its `row.trained_model_type = winner; row.is_override = False` write (keep its response shape).

# EXTEND predict_winner — PIN THE RETURN CONTRACT.
#   Live signature today: `predict_winner(db, selection_id) -> ForecastSummary` (service.py:442); the ROUTE builds
#   `PredictWinnerResponse(selection_id, forecast)` (routes.py:168). Slice C must surface `decision` too, so CHANGE the
#   service return type to a TUPLE:
#     async def predict_winner(self, db, selection_id, lead_time_days: int, service_level: float)
#         -> tuple[ForecastSummary, ForecastDecision | None]
#   Body: build the ForecastSummary as today; set peak/low via decision.forecast_peak_low; compute
#   decision = decision.compute_forecast_decision(points, average_demand, lead_time_days, service_level,
#   winner_bias=row.winner_metrics.get('bias')); persist forecast_result (incl. peak/low) on the row; RETURN
#   (forecast, decision). The ROUTE (not the service) assembles PredictWinnerResponse(selection_id=…, forecast=…,
#   decision=…) — see the route blueprint below. The merged train-winner→predict happy-path tests assert only on
#   `forecast`, so they keep passing; the new `decision` field is additive (PredictWinnerResponse.decision defaults None).

async def promote(self, db, selection_id, req: PromoteRequest) -> PromoteResponse:
    from app.features.registry.schemas import RunCreate, RunUpdate, AliasCreate, RunStatus  # lazy
    from app.features.registry.service import RegistryService                                # lazy
    row = await self._load(db, selection_id)                       # 404
    if not row.final_model_path or not row.trained_model_type:
        raise UnprocessableEntityError(message="Train the model before promoting.")
    if row.is_override and not req.acknowledge_non_recommended:
        raise UnprocessableEntityError(message="Promoting a non-recommended model requires acknowledge_non_recommended=true.")
    registry = RegistryService()
    params = self._params_for_trained(row)                         # from candidate_models / winner_metrics
    run = await registry.create_run(db, RunCreate(model_type=row.trained_model_type, model_config_data=params,
            data_window_start=row.start_date, data_window_end=row.end_date, store_id=row.store_id,
            product_id=row.product_id,
            runtime_info_extras={"feature_frame_version": row.feature_frame_version}))  # REAL persisted version (LOCKED #7)
    await registry.update_run(db, run.run_id, RunUpdate(status=RunStatus.RUNNING))
    artifact_uri, ahash, asize = self._register_artifact(row.final_model_path, run.run_id)   # VERIFY mechanics (Gotchas)
    await registry.update_run(db, run.run_id, RunUpdate(status=RunStatus.SUCCESS, metrics=row.winner_metrics,
            artifact_uri=artifact_uri, artifact_hash=ahash, artifact_size_bytes=asize))
    alias = await registry.create_alias(db, AliasCreate(alias_name=req.alias_name, run_id=run.run_id,
            description=req.description))
    promoted_at = datetime.now(UTC)
    row.champion_run_id = run.run_id; row.promoted_alias = alias.alias_name
    row.promotion_decision = {"decision_id": uuid.uuid4().hex, "alias": alias.alias_name,
        "champion_run_id": run.run_id, "approved_by": req.approved_by, "approved_at": promoted_at.isoformat(),
        "decision": "promoted", "reason": req.description, "trained_model_type": row.trained_model_type,
        "is_override": row.is_override}
    await db.flush()
    return PromoteResponse(selection_id=row.selection_id, alias_name=alias.alias_name, run_id=run.run_id,
        run_status=alias.run_status, model_type=row.trained_model_type, is_override=row.is_override, promoted_at=promoted_at)
```

### Backend routes (`app/features/model_selection/routes.py`)

```python
@router.post("/{selection_id}/train-selected", response_model=TrainWinnerResponse, status_code=200)
async def train_selected(selection_id: str, request: TrainSelectedRequest, db=Depends(get_db)):
    try: return await ModelSelectionService().train_selected(db, selection_id, request.model_type, request.override_reason)
    except ValueError as exc: raise BadRequestError(message=str(exc)) from exc
    except SQLAlchemyError as exc: raise DatabaseError(message="Failed to train selected model", details={"error": str(exc)}) from exc

# predict gains an optional body; the ROUTE assembles the response from the service tuple (service returns
# tuple[ForecastSummary, ForecastDecision | None], NOT the response model):
@router.post("/{selection_id}/predict", response_model=PredictWinnerResponse, status_code=200)
async def predict_winner(selection_id: str, request: ForecastDecisionParams | None = Body(default=None), db=Depends(get_db)):
    params = request or ForecastDecisionParams()
    service = ModelSelectionService()
    try:
        forecast, decision = await service.predict_winner(db, selection_id, params.lead_time_days, params.service_level)
        return PredictWinnerResponse(selection_id=selection_id, forecast=forecast, decision=decision)
    except ValueError as exc: raise BadRequestError(message=str(exc)) from exc   # feature-aware reject → 400
    except SQLAlchemyError as exc: raise DatabaseError(message="Failed to forecast with winning model", details={"error": str(exc)}) from exc

@router.post("/{selection_id}/promote", response_model=PromoteResponse, status_code=200)
async def promote(selection_id: str, request: PromoteRequest, db=Depends(get_db)):
    try: return await ModelSelectionService().promote(db, selection_id, request)
    except ValueError as exc: raise BadRequestError(message=str(exc)) from exc   # registry "only SUCCESS runs" → 400
    except SQLAlchemyError as exc: raise DatabaseError(message="Failed to promote champion", details={"error": str(exc)}) from exc
# NotFoundError(404)/UnprocessableEntityError(422) raised in-service bubble to the global handler.
```

### Implementation Tasks (dependency-ordered)

```yaml
# ───────────────────────── BACKEND ─────────────────────────
Task 1 — Schemas:
  MODIFY app/features/model_selection/schemas.py: + TrainSelectedRequest, ForecastDecisionParams, ForecastDecision,
    PromoteRequest, PromoteResponse; EXTEND ForecastSummary (peak/low Optional), TrainWinnerResponse (is_override,
    override_warning defaults), PredictWinnerResponse (decision Optional).
  MODIFY tests/test_schemas.py: alias_name regex 422; service_level bound; back-compat defaults; validate_python path.

Task 2 — Pure decision module:
  CREATE app/features/model_selection/decision.py: z_for_service_level, compute_forecast_decision, forecast_peak_low
    (pure, no DB/IO; mirror explanations.py). Reuse the locked bias sentence (single constant).
  CREATE tests/test_decision.py: z-table exact + nearest; safety_stock=z*pstdev*sqrt(L) (verify one-liner); flat forecast
    → safety_stock 0.0; peak/low correctness; bias text under/over/neutral.

Task 3 — ORM + migration:
  MODIFY app/features/model_selection/models.py: + the seven columns (Boolean + Integer imports) — the six
    decision/promotion columns PLUS feature_frame_version (Integer, NOT NULL, server_default "1", default 1).
  RUN: uv run alembic heads   # chain off the LIVE head (Slice B migration must precede)
  CREATE alembic/versions/<rev>_add_model_selection_decision_promotion.py: add_column x7 (server_default 'false' for
    is_override; server_default '1' for feature_frame_version — backfills legacy rows only); downgrade drops all seven.
    NO CheckConstraint change.
  MODIFY tests/test_models.py: defaults (is_override False, feature_frame_version 1); JSONB promotion_decision round-trip.

Task 4 — Service:
  MODIFY app/features/model_selection/service.py:
    - PERSIST feature_frame_version at run-creation (M1): ADD `row.feature_frame_version = request.feature_frame_version`
      in run_selection (sync, merged) AND submit_run (async, Slice B's) — additive column write, both live here.
    - + train_selected (validate against row.candidate_models incl. failed candidates; thread
      feature_frame_version=row.feature_frame_version into train_model), + promote (lazy RegistryService import; pass
      runtime_info_extras={"feature_frame_version": row.feature_frame_version} — the REAL value, never a hardcoded 1).
    - EXTEND predict_winner → returns tuple[ForecastSummary, ForecastDecision | None] (route assembles the response).
    - + _params_for_trained, + _register_artifact helper; train_winner additively sets trained_model_type/
      is_override=False and threads feature_frame_version=row.feature_frame_version into its train_model call.
      REUSE _load/_load_ranking/_forecast_summary.
  MODIFY tests/test_service.py: train_selected happy + non-candidate 400 + override warning + failed-candidate still
    trainable; predict decision math + tuple return; run-creation persists request feature_frame_version; train_selected
    threads V2 into train_model; promote orchestration with monkeypatched "app.features.registry.service.RegistryService"
    (create_run/update_run/create_alias) + "app.features.forecasting.service.ForecastingService"; promote carries the
    REAL feature_frame_version (V2 run → 2); promote-before-train 422; non-recommended-no-ack 422.

Task 5 — Routes:
  MODIFY app/features/model_selection/routes.py: + POST /train-selected, + POST /promote; predict gains
    `request: ForecastDecisionParams | None = Body(default=None)`. Mirror error mapping.
  MODIFY tests/test_routes.py (ASGITransport _client harness): train-selected 200 + 400 (bad model_type);
    predict no-body 200 (decision from defaults) + with-body 200; promote 200 + 422 (before train / no ack) +
    422 (bad alias_name via schema); train-winner unchanged (regression).

Task 6 — Integration:
  MODIFY tests/test_routes_integration.py (@pytest.mark.integration, real engine, prefix-scoped teardown):
    seed a pair → POST /runs (or legacy /run) to terminal winner → train-selected/train-winner → predict (decision
    present, peak/low set) → promote → assert a registry model_run (SUCCESS) + alias exist and champion_run_id/
    promoted_alias/promotion_decision persisted on the selection, and the registry run's runtime_info carries the run's
    REAL feature_frame_version (a V2-configured run promotes as 2). Teardown must also clean the created registry
    run/alias (extend the prefix-scoped finally; delete RunAlias + ModelRun by run_id/store_id).

# ───────────────────────── FRONTEND (extends Slice A/B) ─────────────────────────
Task 7 — Types:
  MODIFY frontend/src/types/api.ts (Model Selection section): + TrainSelectedRequest, ForecastDecisionParams,
    ForecastDecision, PromoteRequest, PromoteResponse; EXTEND ForecastSummary (peak/low) + train/predict response types.
    Do NOT redefine Slice A/B types.

Task 8 — Hooks:
  MODIFY frontend/src/hooks/use-model-selection.ts: + useTrainWinner, useTrainSelected, usePredictWinner,
    usePromoteChampion (useMutation; on success invalidate ['model-selection','run', id]). MIRROR use-runs.ts mutation shape.
  MODIFY hooks/use-model-selection.test.ts: each hook POSTs to the right /model-selection/{id}/... endpoint; cache invalidated.

Task 9 — Decision components (components/champion-selector/decision/):
  CREATE winner-decision-panel.tsx (+test): show recommended winner; candidate Select to override; AlertDialog warning
    + override_reason when picking non-winner; calls useTrainWinner / useTrainSelected.
  CREATE train-forecast-actions.tsx (+test): Train + Forecast buttons; if winner.supports_auto_predict===false (catalog),
    render the blocked "feature-aware → use What-If Planner" state and disable Forecast.
  CREATE forecast-summary-card.tsx (+test): KpiCard tiles — total/avg/peak day/low day/horizon (null-safe).
  CREATE forecast-chart.tsx (+test): TimeSeriesChart wrapper (predictedKey='forecast', interval if bounds).
  CREATE daily-forecast-table.tsx (+test): shadcn Table — date, forecast, lower, upper.
  CREATE business-interpretation-panel.tsx (+test): headline/why-won (from business_summary) + expected demand +
    bias_risk_text (BIAS_EXPLANATION) + caveats.
  CREATE safety-stock-panel.tsx (+test): lead_time/service_level inputs → re-predict (or recompute) → labeled
    "Safety stock (heuristic)" with z, sigma, expected demand, reorder point + caveat.
  CREATE promote-champion-dialog.tsx (+test): alias-name input (regex), approver field, non-recommended ack checkbox
    (only when is_override) → usePromoteChampion; success toast + show promoted alias. MIRROR promote-confirmation-dialog.tsx.

Task 10 — Page wiring:
  MODIFY frontend/src/pages/visualize/champion.tsx: when useSelectionRun is terminal AND winner != null, render the
    decision section (WinnerDecisionPanel → TrainForecastActions → ForecastSummaryCard + ForecastChart + DailyForecastTable
    → BusinessInterpretationPanel + SafetyStockPanel → PromoteChampionDialog). Gate forecast on supports_auto_predict.
    Do NOT alter Slice B's progress/results blocks above it.

# ───────────────────────── DOCS + DOGFOOD ─────────────────────────
Task 11 — User guide:
  CREATE docs/user-guide/champion-selector-guide.md: the full journey (select → run → results → decide/override → train →
    forecast → interpret → promote), the WAPE-default + tie-break note, the bias under/over wording, the safety-stock
    heuristic caveat, and the "promotion requires explicit approval and is recorded" rule. Cross-link from feature-reference.md.

Task 12 — Dogfood (manual; see Validation Loop):
  Run the end-to-end probe over http://localhost:5173 with REAL discovered ids; confirm train-selected override warning,
  forecast summary/chart/table, business + safety-stock panels, the feature-aware blocked state, and a gated promote that
  yields a registry alias. Capture a note in the PR description.
```

### Integration Points

```yaml
DATABASE:
  - migration: + trained_model_type / is_override / override_reason / champion_run_id / promoted_alias /
    promotion_decision on model_selection_run (all nullable; is_override server_default 'false'). No constraint change.
CONFIG: none new (reuses forecast_model_artifacts_dir + registry_artifact_root + the registry storage provider).
ROUTES (backend): app/features/model_selection/routes.py only (+ /train-selected, /promote; predict body) — router
  already wired in app/main.py.
CROSS-SLICE (lazy imports inside service methods, mirroring the existing ForecastingService import):
  - ForecastingService (train_selected); RegistryService + registry schemas (promote). NEVER import another slice's
    ORM at module scope beyond the sanctioned data_platform read.
FRONTEND: no new ROUTE/NAV (Slice A added /visualize/champion); extend the page + hooks + types only.
OBSERVABILITY (structlog, mirror existing model_selection.* events):
  - model_selection.winner_selected_override / .winner_predicted (extend) / .champion_promoted (approved_by, alias, run_id).
DOCS: docs/user-guide/champion-selector-guide.md (+ feature-reference.md cross-link).
```

## Validation Loop

### Level 1 — Backend syntax & policy

```bash
uv run ruff check app/features/model_selection app/features/model_selection/decision.py alembic/versions
uv run ruff format --check app/features/model_selection alembic/versions
uv run mypy app/features/model_selection
uv run pyright app/features/model_selection
uv run pytest app/core/tests/test_strict_mode_policy.py -v   # must stay green (no new strict date field)
```

### Level 2 — Backend unit tests

```bash
uv run pytest app/features/model_selection/tests -v -m "not integration"
```
Required new test names (additive to the A/B suite):
- `test_train_selected_trains_chosen_candidate` / `test_train_selected_rejects_non_candidate_model_type_400`
- `test_train_selected_sets_is_override_and_warning_for_non_winner`
- `test_train_winner_now_persists_trained_model_type_not_override`  (regression: train-winner response shape unchanged)
- `test_decision_z_table_exact_and_nearest` / `test_safety_stock_formula_matches_z_sigma_sqrt_l` / `test_flat_forecast_safety_stock_zero`
- `test_forecast_peak_low_picks_max_and_min` / `test_bias_risk_text_under_over_neutral`
- `test_predict_attaches_decision_and_peak_low` / `test_predict_empty_body_uses_default_lead_time_service_level`
- `test_promote_requires_trained_model_422` / `test_promote_non_recommended_requires_ack_422`
- `test_promote_orchestrates_create_run_success_and_alias` (mock RegistryService) / `test_promote_persists_promotion_decision_audit`
- `test_promote_carries_real_feature_frame_version_v2` (a V2 run → RunCreate.runtime_info_extras["feature_frame_version"] == 2; NOT hardcoded)
- `test_promote_defaults_feature_frame_version_1_for_legacy_run` (unset/legacy row → server_default 1 — the ONLY fallback case using the literal 1)
- `test_run_creation_persists_request_feature_frame_version` (run_selection + submit_run write row.feature_frame_version from the request)
- `test_train_selected_threads_feature_frame_version_into_train_model` (V2 run → train_model called with feature_frame_version=2)
- `test_promote_bad_alias_name_422` (schema regex)

### Level 3 — Migration & integration

```bash
docker compose up -d
uv run alembic upgrade head
uv run pytest app/features/model_selection/tests -v -m integration
uv run alembic downgrade -1 && uv run alembic upgrade head   # round-trips cleanly
```
Integration expectations: the seven columns exist (incl. feature_frame_version); train-selected → predict (decision + peak/low) → promote produces a
registry `model_run` in SUCCESS + a `run_alias`, with `champion_run_id`/`promoted_alias`/`promotion_decision` persisted;
teardown removes the created registry run/alias (extend the prefix-scoped cleanup).

### Level 4 — Full gates (must be green before PR)

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
uv run pytest -v -m "not integration"
cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run
```
> Known-local-noise: mypy/pyright report pre-existing lightgbm/xgboost optional-dep import errors in forecasting/+registry/
> (CI installs the extras). Do NOT "fix" them; a green LOCAL mypy can MASK errors that only surface once the extras resolve
> types (memory: the #355 finalizer cast). Reset the DB (`docker compose down -v && up -d && alembic upgrade head`) before
> any Level-3 integration run (memory: integration-suite-shared-state-pollution).

### Manual dogfood probe (discover REAL ids first — IDs are NOT 1-based)

```bash
uv run uvicorn app.main:app --port 8123 &
curl -s "http://localhost:8123/dimensions/stores?page=1&page_size=5"  | python3 -m json.tool | grep '"id"'
curl -s "http://localhost:8123/dimensions/products?page=1&page_size=5" | python3 -m json.tool | grep '"id"'
# 1) run a comparison (Slice B async, or legacy sync /run) to a terminal winner; capture <selection_id>
# 2) train the recommended winner (no body) OR override:
curl -s -X POST "http://localhost:8123/model-selection/<sid>/train-selected" -H "Content-Type: application/json" \
  -d '{"model_type":"seasonal_naive","override_reason":"seasonality"}' | python3 -m json.tool   # is_override + override_warning
# 3) forecast with a decision body (baseline winner only — feature-aware → 400):
curl -s -X POST "http://localhost:8123/model-selection/<sid>/predict" -H "Content-Type: application/json" \
  -d '{"lead_time_days":7,"service_level":0.95}' | python3 -m json.tool | grep -E 'peak|low|safety_stock|reorder'
# 4) promote (approval-gated, audited):
curl -s -X POST "http://localhost:8123/model-selection/<sid>/promote" -H "Content-Type: application/json" \
  -d '{"alias_name":"champion-test","approved_by":"dogfood","acknowledge_non_recommended":true}' | python3 -m json.tool
curl -s "http://localhost:8123/registry/aliases/champion-test" | python3 -m json.tool    # alias → SUCCESS run
# 5) frontend: VITE_API_BASE_URL=http://localhost:8123; dogfood /visualize/champion over http://localhost:5173 (NOT a LAN IP).
```
Expected: train-selected returns `override_warning` on a non-winner; predict returns peak/low + a labeled safety-stock
decision (and 400 for a feature-aware winner, where the UI shows the blocked state); promote returns the alias and a
registry SUCCESS run; the page renders the full decision section.

## Final Validation Checklist

- [ ] `POST /{id}/train-selected` trains a chosen candidate; non-candidate model_type → 400; override persists
      `is_override`/`override_reason` + returns `override_warning`; `train-winner` response shape unchanged (regression green).
- [ ] `POST /{id}/predict` (empty or bodied) returns peak/low + a labeled `decision`; safety stock never feeds ranking;
      feature-aware winner → clean 400 + UI blocked state (no predict call).
- [ ] `POST /{id}/promote`: requires `approved_by`; non-recommended-no-ack → 422; before-train → 422; bad alias_name → 422;
      success creates a SUCCESS registry run + alias and persists `champion_run_id`/`promoted_alias`/`promotion_decision`.
- [ ] `decision.py` is pure; z-table + safety-stock + peak/low + bias text deterministically unit-tested.
- [ ] Migration adds seven columns (six decision/promotion + feature_frame_version); promote carries the REAL persisted version (V2 run → 2, never a hardcoded 1); `downgrade` removes them on a fresh DB; strict-mode policy test green.
- [ ] Ranking math (`ranking.py`/`explanations.py`) UNCHANGED; Slice A/B contracts (page/hooks/types/run/progress/results)
      NOT redefined.
- [ ] Frontend decision section renders after a terminal winning run: accept/override → train → forecast (summary/chart/
      table) → business interpretation (bias + labeled safety stock + caveats) → gated promote; feature-aware → blocked.
- [ ] `docs/user-guide/champion-selector-guide.md` exists (full journey + promotion-is-audited rule); cross-linked.
- [ ] All Level-1..4 gates pass; dogfood journey completes; `gh issue view <N>` confirms the tracking issue is open.
- [ ] `git diff --stat` shows no CRLF whole-file noise; `docker-compose.lan.yml` + `uv.lock` NOT staged.

## Anti-Patterns to Avoid

- ❌ Don't rewrite or change the signature/response of the existing `train-winner` / `predict` (Slice B treats them as
  fixed) — ADD `train-selected`, an OPTIONAL predict body, and additive response fields only.
- ❌ Don't let safety stock (or any decision-layer value) flow into `rank_candidates`/`build_chart_data` — it must never
  affect ranking (LOCKED #3 + coordination contract).
- ❌ Don't fake a forecast for a feature-aware winner — surface the capability limitation (Slice A's
  `supports_auto_predict`) and route the user to the What-If Planner.
- ❌ Don't auto-promote — promotion requires explicit `approved_by` + a recorded `promotion_decision`; a non-recommended
  model requires `acknowledge_non_recommended=true`.
- ❌ Don't perform comparison inside promote (compare and promote are separate workflows).
- ❌ Don't register an unverifiable artifact — register the bundle into registry storage (hash + size) before SUCCESS;
  if that mechanic is out of budget, ship Option-3 scope (no promote) + a follow-up issue rather than a fake artifact.
- ❌ Don't import another feature slice's ORM/service at module scope — lazy-import `ForecastingService`/`RegistryService`
  inside the methods (mirror the existing pattern at `service.py:410`).
- ❌ Don't add an agent tool or `agent_require_approval` entry (promotion is a user REST flow, not an agent mutation).
- ❌ Don't hardcode `feature_frame_version=1` in promote — persist the request's real version on `model_selection_run`
  and pass `row.feature_frame_version` into `runtime_info_extras` (V2 runs must promote as V2). The literal `1` appears
  ONLY as the column's migration server_default (legacy backfill) and as a fallback-case test.
- ❌ Don't add a new strict request model with a date/UUID/Decimal field (none is needed) — keeps the strict-mode linter green.
- ❌ Don't hardcode store_id=1/product_id=1 (IDs aren't 1-based); don't `crypto.randomUUID()` client-side; dogfood over
  http://localhost:5173, not a LAN IP.
- ❌ Don't redefine Slice A/B types/page/hooks/route — extend additively; keep the legacy sync `POST /run` and async
  `POST /runs` untouched.

## Confidence Score

**7.5/10** for one-pass implementation success. The core decision actions are de-risked: `train-winner` and `predict`
already exist and are read verbatim, every reused contract (forecasting train/predict, registry create_run/update_run/
create_alias, storage.save, the exception classes, the test harness, the frontend chart/promote-dialog precedents) is
cited to file:line, and the safety-stock heuristic is a small pure function with a verification one-liner. The score is
below Slice A/B's 8.5 for three reasons: (a) **promotion orchestration** (register run → register artifact → SUCCESS →
alias) is genuinely novel for this slice and the *artifact-registration* call is the one mechanic not fully pinned —
the PRP mandates a grep-verify step + a documented Option-3 fallback before coding it; (b) Slice C has a **hard A→B→C
dependency** — its frontend extends pages/hooks/types that are still unimplemented PRPs, so it cannot land until A and B
merge; (c) the **integration test must clean up created registry runs/aliases** (cross-slice teardown), a sharp edge the
existing prefix-scoped fixture doesn't yet cover. All three are called out with concrete mitigations above. A fourth,
smaller touch (M1): supporting **V2 promotion** adds a `feature_frame_version` column persisted at run-creation in BOTH
`run_selection` and `submit_run`, threaded into training, and carried into the registry run's `runtime_info_extras` —
additive and low-risk, but it means Slice C makes a one-line write inside Slice B's `submit_run` (documented in LOCKED #7).

### Scoring table (packaging brainstorm)

| Option | User value | Repo fit | Impl clarity | Risk control | Dep isolation | Total /25 |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|
| **1 — Extend model_selection with decision endpoints + decision.py + decision UI (CHOSEN)** | 5 | 5 | 4 | 4 | 4 | **22** |
| 3 — Forecast output only; defer promotion/governance (de-risking fallback) | 2 | 4 | 5 | 5 | 5 | 21 |
| 2 — Frontend reuses /forecasting + /registry directly; no new model_selection endpoints | 4 | 2 | 2 | 2 | 2 | 12 |
