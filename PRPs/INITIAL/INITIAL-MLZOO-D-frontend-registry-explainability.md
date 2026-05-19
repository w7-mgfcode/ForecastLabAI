# INITIAL-MLZOO-D-frontend-registry-explainability.md - Frontend, Registry, and Explainability Polish

## FEATURE:

Expose Advanced ML Model Zoo capabilities in the product after backend model contracts and at least one advanced model are stable.

This INITIAL is for later work, not PRP-29.

Goals:

- Add model selection UI where useful.
- Surface advanced model metadata in run detail and comparison pages.
- Show feature config, feature columns, dependency versions, and model family metadata.
- Add basic feature importance or explanation hooks where available.
- Update docs/admin surfaces so operators understand advanced model constraints.

Out of scope:

- Core feature-frame foundation.
- First advanced model backend implementation.
- XGBoost/Prophet backend implementation.
- Full SHAP explainability unless separately scoped.

## EXAMPLES:

Read these before PRP creation:

- `PRPs/INITIAL/INITIAL-MLZOO-A-foundation-feature-frames.md`
  - Foundation dependency.

- `PRPs/INITIAL/INITIAL-MLZOO-B-lightgbm-first-model.md`
  - First advanced model dependency.

- `frontend/src/pages/explorer/runs.tsx`
  - Existing run table.

- `frontend/src/pages/explorer/run-detail.tsx`
  - Existing run detail surface.

- `frontend/src/pages/explorer/run-compare.tsx`
  - Existing comparison surface.

- `frontend/src/pages/visualize/forecast.tsx`
  - Forecast visualization page.

- `frontend/src/pages/visualize/backtest.tsx`
  - Backtest visualization page.

- `app/features/registry/schemas.py`
  - Backend response contracts for run metadata.

## DOCUMENTATION:

- React Router documentation: https://reactrouter.com/home
- TanStack Query documentation: https://tanstack.com/query/latest/docs/framework/react/overview
- TanStack Table documentation: https://tanstack.com/table/latest/docs/overview
- shadcn/ui documentation: https://ui.shadcn.com/docs
- Recharts documentation: https://recharts.org/en-US/
- SHAP documentation: https://shap.readthedocs.io/en/stable/
- scikit-learn permutation importance: https://scikit-learn.org/stable/modules/permutation_importance.html

## OTHER CONSIDERATIONS:

- Do not create frontend controls before backend contracts are stable.
- Avoid adding a large admin panel if run detail and comparison pages are enough.
- Keep advanced model metadata readable and compact.
- Feature importance must be clearly labeled as model-derived, not causal truth.
- Browser QA is required for all frontend additions.

