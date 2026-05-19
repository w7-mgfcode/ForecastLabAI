# INITIAL-MLZOO-index.md - Advanced ML Model Zoo Roadmap

## FEATURE:

Split the Advanced ML Model Zoo into multiple INITIAL briefs so each future PRP can remain small, reviewable, and implementation-safe.

This index is the roadmap for the MLZOO sequence. Do not create one PRP that implements the full model zoo. The correct flow is:

1. Use this index to understand the full architecture.
2. Use `INITIAL-MLZOO-A-foundation-feature-frames.md` as the first PRP input.
3. Implement and merge the foundation before creating PRPs for later parts.
4. Promote B, C, and D into PRPs only after their prerequisites are stable.

Recommended PRP sequence:

| Order | INITIAL | Intended PRP | Purpose |
| --- | --- | --- | --- |
| 1 | `INITIAL-MLZOO-A-foundation-feature-frames.md` | PRP-29 | Feature-aware forecasting foundation and leakage-safe frame contracts |
| 2 | `INITIAL-MLZOO-B-lightgbm-first-model.md` | PRP-30 | First advanced model path with LightGBM (optional `ml-lightgbm` extra) |
| 3 | `INITIAL-MLZOO-C-xgboost-prophet-extensions.md` | Future PRP | XGBoost and Prophet-like extensions |
| 4 | `INITIAL-MLZOO-D-frontend-registry-explainability.md` | Future PRP | UI, registry surfacing, and explanation polish |

Dependency graph:

```text
A. Foundation feature frames
  -> B. LightGBM first model
      -> C. XGBoost / Prophet-like extensions
      -> D. Frontend / registry / explainability
```

The full vision is documented in `docs/optional-features/05-advanced-ml-model-zoo.md`.

## EXAMPLES:

Read these before creating any MLZOO PRP:

- `docs/optional-features/05-advanced-ml-model-zoo.md`
  - Full optional-feature concept and documentation links.

- `PRPs/INITIAL/INITIAL-5.md`
  - Earlier forecasting model brief, including baseline model zoo and global ML hooks.

- `docs/PHASE/4-FORECASTING.md`
  - Completed forecasting phase, model interface, configs, persistence, service, and API behavior.

- `app/features/forecasting/models.py`
  - Current baseline model interface.

- `app/features/featuresets/service.py`
  - Existing time-safe feature engineering.

- `app/features/featuresets/tests/test_leakage.py`
  - Existing leakage-safety testing pattern.

## DOCUMENTATION:

- LightGBM documentation: https://lightgbm.readthedocs.io/
- XGBoost documentation: https://xgboost.readthedocs.io/en/stable/
- Prophet documentation: https://facebook.github.io/prophet/docs/quick_start.html
- scikit-learn model persistence: https://scikit-learn.org/stable/model_persistence.html
- scikit-learn TimeSeriesSplit: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- scikit-learn Pipeline composition: https://scikit-learn.org/stable/modules/compose.html
- Pandas time series documentation: https://pandas.pydata.org/docs/user_guide/timeseries.html
- Joblib persistence documentation: https://joblib.readthedocs.io/en/stable/persistence.html
- Pydantic documentation: https://docs.pydantic.dev/latest/
- FastAPI documentation: https://fastapi.tiangolo.com/

## OTHER CONSIDERATIONS:

- The first PRP should be generated from `INITIAL-MLZOO-A-foundation-feature-frames.md`.
- Do not implement LightGBM before the feature-frame contracts and leakage tests are stable.
- Do not implement XGBoost or Prophet-like models before the first advanced model path proves the architecture.
- Do not add frontend/explainability scope before backend metadata and persistence contracts are stable.
- Keep each PRP to one branch and one reviewable unit.

