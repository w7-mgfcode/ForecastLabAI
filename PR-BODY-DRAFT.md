# feat(forecast): add feature frame v2

Tracking issue: **#299** (under Forecast Intelligence roadmap epic **#295**).
PRP: `PRPs/PRP-35-forecast-intelligence-A-feature-frame-v2.md`.

## Summary

Lands the **V2 feature-frame contract** as an **additive, opt-in** surface
alongside the frozen V1 contract:

- **Shared layer** — V2 column manifest (38 default / 53 max columns across 11
  `FeatureGroup`s), `V2HistoricalSidecar` / `V2FutureSidecar` data carriers,
  and `build_historical_feature_rows_v2` / `build_future_feature_rows_v2`
  pure row builders. `app/shared/feature_frames/` stays leaf-level.
- **Training path** — `POST /forecasting/train` accepts optional
  `feature_frame_version: int = 1` and `feature_groups: list[str] | None = None`.
  V2 bundles persist `feature_frame_version`, `feature_columns`,
  `feature_groups`, `feature_safety_classes`, and `feature_pinned_constants`
  in bundle metadata.
- **Scenarios path** — `POST /scenarios/simulate` reads `feature_frame_version`
  from the loaded bundle metadata and dispatches V1 vs V2 future-frame
  assembly transparently.
- **LOAD-BEARING leakage specs** — three new specs land alongside the V1
  spec; never to be weakened:
  - `app/shared/feature_frames/tests/test_leakage_v2.py`
  - `app/features/forecasting/tests/test_regression_features_v2_leakage.py`
  - `app/features/scenarios/tests/test_future_frame_v2_leakage.py`

## V1 compatibility (back-compat invariant)

- Every V1 export keeps its current signature, return type, and behaviour.
- The load-bearing V1 leakage spec
  (`app/shared/feature_frames/tests/test_leakage.py`) and 22 sibling V1
  contract tests remain green **without modification**.
- V1 bundles trained before this PR load, predict, scenario-simulate, and
  backtest unchanged.
- `feature_frame_version=1` is the default everywhere; legacy bundles that
  predate the metadata field are treated as V1 via
  `bundle.metadata.get("feature_frame_version", 1)`.
- `feature_frame_version` lives on `TrainRequest`, **not** on
  `ModelConfigBase` — adding it to the config would mutate every existing V1
  `config_hash()` and orphan registry rows / aliases. Persisted to bundle
  metadata instead.

## V2 opt-in behaviour

- A `TrainRequest` with `feature_frame_version=2` (optionally `feature_groups=[…]`)
  triggers the V2 path; otherwise V1 runs unchanged.
- Validator gates:
  - V1 + `feature_groups` supplied → 422.
  - V2 + unknown `FeatureGroup` name → 422.
- Default V2 groups: `TARGET_HISTORY`, `CALENDAR`, `ROLLING`, `TREND`,
  `PRICE_PROMO`, `LIFECYCLE` (38 columns). Phase-2 sidecar groups
  (`INVENTORY`, `REPLENISHMENT`, `RETURNS`, `EXOGENOUS_WEATHER`,
  `EXOGENOUS_MACRO`) are off by default so the MVP stays green on smaller
  seeded DBs (max 53 columns when all enabled).
- Pinned V2 constants: `EXOGENOUS_LAGS_V2=(1,7,14,28,56,364)`,
  `ROLLING_WINDOWS_V2=(7,28,90)`, `TREND_WINDOWS_V2=(30,90)`,
  `HISTORY_TAIL_DAYS_V2=400`.

## Validation

All four mandatory gates green locally on `Python 3.12`:

```
✅ uv run ruff check .                       All checks passed
✅ uv run ruff format --check .              327 files already formatted
✅ uv run mypy app/                          0 PRP-35 errors (3 pre-existing xgboost noise on dev)
✅ uv run pyright app/                       0 PRP-35 errors (8 pre-existing optional-extra noise on dev)
✅ uv run pytest -m "not integration"        1480 passed, 12 skipped, 264 deselected
```

