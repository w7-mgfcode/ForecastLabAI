# INITIAL-forecast-intelligence-index.md - Forecast Intelligence Roadmap

## FEATURE:

Split the Forecast Intelligence upgrade into three PRP-ready INITIAL briefs.

This roadmap captures the full extended context from the forecasting brainstorming:

- The current app already has basic and advanced model families.
- The current app does not yet use enough multi-level historical signals for high-quality retail forecasting.
- The desired direction is feature-aware forecasting that can learn from:
  - weekly seasonality
  - monthly patterns
  - yearly seasonality
  - rolling averages
  - demand trend
  - price effects
  - promotion effects
  - stockout and inventory signals
  - lifecycle signals
  - replenishment cadence
  - returns
  - weather and macro exogenous signals
- The desired UI direction is an interactive Forecast Lab where users can choose, vary, compare, and promote models safely.

Current repo evidence:

- Forecasting models exist in `app/features/forecasting/models.py`.
- Model configs exist in `app/features/forecasting/schemas.py`.
- Feature-aware training uses `ForecastingService._build_regression_features`.
- The feature-aware frame contract lives in `app/shared/feature_frames`.
- Scenario simulation uses `model_exogenous` for feature-aware re-forecasting.
- Backtesting, registry, ops/model health, explainability, batch, and frontend pages already exist.

Important clarification:

ForecastLabAI does not need a "start from zero" model zoo PRP. It needs an upgrade sequence that preserves existing behavior while expanding the feature signal, comparison rigor, and UI workflow.

Recommended PRP sequence:

| Order | INITIAL | Purpose |
| --- | --- | --- |
| 1 | `INITIAL-forecast-intelligence-A-feature-frame-v2.md` | Expand the leakage-safe feature frame to include rolling, trend, yearly, stockout, lifecycle, replenishment, returns, and exogenous signals. |
| 2 | `INITIAL-forecast-intelligence-B-model-zoo-backtesting.md` | Add stronger baseline variants, improve feature-aware model/backtest/registry comparison, and make champion/challenger logic metric-aware. |
| 3 | `INITIAL-forecast-intelligence-C-interactive-ui.md` | Build the UI controls, comparison surfaces, what-if variations, model health explanations, and safe promote workflow. |

Dependency graph:

```text
A. Feature Frame V2
  -> B. Model Zoo and Backtesting
      -> C. Interactive UI and Operator Workflow
```

Parallelism:

- C can start with design and existing-field UI planning, but implementation should wait for A/B response contracts.
- B can add new target-only baselines before A lands, but any V2 feature-aware work should wait for A.
- A must land before any model relies on V2 columns.

Full extended context:

The desired forecasting system should move beyond a single rule such as `seasonal_naive`, where tomorrow is copied from seven days ago. It should let the app reason over several historical layers at once:

```text
forecast =
  weekly seasonality
  + monthly pattern
  + yearly seasonality
  + recent rolling demand level
  + medium-term trend
  + price effect
  + promotion effect
  + stockout/inventory correction signal
  + lifecycle signal
  + replenishment/returns/exogenous signals
```

The current app already supports:

- weekly seasonality through `seasonal_naive`, `lag_7`, and day-of-week features
- monthly calendar features through month sin/cos and month-end
- price through `price_factor`
- promotion through `promo_active`
- holiday through `is_holiday`
- product age through `days_since_launch`
- feature-aware models through `regression`, `prophet_like`, optional `lightgbm`, and optional `xgboost`

The important gaps are:

- no explicit yearly lag such as `lag_364` / same-week-last-year
- no forecast-facing rolling averages such as `rolling_mean_7`, `rolling_mean_28`, `rolling_mean_90`
- no explicit trend features such as `trend_30`, `trend_90`, recent-vs-prior ratios
- no model-consumed stockout/inventory correction features
- no model-consumed replenishment, returns, weather, or macro signals
- no stronger baseline variants such as weighted moving average or seasonal average
- no UI-level feature-pack selection
- no easy interactive model comparison across simple vs feature-aware models
- no guardrail that explains "newer run" vs "better run" before promotion

Brainstormed improvements:

- Feature packs:
  - Basic history
  - Rolling demand
  - Trend
  - Yearly seasonality
  - Price/promotion
  - Stockout/inventory
  - Lifecycle
  - Replenishment/returns
  - Exogenous weather/macro

- Better baselines:
  - weighted moving average
  - seasonal average over last N matching weekdays
  - target/calendar trend regression

