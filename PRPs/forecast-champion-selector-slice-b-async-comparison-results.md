name: "Forecast Champion Selector — Slice B: Async Comparison + Results Visualization"
description: |
  Convert the synchronous champion-comparison into a real DB-backed long-running
  operation (LRO) and build the results-visualization half of the UI. Adds an
  async submit endpoint (202 + Location/Retry-After/monitor_url/cancel_url), a
  polling read with live per-candidate progress, cooperative honest cancellation,
  a new per-candidate execution table, and the frontend progress panel + ranking
  table + winner card + comparison charts + model detail drawer + partial-state
  handling. Slice B STOPS before final-model decisioning: it does NOT train the
  winner, generate a forecast, render a business summary beyond the existing
  deterministic `business_summary`, do manual winner override, or promote/register
  a champion — those are Slice C.

**Created:** 2026-06-01 · **Slice:** B of 3 (A → B → C)
**Current repo base observed:** `dev` @ `6c3f8d4` (Merge PR #354 — `model_selection` backend merged)
**Backend foundation (source of truth):** `PRPs/forecast-champion-selector-backend.md` (issue #353, MERGED) +
the live slice `app/features/model_selection/` (schemas/service/routes/ranking/explanations/models verified 2026-06-01).
**Slice A (FIXED upstream dependency):** `PRPs/forecast-champion-selector-slice-a-selection-capability.md` —
owns `/visualize/champion` page, `hooks/use-model-selection.ts`, `types/api.ts` "Model Selection" section,
`components/champion-selector/*`, the `GET /model-selection/models` catalog, and the assembled
`ModelSelectionRunRequest`. Slice B EXTENDS these; it MUST NOT redefine Slice A contracts.
**Async precedent (source of truth):** `app/features/batch/` (runner/routes/models/service) +
`PRPs/ai_docs/asyncio-taskgroup-cancellation.md` (the repo's own, runtime-verified, asyncio LRO doc).
**Working-tree caveat:** `docker-compose.lan.yml` is an untracked local dogfood override; do NOT commit it.
**Tracking issue:** create before implementation, suggested title
`feat(api,db,ui): forecast champion selector slice B — async comparison & results`.
**Suggested branch:** `feat/champion-selector-slice-b` (off `dev`, per `.claude/rules/branch-naming.md`).
**Commit scope:** `api` (async endpoints + runner + service), `db` (child table + additive columns migration),
`ui` (results page/components/hooks/types). One migration. Every commit references the tracking issue.

---

## VALIDATE — What exists vs. what Slice B adds

### Already merged (the foundation Slice B builds on)

- **`POST /model-selection/run` is SYNCHRONOUS and blocking.** `ModelSelectionService.run_selection`
  (`app/features/model_selection/service.py:211`) loops candidates **sequentially in-process**
  (`for candidate in request.candidate_models:` :274), runs each `BacktestingService().run_backtest`
  (:279), ranks (`rank_candidates` :308), builds chart data (`build_chart_data` :370), and flips the
  single `model_selection_run` row to a terminal status **before the request returns 200**. There is
  **no progress, no per-candidate status rows, no cancellation**. The `PENDING`/`RUNNING` enum values
  exist (`models.py:36-40`) but the row is only ever observed in its terminal state by any reader.
- **Pure logic Slice B REUSES unchanged:** `ranking.rank_candidates` / `ranking.build_chart_data`
  (`ranking.py:116,250`), `explanations.explain_winner` (`explanations.py`), and the service mappers
  `_shape_candidate` / `_shape_failed_candidate` / `_forecast_summary` / `_response` (`service.py:468-568`).
- **The stable contract Slice A's TS types mirror:** `ModelSelectionRunResponse` (`schemas.py:267`),
  `ModelRankEntry` (:195), `WinnerSummary` (:216), `ChartData` (:225), `RankingResult` (:207),
  `CandidateResult`+`FoldChart` (:178,169), `PairAvailabilityResponse` (:239).
- **The proven async LRO pattern lives in `app/features/batch/`** — but in another slice, so it cannot
  be imported (vertical-slice rule). It is the TEMPLATE Slice B mirrors slice-locally.

### Slice B's gaps to fill

1. **No true async run.** Batch's own `POST` `await`s the run to completion inline
   (`batch/service.py:178` `await runner.run_batch(...)`; `batch/routes.py:52` returns the *settled*
   parent) — a 202-shaped but client-blocking call. Slice B needs **fire-and-forget**: POST returns
   202 *immediately* with `status=running`, the work continues in a detached task, the client polls.
2. **No per-candidate execution records** — needed for live progress + audit of failed/cancelled candidates.
3. **No cancellation** — no cooperative cancel, drain, or `cancelled` terminal state.
4. **No results UI** — no progress panel, ranking table, winner card, comparison charts, detail drawer,
   or partial-state rendering. Slice A ships only the selection shell with a DISABLED "Run comparison" CTA.

---

## BRAINSTORM / RERANK — Chosen packaging

Three packaging alternatives for the async conversion were scored (user value / repo fit / implementation
clarity / risk control / dependency isolation, each 1–5; total /25):

| # | Option | User | Repo fit | Clarity | Risk | Isolation | **Total** |
|---|--------|:----:|:--------:|:-------:|:----:|:---------:|:---------:|
| **A** | **Fire-and-forget LRO: new `POST /runs` (202, immediate) + `model_selection_candidate` child table + slice-local TaskGroup runner + additive progress on GET + `DELETE` cancel/drain. Reuse all existing pure logic at settle.** | 5 | 5 | 4 | 4 | 5 | **23 ✅** |
| C | New `/runs` + child table but **sequential** (concurrency=1, plain background task, no Semaphore/TaskGroup) | 3 | 3 | 5 | 5 | 5 | 21 |
| B | **Convert `/run` in place** to async + reuse the parent's JSONB `candidate_results` for progress (no child table) | 4 | 2 | 3 | 2 | 2 | 13 |

**Chosen: Option A.** It matches the brief exactly (parallel fan-out, true progress, honest cancel,
rich results), mirrors the merged `batch` precedent (lowest novel-code risk), and keeps the legacy
synchronous `POST /run` + the entire Slice A contract intact (additive only). Option C is the honest
fallback — and is **one config away** from A: setting `model_selection_global_max_parallel=1` makes the
Semaphore degenerate to sequential, so A *subsumes* C with no redesign. Option B is rejected: concurrent
candidate tasks writing the SAME parent row's `candidate_results` JSONB is a read-modify-write lost-update
race (the very reason batch uses child rows), and converting `/run` in place mutates a contract Slice A's
types + the backend tests lock — higher blast radius for no gain.

**One deliberate divergence from batch:** batch `await`s the runner inline; Slice B **detaches** the
runner via `asyncio.create_task` so POST returns 202 before the work finishes (see LOCKED #2 + Known
Gotchas). Everything else — the per-child-session runner internals, `CancelHandle` registry, drain→504,
settle-then-`mark_completed` ordering — is mirrored verbatim.

**Non-goals (Slice C, do NOT build here):** winner train/predict from this run, forecast summary/chart/daily
table, safety-stock heuristic, manual winner override, champion/alias promotion, user-guide docs,
end-to-end dogfood of the full journey. Slice B may surface the EXISTING deterministic `business_summary`
JSONB read-only, but adds no new business-interpretation logic.

---

## Goal

**Feature Goal:** Turn champion comparison into a genuine long-running operation a user can submit, watch
progress on, cancel, and read rich comparison results from — wired into the Slice A `/visualize/champion`
page so the previously-disabled "Run comparison" CTA now launches an async run and streams a live progress
panel that resolves into a ranking table, winner card, comparison charts, and a per-model detail drawer.

**Deliverable:**
- **Backend:** `POST /model-selection/runs` (202, immediate, fire-and-forget) + `DELETE /model-selection/{selection_id}`
  (cooperative cancel + drain) + additive progress fields on the existing `GET /model-selection/{selection_id}`;
  a new `model_selection_candidate` child table + additive `model_selection_run` columns + one Alembic
  migration; a slice-local `runner.py` (TaskGroup + Semaphore + `CancelHandle` registry, mirror of
  `batch/runner.py`); new `Settings.model_selection_global_max_parallel` + `model_selection_cancel_drain_timeout_seconds`.
- **Frontend (extends Slice A):** new mutation/poll hooks in `hooks/use-model-selection.ts`
  (`useSubmitSelectionRun`, `useSelectionRun` polling, `useCancelSelectionRun`); a results component family
  under `components/champion-selector/results/` (progress panel, ranking table, winner card, comparison
  charts, model-detail drawer, partial-state empty/error); the `/visualize/champion` page wires the CTA →
  submit → poll → results; additive types in the Slice-A `types/api.ts` "Model Selection" section.

**Success Definition:**
1. `POST /model-selection/runs` (same `ModelSelectionRunRequest` body Slice A assembles) returns **202**
   within ~tens of ms, with a `selection_id`, `status="running"`, a `Location`/`monitor_url`
   (`/model-selection/{id}`), a `cancel_url` (`/model-selection/{id}`), and a `Retry-After` header — BEFORE
   any backtest finishes.
2. `GET /model-selection/{selection_id}` returns live progress while running (counts + a per-candidate
   list with `pending|running|completed|failed|cancelled`), and on terminal status returns the SAME
   `ranking`/`winner`/`chart_data`/`business_summary` shape the legacy sync `/run` produces today.
3. `DELETE /model-selection/{selection_id}` cooperatively cancels: pending candidates skip, running ones
   stop at the next safe yield (sklearn/LightGBM mid-fit may finish first — honest), no candidate is left
   `running` after drain; returns 200 (settled), 404 (missing), 409 (already terminal), or 504 (drain timeout).
4. The `/visualize/champion` page CTA submits, shows a live progress panel, then renders a ranking table,
   winner card, WAPE/MAE/sMAPE/bias + fold-stability + actual-vs-predicted charts, a per-model detail
   drawer, and a clear partial-success / all-failed / cancelled state. Failed candidates stay visible.
5. All Slice B validation gates pass (backend Level-1..4 incl. migration up/down + integration; frontend
   `tsc`/`lint`/`test`).

## Why

- A multi-fold backtest across up to 10 candidates is genuinely long on a laptop; a blocking request gives
  no feedback and cannot be stopped. Users need progress and an honest cancel.
- The brief mandates a **true DB-backed LRO** (not FastAPI BackgroundTasks for heavy fits) with cooperative
  cancellation and **one AsyncSession per concurrent candidate** — the batch slice already proves this on
  this exact host/runtime, so Slice B inherits a de-risked pattern.
- Slice A delivered the configuration half; Slice B delivers the *answer* half (which model won, by how
  much, how stable across folds) — the payoff that makes the selector worth using.
- Keeps the single-host architecture: no queue, no broker, no cloud SDK — just asyncio + Postgres.

## What

### New / changed endpoints (all under the existing `APIRouter(prefix="/model-selection")`)

```http
POST   /model-selection/runs            # NEW — async submit, 202 immediate, fire-and-forget
GET    /model-selection/{selection_id}  # EXISTING — additive progress fields (no breaking change)
DELETE /model-selection/{selection_id}  # NEW — cooperative cancel + drain
# UNCHANGED & KEPT: GET /availability, GET /models (Slice A), POST /run (legacy sync), GET /{id}/ranking
# Slice C owns: POST /{id}/train-winner, POST /{id}/predict (already present; Slice B does NOT call them)
```

`POST /model-selection/runs` 202 response (additive superset of `ModelSelectionRunResponse`):

```json
{
  "selection_id": "9f3c…",
  "status": "running",
  "store_id": 5, "product_id": 8,
  "monitor_url": "/model-selection/9f3c…",
  "cancel_url": "/model-selection/9f3c…",
  "progress": { "total": 5, "pending": 5, "running": 0, "completed": 0, "failed": 0, "cancelled": 0 },
  "candidate_progress": [
    { "candidate_id": "a1…", "model_type": "naive", "status": "pending", "ordinal": 0,
      "error": null, "started_at": null, "completed_at": null, "duration_ms": null }
  ],
  "ranking": [], "winner": null, "chart_data": null, "business_summary": null,
  "created_at": "…", "started_at": "…", "completed_at": null
}
```
Headers: `Location: /model-selection/9f3c…`, `Retry-After: 2`.

### LOCKED Slice-B decisions

1. **New async endpoint is `POST /model-selection/runs`** (plural), distinct from the legacy synchronous
   `POST /run` (singular), which is **kept unchanged** (existing tests + Slice A's typed `/run` notes
   remain valid). The request body is the EXISTING `ModelSelectionRunRequest` verbatim (Slice A already
   assembles it). Declare `/runs` BEFORE `GET /{selection_id}` is irrelevant for method collision (POST vs
   GET), but for consistency declare all literal routes before path-param routes.
   **Note:** the UI calls `POST /runs` (async); after Slice B the legacy `POST /run` (sync) has **no frontend
   caller** — it is retained only for back-compat + the merged backend tests. Do NOT wire `/run` into the
   frontend (and do NOT delete it).
2. **Fire-and-forget, NOT await-inline.** The `POST /runs` handler: (a) inserts the parent (`status=running`,
   `started_at=now`) + N `model_selection_candidate` child rows (`status=pending`) using the REQUEST session
   and commits; (b) launches the worker as a **detached** `asyncio.create_task`, holding a reference (GC
   foot-gun — see Gotchas); (c) returns 202 immediately. The worker uses its OWN sessions via
   `get_session_maker()` (`app/core/database.py:33`) — NEVER the request `db` (it closes when the request
   returns). This is the ONE divergence from `batch/service.py:178` (which `await`s inline).
3. **Per-candidate execution rows, never JSONB-in-parent for progress.** Each candidate is a
   `model_selection_candidate` row carrying `status`, `result` (the full `CandidateResult` JSONB incl.
   folds, written on success), `error_message`/`error_type`, `started_at`/`completed_at`/`duration_ms`,
   `ordinal`. Concurrent tasks write their OWN child rows in their OWN sessions — no shared-row write race
   (the reason Option B was rejected). Live progress on GET is a `GROUP BY status` over children (race-free);
   final counts are cached on the parent at settle.
4. **Bounded parallel via a slice-local runner.** `app/features/model_selection/runner.py` mirrors
   `app/features/batch/runner.py`: a module-level `_ACTIVE_SELECTIONS: dict[str, CancelHandle]` registry,
   `asyncio.TaskGroup` + `asyncio.Semaphore(min(req-cap, global-cap))`, one `AsyncSession` per child from
   the shared `session_maker`, fast-cancel checks before/after the semaphore + a `CancelledError` branch.
   Concurrency cap = `Settings.model_selection_global_max_parallel` (default 4; setting it to 1 ⇒ sequential
   = Option C). Do NOT import the batch runner (cross-slice rule) — mirror it. (Follow-up issue: promote the
   shared runner to `app/shared/` so batch + model_selection dedupe — out of scope for B.)
5. **Honest cooperative cancellation + drain.** `DELETE /{selection_id}`: 404 if missing, 409 if already
   terminal, else set the `CancelHandle.cancel_event` + `task.cancel()` each child, `await_drain` up to
   `Settings.model_selection_cancel_drain_timeout_seconds` (default 30) → 200 settled or **504** on timeout.
   sklearn/LightGBM fits are uncancellable mid-call — an in-flight candidate may COMPLETE before observing
   cancel; that is acceptable and must be surfaced honestly (the candidate ends `completed`, not `cancelled`).
   The invariant: **no candidate row left in `running` after settle**. (See `asyncio-taskgroup-cancellation.md`
   § "sklearn / LightGBM ignore CancelledError mid-fit".)
6. **`cancelled` is an ADDITIVE status** (not a redefinition). Add `CANCELLED = "cancelled"` to
   `ModelSelectionStatus`, extend the `model_selection_run` status CheckConstraint, extend the response
   `SelectionStatusLiteral`, and (frontend) add `'cancelled'` to the Slice-A TS `SelectionStatus` union.
   The child status enum is `pending|running|completed|failed|cancelled`. Terminal-status rule at settle
   (mirror `batch/service.py:_settle`): all-cancelled-and-none-ran ⇒ `cancelled`; ≥1 completed & ≥1
   failed/cancelled ⇒ `partial`; all completed ⇒ `completed`; all failed (and none completed) ⇒ `failed`.
7. **Ranking/chart/business computed ONCE at settle, reusing existing pure logic.** When all children are
   terminal, the worker loads each child's `result` JSONB → `list[CandidateResult]` (cancelled children →
   an excluded entry, mirroring `_shape_failed_candidate` with `error="cancelled"`), then calls the
   UNCHANGED `rank_candidates(...)`, `build_chart_data(...)`, `explain_winner(...)` and persists
   `ranking_result` / `chart_data` / `winner_*` / `business_summary` into the SAME JSONB columns the sync
   path uses — so the terminal GET response is byte-compatible with today's `/run`.
8. **Slice B does NOT train, predict, override, or promote.** `auto_train_winner` / `auto_predict` on the
   request are treated as **no-ops** by the `/runs` worker (comparison + ranking only). The existing
   `POST /{id}/train-winner` + `POST /{id}/predict` endpoints stay as-is; Slice C wires the UI for them.
   Slice B's results UI may show the deterministic `business_summary` read-only but adds no new
   interpretation, no safety stock, no manual winner override.
   **Coordination (ownership of "Explain Winner"):** `business_summary` is computed ONCE by the backend
   (`explanations.explain_winner`, unchanged). Slice B's winner-card renders it read-only (headline /
   confidence / reasons / `BIAS_EXPLANATION`); Slice C's business-interpretation-panel renders the SAME
   `business_summary` read-only and ADDS only the decision-layer fields (bias-risk text + labeled safety
   stock from `decision.py`). Neither slice re-derives explanation text or duplicates the other's panel.
9. **WAPE stays the default ranking metric; tie-break WAPE → sMAPE → |bias| → MAE is unchanged** (it lives
   in `ranking.py:96` `_sort_key` — Slice B does not touch ranking math). Bias copy wherever surfaced:
   *"Positive bias means the model under-forecasts (risk of stockouts); negative bias means it over-forecasts
   (risk of overstock)."* — reuse the Slice-A `BIAS_EXPLANATION` constant (`components/champion-selector/copy.ts`).

### Success Criteria

- [ ] `POST /model-selection/runs` returns 202 + `Location`/`Retry-After` headers + a `running` body
      BEFORE any candidate finishes (assert via a slow/mocked backtest in a unit test).
- [ ] Detached worker uses `get_session_maker()` sessions, never the request `db`; a held task reference
      prevents GC; the run completes after the response returned.
- [ ] `model_selection_candidate` rows track per-candidate `pending→running→{completed,failed,cancelled}`;
      `result` JSONB carries the full `CandidateResult`; failed/cancelled candidates remain visible.
- [ ] `GET /{selection_id}` returns live `progress` (GROUP BY children) + `candidate_progress` while running,
      and the existing `ranking`/`winner`/`chart_data`/`business_summary` once terminal.
- [ ] `DELETE /{selection_id}`: 404/409/200/504 per LOCKED #5; no candidate left `running` after a clean drain.
- [ ] Concurrency is capped by the Semaphore; one `AsyncSession` per candidate; `global_max_parallel=1`
      degrades to sequential without code change.
- [ ] `cancelled` added additively to ORM enum + CheckConstraint + response Literal + TS union; strict-mode
      policy test stays green (no new strict request model with date fields beyond the existing ones).
- [ ] Migration creates `model_selection_candidate` + adds `model_selection_run` columns + alters the status
      CheckConstraint; `downgrade` reverses cleanly on a fresh DB.
- [ ] `/visualize/champion` CTA → submit → live progress panel → ranking table + winner card + 4 charts +
      model detail drawer; partial/all-failed/cancelled states render clearly.
- [ ] Polling stops on terminal status (`refetchInterval` returns false); cancel button confirms via
      AlertDialog and invalidates the poll query.
- [ ] All backend Level-1..4 gates + frontend `pnpm tsc --noEmit && pnpm lint && pnpm test --run` pass.

## All Needed Context

### Documentation & References

```yaml
# Slice / contract source of truth
- file: PRPs/forecast-champion-selector-backend.md
  why: Merged backend foundation — LOCKED #1-#7, the /run + /{id} contract, availability semantics,
       the verified BacktestingService/ForecastingService signatures, strict-mode + migration gotchas.
       Slice B reuses this verbatim; do NOT re-derive ranking/availability.
- file: PRPs/forecast-champion-selector-slice-a-selection-capability.md
  why: FIXED upstream dependency. Slice A owns the page (pages/visualize/champion.tsx), the hook module
       (hooks/use-model-selection.ts), the types/api.ts "Model Selection" section (the full workflow
       contract is DECLARED there — Slice B implements the run/poll/cancel behavior, not the types), the
       champion-selector component family, and the disabled "Run comparison" CTA. Do NOT redefine these.
- docfile: PRPs/ai_docs/asyncio-taskgroup-cancellation.md
  why: THE async LRO reference for this repo — runtime-verified on Python 3.12.13. TaskGroup public surface
       (only create_task), per-task cancel + cooperative event, semaphore-wraps-work (not scheduling),
       one AsyncSession per child, ContextVar/request-id inheritance, SQLAlchemy pool bound
       (size 5 + overflow 10 ⇒ global cap ≤ 12 safe), and the sklearn/LightGBM-uncancellable caveat.
       Cite its verification commands in Known Gotchas.
- file: PRPs/templates/prp_base.md
  why: Base PRP template. NOTE — "PRPs/prp-readme.md.md" does NOT exist (`find PRPs -iname '*readme*'`
       empty on 2026-06-01); both prior champion PRPs record the same finding.

# Backend async precedent to MIRROR (the batch slice — same runtime, merged, proven)
- file: app/features/batch/runner.py
  why: THE runner to mirror slice-locally. run_batch(:74) TaskGroup(:187) + Semaphore(:115) +
       _ACTIVE_BATCHES registry(:71) + CancelHandle(:47, cancel_event/completed_event/tasks); _child(:126)
       fast-cancel before(:135)/after(:151) acquire + CancelledError branch(:157,179); cancel_batch(:208),
       await_drain(:236), mark_completed(:270); _mark_cancelled_skipped(:305)/_mark_cancelled_running(:322)/
       _mark_failed_unexpected(:353). Slice B reproduces this shape with a model_selection registry.
- file: app/features/batch/service.py
  why: submit() lifecycle (:88) — insert parent+children+commit(:137), parent→running(:148), get_session_maker
       (:159), per-child _exec_one opens OWN session(:168), runner.run_batch(:178), finally settle(:191) +
       mark_completed(:195). CRITICAL DIVERGENCE: batch AWAITS run_batch inline (:178); Slice B detaches it
       via asyncio.create_task so POST returns 202 first (LOCKED #2). _settle(:387) terminal-status rule + counts.
- file: app/features/batch/routes.py
  why: POST returns 202 (:37); DELETE cancel contract (:75) — 200 drained / 404 / 409 terminal / 504 drain
       timeout, with the cooperative-drain description (:79-88) to reuse near-verbatim. Mirror error mapping.
- file: app/features/batch/models.py
  why: Child-table shape to mirror — BatchJobItem (status String + CheckConstraint, JSONB metrics,
       error_message/error_type, started_at/completed_at/duration_ms, indexes). BatchStatus/BatchItemStatus
       enums incl. `cancelled`. TimestampMixin first.
- file: alembic/versions/c1d2e3f40512_create_batch_tables.py
  why: Migration template — postgresql.JSONB(astext_type=sa.Text()); named CheckConstraint; op.create_index
       (op.f for single-col unique, explicit name for composite); FK with ondelete="CASCADE"; downgrade drops
       indexes THEN table. Slice B's migration ALSO alters an existing CheckConstraint (drop+create).
- file: app/core/database.py
  why: get_session_maker() (:33) → async_sessionmaker(expire_on_commit=False) — the OUT-OF-REQUEST session
       factory the detached worker + each child MUST use. get_engine() (:22). get_db (request-scoped) dep.
- file: app/core/config.py
  why: Settings(BaseSettings); batch_global_max_parallel=4 (:131), batch_cancel_drain_timeout_seconds=30
       (:135) — MIRROR with model_selection_global_max_parallel + model_selection_cancel_drain_timeout_seconds
       (typed attr + literal default; env var = UPPER_SNAKE; add to .env.example + a config test).

# Live model_selection slice (the contract Slice B extends — verified 2026-06-01)
- file: app/features/model_selection/service.py
  why: run_selection (:211) is the SYNC body whose internals (per-candidate backtest :279, _shape_candidate
       :468, rank_candidates :308, build_chart_data :370, explain_winner :316/:371, _response :526) Slice B
       REUSES inside the async worker + settle. get_selection(:395)/_load(:513)/_response(:526) extend with
       progress. Lazy cross-slice imports inside methods (:215-219).
- file: app/features/model_selection/models.py
  why: ModelSelectionRun + ModelSelectionStatus (:26). ADD CANCELLED enum value; ADD started_at + count
       columns; ALTER status CheckConstraint (:82) to include 'cancelled'. ADD the new ModelSelectionCandidate ORM.
- file: app/features/model_selection/schemas.py
  why: ModelSelectionRunRequest (:118, REUSE as the /runs body), ModelSelectionRunResponse (:267, ADD
       additive progress fields), SelectionStatusLiteral (:49, ADD 'cancelled'), CandidateResult (:178)/
       FoldChart (:169) (persisted per-child), ChartData (:225)/ModelRankEntry (:195)/WinnerSummary (:216)
       (unchanged). ADD SubmitRunResponse (202 superset), CandidateProgress, SelectionProgress.
- file: app/features/model_selection/routes.py
  why: APIRouter(prefix="/model-selection") (:38); error mapping ValueError→BadRequestError,
       SQLAlchemyError→DatabaseError. ADD POST /runs (202) + DELETE /{selection_id}; extend GET /{id}.
- file: app/features/model_selection/ranking.py
  why: rank_candidates(:116)/build_chart_data(:250) — REUSE UNCHANGED at settle. Do NOT touch ranking math.
- file: app/features/model_selection/tests/test_routes.py + test_routes_integration.py + conftest.py + test_service.py
  why: ASGITransport + AsyncClient + app.dependency_overrides[get_db]; integration fixture (real engine,
       prefix-scoped teardown in finally). MIRROR for the async route + drain integration tests.
- file: app/features/batch/tests/  (test_runner.py, test_routes_cancel.py, test_runner_chaos.py)
  why: Runner unit tests (fake session_maker, monkeypatched DB helpers, semaphore-cap + cancel-skip/running
       assertions) + the chaos integration test asserting "no row left running after cancel". MIRROR for
       app/features/model_selection/tests/test_runner.py + a cancel integration test.

# Frontend examples to MIRROR (verified 2026-06-01)
- file: frontend/src/pages/visualize/batch.tsx
  why: THE polling/progress page. refetchInterval returns 2000ms while pending|running else false (via
       use-batches.ts:44-54); TERMINAL check (:125-127); progress Card + StatusBadge + counts (:294-320);
       per-item Table (:361-411); AlertDialog cancel confirm (:324-351) — pending skip / running-at-safe-yield
       copy reusable. The champion results UI mirrors this density.
- file: frontend/src/hooks/use-batches.ts
  why: useBatch polling hook (:44-54, refetchInterval fn + enabled gate), useSubmitBatch (:13-25) +
       useCancelBatch (:30-40) useMutation + queryClient.setQueryData/invalidateQueries. MIRROR for
       useSubmitSelectionRun / useSelectionRun / useCancelSelectionRun in hooks/use-model-selection.ts.
- file: frontend/src/hooks/use-batches.test.ts
  why: Hook test harness — vi.stubGlobal('fetch',...), QueryClient wrapper (retry:false), renderHook +
       act + waitFor, afterEach(vi.unstubAllGlobals()). MIRROR for the new hooks.
- file: frontend/src/lib/status-utils.ts
  why: getStatusVariant(status) → success|info|pending|error|warning (covers completed/running/pending/
       failed/cancelled). Reuse for candidate + run status badges.
- file: frontend/src/components/common/status-badge.tsx
  why: StatusBadge variant component (cva). Reuse for run + per-candidate status.
- file: frontend/src/components/charts/backtest-folds-chart.tsx
  why: Bar chart of per-fold metrics — props {title, data: FoldMetric[] = {fold,mae,smape,wape,bias},
       metricKey, height}. ChartContainer + Recharts BarChart; height via inline style (Tailwind JIT drops
       dynamic h-[Npx]). Use for fold-stability (per-fold WAPE) of the winner/candidates.
- file: frontend/src/components/charts/multi-series-chart.tsx
  why: Multi-line chart — props {title, data: Record<string,number|string>[], series: {key,label}[],
       xAxisKey, height}. ComposedChart; first line solid, rest dashed. Use for winner actual-vs-predicted
       overlay (series: actual + predicted, x = date).
- file: frontend/src/components/charts/  (revenue-bar-chart, time-series-chart, kpi-card, backtest-horizon-buckets-chart)
  why: Reuse a simple Bar chart pattern for WAPE-by-model + bias-by-model (one bar per candidate). Mirror
       backtest-folds-chart's ChartContainer/ChartConfig + ResizeObserver test stub.
- file: frontend/src/components/ui/sheet.tsx
  why: Sheet primitive (side, SheetContent/Header/Title/Description) — the model-detail DRAWER (no existing
       drawer-usage precedent in pages; this is the first). Trigger on a ranking-row click.
- file: frontend/src/components/ui/alert-dialog.tsx
  why: AlertDialog — the cancel-run confirmation (mirror batch.tsx:324-351). Reuse the pending-skip/
       running-at-safe-yield copy.
- file: frontend/src/components/data-table/data-table.tsx  AND  frontend/src/pages/visualize/batch.tsx:366-411
  why: Two table options — TanStack DataTable (sortable/paginated, manualSorting) for the ranking table, OR
       a plain shadcn Table (batch.tsx) for a short candidate-progress list. Ranking ≤10 rows → plain Table
       is sufficient; use DataTable only if sortable columns are wanted.
- file: frontend/src/components/common/{loading-state,error-display}.tsx
  why: LoadingState / ErrorDisplay / EmptyState — partial/failed/empty states; getErrorMessage (lib/api.ts:94).
- file: frontend/src/lib/api.ts
  why: api<T>(endpoint,{method,body,params}) — POST/DELETE/GET; ApiError + getErrorMessage; 204 handling.
       NOTE: the 202 body is JSON (api<T> parses it); Location/Retry-After headers are not surfaced by api<T>
       — the frontend uses the body's monitor_url/cancel_url/selection_id, not the headers (LOCKED note).
- file: frontend/src/lib/constants.ts  +  frontend/src/App.tsx
  why: ROUTES.VISUALIZE.CHAMPION + NAV_ITEMS + lazy route are ADDED by Slice A. Slice B does NOT add a new
       route — it extends the existing champion page. (If Slice A is not yet merged at impl time, see
       "Dependency on Slice A" below.)
- file: frontend/src/types/api.ts
  why: Slice A adds the "// === Model Selection (Champion Selector) ===" section with the full workflow
       contract. Slice B ADDS (additively, same section): SubmitRunResponse, SelectionProgress,
       CandidateProgress, and 'cancelled' on the SelectionStatus union. Do NOT duplicate Slice A's types.
- file: frontend/vitest.config.ts
  why: jsdom; include src/**/*.test.{ts,tsx}; @→./src. Chart tests need a ResizeObserver beforeAll stub
       (see backtest-horizon-buckets-chart.test.tsx).

# External official docs (with reasoning)
- url: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/202
  why: 202 Accepted semantics — the response is a promise, not a result; include a status-monitor pointer.
       Justifies returning 202 + Location/Retry-After + a monitor_url body field for the running selection.
- url: https://learn.microsoft.com/en-us/rest/api/fabric/articles/long-running-operation
  why: Canonical async LRO contract — submit → 202 + Location + Retry-After → poll status → terminal. Shapes
       SubmitRunResponse (monitor_url/cancel_url) + the GET polling response.
- url: https://fastapi.tiangolo.com/tutorial/background-tasks/
  why: FastAPI BackgroundTasks runs AFTER the response but is NOT suited to heavy/long CPU-bound fits and
       offers no cancellation/progress — the brief forbids it for model fits. Justifies asyncio.create_task
       (detached) + the DB-backed runner instead.
- url: https://docs.python.org/3.12/library/asyncio-task.html#asyncio.create_task
  why: "Save a reference to the result of this function, to avoid a task disappearing mid-execution." The
       GC foot-gun for the detached worker (LOCKED #2) — hold the task ref (in the CancelHandle or a module set).
- url: https://docs.python.org/3.12/library/asyncio-task.html#asyncio.TaskGroup
  why: TaskGroup structured concurrency + except* ExceptionGroup — the runner's child fan-out + cancel absorb.
- url: https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html#using-multiple-asyncio-event-loops
  why: AsyncSession is NOT concurrency-safe to share across tasks — one session per concurrent candidate
       (the contract's explicit rule; matches batch _exec_one).
- url: https://docs.aws.amazon.com/forecast/latest/dg/metrics.html
  why: WAPE/MAPE/RMSE definitions — so the comparison-chart axis labels + tooltips describe each metric
       correctly (and the bias under/over-forecast copy stays accurate).
```

### Current Codebase Tree (relevant)

```bash
app/features/model_selection/        # MERGED backend (issue #353) — SYNC /run today
├── models.py        # ModelSelectionRun + ModelSelectionStatus  ← ADD CANCELLED, started_at, counts; ADD ModelSelectionCandidate
├── schemas.py       # request/response contract                 ← ADD SubmitRunResponse, SelectionProgress, CandidateProgress; +'cancelled'
├── service.py       # ModelSelectionService (sync run_selection) ← ADD submit_run + worker + settle + cancel; extend _response
├── ranking.py       # rank_candidates / build_chart_data        ← REUSE UNCHANGED
├── explanations.py  # explain_winner                            ← REUSE UNCHANGED
├── routes.py        # APIRouter(/model-selection)               ← ADD POST /runs (202), DELETE /{id}; extend GET /{id}
└── tests/           # conftest + unit + integration             ← ADD test_runner, test_async_routes, extend integration
app/features/batch/{runner,service,routes,models}.py  # the async LRO TEMPLATE to mirror (do NOT import)
app/core/{database,config}.py        # get_session_maker; Settings (mirror batch_* keys)
alembic/versions/                     # head observed 6c3f8d4-era; run `uv run alembic heads` at impl time
frontend/src/
├── pages/visualize/champion.tsx      # Slice A page                ← WIRE CTA → submit → poll → results
├── hooks/use-model-selection.ts      # Slice A catalog/availability ← ADD useSubmitSelectionRun/useSelectionRun/useCancelSelectionRun
├── types/api.ts                      # Slice A Model Selection sect ← ADD progress/submit types additively
├── components/champion-selector/     # Slice A selection components ← ADD results/ subfamily
├── components/charts/{backtest-folds-chart,multi-series-chart}.tsx
├── components/ui/{sheet,alert-dialog,table,card,badge,progress}.tsx
└── components/common/{status-badge,loading-state,error-display}.tsx
```

### Desired Codebase Tree (Slice B additions)

```bash
# Backend
app/features/model_selection/runner.py                        # NEW: slice-local TaskGroup+Semaphore runner (mirror batch/runner.py)
app/features/model_selection/models.py                        # MOD: + ModelSelectionCandidate; +CANCELLED; +started_at/counts; alter CheckConstraint
app/features/model_selection/schemas.py                       # MOD: + SubmitRunResponse, SelectionProgress, CandidateProgress; +'cancelled' literal
app/features/model_selection/service.py                       # MOD: + submit_run / _run_in_background / _execute_candidate / _settle / cancel_run; extend _response/get_selection
app/features/model_selection/routes.py                        # MOD: + POST /runs (202), + DELETE /{id}; extend GET /{id}
app/core/config.py                                            # MOD: + model_selection_global_max_parallel, model_selection_cancel_drain_timeout_seconds
.env.example                                                  # MOD: + the two new env vars (UPPER_SNAKE + comment)
alembic/versions/<rev>_add_model_selection_candidate_and_progress.py   # NEW migration
app/features/model_selection/tests/test_runner.py            # NEW: runner unit (semaphore cap, cancel skip/running)
app/features/model_selection/tests/test_async_routes.py      # NEW: 202 immediacy, progress GET, DELETE 404/409/200/504
app/features/model_selection/tests/test_models.py            # MOD: + ModelSelectionCandidate constraints
app/features/model_selection/tests/test_schemas.py           # MOD: + progress/submit schema cases
app/features/model_selection/tests/test_service.py           # MOD: + worker/settle/cancel unit (mock backtest)
app/features/model_selection/tests/test_routes_integration.py# MOD: + async run + cancel-drain integration (no row left running)
app/core/tests/test_config.py                                # MOD: + the two new settings defaults (Settings(_env_file=None))

# Frontend (extends Slice A — no new route)
frontend/src/types/api.ts                                    # MOD: + SubmitRunResponse, SelectionProgress, CandidateProgress; +'cancelled'
frontend/src/hooks/use-model-selection.ts                    # MOD: + useSubmitSelectionRun, useSelectionRun (poll), useCancelSelectionRun
frontend/src/hooks/use-model-selection.test.ts               # MOD: + submit/poll/cancel hook tests
frontend/src/pages/visualize/champion.tsx                    # MOD: CTA enabled → submit → poll → results section
frontend/src/components/champion-selector/results/run-progress-panel.tsx        # NEW (+ .test.tsx)
frontend/src/components/champion-selector/results/ranking-table.tsx             # NEW (+ .test.tsx)
frontend/src/components/champion-selector/results/winner-card.tsx               # NEW (+ .test.tsx)
frontend/src/components/champion-selector/results/comparison-charts.tsx         # NEW (+ .test.tsx)  (WAPE/bias bars + fold-stability + actual-vs-predicted)
frontend/src/components/champion-selector/results/model-detail-drawer.tsx       # NEW (+ .test.tsx)  (Sheet)
frontend/src/components/champion-selector/results/cancel-run-dialog.tsx         # NEW (+ .test.tsx)  (AlertDialog)
```

### Known Gotchas & VERIFIED Contracts

```python
# ── FIRE-AND-FORGET vs BATCH'S AWAIT-INLINE (the core divergence — LOCKED #2) ──
# batch/service.py:178 does `await runner.run_batch(...)` INSIDE the POST handler, so batch's POST blocks
# to completion and returns the SETTLED parent (batch/routes.py:52). That is a 202-shaped SYNC call —
# unusable for Slice B's poll/progress/Retry-After brief. Slice B MUST detach:
#   task = asyncio.create_task(self._run_in_background(selection_id, request_snapshot))
#   _BACKGROUND_TASKS.add(task); task.add_done_callback(_BACKGROUND_TASKS.discard)   # hold a ref!
#   return SubmitRunResponse(...)   # 202 immediately
# GC FOOT-GUN: asyncio only keeps a WEAK ref to the task; without a strong ref it can be GC'd mid-run
#   (https://docs.python.org/3.12/library/asyncio-task.html#asyncio.create_task). Hold it in a module-level
#   set (and/or the CancelHandle.tasks). The CancelHandle in _ACTIVE_SELECTIONS also keeps the runner's
#   child task refs (mirror batch CancelHandle.tasks).

# ── THE DETACHED WORKER MUST NOT USE THE REQUEST SESSION ───────────────────────
# Depends(get_db) closes when the POST handler returns. The detached worker outlives the request, so EVERY
# DB touch in _run_in_background / _execute_candidate / _settle opens its OWN session from get_session_maker()
# (app/core/database.py:33), exactly like batch _exec_one (batch/service.py:168). Sharing the request db = a
# closed-session error (or worse, a use-after-free of the connection). One AsyncSession per concurrent child.

# ── NO SHARED-ROW WRITE RACE — child rows, atomic where needed ─────────────────
# Concurrent candidate tasks write their OWN model_selection_candidate rows (per LOCKED #3). NEVER have two
# tasks read-modify-write the same parent JSONB (Option B's bug). Live progress on GET = a GROUP BY status
# over children (race-free). If you cache live counts on the parent, use atomic SQL `col = col + 1` UPDATEs
# (mirror batch _bump_running) — but the SIMPLER, recommended path is: derive counts on read, write FINAL
# counts only once at settle. Prefer the latter (no live parent writes at all from children).

# ── COOPERATIVE + HONEST CANCEL (LOCKED #5) ───────────────────────────────────
# Mirror batch/runner.py exactly: fast-cancel check BEFORE sem acquire (skip) + AFTER acquire (skip) +
# `except asyncio.CancelledError: mark child cancelled_running; raise`. cancel_run() sets cancel_event +
# task.cancel() per child. await_drain waits CancelHandle.completed_event up to the drain timeout → 504.
# mark_completed() pops the registry AFTER settle commits (never before — else DELETE's drain races settle).
# sklearn/LightGBM fits are sync C — uncancellable mid-call: an in-flight candidate may COMPLETE (status
# completed, not cancelled). That is correct/honest. Invariant: NO candidate left `running` after settle
# (assert in the chaos integration test, mirror batch/tests/test_runner_chaos.py).

# ── TaskGroup absorbs CancelledError; the runner returns normally ──────────────
# `async with asyncio.TaskGroup() as tg:` ... `except* asyncio.CancelledError: pass` — cancellation does NOT
# propagate out of run_selection_candidates; the worker proceeds to settle the parent to its observed state
# (mirror batch/runner.py:186-205). Verified TaskGroup surface: only `create_task`
# (PRPs/ai_docs/asyncio-taskgroup-cancellation.md:13-16). Re-verify on upgrade:
#   uv run python -c "import asyncio; print([m for m in dir(asyncio.TaskGroup) if not m.startswith('_')])"  # ['create_task']

# ── CONCURRENCY CAP / POOL BOUND ──────────────────────────────────────────────
# effective = min(req.split-derived cap?, Settings.model_selection_global_max_parallel). There is NO per-run
# max_parallel field on ModelSelectionRunRequest (Slice A did not add one) — use the GLOBAL setting as the
# cap (a future PRP may add a per-run field). SQLAlchemy pool default size 5 + overflow 10 ⇒ keep the global
# cap ≤ 12 (asyncio-taskgroup-cancellation.md:170-191). Default 4 is safe. Verify pool:
#   uv run python -c "from sqlalchemy.ext.asyncio import create_async_engine; e=create_async_engine('postgresql+asyncpg://x:x@h:5433/x'); print(e.pool.size(), e.pool._max_overflow)"  # 5 10

# ── ADDITIVE 'cancelled' STATUS (LOCKED #6) ───────────────────────────────────
# Add CANCELLED='cancelled' to ModelSelectionStatus; the migration must DROP+CREATE the named CheckConstraint
# ck_model_selection_run_valid_status to include 'cancelled' (forward-only). Extend SelectionStatusLiteral
# (schemas.py:49) and the TS SelectionStatus union. The child status enum literal is
# pending|running|completed|failed|cancelled with its own CheckConstraint on model_selection_candidate.

# ── REUSE THE PURE LOGIC AT SETTLE (LOCKED #7) ────────────────────────────────
# Do NOT rewrite ranking/chart/business. At settle: load children, build list[CandidateResult]
#   (success child → CandidateResult.model_validate(child.result); cancelled child → an excluded result with
#    failed=True, error="cancelled"; failed child → failed=True, error=child.error_message), then call the
# UNCHANGED rank_candidates(results, policy, ranking_metric, availability.status), build_chart_data(results,
# ranking), explain_winner(ranking, availability). Persist into the SAME JSONB columns the sync path writes
# so terminal GET output is byte-compatible (service.py:307-389 is the reference for which columns).

# ── ROUTE ORDERING / METHOD COLLISION ─────────────────────────────────────────
# POST /runs (literal) vs GET/DELETE /{selection_id} (path-param) are different METHODS — no Starlette
# collision. Still, declare literal routes before path-param routes for consistency (mirror /availability
# before /{selection_id}). DELETE /{selection_id} is a NEW method on the existing path-param.

# ── STRICT-MODE POLICY (unchanged) ────────────────────────────────────────────
# No NEW strict request model with date fields is added (the /runs body is the EXISTING
# ModelSelectionRunRequest). SubmitRunResponse/SelectionProgress/CandidateProgress are RESPONSE models
# (plain BaseModel — no strict). app/core/tests/test_strict_mode_policy.py stays green.

# ── VERIFIED INTERNAL SIGNATURES (from the merged backend, do NOT re-derive) ──
# BacktestingService().run_backtest(db, store_id, product_id, start_date, end_date, BacktestConfig(...))
#   -> BacktestResponse  (service.py:279 call site; LOCKED #4 in backend PRP: include_baselines=False,
#   store_fold_details=True). _shape_candidate(candidate, backtest) -> CandidateResult (service.py:468).
# TypeAdapter(ModelConfig).validate_python({"model_type": c.model_type, **c.params}) — FLATTEN params
#   (service.py:276). lightgbm/xgboost may ImportError → that candidate becomes failed (caught per-candidate).
```

```typescript
// ── FRONTEND ────────────────────────────────────────────────────────────────
// POLLING: useSelectionRun(selectionId) mirrors useBatch (use-batches.ts:44-54):
//   refetchInterval: (q) => { const s = q.state.data?.status; return s==='running'||s==='pending' ? 2000 : false }
//   enabled: !!selectionId. A TERMINAL_SELECTION_STATES set = {completed,failed,partial,cancelled}.
// SUBMIT: useSubmitSelectionRun -> api<SubmitRunResponse>('/model-selection/runs',{method:'POST',body:req}).
//   onSuccess: setQueryData(['model-selection','run', data.selection_id], data) so polling starts warm.
// CANCEL: useCancelSelectionRun -> api(`/model-selection/${id}`,{method:'DELETE'}); onSuccess invalidate the
//   run query. Confirm via AlertDialog (mirror batch.tsx:324-351) — reuse the pending-skip/running-yield copy.
// api<T> (lib/api.ts) parses the JSON body but does NOT expose Location/Retry-After headers — drive the UI
//   from the body's selection_id/monitor_url/cancel_url, NOT the headers.
// selection_id is BACKEND-generated — never crypto.randomUUID() client-side (memory:
//   showcase-crypto-randomuuid-lan-crash — undefined over LAN HTTP). Dogfood over http://localhost:5173.
// CHARTS need a ResizeObserver beforeAll stub in jsdom (backtest-horizon-buckets-chart.test.tsx pattern);
//   pass height via inline style (Tailwind JIT drops dynamic h-[Npx]).
// react-refresh/only-export-components: keep non-component constants (TERMINAL_SELECTION_STATES) in a .ts
//   file (reuse Slice A's copy.ts or a results/constants.ts), not exported from a .tsx component.
// Mixed CRLF/LF repo-wide (memory: repo-line-endings-crlf) — `git diff --stat` before committing; new files LF.
// IDs are NOT 1-based (memory: seeder-does-not-reset-id-sequences) — never hardcode store_id=1/product_id=1.
```

## Implementation Blueprint

### Backend data models

`app/features/model_selection/models.py` — additions:

```python
# ModelSelectionStatus: ADD  CANCELLED = "cancelled"
# ModelSelectionRun: ADD
#   started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
#   total_candidates / completed_candidates / failed_candidates / cancelled_candidates: Mapped[int]
#     = mapped_column(Integer, default=0, server_default="0")   # FINAL counts cached at settle
#   ALTER __table_args__ CheckConstraint to: status IN ('pending','running','completed','partial','failed','cancelled')

class CandidateStatus(str, Enum):
    PENDING = "pending"; RUNNING = "running"; COMPLETED = "completed"
    FAILED = "failed"; CANCELLED = "cancelled"

class ModelSelectionCandidate(TimestampMixin, Base):
    __tablename__ = "model_selection_candidate"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    selection_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("model_selection_run.selection_id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)          # submit order, stable display
    model_type: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default=CandidateStatus.PENDING.value, index=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)   # full CandidateResult on success
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (
        CheckConstraint("status IN ('pending','running','completed','failed','cancelled')",
                        name="ck_model_selection_candidate_valid_status"),
        Index("ix_model_selection_candidate_selection_status", "selection_id", "status"),
    )
```

`app/features/model_selection/schemas.py` — additive response models (plain BaseModel):

```python
class CandidateProgress(BaseModel):
    candidate_id: str; ordinal: int; model_type: str
    status: Literal["pending","running","completed","failed","cancelled"]
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None

class SelectionProgress(BaseModel):
    total: int; pending: int; running: int; completed: int; failed: int; cancelled: int

# ADD 'cancelled' to SelectionStatusLiteral (line 49).
# EXTEND ModelSelectionRunResponse additively:
#   started_at: datetime | None
#   progress: SelectionProgress | None
#   candidate_progress: list[CandidateProgress]   (default_factory=list)

class SubmitRunResponse(ModelSelectionRunResponse):  # 202 superset
    monitor_url: str
    cancel_url: str
```

### Backend runner (`app/features/model_selection/runner.py`)

```python
# MIRROR app/features/batch/runner.py 1:1, renaming batch→selection:
#   _ACTIVE_SELECTIONS: dict[str, CancelHandle]
#   @dataclass CancelHandle(cancel_event, completed_event, tasks)
#   async def run_selection_candidates(*, selection_id, candidate_ids, max_parallel, global_max_parallel,
#                                      session_maker, execute_candidate) -> int
#     effective = min(max_parallel, global_max_parallel); sem = Semaphore(effective)
#     handle = _ACTIVE_SELECTIONS.setdefault(selection_id, CancelHandle())
#     async def _child(cid):
#         async with session_maker() as session:
#             if handle.cancel_event.is_set(): await _mark_cancelled_skipped(session, cid); return
#             acquired=False
#             try:
#                 async with sem:
#                     acquired=True
#                     if handle.cancel_event.is_set(): await _mark_cancelled_skipped(session, cid); return
#                     try: await execute_candidate(cid)
#                     except asyncio.CancelledError: await _mark_cancelled_running(session, cid); raise
#                     except Exception: await _mark_failed_unexpected(session, cid)   # do NOT re-raise (don't kill siblings)
#             except asyncio.CancelledError:
#                 if not acquired: await _mark_cancelled_skipped(session, cid)
#                 raise
#     try:
#         async with asyncio.TaskGroup() as tg:
#             for cid in candidate_ids:
#                 handle.tasks.append(tg.create_task(_child(cid), name=f"model_selection:{selection_id}:{cid}"))
#     except* asyncio.CancelledError: pass
#     return effective
#   def cancel_selection(selection_id) -> bool   # set cancel_event + task.cancel() each; False if not registered
#   async def await_drain(selection_id, timeout_seconds) -> bool   # wait completed_event; mirror batch
#   def mark_completed(selection_id) -> None      # set completed_event + pop registry (AFTER settle)
#   helpers _mark_cancelled_skipped/_mark_cancelled_running/_mark_failed_unexpected — UPDATE the candidate row
#     status + completed_at + duration_ms in the child's own session (mirror batch helpers).
# The runner does NOT bump parent counters (counts derived on read; final counts at settle).
```

### Backend service (`app/features/model_selection/service.py`)

```python
# ADD (sync run_selection stays for legacy POST /run):
async def submit_run(self, db, request) -> SubmitRunResponse:
    # 1) availability gate (REUSE get_availability). If unusable → persist failed row, raise BadRequestError (LOCKED #2 parity).
    # 2) insert parent (status=running, started_at=now, total_candidates=N, snapshots) + N ModelSelectionCandidate
    #    rows (status=pending, ordinal=i) using REQUEST db; await db.commit().
    # 3) snapshot the request into a plain dict / re-validated request (the worker must NOT close over the
    #    request session). Launch detached:
    #        task = asyncio.create_task(self._run_in_background(selection_id))
    #        _BACKGROUND_TASKS.add(task); task.add_done_callback(_BACKGROUND_TASKS.discard)
    # 4) re-read the parent (or build from known fields) and return SubmitRunResponse(..., status="running",
    #    monitor_url=f"/model-selection/{sid}", cancel_url=f"/model-selection/{sid}", progress=all-pending).

async def _run_in_background(self, selection_id) -> None:
    session_maker = get_session_maker()
    # load parent + children + the persisted request snapshot via a fresh session.
    async def _exec(cid):
        async with session_maker() as s:
            cand = await s.scalar(select(ModelSelectionCandidate).where(...candidate_id==cid))
            cand.status = RUNNING; cand.started_at = now; await s.commit()
            try:
                cfg = TypeAdapter(ModelConfig).validate_python({"model_type": cand.model_type, **cand.params})  # lazy import
                bt = await BacktestingService().run_backtest(s, store_id, product_id, start, end,
                         BacktestConfig(split_config=..., model_config_main=cfg, include_baselines=False, store_fold_details=True))
                result = self._shape_candidate(CandidateModelConfig(model_type=cand.model_type, params=cand.params), bt)
                cand.result = result.model_dump(mode="json"); cand.status = COMPLETED
            except Exception as exc:
                cand.status = FAILED; cand.error_message = str(exc)[:2000]; cand.error_type = type(exc).__name__
            cand.completed_at = now; cand.duration_ms = ...; await s.commit()
    try:
        await runner.run_selection_candidates(selection_id=selection_id, candidate_ids=[...],
            max_parallel=self.settings.model_selection_global_max_parallel,
            global_max_parallel=self.settings.model_selection_global_max_parallel,
            session_maker=session_maker, execute_candidate=_exec)
    finally:
        await self._settle(selection_id, session_maker)     # ranking/chart/business + terminal status + counts
        runner.mark_completed(selection_id)

async def _settle(self, selection_id, session_maker) -> None:
    async with session_maker() as s:
        # load parent + all children; build list[CandidateResult] (LOCKED #7 mapping);
        # availability = PairAvailabilityResponse.model_validate(parent.availability_snapshot)
        # ranking = rank_candidates(results, policy_from_snapshot, parent.ranking_metric, availability.status)
        # if ranking.winner: chart = build_chart_data(results, ranking); winner_* set
        # business = explain_winner(ranking, availability)
        # counts from children; terminal status per LOCKED #6 rule; completed_at=now; commit.

async def cancel_run(self, db, selection_id) -> ModelSelectionRunResponse:
    # load parent (404). If status terminal → ConflictError (409). 
    # fired = runner.cancel_selection(selection_id); if not fired → ConflictError (race: settled). 
    # drained = await runner.await_drain(selection_id, self.settings.model_selection_cancel_drain_timeout_seconds)
    # if not drained → GatewayTimeoutError (504). reload + return _response.

# EXTEND get_selection/_response to attach progress:
#   progress = SelectionProgress(**counts_from_groupby_or_cached); candidate_progress = [CandidateProgress(...) per child]
#   (a run created by the legacy sync /run has NO children → progress=None, candidate_progress=[]).
```

`app/core/exceptions.py` already provides `ConflictError` (409, :130) and `GatewayTimeoutError` (504, :203);
`batch/routes.py:18` imports both for its DELETE drain. Reuse those exact classes — no new exception needed.

### Backend routes (`app/features/model_selection/routes.py`)

```python
@router.post("/runs", response_model=SubmitRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_run(request: ModelSelectionRunRequest, response: Response, db = Depends(get_db)):
    service = ModelSelectionService()
    try:
        result = await service.submit_run(db, request)
        response.headers["Location"] = result.monitor_url
        response.headers["Retry-After"] = "2"
        return result
    except ValueError as exc: raise BadRequestError(message=str(exc)) from exc
    except SQLAlchemyError as exc: raise DatabaseError(message="Failed to submit selection run", details={"error": str(exc)}) from exc

@router.delete("/{selection_id}", response_model=ModelSelectionRunResponse, status_code=200,
               description="Cooperative cancel + drain. 200 settled / 404 missing / 409 terminal / 504 drain timeout.")
async def cancel_run(selection_id: str, db = Depends(get_db)):
    service = ModelSelectionService()
    try: return await service.cancel_run(db, selection_id)
    except SQLAlchemyError as exc: raise DatabaseError(message="Failed to cancel selection run", details={"error": str(exc)}) from exc
    # NotFoundError(404)/ConflictError(409)/GatewayTimeoutError(504) raised in-service bubble to the global handler.
# GET /{selection_id} unchanged signature — service now attaches progress.
```

### Implementation Tasks (dependency-ordered)

```yaml
# ───────────────────────── BACKEND ─────────────────────────
Task 1 — Config:
  MODIFY app/core/config.py: ADD model_selection_global_max_parallel: int = 4 ;
    model_selection_cancel_drain_timeout_seconds: int = 30  (mirror batch_* placement/typing).
  MODIFY .env.example: ADD MODEL_SELECTION_GLOBAL_MAX_PARALLEL / MODEL_SELECTION_CANCEL_DRAIN_TIMEOUT_SECONDS (+comments).
  MODIFY app/core/tests/test_config.py: assert the two defaults via Settings(_env_file=None).

Task 2 — ORM + migration:
  MODIFY app/features/model_selection/models.py: +CANCELLED enum; +started_at/count columns on ModelSelectionRun;
    ALTER status CheckConstraint to include 'cancelled'; +ModelSelectionCandidate + CandidateStatus (blueprint).
  RUN: uv run alembic heads   # chain down_revision to the LIVE head
  CREATE alembic/versions/<rev>_add_model_selection_candidate_and_progress.py:
    - create_table model_selection_candidate (mirror c1d2e3f40512 JSONB/index/FK ondelete=CASCADE style)
    - add_column started_at + the four count columns to model_selection_run (server_default "0" / NULL)
    - DROP+CREATE ck_model_selection_run_valid_status to include 'cancelled'
    - downgrade(): reverse (recreate old constraint, drop columns, drop indexes+table)
  MODIFY tests/test_models.py: candidate constraint + CRUD; run status accepts 'cancelled'.

Task 3 — Schemas:
  MODIFY app/features/model_selection/schemas.py: +'cancelled' on SelectionStatusLiteral; +CandidateProgress,
    SelectionProgress; EXTEND ModelSelectionRunResponse (started_at/progress/candidate_progress, all additive
    with safe defaults); +SubmitRunResponse(ModelSelectionRunResponse){monitor_url, cancel_url}.
  MODIFY tests/test_schemas.py: progress/submit models validate; existing-response back-compat (defaults).

Task 4 — Runner (pure-ish concurrency module):
  CREATE app/features/model_selection/runner.py: MIRROR batch/runner.py (registry, CancelHandle,
    run_selection_candidates, cancel_selection, await_drain, mark_completed, the 3 mark_* helpers).
  CREATE tests/test_runner.py: MIRROR batch/tests/test_runner.py — semaphore caps concurrency (peak==effective),
    cancel-before-start → skipped, cancel-mid-flight → cancelled_running; fake session_maker + monkeypatched
    DB helpers (NO real DB; not @integration).

Task 5 — Service:
  MODIFY app/features/model_selection/service.py: ADD submit_run, _run_in_background, _execute_candidate (inline
    _exec), _settle, cancel_run; module-level _BACKGROUND_TASKS set; EXTEND get_selection/_response with progress.
    REUSE _shape_candidate/rank_candidates/build_chart_data/explain_winner UNCHANGED. Lazy import services + runner.
  MODIFY tests/test_service.py: mock BacktestingService (patch the lazy target); assert submit_run returns
    running+children pending; worker settles completed/partial/failed; cancel mapping; all reuse the pure logic.

Task 6 — Routes:
  MODIFY app/features/model_selection/routes.py: ADD POST /runs (202 + Location/Retry-After) + DELETE /{id}
    (404/409/200/504); GET /{id} now carries progress (no signature change). Mirror error mapping.
  CREATE tests/test_async_routes.py: 202 immediacy (mock backtest to block; assert response returns first +
    status 'running' + Location header + body monitor_url/cancel_url); GET shows progress; DELETE 404/409/200.

Task 7 — Integration:
  MODIFY tests/test_routes_integration.py (@pytest.mark.integration, real engine, prefix-scoped teardown):
    - submit /runs → poll GET until terminal → ranking/winner present; failed candidate stays visible.
    - cancel mid-flight → no model_selection_candidate left status='running' after drain (mirror
      batch/tests/test_runner_chaos.py); 504 path optional (hard to force deterministically — document, may skip).

# ───────────────────────── FRONTEND (extends Slice A) ─────────────────────────
Task 8 — Types:
  MODIFY frontend/src/types/api.ts (Model Selection section): +SubmitRunResponse, SelectionProgress,
    CandidateProgress; +'cancelled' on the SelectionStatus union; ADD TERMINAL_SELECTION_STATES set in a .ts
    (results/constants.ts) NOT a component file. Do NOT redefine Slice A's types.

Task 9 — Hooks:
  MODIFY frontend/src/hooks/use-model-selection.ts: +useSubmitSelectionRun (POST /runs, seed query cache on
    success), +useSelectionRun(selectionId) (poll, refetchInterval false on terminal, enabled gate),
    +useCancelSelectionRun (DELETE, invalidate run query). MIRROR use-batches.ts.
  MODIFY hooks/use-model-selection.test.ts: submit posts to /model-selection/runs; poll stops on terminal;
    cancel DELETEs /model-selection/{id}; query disabled without id (fetch not called). MIRROR use-batches.test.ts.

Task 10 — Results components (under components/champion-selector/results/):
  CREATE run-progress-panel.tsx (+test): StatusBadge + counts + per-candidate Table (mirror batch.tsx:294-411).
  CREATE ranking-table.tsx (+test): rows from response.ranking (ModelRankEntry); winner highlighted; excluded
    rows show exclusion_reason; row click → onSelectModel (opens drawer). Plain shadcn Table (≤10 rows).
  CREATE winner-card.tsx (+test): winner model_type + metrics + recommendation_confidence + confidence_reasons
    + BIAS_EXPLANATION (Slice A copy.ts). Null-safe when no winner (failed/cancelled run).
  CREATE comparison-charts.tsx (+test): WAPE-by-model + bias-by-model bar charts (from chart_data), fold-stability
    (backtest-folds-chart style, per-fold WAPE), winner actual-vs-predicted (multi-series-chart: actual+predicted
    by date from chart_data.winner_actual_vs_predicted). ResizeObserver beforeAll stub in tests.
  CREATE model-detail-drawer.tsx (+test): Sheet showing one candidate's metrics + per-fold table + error/exclusion.
  CREATE cancel-run-dialog.tsx (+test): AlertDialog (mirror batch.tsx:324-351); confirm → useCancelSelectionRun.

Task 11 — Page wiring:
  MODIFY frontend/src/pages/visualize/champion.tsx: ENABLE the "Run comparison" CTA (gated on form validity);
    onClick → useSubmitSelectionRun(request); on submit store selection_id; render RunProgressPanel while
    running (useSelectionRun polling) + CancelRunDialog; on terminal render WinnerCard + RankingTable +
    ComparisonCharts + ModelDetailDrawer; partial/all-failed/cancelled → EmptyState/ErrorDisplay with failed
    candidates still listed. Do NOT add train/predict/promote UI (Slice C).
```

### Integration Points

```yaml
DATABASE:
  - migration: + model_selection_candidate (FK CASCADE to model_selection_run.selection_id); + started_at +
    {total,completed,failed,cancelled}_candidates on model_selection_run; alter status CheckConstraint (+cancelled).
CONFIG:
  - app/core/config.py: model_selection_global_max_parallel (4), model_selection_cancel_drain_timeout_seconds (30);
    add to .env.example (UPPER_SNAKE) + a config test.
ROUTES:
  - app/features/model_selection/routes.py only (router already wired in app/main.py — no app/main.py change).
FRONTEND:
  - No new ROUTE/NAV (Slice A added /visualize/champion); Slice B extends the page + hooks + types only.
OBSERVABILITY (structlog, mirror existing model_selection.* + batch.* events):
  - model_selection.run_submitted / .candidate_started / .candidate_completed / .candidate_failed /
    .candidate_cancelled / .run_settled / .run_cancel_requested / .run_cancel_drained.
```

## Validation Loop

### Level 1 — Backend syntax & policy

```bash
uv run ruff check app/features/model_selection app/core/config.py alembic/versions
uv run ruff format --check app/features/model_selection app/core/config.py alembic/versions
uv run mypy app/features/model_selection app/core/config.py
uv run pyright app/features/model_selection app/core/config.py
uv run pytest app/core/tests/test_strict_mode_policy.py -v   # must stay green (no new strict date model)
```

### Level 2 — Backend unit tests

```bash
uv run pytest app/features/model_selection/tests -v -m "not integration"
```
Required new test names (additive to the backend foundation suite):
- `test_submit_run_returns_202_before_backtests_finish` (block a mocked backtest; assert response returns first)
- `test_submit_run_inserts_running_parent_and_pending_candidates`
- `test_worker_settles_completed_when_all_candidates_succeed`
- `test_worker_settles_partial_when_some_candidates_fail`
- `test_worker_settles_failed_when_all_candidates_fail` (winner None, 200-shaped GET, status failed)
- `test_settle_reuses_rank_candidates_and_build_chart_data` (terminal output byte-compatible with sync /run)
- `test_runner_semaphore_caps_concurrency` / `test_runner_cancel_before_start_skips` / `test_runner_cancel_mid_flight_marks_cancelled`
- `test_cancel_run_404_when_missing` / `test_cancel_run_409_when_terminal` / `test_cancel_run_returns_settled_on_drain`
- `test_get_selection_attaches_live_progress_groupby` / `test_legacy_sync_run_has_no_progress_children`
- `test_run_status_literal_accepts_cancelled`

### Level 3 — Migration & integration

```bash
docker compose up -d
uv run alembic upgrade head
uv run pytest app/features/model_selection/tests -v -m integration
uv run alembic downgrade -1 && uv run alembic upgrade head   # round-trips cleanly
```
Integration expectations: `model_selection_candidate` exists with FK CASCADE + indexes; `/runs` → poll →
terminal with a winner; a cancel mid-flight leaves NO candidate row in `running`; failed candidate visible.

### Level 4 — Full gates (must be green before PR)

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
uv run pytest -v -m "not integration"
cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run
```
> Known-local-noise: mypy/pyright report pre-existing lightgbm/xgboost optional-dep import errors in
> forecasting/+registry/ (CI installs the extras). Do NOT "fix" them; a green LOCAL mypy can MASK errors that
> only surface once the extras resolve types (memory: the #355 finalizer cast). Reset the DB
> (`docker compose down -v && up -d && alembic upgrade head`) before any Level-3 integration run.

### Manual dogfood probe (discover REAL ids first — IDs are NOT 1-based)

```bash
uv run uvicorn app.main:app --port 8123 &
curl -s "http://localhost:8123/dimensions/stores?page=1&page_size=5" | python3 -m json.tool | grep '"id"'
curl -s "http://localhost:8123/dimensions/products?page=1&page_size=5" | python3 -m json.tool | grep '"id"'
# submit (note Location/Retry-After + immediate 202 running)
curl -s -D - -X POST http://localhost:8123/model-selection/runs -H "Content-Type: application/json" -d '{
  "store_id": <ID>, "product_id": <ID>,
  "selection_window": {"start_date":"2026-01-01","end_date":"2026-05-31"},
  "forecast_horizon": 14,
  "split_config": {"strategy":"expanding","n_splits":5,"min_train_size":30,"gap":0,"horizon":14},
  "candidate_models": [{"model_type":"naive","params":{}},{"model_type":"seasonal_naive","params":{"season_length":7}},
    {"model_type":"moving_average","params":{"window_size":7}},{"model_type":"regression","params":{}},
    {"model_type":"prophet_like","params":{}}]}' | head -40
