# Exogenous-Regressor Forecasting & Leakage-Safe Future Feature Frames

> Curated reference for **PRP-27 (Scenario Simulation — Full Version)**. ForecastLabAI's
> baseline forecasters (`naive`, `seasonal_naive`, `moving_average`) ignore the exogenous
> `X` argument (every `fit`/`predict` carries `# noqa: ARG002`). The Full Version needs a
> forecaster that *consumes* `X` so a scenario assumption can be expressed as a real
> regressor change instead of a post-forecast multiplier. This doc condenses the parts of
> the LightGBM / scikit-learn / pandas docs that matter for that, plus the leakage rule.

---

## 1. The exogenous-regressor model contract (what to build)

A "regression-on-features" forecaster predicts demand from a **feature row per future
day**, not from the historical target series. The flow:

```
TRAIN:   y, X_hist  ─fit─►  estimator               (X_hist built by featuresets, cutoff-safe)
PREDICT: X_future   ─predict─►  ŷ_future             (X_future = the future feature frame)
```

- `X_hist` is a 2-D array `[n_samples, n_features]` — the columns featuresets already
  produces (`lag_*`, `rolling_*`, calendar, `price_lag_*`, `promo_*`, lifecycle).
- `X_future` is the **same columns** for the horizon days. This is the *future feature
  frame* — the central new artifact of PRP-27.
- The estimator is a gradient-boosted tree regressor (`LGBMRegressor`) — or, to avoid a
  new dependency, scikit-learn's `HistGradientBoostingRegressor` (already in the
  `scikit-learn` dep). **Prefer the scikit-learn option** — see §5.

### scikit-learn `HistGradientBoostingRegressor` (no new dependency)

```python
from sklearn.ensemble import HistGradientBoostingRegressor

est = HistGradientBoostingRegressor(
    max_iter=200, learning_rate=0.05, max_depth=6, random_state=42,
)
est.fit(X_hist, y)            # X_hist: ndarray [n, k]; y: ndarray [n]
y_future = est.predict(X_future)   # X_future: ndarray [horizon, k]
```

- Histogram-based, fast, handles `NaN` natively (important — lag features have `NaN`
  at series start). Deterministic with a fixed `random_state`.
- Docs: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html

### LightGBM `LGBMRegressor` (only if a new dependency is approved)

```python
from lightgbm import LGBMRegressor
est = LGBMRegressor(n_estimators=200, learning_rate=0.05, max_depth=6,
                    random_state=42, n_jobs=1, verbose=-1)
est.fit(X_hist, y)
y_future = est.predict(X_future)
```

- API: https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMRegressor.html
- Set `n_jobs=1` + `random_state` for reproducibility; `verbose=-1` to silence.
- `LightGBMModelConfig` already exists in `forecasting/schemas.py` and
  `forecast_enable_lightgbm` already exists in config — but **LightGBM is NOT in
  `pyproject.toml`** and `model_factory` raises `NotImplementedError`. Adding it is a
  `pyproject.toml` change + a stop-and-ask gate (see PRP-27 § Vision Tensions).

---

## 2. The leakage rule for FUTURE feature frames (the load-bearing part)

`app/features/featuresets/service.py` builds **historical** features and is time-safe by
construction: it filters to `cutoff_date` *before* any compute, lags via `shift(positive)`,
rolls via `shift(1).rolling(...)`, all `groupby` entity-aware. `test_leakage.py` is its spec.

A **future** feature frame is different and dangerous: for horizon day `D` you must
produce the SAME feature columns, but `D` has **no observed target**. The rule:

> **A future feature row for day `D` may only use information available at the forecast
> origin `T` (the last training day) — never an observed value at `D` or later.**

Concretely, for a horizon `T+1 … T+H`:

| Feature family | How to populate the future frame | Leakage trap to avoid |
|----------------|----------------------------------|------------------------|
| `lag_k` (k ≥ horizon) | Real observed `y[T+1-k]` — available at `T`. | — |
| `lag_k` (k < horizon) | **Recursive**: `lag_k` at `T+j` = the model's own prediction `ŷ[T+j-k]`. NEVER a real future `y`. | Using a real `y[T+j-k]` (does not exist) or 0. |
| `rolling_*` | Built from the same `shift(1)`-then-roll over the *extended* (history + predicted) series. | Rolling over un-shifted future values. |
| calendar (`dow`, `month`, `is_weekend`, …) | Pure function of the date `D` — always safe, compute directly. | — |
| `price_lag_*`, `promo_*` | Driven by the **scenario assumptions** — the planner is *positing* a future price/promo. This is the intended what-if input, not leakage. | Reading real future `price_history` rows. |
| `is_holiday` | From the scenario's holiday assumption OR the `calendar` table (a `calendar` row is a timeless attribute, like `launch_date`). | — |
| lifecycle (`days_since_launch`) | Pure function of `D - product.launch_date` — safe. | — |

