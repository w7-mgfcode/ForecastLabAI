# Feature-Frame Contract

The contract a **feature-aware** forecasting model (the regression forecaster
today; LightGBM / XGBoost / Prophet-like models in the MLZOO sequence) stands
on. The single source of truth in code is
[`app/shared/feature_frames`](../../app/shared/feature_frames/) — the pinned
constants, the canonical column set and order, the `FutureFeatureFrame`
carrier, the leakage-safe pure builders, and the `FeatureSafety` taxonomy.

A feature-aware model consumes **two** matrices with the *same columns in the
same order*:

| Frame | Built by | Shape | Rows |
|-------|----------|-------|------|
| Historical training frame | `ForecastingService._build_regression_features` → `_assemble_regression_rows` | `[n_observations, n_features]` | observed days in `[train_start, train_end]` |
| Future prediction frame | `app/features/scenarios/feature_frame.build_future_frame` → `assemble_future_frame` | `[horizon, n_features]` | the horizon days `T+1 … T+horizon` |

`T` is the **forecast origin** — the last training day (`train_end`).

## Historical training frame

- One row per observed day in the SQL window `WHERE date >= train_start AND
  date <= train_end`. **That `date <= train_end` filter IS the cutoff guard** —
  no row can be assembled for a day after the origin `T`.
- `lag_k` at row `i` reads `quantity[i - k]` — a strictly earlier observation —
  or `NaN` when `i < k` (no source day exists yet).
- Calendar columns are pure functions of the row's date.
- `price_factor` / `promo_active` / `is_holiday` / `days_since_launch` read the
  row's **same-day** observed attributes — never a future day.
- Spec: [`test_regression_features_leakage.py`](../../app/features/forecasting/tests/test_regression_features_leakage.py)
  (load-bearing — sequential targets make any leakage mathematically detectable).

## Future prediction frame

- One row per horizon day `T+1 … T+horizon`.
- `lag_k` at horizon day `j` reads `history_tail[(j-1) - k]` **only when
  `(j-1)-k < 0`** — i.e. the source day lies at or before the origin `T` and is
  therefore inside the observed history tail. When `(j-1)-k >= 0` the source day
  is itself a future horizon day with no observed target, so the cell is `NaN`.
  **There is no recursion in v1** — a `NaN` lag is never back-filled with a
  prediction.
- Calendar columns are pure functions of the horizon date.
- `price_factor` / `promo_active` are knowable for a future day **only because
  the caller posits them** (a scenario assumption); `is_holiday` and
  `days_since_launch` are timeless date attributes.
- Spec: [`app/shared/feature_frames/tests/test_leakage.py`](../../app/shared/feature_frames/tests/test_leakage.py)
  (the shared pure builders) and
  [`app/features/scenarios/tests/test_future_frame_leakage.py`](../../app/features/scenarios/tests/test_future_frame_leakage.py)
  (the assumption-driven columns + the assembled frame).

## The canonical column set

`canonical_feature_columns()` returns these **14 columns, in this order**:

```
lag_1, lag_7, lag_14, lag_28,
dow_sin, dow_cos, month_sin, month_cos, is_weekend, is_month_end,
price_factor, promo_active, is_holiday, days_since_launch
```

The set is deliberately **fixed** (not horizon-dependent): for a long horizon
some lag columns are mostly `NaN`, which a NaN-tolerant estimator handles — far
safer than a column set that changes shape with the horizon. The trained model
bundle persists exactly this list in its metadata; the future frame reproduces
it column-for-column.

Pinned constants: `EXOGENOUS_LAGS = (1, 7, 14, 28)`, `HISTORY_TAIL_DAYS = 90`
(the observed-target tail length persisted in the bundle so the future frame
can resolve the longest lag).

## Feature-class taxonomy

Every column carries a `FeatureSafety` class (see `FEATURE_CLASS` /
`feature_safety()` in `app/shared/feature_frames`). This is the executable form
of the feature-family table in
[`PRPs/ai_docs/exogenous-regressor-forecasting.md`](../../PRPs/ai_docs/exogenous-regressor-forecasting.md) §2.

| Column | Class | How to populate a future day — and the leakage trap |
|--------|-------|------------------------------------------------------|
| `lag_1`, `lag_7`, `lag_14`, `lag_28` | `CONDITIONALLY_SAFE` | Read `history_tail` only when the source day `<= T`; otherwise `NaN`. **Trap:** filling a future-sourced lag with a prediction (recursion) or a fabricated value. |
| `dow_sin`, `dow_cos`, `month_sin`, `month_cos`, `is_weekend`, `is_month_end` | `SAFE` | Pure function of the date — compute directly. No trap: a calendar feature cannot leak the target. |
| `is_holiday` | `SAFE` | The `calendar` table is a timeless attribute; reading a horizon day's holiday flag is not leakage. |
| `days_since_launch` | `SAFE` | `(date - launch_date).days` — a pure function of the date once the launch date is known. `NaN` when the product has no launch date. |
| `price_factor` | `UNSAFE_UNLESS_SUPPLIED` | Knowable for a future day **only** if the caller posits it (a price assumption). Never inferred from observed data. Default `1.0` (no change). |
| `promo_active` | `UNSAFE_UNLESS_SUPPLIED` | Knowable for a future day **only** if the caller posits a promotion. Default `0.0` (no promotion). |

## The NaN-as-unknown rule

A builder emits `math.nan` for a cell whose source is **genuinely unknowable**
at origin `T` — a long-lag whose source day lies in the horizon, or
`days_since_launch` for a product with no launch date. `NaN` means *unknown*; it
is never silently replaced with a fabricated default such as `0.0`.

`HistGradientBoostingRegressor` tolerates `NaN` natively. A future model that is
**not** NaN-tolerant must impute explicitly inside its own `fit`/`predict` — the
shared frame builders must not impute on its behalf.

## How a future advanced model plugs in

A new feature-aware model (PRP-MLZOO-B onward):

1. Subclasses `BaseForecaster` and sets `requires_features: ClassVar[bool] = True`.
   `ForecastingService.train_model` / `predict` branch on this flag — no
   `isinstance` check, no `model_type` string comparison.
2. Reuses the **shared** frame builders and `canonical_feature_columns()` — it
   writes **zero** new contract code, so it cannot drift from the regression
   contract.
3. Consumes the historical frame for `fit(y, X)` and (via
   `POST /scenarios/simulate`) the future frame for `predict(horizon, X)`.

Known limitation: **backtesting is not wired for feature-aware models.** The
backtest fold loop calls `model.fit(y_train)` target-only; a feature-aware model
raises `ValueError` there — a loud, non-leaky failure, pinned by
`test_feature_aware_model_fails_loud_in_backtest`. Feature-aware backtesting is
PRP-MLZOO-B scope.
