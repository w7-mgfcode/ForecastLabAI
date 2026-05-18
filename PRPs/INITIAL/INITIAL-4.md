# INITIAL-4.md — Feature Engineering (Time-Safe)

## FEATURE:
- Forecasting feature pipeline:
  - calendar features (dow, month, holiday flags)
  - lag features (configurable lags)
  - rolling windows (configurable windows)
  - optional exogenous signals: price/promo/inventory
- Guaranteed time-safety:
  - features computed only up to a specified cutoff (no future leakage)
- Feature flags + schema versioning for long-term traceability.

## EXAMPLES:
- `examples/features/preview_features.py` — feature preview for a store×SKU series using an explicit cutoff.
- `examples/features/leakage_tests.py` — templates for leakage-focused tests.
- `examples/features/config_shape.json` — config shape for lags/windows/exog flags.

## DOCUMENTATION:
- Time-series feature engineering best practices
- scikit-learn transformers/pipelines (if used)
- [scikit-learn Pipeline Composition](https://scikit-learn.org/stable/modules/compose.html)
- [MLForecast Feature Engineering](https://www.nixtla.io/blog/automated-time-series-feature-engineering-with-mlforecast?utm_source=chatgpt.com#introduction-to-mlforecast)
- [sktime Transformations API](https://www.sktime.net/en/stable/api_reference/transformations.html)

## OTHER CONSIDERATIONS:
- Feature configs must be persisted per run in the registry.
- Reproducibility: same config + same data window must be re-runnable.
- **Imputation Logic**: Define behavior for missing price data (forward-fill) vs missing sales data (zero-fill).
- **Agent Tooling**: Expose the Feature Pipeline as a tool for PydanticAI to "inspect" the shape of the data before suggesting ModelConfigs.
- **Computation Overhead**: Evaluate if features should be computed on-the-fly in FastAPI or pre-computed in a materialized view for performance.