**Recursive (iterative) forecasting** is the standard technique for multi-step horizons
when lags shorter than the horizon exist: predict `T+1`, append `ŷ[T+1]` to the working
series, recompute lags, predict `T+2`, and so on. Pandas time-series guide:
https://pandas.pydata.org/docs/user_guide/timeseries.html

**Simplification that sidesteps recursion entirely:** if the future feature frame uses
ONLY lags `k ≥ horizon`, calendar features, and assumption-driven exogenous columns, then
every feature value is knowable at `T` with no recursion. PRP-27 recommends this
"long-lag + exogenous + calendar" feature set for the MVP of the Full Version — it keeps
the leakage proof tractable (`test_leakage.py` can assert it directly) and is one-pass
implementable. Recursion is a documented Phase-2 extension.

---

## 3. Why this is leakage-critical for a planner

The MVP (PRP-26) is *immune* to leakage because it never builds a future feature frame —
it multiplies the baseline forecast by a deterministic factor. The Full Version
*introduces* the future feature frame, so it introduces the leakage surface the MVP did
not have. PRP-27 therefore ships a NEW load-bearing test
`app/features/scenarios/tests/test_leakage.py` extension (or a sibling
`test_future_frame_leakage.py`) that asserts the future-frame generator never reads an
observed target at or after the forecast origin. This mirrors
`app/features/featuresets/tests/test_leakage.py` — never weaken it to make a feature pass.

---

## 4. Multi-scenario comparison (UX + math)

Comparing N scenarios against one baseline is an aggregation over N `ScenarioComparison`
objects:

- Each scenario contributes one `(units_delta, revenue_delta, coverage_verdict)` triple.
- The comparison view ranks scenarios by a chosen metric (revenue delta default) and
  renders all series on one chart (baseline + one line per scenario).
- Recharts renders M+1 `<Line>` series from one merged row array keyed by date —
  `frontend/src/components/charts/time-series-chart.tsx` currently wraps a 2-series case;
  a multi-series variant passes a `series: {key,label,color}[]` prop. Recharts LineChart:
  https://recharts.org/en-US/api/LineChart
- TanStack Query: the comparison page issues one query per saved scenario id (or one
  batch endpoint). Mutations vs queries pattern:
  https://tanstack.com/query/latest/docs/framework/react/guides/mutations

---

## 5. Recommendation for PRP-27 (de-risking)

1. **Prefer `HistGradientBoostingRegressor`** over LightGBM — it is already a transitive
   dependency via `scikit-learn`, so no `pyproject.toml` change and no stop-and-ask gate.
   It is deterministic, NaN-tolerant, and fast enough for single-series horizons.
2. **Use the long-lag + calendar + exogenous feature set** so the future frame needs no
   recursion — the leakage proof stays simple and the PRP stays one-pass implementable.
3. **Keep `method` forward-compatible** — the MVP locked `method="heuristic"` behind a
   CHECK constraint. The Full Version adds `method="model_exogenous"`; the migration must
   widen the CHECK to `IN ('heuristic','model_exogenous')`.
4. **Never replace the heuristic path** — it stays as the fallback when a baseline model
   does not support exogenous features. A scenario result always declares which `method`
   produced it, and the heuristic disclaimer stays on heuristic results.

---

## Source URLs (with the sections that matter)

- scikit-learn `HistGradientBoostingRegressor` — fit/predict, NaN handling, `random_state`:
  https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html
- scikit-learn `TimeSeriesSplit` — for any backtest of the exogenous model:
  https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- LightGBM `LGBMRegressor` Python API — only if the dependency is approved:
  https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMRegressor.html
- pandas time-series user guide — date ranges, shifting, rolling for the future frame:
  https://pandas.pydata.org/docs/user_guide/timeseries.html
- Recharts LineChart — multi-series scenario comparison chart:
  https://recharts.org/en-US/api/LineChart
- NIST AI Risk Management Framework — transparency controls for model-driven revenue
  claims (the `disclaimer` / `method` labelling requirement):
  https://www.nist.gov/itl/ai-risk-management-framework
