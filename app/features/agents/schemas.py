"""Pydantic schemas for Agents API contracts.

Schemas are designed to be:
- Validated for data integrity
- Compatible with SQLAlchemy models via from_attributes
- Structured for PydanticAI agent integration
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(UTC)

# =============================================================================
# Session Management Schemas
# =============================================================================


class SessionCreateRequest(BaseModel):
    """Request to create a new agent session.

    Args:
        agent_type: Type of agent to use (experiment or rag_assistant).
        initial_context: Optional context to prime the conversation.
    """

    model_config = ConfigDict(extra="forbid")

    agent_type: Literal["experiment", "rag_assistant"] = Field(
        ..., description="Type of agent to use"
    )
    initial_context: dict[str, Any] | None = Field(
        None, description="Optional context to prime the conversation"
    )


class SessionResponse(BaseModel):
    """Response containing session details.

    Args:
        session_id: Unique session identifier.
        agent_type: Type of agent for this session.
        status: Current session status.
        total_tokens_used: Cumulative token usage.
        tool_calls_count: Number of tool invocations.
        last_activity: Last interaction timestamp.
        expires_at: Session expiration timestamp.
        created_at: Session creation timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    session_id: str
    agent_type: str
    status: str
    total_tokens_used: int
    tool_calls_count: int
    last_activity: datetime
    expires_at: datetime
    created_at: datetime


class SessionListResponse(BaseModel):
    """List of active sessions.

    Args:
        sessions: List of session summaries.
        total_count: Total number of active sessions.
    """

    sessions: list[SessionResponse]
    total_count: int


# =============================================================================
# Chat Interaction Schemas
# =============================================================================


class ChatMessage(BaseModel):
    """Single message in a conversation.

    Args:
        role: Message role (user, assistant, or tool).
        content: Message content.
        timestamp: When the message was created.
        tool_call_id: Optional tool call identifier.
        tool_name: Optional name of tool that was called.
    """

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant", "tool"] = Field(
        ..., description="Message role"
    )
    content: str = Field(..., description="Message content")
    timestamp: datetime | None = Field(None, description="Message timestamp")
    tool_call_id: str | None = Field(None, description="Tool call identifier")
    tool_name: str | None = Field(None, description="Tool that was called")


class ChatRequest(BaseModel):
    """Request to send a message to the agent.

    Args:
        message: User message to send.
        stream: Whether to stream the response.
    """

    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="User message to send",
    )
    stream: bool = Field(default=False, description="Whether to stream the response")


class ToolCallResult(BaseModel):
    """Result of a tool call.

    Args:
        tool_name: Name of the tool that was called.
        tool_call_id: Unique identifier for this call.
        arguments: Arguments passed to the tool.
        result: Result from the tool execution.
        duration_ms: Time taken to execute the tool.
    """

    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any]
    result: Any
    duration_ms: float


class ChatResponse(BaseModel):
    """Response from the agent.

    Args:
        session_id: Session identifier.
        message: Agent response message.
        tool_calls: List of tools that were called.
        pending_approval: Whether approval is required for next action.
        pending_action: Details of action awaiting approval.
        tokens_used: Tokens consumed in this interaction.
    """

    session_id: str
    message: str
    tool_calls: list[ToolCallResult] = Field(default_factory=list)
    pending_approval: bool = False
    pending_action: PendingAction | None = None
    tokens_used: int = 0


# =============================================================================
# Human-in-the-Loop Approval Schemas
# =============================================================================


class PendingAction(BaseModel):
    """Action awaiting human approval.

    Args:
        action_id: Unique identifier for the pending action.
        action_type: Type of action (tool name).
        description: Human-readable description.
        arguments: Arguments for the action.
        created_at: When the action was queued.
        expires_at: When the approval request expires.
    """

    model_config = ConfigDict(from_attributes=True)

    action_id: str
    action_type: str
    description: str
    arguments: dict[str, Any]
    created_at: datetime
    expires_at: datetime


class ApprovalRequest(BaseModel):
    """Request to approve or reject a pending action.

    Args:
        action_id: Identifier of the action to approve/reject.
        approved: Whether to approve the action.
        reason: Optional reason for the decision.
    """

    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(..., description="Action to approve/reject")
    approved: bool = Field(..., description="Whether to approve the action")
    reason: str | None = Field(None, max_length=500, description="Reason for decision")


