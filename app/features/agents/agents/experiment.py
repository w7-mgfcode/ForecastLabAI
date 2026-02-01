"""Experiment Orchestrator Agent for autonomous model experimentation.

This agent:
- Plans and executes backtesting experiments
- Compares model performance
- Recommends and deploys best models
- Requires human approval for deployment actions
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

import structlog
from pydantic_ai import Agent, RunContext

from app.features.agents.agents.base import (
    SAFETY_INSTRUCTIONS,
    SYSTEM_PROMPT_HEADER,
    TOOL_USAGE_INSTRUCTIONS,
    get_model_identifier,
    get_model_settings,
    requires_approval,
    validate_api_key_for_model,
)
from app.features.agents.deps import AgentDeps
from app.features.agents.schemas import ExperimentReport
from app.features.agents.tools.backtesting_tools import (
    compare_backtest_results,
    run_backtest,
)
from app.features.agents.tools.registry_tools import (
    archive_run,
    compare_runs,
    create_alias,
    get_run,
    list_runs,
)

logger = structlog.get_logger()

# Experiment-specific system prompt
EXPERIMENT_SYSTEM_PROMPT = f"""{SYSTEM_PROMPT_HEADER}

You are the Experiment Orchestrator Agent. Your role is to:
1. Understand the user's forecasting objective
2. Plan an experiment strategy (which models to try, data range, splits)
3. Execute backtests using available tools
4. Analyze results and compare to baselines
5. Recommend the best model with justification
6. Optionally deploy the winner (requires human approval)

WORKFLOW:
1. Parse the objective to understand what the user wants
2. Check existing runs with list_runs to avoid duplicates
3. Run backtests for candidate models
4. Compare results using compare_backtest_results
5. Formulate recommendation with clear metrics
6. If auto_deploy requested and model beats baselines, propose deployment

{TOOL_USAGE_INSTRUCTIONS}