- Better feature-aware models:
  - richer `regression`
  - richer `prophet_like`
  - optional `random_forest`
  - existing optional `lightgbm` and `xgboost`

- Better model health:
  - classify drift from comparable successful runs
  - show WAPE deltas with enough context
  - distinguish freshness from quality
  - make Promote confirm metric regression

- Better UI:
  - model family segmented control
  - model type select
  - feature-frame selector
  - feature-pack toggles
  - price/promo/inventory/lifecycle what-if controls
  - side-by-side model comparison
  - run detail feature importance and artifact verification
  - batch presets for model sweeps
  - RAG/agent actions to explain model degradation

## EXAMPLES:

Read these before creating PRPs from this roadmap:

- `PRPs/INITIAL/INITIAL-forecast-intelligence-A-feature-frame-v2.md`
- `PRPs/INITIAL/INITIAL-forecast-intelligence-B-model-zoo-backtesting.md`
- `PRPs/INITIAL/INITIAL-forecast-intelligence-C-interactive-ui.md`
- `PRPs/INITIAL/INITIAL-MLZOO-index.md`
- `PRPs/INITIAL/INITIAL-MLZOO-A-foundation-feature-frames.md`
- `PRPs/INITIAL/INITIAL-MLZOO-B.2-feature-aware-backtesting.md`
- `PRPs/INITIAL/INITIAL-MLZOO-D-frontend-registry-explainability.md`
- `docs/optional-features/05-advanced-ml-model-zoo.md`
- `docs/optional-features/10-baseforecaster-feature-contract.md`
- `docs/optional-features/11-feature-aware-predict-serving.md`
- `app/shared/feature_frames/contract.py`
- `app/shared/feature_frames/rows.py`
- `app/features/forecasting/models.py`
- `app/features/forecasting/service.py`
- `app/features/backtesting/service.py`
- `app/features/scenarios/feature_frame.py`
- `frontend/src/pages/visualize/forecast.tsx`
- `frontend/src/pages/visualize/backtest.tsx`
- `frontend/src/pages/visualize/planner.tsx`
- `frontend/src/pages/explorer/run-detail.tsx`
- `frontend/src/pages/ops.tsx`

## DOCUMENTATION:

External references:

- scikit-learn lagged features with gradient boosting: https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html
- scikit-learn cyclical/time-related feature engineering: https://sklearn.org/stable/auto_examples/applications/plot_cyclical_feature_engineering.html
- scikit-learn TimeSeriesSplit: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- scikit-learn RandomForestRegressor: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html
- LightGBM LGBMRegressor: https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.LGBMRegressor.html
- XGBoost Python API: https://xgboost.readthedocs.io/en/stable/python/
- Prophet seasonality, holidays, and regressors: https://facebook.github.io/prophet/docs/seasonality%2C_holiday_effects%2C_and_regressors.html
- Darts covariates guide: https://unit8co.github.io/darts/userguide/covariates.html
- Nixtla StatsForecast model docs: https://nixtlaverse.nixtla.io/statsforecast/src/core/models.html
- shadcn/ui docs: https://ui.shadcn.com/docs
- TanStack Query docs: https://tanstack.com/query/latest
- TanStack Table docs: https://tanstack.com/table/latest
- Recharts docs: https://recharts.org/en-US/

## OTHER CONSIDERATIONS:

Global constraints:

- Preserve the vertical-slice architecture.
- Do not import one feature slice's service directly from another slice; use `app/shared` or lazy imports where the repo already uses that pattern.
- Do not weaken leakage tests.
- Do not add managed-cloud SDKs.
- Do not add heavy optional ML dependencies to the core install path.
- Keep feature-frame versions explicit for old artifact compatibility.
- Keep UI implementation consistent with existing shadcn/TanStack/Recharts patterns.
- Keep every PRP reviewable; do not combine A, B, and C into one implementation branch.

Recommended execution:

1. Generate a PRP from A first.
2. Implement and merge A.
3. Generate B, adjusting to the actual A result.
4. Implement and merge B.
5. Generate C against the final backend/API contracts.

Validation expectations:

- A validates leakage safety and feature-frame compatibility.
- B validates model quality/comparison/backtesting/registry behavior.
- C validates TypeScript, UI behavior, and manual dashboard workflows.

Suggested future issue titles:

- `feat(forecasting): add feature frame v2 for retail demand signals`
- `feat(forecasting): add stronger baselines and v2 backtesting comparison`
- `feat(dashboard): add interactive forecast intelligence controls`