class ApprovalResponse(BaseModel):
    """Response from approval decision.

    Args:
        action_id: Identifier of the processed action.
        approved: Whether the action was approved.
        result: Result if action was executed.
        status: Final status of the action.
    """

    action_id: str
    approved: bool
    result: Any | None = None
    status: Literal["executed", "rejected", "expired"]


# =============================================================================
# Streaming Event Schemas (for WebSocket)
# =============================================================================


class StreamEvent(BaseModel):
    """WebSocket streaming event.

    Args:
        event_type: Type of streaming event.
        data: Event payload.
        timestamp: When the event occurred.
    """

    event_type: Literal[
        "text_delta",
        "tool_call_start",
        "tool_call_end",
        "approval_required",
        "complete",
        "error",
    ] = Field(..., description="Type of streaming event")
    data: dict[str, Any] = Field(..., description="Event payload")
    timestamp: datetime = Field(default_factory=_utc_now)


class TextDeltaEvent(BaseModel):
    """Text delta streaming event.

    Args:
        delta: New text to append.
    """

    delta: str


class ToolCallStartEvent(BaseModel):
    """Tool call started event.

    Args:
        tool_name: Name of the tool being called.
        tool_call_id: Unique call identifier.
        arguments: Arguments for the tool.
    """

    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any]


class ToolCallEndEvent(BaseModel):
    """Tool call completed event.

    Args:
        tool_name: Name of the tool that was called.
        tool_call_id: Unique call identifier.
        result: Tool execution result.
        duration_ms: Execution time.
    """

    tool_name: str
    tool_call_id: str
    result: Any
    duration_ms: float


class CompleteEvent(BaseModel):
    """Response complete event.

    Args:
        message: Full response message.
        tokens_used: Total tokens consumed.
        tool_calls_count: Number of tools called.
    """

    message: str
    tokens_used: int
    tool_calls_count: int


class ErrorEvent(BaseModel):
    """Error event.

    Args:
        error: Error message.
        error_type: Type of error.
        recoverable: Whether the session can continue.
    """

    error: str
    error_type: str
    recoverable: bool = True


# =============================================================================
# Agent Output Schemas (PydanticAI structured outputs)
# =============================================================================


class ExperimentPlan(BaseModel):
    """Structured output from experiment agent planning phase.

    Args:
        goal: High-level experiment goal.
        steps: List of planned steps.
        model_type: Recommended model type.
        parameters: Suggested model parameters.
        data_requirements: Required data window.
    """

    goal: str = Field(..., description="High-level experiment goal")
    steps: list[str] = Field(..., description="Planned steps")
    model_type: str = Field(..., description="Recommended model type")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Model parameters")
    data_requirements: dict[str, Any] = Field(
        default_factory=dict, description="Data window requirements"
    )


class ExperimentReport(BaseModel):
    """Structured output from experiment agent after completion.

    Args:
        run_id: Registry run identifier.
        status: Run status (success/failed).
        summary: Human-readable summary.
        metrics: Performance metrics.
        recommendations: Follow-up recommendations.
    """

    run_id: str = Field(..., description="Registry run identifier")
    status: str = Field(..., description="Run status")
    summary: str = Field(..., description="Human-readable summary")
    metrics: dict[str, float] = Field(default_factory=dict, description="Performance metrics")
    recommendations: list[str] = Field(
        default_factory=list, description="Follow-up recommendations"
    )


class RAGAnswer(BaseModel):
    """Structured output from RAG assistant.

    Args:
        answer: The evidence-grounded answer.
        confidence: Confidence level (low/medium/high).
        sources: List of source citations.
        no_evidence: Whether sufficient evidence was found.
    """

    answer: str = Field(..., description="Evidence-grounded answer")
    confidence: Literal["low", "medium", "high"] = Field(
        ..., description="Confidence level"
    )
    sources: list[dict[str, Any]] = Field(default_factory=list, description="Source citations")
    no_evidence: bool = Field(
        default=False, description="True if insufficient evidence"
    )
