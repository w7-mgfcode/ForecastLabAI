"""Agent tools for PydanticAI integration.

This module provides tool wrappers for agents to interact with:
- Registry service (runs, aliases, comparisons)
- Backtesting service (run backtests, compare results)
- Forecasting service (train, predict)
- RAG service (retrieve context)
"""

from app.features.agents.tools.backtesting_tools import (
    compare_backtest_results,
    run_backtest,
)
from app.features.agents.tools.forecasting_tools import predict, train_model
from app.features.agents.tools.rag_tools import retrieve_context
from app.features.agents.tools.registry_tools import (
    archive_run,
    compare_runs,
    create_alias,
    get_run,
    list_runs,
)

__all__ = [
    "archive_run",
    "compare_backtest_results",
    "compare_runs",
    "create_alias",
    "get_run",
    "list_runs",
    "predict",
    "retrieve_context",
    "run_backtest",
    "train_model",
]
