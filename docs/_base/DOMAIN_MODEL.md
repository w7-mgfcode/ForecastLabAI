# ForecastLabAI Domain Model
> Source: heuristic discovery from `app/features/data_platform/models.py`, `app/features/registry/models.py`, `app/features/rag/models.py`, `app/features/agents/models.py`, `app/features/forecasting/models.py`, `app/features/jobs/models.py`, `app/shared/seeder/`. Body spot-verified against the SQLAlchemy models on 2026-05-12.

## Bounded Contexts

| Context | Owns | Anti-Corruption Layer |
|---------|------|-----------------------|
| Data Platform | `store`, `product`, `calendar`, `sales_daily`, `price_history`, `promotion`, `inventory_snapshot_daily` | Ingest layer's natural-key resolution (`store_code` → `store_id`, `sku` → `product_id`) |
| Featuresets | Computed feature matrices (in-memory; not persisted) | Time-cutoff parameter — never reads beyond `cutoff_date` |
| Forecasting | Trained model artifacts on disk (joblib `.pkl`) | Model interface in `examples/models/model_interface.md`; artifact_uri returned to caller |
| Backtesting | Fold results, metrics (returned in response; persisted via Registry) | `SplitConfig` (expanding/sliding, gap, horizon) — `app/features/backtesting/splitter.py` |
| Scenarios | `scenario_plan` (saved what-if plans, JSONB assumptions + comparison) | `load_model_bundle` only (never a sibling `service.py`); `adjustments.py` heuristic multiplier or `feature_frame.py` model re-forecast; `agent_tools.py` is the agent-integration seam |
| Registry | `model_run`, `run_alias`, `model_artifact` | SHA-256 hash on artifact_uri; status state machine |
| RAG | `rag_source`, `rag_chunk` (with pgvector embedding column) | Content hash for idempotent indexing; embedding dimension fixed per provider |
| Agents | `agent_session` (JSONB message_history) | Pydantic-validated tool args; HITL approval queue |
| Jobs | `job` (JSONB params + result) | Discriminated-union `job_type` (`train`/`predict`/`backtest`) |
| Analytics | None persisted — pure read-aggregates | SQL GROUP BY over `sales_daily` joined to dimensions |
| Seeder ("The Forge") | Generates synthetic rows in Data Platform tables | `Scenario` preset + `DimensionConfig`/`FactsConfig` dataclasses; `dataclasses.replace` for field-precise overrides |

## Core Aggregates

### `model_run` (Registry)
- **Root:** `ModelRun(run_id: UUID, status: RunStatus)`
- **Status state machine:** `pending` → `running` → `success` | `failed` → `archived`
- **JSONB fields:** `model_config`, `metrics`, `runtime_info` (Python/numpy/pandas versions captured at training; PRP-35/PRP-36 additionally pin `feature_frame_version`, `feature_columns`, `feature_groups`, `feature_safety_classes`, `feature_pinned_constants` when the caller supplies them via `RunCreate.runtime_info_extras`)
- **Invariants:**
  - An alias may point only to a `success` run.
  - Artifact_uri SHA-256 hash must verify before any consumer trusts it (`GET /registry/runs/{id}/verify`).
  - `runtime_info` is immutable after `success`.
  - **Comparable-run rule (PRP-36).** A run is comparable to another only when ALL three hold: same `(store_id, product_id)` grain, OVERLAPPING `data_window_start`/`data_window_end`, AND same `feature_frame_version`. The third clause is load-bearing — `RegistryService._find_duplicate`, `RegistryService.find_comparable_runs`, and `OpsService` staleness all enforce it. A V1 run and a V2 run with otherwise identical fields are NOT duplicates and NOT comparable; legacy rows without the JSONB key are treated as V=1.
  - **Stale-alias V mismatch (PRP-36).** When an alias's run has `feature_frame_version=V_a` and a newer comparable SUCCESS run has `feature_frame_version=V_b != V_a`, the alias is marked `is_stale=true` with `stale_reason="feature_frame_version_mismatch"` — a distinct enum value from `newer_success_run` so the UI surfaces "your V is now stale" separately from "a newer run exists".

