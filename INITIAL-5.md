# INITIAL-5.md — Forecast Models v0 (Baselines + Global ML Hooks)

## FEATURE:
- Model zoo (minimum set):
  - naive
  - seasonal naive (weekday/week lag)
  - moving average (configurable windows)
- A unified model interface:
  - fit / predict
  - serialize / load
- Extensible “Global ML” hook:
  - regression pipeline (scikit-learn)
  - enabled/disabled via feature flags

## EXAMPLES:
- `examples/models/baseline_naive.py`
- `examples/models/baseline_seasonal.py`
- `examples/models/baseline_mavg.py`
- `examples/models/model_interface.md` — contract: input/output shapes + config schema.

## DOCUMENTATION:
- scikit-learn estimators + pipelines
- joblib serialization patterns
- https://scikit-learn.org/stable/modules/compose.html
- https://scikit-learn.org/stable/glossary.html
- https://scikit-learn.org/stable/model_persistence.html

## OTHER CONSIDERATIONS:
- No hardcoded horizons: driven by request/config.
- Determinism: random seed from Settings.
- Enforce input grain validation (store×product×date).