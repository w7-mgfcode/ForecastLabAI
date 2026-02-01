"""Agent dependencies for tool access.

Provides the AgentDeps dataclass that is injected into all tool functions
via PydanticAI's RunContext mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
    """

    db: AsyncSession
    session_id: str
    request_id: str | None = None
    tool_call_count: int = field(default=0)

    def increment_tool_calls(self) -> int:
        """Increment and return the tool call count."""
        self.tool_call_count += 1
        return self.tool_call_count
