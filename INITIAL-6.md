# INITIAL-6.md — Backtesting + Metrics (ForecastOps Core)

## FEATURE:
- Time-based backtesting:
  - rolling window and expanding window (configurable)
  - configurable horizon
  - per-series metrics + aggregated metrics
- Minimum metrics:
  - MAE
  - sMAPE
  - (optional) pinball loss later
- Persist split boundaries and evaluation artifacts.

## EXAMPLES:
- `examples/backtest/run_backtest.py` — generates splits from config and executes evaluations.
- `examples/backtest/inspect_splits.py` — prints split boundaries + sanity checks.
- `examples/backtest/metrics_demo.py` — edge cases (e.g., zeros in sMAPE).

## DOCUMENTATION:
- Time-series cross-validation patterns
- Metric definitions + edge cases

## OTHER CONSIDERATIONS:
- Random splits are prohibited.
- Aggregation must not mask failures: expose per-series distributions.
- Automated leakage sanity checks during backtests.