40 V2 leakage tests across 3 LOAD-BEARING files all green; 23 V1 contract /
leakage tests byte-stable.

The 3 mypy + 8 pyright pre-existing errors stem from optional `lightgbm` /
`xgboost` extras and are unrelated to PRP-35; CI runs `--all-extras` and won't
see them.

## No Alembic migration

V2 reads only existing tables (`inventory_snapshot_daily`,
`replenishment_event`, `sales_returns`, `exogenous_signal`, `promotion`,
`product`) and writes nothing to the DB. `alembic heads` unchanged at
`c1d2e3f40512`.

## Deferred: V2 backtesting dispatch — tracked in #299

PRP-35 lands V2 **training + scenarios + shared builders**. **Backtesting V2
dispatch is deferred** and explicitly tracked in the
"Deferred follow-up: V2 backtesting dispatch" section of **#299**.

PRP-35 Task 13 reads *"READ `feature_frame_version` from the fitted bundle
BEFORE the fold loop"*, but
`app/features/backtesting/service.py:_run_model_backtest` trains fresh per
fold from `BacktestConfig.model_config_main` and **does not load a fitted
bundle**. The correct opt-in surface is a request-time field on
`BacktestConfig` itself — a re-design Task 13 did not spec.

**This PR does NOT claim completion of PRP-35 Tasks 13 or 18.** V1
backtesting is unchanged; a V2-trained bundle still trains and
scenario-simulates correctly. Only `/backtesting/run` remains V1-only until
the follow-up under #299 lands. Integration tests (PRP-35 Tasks 15 + 16) and
the PHASE/3 + PHASE/4 doc edits (Task 21) are also deferred there.

## qwen3 stash status

The session's `stash@{0}` ("local qwen3 rag demo changes before prp-35",
`app/features/rag/models.py` +7/-2) is **not applied, not popped, not
dropped**. The decision on it (write a real
`INITIAL-rag-embedding-provider-pluggability.md` doc vs. add to
`.git/info/exclude`) is carryover work, untouched by this PR.

## Files changed

```
 M app/features/forecasting/routes.py            (+2)
 M app/features/forecasting/schemas.py           (+70)
 M app/features/forecasting/service.py           (+318)
 M app/features/scenarios/feature_frame.py       (+193)
 M app/features/scenarios/service.py             (+25)
 M app/shared/feature_frames/__init__.py         (+79)
 M docs/optional-features/10-baseforecaster-feature-contract.md (+40)
 A app/shared/feature_frames/contract_v2.py
 A app/shared/feature_frames/rows_v2.py
 A app/shared/feature_frames/sidecar.py
 A app/shared/feature_frames/tests/test_contract_v2.py
 A app/shared/feature_frames/tests/test_leakage_v2.py
 A app/features/forecasting/v2_loaders.py
 A app/features/forecasting/tests/test_regression_features_v2_leakage.py
 A app/features/scenarios/tests/test_future_frame_v2_leakage.py
 A examples/forecasting/feature_frame_v2_preview.py
 A PR-BODY-DRAFT.md
```

## Test plan

- [ ] CI green on all five gates (ruff / mypy / pyright / pytest / migration-check).
- [ ] Verify `/forecasting/train` accepts `feature_frame_version=2` with default groups.
- [ ] Verify `/forecasting/train` accepts `feature_frame_version=2` with opt-in
      Phase-2 group (e.g. `INVENTORY`) on a seeded DB carrying inventory rows.
- [ ] Verify `/scenarios/simulate` against a V2-trained bundle produces a
      `model_exogenous` re-forecast (V2 future-frame assembly via bundle metadata).
- [ ] Verify a V1 bundle trained before this PR still loads, predicts, and
      scenario-simulates unchanged.
- [ ] Verify `/backtesting/run` against a V2-trained bundle remains V1-only
      (no V2 dispatch on the fold loop) — documented deferral above.
