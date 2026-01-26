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

## OTHER CONSIDERATIONS:
- Feature configs must be persisted per run in the registry.
- Reproducibility: same config + same data window must be re-runnable.