# poll (watch progress → terminal)
curl -s "http://localhost:8123/model-selection/<selection_id>" | python3 -m json.tool | grep -E 'status|progress|winner'
# cancel a fresh run mid-flight
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE "http://localhost:8123/model-selection/<selection_id>"   # 200/409
# frontend: VITE_API_BASE_URL=http://localhost:8123; dogfood /visualize/champion over http://localhost:5173 (NOT a LAN IP).
```

## Final Validation Checklist

- [ ] `POST /model-selection/runs` returns 202 + Location + Retry-After + `status="running"` BEFORE any backtest finishes.
- [ ] Detached worker uses `get_session_maker()` (never the request `db`); a held task ref prevents GC.
- [ ] `model_selection_candidate` rows track pending→running→{completed,failed,cancelled}; `result` JSONB on success.
- [ ] GET attaches live `progress` (GROUP BY children) + `candidate_progress`; terminal output byte-compatible with sync `/run`.
- [ ] `DELETE /{id}`: 404/409/200/504; no candidate row left `running` after a clean drain (integration-proven).
- [ ] Concurrency Semaphore-capped; one AsyncSession per candidate; `global_max_parallel=1` ⇒ sequential.
- [ ] `cancelled` added additively (ORM enum + CheckConstraint + response Literal + TS union); strict-mode test green.
- [ ] Migration up/down round-trips on a fresh DB; FK CASCADE + indexes present.
- [ ] Ranking/chart/business at settle REUSE `rank_candidates`/`build_chart_data`/`explain_winner` UNCHANGED.
- [ ] Frontend CTA → submit → progress panel → ranking table + winner card + 4 charts + detail drawer; partial/
      all-failed/cancelled states render; failed candidates stay visible; polling stops on terminal.
- [ ] No train/predict/override/promote UI (Slice C); no new npm dependency; no Slice A contract redefinition.
- [ ] All Level-1..4 gates pass; `gh issue view <N>` confirms the tracking issue is open; `git diff --stat`
      shows no CRLF whole-file noise; `docker-compose.lan.yml` NOT staged.

## Anti-Patterns to Avoid

- ❌ Don't `await` the runner inline in the POST handler (batch's pattern) — Slice B must detach via
  `asyncio.create_task` and return 202 first, or there is no progress/poll/cancel.
- ❌ Don't use the request `Depends(get_db)` session in the detached worker — it's closed; open fresh ones from `get_session_maker()`.
- ❌ Don't `asyncio.create_task` without holding a reference — the task can be GC'd mid-run.
- ❌ Don't write per-candidate progress into one shared parent JSONB from concurrent tasks (lost-update race) — use child rows.
- ❌ Don't import `app/features/batch/runner.py` — mirror it slice-locally (cross-slice rule).
- ❌ Don't rewrite ranking/chart/business at settle — reuse the existing pure modules.
- ❌ Don't pretend a mid-fit candidate cancelled when sklearn/LightGBM completed it — surface the honest outcome.
- ❌ Don't drop partial/failed/cancelled candidates — keep them visible in `ranking` + `candidate_progress`.
- ❌ Don't train, predict, override, or promote (Slice C). Don't add safety stock (Slice C; must not affect ranking).
- ❌ Don't redefine Slice A's types/page/route/catalog — extend additively. Don't break the legacy sync `POST /run`.
- ❌ Don't crypto.randomUUID() client-side; don't hardcode store_id=1/product_id=1; don't add a per-run max_parallel field (use the global setting).

## Confidence Score

**8.5/10** for one-pass implementation success. The async LRO pattern is fully proven in the merged `batch`
slice on this exact runtime, the repo ships a runtime-verified `asyncio-taskgroup-cancellation.md`, every
reused signature (backtest/ranking/chart/explain) is locked by the merged backend PRP, and every frontend
convention (polling hook, status badge, charts, Sheet drawer, AlertDialog, test harness) is cited to live
file:line. Residual risk (the 1.5): (a) the **fire-and-forget divergence** from batch (detached
`create_task` + the GC ref + worker-owns-its-sessions) is the one genuinely novel mechanic — it's spelled
out with the Python-docs citation, but it's the most likely place to slip; (b) a **process restart mid-run**
leaves a parent stuck in `running` with no reconcile pass (accepted single-host limitation; note it in the
PR, do not build crash-recovery here); (c) **504 drain-timeout** is hard to force deterministically in an
integration test (an in-flight sklearn fit is uncancellable) — unit-test the timeout via a stalled drain and
document that the integration 504 path may be probe-only.

### Scoring table (packaging brainstorm)

| Option | User value | Repo fit | Impl clarity | Risk control | Dep isolation | Total /25 |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|
| **A — Fire-and-forget LRO + child table + slice-local runner (CHOSEN)** | 5 | 5 | 4 | 4 | 5 | **23** |
| C — New runs + child table, sequential (no fan-out) | 3 | 3 | 5 | 5 | 5 | 21 |
| B — Convert `/run` in place, JSONB-in-parent progress | 4 | 2 | 3 | 2 | 2 | 13 |
