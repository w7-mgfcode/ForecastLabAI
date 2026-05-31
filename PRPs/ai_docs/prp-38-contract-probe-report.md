# PRP-38 — Contract Probe Report

> Task 1 of `PRPs/PRP-38-showcase-data-modeling-lifecycle.md`.
> Read-only verification of every backend / wire contract PRP-38 cites,
> against branch `feat/showcase-38-data-modeling-lifecycle` (off `origin/dev`
> at `48cddf3`).
> Generated: 2026-05-26.

## Verdict legend

- ✅ **PRESENT** — field/behaviour exists exactly as PRP-38 cites.
- 🟡 **DRIFTED** — exists, but with a shape PRP-38 needs to adjust against.
- ❌ **ABSENT** — does not exist; the dependent task is blocked.

## Summary

- ✅ 13 / 14 contracts verified PRESENT.
- 🟡 1 / 14 DRIFTED — `TrainResponse` does NOT carry V2 metadata
  (`feature_columns`, `feature_groups`, `feature_safety_classes`); call it
  out as PRP-38's Unresolved Assumption #1 fallback.
- ❌ 0 / 14 ABSENT.
- ➕ 1 additional finding: `RunUpdate` cannot patch `runtime_info` — the
  V2 metadata MUST be supplied on `RunCreate` (already what the PRP plans).

A targeted patch to PRP-38 (Task 15 pseudocode + bullets) is applied in the
same commit as this report. No tasks are blocked; the patch only narrows the
step_v2_train metadata source from "train response" to
"`GET /forecasting/runs/{id}/feature-metadata` post-registration", consistent
with PRP-38's own Unresolved Assumption #1 fallback.

---

## (a) `app/features/forecasting/schemas.py`

