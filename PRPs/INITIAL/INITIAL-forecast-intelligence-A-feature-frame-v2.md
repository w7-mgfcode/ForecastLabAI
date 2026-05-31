# INITIAL-forecast-intelligence-A-feature-frame-v2.md - Forecast Intelligence A: Feature Frame V2

## FEATURE:

Create ForecastLabAI's second-generation feature-aware forecasting frame.

This slice expands the existing 14-column canonical feature frame into a richer, leakage-safe retail-demand feature contract that can support better historical forecasting across multiple levels:

- weekly seasonality
- monthly patterns
- yearly seasonality
- recent rolling demand level
- medium-term trend
- price and promotion effects
- stockout-aware demand signals
- product lifecycle signals
- replenishment cadence
- returns signals
- exogenous weather and macro signals

Current repo state:

- `app/shared/feature_frames/contract.py` is the single source of truth for feature-aware forecasting columns.
- Current canonical columns are `lag_1`, `lag_7`, `lag_14`, `lag_28`, calendar cyclic columns, `price_factor`, `promo_active`, `is_holiday`, and `days_since_launch`.
- `app/features/forecasting/service.py` builds historical feature rows for feature-aware models.
- `app/shared/feature_frames/rows.py` builds historical and future feature rows.
- `app/features/featuresets/service.py` already has broader feature engineering families, including lag, rolling, calendar, exogenous, lifecycle, promotion, and replenishment. This PRP should reuse concepts without creating forbidden cross-slice imports.
- `app/features/featuresets/tests/test_leakage.py` and `app/features/forecasting/tests/test_regression_features_leakage.py` are load-bearing leakage specs.

Problem:

The app already has feature-aware models, but the forecast-facing feature frame is still too small for retail demand planning. It can learn simple lags, calendar effects, price, promotion, holiday, and product age, but it does not yet expose the richer signals discussed in the brainstorming:

- explicit yearly lookback such as `lag_364` or `same_week_last_year`
- rolling averages such as `rolling_mean_7`, `rolling_mean_28`, `rolling_mean_90`
- trend features such as `trend_30`, `trend_90`, and recent-vs-prior rolling ratios
- stockout features such as `stockout_days_7`, `stockout_days_28`, and `inventory_available_ratio_28`
- richer lifecycle features such as lifecycle stage, discontinued flag, and days to/from discontinuation
- replenishment features such as days since last replenishment and replenishment count in a trailing window
- returns features such as returns rate over trailing windows
- weather and macro exogenous signals from `exogenous_signal`
- markdown and bundle promotion signals where they are safely available

Goals:

- Introduce a versioned Feature Frame V2 contract under `app/shared/feature_frames`.
- Keep Feature Frame V1 compatible for existing model bundles and registry artifacts.
- Add a feature-frame version identifier to model metadata/config where needed.
- Add safe column taxonomy for every new feature:
  - safe calendar/static feature
  - conditionally safe historical target feature
  - unsafe unless supplied for future horizon
  - observed-only training feature that must not be inferred at prediction time
- Add pure builders for V2 historical rows and future rows.
- Add DB loader plumbing in the forecasting slice to collect the required sidecar data without importing sibling feature services.
- Preserve strict no-leakage rules:
  - no future target values in future frames
  - rolling features use history up to origin only
  - stockout and inventory features use data knowable at or before origin unless explicitly supplied as a scenario assumption
  - future price and promotion are only allowed when supplied by a caller as planned assumptions
- Add tests that prove the new feature families are leakage-safe and aligned column-for-column between training, backtesting, scenarios, and prediction.

Recommended V2 feature groups:

1. Target history:
   - `lag_1`, `lag_7`, `lag_14`, `lag_28`
   - `lag_56`
   - `lag_364` or `lag_365` with an explicit retail-calendar decision
   - `same_dow_mean_4`
   - `same_dow_mean_8`

2. Rolling demand level:
   - `rolling_mean_7`
   - `rolling_mean_28`
   - `rolling_mean_90`
   - `rolling_median_28`
   - `rolling_std_28`

3. Trend:
   - `trend_30`
   - `trend_90`
   - `rolling_mean_7_vs_28`
   - `rolling_mean_28_vs_prev_28`

4. Calendar:
   - keep `dow_sin`, `dow_cos`, `month_sin`, `month_cos`, `is_weekend`, `is_month_end`
   - consider `week_of_year_sin`, `week_of_year_cos`
   - consider `day_of_month_sin`, `day_of_month_cos`

5. Price and promotion:
   - keep `price_factor`
   - keep `promo_active`
   - add `promo_discount_pct`
   - add `promo_kind_markdown_active`
   - add `promo_kind_bundle_active`

6. Inventory and stockout:
   - `is_stockout_lag1`
   - `stockout_days_7`
   - `stockout_days_28`
   - `inventory_available_ratio_28`
   - optional `lost_sales_proxy_28` if defensible and documented as a proxy, not true demand

7. Lifecycle:
   - keep `days_since_launch`
   - add `is_new_product`
   - add `is_mature_product`
   - add `is_discontinued`
   - add `days_until_discontinue` where known

8. Replenishment:
   - `days_since_last_replenishment`
   - `replenishment_count_14`
   - `replenishment_qty_28`

9. Returns:
   - `returns_qty_7`
   - `returns_qty_28`
   - `returns_rate_28`

10. Exogenous:
   - weather feature set from `exogenous_signal` where local/store-specific signals exist
   - macro feature set where global signals exist
   - all future exogenous values must be explicit assumptions or calendar-known facts

Out of scope:

