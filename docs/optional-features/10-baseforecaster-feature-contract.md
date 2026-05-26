# BaseForecaster Feature Contract

## Summary

Formalize the existing `BaseForecaster` interface as the canonical model contract for both target-only baseline models and feature-aware ML models. Add a `requires_features` class attribute or property so services can branch on model capability without `isinstance` checks or a new `FeatureAwareForecaster` subclass.

This is a small but important foundation item for the Advanced ML Model Zoo.

## Why It Fits ForecastLabAI

ForecastLabAI already has a forecasting model interface where models expose:

- `fit(y, X=None)`
- `predict(horizon, X=None)`

Baseline models can ignore `X`; regression and future advanced models need `X`. Introducing a second base class too early would create inheritance churn without solving the harder platform problems: feature-frame contracts, future feature availability, leakage safety, and train/serve skew.

## User Value

- Keeps current baseline behavior stable.
- Makes feature-aware model support explicit.
- Prepares LightGBM/XGBoost/Prophet-like work without API churn.
- Avoids brittle `isinstance` checks in services.
- Reduces persistence risk for existing joblib model bundles.

## Proposed Design

Keep `BaseForecaster` as the single canonical model interface.

Add a class-level capability flag:

```python
requires_features: ClassVar[bool] = False
```

Baseline models:

```python
class NaiveForecaster(BaseForecaster):
    requires_features = False
```

Feature-aware models:

```python
class RegressionForecaster(BaseForecaster):
    requires_features = True
```

Service code branches on the model contract:

```python
if model.requires_features:
    # require and validate X / X_future
else:
    # y-only baseline path
```

## Backend Design

Likely files:

- `app/features/forecasting/models.py`
- `app/features/forecasting/service.py`
- `app/features/forecasting/tests/test_models.py`
- `examples/models/model_interface.md`
- `docs/PHASE/4-FORECASTING.md`

The change should document that:

- `fit(y, X=None)` is the universal train contract.
- `predict(horizon, X=None)` is the universal predict contract.
- `requires_features = False` models may ignore `X`.
- `requires_features = True` models must receive valid feature frames.
- A `FeatureAwareForecaster` subclass should be revisited only after multiple advanced model families need shared behavior beyond the flag.

## MVP Scope

- Add `requires_features` to the model interface.
- Set it explicitly on existing baseline and regression models.
- Update service branching where it currently relies on model type checks.
- Add tests proving baseline models ignore `X` and regression requires it.
- Update model interface documentation.

## Full Version

- Add richer capability flags if needed:
  - `supports_prediction_intervals`
  - `supports_feature_importance`
  - `supports_exogenous_future`
  - `supports_recursive_prediction`
- Introduce a `FeatureAwareForecaster` subclass only when shared advanced-model behavior justifies the abstraction.

## Risks

- Adding a flag without tests can become another implicit contract.
- Service code must not silently pass `None` into feature-aware models.
- Documentation must be precise so future LightGBM work does not reinterpret the contract.

## Validation Plan

- Unit tests for each existing model's `requires_features` value.
- Unit tests proving baseline models still fit/predict with `X=None`.
- Unit tests proving feature-aware models reject missing required features.
- Regression tests for existing forecasting service behavior.
- `uv run pytest -q -m "not integration"`
- `uv run ruff check app tests`

## Documentation

- scikit-learn estimator development guide: https://scikit-learn.org/stable/developers/develop.html
- scikit-learn Pipeline composition: https://scikit-learn.org/stable/modules/compose.html
- scikit-learn model persistence: https://scikit-learn.org/stable/model_persistence.html
- Joblib persistence documentation: https://joblib.readthedocs.io/en/stable/persistence.html
- Pydantic documentation: https://docs.pydantic.dev/latest/

## V2 Feature Contract (PRP-35 — opt-in)

Starting with PRP-35 the feature-frame contract is versioned. V1 (the 14-column manifest documented above) remains the default and the back-compat path; V2 is an opt-in richer manifest reachable via `TrainRequest.feature_frame_version=2`.

**Pinned V2 constants** (`app/shared/feature_frames/contract_v2.py`):
- `EXOGENOUS_LAGS_V2 = (1, 7, 14, 28, 56, 364)` — `lag_364` (not `lag_365`) preserves day-of-week.
- `ROLLING_WINDOWS_V2 = (7, 28, 90)` — leakage-safe via `shift(1).rolling(window)` semantics (`s[i-window..i-1]` for row `i`).
- `TREND_WINDOWS_V2 = (30, 90)` — `numpy.polyfit(deg=1)` slope over the trailing window.
- `HISTORY_TAIL_DAYS_V2 = 400` — comfortably exceeds `lag_364`.

**Feature groups** (`FeatureGroup` enum) — every V2 column belongs to exactly one group; group enablement decides emission. The default `feature_groups=None` resolves to the MVP-green default:

| Group | Default | Columns (example) |
|-------|---------|-------------------|
| `target_history` | ✅ | `lag_1`, `lag_7`, …, `lag_364`, `same_dow_mean_4`, `same_dow_mean_8` |
| `calendar` | ✅ | V1 calendar + `week_of_year_sin/cos`, `day_of_month_sin/cos`, `is_holiday` |
| `rolling` | ✅ | `rolling_mean_7/28/90`, `rolling_median_28`, `rolling_std_28` |
| `trend` | ✅ | `trend_30`, `trend_90`, `rolling_mean_7_vs_28`, `rolling_mean_28_vs_prev_28` |
| `price_promo` | ✅ | V1 price + `promo_discount_pct`, `promo_kind_markdown_active`, `promo_kind_bundle_active` |
| `lifecycle` | ✅ | V1 `days_since_launch` + `is_new_product`, `is_mature_product`, `is_discontinued`, `days_until_discontinue` |
| `inventory` | opt-in | `is_stockout_lag1`, `stockout_days_7/28`, `inventory_available_ratio_28` |
| `replenishment` | opt-in | `days_since_last_replenishment`, `replenishment_count_14`, `replenishment_qty_28` |
| `returns` | opt-in | `returns_qty_7/28`, `returns_rate_28` |
| `exogenous_weather` | opt-in | `exo_weather_temp_c`, `exo_weather_precip_mm` |
| `exogenous_macro` | opt-in | `exo_macro_index` |

**Safety classification** — every V2 column carries a `FeatureSafety` class (`SAFE` / `CONDITIONALLY_SAFE` / `UNSAFE_UNLESS_SUPPLIED`). Persisted into bundle metadata via `v2_feature_safety_classes` so the dashboard can surface the leakage class per column.

**Leakage spec** — the V2 builders obey the same rule as V1: a horizon day reads only information knowable at the forecast origin `T`. The load-bearing specs are `app/shared/feature_frames/tests/test_leakage_v2.py` (cross-cutting) and `app/features/forecasting/tests/test_regression_features_v2_leakage.py` (slice-layer). Both must stay green; neither may be weakened.

**Bundle metadata (additive)** — a V2 bundle's `metadata` dict adds:
- `feature_frame_version: 2`
- `feature_groups: {group_name: [columns]}`
- `feature_safety_classes: {column: safety.value}`
- `feature_pinned_constants: {...}` — reproducibility audit snapshot

V1 bundles default to `metadata.get("feature_frame_version", 1)` at load; the V1 byte-stable path remains the default code path.

**Preview script**: `uv run python examples/forecasting/feature_frame_v2_preview.py --store-id 15 --product-id 52 --cutoff-date 2025-12-31` dumps V1 + V2 columns + per-group NaN counts side by side.