| Field | Cited PRP shape | Found shape | File:line | Verdict |
|-------|-----------------|-------------|-----------|---------|
| `TrainRequest.feature_frame_version` | `int = Field(default=1, ge=1, le=2)` | `int = Field(default=1, ge=1, le=2, …)` | `app/features/forecasting/schemas.py:475` | ✅ PRESENT |
| `TrainRequest.feature_groups` | `list[str] \| None` | `list[str] \| None = Field(default=None, …)` | `app/features/forecasting/schemas.py:484` | ✅ PRESENT |
| `TrainRequest` model_validator (V1+groups → 422; unknown V2 group → 422) | Required | `validate_feature_frame_version_and_groups` raises both | `app/features/forecasting/schemas.py:503-519` | ✅ PRESENT |
| `TrainResponse.model_path` | `str` — full `artifacts/models/...` path | `str` (set to `str(saved_path)` where `saved_path = save_model_bundle(bundle, Path(forecast_model_artifacts_dir)/f"model_{id}")`) | `app/features/forecasting/schemas.py:540` + `app/features/forecasting/service.py:374-394` | ✅ PRESENT — repo-relative `./artifacts/models/model_<id>` form (the load step `Path(...).resolve()`s before validating against `forecast_model_artifacts_dir.resolve()`, so either form works). |
| `TrainResponse.feature_columns` / `feature_groups` / `feature_safety_classes` | (Unresolved #1) "exposes directly OR via `GET /…/feature-metadata`" | **NOT exposed on `TrainResponse`** — only `store_id, product_id, model_type, model_path, config_hash, n_observations, train_start_date, train_end_date, duration_ms` | `app/features/forecasting/schemas.py:522-545` | 🟡 **DRIFTED — falls back to PRP's Unresolved #1 path: enrich step.data via `GET /forecasting/runs/{v2_run_id}/feature-metadata` AFTER success patch.** |
| `FeatureMetadataResponse.feature_frame_version` / `.feature_groups` / `.feature_safety_classes` | Exposed | All three Optional fields PRESENT | `app/features/forecasting/schemas.py:705-723` | ✅ PRESENT |

## (b) `app/features/registry/schemas.py`

| Field | Cited PRP shape | Found shape | File:line | Verdict |
|-------|-----------------|-------------|-----------|---------|
| `RunCreate.runtime_info_extras` | `dict[str, Any] \| None` accepting arbitrary keys including `feature_frame_version`, `feature_columns`, `feature_groups`, `feature_safety_classes` | `dict[str, Any] \| None = Field(default=None, …)` — docstring explicitly names the V2 metadata payload | `app/features/registry/schemas.py:85-95` | ✅ PRESENT |
| `RunResponse.feature_frame_version` | `@computed_field` reading `runtime_info`, None for legacy | `@computed_field` `def feature_frame_version(self) -> int \| None` reading `self.runtime_info.get("feature_frame_version")` | `app/features/registry/schemas.py:179-192` | ✅ PRESENT |
| `RunResponse.feature_groups` | `@computed_field`, None for legacy | `@computed_field` `def feature_groups(self) -> dict[str, list[str]] \| None` reading `self.runtime_info.get("feature_groups")` | `app/features/registry/schemas.py:194-205` | ✅ PRESENT |
| `RunUpdate.runtime_info_extras` | (not cited; assumed only `RunCreate` accepts it) | **NOT present on `RunUpdate`** — fields are `status`, `metrics`, `artifact_uri`, `artifact_hash`, `artifact_size_bytes`, `error_message` only | `app/features/registry/schemas.py:116-126` | ➕ **Finding** — V2 metadata MUST be set on the POST /registry/runs body; cannot be PATCHed later. PRP-38 step_v2_train already plans this (`runtime_info_extras` is set on the `create` POST). No PRP change needed beyond the drift patch above. |

## (c) `app/features/backtesting/schemas.py`

| Field | Cited PRP shape | Found shape | File:line | Verdict |
|-------|-----------------|-------------|-----------|---------|
| `FoldResult.horizon_bucket_metrics` | `dict[str, dict[str, float]]` (default `{}`) | `dict[str, dict[str, float]] = Field(default_factory=dict, …)` | `app/features/backtesting/schemas.py:171-177` | ✅ PRESENT |
| `ModelBacktestResult.bucketed_aggregated_metrics` | `dict[str, dict[str, float]] \| None` (default `None`) | `dict[str, dict[str, float]] \| None = Field(default=None, …)` | `app/features/backtesting/schemas.py:206-213` | ✅ PRESENT |
| `BacktestConfig.include_baselines` | `bool` (default `True`) | `bool = Field(default=True, …)` | `app/features/backtesting/schemas.py:101-104` | ✅ PRESENT |
| `BacktestRequest.feature_frame_version` (PRP assumption — MUST NOT exist) | No top-level field; V2-ness from `model_config_main.model_type` | `BacktestRequest` has fields `store_id, product_id, start_date, end_date, config` only; `ConfigDict(extra="forbid")` rejects extras | `app/features/backtesting/schemas.py:222-254` | ✅ PRESENT (absent, as required) |

## (d) `app/features/backtesting/metrics.py`

| Field | Cited PRP shape | Found shape | File:line | Verdict |
|-------|-----------------|-------------|-----------|---------|
| `HORIZON_BUCKETS` | `("h_1_7", "h_8_14", "h_15_28", "h_29_plus")` | `tuple[tuple[str, int, int \| None], ...]` of `(bucket_id, start, end)` triples — IDs match: `h_1_7`, `h_8_14`, `h_15_28`, `h_29_plus` | `app/features/backtesting/metrics.py:432-437` | ✅ PRESENT — **note:** the constant is triples, not bare IDs; subset checks must do `{b[0] for b in HORIZON_BUCKETS}`. |

## (e) `app/features/forecasting/models.py` — `prophet_like` family

| Item | Cited PRP shape | Found shape | File:line | Verdict |
|------|-----------------|-------------|-----------|---------|
| `prophet_like` is feature-aware (consumes exogenous X) | Required | `ProphetLikeForecaster.fit(...)` raises `ValueError("ProphetLikeForecaster requires exogenous features X for fit()")` and `predict(...)` likewise; classified `ModelFamily.ADDITIVE` in `_MODEL_FAMILY_MAP` | `app/features/forecasting/models.py:1487-1660`, `app/features/forecasting/feature_metadata.py:42-53` (`"prophet_like": ModelFamily.ADDITIVE`) | ✅ PRESENT |
| `ModelType` literal includes `prophet_like` | Required | `Literal[…, "prophet_like"]` | `app/features/forecasting/models.py:1673-1685` | ✅ PRESENT |

## (f) Feature-metadata resolution rule (R1)

| Behaviour | Cited PRP rule | Found | File:line | Verdict |
|-----------|----------------|-------|-----------|---------|
| `GET /forecasting/runs/{run_id}/feature-metadata` loads the bundle from `forecast_model_artifacts_dir` via `load_model_bundle(run.artifact_uri, base_dir=forecast_model_artifacts_dir)` | Required (R1) | `ForecastingService.get_feature_metadata_for_run` loads `load_model_bundle(run.artifact_uri, base_dir=self.settings.forecast_model_artifacts_dir)` — base_dir check is `path.resolve().relative_to(base_dir.resolve())`. A registry-relative `demo/{name}.joblib` resolving inside `artifacts/registry/` would FAIL the base_dir check; the FULL `artifacts/models/...` path resolves under the allowed base. | `app/features/forecasting/service.py:938-1021`, `app/features/forecasting/persistence.py:136-174` | ✅ PRESENT — R1 rule fully load-bearing. **The V2 step's `artifact_uri = train_response["model_path"]` is the ONLY workable choice.** |

## (g) Frontend wire types (`frontend/src/types/api.ts`)

| Field | Cited PRP shape | Found shape | File:line | Verdict |
|-------|-----------------|-------------|-----------|---------|
| `DemoRunRequest.scenario` (new) | Optional, default `demo_minimal` | Not yet added (PRP-38 Task 2 adds it backend + Task 12 wires frontend) | `frontend/src/types/api.ts` (no occurrence) | ✅ PRESENT (correctly absent — PRP-38 adds it) |
| `StepEvent.phase_name` / `.phase_index` / `.phase_total` (new) | Optional, additive | Not yet added (PRP-38 Task 2 adds them backend + Task 12 wires frontend) | `frontend/src/types/api.ts` (no occurrence) | ✅ PRESENT (correctly absent — PRP-38 adds it) |

---

## Patch applied to PRP-38

`PRPs/PRP-38-showcase-data-modeling-lifecycle.md` Task 15 step (c) is
rewritten from "fetch metadata via the train_response itself OR via
`/forecasting/runs/{id}/feature-metadata`" to "**always** call
`GET /forecasting/runs/{v2_run_id}/feature-metadata` AFTER the
running→success patch (step f) and capture `feature_columns` /
`feature_groups` / `feature_safety_classes` into step.data". The
`runtime_info_extras` on RunCreate carries `{"feature_frame_version": 2}`
only — sufficient for `RunResponse.feature_frame_version` to compute V=2,
and the Feature Frame panel still loads full V2 metadata from the bundle.

The pseudocode at lines 998-1000 is replaced; the unit-test assertion list
is updated. See the inline diff in the same commit as this report.

## Net impact on the implementation plan

- **No task deferred.** Task 15 (step_v2_train) gains one extra HTTP call
  after the success patch — three lines of code.
- **No task added.** The `/forecasting/runs/{id}/feature-metadata` endpoint
  already exists.
- **No backend contract change.** PRP-38 stays purely additive at the API
  layer.
- **Task 1 verdict for implementation:** ✅ **GREEN — proceed to Task 2.**