- Adding new ML model classes. That belongs to Forecast Intelligence B.
- Frontend controls. That belongs to Forecast Intelligence C.
- Replacing the existing `featuresets` slice.
- Adding unmanaged cloud services.
- Using direct SQL string concatenation.
- Weakening leakage tests.

Success criteria:

- Existing feature-aware models can continue using V1 bundles.
- New training requests can select or default into V2 where appropriate.
- V2 feature columns are stable, versioned, and persisted in model metadata.
- Backtesting and scenario future frames can reproduce the exact column order.
- Unit and integration tests prove V2 does not leak future target values.

## EXAMPLES:

Reference existing repo examples and patterns:

- `app/shared/feature_frames/contract.py`
  - Existing V1 single source of truth for canonical feature columns and safety classification.

- `app/shared/feature_frames/rows.py`
  - Existing pure row builders for historical and future feature frames.

- `app/features/forecasting/service.py`
  - Existing `_build_regression_features` loader and model training path.

- `app/features/featuresets/service.py`
  - Existing time-safe lag, rolling, calendar, exogenous, lifecycle, promotion, and replenishment compute patterns.

- `app/features/featuresets/tests/test_leakage.py`
  - The leakage test style to mirror. Do not weaken these tests.

- `app/features/forecasting/tests/test_regression_features_leakage.py`
  - Existing forecasting-specific leakage guard.

- `app/features/scenarios/feature_frame.py`
  - Future feature frame construction for scenario simulation and `model_exogenous`.

- `app/features/backtesting/service.py`
  - Fold-level feature construction and evaluation path must stay time-safe.

- `docs/DATA-SEEDER.md`
  - Describes stockouts, exogenous signals, returns, markdowns, bundles, and replenishment data generated by the seeder.

- `docs/_base/DOMAIN_MODEL.md`
  - Existing domain language for `model_exogenous`, replenishment events, and scenario methods.

Potential example artifact to add:

- `examples/forecasting/feature_frame_v2_preview.py`
  - Read one `(store_id, product_id)` series and print V1 vs V2 feature columns, null counts, and sample rows up to a cutoff.
  - This should be read-only and local-development only.

## DOCUMENTATION:

External references to review during PRP creation and implementation:

- scikit-learn lagged features example: https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html
- scikit-learn time-related/cyclical feature engineering: https://sklearn.org/stable/auto_examples/applications/plot_cyclical_feature_engineering.html
- scikit-learn TimeSeriesSplit: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- Darts covariates guide, for past vs future covariate terminology: https://unit8co.github.io/darts/userguide/covariates.html
- Prophet seasonality, holidays, and regressors, for additive component vocabulary: https://facebook.github.io/prophet/docs/seasonality%2C_holiday_effects%2C_and_regressors.html
- LightGBM LGBMRegressor API, for feature-aware tree model compatibility: https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.LGBMRegressor.html
- XGBoost Python API: https://xgboost.readthedocs.io/en/stable/python/
- pandas time series user guide: https://pandas.pydata.org/docs/user_guide/timeseries.html

Internal docs to review:

- `docs/optional-features/05-advanced-ml-model-zoo.md`
- `docs/optional-features/10-baseforecaster-feature-contract.md`
- `docs/optional-features/11-feature-aware-predict-serving.md`
- `docs/PHASE/3-FEATURE_ENGINEERING.md`
- `docs/PHASE/4-FORECASTING.md`
- `docs/DATA-SEEDER.md`
- `docs/_base/ARCHITECTURE.md`
- `docs/_base/RULES.md`

## OTHER CONSIDERATIONS:

Implementation constraints:

- Keep `app/shared/feature_frames` leaf-level. It must not import from `app/features/**`.
- Do not make the canonical feature list horizon-dependent.
- Do not silently fill missing future exogenous inputs with zero if that changes business meaning.
- Do not read future target values to compute future rolling, trend, or lag features.
- Keep V1/V2 compatibility explicit so older artifacts remain loadable.
- Use Pydantic v2 strict schemas for any new request config.
- If DB sidecar loading is required, keep it in the forecasting/backtesting/scenarios services, not in `app/shared`.
- Avoid large abstractions unless they remove real duplication across forecasting, backtesting, and scenarios.

Testing requirements:

- Add pure unit tests for each V2 feature group.
- Add leakage regression tests for rolling, trend, yearly lag, stockout, replenishment, returns, and exogenous signals.
- Add tests that V2 future frames emit `NaN` or reject when a feature cannot be known at the forecast origin.
- Add metadata tests proving V2 model bundles persist `feature_frame_version` and column order.
- Add route/service tests for training a V2 feature-aware model.
- Keep all existing baseline model tests green.

Open design decisions for the PRP:

- Use `lag_364` or `lag_365` for "same weekday last year". Retail daily data often benefits from `364` because it preserves day-of-week alignment.
- Decide whether rolling features are recursively updated for multi-day horizon or remain origin-fixed. The safer MVP is origin-fixed or `NaN` when unknown.
- Decide whether stockout correction is a feature only or also adjusts the target. MVP should use features only; target rewriting needs a separate explicit design.
- Decide whether Phase 2 exogenous signals are included in V2 MVP or exposed as optional feature groups.
- Decide how the UI will label V2 feature groups later, so metadata should include group names and safety classes.

Recommended validation commands:

```bash
uv run ruff check app/shared app/features/forecasting app/features/backtesting app/features/scenarios
uv run ruff format --check app/shared app/features/forecasting app/features/backtesting app/features/scenarios
uv run mypy app/
uv run pyright app/
uv run pytest -v app/features/forecasting/tests app/features/backtesting/tests app/features/scenarios/tests app/features/featuresets/tests/test_leakage.py -m "not integration"
```
