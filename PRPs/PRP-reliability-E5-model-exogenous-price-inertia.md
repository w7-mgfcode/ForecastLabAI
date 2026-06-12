name: "PRP reliability-E5 — model_exogenous price inertia: discriminator tests + seeder price coupling"
description: |
  Issue #237 (epic E5 of umbrella #380, milestone reliability-hardening).
  Investigate-first epic: the `model_exogenous` scenario re-forecast returns an exact
  0.0 units/revenue delta for any price assumption. This PRP lands the discriminating
  reproduction tests (wiring-bug vs zero-learned-elasticity), records the verdict the
  research already established with runtime evidence, and ships the root-cause fix:
  the seeder never couples its generated price changes into `sales_daily`, so every
  trained regression model sees a constant `price_factor ≡ 1.0` and cannot learn a
  price response.

---

## Goal

Make `method="model_exogenous"` scenario simulations genuinely respond to price
assumptions on seeded data, and pin the discriminating evidence as permanent tests:

1. **Discriminator tests** (the issue's primary deliverable) that prove, in CI, which
   hypothesis from #237 holds: (a) the future-frame/predict wiring drops the price
   assumption, or (b) the trained model genuinely learned zero price elasticity.
2. **The fix per the verdict** — the verdict is (b), with a precise mechanical cause:
   `app/shared/seeder/generators/facts.py` hardcodes `current_price=None` (line 525)
   and `unit_price = base_price` (line 544), so seeded `sales_daily.unit_price` is
   constant per product even though `price_history` (and Phase-2 markdowns) say the
   price moved. Training-time `price_factor = unit_price / median(unit_price) ≡ 1.0`
   is a constant column; `HistGradientBoostingRegressor` never splits on a constant,
   so the re-forecast is invariant to any future `price_factor` — delta exactly 0.0
   (runtime-verified below). The fix threads the already-generated price series into
   `SalesDailyGenerator` so `unit_price` varies truthfully AND demand responds via the
   existing (currently dormant) `RetailPatternConfig.price_elasticity` machinery.
3. **End-to-end proof**: an integration test that seeds → trains a regression model →
   simulates a price cut → asserts a non-zero delta. This is the test that fails on
   `dev` today (with coupling off) and passes with the fix.

**End state**: a freshly seeded DB + `POST /forecasting/train` (`regression`) +
`POST /scenarios/simulate` with a price assumption produces `units_delta != 0.0`, and
the What-If Planner's model_exogenous path is demonstrably model-driven.

## Why

- `method="model_exogenous"` is the scenarios slice's headline capability (PRP-27): a
  *model-driven* what-if, distinct from the deterministic heuristic multiplier. While
  it returns 0.0 for every price assumption it is indistinguishable from a no-op and
  actively misleading in the Planner UI (#229/#236 made the path reachable; #237 is
  the follow-up they explicitly deferred).
- The dormant seeder elasticity machinery (`RetailPatternConfig.price_elasticity = -0.5`,
  `_compute_demand` lines 367-370) was designed for exactly this and is one wiring
  step away from working.
- Data consistency: today `price_history` says a product's price changed while every
  `sales_daily` row for the same days carries the unchanged `base_price` — the two
  fact tables contradict each other. The fix removes a falsehood from "The Forge".

## What

### Investigation verdict (pre-established — encode as tests, don't re-litigate)

Research for this PRP traced the full chain and verified each link at runtime:

| # | Link | Evidence | Verdict |
|---|------|----------|---------|
| 1 | Scenario price assumption → future frame | `build_exogenous_columns` emits `price_factor = 1 + change_pct` inside the window (`app/features/scenarios/feature_frame.py:155-158`); unit test `test_exogenous_price_window` (`tests/test_feature_frame.py:133`) passes | ✅ wired |
| 2 | Two frames → two predicts | `_simulate_model_exogenous` builds a scenario frame and an assumptions-stripped baseline frame, feeds both to `bundle.model.predict(h, X)` (`app/features/scenarios/service.py:250-288`) | ✅ wired |
| 3 | `RegressionForecaster.predict` honors X | passes X straight to `HistGradientBoostingRegressor.predict` (`app/features/forecasting/models.py:1129`) | ✅ wired |
| 4 | E2E with a price-sensitive bundle | integration test asserts `units_delta > 0.0` for a LightGBM bundle trained on elastic synthetic data (`app/features/scenarios/tests/test_routes_integration.py:194`) — but the **regression**-bundle twin (line 150) asserts only `method`, not the delta (gap to close) | ✅ wired (gap: assertion missing for `regression`) |
| 5 | Seeded training data | `SalesDailyGenerator` hardcodes `current_price=None` ("Simplified: use base price", `facts.py:525`) and `unit_price = base_price` (`facts.py:544`); `PriceHistoryGenerator` output (`facts.py:562-653`) + markdown price records (`core.py:403`) never reach sales rows | ❌ **root cause** |
| 6 | Constant column → exact 0.0 | runtime-verified (Known Gotchas, VERIFIED CLAIM #1): HistGBR trained with a constant `price_factor` produces byte-identical predictions for price_factor 1.0 / 0.85 / 0.60 | ❌ consequence |

**Verdict: hypothesis 2 from #237 — zero learned elasticity — with a deterministic
mechanical cause in the seeder, NOT a scenarios-slice wiring bug.** The 0.0 is exact
(not merely small) because a tree ensemble never splits on a constant training column.

### Behavior change

- `app/shared/seeder/`: `SalesDailyGenerator.generate` accepts an optional per-day
  price lookup built from the already-generated `price_history` records (including
  Phase-2 markdown price drops). When supplied, each sales row's `unit_price` is the
  resolved day price and `_compute_demand` receives it as `current_price`, activating
  the existing elasticity multiplier (`demand *= 1 + price_elasticity * change_pct`).
  When omitted (`None`, the default) the legacy path is byte-identical — the seeder's
  established disabled-path convention.
- `RetailPatternConfig` gains `price_sales_coupling: bool = True` — the orchestrator
  (`core.py`) threads the lookup only when True. Default True so every scenario
  (`demo_minimal`, `showcase_rich`, …) produces learnable price signal out of the box.
- Scenarios slice: **no production-code change** (wiring is sound). Tests only.
- Forecasting slice: **no production-code change**. Tests only.

### Success Criteria

- [ ] Frame discriminator test: scenario frame vs assumptions-stripped baseline frame
      differ ONLY in the `price_factor` column, exactly inside the assumption window
      (pure unit test, no DB).
- [ ] Inert-mechanism test: a `RegressionForecaster` fit on a constant-`price_factor`
      matrix predicts identically for any future `price_factor` (delta exactly 0.0) —
      pins hypothesis-2 mechanics so the verdict is executable documentation.
- [ ] The regression-bundle integration test asserts `units_delta > 0.0` (closing the
      gap vs its LightGBM twin) and that a −40% cut moves demand at least as much as
      −15%.
- [ ] Seeder: with coupling on, `sales_daily.unit_price` agrees with the active
      `price_history` window per (store, product, date); with the lookup omitted the
      output is byte-identical to today (regression-pinned).
- [ ] E2E integration test: seed (coupling on) → train `regression` → simulate a
      price cut → `units_delta != 0.0` and `method == "model_exogenous"`.
- [ ] All five validation gates green; seeder + scenarios + forecasting suites pass;
      `make demo` still goes green.
- [ ] Issue #237 closed with the verdict + evidence; `docs/DATA-SEEDER.md` documents
      the coupling flag.

## All Needed Context

### Documentation & References

```yaml
# ── The symptom and its scope ────────────────────────────────────────────────
- issue: "#237 — gh issue view 237"
  why: Exact repro (store 332/product 456, run dc6dc4aaea18, -0.15 and -0.40 both → 0.0),
       the two hypotheses, and the investigate-first mandate. Epic E5 of umbrella #380.

- file: app/features/scenarios/service.py
  why: "_simulate_model_exogenous (lines 184-350) — the two-frame compare. READ-ONLY:
       scenario_frame (line 250) carries request.assumptions; baseline_frame (line 265)
       carries ScenarioAssumptions(); both go to bundle.model.predict(h, X) (283-288).
       Wiring is sound — do NOT change this file."

- file: app/features/scenarios/feature_frame.py
  why: "build_exogenous_columns (114-181): price_factor = 1.0 + change_pct inside the
       inclusive window (155-158), 1.0 outside. assemble_future_frame (184-232) is the
       pure assembler the frame discriminator test (T1) drives — no DB needed."

- file: app/features/forecasting/models.py
  why: "RegressionForecaster (1020-1159): requires_features=True, fit validates X
       (1084-1091), HistGBR estimator (1092-1099), predict passes X straight through
       (1123-1133). T2 (inert-mechanism test) fits this class directly."

# ── Root cause: the seeder's price/sales decoupling ─────────────────────────
- file: app/shared/seeder/generators/facts.py
  why: "THE FIX SITE. _compute_demand (303+) already applies price elasticity when
       current_price is not None (367-370: demand *= 1 + price_elasticity*change_pct).
       The sales loop nulls it: current_price=None at 525 ('Simplified: use base
       price') and unit_price = base_price at 544. PriceHistoryGenerator (562-653)
       emits validity-window records: mostly chain-wide (store_id=None, line 604),
       ~10% store-specific (607-608), final open-ended record valid_to=None (643-651)."

- file: app/shared/seeder/core.py
  why: "Orchestration order proves feasibility: price_records materialized at 335-341,
       markdown price drops merged into the same list at 403, sales_gen.generate called
       AFTER at 449-456 — the lookup can be built in between. Mirror the existing
       optional-input convention: weather_lookup_for_sales (429-433) is threaded only
       when its config flag is on, None otherwise."

- file: app/shared/seeder/config.py
  why: "RetailPatternConfig.price_elasticity: float = -0.5 (line 93, documented '% demand
       change per % price change'). Add price_sales_coupling: bool = True beside it.
       Dataclass conventions: field + docstring Args entry."

# ── How training consumes prices (read-only — explains the constant column) ──
- file: app/features/forecasting/service.py
  why: "Regression training reads sales_daily.unit_price (line 636), baseline_price =
       median of positive prices (659-660), so constant unit_price → price_factor ≡ 1.0.
       Also shows promo_dates/holiday_dates sourcing — training DOES see promo flags,
       which is why promo_active (unlike price_factor) has training variance today."

- file: app/shared/feature_frames/rows.py
  why: "build_historical_feature_rows line 113: row.append(prices[index] / baseline_price)
       — the price_factor cell. The single source of truth shared by training and the
       scenarios future frame (canonical_feature_columns)."

# ── Test patterns to mirror (extend, never weaken) ───────────────────────────
- file: app/features/scenarios/tests/conftest.py
  why: "trained_regression_model fixture (line 240): fits RegressionForecaster on
       synthetic X = rng.normal(...), target = 40 - 20*price_factor + noise(0.5),
       full PRP-27 metadata (feature_columns/history_tail/launch_date), saves bundle
       under settings.forecast_model_artifacts_dir, yields run_id, unlinks on teardown.
       TEST_TRAIN_END_DATE='2026-06-30' (line 49) — horizon days are 2026-07-01..14."

- file: app/features/scenarios/tests/test_routes_integration.py
  why: "_PRICE_ASSUMPTION (18-20): change_pct=-0.15, window 2026-07-01..14 — fully
       covers the 14-day horizon. TestSimulateModelExogenous (147): the regression test
       (150-165) asserts ONLY method=='model_exogenous'; the LightGBM twin asserts
       units_delta > 0.0 at line 194. T3 adds the missing assertions to the regression
       test (and dedups the copy-pasted lines 188-191 in the LightGBM twin if touched)."

- file: app/features/scenarios/tests/test_feature_frame.py
  why: "test_exogenous_price_window (133) — the existing price-window unit test; T1
       (frame discriminator) extends this file with a scenario-vs-baseline matrix diff."

- file: app/features/scenarios/tests/test_future_frame_leakage.py
  why: "LOAD-BEARING leakage spec (with app/shared/feature_frames/tests/test_leakage.py).
       NEVER weaken. The new tests must not touch these files."

- file: app/shared/seeder/tests/test_phase1_regression.py
  why: "Byte-stability conventions: no_kwargs == explicit-defaults (58-72) and
       disabled-Phase-1 consumes zero rng (75-93). The price lookup must use NO rng
       draws and default to None so both invariants keep passing unchanged."

- file: app/shared/seeder/tests/test_generators.py
  why: "SalesDailyGenerator unit-test patterns (deterministic random.Random(seed),
       direct .generate calls, dict-row assertions; total_amount == unit_price *
       quantity at 229-243 — still holds after the fix since both are recomputed)."

- docfile: PRPs/ai_docs/exogenous-regressor-forecasting.md
  why: "PRP-27's research doc: the model contract, the future-frame leakage rule, and
       why HistGBR was chosen. Background for the discriminator tests' design."

# ── External references ───────────────────────────────────────────────────────
- url: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html
  why: "Binning behavior — features are discretized into max_bins=255 training-quantile
       bins; values outside the training range fall into the edge bins. Explains both
       the exact-0.0 symptom (constant column → no splits) and the saturation gotcha."

- url: https://github.com/w7-mgfcode/ForecastLabAI/pull/236
  why: "PR that made the model_exogenous path reachable from the Planner (#229/#228)
       and explicitly deferred this 0.0-delta investigation to #237."
```

### Current Codebase tree (relevant subset)

```bash
app/
├── features/
│   ├── forecasting/
│   │   ├── models.py                 # RegressionForecaster (1020-1159)
│   │   ├── service.py                # training reads sales_daily.unit_price (636)
│   │   └── tests/test_models.py      # _synthetic_data() builder pattern
│   └── scenarios/
│       ├── feature_frame.py          # build_exogenous_columns / assemble_future_frame
│       ├── service.py                # _simulate_model_exogenous (READ-ONLY here)
│       └── tests/
│           ├── conftest.py           # trained_regression_model (240), price-sensitive
│           ├── test_feature_frame.py # T1 lands here
│           └── test_routes_integration.py  # T3 lands here (150-165 gap)
└── shared/
    └── seeder/
        ├── config.py                 # RetailPatternConfig (price_elasticity at 93)
        ├── core.py                   # orchestration (335 price → 449 sales)
        ├── generators/facts.py       # SalesDailyGenerator + PriceHistoryGenerator
        └── tests/                    # test_generators.py, test_phase1_regression.py …
```

### Desired Codebase tree

```bash
app/
├── features/
│   ├── forecasting/tests/
│   │   └── test_models.py                       # + T2: constant-column inertia test
│   └── scenarios/tests/
│       ├── test_feature_frame.py                # + T1: scenario-vs-baseline frame diff
│       └── test_routes_integration.py           # + T3: regression delta assertions
│                                                # + T6: seeded-E2E repro (new class)
└── shared/seeder/
    ├── config.py                                # + RetailPatternConfig.price_sales_coupling
    ├── generators/facts.py                      # + build_price_lookup() resolver;
    │                                            #   SalesDailyGenerator.generate(
    │                                            #     ..., price_lookup=None)
    ├── core.py                                  # + build & thread the lookup (gated)
    └── tests/
        ├── test_generators.py                   # + T4: resolver + coupling unit tests
        └── test_phase1_regression.py            # unchanged — must keep passing
docs/DATA-SEEDER.md                              # + coupling flag paragraph
PRPs/PRP-reliability-E5-model-exogenous-price-inertia.md   # this file
```

### Known Gotchas & Library Quirks

```python
# ── VERIFIED LIBRARY CLAIM #1: constant training column → EXACT 0.0 delta (sklearn 1.6+)
#   uv run python -c "
#   import numpy as np
#   from sklearn.ensemble import HistGradientBoostingRegressor
#   rng = np.random.default_rng(42); n = 300
#   X = rng.normal(10, 2, size=(n, 5)); X[:, 4] = 1.0           # price col CONSTANT
#   y = 40.0 + 0.5 * X[:, 0] + rng.normal(0, 0.5, n)
#   m = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05,
#                                     max_depth=6, random_state=42).fit(X, y)
#   xt = X[:5].copy(); p0 = m.predict(xt)
#   xt[:, 4] = 0.85; p15 = m.predict(xt); xt[:, 4] = 0.60; p40 = m.predict(xt)
#   print(np.abs(p15-p0).max(), np.abs(p40-p0).max())"
#   # → 0.0 0.0   (verified 2026-06-12, sklearn from uv.lock)
# A tree ensemble NEVER splits on a constant training column, so predictions are
# invariant to that column at predict time — the delta is EXACTLY 0.0, matching the
# issue symptom byte-for-byte. This is the mechanism T2 pins. Re-verify on sklearn bump.

# ── VERIFIED LIBRARY CLAIM #2: out-of-training-range price clips to the edge bin ──────
#   (same script, but X[:, 4] = rng.uniform(0.7, 1.1, n); y = 40 - 20*X[:, 4] + noise)
#   # → delta(-15%) ≈ 2.88, delta(-40%, i.e. 0.60 < train-min 0.7) == delta(at 0.70)
# HistGBR bins by TRAINING quantiles; a scenario price_factor below the training range
# saturates at the lowest bin. After the seeder fix, training price_factor spans roughly
# [1 - max_price_change_pct, 1 + max_price_change_pct] compounded (~±20%/step) — deltas
# for cuts deeper than the observed range will saturate, NOT extrapolate linearly.
# T3's monotonicity assertion must therefore be >= (not >) between -40% and -15%.

# ── GOTCHA: byte-stability is the seeder's contract ───────────────────────────────────
# app/shared/seeder/tests/test_phase1_regression.py pins (a) no-kwargs == explicit
# defaults and (b) disabled features consume ZERO rng draws. The price resolver must be
# PURE (no rng) and the new generate() parameter must default to None with the legacy
# branch byte-identical. core.py threads it ONLY when config.retail.price_sales_coupling
# is True — mirroring the weather_lookup_for_sales gating pattern (core.py:429-433).

# ── GOTCHA: Decimal vs float ──────────────────────────────────────────────────────────
# base_price / PriceHistory.price are Decimal (Numeric(10,2)); _compute_demand converts
# at line 369 (float((current_price - base_price) / base_price)). The resolver must
# return Decimal (quantized .01 — PriceHistoryGenerator already quantizes at 635-637)
# and the sales row's unit_price must stay Decimal (total_amount = unit_price * quantity
# at 545 multiplies Decimal * int).

# ── GOTCHA: price_history grain & precedence ──────────────────────────────────────────
# Records are chain-wide (store_id=None) for ~90% of products, store-specific for ~10%
# (facts.py:604-608); markdown price records (Phase 2) are appended to the SAME list
# (core.py:403) and may OVERLAP a chain-wide window. Resolver precedence (deterministic):
#   store-specific match  >  chain-wide match;  within a scope, latest valid_from wins
# (markdowns fire later than the base window they cut). valid_to=None == open-ended.
# Days before the first window (shouldn't happen — generator starts at start_date) fall
# back to base_price.

# ── GOTCHA: tests that already isolate price effects ──────────────────────────────────
# Several seeder suites pin OTHER effects with price_elasticity=0.0 (e.g.
# test_phase1_sales_effects.py:44, test_phase2_lifecycle_sales_integration.py:50).
# With coupling ON their demand is unchanged (elasticity 0 → multiplier 1.0) but
# unit_price in emitted rows now varies — any assertion pinned to base_price-derived
# totals must be checked. Tests calling SalesDailyGenerator.generate DIRECTLY (without
# the new kwarg) are byte-identical by construction.

# ── GOTCHA: demo tuning ───────────────────────────────────────────────────────────────
# demo_minimal is tuned to avoid the SPARSE NaN-WAPE trap (RUNBOOKS § make demo).
# Elasticity-driven demand shifts are bounded (±20% price × -0.5 → ≤ ±10% demand), so
# the tuning holds, but Level 4 MUST run `make demo` to confirm green.

# ── GOTCHA: scenarios slice strictness ────────────────────────────────────────────────
# ScenarioAssumptions date fields carry Field(strict=False) (JSON-path policy,
# docs/_base/SECURITY.md). New tests posting JSON bodies follow the existing
# _PRICE_ASSUMPTION dict shape — ISO strings, change_pct as float.

# ── GOTCHA: line endings ──────────────────────────────────────────────────────────────
# The repo has mixed CRLF/LF files. Check `git diff --stat` before committing — a
# whole-file diff on facts.py/core.py means your editor rewrote line endings.
```

## Implementation Blueprint

### Data models and structure

```python
# app/shared/seeder/config.py — RetailPatternConfig (dataclass, beside price_elasticity)
price_sales_coupling: bool = True
# Args docstring: "price_sales_coupling: When True, sales_daily.unit_price follows the
# generated price_history windows (incl. markdowns) and demand responds via
# price_elasticity. When False, legacy behavior: unit_price = base_price always."

# app/shared/seeder/generators/facts.py — pure resolver (NO rng), module level
PriceRecord = dict[str, date | int | Decimal | None]   # the price_history row shape

def build_price_lookup(
    price_records: list[PriceRecord],
) -> dict[tuple[int, int | None], list[tuple[date, date | None, Decimal]]]:
    """Index price records by (product_id, store_id), windows sorted by valid_from."""

def resolve_price(
    lookup: dict[tuple[int, int | None], list[tuple[date, date | None, Decimal]]],
    product_id: int,
    store_id: int,
    day: date,
    base_price: Decimal,
) -> Decimal:
    """Store-specific scope first, then chain-wide (None); within a scope the
    latest-valid_from window covering `day` wins; fall back to base_price."""
```

### List of tasks (dependency order)

```yaml
Task 1 — T1 frame discriminator (scenarios, pure unit test):
  MODIFY app/features/scenarios/tests/test_feature_frame.py:
    - ADD test_scenario_vs_baseline_frame_differs_only_in_price_factor:
        build two frames via assemble_future_frame (same dates/columns/history_tail/
        holiday_dates/launch_date): one with a PriceAssumption(change_pct=-0.15,
        window covering days 3..7 of a 14-day horizon), one with ScenarioAssumptions().
        Assert: for the price_factor column index, cells differ EXACTLY on days 3..7
        (1.0 vs 0.85) and match outside; for EVERY other column index, cells are
        identical (NaN-aware compare: math.isnan(a) and math.isnan(b) counts as equal).
    - MIRROR the import/builder style of test_assemble_future_frame_shape_and_order (186).
  WHY: executable proof of hypothesis-1 falsification — the assumption reaches X_future.

Task 2 — T2 inert-mechanism test (forecasting, pure unit test):
  MODIFY app/features/forecasting/tests/test_models.py:
    - ADD test_regression_constant_price_column_is_inert_to_future_price (class
      TestRegressionForecaster or module style — match the file's existing layout):
        fit RegressionForecaster on synthetic X whose price column is constant 1.0
        (target driven by another column + noise, seeded rng); predict twice on the
        same X_future with price col 1.0 vs 0.60; assert np.array_equal — delta is
        EXACTLY zero. Docstring MUST state this pins issue #237's verdict: a model
        trained on constant price_factor (the pre-fix seeded data) cannot respond to
        price assumptions — the 0.0 delta is zero-learned-elasticity, not lost wiring.
    - ADD the converse: fit on price-elastic synthetic data (price col uniform 0.7-1.1,
      target = 40 - 20*price + noise); assert prediction at price 0.85 differs from 1.0.
  WHY: the discriminating pair — together with Task 1 it IS the reproduction test
       #237 asked for, and it documents the verdict in executable form.

Task 3 — T3 close the regression-delta assertion gap (scenarios, integration):
  MODIFY app/features/scenarios/tests/test_routes_integration.py:
    - In test_regression_baseline_returns_model_exogenous (150-165): after the existing
      method assertion ADD: points length == 14; non-empty disclaimer;
      data["units_delta"] > 0.0  (the conftest bundle at conftest.py:240 is trained
      price-sensitive: target = 40 - 20*price_factor — mirroring the LightGBM twin's
      line 194).
    - ADD test_regression_deeper_cut_moves_at_least_as_much: simulate change_pct=-0.15
      and -0.40 against the same trained_regression_model; assert
      delta(-0.40) >= delta(-0.15) > 0.0   # >= not >: VERIFIED CLAIM #2 (bin clipping)
  WHY: E2E wiring proof for the EXACT model type from the issue's repro.

Task 4 — the fix: seeder price coupling:
  MODIFY app/shared/seeder/config.py:
    - ADD price_sales_coupling: bool = True to RetailPatternConfig (+ Args docstring line).
  MODIFY app/shared/seeder/generators/facts.py:
    - ADD build_price_lookup / resolve_price (pure, NO rng — see Data models).
    - MODIFY SalesDailyGenerator.generate: new keyword-only param
      price_lookup: dict[...] | None = None. In the per-day loop (511-544):
        resolved = resolve_price(price_lookup, product_id, store_id, current_date,
                                 base_price) if price_lookup is not None else None
        pass current_price=resolved   # replaces the hardcoded None at 525
        unit_price = resolved if resolved is not None else base_price   # replaces 544
      PRESERVE everything else byte-for-byte; the None path must not change any rng
      draw or emitted value (test_phase1_regression.py is the watchdog).
  MODIFY app/shared/seeder/core.py:
    - AFTER the markdown merge (403) and BEFORE sales_gen.generate (449): build the
      lookup from price_records when self.config.retail.price_sales_coupling, else None
      (mirror weather_lookup_for_sales gating, 429-433); pass price_lookup=... to
      sales_gen.generate.
  WHY: root-cause fix — truthful unit_price + active elasticity → learnable price signal.

Task 5 — T4/T5 seeder tests:
  MODIFY app/shared/seeder/tests/test_generators.py:
    - ADD resolver unit tests: store-specific beats chain-wide; latest valid_from wins
      on overlap; valid_to=None open-ended; uncovered day → base_price.
    - ADD coupling tests on SalesDailyGenerator.generate:
        (a) with a lookup whose price cuts day D by 20% and price_elasticity=-0.5:
            row(D).unit_price == cut price AND quantity uplift vs a no-lookup run
            (seeded rng twins — same seed, two generators);
        (b) with price_lookup=None: output equals today's byte-for-byte (freeze a
            small golden run in-test: same rng seed, compare full row lists).
    - VERIFY total_amount == unit_price * quantity still holds (existing 229-243
      pattern covers it — extend if the row path changed).
  RUN the full seeder suite; FIX any test that pinned base_price-derived totals with
  coupling implicitly on (prefer setting price_sales_coupling=False in tests that
  isolate OTHER effects — matching their existing price_elasticity=0.0 convention).

Task 6 — T6 seeded end-to-end repro (integration):
  MODIFY app/features/scenarios/tests/test_routes_integration.py (new class
  TestModelExogenousOnSeededData, @pytest.mark.integration):
    - Seed a tiny single-grain dataset DIRECTLY (insert store/product/calendar +
      generate sales via SalesDailyGenerator with a price lookup containing at least
      one multi-week price window — reuse the slice's DB fixtures; do NOT shell out to
      the seeder API), >= _MIN_REGRESSION_TRAIN_ROWS days.
    - POST /forecasting/train {model_type: regression} → run_id;
      POST /scenarios/simulate with a price assumption covering the horizon.
    - ASSERT method == "model_exogenous" and units_delta != 0.0.
    - Idempotency: unique store/product ids (mirror TEST_STORE_ID=990001 convention)
      + teardown deletes — CI shares the Postgres service.
  WHY: the test that fails on pre-fix dev (constant prices) and passes post-fix —
       the issue's repro, automated.

Task 7 — docs + verdict:
  MODIFY docs/DATA-SEEDER.md: paragraph on price_sales_coupling (what it couples, the
    elasticity interaction, why default True, how to disable).
  POST verdict comment on issue #237 (the evidence table from ## What) when the PR
    merges; the PRP file itself is tracked via the standard docs(repo) commit.
```

### Per-task pseudocode (critical details only)

```python
# Task 4 — resolver core (facts.py; pure, deterministic, no rng)
def resolve_price(lookup, product_id, store_id, day, base_price):
    for scope in ((product_id, store_id), (product_id, None)):   # specific → chain
        windows = lookup.get(scope)
        if not windows:
            continue
        # windows sorted by valid_from ASC at build time; scan from the latest so the
        # most recent window covering `day` wins (markdown overlaps cut the base window)
        for valid_from, valid_to, price in reversed(windows):
            if valid_from <= day and (valid_to is None or day <= valid_to):
                return price
    return base_price

# Task 4 — the two-line surgical change in the sales loop (facts.py:521-544)
resolved = (
    resolve_price(price_lookup, product_id, store_id, current_date, base_price)
    if price_lookup is not None else None
)
quantity = self._compute_demand(..., current_price=resolved, ...)   # was: None
...
unit_price = resolved if resolved is not None else base_price        # was: base_price

# Task 6 — the seeded-data signal (make the test data honestly elastic)
# Build sales WITH a lookup so training sees varying price_factor; the price window
# must be long enough (e.g. 3 weeks inside ~120 days) that HistGBR has bins on both
# sides of 1.0. Keep noise low; rely on RetailPatternConfig(price_elasticity=-0.5) default.
```

### Integration Points

```yaml
DATABASE:
  - migration: NONE — no schema change (sales_daily.unit_price already exists; only
    its generated VALUES change)
CONFIG:
  - app/shared/seeder/config.py: RetailPatternConfig.price_sales_coupling: bool = True
    (dataclass field — not an env var; seeder config is request/preset-driven)
ROUTES:
  - NONE — no API surface change
FRONTEND:
  - NONE — the Planner already renders non-zero deltas (heuristic path proves it)
CI:
  - no workflow change; integration tests ride the existing Postgres service job
```

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
# Expected: clean. The resolver's dict-tuple types must be fully annotated (--strict ×2).
```

### Level 2: Unit (no DB)

```bash
# The discriminator pair + frame purity:
uv run pytest -v app/features/forecasting/tests/test_models.py -k "constant_price or elastic"
uv run pytest -v app/features/scenarios/tests/test_feature_frame.py
# Seeder: new resolver/coupling tests AND the untouched byte-stability watchdogs:
uv run pytest -v app/shared/seeder/tests/test_generators.py app/shared/seeder/tests/test_phase1_regression.py
# Then the full unit gate:
uv run pytest -v -m "not integration"
```

### Level 3: Integration (real Postgres)

```bash
docker compose up -d && uv run alembic upgrade head
uv run pytest -v -m integration app/features/scenarios/tests/test_routes_integration.py
uv run pytest -v -m integration app/shared/seeder/tests/
# CAVEAT (memory: integration-suite-shared-state-pollution): run scenario/seeder suites
# against a fresh DB (docker compose down -v first) before trusting failures.
```

### Level 4: End-to-end dogfood (the issue's original repro, inverted)

```bash
docker compose down -v && docker compose up -d && uv run alembic upgrade head
uv run uvicorn app.main:app --port 8123 &   # check no stale uvicorn holds :8123 first
uv run python scripts/seed_random.py --full-new --seed 42 --confirm
# discover a real (store_id, product_id) with sales (seeder does NOT reset sequences):
#   GET /dimensions/stores, /dimensions/products
curl -s -X POST localhost:8123/forecasting/train -H 'content-type: application/json' \
  -d '{"store_id":<S>,"product_id":<P>,"model_type":"regression", ...}'   # → run_id
curl -s -X POST localhost:8123/scenarios/simulate -H 'content-type: application/json' \
  -d '{"run_id":"<run_id>","horizon":14,"assumptions":{"price":{"change_pct":-0.15,
       "start_date":"<T+1>","end_date":"<T+14>"}}}'
