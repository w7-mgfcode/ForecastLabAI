"""Unit tests for agent schemas."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.features.agents.models import AgentType
from app.features.agents.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ExperimentPlan,
    ExperimentReport,
    PendingAction,
    RAGAnswer,
    SessionCreateRequest,
    SessionResponse,
    StreamEvent,
    ToolCallResult,
)


class TestSessionCreateRequest:
    """Tests for SessionCreateRequest schema."""

    def test_create_experiment_session(self) -> None:
        """Should create experiment session request."""
        request = SessionCreateRequest(
            agent_type=AgentType.EXPERIMENT.value,
        )
        assert request.agent_type == "experiment"
        assert request.initial_context is None

    def test_create_rag_session(self) -> None:
        """Should create RAG session request."""
        request = SessionCreateRequest(
            agent_type=AgentType.RAG_ASSISTANT.value,
        )
        assert request.agent_type == "rag_assistant"

    def test_create_with_context(self) -> None:
        """Should create with initial context."""
        context = {"objective": "test", "store_id": 1}
        request = SessionCreateRequest(
            agent_type=AgentType.EXPERIMENT.value,
            initial_context=context,
        )
        assert request.initial_context == context

    def test_missing_agent_type_raises(self) -> None:
        """Should raise for missing agent_type."""
        with pytest.raises(ValidationError):
            SessionCreateRequest()  # type: ignore[call-arg]


class TestSessionResponse:
    """Tests for SessionResponse schema."""

    def test_session_response_creation(self) -> None:
        """Should create session response."""
        now = datetime.now(UTC)
        response = SessionResponse(
            session_id="abc123",
            agent_type="experiment",
            status="active",
            total_tokens_used=100,
            tool_calls_count=5,
            last_activity=now,
            expires_at=now + timedelta(minutes=30),
            created_at=now,
        )
        assert response.session_id == "abc123"
        assert response.total_tokens_used == 100
        assert response.tool_calls_count == 5


class TestChatRequest:
    """Tests for ChatRequest schema."""

    def test_chat_request_minimal(self) -> None:
        """Should create minimal chat request."""
        request = ChatRequest(message="Hello")
        assert request.message == "Hello"
        assert request.stream is False

    def test_chat_request_with_stream(self) -> None:
        """Should create with stream enabled."""
        request = ChatRequest(
            message="Hello",
            stream=True,
        )
        assert request.stream is True

    def test_empty_message_raises(self) -> None:
        """Should raise for empty message."""
        with pytest.raises(ValidationError):
            ChatRequest(message="")


class TestChatResponse:
    """Tests for ChatResponse schema."""

    def test_chat_response_minimal(self) -> None:
        """Should create minimal chat response."""
        response = ChatResponse(
            session_id="abc123",
            message="Hello there!",
        )
        assert response.session_id == "abc123"
        assert response.message == "Hello there!"
        assert response.tool_calls == []
        assert response.pending_approval is False
        assert response.tokens_used == 0

    def test_chat_response_with_tool_calls(self) -> None:
        """Should create with tool calls."""
        tool_call = ToolCallResult(
            tool_name="list_runs",
            tool_call_id="call-123",
            arguments={"page": 1},
            result={"runs": []},
            duration_ms=50.0,
        )
        response = ChatResponse(
            session_id="abc123",
            message="Found no runs.",
            tool_calls=[tool_call],
            tokens_used=50,
        )
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].tool_name == "list_runs"

    def test_chat_response_with_pending_action(self) -> None:
        """Should create with pending action."""
        now = datetime.now(UTC)
        pending = PendingAction(
            action_id="act123",
            action_type="create_alias",
            description="Create alias",
            arguments={"name": "prod"},
            created_at=now,
            expires_at=now + timedelta(minutes=5),
        )
        response = ChatResponse(
            session_id="abc123",
            message="Approval required",
            pending_approval=True,
            pending_action=pending,
        )
        assert response.pending_approval is True
        assert response.pending_action is not None


class TestToolCallResult:
    """Tests for ToolCallResult schema."""

    def test_tool_call_result(self) -> None:
        """Should create tool call result."""
        result = ToolCallResult(
            tool_name="run_backtest",
            tool_call_id="call-456",
            arguments={"store_id": 1, "product_id": 10},
            result={"status": "success"},
            duration_ms=150.5,
        )
        assert result.tool_name == "run_backtest"
        assert result.arguments["store_id"] == 1
        assert result.duration_ms == 150.5

    def test_tool_call_result_null_result(self) -> None:
        """Should allow null result."""
        result = ToolCallResult(
            tool_name="run_backtest",
            tool_call_id="call-789",
            arguments={},
            result=None,
            duration_ms=10.0,
        )
        assert result.result is None


class TestPendingAction:
    """Tests for PendingAction schema."""

    def test_pending_action_creation(self) -> None:
        """Should create pending action."""
        now = datetime.now(UTC)
        action = PendingAction(
            action_id="act123",
            action_type="create_alias",
            description="Create production alias",
            arguments={"alias_name": "production", "run_id": "run456"},
            created_at=now,
            expires_at=now + timedelta(minutes=5),
        )
        assert action.action_id == "act123"
        assert action.action_type == "create_alias"
        assert "alias_name" in action.arguments


class TestApprovalRequest:
    """Tests for ApprovalRequest schema."""

    def test_approval_request_approve(self) -> None:
        """Should create approval request."""
        request = ApprovalRequest(
            action_id="act123",
            approved=True,
        )
        assert request.approved is True
        assert request.reason is None

    def test_approval_request_reject_with_reason(self) -> None:
        """Should create rejection with reason."""
        request = ApprovalRequest(
            action_id="act123",
            approved=False,
            reason="Not ready for production",
        )
        assert request.approved is False
        assert request.reason == "Not ready for production"


class TestApprovalResponse:
    """Tests for ApprovalResponse schema."""

    def test_approval_response_executed(self) -> None:
        """Should create executed response."""
        response = ApprovalResponse(
            action_id="act123",
            approved=True,
            status="executed",
            result={"message": "Alias created"},
        )
        assert response.status == "executed"
        assert response.result is not None

    def test_approval_response_rejected(self) -> None:
        """Should create rejected response."""
        response = ApprovalResponse(
            action_id="act123",
            approved=False,
            status="rejected",
        )
        assert response.status == "rejected"
        assert response.result is None


class TestStreamEvent:
    """Tests for StreamEvent schema."""

    def test_text_delta_event(self) -> None:
        """Should create text delta event."""
        now = datetime.now(UTC)
        event = StreamEvent(
            event_type="text_delta",
            data={"delta": "Hello"},
            timestamp=now,
        )
        assert event.event_type == "text_delta"
        assert event.data["delta"] == "Hello"

    def test_tool_call_start_event(self) -> None:
        """Should create tool call start event."""
        now = datetime.now(UTC)
        event = StreamEvent(
            event_type="tool_call_start",
            data={
                "tool_name": "list_runs",
                "tool_call_id": "call-123",
                "arguments": {"page": 1},
            },
            timestamp=now,
        )
        assert event.event_type == "tool_call_start"

    def test_complete_event(self) -> None:
        """Should create complete event."""
        now = datetime.now(UTC)
        event = StreamEvent(
            event_type="complete",
            data={
                "message": "Done!",
                "tokens_used": 100,
            },
            timestamp=now,
        )
        assert event.event_type == "complete"

    def test_error_event(self) -> None:
        """Should create error event."""
        now = datetime.now(UTC)
        event = StreamEvent(
            event_type="error",
            data={
                "error": "Session expired",
                "recoverable": False,
            },
            timestamp=now,
        )
        assert event.event_type == "error"


class TestExperimentPlan:
    """Tests for ExperimentPlan schema."""

    def test_experiment_plan_minimal(self) -> None:
        """Should create minimal experiment plan."""
        plan = ExperimentPlan(
            goal="Find best model",
            steps=["Step 1", "Step 2"],
            model_type="naive",
        )
        assert plan.goal == "Find best model"
        assert len(plan.steps) == 2
        assert plan.model_type == "naive"
        assert plan.parameters == {}

    def test_experiment_plan_full(self) -> None:
        """Should create full experiment plan."""
        plan = ExperimentPlan(
            goal="Compare all models",
            steps=["Prepare data", "Run backtests", "Compare results"],
            model_type="seasonal_naive",
            parameters={"horizon": 14, "n_splits": 10},
            data_requirements={"start": "2024-01-01", "end": "2024-06-30"},
        )
        assert len(plan.steps) == 3
        assert plan.parameters["horizon"] == 14


class TestExperimentReport:
    """Tests for ExperimentReport schema."""

    def test_experiment_report_success(self) -> None:
        """Should create successful report."""
        report = ExperimentReport(
            run_id="run123",
            status="success",
            summary="Experiment completed successfully",
            metrics={"mae": 10.5, "smape": 15.3},
            recommendations=["Deploy model", "Monitor performance"],
        )
        assert report.run_id == "run123"
        assert report.status == "success"
        assert report.metrics["mae"] == 10.5
        assert len(report.recommendations) == 2

    def test_experiment_report_minimal(self) -> None:
        """Should create minimal report."""
        report = ExperimentReport(
            run_id="run456",
            status="failed",
            summary="Experiment failed due to insufficient data",
        )
        assert report.status == "failed"
        assert report.metrics == {}
        assert report.recommendations == []


class TestRAGAnswer:
    """Tests for RAGAnswer schema."""

    def test_rag_answer_with_sources(self) -> None:
        """Should create answer with sources."""
        answer = RAGAnswer(
            answer="The API supports naive and seasonal_naive models.",
            confidence="high",
            sources=[
                {"source_path": "docs/api.md", "relevance": 0.95},
            ],
        )
        assert len(answer.sources) == 1
        assert answer.confidence == "high"
        assert answer.no_evidence is False

    def test_rag_answer_no_evidence(self) -> None:
        """Should create answer with no evidence."""
        answer = RAGAnswer(
            answer="I don't have enough information to answer that question.",
            confidence="low",
            sources=[],
            no_evidence=True,
        )
        assert answer.no_evidence is True
        assert answer.confidence == "low"

    def test_rag_answer_medium_confidence(self) -> None:
        """Should allow medium confidence."""
        answer = RAGAnswer(
            answer="Test answer",
            confidence="medium",
        )
        assert answer.confidence == "medium"


class TestChatMessage:
    """Tests for ChatMessage schema."""

    def test_user_message(self) -> None:
        """Should create user message."""
        msg = ChatMessage(
            role="user",
            content="Run a backtest",
        )
        assert msg.role == "user"
        assert msg.content == "Run a backtest"
        assert msg.timestamp is None  # Default is None

    def test_assistant_message(self) -> None:
        """Should create assistant message."""
        msg = ChatMessage(
            role="assistant",
            content="Running backtest...",
        )
        assert msg.role == "assistant"

    def test_tool_message(self) -> None:
        """Should create tool message."""
        msg = ChatMessage(
            role="tool",
            content='{"status": "success"}',
            tool_call_id="call-123",
        )
        assert msg.role == "tool"
        assert msg.tool_call_id == "call-123"
