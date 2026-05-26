# INITIAL-forecast-intelligence-C-interactive-ui.md - Forecast Intelligence C: Interactive UI and Operator Workflow

## FEATURE:

Build the UI and interactive workflow layer for richer forecast intelligence.

This slice makes the Forecast Intelligence A/B backend capabilities usable by planners and operators without forcing them to understand every model internals detail. The UI should let users apply, compare, and vary feature-aware forecasting choices easily.

Current repo state:

- Frontend uses React 19, Vite 7, Tailwind 4, shadcn/ui New York, TanStack Query/Table, Recharts.
- Existing relevant pages:
  - `frontend/src/pages/visualize/forecast.tsx`
  - `frontend/src/pages/visualize/backtest.tsx`
  - `frontend/src/pages/visualize/demand.tsx`
  - `frontend/src/pages/visualize/planner.tsx`
  - `frontend/src/pages/visualize/batch.tsx`
  - `frontend/src/pages/explorer/runs.tsx`
  - `frontend/src/pages/explorer/run-detail.tsx`
  - `frontend/src/pages/explorer/run-compare.tsx`
  - `frontend/src/pages/ops.tsx`
- Existing components include charts, feature importance panels, explanation panels, data tables, status badges, job pickers, and batch controls.
- Existing backend surfaces include forecasting, backtesting, registry, ops/model health, explainability, scenarios, batch, and RAG/agents.

Problem:

The backend can gain richer features and models, but users need a clear control surface:

- choose model families
- choose feature frame version or feature packs
- compare simple baselines against richer models
- see why one model is better or worse
- vary assumptions interactively
- understand stale aliases, degrading model health, stockouts, and feature effects
- promote a model only after seeing metric and artifact context

Goals:

1. Forecast training UI:
   - Add model-family segmented controls:
     - Baseline
     - Tree
     - Additive
   - Add model type selector:
     - `naive`
     - `seasonal_naive`
     - `moving_average`
     - `weighted_moving_average` if Forecast Intelligence B adds it
     - `seasonal_average` if Forecast Intelligence B adds it
     - `regression`
     - `prophet_like`
     - `lightgbm` when enabled
     - `xgboost` when enabled
     - `random_forest` if added
   - Add feature-frame selector:
     - V1 safe/default
     - V2 extended when available
   - Add feature pack toggles if the backend exposes optional groups:
     - rolling
     - trend
     - yearly seasonality
     - price/promo
     - stockout
     - lifecycle
     - replenishment
     - returns
     - exogenous
   - Keep defaults conservative and beginner-safe.

2. Backtest/comparison UI:
   - Compare multiple models on the same store/product and same folds.
   - Show metric cards:
     - WAPE
     - sMAPE
     - MAE
     - bias
     - optional RMSE
   - Show horizon-bucket metrics if backend supports them.
   - Show "newer vs better" distinction so users do not promote a worse fresh run by mistake.
   - Add clear badges:
     - best WAPE
     - lowest bias
     - stale alias
     - degrading
     - stockout-constrained history
     - feature-aware
     - baseline

3. Run detail and compare UI:
   - Show feature frame version.
   - Show enabled feature groups.
   - Show top feature importances or additive components.
   - Show stockout and inventory caveats near forecasts where relevant.
   - Show artifact hash verification status in a visible but compact way.
   - Show whether the data window is comparable with the current champion.

4. Interactive planner UI:
   - Allow quick what-if variation:
     - price delta slider
     - promotion toggle
     - holiday toggle
     - inventory/stockout assumption
     - lifecycle stage assumption where supported
   - For feature-aware baselines, use `model_exogenous`.
   - For target-only baselines, clearly label heuristic adjustments.
   - Show side-by-side baseline vs scenario forecast.
   - Show which assumptions are "known future inputs" vs hypothetical.

5. Model health UI:
   - Make "degrading" explainable:
     - latest WAPE
     - previous comparable WAPE
     - delta WAPE
     - number of comparable runs
     - data window freshness
   - Make Promote safer:
     - require confirmation when latest WAPE is worse
     - show artifact verification
     - show champion/challenger comparison
     - show why the alias is stale

6. Batch UI:
   - Let users submit model sweeps across multiple model types and feature packs.
   - Add presets:
     - quick baseline sweep
     - feature-aware comparison
     - champion challenger refresh
     - stockout-sensitive products
     - high-WAPE recovery
   - Keep PRP-34 parallel execution controls compatible.

7. Agent/RAG support:
   - Add copyable context/actions from UI where useful:
     - "Explain why this model degraded"
     - "Summarize champion vs challenger"
     - "Recommend next backtest"
   - RAG should cite user-guide docs and app run context, not invent unsupported model behavior.

Out of scope:

- Replacing the whole dashboard IA.
- Creating a marketing-style landing page.
- Adding auth/roles.
- Adding managed-cloud SDKs.
- Adding backend model logic that belongs to Forecast Intelligence A or B.
- Adding agent mutation tools without updating `agent_require_approval`.

Expected UX principles:

