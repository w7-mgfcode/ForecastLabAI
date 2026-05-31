"""Agent dependencies for tool access.

Provides the AgentDeps dataclass that is injected into all tool functions
via PydanticAI's RunContext mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class AgentDeps:
    """Dependencies passed to agent tools via RunContext.

    This dataclass is injected into all tool functions, providing access
    to shared resources like database sessions and request context.

    Attributes:
        db: Database session for tool operations.
        session_id: Current agent session ID.
        request_id: Optional request correlation ID for logging.
        tool_call_count: Counter for tool calls in this run.
        pending_action: Machine-readable HITL approval request recorded by a
            gated tool when it short-circuits without persisting (#336). The
            service layer reads this after the agent run to flip the session to
            ``awaiting_approval`` and emit the ``approval_required`` event,
            instead of relying on the model echoing the request into its
            structured output.
    """

    db: AsyncSession
    session_id: str
    request_id: str | None = None
    tool_call_count: int = field(default=0)
    pending_action: dict[str, Any] | None = field(default=None)

    def increment_tool_calls(self) -> int:
        """Increment and return the tool call count."""
        self.tool_call_count += 1
        return self.tool_call_count

    def set_pending_action(
        self,
        action_type: str,
        arguments: dict[str, Any],
        description: str,
    ) -> None:
        """Record that a gated tool call needs human approval (HITL).

        Called by approval-gated tools (e.g. ``save_scenario``, ``create_alias``,
        ``archive_run``) instead of persisting their effect. The ``arguments``
        dict must carry everything ``AgentService._execute_pending_action`` needs
        to run the action once a human approves it.

        Args:
            action_type: The gated action name (``create_alias`` / ``archive_run``
                / ``save_scenario``).
            arguments: Arguments to replay when the action is approved.
            description: Human-readable summary shown on the approval card.
        """
        self.pending_action = {
            "action_type": action_type,
            "arguments": arguments,
            "description": description,
        }