### `agent_session` (Agents)
- **Root:** `AgentSession(session_id: UUID, status: SessionStatus)`
- **Status:** `active` / `awaiting_approval` / `expired` / `closed` (`SessionStatus` enum, `app/features/agents/models.py:24`). Transitions: `ACTIVE → AWAITING_APPROVAL` (sensitive action pending), `AWAITING_APPROVAL → ACTIVE` (on approval/rejection), `ACTIVE → EXPIRED` (on timeout), `ACTIVE → CLOSED` (on explicit close).
- **Invariants:**
  - `message_history` JSONB is append-only within a session.
  - Tools in `agent_require_approval` block until `POST /agents/sessions/{id}/approve` returns.
  - Token budget cap (`agent_max_tokens`) and tool-call cap (`agent_max_tool_calls`) per session.

### `sales_daily` (Data Platform)
- **Root:** composite `(store_id, product_id, date)`
- **Invariants:**
  - `quantity >= 0`, `unit_price >= 0`, `total_amount = quantity * unit_price` (approx; rounding tolerated).
  - `store_id`, `product_id`, `date` must reference existing dimension rows.
  - Idempotent upsert via `ON CONFLICT (store_id, product_id, date) DO UPDATE` (`app/features/ingest/service.py`).

### `scenario_plan` (Scenarios)
- **Root:** `ScenarioPlan(scenario_id: str, name: str)`
- **JSONB fields:** `assumptions` (the raw `ScenarioAssumptions`), `comparison` (the full `ScenarioComparison` snapshot — stored so a reloaded plan re-renders without recomputation or the original artifact).
- **Scalar columns:** `tags` (a queryable JSONB string array — its own column, GIN-indexed, never folded into a blob) and `cloned_from` (the `scenario_id` a plan was cloned from); provenance/audit columns `source` (`'user'`|`'agent'`), `agent_session_id`, `approved_by`, `approved_at`, `approval_decision` (`'approved'`|`'rejected'`).
- **Invariants:**
  - `method` is CHECK-constrained to `IN ('heuristic','model_exogenous')`. `heuristic` is a deterministic post-forecast multiplier; `model_exogenous` is a genuine re-forecast of a regression baseline through a leakage-safe future feature frame (`feature_frame.py`).
  - A scenario adjustment touches only horizon (future) points; it never reads or mutates the historical series (`app/features/scenarios/tests/test_leakage.py` and `test_future_frame_leakage.py` are the spec).
  - JSONB columns are persisted via `model_dump(mode="json")` so `date`/`datetime` serialise to ISO strings.
  - An agent-saved plan (`source='agent'`) is persisted ONLY after the human approves it through the HITL gate — it always carries the approval audit trail.