{SAFETY_INSTRUCTIONS}
"""

# Lazily created agent instance
_experiment_agent: Agent[AgentDeps, ExperimentReport] | None = None


def create_experiment_agent() -> Agent[AgentDeps, ExperimentReport]:
    """Create and configure the experiment agent with all tools.

    Returns:
        Configured Agent instance with tools registered.
    """
    model = get_model_identifier()
    validate_api_key_for_model(model)  # Fail-fast validation

    agent: Agent[AgentDeps, ExperimentReport] = Agent(
        model=model,
        deps_type=AgentDeps,
        output_type=ExperimentReport,
        system_prompt=EXPERIMENT_SYSTEM_PROMPT,
        **get_model_settings(),
    )

    # Register tools with the agent
    @agent.tool
    async def tool_list_runs(
        ctx: RunContext[AgentDeps],
        page: int = 1,
        page_size: int = 10,
        model_type: str | None = None,
        status: str | None = None,
        store_id: int | None = None,
        product_id: int | None = None,
    ) -> dict[str, Any]:
        """List model runs from the registry with filtering.

        Use this to browse existing experiments and find runs to compare or analyze.

        Args:
            page: Page number (1-indexed, default 1).
            page_size: Results per page (default 10, max 100).
            model_type: Filter by model type (e.g., 'naive', 'seasonal_naive').
            status: Filter by status ('pending', 'running', 'success', 'failed').
            store_id: Filter by store ID.
            product_id: Filter by product ID.

        Returns:
            Dictionary with 'runs' list and pagination info.
        """
        ctx.deps.increment_tool_calls()
        logger.info(
            "agents.experiment.tool_list_runs",
            session_id=ctx.deps.session_id,
            tool_call_count=ctx.deps.tool_call_count,
        )
        return await list_runs(
            db=ctx.deps.db,
            page=page,
            page_size=page_size,
            model_type=model_type,
            status=status,
            store_id=store_id,
            product_id=product_id,
        )

    @agent.tool
    async def tool_get_run(
        ctx: RunContext[AgentDeps],
        run_id: str,
    ) -> dict[str, Any] | None:
        """Get detailed information about a specific model run.

        Args:
            run_id: The unique run identifier (32-char hex string).

        Returns:
            Run details dictionary or None if not found.
        """
        ctx.deps.increment_tool_calls()
        logger.info(
            "agents.experiment.tool_get_run",
            session_id=ctx.deps.session_id,
            run_id=run_id,
        )
        return await get_run(db=ctx.deps.db, run_id=run_id)

    @agent.tool
    async def tool_run_backtest(
        ctx: RunContext[AgentDeps],
        store_id: int,
        product_id: int,
        start_date: str,
        end_date: str,
        model_type: str = "naive",
        n_splits: int = 5,
        horizon: int = 7,
        strategy: Literal["expanding", "sliding"] = "expanding",
        min_train_size: int = 30,
        include_baselines: bool = True,
    ) -> dict[str, Any]:
        """Run a backtest to evaluate model performance.

        Use this to test a model configuration with time-based cross-validation.

        Args:
            store_id: Store ID to backtest.
            product_id: Product ID to backtest.
            start_date: Start date (YYYY-MM-DD format).
            end_date: End date (YYYY-MM-DD format).
            model_type: Model to test ('naive', 'seasonal_naive', 'moving_average').
            n_splits: Number of CV folds (default 5).
            horizon: Forecast horizon in days (default 7).
            strategy: CV strategy ('expanding' or 'sliding').
            min_train_size: Minimum training observations (default 30).
            include_baselines: Compare against baselines (default True).

        Returns:
            BacktestResponse with aggregated metrics.
        """
        ctx.deps.increment_tool_calls()
        logger.info(
            "agents.experiment.tool_run_backtest",
            session_id=ctx.deps.session_id,
            store_id=store_id,
            product_id=product_id,
            model_type=model_type,
        )

        # Parse date strings
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        return await run_backtest(
            db=ctx.deps.db,
            store_id=store_id,
            product_id=product_id,
            start_date=start,
            end_date=end,
            model_type=model_type,
            n_splits=n_splits,
            horizon=horizon,
            strategy=strategy,
            min_train_size=min_train_size,
            include_baselines=include_baselines,
        )

    @agent.tool_plain
    def tool_compare_backtest_results(
        result_a: dict[str, Any],
        result_b: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare two backtest results.

        Use this to analyze which model performs better.

        Args:
            result_a: First backtest result.
            result_b: Second backtest result.

        Returns:
            Comparison with metric differences and recommendation.
        """
        return compare_backtest_results(result_a, result_b)

    @agent.tool
    async def tool_compare_runs(
        ctx: RunContext[AgentDeps],
        run_id_a: str,
        run_id_b: str,
    ) -> dict[str, Any] | None:
        """Compare two registered model runs.

        Args:
            run_id_a: First run ID.
            run_id_b: Second run ID.

        Returns:
            Comparison with config and metric differences.
        """
        ctx.deps.increment_tool_calls()
        logger.info(
            "agents.experiment.tool_compare_runs",
            session_id=ctx.deps.session_id,
            run_id_a=run_id_a,
            run_id_b=run_id_b,
        )
        return await compare_runs(
            db=ctx.deps.db,
            run_id_a=run_id_a,
            run_id_b=run_id_b,
        )

    @agent.tool
    async def tool_create_alias(
        ctx: RunContext[AgentDeps],
        alias_name: str,
        run_id: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a deployment alias for a successful run.

        REQUIRES HUMAN APPROVAL.

        Use this to promote a model to production or staging.

        Args:
            alias_name: Name for the alias (e.g., 'production').
            run_id: Run ID to alias (must be SUCCESS status).
            description: Optional description.

        Returns:
            Created alias details or approval request.
        """
        ctx.deps.increment_tool_calls()
        logger.info(
            "agents.experiment.tool_create_alias",
            session_id=ctx.deps.session_id,
            alias_name=alias_name,
            run_id=run_id,
            requires_approval=requires_approval("create_alias"),
        )

        # Check if approval is required
        if requires_approval("create_alias"):
            return {
                "status": "approval_required",
                "action": "create_alias",
                "alias_name": alias_name,
                "run_id": run_id,
                "description": description,
                "message": "This action requires human approval. Please approve to proceed.",
            }

        return await create_alias(
            db=ctx.deps.db,
            alias_name=alias_name,
            run_id=run_id,
            description=description,
        )

    @agent.tool
    async def tool_archive_run(
        ctx: RunContext[AgentDeps],
        run_id: str,
    ) -> dict[str, Any] | None:
        """Archive a model run.

        REQUIRES HUMAN APPROVAL.

        Use this to mark runs as no longer active.

        Args:
            run_id: Run ID to archive.

        Returns:
            Updated run details or approval request.
        """
        ctx.deps.increment_tool_calls()
        logger.info(
            "agents.experiment.tool_archive_run",
            session_id=ctx.deps.session_id,
            run_id=run_id,
            requires_approval=requires_approval("archive_run"),
        )

        # Check if approval is required
        if requires_approval("archive_run"):
            return {
                "status": "approval_required",
                "action": "archive_run",
                "run_id": run_id,
                "message": "This action requires human approval. Please approve to proceed.",
            }

        return await archive_run(db=ctx.deps.db, run_id=run_id)

    return agent


def get_experiment_agent() -> Agent[AgentDeps, ExperimentReport]:
    """Get or create the experiment agent singleton.

    Returns:
        Configured experiment agent instance.
    """
    global _experiment_agent
    if _experiment_agent is None:
        _experiment_agent = create_experiment_agent()
    return _experiment_agent
