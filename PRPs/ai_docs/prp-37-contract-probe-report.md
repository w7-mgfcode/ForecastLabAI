# PRP-37 Contract Probe Report

> **Task 1 (Contract Probe) of `PRPs/PRP-37-forecast-intelligence-C-interactive-ui.md`.**
> Verifies that every PRP-35 + PRP-36 backend surface PRP-37 wires UI to is present on `dev` BEFORE execution begins. Output is a per-field PRESENT / ABSENT verdict with `file:line`, plus a list of PRP-37 patches required before Task 2+ may start.

- **Probed against:** `dev` at commit `0e2ad9e` (post PR #303 merge).
- **Probed by:** AI agent, 2026-05-26.
- **Scope:** read-only schema audit. Zero code modified.
- **PRP-37 final-checklist target path:** `PRPs/ai_docs/contract-probe-report.md`. This report lives at the user-requested path `PRPs/ai_docs/prp-37-contract-probe-report.md`; the checklist line should be patched to match (see § "PRP-37 patches required").

---

## Executive Verdict — GO with patches

| Bucket | Result |
|--------|--------|
| **PRP-35 surface** (V2 feature contract) | ✅ **100% present** — `TrainRequest.feature_frame_version` + `feature_groups`, `FeatureMetadataResponse.{feature_frame_version, feature_groups, feature_safety_classes}`, the 11-value `FeatureGroup` enum, `DEFAULT_V2_GROUPS` |
| **PRP-36 surface** (model zoo + bucket metrics + V-aware ops) | ✅ **100% present** — 4 new forecasters, RMSE in `aggregated_metrics`, `FoldResult.horizon_bucket_metrics`, `ModelBacktestResult.bucketed_aggregated_metrics`, `RunResponse.{feature_frame_version, feature_groups}`, `StaleReason.FEATURE_FRAME_VERSION_MISMATCH`, `AliasHealth` + `ModelHealthEntry` carry `alias_feature_frame_version` + `comparable_run_feature_frame_version` |
| **PRP-37 self-consistency** | ⚠️ **3 field-name drifts + 1 absent field** — PRP-37 cites field names that do not match the backend (see § "PRP-37 patches required"). All are docs-level fixes; no backend work required. |

**Recommendation:** PRP-37 may proceed under the existing partial-execution gate model, BUT a one-commit docs patch is required first so the implementer wires the UI to real field names. Patch is mechanical (3 sed-able renames + 1 deferred-feature note). No `[gate:PRP-35]` or `[gate:PRP-36]` task is DEFERRED.

---

## Probe Matrix — every PRP-37 dependency, verified

### A. PRP-35 backend surface (forecasting + featuresets)

| PRP-37 cites | Backend reality | Verdict | Source |
|---|---|---|---|
| `TrainRequest.feature_frame_version: int` | `feature_frame_version: int = Field(default=1, ge=1, le=2, ...)` | ✅ PRESENT | `app/features/forecasting/schemas.py:475` |
| `TrainRequest.feature_groups: list[str] \| None` | `feature_groups: list[str] \| None = Field(...)` | ✅ PRESENT | `app/features/forecasting/schemas.py:484` |
| V1 + `feature_groups` → 422 | `validate_feature_frame_version_and_groups`: V1 + non-None → ValueError; V2 + unknown name → ValueError | ✅ PRESENT — Assumption 1 & 9 (Anti-Patterns) verified | `app/features/forecasting/schemas.py:504-513` |
| `FeatureMetadataResponse.feature_frame_version` | `feature_frame_version: int = Field(default=1, ge=1, le=2, ...)` | ✅ PRESENT | `app/features/forecasting/schemas.py:705` |
| `FeatureMetadataResponse.feature_groups: dict[str, list[str]] \| None` | identical typing | ✅ PRESENT | `app/features/forecasting/schemas.py:711` |
| `FeatureMetadataResponse.feature_safety_classes: dict[str, str] \| None` | identical typing | ✅ PRESENT | `app/features/forecasting/schemas.py:718` |
| `FeatureGroup` enum — 11 values | 11 values: `TARGET_HISTORY`, `CALENDAR`, `ROLLING`, `TREND`, `PRICE_PROMO`, `INVENTORY`, `LIFECYCLE`, `REPLENISHMENT`, `RETURNS`, `EXOGENOUS_WEATHER`, `EXOGENOUS_MACRO` (StrEnum, lowercase wire form) | ✅ PRESENT — every value PRP-37 hard-codes in `feature-frame-utils.ts` matches | `app/shared/feature_frames/contract_v2.py:80-114` |
| `DEFAULT_V2_GROUPS` matches `defaultV2Groups()` | 6 values: target_history, calendar, rolling, trend, price_promo, lifecycle | ✅ PRESENT — matches PRP-37 Task 2 hard-coded list exactly | `app/shared/feature_frames/contract_v2.py:120-127` |

### B. PRP-36 backend surface (backtesting + registry + ops + forecasting)

| PRP-37 cites | Backend reality | Verdict | Source |
|---|---|---|---|
| `FoldResult.horizon_bucket_metrics: dict[str, dict[str, float]]` | identical typing, `default_factory=dict` | ✅ PRESENT | `app/features/backtesting/schemas.py:171-177` |
| `MetricsCalculator.calculate_all` returns `"rmse"` | `"rmse": self.rmse(...).value` | ✅ PRESENT — RMSE is a key inside the `aggregated_metrics: dict[str, float]` payload | `app/features/backtesting/metrics.py:349` |
| `ModelBacktestResult.bucketed_aggregated_metrics: dict[str, dict[str, float]] \| None` | identical typing, default `None` | ✅ PRESENT — see § Drift #1 for name | `app/features/backtesting/schemas.py:206-212` |
| New `model_type` values dispatched | `weighted_moving_average`, `seasonal_average`, `trend_regression_baseline`, `random_forest` all in `model_factory` | ✅ ALL 4 PRESENT | `app/features/forecasting/schemas.py:131,165,198,232`; `app/features/forecasting/models.py:564,682,791,894`; factory at `models.py:1688` |
| New forecasters mapped in `_MODEL_FAMILY_MAP` | `weighted_moving_average → BASELINE`, `seasonal_average → BASELINE`, `trend_regression_baseline → ADDITIVE`, `random_forest → TREE` | ✅ PRESENT | `app/features/forecasting/feature_metadata.py:46-49` |
| `forecast_enable_random_forest` setting | `forecast_enable_random_forest: bool = False` (and used as the gate at train time) | ✅ PRESENT — server-side gate only; UI catches the 422 (PRP-37 Task 1.e expected this) | `app/core/config.py:103`, `app/features/forecasting/models.py:1761` |
| `RunCreate.runtime_info_extras: dict \| None` | identical typing | ✅ PRESENT — used by feature-aware training to persist V2 metadata | `app/features/registry/schemas.py:85` |
| `RunResponse.feature_frame_version: int \| None` (computed) | `@computed_field` returning the value in `runtime_info`, `None` for legacy | ✅ PRESENT | `app/features/registry/schemas.py:179-189` |
| `RunResponse.feature_groups: dict[str, list[str]] \| None` (computed) | `@computed_field` returning the value in `runtime_info`, `None` for legacy | ✅ PRESENT | `app/features/registry/schemas.py:194-204` |
| `StaleReason.FEATURE_FRAME_VERSION_MISMATCH = "feature_frame_version_mismatch"` | identical literal (4 enum values total: NEWER_SUCCESS_RUN, ARTIFACT_NOT_VERIFIED, RUN_NOT_SUCCESS, FEATURE_FRAME_VERSION_MISMATCH) | ✅ PRESENT | `app/features/ops/schemas.py:16-28` |
| `AliasHealth.alias_feature_frame_version: int \| None` | identical typing | ✅ PRESENT | `app/features/ops/schemas.py:161` |
| `AliasHealth.comparable_run_feature_frame_version: int \| None` | identical typing | ✅ PRESENT | `app/features/ops/schemas.py:167` |
| `ModelHealthEntry.alias_feature_frame_version` + `comparable_run_feature_frame_version` | identical typing on both | ✅ PRESENT — same V-mismatch contract as `AliasHealth` | `app/features/ops/schemas.py:355,362` |
| `ScenarioComparison.method: 'heuristic' \| 'model_exogenous'` | `Literal["heuristic", "model_exogenous"]` | ✅ PRESENT | `app/features/scenarios/schemas.py:310` |
| Frontend `ScenarioComparison.method` already typed | `method: 'heuristic' \| 'model_exogenous'` | ✅ PRESENT — Task 18 may proceed without an `api.ts` extension for this field | `frontend/src/types/api.ts:940` |

### C. PRP-37 cited fields with NO backend counterpart

| PRP-37 cites | Backend reality | Verdict | Where PRP-37 cites it |
|---|---|---|---|
| `ModelHealthEntry.n_comparable_runs` | Field does NOT exist. Closest existing field is `ModelHealthEntry.run_count: int` (total successful runs in the grain's history, not strictly comparable) | ❌ ABSENT | PRP-37 line 148, 199, 858 |
| `ScenarioAssumption.is_known_future` (or equivalent on `PriceAssumption` / `PromotionAssumption` / `HolidayAssumption` / `InventoryAssumption` / `LifecycleAssumption`) | Field does NOT exist on any assumption type. Every planner assumption is — by definition — hypothetical; backend has no "known future input" concept | ❌ ABSENT | PRP-37 lines 137, 188, 843, 1101 |

---

## Drift #1 — `bucketed_aggregated_metrics` vs PRP-37's `bucketed_aggregate_metrics`

PRP-37 consistently uses the singular form `aggregate`; the backend uses the past-participle form `aggregated`. Mechanical drift; not a behavioural gap.

| Location in PRP-37 | PRP-37 token | Backend reality |
|---|---|---|
| L130, L184, L693, L836, L1100, L1132 | `bucketed_aggregate_metrics` | `bucketed_aggregated_metrics` (`app/features/backtesting/schemas.py:206`) |
| L130, L184, L688-691, L837, L1100, L1131 | `aggregate_metrics.rmse` | `aggregated_metrics["rmse"]` — `aggregated_metrics` is a `dict[str, float]`, not a Pydantic class (`app/features/backtesting/schemas.py:204`, `app/features/backtesting/metrics.py:349`) |
| L688-691 | Implies a class `AggregateMetrics` with `rmse?: number` field | No such Pydantic class. Metrics are a dict; downstream typing in `frontend/src/types/api.ts` should keep them as `Record<string, number>` (existing `ModelRun.metrics: Record<string, number> \| null` precedent) |

**Effect on Task 4 (modify `frontend/src/types/api.ts`):**
- DO NOT introduce a Pydantic-class mirror `AggregateMetrics`. Keep `aggregated_metrics: Record<string, number>`. Read `rmse` as `aggregated_metrics["rmse"]`.
- Rename the new optional `bucketed_aggregate_metrics?` → `bucketed_aggregated_metrics?` on `ModelBacktestResult`.

---

## Drift #2 — `n_comparable_runs` cited but not shipped on `ModelHealthEntry`

PRP-37 Task 21 (line 858) asserts "All these fields ALREADY exist on `ModelHealthEntry`" and includes `n_comparable_runs` in that list. The actual `ModelHealthEntry` exposes `run_count: int` (total runs evaluated in the grain history), not a separate `n_comparable_runs` (which would have to filter by the comparable-run rule — overlapping window + same V).

**Options for PRP-37 (pick one in the patch):**
1. **Map to `run_count`** (recommended). Slight semantic stretch — surfaces "we have N runs to triangulate the drift verdict over", which is the operator-facing question Task 21 was answering. Cheap, no backend work.
2. **Defer the chip until a future PRP adds a `n_comparable_runs` computed field.** Surface a "N runs" pill with `run_count` in the meantime.
3. **Add `n_comparable_runs` as a backend computed_field** in a follow-up — out of PRP-37 scope (it explicitly forbids backend code).

Recommendation: option (1). Patch PRP-37 Task 21 to cite `run_count` and re-label the UI pill "comparable runs" → "runs evaluated".

---

## Drift #3 — `is_known_future` / "known future input vs hypothetical" pill has no backend support

PRP-37 Task 18 and the User-visible behaviour section (L137) call for a "known future input" vs "hypothetical" pill next to each assumption row. No `is_known_future` flag (or analog) exists on any `*Assumption` schema; every planner assumption is hypothetical by definition.

**Options:**
1. **Drop the pill entirely from PRP-37 Task 18** (recommended). A single "Hypothetical" pill is technically correct and adds no UX value; remove it from scope.
2. **Render the pill with a fixed "Hypothetical" label.** Doesn't drift from the backend but adds visual noise to no end.
3. **Defer until a future PRP adds the planner-side known-future signal.** Acceptable if the planner roadmap actually needs it.

Recommendation: option (1). Remove the pill from PRP-37 Task 18 + Success Criteria. The `method` badge (`heuristic` | `model_exogenous`) on the same page already differentiates baseline-vs-scenario semantics.

---

## Drift #4 — Final-checklist filename

PRP-37 § "Final validation Checklist" (line 1090) cites `PRPs/ai_docs/contract-probe-report.md`; Task 1 (line 721) cites `docs/contract-probe-report.md under PRPs/ai_docs/`. This report lives at `PRPs/ai_docs/prp-37-contract-probe-report.md` (the user-requested path; it is unambiguous as "the PRP-37 probe" and won't collide with a PRP-38 probe later).

Recommendation: patch PRP-37 to reference the prefixed filename, matching the convention already used by `PRPs/ai_docs/prp-35-final-contract-snapshot.md`.

---

## Per-task gate verdict

Every task in PRP-37's Task 1-26 list. `PROCEED` = no patch needed. `PROCEED after patch` = needs a docs fix listed above. `DEFER` = a `[gate:PRP-XX]` field is absent.

| # | Task | Gate | Verdict |
|---|---|---|---|
| 1 | Contract Probe | — | ✅ DONE (this report) |
| 2 | `feature-frame-utils.ts` | always | ✅ PROCEED |
| 3 | `horizon-bucket-utils.ts` | always | ✅ PROCEED |
| 4 | Extend `frontend/src/types/api.ts` | always | ✅ PROCEED after patch (use `bucketed_aggregated_metrics`, drop `AggregateMetrics` class) |
| 5 | `model-family-tabs.tsx` | always | ✅ PROCEED |
| 6 | `model-type-select.tsx` | always | ✅ PROCEED (all 4 new model_types confirmed) |
| 7 | `feature-frame-select.tsx` | [gate:PRP-35] | ✅ PROCEED (gate satisfied) |
| 8 | `feature-groups-toggle.tsx` | [gate:PRP-35] | ✅ PROCEED (gate satisfied) |
| 9 | `horizon-bucket-table.tsx` | [gate:PRP-36] | ✅ PROCEED after patch (consume `bucketed_aggregated_metrics`) |
| 10 | `feature-frame-panel.tsx` | [gate:PRP-35] | ✅ PROCEED |
| 11 | `champion-compatibility-badge.tsx` | [gate:PRP-36] | ✅ PROCEED (`feature_frame_version` on RunResponse confirmed; `data_window_start`/`end` already on frontend ModelRun L187-188) |
| 12 | `promote-confirmation-dialog.tsx` | always | ✅ PROCEED (verify hook exists; ModelRun fields all present) |
| 13 | `batch-preset-select.tsx` | always | ✅ PROCEED (all 4 new model_types + V2 + DEFAULT_V2_GROUPS confirmed) |
| 14 | `batch-matrix-picker.tsx` | always | ✅ PROCEED |
| 15 | `backtest-horizon-buckets-chart.tsx` | [gate:PRP-36] | ✅ PROCEED after patch (same field-name rename) |
| 16 | Modify `forecast.tsx` | — | ✅ PROCEED |
| 17 | Modify `backtest.tsx` | — | ✅ PROCEED after patch (rename) |
| 18 | Modify `planner.tsx` | — | ✅ PROCEED after patch (drop known-future pill; method badge proceeds) |
| 19 | Modify `run-detail.tsx` | — | ✅ PROCEED |
| 20 | Modify `run-compare.tsx` | — | ✅ PROCEED |
| 21 | Modify `ops.tsx` | — | ✅ PROCEED after patch (`n_comparable_runs` → `run_count` rename + label change) |
| 22 | Modify `batch.tsx` | — | ✅ PROCEED |
| 23 | Extend `use-runs.ts` | — | ✅ PROCEED (no backend-side `feature_frame_version` filter on the registry list endpoint exists; hook accepts param locally, does NOT forward — already PRP-37's spec) |
| 24 | Tests | — | ✅ PROCEED |
| 25 | Docs (`docs/user-guide/advanced-forecasting-guide.md`) | — | ✅ PROCEED |
| 26 | Dogfood | — | ✅ PROCEED — caveat: the local DB does not yet seed any V2-aware SUCCESS run; the PRP-37 dogfood note (L1211-1214) already calls this out. |

**0 DEFER.** Every `[gate:PRP-35]` and `[gate:PRP-36]` task gate is satisfied.

---

## PRP-37 patches required before execution

A single docs commit on `dev` (or on the PRP-37 implementation branch's first commit) covering:

1. **Rename throughout PRP-37:** `bucketed_aggregate_metrics` → `bucketed_aggregated_metrics` (6 occurrences listed in Drift #1).
2. **Replace class reference:** `AggregateMetrics` (with implied `.rmse?: number` field) → `aggregated_metrics: Record<string, number>` consistent with the existing `ModelRun.metrics` precedent (Drift #1 — Task 4 typing block at L688-696).
3. **Task 21 + Success Criteria L198-200:** replace `n_comparable_runs` with `run_count` and re-label the surfaced pill (Drift #2).
4. **Task 18 + Success Criteria L188 + User-visible behaviour L137:** remove the "known future input vs hypothetical" pill (Drift #3).
5. **Final validation Checklist L1090 + Task 1 L721:** align the contract-probe report filename to `PRPs/ai_docs/prp-37-contract-probe-report.md` (Drift #4).

Patches are all in `PRPs/PRP-37-forecast-intelligence-C-interactive-ui.md`; no other file moves. Estimated ~6 sed-able edits + 1 paragraph removal.

---

## Pre-execution housekeeping (carry-forwards from prior sessions)

These are not contract gaps — just operator reminders for the next session:

- **Local DB at stale alembic revision `a2b3c4d5e6f7`.** Pre-existing host condition (`HANDOFF.md`). Resolve with `docker compose down -v && docker compose up -d && uv run alembic upgrade head` if the dogfood (Task 26) needs a clean DB.
- **No V2 SUCCESS runs seeded locally.** PRP-37 dogfood Task 26 step (b) ("Train a V2 feature-aware run — confirm feature-groups toggles are visible") needs at least one V2 run before the empty-state vs populated-state distinction is meaningful. Train one before dogfood; do not seed a fake.
- **`stash@{0}` qwen3 stash** still preserved. Not relevant to PRP-37 execution; do not apply/pop/drop without an explicit decision.
- **Missing GitHub labels `scope:data` + `scope:batch`** — carryover from prior sessions. PRP-37 commits will use `scope:ui` (the existing label), so this is independent.

---

## Conclusion

**PRP-37 may proceed** with a 1-commit docs patch on the PRP-37 implementation branch's first commit (or as a small `docs(prp)` PR into `dev` immediately before kicking off the implementation branch). All `[gate:PRP-35]` and `[gate:PRP-36]` field dependencies are live on `dev` at `0e2ad9e`.

`qwen3` stash status: **`stash@{0}: On dev: local qwen3 rag demo changes before prp-35` — untouched (never applied / popped / dropped during this probe).**