### `showcase_workspace` (Demo)
- **Root:** `ShowcaseWorkspace(workspace_id: str, status: str)` — one row = one preserved (`preservation="keep"`) showcase run. Ephemeral runs (the default) write no row; a `workspace_name` merely labels a keep-run row (names are non-unique).
- **Status state machine:** `running` → `completed` | `failed` (CHECK-constrained; the finalize hook settles the row even on mid-run failure).
- **Stored metadata:** replay config (`seed`, `scenario`, `reset`, `skip_seed`), showcase grain + window (`store_id`, `product_id`, `date_start`, `date_end` — NULL on early failure), lifecycle (`status`, `created_at`/`updated_at`), and the JSONB payloads below. E1 (#407) adds operator-curation columns `archived` / `pinned` (booleans, default false, PATCH-mutable, orthogonal to `status` — the pipeline owns the run lifecycle), `notes` (free text, 2000-char cap at the Pydantic boundary), `tags` (a queryable JSONB string array — its own GIN-indexed column, exact `scenario_plan.tags` pattern, ≤20 items at the PATCH boundary), `config_schema_version` (int, default 1 — versions the workspace config + story-slot schema as a whole; any epic that changes a documented slot shape bumps the ORM default and documents the delta here), and the provenance column `replayed_from_workspace_id` (String(32), btree-indexed SOFT reference — see Invariants). E4 (#410) adds the replay-input column `run_config` (nullable JSONB, `{"train_model_types": [...], "backtest": {...}}` or NULL on default-config runs) — a REPLAY INPUT in the same class as `seed`/`scenario`/`reset`/`skip_seed`, **NOT a story slot** (D1): it records the start-frame model set + backtest config a kept run was launched with, written by `create_workspace` at insert time and consumed by Load/Replay. `config_schema_version` is deliberately NOT bumped by E4 — it versions the STORY-SLOT schema; `run_config` presence is NULL-detectable and carries its own documented shape. E5 (#411) DOES bump the ORM default `1 → 2` (it widened the `approval_events.decision` enum + added `"probe"` to `rag_events.event` + the additive entry keys below); `server_default` stays `text("1")` (no migration — pre-E5 rows inserted outside the ORM legitimately read 1).
- **JSONB fields:** `created_objects` (sparse soft-reference keys — `winning_run_id`, `v2_run_id`, `v2_model_path`, `alias`, `agent_session_id`, `batch_id`, `scenario_plan_ids`, `scenario_artifact_key`, `train_model_types`, `stale_alias_run_id`) and `result_summary` (winner / WAPE / wall-clock display payload). E5 (#411) additively writes `result_summary.story_reproduction` on a REPLAY keep-run (`replayed_from_workspace_id` set): `{"agent": V, "knowledge": V, "source_workspace_id": str|null}` with `V ∈ "reproduced" | "not_reproduced" | "not_applicable" | "unknown"` — `agent` compares the source row's `approval_events` vs this run's; `knowledge` compares `rag_events` entries whose `event` is `index`/`retrieve` with `status != "skip"`; a dangling source row → `unknown`. Computed inside `finalize_workspace`'s warn-and-continue try (one extra get-by-id select). It is NOT a story slot and NOT a new column (D7).
- **JSONB story slots (E1 #407 — authoritative per-slot schema):** six dedicated nullable JSONB columns; `NULL` = "slot never written" (distinct from empty). E1 ships the columns only — each slot has an assigned writer epic:
  - `seed_overrides` (**WRITTEN since E3 #409**) — SPARSE dict: only operator-set knobs appear, `{}` is never stored (`None` instead). Allow-listed keys (the `SeederOverrides` schema, `app/shared/seeder/overrides.py`): `stores` int 1-100, `products` int 1-500, `window_days` int 75-365, `sparsity` float 0-0.9, `promotion_intensity` float 0-0.5, `stockout_intensity` float 0-0.5, `noise_sigma` float 0-0.5. Persisted via `model_dump(mode="json", exclude_none=True)` at create time; replay re-submits it verbatim. Records the REQUESTED config — the data the run actually seeded follows from it deterministically.
  - `user_scope` (**WRITTEN since E3 #409**) — dict: operator-selected focus, `{"store_id": int>=1, "product_id": int>=1}` (`UserScope` schema, `extra=forbid`; additive keys need a documented schema change). Records the REQUESTED pair; the row's `store_id`/`product_id` columns record the EFFECTIVE grain the run modeled — the two legitimately diverge when the requested pair dangled and the status step warn-fell-back to discovery (divergence is visible by design). Both slots are exposed on the workspace LIST item (not detail-only) because the frontend Replay builds its start frame from list rows.
  - `approval_events` (**WRITTEN since E5 #411** — schema v2) — list[dict], append-only, one entry per resolved HITL approval. E1-frozen base keys: `{"action_id": str, "tool_name": str, "decision": "approved"|"rejected"|"timed_out", "decided_at": iso8601-str, "session_id": str}` (the `decision` enum is WIDENED with `"timed_out"` in v2). E5 additive keys (`config_schema_version >= 2`): `"auto_approved": bool` (true when the 10 s decision window lapsed → auto-approve), `"reason": str|None` (operator Reject reason, ≤500), `"execution_status": str|None` (agents-API `ApprovalResponse.status`: `executed`|`rejected`|`expired`; `"external_4xx"` on the absorbed direct-pre-empt edge; `None` on `timed_out`), `"tool_call_summary": {"description": str, "arguments_keys": list[str]}` (argument KEYS only — never values, per security-patterns.md), `"transcript_summary": str` (agent chat message, ≤200 chars), `"tokens_used": int`, `"tool_calls_count": int`. Written by `step_agent_hitl_flow` (in-memory) → `finalize_workspace` (DB, warn-and-continue); empty → slot stays NULL.
  - `rag_events` (**WRITTEN since E5 #411** — schema v2) — list[dict], append-only, one entry per knowledge-step return path. `{"event": "probe"|"index"|"retrieve"|"skip", "status": "pass"|"warn"|"skip", "detail": str, "count": int, "occurred_at": iso8601-str, "provider": str|None, "reachable": bool|None}` (the `"probe"` event value + `status`/`provider`/`reachable` keys are v2 additive; `reachable` is populated on the probe entry only). Written by the three knowledge steps (`embedding_provider_probe`/`rag_index_subset`/`rag_retrieve_probe`) on `showcase_rich` → `finalize_workspace`; empty → slot stays NULL.
  - `job_ids` (later parallel epic — E2 #408 / E4 #410 agree on the writer) — list[str]: job / batch sub-job ids the run submitted (soft references).
  - `phase_summaries` (later parallel epic) — list[dict], one per phase: `{"phase_name": str, "status": "pass"|"fail"|"warn"|"skip", "steps": int, "duration_ms": float}`.
- **Relationship to demo pipeline runs:** one workspace row per kept pipeline run — `create_workspace` inserts it as `running` before the first step; `finalize_workspace` settles it with the run's collected ids. NOT a seeder `scenario`: a preset is a reusable data-generation recipe; a workspace is the record of ONE concrete run (which preset it used, with what seed, and what it produced).
- **Invariants:**
  - The config columns (`seed`, `scenario`, `reset`, `skip_seed`) — plus, since E3 #409, the `seed_overrides`/`user_scope` story slots, and since E4 #410 the `run_config` replay-input column — are sufficient for a verbatim Replay through the normal run path; replay never mutates the original row; it creates a NEW row.
  - `name` is deliberately NON-unique; `workspace_id` (UUID hex) is the unique handle.
  - `created_objects` carries SOFT references only — **no ForeignKeys by design**. The workspace row is an audit record, not an ownership root: the referenced runs/plans/aliases are independently operator-deletable, and a workspace must never block (or cascade) their deletion.
  - Deletion is METADATA-ONLY, symmetric with the no-FK design: `DELETE /demo/workspaces/{id}` removes the `showcase_workspace` row and nothing else — the soft-referenced model runs, scenario plans, aliases, jobs, agent sessions, and artifacts survive, and a workspace whose references already dangle still deletes cleanly.
  - Persistence is warn-and-continue: a workspace write failure must never break the demo pipeline (the run completes with `workspace_id: null`). The HTTP-backed helpers (`update_workspace` for PATCH, like get/list/delete) take a caller-owned session and raise normally — warn-and-continue is pipeline-only.
  - E1 (#407): `replayed_from_workspace_id` is a SOFT reference — **no ForeignKey, not even self-referential**: ancestor workspace rows must stay independently deletable (metadata-only delete) without cascading to or blocking descendants. The value is recorded verbatim from the request (no existence check); dangling lineage pointers after an ancestor delete are expected and harmless, like every `created_objects` id.
  - E1 (#407): `status` is NOT patchable — `PATCH /demo/workspaces/{id}` covers `name`/`notes`/`tags`/`archived`/`pinned` only; `archived` is an orthogonal curation flag and the `ck_showcase_workspace_status` CHECK is untouched.
- **Out of scope (deliberately not modeled yet):** export bundles under `artifacts/showcase/<workspace>/` (E6 #412) and per-phase interactive configuration — see `docs/_base/RUNBOOKS.md` § Showcase workspace. (Advanced seed config + scope selection shipped in E3 #409 — the `seed_overrides`/`user_scope` slots are written. Agent/HITL + RAG story capture shipped in E5 #411 — the `approval_events`/`rag_events` slots above are now written, plus `result_summary.story_reproduction` on replay keep-runs. The `job_ids`/`phase_summaries` slots remain unwritten.)

## Key Invariants — NEVER violate

1. **Time safety in features.** `app/features/featuresets/` uses only data at or before `cutoff_date`. Lags via `shift(positive)`, rolling via `shift(1).rolling(...)`, all `groupby` entity-aware. The test `app/features/featuresets/tests/test_leakage.py` is the spec — it MUST keep passing.
2. **Forward-only migrations.** Once an Alembic migration is merged, never edit it. Add a new migration to fix or evolve.
3. **HITL approval gates the agent's mutation surface.** Every tool that writes state (`create_alias`, `archive_run`, `save_scenario`, …) must be in `agent_require_approval`. Widening the surface without updating that list is a security regression.
4. **Single-host deployable.** No managed cloud service in the core path. `docker-compose up` must continue to be the only prerequisite besides Python + Node.
5. **Pre-1.0 contracts may move.** Pin the version you build against. After `v1.0.0`, full SemVer applies.
6. **Seeder is idempotent + scoped.** Never introduce a "wipe everything" path that isn't behind `--confirm` + scope flag.

## Ubiquitous Language — use exactly these terms

| Term | Means | NOT |
|------|-------|-----|
| `store` | Retail location (dimension); composite-key parent of sales | branch, outlet |
| `product` | SKU (dimension); composite-key parent of sales | item, article |
| `sales_daily` | One row per `(store_id, product_id, date)` | order, transaction (those would be finer-grain) |
| `run` | A model training instance tracked in the registry | experiment, job |
| `alias` | A pointer to a `success` run (e.g., `production`, `champion`) | tag, label |
| `session` (agent) | One conversation between user and PydanticAI agent | thread, chat |
| `fold` | One train+test split inside a backtest | iteration |
| `baseline` | A naive / seasonal_naive / moving_average model included for comparison | benchmark, control |
| `lag` | Past value at offset `k` (`shift(k)`) | window |
| `rolling` | Statistic over a trailing window with `shift(1)` to avoid leakage | moving average (only for the MA model name) |
| `chunk` (RAG) | A windowed segment of a source document with its own embedding | section, paragraph |
| `days_since_launch` | Continuous integer offset from `product.launch_date` to a sales-daily row, used as a lifecycle feature (`days_since_launch_lag{N}`) | lifecycle_stage (Phase 2 dropped the categorical) |
| `replenishment event` | One row in `replenishment_event` representing inbound stock at `(store, product, date)`; feature cadence is derived from event spacing | inbound order, restock (those would be different grains) |
| `promotion (kind)` | One row in `promotion` with `kind ∈ {pct_off, bogo, bundle, markdown}`; features are one-hot per kind via `PromotionConfig.kinds_to_track` | discount, sale (kind is the discriminator, not "promotion" in the colloquial sense) |
| `scenario` (seeder) | A YAML or in-code preset (`retail_standard`, `holiday_rush`, …) that wires `DimensionConfig` + `FactsConfig` | template, profile |
| `scenario plan` | A saved what-if analysis — a `scenario_plan` row pairing raw `ScenarioAssumptions` with a `ScenarioComparison` snapshot | seeder `scenario` (a different concept entirely) |
| `assumption` (what-if) | One future change a planner posits — a price change, promotion, holiday set, inventory cap, or lifecycle stage — fed to `POST /scenarios/simulate` | forecast input, feature |
| `applied factor` | The deterministic per-day multiplier `combined_daily_factor` derives from the assumptions; `1.0` means no change | weight, coefficient |
| `model_exogenous` | The scenario `method` where a regression baseline genuinely re-forecasts through the assumptions — as opposed to the `heuristic` post-forecast multiplier | re-trained model (the baseline is not re-trained, only re-run) |
| `future feature frame` | The leakage-safe `X_future` matrix `feature_frame.py` builds — long-lag, calendar, and exogenous columns the regression model consumes to re-forecast a scenario | feature matrix (that is the training-time term) |
| `scenario tag` | A free-text label on a saved `scenario_plan` (its own queryable JSONB-array column) for filtering and grouping the library | seeder `scenario` preset, registry `alias` |
| `workspace` (showcase) | A saved showcase-run record (`showcase_workspace` row) — replay config + soft references to everything the run created | seeder `scenario` (a preset), `scenario plan` (a saved what-if), agent `session` |

## Event Taxonomy

None. There is no async event bus by design (`product-vision.md`: not a streaming system). All workflows are request/response or in-process tool-call.

## Entity Relationship Summary

```
store ─────┐
           ├──► sales_daily ◄──── price_history
product ───┤                 ◄──── promotion
           ├──► inventory_snapshot_daily
calendar ──┘

model_run ──owns──► artifact (on disk; SHA-256 verified)
model_run ◄─points-to── run_alias

rag_source ──owns──► rag_chunk (with pgvector embedding)

agent_session ──owns──► message_history (JSONB) ──may-contain──► tool_call (pending approval)

job ──may-reference──► model_run (for train/backtest jobs)

scenario_plan ──built-from──► model artifact (a baseline run_id) ──embeds──► comparison snapshot (JSONB)

showcase_workspace ──soft-references──► model_run / scenario_plan / run_alias / agent_session / batch (JSONB ids, NO FK)
```

## Glossary (cross-cutting)

| Term | Definition | Context |
|------|------------|---------|
| HITL | Human-in-the-loop — agent pauses for `/approve` call | Agents |
| RFC 7807 | `application/problem+json` error envelope | API |
| HNSW | Hierarchical Navigable Small World — pgvector index type | RAG |
| SMAPE | Symmetric Mean Absolute Percentage Error (0–200 scale) | Backtesting metrics |
| WAPE | Weighted Absolute Percentage Error | Backtesting metrics |
| PRP | Project Requirements Plan — the doc that gates a vertical-slice implementation | Workflow |
| INITIAL-N | Discovery-phase doc that precedes a PRP | Workflow |
| "The Forge" | Internal name for the seeder (`app/shared/seeder/`) | Seeder |