# Expected: method=model_exogenous, units_delta != 0.0 (sign per learned elasticity).
make demo   # must stay green (demo_minimal tuning intact)
```

## Final validation Checklist

- [ ] All five gates green: ruff, ruff format, mypy --strict, pyright --strict, pytest unit
- [ ] Integration suites green on a fresh DB (scenarios + seeder + forecasting)
- [ ] T1/T2 discriminator pair passes and is documented as #237's verdict in docstrings
- [ ] T3: regression model_exogenous integration test asserts units_delta > 0.0
- [ ] T6 seeded E2E test passes (and demonstrably fails if coupling is forced off)
- [ ] test_phase1_regression.py passes UNCHANGED (byte-stability + zero-rng watchdogs)
- [ ] Level 4 curl shows non-zero delta; `make demo` green
- [ ] docs/DATA-SEEDER.md updated; verdict comment posted on #237
- [ ] Commits: `test(forecast): …`, `fix(data): …`, `docs(repo): …` — all `(#237)`;
      branch `fix/forecast-model-exogenous-price-inertia` off dev

## Anti-Patterns to Avoid

- ❌ Don't touch `app/features/scenarios/service.py` or `feature_frame.py` production
  code — the wiring is verified sound; "fixing" it would be cargo-culting the symptom.
- ❌ Don't weaken any leakage spec (`test_future_frame_leakage.py`,
  `app/shared/feature_frames/tests/test_leakage.py`, `featuresets/tests/test_leakage.py`).