- Dense but readable operational UI, not a marketing page.
- Use shadcn/ui controls:
  - segmented controls or tabs for model family
  - Select for model type and feature frame
  - Checkbox/toggle for feature packs
  - Slider for numeric what-if assumptions
  - Dialog/AlertDialog for risky promote actions
  - Tooltip for unfamiliar model/metric labels
  - DataTable for run comparisons
  - Recharts for forecast, error, and metric trends
- Avoid nested cards.
- Keep controls stable in size so labels and dynamic values do not shift layout.
- Do not use in-app tutorial prose for obvious UI behavior.
- Make the first screen an actual working tool, not a landing page.

## EXAMPLES:

Reference existing repo examples and patterns:

- `frontend/src/pages/visualize/forecast.tsx`
  - Existing train/predict workflow.

- `frontend/src/pages/visualize/backtest.tsx`
  - Existing backtest workflow and charts.

- `frontend/src/pages/visualize/planner.tsx`
  - Existing what-if scenario workflow.

- `frontend/src/pages/visualize/batch.tsx`
  - Existing batch submit/cancel/parallel controls.

- `frontend/src/pages/explorer/run-detail.tsx`
  - Existing model run detail page.

- `frontend/src/pages/explorer/run-compare.tsx`
  - Existing run comparison page.

- `frontend/src/pages/ops.tsx`
  - Existing model health / stale alias operational page.

- `frontend/src/components/explainability/explanation-panel.tsx`
  - Existing forecast explanation UI.

- `frontend/src/components/explainability/feature-importance-panel.tsx`
  - Existing feature metadata UI.

- `frontend/src/components/charts/backtest-folds-chart.tsx`
  - Existing backtest fold visualization.

- `frontend/src/hooks/use-runs.ts`
- `frontend/src/hooks/use-ops.ts`
- `frontend/src/hooks/use-batches.ts`
- `frontend/src/hooks/use-feature-metadata.ts`
  - Existing API integration patterns.

- `frontend/src/types/api.ts`
  - Update API types here when backend responses add feature frame metadata.

Potential example artifact to add:

- `docs/user-guide/advanced-forecasting-guide.md`
  - User-facing explanation of model families, feature packs, WAPE, stale aliases, and safe promotion.
  - Should be indexable by RAG.

## DOCUMENTATION:

External references to review during PRP creation and implementation:

- shadcn/ui docs: https://ui.shadcn.com/docs
- Radix UI Slider: https://www.radix-ui.com/primitives/docs/components/slider
- TanStack Query docs: https://tanstack.com/query/latest
- TanStack Table docs: https://tanstack.com/table/latest
- Recharts docs: https://recharts.org/en-US/
- scikit-learn lagged feature forecasting example, for UI labels and mental model: https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html
- Darts covariates guide, for "past vs future covariates" language: https://unit8co.github.io/darts/userguide/covariates.html
- Prophet seasonality/regressor docs, for additive component vocabulary: https://facebook.github.io/prophet/docs/seasonality%2C_holiday_effects%2C_and_regressors.html

Internal docs to review:

- `.claude/rules/ui-design.md`
- `docs/user-guide/dashboard-guide.md`
- `docs/user-guide/feature-reference.md`
- `docs/user-guide/agents-and-rag-guide.md`
- `docs/_base/API_CONTRACTS.md`
- `docs/_base/DOMAIN_MODEL.md`
- `docs/_base/REPO_MAP_INDEX.md`
- `PRPs/INITIAL/INITIAL-forecast-intelligence-A-feature-frame-v2.md`
- `PRPs/INITIAL/INITIAL-forecast-intelligence-B-model-zoo-backtesting.md`

## OTHER CONSIDERATIONS:

Backend/API prerequisites:

- This UI slice should be generated after the backend response contracts are clear.
- If Forecast Intelligence A/B have not landed, this PRP should first create UI affordances only for existing fields:
  - existing model types
  - existing model family
  - existing feature metadata
  - existing WAPE/model health data
- Do not fake backend values in the UI.

Frontend constraints:

- Use existing shadcn/ui components or add them through the repo's shadcn workflow.
- Do not hand-roll components when a local `components/ui/*` component exists.
- Keep URL-shareable filters/sort/page state where existing Explorer pages already do this.
- Keep TypeScript strict and tests green.
- Add component/hook tests for risky conditional rendering:
  - missing feature metadata
  - optional LightGBM/XGBoost disabled
  - stale alias with worse latest WAPE
  - artifact verification failure
  - target-only model using heuristic scenario method
  - feature-aware model using `model_exogenous`

UX gotchas:

- "Promote" must not imply "better" when the latest run has worse metrics.
- "Feature-aware" must not imply causal truth. Feature importance explains model arithmetic or split usage, not business causality.
- Stockout caveats must be visible because observed sales can understate true demand.
- "Future covariates" should be labeled as planned or assumed inputs, not known facts unless the business actually knows them.
- Avoid overwhelming users with every raw feature column by default. Show groups first, drill down on demand.

Recommended validation commands:

```bash
cd frontend && pnpm tsc --noEmit
cd frontend && pnpm lint
cd frontend && pnpm test --run
uv run pytest -v app/features/forecasting/tests app/features/backtesting/tests app/features/registry/tests app/features/ops/tests -m "not integration"
```
