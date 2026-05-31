# PRP-35 Final Contract Snapshot
> Captured for PRP-36 Task 1 (Contract Refresh) and PRP-37 Task 1 (Contract Probe).
> Source: `dev @ f2bf7c8` (PR #300 merge commit). Probed 2026-05-26.
> Read this file before writing any PRP-36 / PRP-37 code — it is the
> authoritative record of what PRP-35 actually shipped, not what the PRPs
> assumed it would ship.

---

## 1. Import-probe (verbatim from PRP-36 Task 1)

```
$ uv run python -c "from app.shared.feature_frames import \
    FEATURE_FRAME_VERSION_V2, FeatureGroup, \
    build_historical_feature_rows_v2, build_future_feature_rows_v2, \
    v2_feature_groups_dict, v2_feature_safety_classes; \
    print('PRP-35 surface OK')"
PRP-35 surface OK
```

`FEATURE_FRAME_VERSION_V2 = 2`. All six symbols resolve.

---

## 2. `FeatureGroup` enum — 11 members

`app/shared/feature_frames/contract_v2.py`. Declaration order:

```
TARGET_HISTORY, CALENDAR, ROLLING, TREND, PRICE_PROMO, INVENTORY,
LIFECYCLE, REPLENISHMENT, RETURNS, EXOGENOUS_WEATHER, EXOGENOUS_MACRO
```

---

## 3. `DEFAULT_V2_GROUPS` — actual ordering

```python
DEFAULT_V2_GROUPS = (
    TARGET_HISTORY, CALENDAR, ROLLING, TREND, PRICE_PROMO, LIFECYCLE,
)  # 6 groups
```

⚠️ **Drift vs PRP-36 § "Unresolved Contract Assumptions" item 10.** PRP-36
cites `(TARGET_HISTORY, ROLLING, TREND, CALENDAR, PRICE_PROMO, LIFECYCLE)`
— CALENDAR at position 4. Shipped order has CALENDAR at position 2.
Membership is identical; only ordering differs. Documentation-only drift
(canonical column ordering is driven by the manifest, not by enum order),
but PRP-36 item 10 should be patched to match.

---

## 4. Column counts (actual, probed at runtime)

| View | Count |
|------|-------|
| `canonical_feature_columns_v2()` (default 6 groups) | **38** |
| `canonical_feature_columns_v2(groups=tuple(g for g in FeatureGroup))` (all 11) | **51** |

⚠️ HANDOFF.md and the PRP-35 PR body both cite "max 53 columns". Actual
runtime is **51**. Doc-only drift; the running code is authoritative.

### Default 38 columns (in canonical manifest order)

```
lag_1, lag_7, lag_14, lag_28, lag_56, lag_364,
same_dow_mean_4, same_dow_mean_8,
dow_sin, dow_cos, month_sin, month_cos,
is_weekend, is_month_end,
week_of_year_sin, week_of_year_cos,
day_of_month_sin, day_of_month_cos,
is_holiday,
rolling_mean_7, rolling_mean_28, rolling_mean_90,
rolling_median_28, rolling_std_28,
trend_30, trend_90,
rolling_mean_7_vs_28, rolling_mean_28_vs_prev_28,
price_factor, promo_active, promo_discount_pct,
promo_kind_markdown_active, promo_kind_bundle_active,
days_since_launch, is_new_product, is_mature_product,
is_discontinued, days_until_discontinue
```

---

## 5. Pinned constants — `v2_pinned_constants()` actual output

```python
{
    "exogenous_lags":               [1, 7, 14, 28, 56, 364],
    "same_dow_mean_lookbacks":      [4, 8],
    "rolling_windows":              [7, 28, 90],
    "trend_windows":                [30, 90],
    "stockout_windows":             [7, 28],
    "replenishment_window":         [14],
    "replenishment_qty_window":     [28],
    "returns_windows":              [7, 28],
    "returns_rate_window":          [28],
    "inventory_availability_window":[28],
    "history_tail_days":            [400],
}
```

⚠️ PRP-36 cites only `EXOGENOUS_LAGS_V2`, `ROLLING_WINDOWS_V2`,
`TREND_WINDOWS_V2`, `HISTORY_TAIL_DAYS_V2` in the HANDOFF / PRP. The
shipped dict has **11 keys** (Phase-2 sidecar groups carry their own
window constants). No PRP-36 task depends on the missing keys directly;
flagged for completeness.

---

## 6. `TrainRequest` V2 fields — `app/features/forecasting/schemas.py:324-365`

```python
class TrainRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    ...
    # PRP-35 — opt-in, additive. NOT on ModelConfigBase (would orphan hashes).
    feature_frame_version: int = Field(default=1, ge=1, le=2, ...)
    feature_groups: list[str] | None = Field(default=None, ...)

    @model_validator(mode="after")
    def validate_feature_frame_version_and_groups(self) -> TrainRequest:
        # V1 + feature_groups → ValueError → FastAPI 422
        # V2 + unknown FeatureGroup name → ValueError → FastAPI 422
        ...
```

✅ Matches PRP-36 Assumption 6.

---

## 7. Bundle `metadata` — V1 vs V2 shape

Written in `app/features/forecasting/service.py:312-321` (V2) and `:335-341` (V1).

### V1 bundles (`feature_frame_version=1`)

```python
extra_metadata = {
    "feature_columns":       list[str],
    "history_tail":          list[float],
    "history_tail_dates":    list[str],   # ISO YYYY-MM-DD
    "launch_date":           str | None,  # ISO
    "feature_frame_version": 1,
}
```

✅ Matches PRP-36 Assumptions 1, 2, 6, 8 for V1.

### V2 bundles (`feature_frame_version=2`)

V1 keys above **PLUS**:

```python
"feature_groups":           dict[str, list[str]],   # v2_feature_groups_dict(...)
"feature_safety_classes":   dict[str, str],         # v2_feature_safety_classes(...)
"feature_pinned_constants": dict[str, list[int]],   # v2_pinned_constants()
```

`feature_frame_version` becomes `2`.

✅ Matches PRP-36 Assumptions 1, 2, 3, 4, 5.

Back-compat read pattern is `bundle.metadata.get("feature_frame_version", 1)`
— legacy bundles without the key default to V1.

---

## 8. `app/features/forecasting/v2_loaders.py` exports

Verified via `grep '^async def \|^def '`:

```
async def load_lifecycle_attrs        (db, product_id) -> tuple[date|None, date|None, str|None]
async def load_inventory_history      (db, store_id, product_id, start_date, end_date) -> dict
async def load_replenishment_history  (db, store_id, product_id, start_date, end_date) -> tuple[list[date], list[int]]
async def load_returns_history        (db, store_id, product_id, start_date, end_date) -> dict
async def load_promotion_history      (db, store_id, product_id, start_date, end_date) -> dict
async def load_exogenous_history      (db, store_id, start_date, end_date, signal_names=None) -> dict
def       assemble_v2_historical_sidecar (**inputs) -> V2HistoricalSidecar
def       assemble_v2_future_sidecar     (**inputs) -> V2FutureSidecar
```

✅ Matches PRP-36 Assumption 9 (all 8 names exposed). Module-level
`__all__` re-exports them.

---

## 9. Scenarios slice V2 dispatch — `app/features/scenarios/`

`feature_frame.py:235-341` — `build_future_frame(...)` now takes
`feature_frame_version: int = 1` + `history_tail_dates: list[date] | None = None`
+ `feature_groups: dict[str, list[str]] | None = None`. Branches:
- `version == 1` → preserved V1 `assemble_future_frame` path (byte-stable).
- `version == 2` → new `_build_future_frame_v2` helper at `:344-471`,
  delegating to `build_future_feature_rows_v2`.

`service.py:231-262` — `_simulate_model_exogenous` reads
`feature_frame_version` + `history_tail_dates` + `feature_groups` from
`bundle.metadata`, threads them through `build_future_frame`. V1 bundles
default to 1 via `.get(..., 1)`.

✅ Matches PRP-35 acceptance criteria; PRP-36 has no Task that depends on
this directly, but PRP-37 (UI) will.

---

## 10. ⚠️ Backtesting slice V2 dispatch — **NOT SHIPPED** (deferred)

This is the **only failing assumption** from PRP-36 Task 1.

### What PRP-36 Assumption 7 expects

> `backtesting/service.py` already reads
> `bundle.metadata.get("feature_frame_version", 1)` BEFORE the fold loop AND
> dispatches the `build_*_feature_rows_v2` calls at the V1 call sites
> (lines 493 / 553 in the V1 codebase). PRP-35 Task 13 promises this.

### What `dev @ f2bf7c8` actually has

Probed `app/features/backtesting/service.py` with `grep`:
- **Zero** mentions of `feature_frame_version`.
- **Zero** mentions of `build_*_feature_rows_v2`.
- **Zero** reads of `bundle.metadata`.
- Lines 493 / 553 still hard-call V1 `build_historical_feature_rows` /
  `build_future_feature_rows`.

### Why

PRP-35 Task 13 was **DEFERRED** in PR #300. Reason: the literal Task 13
wording ("read from fitted bundle BEFORE the fold loop") is incompatible
with backtesting's architecture, which trains fresh per fold from
`BacktestConfig.model_config_main` and never loads a bundle. The correct
opt-in surface is a request-time field on `BacktestConfig` itself — a
re-design Task 13 did not spec. Tracked at **GitHub issue #299** with full
follow-up scope (additive `feature_frame_version` + `feature_groups` on
`BacktestConfig`, V2 fold feature construction, leakage-focused V2
backtest tests, loader-sharing design decision).

### Impact on PRP-36

- **Task 8** ("WIRE backtesting service to emit per-fold
  `horizon_bucket_metrics`") instructs: *"PRESERVE the V1/V2 dispatch
  PRP-35 Task 13 added — no change to it."* — there is no V1/V2 dispatch to
  preserve. Task 8 needs to be either (a) reworded to "V2 dispatch lives in
  follow-up #299; this Task only adds bucket metrics on the existing V1
  path; the V2 bucket-metric emission lands when #299 lands" or (b)
  deferred jointly with #299.
- **Task 1** (Contract Refresh) — this very gate — must record the
  failure here and, per PRP-36's own instruction (line 1286), open a
  `chore(docs): refresh PRP-36 against PRP-35 final contract (#<this-issue>)`
  PR before Task 2 starts.

---

## 11. Verdict — PRP-36 readiness

| Assumption | Status | Notes |
|------------|--------|-------|
| 1. `bundle.metadata["feature_frame_version"]: int` defaults to 1 absent | ✅ | V2=2, V1=1 written; consumer pattern `.get(..., 1)` honoured |
| 2. `bundle.metadata["feature_columns"]: list[str]` for V1 and V2 | ✅ | Both write the key |
| 3. `bundle.metadata["feature_groups"]` for V2 only | ✅ | V2 writes `v2_feature_groups_dict(...)`; V1 omits |
| 4. `bundle.metadata["feature_safety_classes"]` for V2 only | ✅ | V2 writes `v2_feature_safety_classes(...)`; V1 omits |
| 5. `bundle.metadata["feature_pinned_constants"]` for V2 only | ✅ | V2 writes `v2_pinned_constants()`; V1 omits |
| 6. `TrainRequest.feature_frame_version` + `feature_groups` + validator | ✅ | Exactly as spec'd |
| 7. **Backtesting V2 dispatch lines 493/553** | ❌ | **DEFERRED** to issue #299; PRP-36 Task 8 wording needs patch |
| 8. `forecasting/service.py` writes V2 metadata via `extra_metadata` | ✅ | Both V1 and V2 metadata blocks confirmed |
| 9. `v2_loaders.py` exports 8 named functions | ✅ | All 8 exposed; module-level `__all__` re-exports |
| 10. `DEFAULT_V2_GROUPS = (TARGET_HISTORY, ROLLING, TREND, CALENDAR, PRICE_PROMO, LIFECYCLE)` | ⚠️ | Membership correct; ordering differs (CALENDAR is 2nd, not 4th) — doc-only drift |

### Required PRP-36 patches before Task 2

1. **§ Unresolved Contract Assumptions item 7** — replace with the
   "DEFERRED to #299" wording above; cite the architectural mismatch.
2. **Task 8** — drop "PRESERVE the V1/V2 dispatch PRP-35 Task 13 added —
   no change to it." Either: (a) scope Task 8 to the V1 fold path only and
   defer V2 bucket-metric emission to #299, or (b) defer Task 8 itself
   jointly with #299. Recommend (a) — bucket metrics on the V1 path are
   independently valuable.
3. **§ Unresolved Contract Assumptions item 10** — patch the ordering to
   `(TARGET_HISTORY, CALENDAR, ROLLING, TREND, PRICE_PROMO, LIFECYCLE)`.
4. **(Optional) HANDOFF / PR-body cite** of "53 max columns" — actual is
   **51**. Cosmetic; PRP-36 does not assert this number.

Once those patches land in a `chore(docs): refresh PRP-36 against PRP-35
final contract` commit, Task 2 onward is unblocked.