- ❌ Don't draw rng in the price resolver or change rng draw order/count anywhere in
  the legacy (lookup=None) path — byte-stability is the seeder's contract.
- ❌ Don't assert strict `>` between the −40% and −15% deltas — bin clipping makes
  deep cuts saturate (VERIFIED CLAIM #2); use `>=` with both `> 0`.
- ❌ Don't make T6 shell out to the seeder HTTP API or assume 1-based ids — insert the
  grain directly with unique ids and clean up (CI shares the DB).
- ❌ Don't "fix" the data inconsistency from the consumer side (training joining
  price_history instead of sales_daily.unit_price) — sales rows carrying the actual
  transaction price is the truthful contract; fix the producer.
- ❌ Don't add an API caveat field for zero-delta responses in this PRP — out of scope
  (note it on #237 if reviewers want it; it would be additive schema work).

## Confidence Score

**8/10** for one-pass implementation success.

Strong: the verdict is pre-established with runtime-verified mechanics; the fix reuses
dormant, already-tested machinery (`price_elasticity`, validity-window records); every
test has a named in-repo pattern to mirror; no schema/API surface change.

Residual risk (the −2): the breadth of seeder-suite fallout from coupling-on-by-default
(tests that implicitly pinned constant unit_price totals) is only discoverable by
running the suite — Task 5 budgets for it; and T6's training step needs enough price
variance inside one grain's window for HistGBR to bin on, which the test controls by
constructing the price window explicitly.
