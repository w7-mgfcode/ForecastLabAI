"""Forecast Champion Selector — backend vertical slice (issue #353).

Validates a (store, product) pair's data availability, runs comparable
backtests for a set of candidate forecasting models, deterministically ranks
them, selects a champion with a recommendation confidence, persists an
auditable selection run, and optionally trains/predicts with the winner.

Backend-only by design — the UI is a deliberate follow-up PRP.
"""
